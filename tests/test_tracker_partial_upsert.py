import os
import shutil
import tempfile
import unittest
from pathlib import Path
from jh import db, tracker

class TestTrackerPartialUpsert(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ws = Path(self.temp_dir)
        self.jh_dir = self.ws / ".jobhunter"
        self.jh_dir.mkdir(parents=True)
        os.environ["JH_DATA_DIR"] = str(self.jh_dir)
        db.init_db()

    def tearDown(self):
        os.environ.pop("JH_DATA_DIR", None)
        import gc
        gc.collect()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_partial_status_update_preserves_application_data(self):
        initial = {
            "title": "Senior Python Engineer",
            "company": "Acme Corp",
            "url": "https://example.com/jobs/1",
            "status": "saved",
            "notes": "Met founder on LinkedIn",
            "location": "Remote",
            "salary": "$150k",
        }
        app_id = tracker.upsert_application(initial)
        self.assertTrue(bool(app_id))

        # Now perform partial update as frontend does when moving card
        tracker.upsert_application({"id": app_id, "status": "queued"})

        apps = tracker.list_applications()
        updated = next(a for a in apps if a["id"] == app_id)
        self.assertEqual(updated["status"], "queued")
        self.assertEqual(updated["title"], "Senior Python Engineer")
        self.assertEqual(updated["company"], "Acme Corp")
        self.assertEqual(updated["url"], "https://example.com/jobs/1")
        self.assertEqual(updated["notes"], "Met founder on LinkedIn")
        self.assertEqual(updated["location"], "Remote")
        self.assertEqual(updated["salary"], "$150k")
