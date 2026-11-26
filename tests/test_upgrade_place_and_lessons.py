"""Upgrade regression and specification tests for Steps 2-3 Place Rules and Lessons A-E.

Covers:
1. Steps 2-3 Place Rules (no resume place guessing, omitted/skipped place refusal,
   explicit place confirmation & SQL filtering in db.query_jobs).
2. Lesson A (role_inference title_family guesses, Step 5 optional preferences in jh_answer).
3. Lesson B (honest match soft_gap vs hard_gap, weak-match Save anyway, resume buzzword scrubbing).
4. Lesson C (interview prep story & rounds, non-scraped Glassdoor URL, practice_interview MCP tool).
5. Lesson D (side_work stored in confirmed_facts and included only when confirmed).
6. Lesson E (jh_status preserves fields and adds calm factual pacing_note).
"""
from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path

import pytest

import mcp_server
from jh import (
    company_research,
    config,
    db,
    exporters,
    home,
    interview_questions,
    lifecycle,
    preferences,
    radar,
    refit,
    resume_checker,
    resume_parser,
    role_inference,
    save_flow,
    scoring,
    ticket_manager,
    v5_tools,
    worker_launcher,
)
from jh.team import qa, roles

LYON_RESUME_TEXT = """Camille Moreau
camille.moreau@example.com | +33 6 12 34 56 78 | Lyon, France
linkedin.com/in/camillemoreau | github.com/cmoreau

SUMMARY
Backend Software Engineer with 3 years of experience building Python and FastAPI APIs, PostgreSQL databases, and Docker services.
Langues: Francais, Anglais.

SKILLS
Python, FastAPI, PostgreSQL, Redis, Docker, AWS, Git, REST APIs

EXPERIENCE
Backend Engineer | Fintech Global | 2022-01 - 2025-01
- Built asynchronous payment APIs in Python and FastAPI handling 5,000 transactions per second.
- Optimized PostgreSQL queries and Redis caching, cutting p99 latency by 35%.

EDUCATION
B.S. in Computer Science | INSA Lyon | 2021
"""

AUSTIN_RESUME_TEXT = """Jordan Taylor
jordan.taylor@example.com | +1 512 555 0199 | Austin, TX, USA
linkedin.com/in/jordantaylor | github.com/jtaylor

SUMMARY
Backend Engineer with 3 years of experience building Python microservices, FastAPI endpoints, and PostgreSQL data layers.

SKILLS
Python, FastAPI, PostgreSQL, Docker, Kubernetes, AWS, Git

EXPERIENCE
Backend Engineer | LoneStar Cloud | 2022-02 - 2025-02
- Engineered REST APIs in Python and FastAPI serving 4,000 requests per second.
- Tuned PostgreSQL indexes and Docker containers, lowering latency by 28%.

EDUCATION
B.S. in Computer Science | University of Texas at Austin | 2021
"""

NO_DJANGO_RESUME_TEXT = """Nadia Mansour
nadia.mansour@example.com | +33 6 98 76 54 32 | Paris, France

SUMMARY
Backend Engineer with 3 years of experience building Go and FastAPI services with PostgreSQL and Docker.

SKILLS
Python, FastAPI, Go, PostgreSQL, Docker, Redis, Git

EXPERIENCE
Backend Engineer | EuroPay Systems | 2022-01 - 2025-01
- Built high-throughput settlement endpoints in FastAPI handling 3,200 requests per second.
- Reduced PostgreSQL read query time by 30% using composite indexes.

EDUCATION
M.S. in Software Engineering | Telecom Paris | 2021
"""


@pytest.fixture(autouse=True)
def isolated_upgrade_env(tmp_path, monkeypatch):
    """Isolate workspace, database, sessions, and block external browser/network launches."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    test_home = tmp_path / "jobmcp_home"
    data_dir = test_home / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("JH_DATA_DIR", raising=False)
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    monkeypatch.setenv("JOBHUNTER_NO_BROWSER", "1")
    monkeypatch.setenv("JOBHUNTER_BYPASS_DELAY", "1")
    monkeypatch.setattr(config, "WORKSPACE_DIR", str(ws))
    monkeypatch.setattr(config, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(config, "DB_PATH", str(data_dir / "engine.db"))

    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()
    worker_launcher._ACTIVE_SEARCH_JOBS.clear()
    db._SESSION_VIEW_FILTERS.clear()
    home._HOME_CREATED_IN_SESSION = False
    home._FIRST_NOTICE_GIVEN = False
    preferences._cache.update(mtime=None, path=None, data=None)
    yield {"workspace": ws, "home": test_home}


def _mock_launch_runtime(monkeypatch):
    """Prevent real HTTP daemon, background search threads, radar threads, or browsers."""
    counts = {"server": 0, "search": 0}

    def fake_server(*args, **kwargs):
        counts["server"] += 1
        return {"status": "started", "port": 8777, "pid": 4242}

    def fake_search(**kwargs):
        counts["search"] += 1
        return {"search_job_id": f"bg_{counts['search']}", "status": "started"}

    monkeypatch.setattr(worker_launcher, "start_detached_server", fake_server)
    monkeypatch.setattr(worker_launcher, "start_background_search", fake_search)
    monkeypatch.setattr(worker_launcher, "open_browser", lambda *a, **kw: True)
    monkeypatch.setattr(radar, "start_radar_worker", lambda *a, **kw: None)
    return counts


def _seed_geo_jobs():
    """Seed active Backend Engineer postings across regions and work modes."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.store_jobs(
        [
            {
                "id": "job_paris",
                "title": "Backend Engineer",
                "company": "ParisPay",
                "location": "Paris, France",
                "country": "France",
                "work_mode": "Onsite",
                "job_type": "full-time",
                "url": "https://example.com/jobs/paris",
                "posted_at": now_iso,
                "score": 86,
            },
            {
                "id": "job_berlin",
                "title": "Backend Engineer",
                "company": "BerlinCloud",
                "location": "Berlin, Germany",
                "country": "Germany",
                "work_mode": "Hybrid",
                "job_type": "full-time",
                "url": "https://example.com/jobs/berlin",
                "posted_at": now_iso,
                "score": 85,
            },
            {
                "id": "job_austin",
                "title": "Backend Engineer",
                "company": "AustinData",
                "location": "Austin, TX, USA",
                "country": "United States",
                "work_mode": "Onsite",
                "job_type": "full-time",
                "url": "https://example.com/jobs/austin",
                "posted_at": now_iso,
                "score": 84,
            },
            {
                "id": "job_bangalore",
                "title": "Backend Engineer",
                "company": "BengaluruStack",
                "location": "Bangalore, India",
                "country": "India",
                "work_mode": "Onsite",
                "job_type": "full-time",
                "url": "https://example.com/jobs/bangalore",
                "posted_at": now_iso,
                "score": 83,
            },
            {
                "id": "job_karachi",
                "title": "Backend Engineer",
                "company": "KarachiCore",
                "location": "Karachi, Pakistan",
                "country": "Pakistan",
                "work_mode": "Onsite",
                "job_type": "full-time",
                "url": "https://example.com/jobs/karachi",
                "posted_at": now_iso,
                "score": 82,
            },
            {
                "id": "job_remote",
                "title": "Backend Engineer",
                "company": "GlobalAsync",
                "location": "Remote",
                "country": "Worldwide",
                "work_mode": "Remote",
                "job_type": "full-time",
                "url": "https://example.com/jobs/remote",
                "posted_at": now_iso,
                "score": 88,
            },
        ],
        query="Backend Engineer",
    )


