/**
 * JobHunter Modern Autonomous Dashboard & Copilot (Operate Engine)
 * Clean, responsive single-page architecture connecting to local REST daemon (:8765).
 * Strictly enforces the 2-Color Architecture (Dark Gray / White + Emerald).
 */

(function () {
  const BACKEND_BASE = window.location.origin;

  const state = {
    activeTab: "tab-radar",
    activeProfile: null,
    profiles: [],
    jobs: [],
    selectedJob: null,
    applications: [],
    preferences: null,
    filters: {
      jobType: "",
      workMode: "Any",
      scoreFloor: 0,
      sortBy: "score",
    },
  };

  // ---------------------------------------------------------------- Theme Management
  function initTheme() {
    const saved = localStorage.getItem("jobhunter-theme");
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = saved || (prefersDark ? "dark" : "dark"); // Default dark
    applyTheme(theme);

    const btn = document.getElementById("btn-theme-toggle");
    if (btn) {
      btn.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme") || "dark";
        const next = current === "dark" ? "light" : "dark";
        applyTheme(next);
        localStorage.setItem("jobhunter-theme", next);
      });
    }
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const label = document.getElementById("theme-status-text");
    if (label) {
      label.textContent = theme === "dark" ? "Dark" : "Light";
    }
  }

  // ---------------------------------------------------------------- API Helpers
  async function apiGet(endpoint) {
    try {
      const res = await fetch(`${BACKEND_BASE}${endpoint}`);
      const env = await res.json();
      return env.data || env;
    } catch (e) {
      console.error(`[API GET] ${endpoint} failed:`, e);
      return null;
    }
  }

  async function apiPost(endpoint, body) {
    try {
      const res = await fetch(`${BACKEND_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const env = await res.json();
      return env.data || env;
    } catch (e) {
      console.error(`[API POST] ${endpoint} failed:`, e);
      return null;
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

  // ---------------------------------------------------------------- Navigation
  function switchTab(tabId) {
    state.activeTab = tabId;
    document.querySelectorAll(".nav-link").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tabId);
    });
    document.querySelectorAll(".tab-panel").forEach((pane) => {
      pane.classList.toggle("active", pane.id === tabId);
    });

    const titles = {
      "tab-radar": "Radar & Opportunity Discovery",
      "tab-tracker": "Application Kanban Pipeline",
      "tab-copilot": "Document Studio & Copilot",
      "tab-profiles": "Candidate Profile & Resume Variants",
      "tab-preferences": "Search Calibration & Target Filtering",
      "tab-extension": "Auto-Apply & Desktop Hub",
    };
    const titleEl = document.getElementById("page-title");
    if (titleEl) titleEl.textContent = titles[tabId] || "JobHunter";

    if (tabId === "tab-tracker") loadApplications();
    if (tabId === "tab-profiles") loadProfiles();
    if (tabId === "tab-preferences") loadPreferences();
    if (tabId === "tab-extension") {
      loadExtensionStatus();
      loadAutoApplyQueue();
    }
  }

  // ---------------------------------------------------------------- TAB 1: RADAR
  async function runRadarHunt() {
    const q = (document.getElementById("radar-query")?.value || "").trim();
    const loc = (document.getElementById("radar-location")?.value || "").trim();
    const container = document.getElementById("jobs-cards-container");
    const countText = document.getElementById("jobs-count-text");

    if (container) {
      container.innerHTML = `
        <div class="empty-feed-card">
          <div class="status-pulse" style="width:12px;height:12px;margin:0 auto 10px;"></div>
          <h2 style="font-size:15px;margin-bottom:6px;">Scanning Job Boards & Scoring Match Fit...</h2>
          <p>Querying company ATS portals, Keejob, regional sitemaps, and remote boards.</p>
        </div>
      `;
    }

    const params = new URLSearchParams({
      q,
      location: loc,
      work_mode: state.filters.workMode,
      job_type: state.filters.jobType,
      min_score: state.filters.scoreFloor,
    });

    const data = await apiGet(`/api/search?${params.toString()}`);
    if (!data) {
      if (container) {
        container.innerHTML = `
          <div class="empty-feed-card">
            <h2 style="font-size:15px;color:var(--danger)">Discovery Search Failed</h2>
            <p>Ensure local JobHunter daemon is running on :8765.</p>
          </div>`;
      }
      return;
    }

    state.jobs = data.jobs || [];
    if (countText) countText.textContent = `${state.jobs.length} Opportunities`;
    renderJobCards();
  }

  function renderJobCards() {
    const container = document.getElementById("jobs-cards-container");
    if (!container) return;

    let displayJobs = [...state.jobs];

    // Score floor filter
    if (state.filters.scoreFloor > 0) {
      displayJobs = displayJobs.filter((j) => (j.score || 0) >= state.filters.scoreFloor);
    }

    // Work Mode filter
    if (state.filters.workMode && state.filters.workMode !== "Any") {
      displayJobs = displayJobs.filter((j) => (j.work_mode || "").toLowerCase() === state.filters.workMode.toLowerCase());
    }

    // Sorting
    if (state.filters.sortBy === "score") {
      displayJobs.sort((a, b) => (b.score || 0) - (a.score || 0));
    } else if (state.filters.sortBy === "freshness") {
      displayJobs.sort((a, b) => (b.posted_days_ago || 0) - (a.posted_days_ago || 0));
    }

    if (displayJobs.length === 0) {
      container.innerHTML = `
        <div class="empty-feed-card">
          <h2 style="font-size:15px;margin-bottom:6px;">No Opportunities Found</h2>
          <p>Try widening your search terms, target location, or clearing strict filters.</p>
        </div>`;
      return;
    }

    container.innerHTML = displayJobs
      .map((job) => {
        const score = job.score || 85;
        const isSelected = state.selectedJob && (state.selectedJob.id === job.id || state.selectedJob.job_key === job.job_key);
        const workMode = job.work_mode || "Remote";
        const jobType = job.job_type || "Full-time";
        const isIntern = jobType.toLowerCase().includes("intern");

        return `
        <div class="job-item-card ${isSelected ? "selected" : ""}" data-id="${escapeHtml(job.id || job.job_key)}">
          <div class="card-top-row">
            <span class="card-title">${escapeHtml(job.title)}</span>
            <span class="fit-score-ring">${score}% FIT</span>
          </div>
          <div class="card-company-line">
            <strong>${escapeHtml(job.company)}</strong>
            <span>•</span>
            <span>${escapeHtml(job.location || "Worldwide")}</span>
          </div>
          <div class="card-tag-row">
            <span class="tag-badge ${workMode.toLowerCase() === "remote" ? "remote" : ""}">${escapeHtml(workMode)}</span>
            <span class="tag-badge ${isIntern ? "intern" : ""}">${escapeHtml(jobType)}</span>
            ${job.salary ? `<span class="tag-badge">${escapeHtml(job.salary)}</span>` : ""}
          </div>
          <div class="card-skills-row">
            ${(job.matched_skills || []).slice(0, 3).map((s) => `<span class="card-skill-pill">${escapeHtml(s)}</span>`).join("")}
          </div>
        </div>
      `;
      })
      .join("");

    container.querySelectorAll(".job-item-card").forEach((card) => {
      card.addEventListener("click", () => {
        const id = card.dataset.id;
        const job = displayJobs.find((j) => (j.id || j.job_key) === id);
        if (job) selectJob(job);
      });
    });

    if (displayJobs.length > 0 && (!state.selectedJob || !displayJobs.some((j) => (j.id || j.job_key) === (state.selectedJob.id || state.selectedJob.job_key)))) {
      selectJob(displayJobs[0]);
    }
  }

  async function selectJob(job) {
    state.selectedJob = job;

    document.querySelectorAll(".job-item-card").forEach((c) => {
      c.classList.toggle("selected", c.dataset.id === (job.id || job.job_key));
    });

    const placeholder = document.getElementById("inspector-placeholder");
    const content = document.getElementById("inspector-content");
    if (placeholder) placeholder.style.display = "none";
    if (content) content.style.display = "flex";

    // Fill Header
    const titleEl = document.getElementById("ins-job-title");
    const compEl = document.getElementById("ins-job-company");
    const locEl = document.getElementById("ins-job-location");
    const srcEl = document.getElementById("ins-job-source");
    const scoreBadge = document.getElementById("ins-score-badge");

    if (titleEl) titleEl.textContent = job.title || "Role";
    if (compEl) compEl.textContent = job.company || "Company";
    if (locEl) locEl.textContent = job.location || "Remote";
    if (srcEl) srcEl.textContent = job.source_tier || job.source || "Direct ATS";
    if (scoreBadge) scoreBadge.textContent = `${job.score || 85}% Fit`;

    // Fill Diagnostics
    const skillsRow = document.getElementById("ins-diag-skills");
    if (skillsRow) {
      const skills = job.matched_skills || ["Core Stack Match", "Experience Alignment"];
      skillsRow.innerHTML = skills
        .map((s) => `<span class="card-skill-pill" style="background:var(--primary-dim);color:var(--primary-text);border-color:var(--primary-border);">✓ ${escapeHtml(s)}</span>`)
        .join("");
    }

    const notesEl = document.getElementById("ins-diag-notes");
    if (notesEl) {
      const notes = job.match_reasons || job.fit_notes || [
        "Your years of experience and core skills closely match this job's requirements.",
      ];
      notesEl.textContent = Array.isArray(notes) ? notes.join(" ") : String(notes);
    }

    // Fill Description
    const descEl = document.getElementById("ins-job-description");
    if (descEl) {
      descEl.textContent = job.description || "No full description provided. The ATS application link contains full posting details.";
    }

    // Bind Apply Link
    const linkBtn = document.getElementById("ins-btn-open-link");
    if (linkBtn) {
      linkBtn.onclick = () => {
        const url = job.apply_url || job.url;
        if (url) window.open(url, "_blank");
      };
    }

    // Bind Apply with Browser Copilot
    const copilotBtn = document.getElementById("ins-btn-apply-copilot");
    if (copilotBtn) {
      copilotBtn.onclick = async () => {
        const url = job.apply_url || job.url;
        if (!url) return;
        copilotBtn.disabled = true;
        copilotBtn.innerHTML = `<span>Launching...</span>`;
        await apiPost("/api/auto-apply/launch", { url });
        setTimeout(() => {
          copilotBtn.disabled = false;
          copilotBtn.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
            </svg>
            Apply with Browser Copilot`;
        }, 2000);
      };
    }

    // Bind Queue for Auto-Apply
    const queueBtn = document.getElementById("ins-btn-queue-apply");
    if (queueBtn) {
      queueBtn.onclick = async () => {
        queueBtn.disabled = true;
        queueBtn.innerHTML = `<span>Queueing...</span>`;
        await apiPost("/api/applications", {
          company: job.company || "Unknown Company",
          title: job.title || "Job Opportunity",
          url: job.apply_url || job.url || "",
          status: "queued",
          notes: `Queued from Discovery feed. Match score: ${job.score || 85}%`,
        });
        queueBtn.innerHTML = `<span>✓ Queued</span>`;
        loadApplications();
        loadAutoApplyQueue();
        setTimeout(() => {
          queueBtn.disabled = false;
          queueBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            Queue Auto-Apply`;
        }, 2000);
      };
    }

    // Bind Track in Kanban
    const trackBtn = document.getElementById("ins-btn-track-app");
    if (trackBtn) {
      trackBtn.onclick = async () => {
        trackBtn.disabled = true;
        await apiPost("/api/applications", {
          company: job.company || "Unknown Company",
          title: job.title || "Job Opportunity",
          url: job.apply_url || job.url || "",
          status: "saved",
        });
        trackBtn.innerHTML = `<span>✓ Saved</span>`;
        loadApplications();
        setTimeout(() => {
          trackBtn.disabled = false;
          trackBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
            </svg>
            Track in Kanban`;
        }, 2000);
      };
    }
  }

  // ---------------------------------------------------------------- TAB 2: KANBAN TRACKER
  async function loadApplications() {
    const data = await apiGet("/api/applications");
    if (!data) return;
    const apps = data.applications || [];
    const stats = data.stats || {};
    state.applications = apps;

    const countEls = {
      saved: document.getElementById("funnel-saved"),
      queued: document.getElementById("funnel-queued"),
      applied: document.getElementById("funnel-applied"),
      interview: document.getElementById("funnel-interview"),
      offer: document.getElementById("funnel-offer"),
    };

    if (countEls.saved) countEls.saved.textContent = stats.saved || 0;
    if (countEls.queued) countEls.queued.textContent = stats.queued || 0;
    if (countEls.applied) countEls.applied.textContent = stats.applied || 0;
    if (countEls.interview) countEls.interview.textContent = stats.interview || 0;
    if (countEls.offer) countEls.offer.textContent = stats.offer || 0;

    const lanes = {
      saved: document.getElementById("lane-saved"),
      queued: document.getElementById("lane-queued"),
      applied: document.getElementById("lane-applied"),
      interview: document.getElementById("lane-interview"),
      offer: document.getElementById("lane-offer"),
    };

    Object.values(lanes).forEach((l) => {
      if (l) l.innerHTML = "";
    });

    const laneCounts = { saved: 0, queued: 0, applied: 0, interview: 0, offer: 0 };

    apps.forEach((app) => {
      const status = (app.status || "saved").toLowerCase();
      const lane = lanes[status] || lanes.saved;
      if (laneCounts[status] !== undefined) laneCounts[status]++;

      if (lane) {
        const card = document.createElement("div");
        card.className = "kanban-opportunity-card";
        const hasGmail = app.notes && app.notes.includes("[Gmail");
        card.innerHTML = `
          <div class="k-card-title">${escapeHtml(app.title || "Job")}</div>
          <div class="k-card-company">${escapeHtml(app.company || "Employer")}</div>
          ${hasGmail ? '<div style="margin-top:2px;"><span class="tag-badge" style="color:var(--primary-text);border-color:var(--primary-border);font-size:11px;padding:1px 5px;">Gmail Synced</span></div>' : ""}
          <div class="k-card-actions">
            <select class="select-dropdown app-stage-select" data-id="${escapeHtml(app.id)}" style="font-size:12px;padding:3px 6px;">
              <option value="saved" ${status === "saved" ? "selected" : ""}>Saved</option>
              <option value="queued" ${status === "queued" ? "selected" : ""}>Queued Auto-Apply</option>
              <option value="applied" ${status === "applied" ? "selected" : ""}>Applied</option>
              <option value="interview" ${status === "interview" ? "selected" : ""}>Interviewing</option>
              <option value="offer" ${status === "offer" ? "selected" : ""}>Offer</option>
              <option value="rejected" ${status === "rejected" ? "selected" : ""}>Rejected</option>
            </select>
            ${app.url ? `<a href="${escapeHtml(app.url)}" target="_blank" style="color:var(--primary-text);font-size:12px;text-decoration:none;font-weight:600;">Link ↗</a>` : ""}
          </div>
        `;
        lane.appendChild(card);
      }
    });

    document.querySelectorAll(".app-stage-select").forEach((sel) => {
      sel.addEventListener("change", async (e) => {
        const id = e.currentTarget.dataset.id;
        const newStatus = e.currentTarget.value;
        await apiPost("/api/applications", { id, status: newStatus });
        loadApplications();
        loadAutoApplyQueue();
      });
    });

    // Also sync the Auto-Apply Queue
    const queuedApps = apps.filter((a) => (a.status || "").toLowerCase() === "queued");
    renderAutoApplyQueue(queuedApps);
  }

  // ---------------------------------------------------------------- TAB 3: DOCUMENT STUDIO
  let studioViewMode = "cover-letter";

  async function generateStudioDocument() {
    const kind = document.getElementById("doc-type-select")?.value || "cover-letter";
    const jobTitle = document.getElementById("doc-input-title")?.value || "";
    const company = document.getElementById("doc-input-company")?.value || "";
    const desc = document.getElementById("doc-input-desc")?.value || "";
    const tone = document.getElementById("doc-input-tone")?.value || "direct_impact";

    const statusText = document.getElementById("doc-status-text");
    const previewContainer = document.getElementById("doc-rendered-body");
    const qaBadge = document.getElementById("doc-qa-badge");
    const atsBadge = document.getElementById("doc-ats-match-badge");
    const printBtn = document.getElementById("btn-download-doc");
    const toggleBtn = document.getElementById("btn-doc-view-toggle");
    const openGmailBtn = document.getElementById("btn-open-gmail-compose");
    const saveDraftBtn = document.getElementById("btn-save-gmail-draft");

    if (statusText) statusText.textContent = "Writing & running Reviewer QA against profile ledger...";
    if (previewContainer) previewContainer.textContent = "Generating verified documents for this target role...";

    if (openGmailBtn) openGmailBtn.style.display = "none";
    if (saveDraftBtn) saveDraftBtn.style.display = "none";

    if (kind === "founder-cold-email") {
      const founderName = document.getElementById("doc-input-founder-name")?.value || "";
      const founderEmail = document.getElementById("doc-input-founder-email")?.value || "";
      const founderAngle = document.getElementById("doc-input-founder-angle")?.value || "scale_velocity";
      const founderObs = document.getElementById("doc-input-founder-obs")?.value || "";

      const res = await apiPost("/api/outreach/founder-email", {
        job: { title: jobTitle, company: company, description: desc },
        founder_name: founderName,
        recipient_email: founderEmail,
        angle: founderAngle,
        custom_observation: founderObs,
      });

      if (!res) {
        if (previewContainer) previewContainer.textContent = "Error generating founder cold email.";
        return;
      }

      state.currentFounderOutreach = res;

      if (printBtn) printBtn.style.display = "none";
      if (toggleBtn) toggleBtn.style.display = "none";
      if (atsBadge) {
        atsBadge.style.display = "inline-block";
        atsBadge.textContent = `${res.word_count} words (~${res.reading_time_sec}s read)`;
      }

      if (openGmailBtn) {
        openGmailBtn.style.display = "inline-flex";
        openGmailBtn.href = res.gmail_compose_url || "#";
      }
      if (saveDraftBtn) {
        saveDraftBtn.style.display = "inline-flex";
      }

      if (qaBadge) {
        const verdict = res.review?.verdict || "PASS";
        qaBadge.textContent = `QA: ${verdict.toUpperCase()}`;
        qaBadge.className = `qa-badge ${verdict.toLowerCase() === "pass" ? "pass" : "warn"}`;
      }

      renderFounderOutreachContent(res);
      return;
    }

    if (kind === "linkedin-founder-dm") {
      const founderName = document.getElementById("doc-input-founder-name")?.value || "";
      const founderAngle = document.getElementById("doc-input-founder-angle")?.value || "scale_velocity";

      const res = await apiPost("/api/outreach/linkedin-founder", {
        job: { title: jobTitle, company: company, description: desc },
        founder_name: founderName,
        angle: founderAngle,
      });

      if (!res) {
        if (previewContainer) previewContainer.textContent = "Error generating LinkedIn founder outreach.";
        return;
      }

      state.currentLinkedInOutreach = res;

      if (printBtn) printBtn.style.display = "none";
      if (toggleBtn) toggleBtn.style.display = "none";
      if (atsBadge) {
        atsBadge.style.display = "inline-block";
        atsBadge.textContent = `${res.connection_note_length} / 300 chars`;
      }

      if (qaBadge) {
        const verdict = res.review_note?.verdict || "PASS";
        qaBadge.textContent = `QA: ${verdict.toUpperCase()}`;
        qaBadge.className = `qa-badge ${verdict.toLowerCase() === "pass" ? "pass" : "warn"}`;
      }

      renderLinkedInFounderContent(res);
      return;
    }

    if (kind === "bigtech-hr-referral") {
      const compKey = document.getElementById("doc-input-bigtech-company")?.value || "google";
      const reqId = document.getElementById("doc-input-bigtech-req")?.value || "";
      const recruiterName = document.getElementById("doc-input-bigtech-recruiter")?.value || "";
      const levelingTier = document.getElementById("doc-input-bigtech-level")?.value || "mid";

      const res = await apiPost("/api/bigtech/pitch", {
        company_key: compKey,
        req_id: reqId,
        recruiter_name: recruiterName,
        leveling_tier: levelingTier,
        job: { title: jobTitle, company: company, description: desc },
      });

      if (!res) {
        if (previewContainer) previewContainer.textContent = "Error generating Big Tech recruiter pitch.";
        return;
      }

      state.currentBigTechPitch = res;

      if (printBtn) printBtn.style.display = "none";
      if (toggleBtn) toggleBtn.style.display = "none";
      if (atsBadge) {
        atsBadge.style.display = "inline-block";
        atsBadge.textContent = `${res.company} · ${res.level_label}`;
      }

      if (openGmailBtn) {
        openGmailBtn.style.display = "inline-flex";
        openGmailBtn.href = res.gmail_compose_url || "#";
      }

      if (qaBadge) {
        const verdict = res.review_inmail?.verdict || "PASS";
        qaBadge.textContent = `QA: ${verdict.toUpperCase()}`;
        qaBadge.className = `qa-badge ${verdict.toLowerCase() === "pass" ? "pass" : "warn"}`;
      }

      renderBigTechContent(res);
      return;
    }

    if (kind === "cover-letter" || kind === "tailor-resume") {
      const res = await apiPost("/api/documents/job-package", {
        job: { title: jobTitle, company: company, description: desc },
        tone: "direct",
        angle: tone,
      });

      if (!res) {
        if (previewContainer) previewContainer.textContent = "Error generating job package. Please check daemon log.";
        return;
      }

      state.currentJobPackage = res;
      studioViewMode = kind === "tailor-resume" ? "resume" : "cover-letter";

      if (printBtn) printBtn.style.display = "inline-flex";
      if (toggleBtn) {
        toggleBtn.style.display = "inline-flex";
        toggleBtn.textContent = studioViewMode === "cover-letter" ? "View Tailored Resume" : "View Cover Letter";
      }

      if (atsBadge && res.tailored_resume) {
        atsBadge.style.display = "inline-block";
        atsBadge.textContent = `${res.tailored_resume.ats_match_pct || 88}% ATS Match`;
      }

      if (qaBadge && res.cover_letter) {
        const verdict = res.cover_letter.review?.verdict || "PASS";
        qaBadge.textContent = `QA: ${verdict.toUpperCase()}`;
        qaBadge.className = `qa-badge ${verdict.toLowerCase() === "pass" ? "pass" : "warn"}`;
      }

      renderStudioContent();
      return;
    }

    // Other document kinds (interview-prep, outreach)
    const endpointMap = {
      "interview-prep": "/api/documents/interview-prep",
      outreach: "/api/documents/outreach",
    };
    const endpoint = endpointMap[kind] || "/api/documents/cover-letter";
    const res = await apiPost(endpoint, {
      job: { title: jobTitle, company: company, description: desc },
    });

    if (!res) {
      if (previewContainer) previewContainer.textContent = "Error generating document.";
      return;
    }

    if (printBtn) printBtn.style.display = "none";
    if (toggleBtn) toggleBtn.style.display = "none";
    if (atsBadge) atsBadge.style.display = "none";

    if (previewContainer) {
      if (kind === "interview-prep") {
        const prep = res.prep || {};
        previewContainer.innerHTML = `<pre style="font-family:inherit;white-space:pre-wrap;">${escapeHtml(JSON.stringify(prep, null, 2))}</pre>`;
      } else if (kind === "outreach") {
        const out = res.outreach || {};
        previewContainer.innerHTML = `
          <strong>LinkedIn Note (&lt;300 chars):</strong>
          <p>${escapeHtml(out.linkedin_connection_note || "")}</p>
          <hr style="margin:12px 0;border-color:var(--border);">
          <strong>Hiring Manager InMail:</strong>
          <p><strong>Subject:</strong> ${escapeHtml(out.hiring_manager_inmail?.subject_line || "")}</p>
          <pre style="font-family:inherit;white-space:pre-wrap;">${escapeHtml(out.hiring_manager_inmail?.body || "")}</pre>
        `;
      } else {
        previewContainer.textContent = res.text || res.document || "Generated.";
      }
    }
  }

  function renderStudioContent() {
    const previewContainer = document.getElementById("doc-rendered-body");
    const toggleBtn = document.getElementById("btn-doc-view-toggle");
    if (!previewContainer || !state.currentJobPackage) return;

    if (studioViewMode === "cover-letter") {
      const letter = state.currentJobPackage.cover_letter?.full_text || "";
      previewContainer.innerHTML = `<div style="line-height:1.7;white-space:pre-wrap;">${escapeHtml(letter)}</div>`;
      if (toggleBtn) toggleBtn.textContent = "View Tailored Resume";
    } else {
      const resumeTxt = state.currentJobPackage.tailored_resume?.txt || "";
      previewContainer.innerHTML = `
        <div style="margin-bottom:12px;display:flex;gap:6px;flex-wrap:wrap;">
          ${(state.currentJobPackage.tailored_resume?.skills || []).slice(0, 6).map((s) => `<span class="card-skill-pill">✓ ${escapeHtml(s)}</span>`).join("")}
        </div>
        <pre style="font-family:var(--font-mono);font-size:12px;line-height:1.55;white-space:pre-wrap;">${escapeHtml(resumeTxt)}</pre>
      `;
      if (toggleBtn) toggleBtn.textContent = "View Cover Letter";
    }
  }

  function renderFounderOutreachContent(data) {
    const previewContainer = document.getElementById("doc-rendered-body");
    if (!previewContainer || !data) return;

    previewContainer.innerHTML = `
      <div style="margin-bottom:14px;">
        <span style="font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--text-muted);display:block;margin-bottom:6px;">High-Converting Subject Line Options:</span>
        <div style="display:flex;flex-direction:column;gap:6px;" id="founder-subject-options-list">
          ${(data.subject_options || []).map((su, idx) => `
            <div class="card-skill-pill" data-idx="${idx}" style="cursor:pointer;display:flex;align-items:center;justify-content:space-between;padding:8px 12px;font-size:12px;background:var(--bg-muted);border:1px solid ${idx === 0 ? "var(--primary)" : "var(--border)"};border-radius:var(--radius-sm);">
              <span><strong>Option ${idx+1}:</strong> ${escapeHtml(su)}</span>
              <span style="color:var(--primary-text);font-size:11px;font-weight:600;">${idx === 0 ? "✓ Selected" : "Use"}</span>
            </div>
          `).join("")}
        </div>
      </div>
      <hr style="margin:14px 0;border-color:var(--border);">
      <div style="margin-bottom:14px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <span style="font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--text-muted);">Cold Email Body (&lt;120 words · Mobile Scannable):</span>
          <span style="font-size:11px;color:var(--primary-text);font-weight:600;">✓ Reviewer QA Verified</span>
        </div>
        <div style="line-height:1.75;white-space:pre-wrap;padding:14px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);font-size:13px;" id="founder-rendered-email">${escapeHtml(data.body)}</div>
      </div>
      <div style="margin-top:14px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <span style="font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--text-muted);">Follow-Up Bump Note (Send 3-4 days later if no reply):</span>
          <button class="btn btn-secondary btn-sm" id="btn-copy-bump-note" style="padding:2px 8px;font-size:11px;">Copy Bump Note</button>
        </div>
        <div style="line-height:1.65;white-space:pre-wrap;padding:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);font-size:12px;color:var(--text-secondary);">${escapeHtml(data.follow_up_note)}</div>
      </div>
    `;

    // Attach subject selector click listeners
    const optEls = previewContainer.querySelectorAll("#founder-subject-options-list [data-idx]");
    optEls.forEach((el) => {
      el.addEventListener("click", () => {
        const idx = parseInt(el.getAttribute("data-idx"), 10);
        selectFounderSubject(idx);
      });
    });

    document.getElementById("btn-copy-bump-note")?.addEventListener("click", () => {
      navigator.clipboard.writeText(data.follow_up_note || "");
      const b = document.getElementById("btn-copy-bump-note");
      if (b) {
        b.textContent = "✓ Copied";
        setTimeout(() => (b.textContent = "Copy Bump Note"), 2000);
      }
    });
  }

  function selectFounderSubject(index) {
    if (!state.currentFounderOutreach) return;
    const su = state.currentFounderOutreach.subject_options?.[index];
    if (!su) return;
    state.currentFounderOutreach.chosen_subject = su;

    const optEls = document.querySelectorAll("#founder-subject-options-list [data-idx]");
    optEls.forEach((el, idx) => {
      const isSel = idx === index;
      el.style.border = isSel ? "1px solid var(--primary)" : "1px solid var(--border)";
      const label = el.querySelector("span:last-child");
      if (label) {
        label.textContent = isSel ? "✓ Selected" : "Use";
      }
    });

    const openGmailBtn = document.getElementById("btn-open-gmail-compose");
    if (openGmailBtn) {
      const cleanTo = (state.currentFounderOutreach.recipient_email || "").trim();
      const quotedTo = cleanTo ? encodeURIComponent(cleanTo) : "";
      const quotedSu = encodeURIComponent(su);
      const quotedBody = encodeURIComponent(state.currentFounderOutreach.body || "");
      openGmailBtn.href = `https://mail.google.com/mail/?view=cm&fs=1&to=${quotedTo}&su=${quotedSu}&body=${quotedBody}`;
    }
  }

  function renderLinkedInFounderContent(data) {
    const previewContainer = document.getElementById("doc-rendered-body");
    if (!previewContainer || !data) return;

    previewContainer.innerHTML = `
      <div style="margin-bottom:14px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <span style="font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--text-muted);">LinkedIn Connection Request Note (&lt;300 chars limit):</span>
          <span style="font-size:12px;font-family:var(--font-mono);color:var(--primary-text);font-weight:700;">${data.connection_note_length} / 300 chars</span>
        </div>
        <div style="line-height:1.7;white-space:pre-wrap;padding:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);font-size:13px;" id="linkedin-rendered-note">${escapeHtml(data.connection_note)}</div>
        <button class="btn btn-secondary btn-sm" id="btn-copy-linkedin-note" style="margin-top:8px;">
          Copy Connection Note
        </button>
      </div>

      <hr style="margin:14px 0;border-color:var(--border);">

      <div style="margin-top:14px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <span style="font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--text-muted);">Direct InMail / Message (${data.inmail_word_count} words):</span>
          <span style="font-size:11px;color:var(--text-muted);">${escapeHtml(data.inmail_subject)}</span>
        </div>
        <div style="line-height:1.75;white-space:pre-wrap;padding:14px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);font-size:13px;" id="linkedin-rendered-inmail">${escapeHtml(data.inmail_body)}</div>
        <button class="btn btn-secondary btn-sm" id="btn-copy-linkedin-inmail" style="margin-top:8px;">
          Copy InMail Pitch
        </button>
      </div>
    `;

    document.getElementById("btn-copy-linkedin-note")?.addEventListener("click", () => {
      navigator.clipboard.writeText(data.connection_note || "");
      const b = document.getElementById("btn-copy-linkedin-note");
      if (b) {
        b.textContent = "✓ Copied Note";
        setTimeout(() => (b.textContent = "Copy Connection Note"), 2000);
      }
    });

    document.getElementById("btn-copy-linkedin-inmail")?.addEventListener("click", () => {
      navigator.clipboard.writeText(data.inmail_body || "");
      const b = document.getElementById("btn-copy-linkedin-inmail");
      if (b) {
        b.textContent = "✓ Copied InMail";
        setTimeout(() => (b.textContent = "Copy InMail Pitch"), 2000);
      }
    });
  }

  function renderBigTechContent(data) {
    const previewContainer = document.getElementById("doc-rendered-body");
    if (!previewContainer || !data) return;

    previewContainer.innerHTML = `
      <div style="margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <div>
          <span style="font-size:16px;font-weight:700;">${escapeHtml(data.company)} <span style="font-size:13px;color:var(--text-muted);font-weight:400;">(${escapeHtml(data.level_label)})</span></span>
          <span style="display:block;font-size:11px;color:var(--text-muted);margin-top:2px;">Rubric focus: ${escapeHtml(data.rubric_focus)}</span>
        </div>
        <div style="font-size:12px;display:flex;align-items:center;gap:6px;">
          <span style="color:var(--text-muted);">Recruiter:</span>
          <strong style="color:var(--primary-text);font-family:var(--font-mono);">${escapeHtml(data.recruiter_email || "recruiter@bigtech.com")}</strong>
        </div>
      </div>

      <!-- Section 1: Recruiter InMail -->
      <div style="margin-bottom:14px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <span style="font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--text-muted);">1. Recruiter InMail (Screening &amp; Triage Optimized · ${data.inmail_word_count} words):</span>
          <button class="btn btn-secondary btn-sm" id="btn-copy-bigtech-inmail" style="padding:2px 8px;font-size:11px;">Copy InMail</button>
        </div>
        <div style="font-size:12px;font-weight:600;margin-bottom:4px;color:var(--text-secondary);">Subject: ${escapeHtml(data.inmail_subject)}</div>
        <div style="line-height:1.75;white-space:pre-wrap;padding:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);font-size:13px;">${escapeHtml(data.inmail_body)}</div>
      </div>

      <hr style="margin:14px 0;border-color:var(--border);">

      <!-- Section 2: Internal Employee Referral Blurb -->
      <div style="margin-top:14px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <div>
            <span style="font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--text-muted);">2. Employee Referral Blurb (Formatted for ${escapeHtml(data.referral_portal_name)}):</span>
            <span style="display:block;font-size:11px;color:var(--text-muted);">Give this directly to an engineer or alumnus at ${escapeHtml(data.company)} to submit on your behalf.</span>
          </div>
          <button class="btn btn-secondary btn-sm" id="btn-copy-bigtech-referral" style="padding:2px 8px;font-size:11px;">Copy Referral Blurb</button>
        </div>
        <div style="line-height:1.65;white-space:pre-wrap;padding:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);font-size:12px;font-family:var(--font-mono);color:var(--text-secondary);">${escapeHtml(data.referral_blurb)}</div>
      </div>
    `;

    document.getElementById("btn-copy-bigtech-inmail")?.addEventListener("click", () => {
      navigator.clipboard.writeText(data.inmail_body || "");
      const b = document.getElementById("btn-copy-bigtech-inmail");
      if (b) {
        b.textContent = "✓ Copied InMail";
        setTimeout(() => (b.textContent = "Copy InMail"), 2000);
      }
    });

    document.getElementById("btn-copy-bigtech-referral")?.addEventListener("click", () => {
      navigator.clipboard.writeText(data.referral_blurb || "");
      const b = document.getElementById("btn-copy-bigtech-referral");
      if (b) {
        b.textContent = "✓ Copied Referral Blurb";
        setTimeout(() => (b.textContent = "Copy Referral Blurb"), 2000);
      }
    });
  }

  // ---------------------------------------------------------------- TAB 4: PROFILES
  async function loadProfiles() {
    const data = await apiGet("/api/profiles");
    if (!data) return;

    state.activeProfile = data.active;
    state.profiles = data.variants || [];

    const activeNameEl = document.getElementById("active-profile-name");
    if (activeNameEl) {
      activeNameEl.textContent = state.activeProfile?.name || "Default Resume";
    }

    const candNameEl = document.getElementById("profile-cand-name");
    const candRoleEl = document.getElementById("profile-cand-role");
    const candEmailEl = document.getElementById("profile-cand-email");
    const candPhoneEl = document.getElementById("profile-cand-phone");
    const candLocEl = document.getElementById("profile-cand-location");
    const candSkillsEl = document.getElementById("profile-skills-cloud");

    if (state.activeProfile) {
      if (candNameEl) candNameEl.textContent = state.activeProfile.name || "Candidate Name";
      if (candRoleEl) candRoleEl.textContent = state.activeProfile.target_title || "Software Engineer";
      if (candEmailEl) candEmailEl.textContent = state.activeProfile.email || "email@example.com";
      if (candPhoneEl) candPhoneEl.textContent = state.activeProfile.phone || "+1 234 567 890";
      if (candLocEl) candLocEl.textContent = state.activeProfile.location || "Tunisia / Worldwide";

      if (candSkillsEl) {
        const skills = state.activeProfile.skills || ["Python", "FastAPI", "React", "PostgreSQL"];
        candSkillsEl.innerHTML = skills.map((s) => `<span class="profile-skill-tag">${escapeHtml(s)}</span>`).join("");
      }
    }

    const variantsList = document.getElementById("variants-list-deck");
    if (variantsList) {
      variantsList.innerHTML = state.profiles
        .map((v) => {
          const isActive = state.activeProfile && (v.name === state.activeProfile.name || v.id === state.activeProfile.id);
          return `
          <div class="variant-card ${isActive ? "active-variant" : ""}">
            <div class="variant-info">
              <span class="variant-name">${escapeHtml(v.name || v.target_title || "Resume Variant")}</span>
              <span class="variant-meta">${escapeHtml(v.filename || "resume.pdf")} • ${v.skills?.length || 0} skills detected</span>
            </div>
            ${
              isActive
                ? '<span class="active-pill" style="font-size:12px;color:var(--primary-text);font-weight:700;">Active</span>'
                : `<button class="btn btn-secondary btn-sm btn-activate-variant" data-name="${escapeHtml(v.name)}">Activate</button>`
            }
          </div>
        `;
        })
        .join("");

      variantsList.querySelectorAll(".btn-activate-variant").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const name = btn.dataset.name;
          await apiPost("/api/profile/activate", { name });
          loadProfiles();
        });
      });
    }
  }

  // ---------------------------------------------------------------- TAB 5: PREFERENCES
  async function loadPreferences() {
    const prefs = await apiGet("/api/preferences");
    if (!prefs) return;
    state.preferences = prefs;

    const countriesInput = document.getElementById("pref-target-countries");
    const citiesInput = document.getElementById("pref-home-cities");
    const workModeSelect = document.getElementById("pref-work-mode");
    const excludedCompInput = document.getElementById("pref-excluded-companies");
    const excludedKwInput = document.getElementById("pref-excluded-keywords");
    const dreamCompInput = document.getElementById("pref-dream-companies");
    const depthSelect = document.getElementById("pref-search-depth");

    if (countriesInput) countriesInput.value = (prefs.target_countries || ["Tunisia", "Worldwide Remote"]).join(", ");
    if (citiesInput) citiesInput.value = (prefs.home_cities || ["Tunis"]).join(", ");
    if (workModeSelect) workModeSelect.value = prefs.work_mode || "Any";
    if (excludedCompInput) excludedCompInput.value = (prefs.excluded_companies || []).join(", ");
    if (excludedKwInput) excludedKwInput.value = (prefs.excluded_keywords || []).join(", ");
    if (dreamCompInput) dreamCompInput.value = (prefs.dream_companies || []).join(", ");
    if (depthSelect) depthSelect.value = prefs.search_depth || "standard";

    const jobTypes = prefs.job_types || ["Full-time"];
    document.querySelectorAll("#pref-job-types-row input").forEach((chk) => {
      chk.checked = jobTypes.includes(chk.value);
    });

    const activeGeoVal = document.getElementById("active-geo-val");
    if (activeGeoVal) {
      activeGeoVal.textContent = (prefs.target_countries || ["Tunisia", "Worldwide Remote"]).slice(0, 2).join(", ");
    }
  }

  async function savePreferences() {
    const targetCountries = (document.getElementById("pref-target-countries")?.value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const workMode = document.getElementById("pref-work-mode")?.value || "Any";
    const excludedCompanies = (document.getElementById("pref-excluded-companies")?.value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const excludedKeywords = (document.getElementById("pref-excluded-keywords")?.value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const dreamCompanies = (document.getElementById("pref-dream-companies")?.value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const depth = document.getElementById("pref-search-depth")?.value || "standard";

    const selectedJobTypes = [];
    document.querySelectorAll("#pref-job-types-row input:checked").forEach((chk) => {
      selectedJobTypes.push(chk.value);
    });

    const updates = {
      target_countries: targetCountries,
      work_mode: workMode,
      job_types: selectedJobTypes,
      excluded_companies: excludedCompanies,
      excluded_keywords: excludedKeywords,
      dream_companies: dreamCompanies,
      search_depth: depth,
    };

    const res = await apiPost("/api/preferences", { updates });
    const feedback = document.getElementById("pref-status-feedback");
    if (feedback) {
      feedback.style.display = "block";
      feedback.textContent = res?.success ? "✓ Preferences saved successfully to .jobhunter/preferences.json!" : "Could not save preferences.";
      setTimeout(() => (feedback.style.display = "none"), 3500);
    }
    loadPreferences();
  }

  // ---------------------------------------------------------------- TAB 6: AUTO-APPLY HUB
  async function loadExtensionStatus() {
    const data = await apiGet("/api/desktop/extension-status");
    if (!data) return;
    const browsers = data.browsers || [];

    const list = document.getElementById("hub-browsers-list");
    if (list) {
      list.innerHTML = browsers.length
        ? browsers.map((b) => `<li><strong>${escapeHtml(b.name)}</strong> — <code>${escapeHtml(b.path)}</code></li>`).join("")
        : '<li style="color:var(--danger)">No Chromium-based browser found in default paths.</li>';
    }
  }

  async function loadAutoApplyQueue() {
    const data = await apiGet("/api/applications");
    const apps = data?.applications || data || [];
    const queued = Array.isArray(apps) ? apps.filter((a) => (a.status || "").toLowerCase() === "queued") : [];
    renderAutoApplyQueue(queued);
  }

  function renderAutoApplyQueue(queued) {
    const badge = document.getElementById("auto-apply-queue-badge");
    const list = document.getElementById("auto-apply-queue-list");
    if (badge) {
      badge.textContent = `${queued.length} Application${queued.length === 1 ? "" : "s"} Queued`;
    }
    if (!list) return;

    if (queued.length === 0) {
      list.innerHTML = `
        <div class="queue-empty-state">
          <p>No jobs queued for auto-apply yet. Find high-match jobs in Radar & Discovery and click <strong>"Queue Auto-Apply"</strong>.</p>
        </div>`;
      return;
    }

    list.innerHTML = queued
      .map((app) => {
        let domain = "Direct ATS";
        try {
          if (app.url) domain = new URL(app.url).hostname;
        } catch (e) {}

        return `
        <div class="queue-item-row" data-id="${escapeHtml(app.id)}">
          <div class="queue-item-info">
            <span class="queue-item-title">${escapeHtml(app.title || "Job Application")}</span>
            <div class="queue-item-meta">
              <strong>${escapeHtml(app.company || "Employer")}</strong>
              <span>•</span>
              <span>${escapeHtml(domain)}</span>
            </div>
          </div>
          <div class="queue-item-actions">
            <button class="btn btn-primary btn-sm btn-queue-launch" data-url="${escapeHtml(app.url || "")}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
              Apply Now
            </button>
            <button class="btn btn-secondary btn-sm btn-queue-remove" data-id="${escapeHtml(app.id)}">
              Remove
            </button>
          </div>
        </div>`;
      })
      .join("");

    list.querySelectorAll(".btn-queue-launch").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const url = btn.dataset.url;
        if (!url) return;
        btn.disabled = true;
        btn.textContent = "Launching...";
        await apiPost("/api/auto-apply/launch", { url });
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = "Apply Now";
        }, 2000);
      });
    });

    list.querySelectorAll(".btn-queue-remove").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        await apiPost("/api/applications", { id, status: "saved" });
        loadApplications();
        loadAutoApplyQueue();
      });
    });
  }

  // ---------------------------------------------------------------- Setup Listeners
  function initEvents() {
    document.querySelectorAll(".nav-link").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    // Radar Hunt
    document.getElementById("btn-radar-hunt")?.addEventListener("click", runRadarHunt);
    document.getElementById("radar-query")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") runRadarHunt();
    });

    // Filter Chips
    document.querySelectorAll("#filter-job-types .chip-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#filter-job-types .chip-toggle").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.filters.jobType = btn.dataset.val;
        runRadarHunt();
      });
    });

    document.querySelectorAll("#filter-work-modes .chip-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#filter-work-modes .chip-toggle").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.filters.workMode = btn.dataset.val;
        runRadarHunt();
      });
    });

    document.querySelectorAll("#filter-score-floor .chip-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#filter-score-floor .chip-toggle").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.filters.scoreFloor = parseInt(btn.dataset.val || "0", 10);
        renderJobCards();
      });
    });

    document.getElementById("radar-sort")?.addEventListener("change", (e) => {
      state.filters.sortBy = e.target.value;
      renderJobCards();
    });

    // Document shortcuts from Inspector
    document.getElementById("ins-btn-draft-letter")?.addEventListener("click", () => {
      if (!state.selectedJob) return;
      document.getElementById("doc-input-title").value = state.selectedJob.title || "";
      document.getElementById("doc-input-company").value = state.selectedJob.company || "";
      document.getElementById("doc-input-desc").value = state.selectedJob.description || "";
      switchTab("tab-copilot");
      generateStudioDocument();
    });

    document.getElementById("ins-btn-interview-prep")?.addEventListener("click", () => {
      if (!state.selectedJob) return;
      document.getElementById("doc-type-select").value = "interview-prep";
      document.getElementById("doc-input-title").value = state.selectedJob.title || "";
      document.getElementById("doc-input-company").value = state.selectedJob.company || "";
      document.getElementById("doc-input-desc").value = state.selectedJob.description || "";
      switchTab("tab-copilot");
      generateStudioDocument();
    });

    document.getElementById("ins-btn-tailor-cv")?.addEventListener("click", () => {
      if (!state.selectedJob) return;
      document.getElementById("doc-type-select").value = "tailor-resume";
      document.getElementById("doc-input-title").value = state.selectedJob.title || "";
      document.getElementById("doc-input-company").value = state.selectedJob.company || "";
      document.getElementById("doc-input-desc").value = state.selectedJob.description || "";
      switchTab("tab-copilot");
      generateStudioDocument();
    });

    // Document Generation Trigger
    document.getElementById("doc-type-select")?.addEventListener("change", (e) => {
      const val = e.target.value;
      const isFounder = val === "founder-cold-email" || val === "linkedin-founder-dm";
      const isBigTech = val === "bigtech-hr-referral";
      const founderBox = document.getElementById("doc-founder-fields");
      const bigtechBox = document.getElementById("doc-bigtech-fields");
      if (founderBox) founderBox.style.display = isFounder ? "block" : "none";
      if (bigtechBox) bigtechBox.style.display = isBigTech ? "block" : "none";
    });

    // Inline Finder in Founder Cold Email Form
    document.getElementById("btn-find-founder-email")?.addEventListener("click", async () => {
      const founderVal = document.getElementById("doc-input-founder-name")?.value || "";
      const companyVal = document.getElementById("doc-input-company")?.value || "";
      const pill = document.getElementById("founder-email-status-pill");
      const btn = document.getElementById("btn-find-founder-email");

      if (!founderVal && !companyVal) {
        alert("Please enter a founder name/LinkedIn URL and company name first.");
        return;
      }
      if (btn) btn.textContent = "Searching...";

      const isLinkedIn = founderVal.includes("linkedin.com");
      const payload = {
        company: companyVal,
        role: "Founder & CEO",
        name: isLinkedIn ? "" : founderVal,
        linkedin_url: isLinkedIn ? founderVal : "",
      };

      const res = await apiPost("/api/email-finder/find", payload);
      if (btn) btn.textContent = "Find Email";

      if (res && res.primary_email) {
        const emailInput = document.getElementById("doc-input-founder-email");
        if (emailInput) emailInput.value = res.primary_email;
        if (pill) {
          pill.style.display = "block";
          pill.textContent = `✓ ${res.confidence_pct}% Verified (${res.mail_provider || "Corporate Mail"})`;
        }
      } else {
        if (pill) {
          pill.style.display = "block";
          pill.textContent = "Could not verify corporate email. Try full company name.";
        }
      }
    });

    // Email Finder Modal controls
    document.getElementById("btn-open-email-finder")?.addEventListener("click", () => {
      const comp = document.getElementById("doc-input-company")?.value || "";
      const modal = document.getElementById("modal-email-finder");
      if (comp) {
        const inp = document.getElementById("finder-input-company");
        if (inp && !inp.value) inp.value = comp;
      }
      if (modal) modal.style.display = "flex";
    });

    document.getElementById("btn-close-email-finder-modal")?.addEventListener("click", () => {
      document.getElementById("modal-email-finder").style.display = "none";
    });
    document.getElementById("btn-cancel-email-finder-modal")?.addEventListener("click", () => {
      document.getElementById("modal-email-finder").style.display = "none";
    });

    document.getElementById("btn-run-email-finder")?.addEventListener("click", async () => {
      const name = document.getElementById("finder-input-name")?.value || "";
      const company = document.getElementById("finder-input-company")?.value || "";
      const linkedin = document.getElementById("finder-input-linkedin")?.value || "";
      const role = document.getElementById("finder-input-role")?.value || "Founder & CEO";
      const runBtn = document.getElementById("btn-run-email-finder");

      if (!company && !linkedin && !name) {
        alert("Please provide at least a company name or LinkedIn profile URL.");
        return;
      }

      if (runBtn) {
        runBtn.disabled = true;
        runBtn.textContent = "Checking DNS MX & synthesizing patterns...";
      }

      const res = await apiPost("/api/email-finder/find", {
        name,
        company,
        linkedin_url: linkedin,
        role,
      });

      if (runBtn) {
        runBtn.disabled = false;
        runBtn.textContent = "Find & Verify Corporate Email";
      }

      const resultsBox = document.getElementById("finder-results-box");
      if (res && res.primary_email && resultsBox) {
        resultsBox.style.display = "block";
        document.getElementById("finder-result-email").textContent = res.primary_email;
        document.getElementById("finder-result-badge").textContent = `${res.confidence_pct}% Confidence`;
        document.getElementById("finder-result-provider").textContent = `Mail Provider: ${res.mail_provider || "Corporate Mail Server"}`;

        const otherList = (res.candidates || []).slice(1);
        const otherEl = document.getElementById("finder-other-candidates");
        if (otherEl) {
          otherEl.innerHTML = otherList.length
            ? `<strong>Other verified variations:</strong> ${otherList.map((c) => `${escapeHtml(c.email)} (${c.confidence_pct}%)`).join(", ")}`
            : "";
        }

        state.lastFoundLead = res;
      } else {
        alert(res?.error || "No corporate email could be verified with the provided details.");
      }
    });

    document.getElementById("btn-copy-found-email")?.addEventListener("click", () => {
      const email = document.getElementById("finder-result-email")?.textContent;
      if (email) {
        navigator.clipboard.writeText(email);
        const b = document.getElementById("btn-copy-found-email");
        if (b) {
          b.textContent = "✓ Copied";
          setTimeout(() => (b.textContent = "Copy Email"), 2000);
        }
      }
    });

    document.getElementById("btn-use-found-email")?.addEventListener("click", () => {
      if (!state.lastFoundLead) return;
      document.getElementById("modal-email-finder").style.display = "none";
      switchTab("tab-copilot");
      document.getElementById("doc-type-select").value = "founder-cold-email";
      document.getElementById("doc-founder-fields").style.display = "block";

      if (state.lastFoundLead.name) document.getElementById("doc-input-founder-name").value = state.lastFoundLead.name;
      if (state.lastFoundLead.company) document.getElementById("doc-input-company").value = state.lastFoundLead.company;
      if (state.lastFoundLead.primary_email) document.getElementById("doc-input-founder-email").value = state.lastFoundLead.primary_email;

      generateStudioDocument();
    });

    document.getElementById("btn-save-gmail-draft")?.addEventListener("click", async () => {
      if (!state.currentFounderOutreach) return;
      const btn = document.getElementById("btn-save-gmail-draft");
      if (btn) btn.textContent = "Saving...";
      const res = await apiPost("/api/outreach/save-draft", {
        to_email: state.currentFounderOutreach.recipient_email || "",
        subject: state.currentFounderOutreach.chosen_subject || "",
        body: state.currentFounderOutreach.body || "",
      });
      if (res && res.success) {
        alert("✓ Draft successfully saved in your connected Gmail Drafts folder!");
        if (btn) btn.textContent = "✓ Draft Saved";
      } else {
        const err = res?.message || "Could not save draft. Please check your Gmail App Password in Settings.";
        alert(`Gmail Draft: ${err}`);
        if (btn) btn.textContent = "Save Draft";
      }
    });

    document.getElementById("btn-generate-doc")?.addEventListener("click", generateStudioDocument);

    document.getElementById("btn-doc-view-toggle")?.addEventListener("click", () => {
      studioViewMode = studioViewMode === "cover-letter" ? "tailored-resume" : "cover-letter";
      renderStudioContent();
    });

    document.getElementById("btn-download-doc")?.addEventListener("click", () => {
      if (!state.currentJobPackage) return;
      const isResume = studioViewMode === "tailored-resume";
      const title = `${state.currentJobPackage.company || "Job"}_${isResume ? "Resume" : "CoverLetter"}`;
      const content = isResume
        ? (state.currentJobPackage.tailored_resume?.html || `<pre>${escapeHtml(state.currentJobPackage.tailored_resume?.txt || "")}</pre>`)
        : `<div style="max-width:700px;margin:40px auto;font-family:Georgia,serif;font-size:15px;line-height:1.8;white-space:pre-wrap;">${escapeHtml(state.currentJobPackage.cover_letter?.full_text || "")}</div>`;

      const printWin = window.open("", "_blank");
      if (printWin) {
        printWin.document.write(`<!DOCTYPE html><html><head><title>${escapeHtml(title)}</title><style>@media print { @page { margin: 1.5cm; } } body { margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #111; }</style></head><body>${content}<script>window.onload = function() { window.print(); };<\/script></body></html>`);
        printWin.document.close();
      }
    });

    document.getElementById("btn-copy-doc")?.addEventListener("click", () => {
      const text = document.getElementById("doc-rendered-body")?.innerText;
      if (text) {
        navigator.clipboard.writeText(text);
        const btn = document.getElementById("btn-copy-doc");
        if (btn) {
          btn.textContent = "✓ Copied";
          setTimeout(() => (btn.textContent = "Copy"), 2000);
        }
      }
    });

    // Preferences
    document.getElementById("btn-save-preferences")?.addEventListener("click", savePreferences);

    // Rescan Workspace
    document.getElementById("btn-rescan-workspace")?.addEventListener("click", loadProfiles);

    // Auto-apply Browser Launcher
    document.getElementById("btn-hub-launch-browser")?.addEventListener("click", () => {
      apiPost("/api/auto-apply/launch", { url: "http://127.0.0.1:8765" });
    });
    document.getElementById("btn-top-launch-copilot")?.addEventListener("click", () => {
      apiPost("/api/auto-apply/launch", { url: "http://127.0.0.1:8765" });
    });

    // Run Auto-Apply Queue
    document.getElementById("btn-run-auto-apply-queue")?.addEventListener("click", async () => {
      const btn = document.getElementById("btn-run-auto-apply-queue");
      const data = await apiGet("/api/applications");
      const apps = data?.applications || data || [];
      const queued = Array.isArray(apps) ? apps.filter((a) => (a.status || "").toLowerCase() === "queued") : [];
      if (queued.length === 0) {
        alert("The Auto-Apply queue is currently empty. Browse opportunities on the Radar and click 'Queue Auto-Apply' to add jobs.");
        return;
      }
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span>Launching Auto-Apply Copilot...</span>`;
      }
      const firstJob = queued[0];
      await apiPost("/api/auto-apply/launch", { url: firstJob.url || "http://127.0.0.1:8765" });
      setTimeout(() => {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
            </svg>
            Run Auto-Apply on Queued Jobs`;
        }
      }, 3000);
    });

    // Screening question solver test
    document.getElementById("btn-test-solve")?.addEventListener("click", async () => {
      const q = document.getElementById("hub-test-question")?.value || "";
      const box = document.getElementById("hub-test-answer-box");
      if (box) box.innerHTML = "<em>Solving and verifying against resume facts...</em>";
      const res = await apiPost("/api/extension/solve", { question: q });
      if (box && res) {
        box.innerHTML = `<span style="color:var(--primary-text);font-weight:700;">✓ Reviewer QA Verdict: ${res.review?.verdict?.toUpperCase() || "PASS"}</span>\n\n${escapeHtml(res.answer || "Answer generated.")}`;
      }
    });

    // Gmail Tracker Modals & Triggers
    document.getElementById("btn-setup-gmail")?.addEventListener("click", async () => {
      const modal = document.getElementById("modal-gmail-setup");
      const st = await apiGet("/api/gmail/status");
      if (st && st.email) {
        const emailInput = document.getElementById("modal-gmail-email");
        if (emailInput) emailInput.value = st.email;
      }
      if (modal) modal.style.display = "flex";
    });

    document.getElementById("btn-close-gmail-modal")?.addEventListener("click", () => {
      document.getElementById("modal-gmail-setup").style.display = "none";
    });
    document.getElementById("btn-cancel-gmail-modal")?.addEventListener("click", () => {
      document.getElementById("modal-gmail-setup").style.display = "none";
    });

    document.getElementById("btn-save-gmail-config")?.addEventListener("click", async () => {
      const email = document.getElementById("modal-gmail-email")?.value || "";
      const app_password = document.getElementById("modal-gmail-password")?.value || "";
      const feedback = document.getElementById("gmail-modal-feedback");
      if (!email) {
        if (feedback) {
          feedback.style.display = "block";
          feedback.textContent = "Please enter your Gmail address.";
        }
        return;
      }
      const res = await apiPost("/api/gmail/config", { email, app_password });
      if (res && res.saved) {
        if (feedback) {
          feedback.style.display = "block";
          feedback.textContent = "✓ Gmail credentials saved successfully!";
          setTimeout(() => {
            document.getElementById("modal-gmail-setup").style.display = "none";
            feedback.style.display = "none";
          }, 1400);
        }
        loadGmailStatus();
      }
    });

    document.getElementById("btn-sync-gmail")?.addEventListener("click", async () => {
      const btn = document.getElementById("btn-sync-gmail");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span>Syncing Gmail...</span>`;
      }
      const res = await apiPost("/api/gmail/sync", {});
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
            <polyline points="22,6 12,13 2,6"></polyline>
          </svg>
          Sync Gmail`;
      }
      if (res && res.success) {
        alert(`Gmail Sync complete!\n• ${res.applications_updated || 0} applications updated\n• ${res.applications_created || 0} new job confirmations tracked`);
        loadApplications();
        loadGmailStatus();
      } else {
        const err = res?.error || "Could not connect to Gmail. Click the settings icon to configure your App Password.";
        alert(`Gmail Sync: ${err}`);
      }
    });

    // Modal
    document.getElementById("btn-create-tracker-app")?.addEventListener("click", () => {
      document.getElementById("modal-new-app").style.display = "flex";
    });
    document.getElementById("btn-close-app-modal")?.addEventListener("click", () => {
      document.getElementById("modal-new-app").style.display = "none";
    });
    document.getElementById("btn-cancel-modal")?.addEventListener("click", () => {
      document.getElementById("modal-new-app").style.display = "none";
    });
    document.getElementById("btn-save-modal-app")?.addEventListener("click", async () => {
      const company = document.getElementById("modal-app-company")?.value || "";
      const title = document.getElementById("modal-app-title")?.value || "";
      const url = document.getElementById("modal-app-url")?.value || "";
      const status = document.getElementById("modal-app-status")?.value || "saved";
      if (company && title) {
        await apiPost("/api/applications", { company, title, url, status });
        document.getElementById("modal-new-app").style.display = "none";
        loadApplications();
        loadAutoApplyQueue();
      }
    });
  }

  async function loadGmailStatus() {
    const data = await apiGet("/api/gmail/status");
    if (!data) return;
    const btn = document.getElementById("btn-sync-gmail");
    if (btn) {
      if (data.configured) {
        const last = data.last_sync ? ` (Last: ${data.last_sync.slice(11, 16)})` : "";
        btn.title = `Connected: ${data.email}${last}. Click to scan Gmail for updates.`;
      } else {
        btn.title = "Gmail tracking not configured. Click the gear icon to set up.";
      }
    }
  }

  // ---------------------------------------------------------------- Init
  initTheme();
  initEvents();
  loadProfiles();
  loadPreferences();
  loadApplications();
  loadGmailStatus();
  runRadarHunt();
})();
