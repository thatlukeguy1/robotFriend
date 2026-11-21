"""
Tests for Bolt's body, using pretend parts: no Pi, microphone or network needed.
Run from the pi/ folder:  python -m pytest
"""

import io
import struct
import wave

from bolt_body.audio import FRAME, beep, loudness, record_until_quiet
from bolt_body.main import Body

QUIET = b"\0\0" * FRAME
LOUD = struct.pack(f"<{FRAME}h", *([3000, -3000] * (FRAME // 2)))


class PretendMic:
    def __init__(self, frames):
        self.frames, self.flushed = list(frames), 0
    def read(self):
        if not self.frames:
            raise EOFError
        return self.frames.pop(0)
    def flush(self):
        self.flushed += 1


class PretendSpeaker:
    def __init__(self):
        self.played = []
    def play(self, wav):
        self.played.append(wav)


class PretendWake:
    """Hears the wake word on the frames we choose."""
    def __init__(self, on_frames=()):
        self.on, self.n, self.last_score, self.resets = set(on_frames), 0, 0.0, 0
    def heard(self, frame):
        self.n += 1
        return self.n in self.on
    def reset(self):
        self.resets += 1


class PretendBrain:
    def __init__(self):
        self.sent, self.spoken = [], []
    def voice_stream(self, wav):
        self.sent.append(wav)
        yield ("heard", "hello")
        yield ("say", "Hi there!", b"REPLY-AUDIO")
        yield ("done", {"listening": 0.1})
    def speak(self, text):
        self.spoken.append(text)
        return b"REMINDER-AUDIO"
    def notifications(self, after):
        return []


def seconds(n):
    return int(n * 16000 / FRAME)


# ----------------------------------------------------------- audio helpers

def test_loudness():
    assert loudness(QUIET) == 0 and loudness(LOUD) == 3000


def test_beep_is_a_wav():
    with wave.open(io.BytesIO(beep()), "rb") as w:
        assert w.getframerate() == 16000 and w.getnframes() > 0


def test_records_until_you_stop_talking():
    mic = PretendMic([QUIET] * 5 + [LOUD] * seconds(2) + [QUIET] * seconds(3))
    wav = record_until_quiet(mic)
    with wave.open(io.BytesIO(wav), "rb") as w:
        assert 2.5 < w.getnframes() / 16000 < 3.5   # the talking + about 1 s of quiet
    assert len(mic.frames) > 0                       # it stopped before the end


def test_gives_up_if_you_say_nothing():
    assert record_until_quiet(PretendMic([QUIET] * seconds(10))) is None


# --------------------------------------------------------------- the body

def test_wake_word_starts_a_conversation():
    mic = PretendMic([QUIET] * 3 + [LOUD] * seconds(1) + [QUIET] * seconds(2))
    brain, speaker, wake = PretendBrain(), PretendSpeaker(), PretendWake(on_frames=[2])
    try:
        Body(brain, mic, speaker, wake).run()
    except EOFError:
        pass
    assert len(brain.sent) == 1                     # it sent the recording to the brain
    assert speaker.played[-1] == b"REPLY-AUDIO"      # and said the reply
    assert mic.flushed == 1 and wake.resets >= 1     # then ignored its own voice


def test_reminders_are_announced():
    brain, speaker = PretendBrain(), PretendSpeaker()
    body = Body(brain, PretendMic([QUIET] * 3), speaker, PretendWake())
    body.announcements.append("Hey! Reminder: stretch")
    try:
        body.run()
    except EOFError:
        pass
    assert brain.spoken == ["Hey! Reminder: stretch"]
    assert speaker.played[-1] == b"REMINDER-AUDIO"


def test_button_starts_a_conversation():
    brain = PretendBrain()
    body = Body(brain, PretendMic([QUIET] * 2 + [LOUD] * seconds(1) + [QUIET] * seconds(2)), PretendSpeaker(), PretendWake())
    body.button_pressed.set()
    try:
        body.run()
    except EOFError:
        pass
    assert len(brain.sent) == 1


def test_brain_trouble_plays_a_low_beep():
    class BrokenBrain(PretendBrain):
        def voice_stream(self, wav):
            yield ("error", "Can't reach Bolt's brain")
    speaker = PretendSpeaker()
    body = Body(BrokenBrain(), PretendMic([LOUD] * seconds(1) + [QUIET] * seconds(2)), speaker, PretendWake())
    body.converse()
    assert speaker.played[-1] == beep(220, 300)


def test_brain_link_sends_the_key():
    import json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from bolt_body.brain_link import BrainLink
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Authorization"))
            ok = self.headers.get("Authorization") == "Bearer secret-key"
            body = json.dumps({"notifications": []} if ok else {"error": "Please log in."}).encode()
            self.send_response(200 if ok else 401); self.send_header("content-length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    assert BrainLink(url, "secret-key").key_works()
    assert not BrainLink(url, "wrong").key_works()
    assert seen[0] == "Bearer secret-key"
    server.shutdown()


def test_each_sentence_is_played_as_it_arrives():
    played = []

    class TwoSentences(PretendBrain):
        def voice_stream(self, wav):
            yield ("heard", "turn on the lamp")
            yield ("say", "Sure thing!", b"ONE")
            played.append("--- brain still sending ---")  # the first sentence was already played by now
            yield ("say", "It's on now.", b"TWO")
            yield ("done", {})

    class Recording(PretendSpeaker):
        def play(self, wav):
            played.append(wav)

    body = Body(TwoSentences(), PretendMic([LOUD] * seconds(1) + [QUIET] * seconds(2)), Recording(), PretendWake())
    body.converse()
    assert played.index(b"ONE") < played.index("--- brain still sending ---") < played.index(b"TWO")


def test_voice_stream_reads_the_brains_lines():
    import base64, json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from bolt_body.brain_link import BrainLink

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["content-length"]))
            lines = [{"type": "heard", "text": "hi"},
                     {"type": "say", "text": "Hello!", "audio": base64.b64encode(b"WAV").decode()},
                     {"type": "done", "reply": "Hello!", "timings": {"listening": 1.2}}]
            body = "".join(json.dumps(l) + "\n" for l in lines).encode()
            self.send_response(200); self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *a): pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    events = list(BrainLink(f"http://127.0.0.1:{server.server_port}").voice_stream(b"RIFF"))
    server.shutdown()
    assert events == [("heard", "hi"), ("say", "Hello!", b"WAV"), ("done", {"listening": 1.2})]


def test_unknown_wake_word_explains_itself(monkeypatch):
    """A wake word model that doesn't exist gives a plain-English message, not a traceback."""
    import sys, types
    import pytest
    from bolt_body import wake

    def no_such_model(**kwargs):
        raise ValueError("Could not find pretrained model for model name 'hey_bolt'")

    fake_model = types.ModuleType("openwakeword.model"); fake_model.Model = no_such_model
    fake_utils = types.ModuleType("openwakeword.utils"); fake_utils.download_models = lambda **k: None
    monkeypatch.setitem(sys.modules, "openwakeword", types.ModuleType("openwakeword"))
    monkeypatch.setitem(sys.modules, "openwakeword.model", fake_model)
    monkeypatch.setitem(sys.modules, "openwakeword.utils", fake_utils)
    with pytest.raises(SystemExit, match="hey_jarvis"):
        wake.WakeWord("hey_bolt")
