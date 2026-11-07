"""The prompts as a contract. They are text, but the code reads what they ask a model to produce, and a model copies the
style of the prompt it is given. These tests check both: the keys match what the code reads, and the prompts follow the
rules they teach."""

import json
import pathlib
import re

import pytest

import mcp_server
from jh import refit, screening
from jh.team import directives, roles, voice
from jh.team.ceo import RELAY_RULES

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
JH = ROOT / "jh"

PLAYBOOKS = ["cover_letter", "resume_tailor", "interview_prep", "mock_interview_evaluator", "recruiter_outreach",
             "application_follow_up", "screening_question_solver", "career_skill_roadmap"]

# What the code reads from a model's reply, and from which file. Found by reading the consumers in 2.4.
# (source file, keys read from the reply, keys the code sends in the user message)
CONTRACT = {
    "cover_letter": ("refit.py", {"full_text", "pitch_hook", "why_company", "honest_bridge", "call_to_action", "value_pillars"},
                     {"job_post", "candidate_source", "value_pillars", "honest_skill_gaps", "pitch_angle", "tone"}),
    "resume_tailor": ("refit.py", {"executive_hook", "bullets"}, {"job", "candidate", "archetype"}),
    "interview_prep": ("refit.py", {"role", "company", "interview_focus_areas", "technical_deep_dives", "behavioral_scenarios",
                                    "gap_talking_points", "questions_to_ask_interviewer"}, {"job_post", "candidate_source"}),
    "mock_interview_evaluator": ("refit.py", {"overall_score", "verdict", "rubric_scores", "strengths", "areas_for_improvement",
                                              "red_flags", "refined_answer_suggestion"}, {"question", "candidate_answer", "job_post", "candidate_source"}),
    "recruiter_outreach": ("refit.py", {"linkedin_connection_note", "target_company", "target_role", "hiring_manager_inmail",
                                        "peer_referral_request", "key_proof_point_used"}, {"job_post", "candidate_source", "standout_bullet", "custom_hook"}),
    "application_follow_up": ("tracker.py", {"body", "action_type", "subject_line", "strategy_notes", "recommended_send_timing"},
                              {"application", "candidate_source", "follow_up_type"}),
    "screening_question_solver": ("screening.py", {"answer"}, {"question", "job_posting", "candidate_facts", "constraints"}),
    "career_skill_roadmap": ("refit.py", {"fast_track_project", "target_title", "top_missing_skills", "interview_bridge_script",
                                          "recommended_learning_resources"}, {"candidate_source", "market_requirements"}),
}
NESTED = {
    "cover_letter": ["theme", "proof_point"],
    "interview_prep": ["topic", "question", "talking_point", "tip", "skill", "recommended_response"],
    "mock_interview_evaluator": ["ownership", "technical_depth", "quantified_impact", "structure"],
    "recruiter_outreach": ["subject_line", "body"],
    "career_skill_roadmap": ["skill", "market_demand_level", "why_important", "project_title", "architecture_summary", "deliverables",
                             "time_to_complete_days", "topic", "focus_area"],
}


