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
  POST /reset             start a fresh conversation
  GET  /health            "are you alive?" (used to check the server is up)

Requests and responses are written in JSON, a simple text format for data.
"""

import os
import threading
from datetime import datetime
from pathlib import Path

import anthropic
from flask import Flask, jsonify, request, send_file

from robot_friend.brain import Brain
from robot_friend.personality import ROBOT_NAME
from robot_friend.reminders import ReminderStore

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


def create_app(brain, notifications):
    app = Flask(__name__)
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
        try:
            with brain_lock:
                reply = brain.chat(text)
        except anthropic.AuthenticationError:
            return jsonify(error="The API key isn't working. Check .env"), 502
        except anthropic.APIConnectionError as e:
            return jsonify(error=f"Can't reach Claude: {e.__cause__ or e}"), 502
        except anthropic.APIStatusError as e:
            return jsonify(error=f"Claude said error {e.status_code}: {e.message}"), 502
        return jsonify(reply=reply)

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


def alarm_clock(reminders, notifications, stop):
    """The same alarm clock as before, but it posts to the notification list."""
    while not stop.is_set():
        for r in reminders.pop_due():
            print(f"🔔 Reminder: {r['message']}")
            notifications.add(f"Hey! Reminder: {r['message']}")
        stop.wait(15)


def main():
    from waitress import serve  # a sturdy server for running 24/7

    reminders = ReminderStore(os.environ.get("REMINDERS_PATH", "reminders.json"))
    notifications = Notifications()
    app = create_app(Brain(reminders), notifications)

    stop = threading.Event()
    threading.Thread(target=alarm_clock, args=(reminders, notifications, stop), daemon=True).start()

    print(f"{ROBOT_NAME}'s brain is listening on port {PORT}. Open http://localhost:{PORT}")
    # host="0.0.0.0" means "accept requests from other devices on the network",
    # not just from this computer.
    serve(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
