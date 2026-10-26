"""Integration tests for the complete 27 tools, 7 resources, and 8 prompts catalog per Sections 17, 18, 19 of newall-logic.md."""
import pytest
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from jh.filestore import FileStore
from jh.mcp_tools import register_tools_and_resources


@pytest.fixture
def mcp_server(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    jh_dir = ws / ".jobhunter"
    jh_dir.mkdir()
    fs = FileStore(jh_dir)

    server = FastMCP(name="JobHunterTest")
    register_tools_and_resources(server, fs, ws)
    return server


def test_registered_tools_count_and_names(mcp_server):
    tools = mcp_server._tool_manager._tools
    tool_names = set(tools.keys())

    expected_tools = {
        # Group 1: Resume management
        "scan_resumes", "get_resume", "list_resumes", "set_active_resume", "parse_resume_file",
        # Group 2: Job discovery
        "search_jobs", "get_saved_jobs", "get_job_details", "get_recommendations",
        # Group 3: Matching and analysis
        "score_job", "gap_report", "ats_audit",
        # Group 4: Application documents
        "compare_resumes", "tailor_resume", "cover_letter", "export_resume", "solve_screening_questions",
        # Group 5: Interview and outreach
        "interview_prep", "outreach_message", "evaluate_mock_interview",
        # Group 6: Sources and operations
        "source_health",
        # Group 7: Application CRM and settings
        "track_application", "list_applications", "update_application", "application_stats", "daily_digest", "configure"
    }

    assert len(expected_tools) == 27
    missing = expected_tools - tool_names
    assert not missing, f"Missing registered tools: {missing}"
    assert len(tools) == 27


def test_registered_resources_count_and_names(mcp_server):
    resources = mcp_server._resource_manager._resources
    resource_templates = mcp_server._resource_manager._templates
    all_uris = set(resources.keys()) | set(resource_templates.keys())

    assert "jobhunter://resumes" in all_uris
    assert "jobhunter://applications" in all_uris
    assert "jobhunter://jobs/latest" in all_uris
    assert "jobhunter://config" in all_uris
    assert "jobhunter://sources" in all_uris
    # Template URIs
    template_uris = {t.uri_template for t in resource_templates.values()}
    assert any("evidence" in t for t in template_uris) or "jobhunter://evidence/{name}" in all_uris
    assert any("resumes/{name}" in t for t in template_uris) or "jobhunter://resumes/{name}" in all_uris


def test_registered_prompts_count_and_names(mcp_server):
    prompts = mcp_server._prompt_manager._prompts
    prompt_names = set(prompts.keys())

    expected_prompts = {
        "resume_tailor",
        "cover_letter",
        "interview_prep",
        "screening_question_solver",
        "recruiter_outreach",
        "mock_interview_evaluator",
        "career_skill_roadmap",
        "application_follow_up",
    }
    assert len(expected_prompts) == 8
    missing = expected_prompts - prompt_names
    assert not missing, f"Missing registered prompts: {missing}"
    assert len(prompts) == 8
