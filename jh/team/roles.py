"""The roster: who is on the team, what each person owns, and the prompt each one works from.

Every MCP tool of the server belongs to exactly one employee. The CEO is the only one the client
talks to. Role prompts live in ``prompts/team/<key>.md``. A file with the same name in
``<workspace>/prompts/team/`` replaces the built-in one, so the client can retune any employee.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Role:
    key: str
    title: str
    mission: str
    tools: tuple[str, ...]


ROSTER: dict[str, Role] = {r.key: r for r in (
    Role("ceo", "CEO", "Talks to the client, plans the work, briefs the team, and reports only what was verified.", ()),
    Role("scout", "Head of Talent Scouting",
         "Finds open jobs from every fitting source, including small and regional employers.",
         ("search_jobs", "get_saved_jobs", "get_recommendations", "get_job_details", "add_job_source", "remove_job_source",
          "list_job_sources", "discover_job_source", "source_health")),
    Role("analyst", "Market Analyst", "Measures fit, finds gaps, audits how an applicant tracking system reads the resume.",
         ("score_job", "score_fit", "gap_report", "ats_audit", "compare_resumes")),
    Role("writer", "Document Writer", "Writes resumes, cover letters, screening answers and outreach from real facts only.",
         ("tailor_resume", "rewrite_resume", "cover_letter", "solve_screening_questions", "prepare_application", "export_resume",
          "outreach_message", "get_playbook")),
    Role("coach", "Interview Coach", "Prepares interviews, scores practice answers, plans skills to learn.",
         ("interview_prep", "evaluate_mock_interview", "skill_roadmap")),
    Role("ops", "Chief of Staff", "Keeps resumes, preferences and applications in order. Tracks follow-ups.",
         ("scan_resumes", "list_resumes", "get_resume", "set_active_resume", "parse_resume_file", "get_preferences",
          "set_preferences", "configure", "track_application", "add_to_tracker", "list_applications", "update_application",
          "application_stats", "daily_digest", "follow_up_message")),
    Role("reviewer", "Reviewer", "Checks every job and document against stored data and resume evidence. Can block any work.",
         ("verify_draft", "get_evidence")),
)}

_OWNER = {tool: key for key, role in ROSTER.items() for tool in role.tools}

_FALLBACK = {key: f"You are the {role.title}. {role.mission} Use only facts that tools return. Say plainly when data is missing."
             for key, role in ROSTER.items()}


def owner_of(tool: str) -> Optional[str]:
    return _OWNER.get(tool)


def specialists() -> list[str]:
    return [k for k in ROSTER if k != "ceo"]


def role_prompt(key: str, workspace: str | Path = "") -> str:
    """The prompt text for one role. A workspace file wins over the built-in file."""
    if key not in ROSTER:
        raise KeyError(key)
    bases = []
    if workspace:
        bases.append(Path(workspace) / "prompts" / "team")
    bases.append(Path(__file__).resolve().parent.parent.parent / "prompts" / "team")
    for base in bases:
        p = base / f"{key}.md"
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    return text
            except OSError:
                continue
    return _FALLBACK[key]


def describe(workspace: str | Path = "", with_prompts: bool = False) -> list[dict]:
    out = []
    for key, role in ROSTER.items():
        row = {"key": key, "title": role.title, "mission": role.mission, "tools": list(role.tools)}
        if with_prompts:
            row["prompt"] = role_prompt(key, workspace)
        out.append(row)
    return out
