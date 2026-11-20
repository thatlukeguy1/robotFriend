"""
Bolt: an artist's impression of the finished robot, drawn from the SAME
measurements as the bending template (make_template.py), so if a size
changes there, the picture changes too.

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
from make_template import PARTS, TUBE, RADIUS, CLEARANCE, HEAD_DEPTH, BASE_FRONT, BASE_BACK, YOKE, STOP_BAR  # noqa: E402

YAW, PITCH = math.radians(32), math.radians(16)   # camera: to the right, and above
SCALE = 3.4                                       # pixels per millimetre
W, H = 1400, 1000
ORIGIN = (W * 0.5, H * 0.80)                     # where (0, 0, 0) lands on the picture

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


# ===================================================================== the base
tb = TUBE["base"]
bw, bd = PARTS["base_inside"][0] + tb, PARTS["base_inside"][1] + tb
hx, hz = bw / 2, bd / 2
tube([(-hx, 0, -hz), (hx, 0, -hz), (hx, 0, hz), (-hx, 0, hz)], tb, True, RADIUS["base"])         # ③ bottom
for sx in (-hx, hx):                                                                              # ④ sides (wedge)
    tube([(sx, 0, hz), (sx, BASE_FRONT, hz), (sx, BASE_BACK, -hz), (sx, 0, -hz)], tb, False, RADIUS["base"])
tube([(-hx, BASE_FRONT, hz), (hx, BASE_FRONT, hz)], tb)                                           # top bars
tube([(-hx, BASE_BACK, -hz), (hx, BASE_BACK, -hz)], tb)

# what lives inside the base
box(-hx + 8, 4, -hz + 6, -hx + 8 + 85, 6, -hz + 6 + 56, "#1f6f3a", "#185a2f", "#2a8a4a")            # Pi 4 board
box(-hx + 20, 6, -hz + 12, -hx + 20 + 18, 20, -hz + 12 + 14, "#c9ced6", "#a8aeb8", "#e1e5ea")     # USB/ethernet block
box(-hx + 12, 6, -hz + 46, -hx + 12 + 10, 9, -hz + 46 + 10, "#222", "#111", "#333")               # fan (on the Pi)
box(-35, 4, hz - 34, 35, 35, hz - 3, "#20242c", "#15181e", "#2b3039")                             # speaker box, facing forward
for i in range(9):                                                                                # speaker grille holes
    for j in range(3):
        cx, cy = -28 + i * 7, 11 + j * 8
        poly([(cx - 1.6, cy - 1.6, hz - 2.9), (cx + 1.6, cy - 1.6, hz - 2.9), (cx + 1.6, cy + 1.6, hz - 2.9), (cx - 1.6, cy + 1.6, hz - 2.9)], "#0b0d10", nudge=0.5)
box(hx - 30, 4, -hz + 20, hx - 8, 6, -hz + 20 + 18, "#5b2a86", "#48206b", "#7038a3")              # amp
box(hx - 30, 4, -hz + 44, hx - 8, 6, -hz + 44 + 25, "#1e4fa3", "#173e80", "#2a62c4")              # servo board

# a plate across the sloping top for the neck
slope_mid_y = (BASE_FRONT + BASE_BACK) / 2
poly([(-20, BASE_FRONT + 1.5, hz), (20, BASE_FRONT + 1.5, hz), (20, BASE_BACK + 1.5, -hz), (-20, BASE_BACK + 1.5, -hz)],
     "#8d6b1f", "#5e4712", nudge=-2)

# ===================================================================== the neck
pan_top = slope_mid_y + 1.5 + 23
box(-11.5, slope_mid_y + 1.5, -6, 11.5, pan_top, 6, "#2f7fd8", "#2463ad", "#4a98ea")              # pan servo (SG90)
box(-3, pan_top, -3, 3, pan_top + 3, 3, "#eeeeee", "#cccccc", "#ffffff")                           # servo horn
yw, yh = YOKE
yoke_base = pan_top + 4
tube([(-yw / 2, yoke_base + yh, 0), (-yw / 2, yoke_base, 0), (yw / 2, yoke_base, 0), (yw / 2, yoke_base + yh, 0)],
     tb, False, RADIUS["base"])                                                                     # ⑤ yoke
pivot_y = yoke_base + yh
box(yw / 2 + 2.5, pivot_y - 20, -11.5, yw / 2 + 2.5 + 12, pivot_y + 3, 11.5, "#2f7fd8", "#2463ad", "#4a98ea")  # tilt servo, beside the yoke arm

# ===================================================================== the head
t = TUBE["head"]
sw, sh = PARTS["screen"]
fw, fh = sw + 2 * CLEARANCE + t, sh + 2 * CLEARANCE + t
head_bottom = pivot_y + 7
cy = head_bottom + fh / 2
zf, zb = HEAD_DEPTH / 2, -HEAD_DEPTH / 2
tube([(-yw / 2, pivot_y, 0), (-yw / 2, head_bottom - t / 2, 0)], t)                               # head mounts
tube([(yw / 2, pivot_y, 0), (yw / 2, head_bottom - t / 2, 0)], t)
tube([(-yw / 2, head_bottom - t / 2, 0), (yw / 2, head_bottom - t / 2, 0)], t)
for z in (zb, zf):                                                                                 # ① front and back frames
    tube([(-fw / 2, cy - fh / 2, z), (fw / 2, cy - fh / 2, z), (fw / 2, cy + fh / 2, z), (-fw / 2, cy + fh / 2, z)],
         t, True, RADIUS["head"])
for x in (-fw / 2 + RADIUS["head"] + 4, fw / 2 - RADIUS["head"] - 4):                              # struts
    for y in (cy - fh / 2, cy + fh / 2):
        tube([(x, y, zb), (x, y, zf)], t)

# the screen board, its glass, and Bolt's face on it
left, right = PARTS["screen_glass"]
zs = zf - 1.5
poly(rect_xy(-sw / 2, cy - sh / 2, sw, sh, zs - PARTS["screen_thick"] + 1.5), "#9e1b1b", nudge=-1)
poly(rect_xy(-sw / 2, cy - sh / 2, sw, sh, zs), "#b3261e", "#00000066")                             # red PCB
gx0 = -sw / 2 + left
gw = sw - left - right
poly(rect_xy(gx0, cy - sh / 2, gw, sh, zs + 0.3), "#05070c", "#333", nudge=5)                    # glass
lit_w, lit_h = 58, 43.5                                                                            # the lit-up part
lx, ly = gx0 + (gw - lit_w) / 2, cy - lit_h / 2
picture(HERE / "concept-face.png", [(lx, ly + lit_h, zs + 0.5), (lx + lit_w, ly + lit_h, zs + 0.5), (lx, ly, zs + 0.5)], nudge=20)
for bx in (-sw / 2 + left / 2, sw / 2 - right / 2):                                                # stop bars
    tube([(bx, cy - fh / 2, zf + 2.5), (bx, cy + fh / 2, zf + 2.5)], STOP_BAR, nudge=25)

# camera, hanging under the front frame
ts = TUBE["small"]
cw, ch = PARTS["camera"]
uw = cw + 2 * CLEARANCE + ts
cam_top = cy - fh / 2
tube([(-uw / 2, cam_top, zf), (-uw / 2, cam_top - ch - 2, zf), (uw / 2, cam_top - ch - 2, zf), (uw / 2, cam_top, zf)],
     ts, False, RADIUS["small"], nudge=1)
poly(rect_xy(-cw / 2, cam_top - ch - 1, cw, ch, zf - 1), "#1f6f3a", "#00000066", nudge=1.5)       # camera board
poly([(-4.5, cam_top - ch / 2 - 5.5, zf + 0.2), (4.5, cam_top - ch / 2 - 5.5, zf + 0.2), (4.5, cam_top - ch / 2 + 3.5, zf + 0.2), (-4.5, cam_top - ch / 2 + 3.5, zf + 0.2)], "#111", nudge=1.6)
lens = [(-2.2 + 2.2 * math.cos(a), cam_top - ch / 2 - 1 + 2.2 * math.sin(a), zf + 0.4) for a in [k * math.pi / 8 for k in range(16)]]
poly([(x + 2.2, y, z) for x, y, z in lens], "#3a5a8a", nudge=1.7)

# microphone, on the head's top
box(-7, cy + fh / 2 + t / 2, -7, 7, cy + fh / 2 + t / 2 + 1.6, 7, "#5b2a86", "#48206b", "#7038a3", nudge=2)
poly([(-1.5, cy + fh / 2 + t / 2 + 1.7, -1.5), (1.5, cy + fh / 2 + t / 2 + 1.7, -1.5), (1.5, cy + fh / 2 + t / 2 + 1.7, 1.5), (-1.5, cy + fh / 2 + t / 2 + 1.7, 1.5)], "#c0c0c0", nudge=2.5)

# a wire bundle from head to base (behind the neck)
wire = [(8, head_bottom, zb + 3), (14, pivot_y - 10, -12), (12, pan_top - 5, -14), (8, slope_mid_y + 4, -18)]
for a, b in zip(wire, wire[1:]):
    (x1, y1), (x2, y2) = flat(a), flat(b)
    shapes.append((depth([a, b]) - 3, f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#333" stroke-width="5" stroke-linecap="round" opacity="0.9"/>'))

# ===================================================================== labels
top_y = cy + fh / 2 + t / 2 + 2


def label(p3, text, dx, dy, anchor="start"):
    x, y = flat(p3)
    tx, ty = x + dx, y + dy
    return (f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{tx:.0f}" y2="{ty:.0f}" stroke="#4b5563" stroke-width="1.2"/>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3" fill="#4b5563"/>'
            f'<text x="{tx + (6 if anchor == "start" else -6):.0f}" y="{ty + 5:.0f}" class="lab" text-anchor="{anchor}">{text}</text>')


labels = [
    label((0, cy + 12, zs + 0.6), "2.8&quot; screen: Bolt's face", -300, -170, "end"),
    label((0, top_y, 0), "microphone (INMP441)", 150, -70),
    label((0, cam_top - ch / 2, zf + 0.5), "camera: notices your mood", -300, -10, "end"),
    label((sw / 2 - right / 2, cy - 10, zf + 2.5), "stop bars hold the screen", 230, -40),
    label((yw / 2 + 14.5, pivot_y - 8, 0), "tilt servo: nods", 190, 20),
    label((11.5, pan_top - 8, 6), "pan servo: turns to follow you", 220, 40),
    label((0, 22, hz - 2.5), "speaker, facing forward", -300, 60, "end"),
    label((-hx + 4, 5, -hz + 30), "Raspberry Pi 4 (the brain's body)", -150, 120, "end"),
    label((hx - 19, 6, -hz + 56), "amp + servo board", 170, 110),
    label((hx, BASE_FRONT * 0.6, hz * 0.2), "brass tube frame (your template)", 190, -40),
]

# overall size
height = top_y
size_note = f"About {height / 10:.0f} cm tall · {bw / 10 + tb / 10:.0f} cm wide · {bd / 10 + tb / 10:.0f} cm deep"

shapes.sort(key=lambda s: s[0])
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
  <radialGradient id="bg" cx="50%" cy="45%" r="70%"><stop offset="0" stop-color="#fbfaf7"/><stop offset="1" stop-color="#e9e5dc"/></radialGradient>
  <style>
    .title {{ font: 700 34px system-ui, sans-serif; fill: #1f2328; }}
    .sub {{ font: 18px system-ui, sans-serif; fill: #57606a; }}
    .lab {{ font: 600 17px system-ui, sans-serif; fill: #1f2328; }}
  </style>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<ellipse cx="{flat((0, 0, 0))[0]:.0f}" cy="{flat((0, 0, 0))[1] + 8:.0f}" rx="{bw * SCALE * 0.62:.0f}" ry="{bd * SCALE * 0.22:.0f}" fill="#00000018"/>
<text x="40" y="58" class="title">Bolt: how the finished robot could look</text>
<text x="40" y="88" class="sub">Artist's impression, drawn from the frame template's real measurements · {size_note}</text>
{''.join(s for _, s in shapes)}
{''.join(labels)}
<text x="40" y="{H - 28}" class="sub">Open brass frame shown without panels, so you can see where every part goes. Wires mostly left out.</text>
</svg>
"""
(HERE / "concept.svg").write_text(svg)
print("Wrote", HERE / "concept.svg")
