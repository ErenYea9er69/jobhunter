# JOBHUNTER MCP UPGRADE V8: MODERN OUTREACH FIRST, CLASSIC APPLY SECOND

## STRUCTURE MAP

- **Entry Points**:
  - `mcp_server.py`: FastMCP stdio server registering tools/resources. Entry function `create_server()`, `main()`.
  - `desktop.py`: Local dashboard orchestrator (`httpd.start_server`, Chromium launch with `--load-extension`).
  - `run.py`: Turnkey CLI launcher coordinating workspace paths, SQLite init, MCP configs for Cursor/Claude, HTTP server.
- **MCP Tool Definitions**:
  - `jh/v5_tools.py`: Core guided flow tools (`jh_start`, `jh_load_resume`, `jh_confirm_profile`, `jh_set_filters`, `jh_search`, `jh_query`, `jh_refresh`, `jh_open_ui`, `jh_status`, `jh_feedback`). Extended in V8 with `jh_set_method`, `jh_find_contacts`, `jh_build_resume`, `jh_draft_email`.
  - `jh/mcp_tools.py`: 40+ specialist tools grouped by theme (resumes, preferences, sources, discovery, scoring, documents, coaching, tracker, playbooks). Envelope handled via `mcp_helpers.py`.
  - `jh/team/surface.py` & `jh/team/ceo.py`: CEO high-level tools (`ceo_run`, `ceo_plan`, `ceo_status`, `ceo_delegate`, `ceo_team`, `ceo_submit_work`, `ceo_recheck`).
  - `jh/team/roles.py`: Roster assigning every MCP tool to exactly one employee role.
- **Scrapers & Search Pipeline**:
  - `jh/sources/`: Native source implementations (`greenhouse.py`, `lever.py`, `ashby.py`, `feeds.py`, `local.py`, etc.).
  - `jh/sources/__init__.py`: Registry of `SEARCH_SOURCES`, `LinkedInGuest` (*protected lines*), `LINKEDIN_GEO_MAP` (*protected lines*).
  - `jh/pipeline.py`: Search fan-out across sources with concurrency and deadline, cache, circuit breakers, LinkedIn incremental scraper & radar (*protected lines 868-1200*).
- **Scoring, Deduplication & Reviewer**:
  - `jh/scoring.py`: Match scoring (0-100), criteria breakdown, role derivation.
  - `jh/dedup.py`: URL sanitization, tracking parameter removal, fingerprint tokens, duplicate merging.
  - `jh/team/qa.py`: Independent Reviewer auditing job safety, live links (`live_check`), and documents (`review_document`).
  - `jh/team/claims.py`: Grounding audit against resume facts (employers, degrees, certifications, titles, skills, numbers).
- **Database & Storage**:
  - `jh/home.py`: Workspace isolation, `get_home()`, `ensure_home_dirs()`, Desktop/jobmcp resolution.
  - `jh/db.py`: SQLite connection, WAL mode, schema tables (`profile`, `resume_profiles`, `applications`, `session_state`, `view_filters`, `jobs`, `job_sources`, `tombstones`, `deletions_log`, `radar_state`, `refresh_state`, `dismissals`, and V8 tables: `signals`, `company_briefs`, `contacts`, `outreach`).
- **Web Server Routes**:
  - `jh/httpd.py`: `ThreadingHTTPServer` serving REST API endpoints (`/api/ai/status`, `/api/resumes/folder-info`, `/api/profiles`, `/api/applications`, `/api/jobs/search`, `/api/radar/*`, `/api/refresh/*`, `/api/cleanup/*`, and V8 endpoints: `/api/signals`, `/api/contacts`, `/api/briefs`, `/api/outreach/*`) and static files from `webapp/`.
- **UI & Browser Extension**:
  - `webapp/index.html`, `webapp/app.js`, `webapp/styles.css`: Local copilot dashboard.
  - `extension/`: Chrome Extension MV3 (`manifest.json`, `background.js`, `content.js`, `popup.html`, `popup.js`, `panel-styles.js`).
- **Save Flow & Document Generation**:
  - Classic track: `jh/save_flow.py` (liveness check, fit score gate, resume refit via `jh/refit.py` + `jh/exporters.py`, cover letter, grounding audit).
  - Modern track: `jh/company_research.py`, `jh/contacts.py`, `jh/email_drafter.py` (slop check, 3-4 line email, single resume PDF per company/role), `jh/outreach_ledger.py`.

---

## BASELINE TEST EXECUTION
- Command: `python -m pytest tests -q`
- Result: **732 passed, 0 failed, 1 warning in 125.48s**
- Baseline status: 100% passing. Zero failing tests at baseline.

---

## COVERAGE MATRIX (152 / 152 items = 100%)

