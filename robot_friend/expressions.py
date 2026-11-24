"""
LESSON: Saving the eye design safely
====================================
The Eye Studio can now save straight to Bolt. That's powerful, so we CHECK
everything before saving ("validation"). A typo like "open": "lots" or an
iris colour of "blu" would otherwise break the eyes on every screen.

Where things live:
  * web/expressions.json      the ORIGINAL design that comes with the code
  * /data/expressions.json    YOUR saved design (in Bolt's saved data folder,
                              so it survives rebuilds, like reminders do)
  * /data/expressions.backup.json   the version before your last save

If you've saved a design, Bolt uses yours. "Back to original" deletes yours.
"""

import json
import math
import re
import threading
from pathlib import Path

ORIGINAL = Path(__file__).resolve().parent.parent / "web" / "expressions.json"

COLOURS = ("background", "lid", "irisRing", "iris", "pupil", "highlight", "brow", "mouth")
# name: (lowest, highest) allowed
FACE_SHAPE = {
    "eyeWidth": (0.1, 0.45), "eyeHeight": (0.15, 0.8), "eyeSpacing": (0.2, 0.7), "eyeY": (0.2, 0.7),
    "corner": (0, 0.5), "pupilRadius": (0.05, 0.45), "lookRange": (0, 1),
    "browThickness": (0.01, 0.08), "browGap": (0, 0.2), "mouthY": (0.6, 0.97), "mouthWidth": (0.04, 0.4),
}
SETTINGS = {
    "open": (0, 1), "lowerLid": (0, 1), "tilt": (-45, 45), "pupil": (0.2, 2),
    "lookX": (-1, 1), "lookY": (-1, 1), "wander": (0, 1), "blinkEvery": (0, 30), "bounce": (0, 3),
    "browShow": (0, 1), "browRaise": (-1, 1), "browArch": (-1, 1), "browTilt": (-30, 30),
    "mouthSmile": (-1, 1), "mouthOpen": (0, 1), "mouthWidth": (0.3, 2), "zzz": (0, 1), "hand": (0, 1),
}
# The robot's code switches to these, so they can't be deleted.
REQUIRED = ("idle", "sleeping", "listening", "thinking", "speaking", "happy", "confused", "sad", "surprised")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
NAME = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")


class DesignError(ValueError):
    """The design has a problem. The message says what and where."""


