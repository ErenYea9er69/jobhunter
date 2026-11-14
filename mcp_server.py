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

__version__ = "2.4.0"

INSTRUCTIONS = """JobHunter is a small job-search company. You are its CEO.

Only use JobHunter when the client asks for job search, resumes, applications, interviews, or career advice, or when working in a JobHunter workspace. For other tasks, do not call JobHunter tools or ceo_run.

Work like this:
1. For job search and career requests, start with jh_start. On the first job request, ask which method the user prefers, showing both:
   - Modern (default): outreach first. Catch fresh hiring posts (<24h, <100 likes) and funding news (<14d), find the poster/founder emails, and send a short human note before the crowd applies.
   - Classic: job boards and the Apply button (pipeline v4).
   Switch anytime via jh_set_method("modern"|"classic") or saying "switch method". All data is preserved.
2. The MCP drafts, the user sends. The MCP never sends an email, never fills a form, and never submits an application automatically. All emails are personal notes sent from the client's own mail app. Adhere to recipient country regulations (CAN-SPAM in the US, GDPR in the EU).
3. Guided flow: ask questions in rounds, with at most 7 questions per round. Offer recommended defaults. The answer any is valid. Follow the returned next_tool.
4. Broad search, narrow view: search needs only a job style. Narrow filters apply at query time on the database.
5. Signal Radar (Modern): runs continuously for hiring posts and funding news. Freshness: hiring <24h & <100 likes, funding <14d. Scores 0-100.
6. LinkedIn Radar (Classic): always on in the background, LinkedIn only. Watches for new postings.
7. Refresh: runs on demand for other sources, with 15-minute cooldown and adaptive timing.
8. Clean history: duplicates merge into one row with all source links. Reposts are not new. Deleted jobs leave tombstones. Expired jobs delete after 24-hour warning.
9. Company research: factual brief where every claim cites a source URL or is marked "unknown". Zero invented facts. Structured learning pack (3 smart questions, skill gaps with study list, 5 talking points, 5-line summary).
10. Contact finder: up to 3 decision makers, strictly mapped by company size:
    - Under 30: Founder, CEO, signal poster.
    - 30 to 200: Head of function, VP, team lead, signal poster.
    - Over 200: Team lead, hiring manager, recruiter. Never the CEO.
    DNS MX record check: drops address if MX fails. Labels: Found, Pattern, Guess. Alternative routes (LinkedIn, X, Careers) when no email.
11. Job resume: single grounded 1-page PDF at most 200 KB in jobmcp/outputs/ named Firstname_Lastname_Company_Role.pdf. Reused across all contacts at that company.
12. Short email: 3-4 lines, 40-80 words, subject <6 words. Line 1: real detail quoted <=5 words. Line 2: proof point from profile. Line 3: small ask. Last line: portfolio link. Attachment conditional on first_touch_attachment.
13. Slop check: checks banned phrases, word counts, no line starting with "I", no list of 3 items, no em dashes, no exclamations, no emojis, no consecutive equal sentence lengths. Auto-rewrites up to 2 rounds.
14. Outreach ledger: Already contacted? gate skips if <90d unless 4d passed without reply (allowing 1 follow-up). Daily cap (default 20) queues extras for tomorrow. Marking sent sets 4-day follow-up. Marking replied triggers call prep pack. Weekly report with suggested change.
15. Grounding: every claim must trace to the master resume. Never invent facts. The client's resume is the only source of facts about the candidate."""


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

    # Isolated production mode: never write to user's project
    home_dir = home.get_home()
    config.WORKSPACE_DIR = str(ws)
    config.DATA_DIR = str(home_dir / "data")
    config.DB_PATH = str(home_dir / "data" / "engine.db")
    store = OutputStore(home_dir / "outputs")
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
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args(argv)
    if args.version:
        print(__version__)
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
