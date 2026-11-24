"""
LESSON: The brain
=================
This is where your robot "thinks". Here's the big secret:

    Claude has NO memory between messages.

Every time you say something, we send Claude the WHOLE conversation so far
(the `messages` list), and it writes the next reply. That list IS the robot's
short-term memory. Delete it and the robot forgets everything.

TOOLS are how Claude does things in the real world. We describe each tool
(name, what it does, what information it needs). When Claude wants to use one,
it doesn't reply with words. It replies with a "tool_use" request instead,
something like:  "please run add_reminder with message='stretch', when='15:30'".
We run the real Python code, send back the result, and Claude carries on.

That back-and-forth is called the AGENT LOOP. You'll find it in `chat()` below.

LESSON: Two brains (ROUTING)
============================
Bolt actually has TWO brains:

  * CHAT_MODEL (Claude Haiku): small, fast and very cheap. It handles
    everything day to day: chatting, reminders, and later your lights.
  * EXPERT_MODEL (Claude Opus): big, clever and about 40x pricier.

How does Haiku decide when to call the expert? We give it a TOOL called
`ask_expert`. When Haiku thinks a question is too hard, it "uses the tool",
and our code passes the question to Opus and hands the answer back to Haiku,
which then says it in Bolt's voice. So the expert is just another tool!
This pattern is called ROUTING.
"""

import base64
import json
from datetime import datetime, timedelta

import anthropic

from .home_assistant import HomeAssistantError
from .stage import is_time_question, time_cue, weather_cue, without_cues
from .personality import SYSTEM_PROMPT, build_prompt, validate as check_character

CHAT_MODEL = "claude-haiku-5-5"
EXPERT_MODEL = "claude-opus-5-5"

# LESSON: Forgetting on purpose
# The longer a chat gets, the more we resend each time, so every message costs
# a little more. A real friend doesn't recite your whole day back to you either!
# So after 30 quiet minutes, Bolt starts a fresh conversation. (Reminders are
# kept: they live in reminders.json, not in the chat.)
#
# Why not just delete the OLDEST messages instead? Claude checks that earlier
# parts of a conversation haven't been changed, and rejects the request if
# they have. Starting fresh is allowed; editing the past isn't.
IDLE_RESET = timedelta(minutes=30)
# A photo from the camera stays in the conversation (Claude is sent the whole chat
# each time), so a conversation with a photo in it is forgotten sooner.
PHOTO_RESET = timedelta(minutes=5)

REFUSED = "Hmm, I'd rather not talk about that one."

EXPERT_PROMPT = """You are an expert advisor helping a small desktop robot answer its owner.
Give a clear, correct, thoughtful answer. The robot will turn your answer into a short
spoken reply, so lead with the key point and keep it under about 200 words.
No markdown tables or headings."""

# ---------------------------------------------------------------------------
# The tools Claude is allowed to use. Each one has a JSON "schema": a form
# that says exactly which pieces of information Claude must fill in.
# "strict": True makes the API guarantee Claude fills the form in correctly.
# ---------------------------------------------------------------------------
HOME_TOOLS = {"find_devices", "get_device", "control_device",
              "home_logbook", "home_history", "home_error_log", "calendar_events"}
# Logbook entries too routine for a morning briefing (sensors change constantly).
BRIEFING_SKIP = {"sensor", "sun", "weather", "update", "number", "select", "button", "event", "image", "camera"}

