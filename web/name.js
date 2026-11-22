/**
 * LESSON: One name, everywhere
 * ============================
 * The robot's name lives in ONE place: the personality saved in the Studio
 * (Personality tab -> Name). Instead of writing the name into every page,
 * each page asks the brain for it (/health, which anyone may read) and swaps
 * it in: in text, button tips, placeholders, the tab's title, and in messages
 * that appear later (a MutationObserver watches for new text).
 *
 * The pages are written with "Bolt" as the placeholder name. \b in the
 * pattern means "whole word only", so code names like BoltFace are left alone.
 * Anything inside an element marked data-keep-name (like your memories) is
 * shown exactly as written, because those are your words, not labels.
 */
(() => {
  const ATTRS = ["title", "placeholder", "aria-label"];
  const has = (text) => /\bBolt\b/.test(text);
  let swap = (text) => text;

  function fix(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const parent = node.parentElement;
      if (parent && parent.closest("[data-keep-name], script, style")) return;
      if (has(node.nodeValue)) node.nodeValue = swap(node.nodeValue);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE || node.closest("[data-keep-name], script, style")) return;
    for (const a of ATTRS) {
      const value = node.getAttribute(a);
      if (value && has(value)) node.setAttribute(a, swap(value));
    }
    for (const child of node.childNodes) fix(child);
  }

  fetch("/health").then((r) => r.json()).then((health) => {
    const name = health.robot;
    window.ROBOT_NAME = name;
    if (!name || name === "Bolt") return;
    swap = (text) => text.replace(/\bBolt\b/g, name);
    document.title = swap(document.title);
    fix(document.body);
    new MutationObserver((changes) => {
      for (const c of changes) {
        if (c.type === "characterData") fix(c.target);
        else c.addedNodes.forEach(fix);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  }).catch(() => {});
})();
