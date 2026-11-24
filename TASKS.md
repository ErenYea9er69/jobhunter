# JobHunter V7 Task Tracking & Defect Remediation

## Gap Table

| Defect | Requirement | Status | Evidence | Files | Action |
|---|---|---|---|---|---|
| D1 | Session state machine (NEW, RESUME_OK, ASKED, ANSWERED, LAUNCHED, ROUND2_DONE). Old tools check state, refuse out of order calls with needs_input + questions. 2h ticket. | BROKEN | `jh/ticket_manager.py:78` has loose states; `jh/mcp_tools.py:158` search_jobs has zero state checks; `jh/v5_tools.py:621` auto-issues ticket. | `jh/ticket_manager.py`, `jh/v5_tools.py`, `jh/mcp_tools.py` | Implement rigid SessionStateMachine enum and check_state gate on all tools. |
| D2 | Preferences/filters written only via jh_confirm/jh_answer with user_reply. Reject empty, <2 chars, == questions, <5s interval. Audit log. MCP elicitation check + chat fallback. | BROKEN | `jh/v5_tools.py:430` jh_set_filters bypasses validation; no audit log; no 5s delay check. | `jh/ticket_manager.py`, `jh/v5_tools.py`, `jh/db.py`, `jh/elicitation.py` | Add timing gate, length/equality validation, DB audit log table, and elicitation helper. |
| D3 | Split storage into guesses and answers. Guesses from resume never filter search. Roles with conf >= 0.5 set scope. | BROKEN | `jh/db.py:660` merges guesses directly into profiles.preferences; non-role guesses narrow search. | `jh/db.py`, `jh/role_inference.py`, `jh/pipeline.py` | Create guesses and answers tables; query_jobs reads answers only; role conf threshold 0.5. |
| D4 | Round 1 mandatory before ticket. STOP prompt first line. Place question + route sources (Tunisia -> Tunisia/MENA/ATS, no global remote; Remote worldwide -> global; Abroad -> country). | BROKEN | `jh/v5_tools.py:621` skips round 1; `jh/pipeline.py:80` runs global scrapers on Tunisia searches. | `jh/interview_questions.py`, `jh/v5_tools.py`, `jh/pipeline.py`, `jh/source_registry.py` | Enforce Round 1 gate with fixed STOP text; source router filters out global feeds for Tunisia. |
| D5 | Store method in session. Branch on it: Modern -> Signal Radar, UI signals; Classic -> multi-board search, UI jobs. Switch method anytime preserving both. | PARTIAL | `jh/v5_tools.py:107` has method switch, but search/UI lack clean separation and launch gating. | `jh/v5_tools.py`, `jh/radar.py`, `jh/pipeline.py`, `jh/server.py` | Bind method to session state, gate Radar vs multi-board on launch. |
| D6 | Detached worker under 3s (Windows DETACHED_PROCESS+CREATE_NEW_PROCESS_GROUP, POSIX start_new_session, pid/lock in jobmcp/run). Remove blocking search. Strip job cards from tool replies. | BROKEN | `jh/mcp_tools.py:158` search_jobs blocks 57s and returns job lists; `jh/worker_launcher.py:40` lacks process group flags. | `jh/worker_launcher.py`, `jh/mcp_tools.py`, `jh/v5_tools.py` | Implement true detached process flags, pid file in jobmcp/run; strip job objects from AI replies. |
| D7 | Chromium launch at http://127.0.0.1:PORT/?session=ID with extension loaded on progress view. Dedicated profile in jobmcp. UI calls /api/ping, server stores ui_seen. browser_opened, ui_seen in replies. | BROKEN | `jh/v5_tools.py:885` disables browser open (`browser_opened: False`), no extension loaded, no /api/ping handler. | `jh/worker_launcher.py`, `jh/server.py`, `jh/v5_tools.py`, `webapp/app.js` | Implement Chromium launcher with extension flag and dedicated profile; add /api/ping and ui_seen tracking. |
| D8 | Round 2 questions carried until answered/skipped. UI banner "N questions waiting". jh_answer filters DB view live without search restart. "N hidden by filters" counter. | BROKEN | `jh/v5_tools.py:942` drops pending questions in some responses; UI lacks question banner and hidden counter. | `jh/v5_tools.py`, `webapp/index.html`, `webapp/app.js`, `jh/server.py` | Carry ask_user in replies; add banner and counter in webapp and /api/jobs/query. |
| D9 | Visa-needing jobs flagged "work rights not confirmed" before visa answered, hidden only after answered. Chat never lists them. | BROKEN | `jh/pipeline.py` and `jh/ats.py` do not attach visa confirmation flag to jobs. | `jh/ats.py`, `jh/server.py`, `webapp/app.js` | Add visa_confirmed flag logic; show badge in UI; hide only when user specifies no sponsorship. |
| D10 | tailor_resume, cover_letter, outreach_message, score_fit check saved_by == 'ui'. Save click is HTTP action in UI with page token. Remove "next steps" from replies. | BROKEN | `jh/mcp_tools.py:563` tailors unsaved jobs without checking saved_by; prompts include next steps. | `jh/mcp_tools.py`, `jh/server.py`, `webapp/app.js`, `prompts/` | Enforce saved_by == 'ui'; add UI save endpoint with session token; strip next steps advice. |
| D11 | interview_prep, coaching, track_application run only on explicit user request or UI click. Remove coaching next-steps. | BROKEN | `jh/mcp_helpers.py:350` automatically appends unsolicited coaching advice to envelopes. | `jh/mcp_helpers.py`, `jh/mcp_tools.py` | Suppress unsolicited coaching envelopes and suggestions unless explicitly triggered. |
| D12 | Server returns profile_line (name, roles with confidence, years, skills, 'tell me if this is wrong'). AI says it before R1. Post-launch 1-line summary. | BROKEN | `jh/v5_tools.py:485` jh_begin returns generic header without standardized profile_line field. | `jh/v5_tools.py`, `jh/role_inference.py` | Add structured profile_line to jh_begin output and concise launch message to jh_launch. |
| NEW-1 | `test_freshness_evaluation_states` hardcoded date (2026-10-25) expired on 2026-11-24 causing 1 test failure. | BROKEN | `tests/unit/test_normalization_and_freshness.py:54` AssertionError. | `tests/unit/test_normalization_and_freshness.py` | Use relative timestamp (now - 5 days) so test remains valid across dates. |

