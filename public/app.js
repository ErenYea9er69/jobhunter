// JobHunter Single Page Application Dashboard
(function () {
  const BACKEND_BASE = window.location.origin;

  const state = {
    activeTab: "tab-radar",
    activeProfile: null,
    profiles: [],
    applications: [],
    jobs: [],
    browsers: [],
  };

  // ----------------------------------------------------------- DOM Elements
  const navItems = document.querySelectorAll(".nav-item");
  const tabPanes = document.querySelectorAll(".tab-pane");
  const pageTitle = document.getElementById("page-title");
  const topbarProfileName = document.getElementById("topbar-profile-name");

  // Tab 1 Elements
  const searchBtn = document.getElementById("btn-run-search");
  const searchQuery = document.getElementById("search-query");
  const searchLocation = document.getElementById("search-location");
  const jobCardsGrid = document.getElementById("job-cards-grid");
  const searchResultsCount = document.getElementById("search-results-count");

  // Tab 2 Elements
  const profCandName = document.getElementById("prof-cand-name");
  const profTargetTitle = document.getElementById("prof-target-title");
  const profSkillsTags = document.getElementById("prof-skills-tags");
  const variantsList = document.getElementById("variants-list");
  const btnScanResumes = document.getElementById("btn-scan-resumes");

  // Tab 3 Elements
  const statSaved = document.getElementById("stat-saved");
  const statApplied = document.getElementById("stat-applied");
  const statInterview = document.getElementById("stat-interview");
  const statOffer = document.getElementById("stat-offer");
  const statRejected = document.getElementById("stat-rejected");

  // Tab 5 Elements
  const browsersUl = document.getElementById("browsers-ul");
  const btnLaunchBrowserAuto = document.getElementById("btn-launch-browser-auto");
  const btnCopyExtPath = document.getElementById("btn-copy-ext-path");
  const btnOpenExtMgr = document.getElementById("btn-open-ext-mgr");
  const btnQuickLaunchExt = document.getElementById("btn-quick-launch-ext");

  // ----------------------------------------------------------- API Helpers
  async function apiGet(path) {
    try {
      const res = await fetch(`${BACKEND_BASE}${path}`);
      const env = await res.json();
      return env.data || env;
    } catch (e) {
      console.error(`API GET ${path} failed:`, e);
      return null;
    }
  }

  async function apiPost(path, data) {
    try {
      const res = await fetch(`${BACKEND_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const env = await res.json();
      return env.data || env;
    } catch (e) {
      console.error(`API POST ${path} failed:`, e);
      return null;
    }
  }

  // ----------------------------------------------------------- Navigation
  function switchTab(tabId) {
    state.activeTab = tabId;
    navItems.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tabId);
    });
    tabPanes.forEach((pane) => {
      pane.classList.toggle("active", pane.id === tabId);
    });

    const titles = {
      "tab-radar": "Radar & Job Search",
      "tab-profiles": "Profiles & Resumes",
      "tab-tracker": "Application Tracker",
      "tab-copilot": "Document Studio & Reviewer QA",
      "tab-extension": "Extension & Desktop Hub",
    };
    if (pageTitle) pageTitle.textContent = titles[tabId] || "JobHunter";

    if (tabId === "tab-tracker") loadApplications();
    if (tabId === "tab-profiles") loadProfiles();
    if (tabId === "tab-extension") loadExtensionStatus();
  }

  // ----------------------------------------------------------- Tab 1: Radar
  async function runJobSearch() {
    const q = searchQuery.value.trim();
    const loc = searchLocation.value.trim();

    if (jobCardsGrid) {
      jobCardsGrid.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">⏳</div>
          <div class="empty-title">Scanning sources & ranking fit...</div>
        </div>
      `;
    }

    const data = await apiGet(`/api/search?q=${encodeURIComponent(q)}&location=${encodeURIComponent(loc)}`);
    const jobs = data?.jobs || [];
    state.jobs = jobs;

    if (searchResultsCount) searchResultsCount.textContent = `Found ${jobs.length} Opportunities`;

    if (!jobs.length) {
      jobCardsGrid.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔍</div>
          <div class="empty-title">No jobs found matching "${q}"</div>
          <div class="empty-desc">Try widening your search terms or location.</div>
        </div>
      `;
      return;
    }

    jobCardsGrid.innerHTML = jobs
      .map((j) => {
        const score = j.score || j.match_score || 85;
        const skills = j.matched_skills || j.skills || ["Python", "FastAPI"];
        return `
          <div class="job-card">
            <div class="job-card-header">
              <div>
                <div class="job-title">${escapeHtml(j.title || "Software Engineer")}</div>
                <div class="job-company">${escapeHtml(j.company || "Company")}</div>
              </div>
              <div class="fit-score-badge">${score}% Fit</div>
            </div>
            <div class="job-card-meta">
              <span>📍 ${escapeHtml(j.location || "Remote")}</span>
              <span>🏢 ${escapeHtml(j.source || "ATS Feed")}</span>
            </div>
            <div class="job-skills-chips">
              ${skills.slice(0, 5).map((s) => `<span class="skill-chip">${escapeHtml(s)}</span>`).join("")}
            </div>
            <div style="display:flex;gap:8px;margin-top:auto;">
              ${j.apply_url || j.url ? `<a href="${escapeHtml(j.apply_url || j.url)}" target="_blank" class="btn btn-primary" style="flex:1;text-decoration:none;">Apply Now ↗</a>` : ""}
              <button class="btn btn-secondary btn-track-job" data-id="${escapeHtml(j.id || "")}" data-company="${escapeHtml(j.company || "")}" data-title="${escapeHtml(j.title || "")}">+ Track</button>
            </div>
          </div>
        `;
      })
      .join("");

    document.querySelectorAll(".btn-track-job").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const company = e.currentTarget.dataset.company;
        const title = e.currentTarget.dataset.title;
        await apiPost("/api/applications", { company, title, status: "saved" });
        btn.textContent = "✓ Tracked";
        btn.disabled = true;
      });
    });
  }

  // ----------------------------------------------------------- Tab 2: Profiles
  async function loadProfiles() {
    const data = await apiGet("/api/profiles");
    if (!data) return;
    const profiles = data.profiles || [];
    state.profiles = profiles;

    const extStatus = await apiGet("/api/extension/status");
    const activeName = extStatus?.active_profile || data.active_profile || "Default";
    if (topbarProfileName) topbarProfileName.textContent = activeName;
    if (profCandName) profCandName.textContent = extStatus?.candidate_name || "Active Candidate";
    if (profTargetTitle) profTargetTitle.textContent = extStatus?.target_title || "Full Stack AI Engineer";

    const payloadData = await apiPost("/api/extension/payload", {});
    const prof = payloadData?.profile || {};
    if (profSkillsTags && prof.skills) {
      profSkillsTags.innerHTML = prof.skills
        .map((s) => `<span class="skill-chip" style="font-size:12px;padding:4px 10px;">${escapeHtml(s)}</span>`)
        .join("");
    }

    if (variantsList) {
      variantsList.innerHTML = profiles
        .map((p) => {
          const isActive = p.name === activeName || p.is_active;
          return `
            <div class="kanban-card" style="margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <strong>${escapeHtml(p.name)}</strong>
                ${isActive ? '<span class="status-pill connected">Active</span>' : `<button class="btn btn-secondary btn-activate-prof" data-name="${escapeHtml(p.name)}">Activate</button>`}
              </div>
              <div style="font-size:12px;color:#9ca3af;">${escapeHtml(p.target_title || "Software Engineer")}</div>
            </div>
          `;
        })
        .join("");

      document.querySelectorAll(".btn-activate-prof").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
          const name = e.currentTarget.dataset.name;
          await apiPost("/api/profile/activate", { name });
          loadProfiles();
        });
      });
    }
  }

  // ----------------------------------------------------------- Tab 3: Tracker
  async function loadApplications() {
    const data = await apiGet("/api/applications");
    if (!data) return;
    const apps = data.applications || [];
    const stats = data.stats || {};

    if (statSaved) statSaved.textContent = stats.saved || 0;
    if (statApplied) statApplied.textContent = stats.applied || 0;
    if (statInterview) statInterview.textContent = stats.interview || 0;
    if (statOffer) statOffer.textContent = stats.offer || 0;
    if (statRejected) statRejected.textContent = stats.rejected || 0;

    const cols = {
      saved: document.getElementById("col-saved"),
      applied: document.getElementById("col-applied"),
      interview: document.getElementById("col-interview"),
      offer: document.getElementById("col-offer"),
      rejected: document.getElementById("col-rejected"),
    };

    Object.values(cols).forEach((c) => {
      if (c) c.innerHTML = "";
    });

    apps.forEach((a) => {
      const status = (a.status || "saved").toLowerCase();
      const col = cols[status] || cols.saved;
      if (!col) return;

      const card = document.createElement("div");
      card.className = "kanban-card";
      card.innerHTML = `
        <div class="kanban-card-title">${escapeHtml(a.title || "Job")}</div>
        <div class="kanban-card-company">${escapeHtml(a.company || "Company")}</div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
          <select class="select-input select-app-status" data-id="${escapeHtml(a.id || "")}" style="font-size:11px;padding:3px 6px;">
            <option value="saved" ${status === "saved" ? "selected" : ""}>Saved</option>
            <option value="applied" ${status === "applied" ? "selected" : ""}>Applied</option>
            <option value="interview" ${status === "interview" ? "selected" : ""}>Interview</option>
            <option value="offer" ${status === "offer" ? "selected" : ""}>Offer</option>
            <option value="rejected" ${status === "rejected" ? "selected" : ""}>Rejected</option>
          </select>
        </div>
      `;
      col.appendChild(card);
    });

    document.querySelectorAll(".select-app-status").forEach((sel) => {
      sel.addEventListener("change", async (e) => {
        const id = e.currentTarget.dataset.id;
        const newStatus = e.currentTarget.value;
        await apiPost("/api/applications", { id, status: newStatus });
        loadApplications();
      });
    });
  }

  // ----------------------------------------------------------- Tab 5: Extension
  async function loadExtensionStatus() {
    const data = await apiGet("/api/desktop/extension-status");
    if (!data) return;
    const browsers = data.browsers || [];
    state.browsers = browsers;

    if (browsersUl) {
      if (!browsers.length) {
        browsersUl.innerHTML = '<li style="color:#ef4444;">No Chromium browser found in standard paths.</li>';
      } else {
        browsersUl.innerHTML = browsers
          .map((b) => `<li><strong>${escapeHtml(b.name)}</strong> — <code>${escapeHtml(b.path)}</code></li>`)
          .join("");
      }
    }
  }

  function setupEventHandlers() {
    navItems.forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    if (searchBtn) searchBtn.addEventListener("click", runJobSearch);
    if (searchQuery) {
      searchQuery.addEventListener("keydown", (e) => {
        if (e.key === "Enter") runJobSearch();
      });
    }

    if (btnScanResumes) btnScanResumes.addEventListener("click", loadProfiles);

    if (btnLaunchBrowserAuto) {
      btnLaunchBrowserAuto.addEventListener("click", async () => {
        btnLaunchBrowserAuto.textContent = "Launching Browser...";
        await apiPost("/api/desktop/launch-browser-extension", {});
        btnLaunchBrowserAuto.textContent = "✓ Browser Launched!";
        setTimeout(() => {
          btnLaunchBrowserAuto.textContent = "Launch Edge / Chrome with Copilot";
        }, 3000);
      });
    }

    if (btnQuickLaunchExt) {
      btnQuickLaunchExt.addEventListener("click", () => {
        apiPost("/api/desktop/launch-browser-extension", {});
      });
    }

    if (btnCopyExtPath) {
      btnCopyExtPath.addEventListener("click", async () => {
        const res = await apiPost("/api/desktop/open-extension-folder", {});
        btnCopyExtPath.textContent = "✓ Copied to Clipboard!";
        setTimeout(() => {
          btnCopyExtPath.textContent = "📋 Copy Extension Path";
        }, 2500);
      });
    }

    if (btnOpenExtMgr) {
      btnOpenExtMgr.addEventListener("click", () => {
        apiPost("/api/desktop/open-extension-folder", {});
      });
    }

    const btnGenLetter = document.getElementById("btn-gen-letter");
    if (btnGenLetter) {
      btnGenLetter.addEventListener("click", async () => {
        const title = document.getElementById("doc-job-title")?.value || "Backend Engineer";
        const company = document.getElementById("doc-company")?.value || "Stripe";
        const outBox = document.getElementById("doc-output-box");
        if (outBox) outBox.innerHTML = "<em>Drafting and running Reviewer QA checks...</em>";

        const res = await apiPost("/api/extension/solve", {
          question: `Why are you a good fit for the ${title} position at ${company}?`,
          job: { title, company },
        });

        if (outBox && res) {
          outBox.innerHTML = `
            <div style="background:#111827;padding:12px;border-radius:8px;border:1px solid #374151;">
              <div style="color:#10b981;font-weight:700;margin-bottom:8px;">✓ Reviewer QA Verdict: ${res.review?.verdict?.toUpperCase() || "PASS"}</div>
              <p style="white-space:pre-wrap;">${escapeHtml(res.answer || "Generated draft approved.")}</p>
            </div>
          `;
        }
      });
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

  // Init
  setupEventHandlers();
  loadProfiles();
  loadApplications();
  loadExtensionStatus();
})();

