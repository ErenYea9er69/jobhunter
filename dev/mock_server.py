#!/usr/bin/env python3
"""Mock JobHunter daemon for previewing the UI without the real backend.

Usage:  python3 mock_server.py --root ../webapp --port 8765
Switch data at runtime:  GET /__mock/scenario/default | empty | offline
All people, companies and jobs below are fictional sample data.
"""
import argparse
import json
import mimetypes
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

STATE = {"scenario": "default"}

PROFILE = {
    "id": "backend-python",
    "name": "Amira Ben Salah",
    "filename": "Amira_BenSalah_Backend.pdf",
    "target_title": "Backend Engineer (Python)",
    "email": "amira.bensalah@example.com",
    "phone": "+216 20 000 000",
    "location": "Tunis, Tunisia",
    "linkedin": "https://www.linkedin.com/in/amira-example",
    "github": "https://github.com/amira-example",
    "website": "",
    "experience_years": 4,
    "is_active": True,
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis", "REST APIs", "Kubernetes", "CI/CD", "Celery", "SQLAlchemy", "AWS", "Pytest"],
    "experience": [
        {"title": "Backend Engineer", "company": "Sahel Pay", "period": "2022 to now",
         "summary": "Built the payout service in FastAPI and PostgreSQL. Cut settlement time from 2 days to 3 hours. Moved 14 services to Docker and Kubernetes."},
        {"title": "Software Engineer", "company": "Carthage Labs", "period": "2020 to 2022",
         "summary": "Wrote Python data pipelines on Celery and Redis. Raised test coverage from 38% to 81% with Pytest."},
        {"title": "Intern, backend", "company": "Medina Cloud", "period": "2019",
         "summary": "Built an internal REST API for ticket routing."},
    ],
}
PROFILE_ML = dict(PROFILE, id="ml-engineer", name="Amira Ben Salah", filename="Amira_BenSalah_ML.docx",
                  target_title="Machine Learning Engineer", is_active=False,
                  skills=["Python", "PyTorch", "scikit-learn", "SQL", "Airflow", "MLflow", "Docker"])