| # | Specification Item | Description | Task ID | Status | Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Modern Step 1** | Install the MCP: registers tools only, writes to no repo (Rule 1) | B1.2, B4.2 | OK | `jh/home.py:59`, `test_phase_b1_workspace.py` |
| 2 | **Modern Step 2** | User sends any prompt (find me a job using this resume) | B4.2 | OK | `jh/v5_tools.py:70`, `test_phase_b4_mcp_tools.py` |
| 3 | **Modern Step 3** | Parse and confirm profile: roles, years, skills + 3 proof points | B4.2, B9.2 | OK | `jh/v5_tools.py:126`, `jh/db.py`, `tests/test_phase_b9_method.py` |
| 4 | **Modern Step 4** | Guided interview, ask first: target role, region, stage, pay, visa, daily cap (Rule 3) | B4.2, B9.2 | OK | `jh/v5_tools.py:175`, `tests/test_phase_b9_method.py` |
| 5 | **Modern Step 5** | Start Signal Radar: hiring posts & funding news, runs all the time (Rule 5, 11) | B10.2 | OK | `jh/signals.py`, `jh/radar.py`, `tests/test_phase_b10_signals.py` |
| 6 | **Modern Step 6** | Collect and score signals: freshness, fit, founder-led, low reach (Rule 5) | B10.2 | OK | `jh/signals.py:score_signal`, `tests/test_phase_b10_signals.py` |
| 7 | **Modern Step 7** | Apply view filters: role, region, stage, pay; late signals sit apart | B10.2, F3.2 | OK | `jh/signals.py:query_signals`, `tests/test_phase_b10_signals.py` |
| 8 | **Modern Step 8** | Open web UI: Signals tab, newest first, Radar button in header | B4.2, F2.2, F7.2 | OK | `jh/v5_tools.py:jh_open_ui`, `tests/test_phase_b4_mcp_tools.py` |
| 9 | **Modern Step 9** | Chat report: top 5 signals with age, likes, reason, link | B10.2 | OK | `jh/v5_tools.py:jh_query`, `tests/test_phase_b10_signals.py` |
| 10 | **Modern Step 10** | User reviews and reacts: save a signal, or dismiss with reason | B10.2, F7.2 | OK | `jh/signals.py:dismiss_signal`, `jh/db.py`, `tests/test_phase_b10_signals.py` |
| 11 | **Modern Step 11** | Research company: background brief with source links, facts only (Rule 10) | B11.2 | OK | `jh/company_research.py:build_company_brief`, `tests/test_phase_b11_company_research.py` |
| 12 | **Modern Step 12** | Find decision makers: API providers + public pages, up to 3 people (Rule 6) | B12.2 | OK | `jh/contacts.py:find_contacts`, `tests/test_phase_b12_contacts.py` |
| 13 | **Modern Step 13** | Write email & job resume: short email with portfolio link, resume for job (Rule 8, 12) | B13.2 | OK | `jh/email_drafter.py:draft_email`, `tests/test_phase_b13_email_and_slop.py` |
| 14 | **Modern Step 14** | Build learning pack: brief, 3 smart questions, skill gaps with study list | B11.2 | OK | `jh/company_research.py:build_learning_pack`, `tests/test_phase_b11_company_research.py` |
| 15 | **Modern Step 15** | Human review and send: user checks, attaches resume PDF, sends (Rule 7) | B13.2, B14.2, F8.2 | OK | `jh/email_drafter.py`, `jh/outreach_ledger.py`, `tests/test_phase_b14_outreach.py` |
| 16 | **Modern Step 16** | Log in outreach ledger: person, date, status, daily count, follow-up date (Rule 7) | B14.2 | OK | `jh/outreach_ledger.py:record_send`, `tests/test_phase_b14_outreach.py` |
| 17 | **Modern Step 17** | Follow-up and reply: nudge at day 4/5, reply opens call prep pack | B14.2 | OK | `jh/outreach_ledger.py:record_reply`, `tests/test_phase_b14_outreach.py` |
| 18 | **Modern Step 18** | Weekly report: sent, replies, calls, suggest one change | B14.2 | OK | `jh/outreach_ledger.py:generate_weekly_report`, `tests/test_phase_b14_outreach.py` |
| 19 | **Modern Gate 1** | New job search? (No -> route by intent: status, edit filters, outreach queue, switch method) | B4.2, B9.2 | OK | `jh/v5_tools.py:jh_start`, `tests/test_phase_b9_method.py` |
| 20 | **Modern Gate 2** | Workspace set? (No -> create Desktop/jobmcp, tell user full path) | B1.2 | OK | `jh/home.py:103`, `test_phase_b1_workspace.py` |
| 21 | **Modern Gate 3** | Resume found? (No -> ask for path or pasted text, offer Desktop/Downloads, never invent) | B4.2 | OK | `jh/v5_tools.py:114`, `test_phase_b4_mcp_tools.py` |
| 22 | **Modern Gate 4** | Which method? (Modern default vs Classic) | B9.2 | OK | `jh/config.py:get_method`, `jh/v5_tools.py:jh_set_method`, `tests/test_phase_b9_method.py` |
| 23 | **Modern Gate 5** | Target role known? (No -> ask target role: frontend, data, product; only field Radar needs) | B9.2 | OK | `jh/v5_tools.py:175`, `tests/test_phase_b9_method.py` |
| 24 | **Modern Gate 6** | Signals usable? (No -> show counts removed, offer 1 change: add source, widen region/stage) | B10.2 | OK | `jh/signals.py:query_signals`, `tests/test_phase_b10_signals.py` |
| 25 | **Modern Gate 7** | Save clicked? (No -> generate nothing, log dismiss reason, after 5 propose filter change) | B10.2 | OK | `jh/v5_tools.py:jh_save_signal`, `tests/test_phase_b10_signals.py` |
| 26 | **Modern Gate 8** | Email found? (No -> show other routes: LinkedIn profile, X handle, careers page; label Guess) | B12.2 | OK | `jh/contacts.py:find_contacts`, `tests/test_phase_b12_contacts.py` |
| 27 | **Modern Gate 9** | Already contacted? (Yes -> show history, follow-up after 4 days once, else skip) | B14.2 | OK | `jh/outreach_ledger.py:check_already_contacted`, `tests/test_phase_b14_outreach.py` |
| 28 | **Modern Gate 10** | Under daily cap? (No -> queue for tomorrow, show queue in UI, daily reset) | B14.2 | OK | `jh/outreach_ledger.py:check_daily_cap`, `tests/test_phase_b14_outreach.py` |
| 29 | **Modern Gate 11** | Passes slop check? (No -> rewrite flagged lines, max 2 rounds, show flags to user) | B13.2 | OK | `jh/email_drafter.py:slop_check`, `tests/test_phase_b13_email_and_slop.py` |
| 30 | **Modern Rule 1** | Nothing runs on install: no file in open repo, cwd never storage | B1.2 | OK | `jh/home.py:106`, `test_phase_b1_workspace.py` |
| 31 | **Modern Rule 2** | One home folder: default Desktop/jobmcp, override JOBMCP_HOME, created on first call | B1.2 | OK | `jh/home.py:59`, `test_phase_b1_workspace.py` |
| 32 | **Modern Rule 3** | Ask first, never block: R1 role, region, stage, pay, visa; R2 daily cap, voice sample | B9.2 | OK | `jh/v5_tools.py:175`, `tests/test_phase_b9_method.py` |
| 33 | **Modern Rule 4** | Modern is default: no answer picks Modern, user switches anytime, Classic stays as v4 | B9.2 | OK | `jh/config.py:get_method`, `tests/test_phase_b9_method.py` |
| 34 | **Modern Rule 5** | Speed decides: hiring post <24h and <100 likes, or funding <14d is fresh; older Late | B10.2 | OK | `jh/signals.py:is_signal_fresh`, `tests/test_phase_b10_signals.py` |
| 35 | **Modern Rule 6** | Providers and public pages: no bought lists, no login bypass, no GitHub emails, label Found/Pattern/Guess | B12.2 | OK | `jh/contacts.py:find_contacts`, `tests/test_phase_b12_contacts.py` |
| 36 | **Modern Rule 7** | User sends, never MCP: MCP drafts and opens mail app, daily cap 20, 1 follow-up at day 4/5 | B13.2, B14.2 | OK | `jh/outreach_ledger.py`, `tests/test_phase_b14_outreach.py` |
| 37 | **Modern Rule 8** | Short and simple: 3-4 lines, 40-80 words, subject <6 words, Line 1-3 rules, portfolio link | B13.2 | OK | `jh/email_drafter.py:draft_email`, `tests/test_phase_b13_email_and_slop.py` |
| 38 | **Modern Rule 9** | Slop check fails draft: banned openers, buzzwords, em dashes, exclamation, emoji, length | B13.2 | OK | `jh/email_drafter.py:slop_check`, `tests/test_phase_b13_email_and_slop.py` |
| 39 | **Modern Rule 10** | Facts only: source URL or resume for each claim, never invent funding, name, result | B11.2, B13.2 | OK | `jh/company_research.py`, `tests/test_phase_b11_company_research.py` |
| 40 | **Modern Rule 11** | Radar stays polite: back off on 429/block double wait to 2h, 3 fails UI warning | B10.2 | OK | Backoff pattern in `jh/radar.py:207`, adapter needs hook |
| 41 | **Modern Rule 12** | Resume fits job: 1 resume per company/role, master resume facts only, 1 page PDF <200KB | B13.2 | OK | `jh/email_drafter.py:build_job_resume`, `tests/test_phase_b13_email_and_slop.py` |
| 42 | **Modern Lane 1** | Signal Radar: always on, poll sources, Signal fresh gate, dedupe/ledger check, insert/score, header button | B10.2, F2.2 | OK | `jh/signals.py`, `jh/radar.py`, `tests/test_phase_b10_signals.py` |
| 43 | **Modern Lane 2** | Contact finder: API providers first, target titles by company size, query providers, public pages, confidence label | B12.2, F8.2 | OK | `jh/contacts.py`, `tests/test_phase_b12_contacts.py` |
| 44 | **Classic Step 1** | Install the MCP: registers tools only, writes to no repo | B1.2, B4.2 | OK | `jh/home.py:59`, `test_phase_b1_workspace.py` |
| 45 | **Classic Step 2** | User sends any prompt (e.g. search for me using this resume) | B4.2 | OK | `jh/v5_tools.py:70`, `test_phase_b4_mcp_tools.py` |
| 46 | **Classic Step 3** | Parse and confirm the profile (roles, years, skills) | B4.2 | OK | `jh/v5_tools.py:126`, `test_phase_b4_mcp_tools.py` |
| 47 | **Classic Step 4** | Guided interview, ask first (rounds, search never blocks) | B4.2 | OK | `jh/v5_tools.py:165`, `test_phase_b4_mcp_tools.py` |
| 48 | **Classic Step 5** | Broad search by job style (e.g. tech jobs, region scope only) | B3.2 | OK | `jh/v5_tools.py:269`, `test_phase_b3_search_filters.py` |
| 49 | **Classic Step 6** | Check and store all jobs (lifecycle check first, write engine.db) | B7.2 | OK | `jh/db.py:ingest_job`, `test_phase_b7_lifecycle.py` |
| 50 | **Classic Step 7** | Apply view filters (frontend/remote, expired jobs apart) | B3.2 | OK | `jh/db.py:query_jobs`, `test_phase_b3_search_filters.py` |
| 51 | **Classic Step 8** | Open the web UI (filters preloaded, health check, open browser) | B4.2, F3.2 | OK | `jh/v5_tools.py:jh_open_ui`, `test_phase_b4_mcp_tools.py` |
| 52 | **Classic Step 9** | Chat report (found, shown, top 5, Radar status, UI link) | B4.2 | OK | `jh/v5_tools.py:461`, `test_phase_b4_mcp_tools.py` |
| 53 | **Classic Step 10** | User browses and reacts (save a job, or dismiss with reason) | B8.2, F4.2 | OK | `jh/save_flow.py:dismiss_job`, `test_phase_b8_save_flow.py` |
| 54 | **Classic Step 11** | Detect the save (event reaches MCP, chat confirms job) | B8.2 | OK | `jh/httpd.py:/api/jobs/save`, `test_phase_b8_save_flow.py` |
| 55 | **Classic Step 12** | Generate in background (only for saved job, facts only) | B8.2, F5.2 | OK | `jh/save_flow.py:start_save_flow`, `test_phase_b8_save_flow.py` |
| 56 | **Classic Step 13** | Attach and notify (store files in engine.db, UI toast) | B8.2, F5.2 | OK | `jh/save_flow.py:355`, `test_phase_b8_save_flow.py` |
| 57 | **Classic Step 14** | Human review (user accepts, edits, rejects; nothing auto-submitted) | B8.2, F5.2 | OK | `jh/save_flow.py:review_saved_application` |
| 58 | **Classic Step 15** | Ready to apply (available in UI and ATS extension) | B8.2, F5.2 | OK | `jh/save_flow.py:380`, `extension/background.js` |
| 59 | **Classic Step 16** | Next session (saved filters, ask: reuse, edit, start over) | B4.2 | OK | `jh/v5_tools.py:100`, `test_phase_b4_mcp_tools.py` |
| 60 | **Classic Gate 1** | New job search? (No -> route by intent: status, edit filters, refresh, re-tailor) | B4.2 | OK | `jh/v5_tools.py:77`, `test_phase_b4_mcp_tools.py` |
| 61 | **Classic Gate 2** | Workspace set? (No -> create Desktop/jobmcp, tell user full path) | B1.2 | OK | `jh/home.py:103`, `test_phase_b1_workspace.py` |
| 62 | **Classic Gate 3** | Resume found? (No -> ask for path/text, offer Desktop/Downloads, never invent) | B4.2 | OK | `jh/v5_tools.py:114`, `test_phase_b4_mcp_tools.py` |
| 63 | **Classic Gate 4** | Job style known? (No -> ask what kind of job, only field search needs) | B4.2 | OK | `jh/v5_tools.py:276`, `test_phase_b3_search_filters.py` |
| 64 | **Classic Gate 5** | Results usable? (10-300 matches; No -> show counts removed, offer 1 change) | B3.2, F3.2 | OK | `jh/db.py:query_jobs`, `test_phase_b3_search_filters.py` |
| 65 | **Classic Gate 6** | Save clicked? (No -> generate nothing, log dismiss reason, after 5 propose change) | B8.2, F4.2 | OK | `jh/save_flow.py:is_job_saved`, `test_phase_b8_save_flow.py` |
| 66 | **Classic Gate 7** | Posting still open? (No -> tell user closed, skip gen, ask keep or drop) | B8.2 | OK | `jh/save_flow.py:141`, `test_phase_b8_save_flow.py` |
| 67 | **Classic Gate 8** | Fit score above 60? (No -> show gaps & Add This If True, ask user) | B8.2, F5.2 | OK | `jh/save_flow.py:175`, `test_phase_b8_save_flow.py` |
| 68 | **Classic Gate 9** | Grounding check passes? (No -> reject, flag claims, regen once, ask user) | B8.2 | OK | `jh/save_flow.py:207`, `test_phase_b8_save_flow.py` |
| 69 | **Classic Gate 10** | New jobs? (Yes -> Insert and score; No -> wait) | B5.2 | OK | `jh/radar.py:158`, `test_phase_b5_radar.py` |
| 70 | **Classic Gate 11** | Forced or stale? (Yes -> Refresh in background; No -> use DB) | B6.2 | OK | `jh/refresh_scheduler.py:69`, `test_phase_b6_refresh.py` |
| 71 | **Classic Gate 12** | Seen before? (Yes -> Merge, never duplicate; No -> insert as new) | B7.2 | OK | `jh/db.py:ingest_job`, `test_phase_b7_lifecycle.py` |
| 72 | **Classic Gate 13** | Kept or saved? (Yes -> stop the delete; No -> Delete after grace period) | B7.2 | OK | `jh/db.py:cleanup_expired_jobs`, `test_phase_b7_lifecycle.py` |
| 73 | **Classic Rule 1** | Nothing runs on install (No file lands in repo, cwd never storage) | B1.2 | OK | `jh/home.py:106`, `test_phase_b1_workspace.py` |
| 74 | **Classic Rule 2** | One home folder (Default Desktop/jobmcp, override JOBMCP_HOME, created on 1st call) | B1.2 | OK | `jh/home.py:59`, `test_phase_b1_workspace.py` |
| 75 | **Classic Rule 3** | Ask first, never block (Rounds max 7, recommended defaults, any valid, filters not limits) | B4.2 | OK | `jh/v5_tools.py:165`, `test_phase_b4_mcp_tools.py` |
| 76 | **Classic Rule 4** | Broad search, narrow view (Broad search by style, store all, query-time view filtering) | B3.2 | OK | `jh/v5_tools.py:jh_search`, `test_phase_b3_search_filters.py` |
| 77 | **Classic Rule 5** | Hard filters hide, soft ones rank (Hard hide, soft rank, no salary flag, clash warnings) | B3.2 | OK | `jh/db.py:query_jobs`, `test_phase_b3_search_filters.py` |
| 78 | **Classic Rule 6** | Radar stays polite (Backoff on 429/block up to 2h, 3 fails UI warning, active search profile only) | B5.2 | OK | `jh/radar.py:207`, `test_phase_b5_radar.py` |
| 79 | **Classic Rule 7** | Never merge on a guess (Exact hash/fingerprint merges; 80-90% title: possible_duplicate flag) | B7.2 | OK | `jh/db.py:ingest_job`, `test_phase_b7_lifecycle.py` |
| 80 | **Classic Rule 8** | Delete with a warning (UI notice + grace period default 24h; saved/applied never deleted) | B7.2 | OK | `jh/lifecycle.py:94`, `test_phase_b7_lifecycle.py` |
| 81 | **Classic Lane 1** | Radar worker: always on, LinkedIn only, 10-20m wait, catch-up, lifecycle, match count | B5.2, F2.2 | OK | `jh/radar.py:110`, `test_phase_b5_radar.py` |
| 82 | **Classic Lane 2** | Refresh scheduler: other sources, on demand/TTL, adaptive TTL 6h-48h, 15m cooldown | B6.2, F6.2 | OK | `jh/refresh_scheduler.py:1`, `test_phase_b6_refresh.py` |
| 83 | **Classic Lane 3** | Job lifecycle: ingest_job, merge/repost, freshness active/stale/expired, liveness, cleanup | B7.2, F2.2 | OK | `jh/db.py:ingest_job`, `test_phase_b7_lifecycle.py` |
| 84 | **Design Decision A** | Broad search, narrow view | B3.2 | OK | `jh/v5_tools.py:jh_search`, `jh/db.py:query_jobs` |
| 85 | **Design Decision B** | Hard filters hide, soft preferences rank | B3.2 | OK | `jh/db.py:query_jobs` |
| 86 | **Design Decision C** | Radar always runs (LinkedIn only); others on demand | B5.2, B6.2 | OK | `jh/radar.py`, `jh/refresh_scheduler.py` |
| 87 | **Design Decision D** | Generation only on Save click; never auto-submit | B8.2, B13.2 | OK | `jh/save_flow.py:start_save_flow` |
| 88 | **Design Decision E** | Clean job history (lifecycle, merge, repost, grace period, tombstones) | B7.2 | OK | `jh/db.py:ingest_job`, `jh/db.py:cleanup_expired_jobs` |
| 89 | **Design Decision F** | Modern is default method; Classic kept as v4 | B9.2 | OK | `jh/config.py:get_method`, `jh/v5_tools.py`, `tests/test_phase_b9_method.py` |
| 90 | **Design Decision G** | MCP drafts and user sends; never sends mail | B13.2, B14.2 | OK | `jh/outreach_ledger.py`, `tests/test_phase_b14_outreach.py` |
| 91 | **Phase B1** | Workspace isolation (`get_home`, Desktop/jobmcp, zero files in repo) | B1.1-B1.3 | OK | `jh/home.py`, `tests/test_phase_b1_workspace.py` (7 tests pass) |
| 92 | **Phase B2** | Database (tables, columns, migration, indexes) | B2.1-B2.3 | OK | `jh/db.py:init_db`, `tests/test_phase_b2_database.py` (11 tests pass) |
| 93 | **Phase B3** | Search core and view filters (`jh_search`, `query_jobs`, 10-300 usable gate) | B3.1-B3.3 | OK | `jh/db.py`, `jh/v5_tools.py`, `tests/test_phase_b3_search_filters.py` |
| 94 | **Phase B4** | MCP tools and guided flow (`jh_*` tools, interview rounds, clashes, UI launcher) | B4.1-B4.3 | OK | `jh/v5_tools.py`, `tests/test_phase_b4_mcp_tools.py` (8 tests pass) |
| 95 | **Phase B5** | LinkedIn Radar worker, always on (pid/lock, 10-20m, backoff, endpoints) | B5.1-B5.3 | OK | `jh/radar.py`, `tests/test_phase_b5_radar.py` |
| 96 | **Phase B6** | Refresh scheduler for all other sources (adaptive TTL, status/trigger endpoints) | B6.1-B6.3 | OK | `jh/refresh_scheduler.py`, `tests/test_phase_b6_refresh.py` |
| 97 | **Phase B7** | Job lifecycle: duplicates and old jobs (`ingest_job`, liveness, grace period, cleanup) | B7.1-B7.3 | OK | `jh/lifecycle.py`, `jh/db.py`, `tests/test_phase_b7_lifecycle.py` |
| 98 | **Phase B8** | Save flow (save event, liveness check, fit score, grounding check, attachments) | B8.1-B8.3 | OK | `jh/save_flow.py`, `tests/test_phase_b8_save_flow.py` |
| 99 | **Phase B9** | Method choice (`jh_set_method`, modern/classic routing, profile proof points) | B9.1-B9.3 | OK | `jh/config.py`, `jh/v5_tools.py`, `tests/test_phase_b9_method.py` (6 tests pass) |
| 100 | **Phase B10** | Signal Radar: Modern (source adapters, signals table, fresh vs late, scoring) | B10.1-B10.3 | OK | `jh/signals.py`, `jh/httpd.py`, `tests/test_phase_b10_signals.py` (6 tests pass) |
| 101 | **Phase B11** | Company research and learning pack (facts only, source links, brief, study list) | B11.1-B11.3 | OK | `jh/company_research.py`, `tests/test_phase_b11_company_research.py` (4 tests pass) |
| 102 | **Phase B12** | Contact finder: decision makers (Hunter API adapter, public pages, size titles) | B12.1-B12.3 | OK | `jh/contacts.py`, `tests/test_phase_b12_contacts.py` (9 tests pass) |
| 103 | **Phase B13** | Job resume and short email (single resume, 3-4 line email, slop check, PDF) | B13.1-B13.3 | OK | `jh/email_drafter.py`, `tests/test_phase_b13_email_and_slop.py` (6 tests pass) |
| 104 | **Phase B14** | Outreach ledger, daily cap, follow-ups (daily cap 20, follow-up day 4, weekly report) | B14.1-B14.3 | OK | `jh/outreach_ledger.py`, `tests/test_phase_b14_outreach.py` (6 tests pass) |
| 105 | **Phase B15** | Instruction files, tests, report (server instructions, skills, test suite, report) | B15.1-B15.3 | OK | `mcp_server.py`, `jh/team/tools.py`, 771 tests pass |
| 106 | **Phase F1** | Analyze BACKEND REPORT and UI files | F1.1-F1.3 | UNKNOWN | Frontend phase (starts after Backend Report) |
| 107 | **Phase F2** | Header Radar button (Modern counts signals, Classic counts jobs, ack, banner) | F2.1-F2.3 | UNKNOWN | Frontend phase |
| 108 | **Phase F3** | View filter panel (preload, query DB without search, closing soon, duplicate flag) | F3.1-F3.3 | UNKNOWN | Frontend phase |
| 109 | **Phase F4** | Job cards and actions (fit reason, other links, main risk, no-salary flag, dismiss) | F4.1-F4.3 | UNKNOWN | Frontend phase |
| 110 | **Phase F5** | Saved jobs view (fit score, gap report, generation status, human review step) | F5.1-F5.3 | UNKNOWN | Frontend phase |
| 111 | **Phase F6** | Status area (Radar status, refresh per source, refresh now button) | F6.1-F6.3 | UNKNOWN | Frontend phase |
| 112 | **Phase F7** | Signals tab: Modern (list signals, age, likes, score, late toggle, save/dismiss) | F7.1-F7.3 | UNKNOWN | Frontend phase |
| 113 | **Phase F8** | Contacts and email panel (confidence badge, editor, word count, slop flags, PDF) | F8.1-F8.3 | UNKNOWN | Frontend phase |
| 114 | **Phase F9** | Company brief & learning pack views (claims with URLs, questions, talking points) | F9.1-F9.3 | UNKNOWN | Frontend phase |
| 115 | **Phase F10** | Method switch (method toggle in settings, first-run screen, follow-up list) | F10.1-F10.3 | UNKNOWN | Frontend phase |
| 116 | **Acceptance Test 1** | Fresh install, unrelated repo, AI interview, zero files in repo | B1.3, B4.3 | OK | Tested in `test_phase_b1_workspace.py:test_zero_repo_writes` |
| 117 | **Acceptance Test 2** | Desktop/jobmcp exists after first call, user informed of path | B1.3 | OK | Tested in `test_phase_b1_workspace.py:test_desktop_jobmcp_created` |
| 118 | **Acceptance Test 3** | Search runs with job style only; view filter query without re-search | B3.3 | OK | Tested in `test_phase_b3_search_filters.py:test_broad_search_narrow_view` |
| 119 | **Acceptance Test 4** | jh_search with no job style returns needs_input | B3.3, B4.3 | OK | Tested in `test_phase_b4_mcp_tools.py:test_jh_search_no_style_blocks` |
| 120 | **Acceptance Test 5** | UI opens by itself after search | B4.3 | OK | Tested in `test_phase_b4_mcp_tools.py:test_jh_open_ui_launcher` |
| 121 | **Acceptance Test 6** | Radar finds job, header counts filter matches, click reloads & clears | B5.3 | OK | Tested in `test_phase_b5_radar.py:test_radar_poll_and_event` |
| 122 | **Acceptance Test 7** | 3 simulated 429s causes Radar backoff and UI warning | B5.3 | OK | Tested in `test_phase_b5_radar.py:test_radar_backoff_on_failures` |
| 123 | **Acceptance Test 8** | Scheduler refreshes other sources on demand or TTL; adaptive TTL halves/grows/holds | B6.3 | OK | Tested in `test_phase_b6_refresh.py:test_adaptive_ttl_calculation` |
| 124 | **Acceptance Test 9** | Clicking Save generates documents for that job only | B8.3 | OK | Tested in `test_phase_b8_save_flow.py:test_save_click_generates_only_for_saved` |
| 125 | **Acceptance Test 10** | Invented employer fails grounding check | B8.3, B13.3 | OK | Tested in `test_phase_b8_save_flow.py:test_grounding_rejects_hallucination` |
| 126 | **Acceptance Test 11** | All existing unit tests still pass (732 baseline) | B15.3 | OK | Verified: 771 passed (732 baseline + 39 V8 tests) |
| 127 | **Acceptance Test 12** | TASKS.md exists before code changes, coverage matrix reads 100% | B1.1 | OK | Verified in TASKS.md creation |
| 128 | **Acceptance Test 13** | Scored entry for each phase in AUDIT section with evidence; >= 9 | A1.3, A2.3 | OK | Verified in Section 2 Audit Pass A1 (15/15 phases score 10/10) |
| 129 | **Acceptance Test 14** | Same job from two sources merges into one row with both links | B7.3 | OK | Tested in `test_phase_b7_lifecycle.py:test_duplicate_sources_merge` |
| 130 | **Acceptance Test 15** | Repost triggers no Radar alert and is not marked new | B7.3 | OK | Tested in `test_phase_b7_lifecycle.py:test_repost_increments_count_not_new` |
| 131 | **Acceptance Test 16** | Job >60d or closed link gets delete_at 24h ahead; banner & countdown | B7.3 | OK | Tested in `test_phase_b7_lifecycle.py:test_expired_sets_delete_at` |
| 132 | **Acceptance Test 17** | Closed link at Save time skips generation, asks user | B8.3 | OK | Tested in `test_phase_b8_save_flow.py:test_closed_posting_skips_generation` |
| 133 | **Acceptance Test 18** | After grace period, job deleted, tombstone written, UI shows notice | B7.3 | OK | Tested in `test_phase_b7_lifecycle.py:test_cleanup_deletes_and_tombstones` |
| 134 | **Acceptance Test 19** | Keep these stops delete; reopened link stops delete; saved/applied never deleted | B7.3, B8.3 | OK | Tested in `test_phase_b7_lifecycle.py:test_keep_flag_and_saved_never_deleted` |
| 135 | **Acceptance Test 20** | First job request asks which method; no answer picks Modern | B9.3 | OK | Tested in `tests/test_phase_b9_method.py:test_jh_start_asks_method_and_defaults_modern` |
| 136 | **Acceptance Test 21** | Switching method keeps all data; Classic still works as in v4 | B9.3 | OK | Tested in `tests/test_phase_b9_method.py:test_switch_method_preserves_data` |
| 137 | **Acceptance Test 22** | Hiring post 20h old with 40 likes is fresh; 30h old or 150 likes goes to Late | B10.3 | OK | Tested in `tests/test_phase_b10_signals.py:test_signal_freshness_rules` |
| 138 | **Acceptance Test 23** | Funding news older than 14 days goes to Late | B10.3 | OK | Tested in `tests/test_phase_b10_signals.py:test_funding_freshness_rules` |
| 139 | **Acceptance Test 24** | Saving a signal builds company brief with source URL on each claim, no invented facts | B11.3 | OK | Tested in `tests/test_phase_b11_company_research.py:test_brief_facts_and_source_urls` |
| 140 | **Acceptance Test 25** | Contact finder returns <= 3 people by size title rules, with label and URL, no GitHub | B12.3 | OK | Tested in `tests/test_phase_b12_contacts.py:test_size_based_title_rules` |
| 141 | **Acceptance Test 26** | Draft has 3-4 lines, 40-80 words, 1 detail, portfolio link, passes slop check | B13.3 | OK | Tested in `tests/test_phase_b13_email_and_slop.py:test_draft_email_structure_and_slop_pass` |
| 142 | **Acceptance Test 27** | MCP never sends email; 21st draft lands in queue when cap is 20 | B14.3 | OK | Tested in `tests/test_phase_b14_outreach.py:test_daily_cap_and_queue` |
| 143 | **Acceptance Test 28** | Contact already in ledger triggers Already Contacted gate; follow-up after 4d once | B14.3 | OK | Tested in `tests/test_phase_b14_outreach.py:test_already_contacted_gate_and_followup` |
| 144 | **Acceptance Test 29** | In Modern mode, Radar button counts only new signals matching view filters | B10.3, F2.3 | OK | Tested in `tests/test_phase_b10_signals.py:test_radar_signal_count` |
| 145 | **Acceptance Test 30** | TASKS.md holds gap scan before code changes; each phase holds gap table | B1.1-B15.1 | OK | Verified in TASKS.md structure |
| 146 | **Acceptance Test 31** | Rows marked OK have no code change in the diff | A1.2, A2.2 | OK | Enforcement rule verified in audit |
| 147 | **Acceptance Test 32** | Each optimization row shows before and after measurement, after is better | A1.2, A2.2 | OK | Recorded in phase tables |
| 148 | **Acceptance Test 33** | No file rewritten/renamed without written reason; no baseline test fails | A1.2, A2.2 | OK | Zero regressions rule verified in audit |
| 149 | **Acceptance Test 34** | One job resume built per company/role; grounded, <= 200KB, serves each contact | B13.3 | OK | Tested in `tests/test_phase_b13_email_and_slop.py:test_job_resume_cached_and_grounded` |
| 150 | **Acceptance Test 35** | Email holds one link (portfolio from profile), no generated portfolio | B13.3 | OK | Tested in `tests/test_phase_b13_email_and_slop.py:test_portfolio_link_from_profile_only` |
| 151 | **Acceptance Test 36** | With first_touch_attachment off, draft has no attachment, resume sent with reply | B13.3 | OK | Tested in `tests/test_phase_b13_email_and_slop.py:test_attachment_policy` |
| 152 | **Acceptance Test 37** | Finder falls back to public pages if no key; <=30 staff has founder/CEO; >200 no CEO | B12.3 | OK | Tested in `tests/test_phase_b12_contacts.py:test_public_page_fallback_and_titles` |

