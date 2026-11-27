#!/usr/bin/env python3
"""
A full-size paper check of every size the printed body guessed, before anyone pays for plastic.

    python docs/print/make_check_sheet.py && node docs/print/print_sheet.js     (check-sheet.pdf)

Print it at 100 % ("Actual size"), check the 70 mm line with a ruler, then lay each real part on
its drawing. Every dot must sit under a hole. Anything that doesn't line up: measure it, change
the number in make_parts.py, and print this again.
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import make_parts as P  # noqa: E402

INK, GREY, BLUE, GREEN, RED = "#1a1a1a", "#9a9a96", "#2463ad", "#2e8b57", "#c62828"


def t(x, y, s, size=3.0, anchor="start", weight="normal", fill=INK):
    return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">{s}</text>'


def rect(x, y, w, h, r=0, stroke=INK, sw=0.3, dash="", fill="none"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{r:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'


def circ(x, y, d, stroke=INK, sw=0.3, fill="none", dash=""):
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{d / 2:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{ds}/>'


def dot(x, y, d=1.2, colour=RED):
    """A hole's centre: a small dot with a cross, so it shows through the hole."""
    return (circ(x, y, d, colour, 0.2, colour) + f'<line x1="{x - 2:.2f}" y1="{y:.2f}" x2="{x + 2:.2f}" y2="{y:.2f}" stroke="{colour}" stroke-width="0.15"/>'
            f'<line x1="{x:.2f}" y1="{y - 2:.2f}" x2="{x:.2f}" y2="{y + 2:.2f}" stroke="{colour}" stroke-width="0.15"/>')


def tick(x, y):
    return rect(x, y - 2.6, 3.2, 3.2, 0.4, INK, 0.3)


