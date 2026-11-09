"""Tests for workspace isolation, repo auto-detection prevention, and CEO step-by-step mode."""
import os
import tempfile
import unittest
from pathlib import Path

from jh import config, workspace
from jh.team import ceo


class TestWorkspaceIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_unrelated_repo_is_not_jobhunter_workspace(self):
        unrelated = self.tmp_path / "my_react_project"
        unrelated.mkdir()
        (unrelated / "package.json").write_text("{}", encoding="utf-8")
        (unrelated / "src").mkdir()

        self.assertFalse(workspace.is_jobhunter_workspace(unrelated))

    def test_jobhunter_repo_or_workspace_with_indicators(self):
        # 1. Has .jobhunter
        ws1 = self.tmp_path / "ws1"
        ws1.mkdir()
        (ws1 / ".jobhunter").mkdir()
        self.assertTrue(workspace.is_jobhunter_workspace(ws1))

        # 2. Has resumes dir
        ws2 = self.tmp_path / "ws2"
        ws2.mkdir()
        (ws2 / "resumes").mkdir()
        self.assertTrue(workspace.is_jobhunter_workspace(ws2))

        # 3. Base JobHunter repo
        self.assertTrue(workspace.is_jobhunter_workspace(config.BASE_DIR))

    def test_detect_workspace_falls_back_to_base_dir_for_unrelated_cwd(self):
        unrelated = self.tmp_path / "unrelated_repo"
        unrelated.mkdir()

        old_cwd = os.getcwd()
        old_env = os.environ.get("JH_WORKSPACE")
        try:
            os.environ.pop("JH_WORKSPACE", None)
            os.chdir(str(unrelated))

            detected = workspace.detect_workspace()
            # Must NOT detect the unrelated repo; must fall back to BASE_DIR
            self.assertNotEqual(detected, unrelated)
            self.assertEqual(detected, Path(config.BASE_DIR).resolve())
            # And .jobhunter must NOT exist in the unrelated repo
            self.assertFalse((unrelated / ".jobhunter").exists())
        finally:
            os.chdir(old_cwd)
            if old_env is not None:
                os.environ["JH_WORKSPACE"] = old_env

    def test_detect_workspace_honors_explicit_jh_workspace_env(self):
        custom = self.tmp_path / "custom_ws"
        custom.mkdir()

        old_env = os.environ.get("JH_WORKSPACE")
        try:
            os.environ["JH_WORKSPACE"] = str(custom)
            self.assertEqual(workspace.detect_workspace(), custom.resolve())
        finally:
            if old_env is not None:
                os.environ["JH_WORKSPACE"] = old_env
            else:
                os.environ.pop("JH_WORKSPACE", None)


class TestExecutionMode(unittest.TestCase):
    def test_detect_execution_mode_phrases(self):
        self.assertEqual(ceo.detect_execution_mode("find jobs step by step", {}), "step_by_step")
        self.assertEqual(ceo.detect_execution_mode("step-by-step find backend roles", {}), "step_by_step")
        self.assertEqual(ceo.detect_execution_mode("ask me questions first and find jobs", {}), "step_by_step")
        self.assertEqual(ceo.detect_execution_mode("find jobs", {"mode": "step_by_step"}), "step_by_step")
        self.assertEqual(ceo.detect_execution_mode("find jobs", {"mode": "step"}), "step_by_step")

        self.assertEqual(ceo.detect_execution_mode("auto run find jobs", {}), "auto")
        self.assertEqual(ceo.detect_execution_mode("run everything for python jobs", {}), "auto")
        self.assertEqual(ceo.detect_execution_mode("do everything", {}), "auto")
        self.assertEqual(ceo.detect_execution_mode("find jobs", {"mode": "auto"}), "auto")

        self.assertEqual(ceo.detect_execution_mode("find backend engineer jobs in Tunis", {}), "")

    def test_ceo_offers_step_by_step_or_auto_on_first_analysis(self):
        # CEO instance with mock registry
        mock_registry = {
            "list_resumes": lambda **kw: {"success": True, "status": "ok", "data": {"count": 1, "active_resume": "Resume"}},
            "get_preferences": lambda **kw: {"success": True, "status": "ok", "data": {"resolved_target_countries": ["Tunisia"]}},
            "search_jobs": lambda **kw: {"success": True, "status": "ok", "data": {
                "count": 1,
                "jobs": [{
                    "job_id": "job123456789012",
                    "title": "Software Engineer",
                    "company": "Acme Inc",
                    "location": "Tunis",
                    "apply_url": "https://example.com/job",
                    "fit_score": 85,
                }],
                "coverage": {"sources_ran": 1, "sources_with_results": 1, "raw_postings": 1, "unique_jobs": 1},
            }},
            "gap_report": lambda **kw: {"success": True, "status": "ok", "data": {"real_gaps": []}},
        }
        boss = ceo.CEO(mock_registry, str(config.BASE_DIR))
        res = boss.run("find backend engineer jobs")

        self.assertEqual(res["summary"].get("mode"), "unspecified")
        # Decisions needed asks the client whether to proceed step by step or auto run
        has_mode_decision = any("step by step or auto run" in d for d in res["decisions_needed"])
        self.assertTrue(has_mode_decision, f"Expected mode decision in {res['decisions_needed']}")
        # Next steps also mentions it
        has_mode_step = any("step by step" in s for s in res["next_steps"])
        self.assertTrue(has_mode_step, f"Expected mode step in {res['next_steps']}")
        # Brief includes the decision
        self.assertIn("step by step or auto run", res["brief"])

    def test_ceo_step_by_step_mode_acknowledged(self):
        mock_registry = {
            "list_resumes": lambda **kw: {"success": True, "status": "ok", "data": {"count": 1, "active_resume": "Resume"}},
            "get_preferences": lambda **kw: {"success": True, "status": "ok", "data": {"resolved_target_countries": ["Tunisia"]}},
            "search_jobs": lambda **kw: {"success": True, "status": "ok", "data": {
                "count": 1,
                "jobs": [{
                    "job_id": "job123456789012",
                    "title": "Software Engineer",
                    "company": "Acme Inc",
                    "location": "Tunis",
                    "apply_url": "https://example.com/job",
                    "fit_score": 85,
                }],
                "coverage": {"sources_ran": 1, "sources_with_results": 1, "raw_postings": 1, "unique_jobs": 1},
            }},
            "gap_report": lambda **kw: {"success": True, "status": "ok", "data": {"real_gaps": []}},
        }
        boss = ceo.CEO(mock_registry, str(config.BASE_DIR))
        res = boss.run("find backend engineer jobs", hints={"mode": "step_by_step"})

        self.assertEqual(res["summary"].get("mode"), "step_by_step")
        self.assertTrue(any("Which job do you want to target next" in d for d in res["decisions_needed"]))


if __name__ == "__main__":
    unittest.main()

