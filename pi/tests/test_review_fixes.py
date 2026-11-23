"""Pi-side tests for the fixes from the code review."""
from test_body import LOUD, QUIET, PretendBrain, PretendMic, PretendSpeaker, PretendWake

from bolt_body.audio import record_until_quiet
from bolt_body.main import Body


def body(brain=None):
    return Body(brain or PretendBrain(), PretendMic([]), PretendSpeaker(), PretendWake())


# 4. Reminders keep flowing when the brain restarts (and old ones aren't read out at start)
class ListBrain(PretendBrain):
    def __init__(self):
        super().__init__()
        self.boot, self.items, self.down = "A", [], False
    def notifications(self, after):
        if self.down:
            return None
        return {"boot": self.boot, "items": [n for n in self.items if n["id"] > after]}


def test_reminders_survive_a_brain_restart():
    brain = ListBrain()
    brain.items = [{"id": i, "text": f"old {i}"} for i in range(1, 61)]
    b, place = body(brain), {}
    b.check_reminders(place)
    assert b.announcements == [] and place["seen"] == 60            # old ones skipped at start
    brain.boot, brain.items = "B", [{"id": 1, "text": "bins tonight"}]   # restarted: numbers begin again
    b.check_reminders(place)
    assert b.announcements == ["bins tonight"]


def test_a_brain_that_cant_be_reached_at_start_doesnt_cause_a_flood():
    brain = ListBrain()
    brain.down = True
    b, place = body(brain), {}
    b.check_reminders(place)                                         # no answer: nothing decided yet
    brain.down, brain.items = False, [{"id": i, "text": f"old {i}"} for i in range(1, 51)]
    b.check_reminders(place)
    assert b.announcements == []                                     # the 50 old ones aren't read out
    brain.items.append({"id": 51, "text": "new one"})
    b.check_reminders(place)
    assert b.announcements == ["new one"]


# 7. A photo asked for from the typed chat doesn't leave the face stuck
def test_face_goes_back_after_a_photo():
    class Face:
        state = "idle"
        def set_state(self, name): self.state = name
        def someone_here(self): pass
        def say(self, wav): pass
    class Camera:
        def photo(self): return b"\xff\xd8JPEG"
        def small(self): raise RuntimeError("not needed")
    class Brain(PretendBrain):
        asked = ["r1"]
        def photo_wanted(self): return self.asked.pop() if self.asked else None
        def send_photo(self, rid, jpeg): return True
    b = body(Brain())
    b.face, b.camera, b.camera_wakes = Face(), Camera(), False
    b.watch_camera(sleep=lambda s: None, rounds=1)
    assert b.face.state == "idle"


# 9. Interrupting closes the connection to the brain
def test_interrupting_hangs_up_on_the_brain():
    from bolt_body.brain_link import BrainLink
    closed = []
    class Reply:
        headers = {"Content-Type": "application/x-ndjson"}
        def iter_lines(self):
            yield b'{"type": "say", "text": "One.", "audio": null}'
            yield b'{"type": "say", "text": "Two.", "audio": null}'
        def close(self): closed.append(True)
    link = BrainLink("http://brain")
    link.http.post = lambda *a, **k: Reply()
    stream = link.voice_stream(b"RIFF")
    next(stream)
    stream.close()                                                   # "Hey Riley!" mid-reply
    assert closed == [True]


# 11 + 12. The settings check survives problems, and new face designs arrive
def test_new_face_designs_arrive_without_a_restart():
    class Face:
        config = {"expressions": {"idle": {}}}
    class Brain(PretendBrain):
        def body_settings(self): return None
        def face_design(self): return {"expressions": {"idle": {}, "wink": {}}}
    b = body(Brain())
    b.face = Face()
    b.check_settings(None)
    assert "wink" in b.face.config["expressions"]


# 13. Listening windows are as long as the settings say
def test_waiting_four_seconds_means_fifty_frames():
    class Count(PretendMic):
        reads = 0
        def read(self):
            self.reads += 1
            return QUIET
    mic = Count([])
    assert record_until_quiet(mic, wait_seconds=4) is None
    assert mic.reads == 51                                           # 4 s x 12.5 frames, then give up


def test_interrupt_sensitivity_comes_from_the_studio_and_is_logged(capsys):
    from robot_friend_settings_stub import settings
    from test_body import ScoreWake, TalkingSpeaker
    speaker = TalkingSpeaker(frames_long=10)
    b = Body(PretendBrain(), PretendMic([QUIET] * 20), speaker, ScoreWake([0.1, 0.72, 0.75, 0.1]))
    assert b.play(b"AUDIO") is True                                   # 0.75 < 0.9: she carries on...
    assert "best 'Hey Riley' score 0.75, needs 0.90" in capsys.readouterr().out   # ...and says how close it was
    b.apply_settings({"custom": True, "current": settings(interrupt_threshold=0.7)})
    b.wake = ScoreWake([0.1, 0.72, 0.75, 0.1])
    assert b.play(b"AUDIO") is False and speaker.stopped == 1         # with the bar at 0.7, she stops
    assert b.wake.threshold == 0.5                                    # normal waking is untouched
