"""
Riley, rendered: a realistic picture of the finished robot
===========================================================
The bending template (make_template.py) is flat drawings; the concept (make_concept.py) is
a quick sketch. This one describes the WHOLE robot in 3D, from the template's real
measurements and base layout, and a real 3D engine (three.js, in a browser) renders it with
proper materials: polished brass that reflects the room, glossy circuit boards, clear
acrylic, soft shadows on a wooden desk.

    python docs/frame/make_render.py         (writes render-scene.json: every part, in 3D)
    node docs/frame/render_realistic.js      (renders render.png from it)

LESSON: a 3D scene is just a list of simple shapes, each with a MATERIAL saying how light
treats it. Brass is a metal (it reflects, tinted gold); a circuit board is a "dielectric"
(a coloured surface with a thin glossy coat). The renderer works out every pixel from the
lights and the room reflected in the brass.

Coordinates in millimetres: x = right, y = up, z = towards the front. y = 0 is the centre
line of the bottom base ring; the desk is just under it.
"""

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from make_template import (BACK, BACK_LIFT, BASE_HEIGHT, BASE_LAYOUT, BEZEL, BEZEL_DEPTH, CAMERA_STANDOFF,  # noqa: E402
                           CHIN, CLEARANCE, CROSS_BARS_APART, FOOT, NUT, PARTS, PLATE_TOP, RADIUS, TAPER_DEPTH,
                           TOUCH_BAR, TUBE, YOKE, head_sizes)

scene = {"tubes": [], "boxes": [], "cyls": [], "images": [], "wires": [], "plates": [], "hexes": []}


# ------------------------------------------------------------------ shapes
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def unit(a):
    n = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2) or 1
    return mul(a, 1 / n)


def bent(points, r, closed):
    """The tube's centre line with each corner bent round radius r (a smooth arc)."""
    if not r:
        return list(points) + ([points[0]] if closed else [])
    n, out = len(points), []
    for i, p in enumerate(points):
        if not closed and i in (0, n - 1):
            out.append(p)
            continue
        a, c = points[i - 1], points[(i + 1) % n]
        u, v = unit(sub(a, p)), unit(sub(c, p))
        start, end = add(p, mul(u, r)), add(p, mul(v, r))
        for k in range(13):
            t = k / 12
            out.append(add(add(mul(start, (1 - t) ** 2), mul(p, 2 * t * (1 - t))), mul(end, t * t)))
    if closed:
        out.append(out[0])
    return out


def tube(points, dia, closed=False, r=0.0, mat="brass"):
    scene["tubes"].append({"pts": [list(map(lambda q: round(q, 3), p)) for p in bent(points, r, closed)],
                           "r": dia / 2, "mat": mat})


def box(x0, y0, z0, x1, y1, z1, mat, color=None):
    scene["boxes"].append({"min": [min(x0, x1), min(y0, y1), min(z0, z1)], "max": [max(x0, x1), max(y0, y1), max(z0, z1)],
                           "mat": mat, **({"color": color} if color else {})})


def cyl(a, b, r, mat, color=None, segments=24):
    scene["cyls"].append({"a": list(a), "b": list(b), "r": r, "mat": mat, "seg": segments, **({"color": color} if color else {})})


def wire(points, dia, color, mat="wire"):
    scene["wires"].append({"pts": [list(p) for p in points], "r": dia / 2, "color": color, "mat": mat})


def image(src, centre, w, h, normal_z=1):
    scene["images"].append({"src": src, "c": list(centre), "w": w, "h": h})


def rect_xy(x, y, w, h, z):
    return [(x, y, z), (x + w, y, z), (x + w, y + h, z), (x, y + h, z)]


def rect_xz(cx, cz, w, d, y):
    return [(cx - w / 2, y, cz - d / 2), (cx + w / 2, y, cz - d / 2), (cx + w / 2, y, cz + d / 2), (cx - w / 2, y, cz + d / 2)]


def corner_mid(cx, cy, w, h, z, r, which):
    k = r * (1 - math.cos(math.pi / 4))
    sx, sy = (-1 if "l" in which else 1), (1 if "t" in which else -1)
    return (cx + sx * (w / 2 - k), cy + sy * (h / 2 - k), z)


hs = head_sizes()

