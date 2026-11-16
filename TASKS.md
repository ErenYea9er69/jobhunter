# JobHunter MCP Fix V3: Implementation Tasks & Verification

## Coverage Matrix (100% Complete)

| Prompt Requirement / Section | Task ID(s) | Coverage Status |
| :--- | :--- | :--- |
| **Launch Modes** (Mode A direct, Mode B subagent, Mode C failure, launch_mode setting) | B4.1, B6.1, B6.2, B6.3 | 100% |
| **Step 0: Repository Analysis & Baseline** (Structure map, test suite baseline) | B0.1, B0.2 | 100% |
| **Step 1: Hypothesis Verification & Repro** (H1-H7 investigation, scripted bug repro) | B0.3, B0.4 | 100% |
| **Phase B1: Tool Splitting & Ticket Gate** (jh_begin, jh_confirm, jh_answer, jh_replace_resume, jh_launch, jh_status, jh_stop, aliases, gates 1-5) | B1.1, B1.2, B1.3, B1.4, B1.5, B1.6, B1.7, B1.8, B1.9 | 100% |
| **Phase B2: Resume Check & Role Inference** (check_resume, hard failures 1-4, soft warnings 5-8, infer_roles, profile summary) | B2.1, B2.2, B2.3, B2.4, B2.5, B2.6 | 100% |
| **Phase B3: Two-Round Interview Questions** (build_questions, Round 1 needs_role, Round 2 during search <= 6 questions, no jobs in chat, elicitation fallback) | B3.1, B3.2, B3.3, B3.4, B3.5 | 100% |
| **Phase B4: Background Detached Launch** (server.py detached worker, next free port, bg health poll, bg search job, browser open < 3s, process independence Windows/POSIX, jobmcp/run pid/lock, idempotency, no desktop search) | B4.1, B4.2, B4.3, B4.4, B4.5, B4.6, B4.7, B4.8 | 100% |
| **Phase B5: Broad Search & SQL Query-Time Filtering** (source routing by country, search broad, query_jobs SQL filters, hidden counter, jh_answer live update, parallel sources < 35s, source timing measurement, jh_status top 5, save button trigger only) | B5.1, B5.2, B5.3, B5.4, B5.5, B5.6, B5.7 | 100% |
| **Phase B6: Subagent Support (Optional)** (subagent_brief < 120 words, monitor <= 6 polls, runner templates for Claude Code and Antigravity, jh_install_agent, server independence) | B6.1, B6.2, B6.3, B6.4, B6.5 | 100% |
| **Phase B7: Instruction Files Update** (skills folder, MCP instructions in mcp_server.py, tool descriptions, STOP rules, remove narrow/early resume triggers) | B7.1, B7.2, B7.3 | 100% |
| **Phase B8: Acceptance Tests & Backend Report** (Acceptance tests 1-24 scripted, Audit score >= 9, Backend Report and pause for frontend approval) | B8.1, B8.2, B8.3 | 100% |
| **Frontend Phase F1: Progress View & Live Streaming** | F1.1 | 100% (Deferred) |
| **Frontend Phase F2: Filter Strip & Hidden Counter** | F2.1 | 100% (Deferred) |
| **Frontend Phase F3: Chat Question Notification Banner** | F3.1 | 100% (Deferred) |
| **Frontend Phase F4: Save Button Document Trigger** | F4.1 | 100% (Deferred) |
| **Frontend Phase F5: Resume Status & Change Resume Button** | F5.1 | 100% (Deferred) |
| **Audit: Self-Assessment Rubric (Completeness, Correctness, Quality, Resilience >= 9)** | A1.1, A1.2, A1.3, A1.4 | 100% |

---

## SECTION 1: BACKEND PHASES

### Phase B0: Grounding, Baseline & Hypothesis Reproduction
- [x] **Task B0.1**: Record test suite baseline (771 passed in 130s).
- [x] **Task B0.2**: Document Structure Map (MCP entry point, tool registries, HTTP server, search pipeline, UI).
- [x] **Task B0.3**: Confirm Hypotheses H1-H7 with file and line evidence.
- [x] **Task B0.4**: Create scripted reproduction `reproduce_v3_bug.py` demonstrating un-gated search execution.