JOBS = [
    {"id": "j1", "title": "Senior Backend Engineer, Payments", "company": "Northwind Systems", "location": "Remote, Europe", "work_mode": "Remote", "job_type": "Full-time", "salary": "EUR 48k to 62k", "score": 94, "source": "Greenhouse", "posted_days_ago": 1,
     "matched_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
     "match_reasons": ["Your payout service work at Sahel Pay matches the payments scope.", "Four of the five required tools appear in your resume."],
     "description": "About the role\nWe build the payment rails behind a European marketplace. You will own services written in Python and FastAPI, backed by PostgreSQL, and ship them with Docker and Kubernetes.\n\nWhat you will do\n- Design and run REST APIs that handle settlement and refunds.\n- Improve reliability: alerts, retries, idempotent writes.\n- Review code and mentor two junior engineers.\n\nWhat we look for\n- 3+ years with Python in production.\n- Strong PostgreSQL skills, including query tuning.\n- Experience with Docker and CI/CD.\n- Clear written English.\n\nNice to have: Kafka, Terraform.",
     "apply_url": "https://boards.greenhouse.io/example/jobs/1"},
    {"id": "j2", "title": "Python Developer", "company": "Atlas Logistics", "location": "Tunis, Tunisia", "work_mode": "Hybrid", "job_type": "Full-time", "salary": "", "score": 88, "source": "Keejob", "posted_days_ago": 3,
     "matched_skills": ["Python", "REST APIs", "Redis"],
     "match_reasons": ["Location and stack match your profile."],
     "description": "Atlas Logistics is hiring a Python developer for its fleet platform in Tunis. You will write REST APIs, work with Redis queues and improve test coverage. Three days in the office.\n\nRequirements: Python, REST APIs, Redis, Git. French and English.",
     "apply_url": "https://example.com/atlas/apply"},
    {"id": "j3", "title": "Backend Engineer (Go or Python)", "company": "Medina Cloud", "location": "Remote, Worldwide", "work_mode": "Remote", "job_type": "Full-time", "salary": "USD 55k to 70k", "score": 91, "source": "Ashby", "posted_days_ago": 2,
     "matched_skills": ["Python", "Kubernetes", "AWS", "CI/CD"],
     "match_reasons": ["Medina Cloud is where you interned in 2019."],
     "description": "Join the platform team. You will build control plane services on Kubernetes and AWS. Python or Go. Strong CI/CD habits.\n\nYou bring: 3 years of backend work, Kubernetes, AWS.",
     "apply_url": "https://jobs.ashbyhq.com/example/3"},
    {"id": "j4", "title": "Stage PFE: Plateforme de donnees", "company": "Carthage Labs", "location": "Tunis, Tunisia", "work_mode": "Onsite", "job_type": "Internship", "salary": "", "score": 72, "source": "Keejob", "posted_days_ago": 6,
     "matched_skills": ["Python", "Celery"],
     "match_reasons": [],
     "description": "Stage de fin d'etudes (6 mois). Vous participez a la conception de pipelines de donnees en Python. Encadrement par un ingenieur senior.\n\nProfil: Python, SQL, curiosite.",
     "apply_url": "https://example.com/carthage/pfe"},
    {"id": "j5", "title": "Platform Engineer", "company": "Sahel Pay", "location": "Tunis, Tunisia", "work_mode": "Hybrid", "job_type": "Full-time", "salary": "", "score": 86, "source": "Company site", "posted_days_ago": 9,
     "matched_skills": ["Kubernetes", "Docker", "CI/CD"],
     "match_reasons": ["You already work at this company."],
     "description": "Own the deployment platform for 14 services. Kubernetes, Docker, Terraform and observability.",
     "apply_url": "https://example.com/sahelpay/platform"},
    {"id": "j6", "title": "Data Engineer", "company": "Orchid Analytics", "location": "Paris, France", "work_mode": "Hybrid", "job_type": "Contract", "salary": "EUR 450 per day", "score": 79, "source": "HelloWork", "posted_days_ago": 4,
     "matched_skills": ["Python", "PostgreSQL"],
     "match_reasons": [],
     "description": "Mission de 6 mois pour construire des pipelines Airflow sur PostgreSQL et BigQuery. Python requis.",
     "apply_url": "https://example.com/orchid/data"},
    {"id": "j7", "title": "Software Engineer, API", "company": "Lumen Health", "location": "Remote, EMEA", "work_mode": "Remote", "job_type": "Full-time", "salary": "", "score": 83, "source": "Lever", "posted_days_ago": 5,
     "matched_skills": ["Python", "REST APIs", "PostgreSQL"],
     "match_reasons": ["Most required skills appear in your resume."],
     "description": "Build APIs for a telehealth product. Python, PostgreSQL, and care for data privacy.",
     "apply_url": "https://jobs.lever.co/example/7"},
    {"id": "j8", "title": "Junior Backend Developer", "company": "Zitouna Studio", "location": "Sfax, Tunisia", "work_mode": "Onsite", "job_type": "Full-time", "salary": "", "score": 68, "source": "Keejob", "posted_days_ago": 12,
     "matched_skills": ["Python"],
     "match_reasons": [],
     "description": "Poste junior. Vous aurez plus d'experience que requis.",
     "apply_url": "https://example.com/zitouna/junior"},
    {"id": "j9", "title": "Staff Engineer, Developer Experience at a very long company name that keeps going to test wrapping behaviour", "company": "International Consolidated Holdings and Technology Services Group", "location": "Berlin, Germany, with occasional travel to offices in Madrid, Lisbon and Dublin", "work_mode": "Hybrid", "job_type": "Full-time", "salary": "EUR 90k to 110k", "score": 61, "source": "Arbeitsagentur", "posted_days_ago": 20,
     "matched_skills": ["Python", "CI/CD", "Kubernetes", "Docker", "AWS", "Redis"],
     "match_reasons": [],
     "description": "A long posting. " + "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 12,
     "apply_url": "https://example.com/long"},
    {"id": "j10", "title": "\u0645\u0647\u0646\u062f\u0633 \u0628\u0631\u0645\u062c\u064a\u0627\u062a \u062e\u0644\u0641\u064a\u0629", "company": "\u0634\u0631\u0643\u0629 \u0627\u0644\u0645\u062f\u064a\u0646\u0629", "location": "\u062a\u0648\u0646\u0633", "work_mode": "Onsite", "job_type": "Full-time", "salary": "", "score": 74, "source": "Keejob", "posted_days_ago": 7,
     "matched_skills": ["Python"],
     "match_reasons": [],
     "description": "\u0646\u0628\u062d\u062b \u0639\u0646 \u0645\u0647\u0646\u062f\u0633 \u0628\u0631\u0645\u062c\u064a\u0627\u062a \u0644\u062f\u064a\u0647 \u062e\u0628\u0631\u0629 \u0641\u064a Python \u0648 REST APIs.",
     "apply_url": "https://example.com/ar"},
    {"id": "j11", "title": "Backend Engineer", "company": "Quartz Mobility", "location": "Remote, Worldwide", "work_mode": "Remote", "job_type": "Full-time", "salary": "", "score": None, "source": "Remotive", "posted_days_ago": 8,
     "matched_skills": [], "match_reasons": [],
     "description": "No score was computed for this posting.",
     "apply_url": "https://example.com/quartz"},
]

