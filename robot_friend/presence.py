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

MORNING BRIEFS: the first time the camera sees someone between MORNING (5am and noon),
she gives them the morning briefing instead of a hello, once a day. If they asked for it
themselves first ("good morning!"), that counts, so they don't get it twice.

The book also tells Claude who's at the desk, so "remember I like tea" gets
saved against the right person.
"""

import threading
import time
from datetime import datetime

from .storage import load_json_list, save_json

DESK_MINUTES = 10          # seen this recently = "at the desk"
GREET_AGAIN = 3 * 3600     # seconds before the same person is greeted again
MORNING = (5, 12)          # the morning brief is for first sightings from 5:00 until 11:59
EVERYONE = "*"             # "briefed today" for whoever asked, when we don't know who it was


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
        self.briefed_on = {}         # name -> the date ("2026-11-26") of their last morning brief (saved too)
        if path:
            for item in load_json_list(path):        # [name, when] or ["briefed", name, date]
                if isinstance(item, list) and len(item) == 2 and isinstance(item[1], (int, float)):
                    self.greeted_at[str(item[0])] = float(item[1])
                elif isinstance(item, list) and len(item) == 3 and item[0] == "briefed":
                    self.briefed_on[str(item[1])] = str(item[2])

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
            self._save(now)
            return True

    def _today(self):
        return datetime.fromtimestamp(self.clock()).date().isoformat()

    def should_brief(self, name):
        """True (and remembers it) if this is the first sighting of `name` this morning and
        they haven't had their briefing yet today."""
        now = self.clock()
        if not MORNING[0] <= datetime.fromtimestamp(now).hour < MORNING[1]:
            return False
        today = self._today()
        with self._lock:
            for other, day in self.briefed_on.items():
                if day == today and (other == EVERYONE or same_person(other, name)):
                    return False
            self.briefed_on[name] = today
            self._save(now)
            return True

    def briefed(self, names):
        """Someone asked for the briefing themselves: it counts as theirs for today. `names` are
        the people at the desk; if nobody's there, it counts for everyone."""
        now, today = self.clock(), self._today()
        with self._lock:
            for name in names or [EVERYONE]:
                self.briefed_on[name] = today
            self._save(now)

    def _save(self, now):
        """(Called with the lock held.)"""
        if not self.path:
            return
        today = self._today()
        try:
            save_json(self.path, [[n, w] for n, w in self.greeted_at.items() if now - w < GREET_AGAIN]
                      + [["briefed", n, d] for n, d in self.briefed_on.items() if d == today])
        except OSError as e:                          # a full disk mustn't stop the hello
            print(f"! couldn't save greetings: {e}", flush=True)

    def summary(self):
        """For the who_is_home tool."""
        home = self.home or {}
        return {"home": sorted(n for n, s in home.values() if s == "home"),
                "away": sorted(n for n, s in home.values() if s != "home"),
                "at_your_desk": self.at_desk()}