def _extract_gap_items(result: dict) -> list[dict]:
    """Collect gap dicts from either evaluate_honest_match or generate_gap_report."""
    items: list[dict] = []
    for key in ("gaps", "real_gaps", "soft_gaps", "hard_gaps", "add_if_true"):
        val = result.get(key)
        if isinstance(val, list):
            for entry in val:
                if isinstance(entry, dict):
                    items.append(entry)
    return items


def _gap_kind(item: dict) -> str:
    for key in ("classification", "gap_type", "type", "kind", "severity", "category"):
        val = str(item.get(key) or "").lower().strip()
        if val in ("soft_gap", "hard_gap"):
            return val
    return ""


# ---------------------------------------------------------------------------
# 1. Steps 2-3 Place Rules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sid,resume_text,forbidden_city,forbidden_country",
    [
        ("s_place_lyon", LYON_RESUME_TEXT, "lyon", "france"),
        ("s_place_austin", AUSTIN_RESUME_TEXT, "austin", "usa"),
    ],
)
def test_step2_3_resume_place_never_guessed_and_step3_offers_clean_choices(
    sid, resume_text, forbidden_city, forbidden_country
):
    beg = v5_tools.jh_begin(resume_text=resume_text, session_id=sid)
    assert beg["status"] in ("needs_target", "needs_role")
    assert beg.get("ticket") is None

    region_guess = beg["data"]["region_guess"]
    assert region_guess["value"] == ""
    assert db.get_view_filters(sid)["locations"] == []

    step3_q = interview_questions.build_step_3_target_questions(
        beg["data"]["inferred_roles"],
        region_guess,
        ask_role=False,
    )
    place_q = next(q for q in step3_q["questions"] if q["id"] == "target_place")
    choices_lower = [str(c).lower() for c in place_q.get("choices", [])]

    assert any("remote only" in c for c in choices_lower)
    assert any("international" in c and "worldwide remote" in c for c in choices_lower)
    non_remote_choices = [
        c for c in choices_lower if "remote" not in c and "worldwide" not in c
    ]
    assert len(non_remote_choices) >= 2

    rec = str(place_q.get("recommended") or "").lower()
    assert forbidden_city not in rec
    assert forbidden_country not in rec
    assert forbidden_city not in step3_q["formatted_text"].lower()
    assert f"suggested: {forbidden_country}" not in step3_q["formatted_text"].lower()


@pytest.mark.parametrize("reply", ["Modern", "skip"])
def test_step3_jh_confirm_without_place_refuses_ticket_and_keeps_asked_state(reply):
    sid = f"s_no_place_{reply.lower()}"
    beg = v5_tools.jh_begin(resume_text=LYON_RESUME_TEXT, session_id=sid)
    assert beg.get("ticket") is None
    assert ticket_manager.get_session_state_name(sid) == ticket_manager.SessionState.ASKED

    conf = v5_tools.jh_confirm(session_id=sid, user_reply=reply)
    assert conf.get("ticket") is None
    assert conf["status"] == "needs_input"
    assert ticket_manager.get_session_state_name(sid) == ticket_manager.SessionState.ASKED
    assert db.get_view_filters(sid)["locations"] == []