APPS = [
    {"id": "a1", "title": "Backend Engineer", "company": "Orchid Analytics", "status": "saved", "url": "https://example.com/1", "notes": ""},
    {"id": "a2", "title": "Platform Engineer", "company": "Sahel Pay", "status": "saved", "url": "", "notes": ""},
    {"id": "a3", "title": "Python Developer", "company": "Atlas Logistics", "status": "queued", "url": "https://example.com/atlas/apply", "notes": "Queued from Discovery feed. Match score: 88%"},
    {"id": "a4", "title": "Senior Backend Engineer, Payments", "company": "Northwind Systems", "status": "queued", "url": "https://boards.greenhouse.io/example/jobs/1", "notes": ""},
    {"id": "a5", "title": "Software Engineer, API", "company": "Lumen Health", "status": "applied", "url": "https://jobs.lever.co/example/7", "notes": "[Gmail] confirmation received"},
    {"id": "a6", "title": "Backend Developer", "company": "Zitouna Studio", "status": "applied", "url": "", "notes": ""},
    {"id": "a7", "title": "Backend Engineer (Go or Python)", "company": "Medina Cloud", "status": "interview", "url": "https://jobs.ashbyhq.com/example/3", "notes": "[Gmail] interview invitation"},
    {"id": "a8", "title": "Data Engineer", "company": "Quartz Mobility", "status": "rejected", "url": "", "notes": ""},
    {"id": "a9", "title": "Staff Engineer", "company": "Helix Robotics", "status": "offer", "url": "", "notes": ""},
]

PREFS = {"target_countries": ["Tunisia", "France"], "home_cities": ["Tunis"], "work_mode": "Any",
         "job_types": ["Full-time"], "excluded_companies": [], "excluded_keywords": ["php"],
         "dream_companies": ["Northwind Systems"], "search_depth": "standard"}

AI = {"mode": "mcp_client", "provider": "gemini", "model": "", "key_configured": False, "masked_key": "",
      "recommended_models": {}}


def env(data, status=200):
    return status, json.dumps({"status": "ok", "success": True, "data": data}).encode()


def letter(job):
    t = job.get("title") or "the role"
    c = job.get("company") or "your company"
    return ("Dear hiring team,\n\n"
            f"I am writing to apply for the {t} role at {c}. At Sahel Pay I built the payout service in FastAPI and PostgreSQL and cut settlement time from 2 days to 3 hours. "
            "I also moved 14 services to Docker and Kubernetes, so I know the day to day work of running Python services in production.\n\n"
            "Before that, at Carthage Labs, I wrote data pipelines on Celery and Redis and raised test coverage from 38% to 81% with Pytest. I like small teams that review code carefully and measure the result.\n\n"
            "I would be glad to talk about how this experience fits your team.\n\nBest regards,\nAmira Ben Salah")


