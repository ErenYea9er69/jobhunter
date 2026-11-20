"""Test UI Banner, Filter Strip, and Progress components (Phase F1)."""
from pathlib import Path
from jh import db, v5_tools


def test_ui_index_html_has_all_target_components():
    web_idx = Path("webapp/index.html").read_text(encoding="utf-8")
    pub_idx = Path("public/index.html").read_text(encoding="utf-8")

    assert web_idx == pub_idx

    # 1. Filter strip & edit button
    assert 'id="filter-strip"' in web_idx
    assert 'id="filter-summary-text"' in web_idx
    assert 'id="btn-edit-filter-strip"' in web_idx

    # 2. Chat question banner with questions waiting title
    assert 'id="banner-chat-question"' in web_idx
    assert 'id="banner-chat-title"' in web_idx
    assert "The AI is asking you a question in chat:" in web_idx

    # 3. Change resume button and dialog
    assert 'id="btn-change-resume"' in web_idx
    assert 'id="dlg-change-resume"' in web_idx

    # 4. Modern Radar header button
    assert 'id="btn-radar-header"' in web_idx
    assert 'id="radar-header-label"' in web_idx

    # 5. Background search progress view
    assert 'id="search-progress-view"' in web_idx
    assert 'id="progress-sources-summary"' in web_idx


def test_ui_app_js_logic_matches_target_specs():
    app_js = Path("webapp/app.js").read_text(encoding="utf-8")
    pub_js = Path("public/app.js").read_text(encoding="utf-8")

    assert app_js == pub_js

    # Radar found N new signals
    assert "Radar found ${count} new signals" in app_js

    # Progress view summary with matches
    assert "sources done • ${totalJobs} jobs found • ${state.jobs.length} matches" in app_js

    # Questions waiting in chat title
    assert "questions are waiting in the chat" in app_js


def test_jh_status_returns_questions_waiting_count():
    db.init_db()
    db.set_session_state("round_2_pending")
    st1 = v5_tools.jh_status(session_id="ui_sess_1")
    assert st1["data"]["questions_waiting_count"] == 6

    db.set_session_state("round_2_answered")
    st2 = v5_tools.jh_status(session_id="ui_sess_2")
    assert st2["data"]["questions_waiting_count"] == 0
