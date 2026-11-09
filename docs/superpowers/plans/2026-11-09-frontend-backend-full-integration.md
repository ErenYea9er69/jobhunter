# Frontend & Backend 100% Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all API contract, schema, state synchronization, and data persistence mismatches between the newly redesigned Web Dashboard (`public/`, `webapp/`), the Chromium Extension (`extension/`), and the Python backend daemon (`jh/httpd.py`, `jh/tracker.py`, `jh/preferences.py`, `jh/db.py`), ensuring 100% functional integrity and passing test suites.

**Architecture:** 
1. Expand `jh/preferences.py` to support `home_cities` (aliased with `cities`), `work_authorized`, `notice_period`, and `submission_mode`, returning preferences both flat and nested so the Web UI and extension receive all answers.
2. Enrich `jh/db.py:list_resume_profiles()` to merge full candidate profile details (skills, experience, contact, filenames) from `data_json`, and make `jh/httpd.py:/api/profile/activate` activate the profile in both SQLite and the ResumeRegistry.
3. Harden `jh/tracker.py:upsert_application` so partial status updates (e.g. moving a kanban card `{ id, status }`) preserve existing company, title, url, notes, and metadata rather than overwriting with defaults.
4. Update `tests/test_frontend_assets.py` to assert the 5 new route tabs (`data-route="jobs"`, `"applications"`, `"documents"`, `"resume"`, `"settings"`), sync `webapp/` and `public/`, and verify the entire test suite passes.

**Tech Stack:** Python 3.10+, SQLite3, Vanilla JavaScript (ES2022), Chrome Extension Manifest V3, Pytest.

**Spec:** `UI-CHANGES.md`, `PRODUCT.md`, `DESIGN.md`, `docs/superpowers/specs/2026-10-23-jobright-autofill-extension-and-recommendations-design.md`.

## Global Constraints

- Protect regions specified in `AGENTS.md` (`LinkedInGuest`, `LINKEDIN_GEO_MAP`, scraper radar banner, `get_linkedin_scrape_depth`, `get_linkedin_incremental_minutes`).
- Offline test suite: run `python -m pytest tests -q` before and after changes.
- Tools only: all MCP tools must remain envelope-wrapped and assigned to employee roles.
- Prompts and QA gates: ensure Reviewer verification (`jh/team/qa.py`) remains intact.
- Keep stdout clean: daemon logging to stderr only.

## Review Focus

1. `home_cities` vs `cities`: Web app settings sends `home_cities`; saving must succeed and stay in sync with `cities`.
2. Autofill settings persistence: `work_authorized`, `notice_period`, `submission_mode` must persist in `preferences.json` and be returned in `GET /api/preferences` for both the frontend and the extension.
3. Profile details rendering: `GET /api/profiles` must return full candidate skills, experience, and contact data so the UI doesn't report missing facts.
4. Application card moving: moving cards between stages must preserve the job title, company name, url, and notes.
5. Profile variant activation: activating a variant must update both `db.set_active_resume_profile` and `registry.set_active_variant`.

---

### Task 1: Preferences Schema & API Contract Extension

**Files:**
- Modify: `jh/preferences.py:31-70`, `jh/preferences.py:120-175`
- Modify: `jh/httpd.py:176-181`
- Test: `tests/test_preferences_autofill_and_cities.py`

**Interfaces:**
- Consumes: `jh.preferences.load()`, `jh.preferences.update(updates)`
- Produces: `DEFAULTS` containing `home_cities`, `work_authorized`, `notice_period`, `submission_mode`. `GET /api/preferences` returning merged flat and nested dictionary.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preferences_autofill_and_cities.py
import unittest
from jh import preferences

