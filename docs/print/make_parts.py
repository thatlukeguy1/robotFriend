#!/usr/bin/env python3
"""
Riley's 3D-printed body: a closed CRT-monitor head on an open desktop-case base.

    pip install manifold3d trimesh
    python docs/print/make_parts.py          (writes docs/print/stl/*.stl and docs/print/scene.json)
    python docs/print/make_parts.py check    (only checks that the parts fit together)

LESSON: a parametric model
==========================
Nothing here is drawn by hand. Every part is built from the numbers below by adding and cutting
simple solids (boxes, cylinders, rounded slabs): "constructive solid geometry". Change a number,
run the script again, and every part that depends on it changes with it. Sizes marked MEASURE
are guesses until you've measured your own part; check them before ordering a print.

Coordinates are millimetres. x is across (+ = Riley's left as you face her... no: + = YOUR right as
you face her), y is depth (+ = towards the back), z is up. Each part is modelled where it sits on
the finished robot, then turned so its flattest side is down for printing.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold

HERE = Path(__file__).parent
SEG = 96                 # segments in a full circle: smooth curves, no visible facets

# ------------------------------------------------------------------ printing
WALL = 2.4               # shell walls: 6 lines of a 0.4 mm nozzle
FIT = 0.25               # gap per side where one printed part slides into another
SELF_TAP_M2 = 1.7        # hole for an M2 self-tapping screw to cut its own thread
SELF_TAP_M25 = 2.1       # ...M2.5 (the Pi's holes)
SELF_TAP_M3 = 2.5        # ...M3
CLEAR_M3 = 3.4           # an M3 bolt slides through

# ------------------------------------------------------------------ the parts that go inside
SCREEN_PCB = (85.0, 50.0)          # 2.8" ILI9341 board: MEASURED
SCREEN_MARGINS = (6.0, 10.0)       # bare board left / right of the glass (pins on the right): MEASURED
SCREEN_HOLES = (3.2, 3.2)          # corner holes from the side and top edges: MEASURE
SCREEN_GLASS_DEPTH = 4.0           # front of the glass to the front of the board: MEASURE
MIC_BOARD = 14.0                   # INMP441 board, across: MEASURE
CAMERA = (25.0, 24.0)              # Camera Module 3 board
CAMERA_HOLES = (2.0, 2.0, 21.0, 12.5)   # M2 holes: from the left and top edges, then apart across and down
CAMERA_LENS = 5.5                  # lens height above the board's front: MEASURE
SERVO = {"length": 23.0, "width": 12.0, "tabs": 32.0, "tab_thick": 3.0, "hole_spacing": 28.0,
         "shaft_from_end": 6.0, "below_tabs": 17.0, "above_tabs": 11.0, "case_above_tabs": 8.0}   # MEASURED MG90S
HORN = {"diameter": 20.0, "hole_r": 7.0, "above_shaft": 1.5}   # round horn: across, screw holes from centre,
                                                                # its flat face above the shaft's tip: MEASURE
BEARING = {"square": 72.0, "hole": 35.0, "thick": 8.0,          # YOURS
           "bottom_holes": 30.0, "top_holes": 30.0}             # screw holes from the centre: MEASURE
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]  # Pi 4, from its SD-card end and its USB-C edge
SERVO_BOARD_HOLES = (19.0, 56.0)   # PCA9685 board's holes apart (across, along): MEASURE
SPEAKER = (70.0, 30.0, 18.0)       # long, tall, deep: MEASURED (roughly)
SPEAKER_HOLES = 62.0               # its 2 end holes apart: MEASURE

# ------------------------------------------------------------------ the head (a closed CRT)
HEAD = (112.0, 88.0)     # the bezel: width, height
HEAD_R = 14.0            # its corner radius, seen from the front
FRONT_FILLET = 6.0       # every edge is rounded, front...
BACK_FILLET = 8.0        # ...and back: no sharp corners anywhere
FACE_WALL = 3.2          # the face is thicker than the other walls: the black face plate sits in a recess in it
FACE_PLATE_T = 1.6       # the black face plate (screen window, mic and light holes): glued into the recess
FACE_RIM = 3.0           # beige rim round the face plate
BEZEL_DEPTH = 22.0       # the front part's depth (the rest is the back part)
COLLAR = 6.0             # the back part starts straight, so the front part's lip slides in
LIP = 5.0                # how far the lip goes in
BACK = (92.0, 74.0)      # the back of the tube: width, height (a gentle taper: a chunky, friendly CRT)
BACK_R = 12.0
HEAD_DEPTH = 70.0        # face to back
BACK_LIFT = 2.0          # the back sits a little higher than the bottom (CRTs taper more on top)
WINDOW_TOP = 12.0        # top of the head to the top of the screen window
CHIN_Z = 12.5            # height of the mic and the power light

# ------------------------------------------------------------------ the neck
PIVOT_STATIONS = (27.0, 35.0, 43.0)   # where the head can hang from: face to pivot. Pick the one it balances on
LUG_X = 16.0             # head lugs: centre, either side
LUG_T = 4.0              # their thickness
LUG_DROP = 20.0          # pivot below the head's bottom
ARM_T = 4.0              # yoke arm thickness
WASHER = 1.0             # gap for a washer on the bolt side
PIVOT_H = 30.0           # pivot above the drive disc
DISC = 82.0              # drive disc, across
DISC_T = 4.0
HUB = 28.0               # the horn hub, across (passes through the bearing's hole)

# ------------------------------------------------------------------ the base (an open desktop case)
BASE = (150.0, 110.0, 50.0)   # width, depth, height (floor to deck top)
BASE_R = 12.0
FLOOR_T = 3.0
DECK_T = 4.0
PILLAR = 12.0
NECK_Y = -19.0           # the neck sits forward of centre, so the Pi fits behind it
PI_AT = (-58.0, -8.0)    # the Pi's SD-card end (x) and USB-C edge (y): USB and network face RIGHT, pins at the BACK
STANDOFF = 5.0           # boards stand this high off the floor
CASE_POCKET = 3.0        # the pan servo's case tucks this far up into a pocket under the deck, so its shaft
                         # reaches above the deck and the horn turns there, clear of the servo's own screws


# ================================================================== building blocks
def rrect(w, h, r):
    """A rounded rectangle, centred."""
    r = min(r, w / 2 - 0.01, h / 2 - 0.01)
    if r <= 0:
        return CrossSection.square((w, h), center=True)
    return CrossSection.square((w - 2 * r, h - 2 * r), center=True).offset(r, JoinType.Round, circular_segments=SEG)


def slab_y(w, h, r, y0, y1, zc, xc=0.0):
    """A rounded rectangle w (x) by h (z), stretched from y0 to y1."""
    return rrect(w, h, r).extrude(y1 - y0).rotate((90, 0, 0)).translate((xc, y1, zc))


def slab_z(w, d, r, z0, z1, xc=0.0, yc=0.0):
    """A rounded rectangle w (x) by d (y), from z0 up to z1."""
    return rrect(w, d, r).extrude(z1 - z0).translate((xc, yc, z0))


def slab_x(d, h, r, x0, x1, yc=0.0, zc=0.0):
    """A rounded rectangle d (y) by h (z), from x0 to x1."""
    return rrect(h, d, r).extrude(x1 - x0).rotate((0, 90, 0)).translate((x0, yc, zc))


def fillet_steps(f, steps=8):
    """(inset, distance in) pairs round a quarter circle of radius f: stacking slabs at these makes a
    rounded edge, because the hull of the stack is smooth."""
    return [(f * (1 - math.sin(a)), f * (1 - math.cos(a))) for a in (math.pi / 2 * i / steps for i in range(steps + 1))]


def soft_slab_z(w, d, r, z0, z1, f, xc=0.0, yc=0.0):
    """slab_z with its top and bottom edges rounded too (radius f)."""
    layers = []
    for ins, dz in fillet_steps(f):
        size = (w - 2 * ins, d - 2 * ins, max(r - ins, 0.5))
        layers += [slab_z(*size, z0 + dz, z0 + dz + 0.01, xc, yc), slab_z(*size, z1 - dz - 0.01, z1 - dz, xc, yc)]
    return Manifold.batch_hull(layers)


def soft_disc(d, z0, z1, f, x=0.0, y=0.0):
    layers = []
    for ins, dz in fillet_steps(f):
        layers += [cyl_z(d - 2 * ins, z0 + dz, z0 + dz + 0.01, x, y), cyl_z(d - 2 * ins, z1 - dz - 0.01, z1 - dz, x, y)]
    return Manifold.batch_hull(layers)


def soft_tube_y(front, back, y0, y1, straight_to, f0, f1):
    """A rounded box along y whose front (at y0) and back (at y1) can differ in size: a CRT.
    front and back are (width, height, corner radius, z centre); the front size runs straight
    back to straight_to, then tapers. Every edge is rounded (f0 at the front, f1 at the back)."""
    layers = []
    w, h, r, zc = front
    for ins, dy in fillet_steps(f0):
        layers.append(slab_y(w - 2 * ins, h - 2 * ins, max(r - ins, 0.5), y0 + dy, y0 + dy + 0.01, zc))
    layers.append(slab_y(w, h, r, straight_to - 0.01, straight_to, zc))
    w, h, r, zc = back
    for ins, dy in fillet_steps(f1):
        layers.append(slab_y(w - 2 * ins, h - 2 * ins, max(r - ins, 0.5), y1 - dy - 0.01, y1 - dy, zc))
    return Manifold.batch_hull(layers)


def box(x0, y0, z0, x1, y1, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cyl_z(d, z0, z1, x=0.0, y=0.0):
    return Manifold.cylinder(z1 - z0, d / 2, circular_segments=SEG).translate((x, y, z0))


def cyl_x(d, x0, x1, y=0.0, z=0.0):
    return Manifold.cylinder(x1 - x0, d / 2, circular_segments=SEG).rotate((0, 90, 0)).translate((x0, y, z))


def cyl_y(d, y0, y1, x=0.0, z=0.0):
    return Manifold.cylinder(y1 - y0, d / 2, circular_segments=SEG).rotate((-90, 0, 0)).translate((x, y0, z))


def union(parts):
    return Manifold.batch_boolean(list(parts), _op("add"))


def _op(name):
    from manifold3d import OpType
    return {"add": OpType.Add, "sub": OpType.Subtract}[name]


# ================================================================== the head
def screen_layout():
    """Where the screen sits on the face (head coordinates)."""
    gw, gh = SCREEN_PCB[0] - sum(SCREEN_MARGINS), SCREEN_PCB[1]
    zc = HEAD[1] - WINDOW_TOP - gh / 2 - 0.5
    left = -gw / 2 - SCREEN_MARGINS[0]          # the glass is centred, so the board sits a little right
    return dict(glass=(gw, gh), zc=zc, pcb_x=(left, left + SCREEN_PCB[0]), pcb_z=(zc - gh / 2, zc + gh / 2))


def head_shell():
    """The whole CRT as one rounded shell; it's cut in two at the bezel."""
    W = WALL
    hw, hh = HEAD
    bw, bh = BACK
    zb = BACK_LIFT + bh / 2
    straight = BEZEL_DEPTH + COLLAR
    outer = soft_tube_y((hw, hh, HEAD_R, hh / 2), (bw, bh, BACK_R, zb), 0, HEAD_DEPTH, straight, FRONT_FILLET, BACK_FILLET)
    inner = soft_tube_y((hw - 2 * W, hh - 2 * W, HEAD_R - W, hh / 2), (bw - 2 * W, bh - 2 * W, BACK_R - W, zb),
                        FACE_WALL, HEAD_DEPTH - W, straight, FRONT_FILLET - W, BACK_FILLET - W)
    return outer - inner, inner


