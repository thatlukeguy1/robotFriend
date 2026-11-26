"""Echo cancelling: hearing "Hey Riley" over her own voice (see bolt_body/echo.py)."""
import numpy as np

from bolt_body.echo import EchoCanceller, find_delay, to_16k

RNG = np.random.default_rng(1)


def speechish(seconds, rate, seed):
    """Noise shaped a bit like speech: more low pitches, in syllables."""
    r = np.random.default_rng(seed)
    n = int(seconds * rate)
    x = np.convolve(r.standard_normal(n), np.exp(-np.arange(40) / 6), "same")
    t = np.arange(n) / rate
    return x / np.std(x) * 4000 * (np.sin(t * 2 * np.pi * 3.5) > -0.2) * (0.5 + 0.5 * np.abs(np.sin(t * 7)))


ROOM = np.zeros(900)
ROOM[0], ROOM[37], ROOM[210] = 0.9, -0.4, 0.25
ROOM[300:] = RNG.standard_normal(600) * 0.02 * np.exp(-np.arange(600) / 150)


def say(ec, voice, rate, delay, mic_from, you=None):
    """Play `voice` into a pretend room; feed the mic to the canceller. Returns (mic, cleaned)."""
    echo = np.convolve(to_16k(voice, rate), ROOM)[:len(to_16k(voice, rate))]
    mic = np.zeros(len(echo) + delay + 3000)
    mic[delay:delay + len(echo)] += np.tanh(echo / 20000) * 20000        # small speakers distort a bit
    mic += RNG.standard_normal(len(mic)) * 30
    if you is not None:
        mic[20000:20000 + len(you)] += you
    ec.begin(voice, rate, mic_from)
    out = [np.frombuffer(ec.clean(np.clip(mic[i:i + 1280], -32768, 32767).astype(np.int16).tobytes(), mic_from + i),
                         dtype=np.int16) for i in range(0, len(mic) - 1280, 1280)]
    return mic, np.concatenate(out).astype(float)


def test_her_voice_is_taken_out_and_yours_is_kept():
    ec = EchoCanceller()
    say(ec, speechish(3, 22050, 0), 22050, 1500, 0)
    assert ec.delay == 1500 and ec.report() > 10                      # the first sentence: learning
    say(ec, speechish(3, 22050, 1), 22050, 1620, 100_000)
    assert ec.delay == 1620 and ec.report() > 15                      # it kept what it learned
    you = speechish(10000 / 16000, 16000, 99)[:10000] * 0.35          # you: much quieter than her
    mic, out = say(ec, speechish(3, 22050, 2), 22050, 1580, 200_000, you=you)
    part = slice(20000, 30000)
    her_before, her_after = mic[part] - you, out[part] - you
    assert 10 * np.log10((her_before @ her_before) / (her_after @ her_after)) > 10   # her: much quieter
    assert (out[part] - her_after) @ you > 0.8 * (you @ you)                          # you: still there


def test_find_delay():
    voice = speechish(1, 16000, 3)
    mic = np.concatenate([np.zeros(777), voice * 0.5])[:16000] + RNG.standard_normal(16000) * 30
    assert find_delay(mic, voice) == 777
    assert find_delay(RNG.standard_normal(16000) * 30, np.zeros(16000)) is None     # she's silent


def test_resampling_keeps_the_length_and_the_sound():
    t = np.arange(22050) / 22050
    tone = 1000 * np.sin(2 * np.pi * 440 * t)
    out = to_16k(tone, 22050)
    assert len(out) == 16000 and abs(np.std(out) - np.std(tone)) < 5


def test_before_any_speech_frames_pass_through():
    ec = EchoCanceller()
    frame = (np.arange(1280, dtype=np.int16) % 50).tobytes()
    assert ec.clean(frame, 0) == frame


def test_she_listens_through_the_canceller_while_talking():
    from test_body import PretendBrain, PretendMic, PretendSpeaker, PretendWake
    from bolt_body.main import Body
    class Speaker(PretendSpeaker):
        def __init__(self): super().__init__(); self.left = 3
        def start(self, audio): self.last = (np.zeros(100), 16000)
        def busy(self):
            self.left -= 1
            return self.left >= 0
        def stop(self): pass
    class Mic(PretendMic):
        count, position = 0, 0
        def read(self): return b"\0\0" * 1280
    seen = []
    class Echo:
        started_at = None
        def begin(self, samples, rate, at): seen.append(("begin", at))
        def clean(self, frame, at): seen.append("clean"); return frame
        def report(self): return 18.0
    b = Body(PretendBrain(), Mic([]), Speaker(), PretendWake())
    b.echo = Echo()
    b.wake.threshold = 0.5
    b.wake.heard = lambda frame: False
    assert b.play(b"RIFF") is True
    assert seen == [("begin", 0), "clean", "clean", "clean"]
    seen.clear(); b.echo_on = False                         # Studio: switched off
    b.speaker.left = 2
    b.play(b"RIFF")
    assert seen == []


def test_never_makes_her_louder_whatever_the_delay():
    """The bug the real Pi found: at some delays the first nudge was enormous and the filter
    never recovered, making her voice LOUDER at the mic. And late echoes were missed."""
    from bolt_body.echo import _test_sound
    sound = _test_sound()
    voice = to_16k(sound, 22050)
    for delay in (1500, 7000, 12000):
        mic = np.zeros(len(voice) + delay + 4000)
        mic[delay:delay + len(voice)] += 0.6 * voice
        ec = EchoCanceller()
        ec.begin(sound, 22050, 0)
        for i in range(0, len(mic) - 1280, 1280):
            ec.clean(np.clip(mic[i:i + 1280], -32768, 32767).astype(np.int16).tobytes(), i)
        assert ec.delay == delay and ec.report() > 12, (delay, ec.delay, ec.report())


def test_a_slow_speaker_is_matched_by_stretching_her_voice(tmp_path, monkeypatch):
    """Riley's speaker plays 0.23% slow, so her voice drifts later at the mic. Stretched by the
    same amount (measured once by the self-test), it lines up again."""
    import bolt_body.echo as echo
    from bolt_body.echo import _test_sound, stretched
    sound = _test_sound()
    played = stretched(to_16k(sound, 22050), 1 / 0.9977)          # what a slow speaker plays
    mic = np.zeros(len(played) + 4000)
    mic[800:800 + len(played)] += 0.6 * played

    def cancel(stretch):
        ec = EchoCanceller(stretch=stretch)
        for _ in range(2):
            ec.begin(sound, 22050, 0)
            for i in range(0, len(mic) - 1280, 1280):
                ec.clean(np.clip(mic[i:i + 1280], -32768, 32767).astype(np.int16).tobytes(), i)
        return ec.report()
    assert cancel(1.0) < 5 and cancel(1 / 0.9977) > 10
    monkeypatch.setattr(echo, "STRETCH_FILE", tmp_path / "echo.json")
    (tmp_path / "echo.json").write_text('{"stretch": 1.0023}')
    assert EchoCanceller().stretch == 1.0023                          # saved by the self-test
    (tmp_path / "echo.json").write_text('{"stretch": 7}')
    assert EchoCanceller().stretch == 1.0                             # nonsense is ignored
