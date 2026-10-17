"""SQLite access with WAL, versioned migrations, job classification, and background search staging."""
import contextlib
import datetime
import json
import re
import sqlite3
import threading

from . import config
from .util import now_iso, parse_salary, annualize, days_since

_init_lock = threading.Lock()
SCHEMA_VERSION = 3

EMPTY_PROFILE = {
    "name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": "",
    "target_title": "", "target_roles": [], "years_of_experience": 0, "work_mode": "Any",
    "preferred_locations": [], "min_salary": 0, "excluded_keywords": [],
    "preferred_job_types": [], "dream_companies": [], "dream_role": "",
    "summary": "", "skills": [], "skills_by_category": {}, "experience": [], "education": [],
    "_is_empty": True,
}

US_STATES_SET = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia",
    "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt",
    "va", "wa", "wv", "wi", "wy", "dc", "california", "new york", "texas", "washington",
    "florida", "illinois", "massachusetts", "colorado", "georgia", "virginia"
}

FAMOUS_COMPANY_TOKENS = {
    "openai", "anthropic", "grok", "xai", "perplexity", "cohere",
    "mistral", "midjourney", "cursor", "poolside",
    "meta", "facebook", "google", "alphabet", "apple", "microsoft",
    "amazon", "netflix", "vercel", "stripe", "gitlab", "github", "figma",
    "docker", "supabase", "uber", "airbnb", "coinbase", "shopify", "spotify",
    "databricks", "snowflake", "cloudflare", "palantir", "nvidia", "bytedance",
    "tiktok", "salesforce", "atlassian", "adobe", "twitter", "tesla", "spacex"
}


def is_famous_company(name):
    if not name:
        return False
    clean = re.sub(r"\b(inc|llc|corp|ltd|co|corporation|technologies|systems|labs|group)\b\.?", "", str(name).lower())
    tokens = re.findall(r"[a-z0-9]+", clean)
    return any(t in FAMOUS_COMPANY_TOKENS for t in tokens)


