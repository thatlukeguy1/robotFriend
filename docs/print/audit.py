#!/usr/bin/env python3
"""
A second, independent check of the printed body: the whole robot assembled, with a stand-in for
every bought part, tested for collisions standing still, nodding and turning.

    python docs/print/audit.py

LESSON: why a second check?
===========================
make_parts.py's problems() checks the clearances it was written to think about. This file
doesn't trust that: it builds the real solids, puts a box or cylinder where every bought part
goes (screen, camera, mic, servos and their horns, bearing, Pi, boards, speaker), and measures
the volume where any two of them overlap. Then it moves the head through its whole nod and the
neck through its whole turn and does it again. Overlap = something would hit.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import make_parts as P  # noqa: E402
from make_parts import box, cyl_x, cyl_y, cyl_z  # noqa: E402

NOD = 20          # degrees, each way
TURN = 90         # degrees, each way
OVERLAP = 0.5     # mm³: more than this counts as a collision (parts that only touch overlap by ~0)


def head_inside():
    """Bought parts inside the head, in head coordinates."""
    s = P.screen_layout()
    c = P.chin_layout()
    fw = P.FACE_WALL
    x0, x1 = s["pcb_x"]; z0, z1 = s["pcb_z"]
    gw = s["glass"][0]
    lz = c["lens_z"]
    pcb_y = fw + P.SCREEN_GLASS_DEPTH
    cam_y = fw + P.CAMERA_LENS
    return {
        "screen glass": box(-gw / 2, fw, z0, gw / 2, pcb_y, z1),
        "screen board": box(x0, pcb_y, z0, x1, pcb_y + 1.6, z1),
        "screen pin header": box(x1 - 4, pcb_y + 1.6, z0 + 4, x1 - 1, pcb_y + 12.6, z1 - 4),
        "screen SD slot": box(x0 + 1, pcb_y + 1.6, z0 + 10, x0 + 28, pcb_y + 4.6, z1 - 10),
        "camera lens": box(-4.25, fw + 0.1, lz - 4.25, 4.25, cam_y, lz + 4.25),
        "camera board": box(-P.CAMERA[0] / 2, cam_y, c["board_bottom"], P.CAMERA[0] / 2, cam_y + 1, c["board_top"]),
        "camera ribbon plug": box(-10.5, cam_y + 1, c["board_bottom"], 10.5, cam_y + 4, c["board_bottom"] + 5.5),
        "mic board": cyl_y(P.MIC_BOARD, fw + 0.05, fw + 1.2, -P.CHIN_X, lz),
        "power light": cyl_y(5.0, fw + 0.5, fw + 9, P.CHIN_X, lz),
    }


def world_parts(tilt=0.0, pan=0.0):
    """Every solid, by name, in world coordinates, the head nodded by tilt and the neck turned by pan.
    Returns {name: (solid, group)}; group says what it's fixed to."""
    n = P.neck_world()
    t = P.tilt_servo_x()
    built, _ = P.build()
    head_at = (0.0, P.NECK_Y - P.PIVOT_STATIONS[1], n["pivot_z"] + P.LUG_DROP)
    pivot = (0.0, P.NECK_Y, n["pivot_z"])
    neck = (0.0, P.NECK_Y, 0.0)

    def nod(m):
        return m.translate((0, -pivot[1], -pivot[2])).rotate((tilt, 0, 0)).translate((0, pivot[1], pivot[2]))

    def turn(m):
        return m.translate((0, -neck[1], 0)).rotate((0, 0, pan)).translate((0, neck[1], 0))

    out = {}
    # the head and everything in it: nods and turns
    for name in ("head_front", "head_back", "face_plate"):
        out[name] = (turn(nod(built[name][0].translate(head_at))), "head")
    for name, m in head_inside().items():
        out[name] = (turn(nod(m.translate(head_at))), "head")
    out["tilt horn"] = (turn(nod(cyl_x(P.HORN["diameter"], P.LUG_X + P.LUG_T / 2, t["shaft_top"], P.NECK_Y, n["pivot_z"]))), "head")
    # the neck: turns
    out["drive_disc"] = (turn(built["drive_disc"][0]), "neck")
    out["horn_hub"] = (turn(built["horn_hub"][0]), "neck")
    case_c = n["pivot_z"] - (P.SERVO["length"] / 2 - P.SERVO["shaft_from_end"])
    cy = P.NECK_Y
    tilt_servo = P.union([
        box(t["shaft_top"] + 3, cy - 6, case_c - 11.5, t["tabs_in"], cy + 6, case_c + 11.5),           # case above the tabs
        box(t["tabs_in"], cy - 6, case_c - 16, t["arm_in"], cy + 6, case_c + 16),                      # tabs
        box(t["arm_in"], cy - 6, case_c - 11.5, t["body_out"], cy + 6, case_c + 11.5),                 # body, through the arm
        cyl_x(5.0, t["shaft_top"] + 0.5, t["shaft_top"] + 3.01, cy, n["pivot_z"])])                    # boss and shaft
    out["tilt servo"] = (turn(tilt_servo), "neck")
    out["pan horn"] = (turn(cyl_z(P.HORN["diameter"], n["hub_bottom"] - 1.5, n["hub_bottom"], 0, cy)), "neck")
    # the base: still
    out["base_frame"] = (built["base_frame"][0], "base")
    out["base_deck"] = (built["base_deck"][0], "base")
    q = P.BEARING["square"] / 2
    out["bearing"] = (box(-q, cy - q, n["deck_top"], q, cy + q, n["disc_z"]) - cyl_z(P.BEARING["hole"], n["deck_top"] - 1, n["disc_z"] + 1, 0, cy), "base")
    sx0, sy0, sx1, sy1, sz0, sz1 = P.pan_servo_box()
    tab = (P.SERVO["tabs"] - P.SERVO["length"]) / 2
    out["pan servo"] = (P.union([box(sx0, sy0, sz0, sx1, sy1, sz1),
                                 box(sx0 - tab, sy0, n["tabs_top"] - P.SERVO["tab_thick"], sx1 + tab, sy1, n["tabs_top"]),
                                 cyl_z(5.0, sz1, n["shaft_top"], 0, cy)]), "base")
    for name, b in P.base_layout().items():
        if name == "speaker_bracket":
            continue
        x0, y0, x1, y1, z0, z1 = b
        out[name.replace("_", " ")] = (box(x0, y0, z0, x1, y1, z1), "base")
    return out


