"""Face recognition: matching, storing (privately), downloading models safely, and when to look."""
import os

import pytest

from bolt_body.faces import FaceBook, best_match, cosine, ensure_models


def test_matching_picks_the_closest_known_person():
    people = {"Luke": [[1, 0, 0], [0.9, 0.1, 0]], "Sarah": [[0, 1, 0]]}
    assert best_match([0.95, 0.05, 0], people)[0] == "Luke"
    assert best_match([0, 0.9, 0.1], people)[0] == "Sarah"
    assert best_match([0, 0, 1], people)[0] is None                    # a stranger: nobody
    assert abs(cosine([1, 0], [1, 0]) - 1) < 1e-9 and cosine([1, 0], [0, 1]) == 0


def test_face_data_is_private_and_can_be_forgotten(tmp_path):
    book = FaceBook(tmp_path / "faces.json")
    book.add("Luke", [[0.1] * 128])
    assert oct(os.stat(tmp_path / "faces.json").st_mode)[-3:] == "600"  # readable by you only
    assert FaceBook(tmp_path / "faces.json").people["Luke"][0][0] == 0.1
    assert book.forget("Luke") and FaceBook(tmp_path / "faces.json").people == {}


def test_a_download_that_doesnt_match_its_fingerprint_is_refused(tmp_path):
    def fetch(url, path):
        open(path, "wb").write(b"not the real model")
    with pytest.raises(RuntimeError, match="fingerprint"):
        ensure_models(tmp_path, {"m.onnx": ("https://x/m.onnx", "0" * 64)}, fetch=fetch)
    assert not (tmp_path / "m.onnx").exists() and not (tmp_path / "m.part").exists()


class Face:
    def __init__(self): self.woken = 0
    def someone_here(self): self.woken += 1
    def set_state(self, n): pass
    def say(self, w): pass


def body():
    from test_body import PretendBrain, PretendMic, PretendSpeaker, PretendWake
    from bolt_body.main import Body
    class Brain(PretendBrain):
        def __init__(self): super().__init__(); self.told = []
        def presence(self, name): self.told.append(name); return True
    b = Body(Brain(), PretendMic([]), PretendSpeaker(), PretendWake())
    b.face = Face()
    b.camera = type("Cam", (), {"frame": lambda self: "PICTURE"})()
    b.faces = type("Rec", (), {"who": lambda self, picture, people: ["Luke"]})()
    b.face_people = {"Luke": [[1.0]]}
    return b


def test_faces_are_only_looked_for_after_movement_and_not_too_often():
    b = body()
    b.look_for_faces(100.0)
    assert b.brain.told == []                                 # nothing moved: don't look
    b.motion.moved_at = 100.0
    b.look_for_faces(101.0)
    assert b.brain.told == ["Luke"] and b.face.woken == 1
    b.look_for_faces(102.0)                                   # under 2 s later: not again yet
    assert b.face.woken == 1
    b.motion.moved_at = 104.0
    b.look_for_faces(104.0)
    assert b.face.woken == 2 and b.brain.told == ["Luke"]     # seen again, but the brain was told a minute ago
    b.motion.moved_at = 170.0
    b.look_for_faces(170.0)
    assert b.brain.told == ["Luke", "Luke"]


def test_recognition_can_be_switched_off():
    from robot_friend_settings_stub import settings
    b = body()
    b.apply_settings({"custom": True, "current": settings(recognise_faces="off")})
    b.motion.moved_at = 100.0
    b.look_for_faces(100.0)
    assert b.brain.told == []
