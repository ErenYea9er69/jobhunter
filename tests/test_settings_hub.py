import os
import unittest
from jh import db, httpd, config, tracker

class TestSettingsHub(unittest.TestCase):
    def setUp(self):
        # Ensure fresh state
        self.orig_profile = db.get_profile()

    def test_extended_settings_keys(self):
        """Verify new general and SMTP settings keys can be set and fetched."""
        payload = {
            "theme_mode": "dark",
            "ui_density": "compact",
            "sound_enabled": "1",
            "default_sort": "date",
            "auto_hide_applied": "1",
            "auto_hide_expired": "1",
            "digest_smtp_host": "smtp.example.com",
            "digest_smtp_port": "587",
            "digest_smtp_user": "user@example.com",
            "digest_smtp_pass": "secretpass123",
            "adzuna_app_id": "test-app-id",
            "adzuna_app_key": "test-app-key"
        }
        res = httpd.r_settings({}, payload)
        self.assertTrue(res["success"])
        settings = res["settings"]
        self.assertEqual(settings.get("theme_mode"), "dark")
        self.assertEqual(settings.get("ui_density"), "compact")
        self.assertEqual(settings.get("sound_enabled"), "1")
        self.assertEqual(settings.get("default_sort"), "date")
        self.assertEqual(settings.get("auto_hide_applied"), "1")
        self.assertEqual(settings.get("digest_smtp_host"), "smtp.example.com")
        self.assertEqual(settings.get("adzuna_app_id"), "test-app-id")

    def test_backup_export_and_import(self):
        """Verify backup export generates valid JSON and import restores it correctly."""
        # Setup sample data
        db.set_setting("theme_mode", "system")
        export_data = httpd.r_backup_export({}, {})
        self.assertIn("jobhunter_version", export_data)
        self.assertIn("settings", export_data)
        self.assertIn("profile", export_data)
        self.assertEqual(export_data["settings"].get("theme_mode"), "system")

        # Now test import
        import_payload = {
            "settings": {"theme_mode": "light", "ui_density": "comfortable"},
            "profile": {"name": "Test Candidate", "target_title": "Full Stack Lead", "skills": ["Python", "JavaScript"]},
        }
        import_res = httpd.r_backup_import({}, import_payload)
        self.assertTrue(import_res["success"])

        # Check restored
        refetched_settings = httpd.r_get_settings({}, {})
        self.assertEqual(refetched_settings.get("theme_mode"), "light")
        prof = db.get_profile()
        self.assertEqual(prof.get("name"), "Test Candidate")

    def test_system_info(self):
        """Verify system info endpoint returns diagnostic fields."""
        info = httpd.r_system_info({}, {})
        self.assertIn("version", info)
        self.assertIn("python_version", info)
        self.assertIn("platform", info)
        self.assertIn("db_size_kb", info)
        self.assertIn("stored_jobs_count", info)
        self.assertIn("applications_count", info)
        self.assertIsInstance(info["db_size_kb"], (int, float))

if __name__ == "__main__":
    unittest.main()
