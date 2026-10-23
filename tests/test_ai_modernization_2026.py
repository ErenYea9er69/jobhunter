"""Tests for 2026/2027 AI Agent Modernization, Prompt Engine, ATS Intelligence, and Low-Latency Routines."""
import json
import unittest
from unittest.mock import patch, MagicMock

from jh import ats, autofill, config, db, refit


SAMPLE_PROFILE = {
    "name": "Jordan Chen",
    "email": "jordan.chen@example.com",
    "phone": "+1 555-0199",
    "location": "Seattle, WA",
    "target_title": "Senior Distributed Systems Engineer",
    "years_of_experience": 8,
    "min_salary": 185000,
    "notice_period": "3 weeks",
    "skills": ["Go", "Python", "Kubernetes", "Docker", "PostgreSQL", "Redis", "Kafka", "AWS", "gRPC", "CI/CD"],
    "experience": [
        {
            "role": "Staff Infrastructure Engineer",
            "company": "Apex Cloud Systems",
            "dates": "2021 - Present",
            "bullets": [
                "Architected event-driven ingestion pipeline handling 85,000 requests/sec with p99 latency under 12ms.",
                "Decoupled monolithic billing subsystem into Go microservices, improving deployment frequency by 400%.",
                "Benchmarked and tuned Redis cache layer, reducing database query load by 62%."
            ]
        },
        {
            "role": "Backend Software Engineer",
            "company": "Nexus Data Labs",
            "dates": "2018 - 2021",
            "bullets": [
                "Engineered distributed workflow engine processing 14TB of telemetry data daily.",
                "Containerized 28 legacy applications with Docker and automated deployment pipelines in GitLab CI."
            ]
        }
    ],
    "education": [
        {"degree": "B.S. in Computer Science", "institution": "University of Washington", "year": "2018"}
    ]
}

SAMPLE_JOB = {
    "id": "job-stripe-infra-2026",
    "job_key": "job-stripe-infra-2026",
    "title": "Senior Platform Engineer, Core Infrastructure",
    "company": "Stripe",
    "location": "Remote, US",
    "salary": "$190,000 - $240,000",
    "required_skills": ["Go", "Kubernetes", "Kafka", "AWS", "gRPC", "PostgreSQL"],
    "description": (
        "We are looking for a Senior Platform Engineer to scale our core payment infrastructure. "
        "You will design high-throughput systems, optimize p99 latency, and maintain 99.999% SLA uptime. "
        "Requires deep Go, Kafka, AWS, and Kubernetes expertise."
    )
}


