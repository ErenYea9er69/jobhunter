/**
 * JobHunter interface controller.
 * Talks to the same /api endpoints as before. Only the interface changed.
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------ setup
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const STAGES = [
    { key: 'saved', label: 'Saved' },
    { key: 'applied', label: 'Applied' },
    { key: 'interview', label: 'Interviewing' },
    { key: 'offer', label: 'Offer' },
    { key: 'rejected', label: 'Archived' }
  ];
  const TONES = [
    { key: 'direct', label: 'Direct' },
    { key: 'conversational', label: 'Conversational' },
    { key: 'systems', label: 'Systems' }
  ];
  const VIEWS = ['jobs', 'job', 'applications', 'resume', 'companies', 'digest', 'privacy'];
  const TITLES = {
    jobs: 'Jobs', job: 'Job workspace', applications: 'Applications', resume: 'Resume',
    companies: 'Companies', digest: 'Morning digest', privacy: 'Sources and privacy'
  };
  const DEFAULT_IDEAS = ['Full Stack', 'Backend Python', 'TypeScript React', 'DevOps Cloud'];
  const isNarrow = () => window.matchMedia('(max-width: 960px)').matches;

  // Recognized Big Tech & prominent AI companies that users can choose to show or hide
  const FAMOUS_COMPANY_TOKENS = new Set([
    'openai', 'anthropic', 'grok', 'xai', 'perplexity', 'cohere',
    'mistral', 'midjourney', 'cursor', 'poolside',
    'meta', 'facebook', 'google', 'alphabet', 'apple', 'microsoft',
    'amazon', 'netflix',
    'vercel', 'stripe', 'gitlab', 'github', 'figma', 'docker', 'supabase',
    'uber', 'airbnb', 'coinbase', 'shopify', 'spotify', 'databricks',
    'snowflake', 'cloudflare', 'palantir', 'nvidia', 'bytedance', 'tiktok',
    'salesforce', 'atlassian', 'adobe', 'twitter', 'tesla', 'spacex', 'neuralink'
  ]);

  const FAMOUS_COMPANY_PHRASES = [
    'open ai', 'meta platforms', 'x.ai', 'scale ai', 'hugging face',
    'amazon web services', 'deepmind'
  ];

  function isFamousCompany(companyName) {
    if (!companyName) return false;
    const name = String(companyName).toLowerCase().trim();
    if (FAMOUS_COMPANY_PHRASES.some(phrase => name.includes(phrase))) return true;
    const cleaned = name.replace(/\b(inc|llc|corp|ltd|co|corporation|technologies|systems|labs|group)\b\.?/gi, '');
    const tokens = cleaned.match(/[a-z0-9]+/g) || [];
    return tokens.some(t => FAMOUS_COMPANY_TOKENS.has(t));
  }

  function isFamousJob(job) {
    if (!job) return false;
    if (typeof job.is_famous === 'boolean') return job.is_famous;
    return isFamousCompany(job.company);
  }

  const S = {
    view: 'jobs',
    quickFilter: 'all',
    famousFilter: (function() { try { return localStorage.getItem('jh-famous-filter') || 'all'; } catch (e) { return 'all'; } })(),
    filters: {
      keyword: '',
      workMode: 'Any',
      minScore: 0,
      famousMode: (function() { try { return localStorage.getItem('jh-famous-filter') || 'all'; } catch (e) { return 'all'; } })(),
      country: 'all',
      excludedCountries: new Set(),
      seniority: 'all',
      salaryTier: '0',
      freshnessDays: 0,
      directAtsOnly: false,
      hideApplied: false,
      savedOnly: false,
      selectedSkills: new Set()
    },
    drawerOpen: false,
    profile: null,
    profileEmpty: true,
    dirty: false,
    jobs: [],
    jobsRanked: [],
    searchMeta: null,
    searchSeq: 0,
    searchStale: false,
    searchHasRun: false,
    lastSearchTime: null,
    workMode: 'Any',
    selectedKey: null,
    applications: [],
    watchlist: [],
    watchResults: {},
    ws: { job: null, key: '', tab: 'strategy', from: 'jobs', refinement: null, decisions: {}, ats: null, atsFresh: false,
          strategy: null, gaps: null, cover: {}, prep: null, tone: 'direct', showUnchanged: false, seq: 0 }
  };

  function syncFamousUi() {
    const sel = $('#searchFamousSelect');
    if (sel && sel.value !== S.famousFilter) sel.value = S.famousFilter;
    const famSeg = $('#famousSeg');
    if (famSeg) {
      $$('button[data-famous]', famSeg).forEach(b => {
        b.setAttribute('aria-pressed', String(b.dataset.famous === S.famousFilter));
      });
    }
  }

  // Auto-reload schedule
  let autoReloadIntervalId = null;
  function getAutoReloadMinutes() {
    try {
      const v = localStorage.getItem('jh-auto-reload');
      if (v === null) return 300; // default 5 hours
      return parseInt(v, 10);
    } catch (e) { return 300; }
  }
  function setAutoReloadMinutes(mins) {
    try {
      if (mins > 0) localStorage.setItem('jh-auto-reload', String(mins));
      else localStorage.setItem('jh-auto-reload', '0');
    } catch (e) { /* ignore */ }
    scheduleAutoReload(mins);
  }
  function scheduleAutoReload(mins) {
    if (autoReloadIntervalId) { clearInterval(autoReloadIntervalId); autoReloadIntervalId = null; }
    if (mins > 0) {
      autoReloadIntervalId = setInterval(() => {
        if (S.view === 'jobs' || S.searchHasRun) {
          toast('Auto-refreshing job listings and updating database cache...');
          runSearch({ forceRefresh: true });
        }
      }, mins * 60 * 1000);
    }
  }
  function formatTimeSince(ts) {
    if (!ts) return '';
    const diff = Math.round((Date.now() - ts) / 1000);
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return new Date(ts).toLocaleDateString();
  }

  // ---------------------------------------------------------------- helpers
  const ico = (name, cls = '') => `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

  function esc(v) {
    if (v === null || v === undefined) return '';
    return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  function cleanTitle(t) {
    if (!t) return '';
    return String(t).replace(/\s*—\s*/g, ' - ').replace(/\s*–\s*/g, ' - ');
  }

  async function api(url, options = {}) {
    options.headers = options.headers || {};
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }
    const meta = document.querySelector('meta[name="jh-token"]');
    options.headers['X-JH-Token'] = meta ? meta.content : '';
    const res = await fetch(url, options);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'Network error' }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  }

  function toast(message, type = 'ok') {
    const box = $('#toastContainer');
    if (!box) return;
    const el = document.createElement('div');
    el.className = `toast${type === 'error' ? ' toast-error' : ''}`;
    el.innerHTML = `${ico(type === 'error' ? 'alert' : 'check')}<span>${esc(message)}</span>`;
    box.appendChild(el);
    setTimeout(() => el.remove(), type === 'error' ? 6000 : 3500);
  }

  function confirmDialog(title, text, okLabel = 'Confirm') {
    return new Promise(resolve => {
      const d = $('#confirmDialog');
      $('#confirmTitle').textContent = title;
      $('#confirmText').textContent = text;
      $('#confirmOk').textContent = okLabel;
      const finish = value => {
        d.removeEventListener('click', onClick);
        d.removeEventListener('close', onClose);
        if (d.open) d.close();
        resolve(value);
      };
      const onClick = e => { const b = e.target.closest('[data-confirm]'); if (b) finish(b.dataset.confirm === 'ok'); };
      const onClose = () => finish(false);
      d.addEventListener('click', onClick);
      d.addEventListener('close', onClose);
      d.showModal();
    });
  }

  const jobKey = j => String(j.job_key || j.id || `${j.company}|${j.title}`);
  const sameJob = (a, b) => a && b && jobKey(a) === jobKey(b);

  function tierOf(score) {
    if (score >= 85) return { cls: 'tier-high', label: 'Excellent fit' };
    if (score >= 70) return { cls: 'tier-good', label: 'Strong fit' };
    if (score >= 50) return { cls: 'tier-fair', label: 'Fair fit' };
    return { cls: 'tier-low', label: 'Low fit' };
  }
  function ring(score, large = false) {
    const n = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
    return `<div class="score-ring ${large ? 'score-ring-lg ' : ''}${tierOf(n).cls}" style="--pct:${n}" role="img" aria-label="Match score ${n} percent"><span>${n}</span></div>`;
  }

  function timeAgo(iso) {
    const t = Date.parse(iso);
    if (isNaN(t)) return '';
    const s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 90) return 'just now';
    const m = s / 60; if (m < 60) return `${Math.round(m)} min ago`;
    const h = m / 60; if (h < 24) return `${Math.round(h)} hr ago`;
    const d = Math.round(h / 24);
    return d === 1 ? '1 day ago' : `${d} days ago`;
  }

  function daysUntil(dateStr) {
    const p = String(dateStr || '').split('-').map(Number);
    if (p.length < 3 || p.some(isNaN)) return null;
    const target = new Date(p[0], p[1] - 1, p[2]);
    const now = new Date(); now.setHours(0, 0, 0, 0);
    return Math.round((target - now) / 86400000);
  }

  const isoDay = offset => {
    const d = new Date(Date.now() + offset * 86400000);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };

  function jobSources(j) {
    return (j.sources && j.sources.length) ? j.sources : [{ source: j.source, url: j.url }];
  }
  function isDirect(s) {
    const name = String(s.source || '');
    return String(s.source_tier || '').includes('Direct company ATS') || /Greenhouse|Ashby|Lever|SmartRecruiters|Workable/i.test(name);
  }
  function bestApplyUrl(j) {
    const list = jobSources(j).filter(s => s.url);
    const direct = list.find(isDirect);
    return (direct || list[0] || {}).url || '';
  }

  const val = id => ($('#' + id) || {}).value || '';

  // ----------------------------------------------------------------- router
  function route() {
    const parts = location.hash.replace(/^#\/?/, '').split('/');
    let view = VIEWS.includes(parts[0]) ? parts[0] : 'jobs';
    if (view === 'job' && !S.ws.job) view = 'jobs';
    showView(view, parts[1] || '');
  }

  function go(view, sub = '') {
    const hash = `#/${view}${sub ? '/' + sub : ''}`;
    if (location.hash === hash) route(); else location.hash = hash;
  }

  function showView(view, sub) {
    S.view = view;
    $$('.view').forEach(v => { v.hidden = v.id !== `view-${view}`; });
    const navKey = view === 'job' ? (S.ws.from === 'applications' ? 'applications' : 'jobs') : view;
    $$('[data-nav]').forEach(a => {
      if (a.dataset.nav === navKey) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    document.title = `${TITLES[view] || 'JobHunter'} | JobHunter`;
    closeMenu();
    closeDetailSheet();
    window.scrollTo(0, 0);

    if (view === 'jobs') {
      if (S.searchHasRun && S.searchMeta) renderResults();
      else renderWelcomeState();
    }
    if (view === 'job') { S.ws.tab = ['strategy', 'resume', 'ats', 'gaps', 'cover', 'prep'].includes(sub) ? sub : 'strategy'; renderWsHeader(); renderWsTab(); }
    if (view === 'applications') loadApplications();
    if (view === 'companies') loadWatchlist();
    if (view === 'digest') loadDigest();
    if (view === 'privacy') { loadSourceHealth(); loadAiSettings(); }
  }

  // ------------------------------------------------------------ theme, menu
  function initTheme() {
    // Light mode (White Coffee / Warm Editorial Paper) is the primary default theme.
    // If the user explicitly saved 'dark', activate dark mode; otherwise always default to light.
    let saved = 'light';
    try { saved = localStorage.getItem('jh-theme') || 'light'; } catch (e) { /* ignore */ }
    setTheme(saved, false);

    const toggleBtn = $('#themeToggleBtn');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        setTheme(isDark ? 'light' : 'dark', true);
        closeMenu();
      });
    }
  }

  function setTheme(choice, persist) {
    const root = document.documentElement;
    const isDark = choice === 'dark';
    if (isDark) {
      root.setAttribute('data-theme', 'dark');
    } else {
      root.removeAttribute('data-theme');
    }
    const icon = $('#themeIcon use');
    if (icon) icon.setAttribute('href', isDark ? '#i-sun' : '#i-moon');
    const label = $('#themeLabel');
    if (label) label.textContent = isDark ? 'Light theme' : 'Dark theme';
    if (persist) {
      try {
        localStorage.setItem('jh-theme', isDark ? 'dark' : 'light');
      } catch (e) { /* ignore */ }
    }
  }

  function closeMenu() {
    const m = $('#moreMenu');
    if (m && !m.hidden) { m.hidden = true; $('#moreBtn').setAttribute('aria-expanded', 'false'); }
  }
  function toggleMenu() {
    const m = $('#moreMenu');
    m.hidden = !m.hidden;
    $('#moreBtn').setAttribute('aria-expanded', String(!m.hidden));
  }

  // ---------------------------------------------------------------- profile
  function normalizeProfile(p) {
    const q = Object.assign({}, p);
    delete q._is_empty; delete q._updated_at;
    q.skills = Array.isArray(q.skills) ? q.skills : [];
    q.experience = Array.isArray(q.experience) ? q.experience : [];
    q.education = Array.isArray(q.education) ? q.education : [];
    return q;
  }

  async function loadProfile() {
    try {
      const raw = await api('/api/profile');
      S.profileEmpty = !!raw._is_empty;
      S.profile = normalizeProfile(raw);
      if (['Remote', 'Hybrid', 'Onsite'].includes(S.profile.work_mode)) S.workMode = S.profile.work_mode;
      renderProfile();
      renderIdeas();
      syncWorkModeSeg();
    } catch (err) {
      S.profile = normalizeProfile({});
      renderProfile();
      toast('Could not load your profile: ' + err.message, 'error');
    }
    updateProfileLink();
    $('#onboardNotice').hidden = !S.profileEmpty;
  }

  function updateProfileLink() {
    const p = S.profile || {};
    const name = (p.name || '').trim();
    $('#pillName').textContent = name || 'Add your resume';
    $('#pillTitle').textContent = name ? [p.years_of_experience ? `${p.years_of_experience} yrs` : '', p.work_mode || ''].filter(Boolean).join(', ') : '';
    $('#userAvatar').textContent = name ? name.split(/\s+/).map(n => n[0]).join('').slice(0, 2).toUpperCase() : '?';
  }

  function renderProfile() {
    const p = S.profile || normalizeProfile({});
    const set = (id, v) => { const el = $('#' + id); if (el) el.value = v === undefined || v === null ? '' : v; };
    set('profName', p.name); set('profTitle', p.target_title);
    set('profExp', p.years_of_experience === undefined ? '' : p.years_of_experience);
    set('profWorkMode', p.work_mode || 'Remote');
    set('profEmail', p.email); set('profPhone', p.phone); set('profLocation', p.location);
    set('profLinkedin', p.linkedin); set('profGithub', p.github); set('profSummary', p.summary);
    renderSkills(); renderExperience(); renderEducation();

    const card = $('#intakeCard'), form = $('#profileForm');
    if (S.profileEmpty) {
      form.before(card); card.style.marginTop = '';
      $('#intakeTitle').textContent = 'Start with your resume';
      $('#intakeSub').textContent = 'Upload a PDF, Word, text, or Markdown file. The app reads it into the fields below.';
    } else {
      form.after(card); card.style.marginTop = '16px';
      $('#intakeTitle').textContent = 'Replace from a new file';
      $('#intakeSub').textContent = 'Upload a new resume to refill the fields above. Nothing changes until you save.';
    }
  }

  function renderSkills() {
    const skills = (S.profile && S.profile.skills) || [];
    $('#profileSkillsTags').innerHTML = skills.length
      ? skills.map((s, i) => `<span class="tag">${esc(s)}<button type="button" data-action="skill-remove" data-i="${i}" aria-label="Remove ${esc(s)}">${ico('x')}</button></span>`).join('')
      : '<span class="muted">No skills yet. Add the tools and languages you use.</span>';
  }

  function renderExperience() {
    const list = (S.profile && S.profile.experience) || [];
    $('#profileExperienceList').innerHTML = list.length ? list.map((x, i) => `
      <details class="entry" data-exp="${i}" ${S.openExp.has(i) ? 'open' : ''}>
        <summary><span>${esc(x.role || 'New role')}<small>${esc(x.company || '')}</small></span>${ico('chevron')}</summary>
        <div class="entry-body">
          <div class="form-grid">
            <div class="form-field"><label>Company</label><input type="text" class="exp-company" value="${esc(x.company)}"></div>
            <div class="form-field"><label>Title</label><input type="text" class="exp-role" value="${esc(x.role)}"></div>
            <div class="form-field"><label>Start</label><input type="text" class="exp-start" value="${esc(x.start_date)}" placeholder="2021-03"></div>
            <div class="form-field"><label>End</label><input type="text" class="exp-end" value="${esc(x.end_date)}" placeholder="Present"></div>
            <div class="form-field span-2"><label>Location</label><input type="text" class="exp-location" value="${esc(x.location)}"></div>
          </div>
          <div class="bullets">
            <label>Bullets</label>
            ${(x.bullets || []).map((b, bi) => `
              <div class="bullet-row">
                <textarea class="exp-bullet" rows="2" aria-label="Bullet ${bi + 1}">${esc(b)}</textarea>
                <button type="button" class="icon-btn" data-action="bullet-remove" data-i="${i}" data-b="${bi}" aria-label="Remove bullet">${ico('x')}</button>
              </div>`).join('')}
          </div>
          <div class="entry-actions">
            <button type="button" class="btn btn-secondary btn-sm" data-action="bullet-add" data-i="${i}">${ico('plus')}Add bullet</button>
            <button type="button" class="btn btn-quiet-danger btn-sm" data-action="exp-remove" data-i="${i}">Remove position</button>
          </div>
        </div>
      </details>`).join('') : '<p class="muted">No positions yet.</p>';
  }

  function renderEducation() {
    const list = (S.profile && S.profile.education) || [];
    $('#profileEducationList').innerHTML = list.length ? list.map((e, i) => `
      <div class="entry" data-edu="${i}">
        <div class="entry-body" style="padding-top:16px">
          <div class="form-grid">
            <div class="form-field"><label>School</label><input type="text" class="edu-inst" value="${esc(e.institution)}"></div>
            <div class="form-field"><label>Degree</label><input type="text" class="edu-degree" value="${esc(e.degree)}"></div>
            <div class="form-field"><label>Year</label><input type="text" class="edu-year" value="${esc(e.graduation_year)}"></div>
          </div>
          <div class="entry-actions"><button type="button" class="btn btn-quiet-danger btn-sm" data-action="edu-remove" data-i="${i}">Remove</button></div>
        </div>
      </div>`).join('') : '<p class="muted">No education yet.</p>';
  }

  function collectExperience() {
    const old = (S.profile && S.profile.experience) || [];
    return $$('#profileExperienceList [data-exp]').map(box => {
      const i = Number(box.dataset.exp);
      const end = $('.exp-end', box).value.trim();
      return Object.assign({}, old[i] || {}, {
        company: $('.exp-company', box).value.trim(),
        role: $('.exp-role', box).value.trim(),
        start_date: $('.exp-start', box).value.trim(),
        end_date: end,
        current: /^(present|current|now)$/i.test(end),
        location: $('.exp-location', box).value.trim(),
        bullets: $$('.exp-bullet', box).map(t => t.value.trim()).filter(Boolean)
      });
    });
  }
  function collectEducation() {
    const old = (S.profile && S.profile.education) || [];
    return $$('#profileEducationList [data-edu]').map(box => Object.assign({}, old[Number(box.dataset.edu)] || {}, {
      institution: $('.edu-inst', box).value.trim(),
      degree: $('.edu-degree', box).value.trim(),
      graduation_year: $('.edu-year', box).value.trim()
    }));
  }

  /** Read the form into one profile object. Keeps every field the form does not show. */
  function collectProfile() {
    const exp = parseInt(val('profExp'), 10);
    return Object.assign({}, S.profile, {
      name: val('profName').trim(),
      target_title: val('profTitle').trim(),
      years_of_experience: isNaN(exp) ? 0 : exp,
      work_mode: val('profWorkMode') || 'Remote',
      email: val('profEmail').trim(), phone: val('profPhone').trim(), location: val('profLocation').trim(),
      linkedin: val('profLinkedin').trim(), github: val('profGithub').trim(), summary: val('profSummary').trim(),
      skills: (S.profile && S.profile.skills) || [],
      experience: collectExperience(),
      education: collectEducation()
    });
  }
  /** Copy typed values into state so a list redraw never loses them. */
  function syncFormToState() {
    $$('#profileExperienceList [data-exp]').forEach(b => { const i = Number(b.dataset.exp); if (b.open) S.openExp.add(i); else S.openExp.delete(i); });
    S.profile = collectProfile();
  }

  function markDirty(text) {
    S.dirty = true;
    $('#saveBar').hidden = false;
    $('#saveBarText').textContent = text || 'You have unsaved changes.';
  }
  function clearDirty() { S.dirty = false; $('#saveBar').hidden = true; }

  async function saveProfile() {
    const p = collectProfile();
    try {
      await api('/api/profile', { method: 'POST', body: p });
      S.profile = p;
      S.profileEmpty = false;
      clearDirty();
      resetWorkspaceData();
      S.searchStale = true;
      updateProfileLink(); renderIdeas();
      $('#onboardNotice').hidden = true;
      renderProfile();
      toast('Profile saved');
      return true;
    } catch (err) {
      toast('Could not save: ' + err.message, 'error');
      return false;
    }
  }

  async function discardProfile() {
    clearDirty();
    await loadProfile();
    toast('Changes discarded');
  }

  async function handleFile(file) {
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) { toast('That file is larger than 8 MB.', 'error'); return; }
    toast(`Reading ${file.name}`);
    const binary = /\.(pdf|docx|doc)$/i.test(file.name);
    const reader = new FileReader();
    reader.onload = async e => {
      try {
        let body;
        if (binary) {
          const bytes = new Uint8Array(e.target.result);
          let bin = '';
          for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
          body = { filename: file.name, content_base64: btoa(bin) };
        } else {
          body = { text: e.target.result };
        }
        applyParsed(await api('/api/parse-resume', { method: 'POST', body }), file.name);
      } catch (err) {
        toast('Could not read the file: ' + err.message, 'error');
      }
    };
    if (binary) reader.readAsArrayBuffer(file); else reader.readAsText(file);
  }

  function applyParsed(res, label) {
    if (!res || !res.profile) return;
    const keep = S.profile || {};
    S.profile = normalizeProfile(Object.assign({}, keep, res.profile));
    renderProfile();
    const miss = (res.parse_report && res.parse_report.needs_review) || [];
    markDirty(miss.length ? `Check these fields, then save: ${miss.join(', ')}.` : 'Review the fields, then save your profile.');
    toast(`Read ${label}. Review the fields, then save.`);
    $('#profileForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function parsePasted() {
    const text = val('rawResumePaste').trim();
    if (!text) { toast('Paste your resume text first.', 'error'); return; }
    try { applyParsed(await api('/api/parse-resume', { method: 'POST', body: { text } }), 'your text'); }
    catch (err) { toast('Could not read the text: ' + err.message, 'error'); }
  }

  async function addSkillToProfile(skill) {
    syncFormToState();
    if (S.profile.skills.includes(skill)) return;
    S.profile.skills.push(skill);
    renderSkills();
    if (await saveProfile()) {
      toast(`Added ${skill} to your profile`);
      renderWsTab();
    }
  }

  // ----------------------------------------------------------------- search
  function syncWorkModeSeg() {
    $$('#workModeSeg [data-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === S.workMode)));
  }

  function renderIdeas() {
    const p = S.profile || {};
    let ideas = [];
    if (p.target_title) ideas.push(p.target_title);
    if (Array.isArray(p.target_roles)) {
      ideas.push(...p.target_roles);
    }
    const skills = p.skills || [];
    for (const s of skills) {
      if (/^(python|react|node|javascript|typescript|java|golang|c#|ruby|rust)$/i.test(s)) {
        ideas.push(`${s} Developer`);
      }
    }
    ideas.push(...skills.slice(0, 3));
    if (!ideas.length) ideas = DEFAULT_IDEAS;
    const seen = new Set();
    ideas = ideas.filter(x => { const k = x.toLowerCase(); if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 6);
    $('#suggestChips').innerHTML = ideas.map(x => `<button type="button" class="chip" data-action="idea" data-q="${esc(x)}">${esc(x)}</button>`).join('');
  }

  function skeletons(n = 4) {
    return Array.from({ length: n }, () => '<div class="skeleton"><i></i><i></i><i></i></div>').join('');
  }

  const SEARCH_TIPS = [
    {
      title: 'Why direct ATS matters',
      text: 'Applying directly through company applicant systems like Ashby, Greenhouse, or Lever sends your profile straight to the employer\'s internal hiring team.'
    },
    {
      title: 'Merging duplicate listings',
      text: 'Many boards scrape each other and repost identical roles with slight differences. JobHunter groups them together so you only review each position once.'
    },
    {
      title: 'Honest match scoring',
      text: 'Your match score reflects only skills and experience you actually listed in your profile. Nothing is guessed or exaggerated.'
    },
    {
      title: 'Timing matters',
      text: 'Applying within the first two days of a listing going live gives hiring managers the earliest look at your resume.'
    }
  ];

  let searchTipTimer = null;
  let scoreEtaTimer = null;
  let scoreEtaState = { current: 0, total: 350, estSeconds: 2.2, startTime: 0 };

  function stopScoreEtaTicker() {
    if (scoreEtaTimer) { clearInterval(scoreEtaTimer); scoreEtaTimer = null; }
  }

  function startScoreEtaTicker(total, estSeconds) {
    stopScoreEtaTicker();
    scoreEtaState = {
      current: 0,
      total: total || 350,
      estSeconds: estSeconds || 2.2,
      startTime: Date.now()
    };

    scoreEtaTimer = setInterval(() => {
      if (scoreEtaState.current >= scoreEtaState.total) {
        stopScoreEtaTicker();
        return;
      }
      const elapsed = (Date.now() - scoreEtaState.startTime) / 1000;
      const rate = scoreEtaState.estSeconds > 0 ? (scoreEtaState.total - scoreEtaState.current) / scoreEtaState.estSeconds : 50;
      const extra = Math.round(elapsed * rate);
      const simulatedCount = Math.min(scoreEtaState.total, scoreEtaState.current + extra);
      const remSec = Math.max(0.1, scoreEtaState.estSeconds - elapsed).toFixed(1);

      const sub = $('#searchStepSub-3');
      if (sub) {
        if (simulatedCount >= scoreEtaState.total) {
          sub.innerHTML = `${scoreEtaState.total}/${scoreEtaState.total} • <span class="step-eta-text">Done</span>`;
        } else {
          sub.innerHTML = `${simulatedCount}/${scoreEtaState.total} • <span class="step-eta-text">~${remSec}s left</span>`;
        }
      }
      const pct = Math.round((simulatedCount / scoreEtaState.total) * 100);
      const miniBar = $('#stepMiniBar');
      if (miniBar) {
        miniBar.style.width = `${pct}%`;
      }
      const metric = $('#metricDedupVal');
      if (metric) {
        metric.textContent = `${simulatedCount} / ${scoreEtaState.total} scored (~${remSec}s left)`;
      }
      const bar = $('#searchStageBar');
      if (bar) {
        const barPct = Math.min(97, 88 + Math.round((simulatedCount / scoreEtaState.total) * 9));
        bar.style.width = barPct + '%';
      }
    }, 120);
  }

  function updateScoreEtaTickerBaseline(curr, total, estSec) {
    scoreEtaState.current = curr;
    scoreEtaState.total = total;
    scoreEtaState.estSeconds = estSec;
    scoreEtaState.startTime = Date.now();
  }

  function stopSearchProgressAnimation() {
    if (searchTipTimer) { clearInterval(searchTipTimer); searchTipTimer = null; }
    stopScoreEtaTicker();
  }

  function formatSourceLabel(raw) {
    if (!raw) return '';
    if (raw.includes(':')) {
      const parts = raw.split(':');
      const board = parts[0].charAt(0).toUpperCase() + parts[0].slice(1);
      const comp = parts[1].charAt(0).toUpperCase() + parts[1].slice(1);
      return `${comp} (${board})`;
    }
    return raw;
  }

  function renderSearchHubSkeleton() {
    stopSearchProgressAnimation();

    const stage = $('#searchProgressStage');
    if (stage) stage.hidden = false;
    const split = $('#searchSplit');
    if (split) split.hidden = true;
    const resultsMeta = $('#resultsMeta');
    if (resultsMeta) resultsMeta.hidden = true;
    const tools = $('#resultsTools');
    if (tools) tools.hidden = true;

    if (stage) {
      stage.innerHTML = `
        <div class="search-stage-card">
          <div class="search-stage-header">
            <div class="search-stage-status">
              <span class="search-live-orb" aria-hidden="true"><span class="search-live-orb-core"></span></span>
              <span class="search-stage-kicker" id="searchStageKicker">Live search in progress</span>
            </div>
            <h2 class="search-stage-title" id="searchStageTitle">Connecting to employer boards and feeds</h2>
            <p class="search-stage-desc" id="searchStageDesc">Querying company ATS portals, direct employer watchlists, and remote tech feeds in parallel.</p>
          </div>

          <div class="search-stage-track" role="progressbar" aria-label="Search progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="15" id="searchStageTrack">
            <div class="search-stage-bar" id="searchStageBar" style="width: 15%;"></div>
          </div>

          <div class="search-stage-steps" role="list">
            <div class="search-step is-active" id="searchStep-0" role="listitem">
              <div class="search-step-marker">
                <span class="step-num">1</span>
                <span class="step-check" aria-hidden="true">✓</span>
              </div>
              <div class="search-step-body">
                <span class="step-label">Connect</span>
                <span class="step-sub" id="searchStepSub-0">Querying sources</span>
              </div>
            </div>
            <div class="search-step" id="searchStep-1" role="listitem">
              <div class="search-step-marker">
                <span class="step-num">2</span>
                <span class="step-check" aria-hidden="true">✓</span>
              </div>
              <div class="search-step-body">
                <span class="step-label" id="searchScanStepLabel">Collect</span>
                <span class="step-sub" id="searchStepSub-1">Streaming postings</span>
              </div>
            </div>
            <div class="search-step" id="searchStep-2" role="listitem">
              <div class="search-step-marker">
                <span class="step-num">3</span>
                <span class="step-check" aria-hidden="true">✓</span>
              </div>
              <div class="search-step-body">
                <span class="step-label">Deduplicate</span>
                <span class="step-sub" id="searchStepSub-2">Merging duplicates</span>
              </div>
            </div>
            <div class="search-step" id="searchStep-3" role="listitem">
              <div class="search-step-marker">
                <span class="step-num">4</span>
                <span class="step-check" aria-hidden="true">✓</span>
              </div>
              <div class="search-step-body">
                <span class="step-label" id="searchScoreStepLabel">Match &amp; rank</span>
                <span class="step-sub" id="searchStepSub-3">Scoring your resume</span>
                <div class="step-mini-track" id="stepMiniTrack" hidden>
                  <div class="step-mini-bar" id="stepMiniBar" style="width: 0%;"></div>
                </div>
              </div>
            </div>
          </div>

          <div class="search-stage-radar">
            <div class="search-radar-head">
              <span class="radar-title">Active source radar</span>
              <span class="radar-counter" id="searchRadarCounter">Connecting to boards...</span>
            </div>
            <div class="search-sources-grid" id="searchSourcesGrid">
              <div class="source-card is-scanning">
                <span class="source-card-indicator" aria-hidden="true"></span>
                <span class="source-card-name">Connecting to sources...</span>
                <span class="source-card-status">Waiting</span>
              </div>
            </div>
          </div>

          <div class="search-metrics-strip">
            <div class="search-metric-item">
              <span class="metric-label">Sources completed</span>
              <strong class="metric-value" id="metricSourcesVal">0 / 0</strong>
            </div>
            <div class="search-metric-sep"></div>
            <div class="search-metric-item">
              <span class="metric-label">Raw postings gathered</span>
              <strong class="metric-value" id="metricPostingsVal">0</strong>
            </div>
            <div class="search-metric-sep"></div>
            <div class="search-metric-item">
              <span class="metric-label">Duplicate resolution</span>
              <strong class="metric-value" id="metricDedupVal">Waiting</strong>
            </div>
          </div>

          <div class="search-stage-note" id="searchStageNote">
            <div class="search-note-lead" id="searchNoteLead">${esc(SEARCH_TIPS[0].title)}</div>
            <p class="search-note-text" id="searchNoteText">${esc(SEARCH_TIPS[0].text)}</p>
          </div>
        </div>
      `;
    }

    let tipIdx = 0;
    searchTipTimer = setInterval(() => {
      tipIdx = (tipIdx + 1) % SEARCH_TIPS.length;
      const tipLead = $('#searchNoteLead');
      const tipText = $('#searchNoteText');
      if (tipLead && tipText) {
        tipLead.textContent = SEARCH_TIPS[tipIdx].title;
        tipText.textContent = SEARCH_TIPS[tipIdx].text;
      }
    }, 3200);
  }

  function handleRealSearchEvent(type, data) {
    const titleEl = $('#searchStageTitle');
    const descEl = $('#searchStageDesc');
    const barEl = $('#searchStageBar');
    const trackEl = $('#searchStageTrack');
    const gridBox = $('#searchSourcesGrid');
    const counterEl = $('#searchRadarCounter');
    const metricSources = $('#metricSourcesVal');
    const metricPostings = $('#metricPostingsVal');
    const metricDedup = $('#metricDedupVal');

    if (type === 'init') {
      const step0 = $('#searchStep-0');
      const step1 = $('#searchStep-1');
      if (step0) step0.className = 'search-step is-done';
      if (step1) step1.className = 'search-step is-active';
      if (titleEl) titleEl.textContent = `Querying ${data.total} sources in parallel`;
      if (descEl) descEl.textContent = `Dispatched queries to verified company ATS portals and remote tech feeds.`;
      if (barEl) barEl.style.width = '20%';
      if (trackEl) trackEl.setAttribute('aria-valuenow', '20');
      if (counterEl) counterEl.textContent = `0 of ${data.total} answered`;
      if (metricSources) metricSources.textContent = `0 / ${data.total}`;

      if (gridBox && data.sources) {
        gridBox.innerHTML = data.sources.map(s => {
          const safeId = 'src-card-' + String(s).replace(/[^a-zA-Z0-9_-]/g, '_');
          return `
            <div class="source-card is-scanning" id="${safeId}" data-src="${esc(s)}">
              <span class="source-card-indicator" aria-hidden="true"></span>
              <span class="source-card-name" title="${esc(formatSourceLabel(s))}">${esc(formatSourceLabel(s))}</span>
              <span class="source-card-status">Scanning</span>
            </div>`;
        }).join('');
      }
    } else if (type === 'source_done') {
      const safeId = 'src-card-' + String(data.source).replace(/[^a-zA-Z0-9_-]/g, '_');
      const card = $(`#${safeId}`);
      if (card) {
        card.classList.remove('is-scanning');
        const statusSpan = card.querySelector('.source-card-status');
        if (data.state === 'ok' || data.state === 'cached') {
          card.classList.add('is-done');
          if (statusSpan) statusSpan.textContent = `+${data.count} • ${data.ms}ms`;
        } else {
          card.classList.add('is-idle');
          if (statusSpan) statusSpan.textContent = `0 • ${data.ms}ms`;
        }
      }

      const scanLabel = $('#searchScanStepLabel');
      if (scanLabel) scanLabel.textContent = `Collect (${data.completed}/${data.total})`;
      const pct = Math.min(80, Math.round(20 + (data.completed / data.total) * 60));
      if (barEl) barEl.style.width = pct + '%';
      if (trackEl) trackEl.setAttribute('aria-valuenow', String(pct));
      if (counterEl) counterEl.textContent = `${data.completed} of ${data.total} answered`;
      if (metricSources) metricSources.textContent = `${data.completed} / ${data.total}`;
      if (metricPostings) metricPostings.textContent = String(data.raw_total || 0);

      if (titleEl) titleEl.textContent = `Gathered ${data.raw_total} postings (${data.completed} of ${data.total} sources finished)`;
      if (descEl) descEl.textContent = `Received response from ${formatSourceLabel(data.source)} (${data.count} jobs in ${data.ms}ms).`;
    } else if (type === 'stage') {
      if (data.stage === 'dedup') {
        const step1 = $('#searchStep-1');
        const step2 = $('#searchStep-2');
        if (step1) step1.className = 'search-step is-done';
        if (step2) step2.className = 'search-step is-active';
        if (titleEl) titleEl.textContent = `Merging cross-board duplicates`;
        if (descEl) descEl.textContent = data.message || `Deduplicating raw postings to isolate direct company application links.`;
        if (barEl) barEl.style.width = '86%';
        if (trackEl) trackEl.setAttribute('aria-valuenow', '86');
        if (metricDedup) metricDedup.textContent = `Filtering mirrors...`;
      } else if (data.stage === 'score') {
        const step2 = $('#searchStep-2');
        const step3 = $('#searchStep-3');
        if (step2) step2.className = 'search-step is-done';
        if (step3) step3.className = 'search-step is-active';

        const estSec = data.est_seconds || 2.2;
        const total = data.unique_count || 0;

        const scoreLabel = $('#searchScoreStepLabel');
        if (scoreLabel) scoreLabel.textContent = 'Match & rank';
        const miniTrack = $('#stepMiniTrack');
        if (miniTrack) miniTrack.hidden = false;
        const miniBar = $('#stepMiniBar');
        if (miniBar) miniBar.style.width = '6%';
        const stepSub3 = $('#searchStepSub-3');
        if (stepSub3) stepSub3.innerHTML = `0/${total} • <span class="step-eta-text">~${estSec}s left</span>`;

        if (titleEl) titleEl.textContent = `Calculating honest match scores`;
        if (descEl) descEl.textContent = `Evaluating ${total} unique roles against your skills and experience (~${estSec}s remaining)...`;
        if (barEl) barEl.style.width = '88%';
        if (trackEl) trackEl.setAttribute('aria-valuenow', '88');
        if (metricDedup) metricDedup.textContent = `0 / ${total} scored (~${estSec}s left)`;

        startScoreEtaTicker(total, estSec);
      } else if (data.stage === 'score_progress') {
        const scoreLabel = $('#searchScoreStepLabel');
        if (scoreLabel) scoreLabel.textContent = 'Match & rank';
        const miniBar = $('#stepMiniBar');
        if (miniBar) miniBar.style.width = `${data.pct}%`;
        const stepSub3 = $('#searchStepSub-3');

        // If scoring is complete (current == total), show done state immediately
        if (data.current >= data.total) {
          stopScoreEtaTicker();
          if (stepSub3) stepSub3.innerHTML = `${data.total}/${data.total} • <span class="step-eta-text">Done</span>`;
          if (miniBar) miniBar.style.width = '100%';
          if (metricDedup) metricDedup.textContent = `${data.total} / ${data.total} scored`;
          if (titleEl) titleEl.textContent = 'Scoring complete: finalizing results';
          if (descEl) descEl.textContent = `All ${data.total} roles scored against your resume. Sorting results...`;
          const barPct = 97;
          if (barEl) barEl.style.width = barPct + '%';
          if (trackEl) trackEl.setAttribute('aria-valuenow', String(barPct));
          return;
        }

        if (stepSub3) stepSub3.innerHTML = `${data.current}/${data.total} • <span class="step-eta-text">~${data.est_seconds}s left</span>`;

        if (titleEl) titleEl.textContent = `Calculating honest match scores`;
        if (descEl) descEl.textContent = `Scored ${data.current} of ${data.total} roles against your resume profile (~${data.est_seconds}s remaining)...`;

        const barPct = Math.min(96, 88 + Math.round((data.current / data.total) * 9));
        if (barEl) barEl.style.width = barPct + '%';
        if (trackEl) trackEl.setAttribute('aria-valuenow', String(barPct));
        if (metricDedup) metricDedup.textContent = `${data.current} / ${data.total} scored (~${data.est_seconds}s left)`;

        updateScoreEtaTickerBaseline(data.current, data.total, data.est_seconds);
      } else if (data.stage === 'enrich') {
        const scoreLabel = $('#searchScoreStepLabel');
        if (scoreLabel) scoreLabel.textContent = 'Match & rank';
        const stepSub3 = $('#searchStepSub-3');
        if (stepSub3) stepSub3.innerHTML = `Verifying top ${data.enrich_count || 12} direct links • <span class="step-eta-text">~${data.est_seconds || 1}s left</span>`;
        const miniBar = $('#stepMiniBar');
        if (miniBar) miniBar.style.width = '96%';
        if (titleEl) titleEl.textContent = `Verifying direct employer links`;
        if (descEl) descEl.textContent = `Ensuring top application links route straight to verified employer portals (~1s remaining)...`;
        if (barEl) barEl.style.width = '98%';
        if (trackEl) trackEl.setAttribute('aria-valuenow', '98');
      }
    }
  }

  async function runSearch(opts = {}) {
    const isForce = Boolean(opts && opts.forceRefresh);
    stopSearchProgressAnimation();
    const seq = ++S.searchSeq;
    const btn = $('#btnSearch');
    const refreshBtn = $('#btnRefresh');
    if (btn) { btn.disabled = true; btn.innerHTML = `<span class="btn-spinner"></span> Searching`; }
    if (refreshBtn) { refreshBtn.disabled = true; refreshBtn.innerHTML = `<span class="btn-spinner"></span>`; }
    renderSearchHubSkeleton();
    $('#sourceToggle').hidden = true;
    $('#sourcePanel').hidden = true;

    const params = new URLSearchParams({
      q: val('searchQuery').trim(), location: val('searchLocation').trim(),
      work_mode: 'Any', min_score: '0',
      famous_mode: 'all'
    });
    if (isForce) {
      params.set('refresh', '1');
    }

    const metaToken = document.querySelector('meta[name="jh-token"]');
    const token = metaToken ? metaToken.content : '';

    let completedData = null;
    try {
      const res = await fetch('/api/search/stream?' + params.toString(), {
        headers: { 'X-JH-Token': token }
      });

      if (!res.ok) throw new Error('Streaming unavailable');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();
        for (const part of parts) {
          if (!part.trim()) continue;
          let eventType = 'message';
          let dataStr = '';
          for (const line of part.split('\n')) {
            if (line.startsWith('event:')) eventType = line.slice(6).trim();
            else if (line.startsWith('data:')) dataStr = line.slice(5).trim();
          }
          if (!dataStr) continue;
          try {
            const parsed = JSON.parse(dataStr);
            if (seq !== S.searchSeq) return;
            handleRealSearchEvent(eventType, parsed);
            if (eventType === 'complete') {
              completedData = parsed;
              try { reader.cancel(); } catch (e) {}
              break;
            }
          } catch (e) {}
        }
        if (completedData) break;
      }
    } catch (streamErr) {
      try {
        completedData = await api('/api/search?' + params.toString());
      } catch (e) {
        if (seq !== S.searchSeq) return;
        stopSearchProgressAnimation();
        const stage = $('#searchProgressStage');
        if (stage) stage.hidden = true;
        const split = $('#searchSplit');
        if (split) split.hidden = false;
        const tools = $('#resultsTools');
        if (tools) tools.hidden = false;
        const resultsMeta = $('#resultsMeta');
        if (resultsMeta) resultsMeta.hidden = false;
        S.jobs = []; S.searchMeta = null;
        $('#resultsSummary').textContent = 'Search failed';
        $('#jobList').innerHTML = `<div class="empty">${ico('alert')}<h3>The search did not finish</h3><p>${esc(e.message)}</p><div class="empty-actions"><button type="button" class="btn btn-primary" data-action="search-again">Try again</button></div></div>`;
        $('#jobDetail').innerHTML = '';
        return;
      }
    } finally {
      if (seq === S.searchSeq) {
        if (btn) { btn.disabled = false; btn.innerHTML = `${ico('search')} Search`; }
        if (refreshBtn) { refreshBtn.disabled = false; refreshBtn.innerHTML = `${ico('refresh')}<span>Refresh</span>`; }
      }
    }

    if (seq !== S.searchSeq || !completedData) return;

    // Graceful final stage completion moment
    stopScoreEtaTicker();
    const step3 = $('#searchStep-3');
    if (step3) step3.className = 'search-step is-done';
    const badge = $('#searchStepEtaBadge');
    if (badge) {
      badge.textContent = 'Done';
      badge.classList.add('is-done');
    }
    const scoreLabel = $('#searchScoreStepLabel');
    if (scoreLabel) scoreLabel.textContent = 'Match & rank';
    const sub = $('#searchStepSub-3');
    if (sub) sub.textContent = 'Complete';
    const miniBar = $('#stepMiniBar');
    if (miniBar) miniBar.style.width = '100%';
    const barEl = $('#searchStageBar');
    if (barEl) barEl.style.width = '100%';
    const titleEl = $('#searchStageTitle');
    if (titleEl) titleEl.textContent = `Completed`;

    await new Promise(r => setTimeout(r, 260));
    if (seq !== S.searchSeq) return;

    stopSearchProgressAnimation();
    S.searchMeta = completedData;
    S.allJobs = completedData.all_jobs || completedData.jobs || [];
    S.jobsRanked = S.allJobs;
    S.searchHasRun = true;
    S.lastSearchTime = Date.now();
    try {
      sessionStorage.setItem('jh-last-search-meta', JSON.stringify(completedData));
      sessionStorage.setItem('jh-last-search-time', String(S.lastSearchTime));
    } catch (e) {}
    filterAndRender();
  }

  function jobWorkMode(j) {
    const m = String(j.work_mode || '').toLowerCase();
    const loc = String(j.location || '').toLowerCase();
    if (m.includes('remote') || loc.includes('remote') || loc.includes('worldwide') || loc.includes('anywhere')) {
      return 'remote';
    }
    if (m.includes('hybrid') || loc.includes('hybrid')) {
      return 'hybrid';
    }
    if (m || loc) return 'onsite';
    return 'unknown';
  }

  function jobSeniority(j) {
    if (j.seniority) return j.seniority;
    const t = `${j.title || ''} ${(j.description || '').slice(0, 350)}`.toLowerCase();
    if (/\b(intern|internship|co-op|apprentice)\b/.test(t)) return 'intern';
    if (/\b(lead|staff|principal|director|head of|vp|architect|founding)\b/.test(t)) return 'lead_staff';
    if (/\b(senior|sr\.?|sr\b)\b/.test(t)) return 'senior';
    if (/\b(junior|jr\.?|jr\b|entry|associate|graduate|new grad)\b/.test(t)) return 'junior';
    return 'mid';
  }

  function jobAnnualSalaryMax(j) {
    if (typeof j.salary_annual_max === 'number' && j.salary_annual_max > 0) return j.salary_annual_max;
    const raw = String(j.salary || '').toLowerCase().replace(/,/g, '');
    const nums = [];
    for (const m of raw.matchAll(/(\d+(?:\.\d+)?)\s*(k|m)?(?![a-z0-9])/g)) {
      let v = parseFloat(m[1]);
      if (m[2] === 'k') v *= 1000;
      else if (m[2] === 'm') v *= 1000000;
      nums.push(v);
    }
    const valid = nums.filter(n => n >= 10);
    if (!valid.length) return 0;
    const hi = Math.max(...valid.slice(0, 2));
    const isHourly = raw.includes('/hr') || raw.includes('/hour') || raw.includes('hourly') || hi < 400;
    const isMonthly = raw.includes('/mo') || raw.includes('/month') || raw.includes('monthly');
    const mult = isHourly ? 2080 : isMonthly ? 12 : 1;
    return Math.round(hi * mult);
  }

  const US_STATES_SET = new Set([
    'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga', 'hi', 'id', 'il', 'in', 'ia',
    'ks', 'ky', 'la', 'me', 'md', 'ma', 'mi', 'mn', 'ms', 'mo', 'mt', 'ne', 'nv', 'nh', 'nj',
    'nm', 'ny', 'nc', 'nd', 'oh', 'ok', 'or', 'pa', 'ri', 'sc', 'sd', 'tn', 'tx', 'ut', 'vt',
    'va', 'wa', 'wv', 'wi', 'wy', 'dc'
  ]);

  const US_MAJOR_CITIES_LIST = [
    'seattle', 'san francisco', 'new york', 'nyc', 'boston', 'chicago', 'los angeles', 'austin',
    'denver', 'atlanta', 'miami', 'silicon valley', 'bay area', 'dallas', 'houston', 'phoenix',
    'philadelphia', 'san diego', 'salt lake city', 'portland', 'washington'
  ];

  const CANADIAN_PROVINCES_SET = new Set([
    'on', 'bc', 'qc', 'ab', 'mb', 'sk', 'ns', 'nb', 'nl', 'pe',
    'ontario', 'british columbia', 'quebec', 'alberta'
  ]);

  const COUNTRY_MATCH_PATTERNS = [
    [/\b(united states|usa|u\.s\.a?|u\.s\b|us\b)\b/i, 'United States'],
    [/\b(united kingdom|great britain|england|scotland|wales|uk\b|u\.k\b|gb\b)\b/i, 'United Kingdom'],
    [/\b(canada|can\b)\b/i, 'Canada'],
    [/\b(germany|deutschland|de\b)\b/i, 'Germany'],
    [/\b(france|fr\b)\b/i, 'France'],
    [/\b(netherlands|holland|amsterdam|rotterdam|nl\b)\b/i, 'Netherlands'],
    [/\b(india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|noida|gurugram|in\b)\b/i, 'India'],
    [/\b(australia|sydney|melbourne|brisbane|au\b|aus\b)\b/i, 'Australia'],
    [/\b(singapore|sg\b)\b/i, 'Singapore'],
    [/\b(ireland|dublin|ie\b)\b/i, 'Ireland'],
    [/\b(spain|españa|madrid|barcelona|es\b)\b/i, 'Spain'],
    [/\b(switzerland|schweiz|suisse|zurich|geneva|ch\b)\b/i, 'Switzerland'],
    [/\b(poland|polska|warsaw|krakow|pl\b)\b/i, 'Poland'],
    [/\b(sweden|sverige|stockholm|se\b)\b/i, 'Sweden'],
    [/\b(brazil|brasil|sao paulo|br\b)\b/i, 'Brazil'],
    [/\b(japan|nippon|tokyo|jp\b)\b/i, 'Japan'],
    [/\b(south korea|korea|seoul|kr\b)\b/i, 'South Korea'],
    [/\b(israel|tel aviv|il\b)\b/i, 'Israel'],
    [/\b(italy|italia|rome|milan|it\b)\b/i, 'Italy'],
    [/\b(mexico|mx\b)\b/i, 'Mexico'],
    [/\b(new zealand|nz\b)\b/i, 'New Zealand'],
    [/\b(portugal|lisbon|pt\b)\b/i, 'Portugal'],
    [/\b(austria|österreich|vienna|at\b)\b/i, 'Austria'],
    [/\b(belgium|brussels|be\b)\b/i, 'Belgium'],
    [/\b(denmark|copenhagen|dk\b)\b/i, 'Denmark'],
    [/\b(finland|helsinki|fi\b)\b/i, 'Finland'],
    [/\b(norway|oslo|no\b)\b/i, 'Norway'],
    [/\b(south africa|za\b)\b/i, 'South Africa'],
    [/\b(argentina|ar\b)\b/i, 'Argentina'],
    [/\b(colombia|co\b)\b/i, 'Colombia'],
    [/\b(uae|united arab emirates|dubai)\b/i, 'UAE'],
    [/\b(nigeria|lagos|ng\b)\b/i, 'Nigeria'],
    [/\b(kenya|nairobi|ke\b)\b/i, 'Kenya'],
    [/\b(czech republic|czechia|prague|cz\b)\b/i, 'Czech Republic'],
    [/\b(romania|bucharest|ro\b)\b/i, 'Romania'],
    [/\b(estonia|tallinn|ee\b)\b/i, 'Estonia'],
    [/\b(morocco|casablanca|rabat|ma\b)\b/i, 'Morocco'],
    [/\b(egypt|cairo|alexandria|eg\b)\b/i, 'Egypt'],
    [/\b(indonesia|jakarta|id\b)\b/i, 'Indonesia'],
    [/\b(vietnam|hanoi|ho chi minh|vn\b)\b/i, 'Vietnam'],
    [/\b(bangladesh|dhaka|bd\b)\b/i, 'Bangladesh'],
    [/\b(worldwide|anywhere|global|everywhere)\b/i, 'Worldwide']
  ];

  function jobCountry(j) {
    if (j.country) return j.country;
    const loc = (j.location || '').trim();
    if (!loc || /^(remote|unknown|work from home|remote - anywhere)$/i.test(loc)) return 'Worldwide';

    const parts = loc.split(',').map(p => p.trim()).filter(Boolean);
    if (parts.length) {
      const last = parts[parts.length - 1].toLowerCase();
      if (US_STATES_SET.has(last)) return 'United States';
      if (CANADIAN_PROVINCES_SET.has(last)) return 'Canada';
      if (parts.length >= 2) {
        const secondLast = parts[parts.length - 2].toLowerCase();
        if (US_STATES_SET.has(secondLast)) return 'United States';
        if (CANADIAN_PROVINCES_SET.has(secondLast)) return 'Canada';
      }
    }

    const locLower = loc.toLowerCase();
    if (US_MAJOR_CITIES_LIST.some(c => locLower.includes(c))) return 'United States';

    for (const [re, name] of COUNTRY_MATCH_PATTERNS) {
      if (re.test(loc)) return name;
    }

    if (/worldwide|anywhere|global/i.test(locLower)) return 'Worldwide';

    if (parts.length) {
      const cleaned = parts[parts.length - 1].replace(/[^A-Za-z\s-]/g, '').trim();
      if (cleaned.length >= 3 && !/^(remote|hybrid|onsite|area|region|city)$/i.test(cleaned)) {
        return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
      }
    }
    return 'Worldwide';
  }

  function jobIsStartup(j) {
    if (isFamousJob(j)) return false;
    if (j.company_stage === 'startup' || j.company_stage === 'mid_tech') return true;
    const tags = (j.tags || []).map(t => String(t).toLowerCase());
    if (tags.includes('startup')) return true;
    const text = `${j.title || ''} ${j.company || ''} ${(j.description || '').slice(0, 500)}`.toLowerCase();
    if (/\b(startup|early-stage|early stage|founding engineer|founding developer|stealth|seed stage|series a|series b)\b/.test(text)) return true;
    if (/\(yc\b/.test((j.company || '').toLowerCase())) return true;
    if (['Hacker News', 'RemoteOK', 'Himalayas'].includes(j.source)) return true;
    return true;
  }

  function jobDaysAgo(j) {
    if (!j.posted_at) return null;
    const t = new Date(j.posted_at).getTime();
    if (isNaN(t)) return null;
    return Math.max(0, (Date.now() - t) / 86400000);
  }

  function jobSkillsList(j) {
    const set = new Set();
    if (Array.isArray(j.matched_skills)) j.matched_skills.forEach(s => set.add(s));
    if (j.required_skills && typeof j.required_skills === 'object') {
      Object.keys(j.required_skills).forEach(s => set.add(s));
    }
    if (Array.isArray(j.tags)) j.tags.forEach(s => set.add(s));
    return Array.from(set);
  }

  function jobIsApplied(j) {
    if (!S.applications || !S.applications.length) return false;
    const jKey = jobKey(j);
    const co = (j.company || '').toLowerCase().trim();
    return S.applications.some(a => a.job_id === jKey || (a.company && a.company.toLowerCase().trim() === co));
  }

  function jobIsSaved(j) {
    const key = jobKey(j);
    if (S.applications && S.applications.some(a => a.job_id === key && a.status === 'saved')) return true;
    if (S.watchlist && S.watchlist.some(w => (w.company_name || '').toLowerCase() === (j.company || '').toLowerCase())) return true;
    return false;
  }

  function filteredJobs() {
    const pool = (S.jobsRanked && S.jobsRanked.length) ? S.jobsRanked : (S.allJobs || S.jobs || []);
    const f = S.filters || {};

    return pool.filter(j => {
      // 1. Keyword search
      if (f.keyword) {
        const kw = f.keyword.toLowerCase().trim();
        const hay = `${j.title || ''} ${j.company || ''} ${j.location || ''} ${(j.description || '').slice(0, 600)} ${jobSkillsList(j).join(' ')}`.toLowerCase();
        if (!hay.includes(kw)) return false;
      }

      // 2. Work Mode
      const reqMode = (f.workMode || 'Any').toLowerCase();
      if (reqMode && reqMode !== 'any') {
        const jm = jobWorkMode(j);
        if (reqMode === 'remote' && jm !== 'remote') return false;
        if (reqMode === 'hybrid' && jm !== 'hybrid') return false;
        if (reqMode === 'onsite' && jm !== 'onsite') return false;
      }

      // 3. Match Score
      if (f.minScore > 0 && (j.score || 0) < f.minScore) {
        return false;
      }

      // 4. Company Type (Big Tech vs Startups)
      if (f.famousMode === 'hide' && isFamousJob(j)) return false;
      if (f.famousMode === 'only' && !isFamousJob(j)) return false;
      if (f.famousMode === 'startups' && !jobIsStartup(j)) return false;

      // 5. Seniority
      if (f.seniority && f.seniority !== 'all') {
        const sen = jobSeniority(j);
        if (f.seniority === 'junior' && sen !== 'junior' && sen !== 'intern') return false;
        if (f.seniority === 'mid' && sen !== 'mid') return false;
        if (f.seniority === 'senior' && sen !== 'senior') return false;
        if (f.seniority === 'lead_staff' && sen !== 'lead_staff') return false;
      }

      // 6. Salary Tier
      if (f.salaryTier && f.salaryTier !== '0') {
        const salMax = jobAnnualSalaryMax(j);
        if (f.salaryTier === 'disclosed' && !salMax && !j.salary) return false;
        if (f.salaryTier === '100k' && salMax < 100000) return false;
        if (f.salaryTier === '140k' && salMax < 140000) return false;
        if (f.salaryTier === '180k' && salMax < 180000) return false;
      }

      // 7. Freshness
      if (f.freshnessDays > 0) {
        const days = jobDaysAgo(j);
        if (days === null || days > f.freshnessDays) return false;
      }

      // 8. Direct ATS Only
      if (f.directAtsOnly) {
        const isDirect = j.source_kind === 'Direct employer ATS' || String(j.source_tier || '').startsWith('Direct');
        if (!isDirect) return false;
      }

      // 9. Hide Applied
      if (f.hideApplied && jobIsApplied(j)) return false;

      // 10. Saved Only
      if (f.savedOnly && !jobIsSaved(j)) return false;

      // 11. Selected Skill Facets
      if (f.selectedSkills && f.selectedSkills.size > 0) {
        const jSkills = new Set(jobSkillsList(j).map(s => s.toLowerCase()));
        for (const reqSkill of f.selectedSkills) {
          if (!jSkills.has(reqSkill.toLowerCase())) return false;
        }
      }

      // 12. Target Country (Include)
      if (f.country && f.country !== 'all') {
        const jc = jobCountry(j);
        if (f.country === 'Worldwide') {
          if (jc !== 'Worldwide' && jobWorkMode(j) !== 'remote') return false;
        } else {
          const matchesCountry = (jc.toLowerCase() === f.country.toLowerCase());
          const isWorldwideRemote = (jc === 'Worldwide' || jobWorkMode(j) === 'remote');
          if (!matchesCountry && !isWorldwideRemote) return false;
        }
      }

      // 13. Excluded Countries (Hide unwanted)
      if (f.excludedCountries && f.excludedCountries.size > 0) {
        const jc = jobCountry(j).toLowerCase();
        for (const ex of f.excludedCountries) {
          if (jc === ex.toLowerCase()) return false;
        }
      }

      return true;
    });
  }

  function setFacetCountText(id, count) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = count !== undefined ? `(${count})` : '';
      el.style.opacity = count === 0 ? '0.4' : '0.85';
    }
  }

  function renderCountrySelects(all) {
    const cSel = $('#countrySelect');
    const exSel = $('#excludeCountrySelect');
    if (!cSel || !exSel) return;

    const counts = {};
    for (const j of all) {
      const c = jobCountry(j);
      if (c) counts[c] = (counts[c] || 0) + 1;
    }
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);

    const curC = S.filters.country || 'all';
    cSel.innerHTML = `<option value="all">All Countries (${all.length})</option>` +
      sorted.map(([c, count]) => `<option value="${esc(c)}"${c === curC ? ' selected' : ''}>${esc(c)} (${count})</option>`).join('');

    exSel.innerHTML = `<option value="">Choose country to exclude...</option>` +
      sorted.map(([c, count]) => {
        const disabled = S.filters.excludedCountries && S.filters.excludedCountries.has(c);
        return `<option value="${esc(c)}"${disabled ? ' disabled' : ''}>${esc(c)} (${count} jobs)</option>`;
      }).join('');
  }

  function renderExcludedTags() {
    const wrap = $('#excludedCountriesTags');
    if (!wrap) return;
    const ex = Array.from(S.filters.excludedCountries || []);
    if (!ex.length) {
      wrap.innerHTML = '';
      return;
    }
    wrap.innerHTML = ex.map(c => `
      <span class="active-filter-tag is-excluded">
        <span>Exclude: ${esc(c)}</span>
        <button type="button" data-remove-excluded="${esc(c)}" title="Remove exclusion" aria-label="Remove exclusion">&times;</button>
      </span>
    `).join('');
  }

  function updateFacetCounts() {
    const all = S.allJobs || S.jobs || [];
    if (!all.length) return;

    // Work modes
    setFacetCountText('cntModeAny', all.length);
    setFacetCountText('cntModeRemote', all.filter(j => jobWorkMode(j) === 'remote').length);
    setFacetCountText('cntModeHybrid', all.filter(j => jobWorkMode(j) === 'hybrid').length);
    setFacetCountText('cntModeOnsite', all.filter(j => jobWorkMode(j) === 'onsite').length);

    // Scores
    setFacetCountText('cntScore0', all.length);
    setFacetCountText('cntScore60', all.filter(j => (j.score || 0) >= 60).length);
    setFacetCountText('cntScore70', all.filter(j => (j.score || 0) >= 70).length);
    setFacetCountText('cntScore80', all.filter(j => (j.score || 0) >= 80).length);
    setFacetCountText('cntScore85', all.filter(j => (j.score || 0) >= 85).length);

    // Big Tech & Startups
    const cntFamOnly = all.filter(j => isFamousJob(j)).length;
    const cntStartups = all.filter(j => jobIsStartup(j)).length;
    setFacetCountText('cntFamAll', all.length);
    setFacetCountText('cntFamHide', all.length - cntFamOnly);
    setFacetCountText('cntFamStartups', cntStartups);
    setFacetCountText('cntFamOnly', cntFamOnly);

    // Target Country quick buttons
    setFacetCountText('cntCtryWorldwide', all.filter(j => jobCountry(j) === 'Worldwide' || jobWorkMode(j) === 'remote').length);
    setFacetCountText('cntCtryUS', all.filter(j => jobCountry(j) === 'United States').length);
    setFacetCountText('cntCtryUK', all.filter(j => jobCountry(j) === 'United Kingdom').length);
    setFacetCountText('cntCtryDE', all.filter(j => jobCountry(j) === 'Germany').length);
    setFacetCountText('cntCtryCA', all.filter(j => jobCountry(j) === 'Canada').length);

    // Quick exclude count badges
    setFacetCountText('cntExIndia', all.filter(j => jobCountry(j) === 'India').length);
    setFacetCountText('cntExUS', all.filter(j => jobCountry(j) === 'United States').length);

    // Seniority
    setFacetCountText('cntSenJr', all.filter(j => ['junior', 'intern'].includes(jobSeniority(j))).length);
    setFacetCountText('cntSenMid', all.filter(j => jobSeniority(j) === 'mid').length);
    setFacetCountText('cntSenSr', all.filter(j => jobSeniority(j) === 'senior').length);
    setFacetCountText('cntSenLead', all.filter(j => jobSeniority(j) === 'lead_staff').length);

    // Salary
    setFacetCountText('cntSalDisc', all.filter(j => Boolean(j.salary || jobAnnualSalaryMax(j) > 0)).length);
    setFacetCountText('cntSal100', all.filter(j => jobAnnualSalaryMax(j) >= 100000).length);
    setFacetCountText('cntSal140', all.filter(j => jobAnnualSalaryMax(j) >= 140000).length);
    setFacetCountText('cntSal180', all.filter(j => jobAnnualSalaryMax(j) >= 180000).length);

    // Freshness
    setFacetCountText('cntFresh1', all.filter(j => { const d = jobDaysAgo(j); return d !== null && d <= 1; }).length);
    setFacetCountText('cntFresh7', all.filter(j => { const d = jobDaysAgo(j); return d !== null && d <= 7; }).length);
    setFacetCountText('cntFresh14', all.filter(j => { const d = jobDaysAgo(j); return d !== null && d <= 14; }).length);
    setFacetCountText('cntFresh30', all.filter(j => { const d = jobDaysAgo(j); return d !== null && d <= 30; }).length);

    // Flags
    setFacetCountText('cntDirectAts', all.filter(j => j.source_kind === 'Direct employer ATS' || String(j.source_tier || '').startsWith('Direct')).length);
    setFacetCountText('cntApplied', all.filter(j => jobIsApplied(j)).length);
    setFacetCountText('cntSaved', all.filter(j => jobIsSaved(j)).length);

    renderCountrySelects(all);
    renderExcludedTags();
  }

  function renderActiveFilterTags() {
    const bar = $('#activeFiltersBar');
    const list = $('#activeFiltersList');
    if (!bar || !list) return;

    const f = S.filters;
    const tags = [];

    if (f.keyword) tags.push({ type: 'keyword', label: `Search: "${f.keyword}"`, val: f.keyword });
    if (f.workMode && f.workMode.toLowerCase() !== 'any') tags.push({ type: 'workMode', label: `Mode: ${f.workMode}` });
    if (f.minScore > 0) tags.push({ type: 'minScore', label: `Match: ${f.minScore}%+` });
    if (f.famousMode === 'hide') tags.push({ type: 'famousMode', label: 'No Big Tech' });
    else if (f.famousMode === 'startups') tags.push({ type: 'famousMode', label: 'Startups Only' });
    else if (f.famousMode === 'only') tags.push({ type: 'famousMode', label: 'Big Tech Only' });

    if (f.country && f.country !== 'all') tags.push({ type: 'country', label: `Country: ${f.country}` });
    if (f.excludedCountries && f.excludedCountries.size > 0) {
      f.excludedCountries.forEach(ex => {
        tags.push({ type: 'exclude_country', label: `Exclude: ${ex}`, val: ex, isExcluded: true });
      });
    }

    if (f.seniority && f.seniority !== 'all') {
      const labelMap = { junior: 'Entry / Jr', mid: 'Mid-Level', senior: 'Senior', lead_staff: 'Lead / Staff' };
      tags.push({ type: 'seniority', label: `Level: ${labelMap[f.seniority] || f.seniority}` });
    }
    if (f.salaryTier && f.salaryTier !== '0') {
      const salMap = { disclosed: 'Pay Disclosed', '100k': '$100k+', '140k': '$140k+', '180k': '$180k+' };
      tags.push({ type: 'salaryTier', label: `Pay: ${salMap[f.salaryTier] || f.salaryTier}` });
    }
    if (f.freshnessDays > 0) tags.push({ type: 'freshnessDays', label: `Posted: < ${f.freshnessDays}d` });
    if (f.directAtsOnly) tags.push({ type: 'directAtsOnly', label: 'Direct ATS Only' });
    if (f.hideApplied) tags.push({ type: 'hideApplied', label: 'Hide Applied' });
    if (f.savedOnly) tags.push({ type: 'savedOnly', label: 'Saved Only' });

    // Badge on More Filters button
    const drawerActiveCount = [
      f.country !== 'all',
      f.excludedCountries.size > 0,
      f.seniority !== 'all',
      f.salaryTier !== '0',
      f.freshnessDays > 0,
      f.directAtsOnly,
      f.hideApplied,
      f.savedOnly
    ].filter(Boolean).length;

    const drawerBadge = $('#moreFiltersCountBadge');
    if (drawerBadge) {
      drawerBadge.textContent = drawerActiveCount;
      drawerBadge.hidden = drawerActiveCount === 0;
    }

    if (!tags.length) {
      bar.hidden = true;
      list.innerHTML = '';
      return;
    }

    bar.hidden = false;
    list.innerHTML = tags.map(t => `
      <span class="active-filter-tag${t.isExcluded ? ' is-excluded' : ''}">
        <span>${esc(t.label)}</span>
        <button type="button" data-remove-filter="${esc(t.type)}" data-filter-val="${esc(t.val || '')}" title="Remove this filter" aria-label="Remove filter">&times;</button>
      </span>
    `).join('');
  }

  function removeSingleFilter(type, val) {
    const f = S.filters;
    if (type === 'keyword') {
      f.keyword = '';
    } else if (type === 'workMode') {
      f.workMode = 'Any';
      S.workMode = 'Any';
    } else if (type === 'minScore') {
      f.minScore = 0;
      const s = $('#searchMinScore'); if (s) s.value = '0';
    } else if (type === 'famousMode') {
      f.famousMode = 'all';
      S.famousFilter = 'all';
      try { localStorage.setItem('jh-famous-filter', 'all'); } catch (e) {}
    } else if (type === 'country') {
      f.country = 'all';
      const cSel = $('#countrySelect'); if (cSel) cSel.value = 'all';
    } else if (type === 'exclude_country' && val) {
      f.excludedCountries.delete(val);
    } else if (type === 'seniority') {
      f.seniority = 'all';
    } else if (type === 'salaryTier') {
      f.salaryTier = '0';
    } else if (type === 'freshnessDays') {
      f.freshnessDays = 0;
    } else if (type === 'directAtsOnly') {
      f.directAtsOnly = false;
    } else if (type === 'hideApplied') {
      f.hideApplied = false;
    } else if (type === 'savedOnly') {
      f.savedOnly = false;
    } else if (type === 'skill' && val) {
      f.selectedSkills.delete(val);
    }
  }

  function resetAllFilters() {
    S.filters = {
      keyword: '',
      workMode: 'Any',
      minScore: 0,
      famousMode: 'all',
      country: 'all',
      excludedCountries: new Set(),
      seniority: 'all',
      salaryTier: '0',
      freshnessDays: 0,
      directAtsOnly: false,
      hideApplied: false,
      savedOnly: false,
      selectedSkills: new Set()
    };
    S.workMode = 'Any';
    S.famousFilter = 'all';
    try { localStorage.setItem('jh-famous-filter', 'all'); } catch (e) {}
    const s = $('#searchMinScore'); if (s) s.value = '0';
    const fam = $('#searchFamousSelect'); if (fam) fam.value = 'all';
    const cSel = $('#countrySelect'); if (cSel) cSel.value = 'all';
    const exSel = $('#excludeCountrySelect'); if (exSel) exSel.value = '';
  }

  function syncFiltersUi() {
    const f = S.filters;
    // Work Mode
    const wmSeg = $('#workModeSeg');
    if (wmSeg) {
      $$('button[data-mode]', wmSeg).forEach(b => {
        b.setAttribute('aria-pressed', String(b.dataset.mode.toLowerCase() === f.workMode.toLowerCase()));
      });
    }
    // Match Score
    const scoreSeg = $('#matchScoreSeg');
    if (scoreSeg) {
      $$('button[data-min-score]', scoreSeg).forEach(b => {
        b.setAttribute('aria-pressed', String(Number(b.dataset.minScore) === f.minScore));
      });
    }
    // Big Tech & Startups
    const famSeg = $('#famousSeg');
    if (famSeg) {
      $$('button[data-famous]', famSeg).forEach(b => {
        b.setAttribute('aria-pressed', String(b.dataset.famous === f.famousMode));
      });
    }
    // Country quick seg
    const cqSeg = $('#countryQuickSeg');
    if (cqSeg) {
      $$('button[data-country]', cqSeg).forEach(b => {
        b.setAttribute('aria-pressed', String(b.dataset.country.toLowerCase() === f.country.toLowerCase()));
      });
    }
    const cSel = $('#countrySelect');
    if (cSel) cSel.value = f.country;

    // Seniority
    const senSeg = $('#senioritySeg');
    if (senSeg) {
      $$('button[data-sen]', senSeg).forEach(b => {
        b.setAttribute('aria-pressed', String(b.dataset.sen === f.seniority));
      });
    }
    // Salary
    const salSeg = $('#salarySeg');
    if (salSeg) {
      $$('button[data-sal]', salSeg).forEach(b => {
        b.setAttribute('aria-pressed', String(b.dataset.sal === f.salaryTier));
      });
    }
    // Freshness
    const freshSeg = $('#freshnessSeg');
    if (freshSeg) {
      $$('button[data-days]', freshSeg).forEach(b => {
        b.setAttribute('aria-pressed', String(Number(b.dataset.days) === f.freshnessDays));
      });
    }
    // Flags
    const btnAts = $('#btnFlagDirectAts');
    if (btnAts) btnAts.classList.toggle('is-active', f.directAtsOnly);
    const btnApp = $('#btnFlagHideApplied');
    if (btnApp) btnApp.classList.toggle('is-active', f.hideApplied);
    const btnSave = $('#btnFlagSavedOnly');
    if (btnSave) btnSave.classList.toggle('is-active', f.savedOnly);

    renderExcludedTags();
    syncFamousUi();
  }

  function applySort() {
    const how = val('sortResultsBy') || 'ranked';
    const pool = (S.allJobs && S.allJobs.length) ? S.allJobs.slice() : (S.jobsRanked || []).slice();
    if (how === 'score_desc') pool.sort((a, b) => (b.score || 0) - (a.score || 0));
    else if (how === 'salary_desc') pool.sort((a, b) => (jobAnnualSalaryMax(b) || 0) - (jobAnnualSalaryMax(a) || 0) || (b.score || 0) - (a.score || 0));
    else if (how === 'date_desc') pool.sort((a, b) => String(b.posted_at || '').localeCompare(String(a.posted_at || '')));
    else if (how === 'company_asc') pool.sort((a, b) => String(a.company || '').localeCompare(String(b.company || '')));
    else pool.sort((a, b) => (b.opportunity_score || 0) - (a.opportunity_score || 0) || (b.score || 0) - (a.score || 0));
    S.jobsRanked = pool;
    S.jobs = filteredJobs();
  }

  function filterAndRender() {
    applySort();
    syncFiltersUi();
    updateFacetCounts();
    renderActiveFilterTags();
    const currentList = S.jobs || [];
    const keep = currentList.find(j => jobKey(j) === S.selectedKey);
    S.selectedKey = keep ? jobKey(keep) : (!isNarrow() && currentList[0] ? jobKey(currentList[0]) : null);
    renderResults();
  }

  function sourceCounts() {
    const srcs = (S.searchMeta && S.searchMeta.sources) || [];
    const active = srcs.filter(s => s.state !== 'disabled');
    const ok = active.filter(s => s.state === 'ok' || s.state === 'cached').length;
    return { total: active.length, ok, srcs };
  }

  function renderResults() {
    stopSearchProgressAnimation();
    const stage = $('#searchProgressStage');
    if (stage) stage.hidden = true;
    const split = $('#searchSplit');
    if (split) split.hidden = false;
    const resultsMeta = $('#resultsMeta');
    if (resultsMeta) resultsMeta.hidden = false;
    const tools = $('#resultsTools');
    if (tools) tools.hidden = false;

    // Update last search timestamp badge
    const lastBadge = $('#lastSearchBadge');
    if (lastBadge && S.lastSearchTime) {
      lastBadge.textContent = `Last searched ${formatTimeSince(S.lastSearchTime)}`;
      lastBadge.hidden = false;
    }

    const meta = S.searchMeta || {};
    const n = filteredJobs().length;
    const totalAll = (S.allJobs && S.allJobs.length) || n;
    const typed = val('searchQuery').trim();
    const forWhat = !typed && meta.query ? ` <small>for ${esc(meta.query)}, based on your resume</small>` : '';
    let filterBadge = '';
    if (S.filters.famousMode === 'hide') {
      filterBadge = ` <span class="chip chip-outline chip-sm" style="font-size:11.5px;padding:1px 8px;margin-left:6px;" title="Filtered out Big Tech & prominent AI companies">No Big Tech</span>`;
    } else if (S.filters.famousMode === 'only') {
      filterBadge = ` <span class="chip chip-famous chip-sm" style="font-size:11.5px;padding:1px 8px;margin-left:6px;" title="Only showing Big Tech & prominent AI companies">Big Tech Only</span>`;
    }
    const filterSub = n !== totalAll ? ` <small class="text-muted">(${n} of ${totalAll} match current filters)</small>` : '';
    $('#resultsSummary').innerHTML = n ? `${n} job${n === 1 ? '' : 's'}${forWhat}${filterSub}${filterBadge}` : `No jobs found${filterSub}${filterBadge}`;

    // Update fallback notice banner if present
    const fallbackBanner = $('#fallbackBanner');
    if (fallbackBanner) {
      if (meta.fallback_notice) {
        fallbackBanner.innerHTML = `${ico('pin')}<span>${esc(meta.fallback_notice)}</span>`;
        fallbackBanner.hidden = false;
      } else {
        fallbackBanner.hidden = true;
      }
    }

    const { total, ok, srcs } = sourceCounts();
    const toggle = $('#sourceToggle');
    toggle.hidden = !total;
    toggle.textContent = `Sources: ${ok} of ${total} answered`;
    $('#sourcePanel').innerHTML = srcs.map(s => {
      const good = s.state === 'ok' || s.state === 'cached';
      const bad = ['failed', 'timeout', 'paused', 'stale'].includes(s.state);
      const note = good ? `${s.count} job${s.count === 1 ? '' : 's'}${s.state === 'cached' ? ', cached' : ''}` : s.state === 'disabled' ? 'off' : s.state;
      return `<div class="src-row" title="${esc(s.error || '')}"><span class="dot ${good ? 'dot-ok' : bad ? 'dot-bad' : ''}"></span><b>${esc(s.source)}</b><em>${esc(note)}</em></div>`;
    }).join('');

    renderList();
    renderDetail();
  }

  function renderList() {
    const list = $('#jobList');
    const meta = S.searchMeta || {};
    const jobs = filteredJobs();
    const totalAll = (S.allJobs && S.allJobs.length) || 0;

    if (!jobs.length) {
      const { total, ok } = sourceCounts();
      const allFailed = total > 0 && ok === 0;

      // Case 1: Search returned jobs, but client filters eliminated all of them!
      if (totalAll > 0 && !allFailed) {
        list.innerHTML = `<div class="empty">${ico('search')}
          <h3>No jobs match active filters</h3>
          <p>Found <strong>${totalAll} job${totalAll === 1 ? '' : 's'}</strong> for this search, but your current filters excluded all of them.</p>
          <div class="empty-actions">
            <button type="button" class="btn btn-primary" data-action="clear-filters">Show all ${totalAll} jobs</button>
            ${S.filters.minScore > 0 ? '<button type="button" class="btn btn-secondary" data-action="relax-score">Show any match score</button>' : ''}
          </div>
        </div>`;
        return;
      }

      // Case 2: Zero results from search sources
      const qText = val('searchQuery').trim() || meta.query || 'this search';
      const locText = val('searchLocation').trim();

      list.innerHTML = `<div class="empty">${ico(allFailed ? 'alert' : 'search')}
        <h3>${allFailed ? 'No source answered' : `No postings found for "${esc(qText)}"`}</h3>
        <p>${allFailed ? 'Check your internet connection, then search again. Open Sources above to see what failed.' : (locText ? `No listings matched in "${esc(locText)}". Expand to Worldwide Remote to view jobs you can work from anywhere.` : 'Try searching for related job titles or refreshing live sources.')}</p>
        <div class="empty-actions">
          ${locText && locText.toLowerCase() !== 'worldwide' ? '<button type="button" class="btn btn-primary" data-action="search-worldwide-remote">Search Worldwide Remote</button>' : ''}
          <button type="button" class="btn btn-secondary" data-action="search-again">Refresh live sources</button>
          <button type="button" class="btn btn-ghost" data-action="clear-search">Clear search</button>
        </div>
        <div class="empty-suggestions">
          <span>Suggested titles:</span>
          <button type="button" class="empty-suggestion-btn" data-action="suggest-search" data-q="Software Engineer">Software Engineer</button>
          <button type="button" class="empty-suggestion-btn" data-action="suggest-search" data-q="Full Stack Developer">Full Stack</button>
          <button type="button" class="empty-suggestion-btn" data-action="suggest-search" data-q="Backend Engineer">Backend</button>
          <button type="button" class="empty-suggestion-btn" data-action="suggest-search" data-q="Frontend Developer">Frontend</button>
        </div>
      </div>`;
      return;
    }
    const showScore = !meta.profile_empty;
    list.innerHTML = jobs.map(j => {
      const key = jobKey(j);
      const required = Object.keys(j.required_skills || {}).length;
      const matched = (j.matched_skills || []).length;
      const isDirectAts = j.source_kind === 'Direct employer ATS' || String(j.source_tier || '').startsWith('Direct');
      const isFamous = isFamousJob(j);
      return `<button type="button" class="job-item${key === S.selectedKey ? ' is-selected' : ''}" data-action="job-select" data-key="${esc(key)}">
        <span class="job-item-title">${esc(cleanTitle(j.title))}</span>
        <span class="job-item-company">${esc(j.company)}</span>
        ${showScore ? ring(j.score) : ''}
        <span class="job-item-meta">
          <span>${ico('pin')}${esc(j.location || 'Remote')}</span>
          ${j.work_mode ? `<span>${ico('briefcase')}${esc(j.work_mode)}</span>` : ''}
          ${j.salary ? `<span>${esc(j.salary)}</span>` : ''}
          ${showScore && required ? `<span>${matched} of ${required} skills</span>` : ''}
          ${isFamous ? '<span class="chip chip-famous" title="Recognized Big Tech & Prominent AI company">Big Tech</span>' : ''}
          ${isDirectAts ? `<span class="chip chip-ok" title="Direct employer careers board">${ico('shield')}Direct ATS</span>` : ''}
          ${j.score >= 85 ? '<span class="chip chip-ok">Top Match</span>' : ''}
          ${j.is_new ? '<span class="chip chip-info">New</span>' : ''}
          ${j.is_sample ? '<span class="chip chip-warn">Sample</span>' : ''}
          ${jobSources(j).length > 1 ? `<span>${jobSources(j).length} sources</span>` : ''}
        </span>
      </button>`;
    }).join('');
  }

  const selectedJob = () => S.jobs.find(j => jobKey(j) === S.selectedKey) || null;
  const savedApp = j => S.applications.find(a => (a.job_id && j.id && a.job_id === j.id) ||
    (String(a.title).toLowerCase() === String(j.title).toLowerCase() && String(a.company).toLowerCase() === String(j.company).toLowerCase()));

  function renderDetail() {
    const el = $('#jobDetail');
    const j = selectedJob();
    if (!j) {
      el.innerHTML = S.jobs.length ? `<div class="empty" style="border:0">${ico('briefcase')}<h3>Pick a job</h3><p>Select a job on the left to see why it fits and what to do next.</p></div>` : '';
      return;
    }
    const showScore = !(S.searchMeta && S.searchMeta.profile_empty);
    const score = Math.round(j.score || 0);
    const sources = jobSources(j).filter(s => s.url);
    const apply = bestApplyUrl(j);
    const matched = j.matched_skills || [], missing = j.missing_skills || [];
    const desc = String(j.description || '');
    const posted = j.posted_at ? timeAgo(j.posted_at) : '';
    const saved = savedApp(j);
    const isDirectAts = j.source_kind === 'Direct employer ATS' || String(j.source_tier || '').startsWith('Direct');

    el.innerHTML = `
      <button type="button" class="btn btn-ghost btn-sm detail-close" data-action="detail-close">${ico('back')}Back to results</button>
      <div class="detail-body">
        <div class="detail-top">
          <div>
            <h2 class="detail-title">${esc(cleanTitle(j.title))}</h2>
            <p class="detail-company">${esc(j.company)} ${isFamousJob(j) ? `<span class="chip chip-famous" title="Recognized Big Tech & Prominent AI company">Big Tech</span>` : ''} ${isDirectAts ? `<span class="chip chip-ok" title="Direct employer ATS">${ico('shield')}Direct ATS</span>` : ''}</p>
          </div>
          ${showScore ? ring(score, true) : ''}
        </div>
        <div class="detail-facts">
          <span>${ico('pin')}${esc(j.location || 'Remote')}</span>
          ${j.work_mode ? `<span>${ico('briefcase')}${esc(j.work_mode)}</span>` : ''}
          ${j.salary ? `<span>${esc(j.salary)}</span>` : ''}
          ${posted ? `<span>${ico('clock')}Posted ${esc(posted)}</span>` : ''}
        </div>
        <div class="detail-actions">
        <button type="button" class="btn btn-primary" data-action="job-strategy">${ico('bolt')}AI Strategy</button>
        <button type="button" class="btn btn-secondary" data-action="job-tailor">${ico('file')}Tailor resume</button>
        <button type="button" class="btn btn-secondary" data-action="job-save" ${saved ? 'disabled' : ''}>${ico('bookmark')}${saved ? 'Saved' : 'Save'}</button>
        ${apply ? `<a class="btn btn-secondary" href="${esc(apply)}" target="_blank" rel="noopener noreferrer">${ico('external')}Apply</a>` : ''}
        <button type="button" class="btn btn-ghost" data-action="job-hunt" title="Tailor your resume, write a cover letter and prep notes, then save it all to Applications">${ico('bolt')}Prepare everything</button>
        </div>

        ${showScore ? `<div class="detail-block"><h3>Why it fits</h3>
          <div class="fit-box">
            <p><span class="chip ${score >= 85 ? 'chip-ok' : score >= 70 ? 'chip-info' : score >= 50 ? 'chip-warn' : ''}">${tierOf(score).label}</span></p>
            <p>${esc(j.rationale || '')}</p>
            ${matched.length ? `<div class="fit-row"><strong>You have</strong>${matched.map(s => `<span class="chip chip-ok">${esc(s)}</span>`).join('')}</div>` : ''}
            ${missing.length ? `<div class="fit-row"><strong>Missing</strong>${missing.map(s => `<span class="chip chip-warn">${esc(s)}</span>`).join('')}</div>` : ''}
          </div></div>` : ''}

        ${desc ? `<div class="detail-block"><h3>About the role</h3><p class="desc">${esc(desc.length > 3000 ? desc.slice(0, 3000) + '...' : desc)}</p></div>` : ''}

        ${sources.length ? `<div class="detail-block"><h3>${sources.length > 1 ? `Posted on ${sources.length} sites` : 'Where to apply'}</h3>
          <div class="apply-links">${sources.map(s => `<a class="chip chip-outline" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.source)}${isDirect(s) ? ', company site' : ''}${ico('external')}</a>`).join('')}</div></div>` : ''}

        <p class="credit">Source: ${esc(j.source_credit || j.source || '')}</p>
      </div>`;
  }

  function selectJob(key) {
    S.selectedKey = key;
    $$('#jobList .job-item').forEach(b => b.classList.toggle('is-selected', b.dataset.key === key));
    renderDetail();
    if (isNarrow()) {
      const d = $('#jobDetail');
      d.classList.add('is-open'); d.scrollTop = 0;
      document.body.style.overflow = 'hidden';
    }
  }
  function closeDetailSheet() {
    const d = $('#jobDetail');
    if (d) d.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  async function saveJob(job) {
    if (!job) return;
    if (savedApp(job)) { toast('Already in Applications'); return; }
    try {
      await api('/api/applications', { method: 'POST', body: {
        job_id: job.id, company: job.company, title: job.title, location: job.location, salary: job.salary,
        status: 'saved', notes: 'Saved from search.', follow_up_date: isoDay(5),
        sources: jobSources(job), job_data: job
      } });
      await loadApplications();
      toast(`Saved ${job.title}`);
      if (S.view === 'jobs') renderDetail();
      if (S.view === 'job') renderWsHeader();
    } catch (err) { toast('Could not save: ' + err.message, 'error'); }
  }

  async function prepareEverything(job) {
    if (!job) return;
    if (S.profileEmpty) { toast('Add your resume first.', 'error'); go('resume'); return; }
    toast(`Preparing a package for ${job.company}`);
    try {
      await api('/api/auto-hunt', { method: 'POST', body: { job } });
      await loadApplications();
      toast('Package ready. Review it in Applications, then mark it Applied after you submit.');
      go('applications');
    } catch (err) { toast('Could not prepare: ' + err.message, 'error'); }
  }

  // ------------------------------------------------------- job workspace
  function resetWorkspaceData() {
    const w = S.ws;
    w.refinement = null; w.decisions = {}; w.ats = null; w.atsFresh = false; w.strategy = null; w.gaps = null; w.cover = {}; w.prep = null;
  }

  function openWorkspace(job, tab = 'strategy', from = S.view) {
    if (!job) return;
    if (S.profileEmpty) { toast('Add your resume first. Tailoring needs it.', 'error'); go('resume'); return; }
    if (S.dirty) toast('You have unsaved profile changes. Tailoring uses your last saved profile.');
    const key = jobKey(job);
    if (key !== S.ws.key) resetWorkspaceData();
    S.ws.job = job; S.ws.key = key; S.ws.showUnchanged = false;
    if (from !== 'job') S.ws.from = from;
    closeDetailSheet();
    go('job', tab);
  }

  function renderWsHeader() {
    const w = S.ws, j = w.job;
    if (!j) return;
    $('#wsTitle').textContent = cleanTitle(j.title) || 'Job';
    const loc = String(j.location || '');
    $('#wsMeta').textContent = [j.company, loc, loc.toLowerCase().includes(String(j.work_mode || '').toLowerCase()) ? '' : j.work_mode, j.salary].filter(Boolean).join(', ');
    const sc = $('#wsScore');
    const showScore = j.score !== undefined && !(S.searchMeta && S.searchMeta.profile_empty);
    sc.hidden = !showScore;
    if (showScore) sc.outerHTML = ring(j.score).replace('class="', 'id="wsScore" class="');
    const url = bestApplyUrl(j), a = $('#wsApply');
    a.hidden = !url; if (url) a.href = url;
    const saved = savedApp(j);
    const sb = $('[data-action="ws-save"]');
    sb.disabled = !!saved;
    sb.innerHTML = `${ico('bookmark')}${saved ? 'Saved' : 'Save'}`;
    $('#wsBackLabel').textContent = w.from === 'applications' ? 'Back to applications' : w.from === 'digest' ? 'Back to digest' : 'Back to jobs';
    if (w.ats) { const c = $('#wsAtsCount'); c.hidden = false; c.textContent = `${w.ats.ats_score}`; } else $('#wsAtsCount').hidden = true;
  }

  async function renderWsTab() {
    const w = S.ws;
    if (!w.job) return;
    $$('#wsTabs [data-ws-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.wsTab === w.tab)));
    const seq = ++w.seq, panel = $('#wsPanel');
    panel.innerHTML = skeletons(2);
    try {
      if (w.tab === 'strategy') { await ensureStrategy(); if (seq === w.seq) renderStrategyTab(); }
      else if (w.tab === 'resume') { await ensureRefinement(); if (seq === w.seq) renderResumeTab(); }
      else if (w.tab === 'ats') { await ensureAts(); if (seq === w.seq) renderAtsTab(); }
      else if (w.tab === 'gaps') { await ensureGaps(); if (seq === w.seq) renderGapsTab(); }
      else if (w.tab === 'cover') { await ensureCover(); if (seq === w.seq) renderCoverTab(); }
      else if (w.tab === 'prep') { await ensurePrep(); if (seq === w.seq) renderPrepTab(); }
      if (seq === w.seq) renderWsHeader();
    } catch (err) {
      if (seq !== w.seq) return;
      panel.innerHTML = `<div class="empty">${ico('alert')}<h3>This tab did not load</h3><p>${esc(err.message)}</p><div class="empty-actions"><button type="button" class="btn btn-primary" data-action="ws-retry">Try again</button></div></div>`;
    }
  }

  async function ensureStrategy() {
    const w = S.ws;
    if (w.strategy && w.strategy.job_id === w.job.id) return;
    const data = await api('/api/ai-strategy', { method: 'POST', body: { job: w.job } });
    w.strategy = data;
  }

  function renderStrategyTab() {
    const w = S.ws, st = w.strategy;
    if (!st) return;
    const j = w.job;
    const score = Math.round(st.fit_score || j.score || 0);
    const flags = st.posting_health_flags || [];
    const bridges = st.skill_bridges || [];
    const tracks = st.talking_tracks || [];
    const plan = st.action_plan || [];

    $('#wsPanel').innerHTML = `
      <div class="strategy-overview">
        <div class="guardrail-verified-banner">
          <div>${ico('shield')} <strong>100% Grounded Intelligence</strong></div>
          <small>Verified against your master profile. Zero hallucinations.</small>
        </div>

        <div class="strategy-card">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:16px;">
            <div>
              <h3>${ico('bolt')}Role Alignment &amp; Fit Rationale</h3>
              <p style="margin-bottom:12px">${esc(st.executive_summary || 'Analysis complete.')}</p>
              ${st.matched_skills && st.matched_skills.length ? `
                <div class="fit-row" style="margin-top:10px">
                  <strong>Direct Matches:</strong>
                  ${st.matched_skills.map(s => `<span class="chip chip-ok">${esc(s)}</span>`).join('')}
                </div>` : ''}
              ${st.missing_skills && st.missing_skills.length ? `
                <div class="fit-row" style="margin-top:8px">
                  <strong>Gaps to Address:</strong>
                  ${st.missing_skills.map(s => `<span class="chip chip-warn">${esc(s)}</span>`).join('')}
                </div>` : ''}
            </div>
            ${ring(score, true)}
          </div>
        </div>

        ${bridges.length ? `
        <div class="strategy-card">
          <h3>${ico('refresh')}Transferable Skill Bridges</h3>
          <p>These skills aren't listed verbatim on your resume, but your existing tech stack bridges the gap:</p>
          <div class="bridge-list">
            ${bridges.map(b => `
              <div class="bridge-item">
                <div class="bridge-item-head">
                  <strong>Requires ${esc(b.required_skill)}</strong>
                  <span>&larr; Bridge from ${esc(b.candidate_bridge)}</span>
                </div>
                <p>${esc(b.rationale)}</p>
              </div>
            `).join('')}
          </div>
        </div>` : ''}

        ${tracks.length ? `
        <div class="strategy-card">
          <h3>${ico('briefcase')}Interview Talking Tracks</h3>
          <p>How to speak honestly and confidently about stack requirements in technical screens:</p>
          <div class="talking-tracks">
            ${tracks.map(t => `
              <div class="track-item">
                <b>Topic: ${esc(t.topic)}</b>
                <p>${esc(t.strategy)}</p>
              </div>
            `).join('')}
          </div>
        </div>` : ''}

        <div class="strategy-card">
          <h3>${ico('shield')}Posting Health &amp; Transparency Audit</h3>
          <div class="health-flags">
            ${flags.map(f => `
              <div class="flag-item flag-${esc(f.type || 'info')}">
                <b>${esc(f.label)}</b>
                <span>${esc(f.text)}</span>
              </div>
            `).join('')}
          </div>
        </div>

        <div class="strategy-card">
          <h3>${ico('check')}Tactical Application Plan</h3>
          <ol class="action-plan">
            ${plan.map((p, idx) => `
              <li>
                <span class="action-plan-num">${idx + 1}</span>
                <span>${esc(p)}</span>
              </li>
            `).join('')}
          </ol>
        </div>
      </div>
    `;
  }

  async function copyAtsBullets() {
    const r = effectiveResume();
    const bullets = (r.experience || []).flatMap(e => (e.bullets || []).map(b => `• ${b}`));
    if (!bullets.length) { toast('No bullets to copy', 'error'); return; }
    const text = bullets.join('\n');
    try {
      await navigator.clipboard.writeText(text);
      toast('Copied all ATS bullets to clipboard');
    } catch (e) {
      toast('Clipboard blocked. Please copy manually.', 'error');
    }
  }

  async function ensureRefinement() {
    const w = S.ws;
    if (w.refinement) return;
    const data = await api('/api/refine', { method: 'POST', body: { job: w.job } });
    w.refinement = data; w.decisions = {};
    (data.diff_items || []).forEach(d => { w.decisions[d.id] = 'pending'; });
  }

  function effectiveResume() {
    const base = JSON.parse(JSON.stringify(S.profile || {}));
    const w = S.ws, ref = w.refinement;
    if (!ref) return base;
    const item = id => (ref.diff_items || []).find(d => d.id === id);
    const sum = item('diff_summary'), sk = item('diff_skills');
    if (w.decisions.diff_summary === 'accepted' && sum) base.summary = sum.proposed;
    if (w.decisions.diff_skills === 'accepted' && sk) {
      base.skills = sk.edited ? sk.proposed.split(',').map(s => s.trim()).filter(Boolean) : (ref.tailored_skills || base.skills);
    }
    (base.experience || []).forEach((exp, ei) => (exp.bullets || []).forEach((_, bi) => {
      const d = item(`diff_exp_${ei}_${bi}`);
      if (d && w.decisions[d.id] === 'accepted') exp.bullets[bi] = d.proposed;
    }));
    return base;
  }

  const changedItems = () => ((S.ws.refinement && S.ws.refinement.diff_items) || []).filter(d => d.status !== 'unchanged');

  function diffStatsHtml() {
    const items = changedItems(), d = S.ws.decisions;
    const a = items.filter(x => d[x.id] === 'accepted').length, r = items.filter(x => d[x.id] === 'rejected').length;
    return `${items.length} suggested change${items.length === 1 ? '' : 's'}<span>, ${a} accepted, ${r} kept original</span>`;
  }

  function diffCardHtml(d) {
    const dec = S.ws.decisions[d.id] || 'pending';
    const acc = dec === 'accepted', rej = dec === 'rejected';
    const tag = d.status === 'reordered' ? ['chip-info', 'Reordered'] : d.status === 'unchanged' ? ['', 'Unchanged'] : ['chip-ok', 'Reworded'];
    return `<article class="diff-card${acc ? ' is-accepted' : ''}${rej ? ' is-rejected' : ''}" data-diff="${esc(d.id)}">
      <div class="diff-card-head"><strong>${esc(d.label || d.section)}</strong><span class="chip ${tag[0]}">${tag[1]}</span></div>
      <div class="diff-cols">
        <div class="diff-col"><span class="diff-col-label">Your resume</span>${esc(d.original)}</div>
        <div class="diff-col prop"><span class="diff-col-label">Tailored, click to edit</span><div class="editable" contenteditable="true" role="textbox" aria-label="Tailored text" data-id="${esc(d.id)}">${esc(d.proposed)}</div></div>
      </div>
      ${d.rationale ? `<p class="diff-why">${esc(d.rationale)}</p>` : ''}
      <div class="diff-actions">
        <button type="button" class="btn btn-sm ${acc ? 'btn-primary' : 'btn-secondary'}" data-action="diff-accept" data-id="${esc(d.id)}" aria-pressed="${acc}">${ico('check')}${acc ? 'Accepted' : 'Accept'}</button>
        <button type="button" class="btn btn-sm ${rej ? 'btn-primary' : 'btn-secondary'}" data-action="diff-reject" data-id="${esc(d.id)}" aria-pressed="${rej}">${rej ? 'Kept original' : 'Keep original'}</button>
      </div>
    </article>`;
  }

  function renderResumeTab() {
    const w = S.ws, ref = w.refinement;
    const all = ref.diff_items || [];
    const changed = all.filter(d => d.status !== 'unchanged');
    const unchanged = all.filter(d => d.status === 'unchanged');
    $('#wsPanel').innerHTML = `
      <div class="tailor-banner">
        <div><strong>Tailor this resume in one click</strong>
          <p>Reorders your skills and bullets, and mirrors the posting's wording for skills you already list. Every fact comes from your resume. Your master resume stays untouched.</p></div>
        <button type="button" class="btn btn-primary" data-action="auto-tailor">${ico('bolt')}Tailor automatically</button>
      </div>
      <div class="ats-copy-banner">
        <div><strong>${ico('shield')} 100% Grounded Tailoring</strong> &bull; <small>Zero Hallucinations. Every tailored point mirrors verified resume facts.</small></div>
        <button type="button" class="btn btn-secondary btn-sm" data-action="bullets-copy">${ico('copy')}Copy Plain ATS Bullets</button>
      </div>
      <div class="diff-layout">
        <div>
          <div class="diff-bar">
            <div class="diff-bar-stats" id="diffStats">${diffStatsHtml()}</div>
            <div class="head-actions">
              <button type="button" class="btn btn-secondary btn-sm" data-action="diff-accept-all">Accept all</button>
              <button type="button" class="btn btn-ghost btn-sm" data-action="diff-reset">Keep all original</button>
            </div>
          </div>
          <div id="diffList">${changed.length ? changed.map(diffCardHtml).join('') : '<div class="empty"><h3>Nothing to change</h3><p>Your resume already matches this posting well.</p></div>'}</div>
          ${unchanged.length ? `<button type="button" class="link-btn diff-toggle" data-action="diff-unchanged-toggle">${w.showUnchanged ? 'Hide' : 'Show'} ${unchanged.length} unchanged bullet${unchanged.length === 1 ? '' : 's'}</button>
            ${w.showUnchanged ? unchanged.map(diffCardHtml).join('') : ''}` : ''}
        </div>
        <aside class="card preview-card">
          <div class="preview-head">
            <h3>Resume preview</h3>
            <div class="head-actions">
              <button type="button" class="btn btn-ghost btn-sm" data-action="export" data-fmt="txt">${ico('copy')}Copy text</button>
              <button type="button" class="btn btn-secondary btn-sm" data-action="export" data-fmt="docx">${ico('download')}Word</button>
              <button type="button" class="btn btn-secondary btn-sm" data-action="export" data-fmt="pdf">${ico('download')}PDF</button>
            </div>
          </div>
          <div class="preview-scroll"><div class="paper" id="atsPaperPreview"></div></div>
        </aside>
      </div>`;
    renderPreview();
  }

  function renderPreview() {
    const box = $('#atsPaperPreview');
    if (!box) return;
    const r = effectiveResume();
    box.innerHTML = `
      <h2>${esc(r.name || 'Your name')}</h2>
      <div class="contact">${[r.email, r.phone, r.location].filter(Boolean).map(esc).join(', ')}${(r.linkedin || r.github) ? '<br>' + [r.linkedin, r.github].filter(Boolean).map(esc).join(', ') : ''}</div>
      ${r.summary ? `<div class="sec">Summary</div><p>${esc(r.summary)}</p>` : ''}
      ${(r.skills || []).length ? `<div class="sec">Skills</div><p>${(r.skills || []).map(esc).join(', ')}</p>` : ''}
      ${(r.experience || []).length ? '<div class="sec">Experience</div>' : ''}
      ${(r.experience || []).map(x => `<div class="job-block">
        <div class="job-line"><strong>${esc(x.role)}, ${esc(x.company)}</strong><span>${esc(x.start_date)} to ${esc(x.end_date)}</span></div>
        ${x.location ? `<div class="loc">${esc(x.location)}</div>` : ''}
        <ul>${(x.bullets || []).map(b => `<li>${esc(b)}</li>`).join('')}</ul></div>`).join('')}
      ${(r.education || []).length ? '<div class="sec">Education</div>' : ''}
      ${(r.education || []).map(e => `<p><strong>${esc(e.degree)}</strong>, ${esc(e.institution)}${e.graduation_year ? ` (${esc(e.graduation_year)})` : ''}</p>`).join('')}`;
  }

  function afterDiffChange(id) {
    S.ws.atsFresh = false;
    const d = (S.ws.refinement.diff_items || []).find(x => x.id === id);
    const card = id && $(`[data-diff="${CSS.escape(id)}"]`);
    if (card && d) card.outerHTML = diffCardHtml(d);
    const stats = $('#diffStats'); if (stats) stats.innerHTML = diffStatsHtml();
    renderPreview();
  }

  function setDiff(id, decision) {
    const w = S.ws;
    w.decisions[id] = w.decisions[id] === decision ? 'pending' : decision;
    afterDiffChange(id);
  }
  function setAllDiffs(decision) {
    changedItems().forEach(d => { S.ws.decisions[d.id] = decision; });
    S.ws.atsFresh = false;
    renderResumeTab();
  }
  function manualEdit(el) {
    const d = (S.ws.refinement.diff_items || []).find(x => x.id === el.dataset.id);
    const text = el.innerText.trim();
    if (!d || text === String(d.proposed).trim()) return;
    d.proposed = text; d.edited = true;
    S.ws.decisions[d.id] = 'accepted';
    afterDiffChange(d.id);
  }

  async function autoTailor() {
    const w = S.ws, btns = $$('[data-action="auto-tailor"]');
    btns.forEach(b => { b.disabled = true; });
    try {
      const res = await api('/api/auto-tailor', { method: 'POST', body: { job: w.job } });
      w.refinement = res.refinement; w.decisions = {};
      (res.refinement.diff_items || []).forEach(d => { w.decisions[d.id] = 'accepted'; });
      w.ats = res.ats_audit; w.atsFresh = true;
      toast(`Tailored. ATS score is now ${res.ats_audit.ats_score}%${res.boost > 0 ? `, up ${res.boost} points` : ''}.`);
      if (w.tab === 'ats') renderAtsTab(); else renderResumeTab();
      renderWsHeader();
    } catch (err) { toast('Could not tailor: ' + err.message, 'error'); }
    finally { btns.forEach(b => { b.disabled = false; }); }
  }

  async function exportResume(fmt) {
    try {
      const res = await api('/api/export', { method: 'POST', body: { format: fmt, resume: effectiveResume() } });
      if (fmt === 'txt') {
        try { await navigator.clipboard.writeText(res.content); toast('Plain text resume copied'); }
        catch (e) { toast('Your browser blocked copying. Use Word or PDF instead.', 'error'); }
        return;
      }
      const bin = atob(res.content_base64), arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([arr], { type: res.mime }));
      const a = document.createElement('a');
      a.href = url; a.download = res.filename; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast(`Downloaded ${res.filename}`);
    } catch (err) { toast('Export failed: ' + err.message, 'error'); }
  }

  // ATS
  async function ensureAts() {
    const w = S.ws;
    if (w.ats && w.atsFresh) return;
    w.ats = await api('/api/ats-audit', { method: 'POST', body: { job: w.job, resume: effectiveResume() } });
    w.atsFresh = true;
  }

  function renderAtsTab() {
    const a = S.ws.ats, b = a.breakdown || {};
    const score = a.ats_score || 0;
    const head = score >= 90 ? ['Ready to submit', 'Your resume parses cleanly and covers the posting well.']
      : score >= 75 ? ['Passes, with room to improve', 'It will pass a first parse. More measurable results and posting keywords would raise it.']
      : ['Needs work', 'Key posting words or structure are missing. Tailor automatically to fix the common gaps.'];
    const bars = [
      ['Posting keywords', b.keyword_score, 40], ['Structure and contact', b.structure_score, 20],
      ['Measurable results', b.metrics_score, 20], ['Action verbs', b.verbs_score, 10], ['Length', b.length_score, 10]
    ];
    const kw = a.top_keywords_density || [];
    const checks = a.checklist || [];
    const recs = a.recommendations || [];
    $('#wsPanel').innerHTML = `
      <div class="card ats-top">
        <div class="ats-score">
          <div class="score-ring ${tierOf(score).cls}" style="--pct:${score}" role="img" aria-label="ATS score ${score} out of 100"><span>${score}</span></div>
          <div>
            <h2>${head[0]}, grade ${esc(a.grade || '')}</h2>
            <p>${head[1]}</p>
            <div class="actions">
              <button type="button" class="btn btn-primary btn-sm" data-action="auto-tailor">${ico('bolt')}Tailor automatically</button>
              <button type="button" class="btn btn-secondary btn-sm" data-action="export" data-fmt="pdf">${ico('download')}Download PDF</button>
            </div>
          </div>
        </div>
        <div>${bars.map(([n, v, max]) => `<div class="bar-row"><span>${n}</span><div class="bar" role="img" aria-label="${n}: ${v || 0} of ${max}"><i style="width:${Math.round(((v || 0) / max) * 100)}%"></i></div><b>${v || 0}/${max}</b></div>`).join('')}</div>
      </div>
      ${a.note ? `<p class="muted small" style="margin-top:10px">${esc(a.note)}</p>` : ''}
      <div class="two-col">
        <section class="card">
          <h2 class="card-title">Posting keywords</h2>
          <p class="muted small">Each keyword should appear at least once and no more than six times.</p>
          ${kw.length ? kw.map(k => {
            const st = k.status === 'missing' ? ['chip-bad', 'Missing'] : k.status === 'stuffed' ? ['chip-warn', 'Too many'] : ['chip-ok', 'Good'];
            return `<div class="kw-row"><span>${esc(k.keyword)}</span><span><span class="muted small">${k.count}x</span> <span class="chip ${st[0]}">${st[1]}</span></span></div>`;
          }).join('') : '<p class="muted">No keywords found in the posting.</p>'}
        </section>
        <section class="card">
          <h2 class="card-title">Checks</h2>
          ${checks.map(c => `<div class="check-item ${c.passed ? 'pass' : 'fail'}"><span class="check-mark">${ico(c.passed ? 'check' : 'x')}</span><div><strong>${esc(c.rule)}</strong><small>${esc(c.details)}</small></div></div>`).join('')}
          <h3 class="card-title" style="margin-top:18px">What to do next</h3>
          ${recs.length ? `<ul class="reco">${recs.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : '<p class="muted">Nothing blocks this resume. You can submit it.</p>'}
        </section>
      </div>`;
  }

  // Gaps
  async function ensureGaps() {
    if (S.ws.gaps) return;
    S.ws.gaps = await api('/api/gap-report', { method: 'POST', body: { job: S.ws.job } });
  }
  function renderGapsTab() {
    const g = S.ws.gaps;
    const matched = g.matched_skills || [], add = g.add_if_true || [], real = g.real_gaps || [];
    $('#wsPanel').innerHTML = `
      <div class="gap-stats">
        <div class="stat stat-ok"><b>${matched.length}</b><span>Skills you match</span></div>
        <div class="stat stat-info"><b>${add.length}</b><span>Worth adding if true</span></div>
        <div class="stat stat-warn"><b>${real.length}</b><span>Real gaps</span></div>
      </div>
      ${matched.length ? `<div class="card"><h2 class="card-title">You already have</h2><div class="chips" style="margin-top:8px">${matched.map(s => `<span class="chip chip-ok">${esc(s)}</span>`).join('')}</div></div>` : ''}
      <div class="two-col">
        <section class="card">
          <h2 class="card-title">Add if true</h2>
          <p class="muted small">Common tools people use but forget to list. Add one only if you really use it.</p>
          ${add.length ? add.map(i => `<div class="gap-item"><div><strong>${esc(i.skill)}</strong><span>${esc(i.advice)}</span></div><button type="button" class="btn btn-secondary btn-sm" data-action="gap-add" data-skill="${esc(i.skill)}">${ico('plus')}Add to profile</button></div>`).join('')
            : '<p class="muted" style="margin-top:12px">No small gaps found.</p>'}
        </section>
        <section class="card">
          <h2 class="card-title">Real gaps</h2>
          <p class="muted small">Do not claim these. Plan an honest answer for the interview.</p>
          ${real.length ? real.map(i => `<div class="gap-item"><div><strong>${esc(i.skill)} ${i.priority ? `<span class="chip chip-warn">${esc(i.priority)}</span>` : ''}</strong><span>${esc(i.advice)}</span></div></div>`).join('')
            : '<p class="muted" style="margin-top:12px">No major gaps found.</p>'}
        </section>
      </div>`;
  }

  // Cover letter
  async function ensureCover() {
    const w = S.ws;
    if (w.cover[w.tone] !== undefined) return;
    const data = await api('/api/cover-letter', { method: 'POST', body: { job: w.job, tone: w.tone } });
    w.cover[w.tone] = data.cover_letter || '';
  }
  function renderCoverTab() {
    const w = S.ws;
    $('#wsPanel').innerHTML = `
      <div class="card">
        <div class="letter-controls">
          <div class="segmented" role="group" aria-label="Letter tone">${TONES.map(t => `<button type="button" data-action="cover-tone" data-tone="${t.key}" aria-pressed="${t.key === w.tone}">${t.label}</button>`).join('')}</div>
          <div class="head-actions">
            <button type="button" class="btn btn-secondary btn-sm" data-action="cover-copy">${ico('copy')}Copy</button>
            <button type="button" class="btn btn-primary btn-sm" data-action="cover-save">${ico('bookmark')}Save to Applications</button>
          </div>
        </div>
        <label class="sr-only" for="coverLetterTextarea">Cover letter</label>
        <textarea id="coverLetterTextarea" class="letter" rows="16">${esc(w.cover[w.tone])}</textarea>
        <p class="muted small" style="margin-top:10px">Every fact comes from your saved resume. Edit freely before you send it.</p>
      </div>`;
  }
  async function saveCoverLetter() {
    const w = S.ws, job = w.job, text = val('coverLetterTextarea');
    const existing = savedApp(job);
    const base = existing ? Object.assign({}, existing) : {
      job_id: job.id, company: job.company, title: job.title, location: job.location, salary: job.salary,
      status: 'saved', notes: 'Cover letter saved.', follow_up_date: isoDay(5), sources: jobSources(job), job_data: job
    };
    base.cover_letter = text;
    if (w.refinement) base.tailored_resume = effectiveResume();
    try {
      await api('/api/applications', { method: 'POST', body: base });
      await loadApplications();
      renderWsHeader();
      toast('Saved to Applications');
    } catch (err) { toast('Could not save: ' + err.message, 'error'); }
  }

  // Interview prep
  async function ensurePrep() {
    if (S.ws.prep) return;
    S.ws.prep = await api('/api/interview-prep', { method: 'POST', body: { job: S.ws.job } });
  }
  function renderPrepTab() {
    const p = S.ws.prep;
    const block = (title, hint, body, open) => `<details class="prep-block" ${open ? 'open' : ''}><summary>${title}${ico('chevron')}</summary><div class="prep-body">${hint ? `<p class="muted small" style="margin-bottom:6px">${hint}</p>` : ''}${body}</div></details>`;
    const q = (a, b) => `<div class="prep-q"><strong>${a}</strong>${b ? `<p>${b}</p>` : ''}</div>`;
    $('#wsPanel').innerHTML =
      block('Behavioral questions', `Tailored to ${esc(p.company)}. Answer with Situation, Task, Action, Result.`,
        (p.behavioral_questions || []).map(x => q(esc(x.question), esc(x.tip))).join('') || '<p class="muted">None.</p>', true) +
      block('Technical deep dives', 'Based on the posting\'s main tools.',
        (p.technical_deep_dives || []).map(x => q(`${esc(x.topic)}: ${esc(x.question)}`, esc(x.talking_point))).join('') || '<p class="muted">None.</p>', false) +
      block('Your skill gaps, answered honestly', 'Never fake experience. Show how fast you learn.',
        (p.gap_talking_points || []).map(x => q(esc(x.skill), esc(x.recommended_response))).join('') || '<p class="muted">No gaps to address.</p>', false) +
      block('Questions to ask them', '',
        (p.questions_to_ask_interviewer || []).map(x => q(esc(x), '')).join('') || '<p class="muted">None.</p>', false);
  }

  // ----------------------------------------------------------- applications
  async function loadApplications() {
    try {
      const data = await api('/api/applications');
      S.applications = data.applications || [];
    } catch (err) { console.error('Applications failed:', err); }
    const n = S.applications.filter(a => a.status !== 'rejected').length;
    const badge = $('#navAppCount'); badge.hidden = !n; badge.textContent = n;
    if (S.view === 'applications') renderBoard();
  }

  function followHtml(a) {
    if (!a.follow_up_date || a.status === 'rejected' || a.status === 'saved') return '';
    const d = daysUntil(a.follow_up_date);
    if (d === null) return '';
    const late = d < 0, text = late ? `Follow up ${-d}d overdue` : d === 0 ? 'Follow up today' : `Follow up in ${d}d`;
    return `<span class="follow${late || d === 0 ? ' late' : ''}">${ico('clock')}${text}</span>`;
  }

  function renderBoard() {
    const apps = S.applications;
    const live = apps.filter(a => a.status !== 'rejected').length;
    const overdue = apps.filter(a => a.overdue).length;
    $('#appStats').textContent = apps.length
      ? `${live} in progress${overdue ? `, ${overdue} follow-up${overdue === 1 ? '' : 's'} overdue` : ''}. Drag a card or use its stage menu.`
      : 'Track every role from saved to offer.';
    const board = $('#kanbanBoard');
    if (!apps.length) {
      board.style.display = 'block';
      board.innerHTML = `<div class="empty">${ico('board')}<h3>No applications yet</h3><p>Save a job from search, or add one you found elsewhere.</p>
        <div class="empty-actions"><a class="btn btn-primary" href="#/jobs">Find jobs</a><button type="button" class="btn btn-secondary" data-action="app-add">Add application</button></div></div>`;
      return;
    }
    board.style.display = '';
    board.innerHTML = STAGES.map(st => {
      const items = apps.filter(a => (a.status || 'saved') === st.key);
      return `<section class="col" data-stage="${st.key}" aria-label="${st.label}">
        <div class="col-head"><span>${st.label}</span><span class="count">${items.length}</span></div>
        <div class="col-body">${items.length ? items.map(a => `
          <article class="kcard" draggable="true" data-id="${esc(a.id)}">
            <div class="kcard-title">${esc(cleanTitle(a.title))}</div>
            <div class="kcard-company">${esc(a.company)}</div>
            <div class="kcard-meta">${a.location ? `<span>${esc(a.location)}</span>` : ''}${a.salary ? `<span>${esc(a.salary)}</span>` : ''}</div>
            ${followHtml(a)}
            ${a.notes ? `<div class="kcard-notes">${esc(a.notes)}</div>` : ''}
            <div class="kcard-foot">
              <select aria-label="Stage for ${esc(cleanTitle(a.title))}" data-action="app-stage" data-id="${esc(a.id)}">${STAGES.map(s => `<option value="${s.key}" ${s.key === a.status ? 'selected' : ''}>${s.label}</option>`).join('')}</select>
              ${a.job_data && (a.job_data.title || a.job_data.description) ? `<button type="button" class="icon-btn" data-action="app-open" data-id="${esc(a.id)}" title="Open tailoring tools" aria-label="Open tailoring tools">${ico('file')}</button>` : ''}
              <button type="button" class="icon-btn" data-action="app-edit" data-id="${esc(a.id)}" title="Edit" aria-label="Edit ${esc(cleanTitle(a.title))}">${ico('edit')}</button>
              <button type="button" class="icon-btn" data-action="app-delete" data-id="${esc(a.id)}" title="Remove" aria-label="Remove ${esc(cleanTitle(a.title))}">${ico('trash')}</button>
            </div>
          </article>`).join('') : '<div class="col-empty">Nothing here</div>'}</div>
      </section>`;
    }).join('');
  }

  async function moveApp(id, status) {
    const app = S.applications.find(a => a.id === id);
    if (!app || app.status === status) return;
    const previous = app.status;
    app.status = status;
    renderBoard();
    try {
      await api('/api/applications', { method: 'POST', body: app });
      toast(`Moved to ${STAGES.find(s => s.key === status).label}`);
      loadApplications();
    } catch (err) {
      app.status = previous; renderBoard();
      toast('Could not move it: ' + err.message, 'error');
    }
  }

  async function deleteApp(id) {
    const app = S.applications.find(a => a.id === id);
    if (!app) return;
    if (!await confirmDialog('Remove this application?', `${cleanTitle(app.title)} at ${app.company} will leave your pipeline.`, 'Remove')) return;
    try {
      await api(`/api/applications/${encodeURIComponent(id)}`, { method: 'DELETE' });
      S.applications = S.applications.filter(a => a.id !== id);
      renderBoard(); loadApplications();
      toast('Application removed');
    } catch (err) { toast('Could not remove it: ' + err.message, 'error'); }
  }

  let editingApp = null;
  function openAppDialog(app) {
    editingApp = app || null;
    $('#appDialogTitle').textContent = app ? 'Edit application' : 'Add application';
    $('#appDialogSubmit').textContent = 'Save application';
    $('#modalCompany').value = app ? app.company : '';
    $('#modalTitle').value = app ? app.title : '';
    $('#modalLocation').value = app ? app.location : 'Remote';
    $('#modalSalary').value = app ? app.salary : '';
    $('#modalStatus').value = app ? app.status : 'applied';
    $('#modalFollowUp').value = app ? app.follow_up_date : isoDay(3);
    $('#modalNotes').value = app ? app.notes : '';
    $('#appDialog').showModal();
    $('#modalCompany').focus();
  }
  async function submitAppDialog() {
    const fields = {
      company: val('modalCompany').trim(), title: val('modalTitle').trim(), location: val('modalLocation').trim(),
      salary: val('modalSalary').trim(), status: val('modalStatus'), follow_up_date: val('modalFollowUp'), notes: val('modalNotes').trim()
    };
    try {
      await api('/api/applications', { method: 'POST', body: editingApp ? Object.assign({}, editingApp, fields) : fields });
      $('#appDialog').close();
      toast(editingApp ? 'Application updated' : 'Application added');
      await loadApplications();
    } catch (err) { toast('Could not save: ' + err.message, 'error'); }
  }

  // -------------------------------------------------------------- companies
  async function loadWatchlist() {
    try { S.watchlist = (await api('/api/watchlist')).watchlist || []; renderWatchlist(); }
    catch (err) { toast('Could not load companies: ' + err.message, 'error'); }
  }

  function renderWatchlist() {
    const grid = $('#watchlistGrid');
    $('#btnWatchCheck').hidden = !S.watchlist.length;
    if (!S.watchlist.length) {
      grid.innerHTML = `<div class="empty" style="grid-column:1/-1">${ico('building')}<h3>No companies yet</h3><p>Add a company you would love to work for. The app finds its public career page and checks it for roles that fit.</p>
        <div class="empty-actions"><button type="button" class="btn btn-primary" data-action="watch-add">Watch a company</button></div></div>`;
      return;
    }
    grid.innerHTML = S.watchlist.map(w => {
      const r = S.watchResults[w.id];
      let status;
      if (r && r.error) status = `<span class="chip chip-bad">Check failed</span> <span class="muted small">${esc(r.error)}</span>`;
      else if (r) status = `<span class="chip ${r.matches ? 'chip-ok' : ''}">${r.matches} matching of ${r.total} open</span>`;
      else if (w.last_checked) status = `<span class="muted small">Checked ${esc(timeAgo(w.last_checked))}, ${w.active_matches_count || 0} matching</span>`;
      else status = '<span class="muted small">Not checked yet</span>';
      const top = r && r.top && r.top.length ? `<ul class="wl-roles">${r.top.map(t => `<li><a href="${esc(t.url)}" target="_blank" rel="noopener noreferrer">${esc(cleanTitle(t.title))}</a><span class="chip chip-info">${Math.round(t.score)}%</span></li>`).join('')}</ul>` : '';
      return `<article class="wl-card">
        <div class="wl-name">${esc(w.company_name)}<span class="chip">${esc(w.board_type)}</span></div>
        <p class="muted small">Role keyword: ${esc(w.target_role || 'any role')}</p>
        <div>${status}</div>${top}
        <div class="wl-actions">
          <button type="button" class="btn btn-secondary btn-sm" data-action="watch-view" data-name="${esc(w.company_name)}">${ico('search')}Search roles</button>
          <button type="button" class="btn btn-ghost btn-sm" data-action="watch-remove" data-id="${esc(w.id)}" data-name="${esc(w.company_name)}">Remove</button>
        </div></article>`;
    }).join('');
  }

  async function checkWatchlist() {
    const btn = $('#btnWatchCheck');
    btn.disabled = true; btn.innerHTML = `${ico('refresh')}Checking`;
    try {
      const res = await api('/api/watchlist/check', { method: 'POST', body: {} });
      (res.results || []).forEach(r => { S.watchResults[r.id] = r; });
      await loadWatchlist();
      toast('Career pages checked');
    } catch (err) { toast('Check failed: ' + err.message, 'error'); }
    finally { btn.disabled = false; btn.innerHTML = `${ico('refresh')}Check all`; }
  }

  async function submitWatch() {
    const btn = $('#watchSubmit');
    btn.disabled = true; btn.textContent = 'Looking for the career page';
    try {
      const body = { company_name: val('wlCompanyName').trim(), board_type: val('wlAtsType'), target_role: val('wlTargetRole').trim() };
      const r = await api('/api/watchlist', { method: 'POST', body });
      $('#watchDialog').close();
      toast(`Watching ${body.company_name}${r.auto_detected ? ` on ${r.board_type}` : ''}`);
      loadWatchlist();
    } catch (err) { toast(err.message, 'error'); }
    finally { btn.disabled = false; btn.textContent = 'Watch company'; }
  }

  // ----------------------------------------------------------------- digest
  async function loadDigest() {
    const body = $('#digestBody');
    body.innerHTML = skeletons(2);
    try {
      const d = await api('/api/digest');
      $('#digestThresholdSelect').value = String(d.min_score || 75);
      $('#digestSub').textContent = `${d.date || 'Today'}. New roles that score ${d.min_score || 75}% or more.`;
      const jobs = d.digest_jobs || [];
      S.digestJobs = jobs;
      body.innerHTML = `<p class="digest-intro">${esc(d.summary || '')}</p>` + (jobs.length ? jobs.map((j, i) => `
        <div class="digest-row">
          <div><h3>${esc(cleanTitle(j.title))}</h3><p>${esc(j.company)}${j.location ? `, ${esc(j.location)}` : ''}${j.salary ? `, ${esc(j.salary)}` : ''}</p>
            ${(j.matched_skills || []).length ? `<p>Matches ${(j.matched_skills || []).slice(0, 4).map(esc).join(', ')}</p>` : ''}</div>
          <div class="side">${ring(j.score)}<button type="button" class="btn btn-primary btn-sm" data-action="digest-open" data-i="${i}">Tailor</button></div>
        </div>`).join('') : `<div class="empty" style="border:0">${ico('mail')}<h3>Nothing above the cutoff</h3><p>Lower the cutoff, or search again after you update your resume.</p></div>`);
    } catch (err) { body.innerHTML = `<div class="empty" style="border:0">${ico('alert')}<h3>The digest did not load</h3><p>${esc(err.message)}</p></div>`; }
  }

  async function changeDigestCutoff() {
    try {
      await api('/api/settings', { method: 'POST', body: { digest_min_score: val('digestThresholdSelect') } });
      loadDigest();
    } catch (err) { toast('Could not change the cutoff: ' + err.message, 'error'); }
  }

  // ---------------------------------------------------------------- privacy
  async function loadSourceHealth() {
    const box = $('#sourceHealth');
    try {
      const list = (await api('/api/sources')).sources || [];
      box.innerHTML = list.length ? list.map(s => {
        const good = s.ok_count > 0 && !!s.last_ok, bad = !good && s.fail_count > 0;
        const note = s.enabled === false ? (s.note || 'Off') : good ? `Answered ${timeAgo(s.last_ok)}` : bad ? String(s.last_error || 'Not answering').slice(0, 80) : (s.note || 'Not used yet');
        return `<div class="health-row"><span class="dot ${good ? 'dot-ok' : bad ? 'dot-bad' : ''}"></span><strong>${esc(s.source)}</strong><em>${esc(note)}</em></div>`;
      }).join('') : '<p class="muted">Run a search to see how each source responds.</p>';
    } catch (err) { box.innerHTML = `<p class="muted">${esc(err.message)}</p>`; }
  }

  async function loadAiSettings() {
    try {
      const cfg = await api('/api/settings');
      const provSelect = $('#aiProviderSelect');
      if (provSelect) {
        provSelect.value = cfg.active_provider || 'deterministic';
        updateAiKeyVisibility(provSelect.value);
      }
      const modelInput = $('#aiModelInput');
      if (modelInput && cfg.ai_model) modelInput.value = cfg.ai_model;
      const ollamaInput = $('#ollamaEndpointInput');
      if (ollamaInput && cfg.ollama_endpoint) ollamaInput.value = cfg.ollama_endpoint;

      const badge = $('#activeAiBadge');
      if (badge) {
        const prov = cfg.active_provider || 'deterministic';
        badge.textContent = `${prov.toUpperCase()} (${cfg.llm_available ? 'Connected' : 'Active'})`;
        badge.className = `chip ${prov === 'deterministic' ? 'chip-ok' : cfg.llm_available ? 'chip-ok' : 'chip-warn'}`;
      }
    } catch (err) {
      /* ignore */
    }
  }

  function updateAiKeyVisibility(provider) {
    const keyField = $('#aiKeyField');
    const modelField = $('#aiModelField');
    const ollamaField = $('#ollamaEndpointField');
    const keyLabel = $('#aiKeyLabel');
    if (!keyField) return;

    if (provider === 'deterministic') {
      keyField.hidden = true; modelField.hidden = true; ollamaField.hidden = true;
    } else if (provider === 'ollama') {
      keyField.hidden = true; modelField.hidden = false; ollamaField.hidden = false;
    } else {
      keyField.hidden = false; modelField.hidden = false; ollamaField.hidden = true;
      keyLabel.textContent = `${provider.toUpperCase()} API Key`;
    }
  }

  async function testAiConnection() {
    const btn = $('#btnTestAi');
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `${ico('refresh')} Testing...`;
    try {
      const res = await api('/api/test-ai', { method: 'POST' });
      if (res.success) toast(res.message);
      else toast(res.message, 'error');
    } catch (err) {
      toast('Test failed: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = orig;
    }
  }

  async function saveAiSettings() {
    const prov = val('aiProviderSelect');
    const key = val('aiApiKeyInput').trim();
    const model = val('aiModelInput').trim();
    const ollama = val('ollamaEndpointInput').trim();

    const payload = { ai_provider: prov };
    if (model) payload.ai_model = model;
    if (ollama) payload.ollama_endpoint = ollama;
    if (key) {
      if (prov === 'gemini') payload.gemini_api_key = key;
      else if (prov === 'openai') payload.openai_api_key = key;
      else if (prov === 'anthropic') payload.anthropic_api_key = key;
    }
    try {
      await api('/api/settings', { method: 'POST', body: payload });
      toast('AI configuration saved');
      await loadAiSettings();
    } catch (err) {
      toast('Failed to save settings: ' + err.message, 'error');
    }
  }

  async function purgeAll() {
    if (!await confirmDialog('Delete all your data?', 'This removes your profile, applications, watchlist, settings, and cached searches. You cannot undo it.', 'Delete everything')) return;
    try { await api('/api/purge-all-data', { method: 'DELETE' }); toast('All data deleted'); setTimeout(() => { location.hash = '#/jobs'; location.reload(); }, 600); }
    catch (err) { toast('Could not delete: ' + err.message, 'error'); }
  }

  // ----------------------------------------------------------------- events
  const ACTIONS = {
    // search
    'idea': el => {
      $('#searchQuery').value = el.dataset.q;
      resetAllFilters();
      runSearch({ forceRefresh: false });
    },
    'search-again': () => runSearch({ forceRefresh: true }),
    'clear-min': () => {
      S.filters.minScore = 0;
      const s = $('#searchMinScore'); if (s) s.value = '0';
      filterAndRender();
    },
    'relax-score': () => {
      S.filters.minScore = 0;
      const s = $('#searchMinScore'); if (s) s.value = '0';
      filterAndRender();
    },
    'clear-filters': () => {
      resetAllFilters();
      filterAndRender();
    },
    'search-worldwide-remote': () => {
      const loc = $('#searchLocation');
      if (loc) loc.value = 'Worldwide';
      resetAllFilters();
      runSearch({ forceRefresh: false });
    },
    'suggest-search': el => {
      const q = $('#searchQuery');
      if (q) q.value = el.dataset.q || '';
      resetAllFilters();
      runSearch({ forceRefresh: false });
    },
    'clear-search': () => {
      const q = $('#searchQuery'); if (q) q.value = '';
      const loc = $('#searchLocation'); if (loc) loc.value = '';
      resetAllFilters();
      runSearch({ forceRefresh: false });
    },
    'job-select': el => selectJob(el.dataset.key),
    'job-strategy': () => openWorkspace(selectedJob(), 'strategy', 'jobs'),
    'job-tailor': () => openWorkspace(selectedJob(), 'resume', 'jobs'),
    'job-save': () => saveJob(selectedJob()),
    'job-hunt': () => prepareEverything(selectedJob()),
    'detail-close': () => closeDetailSheet(),
    // profile
    'skill-add': () => addSkillFromInput(),
    'skill-remove': el => { syncFormToState(); S.profile.skills.splice(Number(el.dataset.i), 1); renderSkills(); markDirty(); },
    'exp-add': () => { syncFormToState(); S.profile.experience.unshift({ company: '', role: '', location: '', start_date: '', end_date: 'Present', current: true, bullets: [''] }); S.openExp = new Set([0]); renderExperience(); markDirty(); const f = $('#profileExperienceList .exp-company'); if (f) f.focus(); },
    'exp-remove': el => { syncFormToState(); S.profile.experience.splice(Number(el.dataset.i), 1); S.openExp = new Set([0]); renderExperience(); markDirty(); },
    'bullet-add': el => { syncFormToState(); const i = Number(el.dataset.i); S.profile.experience[i].bullets.push(''); S.openExp.add(i); renderExperience(); markDirty(); const t = $$(`#profileExperienceList [data-exp="${i}"] .exp-bullet`); if (t.length) t[t.length - 1].focus(); },
    'bullet-remove': el => { syncFormToState(); S.profile.experience[Number(el.dataset.i)].bullets.splice(Number(el.dataset.b), 1); renderExperience(); markDirty(); },
    'edu-add': () => { syncFormToState(); S.profile.education.push({ institution: '', degree: '', graduation_year: '' }); renderEducation(); markDirty(); const f = $$('#profileEducationList .edu-inst'); if (f.length) f[f.length - 1].focus(); },
    'edu-remove': el => { syncFormToState(); S.profile.education.splice(Number(el.dataset.i), 1); renderEducation(); markDirty(); },
    'parse-paste': () => parsePasted(),
    'profile-save': () => saveProfile(),
    'profile-discard': () => discardProfile(),
    // workspace
    'ws-back': () => go(S.ws.from === 'applications' ? 'applications' : S.ws.from === 'digest' ? 'digest' : 'jobs'),
    'ws-save': () => saveJob(S.ws.job),
    'ws-retry': () => renderWsTab(),
    'auto-tailor': () => autoTailor(),
    'bullets-copy': () => copyAtsBullets(),
    'diff-accept': el => setDiff(el.dataset.id, 'accepted'),
    'diff-reject': el => setDiff(el.dataset.id, 'rejected'),
    'diff-accept-all': () => setAllDiffs('accepted'),
    'diff-reset': () => setAllDiffs('rejected'),
    'diff-unchanged-toggle': () => { S.ws.showUnchanged = !S.ws.showUnchanged; renderResumeTab(); },
    'export': el => exportResume(el.dataset.fmt),
    'gap-add': el => addSkillToProfile(el.dataset.skill),
    'cover-tone': el => { S.ws.tone = el.dataset.tone; renderWsTab(); },
    'cover-copy': async () => { try { await navigator.clipboard.writeText(val('coverLetterTextarea')); toast('Cover letter copied'); } catch (e) { toast('Your browser blocked copying. Select the text and copy it.', 'error'); } },
    'cover-save': () => saveCoverLetter(),
    // applications
    'app-add': () => openAppDialog(null),
    'app-edit': el => openAppDialog(S.applications.find(a => a.id === el.dataset.id)),
    'app-delete': el => deleteApp(el.dataset.id),
    'app-open': el => { const a = S.applications.find(x => x.id === el.dataset.id); if (a) openWorkspace(a.job_data, 'resume', 'applications'); },
    // companies, digest, misc
    'watch-add': () => { $('#wlCompanyName').value = ''; $('#wlTargetRole').value = ''; $('#wlAtsType').value = ''; $('#watchDialog').showModal(); $('#wlCompanyName').focus(); },
    'watch-check': () => checkWatchlist(),
    'watch-view': el => { $('#searchQuery').value = el.dataset.name; go('jobs'); runSearch(); },
    'watch-remove': async el => {
      if (!await confirmDialog(`Stop watching ${el.dataset.name}?`, 'You can add it again later.', 'Remove')) return;
      try { await api(`/api/watchlist/${encodeURIComponent(el.dataset.id)}`, { method: 'DELETE' }); toast('Company removed'); loadWatchlist(); }
      catch (err) { toast(err.message, 'error'); }
    },
    'digest-open': el => openWorkspace((S.digestJobs || [])[Number(el.dataset.i)], 'resume', 'digest'),
    'sources-refresh': () => loadSourceHealth(),
    'purge': () => purgeAll(),
    'dialog-close': el => { const d = el.closest('dialog'); if (d) d.close(); }
  };

  function addSkillFromInput() {
    const input = $('#newSkill'), s = input.value.trim();
    if (!s) return;
    syncFormToState();
    if (!S.profile.skills.some(x => x.toLowerCase() === s.toLowerCase())) { S.profile.skills.push(s); renderSkills(); markDirty(); }
    input.value = ''; input.focus();
  }

  function bindEvents() {
    document.addEventListener('click', e => {
      const el = e.target.closest('[data-action]');
      if (el && ACTIONS[el.dataset.action] && el.tagName !== 'SELECT') ACTIONS[el.dataset.action](el, e);
      if (!e.target.closest('.menu-wrap')) closeMenu();
    });
    $('#moreBtn').addEventListener('click', toggleMenu);
    $('#moreMenu').addEventListener('click', e => { if (e.target.closest('a')) closeMenu(); });

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') { closeMenu(); closeDetailSheet(); }
    });
    window.addEventListener('hashchange', route);
    window.addEventListener('beforeunload', e => { if (S.dirty) { e.preventDefault(); e.returnValue = ''; } });

    // search form & refresh
    $('#searchForm').addEventListener('submit', e => {
      e.preventDefault();
      resetAllFilters();
      runSearch({ forceRefresh: false });
    });
    const btnRefresh = $('#btnRefresh');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => {
        toast('Refreshing jobs from all sources and updating database cache...');
        resetAllFilters();
        runSearch({ forceRefresh: true });
      });
    }

    // segmented work mode
    const wmSeg = $('#workModeSeg');
    if (wmSeg) {
      wmSeg.addEventListener('click', e => {
        const b = e.target.closest('[data-mode]');
        if (!b) return;
        S.filters.workMode = b.dataset.mode;
        S.workMode = b.dataset.mode;
        syncWorkModeSeg();
        if (S.searchHasRun) filterAndRender();
      });
    }

    // segmented match score
    const msSeg = $('#matchScoreSeg');
    if (msSeg) {
      msSeg.addEventListener('click', e => {
        const b = e.target.closest('[data-min-score]');
        if (!b) return;
        S.filters.minScore = parseInt(b.dataset.minScore, 10) || 0;
        const s = $('#searchMinScore'); if (s) s.value = String(S.filters.minScore);
        if (S.searchHasRun) filterAndRender();
      });
    }

    $('#searchMinScore').addEventListener('change', e => {
      S.filters.minScore = parseInt(e.target.value, 10) || 0;
      if (S.searchHasRun) filterAndRender();
    });

    // segmented big tech filter
    const famSeg = $('#famousSeg');
    if (famSeg) {
      famSeg.addEventListener('click', e => {
        const b = e.target.closest('[data-famous]');
        if (!b) return;
        S.filters.famousMode = b.dataset.famous;
        S.famousFilter = b.dataset.famous;
        try { localStorage.setItem('jh-famous-filter', S.famousFilter); } catch (err) {}
        syncFamousUi();
        if (S.searchHasRun) filterAndRender();
      });
    }

    const famSelect = $('#searchFamousSelect');
    if (famSelect) {
      famSelect.addEventListener('change', e => {
        S.famousFilter = e.target.value;
        S.filters.famousMode = e.target.value;
        try { localStorage.setItem('jh-famous-filter', S.famousFilter); } catch (err) {}
        syncFamousUi();
        if (S.searchHasRun) filterAndRender();
      });
    }

    // expandable more filters drawer
    const btnToggleDrawer = $('#btnToggleFiltersDrawer');
    const filtersDrawer = $('#filtersDrawer');
    if (btnToggleDrawer && filtersDrawer) {
      btnToggleDrawer.addEventListener('click', () => {
        const isHidden = filtersDrawer.hidden;
        filtersDrawer.hidden = !isHidden;
        btnToggleDrawer.setAttribute('aria-expanded', String(isHidden));
        btnToggleDrawer.classList.toggle('is-open', isHidden);
      });
    }

    // drawer: target country include
    const cqSeg = $('#countryQuickSeg');
    if (cqSeg) {
      cqSeg.addEventListener('click', e => {
        const b = e.target.closest('[data-country]');
        if (!b) return;
        S.filters.country = b.dataset.country;
        const cSel = $('#countrySelect'); if (cSel) cSel.value = S.filters.country;
        if (S.searchHasRun) filterAndRender();
      });
    }

    const cSel = $('#countrySelect');
    if (cSel) {
      cSel.addEventListener('change', e => {
        S.filters.country = e.target.value;
        if (S.searchHasRun) filterAndRender();
      });
    }

    // drawer: exclude countries
    const exSel = $('#excludeCountrySelect');
    if (exSel) {
      exSel.addEventListener('change', e => {
        const val = e.target.value;
        if (val) {
          if (!S.filters.excludedCountries) S.filters.excludedCountries = new Set();
          S.filters.excludedCountries.add(val);
          e.target.value = '';
          if (S.searchHasRun) filterAndRender();
        }
      });
    }

    const qExWrap = $('#quickExcludeChips');
    if (qExWrap) {
      qExWrap.addEventListener('click', e => {
        const b = e.target.closest('[data-exclude-country]');
        if (!b) return;
        const c = b.dataset.excludeCountry;
        if (!S.filters.excludedCountries) S.filters.excludedCountries = new Set();
        S.filters.excludedCountries.add(c);
        if (S.searchHasRun) filterAndRender();
      });
    }

    const exTagsWrap = $('#excludedCountriesTags');
    if (exTagsWrap) {
      exTagsWrap.addEventListener('click', e => {
        const b = e.target.closest('[data-remove-excluded]');
        if (!b) return;
        const c = b.dataset.removeExcluded;
        if (S.filters.excludedCountries) S.filters.excludedCountries.delete(c);
        if (S.searchHasRun) filterAndRender();
      });
    }

    // drawer: seniority
    const senSeg = $('#senioritySeg');
    if (senSeg) {
      senSeg.addEventListener('click', e => {
        const b = e.target.closest('[data-sen]');
        if (!b) return;
        S.filters.seniority = b.dataset.sen;
        if (S.searchHasRun) filterAndRender();
      });
    }

    // drawer: salary tier
    const salSeg = $('#salarySeg');
    if (salSeg) {
      salSeg.addEventListener('click', e => {
        const b = e.target.closest('[data-sal]');
        if (!b) return;
        S.filters.salaryTier = b.dataset.sal;
        if (S.searchHasRun) filterAndRender();
      });
    }

    // drawer: freshness
    const freshSeg = $('#freshnessSeg');
    if (freshSeg) {
      freshSeg.addEventListener('click', e => {
        const b = e.target.closest('[data-days]');
        if (!b) return;
        S.filters.freshnessDays = parseInt(b.dataset.days, 10) || 0;
        if (S.searchHasRun) filterAndRender();
      });
    }

    // drawer: application & direct ATS flags
    const flagsGroup = $('#flagsGroup');
    if (flagsGroup) {
      flagsGroup.addEventListener('click', e => {
        const b = e.target.closest('[data-flag]');
        if (!b) return;
        const fl = b.dataset.flag;
        if (fl === 'direct_ats') S.filters.directAtsOnly = !S.filters.directAtsOnly;
        else if (fl === 'hide_applied') S.filters.hideApplied = !S.filters.hideApplied;
        else if (fl === 'saved_only') S.filters.savedOnly = !S.filters.savedOnly;
        if (S.searchHasRun) filterAndRender();
      });
    }

    // active filters bar: chip removal
    const actList = $('#activeFiltersList');
    if (actList) {
      actList.addEventListener('click', e => {
        const b = e.target.closest('[data-remove-filter]');
        if (!b) return;
        removeSingleFilter(b.dataset.removeFilter, b.dataset.filterVal);
        if (S.searchHasRun) filterAndRender();
      });
    }

    // reset all filters
    const btnResetAll = $('#btnClearAllFilters');
    if (btnResetAll) {
      btnResetAll.addEventListener('click', () => {
        resetAllFilters();
        if (S.searchHasRun) filterAndRender();
      });
    }

    $('#autoReloadSelect').addEventListener('change', e => {
      setAutoReloadMinutes(parseInt(e.target.value, 10));
      const label = e.target.options[e.target.selectedIndex].text;
      toast(label === 'Off' ? 'Auto-refresh disabled' : `Auto-refresh set to ${label.toLowerCase()}`);
    });
    $('#sortResultsBy').addEventListener('change', () => { filterAndRender(); });
    $('#sourceToggle').addEventListener('click', () => {
      const p = $('#sourcePanel'); p.hidden = !p.hidden;
      $('#sourceToggle').setAttribute('aria-expanded', String(!p.hidden));
    });

    // AI settings
    const provSelect = $('#aiProviderSelect');
    if (provSelect) {
      provSelect.addEventListener('change', () => updateAiKeyVisibility(provSelect.value));
    }
    const testAiBtn = $('#btnTestAi');
    if (testAiBtn) testAiBtn.addEventListener('click', testAiConnection);
    const saveAiBtn = $('#btnSaveAi');
    if (saveAiBtn) saveAiBtn.addEventListener('click', saveAiSettings);

    // workspace tabs
    $('#wsTabs').addEventListener('click', e => {
      const b = e.target.closest('[data-ws-tab]');
      if (b) go('job', b.dataset.wsTab);
    });
    document.addEventListener('focusout', e => { if (e.target.matches && e.target.matches('.editable')) manualEdit(e.target); });
    document.addEventListener('input', e => {
      if (e.target.id === 'coverLetterTextarea') S.ws.cover[S.ws.tone] = e.target.value;
    });

    // profile form
    $('#profileForm').addEventListener('input', e => { if (e.target.id !== 'newSkill') markDirty(); });
    $('#profileForm').addEventListener('submit', e => e.preventDefault());
    $('#newSkill').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addSkillFromInput(); } });
    $('#resumeFileInput').addEventListener('change', e => { handleFile(e.target.files[0]); e.target.value = ''; });
    const dz = $('#dropzone');
    ['dragenter', 'dragover'].forEach(t => dz.addEventListener(t, e => { e.preventDefault(); dz.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach(t => dz.addEventListener(t, e => { e.preventDefault(); dz.classList.remove('is-over'); }));
    dz.addEventListener('drop', e => handleFile(e.dataTransfer.files[0]));

    // applications board: stage menu and drag and drop
    const board = $('#kanbanBoard');
    board.addEventListener('change', e => { const s = e.target.closest('[data-action="app-stage"]'); if (s) moveApp(s.dataset.id, s.value); });
    board.addEventListener('dragstart', e => { const c = e.target.closest('.kcard'); if (c) { e.dataTransfer.setData('text/plain', c.dataset.id); c.classList.add('dragging'); } });
    board.addEventListener('dragend', e => { const c = e.target.closest('.kcard'); if (c) c.classList.remove('dragging'); $$('.col', board).forEach(x => x.classList.remove('drop-over')); });
    board.addEventListener('dragover', e => { const c = e.target.closest('.col'); if (c) { e.preventDefault(); $$('.col', board).forEach(x => x.classList.toggle('drop-over', x === c)); } });
    board.addEventListener('drop', e => {
      const c = e.target.closest('.col');
      if (!c) return;
      e.preventDefault();
      $$('.col', board).forEach(x => x.classList.remove('drop-over'));
      const id = e.dataTransfer.getData('text/plain');
      if (id) moveApp(id, c.dataset.stage);
    });

    // dialogs and digest
    $('#appDialogForm').addEventListener('submit', e => { e.preventDefault(); submitAppDialog(); });
    $('#watchDialogForm').addEventListener('submit', e => { e.preventDefault(); submitWatch(); });
    $('#digestThresholdSelect').addEventListener('change', changeDigestCutoff);
  }

  // ------------------------------------------------------------------- init
  async function init() {
    S.openExp = new Set([0]);
    initTheme();
    syncFamousUi();
    bindEvents();
    await Promise.all([loadProfile(), loadApplications()]);
    renderWsHeader();
    renderIdeas();

    // Restore auto-reload schedule (defaults to 5 hours)
    const savedMins = getAutoReloadMinutes();
    const reloadSelect = $('#autoReloadSelect');
    if (reloadSelect) reloadSelect.value = String(savedMins);
    scheduleAutoReload(savedMins);

    // Check for cached search results from this session or database
    let restoredCached = false;
    try {
      const cached = sessionStorage.getItem('jh-last-search-meta');
      const cachedTime = sessionStorage.getItem('jh-last-search-time');
      if (cached) {
        const meta = JSON.parse(cached);
        const pool = meta.all_jobs || meta.jobs || [];
        if (meta && pool.length > 0) {
          S.searchMeta = meta;
          S.allJobs = pool;
          S.jobsRanked = pool;
          S.searchHasRun = true;
          S.lastSearchTime = parseInt(cachedTime, 10) || Date.now();
          filterAndRender();
          restoredCached = true;
        }
      }
    } catch (e) {}

    if (!restoredCached) {
      try {
        const savedRes = await api('/api/search/saved');
        const pool = savedRes ? (savedRes.all_jobs || savedRes.jobs || []) : [];
        if (pool.length > 0) {
          S.searchMeta = { jobs: savedRes.jobs, all_jobs: pool, ...(savedRes.meta || {}) };
          S.allJobs = pool;
          S.jobsRanked = pool;
          S.searchHasRun = true;
          if (savedRes.meta && savedRes.meta.updated_at) {
            S.lastSearchTime = new Date(savedRes.meta.updated_at).getTime() || Date.now();
          }
          if (savedRes.meta && savedRes.meta.query && !$('#searchQuery').value) {
            $('#searchQuery').value = savedRes.meta.query;
          }
          filterAndRender();
          restoredCached = true;
        }
      } catch (e) {}
    }

    route();

    if (S.view === 'jobs') {
      if (restoredCached) renderResults();
      else renderWelcomeState();
    }
  }

  function renderWelcomeState() {
    const stage = $('#searchProgressStage');
    if (stage) stage.hidden = true;
    const split = $('#searchSplit');
    if (split) split.hidden = false;
    const resultsMeta = $('#resultsMeta');
    if (resultsMeta) resultsMeta.hidden = false;
    const tools = $('#resultsTools');
    if (tools) tools.hidden = false;
    $('#resultsSummary').innerHTML = `Press <strong>Search</strong> to discover jobs matching your profile.`;
    $('#jobList').innerHTML = `<div class="empty">${ico('search')}<h3>Ready to search</h3><p>Enter a query or just hit Search to find jobs based on your resume.</p><div class="empty-actions"><button type="button" class="btn btn-primary" data-action="search-again">Search now</button></div></div>`;
    $('#jobDetail').innerHTML = '';
  }

  document.addEventListener('DOMContentLoaded', init);
})();
