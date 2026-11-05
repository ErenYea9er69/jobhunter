"""The short answer for the client. The long report stays as the audit trail.

The client's AI should relay the ``brief``. It is built only from the mission's results, and every string
that came from the web passes through ``safety.inline`` first.
"""

from __future__ import annotations

from typing import Any

from . import safety
from .reflect import fit_label

_LINK = {"live": "live", "dead": "dead", "not_checked": "not checked"}


def _link(state: str) -> str:
    return _LINK.get(state, f"not confirmed ({state})")


def build(*, headline: str, status: str, jobs: list[dict], removed: list[dict], docs: list[dict], decisions: list[str],
          blocked: list[str], insights: list[dict], not_verified: list[str], next_steps: list[str], facts: list[str], limit_jobs: int = 5) -> str:
    L: list[str] = [headline]
    for i, j in enumerate(jobs[:limit_jobs], start=1):
        v = j.get("verification") or {}
        score = j.get("fit_score")
        tag = f"Fit {score:g} ({fit_label(score)})" if isinstance(score, (int, float)) else "Not scored"
        extras = [x for x in (safety.inline(j.get("salary"), 40), "new" if j.get("is_new") else "") if x]
        L.append(f"{i}. {safety.inline(j.get('title'), 70)} at {safety.inline(j.get('company'), 50)}, {safety.inline(j.get('location') or 'location not listed', 40)}. "
                 f"{tag}. Link: {_link(v.get('link', 'not_checked'))}." + (" " + ", ".join(extras) + "." if extras else "") + f" Job id {j.get('job_id')}.")
        miss = j.get("missing_skills") or []
        if (j.get("gaps") or {}).get("real_gaps"):
            L.append("   Gaps: " + ", ".join(safety.inline(g, 30) for g in j["gaps"]["real_gaps"][:3]) + ".")
        elif miss:
            L.append("   Missing: " + ", ".join(safety.inline(g, 30) for g in miss[:3]) + ".")
    if len(jobs) > limit_jobs:
        L.append(f"(+{len(jobs) - limit_jobs} more in the data.)")
    if removed:
        L.append(f"The Reviewer removed {len(removed)} job(s): " + "; ".join(f"{safety.inline(r.get('company'), 30)} ({safety.inline((r.get('reasons') or [''])[0], 70)})" for r in removed[:2]) + ".")
    for d in docs:
        v = (d.get("review") or {}).get("verdict", "pass")
        L.append(f"{d.get('kind', 'document').capitalize()}" + (f" for job {d['job_id']}" if d.get("job_id") else "") + f": {v}" + (f". File: {d['approved_file']}" if d.get("approved_file") else "") + ".")
        for f in (d.get("review") or {}).get("findings", [])[:2]:
            L.append(f"   {f['severity']}: {safety.inline(f['message'], 140)}")
    for line in facts:
        if line == headline:
            continue
        if line.startswith(("Analyst:", "Ops:", "Preferences", "Source added", "Tracked", "Excluded", "Exported", "Recorded")):
            L.append(safety.inline(line, 160))
    for x in insights[:2]:
        L.append(f"Note: {x['finding']} {x['evidence']} {x['action']}")
    for b in blocked[:3]:
        L.append("Blocked: " + safety.inline(b, 200))
    if decisions:
        L.append("I need from you: " + " ".join(safety.inline(d, 260) for d in decisions[:3]))
    if not_verified:
        L.append("Not verified: " + safety.inline(not_verified[0], 180) + (f" (+{len(not_verified) - 1} more)" if len(not_verified) > 1 else ""))
    if next_steps and status in ("done", "partial"):
        L.append("Next: " + safety.inline(next_steps[0], 160))
    return "\n".join(L)
