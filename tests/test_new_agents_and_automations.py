"""Unit tests for 2026/2027 App-Wide Agents & Automations:
Interview Prep Copilot, Mock Evaluator, Recruiter Outreach, Application Follow-Up & Alerts,
Career Skill Roadmap, and 1-Click Application Prep Bundle.
"""
import json
import unittest
from unittest.mock import patch, MagicMock

from jh import config, db, refit, tracker, httpd, ats


SAMPLE_PROFILE = {
    "name": "Alex Rivera",
    "email": "alex.rivera@example.com",
    "phone": "+1 555-0144",
    "location": "San Francisco, CA",
    "target_title": "Senior Backend Systems Engineer",
    "years_of_experience": 7,
    "target_salary": "$180,000",
    "min_salary": 165000,
    "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "AWS", "CI/CD"],
    "experience": [
        {
            "role": "Senior Software Engineer",
            "company": "CloudScale IO",
            "dates": "2022 - Present",
            "bullets": [
                "Scaled asynchronous API gateways processing 45,000 requests/sec with p99 latency under 15ms.",
                "Instrumented real-time telemetry reducing incident mean-time-to-detection by 55%."
            ]
        },
        {
            "role": "Software Engineer",
            "company": "DataStream Corp",
            "dates": "2019 - 2022",
            "bullets": [
                "Migrated relational databases to PostgreSQL, improving query throughput by 35%.",
                "Containerized microservices using Docker and automated CI/CD deployment pipelines."
            ]
        }
    ],
    "education": [
        {"degree": "B.S. in Computer Science", "institution": "UC Berkeley", "year": "2019"}
    ]
}

SAMPLE_JOB = {
    "id": "job-fintech-2026",
    "title": "Senior Distributed Backend Engineer",
    "company": "Fintech Global",
    "location": "Remote",
    "salary": "$175,000 - $210,000",
    "description": (
        "We are seeking a Senior Distributed Backend Engineer to lead our event processing cluster. "
        "Must have extensive experience with Python, FastAPI, PostgreSQL, Redis, and high-concurrency systems."
    )
}


