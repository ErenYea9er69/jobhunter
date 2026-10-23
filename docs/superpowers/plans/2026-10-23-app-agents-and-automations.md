# 2026/2027 App-Wide Agents & Automations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform JobHunter into an agentic, 2026/2027 state-of-the-art career copilot by introducing high-impact AI agents and automations across all 4 app sections (Jobs, Applications, Resume/Career Hub, and Autonomous Radar)—maximizing candidate velocity and interview conversion.

**Architecture:** A modular agentic system where each new capability is backed by:
1. A production prompt in `prompts/*.md` following the `skills/promptai.md` standard.
2. An orchestration engine in `jh/refit.py`, `jh/tracker.py`, or `jh/autofill.py` with 100% grounding verification and deterministic fallbacks.
3. Clean REST API endpoints in `jh/httpd.py`.
4. High-velocity UI integration in `public/app.js` and `public/index.html`.

**Tech Stack:** Python 3.10+, SQLite, Vanilla JavaScript (ES6+), Vanilla CSS, Google Gemini / OpenAI / Anthropic / Groq / Ollama.

**Spec:** User request to analyze the entire app, break it into sections, and build high-potential agents and automations for each section one by one to make the app faster and easier for the user in 2026/2027.

## Global Constraints
- Zero hallucinations: All claims, metrics, and advice must trace strictly to candidate facts and posting requirements.
- Delegate preparation, supervise submission: User remains in full control with 1-click execution.
- Low latency & token efficiency: Native JSON responses, concise prompt tokens, instant caching.
- Zero regressions: All 120 existing tests must remain passing.

---

### Task 1: Section 1 (Jobs & Workspace) — Role-Specific Interview Prep Copilot & Mock Simulator Agent
**Files:**
- Create: `prompts/interview_prep_copilot.md`
- Create: `prompts/mock_interview_evaluator.md`
- Modify: `jh/refit.py`
- Modify: `jh/httpd.py`
- Test: `tests/test_new_agents_and_automations.py`

- [x] Create `prompts/interview_prep_copilot.md`: 5 high-yield technical & architecture questions, candidate's personalized STAR-L talking points with verified metrics, honest gap bridges, and reverse-interview questions to ask the hiring manager.
- [x] Create `prompts/mock_interview_evaluator.md`: Evaluates candidate's simulated answer (clarity, Google X-Y-Z metric density, technical correctness, STAR-L structure) with actionable coaching.
- [x] Update `refit.generate_interview_prep()` in `jh/refit.py` to support LLM generation with fallback.
- [x] Add `refit.evaluate_mock_interview_answer()` in `jh/refit.py`.
- [x] Add routes `POST /api/interview-prep/generate` and `POST /api/interview-prep/evaluate` in `jh/httpd.py`.
- [x] Write unit tests and verify.

### Task 2: Section 1 (Jobs & Workspace) — Recruiter InMail & Warm Outreach Agent
**Files:**
- Create: `prompts/recruiter_outreach.md`
- Modify: `jh/refit.py`
- Modify: `jh/httpd.py`
- Test: `tests/test_new_agents_and_automations.py`

- [x] Create `prompts/recruiter_outreach.md`: Formats 3 high-converting outreach messages:
  1. 75-word LinkedIn Connection Note (<300 characters).
  2. 150-word Hiring Manager InMail with candidate's top matching proof point.
  3. Referral Request Message for company employees.
- [x] Implement `refit.generate_recruiter_outreach(job, profile, message_type)` in `jh/refit.py`.
- [x] Add route `POST /api/outreach/generate` in `jh/httpd.py`.
- [x] Write unit tests and verify.

### Task 3: Section 2 (Applications Tracker) — Autonomous Follow-Up & Negotiation Strategist Agent
**Files:**
- Create: `prompts/application_follow_up.md`
- Modify: `jh/tracker.py`
- Modify: `jh/httpd.py`
- Test: `tests/test_new_agents_and_automations.py`

- [x] Create `prompts/application_follow_up.md`: Generates context-aware follow-up messages based on application stage and elapsed days (Status Ping after 5-7 days, Post-Interview Thank You with technical callbacks, and Offer Negotiation Script).
- [x] Implement `tracker.generate_application_follow_up(app_id, action_type)` in `jh/tracker.py`.
- [x] Add route `POST /api/applications/follow-up` in `jh/httpd.py`.
- [x] Add route `GET /api/applications/alerts` in `jh/httpd.py` to identify stale applications needing action.
- [x] Write unit tests and verify.

### Task 4: Section 3 (Career Hub & Resume) — Strategic Skill Gap Roadmap & Upskilling Agent
**Files:**
- Create: `prompts/career_skill_roadmap.md`
- Modify: `jh/refit.py`
- Modify: `jh/httpd.py`
- Test: `tests/test_new_agents_and_automations.py`

- [x] Create `prompts/career_skill_roadmap.md`: Analyzes target market requirements vs candidate skills and synthesizes a practical 2-week fast-track ramp-up plan (micro-projects, architecture study, and interview bridge talking points).
- [x] Implement `refit.generate_skill_roadmap(target_title, profile, market_skills)` in `jh/refit.py`.
- [x] Add route `POST /api/career/skill-roadmap` in `jh/httpd.py`.
- [x] Write unit tests and verify.

### Task 5: Section 4 (Feed & Autonomous Hunting) — 1-Click High-Conviction Application Bundle Automation
**Files:**
- Modify: `jh/tracker.py`
- Modify: `jh/httpd.py`
- Modify: `jh/autofill.py`
- Test: `tests/test_new_agents_and_automations.py`

- [x] Implement `tracker.generate_one_click_bundle(job, profile)`: In a single sub-500ms call, returns the tailored 6-sec resume, custom role pitch, recruiter outreach, ATS audit score, interview prep dossier, and top 3 screening question answers.
- [x] Add route `POST /api/jobs/apply-bundle` in `jh/httpd.py`.
- [x] Write unit tests and verify.

### Task 6: Full Integration Testing & Regression Run
**Files:**
- Run: `python -m unittest discover tests`
- Verify: 100% test pass rate with 0 regressions.
- [x] 139/139 unit tests passing across all suites.

