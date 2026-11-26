"""Tests for D10: Save gate enforcement (saved_by == 'ui') on tailor_resume,
cover_letter, outreach_message, and score_fit.
"""
import pytest
from jh import config, db, ticket_manager
from jh import mcp_tools


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    from jh import worker_launcher
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()
    yield
    try:
        worker_launcher.stop_worker()
    except Exception:
        pass


def test_d10_tools_reject_unsaved_jobs(tmp_path, monkeypatch):
    import mcp_server
    import asyncio
    import json

    # Insert an unsaved job (saved_by is empty)
    with db.session() as c:
        c.execute("""
            INSERT INTO jobs (id, job_key, title, company, location, freshness_state, job_json, created_at, updated_at, saved_by)
            VALUES ('job_unsaved_1', 'key_u_1', 'Backend Dev', 'TechCorp', 'Tunis', 'active', '{}', '2026-11-24', '2026-11-24', '')
        """)

    srv = mcp_server.create_server(str(tmp_path))

    def call_tool(name, **kwargs):
        res = asyncio.run(srv.call_tool(name, kwargs))
        blocks = res[0] if isinstance(res, tuple) else res
        return json.loads(blocks[0].text)

    res = call_tool("tailor_resume", job_id="job_unsaved_1")
    assert res["data"]["status"] == "not_saved"
    assert res["data"]["success"] is False

    c_res = call_tool("cover_letter", job_id="job_unsaved_1")
    assert c_res["data"]["status"] == "not_saved"
    assert c_res["data"]["success"] is False

    o_res = call_tool("outreach_message", job_id="job_unsaved_1")
    assert o_res["data"]["status"] == "not_saved"
    assert o_res["data"]["success"] is False

    s_res = call_tool("score_fit", job_id="job_unsaved_1")
    assert s_res["data"]["status"] == "not_saved"
    assert s_res["data"]["success"] is False


def test_d10_ui_save_endpoint_sets_saved_by_ui(monkeypatch):
    # Insert a job
    with db.session() as c:
        c.execute("""
            INSERT INTO jobs (id, job_key, title, company, location, freshness_state, job_json, created_at, updated_at, saved_by)
            VALUES ('job_save_2', 'key_s_2', 'Backend Dev', 'TechCorp', 'Tunis', 'active', '{}', '2026-11-24', '2026-11-24', '')
        """)

    assert db.is_job_saved_by_ui("job_save_2") is False

    # Simulate UI Save click marking saved_by='ui'
    db.mark_job_saved_by_ui("job_save_2")
    assert db.is_job_saved_by_ui("job_save_2") is True
