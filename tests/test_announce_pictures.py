"""Home Assistant camera pictures that come with an announcement."""
import io
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image

from robot_friend.brain import Brain
from robot_friend.home_assistant import HomeAssistant, HomeAssistantError
from robot_friend.reminders import ReminderStore
from robot_friend.security import Security
from server import Notifications, create_app


def jpeg():
    out = io.BytesIO()
    Image.new("RGB", (640, 480), "orange").save(out, "JPEG")
    return out.getvalue()


@pytest.fixture
def ha():
    """A pretend Home Assistant with one camera (and a saved snapshot)."""
    asked = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            asked.append((self.path, self.headers.get("Authorization")))
            if self.path.startswith("/api/states"):
                body, kind = b"[]", "application/json"
            elif self.path in ("/api/camera_proxy/camera.front_door", "/local/snaps/door.jpg"):
                body, kind = jpeg(), "image/jpeg"
            else:
                self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *a): pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield HomeAssistant(url=f"http://127.0.0.1:{server.server_port}", token="t0ken", blocked_domains=["lock"]), asked
    server.shutdown()


def web_with(tmp_path, home):
    brain = Brain(ReminderStore(tmp_path / "r.json"), client=None, home=home)
    notes = Notifications()
    return create_app(brain, notes, security=Security(tmp_path, open_for_testing=True)).test_client(), notes


def test_snapshots_come_from_ha_with_the_token(ha):
    home, asked = ha
    assert home.camera_snapshot(camera="camera.front_door").startswith(b"\xff\xd8")
    assert home.camera_snapshot(image="/api/camera_proxy/camera.front_door?token=abc").startswith(b"\xff\xd8")
    assert home.camera_snapshot(image="/local/snaps/door.jpg").startswith(b"\xff\xd8")
    # a full address (like a Nabu Casa one) is fetched from OUR Home Assistant, by its path
    assert home.camera_snapshot(image="https://abc.ui.nabu.casa/local/snaps/door.jpg").startswith(b"\xff\xd8")
    assert asked[-1][0] == "/local/snaps/door.jpg"
    assert all(auth == "Bearer t0ken" for _, auth in asked)


@pytest.mark.parametrize("camera, image", [("light.kitchen", ""), ("", "/local/../secrets.yaml"),
                                           ("", "https://elsewhere.example/x.jpg"), ("", "/api/states")])
def test_only_cameras_and_pictures_can_be_fetched(ha, camera, image):
    home, _ = ha
    with pytest.raises(HomeAssistantError):
        home.camera_snapshot(camera=camera, image=image)


def test_a_blocked_camera_stays_invisible(ha):
    home, _ = ha
    home.blocked.add("camera")
    with pytest.raises(HomeAssistantError):
        home.camera_snapshot(camera="camera.front_door")


def test_announce_with_a_camera_picture(tmp_path, ha):
    home, _ = ha
    web, notes = web_with(tmp_path, home)
    said = web.post("/announce", json={"message": "Someone's at the door", "camera": "camera.front_door"}).get_json()
    assert said["picture"] is True
    item = notes.after(0)[0]
    got = web.get(item["picture"])
    assert got.status_code == 200 and got.mimetype == "image/jpeg" and got.data.startswith(b"\xff\xd8")


def test_a_missing_picture_still_gets_said(tmp_path, ha):
    home, _ = ha
    web, notes = web_with(tmp_path, home)
    said = web.post("/announce", json={"message": "Motion", "camera": "camera.garden"}).get_json()
    assert said["picture"] is False and "404" in said["picture_problem"]
    assert notes.after(0)[0]["text"] == "Motion" and "picture" not in notes.after(0)[0]


def test_only_the_newest_pictures_are_kept(tmp_path, ha):
    home, _ = ha
    web, notes = web_with(tmp_path, home)
    for i in range(7):
        web.post("/announce", json={"message": f"m{i}", "camera": "camera.front_door"})
    links = [n["picture"] for n in notes.after(0)]
    assert web.get(links[0]).status_code == 404 and web.get(links[-1]).status_code == 200
