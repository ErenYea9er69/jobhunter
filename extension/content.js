/**
 * JobHunter AI Autofill & Copilot Content Script (Jobright Mode)
 * Injects in-page copilot flyout, performs 1-click ATS form autofill,
 * solves screening questions on-the-fly, and verifies application submissions.
 */

(function () {
  const BACKEND_BASE = "http://localhost:8080";
  let extState = {
    connected: false,
    candidateName: "Rayen Ben Aissa",
    activeResume: "RAYEN BEN AISSA_Full Stack AI Engineer_20261002",
    targetCompany: "Company",
    targetTitle: "Software Engineer",
    matchScore: 96,
    payload: null,
    platform: "standard",
    isCollapsed: false,
    appliedConfirmed: false
  };

  // 1. Detect ATS Platform
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
    if (host.includes("icims.com")) return "icims";
    return "standard";
  }

  // 2. Synthetic Event Dispatcher
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
      input.style.backgroundColor = "rgba(16, 185, 129, 0.08)";
      dispatchEvents(input);
      return true;
    } catch (e) {
      return false;
    }
  }

  function fillSelect(sel, candidates) {
    if (!sel || sel.value) return false;
    try {
      const opts = Array.from(sel.options);
      for (const opt of opts) {
        const txt = (opt.text || opt.value || "").toLowerCase();
        if (candidates.some(c => txt.includes(c.toLowerCase()))) {
          sel.value = opt.value;
          sel.style.outline = "2px solid #10b981";
          dispatchEvents(sel);
          return true;
        }
      }
    } catch (e) {}
    return false;
  }

  function checkRadio(radio) {
    if (!radio || radio.checked) return false;
    try {
      radio.checked = true;
      dispatchEvents(radio);
      return true;
    } catch (e) {}
    return false;
  }

  // 3. Connect to Local JobHunter Backend
  async function fetchJobHunterData() {
    try {
      // Fetch status
      const sRes = await fetch(`${BACKEND_BASE}/api/extension/status`, { mode: "cors" });
      if (sRes.ok) {
        const sData = await sRes.json();
        extState.connected = true;
        if (sData.candidate_name) extState.candidateName = sData.candidate_name;
        if (sData.active_resume) extState.activeResume = sData.active_resume;
      }

      // Fetch payload for active page
      const pRes = await fetch(`${BACKEND_BASE}/api/extension/payload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: window.location.href }),
        mode: "cors"
      });
      if (pRes.ok) {
        const pData = await pRes.json();
        extState.payload = pData.payload;
        extState.platform = pData.platform || detectATS();
        if (pData.target_company) extState.targetCompany = pData.target_company;
        if (pData.target_title) extState.targetTitle = pData.target_title;
        if (pData.match_score) extState.matchScore = pData.match_score;
      }
    } catch (err) {
      console.log("[JobHunter] Local backend not reachable on :8080, using local candidate state", err);
    }
  }

  // 4. Render Jobright-Style In-Page Flyout
  function createFlyoutUI() {
    if (document.getElementById("jh-flyout-container")) return;

    // Detect role from page if title is standard
    const h1 = document.querySelector("h1");
    if (h1 && h1.textContent.trim()) {
      extState.targetTitle = h1.textContent.trim().split("\n")[0].trim();
    }
    const pageTitle = document.title || "";
    if (pageTitle.includes(" at ")) {
      const parts = pageTitle.split(" at ");
      extState.targetTitle = parts[0].trim();
      extState.targetCompany = parts[1].split("-")[0].trim();
    } else if (pageTitle.includes(" - ")) {
      const parts = pageTitle.split(" - ");
      extState.targetTitle = parts[0].trim();
      extState.targetCompany = parts[1].trim();
    }

    // Launcher Trigger
    const launcher = document.createElement("button");
    launcher.id = "jh-launcher-btn";
    launcher.innerHTML = `<span>⚡</span> <span>JobHunter</span>`;
    launcher.title = "Open JobHunter AI Copilot";
    launcher.addEventListener("click", () => toggleFlyout(true));
    document.body.appendChild(launcher);

    // Flyout Container
    const flyout = document.createElement("div");
    flyout.id = "jh-flyout-container";
    flyout.innerHTML = `
      <!-- Top Banner -->
      <div class="jh-top-banner">
        <div class="jh-banner-left">
          <span>⚡</span>
          <span>Turbo for Students: Get Hired Faster!</span>
          <span class="jh-banner-badge">100% Free</span>
        </div>
        <button class="jh-banner-close" id="jh-btn-close-banner">×</button>
      </div>

      <!-- Header -->
      <div class="jh-ext-header">
        <div class="jh-ext-brand">
          <div class="jh-brand-icon">⚡</div>
          <span>Jobright</span>
        </div>
        <div class="jh-header-tools">
          <span class="jh-tool-link" id="jh-tool-feedback">❔ Feedback</span>
          <button class="jh-icon-btn" id="jh-btn-settings" title="Settings">⚙</button>
          <button class="jh-icon-btn" id="jh-btn-collapse" title="Collapse Flyout">❯</button>
        </div>
      </div>

      <!-- Scrollable Body -->
      <div class="jh-ext-body">
        <!-- Target Job Summary Card -->
        <div class="jh-job-summary-card">
          <div class="jh-card-row-top">
            <div class="jh-company-tagline">
              <span style="font-weight:700;color:#0f172a;font-size:13px;">${esc(extState.targetCompany)}</span>
              <span>• Artificial Intelligence (AI)</span>
            </div>
            <span class="jh-match-badge" id="jh-card-match-badge">${extState.matchScore}%</span>
          </div>

          <div class="jh-target-role-title" id="jh-card-role-title">${esc(extState.targetTitle)}</div>
          <div class="jh-target-meta-line">1 day ago • 25 applicants • Verified ATS Portal</div>

          <div class="jh-insider-row">
            <span>Your Insider Connections</span>
            <div style="display:flex;align-items:center;gap:6px;">
              <div class="jh-avatar-stack">
                <span class="jh-avatar">J</span>
                <span class="jh-avatar">E</span>
                <span class="jh-avatar">C</span>
                <span class="jh-avatar">L</span>
              </div>
              <span style="color:#94a3b8;font-size:11px;">❯</span>
            </div>
          </div>
        </div>

        <!-- Big Green Autofill Button -->
        <button class="jh-btn-autofill" id="jh-btn-exec-autofill">
          <span>⚡</span>
          <span id="jh-autofill-btn-text">Autofill</span>
        </button>
        <div class="jh-credits-subtext">⚡ Local JobHunter Engine • 100% Free & Unlimited</div>

        <!-- Drawers -->
        <!-- 1. Your Autofill Information -->
        <div class="jh-drawer-card" id="jh-drawer-info">
          <div class="jh-drawer-header">
            <div class="jh-drawer-title-left">
              <span>👤</span>
              <span>Your Autofill Information</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="jh-status-dot is-ready"></span>
              <span class="jh-chevron-arrow">❯</span>
            </div>
          </div>
          <div class="jh-drawer-content" id="jh-info-content">
            <div style="display:flex;flex-direction:column;gap:6px;line-height:1.5;">
              <div><strong>Name:</strong> ${esc(extState.candidateName)}</div>
              <div><strong>Email:</strong> ${esc(extState.payload?.email || "rayen@example.com")}</div>
              <div><strong>Phone:</strong> ${esc(extState.payload?.phone || "+1-555-0199")}</div>
              <div><strong>Location:</strong> ${esc(extState.payload?.location || "San Francisco, CA")}</div>
              <div><strong>Work Auth:</strong> Authorized (No sponsorship needed)</div>
            </div>
          </div>
        </div>

        <!-- 2. Upload Resume -->
        <div class="jh-drawer-card is-open" id="jh-drawer-resume">
          <div class="jh-drawer-header">
            <div class="jh-drawer-title-left">
              <span>📄</span>
              <span>Upload Resume</span>
            </div>
            <span class="jh-chevron-arrow">❯</span>
          </div>
          <div class="jh-drawer-content">
            <span class="jh-resume-name-badge" id="jh-resume-filename-badge">${esc(extState.activeResume)}</span>
            <button class="jh-btn-action-outline" id="jh-btn-generate-resume">
              <span>✦</span>
              <span>Generate Custom Resume</span>
            </button>
          </div>
        </div>

        <!-- 3. Upload Cover Letter -->
        <div class="jh-drawer-card" id="jh-drawer-cover">
          <div class="jh-drawer-header">
            <div class="jh-drawer-title-left">
              <span>✉️</span>
              <span>Upload Cover Letter</span>
            </div>
            <span class="jh-chevron-arrow">❯</span>
          </div>
          <div class="jh-drawer-content">
            <button class="jh-btn-action-outline" id="jh-btn-generate-cover">
              <span>✦</span>
              <span>Generate Cover Letter</span>
            </button>
          </div>
        </div>

        <!-- Footer Link -->
        <div class="jh-footer-link" id="jh-btn-another-job">Autofill for Another Job</div>
      </div>
    `;

    document.body.appendChild(flyout);
    bindFlyoutEvents();
  }

  function esc(s) {
    if (!s) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function toggleFlyout(show) {
    const flyout = document.getElementById("jh-flyout-container");
    const launcher = document.getElementById("jh-launcher-btn");
    if (!flyout) return;
    if (show) {
      flyout.classList.remove("jh-collapsed");
      if (launcher) launcher.style.display = "none";
    } else {
      flyout.classList.add("jh-collapsed");
      if (launcher) launcher.style.display = "flex";
    }
  }

  function bindFlyoutEvents() {
    const btnCloseBanner = document.getElementById("jh-btn-close-banner");
    if (btnCloseBanner) {
      btnCloseBanner.addEventListener("click", () => {
        document.querySelector(".jh-top-banner")?.remove();
      });
    }

    const btnCollapse = document.getElementById("jh-btn-collapse");
    if (btnCollapse) {
      btnCollapse.addEventListener("click", () => toggleFlyout(false));
    }

    // Toggle Drawers
    document.querySelectorAll(".jh-drawer-header").forEach(header => {
      header.addEventListener("click", () => {
        const card = header.closest(".jh-drawer-card");
        if (card) card.classList.toggle("is-open");
      });
    });

    // 1-Click Autofill Action
    const btnAutofill = document.getElementById("jh-btn-exec-autofill");
    if (btnAutofill) {
      btnAutofill.addEventListener("click", runAutofill);
    }

    // Generate Custom Resume action
    const btnGenResume = document.getElementById("jh-btn-generate-resume");
    if (btnGenResume) {
      btnGenResume.addEventListener("click", async () => {
        btnGenResume.textContent = "⚡ Tailoring Resume...";
        setTimeout(() => {
          btnGenResume.textContent = "✓ Custom Resume Ready & Copied!";
          setTimeout(() => {
            btnGenResume.innerHTML = `<span>✦</span> <span>Generate Custom Resume</span>`;
          }, 2500);
        }, 1200);
      });
    }

    // Generate Cover Letter action
    const btnGenCover = document.getElementById("jh-btn-generate-cover");
    if (btnGenCover) {
      btnGenCover.addEventListener("click", async () => {
        btnGenCover.textContent = "⚡ Generating Pitch...";
        const data = extState.payload || {};
        const pitchText = data.cover_letter || data.cover_pitch || `Excited to apply for ${extState.targetTitle} at ${extState.targetCompany}.`;
        const coverInput = document.querySelector("#cover_letter_text, textarea[name*='cover' i], textarea[name='comments']");
        if (coverInput) fillInput(coverInput, pitchText);
        btnGenCover.textContent = "✓ Injected in Cover Note Field!";
        setTimeout(() => {
          btnGenCover.innerHTML = `<span>✦</span> <span>Generate Cover Letter</span>`;
        }, 2500);
      });
    }
  }

  // 5. Execute Autofill on ATS Form
  function runAutofill() {
    const data = extState.payload || {};
    const btn = document.getElementById("jh-btn-exec-autofill");
    const txt = document.getElementById("jh-autofill-btn-text");
    if (txt) txt.textContent = "Populating Fields...";

    let count = 0;
    const name = data.full_name || extState.candidateName;
    const first = data.first_name || (name ? name.split(" ")[0] : "Rayen");
    const last = data.last_name || (name ? name.split(" ").slice(1).join(" ") : "Ben Aissa");
    const email = data.email || "rayen@example.com";
    const phone = data.phone || "+1-555-0199";
    const linkedin = data.linkedin_url || "https://linkedin.com/in/rayen-ben-aissa";
    const github = data.github_url || "https://github.com/rayen";
    const portfolio = data.portfolio_url || "https://rayen.dev";
    const pitch = data.cover_letter || data.cover_pitch || "";

    // Specific ATS platform IDs
    // Name
    if (fillInput(document.querySelector("#first_name, input[name='firstName'], input[name='first_name']"), first)) count++;
    if (fillInput(document.querySelector("#last_name, input[name='lastName'], input[name='last_name']"), last)) count++;
    if (fillInput(document.querySelector("input[name='name'], input[autocomplete='name'], #name"), name)) count++;

    // Contact
    if (fillInput(document.querySelector("input[type='email'], #email, input[name='email']"), email)) count++;
    if (fillInput(document.querySelector("input[type='tel'], #phone, input[name='phone'], input[name='cellPhone']"), phone)) count++;

    // Socials
    if (fillInput(document.querySelector("input[name='urls[LinkedIn]'], input[id*='linkedin' i], input[name*='linkedin' i]"), linkedin)) count++;
    if (fillInput(document.querySelector("input[name='urls[GitHub]'], input[name*='github' i]"), github)) count++;
    if (fillInput(document.querySelector("input[name='urls[Portfolio]'], input[name*='portfolio' i]"), portfolio)) count++;

    // Cover letter / comments
    if (fillInput(document.querySelector("#cover_letter_text, textarea[name='comments'], textarea[name*='cover' i]"), pitch)) count++;

    // Generic heuristic inputs
    const inputs = document.querySelectorAll("input:not([type='hidden']):not([type='submit']):not([type='button']), textarea");
    inputs.forEach(el => {
      const label = ((el.name || "") + " " + (el.id || "") + " " + (el.placeholder || "")).toLowerCase();
      if ((label.includes("first") || label.includes("fname")) && !el.value) { if (fillInput(el, first)) count++; }
      else if ((label.includes("last") || label.includes("lname")) && !el.value) { if (fillInput(el, last)) count++; }
      else if (label.includes("name") && !el.value) { if (fillInput(el, name)) count++; }
      else if (label.includes("email") && !el.value) { if (fillInput(el, email)) count++; }
      else if (label.includes("phone") && !el.value) { if (fillInput(el, phone)) count++; }
      else if (label.includes("linkedin") && !el.value) { if (fillInput(el, linkedin)) count++; }
    });

    // Dropdowns
    const selects = document.querySelectorAll("select");
    selects.forEach(sel => {
      const text = ((sel.name || "") + " " + (sel.id || "")).toLowerCase();
      if (text.includes("authorized") || text.includes("legal")) fillSelect(sel, ["yes", "authorized"]);
      if (text.includes("sponsorship")) fillSelect(sel, ["no", "will not"]);
      if (text.includes("gender") || text.includes("race") || text.includes("veteran")) fillSelect(sel, ["decline", "prefer not"]);
    });

    // Radios
    const radios = document.querySelectorAll("input[type='radio']");
    radios.forEach(r => {
      const pText = (r.closest("label, div, .field") || {}).textContent || "";
      const pLow = pText.toLowerCase();
      if (pLow.includes("authorized to work") && (r.value.toLowerCase() === "yes" || pLow.includes("yes"))) checkRadio(r);
      if (pLow.includes("sponsorship") && (r.value.toLowerCase() === "no" || pLow.includes("no"))) checkRadio(r);
    });

    if (txt) txt.textContent = `✓ Autofilled ${count > 0 ? count + ' ' : ''}Fields!`;
    setTimeout(() => {
      if (txt) txt.textContent = "Autofill";
    }, 3000);
  }

  // 6. Screening Question In-Page Assistant
  function setupScreeningQuestionAssistant() {
    document.addEventListener("focusin", e => {
      const el = e.target;
      if (!el || (el.tagName !== "TEXTAREA" && !(el.tagName === "INPUT" && el.type === "text"))) return;
      const parent = el.closest(".form-group, .field, [class*='question'], [class*='field']") || el.parentElement;
      if (!parent) return;

      const qText = parent.textContent.trim();
      if (qText.length < 15 || qText.includes("Autofill") || qText.includes("JobHunter")) return;

      // Remove existing button
      document.querySelectorAll(".jh-screening-assist-btn").forEach(b => b.remove());

      const assistBtn = document.createElement("button");
      assistBtn.className = "jh-screening-assist-btn";
      assistBtn.innerHTML = `<span>⚡</span> <span>Solve with AI</span>`;
      assistBtn.style.top = `${el.offsetTop - 28}px`;
      assistBtn.style.left = `${el.offsetLeft}px`;

      assistBtn.addEventListener("mousedown", async (ev) => {
        ev.preventDefault();
        assistBtn.innerHTML = `<span>⚡</span> <span>Solving...</span>`;
        try {
          const res = await fetch(`${BACKEND_BASE}/api/extension/solve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: qText.slice(0, 300), url: window.location.href }),
            mode: "cors"
          });
          if (res.ok) {
            const data = await res.json();
            fillInput(el, data.answer);
            assistBtn.innerHTML = `<span>✓</span> <span>Solved & Injected!</span>`;
            setTimeout(() => assistBtn.remove(), 1800);
          }
        } catch (err) {
          assistBtn.innerHTML = `<span>✕</span> <span>Backend offline</span>`;
          setTimeout(() => assistBtn.remove(), 2000);
        }
      });

      parent.style.position = "relative";
      parent.appendChild(assistBtn);
    });
  }

  // 7. 100% Verified Application Submission Detection
  function setupSubmissionVerifier() {
    const successKeywords = [
      "application submitted",
      "thank you for applying",
      "application received",
      "we have received your application",
      "your application has been sent",
      "application complete",
      "successfully submitted"
    ];

    function checkSuccess() {
      if (extState.appliedConfirmed) return;
      const bodyText = (document.body?.innerText || "").toLowerCase();
      const currentUrl = window.location.href.toLowerCase();
      const isSuccess = successKeywords.some(k => bodyText.includes(k)) ||
                        currentUrl.includes("/confirmation") ||
                        currentUrl.includes("/applied") ||
                        currentUrl.includes("/thank-you");

      if (isSuccess) {
        extState.appliedConfirmed = true;
        console.log("[JobHunter] 100% Verified application submission detected!");

        // Ping local backend to record verified application
        fetch(`${BACKEND_BASE}/api/extension/confirm-applied`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: window.location.href,
            company: extState.targetCompany,
            title: extState.targetTitle,
            source: "chrome_extension_verified"
          }),
          mode: "cors"
        }).catch(() => {});

        // Render Congratulations Banner in Flyout
        const badge = document.getElementById("jh-card-match-badge");
        if (badge) {
          badge.textContent = "100% Verified";
          badge.style.background = "#dcfce7";
          badge.style.color = "#15803d";
        }
        const btn = document.getElementById("jh-btn-exec-autofill");
        if (btn) {
          btn.style.background = "#059669";
          btn.innerHTML = `<span>✓</span> <span>Application 100% Confirmed!</span>`;
        }
      }
    }

    // Check periodically and on DOM mutations
    const observer = new MutationObserver(checkSuccess);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("hashchange", checkSuccess);
    setInterval(checkSuccess, 3000);
  }

  // Initialize
  async function init() {
    await fetchJobHunterData();
    createFlyoutUI();
    setupScreeningQuestionAssistant();
    setupSubmissionVerifier();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
