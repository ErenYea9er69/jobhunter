# 2026/2027 AI Agents & Prompts Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize all AI agents, system prompts, ATS auditing, and LLM runtime engines across JobHunter for 2026/2027 standards—eliminating prompt bloat, enforcing strict factual grounding, banning AI slop, fixing prompt loading bugs, and accelerating inference speed with native JSON modes.

**Architecture:** A multi-layered architecture where prompts adhere to the `skills/promptai.md` standard (Task Brief, XML input containment, chain-of-thought analysis, strict output schema, anti-hallucination guardrails, anti-AI-slop bans), coupled with updated ATS heuristics (vector-friendly single-column, modern power verbs, real tech metrics) and optimized LLM provider dispatchers (native JSON modes, cacheable headers, modern 2026/2027 model defaults).

**Tech Stack:** Python 3.10+, SQLite, Google Gemini API, OpenAI API (GPT-4o/o3-mini), Anthropic Claude API (Claude 3.7/3.5 Sonnet), Groq (Llama 3.3 70B), DeepSeek (V3/R1), Ollama.

**Spec:** User request to analyze all AI agents and prompts one by one, identify weaknesses and gaps against 2026/2027 recruitment and ATS realities, and systematically upgrade them one by one.

## Global Constraints
- Zero hallucinations: All tailored output must strictly trace to `<candidate_source>` master profile.
- Single-column ATS safety: Resumes and exported layouts must be clean, text-selectable, and parseable by Greenhouse Intelligence, Workday AI, Ashby, and Lever.
- Modern high-impact role pitch: Cover letters must not exceed 250 words, completely banning generic "I am writing to apply" openings and robotic AI clichés.
- Native JSON mode & low latency: Use JSON mode and structured outputs wherever supported to eliminate markdown backtick wrapping and speed up response times.
- Backward compatibility: All 112 existing unit tests must remain passing with 0 regressions.

## Review Focus
1. `prompts/cover_letter_pitch.md` was previously ignored at runtime in `jh/refit.py` because `generate_cover_pitch()` used a hardcoded fallback string. Ensure file is dynamically loaded with fallback.
2. In `generate_custom_resume()`, ensure `<analysis>` tags don't corrupt JSON parsing or leak into UI diffs.
3. In `jh/autofill.py`, extract `SCREENING_SOLVER_PROMPT` into a dedicated prompt file `prompts/screening_question_solver.md` with 2026 triage heuristics.
4. In `jh/ats.py`, update `POWER_VERBS` and `METRIC` regex to capture modern 2026 cloud, DevOps, AI, and distributed systems impact without false negatives.
5. In `jh/refit.py`, ensure provider dispatchers (`gemini`, `openai`, `anthropic`, `groq`) use low latency configs and native JSON responses where supported.

---

### Task 1: Audit & Upgrade Agent 1 — 6-Second Resume Tailor & Refit Engine
**Files:**
- Modify: `prompts/resume_tailor_6sec.md`
- Modify: `jh/refit.py:309-312, 450-570`
- Test: `tests/test_jobhunter.py`

- [ ] Analyze weaknesses: Wordiness in system prompt, fragile `<analysis>` extraction, fallback `LLM_SYSTEM` lacking 6-second hook schema, vulnerability to AI cliché verbs ("spearheaded", "leveraged").
- [ ] Upgrade `prompts/resume_tailor_6sec.md` to 2026/2027 recruiter 6-second F-pattern standard: Zone 1 (0-2s Target Title & Executive Hook), Zone 2 (2-4s Core Competency Matrix), Zone 3 (4-6s Google X-Y-Z Proof Bullets).
- [ ] Incorporate anti-AI-slop blacklist directly in prompt rules.
- [ ] Upgrade fallback `LLM_SYSTEM` in `jh/refit.py` so that even if the markdown file is unreadable, the fallback system prompt generates the full 6-second tailored schema.
- [ ] Ensure robust `<analysis>` strip in `jh/refit.py` so reasoning is captured for audit while the JSON payload parses cleanly.

