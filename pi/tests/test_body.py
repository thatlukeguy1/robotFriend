"""
Tests for Bolt's body, using pretend parts: no Pi, microphone or network needed.
Run from the pi/ folder:  python -m pytest
"""

import io
import struct
import wave

from bolt_body.audio import FRAME, beep, chime, loudness, record_until_quiet
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
    assert mic.flushed == 2 and wake.resets >= 1     # ignored its own beep, then its own voice


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


def test_brain_trouble_plays_falling_notes():
    class BrokenBrain(PretendBrain):
        def voice_stream(self, wav):
            yield ("error", "Can't reach Bolt's brain")
    speaker = PretendSpeaker()
    body = Body(BrokenBrain(), PretendMic([LOUD] * seconds(1) + [QUIET] * seconds(2)), speaker, PretendWake())
    body.converse()
    assert speaker.played[-1] == chime((440, 330))


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


def test_bolt_does_not_record_its_own_beep():
    """What the mic heard during the beep is thrown away before recording starts."""
    class BufferingMic(PretendMic):
        def __init__(self, during_beep, afterwards):
            super().__init__(afterwards)
            self.queued = list(during_beep)    # piled up while the beep played
        def read(self):
            return self.queued.pop(0) if self.queued else super().read()
        def flush(self):
            self.queued = []
            super().flush()

    brain = PretendBrain()
    speech = [LOUD] * seconds(1)
    mic = BufferingMic(during_beep=[LOUD] * 3,                       # the beep, heard by the mic
                       afterwards=[QUIET] * seconds(1.5) + speech + [QUIET] * seconds(2))
    Body(brain, mic, PretendSpeaker(), PretendWake()).converse()
    with wave.open(io.BytesIO(brain.sent[0]), "rb") as w:
        recorded = w.readframes(w.getnframes())
    assert recorded.count(LOUD) == len(speech)  # all of you, none of the beep


def test_near_misses_are_reported_once(capsys):
    """A try that scores 0.3-0.4 against a 0.5 threshold prints ONE 'nearly woke' line, with the best score."""
    class ScoringWake(PretendWake):
        def __init__(self, scores):
            super().__init__()
            self.scores, self.threshold = list(scores), 0.5
        def heard(self, frame):
            self.last_score = self.scores.pop(0) if self.scores else 0.0
            return self.last_score >= self.threshold

    scores = [0.0, 0.3, 0.42, 0.35, 0.1] + [0.0] * 10 + [0.1, 0.2]   # one near miss, then quiet noise
    body = Body(PretendBrain(), PretendMic([QUIET] * len(scores)), PretendSpeaker(), ScoringWake(scores))
    try:
        body.run()
    except EOFError:
        pass
    lines = [l for l in capsys.readouterr().out.splitlines() if "nearly woke" in l]
    assert lines == ["   (nearly woke: score 0.42, needs 0.50)"]


def test_wake_word_gets_a_spoken_reply_not_the_same_twice():
    class TalkingBrain(PretendBrain):
        def speak(self, text):
            self.spoken.append(text)
            return f"AUDIO:{text}".encode()
    brain, speaker = TalkingBrain(), PretendSpeaker()
    body = Body(brain, PretendMic([QUIET] * 2), speaker, PretendWake())
    assert body.load_acks(["Yes?", "Mm-hm?", ""]) == 2
    assert brain.spoken == ["Yes?", "Mm-hm?"]                  # recorded once, at start-up
    replies = []
    for _ in range(6):
        speaker.played.clear()
        body.acknowledge()
        replies.append(speaker.played[0])
    assert all(a != b for a, b in zip(replies, replies[1:]))   # never the same one twice running


def test_no_replies_means_a_soft_chime():
    speaker = PretendSpeaker()
    body = Body(PretendBrain(), PretendMic([]), speaker, PretendWake())
    body.acknowledge()
    assert speaker.played == [chime()]


def test_chime_fades_in_with_no_click():
    with wave.open(io.BytesIO(chime()), "rb") as w:
        first = struct.unpack("<20h", w.readframes(20))
    assert max(abs(x) for x in first) < 1000                   # starts quietly, not at full volume


