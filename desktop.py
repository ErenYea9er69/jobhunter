#!/usr/bin/env python3
"""
JobHunter Desktop Application.
Launches a native desktop window with the embedded local server.
Zero configuration needed — double-click and run.
"""
import os
import sys
import logging

# Ensure base directory is in sys.path
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from jh import config
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
    set_windows_app_id()

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

    # Launch desktop window
    gui_launched = False
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
        webview.start(private_mode=False, icon=icon_path)

    except Exception as err:
        log.warning("Could not launch native webview window (%s). Falling back to browser...", err)
        if not gui_launched:
            import webbrowser
            import time

            print(f"\n==========================================")
            print(f"  JobHunter Desktop Running at:")
            print(f"  {app_url}")
            print(f"==========================================\n")
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
