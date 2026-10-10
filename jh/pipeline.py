"""Search orchestration: fan out to sources, enforce a deadline, cache per source, merge, score, remember."""
import concurrent.futures as cf
import json
import re
import time

from . import config, db, dedup, sources as src
from .scoring import score_job
from .util import now_iso, parse_date

_pool = cf.ThreadPoolExecutor(max_workers=config.SEARCH_WORKERS, thread_name_prefix="jh-src")


# ---------------------------------------------------------------- cache and health

def _cache_get(key, max_age):
    with db.session() as c:
        row = c.execute("SELECT payload, fetched_at FROM source_cache WHERE cache_key=?", (key,)).fetchone()
    if row and time.time() - row["fetched_at"] <= max_age:
        return json.loads(row["payload"]), time.time() - row["fetched_at"]
    return None, None


def _cache_put(key, jobs):
    with db.session() as c:
        c.execute("INSERT OR REPLACE INTO source_cache (cache_key,payload,fetched_at) VALUES (?,?,?)",
                  (key, json.dumps(jobs), time.time()))
        c.execute("DELETE FROM source_cache WHERE fetched_at < ?", (time.time() - 3 * 86400,))


def _health(name, ok, ms, error=""):
    with db.session() as c:
        c.execute("INSERT OR IGNORE INTO source_health (source) VALUES (?)", (name,))
        if ok:
            c.execute("UPDATE source_health SET ok_count=ok_count+1, last_ok=?, last_ms=?, last_error='' WHERE source=?",
                      (now_iso(), ms, name))
        else:
            c.execute("UPDATE source_health SET fail_count=fail_count+1, last_error=?, last_ms=? WHERE source=?",
                      (error[:200], ms, name))


def clear_cache():
    with db.session() as c:
        c.execute("DELETE FROM source_cache")


def health_report():
    with db.session() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM source_health ORDER BY source")]
    known = {r["source"] for r in rows}
    for s in src.SEARCH_SOURCES:
        if s.name not in known:
            rows.append({"source": s.name, "ok_count": 0, "fail_count": 0, "last_error": "", "last_ok": None, "last_ms": 0})
    for r in rows:
        match = next((s for s in src.SEARCH_SOURCES if s.name == r["source"]), None)
        r["enabled"] = match.available() if match else True
        r["note"] = match.unavailable_reason() if match and not match.available() else ""
    return rows


# ---------------------------------------------------------------- one source task

def _run_source(label, fn, cache_key, force):
    """Return (jobs, status). Falls back to stale cache if the live call fails."""
    status = {"source": label, "state": "ok", "count": 0, "ms": 0, "stale": False, "error": ""}
    if not force:
        cached, age = _cache_get(cache_key, config.CACHE_TTL_SECONDS)
        if cached is not None:
            status.update(state="cached", count=len(cached))
            return cached, status
    if src.breaker_open(label):
        stale, age = _cache_get(cache_key, config.STALE_CACHE_MAX_SECONDS)
        status.update(state="paused", error="Paused after repeated failures. Retrying in a few minutes.")
        if stale is not None:
            status.update(stale=True, count=len(stale))
            return stale, status
        return [], status
    t0 = time.time()
    try:
        jobs = fn()
        ms = int((time.time() - t0) * 1000)
        src.breaker_record(label, True)
        _health(label, True, ms)
        _cache_put(cache_key, jobs)
        status.update(count=len(jobs), ms=ms)
        return jobs, status
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        src.breaker_record(label, False)
        _health(label, False, ms, str(e))
        stale, age = _cache_get(cache_key, config.STALE_CACHE_MAX_SECONDS)
        status.update(state="failed", error=str(e)[:160], ms=ms)
        if stale is not None:
            status.update(stale=True, count=len(stale), state="stale")
            return stale, status
        return [], status


# ---------------------------------------------------------------- filters

def _norm_mode(job):
    m = (job.get("work_mode") or "").lower()
    loc = (job.get("location") or "").lower()
    if "remote" in m or "remote" in loc or "worldwide" in loc or "anywhere" in loc:
        return "remote"
    if "hybrid" in m or "hybrid" in loc:
        return "hybrid"
    if m or loc:
        return "onsite"
    return "unknown"


def _passes(job, work_mode, location):
    jm = _norm_mode(job)
    wm = (work_mode or "any").lower().replace("-", "")
    if wm not in ("any", "") and jm != "unknown":
        if wm != jm:
            return False
    if location and location.lower() not in ("remote", "worldwide", "any"):
        loc = (job.get("location") or "").lower()
        tokens = [t.strip() for t in re.split(r"[,/]", location.lower()) if len(t.strip()) > 1]
        if jm != "remote" and tokens and not any(t in loc for t in tokens):
            return False
    return True


def _remember(jobs):
    now = now_iso()
    with db.session() as c:
        for j in jobs:
            row = c.execute("SELECT first_seen FROM seen_jobs WHERE job_key=?", (j["job_key"],)).fetchone()
            j["first_seen"] = row["first_seen"] if row else now
            j["is_new"] = row is None
            c.execute("""INSERT INTO seen_jobs (job_key,title,company,url,source_names,first_seen,last_seen,best_score)
                         VALUES (?,?,?,?,?,?,?,?)
                         ON CONFLICT(job_key) DO UPDATE SET last_seen=excluded.last_seen, url=excluded.url,
                         source_names=excluded.source_names, best_score=MAX(best_score, excluded.best_score)""",
                      (j["job_key"], j["title"], j["company"], j["url"], ",".join(j.get("source_names", [])),
                       j["first_seen"], now, j.get("score", 0)))