### Task 2: Audit & Upgrade Agent 2 — Cover Letter & High-Impact Role Pitch Generator
**Files:**
- Modify: `prompts/cover_letter_pitch.md`
- Modify: `jh/refit.py:313-332, 970-1040`
- Test: `tests/test_jobhunter.py`

- [ ] Fix critical bug: `jh/refit.py` `generate_cover_pitch()` must dynamically load `prompts/cover_letter_pitch.md` (with fallback to `COVER_PITCH_LLM_SYSTEM`).
- [ ] Upgrade prompt for 2026/2027 standards: Eliminate 4-paragraph boilerplate. Enforce 150-250 word high-impact role pitch (or 3-bullet executive brief).
- [ ] Provide 3 strategic angles: `direct_impact` (business pain solver), `startup_velocity` (0-to-1 builder), `technical_architect` (scale & systems reliability).
- [ ] Add explicit ban on opening clichés ("I am excited to apply", "In today's fast-paced digital world").
- [ ] Strengthen honest skill bridge: When candidate lacks a tech requirement, honestly bridge to parallel foundational architecture without pretending proficiency.

### Task 3: Audit & Upgrade Agent 3 — Job Application Screening Question Solver / Copilot
**Files:**
- Create: `prompts/screening_question_solver.md`
- Modify: `jh/autofill.py:742-751, 805-845`
- Test: `tests/test_jobhunter.py`

- [ ] Create `prompts/screening_question_solver.md` using the `skills/promptai.md` standard.
- [ ] Address 2026 recruiter screening realities: Dissecting individual ownership vs team buzzwords, handling salary transparency & remote/async discipline, and authentic concise voice (60-120 words).
- [ ] Wire `jh/autofill.py` `solve_screening_question()` to load `prompts/screening_question_solver.md` dynamically with fallback to `SCREENING_SOLVER_PROMPT`.
- [ ] Clean up answer sanitization to ensure zero markdown formatting or trailing quotes interfere with web form input fields.

### Task 4: Audit & Upgrade Agent 4 — ATS Readiness Audit & Keyword Intelligence Engine
**Files:**
- Modify: `jh/ats.py:6-14, 22-80`
- Test: `tests/test_jobhunter.py`

- [ ] Upgrade `POWER_VERBS`: Add modern 2026 high-leverage engineering verbs (`decoupled`, `benchmarked`, `containerized`, `orchestrated`, `shipped`, `fine-tuned`, `instrumented`, `refactored`, `migrated`, `scaled`).
- [ ] Upgrade `METRIC` regex: Support modern production metrics (`ms latency`, `TPS`, `RPS`, `p99`, `SLA`, `uptime`, `TB/PB`, `nodes`, `ARR`, `% cost reduction`).
- [ ] Update keyword stuffing threshold: Modern 2026 ATS (Workday AI, Ashby) penalizes >3-4 unnatural keyword repeats. Calibrate threshold from 6 down to 4.
- [ ] Add layout compliance check: Verify single-column structure and standard section names ("Work Experience", "Education", "Skills").

### Task 5: Audit & Upgrade Agent 5 — AI Provider Router & Low-Latency Execution Engine
**Files:**
- Modify: `jh/refit.py:165-306`
- Modify: `jh/config.py` (if applicable)
- Test: `tests/test_jobhunter.py`

- [ ] Gemini API: Enable `responseMimeType: "application/json"` in generationConfig when JSON is requested for instant parsing without markdown wrappers.
- [ ] OpenAI / Custom API: Pass `response_format: {"type": "json_object"}` when generating JSON payloads.
- [ ] Anthropic API: Add `anthropic-beta: "prompt-caching-2024-07-31"` or modern caching headers where applicable.
- [ ] Update default model fallbacks to 2026/2027 top models (`gemini-2.5-flash`, `gpt-4o-mini`, `claude-3-7-sonnet-20250219`, `llama-3.3-70b-versatile`, `deepseek-chat`).

### Task 6: Comprehensive Verification & Regression Testing
**Files:**
- Run: `tests/test_jobhunter.py`
- Test: Full pipeline test with custom resume refit, cover letter pitch generation, screening question solving, and ATS audit.
