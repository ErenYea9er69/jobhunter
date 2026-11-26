# Changelog

## 1.2.1

### Session Isolation, Signal Freshness & Grounded Project Matching
- **Exclusive TCP port & `/health` home ownership**: Closed split-brain port `8080` hijacking caused by Windows `SO_REUSEADDR` and foreign daemon reuse (`jh/worker_launcher.py`, `jh/httpd.py`), ensuring `jh_launch` binds only to an unoccupied port matching the active `JOBMCP_HOME`.
- **Extension multi-port discovery**: Closed extension disconnect on port `8080` (`extension/background.js`, `extension/content.js`, `extension/popup.js`) by probing active ports (`8080–8082`, `8765`) automatically.
- **Automatic stale unsaved-cache reset**: Closed leftover prior-candidate jobs, signals, filters, and radar timers polluting new searches (`jh/db.py`, `jh/v5_tools.py`, `jh/radar.py`), clearing unsaved search cache on resume switch while preserving user applications, outreach, and saved jobs.
- **Modern signal immediate catch-up & filtering**: Closed silent 20-minute radar cooldown skips on fresh `jh_launch` and loose signal filtering (`jh/v5_tools.py`, `jh/db.py`), kicking off a non-blocking Modern signal poll immediately and filtering signals by confirmed places, Step 5 languages, industries, and stages.
- **Grounded `relevant_projects` matching**: Closed missing project proof mapping on Save (`jh/scoring.py`, `jh/save_flow.py`, `webapp/`, `public/`), surfacing matching master-resume projects and concrete experience bullets without fabrication.
- **E2E test teardown hygiene**: Closed leaked detached `server.py` and test `chrome.exe` processes after pytest (`tests/e2e/test_suite.py`, `jh/worker_launcher.py`) via `JOBHUNTER_NO_BROWSER` enforcement and fixture teardown.

## 1.2.0

### Contract Place Rules (Steps 2–3)
- **Zero resume-guessed location**: Closed the gap where resume addresses, phone numbers, defaults, or profile fallbacks pre-filled or filtered `locations` (`jh/role_inference.py`, `jh/pipeline.py`, `jh/regions.py`), so only explicitly confirmed places can ever restrict results.
- **Explicit target-place ticket gate**: Closed the gap where skipping or omitting location still issued a launch ticket (`jh/interview_questions.py`, `jh/v5_tools.py`, `jh/regions.py`), so `jh_confirm` always asks for `remote only`, `worldwide remote`, or specific countries/regions plus optional city and refuses ticket issuance until answered.
- **Confirmed-place SQL filtering**: Closed loose region/country alias matching and mixed remote/country filters (`jh/regions.py`, `jh/db.py`), so Europe, South Asia, USA, France, Worldwide remote, Remote only, and multi-place choices filter accurately and update live via `jh_answer`.

