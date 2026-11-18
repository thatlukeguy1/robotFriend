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

from .personality import SYSTEM_PROMPT

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
    def __init__(self, reminders, client=None):
        # anthropic.Anthropic() finds your API key in the ANTHROPIC_API_KEY
        # environment variable. Never paste a key directly into code!
        self.client = client or anthropic.Anthropic()
        self.reminders = reminders
        self.messages = []  # <-- the robot's short-term memory
        self.last_chat = None

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
            if name == "ask_expert":
                return self.ask_expert(args["question"], args["context"])
            return f"Unknown tool: {name}"
        except Exception as e:  # tell Claude what went wrong so it can try again
            return f"Error: {e}"

    def chat(self, user_text, now=None):
        """Send one thing the owner said, and get back the robot's reply."""
        now = now or datetime.now()
        if self.last_chat and now - self.last_chat > IDLE_RESET:
            self.reset()  # it's been a while, so start a new conversation
        self.last_chat = now
        stamp = now.strftime("%A %d %B %Y, %H:%M")
        memory_before = len(self.messages)  # so we can undo this turn if needed
        self.messages.append({"role": "user", "content": f"[{stamp}] {user_text}"})

        # ----- THE AGENT LOOP -----
        while True:
            response = self.client.messages.create(
                model=CHAT_MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
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
