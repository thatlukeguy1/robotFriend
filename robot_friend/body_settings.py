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
    "wake_threshold": ("How sure she must be she heard her name (lower = wakes more easily)", 0.2, 0.9, 0.05, 0.5),
    "listen_seconds": ("Seconds she waits for you to start talking after \"Yes?\"", 2, 10, 0.5, 4),
}
REPLIES = ("replies", "What she says when she hears her name (one per line; empty = a soft chime)",
           ["Yes?", "Mm-hm?", "I'm listening.", "What's up?", "Hi!"])
MAX_REPLIES, MAX_REPLY_LENGTH = 10, 40

DEFAULTS = {name: spec[4] for name, spec in NUMBERS.items()} | {REPLIES[0]: list(REPLIES[2])}


class SettingsError(ValueError):
    """A setting is wrong. The message says which and why."""


def describe():
    """Everything the Studio needs to draw the form: labels, limits and defaults."""
    numbers = [{"key": k, "label": label, "min": low, "max": high, "step": step, "default": default}
               for k, (label, low, high, step, default) in NUMBERS.items()]
    return {"numbers": numbers, "replies": {"key": REPLIES[0], "label": REPLIES[1], "default": REPLIES[2],
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
