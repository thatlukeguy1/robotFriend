"""
LESSON: The same eyes, in Python
================================
The browser draws Bolt's eyes with JavaScript (web/eyes.js). The Pi will draw
them with Python, onto two little round GC9A01 screens. To make sure both look
the same, they share:

  * the SETTINGS: designed in the Eye Studio and saved on the brain. The Pi
    asks the brain for the latest design, and falls back to web/expressions.json
    (the original) if the brain can't be reached
  * the MATHS: geometry() below is a line-by-line copy of the JavaScript one

Each frame we draw a picture (an "image") with the Pillow library, then send
it to the screen. Until the screens arrive, you can save the pictures instead:

    python -m bolt_body.eyes preview eyes.png
"""

import json
import math
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

EXPRESSIONS = Path(__file__).resolve().parents[2] / "web" / "expressions.json"
SIZE = 240        # the GC9A01 screens are 240 x 240 pixels
SMOOTH = 3        # draw 3x bigger, then shrink: makes the edges smooth (anti-aliasing)


def load_config(path=EXPRESSIONS, brain_url=None):
    """The latest eye design: from the brain if possible, otherwise the original file."""
    if brain_url:
        try:
            with urllib.request.urlopen(brain_url.rstrip("/") + "/static/expressions.json", timeout=5) as r:
                return json.loads(r.read())
        except (OSError, ValueError):
            pass  # brain unreachable or answered nonsense: use the original
    return json.loads(Path(path).read_text())


def params_for(config, name, side):
    """The full settings for one eye in one expression (defaults, then the expression, then that eye)."""
    exp = config["expressions"].get(name, {})
    return {**config["defaults"], **{k: v for k, v in exp.items() if k not in ("left", "right")}, **exp.get(side, {})}


def curve(x0, y0, cx, cy, x1, y1, steps=24):
    """Points along a curved line from (x0,y0) to (x1,y1), bending through (cx,cy)."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        pts.append((u * u * x0 + 2 * u * t * cx + t * t * x1, u * u * y0 + 2 * u * t * cy + t * t * y1))
    return pts


def geometry(size, p, eye, side, blink=0.0, bob=0.0):
    """Exactly the same maths as geometry() in web/eyes.js."""
    R = size / 2
    c = R
    open_ = max(0.0, p["open"] * (1 - blink))
    iris_r = eye["irisRadius"] * R
    ix = c + p["lookX"] * eye["lookRange"] * R
    iy = c + p["lookY"] * eye["lookRange"] * R + bob * R
    pupil_r = eye["pupilRadius"] * iris_r * p["pupil"]

    low_y = c + 1.15 * R - p["lowerLid"] * 1.15 * R
    smile = 0.5 * R * p["lowerLid"] * min(1, open_ * 2)
    bottom = curve(-0.2 * R, low_y + smile * 0.4, c, low_y - smile, size + 0.2 * R, low_y + smile * 0.4)

    edge_y = low_y + (c - 1.05 * R - low_y) * open_
    inner = 1 if side == "left" else -1
    lean = math.tan(math.radians(p["tilt"])) * R
    y_left, y_right = edge_y - lean * inner, edge_y + lean * inner
    arch = 0.45 * R * min(1, open_ * 1.5)
    top = curve(-0.2 * R, y_left, c, edge_y - arch, size + 0.2 * R, y_right)

    return {"R": R, "c": c, "iris_r": iris_r, "ix": ix, "iy": iy, "pupil_r": pupil_r, "top": top, "bottom": bottom}


def draw_eye(p, config, side, blink=0.0, bob=0.0, size=SIZE):
    """Draw one eye and return it as a size x size picture."""
    big = size * SMOOTH
    col = config["colors"]
    g = geometry(big, p, config["eye"], side, blink, bob)
    img = Image.new("RGB", (big, big), col["background"])
    d = ImageDraw.Draw(img)

    def circle(x, y, r, fill):
        r = max(0.0, r)
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    circle(g["ix"], g["iy"], g["iris_r"], col["irisRing"])
    circle(g["ix"], g["iy"], g["iris_r"] * 0.86, col["iris"])
    circle(g["ix"], g["iy"], g["pupil_r"], col["pupil"])
    circle(g["ix"] - g["iris_r"] * 0.32, g["iy"] - g["iris_r"] * 0.34, g["iris_r"] * 0.17, col["highlight"])
    circle(g["ix"] + g["iris_r"] * 0.3, g["iy"] + g["iris_r"] * 0.28, g["iris_r"] * 0.07, col["highlight"])

    d.polygon([(-1, -1), *g["top"], (big + 1, -1)], fill=col["lid"])
    d.polygon([(-1, big + 1), *g["bottom"], (big + 1, big + 1)], fill=col["lid"])

    # The screen is round: paint the corners black (they're hidden on a real GC9A01 anyway).
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    img = Image.composite(img, Image.new("RGB", (big, big), "black"), mask)
    return img.resize((size, size), Image.LANCZOS)


def preview(path, config=None):
    """Save every expression as one picture, two eyes per row, to check the design."""
    config = config or load_config()
    names = list(config["expressions"])
    gap = 20
    sheet = Image.new("RGB", (SIZE * 2 + gap * 3, (SIZE + gap) * len(names) + gap), "#0b0e14")
    for row, name in enumerate(names):
        for col, side in enumerate(("left", "right")):
            eye = draw_eye(params_for(config, name, side), config, side)
            sheet.paste(eye, (gap + col * (SIZE + gap), gap + row * (SIZE + gap)))
    sheet.save(path)
    return names


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "preview":
        print("Drew:", ", ".join(preview(sys.argv[2])), "->", sys.argv[2])
    else:
        print("Usage: python -m bolt_body.eyes preview eyes.png")
