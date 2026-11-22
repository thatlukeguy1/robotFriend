"""
LESSON: Bolt's ears and mouth on the Pi
=======================================
On the mini PC, Whisper and Piper turn sound into words and back. But the
actual SOUND has to be captured and played somewhere, and that's the Pi's
job, using the microphone and speaker wired to it.

The microphone gives us a never-ending stream of numbers (samples). We read
them in FRAMES of 1280 samples. At 16,000 samples a second, one frame is
80 milliseconds of sound: the size the wake word detector wants.

For testing without a Pi, FileMicrophone reads a WAV file instead, and
FileSpeaker saves what Bolt says into files instead of playing it.
"""

import io
import math
import queue
import struct
import wave
from pathlib import Path

RATE = 16000        # samples per second
FRAME = 1280        # samples per frame (80 ms)
WIDTH = 2           # bytes per sample (16-bit)


# ------------------------------------------------------------- microphones

class Microphone:
    """The real microphone, using the `sounddevice` library."""

    def __init__(self, device=None):
        import sounddevice  # only needed on the real robot
        self.frames = queue.Queue()
        # The callback runs in the background every time a frame is ready.
        self.stream = sounddevice.RawInputStream(
            samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME, device=device,
            callback=lambda data, n, time, status: self.frames.put(bytes(data)),
        )
        self.stream.start()

    def read(self):
        """Wait for the next 80 ms of sound."""
        return self.frames.get()

    def flush(self):
        """Throw away sound that piled up (e.g. Bolt hearing itself talk)."""
        while not self.frames.empty():
            self.frames.get_nowait()


class FileMicrophone:
    """Pretends a WAV file is a microphone. Used for testing on any computer."""

    def __init__(self, path):
        with wave.open(str(path), "rb") as w:
            assert w.getframerate() == RATE and w.getsampwidth() == WIDTH and w.getnchannels() == 1, \
                "Test files must be 16 kHz, 16-bit, mono"
            self.audio = w.readframes(w.getnframes())
        self.pos = 0

    def read(self):
        if self.pos >= len(self.audio):
            raise EOFError("End of the test recording")
        frame = self.audio[self.pos:self.pos + FRAME * WIDTH].ljust(FRAME * WIDTH, b"\0")
        self.pos += FRAME * WIDTH
        return frame

    def flush(self):
        pass


# ---------------------------------------------------------------- speakers

class Speaker:
    """The real speaker."""

    def __init__(self, device=None):
        import sounddevice
        self.sd = sounddevice
        self.device = device
        self.volume = 1.0   # 0 to 1, set from the Studio's Body tab

    def start(self, wav_bytes):
        """Start playing, and come straight back (so Bolt can listen while it talks)."""
        import time
        import numpy as np
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            rate = w.getframerate()
        if self.volume < 1.0:
            # LESSON: volume is just multiplying every sample: 0.5 = half as loud
            samples = (samples * self.volume).astype(np.int16)
        self.sd.play(samples, samplerate=rate, device=self.device)
        self.ends = time.monotonic() + len(samples) / rate

    def busy(self):
        import time
        return time.monotonic() < getattr(self, "ends", 0)

    def stop(self):
        """Cut the sound off (someone interrupted)."""
        self.sd.stop()
        self.ends = 0

    def play(self, wav_bytes):
        self.start(wav_bytes)
        self.sd.wait()  # wait until it's finished speaking


class FileSpeaker:
    """Saves everything Bolt would say as numbered WAV files. For testing."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.count = 0

    def play(self, wav_bytes):
        self.count += 1
        (self.folder / f"{self.count:02d}.wav").write_bytes(wav_bytes)


# ------------------------------------------------------------------ helpers

def loudness(frame):
    """How loud is this frame? (RMS: the 'average size' of the samples.)"""
    samples = struct.unpack(f"<{len(frame) // 2}h", frame)
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def to_wav(frames):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setframerate(RATE); w.setsampwidth(WIDTH); w.setnchannels(1)
        w.writeframes(b"".join(frames))
    return out.getvalue()


def beep(freq=880, ms=120, volume=0.3):
    """Make a short beep. Pure maths, no files!"""
    n = int(RATE * ms / 1000)
    samples = [int(volume * 32767 * math.sin(2 * math.pi * freq * i / RATE) * min(1, (n - i) / 400))
               for i in range(n)]
    return to_wav([struct.pack(f"<{n}h", *samples)])


def chime(notes=(660, 880), ms=140, volume=0.12):
    """
    A soft chime: a few gentle notes instead of a harsh beep.

    LESSON: why a beep sounds harsh. A speaker cone jumping from silent to full
    volume in an instant makes a CLICK, and a pure tone at full volume is piercing.
    So each note here fades IN (a quick "attack") and fades OUT slowly (a "decay",
    like a bell), and the whole thing is quieter. Same maths, much kinder on the ears.
    """
    n = int(RATE * ms / 1000)
    attack = int(RATE * 0.01)                       # 10 ms fade in: no click
    samples = []
    for freq in notes:
        for i in range(n):
            fade_in = min(1.0, i / attack)
            decay = math.exp(-4.0 * i / n)          # dies away like a struck bell
            samples.append(int(volume * 32767 * fade_in * decay * math.sin(2 * math.pi * freq * i / RATE)))
    return to_wav([struct.pack(f"<{len(samples)}h", *samples)])


def record_until_quiet(mic, max_seconds=12, wait_seconds=4, quiet_seconds=1.0, min_level=400, stats=None):
    """
    Record what you say after the wake word.

    LESSON: How does Bolt know you've finished talking?
    It listens to how LOUD each frame is. Once you've started speaking, a
    second of quiet means you've stopped. If you never start, it gives up.
    """
    frames, started, quiet, loudest = [], False, 0, 0.0
    per_second = RATE // FRAME  # 12.5 frames a second
    for i in range(int(max_seconds * per_second)):
        frame = mic.read()
        frames.append(frame)
        level = loudness(frame)
        loudest = max(loudest, level)
        if stats is not None:
            stats["loudest"] = loudest        # so Bolt can say how close it came
        if level > min_level:
            started, quiet = True, 0
        elif started:
            quiet += 1
            if quiet >= quiet_seconds * per_second:
                break
        elif i >= wait_seconds * per_second:
            return None  # you never said anything
    return to_wav(frames) if started else None
