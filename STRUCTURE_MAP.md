# JobHunter MCP — Repository Structure Map

## 1. System Architecture Overview
JobHunter is an agent-first Job Hunting MCP (Model Context Protocol) engine designed for autonomous and semi-autonomous job acquisition across two primary tracks:
- **Modern Track (Default)**: Outbound proactive outreach. Scans early funding signals (Seed/Pre-seed <14 days) and fresh hiring posts (<24h, <100 likes), discovers verified decision-maker contacts by company size, generates customized one-page resumes and concise cold emails (3-4 lines, 40-80 words, 1 portfolio link, anti-slop checked), and queues outreach under a strict daily cap of 20.
- **Classic Track**: Traditional job boards (LinkedIn, RemoteOK, Jobicy, Himalayas, etc.). Ingests broad search results into local SQLite, applies live query-time filtering without re-scraping, performs liveness and fit checks on Save, executes grounding audits against master resume facts, and autofills ATS application forms via a Chrome extension while leaving the final submit button to the human candidate.

---

## 2. Directory Layout & Subsystem Mapping

```
jobhunter/
├── jh/                          # Core Python engine & MCP business logic
│   ├── config.py                # Global configurations (TTL, caps, timeouts, protected configs)
│   ├── home.py                  # Isolated home folder management (~/Desktop/jobmcp or JOBMCP_HOME)
│   ├── db.py                    # SQLite schema, queries, application states, session persistence
│   ├── models.py                # Pydantic data schemas (Job, Profile, Signal, Contact, etc.)
│   ├── resume_checker.py        # Local resume validation (PDF, DOCX, TXT, OCR, cover letter, JD checks)
│   ├── resume_parser.py         # Multi-format resume text extraction and structural entity parsing
│   ├── role_inference.py        # Role, skill cluster, and seniority level inference (confidence scoring)
│   ├── interview_questions.py   # Guided interview generation (Location first, Level, Pay, Visa, etc.)
│   ├── ticket_manager.py        # 2-hour session tickets, gating enforcement, stop messages
│   ├── worker_launcher.py       # Detached server.py daemon & background search launcher (<3s, idempotent)
│   ├── v5_tools.py              # User-facing MCP tool definitions (jh_begin, jh_launch, jh_answer, etc.)
│   ├── preferences.py           # User preference storage & SQL query-time filter translation
│   ├── scoring.py               # 0-100 match scoring, Safe/Match/Reach classification, gap detection
│   ├── refit.py                 # Resume refitting, reordering, honest tailoring without fact inflation
│   ├── signals.py               # Signal ingestion & freshness filtering (funding <14d, posts <24h & <100 likes)
│   ├── radar.py                 # Always-on LinkedIn radar background polling with exponential backoff
│   ├── refresh_scheduler.py     # Adaptive TTL calculation for secondary sources (halves on >20%, grows on <5%)
│   ├── lifecycle.py             # Deduplication, fingerprinting, 24h grace deletion warnings, tombstones
│   ├── contacts.py              # Size-tiered decision maker finder (Found, Pattern, Guess; no scraping)
│   ├── email_drafter.py         # Cold email generation (3-4 lines, 40-80 words, 1 link, anti-slop checked)
│   ├── slop.py                  # Banned AI cliché phrase detector & linter
│   ├── outreach_ledger.py       # 90-day cooldown enforcement, 1 follow-up max, daily cap tracker
│   ├── save_flow.py             # Classic generation gate (Save-only trigger, liveness & fit checks)
│   ├── evidence.py              # Grounding audit against master facts (detects invented employers/titles)
│   ├── screening.py             # Form autofill engine, known vs unknown question handling, EEO auto-decline
│   ├── interview.py             # Coaching on trigger, 0-10 mock interview evaluation with quotes & fixes
│   ├── digest.py                # Daily digest & weekly performance reports
│   ├── gmail_tracker.py         # Read-only Gmail sync restricted to ledger contacts
│   ├── httpd.py                 # Embedded Python REST API server for webapp & extension
│   ├── mcp_helpers.py           # Standardized Result envelopes & ToolError exception handlers
│   ├── sources/                 # Modular scrapers (LinkedIn, Jobicy, RemoteOK, Himalayas, Arbeitnow, etc.)
│   └── team/                    # Subagent prompts, role specifications, router, QA, and claims
├── extension/                   # Chrome extension for ATS form autofilling (stops before submit)
│   ├── manifest.json            # Manifest V3 configuration
│   ├── content.js               # Form field detection & autofill injection
│   └── background.js            # Background communication with local server
├── webapp/                      # Lightweight HTML5 / Tailwind Web UI
│   ├── index.html               # Main dashboard (Match list, signals, contacts, filter strip, banners)
│   └── app.js                   # Client-side reactivity, SSE updates, and status polling
├── prompts/                     # Prompt templates & voice guidelines (<voice> identical contract)
├── tests/                       # Complete test suite
│   ├── test_protected_linkedin.py # SHA256 integrity checks for protected scraping code
│   ├── test_team.py             # Role and specialist tool membership gates
│   ├── test_evals.py            # AI QA and hallucination evaluation gate
│   ├── test_prompts.py          # Prompt format & voice contract linting
│   ├── test_prompt_contract.py  # Prompt system message contract tests
│   └── e2e/                     # Hermetic E2E test kit (T1 to T24 scenarios, mock servers, fixtures)
│       ├── run_all.py           # E2E suite orchestrator and report generator
│       ├── test_suite.py        # Black-box scenario implementations
│       ├── mock_servers.py      # Offline mock HTTP servers (Job boards, Signals, Contacts, Gmail)
│       ├── scripted_client.py   # Scripted MCP client simulating lazy and diligent agents
│       └── fixtures/            # Test resumes (valid, thin, scanned, cover letter, JD) and fixture jobs
├── server.py                    # Standalone FastAPI/HTTP daemon process entry point
├── mcp_server.py                # FastMCP stdio server entry point
├── AGENTS.md                    # Working rules & protected code constraints
└── TASKS.md                     # Engineering task board & verification status
```

