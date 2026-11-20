"""Session Ticket & State Manager for JobHunter V3.

Manages 2-hour tickets binding session, resume, and role focus.
Enforces gates across launch, search, and alias tools.
Tracks explicit user skips and maintains idempotency across tool calls.
"""
from __future__ import annotations

import secrets
import time
from typing import Any, Optional

from . import db, util

TICKET_TTL_SECONDS = 2 * 3600  # 2 hours

_TICKETS: dict[str, dict[str, Any]] = {}
_SESSIONS: dict[str, dict[str, Any]] = {}


def generate_ticket(session_id: str, resume_id: str, roles: list[str], method: str = "modern", location: str = "") -> str:
    """Issue a cryptographically secure 2-hour ticket bound to session, resume, roles, method, and location."""
    ticket = f"jh_tkt_{secrets.token_hex(16)}"
    now = time.time()
    payload = {
        "ticket": ticket,
        "session_id": session_id,
        "resume_id": resume_id,
        "roles": roles,
        "method": method,
        "location": location,
        "issued_at": now,
        "expires_at": now + TICKET_TTL_SECONDS,
        "used_for_launch": False,
    }
    _TICKETS[ticket] = payload
    
    # Store in session state
    sess = get_or_create_session(session_id)
    sess["active_ticket"] = ticket
    sess["resume_id"] = resume_id
    sess["role_focus"] = roles
    sess["method"] = method
    sess["location"] = location
    
    return ticket


def validate_ticket(session_id: str, ticket: str) -> tuple[bool, Optional[str]]:
    """Validate ticket existence, session binding, and expiration."""
    if not ticket or not isinstance(ticket, str):
        return False, "Missing ticket. A valid ticket from jh_begin or jh_confirm is required."
    
    t = _TICKETS.get(ticket)
    if not t:
        return False, "Invalid ticket. The ticket was not recognized."
    
    if t["session_id"] != session_id:
        return False, f"Ticket mismatch: ticket was issued for session '{t['session_id']}', not '{session_id}'."
    
    if time.time() > t["expires_at"]:
        return False, "Ticket has expired (tickets are valid for 2 hours). Call jh_begin to obtain a fresh ticket."
        
    return True, None


def get_or_create_session(session_id: str) -> dict[str, Any]:
    """Retrieve or initialize in-memory session object."""
    sid = session_id or "default"
    if sid not in _SESSIONS:
        _SESSIONS[sid] = {
            "session_id": sid,
            "status": "initial",
            "step": 1,
            "resume_path": "",
            "resume_text": "",
            "resume_id": "",
            "profile": {},
            "check_result": {},
            "inference_result": {},
            "role_focus": [],
            "answers": {},
            "skipped_fields": {},
            "skip_log": [],
            "active_ticket": None,
            "search_job_id": None,
            "worker_port": None,
            "launch_time": None,
            "last_questions": None,
        }
    return _SESSIONS[sid]


def is_explicit_skip(text: str) -> bool:
    """Check if the user response explicitly indicates a skip."""
    clean = (text or "").lower().strip()
    return clean in {"skip", "any", "skip all", "pass", "none", "no preference", "default"}


def record_user_reply(session_id: str, user_reply: str) -> None:
    """Record verbatim user reply in session log."""
    sess = get_or_create_session(session_id)
    if "user_replies" not in sess:
        sess["user_replies"] = []
    sess["user_replies"].append({
        "user_reply": user_reply,
        "timestamp": util.now_iso(),
    })


def record_user_skip(session_id: str, field_name: str, user_reply: str) -> None:
    """Record an explicit user skip with exact verbatim words."""
    sess = get_or_create_session(session_id)
    sess["skipped_fields"][field_name] = "any"
    sess["skip_log"].append({
        "field": field_name,
        "user_reply": user_reply,
        "timestamp": util.now_iso(),
    })


def mark_ticket_launched(ticket: str) -> None:
    """Record that the ticket was consumed to launch worker/search."""
    if ticket in _TICKETS:
        _TICKETS[ticket]["used_for_launch"] = True


def build_stop_message(questions_text: str, context_line: str = "") -> str:
    """Build standard message_for_user containing the mandatory STOP prompt."""
    lines = ["STOP. Ask the user the questions below and wait for the answer. Do not call another tool."]
    if context_line:
        lines.append(context_line)
    lines.append("")
    lines.append(questions_text)
    return "\n".join(lines)
