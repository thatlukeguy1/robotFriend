"""
Bolt's brass frame: a full-size bending template on two A4 sheets
(sheet 1: the CRT-monitor head; sheet 2: the desktop-case base and the neck).

LESSON: Drawing at actual size
==============================
Everything here is in MILLIMETRES, and the page is exactly A4 (210 x 297 mm),
so when it's printed at 100% (NOT "fit to page") each shape is the real size.
Lay the brass tube on a shape and bend it to follow the grey band.

LESSON: How a hollow CRT is built from rings
============================================
An old CRT monitor is a box at the front (the BEZEL) and a tapering tube
behind it. In brass that's just three rings joined by straight struts:

    front bezel ring ==(short struts)== middle bezel ring ==(slanted struts)== back ring
                                         (same size)                          (smaller)

Inside the front ring, a smaller SCREEN RING hugs the screen board, held to
the bezel by four short SPOKES. Bolt's camera sits on top like an old webcam.

Every size comes from the numbers below. Change one, then run:

    python docs/frame/make_template.py        (makes frame-template.html)
    node docs/frame/print_pdf.js              (makes frame-template.pdf)
    python docs/frame/make_concept.py         (redraws the picture to match)
"""

import math
from pathlib import Path

# ---------------------------------------------------------------- measurements
# Part sizes in mm (published sizes: CHECK them against your real parts!)
PARTS = {
    "screen": (85.0, 50.0),        # 2.8" ILI9341 board (width, height): MEASURED
    "screen_glass": (6.0, 10.0),   # bare board left and right of the glass (pins on the right): MEASURED
    "screen_thick": 7.0,           # board thickness, front of the glass to the back of the pins: MEASURED
    "camera": (25.0, 24.0),        # Pi Camera Module 3 board
    "base_inside": (128.0, 88.0),  # room inside the base: Pi 4 (85x56) + speaker (70x31) + amp + servo board
}
TUBE = {"head": 4.0, "base": 5.0, "small": 3.0}          # tube outside diameters (mm)
RADIUS = {"head": 10.0, "back": 8.0, "base": 12.0, "small": 5.0}  # bend radius at each corner (to the tube's centre)
CLEARANCE = 1.0          # gap between a part's edge and the inside of the tube
STOP_BAR = 2.0           # rod soldered across the screen ring so the screen can't fall out the front

# The CRT head (all tube-centre sizes)
BEZEL = (108.0, 84.0)    # front and middle bezel rings: width, height
BEZEL_DEPTH = 14.0       # front ring to middle ring
BACK = (66.0, 52.0)      # the small back ring
TAPER_DEPTH = 52.0       # middle ring to back ring
BACK_LIFT = 2.0          # the back ring sits this much higher than the bezel's bottom (CRTs are flat underneath)
CHIN = 18.0              # bezel bottom to screen-ring bottom: the "chin" (mic and power light go here)

# The desktop-case base and the neck
BASE_HEIGHT = 46.0       # bottom ring to top ring
CROSS_BARS_APART = 30.0  # the two bars across the base's top ring that hold the turntable
FOOT = 50.0              # swivel-foot ring diameter (sits on a small turntable bearing)
YOKE = (40.0, 24.0)      # tilt yoke: width between the arms, height of the arms (tube centres)

