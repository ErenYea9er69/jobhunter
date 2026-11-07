"""Tests for job-specific tailored resume and AI cover letter package generation."""

import unittest
from unittest.mock import patch

from jh import db, exporters, mcp_helpers as h, refit
from jh.team import qa


class TestJobPackage(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_job_package_generation(self):
        target_job = {
            "title": "Senior Distributed Backend Engineer",
            "company": "Scale AI",
            "description": "Looking for an engineer experienced in Python, distributed systems, high throughput APIs, and latency optimization.",
        }

        profile = h.resolve_profile(require=False) or {
            "name": "Alex Candidate",
            "target_title": "Backend Engineer",
            "skills": ["Python", "PostgreSQL", "Docker", "REST APIs", "Distributed Systems"],
            "experience": [
                {
                    "company": "Previous Tech",
                    "role": "Software Engineer",
                    "bullets": [
                        "Architected distributed pipeline processing 20M events per day using Python and Redis.",
                        "Reduced API latency by 35% through query optimization and caching.",
                    ],
                }
            ],
        }

        # 1. Custom Resume Generation
        custom_resume = refit.generate_custom_resume(target_job, profile, archetype="startup_velocity")
        self.assertIn("tailored_resume", custom_resume)
        self.assertIn("recruiter_6sec_audit", custom_resume)
        self.assertGreaterEqual(custom_resume["recruiter_6sec_audit"]["ats_keyword_match_pct"], 50)
        self.assertIn("Scale AI", custom_resume["company"])

        # 2. Exporter Validation
        res_dict = custom_resume["tailored_resume"]
        txt_out = exporters.to_txt(res_dict)
        html_out = exporters.to_html(res_dict)

        self.assertIn("PROFESSIONAL EXPERIENCE", txt_out)
        self.assertIn("<!DOCTYPE html>", html_out)

        # 3. Cover Pitch & QA Verification
        pitch = refit.generate_cover_pitch(target_job, profile)
        full_letter = pitch.get("full_text") or ""
        self.assertGreater(len(full_letter.split()), 50)

        review = qa.review_document(full_letter, kind="cover_letter", profile=profile, job=target_job)
        self.assertIn(review.verdict.lower(), ("pass", "warn"))


if __name__ == "__main__":
    unittest.main()
