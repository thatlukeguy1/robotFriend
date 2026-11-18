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
6. **Routing (two brains):** a cheap, fast model (Haiku) does the everyday work. When a question is too hard, it uses the `ask_expert` *tool* to pass it to a big, clever model (Opus). The expert is just another tool!

```
 "remind me at 3"      ──► Haiku ──► add_reminder tool           (≈ 0.02p)
 "how do black holes   ──► Haiku ──► ask_expert tool ──► Opus     (≈ 1-2p)
  evaporate?"                 ◄──── answer in Bolt's voice ◄──┘
```

When you see `(robot is using tool: ask_expert)`, Bolt is calling its clever friend.

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

## Running the brain on your mini PC (Docker)

Your mini PC is on all the time, so it's a good home for the brain. Docker
runs Bolt in its own sealed box, next to Home Assistant, without either one
getting in the other's way.

| Word | Meaning |
|---|---|
| **Image** | The sealed box, built from the recipe in `Dockerfile` |
| **Container** | A running copy of the image |
| **Volume** | A saved folder that survives rebuilds (Bolt's reminders live here) |
| **compose.yaml** | The settings for running it: key, time zone, restart rules |

On the mini PC (you'll need `git` installed), run these one at a time:

```bash
git clone https://github.com/thatlukeguy1/robotFriend.git
```

```bash
cd robotFriend
```

```bash
cp .env.example .env
```

```bash
nano .env
```

Put your API key in `.env`, check the time zone, then save (Ctrl+O, Enter, Ctrl+X).

```bash
docker compose up -d --build
```

Bolt's brain is now running in the background as a **web server**.

### Chatting from your phone or computer

1. Find the mini PC's address on your home network:
```bash
hostname -I
```
   The first number, something like `192.168.1.50`, is its address.
2. On your phone (connected to the same Wi-Fi), open a browser and go to
   `http://192.168.1.50:8770`, using your own number. Bookmark it!

If the page shows a **different** program, something else on the mini PC
already uses door 8770. Pick another number for `BOLT_PORT` in `.env` (see
"Port clash" below).

If the page won't load from your phone but works on the mini PC itself
(`http://localhost:8770`), the mini PC's firewall may be blocking door 8770.
On Ubuntu, this opens it:

```bash
sudo ufw allow 8770/tcp
```

**Safety:** anyone on your home Wi-Fi can chat with Bolt, which spends your API
credit. That's fine at home. **Never** set up "port forwarding" for 8770 on your
router, because that would open Bolt to the whole internet.

### Port clash: "address already in use"

Each door (port) can only be used by one program. To see which doors are taken:

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

Choose a number that isn't in that list, set `BOLT_PORT=` to it in `.env`, then:

```bash
docker compose up -d --force-recreate
```

### Looking after it

To update Bolt after new code is pushed to GitHub:

```bash
git pull && docker compose up -d --build
```

To see what Bolt has been doing (handy for spotting errors):

```bash
docker logs robot-brain --tail 30
```

To check it's healthy (it should say `healthy`):

```bash
docker ps --filter name=robot-brain
```

## How the server works

Read the LESSON at the top of `server.py`. The short version:

```
 phone browser ──POST /chat {"text":"hi"}──►  mini PC :8770  ──► Haiku / Opus
               ◄────── {"reply":"Hi!"} ──────   (server.py)
 phone browser ──GET /notifications────────►  "any reminders gone off?"
```

The web page (`web/index.html`) is a **client**: it does exactly what the Pi
will do later, just with a keyboard instead of a microphone.

Two more things the server does to keep costs low:

- **Prompt caching:** Claude keeps the start of the conversation in a short-term cache, so resending it is about 10x cheaper.
- **Forgetting on purpose:** after 30 quiet minutes, Bolt starts a fresh conversation. You can also press **New chat**. Reminders are always kept.

The keyboard version still works on a laptop: `python main.py`.

## Things to try

- Open the web page and say "Hi! What's your name?"
- "Remind me to stretch in 2 minutes." Then wait for the 🔔.
- "What reminders do I have?" and "Cancel that one."
- Ask something hard ("Explain how a rainbow forms, step by step") and watch for `ask_expert`.
- **Experiment:** change `ROBOT_NAME` and the personality in `personality.py`. Make it grumpy, or a pirate. Run it again and see how different it feels.

## How much does it cost?

You pay a tiny amount for every message. Everyday chat runs on Haiku, at roughly 0.02p a message.
Only questions passed to the expert cost more (about 1–2p each). Expect well under £1 a month
of normal use. Note that a Claude.ai subscription does **not** include API credit: you buy that
separately at platform.claude.com, under Billing.
You can set a monthly spending limit on the Claude platform website so there are no surprises.

## Coming next

- **Phase 2:** move the brain onto a Raspberry Pi, and add a microphone and speaker so you can *talk* to it.
