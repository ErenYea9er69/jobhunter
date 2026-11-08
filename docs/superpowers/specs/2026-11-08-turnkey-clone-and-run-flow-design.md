# Design Document: Turnkey Clone-and-Run Flow, First-Run Resume Drop Folder & UI Wizard

**Date:** 2026-11-08  
**Status:** Approved  
**Target Architecture:** Zero-friction GitHub clone runner (`run.py`, `run.bat`, `run.sh`) + Auto-initialized `resumes/` drop folder with guidance + Browser-based drag-and-drop First-Run Resume Wizard supporting Word (.docx), PDF (.pdf), and Text (.txt) + Auto-connect MCP & SQLite database.

---

## 1. Intent and Why

Previously, JobHunter expected users to manually install an MCP server via `uvx` and manually configure JSON snippets in `claude_desktop_config.json`, which was confusing and required manual setup steps before seeing anything work.

The goal is to switch JobHunter into a 1-command turnkey system:
A user clones the repository from GitHub and runs one command (e.g. `python run.py` or double-clicks `run.bat` on Windows or runs `./run.sh` on macOS/Linux). 

The command automatically:
1. Bootstraps dependencies and initializes the SQLite database (`engine.db`).
2. Creates the dedicated `resumes/` folder populated with an instructional `PUT_YOUR_RESUME_HERE.txt` guide.
3. Automatically sets up / bridges MCP server configuration for popular AI clients (Claude Desktop, Cursor, Antigravity) pointing directly to the local clone.
4. Starts the local HTTP daemon on `127.0.0.1:8765` serving the Web Dashboard.
5. Automatically launches the Chromium browser (Chrome, Edge, Brave) with the ATS extension pre-loaded (`--load-extension`).
6. Delivers a First-Run Resume Onboarding Wizard inside the Web Dashboard: if no resume is found yet, a clean, welcoming drag-and-drop zone allows users to upload Word (`.docx`), PDF (`.pdf`), or Text (`.txt`) resumes right in the browser, parsing candidate facts into SQLite and instantly unlocking the full copilot suite.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **1-Command Zero-Setup**: A single command (`python run.py`, `run.bat`, `./run.sh`) does complete environment check, SQLite initialization, directory structure creation, MCP configuration, and launches the dashboard and extension.
- **Dedicated Drop Folder**: Auto-create `resumes/` in the workspace root with `resumes/PUT_YOUR_RESUME_HERE.txt` detailing supported formats: Word (.docx), PDF (.pdf), Text (.txt, .md).
- **First-Run UI Wizard**: The web dashboard detects when no resumes exist and renders an intuitive First-Run Wizard with drag-and-drop file upload, file format validation, and local folder path indicators with copy-to-clipboard.
- **Support for Word, PDF, and TXT**: Seamless extraction and parsing of `.docx`, `.pdf`, and `.txt`/`.md` files via REST endpoints `/api/resumes/upload` and `/api/resumes/scan`.
- **MCP Auto-Registration**: Setup helper inspects installed AI tools (Claude Desktop config, Cursor config) and offers/executes 1-click registration of the JobHunter MCP server so the AI model shares the exact same database.
- **Preserve Protected Scrapers**: Strictly protect LinkedIn scraping routines in `jh/sources/__init__.py`, `jh/pipeline.py`, and `jh/config.py`.

### Non-Goals
- Altering the protected LinkedIn scraper logic or test hashes.
- Changing MCP stdio JSON-RPC protocol contracts.
- Requiring cloud authentication or external telemetry.

### Anti-Goals
- No stdout pollution (all server logs on stderr).
- No silent failures during resume uploads; provide immediate visual feedback and parsed skill previews.

---

## 3. Architecture & Components

### 3.1 Workspace & Folder Provisioning (`jh/workspace.py`)
- Introduce `ensure_resumes_dir(workspace_path: Path) -> Path`:
  - Ensures `<workspace>/resumes/` directory exists.
  - Creates `PUT_YOUR_RESUME_HERE.txt` if the folder has no resumes, containing human-friendly formatting and placement instructions.
- Ensure `discover_resumes()` checks `resumes/` first, supporting `.docx`, `.pdf`, `.txt`, `.md`.

### 3.2 Backend REST Endpoints (`jh/httpd.py`)
- `POST /api/resumes/upload`:
  - Accepts JSON payload containing `{ "filename": str, "content_base64": str }` or `{ "filename": str, "text": str }`.
  - Saves file securely into `<workspace>/resumes/<filename>`.
  - Calls `registry.scan_and_sync(force=True)`.
  - Saves parsed profile into SQLite (`db.save_profile`), sets as active resume.
  - Returns parsed profile summary (`name`, `target_title`, `skills`, `experience_years`).
- `POST /api/resumes/scan`:
  - Triggers on-demand re-scan of `resumes/` and workspace.
  - Returns updated variants list and count.
- `GET /api/resumes/folder-info`:
  - Returns absolute path of `resumes/`, file count, and status.

### 3.3 Dashboard First-Run UI Wizard (`public/index.html` & `public/app.js`)
- **First-Run Wizard Component**:
  - Automatically displayed at the top of the app or in the Profile tab when 0 resume profiles are detected.
  - Drag-and-drop dropzone supporting `.docx`, `.pdf`, `.txt`.
  - Displays the local path to `resumes/` with an interactive "Copy Folder Path" button.
  - File picker button (`Browse Files`).
  - Real-time upload progress and instant preview card showing parsed candidate name, role, and detected skills chips upon completion.
  - Dismissable / hidden automatically once an active resume is loaded.

### 3.4 Turnkey Bootstrap Runner (`run.py`, `run.bat`, `run.sh`)
- `run.py`:
  - Cross-platform entry point.
  - Checks Python version (>= 3.11).
  - Initializes database (`jh.db.init_db()`).
  - Ensures `resumes/` directory and instructional guide exist.
  - Scans for resumes and logs status.
  - Auto-configures or outputs Claude Desktop / Cursor MCP JSON snippets if requested via `--register-mcp`.
  - Starts HTTP server on port 8765 and opens browser with extension loaded.
- `run.bat`: Windows double-click shortcut running `python run.py`.
- `run.sh`: Linux/macOS shortcut running `python3 run.py`.

---

## 4. Verification & Testing
- Offline pytest suite `python -m pytest tests -q` must remain 100% passing.
- New unit and integration tests for `ensure_resumes_dir`, `/api/resumes/upload`, `/api/resumes/scan`, and `run.py`.

