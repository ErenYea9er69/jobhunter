"""End to end: a model that follows each playbook exactly gets its answer used by the code.

Version 2.3 asked models for keys the code never read (letter_text, total_score, draft_text, answer_text and others),
so with a model key configured the model's answer was dropped for most playbooks, and for screening a whole JSON
object could end up in a form field. This builds a reply from each playbook's own schema and checks it comes through."""

import json
import pathlib
import re

import pytest

from jh import db, refit, screening, tracker

PROMPTS = pathlib.Path(__file__).resolve().parent.parent / "prompts"
MARK = "ZEBRAMARKER"
FACT = "I build REST APIs in Python at Vermeg. " + MARK        # grounded in the sample resume, plus a marker word with no digits


def schema_reply(playbook: str) -> dict:
    """The reply a model would send if it followed the playbook's <output> block, with a marker in every string."""
    raw = (PROMPTS / f"{playbook}.md").read_text(encoding="utf-8")
    system = re.search(r"```markdown\n(.*?)\n```", raw, re.S).group(1)
    block = re.search(r"<output>(.*?)</output>", system, re.S).group(1)
    skeleton = re.search(r"(?ms)^\{\n.*?^\}", block).group(0)
    skeleton = re.sub(r"<[^>]*>", "50", skeleton)

    def fill(node, key=""):
        if key == "missing_inputs":
            return []
        if key == "verdict":
            return "Needs Refinement"
        if key == "market_demand_level":
            return "high"
        if isinstance(node, dict):
            return {k: fill(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [fill(x, key) for x in node]
        if isinstance(node, (int, float)):
            return 50
        return FACT
    return fill(json.loads(skeleton))


def caller(reply):
    seen = {}

    def call(system, user, *a, **k):
        seen["system"], seen["user"] = system, user
        return json.dumps(reply)
    call.seen = seen
    return call


@pytest.fixture
def world(server, tools, net):
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    jid = tools.call("search_jobs", query="backend engineer", limit=2)["data"]["jobs"][0]["job_id"]
    app_id = tools.call("prepare_application", job_id=jid)["data"]["application_id"]
    job = db.get_job(jid)
    sjob = {"company": job["company"], "title": job["title"], "required_skills": ["Python", "PostgreSQL"], "description": (job.get("description") or "")[:300]}
    return {"job": job, "profile": db.get_profile(), "sjob": sjob, "app_id": app_id}


def runners(w):
    j, p = w["job"], w["profile"]
    return {
        "cover_letter": lambda c: refit.generate_cover_pitch(j, p, use_llm=True, llm_caller=c),
        "resume_tailor": lambda c: refit.generate_custom_resume(j, p, use_llm=True, llm_caller=c),
        "interview_prep": lambda c: refit.generate_interview_prep(j, p, use_llm=True, llm_caller=c),
        "mock_interview_evaluator": lambda c: refit.evaluate_mock_interview_answer("Tell me about a bug.", "I fixed a caching bug at Vermeg.", j, p, use_llm=True, llm_caller=c),
        "recruiter_outreach": lambda c: refit.generate_recruiter_outreach(j, p, use_llm=True, llm_caller=c),
        "career_skill_roadmap": lambda c: refit.generate_skill_roadmap(p, use_llm=True, llm_caller=c),
        "screening_question_solver": lambda c: screening.solve_screening_question("Why do you want to work here?", p, w["sjob"], use_llm=True, llm_caller=c),
        "application_follow_up": lambda c: tracker.generate_application_follow_up(w["app_id"], "status_check_5days", "", p, use_llm=True, llm_caller=c),
    }


@pytest.mark.parametrize("playbook", ["cover_letter", "resume_tailor", "interview_prep", "mock_interview_evaluator", "recruiter_outreach",
                                      "career_skill_roadmap", "screening_question_solver", "application_follow_up"])
def test_a_model_that_follows_the_playbook_gets_its_answer_used(world, playbook):
    c = caller(schema_reply(playbook))
    out = runners(world)[playbook](c)
    assert MARK in json.dumps(out, default=str), f"{playbook}: the code dropped a reply that matches the playbook's schema"
    assert "<voice>" in c.seen["system"], f"{playbook}: the system prompt sent to the model is not the playbook"


def test_a_screening_reply_is_the_answer_not_a_json_blob(world):
    out = runners(world)["screening_question_solver"](caller({"answer": FACT}))
    assert out["answer"].startswith("I build REST APIs") and "{" not in out["answer"]


def test_replies_shaped_by_the_old_prompts_were_dropped_which_is_why_the_keys_changed(world):
    """Documents the 2.3 behaviour. These shapes are what the old playbooks asked for."""
    old = {"interview_prep": {"technical_questions": [{"question": FACT}], "questions_for_interviewer": [FACT]},
           "mock_interview_evaluator": {"total_score": 61, "dimension_scores": {"ownership": 15}, "suggested_rewrite": FACT},
           "recruiter_outreach": {"draft_text": {"linkedin_connection_note": MARK, "hiring_manager_inmail": {"body": FACT}}},
           "career_skill_roadmap": {"priority_gaps": [{"skill": "Go"}], "project_specification": {"project_title": MARK}}}
    for name, reply in old.items():
        assert MARK not in json.dumps(runners(world)[name](caller(reply)), default=str), name


def test_missing_inputs_propagates_across_playbooks(world):
    q = "What target figure do you want?"
    for playbook in ("cover_letter", "resume_tailor", "interview_prep", "recruiter_outreach",
                     "career_skill_roadmap", "screening_question_solver", "application_follow_up"):
        reply = schema_reply(playbook)
        reply["missing_inputs"] = [q]
        out = runners(world)[playbook](caller(reply))
        assert out.get("missing_inputs") == [q], playbook


def test_recruiter_outreach_enforces_200_char_limit_without_midword_truncation(world):
    j, p = world["job"], world["profile"]
    long_note = (
        "I applied for the Backend Engineer role at Adyen. "
        "At Vermeg I cut PostgreSQL latency by 45% with Redis caching across 2 million daily transactions. "
        "I would enjoy hearing how your team builds backend services and handles scaling across regions."
    )
    reply = schema_reply("recruiter_outreach")
    reply["linkedin_connection_note"] = long_note
    c = caller(reply)
    out = refit.generate_recruiter_outreach(j, p, use_llm=True, llm_caller=c)
    assert out["linkedin_connection_validated"] is True
    assert out["linkedin_connection_repaired"] is True
    assert len(out["linkedin_connection_note"]) <= 200
    assert not out["linkedin_connection_note"].endswith("...")
    sent_payload = json.loads(c.seen["user"])
    assert "standout_bullet" in sent_payload and "standout_bullet" not in sent_payload["candidate_source"]

    det = refit.generate_recruiter_outreach(j, p, use_llm=False)
    assert len(det["linkedin_connection_note"]) <= 200
    assert "referral" not in det["peer_referral_request"]["body"].lower()


def test_skill_roadmap_truthful_bridge_and_zero_gap_preservation(world):
    p = world["profile"]
    det = refit.generate_skill_roadmap(p, market_skills=["Go"], use_llm=False)
    assert "recently implemented an end-to-end prototype" not in det["interview_bridge_script"]
    assert "Now:" in det["interview_bridge_script"] and "After the project:" in det["interview_bridge_script"]
    assert det["top_missing_skills"][0]["market_demand_level"] == "high"

    none_needed = refit.generate_skill_roadmap(p, market_skills=["Python", "PostgreSQL"], use_llm=False)
    assert none_needed["top_missing_skills"] == []
    assert none_needed["recommended_learning_resources"] == []
    assert none_needed["fast_track_project"]["project_title"] == "No additional project needed"
    assert none_needed["fast_track_project"]["time_to_complete_days"] == 0

    llm_zero = {
        "target_title": "Backend Engineer",
        "top_missing_skills": [],
        "fast_track_project": {
            "project_title": "No additional project needed",
            "architecture_summary": "Current evidence covers all listed requirements.",
            "deliverables": [],
            "time_to_complete_days": 0,
        },
        "interview_bridge_script": "Now: My current experience covers Python and PostgreSQL. After the project: No additional project is needed.",
        "recommended_learning_resources": [],
        "missing_inputs": [],
    }
    out = refit.generate_skill_roadmap(p, market_skills=["Go"], use_llm=True, llm_caller=caller(llm_zero))
    assert out["top_missing_skills"] == [] and out["recommended_learning_resources"] == []
    assert out["fast_track_project"]["time_to_complete_days"] == 0


def test_follow_up_respects_rejected_stage_and_missing_facts(world):
    from jh import tracker as tr
    p = world["profile"]
    app_id = world["app_id"]
    tr.upsert_application({"id": app_id, "company": "Adyen", "title": "Backend Engineer", "status": "rejected", "notes": ""})
    rej = tr.generate_application_follow_up(app_id, action_type="status_check_5days", profile=p, use_llm=False)
    assert "rejected" in rej["strategy_notes"].lower()
    assert "is there an update" not in rej["body"].lower()

    ty = tr.generate_application_follow_up(app_id, action_type="post_interview_thank_you", profile=p, use_llm=False)
    assert "What did you discuss?" in ty["missing_inputs"]

    neg = tr.generate_application_follow_up(app_id, action_type="offer_negotiation", profile={**p, "min_salary": 0}, use_llm=False)
    assert "What figure or terms do you want to request?" in neg["missing_inputs"]
    assert "market rate" not in neg["body"].lower()

    c = caller(schema_reply("application_follow_up"))
    tr.generate_application_follow_up(app_id, action_type="status_check_5days", profile=p, use_llm=True, llm_caller=c)
    sent = json.loads(c.seen["user"])
    assert "experience" in sent["candidate_source"]


def test_screening_solver_never_guesses_missing_facts_and_preserves_csharp(world):
    p = dict(world["profile"])
    p.pop("notice_period", None)
    p["min_salary"] = 0
    sal = screening.solve_screening_question("What are your salary expectations?", p, world["sjob"], use_llm=False)
    assert "What salary range do you want to state?" in sal["missing_inputs"]
    assert "market rates" not in sal["answer"].lower()

    notice = screening.solve_screening_question("What is your notice period?", p, world["sjob"], use_llm=False)
    assert notice["missing_inputs"] and "2 weeks" not in notice["answer"]

    auth = screening.solve_screening_question("Are you legally authorized to work here?", p, world["sjob"], use_llm=False)
    assert auth["answer"] == "" and auth["missing_inputs"]

    csharp_res = screening.solve_screening_question(
        "Which languages do you use?",
        {**p, "skills": ["Python", "C#"]},
        world["sjob"],
        use_llm=True,
        llm_caller=caller({"answer": "I use Python and C#.", "missing_inputs": []}),
    )
    assert "C#" in csharp_res["answer"]


def test_mock_interview_evaluator_allows_empty_lists_and_no_metric_red_flag(world):
    p, j = world["profile"], world["job"]
    det = refit.evaluate_mock_interview_answer("Describe a design tradeoff.", "I chose a simpler queue because the team could maintain it.", j, p, use_llm=False)
    assert det["red_flags"] == []

    llm_empty = {
        "overall_score": 40,
        "verdict": "Needs Refinement",
        "rubric_scores": {"ownership": 40, "technical_depth": 40, "quantified_impact": 40, "structure": 40},
        "strengths": [],
        "areas_for_improvement": ["Explain your own decision."],
        "red_flags": [],
        "refined_answer_suggestion": "I chose a simpler queue.",
    }
    out = refit.evaluate_mock_interview_answer("Q?", "We did it.", j, p, use_llm=True, llm_caller=caller(llm_empty))
    assert out["strengths"] == [] and out["red_flags"] == []


def test_reviewer_structured_verdict_and_ceo_rewrite_cap(tools, world):
    from jh.team import qa
    rev_missing = qa.review_document("Too short", kind="other", profile=world["profile"])
    d = rev_missing.as_dict()
    assert d["verdict"] == "block" and d["status"] == "blocked_missing_data" and d["blockers"]

    rev_fix = qa.review_document("At Google I led 40 engineers and cut latency by 93%.", kind="other", profile=world["profile"])
    d_fix = rev_fix.as_dict()
    assert d_fix["status"] == "blocked_fixable" and d_fix["blockers"]

    jid = world["job"]["id"]
    mission = tools.call("ceo_run", request=f"write a cover letter for {jid}", hints={"job_id": jid, "polish": True})["data"]
    bad = "At Google I led 40 engineers and cut latency by 93%.\nAt Amazon I managed a 12 million dollar budget and 300 staff."
    r1 = tools.call("ceo_submit_work", mission_id=mission["mission_id"], task="cover_letter", text=bad, job_id=jid, kind="other")["data"]
    assert r1["rewrite_attempts"] == 1 and r1["rewrite_limit_reached"] is False
    r2 = tools.call("ceo_submit_work", mission_id=mission["mission_id"], task="cover_letter", text=bad, job_id=jid, kind="other")["data"]
    assert r2["rewrite_attempts"] == 2 and r2["rewrite_limit_reached"] is True


def test_mcp_tools_cover_letter_hook_and_follow_up_playbook(tools, world):
    jid = world["job"]["id"]
    cl = tools.call("cover_letter", job_id=jid)["data"]
    assert cl["hook"] and "missing_inputs" in cl
    pb = tools.call("get_playbook", task="application_follow_up", app_id=world["app_id"])["data"]
    app_ctx = pb["context"]["application"]
    assert {"role", "stage", "applied_date", "offered_salary"} <= set(app_ctx)
