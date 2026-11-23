"""Tests for the fixes from the code review (one per finding)."""
import json
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace as Obj

import pytest

from robot_friend.brain import Brain, check_input
from robot_friend.home_assistant import HomeAssistant, HomeAssistantError
from robot_friend.memory import MemoryStore
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from server import Notifications, alarm_clock, create_app


# 1. Home Assistant: only real entity ids
@pytest.mark.parametrize("sneaky", ["light.x/../lock.front_door", "light.x?y=1", "light.kitchen,lock.door", "LIGHT.x", ""])
def test_odd_entity_ids_are_refused_before_asking_ha(sneaky):
    ha = HomeAssistant(url="http://unreachable.invalid", token="t")
    with pytest.raises(HomeAssistantError, match="isn't an entity id"):
        ha.get_state(sneaky)


def test_entity_ids_must_be_a_list():
    ha = HomeAssistant(url="http://unreachable.invalid", token="t")
    with pytest.raises(HomeAssistantError, match="as a list"):
        ha.call_service("light", "turn_on", "light.kitchen")


# 2. Reminders with a time zone, and an alarm clock that never dies
def test_time_zoned_reminders_become_local(tmp_path):
    store = ReminderStore(tmp_path / "r.json")
    r = store.add("bins", "2020-01-01T09:00Z")
    assert "+" not in r["due"] and "Z" not in r["due"]
    assert [x["message"] for x in store.pop_due()] == ["bins"]       # no crash comparing times


def test_the_alarm_clock_keeps_going_after_a_problem():
    class Flaky:
        rounds = 0
        def pop_due(self):
            self.rounds += 1
            if self.rounds == 1:
                raise TypeError("a bad reminder")
            return [{"message": "stretch"}]
    class Stop:
        def __init__(self): self.n = 0
        def is_set(self): return self.n >= 2
        def wait(self, s): self.n += 1
    notes = Notifications()
    alarm_clock(Flaky(), notes, Stop())
    assert [n["text"] for n in notes.after(0)] == ["Hey! Reminder: stretch"]


# 3. Saving safely, and surviving a damaged file
def test_a_damaged_memories_file_is_kept_aside_not_fatal(tmp_path):
    (tmp_path / "memories.json").write_text('[{"id": "a", "te')          # half-written
    store = MemoryStore(tmp_path / "memories.json")
    assert store.list() == []
    assert len(list(tmp_path.glob("memories.json.broken-*"))) == 1
    store.add("Luke likes tea")
    assert json.loads((tmp_path / "memories.json").read_text())[0]["text"] == "Luke likes tea"
    assert not list(tmp_path.glob("*.tmp"))                              # nothing left lying around


# 4. Notifications carry a boot code
def test_notifications_say_which_boot_they_are_from(tmp_path):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None)
    a, b = Notifications(), Notifications()
    assert a.boot != b.boot
    web = create_app(brain, a, security=Security(tmp_path, open_for_testing=True)).test_client()
    assert web.get("/notifications").get_json()["boot"] == a.boot


# 6. A chat with a photo in it is forgotten sooner
def test_photo_chats_are_forgotten_after_five_quiet_minutes(tmp_path):
    claude = Obj(messages=Obj(create=lambda **kw: Obj(stop_reason="end_turn", content=[Obj(type="text", text="ok")])))
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=claude)
    t = datetime(2026, 11, 23, 12, 0)
    brain.chat("hi", now=t)
    brain.photo_in_chat = True
    brain.chat("still there?", now=t + timedelta(minutes=6))
    assert len(brain.messages) == 2 and not brain.photo_in_chat       # started afresh
    brain.chat("and again", now=t + timedelta(minutes=12))
    assert len(brain.messages) == 4                                   # no photo: the usual 30 minutes


# 8. Tool requests are checked against their forms
def test_tool_inputs_are_checked():
    assert check_input("get_device", {"entity_id": "light.kitchen"}) is None
    assert "entity_ids" in check_input("control_device", {"domain": "light", "action": "turn_on",
                                                           "entity_ids": "light.kitchen", "data_json": "{}"})
    assert "missing" in check_input("add_reminder", {"message": "hi"})
    assert "unexpected" in check_input("forget", {"memory_id": "a", "also": 1})
    assert "should be integer" in check_input("home_history", {"entity_id": "sensor.x", "hours": "24"})


def test_a_badly_filled_tool_isnt_run(tmp_path):
    store = ReminderStore(tmp_path / "r.json")
    said = Brain(store, client=None).run_tool("add_reminder", {"message": "hi", "when": 5})
    assert said.startswith("Error: that request wasn't filled in properly") and store.list() == []


# 10. The streaming fallback doesn't repeat words already spoken
def test_fallback_after_broken_tool_json_doesnt_repeat_words(tmp_path):
    class BrokenStream:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        @property
        def text_stream(self):
            yield "Let me check the lights."
            raise ValueError("broken tool JSON")
    final = Obj(stop_reason="end_turn", content=[Obj(type="text", text="Let me check the lights. The lamp is on.")])
    claude = Obj(messages=Obj(stream=lambda **kw: BrokenStream(), create=lambda **kw: final))
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=claude)
    assert "".join(brain.chat_stream("lights?")) == "Let me check the lights. The lamp is on."


# 15. Login tracking is tidied
def test_old_wrong_password_records_are_forgotten(tmp_path):
    sec = Security(tmp_path)
    sec.record_fail("10.0.0.5", now=1000)
    sec.wait_needed("10.0.0.9", now=1000 + 301)
    assert "10.0.0.5" not in sec._fails
