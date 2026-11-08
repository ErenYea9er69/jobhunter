"""Tests for auto-provisioning the resumes drop folder and guidance instructions."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from jh import workspace


class TestResumeDropFolder(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ws = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ensure_resumes_dir_creates_folder_and_guide(self):
        resumes_dir, guide_path = workspace.ensure_resumes_dir(self.ws)
        self.assertTrue(resumes_dir.is_dir())
        self.assertTrue(guide_path.is_file())
        self.assertEqual(guide_path.name, "PUT_YOUR_RESUME_HERE.txt")
        content = guide_path.read_text(encoding="utf-8")
        self.assertIn("Word (.docx)", content)
        self.assertIn("PDF (.pdf)", content)
        self.assertIn("Text (.txt", content)

    def test_ensure_resumes_dir_does_not_overwrite_existing(self):
        resumes_dir = self.ws / "resumes"
        resumes_dir.mkdir(parents=True)
        custom_resume = resumes_dir / "my_resume.txt"
        custom_resume.write_text("Custom resume content", encoding="utf-8")

        res_dir, guide_path = workspace.ensure_resumes_dir(self.ws)
        self.assertEqual(res_dir, resumes_dir)
        self.assertTrue(custom_resume.exists())
        self.assertEqual(custom_resume.read_text(encoding="utf-8"), "Custom resume content")

    def test_discover_resumes_reads_resumes_dir_first(self):
        workspace.ensure_resumes_dir(self.ws)
        resume_file = self.ws / "resumes" / "developer_cv.txt"
        resume_file.write_text(
            "John Doe\nExperience:\n5 years Python developer at TechCorp\nSkills: Python, SQLite\nEmail: john@example.com",
            encoding="utf-8",
        )
        found = workspace.discover_resumes(self.ws)
        self.assertTrue(len(found) >= 1)
        self.assertEqual(found[0]["filename"], "developer_cv.txt")


if __name__ == "__main__":
    unittest.main()