# ================================================================== the base
tb, rb = TUBE["base"], RADIUS["base"]
iw, idp = PARTS["base_inside"]
bw, bd = iw + tb, idp + tb
for y in (0, BASE_HEIGHT):
    tube(rect_xz(0, 0, bw, bd, y), tb, True, rb)
k = rb * (1 - math.cos(math.pi / 4))
for sx in (-1, 1):
    for sz in (-1, 1):
        tube([(sx * (bw / 2 - k), 0, sz * (bd / 2 - k)), (sx * (bw / 2 - k), BASE_HEIGHT, sz * (bd / 2 - k))], tb)
for sx in (-1, 1):
    tube([(sx * CROSS_BARS_APART / 2, BASE_HEIGHT, -bd / 2), (sx * CROSS_BARS_APART / 2, BASE_HEIGHT, bd / 2)], tb)

# the clear floor plate, lying on the bottom ring
corner = rb - tb / 2
pts = []
for cxs, czs, a0 in ((iw / 2 - corner, idp / 2 - corner, 0), (-(iw / 2 - corner), idp / 2 - corner, 90),
                     (-(iw / 2 - corner), -(idp / 2 - corner), 180), (iw / 2 - corner, -(idp / 2 - corner), 270)):
    for i in range(9):
        a = math.radians(a0 + i * 90 / 8)
        pts.append([cxs + corner * math.cos(a) + 1.5 * math.cos(a), czs + corner * math.sin(a) + 1.5 * math.sin(a)])
scene["plates"].append({"shape": pts, "y0": tb / 2, "y1": PLATE_TOP, "mat": "acrylic"})


def plan(x, y):
    """Base layout position (from the back-left inside corner) -> 3D x, z."""
    return -iw / 2 + x, -idp / 2 + y


def layout_box(name, mat, color=None, y0=None, y1=None):
    x, y, w, d, z0, z1, _ = BASE_LAYOUT[name]
    (ax, az), (bx_, bz) = plan(x, y), plan(x + w, y + d)
    box(ax, z0 if y0 is None else y0, az, bx_, z1 if y1 is None else y1, bz, mat, color)
    return ax, az, bx_, bz


def standoffs(ax, az, bx_, bz, inset, top):
    for x in (ax + inset, bx_ - inset):
        for z in (az + inset, bz - inset):
            cyl((x, PLATE_TOP, z), (x, top, z), 1.9, "nylon", segments=6)


# the Raspberry Pi 4
ax, az, bx_, bz = layout_box("pi", "pcb", "#1f7a3c", y1=BASE_LAYOUT["pi"][4] + 1.6)
standoffs(ax, az, bx_, bz, 3.5, BASE_LAYOUT["pi"][4])
board_top = BASE_LAYOUT["pi"][4] + 1.6
px0, pz0, px1, pz1 = plan(*BASE_LAYOUT["pi_ports"][:2]) + plan(BASE_LAYOUT["pi_ports"][0] + BASE_LAYOUT["pi_ports"][2],
                                                              BASE_LAYOUT["pi_ports"][1] + BASE_LAYOUT["pi_ports"][3])
# network socket and two double USB sockets along the left edge
for (z0, z1, h) in ((pz0 + 1, pz0 + 17, 13.5), (pz0 + 20, pz0 + 34, 16), (pz0 + 38, pz0 + 52, 16)):
    box(px0 - 1.5, board_top, z0, px0 + 21, board_top + h, z1, "steel")
    box(px0 - 1.6, board_top + 3, z0 + 2, px0 - 1.4, board_top + h - 3, z1 - 2, "plastic", "#202020")
gx, gz, gx1, gz1 = plan(*BASE_LAYOUT["pi_pins"][:2]) + plan(BASE_LAYOUT["pi_pins"][0] + BASE_LAYOUT["pi_pins"][2],
                                                           BASE_LAYOUT["pi_pins"][1] + BASE_LAYOUT["pi_pins"][3])
box(gx, board_top, gz + 0.5, gx1, board_top + 2.5, gz1 - 0.5, "plastic", "#151515")
for i in range(20):
    for j in range(2):
        cyl((gx + 1.3 + i * 2.54, board_top + 2.5, gz + 1.8 + j * 2.54), (gx + 1.3 + i * 2.54, board_top + 8.5, gz + 1.8 + j * 2.54),
            0.32, "gold", segments=4)