def text(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def system(name: str) -> str:
    m = re.search(r"```markdown\n(.*?)\n```", text(name), re.S)
    assert m, f"{name}: no markdown block"
    return m.group(1)


def output_block(name: str) -> str:
    m = re.search(r"<output>(.*?)</output>", system(name), re.S)
    assert m, f"{name}: no <output> block"
    return m.group(1)


def schema_keys(name: str) -> set[str]:
    return set(re.findall(r'(?m)^  "(\w+)"\s*:', output_block(name)))


def canonical_voice() -> str:
    return re.search(r"<!-- voice:start -->\n(.*?)\n<!-- voice:end -->", (PROMPTS / "voice.md").read_text(encoding="utf-8"), re.S).group(1).strip()


# ------------------------------------------------------------------ extraction and shape

@pytest.mark.parametrize("name", PLAYBOOKS)
def test_the_system_prompt_extracts_the_same_way_in_every_reader_of_it(name):
    raw = text(name)
    assert raw.count("```markdown") == 1                                  # the code takes the first block; a second would be silent noise
    server_style = re.search(r"```markdown\n(.*?)```", raw, re.S).group(1).strip()      # jh/mcp_tools.py
    refit_style = re.search(r"```markdown\n(.*?)\n```", raw, re.S).group(1).strip()      # jh/refit.py, screening.py, tracker.py
    assert server_style == refit_style == system(name).strip()
    assert "```" not in system(name)


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_system_prompts_say_json_so_the_model_is_put_in_json_mode(name):
    # refit._call_llm turns on JSON mode when the word "json" appears in the system or user message.
    assert "json" in system(name).lower()


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_prompt_size_is_bounded(name):
    n = len(system(name).split())
    assert 350 <= n <= 1000, n


# ------------------------------------------------------------------ the contract with the code

@pytest.mark.parametrize("name", PLAYBOOKS)
def test_every_key_the_code_reads_is_in_the_schema_the_prompt_asks_for(name):
    _, reads, _ = CONTRACT[name]
    assert reads <= schema_keys(name), f"{name} asks for {sorted(schema_keys(name))} but the code reads {sorted(reads - schema_keys(name))} too"


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_the_keys_in_this_test_are_still_the_ones_the_code_reads(name):
    """If someone renames a key in the code, this fails and says to update the prompt and CONTRACT together."""
    src_file, reads, sends = CONTRACT[name]
    src = (JH / src_file).read_text(encoding="utf-8")
    missing = [k for k in reads if f'"{k}"' not in src]
    assert not missing, f"{src_file} no longer mentions {missing}"
    if name != "resume_tailor":      # the resume payload is built under other names in two code paths
        missing = [k for k in sends if f'"{k}"' not in src]
        assert not missing, f"{src_file} no longer sends {missing}"


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_the_prompt_describes_every_input_the_code_sends(name):
    _, _, sends = CONTRACT[name]
    body = system(name)
    if name == "resume_tailor":
        assert {"job", "candidate", "archetype"} <= set(re.findall(r"(?m)^- (\w+):", re.search(r"<inputs>(.*?)</inputs>", body, re.S).group(1)))
        return
    inputs = re.search(r"<inputs>(.*?)</inputs>", body, re.S).group(1)
    missing = [k for k in sends if k not in inputs and not (k in ("pitch_angle", "tone") and "pitch_angle and tone" in inputs)]
    assert not missing, f"{name} does not describe {missing}"


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_nested_keys_are_named_in_the_schema(name):
    for key in NESTED.get(name, []):
        assert f'"{key}"' in output_block(name) or key in output_block(name), f"{name}: {key}"


def test_the_old_wrong_keys_are_gone():
    wrong = {"cover_letter": ["letter_text"], "interview_prep": ["technical_questions", "behavioral_story_outlines", "questions_for_interviewer"],
             "mock_interview_evaluator": ["total_score", "dimension_scores"], "recruiter_outreach": ["draft_text"],
             "application_follow_up": ["draft_text"], "screening_question_solver": ["answer_text"],
             "career_skill_roadmap": ["priority_gaps", "milestones", "project_specification"],
             "resume_tailor": ["recruiter_6sec_audit", "skim_score", "ats_score"]}
    for name, keys in wrong.items():
        for k in keys:
            assert k not in system(name), f"{name} still mentions {k}"


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_the_schema_holds_no_example_values_a_model_would_copy(name):
    block = output_block(name)
    stripped = re.sub(r"<[^>]*>", "", block)                           # <whole number> style placeholders are fine
    assert not re.search(r'":\s*-?\d', stripped), "numeric literal in the schema"
    assert "ev_" not in block and "telemetry" not in block and "word_count" not in block and "char_count" not in block


# ------------------------------------------------------------------ the rules the prompts teach, applied to themselves

ALL_PROMPT_FILES = [PROMPTS / f"{n}.md" for n in PLAYBOOKS] + [PROMPTS / "voice.md"] + sorted((PROMPTS / "team").glob("*.md"))


@pytest.mark.parametrize("path", ALL_PROMPT_FILES, ids=lambda p: p.name)
def test_every_prompt_file_follows_its_own_style_rules(path):
    issues = voice.lint_prompt(path.read_text(encoding="utf-8"))
    assert issues == {}, issues


def test_no_prompt_file_contains_an_em_dash_or_en_dash_anywhere_but_quoted_examples():
    for path in ALL_PROMPT_FILES:
        body = voice.strip_exempt(path.read_text(encoding="utf-8"))
        assert "\u2014" not in body and "\u2013" not in body, path.name


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_the_shared_voice_block_is_identical_in_every_playbook(name):
    assert canonical_voice() in system(name)


@pytest.mark.parametrize("who", ["writer", "coach"])
def test_roles_that_write_for_the_client_carry_the_same_voice_block(who):
    assert canonical_voice() in (PROMPTS / "team" / f"{who}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_examples_teach_what_they_say(name):
    body = system(name)
    robotic = re.findall(r"<robotic>(.*?)</robotic>", body, re.S)
    plain = re.findall(r"<plain>(.*?)</plain>", body, re.S)
    assert robotic and len(robotic) == len(plain), "each example needs a robotic and a plain version"
    for r in robotic:
        assert voice.scan(r, "prose"), f"the robotic example does not trip the scanner: {r[:60]}"
    for p in plain:
        assert voice.scan(p, "prose") == [], f"the plain example is not plain: {p[:60]}"
    assert "Do not reuse" in body                                      # examples are illustrations


def test_examples_across_the_playbooks_are_not_all_about_software():
    plain = " ".join(" ".join(re.findall(r"<plain>(.*?)</plain>", system(n), re.S)) for n in PLAYBOOKS).lower()
    fields = {"finance": ["ledger", "month", "invoice", "accounts", "sap", "oracle"], "teaching": ["students", "maths", "lesson"],
              "operations": ["dispatch", "warehouse", "freight", "supplier", "planner", "distributor"]}
    assert sum(any(w in plain for w in words) for words in fields.values()) == 3


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_untrusted_posting_text_is_named_as_data(name):
    body = system(name)
    assert re.search(r"ignore them|ignore instructions", body)


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_every_schema_lets_the_model_ask_instead_of_guessing(name):
    assert "missing_inputs" in schema_keys(name) or name == "mock_interview_evaluator"


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_the_prompt_asks_for_two_modes_of_output(name):
    body = output_block(name)
    assert "If the user message is a JSON object" in body and "plain prose" in body


def test_no_prompt_claims_a_score_a_model_cannot_measure():
    for name in PLAYBOOKS:
        body = system(name).lower()
        assert "ats score" not in body and "match score" not in body and "skim" not in body and "95%" not in body


# ------------------------------------------------------------------ specific fixes

def test_linkedin_note_limit_is_200_and_there_is_one_number():
    body = system("recruiter_outreach")
    assert "200 characters" in body and "300 characters" not in body.replace("Premium allows 300", "")
    assert not re.search(r"under 300|295", body)


def test_follow_up_asks_questions_instead_of_leaving_placeholders():
    body = system("application_follow_up")
    assert "missing_inputs" in body and "placeholder" in body.lower()
    assert "invent a salary range" in body and "market figure" in body


def test_mock_scoring_has_anchors_and_matches_the_codes_scale():
    body = system("mock_interview_evaluator")
    assert "0 to 100" in body and "Strong Contender" in body and "Solid Foundation" in body and "Needs Refinement" in body
    assert "Strong Hire" not in body and "Lean Hire" not in body
    assert body.count("0 to 30") >= 4 and body.count("70 to 100") >= 4          # an anchor for every dimension


def test_the_roadmap_bridge_script_cannot_claim_unfinished_work():
    body = system("career_skill_roadmap")
    assert '"Now:"' in body and '"After the project:"' in body and "Do not let the first line claim the project exists" in body


def test_resume_prompt_does_not_ask_for_a_literal_formula_or_inflated_verbs():
    body = system("resume_tailor")
    assert "as measured by" in body and "Do not write template words" in body
    assert "Architected" not in body and "Engineered" not in body


# ------------------------------------------------------------------ prompts that live in code

def test_prompts_embedded_in_code_follow_the_same_rules():
    blocks = {"LLM_SYSTEM": refit.LLM_SYSTEM, "COVER_PITCH_LLM_SYSTEM": refit.COVER_PITCH_LLM_SYSTEM,
              "SCREENING_SOLVER_PROMPT": screening.SCREENING_SOLVER_PROMPT, "INSTRUCTIONS": mcp_server.INSTRUCTIONS,
              "RELAY_RULES": "\n".join(RELAY_RULES), "STANDARD_LIMITS": "\n".join(directives.STANDARD_LIMITS)}
    for name, t in blocks.items():
        assert voice.lint_prompt(t) == {}, (name, voice.lint_prompt(t))


def test_embedded_prompts_keep_the_keys_their_own_code_path_reads():
    assert '"summary"' in refit.LLM_SYSTEM and '"bullets"' in refit.LLM_SYSTEM          # refit_llm reads summary and bullets
    for k in ("full_text", "pitch_hook", "value_pillars", "why_company", "honest_bridge", "call_to_action"):
        assert k in refit.COVER_PITCH_LLM_SYSTEM
    assert "json" not in screening.SCREENING_SOLVER_PROMPT.lower()                      # plain text mode for the default screening prompt


def test_tool_descriptions_the_client_ai_reads_follow_the_rules(tmp_path):
    import asyncio
    server = mcp_server.create_server(str(tmp_path), surface="team")
    for tool in asyncio.run(server.list_tools()):
        assert voice.lint_prompt(tool.description or "") == {}, tool.name


def test_role_prompts_still_load_and_the_client_can_override_them(tmp_path):
    for key in roles.ROSTER:
        assert len(roles.role_prompt(key, tmp_path)) > 200 or key == "ops"
    (tmp_path / "prompts" / "team").mkdir(parents=True)
    (tmp_path / "prompts" / "team" / "writer.md").write_text("Custom.", encoding="utf-8")
    assert roles.role_prompt("writer", tmp_path) == "Custom."


def test_the_ceo_prompt_tells_the_ai_about_intent_and_reference_hints():
    t = (PROMPTS / "team" / "ceo.md").read_text(encoding="utf-8")
    assert "hints.reference" in t and "hints.intent" in t and "em dashes" in t


def test_reviewer_prompt_mentions_scams_and_style():
    t = (PROMPTS / "team" / "reviewer.md").read_text(encoding="utf-8").lower()
    assert "scam" in t and "machine-sounding" in t and "alternative" in t
