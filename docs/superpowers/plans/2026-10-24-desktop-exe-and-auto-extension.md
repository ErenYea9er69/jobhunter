# Desktop Exe Rebuild & Automated Extension Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the JobHunter Windows desktop application executable (`JobHunter.exe`) and installer (`JobHunter-Setup.exe`) with the new ATS Autofill & Copilot extension bundled, complete with automated browser extension launching and 1-click installation tooling.

**Architecture:** Create a dedicated `jh/extension_installer.py` module to detect installed Chromium browsers (Chrome, Edge, Brave) on Windows, resolve the bundled extension path across frozen PyInstaller and source environments, and launch browsers with `--load-extension`. Expose management endpoints in `jh/httpd.py`, integrate 1-click extension launching into `desktop.py` and the UI in `public/app.js`, bundle `extension/` via `build_desktop.py` and `installer.iss`, and compile a fresh standalone executable and Inno Setup installer.

**Tech Stack:** Python 3.10+, PyInstaller 6.22+, Inno Setup 7, Windows Shell API (`ctypes.windll`, `subprocess`), Chromium CLI flags (`--load-extension`), HTML5/JavaScript.

**Spec:** User request to re-analyze recent changes (autofill companion extension, ATS autofill engine, security updates) and redo the startup executable with automated extension installation.

---

## Global Constraints

- Must work in both packaged PyInstaller mode (`sys._MEIPASS` / frozen exe) and standard development mode (`python desktop.py`).
- No external Python dependencies beyond standard library for the extension installer module (`subprocess`, `ctypes`, `winreg`, `os`, `sys`, `shutil`).
- Chromium security restrictions must be respected: use standard `--load-extension` flag for automated launching, paired with clipboard + file explorer opening for persistent developer-mode install.
- Build artifacts must output to `dist/JobHunter/JobHunter.exe`, `dist/JobHunter-Windows-x64.zip`, and `dist/JobHunter-Setup.exe`.
- Existing JobHunter server routes, security token requirements, and webview desktop fallback must remain fully intact.

---

## Review Focus

1. **Path Resolution in PyInstaller Frozen Mode:** Extension directory must be correctly resolved whether running from source (`BASE_DIR/extension`), extracted one-file temp dir (`sys._MEIPASS/extension`), or one-dir executable folder (`os.path.dirname(sys.executable)/extension`).
2. **Missing Chromium Browsers on User System:** Graceful handling when Chrome is not installed, falling back to Microsoft Edge or default browser with informative user feedback.
3. **Spaces and Quotes in File Paths:** Windows paths containing spaces (e.g. `C:\Program Files\...` or `C:\Users\User Name\...`) passed to `--load-extension` and subprocess commands must be safely quoted without command injection or syntax breakage.
4. **CORS / Session Token for Extension API:** The new `/api/desktop/*` endpoints must support the extension and desktop UI without tripping session token validation or CORS barriers.
5. **Inno Setup & PyInstaller Build Verification:** Build script must exit cleanly, ensure the extension folder exists in `dist/JobHunter/extension`, and compile `JobHunter-Setup.exe` with Inno Setup 7.

---

## Tasks

### Task 1: Chromium Detection and Extension Auto-Launcher Module

**Files:**
- Create: `jh/extension_installer.py`
- Test: `tests/test_extension_installer.py`

**Interfaces:**
- Consumes: `os`, `sys`, `winreg`, `subprocess`, `ctypes`, `shutil`
- Produces:
  - `find_extension_dir() -> str`
  - `detect_chromium_browsers() -> list[dict]`
  - `launch_browser_with_extension(url: str, browser_name: str) -> dict`
  - `copy_extension_path_to_clipboard() -> bool`
  - `open_extension_manager(browser_name: str) -> dict`

- [ ] **Step 1: Write the failing test for extension directory resolution and browser detection**