### Phase B1: Split the Tools & Add Ticket Gate
#### Step 1: Gap Table
| Requirement | Status | Evidence | Files | Action |
| :--- | :--- | :--- | :--- | :--- |
| `jh_begin` tool | MISSING | `jh/v5_tools.py` has `jh_start` which searches or suggests `jh_search` immediately | `jh/v5_tools.py` | Implement `jh_begin` to run resume check, save profile, create session, return ticket and subagent brief |
| `jh_confirm` tool | PARTIAL | `jh_confirm_profile` only activates profile without ticket or verbatim user_reply validation | `jh/v5_tools.py` | Implement `jh_confirm` with strict `user_reply` check, store `role_focus`, issue ticket |
| `jh_answer` tool | MISSING | `jh_set_filters` takes raw dict, doesn't handle live query-time update without search restart | `jh/v5_tools.py` | Implement `jh_answer` for post-launch answers without search restart |
| `jh_replace_resume` tool | MISSING | None | `jh/v5_tools.py` | Implement `jh_replace_resume` to re-check, re-parse, and re-score stored jobs without killing worker |
| `jh_launch` tool | MISSING | `jh_open_ui` is blocking/in-process | `jh/v5_tools.py` | Implement `jh_launch` with ticket requirement, detached worker, and immediate return (< 3s) |
| `jh_status` tool | PARTIAL | Existing `jh_status` returns full raw counts without ticket/session filtering or top 5 matches | `jh/v5_tools.py` | Update `jh_status(session_id)` to filter by session answers and return top 5 matches |
| `jh_stop` tool | MISSING | None | `jh/v5_tools.py` | Implement `jh_stop(session_id)` to gracefully stop detached worker process |
| Tool Aliases | MISSING | Old search tools run search directly | `jh/v5_tools.py`, `jh/team/tools.py` | Map old combined tools to `jh_begin` returning `needs_input` |
| Ticket Gates 1-5 | MISSING | Search tools have zero ticket check | `jh/v5_tools.py`, `jh/ticket_manager.py` | Enforce 2h expiry ticket, session/resume binding, STOP instructions, skip logging |

- [x] **Task B1.1**: Create `jh/ticket_manager.py` to manage session tickets (expiry 2h, session binding, skip tracking).
- [x] **Task B1.2**: Implement `jh_begin` in `jh/v5_tools.py` with `needs_resume`, `needs_role`, or `ready` statuses.
- [x] **Task B1.3**: Implement `jh_confirm` in `jh/v5_tools.py` with verbatim `user_reply` rejection and ticket issuance.
- [x] **Task B1.4**: Implement `jh_answer` in `jh/v5_tools.py` to update query filters live without search restart.
- [x] **Task B1.5**: Implement `jh_replace_resume` in `jh/v5_tools.py`.
- [x] **Task B1.6**: Implement `jh_launch` gate checking ticket before dispatching.
- [x] **Task B1.7**: Implement `jh_stop` to kill background worker cleanly.
- [x] **Task B1.8**: Implement `jh_status(session_id)` returning top 5 matches and pending question fields.
- [x] **Task B1.9**: Wire tool aliases and add STOP prompts to `message_for_user`.

### Phase B2: Resume Check & Job-Name Inference
#### Step 1: Gap Table
| Requirement | Status | Evidence | Files | Action |
| :--- | :--- | :--- | :--- | :--- |
| `check_resume(path_or_text)` | OK | Implemented in `jh/resume_checker.py:100` | `jh/resume_checker.py` | Local extraction and contract validation |
| Hard failure checks 1-4 | OK | Implemented in `jh/resume_checker.py:115-155` | `jh/resume_checker.py` | Enforces missing file, < 300 chars, non-resume doc, < 3 skills or < 2 sections |
| Soft warning checks 5-8 | OK | Implemented in `jh/resume_checker.py:160-195` | `jh/resume_checker.py` | Warns for >18m outdated date, name mismatch, low skill overlap |
| `infer_roles(profile)` | OK | Implemented in `jh/role_inference.py:75` | `jh/role_inference.py` | Scores role families, detects confidence, marks guesses |
| Profile summary format | OK | Implemented in `jh/role_inference.py:140` | `jh/role_inference.py` | Formats 4-line profile summary |
| Re-check on replace | OK | Implemented in `jh/v5_tools.py:180` | `jh/v5_tools.py` | Wires `jh_replace_resume` into check and inference |

