"""JobHunter MCP tools. Everything the server offers is a tool; there are no MCP prompts.

The registry is split by theme (resumes, preferences and sources, discovery, analysis,
documents, coaching, tracking, playbooks). Each tool returns the standard envelope from
``mcp_helpers``. Long text and big lists stay out of search results: ``search_jobs`` returns
compact cards and ``get_job_details`` returns one full record.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any

from . import (ats, company_directory, config, db, evidence, exporters, interview, pipeline, preferences,
               refit, regions, screening, source_registry, sources, tracker, workspace)
from . import mcp_helpers as h
from .filestore import OutputStore
from .mcp_helpers import Result, ToolError

def _tool_envelope(status: str = "ok", data: Optional[dict] = None, warnings: Optional[list] = None,
                   sources: Optional[list] = None, sources_used: Optional[list] = None, cid: str = "",
                   error: Optional[dict] = None) -> dict[str, Any]:
    src = sources if sources is not None else sources_used
    return h.envelope(status=status, data=data, warnings=warnings, sources=src, cid=cid, error=error)
from .resume_registry import ResumeRegistry
from .source_policy import sanitize_apply_url
from .util import clean_text, http_get_text

log = logging.getLogger("jobhunter.tools")

ARCHETYPE_ALIASES = {
    "standard": "technical_depth", "technical": "technical_depth", "technical_depth": "technical_depth",
    "startup": "startup_velocity", "startup_velocity": "startup_velocity",
    "executive": "enterprise_scale", "enterprise": "enterprise_scale", "enterprise_scale": "enterprise_scale",
}
PLAYBOOKS = ("resume_tailor", "cover_letter", "interview_prep", "screening_question_solver", "recruiter_outreach",
             "mock_interview_evaluator", "career_skill_roadmap", "application_follow_up")
EDITABLE_SETTINGS = {"ai_provider", "ai_model", "max_results", "max_scored_jobs", "min_salary", "active_resume"}
AI_PROVIDERS = {"auto", "deterministic", "gemini", "openai", "anthropic", "deepseek", "groq", "mistral", "ollama", "custom"}


def _slug(text: str) -> str:
    clean = re.sub(r"[^\w\s-]", "", text or "").strip().lower()
    return re.sub(r"[-\s]+", "-", clean)[:40] or "job"


def ai_status() -> dict[str, Any]:
    """The AI setup without any secret. Keys are reported only as present or missing."""
    cfg = refit.get_active_ai_config()
    return {"provider": cfg.get("provider"), "model": cfg.get("model"), "api_key_present": bool(cfg.get("key")),
            "mode": "deterministic engine" if cfg.get("provider") == "deterministic" else "LLM-assisted",
            "note": "Keys are read from environment variables and are never accepted or returned by tools."}


def register_tools_and_resources(mcp: Any, store: OutputStore, workspace_path: str | Path) -> None:
    ws = Path(workspace_path).resolve()
    tool = h.make_tool_decorator(mcp)
    registry = ResumeRegistry(ws)

    def inside_workspace(p: str) -> Path:
        target = Path(p)
        target = (target if target.is_absolute() else ws / target).resolve()
        try:
            target.relative_to(ws)
        except ValueError:
            raise ToolError(f"Access denied: '{p}' is outside the workspace.", code="forbidden")
        return target

    # ===================================================================== 1. RESUMES

    @tool
    def scan_resumes(subpath: str = "") -> dict[str, Any]:
        """Find resume files (PDF, DOCX, TXT) in the workspace, parse them, and make them available as resume variants.

        Args:
            subpath: Optional folder inside the workspace to scan. Default is the whole workspace.
        """
        target = inside_workspace(subpath) if subpath else ws
        found = workspace.discover_resumes(target)
        parsed = []
        for item in found:
            try:
                prof = workspace.parse_resume_variant(item["path"])
                pid = f"var_{_slug(item['name'])}"
                prof["_profile_id"], prof["_profile_name"] = pid, item["name"]
                db.save_profile(prof, profile_id=pid)
                parsed.append({"name": item["name"], "file": item["filename"], "skills": len(prof.get("skills", [])),
                               "target_title": prof.get("target_title", ""), "years_of_experience": prof.get("years_of_experience", 0),
                               "status": "parsed"})
            except Exception as e:
                parsed.append({"name": item["name"], "file": item["filename"], "status": f"error: {str(e)[:120]}"})
        ok = [p for p in parsed if p["status"] == "parsed"]
        active = registry.get_active_variant()
        if ok and not active:
            active = ok[0]["name"]
            registry.set_active_variant(active)
            match = next((p for p in db.list_resume_profiles() if p["name"] == active), None)
            if match:
                db.set_active_resume_profile(match["id"])
        warnings = [] if found else ["No resume files found. Add a PDF, DOCX or TXT resume to the workspace root or a resumes/ folder."]
        return Result({"found": len(found), "parsed": len(ok), "active_resume": active or "none", "resumes": parsed},
                      warnings, status="ok" if (ok or not found) else "partial")

    @tool
    def list_resumes() -> dict[str, Any]:
        """List resume variants with target role, skill count and which one is active."""
        profiles = db.list_resume_profiles()
        active = next((p["name"] for p in profiles if p.get("is_active")), None) or registry.get_active_variant()
        return {"count": len(profiles), "active_resume": active or "none", "resumes": profiles}

    @tool
    def get_resume(name: str = "") -> dict[str, Any]:
        """Return a parsed resume (contact, skills, experience, education). Personal preferences are applied on top.

        Args:
            name: Variant name or id. Empty means the active resume.
        """
        p = h.resolve_profile(name)
        return {"profile_id": p.get("_profile_id", "master"), "profile_name": p.get("_profile_name", "Default Resume"), "profile": p}

    @tool
    def set_active_resume(name: str) -> dict[str, Any]:
        """Choose which resume variant searches and scoring use.

        Args:
            name: Variant name or id.
        """
        target = name.strip().lower()
        profiles = db.list_resume_profiles()
        match = next((p for p in profiles if p["id"].lower() == target or p["name"].lower() == target), None) \
            or next((p for p in profiles if target in p["name"].lower()), None)
        if not match:
            raise ToolError(f"Resume '{name}' not found.", hint=f"Available: {[p['name'] for p in profiles]}")
        db.set_active_resume_profile(match["id"])
        registry.set_active_variant(match["name"])
        return {"active_resume": match["name"], "target_title": match.get("target_title", ""), "skills": match.get("skills_count", 0)}

    @tool
    def parse_resume_file(path: str) -> dict[str, Any]:
        """Parse one resume file into a profile without saving it.

        Args:
            path: File path inside the workspace (.pdf, .docx, .txt).
        """
        fp = inside_workspace(path)
        if not fp.is_file():
            raise ToolError(f"File not found: {fp.name}", code="not_found")
        profile = workspace.parse_resume_variant(fp)
        return {"filename": fp.name, "profile": profile, "report": profile.get("_report", {})}

    # ===================================================================== 2. PREFERENCES AND SOURCES

    def _source_plan(prefs: dict, profile: dict) -> list[dict]:
        targets = regions.resolve_targets(prefs, profile, "")
        remote_ok = regions.wants_remote(prefs, profile)
        out = []
        for s in sources.SEARCH_SOURCES:
            configured = s.configured() if hasattr(s, "configured") else True
            skip = source_registry.skip_reason(s.name, prefs, targets, remote_ok, configured)
            avail = s.available()
            will_run = skip is None and avail
            why = skip[1] if skip else ("" if avail else s.unavailable_reason())
            out.append({"source": s.name, "will_run": will_run, "reason": why})
        return out

    @tool
    def get_preferences() -> dict[str, Any]:
        """Show your personal search preferences and which sources they enable.

        Preferences cover where you want to work, work mode, salary floor, excluded keywords and companies,
        dream companies, company focus, languages, and which sources run.
        """
        prefs = preferences.load()
        prefs.pop("_updated_at", None)
        profile = h.resolve_profile(require=False, overlay=False)
        targets = regions.resolve_targets(prefs, profile, "")
        plan = _source_plan(prefs, profile)
        hints = []
        if not targets:
            hints.append("Set target_countries (for example [\"Tunisia\", \"France\"]) so each search uses the right local sources.")
        if not prefs.get("target_titles") and not profile.get("target_title"):
            hints.append("Set target_titles, or add a resume, so searches know which roles to look for.")
        return {"preferences": prefs, "defaults_in_use": preferences.is_default(prefs),
                "resolved_target_countries": [regions.country_name(c) for c in targets],
                "sources": {"will_run": [s["source"] for s in plan if s["will_run"]],
                            "skipped": [{"source": s["source"], "why": s["reason"]} for s in plan if not s["will_run"]]},
                "valid_values": {"work_mode": list(preferences.WORK_MODES), "company_focus": list(preferences.COMPANY_FOCUS),
                                 "search_depth": list(preferences.SEARCH_DEPTH), "job_types": list(preferences.JOB_TYPES),
                                 "seniority": list(preferences.SENIORITY)},
                "hints": hints}

    @tool
    def set_preferences(updates: dict, merge_lists: bool = False) -> dict[str, Any]:
        """Change personal search preferences. Only the keys you pass change.

        Keys: home_country, target_countries, cities, work_mode, include_worldwide_remote, open_to_relocation,
        needs_visa_sponsorship, languages, target_titles, min_salary, salary_currency, job_types, seniority,
        excluded_keywords, excluded_companies, dream_companies, company_focus (any | avoid_big_names | only_big_names),
        max_age_days, search_depth (quick | standard | deep), enabled_sources, disabled_sources.
        Use add_job_source for custom feeds, career pages and watched companies.

        Args:
            updates: Object of preference names and new values, for example {"target_countries": ["Tunisia", "France"], "company_focus": "avoid_big_names"}.
            merge_lists: When true, list values are added to the stored lists instead of replacing them.
        """
        try:
            saved, warnings = preferences.save(updates, merge_lists=merge_lists)
        except preferences.PreferenceError as e:
            raise ToolError(str(e), hint="Call get_preferences to see valid keys and values.")
        profile = h.resolve_profile(require=False, overlay=False)
        saved.pop("_updated_at", None)
        targets = [regions.country_name(c) for c in regions.resolve_targets(saved, profile, "")]
        return Result({"saved": {k: saved[k] for k in updates if k in saved}, "target_countries_resolved": targets}, warnings)

    @tool
    def list_job_sources() -> dict[str, Any]:
        """List every job source with where it works, whether it runs for you, plus your watched companies, feeds and career pages."""
        prefs = preferences.load()
        profile = h.resolve_profile(require=False, overlay=False)
        plan = {p["source"]: p for p in _source_plan(prefs, profile)}
        catalog = []
        for c in source_registry.catalog():
            p = plan.get(c["name"], {})
            catalog.append({**c, "will_run": p.get("will_run", False), "reason": p.get("reason", "")})
        return {"sources": catalog, "companies": company_directory.list_companies(),
                "custom_feeds": prefs.get("custom_feeds", []), "career_pages": prefs.get("career_pages", []),
                "job_sites": prefs.get("job_sites", []),
                "how_to_add": "add_job_source(kind='company' | 'feed' | 'career_page' | 'site', value=...). Not sure which? Call discover_job_source(url) first."}

    @tool
    def add_job_source(kind: str, value: str, name: str = "", target_role: str = "", force: bool = False) -> dict[str, Any]:
        """Add a place to look for jobs: a company, a feed, or a company career page.

        kind 'company': value is a company name (the board is detected) or its careers URL (Greenhouse, Lever, Ashby,
        Workable, SmartRecruiters, Recruitee, Personio, Teamtailor, BambooHR, Breezy). Every open role is searched.
        kind 'feed': value is an RSS, Atom or JSON feed URL, for example a regional job board's feed.
        kind 'career_page': value is a company careers page URL (ATS links or schema.org job data are read).
        kind 'site': value is a small or regional job board, or any site that publishes schema.org job data. Job pages are
        found through the sitemap and page links. robots.txt is respected. Use discover_job_source first when unsure.

        Args:
            kind: company, feed, career_page or site.
            value: Company name or URL.
            name: Optional display name.
            target_role: Optional role to focus on for a company.
            force: Add a feed or page even when a test read finds no jobs.
        """
        kind = kind.strip().lower().replace("-", "_")
        value = value.strip()
        if not value:
            raise ToolError("value is required.")
        if kind == "company":
            is_url = value.lower().startswith("http")
            try:
                res = company_directory.add_company(name=name or ("" if is_url else value), url=value if is_url else "",
                                                    target_role=target_role)
            except ValueError as e:
                raise ToolError(str(e), code="not_found")
            sample = []
            try:
                jobs = company_directory.fetch_board(res["board_type"], res["slug"], res["company"], ttl=0)
                sample = [j["title"] for j in jobs[:5]]
                res["open_jobs"] = len(jobs)
            except Exception as e:
                res["open_jobs"] = 0
                res["test_read_error"] = str(e)[:120]
            res["sample_titles"] = sample
            warn = []
            if res.get("auto_detected") and res.get("alternatives"):
                warn.append("Several boards matched this name. Check sample_titles; if wrong, remove it and add the careers URL instead.")
            return Result(res, warn)
        if kind in ("feed", "career_page", "site"):
            key = {"feed": "custom_feeds", "career_page": "career_pages", "site": "job_sites"}[kind]
            from .sources import feeds, local
            entry = {"name": name, "url": value}
            try:
                if kind == "feed":
                    count = len(feeds.parse_feed(http_get_text(value, retries=0, timeout=12)))
                elif kind == "site":
                    count = len(local.read_site(entry, "", max_pages=8, source="Job Sites"))
                else:
                    count = len(feeds.CareerPages()._one(entry, ""))
            except PermissionError as e:
                raise ToolError(str(e), code="forbidden", hint="The site asks robots not to read it. force=true does not override that.")
            except Exception as e:
                if not force:
                    raise ToolError(f"Could not read {value}: {str(e)[:140]}", code="unreachable", hint="Check the URL, or pass force=true to add it anyway.")
                count = 0
            if count == 0 and not force:
                raise ToolError("The test read found no jobs at that URL.", code="empty",
                                hint="For a career page, try the company's ATS link or add it as kind='company'. Pass force=true to keep it anyway.")
            try:
                preferences.save({key: [entry]}, merge_lists=True)
            except preferences.PreferenceError as e:
                raise ToolError(str(e))
            return {"added": kind, "url": value, "jobs_found_in_test": count}
        raise ToolError("kind must be 'company', 'feed', 'career_page' or 'site'.")

    @tool
    def discover_job_source(url: str) -> dict[str, Any]:
        """Find out how a website's jobs can be read: ATS board, feed, sitemap or schema.org job data. Adds nothing.

        Use this on a small regional job board or a company site before add_job_source. It reads at most a few pages
        and respects robots.txt.

        Args:
            url: Home page or jobs page of the site.
        """
        if not url.strip().lower().startswith(("http://", "https://")):
            raise ToolError("url must start with http:// or https://.")
        from .sources import local
        return local.discover_site(url.strip())

    @tool
    def remove_job_source(kind: str, value: str) -> dict[str, Any]:
        """Remove a watched company, custom feed or career page.

        Args:
            kind: company, feed, career_page or site.
            value: Company name, id or slug for a company; the URL or name for a feed, page or site.
        """
        kind = kind.strip().lower().replace("-", "_")
        if kind == "company":
            return {"removed": company_directory.remove_company(value)}
        if kind in ("feed", "career_page", "site"):
            key = {"feed": "custom_feeds", "career_page": "career_pages", "site": "job_sites"}[kind]
            prefs = preferences.load()
            keep = [e for e in prefs.get(key, []) if value.lower() not in (e["url"].lower(), (e.get("name") or "").lower())]
            removed = len(prefs.get(key, [])) - len(keep)
            if removed:
                preferences.save({key: keep})
            return {"removed": bool(removed)}
        raise ToolError("kind must be 'company', 'feed', 'career_page' or 'site'.")

    @tool
    def source_health() -> dict[str, Any]:
        """Show how each source did in the last search: results, errors, paused sources, and company board coverage."""
        prefs = preferences.load()
        profile = h.resolve_profile(require=False, overlay=False)
        plan = {p["source"]: p for p in _source_plan(prefs, profile)}
        rows = []
        for s in sources.SEARCH_SOURCES:
            last = pipeline.LAST_SOURCE_STATUS.get(s.name) or next((v for k, v in pipeline.LAST_SOURCE_STATUS.items() if k.startswith(s.name)), None)
            rows.append({"source": s.name, "will_run": plan[s.name]["will_run"], "why_not": plan[s.name]["reason"],
                         "paused_after_failures": sources.breaker_open(s.name),
                         "last_state": (last or {}).get("state", "not run yet"), "last_count": (last or {}).get("count", 0),
                         "last_error": (last or {}).get("error", ""), "last_run": (last or {}).get("at", "")})
        return {"sources": rows, "company_boards": company_directory.list_companies(), "ai": ai_status()}

    # ===================================================================== 3. DISCOVERY

    @tool
    def search_jobs(query: str = "", location: str = "", work_mode: str = "", min_score: int = 0, limit: int = 25,
                    company_focus: str = "", refresh: bool = False) -> dict[str, Any]:
        """Search every enabled source for your region and return compact job cards ranked by fit.

        Which sources run depends on your preferences (set_preferences): target countries, remote, disabled sources,
        company boards, custom feeds and career pages. Use get_job_details for the full text of one job.

        Args:
            query: Job title or keywords. Empty uses your resume or target_titles.
            location: City or country. Empty uses your target countries.
            work_mode: Remote, Hybrid or Onsite. Empty uses your preference.
            min_score: Only return jobs with a fit score at or above this value (0 to 100).
            limit: Cards to return, 1 to 100.
            company_focus: any, avoid_big_names or only_big_names. Empty uses your preference.
            refresh: Skip cached source results.
        """
        profile = h.resolve_profile(overlay=False, require=False)
        if profile.get("_is_empty") and not query:
            raise ToolError("No resume and no query.", code="no_resume", hint="Pass a query, or add a resume and call scan_resumes.")
        famous = {"avoid_big_names": "hide", "only_big_names": "only", "any": "all"}.get(company_focus, "all")
        limit = h.clamp(limit, 1, 100)
        res = pipeline.search(query=query, location=location, work_mode=work_mode or "Any", min_score=h.clamp(min_score, 0, 100),
                              famous_mode=famous, profile=profile, force_refresh=refresh, limit=limit)
        statuses = [{"source": s["source"], "state": s["state"], "count": s.get("count", 0), "ms": s.get("ms", 0),
                     **({"error": s["error"]} if s.get("error") and s["state"] not in ("ok", "cached") else {})}
                    for s in res["sources"] if s["state"] != "disabled" or s.get("error")]
        warnings = list(res.get("warnings", []))
        if not res["count"]:
            if res["coverage"]["sources_with_results"] == 0:
                warnings.append("No source returned jobs. Check source_health, your network, or widen the query.")
            else:
                warnings.append("Sources returned jobs but your filters removed them. Try lower min_score, a wider location, or company_focus 'any'.")
        data = {"query": res["query"], "count": res["count"], "total_found": res["total_stored"], "jobs": h.cards(res["jobs"], limit),
                "coverage": res["coverage"], "sources": statuses, "elapsed_ms": res["elapsed_ms"],
                "fallback_notice": res.get("fallback_notice", ""), "profile_used": bool(not res.get("profile_empty"))}
        return Result(data, warnings, [s["source"] for s in statuses if s["state"] in ("ok", "cached")], "partial" if res.get("partial") else "ok")

    @tool
    def get_saved_jobs(category: str = "", seniority: str = "", work_mode: str = "", min_score: int = 0,
                       sort: str = "score", limit: int = 25) -> dict[str, Any]:
        """Query jobs already found by earlier searches, without any network call. Returns compact cards.

        Args:
            category: Role family such as Backend, Frontend, DevOps, Data, Mobile, Security.
            seniority: Junior, Mid, Senior, Lead.
            work_mode: Remote, Hybrid or Onsite.
            min_score: Minimum fit score.
            sort: score, date or salary.
            limit: Cards to return, 1 to 100.
        """
        limit = h.clamp(limit, 1, 100)
        filters = {k: v for k, v in {"category": category, "seniority": seniority, "work_mode": work_mode,
                                     "min_score": min_score or None, "sort": sort, "limit": limit}.items() if v}
        results = db.query_stored_jobs(filters)
        jobs = results.get("jobs", []) if isinstance(results, dict) else results
        return {"count": len(jobs), "jobs": h.cards(jobs, limit)}

    @tool
    def get_job_details(job_id: str = "", job_title: str = "", company: str = "", url: str = "", description: str = "",
                        full_description: bool = False) -> dict[str, Any]:
        """Return the full record of one job: description, requirements, salary, contacts, fit breakdown and apply link.

        Give a job_id from search results. Or pass job_title and company (plus url or description) for a job found elsewhere.
        The page is read again when the stored description is thin.

        Args:
            job_id: Id from search_jobs, get_saved_jobs or get_recommendations.
            job_title: Title, when there is no job_id.
            company: Company, when there is no job_id.
            url: Posting URL, used to read the full page.
            description: Pasted description text.
            full_description: Return the whole description instead of the first 6000 characters.
        """
        job = h.build_job(job_id, job_title, company, description, url)
        if url and not job.get("url"):
            job["url"] = url
        warnings = []
        if not job.get("enriched") or len(job.get("description", "")) < 500:
            try:
                job = sources.enrich_job(job)
            except Exception as e:
                warnings.append(f"Could not read the full posting: {str(e)[:100]}")
        profile = h.resolve_profile(require=False)
        if profile and not profile.get("_is_empty"):
            job = h.score_against(job, profile)
        job["enrichment_attempted"] = True
        if job_id:
            try:
                db.update_search_job(job)
            except Exception:
                pass
        desc, cut = h.clip(job.get("description", ""), 60000 if full_description else 6000)
        apply_url, w = sanitize_apply_url(job.get("direct_apply_url") or job.get("url", ""))
        warnings += w
        data = {**h.card(job, detail=True), "apply_url": apply_url, "description": desc, "description_truncated": cut,
                "responsibilities": (job.get("responsibilities") or [])[:12], "qualifications": (job.get("qualifications") or [])[:12],
                "preferred_qualifications": (job.get("preferred_qualifications") or [])[:10],
                "how_to_apply": job.get("how_to_apply", ""), "contact_email": job.get("contact_email", ""),
                "contact_website": job.get("contact_website", ""), "required_skills": job.get("required_skills", {}),
                "rationale": job.get("rationale", []), "company_url": job.get("company_url", ""),
                "apply_cost_note": job.get("apply_cost_note", ""), "possible_ghost_posting": bool(job.get("is_ghost_risk"))}
        return Result(data, warnings)

    @tool
    def get_recommendations(limit: int = 15) -> dict[str, Any]:
        """Top matches for your resume and preferences with no query needed. Uses stored jobs first.

        Args:
            limit: Cards to return, 1 to 50.
        """
        limit = h.clamp(limit, 1, 50)
        profile = h.resolve_profile()
        recs = pipeline.get_recommendations(profile=profile, limit=limit)
        jobs = recs.get("jobs") or recs.get("recommendations") or recs.get("top") or []
        extra = {k: v for k, v in recs.items() if k not in ("jobs", "recommendations", "top", "all_jobs") and isinstance(v, (str, int, float, bool))}
        return {"count": len(jobs), "jobs": h.cards(jobs, limit), **extra}

    # ===================================================================== 4. ANALYSIS

    def job_and_profile(job_id, job_title, company, description, resume_name, salary="", location="", url=""):
        profile = h.resolve_profile(resume_name)
        job = h.build_job(job_id, job_title, company, description, url, salary, location)
        return job, profile

    @tool
    def score_job(job_id: str = "", job_title: str = "", company: str = "", description: str = "", salary: str = "",
                  location: str = "", resume_name: str = "") -> dict[str, Any]:
        """Score how well your resume fits one job (0 to 100) with the full breakdown and matched or missing skills.

        Args:
            job_id: Id from search results. Or pass job_title, company and description for pasted text.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
            salary: Optional salary text. Read from the description when empty.
            location: Optional location for pasted text.
            resume_name: Resume variant. Empty means the active resume.
        """
        job, profile = job_and_profile(job_id, job_title, company, description, resume_name, salary, location)
        j = h.score_against(job, profile)
        return {**h.card(j, detail=True), "score": j.get("score"), "breakdown": j.get("score_breakdown", {}), "required_skills": j.get("required_skills", {}), "salary_annual_min": j.get("salary_annual_min"),
                "salary_annual_max": j.get("salary_annual_max"), "country": j.get("country"), "rationale": j.get("rationale", []),
                "confidence": j.get("confidence")}

    @tool
    def gap_report(job_id: str = "", job_title: str = "", company: str = "", description: str = "", resume_name: str = "") -> dict[str, Any]:
        """List which skills the job wants that your resume lacks, which are real gaps, and which you could add truthfully.

        Args:
            job_id: Id from search results. Or pass job_title, company and description.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
            resume_name: Resume variant. Empty means the active resume.
        """
        job, profile = job_and_profile(job_id, job_title, company, description, resume_name)
        report = refit.generate_gap_report(job, profile)
        report["saved_to"] = store.save_output("reports", f"{_slug(job.get('company', ''))}-{_slug(job.get('title', ''))}-gap.json", report)
        report["report_file"] = report["saved_to"]
        return report

    @tool
    def ats_audit(job_id: str = "", job_title: str = "", company: str = "", description: str = "", resume_name: str = "") -> dict[str, Any]:
        """Check how an applicant tracking system would read your resume for this job: keyword coverage, format risks, fixes.

        Args:
            job_id: Id from search results. Or pass job_title, company and description.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
            resume_name: Resume variant. Empty means the active resume.
        """
        job, profile = job_and_profile(job_id, job_title, company, description, resume_name)
        audit = ats.compute_ats_audit(profile, job)
        audit["saved_to"] = store.save_output("reports", f"{_slug(job.get('company', ''))}-{_slug(job.get('title', ''))}-ats.json", audit)
        audit["report_file"] = audit["saved_to"]
        return audit

    @tool
    def compare_resumes(job_id: str = "", job_title: str = "", company: str = "", description: str = "") -> dict[str, Any]:
        """Rank all your resume variants against one job and say which one to send.

        Args:
            job_id: Id from search results. Or pass job_title, company and description.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
        """
        job = h.build_job(job_id, job_title, company, description)
        profiles = [preferences.overlay_profile(p) for p in db.get_live_profiles()]
        if not profiles:
            raise ToolError("No resumes found.", code="no_resume", hint="Call scan_resumes first.")
        return refit.compare_variants_against_job(job, profiles)

    # ===================================================================== 5. DOCUMENTS

    def ledger_for(profile: dict):
        return evidence.build_ledger_from_profile(profile, source_file=profile.get("_profile_name", ""))

    def grounding(text: str, profile: dict, job: dict | None = None) -> dict[str, Any]:
        reqs = [q for q in (job or {}).get("qualifications", [])[:12]] or None
        res = evidence.verify_grounding(text, ledger_for(profile), profile, reqs).to_dict()
        flagged = [v for v in res.get("verdicts", []) if v.get("verdict") in ("unsupported", "needs_review")]
        return {"status": res.get("status"), "total_claims": res.get("total_claims"), "supported": res.get("supported"),
                "needs_review": res.get("needs_review"), "unsupported": res.get("unsupported"),
                "flagged_claims": flagged[:8], "honest_gaps": res.get("honest_gaps", [])[:8]}

    @tool
    def tailor_resume(job_id: str = "", job_title: str = "", company: str = "", description: str = "", archetype: str = "technical_depth",
                      resume_name: str = "", save: bool = True) -> dict[str, Any]:
        """Tailor your resume to a job without inventing facts. Reorders and rewords real content, then checks it against your evidence.

        Args:
            job_id: Id from search results. Or pass job_title, company and description.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
            archetype: technical_depth, startup_velocity or enterprise_scale.
            resume_name: Resume variant. Empty means the active resume.
            save: Write the result to .jobhunter/output/tailored.
        """
        arch = ARCHETYPE_ALIASES.get(archetype.strip().lower())
        if not arch:
            raise ToolError(f"Unknown archetype '{archetype}'.", hint=f"Use one of: {', '.join(sorted(set(ARCHETYPE_ALIASES.values())))}")
        job, profile = job_and_profile(job_id, job_title, company, description, resume_name)
        before = ats.compute_ats_audit(profile, job).get("ats_score", 0)
        result = refit.generate_custom_resume(job, profile, archetype=arch)
        tailored = result.get("tailored_resume") or {}
        if not tailored:
            raise ToolError("Tailoring produced no resume.", code="internal_error")
        after = ats.compute_ats_audit(tailored, job).get("ats_score", 0)
        text = exporters.to_txt(tailored)
        out = {"job": {"title": job.get("title"), "company": job.get("company")}, "archetype": arch, "ats_before": before, "ats_after": after,
               "grounding": grounding(text, profile, job), "tailored_resume": tailored,
               **{k: v for k, v in result.items() if k in ("changes", "summary", "executive_hook", "keywords_added", "notes")}}
        if save:
            base = f"{_slug(job.get('company', ''))}-{_slug(job.get('title', ''))}"
            out["saved_to"] = {"json": store.save_output("tailored", f"{base}.json", tailored), "text": store.save_output("tailored", f"{base}.txt", text)}
        return out

    @tool
    def cover_letter(job_id: str = "", job_title: str = "", company: str = "", description: str = "", tone: str = "direct",
                     angle: str = "direct_impact", resume_name: str = "", format: str = "txt") -> dict[str, Any]:
        """Write a short cover letter from your real experience, then check every claim against your evidence.

        Args:
            job_id: Id from search results. Or pass job_title, company and description.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
            tone: direct, warm or formal.
            angle: direct_impact, startup_velocity, technical_architect or executive_brief.
            resume_name: Resume variant. Empty means the active resume.
            format: txt, docx or pdf.
        """
        fmt = format.strip().lower()
        if fmt not in ("txt", "docx", "pdf"):
            raise ToolError("format must be txt, docx or pdf.")
        job, profile = job_and_profile(job_id, job_title, company, description, resume_name)
        pitch = refit.generate_cover_pitch(job, profile, tone=tone, angle=angle)
        letter = pitch.get("full_text") or ""
        if not letter:
            raise ToolError("No cover letter was produced.", code="internal_error")
        base = f"{_slug(job.get('company', ''))}-{_slug(job.get('title', ''))}"
        paths = {"text": store.save_output("cover-letters", f"{base}.txt", letter)}
        if fmt == "docx":
            paths["docx"] = store.save_bytes("cover-letters", f"{base}.docx", exporters.cover_letter_to_docx(letter, profile, job))
        elif fmt == "pdf":
            paths["pdf"] = store.save_bytes("cover-letters", f"{base}.pdf", exporters.cover_letter_to_pdf(letter, profile, job))
        return {"letter": letter, "word_count": len(letter.split()), "hook": pitch.get("hook", ""), "grounding": grounding(letter, profile, job), "saved_to": paths}

    @tool
    def solve_screening_questions(questions: list[str] | str, job_id: str = "", job_title: str = "", company: str = "",
                                  description: str = "", resume_name: str = "") -> dict[str, Any]:
        """Draft honest answers to application screening questions from your real resume facts. Unknowns are flagged, not invented.

        Args:
            questions: One question or a list of questions.
            job_id: Id from search results. Optional.
            job_title: Title for pasted text. Optional.
            company: Company for pasted text. Optional.
            description: Posting text. Optional.
            resume_name: Resume variant. Empty means the active resume.
        """
        qs = [questions] if isinstance(questions, str) else list(questions or [])
        qs = [clean_text(q) for q in qs if clean_text(q)]
        if not qs:
            raise ToolError("Give at least one question.")
        profile = h.resolve_profile(resume_name)
        job = h.build_job(job_id, job_title, company, description) if (job_id or job_title or description) else {}
        job_for_q = dict(job) if isinstance(job, dict) else {}
        if isinstance(job_for_q.get("required_skills"), dict):
            job_for_q["required_skills"] = list(job_for_q["required_skills"].keys())
        answers = [{"question": q, **screening.solve_screening_question(q, profile, job_for_q)} for q in qs[:20]]
        return {"count": len(answers), "answers": answers}

    @tool
    def prepare_application(job_id: str = "", job_title: str = "", company: str = "", description: str = "", archetype: str = "technical_depth",
                            resume_name: str = "", track: bool = True) -> dict[str, Any]:
        """One call that prepares an application: tailored resume, cover letter, recruiter message, interview prep, and a tracker entry.

        Args:
            job_id: Id from search results. Or pass job_title, company and description.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
            archetype: technical_depth, startup_velocity or enterprise_scale.
            resume_name: Resume variant. Empty means the active resume.
            track: Add the job to your applications as 'saved' with the documents attached.
        """
        arch = ARCHETYPE_ALIASES.get(archetype.strip().lower(), "technical_depth")
        job, profile = job_and_profile(job_id, job_title, company, description, resume_name)
        bundle = tracker.generate_one_click_bundle(job, profile, archetype=arch)
        base = f"{_slug(job.get('company', ''))}-{_slug(job.get('title', ''))}"
        letter = bundle.get("cover_letter") or ""
        tailored = bundle.get("tailored_resume") or {}
        saved = {}
        if tailored:
            saved["resume"] = store.save_output("tailored", f"{base}.json", tailored)
        if letter:
            saved["cover_letter"] = store.save_output("cover-letters", f"{base}.txt", letter)
        # The bundle always stages an application record. Merge it into an existing one for the same job, or drop it when not tracking.
        app_id = bundle.get("app_id", "")
        existing = next((a for a in tracker.list_applications() if a["id"] != app_id and a["company"].lower() == job.get("company", "").lower()
                         and a["title"].lower() == job.get("title", "").lower()), None)
        if existing and track:
            tracker.upsert_application(dict(existing, tailored_resume=tailored or existing.get("tailored_resume"), cover_letter=letter or existing.get("cover_letter", "")))
            tracker.delete_application(app_id)
            app_id = existing["id"]
        elif not track:
            tracker.delete_application(app_id)
            app_id = ""
        return {"application_id": app_id, "saved_to": saved, "grounding": grounding(letter, profile, job) if letter else {},
                "bundle": {k: v for k, v in bundle.items() if k not in ("tailored_resume", "refinement", "app_id", "ok", "success")}}

    @tool
    def verify_draft(text: str, resume_name: str = "", job_id: str = "") -> dict[str, Any]:
        """Check text you or the model wrote (resume bullets, cover letter, answers) against your real resume evidence.

        Each factual claim is marked supported, derived, needs_review or unsupported. Use it after any drafting step.

        Args:
            text: The draft to check.
            resume_name: Resume variant. Empty means the active resume.
            job_id: Optional job, so honest gaps against its requirements are listed.
        """
        if not text.strip():
            raise ToolError("text is required.")
        profile = h.resolve_profile(resume_name)
        job = h.build_job(job_id) if job_id else None
        return grounding(text, profile, job)

    @tool
    def get_evidence(resume_name: str = "", claim_type: str = "", limit: int = 60) -> dict[str, Any]:
        """List the facts extracted from your resume (employers, dates, skills, metrics). Generated documents may only use these.

        Args:
            resume_name: Resume variant. Empty means the active resume.
            claim_type: Optional filter such as skill, employer, role, metric, education.
            limit: Claims to return, 1 to 200.
        """
        profile = h.resolve_profile(resume_name)
        ledger = ledger_for(profile)
        claims = ledger.to_list()
        if claim_type:
            claims = [c for c in claims if str(c.get("claim_type", "")).lower() == claim_type.strip().lower()]
        return {"summary": ledger.summary(), "count": len(claims), "claims": claims[:h.clamp(limit, 1, 200)]}

    @tool
    def export_resume(format: str = "txt", resume_name: str = "") -> dict[str, Any]:
        """Export a resume to TXT, HTML, DOCX or PDF in .jobhunter/output/reports.

        Args:
            format: txt, html, docx or pdf.
            resume_name: Resume variant. Empty means the active resume.
        """
        fmt = format.strip().lower()
        profile = h.resolve_profile(resume_name)
        name = _slug(profile.get("_profile_name", "resume"))
        if fmt == "txt":
            path = store.save_output("reports", f"{name}.txt", exporters.to_txt(profile))
        elif fmt == "html":
            path = store.save_output("reports", f"{name}.html", exporters.to_html(profile))
        elif fmt == "docx":
            path = store.save_bytes("reports", f"{name}.docx", exporters.to_docx(profile))
        elif fmt == "pdf":
            path = store.save_bytes("reports", f"{name}.pdf", exporters.to_pdf(profile))
        else:
            raise ToolError("format must be txt, html, docx or pdf.")
        return {"format": fmt, "exported_to": path}

    # ===================================================================== 6. COACHING

    @tool
    def interview_prep(job_id: str = "", job_title: str = "", company: str = "", description: str = "", resume_name: str = "") -> dict[str, Any]:
        """Build interview prep for one job: likely questions, STAR stories from your real experience, and gaps to prepare for.

        Args:
            job_id: Id from search results. Or pass job_title, company and description.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
            resume_name: Resume variant. Empty means the active resume.
        """
        job, profile = job_and_profile(job_id, job_title, company, description, resume_name)
        prep = refit.generate_interview_prep(job, profile)
        prep["saved_to"] = store.save_output("interview-prep", f"{_slug(job.get('company', ''))}-{_slug(job.get('title', ''))}.json", prep)
        return prep

    @tool
    def outreach_message(job_id: str = "", job_title: str = "", company: str = "", description: str = "", message_type: str = "all",
                         resume_name: str = "") -> dict[str, Any]:
        """Draft a recruiter or hiring-manager message (LinkedIn note, email, follow-up) from your real experience.

        Args:
            job_id: Id from search results. Or pass job_title, company and description.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
            message_type: all, linkedin, email or follow_up.
            resume_name: Resume variant. Empty means the active resume.
        """
        job, profile = job_and_profile(job_id, job_title, company, description, resume_name)
        return refit.generate_recruiter_outreach(job, profile, message_type=message_type)

    @tool
    def evaluate_mock_interview(question: str, candidate_answer: str, role_level: str = "senior", rubric: str = "standard") -> dict[str, Any]:
        """Score a practice interview answer on ownership, metrics, technical depth and clarity, with a coached rewrite.

        Args:
            question: The interview question.
            candidate_answer: Your answer.
            role_level: entry, mid, senior, staff or lead.
            rubric: standard, strict or executive.
        """
        if not question.strip() or not candidate_answer.strip():
            raise ToolError("question and candidate_answer are required.")
        return interview.evaluate_mock_interview(question=question, candidate_answer=candidate_answer, role_level=role_level, rubric=rubric)

    @tool
    def skill_roadmap(job_id: str = "", resume_name: str = "", top_jobs: int = 15) -> dict[str, Any]:
        """Rank the skills worth learning next, by how many of your saved top jobs ask for them and you lack them.

        Args:
            job_id: Optional single job to focus on. Empty uses your best saved jobs.
            resume_name: Resume variant. Empty means the active resume.
            top_jobs: How many saved jobs to read when no job_id is given, 3 to 50.
        """
        profile = h.resolve_profile(resume_name)
        pool = [h.build_job(job_id)] if job_id else (db.query_stored_jobs({"sort": "score", "limit": h.clamp(top_jobs, 3, 50)}).get("jobs", []))
        if not pool:
            raise ToolError("No saved jobs to read.", code="not_found", hint="Run search_jobs first, or pass a job_id.")
        have = {s.lower() for s in profile.get("skills", [])}
        demand: dict[str, dict] = {}
        for j in pool:
            for skill, weight in (j.get("required_skills") or {}).items():
                if skill.lower() in have:
                    continue
                d = demand.setdefault(skill, {"skill": skill, "jobs_asking": 0, "required_in": 0, "examples": []})
                d["jobs_asking"] += 1
                d["required_in"] += 1 if weight >= 0.85 else 0
                if len(d["examples"]) < 3:
                    d["examples"].append(f"{j.get('title', '')} at {j.get('company', '')}")
        ranked = sorted(demand.values(), key=lambda d: (-d["required_in"], -d["jobs_asking"]))[:12]
        return {"based_on_jobs": len(pool), "priority_gaps": ranked,
                "next_step": "Call get_playbook('career_skill_roadmap') to turn these gaps into a two-week plan."}

    @tool
    def follow_up_message(app_id: str, action_type: str = "status_check_5days", notes: str = "", resume_name: str = "") -> dict[str, Any]:
        """Draft a follow-up message for a tracked application.

        Args:
            app_id: Application id from list_applications.
            action_type: status_check_5days, thank_you or offer_response.
            notes: Optional extra context to include.
            resume_name: Resume variant. Empty means the active resume.
        """
        profile = h.resolve_profile(resume_name)
        try:
            return tracker.generate_application_follow_up(app_id, action_type=action_type, notes=notes, profile=profile)
        except KeyError:
            raise ToolError(f"Application '{app_id}' not found.", code="not_found", hint="Call list_applications.")

    # ===================================================================== 7. TRACKING

    @tool
    def track_application(company: str = "", title: str = "", status: str = "applied", url: str = "", notes: str = "",
                          follow_up_date: str = "", job_id: str = "") -> dict[str, Any]:
        """Record an application. With a job_id the details are filled from the stored job. A repeat of the same job updates it.

        Args:
            company: Company, when there is no job_id.
            title: Job title, when there is no job_id.
            status: saved, applied, interview, offer or rejected.
            url: Posting or application link.
            notes: Referrals, contacts, thoughts.
            follow_up_date: YYYY-MM-DD. Calculated from the stage when empty.
            job_id: Id from search results.
        """
        job = db.get_job(job_id) if job_id else None
        if job_id and not job:
            raise ToolError(f"No stored job with id '{job_id}'.", code="not_found")
        company = company or (job or {}).get("company", "")
        title = title or (job or {}).get("title", "")
        if not (company and title):
            raise ToolError("Give a job_id, or both company and title.")
        if status not in tracker.STATUSES:
            raise ToolError(f"status must be one of {', '.join(tracker.STATUSES)}.")
        existing = next((a for a in tracker.list_applications() if a["company"].lower() == company.lower() and a["title"].lower() == title.lower()), None)
        data = {"id": existing["id"] if existing else None, "company": company, "title": title, "status": status,
                "url": url or (job or {}).get("direct_apply_url") or (job or {}).get("url", ""), "notes": notes or (existing or {}).get("notes", ""),
                "follow_up_date": follow_up_date or "", "location": (job or {}).get("location", ""), "salary": (job or {}).get("salary", ""),
                "job_id": job_id or None, "score": (job or {}).get("score") or 0}
        if existing:
            data["tailored_resume"], data["cover_letter"] = existing.get("tailored_resume"), existing.get("cover_letter", "")
        app_id = tracker.upsert_application(data)
        app = next(a for a in tracker.list_applications() if a["id"] == app_id)
        return {"application": {k: app[k] for k in ("id", "company", "title", "status", "follow_up_date", "url", "notes")},
                "updated_existing": bool(existing)}

    @tool
    def list_applications(status: str = "") -> dict[str, Any]:
        """List tracked applications with days in stage and overdue follow-ups.

        Args:
            status: Optional filter: saved, applied, interview, offer, rejected.
        """
        apps = tracker.list_applications()
        if status:
            apps = [a for a in apps if a["status"] == status.strip().lower()]
        slim = [{k: a[k] for k in ("id", "company", "title", "status", "follow_up_date", "overdue", "days_in_stage", "score", "url", "notes")} for a in apps]
        return {"count": len(slim), "applications": slim}

    @tool
    def update_application(id: str, status: str = "", notes: str = "", follow_up_date: str = "") -> dict[str, Any]:
        """Change an application's stage, notes or follow-up date.

        Args:
            id: Application id from list_applications.
            status: saved, applied, interview, offer or rejected.
            notes: New notes.
            follow_up_date: YYYY-MM-DD.
        """
        match = next((a for a in tracker.list_applications() if str(a["id"]) == str(id)), None)
        if not match:
            raise ToolError(f"Application '{id}' not found.", code="not_found", hint="Call list_applications.")
        if status and status not in tracker.STATUSES:
            raise ToolError(f"status must be one of {', '.join(tracker.STATUSES)}.")
        merged = dict(match)
        for k, v in (("status", status), ("notes", notes), ("follow_up_date", follow_up_date)):
            if v:
                merged[k] = v
        tracker.upsert_application(merged)
        return {"id": id, "status": merged["status"], "notes": merged["notes"], "follow_up_date": merged["follow_up_date"], "application": merged}

    @tool
    def application_stats() -> dict[str, Any]:
        """Funnel numbers: how many reached each stage, conversion rates, and overdue follow-ups."""
        apps = tracker.list_applications()
        overdue = [{"id": a["id"], "company": a["company"], "title": a["title"], "follow_up": a["follow_up_date"]} for a in apps if a["overdue"]]
        return {"funnel": tracker.funnel_stats(), "total_tracked": len(apps), "overdue_count": len(overdue), "overdue_applications": overdue}

    @tool
    def daily_digest(limit: int = 8, mark_seen: bool = True) -> dict[str, Any]:
        """What needs attention today: new matching jobs since the last digest, overdue follow-ups, upcoming interviews, next actions.

        New jobs come from earlier searches stored on this machine. The digest does not search the web itself.

        Args:
            limit: New jobs to list, 1 to 25.
            mark_seen: Mark the listed jobs as reported so the next digest shows only newer ones.
        """
        limit = h.clamp(limit, 1, 25)
        apps = tracker.list_applications()
        overdue = [{"id": a["id"], "company": a["company"], "title": a["title"], "follow_up": a["follow_up_date"]} for a in apps if a["overdue"]]
        interviews = [{"id": a["id"], "company": a["company"], "title": a["title"], "round": a.get("interview_round", ""), "date": a.get("interview_date", "")}
                      for a in apps if a["status"] == "interview"]
        with db.session() as c:
            rows = c.execute("""SELECT s.job_key FROM seen_jobs s JOIN search_jobs j ON j.job_key = s.job_key
                                WHERE s.digested = 0 AND j.is_active = 1 ORDER BY j.opportunity_score DESC, j.score DESC LIMIT ?""", (limit,)).fetchall()
            keys = [r["job_key"] for r in rows]
            backlog = c.execute("SELECT COUNT(*) AS n FROM seen_jobs WHERE digested = 0").fetchone()["n"]
            if mark_seen and keys:
                c.executemany("UPDATE seen_jobs SET digested = 1 WHERE job_key = ?", [(k,) for k in keys])
        new_jobs = [j for j in (db.get_job(k) for k in keys) if j]
        actions = [f"Follow up with {o['company']} about {o['title']} (due {o['follow_up']})." for o in overdue]
        actions += [f"Prepare for the {i['company']} interview: call interview_prep." for i in interviews]
        if new_jobs:
            top = new_jobs[0]
            actions.append(f"Review the top new match: {top.get('title')} at {top.get('company')} (fit {top.get('score')}).")
        if not actions:
            actions.append("Run search_jobs to look for new roles.")
        return {"date": datetime.date.today().isoformat(), "new_jobs": h.cards(new_jobs, limit), "new_jobs_waiting": max(0, backlog - len(keys)),
                "overdue_follow_ups": overdue, "upcoming_interviews": interviews, "total_active_applications": sum(1 for a in apps if a["status"] not in ("rejected",)),
                "recommended_actions": actions}

    # ===================================================================== 8. PLAYBOOKS (formerly MCP prompts)

    def playbook_text(name: str) -> str:
        for base in (ws / "prompts", Path(__file__).resolve().parent.parent / "prompts"):
            p = base / f"{name}.md"
            if p.is_file():
                raw = p.read_text(encoding="utf-8")
                m = re.search(r"```markdown\n(.*?)```", raw, re.S)
                return (m.group(1) if m else raw).strip()
        return f"No playbook text found for {name}."

    @tool
    def get_playbook(task: str, job_id: str = "", job_title: str = "", company: str = "", description: str = "",
                     resume_name: str = "", app_id: str = "") -> dict[str, Any]:
        """Get the writing instructions for a task plus the facts to write from, so the model can draft grounded text itself.

        Tasks: resume_tailor, cover_letter, interview_prep, screening_question_solver, recruiter_outreach,
        mock_interview_evaluator, career_skill_roadmap, application_follow_up.
        After drafting, call verify_draft on the text.

        Args:
            task: One of the task names above.
            job_id: Id from search results, when the task is about a job.
            job_title: Title for pasted text.
            company: Company for pasted text.
            description: Posting text.
            resume_name: Resume variant. Empty means the active resume.
            app_id: Application id, for application_follow_up.
        """
        if task not in PLAYBOOKS:
            raise ToolError(f"Unknown task '{task}'.", hint=f"Use one of: {', '.join(PLAYBOOKS)}")
        profile = h.resolve_profile(resume_name)
        exp = [{"employer": e.get("company", ""), "role": e.get("title", ""), "dates": f"{e.get('start', '')} - {e.get('end', '')}",
                "bullets": (e.get("bullets") or [])[:6]} for e in (profile.get("experience") or [])[:5]]
        context: dict[str, Any] = {"candidate": {"name": profile.get("name"), "target_title": profile.get("target_title"),
                                                  "years_of_experience": profile.get("years_of_experience"), "skills": (profile.get("skills") or [])[:30],
                                                  "experience": exp, "education": (profile.get("education") or [])[:3]}}
        if job_id or job_title or description:
            job = h.build_job(job_id, job_title, company, description)
            context["job"] = {**h.card(job), "description": h.clip(job.get("description", ""), 4000)[0],
                              "qualifications": (job.get("qualifications") or [])[:10]}
        if app_id:
            app = next((a for a in tracker.list_applications() if str(a["id"]) == app_id), None)
            if not app:
                raise ToolError(f"Application '{app_id}' not found.", code="not_found")
            context["application"] = {k: app[k] for k in ("id", "company", "title", "status", "notes", "follow_up_date", "days_in_stage")}
        return {"task": task, "instructions": playbook_text(task), "context": context,
                "rules": ["Use only facts in context.candidate. Never invent employers, dates, metrics or skills.",
                          "Say plainly when the candidate lacks a requirement.",
                          "Call verify_draft on the finished text before presenting it."]}

    # ===================================================================== 9. CONFIGURATION

    @tool
    def configure(key: str = "", value: str = "") -> dict[str, Any]:
        """Show or change the few server settings that are safe to change from chat. Secrets are never accepted.

        Editable keys: ai_provider, ai_model, max_results, max_scored_jobs. API keys come from environment variables.
        Personal job-search settings live in get_preferences and set_preferences.

        Args:
            key: Setting to change. Empty shows the current setup.
            value: New value.
        """
        if not key:
            return {"ai": ai_status(), "editable": sorted(EDITABLE_SETTINGS),
                    "limits": {"max_results": config.get_max_results(), "max_scored_jobs": config.get_max_scored_jobs()},
                    "workspace": str(ws)}
        k = key.strip().lower()
        if "key" in k or "token" in k or "secret" in k or "password" in k:
            raise ToolError("Secrets are not accepted here.", code="forbidden", hint="Set the API key as an environment variable and restart the server.")
        if k not in EDITABLE_SETTINGS:
            raise ToolError(f"'{key}' is not editable.", hint=f"Editable: {', '.join(sorted(EDITABLE_SETTINGS))}")
        v = value.strip()
        if k == "ai_provider" and v.lower() not in AI_PROVIDERS:
            raise ToolError(f"ai_provider must be one of: {', '.join(sorted(AI_PROVIDERS))}")
        if k in ("max_results", "max_scored_jobs") and not v.isdigit():
            raise ToolError(f"{k} must be a whole number.")
        db.set_setting(k, v.lower() if k == "ai_provider" else v)
        return {"updated": k, "key": k, "value": v, "ai": ai_status()}

    # ===================================================================== RESOURCES (read-only views of the same data)

    def as_json(obj: Any) -> str:
        return json.dumps(obj, indent=2, default=str)

    @mcp.resource("jobhunter://resumes")
    def resumes_resource() -> str:
        """All resume variants."""
        return as_json(db.list_resume_profiles())

    @mcp.resource("jobhunter://resumes/{name}")
    def resume_resource(name: str) -> str:
        """One parsed resume."""
        try:
            return as_json(h.resolve_profile(name, overlay=False))
        except ToolError as e:
            return as_json({"error": str(e)})

    @mcp.resource("jobhunter://applications")
    def applications_resource() -> str:
        """Tracked applications."""
        return as_json(tracker.list_applications())

    @mcp.resource("jobhunter://jobs/latest")
    def latest_jobs_resource() -> str:
        """Top stored jobs as compact cards."""
        jobs = db.query_stored_jobs({"sort": "score", "limit": 25}).get("jobs", [])
        return as_json(h.cards(jobs, 25))

    @mcp.resource("jobhunter://preferences")
    def preferences_resource() -> str:
        """Personal search preferences."""
        return as_json(preferences.load())

    @mcp.resource("jobhunter://config")
    def config_resource() -> str:
        """Server and workspace configuration."""
        data = dict(preferences.load())
        data["workspace"] = str(ws)
        return as_json(data)

    @mcp.resource("jobhunter://sources")
    def sources_resource() -> str:
        """The source catalog."""
        return as_json(source_registry.catalog())

    @mcp.resource("jobhunter://evidence/{name}")
    def evidence_resource(name: str) -> str:
        """Evidence claims extracted from a resume."""
        try:
            return as_json(ledger_for(h.resolve_profile(name, overlay=False)).to_list())
        except ToolError as e:
            return as_json({"error": str(e)})

    # The CEO and the team sit on top of the tools above. They are registered last so the specialists
    # in ``tool.registry`` are exactly the tools defined before this point.
    from .team import register_team
    mcp.ceo = register_team(mcp, tool, dict(tool.registry), store, ws)   # kept on the server so code and tests can reach the CEO
