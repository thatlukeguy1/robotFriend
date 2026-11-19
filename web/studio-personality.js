/*
 * The Studio's PERSONALITY tab.
 *
 * LESSON: Bolt's personality is three bits of text (name, who it is, how it
 * talks) that get glued to the PROTECTED RULES to make its system prompt.
 * The test chat sends your unsaved text to POST /personality/try, so you can
 * hear the new Bolt before you commit to it. "Save to Bolt" sends it to
 * PUT /personality, which checks it, saves it, and starts a fresh conversation.
 */
(() => {
  const $ = (id) => document.getElementById(id);
  const DRAFT_KEY = "bolt-personality-draft";
  const FIELDS = ["name", "who", "talk"];
  let saved, original, limits, history = [];

  const same = (a, b) => FIELDS.every((k) => (a[k] || "").trim() === (b[k] || "").trim());
  const current = () => Object.fromEntries(FIELDS.map((k) => [k, $("p-" + k).value]));

  function setStatus(text, kind = "") { $("p-status").textContent = text; $("p-status").className = kind; }

  function fill(character) {
    for (const k of FIELDS) if (character[k] !== undefined) $("p-" + k).value = character[k];
    changed(false);
  }

  function changed(save = true) {
    for (const k of FIELDS) $("p-" + k + "-count").textContent = `${$("p-" + k).value.length} / ${limits[k]}`;
    const dirty = !same(current(), saved);
    $("p-save").disabled = !dirty;
    if (save) {
      try { dirty ? localStorage.setItem(DRAFT_KEY, JSON.stringify(current())) : localStorage.removeItem(DRAFT_KEY); } catch (e) {}
      setStatus(dirty ? "Unsaved changes" : "No changes", dirty ? "dirty" : "");
    }
  }

  async function load() {
    const data = await (await fetch("/personality")).json();
    saved = data.current; original = data.original; limits = data.limits;
    $("p-rules").textContent = data.rules;
    for (const k of FIELDS) $("p-" + k).maxLength = limits[k];

    // Ready-made personalities: they fill in "who" and "how", and keep your name.
    const box = $("p-presets");
    const add = (label, character) => {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = label;
      b.addEventListener("click", () => { fill({ ...character, name: character.name || $("p-name").value }); changed(); setStatus(`Loaded "${label}". Try it in the test chat, then save if you like it.`, "dirty"); });
      box.appendChild(b);
    };
    add("Original", original);
    for (const [label, character] of Object.entries(data.presets)) add(label, character);

    let draft = null;
    try { draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); } catch (e) {}
    fill(draft && !same(draft, saved) ? draft : saved);
    changed(false);
    setStatus(draft && !same(draft, saved) ? "Unsaved changes from last time (not on Bolt yet)" :
              data.custom ? "Showing your saved personality" : "Showing the original personality",
              draft && !same(draft, saved) ? "dirty" : "");
  }

  for (const k of FIELDS) $("p-" + k).addEventListener("input", () => changed());

  // ------------------------------------------------------------ test chat
  function bubble(text, who) {
    const div = document.createElement("div");
    div.className = "msg " + who;
    div.textContent = text;
    $("p-chat-log").appendChild(div);
    $("p-chat-log").scrollTop = $("p-chat-log").scrollHeight;
  }

  $("p-chat").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("p-chat-text").value.trim();
    if (!text) return;
    $("p-chat-text").value = "";
    bubble(text, "me");
    history.push({ role: "user", content: text });
    history = history.slice(-11);  // keep the test chat short
    if (history[0].role !== "user") history.shift();
    $("p-chat-send").disabled = true;
    try {
      const r = await fetch("/personality/try", { method: "POST", headers: { "Content-Type": "application/json" },
                                                  body: JSON.stringify({ character: current(), history }) });
      const data = await r.json();
      if (r.ok) { bubble(data.reply, "bolt"); history.push({ role: "assistant", content: data.reply }); }
      else { bubble("⚠ " + (data.error || "That didn't work."), "error"); history.pop(); }
    } catch (err) {
      bubble("⚠ Can't reach Bolt's brain.", "error"); history.pop();
    }
    $("p-chat-send").disabled = false;
    $("p-chat-text").focus();
  });

  $("p-chat-clear").addEventListener("click", () => { history = []; $("p-chat-log").innerHTML = ""; });

  // --------------------------------------------------------------- saving
  async function send(method, url, body) {
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body && JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || "Bolt couldn't save that.");
    return data;
  }

  function adopt(character, message) {
    saved = character;
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
    fill(character); changed(false); setStatus(message, "good");
  }

  $("p-save").addEventListener("click", async () => {
    setStatus("Saving…");
    try { adopt((await send("PUT", "/personality", current())).current, "Saved on Bolt. The next chat uses the new personality."); }
    catch (err) { setStatus(err.message, "bad"); }
  });
  $("p-undo").addEventListener("click", async () => {
    try { adopt((await send("POST", "/personality/undo")).current, "Back to the personality before your last save."); }
    catch (err) { setStatus(err.message, "bad"); }
  });
  $("p-original").addEventListener("click", async () => {
    try { adopt((await send("POST", "/personality/reset")).current, "Back to the original personality. (Undo save brings yours back.)"); }
    catch (err) { setStatus(err.message, "bad"); }
  });

  load().catch(() => setStatus("Couldn't load the personality. Is Bolt's brain running?", "bad"));
})();
