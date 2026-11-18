"""Tests for long-term memory."""

from datetime import datetime, timedelta
from types import SimpleNamespace as Obj

import pytest

from robot_friend.brain import Brain
from robot_friend.memory import MAX_MEMORIES, MemoryStore
from robot_friend.reminders import ReminderStore
from server import Notifications, create_app


class RecordingClaude:
    """Pretend Claude that can be told to call a tool, and records every request."""

    def __init__(self, script=()):
        self.calls, self.script = [], list(script)
        self.messages = Obj(create=self.create)

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        if self.script:
            name, args = self.script.pop(0)
            return Obj(stop_reason="tool_use", content=[Obj(type="tool_use", id="t1", name=name, input=args)])
        return Obj(stop_reason="end_turn", content=[Obj(type="text", text="OK!")])


def make_brain(tmp_path, script=()):
    claude = RecordingClaude(script)
    memories = MemoryStore(tmp_path / "m.json")
    return Brain(ReminderStore(tmp_path / "r.json"), client=claude, memories=memories), claude, memories


# ------------------------------------------------------------ the store

def test_add_list_forget_and_survive_restart(tmp_path):
    store = MemoryStore(tmp_path / "m.json")
    m = store.add("Luke's sister is called Amy.")
    assert MemoryStore(tmp_path / "m.json").list()[0]["text"] == "Luke's sister is called Amy."
    assert store.forget(m["id"]) and store.list() == []
    assert store.forget("nope") is False


def test_empty_memory_is_refused(tmp_path):
    with pytest.raises(ValueError):
        MemoryStore(tmp_path / "m.json").add("   ")


def test_memory_has_a_limit(tmp_path):
    store = MemoryStore(tmp_path / "m.json")
    for i in range(MAX_MEMORIES):
        store.add(f"fact {i}")
    with pytest.raises(ValueError, match="full"):
        store.add("one too many")


# ------------------------------------------------------- through the brain

def test_memories_are_in_the_instructions(tmp_path):
    brain, claude, memories = make_brain(tmp_path)
    memories.add("Luke hates mushrooms.")
    brain.chat("hi")
    assert "Luke hates mushrooms." in claude.calls[0]["system"]


def test_remember_tool_saves(tmp_path):
    brain, _, memories = make_brain(tmp_path, script=[("remember", {"fact": "Luke's cat is called Pixel."})])
    brain.chat("my cat is called Pixel")
    assert memories.list()[0]["text"] == "Luke's cat is called Pixel."


def test_forget_tool(tmp_path):
    brain, _, memories = make_brain(tmp_path)
    m = memories.add("old fact")
    assert brain.run_tool("forget", {"memory_id": m["id"]}) == "Forgotten."
    assert memories.list() == []


def test_instructions_never_change_mid_conversation(tmp_path):
    """Claude rejects conversations whose start was edited, so a new memory must
    wait for the next conversation."""
    brain, claude, memories = make_brain(tmp_path, script=[("remember", {"fact": "Luke likes tea."})])
    t = datetime(2026, 11, 20, 10, 0)
    brain.chat("I like tea", now=t)
    brain.chat("what else?", now=t + timedelta(minutes=1))
    systems = {c["system"] for c in claude.calls}
    assert len(systems) == 1 and "Luke likes tea." not in systems.pop()

    brain.chat("morning!", now=t + timedelta(hours=3))  # quiet for ages -> new conversation
    assert "Luke likes tea." in claude.calls[-1]["system"]


def test_brain_without_memory(tmp_path):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=RecordingClaude())
    assert "isn't switched on" in brain.run_tool("remember", {"fact": "x"})


# --------------------------------------------------------------- the routes

def test_memory_routes(tmp_path):
    brain, _, memories = make_brain(tmp_path)
    m = memories.add("Luke's birthday is 3 March.")
    web = create_app(brain, Notifications()).test_client()
    assert web.get("/memories").get_json()["memories"][0]["text"] == "Luke's birthday is 3 March."
    assert web.delete(f"/memories/{m['id']}").status_code == 200
    assert web.get("/memories").get_json()["memories"] == []
    assert web.delete("/memories/nope").status_code == 404
