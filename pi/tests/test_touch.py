"""The touch screen: taps and holds, with pretend fingers (no Pi needed)."""
from types import SimpleNamespace as Obj

from bolt_body.touch import Gestures


def run(presses, step=0.02):
    """presses: (pressed?, seconds) pairs. Returns every event, in order."""
    g, t, events = Gestures(), 0.0, []
    for pressed, seconds in presses:
        for _ in range(round(seconds / step)):
            t += step
            events += g.update(pressed, t)
    return [e for e in events if e[0] != "hold"], [e[1] for e in events if e[0] == "hold"]


def test_a_quick_tap():
    events, holds = run([(False, 0.1), (True, 0.2), (False, 0.2)])
    assert events == [("down",), ("tap",)] and holds == []


def test_a_glitch_is_ignored():
    events, _ = run([(True, 0.02), (False, 0.3)])
    assert events == []


def test_a_flickering_hold_is_still_one_hold():
    flicker = [(True, 0.6), (False, 0.06)] * 10                  # contact drops for 60 ms, ten times
    events, holds = run(flicker + [(False, 0.3)])
    assert events == [("down",), ("off",)] and holds[-1] == 1.0


def test_two_quick_taps_are_two_taps():
    events, _ = run([(True, 0.15), (False, 0.3), (True, 0.15), (False, 0.3)])
    assert events == [("down",), ("tap",), ("down",), ("tap",)]


def test_holding_fills_up_then_turns_off_once():
    events, holds = run([(True, 6.0), (False, 0.2)])
    assert events == [("down",), ("off",)]                       # no tap, no cancel, "off" only once
    assert holds[0] < 0.05 and holds[-1] == 1.0 and holds == sorted(holds)


def test_letting_go_early_cancels():
    events, holds = run([(True, 3.0), (False, 0.2)])
    assert events == [("down",), ("cancel",)] and 0.4 < holds[-1] < 0.6


class Face:
    def __init__(self): self.power_hold, self.woken, self.state = 0.0, 0, None
    def someone_here(self): self.woken += 1
    def set_state(self, name): self.state = name
    def say(self, wav): pass


def body():
    from bolt_body.main import Body
    from test_body import PretendBrain, PretendMic, PretendSpeaker, PretendWake
    b = Body(PretendBrain(), PretendMic([]), PretendSpeaker(), PretendWake())
    b.face = Face()
    return b


def test_touches_reach_the_body():
    b = body()
    b.on_touch(("down",))
    assert b.face.woken == 1                                     # the screen wakes at once
    b.on_touch(("tap",))
    assert b.touched.is_set()
    b.on_touch(("hold", 0.5))
    assert b.face.power_hold == 0.5
    b.on_touch(("cancel",))
    assert b.face.power_hold == 0.0


def test_turning_off_says_goodnight_then_shuts_down():
    b, ran = body(), []
    b.power_off(run=lambda cmd, **kw: ran.append(cmd) or Obj(returncode=0, stderr=""))
    assert b.brain.spoken == ["Turning off. Goodnight!"] and b.speaker.played == [b"REMINDER-AUDIO"]
    assert ran == [["sudo", "-n", "/usr/bin/systemctl", "poweroff"]] and b.turning_off


def test_if_shutting_down_isnt_allowed_she_carries_on():
    b = body()
    b.power_off(run=lambda cmd, **kw: Obj(returncode=1, stderr="sudo: a password is required"))
    assert not b.turning_off and b.face.power_hold == 0.0


def test_a_tap_wakes_her_up():
    from test_body import LOUD, QUIET, PretendBrain, PretendMic, PretendSpeaker, PretendWake, seconds
    from bolt_body.main import Body
    brain = PretendBrain()
    b = Body(brain, PretendMic([QUIET] * 5 + [LOUD] * seconds(1) + [QUIET] * seconds(3)), PretendSpeaker(), PretendWake())
    b.touched.set()
    try:
        b.run()
    except EOFError:
        pass
    assert len(brain.sent) == 1                                  # she listened and answered, no wake word needed


def test_a_tap_stops_her_talking():
    from test_body import PretendBrain, PretendMic, QUIET, ScoreWake, TalkingSpeaker
    from bolt_body.main import Body
    speaker = TalkingSpeaker(frames_long=50)
    b = Body(PretendBrain(), PretendMic([QUIET] * 60), speaker, ScoreWake([]))
    class TapSoon:
        """The 'mic' notices a tap on its third frame."""
        def __init__(self, mic): self.mic, self.n = mic, 0
        def read(self):
            self.n += 1
            if self.n == 3:
                b.touched.set()
            return self.mic.read()
        def flush(self): self.mic.flush()
    b.mic = TapSoon(b.mic)
    assert b.play(b"AUDIO") is False and speaker.stopped == 1


def test_studio_timings_reach_the_touch_panel():
    from robot_friend_settings_stub import settings
    from bolt_body.touch import Gestures
    b = body()
    b.touch = Obj(gestures=Gestures())
    b.apply_settings({"custom": True, "current": settings(touch_min_ms=200, touch_hold_seconds=3)})
    g = b.touch.gestures
    assert g.debounce == 0.2 and g.hold_off == 3.0
    t, events = 0.0, []
    for pressed, seconds in ((True, 0.15), (False, 0.3), (True, 3.2), (False, 0.3)):
        for _ in range(round(seconds / 0.02)):
            t += 0.02
            events += [e for e in g.update(pressed, t) if e[0] != "hold"]
    assert events == [("down",), ("off",)]          # the 0.15 s brush is ignored; 3 s is enough to turn off
