"""
Bolt's brass frame: a full-size bending template on two A4 sheets
(sheet 1: head and neck; sheet 2: base).

LESSON: Drawing at actual size
==============================
Everything here is in MILLIMETRES, and the page is exactly A4 (210 x 297 mm),
so when it's printed at 100% (NOT "fit to page") each shape is the real size.
Lay the brass tube on a shape and bend it to follow the grey band.

Every size comes from PARTS and TUBE below. When the real screen arrives,
measure its board, change the numbers, and run:

    python docs/frame/make_template.py        (makes frame-template.html)
    node docs/frame/print_pdf.js              (makes frame-template.pdf)
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
RADIUS = {"head": 10.0, "base": 12.0, "small": 5.0}      # bend radius at each corner (to the tube's centre)
CLEARANCE = 1.0          # gap between a part's edge and the inside of the tube
STOP_BAR = 2.0           # rod soldered across the front frame so the screen can't fall out the front
HEAD_DEPTH = 26.0        # front-to-back depth of the head (room for the screen, camera, mic and wires)
BASE_FRONT, BASE_BACK = 60.0, 38.0   # height of the base at the front and back (the wedge from your sketch)
YOKE = (50.0, 40.0)      # neck yoke: width between the arms, height of the arms (tube centres)


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
def build():
    head, base = [], []   # sheet 1 (head and neck) and sheet 2 (base)
    parts = head
    t, r = TUBE["head"], RADIUS["head"]

    # 1. Head frames (front and back): hug the screen board.  (Sheet 1)
    sw, sh = PARTS["screen"]
    hw, hh = sw + 2 * CLEARANCE + t, sh + 2 * CLEARANCE + t     # tube-centre size
    x0, y0 = 18, 46
    parts.append(shape(rect(x0, y0, hw, hh), t, r, True,
                       "① Head frame  ×2 (front and back)",
                       f"{t:g} mm tube · centre line {hw:.0f} × {hh:.0f} mm · fits a {sw:g} × {sh:g} mm screen board (pins on the right)",
                       joint=(x0 + hw / 2, y0 + hh)))
    head_len = 2 * (hw + hh) - 8 * r + 2 * math.pi * r
    # The board and its glass, drawn inside the frame, and the two stop bars.
    # LESSON: the frame ring is a little BIGGER than the board (so it slides in),
    # so something has to stop the board falling out of the front. Two thin rods
    # across the front, over the bare board either side of the glass, do it
    # without covering any of the picture.
    left, right = PARTS["screen_glass"]
    bx0, by0 = x0 + t / 2 + CLEARANCE, y0 + t / 2 + CLEARANCE
    parts.append(f'<rect x="{bx0:.2f}" y="{by0:.2f}" width="{sw}" height="{sh}" fill="none" stroke="#888" stroke-width="0.25"/>')
    parts.append(f'<rect x="{bx0 + left:.2f}" y="{by0:.2f}" width="{sw - left - right}" height="{sh}" fill="#eef3fb" stroke="#7a9cc6" stroke-width="0.25"/>')
    parts.append(f'<text x="{bx0 + left + (sw - left - right) / 2:.2f}" y="{by0 + sh / 2:.2f}" class="hint" text-anchor="middle">glass {sw - left - right:g} × {sh:g} mm</text>')
    for bar_x in (bx0 + left / 2, bx0 + sw - right / 2):
        parts.append(f'<line x1="{bar_x:.2f}" y1="{y0:.2f}" x2="{bar_x:.2f}" y2="{y0 + hh:.2f}" stroke="#b07a1c" stroke-width="{STOP_BAR}" stroke-linecap="round"/>')
    parts.append(f'<text x="{x0 + hw / 2:.2f}" y="{y0 + 8:.2f}" class="small" text-anchor="middle">gold bars: stop bars, FRONT frame only</text>')

    # 2. Camera cradle: a U hanging under the head's front frame.
    ts, rs = TUBE["small"], RADIUS["small"]
    cw, ch = PARTS["camera"]
    uw, uh = cw + 2 * CLEARANCE + ts, ch + CLEARANCE + ts / 2
    cx0, cy0 = 22, 140
    parts.append(shape([(cx0, cy0), (cx0, cy0 + uh), (cx0 + uw, cy0 + uh), (cx0 + uw, cy0)], ts, rs, False,
                       "② Camera cradle  ×1",
                       f"{ts:g} mm tube or rod · ends solder under the head frame",
                       ends=[(cx0, cy0 - 3.2, "to frame"), (cx0 + uw, cy0 - 3.2, "to frame")]))
    cam_len = 2 * uh + uw - 4 * rs + math.pi * rs

    # 3. Base: the bottom rectangle.  (Sheet 2)
    parts = base
    tb, rb = TUBE["base"], RADIUS["base"]
    bw, bd = PARTS["base_inside"][0] + tb, PARTS["base_inside"][1] + tb
    bx, by = 18, 50
    parts.append(shape(rect(bx, by, bw, bd), tb, rb, True,
                       "③ Base bottom  ×1",
                       f"{tb:g} mm tube · centre line {bw:.0f} × {bd:.0f} mm · front edge at the bottom of the page",
                       joint=(bx + bw / 2, by)))
    parts.append(f'<text x="{bx + bw / 2:.1f}" y="{by + bd / 2:.1f}" class="hint" text-anchor="middle">Pi 4 at the back · speaker facing forward · amp and servo board beside</text>')
    base_len = 2 * (bw + bd) - 8 * rb + 2 * math.pi * rb

    # 4. Base sides: the wedge from your sketch (front taller than the back). Viewed from the side.
    sx, sy = 18, 236
    front_x, back_x = sx, sx + bd
    pts = [(front_x, sy), (front_x, sy - BASE_FRONT), (back_x, sy - BASE_BACK), (back_x, sy)]
    parts.append(shape(pts, tb, rb, False,
                       "④ Base side  ×2 (left and right)",
                       f"{tb:g} mm tube · front {BASE_FRONT:g} mm tall, back {BASE_BACK:g} mm · feet solder to ③'s corners",
                       ends=[(front_x, sy + 7.5, "front foot"), (back_x, sy + 7.5, "back foot")]))
    slope = math.hypot(bd, BASE_FRONT - BASE_BACK)
    side_len = BASE_FRONT + BASE_BACK + slope  # roughly; bends shorten it a little

    # 5. Neck yoke: a U holding the head; the tilt servo turns it.  (Sheet 1)
    parts = head
    yw, yh = YOKE
    yx, yy = 96, 140
    parts.append(shape([(yx, yy), (yx, yy + yh), (yx + yw, yy + yh), (yx + yw, yy)], tb, rb, False,
                       "⑤ Neck yoke  ×1 (optional)",
                       "or start with a ready-made pan-tilt bracket",
                       ends=[(yx, yy - 3.5, "pivot"), (yx + yw, yy - 3.5, "pivot"), (yx + yw / 2, yy + yh - 5, "▼ pan servo underneath")]))
    yoke_len = 2 * yh + yw - 4 * rb + math.pi * rb

    cut = [
        ("① Head frame", f"2 × {head_len:.0f} mm", f'{TUBE["head"]:g} mm tube'),
        ("Head struts (straight)", f"4 × {HEAD_DEPTH:.0f} mm", f'{TUBE["head"]:g} mm tube'),
        ("Screen stop bars (straight)", f"2 × {hh:.0f} mm", f'{STOP_BAR:g} mm rod'),
        ("② Camera cradle", f"1 × {cam_len:.0f} mm", f'{TUBE["small"]:g} mm tube/rod'),
        ("③ Base bottom", f"1 × {base_len:.0f} mm", f'{TUBE["base"]:g} mm tube'),
        ("④ Base side", f"2 × {side_len:.0f} mm", f'{TUBE["base"]:g} mm tube'),
        ("Base top bars (straight)", f"2 × {bw:.0f} mm", f'{TUBE["base"]:g} mm tube'),
        ("⑤ Neck yoke", f"1 × {yoke_len:.0f} mm", f'{TUBE["base"]:g} mm tube'),
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
    rows = "\n".join(
        f'<text x="128" y="{50 + i * 5.2:.1f}" class="small">{name}</text>'
        f'<text x="173" y="{50 + i * 5.2:.1f}" class="small">{length}</text>'
        for i, (name, length, _) in enumerate(cut))
    cut_list = f'<text x="128" y="44.5" class="label">Cut list (whole frame)</text>\n{rows}'
    extras = ('<text x="18" y="262" class="small">Also: 2 straight top bars join the two base sides at the front and back '
              '(lengths on sheet 1).</text>')
    sheets = sheet(1, "head and neck", cut_list + "\n" + "\n".join(head)) + "\n" + \
        sheet(2, "base", "\n".join(base) + "\n" + extras)
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
