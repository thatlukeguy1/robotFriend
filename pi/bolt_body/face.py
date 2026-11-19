"""
LESSON: The same face, in Python
================================
The browser draws Bolt's face with JavaScript (web/face.js). The Pi draws it
with Python, onto the 2.8" 320 x 240 screen. To make sure they look the same,
they share:

  * the SETTINGS: designed in the Studio and saved on the brain. The Pi asks
    the brain for the latest design, and falls back to web/expressions.json
    (the original) if the brain can't be reached
  * the MATHS: geometry() below is a line-by-line copy of the JavaScript one

Each frame we draw a picture with the Pillow library, then send it to the
screen. Until the screen arrives, you can save the pictures instead:

    python -m bolt_body.face preview face.png
"""

import json
import math
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

EXPRESSIONS = Path(__file__).resolve().parents[2] / "web" / "expressions.json"
WIDTH, HEIGHT = 320, 240   # the ILI9341 screen
SMOOTH = 3                 # draw 3x bigger, then shrink: smooth edges (anti-aliasing)


def load_config(path=EXPRESSIONS, brain_url=None):
    """The latest face design: from the brain if possible, otherwise the original file."""
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
    base = {k: v for k, v in exp.items() if k not in ("left", "right")}
    return {**config["defaults"], **base, **exp.get(side, {})}


