/*
 * JobHunter content script.
 * Runs only on known application sites, or on a page the person opens it on.
 * The panel lives in a Shadow DOM, so page CSS cannot change it and it cannot change the page.
 * It fills empty fields only, lists every change with an Undo, and never submits unless the
 * person chose the countdown mode and every answer was found.
 */
(function () {
  "use strict";
  if (window.__jhLoaded) return;
  window.__jhLoaded = true;

  const CSS = window.__JH_CSS || "";
  const ICONS = window.__JH_ICONS || {};
  const LOGO = window.__JH_LOGO || "";
  const DASHBOARD = "http://127.0.0.1:8765";

  /* ---------------------------------------------------------------- helpers */
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clean = (s) => String(s || "").replace(/\s+/g, " ").replace(/[*∗]+/g, "").trim();
  const svg = (n, cls) => `<svg viewBox="0 0 24 24" aria-hidden="true"${cls ? ` class="${cls}"` : ""}>${ICONS[n] || ""}</svg>`;

  function api(path, method, body) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "jh-api", path, method: method || "GET", body }, (res) => {
          if (chrome.runtime.lastError || !res) resolve({ ok: false, offline: true, error: "JobHunter is not running on this computer." });
          else resolve(res);
        });
      } catch (e) {
        resolve({ ok: false, offline: true, error: "The extension was reloaded. Reload this page." });
      }
    });
  }

  const host = location.hostname;
  const platform = /(^|\.)linkedin\.com$/.test(host) ? "linkedin" : /(greenhouse|lever|ashbyhq|myworkdayjobs|workable|smartrecruiters|bamboohr|icims|jobvite|recruitee|teamtailor|breezy|personio|taleo|oraclecloud)/.test(host) ? "ats" : "page";

  /* ---------------------------------------------------------------- state */
  const S = {
    open: false,
    stage: "idle", // idle | connecting | offline | noresume | ready | working | done
    profile: null,
    prefs: {},
    entries: [], // fields filled by the panel
    needs: [], // fields the panel could not answer
    status: "",
    countdown: false,
    note: null, // {text, kind}
    applied: false,
    watching: false,
    message: "",
  };
  let timer = null;
  let host_el = null, root = null, shadow = null;

  /* ---------------------------------------------------------------- finding fields */
  function isVisible(el) {
    if (!el.getClientRects().length) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== "hidden" && cs.display !== "none";
  }
  function isFillable(el) {
    if (host_el && host_el.contains(el)) return false;
    if (el.disabled || el.readOnly) return false;
    const t = (el.type || "").toLowerCase();
    if (el.tagName === "INPUT" && ["hidden", "submit", "button", "checkbox", "file", "password", "image", "reset", "search", "range", "color"].includes(t)) return false;
    if ((el.getAttribute("role") || "") === "searchbox" || (el.tagName === "INPUT" && /^(q|query|search)$/i.test(el.name || ""))) return false;
    return isVisible(el);
  }
  function fields() {
    return Array.from(document.querySelectorAll("input, select, textarea")).filter(isFillable);
  }

  function labelOf(el) {
    const parts = [];
    if (el.labels && el.labels.length) Array.from(el.labels).forEach((l) => parts.push(l.innerText));
    const by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(n.innerText); });
    parts.push(el.getAttribute("aria-label") || "", el.placeholder || "");
    if (!clean(parts.join(""))) {
      const fs = el.closest("fieldset");
      const lg = fs && fs.querySelector("legend");
      if (lg) parts.push(lg.innerText);
      const box = el.closest("[class*='field'],[class*='question'],.form-group,li,div");
      const l = box && box.querySelector("label,legend,[class*='label']");
      if (l) parts.push(l.innerText);
    }
    return clean(parts.join(" "));
  }

  function classify(el, text) {
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    const type = (el.type || "").toLowerCase();
    const t = text.toLowerCase();
    if (ac === "given-name" || /\b(first|given)\s*name\b/.test(t)) return "first";
    if (ac === "family-name" || /\b(last|family|sur)\s*name\b/.test(t)) return "last";
    if (type === "email" || ac === "email" || /e-?mail/.test(t)) return "email";
    if (type === "tel" || ac.startsWith("tel") || /\b(phone|mobile|telephone)\b/.test(t)) return "phone";
    if (/linkedin/.test(t)) return "linkedin";
    if (/github/.test(t)) return "github";
    if (/(portfolio|personal (web)?site|website)/.test(t)) return "website";
    if (/(authori[sz]ed|legally|eligible|right) to work|work authori[sz]ation|work permit/.test(t)) return "auth";
    if (/sponsor|visa/.test(t)) return "sponsor";
    if (/notice period|available to start|when can you start|start date|availability/.test(t)) return "notice";
    if (/years? of (professional |relevant |work |total )?experience|experience.{0,20}years/.test(t)) return "years";
    if (/\b(city|current location|where are you (based|located))\b/.test(t) && !/relocat/.test(t)) return "location";
    if (ac === "name" || /^(full\s*name|your name|name|candidate name|legal name)$/.test(t.trim())) return "full";
    return null;
  }

  const NOTICE_TEXT = { immediate: "Immediately", "2weeks": "2 weeks", "1month": "1 month" };
  function answerFor(kind) {
    const p = S.profile || {}, pr = S.prefs || {};
    const yn = (v) => (v === true || v === "yes" || v === "true" ? "yes" : v === false || v === "no" || v === "false" ? "no" : null);
    const name = clean(p.name);
    const parts = name.split(" ").filter(Boolean);
    switch (kind) {
      case "first": return parts[0] || null;
      case "last": return parts.length > 1 ? parts.slice(1).join(" ") : null;
      case "full": return name || null;
      case "email": return p.email || null;
      case "phone": return p.phone || null;
      case "linkedin": return p.linkedin || null;
      case "github": return p.github || null;
      case "website": return p.website || null;
      case "location": return p.location || null;
      case "years": return typeof p.experience_years === "number" ? String(p.experience_years) : null;
      case "auth": return yn(pr.work_authorized);
      case "sponsor": return yn(pr.needs_visa_sponsorship);
      case "notice": return NOTICE_TEXT[pr.notice_period] || null;
      default: return null;
    }
  }
  const WHY = {
    auth: "Set your work authorization in JobHunter Settings, under Autofill answers.",
    sponsor: "Set your sponsorship answer in JobHunter Settings, under Autofill answers.",
    notice: "Set your availability in JobHunter Settings, under Autofill answers.",
    years: "Your resume does not state years of experience.",
  };

  /* ---------------------------------------------------------------- changing the page */
  const RING = "0 0 0 2px #fff, 0 0 0 4px #000";
  function setValue(el, v) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const d = Object.getOwnPropertyDescriptor(proto, "value");
    if (d && d.set) d.set.call(el, v); else el.value = v;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function ring(el) {
    const prev = el.style.boxShadow;
    el.style.boxShadow = RING;
    return prev;
  }
  function record(entry) {
    entry.id = "e" + Math.random().toString(36).slice(2, 8);
    S.entries.push(entry);
  }

  function fillText(el, label, value, extra) {
    if (el.value && el.value.trim()) return false;
    const prevStyle = ring(el);
    setValue(el, value);
    record(Object.assign({ el, label, shown: value, prev: "", prevStyle, type: "text" }, extra || {}));
    return true;
  }
  function fillSelect(el, label, want) {
    const opts = Array.from(el.options).filter((o) => o.value !== "");
    const w = String(want).toLowerCase();
    const pick = opts.find((o) => clean(o.text).toLowerCase() === w) || opts.find((o) => clean(o.text).toLowerCase().startsWith(w)) || opts.find((o) => clean(o.text).toLowerCase().includes(w));
    if (!pick || (el.value && el.selectedIndex > 0)) return false;
    const prev = el.value, prevStyle = ring(el);
    setValue(el, pick.value);
    record({ el, label, shown: clean(pick.text), prev, prevStyle, type: "select" });
    return true;
  }
  function fillRadio(group, label, want) {
    if (group.some((r) => r.checked)) return false;
    const w = String(want).toLowerCase();
    const pick = group.find((r) => { const t = labelOf(r).toLowerCase(); return t === w || t.startsWith(w + " ") || t.startsWith(w + ","); });
    if (!pick) return false;
    const prevStyle = ring(pick);
    pick.click();
    record({ el: pick, label, shown: clean(labelOf(pick)) || want, prev: false, prevStyle, type: "radio" });
    return true;
  }

  function undo(id) {
    const i = S.entries.findIndex((e) => e.id === id);
    if (i < 0) return;
    const e = S.entries[i];
    try {
      if (e.type === "radio") { e.el.checked = false; e.el.dispatchEvent(new Event("change", { bubbles: true })); }
      else setValue(e.el, e.prev);
      e.el.style.boxShadow = e.prevStyle;
    } catch (err) { /* the field may have left the page */ }
    S.entries.splice(i, 1);
    render();
  }
  function undoAll() {
    S.entries.slice().forEach((e) => undo(e.id));
  }

  function fillForm() {
    const all = fields();
    const radios = {};
    let filled = 0;
    const needs = [];
    const seenNeeds = new Set();
    const need = (el, label, why) => { if (seenNeeds.has(label)) return; seenNeeds.add(label); needs.push({ el, label, why }); };

    all.forEach((el) => {
      const type = (el.type || "").toLowerCase();
      if (type === "radio") { (radios[el.name || "r" + radios.length] = radios[el.name] || []).push(el); return; }
      const label = labelOf(el);
      if (!label) return;
      const kind = classify(el, label);
      if (!kind) return;
      const ans = answerFor(kind);
      if (ans == null) { if (!(el.value && el.value.trim())) need(el, label, WHY[kind] || "Not found in your resume."); return; }
      if (el.tagName === "SELECT") { if (fillSelect(el, label, ans)) filled++; else if (!(el.selectedIndex > 0)) need(el, label, "No option matched your answer."); }
      else if (fillText(el, label, ans)) filled++;
    });

    Object.values(radios).forEach((group) => {
      const q = clean((group[0].closest("fieldset") && group[0].closest("fieldset").querySelector("legend") ? group[0].closest("fieldset").querySelector("legend").innerText : "") || labelOf(group[0].closest("div,li,fieldset") ? group[0].closest("div,li,fieldset").querySelector("label,legend,p") || group[0] : group[0]));
      const kind = classify(group[0], q);
      if (!kind) return;
      const ans = answerFor(kind);
      if (ans == null) { if (!group.some((r) => r.checked)) need(group[0], q, WHY[kind] || "Not found in your resume."); return; }
      if (fillRadio(group, q, ans)) filled++;
    });

    S.needs = needs;
    return filled;
  }

  async function answerQuestions() {
    const cand = fields().filter((el) => {
      if (!(el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && /^(text|)$/.test(el.type || "")))) return false;
      if (el.value && el.value.trim()) return false;
      const l = labelOf(el);
      return l.length > 24 && /\?|describe|why |tell us|explain|how many|what |how do|how would/i.test(l) && !classify(el, l);
    }).slice(0, 8);
    if (!cand.length) { S.message = "No open written questions found on this page."; return 0; }
    let done = 0;
    for (let i = 0; i < cand.length; i++) {
      S.status = `Answering ${i + 1} of ${cand.length}`;
      render();
      const label = labelOf(cand[i]);
      const r = await api("/api/extension/solve", "POST", { question: label });
      const ans = r.ok && r.data && (r.data.answer || r.data.text);
      if (ans) {
        const verdict = r.data.review && (r.data.review.verdict || r.data.review.status);
        if (fillText(cand[i], label, ans, { written: true, verdict: verdict || "" })) done++;
      } else {
        S.needs.push({ el: cand[i], label, why: r.offline ? r.error : "Your resume has no facts that answer this. Write it yourself." });
      }
    }
    return done;
  }

  /* ---------------------------------------------------------------- submit helpers */
  function findSubmit() {
    return Array.from(document.querySelectorAll("button, input[type=submit]")).find((b) => {
      if (host_el && host_el.contains(b) || !isVisible(b) || b.disabled) return false;
      const t = clean(b.innerText || b.value || b.getAttribute("aria-label")).toLowerCase();
      return /^(submit( application)?|send application)$/.test(t);
    });
  }
  function startCountdown() {
    const btn = findSubmit();
    if (!btn) return;
    S.countdown = true;
    render();
    timer = setTimeout(() => {
      S.countdown = false;
      render();
      try { btn.click(); } catch (e) { /* ignore */ }
    }, 10000);
  }
  function cancelCountdown() {
    clearTimeout(timer);
    S.countdown = false;
    render();
  }

  /* ---------------------------------------------------------------- tracking */
  const CONFIRM = /(thank you for applying|application (has been )?(submitted|received)|we('| ha)ve received your application|your application (was|has been) sent)/i;
  function watchSubmission() {
    if (S.watching) return;
    S.watching = true;
    document.addEventListener("submit", () => {
      if (!S.entries.length || S.applied) return;
      let n = 0;
      const iv = setInterval(() => {
        n++;
        if (CONFIRM.test(document.body ? document.body.innerText : "")) { clearInterval(iv); markApplied(true); }
        if (n > 20) clearInterval(iv);
      }, 1000);
    }, true);
  }
  async function markApplied(auto) {
    if (S.applied) return;
    const og = document.querySelector('meta[property="og:site_name"]');
    const r = await api("/api/extension/confirm-applied", "POST", { url: location.href, title: document.title, company: (og && og.content) || host, notes: "Marked applied from the JobHunter panel" + (auto ? " after a confirmation page" : "") });
    if (r.ok) { S.applied = true; S.message = "Tracked as Applied in JobHunter."; } else S.message = "Could not track it. " + (r.error || "");
    render();
  }

  /* ---------------------------------------------------------------- panel */
  function build() {
    if (host_el) return;
    host_el = document.createElement("div");
    host_el.setAttribute("data-jobhunter", "");
    host_el.style.cssText = "all:initial";
    shadow = host_el.attachShadow({ mode: "open" });
    shadow.innerHTML = `<style>${CSS}</style><div class="root">
      <button class="launcher" type="button" data-act="open" aria-label="Open JobHunter panel"><img class="logo" src="${LOGO}" alt="">JobHunter</button>
      <section class="panel" role="region" aria-label="JobHunter" hidden>
        <div class="head"><div class="grow"><img class="logo" src="${LOGO}" alt=""><strong>JobHunter</strong></div><button class="iconbtn" type="button" data-act="close" aria-label="Close panel">${svg("x")}</button></div>
        <div class="body" id="body" aria-live="polite"></div>
        <div class="foot"><span>Data stays on this computer.</span><a href="#" data-act="dash">Open JobHunter</a></div>
      </section></div>`;
    root = shadow.querySelector(".root");
    shadow.addEventListener("click", onClick);
    shadow.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.open) setOpen(false); });
    document.documentElement.appendChild(host_el);
  }

  function setOpen(v) {
    build();
    S.open = v;
    shadow.querySelector(".panel").hidden = !v;
    shadow.querySelector(".launcher").hidden = v || !launcherWanted;
    if (v) { if (S.stage === "idle" || S.stage === "offline") connect(); render(); const c = shadow.querySelector('[data-act="close"]'); if (c) c.focus(); }
    else { const l = shadow.querySelector(".launcher"); if (!l.hidden) l.focus(); }
  }

  async function connect() {
    S.stage = "connecting"; render();
    const r = await api("/api/extension/payload", "POST", { url: location.href });
    if (!r.ok) { S.stage = "offline"; S.message = r.error || ""; render(); return; }
    S.profile = (r.data && r.data.profile) || null;
    const pr = await api("/api/preferences");
    S.prefs = pr.ok && pr.data ? pr.data : {};
    S.stage = S.profile && S.profile.name ? "ready" : "noresume";
    render();
  }

  function who() {
    const p = S.profile || {};
    return `<div class="who"><span class="n" dir="auto">${esc(p.name || "")}</span><span class="r" dir="auto">${esc(p.target_title || "")}</span></div>`;
  }

  function render() {
    if (!shadow) return;
    const b = shadow.getElementById("body");
    if (!b) return;
    let h = "";
    if (S.stage === "connecting") h = `<div class="status">${svg("loader-circle", "spin")}Connecting to JobHunter</div>`;
    else if (S.stage === "offline") h = `<div class="notice bad"><strong>JobHunter is not running.</strong><span>Start it on this computer, then try again.</span></div><button class="btn secondary" data-act="retry" type="button">Try again</button>`;
    else if (S.stage === "noresume") h = `<div class="notice warn"><strong>No resume found.</strong><span>JobHunter fills forms only from your resume. Add one first.</span></div><button class="btn primary" data-act="resume" type="button">Add your resume</button>`;
    else {
      const n = fields().length;
      const busy = S.stage === "working";
      h += `<div class="state"><span class="dot"></span><span>Connected</span></div>${who()}`;
      h += `<div class="status" aria-live="polite">${busy ? svg("loader-circle", "spin") : ""}${busy ? esc(S.status || "Working") : `${n} ${n === 1 ? "field" : "fields"} on this page`}</div>`;
      if (platform === "linkedin") {
        h += `<div class="actions"><button class="btn secondary small" data-act="note" type="button">Connection note</button><button class="btn secondary small" data-act="inmail" type="button">Message</button></div>`;
      }
      if (n) {
        h += `<button class="btn primary" data-act="fill" type="button"${busy ? ' aria-busy="true"' : ""}>${svg("pen-line")}Fill this form</button>`;
        h += `<button class="btn secondary" data-act="questions" type="button"${busy ? ' aria-busy="true"' : ""}>Answer written questions</button>`;
      } else if (platform !== "linkedin") {
        h += `<div class="notice"><span>No form on this page yet. Open the application form, then press Fill.</span></div><button class="btn secondary" data-act="fill" type="button">Look again</button>`;
      }
      if (S.note) h += `<div><h2>${esc(S.note.kind)}<span class="count">${S.note.text.length}${S.note.max ? " of " + S.note.max : ""}</span></h2><div class="out" dir="auto">${esc(S.note.text)}</div><div class="actions" style="margin-top:8px"><button class="btn secondary small" data-act="copy" type="button">Copy</button>${S.note.insertable ? `<button class="btn secondary small" data-act="insert" type="button">Put in note box</button>` : ""}</div></div>`;
      if (S.countdown) h += `<div class="notice"><strong>Submitting in 10 seconds.</strong><div class="bar" aria-hidden="true"><i></i></div><button class="btn secondary small" data-act="cancel" type="button">Cancel</button></div>`;
      if (S.entries.length) {
        h += `<div><h2>Filled<span class="count">${S.entries.length}</span><button class="btn quiet" data-act="undoall" type="button">Undo all</button></h2><ul class="list">${S.entries.map((e) => `<li><div class="row"><span class="lbl">${esc(e.label)}</span><button class="btn quiet" data-undo="${e.id}" type="button" aria-label="Undo ${esc(e.label)}">Undo</button></div><span class="val" dir="auto"><mark>${esc(clip(e.shown, 140))}</mark></span>${e.written ? `<span class="why">Written from your resume. Read it before you submit.${e.verdict ? " Reviewer: " + esc(e.verdict) + "." : ""}</span>` : ""}</li>`).join("")}</ul></div>`;
      }
      if (S.needs.length) {
        h += `<div><h2>Needs you<span class="count">${S.needs.length}</span></h2><ul class="list">${S.needs.map((e, i) => `<li><div class="row"><span class="flag" dir="auto">${esc(clip(e.label, 90))}</span><button class="btn quiet" data-goto="${i}" type="button">Go to field</button></div><span class="why">${esc(e.why)}</span></li>`).join("")}</ul></div>`;
      }
      if (S.entries.length && !S.countdown) {
        h += S.applied ? "" : `<div class="notice"><span>Review the form, then submit it yourself.</span><button class="btn secondary small" data-act="applied" type="button">I submitted it. Track as Applied</button></div>`;
      }
      if (S.message) h += `<div class="notice ${S.applied ? "ok" : ""}" role="status">${esc(S.message)}</div>`;
    }
    b.innerHTML = h;
  }
  const clip = (t, n) => (String(t).length > n ? String(t).slice(0, n - 1) + "…" : String(t));

  async function onClick(e) {
    const t = e.target.closest("[data-act],[data-undo],[data-goto]");
    if (!t) return;
    if (t.tagName === "A") e.preventDefault();
    if (t.dataset.undo) return undo(t.dataset.undo);
    if (t.dataset.goto != null) {
      const n = S.needs[Number(t.dataset.goto)];
      if (n && n.el) { n.el.scrollIntoView({ block: "center", behavior: "smooth" }); n.el.focus({ preventScroll: true }); n.el.style.boxShadow = "0 0 0 2px #fff, 0 0 0 4px #b91c1c"; }
      return;
    }
    const a = t.dataset.act;
    if (a === "open") setOpen(true);
    else if (a === "close") setOpen(false);
    else if (a === "retry") connect();
    else if (a === "dash") window.open(DASHBOARD, "_blank", "noopener");
    else if (a === "resume") window.open(DASHBOARD + "/#/resume", "_blank", "noopener");
    else if (a === "undoall") undoAll();
    else if (a === "cancel") cancelCountdown();
    else if (a === "applied") markApplied(false);
    else if (a === "fill") await runFill(false);
    else if (a === "questions") await runFill(true);
    else if (a === "note") await outreach(true);
    else if (a === "inmail") await outreach(false);
    else if (a === "copy") { try { await navigator.clipboard.writeText(S.note.text); S.message = "Copied."; } catch (err) { S.message = "Copy failed."; } render(); }
    else if (a === "insert") insertNote();
  }

  async function runFill(questionsOnly) {
    if (S.stage === "working") return;
    S.stage = "working"; S.message = ""; S.status = questionsOnly ? "Reading the questions" : "Filling fields"; S.needs = questionsOnly ? S.needs : [];
    render();
    let n = 0;
    if (!questionsOnly) n += fillForm();
    if (questionsOnly) n += await answerQuestions();
    S.stage = "ready";
    S.status = "";
    if (!n && !S.needs.length && !S.message) S.message = "Nothing to fill. Empty fields that JobHunter knows how to answer were not found.";
    render();
    watchSubmission();
    if (!questionsOnly && S.prefs && S.prefs.submission_mode === "countdown" && n && !S.needs.length) startCountdown();
    else if (!questionsOnly && S.prefs && S.prefs.submission_mode === "countdown" && S.needs.length) { S.message = "Not submitting by itself, because " + S.needs.length + " answers need you."; render(); }
  }

  async function outreach(noteOnly) {
    const nameEl = document.querySelector("h1");
    const head = document.querySelector(".text-body-medium");
    S.status = "Writing from your resume"; S.stage = "working"; render();
    const r = await api("/api/extension/founder-outreach", "POST", { founder_name: nameEl ? clean(nameEl.innerText) : "", founder_headline: head ? clean(head.innerText) : "", company: location.pathname.split("/")[2] || "" });
    S.stage = "ready"; S.status = "";
    const d = r.ok && r.data;
    if (!d) S.message = r.error || "No message came back.";
    else if (noteOnly && d.connection_note) S.note = { kind: "Connection note", text: d.connection_note, max: 300, insertable: true };
    else if (d.inmail_body) S.note = { kind: "Message", text: d.inmail_body, insertable: false };
    else S.message = "No message came back.";
    render();
  }
  function insertNote() {
    const box = document.querySelector('textarea[name="message"], #custom-message, textarea');
    if (box && S.note) { setValue(box, S.note.text); S.message = "Added to the note box. Read it, then send."; }
    else S.message = "Open the Add a note box first, then press this again.";
    render();
  }

  /* ---------------------------------------------------------------- launcher gate */
  let launcherWanted = false;
  function evaluateGate() {
    const n = fields().length;
    const want = (platform === "linkedin" && /\/(in|jobs|company)\//.test(location.pathname)) || n >= 3;
    if (want && !launcherWanted) { launcherWanted = true; build(); if (!S.open) shadow.querySelector(".launcher").hidden = false; }
    return want;
  }

  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (msg && msg.type === "jh-ping") { reply({ platform, fields: fields().length, open: S.open }); return; }
    if (msg && msg.type === "jh-toggle") { launcherWanted = true; setOpen(msg.open === true ? true : !S.open); reply({ ok: true }); return; }
  });

  if (platform !== "page") {
    let tries = 0;
    evaluateGate();
    const iv = setInterval(() => { tries++; if (launcherWanted || tries > 15) clearInterval(iv); else evaluateGate(); }, 2000);
  }
})();
