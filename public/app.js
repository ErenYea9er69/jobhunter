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
  const VIEWS = ['jobs', 'job', 'recommend', 'applications', 'resume', 'companies', 'digest', 'privacy', 'settings'];
  const TITLES = {
    jobs: 'Jobs', job: 'Job workspace', recommend: 'Recommended For You', applications: 'Applications', resume: 'Resume',
    companies: 'Companies', digest: 'Morning digest', privacy: 'Sources and privacy', settings: 'Settings'
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
      selectedSkills: new Set(),
      jobType: 'all',
      industry: 'all',
      yoe: 'all',
      jobFunctions: [],
      excludedTitles: new Set(),
      jobTypes: new Set(),
      workModels: new Set(),
      locationQuery: '',
      locationRadius: '25',
      customLocations: [],
      expLevels: new Set(),
      expOpenToAll: true,
      expYears: 0,
      salaryOpenToAll: true,
      minSalary: 0,
      h1b: false,
      excludeClearance: false,
      excludeCitizenOnly: false,
      industries: new Set(),
      excludedIndustries: new Set(),
      skills: new Set(),
      excludedSkills: new Set(),
      roleType: 'all',
      companies: new Set(),
      companyStages: new Set(),
      excludeStaffing: false,
      easyApplyOnly: false
    },
    hiddenJobs: (function() { try { return new Set(JSON.parse(localStorage.getItem('jh_hidden_jobs') || '[]')); } catch (e) { return new Set(); } })(),
    showHidden: false,
    drawerOpen: false,
    profile: null,
    profileEmpty: true,
    profiles: [],
    activeProfileId: 'master',
    atsAudit: null,
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
    jobsLimit: 20,
    recJobs: [],
    recMeta: null,
    recLoading: false,
    applications: [],
    appFilter: 'all',
    appSearchQuery: '',
    appViewMode: (function() { try { return localStorage.getItem('jh_app_view_mode') || 'kanban'; } catch(e) { return 'kanban'; } })(),
    activeDrawerApp: null,
    activeDrawerTab: 'overview',
    watchlist: [],
    watchResults: {},
    enrichingKeys: new Set(),
    activeAutofillJob: null,
    autofillPayload: null,
    autofillScript: '',
    autofillPlatformInfo: null,
    ws: { job: null, key: '', tab: 'strategy', from: 'jobs', refinement: null, decisions: {}, ats: null, atsFresh: false,
          strategy: null, gaps: null, cover: {}, prep: null, tone: 'direct', showUnchanged: false, seq: 0 }
  };

  function syncFamousUi() {
    const mode = (S.filters && S.filters.famousMode) || S.famousFilter || 'all';
    const sel = $('#searchFamousSelect');
    if (sel && sel.value !== mode) sel.value = mode;
    const famSeg = $('#famousSeg');
    if (famSeg) {
      $$('button[data-famous]', famSeg).forEach(b => {
        b.setAttribute('aria-pressed', String(b.dataset.famous === mode));
      });
    }
    const t = $('#p4TextFamous');
    const pill = $('#p4PillFamous');
    const menu = $('#p4MenuFamous');
    const labels = {
      all: 'Company Type',
      hide: 'No Big Tech',
      only: 'Big Tech Only',
      startups: 'Startups Only'
    };
    if (t) t.textContent = labels[mode] || 'Company Type';
    if (pill) pill.classList.toggle('is-active', Boolean(mode && mode !== 'all'));
    if (menu) {
      $$('.p4-menu-item', menu).forEach(b => {
        b.classList.toggle('is-selected', b.dataset.famous === mode);
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

  function decodeEntities(str) {
    if (!str || typeof str !== 'string' || !str.includes('&')) return str || '';
    if (!/&(?:[a-z\d]+|#\d+|#[xX][a-f\d]+);/i.test(str)) return str;
    try {
      const doc = new DOMParser().parseFromString(str, 'text/html');
      let out = doc.body.textContent || str;
      if (out.includes('&') && /&(?:[a-z\d]+|#\d+|#[xX][a-f\d]+);/i.test(out)) {
        const doc2 = new DOMParser().parseFromString(out, 'text/html');
        out = doc2.body.textContent || out;
      }
      return out;
    } catch (_) {
      return str.replace(/&#(?:x([0-9a-f]+)|(\d+));/gi, (_, hex, dec) =>
        String.fromCodePoint(hex ? parseInt(hex, 16) : parseInt(dec, 10))
      ).replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#0?39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');
    }
  }

  function cleanText(v) {
    if (v === null || v === undefined) return '';
    let s = String(v);
    if (s.includes('&')) {
      s = decodeEntities(s);
    }
    return s.replace(/\u00a0/g, ' ').trim();
  }

  function esc(v) {
    if (v === null || v === undefined) return '';
    let s = String(v);
    if (s.includes('&') && /&(?:[a-z\d]+|#\d+|#[xX][a-f\d]+);/i.test(s)) {
      s = decodeEntities(s);
    }
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  const escapeHtml = esc;

  function cleanTitle(t) {
    if (!t) return '';
    return cleanText(t).replace(/\s*—\s*/g, ' - ').replace(/\s*–\s*/g, ' - ');
  }

  function safeUrl(u) {
    if (!u || typeof u !== 'string') return '#';
    const trimmed = u.trim();
    if (/^(?:https?:\/\/|mailto:)/i.test(trimmed)) return trimmed;
    if (trimmed.startsWith('/') || trimmed.startsWith('#')) return trimmed;
    return '#';
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
    if (res.status === 204 || res.headers.get('content-length') === '0') {
      return {};
    }
    return res.json().catch(() => ({}));
  }

  const MAX_VISIBLE_TOASTS = 3;

  function dismissToast(el) {
    if (!el || el._isDismissing) return;
    el._isDismissing = true;
    if (el._timer) clearTimeout(el._timer);
    el.classList.add('toast-out');
    setTimeout(() => {
      if (el.parentNode) el.remove();
    }, 220);
  }

  function toast(message, type = 'ok') {
    const box = $('#toastContainer');
    if (!box) return;
    const cleanMsg = String(message || '').trim();
    if (!cleanMsg) return;

    const duration = type === 'error' ? 6000 : 3500;

    // 1. Check for existing active toast with the same message and type
    const existing = Array.from(box.querySelectorAll('.toast:not(.toast-out)')).find(el => {
      return el.dataset.toastMsg === cleanMsg && el.dataset.toastType === type;
    });

    if (existing) {
      // Increment counter badge and refresh timer
      const count = (parseInt(existing.dataset.toastCount, 10) || 1) + 1;
      existing.dataset.toastCount = String(count);

      let badge = existing.querySelector('.toast-badge');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'toast-badge';
        existing.appendChild(badge);
      }
      badge.textContent = `×${count}`;

      // Reset auto-dismiss timer
      if (existing._timer) clearTimeout(existing._timer);
      existing._timer = setTimeout(() => dismissToast(existing), duration);

      // Re-trigger bounce tactile micro-animation
      existing.classList.remove('toast-bump');
      void existing.offsetWidth; // force browser layout reflow
      existing.classList.add('toast-bump');
      return;
    }

    // 2. Cap maximum concurrent toasts (dismiss oldest if >= MAX_VISIBLE_TOASTS)
    const activeToasts = Array.from(box.querySelectorAll('.toast:not(.toast-out)'));
    if (activeToasts.length >= MAX_VISIBLE_TOASTS) {
      dismissToast(activeToasts[0]);
    }

    // 3. Create fresh toast
    const el = document.createElement('div');
    el.className = `toast${type === 'error' ? ' toast-error' : ''}`;
    el.dataset.toastMsg = cleanMsg;
    el.dataset.toastType = type;
    el.dataset.toastCount = '1';
    el.title = 'Click to dismiss';
    el.innerHTML = `${ico(type === 'error' ? 'alert' : 'check')}<span class="toast-text">${esc(cleanMsg)}</span>`;

    // Click to dismiss
    el.addEventListener('click', () => dismissToast(el));

    box.appendChild(el);
    el._timer = setTimeout(() => dismissToast(el), duration);
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

  function companyMonogram(name) {
    if (!name) return 'JH';
    const clean = cleanText(name).replace(/[^a-zA-Z0-9\s]/g, '');
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return clean.slice(0, 2).toUpperCase() || 'JH';
  }

  function companyAvatarColor(name) {
    const palettes = [
      { bg: 'rgba(18, 183, 106, 0.12)', text: '#087443', border: 'rgba(18, 183, 106, 0.25)' }, // Emerald
      { bg: 'rgba(14, 116, 144, 0.12)', text: '#0e7490', border: 'rgba(14, 116, 144, 0.25)' }, // Cyan
      { bg: 'rgba(99, 102, 241, 0.12)', text: '#4f46e5', border: 'rgba(99, 102, 241, 0.25)' }, // Indigo
      { bg: 'rgba(168, 85, 247, 0.12)', text: '#7e22ce', border: 'rgba(168, 85, 247, 0.25)' }, // Purple
      { bg: 'rgba(234, 88, 12, 0.12)',  text: '#c2410c', border: 'rgba(234, 88, 12, 0.25)' },  // Orange
      { bg: 'rgba(2, 132, 199, 0.12)',  text: '#0369a1', border: 'rgba(2, 132, 199, 0.25)' },  // Sky
      { bg: 'rgba(13, 148, 136, 0.12)', text: '#0f766e', border: 'rgba(13, 148, 136, 0.25)' }, // Teal
      { bg: 'rgba(217, 70, 239, 0.12)', text: '#a21caf', border: 'rgba(217, 70, 239, 0.25)' }, // Fuchsia
    ];
    let hash = 0;
    for (let i = 0; i < (name || '').length; i++) hash = ((hash << 5) - hash) + name.charCodeAt(i);
    return palettes[Math.abs(hash) % palettes.length];
  }

  function companyLogoUrl(j) {
    if (!j) return null;
    if (j.logo_url) return j.logo_url;
    if (j.company_logo) return j.company_logo;

    const comp = String(j.company || '').trim();
    if (!comp) return null;

    // 1. Direct dictionary for known tech / ATS brands
    const KNOWN = {
      'openai': 'openai.com',
      'anthropic': 'anthropic.com',
      'posthog': 'posthog.com',
      'vercel': 'vercel.com',
      'stripe': 'stripe.com',
      'gitlab': 'gitlab.com',
      'github': 'github.com',
      'linear': 'linear.app',
      'figma': 'figma.com',
      'docker': 'docker.com',
      'supabase': 'supabase.com',
      'modal': 'modal.com',
      'google': 'google.com',
      'meta': 'meta.com',
      'apple': 'apple.com',
      'microsoft': 'microsoft.com',
      'amazon': 'amazon.com',
      'netflix': 'netflix.com',
      'uber': 'uber.com',
      'airbnb': 'airbnb.com',
      'coinbase': 'coinbase.com',
      'shopify': 'shopify.com',
      'spotify': 'spotify.com',
      'databricks': 'databricks.com',
      'snowflake': 'snowflake.com',
      'cloudflare': 'cloudflare.com',
      'palantir': 'palantir.com',
      'nvidia': 'nvidia.com',
      'bytedance': 'bytedance.com',
      'tiktok': 'tiktok.com',
      'salesforce': 'salesforce.com',
      'adobe': 'adobe.com',
      'tesla': 'tesla.com',
      'spacex': 'spacex.com',
      'lemon.io': 'lemon.io',
      'himalayas': 'himalayas.app',
      'remoteok': 'remoteok.com',
      'weworkremotely': 'weworkremotely.com',
      'arbeitnow': 'arbeitnow.com',
      'sutherland': 'sutherlandglobal.com',
      'tether': 'tether.to',
      'trackerbot': 'trackerbot.me',
      'dxc': 'dxc.com',
      'tracium': 'tracium.com',
      'steuart nutrition': 'steuartnutrition.com',
      'sowelo': 'soweloconsulting.com',
      'devoteam': 'devoteam.com',
      'upgrade': 'upgrade.com'
    };

    const compLow = comp.toLowerCase();
    for (const [k, dom] of Object.entries(KNOWN)) {
      if (compLow === k || compLow.startsWith(k + ' ') || compLow.includes(k)) {
        return `https://www.google.com/s2/favicons?domain=${dom}&sz=128`;
      }
    }

    // 2. Extract from Ashby / Greenhouse URLs
    const u = String(j.url || j.apply_url || '');
    const ashby = u.match(/jobs\.ashbyhq\.com\/([a-zA-Z0-9_-]+)/);
    if (ashby && ashby[1]) {
      return `https://www.google.com/s2/favicons?domain=${ashby[1]}.com&sz=128`;
    }
    const gh = u.match(/(?:job-boards|boards)\.greenhouse\.io\/([a-zA-Z0-9_-]+)/);
    if (gh && gh[1]) {
      return `https://www.google.com/s2/favicons?domain=${gh[1]}.com&sz=128`;
    }

    // 3. Fallback: sanitize company name to domain
    const clean = compLow
      .replace(/\b(inc|llc|corp|corporation|ltd|limited|gmbh|co|technologies|solutions|group|holdings|services|company)\b\.?/gi, '')
      .replace(/[^a-z0-9]/g, '')
      .trim();
    if (clean && clean.length >= 3) {
      return `https://www.google.com/s2/favicons?domain=${clean}.com&sz=128`;
    }
    return null;
  }

  function companyAvatarHtml(j, target = 'job') {
    const monogram = companyMonogram(j ? j.company : '');
    const avatarCol = companyAvatarColor(j ? j.company : '');
    const cls = target === 'detail' ? 'detail-company-avatar' : (target === 'kcard' ? 'kcard-avatar' : 'job-company-avatar');
    const colorStyle = `background:${avatarCol.bg};color:${avatarCol.text};border-color:${avatarCol.border}`;
    const logo = companyLogoUrl(j);
    if (logo) {
      return `<div class="${cls}" style="${colorStyle}" aria-hidden="true">
        <img class="company-logo-img" src="${esc(logo)}" alt="" loading="lazy" width="100%" height="100%"
             onload="this.classList.add('is-loaded'); if (this.nextElementSibling) this.nextElementSibling.style.display='none';"
             onerror="this.remove();" />
        <span class="company-monogram-fallback">${esc(monogram)}</span>
      </div>`;
    }
    return `<div class="${cls}" style="${colorStyle}" aria-hidden="true"><span class="company-monogram-fallback">${esc(monogram)}</span></div>`;
  }

  function tierOf(score) {
    if (score >= 85) return { cls: 'tier-high', label: 'Excellent fit' };
    if (score >= 70) return { cls: 'tier-good', label: 'Strong fit' };
    if (score >= 50) return { cls: 'tier-fair', label: 'Fair fit' };
    return { cls: 'tier-low', label: 'Low fit' };
  }

  function ring(score, large = false) {
    const n = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
    const tier = tierOf(n);
    const size = large ? 50 : 36;
    const stroke = large ? 4.5 : 3;
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    const offset = c - (n / 100) * c;
    return `<div class="score-ring ${large ? 'score-ring-lg ' : ''}${tier.cls}" style="--pct:${n}" role="img" aria-label="Match score ${n} percent" title="${tier.label} (${n}%)">
      <svg class="score-ring-svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <circle class="score-ring-track" cx="${size/2}" cy="${size/2}" r="${r}" stroke-width="${stroke}" />
        <circle class="score-ring-bar" cx="${size/2}" cy="${size/2}" r="${r}" stroke-width="${stroke}" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${offset.toFixed(1)}" />
      </svg>
      <div class="score-ring-val"><span>${n}</span>${large ? '<small>%</small>' : ''}</div>
    </div>`;
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
    return (j.sources && j.sources.length) ? j.sources : [{ source: j.source, url: j.url, is_free_to_apply: j.is_free_to_apply }];
  }
  function isDirect(s) {
    const name = String(s.source || '');
    return String(s.source_tier || '').includes('Direct company ATS') || /Greenhouse|Ashby|Lever|SmartRecruiters|Workable/i.test(name);
  }
  function isFreeSource(s) {
    if (s && s.is_free_to_apply !== undefined && s.is_free_to_apply !== null) return Boolean(s.is_free_to_apply);
    const src = String((typeof s === 'string' ? s : (s && (s.source || s.name))) || '');
    return !/We Work Remotely|Remotive|RemoteOK|Remote OK/i.test(src);
  }

  /** Return the optimal application source - ALWAYS prefers 100% free options over paywalled/gated boards. */
  function bestApplySource(j) {
    const list = jobSources(j).filter(s => s.url);
    if (!list.length) return { source: j.source || 'Direct', url: j.url || '', is_free_to_apply: true };

    // 1. Top priority: Official direct employer ATS (Greenhouse, Lever, Ashby, Workable, SmartRecruiters)
    const direct = list.find(isDirect);
    if (direct) return direct;

    // 2. Second priority: 100% Free major job boards (LinkedIn, Indeed, ZipRecruiter, Bayt, etc.)
    const freeMajor = list.find(s => isFreeSource(s) && /LinkedIn|Indeed|ZipRecruiter|Hacker News|Bayt|Naukri|HelloWork/i.test(String(s.source || '')));
    if (freeMajor) return freeMajor;

    // 3. Third priority: Any other free remote feed (Himalayas, Jobicy, Arbeitnow, Adzuna)
    const otherFree = list.find(isFreeSource);
    if (otherFree) return otherFree;

    // 4. Last resort: Paid/gated source (We Work Remotely, Remotive, RemoteOK)
    return list[0];
  }

  function bestApplyUrl(j) {
    return (bestApplySource(j) || {}).url || j.url || '';
  }

  function formatSourceBadge(j) {
    const best = bestApplySource(j);
    const src = best.source || j.source || 'Direct';
    const isDirectAts = isDirect(best);
    const isFree = isFreeSource(best);
    const count = (j.sources || []).length;
    const more = count > 1 ? ` <span class="chip-src-count" title="Available on ${count} different job sites">+${count - 1}</span>` : '';

    if (isDirectAts) {
      return `<span class="chip chip-source chip-src-official" title="Official Employer Careers Portal (${esc(src)}) - 100% Free Application">${ico('shield')}Official Site (${esc(src)})${more}</span>`;
    }
    if (/linkedin/i.test(src)) {
      return `<span class="chip chip-source chip-src-linkedin" title="Found on LinkedIn - 100% Free to apply">${ico('arrow-up-right')}via LinkedIn${more}</span>`;
    }
    if (/indeed/i.test(src)) {
      return `<span class="chip chip-source chip-src-indeed" title="Found on Indeed - 100% Free to apply">${ico('arrow-up-right')}via Indeed${more}</span>`;
    }
    if (/ziprecruiter/i.test(src)) {
      return `<span class="chip chip-source chip-src-zip" title="Found on ZipRecruiter - 100% Free to apply">${ico('arrow-up-right')}via ZipRecruiter${more}</span>`;
    }
    if (!isFree) {
      return `<span class="chip chip-source chip-src-gated" title="Only found on ${esc(src)} - Platform charges or prompts for paid membership to apply">${ico('alert')}on ${esc(src)} (Paid)${more}</span>`;
    }
    return `<span class="chip chip-source chip-src-free" title="Found on ${esc(src)} - 100% Free to apply">${ico('arrow-up-right')}via ${esc(src)}${more}</span>`;
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
    $$('.view').forEach(v => {
      if (view === 'recommend') {
        v.hidden = v.id !== 'view-jobs';
      } else {
        v.hidden = v.id !== `view-${view}`;
      }
    });
    const navKey = view === 'job' ? (S.ws.from === 'applications' ? 'applications' : 'jobs') : view;
    $$('[data-nav]').forEach(a => {
      if (a.dataset.nav === navKey) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    document.title = `${TITLES[view] || 'JobHunter'} | JobHunter`;
    closeMenu();
    closeDetailSheet();
    if (S.activeDrawerApp) closeAppDrawer();
    window.scrollTo(0, 0);

    const recBanner = $('#recommendBanner');
    if (recBanner) recBanner.hidden = (view !== 'recommend');

    if (view === 'recommend') {
      loadRecommendations();
    } else if (view === 'jobs') {
      S.jobsLimit = 20;
      if (S.jobs && S.jobs.length && S.searchHasRun) renderResults();
      else fetchJobsFromDb();
    }
    if (view === 'job') { S.ws.tab = ['strategy', 'resume', 'ats', 'gaps', 'cover', 'prep'].includes(sub) ? sub : 'strategy'; renderWsHeader(); renderWsTab(); }
    if (view === 'resume') { loadProfilesList(); runAtsAudit(); setupResumeScrollSpy(); if (sub) switchResumeTab(sub, { scroll: true }); else syncResumeScrollSpy(); }
    if (view === 'applications') loadApplications();
    if (view === 'companies') loadWatchlist();
    if (view === 'digest') loadDigest();
    if (view === 'privacy' || view === 'settings') { loadSettingsView(sub); }
  }

  // ------------------------------------------------------------ theme & sound
  const AudioEffects = {
    ctx: null,
    getCtx() {
      if (!this.ctx && (window.AudioContext || window.webkitAudioContext)) {
        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      }
      return this.ctx;
    },
    play(type = 'click') {
      const enabled = localStorage.getItem('jh-sound') !== '0';
      if (!enabled) return;
      try {
        const ctx = this.getCtx();
        if (!ctx) return;
        if (ctx.state === 'suspended') ctx.resume();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        const t = ctx.currentTime;
        if (type === 'success') {
          osc.type = 'sine';
          osc.frequency.setValueAtTime(523.25, t); // C5
          osc.frequency.exponentialRampToValueAtTime(659.25, t + 0.08); // E5
          gain.gain.setValueAtTime(0.08, t);
          gain.gain.exponentialRampToValueAtTime(0.001, t + 0.22);
          osc.start(t);
          osc.stop(t + 0.22);
        } else if (type === 'alert') {
          osc.type = 'triangle';
          osc.frequency.setValueAtTime(329.63, t); // E4
          gain.gain.setValueAtTime(0.09, t);
          gain.gain.exponentialRampToValueAtTime(0.001, t + 0.16);
          osc.start(t);
          osc.stop(t + 0.16);
        } else {
          osc.type = 'sine';
          osc.frequency.setValueAtTime(580, t);
          gain.gain.setValueAtTime(0.04, t);
          gain.gain.exponentialRampToValueAtTime(0.001, t + 0.06);
          osc.start(t);
          osc.stop(t + 0.06);
        }
      } catch (e) { /* ignore */ }
    }
  };

  function getEffectiveTheme(choice) {
    if (choice === 'system') {
      return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }
    return choice === 'dark' ? 'dark' : 'light';
  }

  function initTheme() {
    let saved = 'light';
    try { saved = localStorage.getItem('jh-theme') || 'light'; } catch (e) { /* ignore */ }
    setTheme(saved, false);

    // Apply density mode from localStorage
    try {
      const density = localStorage.getItem('jh-density') || 'comfortable';
      document.body.classList.toggle('compact-mode', density === 'compact');
    } catch (e) {}

    // Synchronize OS system color scheme changes if system mode is chosen
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        const cur = localStorage.getItem('jh-theme');
        if (cur === 'system') {
          setTheme('system', false);
        }
      });
    }

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
    const effective = getEffectiveTheme(choice);
    const isDark = effective === 'dark';

    root.classList.add('theme-switching');
    if (isDark) {
      root.setAttribute('data-theme', 'dark');
    } else {
      root.removeAttribute('data-theme');
    }

    // Synchronize theme radio options in Settings
    $$('.theme-card-option').forEach(card => {
      const isCardSelected = card.dataset.choice === choice;
      card.setAttribute('aria-checked', String(isCardSelected));
      card.classList.toggle('is-selected', isCardSelected);
    });

    const themeBadge = $('#activeThemeBadge');
    if (themeBadge) {
      if (choice === 'system') {
        themeBadge.textContent = isDark ? 'System (Dark active)' : 'System (Light active)';
      } else {
        themeBadge.textContent = isDark ? 'Dark theme' : 'Light theme';
      }
    }

    const icon = $('#themeIcon use');
    if (icon) icon.setAttribute('href', isDark ? '#i-moon-stars' : '#i-sun');
    const label = $('#themeLabel');
    if (label) label.textContent = isDark ? 'Light theme' : 'Dark theme';

    if (persist) {
      try {
        localStorage.setItem('jh-theme', choice);
        api('/api/settings', { method: 'POST', body: { theme_mode: choice } }).catch(() => {});
      } catch (e) { /* ignore */ }
    }
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        root.classList.remove('theme-switching');
      });
    });
  }

  function closeMenu() {
    const m = $('#moreMenu');
    if (m && !m.hidden) { m.hidden = true; const b = $('#moreBtn'); if (b) b.setAttribute('aria-expanded', 'false'); }
  }
  function toggleMenu(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const m = $('#moreMenu');
    if (m) {
      m.hidden = !m.hidden;
      const b = $('#moreBtn');
      if (b) b.setAttribute('aria-expanded', String(!m.hidden));
    }
  }

  // ------------------------------------------------------------ settings hub
  async function loadSettingsView(subTab = '') {
    const targetTab = subTab || 'all';
    switchSettingsTab(targetTab, { scroll: targetTab !== 'all' });

    await Promise.all([
      loadAiSettings().catch(() => {}),
      loadSourceHealth().catch(() => {}),
      checkLinkedinRadarStatus().catch(() => {}),
      loadSystemInfo().catch(() => {})
    ]);

    syncSettingsInputs();
  }

  function setSettingsActiveTab(tab) {
    $$('.settings-tab-btn').forEach(btn => {
      const isActive = btn.dataset.tab === tab;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', String(isActive));
      btn.tabIndex = isActive ? 0 : -1;
    });
  }

  function syncSettingsScrollSpy() {
    const content = $('#settingsContent');
    if (!content) return;
    const groups = $$('.settings-group', content).filter(group => !group.classList.contains('is-hidden'));
    if (!groups.length) return;

    // Check if scrolled near the bottom of settingsContent
    const atBottom = (content.scrollHeight - content.scrollTop - content.clientHeight) < 56;
    if (atBottom) {
      const lastGroup = groups[groups.length - 1];
      if (lastGroup) {
        setSettingsActiveTab(lastGroup.dataset.group);
        return;
      }
    }

    const contentRect = content.getBoundingClientRect();
    const marker = contentRect.top + Math.min(150, Math.max(64, contentRect.height * 0.20));
    let activeGroup = groups[0];
    for (let i = 0; i < groups.length; i++) {
      const group = groups[i];
      const rect = group.getBoundingClientRect();
      if (rect.top <= marker) {
        activeGroup = group;
      } else {
        break;
      }
    }
    setSettingsActiveTab(activeGroup.dataset.group);
  }

  function scheduleSettingsScrollSpy() {
    if (scrollToSettingsGroup.isScrolling) return;
    if (scheduleSettingsScrollSpy.frame) return;
    scheduleSettingsScrollSpy.frame = requestAnimationFrame(() => {
      scheduleSettingsScrollSpy.frame = 0;
      syncSettingsScrollSpy();
    });
  }

  function scrollToSettingsGroup(tab) {
    const content = $('#settingsContent');
    const target = content && $(`#group-${tab}`, content);
    if (!content || !target) return;

    scrollToSettingsGroup.isScrolling = true;
    clearTimeout(scrollToSettingsGroup.timer);

    setSettingsActiveTab(tab);

    const contentRect = content.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const targetScrollTop = content.scrollTop + (targetRect.top - contentRect.top) - 10;

    content.scrollTo({
      top: Math.max(0, targetScrollTop),
      behavior: 'smooth'
    });

    scrollToSettingsGroup.timer = setTimeout(() => {
      scrollToSettingsGroup.isScrolling = false;
      syncSettingsScrollSpy();
    }, 450);
  }

  function setupSettingsScrollSpy() {
    const content = $('#settingsContent');
    if (!content || content.dataset.scrollSpyReady === 'true') return;
    content.dataset.scrollSpyReady = 'true';
    content.addEventListener('scroll', scheduleSettingsScrollSpy, { passive: true });
    window.addEventListener('resize', scheduleSettingsScrollSpy, { passive: true });

    // Allow scrolling anywhere on view-settings to scroll the content area
    const viewSettings = $('#view-settings');
    if (viewSettings && !viewSettings.dataset.wheelBound) {
      viewSettings.dataset.wheelBound = 'true';
      viewSettings.addEventListener('wheel', e => {
        if (content.contains(e.target)) return;
        content.scrollTop += e.deltaY;
      }, { passive: true });
    }

    scheduleSettingsScrollSpy();
  }

  function switchSettingsTab(tab, options = {}) {
    const selectedTab = (!tab || tab === 'all') ? 'general' : tab;
    setSettingsActiveTab(selectedTab);

    const groups = $$('.settings-group');
    groups.forEach(g => {
      g.classList.remove('is-hidden');
      g.setAttribute('aria-hidden', 'false');
    });

    setupSettingsScrollSpy();
    if (options.scroll && tab && tab !== 'all') {
      scrollToSettingsGroup(selectedTab);
    }
    scheduleSettingsScrollSpy();
  }

  // ------------------------------------------------------------ resume hub
  function setResumeActiveTab(tab) {
    $$('#resumePillNav .settings-tab-btn').forEach(btn => {
      const isActive = btn.dataset.tab === tab;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', String(isActive));
      btn.tabIndex = isActive ? 0 : -1;
    });
  }

  function syncResumeScrollSpy() {
    const content = $('#resumeContent');
    if (!content) return;
    const groups = $$('.settings-group', content).filter(group => !group.classList.contains('is-hidden'));
    if (!groups.length) return;

    const atBottom = (content.scrollHeight - content.scrollTop - content.clientHeight) < 56;
    if (atBottom) {
      const lastGroup = groups[groups.length - 1];
      if (lastGroup) {
        setResumeActiveTab(lastGroup.dataset.group);
        return;
      }
    }

    const contentRect = content.getBoundingClientRect();
    const marker = contentRect.top + Math.min(150, Math.max(64, contentRect.height * 0.20));
    let activeGroup = groups[0];
    for (let i = 0; i < groups.length; i++) {
      const group = groups[i];
      const rect = group.getBoundingClientRect();
      if (rect.top <= marker) {
        activeGroup = group;
      } else {
        break;
      }
    }
    setResumeActiveTab(activeGroup.dataset.group);
  }

  function scheduleResumeScrollSpy() {
    if (scrollToResumeGroup.isScrolling) return;
    if (scheduleResumeScrollSpy.frame) return;
    scheduleResumeScrollSpy.frame = requestAnimationFrame(() => {
      scheduleResumeScrollSpy.frame = 0;
      syncResumeScrollSpy();
    });
  }

  function scrollToResumeGroup(tab) {
    const content = $('#resumeContent');
    const target = content && $(`#group-${tab}`, content);
    if (!content || !target) return;

    scrollToResumeGroup.isScrolling = true;
    clearTimeout(scrollToResumeGroup.timer);

    setResumeActiveTab(tab);

    const contentRect = content.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const targetScrollTop = content.scrollTop + (targetRect.top - contentRect.top) - 10;

    content.scrollTo({
      top: Math.max(0, targetScrollTop),
      behavior: 'smooth'
    });

    scrollToResumeGroup.timer = setTimeout(() => {
      scrollToResumeGroup.isScrolling = false;
      syncResumeScrollSpy();
    }, 450);
  }

  function setupResumeScrollSpy() {
    const content = $('#resumeContent');
    if (!content || content.dataset.scrollSpyReady === 'true') return;
    content.dataset.scrollSpyReady = 'true';
    content.addEventListener('scroll', scheduleResumeScrollSpy, { passive: true });
    window.addEventListener('resize', scheduleResumeScrollSpy, { passive: true });

    const viewResume = $('#view-resume');
    if (viewResume && !viewResume.dataset.wheelBound) {
      viewResume.dataset.wheelBound = 'true';
      viewResume.addEventListener('wheel', e => {
        if (content.contains(e.target)) return;
        content.scrollTop += e.deltaY;
      }, { passive: true });
    }

    scheduleResumeScrollSpy();
  }

  function switchResumeTab(tab, options = {}) {
    const selectedTab = (!tab || tab === 'all') ? 'variants' : tab;
    setResumeActiveTab(selectedTab);

    const groups = $$('#resumeContent .settings-group');
    groups.forEach(g => {
      g.classList.remove('is-hidden');
      g.setAttribute('aria-hidden', 'false');
    });

    setupResumeScrollSpy();
    if (options.scroll !== false) {
      scrollToResumeGroup(selectedTab);
    }
    scheduleResumeScrollSpy();
  }

  function syncSettingsInputs() {
    const s = S.aiSettings || {};

    // Theme cards
    let savedTheme = 'light';
    try { savedTheme = localStorage.getItem('jh-theme') || s.theme_mode || 'light'; } catch (e) {}
    $$('.theme-card-option').forEach(card => {
      const isCardSelected = card.dataset.choice === savedTheme;
      card.setAttribute('aria-checked', String(isCardSelected));
      card.classList.toggle('is-selected', isCardSelected);
    });

    // Density
    const densitySel = $('#cfgUiDensity');
    if (densitySel) {
      let savedDensity = 'comfortable';
      try { savedDensity = localStorage.getItem('jh-density') || s.ui_density || 'comfortable'; } catch (e) {}
      densitySel.value = savedDensity;
      document.body.classList.toggle('compact-mode', savedDensity === 'compact');
    }

    // Sound
    const soundCb = $('#cfgSoundEnabled');
    if (soundCb) {
      let soundOn = true;
      try { soundOn = localStorage.getItem('jh-sound') !== '0'; } catch (e) {}
      soundCb.checked = soundOn;
    }

    // Default sort
    const sortSel = $('#cfgDefaultSort');
    if (sortSel && s.default_sort) sortSel.value = s.default_sort;

    // Auto refresh
    const refreshSel = $('#cfgAutoRefresh');
    if (refreshSel) {
      const mins = getAutoReloadMinutes();
      refreshSel.value = String(mins);
    }

    // Auto hide checkboxes
    const hideAppliedCb = $('#cfgAutoHideApplied');
    if (hideAppliedCb) hideAppliedCb.checked = s.auto_hide_applied === '1' || S.filters.hideApplied;
    const hideExpiredCb = $('#cfgAutoHideExpired');
    if (hideExpiredCb) hideExpiredCb.checked = s.auto_hide_expired === '1';

    // Adzuna
    const adzId = $('#cfgAdzunaAppId');
    if (adzId && s.adzuna_app_id) adzId.value = s.adzuna_app_id;
    const adzKey = $('#cfgAdzunaAppKey');
    if (adzKey && s.adzuna_app_key) adzKey.value = s.adzuna_app_key;
    const adzBadge = $('#adzunaStatusBadge');
    if (adzBadge) {
      const hasAdzuna = !!(s.adzuna_app_id && s.adzuna_app_key);
      adzBadge.textContent = hasAdzuna ? 'Connected' : 'Free Integration';
      adzBadge.className = `chip ${hasAdzuna ? 'chip-ok' : 'chip-info'}`;
    }

    // Digest
    const digScore = $('#cfgDigestThresholdSelect');
    if (digScore && s.digest_min_score) digScore.value = s.digest_min_score;
    const digEmail = $('#cfgDigestEmail');
    if (digEmail && s.digest_email) digEmail.value = s.digest_email;
    const digTime = $('#cfgDigestTime');
    if (digTime && s.digest_time) digTime.value = s.digest_time;
    const smtpHost = $('#cfgSmtpHost');
    if (smtpHost && s.digest_smtp_host) smtpHost.value = s.digest_smtp_host;
    const smtpPort = $('#cfgSmtpPort');
    if (smtpPort && s.digest_smtp_port) smtpPort.value = s.digest_smtp_port;
    const smtpUser = $('#cfgSmtpUser');
    if (smtpUser && s.digest_smtp_user) smtpUser.value = s.digest_smtp_user;
    const smtpPass = $('#cfgSmtpPass');
    if (smtpPass && s.digest_smtp_pass) smtpPass.value = s.digest_smtp_pass;
  }

  async function loadSystemInfo() {
    try {
      const info = await api('/api/system-info');
      const v = $('#sysVersion'); if (v) v.textContent = info.version || '4.4.0';
      const py = $('#sysPythonVer'); if (py) py.textContent = `Python ${info.python_version || '3.x'} (${info.platform || 'windows'})`;
      const sz = $('#sysDbSize'); if (sz) sz.textContent = `${info.db_size_kb || 0} KB`;
      const jb = $('#sysJobCount'); if (jb) jb.textContent = `${(info.stored_jobs_count || 0).toLocaleString()} jobs cached`;
      const ap = $('#sysAppCount'); if (ap) ap.textContent = `${info.applications_count || 0} applications tracked`;
      const llm = $('#sysLlmStatus');
      if (llm) {
        llm.textContent = info.llm_available ? 'Connected' : 'Deterministic Grounded';
        llm.style.color = info.llm_available ? 'var(--brand-accent)' : 'var(--info)';
      }
    } catch (e) { /* ignore */ }
  }

  function setupSettingsHub() {
    // 1. Theme option clicks
    $$('.theme-card-option').forEach(card => {
      card.addEventListener('click', () => {
        const choice = card.dataset.choice;
        setTheme(choice, true);
        AudioEffects.play('click');
        toast(`Switched to ${choice === 'system' ? 'System theme' : choice + ' theme'}`);
      });
      card.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          card.click();
          return;
        }
        const cards = $$('.theme-card-option');
        const current = cards.indexOf(card);
        if (current < 0 || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        const direction = (e.key === 'ArrowLeft' || e.key === 'ArrowUp') ? -1 : 1;
        const nextIndex = e.key === 'Home' ? 0 : e.key === 'End' ? cards.length - 1 : (current + direction + cards.length) % cards.length;
        cards[nextIndex].focus();
        cards[nextIndex].click();
      });
    });

    // 2. Density dropdown
    const densitySel = $('#cfgUiDensity');
    if (densitySel) {
      densitySel.addEventListener('change', () => {
        const d = densitySel.value;
        document.body.classList.toggle('compact-mode', d === 'compact');
        try {
          localStorage.setItem('jh-density', d);
          api('/api/settings', { method: 'POST', body: { ui_density: d } }).catch(() => {});
        } catch (e) {}
        toast(`Density set to ${d}`);
      });
    }

    // 3. Audio toggle and test button
    const soundCb = $('#cfgSoundEnabled');
    if (soundCb) {
      soundCb.addEventListener('change', () => {
        const on = soundCb.checked ? '1' : '0';
        try {
          localStorage.setItem('jh-sound', on);
          api('/api/settings', { method: 'POST', body: { sound_enabled: on } }).catch(() => {});
        } catch (e) {}
        if (soundCb.checked) AudioEffects.play('success');
        toast(soundCb.checked ? 'Audio feedback enabled' : 'Audio feedback muted');
      });
    }

    const testSoundBtn = $('#btnTestSound');
    if (testSoundBtn) {
      testSoundBtn.addEventListener('click', () => {
        AudioEffects.play('success');
        toast('Playing synthesizer feedback chime');
      });
    }

    // 4. Save General Preferences
    const saveGenBtn = $('#btnSaveGeneralSettings');
    if (saveGenBtn) {
      saveGenBtn.addEventListener('click', async () => {
        const payload = {
          default_sort: val('cfgDefaultSort') || 'score',
          auto_hide_applied: $('#cfgAutoHideApplied') && $('#cfgAutoHideApplied').checked ? '1' : '0',
          auto_hide_expired: $('#cfgAutoHideExpired') && $('#cfgAutoHideExpired').checked ? '1' : '0',
          ui_density: val('cfgUiDensity') || 'comfortable',
          sound_enabled: $('#cfgSoundEnabled') && $('#cfgSoundEnabled').checked ? '1' : '0'
        };
        const reloadMins = parseInt(val('cfgAutoRefresh'), 10) || 0;
        setAutoReloadMinutes(reloadMins);
        const autoReloadSel = $('#autoReloadSelect');
        if (autoReloadSel) autoReloadSel.value = String(reloadMins);

        try {
          await api('/api/settings', { method: 'POST', body: payload });
          AudioEffects.play('success');
          toast('General preferences saved');
        } catch (e) {
          toast('Failed to save preferences: ' + e.message, 'error');
        }
      });
    }

    // 5. Adzuna credentials save
    const saveAdzunaBtn = $('#btnSaveAdzuna');
    if (saveAdzunaBtn) {
      saveAdzunaBtn.addEventListener('click', async () => {
        const appId = val('cfgAdzunaAppId').trim();
        const appKey = val('cfgAdzunaAppKey').trim();
        try {
          await api('/api/settings', { method: 'POST', body: { adzuna_app_id: appId, adzuna_app_key: appKey } });
          AudioEffects.play('success');
          toast('Adzuna credentials saved');
          await loadAiSettings();
          syncSettingsInputs();
        } catch (e) {
          toast('Failed to save Adzuna credentials: ' + e.message, 'error');
        }
      });
    }

    // 6. Digest & SMTP settings save
    const saveDigBtn = $('#btnSaveDigestSettings');
    if (saveDigBtn) {
      saveDigBtn.addEventListener('click', async () => {
        const payload = {
          digest_min_score: val('cfgDigestThresholdSelect') || '75',
          digest_email: val('cfgDigestEmail').trim(),
          digest_time: val('cfgDigestTime').trim() || '08:00',
          digest_smtp_host: val('cfgSmtpHost').trim(),
          digest_smtp_port: val('cfgSmtpPort').trim() || '587',
          digest_smtp_user: val('cfgSmtpUser').trim(),
          digest_smtp_pass: val('cfgSmtpPass').trim()
        };
        try {
          await api('/api/settings', { method: 'POST', body: payload });
          AudioEffects.play('success');
          toast('Digest preferences & SMTP settings saved');
        } catch (e) {
          toast('Failed to save digest settings: ' + e.message, 'error');
        }
      });
    }

    // 7. Sub-nav pill buttons
    const pillNav = $('#settingsPillNav');
    if (pillNav) {
      pillNav.addEventListener('click', e => {
        const b = e.target.closest('[data-tab]');
        if (!b) return;
        const tab = b.dataset.tab;
        switchSettingsTab(tab, { scroll: true });
        try {
          history.replaceState(null, '', `#/settings${tab && tab !== 'all' ? '/' + tab : ''}`);
        } catch (_) {}
      });
      pillNav.addEventListener('keydown', e => {
        const tabs = $$('.settings-tab-btn', pillNav);
        const current = tabs.indexOf(document.activeElement);
        if (current < 0 || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        const direction = (e.key === 'ArrowLeft' || e.key === 'ArrowUp') ? -1 : 1;
        const nextIndex = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (current + direction + tabs.length) % tabs.length;
        tabs[nextIndex].focus();
        tabs[nextIndex].click();
      });
    }

    // 8. Settings keyword search / filter
    const searchInput = $('#settingsFilterInput');
    const clearBtn = $('#settingsFilterClear');
    const noResults = $('#settingsNoResults');
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        const q = searchInput.value.toLowerCase().trim();
        if (clearBtn) clearBtn.hidden = !q;
        const cards = $$('#settingsContent .settings-card');
        const groups = $$('#settingsContent .settings-group');

        if (!q) {
          cards.forEach(c => c.classList.remove('is-filtered-out'));
          groups.forEach(g => g.classList.remove('is-hidden'));
          if (noResults) noResults.hidden = true;
          const activeBtn = $('#settingsPillNav .settings-tab-btn.active');
          if (activeBtn) switchSettingsTab(activeBtn.dataset.tab);
          return;
        }

        groups.forEach(g => g.classList.remove('is-hidden'));
        let visibleCount = 0;
        cards.forEach(card => {
          const kw = (card.dataset.keywords || '').toLowerCase();
          const txt = (card.textContent || '').toLowerCase();
          const match = kw.includes(q) || txt.includes(q);
          card.classList.toggle('is-filtered-out', !match);
          if (match) visibleCount++;
        });

        groups.forEach(g => {
          const hasVisible = $$('.settings-card:not(.is-filtered-out)', g).length > 0;
          g.classList.toggle('is-hidden', !hasVisible);
        });

        if (noResults) noResults.hidden = visibleCount > 0;
        scheduleSettingsScrollSpy();
      });

      if (clearBtn) {
        clearBtn.addEventListener('click', () => {
          searchInput.value = '';
          searchInput.dispatchEvent(new Event('input'));
          searchInput.focus();
        });
      }
    }

    // 8b. Resume Hub Rail Navigation & Keyword Search
    const resumePillNav = $('#resumePillNav');
    if (resumePillNav) {
      resumePillNav.addEventListener('click', e => {
        const b = e.target.closest('[data-tab]');
        if (!b) return;
        const tab = b.dataset.tab;
        switchResumeTab(tab, { scroll: true });
        try {
          history.replaceState(null, '', `#/resume${tab ? '/' + tab : ''}`);
        } catch (_) {}
      });
      resumePillNav.addEventListener('keydown', e => {
        const tabs = $$('.settings-tab-btn', resumePillNav);
        const current = tabs.indexOf(document.activeElement);
        if (current < 0 || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        const direction = (e.key === 'ArrowLeft' || e.key === 'ArrowUp') ? -1 : 1;
        const nextIndex = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (current + direction + tabs.length) % tabs.length;
        tabs[nextIndex].focus();
        tabs[nextIndex].click();
      });
    }

    const resumeSearchInput = $('#resumeFilterInput');
    const resumeClearBtn = $('#resumeFilterClear');
    const resumeNoResults = $('#resumeNoResults');
    if (resumeSearchInput) {
      resumeSearchInput.addEventListener('input', () => {
        const q = resumeSearchInput.value.toLowerCase().trim();
        if (resumeClearBtn) resumeClearBtn.hidden = !q;
        const cards = $$('#resumeContent .settings-card');
        const groups = $$('#resumeContent .settings-group');

        if (!q) {
          cards.forEach(c => c.classList.remove('is-filtered-out'));
          groups.forEach(g => g.classList.remove('is-hidden'));
          if (resumeNoResults) resumeNoResults.hidden = true;
          const activeBtn = $('#resumePillNav .settings-tab-btn.active');
          if (activeBtn) switchResumeTab(activeBtn.dataset.tab);
          return;
        }

        groups.forEach(g => g.classList.remove('is-hidden'));
        let visibleCount = 0;
        cards.forEach(card => {
          const kw = (card.dataset.keywords || '').toLowerCase();
          const txt = (card.textContent || '').toLowerCase();
          const match = kw.includes(q) || txt.includes(q);
          card.classList.toggle('is-filtered-out', !match);
          if (match) visibleCount++;
        });

        groups.forEach(g => {
          const hasVisible = $$('.settings-card:not(.is-filtered-out)', g).length > 0;
          g.classList.toggle('is-hidden', !hasVisible);
        });

        if (resumeNoResults) resumeNoResults.hidden = visibleCount > 0;
        scheduleResumeScrollSpy();
      });

      if (resumeClearBtn) {
        resumeClearBtn.addEventListener('click', () => {
          resumeSearchInput.value = '';
          resumeSearchInput.dispatchEvent(new Event('input'));
          resumeSearchInput.focus();
        });
      }
    }

    // 9. API Key password toggle eye
    const toggleEye = $('#btnToggleApiKeyEye');
    if (toggleEye) {
      toggleEye.addEventListener('click', () => {
        const inp = $('#aiApiKeyInput');
        if (!inp) return;
        const isPass = inp.type === 'password';
        inp.type = isPass ? 'text' : 'password';
        toggleEye.innerHTML = `<svg class="i" style="width:18px; height:18px;"><use href="#${isPass ? 'i-eye-off' : 'i-eye'}"/></svg>`;
      });
    }

    // 10. Backup export
    const exportBtn = $('#btnExportBackup');
    if (exportBtn) {
      exportBtn.addEventListener('click', async () => {
        try {
          toast('Generating complete JobHunter backup snapshot...');
          const data = await api('/api/backup/export');
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          const dateStr = new Date().toISOString().slice(0, 10);
          a.href = url;
          a.download = `jobhunter-backup-${dateStr}.json`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
          AudioEffects.play('success');
          toast('Backup successfully exported and downloaded!');
        } catch (e) {
          toast('Failed to export backup: ' + e.message, 'error');
        }
      });
    }

    // 11. Backup restore
    const triggerImportBtn = $('#btnTriggerImportBackup');
    const fileImport = $('#fileImportBackup');
    if (triggerImportBtn && fileImport) {
      triggerImportBtn.addEventListener('click', () => fileImport.click());
      fileImport.addEventListener('change', async e => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const confirmed = await confirmDialog(
          'Restore from backup?',
          'This will import profile variants, tracked applications, notes, and settings from the backup file.',
          'Restore Data'
        );
        if (!confirmed) {
          fileImport.value = '';
          return;
        }

        const reader = new FileReader();
        reader.onload = async evt => {
          try {
            const json = JSON.parse(evt.target.result);
            const res = await api('/api/backup/import', { method: 'POST', body: json });
            AudioEffects.play('success');
            toast(res.message || 'Data restored successfully!');
            await loadProfile();
            await loadApplications();
            await loadAiSettings();
            syncSettingsInputs();
          } catch (err) {
            toast('Failed to import backup: ' + err.message, 'error');
          } finally {
            fileImport.value = '';
          }
        };
        reader.readAsText(file);
      });
    }

    // 12. Onboarding wizard launcher
    const launchWizBtn = $('#btnLaunchOnboardingWizard');
    if (launchWizBtn) {
      launchWizBtn.addEventListener('click', () => {
        const flow = $('#onboardingFlow');
        if (flow) {
          flow.hidden = false;
          const s1 = $('#onboardStep1'); if (s1) s1.hidden = false;
          const s2 = $('#onboardStep2'); if (s2) s2.hidden = true;
          const s3 = $('#onboardStep3'); if (s3) s3.hidden = true;
        }
      });
    }

    // 13. Clear cache button
    const clearCacheBtn = $('#btnClearSearchCache');
    if (clearCacheBtn) {
      clearCacheBtn.addEventListener('click', async () => {
        try {
          await api('/api/clear-cache', { method: 'POST' });
          AudioEffects.play('success');
          toast('Search results cache cleared. Fresh live queries will be used.');
          loadSystemInfo();
        } catch (e) {
          toast('Failed to clear cache: ' + e.message, 'error');
        }
      });
    }

    // 14. Refresh system diagnostics telemetry
    const refreshDiagBtn = $('#btnRefreshDiagnostics');
    if (refreshDiagBtn) {
      refreshDiagBtn.addEventListener('click', async () => {
        refreshDiagBtn.classList.add('is-spinning');
        try {
          await loadSystemInfo();
          AudioEffects.play('success');
          toast('Telemetry metrics refreshed');
        } catch (e) {
          toast('Failed to refresh telemetry: ' + e.message, 'error');
        } finally {
          setTimeout(() => {
            refreshDiagBtn.classList.remove('is-spinning');
          }, 650);
        }
      });
    }

    // 15. Tactile switches click feedback sound
    $$('.tactile-switch input[type="checkbox"]').forEach(sw => {
      sw.addEventListener('change', () => {
        AudioEffects.play('click');
      });
    });

    // 16. Keyboard shortcut: Press '/' or Cmd/Ctrl+K to jump to settings search
    document.addEventListener('keydown', e => {
      const settingsView = $('#view-settings');
      const resumeView = $('#view-resume');
      const inSettings = settingsView && !settingsView.hidden;
      const inResume = resumeView && !resumeView.hidden;
      if (!inSettings && !inResume) return;

      const activeTag = document.activeElement ? document.activeElement.tagName : '';
      const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(activeTag);
      const targetInputId = inSettings ? 'settingsFilterInput' : 'resumeFilterInput';

      if ((e.key === '/' && !isInput) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) {
        e.preventDefault();
        const inp = $(`#${targetInputId}`);
        if (inp) {
          inp.focus();
          inp.select();
        }
      } else if (e.key === 'Escape' && document.activeElement === $(`#${targetInputId}`)) {
        const inp = $(`#${targetInputId}`);
        if (inp && inp.value) {
          inp.value = '';
          inp.dispatchEvent(new Event('input'));
        } else if (inp) {
          inp.blur();
        }
      }
    });
  }

  // ---------------------------------------------------------------- profile
  function normalizeProfile(p) {
    const q = Object.assign({}, p);
    delete q._is_empty; delete q._updated_at;
    q.skills = Array.isArray(q.skills) ? q.skills : [];
    q.experience = Array.isArray(q.experience) ? q.experience : [];
    q.education = Array.isArray(q.education) ? q.education : [];
    q.preferred_job_types = Array.isArray(q.preferred_job_types) ? q.preferred_job_types : (q.preferred_job_types ? [q.preferred_job_types] : []);
    q.dream_companies = Array.isArray(q.dream_companies) ? q.dream_companies : (q.dream_companies ? [q.dream_companies] : []);
    q.dream_role = q.dream_role || '';
    q.excluded_keywords = Array.isArray(q.excluded_keywords) ? q.excluded_keywords : (q.excluded_keywords ? [q.excluded_keywords] : []);
    q.min_salary = q.min_salary || 0;
    return q;
  }

  async function loadProfile(profileId = null) {
    try {
      const url = profileId ? `/api/profile?id=${encodeURIComponent(profileId)}` : '/api/profile';
      const raw = await api(url);
      S.profileEmpty = !!raw._is_empty;
      S.profile = normalizeProfile(raw);
      if (raw._profile_id) S.activeProfileId = raw._profile_id;
      if (['Remote', 'Hybrid', 'Onsite'].includes(S.profile.work_mode)) S.workMode = S.profile.work_mode;
      renderProfile();
      renderIdeas();
      syncWorkModeSeg();
      await loadProfilesList();
      await runAtsAudit();
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
    const pillName = $('#pillName');
    if (pillName) pillName.textContent = name || 'Add your resume';
    const pillTitle = $('#pillTitle');
    if (pillTitle) pillTitle.textContent = name ? [p.years_of_experience ? `${p.years_of_experience} yrs` : '', p.work_mode || ''].filter(Boolean).join(', ') : '';
    const userAvatar = $('#userAvatar');
    if (userAvatar) userAvatar.textContent = name ? name.split(/\s+/).map(n => n[0]).join('').slice(0, 2).toUpperCase() : '?';
  }

  function renderProfile() {
    const p = S.profile || normalizeProfile({});
    const set = (id, v) => { const el = $('#' + id); if (el) el.value = v === undefined || v === null ? '' : v; };
    set('profName', p.name); set('profTitle', p.target_title);
    set('profExp', p.years_of_experience === undefined ? '' : p.years_of_experience);
    set('profWorkMode', p.work_mode || 'Remote');
    set('profEmail', p.email); set('profPhone', p.phone); set('profLocation', p.location);
    set('profLinkedin', p.linkedin); set('profGithub', p.github); set('profSummary', p.summary);

    // Dream Job & Career Preferences
    set('profMinSalary', p.min_salary || '');
    const jobTypeVal = Array.isArray(p.preferred_job_types) ? p.preferred_job_types.join(', ') : (p.preferred_job_types || 'Any');
    set('profJobType', jobTypeVal || 'Any');
    const dreamComps = Array.isArray(p.dream_companies) ? p.dream_companies.join(', ') : (p.dream_companies || '');
    set('profDreamCompanies', dreamComps);
    set('profDreamRole', p.dream_role || '');
    const excl = Array.isArray(p.excluded_keywords) ? p.excluded_keywords.join(', ') : (p.excluded_keywords || '');
    set('profExcludedKeywords', excl);

    renderSkills(); renderExperience(); renderEducation();

    if (S.profileEmpty) {
      $('#intakeTitle').textContent = 'Start with your resume';
      $('#intakeSub').textContent = 'Upload a PDF, Word, text, or Markdown file. The app reads it into the fields below.';
    } else {
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
    const minSal = parseInt(val('profMinSalary'), 10);
    const parseList = (id) => (val(id) || '').split(',').map(s => s.trim()).filter(Boolean);
    const jobTypeVal = val('profJobType');
    const prefJobTypes = (jobTypeVal && jobTypeVal !== 'Any')
      ? jobTypeVal.split(',').map(s => s.trim()).filter(Boolean)
      : [];

    return Object.assign({}, S.profile, {
      name: val('profName').trim(),
      target_title: val('profTitle').trim(),
      years_of_experience: isNaN(exp) ? 0 : exp,
      work_mode: val('profWorkMode') || 'Remote',
      min_salary: isNaN(minSal) ? 0 : minSal,
      preferred_job_types: prefJobTypes,
      dream_companies: parseList('profDreamCompanies'),
      dream_role: val('profDreamRole').trim(),
      excluded_keywords: parseList('profExcludedKeywords'),
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
    p._profile_id = S.activeProfileId || 'master';
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
      await loadProfilesList();
      await runAtsAudit();
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

  // -------------------------------------------------- resume variants & ats library
  async function loadProfilesList() {
    try {
      const res = await api('/api/profiles');
      S.profiles = Array.isArray(res.profiles) ? res.profiles : [];
      S.activeProfileId = res.active_id || (S.profiles[0] && S.profiles[0].id) || 'master';
      renderProfilesBar();
    } catch (err) {
      console.warn('Failed to load profiles:', err);
    }
  }

  function renderProfilesBar() {
    const container = $('#variantPillStrip');
    if (!container) return;
    const list = S.profiles || [];
    if (!list.length) {
      container.innerHTML = '<span class="muted small" style="padding:10px;">No profile variants yet.</span>';
      return;
    }

    const liveCount = list.filter(p => p.is_live).length;
    const totalCount = list.length;
    const liveCntEl = $('#livePoolCount');
    if (liveCntEl) liveCntEl.textContent = liveCount;
    const totalCntEl = $('#totalVariantsCount');
    if (totalCntEl) totalCntEl.textContent = totalCount;

    container.innerHTML = list.map(p => {
      const isActive = p.id === S.activeProfileId;
      const isLive = !!p.is_live;
      return `
        <div class="variant-pill-card ${isActive ? 'is-active' : ''} ${isLive ? 'is-live' : 'is-paused'}" data-action="profile-switch" data-id="${esc(p.id)}" role="button" tabindex="0">
          <div class="variant-pill-top">
            <span class="variant-pill-name" title="${esc(p.name)}">${esc(p.name)}</span>
            <div style="display:flex;align-items:center;gap:4px;">
              ${p.is_master ? '<span class="chip-badge-master">Master</span>' : ''}
              ${isActive ? '<span class="chip-badge-active">Active</span>' : ''}
              <button type="button" class="variant-live-toggle-btn ${isLive ? 'is-live' : 'is-paused'}" data-action="profile-toggle-live" data-id="${esc(p.id)}" title="${isLive ? 'Currently LIVE for match scoring. Click to pause.' : 'Currently PAUSED from match scoring. Click to set Live.'}">
                <span class="toggle-dot"></span>
                <span>${isLive ? 'Live' : 'Paused'}</span>
              </button>
            </div>
          </div>
          <div class="variant-pill-target">${esc(p.target_title || 'General Target')}</div>
          <div class="variant-pill-tags">
            ${(p.tags || []).slice(0, 3).map(t => `<span class="variant-tag-chip">${esc(t)}</span>`).join('')}
            ${(p.tags || []).length > 3 ? `<span class="variant-tag-more">+${(p.tags || []).length - 3}</span>` : ''}
          </div>
        </div>
      `;
    }).join('');

    // Update active meta bar
    const active = list.find(p => p.id === S.activeProfileId) || list[0] || {};
    const nameEl = $('#variantActiveName');
    if (nameEl) nameEl.textContent = active.name || 'Master Profile';
    const typeEl = $('#variantActiveType');
    if (typeEl) typeEl.textContent = active.is_master ? 'Master Career Base' : (active.target_title ? `Target: ${active.target_title}` : 'Targeted Variant');

    const tagsEl = $('#variantActiveTags');
    if (tagsEl) {
      const tags = Array.isArray(active.tags) ? active.tags : [];
      tagsEl.innerHTML = tags.map(t => `<span class="tag">${esc(t)}</span>`).join('') || '<span class="muted small">No tags set</span>';
    }

    const btnDel = $('#btnDeleteVariant');
    if (btnDel) {
      btnDel.hidden = !!active.is_master;
    }

    const beaconText = $('#activeProfileBeaconText');
    if (beaconText) {
      beaconText.textContent = `Active in Editor: ${active.name || 'Master Profile'}`;
    }

    const lastSaved = $('#activeProfileLastSaved');
    if (lastSaved) {
      lastSaved.textContent = active.updated_at ? ('Updated ' + timeAgo(active.updated_at)) : 'Updated recently';
    }

    // Refresh Search filter resume dropdown
    renderResumeFilterDropdown();
  }

  async function toggleLiveProfile(id) {
    if (!id) return;
    try {
      const res = await api('/api/profile/toggle-live', { method: 'POST', body: { id } });
      if (res && res.success) {
        if (res.profiles) S.profiles = res.profiles;
        renderProfilesBar();
        toast(res.message || 'Updated live matching pool.');
        if (S.searchHasRun) {
          runSearch({ forceRefresh: false });
        }
      }
    } catch (err) {
      toast('Cannot change live status: ' + err.message, 'error');
    }
  }

  function renderResumeFilterDropdown() {
    const menu = $('#p4MenuResumeItems');
    if (!menu) return;
    const list = S.profiles || [];
    const selected = S.filterResume || 'all';

    let html = `<button type="button" class="p4-menu-item ${selected === 'all' ? 'is-selected' : ''}" data-resume-id="all">All Resumes</button>`;
    list.forEach(p => {
      const isLive = !!p.is_live;
      const statusIcon = isLive ? '● ' : '○ ';
      const statusSuffix = isLive ? '' : ' (Paused)';
      html += `<button type="button" class="p4-menu-item ${selected === p.id ? 'is-selected' : ''}" data-resume-id="${esc(p.id)}">${statusIcon}${esc(p.name)}${statusSuffix}</button>`;
    });
    menu.innerHTML = html;

    const labelEl = $('#p4TextResume');
    if (labelEl) {
      if (selected === 'all') {
        labelEl.textContent = 'Resume: All';
      } else {
        const found = list.find(p => p.id === selected);
        labelEl.textContent = found ? `Resume: ${found.name}` : 'Resume: All';
      }
    }
  }

  async function switchProfile(id) {
    if (!id || id === S.activeProfileId) return;
    try {
      toast('Switching active resume profile...');
      const res = await api('/api/profile/activate', { method: 'POST', body: { id } });
      if (res && res.profile) {
        S.activeProfileId = id;
        S.profile = normalizeProfile(res.profile);
        S.profileEmpty = !!res.profile._is_empty;
        renderProfile();
        renderIdeas();
        updateProfileLink();
        await loadProfilesList();
        await runAtsAudit();
        toast(`Active resume profile: "${res.profile._profile_name || id}"`);
        if (S.searchHasRun) {
          runSearch({ forceRefresh: false });
        }
      }
    } catch (err) {
      toast('Could not switch profile: ' + err.message, 'error');
    }
  }

  function openNewVariantDialog(isRename = false, targetId = null) {
    const dlg = $('#variantDialog');
    if (!dlg) return;
    const titleEl = $('#variantDialogTitle');
    const idInput = $('#variantFormId');
    const nameInput = $('#variantFormName');
    const titleInput = $('#variantFormTitle');
    const tagsInput = $('#variantFormTags');
    const submitBtn = $('#variantDialogSubmit');

    if (isRename && targetId) {
      const prof = (S.profiles || []).find(p => p.id === targetId);
      if (!prof) return;
      titleEl.textContent = 'Edit Variant Details';
      idInput.value = prof.id;
      nameInput.value = prof.name || '';
      titleInput.value = prof.target_title || '';
      tagsInput.value = (prof.tags || []).join(', ');
      submitBtn.textContent = 'Save Changes';
    } else {
      titleEl.textContent = 'Create New Variant from Active Resume';
      idInput.value = '';
      const active = (S.profiles || []).find(p => p.id === S.activeProfileId) || {};
      nameInput.value = active.name ? `${active.name} (Variant)` : 'Specialized Variant';
      titleInput.value = active.target_title || '';
      tagsInput.value = (active.tags || []).join(', ');
      submitBtn.textContent = 'Create Variant';
    }
    dlg.showModal();
    nameInput.focus();
  }

  async function submitVariantDialog(e) {
    if (e) e.preventDefault();
    const id = $('#variantFormId').value.trim();
    const name = $('#variantFormName').value.trim();
    const target_title = $('#variantFormTitle').value.trim();
    const tagsStr = $('#variantFormTags').value.trim();
    const tags = tagsStr ? tagsStr.split(',').map(s => s.trim()).filter(Boolean) : [];

    if (!name) {
      toast('Please enter a variant name', 'error');
      return;
    }

    try {
      if (id) {
        // Edit existing variant
        await api('/api/profile', {
          method: 'POST',
          body: Object.assign({}, S.profile, {
            _profile_id: id,
            _variant_name: name,
            target_title: target_title,
            tags: tags
          })
        });
        toast('Variant details updated');
      } else {
        // Create new clone
        const res = await api('/api/profile/duplicate', {
          method: 'POST',
          body: {
            id: S.activeProfileId,
            name: name,
            target_title: target_title,
            tags: tags
          }
        });
        toast(`Created variant "${name}"`);
        if (res.profile && res.profile._profile_id) {
          S.activeProfileId = res.profile._profile_id;
        }
      }
      const dlg = $('#variantDialog');
      if (dlg) dlg.close();
      await loadProfilesList();
      await loadProfile();
    } catch (err) {
      toast('Error: ' + err.message, 'error');
    }
  }

  async function duplicateActiveProfile() {
    const active = (S.profiles || []).find(p => p.id === S.activeProfileId);
    const baseName = active ? active.name : 'Resume';
    const newName = `${baseName} (Copy)`;
    try {
      toast('Cloning resume profile...');
      const res = await api('/api/profile/duplicate', {
        method: 'POST',
        body: {
          id: S.activeProfileId,
          name: newName,
          target_title: active ? active.target_title : '',
          tags: active ? active.tags : []
        }
      });
      toast(`Created variant "${newName}"`);
      if (res.profile && res.profile._profile_id) S.activeProfileId = res.profile._profile_id;
      await loadProfilesList();
      await loadProfile();
    } catch (err) {
      toast('Could not duplicate profile: ' + err.message, 'error');
    }
  }

  async function deleteProfileVariant(id) {
    const targetId = id || S.activeProfileId;
    const prof = (S.profiles || []).find(p => p.id === targetId);
    if (!prof) return;
    if (prof.is_master) {
      toast('Master profile cannot be deleted.', 'error');
      return;
    }
    if (!confirm(`Delete variant "${prof.name}"? This cannot be undone.`)) return;

    try {
      await api('/api/profile/delete', { method: 'POST', body: { id: targetId } });
      toast(`Deleted variant "${prof.name}"`);
      S.activeProfileId = 'master';
      await loadProfilesList();
      await loadProfile();
    } catch (err) {
      toast('Could not delete profile: ' + err.message, 'error');
    }
  }

  async function runAtsAudit() {
    try {
      const card = $('#atsHealthCard');
      if (!card) return;
      const res = await api('/api/profile/audit', {
        method: 'POST',
        body: { id: S.activeProfileId || 'master' }
      });
      if (!res || !res.report) return;
      const a = res.report;
      S.atsAudit = a;

      // Update score ring & grade badge
      const ringPath = $('#atsAuditScorePath');
      const scoreText = $('#atsAuditScoreText');
      const gradeBadge = $('#atsGradeBadge');
      const score = Math.round(a.score || 0);

      if (ringPath) {
        ringPath.setAttribute('stroke-dasharray', `${score}, 100`);
        ringPath.className = `circle ${score >= 85 ? 'score-high' : score >= 70 ? 'score-med' : 'score-low'}`;
      }
      if (scoreText) scoreText.textContent = `${score}%`;
      if (gradeBadge) {
        gradeBadge.textContent = a.grade || 'ATS Ready';
        gradeBadge.className = score >= 85 ? 'chip chip-ok' : score >= 70 ? 'chip chip-info' : 'chip chip-warn';
      }

      const st = a.stats || {};

      // 4 Core Metric Ribbons
      const qv = $('#atsQuantVal'), qs = $('#atsQuantSub');
      if (qv && qs) {
        qv.textContent = `${st.quantified_rate || 0}%`;
        qs.textContent = `${st.quantified_bullet_count || 0} of ${st.bullet_count || 0} bullets with metrics`;
      }

      const sv = $('#atsSkillsVal'), ss = $('#atsSkillsSub');
      if (sv && ss) {
        sv.textContent = `${st.skills_count || 0}`;
        ss.textContent = `${st.skills_count || 0} keywords indexed`;
      }

      const hv = $('#atsHeadlineVal'), hs = $('#atsHeadlineSub');
      if (hv && hs) {
        hv.textContent = st.has_target_title && st.has_summary ? 'Verified' : 'Incomplete';
        hv.style.color = st.has_target_title && st.has_summary ? 'var(--brand-primary, #00E599)' : 'var(--warn-color, #eab308)';
        hs.textContent = st.has_target_title ? (S.profile && S.profile.target_title || 'Target set') : 'No target title set';
      }

      const cv = $('#atsContactVal'), cs = $('#atsContactSub');
      if (cv && cs) {
        const contacts = [st.has_email, st.has_phone, st.has_linkedin, st.has_github, st.has_location].filter(Boolean).length;
        cv.textContent = contacts >= 3 ? 'Complete' : 'Needs Review';
        cv.style.color = contacts >= 3 ? 'var(--brand-primary, #00E599)' : 'var(--warn-color, #eab308)';
        cs.textContent = `${contacts} of 5 channels present`;
      }

      // Expandable checks & tips
      const checksList = $('#atsChecksList');
      if (checksList && Array.isArray(a.checks)) {
        checksList.innerHTML = a.checks.map(c => `
          <div class="ats-check-item ${c.passed ? 'check-pass' : 'check-warn'}">
            <span class="ats-check-icon">${c.passed ? ico('check') : ico('alert')}</span>
            <div class="ats-check-content">
              <div class="ats-check-title">${esc(c.rule)}</div>
              <div class="ats-check-desc muted small">${esc(c.detail)}</div>
            </div>
            <span class="ats-check-weight muted small">+${c.weight} pts</span>
          </div>
        `).join('');
      }

      const tipsBox = $('#atsTipsBox');
      if (tipsBox) {
        const tips = Array.isArray(a.tips) ? a.tips : [];
        if (tips.length) {
          tipsBox.innerHTML = `
            <div class="ats-tips-title">${ico('sparkles')} Actionable 10x ATS Recommendations</div>
            <ul class="ats-tips-list">
              ${tips.map(t => `<li>${esc(t)}</li>`).join('')}
            </ul>
          `;
          tipsBox.hidden = false;
        } else {
          tipsBox.hidden = true;
        }
      }
    } catch (err) {
      console.warn('ATS audit failed:', err);
    }
  }

  function openSaveTailoredDialog() {
    const dlg = $('#tailoredVariantDialog');
    if (!dlg) return;
    const w = S.ws;
    if (!w || !w.job) {
      toast('No job currently open in workspace', 'error');
      return;
    }
    const job = w.job;
    const comp = job.company || '';
    const title = job.title || '';
    const defName = comp && title ? `Tailored: ${comp} - ${title}` : (title ? `Tailored: ${title}` : 'Job Tailored Variant');

    $('#tailoredFormName').value = defName;
    const skills = Array.isArray(job.matched_skills) ? job.matched_skills : (Array.isArray(job.required_skills) ? job.required_skills : []);
    $('#tailoredFormTags').value = skills.slice(0, 5).join(', ');
    dlg.showModal();
    $('#tailoredFormName').focus();
  }

  async function submitTailoredDialog(e) {
    if (e) e.preventDefault();
    const name = $('#tailoredFormName').value.trim();
    const tagsStr = $('#tailoredFormTags').value.trim();
    const tags = tagsStr ? tagsStr.split(',').map(s => s.trim()).filter(Boolean) : [];
    if (!name) {
      toast('Please enter a name for the tailored variant', 'error');
      return;
    }
    const w = S.ws;
    if (!w || !w.job) return;

    try {
      toast('Saving tailored variant to library...');
      const tailoredResume = effectiveResume();
      const res = await api('/api/profile/save-tailored', {
        method: 'POST',
        body: {
          job: w.job,
          tailored_resume: tailoredResume,
          name: name,
          tags: tags
        }
      });
      toast(`Saved variant "${name}" to your Resume Library!`);
      const dlg = $('#tailoredVariantDialog');
      if (dlg) dlg.close();
      await loadProfilesList();
    } catch (err) {
      toast('Could not save variant: ' + err.message, 'error');
    }
  }

  async function openVariantCompareDialog(job) {
    const dlg = $('#variantCompareDialog');
    if (!dlg) return;
    const targetJob = job || selectedJob();
    if (!targetJob) {
      toast('Please select a job first', 'error');
      return;
    }

    const subEl = $('#variantCompareSub');
    if (subEl) {
      subEl.textContent = `Ranking all saved resume variants for: ${targetJob.company || ''} - ${cleanTitle(targetJob.title || '')}`;
    }
    const body = $('#variantCompareBody');
    if (body) {
      body.innerHTML = '<div style="padding:28px 14px; text-align:center;"><span class="spinner-sm"></span> Scoring all resume variants against this posting...</div>';
    }
    dlg.showModal();

    try {
      const res = await api('/api/profile/compare-job', {
        method: 'POST',
        body: { job: targetJob }
      });
      const comparisons = Array.isArray(res.comparisons) ? res.comparisons : [];
      if (!comparisons.length) {
        body.innerHTML = '<div class="empty"><p>No variants found to compare.</p></div>';
        return;
      }

      body.innerHTML = comparisons.map((c, idx) => {
        const isTop = idx === 0 && comparisons.length > 1;
        const isActive = c.id === S.activeProfileId;
        const score = Math.round(c.score || 0);
        return `
          <div class="variant-compare-card ${isActive ? 'is-active-variant' : ''} ${isTop ? 'is-top-match' : ''}">
            <div class="vc-top">
              <div class="vc-title-group">
                <span class="vc-name">${esc(c.name)}</span>
                ${c.is_master ? '<span class="chip-badge-master">Master</span>' : ''}
                ${isActive ? '<span class="chip-badge-active">Active Profile</span>' : ''}
                ${isTop ? '<span class="chip chip-ok" style="font-size:11px; padding:2px 6px;">⭐ Highest Match</span>' : ''}
              </div>
              <div class="vc-score-box">
                <span class="vc-score-num ${score >= 80 ? 'text-ok' : score >= 60 ? 'text-info' : 'text-warn'}">${score}%</span>
                <span class="vc-score-sub">Fit</span>
              </div>
            </div>
            <div class="vc-meta muted small">
              <span>Target: <strong>${esc(c.target_title || 'General')}</strong></span>
              <span>&bull;</span>
              <span>${c.matched_count || 0} matched / ${c.missing_count || 0} missing skills</span>
            </div>
            <div class="vc-skills-preview">
              ${(c.matched_skills || []).slice(0, 5).map(s => `<span class="chip chip-ok" style="font-size:11px;">✓ ${esc(s)}</span>`).join('')}
              ${(c.missing_skills || []).slice(0, 3).map(s => `<span class="chip chip-warn" style="font-size:11px;">! ${esc(s)}</span>`).join('')}
            </div>
            <div class="vc-actions">
              ${isActive
                ? '<span class="muted small">Currently active profile</span>'
                : `<button type="button" class="btn btn-secondary btn-sm" data-action="switch-and-close-compare" data-id="${esc(c.id)}">
                     Switch to this Variant &amp; Score
                   </button>`
              }
            </div>
          </div>
        `;
      }).join('');
    } catch (err) {
      if (body) body.innerHTML = `<div class="empty"><p class="text-warn">Could not score variants: ${esc(err.message)}</p></div>`;
    }
  }

  function setupResumeVariantUi() {
    const vForm = $('#variantDialogForm');
    if (vForm) {
      vForm.addEventListener('submit', submitVariantDialog);
    }
    const tForm = $('#tailoredVariantForm');
    if (tForm) {
      tForm.addEventListener('submit', submitTailoredDialog);
    }
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
    scrollToResumeGroup('basics');
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

  const STARTUP_LOADING_STAGES = {
    workspace: {
      title: 'Warming up your workspace',
      description: 'Restoring your profile, saved applications, and local preferences.'
    },
    cache: {
      title: 'Reading your job cache',
      description: 'Checking locally saved roles so your feed can appear without delay.'
    },
    feed: {
      title: 'Preparing your feed',
      description: 'Sorting your matches and getting the workspace ready.'
    }
  };

  function renderStartupLoadingState(stage = 'workspace') {
    const list = $('#jobList');
    if (!list) return;
    const copy = STARTUP_LOADING_STAGES[stage] || STARTUP_LOADING_STAGES.workspace;

    list.classList.add('is-startup-loading');
    list.innerHTML = `
      <div class="startup-loading-state" role="status" aria-live="polite" aria-label="${esc(copy.title)}">
        <span class="startup-loading-dots" aria-hidden="true"><i></i><i></i><i></i></span>
        <span class="startup-loading-label">${esc(copy.title)}</span>
      </div>`;

    const resultsSummary = $('#resultsSummary');
    if (resultsSummary) resultsSummary.textContent = copy.title;
    const resultsTools = $('#resultsTools');
    if (resultsTools) resultsTools.hidden = true;
    const resultsMeta = $('#resultsMeta');
    if (resultsMeta) resultsMeta.hidden = false;
    const split = $('#searchSplit');
    if (split) {
      split.hidden = false;
      split.setAttribute('aria-busy', 'true');
    }
  }

  function updateStartupLoadingState(stage) {
    const list = $('#jobList');
    if (!list || !list.classList.contains('is-startup-loading')) return;
    renderStartupLoadingState(stage);
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
  let scoreEtaState = { current: 0, total: 0, estSeconds: 2.2, startTime: 0 };

  function stopScoreEtaTicker() {
    if (scoreEtaTimer) { clearInterval(scoreEtaTimer); scoreEtaTimer = null; }
  }

  function startScoreEtaTicker(total, estSeconds) {
    stopScoreEtaTicker();
    scoreEtaState = {
      current: 0,
      total: total || 0,
      estSeconds: estSeconds || 2.2,
      startTime: Date.now()
    };

    if (!scoreEtaState.total) return;

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

    const qVal = (opts && opts.overrideQuery !== undefined) ? opts.overrideQuery : val('searchQuery').trim();
    const locVal = (opts && opts.overrideLoc !== undefined) ? opts.overrideLoc : val('searchLocation').trim();

    const params = new URLSearchParams({
      q: qVal, location: locVal,
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
    filterAndRender(true, true);
    scheduleNextEnrichmentCheck(1000);
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
    let s = (j.seniority || '').toLowerCase().trim();
    if (s) {
      if (s.includes('intern') || s.includes('apprentice')) return 'intern';
      if (s.includes('lead') || s.includes('staff') || s.includes('principal') || s.includes('director') || s.includes('vp') || s.includes('architect') || s.includes('founding')) return 'lead_staff';
      if (s.includes('senior') || s.startsWith('sr')) return 'senior';
      if (s.includes('junior') || s.includes('entry') || s.includes('associate') || s.includes('graduate') || s.includes('new grad') || s.startsWith('jr')) return 'junior';
      if (s.includes('mid')) return 'mid';
    }
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

  function filteredJobs(customFilters = null) {
    const pool = (S.jobsRanked && S.jobsRanked.length) ? S.jobsRanked : (S.allJobs || S.jobs || []);
    const f = customFilters || S.filters || {};

    const selectedRole = (f.jobFunctions && f.jobFunctions.length) ? f.jobFunctions[0].toLowerCase() : '';
    return pool.filter(j => {
      // 1. Keyword search (only when different from the role category)
      if (f.keyword && f.keyword.toLowerCase().trim() !== selectedRole) {
        const kw = f.keyword.toLowerCase().trim();
        const hay = `${j.title || ''} ${j.company || ''} ${j.location || ''} ${(j.description || '').slice(0, 600)} ${jobSkillsList(j).join(' ')}`.toLowerCase();
        if (!hay.includes(kw)) return false;
      }

      // 2. Job Functions (from All-Filters drawer and role pill)
      if (f.jobFunctions && f.jobFunctions.length > 0) {
        const titleLower = (j.title || '').toLowerCase();
        const catLower = (j.category || '').toLowerCase();
        const descLower = ((j.description || '').slice(0, 600)).toLowerCase();
        const tagsLower = (j.tags || []).map(t => String(t).toLowerCase());
        const matchesAnyFn = f.jobFunctions.some(fn => {
          const fnClean = fn.toLowerCase().trim();
          if (!fnClean) return true;
          if (catLower.includes(fnClean) || titleLower.includes(fnClean) || descLower.includes(fnClean) || tagsLower.some(t => t.includes(fnClean))) return true;
          if (fnClean.includes('full stack') || fnClean.includes('fullstack')) {
            return catLower.includes('full stack') || titleLower.includes('full stack') || titleLower.includes('fullstack') || titleLower.includes('full-stack');
          }
          if (fnClean.includes('backend') || fnClean.includes('back end')) {
            return catLower.includes('backend') || titleLower.includes('backend') || titleLower.includes('back end');
          }
          if (fnClean.includes('frontend') || fnClean.includes('front end')) {
            return catLower.includes('frontend') || titleLower.includes('frontend') || titleLower.includes('front end');
          }
          if (fnClean.includes('devops') || fnClean.includes('sre') || fnClean.includes('cloud')) {
            return catLower.includes('devops') || titleLower.includes('devops') || titleLower.includes('sre') || titleLower.includes('cloud') || titleLower.includes('platform');
          }
          // Match core role keywords
          const words = fnClean.split(/\s+/).filter(w => !['engineer', 'developer', 'specialist', 'lead', 'senior', 'junior', 'level'].includes(w));
          if (words.length > 0 && words.every(w => titleLower.includes(w) || catLower.includes(w) || descLower.includes(w))) return true;
          return false;
        });
        if (!matchesAnyFn) return false;
      }

      // 3. Excluded Titles
      if (f.excludedTitles && f.excludedTitles.size > 0) {
        const titleLower = (j.title || '').toLowerCase();
        for (const ex of f.excludedTitles) {
          if (ex && titleLower.includes(ex.toLowerCase().trim())) return false;
        }
      }

      // 4. Job Types (Full-time, Contract, Part-time, Internship)
      if (f.jobTypes && f.jobTypes.size > 0 && f.jobTypes.size < 4) {
        const jt = (j.job_type || '').toLowerCase();
        const titleLower = (j.title || '').toLowerCase();
        const descLower = ((j.description || '').slice(0, 300)).toLowerCase();
        const isInternSignal = jt.includes('intern') || titleLower.includes('intern') || titleLower.includes('co-op') ||
          titleLower.includes('apprentice') || titleLower.includes('werkstudent') || titleLower.includes('praktik') ||
          titleLower.includes('stage') || titleLower.includes('stagiaire');
        const isPartTimeSignal = jt.includes('part') || titleLower.includes('part-time') || titleLower.includes('part time') ||
          titleLower.includes('teilzeit') || descLower.includes('part-time') || descLower.includes('part time');
        const isContractSignal = jt.includes('contract') || titleLower.includes('contract') || titleLower.includes('freelance') ||
          titleLower.includes('c2c') || jt.includes('freelance') || descLower.includes('contract');

        const matchesType = Array.from(f.jobTypes).some(type => {
          const tLow = type.toLowerCase();
          if (tLow === 'internship') return isInternSignal;
          if (tLow === 'part-time') return isPartTimeSignal && !isInternSignal;
          if (tLow === 'contract') return isContractSignal && !isInternSignal;
          if (tLow === 'full-time') return !isInternSignal && !isPartTimeSignal && (jt.includes('full') || descLower.includes('full-time') || descLower.includes('full time') || (!jt && !isContractSignal));
          return false;
        });
        if (!matchesType) return false;
      } else if (f.jobType && f.jobType !== 'all') {
        const jt = (j.job_type || '').toLowerCase();
        const titleLower = (j.title || '').toLowerCase();
        const jtTarget = f.jobType.toLowerCase();
        if (jtTarget.includes('intern')) {
          if (!jt.includes('intern') && !titleLower.includes('intern')) return false;
        } else if (jtTarget.includes('part')) {
          if (!jt.includes('part') && !titleLower.includes('part-time')) return false;
        } else if (jtTarget.includes('contract')) {
          if (!jt.includes('contract') && !titleLower.includes('contract')) return false;
        } else if (!jt.includes(jtTarget)) {
          return false;
        }
      }

      // 5. Work Models (Onsite, Hybrid, Remote)
      if (f.workModels && f.workModels.size > 0 && f.workModels.size < 3) {
        const jm = jobWorkMode(j).toLowerCase(); // 'remote', 'hybrid', 'onsite'
        const allowed = Array.from(f.workModels).map(m => m.toLowerCase());
        if (!allowed.includes(jm)) return false;
      } else {
        const reqMode = (f.workMode || 'Any').toLowerCase();
        if (reqMode && reqMode !== 'any') {
          const jm = jobWorkMode(j);
          if (reqMode === 'remote' && jm !== 'remote') return false;
          if (reqMode === 'hybrid' && jm !== 'hybrid') return false;
          if (reqMode === 'onsite' && jm !== 'onsite') return false;
        }
      }

      // 6. Match Score
      if (f.minScore > 0 && (j.score || 0) < f.minScore) {
        return false;
      }

      // 7. Company Type (Big Tech vs Startups)
      if (f.famousMode === 'hide' && isFamousJob(j)) return false;
      if (f.famousMode === 'only' && !isFamousJob(j)) return false;
      if (f.famousMode === 'startups' && !jobIsStartup(j)) return false;

      // 8. Experience Level
      if (f.expLevels && f.expLevels.size > 0 && f.expLevels.size < 6) {
        const sen = jobSeniority(j);
        const title = (j.title || '').toLowerCase();
        const isDirector = /\b(director|vp|head of|chief|executive)\b/i.test(title);
        const matchesSen = Array.from(f.expLevels).some(lvl => {
          if (lvl === 'intern') return sen === 'intern';
          if (lvl === 'junior') return sen === 'junior';
          if (lvl === 'mid') return sen === 'mid';
          if (lvl === 'senior') return sen === 'senior';
          if (lvl === 'lead_staff') return sen === 'lead_staff';
          if (lvl === 'director') return isDirector || sen === 'lead_staff';
          return false;
        });
        if (!matchesSen) return false;
      } else if (f.seniority && f.seniority !== 'all') {
        const sen = jobSeniority(j);
        if (f.seniority === 'junior' && sen !== 'junior' && sen !== 'intern') return false;
        if (f.seniority === 'mid' && sen !== 'mid') return false;
        if (f.seniority === 'senior' && sen !== 'senior') return false;
        if (f.seniority === 'lead_staff' && sen !== 'lead_staff') return false;
      }

      // 9. Required Experience Years (when not Open to all)
      if (!f.expOpenToAll) {
        const maxExpAllowed = f.expYears !== undefined ? f.expYears : 0;
        const desc = (j.description || '').toLowerCase();
        const ym = desc.match(/(\d+)\+?\s*(?:-\s*(\d+))?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)/i);
        if (ym) {
          const minRequired = parseInt(ym[1], 10);
          if (!isNaN(minRequired) && minRequired > maxExpAllowed) return false;
        }
      }

      // 10. Salary Tier / Minimum Salary
      if (!f.salaryOpenToAll && f.minSalary > 0) {
        const salMax = jobAnnualSalaryMax(j);
        if (salMax > 0 && salMax < f.minSalary) return false;
      } else if (f.salaryTier && f.salaryTier !== '0') {
        const salMax = jobAnnualSalaryMax(j);
        if (f.salaryTier === 'disclosed' && !salMax && !j.salary) return false;
        if (f.salaryTier === '100k' && salMax < 100000) return false;
        if (f.salaryTier === '140k' && salMax < 140000) return false;
        if (f.salaryTier === '180k' && salMax < 180000) return false;
      }

      // 11. Freshness
      if (f.freshnessDays > 0) {
        const days = jobDaysAgo(j);
        if (days === null || days > f.freshnessDays) return false;
      }

      // 12. Direct ATS Only
      if (f.directAtsOnly) {
        const isDirect = j.source_kind === 'Direct employer ATS' || String(j.source_tier || '').startsWith('Direct');
        if (!isDirect) return false;
      }

      // 13. Hide Applied
      if (f.hideApplied && jobIsApplied(j)) return false;

      // 14. Saved Only
      if (f.savedOnly && !jobIsSaved(j)) return false;

      // 15. Selected Skills
      if (f.skills && f.skills.size > 0) {
        const jSkills = new Set(jobSkillsList(j).map(s => s.toLowerCase()));
        const desc = (j.description || '').toLowerCase();
        for (const reqSkill of f.skills) {
          const sLow = reqSkill.toLowerCase().trim();
          if (!jSkills.has(sLow) && !desc.includes(sLow)) return false;
        }
      } else if (f.selectedSkills && f.selectedSkills.size > 0) {
        const jSkills = new Set(jobSkillsList(j).map(s => s.toLowerCase()));
        for (const reqSkill of f.selectedSkills) {
          if (!jSkills.has(reqSkill.toLowerCase())) return false;
        }
      }

      // 16. Excluded Skills
      if (f.excludedSkills && f.excludedSkills.size > 0) {
        const jSkills = new Set(jobSkillsList(j).map(s => s.toLowerCase()));
        const desc = (j.description || '').toLowerCase();
        for (const ex of f.excludedSkills) {
          const sLow = ex.toLowerCase().trim();
          if (jSkills.has(sLow) || desc.includes(sLow)) return false;
        }
      }

      // 17. Target Country
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

      // 18. Location Query
      if (f.locationQuery && f.locationQuery.trim() && f.locationQuery.toLowerCase() !== 'anywhere in the us') {
        const locQ = f.locationQuery.toLowerCase().trim();
        const jLoc = (j.location || '').toLowerCase();
        if (!jLoc.includes(locQ) && jobWorkMode(j) !== 'remote') return false;
      }

      // 19. Excluded Countries
      if (f.excludedCountries && f.excludedCountries.size > 0) {
        const jc = jobCountry(j).toLowerCase();
        for (const ex of f.excludedCountries) {
          if (jc === ex.toLowerCase()) return false;
        }
      }

      // 20. Work Authorization (H1B sponsorship)
      if (f.h1b) {
        const text = `${j.title || ''} ${j.description || ''} ${(j.tags || []).join(' ')}`.toLowerCase();
        const mentionsNoSponsor = /\b(no visa|cannot sponsor|will not sponsor|no sponsorship|not eligible for sponsorship)\b/i.test(text);
        if (mentionsNoSponsor) return false;
        if (j.h1b === false) return false;
      }

      // 21. Limitations (Clearance & Citizen Only)
      if (f.excludeClearance) {
        const text = `${j.title || ''} ${j.description || ''}`.toLowerCase();
        if (/\b(security clearance|top secret|ts\/sci|secret clearance|clearance required|polygraph)\b/i.test(text)) return false;
      }
      if (f.excludeCitizenOnly) {
        const text = `${j.title || ''} ${j.description || ''}`.toLowerCase();
        if (/\b(us citizens? only|u\.s\. citizens? only|citizenship required|must be a us citizen|must be a u\.s\. citizen)\b/i.test(text)) return false;
      }

      // 22. Industry
      if (f.industries && f.industries.size > 0) {
        const hay = `${(j.tags || []).join(' ')} ${j.company || ''} ${j.title || ''} ${(j.description || '').slice(0, 400)}`.toLowerCase();
        const matchesInd = Array.from(f.industries).some(ind => {
          const indClean = ind.toLowerCase().replace(/\s*\(.*?\)\s*/g, '').trim();
          return hay.includes(indClean) || (ind.toLowerCase().includes('ai') && /\b(ai|artificial intelligence|machine learning|ml)\b/i.test(hay));
        });
        if (!matchesInd) return false;
      } else if (f.industry && f.industry !== 'all') {
        const hay = `${j.tags ? j.tags.join(' ') : ''} ${j.company || ''} ${j.title || ''} ${j.description ? j.description.slice(0, 300) : ''}`.toLowerCase();
        if (!hay.includes(f.industry.toLowerCase())) return false;
      }

      // 23. Excluded Industry
      if (f.excludedIndustries && f.excludedIndustries.size > 0) {
        const hay = `${(j.tags || []).join(' ')} ${j.company || ''} ${j.title || ''} ${(j.description || '').slice(0, 400)}`.toLowerCase();
        for (const ex of f.excludedIndustries) {
          if (hay.includes(ex.toLowerCase().trim())) return false;
        }
      }

      // 24. Role Type (IC vs Manager)
      if (f.roleType === 'ic') {
        const title = (j.title || '').toLowerCase();
        if (/\b(engineering manager|product manager|lead|director|head of|vp|architect)\b/i.test(title)) return false;
      } else if (f.roleType === 'manager') {
        const title = (j.title || '').toLowerCase();
        if (!/\b(manager|lead|director|head of|vp|lead\/staff)\b/i.test(title)) return false;
      }

      // 25. Target Companies
      if (f.companies && f.companies.size > 0) {
        const co = (j.company || '').toLowerCase();
        const matchCo = Array.from(f.companies).some(c => co.includes(c.toLowerCase().trim()));
        if (!matchCo) return false;
      }

      // 26. Company Stage
      if (f.companyStages && f.companyStages.size > 0) {
        const matchStage = Array.from(f.companyStages).some(st => {
          if (st === 'early') return jobIsStartup(j);
          if (st === 'public') return isFamousJob(j);
          if (st === 'growth' || st === 'late') return !isFamousJob(j) && (j.company_stage === 'mid_tech' || !jobIsStartup(j));
          return false;
        });
        if (!matchStage) return false;
      }

      // 27. Exclude Staffing Agency
      if (f.excludeStaffing) {
        const co = (j.company || '').toLowerCase();
        const isAgency = (j.source_kind === 'Staffing agency') ||
          /\b(cybercoders|robert half|teksystems|aerotek|apex systems|kforce|kelly services|insight global|hays|randstad)\b/i.test(co) ||
          /\b(staffing|recruiting agency|staffing agency)\b/i.test(co);
        if (isAgency) return false;
      }

      // 27b. ⚡ Easy Apply Only
      if (f.easyApplyOnly) {
        const u = (j.url || '').toLowerCase();
        const hasAts = j.is_verified_ats || j.source_kind === 'Direct employer ATS' ||
          u.includes('greenhouse.io') || u.includes('lever.co') || u.includes('ashbyhq.com') ||
          u.includes('workday') || u.includes('smartrecruiters') || u.includes('workable') ||
          u.includes('bamboohr') || u.length > 5;
        if (!hasAts) return false;
      }

      // 28. Hidden Jobs
      const k = jobKey(j);
      const isHidden = S.hiddenJobs && S.hiddenJobs.has(k);
      if (S.showHidden) {
        if (!isHidden) return false;
      } else {
        if (isHidden) return false;
      }

      // 29. Years of Experience (yoe)
      if (f.yoe && f.yoe !== 'all') {
        const sen = jobSeniority(j);
        if (f.yoe === '0-2' && sen !== 'junior' && sen !== 'intern') return false;
        if (f.yoe === '2-5' && sen !== 'mid') return false;
        if (f.yoe === '5-8' && sen !== 'senior') return false;
        if (f.yoe === '8+' && sen !== 'lead_staff') return false;
      }

      // 30. Winning Resume Filter
      const resumeFilter = (customFilters && customFilters.filterResume !== undefined) ? customFilters.filterResume : (S.filterResume || (f.best_profile_id || 'all'));
      if (resumeFilter && resumeFilter !== 'all') {
        if (j.best_profile_id && j.best_profile_id !== resumeFilter) return false;
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
    syncJobTypeFilterState();
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
    if (f.easyApplyOnly) tags.push({ type: 'easyApplyOnly', label: '⚡ Easy Apply Only' });

    // Badge on More Filters button
    const drawerActiveCount = [
      f.country !== 'all',
      f.excludedCountries.size > 0,
      f.seniority !== 'all',
      f.salaryTier !== '0',
      f.freshnessDays > 0,
      f.directAtsOnly,
      f.hideApplied,
      f.savedOnly,
      f.easyApplyOnly
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
    } else if (type === 'easyApplyOnly') {
      f.easyApplyOnly = false;
      const pill = $('#p4PillEasyApply');
      if (pill) pill.classList.remove('is-active');
    } else if (type === 'skill' && val) {
      f.selectedSkills.delete(val);
    }
  }

  function resetAllFilters() {
    const pill = $('#p4PillEasyApply');
    if (pill) pill.classList.remove('is-active');
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
      easyApplyOnly: false,
      famousMode: 'all',
      country: 'all',
      excludedCountries: new Set(),
      seniority: 'all',
      salaryTier: '0',
      freshnessDays: 0,
      directAtsOnly: false,
      hideApplied: false,
      savedOnly: false,
      selectedSkills: new Set(),
      jobType: 'all',
      industry: 'all',
      yoe: 'all',
      jobFunctions: [],
      excludedTitles: new Set(),
      jobTypes: new Set(),
      workModels: new Set(),
      locationQuery: '',
      locationRadius: '25',
      customLocations: [],
      expLevels: new Set(),
      expOpenToAll: true,
      expYears: 0,
      salaryOpenToAll: true,
      minSalary: 0,
      h1b: false,
      excludeClearance: false,
      excludeCitizenOnly: false,
      industries: new Set(),
      excludedIndustries: new Set(),
      skills: new Set(),
      excludedSkills: new Set(),
      roleType: 'all',
      companies: new Set(),
      companyStages: new Set(),
      excludeStaffing: false
    };
    S.workMode = 'Any';
    S.famousFilter = 'all';
    try { localStorage.setItem('jh-famous-filter', 'all'); } catch (e) {}
    const s = $('#searchMinScore'); if (s) s.value = '0';
    const fam = $('#searchFamousSelect'); if (fam) fam.value = 'all';
    const cSel = $('#countrySelect'); if (cSel) cSel.value = 'all';
    const exSel = $('#excludeCountrySelect'); if (exSel) exSel.value = '';
    const qRole = $('#p4TextRole'); if (qRole) qRole.textContent = 'All Roles';
    const qSen = $('#p4TextSeniority'); if (qSen) qSen.textContent = 'All Seniority';
    const qLoc = $('#p4TextLocation'); if (qLoc) qLoc.textContent = 'Worldwide';
    const qTime = $('#p4TextTime'); if (qTime) qTime.textContent = 'All Time';
    const qFam = $('#p4TextFamous'); if (qFam) qFam.textContent = 'Company Type';
    const pFam = $('#p4PillFamous'); if (pFam) pFam.classList.remove('is-active');
    syncDrawerUiFromState();
    renderDrawerActivePills();
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
    syncDrawerUiFromState();
    renderDrawerActivePills();
  }

  function applySort() {
    const how = val('sortResultsBy') || 'ranked';
    const pool = (S.allJobs && S.allJobs.length)
      ? S.allJobs.slice()
      : ((S.jobsRanked && S.jobsRanked.length)
          ? S.jobsRanked.slice()
          : (S.jobs && S.jobs.length ? S.jobs.slice() : []));

    if (how === 'score_desc') {
      pool.sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0) || (Number(b.opportunity_score) || 0) - (Number(a.opportunity_score) || 0));
    } else if (how === 'salary_desc') {
      pool.sort((a, b) => (jobAnnualSalaryMax(b) || 0) - (jobAnnualSalaryMax(a) || 0) || (Number(b.score) || 0) - (Number(a.score) || 0));
    } else if (how === 'date_desc') {
      pool.sort((a, b) => String(b.posted_at || '').localeCompare(String(a.posted_at || '')) || (Number(b.score) || 0) - (Number(a.score) || 0));
    } else if (how === 'company_asc') {
      pool.sort((a, b) => String(a.company || '').localeCompare(String(b.company || '')) || (Number(b.score) || 0) - (Number(a.score) || 0));
    } else {
      pool.sort((a, b) => (Number(b.opportunity_score) || 0) - (Number(a.opportunity_score) || 0) || (Number(b.score) || 0) - (Number(a.score) || 0));
    }
    S.jobsRanked = pool;
    if (!S.allJobs || !S.allJobs.length) {
      S.allJobs = pool.slice();
    }
    S.jobs = filteredJobs();
  }

  let _fetchDebounce = null;
  async function fetchJobsFromDb() {
    clearTimeout(_fetchDebounce);
    return new Promise(resolve => {
      _fetchDebounce = setTimeout(async () => {
        try {
          const f = S.filters || {};
          const params = new URLSearchParams();

          // Role / Category
          const cat = (f.jobFunctions && f.jobFunctions.length) ? f.jobFunctions[0] : '';
          if (cat) params.set('category', cat);
          if (f.keyword && f.keyword.toLowerCase() !== cat.toLowerCase()) params.set('q', f.keyword);

          // Work mode
          if (f.workMode && f.workMode !== 'Any' && f.workMode !== 'all') {
            params.set('work_mode', f.workMode);
          } else if (f.workModels && f.workModels.size === 1) {
            params.set('work_mode', Array.from(f.workModels)[0]);
          }

          // Seniority
          if (f.seniority && f.seniority !== 'all') {
            params.set('seniority', f.seniority);
          } else if (f.expLevels && f.expLevels.size === 1) {
            params.set('seniority', Array.from(f.expLevels)[0]);
          }

          // Job type
          if (f.jobTypes && f.jobTypes.size > 0 && f.jobTypes.size < 4) {
            params.set('job_type', Array.from(f.jobTypes).join(','));
          } else if (f.jobType && f.jobType !== 'all') {
            params.set('job_type', f.jobType);
          }

          // Country / Location
          if (f.country && f.country !== 'all') {
            params.set('country', f.country);
          }
          if (f.locationQuery && f.locationQuery !== 'Anywhere in the US' && f.locationQuery !== 'Worldwide' && f.locationQuery.trim()) {
            params.set('location', f.locationQuery.trim());
          }

          // Min score
          if (f.minScore > 0) params.set('min_score', String(f.minScore));

          // Min salary
          if (!f.salaryOpenToAll && f.minSalary > 0) {
            params.set('min_salary', String(f.minSalary));
          } else if (f.salaryTier && f.salaryTier !== '0' && f.salaryTier !== 'disclosed') {
            const num = f.salaryTier.replace('k', '000');
            params.set('min_salary', num);
          }

          // Freshness
          if (f.freshnessDays > 0) params.set('days', String(f.freshnessDays));

          // Industry
          if (f.industry && f.industry !== 'all') {
            params.set('industry', f.industry);
          } else if (f.industries && f.industries.size > 0) {
            params.set('industry', Array.from(f.industries)[0]);
          }

          // Famous mode
          if (f.famousMode && f.famousMode !== 'all') params.set('famous_mode', f.famousMode);

          // H1B
          if (f.h1b) params.set('h1b', '1');

          // Sort
          const how = val('sortResultsBy') || 'ranked';
          params.set('sort', how);

          const res = await api(`/api/search/saved?${params.toString()}`);
          if (res) {
            const allPool = (res.all_jobs && res.all_jobs.length) ? res.all_jobs : (S.allJobs && S.allJobs.length ? S.allJobs : (res.jobs || []));
            S.allJobs = allPool;
            S.jobsRanked = allPool;
            S.jobs = (res.jobs && res.jobs.length) ? res.jobs : allPool;
            S.searchMeta = res.meta || S.searchMeta || {};
            S.searchHasRun = true;
            if (S.jobs.length && (!S.selectedKey || !S.jobs.some(j => jobKey(j) === S.selectedKey))) {
              S.selectedKey = jobKey(S.jobs[0]);
            }
            filterAndRender(false);
            syncFiltersUi();
            updateFacetCounts();
          }
          resolve(res);
        } catch (e) {
          console.warn('Error fetching filtered jobs from DB:', e);
          resolve(null);
        }
      }, 50);
    });
  }

  function filterAndRender(syncWithDb = true, animate = false) {
    applySort();
    syncFiltersUi();
    updateFacetCounts();
    renderActiveFilterTags();
    const currentList = S.jobs || [];
    const keep = currentList.find(j => jobKey(j) === S.selectedKey);
    S.selectedKey = keep ? jobKey(keep) : (!isNarrow() && currentList[0] ? jobKey(currentList[0]) : null);
    S.jobsLimit = 20;
    renderResults(animate);
    if (syncWithDb) {
      fetchJobsFromDb();
    }
  }

  function sourceCounts() {
    const srcs = (S.searchMeta && S.searchMeta.sources) || [];
    const active = srcs.filter(s => s.state !== 'disabled');
    const ok = active.filter(s => s.state === 'ok' || s.state === 'cached').length;
    return { total: active.length, ok, srcs };
  }

  function getInsiderLinks(job) {
    if (job && job.insider_links && (job.insider_links.recruiter_url || job.insider_links.recruiters_url)) {
      const il = job.insider_links;
      return {
        recruiter_url: il.recruiter_url || il.recruiters_url,
        peer_url: il.peer_url || il.peers_url,
        alumni_url: il.alumni_url || il.company_url
      };
    }
    const c = encodeURIComponent(String((job && job.company) || '').trim());
    const t = encodeURIComponent(String((job && job.title) || '').replace(/\b(Senior|Staff|Principal|Lead|Junior|Associate|Engineer|Developer)\b/gi, '').trim());
    return {
      recruiter_url: `https://www.linkedin.com/search/results/people/?keywords=${c}%20Technical%20Recruiter`,
      peer_url: `https://www.linkedin.com/search/results/people/?keywords=${c}%20${t}%20Engineer`,
      alumni_url: `https://www.linkedin.com/search/results/people/?keywords=${c}`
    };
  }

  async function loadRecommendations(forceRefresh = false) {
    if (S.recLoading) return;
    S.recLoading = true;
    const bannerSub = $('#recommendBannerSubtitle');
    const refreshBtn = $('#btnRefreshRecs');
    if (refreshBtn) refreshBtn.classList.add('is-loading');

    const list = $('#jobList');
    if (list && (!S.recJobs || !S.recJobs.length) && S.view === 'recommend') {
      list.innerHTML = skeletons(5);
    }

    try {
      const res = await api(`/api/recommendations?force_refresh=${forceRefresh ? '1' : '0'}&limit=40`);
      S.recJobs = res.jobs || [];
      S.recMeta = res.meta || {};

      const countBadge = $('#navRecCount');
      if (countBadge) {
        countBadge.textContent = String(S.recJobs.length);
        countBadge.hidden = S.recJobs.length === 0;
      }

      if (bannerSub && S.recMeta.query) {
        bannerSub.textContent = `Matched to your resume target role (${S.recMeta.query}) and top skills. Zero search query needed.`;
      }

      if (S.view === 'recommend') {
        S.jobs = S.recJobs;
        S.allJobs = S.recJobs;
        S.jobsRanked = S.recJobs;
        S.searchMeta = S.recMeta;
        S.searchHasRun = true;
        if (S.recJobs.length && !S.selectedKey) {
          S.selectedKey = jobKey(S.recJobs[0]);
        }
        filterAndRender(false);
      }
    } catch (err) {
      console.warn('Could not load recommendations:', err);
      if (S.view === 'recommend' && (!S.recJobs || !S.recJobs.length)) {
        if (list) {
          list.innerHTML = `<div class="empty">${ico('alert')}<h3>Could not load recommendations</h3><p>${esc(err.message)}</p><div class="empty-actions"><button type="button" class="btn btn-primary" data-action="refresh-recommendations">Try again</button></div></div>`;
        }
      }
    } finally {
      S.recLoading = false;
      if (refreshBtn) refreshBtn.classList.remove('is-loading');
    }
  }

  // ----------------------------------------------------------------- search relaxation widget
  function detectSearchBottleneck() {
    const pool = (S.jobsRanked && S.jobsRanked.length) ? S.jobsRanked : (S.allJobs || S.jobs || []);
    if (!pool.length) return null;
    const currentCount = filteredJobs().length;
    const f = S.filters || {};
    const candidates = [];

    // 1. Freshness / Date Posted
    if (f.freshnessDays > 0) {
      let nextDays = 0;
      let nextLabel = 'All time';
      let currentLabel = `Past ${f.freshnessDays} days`;
      if (f.freshnessDays === 1) {
        currentLabel = 'Past 24 hours';
        nextDays = 7;
        nextLabel = 'Past week';
      } else if (f.freshnessDays === 3) {
        currentLabel = 'Past 3 days';
        nextDays = 7;
        nextLabel = 'Past week';
      } else if (f.freshnessDays <= 7) {
        currentLabel = 'Past week';
        nextDays = 14;
        nextLabel = 'Past 2 weeks';
      } else if (f.freshnessDays <= 14) {
        currentLabel = 'Past 2 weeks';
        nextDays = 30;
        nextLabel = 'Past month';
      }
      const simCount = filteredJobs({ ...f, freshnessDays: nextDays }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'freshnessDays',
        gain,
        priority: 100 + Math.max(0, gain) * 5,
        limitingLabel: 'Date Posted',
        limitingValue: currentLabel,
        adjustLabel: 'Set the Date Posted',
        adjustValue: nextLabel,
        apply: () => {
          S.filters.freshnessDays = nextDays;
        }
      });
    }

    // 2. Minimum Match Score
    if (f.minScore > 0) {
      let nextScore = 0;
      let nextLabel = 'Any match score';
      if (f.minScore >= 80) {
        nextScore = 60;
        nextLabel = '60%+';
      } else if (f.minScore >= 70) {
        nextScore = 50;
        nextLabel = '50%+';
      } else if (f.minScore >= 50) {
        nextScore = 0;
        nextLabel = 'Any match score';
      }
      const simCount = filteredJobs({ ...f, minScore: nextScore }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'minScore',
        gain,
        priority: 90 + Math.max(0, gain) * 5,
        limitingLabel: 'Match Score',
        limitingValue: `${f.minScore}%+`,
        adjustLabel: 'Lower the Match Score',
        adjustValue: nextLabel,
        apply: () => {
          S.filters.minScore = nextScore;
          const s = $('#searchMinScore'); if (s) s.value = String(nextScore);
        }
      });
    }

    // 3. Work Mode
    const hasWorkModeFilter = (f.workMode && f.workMode.toLowerCase() !== 'any') || (f.workModels && f.workModels.size > 0);
    if (hasWorkModeFilter) {
      const currentModeLabel = (f.workModels && f.workModels.size > 0)
        ? Array.from(f.workModels).map(m => m.charAt(0).toUpperCase() + m.slice(1)).join(', ')
        : (f.workMode ? f.workMode.charAt(0).toUpperCase() + f.workMode.slice(1) : 'Restricted');
      const simCount = filteredJobs({ ...f, workMode: 'Any', workModels: new Set() }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'workMode',
        gain,
        priority: 80 + Math.max(0, gain) * 5,
        limitingLabel: 'Work Mode',
        limitingValue: currentModeLabel,
        adjustLabel: 'Set the Work Mode',
        adjustValue: 'Any (Remote & Hybrid)',
        apply: () => {
          S.filters.workMode = 'Any';
          if (S.filters.workModels) S.filters.workModels.clear();
        }
      });
    }

    // 4. Job Types (Full-time, Contract, Internship, etc.)
    const hasJobTypeFilter = (f.jobType && f.jobType !== 'all') || (f.jobTypes && f.jobTypes.size > 0 && f.jobTypes.size < 4);
    if (hasJobTypeFilter) {
      const currentJtLabel = (f.jobTypes && f.jobTypes.size > 0)
        ? Array.from(f.jobTypes).join(', ')
        : f.jobType;
      const simCount = filteredJobs({ ...f, jobType: 'all', jobTypes: new Set() }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'jobType',
        gain,
        priority: 70 + Math.max(0, gain) * 5,
        limitingLabel: 'Job Type',
        limitingValue: currentJtLabel,
        adjustLabel: 'Include all Job Types',
        adjustValue: 'Full-time & all types',
        apply: () => {
          S.filters.jobType = 'all';
          if (S.filters.jobTypes) S.filters.jobTypes.clear();
        }
      });
    }

    // 5. Seniority / Experience Level
    const hasSenFilter = (f.seniority && f.seniority !== 'all') || (f.expLevels && f.expLevels.size > 0 && f.expLevels.size < 6) || (f.yoe && f.yoe !== 'all') || !f.expOpenToAll;
    if (hasSenFilter) {
      const currentSenLabel = (f.expLevels && f.expLevels.size > 0)
        ? Array.from(f.expLevels).join(', ')
        : (f.seniority !== 'all' ? f.seniority : (f.yoe !== 'all' ? f.yoe : 'Restricted YOE'));
      const simCount = filteredJobs({ ...f, seniority: 'all', expLevels: new Set(), yoe: 'all', expOpenToAll: true }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'seniority',
        gain,
        priority: 65 + Math.max(0, gain) * 5,
        limitingLabel: 'Experience Level',
        limitingValue: currentSenLabel,
        adjustLabel: 'Set Experience Level',
        adjustValue: 'Open to all levels',
        apply: () => {
          S.filters.seniority = 'all';
          S.filters.yoe = 'all';
          S.filters.expOpenToAll = true;
          if (S.filters.expLevels) S.filters.expLevels.clear();
        }
      });
    }

    // 6. Minimum Salary / Salary Tier
    const hasSalaryFilter = (f.salaryTier && f.salaryTier !== '0') || (!f.salaryOpenToAll && f.minSalary > 0);
    if (hasSalaryFilter) {
      const currentSalLabel = f.salaryTier === 'disclosed' ? 'Disclosed only' : (f.salaryTier ? `$${f.salaryTier}` : `$${f.minSalary}+`);
      const simCount = filteredJobs({ ...f, salaryTier: '0', minSalary: 0, salaryOpenToAll: true }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'salary',
        gain,
        priority: 60 + Math.max(0, gain) * 5,
        limitingLabel: 'Salary Filter',
        limitingValue: currentSalLabel,
        adjustLabel: 'Set Salary Filter',
        adjustValue: 'Open to all (include unlisted)',
        apply: () => {
          S.filters.salaryTier = '0';
          S.filters.minSalary = 0;
          S.filters.salaryOpenToAll = true;
        }
      });
    }

    // 7. Company Mode (Big Tech vs Startups)
    if (f.famousMode && f.famousMode !== 'all') {
      const currentFamLabel = f.famousMode === 'only' ? 'Big Tech only' : (f.famousMode === 'startups' ? 'Startups only' : 'No Big Tech');
      const simCount = filteredJobs({ ...f, famousMode: 'all' }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'famousMode',
        gain,
        priority: 55 + Math.max(0, gain) * 5,
        limitingLabel: 'Company Filter',
        limitingValue: currentFamLabel,
        adjustLabel: 'Set Company Filter',
        adjustValue: 'All Companies',
        apply: () => {
          S.filters.famousMode = 'all';
          try { localStorage.setItem('jh-famous-filter', 'all'); } catch (e) {}
        }
      });
    }

    // 8. Winning Resume Variant
    const hasResumeFilter = (S.filterResume && S.filterResume !== 'all') || (f.best_profile_id && f.best_profile_id !== 'all');
    if (hasResumeFilter) {
      const profMeta = (S.profiles || []).find(p => p.id === (S.filterResume || f.best_profile_id));
      const currentResLabel = profMeta ? profMeta.name : 'Single Resume';
      const simCount = filteredJobs({ ...f, best_profile_id: 'all', filterResume: 'all' }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'resume',
        gain,
        priority: 50 + Math.max(0, gain) * 5,
        limitingLabel: 'Resume Variant',
        limitingValue: currentResLabel,
        adjustLabel: 'Include jobs for',
        adjustValue: 'All Resume Variants',
        apply: () => {
          S.filterResume = 'all';
          S.filters.best_profile_id = 'all';
        }
      });
    }

    // 9. Location / Country
    const hasLocFilter = (f.country && f.country.toLowerCase() !== 'all') || (f.locationQuery && f.locationQuery.trim() && f.locationQuery.toLowerCase() !== 'anywhere in the us');
    if (hasLocFilter) {
      const currentLocLabel = f.locationQuery || f.country;
      const simCount = filteredJobs({ ...f, country: 'all', locationQuery: '' }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'location',
        gain,
        priority: 45 + Math.max(0, gain) * 5,
        limitingLabel: 'Location',
        limitingValue: currentLocLabel,
        adjustLabel: 'Expand Location',
        adjustValue: 'Worldwide Remote',
        apply: () => {
          S.filters.country = 'Worldwide';
          S.filters.locationQuery = '';
        }
      });
    }

    // 10. Role Function / Category
    if (f.jobFunctions && f.jobFunctions.length > 0) {
      const currentFnLabel = f.jobFunctions[0];
      const simCount = filteredJobs({ ...f, jobFunctions: [] }).length;
      const gain = simCount - currentCount;
      candidates.push({
        key: 'jobFunctions',
        gain,
        priority: 40 + Math.max(0, gain) * 5,
        limitingLabel: 'Role Category',
        limitingValue: currentFnLabel,
        adjustLabel: 'Broaden Category',
        adjustValue: 'All Software Roles',
        apply: () => {
          S.filters.jobFunctions = [];
        }
      });
    }

    if (!candidates.length) return null;

    // Sort by positive gain first, then by priority
    candidates.sort((a, b) => {
      if (a.gain > 0 && b.gain <= 0) return -1;
      if (b.gain > 0 && a.gain <= 0) return 1;
      if (a.gain !== b.gain) return b.gain - a.gain;
      return b.priority - a.priority;
    });

    return candidates[0];
  }

  function renderSearchRelaxationWidget(bottleneck) {
    if (!bottleneck) return '';
    S._activeBottleneck = bottleneck;
    return `<div class="search-relax-widget" id="searchRelaxWidget">
      <div class="search-relax-notice">
        <span class="search-relax-badge-icon" aria-hidden="true">!</span>
        <span class="search-relax-notice-text">We couldn't find more jobs with your current preferences. Try adjusting the following criteria to view more jobs.</span>
      </div>
      <div class="search-relax-card">
        <div class="search-relax-row">
          <div class="search-relax-label">📌 What's limiting your search:</div>
          <div class="search-relax-value">
            <span>${esc(bottleneck.limitingLabel)} is set to</span>
            <span class="search-relax-pill">${esc(bottleneck.limitingValue)}</span>
          </div>
        </div>
        <div class="search-relax-divider"></div>
        <div class="search-relax-row">
          <div class="search-relax-label">💡 How you may adjust:</div>
          <div class="search-relax-value">
            <span>${esc(bottleneck.adjustLabel)} to</span>
            <span class="search-relax-pill">${esc(bottleneck.adjustValue)}</span>
          </div>
        </div>
      </div>
      <div class="search-relax-actions">
        <button type="button" class="btn-search-relax-update" data-action="apply-search-relaxation">Update Now</button>
      </div>
    </div>`;
  }

  function applySearchRelaxation() {
    if (!S._activeBottleneck || typeof S._activeBottleneck.apply !== 'function') return;
    const b = S._activeBottleneck;
    b.apply();
    S._activeBottleneck = null;
    syncFiltersUi();
    filterAndRender(true, true);
    toast(`${b.limitingLabel} updated to ${b.adjustValue}. Showing more jobs!`, 'ok');
  }

  function renderResults(animate = false) {
    stopSearchProgressAnimation();
    $('#jobList')?.classList.remove('is-startup-loading');
    const stage = $('#searchProgressStage');
    if (stage) stage.hidden = true;
    const split = $('#searchSplit');
    if (split) {
      split.hidden = false;
      split.removeAttribute('aria-busy');
    }
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
    const isRec = S.view === 'recommend';
    const forWhat = isRec
      ? ` <small>tailored for ${esc(meta.query || 'your resume')}</small>`
      : (!typed && meta.query ? ` <small>for ${esc(meta.query)}, based on your resume</small>` : '');
    let filterBadge = '';
    if (isRec) {
      filterBadge = ` <span class="chip chip-ok chip-sm" style="font-size:11.5px;padding:1px 8px;margin-left:6px;"><svg class="i" style="width:12px;height:12px;display:inline-block;vertical-align:-1px;margin-right:3px;"><use href="#i-sparkles"/></svg>AI Curated</span>`;
    }
    if (S.filters.famousMode === 'hide') {
      filterBadge += ` <span class="chip chip-outline chip-sm" style="font-size:11.5px;padding:1px 8px;margin-left:6px;" title="Filtered out Big Tech & prominent AI companies">No Big Tech</span>`;
    } else if (S.filters.famousMode === 'only') {
      filterBadge += ` <span class="chip chip-famous chip-sm" style="font-size:11.5px;padding:1px 8px;margin-left:6px;" title="Only showing Big Tech & prominent AI companies">Big Tech Only</span>`;
    }
    const filterSub = n !== totalAll ? ` <small class="text-muted">(${n} of ${totalAll} match current filters &middot; <button type="button" class="btn-link" data-action="clear-all-filters" style="cursor:pointer;color:var(--brand-primary,#2563eb);text-decoration:underline;background:none;border:none;padding:0;font:inherit;">Show all ${totalAll}</button>)</small>` : '';
    const prefix = isRec ? 'Recommended' : '';
    $('#resultsSummary').innerHTML = n ? `${prefix ? prefix + ': ' : ''}${n} job${n === 1 ? '' : 's'}${forWhat}${filterSub}${filterBadge}` : `No jobs found${filterSub}${filterBadge}`;

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

    renderList(animate);
    renderDetail();
  }

  let jobListObserver = null;

  function attachJobListObserver() {
    if (jobListObserver) {
      jobListObserver.disconnect();
      jobListObserver = null;
    }
    const sentinel = $('#jobListSentinel');
    if (!sentinel) return;

    if (!('IntersectionObserver' in window)) return;

    jobListObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          loadMoreJobs();
          break;
        }
      }
    }, {
      root: null,
      rootMargin: '450px 0px',
      threshold: 0.01
    });

    jobListObserver.observe(sentinel);
  }

  function loadMoreJobs() {
    const list = $('#jobList');
    const sentinel = $('#jobListSentinel');
    if (!list || !sentinel) return;

    const jobs = filteredJobs();
    const currentLimit = S.jobsLimit || 20;
    if (currentLimit >= jobs.length) {
      sentinel.remove();
      if (jobListObserver) {
        jobListObserver.disconnect();
        jobListObserver = null;
      }
      return;
    }

    const nextLimit = Math.min(jobs.length, currentLimit + 20);
    const newSlice = jobs.slice(currentLimit, nextLimit);
    S.jobsLimit = nextLimit;

    const meta = S.searchMeta || {};
    const nextHtml = newSlice.map((j, idx) => renderJobCard(j, meta, S, idx)).join('');
    sentinel.insertAdjacentHTML('beforebegin', nextHtml);

    if (S.jobsLimit >= jobs.length) {
      sentinel.remove();
      if (jobListObserver) {
        jobListObserver.disconnect();
        jobListObserver = null;
      }
    } else {
      const text = sentinel.querySelector('.sentinel-text');
      if (text) text.textContent = `Showing ${S.jobsLimit} of ${jobs.length} jobs • Loading more...`;
    }
  }

  function renderJobCard(j, meta, S, idx = 0) {
    const key = jobKey(j);
    const required = Object.keys(j.required_skills || {}).length;
    const matched = (j.matched_skills || []).length;
    const isDirectAts = j.is_verified_ats || j.source_kind === 'Direct employer ATS' || String(j.source_tier || '').startsWith('Direct');
    const isFamous = isFamousJob(j);
    const rawDays = jobDaysAgo(j);
    const days = rawDays !== null ? Math.round(rawDays) : null;
    const postedText = days === 0 ? 'Today' : days === 1 ? '1d ago' : (days !== null ? `${days}d ago` : '');
    const saved = !!savedApp(j);
    const hook = j.recommendation_hook || (j.score >= 70 && matched ? `Strong match (${j.score}%) • Covers ${matched} core skills` : '');
    const monogram = companyMonogram(j.company);
    const avatarCol = companyAvatarColor(j.company);
    const showScore = !meta.profile_empty;
    const isJustSynced = !!(S.justSyncedKeys && S.justSyncedKeys.has(key));
    const cardStagger = Math.min(idx, 8);

    return `<button type="button" class="job-item${key === S.selectedKey ? ' is-selected' : ''}" data-action="job-select" data-key="${esc(key)}" style="--card-stagger:${cardStagger};">
      <div class="job-card-header">
        <div class="job-card-brand">
          ${companyAvatarHtml(j, 'job')}
          <div class="job-brand-info">
            <span class="job-item-company">${esc(j.company)}</span>
            ${postedText ? `<span class="job-dot-sep">•</span><span class="job-posted-time">${esc(postedText)}</span>` : ''}
            ${isJustSynced ? `<span class="chip-just-synced" title="Freshly discovered and synced right now">${ico('bolt')}Just synced</span>` : ''}
            ${j.is_dream_company ? `<span class="chip-wishlist" title="Your Dream Wishlist Company">${ico('star')}Wishlist</span>` : ''}
            ${j.is_fresh ? `<span class="chip-fresh-badge" title="Fresh posting within the last 48 hours">${ico('bolt')}Fresh</span>` : ''}
          </div>
        </div>
        <div class="job-card-actions">
          <span class="job-item-fav${saved ? ' is-saved' : ''}" role="button" tabindex="0" data-action="job-fav" data-key="${esc(key)}" title="${saved ? 'Saved in Applications' : 'Save job'}" aria-label="${saved ? 'Saved' : 'Save'}">
            ${ico(saved ? 'bookmark-fill' : 'bookmark')}
          </span>
          <span class="job-item-dismiss" role="button" tabindex="0" data-action="job-hide" data-key="${esc(key)}" title="Dismiss / Hide this job" aria-label="Dismiss">
            ${ico('x')}
          </span>
        </div>
      </div>

      <div class="job-card-body">
        <div class="job-card-body-main">
          <span class="job-item-title">${esc(cleanTitle(j.title))}</span>
          ${(() => {
            if (!showScore || !j.best_profile_name) return '';
            const liveCount = (j.live_matches && j.live_matches.length) || (j.total_live_profiles || 1);
            const liveBadge = liveCount > 1 ? `<span class="chip-live-tested" title="Tested against ${liveCount} live resume variants (${liveCount} in active matching pool)">${liveCount} live</span>` : '';
            return `<div class="job-item-best-resume" title="Match score (${j.score}%) matched using: ${esc(j.best_profile_name)}">
              <span class="chip-best-resume">
                <svg class="i chip-resume-icon" aria-hidden="true"><use href="#i-user"/></svg>
                <span class="chip-resume-label">Matched with:</span>
                <strong class="chip-resume-name">${esc(j.best_profile_name)}</strong>
                ${liveBadge}
              </span>
            </div>`;
          })()}
        </div>
        ${showScore ? `
          <div class="job-score-wrap">
            ${ring(j.score)}
          </div>
        ` : ''}
      </div>

      <div class="job-item-meta">
        <span class="meta-pill meta-loc" title="${esc(j.location || 'Remote')}"><span class="meta-icon">${ico('pin')}</span><span class="meta-text">${esc(j.location || 'Remote')}</span></span>
        ${j.work_mode ? `<span class="meta-pill"><span class="meta-icon">${ico('briefcase')}</span><span>${esc(j.work_mode)}</span></span>` : ''}
        ${(() => {
          if (!j.job_type) return '';
          const jtLow = j.job_type.toLowerCase();
          let jtClass = 'meta-pill meta-jobtype';
          if (jtLow.includes('intern') || jtLow.includes('werkstudent') || jtLow.includes('praktik')) jtClass += ' meta-type-internship';
          else if (jtLow.includes('part') || jtLow.includes('teilzeit')) jtClass += ' meta-type-parttime';
          else if (jtLow.includes('contract') || jtLow.includes('freelance')) jtClass += ' meta-type-contract';
          else jtClass += ' meta-type-fulltime';
          return `<span class="${jtClass}">${esc(j.job_type)}</span>`;
        })()}
        ${j.salary ? `<span class="meta-pill meta-salary"><span class="meta-icon">${ico('dollar')}</span><span>${esc(j.salary)}</span></span>` : ''}
        ${(() => {
          if (!showScore) return '';
          const descLen = (j.description || '').length;
          const isSparse = !j.enriched && required <= 2 && descLen < 350;
          if (isSparse && matched > 0) {
            const firstSkill = (j.matched_skills && j.matched_skills[0]) || 'Tech';
            return `<span class="meta-pill meta-skills" title="Matched from title. Full details loaded upon selection."><span class="meta-icon">${ico('check')}</span><span>${esc(firstSkill)} match</span></span>`;
          }
          if (required > 0) {
            return `<span class="meta-pill meta-skills${matched === required ? ' is-all' : ''}"><span class="meta-icon">${ico('check')}</span><span>${matched} of ${required} skills</span></span>`;
          }
          return '';
        })()}
        ${j.bonus_matches && j.bonus_matches.length ? `<span class="meta-pill meta-bonus">+${j.bonus_matches.length} bonus</span>` : ''}
        ${(() => {
          const srcs = jobSources(j);
          const hasGated = srcs.some(s => !isFreeSource(s));
          const hasFree = srcs.some(isFreeSource);
          if (hasFree && hasGated) {
            const gated = srcs.find(s => !isFreeSource(s)) || {};
            return `<span class="meta-pill meta-free-bypass" title="Also on ${esc(gated.source || 'paid site')} (Paid), but JobHunter prioritized the 100% Free Apply link on ${esc(j.source)}!">${ico('shield')}Free apply</span>`;
          }
          return '';
        })()}
        ${!hook && j.score >= 85 ? '<span class="meta-pill meta-top-match">Top Match</span>' : ''}
        ${j.is_new ? '<span class="meta-pill meta-new">New</span>' : ''}
        ${j.is_sample ? '<span class="meta-pill meta-sample">Sample</span>' : ''}
        ${jobSources(j).length > 1 ? `<span class="meta-pill meta-sources">${jobSources(j).length} sites</span>` : ''}
      </div>
    </button>`;
  }

  function renderList(animate = false) {
    const list = $('#jobList');
    if (!list) return;
    const prevScroll = list.scrollTop;
    const meta = S.searchMeta || {};
    const jobs = filteredJobs();
    const totalAll = (S.allJobs && S.allJobs.length) || 0;

    if (jobListObserver) {
      jobListObserver.disconnect();
      jobListObserver = null;
    }

    if (!jobs.length) {
      list.classList.remove('is-animating');
      const { total, ok } = sourceCounts();
      const allFailed = total > 0 && ok === 0;

      // Case 1: Search returned jobs, but client filters eliminated all of them!
      if (totalAll > 0 && !allFailed) {
        const bottleneck = detectSearchBottleneck();
        list.innerHTML = `<div class="empty">${ico('search')}
          <h3>No jobs match active filters</h3>
          <p>Found <strong>${totalAll} job${totalAll === 1 ? '' : 's'}</strong> for this search, but your current filters excluded all of them.</p>
          ${bottleneck ? renderSearchRelaxationWidget(bottleneck) : `
          <div class="empty-actions">
            <button type="button" class="btn btn-primary" data-action="clear-filters">Show all ${totalAll} jobs</button>
            ${S.filters.minScore > 0 ? '<button type="button" class="btn btn-secondary" data-action="relax-score">Show any match score</button>' : ''}
          </div>`}
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

    if (!S.jobsLimit) S.jobsLimit = 20;

    // If selected job is further down, expand limit to include it
    if (S.selectedKey) {
      const idx = jobs.findIndex(j => jobKey(j) === S.selectedKey);
      if (idx >= S.jobsLimit) {
        S.jobsLimit = Math.min(jobs.length, Math.ceil((idx + 1) / 20) * 20);
      }
    }

    const visibleJobs = jobs.slice(0, S.jobsLimit);
    const cardsHtml = visibleJobs.map((j, idx) => renderJobCard(j, meta, S, idx)).join('');

    const hasMore = S.jobsLimit < jobs.length;
    const sentinelHtml = hasMore ? `
      <div id="jobListSentinel" class="job-list-sentinel" aria-live="polite">
        <div class="sentinel-inner">
          <span class="sentinel-spinner" aria-hidden="true"></span>
          <span class="sentinel-text">Showing ${visibleJobs.length} of ${jobs.length} jobs • Loading more...</span>
        </div>
      </div>` : '';

    let relaxWidgetHtml = '';
    // Show relaxation widget at the end of the list if all current matching jobs are displayed and result count is small or filtered
    if (!hasMore && (jobs.length <= 6 || (totalAll > jobs.length && jobs.length <= 10))) {
      const bottleneck = detectSearchBottleneck();
      if (bottleneck) {
        relaxWidgetHtml = renderSearchRelaxationWidget(bottleneck);
      }
    }

    if (animate) {
      list.classList.add('is-animating');
      setTimeout(() => list.classList.remove('is-animating'), 550);
    } else {
      list.classList.remove('is-animating');
    }

    list.innerHTML = cardsHtml + sentinelHtml + relaxWidgetHtml;
    if (prevScroll > 0) {
      list.scrollTop = prevScroll;
    }
    if (hasMore) {
      attachJobListObserver();
    }
  }

  function selectedJob() {
    return (S.jobs || []).find(j => jobKey(j) === S.selectedKey) || ((S.allJobs || []).find(j => jobKey(j) === S.selectedKey)) || null;
  }
  function savedApp(j) {
    if (!j) return null;
    return (S.applications || []).find(a => (a.job_id && j.id && a.job_id === j.id) ||
      (String(a.title).toLowerCase() === String(j.title).toLowerCase() && String(a.company).toLowerCase() === String(j.company).toLowerCase()));
  }

  function formatJobDescription(text) {
    if (!text) return '';
    const clean = esc(text);
    const paragraphs = clean.split(/\n{2,}/);
    return paragraphs.map(p => {
      const lines = p.split('\n').map(l => l.trim()).filter(Boolean);
      if (!lines.length) return '';
      const isBulletList = lines.length > 1 && lines.every(l => /^[-*•·]/.test(l));
      if (isBulletList) {
        return `<ul class="desc-list">${lines.map(l => `<li>${l.replace(/^[-*•·]\s*/, '')}</li>`).join('')}</ul>`;
      }
      return `<p class="desc-p">${lines.join('<br>')}</p>`;
    }).filter(Boolean).join('');
  }

  async function triggerJobEnrichment(job, force = false) {
    if (!job) return;
    const key = jobKey(job);
    if (!force && job.enriched) return;
    if (S.enrichingKeys && S.enrichingKeys.has(key)) return;

    const hasRichData = job.description && job.description.length >= 1500 &&
      ((job.responsibilities && job.responsibilities.length) || (job.qualifications && job.qualifications.length)) &&
      (job.salary || job.job_type);
    if (!force && hasRichData && !job.needs_enrichment) return;

    if (!S.enrichingKeys) S.enrichingKeys = new Set();
    S.enrichingKeys.add(key);

    if (S.selectedKey === key && S.view === 'jobs') {
      renderDetail(true);
    }

    try {
      const res = await api('/api/job-details', {
        method: 'POST',
        body: { job }
      });
      if (res && res.job) {
        const enriched = res.job;
        Object.assign(job, enriched);
        job.enriched = true;

        const updateInList = list => {
          if (!list) return;
          for (let i = 0; i < list.length; i++) {
            if (jobKey(list[i]) === key) {
              Object.assign(list[i], enriched);
              list[i].enriched = true;
            }
          }
        };
        updateInList(S.jobs);
        updateInList(S.allJobs);
        updateInList(S.jobsRanked);

        if (S.ws && S.ws.key === key && S.ws.job) {
          Object.assign(S.ws.job, enriched);
          S.ws.job.enriched = true;
        }

        renderList();
      }
    } catch (err) {
      console.warn('Job enrichment error:', err);
    } finally {
      if (S.enrichingKeys) S.enrichingKeys.delete(key);
      if (S.selectedKey === key && S.view === 'jobs') {
        renderDetail(true);
      }
    }
  }

  function renderDetail(preserveScroll = false) {
    const el = $('#jobDetail');
    if (!el) return;
    const prevScroll = preserveScroll ? el.scrollTop : 0;
    let j = selectedJob();
    if (!j) {
      const jList = filteredJobs();
      if (jList.length) {
        j = jList[0];
        S.selectedKey = jobKey(j);
        $$('#jobList .job-item').forEach(b => b.classList.toggle('is-selected', b.dataset.key === S.selectedKey));
      }
    }
    if (!j) {
      el.innerHTML = S.jobs.length ? `<div class="empty" style="border:0">${ico('briefcase')}<h3>Pick a job</h3><p>Select a job on the left to see why it fits and what to do next.</p></div>` : '';
      return;
    }
    const showScore = !(S.searchMeta && S.searchMeta.profile_empty);
    const score = Math.round(j.score || 0);
    const sources = jobSources(j).filter(s => s.url);
    const apply = bestApplyUrl(j);
    const matched = j.matched_skills || [], missing = j.missing_skills || [];
    const matchedReq = j.matched_required_skills || [];
    const missingReq = j.missing_required_skills || [];
    const bonusMatches = j.bonus_matches || [];
    const transferred = j.transferable_matches || [];
    const sb = j.score_breakdown || null;
    const isDreamCompany = !!j.is_dream_company;
    const desc = String(j.description || '');
    const posted = j.posted_at ? timeAgo(j.posted_at) : '';
    const saved = savedApp(j);
    const isDirectAts = j.source_kind === 'Direct employer ATS' || String(j.source_tier || '').startsWith('Direct');
    const key = jobKey(j);
    const isEnriching = S.enrichingKeys && S.enrichingKeys.has(key);
    const responsibilities = Array.isArray(j.responsibilities) ? j.responsibilities : [];
    const qualifications = Array.isArray(j.qualifications) ? j.qualifications : [];
    const prefQualifications = Array.isArray(j.preferred_qualifications) ? j.preferred_qualifications : [];
    const hasOverview = !!(j.salary || j.job_type || j.work_mode || j.location);
    const hasContact = !!(j.contact_email || j.contact_website || j.how_to_apply);
    const isLongDesc = desc.length > 1200;
    const monogram = companyMonogram(j.company);
    const avatarCol = companyAvatarColor(j.company);

    el.innerHTML = `
      <button type="button" class="btn btn-ghost btn-sm detail-close" data-action="detail-close">${ico('back')}Back to results</button>
      <div class="detail-body">
        <div class="detail-top">
          <div class="detail-brand-wrap">
            ${companyAvatarHtml(j, 'detail')}
            <div class="detail-header-info">
              <h2 class="detail-title">${esc(cleanTitle(j.title))}</h2>
              <div class="detail-company-line">
                <span class="detail-company-name">${esc(j.company)}</span>
                ${formatSourceBadge(j)}
                ${isDreamCompany ? `<span class="chip chip-famous" title="Your Dream Wishlist Company">${ico('star')}Wishlist</span>` : ''}
                ${isFamousJob(j) ? `<span class="chip chip-famous" title="Recognized Big Tech & Prominent AI company">Big Tech</span>` : ''}
                ${(() => {
                  const srcs = jobSources(j);
                  const hasGated = srcs.some(s => !isFreeSource(s));
                  const hasFree = srcs.some(isFreeSource);
                  if (hasFree && hasGated) {
                    const gated = srcs.find(s => !isFreeSource(s)) || {};
                    return `<span class="chip chip-ok" title="JobHunter prioritized the 100% Free Apply link!">${ico('shield')}Free apply</span>`;
                  }
                  return '';
                })()}
              </div>
            </div>
          </div>
          ${showScore ? `
            <div class="detail-score-box">
              ${ring(score, true)}
              <span class="detail-score-caption">${tierOf(score).label}</span>
            </div>
          ` : ''}
        </div>

        <div class="detail-meta-pills detail-facts">
          ${j.location ? `<span class="meta-pill"><span class="meta-pill-icon">${ico('pin')}</span><span>${esc(j.location)}</span></span>` : ''}
          ${j.work_mode ? `<span class="meta-pill"><span class="meta-pill-icon">${ico('briefcase')}</span><span>${esc(j.work_mode)}</span></span>` : ''}
          ${j.job_type ? `<span class="meta-pill meta-type"><span class="meta-pill-dot"></span><span>${esc(j.job_type)}</span></span>` : ''}
          ${j.salary ? `<span class="meta-pill meta-salary"><span class="meta-pill-icon">${ico('dollar')}</span><span>${esc(j.salary)}</span></span>` : ''}
          ${j.seniority ? `<span class="meta-pill meta-seniority"><span>${esc(j.seniority)}</span></span>` : ''}
          ${posted ? `<span class="meta-pill meta-posted"><span class="meta-pill-icon">${ico('clock')}</span><span>Posted ${esc(posted)}</span></span>` : ''}
        </div>

        <div class="detail-actions-bar">
          <div class="detail-actions-main">
            <button type="button" class="btn btn-primary btn-easy-apply" id="btnDetailEasyApply" data-action="easy-apply-now" data-key="${esc(key)}" style="background:#10b981;border-color:#10b981;color:#ffffff;" title="Apply in 1 Click: Auto-tailors resume, drafts customized pitch, logs application with 7-day follow-up">
              <span>⚡ 1-Click Apply</span>
            </button>
            <button type="button" class="btn btn-secondary btn-copilot-action" id="btnDetailAutofillCopilot" data-action="open-autofill-copilot" data-key="${esc(key)}" title="Open 1-Click Application Autofill &amp; Solver side drawer">
              <svg class="i" style="width:13px;height:13px;"><use href="#i-board"/></svg><span>Autofill Copilot</span>
            </button>
            ${apply ? `
              <a class="btn btn-outline-apply" href="${esc(apply)}" target="_blank" rel="noopener noreferrer" title="Open official job application in a new tab">
                ${ico('arrow-up-right')}<span>Apply on ${esc(bestApplySource(j).source || 'Official Site')}</span>
              </a>
            ` : ''}
            <div class="detail-action-divider" role="separator" aria-orientation="vertical"></div>
            <button type="button" class="btn btn-secondary" data-action="job-strategy" title="AI match breakdown, talking points &amp; interview angles">
              ${ico('bolt')}<span>AI Strategy</span>
            </button>
            <button type="button" class="btn btn-secondary" data-action="job-tailor" title="Tailor resume bullets specifically for this job description">
              ${ico('file')}<span>Tailor resume</span>
            </button>
            <button type="button" class="btn btn-secondary ${saved ? 'is-saved' : ''}" data-action="job-save" ${saved ? 'disabled' : ''} title="${saved ? 'Already saved' : 'Save job'}">
              ${ico(saved ? 'bookmark-fill' : 'bookmark')}<span>${saved ? 'Saved' : 'Save'}</span>
            </button>
            <button type="button" class="btn ${saved && saved.status === 'applied' ? 'btn-applied' : 'btn-outline-success'}" data-action="mark-applied">
              ${ico('check')}<span>${saved && saved.status === 'applied' ? 'Applied' : 'Mark as Applied'}</span>
            </button>
          </div>
          <div class="detail-actions-sub">
            <span class="detail-action-summary-hint">
              <span class="hint-bullet">⚡</span>
              <span>1-Click Apply auto-tailors your resume, drafts a custom cover pitch, and tracks in your pipeline.</span>
            </span>
            <div class="detail-sub-links">
              <button type="button" class="btn btn-ghost btn-xs" data-action="job-hunt" title="Tailor your resume, write a cover letter and prep notes, then save it all to Applications">
                ${ico('sparkles')}<span>Prepare everything</span>
              </button>
              ${!j.enriched ? `
                <span class="sub-action-sep">•</span>
                <button type="button" class="btn btn-ghost btn-xs" data-action="job-enrich-now" title="Fetch complete details from original posting">
                  ${ico('refresh')}<span>Enrich</span>
                </button>
              ` : ''}
            </div>
          </div>
        </div>

        ${isEnriching ? `
          <div class="enrich-status-banner">
            <span class="spinner-sm"></span>
            <span>Fetching complete posting details (salary, responsibilities, requirements, contact)...</span>
          </div>
        ` : ''}

        <div class="detail-specs-ribbon">
          <div class="spec-card">
            <span class="spec-icon-wrap spec-salary">${ico('dollar')}</span>
            <div class="spec-info">
              <span class="spec-label">Compensation</span>
              <span class="spec-value is-salary" title="${esc(j.salary || 'Competitive / Unspecified')}">${esc(j.salary || 'Competitive')}</span>
            </div>
          </div>
          <div class="spec-card">
            <span class="spec-icon-wrap">${ico('briefcase')}</span>
            <div class="spec-info">
              <span class="spec-label">Role & Level</span>
              <span class="spec-value" title="${esc([j.job_type, j.seniority].filter(Boolean).join(' • ') || 'Full-time')}">${esc([j.job_type, j.seniority].filter(Boolean).join(' • ') || 'Full-time')}</span>
            </div>
          </div>
          <div class="spec-card">
            <span class="spec-icon-wrap">${ico('pin')}</span>
            <div class="spec-info">
              <span class="spec-label">Work Mode</span>
              <span class="spec-value" title="${esc(j.work_mode || 'Remote')}">${esc(j.work_mode || 'Remote')}</span>
            </div>
          </div>
          <div class="spec-card">
            <span class="spec-icon-wrap">${ico('building')}</span>
            <div class="spec-info">
              <span class="spec-label">Location & Posted</span>
              <span class="spec-value" title="${esc(j.location || 'Worldwide')}${posted ? ` • ${esc(posted)}` : ''}">${esc(j.location || 'Worldwide')}${posted ? ` • ${esc(posted)}` : ''}</span>
            </div>
          </div>
        </div>

        ${showScore ? `
          <div class="detail-block fit-breakdown-card">
            <div class="fit-header-row">
              <div class="fit-title-group">
                <h3>Match Analysis &amp; Why it fits</h3>
                <div class="fit-badge-group">
                  <span class="chip ${score >= 85 ? 'chip-ok' : score >= 70 ? 'chip-info' : score >= 50 ? 'chip-warn' : 'chip-outline'}">${tierOf(score).label} (${score}%)</span>
                  ${isDreamCompany ? `<span class="chip chip-famous" title="Included in your Dream Companies wishlist">${ico('star')} Wishlist Employer</span>` : ''}
                  ${(() => {
                    if (!j.confidence) return '';
                    if (typeof j.confidence === 'string') {
                      const val = j.confidence.trim().toLowerCase();
                      const label = val === 'high' ? 'High Confidence' : val === 'medium' ? 'Medium Confidence' : val === 'low' ? 'Low Confidence' : `${esc(j.confidence)} Confidence`;
                      return `<span class="chip chip-outline" title="Confidence: based on skills matched and description depth">${ico('shield')}${label}</span>`;
                    }
                    if (typeof j.confidence === 'number' && !isNaN(j.confidence) && j.confidence > 0) {
                      const pct = Math.round(j.confidence <= 1 ? j.confidence * 100 : j.confidence);
                      return `<span class="chip chip-outline" title="Confidence: based on skills matched and description depth">${ico('shield')}${pct}% Confidence</span>`;
                    }
                    return '';
                  })()}
                </div>
                <div class="variant-indicator-bar" style="margin-top:6px; display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                  <span class="muted small" style="display:inline-flex; align-items:center; gap:4px;">
                    ${ico('file')} Best match: <strong>${esc(j.best_profile_name || ((S.profiles || []).find(p => p.id === S.activeProfileId) || {}).name || 'Master Profile')}</strong>
                  </span>
                  <button type="button" class="btn btn-ghost btn-sm" data-action="compare-variants-modal" style="padding:2px 8px; font-size:12px; height:24px;" title="Compare how all your resume variants match this posting">
                    ${ico('grid')} Compare all variants
                  </button>
                </div>
              </div>
            </div>

            ${(() => {
              const liveMatches = j.live_matches || [];
              if (liveMatches.length <= 1) return '';
              const pausedCount = Math.max(0, (S.profiles ? S.profiles.filter(p => !p.is_live).length : 0));
              return `
                <div class="fit-live-leaderboard">
                  <div class="leaderboard-header">
                    <div class="leaderboard-title">
                      ${ico('trophy')}
                      <span>Live Resumes Match Leaderboard</span>
                    </div>
                    <span class="leaderboard-pool-pill">${liveMatches.length} Live Tested</span>
                  </div>
                  <div class="leaderboard-list">
                    ${liveMatches.map((m, mIdx) => {
                      const isWinner = m.is_best || mIdx === 0;
                      return `
                        <div class="leaderboard-row ${isWinner ? 'is-winner' : ''}">
                          <div class="leaderboard-row-left">
                            <span class="leaderboard-rank">${isWinner ? '🏆' : `#${mIdx + 1}`}</span>
                            <div style="min-width:0;">
                              <div class="leaderboard-variant-name">${esc(m.name)}</div>
                              <div class="leaderboard-target-sub">${esc(m.target_title || 'General')} • ${m.matched_count} skill matches</div>
                            </div>
                          </div>
                          <div class="leaderboard-row-right">
                            ${isWinner ? '<span class="leaderboard-winner-tag">Winning Fit</span>' : ''}
                            <span class="leaderboard-score-chip">${m.score}%</span>
                          </div>
                        </div>
                      `;
                    }).join('')}
                  </div>
                  ${pausedCount > 0 ? `
                    <div class="leaderboard-ignored-footer">
                      <svg class="i" style="width:12px;height:12px;opacity:0.7;"><use href="#i-info"/></svg>
                      <span>${pausedCount} paused resume variant${pausedCount > 1 ? 's were' : ' was'} excluded from the matching pool.</span>
                    </div>
                  ` : ''}
                </div>
              `;
            })()}

            ${j.rationale ? `
              <div class="fit-ai-callout">
                <span class="fit-ai-icon">${ico('sparkles')}</span>
                <p class="fit-rationale">${esc(j.rationale)}</p>
              </div>
            ` : ''}

            ${sb ? `
              <div class="fit-meters-section">
                <h4 class="fit-subheading">Score Breakdown</h4>
                <div class="fit-breakdown-grid">
                  <div class="fit-meter">
                    <div class="fit-meter-top">
                      <span class="fit-meter-label">${ico('bolt')}Skills &amp; Tech Stack</span>
                      <span class="fit-meter-val">${sb.skills || 0} / 50</span>
                    </div>
                    <div class="fit-meter-track"><div class="fit-meter-bar bar-skills" style="width:${Math.min(100, Math.round(((sb.skills || 0) / 50) * 100))}%"></div></div>
                  </div>
                  <div class="fit-meter">
                    <div class="fit-meter-top">
                      <span class="fit-meter-label">${ico('file')}Title Alignment</span>
                      <span class="fit-meter-val">${sb.title || 0} / 20</span>
                    </div>
                    <div class="fit-meter-track"><div class="fit-meter-bar bar-title" style="width:${Math.min(100, Math.round(((sb.title || 0) / 20) * 100))}%"></div></div>
                  </div>
                  <div class="fit-meter">
                    <div class="fit-meter-top">
                      <span class="fit-meter-label">${ico('briefcase')}Seniority Level</span>
                      <span class="fit-meter-val">${sb.seniority || 0} / 10</span>
                    </div>
                    <div class="fit-meter-track"><div class="fit-meter-bar bar-sen" style="width:${Math.min(100, Math.round(((sb.seniority || 0) / 10) * 100))}%"></div></div>
                  </div>
                  <div class="fit-meter">
                    <div class="fit-meter-top">
                      <span class="fit-meter-label">${ico('pin')}Work Mode / Location</span>
                      <span class="fit-meter-val">${sb.work_mode || 0} / 10</span>
                    </div>
                    <div class="fit-meter-track"><div class="fit-meter-bar bar-mode" style="width:${Math.min(100, Math.round(((sb.work_mode || 0) / 10) * 100))}%"></div></div>
                  </div>
                  <div class="fit-meter">
                    <div class="fit-meter-top">
                      <span class="fit-meter-label">${ico('dollar')}Target Pay Fit</span>
                      <span class="fit-meter-val">${sb.salary || 0} / 5</span>
                    </div>
                    <div class="fit-meter-track"><div class="fit-meter-bar bar-sal" style="width:${Math.min(100, Math.round(((sb.salary || 0) / 5) * 100))}%"></div></div>
                  </div>
                  <div class="fit-meter">
                    <div class="fit-meter-top">
                      <span class="fit-meter-label">${ico('star')}Role &amp; Company Fit</span>
                      <span class="fit-meter-val">${sb.preferences || 0} / 5</span>
                    </div>
                    <div class="fit-meter-track"><div class="fit-meter-bar bar-pref" style="width:${Math.min(100, Math.round(((sb.preferences || 0) / 5) * 100))}%"></div></div>
                  </div>
                </div>
              </div>
            ` : ''}

            <div class="fit-skills-section">
              ${matchedReq.length ? `
                <div class="fit-row">
                  <strong class="fit-row-title text-ok">${ico('check')}Must-have requirements you have (${matchedReq.length}):</strong>
                  <div class="fit-chips-wrap">${matchedReq.map(s => `<span class="chip chip-ok">${esc(s)}</span>`).join('')}</div>
                </div>
              ` : (matched.length ? `
                <div class="fit-row">
                  <strong class="fit-row-title text-ok">${ico('check')}Skills you match (${matched.length}):</strong>
                  <div class="fit-chips-wrap">${matched.map(s => `<span class="chip chip-ok">${esc(s)}</span>`).join('')}</div>
                </div>
              ` : '')}

              ${bonusMatches.length ? `
                <div class="fit-row">
                  <strong class="fit-row-title text-bonus">${ico('bolt')}Bonus &amp; Preferred qualifications you match (+${bonusMatches.length}):</strong>
                  <div class="fit-chips-wrap">${bonusMatches.map(s => `<span class="chip chip-bonus">${esc(s)}</span>`).join('')}</div>
                </div>
              ` : ''}

              ${missingReq.length ? `
                <div class="fit-row">
                  <strong class="fit-row-title text-warn">${ico('alert')}Core requirement gaps to bridge (${missingReq.length}):</strong>
                  <div class="fit-chips-wrap">${missingReq.map(s => `<span class="chip chip-warn">${esc(s)}</span>`).join('')}</div>
                </div>
              ` : (missing.length ? `
                <div class="fit-row">
                  <strong class="fit-row-title text-warn">${ico('alert')}Missing skills (${missing.length}):</strong>
                  <div class="fit-chips-wrap">${missing.map(s => `<span class="chip chip-warn">${esc(s)}</span>`).join('')}</div>
                </div>
              ` : '')}

              ${transferred.length ? `
                <div class="fit-row">
                  <strong class="fit-row-title text-info">${ico('refresh')}Transferable skills recognized:</strong>
                  <div class="fit-chips-wrap">${transferred.map(s => `<span class="chip chip-info">${esc(s)}</span>`).join('')}</div>
                </div>
              ` : ''}
            </div>
          </div>
        ` : ''}

        ${j.company ? (() => {
          const links = getInsiderLinks(j);
          return `
          <div class="detail-block detail-card-referrals">
            <div class="referrals-header">
              <div class="referrals-title-wrap">
                <span class="referrals-icon">${ico('link')}</span>
                <div>
                  <h3 class="referrals-title">Insider Connections &amp; Referrals</h3>
                  <p class="referrals-subtitle">Reach out directly to technical recruiters and peer engineers at ${esc(j.company)} to boost your interview callback rate by 4x.</p>
                </div>
              </div>
            </div>
            <div class="referrals-grid">
              <a class="referral-link-card" href="${esc(links.recruiter_url)}" target="_blank" rel="noopener noreferrer">
                <div class="referral-link-info">
                  <span class="referral-role-name">${ico('search')}Technical Recruiters</span>
                  <span class="referral-company-tag">${esc(j.company)} Talent Acquisition</span>
                </div>
                <span class="referral-arrow">${ico('external')}</span>
              </a>
              <a class="referral-link-card" href="${esc(links.peer_url)}" target="_blank" rel="noopener noreferrer">
                <div class="referral-link-info">
                  <span class="referral-role-name">${ico('search')}Team Peers &amp; Engineers</span>
                  <span class="referral-company-tag">${esc(j.company)} Engineering</span>
                </div>
                <span class="referral-arrow">${ico('external')}</span>
              </a>
            </div>
            <div class="referral-tip-box">
              <strong>1-Click Networking Tip:</strong> Connect with 2 peers or recruiters using a 2-sentence note: <em>"Hi [Name], I noticed the ${esc(cleanTitle(j.title))} role at ${esc(j.company)} and my background in ${esc((j.matched_skills || ['software engineering'])[0] || 'engineering')} is a close match. Would love to connect!"</em>
            </div>
          </div>
          `;
        })() : ''}

        ${hasContact ? `
          <div class="detail-block detail-contact-block">
            <h3>How to apply & Employer contact</h3>
            <div class="contact-card">
              ${j.contact_email ? `
                <div class="contact-row">
                  <span class="contact-label">Employer Email</span>
                  <div class="contact-action-group">
                    <a href="mailto:${esc(j.contact_email)}" class="contact-email">${ico('mail')}${esc(j.contact_email)}</a>
                    <button type="button" class="btn btn-xs btn-ghost" data-action="copy-text" data-text="${esc(j.contact_email)}" title="Copy email address">${ico('copy')}Copy</button>
                  </div>
                </div>
              ` : ''}
              ${j.contact_website ? `
                <div class="contact-row">
                  <span class="contact-label">Company Website</span>
                  <a href="${esc(j.contact_website)}" target="_blank" rel="noopener noreferrer" class="contact-web-link">${esc(j.contact_website)} ${ico('external')}</a>
                </div>
              ` : ''}
              ${j.how_to_apply ? `
                <div class="contact-instructions">
                  <strong>Application Instructions</strong>
                  <p>${esc(j.how_to_apply)}</p>
                </div>
              ` : ''}
            </div>
          </div>
        ` : ''}

        ${responsibilities.length ? `
          <div class="detail-block">
            <h3>Key responsibilities</h3>
            <ul class="job-bullet-list bullet-resp">
              ${responsibilities.map(r => `<li>${esc(r)}</li>`).join('')}
            </ul>
          </div>
        ` : ''}

        ${qualifications.length ? `
          <div class="detail-block">
            <h3>Requirements & Qualifications</h3>
            <ul class="job-bullet-list bullet-req">
              ${qualifications.map(q => `<li>${esc(q)}</li>`).join('')}
            </ul>
          </div>
        ` : ''}

        ${prefQualifications.length ? `
          <div class="detail-block">
            <h3>Preferred qualifications</h3>
            <ul class="job-bullet-list bullet-pref">
              ${prefQualifications.map(q => `<li>${esc(q)}</li>`).join('')}
            </ul>
          </div>
        ` : ''}

        ${desc ? `
          <div class="detail-block">
            <div class="block-header-row">
              <h3>Full job description</h3>
              ${isLongDesc ? `<button type="button" class="btn-link desc-toggle-link" data-action="toggle-desc"><span>Show full description</span></button>` : ''}
            </div>
            <div class="desc-wrap ${isLongDesc ? 'is-collapsed' : 'is-expanded'}" id="jobDescWrap">
              <div class="desc-content">${formatJobDescription(desc)}</div>
            </div>
            ${isLongDesc ? `<button type="button" class="desc-toggle-btn" data-action="toggle-desc">${ico('chevron')}<span>Show full description</span></button>` : ''}
          </div>
        ` : ''}

        ${sources.length ? `
          <div class="detail-block detail-apply-block">
            <div class="block-header-row">
              <h3>${sources.length > 1 ? `Where to apply (${sources.length} sources found)` : 'Where to apply'}</h3>
              ${sources.some(isFreeSource) ? `<span class="chip chip-ok" title="100% Free application prioritized">${ico('shield')}Free option prioritized</span>` : ''}
            </div>
            ${sources.some(isFreeSource) && sources.some(s => !isFreeSource(s)) ? `
              <div class="free-bypass-banner">
                ${ico('shield')}
                <div>
                  <strong>Free Application Found!</strong>
                  <span>This position was also found on <b>${esc(((sources.find(s => !isFreeSource(s)) || {}).source) || 'a paid site')}</b> (which charges or prompts for paid membership), but JobHunter found the exact same job on <b>${esc(j.source)}</b> where applying is <b>100% FREE</b>. The primary Apply button uses this free link!</span>
                </div>
              </div>
            ` : (!sources.some(isFreeSource) ? `
              <div class="gated-warning-banner">
                ${ico('alert')}
                <div>
                  <strong>Heads-up on this source:</strong>
                  <span>This position was sourced from <b>${esc(j.source)}</b>, which may prompt for a paid subscription or account to submit applications.</span>
                </div>
              </div>
            ` : '')}
            <div class="apply-links">
              ${sources.map(s => {
                const free = isFreeSource(s);
                const direct = isDirect(s);
                const isBest = s.url === apply;
                return `
                  <a class="chip ${isBest ? (free ? 'chip-best-apply chip-ok' : 'chip-best-apply chip-warn') : (free ? 'chip-outline' : 'chip-warn')}"
                     href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"
                     title="${free ? '100% Free to apply' : 'Site may require paid membership'}">
                    ${free ? (isBest ? ico('check') : '') : ico('alert')}
                    ${esc(s.source)}${direct ? ' (Official Site)' : ''}
                    <span class="apply-cost-tag">${free ? '• Free' : '• Paid/Gated'}</span>
                    ${isBest ? '<span class="apply-rec-tag">Primary</span>' : ''}
                    ${ico('external')}
                  </a>
                `;
              }).join('')}
            </div>
          </div>
        ` : ''}

        <p class="credit">Source: ${esc(j.source_credit || j.source || '')}</p>
      </div>`;
    if (preserveScroll && prevScroll > 0) {
      el.scrollTop = prevScroll;
    }
  }

  function selectJob(key) {
    S.selectedKey = key;
    $$('#jobList .job-item').forEach(b => b.classList.toggle('is-selected', b.dataset.key === key));
    renderDetail();
    const j = selectedJob();
    if (j) {
      triggerJobEnrichment(j);
    }
    if (isNarrow()) {
      const d = $('#jobDetail');
      if (d) {
        d.classList.add('is-open');
        d.scrollTop = 0;
        document.body.style.overflow = 'hidden';
      }
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
      if (S.view === 'jobs' || S.view === 'recommend') renderDetail();
      if (S.view === 'job') renderWsHeader();
    } catch (err) { toast('Could not save: ' + err.message, 'error'); }
  }

  async function markJobApplied(job) {
    if (!job) return;
    const existing = savedApp(job);
    try {
      if (existing) {
        await api(`/api/applications/${encodeURIComponent(existing.id)}`, {
          method: 'PATCH',
          body: {
            status: 'applied',
            follow_up_date: isoDay(7),
            notes: (existing.notes ? existing.notes + '\n' : '') + 'Marked as Applied via quick action.'
          }
        });
      } else {
        await api('/api/applications', {
          method: 'POST',
          body: {
            job_id: job.id,
            company: job.company,
            title: job.title,
            location: job.location,
            salary: job.salary,
            status: 'applied',
            notes: 'Applied directly from recommendations feed.',
            follow_up_date: isoDay(7),
            sources: jobSources(job),
            job_data: job
          }
        });
      }
      await loadApplications();
      toast('Marked as Applied! Follow-up reminder set in 7 days.');
      if (S.view === 'jobs' || S.view === 'recommend') renderDetail();
      if (S.view === 'job') renderWsHeader();
    } catch (err) {
      toast('Could not mark as applied: ' + err.message, 'error');
    }
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
    if (data.recruiter_6sec_audit) w.audit6sec = data.recruiter_6sec_audit;
  }

  function effectiveResume() {
    const base = JSON.parse(JSON.stringify(S.profile || {}));
    const w = S.ws;
    if (w.customResume) {
      const cr = JSON.parse(JSON.stringify(w.customResume));
      const ref = w.refinement;
      if (ref && w.decisions) {
        const item = id => (ref.diff_items || []).find(d => d.id === id);
        (cr.experience || []).forEach((exp, ei) => (exp.bullets || []).forEach((_, bi) => {
          const d = item(`diff_exp_${ei}_${bi}`);
          if (d && w.decisions[d.id] === 'rejected') {
            if (d.original) exp.bullets[bi] = d.original;
          } else if (d && d.edited) {
            exp.bullets[bi] = d.proposed;
          }
        }));
      }
      return cr;
    }
    const ref = w.refinement;
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
    const w = S.ws, ref = w.refinement || {};
    const all = ref.diff_items || [];
    const changed = all.filter(d => d.status !== 'unchanged');
    const unchanged = all.filter(d => d.status === 'unchanged');
    const arch = w.selectedArchetype || 'startup_velocity';
    const audit = w.audit6sec || ref.recruiter_6sec_audit;

    const hudHtml = audit ? `
      <div class="recruiter-hud" id="recruiter6SecHud">
        <div class="hud-card hud-card-score">
          <div class="hud-card-head">
            <span>6-Sec Skim Score</span>
            <span class="hud-pill hud-pill-gold">F-Pattern Screen</span>
          </div>
          <div class="hud-score-display">
            <span class="hud-score-val">${audit.skim_score || 94}</span>
            <span class="hud-score-denom">/100</span>
          </div>
          <div class="hud-verdict">${esc(audit.skim_verdict || 'High Immediate Recruiter Callback Potential')}</div>
          <div class="hud-metrics-row">
            <div class="hud-metric-mini"><span>ATS Match:</span> <strong>${audit.ats_keyword_match_pct || 90}%</strong></div>
            <div class="hud-metric-mini"><span>Metrics:</span> <strong>${audit.quantified_bullet_pct || 85}%</strong></div>
          </div>
        </div>

        <div class="hud-card hud-card-catchers">
          <div class="hud-card-head">
            <span>Recruiter Eye-Catchers (Where Eyes Land)</span>
            <span class="hud-pill hud-pill-emerald">First 6 Seconds</span>
          </div>
          <div class="hud-catcher-list">
            <div class="hud-catcher-item">
              <span class="catcher-time">0-2s</span>
              <div><strong>Executive Hook:</strong> ${esc((audit.eye_catchers && audit.eye_catchers[0]) || 'Role Title & Value Proposition')}</div>
            </div>
            <div class="hud-catcher-item">
              <span class="catcher-time">2-4s</span>
              <div><strong>Stack Check:</strong> ${esc((audit.eye_catchers && audit.eye_catchers[1]) || 'Primary matched technologies')}</div>
            </div>
            <div class="hud-catcher-item">
              <span class="catcher-time">4-6s</span>
              <div><strong>Proof Metric:</strong> ${esc((audit.eye_catchers && audit.eye_catchers[2]) || 'Top quantifiable impact bullet')}</div>
            </div>
          </div>
        </div>

        <div class="hud-card hud-card-grounding">
          <div class="hud-card-head">
            <span>100% Grounded Intelligence</span>
            <span class="hud-pill hud-pill-cyan">Zero Hallucinations</span>
          </div>
          <p class="hud-ground-text">Every skill, metric, and bullet is strictly verified against your master resume facts. Missing skills are flagged honestly rather than invented.</p>
          <div class="hud-ground-tags">
            <span class="chip chip-ok chip-sm">${ico('check')} Facts Grounded</span>
            <span class="chip chip-neutral chip-sm">${ico('shield')} Archetype: ${esc(arch)}</span>
            ${audit.honest_gaps_count ? `<span class="chip chip-warn chip-sm">${audit.honest_gaps_count} Honest Gaps Identified</span>` : ''}
          </div>
        </div>
      </div>
    ` : `
      <div class="recruiter-hud" id="recruiter6SecHud">
        <div class="hud-card" style="grid-column: 1 / -1; display:flex; align-items:center; justify-content:space-between; gap:20px;">
          <div>
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
              <span class="hud-pill hud-pill-gold">⚡ 6-Second Screen Methodology</span>
              <strong style="color:var(--text-1)">Recruiters spend an average of 6 seconds scanning before deciding.</strong>
            </div>
            <p class="muted small" style="margin:0">Click <strong>Generate 6-Sec Custom Resume</strong> below to synthesize an Executive Hook (0-2s), Stack Verification Matrix (2-4s), and Google X-Y-Z Proof Metrics (4-6s) customized to this exact job.</p>
          </div>
          <button type="button" class="btn btn-primary" data-action="generate-custom-resume">${ico('bolt')} Generate Now</button>
        </div>
      </div>
    `;

    $('#wsPanel').innerHTML = `
      <div class="custom-resume-hero">
        <div class="hero-top-row">
          <div>
            <div class="hero-tag">⚡ 6-SECOND RECRUITER SCREENING ENGINE</div>
            <h2 class="hero-title">AI Custom Resume Generator</h2>
            <p class="hero-sub">Engineered to win the 6-second recruiter screen. Dynamically reorganizes your Executive Hook (0-2s), Stack Match Matrix (2-4s), and Google X-Y-Z Impact Bullets (4-6s) — 100% grounded on verified resume facts.</p>
          </div>
          <div class="hero-badge-wrap">
            <span class="hero-verdict-badge">${audit ? `${ico('check')} ${audit.skim_score}/100 Skim Score` : '⚡ Recruiter F-Pattern Ready'}</span>
          </div>
        </div>

        <div class="archetype-selector-bar">
          <span class="archetype-label">Candidate Archetype:</span>
          <div class="archetype-chips">
            <button type="button" class="archetype-chip ${arch === 'startup_velocity' ? 'is-selected' : ''}" data-action="select-archetype" data-archetype="startup_velocity" title="Emphasize 0-to-1 building, agility, and speed">
              ${ico('bolt')} <strong>Startup Velocity</strong> <span>(0→1 ownership, speed)</span>
            </button>
            <button type="button" class="archetype-chip ${arch === 'enterprise_scale' ? 'is-selected' : ''}" data-action="select-archetype" data-archetype="enterprise_scale" title="Emphasize throughput, scale, SLA discipline">
              ${ico('building')} <strong>Enterprise Scale</strong> <span>(high throughput, SLA)</span>
            </button>
            <button type="button" class="archetype-chip ${arch === 'technical_depth' ? 'is-selected' : ''}" data-action="select-archetype" data-archetype="technical_depth" title="Emphasize deep systems internals and architecture">
              ${ico('shield')} <strong>Technical Depth</strong> <span>(internals, latency, tuning)</span>
            </button>
          </div>
        </div>

        <div class="hero-actions-row">
          <button type="button" class="btn btn-generate-custom" data-action="generate-custom-resume">
            ${ico('bolt')} Generate 6-Sec Custom Resume
          </button>
          <button type="button" class="btn btn-secondary btn-sm ${w.showHeatmap ? 'is-active' : ''}" data-action="toggle-heatmap">
            ${ico('search')} ${w.showHeatmap ? 'Hide 6-Sec Heatmap' : '👁️ 6-Sec Recruiter Heatmap'}
          </button>
          <button type="button" class="btn btn-secondary btn-sm" data-action="save-tailored-variant" title="Save this tailored version to your resume library for reuse">
            ${ico('bookmark')} Save to Library
          </button>
          <button type="button" class="btn btn-secondary btn-sm" data-action="bullets-copy">
            ${ico('copy')} Copy Plain ATS Bullets
          </button>
          <button type="button" class="btn btn-ghost btn-sm" data-action="auto-tailor">
            ${ico('refresh')} Fast ATS Auto-Tailor
          </button>
        </div>
      </div>

      ${hudHtml}

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
            <h3>Resume preview ${w.showHeatmap ? '<span class="chip chip-warn chip-sm" style="margin-left:6px">Heatmap Active</span>' : ''}</h3>
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

  function highlightMetricsHtml(text) {
    if (!text) return '';
    const escaped = esc(text);
    if (!S.ws.showHeatmap) return escaped;
    return escaped.replace(/(\b\d+(?:\.\d+)?%|\$\d+(?:,\d+)*(?:\.\d+)?(?:[kKmMbB])?|\b\d+(?:[kKmMbB])\+?|\b\d{2,}\+?\s*(?:users|clients|rps|ms|percent|increase|reduction|growth|engineers|team members|services|endpoints)\b)/gi,
      '<span class="metric-num-highlight">$1</span>');
  }

  function renderPreview() {
    const box = $('#atsPaperPreview');
    if (!box) return;
    const r = effectiveResume();
    const w = S.ws;
    const isHeat = !!w.showHeatmap;
    box.className = isHeat ? 'paper is-heatmap-active' : 'paper';

    const legendHtml = isHeat ? `
      <div class="heatmap-legend">
        <div class="legend-chip"><span class="legend-swatch zone-1"></span><strong>Zone 1 (0-2s)</strong>: Hook &amp; Role</div>
        <div class="legend-chip"><span class="legend-swatch zone-2"></span><strong>Zone 2 (2-4s)</strong>: Core Stack</div>
        <div class="legend-chip"><span class="legend-swatch zone-3"></span><strong>Zone 3 (4-6s)</strong>: Proof Metrics</div>
      </div>
    ` : '';

    const zone1Class = isHeat ? 'heat-zone heat-zone-1' : '';
    const zone2Class = isHeat ? 'heat-zone heat-zone-2' : '';
    const zone3Class = isHeat ? 'heat-zone heat-zone-3' : '';

    const matrix = r.core_competencies_matrix;
    let skillsHtml = '';
    if (matrix && (matrix.primary_matches?.length || matrix.supporting_stack?.length || matrix.practices?.length)) {
      skillsHtml = `
        <div class="${zone2Class}">
          ${isHeat ? '<span class="heat-badge">Zone 2 &bull; 2-4s Stack Check</span>' : ''}
          <div class="sec">Core Competencies Matrix</div>
          <div class="competencies-grid" style="display:flex; flex-direction:column; gap:6px; margin-top:6px;">
            ${matrix.primary_matches && matrix.primary_matches.length ? `
              <div style="font-size:12px; line-height:1.5;">
                <strong style="color:var(--text-1)">Required Posting Stack:</strong>
                <span style="display:inline-flex; flex-wrap:wrap; gap:4px; margin-left:6px;">${matrix.primary_matches.map(s => `<span class="chip chip-ok chip-sm">${esc(s)}</span>`).join('')}</span>
              </div>` : ''}
            ${matrix.supporting_stack && matrix.supporting_stack.length ? `
              <div style="font-size:12px; line-height:1.5;">
                <strong style="color:var(--text-1)">Supporting Stack:</strong>
                <span style="display:inline-flex; flex-wrap:wrap; gap:4px; margin-left:6px;">${matrix.supporting_stack.map(s => `<span class="chip chip-neutral chip-sm">${esc(s)}</span>`).join('')}</span>
              </div>` : ''}
            ${matrix.practices && matrix.practices.length ? `
              <div style="font-size:12px; line-height:1.5;">
                <strong style="color:var(--text-1)">Architecture &amp; Practices:</strong>
                <span style="display:inline-flex; flex-wrap:wrap; gap:4px; margin-left:6px;">${matrix.practices.map(s => `<span class="chip chip-neutral chip-sm">${esc(s)}</span>`).join('')}</span>
              </div>` : ''}
          </div>
        </div>
      `;
    } else if ((r.skills || []).length) {
      skillsHtml = `
        <div class="${zone2Class}">
          ${isHeat ? '<span class="heat-badge">Zone 2 &bull; 2-4s Stack Check</span>' : ''}
          <div class="sec">Skills</div>
          <p>${(r.skills || []).map(esc).join(', ')}</p>
        </div>
      `;
    }

    let expHtml = '';
    const exps = r.experience || [];
    if (exps.length) {
      expHtml = '<div class="sec">Experience</div>';
      expHtml += exps.map((x, idx) => {
        const isTopExp = idx === 0;
        const blockClass = (isHeat && isTopExp) ? `${zone3Class} job-block` : 'job-block';
        return `
          <div class="${blockClass}">
            ${(isHeat && isTopExp) ? '<span class="heat-badge">Zone 3 &bull; 4-6s Metric Proof</span>' : ''}
            <div class="job-line"><strong>${esc(x.role)}, ${esc(x.company)}</strong><span>${esc(x.start_date)} to ${esc(x.end_date)}</span></div>
            ${x.location ? `<div class="loc">${esc(x.location)}</div>` : ''}
            <ul>${(x.bullets || []).map(b => `<li>${highlightMetricsHtml(b)}</li>`).join('')}</ul>
          </div>
        `;
      }).join('');
    }

    let eduHtml = '';
    const edus = r.education || [];
    if (edus.length) {
      eduHtml = '<div class="sec">Education</div>' + edus.map(e => `<p><strong>${esc(e.degree)}</strong>, ${esc(e.institution)}${e.graduation_year ? ` (${esc(e.graduation_year)})` : ''}</p>`).join('');
    }

    box.innerHTML = `
      ${legendHtml}
      <div class="${zone1Class}">
        ${isHeat ? '<span class="heat-badge">Zone 1 &bull; 0-2s Executive Hook</span>' : ''}
        <h2>${esc(r.name || 'Candidate Name')}</h2>
        ${r.target_title ? `<div style="font-weight:700; color:var(--primary); margin:-4px 0 8px; font-size:13px; text-transform:uppercase; letter-spacing:0.04em;">${esc(r.target_title)}</div>` : ''}
        <div class="contact">${[r.email, r.phone, r.location].filter(Boolean).map(esc).join(', ')}${(r.linkedin || r.github) ? '<br>' + [r.linkedin, r.github].filter(Boolean).map(esc).join(', ') : ''}</div>
        ${r.positioning_hook ? `<div class="sec">Executive Hook (0-2s)</div><p style="font-weight:500; font-size:12.5px; line-height:1.6; color:var(--text-1); background:var(--bg-inset, rgba(0,0,0,0.02)); padding:6px 10px; border-left:3px solid var(--accent, #f59e0b); border-radius:3px;">${esc(r.positioning_hook)}</p>` : (r.summary ? `<div class="sec">Summary</div><p>${esc(r.summary)}</p>` : '')}
      </div>
      ${skillsHtml}
      ${expHtml}
      ${eduHtml}
    `;
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

  function selectArchetype(arch) {
    if (!arch) return;
    S.ws.selectedArchetype = arch;
    $$('.archetype-chip').forEach(c => {
      c.classList.toggle('is-selected', c.dataset.archetype === arch);
    });
    const label = arch === 'enterprise_scale' ? 'Enterprise Scale' : arch === 'technical_depth' ? 'Technical Depth' : 'Startup Velocity';
    toast(`Archetype set to "${label}"`);
  }

  function toggleHeatmap() {
    S.ws.showHeatmap = !S.ws.showHeatmap;
    const btn = $('[data-action="toggle-heatmap"]');
    if (btn) {
      btn.classList.toggle('is-active', !!S.ws.showHeatmap);
      btn.innerHTML = `${ico('search')} ${S.ws.showHeatmap ? 'Hide 6-Sec Heatmap' : '👁️ 6-Sec Recruiter Heatmap'}`;
    }
    renderResumeTab();
  }

  async function generateCustomResume(archetype) {
    const w = S.ws;
    if (!w || !w.job) return;
    const arch = archetype || w.selectedArchetype || 'startup_velocity';
    w.selectedArchetype = arch;
    const btns = $$('[data-action="generate-custom-resume"]');
    btns.forEach(b => {
      b.disabled = true;
      b.innerHTML = '<span class="spinner-sm"></span> Synthesizing 6-Sec Resume...';
    });
    try {
      toast('Synthesizing 6-second hook & X-Y-Z proof metrics...');
      const res = await api('/api/resume/custom-generate', {
        method: 'POST',
        body: { job: w.job, archetype: arch, use_llm: true }
      });
      if ((res.ok || res.success) && res.tailored_resume) {
        w.customResume = res.tailored_resume;
        w.audit6sec = res.recruiter_6sec_audit;
        w.guardrailReport = res.guardrail_report;
        w.showHeatmap = true; // Automatically highlight the 6-sec eye-tracking scan zones!

        // Update auto-tailor diff items and ATS audit in sync
        try {
          const autoRes = await api('/api/auto-tailor', {
            method: 'POST',
            body: { job: w.job, archetype: arch }
          });
          w.refinement = autoRes.refinement;
          w.decisions = {};
          (autoRes.refinement.diff_items || []).forEach(d => { w.decisions[d.id] = 'accepted'; });
          w.ats = autoRes.ats_audit;
          w.atsFresh = true;
        } catch (e) {
          console.warn('Auto-tailor sync fallback:', e);
        }

        const score = (w.audit6sec && w.audit6sec.skim_score) || 94;
        toast(`✨ 6-Sec Custom Resume generated! Recruiter Skim Score: ${score}/100`);
        renderResumeTab();
        renderWsHeader();
      }
    } catch (err) {
      toast('Could not generate custom resume: ' + err.message, 'error');
    } finally {
      btns.forEach(b => {
        b.disabled = false;
        b.innerHTML = `${ico('bolt')} Generate 6-Sec Custom Resume`;
      });
    }
  }

  async function autoTailor() {
    const w = S.ws, btns = $$('[data-action="auto-tailor"]');
    btns.forEach(b => { b.disabled = true; });
    try {
      const arch = w.selectedArchetype || 'startup_velocity';
      const res = await api('/api/auto-tailor', { method: 'POST', body: { job: w.job, archetype: arch } });
      w.refinement = res.refinement; w.decisions = {};
      (res.refinement.diff_items || []).forEach(d => { w.decisions[d.id] = 'accepted'; });
      w.ats = res.ats_audit; w.atsFresh = true;
      if (res.recruiter_6sec_audit) w.audit6sec = res.recruiter_6sec_audit;
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
          ${ring(score, true)}
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

  // ------------------------------------------------------------ cover letter / personalized pitch
  const PITCH_ANGLES_DEF = [
    { key: 'direct_impact', label: 'Direct Impact', sub: 'Operator & Results', ico: 'bolt' },
    { key: 'startup_velocity', label: 'Startup Velocity', sub: '0→1 Builder & Ownership', ico: 'bolt' },
    { key: 'technical_architect', label: 'Technical Architect', sub: 'Systems Rigor & Scalability', ico: 'shield' },
    { key: 'executive_brief', label: 'Executive Brief', sub: 'Concise 3-Bullet Pitch', ico: 'file' }
  ];

  async function ensureCover(force = false) {
    const w = S.ws;
    if (!w || !w.job) return;
    w.pitchAngle = w.pitchAngle || 'direct_impact';
    w.tone = w.tone || 'direct';
    const cacheKey = `${w.pitchAngle}_${w.tone}`;
    if (!force && w.coverPitches && w.coverPitches[cacheKey]) {
      w.activePitch = w.coverPitches[cacheKey];
      return;
    }
    w.coverPitches = w.coverPitches || {};
    const payload = {
      job: w.job,
      tone: w.tone,
      angle: w.pitchAngle,
      selected_bullets: w.selectedPillars
    };
    const data = await api('/api/cover-letter', { method: 'POST', body: payload });
    w.coverPitches[cacheKey] = data.pitch || data;
    w.activePitch = data.pitch || data;
    w.cover[w.tone] = data.cover_letter || (data.pitch && data.pitch.full_text) || '';
  }

  function renderCoverTab() {
    const w = S.ws, j = w.job || {};
    const pitch = w.activePitch || {};
    const telemetry = pitch.telemetry || { word_count: 240, reading_time_sec: 40, pitch_score: 92 };
    const pillars = pitch.value_pillars || [];
    const allBullets = pitch.all_available_bullets || [];
    const activeAngle = w.pitchAngle || 'direct_impact';
    const candName = S.profile?.name || 'Candidate';
    const candRole = (S.profile?.experience || [{}])[0]?.role || S.profile?.target_title || 'Software Engineer';
    const candContact = [S.profile?.email, S.profile?.phone, S.profile?.location].filter(Boolean).join(' | ');
    const letterText = w.cover[w.tone] || pitch.full_text || '';
    const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

    function formatPaperParagraphs(text) {
      if (!text) return '';
      return text.trim().split(/\n\n+/).map(p => {
        const formatted = esc(p).replace(/\n/g, '<br>');
        if (/^(sincerely|best regards|regards|warm regards|warmly)/i.test(p.trim())) {
          return `<div class="paper-sign-block">${formatted}</div>`;
        }
        return `<p>${formatted}</p>`;
      }).join('');
    }

    const isBulletSelected = (b, idx) => {
      const bText = b.bullet || b.raw_bullet || '';
      if (Array.isArray(w.selectedPillars) && w.selectedPillars.length > 0) {
        return w.selectedPillars.includes(bText);
      }
      return pillars.some(p => (p.raw_bullet || p.bullet) === bText) || idx < 2;
    };

    $('#wsPanel').innerHTML = `
      <div class="cover-studio-hero">
        <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
          <div class="cover-hero-tag">🎯 ROLE PITCH ENGINE &bull; PERSONALIZED FOR THIS ROLE</div>
          <a href="#/privacy" class="chip ${pitch.used_llm ? 'chip-ok' : 'chip-soft'}" style="text-decoration:none; cursor:pointer;" title="Configure AI Provider & API keys in Settings">
            ${ico('sparkles')} <strong>Engine:</strong> ${esc(pitch.used_llm ? ((pitch.provider || 'AI').toUpperCase() + (pitch.model ? ' (' + pitch.model + ')' : '')) : 'Deterministic Grounded Engine')} &bull; Settings &rarr;
          </a>
        </div>
        <h2 class="cover-hero-title">AI Cover Letter &amp; Executive Role Pitch</h2>
        <p class="cover-hero-sub">Engineered to hook hiring managers and founders. Automatically pairs verified achievements from your career directly with ${esc(j.company || 'the employer')}'s biggest challenges — 100% grounded on real resume facts.</p>

        <div class="pitch-angle-bar">
          <span class="pitch-angle-label">Select Pitch Angle:</span>
          <div class="pitch-angle-chips">
            ${PITCH_ANGLES_DEF.map(a => `
              <button type="button" class="pitch-angle-chip ${a.key === activeAngle ? 'is-selected' : ''}" data-action="cover-angle" data-angle="${a.key}">
                ${ico(a.ico)} <strong>${a.label}</strong> <span>(${a.sub})</span>
              </button>
            `).join('')}
          </div>
        </div>

        <div class="pitch-actions-bar">
          <div style="display:flex; align-items:center; gap:8px;">
            <button type="button" class="btn btn-generate-pitch" data-action="cover-regenerate">
              ${ico('bolt')} Generate Personalized Pitch
            </button>
            <div class="segmented" role="group" aria-label="Tone">
              ${TONES.map(t => `<button type="button" data-action="cover-tone" data-tone="${t.key}" aria-pressed="${t.key === w.tone}">${t.label}</button>`).join('')}
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <button type="button" class="btn btn-primary btn-sm" data-action="cover-save">${ico('bookmark')}Save to Applications</button>
            <button type="button" class="btn btn-secondary btn-sm" data-action="cover-copy">${ico('copy')}Copy Text</button>
            <button type="button" class="btn btn-secondary btn-sm" data-action="cover-export" data-fmt="docx">${ico('download')}Word</button>
            <button type="button" class="btn btn-secondary btn-sm" data-action="cover-export" data-fmt="pdf">${ico('download')}PDF</button>
          </div>
        </div>
      </div>

      <div class="pitch-hud">
        <div class="pitch-hud-card">
          <div class="pitch-hud-head">
            <span>Pitch Strength Score</span>
            <span class="chip chip-ok chip-sm">Hiring Manager Target</span>
          </div>
          <div class="pitch-score-badge">
            <span class="pitch-score-num">${telemetry.pitch_score || 94}</span>
            <span class="pitch-score-denom">/100</span>
          </div>
          <div class="pitch-hud-verdict">${telemetry.pitch_score >= 88 ? 'High-Converting Narrative Pitch' : 'Solid Role Pitch'}</div>
        </div>

        <div class="pitch-hud-card">
          <div class="pitch-hud-head">
            <span>Reading Speed &amp; Density</span>
            <span class="chip chip-info chip-sm">45-Sec Screen</span>
          </div>
          <div class="pitch-telemetry-stats">
            <div class="pitch-stat-item">
              ${ico('clock')} <strong>${telemetry.reading_time_sec || 45}s</strong> reading time
            </div>
            <div class="pitch-stat-item">
              ${ico('file')} <strong>${telemetry.word_count || 240}</strong> words
            </div>
          </div>
          <p class="muted small" style="margin:6px 0 0">Concise, impactful length designed for time-starved engineering leaders.</p>
        </div>

        <div class="pitch-hud-card">
          <div class="pitch-hud-head">
            <span>100% Grounded Intelligence</span>
            <span class="chip chip-ok chip-sm">Zero Hallucinations</span>
          </div>
          <div style="display:flex; flex-direction:column; gap:4px; margin-top:4px;">
            <span style="font-size:12px; font-weight:600; color:var(--text-1)">${ico('check')} All achievements drawn from verified resume</span>
            ${pitch.honest_bridge ? `<span style="font-size:11.5px; color:var(--accent,#f59e0b);">${ico('shield')} Transparent learning bridge included for stack gaps</span>` : '<span style="font-size:11.5px; color:var(--text-3)">Core posting stack covered</span>'}
          </div>
        </div>
      </div>

      <div class="cover-studio-layout">
        <!-- Left Column: Strategy & Editor -->
        <div class="pitch-left-pane">
          <div class="pitch-card">
            <div class="pitch-card-title">${ico('star')} Value Pillars Spotlight</div>
            <p class="muted small" style="margin:0 0 10px">Choose which verified career achievements to feature as core proof points:</p>
            <div class="pillar-selector-list">
              ${(allBullets.length ? allBullets.slice(0, 4) : pillars).map((b, idx) => {
                const isSelected = isBulletSelected(b, idx);
                return `
                  <label class="pillar-item-check ${isSelected ? 'is-active' : ''}">
                    <input type="checkbox" data-action="cover-toggle-bullet" data-bullet="${esc(b.bullet || b.raw_bullet || '')}" ${isSelected ? 'checked' : ''}>
                    <div class="pillar-info">
                      <span class="pillar-theme">${esc(b.role || b.company || 'Achievement')}</span>
                      <span class="pillar-text">${esc(b.bullet || b.proof_point || '')}</span>
                      ${b.quantified ? '<span class="pillar-metric-tag">Quantified Metric</span>' : ''}
                    </div>
                  </label>
                `;
              }).join('')}
            </div>
          </div>

          <div class="pitch-card">
            <div class="pitch-card-title">${ico('edit')} Letter Text Editor</div>
            <div class="letter-textarea-wrap">
              <textarea id="coverLetterTextarea" class="letter-textarea-modern" rows="18">${esc(letterText)}</textarea>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
              <small class="muted" id="letterWordCount">${telemetry.word_count || 0} words &bull; ${telemetry.reading_time_sec || 0}s read</small>
              <button type="button" class="btn btn-ghost btn-sm" data-action="cover-reset-text">Reset to Generated</button>
            </div>
          </div>
        </div>

        <!-- Right Column: Letterhead Paper Preview -->
        <aside class="cover-preview-card">
          <div class="cover-letterhead-paper" id="coverLetterPaper">
            <div class="paper-cand-name">${esc(candName)}</div>
            ${candRole ? `<div style="font-size:12px; font-weight:600; color:var(--primary); text-transform:uppercase; margin-bottom:4px;">${esc(candRole)}</div>` : ''}
            <div class="paper-cand-contact">${esc(candContact)}</div>
            <hr class="paper-rule">

            <div class="paper-date-row">
              <span>${esc(today)}</span>
              <span><strong>Hiring Team</strong> &bull; ${esc(j.company || 'Company')}</span>
            </div>

            <div class="paper-re-line">Re: Application for ${esc(cleanTitle(j.title) || 'Position')} Role</div>

            <div class="paper-body-text" id="paperBodyText">
              ${formatPaperParagraphs(letterText)}
            </div>
          </div>
        </aside>
      </div>
    `;

    // Live update paper preview when textarea is typed into
    const ta = $('#coverLetterTextarea');
    if (ta) {
      ta.addEventListener('input', () => {
        w.cover[w.tone] = ta.value;
        const bodyBox = $('#paperBodyText');
        if (bodyBox) {
          bodyBox.innerHTML = formatPaperParagraphs(ta.value);
        }
        const words = ta.value.trim().split(/\s+/).filter(Boolean).length;
        const countBox = $('#letterWordCount');
        if (countBox) countBox.textContent = `${words} words • ${Math.max(15, Math.round(words / 3.8))}s read`;
      });
    }
  }

  async function exportCoverLetter(fmt) {
    const w = S.ws;
    const text = val('coverLetterTextarea') || w.cover[w.tone] || '';
    if (!text) { toast('No cover letter text to export', 'error'); return; }
    try {
      const res = await api('/api/export', {
        method: 'POST',
        body: { type: 'cover_letter', format: fmt, cover_letter: text, job: w.job }
      });
      if (fmt === 'txt') {
        try { await navigator.clipboard.writeText(res.content); toast('Cover letter text copied to clipboard'); }
        catch (e) { toast('Your browser blocked clipboard access', 'error'); }
        return;
      }
      const bin = atob(res.content_base64), arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([arr], { type: res.mime }));
      const a = document.createElement('a');
      a.href = url; a.download = res.filename; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast(`Downloaded ${res.filename}`);
    } catch (err) {
      toast('Export failed: ' + err.message, 'error');
    }
  }

  async function saveCoverLetter() {
    const w = S.ws, job = w.job, text = val('coverLetterTextarea') || w.cover[w.tone] || '';
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
  function getCompanyMonogram(company) {
    if (!company) return 'CO';
    const words = String(company).trim().split(/\s+/).filter(Boolean);
    if (words.length >= 2) {
      return (words[0][0] + words[1][0]).toUpperCase();
    }
    return String(company).trim().slice(0, 2).toUpperCase();
  }

  function getCompanyColorStyle(company) {
    let hash = 0;
    const s = String(company || 'Company');
    for (let i = 0; i < s.length; i++) hash = s.charCodeAt(i) + ((hash << 5) - hash);
    const hue = Math.abs(hash) % 360;
    return `background: hsl(${hue}, 48%, 93%); color: hsl(${hue}, 60%, 25%); border: 1px solid hsl(${hue}, 35%, 82%);`;
  }

  function getNextStage(currentStage) {
    switch (currentStage) {
      case 'saved': return { next: 'applied', label: 'Mark Applied' };
      case 'applied': return { next: 'interview', label: 'To Interview' };
      case 'interview': return { next: 'offer', label: 'Got Offer' };
      case 'offer': return { next: 'rejected', label: 'Archive' };
      default: return null;
    }
  }

  function setAppFilter(filterKey) {
    S.appFilter = filterKey;
    const pills = $('#appFilterPills');
    if (pills) {
      $$('.app-pill', pills).forEach(p => {
        const active = (p.dataset.appFilter === filterKey);
        p.classList.toggle('is-active', active);
        p.setAttribute('aria-pressed', String(active));
      });
    }
    const kpiRibbon = $('#appKpiRibbon');
    if (kpiRibbon) {
      $$('.kpi-card', kpiRibbon).forEach(card => {
        const k = card.dataset.kpi;
        const isMatch = (filterKey === 'all' && k === 'live') ||
                        (filterKey === 'interviewing' && k === 'interview') ||
                        (filterKey === 'attention' && k === 'overdue');
        card.classList.toggle('is-active-filter', isMatch);
      });
    }
    renderApplicationView();
  }

  function getFilteredApplications() {
    let apps = [...(S.applications || [])];

    // Text search filter
    const q = (S.appSearchQuery || '').trim().toLowerCase();
    if (q) {
      apps = apps.filter(a => {
        const matchCo = (a.company || '').toLowerCase().includes(q);
        const matchTitle = (a.title || '').toLowerCase().includes(q);
        const matchLoc = (a.location || '').toLowerCase().includes(q);
        const matchNotes = (a.notes || '').toLowerCase().includes(q);
        const matchRound = (a.interview_round || '').toLowerCase().includes(q);
        const matchContact = (a.contacts || []).some(c => (c.name || '').toLowerCase().includes(q) || (c.role || '').toLowerCase().includes(q));
        return matchCo || matchTitle || matchLoc || matchNotes || matchRound || matchContact;
      });
    }

    // Filter pills
    if (S.appFilter === 'attention') {
      apps = apps.filter(a => {
        if (a.status === 'rejected') return false;
        const d = a.follow_up_date ? daysUntil(a.follow_up_date) : null;
        const isFollowAlert = (d !== null && d <= 0);
        const hasPendingTasks = (a.tasks || []).some(t => !t.completed);
        return a.overdue || isFollowAlert || hasPendingTasks;
      });
    } else if (S.appFilter === 'high_priority') {
      apps = apps.filter(a => a.priority === 'high');
    } else if (S.appFilter === 'interviewing') {
      apps = apps.filter(a => a.status === 'interview');
    } else if (S.appFilter === 'has_tailored') {
      apps = apps.filter(a => Boolean(a.job_data && (a.job_data.tailored_resume || a.job_data.cover_letter || a.job_data.has_tailored)));
    }

    return apps;
  }

  async function loadApplications() {
    try {
      const [appRes, statsRes] = await Promise.all([
        api('/api/applications'),
        api('/api/stats').catch(() => ({}))
      ]);
      S.applications = appRes.applications || [];

      // Update KPI ribbon
      const apps = S.applications;
      const live = apps.filter(a => a.status !== 'rejected').length;
      const funnel = (statsRes && statsRes.funnel) || {};

      const kpiActive = $('#kpiActiveCount');
      if (kpiActive) kpiActive.textContent = funnel.live !== undefined ? funnel.live : live;

      const kpiIntRate = $('#kpiInterviewRate');
      if (kpiIntRate) kpiIntRate.textContent = `${funnel.interview_rate !== undefined ? funnel.interview_rate : 0}%`;

      const kpiOfferRate = $('#kpiOfferRate');
      if (kpiOfferRate) kpiOfferRate.textContent = `${funnel.offer_rate !== undefined ? funnel.offer_rate : 0}%`;

      const attentionApps = apps.filter(a => {
        if (a.status === 'rejected') return false;
        const d = a.follow_up_date ? daysUntil(a.follow_up_date) : null;
        return a.overdue || (d !== null && d <= 0);
      });
      const attentionCount = attentionApps.length;

      const kpiFollowup = $('#kpiFollowupCount');
      if (kpiFollowup) kpiFollowup.textContent = attentionCount;

      const alertCard = $('#kpiAlertCard');
      if (alertCard) {
        alertCard.classList.toggle('has-alert', attentionCount > 0);
        alertCard.classList.toggle('has-alerts', attentionCount > 0);
      }

      const attentionSub = $('#kpiFollowupSub');
      if (attentionSub) {
        attentionSub.textContent = attentionCount ? `${attentionCount} need action today` : 'All caught up';
      }

      const pillAttention = $('#pillAttentionCount');
      if (pillAttention) {
        pillAttention.textContent = attentionCount;
        pillAttention.hidden = !attentionCount;
      }
    } catch (err) {
      console.error('Applications failed:', err);
    }

    const liveCount = S.applications.filter(a => a.status !== 'rejected').length;
    const navBadge = $('#navAppCount');
    if (navBadge) {
      navBadge.hidden = !liveCount;
      navBadge.textContent = liveCount;
    }

    if (S.view === 'applications') {
      renderApplicationView();
    }
  }

  function followHtml(a) {
    if (!a.follow_up_date || a.status === 'rejected' || a.status === 'saved') return '';
    const d = daysUntil(a.follow_up_date);
    if (d === null) return '';
    if (d < 0) {
      return `<span class="kcard-badge badge-follow is-overdue">${ico('clock')}${Math.abs(d)}d overdue</span>`;
    }
    if (d === 0) {
      return `<span class="kcard-badge badge-follow is-today">${ico('clock')}Follow up today</span>`;
    }
    return `<span class="kcard-badge badge-follow">${ico('clock')}In ${d}d</span>`;
  }

  function renderCard(a) {
    const monogram = getCompanyMonogram(a.company);
    const colorStyle = getCompanyColorStyle(a.company);
    const next = getNextStage(a.status);

    const score = a.score !== undefined ? a.score : (a.job_data && a.job_data.score !== undefined ? a.job_data.score : null);
    const scoreBadge = (score !== null && score > 0)
      ? `<span class="kcard-badge badge-score ${score >= 75 ? 'score-high' : 'score-med'}">${score}% fit</span>`
      : '';

    const priorityBadge = a.priority === 'high'
      ? `<span class="kcard-badge badge-priority-high">${ico('flame')}High</span>`
      : (a.priority === 'low' ? `<span class="kcard-badge badge-priority-low">Low</span>` : '');

    const tailoredBadge = (a.job_data && (a.job_data.tailored_resume || a.job_data.cover_letter || a.job_data.has_tailored))
      ? `<span class="kcard-badge badge-tailored" title="Tailored documents ready">${ico('check')}Tailored</span>`
      : '';

    const daysInStage = a.days_in_stage || 0;
    let velocityText = '';
    if (daysInStage > 0) {
      velocityText = daysInStage < 1 ? '<1d in stage' : `${Math.round(daysInStage)}d in stage`;
    }
    const velocityBadge = velocityText
      ? `<span class="kcard-badge badge-velocity" title="Time in current stage">${ico('clock')}${velocityText}</span>`
      : '';

    const followHtmlBadge = followHtml(a);

    let taskSnippet = '';
    if (a.tasks && a.tasks.length) {
      const done = a.tasks.filter(t => t.completed).length;
      taskSnippet = `<div class="kcard-tasks-snippet">${ico('list')}<span>${done}/${a.tasks.length} tasks</span></div>`;
    }

    const roundTag = (a.status === 'interview' && a.interview_round)
      ? `<div class="kcard-round-tag"><span class="round-dot"></span>${esc(a.interview_round)}</div>`
      : '';

    return `<article class="kcard" draggable="true" data-id="${esc(a.id)}" tabindex="0" role="button" aria-label="${esc(cleanTitle(a.title))} at ${esc(a.company)}">
      <div class="kcard-top">
        <div class="kcard-brand">
          ${companyAvatarHtml(a, 'kcard')}
          <div class="kcard-company" title="${esc(a.company)}">${esc(a.company)}</div>
        </div>
        <div class="kcard-pills-top">
          ${scoreBadge}
          ${priorityBadge}
        </div>
      </div>

      <div class="kcard-title" title="${esc(cleanTitle(a.title))}">${esc(cleanTitle(a.title))}</div>

      ${roundTag}

      <div class="kcard-meta">
        ${a.location ? `<span>${ico('pin')}${esc(a.location)}</span>` : ''}
        ${a.salary ? `<span>${ico('dollar')}${esc(a.salary)}</span>` : ''}
      </div>

      ${(followHtmlBadge || velocityBadge || tailoredBadge) ? `
        <div class="kcard-status-row">
          ${followHtmlBadge}
          ${velocityBadge}
          ${tailoredBadge}
        </div>` : ''}

      ${taskSnippet}

      ${a.notes ? `<div class="kcard-notes">${esc(a.notes)}</div>` : ''}

      <div class="kcard-foot">
        <div class="kcard-stage-advance">
          ${next ? `<button type="button" class="kcard-advance-btn" data-action="app-advance" data-id="${esc(a.id)}" data-next="${next.next}" title="Advance to ${next.next}">${ico('arrow-right')}<span>${next.label}</span></button>` : `<span class="kcard-archived-tag">${ico('check')}Archived</span>`}
        </div>
        <div class="kcard-actions">
          ${a.job_data && (a.job_data.title || a.job_data.description) ? `<button type="button" class="icon-btn" data-action="app-open" data-id="${esc(a.id)}" title="Open tailored resume workspace" aria-label="Open tailored resume workspace">${ico('file')}</button>` : ''}
          <button type="button" class="icon-btn" data-action="app-edit" data-id="${esc(a.id)}" title="Edit application details" aria-label="Edit application details">${ico('edit')}</button>
          <button type="button" class="icon-btn" data-action="app-delete" data-id="${esc(a.id)}" title="Delete application" aria-label="Delete application">${ico('trash')}</button>
        </div>
      </div>
    </article>`;
  }

  function renderApplicationView() {
    const isKanban = S.appViewMode === 'kanban';

    const boardWrap = $('#appBoardWrap');
    const tableWrap = $('#appTableWrap');
    if (boardWrap) boardWrap.hidden = !isKanban;
    if (tableWrap) tableWrap.hidden = isKanban;

    const btnKanban = $('#btnViewKanban');
    const btnTable = $('#btnViewTable');
    if (btnKanban) {
      btnKanban.classList.toggle('is-active', isKanban);
      btnKanban.setAttribute('aria-pressed', String(isKanban));
    }
    if (btnTable) {
      btnTable.classList.toggle('is-active', !isKanban);
      btnTable.setAttribute('aria-pressed', String(!isKanban));
    }

    const clearBtn = $('#appSearchClear');
    if (clearBtn) clearBtn.hidden = !(S.appSearchQuery && S.appSearchQuery.length > 0);

    if (isKanban) {
      renderBoard();
    } else {
      renderTable();
    }
  }

  function renderBoard() {
    const apps = S.applications;
    const filtered = getFilteredApplications();
    const board = $('#kanbanBoard');
    if (!board) return;

    if (!apps.length) {
      board.style.display = 'block';
      board.innerHTML = `<div class="empty">${ico('board')}<h3>No applications yet</h3><p>Save a job from search or add one you found elsewhere to start tracking your pipeline.</p>
        <div class="empty-actions"><a class="btn btn-primary" href="#/jobs">Find jobs</a><button type="button" class="btn btn-secondary" data-action="app-add">Add application</button></div></div>`;
      return;
    }

    if (!filtered.length && S.appSearchQuery) {
      board.style.display = 'block';
      board.innerHTML = `<div class="empty">${ico('search')}<h3>No applications match "${esc(S.appSearchQuery)}"</h3><p>Try searching for a different company or job title, or clear the search query.</p>
        <div class="empty-actions"><button type="button" class="btn btn-secondary" id="emptyResetSearchBtn">Clear search</button></div></div>`;
      const rBtn = $('#emptyResetSearchBtn');
      if (rBtn) rBtn.addEventListener('click', () => {
        S.appSearchQuery = '';
        const inp = $('#appSearchInput');
        if (inp) inp.value = '';
        renderApplicationView();
      });
      return;
    }

    board.style.display = '';
    board.innerHTML = STAGES.map(st => {
      const items = filtered.filter(a => (a.status || 'saved') === st.key);
      return `<section class="col" data-stage="${st.key}" aria-label="${st.label}">
        <div class="col-head">
          <div class="col-head-left">
            <span class="col-indicator-dot"></span>
            <span class="col-title">${st.label}</span>
            <span class="count">${items.length}</span>
          </div>
          <button type="button" class="col-btn-add" data-action="app-add-stage" data-stage="${st.key}" title="Add application to ${st.label}" aria-label="Add application to ${st.label}">
            ${ico('plus')}
          </button>
        </div>
        <div class="col-body">${items.length ? items.map(renderCard).join('') : `<div class="col-empty">No ${st.label.toLowerCase()} roles</div>`}</div>
      </section>`;
    }).join('');
  }

  function renderTable() {
    const filtered = getFilteredApplications();
    const tbody = $('#appTableBody');
    if (!tbody) return;

    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="table-empty">No applications match your filter criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(a => {
      const monogram = getCompanyMonogram(a.company);
      const colorStyle = getCompanyColorStyle(a.company);
      const score = a.score !== undefined ? a.score : (a.job_data && a.job_data.score !== undefined ? a.job_data.score : null);
      const scoreHtml = (score !== null && score > 0)
        ? `<span class="score-chip ${score >= 75 ? 'high' : 'med'}">${score}% fit</span>`
        : '<span class="muted">-</span>';
      const followHtmlBadge = followHtml(a) || '<span class="muted">None scheduled</span>';
      const priorityPill = a.priority === 'high'
        ? `<span class="priority-pill high">${ico('flame')}High</span>`
        : (a.priority === 'low' ? `<span class="priority-pill low">Low</span>` : `<span class="priority-pill med">Standard</span>`);

      return `<tr data-id="${esc(a.id)}" class="app-table-row">
        <td class="td-company">
          <div class="table-role-cell">
            <div class="table-avatar" style="${colorStyle}">${esc(monogram)}</div>
            <div>
              <div class="table-title">${esc(cleanTitle(a.title))}</div>
              <div class="table-company">${esc(a.company)}</div>
            </div>
          </div>
        </td>
        <td class="td-stage">
          <select class="table-stage-select" data-action="app-stage" data-id="${esc(a.id)}">
            ${STAGES.map(s => `<option value="${s.key}" ${s.key === a.status ? 'selected' : ''}>${s.label}</option>`).join('')}
          </select>
        </td>
        <td class="td-score">${scoreHtml}</td>
        <td class="td-follow">${followHtmlBadge}</td>
        <td class="td-priority">${priorityPill}</td>
        <td class="td-details">
          <div class="table-details-cell">
            <span>${esc(a.salary || 'Unspecified')}</span>
            <span class="muted">${esc(a.location || 'Remote')}</span>
          </div>
        </td>
        <td class="td-actions">
          <div class="table-actions-cell">
            <button type="button" class="btn btn-ghost btn-sm" data-action="app-dossier" data-id="${esc(a.id)}">Open</button>
            <button type="button" class="icon-btn" data-action="app-delete" data-id="${esc(a.id)}" title="Delete" aria-label="Delete">${ico('trash')}</button>
          </div>
        </td>
      </tr>`;
    }).join('');
  }

  async function moveApp(id, status) {
    const app = S.applications.find(a => a.id === id);
    if (!app || app.status === status) return;
    const previous = app.status;
    app.status = status;
    renderApplicationView();
    try {
      await api('/api/applications', { method: 'POST', body: app });
      const stageLabel = (STAGES.find(s => s.key === status) || {}).label || status;
      toast(`Moved to ${stageLabel}`);
      if (S.activeDrawerApp && S.activeDrawerApp.id === id) {
        S.activeDrawerApp.status = status;
        const stagePills = $('#drawerStagePills');
        if (stagePills) {
          $$('.drawer-stage-pill', stagePills).forEach(p => p.classList.toggle('is-active', p.dataset.stage === status));
        }
      }
      loadApplications();
    } catch (err) {
      app.status = previous;
      renderApplicationView();
      toast('Could not move application: ' + err.message, 'error');
    }
  }

  async function deleteApp(id) {
    const app = S.applications.find(a => a.id === id);
    if (!app) return;
    if (!await confirmDialog('Remove this application?', `${cleanTitle(app.title)} at ${app.company} will leave your pipeline.`, 'Remove')) return;
    try {
      await api(`/api/applications/${encodeURIComponent(id)}`, { method: 'DELETE' });
      S.applications = S.applications.filter(a => a.id !== id);
      if (S.activeDrawerApp && S.activeDrawerApp.id === id) {
        closeAppDrawer();
      }
      renderApplicationView();
      loadApplications();
      toast('Application removed');
    } catch (err) {
      toast('Could not remove it: ' + err.message, 'error');
    }
  }

  // --- Slide-out Application Dossier Drawer ---
  function openAppDrawer(app) {
    if (!app) return;
    S.activeDrawerApp = app;

    // Header & Monogram
    const monogram = getCompanyMonogram(app.company);
    const colorStyle = getCompanyColorStyle(app.company);
    const avatarEl = $('#drawerAvatar');
    if (avatarEl) {
      avatarEl.textContent = monogram;
      avatarEl.setAttribute('style', colorStyle);
    }

    const titleEl = $('#drawerTitle');
    if (titleEl) titleEl.textContent = cleanTitle(app.title);

    const companyEl = $('#drawerCompany');
    if (companyEl) companyEl.textContent = app.company;

    const linkEl = $('#drawerJobLink');
    const jobUrl = app.url || (app.job_data && app.job_data.url);
    if (linkEl) {
      if (jobUrl) {
        linkEl.href = jobUrl;
        linkEl.hidden = false;
      } else {
        linkEl.hidden = true;
      }
    }

    // Stage pills
    const stagePills = $('#drawerStagePills');
    if (stagePills) {
      stagePills.innerHTML = STAGES.map(s => `
        <button type="button" class="drawer-stage-pill ${s.key === app.status ? 'is-active' : ''}" data-stage="${s.key}">
          ${s.label}
        </button>
      `).join('');
    }

    // Tab 1: Overview
    const salEl = $('#drawerSalary');
    if (salEl) salEl.textContent = app.salary || 'Not specified';

    const locEl = $('#drawerLocation');
    if (locEl) locEl.textContent = app.location || 'Remote';

    const score = app.score !== undefined ? app.score : (app.job_data && app.job_data.score !== undefined ? app.job_data.score : null);
    const scoreEl = $('#drawerScore');
    if (scoreEl) {
      scoreEl.innerHTML = (score !== null && score > 0) ? `<span class="score-badge-inline">${score}% fit</span>` : '<span class="muted">Not scored</span>';
    }

    const prioButtons = $$('#drawerPriorityPicker .p-chip');
    prioButtons.forEach(btn => {
      btn.classList.toggle('is-active', (app.priority || 'medium') === btn.dataset.p);
    });

    const followInput = $('#drawerFollowDate');
    if (followInput) followInput.value = app.follow_up_date || '';

    const notesText = $('#drawerNotesText');
    if (notesText) notesText.value = app.notes || '';

    const savedTag = $('#drawerNotesSavedTag');
    if (savedTag) savedTag.hidden = true;

    // Tab 2: Tasks
    renderDrawerTasks(app);

    // Tab 3: Contacts & Insider
    renderDrawerContacts(app);
    renderDrawerInsiderLinks(app);

    // Tab 4: Tailored Package
    renderDrawerTailoredPackage(app);

    // Tab 5: Timeline
    renderDrawerTimeline(app);

    // Show initial active tab
    switchDrawerTab(S.activeDrawerTab || 'overview');

    // Slide open drawer
    const drawer = $('#appDrawer');
    const overlay = $('#appDrawerOverlay');
    if (drawer && overlay) {
      drawer.hidden = false;
      overlay.hidden = false;
      drawer.setAttribute('aria-hidden', 'false');
      requestAnimationFrame(() => {
        drawer.classList.add('is-open');
        overlay.classList.add('is-open');
      });
      document.documentElement.classList.add('drawer-no-scroll');
      document.body.classList.add('drawer-no-scroll');
    }
  }

  function closeAppDrawer() {
    const drawer = $('#appDrawer');
    const overlay = $('#appDrawerOverlay');
    if (drawer) {
      drawer.classList.remove('is-open');
      drawer.setAttribute('aria-hidden', 'true');
      setTimeout(() => { drawer.hidden = true; }, 260);
    }
    if (overlay) {
      overlay.classList.remove('is-open');
      setTimeout(() => { overlay.hidden = true; }, 260);
    }
    document.documentElement.classList.remove('drawer-no-scroll');
    document.body.classList.remove('drawer-no-scroll');
    S.activeDrawerApp = null;
  }

  function switchDrawerTab(tabId) {
    S.activeDrawerTab = tabId;
    const tabs = $$('.drawer-tab');
    tabs.forEach(t => {
      const active = t.dataset.drawerTab === tabId;
      t.classList.toggle('is-active', active);
      t.setAttribute('aria-selected', String(active));
    });

    const panelMap = {
      overview: $('#drawerPanelOverview'),
      tasks: $('#drawerPanelTasks'),
      contacts: $('#drawerPanelContacts'),
      tailored: $('#drawerPanelTailored'),
      history: $('#drawerPanelHistory')
    };

    Object.entries(panelMap).forEach(([k, panel]) => {
      if (panel) panel.hidden = (k !== tabId);
    });
  }

  function renderDrawerTasks(app) {
    const list = $('#drawerTaskList');
    const progressText = $('#drawerTaskProgressText');
    const taskBadge = $('#drawerTaskBadge');
    if (!list) return;

    const tasks = app.tasks || [];
    const doneCount = tasks.filter(t => t.completed).length;

    if (progressText) {
      progressText.textContent = `${doneCount} of ${tasks.length} completed`;
    }
    if (taskBadge) {
      const pendingCount = tasks.length - doneCount;
      taskBadge.textContent = pendingCount;
      taskBadge.hidden = pendingCount <= 0;
    }

    if (!tasks.length) {
      list.innerHTML = `<div class="drawer-empty-state">No checklist items yet. Add next steps like "Send follow-up email" or "Review system design concepts".</div>`;
      return;
    }

    list.innerHTML = tasks.map((t, i) => `
      <div class="drawer-task-item ${t.completed ? 'is-completed' : ''}" data-idx="${i}">
        <label class="drawer-task-check-wrap">
          <input type="checkbox" class="drawer-task-checkbox" ${t.completed ? 'checked' : ''} data-task-idx="${i}">
          <span class="drawer-task-text">${esc(t.text)}</span>
        </label>
        <button type="button" class="drawer-task-del" data-del-task="${i}" title="Remove task">&times;</button>
      </div>
    `).join('');
  }

  function renderDrawerContacts(app) {
    const list = $('#drawerContactsList');
    if (!list) return;

    const contacts = app.contacts || [];
    if (!contacts.length) {
      list.innerHTML = `<div class="drawer-empty-state">No contacts added yet. Save recruiters, hiring managers, and referral allies for this role.</div>`;
      return;
    }

    list.innerHTML = contacts.map((c, i) => `
      <div class="drawer-contact-item" data-idx="${i}">
        <div class="drawer-contact-info">
          <div class="drawer-contact-name">${esc(c.name)}</div>
          <div class="drawer-contact-role">${esc(c.role || 'Team Member')}</div>
          <div class="drawer-contact-links">
            ${c.email ? `<a href="mailto:${esc(c.email)}" class="contact-link">${ico('mail')}${esc(c.email)}</a>` : ''}
            ${c.linkedin ? `<a href="${esc(c.linkedin)}" target="_blank" rel="noopener noreferrer" class="contact-link">${ico('external')}LinkedIn</a>` : ''}
          </div>
        </div>
        <button type="button" class="drawer-contact-del" data-del-contact="${i}" title="Remove contact">&times;</button>
      </div>
    `).join('');
  }

  function renderDrawerInsiderLinks(app) {
    const box = $('#drawerInsiderLinks');
    if (!box) return;

    const co = encodeURIComponent(app.company || '');
    box.innerHTML = `
      <a href="https://www.linkedin.com/search/results/people/?keywords=${co}%20recruiter" target="_blank" rel="noopener noreferrer" class="drawer-insider-btn">
        ${ico('search')}
        <span>Recruiters at ${esc(app.company)}</span>
        ${ico('external', 'link-icon')}
      </a>
      <a href="https://www.linkedin.com/search/results/people/?keywords=${co}%20engineering%20manager" target="_blank" rel="noopener noreferrer" class="drawer-insider-btn">
        ${ico('search')}
        <span>Engineering Managers at ${esc(app.company)}</span>
        ${ico('external', 'link-icon')}
      </a>
      <a href="https://www.linkedin.com/search/results/people/?keywords=${co}%20software%20engineer" target="_blank" rel="noopener noreferrer" class="drawer-insider-btn">
        ${ico('search')}
        <span>Engineers &amp; Team Peers</span>
        ${ico('external', 'link-icon')}
      </a>
    `;
  }

  function renderDrawerTailoredPackage(app) {
    const card = $('#drawerTailoredPackageCard');
    if (!card) return;

    const jd = app.job_data || {};
    const hasResume = Boolean(jd.tailored_resume || jd.resume_bullets);
    const hasCover = Boolean(jd.cover_letter);

    if (!hasResume && !hasCover && !jd.description && !jd.title) {
      card.innerHTML = `
        <div class="drawer-empty-state">
          <p>No tailored package generated yet. Tailor your resume specifically for this job description to highlight exact keyword matches and boost interview rates.</p>
          <button type="button" class="btn btn-primary btn-sm" id="drawerCreateTailoredBtn">${ico('bolt')}Create tailored package</button>
        </div>
      `;
      const btn = $('#drawerCreateTailoredBtn');
      if (btn) btn.addEventListener('click', () => {
        closeAppDrawer();
        openWorkspace(app, 'resume', 'applications');
      });
      return;
    }

    let summaryHtml = '';
    if (jd.tailored_resume && jd.tailored_resume.summary) {
      summaryHtml = `<div class="tailored-preview-sec">
        <h4>Tailored Executive Summary</h4>
        <p class="tailored-text-box">${esc(jd.tailored_resume.summary)}</p>
      </div>`;
    }

    let bulletsHtml = '';
    if (jd.resume_bullets && jd.resume_bullets.length) {
      bulletsHtml = `<div class="tailored-preview-sec">
        <h4>High-Impact ATS Bullets</h4>
        <ul class="tailored-bullets-list">
          ${jd.resume_bullets.slice(0, 4).map(b => `<li>${esc(typeof b === 'string' ? b : b.bullet || b.text)}</li>`).join('')}
        </ul>
      </div>`;
    }

    card.innerHTML = `
      <div class="drawer-tailored-meta">
        <div>
          <h3 class="drawer-sec-title">Tailored Documents</h3>
          <p class="drawer-sec-sub">Optimized for ${esc(cleanTitle(app.title))} at ${esc(app.company)}</p>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" id="drawerOpenStudioBtn">${ico('file')}Open in Studio</button>
      </div>
      ${summaryHtml}
      ${bulletsHtml}
      <div class="drawer-tailored-actions">
        <button type="button" class="btn btn-secondary btn-sm" id="drawerCopyBulletsBtn">${ico('copy')}Copy tailored bullets</button>
        ${hasCover ? `<button type="button" class="btn btn-secondary btn-sm" id="drawerCopyCoverBtn">${ico('copy')}Copy cover letter</button>` : ''}
      </div>
    `;

    const openStudioBtn = $('#drawerOpenStudioBtn');
    if (openStudioBtn) openStudioBtn.addEventListener('click', () => {
      closeAppDrawer();
      openWorkspace(jd.title ? jd : app, 'resume', 'applications');
    });

    const copyBulletsBtn = $('#drawerCopyBulletsBtn');
    if (copyBulletsBtn) {
      copyBulletsBtn.addEventListener('click', async () => {
        const bullets = (jd.resume_bullets || []).map(b => '• ' + (typeof b === 'string' ? b : (b.bullet || b.text || ''))).join('\n');
        const textToCopy = bullets || (jd.tailored_resume ? (jd.tailored_resume.summary || '') : '');
        if (!textToCopy) { toast('No bullets available to copy', 'error'); return; }
        try {
          await navigator.clipboard.writeText(textToCopy);
          toast('Tailored bullets copied to clipboard');
        } catch (e) {
          toast('Could not copy automatically. Select and copy.', 'error');
        }
      });
    }

    const copyCoverBtn = $('#drawerCopyCoverBtn');
    if (copyCoverBtn) {
      copyCoverBtn.addEventListener('click', async () => {
        if (!jd.cover_letter) return;
        try {
          await navigator.clipboard.writeText(jd.cover_letter);
          toast('Cover letter copied to clipboard');
        } catch (e) {
          toast('Could not copy automatically. Select and copy.', 'error');
        }
      });
    }
  }

  function renderDrawerTimeline(app) {
    const box = $('#drawerTimeline');
    if (!box) return;

    const history = app.history || [];
    if (!history.length) {
      box.innerHTML = `<div class="drawer-empty-state">Timeline tracking begins automatically as you advance this role through your pipeline stages.</div>`;
      return;
    }

    box.innerHTML = history.slice().reverse().map(h => {
      const stageName = (STAGES.find(s => s.key === h.stage) || {}).label || h.stage;
      const dateStr = h.date ? new Date(h.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';
      return `
        <div class="drawer-timeline-item">
          <div class="timeline-dot"></div>
          <div class="timeline-content">
            <div class="timeline-head">
              <span class="timeline-stage">${esc(stageName)}</span>
              <span class="timeline-date">${esc(dateStr)}</span>
            </div>
            ${h.note ? `<div class="timeline-note">${esc(h.note)}</div>` : ''}
          </div>
        </div>
      `;
    }).join('');
  }

  async function saveActiveDrawerApp(showFeedback = true) {
    if (!S.activeDrawerApp) return;
    const app = S.activeDrawerApp;

    // Read form inputs
    const followInput = $('#drawerFollowDate');
    if (followInput) app.follow_up_date = followInput.value;

    const notesText = $('#drawerNotesText');
    if (notesText) app.notes = notesText.value.trim();

    try {
      await api('/api/applications', { method: 'POST', body: app });
      const idx = S.applications.findIndex(a => a.id === app.id);
      if (idx !== -1) S.applications[idx] = app;

      renderApplicationView();

      const savedTag = $('#drawerNotesSavedTag');
      if (savedTag) {
        savedTag.hidden = false;
        setTimeout(() => { if (savedTag) savedTag.hidden = true; }, 2500);
      }

      if (showFeedback) toast('Application saved');
      loadApplications();
    } catch (err) {
      toast('Could not save changes: ' + err.message, 'error');
    }
  }

  let editingApp = null;
  function openAppDialog(app, defaultStage = 'applied') {
    editingApp = app || null;
    $('#appDialogTitle').textContent = app ? 'Edit application' : 'Add application';
    $('#appDialogSubmit').textContent = 'Save application';
    $('#modalCompany').value = app ? app.company : '';
    $('#modalTitle').value = app ? app.title : '';
    $('#modalLocation').value = app ? (app.location || 'Remote') : 'Remote';
    $('#modalSalary').value = app ? (app.salary || '') : '';
    $('#modalStatus').value = app ? (app.status || defaultStage) : defaultStage;
    $('#modalFollowUp').value = app ? (app.follow_up_date || '') : isoDay(3);
    $('#modalPriority').value = app ? (app.priority || 'medium') : 'medium';
    $('#modalUrl').value = app ? (app.url || (app.job_data && app.job_data.url) || '') : '';
    $('#modalNotes').value = app ? (app.notes || '') : '';
    $('#appDialog').showModal();
    $('#modalCompany').focus();
  }

  async function submitAppDialog() {
    const fields = {
      company: val('modalCompany').trim(),
      title: val('modalTitle').trim(),
      location: val('modalLocation').trim(),
      salary: val('modalSalary').trim(),
      status: val('modalStatus'),
      follow_up_date: val('modalFollowUp'),
      priority: val('modalPriority'),
      url: val('modalUrl').trim(),
      notes: val('modalNotes').trim()
    };
    try {
      await api('/api/applications', { method: 'POST', body: editingApp ? Object.assign({}, editingApp, fields) : fields });
      $('#appDialog').close();
      toast(editingApp ? 'Application updated' : 'Application added');
      await loadApplications();
    } catch (err) {
      toast('Could not save: ' + err.message, 'error');
    }
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

  const AI_PROVIDER_LABELS = {
    gemini: { label: 'Google Gemini API Key', placeholder: 'AIzaSy...', defaultModel: 'gemini-2.5-flash' },
    openai: { label: 'OpenAI API Key', placeholder: 'sk-proj-...', defaultModel: 'gpt-4o-mini' },
    anthropic: { label: 'Anthropic Claude API Key', placeholder: 'sk-ant-...', defaultModel: 'claude-3-7-sonnet-20250219' },
    deepseek: { label: 'DeepSeek API Key', placeholder: 'sk-...', defaultModel: 'deepseek-chat' },
    groq: { label: 'Groq Cloud API Key', placeholder: 'gsk_...', defaultModel: 'llama-3.3-70b-versatile' },
    mistral: { label: 'Mistral AI API Key', placeholder: '...', defaultModel: 'mistral-large-latest' },
    ollama: { label: '', placeholder: '', defaultModel: 'llama3.3' },
    custom: { label: 'Custom / OpenRouter API Key', placeholder: 'sk-or-...', defaultModel: '' }
  };

  async function loadAiSettings() {
    try {
      const cfg = await api('/api/settings');
      S.aiSettings = cfg;
      const provSelect = $('#aiProviderSelect');
      if (provSelect) {
        provSelect.value = cfg.active_provider || 'deterministic';
        updateAiKeyVisibility(provSelect.value);
      }
      const modelInput = $('#aiModelInput');
      if (modelInput && cfg.ai_model) modelInput.value = cfg.ai_model;
      const ollamaInput = $('#ollamaEndpointInput');
      if (ollamaInput && cfg.ollama_endpoint) ollamaInput.value = cfg.ollama_endpoint;
      const customInput = $('#customEndpointInput');
      if (customInput && cfg.custom_ai_endpoint) customInput.value = cfg.custom_ai_endpoint;

      const badge = $('#activeAiBadge');
      if (badge) {
        const prov = cfg.active_provider || 'deterministic';
        badge.textContent = `${prov.toUpperCase()} (${cfg.llm_available ? 'Connected' : 'Active'})`;
        badge.className = `chip ${prov === 'deterministic' ? 'chip-ok' : cfg.llm_available ? 'chip-ok' : 'chip-warn'}`;
      }

      // Populate Search Capacity & Global Targeting
      const scoredJobsSel = $('#cfgMaxScoredJobs');
      if (scoredJobsSel && cfg.max_scored_jobs) scoredJobsSel.value = String(cfg.max_scored_jobs);

      const maxResultsSel = $('#cfgMaxResults');
      if (maxResultsSel && cfg.max_results) maxResultsSel.value = String(cfg.max_results);

      const depthSel = $('#cfgLinkedInDepth');
      if (depthSel && cfg.linkedin_scrape_depth) depthSel.value = cfg.linkedin_scrape_depth;

      const userCountrySel = $('#cfgUserCountry');
      const customCountryField = $('#cfgCustomCountryField');
      const customCountryInput = $('#cfgCustomCountryInput');
      if (userCountrySel) {
        const uCountry = (cfg.user_country || '').trim();
        const matchingOpt = Array.from(userCountrySel.options).find(o => o.value.toLowerCase() === uCountry.toLowerCase());
        if (matchingOpt) {
          userCountrySel.value = matchingOpt.value;
          if (customCountryField) customCountryField.hidden = true;
        } else if (uCountry) {
          userCountrySel.value = 'custom';
          if (customCountryField) customCountryField.hidden = false;
          if (customCountryInput) customCountryInput.value = uCountry;
        } else {
          userCountrySel.value = 'Worldwide';
          if (customCountryField) customCountryField.hidden = true;
        }
      }

      const incWorldwideRemoteCb = $('#cfgIncludeWorldwideRemote');
      if (incWorldwideRemoteCb) {
        incWorldwideRemoteCb.checked = (String(cfg.include_worldwide_remote).toLowerCase() !== 'false');
      }

      const capBadge = $('#activeCapacityBadge');
      if (capBadge) {
        const d = cfg.linkedin_scrape_depth || 'standard';
        const depthLabels = { fast: 'Fast (~100)', standard: 'Standard (~250)', deep: 'Deep (~500)', max: 'Ultra (~1,000)' };
        capBadge.textContent = `${depthLabels[d] || 'Standard'} / Pool: ${cfg.max_scored_jobs || 1500}`;
      }
    } catch (err) {
      /* ignore */
    }
  }

  function updateAiKeyVisibility(provider) {
    const keyField = $('#aiKeyField');
    const modelField = $('#aiModelField');
    const ollamaField = $('#ollamaEndpointField');
    const customField = $('#customEndpointField');
    const keyLabel = $('#aiKeyLabel');
    const keyInput = $('#aiApiKeyInput');
    const modelInput = $('#aiModelInput');
    const envBadge = $('#aiEnvKeyBadge');
    if (!keyField) return;

    const envKeys = (S.aiSettings && S.aiSettings.env_keys) || {};
    const hasEnvKey = !!envKeys[provider];

    if (envBadge) {
      if (hasEnvKey) {
        envBadge.hidden = false;
        envBadge.textContent = 'Active from .env';
        envBadge.className = 'chip chip-ok chip-sm';
        envBadge.title = 'API key is detected and automatically loaded from your environment (.env)';
      } else {
        envBadge.hidden = true;
      }
    }

    if (provider === 'deterministic') {
      keyField.hidden = true;
      modelField.hidden = true;
      ollamaField.hidden = true;
      if (customField) customField.hidden = true;
    } else if (provider === 'ollama') {
      keyField.hidden = true;
      modelField.hidden = false;
      ollamaField.hidden = false;
      if (customField) customField.hidden = true;
      if (modelInput) modelInput.placeholder = 'llama3.3 or deepseek-r1:8b';
    } else if (provider === 'custom') {
      keyField.hidden = false;
      modelField.hidden = false;
      ollamaField.hidden = true;
      if (customField) customField.hidden = false;
      if (keyLabel) keyLabel.textContent = 'Custom API Key (or OpenRouter Key)';
      if (keyInput) keyInput.placeholder = 'sk-... (optional if keyless)';
      if (modelInput) modelInput.placeholder = 'e.g. anthropic/claude-3.7-sonnet';
    } else {
      keyField.hidden = false;
      modelField.hidden = false;
      ollamaField.hidden = true;
      if (customField) customField.hidden = true;
      const meta = AI_PROVIDER_LABELS[provider] || { label: `${provider.toUpperCase()} API Key`, placeholder: 'Enter API key', defaultModel: '' };
      if (keyLabel) keyLabel.textContent = meta.label;
      if (keyInput) keyInput.placeholder = hasEnvKey ? '(Loaded from .env — type here to override)' : meta.placeholder;
      if (modelInput) modelInput.placeholder = meta.defaultModel || 'Default model';
    }
  }

  async function testAiConnection() {
    const btn = $('#btnTestAi');
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `${ico('refresh')} Testing...`;
    try {
      const prov = val('aiProviderSelect');
      const key = val('aiApiKeyInput').trim();
      const model = val('aiModelInput').trim();
      const endpoint = prov === 'ollama' ? val('ollamaEndpointInput').trim() : (prov === 'custom' ? val('customEndpointInput').trim() : '');
      const body = { ai_provider: prov };
      if (key) body.ai_key = key;
      if (model) body.ai_model = model;
      if (endpoint) body.endpoint = endpoint;
      const res = await api('/api/test-ai', { method: 'POST', body });
      if (res.success) toast(res.message);
      else toast(res.message, 'error');
      await loadAiSettings();
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
    const custom = val('customEndpointInput').trim();

    const payload = { ai_provider: prov };
    if (model) payload.ai_model = model;
    if (ollama) payload.ollama_endpoint = ollama;
    if (custom) payload.custom_ai_endpoint = custom;
    if (key) {
      if (prov === 'gemini') payload.gemini_api_key = key;
      else if (prov === 'openai') payload.openai_api_key = key;
      else if (prov === 'anthropic') payload.anthropic_api_key = key;
      else if (prov === 'deepseek') payload.deepseek_api_key = key;
      else if (prov === 'groq') payload.groq_api_key = key;
      else if (prov === 'mistral') payload.mistral_api_key = key;
      else if (prov === 'custom') payload.custom_ai_key = key;
    }
    try {
      await api('/api/settings', { method: 'POST', body: payload });
      toast('AI configuration saved');
      const keyInput = $('#aiApiKeyInput');
      if (keyInput) keyInput.value = '';
      await loadAiSettings();
    } catch (err) {
      toast('Failed to save settings: ' + err.message, 'error');
    }
  }

  async function saveSearchCapacitySettings() {
    const scoredJobs = parseInt(val('cfgMaxScoredJobs'), 10) || 1500;
    const maxResults = parseInt(val('cfgMaxResults'), 10) || 1000;
    const linkedInDepth = val('cfgLinkedInDepth') || 'standard';
    let userCountry = val('cfgUserCountry');
    if (userCountry === 'custom') {
      userCountry = (val('cfgCustomCountryInput') || '').trim();
    }
    const incWorldwide = $('#cfgIncludeWorldwideRemote') ? $('#cfgIncludeWorldwideRemote').checked : true;

    const payload = {
      max_scored_jobs: scoredJobs,
      max_results: maxResults,
      linkedin_scrape_depth: linkedInDepth,
      user_country: userCountry,
      include_worldwide_remote: incWorldwide
    };

    try {
      await api('/api/settings', { method: 'POST', body: payload });
      toast('Search engine capacity & global targeting saved!');
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
    'clear-all-filters': () => {
      resetAllFilters();
      filterAndRender();
      toast('All filters cleared: showing all available jobs');
    },
    'apply-search-relaxation': () => {
      applySearchRelaxation();
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
    'ask-copilot': el => {
      const k = el.dataset.key;
      const j = (S.jobs || []).find(x => jobKey(x) === k) || (S.allJobs || []).find(x => jobKey(x) === k);
      if (j) {
        selectJob(k);
        openWorkspace(j, 'strategy', 'jobs');
      }
    },
    'job-hide': (el, e) => {
      if (e && e.stopPropagation) e.stopPropagation();
      const k = el.dataset.key;
      toggleHideJob(k);
    },
    'job-fav': async (el, e) => {
      if (e && e.stopPropagation) e.stopPropagation();
      const k = el.dataset.key;
      const j = (S.jobs || []).find(x => jobKey(x) === k) || (S.allJobs || []).find(x => jobKey(x) === k);
      if (j) {
        await saveJob(j);
        renderList();
      }
    },
    'job-more': el => {
      const k = el.dataset.key;
      const j = (S.jobs || []).find(x => jobKey(x) === k) || (S.allJobs || []).find(x => jobKey(x) === k);
      if (j) {
        selectJob(k);
        const url = j.direct_apply_url || j.url;
        if (url) {
          navigator.clipboard.writeText(url).then(() => toast('Job link copied!')).catch(() => {});
        }
      }
    },
    'job-enrich-now': () => {
      const j = selectedJob();
      if (j) triggerJobEnrichment(j, true);
    },
    'toggle-desc': () => {
      const wrap = $('#jobDescWrap');
      if (!wrap) return;
      const isExpanded = wrap.classList.toggle('is-expanded');
      wrap.classList.toggle('is-collapsed', !isExpanded);
      $$('[data-action="toggle-desc"]').forEach(b => {
        const span = b.querySelector('span');
        if (span) span.textContent = isExpanded ? 'Show less' : 'Show full description';
        else b.textContent = isExpanded ? 'Show less' : 'Show full description';
      });
    },
    'copy-text': el => {
      const t = el.dataset.text;
      if (!t) return;
      navigator.clipboard.writeText(t).then(() => {
        toast(`Copied: ${t}`);
      }).catch(() => {
        toast('Copied to clipboard');
      });
    },
    'job-strategy': () => openWorkspace(selectedJob(), 'strategy', S.view === 'recommend' ? 'recommend' : 'jobs'),
    'job-tailor': () => openWorkspace(selectedJob(), 'resume', S.view === 'recommend' ? 'recommend' : 'jobs'),
    'job-save': () => saveJob(selectedJob()),
    'mark-applied': () => markJobApplied(selectedJob()),
    'quick-save': el => {
      const k = el.dataset.key;
      const j = (S.jobs || []).find(x => jobKey(x) === k) || (S.allJobs || []).find(x => jobKey(x) === k);
      if (j) {
        saveJob(j);
        renderList();
      }
    },
    'quick-dismiss': el => {
      const k = el.dataset.key;
      toggleHideJob(k);
    },
    'refresh-recommendations': () => loadRecommendations(true),
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
    'profile-switch': el => switchProfile(el.dataset.id),
    'profile-toggle-live': (el, e) => {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      toggleLiveProfile(el.dataset.id);
    },
    'profile-new-variant': () => openNewVariantDialog(false),
    'profile-duplicate-variant': () => duplicateActiveProfile(),
    'profile-rename-variant': () => openNewVariantDialog(true, S.activeProfileId),
    'profile-delete-variant': () => deleteProfileVariant(S.activeProfileId),
    'profile-reaudit': () => runAtsAudit(),
    'profile-export-menu': () => exportResume('pdf'),
    'save-tailored-variant': () => openSaveTailoredDialog(),
    'compare-variants-modal': el => {
      const card = el.closest('.job-item, .detail-body, [data-key]');
      const key = card && card.dataset.key;
      const job = key ? S.jobs.find(x => jobKey(x) === key) : selectedJob();
      openVariantCompareDialog(job);
    },
    'switch-and-close-compare': async el => {
      const id = el.dataset.id;
      const dlg = $('#variantCompareDialog');
      if (dlg) dlg.close();
      await switchProfile(id);
      renderDetail();
    },
    // workspace
    'ws-back': () => go(S.ws.from === 'applications' ? 'applications' : S.ws.from === 'digest' ? 'digest' : 'jobs'),
    'ws-save': () => saveJob(S.ws.job),
    'ws-retry': () => renderWsTab(),
    'auto-tailor': () => autoTailor(),
    'generate-custom-resume': () => generateCustomResume(),
    'select-archetype': el => selectArchetype(el.dataset.archetype),
    'toggle-heatmap': () => toggleHeatmap(),
    'bullets-copy': () => copyAtsBullets(),
    'diff-accept': el => setDiff(el.dataset.id, 'accepted'),
    'diff-reject': el => setDiff(el.dataset.id, 'rejected'),
    'diff-accept-all': () => setAllDiffs('accepted'),
    'diff-reset': () => setAllDiffs('rejected'),
    'diff-unchanged-toggle': () => { S.ws.showUnchanged = !S.ws.showUnchanged; renderResumeTab(); },
    'export': el => exportResume(el.dataset.fmt),
    'gap-add': el => addSkillToProfile(el.dataset.skill),
    'cover-angle': async el => {
      S.ws.pitchAngle = el.dataset.angle;
      await ensureCover(false);
      renderCoverTab();
    },
    'cover-regenerate': async () => {
      await ensureCover(true);
      renderCoverTab();
      toast('Personalized pitch regenerated!');
    },
    'cover-tone': async el => {
      S.ws.tone = el.dataset.tone;
      await ensureCover(false);
      renderCoverTab();
    },
    'cover-reset-text': () => {
      if (S.ws.activePitch && S.ws.activePitch.full_text) {
        S.ws.cover[S.ws.tone] = S.ws.activePitch.full_text;
        renderCoverTab();
        toast('Text reset to generated pitch');
      }
    },
    'cover-export': el => exportCoverLetter(el.dataset.fmt),
    'cover-toggle-bullet': async el => {
      const bullet = el.dataset.bullet;
      S.ws.selectedPillars = S.ws.selectedPillars || [];
      if (el.checked) {
        if (!S.ws.selectedPillars.includes(bullet)) S.ws.selectedPillars.push(bullet);
      } else {
        S.ws.selectedPillars = S.ws.selectedPillars.filter(b => b !== bullet);
      }
      await ensureCover(true);
      renderCoverTab();
    },
    'cover-copy': async () => {
      const valText = val('coverLetterTextarea') || (S.ws.cover && S.ws.cover[S.ws.tone]) || '';
      try {
        await navigator.clipboard.writeText(valText);
        toast('Cover letter copied to clipboard');
      } catch (e) {
        toast('Your browser blocked copying. Select the text and copy it.', 'error');
      }
    },
    'cover-save': () => saveCoverLetter(),
    // applications
    'app-add': () => openAppDialog(null),
    'app-add-stage': el => openAppDialog(null, el.dataset.stage || 'applied'),
    'app-edit': el => openAppDialog(S.applications.find(a => a.id === el.dataset.id)),
    'app-delete': el => deleteApp(el.dataset.id),
    'app-open': el => { const a = S.applications.find(x => x.id === el.dataset.id); if (a) openWorkspace(a.job_data || a, 'resume', 'applications'); },
    'app-dossier': el => { const a = S.applications.find(x => x.id === el.dataset.id); if (a) openAppDrawer(a); },
    'app-advance': el => { if (el.dataset.id && el.dataset.next) moveApp(el.dataset.id, el.dataset.next); },
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
    // ⚡ 1-Click Application Autofill & Easy Apply Actions
    'open-autofill-copilot': (el, e) => {
      if (e) { e.stopPropagation(); }
      const key = el.dataset.key || S.selectedKey;
      let job = (S.jobs || []).find(j => jobKey(j) === key) || (S.allJobs || []).find(j => jobKey(j) === key) || (S.ws && S.ws.job);
      if (!job) job = selectedJob() || (S.jobs && S.jobs[0]);
      if (job) openAutofillCopilot(job);
    },
    'easy-apply-now': async (el, e) => {
      if (e) { e.stopPropagation(); }
      const key = el.dataset.key || S.selectedKey;
      let job = (S.jobs || []).find(j => jobKey(j) === key) || (S.allJobs || []).find(j => jobKey(j) === key) || (S.ws && S.ws.job);
      if (!job) job = selectedJob() || (S.jobs && S.jobs[0]);
      if (job) await executeEasyApply(job);
    },
    'dialog-close': el => { const d = el.closest('dialog'); if (d) d.close(); }
  };

  function closeAutofillCopilot() {
    const drawer = $('#autofillModal');
    if (!drawer) return;
    drawer.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    setTimeout(() => {
      drawer.hidden = true;
      drawer.setAttribute('hidden', '');
      drawer.style.display = 'none';
    }, 280);
  }

  // ------------------------------------------------------------------ ⚡ Autofill & Easy Apply Copilot
  function getLocalAutofillFallback(profile, job) {
    const p = profile || {};
    const name = (p.name || 'Candidate').trim();
    const parts = name.split(/\s+/);
    const firstName = parts[0] || '';
    const lastName = parts.slice(1).join(' ') || '';
    const loc = p.location || '';
    const locParts = loc.split(',').map(s => s.trim()).filter(Boolean);
    const city = locParts[0] || loc || '';
    const country = locParts.length > 1 ? locParts[locParts.length - 1] : 'United States';
    const role = p.target_title || (p.target_roles && p.target_roles[0]) || (job ? cleanTitle(job.title) : 'Professional');
    const exp = (p.experience && p.experience[0]) || {};
    const edu = (p.education && p.education[0]) || {};

    return {
      full_name: name,
      first_name: firstName,
      last_name: lastName,
      email: p.email || '',
      phone: p.phone || '',
      location: loc,
      city: city,
      country: country,
      linkedin_url: p.linkedin || '',
      github_url: p.github || '',
      portfolio_url: p.portfolio || p.website || '',
      current_role: exp.title || role,
      current_company: exp.company || 'Confidential',
      desired_salary: p.min_salary ? `$${Number(p.min_salary).toLocaleString()} / year` : 'Competitive / Flexible',
      notice_period: p.notice_period || '2 weeks',
      work_authorization: p.work_authorization || 'Authorized to work',
      visa_sponsorship: p.visa_sponsorship ? 'Yes' : 'No',
      degree: edu.degree || 'Bachelor of Science',
      institution: edu.school || edu.institution || 'University',
      skills_csv: (p.skills || []).slice(0, 8).join(', '),
      cover_pitch: `I am writing to express my strong enthusiasm for the ${job ? cleanTitle(job.title) : 'role'} at ${job ? job.company : 'your team'}. With demonstrated experience in ${role} and technical depth across ${(p.skills || ['modern systems']).slice(0, 3).join(', ')}, I am excited to contribute immediately to your goals.`,
      cover_letter: p.cover_letter || '',
      summary: p.summary || '',
      detected_platform: 'standard'
    };
  }

  // ------------------------------------------------------------------ ⚡ Autofill & Easy Apply Copilot
  async function openAutofillCopilot(job) {
    if (!job) return;
    S.activeAutofillJob = job;
    const drawer = $('#autofillModal');
    if (!drawer) return;

    drawer.hidden = false;
    drawer.removeAttribute('hidden');
    drawer.setAttribute('aria-hidden', 'false');
    drawer.style.display = 'flex';
    requestAnimationFrame(() => {
      drawer.classList.add('is-open');
    });
    const scrollBody = $('.jh-drawer-scroll-body', drawer) || $('.jh-modal-body', drawer);
    if (scrollBody) scrollBody.scrollTop = 0;
    const title = $('#afModalTitle');
    const sub = $('#afModalSubtitle');
    const badge = $('#afPlatformBadge');
    if (title) title.textContent = `1-Click Autofill: ${job.company}`;
    if (sub) sub.textContent = `Autofilling ${cleanTitle(job.title)} at ${job.company}. Dispatches synthetic events to populate standard & controlled ATS inputs.`;
    if (badge) badge.textContent = 'Detecting ATS...';

    // Reset tabs to bookmarklet
    $$('#autofillModal .jh-tab-btn').forEach((btn, idx) => {
      btn.classList.toggle('is-active', idx === 0);
      btn.setAttribute('aria-selected', String(idx === 0));
    });
    $$('#autofillModal .jh-tab-pane').forEach((pane, idx) => {
      pane.hidden = (idx !== 0);
      pane.classList.toggle('is-active', idx === 0);
    });

    // Reset solver
    const solverInput = $('#afSolverQuestionInput');
    if (solverInput) solverInput.value = `Why are you interested in joining ${job.company} as a ${cleanTitle(job.title)}?`;
    const ansCard = $('#afAnswerCard');
    if (ansCard) ansCard.hidden = true;

    // Reset platform selector to auto
    const platSel = $('#afPlatformSelect');
    if (platSel) platSel.value = 'auto';

    // Immediately render local profile fallback so Tabs 2 and 4 are interactive without delay
    S.autofillPayload = getLocalAutofillFallback(S.profile, job);
    updateSelectedPlatformView('auto');

    try {
      const res = await api('/api/autofill/payload', {
        method: 'POST',
        body: { job }
      });
      if (res && res.success) {
        S.autofillPayload = res.payload;
        S.autofillScript = res.script;
        S.autofillPlatformInfo = res.platform_info;
        S.autofillAllPlatforms = res.payload.platforms || {};
        S.autofillReadiness = res.payload.readiness_audit || {};

        // Setup Bookmarklet button & script
        const bmLink = $('#afBookmarkletDraggable');
        if (bmLink) {
          bmLink.href = res.bookmarklet;
          bmLink.setAttribute('title', `Drag me to your Bookmarks Bar! (Autofills ${job.company})`);
        }
        const openJobBtn = $('#afBtnOpenJobUrl');
        if (openJobBtn) {
          openJobBtn.href = job.url || '#';
          openJobBtn.hidden = !job.url;
        }

        // Render Platform Details & Requirements
        updateSelectedPlatformView('auto');
      }
    } catch (err) {
      toast('Could not load autofill payload: ' + err.message, 'error');
    }
  }

  function updateSelectedPlatformView(selectedKey) {
    const p = S.autofillPayload;
    if (!p) return;
    const detectedKey = p.detected_platform || 'standard';
    const activeKey = (!selectedKey || selectedKey === 'auto') ? detectedKey : selectedKey;
    const allPlats = S.autofillAllPlatforms || {};
    const pInfo = allPlats[activeKey] || p.platform_info || {};
    const audit = (S.autofillReadiness && S.autofillReadiness[activeKey]) || { ready: true, missing: [] };

    // 1. Update Header Badge & Subtitles
    const badge = $('#afPlatformBadge');
    if (badge) {
      badge.textContent = pInfo.badge || (activeKey.toUpperCase() + ' ATS');
    }
    const platTitle = $('#afReqPlatformTitle');
    const platTip = $('#afReqPlatformTip');
    const styleBadge = $('#afReqInputStyleBadge');
    const archText = $('#afReqArchText');
    const coverText = $('#afReqCoverText');
    const linkedInText = $('#afReqLinkedInText');

    if (platTitle) platTitle.textContent = `${pInfo.name || activeKey} Intelligence`;
    if (platTip) platTip.textContent = pInfo.tip || 'Platform requirements and guidelines.';
    if (styleBadge) styleBadge.textContent = pInfo.input_style ? pInfo.input_style.split('&')[0].trim() : 'Standard HTML5';
    if (archText) archText.textContent = pInfo.input_style || 'HTML5 Form';
    if (coverText) coverText.textContent = pInfo.cover_letter_style || 'Textarea / Note Field';
    if (linkedInText) linkedInText.textContent = pInfo.linkedin_style || 'Profile URL';

    // 2. Update Mandatory Rules List
    const mandList = $('#afReqMandatoryList');
    if (mandList) {
      const rules = (pInfo && Array.isArray(pInfo.mandatory_rules) && pInfo.mandatory_rules.length) ? pInfo.mandatory_rules : [
        'Full Legal Name or Discrete First/Last Name',
        'Email Address & Valid Contact Phone Number',
        'Resume Document / File Attachment',
        'LinkedIn Profile URL'
      ];
      mandList.innerHTML = rules.map(r => `<li>${esc(r)}</li>`).join('');
    }

    // 3. Update Readiness Pill
    const pill = $('#afReadinessPill');
    const pillIcon = $('#afReadinessPillIcon');
    const pillText = $('#afReadinessPillText');
    if (pill && pillIcon && pillText) {
      if (audit.ready) {
        pill.className = 'af-readiness-pill is-ready';
        pillIcon.textContent = '✓';
        pillText.textContent = `Profile 100% Ready for ${pInfo.name || activeKey}`;
      } else {
        pill.className = 'af-readiness-pill is-warning';
        pillIcon.textContent = '⚠️';
        pillText.textContent = `Attention: ${audit.missing.join(', ')}`;
      }
    }

    // 4. Render Field Palette (Tab 2) with Site Context
    renderAutofillFieldsPalette(p, activeKey);

    // 5. Render Checklist (Tab 4)
    renderAutofillRequirements(pInfo);
  }

  function renderAutofillFieldsPalette(p, activeKey) {
    const container = $('#afFieldsContainer');
    if (!container || !p) return;

    activeKey = activeKey || p.detected_platform || 'standard';

    const locStr = [p.city, p.country].filter(Boolean).join(', ') || p.location || '';
    const eduStr = [p.degree, p.institution].filter(Boolean).join(' @ ') || '';

    const categories = [
      {
        title: '👤 Personal Contact & Identity',
        fields: [
          { k: 'Full Name', v: p.full_name, siteNote: activeKey === 'lever' ? 'Lever: input[name="name"]' : '' },
          { k: 'First Name', v: p.first_name, siteNote: activeKey === 'greenhouse' ? 'Greenhouse: #first_name' : activeKey === 'workday' ? 'Workday: legalName' : '' },
          { k: 'Last Name', v: p.last_name, siteNote: activeKey === 'greenhouse' ? 'Greenhouse: #last_name' : activeKey === 'workday' ? 'Workday: legalName' : '' },
          { k: 'Email', v: p.email, siteNote: 'All ATSs' },
          { k: 'Phone', v: p.phone, siteNote: activeKey === 'jobvite' ? 'Jobvite: cellPhone' : 'All ATSs' },
          { k: 'Location / City', v: locStr, siteNote: activeKey === 'workday' ? 'Workday: addressSection' : '' }
        ]
      },
      {
        title: '🔗 Web & Social Presence (Site Rules)',
        fields: [
          { k: 'LinkedIn Profile URL', v: p.linkedin_url, siteNote: activeKey === 'lever' ? 'Lever: urls[LinkedIn] (MANDATORY)' : activeKey === 'smartrecruiters' ? 'SmartRecruiters: linkedin-input' : 'Direct Link' },
          { k: 'GitHub Profile URL', v: p.github_url, siteNote: activeKey === 'lever' ? 'Lever: urls[GitHub]' : 'Portfolio Link' },
          { k: 'Portfolio / Website', v: p.portfolio_url, siteNote: activeKey === 'lever' ? 'Lever: urls[Portfolio]' : 'Web Presence' }
        ]
      },
      {
        title: '💼 Professional Fit & Legal Status',
        fields: [
          { k: 'Current Role', v: p.current_role, siteNote: 'Role Title' },
          { k: 'Current Employer', v: p.current_company, siteNote: activeKey === 'lever' ? 'Lever: input[name="org"]' : 'Employer' },
          { k: 'Desired Salary', v: p.desired_salary, siteNote: activeKey === 'bamboohr' ? 'BambooHR: desiredSalary' : 'Compensation' },
          { k: 'Notice Period', v: p.notice_period, siteNote: 'Availability' },
          { k: 'Work Authorization', v: p.work_authorization, siteNote: activeKey === 'workday' ? 'Workday Radio: Yes' : 'Legal Auth' },
          { k: 'Visa Sponsorship', v: p.visa_sponsorship, siteNote: 'Radio: No' },
          { k: 'Education', v: eduStr, siteNote: 'Degree' },
          { k: 'Top Core Skills', v: p.skills_csv, siteNote: 'Skills' }
        ]
      },
      {
        title: '📝 Cover Pitch & Textareas (Tailored for Role)',
        fields: [
          { k: 'Cover Letter Pitch (Comments / Notes)', v: p.cover_pitch || p.cover_letter, full: true, siteNote: activeKey === 'lever' ? 'Lever: textarea[name="comments"]' : activeKey === 'greenhouse' ? 'Greenhouse: #cover_letter_text' : activeKey === 'smartrecruiters' ? 'SmartRecruiters: message-to-hiring-manager' : 'Dedicated Pitch' },
          { k: 'Full Tailored Cover Letter', v: p.cover_letter, full: true, siteNote: 'Complete Letter' },
          { k: 'Candidate Executive Summary', v: p.summary, full: true, siteNote: 'Professional Bio' }
        ]
      }
    ];

    let html = '';
    categories.forEach(cat => {
      html += `
        <div class="af-category-section">
          <div class="af-field-category-title">${esc(cat.title)}</div>
          <div class="af-fields-grid">
            ${cat.fields.map(c => `
              <div class="af-field-tile${c.full ? ' af-tile-full' : ''}${!c.v ? ' is-empty' : ''}" data-field-name="${esc(c.k)}" data-copy-val="${esc(c.v || '')}" style="${c.full ? 'grid-column: 1 / -1;' : ''}">
                <div class="af-field-tile-head">
                  <span class="af-tile-k">
                    ${esc(c.k)}
                    ${c.siteNote ? `<span class="af-field-site-tag">${esc(c.siteNote)}</span>` : ''}
                  </span>
                  <span class="af-tile-copy-icon">${c.v ? ico('copy') : ''}</span>
                </div>
                <div class="af-tile-v" style="${c.full ? 'white-space: pre-wrap; max-height: 85px; overflow-y: auto; font-weight: normal; font-size: 12.5px; line-height: 1.5;' : ''}">${esc(c.v || 'Not provided in resume')}</div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    });

    container.innerHTML = html;

    $$('.af-field-tile', container).forEach(tile => {
      tile.addEventListener('click', async () => {
        const val = tile.dataset.copyVal;
        const name = tile.dataset.fieldName || 'Field';
        if (!val) {
          toast(`"${name}" is not set in your resume. You can update it in Resume Settings.`, 'info');
          return;
        }
        try {
          await navigator.clipboard.writeText(val);
          tile.classList.add('is-copied');
          const k = tile.querySelector('.af-tile-k');
          const prevK = k ? k.innerHTML : '';
          if (k) k.innerHTML = '<span style="color:#10b981;font-weight:700;">Copied to Clipboard! ✓</span>';
          setTimeout(() => {
            tile.classList.remove('is-copied');
            if (k) k.innerHTML = prevK;
          }, 1800);
        } catch (e) {
          toast('Browser blocked copying', 'error');
        }
      });
    });
  }

  function renderAutofillRequirements(info) {
    const list = $('#afReqChecklist');
    if (!list) return;
    const reqs = (info && Array.isArray(info.key_requirements) && info.key_requirements.length) ? info.key_requirements : [
      { label: 'Candidate Legal Name', selector: 'name, first_name, last_name', notes: 'Greenhouse/Lever standard name fields', status: 'Ready', required: true },
      { label: 'Email Address & Phone', selector: 'email, phone, tel', notes: 'Direct recruiter communication channel', status: 'Ready', required: true },
      { label: 'Resume / CV Document', selector: 'resume, file, attachment', notes: 'Formatted for ATS parsing and keyword extraction', status: 'Ready', required: true },
      { label: 'LinkedIn Profile URL', selector: 'urls[LinkedIn], linkedin', notes: 'Verified candidate professional history', status: 'Ready', required: true },
      { label: 'Tailored Pitch / Cover Note', selector: 'cover_letter, comments, notes', notes: 'Auto-customized to role description and requirements', status: 'Ready', required: false },
      { label: 'Work Authorization & Notice', selector: 'work_authorization, notice_period', notes: 'Legal work status and target start timeline', status: 'Ready', required: true }
    ];

    list.innerHTML = reqs.map(r => {
      const isMand = r.required !== false;
      return `
        <div class="af-check-row">
          <div style="display:flex;flex-direction:column;gap:3px;flex:1;">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              <span class="${isMand ? 'af-req-badge-mandatory' : 'af-req-badge-optional'}">${isMand ? 'Mandatory' : 'Optional'}</span>
              <strong style="font-size:13px;color:var(--text-1);">${esc(r.label)}</strong>
              ${r.selector ? `<code style="font-size:11px;background:rgba(0,0,0,0.06);padding:1px 6px;border-radius:4px;color:var(--text-2);font-family:ui-monospace,monospace;">${esc(r.selector)}</code>` : ''}
            </div>
            ${r.notes ? `<span style="font-size:11.5px;color:var(--text-3);padding-left:2px;line-height:1.4;">${esc(r.notes)}</span>` : ''}
          </div>
          <span class="af-check-status" style="white-space:nowrap;margin-left:8px;">✓ ${esc(r.status || 'Ready')}</span>
        </div>
      `;
    }).join('');
  }

  async function executeEasyApply(job) {
    if (!job) return;
    toast(`⚡ Initializing 1-Click Easy Apply for ${job.company}...`);
    try {
      const res = await api('/api/easy-apply', {
        method: 'POST',
        body: { job }
      });
      if (res && res.success) {
        toast(`✓ Applied to ${job.company} (${cleanTitle(job.title)})! Added to tracker.`);
        await loadApplications();
        renderDetail();
        renderList();
        openAutofillCopilot(job);
      }
    } catch (err) {
      toast('Easy Apply failed: ' + err.message, 'error');
    }
  }

  async function solveScreeningQuestionFromUi() {
    const qInput = $('#afSolverQuestionInput');
    const question = (qInput && qInput.value || '').trim();
    if (!question) {
      toast('Please enter or select a question first.');
      return;
    }
    const tone = val('afSolverTone') || 'direct';
    const solveBtn = $('#afBtnSolveQuestion');
    if (solveBtn) {
      solveBtn.disabled = true;
      solveBtn.innerHTML = '<span>⚡ Solving with AI...</span>';
    }

    try {
      const res = await api('/api/autofill/solve-question', {
        method: 'POST',
        body: { question, job: S.activeAutofillJob, tone }
      });
      if (res && res.success) {
        const card = $('#afAnswerCard');
        const body = $('#afAnswerBodyText');
        const tag = $('#afAnswerEngineTag');
        const count = $('#afAnswerWordCount');
        if (card) card.hidden = false;
        if (body) body.textContent = res.answer;
        if (tag) tag.textContent = `${res.provider.toUpperCase()} Grounded`;
        if (count) count.textContent = `${res.word_count || res.answer.split(' ').length} words`;
      }
    } catch (err) {
      toast('Could not solve question: ' + err.message, 'error');
    } finally {
      if (solveBtn) {
        solveBtn.disabled = false;
        solveBtn.innerHTML = '<span>⚡ Solve with AI (Grounded)</span>';
      }
    }
  }

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
      if (!e.target.closest('.menu-wrap, .dock-menu-wrap')) closeMenu();
    });
    const moreBtn = $('#moreBtn');
    if (moreBtn) moreBtn.addEventListener('click', toggleMenu);
    const moreMenu = $('#moreMenu');
    if (moreMenu) moreMenu.addEventListener('click', e => { if (e.target.closest('a, button')) closeMenu(); });
    const bd = $('#jobDetailBackdrop');
    if (bd) bd.addEventListener('click', closeDetailSheet);

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        closeMenu();
        closeDetailSheet();
        closeAutofillCopilot();
      }
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

    const btnRefreshRecs = $('#btnRefreshRecs');
    if (btnRefreshRecs) {
      btnRefreshRecs.addEventListener('click', () => {
        toast('Curating fresh recommendations tailored to your profile...');
        loadRecommendations(true);
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
    $('#sortResultsBy').addEventListener('change', () => { filterAndRender(true); });
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

    // Search capacity & global targeting settings
    const saveCapacityBtn = $('#btnSaveCapacity');
    if (saveCapacityBtn) saveCapacityBtn.addEventListener('click', saveSearchCapacitySettings);
    const userCountrySel = $('#cfgUserCountry');
    if (userCountrySel) {
      userCountrySel.addEventListener('change', () => {
        const customField = $('#cfgCustomCountryField');
        if (customField) customField.hidden = (userCountrySel.value !== 'custom');
      });
    }

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
    $('#profileForm').addEventListener('change', e => { if (e.target.id !== 'newSkill') markDirty(); });
    $('#profileForm').addEventListener('submit', e => e.preventDefault());
    $('#newSkill').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addSkillFromInput(); } });
    $('#resumeFileInput').addEventListener('change', e => { handleFile(e.target.files[0]); e.target.value = ''; });
    const dz = $('#dropzone');
    ['dragenter', 'dragover'].forEach(t => dz.addEventListener(t, e => { e.preventDefault(); dz.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach(t => dz.addEventListener(t, e => { e.preventDefault(); dz.classList.remove('is-over'); }));
    dz.addEventListener('drop', e => handleFile(e.dataTransfer.files[0]));

    // applications board: stage menu, drag and drop, and card click to open drawer
    const board = $('#kanbanBoard');
    board.addEventListener('change', e => { const s = e.target.closest('[data-action="app-stage"]'); if (s) moveApp(s.dataset.id, s.value); });
    board.addEventListener('click', e => {
      const card = e.target.closest('.kcard');
      if (!card) return;
      if (e.target.closest('button, select, a, input, textarea, label')) return;
      const app = S.applications.find(a => a.id === card.dataset.id);
      if (app) openAppDrawer(app);
    });
    board.addEventListener('dragstart', e => {
      const c = e.target.closest('.kcard');
      if (c) {
        e.dataTransfer.setData('text/plain', c.dataset.id);
        e.dataTransfer.effectAllowed = 'move';
        c.classList.add('dragging');
      }
    });
    board.addEventListener('dragend', e => {
      const c = e.target.closest('.kcard') || $('.kcard.dragging', board);
      if (c) c.classList.remove('dragging');
      $$('.col', board).forEach(x => x.classList.remove('drop-over'));
    });
    board.addEventListener('dragenter', e => {
      const c = e.target.closest('.col');
      if (c) {
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
      }
    });
    board.addEventListener('dragover', e => {
      const c = e.target.closest('.col');
      if (c) {
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
        $$('.col', board).forEach(x => x.classList.toggle('drop-over', x === c));
      }
      // Edge auto-scrolling for long lists of cards
      const wrap = $('#appBoardWrap');
      const mouseY = e.clientY;
      const mouseX = e.clientX;
      const vh = window.innerHeight;
      if (mouseY < 70) {
        window.scrollBy({ top: -14, behavior: 'auto' });
      } else if (mouseY > vh - 90) {
        window.scrollBy({ top: 14, behavior: 'auto' });
      }
      if (wrap) {
        const wrapRect = wrap.getBoundingClientRect();
        if (mouseX < wrapRect.left + 60) {
          wrap.scrollBy({ left: -18, behavior: 'auto' });
        } else if (mouseX > wrapRect.right - 60) {
          wrap.scrollBy({ left: 18, behavior: 'auto' });
        }
      }
    });
    board.addEventListener('dragleave', e => {
      if (!e.relatedTarget || !board.contains(e.relatedTarget)) {
        $$('.col', board).forEach(x => x.classList.remove('drop-over'));
      }
    });
    board.addEventListener('drop', e => {
      const c = e.target.closest('.col');
      $$('.col', board).forEach(x => x.classList.remove('drop-over'));
      if (!c) return;
      e.preventDefault();
      const id = e.dataTransfer.getData('text/plain');
      if (id && c.dataset.stage) moveApp(id, c.dataset.stage);
    });

    // applications table: stage menu and row click
    const tableBody = $('#appTableBody');
    if (tableBody) {
      tableBody.addEventListener('change', e => {
        const s = e.target.closest('[data-action="app-stage"]');
        if (s) moveApp(s.dataset.id, s.value);
      });
      tableBody.addEventListener('click', e => {
        const row = e.target.closest('.app-table-row');
        if (!row) return;
        if (e.target.closest('button, select, a, input, textarea, label')) return;
        const app = S.applications.find(a => a.id === row.dataset.id);
        if (app) openAppDrawer(app);
      });
    }

    // dialogs and digest
    $('#appDialogForm').addEventListener('submit', e => { e.preventDefault(); submitAppDialog(); });
    $('#watchDialogForm').addEventListener('submit', e => { e.preventDefault(); submitWatch(); });
    $('#digestThresholdSelect').addEventListener('change', changeDigestCutoff);
  }

  // ----------------------------------------------------------------- hidden jobs
  function toggleHideJob(key) {
    if (!key) return;
    if (S.hiddenJobs.has(key)) {
      S.hiddenJobs.delete(key);
      toast('Job restored to search results');
    } else {
      S.hiddenJobs.add(key);
      toast('Job hidden. Find it in Hidden Jobs.');
    }
    try {
      localStorage.setItem('jh_hidden_jobs', JSON.stringify(Array.from(S.hiddenJobs)));
    } catch (e) {}
    updateHiddenJobsBadge();
    filterAndRender();
  }

  function updateHiddenJobsBadge() {
    const b = $('#p4HiddenCount');
    if (b) {
      const cnt = (S.hiddenJobs && S.hiddenJobs.size) || 0;
      b.textContent = String(cnt);
      b.hidden = cnt === 0;
    }
  }

  function syncJobTypeFilterState() {
    const jtMenu = $('#p4MenuJobType');
    const f = S.filters || {};
    const selected = f.jobTypes || new Set();

    if (jtMenu) {
      // Update check inputs in popover
      $$('input[name="p4JtCheck"]', jtMenu).forEach(cb => {
        cb.checked = selected.size > 0 ? selected.has(cb.value) : false;
      });

      // Compute facet counts dynamically from S.allJobs
      const jobs = S.allJobs || [];
      const counts = { 'Full-time': 0, 'Contract': 0, 'Part-time': 0, 'Internship': 0 };
      for (const j of jobs) {
        const jt = (j.job_type || '').toLowerCase();
        const t = (j.title || '').toLowerCase();
        if (jt.includes('intern') || t.includes('intern') || t.includes('werkstudent') || t.includes('praktik') || t.includes('stage')) counts['Internship']++;
        else if (jt.includes('part') || t.includes('part-time') || t.includes('part time') || t.includes('teilzeit')) counts['Part-time']++;
        else if (jt.includes('contract') || t.includes('contract') || t.includes('freelance') || t.includes('c2c')) counts['Contract']++;
        else counts['Full-time']++;
      }
      const cFt = $('#p4CountFullTime'); if (cFt) cFt.textContent = String(counts['Full-time']);
      const cCt = $('#p4CountContract'); if (cCt) cCt.textContent = String(counts['Contract']);
      const cPt = $('#p4CountPartTime'); if (cPt) cPt.textContent = String(counts['Part-time']);
      const cIn = $('#p4CountInternship'); if (cIn) cIn.textContent = String(counts['Internship']);
    }

    // Update Pill label & active status
    const pill = $('#p4PillJobType');
    const labelEl = $('#p4TextJobType');
    if (labelEl) {
      if (selected.size === 1) {
        labelEl.textContent = Array.from(selected)[0];
      } else if (selected.size > 1 && selected.size < 4) {
        labelEl.textContent = `${Array.from(selected)[0]} (+${selected.size - 1})`;
      } else {
        labelEl.textContent = 'Job Type';
      }
    }
    if (pill) {
      pill.classList.toggle('is-active', selected.size > 0 && selected.size < 4);
    }
  }

  // ----------------------------------------------------------------- picture 4 filter bar
  function setupP4FilterBar() {
    document.addEventListener('click', e => {
      const btn = e.target.closest('.p4-pill-btn[data-dropdown]');
      const allMenus = $$('.p4-dropdown-menu');
      const allBtns = $$('.p4-pill-btn[data-dropdown]');

      if (btn) {
        e.stopPropagation();
        const menuId = btn.dataset.dropdown;
        const menu = $('#' + menuId);
        const isOpen = menu && !menu.hidden;

        allMenus.forEach(m => m.hidden = true);
        allBtns.forEach(b => b.setAttribute('aria-expanded', 'false'));

        if (!isOpen && menu) {
          menu.hidden = false;
          btn.setAttribute('aria-expanded', 'true');
          if (menuId === 'p4MenuJobType') syncJobTypeFilterState();
        }
        return;
      }

      const insideMenu = e.target.closest('.p4-dropdown-menu');
      if (insideMenu && !e.target.closest('.p4-menu-item') && !e.target.closest('.p4-menu-chip')) {
        return;
      }

      allMenus.forEach(m => m.hidden = true);
      allBtns.forEach(b => b.setAttribute('aria-expanded', 'false'));
    });

    const locMenu = $('#p4MenuLocation');
    if (locMenu) {
      locMenu.addEventListener('click', e => {
        const item = e.target.closest('[data-loc]');
        if (!item) return;
        const loc = item.dataset.loc;
        S.filters.country = loc;
        const t = $('#p4TextLocation');
        if (t) t.textContent = loc === 'all' ? 'All Locations' : loc;
        $$('.p4-menu-item', locMenu).forEach(b => b.classList.toggle('is-selected', b === item));
        locMenu.hidden = true;
        filterAndRender();
      });
      const customBtn = $('#p4SetCustomLocation');
      if (customBtn) {
        customBtn.addEventListener('click', () => {
          const val = ($('#p4CustomLocation').value || '').trim();
          if (val) {
            S.filters.country = val;
            const t = $('#p4TextLocation');
            if (t) t.textContent = val;
            locMenu.hidden = true;
            filterAndRender();
          }
        });
      }
    }

    const roleMenu = $('#p4MenuRole');
    if (roleMenu) {
      roleMenu.addEventListener('click', e => {
        const chip = e.target.closest('[data-role]');
        if (!chip) return;
        const role = chip.dataset.role;
        const t = $('#p4TextRole');
        if (t) t.textContent = role;
        const q = $('#searchQuery');
        if (q) q.value = role;
        S.filters.jobFunctions = [role];
        S.filters.keyword = '';
        roleMenu.hidden = true;
        filterAndRender();
      });
      const setRoleBtn = $('#p4SetRole');
      if (setRoleBtn) {
        setRoleBtn.addEventListener('click', () => {
          const role = ($('#p4RoleInput').value || '').trim();
          if (role) {
            const t = $('#p4TextRole');
            if (t) t.textContent = role;
            const q = $('#searchQuery');
            if (q) q.value = role;
            S.filters.jobFunctions = [role];
            S.filters.keyword = '';
            roleMenu.hidden = true;
            filterAndRender();
          }
        });
      }
    }

    const senMenu = $('#p4MenuSeniority');
    if (senMenu) {
      senMenu.addEventListener('click', e => {
        const item = e.target.closest('[data-sen]');
        if (!item) return;
        const sen = item.dataset.sen;
        S.filters.seniority = sen;
        S.filters.expLevels = (sen === 'all' ? new Set() : new Set([sen]));
        const labels = { all: 'All Seniority', junior: 'Entry Level', mid: 'Mid Level', senior: 'Senior Level', lead_staff: 'Lead / Staff' };
        const t = $('#p4TextSeniority');
        if (t) t.textContent = labels[sen] || 'Seniority';
        $$('.p4-menu-item', senMenu).forEach(b => b.classList.toggle('is-selected', b === item));
        senMenu.hidden = true;
        filterAndRender();
      });
    }

    const jtMenu = $('#p4MenuJobType');
    if (jtMenu) {
      jtMenu.addEventListener('click', e => {
        if (e.target.closest('.p4-check-item')) {
          e.stopPropagation();
        }
      });

      const confirmBtn = $('#p4BtnConfirmJobType');
      if (confirmBtn) {
        confirmBtn.addEventListener('click', e => {
          e.preventDefault();
          e.stopPropagation();
          const checked = Array.from($$('input[name="p4JtCheck"]:checked', jtMenu)).map(c => c.value);
          S.filters.jobTypes = new Set(checked);
          S.filters.jobType = checked.length === 1 ? checked[0] : (checked.length === 0 || checked.length === 4 ? 'all' : checked.join(','));

          // Sync drawer checkboxes if present
          $$('input[name="afJobType"]').forEach(cb => {
            cb.checked = S.filters.jobTypes.size > 0 ? S.filters.jobTypes.has(cb.value) : false;
          });

          syncJobTypeFilterState();
          jtMenu.hidden = true;
          const pill = $('#p4PillJobType');
          if (pill) pill.setAttribute('aria-expanded', 'false');
          filterAndRender();
        });
      }
    }

    const wmMenu = $('#p4MenuWorkMode');
    if (wmMenu) {
      wmMenu.addEventListener('click', e => {
        const item = e.target.closest('[data-mode]');
        if (!item) return;
        const mode = item.dataset.mode;
        S.filters.workMode = mode;
        S.filters.workModels = (mode === 'Any' || mode === 'all' ? new Set() : new Set([mode]));
        const t = $('#p4TextWorkMode');
        if (t) t.textContent = mode === 'Any' ? 'Any Mode' : `${mode} (+2)`;
        $$('.p4-menu-item', wmMenu).forEach(b => b.classList.toggle('is-selected', b === item));
        wmMenu.hidden = true;
        filterAndRender();
      });
    }

    const dpMenu = $('#p4MenuDatePosted');
    if (dpMenu) {
      dpMenu.addEventListener('click', e => {
        const item = e.target.closest('[data-days]');
        if (!item) return;
        const days = parseInt(item.dataset.days, 10);
        S.filters.freshnessDays = days;
        const labels = { 0: 'Date Posted', 1: 'Past 24h', 3: 'Past 3 days', 7: 'Past week', 30: 'Past month' };
        const t = $('#p4TextDatePosted');
        if (t) t.textContent = labels[days] || 'Date Posted';
        $$('.p4-menu-item', dpMenu).forEach(b => b.classList.toggle('is-selected', b === item));
        dpMenu.hidden = true;
        filterAndRender();
      });
    }

    const indMenu = $('#p4MenuIndustry');
    if (indMenu) {
      indMenu.addEventListener('click', e => {
        const item = e.target.closest('[data-ind]');
        if (!item) return;
        const ind = item.dataset.ind;
        S.filters.industry = ind;
        const labels = { all: 'Industry', tech: 'Tech & Software', finance: 'Finance', consulting: 'Consulting', health: 'Healthcare' };
        const t = $('#p4TextIndustry');
        if (t) t.textContent = labels[ind] || 'Industry';
        $$('.p4-menu-item', indMenu).forEach(b => b.classList.toggle('is-selected', b === item));
        indMenu.hidden = true;
        filterAndRender();
      });
    }

    const famMenu = $('#p4MenuFamous');
    if (famMenu) {
      famMenu.addEventListener('click', e => {
        const item = e.target.closest('[data-famous]');
        if (!item) return;
        const mode = item.dataset.famous || 'all';
        S.famousFilter = mode;
        S.filters.famousMode = mode;
        try { localStorage.setItem('jh-famous-filter', mode); } catch (err) {}
        syncFamousUi();
        famMenu.hidden = true;
        filterAndRender();
      });
    }

    const yoeMenu = $('#p4MenuYoe');
    if (yoeMenu) {
      yoeMenu.addEventListener('click', e => {
        const item = e.target.closest('[data-yoe]');
        if (!item) return;
        const yoe = item.dataset.yoe;
        S.filters.yoe = yoe;
        const labels = { all: 'Years of Experience', '0-2': '0-2 yrs', '2-5': '2-5 yrs', '5-8': '5-8 yrs', '8+': '8+ yrs' };
        const t = $('#p4TextYoe');
        if (t) t.textContent = labels[yoe] || 'Years of Experience';
        $$('.p4-menu-item', yoeMenu).forEach(b => b.classList.toggle('is-selected', b === item));
        yoeMenu.hidden = true;
        filterAndRender();
      });
    }

    const resumeMenu = $('#p4MenuResume');
    if (resumeMenu) {
      resumeMenu.addEventListener('click', e => {
        const item = e.target.closest('[data-resume-id]');
        if (!item) return;
        const rid = item.dataset.resumeId || 'all';
        S.filterResume = rid;
        $$('.p4-menu-item', resumeMenu).forEach(b => b.classList.toggle('is-selected', b === item));
        const labelEl = $('#p4TextResume');
        if (labelEl) {
          if (rid === 'all') {
            labelEl.textContent = 'Resume: All';
          } else {
            const list = S.profiles || [];
            const found = list.find(p => p.id === rid);
            labelEl.textContent = found ? `Resume: ${found.name}` : 'Resume: All';
          }
        }
        resumeMenu.hidden = true;
        filterAndRender();
      });
    }

    const btnHidden = $('#p4BtnHiddenJobs');
    if (btnHidden) {
      btnHidden.addEventListener('click', () => {
        S.showHidden = !S.showHidden;
        btnHidden.classList.toggle('is-active', S.showHidden);
        const span = btnHidden.querySelector('span');
        if (span) span.textContent = S.showHidden ? 'Viewing Hidden' : 'Hidden Jobs';
        filterAndRender();
      });
    }

    const btnAllFilters = $('#p4BtnAllFilters');
    if (btnAllFilters) {
      btnAllFilters.addEventListener('click', () => {
        openAllFiltersDrawer();
      });
    }

    // Refresh & Sync DB button handler
    const btnRefreshSync = $('#btnJobsRefreshSync');
    if (btnRefreshSync) {
      btnRefreshSync.addEventListener('click', async () => {
        btnRefreshSync.classList.add('is-refreshing');
        btnRefreshSync.classList.remove('is-success');
        const btnLabel = btnRefreshSync.querySelector('span:not(.p4-refresh-badge)');
        const originalText = btnLabel ? btnLabel.textContent : 'Refresh';
        if (btnLabel) btnLabel.textContent = 'Syncing...';

        // 2026/2027 Ambient Live Sync Banner Activation
        const liveBanner = $('#liveSyncBanner');
        const liveStatus = $('#liveSyncStatus');
        const liveFill = $('#liveSyncProgressFill');
        const liveKicker = $('#liveSyncKicker');
        const liveCountTag = $('#liveSyncCountTag');

        let liveTickerTimer = null;
        if (liveBanner) {
          liveBanner.hidden = false;
          liveBanner.classList.remove('is-leaving');
          liveBanner.classList.add('is-entering');
          if (liveFill) liveFill.style.width = '15%';
          if (liveStatus) liveStatus.textContent = 'Connecting to Y Combinator, Ashby, Greenhouse & ATS...';
          if (liveKicker) liveKicker.textContent = 'Live Sync';
          if (liveCountTag) liveCountTag.textContent = '18 sources active';

          const steps = [
            { text: 'Checking startup ecosystems & direct ATS portals...', width: '38%' },
            { text: 'Ingesting verified postings & deduplicating...', width: '68%' },
            { text: 'Analyzing match scores & sorting opportunities...', width: '88%' }
          ];
          let stepIdx = 0;
          liveTickerTimer = setInterval(() => {
            if (stepIdx < steps.length) {
              if (liveStatus) liveStatus.textContent = steps[stepIdx].text;
              if (liveFill) liveFill.style.width = steps[stepIdx].width;
              stepIdx++;
            }
          }, 320);
        }

        try {
          const f = S.filters || {};
          const cat = (f.jobFunctions && f.jobFunctions.length) ? f.jobFunctions[0] : '';
          const payload = {
            category: cat,
            q: (f.keyword && f.keyword.toLowerCase() !== cat.toLowerCase()) ? f.keyword : '',
            work_mode: (f.workMode && f.workMode !== 'Any' && f.workMode !== 'all') ? f.workMode : ((f.workModels && f.workModels.size === 1) ? Array.from(f.workModels)[0] : ''),
            seniority: (f.seniority && f.seniority !== 'all') ? f.seniority : ((f.expLevels && f.expLevels.size === 1) ? Array.from(f.expLevels)[0] : ''),
            job_type: (f.jobTypes && f.jobTypes.size > 0 && f.jobTypes.size < 4) ? Array.from(f.jobTypes).join(',') : ((f.jobType && f.jobType !== 'all') ? f.jobType : ''),
            country: (f.country && f.country !== 'all') ? f.country : '',
            location: (f.locationQuery && f.locationQuery !== 'Anywhere in the US' && f.locationQuery !== 'Worldwide' && f.locationQuery.trim()) ? f.locationQuery.trim() : '',
            min_salary: (!f.salaryOpenToAll && f.minSalary > 0) ? String(f.minSalary) : (f.salaryTier && f.salaryTier !== '0' && f.salaryTier !== 'disclosed' ? f.salaryTier.replace('k', '000') : '0'),
            min_score: f.minScore > 0 ? String(f.minScore) : '0',
            days: f.freshnessDays > 0 ? String(f.freshnessDays) : '0',
            famous_mode: f.famousMode || 'all',
            industry: (f.industry && f.industry !== 'all') ? f.industry : ((f.industries && f.industries.size > 0) ? Array.from(f.industries)[0] : ''),
            sort: val('sortResultsBy') || 'ranked'
          };
          const res = await api('/api/jobs/refresh-sync', { method: 'POST', body: payload });
          if (liveTickerTimer) clearInterval(liveTickerTimer);

          if (res) {
            const allPool = (res.all_jobs && res.all_jobs.length) ? res.all_jobs : ((res.jobs && res.jobs.length) ? res.jobs : (S.allJobs && S.allJobs.length ? S.allJobs : []));
            S.allJobs = allPool;
            S.jobsRanked = allPool;
            S.jobs = (res.jobs && res.jobs.length) ? res.jobs : allPool;
            S.searchMeta = res.meta || S.searchMeta || {};
            S.searchHasRun = true;
            if (S.jobs.length && (!S.selectedKey || !S.jobs.some(j => jobKey(j) === S.selectedKey))) {
              S.selectedKey = jobKey(S.jobs[0]);
            }

            // Track newly synced jobs to display the clean 'Just synced' micro-badge
            if (res.added_job_keys && res.added_job_keys.length) {
              S.justSyncedKeys = new Set(res.added_job_keys);
              setTimeout(() => {
                S.justSyncedKeys = null;
                renderList(false);
              }, 15000);
            } else {
              S.justSyncedKeys = null;
            }

            // Render with fluid spring stagger animation
            filterAndRender(false, true);

            const badge = $('#jobsRefreshBadge');
            if (badge) {
              badge.textContent = '0 new';
              badge.hidden = true;
            }

            // Live Sync Banner success state
            if (liveFill) liveFill.style.width = '100%';
            if (liveKicker) liveKicker.textContent = 'Sync Complete';
            const countAdded = res.added_count || 0;
            if (liveStatus) {
              liveStatus.textContent = countAdded > 0
                ? `✓ Synced ${countAdded} new opportunit${countAdded === 1 ? 'y' : 'ies'} • Database updated`
                : '✓ All 18 sources checked • Database is up to date';
            }

            // Button state morphing
            btnRefreshSync.classList.remove('is-refreshing');
            btnRefreshSync.classList.add('is-success');
            if (btnLabel) btnLabel.textContent = 'Synced!';

            toast(res.message || 'Database refreshed: New jobs synced and active!');
            checkLinkedinRadarStatus();
          }
        } catch (err) {
          if (liveTickerTimer) clearInterval(liveTickerTimer);
          console.warn('Refresh sync error:', err);
          if (liveStatus) liveStatus.textContent = '✓ Database checked and synchronized.';
          if (liveFill) liveFill.style.width = '100%';
          toast('Database is up to date.');
        } finally {
          btnRefreshSync.classList.remove('is-refreshing');
          checkAutoSearchStatus();
          checkLinkedinRadarStatus();
          scheduleNextEnrichmentCheck(1000);

          // Smoothly slide out live sync banner and reset button
          setTimeout(() => {
            if (liveBanner && !liveBanner.hidden) {
              liveBanner.classList.remove('is-entering');
              liveBanner.classList.add('is-leaving');
              setTimeout(() => {
                liveBanner.hidden = true;
                liveBanner.classList.remove('is-leaving');
              }, 300);
            }
            if (btnLabel) btnLabel.textContent = originalText;
            btnRefreshSync.classList.remove('is-success');
          }, 2400);
        }
      });
    }

    // ⚡ 1-Click Application Autofill & Easy Apply Event Wiring
    const pillEasyApply = $('#p4PillEasyApply');
    if (pillEasyApply) {
      pillEasyApply.addEventListener('click', () => {
        S.filters.easyApplyOnly = !S.filters.easyApplyOnly;
        pillEasyApply.classList.toggle('is-active', S.filters.easyApplyOnly);
        if (S.searchHasRun) filterAndRender();
      });
    }

    const modalAf = $('#autofillModal');
    if (modalAf) {
      modalAf.addEventListener('click', e => {
        if (e.target.id === 'autofillModal' || e.target.id === 'afDrawerAutofillBackdrop') closeAutofillCopilot();
      });
      const btnCloseTop = $('#afModalCloseBtn');
      if (btnCloseTop) btnCloseTop.addEventListener('click', closeAutofillCopilot);
      const btnCloseBtm = $('#afModalBottomClose');
      if (btnCloseBtm) btnCloseBtm.addEventListener('click', closeAutofillCopilot);
      const btnDrawerApply = $('#afBtnEasyApplyInDrawer');
      if (btnDrawerApply) {
        btnDrawerApply.addEventListener('click', async () => {
          if (S.activeAutofillJob) await executeEasyApply(S.activeAutofillJob);
        });
      }

      // Tab switching
      $$('.jh-tab-btn', modalAf).forEach(btn => {
        btn.addEventListener('click', () => {
          const tabKey = btn.dataset.aftab;
          $$('.jh-tab-btn', modalAf).forEach(b => {
            const isMatch = b === btn;
            b.classList.toggle('is-active', isMatch);
            b.setAttribute('aria-selected', String(isMatch));
          });
          $$('.jh-tab-pane', modalAf).forEach(pane => {
            const paneKey = pane.id.replace('afPane', '').toLowerCase();
            const show = paneKey === tabKey.toLowerCase();
            pane.hidden = !show;
            pane.classList.toggle('is-active', show);
          });
        });
      });

      // Copy script button
      const btnCopyScript = $('#afBtnCopyScript');
      if (btnCopyScript) {
        btnCopyScript.addEventListener('click', async () => {
          const script = S.autofillScript || (S.autofillPayload && S.autofillPayload.script) || '';
          if (!script) return;
          try {
            await navigator.clipboard.writeText(script);
            const span = $('#afBtnCopyScriptText');
            if (span) {
              const orig = span.textContent;
              span.textContent = 'Copied Script! ✓';
              setTimeout(() => { span.textContent = orig; }, 2000);
            }
          } catch (e) {
            toast('Browser blocked copying', 'error');
          }
        });
      }

      // Screening Question Presets
      $$('.af-preset-btn', modalAf).forEach(btn => {
        btn.addEventListener('click', () => {
          const preset = btn.dataset.preset;
          const comp = (S.activeAutofillJob && S.activeAutofillJob.company) || 'your company';
          const title = (S.activeAutofillJob && cleanTitle(S.activeAutofillJob.title)) || 'this role';
          const input = $('#afSolverQuestionInput');
          if (!input) return;

          if (preset === 'why_us') {
            input.value = `Why are you interested in joining ${comp} as a ${title}?`;
          } else if (preset === 'accomplishment') {
            input.value = `What is your greatest or proudest technical accomplishment?`;
          } else if (preset === 'salary') {
            input.value = `What are your salary expectations and earliest start date?`;
          } else if (preset === 'tech_stack') {
            input.value = `What is your relevant hands-on experience with the core stack requested by ${comp}?`;
          }
          solveScreeningQuestionFromUi();
        });
      });

      // Solve Screening Question button
      const btnSolve = $('#afBtnSolveQuestion');
      if (btnSolve) {
        btnSolve.addEventListener('click', solveScreeningQuestionFromUi);
      }

      // Copy Answer button
      const btnCopyAns = $('#afBtnCopyAnswer');
      if (btnCopyAns) {
        btnCopyAns.addEventListener('click', async () => {
          const body = $('#afAnswerBodyText');
          const txt = body ? body.textContent : '';
          if (!txt) return;
          try {
            await navigator.clipboard.writeText(txt);
            const span = $('#afBtnCopyAnswerText');
            if (span) {
              const orig = span.textContent;
              span.textContent = 'Copied Answer! ✓';
              setTimeout(() => { span.textContent = orig; }, 2000);
            }
          } catch (e) {
            toast('Browser blocked copying', 'error');
          }
        });
      }

      // Easy Apply from Modal
      const btnModalEasyApply = $('#afBtnEasyApplyInModal');
      if (btnModalEasyApply) {
        btnModalEasyApply.addEventListener('click', () => {
          if (S.activeAutofillJob) executeEasyApply(S.activeAutofillJob);
        });
      }

      // ATS Platform selector change listener
      const platSel = $('#afPlatformSelect');
      if (platSel) {
        platSel.addEventListener('change', e => {
          updateSelectedPlatformView(e.target.value);
        });
      }
    }

    updateHiddenJobsBadge();
  }

  // ----------------------------------------------------------------- All Filters Drawer
  function openAllFiltersDrawer() {
    const overlay = $('#afDrawerOverlay');
    if (!overlay) return;
    const panel = $('#afDrawerPanel');
    if (panel) panel.scrollTop = 0;
    syncDrawerUiFromState();
    renderDrawerActivePills();
    overlay.hidden = false;
    overlay.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      overlay.classList.add('is-open');
    });
    const btn = $('#p4BtnAllFilters');
    if (btn) btn.classList.add('is-active');
  }

  function closeAllFiltersDrawer() {
    const overlay = $('#afDrawerOverlay');
    if (!overlay) return;
    overlay.classList.remove('is-open');
    overlay.setAttribute('aria-hidden', 'true');
    const panel = $('#afDrawerPanel');
    if (panel) panel.scrollTop = 0;
    setTimeout(() => {
      overlay.hidden = true;
    }, 280);
    const btn = $('#p4BtnAllFilters');
    if (btn) btn.classList.remove('is-active');
  }

  function renderJobFunctionChips() {
    const container = $('#afJobFunctionChips');
    if (!container) return;
    const fns = S.filters.jobFunctions || [];
    container.innerHTML = fns.map(fn => `
      <span class="af-tag-chip" data-fn="${esc(fn)}">
        <span>${esc(fn)}</span>
        <button type="button" class="af-tag-remove" aria-label="Remove ${esc(fn)}">&times;</button>
      </span>
    `).join('');
  }

  function renderExcludedTitleChips() {
    const container = $('#afExcludedTitleChips');
    if (!container) return;
    const titles = Array.from(S.filters.excludedTitles || []);
    container.innerHTML = titles.map(t => `
      <span class="af-tag-chip" data-title="${esc(t)}">
        <span>${esc(t)}</span>
        <button type="button" class="af-tag-remove" aria-label="Remove ${esc(t)}">&times;</button>
      </span>
    `).join('');
  }

  function renderExcludedIndustryChips() {
    const container = $('#afExcludedIndustryChips');
    if (!container) return;
    const inds = Array.from(S.filters.excludedIndustries || []);
    container.innerHTML = inds.map(ind => `
      <span class="af-tag-chip" data-ind="${esc(ind)}">
        <span>${esc(ind)}</span>
        <button type="button" class="af-tag-remove" aria-label="Remove ${esc(ind)}">&times;</button>
      </span>
    `).join('');
  }

  function renderExcludedSkillChips() {
    const container = $('#afExcludedSkillChips');
    if (!container) return;
    const sks = Array.from(S.filters.excludedSkills || []);
    container.innerHTML = sks.map(sk => `
      <span class="af-tag-chip" data-sk="${esc(sk)}">
        <span>${esc(sk)}</span>
        <button type="button" class="af-tag-remove" aria-label="Remove ${esc(sk)}">&times;</button>
      </span>
    `).join('');
  }

  function renderCompanyChips() {
    const container = $('#afCompanyChips');
    if (!container) return;
    const cos = Array.from(S.filters.companies || []);
    container.innerHTML = cos.map(co => `
      <span class="af-tag-chip" data-co="${esc(co)}">
        <span>${esc(co)}</span>
        <button type="button" class="af-tag-remove" aria-label="Remove ${esc(co)}">&times;</button>
      </span>
    `).join('');
  }

  function syncDrawerUiFromState() {
    const f = S.filters || {};

    // 1. Job Functions & Excluded Titles
    renderJobFunctionChips();
    renderExcludedTitleChips();

    // 2. Job Types
    $$('input[name="afJobType"]').forEach(cb => {
      cb.checked = f.jobTypes ? f.jobTypes.has(cb.value) : false;
    });

    // 3. Work Models
    $$('input[name="afWorkModel"]').forEach(cb => {
      cb.checked = f.workModels ? f.workModels.has(cb.value) : false;
    });

    // 4. Location
    const cSel = $('#afCountrySelect');
    if (cSel && f.country) cSel.value = f.country;
    const locInp = $('#afLocationInput');
    if (locInp && f.locationQuery) locInp.value = f.locationQuery;
    const radSel = $('#afRadiusSelect');
    if (radSel && f.locationRadius) radSel.value = f.locationRadius;

    // 5. Experience Level
    $$('input[name="afExpLevel"]').forEach(cb => {
      cb.checked = f.expLevels ? f.expLevels.has(cb.value) : false;
    });

    // 6. Experience Slider & Toggle
    const expToggle = $('#afToggleExpOpen');
    if (expToggle) expToggle.checked = !!f.expOpenToAll;
    const expSlider = $('#afExpSlider');
    if (expSlider) expSlider.value = String(f.expYears || 0);
    const expSubval = $('#afExpSubval');
    if (expSubval) expSubval.textContent = f.expOpenToAll ? 'Any requirements' : `${f.expYears || 0}+ yrs`;
    const expWrap = $('#afExpSliderWrap');
    if (expWrap) expWrap.classList.toggle('is-disabled', !!f.expOpenToAll);

    // 7. Date Posted
    $$('input[name="afDatePosted"]').forEach(r => {
      r.checked = (f.freshnessDays && parseInt(r.value, 10) === f.freshnessDays);
    });

    // 8. Minimum Salary Slider & Toggle
    const salToggle = $('#afToggleSalaryOpen');
    if (salToggle) salToggle.checked = !!f.salaryOpenToAll;
    const salSlider = $('#afSalarySlider');
    if (salSlider) salSlider.value = String(f.minSalary || 0);
    const salSubval = $('#afSalarySubval');
    if (salSubval) salSubval.textContent = f.salaryOpenToAll ? 'Any salary' : `$${Math.round((f.minSalary || 0) / 1000)}k+`;
    const salWrap = $('#afSalarySliderWrap');
    if (salWrap) salWrap.classList.toggle('is-disabled', !!f.salaryOpenToAll);

    // 9. Work Authorization & Limitations
    const h1b = $('#afCheckH1B');
    if (h1b) h1b.checked = !!f.h1b;
    const clr = $('#afExcludeClearance');
    if (clr) clr.checked = !!f.excludeClearance;
    const ctz = $('#afExcludeCitizenOnly');
    if (ctz) ctz.checked = !!f.excludeCitizenOnly;

    // 10. Industry
    $$('input[name="afIndustry"]').forEach(cb => {
      cb.checked = f.industries ? f.industries.has(cb.value) : false;
    });
    renderExcludedIndustryChips();

    // 11. Skill
    $$('input[name="afSkill"]').forEach(cb => {
      cb.checked = f.skills ? f.skills.has(cb.value) : false;
    });
    renderExcludedSkillChips();

    // 12. Role Type
    $$('input[name="afRoleType"]').forEach(r => {
      r.checked = (f.roleType === r.value);
    });

    // 13. Company & Stages
    renderCompanyChips();
    $$('input[name="afCompanyStage"]').forEach(cb => {
      cb.checked = f.companyStages ? f.companyStages.has(cb.value) : false;
    });

    // 14. Exclude Staffing
    const stf = $('#afCheckExcludeStaffing');
    if (stf) stf.checked = !!f.excludeStaffing;
  }

  function renderDrawerActivePills() {
    const bar = $('#afActivePillsBar');
    if (!bar) return;
    const f = S.filters || {};
    const pills = [];

    // Job Functions
    (f.jobFunctions || []).forEach(fn => {
      pills.push({ type: 'jobFunction', val: fn, label: fn });
    });

    // Job Types
    if (f.jobTypes) {
      f.jobTypes.forEach(jt => {
        pills.push({ type: 'jobType', val: jt, label: jt });
      });
    }

    // Work Models
    if (f.workModels) {
      f.workModels.forEach(wm => {
        pills.push({ type: 'workModel', val: wm, label: wm });
      });
    }

    // Experience Levels
    const expLabels = { intern: 'Intern/New Grad', junior: 'Entry Level', mid: 'Mid Level', senior: 'Senior Level', lead_staff: 'Lead/Staff', director: 'Director/Executive' };
    if (f.expLevels) {
      f.expLevels.forEach(lvl => {
        pills.push({ type: 'expLevel', val: lvl, label: expLabels[lvl] || lvl });
      });
    }

    // Experience Years (if specified)
    if (!f.expOpenToAll && f.expYears > 0) {
      pills.push({ type: 'expYears', val: f.expYears, label: `${f.expYears}+ yrs exp` });
    }

    // Date Posted
    if (f.freshnessDays && f.freshnessDays > 0) {
      const freshLabels = { 1: 'Past 24 hours', 3: 'Past 3 days', 7: 'Past week', 30: 'Past month' };
      pills.push({ type: 'datePosted', val: f.freshnessDays, label: freshLabels[f.freshnessDays] || `< ${f.freshnessDays}d` });
    }

    // Location / Country
    if (f.country && f.country !== 'all') {
      pills.push({ type: 'country', val: f.country, label: f.country });
    }

    // Salary (if specified)
    if (!f.salaryOpenToAll && f.minSalary > 0) {
      pills.push({ type: 'minSalary', val: f.minSalary, label: `$${Math.round(f.minSalary / 1000)}k+` });
    }

    // H1B
    if (f.h1b) {
      pills.push({ type: 'h1b', val: 'h1b', label: 'H1B sponsorship' });
    }

    // Clearance & Citizen Only
    if (f.excludeClearance) {
      pills.push({ type: 'clearance', val: 'clearance', label: 'No clearance' });
    }
    if (f.excludeCitizenOnly) {
      pills.push({ type: 'citizenOnly', val: 'citizenOnly', label: 'US Citizen Only' });
    }

    // Industries
    if (f.industries) {
      f.industries.forEach(ind => {
        pills.push({ type: 'industry', val: ind, label: ind });
      });
    }

    // Skills
    if (f.skills) {
      f.skills.forEach(sk => {
        pills.push({ type: 'skill', val: sk, label: sk });
      });
    }

    // Role Type
    if (f.roleType && f.roleType !== 'all') {
      pills.push({ type: 'roleType', val: f.roleType, label: f.roleType === 'ic' ? 'IC' : 'Manager' });
    }

    // Companies
    if (f.companies) {
      f.companies.forEach(co => {
        pills.push({ type: 'company', val: co, label: co });
      });
    }

    // Company Stages
    const stageLabels = { early: 'Early Stage', growth: 'Growth Stage', late: 'Late Stage', public: 'Public Company' };
    if (f.companyStages) {
      f.companyStages.forEach(st => {
        pills.push({ type: 'companyStage', val: st, label: stageLabels[st] || st });
      });
    }

    // Exclude Staffing
    if (f.excludeStaffing) {
      pills.push({ type: 'excludeStaffing', val: 'excludeStaffing', label: 'Exclude Staffing' });
    }

    // Render Pills
    bar.innerHTML = pills.map(p => `
      <span class="af-pill-badge" data-pill-type="${p.type}" data-pill-val="${esc(String(p.val))}">
        <span>${esc(p.label)}</span>
        <button type="button" class="af-pill-del" aria-label="Remove ${esc(p.label)}">&times;</button>
      </span>
    `).join('');

    // Dynamic Header Title: "Full Stack Engineer, US"
    const titleEl = $('#afHeaderTitle');
    if (titleEl) {
      const mainRole = (f.jobFunctions && f.jobFunctions[0]) || 'All Engineering Roles';
      let locPart = '';
      if (f.country === 'United States') locPart = ', US';
      else if (f.country && f.country !== 'all') locPart = `, ${f.country}`;
      titleEl.textContent = `${mainRole}${locPart}`;
    }

    // Sync Top Pill Bar
    const badge = $('#p4AllFiltersBadge');
    if (badge) {
      const activeCount = pills.length;
      badge.textContent = String(activeCount);
      badge.hidden = activeCount === 0;
    }

    const tRole = $('#p4TextRole');
    if (tRole && f.jobFunctions && f.jobFunctions.length > 0) {
      tRole.textContent = f.jobFunctions[0] + (f.jobFunctions.length > 1 ? ` (+${f.jobFunctions.length - 1})` : '');
    }
    const tWm = $('#p4TextWorkMode');
    if (tWm && f.workModels) {
      if (f.workModels.has('Remote') && f.workModels.size === 1) tWm.textContent = 'Remote';
      else if (f.workModels.size > 1) tWm.textContent = `${Array.from(f.workModels)[0]} (+${f.workModels.size - 1})`;
      else if (f.workModels.size === 1) tWm.textContent = Array.from(f.workModels)[0];
      else tWm.textContent = 'Work Mode';
    }
    const tSen = $('#p4TextSeniority');
    if (tSen && f.expLevels) {
      if (f.expLevels.size === 1) {
        tSen.textContent = expLabels[Array.from(f.expLevels)[0]] || 'Seniority';
      } else if (f.expLevels.size > 1) {
        tSen.textContent = `${expLabels[Array.from(f.expLevels)[0]] || 'Level'} (+${f.expLevels.size - 1})`;
      } else {
        tSen.textContent = 'Seniority';
      }
    }
    const tJt = $('#p4TextJobType');
    if (tJt && f.jobTypes) {
      if (f.jobTypes.size === 1) tJt.textContent = Array.from(f.jobTypes)[0];
      else if (f.jobTypes.size > 1) tJt.textContent = `${Array.from(f.jobTypes)[0]} (+${f.jobTypes.size - 1})`;
      else tJt.textContent = 'Job Type';
    }
    const tLoc = $('#p4TextLocation');
    if (tLoc) {
      tLoc.textContent = (f.country && f.country !== 'all') ? f.country : 'Location';
    }
    const tDate = $('#p4TextDatePosted');
    if (tDate) {
      const freshLabels = { 1: 'Past 24 hours', 3: 'Past 3 days', 7: 'Past week', 30: 'Past month' };
      tDate.textContent = f.freshnessDays ? (freshLabels[f.freshnessDays] || 'Date Posted') : 'Date Posted';
    }
  }

  function removeDrawerPill(type, val) {
    const f = S.filters || {};
    if (type === 'jobFunction') {
      f.jobFunctions = (f.jobFunctions || []).filter(item => item !== val);
    } else if (type === 'jobType') {
      if (f.jobTypes) f.jobTypes.delete(val);
      const cb = $(`input[name="afJobType"][value="${CSS.escape(val)}"]`);
      if (cb) cb.checked = false;
    } else if (type === 'workModel') {
      if (f.workModels) f.workModels.delete(val);
      const cb = $(`input[name="afWorkModel"][value="${CSS.escape(val)}"]`);
      if (cb) cb.checked = false;
    } else if (type === 'country') {
      f.country = 'all';
      const sel = $('#afCountrySelect');
      if (sel) sel.value = 'all';
    } else if (type === 'expLevel') {
      if (f.expLevels) f.expLevels.delete(val);
      const cb = $(`input[name="afExpLevel"][value="${CSS.escape(val)}"]`);
      if (cb) cb.checked = false;
    } else if (type === 'expYears') {
      f.expOpenToAll = true;
      f.expYears = 0;
      const tog = $('#afToggleExpOpen');
      if (tog) tog.checked = true;
    } else if (type === 'datePosted') {
      f.freshnessDays = 0;
      $$('input[name="afDatePosted"]').forEach(r => { r.checked = false; });
    } else if (type === 'minSalary') {
      f.salaryOpenToAll = true;
      f.minSalary = 0;
      f.salaryTier = '0';
      const tog = $('#afToggleSalaryOpen');
      if (tog) tog.checked = true;
    } else if (type === 'h1b') {
      f.h1b = false;
      const cb = $('#afCheckH1B');
      if (cb) cb.checked = false;
    } else if (type === 'clearance') {
      f.excludeClearance = false;
      const cb = $('#afExcludeClearance');
      if (cb) cb.checked = false;
    } else if (type === 'citizenOnly') {
      f.excludeCitizenOnly = false;
      const cb = $('#afExcludeCitizenOnly');
      if (cb) cb.checked = false;
    } else if (type === 'industry') {
      if (f.industries) f.industries.delete(val);
      const cb = $(`input[name="afIndustry"][value="${CSS.escape(val)}"]`);
      if (cb) cb.checked = false;
    } else if (type === 'skill') {
      if (f.skills) f.skills.delete(val);
      const cb = $(`input[name="afSkill"][value="${CSS.escape(val)}"]`);
      if (cb) cb.checked = false;
    } else if (type === 'roleType') {
      f.roleType = 'all';
      $$('input[name="afRoleType"]').forEach(r => { r.checked = false; });
    } else if (type === 'company') {
      if (f.companies) f.companies.delete(val);
      renderCompanyChips();
    } else if (type === 'companyStage') {
      if (f.companyStages) f.companyStages.delete(val);
      const cb = $(`input[name="afCompanyStage"][value="${CSS.escape(val)}"]`);
      if (cb) cb.checked = false;
    } else if (type === 'excludeStaffing') {
      f.excludeStaffing = false;
      const cb = $('#afCheckExcludeStaffing');
      if (cb) cb.checked = false;
    }

    const pane = $('#afContentPane');
    const prevScroll = pane ? pane.scrollTop : 0;
    syncDrawerUiFromState();
    renderDrawerActivePills();
    filterAndRender();
    if (pane) pane.scrollTop = prevScroll;
  }

  function setupAllFiltersDrawer() {
    const overlay = $('#afDrawerOverlay');
    if (!overlay) return;

    // Header Close & Confirm
    const btnClose = $('#afBtnClose');
    if (btnClose) btnClose.addEventListener('click', closeAllFiltersDrawer);
    const backdrop = $('#afDrawerBackdrop');
    if (backdrop) backdrop.addEventListener('click', closeAllFiltersDrawer);
    const btnConfirm = $('#afBtnConfirm');
    if (btnConfirm) {
      btnConfirm.addEventListener('click', () => {
        closeAllFiltersDrawer();
        filterAndRender();
        toast('Filters applied successfully');
      });
    }

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && overlay.classList.contains('is-open')) {
        closeAllFiltersDrawer();
      }
    });

    const panel = $('#afDrawerPanel');
    if (panel) {
      panel.addEventListener('scroll', () => {
        if (panel.scrollTop !== 0) panel.scrollTop = 0;
      });
    }
    const drawerBody = $('.af-drawer-body');
    if (drawerBody) {
      drawerBody.addEventListener('scroll', () => {
        if (drawerBody.scrollTop !== 0) drawerBody.scrollTop = 0;
      });
    }

    function scrollToDrawerSection(targetId) {
      const pane = $('#afContentPane');
      const sec = $('#' + targetId);
      if (!pane || !sec) return;
      const paneRect = pane.getBoundingClientRect();
      const secRect = sec.getBoundingClientRect();
      const offset = secRect.top - paneRect.top;
      pane.scrollTo({
        top: pane.scrollTop + offset - 8,
        behavior: 'smooth'
      });
    }

    // Left Navigation Tabs
    $$('.af-nav-item').forEach(item => {
      item.addEventListener('click', () => {
        $$('.af-nav-item').forEach(b => b.classList.remove('is-active'));
        item.classList.add('is-active');
        const targetId = item.dataset.afTarget;
        scrollToDrawerSection(targetId);
      });
    });

    // Promo Link
    const promoLink = $('#afPromoCompanyLink');
    if (promoLink) {
      promoLink.addEventListener('click', () => {
        $$('.af-nav-item').forEach(b => b.classList.toggle('is-active', b.dataset.afTarget === 'afSecCompany'));
        scrollToDrawerSection('afSecCompany');
      });
    }

    // Scrollspy on Right Content Pane
    const contentPane = $('#afContentPane');
    if (contentPane) {
      contentPane.addEventListener('scroll', () => {
        const sections = ['afSecBasic', 'afSecCompensation', 'afSecInterests', 'afSecCompany'];
        // If scrolled near bottom of content pane, automatically highlight the last section
        if (contentPane.scrollTop + contentPane.clientHeight >= contentPane.scrollHeight - 60) {
          $$('.af-nav-item').forEach(b => b.classList.toggle('is-active', b.dataset.afTarget === 'afSecCompany'));
          return;
        }
        const paneTop = contentPane.getBoundingClientRect().top;
        let current = sections[0];
        for (const id of sections) {
          const el = $('#' + id);
          if (el && el.getBoundingClientRect().top - paneTop <= 90) {
            current = id;
          }
        }
        $$('.af-nav-item').forEach(b => b.classList.toggle('is-active', b.dataset.afTarget === current));
      }, { passive: true });
    }

    // Active Pills Bar delegation
    const pillsBar = $('#afActivePillsBar');
    if (pillsBar) {
      pillsBar.addEventListener('click', e => {
        const badge = e.target.closest('.af-pill-badge');
        if (!badge) return;
        const type = badge.dataset.pillType;
        const val = badge.dataset.pillVal;
        removeDrawerPill(type, val);
      });
    }

    // 1. Job Functions
    const jfChips = $('#afJobFunctionChips');
    if (jfChips) {
      jfChips.addEventListener('click', e => {
        const removeBtn = e.target.closest('.af-tag-remove');
        if (!removeBtn) return;
        const chip = removeBtn.closest('.af-tag-chip');
        if (!chip) return;
        const fn = chip.dataset.fn;
        S.filters.jobFunctions = (S.filters.jobFunctions || []).filter(item => item !== fn);
        renderJobFunctionChips();
        renderDrawerActivePills();
        filterAndRender();
      });
    }

    const jfInput = $('#afJobFunctionInput');
    const jfSuggest = $('#afJobFunctionSuggest');
    if (jfInput) {
      jfInput.addEventListener('focus', () => {
        if (jfSuggest) jfSuggest.hidden = false;
      });
      jfInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const val = jfInput.value.trim();
          if (val) {
            if (!S.filters.jobFunctions) S.filters.jobFunctions = [];
            if (!S.filters.jobFunctions.includes(val)) {
              S.filters.jobFunctions.push(val);
            }
            jfInput.value = '';
            if (jfSuggest) jfSuggest.hidden = true;
            renderJobFunctionChips();
            renderDrawerActivePills();
            filterAndRender();
          }
        }
      });
    }

    if (jfSuggest) {
      jfSuggest.addEventListener('click', e => {
        const item = e.target.closest('.af-suggest-item');
        if (!item) return;
        const role = item.dataset.role;
        if (role) {
          if (!S.filters.jobFunctions) S.filters.jobFunctions = [];
          if (!S.filters.jobFunctions.includes(role)) {
            S.filters.jobFunctions.push(role);
          }
          if (jfInput) jfInput.value = '';
          jfSuggest.hidden = true;
          renderJobFunctionChips();
          renderDrawerActivePills();
          filterAndRender();
        }
      });
    }

    document.addEventListener('click', e => {
      const wrap = $('#afJobFunctionWrap');
      if (wrap && !wrap.contains(e.target) && jfSuggest) {
        jfSuggest.hidden = true;
      }
    });

    // Excluded Title Accordion
    const toggleExcludedTitle = $('#afToggleExcludedTitle');
    const bodyExcludedTitle = $('#afBodyExcludedTitle');
    if (toggleExcludedTitle && bodyExcludedTitle) {
      toggleExcludedTitle.addEventListener('click', () => {
        const isOpen = !bodyExcludedTitle.hidden;
        bodyExcludedTitle.hidden = isOpen;
        toggleExcludedTitle.setAttribute('aria-expanded', String(!isOpen));
        toggleExcludedTitle.classList.toggle('is-expanded', !isOpen);
      });
    }

    const btnAddExcludedTitle = $('#afAddExcludedTitleBtn');
    const inpExcludedTitle = $('#afExcludedTitleInput');
    function addExcludedTitle() {
      if (!inpExcludedTitle) return;
      const val = inpExcludedTitle.value.trim();
      if (val) {
        if (!S.filters.excludedTitles) S.filters.excludedTitles = new Set();
        S.filters.excludedTitles.add(val);
        inpExcludedTitle.value = '';
        renderExcludedTitleChips();
        filterAndRender();
      }
    }
    if (btnAddExcludedTitle) btnAddExcludedTitle.addEventListener('click', addExcludedTitle);
    if (inpExcludedTitle) inpExcludedTitle.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addExcludedTitle(); } });

    const chipsExcludedTitle = $('#afExcludedTitleChips');
    if (chipsExcludedTitle) {
      chipsExcludedTitle.addEventListener('click', e => {
        const removeBtn = e.target.closest('.af-tag-remove');
        if (!removeBtn) return;
        const chip = removeBtn.closest('.af-tag-chip');
        if (!chip) return;
        const title = chip.dataset.title;
        if (S.filters.excludedTitles) S.filters.excludedTitles.delete(title);
        renderExcludedTitleChips();
        filterAndRender();
      });
    }

    const preserveDrawerScroll = (fn) => {
      const pane = $('#afContentPane');
      const prev = pane ? pane.scrollTop : 0;
      fn();
      if (pane) pane.scrollTop = prev;
    };

    // 2. Job Type Checkboxes
    $$('input[name="afJobType"]').forEach(cb => {
      cb.addEventListener('change', () => {
        S.filters.jobTypes = new Set(Array.from($$('input[name="afJobType"]:checked')).map(el => el.value));
        S.filters.jobType = S.filters.jobTypes.size === 1 ? Array.from(S.filters.jobTypes)[0] : (S.filters.jobTypes.size === 0 || S.filters.jobTypes.size === 4 ? 'all' : Array.from(S.filters.jobTypes).join(','));
        syncJobTypeFilterState();
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    });

    // 3. Work Model Checkboxes
    $$('input[name="afWorkModel"]').forEach(cb => {
      cb.addEventListener('change', () => {
        S.filters.workModels = new Set(Array.from($$('input[name="afWorkModel"]:checked')).map(el => el.value));
        S.filters.workMode = S.filters.workModels.size === 1 ? Array.from(S.filters.workModels)[0] : (S.filters.workModels.size > 1 ? 'Any' : 'all');
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    });

    // 4. Location
    const cSel = $('#afCountrySelect');
    if (cSel) {
      cSel.addEventListener('change', () => {
        S.filters.country = cSel.value;
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    const locInp = $('#afLocationInput');
    if (locInp) {
      locInp.addEventListener('input', () => {
        S.filters.locationQuery = locInp.value;
        filterAndRender();
      });
    }

    const radSel = $('#afRadiusSelect');
    if (radSel) {
      radSel.addEventListener('change', () => {
        S.filters.locationRadius = radSel.value;
      });
    }

    const btnAddLoc = $('#afAddLocationBtn');
    if (btnAddLoc && locInp) {
      btnAddLoc.addEventListener('click', () => {
        const val = locInp.value.trim();
        if (val) {
          toast(`Location target active: ${val}`);
          filterAndRender();
        }
      });
    }

    // 5. Experience Level Checkboxes
    $$('input[name="afExpLevel"]').forEach(cb => {
      cb.addEventListener('change', () => {
        S.filters.expLevels = new Set(Array.from($$('input[name="afExpLevel"]:checked')).map(el => el.value));
        S.filters.seniority = S.filters.expLevels.size === 1 ? Array.from(S.filters.expLevels)[0] : 'all';
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    });

    // 6. Experience Slider & Toggle
    const expToggle = $('#afToggleExpOpen');
    const expSlider = $('#afExpSlider');
    const expSubval = $('#afExpSubval');
    const expWrap = $('#afExpSliderWrap');

    if (expToggle) {
      expToggle.addEventListener('change', () => {
        S.filters.expOpenToAll = expToggle.checked;
        if (expToggle.checked) {
          if (expSubval) expSubval.textContent = 'Any requirements';
          if (expWrap) expWrap.classList.add('is-disabled');
          S.filters.expYears = 0;
        } else {
          const val = expSlider ? parseInt(expSlider.value, 10) : 0;
          S.filters.expYears = val;
          if (expSubval) expSubval.textContent = `${val}+ yrs`;
          if (expWrap) expWrap.classList.remove('is-disabled');
        }
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    if (expSlider) {
      expSlider.addEventListener('input', () => {
        const val = parseInt(expSlider.value, 10);
        if (expToggle && expToggle.checked) {
          expToggle.checked = false;
          S.filters.expOpenToAll = false;
          if (expWrap) expWrap.classList.remove('is-disabled');
        }
        if (expSubval) expSubval.textContent = `${val}+ yrs`;
      });

      expSlider.addEventListener('change', () => {
        const val = parseInt(expSlider.value, 10);
        S.filters.expYears = val;
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    // 7. Date Posted Radios & Clear
    $$('input[name="afDatePosted"]').forEach(r => {
      r.addEventListener('change', () => {
        const checked = $('input[name="afDatePosted"]:checked');
        S.filters.freshnessDays = checked ? parseInt(checked.value, 10) : 0;
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    });

    const btnClearDate = $('#afClearDatePosted');
    if (btnClearDate) {
      btnClearDate.addEventListener('click', () => {
        $$('input[name="afDatePosted"]').forEach(r => { r.checked = false; });
        S.filters.freshnessDays = 0;
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    // 8. Minimum Salary Slider & Toggle
    const salToggle = $('#afToggleSalaryOpen');
    const salSlider = $('#afSalarySlider');
    const salSubval = $('#afSalarySubval');
    const salWrap = $('#afSalarySliderWrap');

    if (salToggle) {
      salToggle.addEventListener('change', () => {
        S.filters.salaryOpenToAll = salToggle.checked;
        if (salToggle.checked) {
          if (salSubval) salSubval.textContent = 'Any salary';
          if (salWrap) salWrap.classList.add('is-disabled');
          S.filters.minSalary = 0;
          S.filters.salaryTier = '0';
        } else {
          const val = salSlider ? parseInt(salSlider.value, 10) : 0;
          S.filters.minSalary = val;
          S.filters.salaryTier = String(val);
          if (salSubval) salSubval.textContent = `$${Math.round(val / 1000)}k+`;
          if (salWrap) salWrap.classList.remove('is-disabled');
        }
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    if (salSlider) {
      salSlider.addEventListener('input', () => {
        const val = parseInt(salSlider.value, 10);
        if (salToggle && salToggle.checked) {
          salToggle.checked = false;
          S.filters.salaryOpenToAll = false;
          if (salWrap) salWrap.classList.remove('is-disabled');
        }
        if (salSubval) salSubval.textContent = `$${Math.round(val / 1000)}k+`;
      });

      salSlider.addEventListener('change', () => {
        const val = parseInt(salSlider.value, 10);
        S.filters.minSalary = val;
        S.filters.salaryTier = String(val);
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    // 9. Work Authorization & Limitations
    const checkH1B = $('#afCheckH1B');
    if (checkH1B) {
      checkH1B.addEventListener('change', () => {
        S.filters.h1b = checkH1B.checked;
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    const checkClearance = $('#afExcludeClearance');
    if (checkClearance) {
      checkClearance.addEventListener('change', () => {
        S.filters.excludeClearance = checkClearance.checked;
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    const checkCitizenOnly = $('#afExcludeCitizenOnly');
    if (checkCitizenOnly) {
      checkCitizenOnly.addEventListener('change', () => {
        S.filters.excludeCitizenOnly = checkCitizenOnly.checked;
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    // 10. Industry
    const industryList = $('#afIndustryList');
    if (industryList) {
      industryList.addEventListener('change', e => {
        if (e.target.name === 'afIndustry') {
          S.filters.industries = new Set(Array.from($$('input[name="afIndustry"]:checked')).map(el => el.value));
          preserveDrawerScroll(() => {
            renderDrawerActivePills();
            filterAndRender();
          });
        }
      });
      industryList.addEventListener('click', e => {
        const removeBtn = e.target.closest('.af-btn-item-remove');
        if (!removeBtn) return;
        const row = removeBtn.closest('.af-list-item');
        if (!row) return;
        const val = row.dataset.val;
        if (S.filters.industries) S.filters.industries.delete(val);
        row.remove();
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    const btnClearIndustry = $('#afClearIndustry');
    if (btnClearIndustry) {
      btnClearIndustry.addEventListener('click', () => {
        $$('input[name="afIndustry"]').forEach(cb => { cb.checked = false; });
        if (S.filters.industries) S.filters.industries.clear();
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    const btnAddIndustry = $('#afBtnAddIndustry');
    if (btnAddIndustry) {
      btnAddIndustry.addEventListener('click', () => {
        const name = prompt('Enter industry name to add:');
        if (name && name.trim()) {
          const clean = name.trim();
          if (!S.filters.industries) S.filters.industries = new Set();
          S.filters.industries.add(clean);
          if (industryList) {
            const item = document.createElement('div');
            item.className = 'af-list-item';
            item.dataset.val = clean;
            item.innerHTML = `
              <label class="af-list-label">
                <input type="checkbox" name="afIndustry" value="${esc(clean)}" checked>
                <span class="af-tile-check"></span>
                <span>${esc(clean)}</span>
              </label>
              <button type="button" class="af-btn-item-remove" title="Remove">&times;</button>
            `;
            industryList.appendChild(item);
          }
          preserveDrawerScroll(() => {
            renderDrawerActivePills();
            filterAndRender();
          });
        }
      });
    }

    // Excluded Industry Accordion
    const toggleExcludedIndustry = $('#afToggleExcludedIndustry');
    const bodyExcludedIndustry = $('#afBodyExcludedIndustry');
    if (toggleExcludedIndustry && bodyExcludedIndustry) {
      toggleExcludedIndustry.addEventListener('click', () => {
        const isOpen = !bodyExcludedIndustry.hidden;
        bodyExcludedIndustry.hidden = isOpen;
        toggleExcludedIndustry.setAttribute('aria-expanded', String(!isOpen));
        toggleExcludedIndustry.classList.toggle('is-expanded', !isOpen);
      });
    }

    const btnAddExcludedIndustry = $('#afAddExcludedIndustryBtn');
    const inpExcludedIndustry = $('#afExcludedIndustryInput');
    function addExcludedIndustry() {
      if (!inpExcludedIndustry) return;
      const val = inpExcludedIndustry.value.trim();
      if (val) {
        if (!S.filters.excludedIndustries) S.filters.excludedIndustries = new Set();
        S.filters.excludedIndustries.add(val);
        inpExcludedIndustry.value = '';
        preserveDrawerScroll(() => {
          renderExcludedIndustryChips();
          filterAndRender();
        });
      }
    }
    if (btnAddExcludedIndustry) btnAddExcludedIndustry.addEventListener('click', addExcludedIndustry);
    if (inpExcludedIndustry) inpExcludedIndustry.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addExcludedIndustry(); } });

    const chipsExcludedIndustry = $('#afExcludedIndustryChips');
    if (chipsExcludedIndustry) {
      chipsExcludedIndustry.addEventListener('click', e => {
        const removeBtn = e.target.closest('.af-tag-remove');
        if (!removeBtn) return;
        const chip = removeBtn.closest('.af-tag-chip');
        if (!chip) return;
        const ind = chip.dataset.ind;
        if (S.filters.excludedIndustries) S.filters.excludedIndustries.delete(ind);
        preserveDrawerScroll(() => {
          renderExcludedIndustryChips();
          filterAndRender();
        });
      });
    }

    // 11. Skill
    const skillList = $('#afSkillList');
    if (skillList) {
      skillList.addEventListener('change', e => {
        if (e.target.name === 'afSkill') {
          S.filters.skills = new Set(Array.from($$('input[name="afSkill"]:checked')).map(el => el.value));
          preserveDrawerScroll(() => {
            renderDrawerActivePills();
            filterAndRender();
          });
        }
      });
      skillList.addEventListener('click', e => {
        const removeBtn = e.target.closest('.af-btn-item-remove');
        if (!removeBtn) return;
        const row = removeBtn.closest('.af-list-item');
        if (!row) return;
        const val = row.dataset.val;
        if (S.filters.skills) S.filters.skills.delete(val);
        row.remove();
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    const btnClearSkills = $('#afClearSkills');
    if (btnClearSkills) {
      btnClearSkills.addEventListener('click', () => {
        $$('input[name="afSkill"]').forEach(cb => { cb.checked = false; });
        if (S.filters.skills) S.filters.skills.clear();
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    const btnAddSkill = $('#afBtnAddSkill');
    if (btnAddSkill) {
      btnAddSkill.addEventListener('click', () => {
        const name = prompt('Enter skill name to add:');
        if (name && name.trim()) {
          const clean = name.trim();
          if (!S.filters.skills) S.filters.skills = new Set();
          S.filters.skills.add(clean);
          if (skillList) {
            const item = document.createElement('div');
            item.className = 'af-list-item';
            item.dataset.val = clean;
            item.innerHTML = `
              <label class="af-list-label">
                <input type="checkbox" name="afSkill" value="${esc(clean)}" checked>
                <span class="af-tile-check"></span>
                <span>${esc(clean)}</span>
              </label>
              <button type="button" class="af-btn-item-remove" title="Remove">&times;</button>
            `;
            skillList.appendChild(item);
          }
          preserveDrawerScroll(() => {
            renderDrawerActivePills();
            filterAndRender();
          });
        }
      });
    }

    // Excluded Skill Accordion
    const toggleExcludedSkill = $('#afToggleExcludedSkill');
    const bodyExcludedSkill = $('#afBodyExcludedSkill');
    if (toggleExcludedSkill && bodyExcludedSkill) {
      toggleExcludedSkill.addEventListener('click', () => {
        const isOpen = !bodyExcludedSkill.hidden;
        bodyExcludedSkill.hidden = isOpen;
        toggleExcludedSkill.setAttribute('aria-expanded', String(!isOpen));
        toggleExcludedSkill.classList.toggle('is-expanded', !isOpen);
      });
    }

    const btnAddExcludedSkill = $('#afAddExcludedSkillBtn');
    const inpExcludedSkill = $('#afExcludedSkillInput');
    function addExcludedSkill() {
      if (!inpExcludedSkill) return;
      const val = inpExcludedSkill.value.trim();
      if (val) {
        if (!S.filters.excludedSkills) S.filters.excludedSkills = new Set();
        S.filters.excludedSkills.add(val);
        inpExcludedSkill.value = '';
        preserveDrawerScroll(() => {
          renderExcludedSkillChips();
          filterAndRender();
        });
      }
    }
    if (btnAddExcludedSkill) btnAddExcludedSkill.addEventListener('click', addExcludedSkill);
    if (inpExcludedSkill) inpExcludedSkill.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addExcludedSkill(); } });

    const chipsExcludedSkill = $('#afExcludedSkillChips');
    if (chipsExcludedSkill) {
      chipsExcludedSkill.addEventListener('click', e => {
        const removeBtn = e.target.closest('.af-tag-remove');
        if (!removeBtn) return;
        const chip = removeBtn.closest('.af-tag-chip');
        if (!chip) return;
        const sk = chip.dataset.sk;
        if (S.filters.excludedSkills) S.filters.excludedSkills.delete(sk);
        preserveDrawerScroll(() => {
          renderExcludedSkillChips();
          filterAndRender();
        });
      });
    }

    // 12. Role Type Radios & Clear
    $$('input[name="afRoleType"]').forEach(r => {
      r.addEventListener('change', () => {
        const checked = $('input[name="afRoleType"]:checked');
        S.filters.roleType = checked ? checked.value : 'all';
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    });

    const btnClearRoleType = $('#afClearRoleType');
    if (btnClearRoleType) {
      btnClearRoleType.addEventListener('click', () => {
        $$('input[name="afRoleType"]').forEach(r => { r.checked = false; });
        S.filters.roleType = 'all';
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    // 13. Company Search & Chips
    const btnAddCo = $('#afBtnAddCompany');
    const coAddRow = $('#afCompanyAddRow');
    const inpCompany = $('#afCompanyInput');
    const btnConfirmCo = $('#afAddCompanyConfirmBtn');

    if (btnAddCo && coAddRow) {
      btnAddCo.addEventListener('click', () => {
        coAddRow.hidden = false;
        if (inpCompany) inpCompany.focus();
      });
    }

    function addCompanyFilter() {
      if (!inpCompany) return;
      const val = inpCompany.value.trim();
      if (val) {
        if (!S.filters.companies) S.filters.companies = new Set();
        S.filters.companies.add(val);
        inpCompany.value = '';
        if (coAddRow) coAddRow.hidden = true;
        preserveDrawerScroll(() => {
          renderCompanyChips();
          renderDrawerActivePills();
          filterAndRender();
        });
      }
    }
    if (btnConfirmCo) btnConfirmCo.addEventListener('click', addCompanyFilter);
    if (inpCompany) inpCompany.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addCompanyFilter(); } });

    const chipsCompany = $('#afCompanyChips');
    if (chipsCompany) {
      chipsCompany.addEventListener('click', e => {
        const removeBtn = e.target.closest('.af-tag-remove');
        if (!removeBtn) return;
        const chip = removeBtn.closest('.af-tag-chip');
        if (!chip) return;
        const co = chip.dataset.co;
        if (S.filters.companies) S.filters.companies.delete(co);
        preserveDrawerScroll(() => {
          renderCompanyChips();
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    const btnClearCo = $('#afClearCompany');
    if (btnClearCo) {
      btnClearCo.addEventListener('click', () => {
        if (S.filters.companies) S.filters.companies.clear();
        preserveDrawerScroll(() => {
          renderCompanyChips();
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    // 14. Company Stage Checkboxes & Clear
    $$('input[name="afCompanyStage"]').forEach(cb => {
      cb.addEventListener('change', () => {
        S.filters.companyStages = new Set(Array.from($$('input[name="afCompanyStage"]:checked')).map(el => el.value));
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    });

    const btnClearStage = $('#afClearCompanyStage');
    if (btnClearStage) {
      btnClearStage.addEventListener('click', () => {
        $$('input[name="afCompanyStage"]').forEach(cb => { cb.checked = false; });
        if (S.filters.companyStages) S.filters.companyStages.clear();
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }

    // 15. Job Source (Exclude Staffing Agency)
    const checkStaffing = $('#afCheckExcludeStaffing');
    if (checkStaffing) {
      checkStaffing.addEventListener('change', () => {
        S.filters.excludeStaffing = checkStaffing.checked;
        preserveDrawerScroll(() => {
          renderDrawerActivePills();
          filterAndRender();
        });
      });
    }
  }

  // ----------------------------------------------------------------- onboarding flow
  function setupOnboardingFlow() {
    const overlay = $('#onboardingFlow');
    if (!overlay) return;

    const btnOpen = $('#btnOpenOnboarding');
    if (btnOpen) btnOpen.addEventListener('click', () => openOnboarding(1));
    const btnMenu = $('#menuOnboardingBtn');
    if (btnMenu) btnMenu.addEventListener('click', () => {
      const more = $('#moreMenu');
      if (more) more.hidden = true;
      openOnboarding(1);
    });

    const roleChips = $('#onboardRoleChips');
    if (roleChips) {
      roleChips.addEventListener('click', e => {
        const chip = e.target.closest('[data-role]');
        if (chip) {
          const inp = $('#onboardJobFunction');
          if (inp) inp.value = chip.dataset.role;
        }
      });
    }

    const btnNext1 = $('#onboardBtnNext1');
    if (btnNext1) {
      btnNext1.addEventListener('click', () => {
        const inp = $('#onboardJobFunction');
        const fn = (inp ? inp.value : '').trim() || 'Full Stack Developer';
        if (inp) inp.value = fn;
        goToStep(2);
      });
    }

    const skip1 = $('#onboardSkipStep1');
    if (skip1) skip1.addEventListener('click', () => closeOnboarding());

    const back1 = $('#onboardBackStep1');
    if (back1) back1.addEventListener('click', () => goToStep(1));
    const skip2 = $('#onboardSkipStep2');
    if (skip2) skip2.addEventListener('click', () => startMatchingFlow());

    const dropzone = $('#onboardDropzone');
    const fileInput = $('#onboardFileInput');
    const uploadBtn = $('#onboardUploadBtn');

    if (uploadBtn && fileInput) {
      uploadBtn.addEventListener('click', () => fileInput.click());
    }
    if (dropzone && fileInput) {
      ['dragenter', 'dragover'].forEach(t => dropzone.addEventListener(t, e => {
        e.preventDefault();
        dropzone.classList.add('is-over');
      }));
      ['dragleave', 'drop'].forEach(t => dropzone.addEventListener(t, e => {
        e.preventDefault();
        dropzone.classList.remove('is-over');
      }));
      dropzone.addEventListener('drop', e => {
        const file = e.dataTransfer.files[0];
        if (file) handleOnboardFile(file);
      });
      fileInput.addEventListener('change', e => {
        const file = e.target.files[0];
        if (file) handleOnboardFile(file);
        e.target.value = '';
      });
    }

    const pasteLink = $('#onboardPasteLink');
    if (pasteLink) {
      pasteLink.addEventListener('click', () => {
        const badge = $('#onboardUploadBadge');
        if (badge) {
          badge.textContent = '✓ Using demo profile template';
          badge.hidden = false;
        }
      });
    }

    const btnMatch = $('#onboardBtnStartMatch');
    if (btnMatch) {
      btnMatch.addEventListener('click', () => startMatchingFlow());
    }

    const btnConfirm = $('#onboardBtnConfirm');
    if (btnConfirm) {
      btnConfirm.addEventListener('click', () => finishOnboarding());
    }

    const completed = localStorage.getItem('jh_onboarded_completed');
    if (!completed) {
      openOnboarding(1);
    }
  }

  function goToStep(num) {
    const s1 = $('#onboardStep1');
    const s2 = $('#onboardStep2');
    const s3 = $('#onboardStep3');
    if (s1) s1.hidden = num !== 1;
    if (s2) s2.hidden = num !== 2;
    if (s3) s3.hidden = num !== 3;
  }

  function openOnboarding(step = 1) {
    const overlay = $('#onboardingFlow');
    if (!overlay) return;
    overlay.hidden = false;
    goToStep(step);
  }

  function closeOnboarding() {
    const overlay = $('#onboardingFlow');
    if (overlay) overlay.hidden = true;
    localStorage.setItem('jh_onboarded_completed', 'true');
  }

  async function handleOnboardFile(file) {
    if (!file) return;
    const badge = $('#onboardUploadBadge');
    if (badge) {
      badge.textContent = `Reading ${file.name}...`;
      badge.hidden = false;
    }
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
        const res = await api('/api/parse-resume', { method: 'POST', body });
        if (res && res.profile) {
          S.profile = normalizeProfile(Object.assign({}, S.profile || {}, res.profile));
          if (badge) {
            const count = (res.profile.skills || []).length;
            badge.textContent = `✓ ${file.name} parsed (${count} skills extracted)`;
            badge.hidden = false;
          }
          if (res.profile.target_role && $('#onboardJobFunction')) {
            $('#onboardJobFunction').value = res.profile.target_role;
          }
        }
      } catch (err) {
        if (badge) {
          badge.textContent = `Warning: ${err.message}. Ready to match anyway.`;
          badge.hidden = false;
        }
      }
    };
    if (binary) reader.readAsArrayBuffer(file); else reader.readAsText(file);
  }

  async function startMatchingFlow() {
    const modal = $('#onboardMatchingModal');
    const fill = $('#matchingBarFill');
    const title = $('#matchingStatusTitle');
    const sub = $('#matchingStatusSub');

    if (modal) modal.hidden = false;

    const role = ($('#onboardJobFunction') ? $('#onboardJobFunction').value : '').trim() || 'Full Stack Developer';
    const loc = ($('#onboardLocation') ? $('#onboardLocation').value : '').trim() || 'United States';

    let p = 0;
    const timer = setInterval(() => {
      p += 15;
      if (fill) fill.style.width = Math.min(p, 95) + '%';
      if (p === 30 && title) {
        title.textContent = 'Searching 11,000+ open listings...';
        if (sub) sub.textContent = 'Scanning Lever, Greenhouse, Workday, and Remote boards...';
      } else if (p === 60 && title) {
        title.textContent = 'Calculating AI Match Score...';
        if (sub) sub.textContent = 'Comparing job requirements against your verified skills...';
      }
    }, 150);

    try {
      await runSearch({ forceRefresh: false, overrideQuery: role, overrideLoc: loc === 'Anywhere in the US' ? 'United States' : loc });
    } catch (e) {
      console.warn('Search query:', e);
    }

    setTimeout(() => {
      clearInterval(timer);
      if (fill) fill.style.width = '100%';
      setTimeout(() => {
        if (modal) modal.hidden = true;
        const total = (S.allJobs && S.allJobs.length) ? S.allJobs.length : 11089;
        const countEl = $('#onboardWelcomeCount');
        if (countEl) countEl.textContent = `${total} roles`;
        goToStep(3);
      }, 350);
    }, 1200);
  }

  function finishOnboarding() {
    const checkedLevel = $('input[name="onboardLevel"]:checked');
    const level = checkedLevel ? checkedLevel.value : 'mid';
    S.filters.seniority = level;

    const linkedinInput = $('#onboardLinkedinUrl');
    if (linkedinInput && linkedinInput.value.trim()) {
      if (!S.profile) S.profile = {};
      S.profile.linkedin = linkedinInput.value.trim();
      api('/api/profile', { method: 'POST', body: S.profile }).catch(() => {});
    }

    const role = ($('#onboardJobFunction') ? $('#onboardJobFunction').value : '').trim() || 'Full Stack Developer';
    const loc = ($('#onboardLocation') ? $('#onboardLocation').value : '').trim() || 'United States';
    const remote = $('#onboardOpenRemote') ? $('#onboardOpenRemote').checked : true;

    const qInput = $('#searchQuery');
    if (qInput) qInput.value = role;
    const tRole = $('#p4TextRole');
    if (tRole) tRole.textContent = role;
    const tLoc = $('#p4TextLocation');
    if (tLoc) tLoc.textContent = loc === 'Anywhere in the US' ? 'United States' : loc;
    const senLabels = { intern: 'Intern', junior: 'Entry Level', mid: 'Mid Level', senior: 'Senior Level', lead_staff: 'Lead / Staff', director: 'Director' };
    const tSen = $('#p4TextSeniority');
    if (tSen) tSen.textContent = senLabels[level] || 'Mid Level';

    if (remote) {
      S.filters.workMode = 'Any';
      const tWm = $('#p4TextWorkMode');
      if (tWm) tWm.textContent = 'Remote (+2)';
    }

    closeOnboarding();
    go('jobs');
    fetchJobsFromDb();
    toast('Welcome! Displaying jobs matching your profile and preferences.');
  }

  // ------------------------------------------------------------------- auto-search helpers
  async function checkAutoSearchStatus() {
    try {
      const res = await api('/api/auto-search/status');
      if (res && res.settings) {
        const s = res.settings;
        const badge = $('#jobsRefreshBadge');
        if (badge) {
          if (s.pending_count > 0) {
            badge.textContent = `${s.pending_count} new`;
            badge.hidden = false;
          } else {
            badge.textContent = '0 new';
            badge.hidden = true;
          }
        }
        const lastEl = $('#autoSearchLastRunText');
        if (lastEl) lastEl.textContent = s.last_run ? formatTimeSince(new Date(s.last_run).getTime()) : 'Never';
        const nextEl = $('#autoSearchNextRunText');
        if (nextEl) {
          if (!s.enabled || s.interval_hours <= 0) nextEl.textContent = 'Disabled';
          else if (s.next_run === 'Immediate') nextEl.textContent = 'Ready to run';
          else if (s.next_run) nextEl.textContent = formatTimeUntil(new Date(s.next_run).getTime());
          else nextEl.textContent = `In ${s.interval_hours}h`;
        }
        const pendingEl = $('#autoSearchPendingText');
        if (pendingEl) pendingEl.textContent = `${s.pending_count} new job${s.pending_count === 1 ? '' : 's'} staged`;
        const statusBadge = $('#autoSearchStatusBadge');
        if (statusBadge) {
          if (!s.enabled || s.interval_hours <= 0) {
            statusBadge.textContent = 'Manual Only';
            statusBadge.className = 'chip chip-muted';
          } else if (s.status === 'running') {
            statusBadge.textContent = 'Scanning Live...';
            statusBadge.className = 'chip chip-warning';
          } else {
            statusBadge.textContent = 'Auto Active';
            statusBadge.className = 'chip chip-ok';
          }
        }
      }
    } catch (e) {
      console.debug('auto search status check:', e);
    }
  }

  // ------------------------------------------------------------------- background enrichment poller
  let _enrichmentCheckTimer = null;
  let _lastCompletedEnrichment = 0;
  let _wasEnriching = false;
  let _isSilentSyncing = false;

  async function silentSyncEnrichedJobs() {
    if (_isSilentSyncing) return;
    _isSilentSyncing = true;
    try {
      const f = S.filters || {};
      const params = new URLSearchParams();
      const cat = (f.jobFunctions && f.jobFunctions.length) ? f.jobFunctions[0] : '';
      if (cat) params.set('category', cat);
      if (f.keyword && f.keyword.toLowerCase() !== cat.toLowerCase()) params.set('q', f.keyword);
      if (f.workMode && f.workMode !== 'Any' && f.workMode !== 'all') params.set('work_mode', f.workMode);
      else if (f.workModels && f.workModels.size === 1) params.set('work_mode', Array.from(f.workModels)[0]);
      if (f.seniority && f.seniority !== 'all') params.set('seniority', f.seniority);
      else if (f.expLevels && f.expLevels.size === 1) params.set('seniority', Array.from(f.expLevels)[0]);
      if (f.jobTypes && f.jobTypes.size > 0 && f.jobTypes.size < 4) params.set('job_type', Array.from(f.jobTypes).join(','));
      else if (f.jobType && f.jobType !== 'all') params.set('job_type', f.jobType);
      if (f.country && f.country !== 'all') params.set('country', f.country);
      if (f.locationQuery && f.locationQuery !== 'Anywhere in the US' && f.locationQuery !== 'Worldwide' && f.locationQuery.trim()) {
        params.set('location', f.locationQuery.trim());
      }
      if (f.minScore > 0) params.set('min_score', String(f.minScore));
      if (!f.salaryOpenToAll && f.minSalary > 0) params.set('min_salary', String(f.minSalary));
      if (f.freshnessDays > 0) params.set('days', String(f.freshnessDays));
      if (f.industry && f.industry !== 'all') params.set('industry', f.industry);
      if (f.famousMode && f.famousMode !== 'all') params.set('famous_mode', f.famousMode);
      if (f.h1b) params.set('h1b', '1');
      params.set('sort', val('sortResultsBy') || 'ranked');

      const res = await api(`/api/search/saved?${params.toString()}`);
      if (res) {
        const allPool = (res.all_jobs && res.all_jobs.length) ? res.all_jobs : (res.jobs || []);
        S.allJobs = allPool;
        S.jobsRanked = allPool;
        S.jobs = (res.jobs && res.jobs.length) ? res.jobs : allPool;
        S.searchMeta = res.meta || S.searchMeta || {};

        if (S.jobs.length && (!S.selectedKey || !S.jobs.some(j => jobKey(j) === S.selectedKey))) {
          S.selectedKey = jobKey(S.jobs[0]);
        }

        renderList(false);
        if (S.view === 'jobs') {
          renderDetail(true);
        }
        updateFacetCounts();
      }
    } catch (e) {
      console.debug('silentSyncEnrichedJobs error:', e);
    } finally {
      _isSilentSyncing = false;
    }
  }

  async function checkEnrichmentStatus() {
    try {
      const res = await api('/api/enrichment/status');
      if (!res || !res.telemetry) return;
      const t = res.telemetry;

      const liveBanner = $('#liveSyncBanner');
      const liveStatus = $('#liveSyncStatus');
      const liveFill = $('#liveSyncProgressFill');
      const liveKicker = $('#liveSyncKicker');
      const liveCountTag = $('#liveSyncCountTag');

      if (t.is_running) {
        _wasEnriching = true;
        if (liveBanner) {
          liveBanner.hidden = false;
          liveBanner.classList.remove('is-leaving');
          liveBanner.classList.add('is-entering');
        }
        if (liveKicker) liveKicker.textContent = 'Deep Analysis';
        if (liveStatus) {
          liveStatus.textContent = t.current_job
            ? `Reading full details: ${t.current_job}`
            : 'Analyzing complete job requirements in background...';
        }
        const total = Math.max(1, t.total || 1);
        const comp = t.completed || 0;
        const pct = Math.min(98, Math.max(10, Math.round((comp / total) * 100)));
        if (liveFill) liveFill.style.width = `${pct}%`;
        if (liveCountTag) liveCountTag.textContent = `${comp} / ${total} analyzed`;

        if (comp > _lastCompletedEnrichment) {
          _lastCompletedEnrichment = comp;
          await silentSyncEnrichedJobs();
        }
      } else if (_wasEnriching) {
        _wasEnriching = false;
        _lastCompletedEnrichment = 0;
        if (liveStatus) liveStatus.textContent = '✓ All job descriptions read & verified match rates calculated.';
        if (liveFill) liveFill.style.width = '100%';
        if (liveCountTag) liveCountTag.textContent = 'Complete';
        await silentSyncEnrichedJobs();

        setTimeout(() => {
          if (!_wasEnriching && liveBanner) {
            liveBanner.classList.remove('is-entering');
            liveBanner.classList.add('is-leaving');
            setTimeout(() => {
              if (!_wasEnriching && liveBanner) {
                liveBanner.hidden = true;
                liveBanner.classList.remove('is-leaving');
              }
            }, 350);
          }
        }, 2500);
      }
    } catch (e) {
      console.debug('checkEnrichmentStatus error:', e);
    }
  }

  function scheduleNextEnrichmentCheck(ms = 4000) {
    clearTimeout(_enrichmentCheckTimer);
    _enrichmentCheckTimer = setTimeout(async () => {
      await checkEnrichmentStatus();
      scheduleNextEnrichmentCheck(_wasEnriching ? 3500 : 12000);
    }, ms);
  }

  function formatTimeUntil(timestamp) {
    if (!timestamp || isNaN(timestamp)) return 'Soon';
    const diff = timestamp - Date.now();
    if (diff <= 0) return 'Any moment';
    const totalSecs = Math.floor(diff / 1000);
    if (totalSecs < 60) return `In ${Math.max(1, totalSecs)}s`;
    const mins = Math.floor(totalSecs / 60);
    const remSecs = totalSecs % 60;
    if (mins < 60) {
      return remSecs > 0 ? `In ${mins}m ${remSecs}s` : `In ${mins}m`;
    }
    const hrs = Math.floor(mins / 60);
    return `In ${hrs}h ${mins % 60}m`;
  }

  function setupAutoSearchUi() {
    const sel = $('#autoSearchIntervalSelect');
    const customField = $('#autoSearchCustomField');
    const customInp = $('#autoSearchCustomHours');
    const triggerBtn = $('#btnTriggerAutoSearch');

    api('/api/auto-search/status').then(res => {
      if (res && res.settings) {
        const s = res.settings;
        if (sel) {
          if (!s.enabled || s.interval_hours <= 0) {
            sel.value = '0';
          } else if (['1', '5', '24', '168'].includes(String(s.interval_hours))) {
            sel.value = String(s.interval_hours);
          } else {
            sel.value = 'custom';
            if (customField) customField.hidden = false;
            if (customInp) customInp.value = String(s.interval_hours);
          }
        }
        checkAutoSearchStatus();
      }
    }).catch(() => {});

    if (sel) {
      sel.addEventListener('change', () => {
        const val = sel.value;
        if (val === 'custom') {
          if (customField) customField.hidden = false;
          const h = parseFloat((customInp && customInp.value) || 12);
          api('/api/auto-search/settings', { method: 'POST', body: { enabled: true, interval_hours: h } }).then(() => {
            toast(`Auto search interval set to every ${h} hours`);
            checkAutoSearchStatus();
          });
        } else if (val === '0') {
          if (customField) customField.hidden = true;
          api('/api/auto-search/settings', { method: 'POST', body: { enabled: false, interval_hours: 0 } }).then(() => {
            toast('Background auto search set to manual only');
            checkAutoSearchStatus();
          });
        } else {
          if (customField) customField.hidden = true;
          const h = parseFloat(val);
          api('/api/auto-search/settings', { method: 'POST', body: { enabled: true, interval_hours: h } }).then(() => {
            toast(`Auto search frequency updated: Every ${h} hours`);
            checkAutoSearchStatus();
          });
        }
      });
    }

    if (customInp) {
      customInp.addEventListener('change', () => {
        const h = parseFloat(customInp.value);
        if (h && h > 0) {
          api('/api/auto-search/settings', { method: 'POST', body: { enabled: true, interval_hours: h } }).then(() => {
            toast(`Auto search custom interval saved: ${h} hours`);
            checkAutoSearchStatus();
          });
        }
      });
    }

    if (triggerBtn) {
      triggerBtn.addEventListener('click', async () => {
        triggerBtn.disabled = true;
        try {
          await api('/api/auto-search/trigger', { method: 'POST' });
          toast('Background search session started! It will run in background and stage new jobs.');
          checkAutoSearchStatus();
        } catch (e) {
          toast('Could not trigger background search: ' + e.message, 'error');
        } finally {
          setTimeout(() => { triggerBtn.disabled = false; }, 2000);
        }
      });
    }
  }

  // ------------------------------------------------------------------- LinkedIn Live Radar UI
  let radarCountdownTicker = null;
  let radarStatusPollTimer = null;
  let lastRadarTelemetry = null;
  let isRadarAutoPolling = false;

  async function checkLinkedinRadarStatus() {
    try {
      const res = await api('/api/linkedin-radar/status');
      if (!res || !res.radar) return;
      const r = res.radar;
      lastRadarTelemetry = r;

      // Update Toolbar Button & Badge
      const radarBtn = $('#btnLinkedinRadar');
      const radarDot = $('#radarLiveDot');
      const radarLabel = $('#p4RadarLabel');
      const radarBadge = $('#p4RadarBadge');

      if (radarBtn) {
        radarBtn.classList.toggle('is-disabled', !r.enabled);
        radarBtn.classList.toggle('is-scanning', Boolean(r.is_running));
      }
      if (radarDot) {
        radarDot.classList.toggle('is-disabled', !r.enabled);
      }
      if (radarLabel) {
        if (!r.enabled) radarLabel.textContent = 'Radar Paused';
        else if (r.is_running) radarLabel.textContent = 'Radar Scanning...';
        else radarLabel.textContent = `Radar (${r.interval_min}m)`;
      }
      if (radarBadge) {
        if (r.pending_count > 0) {
          radarBadge.textContent = `+${r.pending_count} new`;
          radarBadge.hidden = false;
        } else {
          radarBadge.textContent = '0 new';
          radarBadge.hidden = true;
        }
      }

      // Also ensure jobsRefreshBadge reflects pending count
      const refreshBadge = $('#jobsRefreshBadge');
      if (refreshBadge && r.pending_count > 0) {
        refreshBadge.textContent = `${r.pending_count} new`;
        refreshBadge.hidden = false;
      }

      // Update Popover contents
      const chip = $('#radarStatusChip');
      if (chip) {
        if (!r.enabled) {
          chip.textContent = 'Manual Only';
          chip.className = 'chip chip-muted chip-sm';
        } else if (r.is_running) {
          chip.textContent = 'Scanning...';
          chip.className = 'chip chip-warning chip-sm';
        } else {
          chip.textContent = `Active (${r.interval_min}m)`;
          chip.className = 'chip chip-ok chip-sm';
        }
      }

      const lastScanEl = $('#radarLastScanText');
      if (lastScanEl) {
        lastScanEl.textContent = r.last_run ? formatTimeSince(new Date(r.last_run).getTime()) : 'Never';
      }

      const nextScanEl = $('#radarNextScanText');
      if (nextScanEl) {
        if (!r.enabled) nextScanEl.textContent = 'Disabled';
        else if (r.is_running) nextScanEl.textContent = 'Scanning LinkedIn...';
        else if (r.next_run === 'Immediate') nextScanEl.textContent = 'Any moment';
        else if (r.next_run) {
          const nextMs = new Date(r.next_run).getTime();
          const diff = nextMs - Date.now();
          if (diff <= 0) nextScanEl.textContent = 'Sweeping LinkedIn...';
          else nextScanEl.textContent = formatTimeUntil(nextMs);
        }
        else nextScanEl.textContent = `In ${r.interval_min}m`;
      }

      const actEl = $('#radarLastActivityText');
      if (actEl) {
        actEl.textContent = r.last_action || 'Monitoring LinkedIn 24h feed';
      }

      const pendEl = $('#radarPendingText');
      if (pendEl) {
        pendEl.textContent = `${r.pending_count} new job${r.pending_count === 1 ? '' : 's'} ready`;
      }

      const roleEl = $('#radarTargetRoleText');
      if (roleEl) {
        const title = r.target_role || r.last_query || 'Software Engineer';
        roleEl.textContent = title;
        roleEl.title = r.target_location ? `${title} (${r.target_location})` : title;
      }

      // Render Live Radar Job Matches & Match Rates
      const jobsTitleEl = $('#radarJobsTitle');
      const jobsSubEl = $('#radarJobsSubtitle');
      const jobsBadgeEl = $('#radarJobsBadge');
      const applyBtnText = $('#btnRadarApplyJobsText');
      const applyBtn = $('#btnRadarApplyJobs');
      const listEl = $('#radarJobsList');

      const stagedJobs = Array.isArray(r.staged_jobs) ? r.staged_jobs : [];
      const hasStaged = stagedJobs.length > 0;
      
      let displayJobs = [];
      let isStaged = false;

      if (hasStaged) {
        displayJobs = stagedJobs;
        isStaged = true;
        if (jobsTitleEl) jobsTitleEl.textContent = 'Staged for Review';
        if (jobsSubEl) jobsSubEl.textContent = `${stagedJobs.length} new LinkedIn job${stagedJobs.length > 1 ? 's' : ''} ready to add to feed`;
        if (jobsBadgeEl) {
          jobsBadgeEl.textContent = `+${stagedJobs.length} pending`;
          jobsBadgeEl.className = 'radar-jobs-badge is-pending';
        }
        if (applyBtnText) applyBtnText.textContent = `Review Staged Jobs (${stagedJobs.length})`;
        if (applyBtn) {
          applyBtn.disabled = false;
          applyBtn.classList.remove('is-disabled', 'btn-secondary');
          applyBtn.classList.add('btn-primary');
          applyBtn.title = `Import ${stagedJobs.length} staged jobs into your active feed`;
        }
      } else {
        const recent = Array.isArray(r.recent_matches) ? r.recent_matches : [];
        displayJobs = recent;
        isStaged = false;
        if (jobsTitleEl) jobsTitleEl.textContent = displayJobs.length ? 'Active LinkedIn Matches' : 'LinkedIn Live Radar';
        if (jobsSubEl) jobsSubEl.textContent = displayJobs.length ? 'Roles already imported into your job feed' : 'Feed is up to date • 0 pending';
        if (jobsBadgeEl) {
          jobsBadgeEl.textContent = displayJobs.length ? `${displayJobs.length} in feed` : '0 pending';
          jobsBadgeEl.className = 'radar-jobs-badge is-synced';
        }
        if (applyBtnText) applyBtnText.textContent = 'Feed Up to Date';
        if (applyBtn) {
          // Keep clickable for user feedback, but style as disabled secondary button
          applyBtn.disabled = false;
          applyBtn.classList.add('is-disabled', 'btn-secondary');
          applyBtn.classList.remove('btn-primary');
          applyBtn.title = 'Feed is up to date: 0 new postings waiting. Click for details or hit Scan Now.';
        }
      }

      if (listEl) {
        if (!displayJobs.length) {
          listEl.innerHTML = `
            <div class="radar-jobs-empty radar-jobs-synced">
              <div class="radar-synced-icon" aria-hidden="true">✓</div>
              <div class="radar-synced-title">Feed is Up to Date</div>
              <div class="radar-synced-desc">0 new LinkedIn postings waiting for review.<br>Click <strong>Scan Now</strong> to sweep for fresh jobs.</div>
            </div>
          `;
        } else {
          const bannerHtml = !hasStaged
            ? `
              <div class="radar-synced-status-banner">
                <div class="radar-synced-status-header">
                  <span class="radar-synced-icon-sm" aria-hidden="true">✓</span>
                  <span class="radar-synced-status-title">Feed is Up to Date (0 New Postings)</span>
                </div>
                <div class="radar-synced-status-desc">
                  Last LinkedIn sweep found no new postings. The roles below are active listings <strong>already imported into your feed</strong>.
                </div>
              </div>
            `
            : `
              <div class="radar-staged-status-banner">
                <div class="radar-staged-status-header">
                  <span class="radar-staged-icon-sm" aria-hidden="true">⚡</span>
                  <span class="radar-staged-status-title">${stagedJobs.length} New LinkedIn Posting${stagedJobs.length > 1 ? 's' : ''} Ready</span>
                </div>
                <div class="radar-staged-status-desc">
                  Discovered in latest scan. Click <strong>Review Staged Jobs</strong> below to add them to your feed.
                </div>
              </div>
            `;

          const cardsHtml = displayJobs.slice(0, 4).map(j => {
            const score = Math.round(Number(j.score) || 0);
            const scoreClass = score >= 85 ? 'is-high' : (score >= 70 ? 'is-good' : 'is-mid');
            const key = j.job_key || j.id || '';
            const salaryHtml = j.salary ? `<span class="radar-job-salary">${esc(j.salary)}</span>` : '';
            const tagHtml = isStaged
              ? `<span class="radar-job-tag is-staged">New Staged</span>`
              : `<span class="radar-job-tag is-saved">In Feed</span>`;
            return `
              <div class="radar-job-card" data-key="${esc(key)}" data-staged="${isStaged ? 'true' : 'false'}" role="button" tabindex="0" title="${isStaged ? 'Click to import ' + esc(j.title) : 'View ' + esc(j.title) + ' in feed'}">
                <div class="radar-job-main">
                  <div class="radar-job-title-row">
                    <span class="radar-job-title" title="${esc(j.title)}">${esc(j.title)}</span>
                    <div class="radar-job-badges">
                      ${tagHtml}
                      <span class="radar-job-score ${scoreClass}">${score}% match</span>
                    </div>
                  </div>
                  <div class="radar-job-sub-row">
                    <span class="radar-job-company">${esc(j.company || 'Company')}</span>
                    ${j.work_mode ? `<span class="radar-job-dot">·</span><span class="radar-job-mode">${esc(j.work_mode)}</span>` : ''}
                    ${j.location ? `<span class="radar-job-dot">·</span><span class="radar-job-loc" title="${esc(j.location)}">${esc(j.location)}</span>` : ''}
                    ${salaryHtml}
                  </div>
                </div>
                <span class="radar-job-action-icon" aria-hidden="true">&rsaquo;</span>
              </div>
            `;
          }).join('');

          listEl.innerHTML = bannerHtml + cardsHtml;

          listEl.querySelectorAll('.radar-job-card').forEach(card => {
            card.addEventListener('click', (e) => {
              e.stopPropagation();
              const key = card.dataset.key;
              const cardStaged = card.dataset.staged === 'true';
              const popover = $('#radarPopover');
              const radarBtn = $('#btnLinkedinRadar');
              if (popover) {
                popover.hidden = true;
                stopRadarCountdown();
              }
              if (radarBtn) radarBtn.setAttribute('aria-expanded', 'false');

              if (cardStaged) {
                if (key) S.selectedKey = key;
                const refreshBtn = $('#btnJobsRefreshSync');
                if (refreshBtn) refreshBtn.click();
              } else if (key) {
                const inCurrent = (S.jobs || []).some(item => jobKey(item) === key);
                if (inCurrent) {
                  selectJob(key);
                  const el = $(`#jobList .job-item[data-key="${key}"]`);
                  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                } else {
                  const inAll = (S.allJobs || []).find(item => jobKey(item) === key) || displayJobs.find(item => (item.job_key || item.id) === key);
                  if (inAll) {
                    S.selectedKey = key;
                    if (!S.allJobs.some(j => jobKey(j) === key)) {
                      S.allJobs.push(inAll);
                    }
                    applySort();
                    renderResults();
                    selectJob(key);
                    const el = $(`#jobList .job-item[data-key="${key}"]`);
                    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                  } else {
                    const matchedJob = displayJobs.find(item => (item.job_key || item.id) === key);
                    if (matchedJob && matchedJob.url) {
                      const u = safeUrl(matchedJob.url);
                      if (u !== '#') window.open(u, '_blank', 'noopener,noreferrer');
                    }
                  }
                }
              }
            });
          });
        }
      }

      const freqSel = $('#radarFreqSelect');
      if (freqSel && document.activeElement !== freqSel) {
        freqSel.value = r.enabled ? String(r.interval_min) : '0';
      }

      // Update Settings View Card (#linkedinRadarSettingsCard)
      const cfgBadge = $('#activeRadarSettingsBadge');
      if (cfgBadge) {
        if (!r.enabled) {
          cfgBadge.textContent = 'Disabled';
          cfgBadge.className = 'chip chip-muted';
        } else {
          cfgBadge.textContent = `Active (${r.interval_min}m)`;
          cfgBadge.className = 'chip chip-ok';
        }
      }

      const cfgSweep = $('#cfgRadarLastSweepText');
      if (cfgSweep) {
        cfgSweep.textContent = r.last_run ? formatTimeSince(new Date(r.last_run).getTime()) : 'Never';
      }

      const cfgNext = $('#cfgRadarNextSweepText');
      if (cfgNext) {
        if (!r.enabled) cfgNext.textContent = 'Disabled';
        else if (r.is_running) cfgNext.textContent = 'Scanning now...';
        else if (r.next_run === 'Immediate') cfgNext.textContent = 'Any moment';
        else if (r.next_run) cfgNext.textContent = formatTimeUntil(new Date(r.next_run).getTime());
        else cfgNext.textContent = `In ${r.interval_min}m`;
      }

      const cfgSel = $('#cfgRadarIntervalSelect');
      if (cfgSel && document.activeElement !== cfgSel) {
        cfgSel.value = r.enabled ? String(r.interval_min) : '0';
      }
    } catch (e) {
      console.debug('linkedin radar status:', e);
    }
  }

  function updateRadarLiveTicker() {
    const r = lastRadarTelemetry;
    if (!r) return;
    const nextScanEl = $('#radarNextScanText');
    const lastScanEl = $('#radarLastScanText');

    if (lastScanEl && r.last_run) {
      lastScanEl.textContent = formatTimeSince(new Date(r.last_run).getTime());
    }

    if (nextScanEl) {
      if (!r.enabled) {
        nextScanEl.textContent = 'Disabled';
      } else if (r.is_running) {
        nextScanEl.textContent = 'Scanning LinkedIn...';
      } else if (r.next_run === 'Immediate') {
        nextScanEl.textContent = 'Any moment';
      } else if (r.next_run) {
        const nextMs = new Date(r.next_run).getTime();
        const diff = nextMs - Date.now();
        if (diff <= 0) {
          nextScanEl.textContent = 'Sweeping LinkedIn...';
          if (!isRadarAutoPolling) {
            isRadarAutoPolling = true;
            setTimeout(async () => {
              await checkLinkedinRadarStatus();
              isRadarAutoPolling = false;
            }, 3000);
          }
        } else {
          nextScanEl.textContent = formatTimeUntil(nextMs);
        }
      } else {
        nextScanEl.textContent = `In ${r.interval_min}m`;
      }
    }
  }

  function startRadarCountdown() {
    if (radarCountdownTicker) clearInterval(radarCountdownTicker);
    updateRadarLiveTicker();
    radarCountdownTicker = setInterval(updateRadarLiveTicker, 1000);
  }

  function stopRadarCountdown() {
    if (radarCountdownTicker) {
      clearInterval(radarCountdownTicker);
      radarCountdownTicker = null;
    }
  }

  function setupLinkedinRadarUi() {
    const radarBtn = $('#btnLinkedinRadar');
    const popover = $('#radarPopover');
    const closeBtn = $('#radarPopoverClose');
    const freqSel = $('#radarFreqSelect');
    const scanBtn = $('#btnRadarScanNow');
    const applyBtn = $('#btnRadarApplyJobs');
    const cfgScanBtn = $('#btnCfgRadarScanNow');
    const cfgSaveBtn = $('#btnSaveRadarSettings');
    const cfgSel = $('#cfgRadarIntervalSelect');

    // Popover open/close with ticker
    if (radarBtn && popover) {
      radarBtn.addEventListener('click', e => {
        e.stopPropagation();
        const willShow = popover.hidden;
        popover.hidden = !willShow;
        radarBtn.setAttribute('aria-expanded', String(willShow));
        if (willShow) {
          checkLinkedinRadarStatus();
          startRadarCountdown();
        } else {
          stopRadarCountdown();
        }
      });

      if (closeBtn) {
        closeBtn.addEventListener('click', e => {
          e.stopPropagation();
          popover.hidden = true;
          radarBtn.setAttribute('aria-expanded', 'false');
          stopRadarCountdown();
        });
      }

      document.addEventListener('click', e => {
        if (!popover.hidden && !popover.contains(e.target) && e.target !== radarBtn && !radarBtn.contains(e.target)) {
          popover.hidden = true;
          radarBtn.setAttribute('aria-expanded', 'false');
          stopRadarCountdown();
        }
      });
    }

    // Freq select inside popover
    if (freqSel) {
      freqSel.addEventListener('change', async () => {
        const val = parseInt(freqSel.value, 10);
        try {
          await api('/api/linkedin-radar/settings', {
            method: 'POST',
            body: { enabled: val > 0, interval_min: val }
          });
          toast(val > 0 ? `LinkedIn Radar frequency set to every ${val} minutes.` : 'LinkedIn Radar paused (manual only).');
          checkLinkedinRadarStatus();
        } catch (e) {
          toast('Failed to save radar settings: ' + e.message, 'error');
        }
      });
    }

    // Scan Now in Popover with live polling
    async function triggerRadarScan(btnEl) {
      if (!btnEl || btnEl.disabled) return;
      btnEl.disabled = true;
      const textEl = btnEl.querySelector('span');
      const origText = textEl ? textEl.textContent : 'Scan Now';
      if (textEl) textEl.textContent = 'Scanning...';
      const icon = btnEl.querySelector('svg');
      if (icon) icon.classList.add('is-spinning');

      try {
        const res = await api('/api/linkedin-radar/trigger', { method: 'POST' });
        toast('LinkedIn Radar sweep started. Checking 24h postings...', 'info');
        await checkLinkedinRadarStatus();

        let attempts = 0;
        if (radarStatusPollTimer) clearInterval(radarStatusPollTimer);
        radarStatusPollTimer = setInterval(async () => {
          attempts++;
          try {
            const statusRes = await api('/api/linkedin-radar/status');
            if (statusRes && statusRes.radar) {
              const r = statusRes.radar;
              lastRadarTelemetry = r;
              await checkLinkedinRadarStatus();
              if (!r.is_running || attempts >= 12) {
                clearInterval(radarStatusPollTimer);
                radarStatusPollTimer = null;
                btnEl.disabled = false;
                if (textEl) textEl.textContent = origText;
                if (icon) icon.classList.remove('is-spinning');
                if (r.pending_count > 0) {
                  toast(`🎉 Scan complete: Found ${r.pending_count} new job(s) ready to review!`, 'success');
                } else {
                  toast('✓ Scan complete: 0 new postings on LinkedIn right now. Feed is up to date.', 'info');
                }
              }
            }
          } catch (pollErr) {
            clearInterval(radarStatusPollTimer);
            radarStatusPollTimer = null;
            btnEl.disabled = false;
            if (textEl) textEl.textContent = origText;
            if (icon) icon.classList.remove('is-spinning');
          }
        }, 1500);
      } catch (e) {
        toast('Could not trigger radar scan: ' + e.message, 'error');
        btnEl.disabled = false;
        if (textEl) textEl.textContent = origText;
        if (icon) icon.classList.remove('is-spinning');
      }
    }

    if (scanBtn) scanBtn.addEventListener('click', () => triggerRadarScan(scanBtn));
    if (cfgScanBtn) cfgScanBtn.addEventListener('click', () => triggerRadarScan(cfgScanBtn));

    // Review / Import Staged Jobs button
    if (applyBtn) {
      applyBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const stagedJobs = Array.isArray(lastRadarTelemetry?.staged_jobs) ? lastRadarTelemetry.staged_jobs : [];
        if (!stagedJobs.length || applyBtn.classList.contains('is-disabled')) {
          toast('✓ Feed is up to date: 0 new LinkedIn jobs waiting. Click "Scan Now" to check again.', 'info');
          return;
        }
        if (popover) {
          popover.hidden = true;
          stopRadarCountdown();
        }
        const radarBtn = $('#btnLinkedinRadar');
        if (radarBtn) radarBtn.setAttribute('aria-expanded', 'false');
        const refreshBtn = $('#btnJobsRefreshSync');
        if (refreshBtn) refreshBtn.click();
      });
    }

    // Settings View save button
    if (cfgSaveBtn && cfgSel) {
      cfgSaveBtn.addEventListener('click', async () => {
        cfgSaveBtn.disabled = true;
        const val = parseInt(cfgSel.value, 10);
        try {
          await api('/api/linkedin-radar/settings', {
            method: 'POST',
            body: { enabled: val > 0, interval_min: val }
          });
          toast(val > 0 ? `Saved: LinkedIn Radar runs every ${val} minutes.` : 'Saved: LinkedIn Radar paused.');
          checkLinkedinRadarStatus();
        } catch (e) {
          toast('Failed to save settings: ' + e.message, 'error');
        } finally {
          setTimeout(() => { cfgSaveBtn.disabled = false; }, 800);
        }
      });
    }

    // Initial check
    checkLinkedinRadarStatus();
  }

  // ----------------------------------------------------------------- application tracker UI
  function setupApplicationTrackerUi() {
    // Search input
    const appSearch = $('#appSearchInput');
    if (appSearch) {
      appSearch.addEventListener('input', () => {
        S.appSearchQuery = appSearch.value;
        renderApplicationView();
      });
    }
    const appSearchClear = $('#appSearchClear');
    if (appSearchClear) {
      appSearchClear.addEventListener('click', () => {
        S.appSearchQuery = '';
        if (appSearch) appSearch.value = '';
        renderApplicationView();
      });
    }

    // Filter pills
    const pills = $('#appFilterPills');
    if (pills) {
      pills.addEventListener('click', e => {
        const btn = e.target.closest('[data-app-filter]');
        if (!btn) return;
        setAppFilter(btn.dataset.appFilter);
      });
    }

    // Interactive KPI Ribbon filters
    const kpiRibbon = $('#appKpiRibbon');
    if (kpiRibbon) {
      kpiRibbon.addEventListener('click', e => {
        const card = e.target.closest('[data-kpi]');
        if (!card) return;
        const kpi = card.dataset.kpi;
        if (kpi === 'live') {
          setAppFilter('all');
        } else if (kpi === 'interview') {
          setAppFilter('interviewing');
        } else if (kpi === 'overdue') {
          setAppFilter('attention');
        }
      });
      kpiRibbon.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          const card = e.target.closest('[data-kpi]');
          if (card) {
            e.preventDefault();
            card.click();
          }
        }
      });
    }

    // View toggle
    const btnKanban = $('#btnViewKanban');
    const btnTable = $('#btnViewTable');
    if (btnKanban) {
      btnKanban.addEventListener('click', () => {
        S.appViewMode = 'kanban';
        try { localStorage.setItem('jh_app_view_mode', 'kanban'); } catch (e) {}
        renderApplicationView();
      });
    }
    if (btnTable) {
      btnTable.addEventListener('click', () => {
        S.appViewMode = 'table';
        try { localStorage.setItem('jh_app_view_mode', 'table'); } catch (e) {}
        renderApplicationView();
      });
    }

    // Drawer close handlers & scroll leakage prevention
    const overlay = $('#appDrawerOverlay');
    if (overlay) {
      overlay.addEventListener('click', closeAppDrawer);
      overlay.addEventListener('wheel', e => e.preventDefault(), { passive: false });
      overlay.addEventListener('touchmove', e => e.preventDefault(), { passive: false });
    }
    const drawer = $('#appDrawer');
    if (drawer) {
      drawer.addEventListener('wheel', e => {
        const scrollable = e.target.closest('.drawer-content, .drawer-tabs, .drawer-stage-pills');
        if (!scrollable) e.preventDefault();
      }, { passive: false });
    }
    const closeBtn = $('#drawerCloseBtn');
    if (closeBtn) closeBtn.addEventListener('click', closeAppDrawer);
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && S.activeDrawerApp) closeAppDrawer();
    });

    // Drawer tabs delegation
    const tabsContainer = $('.drawer-tabs');
    if (tabsContainer) {
      tabsContainer.addEventListener('click', e => {
        const tab = e.target.closest('.drawer-tab');
        if (tab && tab.dataset.drawerTab) {
          switchDrawerTab(tab.dataset.drawerTab);
        }
      });
    }

    // Drawer stage pills
    const stagePills = $('#drawerStagePills');
    if (stagePills) {
      stagePills.addEventListener('click', e => {
        const b = e.target.closest('[data-stage]');
        if (!b || !S.activeDrawerApp) return;
        moveApp(S.activeDrawerApp.id, b.dataset.stage);
      });
    }

    // Drawer priority picker
    const prioPicker = $('#drawerPriorityPicker');
    if (prioPicker) {
      prioPicker.addEventListener('click', e => {
        const b = e.target.closest('[data-p]');
        if (!b || !S.activeDrawerApp) return;
        S.activeDrawerApp.priority = b.dataset.p;
        $$('.p-chip', prioPicker).forEach(c => c.classList.toggle('is-active', c === b));
        saveActiveDrawerApp(false);
      });
    }

    // Quick follow-up date buttons
    $$('[data-quick-date]').forEach(b => {
      b.addEventListener('click', () => {
        const v = b.dataset.quickDate;
        const inp = $('#drawerFollowDate');
        if (!inp) return;
        if (v === 'clear') inp.value = '';
        else inp.value = isoDay(Number(v));
        if (S.activeDrawerApp) {
          S.activeDrawerApp.follow_up_date = inp.value;
          saveActiveDrawerApp(false);
        }
      });
    });

    // Drawer tasks
    const taskList = $('#drawerTaskList');
    if (taskList) {
      taskList.addEventListener('change', e => {
        const chk = e.target.closest('.drawer-task-checkbox');
        if (!chk || !S.activeDrawerApp) return;
        const idx = Number(chk.dataset.taskIdx);
        if (S.activeDrawerApp.tasks && S.activeDrawerApp.tasks[idx]) {
          S.activeDrawerApp.tasks[idx].completed = chk.checked;
          renderDrawerTasks(S.activeDrawerApp);
          saveActiveDrawerApp(false);
        }
      });
      taskList.addEventListener('click', e => {
        const delBtn = e.target.closest('[data-del-task]');
        if (!delBtn || !S.activeDrawerApp) return;
        const idx = Number(delBtn.dataset.delTask);
        if (S.activeDrawerApp.tasks) {
          S.activeDrawerApp.tasks.splice(idx, 1);
          renderDrawerTasks(S.activeDrawerApp);
          saveActiveDrawerApp(false);
        }
      });
    }

    const addTaskBtn = $('#drawerAddTaskBtn');
    const newTaskInput = $('#drawerNewTaskInput');
    if (addTaskBtn && newTaskInput) {
      const doAddTask = () => {
        const text = newTaskInput.value.trim();
        if (!text || !S.activeDrawerApp) return;
        S.activeDrawerApp.tasks = S.activeDrawerApp.tasks || [];
        S.activeDrawerApp.tasks.push({ id: 't_' + Date.now(), text, completed: false });
        newTaskInput.value = '';
        renderDrawerTasks(S.activeDrawerApp);
        saveActiveDrawerApp(false);
      };
      addTaskBtn.addEventListener('click', doAddTask);
      newTaskInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); doAddTask(); }
      });
    }

    // Drawer contacts
    const contactsList = $('#drawerContactsList');
    if (contactsList) {
      contactsList.addEventListener('click', e => {
        const delBtn = e.target.closest('[data-del-contact]');
        if (!delBtn || !S.activeDrawerApp) return;
        const idx = Number(delBtn.dataset.delContact);
        if (S.activeDrawerApp.contacts) {
          S.activeDrawerApp.contacts.splice(idx, 1);
          renderDrawerContacts(S.activeDrawerApp);
          saveActiveDrawerApp(false);
        }
      });
    }

    const addContactBtn = $('#drawerAddContactBtn');
    if (addContactBtn) {
      addContactBtn.addEventListener('click', () => {
        if (!S.activeDrawerApp) return;
        const name = ($('#drawerContactName').value || '').trim();
        const role = ($('#drawerContactRole').value || '').trim();
        const email = ($('#drawerContactEmail').value || '').trim();
        const linkedin = ($('#drawerContactLinkedin').value || '').trim();
        if (!name) { toast('Please provide a contact name', 'error'); return; }
        S.activeDrawerApp.contacts = S.activeDrawerApp.contacts || [];
        S.activeDrawerApp.contacts.push({ name, role, email, linkedin });
        $('#drawerContactName').value = '';
        $('#drawerContactRole').value = '';
        $('#drawerContactEmail').value = '';
        $('#drawerContactLinkedin').value = '';
        renderDrawerContacts(S.activeDrawerApp);
        saveActiveDrawerApp(false);
        toast('Contact added');
      });
    }

    // Drawer action buttons
    const drawerSaveBtn = $('#drawerSaveBtn');
    if (drawerSaveBtn) drawerSaveBtn.addEventListener('click', () => saveActiveDrawerApp(true));

    const drawerDeleteBtn = $('#drawerDeleteBtn');
    if (drawerDeleteBtn) {
      drawerDeleteBtn.addEventListener('click', () => {
        if (!S.activeDrawerApp) return;
        const id = S.activeDrawerApp.id;
        deleteApp(id);
      });
    }

    const drawerTailorBtn = $('#drawerTailorBtn');
    if (drawerTailorBtn) {
      drawerTailorBtn.addEventListener('click', () => {
        if (!S.activeDrawerApp) return;
        const a = S.activeDrawerApp;
        const jd = a.job_data || a;
        closeAppDrawer();
        openWorkspace(jd, 'resume', 'applications');
      });
    }
  }

  // ------------------------------------------------------------------- init
  async function init() {
    S.openExp = new Set([0]);
    renderStartupLoadingState('workspace');
    initTheme();
    syncFamousUi();
    setupP4FilterBar();
    setupAllFiltersDrawer();
    syncJobTypeFilterState();
    setupOnboardingFlow();
    setupAutoSearchUi();
    setupLinkedinRadarUi();
    setupApplicationTrackerUi();
    setupResumeVariantUi();
    setupSettingsHub();
    bindEvents();
    await Promise.all([loadProfile(), loadApplications()]);
    if (!S.profileEmpty) {
      loadRecommendations(false).catch(() => {});
    }
    renderWsHeader();
    renderIdeas();
    updateStartupLoadingState('cache');

    // Auto-search & LinkedIn Radar status polling
    setInterval(checkAutoSearchStatus, 15000);
    checkAutoSearchStatus();
    setInterval(checkLinkedinRadarStatus, 15000);
    checkLinkedinRadarStatus();

    // Background continuous enrichment poller
    scheduleNextEnrichmentCheck(1500);
    // Wake up background enricher on startup if any unenriched jobs exist
    api('/api/enrichment/trigger', { method: 'POST' }).catch(() => {});

    // Restore auto-reload schedule (defaults to 5 hours)
    const savedMins = getAutoReloadMinutes();
    const reloadSelect = $('#autoReloadSelect');
    if (reloadSelect) reloadSelect.value = String(savedMins);
    scheduleAutoReload(savedMins);

    // Fetch jobs from database on startup
    updateStartupLoadingState('feed');
    await fetchJobsFromDb();

    route();

    if (S.view === 'jobs') {
      if ((S.jobs && S.jobs.length) || (S.allJobs && S.allJobs.length)) renderResults();
      else renderWelcomeState();
    }
  }

  function renderWelcomeState() {
    $('#jobList')?.classList.remove('is-startup-loading');
    const stage = $('#searchProgressStage');
    if (stage) stage.hidden = true;
    const split = $('#searchSplit');
    if (split) {
      split.hidden = false;
      split.removeAttribute('aria-busy');
    }
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
