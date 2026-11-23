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

PRIVACY: photos are only taken when someone asks Riley to look. None are kept:
each one is handed to Claude for that one question, then forgotten here.

If the Pi hasn't checked the desk for a while (it's off, or has no camera),
`take()` says so straight away instead of waiting.
"""

import secrets
import threading
import time

MAX_PHOTO_BYTES = 5_000_000
PI_GONE_AFTER = 5.0      # no check-in for this long = the body (or its camera) isn't there


class PhotoDesk:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.requests = {}        # id -> {"done": Event, "photo": bytes or None}
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

    def deliver(self, rid, photo):
        """The Pi hands in a photo. Returns an error message, or None if it was accepted."""
        if not photo.startswith(b"\xff\xd8"):          # every JPEG starts with these two bytes
            return "That isn't a JPEG photo."
        if len(photo) > MAX_PHOTO_BYTES:
            return "That photo is too big."
        with self.lock:
            r = self.requests.get(rid)
            if r is None:
                return "Nobody asked for that photo (or it took too long)."
            r["photo"] = photo
            r["done"].set()
        return None

    # ------------------------------------------------- the brain's side

    def body_is_there(self):
        return self.last_check is not None and self.clock() - self.last_check < PI_GONE_AFTER

    def take(self, timeout=8.0):
        """Ask the Pi for a photo and wait for it. Returns (photo bytes, None) or (None, why not)."""
        if not self.body_is_there():
            return None, "the camera isn't connected (the body is off, or has no camera)"
        rid = secrets.token_urlsafe(12)
        done = threading.Event()
        with self.lock:
            self.requests[rid] = {"done": done, "photo": None, "handed_out": False}
        try:
            if not done.wait(timeout):
                return None, "the body didn't send a photo in time"
            return self.requests[rid]["photo"], None
        finally:
            with self.lock:
                self.requests.pop(rid, None)               # forget it either way
