"""Company career boards: the starter list, your watchlist, and boards found along the way.

Why this exists: the big job boards show the same famous employers. Most openings at small
and mid-size companies live only on the company's own applicant-tracking system. Three
inputs feed one pool of boards:

1. ``STARTER``        a short built-in list (unverified slugs; dead ones prune themselves)
2. the watchlist      companies you add with ``add_job_source``
3. discovered boards  every job link that points at a known ATS adds that company's board
                      to the pool, so each search teaches the next one

All boards are fetched together by ``CompanyBoards`` with its own thread pool and time
budget, so a long watchlist cannot starve the other sources. Each board keeps a health
record. A board that fails three times in a row rests for 24 hours.
"""

from __future__ import annotations

import concurrent.futures as cf
import re
import threading
import time
import uuid
from typing import Optional

from . import config, db
from .util import now_iso, stable_id

# (board_type, slug, display name). Slugs come from public career-page URLs. Unverified: a wrong
# slug costs one failed request, then the board rests for a day.
STARTER: tuple[tuple[str, str, str], ...] = (
    ("ashby", "ramp", "Ramp"), ("ashby", "notion", "Notion"), ("ashby", "plaid", "Plaid"),
    ("ashby", "cursor", "Cursor"), ("ashby", "zapier", "Zapier"), ("ashby", "perplexity", "Perplexity AI"),
    ("ashby", "vanta", "Vanta"), ("ashby", "resend", "Resend"), ("ashby", "elevenlabs", "ElevenLabs"),
    ("ashby", "cognition", "Cognition"), ("ashby", "harvey", "Harvey"), ("ashby", "langchain", "LangChain"),
    ("ashby", "railway", "Railway"), ("ashby", "neon", "Neon"), ("ashby", "replit", "Replit"),
    ("ashby", "linear", "Linear"), ("ashby", "modal", "Modal"), ("ashby", "posthog", "PostHog"),
    ("ashby", "benchling", "Benchling"),
    ("greenhouse", "brex", "Brex"), ("greenhouse", "scaleai", "Scale AI"), ("greenhouse", "fivetran", "Fivetran"),
    ("greenhouse", "gusto", "Gusto"),
    # Europe, Middle East and Africa friendly employers
    ("greenhouse", "adyen", "Adyen"), ("greenhouse", "monzo", "Monzo"), ("greenhouse", "getyourguide", "GetYourGuide"),
    ("greenhouse", "contentful", "Contentful"), ("greenhouse", "celonis", "Celonis"), ("greenhouse", "n26", "N26"),
    ("greenhouse", "intercom", "Intercom"), ("greenhouse", "gitlab", "GitLab"), ("greenhouse", "elastic", "Elastic"),
    ("greenhouse", "mongodb", "MongoDB"), ("greenhouse", "datadog", "Datadog"), ("greenhouse", "cloudflare", "Cloudflare"),
    ("greenhouse", "duolingo", "Duolingo"), ("greenhouse", "webflow", "Webflow"),
    ("lever", "spotify", "Spotify"), ("lever", "mistral", "Mistral AI"), ("lever", "palantir", "Palantir"),
)

FAIL_LIMIT = 3
REST_SECONDS = 24 * 3600
_cache: dict[tuple[str, str], tuple[float, list]] = {}
_cache_lock = threading.Lock()
_last_run: dict = {}

# Preferred order when one company name matches several boards.
BOARD_PRIORITY = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee", "personio",
                  "teamtailor", "bamboohr", "breezy", "pinpoint", "lever eu")


def _src():
    from . import sources
    return sources


# ------------------------------------------------------------------ storage

