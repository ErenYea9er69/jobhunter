"""Phase B14 Tests: Outreach Ledger, Already Contacted Gate, Daily Cap, Follow-ups, Call Prep Pack, and Weekly Report."""
import datetime
import io
import json
import os
import time
from pathlib import Path

import pytest

from jh import config, db, outreach_ledger
from jh.httpd import JobHunterRequestHandler


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()

    # Seed profile
    db.save_profile({
        "name": "Alex Mercer",
        "email": "alex@mercer.dev",
        "years": 6,
        "skills": ["Python", "Rust", "Distributed Systems"],
    })
    return test_home


def test_already_contacted_gate_and_four_day_followup_at27():
    """Already contacted gate skips if <90d unless 4 days passed with no reply (allowing 1 follow-up) (Acceptance Test 27)."""
    contact = db.save_contact({
        "name": "Sarah Lead",
        "company": "Scale Fast",
        "email": "sarah@scalefast.io",
    })
    cid = contact["id"]

    # 1. Never contacted -> allowed
    check1 = outreach_ledger.check_already_contacted(cid)
    assert check1["allowed"] is True
    assert check1["reason"] == "never_contacted"

    # 2. Contacted 1 day ago -> blocked by 4-day cooldown
    out = db.log_outreach(contact_id=cid, company="Scale Fast", status="sent", recipient_email="sarah@scalefast.io")
    one_day_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
    with db.session() as c:
        c.execute("UPDATE outreach SET sent_at=? WHERE id=?", (one_day_ago, out["id"]))

    check2 = outreach_ledger.check_already_contacted(cid)
    assert check2["allowed"] is False
    assert check2["reason"] == "cooldown_active"
    assert check2["days_remaining"] > 0

    # 3. Contacted 5 days ago with no reply -> allowed for ONE follow-up
    five_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)).isoformat()
    with db.session() as c:
        c.execute("UPDATE outreach SET sent_at=? WHERE id=?", (five_days_ago, out["id"]))

    check3 = outreach_ledger.check_already_contacted(cid)
    assert check3["allowed"] is True
    assert check3["can_follow_up"] is True
    assert check3["reason"] == "follow_up_allowed"

    # 4. After sending follow-up, max 1 follow-up reached -> blocked
    with db.session() as c:
        c.execute("UPDATE outreach SET follow_up_sent_at=? WHERE id=?", (five_days_ago, out["id"]))

    check4 = outreach_ledger.check_already_contacted(cid)
    assert check4["allowed"] is False
    assert check4["reason"] == "follow_up_limit_reached"


def test_daily_cap_and_tomorrow_queue_at27():
    """Daily cap default 20: if >= cap queue for tomorrow, resets daily (Acceptance Test 27)."""
    db.set_setting("daily_cap", "3")  # Test with small cap of 3
    today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    # Initial state: 0 sent
    cap_info = outreach_ledger.check_daily_cap()
    assert cap_info["daily_cap"] == 3
    assert cap_info["sent_today_count"] == 0
    assert cap_info["remaining_cap"] == 3
    assert cap_info["under_cap"] is True

    # Send 3 emails today to reach cap
    for i in range(3):
        out = db.log_outreach(contact_id=f"ct_{i}", company="Acme", status="sent")
        with db.session() as c:
            c.execute("UPDATE outreach SET sent_at=? WHERE id=?", (f"{today_str} 10:0{i}:00", out["id"]))

    # Now cap is reached
    cap_full = outreach_ledger.check_daily_cap()
    assert cap_full["sent_today_count"] == 3
    assert cap_full["remaining_cap"] == 0
    assert cap_full["under_cap"] is False

    # New draft is queued for tomorrow
    new_draft = db.log_outreach(contact_id="ct_new", company="Acme", status="draft")
    q_res = outreach_ledger.queue_or_allow_draft(new_draft["id"])
    assert q_res["queued"] is True
    assert q_res["status"] == "queued"


def test_mark_sent_sets_four_day_followup_at28():
    """Marking sent sets follow_up_due = today + 4d (Acceptance Test 28)."""
    contact = db.save_contact({
        "name": "Elena Fisher",
        "company": "Uncharted Tech",
        "email": "elena@uncharted.com",
    })
    out = db.log_outreach(contact_id=contact["id"], company="Uncharted Tech", status="draft")

    sent_row = outreach_ledger.mark_outreach_sent(out["id"])
    assert sent_row["status"] == "sent"
    assert sent_row["sent_at"] is not None
    assert sent_row["follow_up_due"] is not None

    # Check date difference is approximately 4 days
    sent_dt = datetime.datetime.fromisoformat(sent_row["sent_at"].replace("Z", "+00:00"))
    due_dt = datetime.datetime.fromisoformat(sent_row["follow_up_due"].replace("Z", "+00:00"))
    diff_days = (due_dt - sent_dt).total_seconds() / 86400.0
    assert 3.9 <= diff_days <= 4.1


