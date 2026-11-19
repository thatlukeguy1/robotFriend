"""
Tests for READING Home Assistant: logbook, history, error log and calendars.
As with control, the important ones check that blocked devices (locks) stay invisible.
"""

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from robot_friend.brain import Brain
from robot_friend.home_assistant import HomeAssistant, HomeAssistantError
from robot_friend.reminders import ReminderStore

LOGBOOK = [
    {"when": "2026-11-19T09:00:00+00:00", "name": "Desk Lamp", "message": "turned on", "entity_id": "light.desk_lamp", "domain": "light"},
    {"when": "2026-11-19T09:05:00+00:00", "name": "Front Door", "message": "was unlocked", "entity_id": "lock.front_door", "domain": "lock"},
    {"when": "2026-11-19T09:10:00+00:00", "name": "Morning lights", "message": "triggered", "entity_id": "automation.morning", "domain": "automation"},
]
ERROR_LOG = "\n".join([
    "2026-11-19 08:00:00 WARNING (MainThread) [homeassistant.components.hue] Bridge slow to answer",
    "2026-11-19 08:01:00 ERROR (MainThread) [homeassistant.components.nest] Login failed password=hunter2 for user",
    "2026-11-19 08:02:00 ERROR (MainThread) [homeassistant.components.august] lock.front_door unavailable",
    "2026-11-19 08:03:00 ERROR (MainThread) [custom] sent Authorization: Bearer eyJabc.def.ghi to the cloud",
])


@pytest.fixture
def ha():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body, kind="application/json"):
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(code); self.send_header("content-type", kind)
            self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            seen.append(self.path)
            url = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(url.query, keep_blank_values=True)
            if url.path.startswith("/api/logbook/"):
                entity = query.get("entity", [""])[0]
                return self.reply(200, [e for e in LOGBOOK if not entity or e["entity_id"] == entity])
            if url.path.startswith("/api/history/period/"):
                states = [{"entity_id": "sensor.lounge_temperature", "state": "19.0", "last_changed": "2026-11-19T00:00:00+00:00"}]
                states += [{"state": str(16 + i % 5), "last_changed": f"2026-11-19T{i // 6:02d}:{i % 6 * 10:02d}:00+00:00"} for i in range(1, 100)]
                states.append({"state": "unavailable", "last_changed": "2026-11-19T23:00:00+00:00"})
                return self.reply(200, [states])
            if url.path == "/api/error_log":
                return self.reply(200, ERROR_LOG, "text/plain")
            if url.path == "/api/calendars":
                return self.reply(200, [{"entity_id": "calendar.family", "name": "Family"},
                                        {"entity_id": "calendar.bins", "name": "Bins"}])
            if url.path == "/api/calendars/calendar.family":
                return self.reply(200, [{"summary": "Dentist", "start": {"dateTime": "2026-11-21T10:30:00+00:00"}}])
            if url.path == "/api/calendars/calendar.bins":
                return self.reply(200, [{"summary": "Recycling", "start": {"date": "2026-11-20"}}])
            self.reply(404, {"message": "Not found"})

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield HomeAssistant(f"http://127.0.0.1:{server.server_port}", "token", "", blocked_domains=["lock"]), seen
    server.shutdown()


# ---------------------------------------------------------------- logbook

def test_logbook_hides_the_lock(ha):
    home, seen = ha
    entries = home.logbook(24)
    assert [e["name"] for e in entries] == ["Desk Lamp", "Morning lights"]
    assert "+" not in seen[0]  # the time's '+' was escaped, or HA would read it as a space


def test_logbook_for_a_blocked_entity_pretends_it_doesnt_exist(ha):
    home, seen = ha
    with pytest.raises(HomeAssistantError, match="No entity"):
        home.logbook(24, "lock.front_door")
    assert seen == []  # it didn't even ask HA


def test_logbook_for_one_entity(ha):
    home, seen = ha
    assert [e["entity_id"] for e in home.logbook(24, "light.desk_lamp")] == ["light.desk_lamp"]
    assert "entity=light.desk_lamp" in seen[0]


# ---------------------------------------------------------------- history

def test_history_sums_up_numbers_and_thins_out(ha):
    home, _ = ha
    h = home.history("sensor.lounge_temperature", 24)
    assert h["number_of_changes"] == 101
    assert len(h["changes"]) == 40 and h["changes"][-1][1] == "unavailable"  # the newest is always kept
    assert h["summary"] == {"lowest": 16.0, "highest": 20.0, "average": pytest.approx(h["summary"]["average"])}
    assert 16 <= h["summary"]["average"] <= 20


def test_history_of_a_lock_is_refused(ha):
    home, _ = ha
    with pytest.raises(HomeAssistantError):
        home.history("lock.front_door", 24)


# ---------------------------------------------------------------- error log

def test_error_log_hides_secrets_and_locks(ha):
    home, _ = ha
    log = home.error_log()
    assert "Bridge slow" in log
    assert "hunter2" not in log and "eyJabc" not in log and "[hidden]" in log
    assert "front_door" not in log


def test_error_log_search(ha):
    home, _ = ha
    assert home.error_log("hue").splitlines() == [
        "2026-11-19 08:00:00 WARNING (MainThread) [homeassistant.components.hue] Bridge slow to answer"]


# ---------------------------------------------------------------- calendars

def test_calendar_events_from_all_calendars_soonest_first(ha):
    home, _ = ha
    events = home.calendar_events(7)
    assert [(e["summary"], e["all_day"]) for e in events] == [("Recycling", True), ("Dentist", False)]
    assert events[0]["start"] == "2026-11-20"


def test_blocked_calendar(ha):
    home, _ = ha
    home.blocked.add("calendar")
    assert home.calendars() == []
    with pytest.raises(HomeAssistantError):
        home.calendar_events(7, "calendar.family")


# ---------------------------------------------------------------- Bolt's tools

def test_bolt_can_use_the_reading_tools(ha, tmp_path):
    home, _ = ha
    brain = Brain(client=None, reminders=ReminderStore(tmp_path / "r.json"), home=home)
    assert "Morning lights" in brain.run_tool("home_logbook", {"hours": 24, "entity_id": ""})
    assert '"lowest": 16.0' in brain.run_tool("home_history", {"entity_id": "sensor.lounge_temperature", "hours": 24})
    assert "Bridge slow" in brain.run_tool("home_error_log", {"search": "", "lines": 40})
    assert "Dentist" in brain.run_tool("calendar_events", {"days": 7, "calendar": ""})
    assert brain.run_tool("home_history", {"entity_id": "lock.front_door", "hours": 24}).startswith("Error")


def test_tools_say_when_home_assistant_isnt_set_up(tmp_path):
    brain = Brain(client=None, reminders=ReminderStore(tmp_path / "r.json"), home=HomeAssistant("", "", ""))
    assert "isn't set up" in brain.run_tool("calendar_events", {"days": 7, "calendar": ""})
