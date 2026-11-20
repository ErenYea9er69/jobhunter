# JobHunter V5 Engineering Task Board & Coverage Matrix

_Created: 2026-11-20 | Quality Layer: Resume and Application Quality Engine (R1 to R9)_

## 1. Traceability & Coverage Matrix (100% Coverage)

| Rule | Requirement Summary | Task ID(s) | Status | Verification Surface |
| :--- | :--- | :--- | :--- | :--- |
| **R1** | Master resume as single source of facts, chat confirmed facts (`user_confirmed` + timestamp), strict sentence-level claim audit (employer, title, dates, degree, tools, numbers, results), 2 repair rounds, block if still failing, preserve employment gaps and real dates | `B1-R1-GROUNDING-CONFIRMED-FACTS` | Pending | `tests/test_v5_quality.py`, `tests/test_save_flow.py` |
| **R2** | Real numbers only in bullets ("action, what, number"), single chat batch of <=5 questions for missing metrics, stored as `user_confirmed`, skip allowed with no number, zero estimation or rounding | `B2-R2-METRICS-INTERVIEW` | Pending | `tests/test_v5_quality.py`, `tests/test_refit.py` |
| **R3** | Two-line summary: target role + matching skill group, plus one proof point from verified facts (or role + skills only if none), zero stock phrases ("passionate about", "results-driven", etc.) | `B3-R3-TWO-LINE-SUMMARY` | Pending | `tests/test_v5_quality.py`, `tests/test_refit.py` |
| **R4** | Mirror job keywords without lying: 3 groups (Have = exact wording in bullet & skills, Related = gap without renaming, Missing = gap), keyword stuffing failure (>2 occurrences), coverage "keyword coverage: N of M, gaps: ..." | `B4-R4-KEYWORD-MIRRORING` | Pending | `tests/test_v5_quality.py`, `tests/test_refit.py` |
| **R5** | ATS-safe 1-column layout, standard headings (Experience, Education, Projects, Skills), contact in body, no skill bars/stars/icons, pypdf round-trip extraction test (reading order, sections, email, phone), PDF < 200 KB, 1 page (<5 yrs) / max 2 pages | `B5-R5-ATS-PDF-ROUNDTRIP` | Pending | `tests/test_v5_quality.py`, `tests/test_exporters.py` |
| **R6** | Up to 6 base resumes by role family built once from master facts and approved, on Save pick matching base and tailor in <5 seconds (reorder, Have keywords, R3 summary, pass R1) | `B6-R6-BASE-RESUMES-TAILORING` | Pending | `tests/test_v5_quality.py`, `tests/test_save_flow.py` |
| **R7** | Comprehensive anti-slop check on resume, cover letter, email, and extension answers (editable `slop_rules.json`, buzzwords, em dashes, exclamation marks, same bullet starts, uniform sentence length, lacking concrete detail), 2-round rewrite, voice sample matching, Classic cover letter <=200w (company reason + proof point + small ask, no "I am writing to apply"), proofread gate (spell check, repeated words, past tense for past jobs, exact title/company, dates in order, no placeholders, one typo fails) | `B7-R7-SLOP-PROOFREAD-GATE` | Pending | `tests/test_v5_quality.py`, `tests/test_slop.py` |
| **R8** | Screening answers in extension: answered strictly from master + confirmed facts, short and concrete, slop check (R7), blank + flagged when fact missing, auto-decline EEO, extension stops before Submit | `B8-R8-SCREENING-QUALITY` | Pending | `tests/test_v5_quality.py`, `tests/test_screening.py` |
| **R9** | Freshness: "posted N hours ago", "fresh, under 48 hours" badge, fresh sorted first within filtered matches, company career page preference, Radar alert fresh-only, "ready to apply" count for passing R1/R5/R7, zero auto-apply | `B9-R9-FRESHNESS-BACKEND`, `F1-R9-FRESHNESS-UI`, `F2-R4-KEYWORD-UI` | Pending | `tests/test_v5_quality.py`, `tests/test_freshness.py` |

**Coverage:** 9/9 Quality Layer Rules Mapped = **100% Coverage**.

---

## 2. BACKEND Tasks (Phase 1)

### Task B1: `B1-R1-GROUNDING-CONFIRMED-FACTS`
- **Target Files:** `jh/db.py`, `jh/team/claims.py`, `jh/save_flow.py`
- **Actions:**
  - In `jh/db.py`: Add table and helper functions for confirmed facts: `add_confirmed_fact(fact, category, session_id)`, `get_confirmed_facts(session_id)`. Stored with `date` (ISO timestamp) and `label="user_confirmed"`.
  - In `jh/team/claims.py`: Update `FactBase` to incorporate `user_confirmed` facts alongside profile facts. Ensure phone numbers, emails, and date components in contact lines are never flagged as unsupported metric claims.
  - In `jh/save_flow.py`: Enforce strict 2-round repair loop. If any claim remains ungrounded after 2 repair rounds, set `grounding="blocked"`, block document save, and return the exact ungrounded claim details to the user.
  - Ensure real dates and employment gaps are preserved without smoothing or fabrication.

### Task B2: `B2-R2-METRICS-INTERVIEW` & Task B3: `B3-R3-TWO-LINE-SUMMARY`
- **Target Files:** `jh/refit.py`, `jh/v5_tools.py`
- **Actions:**
  - In `jh/refit.py`:
    - Format bullets as "action, what, and number" when a number exists in master facts or `user_confirmed` facts.
    - If a bullet lacks numbers, never invent or estimate. Provide missing-metric question extractor.
    - Rewrite summary generation to strictly output 2 lines:
      Line 1: Target role + strongest skill group matching the job.
      Line 2: One concrete proof point from verified facts (or omitted if none).
      Strip and block all stock phrases ("hard-working team player", "seeking opportunities", "results-driven", "passionate about").
  - In `jh/v5_tools.py`:
    - Expose `jh_ask_missing_metrics` or question batching (max 5 questions) for unquantified bullets, storing answers with `user_confirmed` label.

