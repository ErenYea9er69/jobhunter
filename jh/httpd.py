"""HTTP layer: a small router, same-origin protection, input limits, and JSON errors."""
import base64
import json
import logging
import mimetypes
import os
import re
import secrets
import time
import traceback
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import ats, autofill, config, db, digest, exporters, pipeline, resume_parser, refit, tracker, __version__

log = logging.getLogger("jobhunter")
TOKEN = os.environ.get("JH_TOKEN") or secrets.token_urlsafe(24)
ROUTES = {}


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def route(method, path):
    def deco(fn):
        ROUTES[(method, path)] = fn
        return fn
    return deco


def _need_profile():
    p = db.get_profile()
    if p.get("_is_empty"):
        raise ApiError("No resume profile yet. Upload or paste your resume first.", 400)
    return p


def _job(body):
    j = body.get("job")
    if not isinstance(j, dict) or not (j.get("title") or j.get("description")):
        raise ApiError("A job object with a title or description is required.")
    return j


# ------------------------------------------------------------------ routes

@route("GET", "/api/profiles")
def r_profiles_list(q, body):
    return {"success": True, "profiles": db.list_resume_profiles()}


@route("GET", "/api/profile")
def r_profile(q, body):
    pid = q.get("id", [None])[0]
    p = db.get_profile(pid)
    with db.session() as c:
        row = c.execute("SELECT updated_at FROM resume_profiles WHERE id=?", (p.get("_profile_id", "master"),)).fetchone()
    p["_updated_at"] = row["updated_at"] if row else None
    return p


@route("POST", "/api/profile")
def r_save_profile(q, body):
    if not isinstance(body, dict) or not isinstance(body.get("skills", []), list):
        raise ApiError("Profile must be an object with a skills list.")
    pid = body.get("_profile_id")
    db.save_profile(body, profile_id=pid)
    db.trigger_rescore_jobs(body)
    return {"success": True, "message": "Profile saved and jobs updated.", "profile": db.get_profile(pid)}


@route("POST", "/api/profile/activate")
def r_activate_profile(q, body):
    pid = body.get("id") or body.get("profile_id")
    if not pid:
        raise ApiError("Profile ID is required to activate.")
    try:
        active = db.set_active_resume_profile(pid)
        return {"success": True, "message": f"Activated profile '{active.get('_profile_name')}'", "profile": active}
    except Exception as e:
        raise ApiError(str(e))


@route("POST", "/api/profile/toggle-live")
def r_toggle_live_profile(q, body):
    pid = body.get("id") or body.get("profile_id")
    if not pid:
        raise ApiError("Profile ID is required to toggle live matching status.")
    is_live = body.get("is_live")
    try:
        updated = db.set_resume_profile_live(pid, is_live=is_live)
        db.trigger_rescore_jobs()
        status_str = "Live" if updated.get("is_live") else "Paused"
        return {
            "success": True,
            "message": f"Resume variant '{updated.get('name')}' is now {status_str} for matching.",
            "profile": updated,
            "profiles": db.list_resume_profiles()
        }
    except Exception as e:
        raise ApiError(str(e))


@route("POST", "/api/profile/duplicate")
def r_duplicate_profile(q, body):
    pid = body.get("id") or body.get("profile_id") or "master"
    new_name = body.get("name")
    target_title = body.get("target_title")
    tags = body.get("tags")
    try:
        cloned = db.duplicate_resume_profile(pid, new_name=new_name, target_title=target_title, tags=tags)
        return {"success": True, "message": f"Created variant '{cloned.get('_profile_name')}'", "profile": cloned}
    except Exception as e:
        raise ApiError(str(e))


@route("POST", "/api/profile/delete")
def r_delete_profile(q, body):
    pid = body.get("id") or body.get("profile_id")
    if not pid:
        raise ApiError("Profile ID is required to delete.")
    try:
        ok = db.delete_resume_profile(pid)
        return {"success": ok, "message": "Variant deleted." if ok else "Profile not found."}
    except Exception as e:
        raise ApiError(str(e))


@route("POST", "/api/profile/save-tailored")
def r_save_tailored_profile(q, body):
    job = body.get("job")
    tailored = body.get("tailored_resume")
    name = body.get("name")
    tags = body.get("tags")
    if not isinstance(job, dict) or not isinstance(tailored, dict):
        raise ApiError("Valid job and tailored_resume objects are required.")
    try:
        saved = db.save_tailored_variant_from_workspace(job, tailored, variant_name=name, tags=tags)
        return {"success": True, "message": f"Saved tailored variant '{saved.get('_profile_name')}' into your resume library.", "profile": saved}
    except Exception as e:
        raise ApiError(str(e))


@route("POST", "/api/profile/audit")
def r_audit_profile(q, body):
    profile = body.get("profile") or db.get_profile(body.get("id"))
    report = refit.audit_resume(profile)
    return {"success": True, "report": report}


@route("POST", "/api/profile/compare-job")
def r_compare_job(q, body):
    job = _job(body)
    all_profiles_meta = db.list_resume_profiles()
    profiles = [db.get_profile(pm["id"]) for pm in all_profiles_meta]
    comp = refit.compare_variants_against_job(job, profiles)
    return {"success": True, **comp}


