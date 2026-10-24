import os
import subprocess
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestDesktopCli(unittest.TestCase):
    def test_help_flag(self):
        res = subprocess.run(
            [sys.executable, os.path.join(BASE_DIR, "desktop.py"), "--help"],
            capture_output=True,
            text=True,
            cwd=BASE_DIR,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--launch-browser", res.stdout)
        self.assertIn("--install-extension", res.stdout)


if __name__ == "__main__":
    unittest.main()
