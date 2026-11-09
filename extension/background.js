/* JobHunter service worker.
 * Pages call the local app through this worker, so page security rules (CORS, mixed content)
 * never block a request and a page cannot read the app's answers directly. */
const BASE = "http://127.0.0.1:8765";
const ALLOWED = /^\/api\/(extension\/(status|payload|solve|confirm-applied|founder-outreach)|preferences)$/;

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (!msg || msg.type !== "jh-api") return;
  if (!ALLOWED.test(msg.path || "")) { reply({ ok: false, error: "This request is not allowed." }); return; }
  const init = { method: msg.method === "POST" ? "POST" : "GET", headers: {} };
  if (init.method === "POST") { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(msg.body || {}); }
  fetch(BASE + msg.path, init)
    .then(async (r) => {
      let j = null;
      try { j = await r.json(); } catch (e) { /* not JSON */ }
      const ok = r.ok && (!j || j.success !== false);
      reply({ ok, data: j && j.data !== undefined ? j.data : j, error: ok ? "" : (j && (j.error || j.message)) || "The app returned an error." });
    })
    .catch(() => reply({ ok: false, offline: true, error: "JobHunter is not running on this computer." }));
  return true;
});

/* Put the panel on the current page, including sites outside the built-in list. */
async function openPanel(tabId) {
  try {
    const r = await chrome.tabs.sendMessage(tabId, { type: "jh-toggle", open: true });
    if (r && r.ok) return true;
  } catch (e) { /* not injected yet */ }
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ["panel-styles.js", "content.js"] });
    await chrome.tabs.sendMessage(tabId, { type: "jh-toggle", open: true });
    return true;
  } catch (e) { return false; }
}

chrome.commands.onCommand.addListener(async (cmd) => {
  if (cmd !== "toggle-panel") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.id != null) {
    try { const r = await chrome.tabs.sendMessage(tab.id, { type: "jh-toggle" }); if (r && r.ok) return; } catch (e) { /* inject below */ }
    openPanel(tab.id);
  }
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg && msg.type === "jh-open-here") { openPanel(msg.tabId).then((ok) => reply({ ok })); return true; }
});
