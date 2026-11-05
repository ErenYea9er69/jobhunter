# Unified Frontend, Extension, Desktop & Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the JobHunter MCP engine with a modernized local HTTP daemon (`jh/httpd.py`), a clean 5-tab web dashboard (`public/`), a Manifest V3 ATS autofill browser extension (`extension/`), and a zero-dependency desktop launcher (`desktop.py`) with 100% test pass rate.

**Architecture:** Maintain clean separation between the MCP stdio protocol and the REST HTTP daemon. Both share the same underlying SQLite database (`engine.db`), `OutputStore`, `jh.tracker`, `jh.screening`, and `jh.team` modules. All REST generation endpoints pass drafts through Reviewer QA (`jh.team.qa`), and responses are serialized in the standard `jh.mcp_helpers.envelope` format.

**Tech Stack:** Python 3.10+, Standard Library (`http.server`, `subprocess`, `winreg`, `sqlite3`, `urllib`), Chrome Manifest V3, HTML5/CSS3/Vanilla ES6.

**Spec:** [`docs/superpowers/specs/2026-11-05-unified-frontend-extension-engine-design.md`](file:///c:/Users/hp/Desktop/jobhunter/docs/superpowers/specs/2026-11-05-unified-frontend-extension-engine-design.md)

---

## Global Constraints

- **Protected Code**: `LinkedInGuest` and `LINKEDIN_GEO_MAP` in `jh/sources/__init__.py`, LinkedIn radar in `jh/pipeline.py`, and `get_linkedin_scrape_depth`/`get_linkedin_incremental_minutes` in `jh/config.py` MUST NOT be modified (enforced by `tests/test_protected_linkedin.py`).
- **No stdout pollution**: MCP stdout must stay completely clean. `jh/httpd.py` and `desktop.py` must never log to stdout; all server and daemon logs must go to stderr or file.
- **Envelope Standard**: All REST endpoints must return data wrapped in `jh.mcp_helpers.envelope` (`{"status": "ok", "success": true, "data": {...}, "warnings": [...]}`).
- **Reviewer QA Gate**: Every generated document and screening answer served over HTTP must pass through `jh.team.qa.verify_document()` before returning to clients.
- **Zero External Dependencies**: The HTTP daemon, browser launcher, and desktop runner must rely solely on the Python Standard Library.
- **Offline Test Suite**: `python -m pytest tests -q` must run 100% offline and pass completely.

---

## Review Focus

1. **Dictionary Slicing in `screening.py`**: When `job.get("required_skills")` is a dict of `{skill: weight}`, slicing with `[:8]` raises `KeyError: slice(None, 8, None)`. The fix must safely extract keys before slicing.
2. **CORS Headers for Browser Extension**: Browser extensions making `fetch` requests from arbitrary ATS origin pages require permissive CORS headers (`Access-Control-Allow-Origin: *`, `Access-Control-Allow-Headers: Content-Type, Authorization`, `Access-Control-Allow-Methods: GET, POST, OPTIONS`).
3. **Paths with Spaces on Windows**: Paths like `C:\Program Files\...` passed to `--load-extension` or browser subprocess commands must be safely quoted without breaking argument vectors.
4. **Manifest V3 Service Worker Lifecycle**: The extension background worker in MV3 terminates after 30 seconds of inactivity; API requests from content scripts must handle potential wake-up or connection timeouts gracefully.
5. **Static File Directory Traversal**: `jh/httpd.py` serving static assets from `public/` must strictly enforce that requested paths resolve inside `public/` and prevent `../` directory traversal attacks.

---

## Tasks

### Task 1: Fix Screening Skill Slicing Bug & Harmonize Legacy Tests

**Files:**
- Modify: `jh/screening.py:230-233`
- Modify: `tests/integration/test_mcp_tools_catalog.py`
- Modify: `tests/security/test_security_policies.py`
- Modify: `tests/test_filestore.py`
- Modify: `tests/unit/test_dedup_and_scoring.py`
- Modify: `tests/unit/test_schemas_and_envelope.py`
- Test: `python -m pytest tests -q`

**Interfaces:**
- Consumes: `jh.screening.solve_screening_question(question, profile, job, use_llm)`
- Produces: 100% green pytest execution across the entire test suite.

- [ ] **Step 1: Verify the failing test in `test_team.py`**

Run: `python -m pytest tests/test_team.py -k test_apply_flow_reviews_every_document_and_saves_approved_files -q`
Expected: FAIL with `KeyError: slice(None, 8, None)`.

- [ ] **Step 2: Fix `jh/screening.py` line 231**

In `jh/screening.py`, change:
```python
"required_skills": job.get("required_skills", [])[:8],
```
to:
```python
"required_skills": list(job.get("required_skills", {}).keys() if isinstance(job.get("required_skills"), dict) else job.get("required_skills", []))[:8],
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `python -m pytest tests/test_team.py -k test_apply_flow_reviews_every_document_and_saves_approved_files -q`
Expected: PASS.

- [ ] **Step 4: Update legacy imports in old test files**

In `tests/integration/test_mcp_tools_catalog.py`, `tests/security/test_security_policies.py`, and `tests/test_filestore.py`, update imports from `from jh.filestore import FileStore` to use `OutputStore` or the appropriate new storage interfaces.
In `tests/unit/test_schemas_and_envelope.py`, update `from jh.mcp_tools import _tool_envelope` to `from jh.mcp_helpers import envelope`.
In `tests/unit/test_dedup_and_scoring.py`, update deduplication function imports to match `jh.dedup`.

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest tests -q`
Expected: Return code 0 (100% passed).

- [ ] **Step 6: Verify protected LinkedIn hashes**

Run: `python -m pytest tests/test_protected_linkedin.py -q`
Expected: PASS (hashes untouched).

- [ ] **Step 7: Commit**

```bash
git add jh/screening.py tests/
git commit -m "fix(screening): safely extract skill keys and harmonize legacy test suite imports"
```

---

### Task 2: Extension Installer & Chromium Browser Auto-Launcher

**Files:**
- Create: `jh/extension_installer.py`
- Test: `tests/test_extension_installer.py`

**Interfaces:**
- Consumes: `os`, `sys`, `winreg`, `subprocess`, `urllib`
- Produces:
  - `find_extension_dir() -> Path`
  - `detect_chromium_browsers() -> list[dict[str, str]]`
  - `launch_browser_with_extension(url: str = "http://127.0.0.1:8765", browser_name: str = "") -> dict[str, Any]`
  - `copy_extension_path_to_clipboard() -> bool`

- [ ] **Step 1: Write the failing test for `extension_installer.py`**

Create `tests/test_extension_installer.py`:
```python
import os
from jh.extension_installer import find_extension_dir, detect_chromium_browsers

def test_find_extension_dir():
    d = find_extension_dir()
    assert d.is_dir()
    assert (d / "manifest.json").is_file()

def test_detect_chromium_browsers():
    browsers = detect_chromium_browsers()
    assert isinstance(browsers, list)
    if os.name == "nt":
        assert any(b["name"] in ("edge", "chrome", "brave") for b in browsers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extension_installer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'jh.extension_installer'`.

- [ ] **Step 3: Implement `jh/extension_installer.py`**

Implement Windows registry inspection for Edge, Chrome, and Brave, path resolution for `extension/`, process spawning with `--load-extension` flag, and clipboard copy fallback.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extension_installer.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jh/extension_installer.py tests/test_extension_installer.py
git commit -m "feat(extension): implement chromium detection and extension auto-launcher"
```

---

### Task 3: Modernized HTTP Daemon & REST API Layer

**Files:**
- Create: `jh/httpd.py`
- Test: `tests/test_httpd.py`

**Interfaces:**
- Consumes: `jh.tracker`, `jh.screening`, `jh.resume_registry`, `jh.pipeline`, `jh.team.qa`, `jh.extension_installer`, `jh.mcp_helpers`
- Produces:
  - `start_server(host: str = "127.0.0.1", port: int = 8765, ws_dir: str = ".") -> ThreadingHTTPServer`
  - REST endpoints for extension, profiles, jobs, applications, and desktop hub.

- [ ] **Step 1: Write the failing tests for `jh/httpd.py`**

Create `tests/test_httpd.py` testing:
- `/api/extension/status` returns `{success: true, data: {status: "ok", active_profile: ...}}`
- `/api/extension/payload` returns candidate details and resume file path
- `/api/extension/solve` passes output through Reviewer QA
- `/api/applications` lists and updates applications in SQLite
- Static asset serving safely denies directory traversal attempts (`/../../secret.txt`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_httpd.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'jh.httpd'`.

- [ ] **Step 3: Implement `jh/httpd.py`**

Implement `ThreadingHTTPServer` and `BaseHTTPRequestHandler` with:
- Standardized CORS handling for `OPTIONS`, `GET`, `POST`.
- Envelope serialization via `jh.mcp_helpers.envelope`.
- Route dispatch table for all required endpoints.
- Path sanitization for static file serving out of `public/`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_httpd.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jh/httpd.py tests/test_httpd.py
git commit -m "feat(httpd): implement lightweight rest daemon with reviewer qa and tracker support"
```

---

### Task 4: ATS Autofill & Copilot Browser Extension (Manifest V3)

**Files:**
- Create: `extension/manifest.json`
- Create: `extension/content.js`
- Create: `extension/flyout.css`
- Create: `extension/background.js`
- Create: `extension/popup.html`
- Create: `extension/popup.js`
- Test: `tests/test_extension_bundle.py`

**Interfaces:**
- Consumes: `http://127.0.0.1:8765/api/extension/*`
- Produces:
  - Valid Chrome MV3 extension package.
  - Floating copilot badge and 1-click form autofill for Greenhouse, Lever, Workday, Ashby, BambooHR.

- [ ] **Step 1: Write validation test for extension files and manifest syntax**

Create `tests/test_extension_bundle.py` checking:
- `manifest.json` is valid JSON, specifies `manifest_version: 3`, and defines correct permissions.
- Referenced content scripts, background worker, and popup files exist on disk.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extension_bundle.py -q`
Expected: FAIL (files missing).

- [ ] **Step 3: Implement `extension/manifest.json`, `content.js`, `background.js`, `flyout.css`, `popup.html`, `popup.js`**

- `manifest.json`: Manifest V3 config.
- `content.js`: Injects non-intrusive floating pill; inspects inputs, textareas, selects; matches common ATS selectors (`input[name*="first_name"]`, `input[name*="email"]`, etc.); queries `/api/extension/payload` and triggers native DOM input events (`dispatchEvent(new Event('input'))`); auto-solves screening questions via `/api/extension/solve`; intercepts submission to notify `/api/extension/confirm-applied`.
- `background.js`: Service worker proxying fetch calls to `http://127.0.0.1:8765`.
- `popup.html` / `popup.js`: Shows connection status and active profile.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extension_bundle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add extension/ tests/test_extension_bundle.py
git commit -m "feat(extension): implement manifest v3 ats autofill and copilot extension"
```

---

### Task 5: Web Dashboard Single Page Application (5-Tab Modern UI)

**Files:**
- Create: `public/index.html`
- Create: `public/styles.css`
- Create: `public/app.js`
- Test: `tests/test_frontend_assets.py`

**Interfaces:**
- Consumes: `/api/search`, `/api/profiles`, `/api/applications`, `/api/desktop/*`, `/api/extension/status`
- Produces: Complete responsive dark-mode 5-tab user interface.

- [ ] **Step 1: Write test validating frontend HTML/JS structure**

Create `tests/test_frontend_assets.py` verifying that:
- `public/index.html` loads without template errors and contains hooks for all 5 tabs.
- `public/styles.css` and `public/app.js` exist and are valid.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_frontend_assets.py -q`
Expected: FAIL (assets missing).

- [ ] **Step 3: Implement `public/index.html`, `public/styles.css`, and `public/app.js`**

Implement the 5 tabs:
1. **Radar & Job Search**: Query input, location filter, cards with match score, skills breakdown, apply link.
2. **Profiles & Resumes**: Active candidate profile selector, parsed skill chips, experience timeline.
3. **Application Kanban Tracker**: Columns for `Saved`, `Applied`, `Interview`, `Offer`, `Rejected`, with one-click status movement, follow-up alerts, and notes.
4. **Document Studio**: Interactive viewer for tailored cover letters and interview prep guides.
5. **Extension & Desktop Hub**: Extension connection indicator, 1-click browser launch button, and installation guides.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_frontend_assets.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add public/ tests/test_frontend_assets.py
git commit -m "feat(ui): implement modern 5-tab web dashboard for job hunting and extension management"
```

---

### Task 6: Desktop Runner CLI & Background Launcher

**Files:**
- Create: `desktop.py`
- Test: `tests/test_desktop_launcher.py`

**Interfaces:**
- Consumes: `jh.httpd.start_server`, `jh.extension_installer.launch_browser_with_extension`
- Produces: Standalone desktop runner with CLI options (`--port`, `--launch-browser`, `--install-extension`, `--no-browser`).

- [ ] **Step 1: Write test for desktop CLI flags**

Create `tests/test_desktop_launcher.py` verifying `--help`, `--port`, and launcher argument parsing.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_desktop_launcher.py -q`
Expected: FAIL with `FileNotFoundError: desktop.py`.

- [ ] **Step 3: Implement `desktop.py`**

Parse CLI arguments:
- Default: Starts HTTP server in background thread, calls `launch_browser_with_extension("http://127.0.0.1:8765")`, and runs an event loop until Ctrl+C.
- `--install-extension`: Opens browser extension management page.
- Log strictly to stderr, keeping stdout clean.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_desktop_launcher.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add desktop.py tests/test_desktop_launcher.py
git commit -m "feat(desktop): implement zero-dependency desktop runner and browser auto-launcher"
```

---

### Task 7: End-to-End System Verification & Final Polish

**Files:**
- Modify: `README.md` (add Desktop & Extension usage instructions)
- Test: Full test suite and live daemon smoke test

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests -q`
Expected: 100% PASS with 0 failures and 0 errors.

- [ ] **Step 2: Verify protected LinkedIn scraper hashes**

Run: `python -m pytest tests/test_protected_linkedin.py -q`
Expected: PASS.

- [ ] **Step 3: Verify MCP server startup clean protocol**

Run: `python mcp_server.py --help` or pipe check to ensure stdout is pristine.

- [ ] **Step 4: Update `README.md` with Desktop & Extension usage**

Document how to launch `python desktop.py` and connect the browser extension.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document desktop launcher and browser extension setup"
```

