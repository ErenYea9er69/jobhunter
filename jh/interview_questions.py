"""Dynamic Interview Questions Engine for JobHunter V3.

Builds personalized 2-round interview questions derived from the parsed resume:
Round 1: Role clarification (only when status is needs_role, confidence < 0.5).
Round 2: Preference refinement batch (6 questions or fewer) while search runs in background.
"""
from __future__ import annotations

from typing import Any


def build_step_3_target_questions(
    inferred_roles: list[dict[str, Any]],
    region_guess: dict[str, Any] | None = None,
    ask_role: bool = False,
) -> dict[str, Any]:
    """Generates Step 3 target search interview questions without ever guessing location from the resume."""
    role_choices = [r["role"] for r in inferred_roles]
    top_role = role_choices[0] if role_choices else "Software Engineer"

    place_choices = [
        "Remote only",
        "International / Worldwide remote",
        "France",
        "Europe",
        "South Asia",
        "United States (USA)",
    ]

    questions = [
        {
            "id": "target_place",
            "question": (
                "1. Target place (required before search, never guessed from your resume): "
                "Pick one or several: remote only, international or worldwide remote, or a specific place such as a country or region "
                "(for example France, Europe, South Asia, or the USA), plus an optional city if you want one."
            ),
            "choices": place_choices,
            "recommended": "",
            "required": True,
        },
    ]

    lines = [
        "Please confirm these target search questions before we run Hybrid search (signals + job boards; target place is required):",
        "1. Target place: remote only, international or worldwide remote, or a specific country/region (e.g. France, Europe, South Asia, USA)? You can pick one or several and add a city if you want one.",
    ]

    if ask_role:
        questions.append({
            "id": "target_role",
            "question": f"2. Target role: What target job title or role are you aiming for?\n   (Options from skill clusters/resume: {', '.join(role_choices)}; or name your own)",
            "choices": role_choices,
            "recommended": top_role,
        })
        lines.append(f"2. Target role: What target job title or role are you aiming for? (Options: {', '.join(role_choices)}; or name your own)")

    formatted_text = "\n".join(lines)

    return {
        "round": "target_search",
        "required": True,
        "ask_role": ask_role,
        "questions": questions,
        "formatted_text": formatted_text,
    }


def build_round_1_role_questions(inferred_roles: list[dict[str, Any]]) -> dict[str, Any]:
    """Generates Round 1 role clarification question when confidence is below 0.5."""
    role_choices = [r["role"] for r in inferred_roles]
    if "Software Engineer" not in role_choices:
        role_choices.append("Software Engineer")
    if "Full Stack Engineer" not in role_choices:
        role_choices.append("Full Stack Engineer")
        
    recommended = role_choices[0] if role_choices else "Software Engineer"
    
    question_text = (
        "1. What target job title or role are you aiming for?\n"
        f"   Options derived from your resume: {', '.join(role_choices)}\n"
        f"   Suggested default: {recommended}\n"
        "   (You can pick one, suggest your own, or combine roles)"
    )

    return {
        "round": 1,
        "required": True,
        "questions": [
            {
                "id": "target_role",
                "question": "What target job title or role are you aiming for?",
                "choices": role_choices,
                "recommended": recommended,
            }
        ],
        "formatted_text": question_text,
    }