```python
import os
from jh.extension_installer import find_extension_dir, detect_chromium_browsers, find_manifest

def test_find_extension_dir():
    ext_dir = find_extension_dir()
    assert os.path.isdir(ext_dir)
    assert os.path.isfile(os.path.join(ext_dir, "manifest.json"))

def test_detect_chromium_browsers():
    browsers = detect_chromium_browsers()
    assert isinstance(browsers, list)
    # On Windows, at least Edge or Chrome should be detected
    if os.name == "nt":
        assert len(browsers) >= 1
        assert any(b["type"] in ("chrome", "edge", "brave") for b in browsers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_extension_installer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jh.extension_installer'`

- [ ] **Step 3: Implement `jh/extension_installer.py`**

Implement robust browser detection scanning standard Windows Program Files directories and registry (`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe` & `msedge.exe`), extension path resolution supporting frozen and unfrozen environments, subprocess launching with `--load-extension`, and clipboard copying via `ctypes` or `powershell`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_extension_installer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jh/extension_installer.py tests/test_extension_installer.py
git commit -m "feat(desktop): add extension detection and auto-launch helper"
```

---

### Task 2: Backend API Endpoints for Desktop Extension Management

**Files:**
- Modify: `jh/httpd.py:580-620` (add desktop extension routes)
- Test: `tests/test_desktop_extension_api.py`

**Interfaces:**
- Consumes: `jh.extension_installer`
- Produces:
  - `GET /api/desktop/extension-status` -> returns `{success: bool, extension_dir: str, browsers: list, is_installed: bool}`
  - `POST /api/desktop/launch-browser-extension` -> launches Chrome/Edge with `--load-extension`
  - `POST /api/desktop/open-extension-folder` -> reveals folder in Explorer & copies path to clipboard

- [ ] **Step 1: Write the failing test for desktop extension routes**

```python
import unittest
from jh import httpd, config

class TestDesktopExtensionApi(unittest.TestCase):
    def test_extension_status_route(self):
        handler = httpd.ROUTES.get(("GET", "/api/desktop/extension-status"))
        self.assertIsNotNone(handler)
        res = handler({}, {})
        self.assertTrue(res.get("success"))
        self.assertIn("browsers", res)
        self.assertIn("extension_dir", res)

    def test_launch_browser_route_exists(self):
        handler = httpd.ROUTES.get(("POST", "/api/desktop/launch-browser-extension"))
        self.assertIsNotNone(handler)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_desktop_extension_api.py -v`
Expected: FAIL with `AssertionError: None is not None`

- [ ] **Step 3: Implement routes in `jh/httpd.py`**

Register `@route("GET", "/api/desktop/extension-status")`, `@route("POST", "/api/desktop/launch-browser-extension")`, and `@route("POST", "/api/desktop/open-extension-folder")`. Add `/api/desktop/` to the token-exempt list alongside `/api/extension/` so desktop UI helpers can query it smoothly.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_desktop_extension_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jh/httpd.py tests/test_desktop_extension_api.py
git commit -m "feat(api): expose desktop extension control endpoints"
```

---

### Task 3: Desktop App Integration & CLI Startup Arguments

**Files:**
- Modify: `desktop.py`
- Modify: `JobHunter.bat`
- Test: `tests/test_desktop_cli.py`

**Interfaces:**
- Consumes: `jh.extension_installer`, `jh.httpd`
- Produces:
  - CLI flags in `desktop.py`:
    - `--launch-browser`: Launches Chrome/Edge with extension loaded instead of pywebview
    - `--install-extension`: Opens extension manager with folder revealed
    - `--help`: Displays launcher options

- [ ] **Step 1: Write the test verifying desktop CLI parsing**

```python
import subprocess
import sys
import unittest

class TestDesktopCli(unittest.TestCase):
    def test_help_flag(self):
        res = subprocess.run([sys.executable, "desktop.py", "--help"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("--launch-browser", res.stdout)
        self.assertIn("--install-extension", res.stdout)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_desktop_cli.py -v`