---

## 3. Data Flow & Subsystem Interaction

### A. Start-Up & Discovery Flow (P1 - P5, T1 - T8)
1. **Candidate Input**: User provides a resume path/text to `jh_begin` (or aliases `jh_start`, `jh_load_resume`).
2. **Local Validation**: `jh.resume_checker` verifies the document without network. Stops with `needs_resume` if invalid/unreadable/cover letter. Warns if older than 2 years. If multiple resumes provided, asks user which to use.
3. **Role & Seniority Inference**: `jh.role_inference` extracts candidate titles, skills, and years of experience. Calculates confidence score (0.0 - 1.0). If confidence >= 0.5, status is `ready` and generates a 2-hour session ticket. If confidence < 0.5, status is `needs_role` and halts with STOP directive.
4. **Detached Worker Launch**: `jh_launch` starts `server.py` daemon, background search scraper, and Chromium browser in parallel within < 3 seconds. The worker process is fully detached and survives caller termination.
5. **Interactive Guidance**: In parallel, MCP presents Round 2 steering questions (Location first, Level shift, Job type, Work mode, Pay, Visa, Exclusions) in chat. Tool replies carry `pending_questions` until answered via `jh_answer` or explicitly skipped.

### B. Search, Filtering & Signal Ingestion (P6 - P12, T9 - T13)
1. **Broad Search**: Scrapers pull jobs across target locations/roles and ingest them into SQLite via `jh.lifecycle.ingest_job()`.
2. **Deduplication & Lifecycle**: Exact URL hash or content fingerprints merge automatically, retaining multiple source links. Reposts do not trigger new alerts. Expired postings receive a 24h grace deletion countdown (`delete_at`). Saved or applied jobs are never deleted.
3. **Live Query-Time Filtering**: `preferences.query_jobs()` applies user filters dynamically at SQL query time. Hidden jobs are counted and never deleted.
4. **Always-On Radar**: `jh.radar` periodically polls LinkedIn for new jobs and monitors funding news (<14 days) and hiring posts (<24h, <100 likes). 429 rate limits trigger exponential backoff up to 2 hours.
5. **Adaptive Refresh**: Non-radar sources refresh based on adaptive TTL (12h base, halves on >20% new listings down to 6h, expands to 48h if <5% new). Forced refreshes enforce a 15-minute cooldown.

