"""Runtime configuration. Every value reads from an environment variable with a safe default.

JobHunter runs as an MCP server. Its data lives in ``<workspace>/.jobhunter/``.
Call ``configure_mcp_environment`` once at startup to point the paths at a workspace.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_DIR = os.environ.get("JH_WORKSPACE", "")
if WORKSPACE_DIR:
    WORKSPACE_DIR = os.path.abspath(WORKSPACE_DIR)

def _get_default_data_dir() -> str:
    from . import home
    return str(home.get_home() / "data")

DEFAULT_DATA_DIR = _get_default_data_dir()
JOBHUNTER_DIR = os.path.join(WORKSPACE_DIR, ".jobhunter") if WORKSPACE_DIR else ""
DATA_DIR = os.environ.get("JH_DATA_DIR") or DEFAULT_DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "engine.db")

def _ensure_data_dir() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        # Migrate legacy data/engine.db only when initializing the user's default home directory
        if DATA_DIR == DEFAULT_DATA_DIR:
            legacy_db = os.path.join(BASE_DIR, "data", "engine.db")
            if os.path.exists(legacy_db) and not os.path.exists(DB_PATH):
                import shutil
                shutil.copy2(legacy_db, DB_PATH)
    except Exception:
        pass

if os.environ.get("JH_DATA_DIR"):
    _ensure_data_dir()

# Search behavior
SEARCH_WORKERS = 16
SEARCH_DEADLINE_SECONDS = float(os.environ.get("JH_SEARCH_DEADLINE", "35"))
SOURCE_TIMEOUT_SECONDS = float(os.environ.get("JH_SOURCE_TIMEOUT", "10"))
CACHE_TTL_SECONDS = int(os.environ.get("JH_CACHE_TTL", "900"))
STALE_CACHE_MAX_SECONDS = int(os.environ.get("JH_STALE_MAX", str(24 * 3600)))
MAX_RESULTS = int(os.environ.get("JH_MAX_RESULTS", "1000"))
MAX_SCORED_JOBS = int(os.environ.get("JH_MAX_SCORED_JOBS", "2500"))
ENRICH_TOP_N = int(os.environ.get("JH_ENRICH_TOP_N", "40"))

# Company career boards (watchlist, starter directory, boards discovered from other sources)
COMPANY_BOARD_WORKERS = int(os.environ.get("JH_COMPANY_WORKERS", "8"))
COMPANY_BOARDS_PER_SEARCH = int(os.environ.get("JH_COMPANY_BOARDS_PER_SEARCH", "60"))
COMPANY_BOARD_BUDGET_SECONDS = float(os.environ.get("JH_COMPANY_BUDGET", "25"))
COMPANY_BOARD_TIMEOUT_SECONDS = float(os.environ.get("JH_COMPANY_TIMEOUT", "6"))
DISCOVERED_BOARDS_MAX = int(os.environ.get("JH_DISCOVERED_BOARDS_MAX", "400"))

# The background enricher reads full job pages. Cap how many it reads per cycle so a
# long-lived MCP process stays polite to job sites.
ENRICH_BG_MAX_PER_CYCLE = int(os.environ.get("JH_ENRICH_BG_MAX", "60"))

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

def get_linkedin_incremental_minutes():
    """Interval in minutes for the lightweight LinkedIn-only background scraper. 0 = disabled."""
    try:
        from . import db
        val = db.get_setting("linkedin_incremental_minutes")
        if val:
            return max(0, min(60, int(val)))
    except Exception:
        pass
    return int(os.environ.get("JH_LINKEDIN_INCREMENTAL_MIN", "10"))

# Major job boards (LinkedIn, Indeed, ZipRecruiter, etc.) are built-in native scrapers
# that run as part of every search without external library wrappers.
ADZUNA_COUNTRY = os.environ.get("JH_ADZUNA_COUNTRY", "us")
ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")
JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY", "")

# Optional LLM for tailoring, cover letters, and strategy. Without a key the app uses the deterministic engine.
# Keys come from environment variables only. The MCP tools never accept or return secrets.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
CUSTOM_AI_KEY = os.environ.get("JH_CUSTOM_AI_KEY", "")
CUSTOM_AI_ENDPOINT = os.environ.get("JH_CUSTOM_AI_ENDPOINT") or os.environ.get("JH_LLM_BASE_URL", "")
AI_PROVIDER = os.environ.get("JH_AI_PROVIDER", "auto")  # "auto", "gemini", "openai", "anthropic", "deepseek", "groq", "mistral", "ollama", "custom", "deterministic"
LLM_MODEL = os.environ.get("JH_LLM_MODEL", "")
LLM_TIMEOUT_SECONDS = float(os.environ.get("JH_LLM_TIMEOUT", "40"))
OLLAMA_ENDPOINT = os.environ.get("JH_OLLAMA_ENDPOINT", "http://127.0.0.1:11434")

USER_AGENT = "JobHunter/2.1 (+local personal job search tool)"


def configure_mcp_environment(workspace_path: str = ""):
    """Point all paths at a workspace directory. Returns the ``.jobhunter`` directory."""
    global WORKSPACE_DIR, JOBHUNTER_DIR, DATA_DIR, DB_PATH
    ws = os.path.abspath(workspace_path) if workspace_path else (WORKSPACE_DIR or os.path.abspath(os.getcwd()))
    WORKSPACE_DIR = ws
    os.environ["JH_WORKSPACE"] = ws
    JOBHUNTER_DIR = os.path.join(ws, ".jobhunter")
    DATA_DIR = os.environ.get("JH_DATA_DIR") or DEFAULT_DATA_DIR
    DB_PATH = os.path.join(DATA_DIR, "engine.db")
    _ensure_data_dir()
    return JOBHUNTER_DIR


def get_method() -> str:
    """Return active search & application method: 'modern' (default) or 'classic'."""
    try:
        from . import db
        val = db.get_setting("method")
        if val and val.lower().strip() in ("modern", "classic"):
            return val.lower().strip()
    except Exception:
        pass
    return os.environ.get("JH_METHOD", "modern").lower().strip()


def set_method(method: str) -> str:
    """Set active search & application method: 'modern' or 'classic'."""
    clean = (method or "modern").lower().strip()
    if clean not in ("modern", "classic"):
        clean = "modern"
    try:
        from . import db
        db.set_setting("method", clean)
    except Exception:
        pass
    os.environ["JH_METHOD"] = clean
    return clean


def get_daily_cap() -> int:
    try:
        from . import db
        val = db.get_setting("daily_cap")
        if val:
            return max(1, min(200, int(val)))
    except Exception:
        pass
    return int(os.environ.get("JH_DAILY_CAP", "20"))


def get_follow_up_days() -> int:
    try:
        from . import db
        val = db.get_setting("follow_up_days")
        if val:
            return max(1, min(30, int(val)))
    except Exception:
        pass
    return int(os.environ.get("JH_FOLLOW_UP_DAYS", "4"))


def get_first_touch_attachment() -> bool:
    try:
        from . import db
        val = db.get_setting("first_touch_attachment")
        if val is not None:
            return str(val).lower() in ("1", "true", "yes", "on")
    except Exception:
        pass
    return True


def get_send_mode() -> str:
    try:
        from . import db
        val = db.get_setting("send_mode")
        if val:
            return val.lower().strip()
    except Exception:
        pass
    return os.environ.get("JH_SEND_MODE", "one_at_a_time")


def get_resume_max_kb() -> int:
    try:
        from . import db
        val = db.get_setting("resume_max_kb")
        if val:
            return max(50, min(1000, int(val)))
    except Exception:
        pass
    return int(os.environ.get("JH_RESUME_MAX_KB", "200"))

