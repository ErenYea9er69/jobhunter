"""JobHunter E2E Test Runner for T1 to T20.

Runs all 20 target scenarios hermetically against a temporary home folder,
records stdout/tracebacks, writes e2e_report.txt, and displays the summary table.
"""
from __future__ import annotations

import datetime
import gc
import os
import pathlib
import sys
import tempfile
import traceback

# Ensure project root and e2e directory are in sys.path
E2E_DIR = pathlib.Path(__file__).resolve().parent
ROOT = E2E_DIR.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

import test_suite

T_IDS = [
    ("T1", "Clean install and one home folder", "test_t1_clean_install_and_home_folder"),
    ("T2", "Resume check, several resumes, wrong files", "test_t2_resume_check_several_resumes_wrong_files"),
    ("T3", "Role inference", "test_t3_role_inference"),
    ("T4", "The targeting questions (the main gap)", "test_t4_targeting_questions"),
    ("T5", "Method choice", "test_t5_method_choice"),
    ("T6", "Ticket gate and launch", "test_t6_ticket_gate_and_launch"),
    ("T7", "Browser and extension", "test_t7_browser_and_extension"),
    ("T8", "Subagent is optional", "test_t8_subagent_optional"),
    ("T9", "Search and live filters", "test_t9_search_and_live_filters"),
    ("T10", "Chat and UI split", "test_t10_chat_and_ui_split"),
    ("T11", "Radar and signals", "test_t11_radar_and_signals"),
    ("T12", "Refresh of other sources", "test_t12_refresh_of_other_sources"),
    ("T13", "Duplicates and old jobs", "test_t13_duplicates_and_old_jobs"),
    ("T14", "Modern: company brief and contacts", "test_t14_modern_company_brief_and_contacts"),
    ("T15", "Modern: the resume and the email", "test_t15_modern_resume_and_email"),
    ("T16", "Classic save flow", "test_t16_classic_save_flow"),
    ("T17", "Extension and screening answers", "test_t17_extension_and_screening_answers"),
    ("T18", "Coaching and mock interviews", "test_t18_coaching_and_mock_interviews"),
    ("T19", "Pipeline tracking, Gmail sync, digests", "test_t19_pipeline_tracking_gmail_sync_digests"),
    ("T20", "Privacy, safety, resilience, speed", "test_t20_privacy_safety_resilience_speed"),
]


def run_e2e_suite(report_title: str = "E2E EXECUTION REPORT") -> dict[str, dict]:
    results = {}
    timestamp = datetime.datetime.now().isoformat()
    command_line = "python tests/e2e/run_all.py"

    print(f"\n=======================================================")
    print(f" {report_title}")
    print(f" Time: {timestamp}")
    print(f" Command: {command_line}")
    print(f"=======================================================\n")

    for t_id, desc, fn_name in T_IDS:
        fn = getattr(test_suite, fn_name, None)
        if not fn:
            results[t_id] = {
                "desc": desc,
                "status": "NOT RUN",
                "error": f"Function {fn_name} not found in test_suite.",
            }
            print(f"[{t_id}] NOT RUN: {desc}")
            continue

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_repo, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_home:
            repo_path = pathlib.Path(temp_repo)
            home_path = pathlib.Path(temp_home)
            env = {
                "repo": repo_path,
                "home": home_path,
                "fixtures": test_suite.FIXTURES_DIR,
            }

            old_env_home = os.environ.get("JOBMCP_HOME")
            os.environ["JOBMCP_HOME"] = str(home_path)

            from jh import config, db, ticket_manager, worker_launcher, home, preferences
            old_ws = config.WORKSPACE_DIR
            old_data = config.DATA_DIR
            old_db = config.DB_PATH

            config.WORKSPACE_DIR = str(repo_path)
            config.DATA_DIR = str(home_path / "data")
            config.DB_PATH = str(home_path / "data" / "engine.db")

            (home_path / "data").mkdir(parents=True, exist_ok=True)
            db.init_db()

            ticket_manager._TICKETS.clear()
            ticket_manager._SESSIONS.clear()
            worker_launcher._ACTIVE_SEARCH_JOBS.clear()
            home._HOME_CREATED_IN_SESSION = False
            home._FIRST_NOTICE_GIVEN = False
            preferences._cache.update(mtime=None, path=None, data=None)

            try:
                fn(env)
                results[t_id] = {
                    "desc": desc,
                    "status": "PASS",
                    "error": "",
                }
                print(f"[{t_id}] PASS: {desc}")
            except Exception as exc:
                err_text = traceback.format_exc()
                results[t_id] = {
                    "desc": desc,
                    "status": "FAIL",
                    "error": err_text,
                }
                print(f"[{t_id}] FAIL: {desc}")
                print(f"    Error: {exc}")
            finally:
                gc.collect()
                if old_env_home:
                    os.environ["JOBMCP_HOME"] = old_env_home
                else:
                    os.environ.pop("JOBMCP_HOME", None)
                config.WORKSPACE_DIR = old_ws
                config.DATA_DIR = old_data
                config.DB_PATH = old_db

    # Format e2e_report.txt
    report_lines = [
        f"======================================================================",
        f" {report_title}",
        f" Command: {command_line}",
        f" Time: {timestamp}",
        f"======================================================================",
        f"",
        f"| T-ID | Requirement Summary | Status | Details |",
        f"| :--- | :------------------ | :----- | :------ |",
    ]

    for t_id, desc, _ in T_IDS:
        r = results.get(t_id, {})
        st = r.get("status", "NOT RUN")
        err = r.get("error", "").replace("\n", " ")[:120]
        report_lines.append(f"| {t_id} | {desc} | {st} | {err} |")

    report_lines.append("")
    report_lines.append("=== DETAILED FAILURE LOGS ===")
    for t_id, desc, _ in T_IDS:
        r = results.get(t_id, {})
        if r.get("status") == "FAIL":
            report_lines.append(f"\n--- [{t_id}] {desc} ---")
            report_lines.append(r.get("error", "No details"))

    report_path = ROOT / "e2e_report.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\nSaved report to {report_path}")
    return results


if __name__ == "__main__":
    run_e2e_suite("BASELINE RUN: TARGET BEHAVIOR (T1-T20)")
