"""
LESSON: Recognising faces (on the Pi, and only the Pi)
=====================================================
Two small "neural network" models from OpenCV do the work:

  * YuNet FINDS faces in a picture (where they are, and where the eyes, nose
    and mouth are).
  * SFace DESCRIBES a face as 128 numbers. Two pictures of the same person give
    very similar numbers; different people give different ones. "Similar" is
    measured with COSINE SIMILARITY: 1.0 = identical, 0 = nothing in common.
    Above about 0.36 is the same person (we use a slightly stricter 0.40).

Teaching Riley a face ("enrolling") takes about 10 looks at you from slightly
different angles and keeps their numbers. Afterwards, when the camera sees a
face, its numbers are compared with everyone she knows.

PRIVACY, by design:
  * Only the NUMBERS are kept, in ~/.config/riley/faces.json (readable by you
    only). No photos are kept, not even while enrolling.
  * Faces she doesn't know are ignored and never stored.
  * Only a NAME ever leaves the Pi ("Luke is at the desk").
  * Only enrol people who've said yes. `forget NAME` deletes someone completely.

On the Pi (stop Riley first: sudo systemctl stop bolt-body):

    cd ~/robotFriend/pi
    .venv/bin/python -m bolt_body.faces enroll Luke     # teach her a face
    .venv/bin/python -m bolt_body.faces list            # who she knows
    .venv/bin/python -m bolt_body.faces test            # who she can see right now
    .venv/bin/python -m bolt_body.faces forget Luke     # delete someone's face data
"""

import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
MODELS = {   # file: (where to get it, its SHA-256 fingerprint: a download that doesn't match is refused)
    "face_detection_yunet_2023mar.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/"
        "face_detection_yunet_2023mar.onnx", "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/"
        "face_recognition_sface_2021dec.onnx", "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}
FACES_FILE = Path(os.environ.get("FACES_FILE", "~/.config/riley/faces.json")).expanduser()
SAME_PERSON = 0.40       # cosine similarity above this = the same person
SMALLEST_FACE = 60       # pixels: a face smaller than this is too far away to recognise reliably
ENROLL_LOOKS = 10


def _fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ensure_models(folder=MODEL_DIR, models=MODELS, fetch=urllib.request.urlretrieve):
    """Download the two models the first time (about 39 MB), checking each one's fingerprint."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, (url, sha) in models.items():
        path = folder / name
        if path.exists() and _fingerprint(path) == sha:
            continue
        print(f"   (downloading {name}...)", flush=True)
        temp = path.with_suffix(".part")
        fetch(url, temp)
        if _fingerprint(temp) != sha:
            temp.unlink(missing_ok=True)
            raise RuntimeError(f"{name} didn't match its fingerprint, so it wasn't used. Try again later.")
        temp.replace(path)
    return folder


class FaceBook:
    """Who Riley knows: {name: [descriptions]}, each description 128 numbers."""

    def __init__(self, path=FACES_FILE):
        self.path = Path(path)
        self.people = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.people))
        os.chmod(temp, 0o600)                       # your eyes only
        temp.replace(self.path)

    def add(self, name, descriptions):
        self.people[name] = [list(map(float, d)) for d in descriptions]
        self.save()

    def forget(self, name):
        found = self.people.pop(name, None) is not None
        self.save()
        return found


def cosine(a, b):
    import numpy as np
    a, b = np.asarray(a, dtype=float).ravel(), np.asarray(b, dtype=float).ravel()
    return float(a @ b / ((np.linalg.norm(a) * np.linalg.norm(b)) or 1.0))


def best_match(description, people, threshold=SAME_PERSON):
    """(name, score) of whoever this face looks most like, or (None, score) if nobody's close enough."""
    best, score = None, 0.0
    for name, known in people.items():
        s = max((cosine(description, k) for k in known), default=0.0)
        if s > score:
            best, score = name, s
    return (best, score) if score >= threshold else (None, score)


class Recogniser:
    """The two OpenCV models (opencv-python-headless, installed by pi/update.sh)."""

    def __init__(self, folder=None):
        import cv2
        folder = ensure_models() if folder is None else Path(folder)
        self.cv2 = cv2
        self.finder = cv2.FaceDetectorYN.create(str(folder / "face_detection_yunet_2023mar.onnx"), "", (320, 240), 0.7, 0.3, 50)
        self.describer = cv2.FaceRecognizerSF.create(str(folder / "face_recognition_sface_2021dec.onnx"), "")

    def describe_all(self, picture):
        """Every face big enough to recognise in a picture (blue-green-red order, like the camera
        gives): [description]."""
        h, w = picture.shape[:2]
        self.finder.setInputSize((w, h))
        _, found = self.finder.detect(picture)
        if found is None:
            return []
        return [self.describer.feature(self.describer.alignCrop(picture, f)).ravel()
                for f in found if min(f[2], f[3]) >= SMALLEST_FACE]

    def who(self, picture, people):
        """The names of everyone she knows in this picture."""
        names = []
        for d in self.describe_all(picture):
            name, _ = best_match(d, people)
            if name and name not in names:
                names.append(name)
        return names


def make_recogniser():
    """A Recogniser if OpenCV is installed and at least one face has been taught, else None."""
    if not FaceBook().people:
        return None
    try:
        return Recogniser()
    except Exception as e:
        print(f"   (no face recognition: {e})", flush=True)
        return None


# ---------------------------------------------------------------- the commands

def enroll(name):
    from .camera import Camera
    if not name.replace(" ", "").replace("-", "").isalpha() or len(name) > 30:
        print("Use a plain name, like Luke.")
        return 1
    rec, cam, book = Recogniser(), Camera(), FaceBook()
    print(f"Teaching Riley {name}'s face. Look at the camera, about an arm's length away,")
    print("and slowly turn your head a little left and right. (Nothing is photographed or kept but numbers.)")
    looks, tries = [], 0
    while len(looks) < ENROLL_LOOKS and tries < 60:
        tries += 1
        found = rec.describe_all(cam.frame())
        if len(found) == 1:
            looks.append(found[0])
            print(f"   got look {len(looks)} of {ENROLL_LOOKS}", flush=True)
        elif len(found) > 1:
            print("   (more than one face: just the person being taught, please)", flush=True)
        time.sleep(0.6)
    if len(looks) < 5:
        print("Couldn't see a face clearly enough. More light, a bit closer, facing the camera, then try again.")
        return 1
    book.add(name, looks)
    print(f"Done: Riley knows {name} ({len(looks)} looks). Start her again: sudo systemctl start bolt-body")
    return 0


def main(args):
    if args[:1] == ["enroll"] and len(args) == 2:
        return enroll(args[1])
    if args == ["list"]:
        people = FaceBook().people
        print("Riley knows:", ", ".join(f"{n} ({len(v)} looks)" for n, v in people.items()) or "nobody yet")
        return 0
    if args[:1] == ["forget"] and len(args) == 2:
        print("Forgotten." if FaceBook().forget(args[1]) else f"Riley doesn't know anyone called {args[1]}.")
        return 0
    if args == ["test"]:
        from .camera import Camera
        rec, cam, people = Recogniser(), Camera(), FaceBook().people
        print("Watching for 20 seconds...")
        end = time.time() + 20
        while time.time() < end:
            picture = cam.frame()
            for d in rec.describe_all(picture):
                name, score = best_match(d, people)
                who = name or "someone she does not know"
                print(f"   {who} (similarity {score:.2f})", flush=True)
            time.sleep(1)
        return 0
    print("Usage: python -m bolt_body.faces enroll NAME | list | test | forget NAME")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
