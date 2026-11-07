"""Shared plumbing for the MCP tools: one result envelope, error handling, compact job cards.

Every tool returns the same envelope::

    {"status": "ok" | "partial" | "error", "success": bool, "data": {...}, "warnings": [...],
     "sources": [...], "error": {...} (only on error), "correlation_id": "...",
     "schema_version": "1.1", "generated_at": "..."}

Tools return a plain dict (the data) or a ``Result``. They raise ``ToolError`` for problems the
caller can fix. Any other exception is logged and returned as a short, safe error message.
"""

from __future__ import annotations

import functools
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import db, freshness, preferences
from .observability import record_tool_call
from .util import now_iso, stable_id

log = logging.getLogger("jobhunter.tools")

SCHEMA_VERSION = "1.1"
MAX_ENVELOPE_BYTES = 150_000


class ToolError(Exception):
    """A problem the caller can fix. The message and hint go back to the model."""

    def __init__(self, message: str, code: str = "invalid_input", hint: str = ""):
        super().__init__(message)
        self.code, self.hint = code, hint


@dataclass
class Result:
    data: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    status: str = "ok"


def correlation_id() -> str:
    return uuid.uuid4().hex[:12]


def envelope(status: str = "ok", data: Optional[dict] = None, warnings: Optional[list] = None,
             sources: Optional[list] = None, cid: str = "", error: Optional[dict] = None) -> dict[str, Any]:
    env: dict[str, Any] = {
        "status": status, "success": status in ("ok", "partial"), "data": data or {},
        "warnings": list(warnings or []), "sources": list(sources or []),
        "correlation_id": cid or correlation_id(), "schema_version": SCHEMA_VERSION, "generated_at": now_iso(),
    }
    if error:
        env["error"] = error
    return env


