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

**Safety:** Bolt is locked with a password (see "The lock" below). Even so,
**never** set up "port forwarding" for 8770 on your router: the lock is for your
home network, not the whole internet.

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

**Talking while thinking.** Bolt doesn't wait for Claude's whole reply any more.
Each sentence is turned into speech the moment Claude finishes writing it, and
played straight away while Claude carries on (read "Talking while thinking" in
`server.py` and the LESSON in `robot_friend/sentences.py`). In testing, Bolt
started talking after about 2 seconds instead of 4½.

**How long does each step take?** After you talk to Bolt, the chat page shows it
under what Bolt heard: *heard in* (Whisper), *first words* (how long until Claude's
first sentence was ready) and *talking after* (from letting go to hearing Bolt).
The same goes in the log: `docker logs bolt | grep "voice:"`. Speed up whichever is slowest:

| Slow step | What to try (in `.env`, then `docker compose up -d`) |
|---|---|
| **heard in** (Whisper) | `WHISPER_MODEL=tiny-int8`: about twice as fast, slightly more mistakes |
| **thought** (Claude) | Usually the internet or a hard question (watch for the expert being asked) |
| **voiced** (Piper) | Use a `low` voice instead of `medium` in `PIPER_VOICE` |

`WHISPER_BEAM=1` (the default) makes Whisper try one guess instead of several:
measured about 15% faster with the same words.

**Accuracy tips** (in `.env`):

- `WHISPER_OPTIONS=--vad-filter` throws away silence and background noise before
  Whisper listens. It stops Whisper inventing words like "Thank you." from hiss.
- `WHISPER_HINT=` lists words Whisper should expect: names, rooms, devices
  (e.g. `WHISPER_HINT=Bolt. Home Assistant. Amy. Desk lamp. Logs.`). It *may*
  help with tricky words; it isn't guaranteed.
- Bolt is told its words come from speech recognition, so it works out what
  you meant from small mistakes ("ham assistant logs").

### Talking from your phone

Hold the 🎤 button, speak, and let go. Bolt shows what it heard, replies, and talks back.

**Microphone:** browsers only allow it on secure `https://` pages. Once your phone
trusts Bolt's HTTPS stamp (see "HTTPS" below), it just works. Before that:

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

## Bolt's face

Bolt has **one 2.8" screen** (320 × 240) showing two rounded-square eyes,
eyebrows and a small mouth. The face is drawn by code about 60 times a second.
Read the LESSON at the top of `web/face.js`.

| File | What it does |
|---|---|
| `web/expressions.json` | **The personality of the face.** Every expression as a handful of numbers |
| `web/face.js` | Draws the face in a browser (the chat page, login page and Studio) |
| `web/studio-face.js` | The Studio's Face tab |
| `pi/bolt_body/face.py` | Draws the same face in Python, for the robot's screen |

Both drawing programs read the same `expressions.json` and use the same maths,
so what you design on your phone is what the robot will show. To check the
Pi's version: `cd pi && python -m bolt_body.face preview face.png`.

### The Studio: Face tab

Open **`http://192.168.4.58:8770/studio`**, or tap **🎨** (or Bolt's eyes) on the chat page.
The **Face** tab is where you design it.
The eyes stay pinned at the top while you scroll, so you always see your changes.

- **Expressions:** tap one to edit it. **Add** makes a new one (a copy of the
  current one, so you start from something). **Delete** removes one you made;
  the seven Bolt needs can't be deleted.
- **Both eyes / Left / Right:** choose which eye the sliders change. When the
  eyes are set differently, "eyes differ" shows next to that slider. **Make both
  eyes match** undoes one-eye changes for that expression.
- **Eyebrows only when they matter:** brows are hidden normally and **fade in**
  for moods that use them (thinking and confused, to start with). Each expression
  has a **Show eyebrows** slider (0 = hidden), plus raise, arch and tilt.
- **Mouth:** each expression can make it smile, frown, open or change width. The mouth also opens and
  closes by itself in time with Bolt's voice.
- **Colours and shape:** eye, ring, pupil, shine, eyebrow, mouth, screen and
  eyelid colours, and the face's layout: eye size, how rounded the corners are,
  spacing, brow thickness, mouth position. These apply to every expression.
- **Pretend to talk:** makes the eyes bob like they do when Bolt speaks.
- **Bob** works in every expression: along with Bolt's voice while it talks,
  and a slow "breathing" bob the rest of the time.
- **Each eye can blink at its own speed.** If both are the same, they blink together.
- **Calm mode:** if your phone is set to reduce motion ("Remove animations" on
  Android), the chat page moves Bolt's eyes half as much. The studio always
  shows full movement, so you can design it properly.

### Saving

**Save to Bolt** sends your design to the brain. It's **checked first** (see the
LESSON in `robot_friend/expressions.py`), so a broken value can't break the eyes:
you'll get a message saying what's wrong instead. It's saved in Bolt's data
folder, next to reminders and memories, so it survives rebuilds. The chat page
uses it straight away, and the Pi will fetch it from the brain.

- **Undo save** goes back to the design before your last save.
- **Original** goes back to the design that came with the code. (Undo save
  brings yours back.)
- Unsaved changes are kept in your browser, so closing the page doesn't lose them.

Saved designs live on the mini PC, not GitHub. To keep one in the project too,
press **Copy design** and send it to Claude.

### On the chat page

The little eyes next to Bolt's name now react: they **listen** while you hold 🎤,
**think** while Bolt works out a reply, **bob along** while it talks, look
**happy** when it answers, and **confused** when something goes wrong.

### Ideas to try

- Change `iris` in `colors` to Bolt's favourite colour.
- Make `sleeping` look up instead of down, or give `thinking` a wonky lid.
- Add a brand new expression, like `"surprised"`, with `open: 1` and a tiny `pupil`.