class TestInterviewPrepAndMockEvaluator(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_interview_prep_deterministic(self):
        """Test deterministic interview prep output structure."""
        prep = refit.generate_interview_prep(SAMPLE_JOB, SAMPLE_PROFILE, use_llm=False)
        self.assertIn("role", prep)
        self.assertIn("company", prep)
        self.assertEqual(prep["company"], "Fintech Global")
        self.assertIn("interview_focus_areas", prep)
        self.assertIn("technical_deep_dives", prep)
        self.assertIn("behavioral_questions", prep)
        self.assertIn("gap_talking_points", prep)
        self.assertIn("questions_to_ask_interviewer", prep)
        self.assertFalse(prep["used_llm"])

    def test_interview_prep_mock_llm(self):
        """Test interview prep copilot with mock LLM response."""
        mock_response = json.dumps({
            "role": "Senior Distributed Backend Engineer",
            "company": "Fintech Global",
            "interview_focus_areas": ["Async Concurrency", "PostgreSQL Sharding", "Redis Caching"],
            "technical_deep_dives": [
                {
                    "topic": "FastAPI & Async IO",
                    "question": "How do you handle connection pool exhaustion under 45k rps?",
                    "expected_concepts": ["Connection pooling", "Keep-alive", "Backpressure"],
                    "candidate_talking_point": "At CloudScale IO, I scaled asynchronous gateways handling 45,000 rps."
                }
            ],
            "behavioral_scenarios": [
                {
                    "theme": "High-Pressure Incident",
                    "question": "Describe an incident where production latency spiked.",
                    "star_strategy": {
                        "situation_task": "P99 spiked during traffic surge",
                        "action_taken": "Instrumented real-time telemetry",
                        "quantified_result": "Cut MTTD by 55%"
                    }
                }
            ],
            "gap_talking_points": [
                {"missing_skill": "Kafka", "recommended_response": "I have deep Redis pub/sub experience and understand consumer groups."}
            ],
            "questions_to_ask_interviewer": [
                "How does the team manage schema migrations across high-concurrency PostgreSQL shards?"
            ]
        })

        def mock_caller(system, user):
            return mock_response

        prep = refit.generate_interview_prep(SAMPLE_JOB, SAMPLE_PROFILE, use_llm=True, llm_caller=mock_caller)
        self.assertTrue(prep["used_llm"])
        self.assertEqual(len(prep["technical_deep_dives"]), 1)
        self.assertEqual(prep["technical_deep_dives"][0]["topic"], "FastAPI & Async IO")
        self.assertIn("Async Concurrency", prep["interview_focus_areas"])
        # Check backward compatibility key
        self.assertIn("behavioral_questions", prep)

    def test_mock_interview_evaluator_deterministic(self):
        """Test mock evaluator with deterministic scoring."""
        good_answer = (
            "In my previous position at CloudScale IO, I identified a severe p99 latency bottleneck in our primary API gateway. "
            "I took direct ownership and re-architected the asynchronous worker pool, instrumenting distributed tracing. "
            "As a result, I reduced p99 latency to under 15ms and increased system throughput to 45,000 requests per second."
        )
        res = refit.evaluate_mock_interview_answer(
            "Tell me about a challenging latency problem you resolved.",
            good_answer,
            job=SAMPLE_JOB,
            profile=SAMPLE_PROFILE,
            use_llm=False
        )
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(res["overall_score"], 80)
        self.assertIn(res["verdict"], ["Strong Contender", "Solid Foundation"])
        self.assertIn("rubric_scores", res)
        self.assertGreaterEqual(res["rubric_scores"]["ownership"], 80)
        self.assertGreaterEqual(res["rubric_scores"]["quantified_impact"], 85)

    def test_mock_interview_evaluator_llm(self):
        """Test mock evaluator with mock LLM caller."""
        mock_response = json.dumps({
            "overall_score": 92,
            "verdict": "Strong Hire",
            "strengths": ["Clear personal ownership", "Cites exact p99 metric (15ms)"],
            "areas_for_improvement": ["Briefly clarify connection pooling settings"],
            "red_flags": [],
            "rubric_scores": {
                "ownership": 95,
                "technical_depth": 90,
                "quantified_impact": 94,
                "structure": 90
            },
            "refined_answer_suggestion": "Polished high-impact rewrite with STAR-L."
        })

        def mock_caller(sys, usr):
            return mock_response

        res = refit.evaluate_mock_interview_answer(
            "How do you optimize latency?",
            "I improved latency by 50% using Redis.",
            job=SAMPLE_JOB,
            profile=SAMPLE_PROFILE,
            use_llm=True,
            llm_caller=mock_caller
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["overall_score"], 92)
        self.assertEqual(res["verdict"], "Strong Hire")
        self.assertTrue(res["used_llm"])


class TestRecruiterOutreachAgent(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_recruiter_outreach_deterministic(self):
        """Test recruiter outreach generation under 295 chars for LinkedIn and complete InMail."""
        outreach = refit.generate_recruiter_outreach(SAMPLE_JOB, SAMPLE_PROFILE, use_llm=False)
        self.assertTrue(outreach["ok"])
        self.assertEqual(outreach["target_company"], "Fintech Global")
        self.assertLessEqual(outreach["linkedin_connection_chars"], 295)
        self.assertIn("hiring_manager_inmail", outreach)
        self.assertIn("subject_line", outreach["hiring_manager_inmail"])
        self.assertIn("body", outreach["hiring_manager_inmail"])
        self.assertIn("peer_referral_request", outreach)
        self.assertFalse(outreach["used_llm"])

    def test_recruiter_outreach_mock_llm(self):
        """Test recruiter outreach with mock LLM enforcing character limits."""
        mock_response = json.dumps({
            "target_company": "Fintech Global",
            "target_role": "Senior Distributed Backend Engineer",
            "linkedin_connection_note": "Hi! Saw Fintech Global's backend role. Scaled 45k rps async pipelines with p99 <15ms at CloudScale IO. Would love to connect and follow the team's engineering work!",
            "hiring_manager_inmail": {
                "subject_line": "Senior Backend Engineer — High-throughput systems focus",
                "body": "Hi Hiring Team, I noticed your opening. In my recent role, I scaled APIs to 45k rps. Would love to chat."
            },
            "peer_referral_request": {
                "subject_line": "Quick question on Fintech Global engineering culture",
                "body": "Hi, saw your work on the core platform. I am applying for the backend role and would love to hear your thoughts."
            },
            "key_proof_point_used": "Scaled async API gateways processing 45k rps"
        })

        def mock_caller(sys, usr):
            return mock_response

        outreach = refit.generate_recruiter_outreach(SAMPLE_JOB, SAMPLE_PROFILE, use_llm=True, llm_caller=mock_caller)
        self.assertTrue(outreach["ok"])
        self.assertTrue(outreach["used_llm"])
        self.assertLessEqual(outreach["linkedin_connection_chars"], 295)


class TestApplicationFollowUpAndAlerts(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.app_id = tracker.upsert_application({
            "company": "Fintech Global",
            "title": "Senior Distributed Backend Engineer",
            "status": "applied",
            "notes": "Submitted via company portal",
            "salary": "$180,000",
            "job_data": SAMPLE_JOB
        })

    def test_follow_up_deterministic_status_check(self):
        """Test 5-day status ping follow-up generation."""
        fu = tracker.generate_application_follow_up(
            self.app_id,
            action_type="status_check_5days",
            profile=SAMPLE_PROFILE,
            use_llm=False
        )
        self.assertTrue(fu["ok"])
        self.assertEqual(fu["action_type"], "status_check_5days")
        self.assertIn("Fintech Global", fu["subject_line"])
        self.assertIn("Alex Rivera", fu["body"])
        self.assertIn("strategy_notes", fu)
        self.assertFalse(fu["used_llm"])

    def test_follow_up_deterministic_interview_thank_you(self):
        """Test post-interview thank you generation."""
        fu = tracker.generate_application_follow_up(
            self.app_id,
            action_type="post_interview_thank_you",
            profile=SAMPLE_PROFILE,
            use_llm=False
        )
        self.assertTrue(fu["ok"])
        self.assertEqual(fu["action_type"], "post_interview_thank_you")
        self.assertIn("Thank you", fu["subject_line"])
        self.assertIn("Alex Rivera", fu["body"])

    def test_follow_up_deterministic_offer_negotiation(self):
        """Test strategic offer negotiation script generation."""
        fu = tracker.generate_application_follow_up(
            self.app_id,
            action_type="offer_negotiation",
            profile=SAMPLE_PROFILE,
            use_llm=False
        )
        self.assertTrue(fu["ok"])
        self.assertEqual(fu["action_type"], "offer_negotiation")
        self.assertIn("Offer", fu["subject_line"])
        self.assertIn("Alex Rivera", fu["body"])

    def test_stale_applications_alerts(self):
        """Test scan for actionable follow-up and interview alerts."""
        alerts_res = tracker.get_stale_applications_alerts(threshold_days=0)
        self.assertTrue(alerts_res["ok"])
        self.assertGreaterEqual(alerts_res["count"], 1)
        alert = next((a for a in alerts_res["alerts"] if a["application_id"] == self.app_id), None)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["company"], "Fintech Global")
        self.assertIn("alert_type", alert)


class TestCareerSkillRoadmapAgent(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_skill_roadmap_deterministic(self):
        """Test strategic skill gap analysis and 2-week fast-track project."""
        roadmap = refit.generate_skill_roadmap(
            SAMPLE_PROFILE,
            target_title="Staff Systems Architect",
            market_skills=["Kubernetes", "Kafka", "Distributed Tracing"],
            use_llm=False
        )
        self.assertTrue(roadmap["ok"])
        self.assertEqual(roadmap["target_title"], "Staff Systems Architect")
        self.assertGreaterEqual(len(roadmap["top_missing_skills"]), 1)
        self.assertIn("fast_track_project", roadmap)
        self.assertIn("project_title", roadmap["fast_track_project"])
        self.assertIn("deliverables", roadmap["fast_track_project"])
        self.assertIn("interview_bridge_script", roadmap)
        self.assertFalse(roadmap["used_llm"])

    def test_skill_roadmap_mock_llm(self):
        """Test skill roadmap with mock LLM."""
        mock_response = json.dumps({
            "target_title": "Principal Systems Engineer",
            "top_missing_skills": [
                {"skill": "Kafka", "market_demand_level": "Critical", "why_important": "Required for event stream ordering"}
            ],
            "fast_track_project": {
                "project_title": "Distributed Financial Ledger with Kafka & FastAPI",
                "architecture_summary": "Idempotent payment stream pipeline with Redis deduplication",
                "deliverables": ["Helm chart", "Benchmark suite", "Integration tests"],
                "time_to_complete_days": 14
            },
            "interview_bridge_script": "My Redis messaging background provides a clean foundation for Kafka partitioning.",
            "recommended_learning_resources": [{"topic": "Kafka Internals", "focus_area": "Consumer group rebalancing"}]
        })

        def mock_caller(sys, usr):
            return mock_response

        roadmap = refit.generate_skill_roadmap(
            SAMPLE_PROFILE,
            target_title="Principal Systems Engineer",
            use_llm=True,
            llm_caller=mock_caller
        )
        self.assertTrue(roadmap["ok"])
        self.assertTrue(roadmap["used_llm"])
        self.assertEqual(roadmap["fast_track_project"]["project_title"], "Distributed Financial Ledger with Kafka & FastAPI")


class TestOneClickApplicationBundle(unittest.TestCase):
    def setUp(self):
        db.init_db()
        db.save_profile(SAMPLE_PROFILE)

    def test_generate_one_click_bundle(self):
        """Test 1-click package assembly containing resume, pitch, outreach, interview prep, and screening questions."""
        bundle = tracker.generate_one_click_bundle(SAMPLE_JOB, SAMPLE_PROFILE, use_llm=False)
        self.assertTrue(bundle["ok"])
        self.assertTrue(bundle["success"])
        self.assertIn("app_id", bundle)
        self.assertIn("tailored_resume", bundle)
        self.assertIn("role_pitch", bundle)
        self.assertIn("recruiter_outreach", bundle)
        self.assertIn("interview_prep", bundle)
        self.assertIn("screening_answers", bundle)
        self.assertEqual(len(bundle["screening_answers"]), 3)
        self.assertIn("ats_audit", bundle)
        self.assertIn("ats_boost", bundle)

        # Verify application was persisted in DB
        app_list = tracker.list_applications()
        saved = next((a for a in app_list if a["id"] == bundle["app_id"]), None)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["company"], "Fintech Global")
        self.assertEqual(saved["status"], "saved")


class TestHttpEndpoints(unittest.TestCase):
    def setUp(self):
        db.init_db()
        db.save_profile(SAMPLE_PROFILE)
        self.app_id = tracker.upsert_application({
            "company": "Fintech Global",
            "title": "Senior Distributed Backend Engineer",
            "status": "applied",
            "salary": "$180,000",
            "job_data": SAMPLE_JOB
        })

    def test_http_interview_prep_evaluate(self):
        handler = httpd.ROUTES[("POST", "/api/interview-prep/evaluate")]
        res = handler({}, {
            "question": "Walk me through how you tuned Redis performance.",
            "answer": "At CloudScale IO, I benchmarked our Redis caching layer and reduced database query load by 62%.",
            "job": SAMPLE_JOB,
            "use_llm": False
        })
        self.assertTrue(res["ok"])
        self.assertIn("overall_score", res)

    def test_http_outreach_generate(self):
        handler = httpd.ROUTES[("POST", "/api/outreach/generate")]
        res = handler({}, {"job": SAMPLE_JOB, "use_llm": False})
        self.assertTrue(res["ok"])
        self.assertIn("linkedin_connection_note", res)

    def test_http_applications_follow_up(self):
        handler = httpd.ROUTES[("POST", "/api/applications/follow-up")]
        res = handler({}, {
            "app_id": self.app_id,
            "action_type": "status_check_5days",
            "use_llm": False
        })
        self.assertTrue(res["ok"])
        self.assertIn("subject_line", res)

    def test_http_applications_alerts(self):
        handler = httpd.ROUTES[("GET", "/api/applications/alerts")]
        res = handler({"threshold_days": ["0"]}, {})
        self.assertTrue(res["ok"])
        self.assertIn("alerts", res)

    def test_http_career_skill_roadmap(self):
        handler = httpd.ROUTES[("POST", "/api/career/skill-roadmap")]
        res = handler({}, {"target_title": "Backend Lead", "use_llm": False})
        self.assertTrue(res["ok"])
        self.assertIn("fast_track_project", res)

    def test_http_apply_bundle(self):
        handler = httpd.ROUTES[("POST", "/api/jobs/apply-bundle")]
        res = handler({}, {"job": SAMPLE_JOB, "use_llm": False})
        self.assertTrue(res["ok"])
        self.assertIn("tailored_resume", res)
        self.assertIn("role_pitch", res)
        self.assertIn("screening_answers", res)


if __name__ == "__main__":
    unittest.main()
