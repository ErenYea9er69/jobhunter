"""HTTP layer: a small router, same-origin protection, input limits, and JSON errors."""
import base64
import json
import logging
import mimetypes
import os
import re
import secrets
import time
import traceback
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import ats, config, db, digest, exporters, pipeline, resume_parser, refit, tracker, __version__

log = logging.getLogger("jobhunter")
TOKEN = secrets.token_urlsafe(24)
ROUTES = {}


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def route(method, path):
    def deco(fn):
        ROUTES[(method, path)] = fn
        return fn
    return deco


def _need_profile():
    p = db.get_profile()
    if p.get("_is_empty"):
        raise ApiError("No resume profile yet. Upload or paste your resume first.", 400)
    return p


def _job(body):
    j = body.get("job")
    if not isinstance(j, dict) or not (j.get("title") or j.get("description")):
        raise ApiError("A job object with a title or description is required.")
    return j


# ------------------------------------------------------------------ routes

@route("GET", "/api/profile")
def r_profile(q, body):
    p = db.get_profile()
    with db.session() as c:
        row = c.execute("SELECT updated_at FROM profile WHERE id=1").fetchone()
    p["_updated_at"] = row["updated_at"] if row else None
    return p


@route("POST", "/api/profile")
def r_save_profile(q, body):
    if not isinstance(body, dict) or not isinstance(body.get("skills", []), list):
        raise ApiError("Profile must be an object with a skills list.")
    db.save_profile(body)
    return {"success": True, "message": "Master profile saved."}


@route("POST", "/api/parse-resume")
def r_parse(q, body):
    try:
        text = resume_parser.decode_upload(body)
    except resume_parser.ParseError as e:
        raise ApiError(str(e))
    if len(text.strip()) < 30:
        raise ApiError("No readable text found. Paste the resume text instead.")
    profile, report = resume_parser.parse_resume(text)
    return {"success": True, "profile": profile, "parse_report": report}


@route("GET", "/api/search")
def r_search(q, body):
    g = lambda k, d="": q.get(k, [d])[0]
    try:
        min_score = int(g("min_score", "0") or 0)
    except ValueError:
        raise ApiError("min_score must be a number.")
    return pipeline.search(query=g("q"), location=g("location"), work_mode=g("work_mode", "Any"),
                           min_score=min_score, force_refresh=g("refresh") == "1")


@route("GET", "/api/sources")
def r_sources(q, body):
    return {"sources": pipeline.health_report()}


@route("POST", "/api/refine")
def r_refine(q, body):
    return refit.refine_resume_for_job(_job(body), _need_profile())


@route("POST", "/api/gap-report")
def r_gap(q, body):
    return refit.generate_gap_report(_job(body), _need_profile())


@route("POST", "/api/cover-letter")
def r_cover(q, body):
    return {"cover_letter": refit.generate_cover_letter(_job(body), _need_profile(), body.get("tone", "direct"))}


@route("POST", "/api/interview-prep")
def r_prep(q, body):
    return refit.generate_interview_prep(_job(body), _need_profile())


@route("POST", "/api/ats-audit")
def r_ats(q, body):
    resume = body.get("resume") or _need_profile()
    return ats.compute_ats_audit(resume, _job(body))


@route("POST", "/api/auto-tailor")
def r_auto_tailor(q, body):
    t0, job, profile = time.time(), _job(body), _need_profile()
    ref = refit.refine_resume_for_job(job, profile)
    before, after = ats.compute_ats_audit(profile, job), ats.compute_ats_audit(ref["tailored_resume"], job)
    return {"success": True, "status": "success", "job_id": job.get("id"), "job_title": job.get("title"),
            "company": job.get("company"), "tailored_resume": ref["tailored_resume"], "refinement": ref,
            "ats_audit": after, "before_ats": before, "after_ats": after,
            "boost": after["ats_score"] - before["ats_score"], "speed_ms": int((time.time() - t0) * 1000),
            "engine": ref["engine"]}