### Job-Seeker Lessons A–E
- **Lesson A — Title families for search queries only**: Closed narrow single-title searches (`jh/role_inference.py`, `jh/v5_tools.py`) by expanding each inferred/confirmed role into up to ~5 related query variants kept strictly out of `view_filters["roles"]` so recall improves without filtering out valid matches.
- **Lesson A — Step 5 optional precision preferences**: Closed missing company-type targeting (`jh/interview_questions.py`, `jh/db.py`, `jh/v5_tools.py`) by adding optional live preference parsing and SQL filters for `industry`, `company_stage` (`startup`, `scale-up`, `public`), `market_served`, and `languages` without restarting running searches.
- **Lesson A — Built In SaaS source (Skipped)**: Skipped adding a Built In scraper because Built In's Terms of Use and Acceptable Use Policy (`builtin.com/terms-of-use`, `builtin.com/acceptable-use-policy`) explicitly forbid automated scraping/crawling and expose no public API, avoiding fragile non-compliant scraping while GreenHouse/Lever/Ashby/Remote/The Muse already cover SaaS postings.
- **Lesson B — Honest match check and soft vs hard gaps**: Closed opaque or conflated gap messages (`jh/scoring.py`, `jh/refit.py`, `jh/save_flow.py`, `webapp/`, `public/`) by surfacing `strengths`, non-blocking `soft_gaps` (e.g., 3 vs 4 years requested -> apply anyway), and `hard_gaps` (work authorization, citizenship, clearance, required license) on Save so weak matches are transparent without hiding jobs.
- **Lesson B — Truthful tailored ordering & hype scrubbing**: Closed generic bullet order and residual buzzwords (`jh/refit.py`, `jh/save_flow.py`, `jh/email_drafter.py`) by ordering relevant experience first, stripping inflated hype in both structured PDFs and plain-text outputs, and preserving exact master resume dates, titles, and numbers.
- **Lesson C — Structured interview prep, talking points & Glassdoor links**: Closed shallow prep and unlinked reputation checks (`jh/refit.py`, `jh/interview.py`, `jh/company_research.py`) by adding `tell_me_about_yourself` story drafts, `recruiter_screen`, `hiring_manager_round`, `peer_round`, Modern brief `talking_points`, and unscraped Glassdoor search URLs (`scraped: False`).
- **Lesson C — Optional `practice_interview` coach tool**: Closed missing active Q&A rehearsal (`jh/mcp_tools.py`, `jh/team/roles.py`) by adding `practice_interview` under the `coach` role that asks saved-prep questions and grades user answers only after prep output exists, leaving all existing tool contracts untouched.
- **Lesson D — Confirmed-only side work and contract facts**: Closed omitted bridge/contract work cleanly without hallucination (`jh/interview_questions.py`, `jh/v5_tools.py`, `jh/db.py`, `jh/save_flow.py`, `jh/exporters.py`, `jh/evidence.py`) by capturing `side_work` in `confirmed_facts` and rendering `"Contract and Side Work"` in tailored resumes/PDFs exclusively when user-confirmed.
- **Lesson E — Pacing note**: Added one plain factual sentence (`pacing_note`) in `jh_status` reminding candidates that wait times often reflect budget timing and hiring pauses rather than fit, adding zero UI clutter or cheerleading.

### Bug Fixes Found During Verification
- Fixed `jh/role_inference.py` reading `job.get("title")` only (ignoring parsed `job.get("role")`), `jh/v5_tools.py` `years_experience` key mismatch in `profile_line`, `jh/save_flow.py` passing `job` dict instead of `job_id` string to `lifecycle.liveness_check`, `jh/httpd.py` `/api/jobs/query` not persisting UI filter updates directly, and `jh/v5_tools.py` negation regex false positives on `excluded_keywords` / `level_shift`.
- Fixed human-chat findings in `v1.2.0`: `jh_begin({})` now prompts the user to pick when multiple resumes exist in workspace/resumes (`jh/v5_tools.py`); `parse_confirmed_places` preserves cities alongside USA and tolerates common place/method typos (`jh/regions.py`, `jh/v5_tools.py`); `jh_answer` parses `"min salary N"` accurately and avoids false `internship` matches on `"company stage"`; `outreach_ledger` and `email_drafter` enforce the 20/day cap across both `jh_draft_email` and `mark_outreach_sent`; `jh_build_resume` invalidates stale cached PDFs when confirmed `side_work` changes; `ceo_delegate` reviews single-job `get_job_details`; `claims.check` detects dropped-pronoun claims; `db.store_jobs` avoids `job_key` collisions; and `screening` never outputs generic boilerplate on PII/fact questions (`email`, `SSN`, `clearance`).

