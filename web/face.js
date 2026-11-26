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
 *   roll        0 = none, 1 = rolls her eyes as this face starts (unimpressed)
 *   hand        0 = none, 1 = a thinking hand under the chin, like 🤔 (thinking)
 *
 * The Christmas hat isn't part of an expression: it's on or off for every mood
 * (face.setHat(true)), switched in the Studio's Body tab.
 *
 * Changing expression doesn't jump: every number glides towards its new value
 * a little each frame. That's called EASING.
 *
 * The Pi draws exactly the same shapes in Python: pi/bolt_body/face.py.
 */

const BoltFace = (() => {
  const KEYS = ["open", "lowerLid", "tilt", "pupil", "lookX", "lookY", "wander", "blinkEvery", "bounce",
                "browShow", "browRaise", "browArch", "browTilt", "mouthSmile", "mouthOpen", "mouthWidth", "zzz", "hand", "roll"];
  /** An eye roll (the same path as eye_roll() in pi/bolt_body/animate.py): up, across the top, back. */
  const ROLL_MS = 1100;
  function eyeRoll(since, size = 1) {
    const p = since / ROLL_MS;
    if (!(p >= 0 && p < 1)) return [0, 0];
    const rise = Math.sin(Math.PI * p);
    return [-0.8 * Math.cos(Math.PI * p) * Math.sqrt(rise) * size, -0.95 * rise * size];
  }
  const WIDTH = 320, HEIGHT = 240;  // the robot's screen
  const ZZZ_SECONDS = 3;            // how long one sleepy Z takes to float away
  const HAND_LIFT = 0.055;          // the face lifts this much (of the height) when the hand is up
  const HAT_DROP = 0.03;            // with the Christmas hat on, the face sits this much lower
  // Snow that comes with the hat: behind her eyes and mouth, piled up in the bottom-left corner.
  // (pi/bolt_body/face.py has the same numbers, so her screen matches.)
  const SNOW_COLOUR = "#eaf2fb", SNOW_STEPS = 64;
  const FLAKES = [[0.05, 0.10], [0.13, 0.30], [0.04, 0.50], [0.21, 0.07], [0.50, 0.04], [0.78, 0.06],
                  [0.95, 0.14], [0.88, 0.34], [0.96, 0.52], [0.10, 0.70], [0.62, 0.02], [0.36, 0.03]];
  function snowHeight(u) {
    return 0.014 + 0.13 * Math.exp(-((u / 0.2) ** 2)) + 0.012 * Math.exp(-(((1 - u) / 0.1) ** 2))
      + 0.005 * Math.sin(2 * Math.PI * 5.3 * u + 1.2) + 0.004 * Math.sin(2 * Math.PI * 9.1 * u + 0.4);
  }
  function drawSnow(ctx, W, H, amount) {
    const sink = (1 - amount) * 0.14 * H;
    ctx.fillStyle = SNOW_COLOUR;
    ctx.beginPath();
    for (let i = 0; i <= SNOW_STEPS; i++) ctx.lineTo(W * i / SNOW_STEPS, H - snowHeight(i / SNOW_STEPS) * H + sink);
    ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fill();
    if (amount > 0.5) {
      for (const [x, y] of FLAKES) { ctx.beginPath(); ctx.arc(x * W, y * H, 0.011 * H, 0, Math.PI * 2); ctx.fill(); }
    }
  }

  /**
   * STICKERS: the thinking hand and the Christmas hat are pictures (web/stickers/), placed
   * where stickers.json says. loadStickers() fetches them once; until they arrive (or if
   * they can't), the face is simply drawn without them.
   */
  let STICKERS = {};
  const tinted = new Map();   // sticker pictures already coloured in, by name + colour
  function loadStickers() {
    return fetch("/static/stickers/stickers.json").then((r) => r.json()).then((places) =>
      Promise.all(Object.entries(places).filter(([name]) => !name.startsWith("_")).map(([name, place]) =>
        new Promise((done) => {
          const image = new Image();
          image.onload = () => { STICKERS[name] = { ...place, image }; done(); };
          image.onerror = done;
          image.src = "/static/stickers/" + place.file;
        })))).catch(() => {});
  }

  /** Where each sticker goes right now: the same maths as place_stickers() in face.py. */
  function placeStickers(W, H, places, amounts, mouth, bob, time) {
    const out = [];
    for (const [name, s] of Object.entries(places)) {
      const a = Math.max(0, Math.min(1, amounts[name] || 0));
      if (a <= 0.01) continue;
      let x, y;
      if (s.at === "mouth") { x = mouth[0] + s.x * W; y = mouth[1] + s.y * H; }
      else { x = s.x * W; y = s.y * H - bob * H; }
      y += (1 - a) * 0.3 * H * (s.enter === "down" ? -1 : 1);        // slides in as it appears
      const angle = (s.angle || 0) + (s.sway || 0) * Math.sin(time * 1.6);
      out.push({ name, x, y, width: s.width * W, anchor: s.anchor, angle, alpha: a, tint: s.tint || null });
    }
    return out;
  }

  /** A grey sticker coloured in (white -> the colour, grey -> a darker shade), like face.py's multiply. */
  function tintedImage(name, image, colour) {
    const key = name + colour;
    if (!tinted.has(key)) {
      const c = document.createElement("canvas");
      c.width = image.naturalWidth; c.height = image.naturalHeight;
      const x = c.getContext("2d");
      x.drawImage(image, 0, 0);
      x.globalCompositeOperation = "multiply"; x.fillStyle = colour; x.fillRect(0, 0, c.width, c.height);
      x.globalCompositeOperation = "destination-in"; x.drawImage(image, 0, 0);   // keep the see-through parts
      tinted.set(key, c);
    }
    return tinted.get(key);
  }

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
  function geometry(W, H, p, face, blink, bob, level, time = 0, hat = 0, stickers = STICKERS) {
    const shapes = { eyes: {}, brows: {} };
    const hand = Math.max(0, Math.min(1, ((p.left.hand || 0) + (p.right.hand || 0)) / 2));
    hat = Math.max(0, Math.min(1, hat || 0));
    const hatBob = bob;
    bob = bob + HAND_LIFT * hand - HAT_DROP * hat;   // chin on her hand lifts the face; the hat pushes it down
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

    // Stickers: pictures placed on the face (the thinking hand, the Christmas hat)
    shapes.stickers = placeStickers(W, H, stickers, { hand, hat }, [mx, my], hatBob, time);
    shapes.hat = hat > 0.01;

    // Sleepy Zs: three of them drift up and away from the right eye, one after
    // another, growing and fading as they rise. Each takes ZZZ_SECONDS to float up.
    const zzz = Math.max(0, Math.min(1, avg("zzz") || 0));
    shapes.zzz = [];
    if (zzz > 0.01) {
      // Beside the right eye, or the LEFT one when the Christmas hat's pom-pom is in the way
      const [side, away] = shapes.hat ? ["left", -1] : ["right", 1];
      const eye = shapes.eyes[side].box;
      const x0 = eye.x + eye.w * (0.5 + 0.45 * away), y0 = eye.y + eye.h * 0.4;   // beside the (closed) eye
      for (let i = 0; i < 3; i++) {
        const phase = ((time / ZZZ_SECONDS) + i / 3) % 1;      // 0 = just appeared, 1 = gone
        const size = H * (0.045 + 0.05 * phase);
        shapes.zzz.push({
          x: x0 + away * phase * 0.09 * W, y: Math.max(size, y0 - phase * 0.3 * H), size,
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

  function draw(ctx, W, H, p, config, blink = { left: 0, right: 0 }, bob = 0, level = 0, time = 0, hat = 0) {
    const col = config.colors;
    const g = geometry(W, H, p, config.face, blink, bob, level, time, hat);
    ctx.save();
    ctx.fillStyle = col.background; ctx.fillRect(0, 0, W, H);
    if (hat > 0.01) drawSnow(ctx, W, H, Math.min(1, hat));

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

    for (const z of g.zzz) {                                     // sleepy Zs: a Z is three strokes
      const h = z.size / 2;
      ctx.globalAlpha = z.alpha; ctx.lineWidth = z.thick;
      ctx.beginPath(); ctx.moveTo(z.x - h, z.y - h); ctx.lineTo(z.x + h, z.y - h);
      ctx.lineTo(z.x - h, z.y + h); ctx.lineTo(z.x + h, z.y + h); ctx.stroke();
    }
    ctx.globalAlpha = 1;

    for (const st of g.stickers) {                               // stickers on top of everything
      const sticker = STICKERS[st.name];
      const pic = st.tint ? tintedImage(st.name, sticker.image, col[st.tint] || "#ffffff") : sticker.image;
      const w = st.width, h = w * sticker.image.naturalHeight / sticker.image.naturalWidth;
      ctx.save();
      ctx.globalAlpha = st.alpha;
      ctx.translate(st.x, st.y); ctx.rotate(st.angle * Math.PI / 180);
      ctx.drawImage(pic, -st.anchor[0] * w, -st.anchor[1] * h, w, h);
      ctx.restore();
    }
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

    setState(name) {
      if (!this.config.expressions[name]) return;
      if (name !== this.state) {                       // a face with an eye roll rolls as it starts
        const size = paramsFor(this.config, name, "left").roll || 0;
        this.roll = size > 0.05 ? { start: performance.now(), size } : null;
      }
      this.state = name;
      if (name === "listening") this.prop = null;     // back to listening: put the prop down
    }
    /** Hold up a prop (an emoji, plus a few characters like "8°"), the same as the Pi's draw_prop. */
    showProp(emoji, text = "", seconds = 15) { this.prop = { emoji, text, until: performance.now() + seconds * 1000 }; }
    setLevel(level) { this.level = Math.max(0, Math.min(1, level)); }
    setConfig(config) { this.config = config; }
    setFullMotion(on) { this.motion = this.calmRequested && !on ? 0.5 : 1; }
    /** The Christmas hat on or off. It slides on (or off) rather than popping. */
    setHat(on) { this.hatTarget = on ? 1 : 0; }

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
      if (this.roll) {
        const [rx, ry] = eyeRoll(t - this.roll.start, this.roll.size * this.motion);
        for (const side of ["left", "right"]) {          // her lids lift a little, so the pupils show going round
          shown[side].lookX += rx; shown[side].lookY += ry;
          shown[side].open = Math.min(1, shown[side].open - 0.35 * ry);
        }
      }
      const bob = ((this.now.left.bounce + this.now.right.bounce) / 2) * lift;
      this.hat = (this.hat || 0) + ((this.hatTarget || 0) - (this.hat || 0)) * (1 - Math.exp(-dt * 4));
      const ctx = this.canvas.getContext("2d"), W = this.canvas.width, H = this.canvas.height;
      draw(ctx, W, H, shown, this.config, blink, bob, this.level, t / 1000, this.hat);
      if (this.prop && t < this.prop.until) {                    // the prop, tucked into the corner
        const cx = W * 0.885, cy = H * 0.74, size = H * 0.25;
        ctx.save();
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.font = `${size}px "Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", sans-serif`;
        ctx.fillText(this.prop.emoji, cx, cy);
        if (this.prop.text) {
          ctx.fillStyle = this.config.colors.mouth;
          ctx.font = `${H * 0.095}px system-ui, sans-serif`;
          ctx.fillText(this.prop.text, cx, cy + size * 0.5 + H * 0.07);
        }
        ctx.restore();
      } else if (this.prop) this.prop = null;
      requestAnimationFrame(this.frame);
    }
  }

  /** Make the canvas sharp on high-resolution screens (keeps the robot's 4:3 shape). */
  function fit(canvas) {
    const ratio = window.devicePixelRatio || 1;
    const w = Math.round(canvas.getBoundingClientRect().width * ratio);
    if (w && canvas.width !== w) { canvas.width = w; canvas.height = Math.round(w * HEIGHT / WIDTH); }
  }

  /** Should the Christmas hat be on? mode: "on", "off" or "auto" (25 Nov to 6 Jan, the same
   *  rule as christmas_time() in robot_friend/body_settings.py). Old saved true/false still work. */
  function hatWanted(mode, day = new Date()) {
    if (mode === true || mode === "on") return true;
    if (mode !== "auto") return false;
    const m = day.getMonth() + 1, d = day.getDate();             // getMonth() counts from 0
    return (m === 11 && d >= 25) || m === 12 || (m === 1 && d <= 6);
  }

  loadStickers();
  return { Face, draw, geometry, paramsFor, fit, loadStickers, hatWanted, KEYS, WIDTH, HEIGHT };
})();
