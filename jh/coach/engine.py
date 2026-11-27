"""Core orchestration engine for JobHunter Coach Layer.

Provides context, template retrieval, trigger evaluation, and state updates.
All operations are non-blocking and fail safely to null.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from .. import config, db
from . import profile_eval, triggers

log = logging.getLogger("jobhunter.coach.engine")


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "jh" / "coach"
    return Path(__file__).resolve().parent


def load_templates(lang: str = "en") -> dict[str, Any]:
    """Load vetted content templates for coaching triggers."""
    base = _get_base_dir() / "templates"
    target = base / f"{lang}.json"
    if not target.is_file():
        target = base / "en.json"
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Failed to load templates for '%s': %s", lang, e)
        return {}


def get_coaching_context(session_id: str = "default", profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return objective signals and coaching state for the MCP host or Web UI.

    Output format:
    {
        experience_level: 'entry' | 'mid' | 'senior' | 'unknown',
        experience_confidence: 'high' | 'medium' | 'low',
        years_estimate: float,
        top_match_scores: list[float],
        coaching_enabled: bool,
        opt_out: bool,
        advice_given: list[str],
        locale: str
    }
    """
    sid = session_id or "default"
    prof = profile or db.get_profile()
    cand_exp = profile_eval.evaluate_candidate_experience(prof)
    state = db.get_coach_state(sid)
    events = db.get_coach_events(sid)

    # Get recent top match scores from search_jobs
    top_scores: list[float] = []
    try:
        top_scores = db.get_top_search_scores(limit=5)
    except Exception:
        pass

    locale = config.get_coach_lang() or "US"

    return {
        "experience_level": cand_exp["experience_level"],
        "experience_confidence": cand_exp["experience_confidence"],
        "years_estimate": cand_exp["years_estimate"],
        "top_match_scores": top_scores,
        "coaching_enabled": state["coaching_enabled"],
        "opt_out": state["opt_out"],
        "advice_given": events,
        "locale": locale,
    }


def get_coaching_content(trigger_id: str, language: str = "en", locale: str = "US") -> dict[str, Any]:
    """Return vetted coaching text and options for a given trigger ID (<= 120 words)."""
    tid = (trigger_id or "").strip().upper()
    lang = language or config.get_coach_lang() or "en"
    templates = load_templates(lang)
    tmpl = templates.get(tid)
    if not tmpl:
        # Fallback to English
        templates = load_templates("en")
        tmpl = templates.get(tid)

    if not tmpl:
        return {
            "trigger_id": tid,
            "title": "Coaching Guidance",
            "text": "Practical career heuristics and guidance are available when you need them.",
            "options": ["Proceed with search"],
            "choice": "Would you like advice, or just to proceed with searching jobs?",
        }

    # Format emergency message if Trigger S
    if tid == "S":
        em_info = triggers.get_emergency_info(locale)
        crisis_text = em_info.get("text", "Please contact local emergency services or a trusted person.")
        body = tmpl["template"].replace("{crisis_text}", crisis_text)
        opts = [opt.replace("{crisis_text}", crisis_text) for opt in tmpl.get("options", [])]
        return {
            "trigger_id": tid,
            "title": tmpl.get("title", "Safety & Support"),
            "acknowledgment": tmpl.get("acknowledgment", ""),
            "insight": tmpl.get("insight", ""),
            "options": opts,
            "choice": tmpl.get("choice", ""),
            "text": body,
            "emergency_contact": em_info,
        }

    return {
        "trigger_id": tid,
        "title": tmpl.get("title", "Career Strategy"),
        "acknowledgment": tmpl.get("acknowledgment", ""),
        "insight": tmpl.get("insight", ""),
        "options": tmpl.get("options", []),
        "choice": tmpl.get("choice", ""),
        "text": tmpl.get("template", ""),
    }


def record_coaching_event(trigger_id: str, session_id: str = "default") -> bool:
    """Mark advice for a trigger as delivered in this session (once-only)."""
    return db.record_coach_event(session_id=session_id, trigger_id=trigger_id)


def set_coaching_preference(enabled: bool, scope: str = "session", session_id: str = "default") -> dict[str, Any]:
    """Enable or disable coaching with session or persistent scope."""
    return db.set_coaching_preference(enabled=enabled, scope=scope, session_id=session_id)


def _call_provider_coaching(user_text: str, trigger_id: str, lang: str = "en") -> Optional[str]:
    """Call AI provider for coaching text if configured, with strict fallback."""
    try:
        from ..ai_manager import get_ai_manager
        ai = get_ai_manager()
        prompt = f"User request: {user_text}\nTrigger: {trigger_id}\nProvide a brief practical coaching note of <= 120 words grounded in the user's request and evidence."
        return ai.generate_text(prompt)
    except Exception as e:
        log.warning("Provider coaching failed or timed out: %s", e)
        return None


def evaluate_coaching(
    user_text: str,
    session_id: str = "default",
    profile: dict[str, Any] | None = None,
    match_scores: list[float] | None = None,
    top_match_scores: list[float] | None = None,
    locale: str = "US",
) -> Optional[dict[str, Any]]:
    """Non-blocking coaching trigger evaluator.

    Returns a dict with coaching content if a trigger fires and has not yet been delivered,
    or None if no coaching applies. Never raises exceptions or blocks search.
    """
    try:
        if top_match_scores is not None and match_scores is None:
            match_scores = top_match_scores

        # Check global coaching switch
        if config.get_coaching_mode() == "off":
            return None

        classifier_mode = config.get_coach_classifier()
        if classifier_mode == "off":
            return None

        sid = session_id or "default"
        state = db.get_coach_state(sid)
        is_opted_out = state["opt_out"] or not state.get("coaching_enabled", True)

        events = db.get_coach_events(sid)
        prof = profile or db.get_profile()
        threshold = config.get_coach_threshold()
        lang = config.get_coach_lang() or "en"

        # Check for opt-out in message
        lex = triggers.load_lexicon(lang)
        is_sess_opt, _ = triggers.check_opt_out(user_text, lex)
        if is_sess_opt and not state["opt_out"]:
            db.set_coach_state(sid, opt_out=True)
            is_opted_out = True

        # Run local classifier
        match = triggers.evaluate_local_triggers(
            user_text=user_text,
            profile=prof,
            match_scores=match_scores,
            session_events=events,
            opt_out=is_opted_out,
            threshold=threshold,
            lang=lang,
            locale=locale,
        )

        if not match:
            return None

        # Build content payload
        content = get_coaching_content(match.trigger_id, language=lang, locale=locale)
        content["trigger_id"] = match.trigger_id
        content["reason"] = match.reason
        content["confidence"] = match.confidence
        content["metadata"] = match.metadata

        # If provider classifier enabled, try refining text with fallback
        if classifier_mode == "provider":
            try:
                refined = _call_provider_coaching(user_text, match.trigger_id, lang=lang)
                if refined:
                    content["text"] = refined
            except Exception as pe:
                log.warning("Provider refinement caught: %s", pe)

        # Record event so it only fires once
        db.record_coach_event(sid, match.trigger_id)

        return content

    except Exception as e:
        log.warning("Coaching evaluation safely caught exception: %s", e)
        return None
