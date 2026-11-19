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
  GET  /studio            the Studio: tabs for Bolt's eyes and personality
  GET  /personality       Bolt's character (name, who it is, how it talks)
  PUT  /personality       save a new character;  POST /personality/undo, /personality/reset
  POST /personality/try   a test chat with a character that isn't saved yet
  GET  /static/<file>     shared files, like face.js and expressions.json
  PUT  /expressions       save a new eye design (from the Eye Studio)
  POST /expressions/undo  go back to the design before the last save
  POST /expressions/reset go back to the original design
  POST /chat              send {"text": "hi"}, get back {"reply": "..."}
  GET  /notifications     reminders that have gone off
  POST /voice             send a WAV recording, get back what you said,
                          Bolt's reply, and the reply as spoken audio
  POST /speak             send {"text": "..."}, get back Bolt's voice (WAV)
  GET  /memories          everything Bolt has chosen to remember
  DELETE /memories/<id>   make Bolt forget one memory
  POST /reset             start a fresh conversation
  GET  /health            "are you alive?" (used to check the server is up)
  GET  /login             the login page;  POST /login to log in;  POST /logout
  GET  /bolt-ca.crt       the HTTPS "stamp" devices install to trust Bolt (see Caddyfile)

Every route except /health, /login and the eye drawing files needs you to be
logged in (a browser) or to send the API key (the Pi). See security.py.

