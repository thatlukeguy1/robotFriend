"""The printed parts must fit together before anyone pays for a print (docs/print/make_parts.py)."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("manifold3d")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docs" / "print"))
import make_parts as parts  # noqa: E402


def test_everything_fits():
    assert parts.problems() == []


def test_the_check_catches_a_servo_clash():
    old = parts.PI_AT
    try:
        parts.PI_AT = (-20.0, -30.0)          # slide the Pi forward, under the pan servo
        assert any("pan servo hits the pi" in p for p in parts.problems())
    finally:
        parts.PI_AT = old


def test_every_part_is_one_solid_and_fits_a_small_printer():
    built, _ = parts.build()
    for name, (m, _) in built.items():
        assert m.volume() > 1000, name                           # not empty
        x0, y0, z0, x1, y1, z1 = m.bounding_box()
        assert max(x1 - x0, y1 - y0) <= 180 and z1 - z0 <= 180, name   # fits a 180 mm printer
        assert len(m.decompose()) == 1, f"{name} is in more than one piece"
