// JobHunter Chrome Extension Service Worker
chrome.runtime.onInstalled.addListener(() => {
  console.log("[JobHunter] Extension installed. Ready to assist on ATS job boards.");
});

// Relay messages between content scripts and background if needed
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "get_status") {
    fetch("http://localhost:8080/api/extension/status")
      .then(res => res.json())
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true; // Keep message channel open for async response
  }
});
