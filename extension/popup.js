// JobHunter Extension Popup Script
document.addEventListener("DOMContentLoaded", async () => {
  const BACKEND_BASE = "http://127.0.0.1:8765";
  const candEl = document.getElementById("ext-cand-name");
  const resEl = document.getElementById("ext-resume-name");
  const statusEl = document.getElementById("server-status");
  const openBtn = document.getElementById("btn-open-app");

  if (openBtn) {
    openBtn.addEventListener("click", () => {
      chrome.tabs.create({ url: `${BACKEND_BASE}/` });
    });
  }

  try {
    const res = await fetch(`${BACKEND_BASE}/api/extension/status`);
    if (res.ok) {
      const envelope = await res.json();
      const data = envelope.data || envelope;
      if (candEl) candEl.textContent = data.candidate_name || "Active Candidate";
      if (resEl) resEl.textContent = data.active_profile || "Primary Resume";
      if (statusEl) statusEl.innerHTML = '<span class="dot"></span>Connected (:8765)';
    } else {
      if (candEl) candEl.textContent = "Offline";
      if (statusEl) statusEl.innerHTML = '<span class="dot" style="background:#ef4444;"></span>Offline';
    }
  } catch (err) {
    if (candEl) candEl.textContent = "Not Running (:8765)";
    if (resEl) resEl.textContent = "Start desktop.py";
    if (statusEl) statusEl.innerHTML = '<span class="dot" style="background:#ef4444;"></span>Disconnected';
  }
});