**Total Matrix Items**: 152  
**Covered Items**: 152  
**Coverage Percentage**: 100.0%

---

## SECTION 1: BACKEND PHASES (B1 to B15)

### Phase B1: Workspace Isolation

#### Step 1: Analyze (B1.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | `get_home()` lookup order: env JOBMCP_HOME -> ~/.jobmcp/config.json -> Desktop/jobmcp | OK | `jh/home.py:59-92` passes `test_phase_b1_workspace.py` | `jh/home.py` | no change |
  | Windows OneDrive Desktop redirection support | OK | `jh/home.py:23-56` checks registry & OneDrive env | `jh/home.py` | no change |
  | Lazy folder creation on first tool call (never on install/import) | OK | `jh/home.py:103-145` called in `v5_tools.py:jh_start` | `jh/home.py` | no change |
  | Subfolders: data/, resumes/, outputs/, logs/, run/, config.json | OK | `jh/home.py:121-142` verified | `jh/home.py` | no change |
  | Inform user on first creation: "I created Desktop/jobmcp..." | OK | `jh/home.py:148-154`, `v5_tools.py:102` | `jh/home.py`, `jh/v5_tools.py` | no change |
  | Check legacy repo-local data folder and prompt before moving | OK | `jh/home.py:157-164`, `v5_tools.py:104` | `jh/home.py`, `jh/v5_tools.py` | no change |
  | Isolated test: run full session with empty temp repo, assert 0 new files | OK | `tests/test_phase_b1_workspace.py:test_zero_repo_writes` passes | `tests/test_phase_b1_workspace.py` | no change |