def _number(value, low, high, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DesignError(f"{where} must be a number.")
    if not low <= value <= high:
        raise DesignError(f"{where} must be between {low} and {high} (it was {value}).")


def _settings(block, where):
    if not isinstance(block, dict):
        raise DesignError(f"{where} must be a set of settings.")
    for key, value in block.items():
        if key not in SETTINGS:
            raise DesignError(f"{where} has an unknown setting '{key}'.")
        _number(value, *SETTINGS[key], f"{where}.{key}")


def upgrade(design):
    """
    Designs saved before Bolt had one rectangular screen had two round eyes
    ("eye" instead of "face"). Keep everything they had, and fill in the new
    face parts (layout, brows, mouth, their colours) from the original.
    Designs saved before a newer setting existed (like browShow) get it filled in too.
    """
    if not isinstance(design, dict) or not all(isinstance(design.get(k), dict) for k in ("colors", "defaults")):
        return design
    original = json.loads(ORIGINAL.read_text())
    upgraded = {k: v for k, v in design.items() if k != "eye"}
    upgraded["face"] = {**original["face"], **(design.get("face") or {})}
    upgraded["colors"] = {**original["colors"], **design["colors"]}
    upgraded["defaults"] = {**original["defaults"], **design["defaults"]}
    # A design from before the thinking hand existed: give its thinking face the hand too.
    if "hand" not in design["defaults"] and isinstance(upgraded.get("expressions"), dict):
        thinking = upgraded["expressions"].get("thinking")
        if isinstance(thinking, dict) and "hand" not in thinking:
            upgraded["expressions"] = {**upgraded["expressions"],
                                       "thinking": {**thinking, "hand": original["expressions"]["thinking"].get("hand", 1)}}
    # A design from before sleepy Zs existed: give its sleeping face the Zs too.
    if "zzz" not in design["defaults"] and isinstance(upgraded.get("expressions"), dict):
        sleeping = upgraded["expressions"].get("sleeping")
        if isinstance(sleeping, dict) and "zzz" not in sleeping:
            upgraded["expressions"] = {**upgraded["expressions"],
                                       "sleeping": {**sleeping, "zzz": original["expressions"]["sleeping"].get("zzz", 1)}}
    # A design from before Riley could look sad or surprised (her mood while she talks).
    if isinstance(upgraded.get("expressions"), dict):
        missing = {name: original["expressions"][name] for name in ("sad", "surprised")
                   if name not in upgraded["expressions"]}
        if missing:
            upgraded["expressions"] = {**upgraded["expressions"], **missing}
    return upgraded


def validate(design):
    """Raise DesignError if anything's wrong; otherwise return a tidy copy."""
    design = upgrade(design)
    if not isinstance(design, dict):
        raise DesignError("The design must be a JSON object.")
    for part in ("colors", "face", "defaults", "expressions"):
        if part not in design:
            raise DesignError(f"The design is missing '{part}'.")

    colours = design["colors"]
    for name in COLOURS:
        if not isinstance(colours.get(name), str) or not HEX.match(colours[name]):
            raise DesignError(f"colors.{name} must be a colour like #33c6ff.")

    for name, (low, high) in FACE_SHAPE.items():
        _number(design["face"].get(name), low, high, f"face.{name}")

    defaults = design["defaults"]
    _settings(defaults, "defaults")
    missing = [k for k in SETTINGS if k not in defaults]
    if missing:
        raise DesignError(f"defaults is missing {', '.join(missing)}.")

    expressions = design["expressions"]
    if not isinstance(expressions, dict):
        raise DesignError("expressions must be a set of named expressions.")
    for name in REQUIRED:
        if name not in expressions:
            raise DesignError(f"The '{name}' expression is needed by Bolt and can't be removed.")
    if len(expressions) > 40:
        raise DesignError("That's a lot of expressions! The limit is 40.")
    for name, exp in expressions.items():
        if not NAME.match(name):
            raise DesignError(f"'{name}' isn't a good expression name: use lowercase letters, numbers, - or _.")
        if not isinstance(exp, dict):
            raise DesignError(f"expressions.{name} must be a set of settings.")
        _settings({k: v for k, v in exp.items() if k not in ("left", "right")}, f"expressions.{name}")
        for side in ("left", "right"):
            if side in exp:
                _settings(exp[side], f"expressions.{name}.{side}")

    tidy = {k: design[k] for k in ("colors", "face", "defaults", "expressions")}
    return {"_about": json.loads(ORIGINAL.read_text()).get("_about", ""), **tidy}


class DesignStore:
    def __init__(self, path, original=ORIGINAL):
        self.path = Path(path)
        self.backup = self.path.with_name(self.path.stem + ".backup.json")
        self.original = Path(original)
        self._lock = threading.Lock()

    def current(self):
        """Your saved design if there is one, otherwise the original."""
        source = self.path if self.path.exists() else self.original
        return upgrade(json.loads(source.read_text()))

    def is_custom(self):
        return self.path.exists()

    def save(self, design):
        tidy = validate(design)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self.backup.write_text(self.path.read_text())
            # Write to a temporary file, then swap it in, so a crash can't leave half a file.
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(tidy, indent=2, ensure_ascii=False) + "\n")
            temp.replace(self.path)
        return tidy

    def undo(self):
        """Go back to the design before the last save."""
        with self._lock:
            if not self.backup.exists():
                raise DesignError("There's no earlier save to go back to.")
            self.backup.replace(self.path)

    def reset(self):
        """Forget your design and use the original again (keeping a backup)."""
        with self._lock:
            if self.path.exists():
                self.path.replace(self.backup)