def face_plate_size():
    hw, hh = HEAD
    w, h = hw - 2 * FRONT_FILLET - 2 * FACE_RIM, hh - 2 * FRONT_FILLET - 2 * FACE_RIM
    return w, h, max(HEAD_R - FRONT_FILLET - FACE_RIM, 1.0)


def head_front():
    """The bezel: the face with its screen window and a recess for the black face plate, the chin's
    mic ring and light sleeve, and a lip that slides into the back part."""
    W = WALL
    hw, hh = HEAD
    s = screen_layout()
    shell, _ = head_shell()
    part = shell ^ box(-200, -1, -200, 200, BEZEL_DEPTH, 200)
    lip_o = slab_y(hw - 2 * W - 2 * FIT, hh - 2 * W - 2 * FIT, HEAD_R - W, BEZEL_DEPTH - 1, BEZEL_DEPTH + LIP, hh / 2)
    lip_i = slab_y(hw - 2 * W - 2 * FIT - 3.2, hh - 2 * W - 2 * FIT - 3.2, HEAD_R - W - 1.6, BEZEL_DEPTH - 2, BEZEL_DEPTH + LIP + 1, hh / 2)
    part = part + (lip_o - lip_i)
    gw, gh = s["glass"]
    pw, ph, pr = face_plate_size()
    recess = slab_y(pw, ph, pr, -1, FACE_PLATE_T, hh / 2)
    win = slab_y(gw + 3, gh + 3, 2.0, -1, FACE_WALL + 1, s["zc"])          # a little bigger than the plate's window
    # 4 bosses the screen's board screws to (from behind), the glass against the face
    x0, x1 = s["pcb_x"]; z0, z1 = s["pcb_z"]
    hx, hz = SCREEN_HOLES
    bosses, holes = [], []
    for x in (x0 + hx, x1 - hx):
        for z in (z0 + hz, z1 - hz):
            bosses.append(cyl_y(5.0, FACE_WALL - 0.5, FACE_WALL + SCREEN_GLASS_DEPTH, x, z))
            holes.append(cyl_y(SELF_TAP_M2, FACE_WALL + 0.8, FACE_WALL + SCREEN_GLASS_DEPTH + 1, x, z))
    # chin: the mic's sound hole with a ring to seat its board, and a sleeve for the power light
    mic = cyl_y(2.0, -1, FACE_WALL + 1, 0, CHIN_Z)
    mic_ring = cyl_y(MIC_BOARD + 4.4, FACE_WALL - 0.5, FACE_WALL + 3, 0, CHIN_Z) - cyl_y(MIC_BOARD + 0.6, FACE_WALL - 1, FACE_WALL + 4, 0, CHIN_Z)
    led_ring = cyl_y(8.4, FACE_WALL - 0.5, FACE_WALL + 6, 32, CHIN_Z) - cyl_y(5.2, FACE_WALL - 1, FACE_WALL + 7, 32, CHIN_Z)
    led = cyl_y(5.2, -1, FACE_WALL + 1, 32, CHIN_Z)
    # the camera on top: a slot for its ribbon and two blocks its hood screws into
    cam_blocks = [box(sx * 16.5 if sx < 0 else 10.5, FACE_WALL - 0.5, hh - W - 6, sx * 10.5 if sx < 0 else 16.5, 15, hh - W + 0.5)
                  for sx in (-1, 1)]
    cam_holes = [cyl_z(SELF_TAP_M2, hh - W - 6.5, hh + 1, sx * 13.5, 12) for sx in (-1, 1)]
    slot = box(-9, 9, hh - W - 1, 9, 12, hh + 1)
    # two ribs inside the sides: the back part's screws go into them
    ribs, rib_holes = [], []
    lx = hw / 2 - W - FIT - 1.6                     # the lip's inside face
    for sx in (-1, 1):
        a, b = sorted((sx * (lx - 5), sx * (hw / 2 - W + 0.5)))
        ribs.append(box(a, FACE_WALL - 0.5, hh / 2 - 4, b, BEZEL_DEPTH, hh / 2 + 4))
        a, b = sorted((sx * (lx - 5), sx * (lx + 0.2)))
        ribs.append(box(a, BEZEL_DEPTH - 1, hh / 2 - 4, b, BEZEL_DEPTH + LIP - 0.5, hh / 2 + 4))
        a, b = sorted((sx * (lx - 6), sx * (hw / 2 + 1)))
        rib_holes.append(cyl_x(SELF_TAP_M2, a, b, BEZEL_DEPTH + 2.5, hh / 2))
    part = union([part, *bosses, mic_ring, led_ring, *cam_blocks, *ribs])
    return part - union([recess, win, *holes, mic, led, *cam_holes, slot, *rib_holes])