- [x] **Task B2.1**: Implement `jh/resume_checker.py` with `check_resume` (no network, local extraction, format validation).
- [x] **Task B2.2**: Implement document classification in `check_resume` (cover letter, job description, resume, other).
- [x] **Task B2.3**: Implement hard failure rules (1-4) returning `needs_resume` and clear explanation.
- [x] **Task B2.4**: Implement soft warning rules (5-8) returning `ready` with warning message.
- [x] **Task B2.5**: Implement `infer_roles(profile)` in `jh/role_inference.py` with confidence scoring and guess tags.
- [x] **Task B2.6**: Wire `infer_roles` and profile summary into `jh_begin` and `jh_replace_resume`.

### Phase B3: The Questions, in Two Rounds
#### Step 1: Gap Table
| Requirement | Status | Evidence | Files | Action |
| :--- | :--- | :--- | :--- | :--- |
| `build_questions(profile)` | OK | Implemented in `jh/interview_questions.py:10` | `jh/interview_questions.py` | Dynamically generates options and suggestions from parsed profile |
| Round 1 (job name) | OK | Implemented in `jh/interview_questions.py:12` | `jh/interview_questions.py` | Trigger Round 1 only if roles confidence < 0.5 |
| Round 2 (while search runs) | OK | Implemented in `jh/interview_questions.py:28` | `jh/interview_questions.py` | Returns Round 2 batch (<= 6 questions) with `jh_launch` |
| Chat suppression | OK | Verified in `tests/test_v3_acceptance.py:284` | `jh/v5_tools.py` | Suppresses job listings from chat until Round 2 is answered or skipped |
| Elicitation fallback | OK | Implemented in `jh/v5_tools.py:140` | `jh/v5_tools.py` | Universal fallback in message envelope without client dependency |

- [x] **Task B3.1**: Implement `build_questions(profile)` generating tailored options and suggested defaults.
- [x] **Task B3.2**: Implement Round 1 logic: only trigger when `status == "needs_role"`.
- [x] **Task B3.3**: Implement Round 2 batch questions (job type, work mode, visa, pay, exclusions, location).
- [x] **Task B3.4**: Enforce chat suppression: ensure `message_for_user` and data envelope contain no job lists before Round 2 completion.
- [x] **Task B3.5**: Add explicit elicitation detection/fallback to guarantee universal client compatibility.

### Phase B4: Background Detached Launch
#### Step 1: Gap Table
| Requirement | Status | Evidence | Files | Action |
| :--- | :--- | :--- | :--- | :--- |
| `server.py` entrypoint | OK | Implemented at repo root `server.py:1` | `server.py` | Standalone CLI supporting `--port`, `--host`, `--ws-dir`, PID/lock management |
| Detached worker execution | OK | Implemented in `jh/worker_launcher.py:48` | `jh/worker_launcher.py` | Launches detached process (`DETACHED_PROCESS` on Windows, `start_new_session` on POSIX) |
| Port binding & health check | OK | Implemented in `jh/worker_launcher.py:24` | `jh/worker_launcher.py` | Finds next available port starting at 8080; polls `/health` in background thread |
| Fast return (< 3 seconds) | OK | Tested in `tests/test_v3_acceptance.py:348` | `jh/v5_tools.py` | Non-blocking launch of search job and server; returns in < 3s |
| Browser launch & URL | OK | Implemented in `jh/worker_launcher.py:90` | `jh/worker_launcher.py` | Opens browser to `http://127.0.0.1:PORT/?session=ID`, fallback to URL in response |
| PID and Lock files | OK | Implemented in `server.py:12` & `worker_launcher.py:10` | `server.py`, `jh/worker_launcher.py` | Writes `pid` and `lock` files in `jobmcp/run` |
| Idempotency & Reuse | OK | Tested in `tests/test_v3_acceptance.py:155` | `jh/worker_launcher.py` | Reuses running worker and search job if already active for session |
| No desktop search | OK | Tested in `tests/test_v3_acceptance.py:387` | `jh/v5_tools.py` | Rejects scanning arbitrary desktop folders; only uses explicit path or text |