@pytest.mark.parametrize(
    "place_reply,expected_loc_tokens,must_include,must_exclude",
    [
        ("Remote only", ["remote"], {"job_remote"}, {"job_paris", "job_berlin", "job_austin", "job_bangalore", "job_karachi"}),
        ("Worldwide remote", ["worldwide"], {"job_remote"}, {"job_paris", "job_austin", "job_bangalore", "job_karachi"}),
        ("France", ["france"], {"job_paris"}, {"job_berlin", "job_austin", "job_bangalore"}),
        ("Europe", ["europe"], {"job_paris", "job_berlin"}, {"job_austin", "job_bangalore", "job_karachi"}),
        ("South Asia", ["south asia"], {"job_bangalore", "job_karachi"}, {"job_paris", "job_berlin", "job_austin"}),
        ("USA", ["usa", "united states"], {"job_austin"}, {"job_paris", "job_berlin", "job_bangalore"}),
        ("Paris, France", ["paris"], {"job_paris"}, {"job_berlin", "job_austin", "job_bangalore"}),
        ("France, Germany", ["france", "germany"], {"job_paris", "job_berlin"}, {"job_austin", "job_bangalore"}),
    ],
)
def test_step3_jh_confirm_explicit_places_issue_ticket_and_filter_accurately(
    place_reply, expected_loc_tokens, must_include, must_exclude
):
    sid = f"s_place_{place_reply.lower().replace(' ', '_').replace(',', '')}"
    _seed_geo_jobs()
    v5_tools.jh_begin(resume_text=LYON_RESUME_TEXT, session_id=sid)

    conf = v5_tools.jh_confirm(session_id=sid, user_reply=place_reply)
    assert conf["status"] == "ready"
    assert conf.get("ticket")
    assert ticket_manager.get_session_state_name(sid) == ticket_manager.SessionState.ANSWERED

    vf = db.get_view_filters(sid)
    locs_joined = " ".join(str(x).lower() for x in (vf.get("locations") or []))
    assert locs_joined
    if place_reply == "France, Germany":
        assert "france" in locs_joined and "germany" in locs_joined
    else:
        assert any(tok in locs_joined for tok in expected_loc_tokens)

    q = db.query_jobs(session_id=sid)
    visible_ids = {j["id"] for j in q["jobs"]}
    assert must_include <= visible_ids
    assert not (must_exclude & visible_ids)


# ---------------------------------------------------------------------------
# 2. Lesson A: Role Inference Title Families & Step 5 Preferences
# ---------------------------------------------------------------------------

def test_lesson_a_role_inference_reads_role_key_expands_title_family_and_keeps_filters_empty():
    parsed_profile, _ = resume_parser.parse_resume(LYON_RESUME_TEXT)
    assert parsed_profile["experience"]
    assert "role" in parsed_profile["experience"][0]

    # Verify infer_roles reads "role" from experience even without target_title
    exp_only_profile = {
        "name": "Test Candidate",
        "target_title": "",
        "skills": ["Python", "Spark", "SQL", "Airflow"],
        "experience": [
            {
                "role": "Data Engineer",
                "company": "PipelineCo",
                "bullets": ["Built Spark and Airflow ETL pipelines in SQL."],
            }
        ],
    }
    inf = role_inference.infer_roles(exp_only_profile)
    assert inf["roles"]
    top_role_names = [r["role"] for r in inf["roles"]]
    assert any("data" in name.lower() for name in top_role_names)

    for entry in inf["roles"]:
        assert entry.get("is_guess") is True
        assert entry.get("usage") == "search_query_only"
        family = entry.get("title_family")
        assert isinstance(family, list)
        assert 4 <= len(family) <= 7
        assert all(isinstance(title, str) and title.strip() for title in family)

    sid = "s_la_filters"
    v5_tools.jh_begin(resume_text=LYON_RESUME_TEXT, session_id=sid)
    assert db.get_view_filters(sid)["roles"] == []


def test_lesson_a_jh_answer_step5_preferences_update_live_without_restarting_search(monkeypatch):
    counts = _mock_launch_runtime(monkeypatch)
    sid = "s_la_step5"

    v5_tools.jh_begin(resume_text=LYON_RESUME_TEXT, session_id=sid)
    tkt = v5_tools.jh_confirm(session_id=sid, user_reply="Classic, Europe")["ticket"]
    v5_tools.jh_launch(session_id=sid, ticket=tkt)
    assert counts == {"server": 1, "search": 1}

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.store_jobs(
        [
            {
                "id": "job_fintech_startup",
                "title": "Backend Engineer",
                "company": "FinPulse",
                "location": "Paris, France",
                "country": "France",
                "work_mode": "Onsite",
                "job_type": "full-time",
                "industry": "Finance & Fintech",
                "company_stage": "startup",
                "company_size": "startup",
                "market_served": "B2B",
                "languages": ["French", "English"],
                "description": "B2B fintech payments startup in Paris. Bilingual French and English required.",
                "url": "https://example.com/la/1",
                "posted_at": now_iso,
                "score": 80,
            },
            {
                "id": "job_health_scaleup",
                "title": "Backend Engineer",
                "company": "MedScale",
                "location": "Paris, France",
                "country": "France",
                "work_mode": "Onsite",
                "job_type": "full-time",
                "industry": "Healthcare & Bio",
                "company_stage": "scale-up",
                "company_size": "scale-up",
                "market_served": "B2C",
                "languages": ["English"],
                "description": "B2C healthcare scale-up in Paris. English working environment.",
                "url": "https://example.com/la/2",
                "posted_at": now_iso,
                "score": 80,
            },
            {
                "id": "job_retail_public",
                "title": "Backend Engineer",
                "company": "EuroRetail PLC",
                "location": "Berlin, Germany",
                "country": "Germany",
                "work_mode": "Onsite",
                "job_type": "full-time",
                "industry": "Retail & E-commerce",
                "company_stage": "public",
                "company_size": "public",
                "market_served": "B2C",
                "languages": ["German"],
                "description": "Public retail and e-commerce enterprise in Berlin. German language required.",
                "url": "https://example.com/la/3",
                "posted_at": now_iso,
                "score": 80,
            },
        ],
        query="Backend Engineer",
    )

    # Round 1: fintech + startup + B2B + bilingual French (via natural user_reply)
    ans1 = v5_tools.jh_answer(
        session_id=sid,
        user_reply="fintech, startup, B2B, bilingual French",
    )
    assert ans1["status"] == "ok"
    assert counts == {"server": 1, "search": 1}

    vf1 = db.get_view_filters(sid)
    ind_val = str(vf1.get("confirmed_industries") or vf1.get("industry") or vf1.get("industries") or "").lower()
    stage_val = str(vf1.get("company_stages") or vf1.get("company_stage") or vf1.get("company_sizes") or "").lower()
    mkt_val = str(vf1.get("markets_served") or vf1.get("market_served") or "").lower()
    lang_val = str(vf1.get("languages") or "").lower()
    assert "fintech" in ind_val
    assert "startup" in stage_val
    assert "b2b" in mkt_val
    assert "french" in lang_val

    q1 = db.query_jobs(session_id=sid)
    assert q1["jobs"]
    assert q1["jobs"][0]["id"] == "job_fintech_startup"

    # Round 2: scale-up + healthcare + B2C + English
    ans2 = v5_tools.jh_answer(
        session_id=sid,
        user_reply="healthcare, scale-up, B2C, English",
        answers={
            "industry": "healthcare",
            "company_stage": "scale-up",
            "market_served": "B2C",
            "languages": ["English"],
        },
    )
    assert ans2["status"] == "ok"
    assert counts == {"server": 1, "search": 1}
    vf2 = db.get_view_filters(sid)
    assert "scale-up" in str(vf2.get("company_stages") or vf2.get("company_stage") or vf2.get("company_sizes") or "").lower()
    q2 = db.query_jobs(session_id=sid)
    assert q2["jobs"] and q2["jobs"][0]["id"] == "job_health_scaleup"

    # Round 3: public stage
    ans3 = v5_tools.jh_answer(
        session_id=sid,
        user_reply="public company, retail, B2C, German",
        answers={
            "industry": "retail",
            "company_stage": "public",
            "market_served": "B2C",
            "languages": ["German"],
        },
    )
    assert ans3["status"] == "ok"
    assert counts == {"server": 1, "search": 1}
    vf3 = db.get_view_filters(sid)
    assert "public" in str(vf3.get("company_stages") or vf3.get("company_stage") or vf3.get("company_sizes") or "").lower()
    q3 = db.query_jobs(session_id=sid)
    assert q3["jobs"] and q3["jobs"][0]["id"] == "job_retail_public"


