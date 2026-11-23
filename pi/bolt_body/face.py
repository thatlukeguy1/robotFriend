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
import ssl
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

EXPRESSIONS = Path(__file__).resolve().parents[2] / "web" / "expressions.json"
STICKERS = Path(__file__).resolve().parents[2] / "web" / "stickers"
WIDTH, HEIGHT = 320, 240   # the ILI9341 screen
HAND_LIFT = 0.055         # the face lifts this much (of the height) when the hand is up
ZZZ_SECONDS = 3            # how long one sleepy Z takes to float away (same as face.js)
HAT_DROP = 0.03            # with the Christmas hat on, the face sits this much lower to make room
SMOOTH = 3                 # draw 3x bigger, then shrink: smooth edges (anti-aliasing)


def load_config(path=EXPRESSIONS, brain_url=None, ca=None):
    """The latest face design: from the brain if possible, otherwise the original file.
    `ca`: Bolt's certificate-authority stamp, to check it's really Bolt over HTTPS."""
    if brain_url:
        try:
            context = ssl.create_default_context(cafile=ca) if ca else None
            with urllib.request.urlopen(brain_url.rstrip("/") + "/static/expressions.json", timeout=5,
                                        context=context) as r:
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


def load_stickers(folder=STICKERS):
    """The sticker pictures and where they go (see web/stickers/make_stickers.js). Empty if missing."""
    try:
        places = json.loads((Path(folder) / "stickers.json").read_text())
        return {name: {**place, "image": Image.open(Path(folder) / place["file"]).convert("RGBA")}
                for name, place in places.items() if not name.startswith("_")}
    except (OSError, ValueError, KeyError) as e:
        print(f"   (no stickers: {e})", flush=True)
        return {}


def place_stickers(W, H, places, amounts, mouth, bob, time):
    """Where each sticker goes right now: the same maths as placeStickers() in face.js.
    amounts: how far each one is on (0 = gone, 1 = fully there)."""
    out = []
    for name, s in places.items():
        a = max(0.0, min(1.0, amounts.get(name, 0.0)))
        if a <= 0.01:
            continue
        if s.get("at") == "mouth":
            x, y = mouth[0] + s["x"] * W, mouth[1] + s["y"] * H
        else:
            x, y = s["x"] * W, s["y"] * H - bob * H
        y += (1 - a) * 0.3 * H * (-1 if s.get("enter") == "down" else 1)   # slides in as it appears
        angle = s.get("angle", 0) + s.get("sway", 0) * math.sin(time * 1.6)
        out.append({"name": name, "x": x, "y": y, "width": s["width"] * W, "anchor": s["anchor"],
                    "angle": angle, "alpha": a, "tint": s.get("tint")})
    return out


def geometry(W, H, p, face, blink, bob=0.0, level=0.0, time=0.0, hat=0.0, stickers=None):
    """Exactly the same maths as geometry() in web/face.js."""
    shapes = {"eyes": {}, "brows": {}}
    hand = max(0.0, min(1.0, (p["left"].get("hand", 0.0) + p["right"].get("hand", 0.0)) / 2))
    hat = max(0.0, min(1.0, hat))
    hat_bob = bob
    bob = bob + HAND_LIFT * hand - HAT_DROP * hat   # chin on her hand lifts the face; the hat pushes it down
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
        return (p["left"].get(k, 0.0) + p["right"].get(k, 0.0)) / 2

    mx, my = W / 2, face["mouthY"] * H - bob * H
    half = (face["mouthWidth"] * W / 2) * avg("mouthWidth")
    bend = avg("mouthSmile") * 0.07 * H
    opening = min(1, avg("mouthOpen") + level * 0.9) * 0.1 * H
    shapes["mouth"] = {
        "upper": curve(mx - half, my, mx, my + bend, mx + half, my),
        "lower": curve(mx - half, my, mx, my + bend + opening * 2, mx + half, my),
        "open": opening, "thick": 0.03 * H,
    }

    # Stickers: pictures placed on the face (the thinking hand, the Christmas hat)
    shapes["stickers"] = place_stickers(W, H, stickers or {}, {"hand": hand, "hat": hat}, (mx, my), hat_bob, time)
    shapes["hat"] = hat > 0.01

    # Sleepy Zs: the same as face.js. Three drift up from the right eye, growing and fading.
    zzz = max(0.0, min(1.0, avg("zzz")))
    shapes["zzz"] = []
    if zzz > 0.01:
        # Beside the right eye, or the LEFT one when the Christmas hat's pom-pom is in the way
        side, away = ("left", -1) if shapes["hat"] else ("right", 1)
        eye = shapes["eyes"][side]["box"]
        x0, y0 = eye["x"] + eye["w"] * (0.5 + 0.45 * away), eye["y"] + eye["h"] * 0.4   # beside the (closed) eye
        for i in range(3):
            phase = ((time / ZZZ_SECONDS) + i / 3) % 1
            size = H * (0.045 + 0.05 * phase)
            shapes["zzz"].append({"x": x0 + away * phase * 0.09 * W, "y": max(size, y0 - phase * 0.3 * H), "size": size,
                                  "alpha": zzz * math.sin(math.pi * phase), "thick": size * 0.2})
    return shapes