## The lock: passwords and keys

Bolt controls your home, remembers things about you and can change its own
eyes, so it's locked. Read the LESSON at the top of `robot_friend/security.py`:
it explains password **hashing**, **cookies** and **API keys**.

| Who | How they get in |
|---|---|
| You, in a browser | Log in once with your password. That browser stays logged in for a year. |
| The Pi | Sends its secret **key** with every request. |
| Anyone else on your Wi-Fi | They can't. They only see the login page. |

**Locked by default:** until a password is set, Bolt does nothing except show
how to set one.

### Setting the password (once)

```bash
docker exec -it bolt python -m robot_friend.security set-password
```

Type it twice (nothing shows while you type, which is normal). Use at least 8
characters; a few random words is good. The password itself is never saved,
only a **hash** of it.

Run the same command any time to **change** it. That logs every browser out.

### Logging out

Tap 🔒 on the chat page, or **Log out** in the Studio.

### The Pi's key

```bash
docker exec bolt python -m robot_friend.security show-key
```

Put the result in `BOLT_KEY=` in the Pi's `bolt.env`. If it ever leaks, make a
new one (the old one stops working straight away):

```bash
docker exec bolt python -m robot_friend.security new-key
```

### Things the lock does for you

- 5 wrong passwords and that device has to wait 5 minutes, so guessing is slow.
- Other websites can't use your logged-in browser to control Bolt.
- `/health` stays open, so Uptime Kuma can still check Bolt is running.

## Bolt's personality

You can't *train* Claude: Anthropic trained it, and that's fixed. What you can
change is its **instructions** (the "system prompt") that it reads at the start
of every conversation. Read the LESSON at the top of `robot_friend/personality.py`.

The prompt has two parts:

| Part | What's in it | Can you change it? |
|---|---|---|
| **Character** | Bolt's name, who it is, how it talks | ✅ Yes, in the Studio |
| **Rules** | How to use reminders, the smart home, memory and the expert, and that it's spoken out loud | 🔒 No. Change these and features break |

### The Studio: Personality tab

Open **`http://192.168.4.58:8770/studio#personality`**.

1. **Start from** a ready-made personality (cheerful sidekick, dry-witted butler,
   curious science buddy, calm companion, pirate robot), or the original.
