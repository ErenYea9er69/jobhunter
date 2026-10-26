#!/usr/bin/env python3
"""JobHunter MCP Server — Model Context Protocol entry point.

Exposes JobHunter search, match scoring, truthful resume tailoring, ATS audits,
and application tracking as MCP tools and resources over stdio transport.

CRITICAL: All logging must be directed to sys.stderr so stdout remains purely
dedicated to JSON-RPC protocol messages.
"""

from __future__ import annotations

import logging
import os
import sys
import warnings

# Filter library warnings before starting
warnings.filterwarnings("ignore")

# Configure stderr logging immediately
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [jobhunter-mcp] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("jobhunter.mcp")

from mcp.server.fastmcp import FastMCP

from jh import config, db, tracker, workspace
from jh.evidence import EvidenceLedger, build_ledger_from_profile
from jh.filestore import FileStore
from jh.mcp_tools import register_tools_and_resources, _slugify
from jh.observability import record_startup, record_recovery, record_parse_event
from jh.source_registry import get_registry


# Module-level evidence ledger — populated during startup, available to tools
_evidence_ledger: EvidenceLedger | None = None


def get_evidence_ledger() -> EvidenceLedger:
    """Return the global evidence ledger built during startup."""
    global _evidence_ledger
    if _evidence_ledger is None:
        _evidence_ledger = EvidenceLedger()
    return _evidence_ledger


def init_workspace_and_engine(ws_path: str = "") -> tuple[FileStore, str]:
    """Execute full startup sequence:

    1. Detect workspace directory
    2. Configure MCP environment in jh.config
    3. Ensure .jobhunter/ directory tree & gitignore
    4. Initialize FileStore and validate source registry
    5. Scan workspace for resume files and parse them
    6. Build evidence ledger from parsed profiles
    7. Initialize ephemeral SQLite database
    8. Populate SQLite with parsed resume profiles
    9. Load cached jobs and applications from JSON into SQLite
    10. Record startup health event
    """
    ws = workspace.detect_workspace() if not ws_path else workspace.Path(ws_path).resolve()
    log.info("Detected workspace: %s", ws)

    # 1. Configure MCP environment
    jh_dir = config.configure_mcp_environment(str(ws))
    workspace.ensure_jobhunter_dir(ws)
    filestore = FileStore(jh_dir)

    # 2. Validate source registry
    registry = get_registry()
    log.info("Source registry: %d sources (%d enabled)",
             len(registry.all()), len(registry.enabled()))

    # 3. Init ephemeral SQLite engine
    log.info("Initializing engine SQLite at %s", config.DB_PATH)
    db.init_db()

    # 4. Incremental Resume Registry scan
    log.info("Scanning workspace for resume files via ResumeRegistry...")
    from jh.resume_registry import ResumeRegistry
    resume_reg = ResumeRegistry(ws)
    sync_res = resume_reg.scan_and_sync()
    log.info("Resume scan sync complete: %s parsed, %s cached",
             sync_res.get("parsed_count", 0), sync_res.get("cached_count", 0))

    global _evidence_ledger
    _evidence_ledger = EvidenceLedger()

    parsed_profiles = []
    for var in resume_reg.list_variants():
        prof = var.get("profile")
        if not prof:
            continue
        p_id = var.get("id") or f"var_{_slugify(var.get('name', ''))}"
        db.save_profile(prof, profile_id=p_id)
        parsed_profiles.append((p_id, var.get("name", ""), prof))

        # Build evidence claims from this profile
        variant_ledger = build_ledger_from_profile(prof, source_file=var.get("path", ""))
        for claim in variant_ledger.claims.values():
            _evidence_ledger.add(claim)

    # 4. Set active resume
    active_name = resume_reg.get_active_variant() or filestore.get_active_resume()
    if active_name:
        profiles = db.list_resume_profiles()
        match = next((p for p in profiles if p["name"].lower() == active_name.lower() or p["id"].lower() == active_name.lower()), None)
        if match:
            db.set_active_resume_profile(match["id"])
            log.info("Active resume restored: '%s'", match["name"])
    elif parsed_profiles:
        # Default to first discovered resume
        first_id, first_name, _ = parsed_profiles[0]
        db.set_active_resume_profile(first_id)
        filestore.set_active_resume(first_name)
        resume_reg.set_active_variant(first_name)
        log.info("Active resume defaulted to: '%s'", first_name)
    else:
        log.info("No resumes found in workspace. Add resumes to root or resumes/ directory.")

    # 5. Populate SQLite from persisted applications.json
    try:
        persisted_apps = filestore.load_applications()
        if persisted_apps:
            log.info("Loading %d persisted application(s) into engine...", len(persisted_apps))
            for app in persisted_apps:
                try:
                    tracker.upsert_application(app)
                except Exception:
                    pass
    except Exception as e:
        log.warning("Could not restore persisted applications: %s", e)

    # 6. Populate SQLite from cached jobs if present
    try:
        latest_cached = filestore.get_latest_cached_jobs()
        if latest_cached:
            log.info("Staging %d cached job(s) into engine...", len(latest_cached))
            db.upsert_search_jobs(latest_cached)
    except Exception as e:
        log.warning("Could not restore cached jobs: %s", e)

    # 10. Record startup health
    record_startup(
        workspace=str(ws),
        resume_count=len(parsed_profiles),
        app_count=len(filestore.load_applications()),
        source_count=len(registry.enabled()),
    )
    log.info("Evidence ledger: %d total claims", len(_evidence_ledger))

    return filestore, str(ws)


def create_server(ws_path: str = "") -> FastMCP:
    """Create and configure the FastMCP JobHunter server instance."""
    filestore, ws = init_workspace_and_engine(ws_path)
    mcp = FastMCP("JobHunter")
    register_tools_and_resources(mcp, filestore, ws)
    log.info("JobHunter MCP Server ready. 27 tools, 7 resources, 8 prompts registered.")
    return mcp


def main():
    """Main CLI entry point for stdio transport."""
    log.info("Starting JobHunter MCP Server...")
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
