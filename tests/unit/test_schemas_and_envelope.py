"""Unit tests for tool result envelope and schemas per newall-logic.md Section 4.3 and 17."""
import pytest
from jh.mcp_tools import _tool_envelope
from jh.models import ToolOutcome
from jh import schemas


def test_tool_envelope_schema_version_and_keys():
    env = _tool_envelope(status="ok", data={"key": "val"}, warnings=["sample warning"], sources_used=["Greenhouse"])
    assert env["status"] == "ok"
    assert env["success"] is True
    assert env["schema_version"] == "1.0"
    assert len(env["correlation_id"]) == 12
    assert env["data"] == {"key": "val"}
    assert env["warnings"] == ["sample warning"]
    assert env["sources"] == ["Greenhouse"]


def test_tool_envelope_statuses():
    env_ok = _tool_envelope(status="ok")
    assert env_ok["success"] is True

    env_partial = _tool_envelope(status="partial")
    assert env_partial["success"] is True

    env_needs_review = _tool_envelope(status="needs_review")
    assert env_needs_review["success"] is False

    env_error = _tool_envelope(status="error")
    assert env_error["success"] is False


def test_tool_outcome_model_schema_version():
    from jh.models import ToolResult
    outcome = ToolResult(status=ToolOutcome.OK, data={"res": 1})
    assert outcome.schema_version == "1.0"
    assert outcome.to_dict()["schema_version"] == "1.0"


def test_screening_input_validation():
    # Valid
    val = schemas.validate_screening_input({"job_id": "job123", "questions": ["Tell me about yourself"]})
    assert val["job_id"] == "job123"
    assert len(val["questions"]) == 1

    # Invalid empty questions
    with pytest.raises(schemas.ValidationError):
        schemas.validate_screening_input({"job_id": "job123", "questions": []})


def test_mock_interview_input_validation():
    val = schemas.validate_mock_interview_input({
        "question": "Explain Paxos",
        "candidate_answer": "Paxos is a consensus algorithm...",
        "role_level": "staff",
        "rubric": "standard"
    })
    assert val["question"] == "Explain Paxos"
    assert val["role_level"] == "staff"

    with pytest.raises(schemas.ValidationError):
        schemas.validate_mock_interview_input({
            "question": "",
            "candidate_answer": "Answer",
        })


def test_daily_digest_input_validation():
    val = schemas.validate_daily_digest_input({
        "date": "2026-10-26",
        "include_jobs": True,
        "include_interviews": False
    })
    assert val["date"] == "2026-10-26"
    assert val["include_interviews"] is False
