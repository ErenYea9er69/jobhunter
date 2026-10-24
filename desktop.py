#!/usr/bin/env python3
"""
JobHunter Desktop Application.
Launches a native desktop window with the embedded local server
or launches Chromium with the JobHunter AI Copilot Extension pre-loaded.
Zero configuration needed — double-click and run.
"""
import argparse
import logging
import os
import sys
import time

# Ensure base directory is in sys.path
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from jh import config
from jh import extension_installer
from jh.httpd import start_background_server

log = logging.getLogger("jobhunter.desktop")


def set_windows_app_id():
    """Set Windows taskbar grouping and icon ID."""
    if sys.platform == "win32":
        try:
            import ctypes
            app_id = "jobhunter.desktop.app.v2"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="JobHunter Desktop Application & AI Copilot Launcher")
    parser.add_argument(
        "--launch-browser",
        action="store_true",
        help="Launch default Chromium browser with the JobHunter extension pre-loaded",
    )
    parser.add_argument(
        "--install-extension",
        action="store_true",
        help="Open browser extension manager, copy extension folder to clipboard, and reveal directory",
    )
    parser.add_argument(
        "--browser",
        default="auto",
        choices=["auto", "chrome", "edge", "brave"],
        help="Specific Chromium browser to launch with extension (default: auto)",
    )
    args, _ = parser.parse_known_args()

    set_windows_app_id()

    # Handle standalone 1-click extension manager / folder opening
    if args.install_extension:
        res = extension_installer.open_extension_manager(browser_type=args.browser)
        print("=" * 60)
        print("  JobHunter AI Copilot Extension Setup")
        print("=" * 60)
        print(f"  Extension Folder: {res.get('extension_dir')}")
        print(f"  Path Copied to Clipboard: {res.get('path_copied_to_clipboard')}")
        print(f"  Browser Settings Opened:  {res.get('opened_url')}")
        print("=" * 60)
        return

    # Start the local server on an available port
    srv, port = start_background_server(host="127.0.0.1", port=config.PORT)
    app_url = f"http://127.0.0.1:{port}"

    # Determine icon file
    icon_candidates = [
        os.path.join(config.BASE_DIR, "app_icon.ico"),
        os.path.join(os.path.dirname(sys.executable), "app_icon.ico"),
        os.path.join(config.STATIC_DIR, "favicon.ico"),
    ]
    icon_path = next((p for p in icon_candidates if os.path.isfile(p)), None)

    # Check launch mode (from argument or saved setting in db)
    try:
        from jh import db
        db_launch_mode = db.get_setting("desktop_launch_mode", "desktop")
    except Exception:
        db_launch_mode = "desktop"
    should_launch_browser = args.launch_browser or (db_launch_mode == "browser")

    # If browser mode is active, launch Chromium with extension pre-loaded
    if should_launch_browser:
        launch_res = extension_installer.launch_browser_with_extension(url=app_url, browser_type=args.browser)
        print("=" * 60)
        print("  JobHunter Running in Browser Mode with AI Extension")
        print(f"  URL:     {app_url}")
        print(f"  Browser: {launch_res.get('browser', 'Default')} ({launch_res.get('path', '')})")
        print("=" * 60)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass
            sys.exit(0)

    # Ensure local server is responsive before opening desktop window
    import urllib.request
    for _ in range(30):
        try:
            with urllib.request.urlopen(app_url, timeout=0.3):
                break
        except Exception:
            time.sleep(0.08)

    # Launch native desktop window
    gui_launched = False
    storage_path = os.path.join(config.DATA_DIR, "webview")
    try:
        os.makedirs(storage_path, exist_ok=True)
    except Exception:
        storage_path = None

    try:
        import webview

        window = webview.create_window(
            title="JobHunter",
            url=app_url,
            width=1280,
            height=850,
            min_size=(980, 640),
            text_select=True,
            zoomable=True,
            confirm_close=False,
            background_color="#0f172a",
        )
        gui_launched = True
        webview.start(private_mode=False, icon=icon_path, storage_path=storage_path)

    except Exception as err:
        log.warning("Could not launch native webview window (%s). Falling back to browser...", err)
        if not gui_launched:
            import webbrowser

            print(f"\n==========================================")
            print(f"  JobHunter Desktop Running at:")
            print(f"  {app_url}")
            print(f"==========================================\n")
            # Try launching with extension preloaded in browser fallback
            ext_res = extension_installer.launch_browser_with_extension(url=app_url, browser_type=args.browser)
            if not ext_res.get("success"):
                webbrowser.open(app_url)

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    finally:
        try:
            srv.shutdown()
            srv.server_close()
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
