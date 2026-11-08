"""Tests to ensure the latest 2026 frontier models are configured as defaults."""
import os
import unittest
from unittest.mock import patch

from jh import refit


class TestLatestModels(unittest.TestCase):
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

