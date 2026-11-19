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

LESSON: Controlling the home, safely
====================================
Bolt gets three tools: find devices, read a device, and run an "action"
(HA calls these services: light.turn_on, climate.set_temperature...).

Every entity ID starts with its DOMAIN: the kind of thing it is
(light.desk_lamp, lock.front_door, sensor.lounge_temperature).
HA_BLOCKED_DOMAINS in .env lists domains Bolt may never see or touch.
The check happens HERE, in our Python code, not in Claude's instructions,
so even if Bolt gets confused (or someone tries to trick it), a blocked
device simply doesn't exist as far as it can tell.

LESSON: Reading what happened (logs, history, calendars)
========================================================
Controlling things is about NOW. Bolt can also look BACK and AHEAD:

  * LOGBOOK: a diary HA keeps: "Back door opened at 15:02".
  * HISTORY: every value a sensor had, so Bolt can answer
    "how cold did the lounge get last night?"
  * ERROR LOG: HA's own complaints, for "why didn't my automation run?".
    (HA only shows this to ADMIN users, so the token must belong to one.)
  * CALENDARS: upcoming events from any calendar HA knows about.

These are all READ-ONLY: looking never changes anything. The same blocked
domains apply: a lock's diary entries are hidden too, otherwise Bolt could
learn about the front door by reading the logbook instead.

Everything Bolt reads gets sent to Claude so it can understand it, so we
trim long logs and blank out anything that looks like a password or token.

Try it yourself (inside the container) with:
    docker exec bolt python -m robot_friend.home_assistant "Hello from Bolt!"
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from .personality import ROBOT_NAME


class HomeAssistantError(Exception):
    """Home Assistant said no, or couldn't be reached."""