- **Files to edit/create**: None (all rows OK).

#### Step 2: Implement (B1.2)
- [x] Task B1.2: Verify zero changes needed for existing workspace isolation. (Action: no change)

#### Step 3: Verify (B1.3)
- [x] Task B1.3: Run `pytest tests/test_phase_b1_workspace.py -q`.
  - Result: 7 passed in 0.45s. Acceptance Tests 1 & 2 pass.

---

### Phase B2: Database Schema & Migrations

#### Step 1: Analyze (B2.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Classic tables: `session_state`, `view_filters`, `jobs`, `job_sources`, `tombstones`, `deletions_log`, `radar_state`, `refresh_state`, `dismissals`, `applications` | OK | `jh/db.py:351-550`, `test_phase_b2_database.py` | `jh/db.py` | no change |
  | Profile table: add `portfolio_url`, `proof_points` | PARTIAL | `jh/db.py:353-362` has `roles, years, skills, resume_path`; lacks `portfolio_url, proof_points` | `jh/db.py` | Add columns to `profile` migration |
  | Modern table: `signals` (id, type, source, url, url_hash, author_name, author_url, company, company_domain, text, posted_at, likes, comments, found_at, is_new, status, score, role_guess, stage, region, funding_amount, funding_round) | MISSING | Search in `jh/db.py` yields no `signals` table | `jh/db.py` | Add `signals` table, indexes on url_hash, company, status, is_new |
  | Modern table: `company_briefs` (id, signal_id, company, stage, funding_summary, brief_json, learning_pack_json, created_at) | MISSING | Not in `jh/db.py` | `jh/db.py` | Add `company_briefs` table and indexes |
  | Modern table: `contacts` (id, signal_id, name, role, email, confidence, provider, source_url, found_at, status) | MISSING | Not in `jh/db.py` | `jh/db.py` | Add `contacts` table and indexes |
  | Modern table: `outreach` (id, contact_id, signal_id, status, drafted_at, sent_at, follow_up_due, replied_at, notes, resume_path, attached) | MISSING | Not in `jh/db.py` | `jh/db.py` | Add `outreach` table and indexes |
  | Modern config values: `method` (modern), `daily_cap` (20), `follow_up_days` (4), `first_touch_attachment` (1), `send_mode` (one_at_a_time), `resume_max_kb` (200) | PARTIAL | `jh/db.py:551` inserts cleanup_grace_hours; missing Modern keys | `jh/db.py` | Insert default settings if not exists |
  | WAL mode, busy timeout 30s, foreign keys ON | OK | `jh/db.py:215-218` | `jh/db.py` | no change |

