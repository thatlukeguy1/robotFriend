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

LESSON: Automations, scripts and scenes: checking before running
===============================================================
Blocking lock.* isn't enough on its own. An automation, script or scene
can CONTAIN "unlock the front door", and running it would get round the
block. So before Bolt runs one, we fetch its recipe from HA (its "config")
and read every step:

  * a step that uses a blocked domain (lock.unlock, lock.front_door,
    or a device action for a lock)? Refuse.
  * a step that runs ANOTHER script, scene or automation? Check that one
    too (and so on, however deep it goes).
  * can't read the recipe (it was written in a YAML file, not HA's editor)?
    Refuse: if we can't check it, we don't run it.

LESSON: Closing the back doors
==============================
Checking before running still leaves two sneaky routes to a lock:

  1. SWITCHING OFF the automation that locks the door every night.
  2. SETTING IT OFF INDIRECTLY: if "unlock the door" runs when
     input_boolean.away_mode changes, Bolt could just flip away_mode.

So Bolt makes a PROTECTED LIST (see protection() below):

  * Any automation, script or scene that touches a lock, or that Bolt
    can't read, is treated like a lock itself: hidden, untouchable.
  * Everything those automations WATCH (their triggers and conditions)
    becomes READ-ONLY: Bolt can tell you the porch light is on, but
    can't switch it, because that could set the lock automation off.
  * Then it goes round again: a "harmless" script that flips away_mode
    is now dangerous too, so it joins the list, and so on, until nothing
    new turns up. (Programmers call this finding a FIXED POINT.)

