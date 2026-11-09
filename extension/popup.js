const BASE = "http://127.0.0.1:8765";
const $ = (id) => document.getElementById(id);

function show(online, text) {
  $("dot").className = "dot" + (online ? "" : " bad");
  $("state-text").textContent = text;
}

async function load() {
  try {
    const r = await fetch(BASE + "/api/extension/status");
    const j = await r.json();
    const d = (j && j.data) || j || {};
    show(true, "Connected to JobHunter");
    if (d.candidate_name) {
      $("who").hidden = false;
      $("who-name").textContent = d.candidate_name;
      $("who-role").textContent = d.active_profile || "";
    } else {
      const n = $("note");
      n.hidden = false; n.className = "note warn";
      n.textContent = "No resume yet. Add one in JobHunter so the panel has answers to use.";
    }
  } catch (e) {
    show(false, "JobHunter is not running");
    const n = $("note");
    n.hidden = false; n.className = "note";
    n.textContent = "Start JobHunter on this computer. The panel stays closed until it runs.";
    $("btn-panel").disabled = true;
  }
}

$("btn-app").addEventListener("click", () => { chrome.tabs.create({ url: BASE + "/" }); window.close(); });
$("btn-panel").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || tab.id == null || !/^https?:/.test(tab.url || "")) {
    const n = $("note"); n.hidden = false; n.className = "note warn"; n.textContent = "Open a job application page first.";
    return;
  }
  chrome.runtime.sendMessage({ type: "jh-open-here", tabId: tab.id }, (res) => {
    if (res && res.ok) window.close();
    else { const n = $("note"); n.hidden = false; n.className = "note"; n.textContent = "This page does not allow the panel."; }
  });
});
load();
