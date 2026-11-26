"""
LESSON: Bringing the face to life
=================================
A still picture isn't a face. This file runs in the BACKGROUND (a "thread":
a second job the program does at the same time as listening) and redraws
Bolt's face about 8 times a second, doing exactly what the browser's face.js
does:

  * EASING: when the mood changes (say idle -> listening), every setting moves
    a fraction of the way to its new value each frame, so eyes widen smoothly
    instead of jumping.
  * GLANCING: every couple of seconds the eyes pick a new spot to look at.
  * BLINKING: a quick close-and-open, at random-ish times.
  * BREATHING: a slow, gentle bob up and down.
  * TALKING: while Bolt speaks, the mouth follows how loud the voice is.
  * NAPPING: after a while with nobody TALKING to her, she dozes off, even if the camera
    can see you sitting there (being seen keeps the SCREEN on, not her eyes open).

The main program only says WHAT Bolt is doing (face.set_state("thinking"));
this file decides how that LOOKS.
"""

import array
import io
import math
import os
import random
import threading
import time
import traceback
import wave
from datetime import date

from .face import draw_face, load_config, params_for

KEYS = ["open", "lowerLid", "tilt", "pupil", "lookX", "lookY", "wander", "blinkEvery", "bounce",
        "browShow", "browRaise", "browArch", "browTilt", "mouthSmile", "mouthOpen", "mouthWidth", "zzz", "hand", "roll"]
LEVEL_STEP = 0.05   # the voice's loudness is measured every 50 ms


def hat_wanted(mode, day):
    """The same rule as robot_friend/body_settings.py: 'auto' = 25 November to 6 January.
    (True/False come from before it was a choice.)"""
    if mode is True or mode == "on":
        return True
    return mode == "auto" and ((day.month, day.day) >= (11, 25) or (day.month, day.day) <= (1, 6))


PROP_SECONDS = 15                        # how long a prop stays up (she usually finishes talking first)
ROLL_SECONDS = 1.1                       # an eye roll: up, across the top, and back
GROGGY_SECONDS = 3.0                     # how long she looks half-awake after a doze
GROGGY_BLINKS = (0.8, 1.9)               # two slow, heavy blinks, this long after waking (seconds)
GROGGY_BLINK = 0.45                      # each one takes this long (a normal blink: 0.16)


def eye_roll(since, size=1.0):
    """LESSON: an eye roll is a path, not a pose. Over ROLL_SECONDS her pupils go up-left, sweep
    across the top, and come back down: lookX follows a half-circle (cos), lookY rises and
    falls (sin). Returns how far to move the pupils: (x, y), with y negative = up."""
    p = since / ROLL_SECONDS
    if not 0 <= p < 1:
        return 0.0, 0.0
    rise = math.sin(math.pi * p)
    return -0.8 * math.cos(math.pi * p) * math.sqrt(rise) * size, -0.95 * rise * size


def groggy_blink(since):
    """How shut a groggy blink has her eyes, `since` seconds after waking (0 = open, 1 = shut)."""
    shut = 0.0
    for at in GROGGY_BLINKS:
        k = (since - at) / GROGGY_BLINK
        if 0 <= k < 1:
            shut = max(shut, k * 2 if k < 0.5 else 2 - k * 2)
    return shut
