"""
Tests for the check-before-running rule: automations, scripts and scenes that
(directly or deep inside) touch a lock must never run.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from robot_friend.brain import Brain
from robot_friend.home_assistant import HomeAssistant, HomeAssistantError
from robot_friend.reminders import ReminderStore

STATES = {
    "automation.morning": {"id": "1001"},
    "automation.leaving": {"id": "1002"},
    "automation.from_yaml": {},  # no id: written in a YAML file
    "automation.calls_bad_script": {"id": "1003"},
    "automation.device_unlock": {"id": "1004"},
    "scene.movie": {"id": "2001"},
    "scene.welcome_home": {"id": "2002"},
    "script.bedtime": {},
    "script.loop": {},
    "script.goodbye": {},
    # the back doors: a night-time lock automation, and an "away" one set off by a helper
    "automation.night_lock": {"id": "1005"},
    "automation.away_unlock": {"id": "1006"},
    "automation.device_trigger": {"id": "1007"},
    "input_boolean.away_mode": {},
    "light.porch": {},
    "switch.doorbell_button": {},
    "light.desk_lamp": {},
    "script.going_out": {},
}
CONFIGS = {
    "/api/config/automation/config/1001": {"triggers": [{"trigger": "time", "at": "07:00"}],
                                           "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.desk_lamp"}}]},
    "/api/config/automation/config/1002": {"actions": [{"action": "light.turn_off", "target": {"area_id": "lounge"}},
                                                       {"action": "lock.lock", "target": {"entity_id": "lock.front_door"}}]},
    "/api/config/automation/config/1003": {"actions": [{"action": "script.turn_on", "target": {"entity_id": "script.goodbye"}}]},
    "/api/config/automation/config/1004": {"actions": [{"device_id": "abc", "domain": "lock", "type": "unlock"}]},
    "/api/config/scene/config/2001": {"entities": {"light.lounge_ceiling": {"state": "on", "brightness": 40}}},
    "/api/config/scene/config/2002": {"entities": {"light.hall": {"state": "on"}, "lock.front_door": {"state": "unlocked"}}},
    "/api/config/script/config/bedtime": {"sequence": [{"action": "scene.turn_on", "target": {"entity_id": "scene.movie"}},
                                                       {"action": "script.loop"}]},
    "/api/config/script/config/loop": {"sequence": [{"action": "script.bedtime"}]},  # calls back: must not loop forever
    "/api/config/automation/config/1005": {"triggers": [{"trigger": "time", "at": "23:00"}],
                                           "conditions": [{"condition": "state", "entity_id": "light.porch", "state": "off"}],
                                           "actions": [{"action": "lock.lock", "target": {"entity_id": "lock.front_door"}}]},
    "/api/config/automation/config/1006": {"triggers": [{"trigger": "state", "entity_id": "input_boolean.away_mode", "to": "off"}],
                                           "actions": [{"action": "lock.unlock", "target": {"entity_id": "lock.front_door"}}]},
    "/api/config/automation/config/1007": {"triggers": [{"trigger": "device", "device_id": "abc123def456", "domain": "switch", "type": "turned_on"}],
                                           "actions": [{"device_id": "999", "domain": "lock", "type": "unlock"}]},
    # looks harmless, but flips away_mode, which sets off away_unlock
    "/api/config/script/config/going_out": {"sequence": [{"action": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.away_mode"}}]},
    "/api/config/script/config/goodbye": {"sequence": [{"action": "scene.turn_on", "target": {"entity_id": "scene.welcome_home"}}]},
}


@pytest.fixture
def ha():
    posts = []

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code); self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            if self.path == "/api/states":
                return self.reply(200, [{"entity_id": k, "state": "on", "attributes": v} for k, v in STATES.items()])
            if self.path in CONFIGS:
                return self.reply(200, CONFIGS[self.path])
            entity_id = self.path.removeprefix("/api/states/")
            if entity_id in STATES:
                return self.reply(200, {"entity_id": entity_id, "state": "on", "attributes": STATES[entity_id]})
            self.reply(404, {"message": "Not found"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            if self.path == "/api/template":  # "which entities does device abc123def456 have?"
                answer = b"switch.doorbell_button,sensor.doorbell_battery" if "abc123def456" in body["template"] else b""
                self.send_response(200); self.send_header("content-length", str(len(answer))); self.end_headers()
                return self.wfile.write(answer)
            posts.append(self.path)
            self.reply(200, [{"entity_id": e, "state": "on"} for e in body["entity_id"]])

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield HomeAssistant(f"http://127.0.0.1:{server.server_port}", "token", "", blocked_domains=["lock"]), posts
    server.shutdown()


# ------------------------------------------------------------ allowed

def test_a_safe_automation_runs(ha):
    home, posts = ha
    home.call_service("automation", "trigger", ["automation.morning"])
    assert posts == ["/api/services/automation/trigger"]


def test_a_safe_script_runs_even_though_it_calls_back_to_itself(ha):
    home, posts = ha
    home.call_service("script", "turn_on", ["script.bedtime"])  # bedtime -> loop -> bedtime...
    assert posts == ["/api/services/script/turn_on"]


def test_switching_a_safe_automation_off_is_fine(ha):
    home, posts = ha
    home.call_service("automation", "turn_off", ["automation.morning"])
    assert posts == ["/api/services/automation/turn_off"]


def test_ordinary_lights_still_work(ha):
    home, posts = ha
    home.call_service("light", "turn_on", ["light.desk_lamp"], {"brightness_pct": 40})
    assert posts == ["/api/services/light/turn_on"]


# ------------------------------------------------------------ the back doors

def test_cant_switch_off_the_night_lock(ha):
    home, posts = ha
    with pytest.raises(HomeAssistantError, match="isn't allowed"):
        home.call_service("automation", "turn_off", ["automation.night_lock"])
    assert posts == []


def test_lock_automations_are_hidden_from_searches(ha):
    home, _ = ha
    found = {e["entity_id"] for e in home.find_entities("", "automation")}
    assert "automation.morning" in found
    assert not found & {"automation.night_lock", "automation.away_unlock", "automation.leaving", "automation.from_yaml"}


@pytest.mark.parametrize("domain, action, entity_id", [
    ("input_boolean", "turn_off", "input_boolean.away_mode"),  # a trigger of away_unlock
    ("light", "turn_on", "light.porch"),                       # a condition of night_lock
    ("switch", "turn_on", "switch.doorbell_button"),           # a DEVICE trigger, found by asking HA
])
def test_cant_change_what_a_lock_automation_watches(ha, domain, action, entity_id):
    home, posts = ha
    with pytest.raises(HomeAssistantError, match="could set off"):
        home.call_service(domain, action, [entity_id])
    assert posts == []
    assert any(e.get("read_only") for e in home.find_entities(entity_id.split(".")[1].replace("_", " ")))


def test_a_harmless_looking_script_that_flips_a_watched_helper_is_hidden(ha):
    home, posts = ha
    with pytest.raises(HomeAssistantError, match="isn't allowed"):
        home.call_service("script", "turn_on", ["script.going_out"])
    assert posts == []


def test_no_sneaking_round_by_area(ha):
    home, posts = ha
    with pytest.raises(HomeAssistantError, match="areas"):
        home.call_service("light", "turn_on", ["light.desk_lamp"], {"area_id": "porch"})
    assert posts == []


def test_protected_list_is_remembered_for_a_while(ha):
    home, _ = ha
    first = home.protection()
    assert home.protection() is not None and home._protected is first[0]  # no second trip to HA


# ------------------------------------------------------------ refused (and nothing was sent)

@pytest.mark.parametrize("domain, entity_id, reason", [
    ("automation", "automation.leaving", "isn't allowed"),         # says lock.lock right there
    ("automation", "automation.device_unlock", "isn't allowed"),   # a device action for a lock
    ("automation", "automation.calls_bad_script", "isn't allowed"),  # automation -> script -> scene -> lock
    ("scene", "scene.welcome_home", "isn't allowed"),              # a scene that sets a lock
    ("automation", "automation.from_yaml", "can't check"),         # can't check it, so won't run it
    ("script", "script.not_in_editor", "couldn't read"),
])
def test_refused(ha, domain, entity_id, reason):
    home, posts = ha
    action = "trigger" if domain == "automation" else "turn_on"
    with pytest.raises(HomeAssistantError, match=reason):
        home.call_service(domain, action, [entity_id])
    assert posts == []


def test_only_known_actions_for_runners(ha):
    home, posts = ha
    # "script.bedtime" as an ACTION would run bedtime, whatever entity it's pointed at
    with pytest.raises(HomeAssistantError, match="can only use"):
        home.call_service("script", "bedtime", ["script.loop"])
    with pytest.raises(HomeAssistantError, match="can only use"):
        home.call_service("scene", "apply", ["scene.movie"])  # apply sets ANY states you give it
    assert posts == []


def test_settings_cant_smuggle_in_a_lock(ha):
    home, posts = ha
    with pytest.raises(HomeAssistantError, match="isn't allowed"):
        home.call_service("script", "turn_on", ["script.bedtime"], {"variables": {"door": "lock.front_door"}})
    assert posts == []


def test_bolt_hears_why(ha, tmp_path):
    home, _ = ha
    brain = Brain(client=None, reminders=ReminderStore(tmp_path / "r.json"), home=home)
    said = brain.run_tool("control_device", {"domain": "automation", "action": "trigger",
                                             "entity_ids": ["automation.leaving"], "data_json": "{}"})
    assert said.startswith("Error") and "won't run it" in said and "lock" in said