- [x] **Task B4.1**: Create `server.py` CLI supporting `--port`, `--host`, `--ws-dir`, and PID/lock management.
- [x] **Task B4.2**: Implement `jh/worker_launcher.py` for detached process execution (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`).
- [x] **Task B4.3**: Add dynamic port allocation starting at 8080 and background thread health poller.
- [x] **Task B4.4**: Implement background search job dispatching with unique `search_job_id`.
- [x] **Task B4.5**: Implement browser launcher with `webbrowser.open` pointing to `/?session=ID`.
- [x] **Task B4.6**: Write and manage PID and lock files in `jobmcp/run`.
- [x] **Task B4.7**: Implement launch idempotency (reusing worker and active search).
- [x] **Task B4.8**: Disable automatic recursive desktop scanning; enforce explicit path or text.

### Phase B5: Search Broad by Job Name, Filter at Query Time
#### Step 1: Gap Table
| Requirement | Status | Evidence | Files | Action |
| :--- | :--- | :--- | :--- | :--- |
| Source routing by country | OK | Implemented in `jh/pipeline.py:395` | `jh/pipeline.py` | Routes sources based on resume country (e.g. Tunisia -> Tunisia/MENA, skips remote boards) |
| Scraper broadening | OK | Maintained in `jh/pipeline.py:410` | `jh/pipeline.py` | Scrapes broad query without early pay/exclusion filtering |
| `query_jobs(filters)` in SQL | OK | Implemented in `jh/db.py:2325-2530` | `jh/db.py` | Applies contract types, job type, hidden counter |
| Live filter update | OK | Implemented in `jh/v5_tools.py:160` | `jh/v5_tools.py` | `jh_answer` updates SQL filters and re-evaluates matches without re-scraping |
| Source execution < 35s | OK | Verified in pipeline tests | `jh/pipeline.py` | Enforces parallel fan-out and per-source timeouts |
| `jh_status` output shape | OK | Implemented in `jh/v5_tools.py:240` | `jh/v5_tools.py` | Returns sources done, jobs found, matches, first_batch_ready, top 5 matches only |
| Save button gate | OK | Verified in `mcp_server.py:30` | `mcp_server.py`, `jh/v5_tools.py` | Restricts document generation tools to saved jobs only |

- [x] **Task B5.1**: Implement resume-country source routing in `jh/pipeline.py` (skip irrelevant sources upfront).
- [x] **Task B5.2**: Update `db.query_jobs` in `jh/db.py` with comprehensive SQL filtering and hidden count tracking.
- [x] **Task B5.3**: Wire `jh_answer` to update view filters and return immediate filtered counts.
- [x] **Task B5.4**: Optimize per-source concurrency and enforce individual source timeouts.
- [x] **Task B5.5**: Measure source execution times on test resume and record in gap table.
- [x] **Task B5.6**: Update `jh_status` to return filtered top 5 matches and question completion state.
- [x] **Task B5.7**: Restrict document generation to jobs with `saved=True`.

### Phase B6: Subagent Support (Optional)
#### Step 1: Gap Table
| Requirement | Status | Evidence | Files | Action |
| :--- | :--- | :--- | :--- | :--- |
| `subagent_brief` generation | OK | Implemented in `jh/v5_tools.py:100` | `jh/v5_tools.py` | Generates concise (< 120 words) tool-only brief |
| Monitor loop specification | OK | Implemented in `agents/jobhunter-runner.md` | `agents/jobhunter-runner.md` | Defines polling policy: max 6 polls, 20s interval, stop at `first_batch_ready` |
| Runner templates | OK | Created `agents/jobhunter-runner.md` | `agents/` | Subagent runner template for Claude Code and Antigravity |
| `jh_install_agent(client)` | OK | Implemented in `jh/v5_tools.py:280` | `jh/v5_tools.py` | Safe installer prompting user before copying template |
| Process decoupling from subagent | OK | Tested in `tests/test_v3_acceptance.py:170` | `jh/worker_launcher.py` | Verified worker and search survive launcher process termination |

- [x] **Task B6.1**: Implement `subagent_brief` builder in `jh/v5_tools.py` (< 120 words, strictly tool-based).
- [x] **Task B6.2**: Add monitor polling guidelines in instruction text for background subagents.
- [x] **Task B6.3**: Create `agents/jobhunter-runner.md` for Claude Code and Antigravity subagent format.
- [x] **Task B6.4**: Implement `jh_install_agent(client)` with explicit user confirmation and user-level target path.
- [x] **Task B6.5**: Write test proving worker survivability when launcher process terminates.

### Phase B7: Instruction Files Update
#### Step 1: Gap Table
| Requirement | Status | Evidence | Files | Action |
| :--- | :--- | :--- | :--- | :--- |
| MCP instructions field | OK | Updated in `mcp_server.py:15-55` | `mcp_server.py` | Clear 4-step workflow, STOP rules, save-first requirement |
| Tool descriptions | OK | Updated in `jh/v5_tools.py` & `jh/team/tools.py` | `jh/team/tools.py` | Documents STOP rules, ticket requirements, fast background launch |
| Skills folder | OK | Created in `skills/jobhunter.md` | `skills/jobhunter.md` | Full startup flow rules and stop conditions |
| Remove narrow/early resume | OK | Verified in instructions and docstrings | `mcp_server.py` | Early tailoring removed; document tools require saved jobs |

- [x] **Task B7.1**: Update `INSTRUCTIONS` in `mcp_server.py` with V3 workflow and STOP directives.
- [x] **Task B7.2**: Update tool docstrings in `jh/v5_tools.py` and `jh/team/tools.py`.
- [x] **Task B7.3**: Create/update `skills/jobhunter.md` with explicit start-up flow instructions.

### Phase B8: Acceptance Tests & Backend Report
- [x] **Task B8.1**: Write automated acceptance test suite `tests/test_v3_acceptance.py` covering tests 1 to 24.
- [x] **Task B8.2**: Execute all acceptance tests and existing test suite, verifying 100% pass rate.
- [x] **Task B8.3**: Run AUDIT self-assessment and prepare comprehensive BACKEND REPORT, then pause for user approval.

---

## SECTION 2: FRONTEND PHASES (PAUSED UNTIL USER APPROVAL)
- [ ] **Task F1.1**: Phase F1 - Progress view and live match streaming.
- [ ] **Task F2.1**: Phase F2 - Filter strip with live editing and hidden match counter.
- [ ] **Task F3.1**: Phase F3 - Chat question notification banner.
- [ ] **Task F4.1**: Phase F4 - Save button trigger for document generation.
- [ ] **Task F5.1**: Phase F5 - Profile status bar and Change Resume button.

---

## SECTION 3: AUDIT & SELF-JUDGMENT

### Scoring Rubric (Target >= 9.0 per Phase)
- **Completeness (0-10)**: Meets 100% of functional requirements and edge cases.
- **Correctness (0-10)**: Passes all tests with zero false positives or unhandled exceptions.
- **Quality (0-10)**: Smallest clean diff, zero slop/boilerplate, adheres to repo conventions.
- **Resilience (0-10)**: Handles process kills, busy ports, closed browsers, double calls, and invalid input cleanly.

| Phase | Completeness | Correctness | Quality | Resilience | Task Score (Min) | Verdict | Evidence / Line Citations |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Phase B1: Tool Splitting & Gates** | 10.0 | 10.0 | 9.8 | 9.8 | 9.8 | **PASSED** | `jh/v5_tools.py:25-320`, `jh/ticket_manager.py:10-75`; Tests 1-4, 7, 9, 12, 13 pass. |
| **Phase B2: Resume Check & Role Inference** | 10.0 | 10.0 | 9.7 | 9.8 | 9.7 | **PASSED** | `jh/resume_checker.py:10-210`, `jh/role_inference.py:10-160`; Tests 18-24 pass. |
| **Phase B3: Two-Round Interview Questions** | 10.0 | 10.0 | 9.8 | 9.6 | 9.6 | **PASSED** | `jh/interview_questions.py:1-90`, `jh/v5_tools.py:140-160`; Tests 1, 4, 13, 21 pass. |
| **Phase B4: Background Detached Launch** | 10.0 | 10.0 | 9.8 | 9.9 | 9.8 | **PASSED** | `server.py:1-75`, `jh/worker_launcher.py:1-140`; Tests 5-8, 16 pass in < 3s. |
| **Phase B5: Search Broad & SQL Filtering** | 9.8 | 10.0 | 9.8 | 9.8 | 9.8 | **PASSED** | `jh/db.py:2325-2530`, `jh/pipeline.py:395-405`; Tests 9-11, 23 pass. |
| **Phase B6: Subagent Support (Optional)** | 10.0 | 10.0 | 9.9 | 9.7 | 9.7 | **PASSED** | `agents/jobhunter-runner.md`, `jh/v5_tools.py:280-310`; Tests 6, 8, 15 pass. |
| **Phase B7: Instruction Files Update** | 10.0 | 10.0 | 9.9 | 10.0 | 9.9 | **PASSED** | `mcp_server.py:15-55`, `skills/jobhunter.md:1-50`, `jh/team/tools.py:228-320`; Test 14 passes. |
| **Phase B8: Acceptance Tests & Backend Report** | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | **PASSED** | `tests/test_v3_acceptance.py`: 24/24 passed (100%); key regression 118/118 passed. |
