"""Phase B1 verification tests: workspace isolation, get_home(), and zero repo pollution."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jh import home, config


class TestWorkspaceIsolationPhaseB1(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tmp = Path(self.temp_dir)
        self.fake_home = self.tmp / "user_home"
        self.fake_home.mkdir()
        self.fake_desktop = self.fake_home / "Desktop"
        self.fake_desktop.mkdir()
        self.empty_repo = self.tmp / "empty_user_repo"
        self.empty_repo.mkdir()

        # Reset session state in home module
        home._HOME_CREATED_IN_SESSION = False
        home._FIRST_NOTICE_GIVEN = False
        home._INITIALIZED = False

    def tearDown(self):
        import gc
        gc.collect()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_home_env_override(self):
        custom = self.tmp / "custom_jobmcp_home"
        with patch.dict(os.environ, {"JOBMCP_HOME": str(custom)}):
            resolved = home.get_home()
            self.assertEqual(resolved, custom.resolve())

    def test_get_home_config_json_lookup(self):
        dot_dir = self.fake_home / ".jobmcp"
        dot_dir.mkdir()
        cfg_file = dot_dir / "config.json"
        target_path = self.tmp / "configured_home"
        cfg_file.write_text(json.dumps({"home": str(target_path)}), encoding="utf-8")

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("JOBMCP_HOME", None)
            with patch("pathlib.Path.home", return_value=self.fake_home):
                resolved = home.get_home()
                self.assertEqual(resolved, target_path.resolve())

    def test_get_home_default_desktop_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("JOBMCP_HOME", None)
            with patch("pathlib.Path.home", return_value=self.fake_home), \
                 patch("jh.home.get_desktop_dir", return_value=self.fake_desktop):
                resolved = home.get_home()
                expected = (self.fake_desktop / "jobmcp").resolve()
                self.assertEqual(resolved, expected)

    def test_no_dirs_created_at_import_or_install_time(self):
        target = self.tmp / "test_fresh_home"
        with patch.dict(os.environ, {"JOBMCP_HOME": str(target)}):
            # Inspecting get_home does not create directory
            h = home.get_home()
            self.assertEqual(h, target.resolve())
            self.assertFalse(target.exists())
            self.assertFalse(home.was_created_now())

    def test_ensure_home_dirs_provisions_all_folders_on_first_tool_call(self):
        target = self.tmp / "test_prov_home"
        with patch.dict(os.environ, {"JOBMCP_HOME": str(target)}):
            self.assertFalse(target.exists())
            home.ensure_home_dirs()

            self.assertTrue(target.exists())
            self.assertTrue((target / "data").is_dir())
            self.assertTrue((target / "resumes").is_dir())
            self.assertTrue((target / "outputs").is_dir())
            self.assertTrue((target / "logs").is_dir())
            self.assertTrue((target / "run").is_dir())
            self.assertTrue((target / "config.json").is_file())
            self.assertTrue(home.was_created_now())

            notice = home.get_first_reply_notice()
            self.assertIsNotNone(notice)
            self.assertIn("I created Desktop/jobmcp. Everything I store goes there. I will not write to your project.", notice)
            self.assertIn(str(target.resolve()), notice)

            # Second call to get notice returns None (one-time notification)
            self.assertIsNone(home.get_first_reply_notice())

    def test_empty_repo_holds_zero_new_files_after_session(self):
        target_home = self.tmp / "isolated_home"
        old_cwd = os.getcwd()
        old_env = dict(os.environ)

        try:
            os.chdir(str(self.empty_repo))
            os.environ["JOBMCP_HOME"] = str(target_home)
            os.environ.pop("JH_DATA_DIR", None)
            os.environ.pop("JH_WORKSPACE", None)

            # Ensure repo starts empty
            files_before = list(self.empty_repo.rglob("*"))
            self.assertEqual(files_before, [])

            # Simulate MCP server startup and execution in this repo
            import mcp_server
            from jh import mcp_tools, mcp_helpers

            server = mcp_server.create_server(ws_path=str(self.empty_repo), surface="full")
            self.assertIsNotNone(server)

            # Invoke a tool function
            tool_fn = mcp_helpers.make_tool_decorator(server)
            @tool_fn
            def sample_tool():
                return {"status": "ok", "message": "done"}

            res = sample_tool()
            self.assertEqual(res["status"], "ok")

            # Assert repo holds ZERO new files
            files_after = list(self.empty_repo.rglob("*"))
            self.assertEqual(files_after, [], f"Repo was polluted with files: {files_after}")

            # Assert everything went into target_home
            self.assertTrue(target_home.exists())
            self.assertTrue((target_home / "data").exists())
            self.assertTrue((target_home / "resumes").exists())
            self.assertTrue((target_home / "outputs").exists())
        finally:
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)

    def test_legacy_repo_local_data_check(self):
        legacy_repo = self.tmp / "legacy_repo"
        legacy_repo.mkdir()
        (legacy_repo / "data").mkdir()
        (legacy_repo / "data" / "engine.db").write_text("dummy", encoding="utf-8")

        found = home.check_legacy_local_data(legacy_repo)
        self.assertEqual(len(found), 1)
        self.assertIn("engine.db", found[0])
