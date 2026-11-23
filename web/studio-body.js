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
  const replies = () => $("b-replies").value.split("\n").map((r) => r.trim()).filter(Boolean);
  const current = () => ({ ...values, [form.replies.key]: replies() });
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  function show(settings) {
    values = {};
    const box = $("b-sliders");
    box.innerHTML = "";
    for (const s of form.numbers) {
      values[s.key] = settings[s.key];
      const wrap = document.createElement("div"); wrap.className = "slider";
      wrap.innerHTML = `<label for="b-${s.key}"><span></span><output></output></label>
        <input type="range" id="b-${s.key}" min="${s.min}" max="${s.max}" step="${s.step}">`;
      wrap.querySelector("span").textContent = s.label;
      const input = wrap.querySelector("input"), out = wrap.querySelector("output");
      input.value = settings[s.key]; out.textContent = settings[s.key];
      input.addEventListener("input", () => { values[s.key] = Number(input.value); out.textContent = input.value; changed(); });
      box.appendChild(wrap);
    }
    const switches = $("b-switches");
    switches.innerHTML = "";
    for (const s of form.switches || []) {
      values[s.key] = !!settings[s.key];
      const row = document.createElement("label"); row.className = "switch";
      row.innerHTML = `<input type="checkbox" id="b-${s.key}"><span></span>`;
      row.querySelector("span").textContent = s.label;
      const box = row.querySelector("input");
      box.checked = values[s.key];
      box.addEventListener("change", () => {
        values[s.key] = box.checked;
        if (s.key === "christmas_hat") window.dispatchEvent(new CustomEvent("bolt-hat", { detail: box.checked }));
        changed();
      });
      switches.appendChild(row);
    }
    window.dispatchEvent(new CustomEvent("bolt-hat", { detail: !!settings.christmas_hat }));
    $("b-replies").value = settings[form.replies.key].join("\n");
    changed(false);
  }

  function changed(mark = true) {
    const list = replies();
    $("b-replies-count").textContent = `${list.length} / ${form.replies.max}`;
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
    $("b-replies-label").textContent = form.replies.label;
    show(saved);
    setStatus(data.custom ? "Showing your saved settings" : "Showing the original settings");
  }

  $("b-replies").addEventListener("input", () => changed());
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