def build_round_2_questions(profile: dict[str, Any], job_type_guess: dict[str, Any], region_guess: dict[str, Any], method: str = "hybrid") -> dict[str, Any]:
    """Generates Round 2 refinement batch asked while background search is executing."""
    suggested_type = job_type_guess.get("value") or "full-time"
    suggested_region = (region_guess.get("value") or "").strip()
    if not suggested_region or suggested_region.lower() in ("any", "unknown"):
        suggested_region = "Worldwide"
    
    loc_choices = [suggested_region]
    for c in ["Remote worldwide", "Worldwide", "Europe / Abroad", "any"]:
        if c not in loc_choices:
            loc_choices.append(c)

    questions = [
        {
            "id": "target_role",
            "number": 1,
            "title": "Desired Roles",
            "question": "What desired job title(s) or role focus are you targeting? (Confirm your resume role or adjust/widen it)",
            "choices": [profile.get("target_title") or "Software Engineer", "Full Stack Engineer", "Backend Engineer", "keep resume roles"],
            "recommended": profile.get("target_title") or "keep resume roles",
        },
        {
            "id": "work_mode",
            "number": 2,
            "title": "Work Mode",
            "question": "What is your preferred work mode?",
            "choices": ["remote", "hybrid", "on-site", "any"],
            "recommended": "any",
        },
        {
            "id": "job_type",
            "number": 3,
            "title": "Job Type & Start Date",
            "question": "What job type are you seeking, and when is your earliest available start date?",
            "choices": ["internship (PFE)", "junior full-time", "full-time", "contract", "any"],
            "recommended": suggested_type,
            "note": f"Suggested: {suggested_type} (from resume/filename)",
        },
        {
            "id": "pay",
            "number": 4,
            "title": "Target Compensation",
            "question": "What is your minimum acceptable compensation (or monthly stipend for internships), currency, and pay period?",
            "choices": ["any / market rate", "specify amount"],
            "recommended": "any / market rate",
        },
        {
            "id": "visa",
            "number": 5,
            "title": "Visa & Work Rights",
            "question": "Do you require visa sponsorship, and which countries do you hold legal work rights for?",
            "choices": ["no sponsorship needed", "visa sponsorship required", "any"],
            "recommended": "no sponsorship needed",
        },
        {
            "id": "company_type",
            "number": 6,
            "title": "Company Type & Exclusions",
            "question": "What company types do you prefer (startup, scale-up, enterprise), and are there any companies or keywords to exclude?",
            "choices": ["any company type", "early-stage startup", "growth-stage / scale-up", "enterprise / big tech"],
            "recommended": "any company type",
        },
    ]

    formatted_lines = [
        "Please confirm your job preferences to filter and rank your matches cleanly in chat:",
        "",
        f"1. Desired Roles: What target role(s) should we prioritize? [From resume: {profile.get('target_title') or 'any'}]",
        "2. Work Mode: remote, hybrid, on-site, or any? [Suggested default: any]",
        f"3. Job Type & Start Date: internship (PFE), junior full-time, full-time, or contract? Target start date? [Suggested default: {suggested_type}]",
        "4. Pay / Compensation: minimum acceptable salary/stipend, currency, or any? [Suggested default: any / market rate]",
        "5. Visa & Work Rights: do you require visa sponsorship, and where do you have work rights? [Suggested default: no sponsorship needed]",
        "6. Company Type & Exclusions: startup, scale-up, enterprise? Any companies or keywords to skip? [Suggested default: any company type]",
    ]

    optional_questions = [
        {
            "id": "industry",
            "title": "Industry",
            "question": "Optional - Target industries (e.g. SaaS, Fintech, Healthtech, AI, Cybersecurity, or any)?",
            "choices": ["any", "SaaS", "Fintech", "AI / ML", "Healthtech", "E-commerce"],
            "recommended": "any",
        },
        {
            "id": "company_stage",
            "title": "Company Stage",
            "question": "Optional - Preferred company stage (startup, scale-up, public, or any)?",
            "choices": ["any", "startup", "scale-up", "public"],
            "recommended": "any",
        },
        {
            "id": "market_served",
            "title": "Market Served",
            "question": "Optional - Target market served (e.g. B2B, B2C, Enterprise, SMB, Developer Tools, or any)?",
            "choices": ["any", "B2B", "B2C", "Enterprise", "SMB", "Developer Tools"],
            "recommended": "any",
        },
        {
            "id": "languages",
            "title": "Languages",
            "question": "Optional - Languages you work in (for example English only, French, bilingual English/French, or any)?",
            "choices": ["any", "English", "French", "Bilingual", "Arabic", "German", "Spanish"],
            "recommended": "any",
        },
        {
            "id": "side_work",
            "title": "Current Side / Freelance / Contract Work",
            "question": "Optional - Do you have any current side work, freelance, or contract work you want listed on tailored resumes (or 'none')?",
            "choices": ["none", "specify current freelance or contract work"],
            "recommended": "none",
        },
    ]

    formatted_lines.append("")
    formatted_lines.append("Optional targeting refinements (only your confirmed answers filter and rank matches):")
    formatted_lines.append("- Industry / stage / market: e.g. SaaS, Fintech, startup, B2B, or any")
    formatted_lines.append("- Languages / side work: working languages or current freelance work to include on tailored resumes")
    formatted_lines.append("")
    formatted_lines.append("(Reply in plain text, or say 'skip all' / 'any' to keep defaults.)")

    return {
        "round": 2,
        "count": len(questions),
        "questions": questions,
        "optional_questions": optional_questions,
        "formatted_text": "\n".join(formatted_lines),
    }


def generate_mock_interview_questions(job: dict[str, Any], resume_or_profile: Any = None) -> list[dict[str, Any]]:
    """Generate mock interview questions tailored to a specific job and candidate profile."""
    from . import interview
    profile = resume_or_profile if isinstance(resume_or_profile, dict) else {}
    prep = interview.generate_interview_prep(job, profile)
    questions = []
    for q in prep.get("behavioral_star_questions", []):
        if isinstance(q, dict):
            questions.append(q)
        else:
            questions.append({"question": str(q)})
    for tq in prep.get("technical_questions", []):
        questions.append({"question": tq})
    if not questions:
        questions = [
            {"question": "Tell me about a challenging technical tradeoff you had to make under tight deadlines."},
            {"question": "Describe a time you resolved a major production incident."}
        ]
    return questions

