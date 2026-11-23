"""
LESSON: Saving files safely
===========================
Writing a file isn't instant. If the power goes off halfway through, you're left
with half a file, and the next time Riley starts she can't read it.

The safe way is two steps:
  1. write everything to a NEW file next to it (memories.json.tmp)
  2. swap the new one into place (replace). The swap is a single step the
     computer does all at once, so there is always either the whole old file
     or the whole new one, never half of either.

And if a file is damaged anyway, Riley keeps a copy for you (…broken-<time>)
and starts with an empty list, instead of refusing to start at all.
"""

import json
import os
import time
from pathlib import Path


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())          # make sure it's really on the disk before the swap
    temp.replace(path)


def load_json_list(path):
    """The list saved in this file; [] if there's no file. A damaged file is kept aside."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return data
        raise ValueError("not a list")
    except (ValueError, UnicodeDecodeError) as e:
        broken = path.with_name(f"{path.name}.broken-{time.strftime('%Y%m%d-%H%M%S')}")
        path.replace(broken)
        print(f"! {path.name} was damaged ({e}). Kept it as {broken.name} and started afresh.", flush=True)
        return []
