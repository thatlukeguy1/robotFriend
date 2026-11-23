"""
LESSON: The touch screen
========================
The 2.8" screen's touch layer is a separate little chip, the XPT2046. It has a
wire called T_IRQ ("interrupt request") that goes LOW whenever a finger presses
the screen, and back HIGH when it lets go. That's all Riley needs to know for a
tap or a long press, so we just watch that one wire; no maths about WHERE you
touched (that would need calibrating, and can come later for on-screen buttons).

    a quick TAP (under 1 second)  -> wake up and listen (or stop talking)
    HOLD for 5 seconds            -> turn the Pi off safely

Holding shows a ring on her face that fills up as you hold. Let go before it's
full and nothing happens, so a brush of the hand or a cat can't switch her off.

The other four touch wires (T_CLK, T_CS, T_DIN, T_DO) share the screen's SPI
connection, on the Pi's second "chip select" (CE1, pin 26). We send the chip one
command at start-up so it's in "tell me when I'm touched" mode, and with its CS
wire connected it ignores everything the screen is sent.

Test it on the Pi (stop Riley first: sudo systemctl stop bolt-body):

    cd ~/robotFriend/pi && .venv/bin/python -m bolt_body.touch test
"""

import os
import sys
import threading
import time

TAP_MAX = 1.0        # a press shorter than this is a tap
HOLD_OFF = 5.0       # hold this long to turn off
DEBOUNCE = 0.04      # shorter than this is a glitch, not a finger
LET_GO = 0.15        # no contact for this long = the finger has really gone (see below)
POLL = 0.02          # check the wire 50 times a second


class Gestures:
    """Turns "is the screen pressed?" (asked again and again) into taps and holds.
    Pure logic, no hardware, so it can be tested on any computer.

    update() returns a list of events:
        ("down",)            a finger just touched (wake the screen)
        ("hold", progress)   being held: 0 = just started holding, 1 = time to turn off
        ("tap",)             let go quickly
        ("cancel",)          let go before the hold finished
        ("off",)             held for HOLD_OFF seconds
    """

    def __init__(self, debounce=DEBOUNCE, hold_off=HOLD_OFF):
        self.debounce = debounce   # shortest touch that counts (the Studio's Body tab can change it)
        self.hold_off = hold_off   # how long to hold to turn off (the Studio too)
        self.since = None        # when the finger went down (None = not touching)
        self.gone_at = None      # when contact was lost (it may come back: see LET_GO)
        self.fired = False       # "off" already sent for this press
        self.announced = False   # "down" already sent for this press

    def update(self, pressed, now):
        """LESSON: a pressing finger isn't a perfect switch. This kind of touch screen works by
        squeezing two thin layers together, and while you hold it the contact flickers off for
        a moment now and then. So "let go" only counts after LET_GO seconds with no contact;
        a shorter gap is still the same press."""
        events = []
        if pressed:
            self.gone_at = None
            if self.since is None:
                self.since, self.fired, self.announced = now, False, False
            held = now - self.since
            if held >= self.debounce and not self.announced:
                self.announced = True
                events.append(("down",))
            if held >= TAP_MAX and not self.fired:
                events.append(("hold", min(1.0, (held - TAP_MAX) / max(0.1, self.hold_off - TAP_MAX))))
                if held >= self.hold_off:
                    self.fired = True
                    events.append(("off",))
        elif self.since is not None:
            if self.gone_at is None:
                self.gone_at = now
            if now - self.gone_at >= LET_GO or not self.announced:
                held = self.gone_at - self.since
                self.since = self.gone_at = None
                if self.announced and held < TAP_MAX:
                    events.append(("tap",))
                elif self.announced and not self.fired:
                    events.append(("cancel",))
        return events


class TouchPanel:
    """The real touch chip: watches T_IRQ and passes each gesture to `handle(event)`."""

    def __init__(self, irq_pin, handle, spi_device=1):
        from gpiozero import Button   # only on a real Pi
        self.irq = Button(int(irq_pin), pull_up=True, bounce_time=None)   # pressed = wire pulled LOW
        self.handle = handle
        self.gestures = Gestures()
        try:
            import spidev
            spi = spidev.SpiDev()
            spi.open(0, spi_device)          # CE1 = pin 26
            spi.max_speed_hz = 500_000       # the touch chip is slow: 2 MHz at most
            spi.xfer2([0x90, 0, 0])          # one reading, ending in "power down, interrupt ON" mode
            spi.close()
        except Exception as e:  # T_IRQ often works anyway (it's the chip's start-up mode)
            print(f"   (touch: couldn't set up the chip over SPI: {e})", flush=True)

    def start(self):
        threading.Thread(target=self._run, name="touch", daemon=True).start()
        return self

    def _run(self):
        print(f"   (touch: watching GPIO {self.irq.pin})", flush=True)
        while True:
            try:
                for event in self.gestures.update(self.irq.is_pressed, time.monotonic()):
                    self.handle(event)
            except Exception as e:  # a problem with one touch must never stop the watching
                import traceback
                traceback.print_exc()
                print(f"   ! touch: {e}", flush=True)
            time.sleep(POLL)


def make_touch(handle):
    """The touch panel if TOUCH_IRQ_PIN is set (bolt.env), otherwise None."""
    pin = os.environ.get("TOUCH_IRQ_PIN", "").strip()
    if not pin:
        return None
    try:
        return TouchPanel(pin, handle).start()
    except Exception as e:
        print(f"   (no touch screen: {e}. Leave TOUCH_IRQ_PIN empty in bolt.env to hide this.)", flush=True)
        return None


def test():
    pin = os.environ.get("TOUCH_IRQ_PIN") or "22"
    print(f"Watching T_IRQ on GPIO {pin}. Tap the screen, then hold it. Ctrl+C to stop.")
    last = [-1]
    def show(event):
        if event[0] == "hold":                       # 50 a second: just show every quarter
            quarter = int(event[1] * 4)
            if quarter == last[0]:
                return
            last[0] = quarter
            print(f"   holding: {quarter * 25}%")
        else:
            last[0] = -1
            print("  ", event[0])
    TouchPanel(pin, show).start()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        try:
            test()
        except KeyboardInterrupt:
            print("Bye!")
    else:
        print("Usage: python -m bolt_body.touch test")
