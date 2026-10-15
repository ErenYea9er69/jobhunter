"""Runtime configuration. Every value reads from an environment variable with a safe default."""
import os
import sys

# Support PyInstaller frozen bundles
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if os.environ.get("JH_DATA_DIR"):
        DATA_DIR = os.environ["JH_DATA_DIR"]
    else:
        portable_dir = os.path.join(exe_dir, "data")
        try:
            os.makedirs(portable_dir, exist_ok=True)
            test_file = os.path.join(portable_dir, ".test_write")
            with open(test_file, "w") as f:
                f.write("1")
            os.remove(test_file)
            DATA_DIR = portable_dir
        except Exception:
            local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            DATA_DIR = os.path.join(local_appdata, "JobHunter", "data")
            os.makedirs(DATA_DIR, exist_ok=True)

    src_db = os.path.join(BASE_DIR, "data", "jobhunter.db")
    dst_db = os.path.join(DATA_DIR, "jobhunter.db")
    if os.path.isfile(src_db) and not os.path.isfile(dst_db):
        import shutil
        try:
            shutil.copy2(src_db, dst_db)
        except Exception:
            pass
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.environ.get("JH_DATA_DIR", os.path.join(BASE_DIR, "data"))

STATIC_DIR = os.path.join(BASE_DIR, "public")
DB_PATH = os.path.join(DATA_DIR, "jobhunter.db")

HOST = os.environ.get("JH_HOST", "127.0.0.1")
PORT = int(os.environ.get("JH_PORT", "8080"))

# Search behavior
SEARCH_WORKERS = 16
SEARCH_DEADLINE_SECONDS = float(os.environ.get("JH_SEARCH_DEADLINE", "20"))
SOURCE_TIMEOUT_SECONDS = float(os.environ.get("JH_SOURCE_TIMEOUT", "10"))
CACHE_TTL_SECONDS = int(os.environ.get("JH_CACHE_TTL", "900"))
STALE_CACHE_MAX_SECONDS = int(os.environ.get("JH_STALE_MAX", str(24 * 3600)))
MAX_RESULTS = int(os.environ.get("JH_MAX_RESULTS", "1000"))
MAX_SCORED_JOBS = int(os.environ.get("JH_MAX_SCORED_JOBS", "2500"))
ENRICH_TOP_N = int(os.environ.get("JH_ENRICH_TOP_N", "12"))

def get_max_scored_jobs():
    try:
        from . import db
        val = db.get_setting("max_scored_jobs")
        if val:
            return max(500, min(20000, int(val)))
    except Exception:
        pass
    return int(os.environ.get("JH_MAX_SCORED_JOBS", str(MAX_SCORED_JOBS)))

def get_max_results():
    try:
        from . import db
        val = db.get_setting("max_results")
        if val:
            return max(200, min(10000, int(val)))
    except Exception:
        pass
    return int(os.environ.get("JH_MAX_RESULTS", str(MAX_RESULTS)))

def get_linkedin_scrape_depth():
    try:
        from . import db
        val = db.get_setting("linkedin_scrape_depth")
        if val:
            return val.lower().strip()
    except Exception:
        pass
    return os.environ.get("JH_LINKEDIN_DEPTH", "standard")

# Major job boards (LinkedIn, Indeed, ZipRecruiter, etc.) are built-in native scrapers
# that run as part of every search without external library wrappers.
ENABLE_LINKEDIN = True
ENABLE_MAJOR_BOARDS = True
ADZUNA_COUNTRY = os.environ.get("JH_ADZUNA_COUNTRY", "us")
ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")

# Optional LLM for tailoring and strategy. Without a key the app uses the deterministic engine.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
AI_PROVIDER = os.environ.get("JH_AI_PROVIDER", "auto")  # "auto", "gemini", "openai", "anthropic", "ollama", "deterministic"
LLM_MODEL = os.environ.get("JH_LLM_MODEL", "")
LLM_TIMEOUT_SECONDS = float(os.environ.get("JH_LLM_TIMEOUT", "40"))
OLLAMA_ENDPOINT = os.environ.get("JH_OLLAMA_ENDPOINT", "http://127.0.0.1:11434")

# Demo mode seeds a sample profile and labeled sample jobs. Off by default.
DEMO = os.environ.get("JH_DEMO", "0") == "1"

# Digest scheduling and email
DIGEST_TIME = os.environ.get("JH_DIGEST_TIME", "")  # "08:00" enables the scheduler
SMTP_HOST = os.environ.get("JH_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("JH_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("JH_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("JH_SMTP_PASSWORD", "")

MAX_BODY_BYTES = 12 * 1024 * 1024
USER_AGENT = "JobHunter/2.0 (+local personal job search tool)"
