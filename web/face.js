/*
 * LESSON: Drawing Bolt's face
 * ===========================
 * The face is ONE screen (320 x 240 on the robot) drawn fresh about 60
 * times a second, in layers, like a cartoon:
 *
 *   1. the dark screen
 *   2. each EYE: a rounded square with a coloured ring, a pupil, and two
 *      white highlights (the shine that makes eyes look alive)
 *   3. EYELIDS: shapes in the background colour that cut into each eye
 *   4. EYEBROWS: curved brows that FADE IN only for moods that need them
 *      (like thinking or confused), and fade out again afterwards
 *   5. the MOUTH: a small curve that smiles or frowns, and opens when Bolt talks
 *
 * An EXPRESSION is a handful of numbers (see expressions.json):
 *   open        how far the top lids are lifted (0 = shut, 1 = wide)
 *   lowerLid    how far the bottom lids rise (a happy squint)
 *   tilt        angle of the top lids (+ = cross, - = worried)
 *   pupil       pupil size
 *   lookX/Y     where it's looking (-1 to 1)
 *   wander      how much it glances around by itself
 *   blinkEvery  seconds between blinks (0 = never)
 *   bounce      how much it bobs: with its voice while talking, gently otherwise
 *   browShow    how visible the eyebrows are (0 = hidden, 1 = fully shown)
 *   browRaise   eyebrows up (+) or down (-)
 *   browArch    + arched (surprised, interested), - flat or frowning
 *   browTilt    eyebrow angle (+ = cross, - = worried)
 *   mouthSmile  + smile, - frown
 *   mouthOpen   how open the mouth is when NOT talking
 *   mouthWidth  1 = normal width
 *   zzz         0 = none, 1 = sleepy Zs floating up (sleeping)
 *   hand        0 = none, 1 = a thinking hand under the chin, like 🤔 (thinking)
 *
 * Changing expression doesn't jump: every number glides towards its new value
 * a little each frame. That's called EASING.
 *
 * The Pi draws exactly the same shapes in Python: pi/bolt_body/face.py.
 */

