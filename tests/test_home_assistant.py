"""Tests for phone notifications, using a pretend Home Assistant server."""

import json
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from robot_friend.home_assistant import HomeAssistant
from robot_friend.reminders import ReminderStore
from server import Notifications, alarm_clock


@pytest.fixture
def fake_ha():
    """Starts a tiny pretend Home Assistant that records what it's sent."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            seen.append({"path": self.path, "auth": self.headers["Authorization"], "body": body})
            if self.headers["Authorization"] != "Bearer good-token":
                self.send_response(401)
            elif self.path != "/api/services/notify/mobile_app_phone":
                self.send_response(400)
            else:
                self.send_response(200)
            self.end_headers()
            self.wfile.write(b"[]")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()


def test_sends_notification(fake_ha):
    url, seen = fake_ha
    worked, _ = HomeAssistant(url, "good-token", "notify.mobile_app_phone").notify("hi")
    assert worked
    assert seen[0]["body"] == {"title": "Bolt", "message": "hi"}
    assert seen[0]["auth"] == "Bearer good-token"


def test_explains_bad_token(fake_ha):
    url, _ = fake_ha
    worked, why = HomeAssistant(url, "wrong", "mobile_app_phone").notify("hi")
    assert not worked and "token" in why


def test_explains_wrong_service(fake_ha):
    url, _ = fake_ha
    worked, why = HomeAssistant(url, "good-token", "mobile_app_typo").notify("hi")
    assert not worked and "HA_NOTIFY" in why


def test_explains_unreachable():
    worked, why = HomeAssistant("http://127.0.0.1:1", "t", "x").notify("hi")
    assert not worked and "HA_URL" in why


def test_disabled_when_not_set_up(monkeypatch):
    for name in ("HA_URL", "HA_TOKEN", "HA_NOTIFY"):
        monkeypatch.delenv(name, raising=False)
    assert HomeAssistant().enabled is False


def test_alarm_clock_buzzes_phone(fake_ha, tmp_path):
    url, seen = fake_ha
    store = ReminderStore(tmp_path / "r.json")
    store.add("tea", (datetime.now() - timedelta(minutes=1)).isoformat(timespec="minutes"))

    class StopAfterOne:
        def __init__(self): self.n = 0
        def is_set(self): self.n += 1; return self.n > 1
        def wait(self, _): pass

    alarm_clock(store, Notifications(), StopAfterOne(), HomeAssistant(url, "good-token", "mobile_app_phone"))
    assert seen[0]["body"]["message"] == "Hey! Reminder: tea"
