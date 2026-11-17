"""Candidate profile evaluation for coaching triggers.

Derives experience level and confidence objectively from resume data
(years of experience, job titles, education/internship history) and user words.
NEVER infers from age, gender, name, or other protected traits.
"""
from __future__ import annotations

import re
from typing import Any


SENIORITY_RANKS: dict[str, int] = {
    "intern": 0,
    "entry": 1,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "lead_staff": 4,
    "lead": 4,
    "staff": 4,
    "principal": 4,
    "director": 5,
    "executive": 5,
    "vp": 5,
}


def parse_seniority_from_title(title: str) -> str:
    """Classify seniority level from a job title string."""
    t = (title or "").lower().strip()
    if any(k in t for k in ["intern", "internship", "co-op", "trainee"]):
        return "intern"
    if any(k in t for k in ["junior", "jr", "entry", "associate", "graduate", "apprentice"]):
        return "entry"
    if any(k in t for k in ["director", "vp", "head of", "chief", "executive", "vp of"]):
        return "director"
    if any(k in t for k in ["lead", "staff", "principal", "architect", "fellow"]):
        return "lead_staff"
    if any(k in t for k in ["senior", "sr."]) or re.search(r"\bsr\b", t):
        return "senior"
    return "mid"


def evaluate_candidate_experience(profile: dict[str, Any] | None, user_text: str = "") -> dict[str, Any]:
    """Derive experience level ('entry' | 'mid' | 'senior') and confidence ('high' | 'medium' | 'low').

    Derivation rules:
    - Purely objective: years of experience, past job titles, education, internships.
    - NEVER considers name, age, gender, photo, or demographics.
    - Confidence is 'low' if signals conflict or profile is missing.
    """
    if not profile or profile.get("_is_empty"):
        # Check if user text explicitly states entry level
        u_lower = (user_text or "").lower()
        if re.search(r"\b(i am a|i'm a|as a)?\s*(recent grad|junior|entry level|first job|new graduate)\b", u_lower):
            return {
                "experience_level": "entry",
                "experience_confidence": "medium",
                "years_estimate": 0.0,
                "seniority_rank": 1,
                "is_entry": True,
            }
        return {
            "experience_level": "unknown",
            "experience_confidence": "low",
            "years_estimate": 0.0,
            "seniority_rank": 1,
            "is_entry": False,
        }

    # 1. Years of experience
    years = 0.0
    try:
        years = float(profile.get("total_years_experience") or profile.get("years_of_experience") or 0.0)
    except (ValueError, TypeError):
        pass

    # 2. Past titles
    titles = []
    experiences = profile.get("experience") or []
    for exp in experiences:
        if isinstance(exp, dict) and exp.get("role"):
            titles.append(str(exp["role"]))
    for r in profile.get("roles") or []:
        if isinstance(r, str):
            titles.append(r)
    target_title = profile.get("target_title", "")
    if target_title:
        titles.append(target_title)

    title_seniorities = [parse_seniority_from_title(t) for t in titles]

    # 3. Education / student status
    has_recent_grad = False
    has_internships_only = bool(experiences) and all(
        parse_seniority_from_title(t) in ("intern", "entry") for t in title_seniorities
    )
    education = profile.get("education") or []
    if education and not experiences:
        has_recent_grad = True

    # 4. User words
    u_lower = (user_text or "").lower()
    user_claims_entry = bool(re.search(r"\b(i am|i'm|as a)?\s*(recent grad|junior|entry level|first job|new grad|intern)\b", u_lower))
    user_claims_senior = bool(re.search(r"\b(i am|i'm|have|with)\s*(a\s+)?(senior|10\+ years|15 years|staff|principal|lead)\b", u_lower))

    has_any_signal = bool(experiences or education or titles or profile.get("total_years_experience") is not None or profile.get("years_of_experience") is not None or user_claims_entry)
    if not has_any_signal:
        return {
            "experience_level": "unknown",
            "experience_confidence": "low",
            "years_estimate": 0.0,
            "seniority_rank": 1,
            "is_entry": False,
        }

    # Evaluate level
    if years >= 5.0 or "senior" in title_seniorities or "lead_staff" in title_seniorities or "director" in title_seniorities:
        level = "senior"
        conf = "high"
        if user_claims_entry:
            conf = "low"  # Conflict!
    elif years >= 2.5:
        level = "mid"
        conf = "high" if not user_claims_entry else "medium"
    else:
        # <= 2.0 years or entry/intern titles
        level = "entry"
        if has_internships_only or years <= 1.0 or user_claims_entry or has_recent_grad:
            conf = "high"
        else:
            conf = "medium"
        if user_claims_senior:
            conf = "low"  # Conflict!

    rank = SENIORITY_RANKS.get(level, 2)
    is_entry = (level == "entry" and conf in ("high", "medium"))

    return {
        "experience_level": level,
        "experience_confidence": conf,
        "years_estimate": years,
        "seniority_rank": rank,
        "is_entry": is_entry,
    }


def check_seniority_gap(candidate_rank: int, target_title: str) -> tuple[int, bool]:
    """Calculate the gap between candidate seniority rank and target title rank.

    Returns (gap, is_mismatch) where is_mismatch is True if gap >= 2.
    """
    target_seniority = parse_seniority_from_title(target_title)
    target_rank = SENIORITY_RANKS.get(target_seniority, 2)
    gap = target_rank - candidate_rank
    return gap, gap >= 2