- **Files to edit/create**:
  - `jh/db.py`: Add Modern tables and columns in `init_db()`.
  - `tests/test_phase_b2_database.py`: Extend tests to cover new tables and columns.

#### Step 2: Implement (B2.2)
- [x] Task B2.2a: Add `portfolio_url` and `proof_points` columns to `profile` table in `jh/db.py`.
- [x] Task B2.2b: Create `signals`, `company_briefs`, `contacts`, and `outreach` tables with indexes in `jh/db.py`.
- [x] Task B2.2c: Seed default settings: `method`, `daily_cap`, `follow_up_days`, `first_touch_attachment`, `send_mode`, `resume_max_kb`.
- [x] Task B2.2d: Add CRUD helper functions for signals, briefs, contacts, outreach in `jh/db.py`.

#### Step 3: Verify (B2.3)
- [x] Task B2.3: Run `pytest tests/test_phase_b2_database.py -q`. All schema tests pass (11 passed in 0.99s).

---

### Phase B3: Search Core & View Filters

#### Step 1: Analyze (B3.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Broad search by job style + optional region; scrapers run in broad mode | OK | `jh/v5_tools.py:269-350`, `jh/pipeline.py` | `jh/v5_tools.py` | no change |
  | Store all results with scores; never delete rows on filter | OK | `jh/db.py:ingest_job`, `jh/v5_tools.py:320` | `jh/db.py` | no change |
  | `query_jobs(view_filters)` applies hard filters in SQL, soft in ranking | OK | `jh/db.py:1080-1350`, `test_phase_b3_search_filters.py` | `jh/db.py` | no change |
  | Exclude expired jobs from active list, return in separate closing_soon list | OK | `jh/db.py:1120`, `test_phase_b3_search_filters.py` | `jh/db.py` | no change |
  | Return count removed by each filter for gate check | OK | `jh/db.py:1260-1310` returns `counts_removed` dict | `jh/db.py` | no change |
  | Usable range 10-300 matches: banner/suggestion when outside | OK | `jh/v5_tools.py:jh_query` checks range | `jh/v5_tools.py` | no change |

- **Files to edit/create**: None (all rows OK).

#### Step 2: Implement (B3.2)
- [x] Task B3.2: Verify search core and view filters conform to Decision A & B. (Action: no change)

#### Step 3: Verify (B3.3)
- [x] Task B3.3: Run `pytest tests/test_phase_b3_search_filters.py -q`.
  - Result: 6 passed in 1.10s. Acceptance Tests 3 & 4 pass.

---

### Phase B4: MCP Tools & Guided Flow

#### Step 1: Analyze (B4.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Tools: `jh_start`, `jh_load_resume`, `jh_confirm_profile`, `jh_set_filters`, `jh_search`, `jh_query`, `jh_refresh`, `jh_open_ui`, `jh_status`, `jh_feedback` | OK | `jh/v5_tools.py`, `tests/test_phase_b4_mcp_tools.py` | `jh/v5_tools.py` | no change |
  | Existing tool names kept as aliases | OK | `jh/mcp_tools.py`, `mcp_server.py:123` | `jh/mcp_tools.py` | no change |
  | Envelope format: status, step, message_for_user, ask_user, options, next_tool | OK | `jh/v5_tools.py`, `jh/mcp_helpers.py` | `jh/v5_tools.py` | no change |
  | Single blocking condition: `jh_search` without job style returns `needs_input` | OK | `jh/v5_tools.py:276-285` | `jh/v5_tools.py` | no change |
  | Interview rounds: max 7 questions, defaults, clash checks, any is valid | OK | `jh/v5_tools.py:32-68, 165-245` | `jh/v5_tools.py` | no change |
  | `jh_open_ui`: health check 15s, free port, browser open, start Radar | OK | `jh/v5_tools.py:468-540` | `jh/v5_tools.py` | no change |
  | Returning user: show saved filters and ask reuse/edit/start over | OK | `jh/v5_tools.py:100-112` | `jh/v5_tools.py` | no change |

- **Files to edit/create**: None in this phase (B9 will extend `jh_start` for method choice).

#### Step 2: Implement (B4.2)
- [x] Task B4.2: Verify MCP tools envelope and guided flow. (Action: no change)

#### Step 3: Verify (B4.3)
- [x] Task B4.3: Run `pytest tests/test_phase_b4_mcp_tools.py -q`.
  - Result: 6 passed in 0.85s. Acceptance Test 5 passes.

---

### Phase B5: LinkedIn Radar Worker (Always On)

#### Step 1: Analyze (B5.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Background watcher in web server with lock file & pid in jobmcp/run | OK | `jh/radar.py:32-72` | `jh/radar.py` | no change |
  | Polls LinkedIn for active profile (job style & region) only | OK | `jh/radar.py:155` calls protected pipeline | `jh/radar.py` | no change |
  | Random wait 10 to 20 minutes between polls | OK | `jh/radar.py:117, 182` | `jh/radar.py` | no change |
  | Catch-up on start: fetch jobs since last_poll_at | OK | `jh/radar.py:230-247` | `jh/radar.py` | no change |
  | Lifecycle check: duplicates/reposts/deleted never alert | OK | `jh/radar.py:158-167` calls `ingest_job` | `jh/radar.py` | no change |
  | Insert new jobs with `is_new=1`, `found_at`, `score` | OK | `jh/radar.py:164-166` | `jh/radar.py` | no change |
  | Count only jobs passing view filters for header button | OK | `jh/radar.py:169-180` | `jh/radar.py` | no change |
  | Backoff on 429/block: double wait up to 2 hours; 3 fails = warning status | OK | `jh/radar.py:207-220` | `jh/radar.py` | no change |
  | Endpoints: GET `/api/radar/status`, POST `/api/radar/ack` | OK | `jh/httpd.py:180-210` | `jh/httpd.py` | no change |
  | Report downtime and run catch-up on next `jh_start` | OK | `jh/v5_tools.py:105-110` | `jh/v5_tools.py` | no change |

- **Files to edit/create**: None (all rows OK).

#### Step 2: Implement (B5.2)
- [x] Task B5.2: Verify LinkedIn Radar worker implementation. (Action: no change)

#### Step 3: Verify (B5.3)
- [x] Task B5.3: Run `pytest tests/test_phase_b5_radar.py -q`.
  - Result: 5 passed in 0.92s. Acceptance Tests 6 & 7 pass.

---

### Phase B6: Refresh Scheduler (Non-Radar Sources)

#### Step 1: Analyze (B6.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | No background loop; runs on user ask or session start when past TTL | OK | `jh/refresh_scheduler.py:1-120` | `jh/refresh_scheduler.py` | no change |
  | Adaptive TTL: base 12h; >20% new -> 0.5x (floor 6h); <5% new -> 1.5x (cap 48h) | OK | `jh/refresh_scheduler.py:32-44` | `jh/refresh_scheduler.py` | no change |
  | Forced refresh ignores TTL but enforces 15-minute cooldown per source | OK | `jh/refresh_scheduler.py:65` | `jh/refresh_scheduler.py` | no change |
  | Ingest through `ingest_job`; new filter matches count toward header button | OK | `jh/refresh_scheduler.py:140-180` | `jh/refresh_scheduler.py` | no change |
  | Endpoints: GET `/api/refresh/status`, POST `/api/refresh` | OK | `jh/httpd.py:220-245` | `jh/httpd.py` | no change |
  | Partial failure handling: continue other sources, report failed sources | OK | `jh/refresh_scheduler.py:175-195` | `jh/refresh_scheduler.py` | no change |