@route("POST", "/api/parse-resume")
def r_parse(q, body):
    try:
        text = resume_parser.decode_upload(body)
    except resume_parser.ParseError as e:
        raise ApiError(str(e))
    if len(text.strip()) < 30:
        raise ApiError("No readable text found. Paste the resume text instead.")
    profile, report = resume_parser.parse_resume(text)
    return {"success": True, "profile": profile, "parse_report": report}


@route("GET", "/api/search")
def r_search(q, body):
    g = lambda k, d="": q.get(k, [d])[0]
    try:
        min_score = int(g("min_score", "0") or 0)
    except ValueError:
        raise ApiError("min_score must be a number.")
    return pipeline.search(query=g("q"), location=g("location"), work_mode=g("work_mode", "Any"),
                           min_score=min_score, famous_mode=g("famous_mode", "all"), force_refresh=g("refresh") == "1")


@route("GET", "/api/search/saved")
def r_saved_search(q, body):
    g = lambda k, d="": q.get(k, [d])[0]
    filters = {
        "category": g("category") or g("role"),
        "work_mode": g("work_mode"),
        "seniority": g("seniority"),
        "job_type": g("job_type"),
        "country": g("country"),
        "location": g("location"),
        "min_salary": g("min_salary", "0"),
        "min_score": g("min_score", "0"),
        "famous_mode": g("famous_mode", "all"),
        "industry": g("industry"),
        "days": g("days", "0"),
        "q": g("q") or g("keyword"),
        "sort": g("sort", "ranked"),
        "h1b": g("h1b"),
        "best_profile_id": g("best_profile_id") or g("profile_id")
    }
    return db.query_stored_jobs(filters, include_all=True)


@route("GET", "/api/jobs/query")
def r_jobs_query(q, body):
    return r_saved_search(q, body)


@route("GET", "/api/auto-search/status")
def r_auto_search_status(q, body):
    return {"success": True, "settings": db.get_auto_search_settings()}


@route("POST", "/api/auto-search/settings")
def r_auto_search_settings(q, body):
    enabled = bool(body.get("enabled", True))
    try:
        interval = float(body.get("interval_hours", 5.0))
    except (ValueError, TypeError):
        interval = 5.0
    saved = db.set_auto_search_settings(enabled=enabled, interval_hours=interval)
    return {"success": True, "settings": saved}


@route("POST", "/api/auto-search/trigger")
def r_auto_search_trigger(q, body):
    import threading
    threading.Thread(target=pipeline.run_background_auto_search, daemon=True).start()
    return {"success": True, "message": "Background auto search started in background."}


@route("GET", "/api/linkedin-radar/status")
def r_linkedin_radar_status(q, body):
    return {"success": True, "radar": pipeline.get_linkedin_radar_status()}


@route("POST", "/api/linkedin-radar/settings")
def r_linkedin_radar_settings(q, body):
    enabled = bool(body.get("enabled", True))
    try:
        interval_min = int(body.get("interval_min", 10))
    except (ValueError, TypeError):
        interval_min = 10
    if not enabled or interval_min <= 0:
        db.set_setting("linkedin_incremental_minutes", "0")
    else:
        db.set_setting("linkedin_incremental_minutes", str(max(1, min(120, interval_min))))
    pipeline.notify_linkedin_worker()
    return {"success": True, "radar": pipeline.get_linkedin_radar_status()}


@route("POST", "/api/linkedin-radar/trigger")
def r_linkedin_radar_trigger(q, body):
    ok, msg = pipeline.trigger_linkedin_radar_now()
    pipeline.notify_linkedin_worker()
    return {"success": ok, "message": msg, "radar": pipeline.get_linkedin_radar_status()}


@route("POST", "/api/jobs/refresh-sync")
def r_refresh_sync(q, body):
    res = db.apply_refresh_sync()
    f_in = body if isinstance(body, dict) and body else {}
    g = lambda k, d="": f_in.get(k) or (q.get(k, [d])[0] if q else d)
    filters = {
        "category": g("category") or g("role"),
        "work_mode": g("work_mode"),
        "seniority": g("seniority"),
        "job_type": g("job_type"),
        "country": g("country"),
        "location": g("location"),
        "min_salary": str(g("min_salary", "0") or "0"),
        "min_score": str(g("min_score", "0") or "0"),
        "famous_mode": g("famous_mode", "all"),
        "industry": g("industry"),
        "days": str(g("days", "0") or "0"),
        "q": g("q") or g("keyword"),
        "sort": g("sort", "ranked")
    }
    sort_order = filters.get("sort") or "ranked"
    all_res = db.query_stored_jobs({"sort": sort_order})
    has_filters = any(v and v not in ("0", "all", "Any") for k, v in filters.items() if k != "sort")
    query_res = db.query_stored_jobs(filters) if has_filters else all_res
    res["jobs"] = query_res["jobs"]
    res["all_jobs"] = all_res["jobs"]
    res["count"] = query_res["count"]
    res["total_all"] = all_res["total_all"]
    res["meta"] = query_res["meta"]
    res["facets"] = all_res.get("facets", {})
    return res


