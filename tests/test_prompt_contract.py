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