2. Change the **name**, **who Bolt is** and **how Bolt talks** however you like.
3. **Try it out** in the test chat. It uses your unsaved text, so you can hear the
   new Bolt first. (Test chats can't set reminders or touch the lights.)
4. **Save to Bolt.** Bolt starts a fresh conversation with its new personality.
   **Undo save** and **Original** work like they do for the eyes.

Open **Protected rules** to see exactly what's always added. If your personality
asks for something the rules forbid (like long lists, which don't work out loud),
the rules win.

### Tips for writing a personality

- **Describe, don't list rules.** "Gentle and patient, never pushy" works better
  than "Rule 1: be nice."
- **Say how it should sound,** not just what it should do: "dry humour", "short
  sentences", "calls you captain".
- **Keep it short.** A few sentences is plenty; Bolt reads it every conversation.
- **Test with tricky questions:** "I'm having a bad day", "tell me a joke",
  "turn on the lights" (in a real chat).

## HTTPS: encrypting Bolt's conversations

Read the LESSON at the top of the `Caddyfile`. In short:

- **Caddy** is a small web server that now sits **in front of** Bolt. It does the
  encryption and passes requests on to Bolt inside Docker. Bolt itself can no
  longer be reached directly.
- Caddy runs its own **certificate authority** (a private "stamp of approval")
  because no public company will vouch for a home address like 192.168.4.58.
- Each device that should trust Bolt gets a copy of the **public** stamp,
  `bolt-ca.crt`, once. It's safe to share: it can *check* Bolt's certificate but
  can't make one.

Bolt's address is now **`https://192.168.4.58:8770`** (note the **s**).

### Switching over (on the mini PC)

```bash
cd ~/robotFriend && git pull && docker compose up -d --build --remove-orphans
```

Check the stamp's **fingerprint** (a unique code for it). You'll compare
against this on each device, so you know nobody swapped the file on the way:

```bash
docker exec bolt python -m robot_friend.security ca-fingerprint
```

### Your phone (Android)

1. Open `https://192.168.4.58:8770/bolt-ca.crt` in Chrome. It will warn that the
   connection isn't private: that's expected **this once**, because your phone
   doesn't trust the stamp yet. Tap **Advanced → Proceed**, and save the file.
2. **Settings → Security & privacy → More security settings → Encryption &
   credentials → Install a certificate → CA certificate**, then pick `bolt-ca.crt`.
   Android will warn you about installing a certificate authority. That's the
   right warning for a stranger's certificate, and fine for your own Bolt.
3. Restart Chrome and open `https://192.168.4.58:8770`. No warning, and the 🎤
   works without the Chrome flag (you can turn that flag off again).

Android may show "Network may be monitored" afterwards. That just means a
certificate authority you installed yourself is present.

### The Pi

```bash
cd ~/robotFriend && git pull
```

```bash
curl -sk https://192.168.4.58:8770/bolt-ca.crt -o ~/robotFriend/pi/bolt-ca.crt
```

```bash
openssl x509 -in ~/robotFriend/pi/bolt-ca.crt -noout -fingerprint -sha256
```

The fingerprint **must match** the one the mini PC printed. Then in
`~/robotFriend/pi/bolt.env` set:

```
BRAIN_URL=https://192.168.4.58:8770
BOLT_CA=/home/luke/robotFriend/pi/bolt-ca.crt
```

Test it (it should print `{"robot": ..., "status": "ok"}`):

```bash
curl --cacert ~/robotFriend/pi/bolt-ca.crt https://192.168.4.58:8770/health
```

### Things that change

- **Old `http://` bookmarks stop working.** Use `https://`.
- **Uptime Kuma:** change the monitor to `https://192.168.4.58:8770/health` and
  tick **Ignore TLS/SSL errors** (or give it the stamp).
- **Login cookies are now HTTPS-only,** so they can't leak over plain HTTP.

## The brass frame template

Bolt is a **hollow brass retro PC**: a CRT-monitor head on a swivel foot, sitting
on a desktop-case base. No panels, so every part and wire is on show
(`docs/frame/concept.png` shows how it should look).

`docs/frame/frame-template.pdf` is a **full-size bending template** on two A4
sheets: sheet 1 is the CRT head, sheet 2 is the base, the neck and the cut list.
Lay the tube on a shape and bend it to follow the grey band; the red ticks show
where each bend starts and ends. Sheet 1 also says what order to solder it in.

**Building order that works:** the screen ring (test-fit the screen), then the
bezel rings with the screen ring inside, then the back ring and the slanted
struts, then the base box. Leave the neck until last: test the head's balance
point on a pencil before soldering the axle.

**The touch bar: pat her on the head to wake her.** The screen's touch layer needs a
firm press (it's the "resistive" kind), so the frame gets its own touch spot: a low
upside-down "U" of 3 mm tube on top of the **middle** bezel ring, just behind the camera's
cradle so the two don't collide (60 mm long, 8 mm legs; it's in the cut list, and
`docs/frame/concept.png` shows where). A tiny **capacitive touch sensor** (TTP223, the same idea as a phone
screen) feels your hand through it, as lightly as a phone.

* **Glue it, never solder it.** The bar must not touch the rest of the frame: stand its
  legs on two nylon spacers and fix them with 5-minute epoxy. If it touched the frame,
  the sensor would "feel" the whole robot and the wiring inside it, and never settle.
* **One thin wire** runs from one leg, inside the head and down the neck sleeve, to the
  sensor's pad. The sensor board sits on a nylon standoff in the base.
* **Sensor wiring:** VCC to 3.3 V, GND to GND, I/O to a free GPIO (the code for it comes
  when the frame does; the touch screen keeps working too).
* **Test before gluing:** wire the sensor to the loose bar on the bench and check a light
  touch lights the sensor's LED, and that it goes off again when you let go.

**Buying and cutting the tube.** The whole frame is **4 mm tube** (5 mm only comes in
200 mm lengths, too short for anything ring-shaped), bought in **400 mm lengths: 10 of
them**, which is 9 plus a spare. Cut each length like this, longest piece first, adding
~10 mm to each piece for trimming after bending:

| Length | Cut from it |
|---|---|
| 1, 2 | a bezel ring (367) + a side spoke |
| 3, 4 | a base ring's long U (357) + a bezel strut |
| 5 | the screen ring (277) + a base cross bar |
| 6 | the back ring (222) + the other cross bar |
| 7 | head axle, tilt yoke, both base back pieces (70), 2 bezel struts |
| 8 | both top taper struts, one bottom taper strut + 3 base posts |
| 9 | the other bottom taper strut, the last base post + the 2 bottom spokes; the rest (about 230 mm) is your offcut for mistakes |
| 10 | spare: only needed if a bezel ring or base U goes wrong |

**The two joints on each base ring.** A base ring is 428 mm, longer than any tube, so it's a
long U (front, sides and corners) plus a straight 70 mm back piece, joined on the back
straight where nobody sees. Join with an **inner sleeve**: a 20 mm piece of 3 mm tube
pushed halfway into each end, soldered, then filed smooth. Check a 3 mm tube slides snugly
inside your 4 mm one before you buy (it does when the 4 mm tube's wall is 0.45 mm thick).

**Because it's hollow, the wiring is part of the look.** Plan it before you
solder: one black braided sleeve from the head down the neck, short wires inside
the case, nylon standoffs under every board (brass conducts electricity!).

1. **Print at 100% / "Actual size"**, never "Fit to page", and check the 70 mm
   line with a ruler before you trust anything else on the sheet.
2. **Measure your real parts first,** especially the screen board. The sizes are
   published ones, not measured.
3. To change a size, edit the numbers at the top of `docs/frame/make_template.py`, then:

```bash
python3 docs/frame/make_template.py && node docs/frame/print_pdf.js
python3 docs/frame/make_concept.py && node docs/frame/render_concept.js
```

## Power: one supply for the whole robot

Bolt runs from **one 5 V power brick**. The rule that makes that safe:

> **Every part takes its power from the rail, never through another part.**
> Servos must never be powered from the Pi's 5 V pin.

**Why?** When a servo starts moving it gulps current for a split second. If that
gulp comes through the Pi, the voltage on the Pi dips, and the Pi reboots or
damages its SD card. Fed from the rail, the gulp comes straight from the brick.

### How much power? (the "power budget")

| Part | Typical | Worst moment |
|---|---|---|
| Pi 4 + camera + screen + fan | 1.2 A | 2.5 A |
| Speaker amp (MAX98357A, loud) | 0.3 A | 1.0 A |
| Two MG90S micro servos | 0.3 A | 1.4 A |
| **Total** | **about 2 A** | **about 5 A** |

So the brick must give **5 A or more**: a **5 V 6 A** brick (for example a Mean
Well GST36E05). The official Pi charger (3 A) is fine for testing, not for the
finished robot. Aim for 5.1 to 5.25 V, because a little is lost in the wires.

### The wiring

```
5V 6A brick ──► fuse (5A) ──► power rail (Wago / terminal block)
                                 ├──► USB-C pigtail ──► Pi 4
                                 ├──► servo board V+   (+ 1000 µF capacitor across V+ and GND)
                                 └──► amp VIN
                all the minus (GND) wires join at the rail too
```

1. **Fuse straight after the brick.** In a hollow brass frame, a bare wire
   touching the brass is a short circuit. The fuse blows instead of the wiring melting.
2. **Feed the Pi through its USB-C socket** with a USB-C-to-screw-terminal lead,
   not the GPIO 5 V pin. The USB-C socket keeps the Pi's own protection in use.
3. **The 1000 µF capacitor** sits on the servo board's power terminal. It's a tiny
   tank of electricity that covers each servo's gulp. Electrolytic capacitors have
   a minus stripe: that leg goes to GND. **Backwards, they can pop.**
4. **Join all the grounds.** The Pi talks to the servo board with signals measured
   against GND, so they must share it.
5. **Thick (20 AWG), short wires** from the brick to the rail. Thin, long wires
   waste voltage; the Pi then shows a lightning-bolt warning.

### Is it working? Ask the Pi

```bash
vcgencmd get_throttled
```

`throttled=0x0` means the power has been fine since the Pi started. Anything else
means the voltage dipped at some point: check the wiring, the capacitor and the brick.

### The code helps too (coming with the servo code)

- **Big moves use one servo at a time**, easing in and out, so the current never spikes
  much. Small gestures (a nod, a head tilt) may use both: the power budget above
  already allows for both servos at once.
- **A servo's signal switches off once it's in place**, so it stops buzzing and
  drawing current while Bolt sits still.
- **Bolt checks for power warnings** and writes them in its log.

## Body language: moving with her moods (the servo plan)

Riley's two servos aren't only for looking around: moving when she *feels* something is
what makes a robot seem alive (it's why Huy Vector's WALL-E is so charming). So every
mood the face already shows gets a matching head movement.

**The two servos:** **pan** turns her head left and right (on the turntable in the base);
**tilt** nods it up and down (the axle through the tilt yoke).

| When | Head movement | Why it reads well |
|---|---|---|
| "Hey Riley" | turns towards you (the middle, until she can tell where you are), lifts slightly | "I'm listening to *you*" |
| Listening | tiny slow nods every few seconds | how people show they're following |
| Thinking | tilts to one side and up a little, with the 🤔 hand | the classic "hmm" pose |
| Speaking | small bobs on the louder words (from the same loudness the mouth uses) | speech without a body looks stiff |
| Happy | a quick double bob | a little bounce of joy |
| Confused / didn't catch that | head tilt to the side, held, then back | a dog's puzzled look |
| "No" / can't do that | a small, slow shake | |
| Reminder going off | a lift and a look around, then towards you | "excuse me!" |
| Idle | a slow glance left or right now and then, like the eyes | so she never looks frozen |
| Dozing off | the head sinks slowly forward, over about 3 seconds | |
| Waking up | lifts back up, a little faster | |
| Turning off (screen held) | sinks forward and stays down | goodnight |

**How it's built (the plan for the code):**

* **Poses live in the face design**, next to each expression's eye and mouth settings:
  `headTurn`, `headTilt` and `nod` (how much it nods while in that mood). The Studio's
  Face tab gets sliders for them, so you design a mood's look *and* its posture together.
  Everything eases from pose to pose, the same way the eyes do.
* **The eyes lead, the head follows.** When she glances, her eyes move first and the head
  follows a moment later, only part of the way. That's how real heads move, and it saves
  the servos a lot of work.
* **Gentle on the servos:** small angles (the whole range is about ±40° turn and ±20°
  tilt), soft starts and stops, and the signal switches off once she's still, so nothing
  buzzes or warms up.
* **Movement settings in the Studio's Body tab:** on or off, how big the moves are, and how
  often she glances around while idle.
* **Safe limits in code,** like the other Body settings: no setting can drive a servo
  past the frame's stops.

**Later, with the camera (and maybe the second mic):** turning towards whoever is
speaking. The camera can find a face; two microphones a few centimetres apart can tell
left from right by which one hears you first. Until then she turns to the middle.

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
4. Edit `robotFriend/pi/bolt.env`: check `BRAIN_URL`, and put the brain's key in
   `BOLT_KEY` (see "The Pi's key" above). Then restart and watch Bolt's body run:
```bash
sudo systemctl restart bolt-body
```
```bash
journalctl -u bolt-body -f
```

Wiring the microphone is a separate step, for when it arrives. The speaker
amplifier comes first, below, with your first soldering.

### First soldering: the speaker amplifier (MAX98357A)

The amp arrives with a loose strip of pins (a "header") that you solder on. It's
the perfect first job: small, cheap if it goes wrong, and you'll hear if it worked.

**Before you start**
- Iron at **330 °C** for leaded solder, **360 °C** for lead-free. Hotter isn't
  better: it burns the flux and lifts the board's copper pads.
- Wet the tip cleaner, tin the tip (melt a little solder onto it), ventilate,
  safety glasses on.

**Soldering the header**
1. Push the header's **long** pins into a breadboard (or hold them in the helping
   hands), then sit the amp on top, pins poking up through its holes.
2. Touch the iron to **both the pin and the copper pad** for 1 to 2 seconds.
3. Feed solder into the joint (the pin and pad, **not** the iron). Stop when it
   flows round the pin. Lift the solder, then the iron.
4. A good joint is a shiny little **volcano** hugging the pin. A ball sitting on
   top means the pad wasn't hot enough: reheat it with a dab of flux.
5. Do the two end pins first, check the board sits flat, then the rest.
6. **Check for bridges** (solder joining two pins): the multimeter's beep mode
   between neighbouring pins should stay silent.

**Wiring it to the Pi** (Pi switched OFF; jumper wires are fine for testing)

| Amp pin | Pi pin | What it carries |
|---|---|---|
| VIN | pin 2 (5V) | power (fine for testing; the finished robot uses the power rail) |
| GND | pin 6 (GND) | ground |
| BCLK | pin 12 (GPIO 18) | the "beat": one tick per bit of sound |
| LRC | pin 35 (GPIO 19) | says "left" or "right" sample |
| DIN | pin 40 (GPIO 21) | the sound itself, as numbers |
| GAIN, SD | leave empty | default volume, and both channels mixed together |

Speaker **+** and **−** go to the amp's two speaker terminals (red wire to +).

**LESSON: I2S.** The Pi sends sound as numbers down three wires: a clock (BCLK),
a left/right flag (LRC) and the data (DIN). The amp turns the numbers back into a
voltage and drives the speaker. No analogue wiring, so no hiss.

**Telling the Pi about the amp**
```bash
sudo nano /boot/firmware/config.txt
```
At the bottom, add this line, save (Ctrl+O, Enter, Ctrl+X) and reboot:
```
dtoverlay=max98357a
```
```bash
sudo reboot
```
Then check it's there and play a test voice:
```bash
aplay -l
```
```bash
speaker-test -D plughw:CARD=MAX98357A -c 2 -t wav -l 1
```
You should hear "front left… front right". If `aplay -l` shows a different card
name, use that name instead, and put it in `SPEAKER_DEVICE` in `pi/bolt.env`.

**If it's silent:** check BCLK/LRC/DIN aren't swapped (the most common mistake),
check every joint with the meter, and check the speaker wires are tight.

### Second job: the microphone (INMP441)

Do this **after** the speaker works, so if something breaks you know which part did it.

**Soldering:** the same as the amp: header pins, volcano joints, check for bridges.
One extra rule: the microphone listens through a **tiny hole** in the board. Keep
solder, flux and fingers away from it, and never blow on it to cool a joint.

**Wiring** (Pi OFF). The mic and the amp **share** the clock wires: both listen
to the same "beat", one talks and one listens.

| Mic pin | Pi pin | Notes |
|---|---|---|
| VDD | pin 1 (**3.3V**) | **NOT 5V.** 5V can kill the mic instantly |
| GND | pin 9 (GND) | |
| L/R | pin 9 too (GND) | GND = "I'm the left channel" |
| SCK | pin 12 (GPIO 18) | shared with the amp's BCLK |
| WS | pin 35 (GPIO 19) | shared with the amp's LRC |
| SD | pin 38 (GPIO 20) | the mic's sound, going IN to the Pi |

Two wires on one Pi pin: use a breadboard, or a jumper wire with a "Y" splice.

**Telling the Pi about BOTH.** The amp-only line can't record, so swap it for one
that does both (it was made for Google's voice kit, which used these same chips):
```bash
sudo nano /boot/firmware/config.txt
```
Change `dtoverlay=max98357a` to:
```
dtoverlay=googlevoicehat-soundcard
```
```bash
sudo reboot
```
Check the new card's name, then record five seconds and play it back:
```bash
arecord -l
```
```bash
arecord -D plughw:CARD=sndrpigooglevoi -c 1 -r 16000 -f S16_LE -d 5 test.wav
```
```bash
aplay -D plughw:CARD=sndrpigooglevoi test.wav
```
If the card name is different, use the one `arecord -l` shows, here and below.

**Making it everyone's default, with a converter.** The card itself only works
at one speed (48,000 samples a second, in stereo). Bolt listens at 16,000 in mono
and Piper speaks at 22,050. ALSA's **plug** layer converts between them, so we
make "plug + this card" the Pi's default sound device:
```bash
sudo nano /etc/asound.conf
```
```
pcm.!default {
    type asym
    playback.pcm "plughw:CARD=sndrpigooglevoi"
    capture.pcm "plughw:CARD=sndrpigooglevoi"
}
ctl.!default {
    type hw
    card sndrpigooglevoi
}
```
Leave `MIC_DEVICE` and `SPEAKER_DEVICE` **empty** in `pi/bolt.env`: Bolt then
uses the default, converter included. (Naming the card there would skip the
converter, and Bolt would complain about the sample rate.)

**"Error querying device -1" when you start Bolt by hand?** Bolt's background
service already has the mic open (only one program can record at once). Either
watch the service with `journalctl -u bolt-body -f`, or stop it first with
`sudo systemctl stop bolt-body`.

**If the recording is silent:** check VDD is on 3.3V, SD is on pin 38 (not 40,
that's the amp's), and L/R is on GND. **If it's very quiet,** that's normal for
this mic; we'll turn it up in software.

**Heatsinks:** wipe the Pi's chips with a little isopropyl alcohol first, then
press each heatsink on for 10 seconds: the big one on the processor (the square
silver chip), the others on the memory and the USB chip beside it.

### Bolt's face on the screen (ILI9341, 2.8")

Wire it with the Pi **off** (USB sockets on your right, counting from the left):

| Screen | Pi pin | Where |
|---|---|---|
| VCC | 4 (5 V) | edge row, 2nd |
| GND | 20 | edge row, 10th |
| CS | 24 | edge row, 12th |
| RESET | 22 | edge row, 11th |
| DC | 18 | edge row, 9th |
| SDI (MOSI) | 19 | inner row, 10th |
| SCK | 23 | inner row, 12th |
| LED | 16 (GPIO 23) | edge row, 8th: a pin the Pi can switch, so the screen can turn off (pin 17 = always on) |

Switch on SPI and test it:
```bash
sudo apt install -y python3-spidev && sudo raspi-config nonint do_spi 0 && sudo reboot
```
```bash
cd ~/robotFriend/pi && .venv/bin/python -m bolt_body.screen test
```
- **Completely dark:** no power: check VCC, GND and LED with the multimeter (5 V and 3.3 V).
- **White but no picture:** the data isn't arriving: beep-test CS, RESET, DC, SDI and SCK.
- **Speckles or stripes:** slow it down with `SCREEN_MHZ` in `bolt.env` (12 is the default).

Once it works, Bolt's body animates the face by itself (read the LESSON in
`pi/bolt_body/animate.py`): **idle** while waiting, **listening** after the wake word,
**thinking**, **speaking** with the mouth following the voice, **confused** if something
went wrong, and **sleeping** after `SLEEP_AFTER_MINUTES` with nobody talking. Designs you
save in the Studio are used next time Bolt's body starts.



### The touch screen

Riley's screen has a second chip for touch (the **XPT2046**). It only needs to know
*whether* you're touching it, not where, so there's nothing to calibrate:

* **Tap** (under a second): she wakes up and listens, like "Hey Riley". Tapping while
  she's talking stops her.
* **Hold for 5 seconds**: she turns the Pi off safely. A ring fills up while you hold;
  let go before it's full and nothing happens.

Both timings are in the Studio's **Body** tab: **ignore touches shorter than** (raise it
if brushes or the cat wake her) and **seconds to hold to turn her off**.

**Wiring** (Pi **off**; same counting as above). Two of these share a pin with the screen,
so use Y-cables like you made for the mic:

| Touch pin | Pi pin | Where |
|---|---|---|
| T_IRQ | 15 (GPIO 22) | inner row, 8th: goes LOW when you touch |
| T_CS | 26 (CE1) | edge row, 13th: the touch chip's own "chip select" |
| T_DO | 21 (MISO) | inner row, 11th: the touch chip talking back |
| T_DIN | 19 (MOSI) | **shared** with the screen's SDI |
| T_CLK | 23 (SCK) | **shared** with the screen's SCK |

The touch chip gets its power from the screen's own VCC and GND, so no extra power wires.

**Let her turn the Pi off** (once): the body needs permission to shut down without a
password. Run `bash ~/robotFriend/pi/install.sh` again, or just:

```bash
echo "$USER ALL=(root) NOPASSWD: /usr/bin/systemctl start bolt-body, /usr/bin/systemctl stop bolt-body, /usr/bin/systemctl restart bolt-body, /usr/bin/systemctl poweroff" | sudo tee /etc/sudoers.d/bolt-body && sudo chmod 440 /etc/sudoers.d/bolt-body && sudo visudo -c
```

**Test it** (stop Riley first so the test can use the wire):

```bash
sudo systemctl stop bolt-body
cd ~/robotFriend/pi && .venv/bin/python -m bolt_body.touch test
```

Tap and hold: it prints `down`, `tap`, `holding: 25%`... `off`. (The test only prints; it
doesn't turn anything off.) Ctrl+C, then `sudo systemctl start bolt-body`.

**Have to press really hard?** First peel off the clear protective film if it's still on.
Then compare the two "pull-up" settings (stop Riley first, as above). It counts your light
taps both ways, and checks for touches that happen by themselves:

```bash
cd ~/robotFriend/pi && .venv/bin/python -m bolt_body.touch compare
```

If "OFF" catches more light taps and 0 by themselves, add `TOUCH_PULL_UP=off` to `bolt.env`.
(This kind of screen always needs a firm press: it works by pressing two layers together.
A fingernail or the tip of a pen cap works with much less force than a fingertip.)

**After turning off:** wait for the Pi's green light to stop flashing, then switch the
power off. To turn her back on, switch the power on again.

### The camera (Camera Module 3)

Riley's camera does two jobs, kept very different on purpose (read the LESSON in
`pi/bolt_body/camera.py`):

* **Noticing you (stays on the Pi).** Twice a second it compares two tiny grey pictures.
  If a person-sized chunk changes for about 1.5 seconds, her face wakes up and the screen
  comes back on. Lights switching on don't count. No picture leaves the Pi for this.
* **Looking when asked (goes to Claude).** "Riley, what's this?", "what can you see?",
  "read this label": she focuses, takes one photo, and Claude looks at it. Photos are only
  taken when you ask, and none are kept. Ask her to read something by holding it about
  20 cm from the camera.

**Connecting it** (Pi **off**): the camera socket is the long thin one between the HDMI
sockets and the audio jack. Gently lift its plastic clip, slide the ribbon in with the
**silver contacts facing the HDMI sockets**, and press the clip back down. The ribbon
should sit straight and not pull out with a gentle tug.

**In the head:** the camera moves when her head does, so use a 30-50 cm cable with a gentle
loop at the neck (never a sharp fold), and clip it either side of the joint.

**Setting it up and testing** (on the Pi):

```bash
sudo apt install -y python3-picamera2
sudo systemctl stop bolt-body
cd ~/robotFriend/pi && .venv/bin/python -m bolt_body.camera test
sudo systemctl start bolt-body
```

The test saves a photo to `~/riley-photo.jpg` and then reports movement for 20 seconds
(keep still, then wave). If the photo is upside down, put `CAMERA_ROTATION=180` in
`bolt.env`. In the Studio's **Body** tab: **wake up when she sees someone** (on/off) and
**how small a movement** wakes her.

You can run the body on any computer, using a recording instead of a microphone:

```bash
cd pi && python -m bolt_body.main --mic-file test.wav --speaker-folder out/
```

### The wake word: "Hey Bolt"

"Hey Bolt" is a **custom model**: openWakeWord trains it from computer-generated voices
saying "Hey Bolt" in thousands of different ways, mixed with background noise and room
echo. It's done in Google Colab (free, in your browser, with a graphics card).

**Training it**
1. In Colab: **Runtime → Change runtime type**: **T4 GPU**, and an older **Runtime
   version** with **Python 3.12** (the newest Python breaks the training tools).
2. Paste all of `pi/training/train_wake_word_colab.py` into ONE cell and press ▶.
   Allow Google Drive when asked. Keep the tab open and click in it now and then.
3. It ends with `DONE!`, and `hey_bolt.onnx` lands in Google Drive (`bolt_wake_word`).

**Why that file has so many fixes in it:** the example notebook it's based on was
written for older versions of a dozen tools, and several have changed since (Python,
PyTorch, a moved dataset, a reorganised clip maker). Every fix has a comment saying why.
If training ever breaks again, it'll be another tool that moved: read the error from the
bottom up.

**Putting it on the Pi**
```bash
scp ~/Downloads/hey_bolt.onnx your-username@YOUR-PI-IP:~/robotFriend/pi/
```
Then in `pi/bolt.env`: `WAKE_MODEL=/home/your-username/robotFriend/pi/hey_bolt.onnx`, and
`sudo systemctl restart bolt-body`.

**Tuning it with the log.** `journalctl -u bolt-body -f` shows two kinds of line:
- `(wake word score 0.62)`: it woke up.
- `(nearly woke: score 0.41, needs 0.50)`: it heard something close, but not enough.

If your real "Hey Bolt"s keep nearly waking it, **lower** `WAKE_THRESHOLD` (we use 0.3).
If it wakes up by mistake, **raise** it. If no threshold works well, retrain with bigger
settings: `n_samples` 10000 and `steps` 50000 (openWakeWord's recommended size; about an
hour longer on Colab).

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

## Bolt reads your home's diary (logbook, history, errors, calendars)

(Read the second LESSON at the top of `robot_friend/home_assistant.py` first.)

Bolt has four new **read-only** tools. Looking never changes anything:

| Ask Bolt… | Tool it uses | What it reads from Home Assistant |
|---|---|---|
| "When did the back door last open?" | `home_logbook` | the logbook |
| "How cold did the lounge get last night?" | `home_history` | a sensor's history |
| "Why didn't my morning automation run?" | `home_error_log` | the error log |
| "What's on this week?" | `calendar_events` | every calendar HA knows about |

It can also list your **automations** and switch them on or off, because in HA an
automation is just another entity (`automation.morning_lights`).

**The locks are still invisible.** The same `HA_BLOCKED_DOMAINS` rule hides a lock's
logbook entries, history and error-log lines, so Bolt can't learn about the front
door by reading the diary instead.

**The error log needs an admin token.** HA only shows it to administrators. If
Bolt says "the error log needs a token made by an ADMIN user", make a new token while
logged in as an admin (your profile → Security → Long-lived access tokens).

**Privacy:** whatever Bolt reads is sent to Claude so it can understand it. Long logs
are trimmed and anything that looks like a password or token is blanked out first,
but logs can still contain things like names of people and places.

### Automations, scripts and scenes: checked before they run

(Read the LESSON "Automations, scripts and scenes" in `robot_friend/home_assistant.py`.)

Before Bolt runs one, it reads the recipe from Home Assistant and follows every step,
including other scripts and scenes it calls. If anything touches a lock, it refuses.
If it can't read the recipe, it refuses too.

| You ask… | What happens |
|---|---|
| "Run my morning automation" (lights only) | ✅ runs |
| "Run leaving home" (lights off **and** lock the door) | ❌ refused: it touches a lock |
| A script that runs a scene that unlocks the door | ❌ refused: Bolt checks all the way down |
| An automation written in a YAML file | ❌ refused: Bolt can't read it, so it can't check it |
| "Turn off the leaving-home automation" | ✅ allowed: on/off only decides whether it runs *by itself later* |

Reading recipes needs an **admin** token (the same as the error log).

### Closing the back doors

(Read the LESSON "Closing the back doors" in `robot_friend/home_assistant.py`.)

Checking before running still left two sneaky routes, so now:

| You ask… | What happens |
|---|---|
| "Turn off the night lock automation" | ❌ any automation that touches a lock is hidden, like a lock |
| "Turn off away mode" (and an automation unlocks the door when away mode goes off) | ❌ away mode is **read-only**: Bolt can tell you it's on, not change it |
| "Run going-out" (a script that flips away mode) | ❌ it changes a read-only helper, so it's hidden too |
| "Turn on the lights in the porch area" | ❌ Bolt must name devices one by one, never a whole area |
| "Turn on the desk lamp" | ✅ nothing about it can reach a lock |

Bolt works out this protected list itself, from your automations, and remembers it for
5 minutes. So if you change an automation in Home Assistant, Bolt notices within 5
minutes (or straight away if you restart Bolt).

**What Bolt still can't see:** automations written in YAML files. Bolt hides those
completely (better safe than sorry), but it can't tell what *they* watch. If a YAML
automation unlocks the door when a helper changes, move it into HA's editor (Settings →
Automations → ⋮ → Edit in YAML, paste, save) so Bolt can protect its helper too.