# ---------------------------------------------------------------------------
# 3. Lesson B: Honest Match, Soft/Hard Gaps, Weak Match Save, Resume Scrubbing
# ---------------------------------------------------------------------------

def test_lesson_b_honest_match_and_gap_report_soft_gap_4_vs_3_years_not_hidden():
    profile = {
        "name": "Camille Moreau",
        "target_title": "Backend Engineer",
        "years_of_experience": 3,
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "experience": [
            {
                "company": "Fintech Global",
                "role": "Backend Engineer",
                "start_date": "2022-01",
                "end_date": "2025-01",
                "bullets": ["Built FastAPI and PostgreSQL APIs handling 5,000 req/s."],
            }
        ],
    }
    job_4yr = {
        "id": "job_4yr_soft",
        "title": "Backend Engineer",
        "company": "ScalePayments",
        "location": "Remote",
        "work_mode": "Remote",
        "description": "Requires 4+ years of backend experience with Python, FastAPI, PostgreSQL, and Docker.",
        "score": 82,
    }

    ev = scoring.evaluate_honest_match(job=job_4yr, profile=profile)
    for key in ("fit_score", "fit_level", "plain_summary", "strengths", "gaps"):
        assert key in ev
    assert isinstance(ev["fit_score"], (int, float))
    assert isinstance(ev["fit_level"], str) and ev["fit_level"].strip()
    assert isinstance(ev["plain_summary"], str) and ev["plain_summary"].strip()
    assert isinstance(ev["strengths"], list) and len(ev["strengths"]) >= 1

    ev_gaps = _extract_gap_items(ev)
    soft_gaps = [g for g in ev_gaps if _gap_kind(g) == "soft_gap"]
    assert soft_gaps, f"Expected a soft_gap entry in evaluate_honest_match gaps: {ev_gaps}"
    assert any(g.get("apply_anyway") is True for g in soft_gaps)
    combined_advice = " ".join(
        [ev["plain_summary"]] + [str(g.get("advice") or g.get("note") or "") for g in soft_gaps]
    ).lower()
    assert "apply" in combined_advice

    gap_rep = refit.generate_gap_report(job_4yr, profile)
    rep_gaps = _extract_gap_items(gap_rep)
    rep_soft = [g for g in rep_gaps if _gap_kind(g) == "soft_gap"]
    assert rep_soft and any(g.get("apply_anyway") is True for g in rep_soft)

    # Posting must NOT be hidden/rejected by query_jobs
    db.store_jobs([job_4yr], query="Backend Engineer")
    q = db.query_jobs(session_id="s_lb_soft", profile=profile)
    assert any(j["id"] == "job_4yr_soft" for j in q["jobs"])


@pytest.mark.parametrize(
    "requirement_text",
    [
        "Must hold an active Top Secret security clearance.",
        "Requires US work authorization without sponsorship.",
        "Must hold an active CPA license in good standing.",
    ],
)
def test_lesson_b_honest_match_and_gap_report_hard_gaps_block_apply_anyway(requirement_text):
    profile = {
        "name": "Camille Moreau",
        "target_title": "Backend Engineer",
        "years_of_experience": 4,
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "experience": [
            {
                "company": "Fintech Global",
                "role": "Backend Engineer",
                "start_date": "2021-01",
                "end_date": "2025-01",
                "bullets": ["Built FastAPI APIs with PostgreSQL and Docker."],
            }
        ],
    }
    job_hard = {
        "id": "job_hard_gap",
        "title": "Backend Engineer",
        "company": "GovSecure",
        "description": f"Python, FastAPI, PostgreSQL, Docker. {requirement_text}",
    }

    ev = scoring.evaluate_honest_match(job=job_hard, profile=profile)
    ev_gaps = _extract_gap_items(ev)
    hard_gaps = [g for g in ev_gaps if _gap_kind(g) == "hard_gap"]
    assert hard_gaps, f"Expected hard_gap for '{requirement_text}', got: {ev_gaps}"
    assert all(g.get("apply_anyway") is False for g in hard_gaps)

    gap_rep = refit.generate_gap_report(job_hard, profile)
    rep_gaps = _extract_gap_items(gap_rep)
    rep_hard = [g for g in rep_gaps if _gap_kind(g) == "hard_gap"]
    assert rep_hard, f"Expected hard_gap in generate_gap_report for '{requirement_text}', got: {rep_gaps}"
    assert all(g.get("apply_anyway") is False for g in rep_hard)


