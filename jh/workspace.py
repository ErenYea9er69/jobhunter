"""Workspace scanner and resume discovery for JobHunter MCP server.

Scans the user's repository/workspace for resume documents (PDF, DOCX, TXT),
manages the .jobhunter/ metadata and output directories, and parses found
resumes into structured profile variants.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import resume_parser
from .util import now_iso

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".jobhunter",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".continue",
    ".superpowers",
}

NON_RESUME_FILENAMES = {
    "readme",
    "license",
    "licence",
    "requirements",
    "setup",
    "changelog",
    "contributing",
    "agents",
    "dockerfile",
    "makefile",
    "todo",
    "package",
    "package-lock",
    "tsconfig",
}

RESUME_HEURISTIC_WORDS = {
    "experience",
    "education",
    "skills",
    "summary",
    "employment",
    "projects",
    "curriculum",
    "vitae",
    "certifications",
    "work history",
}


def detect_workspace() -> Path:
    """Determine workspace root from JH_WORKSPACE environment variable or current directory."""
    env_ws = os.environ.get("JH_WORKSPACE")
    if env_ws and os.path.isdir(env_ws):
        return Path(env_ws).resolve()
    return Path(os.getcwd()).resolve()


def ensure_jobhunter_dir(workspace_path: str | Path) -> Path:
    """Create .jobhunter directory tree with cache and output folders, plus .gitignore."""
    ws = Path(workspace_path).resolve()
    jh_dir = ws / ".jobhunter"

    subdirs = [
        jh_dir / "cache",
        jh_dir / "output" / "tailored",
        jh_dir / "output" / "cover-letters",
        jh_dir / "output" / "reports",
    ]
    for d in subdirs:
        d.mkdir(parents=True, exist_ok=True)

    # Write .gitignore inside .jobhunter if not already present
    gitignore_path = jh_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_content = (
            "# Ignore ephemeral engine db and search cache\n"
            "engine.db\n"
            "engine.db-wal\n"
            "engine.db-shm\n"
            "cache/\n"
            "*.tmp\n"
        )
        try:
            gitignore_path.write_text(gitignore_content, encoding="utf-8")
        except OSError:
            pass

    return jh_dir


def _clean_variant_name(path: Path) -> str:
    """Derive human-friendly variant name from filename.

    e.g. 'backend-engineer.pdf' -> 'Backend Engineer'
         'John_Doe_CV_2026.docx' -> 'John Doe CV 2026'
         'resume.pdf' -> 'Default Resume'
    """
    stem = path.stem
    clean = re.sub(r"[-_.]+", " ", stem).strip()
    # Normalize common abbreviations
    tokens = clean.split()
    if not tokens:
        return "Resume"

    formatted = []
    for t in tokens:
        tl = t.lower()
        if tl in {"cv", "ats", "ai", "ml", "api", "ui", "ux", "qa", "it", "hr"}:
            formatted.append(tl.upper())
        else:
            formatted.append(t.capitalize())

    res = " ".join(formatted)
    if res.lower() in {"resume", "cv", "my resume", "default"}:
        return "Default Resume"
    return res


def _is_probable_resume_text(text: str) -> bool:
    """Heuristic check to confirm text file looks like a resume and not source code or notes."""
    if len(text.strip()) < 40:
        return False
    lower = text.lower()
    matches = sum(1 for w in RESUME_HEURISTIC_WORDS if w in lower)
    has_contact = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text) or re.search(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", text))
    return matches >= 2 or (matches >= 1 and has_contact)


def discover_resumes(workspace_path: str | Path) -> list[dict[str, Any]]:
    """Scan workspace for resume documents in priority order:

    1. resumes/, resume/, cv/ subdirectories (any depth)
    2. Files matching *resume*, *cv*, *curriculum* in workspace root
    3. Any .pdf, .docx, .txt in root passing heuristic checks
    """
    ws = Path(workspace_path).resolve()
    if not ws.exists():
        return []

    found_files: dict[str, dict[str, Any]] = {}
    valid_exts = {".pdf", ".docx", ".txt"}

    # Priority 1: dedicated resume directories
    for resume_dir_name in ("resumes", "resume", "cv", "cvs"):
        candidate_dir = ws / resume_dir_name
        if candidate_dir.is_dir():
            for root, dirs, files in os.walk(candidate_dir):
                # Filter out ignored dirs
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
                for f in files:
                    fp = Path(root) / f
                    ext = fp.suffix.lower()
                    if ext in valid_exts:
                        abs_str = str(fp.resolve())
                        if abs_str not in found_files:
                            try:
                                stat = fp.stat()
                                found_files[abs_str] = {
                                    "path": abs_str,
                                    "filename": fp.name,
                                    "ext": ext,
                                    "name": _clean_variant_name(fp),
                                    "size": stat.st_size,
                                    "mtime": stat.st_mtime,
                                    "source_priority": 1,
                                }
                            except OSError:
                                continue

    # Priority 2: root files matching resume/cv/curriculum keywords
    # Priority 3: other root pdf/docx/txt
    try:
        root_entries = list(ws.iterdir())
    except OSError:
        root_entries = []

    for item in root_entries:
        if not item.is_file():
            continue
        ext = item.suffix.lower()
        if ext not in valid_exts:
            continue
        abs_str = str(item.resolve())
        if abs_str in found_files:
            continue

        stem_lower = item.stem.lower()
        if stem_lower in NON_RESUME_FILENAMES:
            continue

        is_named_resume = any(k in stem_lower for k in ("resume", "cv", "curriculum", "bio"))
        try:
            stat = item.stat()
        except OSError:
            continue

        if is_named_resume:
            found_files[abs_str] = {
                "path": abs_str,
                "filename": item.name,
                "ext": ext,
                "name": _clean_variant_name(item),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "source_priority": 2,
            }
        else:
            # Heuristic for generic .pdf, .docx, .txt in root
            if ext == ".txt":
                try:
                    raw = item.read_bytes()
                    text = raw.decode("utf-8", errors="ignore")
                    if not _is_probable_resume_text(text):
                        continue
                except Exception:
                    continue

            found_files[abs_str] = {
                "path": abs_str,
                "filename": item.name,
                "ext": ext,
                "name": _clean_variant_name(item),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "source_priority": 3,
            }

    # Sort results by priority ascending, then by name
    resumes = sorted(
        found_files.values(),
        key=lambda x: (x.get("source_priority", 3), x.get("name", "").lower()),
    )
    return resumes


def parse_resume_variant(file_path: str | Path) -> dict[str, Any]:
    """Read and parse a resume file into a profile dictionary.

    Returns the parsed profile enriched with metadata (_source_file, _variant_name,
    _parsed_at, _report).
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Resume file not found: {path}")

    raw = path.read_bytes()
    filename = path.name
    text = resume_parser.extract_text(filename, raw)
    profile, report = resume_parser.parse_resume(text)

    variant_name = _clean_variant_name(path)

    profile["_source_file"] = str(path)
    profile["_variant_name"] = variant_name
    profile["_parsed_at"] = now_iso()
    profile["_report"] = report

    # If target_title is empty, fallback to variant name
    if not profile.get("target_title") and variant_name != "Default Resume":
        profile["target_title"] = variant_name

    return profile
