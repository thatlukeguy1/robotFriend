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
            if self.path in CONFIGS:
                return self.reply(200, CONFIGS[self.path])
            entity_id = self.path.removeprefix("/api/states/")
            if entity_id in STATES:
                return self.reply(200, {"entity_id": entity_id, "state": "on", "attributes": STATES[entity_id]})
            self.reply(404, {"message": "Not found"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
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


def test_switching_a_lock_automation_off_is_always_fine(ha):
    home, posts = ha
    home.call_service("automation", "turn_off", ["automation.leaving"])
    assert posts == ["/api/services/automation/turn_off"]


# ------------------------------------------------------------ refused (and nothing was sent)

@pytest.mark.parametrize("domain, entity_id, reason", [
    ("automation", "automation.leaving", "isn't allowed"),         # says lock.lock right there
    ("automation", "automation.device_unlock", "isn't allowed"),   # a device action for a lock
    ("automation", "automation.calls_bad_script", "isn't allowed"),  # automation -> script -> scene -> lock
    ("scene", "scene.welcome_home", "isn't allowed"),              # a scene that sets a lock
    ("automation", "automation.from_yaml", "editor"),              # can't check it, so won't run it
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
    assert said.startswith("Error") and "won't run it" in said
