"""
LESSON: Testing a server without a network
Flask has a "test client": a pretend browser that sends requests straight
to our app. Combined with a pretend Claude, we can test the whole API offline.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace as Obj

from robot_friend.brain import Brain
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from server import Notifications, alarm_clock, create_app


class EchoClaude:
    def __init__(self):
        self.messages = Obj(create=self.create)

    def create(self, **kwargs):
        last = kwargs["messages"][-1]["content"]
        return Obj(stop_reason="end_turn", content=[Obj(type="text", text="You said: " + last.split("] ", 1)[1])])


def make(tmp_path):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=EchoClaude())
    notes = Notifications()
    return brain, notes, create_app(brain, notes, security=Security(tmp_path, open_for_testing=True)).test_client()


def test_health_and_page(tmp_path):
    _, _, web = make(tmp_path)
    assert web.get("/health").get_json()["status"] == "ok"
    assert b"Bolt" in web.get("/").data


def test_chat_and_reset(tmp_path):
    brain, _, web = make(tmp_path)
    assert web.post("/chat", json={"text": "hello"}).get_json() == {"reply": "You said: hello"}
    assert len(brain.messages) == 2
    web.post("/reset")
    assert brain.messages == []


def test_chat_needs_text(tmp_path):
    _, _, web = make(tmp_path)
    assert web.post("/chat", json={}).status_code == 400


def test_notifications_after(tmp_path):
    _, notes, web = make(tmp_path)
    notes.add("one"); notes.add("two")
    assert [n["text"] for n in web.get("/notifications").get_json()["notifications"]] == ["one", "two"]
    assert [n["text"] for n in web.get("/notifications?after=1").get_json()["notifications"]] == ["two"]


def test_alarm_clock_posts_notifications(tmp_path):
    store = ReminderStore(tmp_path / "r.json")
    store.add("tea", (datetime.now() - timedelta(minutes=1)).isoformat(timespec="minutes"))
    notes = Notifications()

    class StopAfterOne:
        def __init__(self): self.n = 0
        def is_set(self): self.n += 1; return self.n > 1
        def wait(self, _): pass

    alarm_clock(store, notes, StopAfterOne())
    assert notes.after(0)[0]["text"] == "Hey! Reminder: tea"


def test_idle_reset(tmp_path):
    brain, _, _ = make(tmp_path)
    t = datetime(2026, 11, 20, 10, 0)
    brain.chat("a", now=t)
    brain.chat("b", now=t + timedelta(minutes=5))
    assert len(brain.messages) == 4          # same conversation
    brain.chat("c", now=t + timedelta(hours=2))
    assert len(brain.messages) == 2          # quiet for ages, so a fresh start


def test_eye_studio_and_shared_files(tmp_path):
    _, _, web = make(tmp_path)
    assert b"Eye Studio" in web.get("/eyes").data
    assert "idle" in web.get("/static/expressions.json").get_json()["expressions"]
    assert b"BoltEyes" in web.get("/static/eyes.js").data
    assert web.get("/static/../server.py").status_code == 404   # can't escape the web folder
