# Changelog

## 2.4.0

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
