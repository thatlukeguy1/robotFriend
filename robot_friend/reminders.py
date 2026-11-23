"""
LESSON: Reminders
=================
Claude can't set an alarm by itself. It only produces words. So WE write the
reminder code, and Claude asks us to run it using a "tool" (see brain.py).

This file is plain Python with no AI in it at all. It:
  1. keeps a list of reminders
  2. saves them to a file (reminders.json) so they survive a restart
  3. tells us which reminders are due
"""

import threading
import uuid
from datetime import datetime
from pathlib import Path

from .storage import load_json_list, save_json


class ReminderStore:
    def __init__(self, path="reminders.json"):
        self.path = Path(path)
        # A "lock" stops two parts of the program changing the list at the
        # same moment (the chat and the reminder checker run side by side).
        self._lock = threading.Lock()
        self._reminders = self._load()

    # ---------- saving and loading ----------

    def _load(self):
        return load_json_list(self.path)

    def _save(self):
        save_json(self.path, self._reminders)

    # ---------- things Claude can ask for ----------

    def add(self, message, when):
        """Add a reminder. `when` is text like '2026-11-18T15:30'."""
        due = datetime.fromisoformat(when)  # raises ValueError if Claude sent nonsense
        if due.tzinfo is not None:
            # LESSON: "09:00Z" (with a time zone) can't be compared with the clock's plain
            # local time; Python refuses. So turn it into local time, without a zone.
            due = due.astimezone().replace(tzinfo=None)
        reminder = {
            "id": uuid.uuid4().hex[:6],  # a short random name, e.g. "a3f9c1"
            "message": message,
            "due": due.isoformat(timespec="minutes"),
        }
        with self._lock:
            self._reminders.append(reminder)
            self._save()
        return reminder

    def list(self):
        with self._lock:
            return sorted(self._reminders, key=lambda r: r["due"])

    def cancel(self, reminder_id):
        with self._lock:
            before = len(self._reminders)
            self._reminders = [r for r in self._reminders if r["id"] != reminder_id]
            self._save()
            return len(self._reminders) < before  # True if we removed one

    # ---------- used by the alarm clock in main.py ----------

    def pop_due(self, now=None):
        """Remove and return every reminder whose time has come."""
        now = now or datetime.now()
        with self._lock:
            due = [r for r in self._reminders if datetime.fromisoformat(r["due"]) <= now]
            if due:
                self._reminders = [r for r in self._reminders if r not in due]
                self._save()
        return due
