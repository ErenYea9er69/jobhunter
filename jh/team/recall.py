"""Resolve "the second one" or "the Adyen job" to a real job id.

People point at jobs the way they talk: by position in the last list, or by company name. This module
looks the pointer up in the last search the CEO ran, then in the tracker, then in the stored jobs. It
never invents an id. When two jobs fit, it returns the options so the client can choose.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import db, tracker
from . import missions


@dataclass
class Recall:
    job_id: str = ""
    options: list[dict] = field(default_factory=list)
    note: str = ""


def last_list() -> list[dict]:
    """The jobs of the newest mission that showed a list, in the order the client saw them."""
    for row in missions.recent(15):
        if {"hunt", "saved"} & set(row["intents"]):
            m = missions.load(row["id"])
            jobs = (m or {}).get("data", {}).get("jobs") or []
            if jobs:
                return jobs
    return []


def _label(j: dict) -> str:
    return f"{j.get('title') or '?'} at {j.get('company') or '?'}"


def by_position(n: int) -> Recall:
    jobs = last_list()
    if not jobs:
        return Recall(note="I have no earlier list of jobs to count from. Ask me to find jobs first, or give a job_id.")
    idx = (len(jobs) if n < 0 else n) - 1
    if not 0 <= idx < len(jobs):
        return Recall(note=f"The last list had {len(jobs)} job(s), so there is no number {n}.")
    j = jobs[idx]
    return Recall(job_id=j["job_id"], note=f"Number {idx + 1} in your last list is {_label(j)} (job id {j['job_id']}).")


def by_company(name: str) -> Recall:
    needle = (name or "").lower().strip()
    if not needle:
        return Recall(note="No company given.")
    shown = [j for j in last_list() if needle in (j.get("company") or "").lower()]
    if len(shown) == 1:
        j = shown[0]
        return Recall(job_id=j["job_id"], note=f"The {name.title()} job in your last list is {_label(j)} (job id {j['job_id']}).")
    pool: dict[str, dict] = {j["job_id"]: j for j in shown}
    if not pool:
        for a in tracker.list_applications():
            if needle in (a.get("company") or "").lower() and a.get("job_id"):
                pool.setdefault(a["job_id"], {"job_id": a["job_id"], "title": a.get("title"), "company": a.get("company")})
        with db.session() as c:
            rows = c.execute("SELECT job_key, title, company FROM search_jobs WHERE lower(company) LIKE ? ORDER BY score DESC LIMIT 6", (f"%{needle}%",)).fetchall()
        for r in rows:
            pool.setdefault(r["job_key"], {"job_id": r["job_key"], "title": r["title"], "company": r["company"]})
    if len(pool) == 1:
        j = next(iter(pool.values()))
        return Recall(job_id=j["job_id"], note=f"The only stored job at {name.title()} is {_label(j)} (job id {j['job_id']}).")
    if pool:
        return Recall(options=list(pool.values())[:5], note=f"More than one job matches '{name}'.")
    return Recall(note=f"I found no job at '{name}' in your last list, your tracker or your stored jobs.")


def resolve(reference: str) -> Recall:
    ref = (reference or "").strip().lower()
    if not ref:
        return Recall()
    if re.fullmatch(r"-?\d{1,2}", ref):
        return by_position(int(ref))
    return by_company(ref)


import re  # noqa: E402  (kept at the bottom so the module reads top-down)
