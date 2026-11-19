/*
 * LESSON: Drawing an eye
 * ======================
 * Each eye is drawn fresh about 60 times a second, in layers, like a cartoon:
 *
 *   1. dark background (the round screen)
 *   2. iris (the coloured circle) with a darker ring
 *   3. pupil (black) and two white highlights, which make it look shiny and alive
 *   4. eyelids: shapes in the lid colour that cover the top and bottom
 *
 * An EXPRESSION is just a handful of numbers (see expressions.json):
 *   open      how far the top lid is lifted (0 = shut, 1 = wide)
 *   lowerLid  how far the bottom lid rises (high = a happy squint)
 *   tilt      angle of the top lid, in degrees (+ = cross, - = worried)
 *   pupil     pupil size (big = interested, small = focused)
 *   lookX/Y   where it's looking (-1 to 1)
 *   wander    how much it glances around by itself
 *   blinkEvery  seconds between blinks (0 = never)
 *   bounce    how much it bobs: along with its voice while talking, and a
 *             slow "breathing" bob the rest of the time
 *
 * Changing between expressions doesn't jump: every number glides towards
 * its new value a little each frame. That's called EASING.
 *
 * The Pi draws the same shapes in Python: pi/bolt_body/eyes.py.
 */

const BoltEyes = (() => {
  const KEYS = ["open", "lowerLid", "tilt", "pupil", "lookX", "lookY", "wander", "blinkEvery", "bounce"];

  /** The full settings for one eye in one expression. */
  function paramsFor(config, name, side) {
    const exp = config.expressions[name] || {};
    return { ...config.defaults, ...exp, ...(exp[side] || {}) };
  }

  /** Points along a curved line from (x0,y0) to (x1,y1), bending through (cx,cy). */
  function curve(x0, y0, cx, cy, x1, y1, steps = 24) {
    const pts = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps, u = 1 - t;
      pts.push([u * u * x0 + 2 * u * t * cx + t * t * x1, u * u * y0 + 2 * u * t * cy + t * t * y1]);
    }
    return pts;
  }

  /**
   * Work out every shape for one eye. Both the browser and the Pi use the
   * same maths, so they look the same. Sizes are in pixels for a square of `size`.
   * side: "left" or "right" (as you look at Bolt). p: that eye's numbers right now.
   */
  function geometry(size, p, eye, side, blink, bob) {
    const R = size / 2, c = R;
    const open = Math.max(0, p.open * (1 - blink));
    const irisR = eye.irisRadius * R;
    const ix = c + p.lookX * eye.lookRange * R;
    const iy = c + p.lookY * eye.lookRange * R + bob * R;
    const pupilR = eye.pupilRadius * irisR * p.pupil;

    // Bottom lid: normally hidden below the screen; rises and curves up for a smile.
    const lowY = c + 1.15 * R - p.lowerLid * 1.15 * R;
    const smile = 0.5 * R * p.lowerLid * Math.min(1, open * 2);  // flattens as the eye shuts
    const bottom = curve(-0.2 * R, lowY + smile * 0.4, c, lowY - smile, size + 0.2 * R, lowY + smile * 0.4);

    // Top lid. Shut, its edge rests on the bottom lid; wide open, it's above the
    // screen. "tilt" lowers the inner corner (the side nearest the other eye),
    // so the two eyes mirror each other.
    const edgeY = lowY + (c - 1.05 * R - lowY) * open;
    const inner = side === "left" ? 1 : -1;  // the left eye's inner corner is on its right
    const lean = Math.tan((p.tilt * Math.PI) / 180) * R;
    const yLeft = edgeY - lean * inner, yRight = edgeY + lean * inner;
    const arch = 0.45 * R * Math.min(1, open * 1.5);  // open eyes are rounder
    const top = curve(-0.2 * R, yLeft, c, edgeY - arch, size + 0.2 * R, yRight);

    return { R, c, irisR, ix, iy, pupilR, top, bottom };
  }

  function draw(ctx, size, p, config, side, blink = 0, bob = 0) {
    const col = config.colors;
    const g = geometry(size, p, config.eye, side, blink, bob);
    ctx.save();
    ctx.clearRect(0, 0, size, size);
    ctx.beginPath(); ctx.arc(g.c, g.c, g.R, 0, Math.PI * 2); ctx.clip();  // round screen
    ctx.fillStyle = col.background; ctx.fillRect(0, 0, size, size);

    const circle = (x, y, r, fill) => { ctx.beginPath(); ctx.arc(x, y, Math.max(0, r), 0, Math.PI * 2); ctx.fillStyle = fill; ctx.fill(); };
    circle(g.ix, g.iy, g.irisR, col.irisRing);
    circle(g.ix, g.iy, g.irisR * 0.86, col.iris);
    circle(g.ix, g.iy, g.pupilR, col.pupil);
    circle(g.ix - g.irisR * 0.32, g.iy - g.irisR * 0.34, g.irisR * 0.17, col.highlight);
    circle(g.ix + g.irisR * 0.3, g.iy + g.irisR * 0.28, g.irisR * 0.07, col.highlight);

    ctx.fillStyle = col.lid;
    ctx.beginPath(); ctx.moveTo(-1, -1);
    g.top.forEach(([x, y]) => ctx.lineTo(x, y));
    ctx.lineTo(size + 1, -1); ctx.closePath(); ctx.fill();
    ctx.beginPath(); ctx.moveTo(-1, size + 1);
    g.bottom.forEach(([x, y]) => ctx.lineTo(x, y));
    ctx.lineTo(size + 1, size + 1); ctx.closePath(); ctx.fill();
    ctx.restore();
  }

  /**
   * A pair of animated eyes on two <canvas> elements.
   *
   * LESSON: Calm mode
   * Phones have a setting for people who feel unwell with lots of movement on
   * screen ("Remove animations" on Android, "Reduce motion" on iPhone). Web
   * pages should respect it, so on the chat page Bolt's eyes move HALF as much
   * when it's on. The Eye Studio passes {fullMotion: true}, because there you're
   * designing the movement and need to see it properly.
   */
  class Eyes {
    constructor(leftCanvas, rightCanvas, config, options = {}) {
      this.canvases = { left: leftCanvas, right: rightCanvas };
      this.config = config;
      this.state = "idle";
      this.level = 0;  // how loud Bolt is speaking right now (0 to 1)
      this.calmRequested = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
      this.motion = this.calmRequested && !options.fullMotion ? 0.5 : 1;
      this.now = { left: paramsFor(config, "idle", "left"), right: paramsFor(config, "idle", "right") };
      this.glance = { x: 0, y: 0, next: 0 };
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

    /** One eye's blink: 0 = open, 1 = shut. A quick close and open (160 ms), at a slightly random rhythm. */
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
      const ease = 1 - Math.exp(-dt * 9);  // glide most of the way in about a third of a second
      const target = { left: paramsFor(this.config, this.state, "left"), right: paramsFor(this.config, this.state, "right") };

      // Glancing around: every couple of seconds both eyes look at a new spot together.
      const wander = ((target.left.wander + target.right.wander) / 2) * this.motion;
      if (t > this.glance.next) {
        this.glance.x = (Math.random() * 2 - 1) * wander;
        this.glance.y = (Math.random() * 2 - 1) * wander * 0.5;
        this.glance.next = t + 1200 + Math.random() * 2200;
      }

      // Blinking: each eye has its own timer. If both eyes blink at the same
      // rate, they share the left one's, so they blink together like real eyes.
      const blink = { left: this.blinkAmount(this.blinks.left, target.left.blinkEvery, t) };
      blink.right = target.right.blinkEvery === target.left.blinkEvery
        ? blink.left
        : this.blinkAmount(this.blinks.right, target.right.blinkEvery, t);

      // Bobbing: follows the voice while Bolt talks, and a slow, gentle
      // "breathing" bob the rest of the time.
      const breathe = 0.5 + 0.5 * Math.sin((t / 2400) * Math.PI * 2);
      const lift = (this.level * 0.1 + (1 - this.level) * 0.07 * breathe) * this.motion;

      for (const side of ["left", "right"]) {
        const now = this.now[side], goal = target[side];
        for (const k of KEYS) now[k] += (goal[k] - now[k]) * ease;
        const shown = { ...now, lookX: now.lookX + this.glance.x, lookY: now.lookY + this.glance.y };
        const canvas = this.canvases[side];
        if (!canvas) continue;
        draw(canvas.getContext("2d"), canvas.width, shown, this.config, side, blink[side], -now.bounce * lift);
      }
      requestAnimationFrame(this.frame);
    }
  }

  /** Make a canvas sharp on high-resolution screens. */
  function fit(canvas) {
    const ratio = window.devicePixelRatio || 1;
    const px = Math.round(canvas.getBoundingClientRect().width * ratio);
    if (px && canvas.width !== px) { canvas.width = px; canvas.height = px; }
  }

  return { Eyes, draw, geometry, paramsFor, fit, KEYS };
})();
