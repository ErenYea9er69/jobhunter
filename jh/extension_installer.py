"""
Desktop Extension Installer & Auto-Launcher Module for JobHunter.
Manages Chromium browser discovery, --load-extension automation,
and clipboard/developer-mode setup helpers on Windows.
"""
import json
import logging
import os
import shutil
import subprocess
import sys

log = logging.getLogger("jobhunter.desktop.extension")


def find_extension_dir() -> str:
    """
    Locates the extension directory across:
    1. PyInstaller frozen bundle (sys._MEIPASS/extension)
    2. One-dir installed executable directory (sys.executable dir / extension)
    3. Source repository root (BASE_DIR/extension)
    """
    candidates = []

    # PyInstaller _MEIPASS
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "extension"))

    # Executable directory
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates.append(os.path.join(exe_dir, "extension"))

    # Source directory relative to this file
    module_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(os.path.dirname(module_dir), "extension"))

    # Working directory
    candidates.append(os.path.join(os.getcwd(), "extension"))

    for c in candidates:
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "manifest.json")):
            return os.path.abspath(c)

    # Fallback to the source path
    return os.path.abspath(candidates[2])


def find_manifest() -> dict:
    """Reads manifest.json from the resolved extension folder."""
    ext_dir = find_extension_dir()
    manifest_file = os.path.join(ext_dir, "manifest.json")
    if os.path.isfile(manifest_file):
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning("Could not read manifest.json: %s", e)
    return {}


def detect_chromium_browsers() -> list[dict]:
    """
    Detects installed Chromium-based browsers on Windows and returns a prioritized list.
    Prioritizes Google Chrome, Microsoft Edge, Brave, Vivaldi.
    """
    browsers = []
    seen_paths = set()

    def add_browser(name: str, b_type: str, path: str):
        if not path:
            return
        clean_path = os.path.abspath(os.path.expandvars(path))
        if os.path.isfile(clean_path) and clean_path.lower() not in seen_paths:
            seen_paths.add(clean_path.lower())
            browsers.append({
                "name": name,
                "type": b_type,
                "path": clean_path,
            })

    if sys.platform == "win32":
        # Check standard Windows paths
        local_app = os.environ.get("LOCALAPPDATA", "")
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

        # 1. Google Chrome
        chrome_candidates = [
            os.path.join(prog_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(prog_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app, "Google", "Chrome", "Application", "chrome.exe"),
        ]
        for p in chrome_candidates:
            add_browser("Google Chrome", "chrome", p)

        # 2. Microsoft Edge
        edge_candidates = [
            os.path.join(prog_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(local_app, "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
        for p in edge_candidates:
            add_browser("Microsoft Edge", "edge", p)

        # 3. Brave Browser
        brave_candidates = [
            os.path.join(prog_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(prog_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_app, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
        for p in brave_candidates:
            add_browser("Brave", "brave", p)

        # 4. Check Windows Registry App Paths
        try:
            import winreg
            for exe_key, b_name, b_type in [
                ("chrome.exe", "Google Chrome", "chrome"),
                ("msedge.exe", "Microsoft Edge", "edge"),
                ("brave.exe", "Brave", "brave"),
            ]:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_key}",
                    ) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val:
                            add_browser(b_name, b_type, val)
                except OSError:
                    pass
        except Exception:
            pass

    # Generic check via PATH for non-windows or custom setups
    for name, b_type, exe in [
        ("Google Chrome", "chrome", "chrome"),
        ("Google Chrome", "chrome", "google-chrome"),
        ("Microsoft Edge", "edge", "msedge"),
        ("Brave", "brave", "brave-browser"),
    ]:
        which_path = shutil.which(exe)
        if which_path:
            add_browser(name, b_type, which_path)

    return browsers


def copy_extension_path_to_clipboard() -> bool:
    """Copies the absolute path of the extension directory to the Windows clipboard."""
    ext_dir = find_extension_dir()
    if sys.platform == "win32":
        try:
            # Using clip.exe directly via standard subprocess
            p = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE, shell=False)
            p.communicate(ext_dir.encode("utf-16le"))
            return True
        except Exception as e:
            log.warning("Could not copy extension path via clip.exe: %s", e)
    return False


def launch_browser_with_extension(url: str = None, browser_type: str = "auto") -> dict:
    """
    Launches a detected Chromium browser with `--load-extension` pointing to the bundled extension.
    """
    browsers = detect_chromium_browsers()
    if not browsers:
        return {
            "success": False,
            "error": "No Chromium-based browser (Chrome, Edge, Brave) detected on this machine.",
        }

    target = None
    if browser_type and browser_type != "auto":
        target = next((b for b in browsers if b["type"] == browser_type), None)

    if not target:
        target = browsers[0]

    ext_dir = find_extension_dir()
    cmd = [target["path"], f"--load-extension={ext_dir}"]
    if url:
        cmd.append(url)

    try:
        subprocess.Popen(cmd, close_fds=False if sys.platform == "win32" else True)
        return {
            "success": True,
            "browser": target["name"],
            "browser_type": target["type"],
            "path": target["path"],
            "extension_dir": ext_dir,
            "url": url,
        }
    except Exception as e:
        log.error("Failed to launch %s with extension: %s", target["name"], e)
        return {"success": False, "error": str(e), "browser": target["name"]}


def open_extension_manager(browser_type: str = "auto") -> dict:
    """
    Opens the browser extension settings page (chrome://extensions or edge://extensions),
    copies the extension path to the clipboard, and reveals the extension folder in Explorer.
    """
    browsers = detect_chromium_browsers()
    target = None
    if browser_type and browser_type != "auto":
        target = next((b for b in browsers if b["type"] == browser_type), None)
    if not target and browsers:
        target = browsers[0]

    ext_dir = find_extension_dir()
    copied = copy_extension_path_to_clipboard()

    # Open extension manager URL in browser
    ext_url = "edge://extensions" if (target and target["type"] == "edge") else "chrome://extensions"
    if target:
        try:
            subprocess.Popen([target["path"], ext_url])
        except Exception:
            import webbrowser
            webbrowser.open(ext_url)
    else:
        import webbrowser
        webbrowser.open(ext_url)

    # Open folder in Windows Explorer
    if sys.platform == "win32" and os.path.isdir(ext_dir):
        try:
            subprocess.Popen(["explorer.exe", ext_dir])
        except Exception:
            pass

    return {
        "success": True,
        "extension_dir": ext_dir,
        "path_copied_to_clipboard": copied,
        "browser": target["name"] if target else "Default Browser",
        "opened_url": ext_url,
    }


def get_extension_status() -> dict:
    """Returns a status summary of the extension files and browser readiness."""
    ext_dir = find_extension_dir()
    manifest = find_manifest()
    browsers = detect_chromium_browsers()

    return {
        "success": True,
        "extension_dir": ext_dir,
        "extension_dir_valid": os.path.isdir(ext_dir) and bool(manifest),
        "version": manifest.get("version", "2.0.0"),
        "name": manifest.get("name", "JobHunter AI Autofill & Copilot"),
        "browsers": browsers,
        "recommended_browser": browsers[0]["name"] if browsers else None,
    }
