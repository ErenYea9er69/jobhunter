"""Phase B12 Tests: Contact Finder (Decision Makers), Confidence Labels, Exclusions, & Deletion."""
import os
import time
from unittest.mock import patch, MagicMock

import pytest

from jh import config, contacts, db


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()
    return test_home


def test_contact_provider_hunter_cache_and_quota(monkeypatch):
    """Hunter API adapter caches domain search in SQLite for 30 days and tracks quota."""
    adapter = contacts.HunterAdapter(api_key="test_key_123")
    assert adapter.is_available() is True

    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.headers = {
        "X-RateLimit-Limit": "25",
        "X-RateLimit-Remaining": "24",
        "X-RateLimit-Reset": str(time.time() + 86400),
    }
    fake_response.text = '{"data": {"emails": [{"first_name": "Alice", "last_name": "Smith", "position": "VP Engineering", "value": "alice@startup.io", "confidence": 85}]}, "meta": {}}'

    with patch("jh.contacts._http_get", return_value=fake_response) as mock_http:
        # First call fetches from API
        res1 = adapter.domain_search("startup.io")
        assert len(res1) == 1
        assert res1[0]["email"] == "alice@startup.io"
        assert res1[0]["confidence"] == "Found"
        assert mock_http.call_count == 1

        # Second call hits 30-day SQLite cache
        res2 = adapter.domain_search("startup.io")
        assert len(res2) == 1
        assert res2[0]["email"] == "alice@startup.io"
        assert mock_http.call_count == 1  # Not called again!

    # Verify quota tracked in DB
    assert db.get_setting("hunter_quota_limit") == "25"
    assert db.get_setting("hunter_quota_remaining") == "24"


def test_size_rules_decision_makers():
    """Target titles mapped strictly by company size:

    - Under 30: Founder, CEO, signal poster.
    - 30-200: Head of function, VP, team lead, poster.
    - Over 200: Team lead, hiring manager, recruiter. NEVER CEO.
    """
    # Under 30 (<30): Founder/CEO allowed
    ok_founder, _, _ = contacts.matches_size_rules("Founder & CEO", company_size=15)
    assert ok_founder is True

    # 30 to 200: VP/Head/Lead allowed
    ok_vp, _, _ = contacts.matches_size_rules("VP of Engineering", company_size=80)
    assert ok_vp is True

    # Over 200: Recruiter/Engineering Manager allowed
    ok_recruiter, _, _ = contacts.matches_size_rules("Technical Recruiter", company_size=300)
    assert ok_recruiter is True
    ok_em, _, _ = contacts.matches_size_rules("Engineering Manager", company_size=500)
    assert ok_em is True

    # Over 200: NEVER CEO
    disallowed_ceo, _, reason = contacts.matches_size_rules("Chief Executive Officer", company_size=500)
    assert disallowed_ceo is False
    assert reason == "disallowed_seniority"


def test_public_fallback_notice_when_no_api_key():
    """When no API key is set, public adapter is used and limits notice is included."""
    with patch.dict(os.environ, {"HUNTER_API_KEY": ""}, clear=True):
        db.set_setting("hunter_api_key", "")
        with patch("jh.email_finder.query_mx_records", return_value={"has_mx": True, "provider": "Google Workspace"}):
            res = contacts.find_contacts("Acme Corp")
            assert res["success"] is True
            assert res["provider_used"] == "public_pages"
            assert any("Finding emails from public pages is limited" in n for n in res["notices"])


def test_mx_record_check_drops_email_and_provides_alternative_routes():
    """If MX check fails, drop email address and provide alternative routes (Acceptance Test 25)."""
    with patch("jh.email_finder.query_mx_records", return_value={"has_mx": False}):
        contact_in = {
            "name": "Jane Doe",
            "company": "FailingDomain",
            "company_domain": "failingdomain.xyz",
            "email": "jane@failingdomain.xyz",
            "confidence": "Found",
            "linkedin_url": "https://linkedin.com/in/janedoe",
            "x_handle": "@janedoe",
        }
        verified = contacts.verify_and_label(contact_in)
        # Email dropped!
        assert verified["email"] == ""
        assert verified["confidence"] == "Guess"
        # Alternative routes present and labeled not an email
        routes = verified.get("alternative_routes", [])
        assert len(routes) >= 2
        assert any(r["channel"] == "LinkedIn" and r["is_email"] is False for r in routes)
        assert any(r["channel"] == "X (Twitter)" and r["is_email"] is False for r in routes)


