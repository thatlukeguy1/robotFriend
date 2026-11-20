"""
Bolt: an artist's impression of the finished robot (a hollow brass retro PC),
drawn from the SAME measurements as the bending template (make_template.py),
so if a size changes there, the picture changes too.

LESSON: Drawing 3D on flat paper
================================
Every part is a list of 3D points in millimetres:
    x = left/right,  y = up,  z = towards you (the front).
To draw it, we turn each point to face a pretend camera standing in front,
a bit to the right and a bit above (this is called a PROJECTION):

    across = how far right it looks       (dot product with the "right" arrow)
    up     = how far up it looks          (dot product with the "up" arrow)
    depth  = how close to the camera it is

Then we paint the furthest things first and the nearest last, like a
painter does, so near things cover far ones ("the painter's algorithm").

    python docs/frame/make_concept.py        (makes concept.svg)
    node docs/frame/render_concept.js        (makes concept.png)
"""

import base64
import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from make_template import (PARTS, TUBE, RADIUS, CLEARANCE, STOP_BAR, BEZEL, BEZEL_DEPTH, BACK,  # noqa: E402
                           TAPER_DEPTH, BACK_LIFT, CHIN, BASE_HEIGHT, CROSS_BARS_APART, FOOT, YOKE, head_sizes)

YAW, PITCH = math.radians(40), math.radians(19)   # camera: to the right, and above
SCALE = 3.3                                       # pixels per millimetre
W, H = 1400, 1000
ORIGIN = (W * 0.5, H * 0.84)                     # where (0, 0, 0) lands on the picture

RIGHT = (math.cos(YAW), 0, -math.sin(YAW))
UP = (-math.sin(YAW) * math.sin(PITCH), math.cos(PITCH), -math.cos(YAW) * math.sin(PITCH))
TOWARDS = (math.sin(YAW) * math.cos(PITCH), math.sin(PITCH), math.cos(YAW) * math.cos(PITCH))

BRASS, BRASS_DARK, BRASS_LIGHT = "#c99a2e", "#7a5a12", "#f3d98a"


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def flat(p):
    """3D point -> (x, y) on the picture."""
    return ORIGIN[0] + dot(p, RIGHT) * SCALE, ORIGIN[1] - dot(p, UP) * SCALE


def depth(points):
    return sum(dot(p, TOWARDS) for p in points) / len(points)


shapes = []  # (depth, svg) -- sorted before drawing


def tube(points, dia, closed=False, radius=0.0, nudge=0.0):
    """A brass tube along `points`, corners rounded. Each little piece is sorted on its own."""
    runs = rounded(points, radius, closed) if radius else [[a, b] for a, b in zip(points, points[1:])]
    w = dia * SCALE
    for run in runs:
        flat_pts = [flat(p) for p in run]
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in flat_pts)
        hi = "M" + " L".join(f"{x - w * 0.18:.1f},{y - w * 0.22:.1f}" for x, y in flat_pts)
        svg = (f'<path d="{d}" fill="none" stroke="{BRASS_DARK}" stroke-width="{w + 1.6:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'<path d="{d}" fill="none" stroke="{BRASS}" stroke-width="{w:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
               f'<path d="{hi}" fill="none" stroke="{BRASS_LIGHT}" stroke-width="{w * 0.28:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>')
        shapes.append((depth(run) + nudge, svg))


def rounded(points, r, closed):
    """Replace each corner with a little arc of radius r (in 3D).
    Returns RUNS: each bend, and each straight bit between bends, as its own list of points."""
    n = len(points)
    corners = []
    for i, p in enumerate(points):
        if not closed and i in (0, n - 1):
            corners.append([p])
            continue
        a, c = points[i - 1], points[(i + 1) % n]
        u = unit(sub(a, p))
        v = unit(sub(c, p))
        start, end = add(p, mul(u, r)), add(p, mul(v, r))
        arc = []
        for k in range(9):  # a quadratic curve through the corner looks like a bend
            t = k / 8
            q = add(add(mul(start, (1 - t) ** 2), mul(p, 2 * t * (1 - t))), mul(end, t * t))
            arc.append(q)
        corners.append(arc)
    runs = []
    for i, arc in enumerate(corners):
        if len(arc) > 1:
            runs.append(arc)
        if i + 1 < n or closed:
            nxt = corners[(i + 1) % n]
            runs.append([arc[-1], nxt[0]])
    return runs


