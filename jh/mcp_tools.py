"""MCP tool and resource definitions for JobHunter.

Exposes all resume parsing, job searching, composite scoring, tailoring,
application tracking, and utility capabilities to AI assistants via FastMCP.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import ats, db, exporters, pipeline, refit, resume_parser, scoring, sources, tracker, workspace
from .filestore import FileStore
from .util import clean_text, now_iso

log = logging.getLogger("jobhunter.mcp")


def _resolve_profile(name_or_id: str = "", filestore: Optional[FileStore] = None) -> dict[str, Any]:
    """Resolve a resume profile by variant name, ID, or fallback to active profile."""
    # 1. If explicit identifier provided
    if name_or_id:
        target = name_or_id.strip().lower()
        profiles = db.list_resume_profiles()
        for p in profiles:
            if p["id"].lower() == target or p["name"].lower() == target:
                return db.get_profile(p["id"])
        # Partial match on name
        for p in profiles:
            if target in p["name"].lower():
                return db.get_profile(p["id"])

    # 2. Check active resume in filestore
    if filestore:
        active_name = filestore.get_active_resume()
        if active_name:
            profiles = db.list_resume_profiles()
            for p in profiles:
                if p["name"].lower() == active_name.lower() or p["id"].lower() == active_name.lower():
                    return db.get_profile(p["id"])

    # 3. Fallback to active in DB
    prof = db.get_profile()
    return prof


def _slugify(text: str) -> str:
    """Make filename-safe slug from company and role."""
    clean = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", clean)[:40] or "job"


def register_tools_and_resources(mcp: Any, filestore: FileStore, workspace_path: str | Path) -> None:
    """Register all 24 JobHunter tools and 6 resources on the FastMCP instance."""
    ws = Path(workspace_path).resolve()

    # =========================================================================
    # 1. RESUME TOOLS
    # =========================================================================

    @mcp.tool()
    def scan_resumes(subpath: str = "") -> dict[str, Any]:
        """Scan repository workspace for resume files (PDF, DOCX, TXT), parse them, and update profiles.

        Args:
            subpath: Optional subdirectory path relative to workspace to scan.

        Returns:
            Dict containing list of discovered resumes, parsed count, and active resume.
        """
        try:
            target_dir = (ws / subpath) if subpath else ws
            found = workspace.discover_resumes(target_dir)
            parsed_list = []

            for item in found:
                try:
                    prof = workspace.parse_resume_variant(item["path"])
                    p_id = f"var_{_slugify(item['name'])}"
                    prof["_profile_id"] = p_id
                    prof["_profile_name"] = item["name"]
                    db.save_profile(prof, profile_id=p_id)
                    parsed_list.append({
                        "name": item["name"],
                        "file": item["filename"],
                        "path": item["path"],
                        "skills_count": len(prof.get("skills", [])),
                        "target_title": prof.get("target_title", ""),
                        "status": "parsed",
                    })
                except Exception as e:
                    parsed_list.append({
                        "name": item["name"],
                        "file": item["filename"],
                        "path": item["path"],
                        "status": f"error: {str(e)}",
                    })

            # Check/set active resume
            active = filestore.get_active_resume()
            if not active and parsed_list:
                first_valid = next((p["name"] for p in parsed_list if p.get("status") == "parsed"), "")
                if first_valid:
                    filestore.set_active_resume(first_valid)
                    active = first_valid

            return {
                "success": True,
                "found_count": len(found),
                "parsed_count": sum(1 for p in parsed_list if p.get("status") == "parsed"),
                "active_resume": active or "None",
                "resumes": parsed_list,
                "hint": "Put resumes in the repository root or resumes/ folder as PDF, DOCX, or TXT." if not found else "",
            }
        except Exception as e:
            log.exception("Error in scan_resumes: %s", e)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_resume(name: str = "") -> dict[str, Any]:
        """Get parsed resume profile details for a specific variant or the active resume.

        Args:
            name: Variant name or ID. If omitted, returns active resume profile.

        Returns:
            Full profile JSON including contact info, skills, experience, education, and audit report.
        """
        try:
            profile = _resolve_profile(name, filestore)
            if profile.get("_is_empty"):
                return {
                    "success": False,
                    "message": "No resume found. Run 'scan_resumes' or add a resume to your repository.",
                    "profile": profile,
                }
            return {
                "success": True,
                "profile_id": profile.get("_profile_id", "master"),
                "profile_name": profile.get("_profile_name", "Default Resume"),
                "profile": profile,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def list_resumes() -> dict[str, Any]:
        """List all available resume variants with their skills count, target role, and active status.

        Returns:
            List of resume variants with summary metadata.
        """
        try:
            profiles = db.list_resume_profiles()
            active_name = filestore.get_active_resume()
            return {
                "success": True,
                "count": len(profiles),
                "active_resume": active_name or (profiles[0]["name"] if profiles else "None"),
                "resumes": profiles,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_active_resume(name: str) -> dict[str, Any]:
        """Set which resume variant is used as the active profile for searches and job match scoring.

        Args:
            name: Name or ID of the resume variant to activate.

        Returns:
            Confirmation and activated profile summary.
        """
        try:
            target = name.strip()
            profiles = db.list_resume_profiles()
            match = next((p for p in profiles if p["id"].lower() == target.lower() or p["name"].lower() == target.lower()), None)
            if not match:
                match = next((p for p in profiles if target.lower() in p["name"].lower()), None)

            if not match:
                return {
                    "success": False,
                    "error": f"Resume variant '{name}' not found. Available: {[p['name'] for p in profiles]}",
                }

            db.set_active_resume_profile(match["id"])
            filestore.set_active_resume(match["name"])

            return {
                "success": True,
                "message": f"Active resume set to '{match['name']}'.",
                "active_resume": match["name"],
                "target_title": match.get("target_title", ""),
                "skills_count": match.get("skills_count", 0),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def parse_resume_file(path: str) -> dict[str, Any]:
        """Parse a specific resume file on disk into a structured profile without saving it permanently.

        Args:
            path: Absolute or workspace-relative path to a resume file (.pdf, .docx, .txt).

        Returns:
            Extracted profile data and validation report.
        """
        try:
            fp = Path(path)
            if not fp.is_absolute():
                fp = ws / fp
            if not fp.is_file():
                return {"success": False, "error": f"File not found: {fp}"}

            profile = workspace.parse_resume_variant(fp)
            return {
                "success": True,
                "filename": fp.name,
                "profile": profile,
                "report": profile.get("_report", {}),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 2. JOB SEARCH TOOLS
    # =========================================================================

    @mcp.tool()
    def search_jobs(
        query: str = "",
        location: str = "",
        work_mode: str = "Any",
        min_score: int = 0,
        force_refresh: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Search across all major job sources (LinkedIn, Indeed, ZipRecruiter, RemoteOK, etc.) and score against active resume.

        Args:
            query: Job title or keywords to search (e.g. 'Senior Python Engineer'). Defaults to resume target title.
            location: City, state, or country (e.g. 'San Francisco, CA' or 'Remote').
            work_mode: Work mode filter: 'Remote', 'Hybrid', 'Onsite', or 'Any'.
            min_score: Minimum match score threshold (0-100).
            force_refresh: Force live scraping instead of returning cached results.
            limit: Maximum number of jobs to return.

        Returns:
            List of matching jobs with full match scores, salary estimates, and source telemetry.
        """
        try:
            profile = _resolve_profile("", filestore)
            res = pipeline.search(
                query=query,
                location=location,
                work_mode=work_mode,
                min_score=min_score,
                profile=profile,
                force_refresh=force_refresh,
                limit=limit,
            )
            jobs = res.get("jobs", [])
            query_key = f"{query or profile.get('target_title', '')}_{location}_{work_mode}".strip("_")
            filestore.cache_jobs(jobs, query_key=query_key)

            return {
                "success": True,
                "query": query or profile.get("target_title", ""),
                "location": location,
                "count": len(jobs),
                "jobs": jobs,
                "telemetry": res.get("telemetry", {}),
            }
        except Exception as e:
            log.exception("Error in search_jobs: %s", e)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_saved_jobs(
        category: str = "",
        seniority: str = "",
        work_mode: str = "",
        min_score: int = 0,
        sort: str = "score",
        limit: int = 50,
    ) -> dict[str, Any]:
        """Query previously found jobs stored in the local engine with 30-dimension filters.

        Args:
            category: Job category (e.g. 'Backend Engineer', 'Full Stack Developer', 'DevOps').
            seniority: Seniority level: 'Junior', 'Mid', 'Senior', 'Lead', 'Staff', 'Director'.
            work_mode: Work mode filter: 'Remote', 'Hybrid', 'Onsite'.
            min_score: Minimum match score (0-100).
            sort: Sort criteria: 'score', 'date', 'salary'.
            limit: Maximum number of jobs to return.

        Returns:
            Filtered jobs list matching criteria.
        """
        try:
            filters = {}
            if category:
                filters["category"] = category
            if seniority:
                filters["seniority"] = seniority
            if work_mode:
                filters["work_mode"] = work_mode
            if min_score:
                filters["min_score"] = min_score
            if sort:
                filters["sort"] = sort
            if limit:
                filters["limit"] = limit

            results = db.query_stored_jobs(filters)
            jobs = results.get("jobs", []) if isinstance(results, dict) else results
            return {
                "success": True,
                "count": len(jobs),
                "jobs": jobs,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_job_details(
        job_title: str,
        company: str,
        url: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Enrich a job posting with full description, skill extraction, and deep match scoring against active resume.

        Args:
            job_title: Exact or approximate job title.
            company: Company name.
            url: Optional URL of the job posting for deep scraping.
            description: Optional text of job description if available.

        Returns:
            Enriched job record with full description, required skills, and match score breakdown.
        """
        try:
            job = {
                "title": clean_text(job_title),
                "company": clean_text(company),
                "url": url,
                "description": description,
            }
            enriched = sources.enrich_job(job)
            profile = _resolve_profile("", filestore)
            if not profile.get("_is_empty"):
                scored = scoring.score_job(enriched, profile)
                enriched.update(scored)
                pipeline._rank_opportunity(enriched)
                pipeline.enrich_recommendation_insights(enriched, profile)

            enriched["enrichment_attempted"] = True
            enriched["enriched"] = True
            return {"success": True, "job": enriched}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_recommendations(limit: int = 15) -> dict[str, Any]:
        """Get top AI-ranked job recommendations specifically curated for the active resume profile.

        Args:
            limit: Maximum recommendations to return (default: 15).

        Returns:
            Ranked list of opportunities with fit reasons, missing skills, and insider company links.
        """
        try:
            profile = _resolve_profile("", filestore)
            if profile.get("_is_empty"):
                return {"success": False, "error": "Active resume profile is empty. Run scan_resumes first."}

            recs = pipeline.get_recommendations(profile=profile, limit=limit)
            return {
                "success": True,
                "count": len(recs),
                "recommendations": recs,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 3. SCORING & ANALYSIS TOOLS
    # =========================================================================

    @mcp.tool()
    def score_job(
        job_title: str,
        company: str = "",
        description: str = "",
        resume_name: str = "",
    ) -> dict[str, Any]:
        """Calculate 100-point composite match score between a job description and a resume profile.

        Args:
            job_title: Title of the target role.
            company: Company name.
            description: Full text or requirements of the job.
            resume_name: Optional name of the resume variant. Defaults to active resume.

        Returns:
            Score breakdown across skills overlap, title alignment, seniority level, and salary.
        """
        try:
            profile = _resolve_profile(resume_name, filestore)
            if profile.get("_is_empty"):
                return {"success": False, "error": "No resume profile available to score against."}

            job = {
                "title": job_title,
                "company": company,
                "description": description,
            }
            score_data = scoring.score_job(job, profile)
            return {
                "success": True,
                "job_title": job_title,
                "company": company,
                "resume_evaluated": profile.get("_profile_name", "Active Resume"),
                "score": score_data.get("score", 0),
                "breakdown": score_data,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def gap_report(
        job_title: str,
        company: str = "",
        description: str = "",
        resume_name: str = "",
    ) -> dict[str, Any]:
        """Generate a skill gap report identifying missing skills, transferable strengths, and an upskilling plan.

        Args:
            job_title: Target role title.
            company: Company name.
            description: Job requirements / description.
            resume_name: Optional resume variant to compare. Defaults to active resume.

        Returns:
            Missing required skills, matching strengths, recommendations, and saved report path.
        """
        try:
            profile = _resolve_profile(resume_name, filestore)
            if profile.get("_is_empty"):
                return {"success": False, "error": "No resume profile available."}

            job = {"title": job_title, "company": company, "description": description}
            report = refit.generate_gap_report(job, profile)

            # Save report to .jobhunter/output/reports/
            fname = f"{_slugify(company)}-{_slugify(job_title)}-gap.json"
            saved_path = filestore.save_output("reports", fname, report)

            return {
                "success": True,
                "job_title": job_title,
                "company": company,
                "report_file": saved_path,
                "gap_report": report,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def ats_audit(
        job_title: str,
        company: str = "",
        description: str = "",
        resume_name: str = "",
    ) -> dict[str, Any]:
        """Audit resume readiness against Applicant Tracking Systems (ATS) for a specific job.

        Args:
            job_title: Target role title.
            company: Target company name.
            description: Job description requirements.
            resume_name: Resume variant to audit. Defaults to active resume.

        Returns:
            ATS score (0-100), keyword match coverage, metric bullet checks, and structure checklist.
        """
        try:
            profile = _resolve_profile(resume_name, filestore)
            if profile.get("_is_empty"):
                return {"success": False, "error": "No resume profile available for ATS audit."}

            job = {"title": job_title, "company": company, "description": description}
            audit = ats.compute_ats_audit(profile, job)

            fname = f"{_slugify(company)}-{_slugify(job_title)}-ats.json"
            saved_path = filestore.save_output("reports", fname, audit)

            return {
                "success": True,
                "ats_score": audit.get("ats_score", 0),
                "report_file": saved_path,
                "audit": audit,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def compare_resumes(
        job_title: str,
        company: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Compare all available resume variants against a target job to determine the best-fit resume.

        Args:
            job_title: Target role title.
            company: Company name.
            description: Job requirements or posting text.

        Returns:
            Ranked list of resume variants with match scores, pros, and recommendation.
        """
        try:
            profiles = db.get_live_profiles()
            if not profiles or (len(profiles) == 1 and profiles[0].get("_is_empty")):
                return {"success": False, "error": "No resume profiles available to compare."}

            job = {"title": job_title, "company": company, "description": description}
            comparison = refit.compare_variants_against_job(job, profiles)
            return {
                "success": True,
                "job_title": job_title,
                "company": company,
                "comparison": comparison,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 4. TAILORING & GENERATION TOOLS
    # =========================================================================

    @mcp.tool()
    def tailor_resume(
        job_title: str,
        company: str,
        description: str,
        archetype: str = "standard",
        resume_name: str = "",
    ) -> dict[str, Any]:
        """Generate a truthfully tailored resume optimized for a specific job without fabricating facts.

        Args:
            job_title: Target job title.
            company: Target company name.
            description: Job posting text and requirements.
            archetype: Tailoring angle ('standard', 'executive', 'technical', 'startup').
            resume_name: Resume variant to base tailoring on. Defaults to active resume.

        Returns:
            Tailored resume JSON, ATS score improvement, and saved file location.
        """
        try:
            profile = _resolve_profile(resume_name, filestore)
            if profile.get("_is_empty"):
                return {"success": False, "error": "No resume profile available to tailor."}

            job = {"title": job_title, "company": company, "description": description}
            before_ats = ats.compute_ats_audit(profile, job).get("ats_score", 0)

            tailored_prof = refit.refine_resume_for_job(job, profile)
            after_ats = ats.compute_ats_audit(tailored_prof, job).get("ats_score", 0)

            fname = f"{_slugify(company)}-{_slugify(job_title)}.json"
            saved_path = filestore.save_output("tailored", fname, tailored_prof)

            return {
                "success": True,
                "job_title": job_title,
                "company": company,
                "ats_before": before_ats,
                "ats_after": after_ats,
                "saved_to": saved_path,
                "tailored_resume": tailored_prof,
            }
        except Exception as e:
            log.exception("Error tailoring resume: %s", e)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def cover_letter(
        job_title: str,
        company: str,
        description: str = "",
        tone: str = "direct",
        angle: str = "direct_impact",
        resume_name: str = "",
    ) -> dict[str, Any]:
        """Generate a targeted, high-impact cover letter grounded entirely in verifiable resume experience.

        Args:
            job_title: Target job title.
            company: Target company name.
            description: Job description and requirements.
            tone: Tone of the letter ('direct', 'enthusiastic', 'formal', 'conversational').
            angle: Pitch angle ('direct_impact', 'growth_story', 'technical_depth', 'problem_solver').
            resume_name: Resume variant to use. Defaults to active resume.

        Returns:
            Cover letter text, pitch structure breakdown, and saved file path.
        """
        try:
            profile = _resolve_profile(resume_name, filestore)
            if profile.get("_is_empty"):
                return {"success": False, "error": "No resume profile available."}

            job = {"title": job_title, "company": company, "description": description}
            result = refit.generate_cover_pitch(job, profile, tone=tone, angle=angle)

            letter_text = result.get("letter") or result.get("cover_letter") or str(result)
            fname = f"{_slugify(company)}-{_slugify(job_title)}.txt"
            saved_path = filestore.save_output("cover-letters", fname, letter_text)

            return {
                "success": True,
                "job_title": job_title,
                "company": company,
                "saved_to": saved_path,
                "cover_letter": letter_text,
                "pitch_structure": result,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def interview_prep(
        job_title: str,
        company: str = "",
        description: str = "",
        resume_name: str = "",
    ) -> dict[str, Any]:
        """Generate tailored interview prep questions (technical, behavioral, situational) with suggested STAR answers.

        Args:
            job_title: Target job title.
            company: Target company name.
            description: Job description.
            resume_name: Resume variant to prepare for. Defaults to active resume.

        Returns:
            Questions categorized by type with custom-tailored STAR talking points.
        """
        try:
            profile = _resolve_profile(resume_name, filestore)
            if profile.get("_is_empty"):
                return {"success": False, "error": "No resume profile available."}

            job = {"title": job_title, "company": company, "description": description}
            prep = refit.generate_interview_prep(job, profile)

            fname = f"{_slugify(company)}-{_slugify(job_title)}-prep.json"
            saved_path = filestore.save_output("reports", fname, prep)

            return {
                "success": True,
                "job_title": job_title,
                "company": company,
                "saved_to": saved_path,
                "prep": prep,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def outreach_message(
        job_title: str,
        company: str = "",
        description: str = "",
        message_type: str = "all",
        resume_name: str = "",
    ) -> dict[str, Any]:
        """Generate high-converting recruiter and hiring manager outreach messages (LinkedIn, Email, InMail).

        Args:
            job_title: Target role title.
            company: Company name.
            description: Job context.
            message_type: 'all', 'linkedin_connect', 'inmail', or 'email'.
            resume_name: Resume variant. Defaults to active resume.

        Returns:
            Ready-to-send outreach messages with character count checks.
        """
        try:
            profile = _resolve_profile(resume_name, filestore)
            if profile.get("_is_empty"):
                return {"success": False, "error": "No resume profile available."}

            job = {"title": job_title, "company": company, "description": description}
            outreach = refit.generate_recruiter_outreach(job, profile, message_type=message_type)
            return {
                "success": True,
                "job_title": job_title,
                "company": company,
                "messages": outreach,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 5. APPLICATION TRACKING TOOLS
    # =========================================================================

    @mcp.tool()
    def track_application(
        company: str,
        title: str,
        status: str = "applied",
        url: str = "",
        notes: str = "",
        follow_up_date: str = "",
    ) -> dict[str, Any]:
        """Record or track a job application in the pipeline with automated follow-up reminders.

        Args:
            company: Company applied to.
            title: Job title.
            status: Stage: 'saved', 'applied', 'interview', 'offer', 'rejected'. Default 'applied'.
            url: Job application URL or link.
            notes: Personal notes, referral names, or thoughts.
            follow_up_date: Target follow-up date (YYYY-MM-DD). If omitted, auto-calculated.

        Returns:
            The tracked application record with tracking ID.
        """
        try:
            import time
            app_id = f"app-{int(time.time() * 1000)}"
            app_data = {
                "id": app_id,
                "company": company,
                "title": title,
                "status": status,
                "url": url,
                "notes": notes,
                "follow_up_date": follow_up_date,
            }
            # Save into SQLite tracker
            tracker.upsert_application(app_data)
            # Sync to filestore JSON
            saved_json = filestore.save_application(app_data)

            return {
                "success": True,
                "message": f"Application at '{company}' tracked as '{status}'.",
                "application": saved_json,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def list_applications(status: str = "") -> dict[str, Any]:
        """List tracked job applications, filterable by status, with stage duration and overdue follow-up alerts.

        Args:
            status: Optional stage filter: 'saved', 'applied', 'interview', 'offer', 'rejected'.

        Returns:
            List of application records with stage history and days in stage.
        """
        try:
            apps = tracker.list_applications()
            if status:
                st = status.strip().lower()
                apps = [a for a in apps if a.get("status", "").lower() == st]

            return {
                "success": True,
                "count": len(apps),
                "applications": apps,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def update_application(
        id: str,
        status: str = "",
        notes: str = "",
        follow_up_date: str = "",
    ) -> dict[str, Any]:
        """Update the status or notes of an existing job application.

        Args:
            id: Application ID (e.g. 'app-123').
            status: New stage: 'saved', 'applied', 'interview', 'offer', 'rejected'.
            notes: Updated notes or status summary.
            follow_up_date: Next follow-up reminder date.

        Returns:
            Updated application record with appended stage history.
        """
        try:
            existing_apps = tracker.list_applications()
            match = next((a for a in existing_apps if str(a.get("id")) == str(id)), None)
            if not match:
                stored_apps = filestore.load_applications()
                match = next((a for a in stored_apps if str(a.get("id")) == str(id)), None)

            if not match:
                return {"success": False, "error": f"Application '{id}' not found."}

            merged = dict(match)
            updates: dict[str, Any] = {}
            if status:
                merged["status"] = status
                updates["status"] = status
            if notes:
                merged["notes"] = notes
                updates["notes"] = notes
            if follow_up_date:
                merged["follow_up_date"] = follow_up_date
                updates["follow_up_date"] = follow_up_date

            tracker.upsert_application(merged)
            updated_json = filestore.update_application(id, updates)

            return {
                "success": True,
                "message": f"Application '{id}' updated.",
                "application": updated_json or merged,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def application_stats() -> dict[str, Any]:
        """Get application funnel metrics: applied, interview, offer conversion rates and overdue reminders.

        Returns:
            Funnel metrics, active applications count, and overdue follow-up count.
        """
        try:
            stats = tracker.funnel_stats()
            apps = tracker.list_applications()
            overdue = [a for a in apps if a.get("overdue")]

            return {
                "success": True,
                "funnel": stats,
                "total_tracked": len(apps),
                "overdue_count": len(overdue),
                "overdue_applications": [
                    {"id": a["id"], "company": a["company"], "title": a["title"], "follow_up": a["follow_up_date"]}
                    for a in overdue
                ],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 6. UTILITY TOOLS
    # =========================================================================

    @mcp.tool()
    def export_resume(format: str = "txt", resume_name: str = "") -> dict[str, Any]:
        """Export a resume profile to TXT, DOCX, PDF, or HTML format.

        Args:
            format: Target format: 'txt', 'docx', 'pdf', 'html'.
            resume_name: Variant name to export. Defaults to active resume.

        Returns:
            Path to exported file and export status.
        """
        try:
            profile = _resolve_profile(resume_name, filestore)
            if profile.get("_is_empty"):
                return {"success": False, "error": "No resume profile available to export."}

            fmt = format.strip().lower()
            var_name = profile.get("_profile_name", "Resume")
            clean_name = _slugify(var_name)

            if fmt == "txt":
                content = exporters.to_txt(profile)
                out_path = filestore.save_output("reports", f"{clean_name}.txt", content)
            elif fmt == "html":
                content = exporters.to_html(profile)
                out_path = filestore.save_output("reports", f"{clean_name}.html", content)
            elif fmt == "docx":
                raw_bytes = exporters.to_docx(profile)
                target_file = filestore.output_dir / "reports" / f"{clean_name}.docx"
                target_file.write_bytes(raw_bytes)
                out_path = str(target_file.resolve())
            elif fmt == "pdf":
                raw_bytes = exporters.to_pdf(profile)
                target_file = filestore.output_dir / "reports" / f"{clean_name}.pdf"
                target_file.write_bytes(raw_bytes)
                out_path = str(target_file.resolve())
            else:
                return {"success": False, "error": f"Unsupported format: {format}. Use txt, docx, pdf, or html."}

            return {
                "success": True,
                "format": fmt,
                "exported_to": out_path,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def source_health() -> dict[str, Any]:
        """Check the status, latency, and operational health of all 15+ job board scrapers.

        Returns:
            Status report for LinkedIn, Indeed, ZipRecruiter, RemoteOK, and other native sources.
        """
        try:
            report = pipeline.health_report()
            filestore.save_sources_health(report)
            return {
                "success": True,
                "sources": report,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def configure(key: str = "", value: str = "") -> dict[str, Any]:
        """Read or update JobHunter configuration settings and AI provider preferences.

        Args:
            key: Setting key to view or update (e.g. 'work_mode', 'min_salary', 'active_resume').
            value: Optional new value to set. If omitted, returns current value or full config.

        Returns:
            Updated configuration dictionary.
        """
        try:
            if key and value is not None and value != "":
                cfg = filestore.save_config(key, value)
                return {
                    "success": True,
                    "updated_key": key,
                    "value": value,
                    "config": cfg,
                }
            cfg = filestore.load_config()
            return {
                "success": True,
                "config": cfg,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 7. MCP RESOURCES
    # =========================================================================

    @mcp.resource("jobhunter://resumes")
    def get_resumes_resource() -> str:
        """List of all parsed resume variants in the workspace."""
        try:
            profiles = db.list_resume_profiles()
            return json.dumps(profiles, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.resource("jobhunter://resumes/{name}")
    def get_resume_variant_resource(name: str) -> str:
        """Full parsed profile JSON for a specific resume variant."""
        try:
            profile = _resolve_profile(name, filestore)
            return json.dumps(profile, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.resource("jobhunter://applications")
    def get_applications_resource() -> str:
        """All tracked job applications with stage history."""
        try:
            apps = tracker.list_applications()
            return json.dumps(apps, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.resource("jobhunter://jobs/latest")
    def get_latest_jobs_resource() -> str:
        """Most recent cached job search results."""
        try:
            jobs = filestore.get_latest_cached_jobs()
            return json.dumps(jobs, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.resource("jobhunter://config")
    def get_config_resource() -> str:
        """Current JobHunter configuration and preferences."""
        try:
            cfg = filestore.load_config()
            cfg["workspace"] = str(ws)
            cfg["ai_provider"] = refit.get_active_ai_config()
            return json.dumps(cfg, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.resource("jobhunter://sources")
    def get_sources_resource() -> str:
        """Health and operational availability of all job board sources."""
        try:
            report = pipeline.health_report()
            return json.dumps(report, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
