"""Session Ticket & State Manager for JobHunter V3.

Manages 2-hour tickets binding session, resume, and role focus.
Enforces gates across launch, search, and alias tools.
Tracks explicit user skips and maintains idempotency across tool calls.
"""
from __future__ import annotations

from enum import Enum
import os
import secrets
import time
from typing import Any, Optional

from . import db, util

TICKET_TTL_SECONDS = 2 * 3600  # 2 hours

_TICKETS: dict[str, dict[str, Any]] = {}
_SESSIONS: dict[str, dict[str, Any]] = {}


class SessionState(str, Enum):
    NEW = "NEW"
    RESUME_OK = "RESUME_OK"
    ASKED = "ASKED"
    ANSWERED = "ANSWERED"
    LAUNCHED = "LAUNCHED"
    ROUND2_DONE = "ROUND2_DONE"


def get_session_state_name(session_id: str) -> SessionState:
    """Return canonical session state for session_id."""
    sess = get_or_create_session(session_id)
    raw = sess.get("session_state") or SessionState.NEW
    if isinstance(raw, SessionState):
        return raw
    try:
        return SessionState(str(raw))
    except ValueError:
        return SessionState.NEW


def transition_session_state(session_id: str, new_state: SessionState) -> None:
    """Update session state in memory and database."""
    sess = get_or_create_session(session_id)
    sess["session_state"] = new_state
    db.set_session_state(new_state.value, session_id=session_id)


def check_tool_state_gate(session_id: str, tool_name: str, ticket: str = "") -> tuple[bool, Optional[dict[str, Any]]]:
    """Check whether tool_name is permitted in current session state.
    Returns (True, None) if permitted, or (False, refusal_dict) if out of order.
    """
    state = get_session_state_name(session_id)
    sess = get_or_create_session(session_id)

    # 1. NEW state: only resume ingestion permitted
    if state == SessionState.NEW:
        if tool_name not in ("jh_begin", "jh_load_resume", "parse_resume_file", "scan_resumes", "list_resumes", "get_resume"):
            pending_q = "Please provide your resume path or text to start the JobHunter process."
            return False, {
                "status": "needs_input",
                "step": 1,
                "message_for_user": build_stop_message(pending_q, f"Session is in state NEW. Tool '{tool_name}' requires a loaded resume."),
                "ask_user": pending_q,
                "next_tool": "jh_begin",
                "data": {"error": f"Tool '{tool_name}' cannot be called before resume is loaded.", "state": state.value}
            }

    # 2. ASKED state: Round 1 questions pending answer via jh_confirm
    elif state == SessionState.ASKED:
        if tool_name not in ("jh_confirm", "jh_begin", "get_resume", "list_resumes"):
            last_q = sess.get("last_questions") or {}
            q_text = last_q.get("formatted_text") or sess.get("last_questions_text") or "Please answer the Round 1 target questions (Target place and Role)."
            return False, {
                "status": "needs_input",
                "step": 2,
                "message_for_user": build_stop_message(q_text, f"Session is in state ASKED. Tool '{tool_name}' is not permitted until Round 1 is answered."),
                "ask_user": q_text,
                "next_tool": "jh_confirm",
                "data": {"error": f"Round 1 questions must be answered first via jh_confirm.", "state": state.value}
            }

    # 3. jh_launch gate: allowed only in ANSWERED state, requires valid ticket
    if tool_name == "jh_launch":
        if state not in (SessionState.ANSWERED, SessionState.LAUNCHED):
            last_q = sess.get("last_questions_text") or "Please complete the setup questions first."
            next_t = "jh_confirm" if state in (SessionState.NEW, SessionState.ASKED) else "jh_begin"
            return False, {
                "status": "needs_input",
                "step": 2,
                "message_for_user": build_stop_message(last_q, f"jh_launch requires state ANSWERED and a valid ticket. Current state: {state.value}."),
                "ask_user": last_q,
                "next_tool": next_t,
                "data": {"error": f"Cannot launch in state '{state.value}'.", "state": state.value}
            }
        valid, err = validate_ticket(session_id, ticket)
        if not valid:
            return False, {
                "status": "needs_input",
                "step": 2,
                "message_for_user": build_stop_message(f"Gate blocked: {err}\nYou must run jh_confirm to obtain a valid ticket."),
                "ask_user": "Please answer the Round 1 target questions to obtain a ticket.",
                "next_tool": "jh_confirm",
                "data": {"error": err, "state": state.value}
            }

    # 4. Search tools (jh_search, search_jobs, jh_query, query_jobs)
    if tool_name in ("jh_search", "search_jobs", "jh_query", "query_jobs"):
        if state in (SessionState.NEW, SessionState.ASKED):
            next_t = "jh_confirm" if state == SessionState.ASKED else "jh_begin"
            q_text = sess.get("last_questions_text") or "Please provide your resume and answer targeting questions first."
            return False, {
                "status": "needs_input",
                "step": 2 if state == SessionState.ASKED else 1,
                "message_for_user": build_stop_message(q_text, f"Search tool '{tool_name}' cannot be called before questions are answered. Current state: {state.value}."),
                "ask_user": q_text,
                "next_tool": next_t,
                "data": {"error": f"Cannot search in state '{state.value}'.", "state": state.value}
            }

    return True, None


def generate_ticket(session_id: str, resume_id: str, roles: list[str], method: str = "hybrid", location: str = "") -> str:
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


def issue_ticket(session_id: str, resume_id: str = "", roles: list[str] | None = None, method: str = "hybrid", location: str = "", **kwargs) -> str:
    """Issue ticket alias."""
    return generate_ticket(session_id=session_id, resume_id=resume_id, roles=roles or [], method=method, location=location)


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
    """Check if the user response explicitly indicates a skip ('skip', 'any', 'skip all')."""
    clean = (text or "").lower().strip()
    return clean in {"skip", "any", "skip all"}


def record_questions_presented(session_id: str, questions_text: str = "") -> None:
    """Track when questions were returned to the user and what was asked."""
    sess = get_or_create_session(session_id)
    sess["questions_presented_at"] = time.time()
    if questions_text:
        sess["last_questions_text"] = questions_text


def validate_user_reply(session_id: str, user_reply: str) -> tuple[bool, Optional[str]]:
    """Reject empty, trivial (< 2 chars), or verbatim question repeats."""
    sess = get_or_create_session(session_id)
    if user_reply is None or not isinstance(user_reply, str):
        return False, "user_reply is empty. Preferences and filters may be written only with the user's words."
    clean = user_reply.strip()
    if not clean:
        return False, "user_reply is empty. Preferences and filters may be written only with the user's words."
    if len(clean) < 2:
        return False, "user_reply is under 2 characters. Please provide valid answers."

    last_q = (sess.get("last_questions_text") or "").strip().lower()
    if last_q and clean.lower() == last_q:
        return False, "user_reply merely repeats the questions."

    q_signatures = [
        "stop. ask the user the questions below",
        "method: modern (default) or classic",
        "method: modern or classic",
        "target place: tunisia, remote worldwide",
        "target place: tunisia",
        "what target job title or role are you aiming for",
    ]
    if any(sig in clean.lower() for sig in q_signatures):
        return False, "user_reply merely repeats the questions."

    return True, None


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
