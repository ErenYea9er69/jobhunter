import os
import sys
import unittest

# Ensure repo root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from jh.extension_installer import (
    find_extension_dir,
    detect_chromium_browsers,
    copy_extension_path_to_clipboard,
    get_extension_status,
)


class TestExtensionInstaller(unittest.TestCase):
    def test_find_extension_dir(self):
        ext_dir = find_extension_dir()
        self.assertTrue(os.path.isdir(ext_dir), f"Directory does not exist: {ext_dir}")
        manifest_path = os.path.join(ext_dir, "manifest.json")
        self.assertTrue(os.path.isfile(manifest_path), f"Manifest missing at: {manifest_path}")

    def test_detect_chromium_browsers(self):
        browsers = detect_chromium_browsers()
        self.assertIsInstance(browsers, list)
        if sys.platform == "win32":
            # On standard Windows systems, at least Edge or Chrome is installed
            self.assertGreaterEqual(len(browsers), 1)
            first = browsers[0]
            self.assertIn("name", first)
            self.assertIn("path", first)
            self.assertIn("type", first)
            self.assertTrue(os.path.isfile(first["path"]))

    def test_get_extension_status(self):
        status = get_extension_status()
        self.assertTrue(status.get("success"))
        self.assertTrue(status.get("extension_dir_valid"))
        self.assertIn("browsers", status)
        self.assertIn("version", status)


if __name__ == "__main__":
    unittest.main()
