# Turnkey Clone-and-Run Flow & First-Run Resume Drop Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform JobHunter from a manual MCP install into a zero-friction clone-and-run repo featuring a root runner command (`run.py`, `run.bat`, `run.sh`), an auto-created `resumes/` drop folder with guidance, and a web dashboard First-Run Resume Wizard supporting Word (.docx), PDF (.pdf), and Text (.txt) uploads.

**Architecture:** A lightweight root runner orchestrates environment validation, SQLite initialization (`engine.db`), and local workspace directory provisioning (`resumes/` with `PUT_YOUR_RESUME_HERE.txt`). The HTTP daemon (`jh/httpd.py`) exposes endpoints for resume upload, folder inspection, and sync. The frontend (`public/`) provides a First-Run Wizard drag-and-drop zone with instant parsing, while an MCP auto-configurator bridges local Claude Desktop and Cursor installations to the repository.

**Tech Stack:** Python 3.11+, standard library (`http.server`, `json`, `pathlib`, `base64`, `subprocess`), Vanilla ES6 JavaScript, HTML5/CSS3.

**Spec:** `docs/superpowers/specs/2026-11-08-turnkey-clone-and-run-flow-design.md`

## Global Constraints

- Protected regions in `jh/sources/__init__.py`, `jh/pipeline.py`, and `jh/config.py` MUST NOT be modified (`tests/test_protected_linkedin.py` hash gate).
- Stdout must stay 100% clean for MCP stdio compatibility; all logs go to stderr.
- All HTTP REST responses must use `jh.mcp_helpers.envelope` formatting.
- The entire test suite `python -m pytest tests -q` must run offline and pass 100%.

## Review Focus

- Handling varied file encodings and formats for Word (.docx), PDF (.pdf), Text (.txt, .md).
- Security against directory traversal in uploaded file names.
- Graceful behavior when no browser is installed or running headlessly.
- Ensuring Windows SQLite file lock safety during tempfile cleanup.
- Safe JSON merging when updating existing `claude_desktop_config.json`.

---

### Task 1: Auto-Provision `resumes/` Directory and Instructional Guide

**Files:**
- Modify: `jh/workspace.py`
- Modify: `jh/config.py`
- Create: `tests/test_resume_drop_folder.py`

- [ ] **Step 1: Write test for `ensure_resumes_dir` and instructional guide**
  Create `tests/test_resume_drop_folder.py` asserting that `ensure_resumes_dir(workspace)` creates the `resumes/` folder, creates `PUT_YOUR_RESUME_HERE.txt` when no resumes exist, and does not overwrite existing user resumes.
- [ ] **Step 2: Run test to verify it fails**
  Run `python -m pytest tests/test_resume_drop_folder.py -q`.
- [ ] **Step 3: Implement `ensure_resumes_dir` in `jh/workspace.py`**
  Implement `ensure_resumes_dir` with human-friendly guidance explaining supported formats (.docx, .pdf, .txt, .md). Ensure `discover_resumes` prioritizes `resumes/`.
- [ ] **Step 4: Run test to verify it passes**
  Run `python -m pytest tests/test_resume_drop_folder.py -q`.

---

### Task 2: Backend REST Endpoints for Resume Upload, Rescan, and Folder Info

**Files:**
- Modify: `jh/httpd.py`
- Create: `tests/test_httpd_resume_upload.py`

- [ ] **Step 1: Write tests for resume upload, folder-info, and rescan**
  In `tests/test_httpd_resume_upload.py`, test:
  - `GET /api/resumes/folder-info` returns folder path, file count, and format guide.
  - `POST /api/resumes/upload` accepts base64-encoded Word (.docx), PDF (.pdf), and text (.txt), saves securely to `resumes/`, parses into SQLite profile, and sets it active.
  - `POST /api/resumes/scan` triggers a forced scan of `resumes/` and updates the profile variants.
- [ ] **Step 2: Run test to verify failure**
  Run `python -m pytest tests/test_httpd_resume_upload.py -q`.
