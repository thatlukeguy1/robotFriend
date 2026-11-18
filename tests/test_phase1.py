"""
LESSON: Tests
=============
A test is a tiny program that checks your real program still works.
These tests use a PRETEND Claude, so they're free, fast and work offline.

Run them with:   python -m pytest
"""

from datetime import datetime
from types import SimpleNamespace as Obj

from robot_friend.brain import Brain
from robot_friend.reminders import ReminderStore


def test_reminders_save_list_and_fire(tmp_path):
    store = ReminderStore(tmp_path / "r.json")
    r = store.add("stretch", "2026-11-18T15:30")
    assert store.list()[0]["message"] == "stretch"

    # Reload from disk: the reminder should survive a "restart".
    assert ReminderStore(tmp_path / "r.json").list()[0]["id"] == r["id"]

    assert store.pop_due(datetime(2026, 11, 18, 15, 0)) == []        # too early
    assert len(store.pop_due(datetime(2026, 11, 18, 15, 31))) == 1   # due!
    assert store.list() == []                                         # and gone


def test_cancel(tmp_path):
    store = ReminderStore(tmp_path / "r.json")
    r = store.add("x", "2026-11-18T15:30")
    assert store.cancel(r["id"]) is True
    assert store.cancel("nope") is False


class FakeClaude:
    """Pretends to be Claude: first asks to set a reminder, then replies."""

    def __init__(self):
        self.calls = []
        self.beta = Obj(messages=Obj(create=self.create))

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot, like the real API
        if len(self.calls) == 1:
            return Obj(stop_reason="tool_use", content=[
                Obj(type="tool_use", id="tu_1", name="add_reminder",
                    input={"message": "drink water", "when": "2026-11-18T15:30"}),
            ])
        return Obj(stop_reason="end_turn", content=[Obj(type="text", text="Done, I'll nudge you!")])


def test_agent_loop_runs_tool_and_replies(tmp_path):
    store = ReminderStore(tmp_path / "r.json")
    fake = FakeClaude()
    brain = Brain(store, client=fake)

    reply = brain.chat("remind me to drink water at half three", now=datetime(2026, 11, 18, 14, 0))

    assert reply == "Done, I'll nudge you!"
    assert store.list()[0]["message"] == "drink water"
    # The second call to Claude must include our tool result.
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "tu_1" and "set for" in tool_result["content"]
    # And the time stamp was added to what the owner said.
    assert brain.messages[0]["content"].startswith("[Wednesday 18 November 2026, 14:00]")


def test_bad_tool_input_is_reported_not_crashed(tmp_path):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=FakeClaude())
    assert brain.run_tool("add_reminder", {"message": "x", "when": "teatime"}).startswith("Error")


def test_refusal_forgets_the_turn(tmp_path):
    fake = Obj(beta=Obj(messages=Obj(create=lambda **k: Obj(stop_reason="refusal", content=[]))))
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=fake)
    brain.chat("something")
    assert brain.messages == []
