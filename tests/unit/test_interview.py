"""Unit tests for interview preparation and mock answer evaluation per Section 6.1, 12 & 17 of newall-logic.md."""
import pytest
from jh.interview import evaluate_mock_interview, generate_interview_prep


def test_evaluate_mock_interview_strong_answer():
    question = "Describe a time you solved a high-latency issue in a distributed system."
    answer = (
        "I investigated our payment processing service when p99 latency spiked to 1.8s. "
        "I profiled the database queries, identified missing compound indexes on transaction_id and timestamp, "
        "and introduced Redis caching for read-heavy authentication tokens. "
        "As a result, I reduced p99 latency by 68% down to 220ms and cut RDS CPU utilization in half."
    )
    result = evaluate_mock_interview(question, answer, role_level="senior", rubric="standard")
    assert 0 <= result["total_score"] <= 100
    assert result["total_score"] >= 75
    assert result["verdict"] in ("Strong Hire", "Lean Hire")
    assert "dimension_scores" in result
    dims = result["dimension_scores"]
    assert "technical_precision" in dims
    assert "structure_clarity" in dims
    assert "evidence_result" in dims
    assert "ownership_reflection" in dims
    assert len(result["strengths"]) > 0
    assert "suggested_rewrite" in result


def test_evaluate_mock_interview_vague_answer():
    question = "How do you handle disagreements on technical design?"
    answer = "We just talk about it and everyone agrees eventually."
    result = evaluate_mock_interview(question, answer, role_level="senior", rubric="standard")
    assert result["total_score"] < 60
    assert result["verdict"] in ("Needs Practice", "Borderline")
    assert len(result["specific_improvements"]) > 0


def test_generate_interview_prep_structure():
    job = {
        "title": "Senior Distributed Systems Engineer",
        "company": "Cloudflare",
        "description": "Looking for Go and Kubernetes expert to build high-scale edge proxy."
    }
    profile = {
        "name": "Alex Engineer",
        "skills": ["Go", "Kubernetes", "Linux", "Distributed Systems"],
        "experience": [
            {
                "title": "Backend Engineer",
                "company": "FastNet",
                "highlights": ["Built reverse proxy handling 50k req/s in Go"]
            }
        ]
    }
    prep = generate_interview_prep(job, profile, interview_type="all")
    assert "technical_questions" in prep
    assert "system_design_questions" in prep
    assert "behavioral_star_questions" in prep
    assert "interviewer_questions" in prep
    assert len(prep["technical_questions"]) >= 2
