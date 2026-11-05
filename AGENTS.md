# Notes for AI coding agents

This repository is a Python MCP server. There is no frontend here.

## Do not edit

These parts are protected by the owner. Do not change them, refactor them, or "fix" them.

- `LinkedInGuest` and `LINKEDIN_GEO_MAP` in `jh/sources/__init__.py`.
- The LinkedIn incremental scraper and radar in `jh/pipeline.py` (from the `LinkedIn incremental scraper` banner to `_enrich_bg_stop`).
- `get_linkedin_scrape_depth` and `get_linkedin_incremental_minutes` in `jh/config.py`.

`tests/test_protected_linkedin.py` compares these regions with stored hashes. If you think one needs a change, stop and ask the owner. Report problems you see there instead of fixing them.

Code that these regions call must keep its signature: `Source`, `make_job`, `http_get`, `html_to_text`, `dedup.job_key`, `_rank_opportunity`, `derive_target_roles`, `score_job_best`, and the `db` functions the radar uses (`get_profile`, `get_live_profiles`, `get_setting`, `set_setting`, `session`, `get_pending_jobs`, `get_pending_jobs_count`, `store_pending_jobs`, `get_saved_search_jobs`).

## Working rules

- Run `python -m pytest tests -q` before and after a change. The suite is offline.
- Tools only. Do not register MCP prompts. The role prompts in `prompts/team/` are files, not MCP prompts.
- Every specialist tool belongs to exactly one employee in `jh/team/roles.py`. `tests/test_team.py` fails otherwise.
- `tests/test_evals.py` is a gate. A change to `jh/team/qa.py`, `claims.py`, `safety.py` or `router.py` must not lower any score in `python -m jh.team.evals`. When a real fabrication or phrasing gets through, add it to `jh/team/evals.py` with a genuine counterpart, watch the test fail, then fix.
- Anything the team shows the client must pass through `jh/team/qa.py`. Do not report a job or a document that skipped the Reviewer.
- The Reviewer removes a job only on clear evidence (HTTP 404 or 410, expired job data, "no longer available" text). A blocked or script-heavy page is "not confirmed", never "dead".
- Every tool returns the envelope from `jh/mcp_helpers.py`. Raise `ToolError` for problems the caller must fix.
- Never return or accept API keys in a tool.
- New source: add a fixture in `tests/fixtures/`, a parser test, and a `SourceInfo` entry in `jh/source_registry.py`.
- Keep `stdout` clean. Log to stderr only, because stdout carries the protocol.
- No `abs(hash(...))` for IDs. Use `jh.util.stable_id`.
