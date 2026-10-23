# Jobright-Style Autofill Extension & Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete Jobright-style local autofill ecosystem: enriched backend payload with multi-work/education history and numeric/boolean question solvers, a dedicated Manifest V3 Chrome Extension replicating the Cohere reference UI with 100% verified application confirmation, and a modern Jobright-style split recommendation feed in the local webapp.

**Architecture:** The local Python backend (`jh/autofill.py`, `jh/httpd.py`) serves enriched candidate payloads, computes skill/experience tenures, and answers screening questions with CORS enabled. A standalone Manifest V3 extension in `extension/` runs in developer mode, injects a floating Jobright copilot onto ATS portals (Greenhouse, Lever, Ashby, Workday, etc.), executes 1-click React-safe autofilling, and intercepts submission success to guarantee verified applications. The webapp's Recommendations tab is redesigned into Jobright's two-pane feed (`jobright.ai/jobs/recommend`).

**Tech Stack:** Python 3 (standard library, SQLite), Manifest V3 Chrome Extension (Vanilla JS, CSS), Vanilla HTML5/JS/CSS for webapp.

**Spec:** `docs/superpowers/specs/2026-10-23-jobright-autofill-extension-and-recommendations-design.md`

## Global Constraints

- Must run completely locally: zero external cloud dependencies, zero telemetry, local API on `http://localhost:8080`.
- Manifest V3 compliant extension with `host_permissions: ["<all_urls>", "http://localhost:8080/*", "http://127.0.0.1:8080/*"]`.
- Backward compatibility: All existing 117 tests across `tests/test_jobhunter.py` and `tests/test_audit_remediation.py` must pass at every step.
- React 16+ DOM synthetic event compatibility: Form filling must bypass fiber value setters so values persist on single-page-app submits.

## Review Focus

1. **Workday / Taleo multi-step wizards:** The extension must persist candidate context across wizard step page transitions without losing state.
2. **Numeric and Boolean screening inputs:** Screening solver must return `"Yes"` / `"No"` or pure integers (e.g. `"4"`) when the input is a radio, select, or number field, preventing form validation rejections.
3. **CORS handling for extension origins:** Backend endpoints must handle browser extension preflight `OPTIONS` and standard `fetch` requests with appropriate `Access-Control-Allow-Origin: *`.
4. **False submission positives:** Application confirmation detector must require explicit DOM success cues (e.g. "Application submitted", "Thank you for applying") or confirmation URLs before triggering the verified ping.
5. **Resume and Cover Pitch Fallbacks:** When LLM is not configured, deterministic fallbacks must provide high-quality grounded candidate answers without blocking the autofill flow.

---

### Task 1: Backend Autofill Payload Enrichment & Experience Calculation

**Files:**
- Modify: `jh/autofill.py:303-440`
- Test: `tests/test_jobright_extension_and_autofill.py`

**Interfaces:**
- Produces: `get_autofill_payload(profile, job) -> dict` containing:
  - `work_history`: list of dicts `[{ "company": str, "title": str, "start_date": str, "end_date": str, "is_current": bool, "location": str, "description": str, "bullets": list }]`
  - `education_history`: list of dicts `[{ "institution": str, "degree": str, "field_of_study": str, "start_year": str, "graduation_year": str, "gpa": str }]`
  - `skill_years`: dict `{"python": int, "react": int, ...}`
  - `total_years_experience`: int
  - `legal_and_eeo`: dict with `authorized_us`, `require_sponsorship_now`, `require_sponsorship_future`, `gender`, `race_ethnicity`, `veteran_status`, `disability_status`
  - `address_components`: dict with `street_address`, `city`, `state_province`, `postal_code`, `country`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_jobright_extension_and_autofill.py
import pytest
from jh import autofill

