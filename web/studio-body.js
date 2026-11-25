/*
 * The Studio's BODY tab: volume, sleeping and listening, for the body on the Pi.
 *
 * LESSON: the form is built from what the brain describes (GET /body-settings
 * sends the labels, limits and defaults), so adding a setting only means
 * adding it in robot_friend/body_settings.py. The brain checks every value
 * again when you save: never trust a web page to enforce the limits.
 */
(() => {
  const $ = (id) => document.getElementById(id);
  let form, saved, values = {};

  const setStatus = (text, kind = "") => { $("b-status").textContent = text; $("b-status").className = kind; };
  // The two reply lists: her usual ones, and the sleepy ones (after a doze)
  const BOXES = [["b-replies", 0], ["b-sleepy", 1]];
  const lines = (id) => $(id).value.split("\n").map((r) => r.trim()).filter(Boolean);
  const lists = () => form.lists || [form.replies];
  const current = () => {
    const now = { ...values };
    for (const [id, i] of BOXES) if (lists()[i]) now[lists()[i].key] = lines(id);
    return now;
  };
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  /** One setting: its short name in bold, its value, the control, and a line explaining it. */
  function field(s, settings) {
    values[s.key] = settings[s.key];
    const wrap = document.createElement("div"); wrap.className = "setting";
    const control = s.kind === "number"
      ? `<input type="range" id="b-${s.key}" min="${s.min}" max="${s.max}" step="${s.step}" aria-describedby="b-${s.key}-hint">`
      : `<select id="b-${s.key}" aria-describedby="b-${s.key}-hint"></select>`;
    wrap.innerHTML = `<label for="b-${s.key}"><strong></strong><output></output></label>${control}<small id="b-${s.key}-hint"></small>`;
    wrap.querySelector("strong").textContent = s.name || s.label;
    wrap.querySelector("small").textContent = s.hint || "";
    const out = wrap.querySelector("output");
    if (s.kind === "number") {
      const input = wrap.querySelector("input");
      input.value = settings[s.key]; out.textContent = settings[s.key];
      input.addEventListener("input", () => { values[s.key] = Number(input.value); out.textContent = input.value; changed(); });
    } else {
      const pick = wrap.querySelector("select");
      for (const o of s.options) pick.add(new Option(o.label, o.value));
      pick.value = values[s.key];
      pick.addEventListener("change", () => {
        values[s.key] = pick.value;
        if (s.key === "christmas_hat") window.dispatchEvent(new CustomEvent("bolt-hat", { detail: pick.value }));
        changed();
      });
    }
    return wrap;
  }

  function show(settings) {
    values = {};
    const box = $("b-groups");
    box.innerHTML = "";
    for (const g of form.groups) {                      // one header per group (see GROUPS in body_settings.py)
      const section = document.createElement("section"); section.className = "setting-group";
      const h = document.createElement("h3"); h.textContent = g.title;
      const grid = document.createElement("div"); grid.className = "settings";
      for (const s of g.fields) grid.appendChild(field(s, settings));
      section.append(h, grid);
      box.appendChild(section);
    }
    window.dispatchEvent(new CustomEvent("bolt-hat", { detail: settings.christmas_hat }));
    for (const [id, i] of BOXES) if (lists()[i]) $(id).value = (settings[lists()[i].key] || []).join("\n");
    changed(false);
  }

  function changed(mark = true) {
    for (const [id, i] of BOXES) if (lists()[i]) $(id + "-count").textContent = `${lines(id).length} / ${lists()[i].max}`;
    const dirty = !same(current(), saved);
    $("b-save").disabled = !dirty;
    if (mark) setStatus(dirty ? "Unsaved changes" : "No changes", dirty ? "dirty" : "");
  }

  async function send(method, url, body) {
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body && JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Bolt couldn't save that.");
    return data;
  }

  async function load() {
    const data = await (await fetch("/body-settings")).json();
    form = data.form; saved = data.current;
    for (const [id, i] of BOXES) {
      if (lists()[i]) $(id + "-label").textContent = lists()[i].label;
      else $(id).closest(".field").hidden = true;          // an older brain without that list
    }
    show(saved);
    setStatus(data.custom ? "Showing your saved settings" : "Showing the original settings");
  }

  for (const [id] of BOXES) $(id).addEventListener("input", () => changed());
  $("b-save").addEventListener("click", async () => {
    try {
      saved = (await send("PUT", "/body-settings", current())).current;
      show(saved);
      setStatus("Saved. Bolt picks it up within 30 seconds.", "good");
    } catch (e) { setStatus(e.message, "bad"); }
  });
  $("b-original").addEventListener("click", async () => {
    if (!confirm("Go back to the settings Bolt came with?")) return;
    try {
      saved = (await send("POST", "/body-settings/reset")).current;
      show(saved);
      setStatus("Back to the original settings. Bolt picks them up within 30 seconds.", "good");
    } catch (e) { setStatus(e.message, "bad"); }
  });

  load().catch(() => setStatus("Couldn't load the settings. Is Bolt's brain running?", "bad"));
})();