### Standards & Verification Sources
- Verified Python MCP stdio/stderr isolation and schema conventions against [Model Context Protocol Docs](https://modelcontextprotocol.io/docs/develop/build-server).
- Verified PEP 621 / PEP 517 build, wheel validation, TestPyPI, and Twine publishing workflow against [PyPA Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/).

## 1.1.2

### UI / UX & Browser Polish (Impeccable & Chrome First-Run Fixes)
- **Dialog Stacking & Styling (UI/UX)**: Re-structured `<dialog>` tags to isolate `.dialog-body` inside inner containers and enforced `dialog:not([open]) { display: none !important; }`, permanently preventing un-opened modals from rendering in the flow.
- **Elevation, Backdrops & Transitions**: Added backdrop blur (`backdrop-filter: blur(8px)`), modal scale-in animations, centered elevation, and deep slate theme styling (`#0a0b0e`/`#13151c`).
- **Drag-and-Drop Resume Upload**: Replaced crude browser native file input with a modern drag-and-drop dropzone with format pills, file size indicator, clear button, and base64 binary upload to `/api/resumes/upload` to avoid raw string corruption.
- **Empty State & Scrollbar Polish**: Centered empty states with pulse icon wrap and contextual action buttons (Reset filters, Switch to Classic). Replaced default browser scrollbars with themed subtle scrollbars.
- **Chrome First-Run Suppression**: Merged `Preferences` (`signin.allowed=false`, `sync_promo.user_skipped=true`) and appended `--disable-features=SyncPromo,SignInProfileCreationDesktop,ChromeWhatsNewUI` and `--password-store=basic` to eliminate "Connectez-vous à Chrome" screen on launch.

## 1.1.1

### Fixed
- **Browser Launch (D7)**: Suppressed Google Chrome first-run experience (FRE) and sign-in onboarding prompt by touching `First Run` sentinel, setting `Preferences` (`signin.allowed=false`, `sync_promo.user_skipped=true`), and adding flags `--no-first-run`, `--no-default-browser-check`, `--disable-fre`, `--disable-search-engine-choice-screen`.

## 1.1.0

### V7 Ask-First Flow & Guard Enforcements (D1 to D12)
- **Session State Machine (D1)**: Strict server-side state machine (`NEW`, `RESUME_OK`, `ASKED`, `ANSWERED`, `LAUNCHED`, `ROUND2_DONE`). Any out-of-order tool call returns `needs_input` with pending questions. Tools and search aliases require valid 2-hour tickets bound to session and resume.
- **Audit Logging & Reply Validation (D2)**: Added `audit_log` table storing raw user words and timestamps. Rejects user replies under 2 characters, echoes of questions, or submitted under 5 seconds from question presentation.
- **Guesses vs Answers Separation (D3)**: Separated DB storage into `guesses` (inferred from resume/filename with confidence scores) and `answers` (explicit user input). Scrapers and filters strictly query `answers`; inferred roles with confidence >= 0.5 define initial scope only.
- **Mandatory Round 1 Questions & Source Routing (D4)**: Round 1 prompt starts with `"STOP. Ask the user the questions below and wait for the answer. Do not call another tool."` Routing respects location: Tunisia exclusively queries MENA/Tunisia boards and ATS feeds without unrequested global remote clutter.
- **Modern vs Classic Execution Branching (D5)**: Modern starts Signal Radar (funding & hiring posts), Classic launches multi-board job search. Session stores method and supports live switching.
- **Detached Background Worker & Zero Job Cards in Chat (D6)**: `jh_launch` detaches process in under 3 seconds using `DETACHED_PROCESS` / `CREATE_NEW_PROCESS_GROUP`. Removed job cards (titles, companies, links, scores) from all tool responses; jobs travel exclusively from SQLite DB to Web UI over HTTP.
- **Dedicated Chromium Session & UI Ping (D7)**: Dedicated browser profile in jobmcp home with ATS autofill extension. `/api/ping` tracks `ui_seen` and issues one-time `page_token`.
- **Live Filtering & Round 2 Questions (D8)**: Pending questions returned in `ask_user` until answered; answers apply live database view filtering without restarting background scrapers.
- **Visa Warning Flagging (D9)**: International on-site roles are flagged with "work rights not confirmed" instead of silent exclusion before visa preference answer.
- **UI Save Guard for Document Generation (D10)**: `tailor_resume`, `cover_letter`, `outreach_message` require jobs to have `saved_by = 'ui'`. Save button in Web UI signs requests using `page_token`.
- **Suppressed Proactive Coaching Offers (D11)**: Coaching and tracking tools run on explicit user demand only.
- **Profile Line & Concise Status (D12)**: Server generates a single-line summary (`profile_line`) with roles, confidence, experience, and top skills, followed by clean post-launch status.

## 1.0.0

A review of every prompt (`docs/prompts.md`).

### Fixed
- Six of eight playbooks asked a model for keys the code does not read, so with a model key the reply was dropped. The cover letter asked for `letter_text` (the code reads `full_text`), the mock evaluator for `total_score` (the code requires `overall_score`), outreach and follow-up nested their message under `draft_text` (the code reads top-level `linkedin_connection_note` and `body`), interview prep and the roadmap used other names, and screening asked for `answer_text` (the code reads `answer`; the whole JSON object could land in a form field). All eight now match, and `tests/test_prompt_contract.py` feeds each code path a reply built from its playbook's own schema.
- The embedded prompts in code (`LLM_SYSTEM`, `COVER_PITCH_LLM_SYSTEM`, `SCREENING_SOLVER_PROMPT`) were rewritten. Their text only. Each keeps the reply keys of its own code path.

### Prompts
- Removed persona boasting, "2026/2027 standard", invented statistics (the 6-second scan, a 95% ATS match, rejection in 5 seconds), self-reported scores and counts, example values in schemas, evidence ids that could not be produced, and the dead "User Message Template" sections.
- Added a single style guide (`prompts/voice.md`). Its `<voice>` block is embedded in every playbook, the Writer prompt and the Coach prompt. Rules name patterns and give a plain alternative, because word bans alone drift to synonyms.
- Each playbook now has the same skeleton (role, inputs, grounding, how to write, voice, examples, output). Examples come in robotic and plain pairs, drawn from finance, teaching and operations as well as software.
- Every playbook serves two modes: JSON when the user message is JSON, plain text when a person reads it. Every schema ends in `missing_inputs`, so the model asks instead of leaving a placeholder.
- Scoring in the mock evaluator has anchors for each band and uses the code's 0 to 100 scale. Follow-up and negotiation no longer ask for market data or competing offers. The roadmap's interview script has a "Now" line that is true today and an "After the project" line. The LinkedIn note limit is 200 characters.
- The CEO prompt tells the AI how to speak to the client and to pass `hints.intent` and `hints.reference`.

### Style checking
- `jh/team/voice.py` finds machine-sounding patterns (openers, hype, stock adjectives, vague power verbs, grand framing, hollow closers, "not just X, but Y", dashes, emoji and markdown in form text). Technical uses such as "financial leverage" are not flagged.
- The Reviewer reports them as a `robotic_style` warning with the phrase and the plain alternative. It does not block.
- `python -m jh.team.voice <file>` lints a prompt file. `tests/test_prompts.py` lints all prompt files, the prompts in code and the tool descriptions.
- Style evals: dev 17 of 17 flagged, 0 of 16 plain flagged. Blind first pass: 10 of 12 flagged, 0 of 10 plain flagged.

### Not changed
- The deterministic templates in `refit.py`, `tracker.py` and `screening.py` still contain some of the patterns, which the Reviewer now flags (see `docs/prompts.md`).
- No model was run. The tests prove the contract and the static properties, not how a given model writes.
- Prompt length grew from 2,715 to 6,126 words across the eight playbooks. About 1,500 words are the voice block repeated.

## 2.3.0

Found by measuring version 2.2 on fixed cases (`docs/evals.md`): the Reviewer caught 12 of 22 fabrications, the job checks got 6 of 12 right, and the router got 18 of 40. This version fixes what that showed.

### Reviewer
- New claims engine (`jh/team/claims.py`). It checks each sentence the candidate would sign: employers, titles, leadership, degrees, skills stated as experience, numbers and years, certifications, awards, talks, publications, clearance, founding or acquisition, languages and status, and facts about the employer. Version 2.2 let an invented employer, degree, certification and job title through.
- New safety checks (`jh/team/safety.py`): scam postings (upfront fees, deposits, cheque scams, requests for ID or bank details, chat-app-only contact), prompt injection in posting text, URL shorteners and odd domains. Honest postings that mention fees, equipment or visas are not flagged. Scam exposure grows with the new small-board sources, so this matters.
- A blocked draft is repaired sentence by sentence. If repair would delete more than a third of it, it is rejected instead.
- The Reviewer fails closed: a crashed document check blocks the document. A crashed job check warns.
- Fixed a false alarm: a degree line and some date lines were blocked as unsupported.
- Fixed two bugs found while testing: the preposition pattern for employers was case-sensitive, and the month in a date ("2021-12") counted as the number 12.

### Router and CEO
- The router reads 14 intents, in English, French and some Arabic. New: explain, track, feedback, saved, export, unclear. It extracts job pointers ("the second one", "the Adyen job"), the stage of an application, exclusions, target countries and export format.
- The AI can state the intent (`hints.intent`) and the pointer (`hints.reference`). The router is the fallback. An unmatched request makes the CEO ask, with a menu of what it can do.
- Pointers are resolved against the last list, the tracker and stored jobs. Two matches make the CEO ask.
- Changes to your tracker and preferences are read back before they are reported as done.
- The shortlist is ranked before it is checked. No source fills more than 40% of it. Small-employer mode favours small sources.
- Reflection: findings from the numbers in a result, each with evidence and a next move. A weak search triggers the Coach's skill roadmap. If regional boards return nothing, the Scout checks why.
- The answer is a short `brief`. The long `report` is the audit trail.
- A time budget (default 50 seconds). The CEO stops widening, skips live checks and gap reports when time is short, and says so. Search widening no longer repeats a full fresh read at every step.
- All posting text in reports is made safe: one line, bounded, no hidden characters. `ceo_delegate` removes scams and injected postings from job lists.
- `ceo_status` shows the Reviewer's running record and can delete stored missions (`forget`). Only the newest 200 missions are kept.
- `hints` may be a JSON string.

### Evals
- `python -m jh.team.evals` and `tests/test_evals.py`. Dev, held-out and a second round. Results and how far to trust them are in `docs/evals.md`.
- First pass on a blind round written after the build: router 13 of 20, documents 9 of 10 caught, jobs 4 of 6. The general causes were fixed. The numbers in the tables are higher than what to expect on new text.

### Unchanged
- The LinkedIn scraper and radar. The protection test passes.

## 2.2.0

### Added: the team
- The AI you talk to is the CEO. `ceo_run` takes any request, writes a directive for each employee (Scout, Analyst, Writer, Coach, Chief of Staff), runs their tools, and reports. Six more CEO tools: `ceo_plan`, `ceo_delegate`, `ceo_submit_work`, `ceo_recheck`, `ceo_status`, `ceo_team`.
- The Reviewer checks every result before it reaches the client: job fields, apply link, dates, target country, duplicates, matched-skill claims, live posting pages, resume grounding, resume header lines against the profile, placeholders. Unsupported lines are removed and re-checked. Invented employers, degrees and numbers are blocked.
- Empty or failed steps are retried, then widened in steps. The report lists every attempt and never fills a gap.
- Every job and document carries the tool call that made it. Reports list what was not verified.
- Work orders: the CEO can hand the client's model a briefed writing task and check the draft with `ceo_submit_work`.
- Role prompts in `prompts/team/`, replaceable per workspace.
- `--surface team|full` (also `JH_SURFACE`). `team` is the default and shows seven tools. `full` shows all 46.
- New table `missions` in `engine.db`.

### Added: more jobs from small and regional employers
- Site reader: reads any site that publishes schema.org JobPosting data, finds job pages through sitemaps and page links, obeys `robots.txt`.
- Sources: Regional Boards (catalog for TN, MA, DZ, EG, NG, KE, ZA), Job Sites (your own), Jooble (key), JobTech (Sweden), Pinpoint (ATS).
- `add_job_source(kind="site")` and `discover_job_source(url)`.
- Local-language query variants (French, German, Spanish, Portuguese, Italian), used only by the new sources.

### Changed
- The server instructions describe the CEO protocol.
- `make_tool_decorator` keeps a registry of wrapped tools, so code can call tools without going through MCP.
- The LinkedIn scraper and radar are unchanged. The protection test passes.

### Not verified
- Jooble, JobTech, Pinpoint and the regional boards were written from public documentation and standards. They were not run against live servers. Tests use fixtures.

## 2.1.0

### Fixed
- Fresh installs crashed at start: `mcp[cli]>=1.0.0` pulled mcp 2.x, which has no `mcp.server.fastmcp`. Pinned to `>=1.9,<2`. Added the missing `curl_cffi` and `pypdf` requirements.
- API keys leaked to the model: the `jobhunter://config` resource and `configure` returned stored keys. Secrets are now never accepted or returned.
- The SSRF check never ran: `http_get` accepted any dotted host and never resolved DNS. Public names that point at private addresses are now blocked, including on redirects and page enrichment.
- Job IDs from Bayt, Himalayas and Naukri used Python's per-process `hash()`, so saved jobs duplicated after every restart. They use a stable hash now.
- `tailor_resume` reported `ats_after: 0` (it scored the wrapper, not the resume) and ignored `archetype`.
- `cover_letter` returned the Python repr of a dict as the letter.
- `get_recommendations` returned the number of dict keys as `count`.
- `search_jobs` read a `telemetry` key that did not exist, so failed sources were invisible, and it reported success with zero results when every source failed.
- `db.get_job` did not exist, so `solve_screening_questions(job_id=...)` always failed.
- One-line postings ("Required: ... Nice to have: ...") weighted every skill as optional.
- Salary written in prose was ignored; TND, MAD, EGP, AED, SAR and other currencies were not recognised; "Europe" matched EUR.
- Bayt matched "Romania" as Oman.
- Application records lived in two stores that only met at start-up. SQLite is now the only store.
- The one-click bundle used the wrong argument order and a key that did not exist.
- The background enricher fetched every stored job in a loop. It now handles the 60 best per search.
- Two functions named `cover_letter` and `interview_prep` existed as both tool and prompt.

### Added
- Personal preferences (`get_preferences`, `set_preferences`) with validation.
- Region-aware source selection. Indeed runs on each target country's local site.
- Company boards: Recruitee, Personio, Teamtailor, BambooHR, Breezy, Lever EU.
- `add_job_source` and `remove_job_source`: companies, feeds, career pages. `list_job_sources`.
- Snowball discovery of company boards from job links, with board health tracking.
- Sources: Working Nomads, The Muse, Arbeitsagentur, custom feeds, career pages. Hacker News reads three pages.
- Tools: `get_job_details` by `job_id`, `verify_draft`, `get_evidence`, `prepare_application`, `skill_roadmap`, `follow_up_message`, `get_playbook`.
- A single result envelope on every tool. Compact job cards.
- 166 offline tests, including a guard for the protected LinkedIn code.

### Changed
- The 8 MCP prompts are gone. `get_playbook` returns the same instructions plus the facts to write from.
- `daily_digest` lists new jobs from earlier searches and marks them reported.
- Documentation now matches the code, including the network policy.

### Removed
- Twelve unused adapter files, the demo mode, the SMTP digest scheduler, the browser bookmarklet autofill (including `execute_easy_apply`, which marked jobs as applied before you applied), `normalization.py`, `schemas.py`, unused models, the `.continue/` folder, the `skills/` folder and the UI-design `AGENTS.md`.
