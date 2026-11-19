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
docker logs bolt --tail 30
```

To check it's healthy (it should say `healthy`):

```bash
docker ps --filter name=bolt
```

## Phone notifications via Home Assistant

Reminders show on the web page only while it's open. To make your **phone buzz**
even when it's locked, Bolt can ask Home Assistant to send a notification.
(Read the LESSON at the top of `robot_friend/home_assistant.py` first.)

You need the **Home Assistant Companion app** on your phone, logged in to your HA.

**1. Find your phone's notify action**
In Home Assistant: **Settings → Developer tools → Actions**. Type `notify.mobile_app`
in the search box. You'll see something like `notify.mobile_app_lukes_phone`.
Copy the part after `notify.`, e.g. `mobile_app_lukes_phone`.

**2. Make an access token**
In Home Assistant: click your **name/profile** (bottom left) → **Security** tab →
scroll to **Long-lived access tokens** → **Create token** → name it `Bolt`.
Copy it straight away; HA only shows it once.

⚠️ This token can control your **whole home**. Only ever paste it into `.env` on
the mini PC. Never into a chat, a message, or GitHub. If it ever leaks, delete it
in the same place in HA and make a new one.

**3. Add three lines to `.env`** on the mini PC (`nano .env`):

```
HA_URL=http://192.168.4.58:8123
HA_TOKEN=paste-the-token-here
HA_NOTIFY=mobile_app_lukes_phone
```

**4. Restart Bolt so it reads the new settings:**

```bash
docker compose up -d --force-recreate
```

**5. Send a test notification:**

```bash
docker exec bolt python -m robot_friend.home_assistant "Hello from Bolt!"
```

You should see `✅ Sent!` and your phone should buzz. If you get `❌`, the message
says what's wrong: a bad token, a wrong action name, or a wrong address.

**6. The real test:** lock your phone, and ask Bolt (from a computer) to remind
you of something in 2 minutes.

## Voice: talking to Bolt

Read the LESSON at the top of `robot_friend/voice.py` first. Bolt's voice is two
extra containers that start alongside the brain:

| Container | Job | Port |
|---|---|---|
| `wyoming-whisper` | **Ears:** your voice → text | 10300 |
| `wyoming-piper` | **Mouth:** text → Bolt's voice | 10200 |

```
 🎤 hold to talk ──WAV──► Bolt ──► Whisper ──"remind me…"──► Claude
 🔊 Bolt speaks  ◄──WAV── Bolt ◄── Piper  ◄──"Done! I'll…"──┘
```

### Setting it up

```bash
cd ~/robotFriend && git pull && docker compose up -d --build
```

The **first** start downloads the speech models (a few hundred MB), so give it a
few minutes. Check progress with `docker logs wyoming-whisper`; it's ready when
it says `Ready`. Then test the ears and mouth together:

```bash
docker exec bolt python -m robot_friend.voice selftest
```

Piper says a sentence, Whisper listens to it, and you should see `✅ Voice is working!`
plus how many seconds each part took.

**Change the voice:** listen to the options at
[rhasspy.github.io/piper-samples](https://rhasspy.github.io/piper-samples/), then set
`PIPER_VOICE=` in `.env` and run `docker compose up -d`.

**Too slow?** Set `WHISPER_MODEL=tiny-int8` in `.env` (faster, but makes more mistakes).

### Talking from your phone

Hold the 🎤 button, speak, and let go. Bolt shows what it heard, replies, and talks back.

**The catch:** browsers only allow the microphone on secure `https://` pages, and
Bolt's page is plain `http://`. Until we add HTTPS:

- **Android (Chrome):** go to `chrome://flags/#unsafely-treat-insecure-origin-as-secure`,
  type `http://192.168.4.58:8770` in the box, set it to **Enabled**, and relaunch Chrome.
  (This trusts **only** Bolt's page.)
- **Laptop (Chrome or Edge):** the same flag works.
- **iPhone:** Safari has no such switch, so the mic button will explain it's blocked.
  Typing still works.

### Using the same voice in Home Assistant

1. In HA: **Settings → Devices & services → Add integration → Wyoming Protocol**.
   Host `192.168.4.58`, port `10300`. Do it again with port `10200`.
2. **Settings → Voice assistants →** open your assistant (or add one). Set
   **Speech-to-text** to `faster-whisper` and **Text-to-speech** to `piper`.
3. In the Home Assistant phone app, tap the Assist button and talk. HA's own
   assistant now uses Bolt's ears and mouth, all running on your mini PC.

### "Hey Bolt" (coming with the Pi)

Wake words run on the device with the microphone, so "Hey Bolt" comes in phase 2.
It's a **custom** wake word, so we'll need to train a small model for it.

## Smart home control

Bolt can now find, read and control your Home Assistant devices: "turn the desk
lamp to 40%", "is the lounge warm?", "turn off all the lights". Read the LESSON
at the top of `robot_friend/home_assistant.py`.

It uses the same `HA_URL` and `HA_TOKEN` as phone notifications, so if those work,
this works. After updating, `docker logs bolt` should show:

```
Smart home control: ON (blocked: lock)
```

### What Bolt can't touch

`HA_BLOCKED_DOMAINS` in `.env` lists the kinds of device Bolt can **never see or
control**. It's enforced in Python, so no clever wording can talk Bolt past it.
The default is `lock`. Worth thinking about:

| Domain | Why you might block it |
|---|---|
| `alarm_control_panel` | Bolt could disarm the alarm |
| `cover` | Garage doors and gates are covers too |
| `script`, `automation` | A script that unlocks a door would get around the lock block |

Remember that anyone on your Wi-Fi (and, once the Pi arrives, anyone Bolt can
hear) can ask Bolt to do things. To change the list, edit `.env`, e.g.
`HA_BLOCKED_DOMAINS=lock,alarm_control_panel,cover`, then run `docker compose up -d`.

### Things to try

- "What lights do I have?"
- "Turn the desk lamp on at 30 percent."
- "What's the temperature in the lounge?"
- "Can you unlock the front door?" (it should say it can't)

## Long-term memory

Bolt now keeps a diary of important facts. Read the LESSON at the top of
`robot_friend/memory.py`.

| | Short-term memory | Long-term memory |
|---|---|---|
| What | The current conversation | Facts Bolt chose to write down |
| Where | `brain.messages` (in the computer's memory) | `memories.json` (saved on disk) |
| How long | Until 30 quiet minutes, or New chat | Until you (or Bolt) delete it |

Bolt saves a memory with its `remember` tool. At the start of every new
conversation it reads the whole list, so "Bolt, my sister's called Amy" today
means "How's Amy?" can make sense next week.

**A new memory joins the list from Bolt's *next* conversation.** Claude rejects
a conversation whose beginning has been changed, so we never edit it mid-chat.
To use a memory straight away, press **New chat**.

### Seeing and deleting memories

Tap **🧠** on the chat page to see everything Bolt remembers, and ✕ to delete any
of it. You can also just say "forget that my sister's called Amy".

### Things to try

1. "Remember that I hate mushrooms."
2. Press **New chat** (or wait 30 minutes).
3. "Can you suggest a pizza for me?"
4. Open 🧠 and look at what Bolt wrote down.

**Remember:** everyone who talks to Bolt adds to the same memory. Bolt won't
save passwords or bank details, but it's worth checking 🧠 now and then.

## Bolt's eyes

Bolt's eyes are drawn by code, about 60 times a second. Read the LESSON at the
top of `web/eyes.js`.

| File | What it does |
|---|---|
| `web/expressions.json` | **The personality.** Every expression as a handful of numbers |
| `web/eyes.js` | Draws the eyes in a browser (the chat page and the Eye Studio) |
| `pi/bolt_body/eyes.py` | Draws the same eyes in Python, for the round screens on the Pi |

Both drawing programs read the same `expressions.json` and use the same maths,
so what you design on your phone is what the robot will show.

### The Eye Studio

Open **`http://192.168.4.58:8770/eyes`** (or tap Bolt's eyes on the chat page).

1. Tap an expression: idle, sleeping, listening, thinking, speaking, happy, confused.
2. Drag the sliders to change it. The eyes update instantly.
3. **Pretend to talk** makes the eyes bob like they do when Bolt speaks.
4. Happy with it? **Copy settings**, then paste over `web/expressions.json` on the
   mini PC (or send it to Claude), and run `docker compose up -d --build`.

Your changes stay in that browser until you copy them into the file, so you
can't break anything by experimenting. **Reset to saved** undoes everything.

### On the chat page

The little eyes next to Bolt's name now react: they **listen** while you hold 🎤,
**think** while Bolt works out a reply, **bob along** while it talks, look
**happy** when it answers, and **confused** when something goes wrong.

### Ideas to try

- Change `iris` in `colors` to Bolt's favourite colour.
- Make `sleeping` look up instead of down, or give `thinking` a wonky lid.
- Add a brand new expression, like `"surprised"`, with `open: 1` and a tiny `pupil`.

## Phase 2: Bolt's body (the Raspberry Pi)

The code for the Pi is ready and waiting in the `pi/` folder, before the parts
have even arrived. Read the LESSONs at the top of each file in `pi/bolt_body/`:

| File | What it does |
|---|---|
| `main.py` | The **state machine**: sleeping → listening → thinking → speaking |
| `wake.py` | Listens for the wake word, on the Pi itself |
| `audio.py` | Microphone, speaker, beeps, and knowing when you've stopped talking |
| `brain_link.py` | Talks to the brain on the mini PC (same routes as the phone page) |

```
 Pi (on your desk)                                  mini PC
 ─────────────────                                  ───────
 mic ─► wake word? ──yes──► record until quiet ──► /voice ──► Whisper → Claude → Piper
 speaker ◄──────────────────────────────────────── reply audio ◄──┘
 speaker ◄── reminder ◄── /notifications (checked every 10 s)
```

**Privacy:** nothing leaves the Pi until it hears the wake word. Only what you
say *after* the wake word is sent, and only to your mini PC.

### Setting up the Pi (when it arrives)

1. **Flash the SD card** with **Raspberry Pi Imager** (free, from raspberrypi.com) on
   your computer. Choose *Raspberry Pi 4* → *Raspberry Pi OS Lite (64-bit)*. Before
   writing, open the settings (⚙ or "Edit settings") and set:
   - hostname: `bolt`
   - a username and password
   - your Wi-Fi name and password
   - **Services → Enable SSH**

   This is the "headless" setup: no screen or keyboard needed.
2. Put the card in the Pi, power it on, wait two minutes, then from the mini PC:
```bash
ssh your-username@bolt.local
```
3. On the Pi:
```bash
sudo apt install -y git && git clone https://github.com/thatlukeguy1/robotFriend.git
```
```bash
bash robotFriend/pi/install.sh
```
4. Check `robotFriend/pi/bolt.env` (especially `BRAIN_URL`), then watch Bolt's body run:
```bash
journalctl -u bolt-body -f
```

Wiring the microphone and amplifier is a separate step that we'll do together
when the parts arrive, including your first soldering. Until then, a USB
microphone and speaker will work for testing.

### Testing without a Pi

You can run the body on any computer, using a recording instead of a microphone:

```bash
cd pi && python -m bolt_body.main --mic-file test.wav --speaker-folder out/
```

### The wake word: "Hey Bolt"

For now the body uses `hey_jarvis`, which comes ready-made. "Hey Bolt" needs a
**custom model**: openWakeWord can train one from computer-generated voices
saying "Hey Bolt" thousands of different ways. That's done in Google Colab (free,
in your browser) and takes about an hour. The result is one small file,
`hey_bolt.onnx`: put it in `pi/` and set `WAKE_MODEL=hey_bolt.onnx` in `bolt.env`.

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
