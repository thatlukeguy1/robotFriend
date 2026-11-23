"""The camera: noticing movement (on the Pi only) and taking a photo when the brain asks."""
import numpy as np

from bolt_body.camera import MotionWatch, changed_share, needed_share

STILL = np.full((120, 160), 100, dtype=np.uint8)


def person(x):
    """The still room, with a darker 'person' 40 pixels wide at x."""
    frame = STILL.copy()
    frame[20:120, x:x + 40] = 30
    return frame


def test_changes_are_measured_and_lights_are_ignored():
    assert changed_share(STILL, STILL) == 0.0
    assert 0.15 < changed_share(STILL, person(60)) < 0.25      # a person-sized chunk changed
    assert changed_share(STILL, STILL + 60) == 0.0              # the lights came on: everything changed


def test_sensitivity_runs_from_big_to_small_movements():
    assert needed_share(1) == 0.15 and abs(needed_share(10) - 0.01) < 1e-9
    assert needed_share(3) > needed_share(7)


def test_someone_walking_in_wakes_her_once():
    watch, t, woke = MotionWatch(), 0.0, []
    for frame in [STILL] * 3 + [person(x) for x in range(0, 120, 20)] + [person(100)] * 5:
        t += 0.5
        woke.append(watch.update(frame, t))
    assert woke.count(True) == 1                                # once, then the cooldown


def test_a_single_flicker_doesnt_wake_her():
    watch, t = MotionWatch(), 0.0
    results = []
    for frame in [STILL, STILL, person(40), STILL, STILL]:
        t += 0.5
        results.append(watch.update(frame, t))
    assert not any(results)


class PretendCamera:
    def __init__(self, frames): self.frames, self.photos = list(frames), 0
    def small(self): return self.frames.pop(0) if self.frames else STILL
    def photo(self):
        self.photos += 1
        return b"\xff\xd8JPEG"


class Face:
    def __init__(self): self.woken, self.states = 0, []
    def someone_here(self): self.woken += 1
    def set_state(self, name): self.states.append(name)
    def say(self, wav): pass


def body_with(camera, wanted=()):
    from bolt_body.main import Body
    from test_body import PretendBrain, PretendMic, PretendSpeaker, PretendWake
    class Brain(PretendBrain):
        def __init__(self):
            super().__init__()
            self.wanted, self.photos = list(wanted), []
        def photo_wanted(self): return self.wanted.pop(0) if self.wanted else None
        def send_photo(self, rid, jpeg): self.photos.append((rid, jpeg)); return True
    b = Body(Brain(), PretendMic([]), PretendSpeaker(), PretendWake())
    b.face, b.camera = Face(), camera
    return b


def test_photos_go_to_the_brain_only_when_asked():
    b = body_with(PretendCamera([]), wanted=[None, "abc", None])
    b.watch_camera(sleep=lambda s: None, rounds=3)
    assert b.brain.photos == [("abc", b"\xff\xd8JPEG")] and b.camera.photos == 1


def test_movement_wakes_the_face_unless_switched_off():
    frames = [STILL] + [person(x) for x in range(0, 120, 20)]
    t = iter(range(100))
    b = body_with(PretendCamera(frames))
    b.watch_camera(sleep=lambda s: None, clock=lambda: next(t), rounds=len(frames))
    assert b.face.woken == 1
    b = body_with(PretendCamera(frames))
    b.camera_wakes = False
    b.watch_camera(sleep=lambda s: None, clock=lambda: next(t), rounds=len(frames))
    assert b.face.woken == 0


def test_studio_settings_reach_the_camera():
    from robot_friend_settings_stub import settings
    b = body_with(PretendCamera([]))
    b.apply_settings({"custom": True, "current": settings(camera_wakes="off", motion_sensitivity=8)})
    assert b.camera_wakes is False and b.motion.sensitivity == 8