def classify_job(j):
    """Extract category, job_type, seniority, country, salary, and flags from job dict."""
    title = (j.get("title") or "").strip()
    t_lower = title.lower()
    desc_sample = ((j.get("description") or "")[:800]).lower()
    loc = (j.get("location") or "").strip()
    loc_lower = loc.lower()
    comp = (j.get("company") or "").strip()
    tags = [str(t).lower() for t in (j.get("tags") or [])]
    haystack = f"{t_lower} {loc_lower} {desc_sample} {' '.join(tags)}"

    # 1. Job Function / Category
    cat = "Software Engineer"
    if any(k in t_lower for k in ["full stack", "fullstack", "mern", "lamp"]):
        cat = "Full Stack Developer"
    elif any(k in t_lower for k in ["back end", "backend", "api engineer", "server", "golang", "python", "node"]):
        cat = "Backend Engineer"
    elif any(k in t_lower for k in ["front end", "frontend", "ui engineer", "react", "vue", "web developer"]):
        cat = "Frontend Engineer"
    elif any(k in t_lower for k in ["devops", "sre", "site reliability", "cloud engineer", "platform engineer", "infrastructure"]):
        cat = "DevOps Engineer"
    elif any(k in t_lower for k in ["data engineer", "big data", "etl", "analytics engineer"]):
        cat = "Data Engineer"
    elif any(k in t_lower for k in ["machine learning", "ml engineer", "ai engineer", "data scientist", "deep learning", "nlp"]):
        cat = "Machine Learning Engineer"
    elif any(k in t_lower for k in ["mobile", "ios", "android", "flutter", "react native"]):
        cat = "Mobile Developer"
    elif any(k in t_lower for k in ["qa", "quality assurance", "test engineer", "sdet", "automation engineer"]):
        cat = "QA Engineer"
    elif any(k in t_lower for k in ["security", "cyber", "infosec", "appsec"]):
        cat = "Security Engineer"
    elif any(k in t_lower for k in ["product manager", "product owner", "technical product"]):
        cat = "Product Manager"
    elif any(k in t_lower for k in ["ui/ux", "designer", "ux design", "product design"]):
        cat = "UI/UX Designer"
    elif any(k in t_lower for k in ["data analyst", "business analyst", "bi analyst"]):
        cat = "Data Analyst"

    # 2. Seniority
    sen = "mid"
    if any(k in t_lower for k in ["intern", "internship", "co-op"]):
        sen = "intern"
    elif any(k in t_lower for k in ["junior", "jr", "entry", "associate", "new grad"]):
        sen = "junior"
    elif any(k in t_lower for k in ["director", "vp", "head of", "chief", "executive"]):
        sen = "director"
    elif any(k in t_lower for k in ["lead", "staff", "principal", "architect"]):
        sen = "lead_staff"
    elif any(k in t_lower for k in ["senior", "sr."]) or re.search(r"\bsr\b", t_lower):
        sen = "senior"

    # 3. Work mode
    wm = (j.get("work_mode") or "").strip()
    if not wm or wm.lower() == "any":
        if any(k in haystack for k in ["remote", "anywhere", "work from home", "virtual"]):
            wm = "Remote"
        elif any(k in haystack for k in ["hybrid"]):
            wm = "Hybrid"
        else:
            wm = "Onsite"

    # 4. Job type
    jt = (j.get("job_type") or "").strip()
    if not jt or jt.lower() == "any":
        if sen == "intern" or "intern" in t_lower:
            jt = "Internship"
        elif any(k in haystack for k in ["contract", "contractor", "freelance", "c2c"]):
            jt = "Contract"
        elif any(k in haystack for k in ["part-time", "part time"]):
            jt = "Part-time"
        else:
            jt = "Full-time"

    # 5. Country
    country = "United States"
    if any(k in loc_lower for k in ["worldwide", "global", "anywhere", "remote"]):
        country = "Worldwide"
    elif any(k in loc_lower for k in ["united kingdom", "london", "england", "uk", "manchester"]):
        country = "United Kingdom"
    elif any(k in loc_lower for k in ["germany", "berlin", "munich", "deutschland"]):
        country = "Germany"
    elif any(k in loc_lower for k in ["canada", "toronto", "vancouver", "montreal", "ontario"]):
        country = "Canada"
    else:
        # Check US states or cities
        loc_tokens = [tok.strip() for tok in re.split(r"[,/ -]+", loc_lower) if tok.strip()]
        if any(tok in US_STATES_SET for tok in loc_tokens) or any(c in loc_lower for c in ["san francisco", "new york", "seattle", "austin", "chicago", "boston", "los angeles"]):
            country = "United States"
        elif wm == "Remote":
            country = "Worldwide"

    # 6. Salary parsing
    sal_info = parse_salary(j.get("salary"))
    ann = annualize(sal_info) if sal_info else None
    min_sal = float(ann[0]) if ann else 0.0
    max_sal = float(ann[1]) if ann else 0.0

    # 7. Industry
    ind = "Tech & Software"
    if any(k in haystack for k in ["fintech", "finance", "bank", "crypto", "trading", "capital", "payments", "insurance"]):
        ind = "Finance & Fintech"
    elif any(k in haystack for k in ["health", "healthcare", "medical", "pharma", "biotech", "clinical"]):
        ind = "Healthcare & Bio"
    elif any(k in haystack for k in ["consulting", "advisory", "agency", "staffing", "services"]):
        ind = "Consulting & Services"

    # 8. Startups & Famous
    is_fam = 1 if is_famous_company(comp) or j.get("is_famous") else 0
    is_start = 1 if not is_fam and any(k in haystack for k in ["series a", "series b", "seed", "startup", "yc", "y combinator"]) else 0

    # 9. H1B Sponsorship
    h1b = 1 if re.search(r"\bh1-?b\b|visa sponsorship|sponsor(?:ship)? available", haystack) else 0

    # 10. Skills text
    if j.get("skills_text"):
        skills_text = str(j.get("skills_text"))
    else:
        skills_list = j.get("skills") or j.get("matched_skills") or []
        if isinstance(skills_list, list):
            skills_text = ", ".join(str(s) for s in skills_list)
        else:
            skills_text = str(skills_list)

    return {
        "category": cat,
        "job_type": jt,
        "seniority": sen,
        "work_mode": wm,
        "country": country,
        "min_salary": min_sal,
        "max_salary": max_sal,
        "industry": ind,
        "skills_text": skills_text,
        "is_famous": is_fam,
        "is_startup": is_start,
        "h1b": h1b
    }


def connect():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