fx, fz, fx1, fz1 = plan(*BASE_LAYOUT["pi_fan"][:2]) + plan(BASE_LAYOUT["pi_fan"][0] + BASE_LAYOUT["pi_fan"][2],
                                                          BASE_LAYOUT["pi_fan"][1] + BASE_LAYOUT["pi_fan"][3])
box(fx, board_top + 1.5, fz, fx1, board_top + 11, fz1, "plastic", "#1c1d21")
cyl(((fx + fx1) / 2, board_top + 11, (fz + fz1) / 2), ((fx + fx1) / 2, board_top + 11.4, (fz + fz1) / 2), 9.5, "plastic", "#2c2e34", 32)
cyl(((fx + fx1) / 2, board_top + 11.4, (fz + fz1) / 2), ((fx + fx1) / 2, board_top + 11.8, (fz + fz1) / 2), 3.5, "plastic", "#111", 24)
ux, uz, ux1, uz1 = plan(*BASE_LAYOUT["pi_power"][:2]) + plan(BASE_LAYOUT["pi_power"][0] + BASE_LAYOUT["pi_power"][2],
                                                            BASE_LAYOUT["pi_power"][1] + BASE_LAYOUT["pi_power"][3])
box(ux + 1, board_top, uz - 3, ux1 - 1, board_top + 12, uz1, "plastic", "#e8e8e8")   # right-angle USB-C plug, pointing up
wire([((ux + ux1) / 2, board_top + 12, (uz + uz1) / 2), ((ux + ux1) / 2, board_top + 20, (uz + uz1) / 2 + 2),
      ((ux + ux1) / 2 + 12, BASE_HEIGHT - 6, -6), (bw / 2 - 8, 14, -bd / 2 + 8)], 3.2, "#f0f0f0")

# the servo board, the amp, the speaker on its bracket
ax, az, bx_, bz = layout_box("servo_board", "pcb", "#1e4fa3", y0=BASE_LAYOUT["servo_board"][4], y1=BASE_LAYOUT["servo_board"][4] + 1.6)
standoffs(ax, az, bx_, bz, 3, BASE_LAYOUT["servo_board"][4])
for i in range(16):
    for j, c in enumerate(("#d4a017", "#c0392b", "#222")):
        box(ax + 4 + j * 2.6, BASE_LAYOUT["servo_board"][4] + 1.6, az + 6 + i * 2.54 - 0.6, ax + 5.5 + j * 2.6,
            BASE_LAYOUT["servo_board"][4] + 8, az + 6 + i * 2.54 + 0.6, "plastic", c)
ax, az, bx_, bz = layout_box("amp", "pcb", "#5b2a86", y0=BASE_LAYOUT["amp"][4], y1=BASE_LAYOUT["amp"][4] + 1.6)
standoffs(ax, az, bx_, bz, 2.5, BASE_LAYOUT["amp"][4])
box(ax + 3, BASE_LAYOUT["amp"][4] + 1.6, bz - 7, bx_ - 3, BASE_LAYOUT["amp"][4] + 8, bz - 1, "plastic", "#2a7d3a")
sx0, sz0, sx1, sz1 = plan(*BASE_LAYOUT["speaker"][:2]) + plan(BASE_LAYOUT["speaker"][0] + BASE_LAYOUT["speaker"][2],
                                                             BASE_LAYOUT["speaker"][1] + BASE_LAYOUT["speaker"][3])
box(sx0, PLATE_TOP, sz0 + 1, sx1, PLATE_TOP + 30, sz1 - 2, "plastic", "#141518")              # the speaker's body
cx_, cy_ = (sx0 + sx1) / 2, PLATE_TOP + 15
cyl((cx_, cy_, sz1 - 2), (cx_, cy_, sz1 - 1.6), 12.5, "rubber", "#0d0d0f", 40)                 # the cone's surround
cyl((cx_, cy_, sz1 - 2.2), (cx_, cy_, sz1 - 1.4), 5.5, "plastic", "#1d1e22", 32)               # dust cap
lx0, lz0, lx1, lz1 = plan(*BASE_LAYOUT["speaker_leg"][:2]) + plan(BASE_LAYOUT["speaker_leg"][0] + BASE_LAYOUT["speaker_leg"][2],
                                                                 BASE_LAYOUT["speaker_leg"][1] + BASE_LAYOUT["speaker_leg"][3])