def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def unit(a):
    n = math.sqrt(dot(a, a)) or 1
    return mul(a, 1 / n)


def poly(points, fill, stroke="none", nudge=0.0, extra=""):
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(flat, points))
    shapes.append((depth(points) + nudge, f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" stroke-width="1" stroke-linejoin="round" {extra}/>'))


def box(x0, y0, z0, x1, y1, z1, front, side, top, nudge=0.0):
    """A solid block: we only ever see its front, right side and top."""
    poly([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], front, "#00000055", nudge)
    poly([(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)], side, "#00000055", nudge)
    poly([(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)], top, "#00000055", nudge)


def rect_xy(x, y, w, h, z):
    return [(x, y, z), (x + w, y, z), (x + w, y + h, z), (x, y + h, z)]


def picture(img_path, corners, nudge=0.0):
    """Stick a flat image onto a flat rectangle (top-left, top-right, bottom-left corners)."""
    (ax, ay), (bx, by), (cx, cy) = (flat(p) for p in corners)
    data = base64.b64encode(Path(img_path).read_bytes()).decode()
    m = f"matrix({(bx - ax) / 320:.5f},{(by - ay) / 320:.5f},{(cx - ax) / 240:.5f},{(cy - ay) / 240:.5f},{ax:.2f},{ay:.2f})"
    shapes.append((depth(corners) + nudge,
                   f'<image href="data:image/png;base64,{data}" width="320" height="240" transform="{m}" preserveAspectRatio="none"/>'))



def wire(points, color, width, nudge=0.0, opacity=1.0, dash=""):
    """A cable: a smooth line through the points."""
    for a, b in zip(points, points[1:]):
        (x1, y1), (x2, y2) = flat(a), flat(b)
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        shapes.append((depth([a, b]) + nudge,
                       f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}" '
                       f'stroke-linecap="round" opacity="{opacity}"{extra}/>'))


def rect_xz(cx, cz, w, d, y):
    return [(cx - w / 2, y, cz - d / 2), (cx + w / 2, y, cz - d / 2), (cx + w / 2, y, cz + d / 2), (cx - w / 2, y, cz + d / 2)]


def corner_mids(cx, cy, w, h, z, r):
    """Where a strut meets a rounded ring: the middle of each bend."""
    k = r * (1 - math.cos(math.pi / 4))
    return {"tl": (cx - w / 2 + k, cy + h / 2 - k, z), "tr": (cx + w / 2 - k, cy + h / 2 - k, z),
            "bl": (cx - w / 2 + k, cy - h / 2 + k, z), "br": (cx + w / 2 - k, cy - h / 2 + k, z)}


hs = head_sizes()

# ===================================================================== the base: a hollow desktop case
tb, rb = TUBE["base"], RADIUS["base"]
bw, bd = PARTS["base_inside"][0] + tb, PARTS["base_inside"][1] + tb
hx, hz = bw / 2, bd / 2
for y in (0, BASE_HEIGHT):
    tube(rect_xz(0, 0, bw, bd, y), tb, True, rb)
k = rb * (1 - math.cos(math.pi / 4))
for sx in (-1, 1):
    for sz in (-1, 1):
        tube([(sx * (hx - k), 0, sz * (hz - k)), (sx * (hx - k), BASE_HEIGHT, sz * (hz - k))], tb)
for sx in (-1, 1):                                                                          # cross bars for the turntable
    tube([(sx * CROSS_BARS_APART / 2, BASE_HEIGHT, -hz), (sx * CROSS_BARS_APART / 2, BASE_HEIGHT, hz)], tb, nudge=-1)

# inside the case
box(-60, 4, -42, 25, 6, 14, "#1f6f3a", "#185a2f", "#2a8a4a")                                 # Pi 4 board, on standoffs
for x, z in ((-56, -38), (21, -38), (-56, 10), (21, 10)):
    box(x - 1.2, 0, z - 1.2, x + 1.2, 4, z + 1.2, "#e8e8e8", "#c8c8c8", "#ffffff")           # nylon standoffs
box(-60, 6, -42, -42, 22, -27, "#c9ced6", "#a8aeb8", "#e1e5ea")                               # USB and network sockets
box(-30, 6, -24, -4, 14, 2, "#24272e", "#1a1c21", "#30343c")                                  # fan
fan_c = (-17, 14.2, -11)
for i in range(6):
    a = i * math.pi / 3
    poly([fan_c, (fan_c[0] + 11 * math.cos(a), 14.2, fan_c[2] + 11 * math.sin(a)),
          (fan_c[0] + 11 * math.cos(a + 0.6), 14.2, fan_c[2] + 11 * math.sin(a + 0.6))], "#3b4049", nudge=0.5)
box(-50, 3, 30, 20, 34, 44, "#20242c", "#15181e", "#2b3039")                                  # speaker, facing forward
for i in range(8):
    for j in range(3):
        cx, cy = -45 + i * 8.5, 10 + j * 8
        poly([(cx - 2, cy - 2, 44.1), (cx + 2, cy - 2, 44.1), (cx + 2, cy + 2, 44.1), (cx - 2, cy + 2, 44.1)], "#0b0d10", nudge=0.5)
box(30, 3, 24, 48, 5, 42, "#5b2a86", "#48206b", "#7038a3")                                    # amp
box(32, 3, -42, 57, 5, 18, "#1e4fa3", "#173e80", "#2a62c4")                                   # servo board
for i, c in enumerate(("#8a5a2b", "#d62d20", "#f5a623")):                                     # servo wires
    wire([(-3 + i * 1.5, 26, -4), (20, 18, -10), (40, 6, -20 + i)], c, 2.2)
wire([(36, 5, 30), (18, 18, 38)], "#d62d20", 2.4); wire([(38, 5, 30), (18, 22, 38)], "#222", 2.4)   # speaker wires

# ===================================================================== the neck
bearing_y = BASE_HEIGHT + tb / 2
box(-25, bearing_y, -25, 25, bearing_y + 5, 25, "#b8bcc4", "#9aa0a8", "#d5d9df")             # turntable bearing
box(-11.5, BASE_HEIGHT - 26, -6, 11.5, BASE_HEIGHT - 3, 6, "#2f7fd8", "#2463ad", "#4a98ea")  # pan servo, under the bars
ts = TUBE["small"]
foot_y = bearing_y + 5 + ts / 2
tube([(FOOT / 2 * math.cos(a), foot_y, FOOT / 2 * math.sin(a)) for a in [i * math.pi / 18 for i in range(36)]], ts, True)
yw, yh = YOKE
yoke_y = foot_y + tb / 2
axle_y = yoke_y + yh
tube([(-yw / 2, axle_y, 0), (-yw / 2, yoke_y, 0), (yw / 2, yoke_y, 0), (yw / 2, axle_y, 0)], tb, False, rb)
box(yw / 2 + 3, axle_y - 22, -11.5, yw / 2 + 15, axle_y + 2, 11.5, "#2f7fd8", "#2463ad", "#4a98ea")  # tilt servo

# ===================================================================== the head: a hollow CRT
t, r = TUBE["head"], RADIUS["head"]
W_, H_ = BEZEL
axle_z = 0.0
zf = axle_z + (BEZEL_DEPTH + TAPER_DEPTH) * 0.3        # front ring: the axle is a third of the way back
zm = zf - BEZEL_DEPTH
zb = zm - TAPER_DEPTH
y0 = axle_y                                            # the head's floor rests on the axle
cy = y0 + H_ / 2
for z in (zf, zm):
    tube(rect_xy(-W_ / 2, y0, W_, H_, z), t, True, r)
kw, kh = BACK
bcy = y0 + BACK_LIFT + kh / 2
tube(rect_xy(-kw / 2, y0 + BACK_LIFT, kw, kh, zb), t, True, RADIUS["back"])
front_c, mid_c = corner_mids(0, cy, W_, H_, zf, r), corner_mids(0, cy, W_, H_, zm, r)
back_c = corner_mids(0, bcy, kw, kh, zb, RADIUS["back"])
for c in front_c:
    tube([front_c[c], mid_c[c]], t)
    tube([mid_c[c], back_c[c]], t)
tube([(-hs["axle"] / 2, y0, axle_z), (hs["axle"] / 2, y0, axle_z)], t)  # head axle

# screen ring, spokes, the screen and Bolt's face
rw, rh = hs["ring"]
ry = y0 + CHIN
tube(rect_xy(-rw / 2, ry, rw, rh, zf), t, True, r, nudge=2)
for sx in (-1, 1):
    tube([(sx * rw / 2, ry + rh / 2, zf), (sx * W_ / 2, ry + rh / 2, zf)], t, nudge=2)
    tube([(sx * rw * 0.22, y0, zf), (sx * rw * 0.22, ry, zf)], t, nudge=2)
sw, sh = PARTS["screen"]
left, right = PARTS["screen_glass"]
sy = ry + t / 2 + CLEARANCE
zs = zf + 1.5
box(-sw / 2, sy, zs - PARTS["screen_thick"], sw / 2, sy + sh, zs - 1.6, "#9e1b1b", "#8a1717", "#b3261e", nudge=-2)
poly(rect_xy(-sw / 2, sy, sw, sh, zs), "#b3261e", "#00000066", nudge=4)
gx0, gw = -sw / 2 + left, sw - left - right
poly(rect_xy(gx0, sy, gw, sh, zs + 0.3), "#05070c", "#333", nudge=8)
lit_w, lit_h = 58, 43.5
lx, ly = gx0 + (gw - lit_w) / 2, sy + (sh - lit_h) / 2
picture(HERE / "concept-face.png", [(lx, ly + lit_h, zs + 0.5), (lx + lit_w, ly + lit_h, zs + 0.5), (lx, ly, zs + 0.5)], nudge=20)
for bx in (-sw / 2 + left / 2, sw / 2 - right / 2):
    tube([(bx, ry, zf + 3.5), (bx, ry + rh, zf + 3.5)], STOP_BAR, nudge=30)

# webcam on top
cw, ch = PARTS["camera"]
uw, uh = cw + 2 * CLEARANCE + TUBE["small"], ch + CLEARANCE + TUBE["small"] / 2
top = y0 + H_ + t / 2 + TUBE["small"] / 2
tube([(-uw / 2, top + uh, zf), (-uw / 2, top, zf), (uw / 2, top, zf), (uw / 2, top + uh, zf)], TUBE["small"], False, RADIUS["small"], nudge=3)
poly(rect_xy(-cw / 2, top + 1.5, cw, ch, zf - 1), "#1f6f3a", "#00000066", nudge=2.5)
poly(rect_xy(-4.5, top + 1.5 + ch / 2 - 4.5, 9, 9, zf - 0.6), "#111", nudge=2.6)
poly([(2.6 * math.cos(a), top + 1.5 + ch / 2 + 2.6 * math.sin(a), zf - 0.4) for a in [i * math.pi / 8 for i in range(16)]], "#3a5a8a", nudge=2.7)
wire([(0, top + 2, zf - 2), (2, cy + 20, zm - 8), (6, cy - 10, zb + 14), (10, y0 + 6, -10), (14, foot_y + 2, -12),
      (12, BASE_HEIGHT - 6, -16), (-4, 8, -24)], "#e9e9e9", 5, nudge=-4)                       # camera ribbon
wire([(0, top + 2, zf - 2), (2, cy + 20, zm - 8), (6, cy - 10, zb + 14), (10, y0 + 6, -10), (14, foot_y + 2, -12),
      (12, BASE_HEIGHT - 6, -16), (-4, 8, -24)], "#9a9a9a", 5, nudge=-4.1, dash="1 3")

# the chin: microphone board and power light
poly(rect_xy(-rw * 0.22 - 14, y0 + 3, 13, 12, zf - 2), "#5b2a86", "#2e1545", nudge=1)
poly([(-rw * 0.22 - 7.5 + 1.6 * math.cos(a), y0 + 9 + 1.6 * math.sin(a), zf - 1.8) for a in [i * math.pi / 6 for i in range(12)]], "#c0c0c0", nudge=1.1)
poly([(rw * 0.22 + 8 + 1.8 * math.cos(a), y0 + 9 + 1.8 * math.sin(a), zf) for a in [i * math.pi / 6 for i in range(12)]], "#35d36a", "#1b7a3a", nudge=3, extra='filter="url(#glow)"')
# the head's wiring: a black braided bundle from the screen, mic and light, down the neck to the Pi
for dx, color in ((0, "#1b1b1b"), (1.2, "#3a3a3a")):
    wire([(-10 + dx, sy + 6, zs - 7.5), (-6 + dx, y0 + 4, zm - 6), (-14 + dx, foot_y + 4, -8), (-18 + dx, BASE_HEIGHT - 2, -14), (-30 + dx, 10, -30)],
         color, 6 if dx == 0 else 2, nudge=-3, dash="" if dx == 0 else "2 2")

# ===================================================================== labels
top_y = top + uh


def label(p3, text, dx, dy, anchor="start"):
    x, y = flat(p3)
    tx, ty = x + dx, y + dy
    return (f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{tx:.0f}" y2="{ty:.0f}" stroke="#4b5563" stroke-width="1.2"/>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3" fill="#4b5563"/>'
            f'<text x="{tx + (6 if anchor == "start" else -6):.0f}" y="{ty + 5:.0f}" class="lab" text-anchor="{anchor}">{text}</text>')


labels = [
    label((-6, top + 1.5 + ch / 2, zf - 0.4), "webcam on top: notices your mood", -330, -40, "end"),
    label((-10, ly + lit_h * 0.7, zs + 0.5), "2.8&quot; screen in its own ring", -330, -30, "end"),
    label((-rw * 0.22 - 7.5, y0 + 9, zf - 1.8), "mic on the chin", -300, 30, "end"),
    label((rw * 0.22 + 8, y0 + 9, zf), "power light", 420, -40),
    label((kw / 2 - 2, bcy, zb), "tapered CRT back", 240, -60),
    label((W_ / 2, cy + 20, zm), "bezel rings", 300, -190),
    label((yw / 2 + 15, axle_y - 10, 0), "tilt servo turns the head axle", 320, -10),
    label((FOOT / 2, foot_y, 0), "swivel foot on a turntable bearing", 330, 60),
    label((-6, BASE_HEIGHT - 14, 6), "pan servo, under the bars", -400, -40, "end"),
    label((-30, 20, 44), "speaker, facing forward", -300, 50, "end"),
    label((18, 6, -4), "Raspberry Pi 4 with fan", 300, 75),
    label((45, 5, -30), "servo board + amp", 330, -10),
]
size_note = f"About {top_y / 10:.0f} cm tall · {bw / 10 + tb / 10:.0f} cm wide · {bd / 10 + tb / 10:.0f} cm deep"

shapes.sort(key=lambda s: s[0])
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
  <radialGradient id="bg" cx="50%" cy="45%" r="70%"><stop offset="0" stop-color="#fbfaf7"/><stop offset="1" stop-color="#e6e1d6"/></radialGradient>
  <filter id="glow" x="-1" y="-1" width="3" height="3"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <style>
    .title {{ font: 700 34px system-ui, sans-serif; fill: #1f2328; }}
    .sub {{ font: 18px system-ui, sans-serif; fill: #57606a; }}
    .lab {{ font: 600 17px system-ui, sans-serif; fill: #1f2328; }}
  </style>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<ellipse cx="{flat((0, 0, 0))[0]:.0f}" cy="{flat((0, 0, 0))[1] + 6:.0f}" rx="{bw * SCALE * 0.66:.0f}" ry="{bd * SCALE * 0.26:.0f}" fill="#00000018"/>
<text x="40" y="58" class="title">Bolt: a hollow brass retro PC</text>
<text x="40" y="88" class="sub">Artist's impression, drawn from the frame template's real measurements · {size_note}</text>
{''.join(s for _, s in shapes)}
{''.join(labels)}
<text x="40" y="{H - 28}" class="sub">No panels: every part and wire is on show, so keep the wiring neat (braided sleeving, cable ties, nylon standoffs).</text>
</svg>
"""
(HERE / "concept.svg").write_text(svg)
print("Wrote", HERE / "concept.svg")
