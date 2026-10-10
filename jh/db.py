"""SQLite access with WAL, versioned migrations, and a real data purge."""
import contextlib
import json
import sqlite3
import threading

from . import config
from .util import now_iso

_init_lock = threading.Lock()
SCHEMA_VERSION = 2

EMPTY_PROFILE = {
    "name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": "",
    "target_title": "", "target_roles": [], "years_of_experience": 0, "work_mode": "Any",
    "preferred_locations": [], "min_salary": 0, "excluded_keywords": [],
    "summary": "", "skills": [], "skills_by_category": {}, "experience": [], "education": [],
    "_is_empty": True,
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
        c.execute("CREATE INDEX IF NOT EXISTS idx_hist_app ON status_history(app_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status)")
        # v1 databases lack nothing structural here, so the version bump records the migration.
        c.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        # Backfill history for v1 rows so funnel stats work on old data.
        c.execute("""INSERT INTO status_history (app_id, status, changed_at)
                     SELECT id, status, created_at FROM applications
                     WHERE id NOT IN (SELECT app_id FROM status_history)""")
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


def get_setting(key, default=""):
    with session() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with session() as c:
        c.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, str(value)))


def purge_all():
    """Delete every user table, then VACUUM so removed content leaves the file."""
    with session() as c:
        for t in ("profile", "applications", "watchlist", "settings", "status_history",
                  "seen_jobs", "source_cache", "source_health"):
            c.execute(f"DELETE FROM {t}")
    conn = connect()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
    finally:
        conn.close()
