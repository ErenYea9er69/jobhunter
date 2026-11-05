"""The CEO's second look at a search: rank the shortlist, then ask what the results say.

``rank`` orders reviewed jobs so the client sees the best first, with no single source filling the list.
``insights`` turns numbers from the results into plain findings, each with its evidence and a next move.
Both are pure functions over the job cards. They add no facts. A finding is only made from data that is
in the results.
"""

from __future__ import annotations

import math
from collections import Counter
from statistics import median
from typing import Any, Optional

from .. import regions

SMALL_SOURCES = {"Regional Boards", "Job Sites", "Jooble", "Career Page", "Custom Feed", "JobTech", "Company Boards"}


def fit_label(score: Any) -> str:
    if not isinstance(score, (int, float)):
        return "not scored"
    return "strong" if score >= 70 else ("decent" if score >= 50 else "stretch")


def _primary(job: dict) -> str:
    s = job.get("sources") or []
    return s[0] if s else ""


def rank(jobs: list[dict], *, small: bool, limit: int) -> list[dict]:
    """Best first. Warnings cost points. Small-employer mode favours small and regional sources.

    No source may fill more than 40% of the list while other sources still have jobs.
    """
    def key(j: dict) -> float:
        base = float(j.get("opportunity_score") or j.get("fit_score") or 0)
        base -= 6 * len((j.get("verification") or {}).get("findings") or [])
        if small and set(j.get("sources") or []) & SMALL_SOURCES:
            base += 8
        return -base
    ordered = sorted(jobs, key=key)
    cap = max(3, math.ceil(limit * 0.4))
    taken: list[dict] = []
    rest: list[dict] = []
    counts: Counter = Counter()
    for j in ordered:
        src = _primary(j)
        if counts[src] >= cap:
            rest.append(j)
            continue
        counts[src] += 1
        taken.append(j)
    return (taken + rest)[:limit]


def insights(jobs: list[dict], removed: list[dict], *, prefs: Optional[dict] = None, checked: int = 0, first_search: bool = False) -> list[dict[str, str]]:
    """Findings about the whole result. Each has ``finding``, ``evidence`` and ``action``."""
    out: list[dict[str, str]] = []
    prefs = prefs or {}
    scores = [j["fit_score"] for j in jobs if isinstance(j.get("fit_score"), (int, float))]
    if scores:
        best, mid = max(scores), median(scores)
        strong = sum(1 for s in scores if s >= 70)
        if best < 50:
            gaps = Counter(s for j in jobs for s in (j.get("missing_skills") or []))
            top = ", ".join(s for s, _ in gaps.most_common(3))
            out.append({"finding": "No job is a strong fit right now.", "evidence": f"The best fit score is {best:g} of 100 and the median is {mid:g}.",
                        "action": "Ask for a skill roadmap" + (f". The most common missing skills are {top}." if top else ".")})
        elif strong:
            out.append({"finding": f"{strong} of {len(scores)} jobs fit strongly.", "evidence": f"Fit scores of 70 or more: {strong}. Best: {best:g}.", "action": "Start with the top ones."})
    targets = regions.resolve_targets(prefs, {}, "") if prefs else []
    if targets and jobs:
        outside = [j for j in jobs if "remote" not in str(j.get("work_mode", "")).lower()
                   and (regions.country_of_location(j.get("location") or "") or targets[0]) not in targets]
        if len(outside) * 2 > len(jobs):
            out.append({"finding": "Most results are outside your target countries.", "evidence": f"{len(outside)} of {len(jobs)} are onsite or hybrid elsewhere.",
                        "action": "Tell me if you are open to relocating, or to remote work."})
    srcs = Counter(_primary(j) for j in jobs if _primary(j))
    if len(jobs) >= 5 and srcs:
        name, n = srcs.most_common(1)[0]
        if n / len(jobs) > 0.6:
            out.append({"finding": f"Most results come from one source ({name}).", "evidence": f"{n} of {len(jobs)} jobs.",
                        "action": "Add a local job site with the discover and add-site steps to widen the search."})
    new = sum(1 for j in jobs if j.get("is_new"))
    if jobs and new and not first_search:
        out.append({"finding": f"{new} of {len(jobs)} jobs are new since your last search.", "evidence": "From the stored history.", "action": "Look at the new ones first."})
    live = sum(1 for j in jobs if (j.get("verification") or {}).get("link") == "live")
    tried = sum(1 for j in jobs if (j.get("verification") or {}).get("link") not in (None, "not_checked"))
    if tried >= 3 and live == 0:
        out.append({"finding": "No posting page could be confirmed.", "evidence": f"0 of {tried} pages showed the job in plain text.",
                    "action": "Many job sites block checks or load with scripts. Open the link yourself before you apply."})
    if removed and checked and len(removed) / checked >= 0.3:
        codes = Counter(c for r in removed for c in r.get("codes", []))
        why = ", ".join(c for c, _ in codes.most_common(2))
        out.append({"finding": "The Reviewer removed many jobs.", "evidence": f"{len(removed)} of {checked} removed" + (f" (mostly: {why})." if why else "."),
                    "action": "Check source health. A weak source may be adding noise."})
    return out[:5]
