# JobHunter MCP v2.0.0 — Repository Structure Map

## 1. System Architecture Overview
JobHunter is a pure **Claude Desktop MCP Server** executing the unified **Hybrid Workflow** without any separate Web UI, Chromium extension, local HTTP server, or SQLite database:
- **Headless Hybrid Discovery**: Searches 25+ job boards alongside fresh hiring signals (<24h posts, <14d funding news) and the LinkedIn radar, ranking opportunities by fit score and recency directly in chat after Reviewer QA verification.
- **User-Controlled Preparation**: Once the user selects specific roles, generates tailored resumes (including 1-page PDFs), cover letters, interview prep, MX-verified hiring-manager contacts, and anti-slop cold outreach drafts under strict daily limits and zero auto-submission.
- **DB-Free Persistence**: Uses atomic per-workspace JSON persistence (`durable.json` and `cache.json`) via `jh/store.py` and in-memory tables with zero `.db` files on disk.

---

## 2. Directory Layout

```
jobhunter/
├── jh/                          # Core Python MCP engine
│   ├── config.py                # Global configurations (Hybrid-only, TTL, caps, protected getters)
│   ├── home.py                  # Isolated home folder management (~/Desktop/jobmcp or JOBMCP_HOME)
│   ├── store.py                 # Atomic JSON + thread-safe in-memory store (zero .db files)
│   ├── db.py                    # Typed persistence facade & live query-time filters
│   ├── models.py                # Pydantic data schemas (Job, Profile, Signal, Contact, etc.)
│   ├── resume_checker.py        # Local resume validation (PDF, DOCX, TXT, cover letter/JD checks)
│   ├── resume_parser.py         # Multi-format resume extraction and structured parsing
│   ├── role_inference.py        # Role, skill cluster, and seniority inference
│   ├── interview_questions.py   # Guided Step 3 target-place + Round 2 filtering questions
│   ├── ticket_manager.py        # 2-hour session tickets & input validation
│   ├── worker_launcher.py       # Headless in-process background search worker
│   ├── v5_tools.py              # Hybrid workflow tools (jh_begin, jh_confirm, jh_launch, jh_answer, jh_query, jh_build_resume, jh_find_contacts, jh_draft_email)
│   ├── mcp_tools.py             # Specialist MCP tools & read-only resources
│   ├── mcp_helpers.py           # Result envelope, ToolError handling, job cards
│   ├── mcp_configurator.py      # Claude Desktop & Cursor MCP config registration
│   ├── preferences.py           # User preference storage & overlay
│   ├── scoring.py               # 0-100 match scoring, Safe/Match/Reach classification, gap reports
│   ├── refit.py                 # Truthful resume tailoring & interview prep
│   ├── exporters.py             # Clean 1-page PDF, DOCX, Markdown, TXT exporters + roundtrip check
│   ├── signals.py               # Signal ingestion & freshness filtering
│   ├── radar.py                 # LinkedIn radar polling & exponential backoff
│   ├── refresh_scheduler.py     # Adaptive source TTL refresh scheduler
│   ├── lifecycle.py             # Deduplication, liveness verification, 24h tombstones
│   ├── contacts.py              # Size-tiered decision maker discovery + MX verification
│   ├── email_drafter.py         # Concise anti-slop cold outreach drafts
│   ├── slop.py                  # Banned cliché detector
│   ├── outreach_ledger.py       # 90-day cooldown, 1 follow-up max, 20/day cap tracker
│   ├── save_flow.py             # Hybrid package generation (ATS docs + contacts/outreach)
│   ├── evidence.py              # Grounding audit against master resume facts
│   ├── screening.py             # Grounded screening question solver & EEO opt-out
│   ├── interview.py             # Mock interview & coaching evaluator
│   ├── digest.py                # Daily digest & weekly metrics reports
│   ├── gmail_tracker.py         # Read-only Gmail classifier (optional)
│   ├── sources/                 # Modular job board & ATS adapters (LinkedIn protected)
│   └── team/                    # CEO orchestrator, specialists, Reviewer QA, evals, voice linter
├── prompts/                     # Agent playbooks, document prompts & voice contract
├── agents/                      # Subagent definitions (jobhunter-runner.md)
├── docs/                        # Architecture, tool contracts, team, prompts, evals, MCP setup
├── tests/                       # Offline pytest suite, contract tests, E2E harness & fixtures
├── mcp_server.py                # FastMCP stdio entry point (--check, --workspace, --surface, --install-claude)
├── pyproject.toml               # PyPI packaging metadata (jobhunter-mcp v2.0.0)
└── AGENTS.md                    # Protected code hashes & verification rules
```
