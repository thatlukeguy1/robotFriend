"""The morning briefing: one tool that gathers weather, calendar, reminders and the night's events."""
import json
from datetime import datetime

from robot_friend.brain import Brain
from robot_friend.home_assistant import HomeAssistant
from robot_friend.reminders import ReminderStore

NOW = datetime(2026, 11, 23, 7, 30)


class StubHome:
    can_control = True
    def weather_today(self):
        return {"now": "rainy", "temperature": 8, "unit": "°C", "today": {"temperature": 11, "templow": 4}}
    def calendar_events(self, days):
        return [{"calendar": "Family", "summary": "Dentist", "start": "Mon 23 Nov 10:30"}]
    def logbook(self, hours):
        return [{"name": "Lounge temperature", "message": "changed to 19", "entity_id": "sensor.lounge_temperature"},
                {"name": "Back door", "message": "opened", "entity_id": "binary_sensor.back_door"}]
    def errors_since(self, since):
        raise RuntimeError("the token isn't an admin's")


def brain(tmp_path, home):
    reminders = ReminderStore(tmp_path / "r.json")
    reminders.add("take the bins out", "2026-11-23T18:00")
    reminders.add("call mum", "2026-11-24T09:00")
    return Brain(reminders, client=None, home=home)


def test_briefing_gathers_everything_and_skips_routine_things(tmp_path):
    out = brain(tmp_path, StubHome()).morning_briefing(NOW)
    assert out["now"] == "Monday 23 November, 07:30"
    assert [r["message"] for r in out["reminders_today"]] == ["take the bins out"]     # not tomorrow's
    assert out["weather"]["now"] == "rainy" and out["calendar_today"][0]["summary"] == "Dentist"
    assert [e["name"] for e in out["overnight"]] == ["Back door"]                     # sensor chatter skipped
    assert out["home_assistant_errors"].startswith("couldn't check")                 # one problem, rest still there


def test_briefing_without_a_smart_home(tmp_path):
    out = brain(tmp_path, None).morning_briefing(NOW)
    assert out["smart_home"] == "not set up" and len(out["reminders_today"]) == 1


def test_the_tool_returns_json(tmp_path):
    said = brain(tmp_path, StubHome()).run_tool("morning_briefing", {})
    assert json.loads(said)["weather"]["temperature"] == 8


def test_weather_today_asks_for_the_forecast():
    home = HomeAssistant("http://ha", "token", "", blocked_domains=["lock"])
    home.protection = lambda: ({}, {})
    asked = []
    def fake_request(method, path, body=None, text=False):
        asked.append((method, path))
        if path == "/api/states":
            return [{"entity_id": "weather.home", "state": "rainy", "attributes": {"friendly_name": "Home"}}]
        if path == "/api/states/weather.home":
            return {"entity_id": "weather.home", "state": "rainy", "attributes": {"temperature": 8, "temperature_unit": "°C"}}
        return {"service_response": {"weather.home": {"forecast": [{"condition": "rainy", "temperature": 11, "templow": 4}]}}}
    home._request = fake_request
    w = home.weather_today()
    assert w["now"] == "rainy" and w["today"]["temperature"] == 11
    assert ("POST", "/api/services/weather/get_forecasts?return_response") in asked


def test_errors_since_counts_only_recent_errors():
    home = HomeAssistant("http://ha", "token", "", blocked_domains=["lock"])
    home.error_log = lambda search, lines: "\n".join([
        "2026-11-22 20:00:00.000 ERROR (MainThread) [hue] old one",
        "2026-11-23 03:12:00.000 ERROR (MainThread) [nest] Login failed",
        "2026-11-23 05:40:00.000 ERROR (MainThread) [zha] Device offline"])
    out = home.errors_since(datetime(2026, 11, 22, 21, 30))
    assert out["count"] == 2 and "nest" in out["examples"][0]