class H(BaseHTTPRequestHandler):
    root = "."

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"")

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        sc = STATE["scenario"]
        if p.startswith("/__mock/scenario/"):
            STATE["scenario"] = p.rsplit("/", 1)[1]
            return self._send(200, b"{}")
        if p.startswith("/api/"):
            return self.api("GET", p, parse_qs(u.query), {})
        if p == "/":
            p = "/index.html"
        fp = os.path.normpath(os.path.join(self.root, p.lstrip("/")))
        if not fp.startswith(os.path.abspath(self.root)) or not os.path.isfile(fp):
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_POST(self):
        u = urlparse(self.path)
        self.api("POST", u.path, parse_qs(u.query), self._body())

    def api(self, method, p, q, b):
        sc = STATE["scenario"]
        if sc == "offline":
            return self._send(503, json.dumps({"success": False, "error": {"message": "offline"}}).encode())
        time.sleep(0.15)
        code, body = 200, None
        if p == "/api/search":
            time.sleep(0.5)
            jobs = [] if sc == "empty" else JOBS
            code, body = env({"jobs": jobs})
        elif p == "/api/applications" and method == "GET":
            apps = [] if sc == "empty" else APPS
            stats = {k: sum(1 for a in apps if a["status"] == k) for k in ["saved", "queued", "applied", "interview", "offer"]}
            code, body = env({"applications": apps, "stats": stats})
        elif p == "/api/applications":
            if b.get("id"):
                for a in APPS:
                    if a["id"] == b["id"]:
                        a["status"] = b.get("status", a["status"])
            else:
                APPS.append({"id": "a%d" % (len(APPS) + 1), "title": b.get("title", ""), "company": b.get("company", ""),
                             "status": b.get("status", "saved"), "url": b.get("url", ""), "notes": b.get("notes", "")})
            code, body = env({"success": True})
        elif p == "/api/profiles":
            profs = [] if sc == "empty" else [PROFILE, PROFILE_ML]
            act = next((x["id"] for x in profs if x["is_active"]), None)
            code, body = env({"active": act, "profiles": profs})
        elif p == "/api/resumes/folder-info":
            code, body = env({"resumes_dir": "/Users/amira/jobhunter/resumes"})
        elif p == "/api/preferences" and method == "GET":
            code, body = env(PREFS)
        elif p == "/api/preferences":
            PREFS.update(b.get("updates", {}))
            code, body = env({"success": True})
        elif p == "/api/ai/status":
            code, body = env(AI)
        elif p == "/api/profile/activate":
            for pr in (PROFILE, PROFILE_ML):
                pr["is_active"] = (pr["id"] == b.get("id")) or (b.get("id") is None and pr["name"] == b.get("name"))
            code, body = env({"success": True})
        elif p in ("/api/ai/config", "/api/ai/clear-key", "/api/ai/test", "/api/resumes/scan", "/api/auto-apply/launch", "/api/outreach/save-draft"):
            code, body = env({"success": True, "latency_ms": 412, "provider": "gemini", "model": "gemini-3.8-flash"})
        elif p == "/api/resumes/upload":
            code, body = env({"success": True, "profile": PROFILE})
        elif p == "/api/desktop/extension-status":
            code, body = env({"browsers": [{"name": "Google Chrome", "path": "C:/Program Files/Google/Chrome/Application/chrome.exe"}, {"name": "Microsoft Edge", "path": "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"}]})
        elif p == "/api/gmail/status":
            code, body = env({"configured": False})
        elif p == "/api/gmail/sync":
            code, body = env({"success": True, "applications_updated": 2, "applications_created": 1})
        elif p == "/api/gmail/config":
            code, body = env({"saved": True})
        elif p == "/api/documents/job-package":
            j = b.get("job", {})
            time.sleep(0.8)
            code, body = env({"company": j.get("company"), "cover_letter": {"full_text": letter(j), "review": {"verdict": "pass"}},
                              "tailored_resume": {"txt": "AMIRA BEN SALAH\nBackend Engineer (Python)\n\nSKILLS\nPython, FastAPI, PostgreSQL, Docker, Kubernetes\n\nEXPERIENCE\nSahel Pay, Backend Engineer, 2022 to now\n- Built the payout service in FastAPI and PostgreSQL.\n- Cut settlement time from 2 days to 3 hours.",
                                                 "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"], "ats_match_pct": 87}})
        elif p == "/api/documents/interview-prep":
            code, body = env({"prep": {"stories": [{"situation": "Settlement was slow", "action": "Rebuilt the payout service", "result": "2 days to 3 hours"}]}})
        elif p == "/api/documents/outreach":
            code, body = env({"outreach": {"linkedin_connection_note": "Hi, I build Python payment services and your team's work caught my eye.", "hiring_manager_inmail": {"subject_line": "Backend engineer, payments", "body": "Hello,\n\nI built a payout service in FastAPI that cut settlement from 2 days to 3 hours."}}})
        elif p == "/api/outreach/founder-email":
            code, body = env({"subject_options": ["Faster settlements at Northwind", "A Python engineer who cut payouts to 3 hours", "Quick question about your payments stack"],
                              "body": "Hi,\n\nI built a payout service in FastAPI and PostgreSQL that cut settlement time from 2 days to 3 hours. I would like to help your team do the same.\n\nWould a short call work this week?\n\nAmira", "follow_up_note": "Hi, bumping this in case it got buried.", "word_count": 46, "reading_time_sec": 14,
                              "review": {"verdict": "pass"}, "recipient_email": b.get("recipient_email", ""), "gmail_compose_url": "https://mail.google.com/"})
        elif p == "/api/outreach/linkedin-founder":
            code, body = env({"connection_note": "Hi, I built a Python payout service that cut settlement from 2 days to 3 hours. Would love to connect.", "connection_note_length": 98, "inmail_subject": "Payments engineer", "inmail_body": "Hello,\n\nI built a payout service in FastAPI.", "inmail_word_count": 8, "review_note": {"verdict": "pass"}})
        elif p == "/api/bigtech/pitch":
            code, body = env({"company": "Google", "level_label": "L4", "rubric_focus": "Coding and system design", "recruiter_email": "", "inmail_subject": "Backend engineer", "inmail_body": "Hello,\n\nI build Python services.", "inmail_word_count": 6, "referral_blurb": "Amira built a payout service in FastAPI.", "referral_portal_name": "Google Referrals", "review_inmail": {"verdict": "pass"}, "gmail_compose_url": ""})
        elif p == "/api/email-finder/find":
            code, body = env({"primary_email": "founder@northwind.example", "confidence_pct": 91, "mail_provider": "Google Workspace", "name": b.get("name", ""), "company": b.get("company", ""), "candidates": [{"email": "founder@northwind.example", "confidence_pct": 91}, {"email": "f.lastname@northwind.example", "confidence_pct": 64}]})
        elif p == "/api/extension/solve":
            code, body = env({"answer": "I have 4 years of professional experience with Python and built REST APIs in FastAPI at Sahel Pay.", "review": {"verdict": "pass"}})
        elif p == "/api/extension/status":
            code, body = env({"candidate_name": PROFILE["name"], "active_profile": PROFILE["target_title"]})
        elif p == "/api/extension/payload":
            code, body = env({"profile": PROFILE})
        elif p == "/api/extension/confirm-applied":
            code, body = env({"success": True})
        elif p == "/api/extension/founder-outreach":
            code, body = env({"connection_note": "Hi, I build Python payment services. Would love to connect.", "connection_note_length": 62, "inmail_body": "Hello,\n\nI build Python services.", "inmail_word_count": 5})
        else:
            code, body = 404, json.dumps({"success": False, "error": {"message": "unknown " + p}}).encode()
        self._send(code, body)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    H.root = os.path.abspath(a.root)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