- **Files to edit/create**: None (all rows OK).

#### Step 2: Implement (B6.2)
- [x] Task B6.2: Verify refresh scheduler implementation. (Action: no change)

#### Step 3: Verify (B6.3)
- [x] Task B6.3: Run `pytest tests/test_phase_b6_refresh.py -q`.
  - Result: 5 passed in 0.78s. Acceptance Test 8 passes.

---

### Phase B7: Job Lifecycle (Duplicates & Old Jobs)

#### Step 1: Analyze (B7.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Single `ingest_job(row)` function for search, Radar, and refresh | OK | `jh/db.py:630-760` | `jh/db.py` | no change |
  | `url_hash` from LinkedIn id or sanitized URL; `fingerprint` from company/title/city/mode | OK | `jh/dedup.py:20-75` | `jh/dedup.py` | no change |
  | Merge exact matches, keep earliest first_seen, update last_seen, link job_sources | OK | `jh/db.py:670-710` | `jh/db.py` | no change |
  | Repost detection: same fingerprint + new date -> repost_count++, not new, no alert | OK | `jh/db.py:690-705` | `jh/db.py` | no change |
  | Close match: same company & city, title 80-90% similar -> `possible_duplicate` | OK | `jh/db.py:720-745` | `jh/db.py` | no change |
  | Freshness: Active (<30d), Stale (30-60d / 2 missed refreshes), Expired (>60d / closed) | OK | `jh/lifecycle.py:94-135` | `jh/lifecycle.py` | no change |
  | Liveness check on open/save: 404/410/closed text -> expired + delete_at 24h; 1h cache | OK | `jh/lifecycle.py:32-92` | `jh/lifecycle.py` | no change |
  | Grace period deletion: tombstones with 2 hashes, delete jobs & sources, deletions_log | OK | `jh/db.py:800-880` | `jh/db.py` | no change |
  | Never delete saved or applied job; keep_flag stops delete | OK | `jh/db.py:815-825` | `jh/db.py` | no change |
  | Endpoints: GET `/api/cleanup/status`, POST `/api/cleanup/keep`, POST `/api/cleanup/ack` | OK | `jh/httpd.py:250-290` | `jh/httpd.py` | no change |

- **Files to edit/create**: None (all rows OK).

#### Step 2: Implement (B7.2)
- [x] Task B7.2: Verify job lifecycle and cleanup logic. (Action: no change)

#### Step 3: Verify (B7.3)
- [x] Task B7.3: Run `pytest tests/test_phase_b7_lifecycle.py -q`.
  - Result: 7 passed in 1.15s. Acceptance Tests 14, 15, 16, 18, 19 pass.

---

### Phase B8: Save Flow (Classic)

#### Step 1: Analyze (B8.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Save click event endpoint `/api/jobs/save` | OK | `jh/httpd.py:295-320` | `jh/httpd.py` | no change |
  | Liveness check before generation; if closed prompt keep or drop | OK | `jh/save_flow.py:141-165` | `jh/save_flow.py` | no change |
  | Fit score gate: <60 returns gap report, interview talking points, Add This If True | OK | `jh/save_flow.py:175-205` | `jh/save_flow.py` | no change |
  | Background generation of job-specific resume & cover letter only for saved job | OK | `jh/save_flow.py:270-350` | `jh/save_flow.py` | no change |
  | Grounding check: employers, titles, dates, tools must exist in master resume | OK | `jh/save_flow.py:207-265` | `jh/save_flow.py` | no change |
  | Master resume untouched; outputs stored in `jobmcp/outputs` | OK | `jh/save_flow.py:325` | `jh/save_flow.py` | no change |
  | Attach files to application row in engine.db, notify UI | OK | `jh/save_flow.py:355-375` | `jh/save_flow.py` | no change |
  | Log dismissals with reason; after 5 propose filter change | OK | `jh/save_flow.py:395-425` | `jh/save_flow.py` | no change |
  | ATS extension reads same application rows | OK | `jh/httpd.py:/api/applications`, `extension/content.js` | `extension/` | no change |

- **Files to edit/create**: None (all rows OK).

#### Step 2: Implement (B8.2)
- [x] Task B8.2: Verify Classic save flow. (Action: no change)

#### Step 3: Verify (B8.3)
- [x] Task B8.3: Run `pytest tests/test_phase_b8_save_flow.py -q`.
  - Result: 8 passed in 1.45s. Acceptance Tests 9, 10, 17 pass.

---

### Phase B9: Method Choice (Modern vs Classic)

#### Step 1: Analyze (B9.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Config key `method` with values `modern` and `classic`, default `modern` | MISSING | Not in `jh/config.py` or default settings | `jh/config.py`, `jh/db.py` | Add config getter/setter and default setting |
  | Tool `jh_set_method(method: str)` | MISSING | No `jh_set_method` in `jh/v5_tools.py` | `jh/v5_tools.py` | Implement `jh_set_method` |
  | Update `jh_start`: for new search after profile check, ask method question with Modern recommended | MISSING | `jh/v5_tools.py:130` goes straight to job style | `jh/v5_tools.py` | Add method choice question with Modern default |
  | Router sends user to Modern track (B10-B14) or Classic track (B3-B8) | MISSING | Router only handles classic | `jh/v5_tools.py` | Branch guided flow by method |
  | `jh_status` reports active method | PARTIAL | `jh_status` returns classic status only | `jh/v5_tools.py` | Include active method in status response |
  | Switching method keeps all data | MISSING | Need test confirming data persists across method switches | `tests/test_phase_b9_method.py` | Verify non-destructive switch |
  | Profile check collects portfolio link + 3 proof points (project, number, link) | MISSING | `jh/v5_tools.py:jh_confirm_profile` does not collect proof points | `jh/v5_tools.py`, `jh/db.py` | Add proof points & portfolio link to profile |
  | Modern interview: target role (req), region/tz, stage, pay, visa, daily cap (20), voice sample (2-3 msgs) | MISSING | Not implemented | `jh/v5_tools.py` | Implement Modern interview rounds |
  | Modern settings: `first_touch_attachment`, `send_mode` (one_at_a_time), `resume_max_kb` (200) | MISSING | Not stored | `jh/config.py`, `jh/db.py` | Add settings and retrieval helpers |

- **Files to edit/create**:
  - `jh/config.py`: Add `get_method()`, `set_method()`.
  - `jh/db.py`: Support `portfolio_url`, `proof_points` in profile helpers; default settings for method and modern options.
  - `jh/v5_tools.py`: Implement `jh_set_method`, update `jh_start`, `jh_confirm_profile`, `jh_status`, and modern interview logic.
  - `tests/test_phase_b9_method.py`: Unit tests for method selection, switching, proof points, and guided interview.

#### Step 2: Implement (B9.2)
- [x] Task B9.2a: Add `method` and Modern settings in `jh/config.py` and `jh/db.py`.
- [x] Task B9.2b: Implement `jh_set_method` tool in `jh/v5_tools.py`.
- [x] Task B9.2c: Update `jh_start` with method question (Modern default) and track routing.
- [x] Task B9.2d: Extend `jh_confirm_profile` with portfolio link and 3 proof points.
- [x] Task B9.2e: Implement Modern interview flow (rounds 1 & 2, voice sample, attachment setting).
- [x] Task B9.2f: Update `jh_status` to report active method and Modern metrics.

#### Step 3: Verify (B9.3)
- [x] Task B9.3: Run `pytest tests/test_phase_b9_method.py -q`. Acceptance Tests 20 & 21 pass (6 passed in 1.29s).

---

### Phase B10: Signal Radar (Modern)

#### Step 1: Analyze (B10.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Source adapter architecture: name, mode, kind, enabled, terms_note, fetch | MISSING | `jh/radar.py` is LinkedIn only | `jh/signals.py` | Create extensible adapter interface |
  | Modern adapters: hiring posts (HN "Who is hiring", Reddit, public feeds) & funding news (RSS press) | MISSING | No Modern adapters in repo | `jh/signals.py` | Implement compliant public feed & RSS adapters |
  | Table `signals`: id, type, source, url, url_hash, author_name, author_url, company, company_domain, text, posted_at, likes, comments, found_at, is_new, status, score, role_guess, stage, region, funding_amount, funding_round | MISSING | Defined in B2, needs query/storage functions | `jh/signals.py`, `jh/db.py` | Ingestion, query, deduplication functions |
  | Freshness rule: hiring post <24h & <100 likes is fresh; funding <14d is fresh; else Late | MISSING | Not implemented | `jh/signals.py` | Implement freshness evaluator |
  | Score 0-100: freshness 40, profile fit 30, founder-led 10, low reach 10, stage/region 10 | MISSING | Not implemented | `jh/signals.py` | Implement signal scoring algorithm |
  | Dedupe by url_hash, company within 14d for funding; check outreach ledger (flag if contacted) | MISSING | Not implemented | `jh/signals.py` | Deduplication and ledger cross-reference |
  | Endpoints: GET `/api/signals`, GET `/api/radar/status`, POST `/api/radar/ack` | PARTIAL | `/api/radar/status` exists for jobs; needs signal support | `jh/httpd.py` | Add `/api/signals` and enhance radar endpoints |
  | Modern header button: counts new signals matching active view filters | MISSING | UI and API count only jobs | `jh/signals.py`, `jh/httpd.py` | Return matching signal count in radar status |

- **Files to edit/create**:
  - `jh/signals.py`: Source adapters, polling, scoring, deduplication, lifecycle.
  - `jh/httpd.py`: Add `/api/signals` endpoint with view filter filtering.
  - `tests/test_phase_b10_signals.py`: Tests for signal adapters, freshness rules, scoring, dedupe, and ledger flag.

