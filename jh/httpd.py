"""HTTP Daemon & REST API Layer for JobHunter.

Bridges the Web Dashboard and ATS Browser Extension into the SQLite tracker,
screening engine, Reviewer QA, and ResumeRegistry without polluting stdout.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import db, extension_installer, pipeline, resume_registry, screening, tracker
from . import mcp_helpers as h
from .mcp_helpers import envelope
from .team import qa

log = logging.getLogger("jobhunter.httpd")
if not log.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [httpd] %(levelname)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def _ensure_db() -> None:
    try:
        db.init_db()
    except Exception:
        pass


class JobHunterRequestHandler(BaseHTTPRequestHandler):
    server_version = "JobHunter/2.3.0"

    def log_message(self, format: str, *args: Any) -> None:
        """Override to ensure all HTTP logging goes strictly to stderr, keeping stdout clean."""
        sys.stderr.write(f"[httpd] {self.address_string()} - {format % args}\n")
        sys.stderr.flush()

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    def _send_json(self, status_code: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _read_body_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
        except Exception:
            return {}

    # ------------------------------------------------------------- GET Dispatch
    def do_GET(self) -> None:
        _ensure_db()
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        ws_dir = getattr(self.server, "ws_dir", Path.cwd())
        registry = resume_registry.ResumeRegistry(ws_dir)

        # 1. API routes
        if path == "/api/extension/status":
            active_name = registry.get_active_variant() or "Default"
            profile = h.resolve_profile(require=False) or {}
            browsers = extension_installer.detect_chromium_browsers()
            res = envelope(
                status="ok",
                data={
                    "status": "ok",
                    "active_profile": active_name,
                    "target_title": profile.get("target_title", ""),
                    "candidate_name": profile.get("name", ""),
                    "browsers_detected": len(browsers),
                },
            )
            return self._send_json(200, res)

        if path == "/api/profiles":
            profiles = db.list_resume_profiles()
            active = next((p["name"] for p in profiles if p.get("is_active")), None) or registry.get_active_variant()
            res = envelope(
                status="ok",
                data={
                    "profiles": profiles,
                    "active_profile": active or "Default",
                    "count": len(profiles),
                },
            )
            return self._send_json(200, res)

        if path == "/api/applications":
            limit = int(query.get("limit", [100])[0])
            status_filter = query.get("status", [""])[0]
            apps = tracker.list_applications()
            if status_filter:
                apps = [a for a in apps if a.get("status") == status_filter]
            if limit:
                apps = apps[:limit]
            stats = tracker.funnel_stats()
            res = envelope(
                status="ok",
                data={
                    "applications": apps,
                    "stats": stats,
                    "count": len(apps),
                },
            )
            return self._send_json(200, res)

        if path == "/api/desktop/extension-status":
            data = extension_installer.get_extension_status()
            return self._send_json(200, envelope(status="ok", data=data))

        if path == "/api/search":
            q = query.get("q", [""])[0]
            loc = query.get("location", [""])[0]
            limit = int(query.get("limit", [25])[0])
            jobs = pipeline.search_jobs(query=q, location=loc, limit=limit)
            return self._send_json(200, envelope(status="ok", data={"jobs": jobs, "count": len(jobs)}))

        # 2. Static files from public/
        self._serve_static(path)

    # ------------------------------------------------------------ POST Dispatch
    def do_POST(self) -> None:
        _ensure_db()
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body_json()

        ws_dir = getattr(self.server, "ws_dir", Path.cwd())
        registry = resume_registry.ResumeRegistry(ws_dir)

        if path == "/api/extension/payload":
            profile = h.resolve_profile(require=False) or {}
            ext_status = extension_installer.get_extension_status()
            res = envelope(
                status="ok",
                data={
                    "profile": {
                        "name": profile.get("name", ""),
                        "email": profile.get("email", ""),
                        "phone": profile.get("phone", ""),
                        "linkedin": profile.get("linkedin", ""),
                        "github": profile.get("github", ""),
                        "website": profile.get("website", ""),
                        "location": profile.get("location", ""),
                        "target_title": profile.get("target_title", ""),
                        "skills": profile.get("skills", []),
                        "experience_years": profile.get("total_experience_years", 3),
                    },
                    "resume_path": profile.get("source_path", ""),
                    "extension_version": ext_status.get("version", "2.3.0"),
                },
            )
            return self._send_json(200, res)

        if path == "/api/extension/solve":
            question = body.get("question", "")
            job_info = body.get("job", {})
            profile = h.resolve_profile(require=False) or {}

            raw_answer = screening.solve_screening_question(question, profile, job_info, use_llm=False)
            answer_text = raw_answer.get("answer", "") if isinstance(raw_answer, dict) else str(raw_answer)

            doc_record = {
                "kind": "screening_answer",
                "text": answer_text,
                "question": question,
            }
            review = qa.review_document(answer_text, kind="screening_answer", profile=profile, job=job_info)
            final_text = review.adjusted.get("text") or answer_text if isinstance(review.adjusted, dict) else answer_text

            res = envelope(
                status="ok",
                data={
                    "question": question,
                    "answer": final_text,
                    "review": {
                        "verdict": review.verdict,
                        "findings": review.findings,
                    },
                },
            )
            return self._send_json(200, res)

        if path == "/api/extension/confirm-applied":
            app_data = {
                "company": body.get("company", "Unknown Employer"),
                "title": body.get("title", "Job Application"),
                "url": body.get("url", ""),
                "status": "applied",
                "notes": body.get("notes", "Submitted via JobHunter ATS Autofill extension"),
            }
            app_id = tracker.upsert_application(app_data)
            return self._send_json(200, envelope(status="ok", data={"application_id": app_id}))

        if path == "/api/applications":
            app_id = tracker.upsert_application(body)
            return self._send_json(200, envelope(status="ok", data={"application_id": app_id}))

        if path == "/api/profile/activate":
            name = body.get("name", "")
            success = registry.set_active_variant(name)
            return self._send_json(200, envelope(status="ok" if success else "error", data={"active_profile": name, "success": success}))

        if path == "/api/desktop/launch-browser-extension":
            browser = body.get("browser", "auto")
            url = body.get("url", "http://127.0.0.1:8765")
            res = extension_installer.launch_browser_with_extension(url=url, browser_type=browser)
            return self._send_json(200, envelope(status="ok" if res.get("success") else "error", data=res))

        if path == "/api/desktop/open-extension-folder":
            browser = body.get("browser", "auto")
            res = extension_installer.open_extension_manager(browser_type=browser)
            return self._send_json(200, envelope(status="ok", data=res))

        self._send_json(404, envelope(status="error", error={"code": "not_found", "message": f"Path '{path}' not found"}))

    # --------------------------------------------------------- Static Serving
    def _serve_static(self, req_path: str) -> None:
        public_dir = Path(__file__).resolve().parent.parent / "public"
        rel = req_path.lstrip("/")
        if not rel or rel == "/":
            rel = "index.html"

        target = (public_dir / rel).resolve()
        # Security: prevent directory traversal
        try:
            target.relative_to(public_dir.resolve())
        except ValueError:
            return self._send_json(403, envelope(status="error", error={"code": "forbidden", "message": "Access denied"}))

        if not target.is_file():
            index = public_dir / "index.html"
            if index.is_file():
                target = index
            else:
                return self._send_json(404, envelope(status="error", error={"code": "not_found", "message": "Static asset not found"}))

        mime, _ = mimetypes.guess_type(str(target))
        try:
            content = target.read_bytes()
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            log.warning("Could not serve static file %s: %s", target, e)
            self._send_json(500, envelope(status="error", error={"code": "server_error", "message": str(e)}))


def start_server(host: str = "127.0.0.1", port: int = 8765, ws_dir: str | Path = ".") -> ThreadingHTTPServer:
    """Starts the ThreadingHTTPServer on a daemon thread and returns the server instance."""
    _ensure_db()
    server = ThreadingHTTPServer((host, port), JobHunterRequestHandler)
    server.daemon_threads = True
    server.ws_dir = Path(ws_dir).resolve()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("JobHunter HTTP Daemon running on http://%s:%d (workspace: %s)", host, port, server.ws_dir)
    return server
