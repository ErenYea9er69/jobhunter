"""Runtime configuration. Every value reads from an environment variable with a safe default."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.environ.get("VERCEL"):
    DATA_DIR = os.environ.get("JH_DATA_DIR", "/tmp/jobhunter_data")
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
    DATA_DIR = os.environ.get("JH_DATA_DIR", os.path.join(BASE_DIR, "data"))

DB_PATH = os.path.join(DATA_DIR, "jobhunter.db")

HOST = os.environ.get("JH_HOST", "127.0.0.1")
PORT = int(os.environ.get("JH_PORT", "8080"))

# Search behavior
SEARCH_WORKERS = 16
SEARCH_DEADLINE_SECONDS = float(os.environ.get("JH_SEARCH_DEADLINE", "20"))
SOURCE_TIMEOUT_SECONDS = float(os.environ.get("JH_SOURCE_TIMEOUT", "10"))
CACHE_TTL_SECONDS = int(os.environ.get("JH_CACHE_TTL", "900"))
STALE_CACHE_MAX_SECONDS = int(os.environ.get("JH_STALE_MAX", str(24 * 3600)))
MAX_RESULTS = int(os.environ.get("JH_MAX_RESULTS", "150"))
ENRICH_TOP_N = int(os.environ.get("JH_ENRICH_TOP_N", "12"))

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
