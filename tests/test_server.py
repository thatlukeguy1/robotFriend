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


def test_studio_and_shared_files(tmp_path):
    _, _, web = make(tmp_path)
    page = web.get("/studio").data
    assert b"Bolt Studio" in page and b"tab-face" in page and b"tab-personality" in page
    assert web.get("/eyes").headers["Location"].endswith("/studio#face")   # old address still works
    assert "idle" in web.get("/static/expressions.json").get_json()["expressions"]
    assert b"BoltFace" in web.get("/static/face.js").data
    assert web.get("/static/../server.py").status_code == 404   # can't escape the web folder


def test_home_assistant_can_make_bolt_speak(tmp_path):
    brain, notes, web = make(tmp_path)
    r = web.post("/announce", json={"message": "The washing machine has finished."})
    assert r.status_code == 200 and notes.after(0)[-1]["text"] == "The washing machine has finished."
    assert web.post("/announce", json={"message": ""}).status_code == 400
    assert web.post("/announce", json={"message": "x" * 600}).status_code == 400


def test_announcements_can_be_said_in_her_own_words(tmp_path):
    brain, notes, web = make(tmp_path)
    brain.client.messages.create = lambda **kw: Obj(content=[Obj(type="text", text="Ooh, your washing's done!")])
    r = web.post("/announce", json={"message": "The washing machine has finished.", "rephrase": True})
    assert r.get_json()["said"] == "Ooh, your washing's done!" and notes.after(0)[-1]["text"] == "Ooh, your washing's done!"


def test_rephrasing_falls_back_to_the_original_words(tmp_path):
    brain, notes, web = make(tmp_path)
    def broken(**kw):
        raise RuntimeError("no internet")
    brain.client.messages.create = broken
    r = web.post("/announce", json={"message": "Front door opened.", "rephrase": True})
    assert r.get_json()["said"] == "Front door opened."