@route("GET", "/api/recommendations")
def r_recommendations(q, body):
    g = lambda k, d="": q.get(k, [d])[0]
    force_refresh = g("refresh") == "1"
    try:
        limit = int(g("limit", "0") or 0) or None
    except ValueError:
        limit = None
    profile = db.get_profile()
    return pipeline.get_recommendations(profile=profile, force_refresh=force_refresh, limit=limit)


@route("GET", "/api/sources")
def r_sources(q, body):
    return {"sources": pipeline.health_report()}


@route("POST", "/api/job-details")
def r_job_details(q, body):
    job = _job(body)
    from . import sources as src
    from .scoring import score_job
    enriched = src.enrich_job(job)
    profile = db.get_profile()
    if not profile.get("_is_empty"):
        scored = score_job(enriched, profile)
        enriched.update(scored)
        pipeline._rank_opportunity(enriched)
        pipeline.enrich_recommendation_insights(enriched, profile)
    enriched["enrichment_attempted"] = True
    enriched["needs_enrichment"] = False
    enriched["enriched"] = True
    db.update_search_job(enriched)
    return {"success": True, "job": enriched}


@route("GET", "/api/enrichment/status")
def r_enrichment_status(q, body):
    return {"success": True, "telemetry": pipeline.get_enrichment_telemetry()}


@route("POST", "/api/enrichment/trigger")
def r_enrichment_trigger(q, body):
    pipeline.trigger_background_enrichment()
    return {"success": True, "message": "Background enrichment triggered.", "telemetry": pipeline.get_enrichment_telemetry()}


@route("POST", "/api/refine")
def r_refine(q, body):
    return refit.refine_resume_for_job(_job(body), _need_profile())


@route("POST", "/api/gap-report")
def r_gap(q, body):
    return refit.generate_gap_report(_job(body), _need_profile())


@route("POST", "/api/cover-letter")
def r_cover(q, body):
    job, profile = _job(body), _need_profile()
    tone = (body.get("tone") or "direct").strip()
    angle = (body.get("angle") or "direct_impact").strip()
    selected_bullets = body.get("selected_bullets")
    use_llm = body.get("use_llm")
    pitch = refit.generate_cover_pitch(job, profile, tone=tone, angle=angle,
                                       selected_bullets=selected_bullets, use_llm=use_llm)
    return {
        "ok": True,
        "success": True,
        "cover_letter": pitch["full_text"],
        "pitch": pitch,
        "pitch_hook": pitch.get("pitch_hook", ""),
        "value_pillars": pitch.get("value_pillars", []),
        "why_company": pitch.get("why_company", ""),
        "honest_bridge": pitch.get("honest_bridge", ""),
        "call_to_action": pitch.get("call_to_action", ""),
        "telemetry": pitch.get("telemetry", {}),
        "angle": angle,
        "tone": tone,
        "provider": pitch.get("provider", "deterministic"),
        "model": pitch.get("model", ""),
        "used_llm": pitch.get("used_llm", False)
    }


@route("POST", "/api/interview-prep")
@route("POST", "/api/interview-prep/generate")
def r_prep(q, body):
    use_llm = body.get("use_llm")
    return refit.generate_interview_prep(_job(body), _need_profile(), use_llm=use_llm)


@route("POST", "/api/interview-prep/evaluate")
def r_prep_evaluate(q, body):
    question = (body.get("question") or "").strip()
    answer = (body.get("answer") or body.get("candidate_answer") or "").strip()
    if not question or not answer:
        raise ApiError("question and answer are required.")
    job = body.get("job")
    profile = body.get("profile") or db.get_profile()
    topic = body.get("topic")
    use_llm = body.get("use_llm")
    return refit.evaluate_mock_interview_answer(question, answer, job=job, profile=profile, topic=topic, use_llm=use_llm)


@route("POST", "/api/outreach/generate")
def r_outreach_generate(q, body):
    job = _job(body)
    profile = body.get("profile") or _need_profile()
    msg_type = body.get("message_type") or "all"
    hook = body.get("custom_hook") or ""
    use_llm = body.get("use_llm")
    return refit.generate_recruiter_outreach(job, profile, message_type=msg_type, custom_hook=hook, use_llm=use_llm)


@route("POST", "/api/ats-audit")
def r_ats(q, body):
    resume = body.get("resume") or _need_profile()
    return ats.compute_ats_audit(resume, _job(body))


@route("POST", "/api/auto-tailor")
def r_auto_tailor(q, body):
    t0, job, profile = time.time(), _job(body), _need_profile()
    archetype = (body.get("archetype") or "startup_velocity").strip()
    ref = refit.generate_custom_resume(job, profile, archetype=archetype)
    before, after = ats.compute_ats_audit(profile, job), ats.compute_ats_audit(ref["tailored_resume"], job)
    return {"success": True, "status": "success", "job_id": job.get("id"), "job_title": job.get("title"),
            "company": job.get("company"), "tailored_resume": ref["tailored_resume"], "refinement": ref,
            "executive_hook": ref.get("executive_hook", ""),
            "recruiter_6sec_audit": ref.get("recruiter_6sec_audit", {}),
            "core_competencies": ref.get("core_competencies", {}),
            "ats_audit": after, "before_ats": before, "after_ats": after,
            "boost": after["ats_score"] - before["ats_score"], "speed_ms": int((time.time() - t0) * 1000),
            "engine": ref["engine"]}


