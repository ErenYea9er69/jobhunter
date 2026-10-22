"""SQLite access with WAL, versioned migrations, job classification, and background search staging."""
import contextlib
import datetime
import json
import re
import sqlite3
import threading
import uuid

from . import config
from .util import now_iso, parse_salary, annualize, days_since, clean_text, clean_job_type

_init_lock = threading.Lock()
SCHEMA_VERSION = 4

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


def clean_job_dict(j):
    """Sanitize all user-facing text fields in job dict."""
    if not isinstance(j, dict):
        return j
    for k in ("title", "company", "location", "work_mode", "salary", "job_type", "seniority"):
        if k in j and j[k] is not None:
            j[k] = clean_text(j[k])
    if "description" in j and j["description"] and "&" in str(j["description"]):
        j["description"] = clean_text(j["description"])
    return j


def classify_job(j):
    """Extract category, job_type, seniority, country, salary, and flags from job dict."""
    title = clean_text(j.get("title") or "")
    t_lower = title.lower()
    desc_sample = clean_text((j.get("description") or "")[:800]).lower()
    loc = clean_text(j.get("location") or "")
    loc_lower = loc.lower()
    comp = clean_text(j.get("company") or "")
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
    jt = clean_job_type(j.get("job_type") or "")
    if any(k in t_lower for k in ["intern", "internship", "co-op", "stagiaire", "praktikant", "werkstudent", "apprentice"]):
        jt = "Internship"
    elif any(k in t_lower for k in ["part-time", "part time"]):
        jt = "Part-time"
    elif any(k in t_lower for k in ["contract", "contractor", "freelance", "c2c"]):
        jt = "Contract"
    elif not jt or jt.lower() in ("any", "other", "unknown", "unknown."):
        if sen == "intern" or any(k in haystack for k in ["intern", "internship", "stage", "alternance", "apprentice", "praktikum", "werkstudent", "co-op"]):
            jt = "Internship"
        elif any(k in haystack for k in ["part-time", "part time", "flexible hours", "20 hours/week", "20 hrs/week"]):
            jt = "Part-time"
        elif any(k in haystack for k in ["contract", "contractor", "freelance", "c2c", "w2 contract", "subcontract"]):
            jt = "Contract"
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
    is_start = 1 if not is_fam and (bool(j.get("is_startup")) or any(k in haystack for k in ["series a", "series b", "seed", "startup", "yc", "y combinator"])) else 0

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
    conn = sqlite3.connect(config.DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
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
        c.execute("""CREATE TABLE IF NOT EXISTS resume_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            target_title TEXT DEFAULT '',
            target_roles_json TEXT DEFAULT '[]',
            tags_json TEXT DEFAULT '[]',
            data_json TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            is_master INTEGER DEFAULT 0,
            is_live INTEGER DEFAULT 1,
            source_job_id TEXT DEFAULT '',
            source_job_title TEXT DEFAULT '',
            source_company TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_resume_profiles_active ON resume_profiles(is_active)")
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
            job_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            best_profile_id TEXT DEFAULT '', best_profile_name TEXT DEFAULT '')""")
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
            job_json TEXT NOT NULL, discovered_at TEXT NOT NULL,
            best_profile_id TEXT DEFAULT '', best_profile_name TEXT DEFAULT '')""")

        # Migration: ensure is_live column exists on resume_profiles
        rp_cols = _columns(c, "resume_profiles")
        if "is_live" not in rp_cols:
            c.execute("ALTER TABLE resume_profiles ADD COLUMN is_live INTEGER DEFAULT 1")

        # Add structured category and profile tracking columns to search_jobs if missing
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
            ("best_profile_id", "TEXT DEFAULT ''"),
            ("best_profile_name", "TEXT DEFAULT ''"),
        ]:
            if col not in s_cols:
                c.execute(f"ALTER TABLE search_jobs ADD COLUMN {col} {col_type}")

        # Add missing columns to pending_search_jobs if missing
        p_cols = _columns(c, "pending_search_jobs")
        if "skills_text" not in p_cols:
            c.execute("ALTER TABLE pending_search_jobs ADD COLUMN skills_text TEXT DEFAULT ''")
        if "best_profile_id" not in p_cols:
            c.execute("ALTER TABLE pending_search_jobs ADD COLUMN best_profile_id TEXT DEFAULT ''")
        if "best_profile_name" not in p_cols:
            c.execute("ALTER TABLE pending_search_jobs ADD COLUMN best_profile_name TEXT DEFAULT ''")

        c.execute("CREATE INDEX IF NOT EXISTS idx_hist_app ON status_history(app_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_query ON search_jobs(query)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_opp ON search_jobs(opportunity_score)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_cat ON search_jobs(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_wm ON search_jobs(work_mode)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_sen ON search_jobs(seniority)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_jt ON search_jobs(job_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_country ON search_jobs(country)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_jobs_best_prof ON search_jobs(best_profile_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_resume_profiles_live ON resume_profiles(is_live)")

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

        # Clean any HTML entities from stored legacy jobs
        _cleanup_html_entities(c)

        # Backfill resume_profiles from existing legacy profile if empty
        has_rp = c.execute("SELECT count(*) as cnt FROM resume_profiles").fetchone()["cnt"]
        if has_rp == 0:
            legacy_p = c.execute("SELECT data, updated_at FROM profile WHERE id=1").fetchone()
            if legacy_p:
                try:
                    p_data = json.loads(legacy_p["data"])
                    target_title = p_data.get("target_title", "Master Profile")
                    roles = p_data.get("target_roles", [])
                    skills = p_data.get("skills", [])
                    tags = skills[:6] if skills else ["Core"]
                    c.execute("""
                        INSERT INTO resume_profiles
                        (id, name, target_title, target_roles_json, tags_json, data_json, is_active, is_master, is_live, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """, (
                        "master", "Master Resume", target_title, json.dumps(roles),
                        json.dumps(tags), legacy_p["data"], 1, 1,
                        legacy_p["updated_at"] or now_iso(), legacy_p["updated_at"] or now_iso()
                    ))
                except Exception:
                    pass


def _cleanup_html_entities(c):
    """Clean all HTML entities from existing stored database records."""
    # 1. Clean search_jobs
    rows = c.execute("SELECT job_key, title, company, location, job_json FROM search_jobs WHERE title LIKE '%&%' OR company LIKE '%&%' OR location LIKE '%&%' OR job_json LIKE '%&%'").fetchall()
    for r in rows:
        title = clean_text(r["title"])
        comp = clean_text(r["company"])
        loc = clean_text(r["location"])
        try:
            j = json.loads(r["job_json"])
            clean_job_dict(j)
            j_json = json.dumps(j)
        except Exception:
            j_json = r["job_json"]
        c.execute("""
            UPDATE search_jobs
            SET title=?, company=?, location=?, job_json=?
            WHERE job_key=?
        """, (title, comp, loc, j_json, r["job_key"]))

    # 2. Clean pending_search_jobs
    p_rows = c.execute("SELECT job_key, title, company, location, job_json FROM pending_search_jobs WHERE title LIKE '%&%' OR company LIKE '%&%' OR location LIKE '%&%' OR job_json LIKE '%&%'").fetchall()
    for r in p_rows:
        title = clean_text(r["title"])
        comp = clean_text(r["company"])
        loc = clean_text(r["location"])
        try:
            j = json.loads(r["job_json"])
            clean_job_dict(j)
            j_json = json.dumps(j)
        except Exception:
            j_json = r["job_json"]
        c.execute("""
            UPDATE pending_search_jobs
            SET title=?, company=?, location=?, job_json=?
            WHERE job_key=?
        """, (title, comp, loc, j_json, r["job_key"]))

    # 3. Clean seen_jobs
    seen_rows = c.execute("SELECT job_key, title, company FROM seen_jobs WHERE title LIKE '%&%' OR company LIKE '%&%'").fetchall()
    for r in seen_rows:
        title = clean_text(r["title"])
        comp = clean_text(r["company"])
        c.execute("UPDATE seen_jobs SET title=?, company=? WHERE job_key=?", (title, comp, r["job_key"]))

    # 4. Clean applications
    app_rows = c.execute("SELECT id, title, company, location, job_data_json FROM applications WHERE title LIKE '%&%' OR company LIKE '%&%' OR location LIKE '%&%' OR job_data_json LIKE '%&%'").fetchall()
    for r in app_rows:
        title = clean_text(r["title"])
        comp = clean_text(r["company"])
        loc = clean_text(r["location"])
        try:
            jd = json.loads(r["job_data_json"]) if r["job_data_json"] else {}
            clean_job_dict(jd)
            jd_json = json.dumps(jd)
        except Exception:
            jd_json = r["job_data_json"]
        c.execute("UPDATE applications SET title=?, company=?, location=?, job_data_json=? WHERE id=?", (title, comp, loc, jd_json, r["id"]))

    # 5. Clean watchlist
    w_rows = c.execute("SELECT id, company_name, target_role FROM watchlist WHERE company_name LIKE '%&%' OR target_role LIKE '%&%'").fetchall()
    for r in w_rows:
        comp = clean_text(r["company_name"])
        role = clean_text(r["target_role"])
        c.execute("UPDATE watchlist SET company_name=?, target_role=? WHERE id=?", (comp, role, r["id"]))

    # 6. Clear cached payloads containing html entities
    c.execute("DELETE FROM source_cache WHERE payload LIKE '%#x%' OR payload LIKE '%&#%'")


def get_profile(profile_id=None):
    with session() as c:
        row = None
        if profile_id:
            row = c.execute("SELECT id, name, data_json, is_active, is_master, is_live FROM resume_profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            row = c.execute("SELECT id, name, data_json, is_active, is_master, is_live FROM resume_profiles WHERE is_active=1 LIMIT 1").fetchone()
        if not row:
            row = c.execute("SELECT id, name, data_json, is_active, is_master, is_live FROM resume_profiles WHERE is_master=1 LIMIT 1").fetchone()
        if not row:
            row = c.execute("SELECT id, name, data_json, is_active, is_master, is_live FROM resume_profiles ORDER BY updated_at DESC LIMIT 1").fetchone()

        if not row:
            legacy = c.execute("SELECT data FROM profile WHERE id=1").fetchone()
            if not legacy:
                return json.loads(json.dumps(EMPTY_PROFILE))
            raw_data = legacy["data"]
        else:
            raw_data = row["data_json"]

    data = json.loads(raw_data)
    for k, v in EMPTY_PROFILE.items():
        data.setdefault(k, json.loads(json.dumps(v)) if k != "_is_empty" else False)
    if not data.get("target_roles") and (data.get("target_title") or data.get("skills")):
        from .scoring import derive_target_roles
        data["target_roles"] = derive_target_roles(data)
    if row:
        data["_profile_id"] = row["id"]
        data["_profile_name"] = row["name"]
        data["_is_master"] = bool(row["is_master"])
        data["_is_active"] = bool(row["is_active"])
        data["_is_live"] = bool(row["is_live"]) if "is_live" in row.keys() else True
    else:
        data["_profile_id"] = "master"
        data["_profile_name"] = "Master Resume"
        data["_is_master"] = True
        data["_is_active"] = True
        data["_is_live"] = True
    return data


def get_resume_profile(profile_id=None):
    return get_profile(profile_id=profile_id)


def get_live_profiles():
    """Retrieve full profile objects for all resumes currently in the active live matching pool."""
    with session() as c:
        rows = c.execute("""
            SELECT id, name, data_json, is_active, is_master, is_live
            FROM resume_profiles
            WHERE is_live=1
            ORDER BY is_master DESC, updated_at DESC
        """).fetchall()

    if not rows:
        return [get_profile()]

    profiles = []
    for r in rows:
        try:
            d = json.loads(r["data_json"])
            for k, v in EMPTY_PROFILE.items():
                d.setdefault(k, json.loads(json.dumps(v)) if k != "_is_empty" else False)
            if not d.get("target_roles") and (d.get("target_title") or d.get("skills")):
                from .scoring import derive_target_roles
                d["target_roles"] = derive_target_roles(d)
            d["_profile_id"] = r["id"]
            d["_profile_name"] = r["name"]
            d["_is_master"] = bool(r["is_master"])
            d["_is_active"] = bool(r["is_active"])
            d["_is_live"] = bool(r["is_live"]) if "is_live" in r.keys() else True
            profiles.append(d)
        except Exception:
            pass
    return profiles or [get_profile()]


def set_resume_profile_live(profile_id, is_live=None):
    """Toggle or set the live matching status for a resume profile.
    Guarantees that at least one resume remains Live in the pool at all times.
    """
    with session() as c:
        row = c.execute("SELECT id, name, is_live FROM resume_profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            raise ValueError(f"Resume profile '{profile_id}' not found.")

        current_live = bool(row["is_live"]) if "is_live" in row.keys() else True
        new_live = (not current_live) if is_live is None else bool(is_live)

        if not new_live:
            live_count = c.execute("SELECT count(*) as cnt FROM resume_profiles WHERE is_live=1").fetchone()["cnt"]
            if live_count <= 1 and current_live:
                raise ValueError("At least one resume must remain Live in the matching pool.")

        c.execute("UPDATE resume_profiles SET is_live=?, updated_at=? WHERE id=?", (1 if new_live else 0, now_iso(), profile_id))

    return {
        "id": row["id"],
        "name": row["name"],
        "is_live": new_live
    }


def save_profile(data, profile_id=None):
    data = dict(data)
    data.pop("_is_empty", None)
    data.pop("_updated_at", None)
    pid = profile_id or data.pop("_profile_id", None) or "master"
    pname = data.pop("_profile_name", None) or ("Master Resume" if pid == "master" else "Resume Variant")
    is_master = 1 if pid == "master" or data.pop("_is_master", False) else 0
    is_active = 1 if data.pop("_is_active", True) else 0
    is_live = 1 if data.pop("_is_live", True) else 0

    target_title = data.get("target_title", "")
    target_roles = data.get("target_roles", [])
    skills = data.get("skills", [])
    tags = data.get("tags") or (skills[:6] if skills else ["Core"])
    iso_now = now_iso()

    with session() as c:
        exists = c.execute("SELECT id FROM resume_profiles WHERE id=?", (pid,)).fetchone()
        if exists:
            c.execute("""
                UPDATE resume_profiles
                SET name=?, target_title=?, target_roles_json=?, tags_json=?, data_json=?, updated_at=?
                WHERE id=?
            """, (pname, target_title, json.dumps(target_roles), json.dumps(tags), json.dumps(data), iso_now, pid))
        else:
            c.execute("""
                INSERT INTO resume_profiles
                (id, name, target_title, target_roles_json, tags_json, data_json, is_active, is_master, is_live, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pid, pname, target_title, json.dumps(target_roles), json.dumps(tags), json.dumps(data), is_active, is_master, is_live, iso_now, iso_now))

        if is_active or is_master or pid == "master":
            c.execute("INSERT OR REPLACE INTO profile (id, data, updated_at) VALUES (1, ?, ?)", (json.dumps(data), iso_now))
    return get_profile(pid)


