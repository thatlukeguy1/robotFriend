"""
LESSON: Ears and a mouth
========================
Bolt's voice is made of two separate programs, each in its own container:

  * WHISPER (the ears): speech-to-text. You give it a recording, it gives
    back the words it heard.
  * PIPER (the mouth): text-to-speech. You give it words, it gives back a
    recording of a voice saying them.

Both speak the WYOMING protocol: a simple "language" for sending audio and
text between voice programs. Home Assistant speaks it too, which is why HA's
own voice assistant can use the very same containers.

LESSON: What is digital audio?
==============================
A microphone measures air pressure thousands of times a second. Each
measurement is a number called a SAMPLE.
  * RATE = samples per second. Whisper likes 16,000 (16 kHz).
  * WIDTH = bytes per sample. 2 bytes (16-bit) is standard.
  * CHANNELS = 1 for mono (one microphone).
A WAV file is just those numbers with a small header that says the rate,
width and channels. We send audio in CHUNKS: small slices, one after another.

Try it yourself (inside the container):
    docker exec bolt python -m robot_friend.voice selftest
"""

import asyncio
import io
import os
import sys
import time
import wave

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize

WHISPER_RATE = 16000  # Whisper wants 16 kHz, 16-bit, mono
TIMEOUT = 60  # seconds; give up rather than hang forever


class VoiceError(Exception):
    """Something went wrong talking to Whisper or Piper."""


def _address(name, default_port):
    """Read e.g. WHISPER_HOST / WHISPER_PORT from the environment."""
    host = os.environ.get(f"{name}_HOST", "localhost")
    port = int(os.environ.get(f"{name}_PORT", default_port))
    return host, port


async def _connect(name, host, port):
    client = AsyncTcpClient(host, port)
    try:
        await asyncio.wait_for(client.connect(), timeout=5)
    except (OSError, asyncio.TimeoutError) as e:
        raise VoiceError(f"Can't reach {name} at {host}:{port}. Is its container running?") from e
    return client


# ---------------------------------------------------------------- the ears

async def _transcribe(wav_bytes, host, port):
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        rate, width, channels = wav.getframerate(), wav.getsampwidth(), wav.getnchannels()
        frames = wav.readframes(wav.getnframes())

    # If the recording isn't already 16 kHz mono 16-bit, convert it.
    converter = AudioChunkConverter(rate=WHISPER_RATE, width=2, channels=1)
    chunk = converter.convert(AudioChunk(rate=rate, width=width, channels=channels, audio=frames))

    client = await _connect("Whisper", host, port)
    try:
        # 1. "Please transcribe what I'm about to send, in English."
        await client.write_event(Transcribe(language="en").event())
        # 2. The audio: a start marker, the audio in slices, a stop marker.
        await client.write_event(AudioStart(rate=chunk.rate, width=chunk.width, channels=chunk.channels).event())
        slice_size = 2048 * chunk.width  # bytes per slice
        for i in range(0, len(chunk.audio), slice_size):
            await client.write_event(AudioChunk(rate=chunk.rate, width=chunk.width, channels=chunk.channels,
                                                audio=chunk.audio[i:i + slice_size]).event())
        await client.write_event(AudioStop().event())
        # 3. Wait for Whisper to answer with the words it heard.
        while True:
            event = await client.read_event()
            if event is None:
                raise VoiceError("Whisper hung up without answering.")
            if Transcript.is_type(event.type):
                return Transcript.from_event(event).text.strip()
    finally:
        await client.disconnect()


def transcribe(wav_bytes):
    """Turn a WAV recording into text."""
    host, port = _address("WHISPER", 10300)
    try:
        return asyncio.run(asyncio.wait_for(_transcribe(wav_bytes, host, port), TIMEOUT))
    except asyncio.TimeoutError as e:
        raise VoiceError("Whisper took too long to answer.") from e
    except wave.Error as e:
        raise VoiceError(f"That recording isn't a WAV file Bolt can read ({e}).") from e


# --------------------------------------------------------------- the mouth

async def _synthesize(text, host, port):
    client = await _connect("Piper", host, port)
    audio, fmt = bytearray(), None
    try:
        await client.write_event(Synthesize(text=text).event())
        # Piper answers with: AudioStart, lots of AudioChunks, AudioStop.
        while True:
            event = await client.read_event()
            if event is None:
                raise VoiceError("Piper hung up before finishing.")
            if AudioStart.is_type(event.type):
                fmt = AudioStart.from_event(event)
            elif AudioChunk.is_type(event.type):
                chunk = AudioChunk.from_event(event)
                fmt = fmt or chunk
                audio.extend(chunk.audio)
            elif AudioStop.is_type(event.type):
                break
    finally:
        await client.disconnect()

    if fmt is None:
        raise VoiceError("Piper didn't send any audio.")
    # Wrap the raw samples in a WAV header so anything can play them.
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setframerate(fmt.rate)
        wav.setsampwidth(fmt.width)
        wav.setnchannels(fmt.channels)
        wav.writeframes(bytes(audio))
    return out.getvalue()


def synthesize(text):
    """Turn text into a WAV recording of Bolt's voice."""
    host, port = _address("PIPER", 10200)
    try:
        return asyncio.run(asyncio.wait_for(_synthesize(text, host, port), TIMEOUT))
    except asyncio.TimeoutError as e:
        raise VoiceError("Piper took too long to answer.") from e


# ---------------------------------------------------------------- self-test

def selftest():
    """Piper says a sentence, then Whisper listens to it. A round trip!"""
    sentence = "Hello! This is Bolt, testing my ears and my mouth."
    try:
        start = time.time()
        wav_bytes = synthesize(sentence)
        spoke = time.time() - start
        start = time.time()
        heard = transcribe(wav_bytes)
        listened = time.time() - start
    except VoiceError as e:
        print(f"❌ {e}")
        return False
    print(f"👄 Piper said:    {sentence!r}  ({spoke:.1f}s)")
    print(f"👂 Whisper heard: {heard!r}  ({listened:.1f}s)")
    print("✅ Voice is working!" if "bolt" in heard.lower() else "⚠ Whisper heard something different. Check the model.")
    return True


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        sys.exit(0 if selftest() else 1)
    print("Usage: python -m robot_friend.voice selftest")