@route("POST", "/api/resume/custom-generate")
def r_custom_generate(q, body):
    t0 = time.time()
    job, profile = _job(body), _need_profile()
    archetype = (body.get("archetype") or "startup_velocity").strip()
    ref = refit.generate_custom_resume(job, profile, archetype=archetype)
    before, after = ats.compute_ats_audit(profile, job), ats.compute_ats_audit(ref["tailored_resume"], job)
    return {
        "ok": True,
        "success": True,
        "job_id": job.get("id"),
        "job_title": job.get("title"),
        "company": job.get("company"),
        "tailored_resume": ref["tailored_resume"],
        "refinement": ref,
        "executive_hook": ref.get("executive_hook", ""),
        "recruiter_6sec_audit": ref.get("recruiter_6sec_audit", {}),
        "core_competencies": ref.get("core_competencies", {}),
        "ats_audit": after,
        "before_ats": before,
        "after_ats": after,
        "boost": max(after["ats_score"] - before["ats_score"], 0),
        "speed_ms": int((time.time() - t0) * 1000),
        "engine": ref["engine"]
    }


@route("POST", "/api/auto-hunt")
def r_hunt(q, body):
    return tracker.prepare_application(_job(body), _need_profile())


@route("POST", "/api/autofill/payload")
def r_autofill_payload(q, body):
    job = body.get("job")
    profile = _need_profile()
    payload = autofill.get_autofill_payload(profile, job)
    code = autofill.generate_bookmarklet_code(payload)
    platform = payload.get("detected_platform", "standard")
    p_info = autofill.PLATFORM_INFO.get(platform, autofill.PLATFORM_INFO["standard"])
    return {
        "success": True,
        "payload": payload,
        "platform": platform,
        "platform_info": p_info,
        "bookmarklet": f"javascript:{urllib.parse.quote(code)}",
        "script": code
    }


@route("POST", "/api/autofill/solve-question")
def r_autofill_solve(q, body):
    question = (body.get("question") or "").strip()
    if not question:
        raise ApiError("question string is required.")
    job = body.get("job")
    profile = _need_profile()
    max_words = int(body.get("max_words") or 140)
    tone = (body.get("tone") or "confident").strip()
    res = autofill.solve_screening_question(question, profile, job, max_words=max_words, tone=tone)
    return {"success": True, **res}


@route("POST", "/api/autofill/batch-answers")
def r_autofill_batch(q, body):
    job = body.get("job")
    profile = _need_profile()
    answers = autofill.get_batch_screening_answers(profile, job)
    return {"success": True, "answers": answers}


@route("POST", "/api/easy-apply")
def r_easy_apply(q, body):
    job = _job(body)
    profile = _need_profile()
    tone = (body.get("tone") or "confident").strip()
    angle = (body.get("angle") or "strongest").strip()
    res = autofill.execute_easy_apply(job, profile, tone=tone, angle=angle)
    return {"success": True, **res}


@route("GET", "/api/applications")
def r_apps(q, body):
    return {"applications": tracker.list_applications()}


@route("POST", "/api/applications")
def r_save_app(q, body):
    try:
        return {"success": True, "id": tracker.upsert_application(body)}
    except ValueError as e:
        raise ApiError(str(e))


@route("POST", "/api/applications/follow-up")
def r_app_follow_up(q, body):
    app_id = body.get("id") or body.get("app_id") or body.get("application_id")
    if not app_id:
        raise ApiError("app_id is required.")
    action_type = body.get("action_type") or "status_check_5days"
    notes = body.get("notes") or ""
    profile = body.get("profile") or db.get_profile()
    use_llm = body.get("use_llm")
    try:
        return tracker.generate_application_follow_up(app_id, action_type=action_type, notes=notes, profile=profile, use_llm=use_llm)
    except ValueError as e:
        raise ApiError(str(e), 404)


@route("GET", "/api/applications/alerts")
def r_app_alerts(q, body):
    th = 5
    if q and q.get("threshold_days"):
        try:
            th = int(q["threshold_days"][0])
        except Exception:
            pass
    return tracker.get_stale_applications_alerts(threshold_days=th)


@route("POST", "/api/career/skill-roadmap")
def r_skill_roadmap(q, body):
    profile = body.get("profile") or _need_profile()
    target_title = body.get("target_title")
    market_skills = body.get("market_skills")
    use_llm = body.get("use_llm")
    return refit.generate_skill_roadmap(profile, target_title=target_title, market_skills=market_skills, use_llm=use_llm)


@route("POST", "/api/jobs/apply-bundle")
def r_apply_bundle(q, body):
    job = _job(body)
    profile = body.get("profile") or _need_profile()
    use_llm = body.get("use_llm")
    return tracker.generate_one_click_bundle(job, profile=profile, use_llm=use_llm)



@route("GET", "/api/stats")
def r_stats(q, body):
    return tracker.funnel_stats()


