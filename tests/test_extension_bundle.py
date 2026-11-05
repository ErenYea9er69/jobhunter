"""Tests verifying the integrity of the Chrome Extension Manifest V3 bundle."""
import json
import unittest
from pathlib import Path


class TestExtensionBundle(unittest.TestCase):
    def setUp(self):
        self.ext_dir = Path(__file__).resolve().parent.parent / "extension"

    def test_manifest_v3_structure(self):
        manifest_file = self.ext_dir / "manifest.json"
        self.assertTrue(manifest_file.is_file(), "manifest.json must exist in extension/")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

        self.assertEqual(manifest.get("manifest_version"), 3)
        self.assertIn("permissions", manifest)
        self.assertIn("activeTab", manifest["permissions"])
        self.assertIn("storage", manifest["permissions"])
        self.assertIn("action", manifest)
        self.assertEqual(manifest["action"].get("default_popup"), "popup.html")

    def test_referenced_files_exist(self):
        required_files = [
            "manifest.json",
            "content.js",
            "background.js",
            "flyout.css",
            "popup.html",
            "popup.js",
        ]
        for fname in required_files:
            file_path = self.ext_dir / fname
            self.assertTrue(file_path.is_file(), f"File '{fname}' missing from extension/")