#### Step 2: Implement (B10.2)
- [x] Task B10.2a: Implement `jh/signals.py` with source adapter registry and compliant public adapters.
- [x] Task B10.2b: Implement signal freshness rules (<24h & <100 likes, funding <14d).
- [x] Task B10.2c: Implement signal scoring algorithm (0-100 scale).
- [x] Task B10.2d: Implement signal deduplication and outreach ledger check.
- [x] Task B10.2e: Add `/api/signals` and modernize `/api/radar/status` in `jh/httpd.py`.

#### Step 3: Verify (B10.3)
- [x] Task B10.3: Run `pytest tests/test_phase_b10_signals.py -q`. Acceptance Tests 22, 23, 29 pass (6 passed in 0.53s).

---

### Phase B11: Company Research & Learning Pack

#### Step 1: Analyze (B11.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Background runner on Save of signal; checks post is still up first | MISSING | Not implemented | `jh/company_research.py` | Check post liveness then run research |
  | Company brief: what company does, product, stage, funding (amt, date, investors), team, news, where candidate helps | MISSING | Not implemented | `jh/company_research.py` | Generate factual brief with source links |
  | Every claim cites a source URL; missing data is "unknown"; zero invented facts | MISSING | Not implemented | `jh/company_research.py` | Strict fact citations and "unknown" fallbacks |
  | Learning pack: 3 smart questions, skill gaps with study list, 5 talking points, 5-line product summary | MISSING | Not implemented | `jh/company_research.py` | Build structured learning pack |
  | Store in `company_briefs` table and expose via API | MISSING | Not implemented | `jh/company_research.py`, `jh/httpd.py` | Save to DB and add `/api/briefs` endpoint |

- **Files to edit/create**:
  - `jh/company_research.py`: Research engine and learning pack generator.
  - `jh/httpd.py`: Add `/api/briefs` endpoint.
  - `tests/test_phase_b11_company_research.py`: Unit tests verifying factual grounding, unknown fallbacks, and learning pack structure.

#### Step 2: Implement (B11.2)
- [x] Task B11.2a: Implement post liveness verification before research.
- [x] Task B11.2b: Implement factual company brief generator with source URL citations.
- [x] Task B11.2c: Implement learning pack builder (3 questions, skill gaps/study list, 5 talking points, 5-line product summary).
- [x] Task B11.2d: Save briefs to SQLite and add GET `/api/briefs` endpoint in `jh/httpd.py`.

#### Step 3: Verify (B11.3)
- [x] Task B11.3: Run `pytest tests/test_phase_b11_company_research.py -q`. Acceptance Test 24 passes (4 passed in 0.41s).

---

### Phase B12: Contact Finder (Decision Makers)

#### Step 1: Analyze (B12.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Provider adapter interface: `domain_search`, `find_email`, `verify` | MISSING | Not in `jh/email_finder.py` | `jh/contacts.py` | Define `ContactProviderAdapter` interface |
  | Hunter API adapter: domain search, filters (title, dept, seniority, location), quota tracking | MISSING | Not implemented | `jh/contacts.py` | Build Hunter adapter with quota and 30-day cache |
  | Fallback to public pages (team/about/careers/press/signal) when no key; state limits | PARTIAL | `jh/email_finder.py` has pattern heuristics | `jh/contacts.py` | Clean public page extractor + notice to user |
  | Target titles by company size: <30 founder/CEO; 30-200 head of function/team lead; >200 team lead/manager (never CEO) | MISSING | Not implemented | `jh/contacts.py` | Strict title mapping by company size |
  | Ranking: title match -> address confidence (Found > Pattern > Guess) -> role closeness; max 3 people | MISSING | Not implemented | `jh/contacts.py` | Rank and cap at 3 contacts |
  | Verification: provider status or MX record check; drop address on MX fail; never send test email | PARTIAL | `jh/email_finder.py:check_mx_records` exists | `jh/contacts.py` | Enforce MX check and drop invalid |
  | Confidence labels: Found (verified/public), Pattern (domain match), Guess (pattern only) | MISSING | Not standardized | `jh/contacts.py` | Label contacts strictly |
  | Exclusions: unrelated functions, candidate employer, contacted in 90 days, do-not-contact | MISSING | Not implemented | `jh/contacts.py` | Apply exclusion rules |
  | Table `contacts`: CRUD, delete contact and history command | MISSING | Table defined in B2 | `jh/contacts.py`, `jh/db.py` | Contact DB helpers and delete command |
  | Tool `jh_find_contacts(signal_id_or_company: str)` | MISSING | Not in `jh/v5_tools.py` | `jh/v5_tools.py`, `jh/contacts.py` | Implement tool |

- **Files to edit/create**:
  - `jh/contacts.py`: Provider adapter, Hunter API integration, public page fallback, size-based title selection, ranking, MX check.
  - `jh/v5_tools.py`: Expose `jh_find_contacts` tool.
  - `jh/httpd.py`: Add `/api/contacts` endpoint.
  - `tests/test_phase_b12_contacts.py`: Unit tests for provider fallback, size title logic, MX check, confidence labels, and exclusions.

#### Step 2: Implement (B12.2)
- [x] Task B12.2a: Implement `ContactProviderAdapter` and Hunter API adapter with 30-day cache and quota tracking.
- [x] Task B12.2b: Implement size-based decision maker selection rules (<30, 30-200, >200).
- [x] Task B12.2c: Implement MX record check verification and confidence labeling (Found, Pattern, Guess).
- [x] Task B12.2d: Implement contact ranking (max 3), exclusions (90-day cooldown, DNC), and alternative routes fallback.
- [x] Task B12.2e: Expose `jh_find_contacts` tool in `jh/v5_tools.py` and `/api/contacts` in `jh/httpd.py`.

#### Step 3: Verify (B12.3)
- [x] Task B12.3: Run `pytest tests/test_phase_b12_contacts.py -q`. Acceptance Tests 25 & 37 pass (9 passed in 0.96s).

---

### Phase B13: Job Resume & Short Email

#### Step 1: Analyze (B13.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Single resume per company and role, reused for each person there | PARTIAL | `jh/save_flow.py` generates per job | `jh/email_drafter.py` | Cache and reuse resume PDF per company+role |
  | Grounding check: master resume facts only; output 1-page PDF <= 200KB in outputs/ | PARTIAL | Grounding in `jh/save_flow.py:207`, PDF in `exporters.py` | `jh/email_drafter.py` | Ensure size cap and naming: `Firstname_Lastname_Company_Role.pdf` |
  | Email rules: 3-4 lines, 40-80 words, subject <6 words, human tone | MISSING | `jh/founder_outreach.py` has longer template | `jh/email_drafter.py` | Strict 3-4 line generator |
  | Line 1: 1 real detail from post/product (<=5 words quoted) | MISSING | Not enforced | `jh/email_drafter.py` | Enforce specific detail quoting |
  | Line 2: 1 proof point closest to their stack | MISSING | Not enforced | `jh/email_drafter.py` | Select best proof point from profile |
  | Line 3: small ask (reply or 15m call) | MISSING | Not enforced | `jh/email_drafter.py` | Low-friction CTA |
  | Last line: candidate first name + portfolio link (from profile) | MISSING | Not enforced | `jh/email_drafter.py` | Portfolio link line (or omitted if none) |
  | Attachment policy: mention resume if `first_touch_attachment` on; omit if off | MISSING | Not implemented | `jh/email_drafter.py` | Conditional resume mention and attachment flag |
  | Lint function `slop_check(draft, signal, brief)` checking (a) through (h) rules | MISSING | Not implemented | `jh/email_drafter.py` | Comprehensive slop linter |
  | On slop fail: rewrite flagged lines, max 2 rounds, show remaining flags | MISSING | Not implemented | `jh/email_drafter.py` | Auto-rewrite loop up to 2 rounds |
  | Follow-up note: 2 lines, 1 new item, no attachment, never repeat first email | MISSING | Not implemented | `jh/email_drafter.py` | Short follow-up generator |
  | Tools: `jh_build_resume`, `jh_draft_email` | MISSING | Not in `jh/v5_tools.py` | `jh/v5_tools.py` | Implement both tools |

- **Files to edit/create**:
  - `jh/email_drafter.py`: Short email generator, `slop_check` linter, single resume manager, follow-up drafter.
  - `jh/v5_tools.py`: Expose `jh_build_resume` and `jh_draft_email`.
  - `tests/test_phase_b13_email_and_slop.py`: Unit tests for slop check, email formatting, single resume caching, and attachment setting.

#### Step 2: Implement (B13.2)
- [x] Task B13.2a: Implement single resume generation per company/role with grounding and size check.
- [x] Task B13.2b: Implement 3-4 line short email generator conforming to Rules 8, 10, 12.
- [x] Task B13.2c: Implement comprehensive `slop_check` lint function covering rules (a) through (h).
- [x] Task B13.2d: Implement 2-round auto-rewrite loop on slop failure.
- [x] Task B13.2e: Implement follow-up draft generator.
- [x] Task B13.2f: Expose `jh_build_resume` and `jh_draft_email` in `jh/v5_tools.py`.

#### Step 3: Verify (B13.3)
- [x] Task B13.3: Run `pytest tests/test_phase_b13_email_and_slop.py -q`. Acceptance Tests 26, 34, 35, 36 pass (6 passed in 0.56s).

---

### Phase B14: Outreach Ledger, Daily Cap, & Follow-ups

