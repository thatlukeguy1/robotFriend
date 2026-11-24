"""
LESSON: Timers vs reminders
===========================
A REMINDER is for a time of day ("at 6pm, the bins"). A TIMER is for a length of
time ("10 minutes for the pasta"). Two differences matter:

  * Timers need to be ON TIME. Reminders are checked every 15 seconds, which is
    fine for "6pm"; a pasta timer 14 seconds late is not. So timers have their
    own clock that checks every second (timer_clock in server.py).
  * Timers are watched. Riley's screen shows how much is left (a line around the
    edge that shrinks), so the Pi is told each timer's time left and its length.

Timers are kept as the moment they END (seconds since 1970, "Unix time"), so they
survive a restart: if one ended while the brain was off, it goes off as soon as
the brain is back.
"""

import threading
import time
import uuid

from .storage import load_json_list, save_json

MAX_TIMERS = 10
MAX_SECONDS = 24 * 3600


class TimerStore:
    def __init__(self, path="timers.json", clock=time.time):
        self.path, self.clock = path, clock
        self._lock = threading.Lock()
        self._timers = load_json_list(path)

    def add(self, seconds, label=""):
        seconds = int(seconds)
        if not 1 <= seconds <= MAX_SECONDS:
            raise ValueError("A timer must be between 1 second and 24 hours.")
        with self._lock:
            if len(self._timers) >= MAX_TIMERS:
                raise ValueError(f"That's {MAX_TIMERS} timers already: cancel one first.")
            timer = {"id": uuid.uuid4().hex[:6], "label": label.strip()[:40], "seconds": seconds,
                     "ends": self.clock() + seconds}
            self._timers.append(timer)
            save_json(self.path, self._timers)
        return self.describe(timer)

    def describe(self, timer):
        return {"id": timer["id"], "label": timer["label"], "seconds": timer["seconds"],
                "seconds_left": max(0, round(timer["ends"] - self.clock()))}

    def list(self):
        with self._lock:
            return [self.describe(t) for t in sorted(self._timers, key=lambda t: t["ends"])]

    def cancel(self, timer_id):
        with self._lock:
            before = len(self._timers)
            self._timers = [t for t in self._timers if t["id"] != timer_id]
            if len(self._timers) < before:
                save_json(self.path, self._timers)
            return len(self._timers) < before

    def pop_done(self):
        """Remove and return every timer that has finished."""
        now = self.clock()
        with self._lock:
            done = [t for t in self._timers if t["ends"] <= now]
            if done:
                self._timers = [t for t in self._timers if t["ends"] > now]
                save_json(self.path, self._timers)
        return done


def spoken_length(seconds):
    """600 -> "10-minute", 90 -> "1 minute 30 second", for "your 10-minute timer is done"."""
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    parts = [f"{h} hour" if h else "", f"{m} minute" if m else "", f"{s} second" if s else ""]
    parts = [p for p in parts if p]
    return "-".join(parts[0].split(" ")) if len(parts) == 1 else " ".join(parts)