# ------------------------------------------------------------------- geometry
def fillet_path(points, radius, closed):
    """
    An SVG path through `points` with every corner rounded to `radius`.
    Returns (path, bend_ticks): where each bend starts and ends, to mark on the paper.
    """
    n = len(points)
    corners = range(n) if closed else range(1, n - 1)
    rounded, ticks = {}, []
    for i in corners:
        p0, p1, p2 = points[i - 1], points[i], points[(i + 1) % n]
        a = (p0[0] - p1[0], p0[1] - p1[1]); b = (p2[0] - p1[0], p2[1] - p1[1])
        la, lb = math.hypot(*a), math.hypot(*b)
        ua, ub = (a[0] / la, a[1] / la), (b[0] / lb, b[1] / lb)
        angle = math.acos(max(-1, min(1, ua[0] * ub[0] + ua[1] * ub[1])))
        d = min(radius / math.tan(angle / 2), la / 2, lb / 2)   # how far from the corner the bend starts
        r = d * math.tan(angle / 2)
        start = (p1[0] + ua[0] * d, p1[1] + ua[1] * d)
        end = (p1[0] + ub[0] * d, p1[1] + ub[1] * d)
        sweep = 1 if (ua[0] * ub[1] - ua[1] * ub[0]) < 0 else 0
        rounded[i] = (start, end, r, sweep)
        ticks += [(start, ua), (end, ub)]

    def fmt(p):
        return f"{p[0]:.2f},{p[1]:.2f}"

    if closed:
        first = rounded[0][1]
        cmds = [f"M{fmt(first)}"]
        order = list(range(1, n)) + [0]
    else:
        cmds = [f"M{fmt(points[0])}"]
        order = list(range(1, n))
    for i in order:
        if i in rounded:
            s, e, r, sweep = rounded[i]
            cmds += [f"L{fmt(s)}", f"A{r:.2f},{r:.2f} 0 0 {sweep} {fmt(e)}"]
        else:
            cmds.append(f"L{fmt(points[i])}")
    if closed:
        cmds.append("Z")
    return " ".join(cmds), ticks


def shape(points, tube, radius, closed, label, note, joint=None, ends=None):
    """One bendable piece: grey band the width of the tube, a dashed centre line,
    red ticks where each bend starts and ends, and labels."""
    path, ticks = fillet_path(points, radius, closed)
    out = [f'<path d="{path}" class="band" style="stroke-width:{tube}"/>',
           f'<path d="{path}" class="centre"/>']
    for (x, y), (ux, uy) in ticks:           # a tick across the tube
        nx, ny = -uy, ux
        h = tube / 2 + 1.6
        out.append(f'<line x1="{x - nx * h:.2f}" y1="{y - ny * h:.2f}" x2="{x + nx * h:.2f}" y2="{y + ny * h:.2f}" class="tick"/>')
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    if joint:
        out.append(f'<circle cx="{joint[0]:.2f}" cy="{joint[1]:.2f}" r="1.6" class="joint"/>')
        # put "join here" on the INSIDE of the shape, away from the labels outside it
        inside = -1 if joint[1] > (min(ys) + max(ys)) / 2 else 1
        y = joint[1] + inside * (tube / 2 + (2.2 if inside < 0 else 4))
        out.append(f'<text x="{joint[0]:.2f}" y="{y:.2f}" class="small" text-anchor="middle">join here</text>')
    end_ys = []
    for (x, y, text) in ends or []:
        out.append(f'<text x="{x:.2f}" y="{y:.2f}" class="small" text-anchor="middle">{text}</text>')
        end_ys.append(y)
    # keep the title above, and the note below, everything else
    title_y = min([min(ys) - tube - 2.5] + [y - 4.5 for y in end_ys if y < min(ys)])
    note_y = max([max(ys) + tube + 4.5] + [y + 4.5 for y in end_ys if y > max(ys)])
    out.append(f'<text x="{min(xs) - tube:.2f}" y="{title_y:.2f}" class="label">{label}</text>')
    out.append(f'<text x="{min(xs) - tube:.2f}" y="{note_y:.2f}" class="small">{note}</text>')
    return "\n".join(out)


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