@route("POST", "/api/auto-hunt")
def r_hunt(q, body):
    return tracker.prepare_application(_job(body), _need_profile())


@route("GET", "/api/applications")
def r_apps(q, body):
    return {"applications": tracker.list_applications()}


@route("POST", "/api/applications")
def r_save_app(q, body):
    try:
        return {"success": True, "id": tracker.upsert_application(body)}
    except ValueError as e:
        raise ApiError(str(e))


@route("GET", "/api/stats")
def r_stats(q, body):
    return tracker.funnel_stats()


@route("GET", "/api/watchlist")
def r_watch(q, body):
    return {"watchlist": tracker.list_watchlist()}


@route("POST", "/api/watchlist")
def r_add_watch(q, body):
    try:
        r = tracker.add_watch(body.get("company_name"), body.get("slug", ""), body.get("board_type", ""), body.get("target_role", ""))
    except ValueError as e:
        raise ApiError(str(e))
    return {"success": True, **r}


@route("POST", "/api/watchlist/check")
def r_check_watch(q, body):
    return {"results": tracker.check_watchlist(db.get_profile())}


@route("GET", "/api/digest")
def r_digest(q, body):
    return digest.build_digest()


@route("POST", "/api/digest/send")
def r_digest_send(q, body):
    return digest.send_digest()


@route("GET", "/api/settings")
def r_get_settings(q, body):
    allowed = {"digest_min_score", "digest_email", "adzuna_app_id", "adzuna_app_key",
               "ai_provider", "gemini_api_key", "openai_api_key", "anthropic_api_key", "ai_model", "ollama_endpoint"}
    out = {}
    with db.session() as c:
        for row in c.execute("SELECT key, value FROM settings"):
            if row["key"] in allowed:
                out[row["key"]] = row["value"]
    cfg = refit.get_active_ai_config()
    out["active_provider"] = cfg["provider"]
    out["active_model"] = cfg["model"]
    out["llm_available"] = refit.llm_available()
    return out


@route("POST", "/api/settings")
def r_settings(q, body):
    allowed = {"digest_min_score", "digest_email", "adzuna_app_id", "adzuna_app_key",
               "ai_provider", "gemini_api_key", "openai_api_key", "anthropic_api_key", "ai_model", "ollama_endpoint"}
    for k, v in body.items():
        if k in allowed:
            db.set_setting(k, str(v).strip())
    return {"success": True, "active_ai": refit.get_active_ai_config()}


@route("POST", "/api/test-ai")
def r_test_ai(q, body):
    t0 = time.time()
    cfg = refit.get_active_ai_config()
    if cfg["provider"] == "deterministic":
        return {"success": True, "provider": "deterministic", "latency_ms": 1,
                "message": "Deterministic engine active (100% local, fast, zero cost, 0 hallucinations)."}
    try:
        reply = refit._call_llm("You are an assistant. Reply with 'OK'.", "Ping", cfg)
        ms = int((time.time() - t0) * 1000)
        return {"success": True, "provider": cfg["provider"], "model": cfg["model"], "latency_ms": ms,
                "message": f"Successfully connected to {cfg['provider'].title()} in {ms}ms."}
    except Exception as e:
        return {"success": False, "provider": cfg["provider"], "error": str(e),
                "message": f"Connection failed to {cfg['provider']}: {str(e)[:160]}"}


@route("POST", "/api/ai-strategy")
def r_ai_strategy(q, body):
    return refit.generate_ai_strategy(_job(body), _need_profile())


@route("GET", "/api/cache-stats")
def r_cache(q, body):
    with db.session() as c:
        n = c.execute("SELECT COUNT(*) n FROM source_cache").fetchone()["n"]
    cfg = refit.get_active_ai_config()
    return {"cached_queries_count": n, "ttl_seconds": config.CACHE_TTL_SECONDS, "version": __version__,
            "llm_enabled": refit.llm_available(), "ai_provider": cfg["provider"], "ai_model": cfg["model"],
            "demo": config.DEMO}


