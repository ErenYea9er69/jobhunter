"""Trigger classification engine for JobHunter Coach Layer.

Evaluates user-authored requests against triggers S, D, A, B, C, E with strict priority:
S > D > A > B > C > E.
Each trigger delivers advice at most once per session unless explicitly re-requested.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import profile_eval

log = logging.getLogger("jobhunter.coach.triggers")

PRIORITY_ORDER = ["S", "D", "A", "B", "C", "E"]


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "jh" / "coach"
    return Path(__file__).resolve().parent


def load_lexicon(lang: str = "en") -> dict[str, list[str]]:
    """Load trigger regex patterns for the specified language."""
    base = _get_base_dir() / "lexicons"
    target = base / f"{lang}.json"
    if not target.is_file():
        target = base / "en.json"
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Failed to load lexicon for '%s': %s", lang, e)
        return {}


def load_emergency_directory() -> dict[str, Any]:
    """Load emergency hotline info."""
    path = _get_base_dir() / "emergency.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "default": {
                "name": "Local Emergency Services",
                "number": "your local emergency number",
                "text": "If you are in distress or need immediate support, please reach out to local emergency services or a trusted person."
            }
        }


def get_emergency_info(locale: str = "US") -> dict[str, str]:
    """Return emergency contact info for a given country or default."""
    data = load_emergency_directory()
    loc = (locale or "").upper().strip()
    return data.get(loc) or data.get("default") or {
        "name": "Local Emergency Services",
        "number": "your local emergency number",
        "text": "Please reach out to your local emergency services or a trusted person."
    }


@dataclass
class TriggerMatch:
    trigger_id: str
    priority: int
    confidence: float
    reason: str
    options: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def check_opt_out(text: str, lexicon: dict[str, list[str]]) -> tuple[bool, bool]:
    """Check if the user input contains opt-out phrases.

    Returns (is_session_opt_out, is_request_opt_out).
    """
    clean = text.lower().strip()
    session_patterns = lexicon.get("opt_out_session", [])
    request_patterns = lexicon.get("opt_out_request", [])

    is_session = any(bool(re.search(pat, clean)) for pat in session_patterns)
    is_request = any(bool(re.search(pat, clean)) for pat in request_patterns)

    return is_session, is_request


def evaluate_local_triggers(
    user_text: str,
    profile: dict[str, Any] | None = None,
    match_scores: list[float] | None = None,
    session_events: list[str] | None = None,
    opt_out: bool = False,
    threshold: float = 60.0,
    lang: str = "en",
    locale: str = "US",
) -> Optional[TriggerMatch]:
    """Evaluate candidate triggers deterministically using local lexicons and profile data."""
    if not user_text or not user_text.strip():
        return None

    clean = user_text.strip()
    u_lower = clean.lower()
    lex = load_lexicon(lang)
    events = set(session_events or [])

    # 1. Opt-out analysis
    is_sess_opt, is_req_opt = check_opt_out(clean, lex)
    user_opted_out = opt_out or is_sess_opt or is_req_opt

    # Explicit advice check (Trigger A)
    has_explicit_advice = any(bool(re.search(p, u_lower)) for p in lex.get("explicit_advice", []))

    # TRIGGER S: Safety (ALWAYS on, ignores opt-out completely)
    for pat in lex.get("safety_patterns", []):
        if re.search(pat, u_lower):
            em_info = get_emergency_info(locale)
            return TriggerMatch(
                trigger_id="S",
                priority=1,
                confidence=1.0,
                reason="Signs of crisis, self-harm, or despair detected.",
                metadata={"emergency": em_info, "overrode_opt_out": user_opted_out},
            )

    # If user opted out, stop here UNLESS they explicitly asked for advice (Trigger A)
    if user_opted_out and not has_explicit_advice:
        return None

    # TRIGGER D: Distress or AI career anxiety
    if "D" not in events:
        # Check distress/stuck
        is_stuck = any(bool(re.search(p, u_lower)) for p in lex.get("distress_stuck", []))
        is_ai_anxiety = False
        if any(bool(re.search(p, u_lower)) for p in lex.get("distress_ai", [])):
            # Must NOT be a neutral question about AI jobs/skills
            is_neutral = any(bool(re.search(np, u_lower)) for np in lex.get("distress_ai_negatives", []))
            if not is_neutral:
                is_ai_anxiety = True

        if is_stuck or is_ai_anxiety:
            reason = "AI career anxiety detected." if is_ai_anxiety else "Search distress / fatigue detected."
            return TriggerMatch(
                trigger_id="D",
                priority=2,
                confidence=0.9,
                reason=reason,
                metadata={"is_ai_anxiety": is_ai_anxiety, "is_stuck": is_stuck},
            )

    # TRIGGER A: Explicit advice request (Overrides session opt-out for this request)
    if has_explicit_advice and ("A" not in events or has_explicit_advice):
        return TriggerMatch(
            trigger_id="A",
            priority=3,
            confidence=0.95,
            reason="User explicitly requested advice, opinion, or help deciding.",
            metadata={"explicit_override": user_opted_out},
        )

    # TRIGGER B: Entry-level + aspirational request + objective mismatch
    if "B" not in events:
        # Condition 1: Candidate is entry level with confidence >= medium
        cand_exp = profile_eval.evaluate_candidate_experience(profile, clean)
        if cand_exp["is_entry"]:
            # Condition 2: Aspirational request
            has_aspirational_neg = any(bool(re.search(p, u_lower)) for p in lex.get("aspirational_negatives", []))
            has_aspirational = not has_aspirational_neg and any(
                bool(re.search(p, u_lower)) for p in lex.get("aspirational", [])
            )

            if has_aspirational:
                # Condition 3: Objective mismatch (Seniority gap >= 2 OR top match scores < threshold)
                _, has_seniority_mismatch = profile_eval.check_seniority_gap(cand_exp["seniority_rank"], clean)

                score_mismatch = False
                if match_scores is not None and len(match_scores) > 0:
                    top_scores = sorted(match_scores, reverse=True)[:5]
                    # If best 5 results are below threshold
                    if all(s < threshold for s in top_scores):
                        score_mismatch = True

                if has_seniority_mismatch or score_mismatch:
                    return TriggerMatch(
                        trigger_id="B",
                        priority=4,
                        confidence=0.88,
                        reason="Entry-level candidate with aspirational reach target and objective mismatch.",
                        metadata={
                            "seniority_mismatch": has_seniority_mismatch,
                            "score_mismatch": score_mismatch,
                            "cand_exp": cand_exp,
                        },
                    )

    # TRIGGER C: Asks what business to start / how to make money with a business
    if "C" not in events:
        if any(bool(re.search(p, u_lower)) for p in lex.get("business", [])):
            return TriggerMatch(
                trigger_id="C",
                priority=5,
                confidence=0.9,
                reason="User asked about starting a business or independent monetization.",
            )

    # TRIGGER E: Career direction or "what am I good at"
    if "E" not in events:
        has_e_neg = any(bool(re.search(p, u_lower)) for p in lex.get("career_direction_negatives", []))
        if not has_e_neg and any(bool(re.search(p, u_lower)) for p in lex.get("career_direction", [])):
            return TriggerMatch(
                trigger_id="E",
                priority=6,
                confidence=0.85,
                reason="User asked for career direction or discovering their core strengths.",
            )

    return None
