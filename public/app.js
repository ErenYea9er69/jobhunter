/*
 * JobHunter web app.
 * Plain JavaScript, no build step. Talks to the local daemon on the same origin.
 * Parts: core, jobs, applications, documents, resume, settings, boot.
 */
(function () {
  "use strict";

  /* ------------------------------------------------------------ helpers */
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const byId = (id) => document.getElementById(id);

  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ESC[c]));

  function icon(name, cls) {
    return `<svg class="icon${cls ? " " + cls : ""}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  }

  function html(node, markup) {
    node.innerHTML = markup;
    return node;
  }

  function debounce(fn, ms) {
    let t;
    return (...a) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...a), ms);
    };
  }

  function lsGet(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function lsSet(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* storage can be blocked */ }
  }
  function ssGet(key) {
    try { return JSON.parse(sessionStorage.getItem(key) || "null"); } catch (e) { return null; }
  }
  function ssSet(key, value) {
    try { sessionStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* ignore */ }
  }

  const rtf = typeof Intl !== "undefined" && Intl.RelativeTimeFormat ? new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }) : null;
  function daysAgo(n) {
    if (n == null || isNaN(n)) return "";
    if (!rtf) return n + " days ago";
    return rtf.format(-Math.round(n), "day");
  }

  const splitList = (s) => String(s || "").split(",").map((x) => x.trim()).filter(Boolean);

  function clip(text, n) {
    const s = String(text || "");
    return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
  }

  function humanize(key) {
    const s = String(key).replace(/[_-]+/g, " ").trim();
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  /* ------------------------------------------------------------ state */
  const state = {
    method: lsGet("jobhunter_method") || "modern",
    route: "signals",
    online: null,
    profiles: [],
    active: null, // active profile object or null
    profilesLoaded: false,
    jobs: [],
    selectedId: null,
    searched: false,
    searching: false,
    query: "",
    place: "",
    filters: { mode: "", type: "", fit: 0, min_salary: 0, seniority: "", show_unknown_salary: true },
    sort: "score",
    radar: { running: false, status: "idle", matches: 0, failureCount: 0, interval: 900, backoffSeconds: 0, warning: null },
    cleanup: { expiringSoonCount: 0, expiringJobs: [], lastDeletedCount: 0, unacknowledgedDeletions: 0 },
    closingSoon: [],
    countsRemoved: {},
    usableGate: { status: "usable", message: "" },
    refreshStatus: { sources: [], minRemainingSeconds: 0 },
    // Modern track state
    signals: [],
    signalsLoaded: false,
    signalsFilter: { q: "", stage: "any", type: "", includeLate: false },
    activeBrief: null,
    activeContacts: [],
    activeOutreachDraft: null,
    outreachToday: { sent_today: 0, daily_cap: 20, remaining: 20, entries: [] },
    outreachQueue: [],
    followups: [],
    apps: [],
    appsLoaded: false,
    stageTab: "saved",
    docDraft: null,
    prefs: null,
    ai: null,
    gmail: null,
    candidate: null,
  };

  const STAGES = [
    { id: "saved", label: "Saved", hint: "Roles you want to apply to." },
    { id: "queued", label: "Queued", hint: "Ready for the extension to fill." },
    { id: "applied", label: "Applied", hint: "Submitted. Waiting for a reply." },
    { id: "interview", label: "Interview", hint: "A company replied." },
    { id: "offer", label: "Offer", hint: "You received an offer." },
  ];
  const STAGE_LABEL = Object.fromEntries(STAGES.concat([{ id: "rejected", label: "Closed" }]).map((s) => [s.id, s.label]));

  /* ------------------------------------------------------------ api */
  async function request(method, path, body, signal) {
    let res;
    try {
      res = await fetch(path, {
        method,
        signal,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      if (e && e.name === "AbortError") throw e;
      setOnline(false);
      const err = new Error("JobHunter is not running on this computer.");
      err.offline = true;
      throw err;
    }
    let env = null;
    try { env = await res.json(); } catch (e) { /* non-JSON body */ }
    if (res.status === 503) {
      setOnline(false);
      const err = new Error("JobHunter is not running on this computer.");
      err.offline = true;
      throw err;
    }
    setOnline(true);
    const failed = !res.ok || (env && env.success === false);
    if (failed) {
      const m = env && env.error && (env.error.message || env.error);
      throw new Error(typeof m === "string" && m ? m : "The request failed (" + res.status + ").");
    }
    return env && env.data !== undefined ? env.data : env;
  }
  const apiGet = (p, signal) => request("GET", p, null, signal);
  const apiPost = (p, b, signal) => request("POST", p, b || {}, signal);

  /* ------------------------------------------------------------ toasts and dialogs */
  function toast(message, opts) {
    opts = opts || {};
    const box = byId("toasts");
    const t = document.createElement("div");
    t.className = "toast" + (opts.kind === "bad" ? " bad" : "");
    t.innerHTML = `<span>${esc(message)}</span>`;
    let timer;
    const close = () => { clearTimeout(timer); t.remove(); };
    if (opts.action) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = opts.action.label;
      b.addEventListener("click", () => { close(); opts.action.run(); });
      t.appendChild(b);
    }
    box.appendChild(t);
    while (box.children.length > 3) box.firstChild.remove();
    timer = setTimeout(close, opts.action ? 8000 : 4500);
  }

  function confirmDialog(opts) {
    return new Promise((resolve) => {
      const dlg = byId("dlg-confirm");
      byId("dlg-confirm-title").textContent = opts.title;
      byId("dlg-confirm-text").textContent = opts.text || "";
      byId("dlg-confirm-ok").textContent = opts.ok || "Remove";
      byId("dlg-confirm-cancel").textContent = opts.cancel || "Keep it";
      const done = () => { dlg.removeEventListener("close", done); resolve(dlg.returnValue === "ok"); };
      dlg.addEventListener("close", done);
      dlg.returnValue = "cancel";
      dlg.showModal();
      byId("dlg-confirm-cancel").focus();
    });
  }

  function closeOnBackdrop(dlg) {
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  }

  /* ------------------------------------------------------------ menus */
  let openMenu = null;
  function closeMenu() {
    if (!openMenu) return;
    openMenu.menu.remove();
    openMenu.trigger.setAttribute("aria-expanded", "false");
    openMenu = null;
  }
  /* items: [{label, icon, checked, href, run}] or "-" for separator, or {heading} */
  function showMenu(trigger, items, opts) {
    opts = opts || {};
    if (openMenu && openMenu.trigger === trigger) { closeMenu(); return; }
    closeMenu();
    const wrap = trigger.closest(".menu-wrap") || trigger.parentElement;
    wrap.classList.add("menu-wrap");
    const menu = document.createElement("div");
    menu.className = "menu" + (opts.up ? " up" : "");
    menu.setAttribute("role", "menu");
    items.forEach((it) => {
      if (it === "-") { menu.appendChild(document.createElement("hr")); return; }
      if (it.heading) {
        const h = document.createElement("div");
        h.className = "menu-label";
        h.textContent = it.heading;
        menu.appendChild(h);
        return;
      }
      const isLink = !!it.href;
      const b = document.createElement(isLink ? "a" : "button");
      if (isLink) { b.href = it.href; b.target = "_blank"; b.rel = "noopener noreferrer"; } else { b.type = "button"; }
      b.setAttribute("role", it.checked != null ? "menuitemradio" : "menuitem");
      if (it.checked != null) b.setAttribute("aria-checked", it.checked ? "true" : "false");
      b.tabIndex = -1;
      b.innerHTML = (it.icon ? icon(it.icon) : "") + `<span>${esc(it.label)}</span>`;
      b.addEventListener("click", () => { closeMenu(); trigger.focus(); if (it.run) it.run(); });
      menu.appendChild(b);
    });
    wrap.appendChild(menu);
    trigger.setAttribute("aria-expanded", "true");
    openMenu = { menu, trigger };
    const first = menu.querySelector('[role^="menuitem"]');
    if (first) first.focus();
    menu.addEventListener("keydown", (e) => {
      const els = $$('[role^="menuitem"]', menu);
      const i = els.indexOf(document.activeElement);
      if (e.key === "ArrowDown") { e.preventDefault(); els[(i + 1) % els.length].focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); els[(i - 1 + els.length) % els.length].focus(); }
      else if (e.key === "Home") { e.preventDefault(); els[0].focus(); }
      else if (e.key === "End") { e.preventDefault(); els[els.length - 1].focus(); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); const t = trigger; closeMenu(); t.focus(); }
      else if (e.key === "Tab") { closeMenu(); }
    });
  }
  document.addEventListener("click", (e) => {
    if (openMenu && !openMenu.menu.contains(e.target) && !openMenu.trigger.contains(e.target)) closeMenu();
  });

  /* ------------------------------------------------------------ theme */
  const THEMES = ["system", "light", "dark"];
  const THEME_LABEL = { system: "System", light: "Light", dark: "Dark" };
  function currentTheme() {
    const t = lsGet("jobhunter-theme");
    return t === "light" || t === "dark" ? t : "system";
  }
  function applyTheme(t) {
    if (t === "system") {
      delete document.documentElement.dataset.theme;
      try { localStorage.removeItem("jobhunter-theme"); } catch (e) { /* ignore */ }
    } else {
      document.documentElement.dataset.theme = t;
      lsSet("jobhunter-theme", t);
    }
    byId("theme-label").textContent = "Theme: " + THEME_LABEL[t];
  }
  function initTheme() {
    applyTheme(currentTheme());
    byId("btn-theme").addEventListener("click", () => {
      applyTheme(THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length]);
    });
  }

  /* ------------------------------------------------------------ service status */
  function setOnline(on) {
    if (state.online === on) return;
    state.online = on;
    const dot = byId("rail-dot");
    dot.className = "dot " + (on ? "ok" : "bad");
    byId("rail-status-title").textContent = on ? (state.candidate ? state.candidate : "Service running") : "Service not reachable";
    byId("rail-status-text").textContent = on ? "Data stays on this computer." : "Start JobHunter, then reload.";
  }

  async function checkStatus() {
    try {
      const s = await apiGet("/api/extension/status");
      state.candidate = (s && s.candidate_name) || null;
      state.online = null; // force a redraw of the label
      setOnline(true);
    } catch (e) { /* setOnline(false) already ran */ }
  }

  function offlineNotice(retry) {
    return `<div class="notice bad" role="alert">${icon("wifi-off")}<div><p><strong>JobHunter is not running.</strong></p><p>Start the app on this computer, then try again.</p>${retry ? '<div class="actions"><button class="btn btn-secondary btn-sm" type="button" data-retry>Try again</button></div>' : ""}</div></div>`;
  }

  function errorNotice(message, retry) {
    return `<div class="notice bad" role="alert">${icon("circle-alert")}<div><p><strong>${esc(message)}</strong></p>${retry ? '<div class="actions"><button class="btn btn-secondary btn-sm" type="button" data-retry>Try again</button></div>' : ""}</div></div>`;
  }

  /* ------------------------------------------------------------ resume term marks */
  /*
   * Wraps terms found in the text with <mark class="mk">. The text is escaped first,
   * piece by piece, so a posting can never inject markup.
   */
  function termRegex(terms) {
    const list = Array.from(new Set(terms.map((t) => String(t || "").trim()).filter((t) => t.length > 1)));
    if (!list.length) return null;
    list.sort((a, b) => b.length - a.length);
    const body = list.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
    try {
      return new RegExp("(?<![\\p{L}\\p{N}_])(" + body + ")(?![\\p{L}\\p{N}_])", "giu");
    } catch (e) {
      return new RegExp("(" + body + ")", "gi");
    }
  }
  function markText(text, terms, startIndex) {
    const re = termRegex(terms);
    const src = String(text == null ? "" : text);
    if (!re) return { html: esc(src), count: 0 };
    let out = "", last = 0, n = 0, m;
    re.lastIndex = 0;
    while ((m = re.exec(src))) {
      out += esc(src.slice(last, m.index));
      out += `<mark class="mk" style="--i:${Math.min((startIndex || 0) + n, 10)}">${esc(m[0])}</mark>`;
      last = m.index + m[0].length;
      n++;
      if (m[0].length === 0) re.lastIndex++;
    }
    out += esc(src.slice(last));
    return { html: out, count: n };
  }

  /* ------------------------------------------------------------ profile data */
  async function loadProfiles(force) {
    if (state.profilesLoaded && !force) return;
    try {
      const d = await apiGet("/api/profiles");
      const list = (d && d.profiles) || [];
      state.profiles = list;
      const activeKey = d && d.active;
      state.active = list.find((p) => p.is_active) || list.find((p) => activeKey && (p.id === activeKey || p.name === activeKey)) || null;
      state.profilesLoaded = true;
    } catch (e) {
      state.profiles = [];
      state.active = null;
    }
    updateResumeFlags();
  }

  function updateResumeFlags() {
    const missing = state.profilesLoaded && !state.active;
    const flag = byId("nav-resume-flag");
    flag.textContent = missing ? "Add" : "";
    flag.style.display = missing ? "" : "none";
    byId("tab-resume-dot").hidden = !missing;
  }

  function profileTerms() {
    const p = state.active;
    if (!p) return [];
    const terms = (p.skills || []).slice();
    (p.experience || []).forEach((x) => {
      const t = String((x && (x.summary || x.description)) || "");
      (t.match(/\d+(?:[.,]\d+)?\s?%/g) || []).forEach((v) => terms.push(v.replace(/\s+/g, "")));
    });
    return terms;
  }

  /* ------------------------------------------------------------ router and page head */
  const PAGES = {
    signals: { title: "Signals", sub: "Fresh hiring posts and funding news for direct outreach." },
    jobs: { title: "Jobs", sub: "Roles ranked by how well your resume fits." },
    outreach: { title: "Outreach", sub: "Track direct emails, follow-ups, and responses." },
    applications: { title: "Applications", sub: "" },
    documents: { title: "Documents", sub: "Every claim in a document comes from your resume." },
    resume: { title: "Resume", sub: "The facts JobHunter writes from." },
    settings: { title: "Settings", sub: "Search, method choice, AI engine, and autofill." },
  };
  const routeHooks = {};

  function setHead(title, sub, actionsHtml) {
    byId("page-title").textContent = title;
    byId("page-sub").textContent = sub || "";
    byId("page-sub").hidden = !sub;
    const custom = byId("page-actions-custom");
    if (custom) custom.innerHTML = actionsHtml || "";
    document.title = title + " | JobHunter";
  }

  function parseHash() {
    const h = (location.hash || "").replace(/^#\/?/, "");
    const parts = h.split("/").filter(Boolean).map((s) => { try { return decodeURIComponent(s); } catch (e) { return s; } });
    const defaultRoute = state.method === "modern" ? "signals" : "jobs";
    const name = PAGES[parts[0]] ? parts[0] : defaultRoute;
    return { name, arg: parts[1] || "" };
  }

  let firstRoute = true;
  function onRoute() {
    closeMenu();
    const { name, arg } = parseHash();
    const changed = name !== state.route || firstRoute;
    state.route = name;
    $$(".view").forEach((v) => { v.hidden = v.dataset.view !== name; });
    $$("[data-route]").forEach((a) => {
      if (a.dataset.route === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    const hook = routeHooks[name];
    if (hook) hook(arg, changed);
    if (changed) {
      window.scrollTo(0, 0);
      const main = byId("main");
      if (main) main.scrollTop = 0;
      if (!firstRoute) byId("page-title").focus({ preventScroll: true });
    }
    firstRoute = false;
  }

  function go(path) {
    if (location.hash === "#/" + path) onRoute(); else location.hash = "#/" + path;
  }

  /* ------------------------------------------------------------ dragging a file anywhere */
  let dragDepth = 0;
  function initFileDrop() {
    const ov = byId("drop-overlay");
    const hasFiles = (e) => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
    window.addEventListener("dragenter", (e) => { if (hasFiles(e)) { dragDepth++; ov.hidden = false; } });
    window.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
    window.addEventListener("dragleave", (e) => { if (hasFiles(e)) { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) ov.hidden = true; } });
    window.addEventListener("drop", (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth = 0;
      ov.hidden = true;
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) { go("resume"); uploadResume(f); }
    });
  }

  /* ============================================================ JOBS */
  const MODES = [["", "Any"], ["Remote", "Remote"], ["Hybrid", "Hybrid"], ["Onsite", "On site"]];
  const TYPES = [["", "Any"], ["Full-time", "Full-time"], ["Internship", "Internship"], ["Contract", "Contract"], ["Freelance", "Freelance"]];
  const FITS = [[0, "Any"], [60, "60+"], [75, "75+"], [85, "85+"]];
  const SENIORITIES = [["", "Any"], ["junior", "Early"], ["mid", "Mid"], ["senior", "Senior"], ["lead", "Lead/Staff"]];
  const desktopQuery = window.matchMedia("(min-width: 1000px)");

  let searchCtl = null;
  let searchError = null;
  let jobsInit = false;
  let lastOpenKey = null;

  const jobKey = (j, i) => String(j.id != null ? j.id : j.apply_url || j.url || (j.title || "") + "|" + (j.company || "") + "|" + i);
  const jobUrl = (j) => j.apply_url || j.url || "";
  const jobByKey = (key) => {
    const i = state.jobs.findIndex((j, idx) => jobKey(j, idx) === key);
    return i < 0 ? null : state.jobs[i];
  };
  const tierOf = (score) => (typeof score !== "number" ? "none" : score >= 80 ? "good" : score >= 60 ? "mid" : "bad");
  const TIER_WORD = { good: "Strong fit", mid: "Partial fit", bad: "Weak fit", none: "No score" };

  function avatarHue(name) {
    const hues = [212, 28, 142, 280, 350, 172, 48];
    let h = 0;
    const s = String(name || "?");
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return hues[h % hues.length];
  }
  const initialOf = (name) => (String(name || "?").trim().match(/[\p{L}\p{N}]/u) || ["?"])[0].toUpperCase();

  function snippet(desc) {
    const t = String(desc || "").replace(/\s+/g, " ").replace(/^(about the (role|opportunity|job)|description|job description)\s*[:\-]?\s*/i, "").trim();
    return clip(t, 170);
  }

  function renderFilterSegs() {
    const defs = { mode: MODES, type: TYPES, fit: FITS, seniority: SENIORITIES };
    $$(".seg[data-filter]").forEach((seg) => {
      const key = seg.dataset.filter;
      if (!defs[key]) return;
      seg.innerHTML = defs[key].map(([v, label]) => {
        const on = String(state.filters[key] || "") === String(v);
        return `<button type="button" role="radio" aria-checked="${on}" data-v="${esc(v)}">${esc(label)}</button>`;
      }).join("");
    });
    const n = (state.filters.mode ? 1 : 0) + (state.filters.type ? 1 : 0) + (state.filters.fit ? 1 : 0) + (state.filters.seniority ? 1 : 0) + (state.filters.min_salary ? 1 : 0);
    byId("filter-count").textContent = n ? " (" + n + ")" : "";
  }

  function updateFilterBadges() {
    const counts = state.countsRemoved || {};
    const map = {
      mode: "badge-removed-mode",
      type: "badge-removed-type",
      seniority: "badge-removed-seniority",
      salary: "badge-removed-salary",
    };
    for (const [key, elId] of Object.entries(map)) {
      const el = byId(elId);
      if (!el) continue;
      const count = counts[key] || 0;
      if (count > 0) {
        el.textContent = `(${count} removed)`;
        el.hidden = false;
      } else {
        el.hidden = true;
      }
    }
  }

  function updateUsabilityBanner() {
    const banner = byId("banner-usability");
    if (!banner) return;
    const count = state.jobs.length;
    const searched = state.searched;

    if (!searched) {
      banner.hidden = true;
      return;
    }

    const msgEl = byId("usability-message");
    const actionsEl = byId("usability-actions");
    if (!msgEl || !actionsEl) return;

    if (count < 10) {
      banner.className = "banner-usability few";
      banner.hidden = false;
      msgEl.textContent = `Only ${count} match${count === 1 ? "" : "es"} found (optimal range: 10–300). Loosen one filter or refresh sources.`;
      actionsEl.innerHTML = `
        ${state.filters.min_salary ? `<button class="btn btn-secondary btn-sm" id="btn-loosen-sal" type="button">Clear min salary</button>` : ""}
        ${state.filters.mode ? `<button class="btn btn-secondary btn-sm" id="btn-loosen-mode" type="button">Set mode to Any</button>` : ""}
        <button class="btn btn-quiet btn-sm" id="btn-usability-refresh" type="button">Refresh now</button>
      `;
      const btnSal = byId("btn-loosen-sal");
      if (btnSal) btnSal.addEventListener("click", () => {
        state.filters.min_salary = 0;
        const fltSal = byId("flt-salary");
        if (fltSal) fltSal.value = "";
        loadJobsQuery();
      });
      const btnMode = byId("btn-loosen-mode");
      if (btnMode) btnMode.addEventListener("click", () => {
        state.filters.mode = "";
        renderFilterSegs();
        loadJobsQuery();
      });
      const btnRef = byId("btn-usability-refresh");
      if (btnRef) btnRef.addEventListener("click", onManualRefreshClick);
    } else if (count > 300) {
      banner.className = "banner-usability many";
      banner.hidden = false;
      msgEl.textContent = `Over 300 matches found (${count} total). Tighten your salary or seniority filter to focus on top matches.`;
      actionsEl.innerHTML = `
        <button class="btn btn-secondary btn-sm" id="btn-tighten-sen" type="button">Filter to Senior</button>
        <button class="btn btn-secondary btn-sm" id="btn-tighten-sal" type="button">Set $120k+ min</button>
      `;
      const btnSen = byId("btn-tighten-sen");
      if (btnSen) btnSen.addEventListener("click", () => {
        state.filters.seniority = "senior";
        renderFilterSegs();
        loadJobsQuery();
      });
      const btnSal = byId("btn-tighten-sal");
      if (btnSal) btnSal.addEventListener("click", () => {
        state.filters.min_salary = 120000;
        const fltSal = byId("flt-salary");
        if (fltSal) fltSal.value = "120000";
        loadJobsQuery();
      });
    } else {
      banner.hidden = true;
    }
  }

  function renderClosingSoon() {
    const wrap = byId("closing-soon-wrap");
    if (!wrap) return;
    const list = state.closingSoon || [];
    if (!list.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    const badge = byId("closing-soon-count");
    if (badge) badge.textContent = String(list.length);
    const ul = byId("closing-soon-list");
    if (!ul) return;
    ul.innerHTML = list.map((j) => {
      const hours = j.hours_remaining != null ? Math.round(j.hours_remaining) : 24;
      return `
        <li class="closing-soon-item">
          <div class="cs-info">
            <strong>${esc(j.title)}</strong>
            <span class="meta">at ${esc(j.company)}</span>
            <span class="cs-countdown">${icon("hourglass", "icon-sm")} Expiring in ~${hours}h</span>
          </div>
          <button class="btn btn-secondary btn-sm" type="button" data-act="keep-job" data-id="${esc(j.id)}">Keep job</button>
        </li>
      `;
    }).join("");
  }

  /* ------------------------------------------------------------ V5 Refresh Scheduler & Status */
  let cooldownTimerInterval = null;

  async function pollRefreshStatus() {
    try {
      const data = await apiGet("/api/refresh/status");
      if (!data) return;
      state.refreshStatus = {
        sources: data.sources || [],
        minRemainingSeconds: data.min_remaining_seconds || 0,
        checkedAt: data.checked_at,
      };
      if (state.refreshStatus.minRemainingSeconds > 0 && !cooldownTimerInterval) {
        startCooldownTimer();
      }
      updateCooldownUI();
      renderSystemStatusDrawer();
    } catch (e) {
      /* ignore */
    }
  }

  function startCooldownTimer() {
    if (cooldownTimerInterval) clearInterval(cooldownTimerInterval);
    cooldownTimerInterval = setInterval(() => {
      if (state.refreshStatus && state.refreshStatus.minRemainingSeconds > 0) {
        state.refreshStatus.minRemainingSeconds -= 1;
        updateCooldownUI();
      } else {
        clearInterval(cooldownTimerInterval);
        cooldownTimerInterval = null;
        updateCooldownUI();
      }
    }, 1000);
  }

  function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return "0s";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function updateCooldownUI() {
    const rem = (state.refreshStatus && state.refreshStatus.minRemainingSeconds) || 0;
    const btnDrawer = byId("btn-status-refresh-now");
    const btnUsability = byId("btn-usability-refresh");

    if (rem > 0) {
      const text = `Cooldown (${formatDuration(rem)})`;
      if (btnDrawer) {
        btnDrawer.disabled = true;
        btnDrawer.textContent = text;
      }
      if (btnUsability) {
        btnUsability.disabled = true;
        btnUsability.textContent = text;
      }
    } else {
      if (btnDrawer) {
        btnDrawer.disabled = false;
        btnDrawer.textContent = "Refresh now";
      }
      if (btnUsability) {
        btnUsability.disabled = false;
        btnUsability.textContent = "Refresh now";
      }
    }
  }

  function renderSystemStatusDrawer() {
    const dlg = byId("dlg-system-status");
    if (!dlg || !dlg.open) return;

    // 1. Radar
    const rDot = byId("status-radar-dot");
    const rBadge = byId("status-radar-state-badge");
    const rLast = byId("status-radar-last-poll");
    const rNext = byId("status-radar-next-poll");
    const rMatches = byId("status-radar-matches");
    const rWarnWrap = byId("status-radar-warning-wrap");
    const rWarnText = byId("status-radar-warning-text");

    if (rDot) {
      rDot.className = "radar-dot";
      if (!state.radar.running) rDot.classList.add("off");
      else if (state.radar.failureCount >= 3 || state.radar.status === "warning") rDot.classList.add("warning");
    }

    if (rBadge) {
      rBadge.textContent = state.radar.status === "warning" ? "Warning (Backoff)" : (state.radar.running ? "Active" : "Idle");
      rBadge.className = "badge" + (state.radar.status === "warning" ? " badge-warning" : (state.radar.running ? " badge-accent" : ""));
    }

    if (rLast) rLast.textContent = state.radar.lastPoll ? daysAgo(state.radar.lastPoll) : "Never";
    if (rNext) {
      if (state.radar.running) {
        rNext.textContent = state.radar.nextPoll ? daysAgo(state.radar.nextPoll) : "In ~10–20 min";
      } else {
        rNext.textContent = "Worker not started";
      }
    }
    if (rMatches) rMatches.textContent = `${state.radar.matches || 0} match(es)`;

    if (rWarnWrap && rWarnText) {
      if (state.radar.failureCount >= 3 || state.radar.status === "warning") {
        rWarnWrap.hidden = false;
        rWarnText.textContent = `LinkedIn rate limit or 429 encountered. Backoff delay active (${state.radar.failureCount} sequential retries).`;
      } else {
        rWarnWrap.hidden = true;
      }
    }

    // 2. Sources Table
    const tbody = byId("status-sources-tbody");
    if (tbody && state.refreshStatus && state.refreshStatus.sources) {
      tbody.innerHTML = state.refreshStatus.sources.map((s) => {
        const ttlHours = s.ttl_seconds ? `${Math.round(s.ttl_seconds / 3600)}h` : "12h";
        const lastRunText = s.last_run_at ? daysAgo(s.last_run_at) : "Never";
        let statusBadge = "";
        if (s.in_cooldown) {
          statusBadge = `<span class="badge badge-cooldown">Cooldown</span>`;
        } else if (s.is_due) {
          statusBadge = `<span class="badge badge-warning">Due</span>`;
        } else {
          statusBadge = `<span class="badge">Fresh (${s.last_new || 0} new)</span>`;
        }
        return `
          <tr>
            <td style="padding:var(--s2);font-weight:600">${esc(s.source)}</td>
            <td style="padding:var(--s2);color:var(--ink-soft)">${esc(lastRunText)}</td>
            <td style="padding:var(--s2)">${ttlHours}</td>
            <td style="padding:var(--s2)">${s.is_due ? "Now" : "In schedule"}</td>
            <td style="padding:var(--s2)">${statusBadge}</td>
          </tr>
        `;
      }).join("");
    }
  }

  async function onManualRefreshClick() {
    try {
      toast("Refreshing non-LinkedIn sources in background...", { kind: "info" });
      const res = await apiPost("/api/refresh", { force: true });
      if (res && res.status === "cooldown") {
        toast(res.message, { kind: "bad" });
        if (res.cooldown_remaining_seconds) {
          if (!state.refreshStatus) state.refreshStatus = {};
          state.refreshStatus.minRemainingSeconds = res.cooldown_remaining_seconds;
          startCooldownTimer();
        }
        return;
      }
      toast(`Refresh complete. ${res.inserted || 0} new jobs stored across ${((res.refreshed_sources) || []).length} sources.`);
      await pollRefreshStatus();
      if (state.refreshStatus.minRemainingSeconds > 0) startCooldownTimer();
      await loadJobsQuery();
      renderSystemStatusDrawer();
    } catch (e) {
      toast("Refresh failed: " + e.message, { kind: "bad" });
    }
  }

  function visibleJobs() {
    const f = state.filters;
    let list = state.jobs.map((j, i) => ({ j, key: jobKey(j, i) }));
    list = list.filter(({ j }) => {
      if (f.mode && String(j.work_mode || "").toLowerCase().replace(/[\s-]/g, "") !== f.mode.toLowerCase()) return false;
      if (f.type && !String(j.job_type || "").toLowerCase().includes(f.type.toLowerCase())) return false;
      if (f.fit && !(typeof j.score === "number" && j.score >= f.fit)) return false;
      return true;
    });
    if (state.sort === "date") {
      const d = (x) => (x.j.posted_days_ago == null ? 1e9 : x.j.posted_days_ago);
      list.sort((a, b) => d(a) - d(b));
    } else {
      const s = (x) => (typeof x.j.score === "number" ? x.j.score : -1);
      list.sort((a, b) => s(b) - s(a));
    }
    return list;
  }

  function scoreBadge(score) {
    const tier = tierOf(score);
    if (tier === "none") return `<span class="score" data-tier="none">No score</span>`;
    return `<span class="score" data-tier="${tier}">${Math.round(score)}%<span class="sr-only"> fit, ${TIER_WORD[tier].toLowerCase()}</span></span>`;
  }

  function findApp(j) {
    const url = jobUrl(j);
    const t = String(j.title || "").toLowerCase(), c = String(j.company || "").toLowerCase();
    return state.apps.find((a) => (url && a.url === url) || (t && c && String(a.title || "").toLowerCase() === t && String(a.company || "").toLowerCase() === c)) || null;
  }

  function cardActions(j, key) {
    const app = findApp(j);
    const url = jobUrl(j);
    let apply;
    if (app && app.status !== "saved") apply = `<span class="btn btn-secondary btn-sm card-state">${icon("check", "icon-sm")}${esc(STAGE_LABEL[app.status] || "Tracked")}</span>`;
    else apply = `<button class="btn btn-primary btn-sm" type="button" data-act="apply" data-key="${esc(key)}"${url ? "" : " disabled"}>Apply</button>`;
    const save = app
      ? (app.status === "saved" ? `<button class="btn btn-quiet btn-sm" type="button" disabled>${icon("bookmark-check", "icon-sm")}<span>Saved</span></button>` : "")
      : `<button class="btn btn-quiet btn-sm" type="button" data-act="save" data-key="${esc(key)}">${icon("bookmark", "icon-sm")}<span>Save</span></button>`;
    const copy = url ? `<button class="btn btn-quiet btn-sm btn-icon" type="button" data-act="copy-link" data-key="${esc(key)}" aria-label="Copy posting link">${icon("link", "icon-sm")}</button>` : "";
    const dismiss = `<button class="btn btn-quiet btn-sm btn-icon" type="button" data-act="dismiss" data-key="${esc(key)}" aria-label="Dismiss job" title="Dismiss">${icon("x", "icon-sm")}</button>`;
    return `${apply}${save}${copy}${dismiss}<button class="btn btn-quiet btn-sm go" type="button" data-act="details" data-key="${esc(key)}">Details${icon("chevron-right", "icon-sm")}</button>`;
  }

  function jobCardHtml(item) {
    const { j, key } = item;
    const tier = tierOf(j.score);
    const isNew = typeof j.posted_days_ago === "number" && j.posted_days_ago <= 2;
    const top = typeof j.score === "number" && j.score >= 90;
    const loc = j.location || "";
    const wm = j.work_mode && !loc.toLowerCase().includes(String(j.work_mode).toLowerCase()) ? j.work_mode : "";

    // V5 Card Fields
    const dupBadge = j.possible_duplicate ? `<span class="badge badge-duplicate" title="80-90% title similarity to an existing posting">${icon("circle-alert", "icon-sm")}Possible duplicate</span>` : "";
    const sources = (Array.isArray(j.sources) && j.sources.length) ? j.sources : (j.source ? [j.source] : []);
    const sourceBadges = sources.map(s => `<span class="badge badge-source">${esc(s)}</span>`).join("");
    const hasSalary = Boolean(j.salary || j.min_salary || j.max_salary);
    const salBadge = !hasSalary ? `<span class="badge badge-sal-missing">No salary listed</span>` : "";
    const fitReason = (j.match_reasons && j.match_reasons[0]) || j.fit_reason || "";
    const risks = j.risk_factors || j.risks || [];
    const riskLine = risks.length ? `<div class="jc-risk"><svg class="icon icon-sm"><use href="#i-shield-alert"/></svg><span>${esc(risks.join(" • "))}</span></div>` : "";

    const meta = [
      top ? `<span class="badge hot">Top fit</span>` : "",
      isNew ? `<span class="badge new">New</span>` : "",
      sourceBadges,
      loc ? `<span dir="auto">${esc(loc)}</span>` : "",
      wm ? `<span>${esc(wm)}</span>` : "",
      j.job_type ? `<span>${esc(j.job_type)}</span>` : "",
      j.salary ? `<span>${esc(j.salary)}</span>` : salBadge,
      j.posted_days_ago != null ? `<span>${esc(daysAgo(j.posted_days_ago))}</span>` : "",
    ].filter(Boolean).join("");
    const sk = (j.matched_skills || []).slice(0, 4);
    const more = (j.matched_skills || []).length - sk.length;
    const sn = snippet(j.description);
    return `<li><article class="job-card" data-tier="${tier}" aria-current="${key === state.selectedId}">
      <div class="jc-top">
        <span class="avatar" aria-hidden="true">${esc(initialOf(j.company))}</span>
        <div class="jc-id">
          <span class="jc-co" dir="auto">${esc(j.company || "Company not listed")}</span>
          <h2 class="jc-title" dir="auto"><button class="job-open" type="button" data-key="${esc(key)}" aria-haspopup="dialog">${esc(j.title || "Untitled role")}</button></h2>
        </div>
        <div class="jc-badges">${scoreBadge(j.score)}${dupBadge}</div>
      </div>
      ${meta ? `<div class="jc-meta">${meta}</div>` : ""}
      ${fitReason ? `<div class="jc-fit-reason">${icon("sparkles", "icon-sm")}<span>${esc(fitReason)}</span></div>` : ""}
      ${riskLine}
      ${sn ? `<p class="jc-desc" dir="auto">${esc(sn)}</p>` : ""}
      ${sk.length ? `<p class="jc-skills" aria-label="Skills from your resume"><span class="sr-only">From your resume: </span>${sk.map((s) => `<span class="mk">${esc(s)}</span>`).join("")}${more > 0 ? `<span class="jc-more">+${more}</span>` : ""}</p>` : ""}
      <div class="jc-actions">${cardActions(j, key)}</div>
    </article></li>`;
  }

  function renderJobs() {
    const list = byId("job-list");
    const st = byId("job-state");
    const bar = byId("results-bar");
    st.innerHTML = "";
    if (state.searching) {
      bar.hidden = true;
      list.innerHTML = Array.from({ length: 6 }, () => `<li><div class="job-card skel" aria-hidden="true"><div class="skeleton" style="height:36px;width:60%"></div><div class="skeleton" style="height:12px;width:80%"></div><div class="skeleton" style="height:12px;width:92%"></div><div class="skeleton" style="height:12px;width:70%"></div><div class="skeleton" style="height:30px;width:45%;margin-block-start:auto"></div></div></li>`).join("");
      st.innerHTML = `<p class="status-text mute" role="status" style="padding:var(--s3) 0">${icon("loader-circle", "icon-sm spin")}Checking job boards and scoring each role against your resume.</p>`;
      return;
    }
    if (searchError) {
      bar.hidden = true;
      list.innerHTML = "";
      st.innerHTML = `<div style="padding-block:var(--s4)">${searchError.offline ? offlineNotice(true) : errorNotice(searchError.message, true)}</div>`;
      return;
    }
    if (!state.searched) {
      bar.hidden = true;
      list.innerHTML = "";
      const t = state.active && state.active.target_title;
      st.innerHTML = `<div class="empty">${icon("search", "icon-lg")}<h2>Start with one search</h2><p>${t ? "JobHunter can look for roles that match your resume." : "Type a role and press Search jobs. Add your resume to see how well each role fits."}</p>${t ? `<button class="btn btn-primary" type="button" data-search-target>${icon("search")}<span>Search for ${esc(t)}</span></button>` : ""}</div>`;
      return;
    }
    const items = visibleJobs();
    const hidden = state.jobs.length - items.length;
    if (!state.jobs.length) {
      bar.hidden = true;
      list.innerHTML = "";
      st.innerHTML = `<div class="empty">${icon("inbox", "icon-lg")}<h2>No jobs found</h2><p>Try a broader title, remove the place, or check the words you skip in Settings.</p><div class="form-foot"><button class="btn btn-secondary" type="button" data-clear-place>Search without a place</button><a class="btn btn-quiet" href="#/settings/search">Open search settings</a></div></div>`;
      return;
    }
    bar.hidden = false;
    byId("results-count").textContent = items.length + (items.length === 1 ? " job" : " jobs");
    let totalRemoved = 0;
    if (state.countsRemoved) {
      totalRemoved = Object.values(state.countsRemoved).reduce((a, b) => a + (Number(b) || 0), 0);
    }
    const clientHidden = state.jobs.length - items.length;
    const totalHidden = totalRemoved + clientHidden;
    byId("results-meta").textContent = totalHidden > 0 ? totalHidden + " hidden by filters" : "";
    if (!items.length) {
      list.innerHTML = "";
      st.innerHTML = `<div class="empty"><h2>Filters hide all ${state.jobs.length} jobs</h2><p>Loosen a filter to see them.</p><button class="btn btn-secondary" type="button" data-clear-filters>Clear filters</button></div>`;
      return;
    }
    list.innerHTML = items.map(jobCardHtml).join("");
  }

  function currentJob() {
    return state.selectedId == null ? null : jobByKey(state.selectedId);
  }

  /* ---------- the drawer */
  function renderDetail() {
    const box = byId("job-detail");
    const j = currentJob();
    if (!j) { box.innerHTML = ""; return; }
    const items = visibleJobs();
    const pos = items.findIndex((x) => x.key === state.selectedId);
    const app = findApp(j);
    const url = jobUrl(j);
    const tier = tierOf(j.score);
    const meta = [
      `<span class="co" dir="auto">${esc(j.company || "Company not listed")}</span>`,
      j.location ? `<span dir="auto">${esc(j.location)}</span>` : "",
      j.work_mode && !(j.location || "").toLowerCase().includes(String(j.work_mode).toLowerCase()) ? `<span>${esc(j.work_mode)}</span>` : "",
      j.job_type ? `<span>${esc(j.job_type)}</span>` : "",
      j.salary ? `<span>${esc(j.salary)}</span>` : "",
      j.source ? `<span>via ${esc(j.source)}</span>` : "",
      j.posted_days_ago != null ? `<span>${esc(daysAgo(j.posted_days_ago))}</span>` : "",
    ].filter(Boolean).join("");

    const inPipeline = app && app.status !== "saved";
    const saveBtn = app && app.status === "saved"
      ? `<button class="btn btn-secondary" type="button" disabled>${icon("bookmark-check")}<span>Saved</span></button>`
      : app ? "" : `<button class="btn btn-secondary" type="button" data-act="save" data-key="${esc(state.selectedId)}">${icon("bookmark")}<span>Save</span></button>`;
    const dismissBtn = `<button class="btn btn-quiet" type="button" data-act="dismiss" data-key="${esc(state.selectedId)}">${icon("x")}<span>Dismiss</span></button>`;
    const applyBtn = inPipeline
      ? `<a class="btn btn-secondary" href="#/applications">${icon("square-kanban")}<span>${esc(STAGE_LABEL[app.status] || "Tracked")} in Applications</span></a>`
      : `<button class="btn btn-primary" type="button" data-act="apply" data-key="${esc(state.selectedId)}"${url ? "" : " disabled"}>${icon("send")}<span>Apply with extension</span></button>`;

    const matched = j.matched_skills || [];
    const terms = matched.concat(profileTerms());
    const post = j.description ? markText(j.description, terms) : null;

    let fitBlock;
    if (typeof j.score === "number") {
      const role = state.active && state.active.target_title ? " with " + esc(state.active.target_title) : " with your resume";
      fitBlock = `<div class="fit-line" data-tier="${tier}"><span class="fit-big">${Math.round(j.score)}%</span><span>${TIER_WORD[tier].toLowerCase()}${role}</span></div>`;
      if ((j.match_reasons || []).length) fitBlock += `<ul class="reasons">${j.match_reasons.map((r) => `<li dir="auto">${esc(r)}</li>`).join("")}</ul>`;
      else fitBlock += `<p class="hint">No written reasons came with this score.</p>`;
    } else {
      fitBlock = `<p>${state.active ? "JobHunter did not score this posting. Read it and decide for yourself." : "No fit score yet. Add your resume so JobHunter can compare it with this posting."}</p>` +
        (state.active ? "" : `<a class="btn btn-secondary btn-sm" href="#/resume">Add resume</a>`);
    }
    const matchedBlock = matched.length
      ? `<div class="matched" aria-label="Skills from your resume that this posting asks for">${matched.map((s, i) => `<span class="mk" style="--i:${Math.min(i, 10)}">${esc(s)}</span>`).join("")}</div><p class="legend">Highlighted terms come from your resume.</p>`
      : "";

    const writeRows = [
      ["cover-letter", "Cover letter", "Built from your resume facts"],
      ["tailor-resume", "Tailored resume", "Your resume, reordered for this posting"],
      ["interview-prep", "Interview prep", "STAR stories from your experience"],
      ["outreach", "Recruiter message", "LinkedIn note and a message to the hiring manager"],
    ].map(([k, t, d]) => `<button class="write-row" type="button" data-doc="${k}"><span><span class="t">${t}</span><span class="d">${d}</span></span><span class="go">${icon("chevron-right")}</span></button>`).join("");

    box.innerHTML = `
      <div class="drawer-bar">
        <button class="btn btn-quiet btn-icon" type="button" data-close aria-label="Close details">${icon("x")}</button>
        <span class="count">${pos >= 0 ? `${pos + 1} of ${items.length}` : ""}</span>
        <span class="drawer-nav">
          <button class="btn btn-quiet btn-icon" type="button" data-step="-1" aria-label="Previous job"${pos <= 0 ? " disabled" : ""}>${icon("chevron-down", "flip")}</button>
          <button class="btn btn-quiet btn-icon" type="button" data-step="1" aria-label="Next job"${pos < 0 || pos >= items.length - 1 ? " disabled" : ""}>${icon("chevron-down")}</button>
        </span>
      </div>
      <div class="drawer-body">
        <header class="detail-head"><div class="dh-top"><span class="avatar lg" aria-hidden="true">${esc(initialOf(j.company))}</span>${scoreBadge(j.score)}</div><h2 id="drawer-title" dir="auto">${esc(j.title || "Untitled role")}</h2><div class="detail-meta">${meta}</div></header>
        <div class="detail-actions">${applyBtn}${saveBtn}${dismissBtn}${url ? `<a class="btn btn-quiet" href="${esc(url)}" target="_blank" rel="noopener noreferrer"><span>Open posting</span>${icon("external-link")}</a>` : ""}</div>
        <section class="detail-section" aria-labelledby="h-fit"><h3 id="h-fit">Why it fits</h3>${fitBlock}${matchedBlock}</section>
        <section class="detail-section" aria-labelledby="h-post"><h3 id="h-post">Posting</h3>
          ${post ? `<div class="posting-wrap"><div class="posting sweep" dir="auto">${post.html}</div></div>${post.count ? `<p class="legend">${post.count} ${post.count === 1 ? "term" : "terms"} from your resume ${post.count === 1 ? "is" : "are"} highlighted.</p>` : ""}` : `<p>This job came without a description.${url ? " Open the posting to read it." : ""}</p>`}
        </section>
        <section class="detail-section" aria-labelledby="h-write"><h3 id="h-write">Write for this job</h3><div class="write-list">${writeRows}</div></section>
      </div>`;
    byId("job-drawer").setAttribute("aria-labelledby", "drawer-title");
    byId("job-drawer").scrollTop = 0;
  }

  function syncSelection() {
    const dlg = byId("job-drawer");
    const j = currentJob();
    $$(".job-card[data-tier]").forEach((c) => c.removeAttribute("aria-current"));
    if (j) {
      lastOpenKey = state.selectedId;
      renderDetail();
      if (!dlg.open) dlg.showModal();
      const card = $(`.job-open[data-key="${CSS.escape(state.selectedId)}"]`);
      if (card) card.closest(".job-card").setAttribute("aria-current", "true");
    } else if (dlg.open) {
      dlg.close();
    }
  }

  function selectJob(key, replace) {
    const target = "#/jobs/" + encodeURIComponent(key);
    if (replace) {
      history.replaceState(null, "", target);
      state.selectedId = key;
      syncSelection();
    } else if (location.hash === target) {
      state.selectedId = key;
      syncSelection();
    } else {
      location.hash = target;
    }
  }

  function stepSelection(delta) {
    const items = visibleJobs();
    if (!items.length) return;
    const i = items.findIndex((x) => x.key === state.selectedId);
    const next = items[Math.min(items.length - 1, Math.max(0, i < 0 ? 0 : i + delta))];
    selectJob(next.key, true);
  }

  function moveSelection(delta) {
    if (state.selectedId != null) { stepSelection(delta); return; }
    const opens = $$(".job-open");
    if (!opens.length) return;
    const i = opens.indexOf(document.activeElement);
    const next = opens[Math.min(opens.length - 1, Math.max(0, i < 0 ? 0 : i + delta))];
    next.focus();
    next.scrollIntoView({ block: "nearest" });
  }

  function persistSearch() {
    ssSet("jh-search", { q: state.query, loc: state.place, jobs: state.jobs, at: Date.now() });
  }

  async function runSearch() {
    if (state.searching) { if (searchCtl) searchCtl.abort(); return; }
    const q = byId("q").value.trim();
    const loc = byId("loc").value.trim();
    clearFieldError(byId("q"));
    if (!q && !state.active) {
      setFieldError(byId("q"), "Type a role or keywords, or add your resume first.");
      byId("q").focus();
      return;
    }
    state.query = q;
    state.place = loc;
    searchError = null;
    state.searching = true;
    searchCtl = new AbortController();
    const btn = byId("btn-search");
    btn.setAttribute("aria-busy", "true");
    btn.innerHTML = `${icon("x")}<span>Stop search</span>`;
    renderJobs();
    try {
      const params = new URLSearchParams({ q, location: loc, work_mode: "Any", job_type: "", min_score: "0" });
      const d = await apiGet("/api/search?" + params.toString(), searchCtl.signal);
      state.jobs = (d && d.jobs) || [];
      state.searched = true;
      persistSearch();
      try { await loadJobsQuery(); } catch (qe) { /* fallback to d.jobs */ }
    } catch (e) {
      if (e.name === "AbortError") toast("Search stopped.");
      else searchError = e;
    } finally {
      state.searching = false;
      btn.removeAttribute("aria-busy");
      btn.innerHTML = `${icon("search")}<span>Search jobs</span>`;
    }
    state.selectedId = null;
    if (location.hash !== "#/jobs") history.replaceState(null, "", "#/jobs");
    renderJobs();
    syncSelection();
  }

  /* ------------------------------------------------------------ V5 View Query & Filtering */
  async function loadJobsQuery() {
    try {
      const payload = {
        filters: {
          job_style: state.query || "tech jobs",
          work_mode: state.filters.mode || "any",
          contract_types: state.filters.type ? [state.filters.type] : [],
          min_salary: state.filters.min_salary || 0,
          seniority: state.filters.seniority ? [state.filters.seniority] : [],
          locations: state.place ? [state.place] : [],
          show_unknown_salary: state.filters.show_unknown_salary !== false,
        },
        sort_by: state.sort === "date" ? "date" : "rank",
        limit: 100,
      };
      const res = await apiPost("/api/jobs/query", payload);
      if (res && res.results) {
        state.jobs = res.results;
        state.closingSoon = res.closing_soon || [];
        state.countsRemoved = res.counts_removed || {};
        state.usableGate = res.gate || { status: "usable", message: "" };
        state.searched = true;
        renderJobs();
        if (typeof renderClosingSoon === "function") renderClosingSoon();
        if (typeof updateFilterBadges === "function") updateFilterBadges();
        if (typeof updateUsabilityBanner === "function") updateUsabilityBanner();
      }
    } catch (e) {
      console.warn("Could not query jobs via V5 API:", e);
    }
  }

  /* ------------------------------------------------------------ V8 Method Selection & Dual-Track */
  function initMethod() {
    const saved = lsGet("jobhunter_method");
    if (saved === "classic" || saved === "modern") {
      state.method = saved;
    } else {
      state.method = "modern"; // Modern is default
    }

    const btnMod = byId("btn-method-modern");
    const btnCls = byId("btn-method-classic");
    if (btnMod) btnMod.addEventListener("click", () => setMethod("modern"));
    if (btnCls) btnCls.addEventListener("click", () => setMethod("classic"));

    const btnSelMod = byId("btn-select-modern");
    const btnSelCls = byId("btn-select-classic");
    const dlgOnboard = byId("dlg-method-onboarding");
    if (btnSelMod && dlgOnboard) {
      btnSelMod.addEventListener("click", () => {
        lsSet("jobhunter_method_chosen", "true");
        dlgOnboard.close();
        setMethod("modern");
      });
    }
    if (btnSelCls && dlgOnboard) {
      btnSelCls.addEventListener("click", () => {
        lsSet("jobhunter_method_chosen", "true");
        dlgOnboard.close();
        setMethod("classic");
      });
    }

    // Check first visit onboarding
    if (!lsGet("jobhunter_method_chosen") && dlgOnboard) {
      closeOnBackdrop(dlgOnboard);
      setTimeout(() => {
        if (!dlgOnboard.open && !lsGet("jobhunter_method_chosen")) {
          dlgOnboard.showModal();
        }
      }, 600);
    }

    updateMethodUI();
  }

  function updateMethodUI() {
    const isModern = state.method === "modern";
    const btnMod = byId("btn-method-modern");
    const btnCls = byId("btn-method-classic");
    if (btnMod) btnMod.classList.toggle("active", isModern);
    if (btnCls) btnCls.classList.toggle("active", !isModern);

    // Nav items visibility
    const sigWrap = byId("nav-item-signals-wrap");
    const outWrap = byId("nav-item-outreach-wrap");
    const tabSig = byId("tabbar-signals");
    const tabOut = byId("tabbar-outreach");

    if (sigWrap) sigWrap.style.display = isModern ? "" : "none";
    if (outWrap) outWrap.style.display = isModern ? "" : "none";
    if (tabSig) tabSig.style.display = isModern ? "" : "none";
    if (tabOut) tabOut.style.display = isModern ? "" : "none";

    updateRadarHeaderUI();
  }

  async function setMethod(method, saveBackend = true) {
    if (method !== "modern" && method !== "classic") return;
    state.method = method;
    lsSet("jobhunter_method", method);
    lsSet("jobhunter_method_chosen", "true");
    lsSet("jobhunter_method_manual_override", "true");
    updateMethodUI();

    if (saveBackend) {
      try {
        await apiPost("/api/method", { method });
      } catch (e) {
        console.warn("Could not sync method with backend:", e);
      }
    }

    // Route dynamically based on method
    if (method === "modern") {
      if (state.route === "jobs") go("signals");
      toast("Switched to Modern outreach track (Signals & Direct Contacts).");
    } else {
      if (state.route === "signals" || state.route === "outreach") go("jobs");
      toast("Switched to Classic track (Job boards & Apply button).");
    }
  }

  /* ------------------------------------------------------------ Header Radar & Method UI */
  async function pollRadarStatus() {
    try {
      const data = await apiGet("/api/radar/status");
      if (!data) return;

      // Sync active method if returned from backend
      if (data.method && (data.method === "modern" || data.method === "classic") && !lsGet("jobhunter_method_manual_override")) {
        if (state.method !== data.method) {
          state.method = data.method;
          updateMethodUI();
        }
      }

      state.radar = {
        running: !!data.running,
        status: data.status || "idle",
        matches: data.active_filter_matches || data.new_jobs_count || 0,
        newSignals: data.new_signals_count || (data.new_count && data.method === "modern" ? data.new_count : 0),
        newJobs: data.new_jobs_count || data.unread_jobs || 0,
        failureCount: data.failure_count || 0,
        lastPoll: data.last_poll_at,
        nextPoll: data.next_poll_at,
        backoffSeconds: data.backoff_seconds || 0,
        warning: data.warning || data.last_error,
      };
      updateRadarHeaderUI();
    } catch (e) {
      /* ignore offline errors */
    }
  }

  function updateRadarHeaderUI() {
    const btn = byId("btn-radar-header");
    if (!btn) return;
    const dot = byId("radar-header-dot");
    const badge = byId("radar-header-badge");
    const label = byId("radar-header-label");

    const isModern = state.method === "modern";
    const count = isModern ? (state.radar.newSignals || 0) : (state.radar.matches || state.radar.newJobs || 0);

    if (label) {
      label.textContent = isModern ? "Signals Radar" : "Radar";
    }

    if (dot) {
      dot.className = "radar-dot";
      if (!state.radar.running) {
        dot.classList.add("off");
      } else if (state.radar.failureCount >= 3 || state.radar.warning || state.radar.backoffSeconds > 0) {
        dot.classList.add("warning");
      }
    }

    if (badge) {
      if (count > 0) {
        badge.textContent = String(count);
        badge.hidden = false;
        const noun = isModern ? "signal" : "job";
        btn.setAttribute("title", `Radar: ${count} new ${noun}(s) found. Click to open and clear count.`);
      } else {
        badge.hidden = true;
        let hint = state.radar.running ? (isModern ? "Signal Radar: Watching for hiring posts & funding news" : "LinkedIn Radar: Watching for new matches") : "Radar: Idle";
        if (state.radar.failureCount >= 3 || state.radar.backoffSeconds > 0) {
          const retryMins = Math.max(1, Math.round((state.radar.backoffSeconds || 120) / 60));
          hint = `Radar backed off after ${state.radar.failureCount} error(s). Retrying in ~${retryMins} minutes.`;
        }
        btn.setAttribute("title", hint);
      }
    }
  }

  async function onRadarHeaderClick() {
    const isModern = state.method === "modern";
    const count = isModern ? state.radar.newSignals : state.radar.matches;
    try {
      await apiPost("/api/radar/ack", { target: isModern ? "signals" : "jobs" });
      if (isModern) {
        state.radar.newSignals = 0;
      } else {
        state.radar.matches = 0;
        state.radar.newJobs = 0;
      }
      updateRadarHeaderUI();

      if (isModern) {
        if (state.route !== "signals") go("signals");
        else await loadSignalsQuery();
      } else {
        if (state.route !== "jobs") go("jobs");
        else await loadJobsQuery();
      }

      if (count > 0) {
        toast(`Acknowledged ${count} new radar ${isModern ? "signal" : "job"}(s).`);
      }
    } catch (e) {
      toast("Could not acknowledge radar updates: " + e.message, { kind: "bad" });
    }
  }

  async function pollCleanupStatus() {
    try {
      const data = await apiGet("/api/cleanup/status");
      if (!data) return;
      state.cleanup = {
        graceHours: data.grace_hours || 24,
        expiringSoonCount: data.expiring_soon_count || 0,
        expiringJobs: data.expiring_jobs || [],
        lastDeletedCount: data.last_deleted_count || 0,
        unacknowledgedDeletions: data.unacknowledged_deletions || 0,
      };
      updateLifecycleBannerUI();
      if (data.unacknowledged_deletions > 0 && data.last_deleted_count > 0) {
        toast(`${data.last_deleted_count} expired job(s) reached the grace period and were cleaned up. Tombstones recorded.`, {
          action: { label: "Dismiss", run: () => apiPost("/api/cleanup/ack") }
        });
      }
    } catch (e) {
      /* ignore */
    }
  }

  function updateLifecycleBannerUI() {
    const banner = byId("banner-lifecycle");
    if (!banner) return;
    const count = state.cleanup.expiringSoonCount;
    if (count > 0) {
      const text = byId("banner-lifecycle-text");
      if (text) {
        const minHours = state.cleanup.expiringJobs.length ? Math.min(...state.cleanup.expiringJobs.map(j => j.hours_remaining || 24)) : 24;
        text.textContent = `${count} job${count === 1 ? "" : "s"} expiring in ${Math.round(minHours)} hour${Math.round(minHours) === 1 ? "" : "s"}. Expired postings will be removed after the grace period.`;
      }
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  }

  async function onKeepExpiringJobs() {
    try {
      const ids = state.cleanup.expiringJobs.map(j => j.id);
      if (!ids.length) return;
      await apiPost("/api/cleanup/keep", { job_ids: ids });
      state.cleanup.expiringSoonCount = 0;
      state.cleanup.expiringJobs = [];
      updateLifecycleBannerUI();
      toast("Saved expiring jobs. They will not be deleted.");
      await loadJobsQuery();
    } catch (e) {
      toast("Could not keep jobs: " + e.message, { kind: "bad" });
    }
  }

  async function onAckLifecycleBanner() {
    try {
      await apiPost("/api/cleanup/ack");
      const banner = byId("banner-lifecycle");
      if (banner) banner.hidden = true;
    } catch (e) {
      const banner = byId("banner-lifecycle");
      if (banner) banner.hidden = true;
    }
  }

  function setFieldError(input, msg) {
    clearFieldError(input);
    input.setAttribute("aria-invalid", "true");
    const f = input.closest(".field");
    const p = document.createElement("span");
    p.className = "field-error";
    p.id = (input.id || "f") + "-err";
    p.textContent = msg;
    input.setAttribute("aria-describedby", p.id);
    f.appendChild(p);
  }
  function clearFieldError(input) {
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
    const f = input.closest(".field");
    if (f) $$(".field-error", f).forEach((n) => n.remove());
  }

  async function reloadApps() {
    try {
      const d = await apiGet("/api/applications");
      state.apps = (d && d.applications) || [];
      state.appsLoaded = true;
    } catch (e) { /* keep the previous list */ }
    updateAppCount();
  }

  function updateAppCount() {
    const n = state.apps.filter((a) => a.status !== "rejected").length;
    const el = byId("nav-count-apps");
    el.textContent = n ? String(n) : "";
    el.style.display = n ? "" : "none";
  }

  async function saveJob(j, status) {
    const existing = findApp(j);
    if (existing) {
      if (existing.status === status || status === "saved") return existing;
      await apiPost("/api/applications", { id: existing.id, status });
    } else {
      await apiPost("/api/applications", {
        title: j.title || "",
        company: j.company || "",
        location: j.location || "",
        salary: j.salary || "",
        url: jobUrl(j),
        status,
        job_id: j.id || j.job_key || "",
        job_data: j
      });
    }
    await reloadApps();
    return findApp(j);
  }

  function refreshJobViews() {
    if (state.route !== "jobs") return;
    const y = window.scrollY, main = byId("main").scrollTop, drawer = byId("job-drawer").scrollTop;
    renderJobs();
    if (currentJob()) { renderDetail(); byId("job-drawer").scrollTop = drawer; }
    window.scrollTo(0, y);
    byId("main").scrollTop = main;
  }

  let pendingSaveJob = null;
  let pendingDismissJob = null;
  let activeProposal = null;

  async function onSave(key, opts) {
    opts = opts || {};
    const j = jobByKey(key != null ? key : state.selectedId);
    if (!j) return;
    pendingSaveJob = j;

    const payload = {
      job_id: j.id || j.job_key,
      id: j.id || j.job_key,
      title: j.title || "",
      company: j.company || "",
      location: j.location || "",
      salary: j.salary || "",
      url: jobUrl(j),
      force: !!opts.force,
      confirm_closed: !!opts.confirm_closed,
      job_data: j
    };

    try {
      toast("Evaluating fit and posting status...", { kind: "info" });
      const res = await apiPost("/api/jobs/save", payload);
      if (!res) return;

      if (res.status === "needs_confirm") {
        const dlg = byId("dlg-closed-confirm");
        if (dlg) dlg.showModal();
        return;
      }

      if (res.status === "low_fit") {
        const dlg = byId("dlg-low-fit");
        if (dlg) {
          const scoreEl = byId("low-fit-score");
          if (scoreEl) scoreEl.textContent = String(res.fit_score || 0);

          const gapsEl = byId("low-fit-gaps");
          const gaps = (res.gap_report && res.gap_report.missing_requirements) || [];
          if (gapsEl) {
            gapsEl.innerHTML = gaps.length ? gaps.map((g) => `<li>${esc(g)}</li>`).join("") : "<li>No specific skills missing</li>";
          }

          const trackEl = byId("low-fit-track");
          const tracks = (res.gap_report && res.gap_report.talking_track) || [];
          if (trackEl) {
            trackEl.innerHTML = tracks.length ? tracks.map((t) => `<p>${esc(t)}</p>`).join("") : "<p>Emphasize rapid adaptability and related toolchains.</p>";
          }

          const addTrueEl = byId("low-fit-add-true");
          const addTrueSec = byId("low-fit-add-true-sec");
          const addList = (res.gap_report && res.gap_report.add_this_if_true) || [];
          if (addTrueEl && addTrueSec) {
            if (addList.length) {
              addTrueSec.hidden = false;
              addTrueEl.innerHTML = addList.map((a) => `<li>${esc(a)}</li>`).join("");
            } else {
              addTrueSec.hidden = true;
            }
          }

          dlg.showModal();
        }
        return;
      }

      // Success
      pendingSaveJob = null;
      await reloadApps();
      refreshJobViews();
      toast("Saved! Tailored resume & cover letter generated in outputs/.", {
        action: { label: "View in Applications", run: () => go("applications") }
      });
    } catch (e) {
      toast("Could not save job: " + e.message, { kind: "bad" });
    }
  }

  function openDismissDialog(key) {
    const j = jobByKey(key != null ? key : state.selectedId);
    if (!j) return;
    pendingDismissJob = j;
    const dlg = byId("dlg-dismiss-reasons");
    if (dlg) dlg.showModal();
  }

  async function onDismiss(reason) {
    const dlg = byId("dlg-dismiss-reasons");
    if (dlg) dlg.close();
    if (!pendingDismissJob) return;

    const j = pendingDismissJob;
    const jid = j.id || j.job_key;
    try {
      const res = await apiPost("/api/jobs/dismiss", { job_id: jid, reason: reason || "Other" });
      state.jobs = state.jobs.filter((x) => (x.id || x.job_key) !== jid);
      renderJobs();
      syncSelection();
      toast(`Dismissed posting (${reason || "Other"}).`);

      if (res && res.proposal) {
        showFilterProposal(res.proposal);
      }
    } catch (e) {
      toast("Could not dismiss job: " + e.message, { kind: "bad" });
    } finally {
      pendingDismissJob = null;
    }
  }

  function showFilterProposal(proposal) {
    activeProposal = proposal;
    const dlg = byId("dlg-filter-proposal");
    if (!dlg) return;
    const msgEl = byId("filter-proposal-message");
    if (msgEl) {
      msgEl.textContent = proposal.message || "Based on your recent dismissals, tuning view filters could improve matching jobs.";
    }
    dlg.showModal();
  }

  async function onApply(key) {
    const j = jobByKey(key != null ? key : state.selectedId);
    if (!j || !jobUrl(j)) return;
    try {
      await saveJob(j, "queued");
      refreshJobViews();
      await apiPost("/api/auto-apply/launch", { url: jobUrl(j) });
      toast("Queued. A browser with the extension is opening on this job.", { action: { label: "View", run: () => go("applications") } });
    } catch (e) { toast(e.message, { kind: "bad" }); }
  }

  function syncSelectionAfterFilter() {
    if (state.selectedId == null) return;
    if (!visibleJobs().some((x) => x.key === state.selectedId)) {
      state.selectedId = null;
      if (location.hash !== "#/jobs") history.replaceState(null, "", "#/jobs");
      syncSelection();
    } else renderDetail();
  }

  function initJobs() {
    if (jobsInit) return;
    jobsInit = true;
    renderFilterSegs();

    byId("search-form").addEventListener("submit", (e) => { e.preventDefault(); runSearch(); });
    byId("q").addEventListener("input", () => clearFieldError(byId("q")));

    byId("filter-toggle").addEventListener("click", (e) => {
      const body = byId("filters-body");
      const open = body.hidden;
      body.hidden = !open;
      e.currentTarget.setAttribute("aria-expanded", String(open));
    });
    byId("filters-body").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-v]");
      if (!b) return;
      const key = b.closest(".seg").dataset.filter;
      state.filters[key] = key === "fit" ? Number(b.dataset.v) : b.dataset.v;
      renderFilterSegs();
      if (state.searched) {
        loadJobsQuery();
      } else {
        renderJobs();
        syncSelectionAfterFilter();
      }
    });

    const fltSalary = byId("flt-salary");
    if (fltSalary) {
      fltSalary.addEventListener("change", (e) => {
        state.filters.min_salary = Math.max(0, Number(e.target.value) || 0);
        renderFilterSegs();
        if (state.searched) loadJobsQuery();
      });
    }

    const fltUnknownSal = byId("flt-unknown-sal");
    if (fltUnknownSal) {
      fltUnknownSal.addEventListener("change", (e) => {
        state.filters.show_unknown_salary = e.target.checked;
        if (state.searched) loadJobsQuery();
      });
    }

    const closingWrap = byId("closing-soon-wrap");
    if (closingWrap) {
      closingWrap.addEventListener("click", async (e) => {
        const btn = e.target.closest("[data-act='keep-job']");
        if (!btn) return;
        const id = Number(btn.dataset.id);
        if (!id) return;
        try {
          await apiPost("/api/cleanup/keep", { job_ids: [id] });
          toast("Job saved and protected from deletion.");
          await loadJobsQuery();
          await pollCleanupStatus();
        } catch (err) {
          toast("Could not keep job: " + err.message, { kind: "bad" });
        }
      });
    }

    byId("sort").addEventListener("change", (e) => {
      state.sort = e.target.value;
      if (state.searched) loadJobsQuery();
      else renderJobs();
    });

    byId("job-list").addEventListener("click", (e) => {
      const act = e.target.closest("[data-act]");
      if (act) {
        const key = act.dataset.key;
        if (act.dataset.act === "save") onSave(key);
        else if (act.dataset.act === "dismiss") openDismissDialog(key);
        else if (act.dataset.act === "apply") onApply(key);
        else if (act.dataset.act === "details") selectJob(key);
        else if (act.dataset.act === "copy-link") {
          const j = jobByKey(key);
          copyText(j ? jobUrl(j) : "").then((ok) => toast(ok ? "Posting link copied." : "Copy failed."));
        }
        return;
      }
      const open = e.target.closest(".job-open");
      if (open) { selectJob(open.dataset.key); return; }
      const card = e.target.closest(".job-card");
      if (card && !e.target.closest("a, button")) { const b = $(".job-open", card); if (b) selectJob(b.dataset.key); }
    });

    byId("job-state").addEventListener("click", (e) => {
      if (e.target.closest("[data-retry]")) runSearch();
      if (e.target.closest("[data-search-target]")) { byId("q").value = state.active.target_title; runSearch(); }
      if (e.target.closest("[data-clear-filters]")) { state.filters = { mode: "", type: "", fit: 0 }; renderFilterSegs(); renderJobs(); }
      if (e.target.closest("[data-clear-place]")) { byId("loc").value = ""; runSearch(); }
    });

    const dlg = byId("job-drawer");
    closeOnBackdrop(dlg);
    dlg.addEventListener("close", () => {
      if (state.selectedId != null) { state.selectedId = null; go("jobs"); }
      const back = lastOpenKey != null ? $(`.job-open[data-key="${CSS.escape(lastOpenKey)}"]`) : null;
      if (back && state.route === "jobs") back.focus({ preventScroll: true });
    });
    byId("job-detail").addEventListener("click", (e) => {
      if (e.target.closest("[data-close]")) { dlg.close(); return; }
      const st = e.target.closest("[data-step]");
      if (st) { stepSelection(Number(st.dataset.step)); return; }
      const a = e.target.closest("[data-act]");
      if (a) {
        if (a.dataset.act === "save") onSave(a.dataset.key);
        else if (a.dataset.act === "dismiss") { dlg.close(); openDismissDialog(a.dataset.key); }
        else if (a.dataset.act === "apply") onApply(a.dataset.key);
        return;
      }
      const w = e.target.closest("[data-doc]");
      if (w) {
        const j = currentJob();
        if (j) state.docDraft = { kind: w.dataset.doc, title: j.title || "", company: j.company || "", description: j.description || "" };
        state.selectedId = null;
        dlg.close();
        go("documents");
      }
    });

    // V5 Dialog Wire-ups
    const closedDlg = byId("dlg-closed-confirm");
    if (closedDlg) {
      closeOnBackdrop(closedDlg);
      const btnSkip = byId("btn-closed-skip");
      if (btnSkip) btnSkip.addEventListener("click", () => { closedDlg.close(); pendingSaveJob = null; });
      const btnConf = byId("btn-closed-confirm");
      if (btnConf) btnConf.addEventListener("click", () => {
        closedDlg.close();
        if (pendingSaveJob) {
          onSave(jobKey(pendingSaveJob), { confirm_closed: true });
        }
      });
    }

    const lowFitDlg = byId("dlg-low-fit");
    if (lowFitDlg) {
      closeOnBackdrop(lowFitDlg);
      const btnSkip = byId("btn-low-fit-skip");
      if (btnSkip) btnSkip.addEventListener("click", () => { lowFitDlg.close(); pendingSaveJob = null; });
      const btnSave = byId("btn-low-fit-save");
      if (btnSave) btnSave.addEventListener("click", () => {
        lowFitDlg.close();
        if (pendingSaveJob) {
          onSave(jobKey(pendingSaveJob), { force: true, confirm_closed: true });
        }
      });
    }

    const dismissDlg = byId("dlg-dismiss-reasons");
    if (dismissDlg) {
      closeOnBackdrop(dismissDlg);
      const btnCancel = byId("btn-dismiss-cancel");
      if (btnCancel) btnCancel.addEventListener("click", () => { dismissDlg.close(); pendingDismissJob = null; });
      const chipList = byId("dismiss-chips");
      if (chipList) chipList.addEventListener("click", (e) => {
        const chip = e.target.closest(".chip-btn");
        if (chip) onDismiss(chip.dataset.reason);
      });
    }

    const proposalDlg = byId("dlg-filter-proposal");
    if (proposalDlg) {
      closeOnBackdrop(proposalDlg);
      const btnDismiss = byId("btn-proposal-dismiss");
      if (btnDismiss) btnDismiss.addEventListener("click", () => { proposalDlg.close(); activeProposal = null; });
      const btnApply = byId("btn-proposal-apply");
      if (btnApply) btnApply.addEventListener("click", () => {
        proposalDlg.close();
        if (activeProposal) {
          if (activeProposal.type === "salary") {
            state.filters.min_salary = Math.max(state.filters.min_salary || 0, 100000);
            const fltSal = byId("flt-salary");
            if (fltSal) fltSal.value = String(state.filters.min_salary);
          } else if (activeProposal.type === "work_mode") {
            state.filters.mode = "Remote";
            renderFilterSegs();
          } else if (activeProposal.type === "seniority") {
            state.filters.seniority = "senior";
            renderFilterSegs();
          } else {
            const body = byId("filters-body");
            if (body) body.hidden = false;
          }
          activeProposal = null;
          toast("Updated view filters based on feedback.");
          loadJobsQuery();
        }
      });
    }

    const cached = ssGet("jh-search");
    if (cached && Array.isArray(cached.jobs)) {
      state.jobs = cached.jobs;
      state.searched = true;
      state.query = cached.q || "";
      state.place = cached.loc || "";
      byId("q").value = state.query;
      byId("loc").value = state.place;
    }
  }

  function jobsNotice() {
    const box = byId("resume-notice");
    if (state.profilesLoaded && !state.active) {
      box.innerHTML = `<div class="notice warn">${icon("triangle-alert")}<div><p><strong>Add your resume to see fit scores.</strong></p><p>Without it, jobs show no score and documents have nothing to draw from.</p><div class="actions"><a class="btn btn-secondary btn-sm" href="#/resume">Add resume</a></div></div></div>`;
    } else {
      box.innerHTML = "";
    }
  }

  routeHooks.jobs = (arg, changed) => {
    initJobs();
    if (changed) {
      const sub = state.active ? "Fit scores compare each role with " + (state.active.name || "your resume") + "." : PAGES.jobs.sub;
      setHead("Jobs", sub, "");
      jobsNotice();
      renderJobs();
    }
    state.selectedId = arg || null;
    if (arg && !currentJob()) {
      state.selectedId = null;
      history.replaceState(null, "", "#/jobs");
    }
    syncSelection();
  };

  /* ============================================================ MODERN TRACK: SIGNALS ============================================================ */
  let signalsInit = false;

  function initSignals() {
    if (signalsInit) return;
    signalsInit = true;

    const form = byId("signals-filter-form");
    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        loadSignalsQuery();
      });
      const qInput = byId("sig-q");
      if (qInput) {
        qInput.addEventListener("input", debounce(() => {
          state.signalsFilter.q = qInput.value.trim();
          loadSignalsQuery();
        }, 250));
      }
      const stageSelect = byId("sig-stage");
      if (stageSelect) {
        stageSelect.addEventListener("change", () => {
          state.signalsFilter.stage = stageSelect.value;
          loadSignalsQuery();
        });
      }
      const typeSelect = byId("sig-type");
      if (typeSelect) {
        typeSelect.addEventListener("change", () => {
          state.signalsFilter.type = typeSelect.value;
          loadSignalsQuery();
        });
      }
    }

    const lateToggle = byId("sig-late-toggle");
    if (lateToggle) {
      lateToggle.addEventListener("change", () => {
        state.signalsFilter.includeLate = lateToggle.checked;
        const lateWrap = byId("signals-late-wrap");
        if (lateWrap) lateWrap.hidden = !lateToggle.checked;
      });
    }

    // Modal close listeners
    const briefDone = byId("btn-brief-done");
    if (briefDone) briefDone.addEventListener("click", () => byId("dlg-company-brief").close());
    const briefClose = byId("btn-brief-close");
    if (briefClose) briefClose.addEventListener("click", () => byId("dlg-company-brief").close());

    // Brief tabs
    const tabFacts = byId("tab-brief-facts");
    const tabLearn = byId("tab-brief-learning");
    if (tabFacts && tabLearn) {
      tabFacts.addEventListener("click", () => {
        tabFacts.classList.add("active");
        tabFacts.setAttribute("aria-selected", "true");
        tabLearn.classList.remove("active");
        tabLearn.setAttribute("aria-selected", "false");
        byId("pane-brief-facts").hidden = false;
        byId("pane-brief-learning").hidden = true;
      });
      tabLearn.addEventListener("click", () => {
        tabLearn.classList.add("active");
        tabLearn.setAttribute("aria-selected", "true");
        tabFacts.classList.remove("active");
        tabFacts.setAttribute("aria-selected", "false");
        byId("pane-brief-facts").hidden = true;
        byId("pane-brief-learning").hidden = false;
      });
    }

    // Contacts drawer close
    const btnContactsClose = byId("btn-contacts-drawer-close");
    if (btnContactsClose) btnContactsClose.addEventListener("click", () => byId("dlg-contacts-panel").close());

    // Contacts actions
    const btnCopyOutreach = byId("btn-copy-outreach");
    if (btnCopyOutreach) {
      btnCopyOutreach.addEventListener("click", () => {
        const bodyText = byId("outreach-email-body").value;
        const subjText = byId("outreach-email-subject").value;
        const full = `Subject: ${subjText}\n\n${bodyText}`;
        navigator.clipboard.writeText(full).then(() => toast("Copied email draft to clipboard."));
      });
    }

    const btnMailto = byId("btn-mailto-outreach");
    if (btnMailto) {
      btnMailto.addEventListener("click", () => {
        const bodyText = encodeURIComponent(byId("outreach-email-body").value);
        const subjText = encodeURIComponent(byId("outreach-email-subject").value);
        const toEmail = state.activeContacts && state.activeContacts[0] && state.activeContacts[0].email ? encodeURIComponent(state.activeContacts[0].email) : "";
        window.location.href = `mailto:${toEmail}?subject=${subjText}&body=${bodyText}`;
      });
    }

    const btnMarkSent = byId("btn-mark-sent-outreach");
    if (btnMarkSent) {
      btnMarkSent.addEventListener("click", onMarkSent);
    }

    const btnViewBrief = byId("btn-view-brief-from-contacts");
    if (btnViewBrief) {
      btnViewBrief.addEventListener("click", () => {
        if (state.activeBrief) {
          renderCompanyBriefModal(state.activeBrief);
        }
      });
    }

    const emailBodyInput = byId("outreach-email-body");
    if (emailBodyInput) {
      emailBodyInput.addEventListener("input", () => {
        updateDraftMetersAndSlop();
      });
    }
  }

  async function loadSignalsQuery() {
    const st = byId("signals-state");
    if (st) st.innerHTML = `<div class="loading">${icon("loader-circle", "spin")}<span>Fetching fresh hiring & funding signals...</span></div>`;

    try {
      const q = state.signalsFilter.q || "";
      const stage = state.signalsFilter.stage || "any";
      const sigType = state.signalsFilter.type || "";

      let path = "/api/signals?apply_filters=true&limit=150";
      if (sigType) path += "&type=" + encodeURIComponent(sigType);

      const res = await apiGet(path);
      let list = (res && res.signals) || [];

      if (q) {
        const lq = q.toLowerCase();
        list = list.filter((s) => (s.company || "").toLowerCase().includes(lq) || (s.role_guess || "").toLowerCase().includes(lq) || (s.text || "").toLowerCase().includes(lq));
      }
      if (stage && stage !== "any") {
        list = list.filter((s) => (s.stage || "").toLowerCase().includes(stage.toLowerCase()));
      }

      state.signals = list;
      state.signalsLoaded = true;
      renderSignals();
    } catch (e) {
      if (st) st.innerHTML = `<div class="notice bad">${icon("triangle-alert")}<span>Could not load signals: ${esc(e.message)}</span></div>`;
    }
  }

  function renderSignals() {
    const freshList = byId("signals-fresh-list");
    const lateList = byId("signals-late-list");
    const st = byId("signals-state");
    const countEl = byId("signals-count");
    const banner = byId("banner-signals-usability");

    if (!freshList) return;
    freshList.innerHTML = "";
    if (lateList) lateList.innerHTML = "";
    if (st) st.innerHTML = "";

    const all = state.signals || [];
    const fresh = all.filter((s) => s.status !== "dismissed" && (s.is_fresh === 1 || s.is_fresh === true || s.status === "fresh" || s.freshness === "fresh"));
    const late = all.filter((s) => s.status !== "dismissed" && !(s.is_fresh === 1 || s.is_fresh === true || s.status === "fresh" || s.freshness === "fresh"));

    if (countEl) {
      countEl.textContent = `${fresh.length} fresh signal${fresh.length === 1 ? "" : "s"}`;
    }

    if (banner) {
      if (fresh.length > 0 && fresh.length < 10) {
        banner.hidden = false;
        byId("signals-usability-message").textContent = `Only ${fresh.length} fresh signal(s) match current filters. Consider including late signals or selecting "Any stage".`;
        byId("signals-usability-actions").innerHTML = `<button class="btn btn-secondary btn-sm" type="button" id="btn-sig-include-late">Include late signals</button>`;
        const btnInc = byId("btn-sig-include-late");
        if (btnInc) btnInc.addEventListener("click", () => {
          const t = byId("sig-late-toggle");
          if (t) { t.checked = true; t.dispatchEvent(new Event("change")); }
        });
      } else if (fresh.length > 300) {
        banner.hidden = false;
        byId("signals-usability-message").textContent = `Over ${fresh.length} signals found. Consider filtering by target stage or specific role keywords.`;
        byId("signals-usability-actions").innerHTML = "";
      } else {
        banner.hidden = true;
      }
    }

    if (!fresh.length && !late.length) {
      if (st) {
        st.innerHTML = `<div class="empty">${icon("inbox", "icon-lg")}<h2>No signals match filters</h2><p>Radar is actively scanning Hacker News, Reddit, and Seed funding news. Try loosening stage or keyword filters.</p></div>`;
      }
      return;
    }

    fresh.forEach((sig) => {
      freshList.appendChild(buildSignalCard(sig));
    });

    if (lateList) {
      late.forEach((sig) => {
        lateList.appendChild(buildSignalCard(sig, true));
      });
    }
  }

  function buildSignalCard(sig, isLate = false) {
    const li = document.createElement("li");
    li.className = "signal-card" + (isLate ? " signal-card-late" : "");
    li.dataset.id = sig.id;

    const sourceClass = sig.source === "HackerNews" ? "signal-source-hn" : sig.source === "Reddit" ? "signal-source-reddit" : "signal-source-funding";
    const sourceLabel = sig.source === "HackerNews" ? "Hacker News" : sig.source === "Reddit" ? "Reddit Hiring" : "Seed Funding";

    const score = typeof sig.score === "number" ? sig.score : 75;
    const scoreClass = score >= 80 ? "signal-score-high" : score >= 60 ? "signal-score-mid" : "signal-score-low";

    const timeStr = sig.posted_at ? daysAgo((Date.now() - new Date(sig.posted_at).getTime()) / (1000 * 3600 * 24)) : "recently";
    const likesText = sig.likes > 0 ? `${sig.likes} like${sig.likes === 1 ? "" : "s"}` : "";

    const reason = sig.match_reason || (sig.type === "funding" ? `Funded ${sig.funding_amount || "Seed"} round. Reaching founders early.` : `Fresh hiring post for ${sig.role_guess || "Engineering"}.`);

    li.innerHTML = `
      <div class="signal-card-header">
        <span class="signal-source-badge ${sourceClass}">${icon("sparkles", "icon-xs")}${esc(sourceLabel)}</span>
        <span class="signal-score-badge ${scoreClass}">${score}% Fit</span>
      </div>
      <div class="signal-title-group">
        <h3 class="signal-company">${esc(sig.company || "Startup")}</h3>
        <div class="signal-role">${esc(sig.role_guess || "Software Engineer")} ${sig.stage && sig.stage !== "any" ? `<span class="badge" style="font-size:10px">${esc(sig.stage)}</span>` : ""}</div>
      </div>
      <div class="signal-meta-line">
        <span>${icon("clock", "icon-xs")}${esc(timeStr)}</span>
        ${likesText ? `<span>&bull;</span><span>${esc(likesText)}</span>` : ""}
        ${sig.url ? `<a href="${esc(sig.url)}" target="_blank" rel="noopener noreferrer" class="text-btn text-xs">${icon("external-link", "icon-xs")}Original</a>` : ""}
      </div>
      <div class="signal-reason-box">${esc(reason)}</div>
      <p class="signal-snippet">${esc(sig.text || "")}</p>
      <div class="signal-card-actions">
        <button class="btn btn-quiet btn-sm" type="button" data-act="brief">${icon("file-text", "icon-sm")}Brief</button>
        <div style="display:flex;gap:var(--s2)">
          <button class="btn btn-quiet btn-sm" type="button" data-act="dismiss">Dismiss</button>
          <button class="btn btn-primary btn-sm" type="button" data-act="save">${icon("bookmark", "icon-sm")}Save</button>
        </div>
      </div>
    `;

    li.querySelector('[data-act="save"]').addEventListener("click", () => onSaveSignal(sig));
    li.querySelector('[data-act="dismiss"]').addEventListener("click", () => onDismissSignal(sig));
    li.querySelector('[data-act="brief"]').addEventListener("click", () => openCompanyBrief(sig.company, sig.id));

    return li;
  }

  async function onSaveSignal(sig) {
    try {
      toast("Researching company, finding decision makers, and drafting email...", { kind: "good" });
      const res = await apiPost("/api/signals/save", {
        signal_id: sig.id,
        company: sig.company,
        role: sig.role_guess,
      });
      state.activeBrief = res;
      state.activeContacts = res.contacts || [];
      state.activeOutreachDraft = res.email || {};

      openContactsPanel(res, sig);
    } catch (e) {
      toast("Could not save signal: " + e.message, { kind: "bad" });
    }
  }

  async function onDismissSignal(sig) {
    try {
      await apiPost("/api/signals/dismiss", { signal_id: sig.id, reason: "not_interested" });
      state.signals = state.signals.filter((s) => s.id !== sig.id);
      renderSignals();
      toast(`Signal for ${sig.company} dismissed.`);
    } catch (e) {
      toast("Could not dismiss signal: " + e.message, { kind: "bad" });
    }
  }

  /* ============================================================ CONTACTS & OUTREACH PANEL ============================================================ */
  function openContactsPanel(data, sig) {
    const dlg = byId("dlg-contacts-panel");
    if (!dlg) return;

    byId("contacts-company-badge").textContent = data.company || (sig && sig.company) || "Company";
    byId("contacts-context-text").textContent = `Signal: ${data.role || (sig && sig.role_guess) || "Role"} at ${data.company || (sig && sig.company)}`;
    const link = byId("contacts-context-link");
    if (link && sig && sig.url) {
      link.href = sig.url;
      link.hidden = false;
    } else if (link) {
      link.hidden = true;
    }

    const cList = byId("contacts-list");
    const countBadge = byId("contacts-count-badge");
    cList.innerHTML = "";
    const contacts = data.contacts || [];
    countBadge.textContent = String(contacts.length);

    if (!contacts.length) {
      cList.innerHTML = `<p class="hint" style="grid-column:1/-1">No public email found. Use the alternative route (LinkedIn / Company careers page) to connect directly.</p>`;
    } else {
      contacts.slice(0, 3).forEach((c) => {
        const card = document.createElement("div");
        card.className = "contact-item-card";
        const conf = c.confidence || "Guess";
        const confBadge = conf === "Found" ? "badge-found" : conf === "Pattern" ? "badge-pattern" : "badge-guess";
        card.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <span class="contact-name">${esc(c.name || "Hiring Manager")}</span>
            <span class="badge ${confBadge}">${esc(conf)}</span>
          </div>
          <div class="contact-role">${esc(c.role || "Decision Maker")}</div>
          <div class="contact-email">${c.email ? esc(c.email) : "<em class='mute'>No email found</em>"}</div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:var(--s1);font-size:11px">
            <span class="hint">${esc(c.source === "hunter" ? "Hunter API" : "Public Page")} ${c.verified_mx ? "• MX verified" : ""}</span>
            ${c.profile_url ? `<a href="${esc(c.profile_url)}" target="_blank" rel="noopener noreferrer" class="text-btn text-xs">Profile</a>` : ""}
          </div>
        `;
        cList.appendChild(card);
      });
    }

    const emailData = data.email || {};
    byId("outreach-email-subject").value = emailData.subject || `Inquiry regarding ${data.role || "role"} at ${data.company}`;
    byId("outreach-email-body").value = emailData.body || "";

    const resumeData = data.resume || {};
    byId("job-resume-filename").textContent = resumeData.pdf_filename || `${data.company}_Resume.pdf`;
    byId("job-resume-meta").textContent = `Size: ${Math.round((resumeData.pdf_size_bytes || 85000) / 1024)} KB. 1-page PDF grounded in your master resume facts.`;
    const btnResumePdf = byId("btn-open-resume-pdf");
    if (btnResumePdf) {
      btnResumePdf.onclick = () => {
        if (resumeData.pdf_path) {
          toast(`Resume saved at: ${resumeData.pdf_path}`);
        } else {
          toast("Job resume generated in outputs/ folder.");
        }
      };
    }

    updateCapIndicator();
    updateDraftMetersAndSlop();

    if (!dlg.open) dlg.showModal();
  }

  function checkSlop(text, subject) {
    const flags = [];
    const t = (text || "").toLowerCase();

    const bannedOpeners = [
      "hope this email finds you well",
      "hope you are doing well",
      "came across your profile",
      "allow me to introduce myself",
      "my name is"
    ];
    for (const b of bannedOpeners) {
      if (t.includes(b)) flags.push(`Banned opener: "${b}"`);
    }

    const buzzwords = ["passionate", "synergy", "dynamic", "rockstar", "ninja", "leverage", "deeply inspired"];
    for (const b of buzzwords) {
      if (t.includes(b)) flags.push(`Banned buzzword: "${b}"`);
    }

    if (text.includes("—") || text.includes("--")) flags.push("Em dashes are prohibited. Use clear sentences.");
    if (text.includes("!")) flags.push("Exclamation marks are prohibited. Keep tone grounded.");
    if (/\p{Extended_Pictographic}/u.test(text)) flags.push("Emojis are prohibited.");

    const words = (text || "").trim().split(/\s+/).filter(Boolean).length;
    if (words > 80) flags.push(`Too long: ${words} words (maximum is 80 words).`);
    else if (words < 40 && words > 0) flags.push(`Too short: ${words} words (minimum is 40 words).`);

    const lines = (text || "").trim().split("\n").filter((l) => l.trim().length > 0).length;
    if (lines > 4) flags.push(`Too many lines: ${lines} lines (target is 3-4 lines).`);

    const subjWords = (subject || "").trim().split(/\s+/).filter(Boolean).length;
    if (subjWords > 6) flags.push(`Subject line is ${subjWords} words (must be under 6 words).`);

    return flags;
  }

  function updateDraftMetersAndSlop() {
    const text = byId("outreach-email-body").value;
    const subject = byId("outreach-email-subject").value;
    const words = (text || "").trim().split(/\s+/).filter(Boolean).length;
    const lines = (text || "").trim().split("\n").filter((l) => l.trim().length > 0).length;

    const wEl = byId("meter-words");
    const lEl = byId("meter-lines");
    if (wEl) wEl.textContent = `${words} words (target: 40-80)`;
    if (lEl) lEl.textContent = `${lines} lines (target: 3-4)`;

    const flags = checkSlop(text, subject);
    const box = byId("banner-slop-warning");
    const list = byId("slop-flag-list");
    if (box && list) {
      if (flags.length > 0) {
        list.innerHTML = flags.map((f) => `<li>${esc(f)}</li>`).join("");
        box.hidden = false;
      } else {
        box.hidden = true;
      }
    }
  }

  async function updateCapIndicator() {
    try {
      const today = await apiGet("/api/outreach/today");
      state.outreachToday = today || { sent_today: 0, daily_cap: 20, remaining: 20 };
      const capEl = byId("drawer-cap-text");
      if (capEl) capEl.textContent = `Sent today: ${state.outreachToday.sent_today || 0} / ${state.outreachToday.daily_cap || 20}`;
      const metSent = byId("metric-sent-today");
      if (metSent) metSent.textContent = String(state.outreachToday.sent_today || 0);
    } catch (e) {
      /* ignore */
    }
  }

  async function onMarkSent() {
    const contact = (state.activeContacts && state.activeContacts[0]) || {};
    const company = (state.activeBrief && state.activeBrief.company) || "Company";
    const role = (state.activeBrief && state.activeBrief.role) || "Software Engineer";

    const payload = {
      contact_id: contact.id || 0,
      company: company,
      role: role,
      subject: byId("outreach-email-subject").value,
      body: byId("outreach-email-body").value,
      attachment_path: (state.activeBrief && state.activeBrief.resume && state.activeBrief.resume.pdf_path) || "",
    };

    try {
      const res = await apiPost("/api/outreach/mark_sent", payload);
      if (res.status === "queued" || res.queued) {
        toast(`Daily cap reached. Draft added to tomorrow's queue.`, { kind: "bad" });
      } else {
        toast(`Sent logged! Follow-up reminder set for ${res.follow_up_due || "4 days from now"}.`, { kind: "good" });
      }
      byId("dlg-contacts-panel").close();
      updateCapIndicator();
    } catch (e) {
      toast("Could not log sent outreach: " + e.message, { kind: "bad" });
    }
  }

  /* ============================================================ COMPANY BRIEF & LEARNING PACK ============================================================ */
  function renderCompanyBriefModal(data) {
    const dlg = byId("dlg-company-brief");
    if (!dlg) return;

    const brief = data.brief || {};
    const pack = data.learning_pack || {};

    byId("brief-dialog-title").textContent = data.company || brief.company || "Company Research";
    byId("brief-company-sub").textContent = `Factual background & call preparation package`;

    byId("brief-what-they-do").textContent = brief.what_they_do || "No public data found.";
    renderCitationLink("brief-src-what", (brief.sources || [])[0]);

    byId("brief-business-model").textContent = brief.business_model || "Not specified in public sources.";
    renderCitationLink("brief-src-biz", (brief.sources || [])[1] || (brief.sources || [])[0]);

    byId("brief-tech-stack").textContent = brief.tech_stack || "No public tech stack disclosed.";
    renderCitationLink("brief-src-tech", (brief.sources || [])[0]);

    byId("brief-recent-news").textContent = brief.recent_news || "No recent funding or expansion news found.";
    renderCitationLink("brief-src-news", (brief.sources || [])[0]);

    const qList = byId("pack-questions");
    const questions = pack.smart_questions || [];
    qList.innerHTML = questions.length ? questions.map((q) => `<li>${esc(q)}</li>`).join("") : "<li>No questions generated.</li>";

    const gList = byId("pack-gaps");
    const gaps = pack.skill_gaps || [];
    gList.innerHTML = gaps.length ? gaps.map((g) => `<li><strong>${esc(g.skill || g)}</strong>: ${g.study_resource ? `<a href="${esc(g.study_resource.includes("http") ? g.study_resource : "https://" + g.study_resource)}" target="_blank" rel="noopener noreferrer">${esc(g.study_resource)}</a>` : "Self-study documentation"}</li>`).join("") : "<li>No significant skill gaps identified.</li>";

    const tpList = byId("pack-talking-points");
    const points = pack.talking_points || [];
    tpList.innerHTML = points.length ? points.map((p) => `<li>${esc(p)}</li>`).join("") : "<li>Connect candidate achievements with role description.</li>";

    const sBox = byId("pack-summary");
    const summary = pack.summary_5_lines || [];
    sBox.innerHTML = Array.isArray(summary) ? summary.map((s) => `<p style="margin:4px 0">${esc(s)}</p>`).join("") : `<p>${esc(summary)}</p>`;

    if (!dlg.open) dlg.showModal();
  }

  function renderCitationLink(containerId, url) {
    const el = byId(containerId);
    if (!el) return;
    if (url) {
      el.innerHTML = `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" class="text-btn text-xs">${icon("external-link", "icon-xs")}${esc(url)}</a>`;
    } else {
      el.innerHTML = `<span class="hint" style="font-size:11px">Source: Verified public registry</span>`;
    }
  }

  async function openCompanyBrief(company, signalId) {
    try {
      const res = await apiGet(`/api/briefs?company=${encodeURIComponent(company)}&signal_id=${encodeURIComponent(signalId || "")}`);
      if (res && res.brief) {
        renderCompanyBriefModal(res);
      } else {
        const genRes = await apiPost("/api/signals/save", { signal_id: signalId, company: company });
        renderCompanyBriefModal(genRes);
      }
    } catch (e) {
      toast("Could not load company brief: " + e.message, { kind: "bad" });
    }
  }

  /* ============================================================ OUTREACH DASHBOARD & FOLLOW-UPS ============================================================ */
  let outreachInit = false;

  function initOutreach() {
    if (outreachInit) return;
    outreachInit = true;

    const btnRep = byId("btn-view-weekly-report");
    if (btnRep) btnRep.addEventListener("click", openWeeklyReportModal);

    const btnRepClose = byId("btn-report-close");
    if (btnRepClose) btnRepClose.addEventListener("click", () => byId("dlg-weekly-report").close());
    const btnRepDone = byId("btn-report-done");
    if (btnRepDone) btnRepDone.addEventListener("click", () => byId("dlg-weekly-report").close());

    const btnFollowupCancel = byId("btn-followup-cancel");
    if (btnFollowupCancel) btnFollowupCancel.addEventListener("click", () => byId("dlg-followup-draft").close());

    const btnReplyCancel = byId("btn-reply-cancel");
    if (btnReplyCancel) btnReplyCancel.addEventListener("click", () => byId("dlg-reply-record").close());
  }

  async function loadOutreachData() {
    try {
      const [today, queue, report] = await Promise.all([
        apiGet("/api/outreach/today"),
        apiGet("/api/outreach/queue"),
        apiGet("/api/outreach/report"),
      ]);

      state.outreachToday = today || { sent_today: 0, daily_cap: 20, entries: [] };
      state.outreachQueue = (queue && queue.queue) || [];
      state.weeklyReport = (report && report.weekly_report) || {};

      renderOutreach();
    } catch (e) {
      console.warn("Could not load outreach data:", e);
    }
  }

  function renderOutreach() {
    const entries = (state.outreachToday && state.outreachToday.entries) || [];
    const queue = state.outreachQueue || [];
    const report = state.weeklyReport || {};

    byId("metric-sent-today").textContent = String(state.outreachToday.sent_today || 0);
    byId("metric-queue-count").textContent = String(queue.length);
    byId("metric-reply-rate").textContent = `${report.reply_rate_pct != null ? report.reply_rate_pct : 0}%`;

    const now = Date.now();
    const followupsDue = entries.filter((e) => {
      if (e.status !== "sent") return false;
      if (e.follow_up_due && new Date(e.follow_up_due).getTime() <= now) return true;
      if (e.sent_at) {
        const sentTime = new Date(e.sent_at).getTime();
        return (now - sentTime) >= (4 * 24 * 3600 * 1000);
      }
      return false;
    });

    byId("metric-followups-count").textContent = String(followupsDue.length);
    byId("badge-followup-count").textContent = String(followupsDue.length);

    const fList = byId("followup-list");
    if (fList) {
      fList.innerHTML = "";
      if (!followupsDue.length) {
        fList.innerHTML = `<li class="hint" style="padding:var(--s2) 0">No follow-ups due right now. The MCP flags contacts after 4 days without a reply.</li>`;
      } else {
        followupsDue.forEach((f) => {
          const li = document.createElement("li");
          li.className = "followup-card";
          li.innerHTML = `
            <div class="followup-meta">
              <strong>${esc(f.company)} — ${esc(f.role || "Role")}</strong>
              <span>Sent ${daysAgo((now - new Date(f.sent_at).getTime()) / (1000 * 3600 * 24))} &bull; ${esc(f.subject || "")}</span>
            </div>
            <div class="followup-actions">
              <button class="btn btn-secondary btn-sm" type="button" data-act="draft-nudge">${icon("mail", "icon-sm")}Draft follow-up</button>
              <button class="btn btn-quiet btn-sm" type="button" data-act="log-reply">${icon("check", "icon-sm")}Log reply</button>
            </div>
          `;
          li.querySelector('[data-act="draft-nudge"]').addEventListener("click", () => openFollowupDraft(f));
          li.querySelector('[data-act="log-reply"]').addEventListener("click", () => openReplyModal(f));
          fList.appendChild(li);
        });
      }
    }

    const qList = byId("queue-list");
    const qBadge = byId("badge-queue-count");
    if (qBadge) qBadge.textContent = String(queue.length);
    if (qList) {
      qList.innerHTML = "";
      if (!queue.length) {
        qList.innerHTML = `<li class="hint" style="padding:var(--s2) 0">No queued drafts. The queue holds emails when the 20-per-day cap is reached.</li>`;
      } else {
        queue.forEach((q) => {
          const li = document.createElement("li");
          li.className = "queue-card";
          li.innerHTML = `
            <div class="followup-meta">
              <strong>${esc(q.company)} — ${esc(q.role || "Role")}</strong>
              <span>Queued for tomorrow &bull; Subject: ${esc(q.subject || "")}</span>
            </div>
            <div class="followup-actions">
              <span class="badge badge-accent">Queued</span>
            </div>
          `;
          qList.appendChild(li);
        });
      }
    }

    const tbody = byId("outreach-tbody");
    if (tbody) {
      tbody.innerHTML = "";
      if (!entries.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="hint" style="text-align:center;padding:var(--s4)">No outreach recorded yet. Save a signal to draft and send your first message.</td></tr>`;
      } else {
        entries.slice(0, 25).forEach((e) => {
          const tr = document.createElement("tr");
          const dateStr = e.sent_at ? new Date(e.sent_at).toLocaleDateString() : "Draft";
          const statusBadge = e.status === "sent" ? "badge-ok" : e.status === "replied" ? "badge-found" : "badge";
          tr.innerHTML = `
            <td><strong>${esc(e.contact_name || "Decision Maker")}</strong></td>
            <td>${esc(e.company)} (${esc(e.role || "")})</td>
            <td>${esc(dateStr)}</td>
            <td><span class="badge" style="font-size:11px">${esc(e.channel || "email")}</span></td>
            <td><span class="badge ${statusBadge}">${esc(e.status)}</span></td>
            <td>
              ${e.status === "sent" ? `<button class="text-btn text-xs" data-act="reply" type="button">Log reply</button>` : ""}
            </td>
          `;
          const replyBtn = tr.querySelector('[data-act="reply"]');
          if (replyBtn) replyBtn.addEventListener("click", () => openReplyModal(e));
          tbody.appendChild(tr);
        });
      }
    }
  }

  function openFollowupDraft(entry) {
    const dlg = byId("dlg-followup-draft");
    if (!dlg) return;

    byId("followup-contact-info").textContent = `To: ${entry.company} regarding ${entry.role || "the role"}`;
    const nudge = `Hi ${entry.company},\nFollowing up briefly on my earlier note regarding the ${entry.role || "engineering"} post. Still very interested if you are open to a brief chat next week.\n`;
    byId("followup-body").value = nudge;

    byId("btn-followup-copy").onclick = () => {
      navigator.clipboard.writeText(byId("followup-body").value).then(() => toast("Follow-up copied to clipboard."));
    };
    byId("btn-followup-mailto").onclick = () => {
      const b = encodeURIComponent(byId("followup-body").value);
      const s = encodeURIComponent(`Following up: ${entry.subject || "Quick note"}`);
      window.location.href = `mailto:?subject=${s}&body=${b}`;
    };

    if (!dlg.open) dlg.showModal();
  }

  function openReplyModal(entry) {
    const dlg = byId("dlg-reply-record");
    if (!dlg) return;

    byId("reply-contact-info").textContent = `Company: ${entry.company}`;
    byId("reply-callprep-result").hidden = true;

    const chips = byId("reply-chips");
    chips.onclick = async (e) => {
      const btn = e.target.closest("[data-reply]");
      if (!btn) return;
      const rType = btn.dataset.reply;
      try {
        const res = await apiPost("/api/outreach/reply", { outreach_id: entry.id, reply_status: rType });
        if (res && res.call_prep_pack) {
          const pack = res.call_prep_pack;
          const prepDiv = byId("reply-prep-content");
          prepDiv.innerHTML = `
            <div><strong>Company:</strong> ${esc(pack.company || entry.company)}</div>
            <div><strong>Smart questions:</strong></div>
            <ul style="margin:0;padding-left:var(--s4)">${(pack.smart_questions || []).map((q) => `<li>${esc(q)}</li>`).join("")}</ul>
            <div style="margin-top:var(--s2)"><strong>Talking points:</strong></div>
            <ul style="margin:0;padding-left:var(--s4)">${(pack.talking_points || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
          `;
          byId("reply-callprep-result").hidden = false;
        } else {
          toast("Reply status recorded.", { kind: "good" });
          dlg.close();
        }
        loadOutreachData();
      } catch (err) {
        toast("Could not log reply: " + err.message, { kind: "bad" });
      }
    };

    if (!dlg.open) dlg.showModal();
  }

  function openWeeklyReportModal() {
    const dlg = byId("dlg-weekly-report");
    if (!dlg) return;

    const rep = state.weeklyReport || {};
    byId("weekly-report-period").textContent = rep.period || "Last 7 days";
    byId("rep-sent").textContent = String(rep.total_sent || 0);
    byId("rep-replies").textContent = String(rep.total_replies || 0);
    byId("rep-rate").textContent = `${rep.reply_rate_pct != null ? rep.reply_rate_pct : 0}%`;

    const sList = byId("rep-sources");
    if (sList) {
      sList.innerHTML = Object.entries(rep.by_source || {}).map(([src, d]) => `<li><strong>${esc(src)}</strong>: ${d.sent || 0} sent, ${d.replies || 0} replies (${d.reply_rate_pct || 0}%)</li>`).join("") || "<li>No source breakdown yet.</li>";
    }

    const aList = byId("rep-attachments");
    if (aList) {
      aList.innerHTML = Object.entries(rep.by_attachment || {}).map(([att, d]) => `<li><strong>${esc(att.replace(/_/g, " "))}</strong>: ${d.sent || 0} sent, ${d.replies || 0} replies (${d.reply_rate_pct || 0}%)</li>`).join("") || "<li>No attachment breakdown yet.</li>";
    }

    byId("rep-suggested-change").textContent = rep.suggested_change || "Maintain high personalized outreach tempo.";

    if (!dlg.open) dlg.showModal();
  }

  routeHooks.signals = (arg, changed) => {
    initSignals();
    if (changed) {
      setHead("Signals", PAGES.signals.sub, "");
      loadSignalsQuery();
    }
  };

  routeHooks.outreach = (arg, changed) => {
    initOutreach();
    if (changed) {
      setHead("Outreach", PAGES.outreach.sub, "");
      loadOutreachData();
    }
  };

  /* ============================================================ APPLICATIONS */
  const pageActionHandlers = {};
  byId("page-actions").addEventListener("click", (e) => {
    const b = e.target.closest("[data-pa]");
    if (b && pageActionHandlers[b.dataset.pa]) pageActionHandlers[b.dataset.pa](b);
  });

  let appsInit = false;
  let appsError = null;
  let dragId = null;
  let composerEl = null;

  function noteHtml(note) {
    const n = String(note || "").trim();
    if (!n) return "";
    const m = n.match(/^\[Gmail\]\s*(.*)$/i);
    if (m) return `<div class="app-note">${icon("mail", "icon-sm")}<span dir="auto">${esc(clip(m[1] || "Updated from Gmail", 70))}</span></div>`;
    return `<div class="app-note"><span dir="auto">${esc(clip(n, 90))}</span></div>`;
  }

  function appCardHtml(a) {
    const hasTailored = Boolean(a.tailored_resume || a.cover_letter || a.tailored_resume_text || a.cover_letter_text || a.resume_path);
    const scoreVal = a.fit_score || a.score || 0;
    const tier = tierOf(scoreVal);
    const fitBadge = scoreVal > 0
      ? `<span class="score" data-tier="${tier}">${Math.round(scoreVal)}% fit</span>`
      : "";

    const tailoredBadge = hasTailored
      ? `<span class="badge badge-accent" title="Tailored resume and cover letter ready">${icon("file-text", "icon-sm")} Tailored Ready</span>`
      : (a.status === "saved" ? `<span class="badge" style="opacity:0.75" title="Tailoring in background...">${icon("refresh-cw", "icon-sm spin")} Tailoring...</span>` : "");

    const isSavedLane = a.status === "saved";
    const reviewBtn = isSavedLane
      ? `<button class="btn btn-secondary btn-sm" type="button" data-act="review-studio" data-id="${esc(a.id)}">${icon("file-text", "icon-sm")}<span>Review Studio</span></button>`
      : (hasTailored ? `<button class="btn btn-quiet btn-sm" type="button" data-act="review-studio" data-id="${esc(a.id)}">${icon("file-text", "icon-sm")}<span>Docs</span></button>` : "");

    const applyExtBtn = (isSavedLane || a.status === "queued") && a.url
      ? `<button class="btn btn-primary btn-sm" type="button" data-act="apply-ext" data-id="${esc(a.id)}">${icon("send", "icon-sm")}<span>Apply</span></button>`
      : "";

    return `<article class="app-card" draggable="true" data-id="${esc(a.id)}">
      <div class="jc-top" style="margin-block-end:var(--s1)">
        <div class="app-title" dir="auto">${esc(a.title || "Untitled role")}</div>
        ${fitBadge}
      </div>
      <div class="app-co" dir="auto">${esc(a.company || "Company not listed")}</div>
      ${tailoredBadge ? `<div style="margin-block:var(--s1)">${tailoredBadge}</div>` : ""}
      ${noteHtml(a.notes)}
      <div class="app-actions">
        <span class="menu-wrap"><button class="btn btn-secondary btn-sm" type="button" data-move aria-haspopup="menu" aria-expanded="false">Move to${icon("chevron-down", "icon-sm")}</button></span>
        ${reviewBtn}
        ${applyExtBtn}
        ${a.url ? `<span class="grow"><a class="btn btn-quiet btn-sm btn-icon" href="${esc(a.url)}" target="_blank" rel="noopener noreferrer" aria-label="Open posting for ${esc(a.title || "this role")}">${icon("external-link", "icon-sm")}</a></span>` : ""}
      </div>
    </article>`;
  }

  /* ------------------------------------------------------------ V5 Human Review Studio */
  let activeStudioApp = null;
  let activeStudioDocTab = "resume";
  let studioIsEditing = false;

  function openReviewStudio(appId) {
    const a = state.apps.find((x) => String(x.id) === String(appId));
    if (!a) return;
    activeStudioApp = a;
    studioIsEditing = false;
    activeStudioDocTab = "resume";

    const dlg = byId("dlg-review-studio");
    if (!dlg) return;

    byId("studio-title").textContent = `${a.title || "Untitled role"} at ${a.company || "Company"}`;
    byId("studio-sub").textContent = [a.location, a.salary, a.url ? "Employer site" : ""].filter(Boolean).join(" • ");

    const scoreVal = a.fit_score || a.score || 0;
    const gaugeEl = byId("studio-fit-gauge");
    const gaugeVal = byId("studio-fit-val");
    if (gaugeVal) gaugeVal.textContent = `${Math.round(scoreVal)}%`;
    if (gaugeEl) gaugeEl.style.borderColor = scoreVal >= 80 ? "var(--good)" : "var(--accent)";

    const jd = a.job_data || {};
    const postBody = byId("studio-post-body");
    const postMeta = byId("studio-post-meta");
    if (postMeta) postMeta.textContent = a.location || "Full-time";

    let postHtml = "";
    if (jd.description || a.description) {
      const desc = jd.description || a.description;
      const matched = jd.matched_skills || profileTerms();
      postHtml = markText(desc, matched).html;
    } else {
      postHtml = `<p class="mute">No description stored for this posting. Open the original link to review.</p>`;
    }
    if (postBody) postBody.innerHTML = postHtml;

    const docTabs = byId("studio-doc-tabs");
    if (docTabs) {
      $$("button[data-doc-tab]", docTabs).forEach((b) => b.setAttribute("aria-selected", String(b.dataset.docTab === activeStudioDocTab)));
    }

    renderStudioDoc();

    const btnSaveEdit = byId("btn-studio-save-edit");
    if (btnSaveEdit) btnSaveEdit.hidden = true;
    const lblEdit = byId("lbl-studio-edit");
    if (lblEdit) lblEdit.textContent = "Edit draft";

    dlg.showModal();
  }

  function getStudioDocContent() {
    if (!activeStudioApp) return "";
    const a = activeStudioApp;
    if (activeStudioDocTab === "resume") {
      return a.tailored_resume_text || (typeof a.tailored_resume === "string" ? a.tailored_resume : JSON.stringify(a.tailored_resume || {}, null, 2)) || "No tailored resume generated yet.";
    } else {
      return a.cover_letter_text || a.cover_letter || "No cover letter generated yet.";
    }
  }

  function renderStudioDoc() {
    const content = getStudioDocContent();
    const previewEl = byId("studio-doc-preview");
    const editorEl = byId("studio-doc-editor");

    if (studioIsEditing) {
      if (previewEl) previewEl.hidden = true;
      if (editorEl) {
        editorEl.hidden = false;
        editorEl.value = content;
        editorEl.focus();
      }
    } else {
      if (editorEl) editorEl.hidden = true;
      if (previewEl) {
        previewEl.hidden = false;
        const terms = profileTerms();
        previewEl.innerHTML = markText(content, terms).html;
      }
    }
  }

  async function onStudioSaveEdit() {
    if (!activeStudioApp) return;
    const editorEl = byId("studio-doc-editor");
    if (!editorEl) return;
    const newText = editorEl.value;
    const a = activeStudioApp;
    if (activeStudioDocTab === "resume") {
      a.tailored_resume_text = newText;
    } else {
      a.cover_letter_text = newText;
      a.cover_letter = newText;
    }
    try {
      await apiPost("/api/applications", {
        id: a.id,
        cover_letter: a.cover_letter_text,
        job_data: a.job_data
      });
      toast("Saved draft edits.");
      studioIsEditing = false;
      const btnSave = byId("btn-studio-save-edit");
      if (btnSave) btnSave.hidden = true;
      const lblEdit = byId("lbl-studio-edit");
      if (lblEdit) lblEdit.textContent = "Edit draft";
      renderStudioDoc();
    } catch (e) {
      toast("Could not save edits: " + e.message, { kind: "bad" });
    }
  }

  async function onStudioAccept() {
    if (!activeStudioApp) return;
    const a = activeStudioApp;
    try {
      a.review_approved = true;
      a.notes = (a.notes ? a.notes + "\n" : "") + "[Review Approved] Tailored materials accepted by user.";
      await apiPost("/api/applications", {
        id: a.id,
        notes: a.notes,
        status: a.status
      });
      toast("Tailored materials approved for use! Ready to apply with extension.");
      const dlg = byId("dlg-review-studio");
      if (dlg) dlg.close();
      renderApps();
    } catch (e) {
      toast("Error accepting draft: " + e.message, { kind: "bad" });
    }
  }

  function onStudioReject() {
    const rejectDlg = byId("dlg-reject-feedback");
    if (rejectDlg) {
      const txt = byId("reject-feedback-text");
      if (txt) txt.value = "";
      rejectDlg.showModal();
    }
  }

  async function onConfirmReject() {
    const rejectDlg = byId("dlg-reject-feedback");
    if (rejectDlg) rejectDlg.close();
    if (!activeStudioApp) return;
    const txt = byId("reject-feedback-text");
    const feedback = (txt && txt.value ? txt.value : "Draft rejected during human review").trim();
    const a = activeStudioApp;
    try {
      a.notes = (a.notes ? a.notes + "\n" : "") + `[Review Rejected] ${feedback}`;
      await apiPost("/api/applications", {
        id: a.id,
        notes: a.notes
      });
      toast("Rejection logged with feedback. You can regenerate or edit.");
      const dlg = byId("dlg-review-studio");
      if (dlg) dlg.close();
      renderApps();
    } catch (e) {
      toast("Could not log rejection: " + e.message, { kind: "bad" });
    }
  }

  async function onApplyWithExtension(appId) {
    const a = state.apps.find((x) => String(x.id) === String(appId || (activeStudioApp && activeStudioApp.id)));
    if (!a || !a.url) {
      toast("No posting link available to apply.", { kind: "bad" });
      return;
    }
    try {
      toast("Opening posting with extension. Matching fields from approved profile...", { kind: "info" });
      await apiPost("/api/auto-apply/launch", { url: a.url });

      if (a.status === "saved") {
        await moveApp(a.id, "queued", true);
      }
      toast("Extension launched. Fields filled automatically (user submits manually per Rule 8).", {
        action: { label: "View", run: () => go("applications") }
      });
      const studioDlg = byId("dlg-review-studio");
      if (studioDlg && studioDlg.open) studioDlg.close();
    } catch (e) {
      toast("Could not launch extension: " + e.message, { kind: "bad" });
    }
  }

  function renderApps() {
    const board = byId("board");
    const empty = byId("board-empty");
    const tabs = byId("stage-tabs");
    empty.innerHTML = "";

    if (!state.appsLoaded) {
      tabs.hidden = true;
      board.hidden = false;
      board.innerHTML = STAGES.map((s) => `<section class="lane ${s.id === state.stageTab ? "show" : ""}" aria-hidden="true"><div class="lane-head"><h2><span class="stage-mark stage-${s.id}"></span>${s.label}</h2></div><div class="lane-body"><div class="skeleton" style="height:4.2rem"></div><div class="skeleton" style="height:4.2rem"></div></div></section>`).join("");
      if (appsError) {
        board.hidden = true;
        empty.innerHTML = `<div style="padding-block:var(--s4)">${appsError.offline ? offlineNotice(true) : errorNotice(appsError.message, true)}</div>`;
      }
      return;
    }

    const active = state.apps.filter((a) => a.status !== "rejected");
    const closed = state.apps.filter((a) => a.status === "rejected");
    byId("page-sub").textContent = state.apps.length ? `${active.length} active${closed.length ? ", " + closed.length + " closed" : ""}.` : "";
    byId("page-sub").hidden = !state.apps.length;

    if (!state.apps.length) {
      tabs.hidden = true;
      board.hidden = true;
      byId("closed-wrap").hidden = true;
      empty.innerHTML = `<div class="empty">${icon("square-kanban", "icon-lg")}<h2>Nothing tracked yet</h2><p>Save a job from the Jobs page and it appears here. Gmail can move it to Applied, Interview or Closed for you.</p><div class="form-foot"><a class="btn btn-primary" href="#/jobs">${icon("search")}<span>Find jobs</span></a><button class="btn btn-secondary" type="button" data-pa="add">${icon("plus")}<span>Add one yourself</span></button></div></div>`;
      return;
    }

    board.hidden = false;
    tabs.hidden = false;
    tabs.innerHTML = STAGES.map((s) => {
      const n = state.apps.filter((a) => a.status === s.id).length;
      return `<button type="button" data-stage="${s.id}" aria-pressed="${s.id === state.stageTab}">${s.label} <span class="count">${n}</span></button>`;
    }).join("");

    const firstQueuedUrl = (state.apps.find((a) => a.status === "queued" && a.url) || {}).url;
    board.innerHTML = STAGES.map((s) => {
      const cards = state.apps.filter((a) => a.status === s.id);
      const extra = s.id === "queued" && firstQueuedUrl ? `<div class="grow"><button class="btn btn-secondary btn-sm" type="button" data-launch="${esc(firstQueuedUrl)}">${icon("globe", "icon-sm")}<span>Open browser</span></button></div>` : "";
      return `<section class="lane ${s.id === state.stageTab ? "show" : ""}" data-lane="${s.id}" aria-label="${s.label}, ${cards.length}">
        <div class="lane-head"><h2><span class="stage-mark stage-${s.id}"></span>${s.label} <span class="lane-count">${cards.length}</span></h2>${extra}</div>
        <div class="lane-body">${cards.length ? cards.map(appCardHtml).join("") : `<div class="lane-empty">${esc(s.hint)}</div>`}</div>
      </section>`;
    }).join("");

    const cw = byId("closed-wrap");
    cw.hidden = !closed.length;
    byId("closed-count").textContent = closed.length ? "(" + closed.length + ")" : "";
    byId("closed-list").innerHTML = closed.map((a) => `<li data-id="${esc(a.id)}"><span class="stage-mark stage-rejected"></span><span dir="auto"><strong>${esc(a.title || "Untitled role")}</strong>, ${esc(a.company || "company not listed")}</span><button class="btn btn-secondary btn-sm" type="button" data-reopen style="margin-inline-start:auto">Reopen</button></li>`).join("");
  }

  async function moveApp(id, status, quiet) {
    const a = state.apps.find((x) => String(x.id) === String(id));
    if (!a || a.status === status) return;
    const prev = a.status;
    a.status = status;
    renderApps();
    updateAppCount();
    try {
      await apiPost("/api/applications", { id: a.id, status });
      const label = status === "rejected" ? "Closed" : STAGE_LABEL[status];
      toast(quiet ? "Moved back." : "Moved to " + label + ".", quiet ? null : { action: { label: "Undo", run: () => moveApp(id, prev, true) } });
    } catch (e) {
      a.status = prev;
      renderApps();
      updateAppCount();
      toast("Could not move it. " + e.message, { kind: "bad" });
    }
  }

  function openComposer() {
    closeComposer();
    const el = document.createElement("form");
    el.className = "composer";
    el.setAttribute("aria-label", "Add an application");
    el.style.marginBlockEnd = "var(--s4)";
    el.innerHTML = `
      <div class="form-grid cols-2" style="display:grid;gap:var(--s3);grid-template-columns:repeat(auto-fit,minmax(14rem,1fr))">
        <div class="field"><label for="ap-title">Role title</label><input class="input" id="ap-title" type="text" required autocomplete="off"></div>
        <div class="field"><label for="ap-company">Company</label><input class="input" id="ap-company" type="text" required autocomplete="off"></div>
        <div class="field"><label for="ap-url">Posting link <span class="opt">(optional)</span></label><input class="input" id="ap-url" type="url" placeholder="https://"></div>
        <div class="field"><label for="ap-status">Stage</label><select class="select" id="ap-status">${STAGES.map((s) => `<option value="${s.id}"${s.id === "saved" ? " selected" : ""}>${s.label}</option>`).join("")}</select></div>
      </div>
      <div class="row"><button class="btn btn-quiet" type="button" data-cancel>Cancel</button><button class="btn btn-primary" type="submit">Add application</button></div>`;
    byId("stage-tabs").before(el);
    composerEl = el;
    byId("ap-title").focus();
    el.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeComposer(true); } });
    el.querySelector("[data-cancel]").addEventListener("click", () => closeComposer(true));
    el.addEventListener("submit", async (e) => {
      e.preventDefault();
      const title = byId("ap-title").value.trim();
      const company = byId("ap-company").value.trim();
      if (!title || !company) return;
      const submit = el.querySelector('[type="submit"]');
      submit.setAttribute("aria-busy", "true");
      try {
        await apiPost("/api/applications", { title, company, url: byId("ap-url").value.trim(), status: byId("ap-status").value });
        await reloadApps();
        state.stageTab = byId("ap-status").value;
        closeComposer(false);
        renderApps();
        toast("Added " + title + " at " + company + ".");
      } catch (err) {
        submit.removeAttribute("aria-busy");
        toast(err.message, { kind: "bad" });
      }
    });
  }
  function closeComposer(refocus) {
    if (!composerEl) return;
    composerEl.remove();
    composerEl = null;
    if (refocus) { const b = $('[data-pa="add"]'); if (b) b.focus(); }
  }
  pageActionHandlers.add = () => { if (state.apps.length === 0) { renderAppsAfterEmpty(); } openComposer(); };
  function renderAppsAfterEmpty() { /* the composer works with or without cards */ }

  pageActionHandlers.gmail = async (btn) => {
    try {
      if (!state.gmail) await loadGmailStatus();
      if (!state.gmail || !state.gmail.configured) { go("settings/gmail"); return; }
      btn.setAttribute("aria-busy", "true");
      const r = await apiPost("/api/gmail/sync", {});
      await reloadApps();
      renderApps();
      const u = (r && r.applications_updated) || 0, c = (r && r.applications_created) || 0;
      toast(u || c ? "Gmail checked. " + u + " updated, " + c + " added." : "Gmail checked. No changes.");
    } catch (e) {
      toast("Gmail check failed. " + e.message, { kind: "bad" });
    } finally {
      btn.removeAttribute("aria-busy");
    }
  };

  async function loadGmailStatus() {
    try { state.gmail = await apiGet("/api/gmail/status"); } catch (e) { state.gmail = null; }
    return state.gmail;
  }

  function initApps() {
    if (appsInit) return;
    appsInit = true;

    byId("stage-tabs").addEventListener("click", (e) => {
      const b = e.target.closest("[data-stage]");
      if (!b) return;
      state.stageTab = b.dataset.stage;
      renderApps();
      const again = $(`[data-stage="${state.stageTab}"]`, byId("stage-tabs"));
      if (again) again.focus();
    });

    byId("board-empty").addEventListener("click", (e) => {
      if (e.target.closest("[data-retry]")) { loadApps(); }
      if (e.target.closest('[data-pa="add"]')) pageActionHandlers.add();
    });

    byId("board").addEventListener("click", (e) => {
      const rs = e.target.closest("[data-act='review-studio']");
      if (rs) {
        openReviewStudio(rs.dataset.id);
        return;
      }
      const ap = e.target.closest("[data-act='apply-ext']");
      if (ap) {
        onApplyWithExtension(ap.dataset.id);
        return;
      }
      const v = e.target.closest("[data-view-tailored]");
      if (v) {
        const id = v.dataset.viewTailored;
        const a = state.apps.find((x) => String(x.id) === String(id));
        if (a) {
          byId("d-title").value = a.title || "";
          byId("d-company").value = a.company || "";
          const desc = (a.job_data && a.job_data.description) || a.notes || "";
          byId("d-desc").value = desc;
          if (a.cover_letter) {
            renderDoc({ text: a.cover_letter, kind: "cover-letter", title: `Cover letter for ${a.company}` });
          }
          go("documents");
        }
        return;
      }
      const mv = e.target.closest("[data-move]");
      if (mv) {
        const id = mv.closest(".app-card").dataset.id;
        const a = state.apps.find((x) => String(x.id) === String(id));
        const items = [{ heading: "Move to" }].concat(STAGES.map((s) => ({ label: s.label, checked: a && a.status === s.id, run: () => moveApp(id, s.id) })), ["-", { label: "Closed, rejected", icon: "x", run: () => moveApp(id, "rejected") }]);
        showMenu(mv, items);
        return;
      }
      const l = e.target.closest("[data-launch]");
      if (l) {
        l.setAttribute("aria-busy", "true");
        apiPost("/api/auto-apply/launch", { url: l.dataset.launch })
          .then(() => toast("A browser with the extension is opening."))
          .catch((err) => toast(err.message, { kind: "bad" }))
          .finally(() => l.removeAttribute("aria-busy"));
      }
    });

    // Human Review Studio wire-up
    const studioDlg = byId("dlg-review-studio");
    if (studioDlg) {
      closeOnBackdrop(studioDlg);
      const btnClose = byId("btn-studio-close");
      if (btnClose) btnClose.addEventListener("click", () => studioDlg.close());
      const btnAccept = byId("btn-studio-accept");
      if (btnAccept) btnAccept.addEventListener("click", onStudioAccept);
      const btnReject = byId("btn-studio-reject");
      if (btnReject) btnReject.addEventListener("click", onStudioReject);
      const btnApply = byId("btn-studio-apply");
      if (btnApply) btnApply.addEventListener("click", () => onApplyWithExtension());

      const docTabs = byId("studio-doc-tabs");
      if (docTabs) {
        docTabs.addEventListener("click", (e) => {
          const btn = e.target.closest("button[data-doc-tab]");
          if (!btn) return;
          activeStudioDocTab = btn.dataset.docTab;
          $$("button[data-doc-tab]", docTabs).forEach((b) => b.setAttribute("aria-selected", String(b === btn)));
          renderStudioDoc();
        });
      }

      const btnToggleEdit = byId("btn-studio-toggle-edit");
      if (btnToggleEdit) {
        btnToggleEdit.addEventListener("click", () => {
          studioIsEditing = !studioIsEditing;
          const btnSave = byId("btn-studio-save-edit");
          if (btnSave) btnSave.hidden = !studioIsEditing;
          const lbl = byId("lbl-studio-edit");
          if (lbl) lbl.textContent = studioIsEditing ? "Cancel edit" : "Edit draft";
          renderStudioDoc();
        });
      }

      const btnSaveEdit = byId("btn-studio-save-edit");
      if (btnSaveEdit) btnSaveEdit.addEventListener("click", onStudioSaveEdit);
    }

    const rejectDlg = byId("dlg-reject-feedback");
    if (rejectDlg) {
      closeOnBackdrop(rejectDlg);
      const btnCancel = byId("btn-reject-cancel");
      if (btnCancel) btnCancel.addEventListener("click", () => rejectDlg.close());
      const btnConfirm = byId("btn-reject-confirm");
      if (btnConfirm) btnConfirm.addEventListener("click", onConfirmReject);
    }

    byId("closed-list").addEventListener("click", (e) => {
      const b = e.target.closest("[data-reopen]");
      if (b) moveApp(b.closest("li").dataset.id, "saved");
    });

    /* drag and drop between lanes */
    const board = byId("board");
    board.addEventListener("dragstart", (e) => {
      const c = e.target.closest(".app-card");
      if (!c) return;
      dragId = c.dataset.id;
      c.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", dragId); } catch (err) { /* ignore */ }
    });
    board.addEventListener("dragend", () => {
      dragId = null;
      $$(".dragging, .drop", board).forEach((n) => n.classList.remove("dragging", "drop"));
    });
    board.addEventListener("dragover", (e) => {
      const lane = e.target.closest(".lane");
      if (!lane || dragId == null) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      lane.classList.add("drop");
    });
    board.addEventListener("dragleave", (e) => {
      const lane = e.target.closest(".lane");
      if (lane && !lane.contains(e.relatedTarget)) lane.classList.remove("drop");
    });
    board.addEventListener("drop", (e) => {
      const lane = e.target.closest(".lane");
      if (!lane || dragId == null) return;
      e.preventDefault();
      lane.classList.remove("drop");
      const id = dragId;
      dragId = null;
      moveApp(id, lane.dataset.lane);
    });
  }

  async function loadApps() {
    appsError = null;
    if (!state.appsLoaded) renderApps();
    try {
      const d = await apiGet("/api/applications");
      state.apps = (d && d.applications) || [];
      state.appsLoaded = true;
    } catch (e) {
      if (!state.appsLoaded) appsError = e;
    }
    updateAppCount();
    renderApps();
  }

  routeHooks.applications = (arg, changed) => {
    initApps();
    if (changed) {
      setHead("Applications", "", `<button class="btn btn-secondary" type="button" data-pa="add">${icon("plus")}<span>Add application</span></button><button class="btn btn-secondary" type="button" data-pa="gmail">${icon("mail")}<span>Check Gmail</span></button>`);
      loadApps();
      loadGmailStatus();
    }
  };

  /* ============================================================ DOCUMENTS */
  const DOC_KINDS = {
    "cover-letter": "Cover letter",
    "tailor-resume": "Tailored resume",
    "interview-prep": "Interview prep",
    outreach: "Recruiter message",
    "founder-cold-email": "Email to a founder",
    "linkedin-founder-dm": "LinkedIn note to a founder",
    "bigtech-hr-referral": "Big Tech recruiter and referral",
  };
  const doc = { kind: null, data: null, view: "letter", texts: {}, subject: 0, marks: lsGet("jh-marks") !== "off", ctl: null, busy: false, error: null, gmailUrl: "", recipient: "" };
  let docsInit = false;

  const docKind = () => ($('input[name="doctype"]:checked') || {}).value || "cover-letter";
  const val = (id) => (byId(id) ? byId(id).value.trim() : "");

  function updateDocFields() {
    const k = docKind();
    const founder = k === "founder-cold-email" || k === "linkedin-founder-dm";
    byId("f-angle").hidden = !(k === "cover-letter" || k === "tailor-resume");
    byId("fields-founder").hidden = !founder;
    byId("f-femail").hidden = k !== "founder-cold-email";
    byId("fields-bigtech").hidden = k !== "bigtech-hr-referral";
    byId("btn-generate").querySelector("span").textContent = "Write " + (DOC_KINDS[k] || "document").toLowerCase();
  }

  function updateUsing() {
    const p = state.active;
    const el = byId("doc-using");
    if (p) {
      const n = (p.skills || []).length;
      el.innerHTML = `${icon("file-text", "icon-sm")}<span>Writing from <strong dir="auto">${esc(p.name || p.filename || "your resume")}</strong>${p.target_title ? ", " + esc(p.target_title) : ""}, ${n} ${n === 1 ? "skill" : "skills"}.</span> <a href="#/resume">Change</a>`;
    } else if (state.profilesLoaded) {
      el.innerHTML = `<span class="status-text warn">${icon("triangle-alert", "icon-sm")}No resume found.</span> <a href="#/resume">Add your resume</a> so documents have facts to use.`;
    } else {
      el.textContent = "";
    }
  }

  function paperEmpty() {
    byId("paper-wrap").innerHTML = `<div class="paper"><div class="empty">${icon("pen-line", "icon-lg")}<h2>Your document appears here</h2><p>Pick a type, enter the role, then write. Terms taken from your resume are highlighted so you can check each claim.</p></div></div>`;
  }

  function verdictOf(review) {
    if (!review) return { cls: "none", icon: "circle-help", label: "Not reviewed", notes: [] };
    const raw = typeof review === "string" ? review : review.verdict || review.status || "";
    const v = String(raw).toLowerCase();
    const list = typeof review === "object" ? review.issues || review.notes || review.flags || review.warnings || [] : [];
    const notes = (Array.isArray(list) ? list : [list]).map((x) => (x && typeof x === "object" ? x.message || x.issue || x.text || "" : String(x))).filter(Boolean);
    if (!v) return { cls: "none", icon: "circle-help", label: "Not reviewed", notes };
    if (/^(pass|ok|approved|clean)/.test(v)) return { cls: "pass", icon: "circle-check", label: "Reviewer: passed", notes };
    if (/(fail|reject|block)/.test(v)) return { cls: "fail", icon: "circle-alert", label: "Reviewer: failed", notes };
    return { cls: "attention", icon: "triangle-alert", label: "Reviewer: needs attention", notes };
  }

  function treeText(v, indent) {
    indent = indent || "";
    if (v == null) return "";
    if (typeof v !== "object") return indent + String(v);
    if (Array.isArray(v)) return v.map((x) => (typeof x === "object" ? treeText(x, indent) : indent + "- " + x)).join("\n");
    return Object.entries(v).map(([k, x]) => (typeof x === "object" && x ? indent + humanize(k) + "\n" + treeText(x, indent + "  ") : indent + humanize(k) + ": " + x)).join("\n");
  }

  function treeHtml(v, key) {
    if (v == null || v === "") return "";
    if (typeof v !== "object") return `<p dir="auto">${esc(v)}</p>`;
    if (Array.isArray(v)) {
      if (v.every((x) => x == null || typeof x !== "object")) return `<ul>${v.map((x) => `<li dir="auto">${esc(x)}</li>`).join("")}</ul>`;
      const one = humanize(String(key || "Item").replace(/s$/i, ""));
      return v.map((x, i) => `<section><h2 class="th">${esc(one)} ${i + 1}</h2>${treeHtml(x)}</section>`).join("");
    }
    let out = "", rows = "";
    const flush = () => { if (rows) { out += `<dl>${rows}</dl>`; rows = ""; } };
    Object.entries(v).forEach(([k, x]) => {
      if (x == null || x === "") return;
      if (typeof x !== "object") rows += `<dt>${esc(humanize(k))}</dt><dd dir="auto">${esc(x)}</dd>`;
      else { flush(); out += `<section><h2 class="th">${esc(humanize(k))}</h2>${treeHtml(x, k)}</section>`; }
    });
    flush();
    return out;
  }

  function textHtml(text) {
    return doc.marks ? markText(text, profileTerms()) : { html: esc(text), count: 0 };
  }

  function blockHtml(id, title, text, opts) {
    opts = opts || {};
    doc.texts[id] = text;
    const t = textHtml(text);
    marksCount += t.count;
    let counter = "";
    if (opts.max) {
      const n = String(text).length;
      counter = `<span class="counter${n > opts.max ? " over" : ""}">${n} of ${opts.max} characters${n > opts.max ? ", too long" : ""}</span>`;
    }
    return `<div class="doc-block"><div class="doc-block-head"><h2>${esc(title)}</h2><span class="row" style="display:flex;gap:var(--s2);align-items:center">${counter}<button class="btn btn-quiet btn-sm" type="button" data-copy="${esc(id)}">${icon("copy", "icon-sm")}<span>Copy</span></button></span></div><div class="doc-text" dir="auto">${t.html}</div></div>`;
  }

  let marksCount = 0;

  function renderDoc() {
    const wrap = byId("paper-wrap");
    wrap.setAttribute("tabindex", "-1");
    if (doc.busy) {
      wrap.innerHTML = `<div class="paper-bar"><p class="status-text mute" role="status">${icon("loader-circle", "icon-sm spin")}Writing from your resume, then checking each claim.</p></div><div class="paper" aria-hidden="true"><div class="skeleton" style="height:16px;width:38%;margin-block-end:18px"></div>${[96, 92, 98, 88, 94, 60].map((w) => `<div class="skeleton" style="height:13px;width:${w}%;margin-block-end:12px"></div>`).join("")}<div style="height:12px"></div>${[90, 96, 84, 40].map((w) => `<div class="skeleton" style="height:13px;width:${w}%;margin-block-end:12px"></div>`).join("")}</div>`;
      return;
    }
    if (doc.error) {
      wrap.innerHTML = `<div class="paper"><div style="font-family:var(--font-sans)">${doc.error.offline ? offlineNotice(true) : errorNotice("The document was not written. " + doc.error.message, true)}</div></div>`;
      return;
    }
    if (!doc.data) { paperEmpty(); return; }

    doc.texts = {};
    marksCount = 0;
    const k = doc.kind, d = doc.data;
    let bar = { verdict: null, meta: [], print: false, gmail: doc.gmailUrl, draft: false };
    let body = "";
    let top = "";

    if (k === "cover-letter" || k === "tailor-resume") {
      top = `<div class="seg" role="group" aria-label="Document">
        <button type="button" data-view="letter" aria-pressed="${doc.view === "letter"}">Cover letter</button>
        <button type="button" data-view="resume" aria-pressed="${doc.view === "resume"}">Tailored resume</button></div>`;
      bar.print = true;
      if (doc.view === "letter") {
        const text = d.cover_letter && (d.cover_letter.full_text || d.cover_letter.text);
        bar.verdict = verdictOf(d.cover_letter && d.cover_letter.review);
        if (text) { doc.texts.main = text; const t = textHtml(text); marksCount += t.count; body = `<div class="doc-text" dir="auto">${t.html}</div>`; }
        else body = `<p>No cover letter came back for this job.</p>`;
      } else {
        const tr = d.tailored_resume || {};
        const text = tr.txt || tr.text || "";
        if (typeof tr.ats_match_pct === "number") bar.meta.push("ATS match " + Math.round(tr.ats_match_pct) + "%");
        if (text) { doc.texts.main = text; const t = textHtml(text); marksCount += t.count; body = `<div class="doc-text resume" dir="auto">${t.html}</div>`; }
        else body = `<p>No tailored resume came back for this job.</p>`;
      }
    } else if (k === "interview-prep") {
      const prep = d.prep || d;
      doc.texts.main = treeText(prep);
      body = `<div class="tree">${treeHtml(prep) || "<p>No prep notes came back.</p>"}</div>`;
    } else if (k === "outreach") {
      const o = d.outreach || {};
      const m = o.hiring_manager_inmail || {};
      const parts = [];
      if (o.linkedin_connection_note) parts.push(blockHtml("li", "LinkedIn connection note", o.linkedin_connection_note, { max: 300 }));
      if (m.body) parts.push(blockHtml("inm", m.subject_line ? "Message to the hiring manager. Subject: " + m.subject_line : "Message to the hiring manager", m.body));
      body = parts.length ? `<div class="doc-blocks">${parts.join("")}</div>` : `<p>No messages came back.</p>`;
      doc.texts.main = [o.linkedin_connection_note, m.subject_line ? "Subject: " + m.subject_line : "", m.body].filter(Boolean).join("\n\n");
    } else if (k === "founder-cold-email") {
      bar.verdict = verdictOf(d.review);
      if (d.word_count) bar.meta.push(d.word_count + " words, about " + (d.reading_time_sec || Math.round(d.word_count / 3.3)) + " seconds to read");
      bar.draft = true;
      const subs = d.subject_options || [];
      const subHtml = subs.length ? `<div class="doc-block"><div class="doc-block-head"><h2 id="h-subj">Subject line</h2></div><div class="subject-list" role="radiogroup" aria-labelledby="h-subj">${subs.map((s, i) => `<label><input type="radio" name="subj" value="${i}"${i === doc.subject ? " checked" : ""}><span dir="auto">${esc(s)}</span></label>`).join("")}</div></div>` : "";
      doc.recipient = d.recipient_email || "";
      body = `<div class="doc-blocks">${subHtml}${d.body ? blockHtml("body", "Email", d.body) : ""}${d.follow_up_note ? blockHtml("fu", "Follow up, if they do not reply", d.follow_up_note) : ""}</div>`;
      doc.texts.main = (subs[doc.subject] ? "Subject: " + subs[doc.subject] + "\n\n" : "") + (d.body || "");
    } else if (k === "linkedin-founder-dm") {
      bar.verdict = verdictOf(d.review_note);
      const parts = [];
      if (d.connection_note) parts.push(blockHtml("li", "Connection note", d.connection_note, { max: 300 }));
      if (d.inmail_body) parts.push(blockHtml("inm", d.inmail_subject ? "Follow up message. Subject: " + d.inmail_subject : "Follow up message", d.inmail_body));
      body = parts.length ? `<div class="doc-blocks">${parts.join("")}</div>` : `<p>No messages came back.</p>`;
      doc.texts.main = [d.connection_note, d.inmail_subject ? "Subject: " + d.inmail_subject : "", d.inmail_body].filter(Boolean).join("\n\n");
    } else if (k === "bigtech-hr-referral") {
      bar.verdict = verdictOf(d.review_inmail);
      if (d.company) bar.meta.push(d.company + (d.level_label ? ", " + d.level_label : ""));
      const parts = [];
      if (d.rubric_focus) parts.push(`<p class="hint" style="font-family:var(--font-sans)">Interview focus at this level: ${esc(d.rubric_focus)}</p>`);
      if (d.inmail_body) parts.push(blockHtml("inm", d.inmail_subject ? "Recruiter message. Subject: " + d.inmail_subject : "Recruiter message", d.inmail_body));
      if (d.referral_blurb) parts.push(blockHtml("ref", d.referral_portal_name ? "Referral note for " + d.referral_portal_name : "Referral note", d.referral_blurb));
      body = parts.length ? `<div class="doc-blocks">${parts.join("")}</div>` : `<p>No messages came back.</p>`;
      doc.texts.main = [d.inmail_subject ? "Subject: " + d.inmail_subject : "", d.inmail_body, d.referral_blurb].filter(Boolean).join("\n\n");
    }

    const v = bar.verdict;
    const hasMarkable = k !== "interview-prep" || true;
    const matchNote = doc.marks && marksCount ? `${marksCount} ${marksCount === 1 ? "term" : "terms"} from your resume ${marksCount === 1 ? "is" : "are"} highlighted.` : (doc.marks ? "" : "Resume highlights are off.");
    const left = [v ? `<span class="verdict ${v.cls}">${icon(v.icon, "icon-sm")}${esc(v.label)}</span>` : "", ...bar.meta.map((m) => `<span class="legend">${esc(m)}</span>`)].filter(Boolean).join("");
    const right = [
      hasMarkable ? `<button class="btn btn-secondary btn-sm" type="button" data-marks aria-pressed="${doc.marks}">${icon("eye", "icon-sm")}<span>Resume matches</span></button>` : "",
      `<button class="btn btn-secondary btn-sm" type="button" data-copy="__all">${icon("copy", "icon-sm")}<span>Copy</span></button>`,
      bar.print ? `<button class="btn btn-secondary btn-sm" type="button" data-print>${icon("printer", "icon-sm")}<span>Print or save PDF</span></button>` : "",
      bar.gmail ? `<a class="btn btn-secondary btn-sm" href="${esc(bar.gmail)}" target="_blank" rel="noopener noreferrer">${icon("mail", "icon-sm")}<span>Open in Gmail</span></a>` : "",
      bar.draft ? `<button class="btn btn-secondary btn-sm" type="button" data-draft>${icon("file-up", "icon-sm")}<span>Save Gmail draft</span></button>` : "",
    ].join("");
    const notes = v && v.cls !== "pass" && v.notes.length ? `<ul class="reviewer-notes">${v.notes.map((n) => `<li dir="auto">${esc(n)}</li>`).join("")}</ul>` : "";

    wrap.innerHTML = `${top}<div class="paper-bar"><div class="left">${left}</div><div class="right">${right}</div></div>${notes}
      <article class="paper" aria-label="${esc(DOC_KINDS[k] || "Document")}"><div class="${doc.marks ? "sweep" : ""}">${body}</div></article>
      ${matchNote ? `<p class="legend" role="status">${esc(matchNote)}</p>` : ""}`;
  }

  function validateDoc(k) {
    ["d-title", "d-company", "d-fname"].forEach((id) => clearFieldError(byId(id)));
    const founder = k === "founder-cold-email" || k === "linkedin-founder-dm";
    if (k === "bigtech-hr-referral") return true;
    if (founder && !val("d-fname")) { setFieldError(byId("d-fname"), "Enter the founder's name or LinkedIn link."); byId("d-fname").focus(); return false; }
    if (!val("d-title") && !val("d-company")) {
      setFieldError(byId("d-title"), "Enter a role title or a company.");
      byId("d-title").focus();
      return false;
    }
    return true;
  }

  async function generateDoc() {
    if (doc.busy) { if (doc.ctl) doc.ctl.abort(); return; }
    const k = docKind();
    if (!validateDoc(k)) return;
    const job = { title: val("d-title"), company: val("d-company"), description: val("d-desc") };
    let path, payload;
    if (k === "cover-letter" || k === "tailor-resume") {
      path = "/api/documents/job-package";
      payload = { job, tone: "direct", angle: val("d-angle") || "direct_impact" };
    } else if (k === "interview-prep") { path = "/api/documents/interview-prep"; payload = { job }; }
    else if (k === "outreach") { path = "/api/documents/outreach"; payload = { job }; }
    else if (k === "founder-cold-email") {
      path = "/api/outreach/founder-email";
      payload = { job, founder_name: val("d-fname"), recipient_email: val("d-femail"), angle: val("d-fangle") || "scale_velocity", custom_observation: val("d-fobs") };
    } else if (k === "linkedin-founder-dm") {
      path = "/api/outreach/linkedin-founder";
      payload = { job, founder_name: val("d-fname"), angle: val("d-fangle") || "scale_velocity" };
    } else {
      path = "/api/bigtech/pitch";
      payload = { company_key: val("d-bcompany") || "google", req_id: val("d-breq"), recruiter_name: val("d-brec"), leveling_tier: val("d-blevel") || "mid", job };
    }

    doc.busy = true; doc.error = null; doc.data = null; doc.kind = k; doc.subject = 0; doc.view = k === "tailor-resume" ? "resume" : "letter";
    doc.ctl = new AbortController();
    const btn = byId("btn-generate");
    btn.setAttribute("aria-busy", "true");
    btn.innerHTML = `${icon("x")}<span>Stop</span>`;
    renderDoc();
    if (!desktopQuery.matches) byId("paper-wrap").scrollIntoView({ block: "start", behavior: "smooth" });
    try {
      const d = await apiPost(path, payload, doc.ctl.signal);
      doc.data = d || {};
      doc.gmailUrl = (d && d.gmail_compose_url) || "";
      if (!d || !Object.keys(d).length) throw new Error("The service returned an empty document.");
    } catch (e) {
      if (e.name === "AbortError") { toast("Stopped."); } else { doc.error = e; }
    } finally {
      doc.busy = false;
      btn.removeAttribute("aria-busy");
      btn.innerHTML = `${icon("pen-line")}<span>Write ${esc((DOC_KINDS[k] || "document").toLowerCase())}</span>`;
    }
    renderDoc();
    if (doc.data) byId("paper-wrap").focus({ preventScroll: true });
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;opacity:0;inset-block-start:0";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      ta.remove();
      return ok;
    }
  }

  function printDoc() {
    const prev = document.title;
    const who = (state.active && state.active.name) || "Resume";
    const what = doc.kind === "tailor-resume" || doc.view === "resume" ? "Resume" : "Cover letter";
    document.title = [who, what, val("d-company")].filter(Boolean).join(" - ");
    const restore = () => { document.title = prev; window.removeEventListener("afterprint", restore); };
    window.addEventListener("afterprint", restore);
    window.print();
  }

  async function findEmail() {
    const name = val("fi-name"), company = val("fi-company"), link = val("fi-linkedin");
    const out = byId("finder-out");
    if (!company && !link && !name) { out.innerHTML = `<p class="field-error">Enter a company or a LinkedIn link.</p>`; byId("fi-company").focus(); return; }
    const btn = byId("btn-find-email");
    btn.setAttribute("aria-busy", "true");
    out.innerHTML = `<p class="status-text mute" role="status">${icon("loader-circle", "icon-sm spin")}Checking the company's mail setup.</p>`;
    try {
      const r = await apiPost("/api/email-finder/find", { name, company, linkedin_url: link, role: val("fi-role") || "Founder & CEO" });
      if (!r || !r.primary_email) {
        out.innerHTML = `<div class="notice warn">${icon("triangle-alert")}<div><p>No address passed the checks. Try the full company domain, for example stripe.com.</p></div></div>`;
      } else {
        const others = (r.candidates || []).slice(1);
        out.innerHTML = `<div class="finder-result"><span class="addr">${esc(r.primary_email)}</span><span class="legend">${esc(r.confidence_pct)}% confidence${r.mail_provider ? ", " + esc(r.mail_provider) : ""}</span>${others.length ? `<span class="legend">Other options: ${others.map((c) => esc(c.email) + " (" + esc(c.confidence_pct) + "%)").join(", ")}</span>` : ""}<div class="form-foot"><button class="btn btn-primary btn-sm" type="button" data-use-email="${esc(r.primary_email)}">Use in a founder email</button><button class="btn btn-secondary btn-sm" type="button" data-copy-email="${esc(r.primary_email)}">${icon("copy", "icon-sm")}<span>Copy</span></button></div></div>`;
      }
    } catch (e) {
      out.innerHTML = e.offline ? offlineNotice(false) : errorNotice("The search failed. " + e.message, false);
    } finally { btn.removeAttribute("aria-busy"); }
  }

  function initDocs() {
    if (docsInit) return;
    docsInit = true;
    paperEmpty();
    updateDocFields();

    $$('input[name="doctype"]').forEach((r) => r.addEventListener("change", updateDocFields));
    byId("doc-form").addEventListener("submit", (e) => { e.preventDefault(); generateDoc(); });
    ["d-title", "d-company", "d-fname"].forEach((id) => byId(id).addEventListener("input", () => clearFieldError(byId(id))));

    byId("finder").addEventListener("toggle", () => {
      if (byId("finder").open) {
        if (!val("fi-company") && val("d-company")) byId("fi-company").value = val("d-company");
        if (!val("fi-name") && val("d-fname") && !/linkedin\.com/i.test(val("d-fname"))) byId("fi-name").value = val("d-fname");
      }
    });
    byId("btn-find-email").addEventListener("click", findEmail);
    byId("finder-out").addEventListener("click", async (e) => {
      const u = e.target.closest("[data-use-email]");
      if (u) {
        $('input[name="doctype"][value="founder-cold-email"]').checked = true;
        updateDocFields();
        byId("d-femail").value = u.dataset.useEmail;
        if (val("fi-name") && !val("d-fname")) byId("d-fname").value = val("fi-name");
        if (val("fi-company") && !val("d-company") && !/\./.test(val("fi-company"))) byId("d-company").value = val("fi-company");
        toast("Address added to the founder email.");
        byId("d-fname").focus();
        return;
      }
      const c = e.target.closest("[data-copy-email]");
      if (c) toast((await copyText(c.dataset.copyEmail)) ? "Copied." : "Copy failed. Select the address and copy it by hand.", { kind: null });
    });

    byId("paper-wrap").addEventListener("click", async (e) => {
      if (e.target.closest("[data-retry]")) { generateDoc(); return; }
      const v = e.target.closest("[data-view]");
      if (v) { doc.view = v.dataset.view; renderDoc(); const again = $(`[data-view="${doc.view}"]`); if (again) again.focus(); return; }
      if (e.target.closest("[data-marks]")) {
        doc.marks = !doc.marks;
        lsSet("jh-marks", doc.marks ? "on" : "off");
        renderDoc();
        const again = $("[data-marks]");
        if (again) again.focus();
        return;
      }
      const cp = e.target.closest("[data-copy]");
      if (cp) {
        const id = cp.dataset.copy === "__all" ? "main" : cp.dataset.copy;
        const text = doc.texts[id] || "";
        toast(text && (await copyText(text)) ? "Copied." : "Nothing to copy.");
        return;
      }
      if (e.target.closest("[data-print]")) { printDoc(); return; }
      if (e.target.closest("[data-draft]")) {
        const b = e.target.closest("[data-draft]");
        const d = doc.data || {};
        const subs = d.subject_options || [];
        b.setAttribute("aria-busy", "true");
        try {
          const r = await apiPost("/api/outreach/save-draft", { to_email: doc.recipient || val("d-femail"), subject: subs[doc.subject] || "", body: d.body || "" });
          if (r && r.success === false) throw new Error(r.message || "The draft was not saved.");
          toast("Saved to your Gmail drafts.");
        } catch (err) {
          toast("Draft not saved. " + err.message + " Check your Gmail app password in Settings.", { kind: "bad" });
        } finally { b.removeAttribute("aria-busy"); }
      }
    });
    byId("paper-wrap").addEventListener("change", (e) => {
      if (e.target.name === "subj") { doc.subject = Number(e.target.value) || 0; const d = doc.data || {}; const subs = d.subject_options || []; doc.texts.main = (subs[doc.subject] ? "Subject: " + subs[doc.subject] + "\n\n" : "") + (d.body || ""); }
    });
  }

  routeHooks.documents = (arg, changed) => {
    initDocs();
    if (!changed) return;
    setHead("Documents", PAGES.documents.sub, "");
    updateUsing();
    const draft = state.docDraft;
    if (draft) {
      state.docDraft = null;
      const r = $(`input[name="doctype"][value="${draft.kind}"]`);
      if (r) r.checked = true;
      byId("d-title").value = draft.title || "";
      byId("d-company").value = draft.company || "";
      byId("d-desc").value = draft.description || "";
      updateDocFields();
      if (state.active && (draft.title || draft.company)) generateDoc();
    }
  };

  /* ============================================================ RESUME */
  let resumeInit = false;
  let uploading = null; // file name while an upload runs
  let folderPath = null;

  function prettyLink(u) {
    return String(u || "").replace(/^https?:\/\/(www\.)?/i, "").replace(/\/$/, "");
  }
  function safeHref(u) {
    const s = String(u || "").trim();
    if (!s) return "";
    return /^https?:\/\//i.test(s) ? s : "https://" + s;
  }

  function dropzoneHtml(compact) {
    if (uploading) {
      return `<div class="dropzone" role="status" aria-busy="true">${icon("loader-circle", "icon-lg spin")}<strong>Reading ${esc(uploading)}</strong><span class="hint">Pulling out your contact details, skills and experience.</span></div>`;
    }
    return `<div class="dropzone" role="button" tabindex="0" data-pick aria-label="Choose a resume file">${icon("file-up", "icon-lg")}<strong>${compact ? "Add another resume" : "Drop your resume here"}</strong><span class="hint">or choose a file. PDF, Word, text or Markdown.</span></div>`;
  }

  function folderHtml() {
    return `<details class="disclosure"><summary>${icon("folder")}Use the resumes folder instead${icon("chevron-down")}</summary><div class="inner">
      <p class="hint">Put resume files in this folder, then scan it. JobHunter adds each file as a variant.</p>
      <div class="path-row"><code class="mono" id="folder-path">${esc(folderPath || "Looking up the folder")}</code><button class="btn btn-secondary btn-sm" type="button" data-copy-path${folderPath ? "" : " disabled"}>${icon("copy", "icon-sm")}<span>Copy path</span></button></div>
      <div><button class="btn btn-secondary btn-sm" type="button" data-scan>${icon("refresh-cw", "icon-sm")}<span>Scan folder</span></button></div></div></details>`;
  }

  function profileHtml(p) {
    const contact = [
      p.email ? `<a href="mailto:${esc(p.email)}">${esc(p.email)}</a>` : "",
      p.phone ? `<span dir="ltr">${esc(p.phone)}</span>` : "",
      p.location ? `<span dir="auto">${esc(p.location)}</span>` : "",
      p.linkedin ? `<a href="${esc(safeHref(p.linkedin))}" target="_blank" rel="noopener noreferrer">${esc(prettyLink(p.linkedin))}</a>` : "",
      p.github ? `<a href="${esc(safeHref(p.github))}" target="_blank" rel="noopener noreferrer">${esc(prettyLink(p.github))}</a>` : "",
      p.website ? `<a href="${esc(safeHref(p.website))}" target="_blank" rel="noopener noreferrer">${esc(prettyLink(p.website))}</a>` : "",
    ].filter(Boolean);
    const skills = p.skills || [];
    const exp = p.experience || [];
    const missing = [];
    if (!p.email) missing.push("an email address");
    if (!p.phone) missing.push("a phone number");
    if (!skills.length) missing.push("skills");
    if (!exp.length) missing.push("work experience");
    const gap = missing.length ? `<div class="notice warn">${icon("triangle-alert")}<div><p><strong>JobHunter did not find ${missing.length === 1 ? missing[0] : missing.slice(0, -1).join(", ") + " or " + missing[missing.length - 1]} in this file.</strong></p><p>It will leave ${missing.length === 1 ? "that" : "those"} blank instead of inventing ${missing.length === 1 ? "it" : "them"}. Check the file, or add a text version.</p></div></div>` : "";
    return `<article>
      <header class="profile-head">
        <h2 dir="auto">${esc(p.name || "Name not found")}</h2>
        ${p.target_title ? `<p class="profile-role" dir="auto">${esc(p.target_title)}${typeof p.experience_years === "number" ? `, ${p.experience_years} ${p.experience_years === 1 ? "year" : "years"} of experience` : ""}</p>` : ""}
        ${contact.length ? `<p class="profile-contact">${contact.map((c) => `<span>${c}</span>`).join("")}</p>` : ""}
      </header>
      ${gap}
      ${skills.length ? `<section class="section" aria-labelledby="h-skills"><h3 id="h-skills">Skills <span class="num legend">${skills.length}</span></h3><ul class="skill-list">${skills.map((s) => `<li dir="auto">${esc(s)}</li>`).join("")}</ul></section>` : ""}
      ${exp.length ? `<section class="section" aria-labelledby="h-exp"><h3 id="h-exp">Experience</h3><div class="exp-list">${exp.map((x) => `<div class="exp"><div class="when">${esc(x.period || x.dates || "")}</div><div class="body"><div class="what" dir="auto">${esc(x.title || x.role || "")}</div><div class="where" dir="auto">${esc(x.company || "")}</div>${x.summary || x.description ? `<p dir="auto">${esc(x.summary || x.description)}</p>` : ""}</div></div>`).join("")}</div></section>` : ""}
    </article>`;
  }

  function variantsHtml() {
    return `<section class="section" aria-labelledby="h-var"><h3 id="h-var">Resume variants</h3>
      <p class="hint">Keep one resume per kind of role. The active one drives fit scores, documents and autofill.</p>
      <ul class="variant-list">${state.profiles.map((v) => {
        const active = state.active && (state.active === v || (v.id && v.id === state.active.id));
        return `<li class="variant" data-active="${!!active}"><span><span class="t" dir="auto">${esc(v.target_title || v.name || "Resume")}</span><span class="d" dir="auto">${esc(v.filename || "resume")}, ${(v.skills || []).length} skills</span></span><span class="grow">${active ? `<span class="status-text ok">${icon("circle-check", "icon-sm")}Active</span>` : `<button class="btn btn-secondary btn-sm" type="button" data-activate="${esc(v.id != null ? v.id : v.name)}">Use this</button>`}</span></li>`;
      }).join("")}</ul></section>`;
  }

  function renderResume() {
    const root = byId("resume-root");
    if (!state.profilesLoaded) {
      root.innerHTML = `<div class="skeleton" style="height:2rem;width:40%;margin-block-end:1rem"></div><div class="skeleton" style="height:8rem"></div>`;
      return;
    }
    if (!state.profiles.length) {
      root.innerHTML = `<div class="first-run"><div><h2>Start with your resume</h2><p>JobHunter writes only from facts in your resume. Add one file and every fit score, document and form answer uses it. Nothing leaves this computer.</p></div>${dropzoneHtml(false)}${folderHtml()}</div>`;
      return;
    }
    const p = state.active || state.profiles[0];
    byId("page-sub").textContent = p.filename ? "Active file: " + p.filename : "";
    byId("page-sub").hidden = !p.filename;
    root.innerHTML = `<div class="resume-grid"><div>${profileHtml(p)}</div><aside style="display:grid;gap:var(--s5);align-content:start">${variantsHtml()}${dropzoneHtml(true)}${folderHtml()}</aside></div>`;
  }

  async function loadFolder() {
    if (folderPath) return;
    try {
      const d = await apiGet("/api/resumes/folder-info");
      folderPath = (d && (d.resumes_dir || d.path)) || "";
    } catch (e) { folderPath = ""; }
    const el = byId("folder-path");
    if (el) { el.textContent = folderPath || "Not available"; const b = $("[data-copy-path]"); if (b) b.disabled = !folderPath; }
  }

  async function uploadResume(file) {
    if (!file || uploading) return;
    const name = file.name || "resume";
    const ext = (name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
    if (![".pdf", ".docx", ".txt", ".md"].includes(ext)) { toast("Use a PDF, Word, text or Markdown file.", { kind: "bad" }); return; }
    if (file.size > 10 * 1024 * 1024) { toast("That file is larger than 10 MB.", { kind: "bad" }); return; }
    uploading = name;
    renderResume();
    try {
      const result = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = () => reject(new Error("The file could not be read."));
        if (ext === ".txt" || ext === ".md") r.readAsText(file); else r.readAsDataURL(file);
      });
      const payload = { filename: name, activate: true };
      if (typeof result === "string" && result.startsWith("data:")) payload.content_base64 = result.slice(result.indexOf(",") + 1);
      else payload.text = result;
      const res = await apiPost("/api/resumes/upload", payload);
      if (res && res.success === false) throw new Error((res.error && res.error.message) || "The file could not be parsed.");
      await loadProfiles(true);
      const p = (res && res.profile) || state.active || {};
      const n = (p.skills || []).length;
      toast(n ? "Added " + name + ". Found " + n + " skills." : "Added " + name + ", but found no skills in it.", { kind: n ? null : "bad" });
      if (state.route !== "resume") go("resume");
    } catch (e) {
      toast("Upload failed. " + e.message, { kind: "bad" });
    } finally {
      uploading = null;
      renderResume();
      if (state.route === "jobs") jobsNotice();
    }
  }

  function initResume() {
    if (resumeInit) return;
    resumeInit = true;
    const input = byId("file-input");
    input.addEventListener("change", () => { if (input.files && input.files[0]) uploadResume(input.files[0]); input.value = ""; });
    const root = byId("resume-root");
    root.addEventListener("click", async (e) => {
      if (e.target.closest("[data-pick]")) { input.click(); return; }
      if (e.target.closest("[data-copy-path]")) { toast((await copyText(folderPath)) ? "Path copied." : "Copy failed.", { kind: null }); return; }
      const sc = e.target.closest("[data-scan]");
      if (sc) {
        sc.setAttribute("aria-busy", "true");
        try {
          await apiPost("/api/resumes/scan", {});
          await loadProfiles(true);
          renderResume();
          toast(state.profiles.length ? "Scanned the folder. " + state.profiles.length + (state.profiles.length === 1 ? " resume" : " resumes") + " found." : "Scanned the folder. No resume files found.");
        } catch (err) { toast("Scan failed. " + err.message, { kind: "bad" }); }
        finally { sc.removeAttribute("aria-busy"); }
        return;
      }
      const act = e.target.closest("[data-activate]");
      if (act) {
        act.setAttribute("aria-busy", "true");
        const key = act.dataset.activate;
        const v = state.profiles.find((x) => String(x.id != null ? x.id : x.name) === key);
        try {
          await apiPost("/api/profile/activate", { name: (v && (v.name || v.id)) || key, id: v && v.id });
          await loadProfiles(true);
          renderResume();
          toast("Now using " + ((v && (v.target_title || v.name)) || "this resume") + ".");
        } catch (err) { toast("Could not switch. " + err.message, { kind: "bad" }); act.removeAttribute("aria-busy"); }
      }
    });
    root.addEventListener("keydown", (e) => {
      const dz = e.target.closest("[data-pick]");
      if (dz && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); input.click(); }
    });
    root.addEventListener("toggle", (e) => { if (e.target.matches("details") && e.target.open) loadFolder(); }, true);
  }

  routeHooks.resume = async (arg, changed) => {
    initResume();
    if (!changed) return;
    setHead("Resume", PAGES.resume.sub, "");
    renderResume();
    await loadProfiles(true);
    renderResume();
  };

  /* ============================================================ SETTINGS */
  const SECTIONS = [["search", "Search"], ["ai", "AI engine"], ["autofill", "Autofill"], ["gmail", "Gmail"], ["browser", "Browser"]];
  const MODELS = {
    gemini: ["gemini-3.8-flash", "gemini-3.1-pro", "gemini-3.5-flash"],
    openai: ["gpt-5-mini", "o3-mini", "gpt-5"],
    anthropic: ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"],
    deepseek: ["deepseek-chat", "deepseek-reasoner"],
    groq: ["llama-3.3-70b-versatile", "qwen-2.5-coder-32b"],
    mistral: ["mistral-large-latest", "pixtral-large-latest"],
    ollama: ["llama3.3", "qwen2.5-coder"],
  };
  const SUBMIT_MODES = [
    ["review", "Fill, then I submit", "The extension fills the form and stops. You read it and press Submit."],
    ["countdown", "Fill, then submit after a countdown", "The extension fills the form, then submits after 10 seconds. You can cancel during the countdown."],
  ];
  let settingsInit = false;
  let settingsSection = "search";
  let customModel = false;

  function showSection(id) {
    if (!SECTIONS.some(([s]) => s === id)) id = "search";
    settingsSection = id;
    $$(".settings-panel").forEach((p) => p.classList.toggle("show", p.dataset.panel === id));
    byId("settings-nav").innerHTML = SECTIONS.map(([s, label]) => `<li><a href="#/settings/${s}"${s === id ? ' aria-current="true"' : ""}>${label}</a></li>`).join("");
    byId("settings-tabs").innerHTML = SECTIONS.map(([s, label]) => `<button type="button" data-section="${s}" aria-pressed="${s === id}">${label}</button>`).join("");
    const label = SECTIONS.find(([s]) => s === id)[1];
    setHead("Settings", label, "");
  }

  function feedback(id, kind, text) {
    const el = byId(id);
    if (!el) return;
    el.innerHTML = text ? `<span class="status-text ${kind}">${icon(kind === "ok" ? "circle-check" : "circle-alert", "icon-sm")}${esc(text)}</span>` : "";
  }

  /* ---------- search preferences */
  function fillPrefs(p) {
    byId("pref-countries").value = (p.target_countries || []).join(", ");
    byId("pref-cities").value = (p.home_cities || []).join(", ");
    byId("pref-mode").value = p.work_mode || "Any";
    byId("pref-excl-co").value = (p.excluded_companies || []).join(", ");
    byId("pref-excl-kw").value = (p.excluded_keywords || []).join(", ");
    byId("pref-dream").value = (p.dream_companies || []).join(", ");
    byId("pref-depth").value = p.search_depth || "standard";
    const types = p.job_types || [];
    $$("#pref-types input").forEach((c) => { c.checked = types.includes(c.value); });
  }

  async function savePrefs(e) {
    e.preventDefault();
    const updates = {
      target_countries: splitList(byId("pref-countries").value),
      home_cities: splitList(byId("pref-cities").value),
      work_mode: byId("pref-mode").value,
      job_types: $$("#pref-types input:checked").map((c) => c.value),
      excluded_companies: splitList(byId("pref-excl-co").value),
      excluded_keywords: splitList(byId("pref-excl-kw").value),
      dream_companies: splitList(byId("pref-dream").value),
      search_depth: byId("pref-depth").value,
    };
    const btn = e.submitter || $('button[type="submit"]', byId("form-search-prefs"));
    btn.setAttribute("aria-busy", "true");
    feedback("fb-search", "", "");
    try {
      await apiPost("/api/preferences", { updates });
      state.prefs = Object.assign({}, state.prefs, updates);
      feedback("fb-search", "ok", "Saved.");
      toast("Search preferences saved.");
    } catch (err) {
      feedback("fb-search", "bad", "Not saved. " + err.message);
    } finally { btn.removeAttribute("aria-busy"); }
  }

  /* ---------- AI engine */
  function renderAiMode() {
    const a = state.ai || {};
    const provider = String(a.provider || "").toLowerCase();
    let ic = "plug", t, p;
    if (a.mode === "direct_api") {
      ic = "key-round";
      t = "Using your own API key";
      p = "Provider: " + (provider || "not set") + (a.model ? ", model " + a.model : "") + ". JobHunter writes on its own.";
    } else if (a.mode === "mcp_client") {
      t = "Writing through the AI app that controls JobHunter";
      p = "No key is stored. JobHunter writes through the host that calls it, such as Claude or Cursor. Add a key below to write on your own.";
    } else {
      ic = "settings";
      t = "Template mode";
      p = "No AI model is connected. Documents come from fixed templates filled with your resume facts.";
    }
    byId("ai-mode").innerHTML = `${icon(ic)}<div><strong>${esc(t)}</strong><p>${esc(p)}</p></div>`;
    byId("ai-key-hint").textContent = a.key_configured ? "Stored key: " + (a.masked_key || "hidden") + ". Leave this empty to keep it." : "No key stored. Keys stay on this computer.";
    byId("btn-ai-clear").hidden = !a.key_configured;
  }

  function fillModels(provider, selected) {
    const rec = state.ai && state.ai.recommended_models && state.ai.recommended_models[provider];
    const list = Array.isArray(rec) && rec.length ? rec : MODELS[provider] || [];
    const sel = byId("ai-model");
    sel.innerHTML = list.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("");
    const custom = byId("ai-model-custom");
    if (selected && !list.includes(selected)) {
      customModel = true;
      custom.value = selected;
    } else {
      customModel = false;
      if (selected) sel.value = selected;
    }
    syncModelUi();
  }
  function syncModelUi() {
    byId("ai-model").hidden = customModel;
    byId("ai-model-custom").hidden = !customModel;
    byId("ai-model-toggle").textContent = customModel ? "Pick from the list" : "Use a different model name";
  }

  function applyAi() {
    const a = state.ai || {};
    const provider = a.provider && MODELS[a.provider] ? a.provider : "gemini";
    byId("ai-provider").value = provider;
    renderAiMode();
    fillModels(provider, a.model || "");
  }

  async function loadAi() {
    try { state.ai = await apiGet("/api/ai/status"); applyAi(); } catch (e) { byId("ai-mode").innerHTML = `${icon("wifi-off")}<div><strong>Could not read the AI engine.</strong><p>${esc(e.message)}</p></div>`; }
  }

  async function saveAi(e) {
    e.preventDefault();
    const provider = byId("ai-provider").value;
    const model = customModel ? byId("ai-model-custom").value.trim() : byId("ai-model").value;
    const key = byId("ai-key").value.trim();
    const had = state.ai && state.ai.key_configured;
    if (!key && !had) {
      feedback("fb-ai", "bad", "Paste an API key to use your own account.");
      byId("ai-key").focus();
      return;
    }
    const body = { provider, model };
    if (key) body.api_key = key;
    const btn = byId("btn-ai-save");
    btn.setAttribute("aria-busy", "true");
    try {
      await apiPost("/api/ai/config", body);
      byId("ai-key").value = "";
      await loadAi();
      feedback("fb-ai", "ok", "Saved. JobHunter now writes with " + provider + (model ? ", " + model : "") + ".");
    } catch (err) { feedback("fb-ai", "bad", "Not saved. " + err.message); }
    finally { btn.removeAttribute("aria-busy"); }
  }

  async function testAi() {
    const btn = byId("btn-ai-test");
    btn.setAttribute("aria-busy", "true");
    feedback("fb-ai", "", "");
    byId("fb-ai").innerHTML = `<span class="status-text mute">${icon("loader-circle", "icon-sm spin")}Sending a test message.</span>`;
    try {
      const r = await apiPost("/api/ai/test", {});
      feedback("fb-ai", "ok", "Connected" + (r && r.latency_ms ? " in " + r.latency_ms + " ms" : "") + (r && r.provider ? " (" + r.provider + (r.model ? ", " + r.model : "") + ")." : "."));
    } catch (err) { feedback("fb-ai", "bad", "Connection failed. " + err.message); }
    finally { btn.removeAttribute("aria-busy"); }
  }

  async function clearAiKey() {
    const ok = await confirmDialog({ title: "Remove the stored API key?", text: "JobHunter goes back to writing through the AI app that controls it, or to templates if none is connected.", ok: "Remove key", cancel: "Keep it" });
    if (!ok) return;
    try {
      await apiPost("/api/ai/clear-key", {});
      await loadAi();
      feedback("fb-ai", "ok", "Key removed.");
    } catch (err) { feedback("fb-ai", "bad", "Could not remove it. " + err.message); }
  }

  /* ---------- autofill answers */
  function readAutofillLocal() {
    try { return JSON.parse(lsGet("jh-autofill") || "{}"); } catch (e) { return {}; }
  }
  function renderSubmitModes(current) {
    byId("auto-mode").innerHTML = SUBMIT_MODES.map(([v, label]) => `<button type="button" role="radio" aria-checked="${v === current}" data-v="${v}">${label}</button>`).join("");
    const m = SUBMIT_MODES.find(([v]) => v === current) || SUBMIT_MODES[0];
    byId("auto-mode-hint").textContent = m[2];
    byId("auto-mode").dataset.value = m[0];
  }
  function fillAutofill() {
    const p = state.prefs || {};
    const local = readAutofillLocal();
    const pick = (k) => (p[k] != null && p[k] !== "" ? p[k] : local[k] != null ? local[k] : "");
    let visa = pick("needs_visa_sponsorship");
    if (visa === true || visa === "true") visa = "yes"; else if (visa === false || visa === "false") visa = "no";
    byId("auto-auth").value = String(pick("work_authorized") || "");
    byId("auto-visa").value = String(visa || "");
    byId("auto-notice").value = String(pick("notice_period") || "");
    renderSubmitModes(String(pick("submission_mode") || "review"));
  }
  async function saveAutofill(e) {
    e.preventDefault();
    const a = { work_authorized: byId("auto-auth").value, needs_visa_sponsorship: byId("auto-visa").value, notice_period: byId("auto-notice").value, submission_mode: byId("auto-mode").dataset.value || "review" };
    lsSet("jh-autofill", JSON.stringify(a));
    const updates = { work_authorized: a.work_authorized, notice_period: a.notice_period, submission_mode: a.submission_mode, needs_visa_sponsorship: a.needs_visa_sponsorship === "yes" ? true : a.needs_visa_sponsorship === "no" ? false : null };
    const btn = e.submitter || $('button[type="submit"]', byId("form-autofill"));
    btn.setAttribute("aria-busy", "true");
    try {
      await apiPost("/api/preferences", { updates });
      const back = await apiGet("/api/preferences");
      state.prefs = back || state.prefs;
      const kept = back && ["work_authorized", "notice_period", "submission_mode"].every((k) => back[k] === updates[k]);
      feedback("fb-auto", kept ? "ok" : "bad", kept ? "Saved. The extension reads these answers." : "Saved in this browser only. This version of the service stores just the sponsorship answer.");
      toast("Autofill answers saved.");
    } catch (err) { feedback("fb-auto", "bad", "Not saved. " + err.message); }
    finally { btn.removeAttribute("aria-busy"); }
  }

  async function solveQuestion(e) {
    e.preventDefault();
    const q = byId("solve-q").value.trim();
    const out = byId("solve-out");
    clearFieldError(byId("solve-q"));
    if (!q) { setFieldError(byId("solve-q"), "Paste a question first."); byId("solve-q").focus(); return; }
    const btn = byId("btn-solve");
    btn.setAttribute("aria-busy", "true");
    out.innerHTML = `<p class="status-text mute" role="status">${icon("loader-circle", "icon-sm spin")}Writing an answer from your resume.</p>`;
    try {
      const r = await apiPost("/api/extension/solve", { question: q });
      const v = verdictOf(r && r.review);
      const ans = r && (r.answer || r.text);
      out.innerHTML = ans ? `<div class="answer-box" dir="auto">${esc(ans)}</div><div class="form-foot" style="margin-block-start:var(--s2)"><span class="verdict ${v.cls}">${icon(v.icon, "icon-sm")}${esc(v.label)}</span><button class="btn btn-quiet btn-sm" type="button" data-copy-answer>${icon("copy", "icon-sm")}<span>Copy</span></button></div>` : `<div class="notice warn">${icon("triangle-alert")}<div><p>Your resume has no facts that answer this question. The extension would ask you instead of guessing.</p></div></div>`;
      out.dataset.answer = ans || "";
    } catch (err) { out.innerHTML = err.offline ? offlineNotice(false) : errorNotice("No answer. " + err.message, false); }
    finally { btn.removeAttribute("aria-busy"); }
  }

  /* ---------- gmail */
  function renderGmail() {
    const g = state.gmail;
    const on = g && g.configured;
    byId("gmail-state").innerHTML = on
      ? `${icon("circle-check")}<div><strong>Connected${g.email ? " as " + esc(g.email) : ""}</strong><p>JobHunter checks for confirmation, interview and rejection emails and moves applications for you.</p></div>`
      : `${icon("mail")}<div><strong>Not connected</strong><p>Connect Gmail so applications move to Applied, Interview or Closed without manual work.</p></div>`;
    byId("btn-gmail-sync2").hidden = !on;
    if (g && g.email && !byId("gm-email").value) byId("gm-email").value = g.email;
  }
  async function saveGmail(e) {
    e.preventDefault();
    const email = byId("gm-email").value.trim();
    const pass = byId("gm-pass").value.replace(/\s+/g, "");
    clearFieldError(byId("gm-email")); clearFieldError(byId("gm-pass"));
    if (!/^\S+@\S+\.\S+$/.test(email)) { setFieldError(byId("gm-email"), "Enter your Gmail address."); byId("gm-email").focus(); return; }
    if (!pass) { setFieldError(byId("gm-pass"), "Enter the app password from your Google account."); byId("gm-pass").focus(); return; }
    const btn = e.submitter || $('button[type="submit"]', byId("form-gmail"));
    btn.setAttribute("aria-busy", "true");
    try {
      await apiPost("/api/gmail/config", { email, app_password: pass });
      byId("gm-pass").value = "";
      await loadGmailStatus();
      renderGmail();
      feedback("fb-gmail", "ok", "Saved.");
    } catch (err) { feedback("fb-gmail", "bad", "Not saved. " + err.message); }
    finally { btn.removeAttribute("aria-busy"); }
  }
  async function syncGmailNow() {
    const btn = byId("btn-gmail-sync2");
    btn.setAttribute("aria-busy", "true");
    try {
      const r = await apiPost("/api/gmail/sync", {});
      await reloadApps();
      const u = (r && r.applications_updated) || 0, c = (r && r.applications_created) || 0;
      feedback("fb-gmail", "ok", u || c ? u + " updated, " + c + " added." : "No changes.");
    } catch (err) { feedback("fb-gmail", "bad", err.message); }
    finally { btn.removeAttribute("aria-busy"); }
  }

  /* ---------- browser */
  async function launchBrowser(btn) {
    if (btn) btn.setAttribute("aria-busy", "true");
    try {
      await apiPost("/api/auto-apply/launch", { url: location.origin });
      toast("A browser with the extension is opening.");
    } catch (err) { toast("Could not open the browser. " + err.message, { kind: "bad" }); }
    finally { if (btn) btn.removeAttribute("aria-busy"); }
  }
  async function loadBrowsers() {
    const list = byId("browser-list");
    try {
      const d = await apiGet("/api/desktop/extension-status");
      const b = (d && d.browsers) || [];
      list.innerHTML = b.length ? b.map((x) => `<li><strong>${esc(x.name || "Browser")}</strong><code class="mono">${esc(x.path || "")}</code></li>`).join("") : `<li>No Chromium browser was found. Install Chrome or Edge, then reload this page.</li>`;
    } catch (e) { list.innerHTML = `<li>Could not look for browsers. ${esc(e.message)}</li>`; }
  }

  async function loadSettingsData() {
    try {
      state.prefs = await apiGet("/api/preferences");
      fillPrefs(state.prefs || {});
      fillAutofill();
    } catch (e) { feedback("fb-search", "bad", e.offline ? "JobHunter is not running." : e.message); }
    loadAi();
    loadGmailStatus().then(renderGmail);
    loadBrowsers();
  }

  function initSettings() {
    if (settingsInit) return;
    settingsInit = true;
    byId("form-search-prefs").addEventListener("submit", savePrefs);
    byId("form-ai").addEventListener("submit", saveAi);
    byId("btn-ai-test").addEventListener("click", testAi);
    byId("btn-ai-clear").addEventListener("click", clearAiKey);
    byId("ai-provider").addEventListener("change", (e) => fillModels(e.target.value, ""));
    byId("ai-model-toggle").addEventListener("click", () => { customModel = !customModel; syncModelUi(); (customModel ? byId("ai-model-custom") : byId("ai-model")).focus(); });
    byId("ai-key-eye").addEventListener("click", (e) => {
      const b = e.currentTarget, inp = byId("ai-key");
      const show = inp.type === "password";
      inp.type = show ? "text" : "password";
      b.setAttribute("aria-pressed", String(show));
      b.setAttribute("aria-label", show ? "Hide key" : "Show key");
      b.querySelector("use").setAttribute("href", show ? "#i-eye-off" : "#i-eye");
    });
    byId("form-autofill").addEventListener("submit", saveAutofill);
    byId("auto-mode").addEventListener("click", (e) => { const b = e.target.closest("button[data-v]"); if (b) renderSubmitModes(b.dataset.v); });
    byId("form-solve").addEventListener("submit", solveQuestion);
    byId("solve-out").addEventListener("click", async (e) => { if (e.target.closest("[data-copy-answer]")) toast((await copyText(byId("solve-out").dataset.answer || "")) ? "Copied." : "Copy failed."); });
    byId("form-gmail").addEventListener("submit", saveGmail);
    byId("btn-gmail-sync2").addEventListener("click", syncGmailNow);
    byId("btn-launch2").addEventListener("click", (e) => launchBrowser(e.currentTarget));
    byId("settings-tabs").addEventListener("click", (e) => { const b = e.target.closest("[data-section]"); if (b) go("settings/" + b.dataset.section); });
  }

  routeHooks.settings = (arg, changed) => {
    initSettings();
    showSection(arg || "search");
    if (changed) loadSettingsData();
  };

  /* ============================================================ BOOT */
  function isTyping(t) {
    return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
  }

  let gPending = false;
  function initShortcuts() {
    document.addEventListener("keydown", (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape" && openMenu) { const t = openMenu.trigger; closeMenu(); t.focus(); return; }
      const openDlg = document.querySelector("dialog[open]");
      if (isTyping(e.target) || (openDlg && openDlg.id !== "job-drawer")) return;
      const k = e.key;
      if (gPending) {
        gPending = false;
        const map = { j: "jobs", a: "applications", d: "documents", r: "resume", s: (state.method === "modern" ? "signals" : "settings"), o: "outreach", i: "signals" };
        if (map[k]) { e.preventDefault(); go(map[k]); }
        return;
      }
      if (k === "g") { gPending = true; setTimeout(() => { gPending = false; }, 1200); return; }
      if (k === "?") { e.preventDefault(); byId("dlg-keys").showModal(); return; }
      if (state.route !== "jobs") return;
      if (k === "/" && !openDlg) { e.preventDefault(); byId("q").focus(); }
      else if (k === "j") moveSelection(1);
      else if (k === "k") moveSelection(-1);
      else if (k === "s" && currentJob()) onSave();
      else if (k === "a" && currentJob()) onApply();
    });
  }

  function boot() {
    initTheme();
    initFileDrop();
    initShortcuts();
    initMethod();
    initSignals();
    initOutreach();
    [byId("dlg-confirm"), byId("dlg-keys"), byId("dlg-contacts-panel"), byId("dlg-company-brief"), byId("dlg-method-onboarding"), byId("dlg-followup-draft"), byId("dlg-reply-record"), byId("dlg-weekly-report")].forEach(d => { if (d) closeOnBackdrop(d); });
    byId("btn-shortcuts").addEventListener("click", () => byId("dlg-keys").showModal());
    byId("btn-launch-browser").addEventListener("click", (e) => launchBrowser(e.currentTarget));
    byId("job-state").addEventListener("click", () => {});
    
    // V5 Header Radar and Lifecycle listeners
    const radarBtn = byId("btn-radar-header");
    if (radarBtn) radarBtn.addEventListener("click", onRadarHeaderClick);
    const keepBtn = byId("btn-lifecycle-keep");
    if (keepBtn) keepBtn.addEventListener("click", onKeepExpiringJobs);
    const ackBtn = byId("btn-lifecycle-ack");
    if (ackBtn) ackBtn.addEventListener("click", onAckLifecycleBanner);
    const reviewBtn = byId("btn-lifecycle-review");
    if (reviewBtn) reviewBtn.addEventListener("click", () => {
      const closingWrap = byId("closing-soon-wrap");
      if (closingWrap) {
        closingWrap.open = true;
        closingWrap.scrollIntoView({ behavior: "smooth" });
      }
    });

    // V5 System Status Drawer listener
    const statusDrawer = byId("dlg-system-status");
    const railStatus = byId("rail-status");
    if (railStatus && statusDrawer) {
      closeOnBackdrop(statusDrawer);
      const openStatus = () => {
        statusDrawer.showModal();
        pollRadarStatus();
        pollRefreshStatus();
        renderSystemStatusDrawer();
      };
      railStatus.addEventListener("click", openStatus);
      railStatus.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openStatus();
        }
      });
      const btnClose = byId("btn-status-drawer-close");
      if (btnClose) btnClose.addEventListener("click", () => statusDrawer.close());
      const btnAck = byId("btn-status-radar-ack");
      if (btnAck) btnAck.addEventListener("click", async () => {
        await onRadarHeaderClick();
        renderSystemStatusDrawer();
      });
      const btnRefreshNow = byId("btn-status-refresh-now");
      if (btnRefreshNow) btnRefreshNow.addEventListener("click", onManualRefreshClick);
    }

    pollRadarStatus();
    pollCleanupStatus();
    pollRefreshStatus();
    setInterval(pollRadarStatus, 25000);
    setInterval(pollCleanupStatus, 60000);
    setInterval(pollRefreshStatus, 45000);

    window.addEventListener("hashchange", onRoute);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        if (state.online === false) checkStatus();
        pollRadarStatus();
        pollCleanupStatus();
        pollRefreshStatus();
      }
    });
    desktopQuery.addEventListener("change", () => { if (state.route === "jobs") syncSelection(); });

    // Draw the first screen at once, then fill it with data.
    onRoute();
    checkStatus();
    Promise.all([loadProfiles(), reloadApps()]).then(() => {
      jobsNotice();
      if (state.route === "jobs") {
        const sub = state.active ? "Fit scores compare each role with " + (state.active.name || "your resume") + "." : PAGES.jobs.sub;
        byId("page-sub").textContent = sub;
        byId("page-sub").hidden = false;
        renderJobs();
        syncSelection();
      }
      if (state.route === "signals") {
        loadSignalsQuery();
      }
      if (state.route === "outreach") {
        loadOutreachData();
      }
      if (state.route === "documents") updateUsing();
      if (state.route === "resume") renderResume();
    });
  }

  boot();
})();