def list_resume_profiles():
    with session() as c:
        rows = c.execute("""
            SELECT id, name, target_title, target_roles_json, tags_json,
                   is_active, is_master, is_live, source_job_id, source_job_title, source_company,
                   created_at, updated_at, data_json
            FROM resume_profiles
            ORDER BY is_master DESC, updated_at DESC
        """).fetchall()

    res = []
    for r in rows:
        try:
            d = json.loads(r["data_json"])
            skills = d.get("skills", [])
            years = d.get("years_of_experience", 0)
            exp_count = len(d.get("experience", []))
            work_mode = d.get("work_mode", "Any")
            min_salary = d.get("min_salary", 0)
        except Exception:
            skills = []
            years = 0
            exp_count = 0
            work_mode = "Any"
            min_salary = 0

        res.append({
            "id": r["id"],
            "name": r["name"],
            "target_title": r["target_title"] or "General Candidate",
            "target_roles": json.loads(r["target_roles_json"] or "[]"),
            "tags": json.loads(r["tags_json"] or "[]"),
            "is_active": bool(r["is_active"]),
            "is_master": bool(r["is_master"]),
            "is_live": bool(r["is_live"]) if "is_live" in r.keys() else True,
            "source_job_id": r["source_job_id"],
            "source_job_title": r["source_job_title"],
            "source_company": r["source_company"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "skills_count": len(skills),
            "top_skills": skills[:6],
            "years_of_experience": years,
            "experience_count": exp_count,
            "work_mode": work_mode,
            "min_salary": min_salary
        })
    return res


def set_active_resume_profile(profile_id):
    with session() as c:
        row = c.execute("SELECT id, data_json FROM resume_profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            raise ValueError(f"Resume profile '{profile_id}' not found.")
        c.execute("UPDATE resume_profiles SET is_active = CASE WHEN id=? THEN 1 ELSE 0 END", (profile_id,))
        c.execute("INSERT OR REPLACE INTO profile (id, data, updated_at) VALUES (1, ?, ?)", (row["data_json"], now_iso()))
    active_profile = get_profile(profile_id)
    trigger_rescore_jobs(active_profile)
    return active_profile


def duplicate_resume_profile(profile_id, new_name=None, target_title=None, tags=None):
    base = get_profile(profile_id)
    if not base or base.get("_is_empty"):
        raise ValueError("Cannot duplicate an empty profile.")

    new_id = f"variant_{uuid.uuid4().hex[:8]}"
    name = new_name or f"{base.get('target_title') or base.get('_profile_name') or 'Resume'} (Variant)"
    data = dict(base)
    data.pop("_profile_id", None)
    data.pop("_is_master", None)
    data.pop("_is_active", None)
    data.pop("_is_live", None)
    data.pop("_profile_name", None)

    if target_title:
        data["target_title"] = target_title
        from .scoring import derive_target_roles
        data["target_roles"] = derive_target_roles(data)

    iso_now = now_iso()
    skills = data.get("skills", [])
    variant_tags = tags if tags is not None else (skills[:5] if skills else ["Variant"])

    with session() as c:
        c.execute("""
            INSERT INTO resume_profiles
            (id, name, target_title, target_roles_json, tags_json, data_json, is_active, is_master, is_live, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?, ?)
        """, (
            new_id, name, data.get("target_title", ""),
            json.dumps(data.get("target_roles", [])), json.dumps(variant_tags),
            json.dumps(data), iso_now, iso_now
        ))

    trigger_rescore_jobs()
    return get_profile(new_id)


def delete_resume_profile(profile_id):
    with session() as c:
        row = c.execute("SELECT is_master, is_active FROM resume_profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            return False
        if row["is_master"]:
            raise ValueError("The Master Resume cannot be deleted. You can edit it or create variants from it.")

        was_active = bool(row["is_active"])
        c.execute("DELETE FROM resume_profiles WHERE id=?", (profile_id,))
        # Ensure at least one profile remains live
        live_cnt = c.execute("SELECT count(*) as cnt FROM resume_profiles WHERE is_live=1").fetchone()["cnt"]
        if live_cnt == 0:
            c.execute("UPDATE resume_profiles SET is_live=1 WHERE is_master=1")
        if was_active:
            c.execute("UPDATE resume_profiles SET is_active=1 WHERE is_master=1")
            master_row = c.execute("SELECT data_json FROM resume_profiles WHERE is_master=1").fetchone()
            if master_row:
                c.execute("INSERT OR REPLACE INTO profile (id, data, updated_at) VALUES (1, ?, ?)", (master_row["data_json"], now_iso()))
    trigger_rescore_jobs()
    return True


def save_tailored_variant_from_workspace(job, tailored_resume, variant_name=None, tags=None):
    active = get_profile()
    new_id = f"tailored_{uuid.uuid4().hex[:8]}"

    comp = job.get("company") or "Target"
    role = job.get("title") or "Role"
    name = variant_name or f"Tailored: {comp} - {role}"

    new_data = dict(active)
    if tailored_resume.get("summary"):
        new_data["summary"] = tailored_resume["summary"]
    if tailored_resume.get("skills"):
        new_data["skills"] = tailored_resume["skills"]
    if tailored_resume.get("experience"):
        new_data["experience"] = tailored_resume["experience"]
    new_data["target_title"] = role
    from .scoring import derive_target_roles
    new_data["target_roles"] = derive_target_roles(new_data)

    iso_now = now_iso()
    extracted_tags = tags or (job.get("matched_skills", []) or new_data.get("skills", []))[:6]

    with session() as c:
        c.execute("""
            INSERT INTO resume_profiles
            (id, name, target_title, target_roles_json, tags_json, data_json, is_active, is_master, is_live,
             source_job_id, source_job_title, source_company, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?, ?, ?, ?, ?)
        """, (
            new_id, name, role, json.dumps(new_data.get("target_roles", [])),
            json.dumps(extracted_tags), json.dumps(new_data),
            job.get("id") or "", role, comp, iso_now, iso_now
        ))

    trigger_rescore_jobs()
    return get_profile(new_id)


_rescore_lock = threading.Lock()
_rescore_worker_running = False
_rescore_requested = False


def trigger_rescore_jobs(profile=None):
    """Trigger background job rescoring across all live profiles in a thread-safe, debounced queue."""
    global _rescore_requested, _rescore_worker_running
    with _rescore_lock:
        _rescore_requested = True
        if _rescore_worker_running:
            return
        _rescore_worker_running = True
    threading.Thread(target=_rescore_worker_loop, daemon=True, name="JobRescoreWorker").start()


def _rescore_worker_loop():
    global _rescore_requested, _rescore_worker_running
    while True:
        with _rescore_lock:
            if not _rescore_requested:
                _rescore_worker_running = False
                break
            _rescore_requested = False
        try:
            rescore_and_classify_stored_jobs()
        except Exception as e:
            import logging
            logging.getLogger("jobhunter").error("Error in rescore worker: %s", e)


def _flush_rescore_updates(batch):
    if not batch:
        return
    with session() as c:
        c.executemany("""
            UPDATE search_jobs
            SET score=?, opportunity_score=?, category=?, job_type=?, seniority=?,
                country=?, work_mode=?, best_profile_id=?, best_profile_name=?, job_json=?
            WHERE job_key=?
        """, batch)


def rescore_and_classify_stored_jobs(profile=None):
    """Re-score and re-classify all stored jobs against live resume profiles in responsive batches."""
    from .scoring import score_job_best
    from .pipeline import _rank_opportunity
    import time
    if profile is None:
        profiles = get_live_profiles()
    elif isinstance(profile, list):
        profiles = profile
    else:
        profiles = [profile]
    if not profiles or (len(profiles) == 1 and profiles[0].get("_is_empty")):
        return 0

    with session() as c:
        rows = c.execute("SELECT job_key, job_json, category, seniority, job_type, country, work_mode FROM search_jobs").fetchall()

    updates = []
    total_updated = 0
    for r in rows:
        try:
            j = json.loads(r["job_json"])
            cat = r["category"] or j.get("category")
            sen = r["seniority"] or j.get("seniority")
            jt = r["job_type"] or j.get("job_type")
            cny = r["country"] or j.get("country")
            wm = r["work_mode"] or j.get("work_mode")
            if not (cat and sen and jt and cny and wm):
                c_meta = classify_job(j)
                cat, sen, jt, cny, wm = c_meta["category"], c_meta["seniority"], c_meta["job_type"], c_meta["country"], c_meta["work_mode"]

            scored = score_job_best(j, profiles)
            j.update(scored)
            j["category"] = cat
            j["seniority"] = sen
            j["job_type"] = jt
            j["country"] = cny
            j["work_mode"] = wm
            _rank_opportunity(j)
            updates.append((
                j.get("score", 0), j.get("opportunity_score", 0),
                cat, jt, sen, cny, wm,
                j.get("best_profile_id", ""), j.get("best_profile_name", ""),
                json.dumps(j),
                r["job_key"]
            ))
        except Exception:
            pass

        # Flush in small 80-row transactions to keep SQLite completely unlocked and yield GIL
        if len(updates) >= 80:
            _flush_rescore_updates(updates)
            total_updated += len(updates)
            updates = []
            time.sleep(0.002)

    if updates:
        _flush_rescore_updates(updates)
        total_updated += len(updates)

    return total_updated


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
            clean_job_dict(j)
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
                 skills_text, is_startup, h1b, is_active, best_profile_id, best_profile_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                key, query or j.get("query", ""), clean_text(j.get("title", "")), clean_text(j.get("company", "")),
                clean_text(j.get("location", "")), c_meta["work_mode"], j.get("score", 0),
                j.get("opportunity_score", 0), c_meta["is_famous"],
                j.get("source_kind", ""), ",".join(j.get("source_names", [])),
                j.get("posted_at", ""), json.dumps(j), now, now,
                c_meta["category"], c_meta["job_type"], c_meta["seniority"], c_meta["country"],
                c_meta["min_salary"], c_meta["max_salary"], c_meta["industry"],
                c_meta["skills_text"], c_meta["is_startup"], c_meta["h1b"],
                j.get("best_profile_id", ""), j.get("best_profile_name", "")
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
    clean_job_dict(job)
    now = now_iso()
    c_meta = classify_job(job)
    with session() as c:
        row = c.execute("SELECT job_key FROM search_jobs WHERE job_key=?", (key,)).fetchone()
        if row:
            c.execute("""
                UPDATE search_jobs
                SET title=?, company=?, location=?, work_mode=?, score=?, opportunity_score=?,
                    job_json=?, updated_at=?, category=?, job_type=?, seniority=?, country=?,
                    best_profile_id=?, best_profile_name=?
                WHERE job_key=?
            """, (
                clean_text(job.get("title", "")), clean_text(job.get("company", "")), clean_text(job.get("location", "")),
                c_meta["work_mode"], job.get("score", 0), job.get("opportunity_score", 0),
                json.dumps(job), now, c_meta["category"], c_meta["job_type"], c_meta["seniority"], c_meta["country"],
                job.get("best_profile_id", ""), job.get("best_profile_name", ""),
                key
            ))
            return True
    return False


def query_stored_jobs(filters=None, include_all=False):
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
    wm_raw = (filters.get("work_mode") or "").strip()
    if wm_raw and wm_raw.lower() not in ("any", "all"):
        modes = [m.strip().lower() for m in wm_raw.split(",") if m.strip()]
        if modes and len(modes) < 3:
            wm_clauses = []
            for m_low in modes:
                if "remote" in m_low:
                    wm_clauses.append("(LOWER(work_mode) LIKE '%remote%' OR LOWER(location) LIKE '%remote%' OR LOWER(country) = 'worldwide')")
                elif "hybrid" in m_low:
                    wm_clauses.append("(LOWER(work_mode) LIKE '%hybrid%' OR LOWER(location) LIKE '%hybrid%')")
                elif any(k in m_low for k in ["onsite", "on-site", "office"]):
                    wm_clauses.append("(LOWER(work_mode) LIKE '%onsite%' OR LOWER(work_mode) LIKE '%on-site%' OR (LOWER(work_mode) NOT LIKE '%remote%' AND LOWER(work_mode) NOT LIKE '%hybrid%'))")
                else:
                    wm_clauses.append("LOWER(work_mode) = ?")
                    params.append(m_low)
            if wm_clauses:
                clauses.append(f"({' OR '.join(wm_clauses)})")

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

    # 4. Job Type (Supports single or multi-value comma-separated, e.g. 'Part-time,Internship')
    jt_raw = (filters.get("job_type") or "").strip()
    if jt_raw and jt_raw.lower() not in ("all", "any"):
        types = [t.strip().lower() for t in jt_raw.split(",") if t.strip()]
        if types and len(types) < 4:
            jt_clauses = []
            for t in types:
                if t == "internship":
                    jt_clauses.append("(LOWER(job_type) LIKE '%intern%' OR LOWER(title) LIKE '%intern%' OR LOWER(title) LIKE '%co-op%' OR LOWER(title) LIKE '%apprentice%')")
                elif t in ("part-time", "part time"):
                    jt_clauses.append("(LOWER(job_type) LIKE '%part%' OR LOWER(title) LIKE '%part-time%' OR LOWER(title) LIKE '%part time%')")
                elif t == "contract":
                    jt_clauses.append("(LOWER(job_type) LIKE '%contract%' OR LOWER(title) LIKE '%contract%' OR LOWER(title) LIKE '%freelance%')")
                elif t in ("full-time", "full time"):
                    jt_clauses.append("(LOWER(job_type) LIKE '%full%' OR (job_type = '' AND LOWER(title) NOT LIKE '%intern%' AND LOWER(title) NOT LIKE '%contract%' AND LOWER(title) NOT LIKE '%part%'))")
                else:
                    jt_clauses.append("LOWER(job_type) LIKE ?")
                    params.append(f"%{t}%")
            if jt_clauses:
                clauses.append(f"({' OR '.join(jt_clauses)})")

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

    # 13. Winning Resume Variant
    pid_filter = (filters.get("best_profile_id") or filters.get("profile_id") or "").strip()
    if pid_filter and pid_filter.lower() not in ("all", "any"):
        clauses.append("best_profile_id = ?")
        params.append(pid_filter)

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
        rows = c.execute(f"SELECT job_type, work_mode, category, seniority, country, best_profile_id, best_profile_name, job_json FROM search_jobs WHERE {where_sql} {order_clause}", params).fetchall()

        # Compute dynamic facet counts
        cat_rows = c.execute("SELECT category, count(*) as cnt FROM search_jobs WHERE is_active=1 GROUP BY category ORDER BY cnt DESC").fetchall()
        wm_rows = c.execute("SELECT work_mode, count(*) as cnt FROM search_jobs WHERE is_active=1 GROUP BY work_mode").fetchall()
        sen_rows = c.execute("SELECT seniority, count(*) as cnt FROM search_jobs WHERE is_active=1 GROUP BY seniority").fetchall()
        jt_rows = c.execute("SELECT job_type, count(*) as cnt FROM search_jobs WHERE is_active=1 AND job_type != '' GROUP BY job_type ORDER BY cnt DESC").fetchall()
        prof_rows = c.execute("SELECT best_profile_id, best_profile_name, count(*) as cnt FROM search_jobs WHERE is_active=1 AND best_profile_id != '' GROUP BY best_profile_id ORDER BY cnt DESC").fetchall()

        if include_all and len(clauses) > 1:
            all_rows = c.execute(f"SELECT job_type, work_mode, category, seniority, country, best_profile_id, best_profile_name, job_json FROM search_jobs WHERE is_active=1 {order_clause}").fetchall()
        else:
            all_rows = None

    def _unpack_row(r, compact=False):
        j = json.loads(r["job_json"])
        if compact:
            j["description"] = ""
            j["qualifications"] = []
            j["responsibilities"] = []
        if r["job_type"]:
            j["job_type"] = r["job_type"]
        if r["work_mode"]:
            j["work_mode"] = r["work_mode"]
        if r["category"]:
            j["category"] = r["category"]
        if r["seniority"]:
            j["seniority"] = r["seniority"]
        if r["country"]:
            j["country"] = r["country"]
        if r["best_profile_id"]:
            j["best_profile_id"] = r["best_profile_id"]
        if r["best_profile_name"]:
            j["best_profile_name"] = r["best_profile_name"]
        return j

    jobs = [_unpack_row(r) for r in rows]
    all_jobs = [_unpack_row(r, compact=True) for r in all_rows] if all_rows is not None else []
    meta = get_search_meta() or {}

    return {
        "jobs": jobs,
        "all_jobs": all_jobs,
        "count": len(jobs),
        "total_all": total_all,
        "meta": meta,
        "facets": {
            "categories": {r["category"]: r["cnt"] for r in cat_rows if r["category"]},
            "work_modes": {r["work_mode"]: r["cnt"] for r in wm_rows if r["work_mode"]},
            "seniorities": {r["seniority"]: r["cnt"] for r in sen_rows if r["seniority"]},
            "job_types": {r["job_type"]: r["cnt"] for r in jt_rows if r["job_type"]},
            "profiles": {r["best_profile_id"]: {"name": r["best_profile_name"], "count": r["cnt"]} for r in prof_rows}
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
    from . import dedup
    now = now_iso()
    added_count = 0
    with session() as c:
        for j in jobs:
            clean_job_dict(j)
            canon_key = dedup.job_key(j) if hasattr(dedup, "job_key") else ""
            key = j.get("job_key") or canon_key or j.get("id")
            if not key:
                continue
            j["job_key"] = key

            # Ignore if already in active search_jobs (by exact key, canonical key, or normalized company/title)
            if c.execute("SELECT 1 FROM search_jobs WHERE job_key=? OR job_key=?", (key, canon_key or key)).fetchone():
                continue
            if j.get("company") and j.get("title"):
                norm_co = dedup.normalize_company(j.get("company"))
                norm_ti = dedup._title_key(j.get("title"))
                if norm_co and norm_ti:
                    # Check exact company/title in search_jobs
                    if c.execute("SELECT 1 FROM search_jobs WHERE LOWER(company)=? AND LOWER(title)=?",
                                 (j.get("company", "").lower().strip(), j.get("title", "").lower().strip())).fetchone():
                        continue

            # Ignore if already staged in pending_search_jobs
            if c.execute("SELECT 1 FROM pending_search_jobs WHERE job_key=? OR job_key=?", (key, canon_key or key)).fetchone():
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
                 source_kind, source_names, posted_at, job_json, discovered_at, skills_text,
                 best_profile_id, best_profile_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                key, query, clean_text(j.get("title", "")), clean_text(j.get("company", "")), clean_text(j.get("location", "")),
                c_meta["work_mode"], c_meta["category"], c_meta["job_type"], c_meta["seniority"], c_meta["country"],
                c_meta["min_salary"], c_meta["max_salary"], j.get("score", 0), j.get("opportunity_score", 0),
                c_meta["is_famous"], c_meta["is_startup"], c_meta["industry"], c_meta["h1b"],
                j.get("source_kind", ""), ",".join(j.get("source_names", [])),
                j.get("posted_at", ""), json.dumps(j), now, c_meta.get("skills_text", ""),
                j.get("best_profile_id", ""), j.get("best_profile_name", "")
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
            best_pid = r["best_profile_id"] if "best_profile_id" in r.keys() else ""
            best_pname = r["best_profile_name"] if "best_profile_name" in r.keys() else ""
            c.execute("""
                INSERT OR REPLACE INTO search_jobs
                (job_key, query, title, company, location, work_mode, category, job_type, seniority, country,
                 min_salary, max_salary, score, opportunity_score, is_famous, is_startup, industry, h1b,
                 source_kind, source_names, posted_at, job_json, created_at, updated_at, is_active, skills_text,
                 best_profile_id, best_profile_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """, (
                r["job_key"], r["query"], r["title"], r["company"], r["location"], r["work_mode"],
                r["category"], r["job_type"], r["seniority"], r["country"], r["min_salary"], r["max_salary"],
                r["score"], r["opportunity_score"], r["is_famous"], r["is_startup"], r["industry"], r["h1b"],
                r["source_kind"], r["source_names"], r["posted_at"], r["job_json"], now, now, skills_txt,
                best_pid, best_pname
            ))
        added_keys = [r["job_key"] for r in pending_rows]
        added_count = len(added_keys)

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
        "added_job_keys": added_keys,
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
        for t in ("resume_profiles", "profile", "applications", "watchlist", "settings", "status_history",
                  "seen_jobs", "source_cache", "source_health", "search_jobs", "search_meta", "pending_search_jobs"):
            c.execute(f"DELETE FROM {t}")
    conn = connect()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
    finally:
        conn.close()