---

## Coverage Matrix

| Defect ID | Task ID(s) | Status |
|---|---|---|
| D1 | TASK-B3 | Covered (100%) |
| D2 | TASK-B1 | Covered (100%) |
| D3 | TASK-B2 | Covered (100%) |
| D4 | TASK-B4 | Covered (100%) |
| D5 | TASK-B5 | Covered (100%) |
| D6 | TASK-B6 | Covered (100%) |
| D7 | TASK-B12, TASK-F1 | Covered (100%) |
| D8 | TASK-B7, TASK-F2 | Covered (100%) |
| D9 | TASK-B8, TASK-F3 | Covered (100%) |
| D10 | TASK-B9, TASK-F4 | Covered (100%) |
| D11 | TASK-B10 | Covered (100%) |
| D12 | TASK-B11 | Covered (100%) |
| NEW-1 | TASK-B0 | Covered (100%) |

**Overall Coverage: 100%**

---

## Tasks

### BACKEND

- [ ] `TASK-B0` (NEW-1): Fix date drift in `tests/unit/test_normalization_and_freshness.py` to restore 100% green baseline.
  - Defect: NEW-1
  - Test: `tests/unit/test_normalization_and_freshness.py`
  - Commit: Pending

- [ ] `TASK-B1` (D2): Preferences/filters written only via `jh_confirm`/`jh_answer` with user words. Validate length >= 2, reject empty, reject matching questions, reject interval < 5s. DB audit log table. MCP elicitation check + chat fallback.
  - Defect: D2
  - Test: `tests/test_d2_preferences_audit.py`
  - Commit: Pending

- [ ] `TASK-B2` (D3): Split storage into `guesses` and `answers` tables in `jh/db.py`. Query jobs and scrapers read answers only. Top role confidence >= 0.5 sets search scope; non-role guesses never filter.
  - Defect: D3
  - Test: `tests/test_d3_guesses_vs_answers.py`
  - Commit: Pending

- [ ] `TASK-B3` (D1): Server session state machine (`NEW`, `RESUME_OK`, `ASKED`, `ANSWERED`, `LAUNCHED`, `ROUND2_DONE`). Every tool checks state first, old aliases return `needs_input` + pending questions. 2-hour ticket.
  - Defect: D1
  - Test: `tests/test_d1_state_machine.py`
  - Commit: Pending

- [ ] `TASK-B4` (D4): Mandatory Round 1 questions before ticket with fixed "STOP." prompt. Method, place (Tunisia, Remote worldwide, Abroad), and role (if conf < 0.5). Source routing (Tunisia excludes global remote feeds).
  - Defect: D4
  - Test: `tests/test_d4_round1_routing.py`
  - Commit: Pending

