# Architecture (v2.0.0 — Hybrid Claude Desktop MCP Server)

## Layers

```
MCP client (Claude Desktop, Cursor, ...)
        |  stdio, JSON-RPC
mcp_server.py            start-up, resume sync, FastMCP instance
jh/team/                 CEO orchestrator, specialists and the Reviewer (see docs/team.md)
jh/mcp_tools.py          specialist tools and read-only resources (via CEO delegation or --surface full)
jh/v5_tools.py           Hybrid guided workflow (jh_begin, jh_confirm, jh_launch, jh_answer, jh_query, jh_build_resume, jh_find_contacts, jh_draft_email)
jh/mcp_helpers.py        envelope, error handling, job cards, resolvers, tool registry
        |
jh/pipeline.py           multi-board search orchestration, scoring, caching, LinkedIn radar
jh/signals.py            fresh hiring posts (<24h) and funding signals (<14d)
jh/contacts.py           size-tiered decision-maker contact discovery + MX verification
jh/email_drafter.py      concise anti-slop cold outreach drafting (never auto-sent)
jh/preferences.py        validated personal preferences (overlay on the resume)
jh/regions.py            countries, cities, which sources serve which place
jh/source_registry.py    catalog of sources, skip rules, per-country call plans
jh/company_directory.py  starter list, watchlist, discovered boards, board health
jh/sources/              source classes (__init__), ATS adapters, feeds and APIs, local.py
jh/scoring.py, skills.py, dedup.py, evidence.py, refit.py, ats.py, interview.py, screening.py, tracker.py
jh/store.py, jh/db.py    DB-free atomic JSON persistence (durable.json + cache.json) & in-memory workspace state
jh/util.py, source_policy.py   HTTP client, parsing helpers, outbound network policy
```

## Hybrid workflow, step by step

1. `jh_begin` loads and validates local resumes without guessing unconfirmed locations or roles, presenting at most the essential Step 3 target questions.
2. `jh_confirm` captures user target place/role and issues a 2-hour session ticket (`jh_confirm` -> `jh_launch`).
3. `jh_launch` starts headless multi-board search + Signal Radar + LinkedIn radar concurrently in Hybrid mode (`method="hybrid"`), never launching a separate web UI, HTTP daemon, or browser.
4. `jh_answer` updates live view filters (`work_mode`, `job_type`, `min_salary`, `industries`, exclusions) without restarting search, and returns Reviewer-verified (`qa.review_job`), fit-and-recency ranked compact job cards directly in chat.
5. Once the user selects specific jobs, `tailor_resume`, `cover_letter`, `jh_build_resume` (1-page PDF), `jh_find_contacts`, and `jh_draft_email` generate strictly resume-grounded application and outreach packages under human approval.

## Data stores

All workspace state is persisted atomically in JSON (`durable.json` for resumes/profiles, view filters, applications, outreach ledger, watchlist, settings; `cache.json` for cached search jobs, signals, and pending discoveries) managed by `jh/store.py`. Generated PDFs, tailored resumes, cover letters, and reports are stored under the user's home output directory (`~/Desktop/jobmcp/outputs/` or `JOBMCP_HOME/outputs/`). Zero SQLite (`.db`) files or external databases are used or created.

## Extending

- Add a source: subclass `Source` (or `_Board` for an ATS) in `jh/sources/`, add it to `SEARCH_SOURCES` or `BOARDS`, add a `SourceInfo` in `source_registry.py` with its regions, and add a fixture test.
- Add a specialist tool: add its name to exactly one `Role.tools` tuple in `jh/team/roles.py`.
- Add a tool: write a function in `register_tools_and_resources` with `@tool` and an `Args:` docstring section, returning a dict or `Result` and raising `ToolError` for fixable problems.
