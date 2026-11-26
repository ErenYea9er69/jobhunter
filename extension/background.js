/* JobHunter service worker.
 * Pages call the local app through this worker, so page security rules (CORS, mixed content)
 * never block a request and a page cannot read the app's answers directly. */
const CANDIDATE_BASES = [
  "http://127.0.0.1:8080",
  "http://127.0.0.1:8081",
  "http://127.0.0.1:8082",
  "http://127.0.0.1:8765",
];
let ACTIVE_BASE = CANDIDATE_BASES[0];
const ALLOWED = /^\/api\/(extension\/(status|payload|solve|confirm-applied|founder-outreach)|preferences)$/;

async function resolveBase(forceProbe = false) {
  if (!forceProbe) {
    try {
      const r = await fetch(ACTIVE_BASE + "/api/extension/status");
      if (r.ok) return ACTIVE_BASE;
    } catch (e) { /* probe candidates */ }
  }
  for (const base of CANDIDATE_BASES) {
    try {
      const r = await fetch(base + "/api/extension/status");
      if (r.ok) {
        ACTIVE_BASE = base;
        return base;
      }
    } catch (e) { /* try next port */ }
  }
  return null;
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (!msg) return;
  if (msg.type === "jh-dashboard-url") {
    resolveBase().then((base) => reply({ url: base || ACTIVE_BASE }));
    return true;
  }
  if (msg.type !== "jh-api") return;
  if (!ALLOWED.test(msg.path || "")) { reply({ ok: false, error: "This request is not allowed." }); return; }
  const init = { method: msg.method === "POST" ? "POST" : "GET", headers: {} };
  if (init.method === "POST") { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(msg.body || {}); }
  (async () => {
    const base = await resolveBase();
    if (!base) {
      reply({ ok: false, offline: true, error: "JobHunter is not running on this computer." });
      return;
    }
    try {
      const r = await fetch(base + msg.path, init);
      let j = null;
      try { j = await r.json(); } catch (e) { /* not JSON */ }
      const ok = r.ok && (!j || j.success !== false);
      reply({ ok, data: j && j.data !== undefined ? j.data : j, error: ok ? "" : (j && (j.error || j.message)) || "The app returned an error." });
    } catch (e) {
      reply({ ok: false, offline: true, error: "JobHunter is not running on this computer." });
    }
  })();
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