box(lx0, PLATE_TOP, lz0, lx1, PLATE_TOP + 30, lz1, "pvc")                                       # the plastic angle
fx0, fz0, fx1_, fz1_ = plan(*BASE_LAYOUT["speaker_foot"][:2]) + plan(BASE_LAYOUT["speaker_foot"][0] + BASE_LAYOUT["speaker_foot"][2],
                                                                    BASE_LAYOUT["speaker_foot"][1] + BASE_LAYOUT["speaker_foot"][3])
box(fx0, PLATE_TOP, fz0, fx1_, PLATE_TOP + 1.6, fz1_, "pvc")
for x in (sx0 + 3, sx1 - 3):
    for y in (PLATE_TOP + 3, PLATE_TOP + 27):
        cyl((x, y, sz1 - 2), (x, y, sz1 - 1), 2.2, "nylon", segments=16)                        # nylon screw heads
wire([(ax + 6, BASE_LAYOUT["amp"][4] + 6, bz - 4), (sx1 - 8, PLATE_TOP + 20, sz0 - 6), (sx1 - 14, PLATE_TOP + 25, sz0 + 1)], 1.4, "#c0392b")
wire([(ax + 9, BASE_LAYOUT["amp"][4] + 6, bz - 4), (sx1 - 10, PLATE_TOP + 18, sz0 - 6), (sx1 - 17, PLATE_TOP + 25, sz0 + 1)], 1.4, "#1a1a1a")
# jumper wires: GPIO pins to the servo board and amp
for i, c in enumerate(("#d4a017", "#2e86de", "#c0392b", "#27ae60")):
    wire([(gx + 20 + i * 5, board_top + 8.5, gz + 3), (gx + 30 + i * 5, board_top + 18, gz + 8),
          (bw / 2 - 25, BASE_LAYOUT["servo_board"][4] + 12, -bd / 2 + 12 + i * 3),
          (bw / 2 - 19, BASE_LAYOUT["servo_board"][4] + 4, -bd / 2 + 14 + i * 3)], 1.3, c)

# ================================================================== the neck: turntable, foot, yoke
bearing_y = BASE_HEIGHT + tb / 2
box(-25, bearing_y, -25, 25, bearing_y + 1.5, 25, "steel")
box(-21, bearing_y + 1.5, -21, 21, bearing_y + 4, 21, "steel")
cyl((0, bearing_y + 4, 0), (0, bearing_y + 5, 0), 18, "steel", segments=48)
sx0p, sz0p = plan(*BASE_LAYOUT["pan_servo"][:2])
sx1p, sz1p = plan(BASE_LAYOUT["pan_servo"][0] + BASE_LAYOUT["pan_servo"][2], BASE_LAYOUT["pan_servo"][1] + BASE_LAYOUT["pan_servo"][3])
box(sx0p, BASE_LAYOUT["pan_servo"][4], sz0p + 5, sx1p, BASE_HEIGHT - 5, sz1p - 5, "plastic", "#2f7fd8")      # pan servo body
box(sx0p, BASE_HEIGHT - 9, sz0p, sx1p, BASE_HEIGHT - 7.5, sz1p, "plastic", "#2f7fd8")                       # its mounting tabs
cyl(((sx0p + sx1p) / 2, BASE_HEIGHT - 5, sz0p + 11), ((sx0p + sx1p) / 2, bearing_y + 5, sz0p + 11), 2.4, "plastic", "#f4f4f4")
for i, c in enumerate(("#8a5a2b", "#d62d20", "#f5a623")):
    wire([(sx1p, BASE_LAYOUT["pan_servo"][4] + 6, sz0p + 14 + i), (sx1p + 12, BASE_LAYOUT["pan_servo"][4] + 2, sz0p + 10 + i),
          (bw / 2 - 24, BASE_LAYOUT["servo_board"][4] + 6, -bd / 2 + 30 + i * 1.4)], 1.2, c)
ts = TUBE["small"]
foot_y = bearing_y + 5 + ts / 2
tube([(FOOT / 2 * math.cos(a), foot_y, FOOT / 2 * math.sin(a)) for a in [i * math.pi / 36 for i in range(72)]] + [(FOOT / 2, foot_y, 0)], ts)
yw, yh = YOKE
yoke_y = foot_y + tb / 2
axle_y = yoke_y + yh
tube([(-yw / 2, axle_y, 0), (-yw / 2, yoke_y, 0), (yw / 2, yoke_y, 0), (yw / 2, axle_y, 0)], tb, False, rb)
box(yw / 2 + 3, axle_y - 22, -11.5, yw / 2 + 15, axle_y + 2, 11.5, "plastic", "#2f7fd8")                     # tilt servo
cyl((yw / 2 + 3, axle_y, 0), (yw / 2 - 1, axle_y, 0), 3.2, "plastic", "#f4f4f4")

