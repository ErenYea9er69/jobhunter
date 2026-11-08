"""Tests for AI Manager lifecycle, key masking, and dynamic provider switching."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from jh import ai_manager, config, db


class TestAIManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ws = Path(self.temp_dir)
        self.jh_dir = self.ws / ".jobhunter"
        self.jh_dir.mkdir(parents=True)
        os.environ["JH_DATA_DIR"] = str(self.jh_dir)

        # Clear any environment API keys for test isolation
        self.env_patcher = patch.dict(os.environ, {
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GROQ_API_KEY": "",
            "DEEPSEEK_API_KEY": "",
            "MISTRAL_API_KEY": "",
            "JH_AI_PROVIDER": "auto",
        }, clear=False)
        self.env_patcher.start()
        self.orig_groq = config.GROQ_API_KEY
        self.orig_gemini = config.GEMINI_API_KEY
        self.orig_openai = config.OPENAI_API_KEY
        config.GROQ_API_KEY = ""
        config.GEMINI_API_KEY = ""
        config.OPENAI_API_KEY = ""

        db.init_db()

    def tearDown(self):
        self.env_patcher.stop()
        config.GROQ_API_KEY = self.orig_groq
        config.GEMINI_API_KEY = self.orig_gemini
        config.OPENAI_API_KEY = self.orig_openai
        os.environ.pop("JH_DATA_DIR", None)
        import gc
        gc.collect()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_mask_api_key(self):
        self.assertEqual(ai_manager.mask_api_key(""), "")
        self.assertEqual(ai_manager.mask_api_key("short"), "••••")
        masked_gemini = ai_manager.mask_api_key("AIzaSyD-1234567890abcdef")
        self.assertTrue(masked_gemini.startswith("AIza"))
        self.assertTrue(masked_gemini.endswith("cdef"))
        self.assertIn("••••", masked_gemini)

        masked_openai = ai_manager.mask_api_key("sk-proj-12345678901234567890")
        self.assertTrue(masked_openai.startswith("sk-proj"))
        self.assertIn("••••", masked_openai)

    def test_get_ai_status_default_mode(self):
        status = ai_manager.get_ai_status()
        self.assertEqual(status["mode"], "mcp_client")
        self.assertFalse(status["key_configured"])
        self.assertIn("gemini-3.8-flash", status["recommended_models"]["gemini"])
        self.assertIn("gpt-5-mini", status["recommended_models"]["openai"])

    def test_set_and_clear_ai_key(self):
        # Set Gemini key
        res = ai_manager.set_ai_key(provider="gemini", api_key="AIzaSyTestKey999988887777", model="gemini-3.8-flash")
        self.assertTrue(res["success"])

        status = ai_manager.get_ai_status()
        self.assertEqual(status["mode"], "direct_api")
        self.assertTrue(status["key_configured"])
        self.assertEqual(status["provider"], "gemini")
        self.assertEqual(status["model"], "gemini-3.8-flash")
        self.assertIn("AIza", status["masked_key"])

        # Clear key and verify dynamic return to MCP mode
        clear_res = ai_manager.clear_ai_key("gemini")
        self.assertTrue(clear_res["success"])

        status_after = ai_manager.get_ai_status()
        self.assertFalse(status_after["key_configured"])
        self.assertEqual(status_after["mode"], "mcp_client")


if __name__ == "__main__":
    unittest.main()
