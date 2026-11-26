"""Tests for preferences validation and home_cities alias without HTTP server."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from jh import config, db, preferences


class TestPreferencesAutofillAndCities(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ws = Path(self.temp_dir)
        self.jh_dir = self.ws / ".jobhunter"
        self.jh_dir.mkdir(parents=True)
        os.environ["JH_DATA_DIR"] = str(self.jh_dir)
        config.DATA_DIR = str(self.jh_dir)
        db.init_db()

    def tearDown(self):
        os.environ.pop("JH_DATA_DIR", None)
        import gc
        gc.collect()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_home_cities_alias_and_autofill_fields(self):
        updates = {
            "home_cities": ["Tunis", "Sousse"],
            "work_authorized": "yes",
            "notice_period": "1month",
            "submission_mode": "review",
            "needs_visa_sponsorship": False,
        }
        clean, _warnings = preferences.validate(updates)
        self.assertEqual(clean.get("cities"), ["Tunis", "Sousse"])
        self.assertEqual(clean.get("home_cities"), ["Tunis", "Sousse"])
        self.assertEqual(clean.get("work_authorized"), "yes")
        self.assertEqual(clean.get("notice_period"), "1month")
        self.assertEqual(clean.get("submission_mode"), "review")


if __name__ == "__main__":
    unittest.main()
