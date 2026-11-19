"""
Tests for Bolt's ears and mouth.

* The /voice and /speak routes are tested with pretend ears and mouth.
* voice.py is tested against a pretend Wyoming server (no models needed).
* If real Whisper and Piper containers are running, a round-trip test runs too.
"""

import asyncio
import base64
import io
import socket
import threading
import wave
from types import SimpleNamespace as Obj

import pytest
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import async_read_event, async_write_event
from wyoming.tts import Synthesize

from robot_friend import voice
from robot_friend.brain import Brain
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from server import Notifications, create_app


def make_wav(seconds=0.5, rate=16000):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setframerate(rate); w.setsampwidth(2); w.setnchannels(1)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return out.getvalue()


class EchoClaude:
    def __init__(self):
        self.messages = Obj(create=lambda **k: Obj(stop_reason="end_turn", content=[
            Obj(type="text", text="You said: " + k["messages"][-1]["content"].split("] ", 1)[1])]))


def web(tmp_path, ears, mouth):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=EchoClaude())
    return create_app(brain, Notifications(), ears=ears, mouth=mouth, security=Security(tmp_path, open_for_testing=True)).test_client()


# ------------------------------------------------------------ the routes

def test_voice_route_round_trip(tmp_path):
    client = web(tmp_path, ears=lambda wav: "hello bolt", mouth=lambda text: b"RIFF-pretend-audio")
    data = client.post("/voice", data=make_wav(), content_type="audio/wav").get_json()
    assert data["transcript"] == "hello bolt"
    assert data["reply"] == "You said: hello bolt"
    assert base64.b64decode(data["audio"]) == b"RIFF-pretend-audio"


def test_voice_route_heard_nothing(tmp_path):
    client = web(tmp_path, ears=lambda wav: "", mouth=lambda text: b"")
    data = client.post("/voice", data=make_wav(), content_type="audio/wav").get_json()
    assert data["transcript"] == "" and "catch" in data["error"]


def test_voice_route_whisper_down(tmp_path):
    def broken_ears(wav):
        raise voice.VoiceError("Can't reach Whisper")
    client = web(tmp_path, ears=broken_ears, mouth=lambda text: b"")
    response = client.post("/voice", data=make_wav(), content_type="audio/wav")
    assert response.status_code == 502 and "Whisper" in response.get_json()["error"]


def test_voice_route_still_replies_if_piper_down(tmp_path):
    def broken_mouth(text):
        raise voice.VoiceError("Can't reach Piper")
    client = web(tmp_path, ears=lambda wav: "hi", mouth=broken_mouth)
    data = client.post("/voice", data=make_wav(), content_type="audio/wav").get_json()
    assert data["reply"] == "You said: hi" and "Piper" in data["error"]


def test_speak_route(tmp_path):
    client = web(tmp_path, ears=None, mouth=lambda text: b"RIFF" + text.encode())
    response = client.post("/speak", json={"text": "hi"})
    assert response.mimetype == "audio/wav" and response.data == b"RIFFhi"


# ---------------------------------------------- voice.py vs pretend Wyoming

@pytest.fixture
def fake_wyoming():
    """A pretend Whisper + Piper in one: it transcribes and synthesizes."""
    received = {}

    async def handle(reader, writer):
        audio = bytearray()
        while (event := await async_read_event(reader)) is not None:
            if Transcribe.is_type(event.type):
                received["language"] = Transcribe.from_event(event).language
            elif AudioStart.is_type(event.type):
                received["rate"] = AudioStart.from_event(event).rate
            elif AudioChunk.is_type(event.type):
                audio.extend(AudioChunk.from_event(event).audio)
            elif AudioStop.is_type(event.type):
                received["bytes"] = len(audio)
                await async_write_event(Transcript(text=" pretend words ").event(), writer)
            elif Synthesize.is_type(event.type):
                await async_write_event(AudioStart(rate=22050, width=2, channels=1).event(), writer)
                await async_write_event(AudioChunk(rate=22050, width=2, channels=1, audio=b"\x01\x00" * 100).event(), writer)
                await async_write_event(AudioStop().event(), writer)
        writer.close()

    loop = asyncio.new_event_loop()
    server = loop.run_until_complete(asyncio.start_server(handle, "127.0.0.1", 0))
    port = server.sockets[0].getsockname()[1]
    threading.Thread(target=loop.run_forever, daemon=True).start()
    yield port, received
    loop.call_soon_threadsafe(loop.stop)


def test_transcribe_converts_to_16k(fake_wyoming, monkeypatch):
    port, received = fake_wyoming
    monkeypatch.setenv("WHISPER_HOST", "127.0.0.1"); monkeypatch.setenv("WHISPER_PORT", str(port))
    assert voice.transcribe(make_wav(seconds=1, rate=48000)) == "pretend words"
    assert received["language"] == "en"
    assert received["rate"] == 16000
    assert received["bytes"] == 16000 * 2  # one second of 16 kHz, 16-bit audio


def test_synthesize_makes_a_wav(fake_wyoming, monkeypatch):
    port, _ = fake_wyoming
    monkeypatch.setenv("PIPER_HOST", "127.0.0.1"); monkeypatch.setenv("PIPER_PORT", str(port))
    with wave.open(io.BytesIO(voice.synthesize("hi")), "rb") as w:
        assert w.getframerate() == 22050 and w.getnframes() == 100