@contextlib.contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db():
    import os
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with _init_lock, session() as c:
        c.execute("CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL)")
        c.execute("""CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY, job_id TEXT, company TEXT NOT NULL, title TEXT NOT NULL, location TEXT,
            salary TEXT, status TEXT NOT NULL, notes TEXT, follow_up_date TEXT, sources_json TEXT,
            job_data_json TEXT, tailored_resume_json TEXT, cover_letter TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS watchlist (
            id TEXT PRIMARY KEY, company_name TEXT NOT NULL, slug TEXT NOT NULL, board_type TEXT NOT NULL,
            target_role TEXT, added_at TEXT NOT NULL, last_checked TEXT, active_matches_count INTEGER DEFAULT 0)""")
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        c.execute("""CREATE TABLE IF NOT EXISTS status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT NOT NULL, status TEXT NOT NULL, changed_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS seen_jobs (
            job_key TEXT PRIMARY KEY, title TEXT, company TEXT, url TEXT, source_names TEXT,
            first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, best_score INTEGER DEFAULT 0, digested INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS source_cache (
            cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at REAL NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS source_health (
            source TEXT PRIMARY KEY, ok_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
            last_error TEXT, last_ok TEXT, last_ms INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS search_jobs (
            job_key TEXT PRIMARY KEY, query TEXT NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL,
            location TEXT, work_mode TEXT, score INTEGER DEFAULT 0, opportunity_score INTEGER DEFAULT 0,
            is_famous INTEGER DEFAULT 0, source_kind TEXT, source_names TEXT, posted_at TEXT,
            job_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS search_meta (
            id INTEGER PRIMARY KEY, query TEXT, location TEXT, total_count INTEGER DEFAULT 0,
            sources_json TEXT, updated_at TEXT NOT NULL)""")

        # Table for background auto-search discoveries (pending new jobs waiting for user refresh)
        c.execute("""CREATE TABLE IF NOT EXISTS pending_search_jobs (
            job_key TEXT PRIMARY KEY, query TEXT NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL,
            location TEXT, work_mode TEXT, category TEXT, job_type TEXT, seniority TEXT, country TEXT,
            min_salary REAL DEFAULT 0, max_salary REAL DEFAULT 0, score INTEGER DEFAULT 0,
            opportunity_score INTEGER DEFAULT 0, is_famous INTEGER DEFAULT 0, is_startup INTEGER DEFAULT 0,
            industry TEXT, h1b INTEGER DEFAULT 0, source_kind TEXT, source_names TEXT, posted_at TEXT,
            job_json TEXT NOT NULL, discovered_at TEXT NOT NULL)""")

        # Add structured category columns to search_jobs if missing
        s_cols = _columns(c, "search_jobs")
        for col, col_type in [
            ("category", "TEXT DEFAULT ''"),
            ("job_type", "TEXT DEFAULT ''"),
            ("seniority", "TEXT DEFAULT ''"),
            ("country", "TEXT DEFAULT ''"),
            ("min_salary", "REAL DEFAULT 0"),
            ("max_salary", "REAL DEFAULT 0"),
            ("industry", "TEXT DEFAULT ''"),
            ("skills_text", "TEXT DEFAULT ''"),
            ("is_startup", "INTEGER DEFAULT 0"),
            ("h1b", "INTEGER DEFAULT 0"),
            ("is_active", "INTEGER DEFAULT 1"),
        ]:
            if col not in s_cols:
                c.execute(f"ALTER TABLE search_jobs ADD COLUMN {col} {col_type}")

        # Add skills_text to pending_search_jobs if missing
        p_cols = _columns(c, "pending_search_jobs")
        if "skills_text" not in p_cols:
            c.execute("ALTER TABLE pending_search_jobs ADD COLUMN skills_text TEXT DEFAULT ''")

        c.execute("CREATE INDEX IF NOT EXISTS idx_hist_app ON status_history(app_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_query ON search_jobs(query)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_opp ON search_jobs(opportunity_score)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_cat ON search_jobs(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_wm ON search_jobs(work_mode)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_sen ON search_jobs(seniority)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_jt ON search_jobs(job_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_country ON search_jobs(country)")

        c.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

        # Backfill history for v1 rows
        c.execute("""INSERT INTO status_history (app_id, status, changed_at)
                     SELECT id, status, created_at FROM applications
                     WHERE id NOT IN (SELECT app_id FROM status_history)""")

        # Backfill any search_jobs rows that don't have categories yet
        unclassified = c.execute("SELECT job_key, job_json FROM search_jobs WHERE category IS NULL OR category = ''").fetchall()
        for r in unclassified:
            try:
                j_obj = json.loads(r["job_json"])
                meta = classify_job(j_obj)
                c.execute("""
                    UPDATE search_jobs
                    SET category=?, job_type=?, seniority=?, country=?, min_salary=?, max_salary=?,
                        industry=?, skills_text=?, is_startup=?, h1b=?, work_mode=?
                    WHERE job_key=?
                """, (
                    meta["category"], meta["job_type"], meta["seniority"], meta["country"],
                    meta["min_salary"], meta["max_salary"], meta["industry"], meta["skills_text"],
                    meta["is_startup"], meta["h1b"], meta["work_mode"], r["job_key"]
                ))
            except Exception:
                pass

        if config.DEMO and not c.execute("SELECT 1 FROM profile WHERE id=1").fetchone():
            from .demo import DEMO_PROFILE
            c.execute("INSERT INTO profile (id,data,updated_at) VALUES (1,?,?)", (json.dumps(DEMO_PROFILE), now_iso()))


def get_profile():
    with session() as c:
        row = c.execute("SELECT data FROM profile WHERE id=1").fetchone()
    if not row:
        return json.loads(json.dumps(EMPTY_PROFILE))
    data = json.loads(row["data"])
    for k, v in EMPTY_PROFILE.items():
        data.setdefault(k, json.loads(json.dumps(v)) if k != "_is_empty" else False)
    if not data.get("target_roles") and (data.get("target_title") or data.get("skills")):
        from .scoring import derive_target_roles
        data["target_roles"] = derive_target_roles(data)
    return data