# ================================================================== the head: a hollow CRT
t, r = TUBE["head"], RADIUS["head"]
W_, H_ = BEZEL
axle_z = 0.0
zf = axle_z + (BEZEL_DEPTH + TAPER_DEPTH) * 0.3
zm = zf - BEZEL_DEPTH
zb = zm - TAPER_DEPTH
y0 = axle_y
cy = y0 + H_ / 2
for z in (zf, zm):
    tube(rect_xy(-W_ / 2, y0, W_, H_, z), t, True, r)
kw, kh = BACK
bcy = y0 + BACK_LIFT + kh / 2
tube(rect_xy(-kw / 2, y0 + BACK_LIFT, kw, kh, zb), t, True, RADIUS["back"])
for c in ("tl", "tr", "bl", "br"):
    f, m = corner_mid(0, cy, W_, H_, zf, r, c), corner_mid(0, cy, W_, H_, zm, r, c)
    b = corner_mid(0, bcy, kw, kh, zb, RADIUS["back"], c)
    tube([f, m], t)
    tube([m, b], t)
tube([(-hs["axle"] / 2, y0, axle_z), (hs["axle"] / 2, y0, axle_z)], t)

# the screen ring and its spokes, the brass nuts, and the screen in front
rw, rh = hs["ring"]
ry = y0 + CHIN
tube(rect_xy(-rw / 2, ry, rw, rh, zf), t, True, r)
for sx in (-1, 1):
    tube([(sx * rw / 2, ry + rh / 2, zf), (sx * W_ / 2, ry + rh / 2, zf)], t)
    tube([(sx * rw * 0.28, y0, zf), (sx * rw * 0.28, ry, zf)], t)
sw, sh = PARTS["screen"]
left, right = PARTS["screen_glass"]
hx, hy = PARTS["screen_holes"]
bx0, by0 = -sw / 2, ry + t / 2 + CLEARANCE
for x in (bx0 + hx, bx0 + sw - hx):
    for y in (by0 + hy, by0 + sh - hy):
        scene["hexes"].append({"c": [x, y, zf], "across": NUT, "h": 2.4, "mat": "brass"})                 # nut, in the ring
pcb_back = zf + t / 2 + 1.0                                                                              # nylon washer
box(bx0, by0, pcb_back, bx0 + sw, by0 + sh, pcb_back + 1.6, "pcb", "#c8281e")
glass_x0, glass_w = bx0 + left, sw - left - right
box(glass_x0, by0 + 0.5, pcb_back + 1.6, glass_x0 + glass_w, by0 + sh - 0.5, pcb_back + 5.2, "steel")       # the display's metal frame
box(glass_x0 + 0.6, by0 + 1.1, pcb_back + 5.2, glass_x0 + glass_w - 0.6, by0 + sh - 1.1, pcb_back + 5.6, "glass")
image("face.png", ((glass_x0 + glass_x0 + glass_w) / 2 - 1.5, by0 + sh / 2, pcb_back + 5.65), 57.6, 43.2)
for x in (bx0 + hx, bx0 + sw - hx):
    for y in (by0 + hy, by0 + sh - hy):
        cyl((x, y, pcb_back + 1.6), (x, y, pcb_back + 3.2), 2.6, "nylon", segments=24)                     # nylon screw heads
for i in range(14):                                                                                        # header joints (right edge)
    cyl((bx0 + sw - 4.5, by0 + 8 + i * 2.54, pcb_back + 1.6), (bx0 + sw - 4.5, by0 + 8 + i * 2.54, pcb_back + 2.2), 0.7, "solder", segments=8)