Expected: FAIL (desktop.py doesn't currently handle `--help` or exits unexpectedly)

- [ ] **Step 3: Update `desktop.py` with argument handling and auto-extension launching**

Add `argparse` to `desktop.py`:
- If `--launch-browser`: Start background server, call `launch_browser_with_extension(app_url)`, and keep server alive until interrupted.
- If `--install-extension`: Call `open_extension_manager()` and exit.
- In normal GUI mode: Still launch webview, but pass a startup option to optionally launch browser with extension if webview fails or user requests it.
- Update `JobHunter.bat` to support passing arguments (`%*`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_desktop_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add desktop.py JobHunter.bat tests/test_desktop_cli.py
git commit -m "feat(desktop): add CLI flags for automated browser extension launch"
```

---

### Task 4: UI 1-Click Extension Status and Launcher in Web Dashboard

**Files:**
- Modify: `public/index.html` (header extension indicator / button)
- Modify: `public/app.js` (extension status polling and 1-click launcher trigger)
- Modify: `public/styles.css` (modern badge styling)

**Interfaces:**
- Consumes: `/api/desktop/extension-status`, `/api/desktop/launch-browser-extension`, `/api/desktop/open-extension-folder`
- Produces:
  - "⚡ Copilot Extension: Active / Launch" header button and interactive modal with 1-click automated browser launch and 1-click folder copy.

- [ ] **Step 1: Verify frontend element hook definitions**

Check `public/index.html` for desktop header action bar and add `#btnExtensionLauncher` modal hook.

- [ ] **Step 2: Implement UI integration in `public/app.js` and `public/styles.css`**

Add `initDesktopExtensionBanner()` in `public/app.js` to poll `/api/desktop/extension-status`. When clicked, offer a modal:
- "🚀 Launch Browser with Extension" (calls `/api/desktop/launch-browser-extension`)
- "📂 1-Click Developer Setup" (calls `/api/desktop/open-extension-folder`, automatically copies path, opens `chrome://extensions` or `edge://extensions`)
Add styling in `public/styles.css` with clean, responsive dark-mode styling conforming to AGENTS.md.

- [ ] **Step 3: Verify frontend script syntax and asset integrity**

Run: `node -c public/app.js` or browser headless check.
Expected: Syntax valid.

- [ ] **Step 4: Commit**

```bash
git add public/index.html public/app.js public/styles.css
git commit -m "feat(ui): add 1-click browser extension launcher to dashboard"
```

---

### Task 5: Packaging & Recompiling JobHunter.exe and Inno Setup Installer

**Files:**
- Modify: `build_desktop.py`
- Modify: `installer.iss`
- Test: Verification of generated `dist/JobHunter/JobHunter.exe` and `dist/JobHunter-Setup.exe`

**Interfaces:**
- Consumes: PyInstaller 6.22, Inno Setup 7 (`ISCC.exe`), `extension/` directory
- Produces:
  - `dist/JobHunter/JobHunter.exe`
  - `dist/JobHunter/extension/*` (bundled)
  - `dist/JobHunter-Windows-x64.zip`
  - `dist/JobHunter-Setup.exe`

- [ ] **Step 1: Update `build_desktop.py` to package `extension/` directory**

Add:
```python
extension_path = os.path.join(BASE_DIR, "extension")
# add to PyInstaller command:
f"--add-data={extension_path}{sep}extension"
```
Ensure `jh.extension_installer` is imported or included.

- [ ] **Step 2: Update `installer.iss`**

Ensure `dist\JobHunter\extension\*` is copied to `{app}\extension`.
Add an installer option or post-install launch task:
`Filename: "{app}\{#MyAppExeName}"; Parameters: "--launch-browser"; Description: "Launch JobHunter and open Chrome/Edge with Autofill Extension"; Flags: nowait postinstall unchecked`

- [ ] **Step 3: Run `build_desktop.py` to compile executable, ZIP, and installer**

Run: `python build_desktop.py`
Expected: Return code 0.
Verify that:
- `dist/JobHunter/JobHunter.exe` exists
- `dist/JobHunter/extension/manifest.json` exists
- `dist/JobHunter-Setup.exe` exists and has size > 30MB
- `dist/JobHunter-Windows-x64.zip` exists

- [ ] **Step 4: Run automated test suite on built distribution**

Run test verifying that the bundled directory structure matches expected files.

- [ ] **Step 5: Commit**

```bash
git add build_desktop.py installer.iss
git commit -m "chore(build): bundle extension and recompile JobHunter desktop exe and installer"
```
