# Design Spec: Jobright-Style Local Chrome Extension & Autofill Engine

**Date:** 2026-10-23  
**Status:** In Review  
**Target Delivery:** JobHunter v2026.10  

---

## 1. Intent & The Why

JobHunter already has an intelligent job-matching, resume tailoring, and screening-question solver engine. However, auto-filling real-world job applications on external Applicant Tracking Systems (ATS) like Workday, Greenhouse, Lever, Ashby, BambooHR, and SmartRecruiters presents severe limitations when attempted purely from a web browser tab or bookmarklet:
1. **Browser Security Sandboxing (Cross-Origin Policy):** A web application running at `http://localhost:8080` is strictly prevented by browser security (Same-Origin Policy, `X-Frame-Options: DENY`) from accessing, inspecting, or typing into form fields on external ATS domains (`*.myworkdayjobs.com`, `boards.greenhouse.io`, `jobs.lever.co`).
2. **Content Security Policy (CSP) Restrictions on Bookmarklets:** Modern enterprise ATS portals inject strict `Content-Security-Policy` headers that block execution of `javascript:` bookmarklets or third-party DOM injectors.
3. **Application Verification Impossibility:** Background headless bots get blocked by Cloudflare, CAPTCHAs, and multi-factor applicant logins. Neither pure backend scrapers nor pure frontend webapps can verify with 100% certainty whether an application was truly submitted.
4. **The Jobright Model:** As proven by **Jobright.ai** (and seen in the reference screenshot of Jobright's companion on Cohere's job board), the state-of-the-art architecture combines:
   - A **Local Backend & Webapp** for job curation, profile modeling, AI resume tailoring, and centralized pipeline tracking.
   - A **Companion Browser Extension (Manifest V3)** that runs directly in the candidate's browser on any ATS tab with `host_permissions: ["<all_urls>"]`. It renders a side panel / floating copilot, fills forms in 1 click using synthetic React-safe event dispatching, solves screening questions on-the-fly via the local AI backend, detects the submission confirmation screen, and pings the local server to guarantee **100% verified application status**.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Full Backend Autofill Remediation:**
  - Enrich `jh/autofill.py` and `get_autofill_payload()` to include structured multi-position work history and multi-degree education arrays (required by Workday, Taleo, iCIMS).
  - Add deterministic calculation for total years of experience and skill-specific experience years (for numeric screening inputs).
  - Support candidate-configurable work authorization, visa sponsorship, and EEO demographics.
  - Upgrade `solve_screening_question()` to categorize question types (Yes/No boolean, numeric years, short text, behavioral STAR) and return appropriately structured answers.
  - Provide dedicated, robust extension API endpoints with CORS and token verification (`/api/extension/status`, `/api/extension/payload`, `/api/extension/solve`, `/api/extension/confirm-applied`).
- **Production-Ready Unpacked Chrome Extension (`extension/`):**
  - Modern Manifest V3 extension ready to load unpacked in Chrome or Edge (`chrome://extensions` -> Load unpacked).
  - Injects a side panel / floating flyout matching the Jobright reference screenshot:
    - Target job header with Company, Role, and Match Score badge (e.g. `96%`).
    - Prominent green **`Autofill`** button that populates all detected ATS form fields in 1 click.
    - `Your Autofill Information` expandable drawer to review candidate details.
    - `Upload Resume` with current resume name and `✦ Generate Custom Resume` button.
    - `Upload Cover Letter` with `✦ Generate Cover Letter` button.
    - In-page screening question assistant.
  - Monitors the active tab for post-submission confirmation (e.g. "Application Submitted", confirmation URL redirects) and sends a verified ping to the local JobHunter database.
