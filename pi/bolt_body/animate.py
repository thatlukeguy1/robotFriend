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
  * NAPPING: after a while with nobody talking to it, Bolt dozes off.

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
        "browShow", "browRaise", "browArch", "browTilt", "mouthSmile", "mouthOpen", "mouthWidth", "zzz", "hand"]
LEVEL_STEP = 0.05   # the voice's loudness is measured every 50 ms


def hat_wanted(mode, day):
    """The same rule as robot_friend/body_settings.py: 'auto' = 25 November to 6 January.
    (True/False come from before it was a choice.)"""
    if mode is True or mode == "on":
        return True
    return mode == "auto" and ((day.month, day.day) >= (11, 25) or (day.month, day.day) <= (1, 6))


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
        self.awake_since = self.clock()
        self.talk = ([], 0.0)            # (voice levels, when they started)
        self.mouth = 0.0                 # the loudness the mouth is SHOWING (eased, see frame())
        self.hat, self.hat_mode = 0.0, "off"   # the Christmas hat: how far on it is (eased), and on/off/auto
        self.today = date.today
        self.now = {s: dict(params_for(self.config, "idle", s)) for s in ("left", "right")}
        t = self.clock()
        self.glance = {"x": 0.0, "y": 0.0, "aimX": 0.0, "aimY": 0.0, "next": t + 2}
        self.blinks = {s: {"start": -1.0, "next": t + 2} for s in ("left", "right")}
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
            self.state = name
            if name != "sleeping":
                self.awake_since = self.clock()

    def someone_here(self):
        """Something noticed a person (the wake word, or one day the camera seeing movement):
        wake the face, and the screen if it was off."""
        self.awake_since = self.clock()

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
        ease = 1 - math.exp(-dt * 9)

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
        bob = (self.now["left"]["bounce"] + self.now["right"]["bounce"]) / 2 * lift
        self.hat += ((1.0 if self.hat_on else 0.0) - self.hat) * (1 - math.exp(-dt * 4))   # slides on, or off
        return draw_face(shown, self.config, blink, bob, level, size=(self.screen.width, self.screen.height), smooth=2,
                         time=t, hat=self.hat)

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
        nobody_for = self.clock() - self.awake_since
        should_be_off = self.screen_off_after > 0 and self.state == "idle" and nobody_for > self.screen_off_after
        if should_be_off != (not self.screen_on):
            self.screen_on = not should_be_off
            if hasattr(self.screen, "power"):
                self.screen.power(self.screen_on)
            print(f"   (screen {'on' if self.screen_on else 'off'})", flush=True)
        if not self.screen_on:
            return "off"
        self.screen.show(self.frame())
        return "drawn"


class NoFace:
    """Stands in when there's no screen, so the rest of Bolt doesn't have to check."""
    sleep_after = 600
    screen_off_after = 0
    hat_mode = "off"
    def set_state(self, name): pass
    def someone_here(self): pass
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