EMOJI_FONT = os.environ.get("EMOJI_FONT", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf")
_emoji_cache = {}


def _emoji_picture(emoji, size):
    """An emoji as a picture, `size` pixels tall. LESSON: colour emoji fonts are really a
    set of small PICTURES, all drawn at one size (109 pixels for Noto). So we draw it at
    109 and shrink it, then keep it, so each emoji is only drawn once."""
    from PIL import Image, ImageDraw, ImageFont
    key = (emoji, size)
    if isinstance(_emoji_cache.get(key), Exception):
        raise _emoji_cache[key]                            # failed before: don't try (or log) 15 times a second
    if key not in _emoji_cache:
        try:
            font = ImageFont.truetype(EMOJI_FONT, 109)
            big = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
            ImageDraw.Draw(big).text((4, 4), emoji, font=font, embedded_color=True)
            box = big.getbbox()
            if not box:
                raise ValueError(f"the emoji font has no {emoji!r}")
            big = big.crop(box)
            scale = size / max(big.size)
            if len(_emoji_cache) > 60:
                _emoji_cache.clear()
            _emoji_cache[key] = big.resize((max(1, round(big.width * scale)), max(1, round(big.height * scale))),
                                           Image.LANCZOS)
        except Exception as e:
            _emoji_cache[key] = e
            print(f"   (prop: can't draw {emoji!r}: {e}. Is the emoji font installed? "
                  "sudo apt install -y fonts-noto-color-emoji)", flush=True)
            raise
    return _emoji_cache[key]


def draw_prop(img, emoji, text, ink):
    """Riley "holding up" a prop in the lower right: the emoji, and big text under it."""
    from PIL import ImageDraw, ImageFont
    W, H = img.size
    cx, cy, size = W * 0.885, H * 0.74, round(H * 0.25)     # tucked into the corner, clear of her eye
    try:
        pic = _emoji_picture(emoji, size)
        img.paste(pic, (round(cx - pic.width / 2), round(cy - pic.height / 2)), pic)
    except Exception:  # no emoji font (or an emoji it doesn't have): the text still shows (logged once)
        pass
    if text:
        try:
            font = ImageFont.load_default(size=round(H * 0.095))
        except TypeError:                                   # an older Pillow
            font = ImageFont.load_default()
        ImageDraw.Draw(img).text((cx, cy + size * 0.5 + H * 0.07), text, fill=ink, font=font, anchor="mm")


def timer_line(img, left, ink, urgent=False, time=0.0, width=4):
    """LESSON: a progress bar that goes round the EDGE of the screen. It starts full (all
    the way round) and shrinks back towards the top middle as the timer runs down, so you
    can tell from across the room roughly how much is left. In the last 10 seconds it
    pulses."""
    from PIL import ImageDraw
    W, H = img.size
    left = max(0.0, min(1.0, left))
    if left <= 0:
        return
    h = width / 2
    # The edge as one long path, clockwise from the top middle
    path = [(W / 2, h), (W - h, h), (W - h, H - h), (h, H - h), (h, h), (W / 2, h)]
    lengths = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(path, path[1:])]
    todo, pts = left * sum(lengths), [path[0]]
    for (a, b), length in zip(zip(path, path[1:]), lengths):
        if todo <= 0:
            break
        k = min(1.0, todo / length)
        pts.append((a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k))
        todo -= length
    colour = ink
    if urgent and int(time * 2) % 2:                       # the last 10 seconds: blink twice a second
        colour = "#ffffff"
    ImageDraw.Draw(img).line(pts, fill=colour, width=width, joint="curve")


