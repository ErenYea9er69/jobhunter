"""Dynamic Interview Questions Engine for JobHunter V3.

Builds personalized 2-round interview questions derived from the parsed resume:
Round 1: Role clarification (only when status is needs_role, confidence < 0.5).
Round 2: Preference refinement batch (6 questions or fewer) while search runs in background.
"""
from __future__ import annotations

from typing import Any


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
    """Generates Round 2 refinement batch (<= 6 questions) asked while background search is executing."""
    suggested_type = job_type_guess.get("value") or "full-time"
    suggested_region = region_guess.get("value") or "Any"
    
    questions = [
        {
            "id": "job_type",
            "number": 1,
            "title": "Job Type & Start Date",
            "question": "What job type are you seeking, and when is your earliest available start date?",
            "choices": ["internship (PFE)", "junior full-time", "full-time", "contract", "any"],
            "recommended": suggested_type,
            "note": f"Suggested: {suggested_type} (from resume/filename)",
        },
        {
            "id": "work_mode",
            "number": 2,
            "title": "Work Mode",
            "question": "What is your preferred work mode?",
            "choices": ["on-site", "hybrid", "remote", "any"],
            "recommended": "any",
        },
        {
            "id": "visa",
            "number": 3,
            "title": "Visa & Work Rights",
            "question": "Do you require visa sponsorship, and which countries do you hold legal work rights for?",
            "choices": ["no sponsorship needed", "visa sponsorship required", "any"],
            "recommended": "no sponsorship needed",
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
            "id": "company_type",
            "number": 5,
            "title": "Company Type & Exclusions",
            "question": "What company types do you prefer (startup, consulting, enterprise), and are there any companies or keywords you wish to skip?",
            "choices": ["any company type", "early-stage startup", "growth-stage / scale-up", "enterprise / big tech"],
            "recommended": "any company type",
        },
        {
            "id": "location",
            "number": 6,
            "title": "Location & Relocation",
            "question": "What locations are you targeting (e.g. Tunisia local, remote worldwide, remote in timezone, or abroad in specific countries)? Are you willing to relocate?",
            "choices": [suggested_region, "Remote worldwide", "Tunisia", "Europe / Abroad", "any"],
            "recommended": suggested_region,
            "note": f"Suggested: {suggested_region}",
        },
    ]

    formatted_lines = [
        "Please answer the following Round 2 preferences to filter your matches live:",
        "",
        "1. Job Type: internship (PFE), junior full-time, full-time, or contract? (What is your target start date?)",
        f"   [Suggested default: {suggested_type}]",
        "2. Work Mode: on-site, hybrid, remote, or any?",
        "   [Suggested default: any]",
        "3. Visa Sponsorship: do you require visa sponsorship, and where do you have work rights?",
        "   [Suggested default: no sponsorship needed]",
        "4. Pay / Compensation: minimum acceptable compensation, stipend, or any?",
        "   [Suggested default: any / market rate]",
        "5. Company Type & Exclusions: startup, consulting, enterprise? Any companies or keywords to skip?",
        "   [Suggested default: any company type]",
        f"6. Location: {suggested_region}, remote worldwide, specific countries, or willing to relocate?",
        f"   [Suggested default: {suggested_region}]",
        "",
        "(You can reply with your answers in plain text, or say 'skip all' / 'any' to proceed with defaults.)"
    ]

    return {
        "round": 2,
        "count": len(questions),
        "questions": questions,
        "formatted_text": "\n".join(formatted_lines),
    }
