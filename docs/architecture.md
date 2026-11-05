# Architecture

## Layers

```
MCP client (Claude Desktop, Cursor, ...)
        |  stdio, JSON-RPC
mcp_server.py            start-up, resume sync, FastMCP instance
jh/team/                 the CEO, five specialists and the Reviewer (see docs/team.md)
jh/mcp_tools.py          39 specialist tools and 7 read-only resources
jh/mcp_helpers.py        envelope, error handling, job cards, resolvers, tool registry
        |
jh/pipeline.py           search orchestration, scoring, caching, LinkedIn radar
jh/preferences.py        validated personal preferences (overlay on the resume)
jh/regions.py            countries, cities, which sources serve which place
jh/source_registry.py    one catalog of sources, skip rules, per-country call plans
jh/company_directory.py  starter list, watchlist, discovered boards, board health
jh/sources/              source classes (__init__), ATS adapters, feeds and APIs, local.py (site reader, regional boards)
jh/regional_boards.py, localize.py   local board catalog, local-language query variants
jh/scoring.py, skills.py, dedup.py, evidence.py, refit.py, ats.py, interview.py, screening.py, tracker.py
jh/db.py                 SQLite: profiles, stored jobs, applications, watchlist, settings
jh/util.py, source_policy.py   HTTP client, parsing helpers, outbound network policy
```

## One search, step by step

1. `pipeline.search` loads your preferences and overlays them on the resume profile. The stored resume is not changed.
2. `regions.resolve_targets` turns target countries, the location argument, and the resume location into country codes.
3. For each source, `source_registry.skip_reason` decides whether to run it. Skips are reported in the result.
4. `source_registry.plan` expands a source into calls: Indeed once per target country, Adzuna once per country, Bayt once per Middle East or North Africa country.
5. All calls run in a thread pool with a 35 second deadline. A failing source never blocks the rest. Results are cached per source and query. Three failures in a row pause a source (circuit breaker).
6. `company_directory.harvest` reads ATS links in the raw results and remembers new company boards.
7. Personal filters apply: excluded companies, maximum age, company focus.
8. `dedup.merge_jobs` merges the same job from several sources. `scoring` scores each job against every live resume and keeps the best.
9. The result carries per-source status and a `coverage` block, so an empty result explains itself.

## The team layer

`jh/team/` sits between the client and the tools. `register_team` runs last in `register_tools_and_resources`, takes the registry of specialist tools (each already wrapped in the envelope), and adds seven CEO tools. `TeamMCP.list_tools` filters what the client sees (surface `team` or `full`). It does not remove tools, so the CEO can still call them.

- `router.py`: request to intents and entities. Rule-based.
- `ceo.py`: plan, delegate, retry and widen, review, report. One handler per intent.
- `directives.py`, `roles.py`: the written brief for each task, the roster, and the owner of every tool.
- `qa.py`: the Reviewer. Pure functions, offline except `live_check`.
- `missions.py`: the `missions` table in `engine.db`.

## Company boards

`CompanyBoards` is one source with its own thread pool and a 25 second budget. It draws from three pools: your watchlist (always fetched, all roles), a short starter list, and discovered boards. The pool is limited per search (default 60), least recently fetched first. Each board keeps a health record in the `discovered_boards` table.

## Data stores

SQLite (`engine.db`) is the only store for resumes, jobs, applications, the watchlist and board health. `preferences.json` holds preferences. Generated documents go to `output/`. Nothing else is persisted.

## Extending

Add a source: subclass `Source` (or `_Board` for an ATS) in `jh/sources/`, add it to `SEARCH_SOURCES` or `BOARDS`, add a `SourceInfo` in `source_registry.py` with its regions, and add a fixture test. The catalog test fails if a source is missing from the registry.

Add a specialist tool: also add its name to exactly one `Role.tools` tuple in `jh/team/roles.py`. A test fails otherwise.

Add a tool: write a function in `register_tools_and_resources` with the `@tool` decorator and a docstring with an `Args:` section. Return a dict or a `Result`. Raise `ToolError` for fixable problems.

## Background workers

`pipeline.py` still holds the auto-search worker and the LinkedIn radar from the web-app version. The MCP server does not start them. The background enricher does run after a search, limited to the 60 best-scored jobs per search.
