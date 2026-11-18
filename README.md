# Robot Friend

A small physical desktop companion robot that uses AI (Claude) to chat, keep
reminders, notice when you sit down, read your mood through a camera, and
control your smart home (Home Assistant).

**New here? Start with [LEARN.md](LEARN.md).**

## Roadmap
1. ✅ **Brain on a laptop:** text chat and reminders (`python main.py`)
2. Raspberry Pi 5 with mic and speaker: it talks
3. Round screen (GC9A01) with animated eyes
4. Camera: reacts when you sit down, then mood
5. Home Assistant control (HA runs in Docker on a mini PC)
6. Brass-rod frame (circuit-sculpture style)

## Run on a server (Docker)
```bash
cp .env.example .env   # then add your API key
docker compose up -d --build
docker attach robot-brain   # detach: Ctrl+P, Ctrl+Q
```

## Quick start (laptop)
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python main.py
```
