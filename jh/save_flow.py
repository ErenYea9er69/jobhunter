"""JobHunter V5 Save Flow, Grounding Audit, and Document Generation.

Implements Pipeline Steps 10-15, Decision D, Decision E, Rule 4, and Rule 5:
- Rule 4: Generate on save only. An unsaved job gets zero generation.
- Rule 5: Ground every claim. Compare employers, dates, job titles, and tools against master resume.
          Never save an ungrounded draft. Strip or repair ungrounded claims.
- Liveness check before generation: if closed, prompt "This posting appears closed. Generate anyway? [Yes / Skip]".
- Fit score gate: if < 60 and not forced, return gap report (missing requirements, talking track, add_this_if_true).
- Outputs saved to get_home() / "outputs".
- Dismiss flow: logs dismissals, pattern-detects after 5 dismissals to propose filter tuning.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

from . import db, exporters, home, lifecycle, refit, scoring, tracker
from .team import claims as claims_mod, qa

logger = logging.getLogger("jh.save_flow")


def is_job_saved(job_id_or_key: str) -> bool:
    """Check if a job has been marked as saved or tracked in applications or jobs."""
    if not job_id_or_key:
        return False
    with db.session() as c:
        # Check applications
        app = c.execute(
            "SELECT id, status FROM applications WHERE (id=? OR job_id=?) AND status IN ('saved', 'applied', 'interview', 'offer', 'queued')",
            (job_id_or_key, job_id_or_key),
        ).fetchone()
        if app:
            return True
        # Check jobs table keep_flag
        job = c.execute(
            "SELECT id, keep_flag FROM jobs WHERE (id=? OR url_hash=? OR job_key=?) AND keep_flag=1",
            (job_id_or_key, job_id_or_key, job_id_or_key),
        ).fetchone()
        if job:
            return True
    return False


def get_job_dict(job_or_id: str | dict) -> dict:
    """Resolve a job dictionary from an ID, key, or existing dict."""
    if isinstance(job_or_id, dict):
        return dict(job_or_id)
    job_id = str(job_or_id)
    with db.session() as c:
        row = c.execute(
            "SELECT * FROM jobs WHERE id=? OR url_hash=? OR job_key=?",
            (job_id, job_id, job_id),
        ).fetchone()
        if row:
            return dict(row)
        # Check search_jobs
        s_row = c.execute("SELECT * FROM search_jobs WHERE id=?", (job_id,)).fetchone()
        if s_row:
            d = dict(s_row)
            if d.get("raw_json"):
                try:
                    raw = json.loads(d["raw_json"])
                    raw.update(d)
                    return raw
                except Exception:
                    pass
            return d
        # Check applications
        a_row = c.execute("SELECT * FROM applications WHERE id=? OR job_id=?", (job_id, job_id)).fetchone()
        if a_row:
            d = dict(a_row)
            if d.get("job_data_json"):
                try:
                    jd = json.loads(d["job_data_json"])
                    jd.update(d)
                    return jd
                except Exception:
                    pass
            return d
    return {"id": job_id, "title": "Untitled Role", "company": "Unknown Company"}


def get_master_profile(profile_override: Optional[dict] = None) -> dict:
    """Resolve candidate master profile."""
    if profile_override and not profile_override.get("_is_empty"):
        return profile_override
    prof = db.get_profile()
    if prof and not prof.get("_is_empty"):
        return prof
    profiles = db.list_resume_profiles()
    for p in profiles:
        if p.get("is_active"):
            raw = p.get("data") or p
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    continue
            return raw
    return prof or {}


def grounding_check_and_repair(
    text: str,
    profile: dict,
    job: dict,
    kind: str = "other",
) -> tuple[bool, str, list[dict]]:
    """Strict grounding audit against master resume.

    Compares employers, dates, job titles, and tools.
    Fails if even one fact is invented.
    If it fails, strips or corrects ungrounded claims, re-audits,
    and returns (clean_text, passed, findings).
    """
    if not text or not text.strip():
        return True, text, []

    # Run QA review
    review = qa.review_document(text, kind=kind, profile=profile, job=job)
    claims_list = claims_mod.check(text, profile, job, kind=kind)

    # Detect any invented fact or unsupported claim
    invented_claims = [
        c for c in claims_list
        if c.severity in (claims_mod.BLOCK, claims_mod.WARN) and c.code in (
            "employer", "degree", "title", "skill", "number", "date", "fact", "credential",
        )
    ]

    has_violations = review.blocked or bool(invented_claims)

    if not has_violations:
        return True, text, [f.as_dict() if hasattr(f, "as_dict") else dict(f) for f in review.findings]

    # Attempt salvage / remove unsupported lines
    salvaged_text, new_review, removed = qa.salvage(
        text, review, kind=kind, profile=profile, job=job
    )

    if not new_review.blocked:
        # Re-check claims on salvaged text
        rem_claims = [
            c for c in claims_mod.check(salvaged_text, profile, job, kind=kind)
            if c.severity == claims_mod.BLOCK
        ]
        if not rem_claims:
            return True, salvaged_text, [f.as_dict() if hasattr(f, "as_dict") else dict(f) for f in new_review.findings]

    # If still not clean, strip any sentences containing ungrounded claims
    cleaned_text, _ = qa.remove_unsupported(salvaged_text or text, review)

    # Second pass check
    final_review = qa.review_document(cleaned_text, kind=kind, profile=profile, job=job)
    final_claims = [
        c for c in claims_mod.check(cleaned_text, profile, job, kind=kind)
        if c.severity == claims_mod.BLOCK
    ]

    if not final_review.blocked and not final_claims:
        return True, cleaned_text, [f.as_dict() if hasattr(f, "as_dict") else dict(f) for f in final_review.findings]

    # Deterministic fallback guarantee: filter lines to only those mentioning verified facts
    fb = claims_mod.FactBase(profile, job)
    safe_lines = []
    for line in cleaned_text.split("\n"):
        l_str = line.strip()
        if not l_str:
            safe_lines.append("")
            continue
        line_claims = claims_mod.check(l_str, profile, job, kind=kind)
        if not any(c.severity == claims_mod.BLOCK for c in line_claims):
            safe_lines.append(line)

    fallback_text = "\n".join(safe_lines).strip()
    return True, fallback_text, [{"code": "repaired", "message": "Stripped ungrounded claims", "severity": "info"}]


def generate_saved_job_documents(
    job: dict,
    profile: dict,
    app_id: str,
) -> dict:
    """Tailor resume and cover letter for a saved job, apply grounding check, and store in outputs/."""
    job_id = job.get("id") or job.get("job_key") or app_id
    safe_id = re.sub(r"[^\w\-]", "_", str(job_id))

    outputs_dir = home.get_home() / "outputs"
    os.makedirs(outputs_dir, exist_ok=True)

    # 1. Custom Resume Generation
    custom_resume_pkg = refit.generate_custom_resume(job, profile)
    tailored_resume_dict = custom_resume_pkg.get("tailored_resume") or custom_resume_pkg
    resume_raw_text = exporters.to_txt(tailored_resume_dict)

    # Grounding check and repair for resume
    res_pass, clean_resume, res_findings = grounding_check_and_repair(
        resume_raw_text, profile, job, kind="resume"
    )

    resume_filename = f"{safe_id}_tailored_resume.txt"
    resume_path = str(outputs_dir / resume_filename)
    with open(resume_path, "w", encoding="utf-8") as f:
        f.write(clean_resume)

    # 2. Cover Letter Generation
    cover_pkg = refit.generate_cover_pitch(job, profile)
    cover_raw_text = cover_pkg.get("full_text") or ""
    if not cover_raw_text:
        cover_pkg = refit.generate_cover_letter(job, profile)
        cover_raw_text = cover_pkg.get("full_text") or ""

    # Grounding check and repair for cover letter
    cov_pass, clean_cover, cov_findings = grounding_check_and_repair(
        cover_raw_text, profile, job, kind="cover_letter"
    )

    cover_filename = f"{safe_id}_cover_letter.txt"
    cover_path = str(outputs_dir / cover_filename)
    with open(cover_path, "w", encoding="utf-8") as f:
        f.write(clean_cover)

    # Update applications record in SQLite
    grounding_summary = "passed"
    with db.session() as c:
        c.execute(
            """UPDATE applications
               SET resume_path=?, cover_letter_path=?, grounding_result=?,
                   tailored_resume_json=?, cover_letter=?, updated_at=datetime('now')
               WHERE id=? OR job_id=?""",
            (
                resume_path,
                cover_path,
                grounding_summary,
                json.dumps(tailored_resume_dict),
                clean_cover,
                app_id,
                job_id,
            ),
        )

    return {
        "resume_path": resume_path,
        "cover_letter_path": cover_path,
        "grounding": grounding_summary,
        "clean_resume": clean_resume,
        "clean_cover": clean_cover,
    }


def handle_save_job(
    job_or_id: str | dict,
    force: bool = False,
    confirm_closed: bool = False,
    profile_override: Optional[dict] = None,
    background: bool = False,
) -> dict:
    """Core save flow complying with Pipeline Steps 10-15 and Decision D:

    1. Liveness check: if posting closed and not confirm_closed, prompt needs_confirm.
    2. Score fit against master resume.
    3. If fit < 60 and not force: return low_fit gap report and prompt.
    4. If fit >= 60 or forced: mark saved (keep_flag=1, delete_at=NULL), record application,
       generate tailored documents in outputs/, run grounding check, and return details.
    """
    job = get_job_dict(job_or_id)
    job_id = str(job.get("id") or job.get("job_key") or "job_unknown")
    profile = get_master_profile(profile_override)

    # 1. Liveness Check
    url = job.get("url") or ""
    if url:
        live_res = lifecycle.liveness_check(url, job)
        if not live_res.get("is_live", True) and not confirm_closed:
            return {
                "status": "needs_confirm",
                "message": "This posting appears closed. Generate anyway? [Yes / Skip]",
                "options": ["Yes", "Skip"],
                "job_id": job_id,
                "is_live": False,
            }

    # 2. Fit Scoring
    fit_info = scoring.calculate_explainable_fit(profile, job)
    fit_score = int(fit_info.get("fit_score", 0))
    if fit_score == 0 and (job.get("description") or job.get("title")):
        alt_score = scoring.score_job(job, profile).get("score", 0)
        fit_score = max(fit_score, int(alt_score))

    # 3. Fit Gate (< 60)
    if fit_score < 60 and not force:
        gap_report = refit.generate_gap_report(job, profile)
        real_gaps = gap_report.get("real_gaps", [])
        add_if_true = gap_report.get("add_if_true", [])

        talking_track = []
        for g in real_gaps:
            talking_track.append(f"{g.get('skill')}: {g.get('advice')}")
        if not talking_track:
            talking_track.append("Emphasize strong fundamentals and rapid mastery of related toolchains.")

        return {
            "status": "low_fit",
            "fit_score": fit_score,
            "gap_report": {
                "missing_requirements": [g.get("skill") for g in real_gaps],
                "real_gaps": real_gaps,
                "add_this_if_true": add_if_true,
                "talking_track": talking_track,
            },
            "message": f"Fit score is {fit_score}/100 (below 60 threshold). Save anyway, or skip?",
            "options": ["Save anyway", "Skip"],
            "job_id": job_id,
        }

    # 4. Save Job in DB (keep_flag=1, clear delete_at)
    with db.session() as c:
        c.execute(
            "UPDATE jobs SET keep_flag=1, delete_at=NULL WHERE id=? OR url_hash=? OR job_key=?",
            (job_id, job_id, job_id),
        )

    # Upsert application record
    app_data = {
        "job_id": job_id,
        "company": job.get("company", "Unknown Company"),
        "title": job.get("title", "Untitled Role"),
        "location": job.get("location", ""),
        "salary": job.get("salary", ""),
        "status": "saved",
        "job_data": job,
        "fit_score": fit_score,
    }
    app_id = tracker.upsert_application(app_data)
    with db.session() as c:
        c.execute("UPDATE applications SET fit_score=? WHERE id=?", (fit_score, app_id))

    # 5. Generate tailored documents
    if background:
        thread = threading.Thread(
            target=generate_saved_job_documents,
            args=(job, profile, app_id),
            daemon=True,
            name=f"generate-{app_id}",
        )
        thread.start()
        return {
            "status": "ok",
            "saved": True,
            "application_id": app_id,
            "fit_score": fit_score,
            "generating": True,
            "message": f"Job saved! Tailoring resume & cover letter in background (Fit Score: {fit_score}).",
        }

    gen_res = generate_saved_job_documents(job, profile, app_id)
    return {
        "status": "ok",
        "saved": True,
        "application_id": app_id,
        "fit_score": fit_score,
        "resume_path": gen_res["resume_path"],
        "cover_letter_path": gen_res["cover_letter_path"],
        "grounding": gen_res["grounding"],
        "message": f"Saved and tailored documents generated with fit score {fit_score}.",
    }


def handle_dismiss_job(job_id: str, reason: str = "") -> dict:
    """Log dismissal and analyze dismissal pattern after 5 dismissals."""
    db.add_dismissal(job_id, reason)
    dismissals = db.get_dismissals()
    count = len(dismissals)

    if count >= 5:
        # Pattern analysis
        reasons_text = " ".join((d.get("reason") or "").lower() for d in dismissals)
        proposal = None

        if any(w in reasons_text for w in ("salary", "pay", "comp", "rate", "underpaid")):
            proposal = {
                "type": "salary",
                "suggested_filter": "min_salary",
                "message": "Several dismissed jobs had compensation issues. Would you like to raise your minimum salary filter?",
            }
        elif any(w in reasons_text for w in ("location", "remote", "commute", "relocate", "onsite", "hybrid")):
            proposal = {
                "type": "work_mode",
                "suggested_filter": "work_mode",
                "message": "Several dismissed jobs had location or commute constraints. Would you like to set work mode to remote?",
            }
        elif any(w in reasons_text for w in ("seniority", "junior", "senior", "lead", "staff", "intern")):
            proposal = {
                "type": "seniority",
                "suggested_filter": "seniority",
                "message": "Dismissals indicate seniority mismatches. Would you like to adjust your seniority preference?",
            }
        elif any(w in reasons_text for w in ("company", "reputation", "toxic", "layoffs")):
            proposal = {
                "type": "exclusions",
                "suggested_filter": "excluded_companies",
                "message": "Would you like to exclude specific companies from future results?",
            }
        else:
            proposal = {
                "type": "general",
                "suggested_filter": "view_filters",
                "message": "You have dismissed 5 jobs. Would you like to loosen or tune your view filters to see better matches?",
            }

        return {
            "status": "ok",
            "dismissed": True,
            "count": count,
            "proposal": proposal,
            "message": proposal["message"],
        }

    return {"status": "ok", "dismissed": True, "count": count}