# ---------------------------------------------------------------- the pieces
def head_sizes():
    """Sizes the template and the picture both need."""
    t = TUBE["head"]
    sw, sh = PARTS["screen"]
    ring = (sw + 2 * CLEARANCE + t, sh + 2 * CLEARANCE + t)      # screen ring, tube centres
    side_gap = (BEZEL[0] - ring[0]) / 2                          # bezel ring to screen ring, centre to centre
    top_gap = BEZEL[1] - CHIN - ring[1]
    dx = (BEZEL[0] - BACK[0]) / 2
    taper_top = math.sqrt(dx ** 2 + (BEZEL[1] - BACK[1] - BACK_LIFT) ** 2 + TAPER_DEPTH ** 2)
    taper_bottom = math.sqrt(dx ** 2 + BACK_LIFT ** 2 + TAPER_DEPTH ** 2)
    # the axle goes across the head's floor at the balance point, about a third of the way back
    axle_z = BEZEL_DEPTH / 2 - (BEZEL_DEPTH + TAPER_DEPTH) * 0.3
    return dict(ring=ring, side_gap=side_gap, top_gap=top_gap, taper_top=taper_top,
                taper_bottom=taper_bottom, axle=BEZEL[0] - 2 * dx * 0.42)


def ring_length(w, h, r):
    return 2 * (w + h) - 8 * r + 2 * math.pi * r


def circle_piece(cx, cy, d, tube, label, note):
    r = d / 2
    return "\n".join([
        f'<circle cx="{cx}" cy="{cy}" r="{r}" class="band" style="stroke-width:{tube}"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{r}" class="centre"/>',
        f'<circle cx="{cx}" cy="{cy + r:.2f}" r="1.6" class="joint"/>',
        f'<text x="{cx}" y="{cy + r - 2.6:.2f}" class="small" text-anchor="middle">join here</text>',
        f'<text x="{cx - r - tube:.2f}" y="{cy - r - tube - 2.5:.2f}" class="label">{label}</text>',
        f'<text x="{cx - r - tube:.2f}" y="{cy + r + tube + 4.5:.2f}" class="small">{note}</text>',
    ])