class HomeAssistant:
    def __init__(self, url=None, token=None, notify_service=None, blocked_domains=None):
        self.url = (url or os.environ.get("HA_URL", "")).rstrip("/")
        self.token = token or os.environ.get("HA_TOKEN", "")
        # e.g. "mobile_app_lukes_phone"; we accept it with or without "notify."
        service = notify_service or os.environ.get("HA_NOTIFY", "")
        self.notify_service = service.removeprefix("notify.")
        # Domains Bolt may never see or control, e.g. "lock,alarm_control_panel"
        if blocked_domains is None:
            blocked_domains = os.environ.get("HA_BLOCKED_DOMAINS", "lock").split(",")
        self.blocked = {d.strip() for d in blocked_domains if d.strip()}

    @property
    def can_control(self):
        """True if Bolt has what it needs to read and control devices."""
        return bool(self.url and self.token)

    def is_blocked(self, entity_id):
        return entity_id.split(".", 1)[0] in self.blocked

    # ------------------------------------------------- talking to HA's API

    def _request(self, method, path, body=None, text=False):
        """Send one request to HA and return its JSON answer (or raise HomeAssistantError).
        text=True returns the answer as plain text instead (the error log isn't JSON)."""
        request = urllib.request.Request(
            f"{self.url}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                answer = response.read()
                return answer.decode(errors="replace") if text else json.loads(answer or b"null")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:200]
            if e.code == 401 and text:
                raise HomeAssistantError("HA said 401: the error log needs a token made by an ADMIN user.") from e
            if e.code == 401:
                raise HomeAssistantError("HA said 401: the token is wrong or was deleted.") from e
            if e.code == 404:
                raise HomeAssistantError("HA said 404: no such entity or action.") from e
            raise HomeAssistantError(f"HA said error {e.code}: {detail}") from e
        except (urllib.error.URLError, OSError) as e:
            raise HomeAssistantError(f"Couldn't reach Home Assistant at {self.url}.") from e

    # ------------------------------------------------- Bolt's three tools

    def find_entities(self, search="", domain=""):
        """List devices whose name or ID contains `search` (blocked ones are hidden)."""
        words = search.lower().split()
        found = []
        for e in self._request("GET", "/api/states"):
            entity_id = e["entity_id"]
            name = e.get("attributes", {}).get("friendly_name", "")
            if self.is_blocked(entity_id):
                continue
            if domain and not entity_id.startswith(domain + "."):
                continue
            haystack = f"{entity_id} {name}".lower().replace("_", " ")
            if all(w in haystack for w in words):
                found.append({"entity_id": entity_id, "name": name, "state": e["state"]})
        return found

    def get_state(self, entity_id):
        if self.is_blocked(entity_id):
            raise HomeAssistantError(f"No entity called {entity_id}.")  # pretend it doesn't exist
        e = self._request("GET", f"/api/states/{entity_id}")
        return {"entity_id": e["entity_id"], "state": e["state"], "attributes": e.get("attributes", {})}

    def call_service(self, domain, service, entity_ids, data=None):
        """Run an action, e.g. light.turn_on, on one or more entities."""
        if not entity_ids:
            raise HomeAssistantError("Say which entity_ids to act on.")
        if domain in self.blocked:
            raise HomeAssistantError(f"Bolt isn't allowed to use {domain} actions.")
        for entity_id in entity_ids:
            if self.is_blocked(entity_id):
                raise HomeAssistantError(f"No entity called {entity_id}.")
            # The action's domain must match the entity's domain (light.turn_on -> light.*).
            # This stops sneaky routes like homeassistant.turn_on on a blocked device.
            if not entity_id.startswith(domain + "."):
                raise HomeAssistantError(f"{domain}.{service} can only be used on {domain}.* entities.")
        changed = self._request("POST", f"/api/services/{domain}/{service}",
                                {**(data or {}), "entity_id": entity_ids})
        return [{"entity_id": c["entity_id"], "state": c["state"]} for c in changed or []]

    # ------------------------------------------------- looking back and ahead

    def logbook(self, hours=24, entity_id=""):
        """What happened recently: [{"when", "name", "message", "entity_id"}], oldest first."""
        if entity_id and self.is_blocked(entity_id):
            raise HomeAssistantError(f"No entity called {entity_id}.")
        end = datetime.now().astimezone()
        path = f"/api/logbook/{_iso(end - timedelta(hours=_hours(hours)))}?end_time={_iso(end, query=True)}"
        if entity_id:
            path += "&entity=" + urllib.parse.quote(entity_id)
        entries = []
        for e in self._request("GET", path) or []:
            about = e.get("entity_id") or ""
            if (about and self.is_blocked(about)) or e.get("domain") in self.blocked:
                continue  # blocked devices have no diary either
            entries.append({"when": _local(e.get("when")), "name": e.get("name", ""),
                            "message": e.get("message") or e.get("state") or "", "entity_id": about})
        return entries

    def history(self, entity_id, hours=24):
        """How one entity changed: {"entity_id", "changes": [[when, state]...], "summary": {...}}."""
        if self.is_blocked(entity_id):
            raise HomeAssistantError(f"No entity called {entity_id}.")
        end = datetime.now().astimezone()
        path = (f"/api/history/period/{_iso(end - timedelta(hours=_hours(hours)))}"
                f"?end_time={_iso(end, query=True)}&filter_entity_id={urllib.parse.quote(entity_id)}"
                "&minimal_response&no_attributes")
        found = self._request("GET", path) or []
        points = [[_local(p.get("last_changed")), p.get("state")] for p in (found[0] if found else [])]
        result = {"entity_id": entity_id, "hours": _hours(hours), "number_of_changes": len(points)}
        numbers = [float(state) for _, state in points if _is_number(state)]
        if numbers:
            result["summary"] = {"lowest": min(numbers), "highest": max(numbers),
                                 "average": round(sum(numbers) / len(numbers), 2)}
        if len(points) > 40:
            # Too many to read out: keep 40 evenly spaced ones (always including the last).
            step = len(points) / 40
            points = [points[int(i * step)] for i in range(39)] + [points[-1]]
            result["note"] = "Thinned out to 40 evenly spaced readings."
        result["changes"] = points
        return result

    def error_log(self, search="", lines=60):
        """The newest lines of HA's error log (matching `search`), with secrets blanked out."""
        text = self._request("GET", "/api/error_log", text=True)
        words = search.lower().split()
        kept = []
        for line in text.splitlines():
            if any(f"{domain}." in line for domain in self.blocked):
                continue  # don't let the log leak blocked devices
            if all(w in line.lower() for w in words):
                kept.append(_redact(line))
        kept = kept[-max(1, min(lines, 150)):]
        joined = "\n".join(kept)
        return joined[-8000:]  # keep the end (the newest) if it's very long

    def calendars(self):
        return [c for c in self._request("GET", "/api/calendars") or [] if not self.is_blocked(c["entity_id"])]

    def calendar_events(self, days=7, calendar=""):
        """Upcoming events from one calendar (or all of them), soonest first."""
        if calendar and self.is_blocked(calendar):
            raise HomeAssistantError(f"No calendar called {calendar}.")
        chosen = [{"entity_id": calendar, "name": calendar}] if calendar else self.calendars()
        start = datetime.now().astimezone()
        end = start + timedelta(days=max(1, min(int(days), 60)))
        events = []
        for c in chosen:
            path = (f"/api/calendars/{urllib.parse.quote(c['entity_id'])}"
                    f"?start={_iso(start, query=True)}&end={_iso(end, query=True)}")
            for e in self._request("GET", path) or []:
                begins = e.get("start", {})
                events.append({"calendar": c.get("name") or c["entity_id"], "summary": e.get("summary", ""),
                               "start": _local(begins.get("dateTime")) if "dateTime" in begins else begins.get("date", ""),
                               "all_day": "dateTime" not in begins,
                               "location": e.get("location") or "", "_sort": begins.get("dateTime") or begins.get("date", "")})
        events.sort(key=lambda e: e.pop("_sort"))
        return events

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


# ------------------------------------------------- little helpers

SECRETS = [
    re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"),                     # access tokens (JWTs)
    re.compile(r"(?i)(bearer\s+)\S+"),                               # Authorization: Bearer ...
    re.compile(r"(?i)((?:password|passwd|token|api_key|apikey|secret)[\"']?\s*[:=]\s*)[\"']?[^\s,\"'}]+"),
]


def _redact(line):
    for pattern in SECRETS:
        line = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[hidden]", line)
    return line


def _hours(hours):
    return max(1, min(int(hours), 24 * 14))  # between 1 hour and 2 weeks


def _iso(moment, query=False):
    """A time the way HA's API wants it. '+' must be escaped or it turns into a space."""
    return urllib.parse.quote(moment.isoformat(timespec="seconds"), safe=":" if not query else "")


def _local(stamp):
    """'2026-11-19T14:05:00+00:00' -> 'Thu 19 Nov 14:05' in our own time zone."""
    if not stamp:
        return ""
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().strftime("%a %d %b %H:%M")
    except ValueError:
        return stamp


def _is_number(state):
    try:
        float(state)
        return True
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    # Lets you send a test message:  python -m robot_friend.home_assistant "hi"
    ha = HomeAssistant()
    worked, explanation = ha.notify(" ".join(sys.argv[1:]) or f"Hello from {ROBOT_NAME}!")
    print(("✅ " if worked else "❌ ") + explanation)
    sys.exit(0 if worked else 1)
