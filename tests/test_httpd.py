"""Hermetic offline tests for the HTTP Daemon & REST API handler."""
import io
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from jh.httpd import JobHunterRequestHandler


class FakeServer:
    def __init__(self, ws_dir=None):
        self.ws_dir = ws_dir or Path.cwd()


class TestHttpdHandler(unittest.TestCase):
    def _call(self, method: str, path: str, body: dict = None) -> tuple[int, dict]:
        raw_body = json.dumps(body).encode("utf-8") if body else b""
        rfile = io.BytesIO(raw_body)
        wfile = io.BytesIO()

        # Mock request & server
        handler = JobHunterRequestHandler.__new__(JobHunterRequestHandler)
        handler.rfile = rfile
        handler.wfile = wfile
        handler.server = FakeServer()
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

    def test_extension_status(self):
        status, res = self._call("GET", "/api/extension/status")
        self.assertEqual(status, 200)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "ok")
        self.assertIn("active_profile", res["data"])

    def test_extension_payload(self):
        status, res = self._call("POST", "/api/extension/payload", {"url": "https://boards.greenhouse.io/test/jobs/123"})
        self.assertEqual(status, 200)
        self.assertTrue(res["success"])
        self.assertIn("profile", res["data"])
        self.assertIn("skills", res["data"]["profile"])

    def test_extension_solve(self):
        status, res = self._call(
            "POST",
            "/api/extension/solve",
            {
                "question": "How many years of Python experience do you have?",
                "job": {"title": "Python Engineer", "company": "Acme Corp"},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(res["success"])
        self.assertIn("answer", res["data"])
        self.assertIn("review", res["data"])
        self.assertIn("verdict", res["data"]["review"])

    def test_applications_lifecycle(self):
        app_data = {
            "company": "Stripe",
            "title": "Backend Engineer",
            "status": "applied",
            "url": "https://stripe.com/jobs/999",
            "notes": "Applied via Copilot",
        }
        status, res = self._call("POST", "/api/applications", app_data)
        self.assertEqual(status, 200)
        self.assertTrue(res["success"])
        self.assertIn("application_id", res["data"])

        status, list_res = self._call("GET", "/api/applications")
        self.assertEqual(status, 200)
        self.assertTrue(list_res["success"])
        apps = list_res["data"]["applications"]
        self.assertTrue(any(a["company"] == "Stripe" for a in apps))

    def test_desktop_extension_status(self):
        status, res = self._call("GET", "/api/desktop/extension-status")
        self.assertEqual(status, 200)
        self.assertTrue(res["success"])
        self.assertIn("browsers", res["data"])

    def test_directory_traversal_blocked(self):
        status, res = self._call("GET", "/../../setup.py")
        self.assertEqual(status, 403)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "forbidden")