Working all that out takes a request for every automation, so Bolt
remembers the answer for a few minutes (a CACHE) instead of asking HA
every single time.

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
import time
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
        self._protected = None  # {entity_id: why Bolt can't touch it}, see protection()
        self._read_only = None  # {entity_id: why Bolt can't change it}
        self._protected_at = 0.0

    @property
    def can_control(self):
        """True if Bolt has what it needs to read and control devices."""
        return bool(self.url and self.token)

    def is_blocked(self, entity_id):
        """Is this in a blocked DOMAIN (e.g. any lock.*)? Quick: no need to ask HA."""
        return entity_id.split(".", 1)[0] in self.blocked

    def is_hidden(self, entity_id):
        """Blocked, or an automation/script/scene on the protected list."""
        return self.is_blocked(entity_id) or entity_id in self.protection()[0]

    def _refuse_if_hidden(self, entity_id):
        # LESSON: check the SHAPE before anything else. An id like "light.x/../lock.door"
        # looks like a light to the checks below, but Home Assistant's web server tidies
        # the "/../" away and hands back the lock. A real entity id is only lowercase
        # letters, numbers and _ either side of one dot, so anything else is refused.
        if not isinstance(entity_id, str) or not VALID_ENTITY.fullmatch(entity_id):
            raise HomeAssistantError(f"{str(entity_id)[:60]!r} isn't an entity id (they look like light.kitchen).")
        if self.is_blocked(entity_id):
            raise HomeAssistantError(f"No entity called {entity_id}.")  # pretend it doesn't exist
        why = self.protection()[0].get(entity_id)
        if why:
            raise HomeAssistantError(why)

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
                raise HomeAssistantError("HA said 401: this needs a token made by an ADMIN user.") from e
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
        hidden, read_only = self.protection()
        for e in self._request("GET", "/api/states"):
            entity_id = e["entity_id"]
            name = e.get("attributes", {}).get("friendly_name", "")
            if self.is_blocked(entity_id) or entity_id in hidden:
                continue
            if domain and not entity_id.startswith(domain + "."):
                continue
            haystack = f"{entity_id} {name}".lower().replace("_", " ")
            if all(w in haystack for w in words):
                found.append({"entity_id": entity_id, "name": name, "state": e["state"]})
                if entity_id in read_only:
                    found[-1]["read_only"] = True  # Bolt can look, but not change it
        return found

    def get_state(self, entity_id):
        self._refuse_if_hidden(entity_id)
        e = self._request("GET", f"/api/states/{urllib.parse.quote(entity_id, safe='')}")
        return {"entity_id": e["entity_id"], "state": e["state"], "attributes": e.get("attributes", {})}

    def call_service(self, domain, service, entity_ids, data=None):
        """Run an action, e.g. light.turn_on, on one or more entities."""
        if not entity_ids or isinstance(entity_ids, str) or not isinstance(entity_ids, list):
            raise HomeAssistantError("Say which entity_ids to act on, as a list like [\"light.kitchen\"].")
        if domain in self.blocked:
            raise HomeAssistantError(f"Bolt isn't allowed to use {domain} actions.")
        if set(data or {}) & TARGET_WORDS:
            # {"area_id": "porch"} would reach every light in the porch, past our checks.
            raise HomeAssistantError("Name the devices with entity_ids (Bolt can't target areas, devices or labels).")
        for entity_id in entity_ids:
            self._refuse_if_hidden(entity_id)
            why = self.protection()[1].get(entity_id)
            if why:
                raise HomeAssistantError(why)
            # The action's domain must match the entity's domain (light.turn_on -> light.*).
            # This stops sneaky routes like homeassistant.turn_on on a blocked device.
            if not entity_id.startswith(domain + "."):
                raise HomeAssistantError(f"{domain}.{service} can only be used on {domain}.* entities.")
        hidden, read_only = self.protection()
        if _uses_blocked(data or {}, self.blocked) or _mentions(data or {}, set(hidden) | set(read_only)):
            raise HomeAssistantError("Those settings mention something Bolt isn't allowed to touch.")
        rules = RUNNERS.get(domain)
        if rules:
            if service not in rules["safe"] | rules["check"]:
                allowed = ", ".join(sorted(rules["safe"] | rules["check"]))
                raise HomeAssistantError(f"For {domain} Bolt can only use: {allowed}.")
            if service in rules["check"]:
                for entity_id in entity_ids:
                    self.check_safe_to_run(entity_id)
        changed = self._request("POST", f"/api/services/{domain}/{service}",
                                {**(data or {}), "entity_id": entity_ids})
        return [{"entity_id": c["entity_id"], "state": c["state"]} for c in changed or []]

    def check_safe_to_run(self, entity_id, checked=None):
        """Raise HomeAssistantError unless this automation/script/scene (and everything
        it runs in turn) stays away from blocked domains."""
        checked = set() if checked is None else checked
        if entity_id in checked:
            return  # already checked (and stops loops: a script that calls itself)
        checked.add(entity_id)
        self._refuse_if_hidden(entity_id)
        recipe = self._recipe(entity_id)
        hidden, read_only = self.protection()
        if _uses_blocked(recipe, self.blocked) or _mentions(recipe, set(hidden) | set(read_only)):
            raise HomeAssistantError(f"{entity_id} controls something Bolt isn't allowed to touch "
                                     "(like a lock), so Bolt won't run it.")
        for inner in sorted(_runs_inside(recipe)):
            self.check_safe_to_run(inner, checked)

    def protection(self):
        """Work out (hidden, read_only): two {entity_id: reason} dicts. Cached for a few minutes.
        If HA can't be reached this raises, so nothing gets controlled unchecked."""
        if self._protected is not None and time.monotonic() - self._protected_at < PROTECTION_CACHE_SECONDS:
            return self._protected, self._read_only
        states = self._request("GET", "/api/states") or []
        known = {e["entity_id"] for e in states}
        recipes, hidden = {}, {}
        for e in states:
            entity_id = e["entity_id"]
            if entity_id.split(".", 1)[0] not in RUNNERS or self.is_blocked(entity_id):
                continue
            try:
                recipes[entity_id] = self._recipe(entity_id, e.get("attributes") or {})
            except HomeAssistantError:
                hidden[entity_id] = (f"Bolt can't check what {entity_id} does (it wasn't made in HA's editor, "
                                     "or the token isn't an admin's), so it won't run it or switch it on or off.")
        touches = (f"{{}} controls something Bolt isn't allowed to touch (like a lock), "
                   "so Bolt won't run it or switch it on or off.")
        for entity_id, recipe in recipes.items():
            if _uses_blocked(recipe, self.blocked):
                hidden[entity_id] = touches.format(entity_id)
        read_only = {}
        while True:  # keep going round until nothing new turns up
            for entity_id in hidden:
                if entity_id.startswith("automation.") and entity_id in recipes:
                    for watched in self._watches(recipes[entity_id], known):
                        if watched not in hidden and not self.is_blocked(watched):
                            read_only.setdefault(watched, (
                                f"Changing {watched} could set off an automation that controls something "
                                "Bolt isn't allowed to touch (like a lock), so Bolt won't change it."))
            grew = {entity_id for entity_id, recipe in recipes.items()
                    if entity_id not in hidden and _mentions(recipe, set(hidden) | set(read_only))}
            if not grew:
                break
            for entity_id in grew:
                hidden[entity_id] = touches.format(entity_id)
        self._protected, self._read_only, self._protected_at = hidden, read_only, time.monotonic()
        return hidden, read_only

    def _watches(self, recipe, known):
        """The entities an automation watches: its triggers, conditions and blueprint inputs."""
        parts = [recipe.get(k) for k in ("trigger", "triggers", "condition", "conditions")]
        parts.append((recipe.get("use_blueprint") or {}).get("input"))
        watched = {found for _, value in _walk(parts) if isinstance(value, str)
                   for found in ENTITY.findall(value) if found in known}
        for part in _dicts(parts):
            device = part.get("device_id")
            if isinstance(device, str):
                # A "device trigger" names a device, not an entity: ask HA which entities it has.
                if not re.fullmatch(r"[0-9a-f]{8,64}", device):
                    raise HomeAssistantError(f"Odd device id {device!r} in an automation.")
                answer = self._request("POST", "/api/template",
                                       {"template": f"{{{{ device_entities('{device}') | join(',') }}}}"}, text=True)
                kind = part.get("domain")
                watched |= {e for e in answer.strip().split(",") if e and (not kind or e.startswith(kind + "."))}
        return watched

    def _recipe(self, entity_id, attributes=None):
        """Fetch what an automation, script or scene does, from HA's editor."""
        domain, object_id = entity_id.split(".", 1)
        if domain not in RUNNERS:
            return {}  # an ordinary device: nothing hidden inside
        if domain == "script":
            key = object_id  # scripts are filed under their own name
        else:
            if attributes is None:
                attributes = self._request("GET", f"/api/states/{entity_id}").get("attributes") or {}
            key = attributes.get("id")
            if not key:
                raise HomeAssistantError(f"{entity_id} wasn't made in HA's editor, so Bolt can't check "
                                         "what it does and won't run it.")
        try:
            return self._request("GET", f"/api/config/{domain}/config/{urllib.parse.quote(str(key), safe='')}")
        except HomeAssistantError as e:
            raise HomeAssistantError(
                f"Bolt couldn't read what {entity_id} does, so it won't run it. Only ones made in HA's "
                f"editor can be checked, and the token must belong to an admin. ({e})") from e

    # ------------------------------------------------- camera pictures

    def camera_snapshot(self, camera="", image=""):
        """A picture from Home Assistant, for Riley's screen: either the camera's snapshot right
        now (camera="camera.front_door"), or a picture HA saved (image="/local/snapshots/x.jpg",
        or the "/api/camera_proxy/camera.x" address the phone notification uses).
        Returns JPEG/PNG bytes, or raises HomeAssistantError."""
        if image:
            proxy = re.fullmatch(r"/api/camera_proxy/([a-z_]+\.[a-z0-9_]+)(\?.*)?", image)
            if proxy:
                camera = proxy.group(1)
            elif not re.fullmatch(r"/local/[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)*\.(jpe?g|png)", image):
                raise HomeAssistantError("image must be like /local/snapshots/front.jpg or /api/camera_proxy/camera.x.")
            else:
                return self._picture(image)
        if not camera.startswith("camera."):
            raise HomeAssistantError("camera must be a camera entity, like camera.front_door.")
        self._refuse_if_hidden(camera)          # blocked cameras stay invisible
        return self._picture(f"/api/camera_proxy/{urllib.parse.quote(camera, safe='')}")

    def _picture(self, path):
        request = urllib.request.Request(f"{self.url}{path}", headers={"Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read(MAX_PICTURE_BYTES + 1)
        except urllib.error.HTTPError as e:
            raise HomeAssistantError(f"HA said {e.code} for that picture.") from e
        except (urllib.error.URLError, OSError) as e:
            raise HomeAssistantError(f"Couldn't reach Home Assistant at {self.url}.") from e
        if len(data) > MAX_PICTURE_BYTES:
            raise HomeAssistantError("That picture is too big.")
        if not (data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG")):
            raise HomeAssistantError("That wasn't a JPEG or PNG picture.")
        return data

    # ------------------------------------------------- looking back and ahead

    def logbook(self, hours=24, entity_id=""):
        """What happened recently: [{"when", "name", "message", "entity_id"}], oldest first."""
        if entity_id:
            self._refuse_if_hidden(entity_id)
        hidden = self.protection()[0]
        end = datetime.now().astimezone()
        path = f"/api/logbook/{_iso(end - timedelta(hours=_hours(hours)))}?end_time={_iso(end, query=True)}"
        if entity_id:
            path += "&entity=" + urllib.parse.quote(entity_id)
        entries = []
        for e in self._request("GET", path) or []:
            about = e.get("entity_id") or ""
            if (about and (self.is_blocked(about) or about in hidden)) or e.get("domain") in self.blocked:
                continue  # blocked devices have no diary either
            entries.append({"when": _local(e.get("when")), "name": e.get("name", ""),
                            "message": e.get("message") or e.get("state") or "", "entity_id": about})
        return entries

    def history(self, entity_id, hours=24):
        """How one entity changed: {"entity_id", "changes": [[when, state]...], "summary": {...}}."""
        self._refuse_if_hidden(entity_id)
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
        hidden = self.protection()[0]
        kept = []
        for line in text.splitlines():
            if any(f"{domain}." in line for domain in self.blocked) or any(h in line for h in hidden):
                continue  # don't let the log leak blocked devices
            if all(w in line.lower() for w in words):
                kept.append(_redact(line))
        kept = kept[-max(1, min(lines, 150)):]
        joined = "\n".join(kept)
        return joined[-8000:]  # keep the end (the newest) if it's very long

    def calendars(self):
        return [c for c in self._request("GET", "/api/calendars") or [] if not self.is_blocked(c["entity_id"])]

    def weather_today(self):
        """The weather right now and today's forecast, from the first weather entity (or None)."""
        found = self.find_entities("", "weather")
        if not found:
            return None
        entity_id = found[0]["entity_id"]
        e = self.get_state(entity_id)
        a = e["attributes"]
        weather = {"where": a.get("friendly_name", entity_id), "now": e["state"], "temperature": a.get("temperature"),
                   "unit": a.get("temperature_unit"), "humidity": a.get("humidity"), "wind_speed": a.get("wind_speed")}
        try:
            # LESSON: forecasts aren't part of the weather entity any more; you ASK for them with
            # an action that sends an answer back ("?return_response").
            answer = self._request("POST", "/api/services/weather/get_forecasts?return_response",
                                   {"entity_id": entity_id, "type": "daily"})
            forecast = ((answer or {}).get("service_response") or answer or {}).get(entity_id, {}).get("forecast") or []
            if forecast:
                weather["today"] = {k: forecast[0].get(k) for k in
                                    ("condition", "temperature", "templow", "precipitation_probability", "wind_speed")}
        except (HomeAssistantError, AttributeError, TypeError):
            pass  # no forecast: the current weather will do
        return weather

    def errors_since(self, since):
        """How many errors HA logged since a time, and the first few (with secrets hidden)."""
        found = []
        for line in self.error_log("ERROR", lines=150).splitlines():
            try:
                when = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if when >= since:
                found.append(line[20:][:160])
        return {"count": len(found), "examples": found[:3]}

    def calendar_events(self, days=7, calendar=""):
        """Upcoming events from one calendar (or all of them), soonest first."""
        if calendar:
            self._refuse_if_hidden(calendar)
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

# Things that can run OTHER things. "safe" actions are allowed as they are;
# "check" actions only after reading the recipe (see check_safe_to_run).
RUNNERS = {
    "automation": {"safe": {"turn_on", "turn_off", "toggle"}, "check": {"trigger"}},
    "script": {"safe": {"turn_off"}, "check": {"turn_on", "toggle"}},
    "scene": {"safe": set(), "check": {"turn_on"}},
}
ACTION_WORDS = {"turn_on", "turn_off", "toggle", "reload", "trigger", "apply", "create", "reset"}
TARGET_WORDS = {"area_id", "device_id", "label_id", "floor_id", "entity_id"}
MAX_PICTURE_BYTES = 5_000_000
VALID_ENTITY = re.compile(r"[a-z_]+\.[a-z0-9_]+")
ENTITY = re.compile(r"(?<![a-z0-9_.])[a-z_]+\.[a-z0-9_]+(?![a-z0-9_])")
PROTECTION_CACHE_SECONDS = 300  # work out the protected list again every 5 minutes
RUNS = re.compile(r"\b(automation|script|scene)\.([a-z0-9_]+)\b")


def _walk(thing):
    """Every key and value inside a recipe, however deeply nested."""
    if isinstance(thing, dict):
        for key, value in thing.items():
            yield key, value
            yield from _walk(key)
            yield from _walk(value)
    elif isinstance(thing, list):
        for item in thing:
            yield from _walk(item)
    else:
        yield None, thing


def _dicts(thing):
    """Every dictionary inside a recipe, however deeply nested."""
    if isinstance(thing, dict):
        yield thing
        for value in thing.values():
            yield from _dicts(value)
    elif isinstance(thing, list):
        for item in thing:
            yield from _dicts(item)


def _mentions(recipe, entity_ids):
    """True if the recipe names any of these entities."""
    if not entity_ids:
        return False
    return any(isinstance(value, str) and set(ENTITY.findall(value)) & entity_ids for _, value in _walk(recipe))


def _uses_blocked(recipe, blocked):
    """True if anything in the recipe mentions a blocked domain."""
    names = [re.compile(rf"(?<![a-z0-9_]){re.escape(d)}\.") for d in blocked]
    for key, value in _walk(recipe):
        if key == "domain" and value in blocked:
            return True  # a "device action", e.g. {"domain": "lock", "type": "unlock"}
        if isinstance(value, str) and any(n.search(value) for n in names):
            return True
    return False


def _runs_inside(recipe):
    """The other automations, scripts and scenes a recipe mentions."""
    found = set()
    for _, value in _walk(recipe):
        if isinstance(value, str):
            for domain, name in RUNS.findall(value):
                if name not in ACTION_WORDS:  # "script.turn_on" is an action, not a script
                    found.add(f"{domain}.{name}")
    return found


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
