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

The book also tells Claude who's at the desk, so "remember I like tea" gets
saved against the right person.
"""

import threading
import time

DESK_MINUTES = 10          # seen this recently = "at the desk"
GREET_AGAIN = 3 * 3600     # seconds before the same person is greeted again


def same_person(a, b):
    """HA says "Luke Newman", the face was enrolled as "Luke": the same person."""
    first = lambda name: (name or "").strip().split(" ")[0].lower()
    return first(a) == first(b) and first(a) != ""


class PresenceBook:
    def __init__(self, clock=time.time):
        self.clock = clock
        self._lock = threading.Lock()
        self.home = None             # {entity_id: (name, state)} the last time HA was asked
        self.desk = {}               # name -> when the camera last saw them
        self.greeted_at = {}         # name -> when she last greeted them

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
            return True

    def summary(self):
        """For the who_is_home tool."""
        home = self.home or {}
        return {"home": sorted(n for n, s in home.values() if s == "home"),
                "away": sorted(n for n, s in home.values() if s != "home"),
                "at_your_desk": self.at_desk()}