Requests and responses are written in JSON, a simple text format for data.
"""

import base64
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import anthropic
from flask import Flask, jsonify, redirect, request, send_file, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix

from robot_friend.brain import Brain
from robot_friend.expressions import DesignError, DesignStore
from robot_friend.home_assistant import HomeAssistant
from robot_friend.memory import MemoryStore
from robot_friend.personality import (DEFAULT_CHARACTER, LIMITS, PRESETS, ROBOT_NAME, RULES,
                                     CharacterError, CharacterStore)
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from robot_friend import voice

PORT = int(os.environ.get("PORT", "8770"))
WEB_DIR = Path(__file__).parent / "web"
WEB_PAGE = WEB_DIR / "index.html"


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


# Anyone can use these without logging in. Nothing private is in them.
PUBLIC = {"/health", "/login", "/login/status", "/static/face.js", "/static/expressions.json", "/static/auth.js",
          "/bolt-ca.crt"}


def create_app(brain, notifications, ears=None, mouth=None, designs=None, security=None, characters=None):
    # ears/mouth default to the real Whisper and Piper. Tests swap in pretend ones.
    ears = ears or voice.transcribe
    mouth = mouth or voice.synthesize

    app = Flask(__name__, static_folder=None)  # we serve web/ ourselves at /static/
    app.json.sort_keys = False  # keep things in the order they were written (e.g. expressions)
    if os.environ.get("BOLT_HTTPS") == "1":
        # Behind Caddy, every request arrives FROM Caddy. Caddy adds the real visitor's
        # address in a header; trust it (only here, where nobody can reach Bolt except via Caddy),
        # so "5 wrong passwords" slows down that one device, not everyone.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # refuse recordings over 10 MB
    # Only one conversation at a time, so two requests can't mix up the memory.
    brain_lock = threading.Lock()

    # ------------------------------------------------------------ THE LOCK
    security = security or Security()
    app.secret_key = security.session_secret()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,      # page scripts can't read the cookie
        SESSION_COOKIE_SAMESITE="Strict",  # other websites can't make your browser use it
        SESSION_COOKIE_SECURE=os.environ.get("BOLT_HTTPS") == "1",  # only ever sent over HTTPS
        PERMANENT_SESSION_LIFETIME=timedelta(days=365),
    )

    def logged_in():
        if security.open_for_testing:
            return True
        key = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if key and security.check_api_key(key):
            return True  # the Pi
        return bool(session.get("ok")) and session.get("pw") == security.fingerprint() != ""

    @app.before_request
    def check_the_lock():
        """Runs before EVERY request. Lets it through, or stops it."""
        if request.path in PUBLIC:
            return None
        if not logged_in():
            if request.method == "GET" and "text/html" in request.headers.get("Accept", ""):
                return redirect("/login?next=" + request.path)  # a person opening a page
            return jsonify(error="Please log in."), 401         # a script or the Pi
        # Changes must come from Bolt's own pages, not from another website.
        origin = request.headers.get("Origin")
        if request.method != "GET" and origin and urlparse(origin).netloc != request.host:
            return jsonify(error="That request came from another website."), 403
        return None

    @app.get("/bolt-ca.crt")
    def bolt_ca():
        """The certificate authority's PUBLIC stamp. Safe to share: it can check
        Bolt's certificate but can't create one. (The secret half never leaves Caddy.)"""
        path = Path(os.environ.get("CA_CERT_PATH", "/caddy/caddy/pki/authorities/local/root.crt"))
        if not path.exists():
            return jsonify(error="HTTPS isn't set up yet (no certificate authority found)."), 404
        return app.response_class(path.read_bytes(), mimetype="application/x-x509-ca-cert",
                                  headers={"Content-Disposition": "attachment; filename=bolt-ca.crt"})

    @app.get("/login")
    def login_page():
        return send_file(WEB_DIR / "login.html")

    @app.get("/login/status")
    def login_status():
        return jsonify(has_password=security.has_password(), logged_in=logged_in())

    @app.post("/login")
    def login():
        device = request.remote_addr or "?"
        wait = security.wait_needed(device)
        if wait:
            return jsonify(error=f"Too many wrong passwords. Try again in {wait} seconds."), 429
        password = str((request.get_json(silent=True) or {}).get("password", ""))
        if not security.check_password(password):
            security.record_fail(device)
            return jsonify(error="That password isn't right."), 401
        security.record_success(device)
        session.clear()
        session.permanent = True
        session["ok"] = True
        session["pw"] = security.fingerprint()
        return jsonify(status="logged in")

    @app.post("/logout")
    def logout():
        session.clear()
        return jsonify(status="logged out")

    @app.get("/")
    def page():
        return send_file(WEB_PAGE)

    @app.get("/studio")
    def studio():
        return send_file(WEB_DIR / "studio.html")

    @app.get("/eyes")
    def eye_studio():
        return redirect("/studio#face")  # the Eye Studio became the Studio's Face tab

    # ------------------------------------------------------- PERSONALITY
    characters = characters or brain.character or CharacterStore(os.environ.get("PERSONALITY_PATH", "personality.json"))
    brain.character = characters

    @app.get("/personality")
    def get_personality():
        return jsonify(current=characters.current(), original=DEFAULT_CHARACTER, custom=characters.is_custom(),
                       presets=PRESETS, rules=RULES, limits=LIMITS)

    @app.put("/personality")
    def save_personality():
        try:
            characters.save(request.get_json(silent=True))
        except CharacterError as e:
            return jsonify(error=str(e)), 400
        with brain_lock:
            brain.reset()  # start a fresh conversation so the new personality applies now
        return jsonify(status="saved", current=characters.current())

    @app.post("/personality/undo")
    def undo_personality():
        try:
            characters.undo()
        except CharacterError as e:
            return jsonify(error=str(e)), 409
        with brain_lock:
            brain.reset()
        return jsonify(status="undone", current=characters.current())

    @app.post("/personality/reset")
    def reset_personality():
        characters.reset()
        with brain_lock:
            brain.reset()
        return jsonify(status="original", current=characters.current())

    @app.post("/personality/try")
    def try_personality():
        data = request.get_json(silent=True) or {}
        history = data.get("history")
        if (not isinstance(history, list) or not history or len(history) > 12
                or any(not isinstance(m, dict) or m.get("role") not in ("user", "assistant")
                       or not isinstance(m.get("content"), str) or not 0 < len(m["content"]) <= 1000
                       for m in history)
                or history[-1]["role"] != "user"):
            return jsonify(error="Send a short test chat that ends with something you said."), 400
        try:
            reply = brain.try_character(data.get("character"), [{"role": m["role"], "content": m["content"]} for m in history])
        except CharacterError as e:
            return jsonify(error=str(e)), 400
        except anthropic.APIStatusError as e:
            return jsonify(error=f"Claude said error {e.status_code}: {e.message}"), 502
        except anthropic.APIConnectionError:
            return jsonify(error="Can't reach Claude right now."), 502
        return jsonify(reply=reply)

    designs = designs or DesignStore(os.environ.get("EXPRESSIONS_PATH", "expressions.json"))

    # The eye design comes from the saved copy if there is one (see expressions.py).
    @app.get("/static/expressions.json")
    def eye_design():
        response = jsonify(designs.current())
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Bolt-Design"] = "custom" if designs.is_custom() else "original"
        return response

    @app.put("/expressions")
    def save_design():
        try:
            designs.save(request.get_json(silent=True))
        except DesignError as e:
            return jsonify(error=str(e)), 400
        return jsonify(status="saved")

    @app.post("/expressions/undo")
    def undo_design():
        try:
            designs.undo()
        except DesignError as e:
            return jsonify(error=str(e)), 409
        return jsonify(status="undone", design=designs.current())

    @app.post("/expressions/reset")
    def reset_design():
        designs.reset()
        return jsonify(status="original", design=designs.current())

    @app.get("/static/<path:name>")
    def static_file(name):
        # send_from_directory refuses paths that try to escape the web folder (../)
        return send_from_directory(WEB_DIR, name, max_age=0)

    @app.get("/health")
    def health():
        return jsonify(status="ok", robot=characters.name())

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
        """
        Recording in -> Whisper -> Claude -> Piper -> words and audio out.

        LESSON: Measure before you speed things up
        A STOPWATCH times each step, so we know which one is slow. The times go
        back with the reply (as "timings") and into Bolt's log:
            docker logs bolt | grep "voice:"
        """
        recording = request.get_data()
        if not recording:
            return jsonify(error="Send a WAV recording as the request body."), 400
        timings = {}
        clock = time.perf_counter()

        def lap(name):
            nonlocal clock
            now = time.perf_counter()
            timings[name] = round(now - clock, 2)
            clock = now

        try:
            heard = ears(recording)
        except voice.VoiceError as e:
            return jsonify(error=str(e)), 502
        lap("listening")   # Whisper: voice -> text
        if not heard:
            return jsonify(transcript="", reply="", error="I didn't catch that. Try again?", timings=timings), 200

        reply, error = think(heard)
        lap("thinking")    # Claude: text -> reply
        if error:
            return jsonify(transcript=heard, error=error, timings=timings), 502
        try:
            audio = mouth(reply)
        except voice.VoiceError as e:
            # Still return the words, even if Bolt can't say them out loud.
            return jsonify(transcript=heard, reply=reply, error=str(e), timings=timings), 200
        lap("speaking")    # Piper: reply -> voice
        print("voice: " + " · ".join(f"{k} {v:.1f}s" for k, v in timings.items()), flush=True)
        # Audio is binary, but JSON is text, so we encode it with base64.
        return jsonify(transcript=heard, reply=reply, audio=base64.b64encode(audio).decode(), timings=timings)

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

    @app.get("/memories")
    def list_memories():
        return jsonify(memories=brain.memories.list() if brain.memories else [])

    @app.delete("/memories/<memory_id>")
    def delete_memory(memory_id):
        if brain.memories and brain.memories.forget(memory_id):
            return jsonify(status="forgotten")
        return jsonify(error="No memory with that id."), 404

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


def alarm_clock(reminders, notifications, stop, home=None, name_of=lambda: ROBOT_NAME):
    """The same alarm clock as before, but it tells everyone who's listening:
    the web page (via the notification list) and your phone (via Home Assistant)."""
    while not stop.is_set():
        for r in reminders.pop_due():
            text = f"Hey! Reminder: {r['message']}"
            print(f"🔔 {text}")
            notifications.add(text)
            if home and home.enabled:
                worked, explanation = home.notify(text, title=name_of())
                if not worked:
                    print(f"   ! Phone notification failed: {explanation}")
        stop.wait(15)


def main():
    from waitress import serve  # a sturdy server for running 24/7

    reminders = ReminderStore(os.environ.get("REMINDERS_PATH", "reminders.json"))
    notifications = Notifications()
    home = HomeAssistant()
    memories = MemoryStore(os.environ.get("MEMORIES_PATH", "memories.json"))
    print(f"Long-term memories: {len(memories.list())}")
    characters = CharacterStore(os.environ.get("PERSONALITY_PATH", "personality.json"))
    app = create_app(Brain(reminders, home=home, memories=memories, character=characters), notifications)

    stop = threading.Event()
    print("Smart home control:", f"ON (blocked: {', '.join(sorted(home.blocked)) or 'nothing'})" if home.can_control else "off")
    print("Phone notifications via Home Assistant:", "ON" if home.enabled else "off (not set up in .env)")
    threading.Thread(target=alarm_clock, args=(reminders, notifications, stop, home, characters.name), daemon=True).start()

    print(f"{ROBOT_NAME}'s brain is listening on port {PORT}. Open http://localhost:{PORT}")
    # host="0.0.0.0" means "accept requests from other devices on the network",
    # not just from this computer.
    serve(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
