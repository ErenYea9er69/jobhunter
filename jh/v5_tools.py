"""V5 MCP Tools: Guided interview flow, broad search, narrow view, and workspace isolation.

Updated for JobHunter V3: ticket gating, detached background worker, 
and live query-time filtering while maintaining 100% backward compatibility.
"""
from __future__ import annotations

import json
import logging
import os
import re
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
    sess = ticket_manager.get_or_create_session(session_id)
    sess["method"] = clean
    db.store_answer(session_id, "method", clean, user_reply=f"method set to {clean}")
    db.set_session_state(f"method_{clean}", last_tool="jh_set_method")
    if clean == "modern":
        from . import radar
        radar.start_radar_worker()
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
    ticket_manager.transition_session_state(profile_id, ticket_manager.SessionState.ANSWERED)
    ticket_manager.transition_session_state("default", ticket_manager.SessionState.ANSWERED)

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
def jh_set_filters(filters: dict[str, Any], session_id: str = "default", user_reply: str = "") -> dict[str, Any]:
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

    # Defect D2 gate: Preferences and filters may be written ONLY through jh_confirm or jh_answer with user words in user_reply
    if not user_reply:
        return {
            "status": "needs_input",
            "step": 4,
            "message_for_user": ticket_manager.build_stop_message(
                "Preferences and filters may be written only through jh_confirm or jh_answer, and only with user words in user_reply."
            ),
            "ask_user": "Please provide your answers in user_reply via jh_answer.",
            "next_tool": "jh_answer",
            "options": {
                "round_2_questions": round_2_triggers if round_2_triggers else None,
                "recommended": "jh_answer",
                "choices": ["jh_answer"],
            },
            "data": {
                "error": "direct_filter_write_prohibited",
                "clashes": clashes,
                "round_2_triggered": bool(round_2_triggers),
            },
        }

    valid, err = ticket_manager.validate_user_reply(session_id, user_reply)
    if not valid:
        return {
            "status": "needs_input",
            "step": 4,
            "message_for_user": ticket_manager.build_stop_message(
                f"Invalid input: {err}\nPreferences and filters may be written only through jh_confirm or jh_answer, and only with user words in user_reply."
            ),
            "ask_user": "Please provide your answers via jh_answer.",
            "next_tool": "jh_answer",
            "data": {"error": err},
        }

    return jh_answer(session_id=session_id, answers=filters, user_reply=user_reply)


# ==============================================================================
# Phase B1 - B4 Tools (JobHunter V3 Start-Up Flow)
# ==============================================================================