### C. Modern Outreach Track (P14 - P16, T14 - T15)
1. **Signal Save**: User saves a funding signal or hiring post.
2. **Company Brief**: Engine compiles verified claims with source citations.
3. **Decision Maker Discovery**: `jh.contacts` identifies up to 3 contacts based on company size:
   - `< 30 employees`: Founder / CEO + Poster.
   - `30 - 200 employees`: Head of Function, Team Lead, Poster (CEOs strictly excluded).
   - `> 200 employees`: Team Lead / Hiring Manager + Recruiter (CEOs strictly excluded).
   Contacts are verified via MX records and tagged `Found`, `Pattern`, or `Guess`. Scraping LinkedIn people pages or harvesting GitHub emails is strictly blocked.
4. **Resume & Cold Email Generation**:
   - Job-specific 1-page PDF built strictly from master resume facts.
   - Cold email draft of 3-4 lines (40-80 words): 1 genuine detail, 1 verifiable proof point, 1 clear ask, and portfolio URL on the final line.
   - `jh.slop` audits text for forbidden AI cliches.
   - Sockets on SMTP ports 25, 465, and 587 are blocked; the MCP never sends emails directly.
   - Strict daily cap of 20 emails; ledger enforces a 90-day cooldown per contact and max 1 follow-up after 4 days.

### D. Classic Save & Application Track (P13, T16 - T17)
1. **Job Save**: User clicks Save on an active job posting.
2. **Liveness & Fit Gate**: Verifies posting is still open (skips generation and alerts user if dead). Warns if fit score < 60.
3. **Document Tailoring & Grounding Audit**: Generates tailored resume and cover letter. `jh.evidence.audit_grounding()` verifies that all employers, titles, dates, and technologies match the master resume. Ungrounded claims are rewritten or removed.
4. **ATS Autofill Extension**: Chrome extension populates verified candidate details into job application forms. Unknown or open-ended questions remain blank with a review flag. EEO responses default to "Decline to state". The extension never clicks the final submit button.

### E. Feedback, Coaching & Pipeline Synchronization (P17 - P20, T18 - T20)
1. **Coaching & Mock Interviews**: Triggers strictly on user request or inbound interview invite. Evaluates mock interview answers on a 0-10 rubric (Ownership, Metrics, Structure, Relevance) with verbatim answer quotes and actionable improvements.
2. **Gmail Tracker**: Minimal read-only OAuth scope (`gmail.readonly`) querying exclusively threads involving contacts registered in the outreach ledger.
3. **Digests & Metrics**: Daily digest reports new matches, pending follow-ups, and expiring jobs. Weekly report tracks outbound conversion rates by source and signal type.

---

## 4. Protected Code Invariants (AGENTS.md)
The following code regions are protected by cryptographic SHA256 hashes (`tests/test_protected_linkedin.py`):
- `jh/sources/__init__.py`: `LinkedInGuest` class & `LINKEDIN_GEO_MAP`.
- `jh/pipeline.py`: LinkedIn incremental scraper and radar (`LinkedIn incremental scraper` banner to `_enrich_bg_stop`).
- `jh/config.py`: `get_linkedin_scrape_depth` and `get_linkedin_incremental_minutes`.

External signatures called by these protected regions must remain strictly preserved:
`Source`, `make_job`, `http_get`, `html_to_text`, `dedup.job_key`, `_rank_opportunity`, `derive_target_roles`, `score_job_best`, and database functions (`get_profile`, `get_live_profiles`, `get_setting`, `set_setting`, `session`, `get_pending_jobs`, `get_pending_jobs_count`, `store_pending_jobs`, `get_saved_search_jobs`).
