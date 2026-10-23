"""Regression tests for audit remediation and security hardening."""
import os
import unittest
from unittest.mock import patch, MagicMock

from jh import dedup, httpd, util, autofill


class TestAuditRemediation(unittest.TestCase):
    def test_find_static_file_path_traversal_blocked(self):
        """Verify that directory traversal sequences cannot escape the public static folder."""
        # Attempt to access jobhunter.db or server.py outside public/
        bad_paths = [
            "../../jobhunter.db",
            "../server.py",
            "/../../server.py",
            "..\\..\\server.py",
            "....//....//server.py",
            "/etc/passwd",
            "c:/windows/win.ini",
            "../../data/jobhunter.db",
            "index.html/../../server.py",
        ]
        for bad in bad_paths:
            with self.subTest(bad=bad):
                res = httpd._find_static_file(bad)
                self.assertIsNone(res, f"Path traversal succeeded for: {bad} -> {res}")

    def test_find_static_file_legitimate_assets_allowed(self):
        """Verify legitimate static files still resolve correctly."""
        index_path = httpd._find_static_file("index.html")
        self.assertIsNotNone(index_path)
        self.assertTrue(index_path.endswith("index.html"))
        self.assertTrue(os.path.isfile(index_path))

        css_path = httpd._find_static_file("styles.css")
        self.assertIsNotNone(css_path)
        self.assertTrue(css_path.endswith("styles.css"))
        self.assertTrue(os.path.isfile(css_path))

    def test_http_get_scheme_validation(self):
        """Verify that http_get enforces http and https schemes and blocks file:// or other protocols."""
        with self.assertRaises(util.HttpError) as ctx:
            util.http_get("file:///c:/windows/win.ini")
        self.assertIn("Unsupported URL scheme", str(ctx.exception))

        with self.assertRaises(util.HttpError) as ctx2:
            util.http_get("ftp://ftp.example.com/file")
        self.assertIn("Unsupported URL scheme", str(ctx2.exception))

        with self.assertRaises(util.HttpError) as ctx3:
            util.http_get("javascript:alert(1)")
        self.assertIn("Unsupported URL scheme", str(ctx3.exception))

    def test_autofill_bookmarklet_escaping(self):
        """Verify that user or platform data with special characters is escaped in autofill bookmarklet."""
        payload = {
            "full_name": "<script>alert(1)</script>",
            "email": "test@example.com",
            "detected_platform": "<img src=x onerror=alert(1)>",
            "cover_letter": "Pitch",
        }
        code = autofill.generate_bookmarklet_code(payload)
        # Check that esc function is included in the script
        self.assertIn("function esc(s)", code)
        self.assertIn("cleanPlatform = esc(platform)", code)
        self.assertIn("filledItems.slice(0, 5).map(esc)", code)

    def test_job_key_sha256_format_and_stability(self):
        """Verify that job_key produces a 16-character hex digest and is stable."""
        job = {"title": "Senior Backend Engineer", "company": "Stripe, Inc."}
        k1 = dedup.job_key(job)
        k2 = dedup.job_key(job)
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 16)
        # Verify it's a valid hex string
        int(k1, 16)

        # Different job produces different key
        other = {"title": "Frontend Engineer", "company": "Stripe, Inc."}
        self.assertNotEqual(k1, dedup.job_key(other))


if __name__ == "__main__":
    unittest.main()
