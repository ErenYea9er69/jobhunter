"""JobHunter Coach Layer.

Provides optional, non-intrusive career coaching heuristics, triggered only
under explicit, objective conditions, delivered at most once per session.
"""
from __future__ import annotations

from .engine import (
    evaluate_coaching,
    get_coaching_content,
    get_coaching_context,
    record_coaching_event,
    set_coaching_preference,
)
from .profile_eval import evaluate_candidate_experience
from .triggers import PRIORITY_ORDER, evaluate_local_triggers

__all__ = [
    "evaluate_coaching",
    "get_coaching_content",
    "get_coaching_context",
    "record_coaching_event",
    "set_coaching_preference",
    "evaluate_candidate_experience",
    "evaluate_local_triggers",
    "PRIORITY_ORDER",
]
