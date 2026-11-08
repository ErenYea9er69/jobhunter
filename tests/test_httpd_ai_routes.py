"""Tests for httpd /api/ai/* endpoints."""
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jh import ai_manager, config, db
from jh.httpd import JobHunterRequestHandler


class FakeServer:
    def __init__(self, ws_dir=None):
        self.ws_dir = ws_dir or Path.cwd()


class TestHttpdAIRoutes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ws = Path(self.temp_dir)
        self.jh_dir = self.ws / ".jobhunter"
        self.jh_dir.mkdir(parents=True)
        os.environ["JH_DATA_DIR"] = str(self.jh_dir)

        # Clear environment keys
        self.env_patcher = patch.dict(os.environ, {
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GROQ_API_KEY": "",
            "DEEPSEEK_API_KEY": "",
            "MISTRAL_API_KEY": "",
            "JH_AI_PROVIDER": "deterministic",
        }, clear=False)
        self.env_patcher.start()
        self.orig_groq = config.GROQ_API_KEY
        config.GROQ_API_KEY = ""

        db.init_db()

    def tearDown(self):
        self.env_patcher.stop()
        config.GROQ_API_KEY = self.orig_groq
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

        wfile.seek(0)
        output = wfile.read()
        parsed_json = json.loads(output.decode("utf-8")) if output else {}
        return status_code[0], parsed_json

    def test_get_ai_status(self):
        status, res = self._call("GET", "/api/ai/status")
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "ok")
        data = res["data"]
        self.assertIn("mode", data)
        self.assertIn("recommended_models", data)

    def test_post_ai_config_and_clear_key(self):
        # Configure Gemini key
        status, res = self._call("POST", "/api/ai/config", {
            "provider": "gemini",
            "api_key": "AIzaSyTestKey12345678",
            "model": "gemini-3.8-flash",
        })
        self.assertEqual(status, 200)
        self.assertTrue(res["data"]["success"])
        self.assertEqual(res["data"]["mode"], "direct_api")

        # Check status reflects direct_api
        s_status, s_res = self._call("GET", "/api/ai/status")
        self.assertEqual(s_res["data"]["mode"], "direct_api")
        self.assertTrue(s_res["data"]["key_configured"])

        # Clear key
        c_status, c_res = self._call("POST", "/api/ai/clear-key", {"provider": "gemini"})
        self.assertEqual(c_status, 200)
        self.assertTrue(c_res["data"]["success"])

        # Verify reverted to mcp_client
        s2_status, s2_res = self._call("GET", "/api/ai/status")
        self.assertFalse(s2_res["data"]["key_configured"])
        self.assertEqual(s2_res["data"]["mode"], "mcp_client")


if __name__ == "__main__":
    unittest.main()