## Home Assistant talks through Riley

Any Home Assistant automation can make Riley say something out loud: "the washing's
finished", "someone's at the door", "it's going to rain". The brain has a door for it,
`POST /announce`, and Riley's body checks for new things to say every 3 seconds.

**1. Tell Home Assistant how to reach Riley.** Add this to HA's `configuration.yaml`:

```yaml
rest_command:
  riley_say:
    url: "https://192.168.4.58:8770/announce"
    method: POST
    headers:
      Authorization: !secret riley_key
    content_type: "application/json"
    payload: '{"message": {{ message | tojson }}, "rephrase": {{ (rephrase | default(false)) | tojson }}}'
    verify_ssl: false
```

and this to HA's `secrets.yaml` (the same key the Pi uses, from
`docker exec bolt python -m robot_friend.security show-key`, with `Bearer ` in front):

```yaml
riley_key: "Bearer paste-the-key-here"
```

`verify_ssl: false` is OK here because Home Assistant and Riley's brain are on the **same
mini PC**: the message never leaves the machine. The key still has to be right.

Then in HA: **Developer tools → YAML → Check configuration**, then **Restart**.

**2. Use it in any automation** (Settings → Automations → an action → "Call service"):

```yaml
action: rest_command.riley_say
data:
  message: "The washing machine has finished."
  rephrase: true
```

