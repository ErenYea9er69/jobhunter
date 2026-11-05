"""Tests verifying the structure and integrity of the Web Dashboard assets in public/."""
import unittest
from pathlib import Path


class TestFrontendAssets(unittest.TestCase):
    def setUp(self):
        self.pub_dir = Path(__file__).resolve().parent.parent / "public"

    def test_dashboard_files_exist(self):
        required_files = ["index.html", "styles.css", "app.js"]
        for f in required_files:
            target = self.pub_dir / f
            self.assertTrue(target.is_file(), f"Expected {f} to exist in public/")
            self.assertGreater(target.stat().st_size, 50, f"{f} must not be empty")

    def test_html_contains_five_tabs(self):
        index_file = self.pub_dir / "index.html"
        self.assertTrue(index_file.is_file())
        html = index_file.read_text(encoding="utf-8")

        # Verify 5 tabs are present
        self.assertIn("tab-radar", html)
        self.assertIn("tab-profiles", html)
        self.assertIn("tab-tracker", html)
        self.assertIn("tab-copilot", html)
        self.assertIn("tab-extension", html)

