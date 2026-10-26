# JobHunter New Logic & MCP Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete revised architecture and MCP contracts specified in [newall-logic.md](file:///c:/Users/hp/Desktop/jobhunter/newall-logic.md), expanding the MCP server to 27 tools, 7 context resources, 8 versioned prompt contracts, modular source adapters (`jh/sources/`), an incremental resume registry, 5-stage deduplication, and a structured test suite (`tests/unit/`, `tests/integration/`, `tests/contracts/`, `tests/security/`).

**Architecture:** 
Decompose the monolithic source and engine logic into single-responsibility modules: `jh/resume_registry.py` for incremental hash tracking, `jh/normalization.py` for canonical job creation, `jh/freshness.py` for job status checks, `jh/interview.py` for mock interview evaluations, and `jh/sources/` package for modular source adapters while protecting the LinkedIn scraper boundary. Expose the full 27 tools, 7 resources, and 8 prompt templates in `jh/mcp_tools.py` under the standardized 1.0 JSON result envelope. Keep `jh/sources.py` as a backward-compatible facade so legacy code continues to work seamlessly.

**Tech Stack:** Python 3.14, FastMCP 4 (MCP 2026-07-28 standard), SQLite WAL + FTS5, Pydantic v2, PyPDF/python-docx/txt parsers, pytest.

