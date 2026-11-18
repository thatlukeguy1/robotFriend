"""
LESSON: Talking to Home Assistant
=================================
Home Assistant (HA) has its own API, just like Bolt's server does. Other
programs can send it requests like "please run the notify action".

To prove we're allowed, every request carries an ACCESS TOKEN: a long secret
password that you create inside HA. It goes in a request HEADER called
"Authorization". Anyone with the token can control your home, so it lives only
in your .env file: never in the code, never on GitHub, never in a chat.

The request we send to make your phone buzz looks like this:

    POST http://192.168.4.58:8123/api/services/notify/mobile_app_your_phone
    Authorization: Bearer <your token>
    {"title": "Bolt", "message": "Hey! Reminder: drink water"}

Try it yourself (inside the container) with:
    docker exec robot-brain python -m robot_friend.home_assistant "Hello from Bolt!"
"""

import json
import os
import sys
import urllib.error
import urllib.request

from .personality import ROBOT_NAME


class HomeAssistant:
    def __init__(self, url=None, token=None, notify_service=None):
        self.url = (url or os.environ.get("HA_URL", "")).rstrip("/")
        self.token = token or os.environ.get("HA_TOKEN", "")
        # e.g. "mobile_app_lukes_phone"; we accept it with or without "notify."
        service = notify_service or os.environ.get("HA_NOTIFY", "")
        self.notify_service = service.removeprefix("notify.")

    @property
    def enabled(self):
        """True only if all three settings are filled in."""
        return bool(self.url and self.token and self.notify_service)

    def notify(self, message, title=ROBOT_NAME):
        """Send a notification to your phone. Returns (worked?, explanation)."""
        if not self.enabled:
            return False, "Home Assistant isn't set up (HA_URL, HA_TOKEN and HA_NOTIFY in .env)."

        request = urllib.request.Request(
            f"{self.url}/api/services/notify/{self.notify_service}",
            data=json.dumps({"title": title, "message": message}).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            # timeout=10: if HA doesn't answer in 10 seconds, give up instead of hanging.
            with urllib.request.urlopen(request, timeout=10):
                return True, "Sent!"
        # Turn confusing errors into plain English.
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "HA said 401: the token is wrong or was deleted. Make a new one."
            if e.code in (400, 404):
                return False, (f"HA said {e.code}: it doesn't know the action notify.{self.notify_service}. "
                               "Check HA_NOTIFY (Developer tools → Actions → search 'notify').")
            return False, f"HA said error {e.code}."
        except (urllib.error.URLError, OSError) as e:
            return False, f"Couldn't reach Home Assistant at {self.url} ({getattr(e, 'reason', e)}). Check HA_URL."


if __name__ == "__main__":
    # Lets you send a test message:  python -m robot_friend.home_assistant "hi"
    ha = HomeAssistant()
    worked, explanation = ha.notify(" ".join(sys.argv[1:]) or f"Hello from {ROBOT_NAME}!")
    print(("✅ " if worked else "❌ ") + explanation)
    sys.exit(0 if worked else 1)
