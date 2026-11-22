"""
LESSON: Talking to a screen over SPI
====================================
The 2.8" screen has its own little chip, the ILI9341, with memory for every
pixel. The Pi doesn't "show" a picture: it sends the chip COMMANDS and DATA
down a fast serial link called SPI (Serial Peripheral Interface):

    SCK   the clock: one tick per bit                 (Pi pin 23)
    MOSI  the bits themselves, Pi -> screen ("SDI")    (Pi pin 19)
    CS    "chip select": "I'm talking to YOU now"      (Pi pin 24)
    DC    "data/command": low = command, high = data   (Pi pin 18)
    RESET a fresh start for the chip                   (Pi pin 22)

To draw a picture we say: "COLUMNS 0-319, ROWS 0-239, here come the pixels",
then send 320 x 240 pixels, each squeezed into 2 bytes (RGB565: 5 bits of red,
6 of green, 5 of blue, because our eyes are most sensitive to green).

That's 153,600 bytes per picture. At 12 million bits a second (SCREEN_MHZ, the
speed that looked cleanest through jumper wires) it takes about 0.1 s.

Test it on the Pi (Bolt's background service can stay running):

    cd ~/robotFriend/pi && .venv/bin/python -m bolt_body.screen test
"""

import os
import sys
import time

import numpy as np

WIDTH, HEIGHT = 320, 240

# The chip's start-up recipe (the widely used one from Adafruit's ILI9341 driver).
# Each entry: (command, data bytes, milliseconds to wait afterwards).
INIT = [
    (0xEF, [0x03, 0x80, 0x02], 0),
    (0xCF, [0x00, 0xC1, 0x30], 0),
    (0xED, [0x64, 0x03, 0x12, 0x81], 0),
    (0xE8, [0x85, 0x00, 0x78], 0),
    (0xCB, [0x39, 0x2C, 0x00, 0x34, 0x02], 0),
    (0xF7, [0x20], 0),
    (0xEA, [0x00, 0x00], 0),
    (0xC0, [0x23], 0),              # power control
    (0xC1, [0x10], 0),
    (0xC5, [0x3E, 0x28], 0),        # voltage for the liquid crystal
    (0xC7, [0x86], 0),
    (0x37, [0x00], 0),              # no scrolling
    (0x3A, [0x55], 0),              # 16 bits per pixel (RGB565)
    (0xB1, [0x00, 0x18], 0),        # refresh rate
    (0xB6, [0x08, 0x82, 0x27], 0),
    (0xF2, [0x00], 0),
    (0x26, [0x01], 0),              # gamma (how bright each shade looks)
    (0xE0, [0x0F, 0x31, 0x2B, 0x0C, 0x0E, 0x08, 0x4E, 0xF1, 0x37, 0x07, 0x10, 0x03, 0x0E, 0x09, 0x00], 0),
    (0xE1, [0x00, 0x0E, 0x14, 0x03, 0x11, 0x07, 0x31, 0xC1, 0x48, 0x08, 0x0F, 0x0C, 0x31, 0x36, 0x0F], 0),
    (0x11, [], 120),                # wake up
    (0x29, [], 20),                 # display on
]

# Which way up: the "MADCTL" setting for each rotation (all landscape or portrait).
# 90 and 270 are the two landscape ways round; if the face is upside down, swap them.
MADCTL = {0: 0x48, 90: 0x28, 180: 0x88, 270: 0xE8}


