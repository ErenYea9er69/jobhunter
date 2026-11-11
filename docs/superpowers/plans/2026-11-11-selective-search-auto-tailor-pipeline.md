# Selective Search & Auto-Tailor Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

This plan re-architects the JobHunter discovery and application flow so that:
1. Candidate profile/resume target roles are dynamically detected.
2. Web scrapers and LinkedIn radar run concurrently and persist all discovered jobs into SQLite (`engine.db`).
3. Only jobs matching the user's specific filter criteria (e.g. Worldwide Remote, no US/Canada visa required) are displayed on the main UI; non-matching jobs stay saved in SQLite but hidden from the active view.
4. The system never auto-saves or auto-applies jobs on its own.
5. When the user explicitly clicks "Save" on a job, a background event hook automatically tailors a resume variant and drafts a cover letter specifically for that job, saving them to SQLite and registering the variant for the ATS Autofill extension.

---

### File Structure & Responsibilities

- **`jh/tracker.py`**:
  - Add `auto_tailor_application_async(app_id, job, profile)` and `auto_tailor_application_sync(app_id, job, profile)`.
  - Connects `refit.generate_custom_resume` and `refit.generate_cover_pitch` directly to the `applications` table update.
  - Registers the tailored profile into `ResumeRegistry` and `resume_profiles`.
- **`jh/httpd.py`**:
  - In `POST /api/applications`, trigger `auto_tailor_application_async` when `status == "saved"` and no tailored resume is present yet.
- **`jh/mcp_tools.py`**:
  - In `track_application` and `add_to_tracker`, trigger auto-tailoring when `status == "saved"`.
  - In `search_jobs`, infer search domains from `derive_target_roles(profile)` when no explicit query is provided.
- **`jh/pipeline.py`**:
  - In `pipeline.search()`, trigger `trigger_linkedin_radar_now()` concurrently so LinkedIn incremental jobs are ingested in parallel without modifying any protected code or hashes.
- **`webapp/app.js` & `public/app.js`**:
  - Synchronized updates for Option A: immediate "Saved" UI feedback, polling/displaying generated tailored resume & cover letter badge in the Applications tab.
- **`tests/test_auto_tailor_pipeline.py`**:
  - Unit & integration tests verifying the entire flow without network dependency.

---

## Tasks

### Task 1: Add Auto-Tailoring Hook in `jh/tracker.py`
- [x] Add `auto_tailor_application(app_id, background=True)` function in `jh/tracker.py`.
- [x] Ensure it fetches `job_data` and active `profile`, runs `refit.generate_custom_resume()` and `refit.generate_cover_pitch()`.
- [x] Updates SQLite `applications` with `tailored_resume_json` and `cover_letter`.
- [x] Syncs new tailored profile into `resume_profiles` table so ATS Autofill and Profile switcher detect it.

### Task 2: Connect Auto-Tailor Hook in `jh/httpd.py` and `jh/mcp_tools.py`
- [x] In `jh/httpd.py` `POST /api/applications`, trigger `auto_tailor_application` when `status == "saved"`.
- [x] In `jh/mcp_tools.py` `track_application`, trigger `auto_tailor_application` when `status == "saved"`.
- [x] Ensure neither auto-saves jobs without explicit user save action.

### Task 3: Enhance Search Role Ingestion & Radar Triggering
- [x] In `jh/pipeline.py` `search()`, call `trigger_linkedin_radar_now()` at search start (ensuring lines 868-1199 remain untouched).
- [x] In `jh/mcp_tools.py` `search_jobs`, if `query` is empty, use `derive_target_roles(profile)` to infer primary target titles and record them in the result metadata.

### Task 4: Update Frontend Dashboard (`webapp/app.js` and `public/app.js`)
- [x] Update `saveJob(j, "saved")` in `app.js` to provide instant Option A feedback.
- [x] Render a "Tailored package ready" or "Tailoring in background..." badge in Applications card drawer.
- [x] Mirror changes between `webapp/app.js` and `public/app.js`.

### Task 5: Automated Tests & Verification
- [x] Create `tests/test_auto_tailor_pipeline.py` testing:
  - Application save triggers auto-tailor.
  - Tailored resume and cover letter stored in SQLite.
  - Radar trigger non-blocking integration.
- [x] Run `python -m pytest tests/test_protected_linkedin.py` to guarantee hash integrity.
- [x] Run `python -m pytest tests -q` to guarantee all 678+ tests pass.
