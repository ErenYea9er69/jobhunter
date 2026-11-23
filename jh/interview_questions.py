"""Dynamic Interview Questions Engine for JobHunter V3.

Builds personalized 2-round interview questions derived from the parsed resume:
Round 1: Role clarification (only when status is needs_role, confidence < 0.5).
Round 2: Preference refinement batch (6 questions or fewer) while search runs in background.
"""
from __future__ import annotations

from typing import Any


def build_step_3_target_questions(
    inferred_roles: list[dict[str, Any]],
    region_guess: dict[str, Any],
    ask_role: bool = False,
) -> dict[str, Any]:
    """Generates Step 3 target search interview questions (3 questions max, all skippable)."""
    suggested_region = (region_guess.get("value") or "").strip()
    if not suggested_region or suggested_region.lower() in ("any", "unknown"):
        suggested_region = "Worldwide"

    role_choices = [r["role"] for r in inferred_roles]
    top_role = role_choices[0] if role_choices else "Software Engineer"

    questions = [
        {
            "id": "method",
            "question": "1. Method: Modern (default) or Classic?\n   - Modern: catches early funding signals and hiring posts and drafts human outreach to decision-maker emails under a daily cap.\n   - Classic: searches many job boards and has the Apply button.",
            "choices": ["Modern", "Classic"],
            "recommended": "Modern",
        },
        {
            "id": "target_place",
            "question": f"2. Target place: remote worldwide, within a time zone range, abroad (which countries), or a specific country/city? Are you open to relocation?\n   (Suggested: {suggested_region})",
            "choices": ["Remote worldwide", "Worldwide", "Europe", "United States", suggested_region],
            "recommended": suggested_region,
        },
    ]

    lines = [
        "Please answer these target search questions before we launch (all are skippable):",
        "1. Method: Modern (default) or Classic?",
        "   - Modern catches early funding signals and hiring posts and drafts human outreach to decision-maker emails under a daily cap.",
        "   - Classic searches many job boards and has the Apply button.",
        f"2. Target place: remote worldwide, within a time zone range, abroad (which countries), or a specific country/city? Are you open to relocation? (Suggested: {suggested_region})",
    ]

    if ask_role:
        questions.append({
            "id": "target_role",
            "question": f"3. Target role: What target job title or role are you aiming for?\n   (Options: {', '.join(role_choices)}; Suggested: {top_role})",
            "choices": role_choices,
            "recommended": top_role,
        })
        lines.append(f"3. Target role: What target job title or role are you aiming for? (Options: {', '.join(role_choices)}; Suggested: {top_role})")

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


def build_round_2_questions(profile: dict[str, Any], job_type_guess: dict[str, Any], region_guess: dict[str, Any]) -> dict[str, Any]:
    """Generates Round 2 refinement batch (7 questions in exact prompt order) asked while background search is executing."""
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
            "id": "location",
            "number": 1,
            "title": "Location & Relocation",
            "question": "What locations are you targeting (e.g. specific city, country, region, remote within a timezone range, or countries abroad)? Are you willing to relocate?",
            "choices": loc_choices,
            "recommended": suggested_region,
            "note": f"Suggested: {suggested_region} (from resume/guess)",
        },
        {
            "id": "level",
            "number": 2,
            "title": "Level & Way of Search",
            "question": "What level or way of search do you prefer: match my level (default), one level up (reach), one level down (safe), or a different role (pivot)?",
            "choices": ["match my level", "one level up (reach)", "one level down (safe)", "different role (pivot)"],
            "recommended": "match my level",
            "note": "Suggested default: match my level",
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
            "id": "work_mode",
            "number": 4,
            "title": "Work Mode",
            "question": "What is your preferred work mode?",
            "choices": ["on-site", "hybrid", "remote", "any"],
            "recommended": "any",
        },
        {
            "id": "pay",
            "number": 5,
            "title": "Target Compensation",
            "question": "What is your minimum acceptable compensation (or monthly stipend for internships), currency, and pay period?",
            "choices": ["any / market rate", "specify amount"],
            "recommended": "any / market rate",
        },
        {
            "id": "visa",
            "number": 6,
            "title": "Visa & Work Rights",
            "question": "Do you require visa sponsorship, and which countries do you hold legal work rights for?",
            "choices": ["no sponsorship needed", "visa sponsorship required", "any"],
            "recommended": "no sponsorship needed",
        },
        {
            "id": "company_type",
            "number": 7,
            "title": "Company Type & Exclusions",
            "question": "What company types do you prefer (startup, consulting, enterprise), and are there any companies or keywords you wish to skip?",
            "choices": ["any company type", "early-stage startup", "growth-stage / scale-up", "enterprise / big tech"],
            "recommended": "any company type",
        },
    ]

    formatted_lines = [
        "Please answer the following Round 2 preferences to filter your matches live:",
        "",
        f"1. Location: {suggested_region}, specific city, remote worldwide, timezone range, or countries abroad? Open to relocation?",
        f"   [Suggested default: {suggested_region}]",
        "2. Level / Way of Search: match my level (default), one level up (reach), one level down (safe), or a different role (pivot)?",
        "   [Suggested default: match my level]",
        "3. Job Type: internship (PFE), junior full-time, full-time, or contract? (What is your target start date?)",
        f"   [Suggested default: {suggested_type}]",
        "4. Work Mode: on-site, hybrid, remote, or any?",
        "   [Suggested default: any]",
        "5. Pay / Compensation: minimum acceptable compensation, stipend, or any?",
        "   [Suggested default: any / market rate]",
        "6. Visa Sponsorship: do you require visa sponsorship, and where do you have work rights?",
        "   [Suggested default: no sponsorship needed]",
        "7. Company Type & Exclusions: startup, consulting, enterprise? Any companies or keywords to skip?",
        "   [Suggested default: any company type]",
        "",
        "(You can reply with your answers in plain text, or say 'skip all' / 'any' to proceed with defaults.)"
    ]

    return {
        "round": 2,
        "count": len(questions),
        "questions": questions,
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

