"""Photos from the body's camera: asked for by the brain, handed in by the Pi."""
import threading
import time
from types import SimpleNamespace as Obj

from robot_friend.brain import Brain
from robot_friend.camera import PhotoDesk
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from server import Notifications, create_app

JPEG = b"\xff\xd8" + b"photo" * 10


def pretend_pi(desk, photo=JPEG, delay=0.05):
    """Checks the desk like the Pi does, and hands in a photo when one is wanted."""
    def run():
        for _ in range(100):
            rid = desk.wanted()
            if rid:
                desk.deliver(rid, photo)
                return
            time.sleep(delay)
    desk.wanted()                                   # the Pi has checked in recently
    threading.Thread(target=run, daemon=True).start()


def test_a_photo_goes_from_the_pi_to_the_brain():
    desk = PhotoDesk()
    pretend_pi(desk)
    photo, problem = desk.take(timeout=3)
    assert photo == JPEG and problem is None
    assert desk.requests == {}                       # nothing kept afterwards


def test_no_body_means_no_waiting():
    started = time.monotonic()
    photo, problem = PhotoDesk().take(timeout=5)
    assert photo is None and "isn't connected" in problem and time.monotonic() - started < 0.5


def test_bad_or_unasked_photos_are_refused():
    desk = PhotoDesk()
    assert "JPEG" in desk.deliver("x", b"not a photo")
    assert "Nobody asked" in desk.deliver("made-up", JPEG)


def test_look_gives_claude_the_picture(tmp_path):
    desk = PhotoDesk()
    pretend_pi(desk)
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None, camera=desk)
    result = brain.run_tool("look", {"question": "what am I holding?"})
    assert result[0]["type"] == "image" and result[0]["source"]["media_type"] == "image/jpeg"
    assert "what am I holding?" in result[1]["text"]


def test_look_without_a_camera(tmp_path):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None)
    assert "don't have a camera" in brain.run_tool("look", {"question": "anything"})


def test_camera_routes(tmp_path):
    desk = PhotoDesk()
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None, camera=desk)
    web = create_app(brain, Notifications(), security=Security(tmp_path, open_for_testing=True), camera=desk).test_client()
    assert web.get("/camera/wanted").get_json() == {"id": None}
    got = {}
    t = threading.Thread(target=lambda: got.update(zip(("photo", "problem"), desk.take(timeout=3))))
    t.start()
    for _ in range(50):
        rid = web.get("/camera/wanted").get_json()["id"]
        if rid:
            break
        time.sleep(0.02)
    assert web.post(f"/camera/photo/{rid}", data=JPEG, content_type="image/jpeg").get_json() == {"status": "thanks"}
    t.join(3)
    assert got["photo"] == JPEG
    assert web.post("/camera/photo/whatever", data=b"nope").status_code == 400
