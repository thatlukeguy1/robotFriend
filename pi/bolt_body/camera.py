"""
LESSON: Riley's camera (Raspberry Pi Camera Module 3)
=====================================================
The camera does two jobs, and they're kept very different on purpose:

1. NOTICING SOMEONE (stays on the Pi). Twice a second we grab a TINY picture,
   160 x 120 in shades of grey, and compare it with the one before. If enough of
   it has changed, something moved, so the face wakes up (and the screen comes
   back on). No picture ever leaves the Pi for this; each one is forgotten as
   soon as the next arrives.

   Comparing pictures is just subtraction: for each pixel, how different is it
   from last time? A person moving changes a CHUNK of the picture a lot. A light
   being switched on changes EVERYTHING a little, so we ignore that (otherwise
   every lamp would wake her).

2. LOOKING WHEN ASKED (goes to Claude). Only when you ask "what's this?": a proper
   photo, focused first (the Module 3 has autofocus, down to about 10 cm), sent
   to the brain once and not kept.

Test it on the Pi (stop Riley first: sudo systemctl stop bolt-body):

    cd ~/robotFriend/pi && .venv/bin/python -m bolt_body.camera test
"""

import io
import os
import sys
import threading
import time

PHOTO_SIZE = (1024, 768)    # for Claude: sharp enough to read a label, small enough to send quickly
SMALL_SIZE = (160, 120)     # for noticing movement: tiny on purpose
PIXEL_CHANGED = 25          # a pixel counts as "changed" if its brightness moved this much (0-255)
LIGHTS_CHANGED = 30         # the WHOLE picture got this much brighter/darker = lights, not a person


def changed_share(before, after):
    """What fraction of the picture changed between two small grey pictures (numpy arrays).
    Returns 0.0 for a lighting change (everything brighter or darker at once)."""
    import numpy as np
    a, b = before.astype(np.int16), after.astype(np.int16)
    if abs(float(b.mean()) - float(a.mean())) > LIGHTS_CHANGED:
        return 0.0
    return float((np.abs(b - a) > PIXEL_CHANGED).mean())


def needed_share(sensitivity):
    """The Studio's sensitivity (1-10) -> how much of the picture must change.
    1 = a big movement (15% of the picture), 10 = a small one (1%)."""
    s = max(1, min(10, sensitivity))
    return 0.15 * (0.01 / 0.15) ** ((s - 1) / 9)


class MotionWatch:
    """Decides "someone's there" from a stream of small pictures. Pure logic, testable anywhere.
    Three changed pictures in a row are needed (about 1.5 s of movement; a flicker makes two:
    one when it appears, one when it goes), and after waking her
    it waits COOLDOWN seconds before it can do so again."""

    COOLDOWN = 10.0

    def __init__(self, sensitivity=5):
        self.sensitivity = sensitivity
        self.last = None
        self.in_a_row = 0
        self.quiet_until = 0.0

    def update(self, small, now):
        if self.last is None:
            self.last = small
            return False
        moved = changed_share(self.last, small) >= needed_share(self.sensitivity)
        self.last = small
        self.in_a_row = self.in_a_row + 1 if moved else 0
        if self.in_a_row >= 3 and now >= self.quiet_until:
            self.in_a_row = 0
            self.quiet_until = now + self.COOLDOWN
            return True
        return False


class Camera:
    """The real camera, through Picamera2 (sudo apt install python3-picamera2)."""

    def __init__(self, rotation=None):
        from picamera2 import Picamera2
        from libcamera import Transform, controls
        rotation = int(rotation if rotation is not None else os.environ.get("CAMERA_ROTATION", "0"))
        flip = rotation == 180       # mounted upside down in the head? CAMERA_ROTATION=180
        self.cam = Picamera2()
        config = self.cam.create_video_configuration(
            main={"size": PHOTO_SIZE, "format": "RGB888"},
            lores={"size": SMALL_SIZE, "format": "YUV420"},
            transform=Transform(hflip=flip, vflip=flip),
            controls={"FrameRate": 10})                     # 10 a second is plenty, and keeps the Pi cool
        self.cam.configure(config)
        self.cam.start()
        try:
            self.cam.set_controls({"AfMode": controls.AfModeEnum.Continuous})   # keep roughly in focus
        except Exception:
            pass                                            # a camera without autofocus
        self.lock = threading.Lock()

    def small(self):
        """A tiny grey picture for noticing movement (the "Y" part of YUV is the brightness)."""
        with self.lock:
            yuv = self.cam.capture_array("lores")
        return yuv[:SMALL_SIZE[1], :SMALL_SIZE[0]]

    def photo(self):
        """A focused JPEG photo, for when Riley is asked to look."""
        from PIL import Image
        with self.lock:
            try:
                from libcamera import controls
                self.cam.autofocus_cycle()                  # focus on what's in front, then shoot
                pixels = self.cam.capture_array("main")
                self.cam.set_controls({"AfMode": controls.AfModeEnum.Continuous})   # back to following along
            except Exception:
                pixels = self.cam.capture_array("main")     # no autofocus: take it as it is
        # LESSON: Picamera2's "RGB888" is stored blue-green-red, so we turn it round.
        image = Image.fromarray(pixels[..., ::-1].copy())
        out = io.BytesIO()
        image.save(out, "JPEG", quality=85)
        return out.getvalue()


def make_camera():
    """The camera if one's connected (and CAMERA isn't 'off' in bolt.env), otherwise None."""
    if os.environ.get("CAMERA", "on").lower() in ("off", "0", "no"):
        return None
    try:
        return Camera()
    except Exception as e:
        print(f"   (no camera: {e}. Set CAMERA=off in bolt.env to hide this.)", flush=True)
        return None


def test():
    camera = Camera()
    path = os.path.expanduser("~/riley-photo.jpg")
    with open(path, "wb") as f:
        f.write(camera.photo())
    print(f"Took a photo: {path}  (copy it to your computer to check it's the right way up)")
    watch = MotionWatch()
    print("Now watching for movement for 20 seconds: keep still, then wave...")
    end = time.time() + 20
    while time.time() < end:
        small = camera.small()
        share = changed_share(watch.last, small) if watch.last is not None else 0.0
        if watch.update(small, time.monotonic()):
            print(f"   SAW MOVEMENT (changed: {share:.0%})")
        time.sleep(0.5)
    print("Done!")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        print("Usage: python -m bolt_body.camera test")
