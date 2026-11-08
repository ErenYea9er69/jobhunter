"""Tests for httpd resume upload, folder-info, and scan REST endpoints."""
import base64
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from jh import config, db, workspace
from jh.httpd import JobHunterRequestHandler


class FakeServer:
    def __init__(self, ws_dir=None):
        self.ws_dir = ws_dir or Path.cwd()


class TestHttpdResumeUpload(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ws = Path(self.temp_dir)
        self.jh_dir = self.ws / ".jobhunter"
        self.jh_dir.mkdir(parents=True)
        os.environ["JH_DATA_DIR"] = str(self.jh_dir)
        config.configure_mcp_environment(str(self.ws))
        db.init_db()

    def tearDown(self):
        os.environ.pop("JH_DATA_DIR", None)
        import gc
        gc.collect()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _call(self, method: str, path: str, body: dict = None) -> tuple[int, dict]:
        raw_body = json.dumps(body).encode("utf-8") if body else b""
        rfile = io.BytesIO(raw_body)
        wfile = io.BytesIO()

        handler = JobHunterRequestHandler.__new__(JobHunterRequestHandler)
        handler.rfile = rfile
        handler.wfile = wfile
        handler.server = FakeServer(self.ws)
        handler.path = path
        handler.command = method
        handler.headers = {
            "Content-Length": str(len(raw_body)),
            "Content-Type": "application/json",
        }
        handler.close_connection = True

        status_code = [200]

        def mock_send_response(code, message=None):
            status_code[0] = code

        handler.send_response = mock_send_response
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None

        if method == "GET":
            handler.do_GET()
        elif method == "POST":
            handler.do_POST()
        elif method == "OPTIONS":
            handler.do_OPTIONS()

        wfile.seek(0)
        output = wfile.read()
        parsed_json = json.loads(output.decode("utf-8")) if output else {}
        return status_code[0], parsed_json

    def test_get_resumes_folder_info(self):
        status, res = self._call("GET", "/api/resumes/folder-info")
        self.assertEqual(status, 200)
        self.assertEqual(res.get("status"), "ok")
        data = res.get("data", {})
        self.assertTrue(os.path.isdir(data.get("resumes_dir")))
        self.assertEqual(data.get("file_count"), 0)
        self.assertIn(".docx", data.get("supported_formats"))

    def test_post_resume_upload_text_and_activate(self):
        sample_text = (
            "Alice Smith\n"
            "Email: alice@example.com\n"
            "Phone: +1-555-0199\n"
            "Target: Senior Cloud Engineer\n"
            "Experience:\n"
            "5 years at CloudCo as Senior Systems Architect\n"
            "Skills: Python, Kubernetes, AWS, Terraform, Docker\n"
        )
        b64_content = base64.b64encode(sample_text.encode("utf-8")).decode("ascii")

        status, res = self._call(
            "POST",
            "/api/resumes/upload",
            {
                "filename": "alice_resume.txt",
                "content_base64": b64_content,
                "activate": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(res.get("status"), "ok")
        data = res.get("data", {})
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("profile", {}).get("name"), "Alice Smith")
        self.assertIn("Python", data.get("profile", {}).get("skills", []))

        # Check that file was written to resumes/
        saved_file = self.ws / "resumes" / "alice_resume.txt"
        self.assertTrue(saved_file.exists())

        # Check that profiles endpoint shows it as active
        p_status, profiles_res = self._call("GET", "/api/profiles")
        self.assertEqual(profiles_res.get("data", {}).get("count"), 1)

    def test_post_resume_upload_rejects_unsafe_file(self):
        status, res = self._call(
            "POST",
            "/api/resumes/upload",
            {
                "filename": "../../evil.exe",
                "content_base64": base64.b64encode(b"malicious").decode("ascii"),
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(res.get("status"), "error")

    def test_post_resume_scan_refreshes_variants(self):
        # Manually drop a resume into resumes/
        resumes_dir = self.ws / "resumes"
        resumes_dir.mkdir(parents=True, exist_ok=True)
        cv = resumes_dir / "bob_cv.txt"
        cv.write_text(
            "Bob Jones\nEmail: bob@example.com\nExperience:\nStaff Python Engineer at Acme\nSkills: Python, Go",
            encoding="utf-8",
        )

        status, res = self._call("POST", "/api/resumes/scan", {})
        self.assertEqual(status, 200)
        self.assertEqual(res.get("status"), "ok")
        data = res.get("data", {})
        self.assertTrue(data.get("count") >= 1)


if __name__ == "__main__":
    unittest.main()