const BoltFace = (() => {
  const KEYS = ["open", "lowerLid", "tilt", "pupil", "lookX", "lookY", "wander", "blinkEvery", "bounce",
                "browShow", "browRaise", "browArch", "browTilt", "mouthSmile", "mouthOpen", "mouthWidth", "zzz", "hand"];
  const WIDTH = 320, HEIGHT = 240;  // the robot's screen
  const ZZZ_SECONDS = 3;            // how long one sleepy Z takes to float away
  const HAND_X = 0.11;              // how far right of the mouth's middle the thinking hand sits

  /** The full settings for one eye in one expression: defaults, then the expression, then that eye. */
  function paramsFor(config, name, side) {
    const exp = config.expressions[name] || {};
    const base = Object.fromEntries(Object.entries(exp).filter(([k]) => k !== "left" && k !== "right"));
    return { ...config.defaults, ...base, ...(exp[side] || {}) };
  }

  /** Points along a curved line from (x0,y0) to (x1,y1), bending towards (cx,cy). */
  function curve(x0, y0, cx, cy, x1, y1, steps = 20) {
    const pts = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps, u = 1 - t;
      pts.push([u * u * x0 + 2 * u * t * cx + t * t * x1, u * u * y0 + 2 * u * t * cy + t * t * y1]);
    }
    return pts;
  }

  /**
   * Work out every shape on the face. The browser and the Pi use the same maths,
   * so they look the same. W, H: the screen size in pixels.
   * p: {left, right} numbers right now. blink: {left, right} 0..1.
   * bob: how far the face moves up (fraction of H). level: how loud Bolt is talking (0..1).
   */
  function geometry(W, H, p, face, blink, bob, level, time = 0) {
    const shapes = { eyes: {}, brows: {} };
    const ew = face.eyeWidth * W, eh = face.eyeHeight * H;
    for (const side of ["left", "right"]) {
      const q = p[side];
      const dir = side === "left" ? -1 : 1;
      // The whole eye shifts a little towards where it's looking; the pupil moves further.
      const cx = W / 2 + dir * face.eyeSpacing * W / 2 + q.lookX * face.lookRange * ew * 0.12;
      const cy = face.eyeY * H - bob * H + q.lookY * face.lookRange * eh * 0.12;
      const box = { x: cx - ew / 2, y: cy - eh / 2, w: ew, h: eh, r: face.corner * Math.min(ew, eh) };
      const pr = face.pupilRadius * eh * q.pupil;
      const px = cx + q.lookX * face.lookRange * (ew / 2 - pr * 0.6);
      const py = cy + q.lookY * face.lookRange * (eh / 2 - pr * 0.6);

      // Lids, measured in this eye's own half-height (hh) and half-width (hw).
      const hh = eh / 2, hw = ew / 2;
      const open = Math.max(0, q.open * (1 - blink[side]));
      const lowY = cy + 1.15 * hh - q.lowerLid * 1.15 * hh;
      const smile = 0.5 * hh * q.lowerLid * Math.min(1, open * 2);
      const pad = hw * 0.3;
      const bottom = curve(cx - hw - pad, lowY + smile * 0.4, cx, lowY - smile, cx + hw + pad, lowY + smile * 0.4);
      const edgeY = lowY + (cy - 1.05 * hh - lowY) * open;
      const inner = side === "left" ? 1 : -1;  // the left eye's inner corner is on its right
      const lean = Math.tan((q.tilt * Math.PI) / 180) * hw;
      const arch = 0.45 * hh * Math.min(1, open * 1.5);
      const top = curve(cx - hw - pad, edgeY - lean * inner, cx, edgeY - arch, cx + hw + pad, edgeY + lean * inner);

      shapes.eyes[side] = { box, ring: 0.07 * Math.min(ew, eh), px, py, pr, top, bottom };

      // Eyebrow: a curved, tapered line above the eye. Each point is [x, y, thickness].
      const by = box.y - face.browGap * H - q.browRaise * 0.06 * H;
      const half = ew * 0.42, thick = face.browThickness * H;
      const browLean = Math.tan((q.browTilt * Math.PI) / 180) * half;
      const pts = [];
      for (let i = 0; i <= 20; i++) {
        const t = i / 20, s = 2 * t - 1;               // s goes from -1 (left end) to 1 (right end)
        const w = thick * (0.45 + 0.55 * Math.sin(Math.PI * t));   // thickest in the middle
        const y = by - q.browArch * 0.06 * H * (1 - s * s) + browLean * inner * s;
        pts.push([cx - half + 2 * half * t, Math.max(w / 2 + 1, y), w]);  // never off the top of the screen
      }
      shapes.brows[side] = { pts, show: Math.max(0, Math.min(1, q.browShow)) };
    }

    // Mouth: shared by both sides (we use the average of the two eyes' numbers).
    const avg = (k) => (p.left[k] + p.right[k]) / 2;
    const mx = W / 2, my = face.mouthY * H - bob * H;
    const half = (face.mouthWidth * W / 2) * avg("mouthWidth");
    const bend = avg("mouthSmile") * 0.07 * H;   // + smile: the middle dips below the corners
    const opening = Math.min(1, avg("mouthOpen") + level * 0.9) * 0.1 * H;
    shapes.mouth = {
      upper: curve(mx - half, my, mx, my + bend, mx + half, my),
      lower: curve(mx - half, my, mx, my + bend + opening * 2, mx + half, my),
      open: opening, thick: 0.03 * H,
    };

    // Thinking hand (like the 🤔 emoji): a fist under the chin, index finger up beside the
    // mouth, thumb tucked under it. It rises from the bottom of the screen as it appears.
    const hand = Math.max(0, Math.min(1, avg("hand") || 0));
    shapes.hand = null;
    if (hand > 0.01) {
      const dy = (1 - hand) * 0.25 * H - bob * H, hx = mx + HAND_X * W;
      shapes.hand = {
        alpha: hand,
        fist: { x: hx, y: 0.84 * H + dy, w: 0.15 * W, h: 0.3 * H, r: 0.06 * H },
        finger: [[hx + 0.03 * W, 0.88 * H + dy], [hx + 0.04 * W, 0.765 * H + dy]], fingerThick: 0.065 * H,
        thumb: [[hx + 0.03 * W, 0.935 * H + dy], [hx - 0.03 * W, 0.915 * H + dy]], thumbThick: 0.05 * H,
        creases: [0.9, 0.955].map((y) => [[hx + 0.075 * W, y * H + dy], [hx + 0.135 * W, y * H + dy]]),
        creaseThick: 0.014 * H,
      };
    }

    // Sleepy Zs: three of them drift up and away from the right eye, one after
    // another, growing and fading as they rise. Each takes ZZZ_SECONDS to float up.
    const zzz = Math.max(0, Math.min(1, avg("zzz") || 0));
    shapes.zzz = [];
    if (zzz > 0.01) {
      const eye = shapes.eyes.right.box;
      const x0 = eye.x + eye.w * 0.95, y0 = eye.y + eye.h * 0.4;   // beside the (closed) eye
      for (let i = 0; i < 3; i++) {
        const phase = ((time / ZZZ_SECONDS) + i / 3) % 1;      // 0 = just appeared, 1 = gone
        const size = H * (0.045 + 0.05 * phase);
        shapes.zzz.push({
          x: x0 + phase * 0.09 * W, y: Math.max(size, y0 - phase * 0.3 * H), size,
          alpha: zzz * Math.sin(Math.PI * phase), thick: size * 0.2,
        });
      }
    }
    return shapes;
  }

  function roundRect(ctx, b) {
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(b.x, b.y, b.w, b.h, b.r) : ctx.rect(b.x, b.y, b.w, b.h);
  }

  /** Add a curve to the current shape. `start: true` begins a new line; otherwise it carries on from the last point. */
  function polyline(ctx, pts, start = false) {
    pts.forEach(([x, y], i) => (start && i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
  }

  function draw(ctx, W, H, p, config, blink = { left: 0, right: 0 }, bob = 0, level = 0, time = 0) {
    const col = config.colors;
    const g = geometry(W, H, p, config.face, blink, bob, level, time);
    ctx.save();
    ctx.fillStyle = col.background; ctx.fillRect(0, 0, W, H);

    for (const side of ["left", "right"]) {
      const e = g.eyes[side];
      ctx.save();
      roundRect(ctx, e.box); ctx.clip();                        // everything stays inside the eye
      ctx.fillStyle = col.irisRing; ctx.fillRect(e.box.x, e.box.y, e.box.w, e.box.h);
      ctx.fillStyle = col.iris;
      roundRect(ctx, { x: e.box.x + e.ring, y: e.box.y + e.ring, w: e.box.w - 2 * e.ring, h: e.box.h - 2 * e.ring,
                       r: Math.max(0, e.box.r - e.ring) });
      ctx.fill();
      const dot = (x, y, r, c) => { ctx.beginPath(); ctx.arc(x, y, Math.max(0, r), 0, Math.PI * 2); ctx.fillStyle = c; ctx.fill(); };
      dot(e.px, e.py, e.pr, col.pupil);
      dot(e.px + e.pr * 0.45, e.py - e.pr * 0.5, e.pr * 0.32, col.highlight);
      dot(e.px + e.pr * 0.95, e.py - e.pr * 0.05, e.pr * 0.14, col.highlight);
      ctx.restore();
      // Eyelids are drawn just outside the eye's outline too, so a shut eye leaves no faint edge.
      const lx0 = e.top[0][0], lx1 = e.top[e.top.length - 1][0];
      ctx.fillStyle = col.lid;
      ctx.beginPath(); ctx.moveTo(lx0, e.box.y - 2); polyline(ctx, e.top); ctx.lineTo(lx1, e.box.y - 2); ctx.closePath(); ctx.fill();
      ctx.beginPath(); ctx.moveTo(lx0, e.box.y + e.box.h + 2); polyline(ctx, e.bottom); ctx.lineTo(lx1, e.box.y + e.box.h + 2); ctx.closePath(); ctx.fill();

      const b = g.brows[side];                                   // eyebrow (only if showing)
      if (b.show > 0.01) {
        ctx.globalAlpha = b.show; ctx.fillStyle = col.brow;
        ctx.beginPath();
        b.pts.forEach(([x, y, w], i) => (i ? ctx.lineTo(x, y - w / 2) : ctx.moveTo(x, y - w / 2)));
        [...b.pts].reverse().forEach(([x, y, w]) => ctx.lineTo(x, y + w / 2));
        ctx.closePath(); ctx.fill();
        for (const [x, y, w] of [b.pts[0], b.pts[b.pts.length - 1]]) {   // round ends
          ctx.beginPath(); ctx.arc(x, y, w / 2, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalAlpha = 1;
      }
    }

    const m = g.mouth;                                           // mouth
    ctx.strokeStyle = col.mouth; ctx.fillStyle = col.mouth; ctx.lineWidth = m.thick; ctx.lineCap = "round"; ctx.lineJoin = "round";
    ctx.beginPath(); polyline(ctx, m.upper, true);
    if (m.open > 0.5) { polyline(ctx, [...m.lower].reverse()); ctx.closePath(); ctx.fill(); }
    ctx.stroke();

    const hd = g.hand;                                           // thinking hand
    if (hd) {
      const line = ([a, b], thick, colour) => {
        ctx.strokeStyle = colour; ctx.lineWidth = thick;
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
      };
      ctx.globalAlpha = hd.alpha; ctx.fillStyle = col.mouth;
      roundRect(ctx, hd.fist); ctx.fill();
      line(hd.finger, hd.fingerThick, col.mouth);
      line(hd.thumb, hd.thumbThick, col.mouth);
      ctx.globalAlpha = 1;
      for (const c of hd.creases) line(c, hd.creaseThick, col.background);
      ctx.strokeStyle = col.mouth;
    }

    for (const z of g.zzz) {                                     // sleepy Zs: a Z is three strokes
      const h = z.size / 2;
      ctx.globalAlpha = z.alpha; ctx.lineWidth = z.thick;
      ctx.beginPath(); ctx.moveTo(z.x - h, z.y - h); ctx.lineTo(z.x + h, z.y - h);
      ctx.lineTo(z.x - h, z.y + h); ctx.lineTo(z.x + h, z.y + h); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  /**
   * A living face on a <canvas>.
   *
   * LESSON: Calm mode
   * Phones have a setting for people who feel unwell with lots of movement
   * ("Remove animations" on Android, "Reduce motion" on iPhone). On the chat
   * page the face moves HALF as much when it's on. The Studio passes
   * {fullMotion: true}, because there you're designing the movement.
   */
  class Face {
    constructor(canvas, config, options = {}) {
      this.canvas = canvas;
      this.config = config;
      this.state = "idle";
      this.level = 0;  // how loud Bolt is speaking right now (0 to 1)
      this.calmRequested = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
      this.motion = this.calmRequested && !options.fullMotion ? 0.5 : 1;
      this.now = { left: paramsFor(config, "idle", "left"), right: paramsFor(config, "idle", "right") };
      this.glance = { x: 0, y: 0, aimX: 0, aimY: 0, next: 0 };
      const soon = performance.now() + 2000;
      this.blinks = { left: { start: -1, next: soon }, right: { start: -1, next: soon } };
      this.last = performance.now();
      this.frame = this.frame.bind(this);
      requestAnimationFrame(this.frame);
    }

    setState(name) { if (this.config.expressions[name]) this.state = name; }
    setLevel(level) { this.level = Math.max(0, Math.min(1, level)); }
    setConfig(config) { this.config = config; }
    setFullMotion(on) { this.motion = this.calmRequested && !on ? 0.5 : 1; }

    /** One eye's blink: 0 = open, 1 = shut. A quick close and open (160 ms). */
    blinkAmount(state, every, t) {
      if (every > 0 && state.start < 0 && t > state.next) state.start = t;
      if (state.start < 0) return 0;
      const k = (t - state.start) / 160;
      if (k >= 1) { state.start = -1; state.next = t + every * 1000 * (0.6 + Math.random() * 0.8); return 0; }
      return k < 0.5 ? k * 2 : 2 - k * 2;
    }

    frame(t) {
      const dt = Math.min(0.1, (t - this.last) / 1000);
      this.last = t;
      const ease = 1 - Math.exp(-dt * 9);
      const target = { left: paramsFor(this.config, this.state, "left"), right: paramsFor(this.config, this.state, "right") };

      // Glancing around: every couple of seconds both eyes pick a new spot (often the middle)...
      const wander = ((target.left.wander + target.right.wander) / 2) * this.motion;
      const g = this.glance;
      if (t > g.next) {
        const toMiddle = Math.random() < 0.4;
        g.aimX = toMiddle ? 0 : (Math.random() * 2 - 1) * wander;
        g.aimY = toMiddle ? 0 : (Math.random() * 2 - 1) * wander * 0.15;  // mostly sideways
        g.next = t + 1500 + Math.random() * 2500;
      }
      // ...and glide there: fast at first, then settling (about 0.25 s).
      const glide = 1 - Math.exp(-dt * 14);
      g.x += (g.aimX - g.x) * glide;
      g.y += (g.aimY - g.y) * glide;
      const driftX = Math.sin(t / 1700) * 0.03 * wander, driftY = Math.sin(t / 2300 + 1) * 0.01 * wander;

      // Blinking: each eye has its own timer; same speed = blink together.
      const blink = { left: this.blinkAmount(this.blinks.left, target.left.blinkEvery, t) };
      blink.right = target.right.blinkEvery === target.left.blinkEvery
        ? blink.left : this.blinkAmount(this.blinks.right, target.right.blinkEvery, t);

      // Bobbing: with the voice while talking, a slow "breathing" bob otherwise.
      const breathe = 0.5 + 0.5 * Math.sin((t / 2400) * Math.PI * 2);
      const lift = (this.level * 0.05 + (1 - this.level) * 0.035 * breathe) * this.motion;

      const shown = {};
      for (const side of ["left", "right"]) {
        const now = this.now[side], goal = target[side];
        for (const k of KEYS) now[k] += ((goal[k] ?? 0) - now[k]) * ease;
        shown[side] = { ...now, lookX: now.lookX + g.x + driftX, lookY: now.lookY + g.y + driftY };
      }
      const bob = ((this.now.left.bounce + this.now.right.bounce) / 2) * lift;
      draw(this.canvas.getContext("2d"), this.canvas.width, this.canvas.height, shown, this.config, blink, bob, this.level, t / 1000);
      requestAnimationFrame(this.frame);
    }
  }

  /** Make the canvas sharp on high-resolution screens (keeps the robot's 4:3 shape). */
  function fit(canvas) {
    const ratio = window.devicePixelRatio || 1;
    const w = Math.round(canvas.getBoundingClientRect().width * ratio);
    if (w && canvas.width !== w) { canvas.width = w; canvas.height = Math.round(w * HEIGHT / WIDTH); }
  }

  return { Face, draw, geometry, paramsFor, fit, KEYS, WIDTH, HEIGHT };
})();