def face_plate():
    """The black front: one smooth panel over the whole face, like a modern screen. Glued into the recess."""
    hw, hh = HEAD
    s = screen_layout()
    gw, gh = s["glass"]
    pw, ph, pr = face_plate_size()
    plate = slab_y(pw - 2 * FIT, ph - 2 * FIT, pr - FIT, 0, FACE_PLATE_T, hh / 2)
    cuts = [slab_y(gw + 1, gh + 1, 1.5, -1, FACE_PLATE_T + 1, s["zc"]),
            cyl_y(2.0, -1, FACE_PLATE_T + 1, 0, CHIN_Z), cyl_y(5.2, -1, FACE_PLATE_T + 1, 32, CHIN_Z)]
    return plate - union(cuts)


def head_back():
    """The tapering tube and back of the CRT, with vents, a cable hole and the two lugs it pivots on."""
    W = WALL
    hw, hh = HEAD
    bw, bh = BACK
    y0 = BEZEL_DEPTH
    zb = BACK_LIFT + bh / 2
    shell, inner = head_shell()
    part = shell ^ box(-200, y0, -200, 200, HEAD_DEPTH + 1, 200)
    cuts = [slab_y(40, 2.6, 1.3, HEAD_DEPTH - W - 2, HEAD_DEPTH + 1, zb + k) for k in (-15, -9, -3, 3, 9, 15)]   # vents
    cuts.append(slab_z(24, 12, 4, -1, 6, 0, 56))                                 # cable hole underneath
    cuts += [cyl_x(2.4, sx * (hw / 2 - W - 1), sx * (hw / 2 + 1), y0 + 2.5, hh / 2) if sx > 0 else
             cyl_x(2.4, -hw / 2 - 1, -hw / 2 + W + 1, y0 + 2.5, hh / 2) for sx in (-1, 1)]   # 2 screws into the front part's ribs
    # the lugs: hang down under the bottom, rounded at the bottom; a pivot hole at each station
    ly0, ly1 = PIVOT_STATIONS[0] - 6, PIVOT_STATIONS[-1] + 6
    zp = -LUG_DROP
    zbot = zp - HORN["hole_r"] - 4.5
    lugs = []
    for sx in (-1, 1):
        a, b = sorted((sx * (LUG_X - LUG_T / 2), sx * (LUG_X + LUG_T / 2)))
        lugs.append(slab_x(ly1 - ly0, 2 * (zp - zbot), 7, a, b, (ly0 + ly1) / 2, zp))
        lugs.append(box(a, ly0, zp, b, ly1, 3))
        for st in PIVOT_STATIONS:
            if sx < 0:
                cuts.append(cyl_x(CLEAR_M3, a - 1, b + 1, st, zp))             # left: an M3 bolt is the hinge
            else:
                cuts.append(cyl_x(6.0, a - 1, b + 1, st, zp))                  # right: the tilt servo's horn, centre screw through here
                for dz in (-HORN["hole_r"], HORN["hole_r"]):
                    cuts.append(cyl_x(1.5, a - 1, b + 1, st, zp + dz))         # ...and its 2 small screws
    part = union([part, *lugs]) - union(cuts)
    return part - inner        # the lugs mustn't poke inside