def test_autofill_payload_extended_history_and_metrics():
    profile = {
        "name": "Rayen Ben Aissa",
        "email": "rayen@example.com",
        "phone": "+1-555-0199",
        "location": "San Francisco, CA, United States",
        "skills": ["Python", "React", "TypeScript", "FastAPI"],
        "experience": [
            {
                "company": "Tech Corp",
                "role": "Senior Full Stack Engineer",
                "start": "2023-01",
                "end": "Present",
                "bullets": ["Engineered core backend APIs in Python and FastAPI", "Built React UI"]
            },
            {
                "company": "Startup Studio",
                "role": "Software Engineer",
                "start": "2021-01",
                "end": "2022-12",
                "bullets": ["Developed full stack web apps using React and Python"]
            }
        ],
        "education": [
            {
                "institution": "University of Technology",
                "degree": "Bachelor of Science in Computer Science",
                "graduation_year": "2021"
            }
        ]
    }
    payload = autofill.get_autofill_payload(profile)
    assert len(payload["work_history"]) == 2
    assert payload["work_history"][0]["company"] == "Tech Corp"
    assert payload["work_history"][0]["is_current"] is True
    assert len(payload["education_history"]) == 1
    assert payload["total_years_experience"] >= 3
    assert payload["skill_years"]["python"] >= 3
    assert payload["address_components"]["city"] == "San Francisco"
    assert "legal_and_eeo" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_jobright_extension_and_autofill.py::test_autofill_payload_extended_history_and_metrics -v`
Expected: FAIL (file or keys missing)

- [ ] **Step 3: Implement calculation and payload enrichment in `jh/autofill.py`**

Implement helper functions in `jh/autofill.py`:
- `calculate_experience_years(experiences)`: Parses start/end date strings (e.g. "2021-01", "2021", "Present") and sums active tenure.
- `calculate_skill_tenures(skills, experiences)`: Computes overlapping tenure for each candidate skill based on experience entries mentioning that skill or bullet points.
- `extract_address_components(location_str)`: Parses street, city, state, postal code, and country.
- Enrich `get_autofill_payload()` to return `work_history`, `education_history`, `skill_years`, `total_years_experience`, `legal_and_eeo`, and `address_components`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_jobright_extension_and_autofill.py::test_autofill_payload_extended_history_and_metrics -v`
Expected: PASS

- [ ] **Step 5: Run existing test suite**

Run: `python -m pytest tests/test_jobhunter.py tests/test_audit_remediation.py -v`
Expected: ALL PASS

---

### Task 2: Question-Type-Aware Screening Solver

**Files:**
- Modify: `jh/autofill.py:781-903`
- Test: `tests/test_jobright_extension_and_autofill.py`

**Interfaces:**
- Produces: `solve_screening_question(question, profile, job=None, question_type="auto", max_words=120, tone="direct") -> dict`
  - Returns `{"question": str, "answer": str, "question_type": str, "provider": str, "grounded": bool, "word_count": int}`
  - If `question_type` or detected intent is boolean: returns `"Yes"` (e.g., authorization, 18+ age) or `"No"` (e.g., sponsorship, prior criminal history).
  - If numeric: returns integer string representing computed skill or total experience tenure (e.g., `"4"`).

- [ ] **Step 1: Write the failing test**

```python
def test_screening_solver_question_types():
    profile = {
        "name": "Rayen Ben Aissa",
        "skills": ["Python", "React"],
        "experience": [
            {"company": "Tech Corp", "role": "Engineer", "start": "2021-01", "end": "2025-01", "bullets": ["Python development"]}
        ],
        "work_authorization": "Authorized to work without sponsorship",
        "visa_sponsorship": "No"
    }
    # Boolean Yes
    res_auth = autofill.solve_screening_question("Are you legally authorized to work in the United States?", profile)
    assert res_auth["answer"].strip() in ["Yes", "Yes, I am legally authorized to work in the United States."]
    assert res_auth["question_type"] == "boolean"

    # Boolean No
    res_spons = autofill.solve_screening_question("Will you now or in the future require visa sponsorship?", profile)
    assert res_spons["answer"].strip() in ["No", "No, I do not require visa sponsorship."]
    assert res_spons["question_type"] == "boolean"

    # Numeric Years
    res_num = autofill.solve_screening_question("How many years of Python experience do you have?", profile)
    assert any(char.isdigit() for char in res_num["answer"])
    assert res_num["question_type"] == "numeric"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_jobright_extension_and_autofill.py::test_screening_solver_question_types -v`
