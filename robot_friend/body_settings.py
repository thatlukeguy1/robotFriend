"""
LESSON: Settings for the body, kept by the brain
================================================
Riley's body (the Pi) does the speaking and listening, but you change things in
the Studio, which the BRAIN (the mini PC) serves. So the brain keeps the body's
settings, and the body asks for them every 30 seconds and applies any change
straight away: no SSH, no restart.

Every setting has limits, checked HERE (not just in the web page), so a typo or
a stray request can't set the volume to a million or make Riley wait forever.
"""

import json
import math
import threading
from pathlib import Path

# name: (label, lowest, highest, step, default)
NUMBERS = {
    "volume": ("Speaker volume (%)", 0, 100, 5, 100),
    "sleep_after_minutes": ("Minutes with nobody talking before she dozes off", 1, 120, 1, 10),
    "screen_off_minutes": ("Minutes with nobody talking before the screen turns off (0 = never)", 0, 240, 1, 0),
    "wake_threshold": ("How sure she must be she heard her name (lower = wakes more easily)", 0.2, 0.9, 0.05, 0.5),
    "wake_frames": ("How many checks in a row must hear her name (higher = fewer false wake-ups)", 1, 4, 1, 1),
    "interrupt_threshold": ("How sure she must be she heard her name WHILE SHE'S TALKING (lower = easier to "
                            "interrupt; too low and her own voice can stop her)", 0.4, 0.95, 0.05, 0.9),
    "listen_seconds": ("Seconds she waits for you to start talking after \"Yes?\"", 2, 10, 0.5, 4),
    "follow_up_seconds": ("Seconds she listens for your answer after asking a question (0 = don't)", 0, 10, 0.5, 5),
    "touch_min_ms": ("Touch screen: ignore touches shorter than this, in milliseconds (higher = fewer accidental taps)",
                     20, 500, 10, 40),
    "touch_hold_seconds": ("Touch screen: seconds to hold it to turn her off", 2, 10, 1, 5),
    "motion_sensitivity": ("Camera: how small a movement wakes her screen (higher = notices smaller movements)",
                           1, 10, 1, 5),
}
# name: (label, {value: what the Studio shows}, default). Pick-one-of settings.
CHOICES = {
    "christmas_hat": ("Christmas hat 🎅 (on her screen and the chat page)",
                      {"auto": "Automatic: 25 November to 6 January", "on": "On", "off": "Off"}, "auto"),
    "camera_wakes": ("Camera: wake up when she sees someone (checked on the Pi; no pictures leave it)",
                     {"on": "On", "off": "Off"}, "on"),
}
OLD_VALUES = {True: "on", False: "off"}   # it used to be a tick box: saved settings from then still work
REPLIES = ("replies", "What she says when she hears her name (one per line; empty = a soft chime)",
           ["Yes?", "Mm-hm?", "I'm listening.", "What's up?", "Hi!"])
MAX_REPLIES, MAX_REPLY_LENGTH = 10, 40

DEFAULTS = ({name: spec[4] for name, spec in NUMBERS.items()} | {name: spec[2] for name, spec in CHOICES.items()}
            | {REPLIES[0]: list(REPLIES[2])})


class SettingsError(ValueError):
    """A setting is wrong. The message says which and why."""


def describe():
    """Everything the Studio needs to draw the form: labels, limits and defaults."""
    numbers = [{"key": k, "label": label, "min": low, "max": high, "step": step, "default": default}
               for k, (label, low, high, step, default) in NUMBERS.items()]
    choices = [{"key": k, "label": label, "options": [{"value": v, "label": text} for v, text in options.items()],
                "default": default} for k, (label, options, default) in CHOICES.items()]
    return {"numbers": numbers, "choices": choices, "replies": {"key": REPLIES[0], "label": REPLIES[1], "default": REPLIES[2],
                                            "max": MAX_REPLIES, "maxLength": MAX_REPLY_LENGTH}}


def validate(data):
    if not isinstance(data, dict):
        raise SettingsError("Settings must be a JSON object.")
    tidy = {}
    for k, (label, low, high, _step, default) in NUMBERS.items():
        value = data.get(k, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise SettingsError(f"{label} must be a number.")
        if not low <= value <= high:
            raise SettingsError(f"{label} must be between {low} and {high}.")
        tidy[k] = value
    for k, (label, options, default) in CHOICES.items():
        value = data.get(k, default)
        value = OLD_VALUES.get(value, value) if isinstance(value, bool) else value
        if value not in options:
            raise SettingsError(f"{label} must be one of: {', '.join(options)}.")
        tidy[k] = value
    replies = data.get(REPLIES[0], REPLIES[2])
    if not isinstance(replies, list) or not all(isinstance(r, str) for r in replies):
        raise SettingsError("The replies must be a list of short phrases.")
    replies = [r.strip() for r in replies if r.strip()]
    if len(replies) > MAX_REPLIES:
        raise SettingsError(f"Up to {MAX_REPLIES} replies, please.")
    if any(len(r) > MAX_REPLY_LENGTH for r in replies):
        raise SettingsError(f"Keep each reply under {MAX_REPLY_LENGTH} characters: it's what she says before listening.")
    tidy[REPLIES[0]] = replies
    return tidy


class BodySettingsStore:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def is_custom(self):
        return self.path.exists()

    def current(self):
        if self.path.exists():
            try:
                return validate({**DEFAULTS, **json.loads(self.path.read_text())})
            except (ValueError, SettingsError):
                pass  # a damaged file: fall back to the defaults rather than break the body
        return dict(DEFAULTS)

    def save(self, data):
        tidy = validate(data)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(tidy, indent=2, ensure_ascii=False) + "\n")
            temp.replace(self.path)
        return tidy

    def reset(self):
        with self._lock:
            if self.path.exists():
                self.path.unlink()


def christmas_time(day):
    """LESSON: dates that wrap round the new year. The season starts on 25 November and ends
    on 6 January (Twelfth Night, when the decorations traditionally come down). It isn't one
    range from start to end, because January comes BEFORE November in the year: it's
    "on or after 25 Nov" OR "on or before 6 Jan". The Pi (pi/bolt_body/animate.py) and the
    browser (web/face.js) use the same rule."""
    return (day.month, day.day) >= (11, 25) or (day.month, day.day) <= (1, 6)


def hat_wanted(mode, day):
    return mode == "on" or (mode == "auto" and christmas_time(day))