def test_lesson_b_weak_match_still_allows_save_with_force(monkeypatch):
    prof = resume_checker.check_resume(text=LYON_RESUME_TEXT)["profile"]
    db.save_profile(prof, profile_id="master")
    low_job = {
        "id": "job_weak_save",
        "title": "Principal FPGA Kernel Architect",
        "company": "SiliconCore",
        "url": "https://example.com/jobs/weak",
        "description": "Requires 12 years Rust, VHDL, Verilog, FPGA, embedded RTOS, and Haskell.",
        "saved_by": "ui",
    }
    db.ingest_job(low_job)
    monkeypatch.setattr(
        lifecycle,
        "liveness_check",
        lambda url, job_id=None: {"url": url, "is_live": True, "status_code": 200, "reason": "ok"},
    )

    ev = scoring.evaluate_honest_match(job=low_job, profile=prof)
    assert ev["fit_score"] < 60
    assert ev["fit_level"]

    low_res = save_flow.handle_save_job(low_job["id"], force=False)
    assert low_res["status"] == "low_fit"
    assert "Save anyway" in low_res.get("options", [])

    forced_res = save_flow.handle_save_job(low_job["id"], force=True)
    assert forced_res["status"] == "ok"
    assert forced_res["saved"] is True
    assert Path(forced_res["resume_path"]).is_file()


def test_lesson_b_tailor_base_resume_and_refit_deterministic_preserve_facts_order_and_scrub_hype():
    profile = {
        "name": "Alex Mercer",
        "email": "alex@example.com",
        "phone": "+1 512 555 0100",
        "target_title": "Backend Engineer",
        "years_of_experience": 4,
        "summary": "Passionate Backend Engineer who leveraged FastAPI and spearheaded scalable microservices.",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "experience": [
            {
                "company": "Fintech Global",
                "role": "Backend Engineer",
                "start_date": "2022-01",
                "end_date": "2024-06",
                "bullets": [
                    "Spearheaded weekly team syncs and leveraged shared sprint trackers.",
                    "Leveraged FastAPI and PostgreSQL to serve 5,000 requests/sec and cut p99 latency by 35%.",
                ],
            }
        ],
        "education": [{"institution": "UT Austin", "degree": "B.S. CS", "graduation_year": "2020"}],
    }
    job = {
        "title": "Backend Engineer",
        "company": "TargetPay",
        "description": "Seeking Backend Engineer skilled in FastAPI and PostgreSQL for low-latency APIs.",
    }

    tailored = refit.tailor_base_resume(profile, job)
    det_tailored, _, _, _ = refit.refit_deterministic(job, profile)

    for variant in (tailored, det_tailored):
        exp0 = variant["experience"][0]
        assert exp0["role"] == "Backend Engineer"
        assert exp0["company"] == "Fintech Global"
        assert exp0["start_date"] == "2022-01"
        assert exp0["end_date"] == "2024-06"

        bullets = exp0["bullets"]
        assert "5,000" in bullets[0] and "35%" in bullets[0]
        assert "FastAPI" in bullets[0] or "PostgreSQL" in bullets[0]

        all_text = (variant.get("summary", "") + "\n" + "\n".join(bullets)).lower()
        for hype in ("passionate", "leveraged", "spearheaded"):
            assert hype not in all_text, f"Hype buzzword '{hype}' was not scrubbed from tailored output"


# ---------------------------------------------------------------------------
# 4. Lesson C: Interview Prep, Company Brief Glassdoor URL, practice_interview Tool
# ---------------------------------------------------------------------------

def test_lesson_c_generate_interview_prep_sections_and_unscraped_glassdoor():
    prof = resume_checker.check_resume(text=LYON_RESUME_TEXT)["profile"]
    job = {
        "id": "job_lc_prep",
        "title": "Backend Engineer",
        "company": "NovaPay",
        "description": "Python, FastAPI, PostgreSQL APIs handling high payment volume.",
    }
    prep = refit.generate_interview_prep(job, prof, use_llm=False)

    # Legacy keys preserved
    for legacy_key in (
        "role",
        "company",
        "interview_focus_areas",
        "behavioral_questions",
        "behavioral_scenarios",
        "technical_deep_dives",
        "gap_talking_points",
        "questions_to_ask_interviewer",
    ):
        assert legacy_key in prep

    # Story-based tell_me_about_yourself (not pitch/hype)
    tmay = prep.get("tell_me_about_yourself")
    assert tmay
    tmay_str = json.dumps(tmay).lower() if not isinstance(tmay, str) else tmay.lower()
    assert any(cue in tmay_str for cue in ("fintech global", "python", "fastapi", "backend"))
    for pitch_hype in ("passionate", "results-driven", "i am writing to"):
        assert pitch_hype not in tmay_str

    assert prep.get("recruiter_screen")

    hm = prep.get("hiring_manager_round")
    assert isinstance(hm, dict)
    assert isinstance(hm.get("likely_questions"), list) and len(hm["likely_questions"]) >= 1
    assert any(
        isinstance(q, dict) and q.get("resume_example")
        for q in hm["likely_questions"]
    )
    assert hm.get("why_this_job")
    assert isinstance(hm.get("questions_to_ask"), list) and len(hm["questions_to_ask"]) >= 1

    assert prep.get("peer_round")

    rep = prep.get("company_reputation")
    assert isinstance(rep, dict)
    assert rep.get("scraped") is False
    rep_dump = json.dumps(rep).lower()
    assert "glassdoor.com" in rep_dump
    assert "novapay" in rep_dump
    assert "4." not in str(rep.get("rating", ""))  # no fabricated star rating