def camera_hood():
    """A little rounded box on top of the head, like an old clip-on webcam."""
    W = 2.0
    cw, ch = CAMERA
    w, d, h = cw + 2 * W + 4, 16.0, ch + 4 + 3 + 2 * W
    outer = soft_tube_y((w, h, 6, h / 2), (w, h, 6, h / 2), 0, d, d - 2.5, 2.5, 2.5)
    inner = slab_y(w - 2 * W, h - 2 * W, 4, W, d + 1, h / 2)
    part = outer - inner
    bz = W + 4                                    # the board's bottom edge
    hx0, hy0, hdx, hdy = CAMERA_HOLES
    boss_len = CAMERA_LENS - 1
    bosses, cuts = [], []
    for x in (-cw / 2 + hx0, -cw / 2 + hx0 + hdx):
        for z in (bz + ch - hy0, bz + ch - hy0 - hdy):
            bosses.append(cyl_y(4.5, W - 0.5, W + boss_len, x, z))
            cuts.append(cyl_y(SELF_TAP_M2 - 0.2, W + 0.6, W + boss_len + 1, x, z))
    cuts.append(cyl_y(11, -1, W + 1, 0, bz + ch - 9.5))                       # round lens window
    cuts.append(box(-9, W + boss_len - 1, -1, 9, W + boss_len + 2.5, W + 1))  # ribbon slot, down into the head
    for sx in (-1, 1):
        cuts.append(cyl_z(2.4, -1, W + 1, sx * 13.5, 10))                      # 2 screws down into the head
    return union([part, *bosses]) - union(cuts), (w, d, h)