def build():
    head, base = [], []   # sheet 1 (head) and sheet 2 (base and neck)
    t, r = TUBE["head"], RADIUS["head"]
    hs = head_sizes()

    # 1. Bezel rings (front and middle).  (Sheet 1)
    bw, bh = BEZEL
    x0, y0 = 18, 46
    head.append(shape(rect(x0, y0, bw, bh), t, r, True, "① Bezel ring  ×2 (front and middle)",
                      f"{t:g} mm tube · centre line {bw:g} × {bh:g} mm · joined by 4 straight struts, {BEZEL_DEPTH:g} mm",
                      joint=(x0 + bw / 2, y0 + bh)))
    # where the screen ring sits inside it (so you can check before soldering the spokes)
    rw, rh = hs["ring"]
    rx, ry = x0 + (bw - rw) / 2, y0 + bh - CHIN - rh
    head.append(f'<rect x="{rx:.2f}" y="{ry:.2f}" width="{rw:.2f}" height="{rh:.2f}" rx="{r}" fill="none" stroke="#7a9cc6" stroke-width="0.35" stroke-dasharray="1.5 1"/>')
    head.append(f'<text x="{x0 + bw / 2:.2f}" y="{ry + rh / 2:.2f}" class="hint" text-anchor="middle">screen ring ③ goes here (front ring only)</text>')
    head.append(f'<text x="{x0 + bw / 2:.2f}" y="{ry + rh + CHIN / 2 + 1:.2f}" class="hint" text-anchor="middle">chin: mic and power light</text>')
    for sx in (rx + rw * 0.28, rx + rw * 0.72):        # bottom spokes
        head.append(f'<line x1="{sx:.2f}" y1="{ry + rh:.2f}" x2="{sx:.2f}" y2="{y0 + bh:.2f}" stroke="#b07a1c" stroke-width="2"/>')
    for sx in (rx, rx + rw):                           # side spokes
        to = x0 if sx == rx else x0 + bw
        head.append(f'<line x1="{sx:.2f}" y1="{ry + rh / 2:.2f}" x2="{to:.2f}" y2="{ry + rh / 2:.2f}" stroke="#b07a1c" stroke-width="2"/>')
    bezel_len = ring_length(bw, bh, r)

    # 2. Webcam cradle: a U standing on top of the bezel, like an old clip-on webcam.
    ts, rs = TUBE["small"], RADIUS["small"]
    cw, ch = PARTS["camera"]
    uw, uh = cw + 2 * CLEARANCE + ts, ch + CLEARANCE + ts / 2
    cx0, cy0 = 150, 52
    head.append(shape([(cx0, cy0), (cx0, cy0 + uh), (cx0 + uw, cy0 + uh), (cx0 + uw, cy0)], ts, rs, False,
                      "② Webcam cradle  ×1",
                      f"{ts:g} mm tube/rod · bottom solders on top of the bezel",
                      ends=[(cx0, cy0 - 3.2, "top"), (cx0 + uw, cy0 - 3.2, "top")]))
    cam_len = 2 * uh + uw - 4 * rs + math.pi * rs

    # 3. Screen ring: hugs the screen board, with two stop bars across the front.
    sw, sh = PARTS["screen"]
    sx0, sy0 = 18, 162
    head.append(shape(rect(sx0, sy0, rw, rh), t, r, True, "③ Screen ring  ×1",
                      f"{t:g} mm tube · centre line {rw:.0f} × {rh:.0f} mm · fits the {sw:g} × {sh:g} mm screen board (pins on the right)",
                      joint=(sx0 + rw / 2, sy0 + rh)))
    left, right = PARTS["screen_glass"]
    bx0, by0 = sx0 + t / 2 + CLEARANCE, sy0 + t / 2 + CLEARANCE
    head.append(f'<rect x="{bx0:.2f}" y="{by0:.2f}" width="{sw}" height="{sh}" fill="none" stroke="#888" stroke-width="0.25"/>')
    head.append(f'<rect x="{bx0 + left:.2f}" y="{by0:.2f}" width="{sw - left - right}" height="{sh}" fill="#eef3fb" stroke="#7a9cc6" stroke-width="0.25"/>')
    head.append(f'<text x="{bx0 + left + (sw - left - right) / 2:.2f}" y="{by0 + sh / 2:.2f}" class="hint" text-anchor="middle">glass {sw - left - right:g} × {sh:g} mm</text>')
    for bar_x in (bx0 + left / 2, bx0 + sw - right / 2):
        head.append(f'<line x1="{bar_x:.2f}" y1="{sy0:.2f}" x2="{bar_x:.2f}" y2="{sy0 + rh:.2f}" stroke="#b07a1c" stroke-width="{STOP_BAR}" stroke-linecap="round"/>')
    head.append(f'<text x="{sx0 + rw / 2:.2f}" y="{sy0 + 8:.2f}" class="small" text-anchor="middle">gold bars: stop bars, on the front</text>')
    ring_len = ring_length(rw, rh, r)

    # 4. Back ring: the small end of the CRT.
    kw, kh = BACK
    kx0, ky0 = 126, 162
    head.append(shape(rect(kx0, ky0, kw, kh), t, RADIUS["back"], True, "④ Back ring  ×1",
                      f"{t:g} mm tube · centre line {kw:g} × {kh:g} mm",
                      joint=(kx0 + kw / 2, ky0 + kh)))
    back_len = ring_length(kw, kh, RADIUS["back"])

    head.append('<text x="12" y="246" class="label">Putting the head together</text>')
    for i, line in enumerate([
        "1. Solder the screen ring ③ inside the FRONT bezel ring ① with the 4 spokes (positions drawn on ①).",
        f"2. Join the front and middle bezel rings with 4 straight struts ({BEZEL_DEPTH:g} mm) at the corners.",
        f"3. Join the middle ring to the back ring ④ with 4 slanted struts: {hs['taper_top']:.0f} mm at the top, {hs['taper_bottom']:.0f} mm at the bottom.",
        f"4. Solder the head axle across the floor, about a third of the way back, where the head balances.",
        "5. Stand the webcam cradle ② on top of the front ring, in the middle.",
    ]):
        head.append(f'<text x="12" y="{252 + i * 5:.1f}" class="small">{line}</text>')

    # 5. Base rings: the desktop case's top and bottom.  (Sheet 2)
    tb, rb = TUBE["base"], RADIUS["base"]
    cw2, cd2 = PARTS["base_inside"][0] + tb, PARTS["base_inside"][1] + tb
    bx, by = 18, 50
    base.append(shape(rect(bx, by, cw2, cd2), tb, rb, True, "⑤ Base ring  ×2 (top and bottom)",
                      f"{tb:g} mm tube · centre line {cw2:.0f} × {cd2:.0f} mm · 4 straight posts ({BASE_HEIGHT:g} mm) join them at the corners",
                      joint=(bx + cw2 / 2, by + cd2)))
    for k in (-1, 1):
        x = bx + cw2 / 2 + k * CROSS_BARS_APART / 2
        base.append(f'<line x1="{x:.2f}" y1="{by:.2f}" x2="{x:.2f}" y2="{by + cd2:.2f}" stroke="#b07a1c" stroke-width="2" opacity="0.8"/>')
    base.append(f'<text x="{bx + 8:.1f}" y="{by + cd2 / 2:.1f}" class="hint">gold: 2 cross bars,</text>')
    base.append(f'<text x="{bx + 8:.1f}" y="{by + cd2 / 2 + 4:.1f}" class="hint">TOP ring only, for</text>')
    base.append(f'<text x="{bx + 8:.1f}" y="{by + cd2 / 2 + 8:.1f}" class="hint">the turntable (pan</text>')
    base.append(f'<text x="{bx + 8:.1f}" y="{by + cd2 / 2 + 12:.1f}" class="hint">servo hangs below)</text>')
    base_len = ring_length(cw2, cd2, rb)

    # 6. Swivel foot: a ring that sits on the turntable bearing.
    ts2 = TUBE["small"]
    base.append(circle_piece(18 + FOOT / 2, 190, FOOT, ts2, "⑥ Swivel foot  ×1",
                             f"{ts2:g} mm tube · {FOOT:g} mm across · bend round a jar"))

    # 7. Tilt yoke: a U standing on the foot; its arms hold the head axle.
    yw, yh = YOKE
    yx, yy = 88, 172
    base.append(shape([(yx, yy), (yx, yy + yh), (yx + yw, yy + yh), (yx + yw, yy)], tb, rb, False,
                      "⑦ Tilt yoke  ×1",
                      "bottom on the foot · axle through the arm tops",
                      ends=[(yx, yy - 3.5, "axle"), (yx + yw, yy - 3.5, "axle")]))
    yoke_len = 2 * yh + yw - 4 * rb + math.pi * rb

    cut = [
        ("① Bezel ring", f"2 × {bezel_len:.0f}", "4 mm"),
        ("Bezel struts", f"4 × {BEZEL_DEPTH:.0f}", "4 mm"),
        ("Taper struts (top)", f"2 × {hs['taper_top']:.0f}", "4 mm"),
        ("Taper struts (bottom)", f"2 × {hs['taper_bottom']:.0f}", "4 mm"),
        ("② Webcam cradle", f"1 × {cam_len:.0f}", "3 mm"),
        ("③ Screen ring", f"1 × {ring_len:.0f}", "4 mm"),
        ("Screen stop bars", f"2 × {rh:.0f}", "2 mm rod"),
        ("Spokes (sides)", f"2 × {hs['side_gap'] - t:.0f}", "4 mm"),
        ("Spokes (bottom)", f"2 × {CHIN - t:.0f}", "4 mm"),
        ("④ Back ring", f"1 × {back_len:.0f}", "4 mm"),
        ("Head axle", f"1 × {hs['axle']:.0f}", "4 mm"),
        ("⑤ Base ring", f"2 × {base_len:.0f}", "5 mm"),
        ("Base posts", f"4 × {BASE_HEIGHT:.0f}", "5 mm"),
        ("Base cross bars", f"2 × {cd2:.0f}", "5 mm"),
        ("⑥ Swivel foot", f"1 × {math.pi * FOOT:.0f}", "3 mm"),
        ("⑦ Tilt yoke", f"1 × {yoke_len:.0f}", "5 mm"),
    ]
    return head, base, cut


