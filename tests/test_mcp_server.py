"""Integration tests for JobHunter MCP server tools and resources."""

import json
import os
import tempfile
import unittest
from pathlib import Path

import mcp_server


SAMPLE_RESUME = """John Doe
john.doe@example.com | 555-123-4567 | San Francisco, CA | linkedin.com/in/johndoe | github.com/johndoe

SUMMARY
Senior Software Engineer with 8 years of experience building high-throughput distributed backend systems, REST APIs, and event-driven architectures using Python, Go, and PostgreSQL.

EXPERIENCE
Senior Backend Engineer | Stripe | 2021 - Present
- Architected payment processing pipeline handling 50,000 transactions per second.
- Reduced p99 latency by 45% through Redis caching and query optimization.
- Led migration of monolithic billing service to Go microservices on Kubernetes.

Backend Developer | Square | 2018 - 2021
- Built merchant onboarding REST APIs with Python, FastAPI, and PostgreSQL.
- Implemented automated CI/CD deployment pipelines on AWS using Docker.

EDUCATION
BS in Computer Science | University of California, Berkeley | 2018

SKILLS
Python, Go, FastAPI, Django, PostgreSQL, Redis, Docker, Kubernetes, AWS, Microservices, System Design, REST APIs
"""

SAMPLE_JOB = {
    "title": "Senior Python Engineer",
    "company": "Anthropic",
    "description": """Anthropic is looking for a Senior Python Engineer to scale our AI evaluation infrastructure.
Requirements:
- 5+ years of software engineering experience with Python and distributed systems.
- Experience with PostgreSQL, Redis, Docker, and AWS.
- Strong knowledge of REST APIs and microservice architecture.
- Experience with Kubernetes and CI/CD pipelines is a plus.
""",
}


