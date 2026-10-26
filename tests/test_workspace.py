"""Unit tests for workspace scanner and resume discovery."""

import os
import tempfile
import unittest
from pathlib import Path

from jh import workspace


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ensure_jobhunter_dir(self):
        jh_dir = workspace.ensure_jobhunter_dir(self.ws_path)
        self.assertTrue(jh_dir.is_dir())
        self.assertTrue((jh_dir / "cache").is_dir())
        self.assertTrue((jh_dir / "output" / "tailored").is_dir())
        self.assertTrue((jh_dir / "output" / "cover-letters").is_dir())
        self.assertTrue((jh_dir / "output" / "reports").is_dir())
        self.assertTrue((jh_dir / ".gitignore").is_file())

    def test_discover_resumes_empty(self):
        resumes = workspace.discover_resumes(self.ws_path)
        self.assertEqual(resumes, [])

    def test_discover_resumes_in_resumes_folder_and_root(self):
        # Create resumes/ folder with backend.docx and frontend.pdf
        resumes_dir = self.ws_path / "resumes"
        resumes_dir.mkdir()
        (resumes_dir / "backend-engineer.pdf").write_bytes(b"%PDF-1.4 dummy")
        (resumes_dir / "data-engineer.docx").write_bytes(b"PK dummy")

        # Create root resume file
        (self.ws_path / "my_cv.pdf").write_bytes(b"%PDF-1.4 dummy")

        # Create non-resume files that should be ignored
        (self.ws_path / "README.md").write_text("# Project", encoding="utf-8")
        (self.ws_path / "requirements.txt").write_text("mcp>=1.0", encoding="utf-8")

        resumes = workspace.discover_resumes(self.ws_path)
        self.assertEqual(len(resumes), 3)

        names = [r["name"] for r in resumes]
        self.assertIn("Backend Engineer", names)
        self.assertIn("Data Engineer", names)
        self.assertIn("My CV", names)

    def test_parse_resume_variant(self):
        resume_content = """John Doe
john.doe@example.com | 555-123-4567 | San Francisco, CA | linkedin.com/in/johndoe | github.com/johndoe

SUMMARY
Experienced Senior Software Engineer with 8 years building scalable distributed backend systems in Python, Go, and PostgreSQL.

EXPERIENCE
Senior Software Engineer | Acme Corp | 2021 - Present
- Architected high-throughput microservices handling 50k RPS.
- Mentored junior engineers and led system design reviews.

Software Engineer | Beta LLC | 2018 - 2021
- Developed REST APIs and data ingestion pipelines using Python, FastAPI, and Redis.

EDUCATION
BS in Computer Science | University of California, Berkeley | 2018

SKILLS
Python, Go, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, AWS, Microservices
"""
        resume_file = self.ws_path / "senior-backend-engineer.txt"
        resume_file.write_text(resume_content, encoding="utf-8")

        profile = workspace.parse_resume_variant(resume_file)
        self.assertIn("name", profile)
        self.assertEqual(profile["name"], "John Doe")
        self.assertEqual(profile["_variant_name"], "Senior Backend Engineer")
        self.assertEqual(profile["_source_file"], str(resume_file.resolve()))
        self.assertTrue(len(profile.get("skills", [])) >= 3)
        self.assertIn("_report", profile)


if __name__ == "__main__":
    unittest.main()