def test_lesson_c_company_research_build_company_brief_talking_points_and_glassdoor():
    prof = resume_checker.check_resume(text=LYON_RESUME_TEXT)["profile"]
    sig = {
        "id": "sig_lc_1",
        "company": "NovaPay",
        "url": "https://news.ycombinator.com/item?id=999",
        "text": "NovaPay is a Series A fintech startup hiring Python and FastAPI backend engineers.",
        "stage": "series_a",
    }
    brief = company_research.build_company_brief(sig, prof)

    assert brief["company"] == "NovaPay"
    assert isinstance(brief.get("talking_points"), list) and len(brief["talking_points"]) >= 1
    assert "glassdoor.com" in (brief.get("glassdoor_url") or "").lower()
    assert "novapay" in (brief.get("glassdoor_url") or "").lower()


def test_lesson_c_practice_interview_tool_role_prep_gate_and_mock_grading(tmp_path):
    assert roles.owner_of("practice_interview") == "coach"
    assert "practice_interview" in roles.ROSTER["coach"].tools

    srv = mcp_server.create_server(str(tmp_path))
    tool_objs = {t.name: t for t in asyncio.run(srv.list_tools())}
    assert "practice_interview" in tool_objs

    prof = resume_checker.check_resume(text=LYON_RESUME_TEXT)["profile"]
    db.save_profile(prof, profile_id="master")
    db.store_jobs(
        [
            {
                "id": "job_practice_1",
                "title": "Backend Engineer",
                "company": "AcmePay",
                "url": "https://example.com/jobs/practice1",
                "description": "Python, FastAPI, PostgreSQL backend engineering.",
            }
        ],
        query="Backend Engineer",
    )

    def call_tool(name, **kwargs):
        res = asyncio.run(srv.call_tool(name, kwargs))
        blocks = res[0] if isinstance(res, tuple) else res
        return json.loads(blocks[0].text)

    # 1. Requires saved prep output first
    before_prep = call_tool("practice_interview", job_id="job_practice_1")
    assert before_prep["status"] in ("error", "needs_prep", "needs_input") or not before_prep.get("success")
    assert before_prep.get("data", {}).get("prep_exists") is False or "prep" in json.dumps(before_prep).lower()

    # 2. Generate and save interview prep
    prep_res = call_tool("interview_prep", job_id="job_practice_1")
    assert prep_res["success"] is True

    # 3. Ask questions from saved prep
    ask_res = call_tool("practice_interview", job_id="job_practice_1")
    assert ask_res["success"] is True
    assert ask_res["data"].get("status") != "needs_prep"
    ask_dump = json.dumps(ask_res["data"]).lower()
    assert "?" in ask_dump or "question" in ask_dump

    # 4. Grade user answer via mock rubric
    props = tool_objs["practice_interview"].inputSchema.get("properties", {})
    kwargs: dict[str, object] = {"job_id": "job_practice_1"}
    if "action" in props:
        kwargs["action"] = "answer"
    for ans_key in ("user_answer", "candidate_answer", "answer"):
        if ans_key in props:
            kwargs[ans_key] = (
                "At Fintech Global I redesigned PostgreSQL indexes and Redis caching on our FastAPI service, "
                "cutting p99 latency by 35% at 5,000 req/s."
            )
            break
    else:
        kwargs["user_answer"] = (
            "At Fintech Global I redesigned PostgreSQL indexes and Redis caching on our FastAPI service, "
            "cutting p99 latency by 35% at 5,000 req/s."
        )
    if "question" in props:
        kwargs["question"] = "Walk me through a problem you solved with PostgreSQL."

    grade_res = call_tool("practice_interview", **kwargs)
    assert grade_res["success"] is True
    gdata = grade_res["data"]
    eval_obj = gdata.get("evaluation") if isinstance(gdata.get("evaluation"), dict) else gdata
    assert any(k in eval_obj for k in ("total_score", "overall_score", "scores", "dimension_scores", "rubric_scores"))
    assert "verdict" in eval_obj or "strengths" in eval_obj


# ---------------------------------------------------------------------------
# 5. Lesson D: Confirmed Side Work in confirmed_facts and Resume Generation
# ---------------------------------------------------------------------------