# ================================================================== the neck
def neck_world():
    """World positions: the base's floor centre is (0, 0, 0)."""
    deck_top = BASE[2]
    disc_z = deck_top + BEARING["thick"]
    pivot_z = disc_z + DISC_T + PIVOT_H
    tabs_top = deck_top - DECK_T + CASE_POCKET - 0.3 - SERVO["case_above_tabs"]   # case top just inside its pocket
    shaft_top = tabs_top + SERVO["above_tabs"]
    return dict(deck_top=deck_top, disc_z=disc_z, pivot_z=pivot_z, tabs_top=tabs_top, shaft_top=shaft_top,
                hub_bottom=shaft_top + HORN["above_shaft"])


def tilt_servo_x():
    """The tilt servo lies on its side in the right arm, shaft pointing in at the right lug."""
    lug_face = LUG_X + LUG_T / 2
    shaft_top = lug_face + HORN["above_shaft"]
    tabs_in = shaft_top + SERVO["above_tabs"]                  # the tabs' shaft-side face
    arm_in = tabs_in + SERVO["tab_thick"]                      # tabs pressed against the arm's inside
    return dict(shaft_top=shaft_top, tabs_in=tabs_in, arm_in=arm_in, arm_out=arm_in + ARM_T,
                body_out=arm_in + SERVO["below_tabs"])


def drive_disc():
    """The disc that turns on the bearing, with the yoke's two arms. The right arm holds the tilt servo."""
    n = neck_world()
    t = tilt_servo_x()
    z0, z1 = n["disc_z"], n["disc_z"] + DISC_T
    pz = n["pivot_z"]
    part = soft_disc(DISC, z0, z1, 1.5, 0, NECK_Y)
    case_c = pz - (SERVO["length"] / 2 - SERVO["shaft_from_end"])     # the case runs down from the shaft
    arm_top = pz + SERVO["hole_spacing"] / 2 - (case_c - pz) * -1 + 4
    arm_top = case_c + SERVO["hole_spacing"] / 2 + 4
    lx0, lx1 = -(LUG_X + LUG_T / 2 + WASHER + ARM_T), -(LUG_X + LUG_T / 2 + WASHER)
    arms = [box(t["arm_in"], NECK_Y - 9, z1 - 0.5, t["arm_out"], NECK_Y + 9, arm_top - 9),        # round-topped arms
            slab_x(18, 18, 9, t["arm_in"], t["arm_out"], NECK_Y, arm_top - 9),
            box(lx0, NECK_Y - 9, z1 - 0.5, lx1, NECK_Y + 9, pz),
            slab_x(18, 18, 9, lx0, lx1, NECK_Y, pz)]
    # gussets: wedges from each arm's foot onto the disc
    for x_in, x_out in ((t["arm_in"], t["arm_out"]), (-(LUG_X + LUG_T / 2 + WASHER), -(LUG_X + LUG_T / 2 + WASHER + ARM_T))):
        sgn = 1 if x_out > x_in else -1
        g = Manifold.batch_hull([box(min(x_in, x_out), NECK_Y - 9, z1 - 0.5, max(x_in, x_out), NECK_Y + 9, z1 + 10),
                                 box(min(x_in - sgn * 8, x_in), NECK_Y - 9, z1 - 0.5, max(x_in - sgn * 8, x_in), NECK_Y + 9, z1)])
        arms.append(g)
    cuts = [cyl_z(6.5, z0 - 1, z1 + 1, 0, NECK_Y)]                                  # screwdriver to the horn's centre screw
    for a in range(3):                                                             # 3 screws down into the hub
        ang = math.radians(90 + a * 120)
        cuts.append(cyl_z(2.4, z0 - 1, z1 + 1, 10.5 * math.cos(ang), NECK_Y + 10.5 * math.sin(ang)))
    r = BEARING["top_holes"]
    for a in range(4):                                                             # 4 screws into the bearing's top plate
        ang = math.radians(45 + a * 90)
        cuts.append(cyl_z(CLEAR_M3, z0 - 1, z1 + 1, r * math.cos(ang), NECK_Y + r * math.sin(ang)))
    # the right arm: a window for the servo's body, 2 screw holes for its tabs
    cuts.append(box(t["arm_in"] - 1, NECK_Y - 6.3, case_c - SERVO["length"] / 2 - 0.3, t["arm_out"] + 1, NECK_Y + 6.3,
                    case_c + SERVO["length"] / 2 + 0.3))
    for dz in (-SERVO["hole_spacing"] / 2, SERVO["hole_spacing"] / 2):
        cuts.append(cyl_x(SELF_TAP_M2, t["arm_in"] - 1, t["arm_out"] + 1, NECK_Y, case_c + dz))
    # the left arm: the hinge bolt
    cuts.append(cyl_x(CLEAR_M3, -(LUG_X + LUG_T / 2 + WASHER + ARM_T) - 1, -(LUG_X + LUG_T / 2 + WASHER) + 1, NECK_Y, pz))
    disc = union([part, *arms]) - union(cuts)
    # nothing may stand where the bearing's hole lets the hub through
    return disc