@route("POST", "/api/clear-cache")
def r_clear(q, body):
    pipeline.clear_cache()
    return {"success": True, "message": "Search cache cleared."}


@route("POST", "/api/export")
def r_export(q, body):
    fmt = (body.get("format") or "txt").lower()
    resume = body.get("resume") or _need_profile()
    if fmt == "doc":
        fmt = "docx"
    if fmt == "txt":
        return {"format": "txt", "content": exporters.to_txt(resume), "filename": exporters.safe_name(resume, "txt")}
    if fmt == "html":
        return {"format": "html", "content": exporters.to_html(resume), "filename": exporters.safe_name(resume, "html")}
    if fmt == "docx":
        data, mime = exporters.to_docx(resume), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif fmt == "pdf":
        data, mime = exporters.to_pdf(resume), "application/pdf"
    else:
        raise ApiError("format must be txt, html, docx, or pdf.")
    return {"format": fmt, "mime": mime, "content_base64": base64.b64encode(data).decode(), "filename": exporters.safe_name(resume, fmt)}


# ------------------------------------------------------------------ handler

class Handler(SimpleHTTPRequestHandler):
    server_version = "JobHunter/" + __version__

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=config.STATIC_DIR, **kw)

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    # -- helpers
    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost", "[::1]") or host == config.HOST.lower()

    def _dispatch(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not self._host_ok():
            return self._json({"error": "Host not allowed"}, 403)
        if not path.startswith("/api/"):
            return False
        if self.headers.get("X-JH-Token") != TOKEN:
            return self._json({"error": "Missing or invalid session token. Reload the page."}, 401)
        body = {}
        if method in ("POST", "DELETE"):
            n = int(self.headers.get("Content-Length") or 0)
            if n > config.MAX_BODY_BYTES:
                return self._json({"error": "Request body too large"}, 413)
            if n:
                try:
                    body = json.loads(self.rfile.read(n).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    return self._json({"error": "Body must be valid JSON"}, 400)
        try:
            if method == "DELETE":
                return self._delete(path)
            fn = ROUTES.get((method, path))
            if not fn:
                return self._json({"error": "Endpoint not found"}, 404)
            return self._json(fn(urllib.parse.parse_qs(parsed.query), body if isinstance(body, dict) else {}))
        except ApiError as e:
            return self._json({"error": str(e)}, e.status)
        except Exception as e:
            ref = secrets.token_hex(4)
            log.error("error %s: %s\n%s", ref, e, traceback.format_exc())
            return self._json({"error": f"Internal error (ref {ref}). Check the server log."}, 500)

    def _delete(self, path):
        if path.startswith("/api/applications/"):
            tracker.delete_application(path.rsplit("/", 1)[-1])
        elif path.startswith("/api/watchlist/"):
            tracker.delete_watch(path.rsplit("/", 1)[-1])
        elif path == "/api/purge-all-data":
            db.purge_all()
            pipeline.clear_cache()
            return self._json({"success": True, "message": "All local data deleted and the database file compacted."})
        else:
            return self._json({"error": "Endpoint not found"}, 404)
        return self._json({"success": True})

    # -- verbs
    def do_GET(self):
        if self._dispatch("GET") is not False:
            return
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(config.STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
                page = f.read().replace("</head>", f'<meta name="jh-token" content="{TOKEN}"></head>', 1).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(page)
            return
        super().do_GET()

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):  # no cross-origin access is granted
        self.send_response(204)
        self.end_headers()


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.init_db()
    digest.start_scheduler()
    srv = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    srv.daemon_threads = True
    log.info("JobHunter %s on http://%s:%d  (LLM: %s, demo: %s)", __version__, config.HOST, config.PORT,
             "on" if refit.llm_available() else "off", config.DEMO)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("Stopped.")