- [ ] `TASK-B5` (D5): Method stored in session. Modern starts Signal Radar, Classic starts multi-board search. Switching method preserves both datasets.
  - Defect: D5
  - Test: `tests/test_d5_method_branching.py`
  - Commit: Pending

- [ ] `TASK-B6` (D6): Detached worker launch in under 3s (`DETACHED_PROCESS` / `CREATE_NEW_PROCESS_GROUP`, `start_new_session`, pid/lock in `jobmcp/run`). Remove blocking search from old tools. Strip job cards from tool replies.
  - Defect: D6
  - Test: `tests/test_d6_detached_and_strip.py`
  - Commit: Pending

- [ ] `TASK-B7` (D8): Carry `ask_user` with round 2 questions in `jh_launch`, `jh_status`, `jh_answer` until answered/skipped. `jh_answer` filters DB view live without restarting search.
  - Defect: D8
  - Test: `tests/test_d8_round2_filter.py`
  - Commit: Pending

- [ ] `TASK-B8` (D9): Visa sponsorship detection and "work rights not confirmed" flag before visa answered. Jobs hidden only after explicit visa answer.
  - Defect: D9
  - Test: `tests/test_d9_visa_handling.py`
  - Commit: Pending

- [ ] `TASK-B9` (D10): Enforce `saved_by == 'ui'` on `tailor_resume`, `cover_letter`, `outreach_message`, `score_fit`. Remove "next steps" suggestions.
  - Defect: D10
  - Test: `tests/test_d10_save_gate.py`
  - Commit: Pending

- [ ] `TASK-B10` (D11): Suppress unsolicited coaching and tracking advice from MCP replies.
  - Defect: D11
  - Test: `tests/test_d11_coaching_gate.py`
  - Commit: Pending

- [ ] `TASK-B11` (D12): Structured `profile_line` in `jh_begin` output; concise 1-line status in `jh_launch`.
  - Defect: D12
  - Test: `tests/test_d12_profile_line.py`
  - Commit: Pending

- [ ] `TASK-B12` (D7 Backend): Chromium launcher with extension flag and dedicated profile in `jobmcp`. `/api/ping` endpoint on server, `ui_seen` state tracking.
  - Defect: D7
  - Test: `tests/test_d7_browser_and_ping.py`
  - Commit: Pending

### FRONTEND

- [ ] `TASK-F1` (D7 Frontend): Web UI calls `/api/ping` on page load to confirm `ui_seen: true`.
  - Defect: D7
  - Test: `tests/test_d7_browser_and_ping.py`
  - Commit: Pending

- [ ] `TASK-F2` (D8 Frontend): UI banner "N questions are waiting in the chat" and counter "N hidden by your filters".
  - Defect: D8
  - Test: `tests/test_ui_banner_strip.py`
  - Commit: Pending

- [ ] `TASK-F3` (D9 Frontend): UI badge "work rights not confirmed" on visa-requiring jobs when visa is not confirmed.
  - Defect: D9
  - Test: `tests/test_d9_visa_handling.py`
  - Commit: Pending

- [ ] `TASK-F4` (D10 Frontend): UI Save button calls `/api/jobs/:id/save` with session page token to set `saved_by = 'ui'`.
  - Defect: D10
  - Test: `tests/test_d10_save_gate.py`
  - Commit: Pending

### ADVERSARIAL SCRIPT & AUDIT

- [ ] `TASK-ADV` (Step 3): Comprehensive adversarial script testing all short-path shortcuts, invalid answers, rapid calls, unsaved tailoring, and old tool names.
  - Test: `tests/test_adversarial_v7.py`
  - Commit: Pending

- [ ] `TASK-AUD` (Step 4): Self-audit scoring D1 to D12 across completeness, correctness, quality, and resilience with concrete evidence.
  - Commit: Pending

### CLEAN SLATE, TESTER & SHIP

- [ ] `TASK-CS1` (Step 4b): Clean slate backup, worker stop, delete old data, build & install local wheel, verify clean environment.
  - Commit: Pending

- [ ] `TASK-TST` (Step 5): Black-box tester subagent verification across scenarios (lazy path, correct modern/classic, bad inputs).
  - Commit: Pending

- [ ] `TASK-SHIP` (Step 6): Bump version to 1.1.0, update CHANGELOG and README, tag git release, publish, update client MCP config.
  - Commit: Pending
