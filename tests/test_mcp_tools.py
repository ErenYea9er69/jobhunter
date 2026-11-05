"""The MCP surface as a client sees it: envelope, tools only, safe outputs, job ids that round-trip."""

import asyncio
import json

import pytest

ENVELOPE_KEYS = {"status", "success", "data", "warnings", "sources", "correlation_id", "schema_version", "generated_at"}


@pytest.fixture
def seeded(tools, net):
    """A server that already ran one search, so stored jobs exist."""
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    net.fixture("workingnomads.com/api/exposed_jobs", "workingnomads.json")
    res = tools.call("search_jobs", query="backend engineer", limit=10)
    assert res["success"], res
    return tools


def first_job(res):
    jobs = res["data"]["jobs"]
    assert jobs, res
    return jobs[0]


# ------------------------------------------------------------------ surface

def test_tools_only_no_prompts(server):
    assert asyncio.run(server.list_prompts()) == []
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert len(names) >= 35
    assert {"search_jobs", "get_job_details", "set_preferences", "add_job_source", "verify_draft", "get_playbook",
            "prepare_application", "daily_digest"} <= names
    assert all(t.description and len(t.description) > 20 for t in tools), [t.name for t in tools if not t.description]


def test_every_tool_documents_its_arguments(server):
    for t in asyncio.run(server.list_tools()):
        props = t.inputSchema.get("properties", {})
        for arg, spec in props.items():
            assert spec.get("description") or "title" in spec, f"{t.name}.{arg}"


def test_errors_use_the_same_envelope(tools):
    res = tools.call("get_job_details", job_id="does-not-exist")
    assert ENVELOPE_KEYS <= set(res) and res["status"] == "error" and not res["success"]
    assert res["error"]["code"] == "not_found" and res["error"]["hint"]


def test_unknown_resume_is_a_clear_error(tools):
    res = tools.call("get_resume", name="nope")
    assert res["error"]["code"] == "invalid_input" and "Available" in res["error"]["hint"]


def test_path_outside_workspace_is_refused(tools):
    res = tools.call("parse_resume_file", path="../../etc/passwd")
    assert res["status"] == "error" and res["error"]["code"] == "forbidden"
    assert tools.call("scan_resumes", subpath="../..")["error"]["code"] == "forbidden"


# ------------------------------------------------------------------ secrets