def test_quiet_mic_still_counts_as_talking_in_a_quiet_room():
    """A soft voice (level 300) in a quiet room (level 40) is heard, though it's under the old fixed 400."""
    soft = struct.pack(f"<{FRAME}h", *([300, -300] * (FRAME // 2)))
    hum = struct.pack(f"<{FRAME}h", *([40, -40] * (FRAME // 2)))
    body = Body(PretendBrain(), PretendMic([]), PretendSpeaker(), PretendWake())
    for _ in range(300):                                   # 24 seconds of a quiet room
        body.hear_background(hum)
    assert 35 < body.background < 50 and 120 <= body.speech_level() < 150
    body.mic = PretendMic([soft] * seconds(1) + [hum] * seconds(2))
    body.converse()
    assert len(body.brain.sent) == 1


def test_talking_does_not_teach_it_the_room_is_noisy():
    body = Body(PretendBrain(), PretendMic([]), PretendSpeaker(), PretendWake())
    body.background = 50.0
    for _ in range(50):
        body.hear_background(LOUD)                          # someone chatting nearby
    assert body.background == 50.0


def test_hearing_nothing_says_how_close_it_came(capsys):
    body = Body(PretendBrain(), PretendMic([QUIET] * seconds(10)), PretendSpeaker(), PretendWake())
    body.converse()
    assert "loudest sound 0, talking needs 300, background 100" in capsys.readouterr().out


def test_studio_body_settings_are_applied_live():
    class TalkingBrain(PretendBrain):
        def speak(self, text):
            self.spoken.append(text)
            return f"AUDIO:{text}".encode()
    speaker, wake = PretendSpeaker(), PretendWake()
    speaker.volume, wake.threshold, wake.frames_needed = 1.0, 0.5, 1
    brain = TalkingBrain()
    body = Body(brain, PretendMic([]), speaker, wake)
    settings = {"volume": 40, "sleep_after_minutes": 3, "screen_off_minutes": 5, "wake_threshold": 0.35, "wake_frames": 2, "listen_seconds": 6,
                "replies": ["Hiya!"]}
    assert body.apply_settings({"custom": False, "current": settings}) is False   # not saved in the Studio yet
    assert speaker.volume == 1.0
    assert body.apply_settings({"custom": True, "current": settings}) is True
    assert (speaker.volume, wake.threshold, wake.frames_needed, body.listen_seconds, body.face.sleep_after) == (0.4, 0.35, 2, 6, 180)
    assert brain.spoken == ["Hiya!"] and body.acks == [b"AUDIO:Hiya!"]
    body.apply_settings({"custom": True, "current": settings})
    assert brain.spoken == ["Hiya!"]                                   # same replies: not recorded again


def test_listen_seconds_sets_how_long_it_waits():
    body = Body(PretendBrain(), PretendMic([QUIET] * seconds(20)), PretendSpeaker(), PretendWake())
    body.listen_seconds = 2
    body.converse()
    assert len(body.mic.frames) >= seconds(20) - seconds(2) - 2       # gave up after about 2 seconds


def test_speaker_volume_scales_the_sound(monkeypatch):
    import sys, types
    played = {}
    fake = types.ModuleType("sounddevice")
    fake.play = lambda samples, samplerate, device: played.setdefault("samples", samples)
    fake.wait = lambda: None
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    from bolt_body.audio import Speaker, to_wav
    speaker = Speaker()
    speaker.volume = 0.5
    speaker.play(to_wav([struct.pack("<2h", 10000, -10000)]))
    assert list(played["samples"]) == [5000, -5000]


def test_wake_word_can_require_several_checks_in_a_row():
    from bolt_body.wake import WakeWord
    wake = WakeWord.__new__(WakeWord)              # no model needed: we feed it scores directly
    wake.threshold, wake.frames_needed, wake.in_a_row, wake.last_score = 0.5, 2, 0, 0.0
    tv_spike = [wake.judge(s) for s in (0.1, 0.8, 0.2, 0.1)]
    assert not any(tv_spike)                       # one high check on its own: ignored
    real = [wake.judge(s) for s in (0.3, 0.7, 0.9, 0.6)]
    assert real == [False, False, True, True]      # two in a row: awake


class QuestionBrain(PretendBrain):
    """Asks a question the first time, then just answers."""
    def voice_stream(self, wav):
        self.sent.append(wav)
        yield ("heard", "hello")
        if len(self.sent) == 1:
            yield ("say", "Do you fancy a cup of tea?", b"QUESTION-AUDIO")
        else:
            yield ("say", "Lovely, I'll remind you.", b"REPLY-AUDIO")
        yield ("done", {})


def test_she_listens_for_your_answer_after_asking_a_question():
    talk = [LOUD] * seconds(1) + [QUIET] * seconds(1.5)
    brain = QuestionBrain()
    body = Body(brain, PretendMic(talk + talk + [QUIET] * seconds(10)), PretendSpeaker(), PretendWake())
    body.converse()
    assert len(brain.sent) == 2                 # your answer went to the brain, with no wake word


def test_nobody_answers_and_she_goes_back_to_waiting():
    talk = [LOUD] * seconds(1) + [QUIET] * seconds(1.5)
    brain = QuestionBrain()
    body = Body(brain, PretendMic(talk + [QUIET] * seconds(10)), PretendSpeaker(), PretendWake())
    body.converse()
    assert len(brain.sent) == 1


def test_follow_ups_can_be_switched_off():
    talk = [LOUD] * seconds(1) + [QUIET] * seconds(1.5)
    brain = QuestionBrain()
    body = Body(brain, PretendMic(talk + talk + [QUIET] * seconds(10)), PretendSpeaker(), PretendWake())
    body.follow_up_seconds = 0
    body.converse()
    assert len(brain.sent) == 1


class TalkingSpeaker(PretendSpeaker):
    """Plays for a number of mic frames, and can be cut off."""
    def __init__(self, frames_long=10):
        super().__init__()
        self.frames_long, self.left, self.stopped = frames_long, 0, 0
    def start(self, wav):
        self.played.append(wav)
        self.left = self.frames_long
    def busy(self):
        self.left -= 1
        return self.left >= 0
    def stop(self):
        self.stopped += 1
        self.left = 0


class ScoreWake(PretendWake):
    """Scores each frame from a list, so we can say WHEN 'Hey Riley' happens."""
    def __init__(self, scores):
        super().__init__()
        self.scores, self.threshold, self.frames_needed, self.in_a_row = list(scores), 0.5, 1, 0
    def heard(self, frame):
        self.last_score = self.scores.pop(0) if self.scores else 0.0
        self.in_a_row = self.in_a_row + 1 if self.last_score >= self.threshold else 0
        return self.in_a_row >= self.frames_needed


def test_hey_riley_while_she_talks_stops_her_and_she_listens():
    talk = [LOUD] * seconds(1) + [QUIET] * seconds(1.5)
    speaker = TalkingSpeaker(frames_long=10)
    wake = ScoreWake([0.1, 0.95, 0.97])               # you say "Hey Riley" during her reply
    brain = PretendBrain()
    body = Body(brain, PretendMic(talk + [QUIET] * 10 + talk + [QUIET] * seconds(10)), speaker, wake)
    body.converse()
    assert speaker.stopped == 1                       # she stopped talking...
    assert len(brain.sent) == 2                       # ...and listened to what you said next


def test_her_own_voice_does_not_interrupt_her():
    """A single loud-ish spike while she talks (her own voice) isn't enough: it must be very sure, twice."""
    speaker = TalkingSpeaker(frames_long=6)
    body = Body(PretendBrain(), PretendMic([QUIET] * 20), speaker, ScoreWake([0.7, 0.95, 0.1, 0.8]))
    assert body.play(b"AUDIO") is True and speaker.stopped == 0
    assert body.wake.threshold == 0.5 and body.wake.frames_needed == 1   # normal settings put back