TOOLS = [
    {
        "name": "add_reminder",
        "description": "Set a reminder that will alert the owner at a specific local date and time.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What to remind the owner about."},
                "when": {
                    "type": "string",
                    "description": "Local date and time in ISO format, e.g. 2026-11-18T15:30",
                },
            },
            "required": ["message", "when"],
            "additionalProperties": False,
        },
    },
    {
        "name": "weather",
        "description": (
            "The weather outside now (condition, temperature, humidity, wind) and today's forecast "
            "(high, low, chance of rain), from Home Assistant. Use it for ANY question about the "
            "weather, the temperature outside, rain, or what to wear. Not the morning briefing."
        ),
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "morning_briefing",
        "description": (
            "Everything for a morning briefing in one go: the date, today's weather and forecast, "
            "today's calendar, today's reminders, and anything notable overnight in the smart home "
            "(the logbook since 10 hours ago, and any Home Assistant errors). Use it when your owner "
            "says good morning or asks what's on today."
        ),
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "look",
        "description": (
            "Take a photo with your camera (in your head, facing whoever is talking to you) and "
            "see it. Use it ONLY when asked to look at something: \"what's this?\", \"what can you "
            "see?\", \"read this label\", \"how do I look?\". Never to check on people uninvited."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "What you're looking for, e.g. 'what is the person holding up?'"}},
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_timer",
        "description": (
            "Start a countdown timer (for cooking, a break, a game). Use it for a LENGTH of time "
            "(\"10 minutes\"); use add_reminder for a time of day. The time left shows on your screen."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "description": "How long, in seconds (10 minutes = 600). Up to 86400."},
                "label": {"type": "string", "description": "What it's for, in a word or two (\"pasta\"), or empty."},
            },
            "required": ["seconds", "label"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_timers",
        "description": "The timers running now, with their ids and how long each has left (in seconds).",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "cancel_timer",
        "description": "Stop a timer by its id (from set_timer or list_timers).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"timer_id": {"type": "string"}},
            "required": ["timer_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_reminders",
        "description": "List all upcoming reminders with their ids.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel a reminder by its id. Call list_reminders first if you don't know the id.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"reminder_id": {"type": "string"}},
            "required": ["reminder_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_devices",
        "description": (
            "Search the owner's smart home (Home Assistant) for devices and sensors. "
            "Returns entity_id, name and current state. Use it to find the right entity_id "
            "before reading or controlling anything. Leave search empty to list everything "
            "in a domain (e.g. domain 'light')."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Words to look for, e.g. 'lounge lamp'. Can be empty."},
                "domain": {"type": "string", "description": "Optional kind of entity, e.g. light, switch, climate, sensor. Can be empty."},
            },
            "required": ["search", "domain"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_device",
        "description": "Get the full current state and attributes of one Home Assistant entity (e.g. brightness, temperature).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"entity_id": {"type": "string"}},
            "required": ["entity_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "control_device",
        "description": (
            "Run a Home Assistant action on devices, e.g. domain 'light' + action 'turn_on'. "
            "The domain must match the entities (light.turn_on only works on light.* entities). "
            "Common actions: turn_on, turn_off, toggle; climate: set_temperature; "
            "media_player: media_pause, volume_set; cover: open_cover, close_cover; "
            "automation: turn_on, turn_off, trigger; script: turn_on, turn_off; scene: turn_on. "
            "Before running an automation, script or scene, Bolt's safety check reads what it does "
            "and refuses if it touches anything blocked."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "e.g. light"},
                "action": {"type": "string", "description": "e.g. turn_on"},
                "entity_ids": {"type": "array", "items": {"type": "string"}},
                "data_json": {
                    "type": "string",
                    "description": 'Extra settings as a JSON object, e.g. {"brightness_pct": 40} or {"temperature": 20}. Use {} for none.',
                },
            },
            "required": ["domain", "action", "entity_ids", "data_json"],
            "additionalProperties": False,
        },
    },
    {
        "name": "home_logbook",
        "description": (
            "Read Home Assistant's logbook: what happened and when (doors opening, lights "
            "switching, automations running). Optionally just one entity."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "How far back to look, 1 to 336. Usually 24."},
                "entity_id": {"type": "string", "description": "One entity to look at, or empty for everything."},
            },
            "required": ["hours", "entity_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "home_history",
        "description": (
            "How one entity's state changed over time, e.g. a temperature sensor overnight. "
            "Numbers come with lowest, highest and average. Find the entity_id with find_devices first."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "hours": {"type": "integer", "description": "How far back to look, 1 to 336."},
            },
            "required": ["entity_id", "hours"],
            "additionalProperties": False,
        },
    },
    {
        "name": "home_error_log",
        "description": (
            "Read the newest lines of Home Assistant's error log, to work out why something "
            "isn't working. Use search to narrow it down (e.g. an integration or automation name)."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Words every line must contain, or empty for all."},
                "lines": {"type": "integer", "description": "How many of the newest matching lines, 1 to 150. Usually 40."},
            },
            "required": ["search", "lines"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calendar_events",
        "description": "Upcoming events from the owner's calendars in Home Assistant, soonest first.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "How many days ahead, 1 to 60. Usually 7."},
                "calendar": {"type": "string", "description": "One calendar entity_id, or empty for all of them."},
            },
            "required": ["days", "calendar"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remember",
        "description": (
            "Save a fact to long-term memory, so you still know it in future conversations. "
            "Use it for lasting things: names of people and pets, likes and dislikes, routines, "
            "birthdays, ongoing projects, and anything you're asked to remember. "
            "Not for passing small talk. Write each memory as one clear sentence."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"fact": {"type": "string", "description": "e.g. 'Luke's sister is called Amy.'"}},
            "required": ["fact"],
            "additionalProperties": False,
        },
    },
    {
        "name": "forget",
        "description": "Delete a long-term memory by its id (shown in your list of memories), e.g. when it's out of date or you're asked to forget it.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"memory_id": {"type": "string"}},
            "required": ["memory_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ask_expert",
        "description": (
            "Ask a much more capable (and more expensive) AI for help. Use it ONLY for questions "
            "that need deep knowledge or careful reasoning: tricky facts, maths, planning, "
            "detailed explanations, or serious advice. Do NOT use it for small talk, "
            "reminders, or anything simple you can answer well yourself."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The full question, written so it makes sense on its own."},
                "context": {"type": "string", "description": "Anything from the conversation the expert needs to know. Can be empty."},
            },
            "required": ["question", "context"],
            "additionalProperties": False,
        },
    },
]


