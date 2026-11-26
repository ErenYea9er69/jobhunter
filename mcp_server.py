#!/usr/bin/env python3
"""JobHunter MCP server: stdio entry point.

Exposes job search across many sources, resume-grounded scoring, truthful tailoring, ATS audits and
application tracking as MCP tools (and a few read-only resources). There are no MCP prompts.

All logging goes to stderr. Standard output carries only JSON-RPC messages.

Usage:
    python mcp_server.py                       run the server over stdio
    python mcp_server.py --workspace DIR       use DIR as the workspace
    python mcp_server.py --surface full        show every tool, not only the CEO tools
    python mcp_server.py --check               start up, list the tools, and exit
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] [jobhunter] %(message)s",
                    datefmt="%H:%M:%S", stream=sys.stderr)
log = logging.getLogger("jobhunter.mcp")

from mcp.server.fastmcp import FastMCP  # noqa: E402

from jh import config, db, workspace  # noqa: E402
from jh.filestore import OutputStore  # noqa: E402
from jh.mcp_tools import register_tools_and_resources  # noqa: E402
from jh.observability import record_startup  # noqa: E402
from jh.resume_registry import ResumeRegistry  # noqa: E402
from jh.team.surface import TeamMCP, resolve as resolve_surface  # noqa: E402

__version__ = "2.0.0"

INSTRUCTIONS = """JobHunter is a Hybrid job search copilot for Claude Desktop combining multi-board discovery, fresh hiring signals, tailored application materials, and decision-maker outreach.

