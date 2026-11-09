"""MCP Client Auto-Configurator for JobHunter.

Detects installed AI coding agents and desktop clients (Claude Desktop, Cursor, Antigravity)
and automatically registers JobHunter in their configuration files so users do not have
to edit JSON manually.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("jobhunter.mcp_configurator")


def get_default_claude_desktop_path() -> Path:
    """Returns the platform-dependent path to claude_desktop_config.json."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        home = Path.home()
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        # Linux / XDG
        home = Path.home()
        return home / ".config" / "Claude" / "claude_desktop_config.json"


def get_default_antigravity_config_path() -> Path:
    """Returns the path to ~/.gemini/config/mcp_config.json."""
    home = Path.home()
    return home / ".gemini" / "config" / "mcp_config.json"


def get_mcp_config_dict(workspace_dir: str | Path, python_exe: str | None = None) -> dict[str, Any]:
    """Generates the standard MCP server connection dict for this repository."""
    ws = str(Path(workspace_dir).resolve())
    py_bin = python_exe or sys.executable
    server_script = os.path.join(ws, "mcp_server.py")
    return {
        "command": py_bin,
        "args": [server_script],
        "env": {
            "JH_WORKSPACE": ws,
        },
    }


def register_with_claude_desktop(
    workspace_dir: str | Path,
    python_exe: str | None = None,
    target_path: str | Path | None = None,
) -> dict[str, Any]:
    """Registers JobHunter in the Claude Desktop configuration file without overwriting existing servers."""
    config_file = Path(target_path).resolve() if target_path else get_default_claude_desktop_path()
    cfg_dict = get_mcp_config_dict(workspace_dir, python_exe)

    try:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        existing_data: dict[str, Any] = {}
        if config_file.exists():
            try:
                existing_data = json.loads(config_file.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("Could not read existing Claude Desktop config: %s", e)
                existing_data = {}

        if not isinstance(existing_data, dict):
            existing_data = {}

        mcp_servers = existing_data.setdefault("mcpServers", {})
        mcp_servers["jobhunter"] = cfg_dict

        config_file.write_text(json.dumps(existing_data, indent=2), encoding="utf-8")
        return {
            "success": True,
            "path": str(config_file),
            "client": "Claude Desktop",
            "server_name": "jobhunter",
        }
    except Exception as e:
        log.error("Failed to update Claude Desktop configuration: %s", e)
        return {
            "success": False,
            "error": str(e),
            "path": str(config_file),
            "client": "Claude Desktop",
        }


def register_with_cursor(
    workspace_dir: str | Path,
    python_exe: str | None = None,
) -> dict[str, Any]:
    """Registers JobHunter in the workspace .cursor/mcp.json file for Cursor."""
    ws = Path(workspace_dir).resolve()
    cursor_dir = ws / ".cursor"
    config_file = cursor_dir / "mcp.json"
    cfg_dict = get_mcp_config_dict(ws, python_exe)

    try:
        cursor_dir.mkdir(parents=True, exist_ok=True)
        existing_data: dict[str, Any] = {}
        if config_file.exists():
            try:
                existing_data = json.loads(config_file.read_text(encoding="utf-8"))
            except Exception:
                existing_data = {}

        if not isinstance(existing_data, dict):
            existing_data = {}

        mcp_servers = existing_data.setdefault("mcpServers", {})
        mcp_servers["jobhunter"] = cfg_dict

        config_file.write_text(json.dumps(existing_data, indent=2), encoding="utf-8")
        return {
            "success": True,
            "path": str(config_file),
            "client": "Cursor",
            "server_name": "jobhunter",
        }
    except Exception as e:
        log.error("Failed to update Cursor configuration: %s", e)
        return {
            "success": False,
            "error": str(e),
            "path": str(config_file),
            "client": "Cursor",
        }


def register_with_antigravity(
    workspace_dir: str | Path,
    python_exe: str | None = None,
    target_path: str | Path | None = None,
) -> dict[str, Any]:
    """Registers JobHunter in the Antigravity configuration file (~/.gemini/config/mcp_config.json)."""
    config_file = Path(target_path).resolve() if target_path else get_default_antigravity_config_path()
    cfg_dict = get_mcp_config_dict(workspace_dir, python_exe)

    try:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        existing_data: dict[str, Any] = {}
        if config_file.exists():
            try:
                existing_data = json.loads(config_file.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("Could not read existing Antigravity config: %s", e)
                existing_data = {}

        if not isinstance(existing_data, dict):
            existing_data = {}

        mcp_servers = existing_data.setdefault("mcpServers", {})
        mcp_servers["jobhunter"] = cfg_dict

        config_file.write_text(json.dumps(existing_data, indent=2), encoding="utf-8")
        return {
            "success": True,
            "path": str(config_file),
            "client": "Antigravity",
            "server_name": "jobhunter",
        }
    except Exception as e:
        log.error("Failed to update Antigravity configuration: %s", e)
        return {
            "success": False,
            "error": str(e),
            "path": str(config_file),
            "client": "Antigravity",
        }


def auto_register_all(workspace_dir: str | Path) -> list[dict[str, Any]]:
    """Attempts automatic registration for all detected AI clients and returns a report."""
    results = []

    # 1. Cursor workspace config
    res_cursor = register_with_cursor(workspace_dir)
    results.append(res_cursor)

    # 2. Claude Desktop (only if Claude Desktop folder exists or user has Claude installed)
    claude_path = get_default_claude_desktop_path()
    if claude_path.parent.exists():
        res_claude = register_with_claude_desktop(workspace_dir)
        results.append(res_claude)
    else:
        results.append({
            "success": False,
            "client": "Claude Desktop",
            "reason": "Claude Desktop folder not detected",
            "path": str(claude_path),
        })

    # 3. Antigravity config
    ag_path = get_default_antigravity_config_path()
    if ag_path.parent.exists():
        res_ag = register_with_antigravity(workspace_dir)
        results.append(res_ag)
    else:
        results.append({
            "success": False,
            "client": "Antigravity",
            "reason": "Antigravity config directory not detected",
            "path": str(ag_path),
        })

    return results

