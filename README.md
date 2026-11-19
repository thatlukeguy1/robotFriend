# Robot Friend

A small physical desktop companion robot that uses AI (Claude Haiku for everyday
chat, handing hard questions to Claude Opus) to chat, keep
reminders, notice when you sit down, read your mood through a camera, and
control your smart home (Home Assistant).

**New here? Start with [LEARN.md](LEARN.md).**

## Roadmap
1. ✅ **Brain:** text chat, reminders, Haiku + Opus routing
1b. ✅ **Brain as a web server** in Docker on the mini PC, with a chat page (`server.py`)
1c. ✅ **Reminders buzz your phone** through Home Assistant
1h. ✅ **The Studio** (`/studio`): design Bolt's face and personality
1g. ✅ **Locked:** password for browsers, a key for the Pi
1f. ✅ **Long-term memory** you can see and edit (🧠 on the chat page)
1e. ✅ **Smart home control** via Home Assistant (locks blocked)
1d. ✅ **Voice:** Whisper (ears) and Piper (mouth) in Docker, shared with Home Assistant
2. Raspberry Pi 4 with mic and speaker: it talks (software ready in `pi/`; waiting for parts)
3. One 2.8" ILI9341 screen with an animated face: eyes, brows and a mouth (designed in the Studio at `/studio`; waiting for the screen)
4. Camera: reacts when you sit down, then mood
5. ✅ Home Assistant control (done early, see 1e)
6. Body: a box for the Pi and speaker, a servo neck, and a head with the screen, camera and mic (brass frame)

## Run on a server (Docker)
```bash
cp .env.example .env   # then add your API key
docker compose up -d --build
docker exec -it bolt python -m robot_friend.security set-password
# then open http://<mini-pc-address>:8770 in a browser
```

## Quick start (laptop)
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python main.py
```
