"""Tests for the desktop runner CLI."""
import subprocess
import sys
import unittest
from pathlib import Path


class TestDesktopLauncher(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).resolve().parent.parent
        self.desktop_py = self.root_dir / "desktop.py"

    def test_desktop_file_exists(self):
        self.assertTrue(self.desktop_py.is_file(), "desktop.py must exist in repo root")

    def test_help_flag(self):
        res = subprocess.run(
            [sys.executable, str(self.desktop_py), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--port", res.stdout)
        self.assertIn("--launch-browser", res.stdout)
        self.assertIn("--install-extension", res.stdout)

