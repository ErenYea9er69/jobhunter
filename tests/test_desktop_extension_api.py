import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from jh import httpd


class TestDesktopExtensionApi(unittest.TestCase):
    def test_extension_status_route_exists(self):
        handler = httpd.ROUTES.get(("GET", "/api/desktop/extension-status"))
        self.assertIsNotNone(handler, "Route GET /api/desktop/extension-status must be registered")
        res = handler({}, {})
        self.assertTrue(res.get("success"))
        self.assertIn("browsers", res)
        self.assertIn("extension_dir", res)

    def test_launch_browser_route_exists(self):
        handler = httpd.ROUTES.get(("POST", "/api/desktop/launch-browser-extension"))
        self.assertIsNotNone(handler, "Route POST /api/desktop/launch-browser-extension must be registered")

    def test_open_extension_folder_route_exists(self):
        handler = httpd.ROUTES.get(("POST", "/api/desktop/open-extension-folder"))
        self.assertIsNotNone(handler, "Route POST /api/desktop/open-extension-folder must be registered")


if __name__ == "__main__":
    unittest.main()