def save_profile(data):
    data = dict(data)
    data.pop("_is_empty", None)
    data.pop("_updated_at", None)
    with session() as c:
        c.execute("INSERT OR REPLACE INTO profile (id,data,updated_at) VALUES (1,?,?)", (json.dumps(data), now_iso()))


def rescore_and_classify_stored_jobs(profile=None):
    """Re-score and re-classify all stored jobs against updated profile/resume."""
    from .scoring import score_job
    from .pipeline import _rank_opportunity
    if profile is None:
        profile = get_profile()
    if not profile or profile.get("_is_empty"):
        return 0
    updated_count = 0
    with session() as c:
        rows = c.execute("SELECT job_key, job_json FROM search_jobs").fetchall()
        for r in rows:
            try:
                j = json.loads(r["job_json"])
                c_meta = classify_job(j)
                scored = score_job(j, profile)
                j.update(scored)
                j["category"] = c_meta["category"]
                j["seniority"] = c_meta["seniority"]
                j["job_type"] = c_meta["job_type"]
                j["country"] = c_meta["country"]
                j["work_mode"] = c_meta["work_mode"]
                _rank_opportunity(j)
                c.execute("""
                    UPDATE search_jobs
                    SET score=?, opportunity_score=?, category=?, job_type=?, seniority=?,
                        country=?, work_mode=?, job_json=?
                    WHERE job_key=?
                """, (
                    j.get("score", 0), j.get("opportunity_score", 0),
                    c_meta["category"], c_meta["job_type"], c_meta["seniority"],
                    c_meta["country"], c_meta["work_mode"], json.dumps(j),
                    r["job_key"]
                ))
                updated_count += 1
            except Exception:
                pass
    return updated_count


def get_setting(key, default=""):
    with session() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with session() as c:
        c.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, str(value)))


