import os
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestBuildArtifacts(unittest.TestCase):
    def test_dist_exe_exists(self):
        dist_exe = os.path.join(BASE_DIR, "dist", "JobHunter", "JobHunter.exe")
        self.assertTrue(os.path.isfile(dist_exe), f"Missing executable: {dist_exe}")

    def test_dist_extension_bundled(self):
        ext_manifest = os.path.join(BASE_DIR, "dist", "JobHunter", "extension", "manifest.json")
        self.assertTrue(os.path.isfile(ext_manifest), f"Missing bundled extension manifest: {ext_manifest}")

    def test_dist_installer_exists(self):
        installer_exe = os.path.join(BASE_DIR, "dist", "JobHunter-Setup.exe")
        self.assertTrue(os.path.isfile(installer_exe), f"Missing setup installer: {installer_exe}")
        size_mb = os.path.getsize(installer_exe) / (1024 * 1024)
        self.assertGreater(size_mb, 15, f"Installer size unexpectedly small: {size_mb} MB")

    def test_dist_zip_exists(self):
        zip_file = os.path.join(BASE_DIR, "dist", "JobHunter-Windows-x64.zip")
        self.assertTrue(os.path.isfile(zip_file), f"Missing distribution zip: {zip_file}")


if __name__ == "__main__":
    unittest.main()
