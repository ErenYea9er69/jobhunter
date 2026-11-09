import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from jh import config, db, preferences
from jh.httpd import JobHunterRequestHandler

class FakeServer:
    def __init__(self, ws_dir=None):
        self.ws_dir = ws_dir or Path.cwd()

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

    def _call(self, method: str, path: str, body: dict = None) -> tuple[int, dict]:
        raw_body = json.dumps(body).encode("utf-8") if body else b""
        handler = JobHunterRequestHandler.__new__(JobHunterRequestHandler)
        handler.rfile = io.BytesIO(raw_body)
        handler.wfile = io.BytesIO()
        handler.server = FakeServer(self.ws)
        handler.path = path
        handler.command = method
        handler.headers = {
            "Content-Length": str(len(raw_body)),
            "Content-Type": "application/json",
        }
        handler.close_connection = True
        status_code = [200]
        handler.send_response = lambda code, message=None: status_code.__setitem__(0, code)
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None

        if method == "GET":
            handler.do_GET()
        else:
            handler.do_POST()

        out = handler.wfile.getvalue().decode("utf-8")
        parsed = json.loads(out) if out else {}
        return status_code[0], parsed

    def test_home_cities_alias_and_autofill_fields(self):
        updates = {
            "home_cities": ["Tunis", "Sousse"],
            "work_authorized": "yes",
            "notice_period": "1month",
            "submission_mode": "review",
            "needs_visa_sponsorship": False,
        }
        clean, warnings = preferences.validate(updates)
        self.assertEqual(clean.get("cities"), ["Tunis", "Sousse"])
        self.assertEqual(clean.get("home_cities"), ["Tunis", "Sousse"])
        self.assertEqual(clean.get("work_authorized"), "yes")
        self.assertEqual(clean.get("notice_period"), "1month")
        self.assertEqual(clean.get("submission_mode"), "review")

    def test_httpd_preferences_post_and_get_contract(self):
        # 1. POST updates
        updates = {
            "home_cities": ["Tunis"],
            "work_authorized": "yes",
            "notice_period": "immediate",
            "submission_mode": "review",
            "needs_visa_sponsorship": True,
        }
        status, res = self._call("POST", "/api/preferences", {"updates": updates})
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))

        # 2. GET preferences
        status, res = self._call("GET", "/api/preferences")
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        data = res.get("data", {})
        # Verify flat access for webapp and extension
        self.assertEqual(data.get("home_cities"), ["Tunis"])
        self.assertEqual(data.get("cities"), ["Tunis"])
        self.assertEqual(data.get("work_authorized"), "yes")
        self.assertEqual(data.get("notice_period"), "immediate")
        self.assertEqual(data.get("submission_mode"), "review")
        self.assertTrue(data.get("needs_visa_sponsorship"))
        # Verify nested preferences key for backward compatibility
        self.assertIn("preferences", data)
        self.assertEqual(data["preferences"].get("work_authorized"), "yes")