def replace_search_jobs(jobs, query="", location="", sources=None, clear_existing=True):
    """Store search jobs with extracted categories into DB.
    If clear_existing is True, deletes old search jobs first (explicit query replacement).
    Otherwise, upserts jobs into the existing database cache so prior discoveries are preserved.
    """
    now = now_iso()
    with session() as c:
        if clear_existing:
            c.execute("DELETE FROM search_jobs")
        for j in jobs:
            key = j.get("job_key") or j.get("id")
            if not key:
                continue
            c_meta = classify_job(j)
            j["category"] = c_meta["category"]
            j["seniority"] = c_meta["seniority"]
            j["job_type"] = c_meta["job_type"]
            j["country"] = c_meta["country"]
            j["work_mode"] = c_meta["work_mode"]

            c.execute("""
                INSERT OR REPLACE INTO search_jobs
                (job_key, query, title, company, location, work_mode, score, opportunity_score,
                 is_famous, source_kind, source_names, posted_at, job_json, created_at, updated_at,
                 category, job_type, seniority, country, min_salary, max_salary, industry,
                 skills_text, is_startup, h1b, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                key, query or j.get("query", ""), j.get("title", ""), j.get("company", ""),
                j.get("location", ""), c_meta["work_mode"], j.get("score", 0),
                j.get("opportunity_score", 0), c_meta["is_famous"],
                j.get("source_kind", ""), ",".join(j.get("source_names", [])),
                j.get("posted_at", ""), json.dumps(j), now, now,
                c_meta["category"], c_meta["job_type"], c_meta["seniority"], c_meta["country"],
                c_meta["min_salary"], c_meta["max_salary"], c_meta["industry"],
                c_meta["skills_text"], c_meta["is_startup"], c_meta["h1b"]
            ))
        total_now = c.execute("SELECT count(*) FROM search_jobs WHERE is_active=1").fetchone()[0]
        c.execute("""INSERT OR REPLACE INTO search_meta
                     (id, query, location, total_count, sources_json, updated_at)
                     VALUES (1, ?, ?, ?, ?, ?)""",
                  (query, location, total_now, json.dumps(sources or []), now))


def upsert_search_jobs(jobs, query="", location="", sources=None):
    """Upsert search jobs into search_jobs cache without clearing existing jobs."""
    return replace_search_jobs(jobs, query=query, location=location, sources=sources, clear_existing=False)


def update_search_job(job):
    """Update a single job in search_jobs cache if it exists."""
    from . import dedup
    key = job.get("job_key") or dedup.job_key(job) or job.get("id")
    if not key:
        return False
    now = now_iso()
    c_meta = classify_job(job)
    with session() as c:
        row = c.execute("SELECT job_key FROM search_jobs WHERE job_key=?", (key,)).fetchone()
        if row:
            c.execute("""
                UPDATE search_jobs
                SET title=?, company=?, location=?, work_mode=?, score=?, opportunity_score=?,
                    job_json=?, updated_at=?, category=?, job_type=?, seniority=?, country=?
                WHERE job_key=?
            """, (
                job.get("title", ""), job.get("company", ""), job.get("location", ""),
                c_meta["work_mode"], job.get("score", 0), job.get("opportunity_score", 0),
                json.dumps(job), now, c_meta["category"], c_meta["job_type"], c_meta["seniority"], c_meta["country"],
                key
            ))
            return True
    return False


def query_stored_jobs(filters=None):
    """Fast SQLite-level filtering across all stored jobs based on user criteria.
    Never launches a new external scraping search session.
    """
    filters = filters or {}
    clauses = ["is_active = 1"]
    params = []

    # 1. Job Function / Category
    cat = (filters.get("category") or filters.get("role") or "").strip()
    if cat and cat.lower() not in ("all", "any"):
        c_low = cat.lower()
        if "full stack" in c_low or "fullstack" in c_low:
            clauses.append("(category LIKE '%Full Stack%' OR title LIKE '%Full Stack%' OR title LIKE '%Fullstack%' OR title LIKE '%Full-Stack%' OR skills_text LIKE '%fullstack%' OR skills_text LIKE '%full stack%')")
        elif "backend" in c_low or "back end" in c_low:
            clauses.append("(category LIKE '%Backend%' OR title LIKE '%Backend%' OR title LIKE '%Back end%' OR title LIKE '%Back-End%')")
        elif "frontend" in c_low or "front end" in c_low:
            clauses.append("(category LIKE '%Frontend%' OR title LIKE '%Frontend%' OR title LIKE '%Front end%' OR title LIKE '%Front-End%')")
        elif any(k in c_low for k in ["devops", "sre", "cloud", "infrastructure"]):
            clauses.append("(category LIKE '%DevOps%' OR title LIKE '%DevOps%' OR title LIKE '%SRE%' OR title LIKE '%Site Reliability%' OR title LIKE '%Platform%' OR title LIKE '%Infrastructure%')")
        elif any(k in c_low for k in ["machine learning", "ml", "ai"]):
            clauses.append("(category LIKE '%Machine Learning%' OR title LIKE '%Machine Learning%' OR title LIKE '%ML%' OR title LIKE '%AI %' OR title LIKE '%AI-%' OR title LIKE '%Data Scientist%')")
        elif "data" in c_low and ("engineer" in c_low or "analytics" in c_low):
            clauses.append("(category LIKE '%Data%' OR title LIKE '%Data Engineer%' OR title LIKE '%Analytics Engineer%')")
        elif any(k in c_low for k in ["mobile", "ios", "android"]):
            clauses.append("(category LIKE '%Mobile%' OR title LIKE '%Mobile%' OR title LIKE '%iOS%' OR title LIKE '%Android%')")
        elif any(k in c_low for k in ["security", "cyber"]):
            clauses.append("(category LIKE '%Security%' OR title LIKE '%Security%' OR title LIKE '%Cyber%')")
        elif any(k in c_low for k in ["qa", "quality", "test"]):
            clauses.append("(category LIKE '%QA%' OR title LIKE '%QA%' OR title LIKE '%Test%' OR title LIKE '%Quality%')")
        elif "product" in c_low:
            clauses.append("(category LIKE '%Product%' OR title LIKE '%Product%')")
        elif any(k in c_low for k in ["design", "ux", "ui"]):
            clauses.append("(category LIKE '%Design%' OR title LIKE '%Design%' OR title LIKE '%UX%' OR title LIKE '%UI%')")
        elif "software" in c_low or "engineer" in c_low or "developer" in c_low:
            clauses.append("(category LIKE '%Engineer%' OR category LIKE '%Developer%' OR title LIKE '%Engineer%' OR title LIKE '%Developer%')")
        else:
            clauses.append("(category LIKE ? OR title LIKE ?)")
            params.extend([f"%{cat}%", f"%{cat}%"])

    # 2. Work Mode
    wm = (filters.get("work_mode") or "").strip()
    if wm and wm.lower() not in ("any", "all"):
        wm_low = wm.lower()
        if "remote" in wm_low:
            clauses.append("(LOWER(work_mode) LIKE '%remote%' OR LOWER(location) LIKE '%remote%' OR LOWER(country) = 'worldwide')")
        elif "hybrid" in wm_low:
            clauses.append("(LOWER(work_mode) LIKE '%hybrid%' OR LOWER(location) LIKE '%hybrid%')")
        elif any(k in wm_low for k in ["onsite", "on-site", "office"]):
            clauses.append("(LOWER(work_mode) LIKE '%onsite%' OR LOWER(work_mode) LIKE '%on-site%' OR (LOWER(work_mode) NOT LIKE '%remote%' AND LOWER(work_mode) NOT LIKE '%hybrid%'))")
        else:
            clauses.append("LOWER(work_mode) = ?")
            params.append(wm_low)

    # 3. Seniority
    sen = (filters.get("seniority") or "").strip()
    if sen and sen.lower() not in ("all", "any"):
        s_low = sen.lower()
        if s_low in ("junior", "entry", "intern", "entry_junior"):
            clauses.append("(seniority IN ('junior', 'intern') OR LOWER(title) LIKE '%junior%' OR LOWER(title) LIKE '%entry%' OR LOWER(title) LIKE '%intern%' OR LOWER(title) LIKE '%new grad%' OR LOWER(title) LIKE '%associate%')")
        elif s_low == "mid":
            clauses.append("(seniority = 'mid' OR (seniority NOT IN ('intern', 'junior', 'director') AND LOWER(title) NOT LIKE '%director%' AND LOWER(title) NOT LIKE '%vp%'))")
        elif s_low == "senior":
            clauses.append("(seniority IN ('senior', 'lead_staff') OR LOWER(title) LIKE '%senior%' OR LOWER(title) LIKE '%sr%' OR LOWER(title) LIKE '%lead%' OR LOWER(title) LIKE '%staff%')")
        elif s_low in ("lead_staff", "lead", "staff", "director"):
            clauses.append("(seniority IN ('lead_staff', 'director') OR LOWER(title) LIKE '%lead%' OR LOWER(title) LIKE '%staff%' OR LOWER(title) LIKE '%principal%' OR LOWER(title) LIKE '%director%' OR LOWER(title) LIKE '%head of%')")
        else:
            clauses.append("seniority = ?")
            params.append(s_low)

    # 4. Job Type
    jt = (filters.get("job_type") or "").strip()
    if jt and jt.lower() not in ("all", "any"):
        clauses.append("LOWER(job_type) LIKE ?")
        params.append(f"%{jt.lower()}%")

    # 5. Country / Location
    country = (filters.get("country") or "").strip()
    if country and country.lower() not in ("all", "any"):
        c_low = country.lower()
        inc_remote = str(get_setting("include_worldwide_remote", "true")).lower() in ("true", "1", "yes")
        if c_low in ("united states", "usa", "us"):
            clauses.append("(LOWER(country) = 'united states' OR LOWER(country) = 'worldwide' OR LOWER(work_mode) LIKE '%remote%')")
        elif c_low == "worldwide":
            clauses.append("(LOWER(country) = 'worldwide' OR LOWER(work_mode) LIKE '%remote%')")
        elif inc_remote:
            clauses.append("(LOWER(country) = ? OR LOWER(location) LIKE ? OR (LOWER(work_mode) LIKE '%remote%' AND LOWER(country) = 'worldwide'))")
            params.extend([c_low, f"%{c_low}%"])
        else:
            clauses.append("(LOWER(country) = ? OR LOWER(location) LIKE ?)")
            params.extend([c_low, f"%{c_low}%"])

    loc_q = (filters.get("location") or "").strip()
    if loc_q and loc_q.lower() not in ("all", "any", "anywhere in the us"):
        clauses.append("(LOWER(location) LIKE ? OR work_mode = 'Remote')")
        params.append(f"%{loc_q.lower()}%")

    # 6. Minimum Salary
    try:
        min_sal = float(filters.get("min_salary") or 0)
        if min_sal > 0:
            clauses.append("(max_salary >= ? OR (min_salary >= ? AND min_salary > 0))")
            params.extend([min_sal, min_sal])
    except (ValueError, TypeError):
        pass

    # 7. Minimum Score
    try:
        min_score = int(filters.get("min_score") or 0)
        if min_score > 0:
            clauses.append("score >= ?")
            params.append(min_score)
    except (ValueError, TypeError):
        pass

    # 8. Company Mode (Famous vs Startups)
    fam_mode = (filters.get("famous_mode") or "all").lower()
    if fam_mode == "hide":
        clauses.append("is_famous = 0")
    elif fam_mode == "only":
        clauses.append("is_famous = 1")
    elif fam_mode == "startups":
        clauses.append("is_startup = 1")

    # 9. Industry
    ind = (filters.get("industry") or "").strip()
    if ind and ind.lower() not in ("all", "any"):
        if ind.lower() in ("tech", "software"):
            clauses.append("industry LIKE '%Tech%'")
        elif ind.lower() in ("finance", "fintech"):
            clauses.append("industry LIKE '%Finance%'")
        elif ind.lower() in ("health", "healthcare", "bio"):
            clauses.append("industry LIKE '%Health%'")
        elif ind.lower() in ("consulting", "services"):
            clauses.append("industry LIKE '%Consulting%'")

    # 10. Date Freshness (days)
    try:
        days = int(filters.get("days") or filters.get("freshness_days") or 0)
        if days > 0:
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
            clauses.append("(posted_at >= ? OR posted_at IS NULL OR posted_at = '')")
            params.append(cutoff)
    except (ValueError, TypeError):
        pass

    # 11. Keyword
    kw = (filters.get("q") or filters.get("keyword") or "").strip()
    if kw:
        clauses.append("(title LIKE ? OR company LIKE ? OR skills_text LIKE ? OR location LIKE ?)")
        pat = f"%{kw}%"
        params.extend([pat, pat, pat, pat])

    # 12. H1B
    if str(filters.get("h1b") or "").lower() in ("1", "true"):
        clauses.append("h1b = 1")

    # Sorting
    sort = (filters.get("sort") or "ranked").lower()
    if sort == "score_desc":
        order_clause = "ORDER BY score DESC, opportunity_score DESC"
    elif sort == "salary_desc":
        order_clause = "ORDER BY max_salary DESC, score DESC"
    elif sort == "date_desc":
        order_clause = "ORDER BY posted_at DESC, opportunity_score DESC"
    elif sort == "company_asc":
        order_clause = "ORDER BY company ASC"
    else:
        order_clause = "ORDER BY opportunity_score DESC, score DESC"

    where_sql = " AND ".join(clauses) if clauses else "1=1"

    with session() as c:
        total_all = c.execute("SELECT count(*) FROM search_jobs WHERE is_active=1").fetchone()[0]
        rows = c.execute(f"SELECT job_json FROM search_jobs WHERE {where_sql} {order_clause}", params).fetchall()

        # Compute dynamic facet counts
        cat_rows = c.execute("SELECT category, count(*) as cnt FROM search_jobs WHERE is_active=1 GROUP BY category ORDER BY cnt DESC").fetchall()
        wm_rows = c.execute("SELECT work_mode, count(*) as cnt FROM search_jobs WHERE is_active=1 GROUP BY work_mode").fetchall()
        sen_rows = c.execute("SELECT seniority, count(*) as cnt FROM search_jobs WHERE is_active=1 GROUP BY seniority").fetchall()

    jobs = [json.loads(r["job_json"]) for r in rows]
    meta = get_search_meta() or {}

    return {
        "jobs": jobs,
        "all_jobs": jobs,
        "count": len(jobs),
        "total_all": total_all,
        "meta": meta,
        "facets": {
            "categories": {r["category"]: r["cnt"] for r in cat_rows if r["category"]},
            "work_modes": {r["work_mode"]: r["cnt"] for r in wm_rows if r["work_mode"]},
            "seniorities": {r["seniority"]: r["cnt"] for r in sen_rows if r["seniority"]}
        }
    }


def get_saved_search_jobs():
    """Retrieve all saved search jobs."""
    return query_stored_jobs()["jobs"]


def get_search_meta():
    """Retrieve metadata of the last search stored in DB."""
    with session() as c:
        row = c.execute("SELECT * FROM search_meta WHERE id=1").fetchone()
    if not row:
        return None
    return {
        "query": row["query"],
        "location": row["location"],
        "total_count": row["total_count"],
        "sources": json.loads(row["sources_json"] or "[]"),
        "updated_at": row["updated_at"]
    }


def get_pending_jobs_count():
    """Count newly discovered jobs found in background auto-search waiting for user refresh."""
    with session() as c:
        row = c.execute("SELECT count(*) FROM pending_search_jobs").fetchone()
    return row[0] if row else 0


def get_pending_jobs():
    """Get all staged pending jobs."""
    with session() as c:
        rows = c.execute("SELECT job_json FROM pending_search_jobs ORDER BY opportunity_score DESC, score DESC").fetchall()
    return [json.loads(r["job_json"]) for r in rows]


def store_pending_jobs(jobs, query=""):
    """Store newly discovered jobs from background search into pending_search_jobs staging table."""
    now = now_iso()
    added_count = 0
    with session() as c:
        for j in jobs:
            key = j.get("job_key") or j.get("id")
            if not key:
                continue
            # Ignore if already in active search_jobs
            if c.execute("SELECT 1 FROM search_jobs WHERE job_key=?", (key,)).fetchone():
                continue
            c_meta = classify_job(j)
            j["category"] = c_meta["category"]
            j["seniority"] = c_meta["seniority"]
            j["job_type"] = c_meta["job_type"]
            j["country"] = c_meta["country"]
            j["work_mode"] = c_meta["work_mode"]
            c.execute("""
                INSERT OR REPLACE INTO pending_search_jobs
                (job_key, query, title, company, location, work_mode, category, job_type, seniority, country,
                 min_salary, max_salary, score, opportunity_score, is_famous, is_startup, industry, h1b,
                 source_kind, source_names, posted_at, job_json, discovered_at, skills_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                key, query, j.get("title", ""), j.get("company", ""), j.get("location", ""),
                c_meta["work_mode"], c_meta["category"], c_meta["job_type"], c_meta["seniority"], c_meta["country"],
                c_meta["min_salary"], c_meta["max_salary"], j.get("score", 0), j.get("opportunity_score", 0),
                c_meta["is_famous"], c_meta["is_startup"], c_meta["industry"], c_meta["h1b"],
                j.get("source_kind", ""), ",".join(j.get("source_names", [])),
                j.get("posted_at", ""), json.dumps(j), now, c_meta.get("skills_text", "")
            ))
            added_count += 1
    return added_count