### Task B4: `B4-R4-KEYWORD-MIRRORING`
- **Target Files:** `jh/skills.py`, `jh/refit.py`, `jh/save_flow.py`
- **Actions:**
  - Partition extracted posting terms into 3 explicit groups:
    - **Have:** In candidate facts. Use posting's exact casing/wording in bullet and skills line.
    - **Related:** Close skill in candidate ontology; keep candidate's own skill name; show as gap.
    - **Missing:** Not present; add nothing; show as gap.
  - Enforce keyword stuffing gate: a keyword appears at most 2 times in the resume body.
  - Return formatted string `keyword_coverage: "N of M, gaps: <list>"`.

### Task B5: `B5-R5-ATS-PDF-ROUNDTRIP`
- **Target Files:** `jh/exporters.py`
- **Actions:**
  - Enforce standard ATS section headings in `exporters.py`: `Experience`, `Education`, `Projects`, `Skills`.
  - Keep contact details inside page body (never in headers or footers).
  - Eliminate skill bars, stars, and graphic symbols.
  - Implement `verify_pdf_roundtrip(pdf_bytes, expected_data)` using `pypdf`:
    - Extract text layer from generated PDF.
    - Assert correct reading order from top to bottom.
    - Assert all standard sections are found.
    - Assert email and phone are extracted intact.
    - Assert PDF size < 200 KB.
  - Length control: enforce 1 page for students / <5 years experience; max 2 pages for senior profiles.

### Task B6: `B6-R6-BASE-RESUMES-TAILORING`
- **Target Files:** `jh/db.py`, `jh/role_inference.py`, `jh/refit.py`, `jh/save_flow.py`
- **Actions:**
  - In `jh/db.py`: Create storage and schema for `base_resumes` (`id, role_family, resume_data, approved, created_at`).
  - In `jh/refit.py`: Generate up to 6 base resumes for role families discovered by `role_inference.py` (Full Stack, Backend, Frontend, Cloud/DevOps, AI/ML, Data).
  - In `jh/save_flow.py`: On Save, select the matching base resume and apply light tailoring (reorder, Have keywords, R3 summary) in < 5 seconds.

### Task B7: `B7-R7-SLOP-PROOFREAD-GATE`
- **Target Files:** `jh/slop.py`, `jh/email_drafter.py`, `jh/save_flow.py`, `jh/screening.py`
- **Actions:**
  - Create centralized `jh/slop.py` with editable config file (`jh/slop_rules.json`).
  - Lint resume, cover letter, email, and extension answers against:
    - Banned openers and stock phrases.
    - Buzzword stacks.
    - Em dashes (`—`, `–`, `--`) and exclamation marks (`!`).
    - Bullets that all start with the same verb or opener.
    - Sentences of uniform length.
    - Lines lacking concrete detail from facts or posting.
  - Implement 2-round auto-rewrite loop.
  - Implement Classic cover letter rule: <= 200 words, line 1: specific reason about company with source from posting, line 2: one proof point, line 3: small ask; never open with "I am writing to apply".
  - Implement Proofread Gate: spell check, repeated words, past tense for past jobs, company name and title spelled exactly as in posting, dates in chronological order, zero placeholders (`[Company]`). One typo fails the gate.

### Task B8: `B8-R8-SCREENING-QUALITY`
- **Target Files:** `jh/screening.py`, `jh/httpd.py`
- **Actions:**
  - In `jh/screening.py`: Remove speculative boilerplate from narrative fallbacks. If a fact is missing from master facts and confirmed facts, leave field blank and flag with `flagged=True`.
  - Pass all answers through R7 slop check before returning.
  - Maintain EEO / diversity auto-decline and stop before Submit.

### Task B9: `B9-R9-FRESHNESS-BACKEND`
- **Target Files:** `jh/freshness.py`, `jh/db.py`, `jh/pipeline.py`
- **Actions:**
  - Compute `posted_hours_ago` and `is_fresh_48h` (age <= 48 hours).
  - Prefer company career page timestamp over aggregator timestamps.
  - In `jh/db.py`: Add `get_ready_to_apply_count()` tracking jobs with passing R1, R5, and R7 document sets.
  - Ensure Radar alert queries fresh matches only.

---

## 3. FRONTEND Tasks (Phase 2 - Deferred until Backend complete)

### Task F1: `F1-R9-FRESHNESS-UI`
- **Target Files:** `webapp/app.js`, `public/app.js`, `webapp/styles.css`, `public/styles.css`
- **Actions:**
  - In job card rendering: Display `posted N hours ago` (or days if >= 48h) and `<span class="badge badge-fresh">fresh, under 48 hours</span>`.
  - Inside filtered matches, sort fresh jobs first.
  - Display "Ready to apply: N" counter in header/metrics bar.

### Task F2: `F2-R4-KEYWORD-UI`
- **Target Files:** `webapp/app.js`, `public/app.js`
- **Actions:**
  - Display "keyword coverage: N of M, gaps: ..." in the job details and document review panel before sending.

---

## 4. AUDIT & ACCEPTANCE (Phase 3)

### Task A1: `A1-ACCEPTANCE-AUDIT`
- **Target Files:** `tests/test_v5_quality.py`
- **Actions:**
  - Comprehensive acceptance test suite verifying all 12 scripted checks (R1-R9).
  - Self-audit score across Completeness, Correctness, Quality, and Resilience (threshold >= 9/10).
  - Manual test of 10 lines or fewer.
