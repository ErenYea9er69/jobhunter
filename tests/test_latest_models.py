"""Tests to ensure the latest 2026 frontier models are configured as defaults."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jh import config, db, refit


class TestLatestModels(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._old_db = config.DB_PATH
        self._old_data = config.DATA_DIR
        tmp_path = Path(self._tmp.name)
        config.DATA_DIR = str(tmp_path / "data")
        config.DB_PATH = str(tmp_path / "data" / "state")
        db.init_db()

    def tearDown(self):
        config.DB_PATH = self._old_db
        config.DATA_DIR = self._old_data
        self._tmp.cleanup()

    def test_gemini_latest_default_model(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_gemini_key", "JH_AI_PROVIDER": "gemini"}, clear=False):
            cfg = refit.get_active_ai_config()
            self.assertEqual(cfg["provider"], "gemini")
            self.assertIn("3.8", cfg["model"])
            self.assertNotIn("2.5", cfg["model"])

    def test_openai_latest_default_model(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_openai_key", "JH_AI_PROVIDER": "openai"}, clear=False):
            cfg = refit.get_active_ai_config()
            self.assertEqual(cfg["provider"], "openai")
            self.assertIn("gpt-5", cfg["model"])
            self.assertNotIn("4o", cfg["model"])

    def test_anthropic_latest_default_model(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test_anthropic_key", "JH_AI_PROVIDER": "anthropic"}, clear=False):
            cfg = refit.get_active_ai_config()
            self.assertEqual(cfg["provider"], "anthropic")
            self.assertIn("claude-3-7-sonnet", cfg["model"])


if __name__ == "__main__":
    unittest.main()

