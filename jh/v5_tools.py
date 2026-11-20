"""V5 MCP Tools: Guided interview flow, broad search, narrow view, and workspace isolation.

Updated for JobHunter V3: ticket gating, detached background worker, 
and live query-time filtering while maintaining 100% backward compatibility.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Optional

from . import (
    config,
    db,
    dedup,
    home,
    interview_questions,
    pipeline,
    preferences,
    resume_checker,
    role_inference,
    scoring,
    ticket_manager,
    util,
    worker_launcher,
    workspace,
)
from .mcp_helpers import Result, ToolError

log = logging.getLogger("jobhunter.v5")


def _is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _find_free_port(start_port: int = 8765, host: str = "127.0.0.1") -> int:
    port = start_port
    while port < start_port + 50:
        if not _is_port_in_use(port, host):
            return port
        port += 1
    return start_port


def _coaching_envelope(fn):
    """Decorator ensuring that every tool response dictionary structurally includes 'coaching': null by default."""
    import functools
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        res = fn(*args, **kwargs)
        if isinstance(res, dict):
            res.setdefault("coaching", None)
        return res
    return wrapper


def check_filter_clashes(filters: dict[str, Any]) -> list[str]:
    """Detect contradictory search criteria and provide actionable fix suggestions."""
    warnings = []
    wm = (filters.get("work_mode") or "any").lower().strip()
    locs = filters.get("locations") or []
    reloc = bool(filters.get("relocation"))
    min_sal = float(filters.get("min_salary") or 0)
    sen = [str(s).lower() for s in (filters.get("seniority") or [])]
    visa = bool(filters.get("visa_need"))
    visa_countries = filters.get("visa_countries") or []

    # 1. Remote + specific city clash
    if wm == "remote" and len(locs) == 1 and not reloc:
        city = locs[0]
        if "remote" not in city.lower() and "worldwide" not in city.lower():
            warnings.append(
                f"Clash detected: Work mode is 'remote' but specific location '{city}' was requested. "
                f"Remote positions are generally location-independent. "
                f"Suggested fix: Set work mode to 'any'/'hybrid' if you require '{city}', or remove the location restriction."
            )

    # 2. Extreme salary for entry/junior level
    if min_sal > 350000 and any(s in ("junior", "entry", "intern") for s in sen):
        warnings.append(
            f"Clash detected: Minimum salary of ${min_sal:,.0f} is significantly above market bands for entry/junior levels. "
            f"Suggested fix: Lower minimum salary threshold (e.g. $120,000 - $160,000) or adjust seniority level."
        )

    # 3. Visa sponsorship requested without target countries for onsite role
    if visa and wm in ("onsite", "hybrid") and not visa_countries and not locs:
        warnings.append(
            "Clash detected: Visa sponsorship requested for onsite/hybrid roles without eligible destination countries. "
            "Suggested fix: Specify target countries (e.g. US, Canada, UK) where you seek sponsorship."
        )

    return warnings


@_coaching_envelope
def jh_set_method(method: str = "modern", session_id: str = "default") -> dict[str, Any]:
    """Step 4: Set active job hunting method: 'modern' (outreach first, default) or 'classic' (job boards & apply).
    Preserves all existing data across switches.
    """
    clean = config.set_method(method)
    db.set_session_state(f"method_{clean}", last_tool="jh_set_method")
    if clean == "modern":
        msg = (
            "Switched to Modern method: outreach first. Catch fresh hiring posts and seed funding news, "
            "find decision-maker emails, and send a short human email before the crowd applies. "
            "All Classic job board data and applications remain intact."
        )
        next_tool = "jh_start"
    else:
        msg = (
            "Switched to Classic method: job boards and Apply button. "
            "Broad search, view filters, and tailored resume & cover letter generation. "
            "All Modern signals, company briefs, and outreach records remain intact."
        )
        next_tool = "jh_search"

    return {
        "status": "ok",
        "step": 4,
        "message_for_user": msg,
        "ask_user": None,
        "options": {
            "method": clean,
            "choices": ["modern", "classic"],
            "recommended": "modern"
        },
        "next_tool": next_tool,
        "data": {
            "method": clean,
        }
    }


@_coaching_envelope
def jh_start(prompt: str = "", intent: str = "", session_id: str = "default", **kwargs) -> dict[str, Any]:
    """Step 1 & 2: Entry point for any job-related prompt.
    If session_id != 'default' or a resume is attached, delegates to jh_begin.
    Otherwise sets up isolated workspace, loads saved profile and view filters, detects intent, and returns guided question.
    """
    if session_id != "default" or kwargs.get("resume_path") or kwargs.get("resume_text"):
        return jh_begin(
            resume_path=kwargs.get("resume_path", ""),
            resume_text=kwargs.get("resume_text", ""),
            session_id=session_id,
        )

    home_dir = home.get_home()
    db.set_session_state("guided_interview", last_tool="jh_start")

    # Detect user intent from prompt if not explicitly passed
    p_lower = (prompt or "").lower().strip()
    detected_intent = intent or "new_search"
    if not intent and p_lower:
        if any(w in p_lower for w in ["switch method", "change method", "set method", "toggle method"]):
            detected_intent = "switch_method"
        elif any(w in p_lower for w in ["status", "health", "how many", "state"]):
            detected_intent = "status"
        elif any(w in p_lower for w in ["filter", "salary", "remote", "criteria", "set filter"]):
            detected_intent = "edit_filters"
        elif any(w in p_lower for w in ["refresh", "reload", "pull new"]):
            detected_intent = "refresh"
        elif any(w in p_lower for w in ["tailor", "cover letter", "resume", "regenerate"]):
            detected_intent = "regenerate"

    # Branch on switch_method
    if detected_intent == "switch_method":
        curr = config.get_method()
        alt = "classic" if curr == "modern" else "modern"
        return {
            "status": "needs_input",
            "step": "method_choice",
            "message_for_user": f"Active method is '{curr.capitalize()}'. Switching methods preserves all stored jobs, signals, and outreach records.",
            "ask_user": f"Would you like to switch to '{alt.capitalize()}' method, or stay with '{curr.capitalize()}'?",
            "options": {
                "choices": [alt, curr],
                "recommended": alt,
            },
            "next_tool": "jh_set_method",
            "data": {
                "current_method": curr,
                "target_method": alt,
            }
        }

    # Branch on status intent
    if detected_intent == "status":
        return jh_status(session_id=session_id)

    # Load saved profile and view filters
    saved_filters = db.get_view_filters(session_id)
    profile = db.get_profile()
    active_method = config.get_method()

    has_saved_filters = bool(saved_filters.get("job_style") or saved_filters.get("roles") or saved_filters.get("min_salary"))
    has_profile = bool(not profile.get("_is_empty") and profile.get("target_title"))

    # Returning user with saved filters
    if has_saved_filters and detected_intent != "edit_filters":
        msg = (
            f"Welcome back! Loaded saved filters from {home_dir}:\n"
            f"- Method: {active_method.capitalize()}\n"
            f"- Job Style / Role: {saved_filters.get('job_style') or 'Any'}\n"
            f"- Work Mode: {saved_filters.get('work_mode')}\n"
            f"- Roles: {', '.join(saved_filters.get('roles', [])) or 'Any'}\n"
            f"- Min Salary: ${saved_filters.get('min_salary', 0):,.0f}\n"
            f"- Locations: {', '.join(saved_filters.get('locations', [])) or 'Any'}"
        )
        return {
            "status": "ok",
            "step": 2,
            "message_for_user": msg,
            "ask_user": "Would you like to reuse these saved filters, edit them, or start over?",
            "options": {
                "choices": ["reuse", "edit", "start over"],
                "recommended": "reuse",
            },
            "next_tool": "jh_search" if (active_method == "classic" and saved_filters.get("job_style")) else ("jh_open_ui" if active_method == "modern" else "jh_set_filters"),
            "data": {
                "method": active_method,
                "saved_filters": saved_filters,
                "has_profile": has_profile,
            }
        }

    # New search or edit filters: Guided Interview
    if active_method == "modern":
        round_1_questions = [
            {"id": "target_role", "question": "What target role are you looking for? (Required for Signal Radar, e.g. Frontend Engineer, ML Engineer)", "recommended": profile.get("target_title") or "Software Engineer"},
            {"id": "region", "question": "What is your target region and time zone? (or 'any')", "recommended": "any"},
            {"id": "stage", "question": "Target company funding stage? (pre-seed, seed, series A, or any)", "recommended": "any", "choices": ["any", "pre-seed", "seed", "series A"]},
            {"id": "min_salary", "question": "What is your minimum annual compensation? (or 'any')", "recommended": "any"},
            {"id": "visa_need", "question": "Do you require visa sponsorship?", "recommended": "no", "choices": ["no", "yes"]},
            {"id": "work_mode", "question": "Preferred work mode?", "recommended": "any", "choices": ["any", "remote", "onsite", "hybrid"]}
        ]
        return {
            "status": "needs_input",
            "step": 4,
            "message_for_user": f"Workspace initialized at {home_dir}. Active Method: Modern (outreach first).",
            "ask_user": "Please review and confirm your Modern outreach criteria (Round 1 of 2; target role is required, others can be 'any'):",
            "options": {
                "round": 1,
                "method": "modern",
                "questions": round_1_questions,
                "recommended": {
                    "target_role": profile.get("target_title") or "Software Engineer",
                    "job_style": profile.get("target_title") or "tech jobs",
                    "region": "any",
                    "stage": "any",
                    "min_salary": "any",
                    "visa_need": "no",
                    "work_mode": "any",
                }
            },
            "next_tool": "jh_set_filters",
            "data": {
                "method": "modern",
                "has_profile": has_profile,
                "interview_rules": "Only target role is required. Any is valid for others. 7 questions max per round.",
            }
        }
    else:
        round_1_questions = [
            {"id": "job_style", "question": "What kind of job style or domain are you targeting?", "recommended": saved_filters.get("job_style") or "tech jobs"},
            {"id": "work_mode", "question": "What is your preferred work mode?", "recommended": saved_filters.get("work_mode") or "any", "choices": ["any", "remote", "hybrid", "onsite"]},
            {"id": "locations", "question": "What is your target location or country?", "recommended": ", ".join(saved_filters.get("locations", [])) or "any"},
            {"id": "min_salary", "question": "What is your minimum acceptable annual salary?", "recommended": str(saved_filters.get("min_salary", 0)) if saved_filters.get("min_salary") else "any"},
            {"id": "visa_need", "question": "Do you require visa sponsorship?", "recommended": "yes" if saved_filters.get("visa_need") else "no", "choices": ["no", "yes"]}
        ]
        return {
            "status": "needs_input",
            "step": 4,
            "message_for_user": f"Workspace initialized at {home_dir}. Active Method: Classic (job boards).",
            "ask_user": "Please review and confirm your initial job criteria (Round 1 of 2):",
            "options": {
                "round": 1,
                "method": "classic",
                "questions": round_1_questions,
                "recommended": {"job_style": "tech jobs", "work_mode": "any", "locations": "any", "min_salary": "any", "visa_need": "no"}
            },
            "next_tool": "jh_set_filters",
            "data": {
                "method": "classic",
                "has_profile": has_profile,
                "interview_rules": "Ask in rounds, 7 questions max per round. 'any' is valid. Hard filters hide, soft rank.",
            }
        }


@_coaching_envelope
def jh_load_resume(resume_path: str = "", raw_text: str = "", profile_id: str = "master", session_id: str = "default") -> dict[str, Any]:
    """Step 3: Load, parse, and extract skills, target roles, and experience from a resume file or raw text into candidate profile."""
    if session_id != "default":
        return jh_begin(resume_path=resume_path, resume_text=raw_text, session_id=session_id)

    ws = home.get_home()
    parsed_profile = None

    if resume_path:
        p = Path(resume_path)
        if not p.is_file():
            p = ws / "resumes" / resume_path
        if p.is_file():
            try:
                parsed_profile = workspace.parse_resume_variant(p)
            except Exception as e:
                raise ToolError(f"Failed to parse resume at '{resume_path}': {e}")
        else:
            raise ToolError(f"Resume file not found at '{resume_path}'", hint="Provide valid path to PDF, DOCX, or TXT resume.")

    elif raw_text and raw_text.strip():
        parsed_profile = dict(db.EMPTY_PROFILE)
        parsed_profile["summary"] = raw_text[:500]
        parsed_profile["skills"] = [w for w in ["Python", "JavaScript", "TypeScript", "SQL", "Docker", "AWS", "Go", "Java", "React"] if w.lower() in raw_text.lower()]
        parsed_profile["target_title"] = "Software Engineer"
        parsed_profile["_is_empty"] = False

    else:
        resumes_dir = ws / "resumes"
        resumes_dir.mkdir(parents=True, exist_ok=True)
        found = workspace.discover_resumes(resumes_dir)
        if found:
            parsed_profile = workspace.parse_resume_variant(found[0]["path"])
        else:
            return {
                "status": "needs_input",
                "step": 3,
                "message_for_user": f"No resume found in {resumes_dir}.",
                "ask_user": "Please provide a resume file path or paste resume text to extract your skills and experience.",
                "options": {
                    "choices": ["provide file path", "paste text", "skip resume"],
                    "recommended": "skip resume"
                },
                "next_tool": "jh_load_resume"
            }

    if parsed_profile:
        parsed_profile["_profile_id"] = profile_id
        parsed_profile["_profile_name"] = f"Profile {profile_id}"
        db.save_profile(parsed_profile, profile_id=profile_id)

    title = parsed_profile.get("target_title", "Candidate")
    skills = parsed_profile.get("skills", [])
    years = parsed_profile.get("years_of_experience", 0)

    return {
        "status": "ok",
        "step": 3,
        "message_for_user": (
            f"Parsed resume for {parsed_profile.get('name') or 'Candidate'}.\n"
            f"- Inferred Target Title: {title}\n"
            f"- Extracted Skills ({len(skills)}): {', '.join(skills[:8])}{'...' if len(skills) > 8 else ''}\n"
            f"- Experience: ~{years:.1f} years"
        ),
        "ask_user": "Would you like to confirm this profile or override any field (e.g. target_title)?",
        "options": {
            "choices": ["confirm", "override target_title", "rescan"],
            "recommended": "confirm"
        },
        "next_tool": "jh_confirm_profile",
        "data": {
            "profile_id": profile_id,
            "target_title": title,
            "skills": skills,
            "years_of_experience": years,
            "profile": parsed_profile
        }
    }


@_coaching_envelope
def jh_confirm_profile(confirmed: bool = True, overrides: Optional[dict[str, Any]] = None,
                       portfolio_url: str = "", proof_points: Optional[list[dict[str, str]]] = None,
                       profile_id: str = "master") -> dict[str, Any]:
    """Step 3: Confirm candidate target roles, skills, and portfolio proof points for outreach."""
    prof = db.get_profile(profile_id)
    if overrides and isinstance(overrides, dict):
        prof.update(overrides)

    if portfolio_url:
        prof["portfolio_url"] = str(portfolio_url).strip()
    if proof_points and isinstance(proof_points, list):
        prof["proof_points"] = proof_points

    db.save_profile(prof, profile_id=profile_id)
    db.set_active_resume_profile(profile_id)

    curr_method = config.get_method()
    return {
        "status": "ok",
        "step": 3,
        "message_for_user": (
            f"Profile '{prof.get('_profile_name')}' confirmed and activated.\n"
            f"- Portfolio: {prof.get('portfolio_url') or 'Not provided'}\n"
            f"- Proof points: {len(prof.get('proof_points', []))} recorded\n"
            f"Next: select your job hunting method. Modern (outreach first) is default."
        ),
        "ask_user": (
            "Select your active job hunting method:\n"
            "1. Modern (Recommended): Outreach first, scan seed funding and fresh hiring posts, contact decision makers before the crowd.\n"
            "2. Classic: Traditional job boards, broad search, view filters, tailored resume & cover letter for the Apply button.\n"
            "(No answer defaults to Modern)"
        ),
        "options": {
            "choices": ["modern", "classic"],
            "recommended": "modern"
        },
        "next_tool": "jh_set_filters" if curr_method == "classic" else "jh_set_method",
        "data": {
            "active_profile": prof.get("_profile_name"),
            "target_roles": prof.get("target_roles", []),
            "portfolio_url": prof.get("portfolio_url", ""),
            "proof_points": prof.get("proof_points", []),
            "method": curr_method,
        }
    }


@_coaching_envelope
def jh_set_filters(filters: dict[str, Any], session_id: str = "default") -> dict[str, Any]:
    """Step 4: Set or update query-time view filters with clash detection and round-based checks."""
    if not isinstance(filters, dict):
        raise ToolError("filters must be a dictionary of criteria.")

    # Run clash detection
    clashes = check_filter_clashes(filters)

    # Check for triggered Round 2 questions
    wm = (filters.get("work_mode") or "any").lower().strip()
    visa = bool(filters.get("visa_need"))
    round_2_triggers = []

    if wm == "remote" and not filters.get("time_zone"):
        round_2_triggers.append({"id": "time_zone", "question": "For remote work, do you prefer specific time zones (US, Europe, APAC, or Any)?", "recommended": "any"})
    if wm in ("onsite", "hybrid") and "relocation" not in filters:
        round_2_triggers.append({"id": "relocation", "question": "Are you willing to relocate for this position?", "recommended": "no", "choices": ["no", "yes"]})
    if visa and not filters.get("visa_countries"):
        round_2_triggers.append({"id": "visa_countries", "question": "Which destination countries do you need visa sponsorship for?", "recommended": "United States"})

    saved = db.save_view_filters(filters, session_id=session_id)
    db.set_session_state("filters_set", last_tool="jh_set_filters")

    msg = "View filters saved successfully."
    if clashes:
        msg += f" Notice: {'; '.join(clashes)}"

    ask = None
    if round_2_triggers:
        ask = "Please answer the conditional Round 2 questions if applicable:"

    return {
        "status": "ok",
        "step": 4,
        "message_for_user": msg,
        "ask_user": ask,
        "options": {
            "round_2_questions": round_2_triggers if round_2_triggers else None,
            "recommended": "jh_search" if saved.get("job_style") else "jh_set_filters",
            "choices": ["jh_search", "jh_query", "jh_set_filters"]
        },
        "next_tool": "jh_search" if saved.get("job_style") else "jh_set_filters",
        "data": {
            "filters": saved,
            "clashes": clashes,
            "round_2_triggered": bool(round_2_triggers)
        }
    }


# ==============================================================================
# Phase B1 - B4 Tools (JobHunter V3 Start-Up Flow)
# ==============================================================================

@_coaching_envelope
def jh_begin(resume_path: str = "", resume_text: str = "", session_id: str = "default", track: str = "") -> dict[str, Any]:
    """Phase B1: Entry point for any job request. Runs resume check and job-name inference, saves profile, creates session, and replies with needs_resume, needs_role, or ready with ticket."""
    sess = ticket_manager.get_or_create_session(session_id)

    # Gate 5: calling jh_begin twice before answering returns same status and questions again
    if sess.get("last_status") in ("needs_resume", "needs_role") and not resume_path and not resume_text:
        return sess["last_reply"]

    # Local resume check (Phase B2 - no network)
    check_res = resume_checker.check_resume(
        resume_path or resume_text,
        saved_profile=db.get_profile(),
        resume_text=resume_text,
        filename=resume_path,
    )
    sess["check_result"] = check_res

    if not check_res["ok"]:
        reply = {
            "status": "needs_resume",
            "step": 1,
            "message_for_user": ticket_manager.build_stop_message(
                f"Resume Check Failed:\n" + "\n".join(f"- {issue}" for issue in check_res["issues"]) +
                "\n\nPlease provide a path to a valid PDF, DOCX, TXT, or MD resume, or paste the text directly."
            ),
            "ask_user": "Please provide a valid resume file (PDF, DOCX, TXT, MD) or paste your resume text.",
            "next_tool": "jh_begin",
            "data": {
                "issues": check_res["issues"],
                "text_chars": check_res["text_chars"],
            }
        }
        sess["last_status"] = "needs_resume"
        sess["last_reply"] = reply
        return reply

    prof = check_res["profile"]
    db.save_profile(prof, profile_id="master")
    db.set_active_resume_profile("master")

    filename = Path(resume_path).name if resume_path else "pasted_resume.txt"
    inf = role_inference.infer_roles(prof, filename)
    sess["profile"] = prof
    sess["inference_result"] = inf
    sess["resume_id"] = util.stable_id(prof.get("name") or "candidate", check_res.get("text_chars", 0))

    ask_role = (len(inf.get("role_focus", [])) == 0)
    step3_q = interview_questions.build_step_3_target_questions(
        inf["roles"], inf["region_guess"], ask_role=ask_role
    )
    sess["last_questions"] = step3_q
    sess["role_focus"] = inf.get("role_focus", [])

    warnings_lines = "\n".join(check_res["warnings"]) if check_res["warnings"] else ""
    header_parts = [inf.get("one_line_summary") or inf.get("profile_summary", "")]
    if warnings_lines:
        header_parts.append(warnings_lines)
    header_parts.append("")
    header_parts.append(step3_q["formatted_text"])
    header_text = "\n".join(header_parts)

    status_name = "needs_role" if ask_role else "needs_target"
    reply = {
        "status": status_name,
        "step": 2,
        "message_for_user": ticket_manager.build_stop_message(header_text),
        "ask_user": step3_q["formatted_text"],
        "options": step3_q,
        "next_tool": "jh_confirm",
        "data": {
            "name": check_res["name"],
            "one_line_summary": inf.get("one_line_summary", ""),
            "inferred_roles": inf["roles"],
            "role_focus": inf.get("role_focus", []),
            "job_type_guess": inf["job_type_guess"],
            "region_guess": inf["region_guess"],
            "warnings": check_res["warnings"],
            "profile_summary": inf["profile_summary"],
            "questions": step3_q["questions"],
        }
    }
    sess["last_status"] = status_name
    sess["last_reply"] = reply
    return reply


@_coaching_envelope
def jh_confirm(session_id: str = "default", answers: Optional[dict[str, Any]] = None, user_reply: str = "", track: str = "") -> dict[str, Any]:
    """Phase B1: Confirms target search questions (method, place, role) and issues 2-hour session ticket."""
    sess = ticket_manager.get_or_create_session(session_id)

    # Evaluate optional coaching trigger on user_reply
    coaching = None
    if user_reply:
        from . import coach
        coaching = coach.evaluate_coaching(user_reply, session_id=session_id)

    # Reject empty user_reply
    if not user_reply or not str(user_reply).strip():
        return {
            "status": "needs_input",
            "step": 2,
            "message_for_user": ticket_manager.build_stop_message(
                "Invalid input: user_reply is empty. Please provide the user's exact words to answer the target search questions."
            ),
            "ask_user": "Please answer the target search questions (Method, Target place, and Role).",
            "next_tool": "jh_confirm",
        }

    # Reject repetition of question
    clean_reply = str(user_reply).strip().lower()
    last_q = sess.get("last_questions") or {}
    last_q_text = (last_q.get("formatted_text") or "").lower()
    q_signatures = [
        "method: modern (default) or classic",
        "method: modern or classic",
        "target place: tunisia, remote worldwide",
        "target place: tunisia",
        "what target job title or role are you aiming for",
        "stop. ask the user the questions below",
    ]
    is_echo = (
        (last_q_text and clean_reply in last_q_text and len(clean_reply) > 20)
        or any(sig in clean_reply for sig in q_signatures)
        or (clean_reply.endswith("?") and not any(k in clean_reply for k in ["tunis", "france", "germany", "remote", "developer", "engineer", "designer"]))
    )
    if is_echo:
        return {
            "status": "needs_input",
            "step": 2,
            "message_for_user": ticket_manager.build_stop_message(
                "Invalid input: user_reply merely repeats the question. Please provide the user's actual answers."
            ),
            "ask_user": "Please answer the target search questions (Method, Target place, and Role).",
            "next_tool": "jh_confirm",
        }

    # Record verbatim words in session log
    ticket_manager.record_user_reply(session_id, user_reply)
    answers = answers or {}

    # 1. Parse Method (default Modern)
    if "classic" in clean_reply or answers.get("method") == "classic":
        chosen_method = "classic"
    elif "modern" in clean_reply or answers.get("method") == "modern":
        chosen_method = "modern"
    else:
        chosen_method = "modern"

    config.set_method(chosen_method)
    db.set_session_state(f"method_{chosen_method}")

    # 2. Parse Target Place
    inf = sess.get("inference_result") or {}
    resume_country = (inf.get("region_guess", {}).get("value") or "").strip()
    if not resume_country or resume_country.lower() in ("any", "unknown", ""):
        resume_country = "Tunisia"

    if ticket_manager.is_explicit_skip(clean_reply) and not any(k in clean_reply for k in ["tunis", "remote", "france", "germany", "us"]):
        chosen_place = resume_country
    elif answers.get("target_place") or answers.get("location"):
        chosen_place = str(answers.get("target_place") or answers.get("location")).strip()
    else:
        if "tunis" in clean_reply or "tunisia" in clean_reply or "tunisie" in clean_reply:
            chosen_place = "Tunisia"
        elif "remote worldwide" in clean_reply or "worldwide" in clean_reply or "global remote" in clean_reply:
            chosen_place = "remote worldwide"
        elif "remote" in clean_reply:
            chosen_place = "remote"
        elif "france" in clean_reply:
            chosen_place = "France"
        elif "germany" in clean_reply or "deutschland" in clean_reply:
            chosen_place = "Germany"
        elif "uk" in clean_reply or "united kingdom" in clean_reply:
            chosen_place = "United Kingdom"
        elif "us" in clean_reply or "united states" in clean_reply or "usa" in clean_reply:
            chosen_place = "United States"
        elif "abroad" in clean_reply:
            chosen_place = "abroad"
        else:
            chosen_place = resume_country

    # 3. Parse Target Role
    if answers.get("target_role") or answers.get("role"):
        role_focus = [str(answers.get("target_role") or answers.get("role")).strip()]
    elif ticket_manager.is_explicit_skip(clean_reply):
        role_focus = sess.get("role_focus") or [r["role"] for r in inf.get("roles", [])[:1]] or ["Software Engineer"]
    else:
        import re
        m = re.search(r"(?:role(?:\s*is|:)?|target(?:\s*role)?(?:\s*is|:)?|i want|aiming for)\s+([a-zA-Z\s\/\+\#]+?)(?:in|using|with|method|$|,)", user_reply, re.I)
        if m and len(m.group(1).strip().split()) <= 4:
            role_focus = [m.group(1).strip()]
        else:
            role_focus = sess.get("role_focus") or [r["role"] for r in inf.get("roles", [])[:1]] or ["Software Engineer"]

    db.save_view_filters({
        "locations": [chosen_place],
        "job_style": role_focus[0],
        "roles": role_focus,
        "method": chosen_method,
    }, session_id=session_id)
    sess["role_focus"] = role_focus
    sess["target_place"] = chosen_place
    sess["method"] = chosen_method

    resume_id = sess.get("resume_id") or "master"
    ticket = ticket_manager.generate_ticket(
        session_id=session_id,
        resume_id=resume_id,
        roles=role_focus,
        method=chosen_method,
        location=chosen_place,
    )

    subagent_brief = (
        f"You are the JobHunter runner. Call jh_launch with session_id '{session_id}' and ticket '{ticket}'. "
        f"Then report one line: ui_url, server_status, search status. "
        f"Use only JobHunter MCP tools. Write no files. Use no terminal. List no jobs."
    )

    msg = (
        f"Target search configured: Method={chosen_method.capitalize()}, Target Place={chosen_place}, Role={', '.join(role_focus)}.\n"
        f"Ticket issued. Ready to launch. Call jh_launch with ticket '{ticket}', or dispatch a subagent with subagent_brief."
    )

    reply = {
        "status": "ready",
        "step": 3,
        "ticket": ticket,
        "subagent_brief": subagent_brief,
        "message_for_user": msg,
        "ask_user": None,
        "next_tool": "jh_launch",
        "data": {
            "method": chosen_method,
            "target_place": chosen_place,
            "role_focus": role_focus,
            "ticket": ticket,
            "subagent_brief": subagent_brief,
        }
    }
    sess["last_status"] = "ready"
    sess["last_reply"] = reply
    return reply


@_coaching_envelope
def jh_launch(session_id: str = "default", ticket: str = "") -> dict[str, Any]:
    """Phase B4: Detached launch of HTTP daemon, background search, and browser in under 3 seconds."""
    sess = ticket_manager.get_or_create_session(session_id)

    # Gate 1: Reject without ticket
    valid, err = ticket_manager.validate_ticket(session_id, ticket)
    if not valid:
        return {
            "status": "needs_input",
            "step": 1,
            "message_for_user": ticket_manager.build_stop_message(
                f"Gate blocked: {err}\nYou must run jh_begin and obtain a ticket before calling jh_launch."
            ),
            "ask_user": "Please provide your resume path or text to start the JobHunter process.",
            "next_tool": "jh_begin",
            "data": {"error": err},
        }

    ticket_manager.mark_ticket_launched(ticket)

    # 1. Start server.py detached if down
    server_res = worker_launcher.start_detached_server(preferred_port=8080)
    port = server_res["port"]
    ui_url = f"http://127.0.0.1:{port}/?session={session_id}"
    sess["worker_port"] = port
    sess["ui_url"] = ui_url

    # 2. Start search as background job (idempotent reuse within session)
    query = ", ".join(sess.get("role_focus", ["Software Engineer"]))
    target_loc = sess.get("target_place") or sess.get("location") or ""
    if not target_loc:
        inf = sess.get("inference_result", {})
        region_guess = inf.get("region_guess", {}).get("value", "")
        target_loc = region_guess if region_guess != "Any" else ""

    if sess.get("search_job_id"):
        search_job_id = sess["search_job_id"]
        search_status = "already_running"
    else:
        search_res = worker_launcher.start_background_search(
            session_id=session_id,
            query=query,
            location=target_loc,
            role_focus=sess.get("role_focus", []),
        )
        search_job_id = search_res["search_job_id"]
        sess["search_job_id"] = search_job_id
        search_status = "started"

    # 3. Open Chromium with autofill extension
    from . import extension_installer
    ext_dir = extension_installer.find_extension_dir()
    browser_opened = worker_launcher.open_browser(ui_url)
    ext_status = "loaded" if browser_opened else "manual_load_ready"

    # Build Round 2 questions
    r2 = interview_questions.build_round_2_questions(
        sess.get("profile", {}),
        sess.get("inference_result", {}).get("job_type_guess", {}),
        sess.get("inference_result", {}).get("region_guess", {}),
    )
    sess["round_2_questions"] = r2

    msg = (
        f"JobHunter launched successfully in background.\n"
        f"- Web UI: {ui_url}\n"
        f"- Search Job ID: {search_job_id}\n"
        f"- Server Status: {server_res['status']} (port {port})\n"
        f"- Extension Status: {ext_status} ({ext_dir})\n\n"
        f"INSTRUCTION FOR AI: Tell the user that the search is running and the web UI is open. "
        f"Do not list jobs in chat; results are displayed live in the web UI. "
        f"Then ask the Round 2 questions below. Call jh_status at most once and NEVER poll in a loop.\n\n"
        f"While search runs, please answer these preferences to filter results live in the UI:\n"
        f"{r2['formatted_text']}"
    )

    return {
        "status": "ok",
        "step": 4,
        "server_status": server_res["status"],
        "ui_url": ui_url,
        "extension_status": ext_status,
        "search_status": search_status,
        "search_job_id": search_job_id,
        "message_for_user": msg,
        "ask_user": r2["formatted_text"],
        "options": r2,
        "next_tool": "jh_answer",
        "data": {
            "ui_url": ui_url,
            "port": port,
            "search_job_id": search_job_id,
            "server_status": server_res["status"],
            "extension_status": ext_status,
            "extension_dir": ext_dir,
            "browser_opened": True,
            "round_2_questions": r2["questions"],
        }
    }


@_coaching_envelope
def jh_answer(session_id: str = "default", answers: Optional[dict[str, Any]] = None, user_reply: str = "", track: str = "") -> dict[str, Any]:
    """Phase B1 & B5: Updates view filters live at query time without restarting the background search."""
    sess = ticket_manager.get_or_create_session(session_id)
    answers = answers or {}
    if track:
        answers["track"] = track

    # Evaluate optional coaching trigger on user_reply
    coaching = None
    if user_reply:
        from . import coach
        coaching = coach.evaluate_coaching(user_reply, session_id=session_id)

    if user_reply and ticket_manager.is_explicit_skip(user_reply):
        ticket_manager.record_user_skip(session_id, "round_2", user_reply)
        for field in ["job_type", "work_mode", "visa", "pay", "company_type", "location"]:
            if field not in sess["answers"]:
                sess["answers"][field] = "any"
    else:
        if user_reply:
            sess["user_reply_log"] = sess.get("user_reply_log", []) + [user_reply]
            clean_reply = user_reply.lower()
            if "intern" in clean_reply or "pfe" in clean_reply or "stage" in clean_reply:
                answers["job_type"] = "internship (PFE)"
            elif "full" in clean_reply or "junior" in clean_reply:
                answers["job_type"] = "full-time"
            if "remote" in clean_reply:
                answers["work_mode"] = "remote"
            elif "hybrid" in clean_reply:
                answers["work_mode"] = "hybrid"
            elif "onsite" in clean_reply or "on-site" in clean_reply:
                answers["work_mode"] = "onsite"
            if "tunisia" in clean_reply or "tunis" in clean_reply:
                answers["locations"] = ["Tunisia"]
            elif "remote worldwide" in clean_reply or "worldwide" in clean_reply:
                answers["locations"] = ["worldwide"]

        sess["answers"].update(answers)

    # Persist answers into view filters
    db.save_view_filters(sess["answers"], session_id=session_id)

    # Re-evaluate SQL query filters
    q_res = db.query_jobs(session_id=session_id)

    port_info = worker_launcher.get_running_server_info()
    port = port_info["port"] if port_info else (sess.get("worker_port") or 8080)
    ui_url = f"http://127.0.0.1:{port}/?session={session_id}"

    hidden_count = max(0, q_res.get("total_active_pool", q_res["count"]) - q_res["count"])

    return {
        "status": "ok",
        "step": 5,
        "message_for_user": (
            f"Filters updated live. {q_res['count']} jobs match your preferences ({hidden_count} hidden by your filters). "
            f"The web UI at {ui_url} shows the matches live. Chat remains clean."
        ),
        "ask_user": None,
        "next_tool": "jh_status",
        "data": {
            "matches": q_res["count"],
            "matches_count": q_res["count"],
            "hidden_by_filters": hidden_count,
            "filters_applied": sess["answers"],
            "ui_url": ui_url,
        },
        "coaching": coaching,
    }


@_coaching_envelope
def jh_replace_resume(session_id: str = "default", resume_path: str = "", resume_text: str = "") -> dict[str, Any]:
    """Phase B1 & B2: Runs resume check on new file, re-parses it, re-scores stored jobs, and keeps worker and search running."""
    sess = ticket_manager.get_or_create_session(session_id)
    check_res = resume_checker.check_resume(
        resume_path or resume_text,
        saved_profile=db.get_profile(),
        resume_text=resume_text,
        filename=resume_path,
    )
    if not check_res["ok"]:
        return {
            "status": "needs_resume",
            "step": 1,
            "message_for_user": ticket_manager.build_stop_message(
                f"Resume Check Failed:\n" + "\n".join(f"- {issue}" for issue in check_res["issues"]) +
                "\n\nPlease provide a path to a valid PDF, DOCX, TXT, or MD resume, or paste the text directly."
            ),
            "ask_user": "Please provide a valid resume file (PDF, DOCX, TXT, MD) or paste your resume text.",
            "next_tool": "jh_replace_resume",
            "data": {"issues": check_res["issues"]},
        }

    prof = check_res["profile"]
    db.save_profile(prof, profile_id="master")
    db.set_active_resume_profile("master")

    filename = Path(resume_path).name if resume_path else "pasted_resume.txt"
    inf = role_inference.infer_roles(prof, filename)
    sess["profile"] = prof
    sess["role_focus"] = inf["role_focus"]
    sess["inference_result"] = inf

    # Re-score stored jobs against the new profile
    with db.session() as c:
        rows = c.execute("SELECT id, job_json FROM jobs").fetchall()
        for r in rows:
            try:
                j = json.loads(r["job_json"])
                match_res = scoring.score_job_best(j, prof)
                new_score = match_res.get("score", 0)
                j["score"] = new_score
                j["score_breakdown"] = match_res
                c.execute("UPDATE jobs SET score=?, job_json=? WHERE id=?", (new_score, json.dumps(j), r["id"]))
            except Exception:
                pass

    return {
        "status": "ready",
        "step": 3,
        "message_for_user": (
            f"Resume updated and re-scored successfully for {check_res['name']}.\n"
            f"{inf['profile_summary']}\n"
            f"Worker and background search continue running without restart."
        ),
        "ask_user": None,
        "next_tool": "jh_status",
        "data": {
            "name": check_res["name"],
            "role_focus": inf["role_focus"],
            "profile_summary": inf["profile_summary"],
        }
    }


@_coaching_envelope
def jh_stop(session_id: str = "default") -> dict[str, Any]:
    """Phase B1: Stops the background worker and search job for a session."""
    worker_launcher.stop_worker(session_id)
    return {
        "status": "ok",
        "step": "stopped",
        "message_for_user": f"Worker and search stopped for session '{session_id}'.",
        "ask_user": None,
        "next_tool": "jh_begin",
        "data": {"session_id": session_id, "stopped": True},
    }


@_coaching_envelope
def jh_install_agent(client: str = "claude", confirmed: bool = False) -> dict[str, Any]:
    """Phase B6: Installs jobhunter-runner subagent definition into user config directory."""
    clean_client = client.lower().strip()
    if clean_client not in ("claude", "cursor", "antigravity"):
        clean_client = "claude"

    home_dir = Path.home()
    if clean_client == "claude":
        target_dir = home_dir / ".claude" / "agents"
        target_file = target_dir / "jobhunter-runner.md"
    elif clean_client == "cursor":
        target_dir = home_dir / ".cursor" / "agents"
        target_file = target_dir / "jobhunter-runner.md"
    else:
        target_dir = home_dir / ".antigravity" / "agents"
        target_file = target_dir / "jobhunter-runner.md"

    if not confirmed:
        return {
            "status": "needs_input",
            "message_for_user": (
                f"Would you like to install the JobHunter background runner subagent definition for '{clean_client}'?\n"
                f"Target file: {target_file}\n"
                f"This file will be written ONLY to your user profile directory, never to the workspace repo."
            ),
            "ask_user": f"Confirm installation to {target_file}? (yes/no)",
            "next_tool": "jh_install_agent",
            "data": {
                "client": clean_client,
                "target_file": str(target_file),
                "confirmed": False,
            }
        }

    template_file = Path(__file__).resolve().parent.parent / "agents" / "jobhunter-runner.md"
    if template_file.exists():
        content = template_file.read_text(encoding="utf-8")
    else:
        content = (
            "---\n"
            "name: jobhunter-runner\n"
            "description: Detached background runner for JobHunter search execution\n"
            "---\n"
            "You are the JobHunter detached runner. Execute jh_launch with the ticket and report status.\n"
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content, encoding="utf-8")

    return {
        "status": "ok",
        "message_for_user": f"Subagent installed successfully at {target_file}.",
        "ask_user": None,
        "next_tool": "jh_begin",
        "data": {
            "client": clean_client,
            "target_file": str(target_file),
            "installed": True,
        }
    }


# ==============================================================================
# Search & Query Tools (with Ticket Gating & Backward Compatibility)
# ==============================================================================

@_coaching_envelope
def jh_search(
    job_style: str = "",
    region: str = "",
    force_refresh: bool = False,
    session_id: str = "default",
    ticket: str = "",
    **kwargs,
) -> dict[str, Any]:
    """Step 5 & 6: Search tool with Gate 1 ticket enforcement.
    Rejects calls without a valid ticket when a ticket or session is provided.
    Runs broad search across sources and stores results in DB.
    """
    # Ticket gate enforcement for V3 flows
    if ticket or session_id != "default":
        valid, err = ticket_manager.validate_ticket(session_id, ticket)
        if not valid:
            return {
                "status": "needs_input",
                "step": 1,
                "message_for_user": ticket_manager.build_stop_message(
                    f"Gate blocked: {err}\nYou must run jh_begin and obtain a ticket before calling jh_search."
                ),
                "ask_user": "Please provide your resume path or text to start the JobHunter process.",
                "next_tool": "jh_begin",
                "data": {"error": err},
            }

    style = (job_style or "").strip()
    if not style:
        vf = db.get_view_filters(session_id)
        if vf.get("job_style"):
            style = vf["job_style"]

    # Blocked gate: search requires a job style
    if not style:
        return {
            "status": "needs_input",
            "step": 4,
            "message_for_user": "A job style is required to start a broad search (e.g. 'tech jobs', 'software engineer', 'data science').",
            "ask_user": "What job style would you like to search for?",
            "options": {
                "choices": ["tech jobs", "software engineering", "data science", "product management"],
                "recommended": "tech jobs"
            },
            "next_tool": "jh_search"
        }

    # Persist job style into view filters
    db.save_view_filters({"job_style": style}, session_id=session_id)
    db.set_session_state("searching", last_tool="jh_search")

    # Run broad search across scrapers without dropping records
    search_res = pipeline.search(query=style, location=region or "", force_refresh=force_refresh)
    jobs = search_res.get("jobs", []) if isinstance(search_res, dict) else search_res

    # Store with lifecycle deduplication
    store_stats = db.store_jobs(jobs, query=style, location=region)

    # Query view filters in SQL
    view_res = db.query_jobs(session_id=session_id)
    usable_gate = view_res["usable_gate"]

    next_tool = "jh_open_ui" if usable_gate["usable"] else ("jh_set_filters" if usable_gate["status"] == "too_few" else "jh_query")

    return {
        "status": "ok",
        "step": 7,
        "message_for_user": (
            f"Broad search for '{style}' completed. Ingested {store_stats['total']} postings "
            f"({store_stats['inserted']} new, {store_stats['merged']} merged). "
            f"{view_res['count']} jobs match your view filters. {usable_gate['message']}"
        ),
        "ask_user": usable_gate["suggestion"] if not usable_gate["usable"] else None,
        "options": {
            "choices": usable_gate["actions"],
            "recommended": usable_gate["actions"][0] if usable_gate["actions"] else "open_ui"
        },
        "next_tool": next_tool,
        "data": {
            "matches_count": view_res["count"],
            "total_active_pool": view_res["total_active_pool"],
            "removed_counts": view_res["removed_counts"],
            "closing_soon_count": view_res["closing_soon_count"],
            "usable_gate": usable_gate,
            "jobs_preview": view_res["jobs"][:10],
        }
    }


@_coaching_envelope
def jh_query(filters: Optional[dict[str, Any]] = None, session_id: str = "default", track: str = "") -> dict[str, Any]:
    """Step 7: Query stored jobs using view filters without re-scraping. Hard filters hide, soft preferences rank, expired jobs returned in closing_soon."""
    if track:
        filters = dict(filters or {})
        filters["track"] = track
    q_res = db.query_jobs(view_filters=filters, session_id=session_id)
    usable_gate = q_res["usable_gate"]
    next_tool = "jh_open_ui" if usable_gate["usable"] else "jh_set_filters"

    return {
        "status": "ok",
        "step": 7,
        "message_for_user": f"Filter query returned {q_res['count']} matching opportunities ({q_res['closing_soon_count']} closing soon). {usable_gate['message']}",
        "ask_user": usable_gate["suggestion"] if not usable_gate["usable"] else None,
        "options": {
            "choices": ["open_ui", "edit_filters", "refresh"],
            "recommended": "open_ui" if usable_gate["usable"] else "edit_filters"
        },
        "next_tool": next_tool,
        "data": {
            "count": q_res["count"],
            "total_active_pool": q_res["total_active_pool"],
            "removed_counts": q_res["removed_counts"],
            "closing_soon_count": q_res["closing_soon_count"],
            "usable_gate": usable_gate,
            "jobs": q_res["jobs"][:25],
            "closing_soon": q_res["closing_soon"][:5],
        }
    }


@_coaching_envelope
def jh_refresh(source: str = "", force: bool = False) -> dict[str, Any]:
    """Background lane: Trigger on-demand refresh for non-Radar sources respecting TTL and forced cooldown."""
    from . import refresh_scheduler
    res = refresh_scheduler.run_refresh(source=source or None, force=force)
    return {
        "status": "ok",
        "step": "refresh",
        "message_for_user": res.get("message", "Refresh complete."),
        "ask_user": None,
        "options": {
            "choices": ["jh_query", "jh_status"],
            "recommended": "jh_query"
        },
        "next_tool": "jh_query",
        "data": res
    }


def _check_health(host: str, port: int, timeout: float = 0.5) -> bool:
    import http.client
    conn = None
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        return resp.status == 200
    except Exception:
        return False
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@_coaching_envelope
def jh_open_ui(port: int = 8765, host: str = "127.0.0.1") -> dict[str, Any]:
    """Step 8: Start the web UI server if down, verify health endpoint, find next free port if occupied, start LinkedIn Radar worker, and open browser."""
    from . import httpd
    ws = home.get_home()

    target_port = port
    url = f"http://{host}:{target_port}"
    server_ready = _check_health(host, target_port, timeout=0.5)

    if not server_ready:
        if _is_port_in_use(target_port, host):
            target_port = _find_free_port(target_port + 1, host)
            url = f"http://{host}:{target_port}"

        try:
            httpd.start_server(host=host, port=target_port, ws_dir=ws)
        except Exception as e:
            log.warning("HTTP daemon start failed: %s", e)

        deadline = time.time() + 15.0
        while time.time() < deadline:
            if _check_health(host, target_port, timeout=1.0):
                server_ready = True
                break
            time.sleep(0.3)

    from . import radar
    radar.start_radar_worker()

    browser_opened = False
    try:
        browser_opened = webbrowser.open(url)
    except Exception as e:
        log.warning("webbrowser.open failed: %s", e)

    msg = f"Web UI is running at {url}."
    if browser_opened:
        msg += " Opened in your default browser."
    else:
        msg += f" Please open {url} in your browser."

    return {
        "status": "ok",
        "step": 8,
        "message_for_user": msg,
        "ask_user": None,
        "options": {
            "choices": ["jh_status", "jh_query"],
            "recommended": "jh_status"
        },
        "next_tool": "jh_status",
        "data": {
            "url": url,
            "port": target_port,
            "server_ready": server_ready,
            "browser_opened": browser_opened,
            "radar_status": db.get_radar_state().get("status"),
        }
    }


@_coaching_envelope
def jh_status(session_id: str = "default") -> dict[str, Any]:
    """Inspect full JobHunter state: active method, workspace path, session state, radar, refresh states, cleanup status, and top 5 matches."""
    home_dir = home.get_home()
    session_state = db.get_session_state()
    radar = db.get_radar_state()
    refresh = db.get_refresh_states()
    cleanup = db.get_cleanup_status()
    profile = db.get_profile()
    filters = db.get_view_filters(session_id)
    active_method = config.get_method()

    with db.session() as c:
        total_jobs = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        active_jobs = c.execute("SELECT COUNT(*) FROM jobs WHERE freshness_state='active'").fetchone()[0]
        dismissals_count = c.execute("SELECT COUNT(*) FROM dismissals").fetchone()[0]
        signals_count = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        fresh_signals = c.execute("SELECT COUNT(*) FROM signals WHERE status='fresh'").fetchone()[0]
        contacts_count = c.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        outreach_count = c.execute("SELECT COUNT(*) FROM outreach").fetchone()[0]

    daily_cap = config.get_daily_cap()
    today_sent = db.get_outreach_today_count()
    remaining_cap = max(0, daily_cap - today_sent)

    # Compute query-time matches for V3
    q_res = db.query_jobs(session_id=session_id)
    matches_count = q_res.get("count", 0)
    top_5 = q_res.get("jobs", [])[:5]
    hidden_count = max(0, q_res.get("total_active_pool", matches_count) - matches_count)

    port_info = worker_launcher.get_running_server_info()
    port = port_info["port"] if port_info else 8080
    ui_url = f"http://127.0.0.1:{port}/?session={session_id}"

    questions_waiting = 0
    curr_state_str = session_state.get("current_state", "") if isinstance(session_state, dict) else str(session_state)
    if curr_state_str in ("round_2_pending", "round_1_done", "ready"):
        questions_waiting = 6
    if curr_state_str in ("round_2_answered", "round_2_skipped"):
        questions_waiting = 0

    if active_method == "modern":
        method_summary = (
            f"- Method: Modern (Outreach First)\n"
            f"- Signals: {signals_count} stored ({fresh_signals} fresh)\n"
            f"- Contacts Found: {contacts_count}\n"
            f"- Outreach Today: {today_sent} / {daily_cap} sent ({remaining_cap} remaining)\n"
            f"- Send Mode: {config.get_send_mode()} | Follow-up: {config.get_follow_up_days()}d"
        )
    else:
        method_summary = (
            f"- Method: Classic (Job Boards & Apply)\n"
            f"- Stored Jobs: {total_jobs} ({active_jobs} active)\n"
            f"- Matches for Session: {matches_count} ({hidden_count} hidden by filters)\n"
            f"- LinkedIn Radar: {radar.get('status')} (Interval: {radar.get('interval_seconds')}s)\n"
            f"- Dismissals: {dismissals_count}\n"
            f"- Cleanup Grace: {cleanup.get('grace_hours')}h"
        )

    msg = (
        f"JobHunter Status:\n"
        f"- Workspace: {home_dir}\n"
        f"{method_summary}\n"
        f"- Active Profile: {profile.get('_profile_name')} ({profile.get('target_title') or 'Candidate'})\n"
        f"- Web UI: {ui_url}"
    )

    return {
        "status": "ok",
        "step": "status",
        "message_for_user": msg,
        "ask_user": None,
        "options": {
            "choices": ["jh_start", "jh_set_method", "jh_open_ui"],
            "recommended": "jh_start"
        },
        "next_tool": "jh_search" if active_method == "classic" else "jh_start",
        "data": {
            "method": active_method,
            "session_id": session_id,
            "matches": matches_count,
            "top_5_matches": top_5,
            "hidden_by_filters": hidden_count,
            "ui_url": ui_url,
            "total_jobs": total_jobs,
            "active_jobs": active_jobs,
            "workspace_home": str(home_dir),
            "session_state": session_state,
            "radar_state": radar,
            "refresh_states": refresh,
            "cleanup_status": cleanup,
            "active_profile": profile.get("_profile_name"),
            "view_filters": filters,
            "questions_waiting_count": questions_waiting,
            "signals_count": signals_count,
            "fresh_signals": fresh_signals,
            "contacts_count": contacts_count,
            "outreach_count": outreach_count,
            "today_sent": today_sent,
            "remaining_cap": remaining_cap,
        }
    }


@_coaching_envelope
def jh_feedback(
    job_id: str = "",
    action: str = "dismiss",
    reason: str = "",
    exclude_company: str = "",
    exclude_keyword: str = "",
    session_id: str = "default",
) -> dict[str, Any]:
    """Step 10: Record user feedback (dismissal, reasons, exclusions) with automatic tuning suggestion after 5 dismissals."""
    filters = db.get_view_filters(session_id)
    dismissal_note = ""
    tuning_suggestion = None

    if action == "dismiss" and job_id:
        db.add_dismissal(job_id, reason or "Dismissed by user")
        dismissal_count = db.count_dismissals()
        dismissal_note = f"Job '{job_id}' dismissed."
        if dismissal_count >= 5 and dismissal_count % 5 == 0:
            tuning_suggestion = (
                f"You have dismissed {dismissal_count} jobs. Would you like to refine your view filters "
                f"by excluding companies or keywords that frequently appear in dismissed roles?"
            )

    updated_filters = False
    if exclude_company:
        cos = list(filters.get("excluded_companies") or [])
        if exclude_company not in cos:
            cos.append(exclude_company)
            filters["excluded_companies"] = cos
            updated_filters = True

    if exclude_keyword:
        kws = list(filters.get("excluded_keywords") or [])
        if exclude_keyword not in kws:
            kws.append(exclude_keyword)
            filters["excluded_keywords"] = kws
            updated_filters = True

    if updated_filters:
        db.save_view_filters(filters, session_id=session_id)

    msg = dismissal_note or "Feedback processed."
    if tuning_suggestion:
        msg += f" {tuning_suggestion}"

    return {
        "status": "ok",
        "step": 10,
        "message_for_user": msg,
        "ask_user": tuning_suggestion,
        "options": {
            "choices": ["jh_query", "jh_set_filters"],
            "recommended": "jh_query"
        },
        "next_tool": "jh_query",
        "data": {
            "job_id": job_id,
            "action": action,
            "reason": reason,
            "tuning_suggestion": tuning_suggestion,
            "excluded_companies": filters.get("excluded_companies", []),
            "excluded_keywords": filters.get("excluded_keywords", []),
        }
    }


@_coaching_envelope
def jh_find_contacts(signal_id_or_company: str, target_role: str = "") -> dict[str, Any]:
    """Modern Step 12: Find up to 3 decision makers (Found, Pattern, Guess) or alternative routes for outreach."""
    from . import contacts
    return contacts.jh_find_contacts(signal_id_or_company, target_role=target_role)


@_coaching_envelope
def jh_build_resume(company: str, role: str, signal_id: str = "") -> dict[str, Any]:
    """Modern Step 13: Build or retrieve single grounded 1-page PDF resume <= 200 KB in jobmcp/outputs/."""
    from . import email_drafter
    return email_drafter.jh_build_resume(company=company, role=role, signal_id=signal_id)


@_coaching_envelope
def jh_draft_email(contact_id: str, signal_id: str = "", resume_path: str = "") -> dict[str, Any]:
    """Modern Step 13: Draft human 3-4 line outreach email with slop linting and attachment policy."""
    from . import email_drafter
    return email_drafter.jh_draft_email(contact_id=contact_id, signal_id=signal_id, resume_path=resume_path)