# pairs that are meant to touch or overlap
ALLOWED = {frozenset(p) for p in [
    ("tilt horn", "tilt servo"),            # the horn sits on the shaft
    ("pan horn", "pan servo"),
    ("pan horn", "horn_hub"),
    ("pi ports", "pi"), ("pi power", "pi"),  # parts of the Pi
]}


def collisions(parts, only_between=None):
    """Pairs of solids that overlap by more than OVERLAP mm³."""
    names = list(parts)
    found = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if frozenset((a, b)) in ALLOWED:
                continue
            ga, gb = parts[a][1], parts[b][1]
            if only_between and {ga, gb} != set(only_between):
                continue
            ma, mb = parts[a][0], parts[b][0]
            ax0, ay0, az0, ax1, ay1, az1 = ma.bounding_box()
            bx0, by0, bz0, bx1, by1, bz1 = mb.bounding_box()
            if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0 or az1 < bz0 or bz1 < az0:
                continue
            v = (ma ^ mb).volume()
            if v > OVERLAP:
                found.append((a, b, round(v, 1)))
    return found


def audit(verbose=True):
    problems = []

    def say(*a):
        if verbose:
            print(*a)

    still = collisions(world_parts())
    for a, b, v in still:
        problems.append(f"standing still: {a} hits {b} ({v} mm³)")
    say(f"standing still: {len(still)} collisions")
    worst = []
    for tilt in range(-NOD, NOD + 1, 5):
        parts = world_parts(tilt=tilt)
        hits = collisions(parts, only_between=("head", "neck")) + collisions(parts, only_between=("head", "base"))
        for a, b, v in hits:
            problems.append(f"nodding {tilt:+d}°: {a} hits {b} ({v} mm³)")
        worst += hits
    say(f"nodding ±{NOD}°: {len(worst)} collisions")
    worst = []
    for pan in range(-TURN, TURN + 1, 15):
        for tilt in (-NOD, 0, NOD):
            parts = world_parts(tilt=tilt, pan=pan)
            hits = collisions(parts, only_between=("head", "base")) + collisions(parts, only_between=("neck", "base"))
            for a, b, v in hits:
                problems.append(f"turned {pan:+d}°, nodded {tilt:+d}°: {a} hits {b} ({v} mm³)")
            worst += hits
    say(f"turning ±{TURN}° (and nodding): {len(worst)} collisions")
    return problems


if __name__ == "__main__":
    found = audit()
    for p in found[:40]:
        print("  ", p)
    print("ALL CLEAR" if not found else f"{len(found)} PROBLEMS")