def _upsert_health(board: str, slug: str, name: str, found_via: str, ok: Optional[bool], count: int = 0) -> None:
    now = time.time()
    with db.session() as c:
        row = c.execute("SELECT fail_count FROM discovered_boards WHERE board_type=? AND slug=?", (board, slug)).fetchone()
        if row is None:
            c.execute("INSERT INTO discovered_boards (board_type,slug,company_name,first_seen,found_via) VALUES (?,?,?,?,?)",
                      (board, slug, name, now_iso(), found_via))
            fails = 0
        else:
            fails = row["fail_count"]
        if ok is None:
            return
        if ok:
            c.execute("UPDATE discovered_boards SET last_fetched=?, last_ok=?, job_count=?, fail_count=0 WHERE board_type=? AND slug=?",
                      (now, now, count, board, slug))
        else:
            c.execute("UPDATE discovered_boards SET last_fetched=?, fail_count=? WHERE board_type=? AND slug=?",
                      (now, fails + 1, board, slug))


def harvest(jobs: list[dict]) -> int:
    """Remember every ATS board that the given jobs link to. Returns how many boards were new."""
    from .sources.ats_boards import board_from_url
    boards = _src().BOARDS
    found: dict[tuple[str, str], tuple[str, str]] = {}
    for j in jobs:
        urls = [j.get("url"), j.get("direct_apply_url"), j.get("company_url")]
        desc = j.get("description") or ""
        urls += re.findall(r"https?://[^\s\"'<>)]+", desc[:6000])[:6]
        for u in urls:
            hit = board_from_url(u or "")
            if hit and hit[0] in boards:
                found.setdefault(hit, (j.get("company") or "", j.get("source") or ""))
    if not found:
        return 0
    new = 0
    try:
        with db.session() as c:
            total = c.execute("SELECT COUNT(*) AS n FROM discovered_boards").fetchone()["n"]
            for (board, slug), (company, via) in found.items():
                if total + new >= config.DISCOVERED_BOARDS_MAX:
                    break
                cur = c.execute("INSERT OR IGNORE INTO discovered_boards (board_type,slug,company_name,first_seen,found_via) VALUES (?,?,?,?,?)",
                                (board, slug, company, now_iso(), f"found in {via}"[:60]))
                new += cur.rowcount or 0
    except Exception:
        return 0
    return new


def _watchlist() -> list[dict]:
    with db.session() as c:
        return [dict(r) for r in c.execute("SELECT * FROM watchlist")]


def _health() -> dict[tuple[str, str], dict]:
    with db.session() as c:
        return {(r["board_type"], r["slug"]): dict(r) for r in c.execute("SELECT * FROM discovered_boards")}


def select_boards(limit: int) -> list[dict]:
    """Choose which boards to fetch now: watchlist first, then least recently fetched."""
    health = _health()
    now = time.time()
    entries: dict[tuple[str, str], dict] = {}
    for w in _watchlist():
        key = ((w["board_type"] or "").lower(), w["slug"])
        entries[key] = {"board": key[0], "slug": key[1], "name": w["company_name"], "via": "watchlist", "priority": 0}
    for board, slug, name in STARTER:
        entries.setdefault((board, slug), {"board": board, "slug": slug, "name": name, "via": "starter", "priority": 2})
    for (board, slug), h in health.items():
        if (h["found_via"] or "").startswith("found in") and (board, slug) not in entries:
            entries[(board, slug)] = {"board": board, "slug": slug, "name": h["company_name"] or slug.replace("-", " ").title(),
                                      "via": "discovered", "priority": 1}
    chosen = []
    for key, e in entries.items():
        h = health.get(key) or {}
        if e["priority"] > 0 and h.get("fail_count", 0) >= FAIL_LIMIT and now - (h.get("last_fetched") or 0) < REST_SECONDS:
            continue
        e["_age"] = h.get("last_fetched") or 0
        chosen.append(e)
    chosen.sort(key=lambda e: (e["priority"] != 0, e["_age"]))
    return chosen[:max(1, limit)]


# ------------------------------------------------------------------ fetching

def fetch_board(board: str, slug: str, name: str, ttl: Optional[float] = None) -> list[dict]:
    """Fetch one board with a short-lived cache."""
    ttl = config.CACHE_TTL_SECONDS if ttl is None else ttl
    key = (board, slug)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return [dict(j) for j in hit[1]]
    jobs = _src().BOARDS[board].fetch_company(slug, name)
    with _cache_lock:
        if len(_cache) > 800:
            _cache.clear()
        _cache[key] = (time.time(), jobs)
    return [dict(j) for j in jobs]