class TestPreferencesAutofillAndCities(unittest.TestCase):
    def test_home_cities_alias_and_autofill_fields(self):
        updates = {
            "home_cities": ["Tunis", "Sousse"],
            "work_authorized": "yes",
            "notice_period": "1month",
            "submission_mode": "review",
            "needs_visa_sponsorship": False,
        }
        clean, warnings = preferences.validate(updates)
        self.assertEqual(clean.get("cities"), ["Tunis", "Sousse"])
        self.assertEqual(clean.get("home_cities"), ["Tunis", "Sousse"])
        self.assertEqual(clean.get("work_authorized"), "yes")
        self.assertEqual(clean.get("notice_period"), "1month")
        self.assertEqual(clean.get("submission_mode"), "review")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_preferences_autofill_and_cities.py -v`
Expected: FAIL with `PreferenceError: Unknown preference 'home_cities'` or `'work_authorized'`.

- [ ] **Step 3: Implement in `jh/preferences.py` and `jh/httpd.py`**

In `jh/preferences.py`:
- Add `home_cities: []`, `work_authorized: ""`, `notice_period: ""`, `submission_mode: "review"` to `DEFAULTS`.
- Add `home_cities` to `LIST_FIELDS`.
- In `validate()`:
  - If `home_cities` is present in updates, set both `clean["cities"]` and `clean["home_cities"]`. If `cities` is present, set both.
  - Handle `work_authorized` (strings up to 80 chars), `notice_period` (strings up to 80 chars), and `submission_mode` (validate in `("review", "countdown", "instant", "manual")`).
- In `load()`: ensure returned dict has `home_cities` synced with `cities`.
In `jh/httpd.py`:
- In `path == "/api/preferences"` GET handler:
  Return `data={**prefs, "home_cities": prefs.get("home_cities") or prefs.get("cities", []), "preferences": prefs, "resolved_targets": targets}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_preferences_autofill_and_cities.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jh/preferences.py jh/httpd.py tests/test_preferences_autofill_and_cities.py
git commit -m "fix(preferences): support home_cities and autofill fields in preferences API"
```

---

### Task 2: Fix Profiles API Data Completeness & Variant Activation

**Files:**
- Modify: `jh/db.py:585-634`
- Modify: `jh/httpd.py:128-147`, `jh/httpd.py:374-378`
- Test: `tests/test_profiles_api_sync.py`

**Interfaces:**
- Consumes: `jh.db.list_resume_profiles()`, `jh.resume_registry.ResumeRegistry`
- Produces: `GET /api/profiles` with full `skills`, `experience`, and `active` field; `POST /api/profile/activate` activating profile in both DB and registry.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profiles_api_sync.py
import unittest
from jh import db

class TestProfilesApiSync(unittest.TestCase):
    def test_list_resume_profiles_contains_full_fields(self):
        db.init_db()
        profiles = db.list_resume_profiles()
        if profiles:
            p = profiles[0]
            self.assertIn("skills", p)
            self.assertIn("experience", p)
            self.assertIn("email", p)
            self.assertIn("phone", p)
            self.assertIn("experience_years", p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_profiles_api_sync.py -v`
Expected: FAIL with `AssertionError: 'skills' not found in ...`

- [ ] **Step 3: Implement in `jh/db.py` and `jh/httpd.py`**

In `jh/db.py`:
- In `list_resume_profiles()`, extract all fields from `data_json`:
  ```python
  skills = d.get("skills", [])
  experience = d.get("experience", [])
  email = d.get("email", "")
  phone = d.get("phone", "")
  location = d.get("location", "")
  linkedin = d.get("linkedin", "")
  github = d.get("github", "")
  website = d.get("website", "")
  filename = d.get("filename") or d.get("_source_file", "")
  if filename and ("/" in filename or "\\" in filename):
      filename = Path(filename).name
  ```
  Include these keys in each returned profile dict, plus `experience_years: years`.

In `jh/httpd.py`:
- In `path == "/api/profiles"` GET handler:
  Return `data={"profiles": profiles, "active": active or "", "active_profile": active or "", "count": len(profiles)}`.
- In `path == "/api/profile/activate"` POST handler:
  ```python
  name_or_id = body.get("id") or body.get("name", "")
  var = registry.get_variant(name_or_id)
  prof_id = (var.get("id") if var else None) or name_or_id
  try:
      db.set_active_resume_profile(prof_id)
  except Exception:
      pass
  success = registry.set_active_variant(var.get("name") if var else name_or_id)
  ```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_profiles_api_sync.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jh/db.py jh/httpd.py tests/test_profiles_api_sync.py