class TestMCPServer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws_path = Path(self.temp_dir.name)

        # Create a resume file in the temporary workspace
        resumes_dir = self.ws_path / "resumes"
        resumes_dir.mkdir()
        resume_file = resumes_dir / "senior-python-engineer.txt"
        resume_file.write_text(SAMPLE_RESUME, encoding="utf-8")

        # Create and initialize server
        self.server = mcp_server.create_server(str(self.ws_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _call_tool(self, name: str, **kwargs):
        # Directly invoke the registered tool function through FastMCP tool manager
        tool = self.server._tool_manager.get_tool(name)
        self.assertIsNotNone(tool, f"Tool '{name}' not found on server")
        return tool.fn(**kwargs)

    def test_startup_discovery_and_active_resume(self):
        res = self._call_tool("list_resumes")
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)
        self.assertIn("Senior Python Engineer", res["active_resume"])

        get_res = self._call_tool("get_resume")
        self.assertTrue(get_res["success"])
        self.assertEqual(get_res["profile"]["name"], "John Doe")
        self.assertTrue(len(get_res["profile"]["skills"]) >= 5)

    def test_scoring_tools(self):
        # 1. score_job
        res = self._call_tool(
            "score_job",
            job_title=SAMPLE_JOB["title"],
            company=SAMPLE_JOB["company"],
            description=SAMPLE_JOB["description"],
        )
        self.assertTrue(res["success"])
        self.assertTrue(res["score"] > 60)
        self.assertIn("breakdown", res)

        # 2. ats_audit
        audit_res = self._call_tool(
            "ats_audit",
            job_title=SAMPLE_JOB["title"],
            company=SAMPLE_JOB["company"],
            description=SAMPLE_JOB["description"],
        )
        self.assertTrue(audit_res["success"])
        self.assertIn("ats_score", audit_res)
        self.assertTrue(Path(audit_res["report_file"]).is_file())

        # 3. gap_report
        gap_res = self._call_tool(
            "gap_report",
            job_title=SAMPLE_JOB["title"],
            company=SAMPLE_JOB["company"],
            description=SAMPLE_JOB["description"],
        )
        self.assertTrue(gap_res["success"])
        self.assertTrue(Path(gap_res["report_file"]).is_file())

        # 4. compare_resumes
        comp_res = self._call_tool(
            "compare_resumes",
            job_title=SAMPLE_JOB["title"],
            company=SAMPLE_JOB["company"],
            description=SAMPLE_JOB["description"],
        )
        self.assertTrue(comp_res["success"])

    def test_tailoring_and_generation_tools(self):
        # 1. tailor_resume
        tailor_res = self._call_tool(
            "tailor_resume",
            job_title=SAMPLE_JOB["title"],
            company=SAMPLE_JOB["company"],
            description=SAMPLE_JOB["description"],
        )
        self.assertTrue(tailor_res["success"])
        self.assertTrue(Path(tailor_res["saved_to"]).is_file())
        self.assertIn("ats_before", tailor_res)
        self.assertIn("ats_after", tailor_res)

        # 2. cover_letter
        letter_res = self._call_tool(
            "cover_letter",
            job_title=SAMPLE_JOB["title"],
            company=SAMPLE_JOB["company"],
            description=SAMPLE_JOB["description"],
        )
        self.assertTrue(letter_res["success"])
        self.assertTrue(Path(letter_res["saved_to"]).is_file())
        self.assertTrue(len(letter_res["cover_letter"]) > 100)

        # 3. interview_prep
        prep_res = self._call_tool(
            "interview_prep",
            job_title=SAMPLE_JOB["title"],
            company=SAMPLE_JOB["company"],
            description=SAMPLE_JOB["description"],
        )
        self.assertTrue(prep_res["success"])
        self.assertTrue(Path(prep_res["saved_to"]).is_file())

        # 4. outreach_message
        outreach_res = self._call_tool(
            "outreach_message",
            job_title=SAMPLE_JOB["title"],
            company=SAMPLE_JOB["company"],
            description=SAMPLE_JOB["description"],
        )
        self.assertTrue(outreach_res["success"])

    def test_application_tracking_lifecycle(self):
        # 1. track_application
        track_res = self._call_tool(
            "track_application",
            company="Anthropic",
            title="Senior Python Engineer",
            status="applied",
            url="https://anthropic.com/careers/123",
            notes="Applied through portal",
        )
        self.assertTrue(track_res["success"])
        app_id = track_res["application"]["id"]

        # 2. list_applications
        list_res = self._call_tool("list_applications")
        self.assertTrue(list_res["success"])
        self.assertEqual(list_res["count"], 1)

        # 3. update_application
        update_res = self._call_tool(
            "update_application",
            id=app_id,
            status="interview",
            notes="Technical screen arranged",
        )
        self.assertTrue(update_res["success"])
        self.assertEqual(update_res["application"]["status"], "interview")

        # 4. application_stats
        stats_res = self._call_tool("application_stats")
        self.assertTrue(stats_res["success"])
        self.assertEqual(stats_res["total_tracked"], 1)

    def test_utility_and_export_tools(self):
        # 1. configure
        cfg_res = self._call_tool("configure", key="min_salary", value="150000")
        self.assertTrue(cfg_res["success"])
        self.assertEqual(cfg_res["value"], "150000")

        # 2. export_resume txt
        export_res = self._call_tool("export_resume", format="txt")
        self.assertTrue(export_res["success"])
        self.assertTrue(Path(export_res["exported_to"]).is_file())

        # 3. source_health
        health_res = self._call_tool("source_health")
        self.assertTrue(health_res["success"])
        self.assertIn("sources", health_res)

    def test_resources(self):
        # Resource read: jobhunter://resumes
        res_manager = self.server._resource_manager
        resumes_raw = res_manager._resources["jobhunter://resumes"].fn()
        resumes = json.loads(resumes_raw)
        self.assertTrue(len(resumes) >= 1)

        # Resource read: jobhunter://applications
        apps_raw = res_manager._resources["jobhunter://applications"].fn()
        apps = json.loads(apps_raw)
        self.assertIsInstance(apps, list)

        # Resource read: jobhunter://config
        config_raw = res_manager._resources["jobhunter://config"].fn()
        cfg = json.loads(config_raw)
        self.assertIn("workspace", cfg)


if __name__ == "__main__":
    unittest.main()
