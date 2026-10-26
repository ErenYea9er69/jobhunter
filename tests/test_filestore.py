"""Unit tests for FileStore persistence in .jobhunter/."""

import tempfile
import time
import unittest
from pathlib import Path

from jh.filestore import FileStore


class TestFileStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.jh_dir = Path(self.temp_dir.name) / ".jobhunter"
        self.store = FileStore(self.jh_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_config_roundtrip(self):
        self.assertEqual(self.store.load_config(), {})
        self.store.save_config("active_resume", "Backend Engineer")
        self.assertEqual(self.store.get_active_resume(), "Backend Engineer")

        self.store.save_config({"min_salary": 120000, "work_mode": "Remote"})
        cfg = self.store.load_config()
        self.assertEqual(cfg.get("active_resume"), "Backend Engineer")
        self.assertEqual(cfg.get("min_salary"), 120000)
        self.assertEqual(cfg.get("work_mode"), "Remote")

    def test_application_lifecycle(self):
        self.assertEqual(self.store.load_applications(), [])

        app = {
            "id": "app-123",
            "company": "Stripe",
            "title": "Senior Backend Engineer",
            "status": "applied",
            "url": "https://stripe.com/jobs/123",
            "notes": "Referral from Alice",
        }
        saved = self.store.save_application(app)
        self.assertEqual(saved["id"], "app-123")
        self.assertEqual(len(saved["history"]), 1)
        self.assertEqual(saved["history"][0]["status"], "applied")

        loaded = self.store.load_applications()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["company"], "Stripe")

        # Update application status
        updated = self.store.update_application("app-123", {"status": "interview", "notes": "Technical screen scheduled"})
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "interview")
        self.assertEqual(len(updated["history"]), 2)
        self.assertEqual(updated["history"][1]["status"], "interview")

        # Verify persistence
        reloaded = self.store.load_applications()
        self.assertEqual(reloaded[0]["status"], "interview")
        self.assertEqual(len(reloaded[0]["history"]), 2)

    def test_jobs_cache_with_ttl(self):
        sample_jobs = [{"id": "job1", "title": "Python Dev", "company": "Acme"}]
        self.store.cache_jobs(sample_jobs, query_key="python_remote")

        # Immediate fetch should succeed
        cached = self.store.get_cached_jobs("python_remote", max_age_seconds=60)
        self.assertIsNotNone(cached)
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0]["title"], "Python Dev")

        # Expired max_age should return None
        expired = self.store.get_cached_jobs("python_remote", max_age_seconds=0)
        self.assertIsNone(expired)

        # get_latest_cached_jobs
        latest = self.store.get_latest_cached_jobs()
        self.assertEqual(len(latest), 1)

    def test_save_output_json_and_text(self):
        json_data = {"tailored_title": "Staff Engineer", "score": 95}
        json_path = self.store.save_output("tailored", "stripe-staff.json", json_data)
        self.assertTrue(Path(json_path).is_file())
        self.assertTrue(json_path.endswith("stripe-staff.json"))

        text_content = "Dear Hiring Manager,\n\nI am writing to express my interest..."
        letter_path = self.store.save_output("cover-letters", "stripe-letter.txt", text_content)
        self.assertTrue(Path(letter_path).is_file())
        self.assertEqual(Path(letter_path).read_text(encoding="utf-8"), text_content)

    def test_watchlist_lifecycle(self):
        self.assertEqual(self.store.load_watchlist(), [])

        # Add company
        entry = self.store.add_to_watchlist("Stripe", board_url="https://stripe.com/jobs", notes="Target tier 1")
        self.assertEqual(entry["company"], "Stripe")
        self.assertEqual(entry["board_url"], "https://stripe.com/jobs")

        # Load watchlist
        wl = self.store.load_watchlist()
        self.assertEqual(len(wl), 1)
        self.assertEqual(wl[0]["company"], "Stripe")

        # Update company
        updated = self.store.add_to_watchlist("Stripe", notes="Updated notes")
        self.assertEqual(updated["notes"], "Updated notes")
        self.assertEqual(len(self.store.load_watchlist()), 1)

        # Remove company
        removed = self.store.remove_from_watchlist("Stripe")
        self.assertTrue(removed)
        self.assertEqual(len(self.store.load_watchlist()), 0)

        # Remove nonexistent returns False
        self.assertFalse(self.store.remove_from_watchlist("Nonexistent"))

    def test_export_and_list_deletable(self):
        self.store.save_config("theme", "dark")
        self.store.add_to_watchlist("Datadog")
        self.store.save_output("reports", "fit_report.json", {"score": 90})

        export = self.store.export_all_data()
        self.assertIn("config", export)
        self.assertIn("watchlist", export)
        self.assertIn("generated_outputs", export)
        self.assertEqual(export["config"].get("theme"), "dark")

        deletable = self.store.list_deletable_files()
        self.assertTrue(len(deletable) >= 2)
        types = [d["type"] for d in deletable]
        self.assertIn("durable_data", types)


if __name__ == "__main__":
    unittest.main()