Expected: FAIL

- [ ] **Step 3: Implement question classifier and targeted answers in `jh/autofill.py`**

In `solve_screening_question`:
- Add `detect_question_type(question)`: checks for boolean cues (`authorized to work`, `require sponsorship`, `are you at least`, `will you require`, `have you ever worked`), numeric cues (`how many years`, `years of experience`, `numeric`), or default to `narrative`.
- When boolean: extract direct Yes/No from candidate's profile/auth status.
- When numeric: return the candidate's exact computed years of experience for that skill or total tenure.
- When narrative: use the grounded STAR-L prompt and fallback.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_jobright_extension_and_autofill.py::test_screening_solver_question_types -v`
Expected: PASS

---

### Task 3: Extension API Endpoints with CORS & Verified Submission

**Files:**
- Modify: `jh/httpd.py:460-525`
- Test: `tests/test_jobright_extension_and_autofill.py`

**Interfaces:**
- Produces HTTP routes:
  - `GET /api/extension/status`: returns `{ success: True, profile_loaded: bool, candidate_name: str, active_resume: str }`
  - `POST /api/extension/payload`: accepts `{ "url": str, "job": dict (optional) }`, returns full payload with CORS headers.
  - `POST /api/extension/solve`: accepts `{ "question": str, "question_type": str, "job": dict }`, returns solved answer.
  - `POST /api/extension/confirm-applied`: accepts `{ "job_url": str, "company": str, "title": str, "notes": str }`, logs application in `tracker.upsert_application` with `status: "applied"`, returns `{ success: True, application_id: str, verified: True }`.

- [ ] **Step 1: Write the failing test**

```python
def test_extension_api_endpoints():
    from jh import httpd
    # 1. Status
    r_status = httpd.ROUTES[("GET", "/api/extension/status")]({}, {})
    assert r_status["success"] is True
    assert "candidate_name" in r_status

    # 2. Confirm applied
    r_confirm = httpd.ROUTES[("POST", "/api/extension/confirm-applied")]({}, {
        "job_url": "https://jobs.lever.co/cohere/intern-2027",
        "company": "Cohere",
        "title": "Software Engineer Intern (Winter 2027)",
        "source": "chrome_extension"
    })
    assert r_confirm["success"] is True
    assert r_confirm["verified"] is True
    assert "application_id" in r_confirm
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_jobright_extension_and_autofill.py::test_extension_api_endpoints -v`
Expected: FAIL (KeyError for routes)

- [ ] **Step 3: Implement extension routes and CORS handler in `jh/httpd.py`**

- In `jh/httpd.py`, register routes `@route("GET", "/api/extension/status")`, `@route("POST", "/api/extension/payload")`, `@route("POST", "/api/extension/solve")`, `@route("POST", "/api/extension/confirm-applied")`.
- In `do_OPTIONS` and response headers, ensure `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Headers: Content-Type, Authorization` are set for all `/api/extension/` and `/api/autofill/` requests.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_jobright_extension_and_autofill.py::test_extension_api_endpoints -v`
Expected: PASS

---

### Task 4: Standalone Chrome Extension (`extension/`)

**Files:**
- Create: `extension/manifest.json`
- Create: `extension/content.js`
- Create: `extension/flyout.css`
- Create: `extension/popup.html`
- Create: `extension/popup.js`
- Create: `extension/background.js`
- Create: `extension/icons/icon16.png`, `icon48.png`, `icon128.png`
- Create: `extension/README.md` (instructions for loading unpacked in Chrome/Edge)
- Test: `tests/test_extension_manifest_and_files.py`

**Interfaces:**
- The extension runs locally in Developer Mode.
- Matches the exact visual hierarchy of the user's Cohere screenshot:
  - Header: Logo `Jobright / JobHunter`, `? Feedback`, `⚙ Settings`, `>` minimize button.
  - Job card: Company tag, Title, Match Score pill (e.g. `96%`), `Your Insider Connections`.
  - Big Green `Autofill` button.
  - Expandable `Your Autofill Information` drawer.
  - `Upload Resume` with current resume name (`RAYEN BEN AISSA_...`) and `✦ Generate Custom Resume`.
  - `Upload Cover Letter` with `✦ Generate Cover Letter`.
  - Confirmation observer: Automatically detects success messages on submission, sends confirmation to `http://localhost:8080/api/extension/confirm-applied`.

