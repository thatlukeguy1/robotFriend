/*
 * The Studio's EYES tab. (This used to be its own page, the Eye Studio.)
 * Everything here edits one object called `design` (the same shape as
 * web/expressions.json). "Save to Bolt" sends it to the brain (PUT /expressions).
 * Wrapped in (() => { ... })() so its names don't clash with the other tabs.
 */
(() => {
const SETTINGS = [
  { key: "open", label: "Top lid open", min: 0, max: 1, step: 0.01 },
  { key: "lowerLid", label: "Bottom lid (smile)", min: 0, max: 1, step: 0.01 },
  { key: "tilt", label: "Lid tilt (+ cross, − worried)", min: -45, max: 45, step: 1 },
  { key: "pupil", label: "Pupil size", min: 0.2, max: 2, step: 0.01 },
  { key: "lookX", label: "Look left ↔ right", min: -1, max: 1, step: 0.01 },
  { key: "lookY", label: "Look up ↕ down", min: -1, max: 1, step: 0.01 },
  { key: "wander", label: "Glancing around", min: 0, max: 1, step: 0.01, bothOnly: true },
  { key: "blinkEvery", label: "Seconds between blinks (0 = never)", min: 0, max: 30, step: 0.5 },
  { key: "bounce", label: "Bob (with the voice when talking, gently otherwise)", min: 0, max: 3, step: 0.05 },
];
const SHAPE = [
  { key: "irisRadius", label: "Iris size", min: 0.2, max: 0.9, step: 0.01 },
  { key: "pupilRadius", label: "Pupil size (overall)", min: 0.1, max: 0.9, step: 0.01 },
  { key: "lookRange", label: "How far the eyes can look", min: 0, max: 0.5, step: 0.01 },
];
const COLOURS = [
  { key: "iris", label: "Iris" }, { key: "irisRing", label: "Iris ring" }, { key: "pupil", label: "Pupil" },
  { key: "highlight", label: "Shine" }, { key: "background", label: "Screen" }, { key: "lid", label: "Eyelids" },
];
const REQUIRED = ["idle", "sleeping", "listening", "thinking", "speaking", "happy", "confused"];
const DRAFT_KEY = "bolt-eye-draft";

let design, saved, eyes, current = "idle", side = "both", talking = false, deleteArmed = false;
const $ = (id) => document.getElementById(id);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ------------------------------------------------------------ loading
async function load() {
  const response = await fetch("/static/expressions.json", { cache: "no-store" });
  saved = await response.json();
  design = structuredClone(saved);
  let usedDraft = false;
  try {
    const draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    if (draft && !same(draft, saved)) { design = draft; usedDraft = true; }
  } catch (e) {}
  for (const c of document.querySelectorAll(".face canvas")) BoltEyes.fit(c);
  eyes = new BoltEyes.Eyes($("eye-left"), $("eye-right"), design, { fullMotion: true });
  $("calm-note").hidden = !eyes.calmRequested;
  renderAll();
  setStatus(usedDraft ? "Unsaved changes from last time (not on Bolt yet)" :
            response.headers.get("X-Bolt-Design") === "custom" ? "Showing your saved design" : "Showing the original design",
            usedDraft ? "dirty" : "");
}

function renderAll() { renderStates(); renderSliders(); renderLook(); updateButtons(); }

// ---------------------------------------------------------- expressions
function renderStates() {
  const box = $("states");
  box.innerHTML = "";
  for (const name of Object.keys(design.expressions)) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = name; b.setAttribute("aria-pressed", name === current);
    b.addEventListener("click", () => { current = name; deleteArmed = false; eyes.setState(name); renderAll(); });
    box.appendChild(b);
  }
}

$("add").addEventListener("click", () => {
  const name = $("new-name").value.trim().toLowerCase();
  if (!/^[a-z][a-z0-9_-]{0,23}$/.test(name)) return setStatus("Names use lowercase letters, numbers, - or _ (start with a letter).", "bad");
  if (design.expressions[name]) return setStatus(`There's already an expression called "${name}".`, "bad");
  design.expressions[name] = structuredClone(design.expressions[current]);
  current = name; $("new-name").value = "";
  changed(); eyes.setState(name); renderAll();
});

$("delete").addEventListener("click", () => {
  if (REQUIRED.includes(current)) return;
  if (!deleteArmed) { deleteArmed = true; $("delete").textContent = `Tap again to delete "${current}"`; return; }
  delete design.expressions[current];
  current = "idle"; deleteArmed = false; eyes.setState("idle");
  changed(); renderAll();
});

// ----------------------------------------------------------- the sliders
function valueFor(key, which) {
  return BoltEyes.paramsFor(design, current, which === "right" ? "right" : "left")[key];
}

function eyesDiffer(key) {
  return valueFor(key, "left") !== valueFor(key, "right");
}

function renderSliders() {
  $("tune-name").textContent = current;
  for (const b of $("sides").querySelectorAll("button")) b.setAttribute("aria-pressed", b.dataset.side === side);
  $("side-help").textContent = side === "both" ? "Changes apply to both eyes." :
    `Changes apply to the ${side} eye only (as you look at Bolt).`;
  const box = $("sliders");
  box.innerHTML = "";
  for (const s of SETTINGS) {
    const id = "s-" + s.key;
    const value = valueFor(s.key, side);
    const wrap = document.createElement("div"); wrap.className = "slider";
    const badge = side === "both" && eyesDiffer(s.key) ? '<span class="badge">eyes differ</span>' : "";
    const locked = s.bothOnly && side !== "both";
    if (locked) wrap.classList.add("disabled");
    wrap.innerHTML = `<label for="${id}"><span>${s.label}${badge}</span><output>${value}</output></label>
      <input type="range" id="${id}" min="${s.min}" max="${s.max}" step="${s.step}" value="${value}" ${locked ? "disabled" : ""}>
      ${locked ? '<span class="hint">Both eyes always look the same way. Change this under "Both eyes".</span>' : ""}`;
    box.appendChild(wrap);
    const input = wrap.querySelector("input"), out = wrap.querySelector("output");
    input.addEventListener("input", () => {
      const v = Number(input.value);
      out.textContent = v;
      const exp = design.expressions[current];
      if (side === "both") {
        exp[s.key] = v;
        for (const eye of ["left", "right"]) if (exp[eye]) { delete exp[eye][s.key]; if (!Object.keys(exp[eye]).length) delete exp[eye]; }
        wrap.querySelector(".badge")?.remove();
      } else {
        exp[side] = exp[side] || {};
        exp[side][s.key] = v;
      }
      changed();
    });
  }
}

for (const b of $("sides").querySelectorAll("button")) {
  b.addEventListener("click", () => { side = b.dataset.side; renderSliders(); });
}

$("match").addEventListener("click", () => {
  const exp = design.expressions[current];
  delete exp.left; delete exp.right;
  changed(); renderSliders();
});

// ------------------------------------------------------ colours and shape
function renderLook() {
  const colours = $("colours");
  colours.innerHTML = "";
  for (const c of COLOURS) {
    const id = "c-" + c.key;
    const wrap = document.createElement("div"); wrap.className = "colour";
    wrap.innerHTML = `<input type="color" id="${id}" value="${design.colors[c.key]}"><label for="${id}">${c.label}</label>`;
    wrap.querySelector("input").addEventListener("input", (e) => { design.colors[c.key] = e.target.value; changed(); });
    colours.appendChild(wrap);
  }
  const shape = $("shape");
  shape.innerHTML = "";
  for (const s of SHAPE) {
    const id = "e-" + s.key, value = design.eye[s.key];
    const wrap = document.createElement("div"); wrap.className = "slider";
    wrap.innerHTML = `<label for="${id}"><span>${s.label}</span><output>${value}</output></label>
      <input type="range" id="${id}" min="${s.min}" max="${s.max}" step="${s.step}" value="${value}">`;
    const input = wrap.querySelector("input"), out = wrap.querySelector("output");
    input.addEventListener("input", () => { design.eye[s.key] = Number(input.value); out.textContent = input.value; changed(); });
    shape.appendChild(wrap);
  }
}

// --------------------------------------------------------------- saving
function changed() {
  eyes.setConfig(design);
  try { localStorage.setItem(DRAFT_KEY, JSON.stringify(design)); } catch (e) {}
  setStatus("Unsaved changes", "dirty");
  updateButtons();
}

function updateButtons() {
  $("save").disabled = same(design, saved);
  const required = REQUIRED.includes(current);
  $("delete").disabled = required;
  $("delete").title = required ? "Bolt needs this expression" : "";
  if (!deleteArmed) $("delete").textContent = "Delete current";
}

function setStatus(text, kind = "") { $("status").textContent = text; $("status").className = kind; }

async function send(method, url, body) {
  const response = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body && JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Bolt couldn't save that.");
  return data;
}

function adopt(newDesign, message) {
  saved = newDesign; design = structuredClone(newDesign);
  if (!design.expressions[current]) { current = "idle"; eyes.setState("idle"); }
  try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  eyes.setConfig(design); renderAll(); setStatus(message, "good");
}

$("save").addEventListener("click", async () => {
  setStatus("Saving…");
  try {
    await send("PUT", "/expressions", design);
    adopt(structuredClone(design), "Saved on Bolt. The chat page and the Pi will use it.");
  } catch (err) { setStatus(err.message, "bad"); }
});

$("undo").addEventListener("click", async () => {
  try { adopt((await send("POST", "/expressions/undo")).design, "Back to the design before your last save."); }
  catch (err) { setStatus(err.message, "bad"); }
});

$("original").addEventListener("click", async () => {
  try { adopt((await send("POST", "/expressions/reset")).design, "Back to the original design. (Undo last save brings yours back.)"); }
  catch (err) { setStatus(err.message, "bad"); }
});

$("copy").addEventListener("click", async () => {
  const text = JSON.stringify(design, null, 2);
  try { await navigator.clipboard.writeText(text); setStatus("Design copied.", "good"); $("copy-box").hidden = true; }
  catch (e) { const box = $("copy-box"); box.value = text; box.hidden = false; box.select(); setStatus("Select the text and copy it."); }
});

// "Pretend to talk" wiggles the speaking level like a voice would.
$("talk").addEventListener("click", (e) => {
  talking = !talking;
  e.currentTarget.setAttribute("aria-pressed", talking);
  if (talking && design.expressions.speaking) { current = "speaking"; eyes.setState("speaking"); renderAll(); }
});
(function wiggle(t) {
  if (eyes) eyes.setLevel(talking ? 0.5 + 0.5 * Math.sin(t / 90) * Math.sin(t / 37) : 0);
  requestAnimationFrame(wiggle);
})(0);

load().catch(() => setStatus("Couldn't load the design. Is Bolt's brain running?", "bad"));

// The canvases can't be sized while their tab is hidden, so size them when it's shown.
document.addEventListener("studio:tab", (e) => {
  if (e.detail === "eyes") for (const c of document.querySelectorAll(".face canvas")) BoltEyes.fit(c);
});
})();