@_coaching_envelope
def jh_begin(resume_path: str = "", resume_text: str = "", session_id: str = "default", track: str = "") -> dict[str, Any]:
    """Phase B1: Entry point for any job request. Runs resume check and job-name inference, saves profile, creates session, and replies with needs_resume, needs_role, or ready with ticket."""
    sess = ticket_manager.get_or_create_session(session_id)

    # Multi-resume check: attached together OR multiple resume files sitting in workspace/resumes/
    resume_str = str(resume_path) if resume_path else ""
    if resume_str and any(sep in resume_str for sep in [";", "\n", " and "]):
        parts = [p.strip() for p in re.split(r"[;\n]| and ", resume_str) if p.strip()]
        if len(parts) > 1:
            names = [Path(p).name for p in parts]
            reply = {
                "status": "multiple_resumes",
                "session_id": session_id,
                "step": 1,
                "message_for_user": (
                    f"Multiple resumes provided ({', '.join(names)}). "
                    f"Which resume would you like to use for this search ({' or '.join(names)}), or would you like to search for both?"
                ),
                "ask_user": f"Which resume should I use ({', '.join(names)}), or should I search for both?",
                "options": {
                    "choices": names + ["both"],
                    "recommended": names[0],
                },
                "next_tool": "jh_begin",
                "data": {"resume_candidates": parts}
            }
            sess["last_status"] = "multiple_resumes"
            sess["last_reply"] = reply
            return reply

    if not resume_str.strip() and not str(resume_text or "").strip():
        ws_root = Path(config.WORKSPACE_DIR) if config.WORKSPACE_DIR else None
        if ws_root and ws_root.is_dir():
            _NON_RESUME_NAMES = {
                "readme.md", "readme.txt", "changelog.md", "agents.md", "license", "license.txt",
                "license.md", "product.md", "design.md", "structure_map.md", "ui-changes.md",
                "put_your_resume_here.txt", "requirements.txt", "requirements-dev.txt",
            }
            scan_dirs = [ws_root]
            if (ws_root / "resumes").is_dir():
                scan_dirs.append(ws_root / "resumes")
            candidates: list[Path] = []
            seen_resolved: set[str] = set()
            for d in scan_dirs:
                try:
                    for item in sorted(d.iterdir()):
                        if not item.is_file():
                            continue
                        if item.suffix.lower() not in (".pdf", ".docx", ".txt", ".md"):
                            continue
                        if item.name.lower() in _NON_RESUME_NAMES or item.name.startswith("."):
                            continue
                        if item.stat().st_size < 100:
                            continue
                        rp = str(item.resolve())
                        if rp not in seen_resolved:
                            seen_resolved.add(rp)
                            candidates.append(item)
                except OSError:
                    continue
            if len(candidates) >= 2:
                cand_paths = [str(c) for c in candidates]
                names = [c.name for c in candidates]
                reply = {
                    "status": "multiple_resumes",
                    "session_id": session_id,
                    "step": 1,
                    "message_for_user": (
                        f"I found {len(names)} resumes in your workspace ({', '.join(names)}). "
                        f"Which resume would you like to use ({' or '.join(names)})?"
                    ),
                    "ask_user": f"Which resume should I use ({', '.join(names)})?",
                    "options": {
                        "choices": names,
                        "recommended": names[0],
                    },
                    "next_tool": "jh_begin",
                    "data": {"resume_candidates": cand_paths},
                }
                sess["last_status"] = "multiple_resumes"
                sess["last_reply"] = reply
                return reply

    # Central home directory setup & first reply notice
    home.ensure_home_dirs()
    notice = home.get_first_reply_notice()

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
        stop_body = (
            f"Resume Check Failed:\n" + "\n".join(f"- {issue}" for issue in check_res["issues"]) +
            "\n\nPlease provide a path to a valid PDF, DOCX, TXT, or MD resume, or paste the text directly."
        )
        if notice:
            stop_body = f"{notice}\n\n{stop_body}"
        reply = {
            "status": "needs_resume",
            "session_id": session_id,
            "step": 1,
            "notice": notice,
            "message_for_user": ticket_manager.build_stop_message(stop_body),
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
    new_resume_id = util.stable_id(prof.get("name") or "candidate", check_res.get("text_chars", 0))
    prev_resume_id = db.get_setting("active_resume_id", "")
    # Clear stale unsaved cache when switching to a different candidate OR upgrading a dirty legacy DB
    should_reset_cache = False
    if prev_resume_id and prev_resume_id != new_resume_id:
        should_reset_cache = True
    elif not prev_resume_id:
        with db.session() as c:
            has_stale_jobs = c.execute("SELECT COUNT(*) FROM jobs WHERE COALESCE(saved_by, '') != 'ui'").fetchone()[0] > 0
            has_stale_sigs = c.execute("SELECT COUNT(*) FROM signals WHERE COALESCE(status, '') != 'saved'").fetchone()[0] > 0
            has_stale_filters = c.execute("SELECT COUNT(*) FROM view_filters").fetchone()[0] > 0
            if (has_stale_jobs or has_stale_sigs) and has_stale_filters:
                should_reset_cache = True
    if should_reset_cache:
        db.reset_stale_search_cache(session_id=session_id)
        db.set_setting(f"ui_seen_{session_id}", "0")
        sess["answers"] = {}
        sess.pop("search_job_id", None)

    db.save_profile(prof, profile_id="master")
    db.set_active_resume_profile("master")
    db.set_setting("active_session_id", session_id)
    db.set_setting("active_resume_id", new_resume_id)
    db.set_setting("radar_force_refresh", "1")

    filename = Path(resume_path).name if resume_path else "pasted_resume.txt"
    inf = role_inference.infer_roles(prof, filename)
    sess["profile"] = prof
    sess["inference_result"] = inf
    sess["resume_id"] = new_resume_id

    # D3: Store inferences into guesses table (never filters search/view). Never store resume-guessed locations.
    for r in inf.get("roles", []):
        db.store_guess(session_id, "role", r.get("role", ""), confidence=float(r.get("confidence", 0.0)), resume_id=sess["resume_id"])
    if inf.get("job_type_guess"):
        db.store_guess(session_id, "job_type", inf["job_type_guess"].get("value", ""), confidence=float(inf["job_type_guess"].get("confidence", 0.0)), resume_id=sess["resume_id"])
    if inf.get("region_guess") and inf["region_guess"].get("value"):
        db.store_guess(session_id, "location", inf["region_guess"].get("value", ""), confidence=float(inf["region_guess"].get("confidence", 0.0)), resume_id=sess["resume_id"])

    # Profile Line formatting (D12)
    cand_name = check_res.get("name") or prof.get("name") or "Candidate"
    roles_with_conf = [f"{r.get('role', '')} ({float(r.get('confidence', 0.0)):.2f})" for r in inf.get("roles", [])[:2]]
    roles_str = ", ".join(roles_with_conf) if roles_with_conf else "General"
    years = prof.get("years_of_experience") if prof.get("years_of_experience") is not None else prof.get("years_experience")
    years_str = f"{years} years" if years else "Intern / Student"
    skills = prof.get("skills", [])[:5]
    if isinstance(skills, dict):
        skills = list(skills.keys())[:5]
    skills_str = ", ".join(skills) if skills else "Software Engineering"
    profile_line = f"Profile: {cand_name} | Roles: {roles_str} | Exp: {years_str} | Top Skills: {skills_str}. Tell me if this is wrong."
    sess["profile_line"] = profile_line

    ask_role = (len(inf.get("role_focus", [])) == 0)

    # Mandatory Round 1 Questions (D1, D4, Steps 2-3 Place Rule)
    step3_q = interview_questions.build_step_3_target_questions(
        inf["roles"], inf["region_guess"], ask_role=ask_role
    )
    sess["last_questions"] = step3_q
    sess["pending_questions"] = step3_q["questions"]
    sess["role_focus"] = inf.get("role_focus", [])
    sess["title_families"] = inf.get("title_families", [])
    warnings_lines = "\n".join(check_res["warnings"]) if check_res["warnings"] else ""
    header_parts = []
    if notice:
        header_parts.append(notice)
    header_parts.append(profile_line)
    if warnings_lines:
        header_parts.append(warnings_lines)
    header_parts.append("")
    header_parts.append(step3_q["formatted_text"])
    header_text = "\n".join(header_parts)
    status_name = "needs_role" if ask_role else "needs_target"

    # Transition state machine to ASKED and record presented questions
    ticket_manager.transition_session_state(session_id, ticket_manager.SessionState.ASKED)
    ticket_manager.record_questions_presented(session_id, step3_q["formatted_text"])

    reply = {
        "status": status_name,
        "session_id": session_id,
        "step": 2,
        "notice": notice,
        "profile_line": profile_line,
        "message_for_user": ticket_manager.build_stop_message(header_text),
        "ask_user": step3_q["formatted_text"],
        "options": step3_q,
        "next_tool": "jh_confirm",
        "data": {
            "name": check_res["name"],
            "session_id": session_id,
            "profile_line": profile_line,
            "one_line_summary": inf.get("one_line_summary", ""),
            "inferred_roles": inf["roles"],
            "role_focus": inf.get("role_focus", []),
            "title_families": inf.get("title_families", []),
            "title_families_note": "Inferred title variants (guesses) used for search queries only; never used to filter results.",
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

    # Validate user reply (D2 gate: non-empty, >= 2 chars, not question echo, >= 5s elapsed)
    valid, err = ticket_manager.validate_user_reply(session_id, user_reply)
    if not valid:
        return {
            "status": "needs_input",
            "step": 2,
            "message_for_user": ticket_manager.build_stop_message(
                f"Invalid input: {err}\nPlease provide the user's actual answers to the target search questions."
            ),
            "ask_user": "Please answer the target search questions (Method, Target place, and Role).",
            "next_tool": "jh_confirm",
            "data": {"error": err},
        }

    # Record verbatim words in session log and persistent audit log
    ticket_manager.record_user_reply(session_id, user_reply)
    db.log_audit_event(session_id, user_reply, action="jh_confirm", details=str(answers or {}))
    clean_reply = str(user_reply).strip().lower()
    answers = answers or {}

    # 1. Parse Method (default Modern; tolerate typos like 'clasic')
    if "classic" in clean_reply or re.search(r"\b(?:clas+s?ic|classik|job\s*boards?)\b", clean_reply) or answers.get("method") == "classic":
        chosen_method = "classic"
    elif "modern" in clean_reply or answers.get("method") == "modern":
        chosen_method = "modern"
    else:
        chosen_method = "modern"

    config.set_method(chosen_method)
    db.set_session_state(f"method_{chosen_method}")

    # 2. Parse Target Place (NEVER guess from resume, address, phone, IP, or language)
    from . import regions
    inf = sess.get("inference_result") or {}
    parsed_places = regions.parse_confirmed_places(user_reply, answers)
    places = list(parsed_places.get("places") or [])
    if not places:
        return {
            "status": "needs_input",
            "step": 2,
            "ticket": None,
            "message_for_user": ticket_manager.build_stop_message(
                "Please confirm your target place before I issue a session ticket (I never guess place from your resume). "
                "Pick one or several: remote only, international or worldwide remote, or a specific country/region "
                "(e.g. France, Europe, South Asia, or the USA), plus an optional city."
            ),
            "ask_user": "Target place (remote only, international/worldwide remote, or specific country/region + optional city, visa free or sponsoring visa)?",
            "next_tool": "jh_confirm",
            "data": {"error": "target_place_required", "ticket": None},
        }
    chosen_place = ", ".join(places)

    # 3. Parse Target Role (keep guesses out of filters unless user explicitly confirms/overrides role)
    role_confirmed = False
    if answers.get("target_role") or answers.get("role"):
        role_focus = [str(answers.get("target_role") or answers.get("role")).strip()]
        role_confirmed = True
    else:
        m = re.search(r"(?:role(?:\s*is|:)?|target(?:\s*role)?(?:\s*is|:)?|i want|aiming for)\s+([a-zA-Z\s\/\+\#]+?)(?:in|using|with|method|$|,)", user_reply, re.I)
        if m and len(m.group(1).strip().split()) <= 4:
            role_focus = [m.group(1).strip()]
            role_confirmed = True
        else:
            role_focus = sess.get("role_focus") or [r["role"] for r in inf.get("roles", [])[:1]] or ["Software Engineer"]

    view_filter_payload: dict[str, Any] = {
        "locations": places,
        "method": chosen_method,
        "roles": role_focus if role_confirmed else [],
    }
    if role_confirmed:
        view_filter_payload["job_style"] = role_focus[0]
    if parsed_places.get("remote_only") or parsed_places.get("worldwide_remote"):
        view_filter_payload["work_mode"] = "remote"
        sess["answers"]["work_mode"] = "remote"

    db.save_view_filters(view_filter_payload, session_id=session_id)
    sess["answers"]["locations"] = places
    sess["role_focus"] = role_focus
    sess["target_place"] = chosen_place
    sess["confirmed_places"] = places
    sess["method"] = chosen_method

    resume_id = sess.get("resume_id") or "master"
    ticket = ticket_manager.generate_ticket(
        session_id=session_id,
        resume_id=resume_id,
        roles=role_focus,
        method=chosen_method,
        location=chosen_place,
    )
    # D3: Store confirmed answers from user reply into answers & confirmed_facts tables
    db.store_answer(session_id, "method", chosen_method, user_reply=user_reply)
    db.store_answer(session_id, "target_place", chosen_place, user_reply=user_reply)
    db.add_confirmed_fact(f"target_place: {chosen_place}", category="target_place", session_id=session_id)
    if parsed_places.get("remote_only") or parsed_places.get("worldwide_remote"):
        db.add_confirmed_fact("work_mode: remote", category="work_mode", session_id=session_id)
    if role_confirmed and role_focus:
        db.store_answer(session_id, "role", ", ".join(role_focus), user_reply=user_reply)
        db.add_confirmed_fact(f"target_role: {', '.join(role_focus)}", category="role", session_id=session_id)

    # D1: Transition session state machine to ANSWERED
    ticket_manager.transition_session_state(session_id, ticket_manager.SessionState.ANSWERED)

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


def _resolve_launch_search_params(sess: dict[str, Any], session_id: str) -> tuple[str, str, list[str]]:
    """Resolve confirmed role/title-family query parameters and target place for background search."""
    confirmed_role = db.get_confirmed_answer(session_id, "role")
    inf = sess.get("inference_result") or {}
    if confirmed_role:
        from . import role_inference
        family = role_inference.expand_title_family(confirmed_role)
        query = confirmed_role
        search_role_focus = family
    else:
        role_guesses = db.get_guesses(session_id, category="role")
        high_conf = [r["value"] for r in role_guesses if r.get("confidence", 0.0) >= 0.5]
        base_roles = high_conf or sess.get("role_focus") or ["Software Engineer"]
        families = inf.get("title_families") or []
        if not families:
            from . import role_inference
            families = role_inference.expand_title_family(base_roles[0])
        query = ", ".join(base_roles)
        search_role_focus = families

    target_loc = db.get_confirmed_answer(session_id, "target_place") or sess.get("target_place") or ""
    return query, target_loc, search_role_focus


@_coaching_envelope
def jh_launch(session_id: str = "default", ticket: str = "") -> dict[str, Any]:
    """Phase B4: Detached launch of HTTP daemon, background search, and browser in under 3 seconds."""
    sess = ticket_manager.get_or_create_session(session_id)

    # D1 State Machine & Ticket Gate
    ok, err_res = ticket_manager.check_tool_state_gate(session_id, "jh_launch", ticket=ticket)
    if not ok:
        return err_res

    ticket_manager.mark_ticket_launched(ticket)

    active_method = (sess.get("method") or db.get_confirmed_answer(session_id, "method") or config.get_method()).lower().strip()

    # 1. Start server.py detached if down
    server_res = worker_launcher.start_detached_server(preferred_port=8080)
    port = server_res["port"]
    # Modern UI opens #/signals (with full jobs available on #/jobs); Classic opens #/jobs (D5)
    ui_route = "#/signals" if active_method == "modern" else "#/jobs"
    ui_url = f"http://127.0.0.1:{port}/?session={session_id}{ui_route}"
    sess["worker_port"] = port
    sess["ui_url"] = ui_url

    # 2. Start search engines: Modern runs Signal Radar AND Multi-Board Search; Classic runs Multi-Board Search (D5)
    query, target_loc, search_role_focus = _resolve_launch_search_params(sess, session_id)
    if active_method == "modern":
        from . import radar, signals as _signals
        radar.start_radar_worker()
        conf_role = db.get_confirmed_answer(session_id, "role")
        sig_role = conf_role or ((sess.get("role_focus") or ["Software Engineer"])[0])
        sig_loc = target_loc or "any"

        def _kick_modern_signals():
            try:
                _signals.poll_modern_signals(target_role=sig_role, target_region=sig_loc)
            except Exception:
                pass

        import threading as _th
        _th.Thread(target=_kick_modern_signals, daemon=True, name=f"jh-modern-sig-{session_id}").start()

        if not sess.get("board_search_job_id"):
            board_res = worker_launcher.start_background_search(
                session_id=session_id,
                query=query,
                location=target_loc,
                role_focus=search_role_focus,
            )
            sess["board_search_job_id"] = board_res["search_job_id"]

        search_status = "started" if sess.get("search_job_id") != "radar_worker" else "already_running"
        search_job_id = sess.get("search_job_id") or "radar_worker"
        sess["search_job_id"] = search_job_id
    else:
        if sess.get("search_job_id"):
            search_job_id = sess["search_job_id"]
            search_status = "already_running"
        else:
            search_res = worker_launcher.start_background_search(
                session_id=session_id,
                query=query,
                location=target_loc,
                role_focus=search_role_focus,
            )
            search_job_id = search_res["search_job_id"]
            sess["search_job_id"] = search_job_id
            search_status = "started"

    # 3. Launch Chromium with dedicated profile and ATS autofill extension (D7)
    from . import extension_installer
    ext_dir = extension_installer.find_extension_dir()
    browser_opened = worker_launcher.open_browser(ui_url)
    sess["browser_opened"] = browser_opened
    ext_status = "loaded" if Path(ext_dir).is_dir() else "manual_load_ready"
    ui_seen = bool(sess.get("ui_seen", False))

    # Build Round 2 questions (incorporating method: Modern vs Classic) (D8)
    chosen_method = sess.get("method", "modern")
    r2 = interview_questions.build_round_2_questions(
        sess.get("profile", {}),
        sess.get("inference_result", {}).get("job_type_guess", {}),
        sess.get("inference_result", {}).get("region_guess", {}),
        method=chosen_method,
    )
    sess["round_2_questions"] = r2

    if ui_seen:
        ui_line = f"The Web UI is open at {ui_url}"
    else:
        ui_line = f"Web UI available at {ui_url} (seen: False)"

    post_launch_line = f"{ui_line}. Search status: {search_status}. Questions come next."

    msg = (
        f"{post_launch_line}\n\n"
        f"INSTRUCTION FOR AI: Output the single line above. Do not list jobs in chat; results are displayed live in the web UI. "
        f"Then ask the Round 2 questions below. Call jh_status at most once and NEVER poll in a loop.\n\n"
        f"While search runs, please answer these preferences to filter results live in the UI:\n"
        f"{r2['formatted_text']}"
    )

    launch_status = "reused" if server_res["status"] == "reused" and search_status == "already_running" else "started"

    ticket_manager.transition_session_state(session_id, ticket_manager.SessionState.LAUNCHED)
    ticket_manager.record_questions_presented(session_id, r2["formatted_text"])

    return {
        "status": "ok",
        "launch_status": launch_status,
        "step": 4,
        "server_status": server_res["status"],
        "ui_url": ui_url,
        "browser_opened": browser_opened,
        "ui_seen": ui_seen,
        "extension_status": ext_status,
        "search_status": search_status,
        "search_job_id": search_job_id,
        "post_launch_summary": post_launch_line,
        "message_for_user": msg,
        "ask_user": r2["formatted_text"],
        "options": r2,
        "next_tool": "jh_answer",
        "data": {
            "ui_url": ui_url,
            "port": port,
            "search_job_id": search_job_id,
            "board_search_job_id": sess.get("board_search_job_id", ""),
            "server_status": server_res["status"],
            "extension_status": ext_status,
            "extension_dir": ext_dir,
            "browser_opened": browser_opened,
            "ui_seen": ui_seen,
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

    # Validate user reply (D2 gate: non-empty, >= 2 chars, not question echo, >= 5s elapsed)
    valid, err = ticket_manager.validate_user_reply(session_id, user_reply)
    if not valid:
        return {
            "status": "needs_input",
            "step": 4,
            "message_for_user": ticket_manager.build_stop_message(
                f"Invalid input: {err}\nPlease provide the user's actual reply to the Round 2 questions."
            ),
            "ask_user": "Please answer the Round 2 questions.",
            "next_tool": "jh_answer",
            "data": {"error": err},
        }

    # Record verbatim words in session log and persistent audit log
    ticket_manager.record_user_reply(session_id, user_reply)
    db.log_audit_event(session_id, user_reply, action="jh_answer", details=str(answers or {}))

    reading_prefix = ""
    if user_reply and ticket_manager.is_explicit_skip(user_reply):
        ticket_manager.record_user_skip(session_id, "round_2", user_reply)
        for field in ["job_type", "work_mode", "visa", "pay", "company_type", "location", "locations"]:
            if field not in sess["answers"]:
                sess["answers"][field] = "any"
        sess["pending_questions"] = []
        sess["round_2_done"] = True
        ticket_manager.transition_session_state(session_id, ticket_manager.SessionState.ROUND2_DONE)
        db.set_session_state("round_2_skipped", last_tool="jh_answer")
    else:
        mapped_dict = {}
        if user_reply:
            sess["user_reply_log"] = sess.get("user_reply_log", []) + [user_reply]
            clean_reply = user_reply.lower().strip()

            if re.search(r"\b(?:intern|internship|pfe)\b", clean_reply) or (
                re.search(r"\bstage\b", clean_reply) and not re.search(r"\b(?:company|compny)\s+stage\b", clean_reply)
            ):
                answers["job_type"] = "internship"
                mapped_dict["job_type"] = "internship"
            elif re.search(r"\b(?:full[-\s]?time|full|junior)\b", clean_reply):
                answers["job_type"] = "full-time"
                mapped_dict["job_type"] = "full-time"

            if re.search(r"\b(?:remote|remtoe)\b", clean_reply):
                answers["work_mode"] = "remote"
                mapped_dict["work_mode"] = "remote"
            elif "hybrid" in clean_reply:
                answers["work_mode"] = "hybrid"
                mapped_dict["work_mode"] = "hybrid"
            elif "onsite" in clean_reply or "on-site" in clean_reply:
                answers["work_mode"] = "on-site"
                mapped_dict["work_mode"] = "on-site"

            sal_match = re.search(
                r"\b(?:at\s+least|min(?:imum)?(?:\s+(?:salary|salry|pay|comp(?:ensation)?))?|above|salary(?:\s+(?:at\s+least|min|minimum|above|of))?)\s*[:$]?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?\b",
                clean_reply,
            )
            if sal_match:
                val = float(sal_match.group(1).replace(",", ""))
                if sal_match.group(2):
                    val *= 1000.0
                answers["min_salary"] = val
                mapped_dict["min_salary"] = val

            clean_reply_no_paren = re.sub(r"\(.*?\)", "", clean_reply).strip()
            from . import regions
            parsed_loc = regions.parse_confirmed_places(user_reply, None)
            explicit_place_switch = bool(re.search(r"\b(?:location|place|where|city|country|move|relocate|switch|change)\b", clean_reply))
            non_remote_places = [p for p in (parsed_loc.get("places") or []) if p.lower() not in ("remote",)]
            if (non_remote_places or (parsed_loc.get("places") and explicit_place_switch)) and not answers.get("locations"):
                answers["locations"] = non_remote_places or list(parsed_loc["places"])
                mapped_dict["locations"] = list(answers["locations"])
                if parsed_loc.get("worldwide_remote") or (parsed_loc.get("remote_only") and explicit_place_switch):
                    answers["work_mode"] = "remote"
                    mapped_dict["work_mode"] = "remote"

            # Lesson A: Optional Step 5 targeting (industry, company_stage, market_served, languages)
            if not answers.get("confirmed_industries") and not answers.get("industry"):
                ind_hits = [ind for ind in ("saas", "fintech", "healthtech", "ai", "cybersecurity", "ecommerce", "e-commerce", "consulting") if re.search(rf"\b{re.escape(ind)}\b", clean_reply)]
                if ind_hits:
                    answers["confirmed_industries"] = ind_hits
                    mapped_dict["confirmed_industries"] = ind_hits

            if not answers.get("company_stages") and not answers.get("company_stage"):
                stage_hits = []
                if re.search(r"\bstartup\b", clean_reply):
                    stage_hits.append("startup")
                if re.search(r"\bscale[-\s]?up\b", clean_reply):
                    stage_hits.append("scale-up")
                if re.search(r"\bpublic\b", clean_reply):
                    stage_hits.append("public")
                if stage_hits:
                    answers["company_stages"] = stage_hits
                    mapped_dict["company_stages"] = stage_hits

            if not answers.get("markets_served") and not answers.get("market_served"):
                mkt_hits = [m for m in ("b2b", "b2c", "enterprise", "smb", "developer tools", "devtools") if re.search(rf"\b{re.escape(m)}\b", clean_reply)]
                if mkt_hits:
                    answers["markets_served"] = mkt_hits
                    mapped_dict["markets_served"] = mkt_hits

            if not answers.get("languages"):
                lang_hits = [lg for lg in ("bilingual", "english", "french", "arabic", "german", "spanish") if re.search(rf"\b{re.escape(lg)}\b", clean_reply)]
                if lang_hits:
                    answers["languages"] = lang_hits
                    mapped_dict["languages"] = lang_hits

            # Lesson D: Side work / freelance / contract fact (stored ONLY when explicitly confirmed)
            if not answers.get("side_work"):
                side_m = re.search(r"(?:side\s+work|freelance|contract(?:\s+work)?)\s*(?::|is|-)?\s*([^\n.;]+)", user_reply, re.I)
                if side_m:
                    sw_val = side_m.group(1).strip()
                    if sw_val and sw_val.lower() not in ("none", "no", "n/a", "skip"):
                        answers["side_work"] = sw_val
                        mapped_dict["side_work"] = sw_val

            _EXCL_STOPWORDS = {
                "more", "a", "an", "the", "devops", "visa", "sponsor", "sponsorship",
                "side", "work", "freelance", "contract", "remote", "hybrid", "onsite",
                "on-site", "senior", "junior", "pay", "salary", "cap", "limit", "need",
                "needed", "required", "experience", "problem", "worries", "preference",
                "preferences", "any", "match", "jobs", "roles",
            }
            excl_matches = re.findall(r"\b(?:exclude|avoid|not|no)\s+([a-zA-Z0-9_-]+)", clean_reply)
            filtered_excl = [w.strip().lower() for w in excl_matches if w.strip().lower() not in _EXCL_STOPWORDS]
            if filtered_excl:
                answers["excluded_keywords"] = filtered_excl
                mapped_dict["excluded_keywords"] = filtered_excl

            if not re.search(r"\b(?:no|not)\s+senior\b", clean_reply) and any(
                w in clean_reply for w in ["go higher", "search higher", "search senior", "aim higher", "senior"]
            ):
                answers["level_shift"] = 1
                mapped_dict["level_shift"] = 1
            elif not re.search(r"\b(?:no|not)\s+junior\b", clean_reply) and any(
                w in clean_reply for w in ["go lower", "search lower", "something easier", "junior"]
            ):
                answers["level_shift"] = -1
                mapped_dict["level_shift"] = -1

            if "forget devops" in clean_reply or "forget" in clean_reply or "clear role" in clean_reply:
                answers["role_pivot"] = None
                mapped_dict["role_pivot"] = None
            elif "devops instead" in clean_reply or ("devops" in clean_reply and "forget" not in clean_reply):
                answers["role_pivot"] = "DevOps"
                answers["roles"] = ["DevOps Engineer"]
                mapped_dict["role_pivot"] = "DevOps"

            if "visa" in clean_reply or "sponsor" in clean_reply:
                if any(w in clean_reply for w in ["no sponsor", "no visa", "citizen", "authorized", "don't need", "dont need", "none"]):
                    answers["visa_need"] = False
                    mapped_dict["visa_need"] = False
                elif any(w in clean_reply for w in ["need sponsor", "require sponsor", "sponsorship required", "visa required", "need visa", "yes"]):
                    answers["visa_need"] = True
                    mapped_dict["visa_need"] = True

            cap_match = re.search(r"(?:cap|limit|daily)\s*(?:of|is|:)?\s*(\d+)", clean_reply)
            if cap_match:
                c_val = int(cap_match.group(1))
                answers["daily_email_cap"] = c_val
                mapped_dict["daily_email_cap"] = c_val
                config.set_daily_cap(c_val)

            if mapped_dict:
                reading_prefix = f"I read this as: {', '.join(f'{k}: {v}' for k, v in mapped_dict.items())}. Say if wrong.\n"
            else:
                reading_prefix = f"I read this as: {user_reply}. Say if wrong.\n"

        if "location" in answers and "locations" not in answers:
            loc = answers["location"]
            answers["locations"] = [loc] if isinstance(loc, str) else list(loc)
        if "industry" in answers and "confirmed_industries" not in answers:
            ind_v = answers["industry"]
            answers["confirmed_industries"] = [ind_v] if isinstance(ind_v, str) else list(ind_v)
        if "company_stage" in answers and "company_stages" not in answers:
            st_v = answers["company_stage"]
            answers["company_stages"] = [st_v] if isinstance(st_v, str) else list(st_v)
        if "market_served" in answers and "markets_served" not in answers:
            mk_v = answers["market_served"]
            answers["markets_served"] = [mk_v] if isinstance(mk_v, str) else list(mk_v)

        # Contract Step 5: Never restart search on live filter edits; persist confirmed facts & SQL filters only
        if answers.get("locations"):
            sess["target_place"] = ", ".join(str(x) for x in answers["locations"])
            db.add_confirmed_fact(f"target_place: {sess['target_place']}", category="target_place", session_id=session_id)
        for fact_cat, ans_key in (
            ("industry", "confirmed_industries"),
            ("company_stage", "company_stages"),
            ("market_served", "markets_served"),
            ("languages", "languages"),
        ):
            if answers.get(ans_key):
                vals = answers[ans_key] if isinstance(answers[ans_key], list) else [answers[ans_key]]
                db.add_confirmed_fact(f"{fact_cat}: {', '.join(str(x) for x in vals)}", category=fact_cat, session_id=session_id)
        if answers.get("side_work"):
            sw = str(answers["side_work"]).strip()
            if sw.lower() not in ("none", "no", "skip"):
                db.add_confirmed_fact(sw, category="side_work", session_id=session_id)

        sess["answers"].update(answers)
        sess["pending_questions"] = []
        sess["round_2_done"] = True
        ticket_manager.transition_session_state(session_id, ticket_manager.SessionState.ROUND2_DONE)
        db.set_session_state("round_2_answered", last_tool="jh_answer")

    # Persist answers into view filters & user preferences
    db.set_setting("active_session_id", session_id)
    db.save_view_filters(sess["answers"], session_id=session_id)
    try:
        from . import preferences, regions as _reg
        pref_updates = {}
        if "locations" in sess["answers"]:
            geo_locs = []
            for loc_item in sess["answers"]["locations"]:
                ls = str(loc_item or "").strip()
                if not ls or ls.lower() in ("any", "remote", "remote only", "worldwide", "worldwide remote", "international remote"):
                    continue
                if _reg.to_code(ls) or _reg.country_of_location(ls):
                    geo_locs.append(ls)
            if geo_locs:
                pref_updates["cities"] = geo_locs
                pref_updates["target_countries"] = geo_locs
        if "work_mode" in sess["answers"] and sess["answers"]["work_mode"].lower() != "any":
            pref_updates["work_mode"] = sess["answers"]["work_mode"].capitalize()
        if pref_updates:
            preferences.save(pref_updates)
    except Exception:
        pass

    # Re-evaluate SQL query filters
    q_res = db.query_jobs(session_id=session_id)

    port_info = worker_launcher.get_running_server_info()
    port = port_info["port"] if port_info else (sess.get("worker_port") or 8080)
    ui_url = f"http://127.0.0.1:{port}/?session={session_id}"

    hidden_count = max(0, q_res.get("total_active_pool", q_res["count"]) - q_res["count"])

    return {
        "status": "ok",
        "step": 5,
        "filters": sess["answers"],
        "message_for_user": (
            (reading_prefix if reading_prefix else "") +
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
    db.set_setting("active_session_id", session_id)

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
    """Step 5 & 6: Search tool with Gate 1 ticket and session state enforcement.
    Rejects out-of-order calls before questions are answered.
    """
    ok, err_res = ticket_manager.check_tool_state_gate(session_id, "jh_search", ticket=ticket)
    if not ok:
        return err_res

    style = (job_style or "").strip()

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
            "ui_url": f"http://127.0.0.1:{worker_launcher.get_running_server_info()['port'] if worker_launcher.get_running_server_info() else 8080}/?session={session_id}",
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
            "ui_url": f"http://127.0.0.1:{worker_launcher.get_running_server_info()['port'] if worker_launcher.get_running_server_info() else 8080}/?session={session_id}",
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
    msg = f"Web UI is running at {url}. Please open {url} in your browser."

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
def jh_status(session_id: str = "default", include_matches: bool = False) -> dict[str, Any]:
    """Inspect full JobHunter state: active method, workspace path, session state, radar, refresh states, cleanup status, and top 5 matches."""
    home_dir = home.get_home()
    session_state = db.get_session_state()
    radar = db.get_radar_state()
    refresh = db.get_refresh_states()
    cleanup = db.get_cleanup_status()
    profile = db.get_profile()
    filters = db.get_view_filters(session_id)
    active_method = config.get_method()
    sess = ticket_manager.get_or_create_session(session_id)

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

    questions_waiting = len(sess.get("pending_questions", []))
    curr_state_str = session_state.get("current_state", "") if isinstance(session_state, dict) else str(session_state)
    if questions_waiting == 0 and curr_state_str in ("round_2_pending", "round_1_done", "ready"):
        questions_waiting = 6
    if curr_state_str in ("round_2_answered", "round_2_skipped"):
        questions_waiting = 0

    has_pending = bool(sess.get("pending_questions")) or (questions_waiting > 0 and curr_state_str not in ("round_2_answered", "round_2_skipped"))
    if has_pending or not include_matches:
        top_matches = []
    else:
        top_matches = top_5

    if active_method == "modern":
        method_summary = (
            f"- Method: Modern (Outreach First)\n"
            f"- Signals: {signals_count} stored ({fresh_signals} fresh)\n"
            f"- Stored Jobs: {total_jobs} ({active_jobs} active) | Matches: {matches_count} ({hidden_count} hidden by filters)\n"
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

    from . import extension_installer
    ext_dir = extension_installer.find_extension_dir()
    ext_status = "loaded" if Path(ext_dir).is_dir() else "manual_load_ready"
    ui_seen = (
        bool(sess.get("ui_seen", False))
        or (curr_state_str == "ui_seen")
        or (db.get_setting(f"ui_seen_{session_id}", "") == "1")
    )
    browser_opened = bool(sess.get("browser_opened", False))

    # Force D8: until round 2 is answered or skipped, every reply carries ask_user with pending questions
    state_enum = ticket_manager.get_session_state_name(session_id)
    r2_pending = (state_enum == ticket_manager.SessionState.LAUNCHED) and not sess.get("round_2_done")
    if r2_pending:
        r2 = sess.get("round_2_questions")
        if not r2:
            r2 = interview_questions.build_round_2_questions(
                sess.get("profile", {}),
                sess.get("inference_result", {}).get("job_type_guess", {}),
                sess.get("inference_result", {}).get("region_guess", {}),
                method=active_method,
            )
            sess["round_2_questions"] = r2
        ask_user_val = r2.get("formatted_text")
    else:
        ask_user_val = None

    pacing_note = "Waiting on replies often reflects budget timing and hiring pauses rather than fit."
    msg = (
        f"JobHunter Status:\n"
        f"- Workspace: {home_dir}\n"
        f"{method_summary}\n"
        f"- Active Profile: {profile.get('_profile_name')} ({profile.get('target_title') or 'Candidate'})\n"
        f"- Web UI: {ui_url}\n"
        f"- Note: {pacing_note}"
    )

    return {
        "status": "ok",
        "step": "status",
        "session_id": session_id,
        "message_for_user": msg,
        "ask_user": ask_user_val,
        "options": {
            "choices": ["jh_start", "jh_set_method", "jh_open_ui"],
            "recommended": "jh_start"
        },
        "next_tool": "jh_search" if active_method == "classic" else "jh_start",
        "data": {
            "method": active_method,
            "session_id": session_id,
            "matches": matches_count,
            "hidden_by_filters": hidden_count,
            "ui_url": ui_url,
            "browser_opened": browser_opened,
            "ui_seen": ui_seen,
            "extension_status": ext_status,
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
            "pacing_note": pacing_note,
        }
    }


def build_ai_task_payload(task: str, job: dict[str, Any] | None = None, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ensure AI payload receives strictly the minimal fields needed for the task, with no DB or contact dumps."""
    clean_payload: dict[str, Any] = {"task": task}
    if job:
        clean_payload["job"] = {
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "description": (job.get("description", "") or "")[:1500],
            "skills": job.get("required_skills", []) or job.get("skills", []),
        }
    if profile:
        clean_payload["profile"] = {
            "target_title": profile.get("target_title", ""),
            "skills": profile.get("skills", [])[:20],
            "experience_summary": profile.get("summary", ""),
        }
    return clean_payload


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


@_coaching_envelope
def jh_ask_missing_metrics(session_id: str = "default") -> dict[str, Any]:
    """Identify bullets without metrics in the profile and ask once in a single batch of <= 5 questions (R2)."""
    from . import db, refit
    profile = db.get_profile(session_id) or db.get_profile() or {}
    questions = refit.extract_missing_metric_questions(profile, limit=5)
    return {
        "status": "ok",
        "count": len(questions),
        "questions": questions,
        "message": (
            f"Found {len(questions)} bullets without metrics. You may provide real numbers or skip."
            if questions
            else "All bullets have metrics or no questions needed."
        ),
    }


@_coaching_envelope
def jh_confirm_metric(
    session_id: str = "default",
    question_id: str = "",
    bullet_ref: str = "",
    metric_value: str = "",
    skip: bool = False,
) -> dict[str, Any]:
    """Confirm or skip a real metric for a resume bullet (R2).
    Confirmed metrics are stored with label 'user_confirmed' and date. Never estimates or rounds up.
    """
    from . import db
    if skip or not metric_value.strip():
        return {
            "status": "skipped",
            "question_id": question_id,
            "message": "Metric question skipped; bullet will remain unnumbered.",
        }

    fact_text = f"Metric confirmed for {bullet_ref or question_id}: {metric_value.strip()}"
    fact_id = db.add_confirmed_fact(
        fact_text,
        category="metric",
        label="user_confirmed",
        session_id=session_id,
    )

    profile = db.get_profile(session_id) or db.get_profile() or {}
    if question_id.startswith("q_metric_"):
        parts = question_id.split("_")
        if len(parts) >= 4 and parts[2].isdigit() and parts[3].isdigit():
            xi, bi = int(parts[2]), int(parts[3])
            exps = profile.get("experience", [])
            if xi < len(exps):
                bullets = exps[xi].get("bullets", [])
                if bi < len(bullets):
                    orig = bullets[bi].rstrip(".")
                    bullets[bi] = f"{orig} ({metric_value.strip()})."
                    db.save_profile(profile, profile_id=session_id)

    return {
        "status": "confirmed",
        "fact_id": fact_id,
        "metric_value": metric_value.strip(),
        "label": "user_confirmed",
        "message": f"Stored confirmed metric: {metric_value.strip()}",
    }