def sheet(number, title, body):
    """One A4 sheet: title, the printing check, the pieces, and a reminder."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 297">
  <text x="12" y="16" class="title">Bolt · brass frame · sheet {number} of 2: {title}</text>
  <text x="12" y="22.5" class="warn">Print at 100% / "Actual size" (NOT "Fit to page"). Check the 70 mm line with a ruler first.</text>
  <text x="12" y="27" class="small">Grey band = the tube · dashed line = tube centre · red ticks = where each bend starts and ends · bend slowly with a bending spring</text>
  <line x1="128" y1="34" x2="198" y2="34" stroke="#222" stroke-width="0.35"/>
  <line x1="128" y1="32.5" x2="128" y2="35.5" stroke="#222" stroke-width="0.35"/>
  <line x1="198" y1="32.5" x2="198" y2="35.5" stroke="#222" stroke-width="0.35"/>
  <text x="128" y="31.5" class="small">This line must measure exactly 70 mm</text>
  {body}
  <text x="12" y="284" class="warn">Measure your REAL screen board and parts before cutting. Change the sizes in docs/frame/make_template.py and print again.</text>
  <text x="12" y="289" class="small">Leave the tube ~10 mm longer than the cut list and trim after bending. Brass conducts: keep bare wires and boards off it (heat-shrink, nylon standoffs).</text>
</svg>"""


