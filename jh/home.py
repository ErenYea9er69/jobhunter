"""Workspace isolation and central storage management for JobHunter.

Ensures that JobHunter never writes files to the user's project or repository.
All data, databases, resumes, outputs, logs, and PID/lock files are isolated
inside a single dedicated directory resolved by get_home().
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("jobhunter.home")

_HOME_CREATED_IN_SESSION: bool = False
_INITIALIZED: bool = False


def get_desktop_dir() -> Path:
    """Resolve the user's Desktop directory, handling Windows OneDrive redirection."""
    if sys.platform == "win32":
        # 1. Check Windows Registry for redirected User Shell Folders (OneDrive / custom desktop)
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "Desktop")
                if val:
                    expanded = os.path.expandvars(val)
                    p = Path(expanded).resolve()
                    if p.is_dir():
                        return p
        except Exception:
            pass

        # 2. Check OneDrive environment variable
        onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or os.environ.get("OneDriveCommercial")
        if onedrive:
            p = Path(onedrive) / "Desktop"
            if p.is_dir():
                return p.resolve()

    # 3. Standard fallback
    try:
        standard = Path.home() / "Desktop"
    except Exception:
        fallback_base = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "."
        standard = Path(fallback_base) / "Desktop"
    return standard.resolve()


def get_home() -> Path:
    """Resolve JobHunter isolated home directory.

    Lookup order:
    1. JOBMCP_HOME environment variable.
    2. ~/.jobmcp/config.json -> "home" or "data_dir" setting.
    3. Desktop/jobmcp (with Windows OneDrive redirection support).
    """
    # 1. Environment variable override
    env_home = os.environ.get("JOBMCP_HOME")
    if env_home and env_home.strip():
        return Path(env_home.strip()).resolve()

    # 2. ~/.jobmcp/config.json
    try:
        home_dir = Path.home()
    except Exception:
        fallback_base = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "."
        home_dir = Path(fallback_base)

    try:
        cfg_file = home_dir / ".jobmcp" / "config.json"
        if cfg_file.is_file():
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            candidate = data.get("home") or data.get("data_dir")
            if candidate and str(candidate).strip():
                return Path(str(candidate).strip()).resolve()
    except Exception:
        pass

    # 3. Desktop/jobmcp
    desktop = get_desktop_dir()
    return (desktop / "jobmcp").resolve()


_FIRST_NOTICE_GIVEN: bool = False


def was_created_now() -> bool:
    """True if the home folder was provisioned during this session's tool calls."""
    global _HOME_CREATED_IN_SESSION
    return _HOME_CREATED_IN_SESSION


def ensure_home_dirs() -> Path:
    """Create the home directory structure on the first tool call.

    Never called at install or import time.
    Directories created:
      data/ (holds engine.db)
      resumes/
      outputs/
      logs/
      run/
      config.json
    """
    global _HOME_CREATED_IN_SESSION, _INITIALIZED
    home = get_home()

    if not home.exists():
        _HOME_CREATED_IN_SESSION = True

    subdirs = [
        home / "data",
        home / "resumes",
        home / "outputs",
        home / "logs",
        home / "run",
    ]
    for d in subdirs:
        d.mkdir(parents=True, exist_ok=True)

    config_path = home / "config.json"
    if not config_path.exists():
        initial_cfg = {
            "cleanup_grace_hours": 24,
            "max_scored_jobs": 2500,
            "max_results": 1000,
            "created_at": None,
        }
        try:
            config_path.write_text(json.dumps(initial_cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    _INITIALIZED = True
    return home


def get_first_reply_notice() -> Optional[str]:
    """Return notice message for the user if home was created during this session."""
    global _FIRST_NOTICE_GIVEN
    if was_created_now() and not _FIRST_NOTICE_GIVEN:
        _FIRST_NOTICE_GIVEN = True
        return f"I created Desktop/jobmcp. Everything I store goes there. I will not write to your project. Full path: {get_home()}"
    return None


def check_legacy_local_data(repo_path: Path | None = None) -> list[str]:
    """Check if an old repo-local data folder exists in the project."""
    repo = (repo_path or Path.cwd()).resolve()
    found: list[str] = []
    for candidate in [repo / "data" / "engine.db", repo / ".jobhunter" / "engine.db"]:
        if candidate.is_file():
            found.append(str(candidate))
    return found