def test_lesson_d_side_work_confirmed_facts_and_resume_generation(monkeypatch):
    _mock_launch_runtime(monkeypatch)
    prof_unconfirmed = resume_checker.check_resume(text=NO_DJANGO_RESUME_TEXT)["profile"]
    django_job = {
        "id": "job_ld_django",
        "title": "Backend Engineer",
        "company": "DjangoCloud",
        "description": "Seeking Backend Engineer with Python, FastAPI, Django API optimization, and PostgreSQL.",
    }

    # Before confirming side work: resume generators must NEVER invent freelance/Django side work
    tailored_before = refit.tailor_base_resume(prof_unconfirmed, django_job)
    custom_before = refit.generate_custom_resume(django_job, prof_unconfirmed, use_llm=False)
    txt_before_1 = exporters.to_txt(tailored_before).lower()
    txt_before_2 = exporters.to_txt(custom_before["tailored_resume"]).lower()
    assert "freelance" not in txt_before_1 and "django" not in txt_before_1
    assert "freelance" not in txt_before_2 and "django" not in txt_before_2

    # Confirm side_work through jh_answer
    v5_tools.jh_begin(resume_text=NO_DJANGO_RESUME_TEXT, session_id="default")
    tkt = v5_tools.jh_confirm(session_id="default", user_reply="Classic, Europe")["ticket"]
    v5_tools.jh_launch(session_id="default", ticket=tkt)

    ans = v5_tools.jh_answer(
        session_id="default",
        user_reply="I also did freelance Django API optimization since 2025",
        answers={"side_work": "freelance Django API optimization since 2025"},
    )
    assert ans["status"] == "ok"

    facts = db.get_confirmed_facts("default")
    assert any("freelance django api optimization since 2025" in f["fact"].lower() for f in facts)

    # Also verify plain-text side_work parsing without answers dict in a separate session
    sid_text = "s_ld_text_only"
    v5_tools.jh_begin(resume_text=NO_DJANGO_RESUME_TEXT, session_id=sid_text)
    tkt2 = v5_tools.jh_confirm(session_id=sid_text, user_reply="Classic, Europe")["ticket"]
    v5_tools.jh_launch(session_id=sid_text, ticket=tkt2)
    v5_tools.jh_answer(
        session_id=sid_text,
        user_reply="side work: freelance Django API optimization since 2025",
    )
    facts2 = db.get_confirmed_facts(sid_text)
    assert any("freelance django api optimization since 2025" in f["fact"].lower() for f in facts2)

    # After confirmation: resume generators include confirmed side work and pass QA review
    prof_confirmed = db.get_profile("master")
    tailored_after = refit.tailor_base_resume(prof_confirmed, django_job)
    custom_after = refit.generate_custom_resume(django_job, prof_confirmed, use_llm=False)
    txt_after_1 = exporters.to_txt(tailored_after)
    txt_after_2 = exporters.to_txt(custom_after["tailored_resume"])

    assert "freelance django api optimization since 2025" in txt_after_1.lower()
    assert "freelance django api optimization since 2025" in txt_after_2.lower()

    rev = qa.review_document(txt_after_1, kind="resume", profile=prof_confirmed, job=django_job)
    assert not rev.blocked, rev.findings


# ---------------------------------------------------------------------------
# 6. Lesson E: jh_status Preserves Existing Fields & Adds Factual pacing_note
# ---------------------------------------------------------------------------

def test_lesson_e_jh_status_preserves_fields_and_adds_calm_factual_pacing_note(monkeypatch):
    _mock_launch_runtime(monkeypatch)
    sid = "s_le_pacing"

    v5_tools.jh_begin(resume_text=LYON_RESUME_TEXT, session_id=sid)
    tkt = v5_tools.jh_confirm(session_id=sid, user_reply="Modern, Europe")["ticket"]
    v5_tools.jh_launch(session_id=sid, ticket=tkt)
    v5_tools.jh_answer(session_id=sid, user_reply="full-time, no visa needed")

    _seed_geo_jobs()
    today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    db.set_setting("daily_cap", "20")
    for i in range(20):
        row = db.log_outreach(contact_id=f"ct_{i}", company="ParisPay", status="sent")
        with db.session() as c:
            c.execute("UPDATE outreach SET sent_at=? WHERE id=?", (f"{today_str} 10:{i:02d}:00", row["id"]))

    st = v5_tools.jh_status(session_id=sid)
    assert st["status"] == "ok"
    data = st["data"]

    expected_keys = (
        "method",
        "session_id",
        "matches",
        "hidden_by_filters",
        "ui_url",
        "browser_opened",
        "ui_seen",
        "extension_status",
        "total_jobs",
        "active_jobs",
        "workspace_home",
        "session_state",
        "radar_state",
        "refresh_states",
        "cleanup_status",
        "active_profile",
        "view_filters",
        "questions_waiting_count",
        "signals_count",
        "fresh_signals",
        "contacts_count",
        "outreach_count",
        "today_sent",
        "remaining_cap",
    )
    for k in expected_keys:
        assert k in data, f"Missing existing jh_status data key: {k}"

    assert data["today_sent"] == 20
    assert data["remaining_cap"] == 0
    assert isinstance(data["matches"], int)
    assert str(data["ui_url"]).startswith("http://127.0.0.1:")

    pacing_note = st.get("pacing_note") if "pacing_note" in st else data.get("pacing_note")
    assert isinstance(pacing_note, str) and len(pacing_note.strip()) > 0
    assert "!" not in pacing_note
    assert len(pacing_note) <= 280
    assert len(pacing_note.splitlines()) <= 2
    for hype in ("awesome", "amazing", "great job", "you got this", "keep going", "crushing", "fantastic", "congrats"):
        assert hype not in pacing_note.lower()


