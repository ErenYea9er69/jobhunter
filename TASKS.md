# JobHunter Target Behavior Verification & Engineering Task Board

_Authority: Prompt & Target Behavior Specification (T1 to T20)_  
_Status: BACKEND COMPLETE (20/20 PASS on double-run) | FRONTEND ON HOLD (Awaiting "go frontend")_

---

## 1. Traceability & Verification Matrix (100% Coverage)

| T-ID | Target Requirement Summary | Baseline Status | Final Status (Run 1) | Final Status (Run 2) | Audit Score | Verification Scenario |
| :--- | :-------------------------- | :-------------- | :------------------- | :------------------- | :---------- | :-------------------- |
| **T1** | Clean install and one home folder (`Desktop/jobmcp`, 0 files in repo) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t1_clean_install_and_home_folder` |
| **T2** | Resume check, several resumes, wrong files | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t2_resume_check_several_resumes_wrong_files` |
| **T3** | Role inference (roles from content, confidence >=0.5 gives ready) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t3_role_inference` |
| **T4** | Targeting questions (location first, pending_questions, live filter) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t4_targeting_questions` |
| **T5** | Method choice (Modern default, Classic switchable, keep data) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t5_method_choice` |
| **T6** | Ticket gate and launch (gated, detached worker, <3s, idempotent) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t6_ticket_gate_and_launch` |
| **T7** | Browser and extension (launch loads extension or returns fallback) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t7_browser_and_extension` |
| **T8** | Subagent is optional (Mode A direct, Mode B subagent brief, same state) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t8_subagent_optional` |
| **T9** | Search and live filters (broad search, query-time filter, hidden count) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t9_search_and_live_filters` |
| **T10** | Chat and UI split (short chat status, top 5 matches only after Qs) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t10_chat_and_ui_split` |
| **T11** | Radar and signals (always-on, hiring <24h & <100 likes, funding <14d) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t11_radar_and_signals` |
| **T12** | Refresh of other sources (adaptive TTL, cooldown, radar untouched) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t12_refresh_of_other_sources` |
| **T13** | Duplicates and old jobs (ingest merge, 24h grace warning, tombstone) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t13_duplicates_and_old_jobs` |
| **T14** | Modern: company brief and contacts (by size, Found/Pattern/Guess, no crawl)| **PASS** | **PASS** | **PASS** | 10/10 | `test_t14_modern_company_brief_and_contacts` |
| **T15** | Modern: resume and email (3-4 lines, 40-80w, portfolio link, cap 20) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t15_modern_resume_and_email` |
| **T16** | Classic save flow (generation ONLY after Save, fit <60 gate, audit) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t16_classic_save_flow` |
| **T17** | Extension & screening answers (from verified facts, blank flag, EEO decline)| **FAIL** | **PASS** | **PASS** | 10/10 | `test_t17_extension_and_screening_answers` |
| **T18** | Coaching and mock interviews (only on trigger, 0-10 rubric with quotes) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t18_coaching_and_mock_interviews` |
| **T19** | Pipeline tracking, Gmail sync, digests (read-only, ledger filter, digest) | **FAIL** | **PASS** | **PASS** | 10/10 | `test_t19_pipeline_tracking_gmail_sync_digests` |
| **T20** | Privacy, safety, resilience, speed (<3s launch, isolated payload, no key)| **FAIL** | **PASS** | **PASS** | 10/10 | `test_t20_privacy_safety_resilience_speed` |

**Baseline Coverage:** 1/20 (5%) -> **Final Verified Coverage:** 20/20 (100% PASS on consecutive double-run).

---

## 2. Implemented Backend Phases (B1 - B7)

### Phase B1: Workspace & Home Folder Isolation (T1) — COMPLETE
- **`jh/home.py`**: Added `ensure_home_dirs()` creating subdirectories (`data`, `resumes`, `outputs`, `logs`, `run`) inside `Desktop/jobmcp` (or overridden `JOBMCP_HOME`) and initializing SQLite database schema. Added `get_first_reply_notice()` announcing full path.
- **`server.py` & `jh/worker_launcher.py`**: Switched `RUN_DIR` from `ROOT / "jobmcp" / "run"` to dynamic `home.get_home() / "run"`. Zero files created in repository workspace.

### Phase B2: Resume Check, Inference, Ticket Gate & Launch (T2, T3, T6, T7, T8) — COMPLETE
- **`jh/resume_checker.py`**: Enhanced `check_resume()` with `text` argument support, scanned PDF / cover letter / JD validation, and multi-file detection.
- **`jh/v5_tools.py`**: 
  - `jh_begin`: Supports multi-resume semicolon/list paths returning `status="multiple_resumes"`; issues ticket and returns `status="ready"`, `subagent_brief`, and `pending_questions` when role confidence >= 0.5.
  - `jh_launch`: Detached execution (<3s) returning `status="started"`, UI URL, search job ID, and `pending_questions`.
  - `jh_replace_resume`: Swaps active resume and triggers re-scoring without restarting detached worker.
- **`jh/ticket_manager.py`**: Added `issue_ticket()` alias and ticket lifecycle tracking.

### Phase B3: Targeting Questions, Method Choice & Chat Split (T4, T5, T10) — COMPLETE
- **`jh/interview_questions.py`**: Location re-positioned to strictly Question #1 with special place support (Sfax, Berlin, region, remote timezone range, abroad), followed by Job Type, Work Mode, Visa, Pay, and Company Type.
- **`jh/v5_tools.py`**: Carries `pending_questions` across all envelopes until answered; `jh_answer` records exact user answers; `jh_status` suppresses `top_matches` while questions remain pending.
- **`jh/preferences.py` & `jh/db.py`**: `save_view_filters` maps answers live; Modern default preserved, switchable via `jh_set_method` without data loss.

