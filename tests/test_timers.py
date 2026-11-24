"""Timers: a length of time, checked every second, shown on the screen."""
import pytest

from robot_friend.brain import Brain
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from robot_friend.timers import TimerStore, spoken_length
from server import Notifications, create_app, timer_clock


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


def test_timers_count_down_and_finish(tmp_path):
    clock = Clock()
    timers = TimerStore(tmp_path / "t.json", clock=clock)
    t = timers.add(600, "pasta")
    clock.now += 400
    assert timers.list()[0]["seconds_left"] == 200 and timers.pop_done() == []
    clock.now += 201
    assert [x["label"] for x in timers.pop_done()] == ["pasta"] and timers.list() == []


def test_timers_survive_a_restart(tmp_path):
    clock = Clock()
    TimerStore(tmp_path / "t.json", clock=clock).add(60, "tea")
    assert TimerStore(tmp_path / "t.json", clock=clock).list()[0]["label"] == "tea"


@pytest.mark.parametrize("seconds", [0, -5, 86401])
def test_silly_lengths_are_refused(tmp_path, seconds):
    with pytest.raises(ValueError):
        TimerStore(tmp_path / "t.json").add(seconds)


def test_cancel(tmp_path):
    timers = TimerStore(tmp_path / "t.json")
    t = timers.add(30)
    assert timers.cancel(t["id"]) and not timers.cancel(t["id"]) and timers.list() == []


def test_spoken_lengths():
    assert spoken_length(600) == "10-minute" and spoken_length(90) == "1 minute 30 second"
    assert spoken_length(3600) == "1-hour"


def test_the_timer_clock_announces_a_finished_timer(tmp_path):
    clock = Clock()
    timers = TimerStore(tmp_path / "t.json", clock=clock)
    timers.add(600, "pasta")
    clock.now += 601
    class Stop:
        n = 0
        def is_set(self): return self.n >= 1
        def wait(self, s): self.n += 1
    notes = Notifications()
    timer_clock(timers, notes, Stop())
    assert [n["text"] for n in notes.after(0)] == ["Your 10-minute pasta timer is done!"]


def test_timer_tools_and_the_feed(tmp_path):
    timers = TimerStore(tmp_path / "t.json")
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None, timers=timers)
    said = brain.run_tool("set_timer", {"seconds": 300, "label": "tea"})
    assert said.startswith("Timer ") and "300 seconds for tea" in said
    web = create_app(brain, Notifications(), security=Security(tmp_path, open_for_testing=True)).test_client()
    feed = web.get("/notifications").get_json()
    assert feed["timers"][0]["label"] == "tea" and feed["timers"][0]["seconds"] == 300
    assert "should be integer" in brain.run_tool("set_timer", {"seconds": "300", "label": ""})