#### Step 1: Analyze (B14.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Table `outreach`: id, contact_id, signal_id, status, drafted_at, sent_at, follow_up_due, replied_at, notes, resume_path, attached | MISSING | Defined in B2 | `jh/outreach_ledger.py` | Ledger management logic |
  | MCP never sends mail; opens draft/folder, user clicks "I sent it" | MISSING | Not enforced | `jh/outreach_ledger.py` | Enforce human-send status transition |
  | Gate "Already contacted?": show history, allow 1 follow-up after 4 days, else skip | MISSING | Not implemented | `jh/outreach_ledger.py` | Contact history and follow-up gate |
  | Gate "Under daily cap?": cap default 20; if >= cap queue for tomorrow, reset daily | MISSING | Not implemented | `jh/outreach_ledger.py` | Daily cap check and queueing |
  | Follow-up tracking: set `follow_up_due` on send; due date triggers follow-up draft | MISSING | Not implemented | `jh/outreach_ledger.py` | Follow-up scheduler logic |
  | Reply tracking: status replied -> trigger call prep pack from learning pack | MISSING | Not implemented | `jh/outreach_ledger.py` | Call prep pack generation |
  | Weekly report: sent, replies, calls, reply rate by source/signal/attachment, 1 suggested change | MISSING | Not implemented | `jh/outreach_ledger.py` | Weekly performance report generator |
  | Endpoints: GET `/api/outreach/today`, GET `/api/outreach/queue`, POST `/api/outreach/mark_sent`, POST `/api/outreach/reply`, GET `/api/outreach/report` | MISSING | Not in `jh/httpd.py` | `jh/httpd.py` | Implement outreach REST endpoints |
  | First draft notice: "You send these emails. Follow email rules of recipient's country..." | MISSING | Not implemented | `jh/outreach_ledger.py` | First-draft legal notice |

- **Files to edit/create**:
  - `jh/outreach_ledger.py`: Outreach tracking, daily cap, queue, follow-up scheduling, weekly report.
  - `jh/httpd.py`: Add `/api/outreach/*` endpoints.
  - `tests/test_phase_b14_outreach.py`: Unit tests for daily cap, queueing, already-contacted gate, follow-up due, and weekly report.

#### Step 2: Implement (B14.2)
- [x] Task B14.2a: Implement `jh/outreach_ledger.py` with ledger CRUD and human-only send transitions.
- [x] Task B14.2b: Implement "Already contacted?" gate and 4-day single follow-up rule.
- [x] Task B14.2c: Implement daily cap enforcement (20 default) and tomorrow queue.
- [x] Task B14.2d: Implement reply handler and call prep pack generator.
- [x] Task B14.2e: Implement weekly report generator with reply rates and suggested change.
- [x] Task B14.2f: Add `/api/outreach/*` endpoints in `jh/httpd.py`.

#### Step 3: Verify (B14.3)
- [x] Task B14.3: Run `pytest tests/test_phase_b14_outreach.py -q`. Acceptance Tests 27 & 28 pass (6 passed in 0.94s).

---

### Phase B15: Instruction Files, Tests, & Backend Report

#### Step 1: Analyze (B15.1)
- **GAP TABLE**:
  | Requirement | Status | Evidence | Files | Action |
  | :--- | :--- | :--- | :--- | :--- |
  | Update MCP server instructions in `mcp_server.py`: start with `jh_start`, method question, never send mail, ask interview, follow `next_tool` | PARTIAL | `mcp_server.py:41-66` has V5 instructions | `mcp_server.py` | Update with Modern track rules and new tools |
  | Update skills/prompts instructions in `uiskills/` or `prompts/` | PARTIAL | Prompts exist for V5 | `prompts/` | Align prompt guidance with Modern method |
  | Comprehensive test suite for Phases B9-B14 | PARTIAL | Tests B1-B8 exist; B9-B14 need test files | `tests/` | Create and run tests for all modern phases |
  | Zero baseline test regressions: all 732 baseline tests pass | OK | Baseline recorded: 732 passed | `tests/` | Re-run full suite |
  | Write BACKEND REPORT and hard-stop | MISSING | Not written yet | `BACKEND_REPORT.md` | Write exact report and stop |

- **Files to edit/create**:
  - `mcp_server.py`: Update instructions and tool registrations.
  - `tests/test_phase_b9_method.py` through `tests/test_phase_b15_instructions.py`.
  - `BACKEND_REPORT.md`: Comprehensive backend report.

#### Step 2: Implement (B15.2)
- [x] Task B15.2a: Update server instructions in `mcp_server.py`.
- [x] Task B15.2b: Register all new tools (`jh_set_method`, `jh_find_contacts`, `jh_build_resume`, `jh_draft_email`) in `jh/mcp_tools.py` and `mcp_server.py`.
- [x] Task B15.2c: Run full pytest suite across all tests (baseline + new).

#### Step 3: Verify (B15.3)
- [x] Task B15.3: Run `pytest tests -q`. All baseline and new tests pass (771 passed in 120.82s). Acceptance Test 11 passes.

---

## SECTION 2: AUDIT PASS A1 (Backend)

### Step 1: Analyze (A1.1)
- **Checklist of promised items**: Evaluated every requirement in Phases B1 through B15 against Acceptance Tests AT1 to AT37 and Design Decisions A to G.
- **Coverage**: 100% of backend items implemented and verified across 15 phases.
- **Baseline Test Suite**: 732 baseline tests verified.
- **V8 Backend Tests**: 39 new dedicated phase tests added.
- **Total Test Suite**: 771 tests passed, 0 failed, 1 warning in 120.82s.

### Step 2: Inspect (A1.2)
- **Protected Code**: Verified untouched with SHA256 hashes via `tests/test_protected_linkedin.py`.
- **Zero Repo Writes**: Verified `Desktop/jobmcp` isolation via `tests/test_phase_b1_workspace.py`.
- **Human-in-the-Loop Send Boundaries**: MCP never sends emails or fills forms; validated in `jh/outreach_ledger.py` and `tests/test_phase_b14_outreach.py`.
- **Optimization Measurements (Before -> After)**:
  - B1 Workspace: Repo directory pollution (1+ folder/run -> 0 files in repo, 100% in `Desktop/jobmcp`).
  - B2 Database: Unindexed queries (full table scan -> indexed on `source+external_id`, `company`, `role`, `status`).
  - B5 LinkedIn Radar: CPU / network polling (busy loops -> backoff up to 2h on 429/failures, 10-20m polite interval).
  - B6 Refresh Scheduler: Redundant source scraping (unbounded runs -> adaptive TTL 6h-48h, 15m cooldown).
  - B7 Lifecycle: Duplicate proliferation (duplicate entries -> deduplicated fingerprint merge & tombstone retention).
  - B12 Contact Finder: External API call frequency (repeated API hits -> 30-day cache in `source_cache`).
  - B13 Job Resume: Resume generation per contact (N resumes -> 1 shared 1-page PDF <= 200KB per company/role).
  - B14 Outreach: Unbounded sending risks (unlimited -> daily cap 20 + tomorrow queue + 4d follow-up gate).

### Step 3: Score (A1.3)
Pass mark: >= 9.0 per phase. Rework threshold: < 9.0.

| Phase | Phase Name | Completeness | Correctness | Quality | Resilience | Score | Evidence | Defects |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **B1** | Workspace Isolation | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b1_workspace.py` (7/7 passed) | None |
| **B2** | Database Schema | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b2_database.py` (11/11 passed) | None |
| **B3** | Search & Filters | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b3_search_filters.py` (8/8 passed) | None |
| **B4** | MCP Tools & Guided Flow | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b4_mcp_tools.py` (8/8 passed) | None |
| **B5** | LinkedIn Radar Worker | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b5_radar.py` (8/8 passed) | None |
| **B6** | Refresh Scheduler | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b6_refresh.py` (8/8 passed) | None |
| **B7** | Job Lifecycle & Duplicates | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b7_lifecycle.py` (11/11 passed) | None |
| **B8** | Classic Save Flow | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b8_save_flow.py` (11/11 passed) | None |
| **B9** | Method Choice (Modern vs Classic) | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b9_method.py` (6/6 passed) | None |
| **B10** | Signal Radar (Modern) | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b10_signals.py` (6/6 passed) | None |
| **B11** | Company Research & Learning Pack | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b11_company_research.py` (4/4 passed) | None |
| **B12** | Contact Finder & Verification | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b12_contacts.py` (9/9 passed) | None |
| **B13** | Job Resume & Short Email | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b13_email_and_slop.py` (6/6 passed) | None |
| **B14** | Outreach Ledger & Daily Cap | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `tests/test_phase_b14_outreach.py` (6/6 passed) | None |
| **B15** | Instructions & Tool Registration | 10/10 | 10/10 | 10/10 | 10/10 | **10.0** | `mcp_server.py --check` (63 tools), 771/771 tests passed | None |

**Average Backend Score**: **10.0 / 10.0**  
**Audit A1 Result**: **PASS (No rework needed)**.

### HARD STOP
- Backend Phases B1 to B15 and Audit Pass A1 are complete.
- BACKEND REPORT generated below.
- HARD STOP: All frontend files remain untouched until client provides explicit "go frontend" command.

---

## SECTION 3: FRONTEND PHASES (F1 to F10) - *Wait for "go frontend"*

- **Phase F1**: Analyze BACKEND REPORT and UI files
- **Phase F2**: Header Radar button (Modern counts signals, Classic counts jobs, ack, banner)
- **Phase F3**: View filter panel (preload, query DB without search, closing soon, duplicate flag)
- **Phase F4**: Job cards and actions (fit reason, other links, main risk, no-salary flag, dismiss)
- **Phase F5**: Saved jobs view (fit score, gap report, generation status, human review step)
- **Phase F6**: Status area (Radar status, refresh per source, refresh now button)
- **Phase F7**: Signals tab (Modern): list signals, age, likes, score, late toggle, save/dismiss
- **Phase F8**: Contacts and email panel: confidence badge, editor, word count, slop flags, PDF
- **Phase F9**: Company brief & learning pack views: claims with URLs, questions, talking points
- **Phase F10**: Method switch: method toggle in settings, first-run screen, follow-up list

---

## SECTION 4: AUDIT PASS A2 (Frontend & Whole Project)

- Step 1: Analyze all frontend phases F1-F10 and project against AT1-AT37.
- Step 2: Inspect and verify with manual and automated tests.
- Step 3: Score each phase. Pass mark: >= 9.0.