def test_new_resume_clears_stale_unsaved_cache_preserves_crm_and_forces_radar_refresh():
    from jh import tracker
    b1 = v5_tools.jh_begin(resume_text=LYON_RESUME_TEXT, session_id="s_reset")
    assert b1["status"] == "needs_target"
    db.store_jobs(
        [
            {"id": "unsaved_old_tn", "title": "Legacy Tunisia Dev", "company": "OldCo", "location": "Tunis, Tunisia", "work_mode": "Onsite"},
            {"id": "saved_crm_job", "title": "Saved Backend Role", "company": "KeepCo", "location": "Remote", "work_mode": "Remote"},
        ],
        query="Legacy",
    )
    db.mark_job_saved_by_ui("saved_crm_job")
    tracker.upsert_application({"job_id": "saved_crm_job", "company": "KeepCo", "title": "Saved Backend Role", "status": "applied"})
    db.ingest_signal({"id": "sig_old_unsaved", "company": "StaleStartup", "text": "Old HN comment", "source": "HackerNews", "status": "fresh"})
    db.save_view_filters({"min_salary": 120000, "seniority": ["senior"], "locations": ["Tunisia"]}, session_id="s_reset")
    db.set_setting("li_radar_last_run", "2026-11-26T10:00:00+00:00")

    b2 = v5_tools.jh_begin(resume_text=AUSTIN_RESUME_TEXT, session_id="s_reset")
    assert b2["status"] == "needs_target"
    assert db.get_job("unsaved_old_tn") is None
    assert db.get_job("saved_crm_job") is not None
    assert len(tracker.list_applications()) >= 1
    assert db.get_signal("sig_old_unsaved") is None
    vf = db.get_view_filters("s_reset")
    assert vf["min_salary"] == 0.0 and vf["locations"] == []
    assert db.get_setting("radar_force_refresh") == "1"


def test_modern_launch_kicks_signal_poll_and_db_get_signals_filters_place_and_language(monkeypatch):
    from jh import signals as _signals, radar as _radar

    v5_tools.jh_begin(resume_text=AUSTIN_RESUME_TEXT, session_id="s_mod_sig")
    conf = v5_tools.jh_confirm(user_reply="modern, South Asia", session_id="s_mod_sig")
    assert conf["ticket"]

    polled_calls = []
    board_calls = []
    monkeypatch.setattr(worker_launcher, "start_detached_server", lambda *a, **kw: {"status": "started", "port": 8089})
    monkeypatch.setattr(worker_launcher, "open_browser", lambda *a, **kw: False)
    monkeypatch.setattr(worker_launcher, "start_background_search", lambda **kw: board_calls.append(kw) or {"search_job_id": "bg_mod_1", "status": "started"})
    monkeypatch.setattr(_radar, "start_radar_worker", lambda: True)
    monkeypatch.setattr(_signals, "poll_modern_signals", lambda target_role="", target_region="", **kw: polled_calls.append((target_role, target_region)) or {"discovered": 0, "new_ingested": 0})

    res = v5_tools.jh_launch(session_id="s_mod_sig", ticket=conf["ticket"])
    assert res["status"] == "ok"
    assert board_calls and board_calls[0]["location"] == "South Asia"
    import time
    for _ in range(20):
        if polled_calls:
            break
        time.sleep(0.05)
    assert polled_calls and polled_calls[0][1] == "South Asia"

    db.ingest_signal({"id": "sig_sa_en", "company": "IndiCloud", "text": "Hiring Python cloud intern remote India English", "region": "India", "role_guess": "Backend Engineer", "status": "fresh"})
    db.ingest_signal({"id": "sig_us_only", "company": "USGovCo", "text": "US only onsite role", "region": "United States", "role_guess": "Backend Engineer", "status": "fresh"})
    db.ingest_signal({"id": "sig_fr_only", "company": "ParisShop", "text": "French only role in Paris", "region": "France", "role_guess": "Backend Engineer", "status": "fresh"})

    sigs = db.get_signals(view_filters={"locations": ["South Asia"], "languages": ["English"]})
    sig_ids = {s["id"] for s in sigs}
    assert "sig_sa_en" in sig_ids
    assert "sig_us_only" not in sig_ids
    assert "sig_fr_only" not in sig_ids


def test_honest_match_surfaces_grounded_relevant_projects_without_invention():
    prof = {
        "name": "Rayen Ben Aissa",
        "years_of_experience": 1,
        "skills": ["Python", "Docker", "Kubernetes", "CI/CD", "FastAPI"],
        "projects": [
            {"name": "CloudPipeline", "description": "Built a Docker and Kubernetes CI/CD deployment pipeline for Python microservices."},
            {"name": "CanvasGame", "description": "2D browser puzzle game in vanilla JavaScript."},
        ],
        "experience": [
            {"company": "MyNet", "role": "Cloud Intern", "bullets": ["Automated Terraform and Docker container builds in GitHub Actions."]},
        ],
    }
    job = {
        "title": "Cloud Software Engineering Intern",
        "company": "ScaleInfra",
        "description": "Looking for Python, Docker, Kubernetes, CI/CD, and Terraform deployment experience.",
    }
    ev = scoring.evaluate_honest_match(prof, job)
    rps = ev.get("relevant_projects") or []
    assert rps, "Expected grounded relevant_projects to surface matching built work"
    titles = " ".join(rp["title"] for rp in rps)
    assert "CloudPipeline" in titles or "MyNet" in titles
    assert "InventedProject" not in titles


def test_resume_parser_extracts_projects_section_for_relevant_project_matching():
    resume_txt = """Rayen Ben Aissa
rayen@example.com | Paris, France

SUMMARY
Cloud Software Engineering student with Python and containerization experience.

SKILLS
Python, Docker, Kubernetes, CI/CD, GitHub Actions, FastAPI

TECHNICAL PROJECTS
CloudPipeline | Docker, Kubernetes, Python
- Built automated Docker and Kubernetes CI/CD microservices pipeline in Python.
MyNet | FastAPI, Docker
- Built an API gateway container stack for internal routing.

EDUCATION
Engineering Degree in Computer Science | INSAT | 2027
"""
    prof, _ = resume_parser.parse_resume(resume_txt)
    projs = prof.get("projects") or []
    assert len(projs) >= 2
    assert any("CloudPipeline" in p["name"] for p in projs)
    ev = scoring.evaluate_honest_match(
        prof,
        {"title": "Cloud Software Engineering Intern", "company": "InfraCo", "description": "Python, Docker, Kubernetes, CI/CD pipelines."},
    )
    assert any("CloudPipeline" in rp["title"] for rp in ev.get("relevant_projects", []))
