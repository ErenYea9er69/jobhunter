"""Tests for Claude Desktop MCP tailoring workflow without web UI save locks."""
import asyncio
import json
import pytest

from jh import config, db


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    test_db = tmp_path / "test_state"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir(exist_ok=True)
    (resumes_dir / "candidate.txt").write_text(
        "Jane Doe\njane@example.com\n\nSUMMARY\nBackend Engineer with 5 years in Python, FastAPI, PostgreSQL.\n\nEXPERIENCE\nSenior Backend Engineer, TechCorp, 2021-Present\n- Built REST APIs in Python and FastAPI.\n",
        encoding="utf-8",
    )
    db.init_db()
    return tmp_path


def test_tailoring_and_scoring_work_directly_without_ui_save_gate(tmp_path):
    import mcp_server

    with db.session() as c:
        c.execute("""
            INSERT INTO jobs (id, job_key, title, company, location, freshness_state, job_json, created_at, updated_at, saved_by)
            VALUES ('job_direct_1', 'key_d_1', 'Backend Dev', 'TechCorp', 'Tunis', 'active', '{"title":"Backend Dev","company":"TechCorp","description":"Python FastAPI engineer"}', '2026-11-24', '2026-11-24', '')
        """)

    srv = mcp_server.create_server(str(tmp_path))

    def call_tool(name, **kwargs):
        res = asyncio.run(srv.call_tool(name, kwargs))
        blocks = res[0] if isinstance(res, tuple) else res
        return json.loads(blocks[0].text)

    s_res = call_tool("score_fit", job_id="job_direct_1")
    assert s_res["success"] is True

    t_res = call_tool("tailor_resume", job_id="job_direct_1")
    assert t_res["success"] is True
    assert "tailored_resume" in t_res["data"]

    c_res = call_tool("cover_letter", job_id="job_direct_1")
    assert c_res["success"] is True
    assert "letter" in c_res["data"]

    o_res = call_tool("outreach_message", job_id="job_direct_1")
    assert o_res["success"] is True