def test_exclusions_unrelated_employer_cooldown_dnc():
    """Verify exclusions for unrelated functions, current employer, 90-day cooldown, and DNC domains."""
    # 1. Unrelated function
    unrelated = {"title": "General Counsel & Legal Advisor", "company": "Test Co", "email": "legal@test.co"}
    is_ex, reason = contacts.is_excluded(unrelated)
    assert is_ex is True
    assert reason == "unrelated_function"

    # 2. Candidate current employer
    emp_contact = {"title": "VP Engineering", "company": "ExistingEmployer Inc", "email": "lead@existing.com"}
    is_ex, reason = contacts.is_excluded(emp_contact, candidate_current_employer="ExistingEmployer Inc")
    assert is_ex is True
    assert reason == "candidate_current_employer"

    # 3. Contacted in past 90 days
    db.log_outreach(
        contact_id="ct_old",
        company="Recent Co",
        status="sent",
        recipient_email="already@recent.com",
    )
    with db.session() as c:
        # Set sent_at to 10 days ago
        sent_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 10 * 86400))
        c.execute("UPDATE outreach SET sent_at=? WHERE contact_id='ct_old'", (sent_iso,))

    contacted_contact = {"title": "VP Tech", "company": "Recent Co", "email": "already@recent.com"}
    is_ex, reason = contacts.is_excluded(contacted_contact)
    assert is_ex is True
    assert reason == "contacted_in_past_90_days"

    # 4. Do-not-contact domains
    dnc_contact = {"title": "Lead", "company": "Blocked Co", "company_domain": "blocked.com", "email": "hi@blocked.com"}
    is_ex, reason = contacts.is_excluded(dnc_contact, do_not_contact_domains={"blocked.com"})
    assert is_ex is True
    assert reason == "do_not_contact_domain"


def test_contacts_ranked_and_capped_at_three():
    """Returns at most 3 contacts ranked by title match, reachability, closeness (Acceptance Test 25)."""
    fake_contacts = [
        {"name": "Alice Recruiter", "title": "Recruiter", "email": "alice@startup.io", "confidence": "Pattern"},
        {"name": "Bob Founder", "title": "Founder & CEO", "email": "bob@startup.io", "confidence": "Found"},
        {"name": "Charlie Lead", "title": "Tech Lead", "email": "charlie@startup.io", "confidence": "Pattern"},
        {"name": "Diana Engineer", "title": "Junior Engineer", "email": "diana@startup.io", "confidence": "Guess"},
    ]
    with patch.object(contacts.HunterAdapter, "is_available", return_value=True):
        with patch.object(contacts.HunterAdapter, "domain_search", return_value=fake_contacts):
            with patch("jh.email_finder.query_mx_records", return_value={"has_mx": True, "provider": "Google Workspace"}):
                res = contacts.find_contacts("Startup Co", company_size=15)
                assert res["success"] is True
                assert len(res["contacts"]) <= 3
                # Founder should be ranked first for company size 15
                assert res["contacts"][0]["name"] == "Bob Founder"
                assert res["contacts"][0]["email_confidence"] == "Found"


def test_delete_contact_and_history_acceptance_test_37():
    """Delete contact and history removes contact and all associated outreach rows from SQLite (Acceptance Test 37)."""
    contact = db.save_contact({
        "name": "Sarah Connor",
        "company": "Cyberdyne Systems",
        "email": "sarah@cyberdyne.com",
        "role": "Resistance Lead",
    })
    cid = contact["id"]
    out1 = db.log_outreach(contact_id=cid, company="Cyberdyne Systems", status="draft")
    out2 = db.log_outreach(contact_id=cid, company="Cyberdyne Systems", status="sent")

    # Verify rows exist
    assert db.get_contact(cid) is not None
    assert len(db.get_outreach_for_contact(cid)) == 2

    # Delete contact and history
    ok = contacts.delete_contact_and_history(cid)
    assert ok is True

    # Verify contact is deleted
    assert db.get_contact(cid) is None
    # Verify associated outreach rows are deleted
    assert len(db.get_outreach_for_contact(cid)) == 0


def test_jh_find_contacts_tool_envelope():
    """jh_find_contacts returns valid MCP envelope."""
    with patch("jh.email_finder.query_mx_records", return_value={"has_mx": True, "provider": "Google Workspace"}):
        res = contacts.jh_find_contacts("Innovate Labs")
        assert "data" in res or "contacts" in res
        if "data" in res:
            assert res["status"] == "ok"
            assert "contacts" in res["data"]


def test_contacts_http_endpoints():
    """Verify GET, POST, and DELETE /api/contacts endpoints."""
    import io
    import json
    from pathlib import Path
    from jh.httpd import JobHunterRequestHandler

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
        elif method == "DELETE":
            handler.do_DELETE()

        wfile.seek(0)
        output = wfile.read()
        return status_code[0], json.loads(output.decode("utf-8")) if output else {}

    # Save a contact directly
    c = db.save_contact({"name": "Http Contact", "company": "API Corp", "email": "http@api.com"})
    cid = c["id"]

    # 1. GET /api/contacts
    code, res = call_api("GET", f"/api/contacts?company=API Corp")
    assert code == 200
    assert res["status"] == "ok"
    assert len(res["data"]["contacts"]) >= 1

    # 2. DELETE /api/contacts?id=...
    code, del_res = call_api("DELETE", f"/api/contacts?id={cid}")
    assert code == 200
    assert del_res["data"]["deleted"] is True
    assert db.get_contact(cid) is None
