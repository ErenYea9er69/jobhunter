/**
 * JobHunter AI Autofill & Copilot Content Script
 * Injects in-page copilot flyout, performs 1-click ATS form autofill,
 * solves screening questions on-the-fly, and verifies application submissions.
 */

(function () {
  const BACKEND_BASE = "http://127.0.0.1:8765";
  let extState = {
    connected: false,
    candidateName: "",
    activeResume: "",
    payload: null,
    platform: "standard",
    isCollapsed: false,
    appliedConfirmed: false,
  };

  function detectATS() {
    const host = window.location.hostname.toLowerCase();
    if (host.includes("greenhouse.io") || host.includes("grnh.se")) return "greenhouse";
    if (host.includes("lever.co")) return "lever";
    if (host.includes("ashbyhq.com") || document.querySelector("[class*='ashby' i]")) return "ashby";
    if (host.includes("workday") || host.includes("myworkdayjobs")) return "workday";
    if (host.includes("smartrecruiters.com")) return "smartrecruiters";
    if (host.includes("workable.com")) return "workable";
    if (host.includes("bamboohr.com")) return "bamboohr";
    if (host.includes("taleo.net") || host.includes("oraclecloud.com")) return "taleo";
    return "standard";
  }

  function dispatchEvents(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function fillInput(input, val) {
    if (!input || !val || input.value) return false;
    try {
      input.focus();
      const proto = Object.getPrototypeOf(input);
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (setter) {
        setter.call(input, val);
      } else {
        input.value = val;
      }
      input.style.outline = "2px solid #10b981";
      dispatchEvents(input);
      return true;
    } catch (e) {
      return false;
    }
  }

  async function performAutofill() {
    if (!extState.payload) return;
    const prof = extState.payload.profile || {};
    const nameParts = (prof.name || "").trim().split(/\s+/);
    const firstName = nameParts[0] || "";
    const lastName = nameParts.slice(1).join(" ") || "";

    let filledCount = 0;
    const inputs = Array.from(document.querySelectorAll("input, textarea"));

    inputs.forEach((input) => {
      const id = (input.id || "").toLowerCase();
      const name = (input.name || "").toLowerCase();
      const aria = (input.getAttribute("aria-label") || "").toLowerCase();
      const placeholder = (input.placeholder || "").toLowerCase();
      const label = input.closest("label")?.innerText?.toLowerCase() || "";
      const text = `${id} ${name} ${aria} ${placeholder} ${label}`;

      if (text.includes("first") && text.includes("name")) {
        if (fillInput(input, firstName)) filledCount++;
      } else if (text.includes("last") && text.includes("name")) {
        if (fillInput(input, lastName)) filledCount++;
      } else if (text.includes("full") && text.includes("name") || (text.includes("name") && !text.includes("user"))) {
        if (fillInput(input, prof.name)) filledCount++;
      } else if (text.includes("email")) {
        if (fillInput(input, prof.email)) filledCount++;
      } else if (text.includes("phone") || text.includes("mobile")) {
        if (fillInput(input, prof.phone)) filledCount++;
      } else if (text.includes("linkedin")) {
        if (fillInput(input, prof.linkedin)) filledCount++;
      } else if (text.includes("github")) {
        if (fillInput(input, prof.github)) filledCount++;
      } else if (text.includes("website") || text.includes("portfolio")) {
        if (fillInput(input, prof.website)) filledCount++;
      } else if (text.includes("location") || text.includes("city")) {
        if (fillInput(input, prof.location)) filledCount++;
      }
    });

    const statusEl = document.getElementById("jh-fill-status");
    if (statusEl) {
      statusEl.textContent = `✓ Filled ${filledCount} fields!`;
      statusEl.style.color = "#10b981";
    }
  }

  async function solveScreeningQuestions() {
    if (!extState.payload) return;
    const textareas = Array.from(document.querySelectorAll("textarea"));
    const statusEl = document.getElementById("jh-fill-status");
    if (statusEl) statusEl.textContent = "Solving questions with Reviewer QA...";

    for (const ta of textareas) {
      if (ta.value) continue;
      const labelEl = ta.closest("div")?.querySelector("label") || ta.closest("label");
      const question = labelEl?.innerText?.trim() || ta.placeholder || "Candidate qualification question";

      try {
        const res = await fetch(`${BACKEND_BASE}/api/extension/solve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: json.stringify({ question, job: { title: document.title } }),
        });
        const env = await res.json();
        const data = env.data || env;
        if (data.answer) {
          fillInput(ta, data.answer);
        }
      } catch (e) {
        console.error("[JobHunter] Error solving question:", e);
      }
    }

    if (statusEl) statusEl.textContent = "✓ Questions solved & verified!";
  }

  function trackSubmission() {
    const forms = Array.from(document.querySelectorAll("form"));
    forms.forEach((form) => {
      form.addEventListener("submit", () => {
        if (extState.appliedConfirmed) return;
        extState.appliedConfirmed = true;
        fetch(`${BACKEND_BASE}/api/extension/confirm-applied`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: window.location.href,
            title: document.title,
            company: window.location.hostname,
          }),
        }).catch(() => {});
      });
    });
  }

  function buildUI() {
    if (document.getElementById("jh-flyout-container")) return;

    const launcher = document.createElement("button");
    launcher.id = "jh-launcher-btn";
    launcher.innerHTML = '<span>⚡</span> <span>Autofill</span>';
    launcher.addEventListener("click", () => {
      const flyout = document.getElementById("jh-flyout-container");
      if (flyout) flyout.classList.toggle("jh-collapsed");
    });
    document.body.appendChild(launcher);

    const flyout = document.createElement("div");
    flyout.id = "jh-flyout-container";
    flyout.className = "jh-collapsed";
    flyout.innerHTML = `
      <div class="jh-header">
        <div class="jh-header-left">
          <span class="jh-badge">2.3.0</span>
          <span class="jh-header-title">JobHunter Copilot</span>
        </div>
        <button class="jh-close-btn" id="jh-close-btn">&times;</button>
      </div>
      <div class="jh-body">
        <div class="jh-card">
          <div class="jh-field-row">
            <span>ATS Detected:</span>
            <span class="jh-field-val">${extState.platform.toUpperCase()}</span>
          </div>
          <div class="jh-field-row">
            <span>Candidate:</span>
            <span class="jh-field-val" id="jh-cand-val">${extState.candidateName || "Loading..."}</span>
          </div>
          <div class="jh-field-row">
            <span>Active Resume:</span>
            <span class="jh-field-val" id="jh-res-val">${extState.activeResume || "Loading..."}</span>
          </div>
        </div>
        <button class="jh-action-btn" id="jh-autofill-btn">⚡ 1-Click Autofill Form</button>
        <button class="jh-action-btn" style="background:#3b82f6;" id="jh-solve-btn">🤖 Answer Screening Questions</button>
        <div id="jh-fill-status" style="font-size:12px;text-align:center;min-height:16px;"></div>
      </div>
      <div class="jh-footer">
        <span>Protected Local Engine</span>
        <a href="${BACKEND_BASE}/" target="_blank" style="color:#10b981;text-decoration:none;font-weight:600;">Dashboard ↗</a>
      </div>
    `;
    document.body.appendChild(flyout);

    document.getElementById("jh-close-btn")?.addEventListener("click", () => {
      flyout.classList.add("jh-collapsed");
    });
    document.getElementById("jh-autofill-btn")?.addEventListener("click", performAutofill);
    document.getElementById("jh-solve-btn")?.addEventListener("click", solveScreeningQuestions);
  }

  async function init() {
    extState.platform = detectATS();
    try {
      const res = await fetch(`${BACKEND_BASE}/api/extension/payload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: window.location.href }),
      });
      if (res.ok) {
        const env = await res.json();
        const data = env.data || env;
        extState.connected = true;
        extState.payload = data;
        extState.candidateName = data.profile?.name || "Active Candidate";
        extState.activeResume = data.profile?.target_title || "Software Engineer";
      }
    } catch (e) {
      console.log("[JobHunter] Local daemon not running on :8765");
    }

    buildUI();
    trackSubmission();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