TOOL_FORMS = {t["name"]: t["input_schema"] for t in TOOLS}
JSON_TYPES = {"string": str, "integer": int, "array": list, "object": dict}


def check_input(name, args):
    """LESSON: check the form before acting on it. Each tool has a FORM (its input_schema).
    The API normally checks Claude filled it in properly, but on the voice path the form
    streams in as it's written, and then the API leaves the checking to us. So: every box
    filled in, nothing extra, and the right kind of thing in each. Returns a problem or None."""
    form = TOOL_FORMS.get(name)
    if form is None:
        return f"there's no tool called {name}"
    if not isinstance(args, dict):
        return "the tool's settings must be a JSON object"
    fields = form.get("properties", {})
    missing = [k for k in form.get("required", []) if k not in args]
    extra = [k for k in args if k not in fields]
    if missing or extra:
        return f"missing {missing}" if missing else f"unexpected {extra}"
    for key, value in args.items():
        want = fields[key].get("type")
        if want and (not isinstance(value, JSON_TYPES[want]) or isinstance(value, bool)):
            return f"{key} should be {want}"
        if want == "array":
            item = (fields[key].get("items") or {}).get("type")
            if item and not all(isinstance(v, JSON_TYPES[item]) for v in value):
                return f"every item in {key} should be {item}"
    return None


