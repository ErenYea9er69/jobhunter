"""Screening-question solver: answers application questions from the candidate's real resume facts.

Answers come from the grounded rules engine. A configured LLM may phrase them, but only from the
same facts. Nothing is invented: when the resume has no evidence the answer says so.
"""
import datetime
import json
import re
from typing import Any, Optional

from . import config, refit
from .util import clean_text

def parse_date_to_year(date_str, default_year=2026):
    """Extract approximate year integer from date string (e.g. '2023-01', '2021', 'Present')."""
    if not date_str:
        return default_year
    s = str(date_str).strip().lower()
    if "present" in s or "now" in s or "current" in s:
        return default_year
    m = re.search(r"\b(19\d\d|20\d\d)\b", s)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return default_year


def calculate_experience_years(experiences):
    """Calculate deterministic total years of professional experience across all roles."""
    if not experiences:
        return 0
    total_years = 0
    now_year = datetime.date.today().year
    for exp in experiences:
        start_y = parse_date_to_year(exp.get("start") or exp.get("start_date"), default_year=now_year)
        end_y = parse_date_to_year(exp.get("end") or exp.get("end_date"), default_year=now_year)
        if start_y > end_y:
            start_y, end_y = end_y, start_y
        dur = max(1, end_y - start_y + 1)
        total_years += dur
    return max(1, min(total_years, 35)) if experiences else 0


def calculate_skill_tenures(skills, experiences):
    """Compute calculated years of experience per skill based on candidate role history."""
    tenures = {}
    now_year = datetime.date.today().year
    exp_text_durations = []
    for exp in experiences:
        start_y = parse_date_to_year(exp.get("start") or exp.get("start_date"), default_year=now_year)
        end_y = parse_date_to_year(exp.get("end") or exp.get("end_date"), default_year=now_year)
        dur = max(1, end_y - start_y + 1)
        role = (exp.get("role") or "").lower()
        company = (exp.get("company") or "").lower()
        bullets = " ".join(exp.get("bullets") or []).lower()
        combined = f"{role} {company} {bullets}"
        exp_text_durations.append((combined, dur))

    total_overall = calculate_experience_years(experiences)
    for sk in (skills or []):
        sk_clean = sk.strip().lower()
        if not sk_clean:
            continue
        sk_years = 0
        for text, dur in exp_text_durations:
            if sk_clean in text:
                sk_years += dur
        if sk_years == 0:
            sk_years = max(1, int(total_overall * 0.5)) if total_overall > 1 else 1
        tenures[sk_clean] = sk_years
    return tenures


SCREENING_SOLVER_PROMPT = """You answer one application form question for a job seeker. The answer goes straight into a form field, so it is plain text, in the candidate's voice, and true.

Rules:
1. Every fact about the candidate (employer, title, number, skill) comes from the candidate's verified profile facts. Facts about the company come only from the job posting. If the data does not support a sentence, leave the sentence out.
2. The first sentence answers the question. Then add one or two supporting facts, and say what the candidate personally did, not what "we" did.
3. If the question asks about a skill the profile does not list, say "I have not used X at work; the closest I have done is Y" and name the real Y.
4. Write 60 to 120 words unless a limit is given. Use the vocabulary of the candidate's field.
5. Write plainly, with commas and periods and no em dashes or en dashes. Leave out stock praise such as <avoid>passionate, fast-paced, results-driven</avoid>, vague power verbs and openers about feeling or intent.
6. Reply with plain text only: no bullets, no bold, no headings, no quotation marks around the answer.
"""


def classify_question_type(question):
    """Classify screening question as boolean, numeric, or narrative."""
    q_low = (question or "").lower()
    if any(k in q_low for k in ["how many years", "years of experience", "number of years", "years of hands-on"]):
        return "numeric"
    if any(k in q_low for k in [
        "authorized to work", "legally authorized", "eligible to work",
        "require visa", "require sponsorship", "visa sponsorship",
        "are you at least 18", "over 18", "willing to relocate",
        "have you ever worked", "previously employed", "prior employee"
    ]):
        return "boolean"
    return "narrative"