@route("GET", "/api/watchlist")
def r_watch(q, body):
    return {"watchlist": tracker.list_watchlist()}


@route("POST", "/api/watchlist")
def r_add_watch(q, body):
    try:
        r = tracker.add_watch(body.get("company_name"), body.get("slug", ""), body.get("board_type", ""), body.get("target_role", ""))
    except ValueError as e:
        raise ApiError(str(e))
    return {"success": True, **r}


@route("POST", "/api/watchlist/check")
def r_check_watch(q, body):
    return {"results": tracker.check_watchlist(db.get_profile())}


@route("GET", "/api/digest")
def r_digest(q, body):
    return digest.build_digest()


@route("POST", "/api/digest/send")
def r_digest_send(q, body):
    return digest.send_digest()


@route("GET", "/api/settings")
def r_get_settings(q, body):
    allowed = {"digest_min_score", "digest_email", "digest_time",
               "digest_smtp_host", "digest_smtp_port", "digest_smtp_user", "digest_smtp_pass",
               "adzuna_app_id", "adzuna_app_key",
               "ai_provider", "gemini_api_key", "openai_api_key", "anthropic_api_key",
               "deepseek_api_key", "groq_api_key", "mistral_api_key", "custom_ai_key", "custom_ai_endpoint",
               "ai_model", "ollama_endpoint",
               "max_scored_jobs", "max_results", "linkedin_scrape_depth", "user_country", "include_worldwide_remote",
               "theme_mode", "ui_density", "sound_enabled", "default_sort", "default_work_mode", "default_min_score",
               "auto_hide_applied", "auto_hide_expired"}
    out = {}
    with db.session() as c:
        for row in c.execute("SELECT key, value FROM settings"):
            if row["key"] in allowed:
                out[row["key"]] = row["value"]
    cfg = refit.get_active_ai_config()
    out["active_provider"] = cfg["provider"]
    out["active_model"] = cfg["model"]
    out["llm_available"] = refit.llm_available()
    out["env_keys"] = {
        "gemini": bool(config.GEMINI_API_KEY),
        "openai": bool(config.OPENAI_API_KEY),
        "anthropic": bool(config.ANTHROPIC_API_KEY),
        "deepseek": bool(config.DEEPSEEK_API_KEY),
        "groq": bool(config.GROQ_API_KEY),
        "mistral": bool(config.MISTRAL_API_KEY),
        "custom": bool(config.CUSTOM_AI_KEY or config.CUSTOM_AI_ENDPOINT),
        "ollama": bool(config.OLLAMA_ENDPOINT)
    }
    out.setdefault("max_scored_jobs", str(config.get_max_scored_jobs()))
    out.setdefault("max_results", str(config.get_max_results()))
    out.setdefault("linkedin_scrape_depth", config.get_linkedin_scrape_depth())
    out.setdefault("user_country", db.get_setting("user_country", "Worldwide"))
    out.setdefault("include_worldwide_remote", db.get_setting("include_worldwide_remote", "1"))
    out.setdefault("theme_mode", db.get_setting("theme_mode", "light"))
    out.setdefault("ui_density", db.get_setting("ui_density", "comfortable"))
    out.setdefault("sound_enabled", db.get_setting("sound_enabled", "1"))
    out.setdefault("default_sort", db.get_setting("default_sort", "score"))
    out.setdefault("auto_hide_applied", db.get_setting("auto_hide_applied", "0"))
    out.setdefault("auto_hide_expired", db.get_setting("auto_hide_expired", "0"))
    return out


@route("POST", "/api/settings")
def r_settings(q, body):
    allowed = {"digest_min_score", "digest_email", "digest_time",
               "digest_smtp_host", "digest_smtp_port", "digest_smtp_user", "digest_smtp_pass",
               "adzuna_app_id", "adzuna_app_key",
               "ai_provider", "gemini_api_key", "openai_api_key", "anthropic_api_key",
               "deepseek_api_key", "groq_api_key", "mistral_api_key", "custom_ai_key", "custom_ai_endpoint",
               "ai_model", "ollama_endpoint",
               "max_scored_jobs", "max_results", "linkedin_scrape_depth", "user_country", "include_worldwide_remote",
               "theme_mode", "ui_density", "sound_enabled", "default_sort", "default_work_mode", "default_min_score",
               "auto_hide_applied", "auto_hide_expired"}
    for k, v in body.items():
        if k in allowed:
            db.set_setting(k, str(v).strip())
    return {"success": True, "active_ai": refit.get_active_ai_config(), "settings": r_get_settings(q, body)}