Workflow:
1. Start with jh_begin (or ceo_run setup) to load the candidate resume without guessing location or unconfirmed facts.
2. Confirm target place, target role, and key filters with the user via jh_confirm, jh_set_filters, or jh_answer.
3. Run Hybrid discovery (jh_launch, jh_search, search_jobs, or ceo_run hunt) to combine job boards and fresh hiring signals, then rank and present verified matches sorted by fit and recency in chat.
4. Ask which jobs the user wants to pursue, then run tailor_resume, cover_letter, prepare_application, jh_build_resume, jh_find_contacts, or jh_draft_email on selected matches.
5. Keep the user in control: never submit applications or send outreach automatically, and surface only verified, resume-grounded claims and files.
6. Coaching: default to zero unsolicited advice unless triggers apply (get_coaching_context, get_coaching_content)."""


def init_workspace_and_engine(ws_path: str = "") -> tuple[OutputStore, str]:
    """Start-up: configure paths, open the database, parse resumes, restore the active resume."""
    from jh import home
    ws = Path(ws_path).resolve() if ws_path else workspace.detect_workspace()
    log.info("Workspace: %s", ws)

    if os.environ.get("JH_DATA_DIR"):
        jh_dir = config.configure_mcp_environment(str(ws))
        workspace.ensure_jobhunter_dir(ws)
        store = OutputStore(jh_dir)
        db.init_db()

        registry = ResumeRegistry(ws)
        sync = registry.scan_and_sync()
        log.info("Resumes: %s parsed, %s cached", sync.get("parsed_count", 0), sync.get("cached_count", 0))
        variants = registry.list_variants()
        for var in variants:
            prof = var.get("profile")
            if prof:
                db.save_profile(prof, profile_id=var.get("id") or f"var_{var.get('name', '').lower().replace(' ', '-')}")

        profiles = db.list_resume_profiles()
        wanted = registry.get_active_variant()
        match = next((p for p in profiles if wanted and wanted.lower() in (p["name"].lower(), p["id"].lower())), None) or (profiles[0] if profiles else None)
        if match:
            db.set_active_resume_profile(match["id"])
            registry.set_active_variant(match["name"])
            log.info("Active resume: %s", match["name"])
        else:
            log.info("No resumes found. Add a PDF, DOCX or TXT resume to the workspace.")

        imported = store.import_legacy_applications()
        if imported:
            log.info("Imported %d application(s) from the old applications.json", imported)

        from jh import tracker, source_registry
        record_startup(workspace=str(ws), resume_count=len(profiles), app_count=len(tracker.list_applications()),
                       source_count=len(source_registry.catalog()))
        return store, str(ws)

    # Isolated production mode: keep any explicit test DB_PATH override intact
    home_dir = home.get_home()
    expected_data = (home_dir / "data").resolve()
    config.WORKSPACE_DIR = str(ws)
    cur_db = Path(config.DB_PATH).resolve() if config.DB_PATH else None
    default_initial_dbs = {
        (Path(config.DEFAULT_DATA_DIR) / "engine.db").resolve(),
        (Path(config.DEFAULT_DATA_DIR) / "state").resolve(),
    }
    if cur_db is None or (cur_db in default_initial_dbs and expected_data != Path(config.DEFAULT_DATA_DIR).resolve()):
        config.DATA_DIR = str(expected_data)
        config.DB_PATH = str(expected_data / "state")
    elif cur_db not in default_initial_dbs:
        config.DATA_DIR = str(cur_db.parent)
    else:
        config.DATA_DIR = str(expected_data)

    store_root = (home_dir / "outputs") if (Path(config.DB_PATH).parent.resolve() == expected_data) else (Path(config.DB_PATH).parent / "outputs")
    store = OutputStore(store_root)

    db.init_db()
    if (ws / "resumes").is_dir():
        try:
            registry = ResumeRegistry(ws)
            registry.scan_and_sync()
            for var in registry.list_variants():
                prof = var.get("profile")
                if prof:
                    db.save_profile(prof, profile_id=var.get("id") or f"var_{var.get('name', '').lower().replace(' ', '-')}")
            profiles = db.list_resume_profiles()
            wanted = registry.get_active_variant()
            match = next((p for p in profiles if wanted and wanted.lower() in (p["name"].lower(), p["id"].lower())), None) or (profiles[0] if profiles else None)
            if match:
                db.set_active_resume_profile(match["id"])
                registry.set_active_variant(match["name"])
        except Exception as exc:
            log.debug("Resume scan in %s skipped: %s", ws, exc)
    return store, str(ws)


def create_server(ws_path: str = "", surface: str = "full") -> TeamMCP:
    """Build the server. ``surface="team"`` shows the client only the CEO tools; ``"full"`` shows every tool."""
    store, ws = init_workspace_and_engine(ws_path)
    mcp = TeamMCP("JobHunter", instructions=INSTRUCTIONS)
    mcp.surface = resolve_surface(surface)
    register_tools_and_resources(mcp, store, ws)
    return mcp


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="JobHunter MCP server")
    ap.add_argument("--workspace", default="", help="workspace folder (default: JH_WORKSPACE or the current folder)")
    ap.add_argument("--surface", default="", choices=["", "team", "full"],
                    help="team (default): the client sees only the CEO tools. full: every tool. Also JH_SURFACE.")
    ap.add_argument("--check", action="store_true", help="start up, list tools, and exit")
    ap.add_argument("--install-claude", action="store_true", help="register JobHunter in Claude Desktop config")
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args(argv)
    if args.version:
        print(__version__)
        return
    if args.install_claude:
        from jh import mcp_configurator
        ws = str(Path(args.workspace).resolve()) if args.workspace else str(workspace.detect_workspace())
        res = mcp_configurator.register_with_claude_desktop(ws)
        print(res.get("path") or res, file=sys.stderr)
        return
    server = create_server(args.workspace, surface=resolve_surface(args.surface))
    if args.check:
        import asyncio
        tools = asyncio.run(server.list_tools())
        print(f"JobHunter {__version__}: {len(tools)} tools OK", file=sys.stderr)
        for t in sorted(tools, key=lambda x: x.name):
            print(f"  {t.name}", file=sys.stderr)
        return
    log.info("JobHunter %s ready. Serving over stdio.", __version__)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