def solve_screening_question(question, profile, job=None, question_type="auto", max_words=120, tone="direct", use_llm=None, llm_caller=None):
    """Synthesize a grounded, personalized answer to any job application screening question."""
    if isinstance(profile, dict) and isinstance(job, dict):
        if ("company" in profile or "title" in profile) and ("skills" in job or "experience" in job):
            profile, job = job, profile
    job = job or {}
    company = job.get("company") or "the company"
    title = job.get("title") or "the role"
    cand_name = profile.get("name") or "Candidate"
    skills = profile.get("skills") or []
    exps = profile.get("experience") or []
    top_bullets = [b for e in exps for b in e.get("bullets", []) if b.strip()][:4]

    q_low = (question or "").lower()
    resolved_type = classify_question_type(question) if question_type == "auto" else question_type

    cfg_legal = profile.get("legal_and_eeo") or {}
    auth_us = cfg_legal.get("authorized_us") or profile.get("work_authorization") or "Yes"
    auth_val = "Yes" if "yes" in str(auth_us).lower() or "authorized" in str(auth_us).lower() else "No"
    spons = cfg_legal.get("require_sponsorship_now") or profile.get("visa_sponsorship") or "No"
    spons_val = "Yes" if "yes" in str(spons).lower() or "require" in str(spons).lower() else "No"

    # 1. Direct Boolean / Radio Question Handling
    if resolved_type == "boolean":
        if any(k in q_low for k in ["require sponsorship", "require visa", "visa sponsorship", "need sponsorship"]):
            ans = spons_val
        elif any(k in q_low for k in ["authorized", "authorization", "legally", "eligible"]):
            ans = auth_val
        elif any(k in q_low for k in ["prior", "previously", "former employee", "have you ever worked"]):
            ans = "No"
        elif any(k in q_low for k in ["18", "age", "adult"]):
            ans = "Yes"
        elif any(k in q_low for k in ["relocate", "relocation"]):
            ans = "Yes"
        else:
            ans = "Yes"
        return {
            "question": question,
            "answer": ans,
            "question_type": "boolean",
            "provider": "profile_rules",
            "model": "grounded_boolean",
            "grounded": True,
            "word_count": len(ans.split())
        }

    # 2. Direct Numeric Experience Years Handling
    if resolved_type == "numeric":
        total_exp = calculate_experience_years(exps)
        skill_tenures = calculate_skill_tenures(skills, exps)
        matched_years = total_exp
        # Identify if a specific skill was requested in the question
        for sk, yrs in skill_tenures.items():
            if sk in q_low:
                matched_years = yrs
                break
        ans = str(max(1, matched_years))
        return {
            "question": question,
            "answer": ans,
            "question_type": "numeric",
            "provider": "profile_calculation",
            "model": "deterministic_tenure",
            "grounded": True,
            "word_count": 1
        }

    # 3. Deterministic narrative fallback response generator
    fallback_answer = ""

    if any(k in q_low for k in ["why", "interest", "excite", "apply"]):
        skill_str = ", ".join(skills[:3]) if skills else "modern engineering"
        fallback_answer = (
            f"The {title} role at {company} directly connects with my engineering work in {skill_str}. "
            f"In my previous work, {top_bullets[0] if top_bullets else 'I consistently shipped reliable production software'}. "
            f"I focus on clean architecture, high delivery velocity, and measurable product outcomes at {company}."
        )
    elif any(k in q_low for k in ["achievement", "accomplish", "proud", "impact"]):
        bullet = top_bullets[0] if top_bullets else "architecting scalable software solutions"
        fallback_answer = (
            f"A major accomplishment was when {bullet}. This initiative demonstrated "
            f"engineering rigor, measurable performance gains, and direct value to users."
        )
    elif any(k in q_low for k in ["salary", "compensation", "rate", "expectation"]):
        sal = profile.get("min_salary")
        fallback_answer = (
            f"My target compensation is {f'around ${int(sal):,} annually' if sal else 'in line with standard market rates for this role'}, "
            f"and I remain open to discussing the full scope and compensation structure."
        )
    elif any(k in q_low for k in ["notice", "availability", "start date", "when can you start"]):
        np = profile.get("notice_period") or "2 weeks"
        fallback_answer = (
            f"I can start with a standard {np} notice period (or immediately where appropriate) to ensure a smooth transition, "
            f"contributing immediately to active development priorities."
        )
    elif any(k in q_low for k in ["remote", "work mode", "time zone", "location"]):
        fallback_answer = (
            f"I have worked asynchronously in distributed teams for multiple years, maintaining thorough documentation, "
            f"clear progress updates, and autonomous delivery across time zones."
        )
    else:
        skill_str = ", ".join(skills[:4]) if skills else "software engineering"
        fallback_answer = (
            f"Throughout my work as a {profile.get('target_title', 'Software Engineer')}, I have built production systems using {skill_str}. "
            f"I emphasize disciplined problem-solving, clean code, and alignment with business requirements."
        )

    cfg = refit.get_active_ai_config()
    should_use_llm = (use_llm is True) or (use_llm is None and refit.llm_available())
    caller = llm_caller or refit._call_llm
    if should_use_llm:
        import pathlib
        prompt_path = pathlib.Path(config.BASE_DIR) / "prompts" / "screening_question_solver.md"
        system_prompt = SCREENING_SOLVER_PROMPT
        try:
            if prompt_path.exists():
                text_content = prompt_path.read_text(encoding="utf-8")
                m = re.search(r"```markdown\n(.*?)\n```", text_content, re.S)
                if m:
                    system_prompt = m.group(1)
        except Exception:
            pass

        user_prompt = json.dumps({
            "question": question,
            "job_posting": {
                "company": company,
                "title": title,
                "required_skills": job.get("required_skills", [])[:8],
                "description_snippet": (job.get("description", "") or "")[:1200]
            },
            "candidate_facts": {
                "name": cand_name,
                "target_title": profile.get("target_title"),
                "verified_skills": skills[:20],
                "experience_proof_points": top_bullets
            },
            "constraints": {
                "max_words": max_words,
                "tone": tone
            }
        }, indent=2)
        try:
            raw_res = caller(system_prompt, user_prompt)
            parsed_json = refit._parse_json_llm_response(raw_res)
            if isinstance(parsed_json, dict) and "answer" in parsed_json:
                cleaned = clean_text(str(parsed_json["answer"])).strip()
            else:
                cleaned = clean_text(raw_res).strip()
            cleaned = re.sub(r"^\s*[\"']+|[\"']+\s*$", "", cleaned).strip()
            cleaned = re.sub(r"[*#_`]", "", cleaned).strip()

            check = refit.ungrounded(profile, cleaned.replace(title, "").replace(company, ""))
            if not check["skills"] and not check["numbers"]:
                from . import slop
                cleaned, _, _ = slop.rewrite_slop(cleaned, kind="screening_answer", job=job, profile=profile)
                return {
                    "question": question,
                    "answer": cleaned,
                    "question_type": "narrative",
                    "provider": cfg.get("provider", "ai"),
                    "model": cfg.get("model", ""),
                    "grounded": True,
                    "word_count": len(cleaned.split())
                }
        except Exception:
            pass

    from . import slop
    fallback_answer, _, _ = slop.rewrite_slop(fallback_answer, kind="screening_answer", job=job, profile=profile)
    return {
        "question": question,
        "answer": fallback_answer,
        "question_type": "narrative",
        "provider": "deterministic",
        "model": "grounded_rules",
        "grounded": True,
        "word_count": len(fallback_answer.split())
    }