def page():
    head, base, cut = build()
    total = {}
    for _, length, tube in cut:
        n, mm = length.split(" × ")
        total[tube] = total.get(tube, 0) + int(n) * float(mm)
    rows = "\n".join(
        f'<text x="140" y="{173 + i * 4.4:.1f}" class="small">{name}</text>'
        f'<text x="178" y="{173 + i * 4.4:.1f}" class="small">{length} mm</text>'
        f'<text x="198" y="{173 + i * 4.4:.1f}" class="small" text-anchor="end"></text>'
        for i, (name, length, tube) in enumerate(cut))
    totals = " · ".join(f"{tube}: {mm / 1000:.2f} m" for tube, mm in total.items())
    cut_list = (f'<text x="140" y="166" class="label">Cut list (whole frame)</text>\n{rows}\n'
                f'<text x="12" y="262" class="small">Total tube (before the ~10 mm extra per piece): {totals}</text>'
                f'<text x="12" y="267" class="small">Also needed: a small turntable ("lazy Susan") bearing, about 50 mm, between the cross bars and the foot.</text>')
    sheets = sheet(1, "the CRT head", "\n".join(head)) + "\n" + \
        sheet(2, "the base and neck", "\n".join(base) + "\n" + cut_list)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Bolt Frame Template</title>
<style>
  @page {{ size: A4; margin: 0; }}
  html, body {{ margin: 0; padding: 0; background: #fff; }}
  svg {{ display: block; width: 210mm; height: 297mm; font-family: Helvetica, Arial, sans-serif; break-after: page; }}
  .band {{ fill: none; stroke: #d9d9d9; stroke-linecap: round; stroke-linejoin: round; }}
  .centre {{ fill: none; stroke: #222; stroke-width: 0.25; stroke-dasharray: 2 1.2; }}
  .tick {{ stroke: #d03a2b; stroke-width: 0.45; }}
  .joint {{ fill: #fff; stroke: #d03a2b; stroke-width: 0.4; }}
  .title {{ font-size: 6px; font-weight: bold; }}
  .label {{ font-size: 3.4px; font-weight: bold; }}
  .small {{ font-size: 2.6px; fill: #333; }}
  .hint {{ font-size: 2.6px; fill: #999; font-style: italic; }}
  .warn {{ font-size: 2.8px; fill: #d03a2b; font-weight: bold; }}
</style></head>
<body>
{sheets}
</body></html>
"""


if __name__ == "__main__":
    out = Path(__file__).with_name("frame-template.html")
    out.write_text(page())
    print("Wrote", out)
