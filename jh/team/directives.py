"""Directives: the written brief the CEO gives an employee for one task.

A directive has an objective, inputs, limits and a definition of done. It also carries a
ready-to-use prompt, built from the employee's role prompt plus the brief. Employees that run as
code receive the same directive, so the report can show exactly what each one was told to do.
A model-written task (a cover letter, say) is handed out as a work order that contains this prompt.
"""

from __future__ import annotations

from typing import Any

from . import roles

STANDARD_LIMITS = (
    "Use only facts that tools or the candidate evidence returned.",
    "If a fact is missing, say it is missing. Do not guess.",
    "Name the job id for every job you mention.",
    "Your work goes to the Reviewer before it reaches the client.",
)


def make(employee: str, objective: str, *, inputs: dict[str, Any] | None = None, limits: list[str] | None = None,
         done_when: str = "", workspace: str = "", with_prompt: bool = False) -> dict[str, Any]:
    role = roles.ROSTER[employee]
    d: dict[str, Any] = {
        "to": employee, "title": role.title, "objective": objective,
        "inputs": {k: v for k, v in (inputs or {}).items() if v not in (None, "", [], {})},
        "limits": list(STANDARD_LIMITS) + list(limits or []),
        "done_when": done_when or "The result is complete and the Reviewer has checked it.",
    }
    if with_prompt:
        d["prompt"] = render(d, workspace)
    return d


def render(directive: dict[str, Any], workspace: str = "") -> str:
    """Role prompt plus the brief, as plain text a model can follow."""
    lines = [roles.role_prompt(directive["to"], workspace), "", "TASK", directive["objective"], ""]
    if directive.get("inputs"):
        lines.append("INPUTS")
        lines += [f"- {k}: {v}" for k, v in directive["inputs"].items()]
        lines.append("")
    lines.append("LIMITS")
    lines += [f"- {x}" for x in directive["limits"]]
    lines += ["", "DONE WHEN", directive["done_when"]]
    return "\n".join(lines)


def brief(directive: dict[str, Any]) -> dict[str, str]:
    """A one-line view for reports."""
    return {"to": directive["title"], "objective": directive["objective"]}