def horn_hub():
    """Hangs under the disc, through the bearing's hole, down to the pan servo's horn."""
    n = neck_world()
    z0, z1 = n["hub_bottom"], n["disc_z"]
    part = cyl_z(HUB, z0, z1, 0, NECK_Y)
    cuts = [cyl_z(6.5, z0 - 1, z1 + 1, 0, NECK_Y)]
    for dx in (-HORN["hole_r"], HORN["hole_r"]):
        cuts.append(cyl_z(1.5, z0 - 1, z0 + 6, dx, NECK_Y))
    for a in range(3):
        ang = math.radians(90 + a * 120)
        cuts.append(cyl_z(SELF_TAP_M2, z1 - 7, z1 + 1, 10.5 * math.cos(ang), NECK_Y + 10.5 * math.sin(ang)))
    return part - union(cuts)


# ================================================================== the base
def pillar_xy():
    w, d, _ = BASE
    return [(sx * (w / 2 - PILLAR / 2 - 3), sy * (d / 2 - PILLAR / 2 - 3)) for sx in (-1, 1) for sy in (-1, 1)]


def base_layout():
    """What sits on the floor, as boxes (x0, y0, x1, y1, z0, z1): for the fit check and the picture."""
    px, py = PI_AT
    z = FLOOR_T + STANDOFF
    return {
        "pi": (px, py, px + 85, py + 56, z, z + 17),
        "pi_ports": (px + 85, py + 2, px + 88, py + 54, z, z + 17),
        "pi_power": (px + 4, py - 16, px + 15, py, z, z + 26),      # a right-angle USB-C plug, pointing UP
        "servo_board": (40, -24, 65, 39, z, z + 15),
        "amp": (40, -53, 58, -35, z, z + 10),
        "speaker": (-SPEAKER[0] / 2, -53, SPEAKER[0] / 2, -53 + SPEAKER[2], FLOOR_T, FLOOR_T + SPEAKER[1]),
        "speaker_bracket": (-38, -35, 38, -32, FLOOR_T, FLOOR_T + SPEAKER[1]),
    }


def pan_servo_box():
    n = neck_world()
    sx = SERVO["shaft_from_end"]
    return (-(SERVO["length"] - sx), NECK_Y - SERVO["width"] / 2, sx, NECK_Y + SERVO["width"] / 2,
            n["tabs_top"] - SERVO["tab_thick"] - SERVO["below_tabs"], n["tabs_top"] + SERVO["case_above_tabs"] - SERVO["tab_thick"])


def base_frame():
    """The floor, four corner pillars, and everything the boards stand on."""
    w, d, h = BASE
    deck_under = h - DECK_T
    part = [soft_slab_z(w, d, BASE_R, 0, FLOOR_T, 1.2)]
    cuts = []
    for x, y in pillar_xy():
        part.append(cyl_z(PILLAR, FLOOR_T - 0.5, deck_under, x, y))
        cuts.append(cyl_z(SELF_TAP_M3, deck_under - 12, deck_under + 1, x, y))
    # Pi standoffs
    px, py = PI_AT
    for hx, hy in PI_HOLES:
        part.append(cyl_z(6, FLOOR_T - 0.5, FLOOR_T + STANDOFF, px + hx, py + hy))
        cuts.append(cyl_z(SELF_TAP_M25, FLOOR_T, FLOOR_T + STANDOFF + 1, px + hx, py + hy))
    # servo board standoffs (its long side front to back)
    sx0, sy0, sx1, sy1, *_ = base_layout()["servo_board"]
    cx, cy = (sx0 + sx1) / 2, (sy0 + sy1) / 2
    for dx in (-SERVO_BOARD_HOLES[0] / 2, SERVO_BOARD_HOLES[0] / 2):
        for dy in (-SERVO_BOARD_HOLES[1] / 2, SERVO_BOARD_HOLES[1] / 2):
            part.append(cyl_z(6, FLOOR_T - 0.5, FLOOR_T + STANDOFF, cx + dx, cy + dy))
            cuts.append(cyl_z(SELF_TAP_M25, FLOOR_T, FLOOR_T + STANDOFF + 1, cx + dx, cy + dy))
    # the amp: a shallow tray to stick it in (double-sided foam tape)
    ax0, ay0, ax1, ay1, *_ = base_layout()["amp"]
    part.append(box(ax0 - 1.5, ay0 - 1.5, FLOOR_T - 0.5, ax1 + 1.5, ay1 + 1.5, FLOOR_T + 2))
    cuts.append(box(ax0, ay0, FLOOR_T, ax1, ay1, FLOOR_T + 3))
    # the speaker's bracket: an upright plate it screws to (through rubber washers), with 2 braces
    bx0, by0, bx1, by1, bz0, bz1 = base_layout()["speaker_bracket"]
    part.append(box(bx0, by0, bz0 - 0.5, bx1, by1, bz1))
    for x in (bx0 + 4, bx1 - 8):
        part.append(Manifold.batch_hull([box(x, by1 - 0.5, bz0 - 0.5, x + 4, by1 + 14, bz0),
                                         box(x, by1 - 0.5, bz0 - 0.5, x + 4, by1, bz1 - 4)]))
    for dx in (-SPEAKER_HOLES / 2, SPEAKER_HOLES / 2):
        cuts.append(cyl_y(3.2, by0 - 1, by1 + 1, dx, FLOOR_T + SPEAKER[1] / 2))
    # a hole under the Pi's fan to let air in, and two cable-tie slots by the speaker
    cuts.append(slab_z(30, 30, 4, -1, FLOOR_T + 1, px + 34, py + 30))
    return union(part) - union(cuts)


