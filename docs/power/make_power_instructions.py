#!/usr/bin/env python3
"""Draws Riley's power wiring as flat-pack style instructions: power-instructions.html,
one A4 landscape page per step. Then `node docs/power/print_power.js` makes the PNGs and the PDF.

    python docs/power/make_power_instructions.py

LESSON: everything is drawn from a few small part drawings (the supply, a lever connector,
the servo board...) that each say where their wires join ("anchors"). A page only places parts
and joins anchors with cables, so moving a part drags its wires along with it.
"""
import math
from pathlib import Path

HERE = Path(__file__).parent

INK, LIGHT, MID, DARK = "#1a1a1a", "#f4f4f2", "#d9d9d5", "#6b6b68"
RED, BLACK, ORANGE, COPPER = "#d33a2c", "#3a3a3a", "#f39a1e", "#c98a3a"
GOOD, BAD, NOTE = "#2e8b57", "#c62828", "#e0a800"
BOARD_BLUE, PI_GREEN, TERM_GREEN, METAL = "#4a78c0", "#4f9a5a", "#3aa55a", "#b9bcc0"
SW = 0.45  # line width (mm)
_ids = [0]


def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def rect(x, y, w, h, fill=LIGHT, r=0, sw=SW, stroke=INK, extra=""):
    return (f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="{f(r)}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{f(sw)}" {extra}/>')


def circle(x, y, r, fill=LIGHT, sw=SW, stroke=INK, extra=""):
    return f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{fill}" stroke="{stroke}" stroke-width="{f(sw)}" {extra}/>'


def line(x1, y1, x2, y2, sw=SW, stroke=INK, extra=""):
    return (f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" stroke="{stroke}" '
            f'stroke-width="{f(sw)}" stroke-linecap="round" {extra}/>')


def path(d, fill="none", sw=SW, stroke=INK, extra=""):
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{f(sw)}" stroke-linejoin="round" {extra}/>'


def text(x, y, s, size=3.2, anchor="start", weight="normal", fill=INK, mono=False):
    fam = ' font-family="DejaVu Sans Mono, Menlo, monospace" xml:space="preserve"' if mono else ""
    lines = s.split("\n")
    out = []
    for i, ln in enumerate(lines):
        out.append(f'<text x="{f(x)}" y="{f(y + i * size * 1.3)}" font-size="{f(size)}" text-anchor="{anchor}" '
                   f'font-weight="{weight}" fill="{fill}"{fam}>{ln.replace("&", "&amp;").replace("<", "&lt;")}</text>')
    return "".join(out)


def smooth(pts):
    """A smooth path through the points (Catmull-Rom turned into Bezier curves)."""
    p = [pts[0]] + list(pts) + [pts[-1]]
    d = f"M{f(pts[0][0])},{f(pts[0][1])}"
    for i in range(1, len(p) - 2):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (x1 + (x2 - x0) / 6, y1 + (y2 - y0) / 6)
        c2 = (x2 - (x3 - x1) / 6, y2 - (y3 - y1) / 6)
        d += f" C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(x2)},{f(y2)}"
    return d


def cable(pts, color, w=1.3):
    d = smooth(pts)
    return (path(d, sw=w + 0.7, stroke=INK, extra='stroke-linecap="round"') +
            path(d, sw=w, stroke=color, extra='stroke-linecap="round"'))


def arrow(x1, y1, x2, y2, color=INK, w=0.8):
    a = math.atan2(y2 - y1, x2 - x1)
    h = 2.6 + w
    p1 = (x2 - h * math.cos(a - 0.45), y2 - h * math.sin(a - 0.45))
    p2 = (x2 - h * math.cos(a + 0.45), y2 - h * math.sin(a + 0.45))
    bx, by = x2 - h * 0.8 * math.cos(a), y2 - h * 0.8 * math.sin(a)
    return (line(x1, y1, bx, by, w, color) +
            path(f"M{f(x2)},{f(y2)} L{f(p1[0])},{f(p1[1])} L{f(p2[0])},{f(p2[1])} Z", fill=color, sw=0.2, stroke=color))


def put(part, x, y, s=1.0):
    """Place a part drawn round (0, 0) at (x, y), scaled by s. Returns its SVG and its moved anchors."""
    svg, anchors = part
    return (f'<g transform="translate({f(x)},{f(y)}) scale({f(s)})">{svg}</g>',
            {k: (x + s * ax, y + s * ay) for k, (ax, ay) in anchors.items()})


# ===================================================================== the parts
def supply():
    """The 5 V plug-top supply, cable leaving its right side."""
    s = rect(0, 0, 34, 26, LIGHT, 3) + rect(-1.2, 5, 3, 16, MID, 1)
    s += text(17, 12, "5 V", 4.6, "middle", "bold") + text(17, 18, "4 A", 3.4, "middle")
    s += rect(30, 11, 5, 4, MID, 1)
    return s, {"cable": (35, 13), "slot": (-1, 13)}


def uk_clip():
    s = rect(0, 0, 13, 18, LIGHT, 2.5)
    s += rect(-5, 2.5, 5.5, 2.6, METAL, 0.5) + rect(-5, 9, 5.5, 2.2, METAL, 0.5) + rect(-5, 13.3, 5.5, 2.2, METAL, 0.5)
    s += text(6.5, 10.5, "UK", 3, "middle", "bold")
    return s, {"back": (13, 9)}


def barrel_plug(tip_x, tip_y, cable_pts, color=BLACK):
    """The supply's round plug, pointing right with its tip at (tip_x, tip_y)."""
    s = cable(list(cable_pts) + [(tip_x - 15, tip_y)], color, 1.6)
    s += rect(tip_x - 16, tip_y - 2.8, 11, 5.6, "#2b2b2b", 1.2)
    s += rect(tip_x - 5, tip_y - 1.9, 5, 3.8, METAL, 0.4)
    return s


def barrel_adapter():
    """The barrel-jack socket and its 2 screw terminals (wires go in on the right)."""
    s = rect(0, 2, 11, 8, "#2b2b2b", 1) + circle(0.6, 6, 3.2, "#2b2b2b", stroke=INK) + circle(0.6, 6, 1.1, METAL)
    s += rect(11, 0, 16, 12, TERM_GREEN, 1)
    for yy in (3.5, 8.5):
        s += circle(18, yy, 1.8, METAL) + line(16.9, yy - 0.9, 19.1, yy + 0.9, 0.35)
        s += rect(25.2, yy - 1.4, 1.8, 2.8, "#1f6b38", 0.3, 0.3)
    s += text(13.6, 4.8, "+", 3.4, "middle", "bold", "#fff") + text(13.6, 10, "−", 3.4, "middle", "bold", "#fff")
    return s, {"socket": (-1, 6), "plus_in": (27, 3.5), "minus_in": (27, 8.5),
               "plus_screw": (18, 3.5), "minus_screw": (18, 8.5)}


def fuse(length=34, label=True):
    """An inline fuse holder lying left to right: leads at a (left) and b (right)."""
    m = length / 2
    s = cable([(0, 0), (m - 8, 0)], RED) + cable([(m + 8, 0), (length, 0)], RED)
    s += rect(m - 8, -3.2, 16, 6.4, "#2b2b2b", 3) + line(m + 1, -3.2, m + 1, 3.2, 0.5, "#888")
    if label:
        s += text(m, -4.6, "fuse 4 A", 2.8, "middle")
    return s, {"a": (0, 0), "b": (length, 0)}


def wago(label, n=5):
    """A lever connector from above: wires go in along the bottom edge, levers on top."""
    w = 5 * n + 1
    s = rect(0, 0, w, 12, "#eef3f4", 1.5)
    anchors = {}
    for i in range(n):
        x = 3 + 5 * i
        s += rect(x - 1.9, -2.6, 3.8, 8, ORANGE, 0.8)
        s += circle(x, 8.6, 0.7, "#fff", 0.3)              # the little test hole for a meter probe
        s += rect(x - 1.4, 10.6, 2.8, 1.4, "#c7d1d4", 0.3, 0.3)
        anchors[f"s{i}"] = (x, 12)
        anchors[f"t{i}"] = (x, 8.6)
    s += text(w + 2, 8, label, 3.4, "start", "bold", RED if label == "+" else INK)
    return s, anchors


def wago_side(open_):
    """A lever connector from the side, the wire coming in from the left."""
    s = rect(0, 0, 18, 8, "#eef3f4", 1.2) + rect(0, 2.8, 1.6, 2.4, "#c7d1d4", 0.3, 0.3)
    ang = 38 if open_ else 0
    s += f'<g transform="rotate({ang} 17 0)">' + rect(3, -2.2, 14.5, 2.6, ORANGE, 1) + "</g>"
    return s, {"hole": (0, 4)}


def stripped_wire(x, y, length, color, strip=11):
    s = rect(x, y - 1.3, length, 2.6, color, 1.2)
    if not strip:
        return s
    s += rect(x + length, y - 0.85, strip, 1.7, COPPER, 0.6, 0.3)
    for k in range(4):
        s += line(x + length + 1 + k * 2.4, y - 0.8, x + length + 2.6 + k * 2.4, y + 0.8, 0.25, "#8a5a1e")
    return s


def capacitor(reversed_=False, legs=(12, 12)):
    """The 1000 uF capacitor standing up; its stripe marks the minus leg."""
    body = "#2f4f86"
    s = rect(-4.5, 0, 9, 14, body, 1.8)
    sx = -4.5 if reversed_ else 1.6
    s += rect(sx, 0.3, 2.9, 13.4, "#cfd4dc", 0.6, 0.25)
    for k in range(3):
        s += line(sx + 0.8, 3 + k * 4, sx + 2.1, 3 + k * 4, 0.45, body)
    s += path("M-4.5,1.8 Q0,-1 4.5,1.8", fill="none", sw=0.35, stroke="#9fb2d6")
    plus_x, minus_x = (3, -3) if reversed_ else (-3, 3)
    s += line(plus_x, 14, plus_x, 14 + legs[0], 0.6, "#8d9196") + line(minus_x, 14, minus_x, 14 + legs[1], 0.6, "#8d9196")
    return s, {"plus": (plus_x, 14 + legs[0]), "minus": (minus_x, 14 + legs[1])}


def pca9685():
    """The 16-channel servo board, seen from above, power terminal on its top edge."""
    s = rect(0, 0, 62, 26, BOARD_BLUE, 1.5)
    s += rect(29, 8, 10, 10, "#1e1e1e", 0.6) + text(34, 22.5, "PCA9685", 2.2, "middle", "bold", "#fff")
    s += rect(25, -6.5, 13, 7.5, TERM_GREEN, 0.8)
    for x in (28.2, 34.8):
        s += circle(x, -2.8, 1.7, METAL) + line(x - 0.9, -3.7, x + 0.9, -1.9, 0.35)
        s += rect(x - 1.2, -6.5, 2.4, 1.2, "#1f6b38", 0.3, 0.3)
    s += text(28.2, 3.6, "V+", 2.2, "middle", "bold", "#fff") + text(34.8, 3.6, "GND", 2.2, "middle", "bold", "#fff")
    for i in range(16):                                    # 16 servo plugs: 3 pins each
        x = 46 + (i % 4) * 3.4 if i < 4 else None
    for i in range(12):
        x = 44 + (i % 6) * 2.9
        y = 5 + (i // 6) * 8
        for r in range(3):
            s += rect(x - 0.6, y + r * 2.2, 1.2, 1.2, "#e9e9e9", 0, 0.2)
    labels = ["GND", "OE", "SCL", "SDA", "VCC", "V+"]
    anchors = {"vplus": (28.2, -6.5), "gnd": (34.8, -6.5), "vplus_screw": (28.2, -2.8), "gnd_screw": (34.8, -2.8)}
    for i, lab in enumerate(labels):
        y = 4.5 + i * 3.2
        s += line(-3.2, y, 2, y, 0.9, "#d6b44a") + rect(1.2, y - 1.1, 2.2, 2.2, "#1e1e1e", 0.2, 0.2)
        s += text(4.5, y + 0.9, lab, 2.2, "start", "bold", "#fff")
        anchors[lab] = (-3.2, y)
    return s, anchors


def pi4(s_led=False):
    """The Pi 4 from above: USB sockets on the right, GPIO header along the top, USB-C power at bottom left."""
    s = rect(0, 0, 85, 56, PI_GREEN, 3)
    for hx, hy in ((3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)):
        s += circle(hx, hy, 1.4, "#e8e8e8", 0.3)
    s += rect(7, 0.6, 51, 5.2, "#222", 0.4, 0.2)
    for n in range(1, 41):
        x, y = pi_pin(n)
        s += rect(x - 0.55, y - 0.55, 1.1, 1.1, "#d6b44a", 0, 0.15)
    s += rect(26, 18, 15, 15, "#bfc3c7", 0.8) + text(33.5, 27, "Pi 4", 2.6, "middle", "bold")
    s += rect(66, 2, 21, 15, METAL, 0.8) + rect(69, 21, 18, 14, METAL, 0.8) + rect(69, 39, 18, 14, METAL, 0.8)
    s += rect(6.5, 52.5, 9, 4, METAL, 1.4) + rect(22, 53, 7, 3.4, METAL, 0.6) + rect(35, 53, 7, 3.4, METAL, 0.6)
    s += text(11, 51, "USB-C", 2, "middle", "bold", "#fff")
    led = "#5cff7a" if s_led else "#2d4a33"
    s += circle(3, 46, 1, led, 0.25) + circle(3, 42.5, 1, "#ff5a4a" if s_led else "#4a2d2d", 0.25)
    if s_led:
        s += circle(3, 46, 2.6, "none", 0.4, "#5cff7a", 'opacity="0.6"')
    return s, {"usbc": (11, 56.5)}


def pi_pin(n):
    """Where GPIO pin n sits on pi4(): odd pins on the inner row, even pins along the edge."""
    col = (n - 1) // 2
    return 8.27 + col * 2.54, (4.3 if n % 2 else 1.9)


def pigtail():
    """USB-C plug on a lead to 2 screw terminals; plug points up."""
    s = cable([(0, 9), (0, 16), (-1, 21)], BLACK, 1.6)
    s += rect(-3.2, 0, 6.4, 9, "#2b2b2b", 1.4) + rect(-2.4, -3.2, 4.8, 3.4, METAL, 1)
    s += rect(-8, 21, 16, 10, TERM_GREEN, 1)
    for x in (-3.8, 3.8):
        s += circle(x, 25, 1.7, METAL) + line(x - 0.9, 24.1, x + 0.9, 25.9, 0.35)
        s += rect(x - 1.2, 29.8, 2.4, 1.2, "#1f6b38", 0.3, 0.3)
    s += text(-3.8, 29.4, "+", 2.6, "middle", "bold", "#fff") + text(3.8, 29.4, "−", 2.6, "middle", "bold", "#fff")
    return s, {"tip": (0, -3.2), "plus": (-3.8, 31), "minus": (3.8, 31), "plus_screw": (-3.8, 25), "minus_screw": (3.8, 25)}


def meter(reading):
    s = rect(0, 0, 30, 46, "#f2c230", 3.5) + rect(2.5, 2.5, 25, 41, "#3a3a3a", 2.5, 0.3)
    s += rect(4.5, 4.5, 21, 10, "#cfdac4", 1)
    s += text(24, 12.4, reading, 6.2, "end", "bold", "#1d2a1d", mono=True)
    s += circle(15, 26, 7.2, "#e6e6e6") + line(15, 26, 15 + 6 * math.cos(-1.1), 26 + 6 * math.sin(-1.1), 1.1)
    s += text(23.5, 19.6, "V⎓", 2.6, "start", "bold", "#fff")
    s += circle(9, 39.5, 1.8, "#111", 0.3) + circle(21, 39.5, 1.8, RED, 0.3)
    s += text(9, 36.2, "COM", 1.8, "middle", "bold", "#fff") + text(21, 36.2, "V", 1.8, "middle", "bold", "#fff")
    return s, {"com": (9, 39.5), "v": (21, 39.5)}


def probe(socket, tip, color, sag=6):
    """A meter probe touching tip; its handle points back toward the meter's socket."""
    vx, vy = socket[0] - tip[0], socket[1] - tip[1]
    d = math.hypot(vx, vy) or 1
    dx, dy = vx / d, vy / d
    n_end = (tip[0] + dx * 3, tip[1] + dy * 3)
    h_end = (tip[0] + dx * 13, tip[1] + dy * 13)
    mid = ((h_end[0] + socket[0]) / 2, (h_end[1] + socket[1]) / 2 + sag)
    s = cable([h_end, (h_end[0] + dx * 4, h_end[1] + dy * 4), mid, socket], color, 0.9)
    s += line(n_end[0], n_end[1], h_end[0], h_end[1], 2.8, INK) + line(n_end[0], n_end[1], h_end[0], h_end[1], 2.0, color)
    s += line(tip[0], tip[1], n_end[0], n_end[1], 0.7, "#777")
    s += circle(socket[0], socket[1], 1.5, color, 0.3)
    return s


def servo():
    s = rect(-16, -6, 32, 12, "#2b2b2b", 1) + rect(-11.5, -6, 23, 12, "#3c5fa0", 1.2)
    s += circle(-1.5 - 3.5, 0, 3.4, "#e8e8e8") + circle(-5, 0, 1.2, METAL)
    s += circle(-14, 0, 1, "#fff", 0.3) + circle(14, 0, 1, "#fff", 0.3)
    s += cable([(11.5, 3), (18, 6), (22, 3)], "#c47a2a", 1.0)
    return s, {}


def jumper(color, length=40):
    s = cable([(5, 0), (length * 0.4, 5), (length * 0.7, -4), (length - 5, 0)], color, 1.0)
    s += rect(0, -1.6, 6, 3.2, "#222", 0.4) + rect(length - 6, -1.6, 6, 3.2, "#222", 0.4)
    return s, {}


def heatshrink():
    s = rect(0, 0, 18, 3.2, "#222", 1.2) + rect(0, 6, 14, 4.2, RED, 1.6) + rect(0, 13, 10, 5, "#222", 2)
    return s, {}


def wire_coil(color):
    s = ""
    for k in range(4):
        s += f'<ellipse cx="{f(k * 1.6)}" cy="0" rx="9" ry="5.5" fill="none" stroke="{INK}" stroke-width="2.1"/>'
        s += f'<ellipse cx="{f(k * 1.6)}" cy="0" rx="9" ry="5.5" fill="none" stroke="{color}" stroke-width="1.4"/>'
    return s, {}


# ===================================================================== icons and page furniture
def ok(x, y, r=4.5):
    return circle(x, y, r, "#fff", 0.9, GOOD) + path(f"M{f(x - r * .45)},{f(y)} L{f(x - r * .1)},{f(y + r * .4)} L{f(x + r * .5)},{f(y - r * .4)}", sw=1.1, stroke=GOOD)


def no(x, y, r=4.5):
    k = r * 0.4
    return circle(x, y, r, "#fff", 0.9, BAD) + line(x - k, y - k, x + k, y + k, 1.1, BAD) + line(x - k, y + k, x + k, y - k, 1.1, BAD)


def bang(x, y, r=4.5):
    return (path(f"M{f(x)},{f(y - r)} L{f(x + r)},{f(y + r * .8)} L{f(x - r)},{f(y + r * .8)} Z", "#fff", 0.9, NOTE) +
            text(x, y + r * .55, "!", r * 1.1, "middle", "bold", NOTE))


def plug_icon(x, y, live):
    """A wall plug: live = plugged in (lightning), otherwise crossed out (unplugged)."""
    c = NOTE if live else BAD
    s = circle(x, y, 6, "#fff", 0.8, c)
    s += rect(x - 2.6, y - 1.5, 5.2, 4.6, INK, 0.8) + line(x - 1.3, y - 1.5, x - 1.3, y - 3.6, 0.7) + line(x + 1.3, y - 1.5, x + 1.3, y - 3.6, 0.7)
    s += line(x, y + 3.1, x, y + 4.8, 0.7)
    if live:
        s += path(f"M{f(x + 3.4)},{f(y - 4.6)} L{f(x + 2.2)},{f(y - 1.6)} L{f(x + 3.6)},{f(y - 1.6)} L{f(x + 2.4)},{f(y + 1.4)}", sw=0.6, stroke=c)
    else:
        s += line(x - 4.2, y + 4.2, x + 4.2, y - 4.2, 0.9, c)
    s += text(x, y + 9.6, "plugged in" if live else "unplugged", 2.6, "middle", "bold", c)
    return s


def panel(x, y, w, h, n=None):
    s = rect(x, y, w, h, "none", 3, 0.35, "#9a9a96")
    if n:
        s += circle(x + 5.5, y + 5.5, 3.6, INK, 0) + text(x + 5.5, y + 6.8, str(n), 3.6, "middle", "bold", "#fff")
    return s


def caption(x, y, s, size=3.3, anchor="start", weight="normal", fill=INK):
    return text(x, y, s, size, anchor, weight, fill)


def zoom(cx, cy, r, fx, fy, k, content, src=None):
    """A round magnifier at (cx, cy) showing content k times bigger around (fx, fy)."""
    _ids[0] += 1
    cid = f"z{_ids[0]}"
    s = ""
    if src:
        a = math.atan2(src[1] - cy, src[0] - cx)
        s += line(src[0], src[1], cx + r * math.cos(a), cy + r * math.sin(a), 0.35, DARK, 'stroke-dasharray="1.2 1"')
        s += circle(src[0], src[1], 2.2 * 1.0, "none", 0.35, DARK)
    s += f'<clipPath id="{cid}"><circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}"/></clipPath>'
    s += circle(cx, cy, r, "#fff", 0)
    s += f'<g clip-path="url(#{cid})"><g transform="translate({f(cx)},{f(cy)}) scale({f(k)}) translate({f(-fx)},{f(-fy)})">{content}</g></g>'
    s += circle(cx, cy, r, "none", 0.7, INK)
    return s


PAGES = []


def page(title, body, step=None):
    head = ""
    if step is not None:
        head += text(12, 25, str(step), 17, "start", "bold")
        head += text(27 if step < 10 else 35, 18.5, title, 6, "start", "bold")
    else:
        head += text(12, 22, title, 8, "start", "bold")
    PAGES.append((head, body))


# ===================================================================== shared layouts
def rail_layout(ox, oy, plugged=False):
    """Adapter, fuse and the two lever connectors, as wired in step 3. Returns svg and anchors."""
    out = ""
    ad_svg, ad = put(barrel_adapter(), ox, oy)
    fu_svg, fu = put(fuse(), ox + 46, oy - 12)
    rp_svg, rp = put(wago("+"), ox + 104, oy - 38)
    rm_svg, rm = put(wago("GND"), ox + 104, oy - 2)
    if plugged:
        out += barrel_plug(ad["socket"][0] + 4, ad["socket"][1], [(ox - 30, oy - 18), (ox - 16, oy + 4), (ad["socket"][0] - 12, ad["socket"][1])])
    out += cable([ad["plus_in"], (ox + 34, oy + 3.5), (ox + 40, oy - 10), fu["a"]], RED)
    out += cable([fu["b"], (ox + 92, oy - 12), (rp["s0"][0], oy - 18), rp["s0"]], RED)
    out += cable([ad["minus_in"], (ox + 36, oy + 9), (ox + 70, oy + 18), (rm["s0"][0] - 2, oy + 18), rm["s0"]], BLACK)
    out += ad_svg + fu_svg + rp_svg + rm_svg
    return out, {"ad": ad, "rp": rp, "rm": rm}


# ===================================================================== cover
def cover():
    b = text(12, 40, "One supply for the whole robot. Every part takes its power from the rail, never through another part.", 4)
    b += text(12, 50, "You need:", 3.4, "start", "bold")
    b += text(32, 50, "small screwdriver · wire strippers · multimeter · soldering iron + heat-shrink", 3.4)
    b += text(12, 57, "About 45 minutes. Each step ends with a check: don't move on until it passes.", 3.4, "start", "normal", DARK)
    lay, a = rail_layout(40, 135, plugged=False)
    su_svg, su = put(supply(), 14, 74)
    b += su_svg + barrel_plug(a["ad"]["socket"][0] + 4, a["ad"]["socket"][1], [su["cable"], (56, 96), (30, 116), (24, 135)])
    b += lay
    pc_svg, pc = put(pca9685(), 194, 152, 0.9)
    rp, rm = a["rp"], a["rm"]
    b += cable([rp["s1"], (rp["s1"][0], 116), (180, 116), (pc["vplus"][0] - 2, 128), pc["vplus"]], RED)
    b += cable([rm["s1"], (rm["s1"][0], 153), (200, 142), (pc["gnd"][0] + 3, 139), pc["gnd"]], BLACK)
    pi_svg, pi = put(pi4(True), 228, 62, 0.62)
    pt_svg, pt = put(pigtail(), pi["usbc"][0], pi["usbc"][1] + 2.6 * 0.8 + 0.6, 0.8)
    b += cable([rp["s3"], (rp["s3"][0], 112), (200, 108), (pt["plus"][0], 122), pt["plus"]], RED, 1.1)
    b += cable([rm["s3"], (rm["s3"][0], 152), (216, 136), (pt["minus"][0] + 5, 127), pt["minus"]], BLACK, 1.1)
    b += pc_svg + pi_svg + pt_svg
    b += caption(31, 106, "supply", 3, "middle") + caption(rp["s0"][0] - 2, 91, "the rail", 3, "start", "bold")
    b += caption(pc["vplus"][0] + 3, 183, "servo board", 3, "middle") + caption(262, 58, "Pi", 3, "middle", "bold")
    b += caption(256, 120, "USB-C lead", 2.8, "start")
    page("Riley · the power rail", b)


# ===================================================================== parts
def parts():
    b = ""
    cells = [
        ("A", "5 V 4 A supply", "1", put(supply(), -17, -13)),
        ("B", "UK plug clip", "1", put(uk_clip(), -4, -9)),
        ("C", "barrel-jack adapter", "1", put(barrel_adapter(), -13, -6)),
        ("D", "fuse holder + 4 A fuse", "1", put(fuse(40, False), -20, 0)),
        ("E", "lever connector, 5-way", "2", put(wago(""), -13, -5)),
        ("F", "20 AWG wire, red + black", "", None),
        ("G", "1000 µF capacitor", "1", put(capacitor(legs=(12, 9)), 0, -13)),
        ("H", "USB-C power lead", "1", put(pigtail(), 0, -14)),
        ("I", "servo board (PCA9685)", "1", put(pca9685(), -31, -10)),
        ("J", "jumper wires, F-F", "4", None),
        ("K", "heat-shrink", "", put(heatshrink(), -9, -9)),
        ("", "servos: NOT yet", "", put(servo(), 0, 0)),
    ]
    for i, (letter, name, count, drawn) in enumerate(cells):
        cx = 12 + (i % 4) * 69
        cy = 34 + (i // 4) * 56
        b += rect(cx, cy, 65, 52, "none", 3, 0.35, "#9a9a96")
        mx, my = cx + 32.5, cy + 24
        if letter == "F":
            b += put(wire_coil(RED), mx - 12, my, 1)[0] + put(wire_coil(BLACK), mx + 8, my, 1)[0]
        elif letter == "J":
            for k, c in enumerate(("#e07b00", INK, "#2f6fd0", "#e3c21a")):
                b += put(jumper(c, 40), mx - 20, my - 9 + k * 6)[0]
        else:
            b += f'<g transform="translate({f(mx)},{f(my)})">{drawn[0]}</g>'
        if letter:
            b += circle(cx + 6, cy + 6, 3.8, INK, 0) + text(cx + 6, cy + 7.3, letter, 3.8, "middle", "bold", "#fff")
        if count:
            b += text(cx + 60, cy + 8, f"× {count}", 4, "end", "bold")
        b += text(cx + 32.5, cy + 47, name, 3, "middle")
        if not letter:
            b += no(mx + 20, my - 12, 4)
    page("What's in the box", b)


# ===================================================================== step 1
def step1():
    b = panel(12, 34, 88, 128, 1) + panel(104, 34, 88, 128, 2) + panel(196, 34, 89, 128, 3)
    # 1: clip on
    cl_svg, cl = put(uk_clip(), 24, 70)
    su_svg, su = put(supply(), 58, 66)
    b += cl_svg + su_svg + arrow(39, 79, 55, 79, INK, 1)
    b += barrel_plug(92, 128, [su["cable"], (98, 92), (90, 116), (66, 128)])
    b += caption(18, 148, "Slide the UK clip into the supply\nuntil it clicks.")
    # 2: plug into the adapter
    ad_svg, ad = put(barrel_adapter(), 150, 92)
    b += ad_svg + barrel_plug(140, 98, [(108, 72), (116, 92), (124, 98)])
    b += arrow(126, 90, 143, 90, INK, 1)
    b += caption(110, 148, "Push the round plug into\nthe adapter's socket.")
    # 3: plug in and measure
    ad_svg, ad = put(barrel_adapter(), 228, 64)
    b += barrel_plug(ad["socket"][0] + 4, ad["socket"][1], [(200, 50), (212, 70)]) + ad_svg
    me_svg, me = put(meter("5.08"), 256, 92, 0.75)
    b += me_svg + probe(me["v"], ad["plus_screw"], RED) + probe(me["com"], ad["minus_screw"], INK)
    b += plug_icon(270, 52, True) + ok(220, 118)
    b += caption(202, 148, "Plug in. Meter on DC volts (20 V).\nRed on +, black on −: 5.0 to 5.2 V.")
    # if it's negative
    b += rect(12, 167, 273, 28, "none", 3, 0.35, "#9a9a96")
    sm_svg, _ = put(meter("-5.08"), 22, 170, 0.48)
    b += sm_svg + bang(44, 180)
    b += caption(52, 178, "Reads −5.08? The adapter's labels are the wrong way round. Mark the screw that's really + with red tape,\n"
                          "and use THAT one as + from now on.", 3.2)
    b += plug_icon(272, 180, False) + caption(258, 193.5, "", 2)
    b += caption(196, 192, "Unplug before step 2 →", 3.2, "start", "bold")
    page("The supply on its own", b, 1)


# ===================================================================== step 2
def step2():
    b = panel(12, 34, 88, 128, 1) + panel(104, 34, 88, 128, 2) + panel(196, 34, 89, 128, 3)
    b += stripped_wire(24, 80, 44, RED) + stripped_wire(24, 100, 44, BLACK)
    b += line(68, 88, 68, 74, 0.3) + line(79, 88, 79, 74, 0.3) + arrow(73.5, 76, 79, 76, INK, 0.3) + arrow(73.5, 76, 68, 76, INK, 0.3)
    b += text(73.5, 72, "11 mm", 3, "middle", "bold")
    b += caption(18, 140, "Strip 11 mm off the end.\nTwist the strands tight so\nnone stick out.")
    # 2: lever up, wire in
    ws, w = put(wago_side(True), 140, 84, 2.4)
    b += ws + stripped_wire(108, w["hole"][1], 14, RED) + arrow(124, w["hole"][1] - 8, 136, w["hole"][1] - 8, INK, 0.9)
    b += arrow(176, 64, 176, 54, ORANGE, 1)
    b += caption(110, 140, "Lift the orange lever.\nPush the bare end in\nall the way.")
    # 3: lever down, tug
    ws, w = put(wago_side(False), 236, 84, 2.4)
    b += stripped_wire(198, w["hole"][1], 38, RED, 0) + ws
    b += rect(218, w["hole"][1] - 0.85, 18, 1.7, COPPER, 0.6, 0.3, extra='opacity="0"')
    b += arrow(268, 70, 268, 80, ORANGE, 1) + arrow(214, w["hole"][1] + 9, 202, w["hole"][1] + 9, INK, 0.9)
    b += ok(276, 110)
    b += caption(202, 140, "Press the lever down.\nTug the wire: it must not move.\nNo copper showing outside.")
    b += rect(12, 167, 273, 28, "none", 3, 0.35, "#9a9a96") + bang(24, 180)
    b += caption(32, 178, "Every wire into a lever connector or screw terminal is done this way. Screw terminals: strip 6 mm instead,\n"
                          "loosen the screw, push the wire in, tighten until a tug doesn't move it.", 3.2)
    page("Strip and clamp", b, 2)


# ===================================================================== step 3
def step3():
    b = panel(12, 34, 273, 108, 1)
    lay, a = rail_layout(42, 96)
    b += lay + plug_icon(270, 50, False)
    b += caption(18, 126, "Red: the adapter's + → the fuse → the + connector.     Black: the adapter's − → the GND connector.\n"
                          "Short wires, about 10 cm each. Push the 4 A fuse into its holder.", 3.3)
    # the join, in three little pictures
    b += panel(12, 146, 273, 49, 2)
    x0 = 30
    for k in range(3):
        bx = x0 + k * 88
        b += stripped_wire(bx, 168, 22, RED, 0)
        b += stripped_wire(bx + 54, 168, 22, RED, 0).replace(f'x="{f(bx + 54)}"', f'x="{f(bx + 54)}"')
        if k == 0:
            b += rect(bx + 4, 165.4, 12, 5.2, "#222", 1.4)
            b += arrow(bx + 12, 160, bx + 4, 160, INK, 0.7)
            b += stripped_wire(bx + 22, 168, 0, RED, 10) + rect(bx + 44, 166.8, 10, 2.4, COPPER, 0.5, 0.3)
            b += caption(bx, 186, "Slide heat-shrink on first.", 3)
        elif k == 1:
            b += rect(bx + 2, 165.4, 12, 5.2, "#222", 1.4)
            b += rect(bx + 22, 166.8, 32, 2.4, COPPER, 0.6, 0.3)
            b += path(f"M{f(bx + 36)},{f(168)} l3,-9 l3,1", sw=0.8) + rect(bx + 40, 156, 16, 4, "#bbb", 1.5)
            b += caption(bx, 186, "Twist the ends together, solder.", 3)
        else:
            b += rect(bx + 22, 165.8, 32, 4.4, "#222", 1.6)
            for j in range(3):
                b += path(f"M{f(bx + 30 + j * 8)},{f(162)} q-1.5,-2.5 0,-5 q1.5,-2.5 0,-5", sw=0.6, stroke=BAD)
            b += ok(bx + 66, 160, 3.6)
            b += caption(bx, 186, "Slide it over the join, heat it.", 3)
    b += text(270, 186, "or put the fuse's\nleads straight into\nthe connectors", 2.6, "end", "normal", DARK)
    page("The fuse and the rail", b, 3)


# ===================================================================== step 4
def step4():
    b = panel(12, 34, 273, 161)
    lay, a = rail_layout(42, 120, plugged=True)
    b += lay
    me_svg, me = put(meter("5.08"), 218, 104)
    b += me_svg + probe(me["v"], a["rp"]["t4"], RED) + probe(me["com"], a["rm"]["t4"], INK)
    b += plug_icon(270, 50, True) + ok(258, 168)
    b += caption(20, 178, "Plug in. Probe tips in the little test holes on top of the connectors:\n"
                          "red in a + hole, black in a GND hole. You want 5.0 to 5.2 V.", 3.4)
    b += caption(20, 190, "Nothing? Check the fuse is in, and every lever is down.   Then unplug.", 3.2, "start", "bold")
    page("Check the rail", b, 4)


# ===================================================================== step 5
def step5():
    b = panel(12, 34, 180, 161, 1) + panel(196, 34, 89, 78, 2) + panel(196, 116, 89, 79, 3)
    rp_svg, rp = put(wago("+"), 28, 62)
    rm_svg, rm = put(wago("GND"), 28, 98)
    pc_svg, pc = put(pca9685(), 92, 140)
    cap_svg, cap = put(capacitor(legs=(13, 13)), pc["vplus"][0] + 3, pc["vplus"][1] - 27)
    wires = cable([rp["s1"], (36, 84), (70, 88), (108, 118), (pc["vplus"][0] - 3, pc["vplus"][1] - 7), pc["vplus"]], RED)
    wires += cable([rm["s1"], (36, 122), (66, 126), (104, 124), (pc["gnd"][0] + 6, pc["gnd"][1] - 9), pc["gnd"]], BLACK)
    scene = wires + pc_svg + cap_svg
    b += rp_svg + rm_svg + scene + plug_icon(178, 48, False)
    b += caption(18, 178, "From each connector to the servo board's green terminal: red to V+, black to GND.\n"
                          "Clamp the capacitor's legs in the SAME two holes, with the wires.", 3.2)
    focus = (pc["vplus"][0] + 3.3, pc["vplus"][1] - 6)
    b += zoom(166, 82, 24, focus[0], focus[1], 2.6, scene, src=focus)
    # 2: which leg is which
    cs, c = put(capacitor(legs=(16, 12)), 226, 50)
    b += cs + caption(c["plus"][0] - 2, c["plus"][1] + 4, "long leg\n= V+", 2.8, "end", "bold", RED)
    b += caption(c["minus"][0] + 2, c["minus"][1] + 8, "stripe side\n= GND", 2.8, "start", "bold")
    b += ok(276, 52) + caption(244, 106, "", 2)
    # 2b: wrong way
    cs2, c2 = put(capacitor(True, legs=(10, 10)), 262, 72, 0.7)
    b += cs2 + no(274, 70, 3.4)
    star = " ".join(f"{f(262 + (5 if i % 2 else 9) * math.cos(i * math.pi / 8))},{f(80 + (5 if i % 2 else 9) * math.sin(i * math.pi / 8))}" for i in range(16))
    b += f'<polygon points="{star}" fill="#ffe066" stroke="{BAD}" stroke-width="0.5" opacity="0.85"/>'
    b += text(262, 81.5, "POP", 3, "middle", "bold", BAD)
    b += caption(202, 107, "Backwards, it can pop.", 3, "start", "bold", BAD)
    # 3: check
    pc2_svg, pc2 = put(pca9685(), 206, 132, 0.55)
    me_svg, me = put(meter("5.06"), 246, 140, 0.6)
    b += pc2_svg + me_svg + probe(me["v"], pc2["vplus_screw"], RED) + probe(me["com"], pc2["gnd_screw"], INK)
    b += plug_icon(274, 128, True) + ok(232, 166, 3.6)
    b += caption(240, 178, "", 2) + caption(202, 186, "Plug in: 5 V across the terminal.\nThen unplug.", 3)
    page("Power to the servo board", b, 5)


# ===================================================================== step 6
def step6():
    b = panel(12, 34, 88, 161, 1) + panel(104, 34, 88, 161, 2) + panel(196, 34, 89, 161, 3)
    # 1: shut down, official charger out
    pi_svg, pi = put(pi4(), 18, 62, 0.88)
    b += pi_svg
    b += rect(38, 140, 24, 16, "#fff", 2.5) + cable([(50, 140), (50, 130), (pi["usbc"][0], 124), pi["usbc"]], "#e8e8e8", 1.4)
    b += no(70, 138) + text(50, 165, "official charger", 2.8, "middle")
    b += caption(18, 178, "Shut Riley down properly.\nUnplug the official charger:\nit's not needed any more.", 3.1)
    # 2: lead on the rail, measure before it goes in
    rp_svg, rp = put(wago("+"), 116, 54, 0.9)
    rm_svg, rm = put(wago("GND"), 116, 74, 0.9)
    pt_svg, pt = put(pigtail(), 140, 100)
    b += cable([rp["s0"], (rp["s0"][0], 70), (110, 82), (111, 120), (124, 142), (pt["plus"][0], 140), pt["plus"]], RED)
    b += cable([rm["s0"], (rm["s0"][0], 96), (124, 128), (134, 146), (pt["minus"][0] + 3, 141), pt["minus"]], BLACK)
    b += rp_svg + rm_svg + pt_svg
    me_svg, me = put(meter("5.08"), 162, 112, 0.6)
    b += me_svg + probe(me["v"], pt["plus_screw"], RED) + probe(me["com"], pt["minus_screw"], INK)
    b += plug_icon(184, 50, True) + ok(160, 90, 3.6)
    b += caption(110, 178, "USB-C lead: + to red, − to black.\nPlug in and measure 5 V at its\nscrews BEFORE it goes in the Pi.", 3.1)
    # 3: into the Pi
    pi_svg, pi = put(pi4(True), 204, 62, 0.88)
    pt_svg, pt = put(pigtail(), 214, 126)
    b += pi_svg + pt_svg + arrow(pt["tip"][0] + 6, 124, pi["usbc"][0] + 6, pi["usbc"][1] + 4, INK, 0.9)
    b += plug_icon(276, 140, True) + ok(276, 160, 3.6)
    b += caption(202, 178, "Unplug, push the USB-C into\nthe Pi, plug in again.\nShe boots as normal.", 3.1)
    page("Power to the Pi", b, 6)


# ===================================================================== step 7
def step7():
    b = panel(12, 34, 273, 161)
    b += plug_icon(270, 50, False) + text(270, 66, "Pi OFF", 2.8, "middle", "bold", BAD)
    # the header, big: pins 1 to 26 (USB sockets off to the right)
    X, Y, P = 52, 62, 8.0
    used = {1: "mic", 2: "amp", 4: "screen", 6: "amp", 9: "mic", 12: "sound", 14: "button", 15: "touch", 16: "screen",
            18: "screen", 19: "screen", 20: "screen", 21: "touch", 22: "screen", 23: "screen", 24: "screen", 26: "touch"}
    wanted = {3: ("SDA", "#2f6fd0"), 5: ("SCL", "#e3c21a"), 17: ("VCC", "#e07b00"), 25: ("GND", INK)}
    b += rect(X - 6, Y - 6, 13 * P + 4, 20, "#222", 1.2)
    b += line(X - 10, Y - 9, X + 13 * P + 4, Y - 9, 0.4, DARK, 'stroke-dasharray="2 1.4"')
    b += text(X + 13 * P + 6, Y - 8, "board edge", 2.6, "start", "normal", DARK)
    b += text(X + 13 * P + 6, Y + 2, "USB sockets\nthis way →", 2.6, "start", "normal", DARK)
    pin = {}
    for n in range(1, 27):
        col = (n - 1) // 2
        x, y = X + col * P, (Y + P if n % 2 else Y)
        pin[n] = (x, y)
        fill = wanted[n][1] if n in wanted else ("#8d8d8d" if n in used else "#d6b44a")
        b += rect(x - 2, y - 2, 4, 4, fill, 0.4, 0.3, "#000")
        if n % 2 == 0:
            b += text(x, y - 3.6 - 6, str(n), 2.4, "middle", "normal", "#bbb")
        else:
            b += text(x, y + 6.4 + 6, str(n), 2.4, "middle", "bold" if n in wanted else "normal", INK if n in wanted else DARK)
    b += text(X - 10, Y + P + 1, "inner\nrow", 2.4, "end", "normal", DARK)
    # the servo board and its 4 jumpers
    pc_svg, pc = put(pca9685(), 64, 150, 1.25)
    for n, (lab, col) in wanted.items():
        px, py = pin[n]
        hx, hy = pc[lab]
        b += cable([(hx, hy), (hx - 12 - (n % 7), hy), (hx - 20, hy - 30 + n * 0.6), (px, py + 26), (px, py + 2)], col, 1.1)
    b += pc_svg
    b += no(pc["OE"][0] - 8, pc["OE"][1], 2.6) + no(pc["V+"][0] - 8, pc["V+"][1], 2.6)
    b += text(pc["V+"][0] - 12, pc["V+"][1] + 6.4, "V+ and OE: leave empty", 2.8, "end", "bold", BAD)
    # the key
    kx, ky = 160, 120
    rows = [("VCC", "pin 17", "3.3 V. NOT 5 V (pin 1 already feeds the mic)", "#e07b00"),
            ("GND", "pin 25", "any ground pin works", INK),
            ("SDA", "pin 3", "data", "#2f6fd0"),
            ("SCL", "pin 5", "clock (shared with the wake button: fine)", "#e3c21a")]
    for i, (lab, p, why, col) in enumerate(rows):
        y = ky + i * 9
        b += rect(kx, y - 3.2, 8, 4.2, col, 0.6, 0.3)
        b += text(kx + 11, y, f"{lab} → {p}", 3.4, "start", "bold") + text(kx + 38, y, why, 2.8, "start", "normal", DARK)
    b += text(kx, ky + 40, "Grey pins are already in use: leave them alone.", 2.8, "start", "normal", DARK)
    b += text(kx, ky + 47, "Header V+ is tied to the servo power. Joining it to the Pi\nis \"power through another part\", the one thing the rail exists to stop.", 2.8, "start", "normal", BAD)
    page("The servo board's brain", b, 7)


# ===================================================================== step 8
def step8():
    b = panel(12, 34, 190, 161) + panel(206, 34, 79, 161)
    tx, ty = 20, 44
    b += rect(tx, ty, 174, 140, "#1d1f21", 3)
    lines = [("$ sudo raspi-config nonint do_i2c 0", "#8fd18f"), ("$ sudo apt install -y i2c-tools", "#8fd18f"),
             ("$ i2cdetect -y 1", "#8fd18f"),
             ("     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f", "#ccc")]
    rows = ["00:          -- -- -- -- -- -- -- -- -- -- -- -- --"] + \
           [f"{r}0: " + " ".join(["--"] * 16) for r in range(1, 7)] + ["70: -- -- -- -- -- -- -- --"]
    rows[4] = "40: 40 " + " ".join(["--"] * 15)
    rows[7] = "70: 70 -- -- -- -- -- -- --"
    lines += [(r, "#ccc") for r in rows]
    lines += [("", "#ccc"), ("$ vcgencmd get_throttled", "#8fd18f"), ("throttled=0x0", "#ccc")]
    for i, (ln, col) in enumerate(lines):
        b += text(tx + 5, ty + 9 + i * 7.6, ln, 3.3, "start", "normal", col, mono=True)
    gx = tx + 5 + 4 * 3.3 * 0.602 * 1.0
    b += circle(tx + 5 + 5 * 1.99, ty + 9 + 8 * 7.6 - 1.1, 3.8, "none", 0.7, NOTE)
    b += circle(tx + 5 + 5 * 1.99, ty + 9 + 11 * 7.6 - 1.1, 3.8, "none", 0.7, NOTE)
    b += circle(tx + 5 + 11.5 * 1.99, ty + 9 + 14 * 7.6 - 1.1, 0.01, "none", 0)
    b += text(tx + 130, ty + 70, "40 = the servo board", 3.2, "start", "bold", NOTE)
    b += text(tx + 130, ty + 76, "70 = \"all boards\":\nnormal too", 3, "start", "normal", "#ccc")
    b += text(tx + 130, ty + 128, "0x0 = power has\nbeen clean", 3, "start", "bold", "#8fd18f")
    b += ok(186, 48, 4)
    # servos: not yet
    sv_svg, _ = put(servo(), 245, 80, 1.3)
    b += sv_svg + no(268, 66, 5)
    b += caption(214, 110, "Don't plug the servos\nin yet.", 3.6, "start", "bold")
    b += caption(214, 126, "The servo code and a\nbench test come next:\ncentre first, then a\nslow sweep, so the first\ntime they move it's\ngentle.", 3.2)
    b += caption(214, 174, "No 40? Check the 4\njumpers, and that the\nPi was off when wired.", 3.0, "start", "normal", DARK)
    page("Ask the Pi", b, 8)


def build():
    cover(); parts(); step1(); step2(); step3(); step4(); step5(); step6(); step7(); step8()
    total = len(PAGES)
    svgs = []
    for i, (head, body) in enumerate(PAGES):
        foot = text(285, 204, f"Riley · power · {i + 1} / {total}", 2.6, "end", "normal", DARK)
        svgs.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 297 210" class="page">'
                    f'<rect width="297" height="210" fill="#fff"/>{head}{body}{foot}</svg>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Riley Power Instructions</title>
<style>
  @page {{ size: A4 landscape; margin: 0; }}
  html, body {{ margin: 0; padding: 0; background: #fff; }}
  svg.page {{ display: block; width: 297mm; height: 210mm; font-family: Helvetica, Arial, sans-serif; break-after: page; }}
</style></head><body>
{chr(10).join(svgs)}
</body></html>"""


if __name__ == "__main__":
    out = HERE / "power-instructions.html"
    out.write_text(build())
    print("Wrote", out, f"({len(PAGES)} pages)")