- [ ] **Step 1: Write test verifying extension files and manifest V3 validity**

```python
# In tests/test_extension_manifest_and_files.py
import json
import pathlib

def test_manifest_v3_structure():
    ext_dir = pathlib.Path("extension")
    manifest_path = ext_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert "activeTab" in manifest["permissions"]
    assert "http://localhost:8080/*" in manifest["host_permissions"] or "<all_urls>" in manifest["host_permissions"]
    assert (ext_dir / "content.js").exists()
    assert (ext_dir / "flyout.css").exists()
    assert (ext_dir / "popup.html").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extension_manifest_and_files.py -v`
Expected: FAIL

- [ ] **Step 3: Create extension files**

- Create `extension/manifest.json` with Manifest V3 specifications.
- Create `extension/flyout.css` with clean, modern Jobright styling (green accents `#10b981`, `#059669`, rounded cards, clean typography, badge pills, responsive side flyout).
- Create `extension/content.js` with:
  - Synthetic event dispatcher (`input`, `change`, `blur`, React fiber value tracker bypass).
  - Platform detection (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, BambooHR, Taleo, iCIMS).
  - DOM form filler for text, textarea, select, radio, and checkboxes.
  - In-page flyout widget rendering matching the user's Cohere screenshot.
  - In-flight screening question solver integration with `http://localhost:8080/api/extension/solve`.
  - MutationObserver detecting submission confirmation and notifying `http://localhost:8080/api/extension/confirm-applied`.
- Create `extension/popup.html` and `extension/popup.js` for quick status and connection verification.
- Generate extension icons and create `extension/README.md` with simple 3-step setup instructions.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extension_manifest_and_files.py -v`
Expected: PASS

---

### Task 5: Webapp Recommendations UI Redesign to Jobright Split Feed

**Files:**
- Modify: `public/index.html` (recommendations tab layout)
- Modify: `public/styles.css` (split-view recommendation feed styles)
- Modify: `public/app.js` (rendering logic for recommendations feed and match details)
- Test: Verify DOM rendering and interactions

**Interfaces:**
- Renders Jobright-style split recommendation view on `#recommendations` tab:
  - Left feed: Recommended job cards with radial/pill match score (`96%`), role family, salary, location, and quick actions ("Apply & Autofill", "Save", "Dismiss").
  - Right pane: In-depth recommendation card with:
    - Match Score Gauge
    - "Why You're a Great Fit" bullet insights
    - Matched Skills (green pills) vs Missing Skills (neutral pills)
    - Experience & Seniority Fit
    - Action bar: "Open in ATS (Autofill with Extension)" button, "Download Tailored Resume", "View Cover Pitch".

- [ ] **Step 1: Inspect existing recommendations markup in `public/index.html` and `public/app.js`**
- [ ] **Step 2: Update `public/index.html` to add split-container layout for recommendations**
- [ ] **Step 3: Add CSS in `public/styles.css` for the Jobright-style feed and fit breakdown cards**
- [ ] **Step 4: Enhance `loadRecommendations` and `renderRecommendations` in `public/app.js` to populate the split feed, match score badges, and why-fit bullets**
- [ ] **Step 5: Test locally in browser / inspect markup**

---

### Task 6: Comprehensive Verification & Regression Testing

**Files:**
- Test: `tests/test_jobright_extension_and_autofill.py`
- Test: `tests/test_jobhunter.py`
- Test: `tests/test_audit_remediation.py`
- Test: `tests/test_ai_modernization_2026.py`

- [ ] **Step 1: Run all test suites across the repository**

Run: `python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Commit all changes**

```bash
git add .
git commit -m "feat: complete Jobright-style local Chrome extension, autofill engine, and recommendations feed"
```
