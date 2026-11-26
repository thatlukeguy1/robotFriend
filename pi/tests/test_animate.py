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


def test_mouth_eases_instead_of_jumping():
    face, clock = animator()
    face.say(wav([12000, -12000] * 8000))                    # a loud second
    clock.t += 0.02
    face.frame()
    first = face.mouth
    run_for(face, clock, 0.5, fps=15)
    assert 0 < first < face.mouth                            # opening, not jumped
    clock.t += 2                                             # the voice has finished
    face.frame()
    assert face.mouth < 0.05                                 # and it closes again


def test_screen_turns_off_when_nobody_is_about_and_back_on_for_the_wake_word():
    class PowerScreen(PretendScreen):
        def __init__(self):
            super().__init__()
            self.power_log = []
        def power(self, on):
            self.power_log.append(on)
    clock = Clock()
    screen = PowerScreen()
    face = FaceAnimator(screen, load_config(), clock=clock, rng=random.Random(1), screen_off_after=60)
    assert face.step() == "drawn"
    clock.t += 61
    assert face.step() == "off" and screen.power_log == [False]
    drawn = len(screen.shown)
    clock.t += 30
    assert face.step() == "off" and len(screen.shown) == drawn       # no drawing while it's off
    face.set_state("listening")                                       # "Hey Riley"
    assert face.step() == "drawn" and screen.power_log == [False, True]


def test_screen_stays_on_while_she_is_busy():
    clock = Clock()
    face = FaceAnimator(PretendScreen(), load_config(), clock=clock, rng=random.Random(1), screen_off_after=60)
    face.set_state("speaking")
    clock.t += 300
    assert face.step() == "drawn"


def test_someone_here_wakes_the_screen():
    clock = Clock()
    face = FaceAnimator(PretendScreen(), load_config(), clock=clock, rng=random.Random(1), screen_off_after=60)
    clock.t += 61
    assert face.step() == "off"
    face.someone_here()                                               # one day: the camera sees movement
    assert face.step() == "drawn"


def test_being_seen_keeps_the_screen_on_but_she_still_dozes():
    """Sitting at the desk without talking: the screen stays on, but her eyes close."""
    clock = Clock()
    face = FaceAnimator(PretendScreen(), load_config(), clock=clock, rng=random.Random(1),
                        sleep_after=600, screen_off_after=900)
    for _ in range(20):                                   # 20 minutes of being seen, never spoken to
        clock.t += 60
        face.someone_seen()
        assert face.step() == "drawn"                    # the screen never goes off...
    face.frame()
    assert face.state == "idle" and clock.t - face.awake_since > face.sleep_after   # ...but she's dozed
    clock.t += 901                                       # everyone leaves: screen off as usual
    assert face.step() == "off"
    face.someone_here()                                  # "Hey Riley": awake again
    assert face.step() == "drawn" and clock.t - face.awake_since < 1


def test_waking_from_a_doze_is_groggy_but_a_quick_wake_is_not():
    from bolt_body.animate import GROGGY_SECONDS, groggy_blink
    def open_after_waking(dozed):
        face, clock = animator(sleep_after=60)
        run_for(face, clock, 70 if dozed else 30)          # long enough to doze off (or not)
        face.set_state("listening")                         # "Hey Riley"
        run_for(face, clock, 0.6)
        early = face.now["left"]["open"]
        run_for(face, clock, GROGGY_SECONDS + 1)
        return early, face.now["left"]["open"]
    groggy_early, groggy_later = open_after_waking(True)
    fresh_early, fresh_later = open_after_waking(False)
    assert groggy_early < fresh_early - 0.2                 # heavy lids at first...
    assert abs(groggy_later - fresh_later) < 0.05           # ...then properly awake
    assert groggy_blink(0.0) == 0 and groggy_blink(0.8 + 0.225) > 0.95 and groggy_blink(5) == 0


def test_an_announcement_at_night_doesnt_keep_the_screen_on():
    """'Motion spotted' at 3am: the picture shows, then the screen goes back off."""
    import io
    from PIL import Image
    face, clock = animator(screen_off_after=40 * 60)
    clock.t += 3 * 3600                                    # hours since anyone was about
    assert face.step() == "off"
    pic = io.BytesIO(); Image.new("RGB", (64, 48), "red").save(pic, "JPEG")
    b = Body(PretendBrain(), PretendMic([]), PretendSpeaker(), PretendWake(), face=face)
    b.brain.speak = lambda text: wav([0] * 1600)               # a real (silent) recording
    b.announce("Motion spotted")
    face.show_picture(pic.getvalue(), seconds=20)
    assert face.step() != "off"                            # the picture shows...
    clock.t += 21
    assert face.step() == "off"                            # ...then dark again, not for another 40 minutes


def test_the_eyeroll_face_rolls_her_eyes_once_as_it_starts():
    from bolt_body.animate import ROLL_SECONDS, eye_roll
    assert eye_roll(0) == (0.0, 0.0) and eye_roll(ROLL_SECONDS) == (0.0, 0.0)
    x1, y1 = eye_roll(ROLL_SECONDS * 0.25)
    x2, y2 = eye_roll(ROLL_SECONDS * 0.5)
    x3, _ = eye_roll(ROLL_SECONDS * 0.75)
    assert x1 < 0 < x3 and y2 < y1 < 0                   # up-left, over the top, up-right
    face, clock = animator()
    face.set_state("unimpressed")                        # the deadpan stare: no roll
    assert face.roll is None
    face.set_state("eyeroll")
    assert face.roll is not None
    started = face.roll
    face.set_state("eyeroll")                            # the same mood again (next sentence): no second roll
    assert face.roll is started
    face.set_state("sarcastic")                          # a smirk, not a roll
    assert face.roll is None
    run_for(face, clock, 1)                              # and it draws
