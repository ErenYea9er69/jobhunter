/**
 * JobHunter — Client-Side Application Controller
 * Handles Multi-Source Aggregation, Deduplication, Match Scoring, Resume Refiner (Diffs),
 * Gap Reports, Cover Letters, Application Kanban, and Watchlist.
 */

(function () {
  'use strict';

  const AppState = {
    profile: null,
    jobs: [],
    applications: [],
    watchlist: [],
    activeJob: null,
    activeRefinement: null,
    activeAtsAudit: null,
    diffDecisions: {}, // diffId -> 'accepted' | 'rejected' | 'pending'
    coverTone: 'direct',
    searchInProgress: false
  };

  // Helper for API calls
  async function api(url, options = {}) {
    options.headers = options.headers || {};
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }
    const tokenMeta = document.querySelector('meta[name="jh-token"]');
    options.headers['X-JH-Token'] = tokenMeta ? tokenMeta.content : '';
    const res = await fetch(url, options);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'Network error' }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  }

  // Toast Notification System
  function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
        ${type === 'success' ? '<path d="M20 6L9 17l-5-5"></path>' : '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>'}
      </svg>
      <span>${escapeHtml(message)}</span>
    `;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.25s ease';
      setTimeout(() => toast.remove(), 250);
    }, 3200);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Navigation Controller
  function initNavigation() {
    const navButtons = document.querySelectorAll('.nav-btn');
    navButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        switchTab(targetTab);
      });
    });

    const userPill = document.getElementById('userProfilePill');
    if (userPill) {
      userPill.addEventListener('click', () => switchTab('tab-profile'));
    }
  }

  function switchTab(tabId) {
    document.querySelectorAll('.nav-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
    });
    document.querySelectorAll('.tab-pane').forEach(p => {
      p.classList.toggle('active', p.id === tabId);
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Tab-specific refreshes
    if (tabId === 'tab-tracker') {
      renderKanbanBoard();
    } else if (tabId === 'tab-watchlist') {
      loadWatchlist();
    } else if (tabId === 'tab-digest') {
      loadDailyDigest();
    } else if (tabId === 'tab-ats-audit') {
      loadAtsForActiveJob();
    }
  }

  // -------------------------------------------------------------
  // Profile Controller (Master Resume Intake & Editor)
  // -------------------------------------------------------------

  async function loadProfile() {
    try {
      const data = await api('/api/profile');
      AppState.profile = data;
      renderProfileForm(data);
      updateUserPill(data);
    } catch (err) {
      console.error('Failed to load profile:', err);
    }
  }

  function updateUserPill(profile) {
    const nameEl = document.getElementById('pillName');
    const titleEl = document.getElementById('pillTitle');
    const avatarEl = document.getElementById('userAvatar');
    if (nameEl) nameEl.textContent = profile.name || 'Alex Rivera';
    if (titleEl) titleEl.textContent = `${profile.years_of_experience || 5} yrs • ${profile.work_mode || 'Remote'}`;
    if (avatarEl && profile.name) {
      const initials = profile.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
      avatarEl.textContent = initials;
    }
  }

  function renderProfileForm(p) {
    if (!p) return;
    document.getElementById('profName').value = p.name || '';
    document.getElementById('profTitle').value = p.target_title || '';
    document.getElementById('profExp').value = p.years_of_experience || 5;
    document.getElementById('profWorkMode').value = p.work_mode || 'Remote';
    document.getElementById('profEmail').value = p.email || '';
    document.getElementById('profPhone').value = p.phone || '';
    document.getElementById('profLocation').value = p.location || '';
    document.getElementById('profLinkedin').value = p.linkedin || '';
    document.getElementById('profGithub').value = p.github || '';
    document.getElementById('profSummary').value = p.summary || '';

    renderSkillsTags(p.skills || []);
    renderExperienceList(p.experience || []);
    renderEducationList(p.education || []);
  }

  function renderSkillsTags(skills) {
    const container = document.getElementById('profileSkillsTags');
    if (!container) return;
    container.innerHTML = skills.map((s, idx) => `
      <span class="skill-tag" data-index="${idx}">
        ${escapeHtml(s)}
        <span class="tag-remove" onclick="window.JobHunterApp.removeSkill(${idx})">&times;</span>
      </span>
    `).join('');
  }

  function renderExperienceList(expList) {
    const container = document.getElementById('profileExperienceList');
    if (!container) return;
    container.innerHTML = expList.map((exp, idx) => `
      <div class="experience-entry-box" data-exp-index="${idx}">
        <div class="entry-header">
          <h4>${escapeHtml(exp.role || 'Role')} &mdash; ${escapeHtml(exp.company || 'Company')}</h4>
          <button type="button" class="btn btn-sm btn-outline-danger" onclick="window.JobHunterApp.removeExperienceEntry(${idx})">Remove Role</button>
        </div>
        <div class="form-grid-2">
          <div class="form-field">
            <label>Company</label>
            <input type="text" class="exp-company" value="${escapeHtml(exp.company || '')}">
          </div>
          <div class="form-field">
            <label>Title / Role</label>
            <input type="text" class="exp-role" value="${escapeHtml(exp.role || '')}">
          </div>
          <div class="form-field">
            <label>Dates</label>
            <input type="text" class="exp-dates" value="${escapeHtml(exp.start_date || '')} - ${escapeHtml(exp.end_date || '')}">
          </div>
          <div class="form-field">
            <label>Location</label>
            <input type="text" class="exp-location" value="${escapeHtml(exp.location || '')}">
          </div>
        </div>
        <div class="bullets-editor-list">
          <label style="font-size: 11.5px; font-weight: 600; color: #94a3b8; text-transform: uppercase;">Experience Bullets (Targeted by AI Refiner)</label>
          ${(exp.bullets || []).map((b, bIdx) => `
            <div class="bullet-edit-row">
              <textarea rows="2" class="exp-bullet-text">${escapeHtml(b)}</textarea>
              <button type="button" class="btn btn-sm btn-outline-danger" onclick="window.JobHunterApp.removeBullet(${idx}, ${bIdx})">&times;</button>
            </div>
          `).join('')}
          <button type="button" class="btn btn-sm btn-secondary" style="align-self: flex-start; margin-top: 6px;" onclick="window.JobHunterApp.addBullet(${idx})">+ Add Bullet</button>
        </div>
      </div>
    `).join('');
  }

  function renderEducationList(eduList) {
    const container = document.getElementById('profileEducationList');
    if (!container) return;
    container.innerHTML = eduList.map((edu, idx) => `
      <div class="experience-entry-box" style="padding: 14px;" data-edu-index="${idx}">
        <div class="form-grid-2">
          <div class="form-field">
            <label>Institution</label>
            <input type="text" class="edu-inst" value="${escapeHtml(edu.institution || '')}">
          </div>
          <div class="form-field">
            <label>Degree</label>
            <input type="text" class="edu-degree" value="${escapeHtml(edu.degree || '')}">
          </div>
        </div>
      </div>
    `).join('');
  }

  async function saveMasterProfile() {
    const updated = {
      name: document.getElementById('profName').value.trim(),
      target_title: document.getElementById('profTitle').value.trim(),
      years_of_experience: parseInt(document.getElementById('profExp').value) || 5,
      work_mode: document.getElementById('profWorkMode').value,
      email: document.getElementById('profEmail').value.trim(),
      phone: document.getElementById('profPhone').value.trim(),
      location: document.getElementById('profLocation').value.trim(),
      linkedin: document.getElementById('profLinkedin').value.trim(),
      github: document.getElementById('profGithub').value.trim(),
      summary: document.getElementById('profSummary').value.trim(),
      skills: AppState.profile.skills || [],
      experience: collectExperienceFromForm(),
      education: collectEducationFromForm(),
      preferred_locations: ["Remote", "Worldwide"]
    };

    try {
      await api('/api/profile', { method: 'POST', body: updated });
      AppState.profile = updated;
      updateUserPill(updated);
      showToast('Master resume profile saved locally to SQLite!');
      // Re-run search match scoring with updated profile
      handleSearch();
    } catch (err) {
      showToast('Failed to save profile: ' + err.message, 'error');
    }
  }

  function collectExperienceFromForm() {
    const boxes = document.querySelectorAll('.experience-entry-box[data-exp-index]');
    const list = [];
    boxes.forEach(box => {
      const company = box.querySelector('.exp-company')?.value || '';
      const role = box.querySelector('.exp-role')?.value || '';
      const dates = (box.querySelector('.exp-dates')?.value || '').split('-');
      const location = box.querySelector('.exp-location')?.value || 'Remote';
      const bulletTextareas = box.querySelectorAll('.exp-bullet-text');
      const bullets = Array.from(bulletTextareas).map(ta => ta.value.trim()).filter(b => b.length > 0);
      list.push({
        company,
        role,
        location,
        start_date: dates[0]?.trim() || '2021',
        end_date: dates[1]?.trim() || 'Present',
        bullets
      });
    });
    return list;
  }

  function collectEducationFromForm() {
    const boxes = document.querySelectorAll('.experience-entry-box[data-edu-index]');
    const list = [];
    boxes.forEach(box => {
      const institution = box.querySelector('.edu-inst')?.value || '';
      const degree = box.querySelector('.edu-degree')?.value || '';
      list.push({ institution, degree, graduation_year: '2020' });
    });
    return list;
  }

  // -------------------------------------------------------------
  // Resume File Upload & Parsing Intake
  // -------------------------------------------------------------

  async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) { showToast('File is larger than 8 MB.', 'error'); return; }
    showToast(`Reading ${file.name}...`);
    const isBinary = /\.(pdf|docx|doc)$/i.test(file.name);
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        let body;
        if (isBinary) {
          const bytes = new Uint8Array(e.target.result);
          let bin = '';
          for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
          body = { filename: file.name, content_base64: btoa(bin) };
        } else {
          body = { text: e.target.result };
        }
        const res = await api('/api/parse-resume', { method: 'POST', body });
        if (res.profile) {
          AppState.profile = res.profile;
          renderProfileForm(res.profile);
          updateUserPill(res.profile);
          const miss = (res.parse_report && res.parse_report.needs_review) || [];
          showToast(miss.length ? `Parsed ${file.name}. Please fill in: ${miss.join(', ')}.` : `Parsed ${file.name}. Review the fields, then save.`);
        }
      } catch (err) {
        showToast('Could not read the file: ' + err.message, 'error');
      }
    };
    if (isBinary) reader.readAsArrayBuffer(file); else reader.readAsText(file);
  }

  async function handlePasteParse() {
    const text = document.getElementById('rawResumePaste').value.trim();
    if (!text) {
      showToast('Please paste resume text first.', 'error');
      return;
    }
    showToast('Extracting structured profile from pasted text...');
    try {
      const res = await api('/api/parse-resume', {
        method: 'POST',
        body: { text }
      });
      if (res.profile) {
        AppState.profile = res.profile;
        renderProfileForm(res.profile);
        updateUserPill(res.profile);
        showToast('Extracted profile! Review and save your master resume.');
      }
    } catch (err) {
      showToast('Error parsing text: ' + err.message, 'error');
    }
  }

  // -------------------------------------------------------------
  // Unified Multi-Source Search & Deduplication Engine
  // -------------------------------------------------------------

  async function handleSearch() {
    const query = document.getElementById('searchQuery').value.trim();
    const location = document.getElementById('searchLocation').value.trim();
    const workMode = document.getElementById('searchWorkMode').value;
    const minScore = document.getElementById('searchMinScore').value;

    const grid = document.getElementById('jobResultsGrid');
    grid.innerHTML = `
      <div class="empty-state-card" id="searchLoadingState">
        <div class="spinner"></div>
        <p>Querying all enabled sources at the same time. Slow sources stop at the deadline and the rest still show.</p>
      </div>
    `;

    try {
      const params = new URLSearchParams({
        q: query,
        location: location,
        work_mode: workMode,
        min_score: minScore
      });

      const data = await api(`/api/search?${params.toString()}`);
      AppState.jobs = data.jobs || [];
      renderSourceStatus(data);

      renderSearchResults(AppState.jobs);
      populateJobDropdowns(AppState.jobs);

      // If active job not set, default to highest score
      if (AppState.jobs.length > 0 && !AppState.activeJob) {
        setActiveJob(AppState.jobs[0]);
      }
    } catch (err) {
      grid.innerHTML = `<div class="empty-state-card text-danger">Search failed: ${escapeHtml(err.message)}</div>`;
    }
  }

  function renderSourceStatus(data) {
    const el = document.getElementById('sourceStatus');
    if (!el) return;
    const srcs = data.sources || [];
    const ok = srcs.filter(s => s.state === 'ok' || s.state === 'cached').map(s => `${s.source} (${s.count})`);
    const bad = srcs.filter(s => ['failed', 'timeout', 'paused', 'stale'].includes(s.state)).map(s => `${s.source}: ${s.state}${s.stale ? ' (showing older results)' : ''}`);
    const off = srcs.filter(s => s.state === 'disabled').map(s => s.source);
    let html = `Searched in ${(data.elapsed_ms / 1000).toFixed(1)}s. ` + (ok.length ? `Answered: ${escapeHtml(ok.join(', '))}. ` : '');
    if (bad.length) html += `<span style="color:#f59e0b">Problems: ${escapeHtml(bad.join('; '))}.</span> `;
    if (off.length) html += `Off: ${escapeHtml(off.join(', '))}. `;
    if (data.profile_empty) html += '<strong>Upload your resume first so jobs get a real match score.</strong>';
    el.innerHTML = html;
  }

  function renderSearchResults(jobs) {
    const grid = document.getElementById('jobResultsGrid');
    const countEl = document.getElementById('resultsCount');
    if (countEl) countEl.textContent = jobs.length;

    if (!jobs || jobs.length === 0) {
      grid.innerHTML = `
        <div class="empty-state-card">
          <h3>No matching jobs found</h3>
          <p>Try lowering the min match score or searching for broader terms (e.g. "Engineer", "Full Stack", "Python").</p>
        </div>
      `;
      return;
    }

    grid.innerHTML = jobs.map((j, idx) => {
      const score = j.score || 70;
      let scoreClass = 'score-low';
      let fitCardClass = 'fit-low';
      if (score >= 85) { scoreClass = 'score-exceptional'; fitCardClass = 'fit-exceptional'; }
      else if (score >= 70) { scoreClass = 'score-strong'; fitCardClass = 'fit-strong'; }
      else if (score >= 50) { scoreClass = 'score-moderate'; fitCardClass = 'fit-moderate'; }

      const companyInitial = (j.company || 'C').charAt(0).toUpperCase();

      // Multi-source deduplication presentation
      const sourcesList = j.sources || [{ source: j.source, url: j.url }];
      const isMultiSource = sourcesList.length > 1;

      return `
        <article class="job-card ${fitCardClass}" id="job-card-${idx}">
          <div class="job-card-main">
            <div class="job-header-line">
              <div class="company-avatar">${companyInitial}</div>
              <div class="job-titles-group">
                <h3>${escapeHtml(j.title)}</h3>
                <div class="company-name-row">
                  <span class="company-name">${escapeHtml(j.company)}</span>
                  <span class="source-chip source-active" style="padding: 1px 7px; font-size: 10px;">${escapeHtml(j.source_tier || 'Tier 1')}</span>
                </div>
              </div>
            </div>

            <div class="job-metadata-chips">
              <span class="meta-chip">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>
                ${escapeHtml(j.location || 'Remote')}
              </span>
              <span class="meta-chip">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>
                ${escapeHtml(j.work_mode || 'Remote')}
              </span>
              ${j.salary ? `<span class="meta-chip salary-chip">${escapeHtml(j.salary)}</span>` : ''}
            </div>

            <p class="job-desc-snippet">${escapeHtml(j.description)}</p>

            <!-- Match Score Rationale Note -->
            <div class="match-rationale-box">
              <strong>Match Analysis:</strong> ${escapeHtml(j.rationale || 'Good skill alignment.')}
            </div>

            <!-- Cross-Source Deduplication & Direct Application Links -->
            <div class="dedup-sources-cluster">
              ${isMultiSource ? `<span class="dedup-badge">Consolidated from ${sourcesList.length} Sources:</span>` : '<span class="dedup-badge">Direct Source:</span>'}
              ${sourcesList.map(s => {
                const isATS = s.source.includes('Greenhouse') || s.source.includes('Ashby') || s.source.includes('Lever') || s.source.includes('SmartRecruiters');
                return `
                  <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" class="source-apply-link ${isATS ? 'primary-ats' : ''}" title="Apply directly on original posting">
                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                    ${escapeHtml(s.source)} ${isATS ? '(Direct ATS)' : ''}
                  </a>
                `;
              }).join('')}
            </div>

            <!-- Source Credit / Attribution compliance -->
            <div class="source-credit-text">
              Source Attribution: ${escapeHtml(j.source_credit || j.source)} &bull; Privacy preserved
            </div>
          </div>

          <!-- Score & Action Buttons -->
          <div class="job-card-actions">
            <div class="score-widget">
              <div class="score-badge-circle ${scoreClass}">
                ${score}<span class="score-pct">%</span>
              </div>
              <span class="score-label">Fit Match</span>
            </div>

            <div class="action-buttons-stack">
              <button class="btn btn-autohunt btn-sm" onclick="window.JobHunterApp.execute1ClickAutoHunt(${idx})" title="1-Click Auto-Hunt: Tailor resume, generate cover letter & prep, and log to pipeline">
                ⚡ Auto-Hunt
              </button>
              <button class="btn btn-primary btn-sm" onclick="window.JobHunterApp.triggerTailorJob(${idx})">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                Tailor Resume
              </button>
              <button class="btn btn-secondary btn-sm" onclick="window.JobHunterApp.triggerAtsJob(${idx})">
                ATS Audit
              </button>
              <button class="btn btn-secondary btn-sm" onclick="window.JobHunterApp.triggerGapJob(${idx})">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path></svg>
                Gap Report
              </button>
              <button class="btn btn-secondary btn-sm" onclick="window.JobHunterApp.saveJobToTracker(${idx})">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                Save
              </button>
            </div>
          </div>
        </article>
      `;
    }).join('');
  }

  function populateJobDropdowns(jobs) {
    const dropdownIds = ['refinerJobSelector', 'gapJobSelector', 'coverJobSelector', 'prepJobSelector', 'atsJobSelector'];
    dropdownIds.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.innerHTML = jobs.map((j, idx) => `
        <option value="${idx}">${escapeHtml(j.company)} — ${escapeHtml(j.title)} (${j.score || 70}%)</option>
      `).join('');
    });
  }

  function setActiveJob(job) {
    AppState.activeJob = job;
    updateRefinerHeader(job);
    loadRefinementForActiveJob();
    loadGapForActiveJob();
    loadCoverForActiveJob();
    loadPrepForActiveJob();
    loadAtsForActiveJob();
  }

  // -------------------------------------------------------------
  // Resume Refiner (Side-by-Side Diff & Granular Controls)
  // -------------------------------------------------------------

  function updateRefinerHeader(job) {
    if (!job) return;
    document.getElementById('refinerJobTitle').textContent = job.title;
    document.getElementById('refinerCompany').textContent = job.company;
    document.getElementById('refinerLocation').textContent = job.location || 'Remote';
    const scoreEl = document.getElementById('refinerMatchScore');
    scoreEl.textContent = `${job.score || 75}% Match`;
  }

  async function loadRefinementForActiveJob() {
    if (!AppState.activeJob) return;
    try {
      const data = await api('/api/refine', {
        method: 'POST',
        body: { job: AppState.activeJob }
      });
      AppState.activeRefinement = data;
      AppState.diffDecisions = {};
      (data.diff_items || []).forEach(d => {
        AppState.diffDecisions[d.id] = 'pending';
      });
      renderDiffStream(data.diff_items || []);
      renderAtsPreview();
      updateDiffSummaryStats();
    } catch (err) {
      console.error('Refine error:', err);
    }
  }

  function renderDiffStream(diffItems) {
    const container = document.getElementById('diffCardsStream');
    if (!container) return;

    container.innerHTML = diffItems.map(d => {
      const decision = AppState.diffDecisions[d.id] || 'pending';
      const isAccepted = decision === 'accepted';
      const isRejected = decision === 'rejected';

      let cardStatusClass = '';
      if (isAccepted) cardStatusClass = 'accepted';
      if (isRejected) cardStatusClass = 'rejected';

      let badgeClass = 'badge-modified';
      if (d.status === 'reordered') badgeClass = 'badge-reordered';
      if (d.status === 'unchanged') badgeClass = 'badge-unchanged';

      return `
        <div class="diff-card ${cardStatusClass}" id="card-${d.id}">
          <div class="diff-card-header">
            <div class="diff-label-group">
              <span class="diff-section-tag">${escapeHtml(d.section)}</span>
              <span class="diff-title">${escapeHtml(d.label)}</span>
            </div>
            <span class="diff-status-badge ${badgeClass}">${escapeHtml(d.status.toUpperCase())}</span>
          </div>

          <div class="diff-columns-grid">
            <div class="diff-col diff-col-orig">
              <div class="diff-col-title">Master Resume (Original)</div>
              <div>${escapeHtml(d.original)}</div>
            </div>
            <div class="diff-col diff-col-prop">
              <div class="diff-col-title">Tailored Proposal for ${escapeHtml(AppState.activeJob.company)}</div>
              <div id="text-${d.id}" contenteditable="true" onblur="window.JobHunterApp.handleManualDiffEdit('${d.id}', this.innerText)">${escapeHtml(d.proposed)}</div>
            </div>
          </div>

          <div class="diff-rationale">
            &bull; Tailoring Rationale: ${escapeHtml(d.rationale)}
          </div>

          <div class="diff-actions-row">
            <button class="btn btn-sm ${isAccepted ? 'btn-primary' : 'btn-outline-success'}" onclick="window.JobHunterApp.setDiffDecision('${d.id}', 'accepted')">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
              ${isAccepted ? 'Accepted' : 'Accept Change'}
            </button>
            <button class="btn btn-sm ${isRejected ? 'btn-danger' : 'btn-outline-danger'}" onclick="window.JobHunterApp.setDiffDecision('${d.id}', 'rejected')">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              ${isRejected ? 'Rejected (Reverted)' : 'Reject / Keep Original'}
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  function setDiffDecision(diffId, decision) {
    AppState.diffDecisions[diffId] = decision;
    const card = document.getElementById(`card-${diffId}`);
    if (card) {
      card.classList.toggle('accepted', decision === 'accepted');
      card.classList.toggle('rejected', decision === 'rejected');
    }
    updateDiffSummaryStats();
    renderAtsPreview();
    showToast(`Change ${decision === 'accepted' ? 'accepted' : 'rejected'}`);
  }

  function acceptAllDiffs() {
    if (!AppState.activeRefinement) return;
    (AppState.activeRefinement.diff_items || []).forEach(d => {
      AppState.diffDecisions[d.id] = 'accepted';
      const card = document.getElementById(`card-${d.id}`);
      if (card) {
        card.classList.add('accepted');
        card.classList.remove('rejected');
      }
    });
    updateDiffSummaryStats();
    renderAtsPreview();
    showToast('Accepted all tailored optimizations!');
  }

  function rejectAllDiffs() {
    if (!AppState.activeRefinement) return;
    (AppState.activeRefinement.diff_items || []).forEach(d => {
      AppState.diffDecisions[d.id] = 'rejected';
      const card = document.getElementById(`card-${d.id}`);
      if (card) {
        card.classList.remove('accepted');
        card.classList.add('rejected');
      }
    });
    updateDiffSummaryStats();
    renderAtsPreview();
    showToast('Reverted all to original master text.');
  }

  function handleManualDiffEdit(diffId, newText) {
    if (!AppState.activeRefinement) return;
    const item = AppState.activeRefinement.diff_items.find(d => d.id === diffId);
    if (item) {
      item.proposed = newText;
      AppState.diffDecisions[diffId] = 'accepted';
      const card = document.getElementById(`card-${diffId}`);
      if (card) card.classList.add('accepted');
      renderAtsPreview();
    }
  }

  function updateDiffSummaryStats() {
    const statsEl = document.getElementById('diffSummaryStats');
    if (!statsEl || !AppState.activeRefinement) return;
    const total = (AppState.activeRefinement.diff_items || []).length;
    let accepted = 0;
    let rejected = 0;
    Object.values(AppState.diffDecisions).forEach(val => {
      if (val === 'accepted') accepted++;
      if (val === 'rejected') rejected++;
    });
    statsEl.innerHTML = `${total} Proposed Optimizations &bull; <strong style="color: #34d399">${accepted} Accepted</strong> &bull; <strong style="color: #f87171">${rejected} Rejected</strong>`;
  }

  function getEffectiveTailoredResume() {
    if (!AppState.profile) return {};
    const effective = JSON.parse(JSON.stringify(AppState.profile));

    if (!AppState.activeRefinement) return effective;

    // Apply summary if accepted
    if (AppState.diffDecisions['diff_summary'] === 'accepted') {
      effective.summary = AppState.activeRefinement.tailored_summary;
    }

    // Apply skills if accepted
    if (AppState.diffDecisions['diff_skills'] === 'accepted') {
      effective.skills = AppState.activeRefinement.tailored_skills;
    }

    // Apply experience bullets
    effective.experience.forEach((exp, expIdx) => {
      exp.bullets.forEach((bullet, bIdx) => {
        const diffId = `diff_exp_${expIdx}_${bIdx}`;
        if (AppState.diffDecisions[diffId] === 'accepted') {
          const item = AppState.activeRefinement.diff_items.find(d => d.id === diffId);
          if (item) {
            exp.bullets[bIdx] = item.proposed;
          }
        }
      });
    });

    return effective;
  }

  function renderAtsPreview() {
    const container = document.getElementById('atsPaperPreview');
    if (!container) return;
    const res = getEffectiveTailoredResume();

    container.innerHTML = `
      <h2>${escapeHtml(res.name || 'Candidate Name')}</h2>
      <div class="ats-paper-contact">
        ${escapeHtml(res.email || '')} &bull; ${escapeHtml(res.phone || '')} &bull; ${escapeHtml(res.location || '')}<br>
        ${escapeHtml(res.linkedin || '')} &bull; ${escapeHtml(res.github || '')}
      </div>

      <div class="ats-paper-section-title">Professional Summary</div>
      <p>${escapeHtml(res.summary || '')}</p>

      <div class="ats-paper-section-title">Core Competencies &amp; Technical Skills</div>
      <p>${(res.skills || []).join(' &bull; ')}</p>

      <div class="ats-paper-section-title">Professional Experience</div>
      ${(res.experience || []).map(exp => `
        <div style="margin-bottom: 14px;">
          <table style="width: 100%;">
            <tr>
              <td><strong>${escapeHtml(exp.role)}</strong> &mdash; ${escapeHtml(exp.company)}</td>
              <td style="text-align: right; color: #555;">${escapeHtml(exp.start_date)} &ndash; ${escapeHtml(exp.end_date)}</td>
            </tr>
          </table>
          <div style="font-size: 11.5px; color: #666; font-style: italic;">${escapeHtml(exp.location)}</div>
          <ul>
            ${(exp.bullets || []).map(b => `<li>${escapeHtml(b)}</li>`).join('')}
          </ul>
        </div>
      `).join('')}

      <div class="ats-paper-section-title">Education</div>
      ${(res.education || []).map(edu => `
        <p><strong>${escapeHtml(edu.degree)}</strong> &mdash; ${escapeHtml(edu.institution)} (${escapeHtml(edu.graduation_year)})</p>
      `).join('')}
    `;
  }

  async function exportResume(format) {
    const resume = getEffectiveTailoredResume();
    try {
      const res = await api('/api/export', {
        method: 'POST',
        body: { format, resume }
      });

      if (format === 'txt') {
        navigator.clipboard.writeText(res.content);
        showToast('Plain text ATS resume copied to clipboard!');
      } else {
        let blob;
        if (res.content_base64) {
          const bin = atob(res.content_base64);
          const arr = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
          blob = new Blob([arr], { type: res.mime });
        } else {
          blob = new Blob([res.content], { type: 'text/html' });
        }
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = res.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast(`Downloaded ${res.filename}!`);
      }
    } catch (err) {
      showToast('Export failed: ' + err.message, 'error');
    }
  }

  function printAtsPreview() {
    window.print();
  }

  // -------------------------------------------------------------
  // Gap Report Controller
  // -------------------------------------------------------------

  async function loadGapForActiveJob() {
    if (!AppState.activeJob) return;
    try {
      const report = await api('/api/gap-report', {
        method: 'POST',
        body: { job: AppState.activeJob }
      });
      renderGapReport(report);
    } catch (err) {
      console.error('Gap report error:', err);
    }
  }

  function renderGapReport(rep) {
    const matchedCount = (rep.matched_skills || []).length;
    const addCount = (rep.add_if_true || []).length;
    const realCount = (rep.real_gaps || []).length;

    document.getElementById('gapMatchedCount').textContent = matchedCount;
    document.getElementById('gapMatchedList').textContent = (rep.matched_skills || []).slice(0, 6).join(', ') || 'Core Stack';
    document.getElementById('gapAddIfTrueCount').textContent = addCount;
    document.getElementById('gapRealCount').textContent = realCount;

    const addContainer = document.getElementById('gapAddIfTrueList');
    if (addContainer) {
      if (addCount === 0) {
        addContainer.innerHTML = '<p class="field-help">No minor adjacent tool gaps detected! Your toolchain matches well.</p>';
      } else {
        addContainer.innerHTML = rep.add_if_true.map(item => `
          <div class="gap-item-card">
            <div class="gap-item-main">
              <span class="gap-item-name">${escapeHtml(item.skill)}</span>
              <span class="gap-item-advice">${escapeHtml(item.advice)}</span>
            </div>
            <button class="btn btn-outline-success btn-sm" onclick="window.JobHunterApp.addSkillToProfile('${escapeHtml(item.skill)}')">
              + Add to Profile
            </button>
          </div>
        `).join('');
      }
    }

    const realContainer = document.getElementById('gapRealList');
    if (realContainer) {
      if (realCount === 0) {
        realContainer.innerHTML = '<p class="field-help">Zero major architectural gaps! You meet all structural requirements.</p>';
      } else {
        realContainer.innerHTML = rep.real_gaps.map(item => `
          <div class="gap-item-card" style="border-left: 3px solid var(--accent-amber);">
            <div class="gap-item-main">
              <span class="gap-item-name text-amber">${escapeHtml(item.skill)}</span>
              <span class="gap-item-advice">${escapeHtml(item.advice)}</span>
            </div>
            <span class="badge badge-amber" style="font-size: 10px; font-weight: 700;">PREPARE TALKING POINT</span>
          </div>
        `).join('');
      }
    }
  }

  async function addSkillToProfile(skillName) {
    if (!AppState.profile.skills.includes(skillName)) {
      AppState.profile.skills.push(skillName);
      await saveMasterProfile();
      showToast(`Added "${skillName}" to your master profile!`);
      loadGapForActiveJob();
      loadRefinementForActiveJob();
    }
  }

  // -------------------------------------------------------------
  // Cover Letter Generator Controller
  // -------------------------------------------------------------

  async function loadCoverForActiveJob() {
    if (!AppState.activeJob) return;
    try {
      const data = await api('/api/cover-letter', {
        method: 'POST',
        body: { job: AppState.activeJob }
      });
      const textarea = document.getElementById('coverLetterTextarea');
      if (textarea) textarea.value = data.cover_letter || '';
    } catch (err) {
      console.error('Cover letter error:', err);
    }
  }

  function setCoverTone(tone) {
    AppState.coverTone = tone;
    document.querySelectorAll('.btn-tone').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-tone') === tone);
    });
    loadCoverForActiveJob();
    showToast(`Tone updated to ${tone}`);
  }

  function copyCoverLetter() {
    const text = document.getElementById('coverLetterTextarea').value;
    navigator.clipboard.writeText(text);
    showToast('Cover letter copied to clipboard!');
  }

  async function saveCoverLetterToTracker() {
    if (!AppState.activeJob) return;
    const text = document.getElementById('coverLetterTextarea').value;
    const payload = {
      job_id: AppState.activeJob.id,
      company: AppState.activeJob.company,
      title: AppState.activeJob.title,
      location: AppState.activeJob.location,
      salary: AppState.activeJob.salary,
      status: 'applied',
      notes: 'Applied with tailored cover letter and resume.',
      sources: AppState.activeJob.sources || [{ source: AppState.activeJob.source, url: AppState.activeJob.url }],
      job_data: AppState.activeJob,
      cover_letter: text
    };
    try {
      await api('/api/applications', { method: 'POST', body: payload });
      showToast('Saved to Application Pipeline (Applied column)!');
      loadApplications();
    } catch (err) {
      showToast('Error saving application: ' + err.message, 'error');
    }
  }

  // -------------------------------------------------------------
  // Application Tracker (Kanban Pipeline) Controller
  // -------------------------------------------------------------

  async function loadApplications() {
    try {
      const data = await api('/api/applications');
      AppState.applications = data.applications || [];
      renderKanbanBoard();
      updateTrackerCount(AppState.applications.length);
    } catch (err) {
      console.error('Error loading applications:', err);
    }
  }

  function updateTrackerCount(count) {
    const el = document.getElementById('navTrackerCount');
    if (el) el.textContent = count;
  }

  function renderKanbanBoard() {
    const statuses = ['saved', 'applied', 'interview', 'offer', 'rejected'];
    const counts = { saved: 0, applied: 0, interview: 0, offer: 0, rejected: 0 };

    statuses.forEach(status => {
      const dropzone = document.getElementById(`cards${status.charAt(0).toUpperCase() + status.slice(1)}`);
      if (!dropzone) return;

      const filtered = AppState.applications.filter(a => (a.status || 'saved') === status);
      counts[status] = filtered.length;

      dropzone.innerHTML = filtered.map(app => {
        // Calculate follow-up status
        let followUpBadge = '';
        if (app.follow_up_date) {
          const followDate = new Date(app.follow_up_date);
          const today = new Date();
          const diffDays = Math.ceil((followDate - today) / (1000 * 60 * 60 * 24));
          const isOverdue = diffDays < 0;
          const isToday = diffDays === 0;

          followUpBadge = `
            <div class="follow-up-badge ${isOverdue || isToday ? 'overdue' : ''}">
              <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
              ${isOverdue ? 'Overdue!' : isToday ? 'Follow up today!' : `Follow-up in ${diffDays}d`}
            </div>
          `;
        }

        return `
          <div class="kanban-card" draggable="true" ondragstart="event.dataTransfer.setData('text/plain', '${app.id}')" id="kanban-card-${app.id}">
            <div class="kanban-card-title">${escapeHtml(app.title)}</div>
            <div class="kanban-card-company">${escapeHtml(app.company)}</div>
            <div class="kanban-card-meta">
              <span>${escapeHtml(app.location || 'Remote')}</span>
              <span>${escapeHtml(app.salary || '')}</span>
            </div>
            ${followUpBadge}
            ${app.notes ? `<div style="font-size: 11px; color: #94a3b8; font-style: italic; margin-bottom: 6px;">"${escapeHtml(app.notes)}"</div>` : ''}
            <div class="kanban-card-actions">
              <select class="stage-select" onchange="window.JobHunterApp.moveApplicationStage('${app.id}', this.value)">
                <option value="saved" ${app.status === 'saved' ? 'selected' : ''}>Saved</option>
                <option value="applied" ${app.status === 'applied' ? 'selected' : ''}>Applied</option>
                <option value="interview" ${app.status === 'interview' ? 'selected' : ''}>Interview</option>
                <option value="offer" ${app.status === 'offer' ? 'selected' : ''}>Offer</option>
                <option value="rejected" ${app.status === 'rejected' ? 'selected' : ''}>Archived</option>
              </select>
              <button class="btn btn-sm btn-outline-danger" style="padding: 2px 6px;" onclick="window.JobHunterApp.deleteApplication('${app.id}')">&times;</button>
            </div>
          </div>
        `;
      }).join('');

      // Update column header count
      const countEl = document.getElementById(`count${status.charAt(0).toUpperCase() + status.slice(1)}`);
      if (countEl) countEl.textContent = counts[status];
    });
  }

  async function moveApplicationStage(appId, newStatus) {
    const app = AppState.applications.find(a => a.id === appId);
    if (!app) return;
    app.status = newStatus;
    try {
      await api('/api/applications', { method: 'POST', body: app });
      renderKanbanBoard();
      showToast(`Moved to ${newStatus}`);
    } catch (err) {
      showToast('Error moving stage: ' + err.message, 'error');
    }
  }

  function handleCardDrop(event, targetStatus) {
    event.preventDefault();
    const appId = event.dataTransfer.getData('text/plain');
    if (appId) {
      moveApplicationStage(appId, targetStatus);
    }
  }

  async function deleteApplication(appId) {
    if (!confirm('Remove this application from the pipeline?')) return;
    try {
      await api(`/api/applications/${appId}`, { method: 'DELETE' });
      AppState.applications = AppState.applications.filter(a => a.id !== appId);
      renderKanbanBoard();
      updateTrackerCount(AppState.applications.length);
      showToast('Application deleted.');
    } catch (err) {
      showToast('Error deleting application: ' + err.message, 'error');
    }
  }

  async function saveJobToTracker(jobIdx) {
    const job = AppState.jobs[jobIdx];
    if (!job) return;

    const payload = {
      job_id: job.id,
      company: job.company,
      title: job.title,
      location: job.location,
      salary: job.salary,
      status: 'saved',
      notes: 'Bookmarked from multi-source search.',
      follow_up_date: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      sources: job.sources || [{ source: job.source, url: job.url }],
      job_data: job
    };

    try {
      await api('/api/applications', { method: 'POST', body: payload });
      showToast(`Saved "${job.title}" to tracker!`);
      loadApplications();
    } catch (err) {
      showToast('Error saving to tracker: ' + err.message, 'error');
    }
  }

  function openAddCustomAppModal() {
    document.getElementById('appModalTitle').textContent = 'Add Opportunity to Pipeline';
    document.getElementById('modalCompany').value = '';
    document.getElementById('modalTitle').value = '';
    document.getElementById('modalLocation').value = 'Remote';
    document.getElementById('modalSalary').value = '';
    document.getElementById('modalFollowUp').value = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    document.getElementById('modalNotes').value = '';
    document.getElementById('appModal').style.display = 'flex';
  }

  async function saveModalApplication() {
    const payload = {
      company: document.getElementById('modalCompany').value.trim(),
      title: document.getElementById('modalTitle').value.trim(),
      location: document.getElementById('modalLocation').value.trim(),
      salary: document.getElementById('modalSalary').value.trim(),
      status: document.getElementById('modalStatus').value,
      follow_up_date: document.getElementById('modalFollowUp').value,
      notes: document.getElementById('modalNotes').value.trim()
    };
    try {
      await api('/api/applications', { method: 'POST', body: payload });
      closeModal('appModal');
      showToast('Added to application tracker!');
      loadApplications();
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    }
  }

  // -------------------------------------------------------------
  // Watchlist Controller (Greenhouse, Lever, Ashby Career Portals)
  // -------------------------------------------------------------

  async function loadWatchlist() {
    try {
      const data = await api('/api/watchlist');
      AppState.watchlist = data.watchlist || [];
      renderWatchlistGrid();
    } catch (err) {
      console.error('Watchlist error:', err);
    }
  }

  function renderWatchlistGrid() {
    const container = document.getElementById('watchlistGrid');
    if (!container) return;

    if (AppState.watchlist.length === 0) {
      container.innerHTML = '<div class="empty-state-card">No companies watched yet. Add target employers to monitor their ATS boards.</div>';
      return;
    }

    container.innerHTML = AppState.watchlist.map(w => `
      <div class="card watchlist-card">
        <div>
          <div class="wl-company-header">
            <span class="wl-company-name">${escapeHtml(w.company_name)}</span>
            <span class="wl-badge badge-cyan">${escapeHtml(w.board_type.toUpperCase())}</span>
          </div>
          <p style="font-size: 13px; color: #94a3b8; margin-bottom: 8px;">Target Role: <strong>${escapeHtml(w.target_role || 'Engineering')}</strong></p>
          <div style="font-size: 12px; color: #34d399; font-weight: 600;">
            &bull; Active Board Monitor: 1+ matching positions
          </div>
        </div>
        <div style="display: flex; gap: 8px; margin-top: 16px;">
          <button class="btn btn-primary btn-sm" onclick="window.JobHunterApp.searchCompanyRoles('${escapeHtml(w.company_name)}')">View Roles</button>
          <button class="btn btn-outline-danger btn-sm" onclick="window.JobHunterApp.deleteWatchlistItem('${w.id}')">Unwatch</button>
        </div>
      </div>
    `).join('');
  }

  function openAddWatchlistModal() {
    document.getElementById('wlCompanyName').value = '';
    document.getElementById('wlTargetRole').value = 'Software Engineer';
    document.getElementById('watchlistModal').style.display = 'flex';
  }

  async function saveModalWatchlist() {
    const company_name = document.getElementById('wlCompanyName').value.trim();
    const board_type = document.getElementById('wlAtsType').value;
    const target_role = document.getElementById('wlTargetRole').value.trim();

    try {
      await api('/api/watchlist', {
        method: 'POST',
        body: { company_name, board_type, target_role }
      });
      closeModal('watchlistModal');
      showToast(`Added ${company_name} to career board watchlist!`);
      loadWatchlist();
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    }
  }

  async function deleteWatchlistItem(id) {
    try {
      await api(`/api/watchlist/${id}`, { method: 'DELETE' });
      showToast('Removed from watchlist.');
      loadWatchlist();
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    }
  }

  function searchCompanyRoles(companyName) {
    document.getElementById('searchQuery').value = companyName;
    switchTab('tab-search');
    handleSearch();
  }

  // -------------------------------------------------------------
  // Daily Digest Simulator Controller
  // -------------------------------------------------------------

  async function loadDailyDigest(threshold = 75) {
    try {
      const data = await api('/api/digest');
      renderDailyDigest(data);
    } catch (err) {
      console.error('Digest error:', err);
    }
  }

  function renderDailyDigest(digest) {
    document.getElementById('digestGreetingName').textContent = digest.recipient_name || 'Alex';
    document.getElementById('digestDate').textContent = digest.date || 'Today, 8:00 AM';
    document.getElementById('digestThresholdBadge').textContent = `${digest.min_score || 75}%+`;
    document.getElementById('digestIntroText').textContent = digest.summary || 'Here are today’s top matching opportunities:';

    const container = document.getElementById('digestJobsStream');
    if (!container) return;

    const jobs = digest.digest_jobs || [];
    if (jobs.length === 0) {
      container.innerHTML = '<p class="empty-state-card">No jobs met the minimum score threshold today. Lower threshold to see more.</p>';
      return;
    }

    container.innerHTML = jobs.map((j, idx) => `
      <div class="digest-job-row">
        <div class="digest-job-info">
          <h4>${escapeHtml(j.title)} &mdash; ${escapeHtml(j.company)}</h4>
          <div class="digest-job-sub">
            ${escapeHtml(j.location || 'Remote')} &bull; ${escapeHtml(j.salary || 'Competitive')} &bull; Matched on: ${(j.matched_skills || []).slice(0, 3).join(', ')}
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <span class="score-badge-circle score-exceptional" style="font-size: 14px; padding: 4px 10px;">${j.score || 85}%</span>
          <button class="btn btn-primary btn-sm" onclick="window.JobHunterApp.triggerTailorFromDigest('${escapeHtml(j.company)}')">Tailor &amp; Apply</button>
        </div>
      </div>
    `).join('');
  }

  function reloadDigest(threshold) {
    loadDailyDigest(threshold);
  }

  // -------------------------------------------------------------
  // Interview Prep Studio Controller
  // -------------------------------------------------------------

  async function loadPrepForActiveJob() {
    if (!AppState.activeJob) return;
    try {
      const data = await api('/api/interview-prep', {
        method: 'POST',
        body: { job: AppState.activeJob }
      });
      renderInterviewPrep(data);
    } catch (err) {
      console.error('Prep error:', err);
    }
  }

  function renderInterviewPrep(prep) {
    const container = document.getElementById('prepSectionsGrid');
    if (!container) return;

    container.innerHTML = `
      <!-- Behavioral Questions -->
      <div class="card prep-category-card">
        <h3 class="card-title text-cyan">Behavioral &amp; Situational Questions</h3>
        <p class="field-help">Tailored to ${escapeHtml(prep.company)} and structured around the STAR framework (Situation, Task, Action, Result).</p>
        ${(prep.behavioral_questions || []).map(q => `
          <div class="prep-question-item">
            <div class="prep-q-title">${escapeHtml(q.question)}</div>
            <div class="prep-q-tip"><strong>STAR Strategy:</strong> ${escapeHtml(q.tip)}</div>
          </div>
        `).join('')}
      </div>

      <!-- Technical Deep Dives -->
      <div class="card prep-category-card">
        <h3 class="card-title text-success">Technical Architecture &amp; Stack Deep Dives</h3>
        <p class="field-help">Targeted challenges based on the posting's core infrastructure.</p>
        ${(prep.technical_deep_dives || []).map(t => `
          <div class="prep-question-item">
            <div class="prep-q-title"><strong>${escapeHtml(t.topic)}:</strong> ${escapeHtml(t.question)}</div>
            <div class="prep-q-tip"><strong>Key Talking Points:</strong> ${escapeHtml(t.talking_point)}</div>
          </div>
        `).join('')}
      </div>

      <!-- Overcoming Gaps Honestly -->
      <div class="card prep-category-card">
        <h3 class="card-title text-amber">Addressing Identified Skill Gaps Honestly</h3>
        <p class="field-help">Never fake experience. Use this framing to demonstrate rapid ramp-up capability.</p>
        ${(prep.gap_talking_points || []).map(g => `
          <div class="prep-question-item">
            <div class="prep-q-title">Gap: ${escapeHtml(g.skill)}</div>
            <div class="prep-q-tip">${escapeHtml(g.recommended_response)}</div>
          </div>
        `).join('')}
      </div>

      <!-- Questions for the Interviewer -->
      <div class="card prep-category-card">
        <h3 class="card-title">High-Signal Questions to Ask the Hiring Team</h3>
        <p class="field-help">Shows domain expertise and genuine enthusiasm.</p>
        ${(prep.questions_to_ask_interviewer || []).map(q => `
          <div class="prep-question-item">
            <div class="prep-q-title">${escapeHtml(q)}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // -------------------------------------------------------------
  // ATS Score & Parseability Studio Controller (10X Parseability)
  // -------------------------------------------------------------

  async function loadAtsForActiveJob() {
    if (!AppState.activeJob) return;
    try {
      const effectiveResume = getEffectiveTailoredResume();
      const data = await api('/api/ats-audit', {
        method: 'POST',
        body: {
          job: AppState.activeJob,
          resume: effectiveResume
        }
      });
      AppState.activeAtsAudit = data;
      renderAtsAudit(data);
    } catch (err) {
      console.error('ATS audit error:', err);
    }
  }

  function renderAtsAudit(audit) {
    if (!audit) return;

    // Grade and Points
    const letterEl = document.getElementById('atsGradeLetter');
    const pointsEl = document.getElementById('atsScorePoints');
    const circleEl = document.getElementById('atsGradeCircle');
    const navBadgeEl = document.getElementById('navAtsScoreBadge');

    if (letterEl) letterEl.textContent = audit.grade || 'A';
    if (pointsEl) pointsEl.textContent = `${audit.ats_score || 0} / 100`;
    if (navBadgeEl) navBadgeEl.textContent = `${audit.ats_score}% ${audit.grade}`;

    if (circleEl) {
      circleEl.className = 'ats-grade-circle';
      const gradeFirst = (audit.grade || 'A').charAt(0).toLowerCase();
      circleEl.classList.add(`grade-${gradeFirst}`);
    }

    // Status Badge & Narrative
    const statusBadge = document.getElementById('atsStatusBadge');
    const titleEl = document.getElementById('atsSummaryTitle');
    const descEl = document.getElementById('atsSummaryDesc');

    if (audit.ats_score >= 90) {
      if (statusBadge) {
        statusBadge.className = 'ats-status-badge badge-emerald';
        statusBadge.textContent = 'OPTIMAL ATS PARSEABILITY';
      }
      if (titleEl) titleEl.textContent = 'Ready for Enterprise ATS Systems';
      if (descEl) descEl.textContent = 'Your resume achieves tier-1 parseability across Greenhouse, Lever, and Workday with zero structural blockers and optimal keyword frequency.';
    } else if (audit.ats_score >= 75) {
      if (statusBadge) {
        statusBadge.className = 'ats-status-badge badge-amber-glow';
        statusBadge.textContent = 'COMPATIBLE WITH ROOM FOR OPTIMIZATION';
      }
      if (titleEl) titleEl.textContent = 'Passable ATS Formatting & Density';
      if (descEl) descEl.textContent = 'Your resume will pass initial parsing filters, but adding quantified impact metrics and top role keywords will boost recruiter match rankings.';
    } else {
      if (statusBadge) {
        statusBadge.className = 'ats-status-badge badge-rose-glow';
        statusBadge.textContent = 'ATS GAPS DETECTED';
      }
      if (titleEl) titleEl.textContent = 'Action Required: Key Requirements Missing';
      if (descEl) descEl.textContent = 'Several required job keywords or structural elements are missing. Click 1-Click Auto-Tailor to instantly optimize.';
    }

    // Pillars Breakdown
    const b = audit.breakdown || {};
    const pkEl = document.getElementById('atsPillarKeywords');
    const pmEl = document.getElementById('atsPillarMetrics');
    const pmSub = document.getElementById('atsPillarMetricsSub');
    const pvEl = document.getElementById('atsPillarVerbs');
    const psEl = document.getElementById('atsPillarSections');

    if (pkEl) pkEl.textContent = `${b.keyword_score || 0} / 35 pts`;
    if (pmEl) pmEl.textContent = `${b.metrics_score || 0} / 25 pts`;
    if (pmSub) pmSub.textContent = `${b.quantified_bullets_pct || 0}% metrics density`;
    if (pvEl) pvEl.textContent = `${b.verbs_score || 0} / 20 pts`;
    if (psEl) psEl.textContent = `${b.structure_score || 0} / 20 pts`;

    // Keyword Density Saturation Table
    const kwListContainer = document.getElementById('atsKeywordDensityList');
    if (kwListContainer) {
      const topKw = audit.top_keywords_density || [];
      if (topKw.length === 0) {
        kwListContainer.innerHTML = '<div style="color: #94a3b8; font-size: 13px;">No required keywords extracted.</div>';
      } else {
        kwListContainer.innerHTML = topKw.map(kw => {
          let badgeHtml = '';
          if (kw.status === 'optimal') {
            badgeHtml = `<span class="kw-badge optimal">Optimal (${kw.count}x)</span>`;
          } else if (kw.status === 'single') {
            badgeHtml = `<span class="kw-badge single">Present (${kw.count}x)</span>`;
          } else {
            badgeHtml = `<span class="kw-badge missing">Missing (0x)</span>`;
          }
          return `
            <div class="keyword-row">
              <div class="kw-left">
                <span class="kw-name">${escapeHtml(kw.keyword)}</span>
              </div>
              <div class="kw-right">
                <span class="kw-count">${kw.count} occurrences</span>
                ${badgeHtml}
              </div>
            </div>
          `;
        }).join('');
      }
    }

    // Checklist Stream
    const checklistContainer = document.getElementById('atsChecklistStream');
    if (checklistContainer) {
      const items = audit.checklist || [];
      checklistContainer.innerHTML = items.map(c => `
        <div class="checklist-item ${c.passed ? 'check-pass' : 'check-fail'}">
          <div class="check-icon-box">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5">
              ${c.passed ? '<polyline points="20 6 9 17 4 12"></polyline>' : '<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>'}
            </svg>
          </div>
          <div class="check-text-group">
            <div class="check-title">${escapeHtml(c.rule)}</div>
            <div class="check-desc">${escapeHtml(c.details)}</div>
          </div>
        </div>
      `).join('');
    }

    // Recommendations
    const recsList = document.getElementById('atsRecommendationsList');
    if (recsList) {
      const recs = audit.recommendations || [];
      if (recs.length === 0) {
        recsList.innerHTML = '<li>Zero ATS blockers detected! Your resume is ready for direct submission.</li>';
      } else {
        recsList.innerHTML = recs.map(r => `<li>${escapeHtml(r)}</li>`).join('');
      }
    }
  }

  // 1-Click Auto-Tailor Action
  async function execute1ClickAutoTailor() {
    if (!AppState.activeJob || !AppState.profile) {
      showToast('Select a target job first.', 'error');
      return;
    }

    showToast('⚡ Running 1-Click Auto-Tailor optimization...');
    try {
      const res = await api('/api/auto-tailor', {
        method: 'POST',
        body: {
          job: AppState.activeJob,
          profile: AppState.profile
        }
      });

      // Update refinement state
      AppState.activeRefinement = res.refinement;
      AppState.diffDecisions = {};
      (res.refinement.diff_items || []).forEach(d => {
        AppState.diffDecisions[d.id] = 'accepted';
      });

      renderDiffStream(res.refinement.diff_items || []);
      renderAtsPreview();
      updateDiffSummaryStats();

      // Render ATS audit response
      if (res.ats_audit) {
        AppState.activeAtsAudit = res.ats_audit;
        renderAtsAudit(res.ats_audit);
      }

      showToast(`⚡ Auto-Tailored to ${res.ats_audit.ats_score}% (Grade ${res.ats_audit.grade}) in ${res.speed_ms || 35}ms!`);
    } catch (err) {
      showToast('Auto-tailor error: ' + err.message, 'error');
    }
  }

  // 1-Click Auto-Hunt Action
  async function execute1ClickAutoHunt(jobIdx) {
    const job = (typeof jobIdx === 'number') ? AppState.jobs[jobIdx] : AppState.activeJob;
    if (!job) {
      showToast('No job selected for auto-hunt', 'error');
      return;
    }

    showToast(`Preparing a package for ${job.company}...`);
    try {
      const res = await api('/api/auto-hunt', {
        method: 'POST',
        body: {
          job: job,
          profile: AppState.profile
        }
      });

      showToast(`Package ready: tailored resume, cover letter, and prep notes saved to your pipeline as Saved. Mark it Applied after you submit.`);
      await loadApplications();
      
      // Transition smoothly to Kanban pipeline
      setTimeout(() => {
        switchTab('tab-tracker');
      }, 700);
    } catch (err) {
      showToast('Auto-hunt error: ' + err.message, 'error');
    }
  }

  // -------------------------------------------------------------
  // Data Privacy & Purge Controller
  // -------------------------------------------------------------

  async function purgeAllData() {
    if (!confirm('Are you absolutely sure you want to permanently delete all your data? This deletes your profile, applications, watchlist, settings, and cached searches, then compacts the database file.')) {
      return;
    }
    try {
      await api('/api/purge-all-data', { method: 'DELETE' });
      showToast('All data has been permanently wiped.');
      location.reload();
    } catch (err) {
      showToast('Error purging data: ' + err.message, 'error');
    }
  }

  function closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.style.display = 'none';
  }

  // -------------------------------------------------------------
  // Quick Actions & Triggers
  // -------------------------------------------------------------

  function triggerTailorJob(idx) {
    const job = AppState.jobs[idx];
    if (job) {
      setActiveJob(job);
      document.getElementById('refinerJobSelector').value = idx;
      switchTab('tab-refiner');
    }
  }

  function triggerGapJob(idx) {
    const job = AppState.jobs[idx];
    if (job) {
      setActiveJob(job);
      document.getElementById('gapJobSelector').value = idx;
      switchTab('tab-gap');
    }
  }

  function triggerAtsJob(idx) {
    const job = AppState.jobs[idx];
    if (job) {
      setActiveJob(job);
      const sel = document.getElementById('atsJobSelector');
      if (sel) sel.value = idx;
      switchTab('tab-ats-audit');
    }
  }

  function loadJobForAts(idx) {
    const job = AppState.jobs[parseInt(idx)];
    if (job) setActiveJob(job);
  }

  function triggerTailorFromDigest(companyName) {
    const match = AppState.jobs.find(j => j.company.toLowerCase().includes(companyName.toLowerCase()));
    if (match) {
      setActiveJob(match);
      switchTab('tab-refiner');
    } else {
      searchCompanyRoles(companyName);
    }
  }

  function loadJobForRefiner(idx) {
    const job = AppState.jobs[parseInt(idx)];
    if (job) setActiveJob(job);
  }

  function loadJobForGap(idx) {
    const job = AppState.jobs[parseInt(idx)];
    if (job) setActiveJob(job);
  }

  function loadJobForCover(idx) {
    const job = AppState.jobs[parseInt(idx)];
    if (job) setActiveJob(job);
  }

  function loadJobForPrep(idx) {
    const job = AppState.jobs[parseInt(idx)];
    if (job) setActiveJob(job);
  }

  function setSearchKeyword(kw) {
    document.getElementById('searchQuery').value = kw;
    handleSearch();
  }

  function sortResults(criterion) {
    if (criterion === 'score_desc') {
      AppState.jobs.sort((a, b) => (b.score || 0) - (a.score || 0));
    } else if (criterion === 'date_desc') {
      AppState.jobs.sort((a, b) => (b.posted_at || '').localeCompare(a.posted_at || ''));
    } else if (criterion === 'company_asc') {
      AppState.jobs.sort((a, b) => (a.company || '').localeCompare(b.company || ''));
    }
    renderSearchResults(AppState.jobs);
  }

  function promptAddSkill() {
    const s = prompt('Enter technical skill or tool:');
    if (s && s.trim()) {
      if (!AppState.profile.skills.includes(s.trim())) {
        AppState.profile.skills.push(s.trim());
        renderSkillsTags(AppState.profile.skills);
      }
    }
  }

  function removeSkill(idx) {
    AppState.profile.skills.splice(idx, 1);
    renderSkillsTags(AppState.profile.skills);
  }

  function addExperienceEntry() {
    AppState.profile.experience = AppState.profile.experience || [];
    AppState.profile.experience.unshift({
      company: 'New Company',
      role: 'Software Engineer',
      location: 'Remote',
      start_date: '2023',
      end_date: 'Present',
      bullets: ['Built reliable backend APIs and web features.']
    });
    renderExperienceList(AppState.profile.experience);
  }

  function removeExperienceEntry(idx) {
    AppState.profile.experience.splice(idx, 1);
    renderExperienceList(AppState.profile.experience);
  }

  function addBullet(expIdx) {
    if (AppState.profile.experience[expIdx]) {
      AppState.profile.experience[expIdx].bullets.push('Designed and scaled production features with measurable impact.');
      renderExperienceList(AppState.profile.experience);
    }
  }

  function removeBullet(expIdx, bIdx) {
    if (AppState.profile.experience[expIdx]) {
      AppState.profile.experience[expIdx].bullets.splice(bIdx, 1);
      renderExperienceList(AppState.profile.experience);
    }
  }

  function addEducationEntry() {
    AppState.profile.education = AppState.profile.education || [];
    AppState.profile.education.push({
      institution: 'University Name',
      degree: 'B.S. in Computer Science',
      graduation_year: '2021'
    });
    renderEducationList(AppState.profile.education);
  }

  function loadSampleProfile() {
    location.reload();
  }

  // -------------------------------------------------------------
  // Application Bootstrap
  // -------------------------------------------------------------

  async function init() {
    initNavigation();
    await loadProfile();
    await loadApplications();
    await handleSearch();
  }

  // Expose global controller
  window.JobHunterApp = {
    handleSearch,
    saveMasterProfile,
    handleFileUpload,
    handlePasteParse,
    loadSampleProfile,
    promptAddSkill,
    removeSkill,
    addSkillToProfile,
    addExperienceEntry,
    removeExperienceEntry,
    addBullet,
    removeBullet,
    addEducationEntry,
    triggerTailorJob,
    triggerGapJob,
    triggerAtsJob,
    saveJobToTracker,
    loadJobForRefiner,
    loadJobForGap,
    loadJobForCover,
    loadJobForPrep,
    loadJobForAts,
    loadAtsForActiveJob,
    execute1ClickAutoTailor,
    execute1ClickAutoHunt,
    setSearchKeyword,
    sortResults,
    setDiffDecision,
    acceptAllDiffs,
    rejectAllDiffs,
    handleManualDiffEdit,
    exportResume,
    printAtsPreview,
    setCoverTone,
    copyCoverLetter,
    saveCoverLetterToTracker,
    moveApplicationStage,
    handleCardDrop,
    deleteApplication,
    openAddCustomAppModal,
    saveModalApplication,
    openAddWatchlistModal,
    saveModalWatchlist,
    deleteWatchlistItem,
    searchCompanyRoles,
    reloadDigest,
    triggerTailorFromDigest,
    purgeAllData,
    closeModal
  };

  document.addEventListener('DOMContentLoaded', init);
})();
