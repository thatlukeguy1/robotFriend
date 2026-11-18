# Learning Guide: How Robot Friend Works

Read this alongside the code. Every file also starts with a **LESSON** comment.

## The big picture

A robot friend has three parts, a bit like you do:

| Part | Robot | You |
|---|---|---|
| **Senses** | microphone, camera | ears, eyes |
| **Brain** | Claude (an AI, running on the internet) | brain |
| **Body** | speaker, screen, motors | mouth, face, neck |

In **phase 1** we build only the brain. You type instead of talk, and it types
back instead of speaking. Senses and body get added later, one at a time.

```
 you type ──► main.py ──► brain.py ──► Claude (on the internet)
                │             ▲              │
                │             └── tools ◄────┘  (e.g. "set a reminder")
                ▼
          reminders.py ◄── alarm clock checks every 15 s
```

## The files

| File | What it does |
|---|---|
| `main.py` | Starts everything. Reads what you type, prints replies, and runs the alarm clock. |
| `robot_friend/personality.py` | **Who the robot is.** Change the name and the character here. |
| `robot_friend/brain.py` | Talks to Claude. Holds the memory. Runs the agent loop. |
| `robot_friend/reminders.py` | Plain Python that stores reminders in `reminders.json`. |
| `tests/test_phase1.py` | Checks it all works, using a pretend Claude (free and offline). |

## Five ideas to understand

1. **System prompt:** instructions sent before every chat that set the robot's personality.
2. **Claude has no memory.** We resend the whole conversation every time, and that list *is* the robot's memory. Quit the program and it forgets the chat (reminders are saved to a file, so they survive).
3. **Tools:** Claude can only write words. To *do* something, it asks us to run a tool, we run real Python code, and we tell Claude the result.
4. **The agent loop:** ask Claude, and if it wants a tool, run it and ask again. Repeat until it just talks.
5. **Threads:** two jobs at once. Your typing runs in one, and the alarm clock runs in the other.

## Setting it up on your computer

You need **Python 3.10 or newer** ([python.org](https://www.python.org/downloads/)).

**1. Get an API key.** This is a password that lets your program use Claude.
Make an account at [platform.claude.com](https://platform.claude.com), add a little credit,
and create a key. **Never share it or put it in your code.** Anyone who has it can spend your money.

**2. Get the code and install the libraries** (in a terminal, inside the project folder):

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate
```

(On Windows use `.venv\Scripts\activate` instead.)

```bash
pip install -r requirements.txt
```

**3. Give the program your key** (only for this terminal window):

```bash
export ANTHROPIC_API_KEY="paste-your-key-here"
```

(On Windows PowerShell: `$env:ANTHROPIC_API_KEY="paste-your-key-here"`)

**4. Run the tests, then the robot:**

```bash
python -m pytest
```

```bash
python main.py
```

## Things to try

- "Hi! What's your name?"
- "Remind me to stretch in 2 minutes." Then wait for the 🔔.
- "What reminders do I have?" and "Cancel that one."
- **Experiment:** change `ROBOT_NAME` and the personality in `personality.py`. Make it grumpy, or a pirate. Run it again and see how different it feels.

## How much does it cost?

You pay a tiny amount for every message. Casual chatting usually costs pennies a day.
You can set a monthly spending limit on the Claude platform website so there are no surprises.

## Coming next

- **Phase 2:** move the brain onto a Raspberry Pi, and add a microphone and speaker so you can *talk* to it.
