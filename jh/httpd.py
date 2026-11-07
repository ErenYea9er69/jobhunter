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

from . import db, exporters, extension_installer, founder_outreach, gmail_tracker, pipeline, preferences, refit, regions, resume_registry, screening, tracker
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

        if path == "/api/gmail/status":
            data = gmail_tracker.get_gmail_config()
            return self._send_json(200, envelope(status="ok", data=data))

        if path == "/api/preferences":
            prefs = preferences.load()
            prof = h.resolve_profile(require=False) or {}
            targets = regions.resolve_targets(prefs, prof, "")
            return self._send_json(200, envelope(status="ok", data={"preferences": prefs, "resolved_targets": targets}))

        if path == "/api/jobs/details":
            job_id = query.get("job_id", [""])[0]
            job = h.build_job(job_id=job_id) if job_id else {}
            prof = h.resolve_profile(require=False) or {}
            gap = refit.generate_gap_report(job, prof) if job else {}
            return self._send_json(200, envelope(status="ok", data={"job": job, "gap": gap}))

        if path == "/api/search":
            q = query.get("q", [""])[0]
            loc = query.get("location", [""])[0]
            wm = query.get("work_mode", ["Any"])[0]
            jt = query.get("job_type", [""])[0]
            min_score = int(query.get("min_score", [0])[0])
            limit = int(query.get("limit", [50])[0])
            prof = h.resolve_profile(overlay=False, require=False)
            res = pipeline.search(query=q, location=loc, work_mode=wm, min_score=min_score, limit=limit, profile=prof, job_type=jt)
            jobs = res.get("jobs", []) if isinstance(res, dict) else res
            return self._send_json(200, envelope(status="ok", data={"jobs": jobs, "count": len(jobs), "coverage": res.get("coverage", {})}))

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

        if path == "/api/preferences":
            updates = body.get("updates", body)
            try:
                saved = preferences.update(updates)
                return self._send_json(200, envelope(status="ok", data={"saved": saved, "success": True}))
            except Exception as e:
                return self._send_json(400, envelope(status="error", error={"code": "invalid_preference", "message": str(e)}))

        if path == "/api/documents/cover-letter":
            job_id = body.get("job_id", "")
            title = body.get("title", "")
            company = body.get("company", "")
            desc = body.get("description", "")
            tone = body.get("tone", "direct")
            angle = body.get("angle", "direct_impact")
            job, profile = h.job_and_profile(job_id, title, company, desc)
            pitch = refit.generate_cover_pitch(job, profile, tone=tone, angle=angle)
            letter = pitch.get("full_text") or ""
            review = qa.review_document(letter, kind="cover_letter", profile=profile, job=job)
            return self._send_json(200, envelope(status="ok", data={
                "letter": letter,
                "hook": pitch.get("hook", ""),
                "word_count": len(letter.split()),
                "review": {"verdict": review.verdict, "findings": review.findings}
            }))

        if path == "/api/documents/interview-prep":
            job_id = body.get("job_id", "")
            job, profile = h.job_and_profile(job_id, body.get("title", ""), body.get("company", ""), body.get("description", ""))
            prep = refit.generate_interview_prep(job, profile)
            return self._send_json(200, envelope(status="ok", data={"prep": prep}))

        if path == "/api/documents/outreach":
            job_id = body.get("job_id", "")
            job, profile = h.job_and_profile(job_id, body.get("title", ""), body.get("company", ""), body.get("description", ""))
            outreach = refit.generate_recruiter_outreach(job, profile)
            return self._send_json(200, envelope(status="ok", data={"outreach": outreach}))

        if path == "/api/documents/tailor-resume":
            job_id = body.get("job_id", "")
            job, profile = h.job_and_profile(job_id, body.get("title", ""), body.get("company", ""), body.get("description", ""))
            tailored = refit.generate_custom_resume(job, profile)
            return self._send_json(200, envelope(status="ok", data={"tailored_resume": tailored}))

        if path == "/api/documents/job-package":
            job_info = body.get("job") or body
            job_id = job_info.get("job_id", "")
            job, profile = h.job_and_profile(job_id, job_info.get("title", ""), job_info.get("company", ""), job_info.get("description", ""))
            archetype = body.get("archetype", "startup_velocity")
            custom_resume = refit.generate_custom_resume(job, profile, archetype=archetype)
            resume_dict = custom_resume.get("tailored_resume", {})
            html_export = exporters.to_html(resume_dict)
            txt_export = exporters.to_txt(resume_dict)

            pitch = refit.generate_cover_pitch(job, profile, tone=body.get("tone", "direct"), angle=body.get("angle", "direct_impact"))
            letter_text = pitch.get("full_text") or ""
            review = qa.review_document(letter_text, kind="cover_letter", profile=profile, job=job)

            return self._send_json(200, envelope(status="ok", data={
                "company": job.get("company", "Employer"),
                "title": job.get("title", "Role"),
                "tailored_resume": {
                    "summary": custom_resume.get("tailored_summary", ""),
                    "skills": custom_resume.get("tailored_skills", []),
                    "core_competencies": custom_resume.get("core_competencies", []),
                    "experience": custom_resume.get("tailored_experience", []),
                    "txt": txt_export,
                    "html": html_export,
                    "ats_match_pct": custom_resume.get("recruiter_6sec_audit", {}).get("ats_keyword_match_pct", 85),
                    "skim_score": custom_resume.get("recruiter_6sec_audit", {}).get("skim_score", 90),
                    "eye_catchers": custom_resume.get("recruiter_6sec_audit", {}).get("eye_catchers", [])
                },
                "cover_letter": {
                    "hook": pitch.get("hook", ""),
                    "full_text": letter_text,
                    "word_count": len(letter_text.split()),
                    "review": {
                        "verdict": review.verdict,
                        "findings": review.findings
                    }
                }
            }))

        if path == "/api/outreach/founder-email":
            job_info = body.get("job") or body
            job_id = job_info.get("job_id", "")
            job, profile = h.job_and_profile(job_id, job_info.get("title", ""), job_info.get("company", ""), job_info.get("description", ""))
            res = founder_outreach.generate_founder_cold_email(
                job,
                profile,
                founder_name=body.get("founder_name", ""),
                founder_role=body.get("founder_role", "Founder & CEO"),
                angle=body.get("angle", "scale_velocity"),
                custom_observation=body.get("custom_observation", ""),
                recipient_email=body.get("recipient_email", ""),
            )
            return self._send_json(200, envelope(status="ok", data=res))

        if path == "/api/outreach/save-draft":
            to_email = body.get("to_email", "")
            subject = body.get("subject", "")
            mail_body = body.get("body", "")
            res = founder_outreach.save_draft_to_gmail(to_email, subject, mail_body)
            return self._send_json(200, envelope(status="ok" if res.get("success") else "error", data=res))

        if path == "/api/outreach/send-email":
            to_email = body.get("to_email", "")
            subject = body.get("subject", "")
            mail_body = body.get("body", "")
            company = body.get("company", "")
            job_title = body.get("title", "")
            res = founder_outreach.send_cold_email(to_email, subject, mail_body, company=company, job_title=job_title)
            return self._send_json(200, envelope(status="ok" if res.get("success") else "error", data=res))

        if path == "/api/gmail/config":
            em = body.get("email", "")
            pw = body.get("app_password", "")
            srv = body.get("imap_server", "imap.gmail.com")
            port = body.get("imap_port", 993)
            en = body.get("sync_enabled", True)
            ok = gmail_tracker.save_gmail_config(em, pw, srv, port, en)
            return self._send_json(200, envelope(status="ok" if ok else "error", data={"saved": ok}))

        if path == "/api/gmail/sync":
            mock_msgs = body.get("mock_messages")
            limit = int(body.get("limit", 40))
            sync_res = gmail_tracker.fetch_gmail_and_sync(limit=limit, mock_messages=mock_msgs)
            return self._send_json(200, envelope(status="ok" if sync_res.get("success") else "error", data=sync_res))

        if path == "/api/auto-apply/launch":
            url = body.get("url", "http://127.0.0.1:8765")
            browser = body.get("browser", "auto")
            res = extension_installer.launch_browser_with_extension(url=url, browser_type=browser)
            return self._send_json(200, envelope(status="ok" if res.get("success") else "error", data=res))

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