@route("POST", "/api/test-ai")
def r_test_ai(q, body):
    t0 = time.time()
    cfg = dict(refit.get_active_ai_config())
    if body and body.get("ai_provider"):
        p = body["ai_provider"].lower()
        cfg["provider"] = p
        if body.get("ai_key"):
            cfg["key"] = body["ai_key"].strip()
        if body.get("ai_model"):
            cfg["model"] = body["ai_model"].strip()
        if body.get("endpoint"):
            cfg["endpoint"] = body["endpoint"].strip()
    if cfg["provider"] == "deterministic":
        return {"success": True, "provider": "deterministic", "latency_ms": 1,
                "message": "Deterministic engine active (100% local, fast, zero cost, 0 hallucinations)."}
    try:
        reply = refit._call_llm("You are an assistant. Reply with 'OK'.", "Ping", cfg)
        ms = int((time.time() - t0) * 1000)
        return {"success": True, "provider": cfg["provider"], "model": cfg.get("model", ""), "latency_ms": ms,
                "message": f"Successfully connected to {cfg['provider'].title()} in {ms}ms."}
    except Exception as e:
        return {"success": False, "provider": cfg["provider"], "error": str(e),
                "message": f"Connection failed to {cfg['provider']}: {str(e)[:160]}"}


@route("POST", "/api/ai-strategy")
def r_ai_strategy(q, body):
    return refit.generate_ai_strategy(_job(body), _need_profile())


@route("GET", "/api/cache-stats")
def r_cache(q, body):
    with db.session() as c:
        n = c.execute("SELECT COUNT(*) n FROM source_cache").fetchone()["n"]
    cfg = refit.get_active_ai_config()
    return {"cached_queries_count": n, "ttl_seconds": config.CACHE_TTL_SECONDS, "version": __version__,
            "llm_enabled": refit.llm_available(), "ai_provider": cfg["provider"], "ai_model": cfg["model"],
            "demo": config.DEMO}


@route("POST", "/api/clear-cache")
def r_clear(q, body):
    pipeline.clear_cache()
    return {"success": True, "message": "Search cache cleared."}


@route("GET", "/api/backup/export")
def r_backup_export(q, body):
    import datetime
    with db.session() as c:
        all_settings = {row["key"]: row["value"] for row in c.execute("SELECT key, value FROM settings")}
    return {
        "jobhunter_version": __version__,
        "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "profile": db.get_profile(),
        "profiles": db.list_resume_profiles(),
        "applications": tracker.list_applications(),
        "watchlist": tracker.list_watchlist(),
        "settings": all_settings,
    }


@route("POST", "/api/backup/import")
def r_backup_import(q, body):
    if not isinstance(body, dict):
        raise ApiError("Invalid backup format. Expected a JSON object.")
    imported = []
    if "profile" in body and isinstance(body["profile"], dict):
        db.save_profile(body["profile"])
        imported.append("primary profile")
    if "profiles" in body and isinstance(body["profiles"], list):
        for p in body["profiles"]:
            if isinstance(p, dict):
                pid = p.get("id") or p.get("_profile_id")
                db.save_profile(p, profile_id=pid)
        imported.append(f"{len(body['profiles'])} variants")
    if "settings" in body and isinstance(body["settings"], dict):
        for k, v in body["settings"].items():
            db.set_setting(k, str(v))
        imported.append("settings")
    if "applications" in body and isinstance(body["applications"], list):
        for app in body["applications"]:
            if isinstance(app, dict) and app.get("company"):
                tracker.upsert_application(app)
        imported.append(f"{len(body['applications'])} applications")
    if "watchlist" in body and isinstance(body["watchlist"], list):
        with db.session() as c:
            for w in body["watchlist"]:
                if isinstance(w, dict) and w.get("company_name"):
                    c.execute("INSERT OR REPLACE INTO watchlist (id,company_name,slug,board_type,target_role,added_at) VALUES (?,?,?,?,?,?)",
                              (w.get("id") or f"wl-{int(time.time() * 1000)}", w["company_name"], w.get("slug", ""), w.get("board_type", "greenhouse"), w.get("target_role", ""), w.get("added_at", "")))
        imported.append(f"{len(body['watchlist'])} watchlist companies")
    return {"success": True, "message": f"Successfully restored: {', '.join(imported) if imported else 'Nothing to import'}."}


@route("GET", "/api/system-info")
def r_system_info(q, body):
    import sys
    db_path = config.DB_PATH
    db_size_kb = 0
    if os.path.isfile(db_path):
        db_size_kb = round(os.path.getsize(db_path) / 1024, 1)
    with db.session() as c:
        job_count = c.execute("SELECT COUNT(*) n FROM search_jobs").fetchone()["n"]
        app_count = c.execute("SELECT COUNT(*) n FROM applications").fetchone()["n"]
    return {
        "version": __version__,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "db_size_kb": db_size_kb,
        "stored_jobs_count": job_count,
        "applications_count": app_count,
        "llm_available": refit.llm_available()
    }