- **Jobright-Style Recommendations Webapp Experience:**
  - Enhance JobHunter's Recommendations view (`#recommendations` or `/jobs/recommend?id=...`) to feature a two-pane split layout:
    - Left column: Curated recommendation feed with match scores, key fit highlights ("96% Match • Senior Full Stack"), salary, and quick actions.
    - Right pane: In-depth fit breakdown (Why You're a Fit, Matched Skills vs Missing Skills pills, Experience breakdown), 1-click tailored resume preview, and "Open & Autofill with Extension" launch action.

### Non-Goals
- Publishing the extension to the official public Chrome Web Store (the extension runs locally unpacked in developer mode connected to `localhost:8080`).
- Fully automated headless bot submissions that attempt to bypass CAPTCHAs without human oversight (Jobright's model is semi-supervised 1-click assist, ensuring candidate safety and zero anti-bot bans).

### Anti-Goals
- Do not introduce external cloud telemetry or third-party data tracking. All profile data and API communication remain 100% local between the user's browser and `http://localhost:8080`.
- Do not break backward compatibility with the existing JobHunter webapp, bookmarklet fallback, or test suite (all 117+ existing tests must continue to pass).

---

## 3. Approaches Considered & Selected

### Approach 1: Complete Jobright-Style Local Ecosystem (SELECTED)
- **Backend**: Fix all payload gaps, add work history / education arrays, numeric/boolean screening solvers, and dedicated extension API routes.
- **Extension**: Build a standalone Manifest V3 extension in `extension/` that can be loaded in 10 seconds, matching the exact Jobright UI provided in the user's screenshot.
- **Webapp**: Redesign the recommendations view into a modern two-pane split layout matching `jobright.ai/jobs/recommend`.
- **Trade-off**: Requires touching backend, creating the extension directory, and updating the recommendation UI, but delivers the exact complete feature requested.

### Approach 2: Backend + Extension Only (No Webapp Changes)
- Fix backend gaps and build the extension, but leave the webapp's existing cards as-is.
- **Trade-off**: Misses the user's explicit request for the `jobright.ai/jobs/recommend` UI experience.

### Approach 3: Webapp & Bookmarklet Only (No Extension)
- Improve the bookmarklet script and webapp modal without creating an extension.
- **Trade-off**: Strictly impossible to 100% verify submission due to browser security, blocked by CSP on Workday/Lever, and cannot attach resume files.

---

## 4. Technical Architecture & Component Design

```
+-----------------------------------------------------------------------------------+
|                                 USER BROWSER                                      |
|                                                                                   |
|  +---------------------------+       +-----------------------------------------+  |
|  |     JobHunter Webapp      |       |             External ATS Tab            |  |
|  |  (http://localhost:8080)  |       |   (boards.greenhouse.io, workday, etc)  |  |
|  |                           |       |                                         |  |
|  |  +---------------------+  |       |  +-----------------------------------+  |  |
|  |  | Jobright-Style Feed |  |       |  | ATS Application Form              |  |  |
|  |  | - 96% Match Scores  |  |       |  | (Name, Email, History, Questions) |  |  |
|  |  | - Fit Breakdown     |  |       |  +-----------------------------------+  |  |
|  |  | - Skill Pills       |  |       |                                         |  |
|  |  +---------------------+  |       |  +-----------------------------------+  |  |
|  +-------------+-------------+       |  | JobHunter Chrome Extension         |  |  |
|                |                     |  | Side Panel / Injected Flyout      |  |  |
|                |                     |  | (Exact Jobright Cohere Design)    |  |  |
|                |                     |  | - 96% Match Badge                 |  |  |
|                |                     |  | - [Autofill] Big Green Button     |  |  |
|                |                     |  | - Resume & Cover Letter Tailoring |  |  |
|                |                     |  | - 100% Confirmed Submission Check |  |  |
|                |                     |  +-----------------+-----------------+  |  |
|                |                     +--------------------+--------------------+  |
+----------------+------------------------------------------+-----------------------+
                 |                                          |
                 | Fetch Jobs, Tailor, Status               | Sync Payload, Solve Questions,
                 |                                          | Confirm Application
                 v                                          v
+-----------------------------------------------------------------------------------+
|                       JOBHUNTER LOCAL BACKEND (Python 3)                          |
|                                                                                   |
|   +-----------------------+   +----------------------+   +---------------------+  |
|   |      jh/httpd.py      |   |    jh/autofill.py    |   |     jh/refit.py     |  |
|   | /api/extension/*      |   | - Multi-Job Arrays   |   | - LLM Tailoring     |  |
|   | /api/autofill/*       |   | - Skill Years Calc   |   | - Grounded Answers  |  |
|   | /api/recommendations  |   | - Boolean/Num Solver |   | - Anti-Slop Star-L  |  |
|   +-----------+-----------+   +----------+-----------+   +----------+----------+  |
|               |                          |                          |             |
|               +--------------------------+--------------------------+             |
|                                          |                                        |
|                                          v                                        |
|                             +--------------------------+                          |
|                             |  jh/db.py & tracker.py   |                          |
|                             |  Applications Tracker    |                          |
|                             |  100% Confirmed History  |                          |
|                             +--------------------------+                          |
+-----------------------------------------------------------------------------------+
```

---

## 5. Detailed Component Specifications

### A. Backend Enhancements (`jh/autofill.py` & `jh/httpd.py`)
1. **Extended Payload Structure (`get_autofill_payload`)**:
   - `work_history`: Array of structured objects `[{ company, title, start_date, end_date, is_current, location, description, bullets }]`.
   - `education_history`: Array of structured objects `[{ institution, degree, field_of_study, start_year, graduation_year, gpa }]`.
   - `skill_years`: Dictionary mapping identified skills to calculated years of experience based on work experience chronology (e.g. `{"python": 4, "react": 3, "fastapi": 2}`).
   - `total_years_experience`: Deterministic sum of professional tenure in years.
   - `legal_and_eeo`: Structured candidate preferences:
     - `authorized_us`, `require_sponsorship_now`, `require_sponsorship_future`
     - `gender`, `race_ethnicity`, `veteran_status`, `disability_status` (defaults to "Decline to self-identify" unless specified in profile).
   - `address_components`: Discrete `street_address`, `city`, `state_province`, `postal_code`, `country`.
2. **Question-Type-Aware Screening Solver (`solve_screening_question`)**:
   - Detects question pattern:
     - **Boolean / Radio (Yes/No)**: Returns `"Yes"` or `"No"` with high confidence for authorization, 18+ age, or background checks.
     - **Numeric (Years / Integer)**: Returns clean numeric integer string (e.g. `"4"`) matching candidate's calculated skill tenure.
     - **Short Answer (1 sentence)**: e.g. Notice period or location preference.
     - **Behavioral / Technical (STAR-L)**: 60-120 words grounded in verified profile facts without markdown or hallucinated technologies.
3. **Dedicated Extension Endpoints (`jh/httpd.py`)**:
   - `GET /api/extension/status`: Healthcheck & active candidate profile summary.
   - `POST /api/extension/payload`: Returns full ATS autofill payload for the active job URL/domain.
   - `POST /api/extension/solve`: Solves on-the-fly screening questions directly from the extension.
   - `POST /api/extension/confirm-applied`: Receives confirmation payload `{ job_url, company, title, applied_at, source: "extension_confirmed" }` and upserts application status to `applied` with `is_verified: true`.
   - All extension routes support standard CORS headers (`Access-Control-Allow-Origin: *`, `Access-Control-Allow-Headers: Content-Type, Authorization`).

### B. Chrome Extension Architecture (`extension/`)
1. **`manifest.json` (Manifest V3)**:
   - `name`: "JobHunter AI Autofill & Copilot"
   - `permissions`: `["activeTab", "scripting", "storage"]`
   - `host_permissions`: `["<all_urls>", "http://localhost:8080/*", "http://127.0.0.1:8080/*"]`
   - `action`: `default_popup: "popup.html"`
   - `content_scripts`: Injected into ATS domains (`*://*.greenhouse.io/*`, `*://*.lever.co/*`, `*://*.ashbyhq.com/*`, `*://*.myworkdayjobs.com/*`, `*://*.smartrecruiters.com/*`, `*://*.workable.com/*`, `*://*.bamboohr.com/*`, `*://*.taleo.net/*`, `*://*.icims.com/*`, `*://*.jobvite.com/*`, etc.).
2. **Extension Content Script & Flyout UI (`content.js`, `flyout.css`)**:
   - Renders a floating Jobright-style slide-over panel on the right side of the ATS page (exact match to user screenshot):
     - Top banner: `⚡ JobHunter Local AI • 100% Free & Unlimited Credits`.
     - Brand Header: JobHunter logo + title + Settings icon + Minimize toggle.
     - Target Job Card: Company name, Industry/Tag, Match Score pill (e.g. `96%`), Role title, and Applicant metadata.
     - Big Green `Autofill` button:
       - Triggers synthetic event dispatching across text, select, radio, checkbox, and contenteditable fields.
       - Dispatches `input`, `change`, and `blur` events, invoking `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set` to ensure React 16+ virtual DOM tracking syncs properly.
       - Highlights populated fields with subtle green glow (`#10b981`).
     - `Your Autofill Information` expandable drawer:
       - Displays candidate's active details (Name, Contact, Education, Work Auth, Socials) with 1-click copy icons.
     - `Upload Resume` drawer:
       - Displays active resume filename (e.g. `RAYEN BEN AISSA_Full Stack AI Engineer_20261002`).
       - `✦ Generate Custom Resume` button: Calls local backend to generate tailored 6-second resume variant.
     - `Upload Cover Letter` drawer:
       - Displays `✦ Generate Cover Letter` button: Calls local backend to generate tailored cover letter and auto-injects it into the ATS pitch textarea.
     - Automated Confirmation Detection:
       - Observes DOM mutations and URL changes for completion indicators (e.g. `contains('Application submitted')`, `contains('Thank you for applying')`, `/confirmation`, `/applied`).
       - On detection, notifies backend `/api/extension/confirm-applied`, changes extension status to `✓ 100% Verified Applied`, and triggers celebratory UI feedback.

### C. Webapp Recommendations UI (`public/app.js`, `public/styles.css`, `public/index.html`)
1. **Split-Feed Layout (Jobright.ai Style)**:
   - Left Column: Recommendation cards sorted by Match Score (e.g. 96%, 92%, 88%).
     - Badges: Match Score radial/pill, Role Family tag, Salary, Location (Remote/Hybrid).
     - Quick Actions: `1-Click Apply`, `Autofill`, `Save`, `Dismiss`.
   - Right Pane: Selected Job Recommendation Detail:
     - Header: Company title, role, match score.
     - Fit Breakdown Card:
       - Overall Match % score meter.
       - "Why You're a Great Fit" (bullet points computed from candidate profile vs job requirements).
       - Matched Skills (green pills) vs Missing/Growth Skills (subtle neutral pills).
       - Experience & Seniority alignment.
     - Action Bar:
       - "Apply on Company Site" button (opens the ATS link with instructions to click Autofill in the extension).
       - "Download Tailored Resume" & "View Cover Letter".
       - In-App Autofill Palette & Screening Solver modal fallback (for users without the extension).

---

## 6. What's Left to the Builder
- Detailed DOM selectors for edge-case ATS variations (e.g. nested shadow DOM in custom enterprise Workday portals).
- Exact animation timings for the extension slide-in panel (250ms ease-out).
- Local storage caching inside the extension for offline fallback.

---

## 7. Verification Plan
1. **Automated Unit & Integration Tests**:
   - Test extended payload generation (`work_history`, `education_history`, `skill_years`, `legal_and_eeo`).
   - Test question-type solver categorization (Yes/No, numeric years, STAR narrative).
   - Test new HTTP extension endpoints (`/api/extension/status`, `/api/extension/payload`, `/api/extension/solve`, `/api/extension/confirm-applied`).
   - Verify all 109 existing tests in `test_jobhunter.py` and 8 in `test_ai_modernization_2026.py` continue to pass.
2. **Browser Extension Verification**:
   - Inspect `extension/manifest.json` for Manifest V3 compliance.
   - Verify content script injection, synthetic event dispatching, and communication with `http://localhost:8080`.
3. **UI Visual & Functional Review**:
   - Validate the extension flyout visual hierarchy, typography, colors, and layout against the user's reference screenshot.
   - Test recommendation feed responsiveness and detail view rendering.
