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

import json
from datetime import datetime, timedelta

import anthropic

from .home_assistant import HomeAssistantError
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

EXPERT_PROMPT = """You are an expert advisor helping a small desktop robot answer its owner.
Give a clear, correct, thoughtful answer. The robot will turn your answer into a short
spoken reply, so lead with the key point and keep it under about 200 words.
No markdown tables or headings."""

# ---------------------------------------------------------------------------
# The tools Claude is allowed to use. Each one has a JSON "schema": a form
# that says exactly which pieces of information Claude must fill in.
# "strict": True makes the API guarantee Claude fills the form in correctly.
# ---------------------------------------------------------------------------
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
            "media_player: media_pause, volume_set; cover: open_cover, close_cover."
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


class Brain:
    def __init__(self, reminders, client=None, home=None, memories=None, character=None):
        # anthropic.Anthropic() finds your API key in the ANTHROPIC_API_KEY
        # environment variable. Never paste a key directly into code!
        self.client = client or anthropic.Anthropic()
        self.reminders = reminders
        self.home = home  # Home Assistant connection (or None if not set up)
        self.memories = memories  # <-- the robot's long-term memory (see memory.py)
        self.character = character  # <-- who it is (see personality.py)
        self.messages = []  # <-- the robot's short-term memory
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
        return " ".join(b.text for b in response.content if b.type == "text").strip()

    def reset(self):
        """Forget the current conversation and start a fresh one."""
        self.messages = []

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
        try:
            if name == "add_reminder":
                r = self.reminders.add(args["message"], args["when"])
                return f"Reminder {r['id']} set for {r['due']}: {r['message']}"
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
            if name in ("find_devices", "get_device", "control_device"):
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

    def chat(self, user_text, now=None):
        """Send one thing the owner said, and get back the robot's reply."""
        now = now or datetime.now()
        if self.last_chat and now - self.last_chat > IDLE_RESET:
            self.reset()  # it's been a while, so start a new conversation
        self.last_chat = now
        stamp = now.strftime("%A %d %B %Y, %H:%M")
        memory_before = len(self.messages)  # so we can undo this turn if needed
        if not self.messages:
            # A brand-new conversation: read the long-term memories now. They
            # stay fixed until the next conversation (see memory.py for why).
            self.system = self.instructions()
        self.messages.append({"role": "user", "content": f"[{stamp}] {user_text}"})

        # ----- THE AGENT LOOP -----
        while True:
            response = self.client.messages.create(
                model=CHAT_MODEL,
                max_tokens=16000,
                system=self.system,
                tools=TOOLS,
                messages=self.messages,
                # "effort" = how hard Claude thinks before answering. Chatting
                # doesn't need deep thought, and low effort means faster replies.
                output_config={"effort": "low"},
                # PROMPT CACHING: Claude remembers the start of the conversation
                # for a few minutes, so resending it costs about 10x less.
                cache_control={"type": "ephemeral"},
            )

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
                continue

            if response.stop_reason == "refusal":
                # Forget this whole turn so the chat can carry on.
                self.messages = self.messages[:memory_before]
                return "Hmm, I'd rather not talk about that one."

            # Any other stop reason means Claude has finished. Collect its words.
            return " ".join(b.text for b in response.content if b.type == "text").strip()
