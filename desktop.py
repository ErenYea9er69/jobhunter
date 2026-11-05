"""Desktop Runner & Local Service Orchestrator for JobHunter.

Starts the lightweight HTTP daemon, serves the Web Dashboard, and
automatically launches Chromium with the ATS Autofill extension loaded.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

# Configure stderr logging
log = logging.getLogger("jobhunter.desktop")
if not log.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [desktop] %(levelname)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

from jh import extension_installer, httpd


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="desktop.py",
        description="JobHunter Desktop Runner — Launches local dashboard and auto-loads ATS browser extension.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind the local HTTP daemon (default: 8765)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--launch-browser",
        action="store_true",
        default=True,
        help="Automatically launch Chromium browser with ATS extension (default: True)",
    )
    parser.add_argument(
        "--no-browser",
        dest="launch_browser",
        action="store_false",
        help="Do not automatically launch a browser on startup",
    )
    parser.add_argument(
        "--install-extension",
        action="store_true",
        help="Open browser extension management page and reveal folder in Explorer, then exit",
    )
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()

    if args.install_extension:
        sys.stderr.write("Opening extension manager and copying path to clipboard...\n")
        res = extension_installer.open_extension_manager()
        sys.stderr.write(f"Extension directory: {res.get('extension_dir')}\n")
        sys.stderr.write(f"Clipboard copied: {res.get('path_copied_to_clipboard')}\n")
        return

    # Start local HTTP server
    ws_dir = Path.cwd()
    sys.stderr.write(f"\n=========================================================\n")
    sys.stderr.write(f"  ⚡ JobHunter Autonomous Copilot & Web Dashboard v2.3\n")
    sys.stderr.write(f"=========================================================\n")
    sys.stderr.write(f"Serving dashboard at: http://{args.host}:{args.port}\n")
    sys.stderr.write(f"Workspace directory:  {ws_dir}\n")

    server = httpd.start_server(host=args.host, port=args.port, ws_dir=ws_dir)

    # Launch browser if requested
    if args.launch_browser:
        app_url = f"http://{args.host}:{args.port}"
        sys.stderr.write("Detecting installed Chromium browsers and loading extension...\n")
        launch_res = extension_installer.launch_browser_with_extension(url=app_url)
        if launch_res.get("success"):
            sys.stderr.write(f"✓ Launched {launch_res.get('browser')} with ATS extension.\n")
        else:
            sys.stderr.write(f"Notice: {launch_res.get('error', 'Browser not launched automatically.')}\n")
            sys.stderr.write(f"Open {app_url} in your browser manually.\n")

    sys.stderr.write("\nRunning... Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.stderr.write("\nShutting down JobHunter server...\n")
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        sys.stderr.write("Server stopped.\n")


if __name__ == "__main__":
    main()
