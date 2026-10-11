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
        from .scoring import classify_job_country
        loc = (job.get("location") or "").lower()
        req_country = classify_job_country(location)
        job_country = job.get("country") or classify_job_country(loc, job.get("title", ""), job.get("description", ""))
        tokens = [t.strip() for t in re.split(r"[,/]", location.lower()) if len(t.strip()) > 1]

        if jm != "remote":
            # On-site or hybrid: must match the target city/tokens or target country
            matches_token = any(t in loc for t in tokens) if tokens else False
            matches_country = (req_country != "Worldwide" and job_country == req_country)
            if not (matches_token or matches_country):
                return False
        else:
            # Remote job:
            # 1. Matches requested country directly (e.g. Remote within Tunisia)
            if req_country != "Worldwide" and job_country == req_country:
                return True

            text_hay = f"{loc} {job.get('description', '')[:500]}".lower()

            is_us_only = bool(re.search(r"\b(us only|u\.s\. only|united states only|must reside in (the )?us|must be located in (the )?united states)\b", text_hay))
            is_uk_only = bool(re.search(r"\b(uk only|united kingdom only|must reside in (the )?uk)\b", text_hay))
            is_eu_only = bool(re.search(r"\b(eu only|europe only|emea only|schengen)\b", text_hay))
            is_can_only = bool(re.search(r"\b(canada only|must reside in canada)\b", text_hay))
            is_ind_only = bool(re.search(r"\b(india only|must reside in india)\b", text_hay))

            if req_country == "United States" and is_us_only:
                return True
            if req_country == "United Kingdom" and is_uk_only:
                return True
            if req_country in ("Germany", "France", "Spain", "Italy", "Netherlands", "Poland") and is_eu_only:
                return True
            if req_country == "Canada" and is_can_only:
                return True
            if req_country == "India" and is_ind_only:
                return True

            # If it has regional restrictions for another country, reject
            if is_us_only or is_uk_only or is_can_only or is_ind_only:
                return False

            # If job is pinned to a different specific country, reject
            if job_country != "Worldwide" and req_country != "Worldwide" and job_country != req_country:
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
    dominant (78%). Poor fits (< 45%) are never artificially inflated.
    """
    fit = job.get("score", 0)
    source_rank = max([job.get("source_rank", 0)] + [s.get("source_rank", 0) for s in job.get("sources", [])])
    direct = 10 if job.get("source_kind") == "Direct employer ATS" else 0
    corroboration = min(10, max(0, len(job.get("sources", [])) - 1) * 4)
    description = min(10, round(len(job.get("description", "") or "") / 700 * 10))
    freshness = job.get("score_breakdown", {}).get("freshness", 0) * 2
    evidence = min(30, direct + corroboration + description + freshness)

    if fit < 45:
        opportunity = fit
    else:
        opportunity = int(round(fit * 0.78 + source_rank * 0.14 + (evidence / 30) * 8))

    if job.get("is_dream_company"):
        opportunity = min(100, opportunity + 8)

    kind = job.get("source_kind") or "Job source"
    is_free = job.get("is_free_to_apply") is not False
    job["opportunity_score"] = max(0, min(100, opportunity))
    job["ranking"] = {
        "source_authority": source_rank, "source_kind": kind,
        "evidence_points": evidence,
        "is_free_to_apply": is_free,
        "reason": f"{kind}; {len(job.get('sources', []))} source(s); {'100% Free apply' if is_free else 'Paid/gated board'}; {'direct employer application link' if direct else 'board/feed application link'}{'; Wishlist dream company' if job.get('is_dream_company') else ''}"
    }


# ---------------------------------------------------------------- famous companies & big tech

FAMOUS_COMPANY_TOKENS = {
    # Frontier AI & Prominent AI Labs
    "openai", "anthropic", "grok", "xai", "perplexity", "cohere",
    "mistral", "midjourney", "cursor", "poolside",
    # Big Tech / FAANG / MAMAA
    "meta", "facebook", "google", "alphabet", "apple", "microsoft",
    "amazon", "netflix",
    # Famous Unicorns & Public Tech Giants
    "vercel", "stripe", "gitlab", "github", "figma", "docker", "supabase",
    "uber", "airbnb", "coinbase", "shopify", "spotify", "databricks",
    "snowflake", "cloudflare", "palantir", "nvidia", "bytedance", "tiktok",
    "salesforce", "atlassian", "adobe", "twitter", "tesla", "spacex", "neuralink"
}

FAMOUS_COMPANY_PHRASES = (
    "open ai", "meta platforms", "x.ai", "scale ai", "hugging face",
    "amazon web services", "deepmind"
)


def is_famous_company(company_name):
    """Return True if company is a well-known Big Tech firm or prominent AI lab."""
    if not company_name:
        return False
    name = str(company_name).lower().strip()
    if any(phrase in name for phrase in FAMOUS_COMPANY_PHRASES):
        return True
    cleaned = re.sub(r"\b(inc|llc|corp|ltd|co|corporation|technologies|systems|labs|group)\b\.?", "", name)
    tokens = set(re.findall(r"[a-z0-9]+", cleaned))
    return bool(tokens & FAMOUS_COMPANY_TOKENS)


# ---------------------------------------------------------------- main entry

def derive_query(profile):
    return (profile.get("target_title") or "").strip()


def search(query="", location="", work_mode="Any", min_score=0, famous_mode="all", profile=None, force_refresh=False, limit=None, on_progress=None):
    t0 = time.time()
    profile = profile if profile is not None else db.get_profile()
    is_profile_search = not (query and query.strip()) or query.strip().lower() == (profile.get("target_title") or "").strip().lower()
    query = (query or "").strip() or derive_query(profile)
    location = (location or "").strip()
    statuses, raw = [], []

    from .scoring import derive_target_roles
    extra_terms = [r for r in derive_target_roles(profile) if r.lower() != query.lower()] if is_profile_search else []

    tasks = {}
    for s in src.SEARCH_SOURCES:
        if not s.available():
            statuses.append({"source": s.name, "state": "disabled", "count": 0, "error": s.unavailable_reason(), "ms": 0, "stale": False})
            continue
        queries_for_s = [query]
        if is_profile_search and extra_terms and s.name in ("Indeed", "LinkedIn"):
            queries_for_s.append(extra_terms[0])
        for q_term in queries_for_s:
            key = f"{s.name}|{q_term.lower()}|{location.lower()}"
            lbl = f"{s.name}:{q_term}" if len(queries_for_s) > 1 else s.name
            tasks[_pool.submit(_run_source, lbl, lambda s=s, q_term=q_term: s.fetch(q_term, location), key, force_refresh)] = lbl

    fam_mode = (famous_mode or "all").lower().strip()
    with db.session() as c:
        watch = [dict(r) for r in c.execute("SELECT * FROM watchlist")]
    for w in watch:
        board = src.BOARDS.get((w["board_type"] or "").lower())
        if not board:
            continue
        c_famous = is_famous_company(w.get("company_name") or w.get("slug"))
        if fam_mode == "hide" and c_famous:
            continue
        if fam_mode == "only" and not c_famous:
            continue
        label = f"{board.name}:{w['slug']}"
        key = f"board|{board.name}|{w['slug']}"
        tasks[_pool.submit(_run_source, label, lambda b=board, w=w: b.fetch_company(w["slug"], w["company_name"]), key, force_refresh)] = label

    source_labels = [tasks[f] for f in tasks]
    if on_progress:
        on_progress("init", {
            "sources": source_labels,
            "total": len(tasks),
            "query": query,
            "location": location
        })

    done_labels = set()
    deadline = time.time() + config.SEARCH_DEADLINE_SECONDS
    try:
        for f in cf.as_completed(list(tasks), timeout=config.SEARCH_DEADLINE_SECONDS):
            label = tasks[f]
            done_labels.add(label)
            try:
                jobs, st = f.result()
                raw.extend(jobs)
                statuses.append(st)
                if on_progress:
                    on_progress("source_done", {
                        "source": st["source"],
                        "state": st["state"],
                        "count": st["count"],
                        "ms": st["ms"],
                        "raw_total": len(raw),
                        "completed": len(done_labels),
                        "total": len(tasks)
                    })
            except Exception as e:
                st = {"source": label, "state": "failed", "count": 0, "error": str(e)[:160], "ms": 0, "stale": False}
                statuses.append(st)
                if on_progress:
                    on_progress("source_done", {
                        "source": label,
                        "state": "failed",
                        "count": 0,
                        "error": str(e)[:160],
                        "ms": 0,
                        "raw_total": len(raw),
                        "completed": len(done_labels),
                        "total": len(tasks)
                    })
    except cf.TimeoutError:
        for f, label in tasks.items():
            if label not in done_labels:
                f.cancel()
                st = {"source": label, "state": "timeout", "count": 0, "ms": int(config.SEARCH_DEADLINE_SECONDS * 1000),
                      "error": "Did not answer before search deadline.", "stale": False}
                statuses.append(st)
                if on_progress:
                    on_progress("source_done", {
                        "source": label,
                        "state": "timeout",
                        "count": 0,
                        "error": "Timeout",
                        "ms": int(config.SEARCH_DEADLINE_SECONDS * 1000),
                        "raw_total": len(raw),
                        "completed": len(statuses),
                        "total": len(tasks)
                    })

    if config.DEMO:
        from .demo import SAMPLE_JOBS
        raw.extend(SAMPLE_JOBS)

    famous_mode = (famous_mode or "all").lower().strip()
    for j in raw:
        j["is_famous"] = is_famous_company(j.get("company"))
    if famous_mode == "hide":
        raw = [j for j in raw if not j.get("is_famous")]
    elif famous_mode == "only":
        raw = [j for j in raw if j.get("is_famous")]

    if query:
        qwords = [w for w in re.findall(r"[a-z0-9+#]+", query.lower()) if len(w) > 2]
        syns = set(qwords)
        if "engineer" in syns or "developer" in syns or "swe" in syns:
            syns.update({"engineer", "developer", "swe", "dev", "programmer", "software", "architect"})
        if "frontend" in syns or "front-end" in syns:
            syns.update({"frontend", "front end", "ui", "web", "react", "vue", "javascript", "typescript"})
        if "backend" in syns or "back-end" in syns:
            syns.update({"backend", "back end", "api", "server", "python", "node", "java", "golang"})
        if "fullstack" in syns or "full-stack" in syns:
            syns.update({"fullstack", "full stack", "backend", "frontend", "software", "web"})
        if "devops" in syns or "cloud" in syns or "sre" in syns:
            syns.update({"devops", "cloud", "sre", "infrastructure", "platform", "kubernetes", "aws", "docker"})
        if "data" in syns or "ai" in syns or "ml" in syns:
            syns.update({"data", "analytics", "machine learning", "ai", "ml"})
        if "mobile" in syns or "ios" in syns or "android" in syns:
            syns.update({"mobile", "ios", "android", "flutter", "react native"})
        for sk_name in profile.get("skills", [])[:8]:
            for tok in re.findall(r"[a-z0-9+#]+", sk_name.lower()):
                if len(tok) > 2:
                    syns.add(tok)
        def relevant(j):
            if not j["source_tier"].startswith("Direct"):
                return True
            hay = f"{j['title']} {j.get('description', '')[:600]}".lower()
            return any(w in hay for w in syns) if syns else True
        raw = [j for j in raw if relevant(j)]

    if on_progress:
        on_progress("stage", {
            "stage": "dedup",
            "message": f"Deduplicating {len(raw)} raw postings across all boards...",
            "raw_count": len(raw)
        })

    merged = dedup.merge_jobs(raw)
    for j in merged:
        j["is_famous"] = is_famous_company(j.get("company"))

    # Score all candidate opportunities for this query/location so DB and client have the full pool
    if len(merged) > 350:
        if query:
            merged.sort(key=lambda j: (any(w in (j.get("title") or "").lower() for w in syns), j.get("source_rank", 0)), reverse=True)
        merged = merged[:350]

    total_unique = len(merged)
    has_enrichable = any(j.get("needs_enrichment") for j in merged[:config.ENRICH_TOP_N])
    est_total_s = max(0.8, round(total_unique * 0.003 + (1.6 if has_enrichable else 0.3), 1))

    if on_progress:
        on_progress("stage", {
            "stage": "score",
            "message": f"Calculating resume fit scores for {total_unique} matching opportunities (~{est_total_s}s remaining)...",
            "unique_count": total_unique,
            "est_seconds": est_total_s
        })

    t_score_start = time.time()
    for idx, j in enumerate(merged, start=1):
        j.update(score_job(j, profile))
        _rank_opportunity(j)
        if on_progress and (idx % 25 == 0 or idx == total_unique):
            is_final = (idx == total_unique)
            elapsed = time.time() - t_score_start
            rate = idx / elapsed if elapsed > 0 else 400
            rem_scoring = (total_unique - idx) / rate if (rate > 0 and not is_final) else 0
            rem_total = 0.0 if is_final else max(0.2, round(rem_scoring + (1.2 if has_enrichable else 0.1), 1))
            on_progress("stage", {
                "stage": "score_progress",
                "current": idx,
                "total": total_unique,
                "est_seconds": rem_total,
                "pct": 100 if is_final else (int(round((idx / total_unique) * 100)) if total_unique else 100),
                "message": f"Scoring complete for all {total_unique} roles" if is_final else f"Scoring match fit: {idx} of {total_unique} roles (~{rem_total}s remaining)..."
            })

    merged.sort(key=lambda j: (j["opportunity_score"], j["score"], j.get("posted_at") or ""), reverse=True)
    to_enrich = [j for j in merged[:config.ENRICH_TOP_N] if j.get("needs_enrichment")]
    if to_enrich:
        if on_progress:
            on_progress("stage", {
                "stage": "enrich",
                "message": f"Verifying direct employer links for top {len(to_enrich)} roles (~1s remaining)...",
                "enrich_count": len(to_enrich),
                "est_seconds": 1.0
            })
        futs = {_pool.submit(src.enrich_job, j): j for j in to_enrich}
        d2, _ = cf.wait(list(futs), timeout=4.0)
        for f in d2:
            try:
                res_job = f.result()
                futs[f].update(res_job)
                futs[f].update(score_job(futs[f], profile))
                _rank_opportunity(futs[f])
            except Exception:
                pass
        merged.sort(key=lambda j: (j["opportunity_score"], j["score"], j.get("posted_at") or ""), reverse=True)

    # Persist all fresh scored jobs into SQLite DB (clears old ones and stores new ones)
    db.replace_search_jobs(merged, query=query, location=location, sources=statuses)

    # Filter according to requested params for immediate response
    bad_keys = [k.lower().strip() for k in profile.get("excluded_keywords", []) if k and k.strip()]
    filtered = []
    for j in merged:
        if famous_mode == "hide" and j.get("is_famous"):
            continue
        if famous_mode == "only" and not j.get("is_famous"):
            continue
        if not _passes(j, work_mode, location):
            continue
        if min_score and j["score"] < int(min_score):
            continue
        if bad_keys:
            j_text = f"{j.get('title', '')} {j.get('description', '')}".lower()
            if any(k in j_text for k in bad_keys):
                continue
        filtered.append(j)

    # Smart Graceful Fallback: if location yielded 0 results, find Worldwide Remote opportunities
    fallback_notice = ""
    if not filtered and location and location.lower() not in ("remote", "worldwide", "any"):
        from .scoring import classify_job_country
        req_country = classify_job_country(location)
        fallback_candidates = []
        for j in merged:
            if famous_mode == "hide" and j.get("is_famous"):
                continue
            if famous_mode == "only" and not j.get("is_famous"):
                continue
            if bad_keys:
                j_text = f"{j.get('title', '')} {j.get('description', '')}".lower()
                if any(k in j_text for k in bad_keys):
                    continue
            jm = _norm_mode(j)
            if jm == "remote":
                loc_low = (j.get("location") or "").lower()
                text_hay = f"{loc_low} {j.get('description', '')[:500]}".lower()
                is_us_only = bool(re.search(r"\b(us only|u\.s\. only|united states only|must reside in (the )?us)\b", text_hay))
                is_uk_only = bool(re.search(r"\b(uk only|united kingdom only|must reside in (the )?uk)\b", text_hay))
                is_can_only = bool(re.search(r"\b(canada only|must reside in canada)\b", text_hay))
                is_ind_only = bool(re.search(r"\b(india only|must reside in india)\b", text_hay))
                if (req_country != "United States" and is_us_only) or \
                   (req_country != "United Kingdom" and is_uk_only) or \
                   (req_country != "Canada" and is_can_only) or \
                   (req_country != "India" and is_ind_only):
                    continue
                j_copy = dict(j)
                j_copy["is_fallback"] = True
                fallback_candidates.append(j_copy)
        if fallback_candidates:
            filtered = fallback_candidates
            fallback_notice = f"No on-site postings found in '{location}'. Showing {len(filtered)} Worldwide Remote opportunities you can work from {location}."

    filtered = filtered[: (limit or config.MAX_RESULTS)]
    _remember(filtered)

    failed = [s for s in statuses if s["state"] in ("failed", "timeout", "paused", "stale")]
    result = {
        "count": len(filtered), "query": query, "famous_mode": famous_mode, "jobs": filtered,
        "all_jobs": merged, "total_stored": len(merged), "sources": sorted(statuses, key=lambda s: s["source"]),
        "ranking": {"method": "fit 70% + source authority 20% + evidence 10%", "workers": config.SEARCH_WORKERS},
        "partial": bool(failed), "elapsed_ms": int((time.time() - t0) * 1000),
        "profile_empty": bool(profile.get("_is_empty")),
        "fallback_notice": fallback_notice,
        "warnings": ([f"{len(failed)} source(s) did not respond. Showing results from the rest."] if failed else []),
    }
    if on_progress:
        on_progress("complete", result)
    return result