- `rephrase: true`: Riley says it in her own words and personality (she keeps the facts).
- leave it out: she says your exact words (a little quicker).

Try it straight away from **Developer tools → Actions → `rest_command.riley_say`**.

## Morning briefing

Say **"Hey Riley, good morning"** (or "what's on today?"). One tool, `morning_briefing`,
gathers everything at once, so she starts talking quickly:

- the **weather** now and today's forecast (from your first `weather.` entity in HA)
- today's **calendar** and today's **reminders**
- anything notable **overnight** from the logbook (doors, the alarm; routine sensor chatter is skipped)
- how many **errors** Home Assistant logged overnight (needs the admin token)

Each part is checked on its own, so if one is missing (say, no calendar) she still tells you
the rest. Change how she does it in the Studio's Personality tab: the rules are at the bottom.

## Stop!

Say **"Hey Riley"** while she's talking and she stops straight away and listens. While she's
talking she has to be extra sure it was her name (her own voice reaches the mic too), so say
it clearly.

## Christmas hat 🎅

Studio → **Body** tab → **Christmas hat**, then **Save**:

* **Automatic** (the default): she puts it on by herself on **25 November** and takes it
  off after **6 January** (Twelfth Night), every year. Dates that wrap round New Year are
  a nice puzzle: see `christmas_time()` in `robot_friend/body_settings.py`.