def base_deck():
    """The top: the bearing sits on it, the pan servo hangs under it, and it screws onto the pillars."""
    w, d, h = BASE
    n = neck_world()
    z0, z1 = h - DECK_T, h
    part = [soft_slab_z(w, d, BASE_R, z0, z1, 1.8)]
    sx = SERVO["shaft_from_end"]
    case_c = -(SERVO["length"] / 2 - sx)
    cuts = [box(case_c - SERVO["length"] / 2 - 0.3, NECK_Y - SERVO["width"] / 2 - 0.3, z0 - 1,
                case_c + SERVO["length"] / 2 + 0.3, NECK_Y + SERVO["width"] / 2 + 0.3, z0 + CASE_POCKET),   # the case's pocket
            cyl_z(13.0, z0 - 1, z1 + 1, 0, NECK_Y)]                                    # its round boss and shaft come through
    for x, y in pillar_xy():
        cuts.append(cyl_z(CLEAR_M3, z0 - 1, z1 + 1, x, y))
    r = BEARING["bottom_holes"]
    for sx in (-1, 1):
        for sy in (-1, 1):
            cuts.append(cyl_z(CLEAR_M3, z0 - 1, z1 + 1, sx * r * math.sqrt(0.5), NECK_Y + sy * r * math.sqrt(0.5)))
    cuts.append(slab_z(34, 14, 5, z0 - 1, z1 + 1, 0, 32))                         # cables from the head go down here
    # the pan servo hangs from 2 blocks under the deck, screwed up through its tabs
    for dx in (-SERVO["hole_spacing"] / 2, SERVO["hole_spacing"] / 2):
        x = case_c + dx
        part.append(box(x - 2, NECK_Y - 6, n["tabs_top"], x + 2, NECK_Y + 6, z0 + 0.5))
        cuts.append(cyl_z(SELF_TAP_M2, n["tabs_top"] - 1, n["tabs_top"] + 8, x, NECK_Y))
    return union(part) - union(cuts)


# ================================================================== checks
def problems():
    """Things that don't fit, as sentences ([] = it all fits)."""
    out = []
    n = neck_world()
    t = tilt_servo_x()
    s = screen_layout()
    w, d, h = BASE
    if s["pcb_x"][0] < -HEAD[0] / 2 + WALL or s["pcb_x"][1] > HEAD[0] / 2 - WALL - 6:
        out.append("the screen's board doesn't fit inside the head")
    if n["disc_z"] - n["hub_bottom"] < 2:
        out.append("the horn hub is too short to hold")
    if n["hub_bottom"] - HORN["above_shaft"] - 0.5 < n["deck_top"]:
        out.append("the horn would rub on the deck")
    if HUB >= BEARING["hole"] - 2:
        out.append("the hub doesn't fit through the bearing's hole")
    if t["arm_out"] > DISC / 2 - 1:
        out.append("the right arm is off the edge of the drive disc")
    if NECK_Y - BEARING["square"] / 2 < -d / 2 - 0.01:
        out.append("the bearing hangs off the front of the base")
    # the hanging servo against everything on the floor
    sb = pan_servo_box()
    lay = base_layout()
    for name, b in lay.items():
        if name.startswith("speaker"):
            continue
        if b[0] < sb[2] and sb[0] < b[2] and b[1] < sb[3] and sb[1] < b[3] and b[4] < sb[5] and sb[4] < b[5]:
            out.append(f"the pan servo hits the {name}")
    for name, b in lay.items():
        for x, y in pillar_xy():
            if b[0] < x + PILLAR / 2 and x - PILLAR / 2 < b[2] and b[1] < y + PILLAR / 2 and y - PILLAR / 2 < b[3]:
                out.append(f"the {name} hits a corner pillar")
        if b[0] < -w / 2 or b[2] > w / 2 or b[1] < -d / 2 or b[3] > d / 2 or b[5] > h - DECK_T:
            out.append(f"the {name} doesn't fit in the base")
    # the head nodding: its bottom must clear the yoke's arms (20 degrees either way)
    arm_top = (n["pivot_z"] - (SERVO["length"] / 2 - SERVO["shaft_from_end"])) + SERVO["hole_spacing"] / 2 + 4
    lowest = n["pivot_z"] + LUG_DROP - 9 * math.sin(math.radians(20))
    if lowest < arm_top + 1:
        out.append("the head would hit the yoke's arms when it nods")
    return out


