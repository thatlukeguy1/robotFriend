/*
 * LESSON: Staying logged in
 * If the server ever answers "401: please log in" (for example after the
 * password was changed), send the person to the login page, then bring them
 * back here afterwards.
 */
(() => {
  const realFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await realFetch(...args);
    if (response.status === 401 && !String(args[0]).startsWith("/login")) {
      location.href = "/login?next=" + encodeURIComponent(location.pathname);
    }
    return response;
  };

  // Any button with data-logout logs this browser out.
  document.addEventListener("click", async (e) => {
    if (!e.target.closest("[data-logout]")) return;
    await realFetch("/logout", { method: "POST" });
    location.href = "/login";
  });
})();
