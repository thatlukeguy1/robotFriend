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
"""

import json
from datetime import datetime

import anthropic

from .personality import SYSTEM_PROMPT

MODEL = "claude-opus-5-5"

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
]


class Brain:
    def __init__(self, reminders, client=None):
        # anthropic.Anthropic() finds your API key in the ANTHROPIC_API_KEY
        # environment variable. Never paste a key directly into code!
        self.client = client or anthropic.Anthropic()
        self.reminders = reminders
        self.messages = []  # <-- the robot's short-term memory

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
            return f"Unknown tool: {name}"
        except Exception as e:  # tell Claude what went wrong so it can try again
            return f"Error: {e}"

    def chat(self, user_text, now=None):
        """Send one thing the owner said, and get back the robot's reply."""
        now = now or datetime.now()
        stamp = now.strftime("%A %d %B %Y, %H:%M")
        memory_before = len(self.messages)  # so we can undo this turn if needed
        self.messages.append({"role": "user", "content": f"[{stamp}] {user_text}"})

        # ----- THE AGENT LOOP -----
        while True:
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.messages,
                # "effort" = how hard Claude thinks before answering. Chatting
                # doesn't need deep thought, and low effort means faster replies.
                output_config={"effort": "low"},
                # If Claude's safety check ever declines a message, quietly
                # retry it on a suitable backup model instead of going silent.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
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