# ================================================================== output
PRINT = {   # name: (how to turn it so its flattest side is down, colour in the picture)
    "head_front": ((90, 0, 0), "#e8dcc0"),
    "face_plate": ((90, 0, 0), "#16181c"),
    "head_back": ((-90, 0, 0), "#e8dcc0"),
    "camera_hood": ((90, 0, 0), "#e8dcc0"),
    "base_frame": ((0, 0, 0), "#c9a227"),
    "base_deck": ((180, 0, 0), "#c9a227"),
    "drive_disc": ((0, 0, 0), "#c9a227"),
    "horn_hub": ((0, 0, 0), "#c9a227"),
}


def save(m, path, rot):
    m = m.rotate(rot) if any(rot) else m
    x0, y0, z0, x1, y1, z1 = m.bounding_box()
    m = m.translate((-(x0 + x1) / 2, -(y0 + y1) / 2, -z0))          # centred, sitting on the bed
    mesh = m.to_mesh()
    trimesh.Trimesh(np.array(mesh.vert_properties)[:, :3], np.array(mesh.tri_verts), process=False).export(path)
    return (x1 - x0, y1 - y0, z1 - z0)


def build():
    n = neck_world()
    hood, hood_size = camera_hood()
    head_station = PIVOT_STATIONS[1]
    # head coordinates -> world: the chosen pivot station lands on the yoke's pivot
    head_at = (0.0, NECK_Y - head_station, n["pivot_z"] + LUG_DROP)
    parts = {
        "head_front": (head_front(), head_at),
        "face_plate": (face_plate(), head_at),
        "head_back": (head_back(), head_at),
        "camera_hood": (hood, (head_at[0], head_at[1] + 2, head_at[2] + HEAD[1])),
        "base_frame": (base_frame(), (0, 0, 0)),
        "base_deck": (base_deck(), (0, 0, 0)),
        "drive_disc": (drive_disc(), (0, 0, 0)),
        "horn_hub": (horn_hub(), (0, 0, 0)),
    }
    return parts, hood_size


def main():
    found = problems()
    for p in found:
        print("DOESN'T FIT:", p)
    if sys.argv[1:] == ["check"]:
        raise SystemExit(1 if found else 0)
    parts, _ = build()
    out = HERE / "stl"
    out.mkdir(exist_ok=True)
    scene = {"parts": [], "mocks": []}
    for name, (m, at) in parts.items():
        rot, colour = PRINT[name]
        size = save(m, out / f"{name}.stl", rot)
        world = m.translate(at)
        save(world, out / f"_world_{name}.stl", (0, 0, 0))
        x0, y0, z0, x1, y1, z1 = world.bounding_box()
        scene["parts"].append({"name": name, "file": f"stl/_world_{name}.stl", "colour": colour,
                               "offset": [(x0 + x1) / 2, (y0 + y1) / 2, z0]})
        print(f"{name:12s} {size[0]:6.1f} x {size[1]:6.1f} x {size[2]:6.1f} mm   {m.volume() / 1000:5.1f} cm³")
    # stand-ins for the bought parts, for the picture
    n = neck_world()
    t = tilt_servo_x()
    lay = base_layout()
    mocks = [("pi", lay["pi"], "#2f8a46"), ("pi_ports", lay["pi_ports"], "#b9bcc0"), ("servo_board", lay["servo_board"][:4] + (FLOOR_T + STANDOFF, FLOOR_T + STANDOFF + 2), "#3d6db5"),
             ("amp", lay["amp"][:4] + (FLOOR_T, FLOOR_T + 3), "#6b3fa0"), ("speaker", lay["speaker"], "#1b1b1b"),
             ("pan_servo", pan_servo_box(), "#2f6fd8"),
             ("bearing", (-BEARING["square"] / 2, NECK_Y - BEARING["square"] / 2, BEARING["square"] / 2, NECK_Y + BEARING["square"] / 2,
                          n["deck_top"], n["disc_z"]), "#9aa0a6")]
    case_c = n["pivot_z"] - (SERVO["length"] / 2 - SERVO["shaft_from_end"])
    mocks.append(("tilt_servo", (t["tabs_in"] - SERVO["case_above_tabs"], NECK_Y - 6, t["body_out"], NECK_Y + 6,
                                 case_c - 11.5, case_c + 11.5), "#2f6fd8"))
    for name, b, colour in mocks:
        scene["mocks"].append({"name": name, "box": list(map(float, b)), "colour": colour})
    s = screen_layout()
    head_at = (0.0, NECK_Y - PIVOT_STATIONS[1], n["pivot_z"] + LUG_DROP)
    scene["screen"] = {"x": [s["pcb_x"][0] + SCREEN_MARGINS[0], s["pcb_x"][1] - SCREEN_MARGINS[1]],
                       "z": [head_at[2] + s["pcb_z"][0], head_at[2] + s["pcb_z"][1]], "y": head_at[1] + FACE_WALL - 1.5}
    (HERE / "scene.json").write_text(json.dumps(scene, indent=1))
    print("Wrote", out, "and scene.json")


if __name__ == "__main__":
    main()