def power_ring(img, progress, smooth=3):
    """While you hold the screen to turn her off: the face dims, and a ring with a power
    symbol fills up clockwise. Full = turning off. Let go before then to cancel.
    (Drawn 3x bigger on a see-through layer, then shrunk, for smooth edges.)"""
    from PIL import Image, ImageDraw, ImageFont
    W, H = img.size
    img = Image.blend(img, Image.new("RGB", img.size, "black"), 0.82)
    layer = Image.new("RGBA", (W * smooth, H * smooth), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    X = lambda v: v * smooth
    cx, cy, r, w = X(W / 2), X(H * 0.42), X(H * 0.26), X(max(4, round(H * 0.045)))
    box = (cx - r, cy - r, cx + r, cy + r)
    d.ellipse(box, outline="#3a3f4a", width=w)                                  # the empty ring
    if progress > 0:
        d.arc(box, -90, -90 + 360 * min(1.0, progress), fill="#ff5a68", width=w)   # filling up
    s, line = r * 0.45, round(w * 0.8)                                          # the power symbol
    d.arc((cx - s, cy - s, cx + s, cy + s), -60, 240, fill="#ffffff", width=line)
    d.line((cx, cy - s * 1.25, cx, cy - s * 0.1), fill="#ffffff", width=line)
    for x, y in ((cx, cy - s * 1.25), (cx, cy - s * 0.1)):                     # round ends
        d.ellipse((x - line / 2, y - line / 2, x + line / 2, y + line / 2), fill="#ffffff")
    text = "Goodnight!" if progress >= 1 else "Keep holding to turn off"
    try:
        font = ImageFont.load_default(size=X(max(12, round(H * 0.075))))
    except TypeError:                                                           # an older Pillow
        font = ImageFont.load_default()
    d.text((cx, cy + r + X(H * 0.12)), text, fill="#ffffff", font=font, anchor="mm")
    layer = layer.resize((W, H), Image.LANCZOS)
    img.paste(layer, (0, 0), layer)
    return img


def voice_levels(wav_bytes, step=LEVEL_STEP):
    """How loud a recording is, every `step` seconds, from 0 (silent) to 1 (very loud).
    The same sum the chat page uses: the RMS ("average size") of the samples, times 6."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        rate, channels = w.getframerate(), w.getnchannels()
        samples = array.array("h", w.readframes(w.getnframes()))
    chunk = max(1, int(rate * step)) * channels
    levels = []
    for i in range(0, len(samples), chunk):
        part = samples[i:i + chunk]
        rms = math.sqrt(sum(s * s for s in part) / len(part)) / 32768
        levels.append(min(1.0, rms * 6))
    return levels


class FaceAnimator:
    def __init__(self, screen, config=None, fps=15, sleep_after=600, clock=time.monotonic, rng=None, screen_off_after=0):
        self.screen, self.fps, self.sleep_after = screen, fps, sleep_after
        self.screen_off_after = screen_off_after   # seconds with nobody about before the screen goes off (0 = never)
        self.screen_on = True
        self.clock, self.rng = clock, rng or random.Random()
        self.config = config or load_config()
        self.state = "idle"
        self.awake_since = self.clock()  # when someone last talked to her (or tapped): for dozing off
        self.seen_at = self.awake_since  # when the camera last saw someone: for the screen
        self.talk = ([], 0.0)            # (voice levels, when they started)
        self.mouth = 0.0                 # the loudness the mouth is SHOWING (eased, see frame())
        self.power_hold = 0.0            # 0..1 while the screen is held down to turn off (see touch.py)
        self.picture = None              # (picture, until when) a camera picture from Home Assistant
        self.prop = None                 # (emoji, text, until when) something she's "holding up"
        self.timers = []                 # [(ends at, length in seconds)] from the brain, soonest first
        self.hat, self.hat_mode = 0.0, "off"   # the Christmas hat: how far on it is (eased), and on/off/auto
        self.today = date.today
        self.now = {s: dict(params_for(self.config, "idle", s)) for s in ("left", "right")}
        t = self.clock()
        self.glance = {"x": 0.0, "y": 0.0, "aimX": 0.0, "aimY": 0.0, "next": t + 2}
        self.blinks = {s: {"start": -1.0, "next": t + 2} for s in ("left", "right")}
        self.dozing = False                  # was she dozing last frame? (to notice her waking up)
        self.roll = None                     # (started, size) of an eye roll in progress
        self.woke_at = None                  # when she last woke from a doze (for looking groggy)
        self.last = t
        self._stop = threading.Event()
        self._thread = None
        self._last_error = None

    # ---------------------------------------------- what the rest of Bolt calls

    @property
    def hat_on(self):
        """Should the Christmas hat be on right now? "auto" means 25 November to 6 January."""
        return hat_wanted(self.hat_mode, self.today())

    def set_state(self, name):
        """idle, listening, thinking, speaking, happy, confused... (any expression in the design)."""
        if name in self.config["expressions"]:
            if name != self.state:               # a face with an eye roll rolls as it starts
                size = params_for(self.config, name, "left").get("roll", 0) or 0
                self.roll = (self.clock(), size) if size > 0.05 else None
            self.state = name
            if name != "sleeping":
                self.awake_since = self.clock()
            if name == "listening":
                self.picture = None              # "Hey Riley" (or a tap): back to her face
                self.prop = None

    def show_prop(self, emoji, text="", seconds=PROP_SECONDS):
        """Hold up a prop (an emoji, plus a few characters like "8°") while she talks."""
        self.prop = (emoji, text, self.clock() + seconds)

    def set_timers(self, timers):
        """The timers running now, from the brain: [{"seconds_left", "seconds"}]. Kept as the
        moment each ends on OUR clock, so the line shrinks smoothly between updates."""
        now = self.clock()
        self.timers = sorted((now + t["seconds_left"], t["seconds"]) for t in timers if t.get("seconds"))

    def show_picture(self, data, seconds=20):
        """Show a picture (JPEG/PNG bytes) instead of the face for a while, e.g. a doorbell
        camera's snapshot. LESSON: "letterboxing". The camera's picture is a different shape
        from the screen, so it's shrunk to fit inside, with black bars at the sides, rather
        than stretched (squashed faces) or cropped (missing the person at the edge)."""
        from PIL import Image, ImageOps
        picture = Image.open(io.BytesIO(data)).convert("RGB")
        size = (self.screen.width, self.screen.height)
        fitted = ImageOps.contain(picture, size)
        canvas = Image.new("RGB", size, "black")
        canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
        self.picture = (canvas, self.clock() + seconds)   # the screen stays on while it shows (see step)

    def someone_here(self):
        """Someone's dealing with her (a tap, her name, a conversation, an announcement):
        wake the face, and the screen if it was off."""
        self.awake_since = self.seen_at = self.clock()

    def someone_seen(self):
        """The camera saw someone: keep the SCREEN on, but don't stop her dozing off. Only
        talking to her (or a tap) wakes her eyes up."""
        self.seen_at = self.clock()

    def say(self, wav_bytes):
        """Bolt is about to play this audio: move the mouth along with it (empty = stop talking)."""
        self.talk = (voice_levels(wav_bytes) if wav_bytes else [], self.clock())

    def level(self, t):
        levels, start = self.talk
        i = int((t - start) / LEVEL_STEP)
        return levels[i] if 0 <= i < len(levels) else 0.0

    # ---------------------------------------------- one frame (the same maths as face.js)

    def blink_amount(self, state, every, t):
        if every > 0 and state["start"] < 0 and t > state["next"]:
            state["start"] = t
        if state["start"] < 0:
            return 0.0
        k = (t - state["start"]) / 0.16
        if k >= 1:
            state["start"] = -1.0
            state["next"] = t + every * (0.6 + self.rng.random() * 0.8)
            return 0.0
        return k * 2 if k < 0.5 else 2 - k * 2

    def frame(self, t=None):
        t = self.clock() if t is None else t
        dt = min(0.25, max(0.0, t - self.last))
        self.last = t
        mood = self.state
        if mood == "idle" and t - self.awake_since > self.sleep_after and "sleeping" in self.config["expressions"]:
            mood = "sleeping"                                    # nobody's talked to Bolt for a while
        target = {s: params_for(self.config, mood, s) for s in ("left", "right")}

        # LESSON: waking up groggy. Straight after a doze, for a few seconds, her lids are
        # heavy and lift slowly, she doesn't look about, and she blinks slowly twice. "groggy"
        # goes from 1 (just woke) down to 0 (properly awake), and everything scales with it.
        if self.dozing and mood != "sleeping":
            self.woke_at = t
        self.dozing = mood == "sleeping"
        groggy = max(0.0, 1 - (t - self.woke_at) / GROGGY_SECONDS) if self.woke_at is not None else 0.0
        if groggy > 0:
            for side in ("left", "right"):
                goal = target[side] = dict(target[side])
                goal["open"] = goal["open"] * (1 - 0.5 * groggy)
                goal["lowerLid"] = max(goal["lowerLid"], 0.25 * groggy)
                goal["lookY"] = goal["lookY"] + 0.15 * groggy
                goal["wander"] = goal["wander"] * (1 - groggy)
        ease = 1 - math.exp(-dt * 9 * (1 - 0.75 * groggy))      # slow to change while groggy

        # Glancing around, then gliding there
        wander = (target["left"]["wander"] + target["right"]["wander"]) / 2
        g = self.glance
        if t > g["next"]:
            to_middle = self.rng.random() < 0.4
            g["aimX"] = 0.0 if to_middle else (self.rng.random() * 2 - 1) * wander
            g["aimY"] = 0.0 if to_middle else (self.rng.random() * 2 - 1) * wander * 0.15
            g["next"] = t + 1.5 + self.rng.random() * 2.5
        glide = 1 - math.exp(-dt * 14)
        g["x"] += (g["aimX"] - g["x"]) * glide
        g["y"] += (g["aimY"] - g["y"]) * glide
        drift_x = math.sin(t / 1.7) * 0.03 * wander
        drift_y = math.sin(t / 2.3 + 1) * 0.01 * wander

        # Blinking: same timer for both eyes unless they blink at different speeds
        blink = {"left": self.blink_amount(self.blinks["left"], target["left"]["blinkEvery"], t)}
        blink["right"] = (blink["left"] if target["right"]["blinkEvery"] == target["left"]["blinkEvery"]
                          else self.blink_amount(self.blinks["right"], target["right"]["blinkEvery"], t))
        if groggy > 0:
            heavy = groggy_blink(t - self.woke_at)
            blink = {side: max(amount, heavy) for side, amount in blink.items()}

        # The mouth opens fast and closes a little slower, like a real one, instead of
        # jumping to each new loudness reading (they come every 50 ms).
        heard = self.level(t)
        speed = 30 if heard > self.mouth else 14
        self.mouth += (heard - self.mouth) * (1 - math.exp(-dt * speed))
        level = self.mouth

        # Bobbing: with the voice while talking, slow "breathing" otherwise
        breathe = 0.5 + 0.5 * math.sin(t / 2.4 * math.pi * 2)
        lift = level * 0.05 + (1 - level) * 0.035 * breathe

        shown = {}
        for side in ("left", "right"):
            now, goal = self.now[side], target[side]
            for k in KEYS:
                now[k] = now.get(k, 0.0) + (goal.get(k, 0.0) - now.get(k, 0.0)) * ease
            shown[side] = {**now, "lookX": now["lookX"] + g["x"] + drift_x, "lookY": now["lookY"] + g["y"] + drift_y}
        if self.roll:
            rx, ry = eye_roll(t - self.roll[0], self.roll[1])
            for side in ("left", "right"):          # her lids lift a little, so the pupils show going round
                shown[side]["lookX"] += rx
                shown[side]["lookY"] += ry
                shown[side]["open"] = min(1.0, shown[side]["open"] - 0.35 * ry)
        bob = (self.now["left"]["bounce"] + self.now["right"]["bounce"]) / 2 * lift
        self.hat += ((1.0 if self.hat_on else 0.0) - self.hat) * (1 - math.exp(-dt * 4))   # slides on, or off
        img = draw_face(shown, self.config, blink, bob, level, size=(self.screen.width, self.screen.height), smooth=2,
                        time=t, hat=self.hat)
        ink = self.config["colors"].get("mouth", "#7fdcff")
        while self.timers and self.timers[0][0] <= t - 1:
            self.timers.pop(0)                   # finished (the brain announces it)
        if self.timers:
            ends, length = self.timers[0]
            timer_line(img, (ends - t) / length, ink, urgent=ends - t <= 10, time=t)
        if self.prop and t < self.prop[2]:
            draw_prop(img, self.prop[0], self.prop[1], ink)
        elif self.prop:
            self.prop = None
        return power_ring(img, self.power_hold) if self.power_hold > 0 else img

    # ---------------------------------------------- running in the background

    def start(self):
        self._thread = threading.Thread(target=self._run, name="face", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        gap = 1 / self.fps
        frames, counting_since = 0, time.monotonic()
        while not self._stop.is_set():
            began = time.monotonic()
            frames += 1
            if began - counting_since >= 30:          # once, after 30 s: how smooth is it?
                print(f"   (face: {frames / (began - counting_since):.1f} pictures a second)", flush=True)
                counting_since, frames = float("inf"), 0
            try:
                if self.step() == "off":
                    self._stop.wait(0.2)              # screen's off: just check now and then
                    continue
            except Exception as e:  # a glitch on the screen must never stop Bolt listening
                print(f"   ! face: {e}", flush=True)
                if str(e) != self._last_error:          # the first time: WHERE it went wrong, for fixing
                    self._last_error = str(e)
                    traceback.print_exc()
                    print(f"   (face state: {self.state}, mouth {self.mouth!r}, talk {type(self.talk[0]).__name__})", flush=True)
                time.sleep(1)
            self._stop.wait(max(0.0, gap - (time.monotonic() - began)))

    def step(self):
        """One go of the loop: switch the screen off or on if it's time, otherwise draw a frame."""
        nobody_for = self.clock() - max(self.awake_since, self.seen_at)
        showing_picture = self.picture is not None and self.clock() < self.picture[1]
        should_be_off = (self.screen_off_after > 0 and self.state == "idle" and nobody_for > self.screen_off_after
                         and self.power_hold == 0 and not showing_picture)
        if should_be_off != (not self.screen_on):
            self.screen_on = not should_be_off
            if hasattr(self.screen, "power"):
                self.screen.power(self.screen_on)
            print(f"   (screen {'on' if self.screen_on else 'off'})", flush=True)
        if not self.screen_on:
            return "off"
        if self.picture and self.clock() < self.picture[1]:
            self.screen.show(self.picture[0])    # unchanged pictures cost nothing to "re-send"
            return "picture"
        self.picture = None
        self.screen.show(self.frame())
        return "drawn"


class NoFace:
    """Stands in when there's no screen, so the rest of Bolt doesn't have to check."""
    sleep_after = 600
    screen_off_after = 0
    hat_mode = "off"
    power_hold = 0.0
    def show_prop(self, emoji, text="", seconds=12): pass
    def set_timers(self, timers): pass
    def set_state(self, name): pass
    def someone_here(self): pass
    def someone_seen(self): pass
    def show_picture(self, data, seconds=20): pass
    def say(self, wav_bytes): pass
    def start(self): return self
    def stop(self): pass


def make_face(brain_url=None, ca=None):
    """The real animated face if a screen is connected (and SCREEN isn't 'off'), otherwise NoFace."""
    if os.environ.get("SCREEN", "on").lower() in ("off", "0", "no"):
        return NoFace()
    try:
        from .screen import Screen
        screen = Screen()
    except Exception as e:
        print(f"   (no screen: {e}. Set SCREEN=off in bolt.env to hide this.)", flush=True)
        return NoFace()
    return FaceAnimator(screen, load_config(brain_url=brain_url, ca=ca),
                        sleep_after=float(os.environ.get("SLEEP_AFTER_MINUTES", "10")) * 60,
                        screen_off_after=float(os.environ.get("SCREEN_OFF_MINUTES", "0")) * 60).start()