- [ ] **Step 3: Implement endpoints in `jh/httpd.py`**
  Add handlers for `GET /api/resumes/folder-info`, `POST /api/resumes/upload`, and `POST /api/resumes/scan` using sanitized file names and `ResumeRegistry.scan_and_sync(force=True)`.
- [ ] **Step 4: Run test to verify it passes**
  Run `python -m pytest tests/test_httpd_resume_upload.py -q`.

---

### Task 3: First-Run UI Wizard in Web Dashboard (Word, PDF, TXT Dropzone)

**Files:**
- Modify: `public/index.html`
- Modify: `public/styles.css`
- Modify: `public/app.js`

- [ ] **Step 1: Add HTML markup for First-Run Wizard and Drag-and-Drop Zone**
  In `public/index.html`, add a `#first-run-wizard` container with:
  - Drag-and-drop dropzone for Word (`.docx`), PDF (`.pdf`), and Text (`.txt`).
  - Folder path badge with "Copy Folder Path" button.
  - Upload status indicator and parsed skills preview chips.
- [ ] **Step 2: Add styling for First-Run Wizard in `public/styles.css`**
  Add responsive, clean styles matching the dark modern theme for the dropzone, drag-over highlights, upload badge, and format icons.
- [ ] **Step 3: Implement client-side drag-and-drop and upload logic in `public/app.js`**
  In `public/app.js`, add `initFirstRunWizard()`:
  - Check if profiles count is 0 or no active profile exists; show wizard.
  - Handle dragover, dragleave, drop, and file input changes.
  - Read files via `FileReader` (base64 or text) and post to `/api/resumes/upload`.
  - Automatically refresh profiles and activate candidate facts on successful upload.
  - Add "Copy Path" action using `navigator.clipboard`.

---

### Task 4: Turnkey Root Runners (`run.py`, `run.bat`, `run.sh`) and MCP Auto-Configurator

**Files:**
- Create: `jh/mcp_configurator.py`
- Create: `run.py`
- Create: `run.bat`
- Create: `run.sh`
- Create: `tests/test_run_and_mcp_config.py`

- [ ] **Step 1: Write tests for `mcp_configurator.py`**
  In `tests/test_run_and_mcp_config.py`, test detection of Claude Desktop config path, Cursor mcp config path, and config injection without clobbering existing servers.
- [ ] **Step 2: Implement `jh/mcp_configurator.py`**
  Provide helper functions: `detect_claude_desktop_config()`, `register_claude_desktop()`, `register_cursor()`, `get_config_snippet()`.
- [ ] **Step 3: Implement `run.py` root runner**
  Root command script:
  - Validates Python >= 3.11.
  - Calls `ensure_resumes_dir()`.
  - Calls `db.init_db()`.
  - Scans resumes and prints summary.
  - Auto-configures MCP clients or displays snippet.
  - Starts HTTP daemon on port 8765.
  - Auto-launches Chromium with ATS extension loaded.
- [ ] **Step 4: Create `run.bat` and `run.sh` entry points**
  One-click Windows batch script and Unix shell script.
- [ ] **Step 5: Run tests for `mcp_configurator`**
  Run `python -m pytest tests/test_run_and_mcp_config.py -q`.

---

### Task 5: Documentation Update and Full Test Suite Verification

**Files:**
- Modify: `tests/test_mcp_server.py` (add garbage collection in tearDown to prevent Windows SQLite file lock during test cleanup)
- Modify: `README.md` (Update quick start to highlight the 1-command `git clone && python run.py` / `run.bat` flow)

- [ ] **Step 1: Fix Windows SQLite file cleanup in `tests/test_mcp_server.py`**
  Add explicit `gc.collect()` before `self.temp_dir.cleanup()`.
- [ ] **Step 2: Update `README.md`**
  Add clear, prominent instructions for the 1-command clone-and-run workflow.
- [ ] **Step 3: Run the entire test suite**
  Execute `python -m pytest tests -q` and verify all tests pass 100%.