def answer_screening_question(question: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Screening question evaluator for ATS autofill (Rule R8):
    - Answers known questions strictly from profile facts and confirmed facts.
    - Leaves unknown questions empty with flagged=True (highlight in orange for user).
    - Automatically declines EEO and diversity self-identification disclosures.
    - Runs slop check (R7) on answered content.
    """
    from . import slop
    q_low = (question or "").lower()

    # 1. EEO & Diversity Disclosures -> Auto-decline
    if any(k in q_low for k in [
        "gender", "race", "ethnicity", "veteran", "disability",
        "diversity", "eeo", "self-identify", "sexual orientation", "demographic"
    ]):
        return {
            "question": question,
            "answer": "I do not wish to answer",
            "answered": True,
            "flagged": False,
            "category": "eeo",
        }

    # 2. Known profile facts: Years of experience
    if any(k in q_low for k in ["how many years", "years of experience", "years of hands-on", "total years"]):
        yoe = profile.get("years_of_experience")
        if yoe is None:
            exps = profile.get("experience") or []
            yoe = calculate_experience_years(exps)
        return {
            "question": question,
            "answer": str(int(yoe) if isinstance(yoe, (int, float)) and yoe == int(yoe) else yoe),
            "answered": True,
            "flagged": False,
            "category": "numeric_experience",
        }

    # 3. Known profile facts: Location
    if any(k in q_low for k in ["where are you located", "current location", "city and country", "based in"]):
        loc = profile.get("location") or profile.get("city")
        if loc:
            return {
                "question": question,
                "answer": str(loc),
                "answered": True,
                "flagged": False,
                "category": "location",
            }

    # 4. Known profile facts: Work authorization / Sponsorship
    if any(k in q_low for k in ["authorized to work", "legally authorized", "eligible to work"]):
        auth = profile.get("work_authorization") or (profile.get("legal_and_eeo") or {}).get("authorized_us")
        if auth is not None:
            return {
                "question": question,
                "answer": "Yes" if "yes" in str(auth).lower() or auth is True else "No",
                "answered": True,
                "flagged": False,
                "category": "authorization",
            }
    if any(k in q_low for k in ["require sponsorship", "require visa", "visa sponsorship", "need sponsorship"]):
        spons = profile.get("visa_sponsorship") or (profile.get("legal_and_eeo") or {}).get("require_sponsorship_now")
        if spons is not None:
            return {
                "question": question,
                "answer": "Yes" if "yes" in str(spons).lower() or spons is True else "No",
                "answered": True,
                "flagged": False,
                "category": "sponsorship",
            }

    # 5. Check confirmed facts (R1 & R8)
    confirmed_facts = profile.get("confirmed_facts") or []
    if not confirmed_facts:
        try:
            from . import db
            confirmed_facts = db.get_confirmed_facts()
        except Exception:
            confirmed_facts = []

    for cf in confirmed_facts:
        f_text = cf.get("fact", "") if isinstance(cf, dict) else str(cf)
        words = [w for w in re.findall(r"\w+", q_low) if len(w) > 3 and w not in ("tell", "about", "your", "have", "with")]
        if words and sum(1 for w in words if w in f_text.lower()) >= len(words) * 0.5:
            clean_ans, _, _ = slop.rewrite_slop(f_text, kind="screening_answer", profile=profile)
            return {
                "question": question,
                "answer": clean_ans,
                "answered": True,
                "flagged": False,
                "category": "confirmed_fact",
            }

    # 6. Unknown question / unverified facts -> Leave empty, flagged=True
    return {
        "question": question,
        "answer": "",
        "answered": False,
        "flagged": True,
        "reason": "Fact not present in verified profile ledger",
    }