# the webcam cradle, its two bars, and the camera on nylon standoffs
cw, ch = PARTS["camera"]
uw, uh = cw + 2 * CLEARANCE + ts, ch + CLEARANCE + ts / 2
top = y0 + H_ + t / 2 + ts / 2
tube([(-uw / 2, top + uh, zf), (-uw / 2, top, zf), (uw / 2, top, zf), (uw / 2, top + uh, zf)], ts, False, RADIUS["small"])
hx0, hy0, hdx, hdy = PARTS["camera_holes"]
cam_y1 = top + uh - ts / 2 - CLEARANCE          # the camera's top edge (the cradle is open at the top)
bar_z = zf - 3
for yy in (cam_y1 - hy0, cam_y1 - hy0 - hdy):
    tube([(-uw / 2, yy, zf), (-uw / 2 + 0.5, yy, bar_z), (uw / 2 - 0.5, yy, bar_z), (uw / 2, yy, zf)], 2.0)
    for xx in (-cw / 2 + hx0, -cw / 2 + hx0 + hdx):
        cyl((xx, yy, bar_z + 1), (xx, yy, bar_z + 1 + CAMERA_STANDOFF), 1.5, "nylon", segments=6)
cam_z = bar_z + 1 + CAMERA_STANDOFF
box(-cw / 2, cam_y1 - ch, cam_z, cw / 2, cam_y1, cam_z + 1, "pcb", "#1f7a3c")
box(-4.25, cam_y1 - 12 - 4.25, cam_z + 1, 4.25, cam_y1 - 12 + 4.25, cam_z + 5.5, "plastic", "#121212")
cyl((0, cam_y1 - 12, cam_z + 5.5), (0, cam_y1 - 12, cam_z + 6.6), 2.6, "glass")
wire([(0, cam_y1 - ch + 2, cam_z - 0.5), (0, top + 2, zf - 5), (1, top - 4, zm - 6), (3, cy + 10, zm - 12), (6, y0 + 4, -14), (10, foot_y + 2, -12),
      (14, BASE_HEIGHT - 4, -16), (-8, board_top + 4, -26)], 2.2, "#efefef", "ribbon")

# the touch bar on nylon spacers (glued, never soldered), and the chin's mic and power light
tbw, tbh = TOUCH_BAR
mid_top = y0 + H_ + t / 2
for sx in (-1, 1):
    cyl((sx * tbw / 2, mid_top, zm), (sx * tbw / 2, mid_top + 3, zm), 2.2, "nylon", segments=6)
tube([(-tbw / 2, mid_top + 3, zm), (-tbw / 2, mid_top + 3 + tbh, zm), (tbw / 2, mid_top + 3 + tbh, zm), (tbw / 2, mid_top + 3, zm)],
     ts, False, RADIUS["small"])
chin_y = (ry + y0) / 2 + t / 4
cyl((0, chin_y, zf - 3.5), (0, chin_y, zf - 2.5), PARTS["mic"] / 2, "pcb", "#1d3f8a", 32)
cyl((0, chin_y, zf - 2.5), (0, chin_y, zf - 1.5), 2.0, "steel")
cyl((rw * 0.36, chin_y, zf - 1), (rw * 0.36, chin_y, zf + 2), 2.5, "led")
# the head's wiring: one black braided bundle, down the neck to the Pi
wire([(-8, by0 + 10, pcb_back - 1), (-6, y0 + 6, zm - 6), (-14, foot_y + 4, -8), (-18, BASE_HEIGHT - 2, -14),
      (-30, board_top + 9, -bd / 2 + 10)], 5.2, "#161616", "braid")

top_y = top + uh
scene["meta"] = {"centre": [0, top_y / 2, 0], "height": top_y, "width": bw + tb, "depth": bd + tb, "desk": -tb / 2}

def draw_her_face(path):
    """Her face for the screen, drawn by her own code (pi/bolt_body/face.py), hat and snow included."""
    sys.path.insert(0, str(HERE.parents[1] / "pi"))
    from bolt_body.face import draw_face, load_config, params_for
    config = load_config()
    expression = {side: params_for(config, "idle", side) for side in ("left", "right")}
    draw_face(expression, config, size=(640, 480), smooth=2, time=1.3, hat=1.0).save(path)


if __name__ == "__main__":
    draw_her_face(HERE / "render-face.png")
    scene["images"] = [{**i, "src": "render-face.png"} for i in scene["images"]]
    out = HERE / "render-scene.json"
    out.write_text(json.dumps(scene))
    print(f"Wrote {out}: {sum(len(v) for k, v in scene.items() if isinstance(v, list))} parts, "
          f"about {top_y / 10:.0f} cm tall")
