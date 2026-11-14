"""V5 MCP Tools: Guided interview flow, broad search, narrow view, and workspace isolation."""
from __future__ import annotations

import logging
import socket
import time
import urllib.request
import webbrowser
from typing import Any, Optional

from . import config, db, dedup, home, pipeline, preferences, workspace
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


def jh_start(prompt: str = "", intent: str = "", session_id: str = "default") -> dict[str, Any]:
    """Step 1 & 2: Entry point for any job-related prompt. Sets up isolated workspace, loads saved profile and view filters, detects intent, and returns the first guided question."""
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
        return jh_status()

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
        # Modern Interview: Round 1 (target role required, region, stage, pay, visa, work mode)
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
        # Classic Interview: Round 1
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


def jh_load_resume(resume_path: str = "", raw_text: str = "", profile_id: str = "master") -> dict[str, Any]:
    """Step 3: Load, parse, and extract skills, target roles, and experience from a resume file or raw text into candidate profile."""
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
        from . import refit
        parsed_profile = dict(db.EMPTY_PROFILE)
        parsed_profile["summary"] = raw_text[:500]
        # Extract basic skills from text
        parsed_profile["skills"] = [w for w in ["Python", "JavaScript", "TypeScript", "SQL", "Docker", "AWS", "Go", "Java", "React"] if w.lower() in raw_text.lower()]
        parsed_profile["target_title"] = "Software Engineer"
        parsed_profile["_is_empty"] = False

    else:
        # Search for resumes in home/resumes
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
        "message_for_user": f"Parsed resume for '{title}'. Found {len(skills)} skills and {years} years of experience. Note: Search filters are NOT auto-filled without your permission.",
        "ask_user": "Do you confirm this extracted profile, or would you like to provide overrides?",
        "options": {
            "choices": ["confirm", "edit"],
            "recommended": "confirm"
        },
        "next_tool": "jh_confirm_profile",
        "data": {
            "profile_id": profile_id,
            "target_title": title,
            "skills": skills[:15],
            "years_of_experience": years,
        }
    }


def jh_confirm_profile(
    confirmed: bool = True,
    overrides: Optional[dict[str, Any]] = None,
    portfolio_url: str = "",
    proof_points: Optional[list[dict[str, str]]] = None,
    profile_id: str = "master"
) -> dict[str, Any]:
    """Step 3: Confirm profile details, collect portfolio link and 3 proof points, and activate candidate profile."""
    prof = db.get_profile(profile_id)
    if overrides and isinstance(overrides, dict):
        prof.update(overrides)
    if portfolio_url:
        prof["portfolio_url"] = str(portfolio_url).strip()
    if proof_points is not None:
        prof["proof_points"] = proof_points

    db.save_profile(prof, profile_id=profile_id)
    db.set_active_resume_profile(profile_id)
    db.set_session_state("profile_confirmed", last_tool="jh_confirm_profile")

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
            "Which search method do you prefer?\n"
            "1. Modern (Recommended): Outreach first. Catch fresh hiring posts & seed funding news, "
            "find decision-maker emails, and send a short human email before the crowd applies.\n"
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


def jh_search(job_style: str = "", region: str = "", force_refresh: bool = False, session_id: str = "default") -> dict[str, Any]:
    """Step 5 & 6: Broad search by job style and optional region. Scrapes all sources broadly and stores all results in DB with lifecycle deduplication. Blocks only if job style is missing."""
    style = (job_style or "").strip()
    if not style:
        # Load from saved filters if available
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


def jh_query(filters: Optional[dict[str, Any]] = None, session_id: str = "default") -> dict[str, Any]:
    """Step 7: Query stored jobs using view filters without re-scraping. Hard filters hide, soft preferences rank, expired jobs returned in closing_soon."""
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


def jh_open_ui(port: int = 8765, host: str = "127.0.0.1") -> dict[str, Any]:
    """Step 8: Start the web UI server if down, verify health endpoint, find next free port if occupied, start LinkedIn Radar worker, and open browser."""
    from . import httpd
    ws = home.get_home()

    # 1. Check if server already running on port
    target_port = port
    url = f"http://{host}:{target_port}"
    server_ready = _check_health(host, target_port, timeout=0.5)

    # 2. If down, find free port and start
    if not server_ready:
        if _is_port_in_use(target_port, host):
            target_port = _find_free_port(target_port + 1, host)
            url = f"http://{host}:{target_port}"

        try:
            httpd.start_server(host=host, port=target_port, ws_dir=ws)
        except Exception as e:
            log.warning("HTTP daemon start failed: %s", e)

        # Poll /health for up to 15 seconds
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if _check_health(host, target_port, timeout=1.0):
                server_ready = True
                break
            time.sleep(0.3)

    # 3. Start LinkedIn Radar worker
    from . import radar
    radar.start_radar_worker()

    # 4. Open in browser
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


def jh_status() -> dict[str, Any]:
    """Inspect full JobHunter state: active method, workspace path, session state, radar, refresh states, cleanup status, and stored job/signal counts."""
    home_dir = home.get_home()
    session_state = db.get_session_state()
    radar = db.get_radar_state()
    refresh = db.get_refresh_states()
    cleanup = db.get_cleanup_status()
    profile = db.get_profile()
    filters = db.get_view_filters()
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
            f"- LinkedIn Radar: {radar.get('status')} (Interval: {radar.get('interval_seconds')}s)\n"
            f"- Dismissals: {dismissals_count}\n"
            f"- Cleanup Grace: {cleanup.get('grace_hours')}h"
        )

    msg = (
        f"JobHunter Status:\n"
        f"- Workspace: {home_dir}\n"
        f"{method_summary}\n"
        f"- Active Profile: {profile.get('_profile_name')} ({profile.get('target_title') or 'Candidate'})"
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
            "workspace_home": str(home_dir),
            "session_state": session_state,
            "radar_state": radar,
            "refresh_states": refresh,
            "cleanup_status": cleanup,
            "active_profile": profile.get("_profile_name"),
            "view_filters": filters,
            "total_jobs": total_jobs,
            "active_jobs": active_jobs,
            "signals_count": signals_count,
            "fresh_signals": fresh_signals,
            "contacts_count": contacts_count,
            "outreach_count": outreach_count,
            "today_sent": today_sent,
            "remaining_cap": remaining_cap,
        }
    }


def jh_feedback(job_id: str = "", action: str = "dismiss", reason: str = "",
                exclude_company: str = "", exclude_keyword: str = "", session_id: str = "default") -> dict[str, Any]:
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

    # Exclusions
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


def jh_find_contacts(signal_id_or_company: str, target_role: str = "") -> dict[str, Any]:
    """Modern Step 12: Find up to 3 decision makers (Found, Pattern, Guess) or alternative routes for outreach."""
    from . import contacts
    return contacts.jh_find_contacts(signal_id_or_company, target_role=target_role)


def jh_build_resume(company: str, role: str, signal_id: str = "") -> dict[str, Any]:
    """Modern Step 13: Build or retrieve single grounded 1-page PDF resume <= 200 KB in jobmcp/outputs/."""
    from . import email_drafter
    return email_drafter.jh_build_resume(company=company, role=role, signal_id=signal_id)


def jh_draft_email(contact_id: str, signal_id: str = "", resume_path: str = "") -> dict[str, Any]:
    """Modern Step 13: Draft human 3-4 line outreach email with slop linting and attachment policy."""
    from . import email_drafter
    return email_drafter.jh_draft_email(contact_id=contact_id, signal_id=signal_id, resume_path=resume_path)
