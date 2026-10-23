// JobHunter Extension Popup Script
document.addEventListener("DOMContentLoaded", async () => {
  const BACKEND_BASE = "http://localhost:8080";
  const candEl = document.getElementById("ext-cand-name");
  const resEl = document.getElementById("ext-resume-name");
  const openBtn = document.getElementById("btn-open-app");

  if (openBtn) {
    openBtn.addEventListener("click", () => {
      chrome.tabs.create({ url: `${BACKEND_BASE}/` });
    });
  }

  try {
    const res = await fetch(`${BACKEND_BASE}/api/extension/status`);
    if (res.ok) {
      const data = await res.json();
      if (candEl) candEl.textContent = data.candidate_name || "Rayen Ben Aissa";
      if (resEl) resEl.textContent = data.active_resume || "Primary Resume";
    } else {
      if (candEl) candEl.textContent = "Offline";
    }
  } catch (err) {
    if (candEl) candEl.textContent = "Not Running (:8080)";
    if (resEl) resEl.textContent = "Start JobHunter";
  }
});
