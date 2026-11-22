"""Mock servers and hermetic environment for JobHunter E2E verification."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any, Optional


class MockJobBoards:
    """Mock job boards serving the 40 deterministic fixture jobs."""
    def __init__(self, jobs_path: str | None = None):
        import pathlib
        if jobs_path is None:
            jobs_path = str(pathlib.Path(__file__).parent / "fixtures" / "jobs" / "jobs_40.json")
        with open(jobs_path, "r", encoding="utf-8") as f:
            self.jobs = json.load(f)

    def search(self, query: str = "", region: str = "", filters: dict | None = None) -> list[dict]:
        results = []
        q = (query or "").lower().strip()
        r = (region or "").lower().strip()
        for j in self.jobs:
            title_lower = j["title"].lower()
            is_senior = any(w in title_lower for w in ["senior", "lead", "staff", "sr."])
            is_junior = any(w in title_lower for w in ["junior", "intern", "entry", "pfe", "stage", "jr."])

            # Query rule: returns senior or junior jobs only when query holds those words
            if is_senior and not any(w in q for w in ["senior", "lead", "staff", "sr"]):
                continue
            if is_junior and not any(w in q for w in ["junior", "intern", "entry", "pfe", "stage", "jr"]):
                continue

            # Core title/keyword matching for non-level terms
            base_terms = [w for w in q.split() if w not in ["senior", "junior", "lead", "intern", "entry", "staff", "sr", "jr", "pfe", "stage"]]
            if base_terms:
                haystack = f"{j['title']} {j['description']} {j.get('role_focus', '')}".lower()
                if not any(term in haystack for term in base_terms):
                    continue

            if r and r not in j["country"].lower() and r not in j["city"].lower() and r not in j["location"].lower():
                continue
            results.append(j)
        return results


class MockSignalsFeed:
    """Mock funding and hiring posts feeds."""
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.funding_news = [
            # Fresh under 14 days
            {
                "id": "fund_fresh_1",
                "company": "Instadeep",
                "amount": "$100M",
                "round": "Series B",
                "date": (now - timedelta(days=3)).isoformat(),
                "source_url": "https://techcrunch.com/instadeep-100m",
                "summary": "Instadeep raises $100M for enterprise AI decision making.",
                "verified": True,
            },
            # Late (over 14 days)
            {
                "id": "fund_late_1",
                "company": "OldScale",
                "amount": "$10M",
                "round": "Series A",
                "date": (now - timedelta(days=20)).isoformat(),
                "source_url": "https://news.example.com/oldscale-10m",
                "summary": "OldScale announced $10M Series A three weeks ago.",
                "verified": True,
            },
        ]
        self.hiring_posts = [
            # Fresh under 24 hours & under 100 likes
            {
                "id": "post_fresh_1",
                "company": "Instadeep",
                "poster_name": "Karim Baccouche",
                "poster_title": "Head of Engineering",
                "poster_email": "karim@instadeep.example",
                "text": "We are hiring Backend Engineers in Tunis/Sfax to scale our simulation clusters. DM me or email directly!",
                "likes": 42,
                "date": (now - timedelta(hours=8)).isoformat(),
                "role": "Backend Engineer",
                "city": "Tunis",
                "country": "Tunisia",
            },
            # Late due to age (> 24 hours)
            {
                "id": "post_late_age",
                "company": "Expensya",
                "poster_name": "Jihed Othmani",
                "poster_title": "Engineering Lead",
                "poster_email": "jihed@expensya.example",
                "text": "Hiring Python developers for our payment platform.",
                "likes": 35,
                "date": (now - timedelta(hours=36)).isoformat(),
                "role": "Backend Engineer",
                "city": "Tunis",
                "country": "Tunisia",
            },
            # Late due to high engagement (>= 100 likes)
            {
                "id": "post_late_viral",
                "company": "Vermeg",
                "poster_name": "Moussa Diop",
                "poster_title": "CTO",
                "poster_email": "moussa@vermeg.example",
                "text": "We are rapidly expanding our core banking team in Sfax! Looking for 10 backend engineers.",
                "likes": 185,
                "date": (now - timedelta(hours=10)).isoformat(),
                "role": "Backend Engineer",
                "city": "Sfax",
                "country": "Tunisia",
            },
        ]


class MockContactProvider:
    """Mock contact provider returning people by company size."""
    def __init__(self):
        # 12 people across 3 company sizes
        self.directory = {
            # Under 30 employees: StartupAlpha (size: 15) -> Founder/CEO + poster
            "startupalpha": [
                {"name": "Alice Founder", "title": "Founder & CEO", "email": "alice@startupalpha.com", "label": "Found"},
                {"name": "Bob Poster", "title": "Head of Product & Poster", "email": "bob@startupalpha.com", "label": "Found"},
                {"name": "Charlie Dev", "title": "Lead Developer", "email": "charlie@startupalpha.com", "label": "Pattern"},
                {"name": "Danielle Ops", "title": "Operations Manager", "email": "danielle@startupalpha.com", "label": "Guess"},
            ],
            # 30 to 200 employees: MidTech (size: 95) -> Head of function, team lead, poster
            "midtech": [
                {"name": "Frank Head", "title": "VP of Engineering", "email": "frank@midtech.com", "label": "Found"},
                {"name": "Grace Lead", "title": "Backend Team Lead", "email": "grace@midtech.com", "label": "Found"},
                {"name": "Henry Poster", "title": "Senior Engineer & Poster", "email": "henry@midtech.com", "label": "Found"},
                {"name": "CEO Gary", "title": "CEO", "email": "gary@midtech.com", "label": "Found"},  # Should NOT be chosen for > 30
            ],
            # Over 200 employees: EnterpriseGiant (size: 500) -> Team lead/hiring manager + recruiter for process. Never CEO!
            "enterprisegiant": [
                {"name": "Ivan Manager", "title": "Engineering Manager", "email": "ivan@enterprisegiant.com", "label": "Found"},
                {"name": "Julia Recruiter", "title": "Technical Recruiter", "email": "julia@enterprisegiant.com", "label": "Found"},
                {"name": "Kevin Lead", "title": "Staff Backend Lead", "email": "kevin@enterprisegiant.com", "label": "Pattern"},
                {"name": "Big Boss CEO", "title": "Chief Executive Officer", "email": "boss@enterprisegiant.com", "label": "Found"}, # Never CEO!
            ],
        }

    def get_contacts_for_company(self, company_name: str, company_size: int = 25) -> list[dict]:
        key = company_name.lower().replace(" ", "").replace("-", "")
        candidates = self.directory.get(key, [])
        if not candidates:
            # Fallback mock contacts
            return [
                {"name": "General Contact", "title": "Hiring Manager", "email": f"hiring@{key}.example", "label": "Guess"}
            ]

        # Apply company size rules:
        if company_size < 30:
            # Founder or CEO plus poster
            selected = [c for c in candidates if "CEO" in c["title"] or "Founder" in c["title"] or "Poster" in c["title"]]
        elif company_size <= 200:
            # Head of function, team lead, poster (NEVER CEO)
            selected = [c for c in candidates if "CEO" not in c["title"] and ("VP" in c["title"] or "Head" in c["title"] or "Lead" in c["title"] or "Poster" in c["title"])]
        else:
            # Over 200: team lead or hiring manager, recruiter for process only. Never CEO!
            selected = [c for c in candidates if "CEO" not in c["title"] and ("Manager" in c["title"] or "Recruiter" in c["title"] or "Lead" in c["title"])]

        # Max 3 people
        return selected[:3]


class MockGmailAPI:
    """Mock Gmail API enforcing minimum read-only scope and ledger thread filtering."""
    def __init__(self):
        self.scope = "https://www.googleapis.com/auth/gmail.readonly"
        self.token = "mock-gmail-local-token-xyz"
        self.revoked = False
        self.threads = [
            {
                "id": "thread_1",
                "contact_email": "karim@instadeep.example",
                "subject": "Re: Application - Backend Engineer",
                "messages": [
                    {"from": "alex.mercer@example.com", "body": "Hi Karim, here is my resume."},
                    {"from": "karim@instadeep.example", "body": "Thanks Alex! We would love to invite you to an initial technical screen call."},
                ],
            },
            {
                "id": "thread_outside_ledger",
                "contact_email": "newsletter@randomnews.com",
                "subject": "Weekly Newsletter",
                "messages": [
                    {"from": "newsletter@randomnews.com", "body": "Your weekly digest is here."}
                ],
            },
        ]

    def get_authorized_scope(self) -> str:
        return self.scope

    def fetch_threads_for_contacts(self, allowed_emails: list[str]) -> list[dict]:
        if self.revoked:
            raise PermissionError("Token has been revoked.")
        allowed_set = {e.lower().strip() for e in allowed_emails}
        return [t for t in self.threads if t["contact_email"].lower() in allowed_set]

    def revoke_token(self) -> bool:
        self.revoked = True
        return True