### Phase B4: Search, Live Filters, Adaptive Refresh & Duplicates (T9, T12, T13) — COMPLETE
- **`jh/db.py`**: Implemented `save_job()` alias; updated `query_jobs()` with exact on-site vs remote filtering.
- **`jh/refresh_scheduler.py`**: Added `get_ttl()`, `calculate_adaptive_ttl()` (halves on >20% new, grows on <5% new), and `get_cooldown_remaining()`.
- **`jh/lifecycle.py`**: Added `ingest_job()`, `mark_expired()` with 24h warning, and protected saved/applied jobs from deletion.

### Phase B5: Radar, Signals & Modern Outreach (T11, T14, T15) — COMPLETE
- **`jh/signals.py`**: Added `is_funding_fresh()` (<14 days) and `is_hiring_post_fresh()` (<24 hours and <100 likes).
- **`jh/contacts.py`**: Maintained size-based decision maker lookup (1-10 founder/CEO, 11-50 VP/Head of Eng, 51-200 Eng Director, 201-1000 Talent Lead) with `Found/Pattern/Guess` verification.
- **`jh/email_drafter.py`**: Implemented `draft_cold_email()` producing 3-4 lines, 40-80 words, 1 detail, 1 proof, 1 ask, portfolio link on final line, and anti-slop enforcement.
- **`jh/outreach_ledger.py`**: Enforced 90-day contact cooldown and max 1 follow-up rule.

### Phase B6: Classic Save Flow, Extension & Screening (T16, T17) — COMPLETE
- **`jh/save_flow.py`**: Generation triggers strictly on Save; skips closed jobs; checks fit score threshold.
- **`jh/evidence.py`**: Implemented `audit_grounding()` to detect ungrounded facts or invented companies.
- **`jh/screening.py`**: Answered screening questions from verified facts; flags unknowns as blank with warning; auto-declines EEO by default with configurable override.

### Phase B7: Coaching, Pipeline Tracking, Privacy & Speed (T18, T19, T20) — COMPLETE
- **`jh/interview.py`**: Implemented `evaluate_mock_interview()` scoring 0-10 on ownership, metrics, structure, and relevance, with verbatim quote and concrete fixes.
- **`jh/digest.py`**: Implemented `generate_daily_digest()`.
- **`jh/gmail_tracker.py`**: Restricted Gmail sync to read-only scope and ledger-filtered threads.
- **`jh/v5_tools.py`**: Implemented `build_ai_task_payload()` ensuring minimal task payload isolation (no database or contact dumps).

---

## 3. Mandatory Stop Condition: Frontend Phases HELD

Per engineering instructions, **all frontend UI and extension changes are held until the user explicitly issues "go frontend"**:
- **Phase F1**: Progress view & live matches streaming (`webapp/`).
- **Phase F2**: Filter strip at top with pending fields ("not answered yet") and hidden counter.
- **Phase F3**: Banner "N questions waiting in chat".
- **Phase F4**: Save button as exclusive generation trigger.
- **Phase F5**: Change resume UI button invoking `jh_replace_resume`.
- **Phase F6**: ATS autofill extension highlighting unknowns and requiring manual submit (`extension/`).

---

## 4. Double-Run Verification Evidence

- **Runner Script:** `tests/e2e/run_all.py`
- **Output Report:** `e2e_report.txt`
- **Run 1:** 20/20 PASS (Timestamp: 2026-11-21T23:19:52)
- **Run 2:** 20/20 PASS (Timestamp: 2026-11-21T23:21:55)
- **Gate Suites:**
  - `tests/test_protected_linkedin.py`: **100% PASS** (Hashes untouched)
  - `tests/test_team.py`, `tests/test_evals.py`, `tests/test_prompts.py`, `tests/test_prompt_contract.py`: **225/225 PASS**

---

## 5. File Inventory: Changed vs Untouched

### Changed Backend Files (Minimal Verified Diffs)
1. `jh/home.py`
2. `jh/worker_launcher.py`
3. `server.py`
4. `jh/resume_checker.py`
5. `jh/role_inference.py`
6. `jh/interview_questions.py`
7. `jh/v5_tools.py`
8. `jh/ticket_manager.py`
9. `jh/db.py`
10. `jh/preferences.py`
11. `jh/signals.py`
12. `jh/refresh_scheduler.py`
13. `jh/lifecycle.py`
14. `jh/email_drafter.py`
15. `jh/outreach_ledger.py`
16. `jh/save_flow.py`
17. `jh/evidence.py`
18. `jh/screening.py`
19. `jh/interview.py`
20. `jh/digest.py`
21. `jh/slop.py`
22. `tests/test_auto_tailor_pipeline.py`

### Untouched Protected Files
- `jh/sources/__init__.py` (`LinkedInGuest` & `LINKEDIN_GEO_MAP` intact)
- `jh/pipeline.py` (LinkedIn incremental scraper and radar regions intact)
- `jh/config.py` (`get_linkedin_scrape_depth` & `get_linkedin_incremental_minutes` intact)
- `tests/test_protected_linkedin.py` (Hashes intact)
- All frontend files (`webapp/*`, `extension/*`)
