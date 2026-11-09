import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from jh import db
from jh.httpd import JobHunterRequestHandler
from jh.resume_registry import ResumeRegistry

class FakeServer:
    def __init__(self, ws_dir=None):
        self.ws_dir = ws_dir or Path.cwd()

class TestProfilesApiSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ws = Path(self.temp_dir)
        self.jh_dir = self.ws / ".jobhunter"
        self.jh_dir.mkdir(parents=True)
        os.environ["JH_DATA_DIR"] = str(self.jh_dir)
        db.init_db()

        # Seed sample profile
        sample_profile = {
            "name": "Jane Doe",
            "target_title": "Full Stack Engineer",
            "email": "jane@example.com",
            "phone": "+1 555-0199",
            "location": "New York, NY",
            "linkedin": "https://linkedin.com/in/janedoe",
            "github": "https://github.com/janedoe",
            "website": "https://janedoe.me",
            "skills": ["Python", "FastAPI", "React", "PostgreSQL"],
            "experience": [
                {
                    "title": "Senior Engineer",
                    "company": "Tech Corp",
                    "period": "2021 to now",
                    "summary": "Built core services.",
                }
            ],
            "years_of_experience": 5,
        }
        db.save_profile(sample_profile, profile_id="var_fullstack")

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

    def test_list_resume_profiles_contains_full_fields(self):
        profiles = db.list_resume_profiles()
        self.assertTrue(len(profiles) > 0)
        p = next(x for x in profiles if x["id"] == "var_fullstack")
        self.assertIn("skills", p)
        self.assertEqual(p["skills"], ["Python", "FastAPI", "React", "PostgreSQL"])
        self.assertIn("experience", p)
        self.assertEqual(p["email"], "jane@example.com")
        self.assertEqual(p["phone"], "+1 555-0199")
        self.assertEqual(p["experience_years"], 5)

    def test_httpd_profiles_get_and_activate(self):
        # Create second profile to test activation
        sample2 = {
            "name": "Jane Doe",
            "target_title": "Data Engineer",
            "skills": ["Python", "SQL", "Spark"],
            "experience": [],
        }
        db.save_profile(sample2, profile_id="var_data")

        # GET /api/profiles
        status, res = self._call("GET", "/api/profiles")
        self.assertEqual(status, 200)
        data = res.get("data", {})
        self.assertIn("active", data)
        self.assertIn("active_profile", data)
        self.assertTrue(len(data.get("profiles", [])) >= 2)

        # POST /api/profile/activate with id
        status, act_res = self._call("POST", "/api/profile/activate", {"id": "var_data"})
        self.assertEqual(status, 200)
        self.assertTrue(act_res.get("success"))

        # Check DB shows active
        profs = db.list_resume_profiles()
        active_p = next(x for x in profs if x["is_active"])
        self.assertEqual(active_p["id"], "var_data")
