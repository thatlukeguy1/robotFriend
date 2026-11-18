"""
Robot Friend: the brain as a web server.

Run it with:   python server.py
Then open      http://localhost:8770   in a browser.

LESSON: What's a server?
========================
Until now you typed straight into Bolt. Soon the Pi (Bolt's ears and mouth)
will live on your desk while the brain lives on the mini PC. They need a way
to talk across your home Wi-Fi. That's what a SERVER is for.

A server sits and waits for REQUESTS. Each request goes to an ADDRESS
(e.g. http://192.168.1.50:8770/chat), and the server sends back a RESPONSE.

  * 192.168.1.50 is the mini PC's address on your home network (its "street").
  * 8770 is the PORT (the "door number"). Home Assistant uses door 8123;
    Bolt uses 8770, so they don't bump into each other. Two programs can't
    share a door: if one is already using it, the second can't start.
  * /chat is the ROUTE: which job you want done.

The set of routes a server offers is called its API. Bolt's API:

  GET  /                  the chat web page (open it on your phone!)
  POST /chat              send {"text": "hi"}, get back {"reply": "..."}
  GET  /notifications     reminders that have gone off
  POST /voice             send a WAV recording, get back what you said,
                          Bolt's reply, and the reply as spoken audio
  POST /speak             send {"text": "..."}, get back Bolt's voice (WAV)
  POST /reset             start a fresh conversation
  GET  /health            "are you alive?" (used to check the server is up)

Requests and responses are written in JSON, a simple text format for data.
"""

import base64
import os
import threading
from datetime import datetime
from pathlib import Path

import anthropic
from flask import Flask, jsonify, request, send_file

from robot_friend.brain import Brain
from robot_friend.home_assistant import HomeAssistant
from robot_friend.personality import ROBOT_NAME
from robot_friend.reminders import ReminderStore
from robot_friend import voice

PORT = int(os.environ.get("PORT", "8770"))
WEB_PAGE = Path(__file__).parent / "web" / "index.html"


class Notifications:
    """A list of reminders that have gone off, each with a number.

    Each listener (your phone, later the Pi) remembers the last number it saw
    and asks "anything after number 7?". That way several listeners can all
    hear every reminder.
    """

    def __init__(self, keep=50):
        self._lock = threading.Lock()
        self._items = []
        self._next_id = 1
        self._keep = keep

    def add(self, text):
        with self._lock:
            self._items.append({"id": self._next_id, "text": text,
                                "time": datetime.now().isoformat(timespec="seconds")})
            self._next_id += 1
            self._items = self._items[-self._keep:]  # only keep the newest ones

    def after(self, last_seen):
        with self._lock:
            return [n for n in self._items if n["id"] > last_seen]


def create_app(brain, notifications, ears=None, mouth=None):
    # ears/mouth default to the real Whisper and Piper. Tests swap in pretend ones.
    ears = ears or voice.transcribe
    mouth = mouth or voice.synthesize

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # refuse recordings over 10 MB
    # Only one conversation at a time, so two requests can't mix up the memory.
    brain_lock = threading.Lock()

    @app.get("/")
    def page():
        return send_file(WEB_PAGE)

    @app.get("/health")
    def health():
        return jsonify(status="ok", robot=ROBOT_NAME)

    @app.post("/chat")
    def chat():
        data = request.get_json(silent=True) or {}
        text = str(data.get("text", "")).strip()
        if not text:
            return jsonify(error="Send some text, like {\"text\": \"hi\"}"), 400  # 400 = "bad request"
        reply, error = think(text)
        if error:
            return jsonify(error=error), 502
        return jsonify(reply=reply)

    def think(text):
        """Ask the brain. Returns (reply, None) or (None, an error message)."""
        try:
            with brain_lock:
                return brain.chat(text), None
        except anthropic.AuthenticationError:
            return None, "The API key isn't working. Check .env"
        except anthropic.APIConnectionError as e:
            return None, f"Can't reach Claude: {e.__cause__ or e}"
        except anthropic.APIStatusError as e:
            return None, f"Claude said error {e.status_code}: {e.message}"

    @app.post("/voice")
    def voice_chat():
        """Recording in -> Whisper -> Claude -> Piper -> words and audio out."""
        recording = request.get_data()
        if not recording:
            return jsonify(error="Send a WAV recording as the request body."), 400
        try:
            heard = ears(recording)
        except voice.VoiceError as e:
            return jsonify(error=str(e)), 502
        if not heard:
            return jsonify(transcript="", reply="", error="I didn't catch that. Try again?"), 200

        reply, error = think(heard)
        if error:
            return jsonify(transcript=heard, error=error), 502
        try:
            audio = mouth(reply)
        except voice.VoiceError as e:
            # Still return the words, even if Bolt can't say them out loud.
            return jsonify(transcript=heard, reply=reply, error=str(e)), 200
        # Audio is binary, but JSON is text, so we encode it with base64.
        return jsonify(transcript=heard, reply=reply, audio=base64.b64encode(audio).decode())

    @app.post("/speak")
    def speak():
        """Just the mouth: text in, Bolt's voice out. The Pi will use this for reminders."""
        text = str((request.get_json(silent=True) or {}).get("text", "")).strip()
        if not text:
            return jsonify(error="Send some text, like {\"text\": \"hi\"}"), 400
        try:
            return app.response_class(mouth(text), mimetype="audio/wav")
        except voice.VoiceError as e:
            return jsonify(error=str(e)), 502

    @app.post("/reset")
    def reset():
        with brain_lock:
            brain.reset()
        return jsonify(status="fresh conversation started")

    @app.get("/notifications")
    def get_notifications():
        last_seen = request.args.get("after", default=0, type=int)
        return jsonify(notifications=notifications.after(last_seen))

    return app


def alarm_clock(reminders, notifications, stop, home=None):
    """The same alarm clock as before, but it tells everyone who's listening:
    the web page (via the notification list) and your phone (via Home Assistant)."""
    while not stop.is_set():
        for r in reminders.pop_due():
            text = f"Hey! Reminder: {r['message']}"
            print(f"🔔 {text}")
            notifications.add(text)
            if home and home.enabled:
                worked, explanation = home.notify(text)
                if not worked:
                    print(f"   ! Phone notification failed: {explanation}")
        stop.wait(15)


def main():
    from waitress import serve  # a sturdy server for running 24/7

    reminders = ReminderStore(os.environ.get("REMINDERS_PATH", "reminders.json"))
    notifications = Notifications()
    home = HomeAssistant()
    app = create_app(Brain(reminders, home=home), notifications)

    stop = threading.Event()
    print("Smart home control:", f"ON (blocked: {', '.join(sorted(home.blocked)) or 'nothing'})" if home.can_control else "off")
    print("Phone notifications via Home Assistant:", "ON" if home.enabled else "off (not set up in .env)")
    threading.Thread(target=alarm_clock, args=(reminders, notifications, stop, home), daemon=True).start()

    print(f"{ROBOT_NAME}'s brain is listening on port {PORT}. Open http://localhost:{PORT}")
    # host="0.0.0.0" means "accept requests from other devices on the network",
    # not just from this computer.
    serve(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