def to_rgb565(image):
    """A Pillow RGB picture (or a numpy array of one) -> the screen's 2-bytes-per-pixel format."""
    a = np.asarray(image.convert("RGB") if hasattr(image, "convert") else image, dtype=np.uint16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    packed = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return packed.astype(">u2").tobytes()


class Screen:
    """The ILI9341 over SPI. spi/dc/reset can be swapped for pretend ones in tests."""

    def __init__(self, spi=None, dc=None, reset=None, rotation=None, mhz=None):
        rotation = int(rotation if rotation is not None else os.environ.get("SCREEN_ROTATION", "90"))
        if rotation not in MADCTL:
            raise ValueError("SCREEN_ROTATION must be 0, 90, 180 or 270")
        self.rotation = rotation
        self.width, self.height = (WIDTH, HEIGHT) if rotation in (90, 270) else (HEIGHT, WIDTH)
        if spi is None:
            import spidev  # only on the real Pi (sudo apt install python3-spidev)
            spi = spidev.SpiDev()
            spi.open(0, 0)  # SPI bus 0, chip select CE0 (pin 24)
            spi.max_speed_hz = int(float(mhz or os.environ.get("SCREEN_MHZ", "12")) * 1_000_000)
            spi.mode = 0
        if dc is None or reset is None:
            from gpiozero import DigitalOutputDevice  # only on the real Pi
            dc = dc or DigitalOutputDevice(int(os.environ.get("SCREEN_DC", "24")))
            reset = reset or DigitalOutputDevice(int(os.environ.get("SCREEN_RESET", "25")))
        self.spi, self.dc, self.reset = spi, dc, reset
        self.last = None          # the picture already on the screen
        self.sent_pixels = 0      # for measuring
        self.start()

    def command(self, cmd, data=()):
        self.dc.off()                 # DC low: this byte is a command
        self.spi.writebytes([cmd])
        if data:
            self.dc.on()              # DC high: these bytes are data for it
            self.spi.writebytes2(bytes(data))

    def start(self):
        self.reset.on(); time.sleep(0.01)
        self.reset.off(); time.sleep(0.01)    # a short low pulse = "start again"
        self.reset.on(); time.sleep(0.12)
        for cmd, data, wait in INIT:
            self.command(cmd, data)
            if wait:
                time.sleep(wait / 1000)
        self.command(0x36, [MADCTL[self.rotation]])  # which way up

    def show(self, image):
        """Show a picture. LESSON: only the part that CHANGED since last time is sent.
        When Bolt talks, often just the mouth moves: a small strip instead of the whole
        screen, so pictures can go out many times faster."""
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height))
        now = np.asarray(image.convert("RGB"))
        x0, y0, x1, y1 = 0, 0, self.width - 1, self.height - 1
        if self.last is not None:
            changed = np.any(now != self.last, axis=2)          # True where a pixel is different
            rows, cols = np.flatnonzero(changed.any(axis=1)), np.flatnonzero(changed.any(axis=0))
            if rows.size == 0:
                return                                          # nothing changed: send nothing
            x0, x1, y0, y1 = int(cols[0]), int(cols[-1]), int(rows[0]), int(rows[-1])
        self.last = now
        self.command(0x2A, [x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])   # columns x0..x1
        self.command(0x2B, [y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])   # rows y0..y1
        self.command(0x2C)                                              # "here come the pixels"
        self.dc.on()
        self.spi.writebytes2(to_rgb565(now[y0:y1 + 1, x0:x1 + 1]))
        self.sent_pixels += (x1 - x0 + 1) * (y1 - y0 + 1)

    def off(self):
        self.command(0x28)  # display off (the backlight stays on: it's wired to 3.3V)


def test():
    """Colour bars, then every expression for two seconds each."""
    from PIL import Image, ImageDraw
    from .face import draw_face, load_config, params_for

    screen = Screen()
    print(f"Screen ready: {screen.width} x {screen.height}, rotation {screen.rotation}")
    for name, colour in (("RED", "#ff0000"), ("GREEN", "#00ff00"), ("BLUE", "#0000ff")):
        img = Image.new("RGB", (screen.width, screen.height), colour)
        ImageDraw.Draw(img).text((10, 10), f"{name}  (this text should be top left, the right way up)", fill="white")
        screen.show(img)
        print(f"Showing {name}. Is the whole screen {name.lower()}?")
        time.sleep(1.5)
    config = load_config()
    for name in config["expressions"]:
        p = {side: params_for(config, name, side) for side in ("left", "right")}
        start = time.time()
        screen.show(draw_face(p, config, level=0.6 if name == "speaking" else 0.0,
                              size=(screen.width, screen.height)))
        print(f"Showing {name} (took {time.time() - start:.2f} s to draw and send)")
        time.sleep(2)
    print("Done!")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        print("Usage: python -m bolt_body.screen test")