def apply_refresh_sync():
    """Triggered when the user presses Refresh:
    1. Moves staged new jobs from pending_search_jobs into search_jobs.
    2. Safely prunes truly stale jobs (e.g. jobs not updated in over 90 days).
    3. Clears pending_search_jobs table.
    4. Returns refresh statistics and updated database list.
    """
    now = now_iso()
    added_count = 0
    removed_count = 0

    with session() as c:
        pending_rows = c.execute("SELECT * FROM pending_search_jobs").fetchall()
        for r in pending_rows:
            skills_txt = r["skills_text"] if "skills_text" in r.keys() else ""
            c.execute("""
                INSERT OR REPLACE INTO search_jobs
                (job_key, query, title, company, location, work_mode, category, job_type, seniority, country,
                 min_salary, max_salary, score, opportunity_score, is_famous, is_startup, industry, h1b,
                 source_kind, source_names, posted_at, job_json, created_at, updated_at, is_active, skills_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                r["job_key"], r["query"], r["title"], r["company"], r["location"], r["work_mode"],
                r["category"], r["job_type"], r["seniority"], r["country"], r["min_salary"], r["max_salary"],
                r["score"], r["opportunity_score"], r["is_famous"], r["is_startup"], r["industry"], r["h1b"],
                r["source_kind"], r["source_names"], r["posted_at"], r["job_json"], now, now, skills_txt
            ))
            added_count += 1

        # Clear pending queue
        c.execute("DELETE FROM pending_search_jobs")

        # Safely prune dead / stale jobs without discarding active listings:
        # Never prune jobs that were just staged/added/updated today.
        # Only prune jobs whose last sync was > 90 days ago and posted > 90 days ago.
        cutoff_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)).isoformat()
        prune_cur = c.execute("""
            DELETE FROM search_jobs
            WHERE updated_at < ?
              AND posted_at != '' AND posted_at IS NOT NULL AND posted_at < ?
        """, (cutoff_date, cutoff_date))
        removed_count = prune_cur.rowcount if prune_cur else 0

        # Update meta count and timestamp
        total_now = c.execute("SELECT count(*) FROM search_jobs WHERE is_active=1").fetchone()[0]
        c.execute("UPDATE search_meta SET total_count=?, updated_at=? WHERE id=1", (total_now, now))

    return {
        "success": True,
        "added_count": added_count,
        "removed_count": removed_count,
        "total_jobs": total_now,
        "message": f"Refreshed: {added_count} new job{'s' if added_count != 1 else ''} added, {removed_count} expired job{'s' if removed_count != 1 else ''} removed."
    }


def get_auto_search_settings():
    """Retrieve background auto-search configuration."""
    with session() as c:
        row_enabled = c.execute("SELECT value FROM settings WHERE key='bg_search_enabled'").fetchone()
        row_interval = c.execute("SELECT value FROM settings WHERE key='bg_search_interval_hours'").fetchone()
        row_last = c.execute("SELECT value FROM settings WHERE key='bg_search_last_run'").fetchone()
        row_status = c.execute("SELECT value FROM settings WHERE key='bg_search_status'").fetchone()

    enabled = (row_enabled["value"] if row_enabled else "1") == "1"
    try:
        interval_hours = float(row_interval["value"] if row_interval else "5.0")
    except ValueError:
        interval_hours = 5.0
    last_run = row_last["value"] if row_last else None
    status = row_status["value"] if row_status else "idle"
    pending_count = get_pending_jobs_count()

    # Calculate next scheduled run
    next_run = None
    if enabled and interval_hours > 0:
        if last_run:
            try:
                last_dt = datetime.datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                next_dt = last_dt + datetime.timedelta(hours=interval_hours)
                next_run = next_dt.isoformat()
            except Exception:
                pass
        else:
            next_run = "Immediate"

    return {
        "enabled": enabled,
        "interval_hours": interval_hours,
        "last_run": last_run,
        "next_run": next_run,
        "status": status,
        "pending_count": pending_count
    }


def set_auto_search_settings(enabled=True, interval_hours=5.0):
    """Save background auto-search configuration."""
    with session() as c:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bg_search_enabled', ?)", ("1" if enabled else "0",))
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bg_search_interval_hours', ?)", (str(interval_hours),))
    return get_auto_search_settings()


def purge_all():
    """Delete every user table, then VACUUM so removed content leaves the file."""
    with session() as c:
        for t in ("profile", "applications", "watchlist", "settings", "status_history",
                  "seen_jobs", "source_cache", "source_health", "search_jobs", "search_meta", "pending_search_jobs"):
            c.execute(f"DELETE FROM {t}")
    conn = connect()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
    finally:
        conn.close()