def sheet(n, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 297" class="page">
<rect width="210" height="297" fill="#fff"/>
{t(12, 16, f"Riley · printed body · check sheet {n} of 2: {title}", 5.2, weight="bold")}
{t(12, 22.5, 'Print at 100% / "Actual size" (NOT "Fit to page"). Check the 70 mm line below with a ruler first.', 2.9, fill=RED, weight="bold")}
{t(12, 28.8, "Lay each real part on its drawing: every red dot must sit under a hole. Tick the box when it does.", 2.9)}
{t(12, 36, "This line must be 70 mm:", 2.9, weight="bold")}
<line x1="50" y1="35" x2="120" y2="35" stroke="{INK}" stroke-width="0.35"/><line x1="50" y1="33.5" x2="50" y2="36.5" stroke="{INK}" stroke-width="0.35"/><line x1="120" y1="33.5" x2="120" y2="36.5" stroke="{INK}" stroke-width="0.35"/>
{body}
{t(12, 289, "Doesn't line up? Measure it, change the number in docs/print/make_parts.py (named in brackets), and print this again.", 2.6, fill=GREY)}
</svg>"""


def face_sheet():
    hw, hh = P.HEAD
    s = P.screen_layout()
    c = P.chin_layout()
    ox, oy = 105, 50                       # the face's top-left corner... as its centre-top
    X = lambda x: ox + x                    # noqa: E731  model x -> paper (you facing her)
    Y = lambda z: oy + (hh - z)             # noqa: E731  model z (up) -> paper (down)
    b = [rect(X(-hw / 2), Y(hh), hw, hh, P.HEAD_R, GREY, 0.8)]
    b.append(t(X(-hw / 2), Y(hh) - 2, "Riley's face, full size, as you look at her", 3, weight="bold"))
    pw, ph, pr = P.face_plate_size()
    b.append(rect(X(-pw / 2), Y(hh / 2 + ph / 2), pw, ph, pr, INK, 0.25, "1 1"))
    gw, gh = s["glass"]
    # the screen: lay it face UP on its outline
    x0, x1 = s["pcb_x"]; z0, z1 = s["pcb_z"]
    b.append(rect(X(x0), Y(z1), x1 - x0, z1 - z0, 1, BLUE, 0.35))
    b.append(rect(X(-gw / 2), Y(z1), gw, gh, 0.5, BLUE, 0.25, "2 1"))
    hx, hz = P.SCREEN_HOLES
    for x in (x0 + hx, x1 - hx):
        for z in (z0 + hz, z1 - hz):
            b.append(dot(X(x), Y(z)))
    b.append(t(X(0), Y((z0 + z1) / 2) - 3, "SCREEN, face up, its edges on the blue outline:", 2.8, "middle", "bold", BLUE))
    b.append(t(X(0), Y((z0 + z1) / 2) + 1.5, "• its glass inside the dashed box (SCREEN_MARGINS)", 2.6, "middle"))
    b.append(t(X(0), Y((z0 + z1) / 2) + 5, "• its 4 corner holes over the red dots (SCREEN_HOLES)", 2.6, "middle"))
    # the camera
    cw, ch = P.CAMERA
    b.append(rect(X(-cw / 2), Y(c["board_top"]), cw, ch, 0.5, GREEN, 0.35))
    hx0, hy0, hdx, hdy = P.CAMERA_HOLES
    for x in (-cw / 2 + hx0, -cw / 2 + hx0 + hdx):
        for z in (c["board_top"] - hy0, c["board_top"] - hy0 - hdy):
            b.append(dot(X(x), Y(z)))
    b.append(circ(X(0), Y(c["lens_z"]), 8.5, GREEN, 0.35) + dot(X(0), Y(c["lens_z"]), 0.8, GREEN))
    # the mic and the light
    b.append(circ(X(-P.CHIN_X), Y(c["lens_z"]), P.MIC_BOARD, INK, 0.35) + dot(X(-P.CHIN_X), Y(c["lens_z"]), 0.8))
    b.append(circ(X(P.CHIN_X), Y(c["lens_z"]), 5.2, INK, 0.35))
    # notes below
    y = Y(0) + 10
    rows = [
        (GREEN, f"CAMERA, lens up, on the green outline: 4 holes over the dots (CAMERA_HOLES), the lens centred in its circle (CAMERA_LENS_FROM_TOP)."),
        (INK, f"MIC board on the left circle: it must fit inside it ({P.MIC_BOARD:g} mm, MIC_BOARD), its sound hole over the dot."),
        (INK, "POWER LIGHT (5 mm LED) in the right circle."),
        (BLUE, f"SCREEN glass depth: front of the glass to the front of the green board, beside it = {P.SCREEN_GLASS_DEPTH:g} mm? (SCREEN_GLASS_DEPTH)"),
        (GREEN, f"CAMERA lens height: top of the lens to the front of its board = {P.CAMERA_LENS:g} mm? (CAMERA_LENS)"),
    ]
    for i, (col, line) in enumerate(rows):
        b.append(tick(12, y + i * 7) + t(18, y + i * 7, line, 2.7, fill=col))
    return "\n".join(b)


def neck_sheet():
    b = []
    # the bearing, from above
    cx, cy = 62, 82
    q = P.BEARING["square"] / 2
    b.append(t(cx - q, cy - q - 4, "TURNTABLE BEARING, from above", 3, weight="bold"))
    b.append(rect(cx - q, cy - q, 2 * q, 2 * q, 2, INK, 0.5) + circ(cx, cy, P.BEARING["hole"], INK, 0.35, dash="2 1"))
    for k in range(4):
        a = math.radians(45 + 90 * k)
        r = P.BEARING["bottom_holes"]
        b.append(dot(cx + r * math.cos(a), cy + r * math.sin(a)))
    b.append(t(cx, cy + q + 5, "bottom plate's screw holes over the red dots (BEARING bottom_holes)", 2.5, "middle"))
    b.append(t(cx, cy + q + 8.5, "then turn it over: top plate's holes the same way (top_holes)", 2.5, "middle"))
    b.append(t(cx, cy + q + 12, f"square {P.BEARING['square']:g} mm, centre hole {P.BEARING['hole']:g} mm, {P.BEARING['thick']:g} mm thick", 2.5, "middle", fill=GREY))
    # the round horn
    hx, hy = 160, 70
    hd = P.HORN["diameter"]
    b.append(t(hx - 25, hy - hd / 2 - 8, "ROUND SERVO HORN, flat side down", 3, weight="bold"))
    b.append(circ(hx, hy, hd, INK, 0.5) + dot(hx, hy, 1.0, GREEN))
    for dx in (-P.HORN["hole_r"], P.HORN["hole_r"]):
        b.append(dot(hx + dx, hy))
    b.append(t(hx, hy + hd / 2 + 5, f"{hd:g} mm across (HORN diameter); 2 holes", 2.5, "middle"))
    b.append(t(hx, hy + hd / 2 + 8.5, f"{P.HORN['hole_r']:g} mm from the centre (HORN hole_r)", 2.5, "middle"))
    b.append(t(hx, hy + hd / 2 + 12, f"pushed on: flat face {P.HORN['above_shaft']:g} mm above", 2.5, "middle"))
    b.append(t(hx, hy + hd / 2 + 15.5, "the shaft's tip? (HORN above_shaft)", 2.5, "middle"))
    # the servo, from above, standing on its tabs
    sx, sy = 160, 140
    L, Wd, tabs = P.SERVO["length"], P.SERVO["width"], P.SERVO["tabs"]
    shaft_x = sx
    case_x0 = shaft_x - (L - P.SERVO["shaft_from_end"])
    b.append(t(sx - 30, sy - 12, "SERVO, shaft up (a check, already measured)", 3, weight="bold"))
    b.append(rect(case_x0 - (tabs - L) / 2, sy - Wd / 2, tabs, Wd, 1, GREY, 0.3))
    b.append(rect(case_x0, sy - Wd / 2, L, Wd, 1, INK, 0.5) + dot(shaft_x, sy, 1.0, GREEN))
    for dx in (-P.SERVO["hole_spacing"] / 2, P.SERVO["hole_spacing"] / 2):
        b.append(dot(case_x0 + L / 2 + dx, sy))
    b.append(t(sx, sy + 11, "shaft on the green dot, tab holes over the red", 2.5, "middle"))
    # the servo board's holes
    bx, by = 40, 160
    w, l = P.SERVO_BOARD_HOLES
    b.append(t(bx - 18, by - 6, "SERVO BOARD (PCA9685)", 3, weight="bold"))
    b.append(rect(bx - 12.7, by - 3, 25.4, l + 6, 1, GREY, 0.3, "2 1"))
    for dx in (0, w):
        for dy in (0, l):
            b.append(dot(bx - w / 2 + dx, by + dy))
    b.append(t(bx + 16, by + l / 2, "4 holes over", 2.5) + t(bx + 16, by + l / 2 + 3.5, "the dots", 2.5))
    b.append(t(bx + 16, by + l / 2 + 7, "(SERVO_BOARD_HOLES)", 2.5, fill=GREY))
    # the speaker
    spx, spy = 140, 185
    sl, sh, _ = P.SPEAKER
    b.append(t(spx - sl / 2, spy - sh / 2 - 4, "SPEAKER, face down", 3, weight="bold"))
    b.append(rect(spx - sl / 2, spy - sh / 2, sl, sh, 2, INK, 0.5))
    for dx in (-P.SPEAKER_HOLES / 2, P.SPEAKER_HOLES / 2):
        b.append(dot(spx + dx, spy))
    b.append(t(spx, spy + sh / 2 + 5, "its 2 end holes over the dots (SPEAKER_HOLES)", 2.5, "middle"))
    # the to-do list
    y = 240
    rows = ["Bearing: bottom holes", "Bearing: top holes", "Horn: size and holes", "Horn: height on the shaft",
            "Servo board holes", "Speaker holes"]
    b.append(t(12, y - 6, "Ticked them all? Then the parts are right to order.", 3.2, weight="bold", fill=GREEN))
    for i, r in enumerate(rows):
        x = 12 + (i % 2) * 95
        b.append(tick(x, y + (i // 2) * 7) + t(x + 6, y + (i // 2) * 7, r, 2.8))
    return "\n".join(b)


def main():
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Riley Check Sheet</title>
<style>@page {{ size: A4; margin: 0; }} html, body {{ margin: 0; background: #fff; }}
svg.page {{ display: block; width: 210mm; height: 297mm; font-family: Helvetica, Arial, sans-serif; break-after: page; }}</style>
</head><body>
{sheet(1, "the face", face_sheet())}
{sheet(2, "the neck and base", neck_sheet())}
</body></html>"""
    out = HERE / "check-sheet.html"
    out.write_text(html)
    print("Wrote", out)


if __name__ == "__main__":
    main()
