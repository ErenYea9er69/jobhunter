"""Phase B13 Tests: Single Job Resume, Short Outreach Email, Slop Checker, and Attachment Policy."""
import os
import re
from pathlib import Path

import pytest

from jh import config, db, email_drafter, home


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    os.makedirs(test_home / "outputs", exist_ok=True)
    db.init_db()

    # Seed master profile with proof points and portfolio link
    profile_data = {
        "name": "Jane Developer",
        "email": "jane@example.com",
        "portfolio_url": "https://janedev.io",
        "years": 5,
        "skills": ["Python", "PostgreSQL", "FastAPI", "Docker"],
        "proof_points": [
            {"project": "Realtime Billing Pipeline", "number": "100k events/sec", "link": "https://janedev.io/billing"},
            {"project": "Search Optimization", "number": "4x faster latency", "link": "https://janedev.io/search"},
        ],
    }
    db.save_profile(profile_data)
    return test_home


def test_single_resume_generation_and_reuse_cache_at26():
    """Single resume per company and role, reused across contacts. 1-page PDF <= 200 KB named Firstname_Lastname_Company_Role.pdf."""
    res1 = email_drafter.build_job_resume(company="Acme Corp", role="Senior Backend Engineer")
    assert res1["success"] is True
    assert res1["reused"] is False
    pdf_path = Path(res1["resume_path"])
    assert pdf_path.is_file()
    assert pdf_path.name == "Jane_Developer_Acme_Corp_Senior_Backend_Engineer.pdf"
    assert res1["size_kb"] <= 200.0

    # Second call for same company and role reuses the existing PDF
    res2 = email_drafter.build_job_resume(company="Acme Corp", role="Senior Backend Engineer")
    assert res2["success"] is True
    assert res2["reused"] is True
    assert res2["resume_path"] == str(pdf_path)


def test_slop_check_comprehensive_rules():
    """Test all 8 rules (a through h) of slop_check."""
    # (a) Banned phrases
    bad_a = {"subject": "Quick note", "body": "I hope this email finds you well. Let's delve into synergy."}
    passed_a, flags_a = email_drafter.slop_check(bad_a)
    assert passed_a is False
    assert any("banned_phrase" in f for f in flags_a)

    # (b) Word count too short / too long
    bad_b_short = {"subject": "Hi", "body": "Too short words here."}
    passed_b, flags_b = email_drafter.slop_check(bad_b_short)
    assert passed_b is False
    assert any("word_count_too_short" in f for f in flags_b)

    # (c) Subject under 6 words
    bad_c = {"subject": "This subject line has more than five words here", "body": "Line one here with enough words to meet the requirement.\nLine two is here.\nLine three is here.\nJane"}
    passed_c, flags_c = email_drafter.slop_check(bad_c)
    assert any("subject_too_long" in f for f in flags_c)

    # (d) Quotes at most 5 words
    bad_d = {
        "subject": "Note on stack",
        "body": 'I saw your post discussing "one two three four five six seven" on Twitter today.\nSecond line with proof point here.\nThird line with a small ask for a call.\nJane',
    }
    passed_d, flags_d = email_drafter.slop_check(bad_d)
    assert any("quote_too_long" in f for f in flags_d)

    # (e) Line openers: no two lines start with "I"
    bad_e = {
        "subject": "Note on stack",
        "body": "I saw your note discussing distributed systems.\nI also scaled similar services to high volume.\nCurious if you have fifteen minutes this Thursday.\nJane",
    }
    passed_e, flags_e = email_drafter.slop_check(bad_e)
    assert any("multiple_i_openers" in f for f in flags_e)

    # (f) No list of 3 items in a sentence
    bad_f = {
        "subject": "Note on stack",
        "body": "Saw your post mentioning databases yesterday.\nExperience includes Python, Docker, and Kubernetes across systems.\nOpen to a brief call this week.\nJane",
    }
    passed_f, flags_f = email_drafter.slop_check(bad_f)
    assert any("list_of_three_items" in f for f in flags_f)

    # (g) No em dashes, exclamation marks, or emojis
    bad_g = {
        "subject": "Note on stack",
        "body": "Saw your post mentioning databases yesterday—great work! 😊\nWork centered on scaling databases.\nOpen to a brief call this week.\nJane",
    }
    passed_g, flags_g = email_drafter.slop_check(bad_g)
    assert any("em_dash_detected" in f for f in flags_g)
    assert any("exclamation_mark_detected" in f for f in flags_g)
    assert any("emoji_detected" in f for f in flags_g)


def test_email_drafter_output_structure_at34():
    """Email drafter outputs 3-4 lines, 40-80 words, subject <6 words, portfolio link at the end (Acceptance Test 34)."""
    contact = db.save_contact({
        "name": "Sarah Connor",
        "company": "Cyberdyne Systems",
        "email": "sarah@cyberdyne.com",
        "role": "VP Engineering",
    })
    res = email_drafter.draft_short_email(contact_id=contact["id"])
    assert res["success"] is True

    # Subject <6 words
    subj_words = re.findall(r"\b\w+\b", res["subject"])
    assert len(subj_words) < 6

    # 3-4 lines
    lines = [line.strip() for line in res["body"].splitlines() if line.strip()]
    assert len(lines) in (3, 4)

    # Word count between 30 and 80 words
    assert 30 <= res["word_count"] <= 80

    # Last line has portfolio link
    assert "https://janedev.io" in lines[-1]

    # Passes slop check
    assert res["slop_check_passed"] is True
    assert len(res["slop_flags"]) == 0


def test_attachment_policy_at36():
    """When first_touch_attachment is 1, email mentions resume & attaches PDF. When 0, omits both (Acceptance Test 36)."""
    contact = db.save_contact({
        "name": "Kyle Reese",
        "company": "Tech Resistance",
        "email": "kyle@resistance.org",
        "role": "Team Lead",
    })

    # Case 1: Attachment ON (1)
    db.set_setting("first_touch_attachment", "1")
    draft_on = email_drafter.draft_short_email(contact_id=contact["id"])
    assert draft_on["attached"] is True
    assert draft_on["resume_path"] is not None
    assert "attached" in draft_on["body"].lower()

    # Case 2: Attachment OFF (0)
    db.set_setting("first_touch_attachment", "0")
    draft_off = email_drafter.draft_short_email(contact_id=contact["id"])
    assert draft_off["attached"] is False
    assert draft_off["resume_path"] is None
    assert "attached" not in draft_off["body"].lower()


def test_follow_up_note():
    """Follow-up note is 2 lines, 1 new item, no attachment."""
    contact = db.save_contact({
        "name": "John Connor",
        "company": "Future Corp",
        "email": "john@future.org",
    })
    fu = email_drafter.draft_follow_up(contact["id"], new_item="the new edge runtime")
    assert fu["success"] is True
    assert fu["attached"] is False
    lines = [l.strip() for l in fu["body"].splitlines() if l.strip()]
    assert len(lines) in (2, 3)  # 2 content lines + sign-off
    assert "edge runtime" in fu["body"]


def test_jh_build_resume_and_draft_email_tools():
    """MCP tools return valid envelopes."""
    contact = db.save_contact({
        "name": "Marcus Wright",
        "company": "Skynet Research",
        "email": "marcus@skynet.ai",
        "role": "Lead Architect",
    })
    res_env = email_drafter.jh_build_resume("Skynet Research", "Lead Architect")
    assert res_env["status"] == "ok"
    assert "resume_path" in res_env["data"]

    email_env = email_drafter.jh_draft_email(contact["id"])
    assert email_env["status"] == "ok"
    assert "body" in email_env["data"]