def last_run() -> dict:
    return dict(_last_run)


def _make_source():
    from .sources import Source, _matches

    class CompanyBoards(Source):
        name, tier = "Company Boards", "Direct company ATS"

        def fetch(self, query, location):
            entries = select_boards(config.COMPANY_BOARDS_PER_SEARCH)
            stats = {"tried": 0, "ok": 0, "failed": 0, "skipped_budget": 0, "jobs": 0,
                     "by_origin": {"watchlist": 0, "starter": 0, "discovered": 0}}
            out: list[dict] = []
            budget_end = time.time() + config.COMPANY_BOARD_BUDGET_SECONDS
            boards = _src().BOARDS

            def one(e):
                if e["board"] not in boards:
                    raise ValueError("unknown board")
                return fetch_board(e["board"], e["slug"], e["name"])

            pool = cf.ThreadPoolExecutor(max_workers=config.COMPANY_BOARD_WORKERS, thread_name_prefix="boards")
            futs = {pool.submit(one, e): e for e in entries}
            try:
                for fut in cf.as_completed(futs, timeout=max(1.0, budget_end - time.time())):
                    e = futs[fut]
                    stats["tried"] += 1
                    try:
                        jobs = fut.result()
                    except Exception:
                        stats["failed"] += 1
                        _upsert_health(e["board"], e["slug"], e["name"], e["via"], False)
                        continue
                    stats["ok"] += 1
                    _upsert_health(e["board"], e["slug"], e["name"], e["via"], True, len(jobs))
                    for j in jobs:
                        j["found_via"] = e["via"]
                        if e["via"] == "starter":
                            j["is_startup"] = True
                        # Watched companies are shown in full; the rest are filtered by the search terms.
                        if e["via"] != "watchlist" and query and not _matches(query, j.get("title", ""), j.get("company", "")):
                            continue
                        out.append(j)
                        stats["by_origin"][e["via"]] += 1
            except cf.TimeoutError:
                stats["skipped_budget"] = sum(1 for f in futs if not f.done())
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            stats["jobs"] = len(out)
            _last_run.clear()
            _last_run.update(stats, at=now_iso(), pool_size=len(entries))
            return out

    return CompanyBoards()


# ------------------------------------------------------------------ detection

_LEGAL = re.compile(r"\b(inc|ltd|llc|gmbh|sarl|sas|sa|ag|plc|corp|corporation|co|company|group|holding|technologies|technology|tech|labs|solutions)\b\.?", re.I)


def slug_candidates(name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9 -]", "", _LEGAL.sub(" ", (name or "").lower())).strip()
    base = re.sub(r"\s+", " ", base)
    raw = re.sub(r"[^a-z0-9 -]", "", (name or "").lower()).strip()
    cands = [base.replace(" ", ""), base.replace(" ", "-"), raw.replace(" ", ""), base.split(" ")[0] if base else ""]
    return [c for c in dict.fromkeys(cands) if c and len(c) > 1][:4]


def detect_all(name: str, budget: float = 15.0) -> list[dict]:
    """Probe every supported ATS for a company name. Returns hits ordered by board priority.

    Each hit carries job count and sample titles so the caller can confirm it is the right company.
    """
    boards = _src().BOARDS
    pairs = [(b, s) for s in slug_candidates(name) for b in boards]
    hits: list[dict] = []

    def probe(board, slug):
        jobs = boards[board].fetch_company(slug, name)
        if not jobs:
            return None
        return {"board_type": board, "slug": slug, "job_count": len(jobs),
                "sample_titles": [j.get("title", "") for j in jobs[:3]], "sample_url": jobs[0].get("url", "")}

    pool = cf.ThreadPoolExecutor(max_workers=12, thread_name_prefix="detect")
    futs = [pool.submit(probe, b, s) for b, s in pairs]
    try:
        for fut in cf.as_completed(futs, timeout=budget):
            try:
                r = fut.result()
                if r:
                    hits.append(r)
            except Exception:
                continue
    except cf.TimeoutError:
        pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    order = {b: i for i, b in enumerate(BOARD_PRIORITY)}
    hits.sort(key=lambda h: (order.get(h["board_type"], 99), -h["job_count"]))
    return hits


