"""The base's parts must fit before the brass is bent (docs/frame/make_template.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docs" / "frame"))
import make_template as frame  # noqa: E402


def test_everything_fits_in_the_base():
    assert frame.fits() == []


def test_the_check_catches_a_clash_and_a_corner():
    bad = dict(frame.BASE_LAYOUT)
    bad["speaker"] = (29, 50, 70, 18, 4, 34, "under the servo")
    assert "pan_servo and speaker collide" in frame.fits(bad)
    bad = dict(frame.BASE_LAYOUT)
    bad["amp"] = (108, 70, 18, 18, 9, 19, "in the corner")
    assert "amp hits a rounded corner of the base" in frame.fits(bad)