git commit -m "fix(profiles): enrich list_resume_profiles and synchronize dual-layer activation"
```

---

### Task 3: Prevent Application Data Loss on Partial Status Updates

**Files:**
- Modify: `jh/tracker.py:43-76`
- Test: `tests/test_tracker_partial_upsert.py`

**Interfaces:**
- Consumes: `jh.tracker.upsert_application(data)`
- Produces: Safe partial upsert preserving existing row data.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tracker_partial_upsert.py
import unittest
from jh import tracker

class TestTrackerPartialUpsert(unittest.TestCase):
    def test_partial_status_update_preserves_application_data(self):
        initial = {
            "title": "Senior Python Engineer",
            "company": "Acme Corp",
            "url": "https://example.com/jobs/1",
            "status": "saved",
            "notes": "Met founder on LinkedIn",
        }
        app_id = tracker.upsert_application(initial)
        
        # Now perform partial update as frontend does:
        tracker.upsert_application({"id": app_id, "status": "queued"})
        
        apps = tracker.list_applications()
        updated = next(a for a in apps if a["id"] == app_id)
        self.assertEqual(updated["status"], "queued")
        self.assertEqual(updated["title"], "Senior Python Engineer")
        self.assertEqual(updated["company"], "Acme Corp")
        self.assertEqual(updated["url"], "https://example.com/jobs/1")
        self.assertEqual(updated["notes"], "Met founder on LinkedIn")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tracker_partial_upsert.py -v`
Expected: FAIL because `updated["company"]` becomes `"Unknown"` and `updated["title"]` becomes `"Untitled role"`.

- [ ] **Step 3: Implement safe upsert in `jh/tracker.py`**

In `jh/tracker.py:upsert_application(data)`:
```python
    with db.session() as c:
        old = c.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
        follow = data.get("follow_up_date") or ""
        if not follow and status in FOLLOW_UP_DAYS and (old is None or old["status"] != status):
            follow = (datetime.date.today() + datetime.timedelta(days=FOLLOW_UP_DAYS[status])).isoformat()
        elif not follow and old:
            follow = old["follow_up_date"] or ""

        if old:
            company = clean_text(data.get("company")) or old["company"]
            title = clean_text(data.get("title")) or old["title"]
            location = clean_text(data.get("location")) if "location" in data else old["location"]
            salary = clean_text(data.get("salary")) if "salary" in data else old["salary"]
            notes = data.get("notes") if "notes" in data else old["notes"]
            job_id = data.get("job_id") if "job_id" in data else old["job_id"]
            sources_json = json.dumps(data["sources"]) if "sources" in data else old["sources_json"]
            cover_letter = data.get("cover_letter") if "cover_letter" in data else old["cover_letter"]
            tailored_json = json.dumps(data["tailored_resume"]) if "tailored_resume" in data else old["tailored_resume_json"]
            
            old_jd = json.loads(old["job_data_json"]) if old["job_data_json"] else {}
            old_jd.update(job_d)
            final_job_d = old_jd
        else:
            company = clean_text(data.get("company")) or "Unknown"
            title = clean_text(data.get("title")) or "Untitled role"
            location = clean_text(data.get("location", ""))
            salary = clean_text(data.get("salary", ""))
            notes = data.get("notes", "")
            job_id = data.get("job_id")
            sources_json = json.dumps(data.get("sources", []))
            cover_letter = data.get("cover_letter", "")
            tailored_json = json.dumps(data.get("tailored_resume"))
            final_job_d = job_d
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tracker_partial_upsert.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jh/tracker.py tests/test_tracker_partial_upsert.py
git commit -m "fix(tracker): preserve existing data on partial application status updates"
```

---

### Task 4: Align Frontend Assets Test & Synchronize Webapp to Public

**Files:**
- Modify: `tests/test_frontend_assets.py`
- Modify: `public/app.js`, `webapp/app.js` (if any minor tweak needed for compatibility)
- Verify: Full test suite `python -m pytest tests -q`

- [ ] **Step 1: Update `tests/test_frontend_assets.py`**

Update `test_html_contains_five_tabs`:
```python
    def test_html_contains_five_tabs(self):
        index_file = self.pub_dir / "index.html"
        self.assertTrue(index_file.is_file())
        html = index_file.read_text(encoding="utf-8")

        # Verify 5 tabs are present
        self.assertIn('data-route="jobs"', html)
        self.assertIn('data-route="applications"', html)
        self.assertIn('data-route="documents"', html)
        self.assertIn('data-route="resume"', html)
        self.assertIn('data-route="settings"', html)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_frontend_assets.py -v`
Expected: PASS

- [ ] **Step 3: Ensure `public/` and `webapp/` remain perfectly synchronized**

Copy any modified `public/` or `webapp/` files to ensure 0 diff:
`git diff --no-index webapp/ public/` returns empty.

- [ ] **Step 4: Run full offline test suite**

Run: `python -m pytest tests -q`
Expected: 665+ tests passing, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add tests/test_frontend_assets.py public/ webapp/
git commit -m "test(frontend): update frontend assets test for 5-route navigation and sync public"
```