@route("POST", "/api/export")
def r_export(q, body):
    fmt = (body.get("format") or "txt").lower()
    if fmt == "doc":
        fmt = "docx"
    doc_type = body.get("type") or "resume"
    if doc_type == "cover_letter" or "cover_letter" in body:
        text = body.get("cover_letter") or body.get("text") or ""
        profile = _need_profile()
        job = body.get("job") or {}
        if fmt == "txt":
            return {"format": "txt", "content": text, "filename": exporters.safe_cover_name(profile, job, "txt")}
        if fmt == "docx":
            data = exporters.cover_letter_to_docx(text, profile, job)
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif fmt == "pdf":
            data = exporters.cover_letter_to_pdf(text, profile, job)
            mime = "application/pdf"
        else:
            raise ApiError("format must be txt, docx, or pdf.")
        return {
            "format": fmt,
            "mime": mime,
            "content_base64": base64.b64encode(data).decode(),
            "filename": exporters.safe_cover_name(profile, job, fmt)
        }

    resume = body.get("resume") or _need_profile()
    if fmt == "txt":
        return {"format": "txt", "content": exporters.to_txt(resume), "filename": exporters.safe_name(resume, "txt")}
    if fmt == "html":
        return {"format": "html", "content": exporters.to_html(resume), "filename": exporters.safe_name(resume, "html")}
    if fmt == "docx":
        data, mime = exporters.to_docx(resume), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif fmt == "pdf":
        data, mime = exporters.to_pdf(resume), "application/pdf"
    else:
        raise ApiError("format must be txt, html, docx, or pdf.")
    return {"format": fmt, "mime": mime, "content_base64": base64.b64encode(data).decode(), "filename": exporters.safe_name(resume, fmt)}


# ------------------------------------------------------------------ handler

