// JobHunter Chrome Extension Service Worker (Manifest V3)
const BACKEND_BASE = "http://127.0.0.1:8765";

chrome.runtime.onInstalled.addListener(() => {
  console.log("[JobHunter] Extension installed. Ready to assist on ATS job boards.");
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "get_status") {
    fetch(`${BACKEND_BASE}/api/extension/status`)
      .then(res => res.json())
      .then(res => sendResponse({ success: true, data: res.data || res }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});
