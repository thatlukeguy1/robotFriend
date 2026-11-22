"""Tests for the animated face, with a pretend screen and a pretend clock."""
import io
import math
import random
import struct
import wave

from bolt_body.animate import FaceAnimator, NoFace, make_face, voice_levels
from bolt_body.face import load_config, params_for
from bolt_body.main import Body
from test_body import LOUD, QUIET, PretendBrain, PretendMic, PretendSpeaker, PretendWake, seconds


class PretendScreen:
    width, height = 320, 240
    def __init__(self):
        self.shown = []
    def show(self, image):
        self.shown.append(image)


class Clock:
    def __init__(self):
        self.t = 100.0
    def __call__(self):
        return self.t


def wav(samples, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def animator(**kw):
    clock = Clock()
    return FaceAnimator(PretendScreen(), load_config(), clock=clock, rng=random.Random(1), **kw), clock


def run_for(face, clock, seconds_, fps=10):
    for _ in range(int(seconds_ * fps)):
        clock.t += 1 / fps
        face.frame()


def test_voice_levels_follow_loudness():
    tone = [int(8000 * math.sin(i / 5)) for i in range(1600)]      # 0.1 s of voice
    levels = voice_levels(wav(tone + [0] * 1600))                  # then 0.1 s of silence
    assert len(levels) == 4 and levels[0] > 0.5 and levels[-1] == 0.0


def test_moods_ease_in_rather_than_jump():
    face, clock = animator()
    face.set_state("sleeping")
    start = face.now["left"]["open"]
    run_for(face, clock, 0.1, fps=10)                              # one frame later...
    one_frame = face.now["left"]["open"]
    run_for(face, clock, 3)                                        # ...and a while later
    goal = params_for(face.config, "sleeping", "left")["open"]
    assert start > one_frame > goal - 0.01                         # moving towards it...
    assert abs(face.now["left"]["open"] - goal) < 0.01             # ...and then there


def test_dozes_off_after_a_while_and_wakes_for_the_wake_word():
    face, clock = animator(sleep_after=60)
    run_for(face, clock, 65)
    sleepy = params_for(face.config, "sleeping", "left")["open"]
    assert abs(face.now["left"]["open"] - sleepy) < 0.05           # nodded off
    face.set_state("listening")
    run_for(face, clock, 3)
    assert face.now["left"]["open"] > 0.5                          # wide awake again


def test_it_blinks():
    face, clock = animator()
    blinked = False
    for _ in range(200):                                           # 10 seconds at 20 fps
        clock.t += 0.05
        if face.blink_amount(face.blinks["left"], 4, clock.t) > 0:
            blinked = True
    assert blinked


def test_frames_are_screen_sized_pictures():
    face, clock = animator()
    face.say(wav([9000, -9000] * 4000))
    clock.t += 0.1
    img = face.frame()
    assert img.size == (320, 240) and face.level(clock.t) > 0.5   # and the mouth is "talking"


def test_body_moods_reach_the_face():
    class PretendFace(NoFace):
        def __init__(self):
            self.states, self.said = [], []
        def set_state(self, name):
            self.states.append(name)
        def say(self, wav_bytes):
            self.said.append(wav_bytes)

    face = PretendFace()
    body = Body(PretendBrain(), PretendMic([LOUD] * seconds(1) + [QUIET] * seconds(2)), PretendSpeaker(),
                PretendWake(), face=face)
    body.converse()
    assert face.states == ["listening", "thinking", "speaking", "idle"]
    assert face.said == [b"REPLY-AUDIO"]                           # the mouth moved with the reply


def test_no_screen_means_no_face(monkeypatch):
    monkeypatch.setenv("SCREEN", "off")
    assert isinstance(make_face(), NoFace)
    monkeypatch.setenv("SCREEN", "on")
    assert isinstance(make_face(), NoFace)                         # no spidev on this computer: carries on
