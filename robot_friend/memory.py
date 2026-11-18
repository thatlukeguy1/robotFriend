"""
LESSON: Long-term memory
========================
Remember the big secret from brain.py? Claude has NO memory between messages:
we resend the conversation every time. That's SHORT-TERM memory, and Bolt
wipes it after 30 quiet minutes.

LONG-TERM memory works differently. When Bolt learns something worth keeping
("Luke's sister is called Amy", "Luke hates mushrooms"), it uses a tool to
write it down in memories.json. At the start of EVERY new conversation, we
read that file and add the list to Bolt's instructions, so it "remembers".

It's a lot like a person keeping a diary of important facts, and reading it
every morning.

Two rules keep it honest:
  * You can see and delete every memory (the 🧠 button on the chat page).
  * Memories are added at the START of a conversation only. Claude rejects a
    conversation whose earlier parts have been changed, so a new memory joins
    the instructions the next time a conversation starts.
"""

import json
import threading
import uuid
from datetime import date
from pathlib import Path

MAX_MEMORIES = 200  # plenty for a friend; keeps the instructions a sensible size


class MemoryStore:
    def __init__(self, path="memories.json"):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._memories = json.loads(self.path.read_text()) if self.path.exists() else []

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._memories, indent=2))

    def add(self, text):
        text = text.strip()
        if not text:
            raise ValueError("A memory needs some text.")
        with self._lock:
            if len(self._memories) >= MAX_MEMORIES:
                raise ValueError(f"Memory is full ({MAX_MEMORIES}). Forget something old first.")
            memory = {"id": uuid.uuid4().hex[:6], "text": text, "saved": date.today().isoformat()}
            self._memories.append(memory)
            self._save()
        return memory

    def forget(self, memory_id):
        with self._lock:
            before = len(self._memories)
            self._memories = [m for m in self._memories if m["id"] != memory_id]
            self._save()
            return len(self._memories) < before

    def list(self):
        with self._lock:
            return list(self._memories)

    def as_prompt(self):
        """The memories, written out for Bolt's instructions."""
        memories = self.list()
        if not memories:
            return "You don't have any long-term memories yet."
        lines = [f"- [{m['id']}, saved {m['saved']}] {m['text']}" for m in memories]
        return "Things you've chosen to remember:\n" + "\n".join(lines)