def test_reply_tracking_triggers_call_prep_pack_at28():
    """Marking replied triggers call prep pack from learning pack (Acceptance Test 28)."""
    # Seed company brief & learning pack
    db.save_company_brief(
        company="Vanguard Labs",
        brief_data={"summary": "Next-gen platform engineering tools", "stage": "Series A"},
        learning_pack_data={
            "talking_points": ["Discuss distributed raft consensus", "Experience with high concurrency"],
            "smart_questions": ["What is your main scaling challenge?"],
        },
        signal_id="sig_vanguard",
    )

    contact = db.save_contact({
        "name": "Dr. Vance",
        "company": "Vanguard Labs",
        "email": "vance@vanguard.io",
    })
    out = db.log_outreach(contact_id=contact["id"], signal_id="sig_vanguard", company="Vanguard Labs", status="sent")

    # Record positive reply
    reply_res = outreach_ledger.record_reply(out["id"], sentiment="positive")
    assert reply_res["success"] is True
    assert reply_res["status"] == "replied"
    assert "call_prep_pack" in reply_res

    cpp = reply_res["call_prep_pack"]
    assert cpp["company"] == "Vanguard Labs"
    assert cpp["contact_name"] == "Dr. Vance"
    assert len(cpp["talking_points"]) >= 2
    assert len(cpp["questions_to_ask"]) >= 1
    assert len(cpp["questions_to_expect"]) >= 2


def test_weekly_report_metrics_and_suggestion_at28():
    """Weekly report returns counts, breakdown, and 1 suggested change (Acceptance Test 28)."""
    # Seed some signals and outreach rows
    sig = db.ingest_signal({"source": "hn", "company": "HN Corp", "url": "https://news.ycombinator.com/item?id=1"})
    out1 = db.log_outreach(contact_id="c1", signal_id=sig["id"], company="HN Corp", status="replied", attached=1)
    with db.session() as c:
        c.execute("UPDATE outreach SET sent_at=datetime('now'), replied_at=datetime('now') WHERE id=?", (out1["id"],))

    report = outreach_ledger.generate_weekly_report()
    assert report["success"] is True
    assert "total_sent" in report
    assert "total_replied" in report
    assert "overall_reply_rate" in report
    assert "by_attachment" in report
    assert "by_source" in report
    assert "suggested_change" in report
    assert len(report["suggested_change"]) > 10
    assert "notice" in report
    assert "CAN-SPAM" in report["notice"]


def test_outreach_http_endpoints():
    """Test all REST outreach endpoints: GET /today, GET /queue, POST /mark_sent, POST /reply, GET /report."""
    class FakeServer:
        def __init__(self):
            self.ws_dir = Path.cwd()

    def call_api(method: str, path: str, body: dict = None):
        raw_body = json.dumps(body).encode("utf-8") if body else b""
        rfile = io.BytesIO(raw_body)
        wfile = io.BytesIO()

        handler = JobHunterRequestHandler.__new__(JobHunterRequestHandler)
        handler.rfile = rfile
        handler.wfile = wfile
        handler.server = FakeServer()
        handler.path = path
        handler.command = method
        handler.headers = {
            "Content-Length": str(len(raw_body)),
            "Content-Type": "application/json",
        }
        handler.close_connection = True
        status_code = [200]
        handler.send_response = lambda code, msg=None: status_code.__setitem__(0, code)
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None

        if method == "GET":
            handler.do_GET()
        elif method == "POST":
            handler.do_POST()

        wfile.seek(0)
        output = wfile.read()
        return status_code[0], json.loads(output.decode("utf-8")) if output else {}

    # 1. GET /api/outreach/today
    code, res_today = call_api("GET", "/api/outreach/today")
    assert code == 200
    assert "cap" in res_today["data"]

    # 2. GET /api/outreach/queue
    code, res_queue = call_api("GET", "/api/outreach/queue")
    assert code == 200
    assert "queue" in res_queue["data"]

    # 3. POST /api/outreach/mark_sent
    out = db.log_outreach(contact_id="c_test_http", company="Test Corp", status="draft")
    code, res_sent = call_api("POST", "/api/outreach/mark_sent", {"outreach_id": out["id"]})
    assert code == 200
    assert res_sent["data"]["status"] == "sent"

    # 4. POST /api/outreach/reply
    code, res_rep = call_api("POST", "/api/outreach/reply", {"outreach_id": out["id"], "sentiment": "positive"})
    assert code == 200
    assert res_rep["data"]["status"] == "replied"
    assert "call_prep_pack" in res_rep["data"]

    # 5. GET /api/outreach/report
    code, res_rep = call_api("GET", "/api/outreach/report")
    assert code == 200
    assert "suggested_change" in res_rep["data"]