def detect_board(name: str) -> Optional[tuple[str, str]]:
    hits = detect_all(name)
    return (hits[0]["board_type"], hits[0]["slug"]) if hits else None


# ------------------------------------------------------------------ watchlist management

def add_company(name: str = "", url: str = "", board_type: str = "", slug: str = "", target_role: str = "") -> dict:
    """Add a company to the watchlist from a careers URL, an explicit board and slug, or just a name."""
    from .sources.ats_boards import board_from_url
    boards = _src().BOARDS
    alternatives: list[dict] = []
    detected = False
    if url:
        hit = board_from_url(url)
        if not hit:
            raise ValueError("That URL is not a known applicant-tracking page. Add it as a career_page instead.")
        board_type, slug = hit
        name = name or slug.replace("-", " ").title()
    elif not (board_type and slug):
        if not name:
            raise ValueError("Give a company name, a careers URL, or a board_type with a slug.")
        hits = detect_all(name)
        if not hits:
            raise ValueError(f"No public careers board found for '{name}'. Try its careers URL, or add the page as a career_page.")
        board_type, slug = hits[0]["board_type"], hits[0]["slug"]
        alternatives = hits[1:4]
        detected = True
    board_type = board_type.lower()
    if board_type not in boards:
        raise ValueError(f"board_type must be one of: {', '.join(sorted(boards))}")
    slug = slug.strip()
    name = (name or slug).strip()
    with db.session() as c:
        row = c.execute("SELECT id FROM watchlist WHERE lower(board_type)=? AND slug=?", (board_type, slug)).fetchone()
        if row:
            return {"id": row["id"], "board_type": board_type, "slug": slug, "company": name, "already_watched": True,
                    "auto_detected": detected, "alternatives": alternatives}
        wl_id = f"wl-{uuid.uuid4().hex[:10]}"
        c.execute("INSERT INTO watchlist (id,company_name,slug,board_type,target_role,added_at) VALUES (?,?,?,?,?,?)",
                  (wl_id, name, slug, board_type, target_role or "", now_iso()))
    _cache.pop((board_type, slug), None)
    return {"id": wl_id, "board_type": board_type, "slug": slug, "company": name, "already_watched": False,
            "auto_detected": detected, "alternatives": alternatives}


def remove_company(ident: str) -> bool:
    """Remove a watchlist entry by id, slug or company name."""
    ident = (ident or "").strip()
    with db.session() as c:
        cur = c.execute("DELETE FROM watchlist WHERE id=? OR lower(slug)=lower(?) OR lower(company_name)=lower(?)", (ident, ident, ident))
        return bool(cur.rowcount)


def list_companies() -> dict:
    health = _health()
    watch = []
    for w in _watchlist():
        h = health.get(((w["board_type"] or "").lower(), w["slug"])) or {}
        watch.append({"id": w["id"], "company": w["company_name"], "board_type": w["board_type"], "slug": w["slug"],
                      "target_role": w.get("target_role") or "", "open_jobs": h.get("job_count", 0),
                      "last_ok": bool(h.get("last_ok")), "failing": h.get("fail_count", 0) >= FAIL_LIMIT})
    discovered = [h for k, h in health.items() if h.get("found_via", "").startswith("found in")]
    resting = [h for h in health.values() if h.get("fail_count", 0) >= FAIL_LIMIT]
    return {"watchlist": watch, "starter_count": len(STARTER), "discovered_count": len(discovered),
            "discovered_with_jobs": sum(1 for h in discovered if h.get("job_count", 0) > 0),
            "resting_count": len(resting), "last_run": last_run()}


def make_company_boards_source():
    return _make_source()


__all__ = ["STARTER", "harvest", "select_boards", "fetch_board", "detect_all", "detect_board", "add_company",
           "remove_company", "list_companies", "make_company_boards_source", "slug_candidates", "stable_id"]
