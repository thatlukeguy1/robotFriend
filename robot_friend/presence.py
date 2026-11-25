"""
LESSON: Knowing who's around
============================
Riley learns who's about in two ways, and keeps them in one "book":

  * WHO'S HOME comes from Home Assistant: your phones tell it who's in
    (person.luke: "home" / "not_home"). When someone changes to "home", that's
    an ARRIVAL, and Riley can welcome them back.
  * WHO'S AT THE DESK comes from the Pi's camera, which recognises faces it has
    been taught (pi/bolt_body/faces.py). Only a NAME ever reaches the brain.

Two rules keep the greetings friendly rather than annoying:
  * she greets each person at most once every few hours (GREET_AGAIN), however
    many times they walk past;
  * a welcome-home counts, so she won't say hello again when you sit down a
    minute later.

Who she's greeted, and when, is saved to a file (GREETED_PATH), so restarting the brain
(an update, say) doesn't make her greet everyone again as if they'd just arrived.

The book also tells Claude who's at the desk, so "remember I like tea" gets
saved against the right person.
"""

import threading
import time

from .storage import load_json_list, save_json

DESK_MINUTES = 10          # seen this recently = "at the desk"
GREET_AGAIN = 3 * 3600     # seconds before the same person is greeted again


def same_person(a, b):
    """HA says "Luke Newman", the face was enrolled as "Luke": the same person."""
    first = lambda name: (name or "").strip().split(" ")[0].lower()
    return first(a) == first(b) and first(a) != ""


class PresenceBook:
    def __init__(self, clock=time.time, path=None):
        self.clock, self.path = clock, path
        self._lock = threading.Lock()
        self.home = None             # {entity_id: (name, state)} the last time HA was asked
        self.desk = {}               # name -> when the camera last saw them
        self.greeted_at = {}         # name -> when she last greeted them (saved, see above)
        if path:
            for item in load_json_list(path):        # [[name, when], ...]
                if isinstance(item, list) and len(item) == 2 and isinstance(item[1], (int, float)):
                    self.greeted_at[str(item[0])] = float(item[1])

    def update_home(self, people):
        """People from Home Assistant: [{"entity_id", "name", "state"}]. Returns the names that
        have just ARRIVED home. The very first look finds nobody "arriving": they were already in."""
        now_home = {p["entity_id"]: (p["name"], p["state"]) for p in people}
        with self._lock:
            before, self.home = self.home, now_home
        if before is None:
            return []
        return [name for eid, (name, state) in now_home.items()
                if state == "home" and before.get(eid, (name, "home"))[1] != "home"]

    def seen_at_desk(self, name):
        with self._lock:
            self.desk[name] = self.clock()

    def at_desk(self):
        now = self.clock()
        with self._lock:
            return sorted(n for n, t in self.desk.items() if now - t < DESK_MINUTES * 60)

    def should_greet(self, name):
        """True (and remembers it) if this person hasn't been greeted for a while."""
        now = self.clock()
        with self._lock:
            for other, when in self.greeted_at.items():
                if same_person(other, name) and now - when < GREET_AGAIN:
                    return False
            self.greeted_at[name] = now
            if self.path:
                try:
                    save_json(self.path, [[n, w] for n, w in self.greeted_at.items() if now - w < GREET_AGAIN])
                except OSError as e:                  # a full disk mustn't stop the hello
                    print(f"! couldn't save greetings: {e}", flush=True)
            return True

    def summary(self):
        """For the who_is_home tool."""
        home = self.home or {}
        return {"home": sorted(n for n, s in home.values() if s == "home"),
                "away": sorted(n for n, s in home.values() if s != "home"),
                "at_your_desk": self.at_desk()}
