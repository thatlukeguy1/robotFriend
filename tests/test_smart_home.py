"""
Tests for smart home control, using a pretend Home Assistant.
Most of these check the SAFETY rules: blocked devices must be invisible and untouchable.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from robot_friend.brain import Brain
from robot_friend.home_assistant import HomeAssistant, HomeAssistantError
from robot_friend.reminders import ReminderStore

STATES = {
    "light.desk_lamp": {"state": "off", "attributes": {"friendly_name": "Desk Lamp"}},
    "light.lounge_ceiling": {"state": "on", "attributes": {"friendly_name": "Lounge Ceiling", "brightness": 200}},
    "sensor.lounge_temperature": {"state": "20.5", "attributes": {"friendly_name": "Lounge Temperature", "unit_of_measurement": "°C"}},
    "lock.front_door": {"state": "locked", "attributes": {"friendly_name": "Front Door"}},
}


@pytest.fixture
def ha():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code); self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            if self.path == "/api/states":
                return self.reply(200, [{"entity_id": k, **v} for k, v in STATES.items()])
            entity_id = self.path.removeprefix("/api/states/")
            if entity_id in STATES:
                return self.reply(200, {"entity_id": entity_id, **STATES[entity_id]})
            self.reply(404, {"message": "Entity not found."})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            calls.append({"path": self.path, "body": body})
            self.reply(200, [{"entity_id": e, "state": "on"} for e in body["entity_id"]])

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield HomeAssistant(f"http://127.0.0.1:{server.server_port}", "token", "", blocked_domains=["lock"]), calls
    server.shutdown()


# ---------------------------------------------------------------- it works

def test_find_by_words(ha):
    home, _ = ha
    assert [e["entity_id"] for e in home.find_entities("lounge temp")] == ["sensor.lounge_temperature"]


def test_find_by_domain(ha):
    home, _ = ha
    assert {e["entity_id"] for e in home.find_entities("", "light")} == {"light.desk_lamp", "light.lounge_ceiling"}


def test_get_state(ha):
    home, _ = ha
    assert home.get_state("sensor.lounge_temperature")["state"] == "20.5"


def test_turn_on_with_data(ha):
    home, calls = ha
    home.call_service("light", "turn_on", ["light.desk_lamp"], {"brightness_pct": 40})
    assert calls[0] == {"path": "/api/services/light/turn_on",
                        "body": {"brightness_pct": 40, "entity_id": ["light.desk_lamp"]}}


# ------------------------------------------------------- the safety rules

def test_locks_are_invisible(ha):
    home, _ = ha
    assert all(not e["entity_id"].startswith("lock.") for e in home.find_entities(""))
    assert home.find_entities("front door") == []


def test_cannot_read_a_lock(ha):
    home, _ = ha
    with pytest.raises(HomeAssistantError, match="No entity"):
        home.get_state("lock.front_door")


@pytest.mark.parametrize("domain, action, entity", [
    ("lock", "unlock", "lock.front_door"),               # the obvious way
    ("homeassistant", "turn_off", "lock.front_door"),    # a generic action
    ("light", "turn_on", "lock.front_door"),             # wrong domain on purpose
    ("homeassistant", "turn_off", "light.desk_lamp"),    # generic actions aren't allowed at all
])
def test_sneaky_routes_are_refused(ha, domain, action, entity):
    home, calls = ha
    with pytest.raises(HomeAssistantError):
        home.call_service(domain, action, [entity])
    assert calls == []  # nothing was ever sent to Home Assistant


def test_one_blocked_entity_stops_the_whole_action(ha):
    home, calls = ha
    with pytest.raises(HomeAssistantError):
        home.call_service("light", "turn_on", ["light.desk_lamp", "lock.front_door"])
    assert calls == []


def test_blocked_domains_from_env(monkeypatch):
    monkeypatch.setenv("HA_BLOCKED_DOMAINS", "lock, alarm_control_panel ,cover")
    assert HomeAssistant().blocked == {"lock", "alarm_control_panel", "cover"}


def test_locks_blocked_by_default(monkeypatch):
    monkeypatch.delenv("HA_BLOCKED_DOMAINS", raising=False)
    assert HomeAssistant().blocked == {"lock"}


# ----------------------------------------------------- through Bolt's brain

def test_brain_tools(ha, tmp_path):
    home, calls = ha
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=object(), home=home)
    assert "light.desk_lamp" in brain.run_tool("find_devices", {"search": "desk", "domain": ""})
    assert "Done" in brain.run_tool("control_device", {"domain": "light", "action": "turn_on",
                                                       "entity_ids": ["light.desk_lamp"], "data_json": "{}"})
    refused = brain.run_tool("control_device", {"domain": "lock", "action": "unlock",
                                                "entity_ids": ["lock.front_door"], "data_json": "{}"})
    assert refused.startswith("Error") and len(calls) == 1
    assert "valid JSON" in brain.run_tool("control_device", {"domain": "light", "action": "turn_on",
                                                             "entity_ids": ["light.desk_lamp"], "data_json": "{oops"})


def test_brain_without_home_assistant(tmp_path):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=object(), home=None)
    assert "isn't set up" in brain.run_tool("find_devices", {"search": "", "domain": ""})
