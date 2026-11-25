"""
LESSON: Asking the body for a photo
===================================
The camera is on the Pi, but the thinking happens here on the brain. The brain
can't phone the Pi (the Pi is the one that phones the brain, like your phone
visiting a website), so a photo is fetched like this:

  1. Claude uses the `look` tool. The brain writes a REQUEST on this "desk"
     and waits (up to about 8 seconds).
  2. The Pi checks the desk twice a second (GET /camera/wanted). It sees the
     request, takes a photo, and hands it in (POST /camera/photo/<id>).
  3. The brain wakes up with the photo and gives it to Claude.

PRIVACY: photos are only taken when someone asks Riley to look, and none are
saved to disk. A photo does stay in that conversation's short-term memory (Claude
is sent the whole conversation each time), so a conversation with a photo in it is
forgotten after 5 quiet minutes instead of 30 (PHOTO_RESET in brain.py).

If the Pi hasn't checked the desk for a while (it's off, or has no camera),
`take()` says so straight away instead of waiting.

SEEING WHAT SHE SEES (the 📷 button on the chat page) uses the same desk, with a
second kind of request, a "view": a smaller picture, plus BOXES the Pi drew
round what it recognised (faces with names, everyday things with their labels).
The page asks for a new one about once a second while it's open. Views aren't
given to Claude and aren't saved, and her screen shows 📷 while anyone watches.
"""

import base64
import secrets
import threading
import time

MAX_PHOTO_BYTES = 5_000_000
PI_GONE_AFTER = 10.0     # no check-in for this long = the body (or its camera) isn't there
                         # (longer than the Pi's 5.5 s pause after a camera hiccup)
MAX_BOXES = 40
BOX_KINDS = ("face", "thing")


def clean_boxes(boxes):
    """Only what the page needs, checked: [{"kind", "label", "box": [x, y, w, h], "score"}].
    Anything odd is dropped rather than passed on (the page draws these labels)."""
    tidy = []
    for b in boxes if isinstance(boxes, list) else []:
        if not isinstance(b, dict) or b.get("kind") not in BOX_KINDS:
            continue
        box = b.get("box")
        if not (isinstance(box, list) and len(box) == 4
                and all(isinstance(n, (int, float)) and not isinstance(n, bool) and 0 <= n <= 10000 for n in box)):
            continue
        score = b.get("score")
        tidy.append({"kind": b["kind"], "label": str(b.get("label", ""))[:40], "box": [round(n) for n in box],
                     "score": round(float(score), 2) if isinstance(score, (int, float)) and not isinstance(score, bool) else None})
        if len(tidy) >= MAX_BOXES:
            break
    return tidy


class PhotoDesk:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.requests = {}        # id -> {"done": Event, "photo": bytes or None, "kind", "boxes"}
        self.last_check = None    # when the Pi last asked for work

    # ------------------------------------------------- the Pi's side

    def wanted(self):
        """The Pi asks: is a photo wanted? Returns a request id, or None."""
        with self.lock:
            self.last_check = self.clock()
            for rid, r in self.requests.items():
                if r["photo"] is None and not r["handed_out"]:
                    r["handed_out"] = True
                    return rid
        return None

    def kind(self, rid):
        """"photo" (for Claude) or "view" (for the 📷 page)."""
        with self.lock:
            return self.requests.get(rid, {}).get("kind", "photo")

    def deliver_view(self, rid, data):
        """The Pi hands in a view: {"image": JPEG as base64 text, "boxes": [...]}."""
        if not isinstance(data, dict):
            return "Send {\"image\": ..., \"boxes\": [...]}."
        try:
            jpeg = base64.b64decode(str(data.get("image", "")), validate=True)
        except ValueError:
            return "The image wasn't base64."
        return self.deliver(rid, jpeg, boxes=clean_boxes(data.get("boxes")), paused=data.get("paused") is True)

    def deliver(self, rid, photo, boxes=None, paused=False):
        """The Pi hands in a photo. Returns an error message, or None if it was accepted."""
        if not photo.startswith(b"\xff\xd8"):          # every JPEG starts with these two bytes
            return "That isn't a JPEG photo."
        if len(photo) > MAX_PHOTO_BYTES:
            return "That photo is too big."
        with self.lock:
            r = self.requests.get(rid)
            if r is None:
                return "Nobody asked for that photo (or it took too long)."
            r["photo"], r["boxes"], r["paused"] = photo, boxes or [], paused
            r["done"].set()
        return None

    # ------------------------------------------------- the brain's side

    def body_is_there(self):
        return self.last_check is not None and self.clock() - self.last_check < PI_GONE_AFTER

    def take(self, timeout=8.0):
        """Ask the Pi for a photo and wait for it. Returns (photo bytes, None) or (None, why not)."""
        got, problem = self._ask("photo", timeout)
        return (got["photo"] if got else None), problem

    def view(self, timeout=5.0):
        """What she sees right now, for the 📷 page: ({"photo": JPEG, "boxes": [...]}, None)
        or (None, why not)."""
        return self._ask("view", timeout)

    def _ask(self, kind, timeout):
        if not self.body_is_there():
            return None, "the camera isn't connected (the body is off, or has no camera)"
        rid = secrets.token_urlsafe(12)
        done = threading.Event()
        with self.lock:
            self.requests[rid] = {"done": done, "photo": None, "handed_out": False, "kind": kind, "boxes": []}
        try:
            if not done.wait(timeout):
                return None, "the body didn't send a picture in time"
            r = self.requests[rid]
            return {"photo": r["photo"], "boxes": r["boxes"], "paused": r.get("paused", False)}, None
        finally:
            with self.lock:
                self.requests.pop(rid, None)               # forget it either way