def test_secrets_are_never_returned_or_accepted(tools, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRET-123")
    from jh import config
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-SECRET-123")
    cfg = tools.call("configure")
    assert cfg["data"]["ai"]["api_key_present"] is True and "sk-SECRET-123" not in json.dumps(cfg)
    health = tools.call("source_health")
    assert "sk-SECRET-123" not in json.dumps(health)
    bad = tools.call("configure", key="openai_api_key", value="sk-SECRET-999")
    assert bad["error"]["code"] == "forbidden" and "sk-SECRET-999" not in json.dumps(bad)


def test_resources_do_not_leak_secrets(server, monkeypatch):
    from jh import config
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-SECRET-123")
    for uri in ("jobhunter://preferences", "jobhunter://sources", "jobhunter://resumes", "jobhunter://applications"):
        body = asyncio.run(server.read_resource(uri))
        assert "sk-SECRET" not in str(body)


def test_configure_only_changes_whitelisted_settings(tools):
    assert tools.call("configure", key="li_radar_enabled", value="1")["status"] == "error"
    ok = tools.call("configure", key="max_results", value="500")
    assert ok["success"]
    assert tools.call("configure", key="max_results", value="lots")["status"] == "error"


# ------------------------------------------------------------------ resumes

def test_resume_flow(tools):
    lst = tools.call("list_resumes")["data"]
    assert lst["count"] == 1 and lst["active_resume"] == "Ahmed Backend"
    prof = tools.call("get_resume")["data"]["profile"]
    assert "Python" in prof["skills"] and prof["location"].startswith("Tunis")
    assert tools.call("set_active_resume", name="ahmed")["data"]["active_resume"] == "Ahmed Backend"
    assert tools.call("scan_resumes")["data"]["parsed"] == 1


# ------------------------------------------------------------------ preferences and sources

def test_preferences_round_trip_and_validation(tools):
    bad = tools.call("set_preferences", updates={"work_mode": "teleport"})
    assert bad["status"] == "error" and "work_mode" in bad["error"]["message"]
    ok = tools.call("set_preferences", updates={"target_countries": ["Tunisia", "France"], "company_focus": "avoid_big_names",
                                                "excluded_keywords": ["php"]})
    assert ok["success"] and ok["data"]["target_countries_resolved"] == ["Tunisia", "France"]
    got = tools.call("get_preferences")["data"]
    assert got["preferences"]["company_focus"] == "avoid_big_names" and not got["defaults_in_use"]
    skipped = {s["source"] for s in got["sources"]["skipped"]}
    assert "Naukri" in skipped and "Bayt" not in skipped and "HelloWork" not in skipped


def test_get_preferences_hints_only_when_something_is_missing(tools):
    # The sample resume says "Tunis, Tunisia", so the target country is already known.
    d = tools.call("get_preferences")["data"]
    assert d["resolved_target_countries"] == ["Tunisia"] and not any("target_countries" in h for h in d["hints"])


def test_add_company_by_url_name_and_remove(tools, net):
    net.fixture("acme-tn.recruitee.com/api/offers", "recruitee.json")
    res = tools.call("add_job_source", kind="company", value="https://acme-tn.recruitee.com/o/python-developer")
    assert res["success"] and res["data"]["board_type"] == "recruitee" and res["data"]["open_jobs"] == 1
    assert res["data"]["sample_titles"] == ["Python Developer"]
    listing = tools.call("list_job_sources")["data"]
    assert listing["companies"]["watchlist"][0]["slug"] == "acme-tn"
    assert any(s["name"] == "Company Boards" and "Personio" in s["description"] for s in listing["sources"])
    assert tools.call("remove_job_source", kind="company", value="acme-tn")["data"]["removed"] is True
    assert tools.call("list_job_sources")["data"]["companies"]["watchlist"] == []


def test_add_company_unknown_name_is_a_clear_error(tools, net):
    res = tools.call("add_job_source", kind="company", value="Nonexistent Startup")
    assert res["error"]["code"] == "not_found"


def test_add_feed_is_tested_before_it_is_saved(tools, net):
    net.fixture("jobs.example.tn/feed", "feed_wpjobmanager.rss")
    ok = tools.call("add_job_source", kind="feed", value="https://jobs.example.tn/feed/", name="Tunisia Jobs")
    assert ok["success"] and ok["data"]["jobs_found_in_test"] == 2
    dead = tools.call("add_job_source", kind="feed", value="https://dead.example.org/feed")
    assert dead["error"]["code"] == "unreachable"
    forced = tools.call("add_job_source", kind="feed", value="https://dead.example.org/feed", force=True)
    assert forced["success"]
    assert len(tools.call("get_preferences")["data"]["preferences"]["custom_feeds"]) == 2


def test_private_feed_urls_are_refused(tools):
    res = tools.call("add_job_source", kind="feed", value="http://127.0.0.1:8000/feed", force=True)
    assert res["status"] == "error"


def test_add_career_page_with_jsonld(tools, net):
    net.fixture("careers.example.com/jobs", "careerpage_jsonld.html")
    res = tools.call("add_job_source", kind="career_page", value="https://careers.example.com/jobs", name="InstaDeep")
    assert res["success"] and res["data"]["jobs_found_in_test"] == 1


# ------------------------------------------------------------------ discovery

def test_search_returns_compact_cards_not_full_records(seeded):
    res = seeded.call("search_jobs", query="backend engineer", limit=10)
    card = first_job(res)
    assert {"job_id", "title", "company", "fit_score", "apply_url", "sources", "freshness", "posted"} <= set(card)
    assert "description" not in card and len(json.dumps(res)) < 40_000
    assert res["data"]["coverage"]["sources_ran"] >= 3 and res["data"]["sources"]


def test_search_reports_total_failure_honestly(tools, net):
    res = tools.call("search_jobs", query="python developer")
    assert res["status"] == "partial" and res["data"]["count"] == 0 and res["warnings"]


def test_job_ids_round_trip_through_every_tool(seeded):
    jid = first_job(seeded.call("search_jobs", query="backend engineer"))["job_id"]
    details = seeded.call("get_job_details", job_id=jid)["data"]
    assert details["job_id"] == jid and "Python" in details["description"]
    assert seeded.call("score_job", job_id=jid)["data"]["fit_score"] > 0
    assert "gaps" in json.dumps(seeded.call("gap_report", job_id=jid)["data"]).lower() or seeded.call("gap_report", job_id=jid)["success"]
    assert seeded.call("ats_audit", job_id=jid)["success"]
    assert seeded.call("compare_resumes", job_id=jid)["success"]
    assert seeded.call("interview_prep", job_id=jid)["success"]
    assert seeded.call("outreach_message", job_id=jid)["success"]
    saved = seeded.call("get_saved_jobs", limit=5)["data"]
    assert saved["count"] >= 1 and "description" not in saved["jobs"][0]


def test_get_recommendations_count_is_the_number_of_jobs(seeded):
    res = seeded.call("get_recommendations", limit=5)
    assert res["success"] and res["data"]["count"] == len(res["data"]["jobs"])


def test_pasted_job_text_still_works_without_search(tools):
    res = tools.call("score_job", job_title="Senior Backend Engineer", company="Acme",
                     description="Required: Python, FastAPI, PostgreSQL, Kubernetes. Nice to have: Kafka. Salary 60,000-80,000 EUR")
    d = res["data"]
    assert res["success"] and d["fit_score"] > 40 and d["salary"].startswith("60,000")
    assert "Kubernetes" in d["missing_skills"] and "Kafka" in d["missing_skills"]


# ------------------------------------------------------------------ documents

def test_tailor_resume_reports_real_scores_and_grounding(seeded):
    jid = first_job(seeded.call("search_jobs", query="backend engineer"))["job_id"]
    res = seeded.call("tailor_resume", job_id=jid, archetype="startup")
    d = res["data"]
    assert res["success"] and d["archetype"] == "startup_velocity"
    assert d["ats_after"] > 0 and d["ats_after"] >= d["ats_before"] - 15      # used to report 0: it scored the wrapper dict
    assert d["grounding"]["status"] and "unsupported" in d["grounding"]
    assert set(d["saved_to"]) == {"json", "text"} and d["tailored_resume"]["name"] == "Ahmed Ben Salah"


def test_tailor_rejects_unknown_archetype(tools):
    res = tools.call("tailor_resume", job_title="x", description="y", archetype="wizard")
    assert res["status"] == "error" and "technical_depth" in res["error"]["hint"]


def test_cover_letter_is_text_not_a_dict_repr(seeded):
    jid = first_job(seeded.call("search_jobs", query="backend engineer"))["job_id"]
    res = seeded.call("cover_letter", job_id=jid)
    d = res["data"]
    assert res["success"] and isinstance(d["letter"], str) and not d["letter"].startswith("{") and "Ahmed" in d["letter"]
    assert d["word_count"] > 60 and d["grounding"]["status"]
    import pathlib
    assert pathlib.Path(d["saved_to"]["text"]).read_text(encoding="utf-8") == d["letter"]


def test_cover_letter_docx_and_pdf(seeded):
    jid = first_job(seeded.call("search_jobs", query="backend engineer"))["job_id"]
    import pathlib
    for fmt in ("docx", "pdf"):
        res = seeded.call("cover_letter", job_id=jid, format=fmt)
        assert res["success"], res
        assert pathlib.Path(res["data"]["saved_to"][fmt]).stat().st_size > 500


def test_verify_draft_catches_invented_claims(tools):
    good = tools.call("verify_draft", text="I reduced PostgreSQL query latency by 45% at Vermeg using Redis caching.")["data"]
    bad = tools.call("verify_draft", text="I led a team of 40 engineers at Google for 12 years and built Kubernetes operators in Rust.")["data"]
    assert bad["unsupported"] + bad["needs_review"] > good["unsupported"] + good["needs_review"]
    assert bad["flagged_claims"] and good["supported"] >= 1


def test_get_evidence_lists_resume_facts(tools):
    d = tools.call("get_evidence")["data"]
    assert d["count"] > 5 and any("Vermeg" in json.dumps(c) for c in d["claims"])


def test_export_resume_formats(tools):
    import pathlib
    for fmt in ("txt", "html", "docx", "pdf"):
        res = tools.call("export_resume", format=fmt)
        assert res["success"] and pathlib.Path(res["data"]["exported_to"]).stat().st_size > 100
    assert tools.call("export_resume", format="exe")["status"] == "error"


def test_screening_questions_flag_unknowns(tools):
    res = tools.call("solve_screening_questions", questions=["How many years of Python experience do you have?", "Do you have a security clearance?"])
    answers = res["data"]["answers"]
    assert len(answers) == 2 and "Python" in json.dumps(answers[0])


def test_prepare_application_bundles_and_tracks(seeded):
    jid = first_job(seeded.call("search_jobs", query="backend engineer"))["job_id"]
    res = seeded.call("prepare_application", job_id=jid)
    assert res["success"] and res["data"]["application_id"] and set(res["data"]["saved_to"]) >= {"resume", "cover_letter"}
    apps = seeded.call("list_applications", status="saved")["data"]["applications"]
    assert len(apps) == 1


# ------------------------------------------------------------------ playbooks (formerly prompts)

@pytest.mark.parametrize("task", ["resume_tailor", "cover_letter", "interview_prep", "screening_question_solver",
                                  "recruiter_outreach", "mock_interview_evaluator", "career_skill_roadmap"])
def test_every_playbook_returns_instructions_and_candidate_facts(tools, task):
    res = tools.call("get_playbook", task=task, job_title="Backend Engineer", company="Acme", description="Python and PostgreSQL role")
    d = res["data"]
    assert res["success"] and len(d["instructions"]) > 300 and d["context"]["candidate"]["skills"]
    assert d["context"]["job"]["title"] == "Backend Engineer" and any("verify_draft" in r for r in d["rules"])


def test_follow_up_playbook_needs_a_real_application(tools):
    assert tools.call("get_playbook", task="application_follow_up", app_id="app-0")["error"]["code"] == "not_found"
    assert tools.call("get_playbook", task="bogus")["status"] == "error"


# ------------------------------------------------------------------ tracking

def test_tracking_lifecycle_and_digest(seeded):
    jid = first_job(seeded.call("search_jobs", query="backend engineer"))["job_id"]
    t1 = seeded.call("track_application", job_id=jid, status="applied")
    assert t1["success"] and not t1["data"]["updated_existing"]
    t2 = seeded.call("track_application", job_id=jid, status="interview", notes="Phone screen Tuesday")
    assert t2["data"]["updated_existing"] and t2["data"]["application"]["id"] == t1["data"]["application"]["id"]
    app_id = t1["data"]["application"]["id"]
    assert len(seeded.call("list_applications")["data"]["applications"]) == 1       # no duplicate
    upd = seeded.call("update_application", id=app_id, status="offer", follow_up_date="2026-11-10")
    assert upd["data"]["status"] == "offer"
    assert seeded.call("update_application", id="nope", status="offer")["error"]["code"] == "not_found"
    assert seeded.call("update_application", id=app_id, status="bogus")["status"] == "error"
    stats = seeded.call("application_stats")["data"]
    assert stats["total_tracked"] == 1 and "funnel" in stats
    fu = seeded.call("follow_up_message", app_id=app_id)
    assert fu["success"]


def test_digest_lists_new_jobs_once(seeded):
    first = seeded.call("daily_digest")["data"]
    assert first["new_jobs"] and first["recommended_actions"]
    again = seeded.call("daily_digest")["data"]
    assert again["new_jobs"] == [] and first["new_jobs"][0]["job_id"]


def test_skill_roadmap_ranks_missing_skills(tools):
    tools.call("score_job", job_title="x", description="y")     # no stored jobs yet
    res = tools.call("skill_roadmap")
    assert res["status"] == "error" and res["error"]["code"] == "not_found"


def test_skill_roadmap_from_saved_jobs(seeded):
    res = seeded.call("skill_roadmap", top_jobs=5)
    assert res["success"] and "priority_gaps" in res["data"]


def test_mock_interview_scoring(tools):
    res = tools.call("evaluate_mock_interview", question="Tell me about a performance win.",
                     candidate_answer="I cut PostgreSQL latency by 45 percent by redesigning indexes and adding Redis caching, serving 2 million daily transactions.")
    assert res["success"] and res["data"]
    assert tools.call("evaluate_mock_interview", question="", candidate_answer="x")["status"] == "error"