**Spec:** [newall-logic.md](file:///c:/Users/hp/Desktop/jobhunter/newall-logic.md)

---

## Global Constraints

- Never invent a skill, employer, role, qualification, date, project, result, or metric (Section 3.1).
- STDIO remains the default local transport; write protocol messages only to stdout, logs to stderr (Section 4.1).
- Tool envelope format: `{"status": "ok | partial | needs_review | error", "success": bool, "data": dict, "warnings": list, "sources": list, "correlation_id": str, "schema_version": "1.0"}` (Section 4.3).
- The existing LinkedIn scraper implementation and output path remain unchanged; `linkedin_adapter.py` is strictly an adapter boundary (Section 7.3).
- Preserve source attribution and source-specific apply links without modification (Section 7.4).
- 100-point explainable fit score weights: Skills 35, Responsibilities 25, Seniority 15, Domain 10, Work conditions 10, Compensation 5 (Section 10.2).
- Eligibility checks are separate from fit score: `met`, `not_met`, or `unknown` (Section 10.1).
- Duplicate resolution uses 5 stages: Provider identity, Canonical URL, Employer+role key, Description fingerprint, Merge decision (Section 9.1).
- MCP surface must expose exactly 27 tools, 7 context resources, and 8 prompt contracts (Sections 17, 18, 19).

---

## Review Focus

1. **Missing salary/seniority fields:** Must not produce a 0 score or negative eligibility; returns `unknown` and scores on available dimensions (Section 10.2).
2. **Untrusted job description prompt injection:** AI document generation must not execute tool calls or alter configuration based on text in job descriptions (Section 13.4).
3. **Application URL integrity:** Never overwrite a source-mandated application link with a generic ATS link (Section 9.1).
4. **Incremental re-parse performance:** Only files with changed SHA-256 hashes re-parse at startup or during `scan_resumes` (Section 6.2).
5. **Standardized result envelope:** All 27 tools must consistently return `schema_version: "1.0"`, `correlation_id` (12 hex chars), and valid `status` (Section 4.3).

---

## Task Decomposition

### Task 1: Result Envelope & Schema Updates
**Files:**
- Modify: `jh/models.py`
- Modify: `jh/schemas.py`
- Modify: `jh/mcp_tools.py:34-56`
- Test: `tests/unit/test_schemas_and_envelope.py`

**Interfaces:**
- Consumes: `jh.util.now_iso`
- Produces: `_tool_envelope(status, data, warnings, sources_used, correlation_id, schema_version="1.0") -> dict`

- [ ] **Step 1: Write unit tests for standard result envelope and input schemas**
  Create `tests/unit/test_schemas_and_envelope.py` testing envelope structure (`status`, `success`, `data`, `warnings`, `sources`, `correlation_id`, `schema_version == "1.0"`), validation of new tool parameters (`variant_name`, `force_reparse`, `refresh`, `questions`, `rubric`, `channel`).
- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m pytest tests/unit/test_schemas_and_envelope.py -v`
  Expected: FAIL (missing module / fields).
- [ ] **Step 3: Update `jh/models.py`, `jh/schemas.py`, and `_tool_envelope`**
  Add `schema_version: str = "1.0"` to tool envelopes and outcome models; add validators for `solve_screening_questions`, `evaluate_mock_interview`, and `daily_digest`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m pytest tests/unit/test_schemas_and_envelope.py -v`
  Expected: PASS.

---

### Task 2: Incremental Resume Registry (`jh/resume_registry.py`)
**Files:**
- Create: `jh/resume_registry.py`
- Modify: `jh/workspace.py`
- Test: `tests/unit/test_resume_registry.py`

**Interfaces:**
- Consumes: `jh.workspace.discover_resumes`, `jh.workspace.parse_resume_variant`, `jh.util.sha256_file`
- Produces: `ResumeRegistry.scan_and_sync(workspace_dir: Path, force: bool = False) -> dict`

- [ ] **Step 1: Write unit tests for ResumeRegistry**
  Create `tests/unit/test_resume_registry.py` testing:
  - Detection of resume variants in workspace.
  - Content hash tracking and manifest caching (`.jobhunter/resume_manifest.json`).
  - Incremental re-parse: skips unchanged file hashes unless `force_reparse=True`.
  - Active variant setting and retrieval.
- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m pytest tests/unit/test_resume_registry.py -v`
  Expected: FAIL (`jh.resume_registry` not found).
- [ ] **Step 3: Implement `jh/resume_registry.py`**
  Implement `ResumeRegistry` with manifest persistence, content hashing, incremental scan logic, and active variant tracking.
- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m pytest tests/unit/test_resume_registry.py -v`
  Expected: PASS.

---

### Task 3: Canonical Job Normalization & Freshness Lifecycle (`jh/normalization.py` & `jh/freshness.py`)
**Files:**
- Create: `jh/normalization.py`
- Create: `jh/freshness.py`
- Test: `tests/unit/test_normalization_and_freshness.py`

**Interfaces:**
- Consumes: `jh.util` (sanitizers, clean text, currency extraction)
- Produces:
  - `normalization.build_canonical_posting(raw_data: dict, source_name: str) -> dict`
  - `freshness.evaluate_freshness(job: dict, max_age_days: int = 30) -> str` (`"open"`, `"closed"`, `"stale"`, `"unknown"`)

- [ ] **Step 1: Write unit tests for Normalization and Freshness**
  Create `tests/unit/test_normalization_and_freshness.py` testing:
  - Canonical field extraction: title, company, clean salary, currency, remote/hybrid/onsite, employment type.
  - Preservation of separate `source_url` and `apply_url`.
  - Freshness state evaluation based on publication date, last-verified date, and explicit closure markers.
- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m pytest tests/unit/test_normalization_and_freshness.py -v`
  Expected: FAIL (`jh.normalization` not found).
- [ ] **Step 3: Implement `jh/normalization.py` and `jh/freshness.py`**
  Implement canonical posting builder and freshness lifecycle handlers.
- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m pytest tests/unit/test_normalization_and_freshness.py -v`
  Expected: PASS.

---

### Task 4: 5-Stage Duplicate Resolution & 100-Point Explainable Scoring Alignment
**Files:**
- Modify: `jh/dedup.py`
- Modify: `jh/scoring.py`
- Test: `tests/unit/test_dedup_and_scoring.py`

**Interfaces:**
- Consumes: `jh.normalization.build_canonical_posting`, `jh.skills`
- Produces:
  - `dedup.resolve_duplicates_5stage(postings: list[dict]) -> tuple[list[dict], list[dict]]`
  - `scoring.calculate_composite_fit(candidate_profile: dict, job: dict) -> dict` with 100-point weights (35/25/15/10/10/5) and separate `eligibility`

- [ ] **Step 1: Write unit tests for 5-stage dedup and 100-point scoring**
  Create `tests/unit/test_dedup_and_scoring.py` testing:
  - Stage 1: Provider ID match.
  - Stage 2: Canonical source URL match.
  - Stage 3: Employer + role key match.
  - Stage 4: Description fingerprint match.
  - Stage 5: Merge decision: retain all source links without overwriting apply URLs.
  - Scoring: 35/25/15/10/10/5 dimension weights, data completeness, candidate coverage, and separate eligibility (`met`, `not_met`, `unknown`).
- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m pytest tests/unit/test_dedup_and_scoring.py -v`
  Expected: FAIL on specific assertion checks.
- [ ] **Step 3: Update `jh/dedup.py` and `jh/scoring.py`**
  Align deduplication stages and weighted fit score formulas with Section 9.1 & 10.2 of `newall-logic.md`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m pytest tests/unit/test_dedup_and_scoring.py -v`
  Expected: PASS.

---

### Task 5: Modular Source Adapters (`jh/sources/`) with Protected LinkedIn Boundary
**Files:**
- Create: `jh/sources/__init__.py`
- Create: `jh/sources/base.py`
- Create: `jh/sources/linkedin_adapter.py`
- Create: `jh/sources/greenhouse.py`
- Create: `jh/sources/lever.py`
- Create: `jh/sources/ashby.py`
- Create: `jh/sources/smartrecruiters.py`
- Create: `jh/sources/jobicy.py`
- Create: `jh/sources/himalayas.py`
- Create: `jh/sources/adzuna.py`
- Create: `jh/sources/usajobs.py`
- Create: `jh/sources/remotive.py`
- Create: `jh/sources/jooble.py`
- Create: `jh/sources/workable_account.py`
- Modify: `jh/sources.py` (backward-compatibility shim exporting all adapter functions)
- Test: `tests/contracts/test_source_adapters.py`

**Interfaces:**
- Consumes: `jh.source_policy.check_url`, `jh.util.http_get`, `jh.util.http_get_json`
- Produces: `BaseSourceAdapter` with `search`, `get_details`, `check_status`, `health_check`

- [ ] **Step 1: Write contract tests for source adapters**
  Create `tests/contracts/test_source_adapters.py` verifying each adapter satisfies `BaseSourceAdapter` contract, handles pagination/filtering, validates URLs via `source_policy`, and preserves LinkedIn scraper output untouched.
- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m pytest tests/contracts/test_source_adapters.py -v`
  Expected: FAIL (`jh.sources.base` not found).
- [ ] **Step 3: Implement `jh/sources/` package and adapters**
  - Implement `base.py` with `BaseSourceAdapter`, `SourcePage`, `SourceJob`, `StatusBatch`, `SourceHealth`.
  - Implement direct ATS adapters (`greenhouse`, `lever`, `ashby`, `smartrecruiters`).
  - Implement aggregators (`jobicy`, `himalayas`, `adzuna`, `usajobs`, `remotive`, `jooble`, `workable_account`).
  - Implement `linkedin_adapter.py` strictly wrapping existing LinkedIn output.
  - Maintain `jh/sources.py` as facade re-exporting functions to ensure zero breakage of existing callers.
- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m pytest tests/contracts/test_source_adapters.py -v`
  Expected: PASS.

---

### Task 6: Interview Evaluation & Mock Interview Engine (`jh/interview.py`)
**Files:**
- Create: `jh/interview.py`
- Test: `tests/unit/test_interview.py`

**Interfaces:**
- Consumes: `jh.models`, `jh.prompts`
- Produces:
  - `generate_interview_prep(job: dict, profile: dict, interview_type: str = "all") -> dict`
  - `evaluate_mock_interview(question: str, candidate_answer: str, role_level: str = "senior", rubric: str = "standard") -> dict`

- [ ] **Step 1: Write unit tests for interview evaluation**
  Create `tests/unit/test_interview.py` testing:
  - Generation of technical, system-design, behavioral questions with STAR outlines.
  - Practice answer evaluation: scoring correctness, depth, structure, relevance, and communication.
  - Distinguishing weak explanation from missing verified experience.
- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m pytest tests/unit/test_interview.py -v`
  Expected: FAIL (`jh.interview` not found).
- [ ] **Step 3: Implement `jh/interview.py`**
  Implement prep generation and mock answer evaluator following `mock_interview_evaluator.md`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m pytest tests/unit/test_interview.py -v`
  Expected: PASS.

---

### Task 7: Full 27 Tools, 7 Resources, and 8 Prompt Contracts Registration
**Files:**
- Modify: `jh/mcp_tools.py`
- Modify: `mcp_server.py`
- Align: `prompts/` filenames (`resume_tailor.md`, `cover_letter.md`, `interview_prep.md`, etc.)
- Test: `tests/integration/test_mcp_tools_catalog.py`

**Interfaces:**
- Consumes: All `jh.*` workflows
- Produces: Complete FastMCP tool, resource, and prompt registration

- [ ] **Step 1: Write integration tests for all 27 tools, 7 resources, and 8 prompts**
  Create `tests/integration/test_mcp_tools_catalog.py` verifying:
  - Exactly 27 tools registered and callable.
  - All 7 resources registered (`jobhunter://resumes`, `jobhunter://resumes/{name}`, `jobhunter://evidence/{name}`, `jobhunter://applications`, `jobhunter://jobs/latest`, `jobhunter://config`, `jobhunter://sources`).
  - All 8 prompt templates registered on `@mcp.prompt()`.
  - All responses contain standard 1.0 envelope with correlation ID.
- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m pytest tests/integration/test_mcp_tools_catalog.py -v`
  Expected: FAIL (missing tools/resources/prompts).
- [ ] **Step 3: Implement missing tools, resource, and prompts in `jh/mcp_tools.py`**
  - Add missing tools: `solve_screening_questions`, `evaluate_mock_interview`, `daily_digest`.
  - Add missing resource: `jobhunter://evidence/{name}` returning structured evidence ledger.
  - Add `@mcp.prompt()` registration for all 8 prompts.
  - Ensure prompt files in `prompts/` match names: `resume_tailor.md`, `cover_letter.md`, `interview_prep.md`, `screening_question_solver.md`, `recruiter_outreach.md`, `mock_interview_evaluator.md`, `career_skill_roadmap.md`, `application_follow_up.md`.
  - Update `mcp_server.py` lifecycle to integrate `ResumeRegistry`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m pytest tests/integration/test_mcp_tools_catalog.py -v`
  Expected: PASS.

---

### Task 8: Security Tests & Regression Verification
**Files:**
- Create: `tests/security/test_security_policies.py`
- Test: Full test suite (`tests/`)

**Interfaces:**
- Consumes: `jh.source_policy`, `jh.workspace`
- Produces: Verified security gates

- [ ] **Step 1: Write security tests**
  Create `tests/security/test_security_policies.py` testing:
  - SSRF protection against loopback (127.0.0.1, ::1), private ranges (10.0.0.0/8, 192.168.0.0/16, 172.16.0.0/12), AWS/GCP metadata IP (169.254.169.254).
  - Path traversal protection (e.g. `../../etc/passwd`).
  - Sensitive data redaction in error envelopes.
- [ ] **Step 2: Run test to verify it passes**
  Run: `python -m pytest tests/security/test_security_policies.py -v`
  Expected: PASS.
- [ ] **Step 3: Run entire test suite (all unit, integration, contract, security, and legacy tests)**
  Run: `python -m pytest tests/ -v`
  Expected: 100% PASS with 0 failures.

---

## Execution Handoff

Please review this implementation plan. Does it capture what you want, and should we proceed with Native execution in this session?
