#!/usr/bin/env python3
"""JobHunter Turnkey Runner & Local Copilot Orchestrator.

One command to run everything after cloning:
    python run.py

Automatically:
1. Verifies Python runtime (>= 3.11).
2. Provisions the SQLite database (`engine.db`) and workspace structure.
3. Creates the `resumes/` folder with `PUT_YOUR_RESUME_HERE.txt` guidance.
4. Auto-registers the MCP server in Cursor and Claude Desktop configs.
5. Starts the local Web Dashboard and REST API daemon.
6. Launches your browser with the ATS Autofill extension loaded.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Enforce Python >= 3.11
if sys.version_info < (3, 11):
    sys.stderr.write(
        f"ERROR: JobHunter requires Python 3.11 or newer (detected: {sys.version.split()[0]}).\n"
        "Please upgrade your Python installation: https://www.python.org/downloads/\n"
    )
    sys.exit(1)

from jh import config, db, extension_installer, httpd, mcp_configurator, resume_registry, workspace


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="JobHunter Turnkey Runner — Starts the copilot engine, dashboard, extension, and MCP bridge.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for the local web dashboard and HTTP daemon (default: 8765)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind local HTTP server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-browser",
        dest="launch_browser",
        action="store_false",
        default=True,
        help="Do not automatically launch Chromium with the ATS extension",
    )
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Initialize SQLite database, folders, and MCP configs, then exit without running server",
    )
    return parser.parse_args(args)


def bootstrap_workspace(ws: Path) -> dict:
    """Provisions directories, guides, database, and registers MCP configs."""
    # 1. Workspace directories
    jh_dir = workspace.ensure_jobhunter_dir(ws)
    config.configure_mcp_environment(str(ws))

    # 2. Resumes drop folder & instructional guide
    resumes_dir, guide_path = workspace.ensure_resumes_dir(ws)

    # 3. SQLite Database initialization
    db.init_db()

    # 4. Resume discovery & sync
    registry = resume_registry.ResumeRegistry(ws)
    sync_res = registry.scan_and_sync()
    variants = registry.list_variants()
    for var in variants:
        prof = var.get("profile")
        if prof:
            db.save_profile(prof, profile_id=var.get("id") or f"var_{var.get('name', '').lower().replace(' ', '-')}")

    active_var = registry.get_active_variant()

    # 5. Auto-register MCP configs for AI coding agents
    mcp_results = mcp_configurator.auto_register_all(ws)

    return {
        "workspace": ws,
        "jh_dir": jh_dir,
        "resumes_dir": resumes_dir,
        "guide_path": guide_path,
        "variants": variants,
        "active_variant": active_var,
        "mcp_results": mcp_results,
    }


def main() -> None:
    args = parse_args()
    ws = Path.cwd().resolve()

    sys.stderr.write("\n" + "=" * 64 + "\n")
    sys.stderr.write("  ⚡ JobHunter Autonomous Copilot & Web Dashboard v2.4\n")
    sys.stderr.write("=" * 64 + "\n")

    sys.stderr.write("Initializing workspace, SQLite engine, and directories...\n")
    info = bootstrap_workspace(ws)

    resumes_dir = info["resumes_dir"]
    variants = info["variants"]
    active = info["active_variant"]

    sys.stderr.write(f"✓ SQLite database initialized: {config.DB_PATH}\n")
    sys.stderr.write(f"✓ Candidate drop folder ready:  {resumes_dir}\n")

    if variants:
        sys.stderr.write(f"✓ Resumes discovered ({len(variants)}): active -> '{active or variants[0].get('name')}'\n")
    else:
        sys.stderr.write(f"! No resumes found yet. Drop your Word (.docx), PDF (.pdf), or Text (.txt) file into:\n")
        sys.stderr.write(f"  {resumes_dir}\n")

    for m in info["mcp_results"]:
        if m.get("success"):
            sys.stderr.write(f"✓ Connected MCP for {m.get('client')}: {m.get('path')}\n")

    if args.setup_only:
        sys.stderr.write("\nSetup complete. Exiting (--setup-only).\n")
        return

    # Start HTTP server
    dashboard_url = f"http://{args.host}:{args.port}"
    sys.stderr.write(f"\nServing Web Dashboard at: {dashboard_url}\n")
    server = httpd.start_server(host=args.host, port=args.port, ws_dir=ws)

    # Launch browser with extension
    if args.launch_browser:
        sys.stderr.write("Detecting installed Chromium browsers and loading ATS extension...\n")
        launch_res = extension_installer.launch_browser_with_extension(url=dashboard_url)
        if launch_res.get("success"):
            sys.stderr.write(f"✓ Launched {launch_res.get('browser')} with ATS Autofill extension.\n")
        else:
            sys.stderr.write(f"Notice: {launch_res.get('error', 'Browser not launched automatically.')}\n")
            sys.stderr.write(f"Open {dashboard_url} in your browser manually.\n")

    sys.stderr.write("\nJobHunter is running! Press Ctrl+C to stop.\n")
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

