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
  GET  /body-settings     the body's settings (volume, sleep time...); PUT to save, POST /body-settings/reset
  GET  /static/<file>     shared files, like face.js and expressions.json
  PUT  /expressions       save a new eye design (from the Eye Studio)
  POST /expressions/undo  go back to the design before the last save
  POST /expressions/reset go back to the original design
  POST /chat              send {"text": "hi"}, get back {"reply": "..."}
  GET  /notifications     reminders that have gone off, and announcements
  GET  /camera/wanted     the Pi: is a photo wanted? (twice a second)
  POST /camera/photo/<id> the Pi: here's the photo that was asked for
  GET  /camera/view       the 📷 page: what she sees now, with boxes round what she recognises
  POST /announce          Home Assistant: {"message": "..."} for Bolt to say out loud ("rephrase": true = in its own words;
                          "camera": "camera.x" = show that camera's snapshot too)
  GET  /pictures/<token>  a picture that came with an announcement
  POST /voice             send a WAV recording, get back what you said,
                          Bolt's reply, and the reply as spoken audio
  POST /voice/stream      the same, but Bolt's reply comes back ONE SENTENCE AT A TIME,
                          each with its audio, so it can start talking sooner
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
import io
import json
import os
import secrets
import wave
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
from robot_friend.camera import PhotoDesk
from robot_friend.memory import MemoryStore
from robot_friend.body_settings import BodySettingsStore, SettingsError, describe as describe_body_settings
from robot_friend.personality import (DEFAULT_CHARACTER, LIMITS, PRESETS, ROBOT_NAME, RULES,
                                     CharacterError, CharacterStore)
from robot_friend.reminders import ReminderStore
from robot_friend.timers import TimerStore
from robot_friend.presence import PresenceBook
from robot_friend.sentences import sentences
from robot_friend.stage import split_cues, without_cues
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
        # LESSON: the numbers start again at 1 whenever the brain restarts, so a listener who
        # remembers "I've seen up to 60" would wait for number 61 and miss 1-60. The BOOT
        # code changes on every restart: when it changes, listeners start counting again.
        self.boot = secrets.token_hex(4)
        self._lock = threading.Lock()
        self._items = []
        self._next_id = 1
        self._keep = keep

    def add(self, text, picture=None, show=None):
        with self._lock:
            item = {"id": self._next_id, "text": text, "time": datetime.now().isoformat(timespec="seconds")}
            if picture:
                item["picture"] = picture      # where to fetch the picture that goes with it
            if show:
                item["show"] = show            # a prop for her screen while she says it: [emoji, text]
            self._items.append(item)
            self._next_id += 1
            self._items = self._items[-self._keep:]  # only keep the newest ones

    def after(self, last_seen):
        with self._lock:
            return [n for n in self._items if n["id"] > last_seen]


# Anyone can use these without logging in. Nothing private is in them.
PUBLIC = {"/health", "/login", "/login/status", "/static/face.js", "/static/expressions.json", "/static/auth.js",
          "/static/name.js", "/bolt-ca.crt"}


def create_app(brain, notifications, ears=None, mouth=None, designs=None, security=None, characters=None,
               body_settings=None, camera=None):
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
    # Camera pictures that came with announcements: only the newest few, only in memory.
    pictures, pictures_lock = {}, threading.Lock()

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
        if request.path in PUBLIC or request.path.startswith("/static/stickers/"):
            return None   # (stickers are just pictures for the face, which the login page shows too)
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

    # ------------------------------------------------------- BODY SETTINGS
    # Volume, sleep time and so on, for Riley's body on the Pi (see robot_friend/body_settings.py).
    body_settings = body_settings or BodySettingsStore(os.environ.get("BODY_SETTINGS_PATH", "body_settings.json"))

    @app.get("/body-settings")
    def get_body_settings():
        return jsonify(current=body_settings.current(), custom=body_settings.is_custom(), form=describe_body_settings())

    @app.put("/body-settings")
    def save_body_settings():
        try:
            return jsonify(status="saved", current=body_settings.save(request.get_json(silent=True)))
        except SettingsError as e:
            return jsonify(error=str(e)), 400

    @app.post("/body-settings/reset")
    def reset_body_settings():
        body_settings.reset()
        return jsonify(status="original", current=body_settings.current())

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
        words, cues = split_cues(reply)
        return jsonify(reply=words, cues=[list(c) for c in cues])

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
        try:  # how long the recording itself is: longer recordings take Whisper longer
            with wave.open(io.BytesIO(recording), "rb") as w:
                timings["recording"] = round(w.getnframes() / w.getframerate(), 1)
        except (wave.Error, EOFError, ZeroDivisionError):
            pass
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
        reply = without_cues(reply)
        try:
            audio = mouth(reply)
        except voice.VoiceError as e:
            # Still return the words, even if Bolt can't say them out loud.
            return jsonify(transcript=heard, reply=reply, error=str(e), timings=timings), 200
        lap("speaking")    # Piper: reply -> voice
        print("voice: " + " · ".join(f"{k} {v:.1f}s" for k, v in timings.items()) + f' · heard "{heard}"', flush=True)
        # Audio is binary, but JSON is text, so we encode it with base64.
        return jsonify(transcript=heard, reply=reply, audio=base64.b64encode(audio).decode(), timings=timings)

    @app.post("/voice/stream")
    def voice_stream():
        """
        LESSON: Talking while thinking
        ==============================
        /voice waits for Claude's whole reply, then turns ALL of it into speech,
        then sends it back. Here, each SENTENCE is turned into speech as soon as
        Claude finishes writing it, and sent straight away. Bolt starts talking
        while Claude is still writing the rest.

        The answer is a stream of JSON lines ("NDJSON"), one per event:
          {"type": "heard", "text": ...}               what Whisper heard
          {"type": "say", "text": ..., "audio": ...}   one sentence and its sound
          {"type": "mood", "name": ...}                her face, for what comes next (see stage.py)
          {"type": "show", "emoji": ..., "text": ...}  a prop to hold up on her screen
          {"type": "done", "reply": ..., "timings": ...}
        """
        recording = request.get_data()
        if not recording:
            return jsonify(error="Send a WAV recording as the request body."), 400
        timings = {}
        try:
            with wave.open(io.BytesIO(recording), "rb") as w:
                timings["recording"] = round(w.getnframes() / w.getframerate(), 1)
        except (wave.Error, EOFError, ZeroDivisionError):
            pass
        started = time.perf_counter()
        try:
            heard = ears(recording)
        except voice.VoiceError as e:
            return jsonify(error=str(e)), 502
        timings["listening"] = round(time.perf_counter() - started, 2)
        if not heard:
            return jsonify(transcript="", reply="", error="I didn't catch that. Try again?", timings=timings), 200

        def line(**event):
            return json.dumps(event) + "\n"

        def events():
            yield line(type="heard", text=heard, timings=dict(timings))
            thinking_started = time.perf_counter()
            said, voice_problem = [], None
            try:
                with brain_lock:   # one conversation at a time, for the whole reply
                    for sentence in sentences(brain.chat_stream(heard)):
                        # Stage directions ([happy], [show:☀️ 12°]) go to the face, not the voice
                        sentence, cues = split_cues(sentence)
                        for cue in cues:
                            yield (line(type="mood", name=cue[1]) if cue[0] == "mood"
                                   else line(type="show", emoji=cue[1], text=cue[2]))
                        if not sentence:
                            continue
                        said.append(sentence)
                        audio = None
                        if voice_problem is None:
                            try:
                                audio = base64.b64encode(mouth(sentence)).decode()
                            except voice.VoiceError as e:
                                voice_problem = str(e)  # keep sending the words, just without sound
                        if "first_words" not in timings:
                            timings["first_words"] = round(time.perf_counter() - thinking_started, 2)
                        yield line(type="say", text=sentence, audio=audio)
            except anthropic.AuthenticationError:
                yield line(type="error", error="The API key isn't working. Check .env")
            except anthropic.APIConnectionError as e:
                yield line(type="error", error=f"Can't reach Claude: {e.__cause__ or e}")
            except anthropic.APIStatusError as e:
                yield line(type="error", error=f"Claude said error {e.status_code}: {e.message}")
            timings["whole_reply"] = round(time.perf_counter() - thinking_started, 2)
            if voice_problem:
                yield line(type="error", error=voice_problem)
            print("voice: " + " · ".join(f"{k} {v:.1f}s" for k, v in timings.items()) + f' · heard "{heard}"', flush=True)
            yield line(type="done", reply=" ".join(said), timings=timings)

        # "no-cache"/"X-Accel-Buffering: no" ask anything in between not to hold the lines back.
        return app.response_class(events(), mimetype="application/x-ndjson",
                                  headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------ THE CAMERA (see robot_friend/camera.py)
    @app.get("/camera/wanted")
    def camera_wanted():
        """The Pi checks here twice a second: is a photo wanted?"""
        if camera is None:
            return jsonify(id=None)
        rid = camera.wanted()
        return jsonify(id=rid, kind=camera.kind(rid)) if rid else jsonify(id=None)

    @app.post("/camera/photo/<rid>")
    def camera_photo(rid):
        """The Pi hands in the photo that was asked for: a JPEG as the body, or for a view,
        {"image": base64 JPEG, "boxes": [...]}."""
        if camera is None:
            return jsonify(error="No camera desk."), 404
        if request.is_json:
            problem = camera.deliver_view(rid, request.get_json(silent=True))
        else:
            problem = camera.deliver(rid, request.get_data())
        return (jsonify(error=problem), 400) if problem else jsonify(status="thanks")

    @app.get("/camera/view")
    def camera_view():
        """LESSON: seeing what she sees. The chat page's 📷 panel asks here about once a second.
        Logged in only (like everything else), never saved, never given to Claude."""
        if camera is None:
            return jsonify(error="No camera desk."), 404
        got, problem = camera.view()
        if problem:
            return jsonify(error=problem), 503
        return jsonify(image="data:image/jpeg;base64," + base64.b64encode(got["photo"]).decode(),
                       boxes=got["boxes"], paused=got["paused"]), 200, {"Cache-Control": "no-store"}

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

    @app.post("/announce")
    def announce():
        """LESSON: Home Assistant talking THROUGH Bolt. An automation sends
        {"message": "The washing machine has finished"} (with the same key the Pi uses),
        and it joins the list of things Bolt's body says out loud (the Pi checks every few
        seconds). With "rephrase": true, Bolt says it in its own words and personality."""
        data = request.get_json(silent=True) or {}
        message = str(data.get("message", "")).strip()
        if not 0 < len(message) <= 500:
            return jsonify(error='Send {"message": "something to say"} (up to 500 characters).'), 400
        if data.get("rephrase") is True:
            try:
                message = brain.in_my_words(message)
            except Exception:
                pass  # Claude unreachable: say the message as it was sent, rather than nothing
        # LESSON: a picture with the message. {"camera": "camera.front_door"} (or "image": the
        # address HA's phone notification uses) and Riley fetches the snapshot from HA herself,
        # shows it on her screen and in the chat. Only the newest few are kept, in memory.
        picture, problem = None, None
        camera, image = str(data.get("camera") or ""), str(data.get("image") or "")
        if camera or image:
            if not (brain.home and brain.home.can_control):
                problem = "Home Assistant isn't set up, so Riley can't fetch the picture."
            else:
                try:
                    jpeg = brain.home.camera_snapshot(camera=camera, image=image)
                    token = secrets.token_urlsafe(12)
                    with pictures_lock:
                        pictures[token] = jpeg
                        while len(pictures) > 5:
                            pictures.pop(next(iter(pictures)))      # forget the oldest
                    picture = f"/pictures/{token}"
                except Exception as e:      # still say the message, just without the picture
                    problem = str(e)
                    print(f"   ! announce picture: {problem}", flush=True)
        notifications.add(message, picture=picture)
        print(f"announce: {message}" + (" (with a picture)" if picture else ""), flush=True)
        return jsonify(status="announced", said=message, picture=bool(picture), **({"picture_problem": problem} if problem else {}))

    @app.post("/presence")
    def presence():
        """The Pi: "the camera recognised this person at the desk". Only a name, never a face."""
        name = str((request.get_json(silent=True) or {}).get("name", "")).strip()[:40]
        book = getattr(brain, "presence", None)
        if not name or book is None:
            return jsonify(error="Send {\"name\": ...}."), 400
        book.seen_at_desk(name)
        settings = body_settings.current()
        if settings.get("morning_brief", "on") == "on" and book.should_brief(name):
            book.should_greet(name)                          # the brief is her hello too
            def brief():
                try:
                    words, prop = brain.morning_brief_for(name)
                except Exception as e:                       # Claude unreachable: at least say hello
                    print(f"   ! morning brief: {e}", flush=True)
                    words, prop = f"Good morning, {name}!", None
                notifications.add(words, show=prop)
            threading.Thread(target=brief, daemon=True).start()
            return jsonify(status="briefing")
        if settings.get("greetings") in ("both", "desk") and book.should_greet(name):
            threading.Thread(target=lambda: notifications.add(brain.greet(name, "desk")), daemon=True).start()
            return jsonify(status="greeting")
        return jsonify(status="noted")

    @app.get("/pictures/<token>")
    def picture(token):
        """A picture that came with an announcement (logged in only, like everything else)."""
        with pictures_lock:
            data = pictures.get(token)
        if data is None:
            return jsonify(error="That picture has gone (only the newest few are kept)."), 404
        return app.response_class(data, mimetype="image/png" if data.startswith(b"\x89PNG") else "image/jpeg",
                                  headers={"Cache-Control": "no-store"})

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
        # The timers running now ride along too, so the Pi can show how long each has left.
        running = brain.timers.list() if getattr(brain, "timers", None) else []
        return jsonify(notifications=notifications.after(last_seen), boot=notifications.boot, timers=running)

    return app


def alarm_clock(reminders, notifications, stop, home=None, name_of=lambda: ROBOT_NAME):
    """The same alarm clock as before, but it tells everyone who's listening:
    the web page (via the notification list) and your phone (via Home Assistant)."""
    while not stop.is_set():
        try:
            for r in reminders.pop_due():
                text = f"Hey! Reminder: {r['message']}"
                print(f"🔔 {text}")
                notifications.add(text)
                if home and home.enabled:
                    worked, explanation = home.notify(text, title=name_of())
                    if not worked:
                        print(f"   ! Phone notification failed: {explanation}")
        except Exception as e:  # one bad reminder must never stop all the others
            print(f"   ! alarm clock: {e}", flush=True)
        stop.wait(15)


def presence_watch(brain, notifications, stop, settings, every=30):
    """Asks Home Assistant who's home every 30 seconds, and welcomes anyone who's just arrived."""
    while not stop.is_set():
        try:
            if brain.home and brain.home.can_control and brain.presence:
                for name in brain.presence.update_home(brain.home.people()):
                    print(f"🏠 {name} got home", flush=True)
                    if settings.current().get("greetings") in ("both", "home") and brain.presence.should_greet(name):
                        notifications.add(brain.greet(name, "home"))
        except Exception as e:  # HA unreachable for a moment: try again next time
            print(f"   ! presence: {e}", flush=True)
        stop.wait(every)


def timer_clock(timers, notifications, stop, home=None, name_of=lambda: ROBOT_NAME):
    """Checks the timers every second (reminders only need checking every 15)."""
    from robot_friend.timers import spoken_length
    while not stop.is_set():
        try:
            for t in timers.pop_done():
                what = f"{t['label']} " if t["label"] else ""
                text = f"Your {spoken_length(t['seconds'])} {what}timer is done!"
                print(f"⏲️ {text}", flush=True)
                notifications.add(text)
                if home and home.enabled:
                    home.notify(text, title=name_of())
        except Exception as e:  # one bad timer must never stop the others
            print(f"   ! timer clock: {e}", flush=True)
        stop.wait(1)


def main():
    from waitress import serve  # a sturdy server for running 24/7

    reminders = ReminderStore(os.environ.get("REMINDERS_PATH", "reminders.json"))
    notifications = Notifications()
    home = HomeAssistant()
    memories = MemoryStore(os.environ.get("MEMORIES_PATH", "memories.json"))
    print(f"Long-term memories: {len(memories.list())}")
    characters = CharacterStore(os.environ.get("PERSONALITY_PATH", "personality.json"))
    camera = PhotoDesk()
    timers = TimerStore(os.environ.get("TIMERS_PATH", "timers.json"))
    presence = PresenceBook(path=os.environ.get("GREETED_PATH", "greeted.json"))
    body_settings = BodySettingsStore(os.environ.get("BODY_SETTINGS_PATH", "body_settings.json"))
    brain = Brain(reminders, home=home, memories=memories, character=characters, camera=camera, timers=timers,
                  presence=presence)
    app = create_app(brain, notifications, camera=camera, body_settings=body_settings)

    stop = threading.Event()
    print("Smart home control:", f"ON (blocked: {', '.join(sorted(home.blocked)) or 'nothing'})" if home.can_control else "off")
    print("Phone notifications via Home Assistant:", "ON" if home.enabled else "off (not set up in .env)")
    threading.Thread(target=alarm_clock, args=(reminders, notifications, stop, home, characters.name), daemon=True).start()
    threading.Thread(target=timer_clock, args=(timers, notifications, stop, home, characters.name), daemon=True).start()
    threading.Thread(target=presence_watch, args=(brain, notifications, stop, body_settings), daemon=True).start()

    print(f"{ROBOT_NAME}'s brain is listening on port {PORT}. Open http://localhost:{PORT}")
    # host="0.0.0.0" means "accept requests from other devices on the network",
    # not just from this computer.
    serve(app, host="0.0.0.0", port=PORT, threads=8)   # 8 at once: the Pi now checks in twice a second


if __name__ == "__main__":
    main()