def curve(x0, y0, cx, cy, x1, y1, steps=20):
    """Points along a curved line from (x0,y0) to (x1,y1), bending towards (cx,cy)."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        pts.append((u * u * x0 + 2 * u * t * cx + t * t * x1, u * u * y0 + 2 * u * t * cy + t * t * y1))
    return pts


def geometry(W, H, p, face, blink, bob=0.0, level=0.0):
    """Exactly the same maths as geometry() in web/face.js."""
    shapes = {"eyes": {}, "brows": {}}
    ew, eh = face["eyeWidth"] * W, face["eyeHeight"] * H
    for side in ("left", "right"):
        q = p[side]
        d = -1 if side == "left" else 1
        cx = W / 2 + d * face["eyeSpacing"] * W / 2 + q["lookX"] * face["lookRange"] * ew * 0.12
        cy = face["eyeY"] * H - bob * H + q["lookY"] * face["lookRange"] * eh * 0.12
        box = {"x": cx - ew / 2, "y": cy - eh / 2, "w": ew, "h": eh, "r": face["corner"] * min(ew, eh)}
        pr = face["pupilRadius"] * eh * q["pupil"]
        px = cx + q["lookX"] * face["lookRange"] * (ew / 2 - pr * 0.6)
        py = cy + q["lookY"] * face["lookRange"] * (eh / 2 - pr * 0.6)

        hh, hw = eh / 2, ew / 2
        open_ = max(0.0, q["open"] * (1 - blink[side]))
        low_y = cy + 1.15 * hh - q["lowerLid"] * 1.15 * hh
        smile = 0.5 * hh * q["lowerLid"] * min(1, open_ * 2)
        pad = hw * 0.3
        bottom = curve(cx - hw - pad, low_y + smile * 0.4, cx, low_y - smile, cx + hw + pad, low_y + smile * 0.4)
        edge_y = low_y + (cy - 1.05 * hh - low_y) * open_
        inner = 1 if side == "left" else -1
        lean = math.tan(math.radians(q["tilt"])) * hw
        arch = 0.45 * hh * min(1, open_ * 1.5)
        top = curve(cx - hw - pad, edge_y - lean * inner, cx, edge_y - arch, cx + hw + pad, edge_y + lean * inner)
        shapes["eyes"][side] = {"box": box, "ring": 0.07 * min(ew, eh), "px": px, "py": py, "pr": pr,
                                "top": top, "bottom": bottom}

        by = box["y"] - face["browGap"] * H - q["browRaise"] * 0.06 * H
        half, thick = ew * 0.42, face["browThickness"] * H
        brow_lean = math.tan(math.radians(q["browTilt"])) * half
        pts = []
        for i in range(21):
            t = i / 20
            s = 2 * t - 1
            w = thick * (0.45 + 0.55 * math.sin(math.pi * t))
            y = by - q["browArch"] * 0.06 * H * (1 - s * s) + brow_lean * inner * s
            pts.append((cx - half + 2 * half * t, max(w / 2 + 1, y), w))  # never off the top of the screen
        shapes["brows"][side] = {"pts": pts, "show": max(0.0, min(1.0, q["browShow"]))}

    def avg(k):
        return (p["left"][k] + p["right"][k]) / 2

    mx, my = W / 2, face["mouthY"] * H - bob * H
    half = (face["mouthWidth"] * W / 2) * avg("mouthWidth")
    bend = avg("mouthSmile") * 0.07 * H
    opening = min(1, avg("mouthOpen") + level * 0.9) * 0.1 * H
    shapes["mouth"] = {
        "upper": curve(mx - half, my, mx, my + bend, mx + half, my),
        "lower": curve(mx - half, my, mx, my + bend + opening * 2, mx + half, my),
        "open": opening, "thick": 0.03 * H,
    }
    return shapes


def _thick_line(d, pts, width, fill):
    """A line with round ends (Pillow's lines have flat ends)."""
    d.line(pts, fill=fill, width=max(1, round(width)), joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def draw_face(p, config, blink=None, bob=0.0, level=0.0, size=(WIDTH, HEIGHT)):
    """Draw the whole face and return it as a picture. p: {"left": settings, "right": settings}."""
    blink = blink or {"left": 0.0, "right": 0.0}
    W, H = size[0] * SMOOTH, size[1] * SMOOTH
    col = config["colors"]
    g = geometry(W, H, p, config["face"], blink, bob, level)
    img = Image.new("RGB", (W, H), col["background"])

    for side in ("left", "right"):
        e = g["eyes"][side]
        b = e["box"]
        # Draw the eye on its own layer, then stamp it through a rounded-square stencil (a "mask").
        layer = Image.new("RGB", (W, H), col["irisRing"])
        d = ImageDraw.Draw(layer)
        ring = e["ring"]
        d.rounded_rectangle((b["x"] + ring, b["y"] + ring, b["x"] + b["w"] - ring, b["y"] + b["h"] - ring),
                            radius=max(0, b["r"] - ring), fill=col["iris"])

        def dot(x, y, r, c):
            r = max(0.0, r)
            d.ellipse((x - r, y - r, x + r, y + r), fill=c)

        dot(e["px"], e["py"], e["pr"], col["pupil"])
        dot(e["px"] + e["pr"] * 0.45, e["py"] - e["pr"] * 0.5, e["pr"] * 0.32, col["highlight"])
        dot(e["px"] + e["pr"] * 0.95, e["py"] - e["pr"] * 0.05, e["pr"] * 0.14, col["highlight"])
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle((b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]), radius=b["r"], fill=255)
        img.paste(layer, (0, 0), mask)
        # Eyelids go just outside the eye's outline too, so a shut eye leaves no faint edge.
        lid = ImageDraw.Draw(img)
        lx0, lx1 = e["top"][0][0], e["top"][-1][0]
        lid.polygon([(lx0, b["y"] - 2), *e["top"], (lx1, b["y"] - 2)], fill=col["lid"])
        lid.polygon([(lx0, b["y"] + b["h"] + 2), *e["bottom"], (lx1, b["y"] + b["h"] + 2)], fill=col["lid"])

        br = g["brows"][side]
        if br["show"] > 0.01:  # eyebrows only appear in moods that use them, and can be half-faded
            layer = Image.new("L", (W, H), 0)
            ld = ImageDraw.Draw(layer)
            alpha = round(255 * br["show"])
            ld.polygon([(x, y - w / 2) for x, y, w in br["pts"]] + [(x, y + w / 2) for x, y, w in reversed(br["pts"])],
                       fill=alpha)
            for x, y, w in (br["pts"][0], br["pts"][-1]):
                ld.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=alpha)
            img.paste(Image.new("RGB", (W, H), col["brow"]), (0, 0), layer)

    m = g["mouth"]
    d = ImageDraw.Draw(img)
    if m["open"] > 0.5 * SMOOTH:
        d.polygon([*m["upper"], *reversed(m["lower"])], fill=col["mouth"])
    _thick_line(d, m["upper"], m["thick"], col["mouth"])
    return img.resize(size, Image.LANCZOS)


def preview(path, config=None):
    """Save every expression as one picture, to check the design."""
    config = config or load_config()
    names = list(config["expressions"])
    gap, cols = 16, 2
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (WIDTH + gap) + gap, rows * (HEIGHT + gap) + gap), "#6d5424")
    for i, name in enumerate(names):
        p = {side: params_for(config, name, side) for side in ("left", "right")}
        talking = 0.6 if name == "speaking" else 0.0
        sheet.paste(draw_face(p, config, level=talking),
                    (gap + (i % cols) * (WIDTH + gap), gap + (i // cols) * (HEIGHT + gap)))
    sheet.save(path)
    return names


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "preview":
        print("Drew:", ", ".join(preview(sys.argv[2])), "->", sys.argv[2])
    else:
        print("Usage: python -m bolt_body.face preview face.png")