def _mix(a, b, amount):
    """A colour `amount` of the way from a to b (both like #33c6ff). Like see-through paint."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return tuple(round(x + (y - x) * amount) for x, y in zip(ca, cb))


def _thick_line(d, pts, width, fill):
    """A line with round ends (Pillow's lines have flat ends)."""
    d.line(pts, fill=fill, width=max(1, round(width)), joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


_sized = {}   # sticker pictures already shrunk and coloured, so each frame only has to tilt them


def _stamp(img, picture, st, col):
    """Shrink (and colour) a sticker, tilt it, fade it, and paste it with its anchor at (x, y)."""
    width = max(1, round(st["width"]))
    tint = col.get(st["tint"]) if st["tint"] else None
    key = (id(picture), width, tint)
    if key not in _sized:
        small = picture.resize((width, max(1, round(picture.height * width / picture.width))), Image.LANCZOS)
        if tint:   # LESSON: colouring a grey drawing = multiplying: white becomes the colour, grey a darker shade
            rgb = ImageChops.multiply(small.convert("RGB"), Image.new("RGB", small.size, tint))
            rgb.putalpha(small.getchannel("A"))
            small = rgb
        if len(_sized) > 80:
            _sized.clear()
        _sized[key] = small
    small = _sized[key]
    ax, ay = st["anchor"][0] * small.width, st["anchor"][1] * small.height
    # Tilting is the slow part, so each tilt (to the nearest half degree) is kept and reused
    angle = round(st["angle"] * 2) / 2
    turn_key = key + (angle,)
    if turn_key not in _sized:
        _sized[turn_key] = small.rotate(-angle, resample=Image.BICUBIC, expand=True)   # turns about its middle
    turned = _sized[turn_key]
    st = {**st, "angle": angle}
    # Where the anchor ended up after turning (rotate(expand=True) grows the picture to fit)
    r = math.radians(st["angle"])
    cx, cy = small.width / 2, small.height / 2
    dx, dy = ax - cx, ay - cy
    tx = cx + dx * math.cos(r) - dy * math.sin(r) + (turned.width - small.width) / 2
    ty = cy + dx * math.sin(r) + dy * math.cos(r) + (turned.height - small.height) / 2
    if st["alpha"] < 0.99:   # fading in or out: a see-through copy (only while it slides on or off)
        turned = turned.copy()
        turned.putalpha(turned.getchannel("A").point(lambda v: round(v * st["alpha"])))
    img.paste(turned, (round(st["x"] - tx), round(st["y"] - ty)), turned)


def draw_face(p, config, blink=None, bob=0.0, level=0.0, size=(WIDTH, HEIGHT), smooth=SMOOTH, time=0.0, hat=0.0,
              stickers=None):
    """Draw the whole face and return it as a picture. p: {"left": settings, "right": settings}.
    smooth: how many times bigger to draw before shrinking (3 = smoothest, 2 = faster, for animation)."""
    blink = blink or {"left": 0.0, "right": 0.0}
    W, H = size[0] * smooth, size[1] * smooth
    col = config["colors"]
    stickers = STICKER_SET if stickers is None else stickers
    g = geometry(W, H, p, config["face"], blink, bob, level, time, hat, stickers)
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
    if m["open"] > 0.5 * smooth:
        d.polygon([*m["upper"], *reversed(m["lower"])], fill=col["mouth"])
    _thick_line(d, m["upper"], m["thick"], col["mouth"])

    for z in g["zzz"]:                       # sleepy Zs: three strokes each, faded towards the background
        h = z["size"] / 2
        _thick_line(d, [(z["x"] - h, z["y"] - h), (z["x"] + h, z["y"] - h), (z["x"] - h, z["y"] + h), (z["x"] + h, z["y"] + h)],
                    z["thick"], _mix(col["background"], col["mouth"], z["alpha"]))

    for st in g["stickers"]:                 # stickers on top of everything
        _stamp(img, stickers[st["name"]]["image"], st, col)
    return img.resize(size, Image.BILINEAR if smooth <= 2 else Image.LANCZOS)


STICKER_SET = load_stickers()


def preview(path, config=None, hat=0.0):
    """Save every expression as one picture, to check the design."""
    config = config or load_config()
    names = list(config["expressions"])
    gap, cols = 16, 2
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (WIDTH + gap) + gap, rows * (HEIGHT + gap) + gap), "#6d5424")
    for i, name in enumerate(names):
        p = {side: params_for(config, name, side) for side in ("left", "right")}
        talking = 0.6 if name == "speaking" else 0.0
        sheet.paste(draw_face(p, config, level=talking, time=1.2, hat=hat),
                    (gap + (i % cols) * (WIDTH + gap), gap + (i // cols) * (HEIGHT + gap)))
    sheet.save(path)
    return names


if __name__ == "__main__":
    if len(sys.argv) in (3, 4) and sys.argv[1] == "preview":   # add "hat" for the Christmas hat
        print("Drew:", ", ".join(preview(sys.argv[2], hat=1.0 if sys.argv[3:] == ["hat"] else 0.0)), "->", sys.argv[2])
    else:
        print("Usage: python -m bolt_body.face preview face.png")
