"""Tests for Chromium browser detection and extension auto-launcher."""
import os
import sys
import unittest
from pathlib import Path

from jh.extension_installer import (
    find_extension_dir,
    find_manifest,
    detect_chromium_browsers,
    get_extension_status,
)


class TestExtensionInstaller(unittest.TestCase):
    def test_find_extension_dir_resolves_path(self):
        ext_dir = find_extension_dir()
        self.assertTrue(isinstance(ext_dir, str))
        self.assertTrue(len(ext_dir) > 0)
        # Should point towards an extension directory
        self.assertTrue(ext_dir.lower().endswith("extension"))

    def test_detect_chromium_browsers(self):
        browsers = detect_chromium_browsers()
        self.assertIsInstance(browsers, list)
        if sys.platform == "win32":
            # On standard Windows environments, Edge is built-in
            self.assertTrue(len(browsers) >= 1)
            self.assertTrue(any(b["type"] in ("chrome", "edge", "brave") for b in browsers))
            for b in browsers:
                self.assertIn("name", b)
                self.assertIn("path", b)
                self.assertTrue(os.path.isfile(b["path"]))

    def test_get_extension_status_structure(self):
        status = get_extension_status()
        self.assertTrue(status["success"])
        self.assertIn("extension_dir", status)
        self.assertIn("browsers", status)
        self.assertIn("extension_dir_valid", status)