class Brain:
    def __init__(self, reminders, client=None, home=None, memories=None, character=None, camera=None, timers=None):
        # anthropic.Anthropic() finds your API key in the ANTHROPIC_API_KEY
        # environment variable. Never paste a key directly into code!
        self.client = client or anthropic.Anthropic()
        self.reminders = reminders
        self.home = home  # Home Assistant connection (or None if not set up)
        self.memories = memories  # <-- the robot's long-term memory (see memory.py)
        self.character = character  # <-- who it is (see personality.py)
        self.camera = camera  # <-- photos from the body's camera, when asked (see camera.py)
        self.timers = timers  # <-- countdown timers (see timers.py)
        self.messages = []  # <-- the robot's short-term memory
        self.photo_in_chat = False  # a camera photo is in this conversation (see PHOTO_RESET)
        self.stage_waiting = ""     # a prop the brain chose itself (e.g. the weather), shown after tools run
        self.system = SYSTEM_PROMPT
        self.last_chat = None

    def instructions(self):
        """Bolt's personality, plus everything in its long-term memory."""
        prompt = self.character.prompt() if self.character else SYSTEM_PROMPT
        if self.memories is None:
            return prompt
        return prompt + "\n\n" + self.memories.as_prompt()

    def try_character(self, character, history):
        """
        A quick test chat with a personality that ISN'T saved yet, for the Studio.
        It has no tools (so it can't set reminders or touch the lights) and no
        memories, and it doesn't touch Bolt's real conversation.
        """
        prompt = build_prompt(check_character(character))
        prompt += "\n(This is a test chat in the Studio. You can't use any tools here, so just chat.)\n"
        response = self.client.messages.create(
            model=CHAT_MODEL,
            max_tokens=2000,
            system=prompt,
            messages=history,
            output_config={"effort": "low"},
        )
        if response.stop_reason == "refusal":
            return "Hmm, I'd rather not talk about that one."
        return without_cues(" ".join(b.text for b in response.content if b.type == "text"))

    def reset(self):
        """Forget the current conversation and start a fresh one."""
        self.messages = []
        self.photo_in_chat = False

    def morning_briefing(self, now=None):
        """Gather a morning briefing. Each part is checked on its own, so one problem
        (say, no calendar) doesn't spoil the rest."""
        now = now or datetime.now()
        end_of_today = now.replace(hour=23, minute=59).isoformat(timespec="minutes")
        out = {"now": now.strftime("%A %d %B, %H:%M"),
               "reminders_today": [r for r in self.reminders.list() if r["due"] <= end_of_today]}
        if not (self.home and self.home.can_control):
            out["smart_home"] = "not set up"
            return out
        since = now - timedelta(hours=10)
        parts = {
            "weather": self.home.weather_today,
            "calendar_today": lambda: self.home.calendar_events(1),
            "overnight": lambda: [e for e in self.home.logbook(10)
                                  if (e.get("entity_id") or ".").split(".")[0] not in BRIEFING_SKIP][-25:],
            "home_assistant_errors": lambda: self.home.errors_since(since),
        }
        for key, get in parts.items():
            try:
                out[key] = get()
            except Exception as e:
                out[key] = f"couldn't check ({e})"
        return out

    def look(self, question):
        """LESSON: tools can return PICTURES. Instead of a sentence, this tool's result is
        the photo itself (plus a line of text), so Claude sees it directly, the same way
        it would see a picture you pasted into a chat."""
        if self.camera is None:
            return "You don't have a camera yet. Say so briefly."
        photo, problem = self.camera.take()
        if photo is None:
            return f"You couldn't see anything: {problem}. Say so briefly."
        self.photo_in_chat = True
        return [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(photo).decode()}},
            {"type": "text", "text": f"Your camera just took this photo. Looking for: {question}. "
                                     "Answer in a sentence or two, out loud, like a friend would."},
        ]

    def in_my_words(self, message):
        """Say a message from Home Assistant the way Bolt would: one short spoken sentence,
        in character. Separate from the conversation, so it doesn't disturb a chat."""
        response = self.client.messages.create(
            model=CHAT_MODEL,
            max_tokens=200,
            system=self.instructions(),
            messages=[{"role": "user", "content": (
                "[A message from the smart home, to say out loud to your owner now. Say it in your own "
                "words, in one or two short spoken sentences, keeping every fact (numbers, names, rooms) "
                f"exactly right. No questions, no greeting.]\n{message}")}],
        )
        words = without_cues("".join(b.text for b in response.content if b.type == "text"))
        return words or message

    def ask_expert(self, question, context):
        """Pass a hard question to the big, expensive model and return its answer."""
        prompt = f"Context: {context}\n\nQuestion: {question}" if context else question
        response = self.client.beta.messages.create(
            model=EXPERT_MODEL,
            max_tokens=16000,
            system=EXPERT_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "medium"},  # think properly, it's a hard question
            # If the expert's safety check declines, a suitable backup model answers instead.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            return "The expert couldn't help with that one."
        return " ".join(b.text for b in response.content if b.type == "text").strip()

    def run_tool(self, name, args):
        """Claude asked us to do something. Do it, and describe what happened."""
        problem = check_input(name, args)
        if problem:
            return f"Error: that request wasn't filled in properly ({problem}). Try again."
        try:
            if name == "add_reminder":
                r = self.reminders.add(args["message"], args["when"])
                return f"Reminder {r['id']} set for {r['due']}: {r['message']}"
            if name == "morning_briefing":
                briefing = self.morning_briefing()
                self.stage_waiting = weather_cue(briefing.get("weather"))
                return json.dumps(briefing, ensure_ascii=False, default=str)
            if name == "weather":
                if not (self.home and self.home.can_control):
                    return "The smart home isn't set up, so you can't check the weather."
                weather = self.home.weather_today()
                if not weather:
                    return "There's no weather entity in Home Assistant."
                self.stage_waiting = weather_cue(weather)      # the prop: the real sky and temperature
                return json.dumps(weather, ensure_ascii=False, default=str)
            if name == "look":
                return self.look(args["question"])
            if name in ("set_timer", "list_timers", "cancel_timer"):
                if self.timers is None:
                    return "Timers aren't switched on."
                if name == "set_timer":
                    t = self.timers.add(args["seconds"], args["label"])
                    return f"Timer {t['id']} started: {t['seconds']} seconds" + (f" for {t['label']}" if t["label"] else "") + "."
                if name == "list_timers":
                    items = self.timers.list()
                    return json.dumps(items) if items else "No timers running."
                return "Cancelled." if self.timers.cancel(args["timer_id"]) else "No timer with that id."
            if name == "list_reminders":
                items = self.reminders.list()
                return json.dumps(items) if items else "No reminders set."
            if name == "cancel_reminder":
                ok = self.reminders.cancel(args["reminder_id"])
                return "Cancelled." if ok else "No reminder with that id."
            if name == "remember":
                if self.memories is None:
                    return "Long-term memory isn't switched on."
                m = self.memories.add(args["fact"])
                return f"Saved as memory {m['id']}."
            if name == "forget":
                if self.memories is None:
                    return "Long-term memory isn't switched on."
                return "Forgotten." if self.memories.forget(args["memory_id"]) else "No memory with that id."
            if name == "ask_expert":
                return self.ask_expert(args["question"], args["context"])
            if name in HOME_TOOLS:
                return self.run_home_tool(name, args)
            return f"Unknown tool: {name}"
        except Exception as e:  # tell Claude what went wrong so it can try again
            return f"Error: {e}"

    def run_home_tool(self, name, args):
        if not (self.home and self.home.can_control):
            return "Smart home control isn't set up (HA_URL and HA_TOKEN in .env)."
        try:
            if name == "find_devices":
                found = self.home.find_entities(args["search"], args["domain"])
                if not found:
                    return "Nothing matched. Try fewer or different words, or just a domain."
                more = f" (showing 40 of {len(found)}; search more specifically)" if len(found) > 40 else ""
                return json.dumps(found[:40]) + more
            if name == "get_device":
                return json.dumps(self.home.get_state(args["entity_id"]))
            if name == "home_logbook":
                entries = self.home.logbook(args["hours"], args["entity_id"])
                if not entries:
                    return "Nothing in the logbook for that time."
                more = f" (only the newest 60 of {len(entries)} entries)" if len(entries) > 60 else ""
                return json.dumps(entries[-60:], ensure_ascii=False) + more
            if name == "home_history":
                return json.dumps(self.home.history(args["entity_id"], args["hours"]), ensure_ascii=False)
            if name == "home_error_log":
                log = self.home.error_log(args["search"], args["lines"])
                return log or "No matching lines in the error log."
            if name == "calendar_events":
                events = self.home.calendar_events(args["days"], args["calendar"])
                if not events:
                    return "No events coming up in that time."
                more = f" (first 40 of {len(events)})" if len(events) > 40 else ""
                return json.dumps(events[:40], ensure_ascii=False) + more
            if name == "control_device":
                data = json.loads(args["data_json"] or "{}")
                if not isinstance(data, dict):
                    return "Error: data_json must be a JSON object like {}."
                changed = self.home.call_service(args["domain"], args["action"], args["entity_ids"], data)
                return "Done. New states: " + json.dumps(changed) if changed else "Done."
        except HomeAssistantError as e:
            return f"Error: {e}"
        except json.JSONDecodeError:
            return "Error: data_json wasn't valid JSON."

    # ------------------------------------------------------------ a turn
    def _start_turn(self, user_text, now):
        """Get ready for something the owner said. Returns where this turn starts in memory."""
        now = now or datetime.now()
        if self.last_chat and now - self.last_chat > (PHOTO_RESET if self.photo_in_chat else IDLE_RESET):
            self.reset()  # it's been a while, so start a new conversation
        self.last_chat = now
        stamp = now.strftime("%A %d %B %Y, %H:%M")
        memory_before = len(self.messages)  # so we can undo this turn if needed
        self.stage_waiting = ""             # no leftover prop from a turn that went wrong
        if not self.messages:
            # A brand-new conversation: read the long-term memories now. They
            # stay fixed until the next conversation (see memory.py for why).
            self.system = self.instructions()
        self.messages.append({"role": "user", "content": f"[{stamp}] {user_text}"})
        return memory_before

    def _request(self, tools=TOOLS):
        """Everything we send Claude each time round the agent loop."""
        return dict(
            model=CHAT_MODEL,
            max_tokens=16000,
            system=self.system,
            tools=tools,
            messages=self.messages,
            # "effort" = how hard Claude thinks before answering. Chatting
            # doesn't need deep thought, and low effort means faster replies.
            output_config={"effort": "low"},
            # PROMPT CACHING: Claude remembers the start of the conversation
            # for a few minutes, so resending it costs about 10x less.
            cache_control={"type": "ephemeral"},
        )

    def _after_reply(self, response, memory_before):
        """Deal with one reply from Claude. Returns "again" (tools ran), "refused" or "done"."""
        if response.stop_reason == "refusal":
            # Forget this whole turn so the chat can carry on.
            self.messages = self.messages[:memory_before]
            return "refused"
        # Save Claude's whole reply (words AND tool requests) into memory.
        self.messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "tool_use":
            # Claude wants us to run one or more tools.
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"   (robot is using tool: {block.name})")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,  # which request this answers
                        "content": self.run_tool(block.name, block.input),
                    })
            # Send the results back, then go round the loop again.
            self.messages.append({"role": "user", "content": results})
            return "again"
        return "done"

    def chat(self, user_text, now=None):
        """Send one thing the owner said, and get back the robot's whole reply."""
        memory_before = self._start_turn(user_text, now)
        words = [time_cue(now or datetime.now())] if is_time_question(user_text) else []
        # ----- THE AGENT LOOP -----
        while True:
            response = self.client.messages.create(**self._request())
            words += [b.text for b in response.content if b.type == "text"]
            outcome = self._after_reply(response, memory_before)
            if outcome == "refused":
                return REFUSED
            if self.stage_waiting:                     # a prop the brain chose (see stage.py)
                words.append(self.stage_waiting)
                self.stage_waiting = ""
            if outcome == "done":
                return " ".join(w.strip() for w in words if w.strip())

    def chat_stream(self, user_text, now=None):
        """
        LESSON: Streaming
        =================
        chat() waits for Claude's WHOLE reply. This version hands over the reply
        a few words at a time, AS Claude writes it (a "generator": each `yield`
        passes on one piece). That way Bolt can start speaking its first
        sentence while Claude is still writing the rest.
        """
        memory_before = self._start_turn(user_text, now)
        if is_time_question(user_text):
            # Asked the time: the clock goes up straight away, before Claude has said a word
            yield time_cue(now or datetime.now()) + " "
        streaming_tools = [{**t, "eager_input_streaming": True} for t in TOOLS]
        while True:
            spoken = ""
            try:
                with self.client.messages.stream(**self._request(streaming_tools)) as stream:
                    for words in stream.text_stream:
                        spoken += words
                        yield words
                    response = stream.get_final_message()
            except ValueError:
                # A tool's settings arrived as broken JSON part-way through the
                # stream. Ask again, this time without streaming.
                response = self.client.messages.create(**self._request())
                again = "".join(b.text for b in response.content if b.type == "text")
                # Some words may already have gone out: say only what's new. (If the second
                # try starts differently, it's safer to say nothing than to repeat ourselves.)
                if again.startswith(spoken):
                    yield again[len(spoken):]
                elif not spoken.strip():
                    yield again
            if response.stop_reason == "max_tokens" and any(b.type == "tool_use" for b in response.content):
                # The reply was cut off mid-tool: don't run half a tool request.
                self.messages = self.messages[:memory_before]
                yield " Sorry, I got a bit muddled there."
                return
            outcome = self._after_reply(response, memory_before)
            if outcome == "refused":
                yield REFUSED
                return
            if outcome == "done":
                return
            # Tools ran: keep any words before and after them apart, and hold up any prop the
            # brain chose from what the tools found (the weather), just before she says it.
            yield f" {self.stage_waiting} " if self.stage_waiting else " "
            self.stage_waiting = ""