* **On** / **Off**: whenever you like.

It slides down onto her screen within 30 seconds (and onto the chat page and the Face
tab's preview). With the hat on, her sleepy Zs float from her other eye so they don't
hit the pom-pom.

### Stickers: how the hat and the thinking hand are drawn

They're **pictures**, not shapes worked out in code. Each one lives in `web/stickers/`:

* `hat.svg`, `hand.svg`: the drawings. SVG is a picture made of curves, so it stays sharp
  at any size. Open one in a web browser to see it big.
* `hat.png`, `hand.png`: the same, turned into ordinary pictures with see-through
  backgrounds by `make_stickers.js`. These are what Riley actually uses.
* `stickers.json`: where each one goes: how wide, which point of the picture sits where,
  its tilt, and whether it's coloured in her colour. The hand is drawn in greys and
  coloured at draw time ("tint"), so it matches whatever colours you give her face.

The Pi (`face.py`) and the browser (`face.js`) both just place, tilt and fade the
pictures, so they look the same everywhere. To nudge one, change its numbers in
`stickers.json` (e.g. `"y"` to move it down, `"width"` to make it bigger), then run
`git pull` and the update scripts as usual. To redraw one, edit its `.svg` and run
`node make_stickers.js` (or ask me).

Preview it without the Pi's screen: `python -m bolt_body.face preview hat.png hat`

## Backing Riley up

`backup.sh` saves everything that makes Riley *her* into one dated file: memories,
personality, reminders, face designs, body settings, her password and keys, the HTTPS
certificate authority, and `.env`. It keeps the newest 14. `restore.sh` puts one back.

```bash
bash ~/robotFriend/backup.sh
```

**Every night, automatically:** `crontab -e` (pick nano if it asks), and add this line at the
bottom (3:17am every night; change `luke` if your username is different):

```
17 3 * * * /home/luke/robotFriend/backup.sh >> /home/luke/riley-backups/backup.log 2>&1
```

**A second copy somewhere else** (a backup on the same disk can't survive that disk
dying): put the folder in front of the command, e.g. a USB stick:

```
17 3 * * * RILEY_BACKUP_COPY_TO=/media/luke/USB /home/luke/robotFriend/backup.sh >> /home/luke/riley-backups/backup.log 2>&1
```

**Restoring** (Riley's brain stops for a moment while it happens):

```bash
bash ~/robotFriend/restore.sh ~/riley-backups/riley-2026-11-23_0317.tar.gz
```

The backup holds passwords and API keys, so it's made readable by you only. Never upload it
anywhere public.

### A copy in Google Drive (encrypted first)

The backup holds your API key and passwords, so it is **scrambled on the mini PC before it
leaves** (gpg, AES-256, with a passphrase only you have). Google only ever sees noise. The
tool that does the uploading is `rclone`; Drive keeps the newest 14, like the local folder.

1. Install the tools: `sudo apt install -y rclone gnupg`
2. Make the passphrase (a long random one, readable by you only):
   `mkdir -p ~/.config/riley && (umask 077; openssl rand -base64 32 > ~/.config/riley/backup-passphrase)`
   Then `cat ~/.config/riley/backup-passphrase` and **save it in your password manager**.
   If the mini PC dies, that's the only way to unscramble the Drive copies.
3. Connect rclone to Drive: `rclone config`, then `n` (new), name `gdrive`, storage `drive`,
   leave client id/secret empty, scope `drive.file` (it can only see files it made), leave
   the rest as default, and say **yes** to auto config: a browser opens, sign in and allow.
4. Try it: `RILEY_BACKUP_CLOUD=gdrive:riley-backups bash ~/robotFriend/backup.sh`
   It should end with "Encrypted copy uploaded". Look in Drive for a `riley-backups` folder.
5. Every night: change your crontab line to
   `17 3 * * * RILEY_BACKUP_CLOUD=gdrive:riley-backups /home/luke/robotFriend/backup.sh >> /home/luke/riley-backups/backup.log 2>&1`

**Restoring from Drive:** `rclone copy gdrive:riley-backups/riley-2026-11-23_0317.tar.gz.gpg ~/`
then `bash ~/robotFriend/restore.sh ~/riley-2026-11-23_0317.tar.gz.gpg`. On a new machine
with no passphrase file it asks you to type it. A wrong passphrase stops before anything changes.
