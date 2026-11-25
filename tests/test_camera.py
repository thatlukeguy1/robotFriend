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


def test_a_view_brings_back_the_picture_and_checked_boxes(tmp_path):
    import base64
    desk = PhotoDesk()
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None, camera=desk)
    web = create_app(brain, Notifications(), security=Security(tmp_path, open_for_testing=True), camera=desk).test_client()
    web.get("/camera/wanted")                         # the Pi is there
    boxes = [{"kind": "face", "label": "Luke", "box": [1, 2, 3, 4], "score": 0.71},
             {"kind": "thing", "label": "cup<script>", "box": [5, 6, 7, 8]},
             {"kind": "secret", "label": "x", "box": [1, 1, 1, 1]},        # not a kind we know
             {"kind": "face", "label": "y", "box": [1, "a", 1, 1]}]        # not numbers
    def pi():
        for _ in range(100):
            w = web.get("/camera/wanted").get_json()
            if w["id"]:
                assert w["kind"] == "view"
                web.post(f"/camera/photo/{w['id']}", json={"image": base64.b64encode(JPEG).decode(), "boxes": boxes})
                return
            time.sleep(0.02)
    threading.Thread(target=pi, daemon=True).start()
    got = web.get("/camera/view").get_json()
    assert base64.b64decode(got["image"].split(",", 1)[1]) == JPEG
    assert [(b["kind"], b["label"]) for b in got["boxes"]] == [("face", "Luke"), ("thing", "cup<script>")]
    assert desk.requests == {} and got["paused"] is False


def test_a_view_needs_the_body(tmp_path):
    desk = PhotoDesk()
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None, camera=desk)
    web = create_app(brain, Notifications(), security=Security(tmp_path, open_for_testing=True), camera=desk).test_client()
    r = web.get("/camera/view")
    assert r.status_code == 503 and "isn't connected" in r.get_json()["error"]


def test_a_view_that_isnt_base64_is_refused():
    desk = PhotoDesk()
    assert "base64" in desk.deliver_view("x", {"image": "not base64!!"})
    assert "Send" in desk.deliver_view("x", "nope")


def test_a_paused_view_says_so():
    import base64
    desk = PhotoDesk()
    pretend = lambda: [desk.deliver_view(rid, {"image": base64.b64encode(JPEG).decode(), "boxes": [], "paused": True})
                       for _ in range(200) for rid in [desk.wanted()] if rid or time.sleep(0.01)]
    desk.wanted()
    threading.Thread(target=pretend, daemon=True).start()
    got, problem = desk.view(timeout=3)
    assert problem is None and got["paused"] is True
