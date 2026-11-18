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
2. Raspberry Pi 5 with mic and speaker: it talks
3. Round screen (GC9A01) with animated eyes
4. Camera: reacts when you sit down, then mood
5. Home Assistant control (HA runs in Docker on a mini PC)
6. Brass-rod frame (circuit-sculpture style)

## Run on a server (Docker)
```bash
cp .env.example .env   # then add your API key
docker compose up -d --build
# then open http://<mini-pc-address>:8770 in a browser
```

## Quick start (laptop)
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python main.py
```
