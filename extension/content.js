/**
 * JobHunter AI Autofill & Copilot Content Script
 * 1-click ATS form autofill, AI screening question solver,
 * multi-step wizard auto-pilot, and verified application tracking.
 * Adheres strictly to the 2-color system (Dark Gray + Crisp Emerald).
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
    autoPilotTimer: null,
  };

  function detectATS() {
    const host = window.location.hostname.toLowerCase();
    if (host.includes("linkedin.com")) return "linkedin";
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
      input.style.outline = "2px solid #047857";
      dispatchEvents(input);
      return true;
    } catch (e) {
      return false;
    }
  }

  function selectOptionByText(select, regex) {
    if (!select || !select.options) return false;
    for (let i = 0; i < select.options.length; i++) {
      const opt = select.options[i];
      if (regex.test(opt.text || "") || regex.test(opt.value || "")) {
        select.selectedIndex = i;
        select.style.outline = "2px solid #047857";
        dispatchEvents(select);
        return true;
      }
    }
    return false;
  }

  async function performAutofill() {
    if (!extState.payload) return 0;
    const prof = extState.payload.profile || {};
    const nameParts = (prof.name || "").trim().split(/\s+/);
    const firstName = nameParts[0] || "";
    const lastName = nameParts.slice(1).join(" ") || "";

    let filledCount = 0;
    const inputs = Array.from(document.querySelectorAll("input, textarea, select"));

    inputs.forEach((input) => {
      const tag = input.tagName.toLowerCase();
      const id = (input.id || "").toLowerCase();
      const name = (input.name || "").toLowerCase();
      const aria = (input.getAttribute("aria-label") || "").toLowerCase();
      const placeholder = (input.placeholder || "").toLowerCase();
      const label = input.closest("label")?.innerText?.toLowerCase() ||
        input.closest(".form-group, .field, [class*='field'], [class*='question']")?.querySelector("label, .label, [class*='label']")?.innerText?.toLowerCase() || "";
      const text = `${id} ${name} ${aria} ${placeholder} ${label}`;

      if (tag === "select") {
        if (/authori[zs]ed|legally eligible|work authorization/i.test(text)) {
          if (selectOptionByText(input, /^yes|authorized/i)) filledCount++;
        } else if (/sponsorship|require.*visa|visa.*sponsorship/i.test(text)) {
          if (selectOptionByText(input, /^no|not require/i)) filledCount++;
        }
        return;
      }

      if (input.type === "radio") {
        const valText = `${input.value || ""} ${input.closest("label")?.innerText || ""}`.toLowerCase();
        if (/authori[zs]ed|legally eligible/i.test(text) && /yes/i.test(valText)) {
          input.checked = true;
          dispatchEvents(input);
          filledCount++;
        } else if (/sponsorship|require.*visa/i.test(text) && /no/i.test(valText)) {
          input.checked = true;
          dispatchEvents(input);
          filledCount++;
        }
        return;
      }

      if (text.includes("first") && text.includes("name")) {
        if (fillInput(input, firstName)) filledCount++;
      } else if (text.includes("last") && text.includes("name")) {
        if (fillInput(input, lastName)) filledCount++;
      } else if ((text.includes("full") && text.includes("name")) || (text.includes("name") && !text.includes("user") && !text.includes("company"))) {
        if (fillInput(input, prof.name)) filledCount++;
      } else if (text.includes("email")) {
        if (fillInput(input, prof.email)) filledCount++;
      } else if (text.includes("phone") || text.includes("mobile") || text.includes("tel")) {
        if (fillInput(input, prof.phone)) filledCount++;
      } else if (text.includes("linkedin")) {
        if (fillInput(input, prof.linkedin)) filledCount++;
      } else if (text.includes("github")) {
        if (fillInput(input, prof.github)) filledCount++;
      } else if (text.includes("website") || text.includes("portfolio")) {
        if (fillInput(input, prof.website)) filledCount++;
      } else if (text.includes("location") || text.includes("city")) {
        if (fillInput(input, prof.location)) filledCount++;
      } else if (text.includes("experience") && (text.includes("years") || text.includes("total"))) {
        if (fillInput(input, String(prof.experience_years || 3))) filledCount++;
      }
    });

    const statusEl = document.getElementById("jh-fill-status");
    if (statusEl) {
      statusEl.textContent = `✓ Filled ${filledCount} verified fields!`;
      statusEl.style.color = "#34d399";
    }
    return filledCount;
  }

  async function solveScreeningQuestions() {
    if (!extState.payload) return 0;
    const textareas = Array.from(document.querySelectorAll("textarea, input[type='text']:not([value])"));
    const statusEl = document.getElementById("jh-fill-status");
    if (statusEl) statusEl.textContent = "Solving questions with Reviewer QA...";

    let solvedCount = 0;
    for (const el of textareas) {
      if (el.value) continue;
      const id = (el.id || "").toLowerCase();
      const name = (el.name || "").toLowerCase();
      // Skip personal info inputs
      if (/name|email|phone|city|location|linkedin|github|website/i.test(`${id} ${name}`)) continue;

      const labelEl = el.closest("div")?.querySelector("label") || el.closest("label");
      const question = labelEl?.innerText?.trim() || el.placeholder || el.getAttribute("aria-label");
      if (!question || question.length < 5) continue;

      try {
        const res = await fetch(`${BACKEND_BASE}/api/extension/solve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question, job: { title: document.title, url: window.location.href } }),
        });
        const env = await res.json();
        const data = env.data || env;
        if (data.answer) {
          fillInput(el, data.answer);
          solvedCount++;
        }
      } catch (e) {
        console.error("[JobHunter] Error solving question:", e);
      }
    }

    if (statusEl) {
      statusEl.textContent = `✓ Solved ${solvedCount} screening questions!`;
      statusEl.style.color = "#34d399";
    }
    return solvedCount;
  }

  function findSubmitOrNextButton() {
    const buttons = Array.from(document.querySelectorAll("button, input[type='submit'], a.btn"));
    // Look for submit button first
    for (const b of buttons) {
      const text = (b.innerText || b.value || "").toLowerCase().trim();
      if (/^(submit|submit application|apply now|send application)/i.test(text)) {
        return { el: b, isSubmit: true };
      }
    }
    // Look for next/continue button in multi-step wizards
    for (const b of buttons) {
      const text = (b.innerText || b.value || "").toLowerCase().trim();
      if (/^(next|continue|review application|save and continue|proceed)/i.test(text)) {
        return { el: b, isSubmit: false };
      }
    }
    return null;
  }

  async function runAutoPilot() {
    const statusEl = document.getElementById("jh-fill-status");
    if (statusEl) statusEl.textContent = "⚡ Auto-Pilot running: filling fields...";

    await performAutofill();
    await solveScreeningQuestions();

    const targetBtn = findSubmitOrNextButton();
    if (!targetBtn) {
      if (statusEl) statusEl.textContent = "✓ Fields filled. Please review and submit.";
      return;
    }

    if (!targetBtn.isSubmit) {
      if (statusEl) statusEl.textContent = "Advancing to next application step...";
      setTimeout(() => {
        targetBtn.el.click();
        setTimeout(runAutoPilot, 1800);
      }, 1200);
      return;
    }

    // Final Submit with 5s Safety Countdown
    let countdown = 5;
    if (statusEl) {
      statusEl.innerHTML = `Auto-submitting in <strong>${countdown}s</strong>... <button id="jh-cancel-submit" style="background:#ef4444;color:#fff;border:none;border-radius:3px;padding:2px 6px;cursor:pointer;margin-left:4px;">Cancel</button>`;
      document.getElementById("jh-cancel-submit")?.addEventListener("click", () => {
        clearInterval(extState.autoPilotTimer);
        statusEl.textContent = "Submission paused by user. Review and click Submit when ready.";
        statusEl.style.color = "#f4f4f5";
      });
    }

    extState.autoPilotTimer = setInterval(() => {
      countdown--;
      if (countdown > 0) {
        if (statusEl) {
          statusEl.innerHTML = `Auto-submitting in <strong>${countdown}s</strong>... <button id="jh-cancel-submit" style="background:#ef4444;color:#fff;border:none;border-radius:3px;padding:2px 6px;cursor:pointer;margin-left:4px;">Cancel</button>`;
          document.getElementById("jh-cancel-submit")?.addEventListener("click", () => {
            clearInterval(extState.autoPilotTimer);
            statusEl.textContent = "Submission paused by user. Review and click Submit when ready.";
          });
        }
      } else {
        clearInterval(extState.autoPilotTimer);
        if (statusEl) statusEl.textContent = "Submitting application...";
        targetBtn.el.click();
      }
    }, 1000);
  }

  function trackSubmission() {
    const notifyApplied = () => {
      if (extState.appliedConfirmed) return;
      extState.appliedConfirmed = true;
      fetch(`${BACKEND_BASE}/api/extension/confirm-applied`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: window.location.href,
          title: document.title,
          company: window.location.hostname,
          notes: `Submitted via JobHunter Copilot (${extState.platform.toUpperCase()})`,
        }),
      }).catch(() => {});
    };

    const forms = Array.from(document.querySelectorAll("form"));
    forms.forEach((form) => {
      form.addEventListener("submit", notifyApplied);
    });

    // Also observe DOM mutations for confirmation screens
    const observer = new MutationObserver(() => {
      const pageText = document.body ? document.body.innerText.toLowerCase() : "";
      if (
        pageText.includes("thank you for applying") ||
        pageText.includes("application submitted") ||
        pageText.includes("application has been received") ||
        pageText.includes("application received")
      ) {
        notifyApplied();
      }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  function buildUI() {
    if (document.getElementById("jh-flyout-container")) return;

    const launcher = document.createElement("button");
    launcher.id = "jh-launcher-btn";
    launcher.innerHTML = '<span>⚡</span> <span>JobHunter Copilot</span>';
    launcher.addEventListener("click", () => {
      const flyout = document.getElementById("jh-flyout-container");
      if (flyout) flyout.classList.toggle("jh-collapsed");
    });
    document.body.appendChild(launcher);

    const flyout = document.createElement("div");
    flyout.id = "jh-flyout-container";
    flyout.className = "jh-collapsed";
    const isLinkedIn = extState.platform === "linkedin";
    flyout.innerHTML = `
      <div class="jh-header">
        <div class="jh-header-left">
          <span class="jh-badge">2.4.0</span>
          <span class="jh-header-title">JobHunter Copilot</span>
        </div>
        <button class="jh-close-btn" id="jh-close-btn" aria-label="Close copilot">&times;</button>
      </div>
      <div class="jh-body">
        <div class="jh-card">
          <div class="jh-field-row">
            <span>Mode:</span>
            <span class="jh-field-val">${isLinkedIn ? "LINKEDIN OUTREACH" : extState.platform.toUpperCase()}</span>
          </div>
          <div class="jh-field-row">
            <span>Candidate:</span>
            <span class="jh-field-val" id="jh-cand-val">${escapeHtml(extState.candidateName || "Active Candidate")}</span>
          </div>
          <div class="jh-field-row">
            <span>Active Profile:</span>
            <span class="jh-field-val" id="jh-res-val">${escapeHtml(extState.activeResume || "Software Engineer")}</span>
          </div>
        </div>
        ${isLinkedIn ? `
          <button class="jh-action-btn" id="jh-gen-note-btn" style="background:#047857;color:#fff;">⚡ Generate &lt;300 Char Note</button>
          <button class="jh-action-btn" id="jh-gen-inmail-btn">📝 Generate Direct InMail</button>
          <button class="jh-action-btn" id="jh-insert-note-btn" style="display:none;background:#18181b;color:#34d399;border:1px solid #047857;">Insert into LinkedIn Note</button>
        ` : `
          <button class="jh-action-btn" id="jh-autopilot-btn" style="background:#047857;color:#fff;">⚡ Auto-Pilot (Fill & Submit)</button>
          <button class="jh-action-btn" id="jh-autofill-btn">📝 1-Click Autofill Form</button>
          <button class="jh-action-btn" id="jh-solve-btn">🤖 Answer Screening Questions</button>
        `}
        <div id="jh-fill-status" style="font-size:12px;text-align:left;min-height:16px;margin-top:6px;"></div>
      </div>
      <div class="jh-footer">
        <span>Protected Local Engine</span>
        <a href="${BACKEND_BASE}/" target="_blank" style="color:#34d399;text-decoration:none;font-weight:600;">Dashboard ↗</a>
      </div>
    `;
    document.body.appendChild(flyout);

    document.getElementById("jh-close-btn")?.addEventListener("click", () => {
      flyout.classList.add("jh-collapsed");
    });

    if (isLinkedIn) {
      async function fetchLinkedInPitch(isNoteOnly) {
        const statusEl = document.getElementById("jh-fill-status");
        if (statusEl) statusEl.textContent = "Analyzing profile & synthesizing grounded pitch...";

        const nameEl = document.querySelector("h1.text-heading-xlarge") || document.querySelector("h1");
        const headlineEl = document.querySelector(".text-body-medium") || document.querySelector("div.pv-text-details__left-panel");
        const founderName = nameEl ? nameEl.innerText.trim() : "";
        const founderHeadline = headlineEl ? headlineEl.innerText.trim() : "";

        try {
          const res = await fetch(`${BACKEND_BASE}/api/extension/founder-outreach`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              founder_name: founderName,
              founder_headline: founderHeadline,
              company: window.location.pathname.split("/")[2] || "Company",
            }),
          });
          const env = await res.json();
          const data = env.data || env;
          if (data && data.connection_note) {
            extState.lastLinkedInNote = data.connection_note;
            const insertBtn = document.getElementById("jh-insert-note-btn");
            if (insertBtn) insertBtn.style.display = "block";

            if (isNoteOnly) {
              if (statusEl) {
                statusEl.innerHTML = `<strong>Note (${data.connection_note_length}/300 chars):</strong><div style="background:#18181b;padding:8px;border-radius:4px;margin-top:4px;font-size:11px;line-height:1.5;">${escapeHtml(data.connection_note)}</div>`;
              }
            } else {
              if (statusEl) {
                statusEl.innerHTML = `<strong>InMail (${data.inmail_word_count} words):</strong><div style="background:#18181b;padding:8px;border-radius:4px;margin-top:4px;font-size:11px;line-height:1.5;white-space:pre-wrap;">${escapeHtml(data.inmail_body)}</div>`;
              }
            }
          }
        } catch (e) {
          if (statusEl) statusEl.textContent = "Error generating outreach. Ensure JobHunter daemon is running on :8765.";
        }
      }

      document.getElementById("jh-gen-note-btn")?.addEventListener("click", () => fetchLinkedInPitch(true));
      document.getElementById("jh-gen-inmail-btn")?.addEventListener("click", () => fetchLinkedInPitch(false));
      document.getElementById("jh-insert-note-btn")?.addEventListener("click", () => {
        if (!extState.lastLinkedInNote) return;
        const textarea = document.querySelector("textarea[name='message']") || document.querySelector("textarea#custom-message") || document.querySelector("textarea");
        if (textarea) {
          textarea.focus();
          textarea.value = extState.lastLinkedInNote;
          dispatchEvents(textarea);
          const statusEl = document.getElementById("jh-fill-status");
          if (statusEl) statusEl.textContent = "✓ Inserted into LinkedIn note input!";
        } else {
          navigator.clipboard.writeText(extState.lastLinkedInNote);
          const statusEl = document.getElementById("jh-fill-status");
          if (statusEl) statusEl.textContent = "✓ Copied to clipboard! (Modal textarea not open yet)";
        }
      });
    } else {
      document.getElementById("jh-autopilot-btn")?.addEventListener("click", runAutoPilot);
      document.getElementById("jh-autofill-btn")?.addEventListener("click", performAutofill);
      document.getElementById("jh-solve-btn")?.addEventListener("click", solveScreeningQuestions);
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
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