def test_unreachable_gives_a_clear_error(monkeypatch):
    monkeypatch.setenv("PIPER_HOST", "127.0.0.1"); monkeypatch.setenv("PIPER_PORT", "1")
    with pytest.raises(voice.VoiceError, match="Is its container running"):
        voice.synthesize("hi")


def test_not_a_wav():
    with pytest.raises(voice.VoiceError, match="WAV"):
        voice.transcribe(b"definitely not audio")


# ----------------------------------------- the real thing, if it's running

def _running(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("localhost", port)) == 0


@pytest.mark.skipif(not (_running(10300) and _running(10200)), reason="Whisper/Piper containers not running")
def test_real_round_trip():
    heard = voice.transcribe(voice.synthesize("Remind me to water the plants."))
    assert "plants" in heard.lower()


def test_voice_route_reports_timings(tmp_path):
    client = web(tmp_path, ears=lambda wav: "hi", mouth=lambda text: b"RIFF")
    t = client.post("/voice", data=make_wav(), content_type="audio/wav").get_json()["timings"]
    assert set(t) == {"recording", "listening", "thinking", "speaking"} and all(v >= 0 for v in t.values())
    assert t["recording"] == 0.5  # make_wav() is half a second long


# --------------------------------------------------------- talking while thinking

class StreamingClaude:
    """Pretend Claude that streams its reply in small pieces."""
    def __init__(self, pieces):
        self.pieces = pieces
        self.messages = Obj(stream=self.stream, create=None)

    def stream(self, **kwargs):
        pieces = self.pieces
        final = Obj(stop_reason="end_turn", content=[Obj(type="text", text="".join(pieces))])

        class Stream:
            text_stream = iter(pieces)
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get_final_message(self): return final
        return Stream()


def stream_web(tmp_path, pieces, mouth):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=StreamingClaude(pieces))
    return create_app(brain, Notifications(), ears=lambda wav: "turn on the lamp", mouth=mouth,
                      security=Security(tmp_path, open_for_testing=True)).test_client(), brain


def test_voice_stream_sends_each_sentence_with_its_audio(tmp_path):
    import json
    web, brain = stream_web(tmp_path, ["Sure thing!", " I'll turn the desk", " lamp on now.", " Anything else?"],
                            mouth=lambda text: text.encode())
    lines = [json.loads(l) for l in web.post("/voice/stream", data=make_wav(), content_type="audio/wav").data.decode().splitlines()]
    assert [l["type"] for l in lines] == ["heard", "say", "say", "done"]
    assert lines[0]["text"] == "turn on the lamp"
    assert lines[1]["text"] == "Sure thing! I'll turn the desk lamp on now."
    assert base64.b64decode(lines[1]["audio"]) == lines[1]["text"].encode()
    assert lines[3]["reply"] == "Sure thing! I'll turn the desk lamp on now. Anything else?"
    assert {"recording", "listening", "first_words", "whole_reply"} <= set(lines[3]["timings"])
    assert brain.messages[-1]["role"] == "assistant"  # the reply was remembered


def test_voice_stream_keeps_the_words_if_piper_is_down(tmp_path):
    import json
    def broken_mouth(text):
        raise voice.VoiceError("Can't reach Piper")
    web, _ = stream_web(tmp_path, ["Hello there.", " How are you?"], mouth=broken_mouth)
    lines = [json.loads(l) for l in web.post("/voice/stream", data=make_wav(), content_type="audio/wav").data.decode().splitlines()]
    says = [l for l in lines if l["type"] == "say"]
    assert [s["text"] for s in says] == ["Hello there.", "How are you?"] and all(s["audio"] is None for s in says)
    assert any(l["type"] == "error" and "Piper" in l["error"] for l in lines)


def test_chat_stream_speaks_before_and_after_a_tool(tmp_path):
    """'Let me check.' is spoken straight away, the tool runs, then the rest follows."""
    turns = [
        (["Let me check", " the time."], Obj(stop_reason="tool_use", content=[
            Obj(type="text", text="Let me check the time."),
            Obj(type="tool_use", id="t1", name="list_reminders", input={})])),
        (["You have", " no reminders."], Obj(stop_reason="end_turn", content=[Obj(type="text", text="You have no reminders.")])),
    ]
    calls = []

    def stream(**kwargs):
        pieces, final = turns[len(calls)]
        calls.append({**kwargs, "messages": list(kwargs["messages"])})  # a snapshot, like the real API sees

        class S:
            text_stream = iter(pieces)
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get_final_message(self): return final
        return S()

    brain = Brain(ReminderStore(tmp_path / "r.json"), client=Obj(messages=Obj(stream=stream)))
    from robot_friend.sentences import sentences
    assert list(sentences(brain.chat_stream("any reminders?"))) == ["Let me check the time.", "You have no reminders."]
    assert all(t.get("eager_input_streaming") for t in calls[0]["tools"])      # tool settings stream too
    assert calls[1]["messages"][-1]["content"][0]["type"] == "tool_result"     # the tool's answer went back


def test_chat_stream_refusal_forgets_the_turn(tmp_path):
    def stream(**kwargs):
        class S:
            text_stream = iter([])
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get_final_message(self): return Obj(stop_reason="refusal", content=[])
        return S()
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=Obj(messages=Obj(stream=stream)))
    assert "rather not" in "".join(brain.chat_stream("something"))
    assert brain.messages == []