def make_tool_decorator(mcp: Any) -> Callable:
    """Return a decorator that registers a function as an MCP tool inside the standard envelope."""

    def tool(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            cid, t0 = correlation_id(), time.time()
            try:
                out = fn(*args, **kwargs)
                res = out if isinstance(out, Result) else Result(data=out if isinstance(out, dict) else {"result": out})
                env = envelope(res.status, res.data, res.warnings, res.sources, cid)
                outcome = res.status
            except ToolError as e:
                env = envelope("error", warnings=[str(e)], cid=cid,
                               error={"code": e.code, "message": str(e), "hint": e.hint})
                outcome = "error"
            except Exception as e:  # never leak a traceback to the model
                log.exception("Tool %s failed", fn.__name__)
                env = envelope("error", warnings=[f"{fn.__name__} failed: {str(e)[:160]}"], cid=cid,
                               error={"code": "internal_error", "message": str(e)[:160], "hint": "Check the server log."})
                outcome = "error"
            try:
                size = len(json.dumps(env, default=str))
                if size > MAX_ENVELOPE_BYTES:
                    env["warnings"].append(f"Result is large ({size // 1024} KB). Ask for fewer items or use get_job_details for one job.")
                record_tool_call(fn.__name__, cid, outcome=outcome, duration_ms=(time.time() - t0) * 1000)
            except Exception:
                pass
            return env

        mcp.tool()(wrapper)
        tool.registry[fn.__name__] = wrapper
        return wrapper

    tool.registry = {}  # name -> wrapped tool, so the team layer can call tools in code
    return tool


# ------------------------------------------------------------------ resumes and jobs

def resolve_profile(name: str = "", overlay: bool = True, require: bool = True) -> dict[str, Any]:
    """Find a resume profile by id or name (exact, then partial), else the active one."""
    profile: Optional[dict] = None
    target = (name or "").strip().lower()
    if target:
        profiles = db.list_resume_profiles()
        hit = next((p for p in profiles if p["id"].lower() == target or p["name"].lower() == target), None) \
            or next((p for p in profiles if target in p["name"].lower()), None)
        if not hit:
            raise ToolError(f"Resume '{name}' not found.", hint=f"Available: {[p['name'] for p in profiles]}")
        profile = db.get_profile(hit["id"])
    else:
        profile = db.get_profile()
    if require and (not profile or profile.get("_is_empty")):
        raise ToolError("No resume found.", code="no_resume", hint="Put a PDF, DOCX or TXT resume in the workspace and call scan_resumes.")
    return preferences.overlay_profile(profile, None) if overlay and profile else (profile or {})


def job_and_profile(job_id: str = "", title: str = "", company: str = "", description: str = "",
                    resume_name: str = "", salary: str = "", location: str = "", url: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """Retrieve or build a job and resolve the target profile."""
    profile = resolve_profile(resume_name, overlay=True, require=False)
    job = build_job(job_id, title, company, description, url=url, salary=salary, location=location) if (job_id or title or description) else {}
    return job, profile


def build_job(job_id: str = "", title: str = "", company: str = "", description: str = "", url: str = "",
              salary: str = "", location: str = "") -> dict[str, Any]:
    """A stored job by id, or a job built from pasted text."""
    if job_id:
        job = db.get_job(job_id)
        if not job:
            raise ToolError(f"No stored job with id '{job_id}'.", code="not_found",
                            hint="Call search_jobs or get_saved_jobs first, and use the job_id from those results.")
        return job
    if not (title or description):
        raise ToolError("Give a job_id, or a job_title with a description.", hint="job_id comes from search_jobs results.")
    from .sources import make_job
    return make_job(id=f"manual-{stable_id(title, company, description[:80])}", title=title, company=company or "Unknown",
                    description=description, url=url, salary=salary, location=location, source="Pasted", source_tier="")


def score_against(job: dict, profile: dict) -> dict:
    """Score a job for a profile and fill the ranking fields. Works on a copy."""
    from . import pipeline, scoring
    j = dict(job)
    j.update(scoring.score_job(j, profile))
    pipeline._rank_opportunity(j)
    pipeline.enrich_recommendation_insights(j, profile)
    return j


# ------------------------------------------------------------------ compact output

def _posted_label(j: dict) -> str:
    days = j.get("days_old")
    if days is None and j.get("posted_at"):
        from .util import days_since
        d = days_since(j["posted_at"])
        days = None if d is None else int(d)
    if days is None:
        return j.get("posted_relative") or ""
    return "today" if days <= 0 else ("1 day ago" if days == 1 else f"{days} days ago")


def card(j: dict, detail: bool = False) -> dict[str, Any]:
    """A small, model-friendly view of a job. The full record is one get_job_details call away."""
    out = {
        "job_id": j.get("job_key") or j.get("id"),
        "title": j.get("title", ""), "company": j.get("company", ""), "location": j.get("location", ""),
        "work_mode": j.get("work_mode", ""), "job_type": j.get("job_type", ""), "seniority": j.get("seniority", ""),
        "salary": j.get("salary", ""),
        "fit_score": j.get("score"), "opportunity_score": j.get("opportunity_score"),
        "posted": _posted_label(j), "freshness": freshness.evaluate_freshness(j).value,
        "apply_url": j.get("direct_apply_url") or j.get("url", ""),
        "sources": j.get("source_names") or ([j["source"]] if j.get("source") else []),
        "direct_from_employer": j.get("source_kind") == "Direct employer ATS" or bool(j.get("is_verified_ats")),
        "is_new": bool(j.get("is_new")),
        "matched_skills": (j.get("matched_skills") or [])[:6],
        "missing_skills": (j.get("missing_skills") or [])[:5],
        "why": (j.get("recommendation_hook") or "")[:220],
    }
    if j.get("is_dream_company"):
        out["dream_company"] = True
    if detail:
        out["score_breakdown"] = j.get("score_breakdown") or {}
    return out


def cards(jobs: list[dict], limit: int) -> list[dict]:
    return [card(j) for j in jobs[:limit]]


def clip(text: str, limit: int) -> tuple[str, bool]:
    text = text or ""
    return (text, False) if len(text) <= limit else (text[:limit].rsplit(" ", 1)[0] + " ...", True)


def clamp(value: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low