class AIModernization2026Tests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(json.dumps(SAMPLE_PROFILE))
        self.job = json.loads(json.dumps(SAMPLE_JOB))

    def test_robust_json_parser_strips_analysis_tags(self):
        """Verify _parse_json_llm_response extracts clean JSON even if preceded by XML reasoning tags."""
        raw_output_with_cot = """
<analysis>
1. Target Analysis: Candidate has strong Go and Kafka experience.
2. Hook Strategy: Focus on 85k req/sec throughput.
3. Bullet Strategy: Google X-Y-Z formula.
</analysis>
{
  "executive_hook": "Senior Platform Engineer with 8 years of experience scaling Go infrastructure.",
  "bullets": {
    "0.0": "Architected event-driven ingestion pipeline handling 85,000 requests/sec with p99 latency under 12ms."
  }
}
"""
        parsed = refit._parse_json_llm_response(raw_output_with_cot)
        self.assertIsNotNone(parsed)
        self.assertIn("executive_hook", parsed)
        self.assertIn("bullets", parsed)
        self.assertEqual(len(parsed["bullets"]), 1)

    def test_robust_json_parser_strips_markdown_code_fences(self):
        """Verify _parse_json_llm_response extracts JSON wrapped in ```json ... ``` markdown."""
        raw_markdown = """```json
{
  "pitch_angle": "technical_architect",
  "pitch_hook": "At Apex Cloud Systems, I led systems handling 85,000 requests/sec with p99 under 12ms.",
  "full_text": "High impact role pitch."
}
```"""
        parsed = refit._parse_json_llm_response(raw_markdown)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["pitch_angle"], "technical_architect")

    def test_modern_power_verbs_recognition(self):
        """Verify 2026 modern high-impact engineering verbs are recognized by the ATS audit engine."""
        modern_verbs = ["architected", "decoupled", "benchmarked", "containerized", "fine-tuned", "scaled", "shipped"]
        for v in modern_verbs:
            self.assertIn(v, ats.POWER_VERBS, f"Verb '{v}' should be recognized as a modern power verb")

    def test_modern_metrics_recognition(self):
        """Verify 2026 modern production metrics (ms latency, RPS, TB data, uptime) are recognized by ATS regex."""
        sample_metrics = [
            "12ms latency",
            "85,000 requests/sec",
            "14TB daily",
            "99.99% uptime",
            "400% deployment frequency",
            "120 tps",
            "$185,000"
        ]
        for m in sample_metrics:
            self.assertTrue(bool(ats.METRIC.search(m)), f"Metric '{m}' should be detected by modern ATS METRIC regex")

    def test_ats_audit_on_modern_resume(self):
        """Verify that a modern high-performance profile receives high ATS score and metrics score."""
        audit = ats.compute_ats_audit(self.profile, self.job)
        self.assertGreaterEqual(audit["ats_score"], 80)
        self.assertEqual(audit["grade"], "A")
        self.assertGreaterEqual(audit["breakdown"]["metrics_score"], 15)
        self.assertGreaterEqual(audit["breakdown"]["verbs_score"], 8)

    def test_cover_pitch_loads_custom_prompt_file(self):
        """Verify generate_cover_pitch reads prompts/cover_letter_pitch.md and passes candidate context."""
        recorded_system = []

        def mock_llm(system, user):
            recorded_system.append(system)
            return json.dumps({
                "pitch_angle": "technical_architect",
                "pitch_hook": "With 8 years architecting Go services at 85,000 requests/sec, I am eager to contribute to Stripe's core infrastructure.",
                "value_pillars": [
                    {
                        "theme": "High Throughput Ingestion",
                        "proof_point": "Architected event-driven ingestion pipeline handling 85,000 requests/sec with p99 latency under 12ms."
                    }
                ],
                "why_company": "Stripe represents the gold standard of financial infrastructure.",
                "honest_bridge": "",
                "call_to_action": "I'd welcome a brief 15-minute conversation to discuss payment pipeline scalability.",
                "full_text": "With 8 years architecting Go services at 85,000 requests/sec, I am eager to contribute to Stripe's core infrastructure.\n\nArchitected event-driven ingestion pipeline handling 85,000 requests/sec with p99 latency under 12ms.\n\nBest regards,\nJordan Chen"
            })

        pitch = refit.generate_cover_pitch(self.job, self.profile, angle="technical_architect", use_llm=True, llm_caller=mock_llm)
        self.assertTrue(len(recorded_system) > 0)
        # Verify the modern prompt instructions were passed
        self.assertTrue("anti-ai slop" in recorded_system[0].lower() or "cliché" in recorded_system[0].lower() or "2026" in recorded_system[0] or "elite" in recorded_system[0].lower())
        self.assertEqual(pitch["pitch_angle"], "technical_architect")
        self.assertIn("85,000 requests/sec", pitch["full_text"])

    def test_screening_question_solver_with_modern_prompt(self):
        """Verify solve_screening_question executes with 2026 guidelines and returns clean text."""
        recorded_system = []

        def mock_screening_llm(system, user):
            recorded_system.append(system)
            return json.dumps({
                "question_type": "technical_achievement",
                "answer": "At Apex Cloud Systems, I personally architected an event-driven ingestion pipeline handling 85,000 requests/sec with p99 latency under 12ms. By decoupling the architecture into Go microservices and optimizing Redis caching, we reduced database query load by 62% without dropping customer traffic.",
                "key_proof_point": "Architected ingestion pipeline handling 85,000 requests/sec.",
                "word_count": 42,
                "grounded": True
            })

        q = "Describe your proudest technical accomplishment in distributed systems."
        with patch.object(refit, "_call_llm", side_effect=mock_screening_llm):
            with patch.object(refit, "llm_available", return_value=True):
                result = autofill.solve_screening_question(q, self.profile, self.job)

        self.assertTrue(result["grounded"])
        self.assertIn("85,000 requests/sec", result["answer"])
        # Verify no trailing quotes or markdown asterisks
        self.assertFalse(result["answer"].startswith('"'))
        self.assertFalse(result["answer"].endswith('"'))
        self.assertNotIn("**", result["answer"])

    def test_call_llm_json_mode_dispatch(self):
        """Verify _call_llm passes json mode parameters for Gemini, OpenAI, and Ollama."""
        # 1. Test Gemini JSON mode
        with patch("jh.refit.http_get") as mock_http:
            mock_http.return_value = json.dumps({
                "candidates": [{"content": {"parts": [{"text": "{\"status\": \"ok\"}"}]}}]
            })
            cfg_gemini = {"provider": "gemini", "key": "test-key", "model": "gemini-2.5-flash", "endpoint": ""}
            res = refit._call_llm("Generate JSON output.", "Input data", cfg=cfg_gemini)
            self.assertEqual(res, "{\"status\": \"ok\"}")
            call_kwargs = mock_http.call_args[1]
            sent_body = json.loads(call_kwargs["data"].decode("utf-8"))
            self.assertEqual(sent_body["generationConfig"].get("responseMimeType"), "application/json")

        # 2. Test OpenAI JSON mode
        with patch("jh.refit.http_get") as mock_http:
            mock_http.return_value = json.dumps({
                "choices": [{"message": {"content": "{\"status\": \"ok\"}"}}]
            })
            cfg_openai = {"provider": "openai", "key": "test-key", "model": "gpt-4o-mini", "endpoint": ""}
            res = refit._call_llm("Return JSON only: {}", "User task", cfg=cfg_openai)
            self.assertEqual(res, "{\"status\": \"ok\"}")
            call_kwargs = mock_http.call_args[1]
            sent_body = json.loads(call_kwargs["data"].decode("utf-8"))
            self.assertEqual(sent_body.get("response_format"), {"type": "json_object"})

        # 3. Test Ollama JSON mode
        with patch("jh.refit.http_get") as mock_http:
            mock_http.return_value = json.dumps({"response": "{\"status\": \"ok\"}"})
            cfg_ollama = {"provider": "ollama", "key": "", "model": "llama3.3", "endpoint": "http://127.0.0.1:11434"}
            res = refit._call_llm("Generate JSON reply", "Payload", cfg=cfg_ollama)
            self.assertEqual(res, "{\"status\": \"ok\"}")
            call_kwargs = mock_http.call_args[1]
            sent_body = json.loads(call_kwargs["data"].decode("utf-8"))
            self.assertEqual(sent_body.get("format"), "json")


if __name__ == "__main__":
    unittest.main()
