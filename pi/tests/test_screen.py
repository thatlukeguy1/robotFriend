"""Tests for the screen driver, with a pretend SPI link and pretend pins."""
from PIL import Image

from bolt_body.screen import Screen, to_rgb565


class PretendSPI:
    def __init__(self):
        self.sent = []          # (dc_level, bytes)
        self.dc = None
    def writebytes(self, data):
        self.sent.append((self.dc.level, bytes(data)))
    def writebytes2(self, data):
        self.sent.append((self.dc.level, bytes(data)))


class PretendPin:
    def __init__(self):
        self.level = 0
    def on(self):
        self.level = 1
    def off(self):
        self.level = 0


def make(rotation=90):
    spi, dc, reset = PretendSPI(), PretendPin(), PretendPin()
    spi.dc = dc
    return Screen(spi=spi, dc=dc, reset=reset, rotation=rotation, backlight=PretendPin()), spi


def test_rgb565_packs_colours():
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (255, 0, 0))   # red   -> 0xF800
    img.putpixel((1, 0), (0, 0, 255))   # blue  -> 0x001F
    assert to_rgb565(img) == bytes([0xF8, 0x00, 0x00, 0x1F])


def test_start_sends_commands_with_dc_low_and_wakes_the_screen():
    _, spi = make()
    commands = [data[0] for level, data in spi.sent if level == 0]
    assert 0x11 in commands and 0x29 in commands     # wake up, display on
    assert commands[-1] == 0x36                      # then which way up
    assert spi.sent[-1] == (1, bytes([0x28]))         # landscape (90)


def test_show_sends_a_whole_landscape_picture():
    screen, spi = make()
    spi.sent.clear()
    screen.show(Image.new("RGB", (160, 120), "#ffffff"))   # wrong size: gets resized
    assert (0, bytes([0x2A])) in spi.sent and (1, bytes([0, 0, 0x01, 0x3F])) in spi.sent   # columns 0..319
    assert (1, bytes([0, 0, 0x00, 0xEF])) in spi.sent                                      # rows 0..239
    level, pixels = spi.sent[-1]
    assert level == 1 and len(pixels) == 320 * 240 * 2 and pixels[:2] == b"\xff\xff"


def test_portrait_rotation_swaps_width_and_height():
    screen, _ = make(rotation=0)
    assert (screen.width, screen.height) == (240, 320)


def test_only_the_changed_part_is_sent():
    screen, spi = make()
    picture = Image.new("RGB", (320, 240), "#000000")
    screen.show(picture)
    spi.sent.clear()
    screen.show(picture.copy())
    assert spi.sent == []                                   # nothing changed: nothing sent
    mouth = picture.copy()
    for x in range(140, 180):
        for y in range(200, 210):
            mouth.putpixel((x, y), (255, 255, 255))
    screen.show(mouth)
    assert (1, bytes([0, 140, 0, 179])) in spi.sent        # columns 140..179
    assert (1, bytes([0, 200, 0, 209])) in spi.sent        # rows 200..209
    assert len(spi.sent[-1][1]) == 40 * 10 * 2              # just that strip


def test_power_off_blacks_the_screen_and_switches_the_backlight():
    spi, dc, reset, light = PretendSPI(), PretendPin(), PretendPin(), PretendPin()
    spi.dc = dc
    screen = Screen(spi=spi, dc=dc, reset=reset, rotation=90, backlight=light)
    screen.show(Image.new("RGB", (320, 240), "#ffffff"))
    light.on()
    screen.power(False)
    assert light.level == 0 and spi.sent[-1][1][:2] == b"\x00\x00"    # black picture, light off
    screen.power(True)
    assert light.level == 1 and screen.last is None                   # next picture redraws everything