def _rank_opportunity(job):
    """Combine fit with source authority and evidence of a real opening.

    A famous board alone cannot make a poor match outrank a good one: fit is
    weighted at 70%. The remaining points reward direct employer application
    links, corroborating sources, readable descriptions and fresh postings.
    """
    source_rank = max([job.get("source_rank", 0)] + [s.get("source_rank", 0) for s in job.get("sources", [])])
    direct = 10 if job.get("source_kind") == "Direct employer ATS" else 0
    corroboration = min(10, max(0, len(job.get("sources", [])) - 1) * 4)
    description = min(10, round(len(job.get("description", "") or "") / 700 * 10))
    freshness = job.get("score_breakdown", {}).get("freshness", 0) * 2
    evidence = min(30, direct + corroboration + description + freshness)
    opportunity = int(round(job.get("score", 0) * 0.70 + source_rank * 0.20 + (evidence / 30) * 10))
    kind = job.get("source_kind") or "Job source"
    job["opportunity_score"] = max(0, min(100, opportunity))
    job["ranking"] = {
        "source_authority": source_rank, "source_kind": kind,
        "evidence_points": evidence,
        "reason": f"{kind}; {len(job.get('sources', []))} source(s); {'direct employer application link' if direct else 'board/feed application link'}"
    }


# ---------------------------------------------------------------- main entry

def derive_query(profile):
    return (profile.get("target_title") or "").strip()


def search(query="", location="", work_mode="Any", min_score=0, profile=None, force_refresh=False, limit=None):
    t0 = time.time()
    profile = profile if profile is not None else db.get_profile()
    query = (query or "").strip() or derive_query(profile)
    location = (location or "").strip()
    statuses, raw = [], []

    tasks = {}
    for s in src.SEARCH_SOURCES:
        if not s.available():
            statuses.append({"source": s.name, "state": "disabled", "count": 0, "error": s.unavailable_reason(), "ms": 0, "stale": False})
            continue
        key = f"{s.name}|{query.lower()}|{location.lower()}"
        tasks[_pool.submit(_run_source, s.name, lambda s=s: s.fetch(query, location), key, force_refresh)] = s.name

    with db.session() as c:
        watch = [dict(r) for r in c.execute("SELECT * FROM watchlist")]
    for w in watch:
        board = src.BOARDS.get((w["board_type"] or "").lower())
        if not board:
            continue
        label = f"{board.name}:{w['slug']}"
        key = f"board|{board.name}|{w['slug']}"
        tasks[_pool.submit(_run_source, label, lambda b=board, w=w: b.fetch_company(w["slug"], w["company_name"]), key, force_refresh)] = label

    done, pending = cf.wait(list(tasks), timeout=config.SEARCH_DEADLINE_SECONDS)
    for f in done:
        try:
            jobs, st = f.result()
            raw.extend(jobs)
            statuses.append(st)
        except Exception as e:  # defensive: _run_source already catches source errors
            statuses.append({"source": tasks[f], "state": "failed", "count": 0, "error": str(e)[:160], "ms": 0, "stale": False})
    for f in pending:
        f.cancel()
        statuses.append({"source": tasks[f], "state": "timeout", "count": 0, "ms": int(config.SEARCH_DEADLINE_SECONDS * 1000),
                         "error": "Did not answer before the search deadline.", "stale": False})

    if config.DEMO:
        from .demo import SAMPLE_JOBS
        raw.extend(SAMPLE_JOBS)

    # Watchlist boards return every opening, so keep only those relevant to the query or the user's target.
    if query:
        qwords = [w for w in re.findall(r"[a-z0-9+#]+", query.lower()) if len(w) > 2]
        def relevant(j):
            if not j["source_tier"].startswith("Direct"):
                return True
            hay = f"{j['title']} {j.get('description', '')[:600]}".lower()
            return any(w in hay for w in qwords) if qwords else True
        raw = [j for j in raw if relevant(j)]

    merged = dedup.merge_jobs(raw)

    # Fetch full text for the top candidates whose source only gave a stub, then score everything.
    for j in merged:
        j.update(score_job(j, profile))
        _rank_opportunity(j)
    merged.sort(key=lambda j: (j["opportunity_score"], j["score"], j.get("posted_at") or ""), reverse=True)
    to_enrich = [j for j in merged[:config.ENRICH_TOP_N] if j.get("needs_enrichment")]
    if to_enrich:
        by_name = {s.name: s for s in list(src.BOARDS.values()) + src.SEARCH_SOURCES}
        futs = {_pool.submit(by_name[j["source"]].enrich, j): j for j in to_enrich if j["source"] in by_name}
        d2, _ = cf.wait(list(futs), timeout=6)
        for f in d2:
            try:
                f.result()
                futs[f].update(score_job(futs[f], profile))
                _rank_opportunity(futs[f])
            except Exception:
                pass
        merged.sort(key=lambda j: (j["opportunity_score"], j["score"], j.get("posted_at") or ""), reverse=True)

    filtered = []
    for j in merged:
        if min_score and j["score"] < int(min_score):
            continue
        if not _passes(j, work_mode, location):
            continue
        filtered.append(j)
    filtered = filtered[: (limit or config.MAX_RESULTS)]
    _remember(filtered)

    failed = [s for s in statuses if s["state"] in ("failed", "timeout", "paused", "stale")]
    return {
        "count": len(filtered), "query": query, "jobs": filtered, "sources": sorted(statuses, key=lambda s: s["source"]),
        "ranking": {"method": "fit 70% + source authority 20% + evidence 10%", "workers": config.SEARCH_WORKERS},
        "partial": bool(failed), "elapsed_ms": int((time.time() - t0) * 1000),
        "profile_empty": bool(profile.get("_is_empty")),
        "warnings": ([f"{len(failed)} source(s) did not respond. Showing results from the rest."] if failed else []),
    }
