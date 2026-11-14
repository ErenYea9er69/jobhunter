"""Tests for Phase B11: Company research, factual briefs with source URLs, and learning pack generation."""
import os
import pytest

from jh import config, db
from jh.company_research import (
    build_company_brief,
    build_learning_pack,
    research_saved_signal,
    verify_signal_liveness,
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()
    return test_home


def test_company_brief_facts_only_and_source_urls():
    # Acceptance test 24:
    # Saving a signal builds a company brief with a source URL on each claim, and no invented fact.
    signal = {
        "id": "sig_facts_1",
        "company": "Supabase",
        "url": "https://news.ycombinator.com/item?id=9999",
        "type": "hiring_post",
        "stage": "series B",
        "funding_amount": "$80M",
        "funding_round": "Series B",
        "author_name": "Paul Copplestone",
        "text": "Supabase raises $80M Series B led by Felicis. We are 60 people building open source Firebase.",
    }
    profile = {
        "target_title": "Database Engineer",
        "skills": ["PostgreSQL", "Go", "Docker"],
        "experience": [
            {"bullets": ["Architected distributed PostgreSQL clusters", "Scaled write throughput by 3x"]}
        ],
    }

    brief = build_company_brief(signal, profile)
    assert brief["company"] == "Supabase"

    # Every claim has a source_url
    assert brief["product_summary"]["source_url"] == "https://news.ycombinator.com/item?id=9999"
    assert brief["funding"]["amount"] == "$80M"
    assert brief["funding"]["investors"] == "Felicis"
    assert brief["funding"]["source_url"] == "https://news.ycombinator.com/item?id=9999"
    assert brief["team"]["size"] == "60"
    assert brief["team"]["key_person"] == "Paul Copplestone"

    # When field is missing, writes 'unknown', never invents
    empty_signal = {
        "id": "sig_empty",
        "company": "Stealth AI",
        "url": "https://example.com/post",
        "text": "Looking for engineers.",
    }
    brief_unknowns = build_company_brief(empty_signal, profile)
    assert brief_unknowns["stage"]["claim"] == "unknown"
    assert brief_unknowns["funding"]["amount"] == "unknown"
    assert brief_unknowns["funding"]["investors"] == "unknown"
    assert brief_unknowns["team"]["size"] == "unknown"


def test_learning_pack_structure():
    signal = {
        "id": "sig_pack",
        "company": "Vercel",
        "text": "Hiring Frontend Engineers for Next.js and Turbopack. Must know Rust, React, and WebAssembly.",
    }
    profile = {
        "target_title": "Senior Frontend Engineer",
        "skills": ["React", "TypeScript", "Node.js"],
        "experience": [
            {"bullets": [
                "Led frontend migration to Next.js App Router",
                "Reduced bundle size by 40% via code splitting",
                "Built accessible component design system",
                "Mentored 4 junior frontend developers",
            ]},
        ],
        "proof_points": [
            {"project": "Next.js redesign", "metric": "Improved Lighthouse score from 54 to 98"}
        ]
    }
    brief = build_company_brief(signal, profile)
    pack = build_learning_pack(brief, signal, profile)

    # 3 smart questions
    assert len(pack["questions"]) == 3
    assert all(isinstance(q, str) and len(q) > 10 for q in pack["questions"])

    # Skill gaps and study list
    assert "Rust" in pack["skill_gaps"] or "WebAssembly" in pack["skill_gaps"]
    assert len(pack["study_list"]) >= 1

    # 5 interview talking points
    assert len(pack["talking_points"]) == 5

    # 5-line product summary
    assert len(pack["product_summary"]) == 5
    assert pack["product_summary"][0].startswith("1. Company: Vercel")


def test_research_saved_signal_end_to_end(monkeypatch):
    sig = {
        "id": "sig_e2e_1",
        "company": "Linear",
        "url": "https://linear.app/careers",
        "type": "hiring_post",
        "text": "Building the future of product development. Series B company.",
    }
    db.ingest_signal(sig)

    # Mock liveness check to return True
    monkeypatch.setattr("jh.lifecycle.liveness_check", lambda url, job_id=None: {"is_live": True})

    res = research_saved_signal(sig)
    assert res["status"] == "ok"
    assert res["company"] == "Linear"

    # Verify saved in SQLite company_briefs
    stored_brief = db.get_company_brief("Linear")
    assert stored_brief is not None
    assert "questions" in stored_brief["learning_pack"]
    assert len(stored_brief["learning_pack"]["questions"]) == 3

    # Check signal status updated to 'saved'
    sig_db = db.get_signal("sig_e2e_1")
    assert sig_db["status"] == "saved"


def test_research_skips_closed_post(monkeypatch):
    sig = {
        "id": "sig_closed_1",
        "company": "DeadStartup",
        "url": "https://example.com/closed-job",
        "type": "hiring_post",
    }
    db.ingest_signal(sig)

    # Mock liveness check to return False
    monkeypatch.setattr("jh.lifecycle.liveness_check", lambda url, job_id=None: {"is_live": False, "reason": "HTTP 404"})

    res = research_saved_signal(sig)
    assert res["status"] == "closed"
    assert "closed" in res["message"].lower()