def _find_static_dir():
    for d in [
        getattr(config, "STATIC_DIR", ""),
        os.path.join(config.BASE_DIR, "public"),
        os.path.join(os.getcwd(), "public"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public"),
    ]:
        if d and os.path.isdir(d):
            return os.path.abspath(d)
    return config.STATIC_DIR


def _find_static_file(rel_path):
    if not rel_path or "\x00" in rel_path:
        return None
    norm = os.path.normpath(rel_path).replace("\\", "/")
    if norm.startswith("../") or "/../" in norm or norm == "..":
        return None
    rel = rel_path.lstrip("/\\")
    candidates = [rel]
    if rel and not os.path.splitext(rel)[1]:
        candidates.append(rel + ".html")
    for d in [
        getattr(config, "STATIC_DIR", ""),
        os.path.join(config.BASE_DIR, "public"),
        os.path.join(os.getcwd(), "public"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public"),
    ]:
        if d and os.path.isdir(d):
            abs_d = os.path.abspath(d)
            for cand in candidates:
                cand_clean = cand.lstrip("/\\")
                p = os.path.abspath(os.path.join(abs_d, cand_clean))
                try:
                    if os.path.commonpath([p, abs_d]) == abs_d and os.path.isfile(p):
                        return p
                except (ValueError, OSError):
                    continue
    return None


def _is_disconnect(e):
    if isinstance(e, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return True
    if isinstance(e, OSError):
        if getattr(e, "winerror", None) in (10053, 10054, 10058):
            return True
        import errno
        if getattr(e, "errno", None) in (errno.EPIPE, errno.ECONNRESET, errno.ECONNABORTED):
            return True
    return False


class Handler(SimpleHTTPRequestHandler):
    server_version = "JobHunter/" + __version__

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=_find_static_dir(), **kw)

    def handle(self):
        try:
            super().handle()
        except Exception as e:
            if _is_disconnect(e):
                self.close_connection = True
                return
            raise

    def finish(self):
        try:
            super().finish()
        except Exception as e:
            if _is_disconnect(e):
                return
            raise

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    # -- helpers
    def _json(self, data, status=200):
        try:
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            if _is_disconnect(e):
                self.close_connection = True
                return
            raise

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost", "[::1]") or host == config.HOST.lower()

    def _stream_search(self, q):
        g = lambda k, d="": q.get(k, [d])[0]
        try:
            min_score = int(g("min_score", "0") or 0)
        except ValueError:
            return self._json({"error": "min_score must be a number."}, 400)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def send_event(event_type, data):
            try:
                msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
                self.wfile.write(msg)
                self.wfile.flush()
            except Exception:
                pass

        try:
            pipeline.search(
                query=g("q"),
                location=g("location"),
                work_mode=g("work_mode", "Any"),
                min_score=min_score,
                famous_mode=g("famous_mode", "all"),
                force_refresh=g("refresh") == "1",
                on_progress=send_event
            )
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.close_connection = True

    def _dispatch(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not self._host_ok():
            return self._json({"error": "Host not allowed"}, 403)
        if not path.startswith("/api/"):
            return False
        token_in_query = f"token={TOKEN}" in (parsed.query or "")
        token_valid = (self.headers.get("X-JH-Token") == TOKEN) or token_in_query
        if not token_valid:
            return self._json({"error": "Missing or invalid session token. Reload the page."}, 401)
        if method == "GET" and path == "/api/search/stream":
            return self._stream_search(urllib.parse.parse_qs(parsed.query))
        body = {}
        if method in ("POST", "DELETE"):
            n = int(self.headers.get("Content-Length") or 0)
            if n > config.MAX_BODY_BYTES:
                return self._json({"error": "Request body too large"}, 413)
            if n:
                try:
                    body = json.loads(self.rfile.read(n).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    return self._json({"error": "Body must be valid JSON"}, 400)
        try:
            if method == "DELETE":
                return self._delete(path)
            fn = ROUTES.get((method, path))
            if not fn:
                return self._json({"error": "Endpoint not found"}, 404)
            return self._json(fn(urllib.parse.parse_qs(parsed.query), body if isinstance(body, dict) else {}))
        except ApiError as e:
            try:
                return self._json({"error": str(e)}, e.status)
            except Exception as se:
                if _is_disconnect(se):
                    self.close_connection = True
                    return False
                raise
        except Exception as e:
            if _is_disconnect(e):
                self.close_connection = True
                return False
            ref = secrets.token_hex(4)
            log.error("error %s: %s\n%s", ref, e, traceback.format_exc())
            try:
                return self._json({"error": f"Internal error (ref {ref}). Check the server log."}, 500)
            except Exception as se:
                if _is_disconnect(se):
                    self.close_connection = True
                    return False
                raise

    def _delete(self, path):
        if path.startswith("/api/applications/"):
            tracker.delete_application(path.rsplit("/", 1)[-1])
        elif path.startswith("/api/watchlist/"):
            tracker.delete_watch(path.rsplit("/", 1)[-1])
        elif path.startswith("/api/profiles/"):
            db.delete_resume_profile(path.rsplit("/", 1)[-1])
        elif path == "/api/purge-all-data":
            db.purge_all()
            pipeline.clear_cache()
            return self._json({"success": True, "message": "All local data deleted and the database file compacted."})
        else:
            return self._json({"error": "Endpoint not found"}, 404)
        return self._json({"success": True})

    # -- verbs
    def do_GET(self):
        try:
            if self._dispatch("GET") is not False:
                return
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            # Strip /static or /public prefix if rewritten
            clean_path = path
            if clean_path.startswith("/static/"):
                clean_path = clean_path[len("/static"):]
            elif clean_path.startswith("/public/"):
                clean_path = clean_path[len("/public"):]

            if ".." in clean_path or "\x00" in clean_path:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            if clean_path in ("/", "/index.html", ""):
                index_file = _find_static_file("index.html")
                if index_file and os.path.isfile(index_file):
                    with open(index_file, "r", encoding="utf-8") as f:
                        raw = f.read()
                    if 'name="jh-token"' in raw:
                        page = re.sub(r'<meta\s+name=["\']jh-token["\'][^>]*>', f'<meta name="jh-token" content="{TOKEN}">', raw).encode()
                    else:
                        page = raw.replace("</head>", f'<meta name="jh-token" content="{TOKEN}"></head>', 1).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(page)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Frame-Options", "DENY")
                    self.end_headers()
                    self.wfile.write(page)
                    return

            if clean_path in ("/landing", "/landing.html"):
                landing_file = _find_static_file("landing.html")
                if landing_file and os.path.isfile(landing_file):
                    with open(landing_file, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Cache-Control", "no-cache, must-revalidate")
                    self.end_headers()
                    self.wfile.write(content)
                    return

            asset_file = _find_static_file(clean_path)
            if asset_file and os.path.isfile(asset_file):
                mime, _ = mimetypes.guess_type(asset_file)
                mime = mime or "application/octet-stream"
                with open(asset_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(content)
                return

            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not Found")
        except Exception as e:
            if _is_disconnect(e):
                self.close_connection = True
                return
            raise

    def do_POST(self):
        try:
            self._dispatch("POST")
        except Exception as e:
            if _is_disconnect(e):
                self.close_connection = True
                return
            raise

    def do_DELETE(self):
        try:
            self._dispatch("DELETE")
        except Exception as e:
            if _is_disconnect(e):
                self.close_connection = True
                return
            raise

    def do_OPTIONS(self):  # no cross-origin access is granted
        self.send_response(204)
        self.end_headers()


def create_server(host=None, port=None):
    h = host or config.HOST
    start_port = port or config.PORT
    srv = None
    actual_port = start_port
    for p in range(start_port, start_port + 25):
        try:
            srv = ThreadingHTTPServer((h, p), Handler)
            actual_port = p
            break
        except OSError:
            if port is not None:
                raise
            continue

    if srv is None:
        srv = ThreadingHTTPServer((h, 0), Handler)
        actual_port = srv.server_address[1]

    srv.daemon_threads = True
    config.HOST = h
    config.PORT = actual_port
    return srv, actual_port


def start_background_server(host=None, port=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.init_db()
    digest.start_scheduler()
    pipeline.start_auto_search_worker()
    pipeline.start_background_enricher()
    srv, actual_port = create_server(host, port)
    log.info("JobHunter %s background server started on http://%s:%d (LLM: %s, demo: %s)",
             __version__, config.HOST, actual_port,
             "on" if refit.llm_available() else "off", config.DEMO)
    import threading
    th = threading.Thread(target=srv.serve_forever, daemon=True, name="JobHunterServer")
    th.start()
    return srv, actual_port


def run(host=None, port=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.init_db()
    digest.start_scheduler()
    pipeline.start_auto_search_worker()
    pipeline.start_background_enricher()
    srv, actual_port = create_server(host, port)
    log.info("JobHunter %s on http://%s:%d  (LLM: %s, demo: %s)", __version__, config.HOST, actual_port,
             "on" if refit.llm_available() else "off", config.DEMO)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("Stopped.")
    finally:
        try:
            srv.server_close()
        except Exception:
            pass

