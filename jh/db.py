"""Persistence & query layer backed by thread-safe in-memory tables and atomic JSON files.

Replaces SQLite (engine.db) with zero database files on disk while preserving
exact function signatures for protected modules and callers.
"""
from __future__ import annotations

import contextlib
import copy
import datetime
import json
import os
import re
import threading
import time
import uuid
from typing import Any, Optional

from . import config, store
from .util import annualize, clean_job_type, clean_text, now_iso, parse_date, parse_salary, stable_id

_init_lock = threading.Lock()
SCHEMA_VERSION = 6

EMPTY_PROFILE = {
    "name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": "",
    "portfolio_url": "", "proof_points": [],
    "target_title": "", "target_roles": [], "years_of_experience": 0, "work_mode": "Any",
    "preferred_locations": [], "min_salary": 0, "excluded_keywords": [],
    "preferred_job_types": [], "dream_companies": [], "dream_role": "",
    "summary": "", "skills": [], "skills_by_category": {}, "experience": [], "education": [],
    "_is_empty": True,
}

US_STATES_SET = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia",
    "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt",
    "va", "wa", "wv", "wi", "wy", "dc", "california", "new york", "texas", "washington",
    "florida", "illinois", "massachusetts", "colorado", "georgia", "virginia"
}

FAMOUS_COMPANY_TOKENS = {
    "openai", "anthropic", "grok", "xai", "perplexity", "cohere",
    "mistral", "midjourney", "cursor", "poolside",
    "meta", "facebook", "google", "alphabet", "apple", "microsoft",
    "amazon", "netflix", "vercel", "stripe", "gitlab", "github", "figma",
    "docker", "supabase", "uber", "airbnb", "coinbase", "shopify", "spotify",
    "databricks", "snowflake", "cloudflare", "palantir", "nvidia", "bytedance",
    "tiktok", "salesforce", "atlassian", "adobe", "twitter", "tesla", "spacex"
}


def is_famous_company(name: Any) -> bool:
    if not name:
        return False
    clean = re.sub(r"\b(inc|llc|corp|ltd|co|corporation|technologies|systems|labs|group)\b\.?", "", str(name).lower())
    tokens = re.findall(r"[a-z0-9]+", clean)
    return any(t in FAMOUS_COMPANY_TOKENS for t in tokens)


def clean_job_dict(j: Any) -> Any:
    """Sanitize all user-facing text fields in job dict."""
    if not isinstance(j, dict):
        return j
    for k in ("title", "company", "location", "work_mode", "salary", "job_type", "seniority"):
        if k in j and j[k] is not None:
            j[k] = clean_text(j[k])
    if "description" in j and j["description"] and "&" in str(j["description"]):
        j["description"] = clean_text(j["description"])
    return j


def classify_job(j: dict[str, Any]) -> dict[str, Any]:
    """Extract category, job_type, seniority, country, salary, and flags from job dict."""
    title = clean_text(j.get("title") or "")
    t_lower = title.lower()
    desc_sample = clean_text((j.get("description") or "")[:800]).lower()
    loc = clean_text(j.get("location") or "")
    loc_lower = loc.lower()
    comp = clean_text(j.get("company") or "")
    tags = [str(t).lower() for t in (j.get("tags") or [])]
    haystack = f"{t_lower} {loc_lower} {desc_sample} {' '.join(tags)}"

    # 1. Job Function / Category
    cat = "Software Engineer"
    if any(k in t_lower for k in ["full stack", "fullstack", "mern", "lamp"]):
        cat = "Full Stack Developer"
    elif any(k in t_lower for k in ["back end", "backend", "api engineer", "server", "golang", "python", "node"]):
        cat = "Backend Engineer"
    elif any(k in t_lower for k in ["front end", "frontend", "ui engineer", "react", "vue", "web developer"]):
        cat = "Frontend Engineer"
    elif any(k in t_lower for k in ["devops", "sre", "site reliability", "cloud engineer", "platform engineer", "infrastructure"]):
        cat = "DevOps Engineer"
    elif any(k in t_lower for k in ["data engineer", "big data", "etl", "analytics engineer"]):
        cat = "Data Engineer"
    elif any(k in t_lower for k in ["machine learning", "ml engineer", "ai engineer", "data scientist", "deep learning", "nlp"]):
        cat = "Machine Learning Engineer"
    elif any(k in t_lower for k in ["mobile", "ios", "android", "flutter", "react native"]):
        cat = "Mobile Developer"
    elif any(k in t_lower for k in ["qa", "quality assurance", "test engineer", "sdet", "automation engineer"]):
        cat = "QA Engineer"
    elif any(k in t_lower for k in ["security", "cyber", "infosec", "appsec"]):
        cat = "Security Engineer"
    elif any(k in t_lower for k in ["product manager", "product owner", "technical product"]):
        cat = "Product Manager"
    elif any(k in t_lower for k in ["ui/ux", "designer", "ux design", "product design"]):
        cat = "UI/UX Designer"
    elif any(k in t_lower for k in ["data analyst", "business analyst", "bi analyst"]):
        cat = "Data Analyst"

    # 2. Seniority
    sen = "mid"
    if any(k in t_lower for k in ["intern", "internship", "co-op"]):
        sen = "intern"
    elif any(k in t_lower for k in ["junior", "jr", "entry", "associate", "new grad"]):
        sen = "junior"
    elif any(k in t_lower for k in ["director", "vp", "head of", "chief", "executive"]):
        sen = "director"
    elif any(k in t_lower for k in ["lead", "staff", "principal", "architect"]):
        sen = "lead_staff"
    elif any(k in t_lower for k in ["senior", "sr."]) or re.search(r"\bsr\b", t_lower):
        sen = "senior"

    # 3. Work mode
    wm = (j.get("work_mode") or "").strip()
    if not wm or wm.lower() == "any":
        if any(k in haystack for k in ["remote", "anywhere", "work from home", "virtual"]):
            wm = "Remote"
        elif any(k in haystack for k in ["hybrid"]):
            wm = "Hybrid"
        else:
            wm = "Onsite"

    # 4. Job type
    jt = clean_job_type(j.get("job_type") or "")
    if any(k in t_lower for k in ["intern", "internship", "co-op", "stagiaire", "praktikant", "werkstudent", "apprentice"]):
        jt = "Internship"
    elif any(k in t_lower for k in ["part-time", "part time"]):
        jt = "Part-time"
    elif any(k in t_lower for k in ["contract", "contractor", "freelance", "c2c"]):
        jt = "Contract"
    elif not jt or jt.lower() in ("any", "other", "unknown", "unknown."):
        if sen == "intern" or any(k in haystack for k in ["intern", "internship", "stage", "alternance", "apprentice", "praktikum", "werkstudent", "co-op"]):
            jt = "Internship"
        elif any(k in haystack for k in ["part-time", "part time", "flexible hours", "20 hours/week", "20 hrs/week"]):
            jt = "Part-time"
        elif any(k in haystack for k in ["contract", "contractor", "freelance", "c2c", "w2 contract", "subcontract"]):
            jt = "Contract"
        else:
            jt = "Full-time"

    # 5. Country
    country = "United States"
    if any(k in loc_lower for k in ["worldwide", "global", "anywhere", "remote"]):
        country = "Worldwide"
    elif any(k in loc_lower for k in ["united kingdom", "london", "england", "uk", "manchester"]):
        country = "United Kingdom"
    elif any(k in loc_lower for k in ["germany", "berlin", "munich", "deutschland"]):
        country = "Germany"
    elif any(k in loc_lower for k in ["canada", "toronto", "vancouver", "montreal", "ontario"]):
        country = "Canada"
    else:
        loc_tokens = [tok.strip() for tok in re.split(r"[,/ -]+", loc_lower) if tok.strip()]
        if any(tok in US_STATES_SET for tok in loc_tokens) or any(c in loc_lower for c in ["san francisco", "new york", "seattle", "austin", "chicago", "boston", "los angeles"]):
            country = "United States"
        elif wm == "Remote":
            country = "Worldwide"

    # 6. Salary parsing
    sal_info = parse_salary(j.get("salary"))
    ann = annualize(sal_info) if sal_info else None
    min_sal = float(ann[0]) if ann else float(j.get("min_salary") or 0.0)
    max_sal = float(ann[1]) if ann else float(j.get("max_salary") or 0.0)

    # 7. Industry
    ind = "Tech & Software"
    if any(k in haystack for k in ["fintech", "finance", "bank", "crypto", "trading", "capital", "payments", "insurance"]):
        ind = "Finance & Fintech"
    elif any(k in haystack for k in ["health", "healthcare", "medical", "pharma", "biotech", "clinical"]):
        ind = "Healthcare & Bio"
    elif any(k in haystack for k in ["consulting", "advisory", "agency", "staffing", "services"]):
        ind = "Consulting & Services"

    # 8. Startups & Famous
    is_fam = 1 if is_famous_company(comp) or j.get("is_famous") else 0
    is_start = 1 if not is_fam and (bool(j.get("is_startup")) or any(k in haystack for k in ["series a", "series b", "seed", "startup", "yc", "y combinator"])) else 0

    # 9. H1B Sponsorship
    h1b = 1 if re.search(r"\bh1-?b\b|visa sponsorship|sponsor(?:ship)? available", haystack) else 0

    # 10. Skills text
    if j.get("skills_text"):
        skills_text = str(j.get("skills_text"))
    else:
        skills_list = j.get("skills") or j.get("matched_skills") or []
        skills_text = ", ".join(str(s) for s in skills_list) if isinstance(skills_list, list) else str(skills_list)

    return {
        "category": cat,
        "job_type": jt,
        "seniority": sen,
        "work_mode": wm,
        "country": country,
        "min_salary": min_sal,
        "max_salary": max_sal,
        "industry": ind,
        "skills_text": skills_text,
        "is_famous": is_fam,
        "is_startup": is_start,
        "h1b": h1b,
    }


def _ws() -> store.WorkspaceStore:
    return store.get_store(ensure_dirs=True)


def connect() -> store.MemSession:
    return store.MemSession(_ws())


@contextlib.contextmanager
def session():
    with store.open_session(ensure_dirs=True) as s:
        yield s


def _columns(conn: Any, table: str) -> set[str]:
    return set(store.TABLE_DEFAULTS.get(table, {}).keys())


def init_db() -> None:
    with _init_lock:
        ws = store.get_store(ensure_dirs=True)
        with ws.lock:
            changed = False
            for tbl in ("jobs", "search_jobs", "applications", "signals"):
                for r in ws.tables.get(tbl, []):
                    for k in ("title", "company", "location", "work_mode", "salary", "notes", "text"):
                        v = r.get(k)
                        if isinstance(v, str) and "&" in v:
                            r[k] = clean_text(v)
                            changed = True
            if changed:
                ws.flush_durable()
                ws.flush_cache()


def _cleanup_html_entities(c: Any = None) -> None:
    init_db()


# ------------------------------------------------------------------ Profile & Resume Profiles

def _hydrate_profile(raw_data: str | dict, row: dict | None) -> dict[str, Any]:
    data = json.loads(raw_data) if isinstance(raw_data, str) else dict(raw_data or {})
    for k, v in EMPTY_PROFILE.items():
        data.setdefault(k, json.loads(json.dumps(v)) if k != "_is_empty" else False)
    if not data.get("target_roles") and (data.get("target_title") or data.get("skills")):
        from .scoring import derive_target_roles
        data["target_roles"] = derive_target_roles(data)
    if row:
        data["_profile_id"] = row["id"]
        data["_profile_name"] = row["name"]
        data["_is_master"] = bool(row["is_master"])
        data["_is_active"] = bool(row["is_active"])
        data["_is_live"] = bool(row.get("is_live", 1))
    else:
        data["_profile_id"] = "master"
        data["_profile_name"] = "Master Resume"
        data["_is_master"] = True
        data["_is_active"] = True
        data["_is_live"] = True
    return data


def get_profile(profile_id: str | None = None) -> dict[str, Any]:
    ws = _ws()
    with ws.lock:
        rps = ws.tables["resume_profiles"]
        row = None
        if profile_id:
            row = next((r for r in rps if r.get("id") == profile_id), None)
        if not row:
            row = next((r for r in rps if r.get("is_active")), None)
        if not row:
            row = next((r for r in rps if r.get("is_master")), None)
        if not row and rps:
            row = sorted(rps, key=lambda r: r.get("updated_at") or "", reverse=True)[0]
        if row:
            raw_data = row.get("data_json") or json.dumps(EMPTY_PROFILE)
        else:
            leg = next((r for r in ws.tables["profile"] if r.get("id") == 1), None)
            raw_data = leg["data"] if (leg and leg.get("data")) else json.dumps(EMPTY_PROFILE)
    return _hydrate_profile(raw_data, row)


def get_live_profiles() -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = [dict(r) for r in ws.tables["resume_profiles"] if r.get("is_live", 1)]
        rows.sort(key=lambda r: (1 if r.get("is_master") else 0, r.get("updated_at") or ""), reverse=True)
    if not rows:
        return [get_profile()]
    profiles = []
    for r in rows:
        try:
            profiles.append(_hydrate_profile(r.get("data_json") or "{}", r))
        except Exception:
            pass
    return profiles or [get_profile()]


def save_profile(data: dict[str, Any], profile_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    data = dict(data)
    data.pop("_is_empty", None)
    data.pop("_updated_at", None)
    pid = profile_id or session_id or data.pop("_profile_id", None) or "master"
    pname = data.pop("_profile_name", None) or ("Master Resume" if pid == "master" else "Resume Variant")
    is_master = 1 if pid == "master" or data.pop("_is_master", False) else 0
    is_active = 1 if data.pop("_is_active", True) else 0
    is_live = 1 if data.pop("_is_live", True) else 0

    target_title = data.get("target_title", "")
    target_roles = data.get("target_roles", [])
    skills = data.get("skills", [])
    tags = data.get("tags") or (skills[:6] if skills else ["Core"])
    iso_now = now_iso()
    data_json = json.dumps(data)

    ws = _ws()
    with ws.lock:
        rps = ws.tables["resume_profiles"]
        existing = next((r for r in rps if r.get("id") == pid), None)
        if existing:
            existing.update({
                "name": pname,
                "target_title": target_title,
                "target_roles_json": json.dumps(target_roles),
                "tags_json": json.dumps(tags),
                "data_json": data_json,
                "updated_at": iso_now,
            })
        else:
            rps.append(ws._normalize_row("resume_profiles", {
                "id": pid,
                "name": pname,
                "target_title": target_title,
                "target_roles_json": json.dumps(target_roles),
                "tags_json": json.dumps(tags),
                "data_json": data_json,
                "is_active": is_active,
                "is_master": is_master,
                "is_live": is_live,
                "created_at": iso_now,
                "updated_at": iso_now,
            }))

        if is_active or is_master or pid == "master":
            roles_val = json.dumps(target_roles) if isinstance(target_roles, list) else str(target_roles or "")
            skills_val = json.dumps(skills) if isinstance(skills, list) else str(skills or "")
            years_val = float(data.get("years_of_experience") or 0)
            resume_path_val = str(data.get("resume_path") or "")
            portfolio_url_val = str(data.get("portfolio_url") or "")
            proof_points_val = json.dumps(data.get("proof_points") or []) if isinstance(data.get("proof_points"), (list, dict)) else str(data.get("proof_points") or "[]")
            ws.tables["profile"] = [ws._normalize_row("profile", {
                "id": 1,
                "data": data_json,
                "updated_at": iso_now,
                "roles": roles_val,
                "years": years_val,
                "skills": skills_val,
                "resume_path": resume_path_val,
                "portfolio_url": portfolio_url_val,
                "proof_points": proof_points_val,
            })]
        ws.flush_durable()
    return get_profile(pid)


def list_resume_profiles() -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = sorted(
            ws.tables["resume_profiles"],
            key=lambda r: (1 if r.get("is_master") else 0, r.get("updated_at") or ""),
            reverse=True,
        )
        rows = [dict(r) for r in rows]

    res = []
    for r in rows:
        try:
            d = json.loads(r.get("data_json") or "{}")
            skills = d.get("skills", [])
            experience = d.get("experience", [])
            email = d.get("email", "")
            phone = d.get("phone", "")
            location = d.get("location", "")
            linkedin = d.get("linkedin", "")
            github = d.get("github", "")
            website = d.get("website", "")
            years = d.get("total_experience_years") or d.get("years_of_experience", 0)
            exp_count = len(experience)
            work_mode = d.get("work_mode", "Any")
            min_salary = d.get("min_salary", 0)
            raw_fn = d.get("filename") or d.get("_source_file", "")
            filename = os.path.basename(raw_fn) if raw_fn else ""
        except Exception:
            skills, experience = [], []
            email = phone = location = linkedin = github = website = filename = ""
            years = exp_count = min_salary = 0
            work_mode = "Any"

        res.append({
            "id": r["id"],
            "name": r["name"],
            "target_title": r.get("target_title") or "General Candidate",
            "target_roles": json.loads(r.get("target_roles_json") or "[]"),
            "tags": json.loads(r.get("tags_json") or "[]"),
            "is_active": bool(r.get("is_active")),
            "is_master": bool(r.get("is_master")),
            "is_live": bool(r.get("is_live", 1)),
            "source_job_id": r.get("source_job_id", ""),
            "source_job_title": r.get("source_job_title", ""),
            "source_company": r.get("source_company", ""),
            "created_at": r.get("created_at", ""),
            "updated_at": r.get("updated_at", ""),
            "skills_count": len(skills),
            "top_skills": skills[:6],
            "skills": skills,
            "experience": experience,
            "email": email,
            "phone": phone,
            "location": location,
            "linkedin": linkedin,
            "github": github,
            "website": website,
            "filename": filename,
            "years_of_experience": years,
            "experience_years": years,
            "experience_count": exp_count,
            "work_mode": work_mode,
            "min_salary": min_salary,
        })
    return res


def set_active_resume_profile(profile_id: str) -> dict[str, Any]:
    ws = _ws()
    with ws.lock:
        target = next((r for r in ws.tables["resume_profiles"] if r.get("id") == profile_id), None)
        if not target:
            raise ValueError(f"Resume profile '{profile_id}' not found.")
        for r in ws.tables["resume_profiles"]:
            r["is_active"] = 1 if r.get("id") == profile_id else 0
        ws.tables["profile"] = [ws._normalize_row("profile", {"id": 1, "data": target.get("data_json") or "{}", "updated_at": now_iso()})]
        ws.flush_durable()
    active_profile = get_profile(profile_id)
    trigger_rescore_jobs(active_profile)
    return active_profile


def duplicate_resume_profile(profile_id: str, new_name: str | None = None, target_title: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    base = get_profile(profile_id)
    if not base or base.get("_is_empty"):
        raise ValueError("Cannot duplicate an empty profile.")

    new_id = f"variant_{uuid.uuid4().hex[:8]}"
    name = new_name or f"{base.get('target_title') or base.get('_profile_name') or 'Resume'} (Variant)"
    data = dict(base)
    for k in ("_profile_id", "_is_master", "_is_active", "_is_live", "_profile_name"):
        data.pop(k, None)

    if target_title:
        data["target_title"] = target_title
        from .scoring import derive_target_roles
        data["target_roles"] = derive_target_roles(data)

    iso_now = now_iso()
    skills = data.get("skills", [])
    variant_tags = tags if tags is not None else (skills[:5] if skills else ["Variant"])

    ws = _ws()
    with ws.lock:
        ws.tables["resume_profiles"].append(ws._normalize_row("resume_profiles", {
            "id": new_id,
            "name": name,
            "target_title": data.get("target_title", ""),
            "target_roles_json": json.dumps(data.get("target_roles", [])),
            "tags_json": json.dumps(variant_tags),
            "data_json": json.dumps(data),
            "is_active": 0,
            "is_master": 0,
            "is_live": 1,
            "created_at": iso_now,
            "updated_at": iso_now,
        }))
        ws.flush_durable()

    trigger_rescore_jobs()
    return get_profile(new_id)


def delete_resume_profile(profile_id: str) -> bool:
    ws = _ws()
    with ws.lock:
        rps = ws.tables["resume_profiles"]
        row = next((r for r in rps if r.get("id") == profile_id), None)
        if not row:
            return False
        if row.get("is_master"):
            raise ValueError("The Master Resume cannot be deleted. You can edit it or create variants from it.")
        was_active = bool(row.get("is_active"))
        ws.tables["resume_profiles"] = [r for r in rps if r.get("id") != profile_id]
        if not any(r.get("is_live") for r in ws.tables["resume_profiles"]):
            for r in ws.tables["resume_profiles"]:
                if r.get("is_master"):
                    r["is_live"] = 1
        if was_active:
            for r in ws.tables["resume_profiles"]:
                if r.get("is_master"):
                    r["is_active"] = 1
                    ws.tables["profile"] = [ws._normalize_row("profile", {"id": 1, "data": r.get("data_json") or "{}", "updated_at": now_iso()})]
        ws.flush_durable()
    trigger_rescore_jobs()
    return True


def save_tailored_variant_from_workspace(job: dict[str, Any], tailored_resume: dict[str, Any], variant_name: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    active = get_profile()
    new_id = f"tailored_{uuid.uuid4().hex[:8]}"

    comp = job.get("company") or "Target"
    role = job.get("title") or "Role"
    name = variant_name or f"Tailored: {comp} - {role}"

    new_data = dict(active)
    for k in ("summary", "skills", "experience"):
        if tailored_resume.get(k):
            new_data[k] = tailored_resume[k]
    new_data["target_title"] = role
    from .scoring import derive_target_roles
    new_data["target_roles"] = derive_target_roles(new_data)

    iso_now = now_iso()
    extracted_tags = tags or (job.get("matched_skills", []) or new_data.get("skills", []))[:6]

    ws = _ws()
    with ws.lock:
        ws.tables["resume_profiles"].append(ws._normalize_row("resume_profiles", {
            "id": new_id,
            "name": name,
            "target_title": role,
            "target_roles_json": json.dumps(new_data.get("target_roles", [])),
            "tags_json": json.dumps(extracted_tags),
            "data_json": json.dumps(new_data),
            "is_active": 0,
            "is_master": 0,
            "is_live": 1,
            "source_job_id": job.get("id") or "",
            "source_job_title": role,
            "source_company": comp,
            "created_at": iso_now,
            "updated_at": iso_now,
        }))
        ws.flush_durable()

    trigger_rescore_jobs()
    return get_profile(new_id)


# ------------------------------------------------------------------ Rescoring

_rescore_lock = threading.Lock()
_rescore_worker_running = False
_rescore_requested = False


def trigger_rescore_jobs(profile: Any = None) -> None:
    global _rescore_requested, _rescore_worker_running
    with _rescore_lock:
        _rescore_requested = True
        if _rescore_worker_running:
            return
        _rescore_worker_running = True
    threading.Thread(target=_rescore_worker_loop, daemon=True, name="JobRescoreWorker").start()


def _rescore_worker_loop() -> None:
    global _rescore_requested, _rescore_worker_running
    while True:
        with _rescore_lock:
            if not _rescore_requested:
                _rescore_worker_running = False
                break
            _rescore_requested = False
        try:
            rescore_and_classify_stored_jobs()
        except Exception:
            pass


def _flush_rescore_updates(batch: list[tuple[Any, ...]]) -> None:
    if not batch:
        return
    ws = _ws()
    with ws.lock:
        by_key = {r.get("job_key"): r for r in ws.tables["search_jobs"]}
        for item in batch:
            score, opp, cat, jt, sen, cny, wm, pid, pname, jjson, jkey = item
            row = by_key.get(jkey)
            if row:
                row.update({
                    "score": score, "opportunity_score": opp, "category": cat,
                    "job_type": jt, "seniority": sen, "country": cny, "work_mode": wm,
                    "best_profile_id": pid, "best_profile_name": pname, "job_json": jjson,
                })
        ws.flush_cache()


def rescore_and_classify_stored_jobs(profile: Any = None) -> int:
    from .scoring import score_job_best
    from .pipeline import _rank_opportunity

    if profile is None:
        profiles = get_live_profiles()
    elif isinstance(profile, list):
        profiles = profile
    else:
        profiles = [profile]
    if not profiles or (len(profiles) == 1 and profiles[0].get("_is_empty")):
        return 0

    ws = _ws()
    with ws.lock:
        rows = [dict(r) for r in ws.tables["search_jobs"]]

    updates = []
    for r in rows:
        try:
            j = json.loads(r["job_json"])
            cat = r.get("category") or j.get("category")
            sen = r.get("seniority") or j.get("seniority")
            jt = r.get("job_type") or j.get("job_type")
            cny = r.get("country") or j.get("country")
            wm = r.get("work_mode") or j.get("work_mode")
            if not (cat and sen and jt and cny and wm):
                c_meta = classify_job(j)
                cat, sen, jt, cny, wm = c_meta["category"], c_meta["seniority"], c_meta["job_type"], c_meta["country"], c_meta["work_mode"]

            scored = score_job_best(j, profiles)
            j.update(scored)
            j["category"], j["seniority"], j["job_type"], j["country"], j["work_mode"] = cat, sen, jt, cny, wm
            _rank_opportunity(j)
            updates.append((
                j.get("score", 0), j.get("opportunity_score", 0),
                cat, jt, sen, cny, wm,
                j.get("best_profile_id", ""), j.get("best_profile_name", ""),
                json.dumps(j), r["job_key"],
            ))
        except Exception:
            pass

    if updates:
        _flush_rescore_updates(updates)
    return len(updates)


# ------------------------------------------------------------------ Settings

def get_setting(key: str, default: str = "") -> str:
    ws = _ws()
    with ws.lock:
        for r in ws.tables["settings"]:
            if r.get("key") == key:
                return str(r.get("value", default))
    return default


def set_setting(key: str, value: Any) -> None:
    ws = _ws()
    with ws.lock:
        for r in ws.tables["settings"]:
            if r.get("key") == key:
                r["value"] = str(value)
                ws.flush_durable()
                return
        ws.tables["settings"].append({"key": key, "value": str(value)})
        ws.flush_durable()


save_setting = set_setting


def delete_settings(keys: list[str] | tuple[str, ...]) -> int:
    key_set = set(keys)
    ws = _ws()
    with ws.lock:
        before = len(ws.tables["settings"])
        ws.tables["settings"] = [r for r in ws.tables["settings"] if r.get("key") not in key_set]
        removed = before - len(ws.tables["settings"])
        if removed:
            ws.flush_durable()
        return removed


# ------------------------------------------------------------------ Search Jobs & Staging

def get_job(job_id: str) -> Optional[dict[str, Any]]:
    key = (job_id or "").strip()
    if not key:
        return None
    ws = _ws()
    with ws.lock:
        for tbl in ("search_jobs", "pending_search_jobs", "jobs"):
            for r in ws.tables[tbl]:
                if r.get("job_key") == key or r.get("id") == key:
                    try:
                        return json.loads(r.get("job_json") or "{}")
                    except Exception:
                        return None
    return None


def _upsert_search_job_locked(ws: store.WorkspaceStore, j: dict[str, Any], query: str, now: str) -> None:
    key = j.get("job_key") or j.get("id")
    if not key:
        return
    clean_job_dict(j)
    c_meta = classify_job(j)
    j["category"] = c_meta["category"]
    j["seniority"] = c_meta["seniority"]
    j["job_type"] = c_meta["job_type"]
    j["country"] = c_meta["country"]
    j["work_mode"] = c_meta["work_mode"]
    row = ws._normalize_row("search_jobs", {
        "job_key": key,
        "query": query or j.get("query", ""),
        "title": clean_text(j.get("title", "")),
        "company": clean_text(j.get("company", "")),
        "location": clean_text(j.get("location", "")),
        "work_mode": c_meta["work_mode"],
        "score": j.get("score", 0),
        "opportunity_score": j.get("opportunity_score", 0),
        "is_famous": c_meta["is_famous"],
        "source_kind": j.get("source_kind", ""),
        "source_names": ",".join(j.get("source_names", [])),
        "posted_at": j.get("posted_at", ""),
        "job_json": json.dumps(j),
        "created_at": now,
        "updated_at": now,
        "category": c_meta["category"],
        "job_type": c_meta["job_type"],
        "seniority": c_meta["seniority"],
        "country": c_meta["country"],
        "min_salary": c_meta["min_salary"],
        "max_salary": c_meta["max_salary"],
        "industry": c_meta["industry"],
        "skills_text": c_meta["skills_text"],
        "is_startup": c_meta["is_startup"],
        "h1b": c_meta["h1b"],
        "is_active": 1,
        "best_profile_id": j.get("best_profile_id", ""),
        "best_profile_name": j.get("best_profile_name", ""),
    })
    tbl = ws.tables["search_jobs"]
    for idx, existing in enumerate(tbl):
        if existing.get("job_key") == key:
            tbl[idx] = row
            return
    tbl.append(row)


def replace_search_jobs(jobs: list[dict[str, Any]], query: str = "", location: str = "", sources: Any = None, clear_existing: bool = True, conn: Any = None) -> None:
    now = now_iso()
    ws = _ws()
    with ws.lock:
        if clear_existing:
            ws.tables["search_jobs"] = []
        for j in jobs:
            _upsert_search_job_locked(ws, j, query, now)
        total_now = sum(1 for r in ws.tables["search_jobs"] if r.get("is_active", 1) == 1)
        ws.tables["search_meta"] = [ws._normalize_row("search_meta", {
            "id": 1,
            "query": query,
            "location": location,
            "total_count": total_now,
            "sources_json": json.dumps(sources or []),
            "updated_at": now,
        })]
        ws.flush_cache()


def update_search_job(job: dict[str, Any]) -> bool:
    from . import dedup
    key = job.get("job_key") or dedup.job_key(job) or job.get("id")
    if not key:
        return False
    clean_job_dict(job)
    now = now_iso()
    c_meta = classify_job(job)
    ws = _ws()
    with ws.lock:
        for r in ws.tables["search_jobs"]:
            if r.get("job_key") == key:
                r.update({
                    "title": clean_text(job.get("title", "")),
                    "company": clean_text(job.get("company", "")),
                    "location": clean_text(job.get("location", "")),
                    "work_mode": c_meta["work_mode"],
                    "score": job.get("score", 0),
                    "opportunity_score": job.get("opportunity_score", 0),
                    "job_json": json.dumps(job),
                    "updated_at": now,
                    "category": c_meta["category"],
                    "job_type": c_meta["job_type"],
                    "seniority": c_meta["seniority"],
                    "country": c_meta["country"],
                    "best_profile_id": job.get("best_profile_id", ""),
                    "best_profile_name": job.get("best_profile_name", ""),
                })
                ws.flush_cache()
                return True
    return False


def _unpack_search_row(r: dict[str, Any], compact: bool = False) -> dict[str, Any]:
    j = json.loads(r.get("job_json") or "{}")
    if compact:
        j["description"] = ""
        j["qualifications"] = []
        j["responsibilities"] = []
    for col in ("job_type", "work_mode", "category", "seniority", "country", "best_profile_id", "best_profile_name"):
        if r.get(col):
            j[col] = r[col]
    return j


def _matches_stored_filters(r: dict[str, Any], filters: dict[str, Any], inc_remote: bool) -> bool:
    title = r.get("title") or ""
    t_low = title.lower()
    cat_val = r.get("category") or ""
    skills_low = (r.get("skills_text") or "").lower()
    wm_low = (r.get("work_mode") or "").lower()
    loc_low = (r.get("location") or "").lower()
    cny_low = (r.get("country") or "").lower()
    sen_val = r.get("seniority") or ""
    jt_low = (r.get("job_type") or "").lower()
    ind_val = r.get("industry") or ""

    cat = (filters.get("category") or filters.get("role") or "").strip()
    if cat and cat.lower() not in ("all", "any"):
        cl = cat.lower()
        if "full stack" in cl or "fullstack" in cl:
            if not ("full stack" in cat_val.lower() or any(k in t_low for k in ("full stack", "fullstack", "full-stack")) or "fullstack" in skills_low or "full stack" in skills_low):
                return False
        elif "backend" in cl or "back end" in cl:
            if not ("backend" in cat_val.lower() or any(k in t_low for k in ("backend", "back end", "back-end"))):
                return False
        elif "frontend" in cl or "front end" in cl:
            if not ("frontend" in cat_val.lower() or any(k in t_low for k in ("frontend", "front end", "front-end"))):
                return False
        elif any(k in cl for k in ("devops", "sre", "cloud", "infrastructure")):
            if not ("devops" in cat_val.lower() or any(k in t_low for k in ("devops", "sre", "site reliability", "platform", "infrastructure"))):
                return False
        elif any(k in cl for k in ("machine learning", "ml", "ai")):
            if not ("machine learning" in cat_val.lower() or any(k in t_low for k in ("machine learning", "ml", "ai ", "ai-", "data scientist"))):
                return False
        elif "data" in cl and ("engineer" in cl or "analytics" in cl):
            if not ("data" in cat_val.lower() or "data engineer" in t_low or "analytics engineer" in t_low):
                return False
        elif any(k in cl for k in ("mobile", "ios", "android")):
            if not ("mobile" in cat_val.lower() or any(k in t_low for k in ("mobile", "ios", "android"))):
                return False
        elif any(k in cl for k in ("security", "cyber")):
            if not ("security" in cat_val.lower() or "security" in t_low or "cyber" in t_low):
                return False
        elif any(k in cl for k in ("qa", "quality", "test")):
            if not ("qa" in cat_val.lower() or any(k in t_low for k in ("qa", "test", "quality"))):
                return False
        elif "product" in cl:
            if "product" not in cat_val.lower() and "product" not in t_low:
                return False
        elif any(k in cl for k in ("design", "ux", "ui")):
            if not ("design" in cat_val.lower() or any(k in t_low for k in ("design", "ux", "ui"))):
                return False
        elif any(k in cl for k in ("software", "engineer", "developer")):
            if not (any(k in cat_val.lower() for k in ("engineer", "developer")) or any(k in t_low for k in ("engineer", "developer"))):
                return False
        elif cl not in cat_val.lower() and cl not in t_low:
            return False

    wm_raw = (filters.get("work_mode") or "").strip()
    if wm_raw and wm_raw.lower() not in ("any", "all"):
        modes = [m.strip().lower() for m in wm_raw.split(",") if m.strip()]
        if modes and len(modes) < 3:
            ok = False
            for m_low in modes:
                if "remote" in m_low and ("remote" in wm_low or "remote" in loc_low or cny_low == "worldwide"):
                    ok = True
                elif "hybrid" in m_low and ("hybrid" in wm_low or "hybrid" in loc_low):
                    ok = True
                elif any(k in m_low for k in ("onsite", "on-site", "office")) and ("onsite" in wm_low or "on-site" in wm_low or ("remote" not in wm_low and "hybrid" not in wm_low)):
                    ok = True
                elif wm_low == m_low:
                    ok = True
            if not ok:
                return False

    sen = (filters.get("seniority") or "").strip()
    if sen and sen.lower() not in ("all", "any"):
        sl = sen.lower()
        if sl in ("junior", "entry", "intern", "entry_junior"):
            if not (sen_val in ("junior", "intern") or any(k in t_low for k in ("junior", "entry", "intern", "new grad", "associate"))):
                return False
        elif sl == "mid":
            if not (sen_val == "mid" or (sen_val not in ("intern", "junior", "director") and "director" not in t_low and "vp" not in t_low)):
                return False
        elif sl == "senior":
            if not (sen_val in ("senior", "lead_staff") or any(k in t_low for k in ("senior", "sr", "lead", "staff"))):
                return False
        elif sl in ("lead_staff", "lead", "staff", "director"):
            if not (sen_val in ("lead_staff", "director") or any(k in t_low for k in ("lead", "staff", "principal", "director", "head of"))):
                return False
        elif sen_val != sl:
            return False

    jt_raw = (filters.get("job_type") or "").strip()
    if jt_raw and jt_raw.lower() not in ("all", "any"):
        types = [t.strip().lower() for t in jt_raw.split(",") if t.strip()]
        if types and len(types) < 4:
            ok = False
            for t in types:
                if t == "internship" and ("intern" in jt_low or any(k in t_low for k in ("intern", "co-op", "apprentice"))):
                    ok = True
                elif t in ("part-time", "part time") and ("part" in jt_low or "part-time" in t_low or "part time" in t_low):
                    ok = True
                elif t == "contract" and ("contract" in jt_low or "contract" in t_low or "freelance" in t_low):
                    ok = True
                elif t in ("full-time", "full time") and ("full" in jt_low or (not jt_low and not any(k in t_low for k in ("intern", "contract", "part")))):
                    ok = True
                elif t in jt_low:
                    ok = True
            if not ok:
                return False

    country = (filters.get("country") or "").strip()
    if country and country.lower() not in ("all", "any"):
        cl = country.lower()
        if cl in ("united states", "usa", "us"):
            if not (cny_low in ("united states", "worldwide") or "remote" in wm_low):
                return False
        elif cl == "worldwide":
            if not (cny_low == "worldwide" or "remote" in wm_low):
                return False
        elif inc_remote:
            if not (cny_low == cl or cl in loc_low or ("remote" in wm_low and cny_low == "worldwide")):
                return False
        elif not (cny_low == cl or cl in loc_low):
            return False

    loc_q = (filters.get("location") or "").strip()
    if loc_q and loc_q.lower() not in ("all", "any", "anywhere in the us"):
        if not (loc_q.lower() in loc_low or (r.get("work_mode") == "Remote")):
            return False

    try:
        min_sal = float(filters.get("min_salary") or 0)
        if min_sal > 0:
            rmax, rmin = float(r.get("max_salary") or 0), float(r.get("min_salary") or 0)
            if not (rmax >= min_sal or (rmin >= min_sal and rmin > 0)):
                return False
    except (ValueError, TypeError):
        pass

    try:
        min_score = int(filters.get("min_score") or 0)
        if min_score > 0 and int(r.get("score") or 0) < min_score:
            return False
    except (ValueError, TypeError):
        pass

    fam_mode = (filters.get("famous_mode") or "all").lower()
    if fam_mode == "hide" and r.get("is_famous"):
        return False
    elif fam_mode == "only" and not r.get("is_famous"):
        return False
    elif fam_mode == "startups" and not r.get("is_startup"):
        return False

    ind = (filters.get("industry") or "").strip()
    if ind and ind.lower() not in ("all", "any"):
        il = ind.lower()
        if il in ("tech", "software") and "tech" not in ind_val.lower():
            return False
        elif il in ("finance", "fintech") and "finance" not in ind_val.lower():
            return False
        elif il in ("health", "healthcare", "bio") and "health" not in ind_val.lower():
            return False
        elif il in ("consulting", "services") and "consulting" not in ind_val.lower():
            return False

    try:
        days = int(filters.get("days") or filters.get("freshness_days") or 0)
        if days > 0:
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
            pa = r.get("posted_at")
            if pa and pa < cutoff:
                return False
    except (ValueError, TypeError):
        pass

    kw = (filters.get("q") or filters.get("keyword") or "").strip().lower()
    if kw:
        comp_low = (r.get("company") or "").lower()
        if not any(kw in hay for hay in (t_low, comp_low, skills_low, loc_low)):
            return False

    if str(filters.get("h1b") or "").lower() in ("1", "true") and not r.get("h1b"):
        return False

    pid_filter = (filters.get("best_profile_id") or filters.get("profile_id") or "").strip()
    if pid_filter and pid_filter.lower() not in ("all", "any") and r.get("best_profile_id") != pid_filter:
        return False

    return True


def query_stored_jobs(filters: dict[str, Any] | None = None, include_all: bool = False) -> dict[str, Any]:
    filters = filters or {}
    inc_remote = str(get_setting("include_worldwide_remote", "true")).lower() in ("true", "1", "yes")
    sort = (filters.get("sort") or "ranked").lower()

    def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if sort == "score_desc":
            return sorted(rows, key=lambda r: (r.get("score") or 0, r.get("opportunity_score") or 0), reverse=True)
        if sort == "salary_desc":
            return sorted(rows, key=lambda r: (r.get("max_salary") or 0, r.get("score") or 0), reverse=True)
        if sort == "date_desc":
            return sorted(rows, key=lambda r: (r.get("posted_at") or "", r.get("opportunity_score") or 0), reverse=True)
        if sort == "company_asc":
            return sorted(rows, key=lambda r: (r.get("company") or "").lower())
        return sorted(rows, key=lambda r: (r.get("opportunity_score") or 0, r.get("score") or 0), reverse=True)

    ws = _ws()
    with ws.lock:
        active = [dict(r) for r in ws.tables["search_jobs"] if r.get("is_active", 1) == 1]

    matched = _sort_rows([r for r in active if _matches_stored_filters(r, filters, inc_remote)])
    jobs = [_unpack_search_row(r) for r in matched]
    all_jobs = [_unpack_search_row(r, compact=True) for r in _sort_rows(active)] if (include_all and len(matched) < len(active)) else []

    cat_cnt: dict[str, int] = {}
    wm_cnt: dict[str, int] = {}
    sen_cnt: dict[str, int] = {}
    jt_cnt: dict[str, int] = {}
    prof_cnt: dict[str, dict[str, Any]] = {}
    for r in active:
        if r.get("category"):
            cat_cnt[r["category"]] = cat_cnt.get(r["category"], 0) + 1
        if r.get("work_mode"):
            wm_cnt[r["work_mode"]] = wm_cnt.get(r["work_mode"], 0) + 1
        if r.get("seniority"):
            sen_cnt[r["seniority"]] = sen_cnt.get(r["seniority"], 0) + 1
        if r.get("job_type"):
            jt_cnt[r["job_type"]] = jt_cnt.get(r["job_type"], 0) + 1
        pid = r.get("best_profile_id")
        if pid:
            cur = prof_cnt.setdefault(pid, {"name": r.get("best_profile_name", ""), "count": 0})
            cur["count"] += 1

    return {
        "jobs": jobs,
        "all_jobs": all_jobs,
        "count": len(jobs),
        "total_all": len(active),
        "meta": get_search_meta() or {},
        "facets": {
            "categories": dict(sorted(cat_cnt.items(), key=lambda x: -x[1])),
            "work_modes": wm_cnt,
            "seniorities": sen_cnt,
            "job_types": dict(sorted(jt_cnt.items(), key=lambda x: -x[1])),
            "profiles": prof_cnt,
        },
    }


def get_saved_search_jobs() -> list[dict[str, Any]]:
    return query_stored_jobs()["jobs"]


def get_search_meta() -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = ws.tables["search_meta"]
        if not rows:
            return None
        r = rows[0]
        return {
            "query": r.get("query", ""),
            "location": r.get("location", ""),
            "total_count": r.get("total_count", 0),
            "sources": json.loads(r.get("sources_json") or "[]"),
            "updated_at": r.get("updated_at", ""),
        }


def get_pending_jobs_count() -> int:
    ws = _ws()
    with ws.lock:
        return len(ws.tables["pending_search_jobs"])


def get_pending_jobs() -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = sorted(
            ws.tables["pending_search_jobs"],
            key=lambda r: (r.get("opportunity_score") or 0, r.get("score") or 0),
            reverse=True,
        )
        return [json.loads(r.get("job_json") or "{}") for r in rows]


def store_pending_jobs(jobs: list[dict[str, Any]], query: str = "") -> int:
    from . import dedup
    now = now_iso()
    added_count = 0
    ws = _ws()
    with ws.lock:
        s_rows = ws.tables["search_jobs"]
        p_rows = ws.tables["pending_search_jobs"]
        s_keys = {r.get("job_key") for r in s_rows}
        s_ct = {(r.get("company", "").lower().strip(), r.get("title", "").lower().strip()) for r in s_rows}
        p_keys = {r.get("job_key") for r in p_rows}

        for j in jobs:
            clean_job_dict(j)
            canon_key = dedup.job_key(j) if hasattr(dedup, "job_key") else ""
            key = j.get("job_key") or canon_key or j.get("id")
            if not key:
                continue
            j["job_key"] = key
            if key in s_keys or (canon_key and canon_key in s_keys):
                continue
            if j.get("company") and j.get("title"):
                if (j["company"].lower().strip(), j["title"].lower().strip()) in s_ct:
                    continue
            if key in p_keys or (canon_key and canon_key in p_keys):
                continue

            c_meta = classify_job(j)
            j["category"] = c_meta["category"]
            j["seniority"] = c_meta["seniority"]
            j["job_type"] = c_meta["job_type"]
            j["country"] = c_meta["country"]
            j["work_mode"] = c_meta["work_mode"]
            p_rows.append(ws._normalize_row("pending_search_jobs", {
                "job_key": key,
                "query": query,
                "title": clean_text(j.get("title", "")),
                "company": clean_text(j.get("company", "")),
                "location": clean_text(j.get("location", "")),
                "work_mode": c_meta["work_mode"],
                "category": c_meta["category"],
                "job_type": c_meta["job_type"],
                "seniority": c_meta["seniority"],
                "country": c_meta["country"],
                "min_salary": c_meta["min_salary"],
                "max_salary": c_meta["max_salary"],
                "score": j.get("score", 0),
                "opportunity_score": j.get("opportunity_score", 0),
                "is_famous": c_meta["is_famous"],
                "is_startup": c_meta["is_startup"],
                "industry": c_meta["industry"],
                "h1b": c_meta["h1b"],
                "source_kind": j.get("source_kind", ""),
                "source_names": ",".join(j.get("source_names", [])),
                "posted_at": j.get("posted_at", ""),
                "job_json": json.dumps(j),
                "discovered_at": now,
                "skills_text": c_meta.get("skills_text", ""),
                "best_profile_id": j.get("best_profile_id", ""),
                "best_profile_name": j.get("best_profile_name", ""),
            }))
            p_keys.add(key)
            added_count += 1
        if added_count:
            ws.flush_cache()
    return added_count


# ------------------------------------------------------------------ Auto Search, Session, View Filters

def get_auto_search_settings() -> dict[str, Any]:
    enabled = get_setting("bg_search_enabled", "1") == "1"
    try:
        interval_hours = float(get_setting("bg_search_interval_hours", "5.0"))
    except ValueError:
        interval_hours = 5.0
    last_run = get_setting("bg_search_last_run", "") or None
    status = get_setting("bg_search_status", "idle")
    next_run = None
    if enabled and interval_hours > 0:
        if last_run:
            try:
                last_dt = datetime.datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                next_run = (last_dt + datetime.timedelta(hours=interval_hours)).isoformat()
            except Exception:
                pass
        else:
            next_run = "Immediate"
    return {
        "enabled": enabled,
        "interval_hours": interval_hours,
        "last_run": last_run,
        "next_run": next_run,
        "status": status,
        "pending_count": get_pending_jobs_count(),
    }


def set_auto_search_settings(enabled: bool = True, interval_hours: float = 5.0) -> dict[str, Any]:
    set_setting("bg_search_enabled", "1" if enabled else "0")
    set_setting("bg_search_interval_hours", str(interval_hours))
    return get_auto_search_settings()


def get_session_state() -> dict[str, Any]:
    ws = _ws()
    with ws.lock:
        rows = ws.tables["session_state"]
        if rows:
            return dict(rows[0])
        return {"current_state": "idle", "last_tool": "", "updated_at": now_iso()}


def set_session_state(current_state: str, last_tool: str = "", session_id: str = "default") -> dict[str, Any]:
    iso = now_iso()
    ws = _ws()
    with ws.lock:
        curr = ws.tables["session_state"][0] if ws.tables["session_state"] else {"id": 1, "last_tool": ""}
        new_last = last_tool if last_tool else curr.get("last_tool", "")
        ws.tables["session_state"] = [{"id": 1, "current_state": current_state, "last_tool": new_last, "updated_at": iso}]
        ws.flush_durable()
    return get_session_state()


DEFAULT_VIEW_FILTERS = {
    "job_style": "",
    "roles": [],
    "work_mode": "any",
    "locations": [],
    "relocation": False,
    "visa_need": False,
    "visa_countries": [],
    "min_salary": 0,
    "currency": "USD",
    "period": "year",
    "contract_types": [],
    "seniority": [],
    "company_sizes": [],
    "industries": [],
    "confirmed_industries": [],
    "company_stages": [],
    "markets_served": [],
    "languages": [],
    "excluded_companies": [],
    "excluded_keywords": [],
    "posting_age": 30,
    "show_unknown_salary": True,
}

_EXTRA_LIST_KEYS = ("confirmed_industries", "company_stages", "markets_served", "languages")


def _normalize_str_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
        return [x.strip() for x in val.split(",") if x.strip()]
    return []


def _deserialize_view_filter_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    extra_raw = out.pop("extra_filters", None)
    if isinstance(extra_raw, str) and extra_raw.strip():
        try:
            extra_obj = json.loads(extra_raw)
            if isinstance(extra_obj, dict):
                for k, v in extra_obj.items():
                    out.setdefault(k, v)
        except Exception:
            pass
    for list_col in ("roles", "locations", "visa_countries", "contract_types", "seniority", "company_sizes", "industries", "excluded_companies", "excluded_keywords", *_EXTRA_LIST_KEYS):
        out[list_col] = _normalize_str_list(out.get(list_col))
    out["relocation"] = bool(out.get("relocation"))
    out["visa_need"] = bool(out.get("visa_need"))
    out["show_unknown_salary"] = bool(out.get("show_unknown_salary", True))
    return out


def get_view_filters(session_id: str = "default") -> dict[str, Any]:
    ws = _ws()
    with ws.lock:
        rows = [r for r in ws.tables["view_filters"] if r.get("session_id") == session_id]
        row = dict(rows[-1]) if rows else None

    if not row:
        res = dict(DEFAULT_VIEW_FILTERS)
        res["session_id"] = session_id
        for k in _EXTRA_LIST_KEYS:
            res[k] = _normalize_str_list(res.get(k))
        return res

    return _deserialize_view_filter_row(row)


def save_view_filters(filters: dict[str, Any], session_id: str = "default") -> dict[str, Any]:
    d = get_view_filters(session_id)
    d.update(filters)
    d["session_id"] = session_id
    iso_now = now_iso()

    def _ser(v: Any) -> str:
        if isinstance(v, (list, tuple, set)):
            return json.dumps(list(v))
        return str(v or "")

    extra_dict: dict[str, Any] = {k: _normalize_str_list(d.get(k)) for k in _EXTRA_LIST_KEYS}
    known_keys = set(DEFAULT_VIEW_FILTERS.keys()) | set(_EXTRA_LIST_KEYS) | {"id", "session_id", "updated_at", "extra_filters"}
    for k, v in d.items():
        if k not in known_keys and v is not None:
            extra_dict[k] = v
    extra_payload = json.dumps(extra_dict)
    rec_vals = {
        "session_id": session_id,
        "job_style": d.get("job_style", ""),
        "roles": _ser(d.get("roles", [])),
        "work_mode": d.get("work_mode", "any"),
        "locations": _ser(d.get("locations", [])),
        "relocation": 1 if d.get("relocation") else 0,
        "visa_need": 1 if d.get("visa_need") else 0,
        "visa_countries": _ser(d.get("visa_countries", [])),
        "min_salary": float(d.get("min_salary") or 0),
        "currency": d.get("currency", "USD"),
        "period": d.get("period", "year"),
        "contract_types": _ser(d.get("contract_types", [])),
        "seniority": _ser(d.get("seniority", [])),
        "company_sizes": _ser(d.get("company_sizes", [])),
        "industries": _ser(d.get("industries", [])),
        "excluded_companies": _ser(d.get("excluded_companies", [])),
        "excluded_keywords": _ser(d.get("excluded_keywords", [])),
        "posting_age": int(d.get("posting_age") or 30),
        "show_unknown_salary": 1 if d.get("show_unknown_salary", True) else 0,
        "extra_filters": extra_payload,
        "updated_at": iso_now,
    }
    ws = _ws()
    with ws.lock:
        tbl = ws.tables["view_filters"]
        existing = next((r for r in tbl if r.get("session_id") == session_id), None)
        if existing:
            existing.update(rec_vals)
        else:
            rec_vals["id"] = ws.next_id("view_filters")
            tbl.append(ws._normalize_row("view_filters", rec_vals))
        ws.flush_durable()
    return get_view_filters(session_id)


# ------------------------------------------------------------------ Radar & Refresh

def get_radar_state() -> dict[str, Any]:
    ws = _ws()
    with ws.lock:
        rows = ws.tables["radar_state"]
        if rows:
            return dict(rows[0])
        return {"id": 1, "last_poll_at": None, "next_poll_at": None, "interval_seconds": 600, "failure_count": 0, "status": "idle", "last_error": ""}


def update_radar_state(**kwargs: Any) -> dict[str, Any]:
    valid_cols = {"last_poll_at", "next_poll_at", "interval_seconds", "failure_count", "status", "last_error"}
    updates = {k: v for k, v in kwargs.items() if k in valid_cols}
    if not updates:
        return get_radar_state()
    ws = _ws()
    with ws.lock:
        if not ws.tables["radar_state"]:
            ws._seed_defaults()
        ws.tables["radar_state"][0].update(updates)
        ws.flush_durable()
    return get_radar_state()


def get_refresh_states() -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        return sorted([dict(r) for r in ws.tables["refresh_state"]], key=lambda r: r.get("source") or "")


def get_refresh_state(source: str) -> dict[str, Any]:
    ws = _ws()
    with ws.lock:
        row = next((r for r in ws.tables["refresh_state"] if r.get("source") == source), None)
        if row:
            return dict(row)
    return {"source": source, "last_run_at": None, "ttl_seconds": 43200, "last_new_ratio": 0.0, "last_total": 0, "last_new": 0}


def update_refresh_state(source: str, **kwargs: Any) -> dict[str, Any]:
    curr = get_refresh_state(source)
    curr.update(kwargs)
    rec = {
        "source": source,
        "last_run_at": curr.get("last_run_at"),
        "ttl_seconds": int(curr.get("ttl_seconds") or 43200),
        "last_new_ratio": float(curr.get("last_new_ratio") or 0.0),
        "last_total": int(curr.get("last_total") or 0),
        "last_new": int(curr.get("last_new") or 0),
    }
    ws = _ws()
    with ws.lock:
        tbl = ws.tables["refresh_state"]
        existing = next((r for r in tbl if r.get("source") == source), None)
        if existing:
            existing.update(rec)
        else:
            tbl.append(rec)
        ws.flush_durable()
    return get_refresh_state(source)


# ------------------------------------------------------------------ Dismissals, Tombstones, Deletions

def add_dismissal(job_id: str, reason: str) -> None:
    ws = _ws()
    with ws.lock:
        ws.tables["dismissals"].append({
            "id": ws.next_id("dismissals"),
            "job_id": str(job_id),
            "reason": str(reason),
            "created_at": now_iso(),
        })
        for r in ws.tables["jobs"]:
            if r.get("id") == str(job_id) or r.get("job_key") == str(job_id):
                r["seen_by_user"] = 1
        ws.flush_durable()
        ws.flush_cache()


def get_dismissals(job_id: str | None = None) -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = ws.tables["dismissals"]
        if job_id:
            rows = [r for r in rows if r.get("job_id") == str(job_id)]
        return [dict(r) for r in sorted(rows, key=lambda x: x.get("id") or 0, reverse=True)]


def count_dismissals() -> int:
    ws = _ws()
    with ws.lock:
        return len(ws.tables["dismissals"])


def add_tombstone(url_hash: str, fingerprint: str, conn: Any = None) -> None:
    ws = _ws()
    with ws.lock:
        ws.tables["tombstones"].append({
            "id": ws.next_id("tombstones"),
            "url_hash": url_hash or "",
            "fingerprint": fingerprint or "",
            "deleted_at": now_iso(),
        })
        if conn is None:
            ws.flush_durable()


def is_tombstoned(url_hash: str = "", fingerprint: str = "") -> bool:
    if not url_hash and not fingerprint:
        return False
    ws = _ws()
    with ws.lock:
        for r in ws.tables["tombstones"]:
            if url_hash and r.get("url_hash") == url_hash:
                return True
            if fingerprint and r.get("fingerprint") == fingerprint:
                return True
    return False


def log_deletion(count: int) -> None:
    if count <= 0:
        return
    ws = _ws()
    with ws.lock:
        ws.tables["deletions_log"].append({
            "id": ws.next_id("deletions_log"),
            "count": int(count),
            "deleted_at": now_iso(),
            "acknowledged": 0,
        })
        ws.flush_durable()


def get_last_deletion() -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = ws.tables["deletions_log"]
        return dict(rows[-1]) if rows else None


def ack_deletions() -> None:
    ws = _ws()
    with ws.lock:
        for r in ws.tables["deletions_log"]:
            if not r.get("acknowledged"):
                r["acknowledged"] = 1
        ws.flush_durable()


def get_cleanup_status() -> dict[str, Any]:
    grace_hours = int(get_setting("cleanup_grace_hours", "24"))
    ws = _ws()
    with ws.lock:
        unack_count = sum(int(r.get("count") or 0) for r in ws.tables["deletions_log"] if not r.get("acknowledged"))
        warning_count = sum(
            1 for r in ws.tables["jobs"]
            if r.get("freshness_state") == "expired" and not r.get("keep_flag") and r.get("delete_at") is not None
        )
        t_count = len(ws.tables["tombstones"])
    return {
        "grace_hours": grace_hours,
        "warning_count": warning_count,
        "recently_deleted": unack_count,
        "tombstones_count": t_count,
    }


# ------------------------------------------------------------------ Jobs Ingestion & Lifecycle

def _ingest_job_locked(ws: store.WorkspaceStore, j: dict[str, Any]) -> Optional[dict[str, Any]]:
    from . import dedup
    if not isinstance(j, dict):
        return None
    clean_job_dict(j)
    title = clean_text(j.get("title") or "")
    company = clean_text(j.get("company") or "")
    if not title or not company:
        return None

    location = clean_text(j.get("location") or "")
    work_mode = clean_text(j.get("work_mode") or "")
    url = clean_text(j.get("url") or j.get("link") or "")
    source_name = j.get("source") or (j.get("source_names", [""])[0] if j.get("source_names") else "Search")

    url_hash = j.get("url_hash") or dedup.build_url_hash(url, linkedin_id=j.get("linkedin_id", ""))
    fingerprint = j.get("fingerprint") or dedup.build_fingerprint(company, title, location, work_mode)

    for tb in ws.tables["tombstones"]:
        if (url_hash and tb.get("url_hash") == url_hash) or (fingerprint and tb.get("fingerprint") == fingerprint):
            return {"status": "tombstoned", "job_id": None, "is_new": False}

    iso_now = now_iso()
    c_meta = classify_job(j)
    work_mode = c_meta["work_mode"] or work_mode
    category = c_meta["category"]
    job_type = c_meta["job_type"]
    seniority = c_meta["seniority"]
    country = c_meta["country"]
    min_sal = float(c_meta["min_salary"] or j.get("min_salary") or 0)
    max_sal = float(c_meta["max_salary"] or j.get("max_salary") or 0)
    industry = c_meta["industry"]
    skills_text = c_meta.get("skills_text", "")
    is_famous = 1 if c_meta.get("is_famous") else 0
    is_startup = 1 if c_meta.get("is_startup") else 0
    visa_sponsor = 1 if (c_meta.get("h1b") or j.get("visa_sponsor") or j.get("h1b")) else 0
    company_size = j.get("company_size") or ("startup" if is_startup else ("enterprise" if is_famous else "midsize"))
    score = int(j.get("score") or 0)
    opp_score = int(j.get("opportunity_score") or score)
    fit_score = int(j.get("fit_score") or score)

    posted_at = j.get("posted_at") or ""
    age_days = 0.0
    if posted_at:
        d = parse_date(posted_at)
        if d:
            age_days = max(0.0, (datetime.datetime.now(datetime.timezone.utc) - d).total_seconds() / 86400.0)
    freshness_state = "expired" if age_days > 60 else ("stale" if age_days >= 30 else "active")

    jobs_tbl = ws.tables["jobs"]
    srcs_tbl = ws.tables["job_sources"]

    existing_job = None
    if url_hash:
        src_row = next((s for s in srcs_tbl if s.get("url_hash") == url_hash), None)
        if src_row:
            existing_job = next((r for r in jobs_tbl if r.get("id") == src_row.get("job_id")), None)
    if not existing_job and fingerprint:
        existing_job = next((r for r in jobs_tbl if r.get("fingerprint") == fingerprint), None)

    if existing_job:
        job_id = existing_job["id"]
        existing_job["repost_count"] = int(existing_job.get("repost_count") or 0) + 1
        existing_job["last_seen_at"] = iso_now
        existing_job["is_new"] = 0
        existing_job["updated_at"] = iso_now
        if url_hash:
            src_row = next((s for s in srcs_tbl if s.get("url_hash") == url_hash), None)
            if src_row:
                src_row["last_seen_at"] = iso_now
            else:
                srcs_tbl.append(ws._normalize_row("job_sources", {
                    "id": ws.next_id("job_sources"),
                    "job_id": job_id, "source": source_name, "url": url,
                    "url_hash": url_hash, "first_seen_at": iso_now, "last_seen_at": iso_now,
                }))
        return {"status": "merged", "job_id": job_id, "is_new": False}

    possible_dup = 0
    co_prefix = company.lower()[:8]
    for cand in jobs_tbl:
        if co_prefix in (cand.get("company") or "").lower():
            sim = dedup.title_similarity(cand.get("title") or "", title)
            if 0.80 <= sim < 1.0:
                possible_dup = 1
                break

    existing_ids = {r.get("id") for r in jobs_tbl}
    existing_keys = {r.get("job_key") for r in jobs_tbl}
    new_id = str(j.get("id") or uuid.uuid4())
    if new_id in existing_ids:
        new_id = str(uuid.uuid4())
    job_key = j.get("job_key") or new_id or (dedup.job_key(j) if hasattr(dedup, "job_key") else new_id[:16])
    if job_key in existing_keys:
        job_key = f"{job_key}_{new_id[:8]}"
        while job_key in existing_keys:
            job_key = f"{job_key}_{uuid.uuid4().hex[:6]}"

    j_created = j.get("created_at") or j.get("date_posted") or iso_now
    j_first_seen = j.get("first_seen_at") or j_created
    j_last_seen = j.get("last_seen_at") or iso_now

    jobs_tbl.append(ws._normalize_row("jobs", {
        "id": new_id, "job_key": job_key, "title": title, "company": company,
        "location": location, "work_mode": work_mode, "source": source_name,
        "url": url, "url_hash": url_hash, "fingerprint": fingerprint,
        "description": clean_text(j.get("description") or ""),
        "score": score, "fit_score": fit_score, "opportunity_score": opp_score,
        "found_at": iso_now, "first_seen_at": j_first_seen, "last_seen_at": j_last_seen,
        "is_new": 1, "seen_by_user": 0, "repost_count": 0,
        "possible_duplicate": possible_dup, "freshness_state": freshness_state,
        "delete_at": None, "keep_flag": 0, "closed_checked_at": None,
        "job_json": json.dumps(j), "created_at": j_created, "updated_at": iso_now,
        "category": category, "job_type": job_type, "seniority": seniority,
        "country": country, "min_salary": min_sal, "max_salary": max_sal,
        "company_size": company_size, "industry": industry,
        "visa_sponsor": visa_sponsor, "skills_text": skills_text,
    }))
    if url_hash and not any(s.get("url_hash") == url_hash for s in srcs_tbl):
        srcs_tbl.append(ws._normalize_row("job_sources", {
            "id": ws.next_id("job_sources"),
            "job_id": new_id, "source": source_name, "url": url,
            "url_hash": url_hash, "first_seen_at": iso_now, "last_seen_at": iso_now,
        }))
    return {"status": "inserted", "job_id": new_id, "is_new": True}


def ingest_job(j: dict[str, Any], conn: Any = None) -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        res = _ingest_job_locked(ws, j)
        if conn is None and res is not None:
            ws.flush_cache()
        return res


def store_jobs(jobs: list[dict[str, Any]], query: str = "", location: str = "") -> dict[str, int]:
    inserted = merged = tombstoned = 0
    now = now_iso()
    ws = _ws()
    with ws.lock:
        for j in jobs:
            res = _ingest_job_locked(ws, j)
            if not res:
                continue
            st = res["status"]
            if st == "inserted":
                inserted += 1
            elif st == "merged":
                merged += 1
            elif st == "tombstoned":
                tombstoned += 1
        for j in jobs:
            _upsert_search_job_locked(ws, j, query, now)
        total_now = sum(1 for r in ws.tables["search_jobs"] if r.get("is_active", 1) == 1)
        ws.tables["search_meta"] = [ws._normalize_row("search_meta", {
            "id": 1, "query": query, "location": location,
            "total_count": total_now, "sources_json": "[]", "updated_at": now,
        })]
        ws.flush_cache()
    return {"inserted": inserted, "merged": merged, "tombstoned": tombstoned, "total": len(jobs)}


def save_job(job: dict[str, Any]) -> str:
    res = ingest_job(job)
    return res["job_id"] if res and res.get("job_id") else ""


def get_user_preferences() -> dict[str, Any]:
    return get_view_filters("default")


def update_application_status(job_id: str, status: str) -> bool:
    ws = _ws()
    with ws.lock:
        now = now_iso()
        updated = False
        for a in ws.tables["applications"]:
            if a.get("id") == job_id or a.get("job_id") == job_id:
                a["status"] = status
                a["updated_at"] = now
                updated = True
                if status == "applied":
                    jid = a.get("job_id") or job_id
                    for j in ws.tables["jobs"]:
                        if j.get("id") == jid or j.get("job_key") == jid:
                            j["keep_flag"] = 1
                            j["delete_at"] = None
        if updated:
            ws.flush_durable()
            ws.flush_cache()
        return updated


def query_jobs(view_filters: dict[str, Any] | None = None, session_id: str = "default", profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Filter active jobs in Python, rank with soft preferences + freshness, and evaluate usable range."""
    filters = get_view_filters(session_id)
    if view_filters and isinstance(view_filters, dict):
        filters.update(view_filters)

    if profile is None:
        try:
            profile = get_profile()
        except Exception:
            profile = {}

    ws = _ws()
    with ws.lock:
        if not ws.tables["jobs"] and ws.tables["search_jobs"]:
            for sr in list(ws.tables["search_jobs"]):
                try:
                    _ingest_job_locked(ws, json.loads(sr.get("job_json") or "{}"))
                except Exception:
                    pass
            ws.flush_cache()
        rows = sorted(
            [dict(r) for r in ws.tables["jobs"]],
            key=lambda r: (r.get("opportunity_score") or 0, r.get("score") or 0),
            reverse=True,
        )
        sources_map: dict[str, list[str]] = {}
        for sr in ws.tables["job_sources"]:
            jid, sname = sr.get("job_id"), sr.get("source")
            if jid and sname:
                lst = sources_map.setdefault(jid, [])
                if sname not in lst:
                    lst.append(sname)

    candidate_jobs = []
    closing_soon = []
    for r in rows:
        j_dict = json.loads(r.get("job_json") or "{}")
        j_dict["id"] = r["id"]
        j_sources = sources_map.get(r["id"]) or ([r["source"]] if r.get("source") else [])
        if not j_sources and j_dict.get("source"):
            j_sources = [j_dict["source"]]
        j_dict["sources"] = j_sources
        for col in (
            "job_key", "title", "company", "location", "work_mode", "freshness_state",
            "delete_at", "repost_count", "min_salary", "max_salary", "category",
            "seniority", "job_type", "industry", "company_size", "score", "opportunity_score",
        ):
            j_dict[col] = r.get(col)
        j_dict["keep_flag"] = bool(r.get("keep_flag"))
        j_dict["is_new"] = bool(r.get("is_new"))
        j_dict["possible_duplicate"] = bool(r.get("possible_duplicate"))

        if r.get("freshness_state") == "expired" or (r.get("delete_at") is not None and not r.get("keep_flag")):
            closing_soon.append(j_dict)
        else:
            candidate_jobs.append(j_dict)

    roles_filter = [r.lower().strip() for r in (filters.get("roles") or []) if r and r.strip()]
    wm_filter = (filters.get("work_mode") or "any").lower().strip()
    locs_filter = [l.lower().strip() for l in (filters.get("locations") or []) if l and l.strip()]
    relocation = bool(filters.get("relocation"))
    visa_need = bool(filters.get("visa_need"))
    visa_countries = [c.lower().strip() for c in (filters.get("visa_countries") or []) if c and c.strip()]
    min_sal = float(filters.get("min_salary") or 0)
    show_unknown_salary = bool(filters.get("show_unknown_salary", True))
    contract_types = [c.lower().strip() for c in (filters.get("contract_types") or []) if c and c.strip()]
    if filters.get("job_type") and str(filters["job_type"]).lower() not in ("any", ""):
        contract_types.append(str(filters["job_type"]).lower().strip())
    excluded_cos = [c.lower().strip() for c in (filters.get("excluded_companies") or []) if c and c.strip()]
    excluded_kws = [k.lower().strip() for k in (filters.get("excluded_keywords") or []) if k and k.strip()]
    posting_age = int(filters.get("posting_age") or 30)

    def _check_role(j):
        if not roles_filter:
            return True
        hay = f"{j.get('title', '')} {j.get('category', '')} {j.get('skills_text', '')}".lower()
        return any(r in hay for r in roles_filter)

    def _check_work_mode(j):
        if not wm_filter or wm_filter in ("any", "all"):
            return True
        j_wm = (j.get("work_mode") or "").lower()
        j_loc = (j.get("location") or "").lower()
        if "remote" in wm_filter:
            return "remote" in j_wm or "remote" in j_loc or j.get("country") == "worldwide"
        if "hybrid" in wm_filter:
            return "hybrid" in j_wm or "hybrid" in j_loc
        if "onsite" in wm_filter or "on-site" in wm_filter:
            return ("remote" not in j_wm and "hybrid" not in j_wm) or "onsite" in j_wm or "on-site" in j_wm
        return True

    def _check_location(j):
        if not locs_filter or relocation:
            return True
        from . import regions
        return regions.job_matches_confirmed_places(j, locs_filter, wm_filter)

    confirmed_industries = [i.lower().strip() for i in (filters.get("confirmed_industries") or []) if i and str(i).strip() and str(i).lower().strip() not in ("any", "all")]
    company_stages = [s.lower().strip() for s in (filters.get("company_stages") or []) if s and str(s).strip() and str(s).lower().strip() not in ("any", "all")]
    markets_served = [m.lower().strip() for m in (filters.get("markets_served") or []) if m and str(m).strip() and str(m).lower().strip() not in ("any", "all")]
    languages_filter = [lg.lower().strip() for lg in (filters.get("languages") or []) if lg and str(lg).strip() and str(lg).lower().strip() not in ("any", "all")]

    def _job_hay(j):
        return f"{j.get('title', '')} {j.get('company', '')} {j.get('industry', '')} {j.get('market_served', '')} {j.get('stage', '')} {j.get('company_size', '')} {j.get('languages', '')} {j.get('language', '')} {' '.join(str(t) for t in (j.get('tags') or []))} {j.get('description', '')}".lower()

    def _check_confirmed_industry(j):
        if not confirmed_industries:
            return True
        j_ind = (j.get("industry") or "").lower()
        hay = _job_hay(j)
        return any(ind in j_ind or re.search(rf"\b{re.escape(ind)}\b", hay) for ind in confirmed_industries)

    def _check_company_stage(j):
        if not company_stages:
            return True
        from . import scoring
        stage_raw = f"{j.get('stage', '')} {j.get('company_size', '')} {scoring.classify_company_stage(j)}".lower()
        hay = _job_hay(j)
        aliases = {
            "startup": ("startup", "seed", "series a", "early-stage", "early stage"),
            "scale-up": ("scale-up", "scaleup", "scale up", "series b", "series c", "series d", "growth"),
            "scaleup": ("scale-up", "scaleup", "scale up", "series b", "series c", "growth"),
            "scale up": ("scale-up", "scaleup", "scale up", "series b", "series c", "growth"),
            "public": ("public", "publicly traded", "nasdaq", "nyse", "enterprise", "fortune 500"),
        }
        return any(any(t in stage_raw or re.search(rf"\b{re.escape(t)}\b", hay) for t in aliases.get(st, (st,))) for st in company_stages)

    def _check_market_served(j):
        if not markets_served:
            return True
        hay = _job_hay(j)
        aliases = {
            "b2b": ("b2b", "business-to-business", "saas"),
            "b2c": ("b2c", "consumer", "marketplace"),
            "enterprise": ("enterprise", "fortune 500", "large organizations"),
            "smb": ("smb", "small business", "mid-market", "midmarket"),
            "developer tools": ("developer tools", "devtools", "sdk", "api platform", "for developers"),
            "devtools": ("developer tools", "devtools", "sdk", "api platform", "for developers"),
        }
        return any(any(re.search(rf"\b{re.escape(t)}\b", hay) for t in aliases.get(mk, (mk,))) for mk in markets_served)

    def _check_languages(j):
        if not languages_filter:
            return True
        hay = _job_hay(j)
        for lg in languages_filter:
            if lg == "bilingual":
                if "bilingual" in hay or ("french" in hay and "english" in hay) or ("arabic" in hay and "french" in hay) or ("spanish" in hay and "english" in hay):
                    return True
            elif re.search(rf"\b{re.escape(lg)}\b", hay):
                return True
        return False

    def _check_visa(j):
        if not visa_need:
            return True
        if j.get("visa_sponsor") or j.get("h1b"):
            return True
        desc = (j.get("description") or "").lower()
        if any(term in desc for term in ["visa sponsorship", "h-1b", "h1b", "sponsorship available"]):
            return True
        if visa_countries:
            j_loc = (j.get("location") or "").lower()
            return any(vc in j_loc for vc in visa_countries)
        return False

    def _check_salary(j):
        if min_sal <= 0:
            return True
        if j.get("max_salary", 0) > 0 or j.get("min_salary", 0) > 0:
            return (j.get("max_salary") or j.get("min_salary") or 0) >= min_sal
        return show_unknown_salary

    def _check_contract_type(j):
        if not contract_types:
            return True
        hay = f"{(j.get('job_type') or '').lower()} {(j.get('title') or '').lower()} {(j.get('description') or '')[:400].lower()}"
        is_intern = bool(re.search(r"\b(intern|internship|stage|stagiaire|alternance|pfe|co-?op|student|praktik)\b", hay))
        wants_intern = any("intern" in ct or "pfe" in ct or "stage" in ct for ct in contract_types)
        wants_fulltime = any("full" in ct for ct in contract_types)
        if wants_intern and not wants_fulltime:
            return is_intern
        if wants_fulltime and not wants_intern:
            return not is_intern
        return any(ct in hay for ct in contract_types)

    def _check_excluded_companies(j):
        if not excluded_cos:
            return True
        comp = (j.get("company") or "").lower()
        return not any(ec in comp for ec in excluded_cos)

    def _check_excluded_keywords(j):
        if not excluded_kws:
            return True
        hay = f"{j.get('title', '')} {j.get('description', '')}".lower()
        return not any(kw in hay for kw in excluded_kws)

    def _check_posting_age(j):
        if posting_age <= 0 or not j.get("posted_at"):
            return True
        d = parse_date(j.get("posted_at"))
        if not d:
            return True
        return max(0.0, (datetime.datetime.now(datetime.timezone.utc) - d).total_seconds() / 86400.0) <= posting_age

    removed_counts = {
        "roles": sum(1 for j in candidate_jobs if not _check_role(j)) if roles_filter else 0,
        "work_mode": sum(1 for j in candidate_jobs if not _check_work_mode(j)) if (wm_filter and wm_filter not in ("any", "all")) else 0,
        "location": sum(1 for j in candidate_jobs if not _check_location(j)) if (locs_filter and not relocation) else 0,
        "visa": sum(1 for j in candidate_jobs if not _check_visa(j)) if visa_need else 0,
        "salary": sum(1 for j in candidate_jobs if not _check_salary(j)) if min_sal > 0 else 0,
        "contract_types": sum(1 for j in candidate_jobs if not _check_contract_type(j)) if contract_types else 0,
        "excluded_companies": sum(1 for j in candidate_jobs if not _check_excluded_companies(j)) if excluded_cos else 0,
        "excluded_keywords": sum(1 for j in candidate_jobs if not _check_excluded_keywords(j)) if excluded_kws else 0,
        "posting_age": sum(1 for j in candidate_jobs if not _check_posting_age(j)) if posting_age > 0 else 0,
        "industry": sum(1 for j in candidate_jobs if not _check_confirmed_industry(j)) if confirmed_industries else 0,
        "company_stage": sum(1 for j in candidate_jobs if not _check_company_stage(j)) if company_stages else 0,
        "market_served": sum(1 for j in candidate_jobs if not _check_market_served(j)) if markets_served else 0,
        "languages": sum(1 for j in candidate_jobs if not _check_languages(j)) if languages_filter else 0,
    }

    checks = (_check_role, _check_work_mode, _check_location, _check_visa, _check_salary,
              _check_contract_type, _check_excluded_companies, _check_excluded_keywords,
              _check_posting_age, _check_confirmed_industry, _check_company_stage,
              _check_market_served, _check_languages)
    matching_jobs = []
    for j in candidate_jobs:
        if all(fn(j) for fn in checks):
            if not (j.get("max_salary", 0) > 0 or j.get("min_salary", 0) > 0):
                j["unknown_salary"] = True
            matching_jobs.append(j)

    sen_prefs = [s.lower().strip() for s in (filters.get("seniority") or []) if s and s.strip()]
    size_prefs = [s.lower().strip() for s in (filters.get("company_sizes") or []) if s and s.strip()]
    ind_prefs = [i.lower().strip() for i in (filters.get("industries") or []) if i and i.strip()]

    for j in matching_jobs:
        rank_score = float(j.get("opportunity_score") or j.get("score") or 0)
        if sen_prefs and any(sp in (j.get("seniority") or "").lower() or sp in (j.get("title") or "").lower() for sp in sen_prefs):
            rank_score += 15.0
        if size_prefs and any(sp in (j.get("company_size") or "").lower() for sp in size_prefs):
            rank_score += 10.0
        if ind_prefs and any(ip in (j.get("industry") or "").lower() for ip in ind_prefs):
            rank_score += 10.0
        j["rank_score"] = round(rank_score, 1)

    from . import freshness, scoring, lifecycle
    for j in matching_jobs:
        fresh_meta = freshness.format_freshness_badge(j)
        j["posted_hours_ago"] = fresh_meta["posted_hours_ago"]
        j["is_fresh_48h"] = fresh_meta["is_fresh"]
        j["freshness_badge"] = fresh_meta["badge"]
        j["freshness_label"] = fresh_meta["label"]

    matching_jobs.sort(key=lambda j: (1 if j.get("is_fresh_48h") else 0, j.get("rank_score", 0), j.get("score", 0)), reverse=True)

    level_shift = int(filters.get("level_shift", 0))
    for j in matching_jobs:
        lbl, gaps = scoring.classify_job_fit(j, profile=profile, level_shift=level_shift)
        j["label"] = lbl
        j["top_gaps"] = gaps
        j.update(lifecycle.evaluate_job_flags(j))

    total_count = len(matching_jobs)
    if 10 <= total_count <= 300:
        usable_gate = {"usable": True, "status": "ok", "count": total_count, "message": f"{total_count} matches found, within the optimal 10-300 range.", "suggestion": None, "actions": ["browse_jobs", "prepare_application"]}
    elif total_count < 10:
        usable_gate = {"usable": False, "status": "too_few", "count": total_count, "message": f"Only {total_count} matches found (below minimum threshold of 10).", "suggestion": "Offer to loosen one filter (such as role, work mode, or salary), or run a wider search or refresh.", "actions": ["loosen_filter", "wider_search", "run_refresh"]}
    else:
        usable_gate = {"usable": False, "status": "too_many", "count": total_count, "message": f"{total_count} matches found (exceeds recommended threshold of 300).", "suggestion": "Offer to tighten filters by minimum salary, seniority, or specific locations.", "actions": ["tighten_salary", "tighten_seniority", "tighten_location"]}

    hidden_count = max(0, len(candidate_jobs) - total_count)
    return {
        "jobs": matching_jobs,
        "count": total_count,
        "total_active_pool": len(candidate_jobs),
        "hidden_count": hidden_count,
        "hidden_message": f"{hidden_count} hidden by your filters",
        "closing_soon": closing_soon,
        "closing_soon_count": len(closing_soon),
        "removed_counts": removed_counts,
        "usable_gate": usable_gate,
        "ready_to_apply_count": get_ready_to_apply_count(session_id),
        "view_filters": filters,
    }


# ------------------------------------------------------------------ Signals, Company Briefs, Contacts, Outreach

def ingest_signal(sig: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    s = dict(sig)
    sig_id = s.get("id") or f"sig_{uuid.uuid4().hex[:12]}"
    sig_type = s.get("type") or "hiring_post"
    url = s.get("url") or ""
    url_hash = s.get("url_hash") or (url if url else sig_id)
    company = s.get("company") or "Unknown Company"
    status = s.get("status") or "fresh"
    likes = int(s.get("likes") or 0)
    comments = int(s.get("comments") or 0)

    ws = _ws()
    with ws.lock:
        sigs = ws.tables["signals"]
        existing = next((r for r in sigs if r.get("url_hash") == url_hash), None)
        if existing:
            curr_status = existing.get("status", "fresh")
            new_status = curr_status if curr_status in ("saved", "dismissed") else status
            existing.update({"likes": likes, "comments": comments, "status": new_status, "updated_at": now})
            s["id"] = existing["id"]
            s["status"] = new_status
            s["is_new"] = existing.get("is_new", 1)
            ws.flush_cache()
            return s

        if sig_type == "funding":
            cutoff_14d = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)).isoformat()
            prev = next((r for r in sigs if r.get("type") == "funding" and (r.get("company") or "").lower() == company.lower() and (r.get("found_at") or "") >= cutoff_14d), None)
            if prev:
                return {"id": prev["id"], "duplicate": True, "status": "duplicate"}

        rec = ws._normalize_row("signals", {
            "id": sig_id, "type": sig_type, "source": s.get("source") or "radar",
            "url": url, "url_hash": url_hash, "author_name": s.get("author_name") or "",
            "author_url": s.get("author_url") or "", "company": company,
            "company_domain": s.get("company_domain") or "", "text": s.get("text") or "",
            "posted_at": s.get("posted_at") or now, "likes": likes, "comments": comments,
            "found_at": s.get("found_at") or now, "is_new": int(s.get("is_new", 1)),
            "status": status, "score": int(s.get("score") or 0),
            "role_guess": s.get("role_guess") or "", "stage": s.get("stage") or "any",
            "region": s.get("region") or "any", "funding_amount": s.get("funding_amount") or "",
            "funding_round": s.get("funding_round") or "",
            "signal_json": json.dumps(s.get("signal_json") or s),
            "created_at": now, "updated_at": now,
        })
        sigs.append(rec)
        ws.flush_cache()
    s["id"] = sig_id
    return s


def get_signals(limit: int = 100, status: str | None = None, view_filters: dict | None = None, sig_type: str | None = None) -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = [
            dict(r) for r in ws.tables["signals"]
            if (not status or r.get("status") == status) and (not sig_type or r.get("type") == sig_type)
        ]
    rows.sort(key=lambda r: (r.get("posted_at") or "", r.get("score") or 0), reverse=True)
    rows = rows[:limit]
    results = []
    for r in rows:
        d = dict(r)
        if d.get("signal_json"):
            try:
                d["data"] = json.loads(d["signal_json"])
            except Exception:
                d["data"] = {}
        results.append(d)

    if view_filters:
        raw_role = view_filters.get("job_style") or view_filters.get("role") or view_filters.get("roles") or ""
        target_role = (" ".join(str(x) for x in raw_role if str(x).strip()) if isinstance(raw_role, (list, tuple, set)) else str(raw_role)).lower().strip()
        locs_list = _normalize_str_list(view_filters.get("locations") or view_filters.get("region") or [])
        wm_filter = str(view_filters.get("work_mode") or "").lower().strip()
        conf_inds = [i.lower() for i in _normalize_str_list(view_filters.get("confirmed_industries")) if i.lower() not in ("any", "all")]
        conf_stages = [st.lower() for st in _normalize_str_list(view_filters.get("company_stages")) if st.lower() not in ("any", "all")]
        conf_langs = [lg.lower() for lg in _normalize_str_list(view_filters.get("languages")) if lg.lower() not in ("any", "all")]

        from . import regions
        filtered = []
        for s in results:
            sig_text = f"{s.get('company', '')} {s.get('text', '')} {s.get('role_guess', '')} {s.get('stage', '')} {s.get('region', '')}".lower()
            if target_role and s.get("role_guess"):
                rg = s["role_guess"].lower()
                if target_role not in rg and rg not in target_role and not any(t in sig_text for t in target_role.split() if len(t) > 2):
                    continue
            if locs_list:
                sig_region = str(s.get("region") or "").strip()
                if sig_region and sig_region.lower() not in ("any", ""):
                    pseudo = {"location": sig_region, "work_mode": "remote" if "remote" in sig_text or "remote" in sig_region.lower() else ""}
                    if not regions.job_matches_confirmed_places(pseudo, locs_list, wm_filter):
                        continue
            if conf_inds and not any(re.search(rf"\b{re.escape(ind)}\b", sig_text) for ind in conf_inds):
                continue
            if conf_stages and s.get("stage", "any").lower() not in ("any", "") and not any(st in str(s.get("stage", "")).lower() or st in sig_text for st in conf_stages):
                continue
            if conf_langs and not any(re.search(rf"\b{re.escape(lg)}\b", sig_text) or (lg == "english" and not re.search(r"\b(?:french|german|spanish|arabic)\s+only\b", sig_text)) for lg in conf_langs):
                continue
            filtered.append(s)
        return filtered
    return results


def get_signal(signal_id: str) -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        r = next((x for x in ws.tables["signals"] if x.get("id") == signal_id or x.get("url_hash") == signal_id), None)
        if not r:
            return None
        d = dict(r)
        if d.get("signal_json"):
            try:
                d["data"] = json.loads(d["signal_json"])
            except Exception:
                d["data"] = {}
        return d


def update_signal_status(signal_id: str, status: str) -> bool:
    ws = _ws()
    with ws.lock:
        for r in ws.tables["signals"]:
            if r.get("id") == signal_id:
                r["status"] = status
                r["updated_at"] = now_iso()
                ws.flush_cache()
                return True
    return False


def ack_signals(signal_ids: list[str] | None = None) -> int:
    ws = _ws()
    id_set = set(signal_ids) if signal_ids else None
    changed = 0
    with ws.lock:
        for r in ws.tables["signals"]:
            if id_set is not None:
                if r.get("id") in id_set:
                    r["is_new"] = 0
                    changed += 1
            elif r.get("is_new") == 1:
                r["is_new"] = 0
                changed += 1
        if changed:
            ws.flush_cache()
    return changed


def get_new_signals_count(view_filters: dict | None = None) -> int:
    sigs = get_signals(limit=250, status="fresh", view_filters=view_filters)
    return sum(1 for s in sigs if s.get("is_new"))


def save_company_brief(company: str, brief_data: dict, learning_pack_data: dict, signal_id: str = "", domain: str = "", stage: str = "", funding_summary: str = "") -> dict[str, Any]:
    now = now_iso()
    brief_id = f"brief_{uuid.uuid4().hex[:12]}"
    brief_json = json.dumps(brief_data)
    lp_json = json.dumps(learning_pack_data)
    ws = _ws()
    with ws.lock:
        tbl = ws.tables["company_briefs"]
        existing = None
        if signal_id:
            existing = next((r for r in tbl if r.get("signal_id") == signal_id), None)
        if not existing and company:
            existing = next((r for r in tbl if (r.get("company") or "").lower() == company.lower()), None)
        if existing:
            brief_id = existing["id"]
            existing.update({"stage": stage, "funding_summary": funding_summary, "brief_json": brief_json, "learning_pack_json": lp_json, "updated_at": now})
        else:
            tbl.append(ws._normalize_row("company_briefs", {
                "id": brief_id, "signal_id": signal_id, "company": company,
                "company_domain": domain, "stage": stage, "funding_summary": funding_summary,
                "brief_json": brief_json, "learning_pack_json": lp_json, "created_at": now, "updated_at": now,
            }))
        ws.flush_durable()
    return {"id": brief_id, "signal_id": signal_id, "company": company, "brief": brief_data, "learning_pack": learning_pack_data, "updated_at": now}


def get_company_brief(company_or_signal_id: str) -> Optional[dict[str, Any]]:
    needle = (company_or_signal_id or "").lower()
    ws = _ws()
    with ws.lock:
        matches = [
            r for r in ws.tables["company_briefs"]
            if r.get("id") == company_or_signal_id or r.get("signal_id") == company_or_signal_id or (r.get("company") or "").lower() == needle
        ]
        if not matches:
            return None
        matches.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
        d = dict(matches[0])
    try:
        d["brief"] = json.loads(d.get("brief_json") or "{}")
    except Exception:
        d["brief"] = {}
    try:
        d["learning_pack"] = json.loads(d.get("learning_pack_json") or "{}")
    except Exception:
        d["learning_pack"] = {}
    return d


def save_contact(contact: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    c_dict = dict(contact)
    cid = c_dict.get("id") or f"ct_{uuid.uuid4().hex[:12]}"
    company = c_dict.get("company") or ""
    name = c_dict.get("name") or "Contact"
    title = c_dict.get("title") or c_dict.get("role") or ""
    email = c_dict.get("email") or ""
    confidence = c_dict.get("email_confidence") or c_dict.get("confidence") or "Guess"
    provider = c_dict.get("provider") or c_dict.get("source") or ""

    ws = _ws()
    with ws.lock:
        tbl = ws.tables["contacts"]
        existing = None
        if email:
            existing = next((r for r in tbl if (r.get("email") or "").lower() == email.lower()), None)
        if not existing and name and company:
            existing = next((r for r in tbl if (r.get("name") or "").lower() == name.lower() and (r.get("company") or "").lower() == company.lower()), None)

        updates = {
            "role": title, "title": title, "role_category": c_dict.get("role_category") or "",
            "company_domain": c_dict.get("company_domain") or "", "confidence": confidence,
            "email_confidence": confidence, "provider": provider, "source": c_dict.get("source") or provider,
            "source_url": c_dict.get("source_url") or "", "linkedin_url": c_dict.get("linkedin_url") or "",
            "x_handle": c_dict.get("x_handle") or "", "phone": c_dict.get("phone") or "",
            "notes": c_dict.get("notes") or "", "last_contacted_at": c_dict.get("last_contacted_at") or "",
            "status": c_dict.get("status") or "new", "updated_at": now,
        }
        if existing:
            cid = existing["id"]
            existing.update(updates)
        else:
            updates.update({
                "id": cid, "signal_id": c_dict.get("signal_id") or "", "company": company,
                "name": name, "email": email, "found_at": c_dict.get("found_at") or now, "created_at": now,
            })
            tbl.append(ws._normalize_row("contacts", updates))
        ws.flush_durable()

    c_dict["id"] = cid
    c_dict["title"] = title
    c_dict["role"] = title
    c_dict["confidence"] = confidence
    c_dict["email_confidence"] = confidence
    return c_dict


def get_contacts(signal_id: str = "", company: str = "") -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = ws.tables["contacts"]
        if signal_id and company:
            res = [r for r in rows if r.get("signal_id") == signal_id or (r.get("company") or "").lower() == company.lower()]
        elif signal_id:
            res = [r for r in rows if r.get("signal_id") == signal_id]
        elif company:
            res = [r for r in rows if (r.get("company") or "").lower() == company.lower()]
        else:
            res = list(rows)
        res = sorted([dict(r) for r in res], key=lambda r: r.get("created_at") or "", reverse=True)
        return res if (signal_id or company) else res[:100]


def get_contact(contact_id: str) -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        r = next((x for x in ws.tables["contacts"] if x.get("id") == contact_id), None)
        return dict(r) if r else None


def delete_contact(contact_id: str) -> bool:
    ws = _ws()
    with ws.lock:
        ws.tables["outreach"] = [r for r in ws.tables["outreach"] if r.get("contact_id") != contact_id]
        before = len(ws.tables["contacts"])
        ws.tables["contacts"] = [r for r in ws.tables["contacts"] if r.get("id") != contact_id]
        removed = len(ws.tables["contacts"]) < before
        if removed:
            ws.flush_durable()
        return removed


def update_contact_status(contact_id: str, status: str) -> bool:
    ws = _ws()
    with ws.lock:
        for r in ws.tables["contacts"]:
            if r.get("id") == contact_id:
                r["status"] = status
                r["updated_at"] = now_iso()
                ws.flush_durable()
                return True
    return False


def log_outreach(
    contact_id: str,
    signal_id: str = "",
    company: str = "",
    status: str = "draft",
    notes: str = "",
    resume_path: str = "",
    attached: int = 1,
    recipient_name: str = "",
    recipient_email: str = "",
    recipient_title: str = "",
    subject: str = "",
    body: str = "",
    follow_up_due: str | None = None,
    follow_up_sent_at: str | None = None,
    reply_received_at: str | None = None,
    reply_sentiment: str = "",
    sent_at: str = "",
    outreach_id: str | None = None,
) -> dict[str, Any]:
    now = now_iso()
    oid = outreach_id or f"out_{uuid.uuid4().hex[:12]}"
    rec = {
        "id": oid, "contact_id": contact_id, "signal_id": signal_id, "company": company,
        "recipient_name": recipient_name, "recipient_email": recipient_email, "recipient_title": recipient_title,
        "subject": subject, "body": body, "status": status, "drafted_at": now,
        "sent_at": sent_at or (now if status == "sent" else ""),
        "follow_up_due": follow_up_due, "follow_up_sent_at": follow_up_sent_at,
        "reply_received_at": reply_received_at, "reply_sentiment": reply_sentiment,
        "notes": notes, "resume_path": resume_path, "attached": attached,
        "created_at": now, "updated_at": now,
    }
    ws = _ws()
    with ws.lock:
        ws.tables["outreach"].append(ws._normalize_row("outreach", rec))
        ws.flush_durable()
    return {
        "id": oid, "contact_id": contact_id, "signal_id": signal_id, "company": company,
        "recipient_name": recipient_name, "recipient_email": recipient_email, "recipient_title": recipient_title,
        "subject": subject, "body": body, "status": status, "drafted_at": now,
        "follow_up_due": follow_up_due, "notes": notes, "resume_path": resume_path, "attached": attached,
    }


def get_outreach_for_contact(contact_id: str) -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = [dict(r) for r in ws.tables["outreach"] if r.get("contact_id") == contact_id]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows


def get_outreach_today() -> list[dict[str, Any]]:
    today_prefix = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    ws = _ws()
    with ws.lock:
        rows = [dict(r) for r in ws.tables["outreach"] if (r.get("sent_at") or "").startswith(today_prefix)]
    rows.sort(key=lambda r: r.get("sent_at") or "", reverse=True)
    return rows


def get_outreach_today_count() -> int:
    return len(get_outreach_today())


def get_outreach_queue() -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = [dict(r) for r in ws.tables["outreach"] if r.get("status") in ("draft", "queued")]
    rows.sort(key=lambda r: r.get("created_at") or "")
    return rows


def mark_outreach_sent(outreach_id_or_contact_id: str) -> Optional[dict[str, Any]]:
    now = now_iso()
    follow_up_days = int(get_setting("follow_up_days", "4"))
    follow_up_due = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=follow_up_days)).isoformat()
    ws = _ws()
    with ws.lock:
        matches = [r for r in ws.tables["outreach"] if r.get("id") == outreach_id_or_contact_id or r.get("contact_id") == outreach_id_or_contact_id]
        if not matches:
            return None
        matches.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        row = matches[0]
        row.update({"status": "sent", "sent_at": now, "follow_up_due": follow_up_due, "updated_at": now})
        for ct in ws.tables["contacts"]:
            if ct.get("id") == row.get("contact_id"):
                ct["status"] = "sent"
                ct["updated_at"] = now
        ws.flush_durable()
        return dict(row)


def mark_outreach_replied(outreach_id_or_contact_id: str) -> Optional[dict[str, Any]]:
    now = now_iso()
    ws = _ws()
    with ws.lock:
        matches = [r for r in ws.tables["outreach"] if r.get("id") == outreach_id_or_contact_id or r.get("contact_id") == outreach_id_or_contact_id]
        if not matches:
            return None
        matches.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        row = matches[0]
        row.update({"status": "replied", "replied_at": now, "updated_at": now})
        for ct in ws.tables["contacts"]:
            if ct.get("id") == row.get("contact_id"):
                ct["status"] = "replied"
                ct["updated_at"] = now
        ws.flush_durable()
        return dict(row)


def get_outreach_report() -> dict[str, Any]:
    ws = _ws()
    with ws.lock:
        all_rows = [dict(r) for r in ws.tables["outreach"]]
    total_drafted = len(all_rows)
    total_sent = sum(1 for r in all_rows if r.get("status") in ("sent", "replied", "followup_sent", "closed"))
    total_replied = sum(1 for r in all_rows if r.get("status") == "replied")
    reply_rate = (total_replied / total_sent) if total_sent > 0 else 0.0

    w_rows = [r for r in all_rows if r.get("attached") == 1 and r.get("status") != "draft"]
    wo_rows = [r for r in all_rows if r.get("attached") == 0 and r.get("status") != "draft"]
    w_sent, w_rep = len(w_rows), sum(1 for r in w_rows if r.get("status") == "replied")
    wo_sent, wo_rep = len(wo_rows), sum(1 for r in wo_rows if r.get("status") == "replied")
    rate_with = (w_rep / w_sent) if w_sent > 0 else 0.0
    rate_without = (wo_rep / wo_sent) if wo_sent > 0 else 0.0

    suggestion = "Keep sending targeted 3-4 line notes with relevant proof points."
    if wo_sent >= 5 and rate_without > rate_with:
        suggestion = "Sending initial emails without attachments is yielding higher reply rates. Consider keeping first_touch_attachment off."
    elif total_sent >= 10 and reply_rate < 0.10:
        suggestion = "Reply rate is below 10%. Consider refining the target role or quoting a tighter observation from recent company news."

    return {
        "total_drafted": total_drafted,
        "total_sent": total_sent,
        "total_replied": total_replied,
        "total_calls": total_replied,
        "reply_rate": round(reply_rate, 3),
        "by_attachment": {
            "attached": {"sent": w_sent, "replies": w_rep, "rate": round(rate_with, 3)},
            "unattached": {"sent": wo_sent, "replies": wo_rep, "rate": round(rate_without, 3)},
        },
        "suggested_change": suggestion,
        "generated_at": now_iso(),
    }


# ------------------------------------------------------------------ Coach Layer

def get_coach_state(session_id: str = "default") -> dict[str, Any]:
    sid = session_id or "default"
    global_pref = get_coaching_preference()
    ws = _ws()
    with ws.lock:
        row = next((r for r in ws.tables["coach_state"] if r.get("session_id") == sid), None)
        if not row:
            now = now_iso()
            row = {"session_id": sid, "coaching_enabled": 1 if global_pref else 0, "opt_out": 0, "updated_at": now}
            ws.tables["coach_state"].append(row)
            ws.flush_durable()
            return {"session_id": sid, "coaching_enabled": bool(global_pref), "opt_out": False, "updated_at": now}
        return {
            "session_id": row["session_id"],
            "coaching_enabled": bool(row.get("coaching_enabled")) and global_pref,
            "opt_out": bool(row.get("opt_out")),
            "updated_at": row.get("updated_at", ""),
        }


def set_coach_state(session_id: str = "default", coaching_enabled: bool | None = None, opt_out: bool | None = None) -> dict[str, Any]:
    sid = session_id or "default"
    curr = get_coach_state(sid)
    new_enabled = curr["coaching_enabled"] if coaching_enabled is None else bool(coaching_enabled)
    new_opt_out = curr["opt_out"] if opt_out is None else bool(opt_out)
    now = now_iso()
    ws = _ws()
    with ws.lock:
        row = next((r for r in ws.tables["coach_state"] if r.get("session_id") == sid), None)
        vals = {"session_id": sid, "coaching_enabled": 1 if new_enabled else 0, "opt_out": 1 if new_opt_out else 0, "updated_at": now}
        if row:
            row.update(vals)
        else:
            ws.tables["coach_state"].append(vals)
        ws.flush_durable()
    return {"session_id": sid, "coaching_enabled": new_enabled, "opt_out": new_opt_out, "updated_at": now}


def record_coach_event(session_id: str = "default", trigger_id: str = "") -> bool:
    if not trigger_id:
        return False
    sid = session_id or "default"
    tid = trigger_id.strip().upper()
    ws = _ws()
    with ws.lock:
        if any(r.get("session_id") == sid and r.get("trigger_id") == tid for r in ws.tables["coach_events"]):
            return False
        ws.tables["coach_events"].append({"session_id": sid, "trigger_id": tid, "ts": now_iso()})
        ws.flush_durable()
        return True


def get_coach_events(session_id: str = "default") -> list[str]:
    sid = session_id or "default"
    ws = _ws()
    with ws.lock:
        rows = sorted([r for r in ws.tables["coach_events"] if r.get("session_id") == sid], key=lambda r: r.get("ts") or "")
        return [r["trigger_id"] for r in rows]


def has_coach_event(session_id: str = "default", trigger_id: str = "") -> bool:
    if not trigger_id:
        return False
    sid = session_id or "default"
    tid = trigger_id.strip().upper()
    ws = _ws()
    with ws.lock:
        return any(r.get("session_id") == sid and r.get("trigger_id") == tid for r in ws.tables["coach_events"])


def reset_coach_events(session_id: str = "default") -> None:
    sid = session_id or "default"
    ws = _ws()
    with ws.lock:
        ws.tables["coach_events"] = [r for r in ws.tables["coach_events"] if r.get("session_id") != sid]
        ws.flush_durable()


def get_coaching_preference() -> bool:
    env = os.environ.get("JH_COACHING", "").strip().lower()
    if env == "off":
        return False
    val = get_setting("coaching_enabled", "1")
    return str(val).strip().lower() not in ("0", "false", "off", "no")


def set_coaching_preference(enabled: bool, scope: str = "session", session_id: str = "default") -> dict[str, Any]:
    sid = session_id or "default"
    sc = (scope or "session").strip().lower()
    if sc == "persistent":
        set_setting("coaching_enabled", "1" if enabled else "0")
    set_coach_state(session_id=sid, coaching_enabled=enabled, opt_out=not enabled)
    return {"enabled": enabled, "coaching_enabled": enabled, "scope": sc, "session_id": sid, "opt_out": not enabled}


def wipe_coaching_data(session_id: str | None = None) -> dict[str, int]:
    ws = _ws()
    with ws.lock:
        b1, b2 = len(ws.tables["coach_events"]), len(ws.tables["coach_state"])
        if session_id:
            ws.tables["coach_events"] = [r for r in ws.tables["coach_events"] if r.get("session_id") != session_id]
            ws.tables["coach_state"] = [r for r in ws.tables["coach_state"] if r.get("session_id") != session_id]
        else:
            ws.tables["coach_events"] = []
            ws.tables["coach_state"] = []
        ws.flush_durable()
        return {"coach_events_cleared": b1 - len(ws.tables["coach_events"]), "coach_state_cleared": b2 - len(ws.tables["coach_state"])}


def wipe_all_data() -> dict[str, int]:
    ws = _ws()
    counts = {}
    targets = (
        "coach_events", "coach_state", "search_jobs", "pending_search_jobs",
        "applications", "status_history", "watchlist", "seen_jobs",
        "outreach", "contacts", "signals", "company_briefs", "dismissals",
        "confirmed_facts", "base_resumes",
    )
    with ws.lock:
        for tbl in targets:
            counts[tbl] = len(ws.tables.get(tbl, []))
            ws.tables[tbl] = []
        ws.flush_durable()
        ws.flush_cache()
    return counts


# ------------------------------------------------------------------ Confirmed Facts, Base Resumes, Audit, Guesses, Answers

def add_confirmed_fact(fact: str, category: str = "general", label: str = "user_confirmed", session_id: str = "default") -> str:
    fact_clean = (fact or "").strip()
    if not fact_clean:
        return ""
    fact_id = f"fact_{stable_id(fact_clean + session_id)[:12]}"
    now = now_iso()
    ws = _ws()
    with ws.lock:
        tbl = ws.tables["confirmed_facts"]
        existing = next((r for r in tbl if r.get("id") == fact_id), None)
        rec = {"id": fact_id, "session_id": session_id, "fact": fact_clean, "category": category, "label": label, "created_at": now}
        if existing:
            existing.update(rec)
        else:
            tbl.append(rec)
        ws.flush_durable()
    return fact_id


def get_confirmed_facts(session_id: Optional[str] = None) -> list[dict[str, Any]]:
    active_sid = get_setting("active_session_id", "default") or "default"
    ws = _ws()
    with ws.lock:
        if session_id is None:
            sids = {active_sid, "default"}
            rows = [dict(r) for r in ws.tables["confirmed_facts"] if r.get("session_id") in sids]
        else:
            rows = [dict(r) for r in ws.tables["confirmed_facts"] if r.get("session_id") == session_id]
    rows.sort(key=lambda r: r.get("created_at") or "")
    return rows


def save_base_resume(role_family: str, resume_data: dict, approved: bool = False, session_id: str = "default") -> str:
    base_id = f"base_{stable_id(role_family.lower() + session_id)[:12]}"
    now = now_iso()
    raw = json.dumps(resume_data)
    ws = _ws()
    with ws.lock:
        tbl = ws.tables["base_resumes"]
        existing = next((r for r in tbl if r.get("id") == base_id), None)
        rec = {
            "id": base_id, "session_id": session_id, "role_family": role_family,
            "resume_data": raw, "approved": 1 if approved else 0, "created_at": now, "updated_at": now,
        }
        if existing:
            existing.update(rec)
        else:
            tbl.append(rec)
        ws.flush_durable()
    return base_id


def get_base_resumes(session_id: str = "default") -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = sorted([dict(r) for r in ws.tables["base_resumes"] if r.get("session_id") == session_id], key=lambda r: r.get("created_at") or "")
    for d in rows:
        if isinstance(d.get("resume_data"), str):
            try:
                d["resume_data"] = json.loads(d["resume_data"])
            except Exception:
                pass
    return rows


def get_base_resume(role_family: str, session_id: str = "default") -> Optional[dict[str, Any]]:
    needle = role_family.strip().lower()
    ws = _ws()
    with ws.lock:
        row = next((dict(r) for r in ws.tables["base_resumes"] if r.get("session_id") == session_id and (r.get("role_family") or "").lower() == needle), None)
    if row and isinstance(row.get("resume_data"), str):
        try:
            row["resume_data"] = json.loads(row["resume_data"])
        except Exception:
            pass
    return row


def approve_base_resume(base_resume_id: str, session_id: str = "default") -> bool:
    now = now_iso()
    ws = _ws()
    with ws.lock:
        for r in ws.tables["base_resumes"]:
            if r.get("session_id") == session_id and (r.get("id") == base_resume_id or r.get("role_family") == base_resume_id):
                r["approved"] = 1
                r["updated_at"] = now
                ws.flush_durable()
                return True
    return False


def get_ready_to_apply_count(session_id: str = "default") -> int:
    ws = _ws()
    with ws.lock:
        return sum(
            1 for r in ws.tables["applications"]
            if r.get("grounding_result") in ("passed", "repaired") and (r.get("resume_path") or "") != ""
        )


def log_audit_event(session_id: str, user_reply: str, action: str, details: str = "") -> None:
    ws = _ws()
    with ws.lock:
        ws.tables["audit_log"].append({
            "id": ws.next_id("audit_log"),
            "session_id": session_id, "user_reply": str(user_reply),
            "action": str(action), "details": str(details), "created_at": now_iso(),
        })
        ws.flush_durable()


def get_audit_events(session_id: str = "") -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = ws.tables["audit_log"]
        if session_id:
            rows = [r for r in rows if r.get("session_id") == session_id]
        return [dict(r) for r in sorted(rows, key=lambda r: r.get("id") or 0)]


def store_guess(session_id: str, category: str, value: str, confidence: float = 0.0, metadata: Optional[dict] = None, resume_id: str = "") -> None:
    ws = _ws()
    with ws.lock:
        ws.tables["guesses"].append({
            "id": ws.next_id("guesses"),
            "session_id": session_id, "resume_id": resume_id, "category": category,
            "value": str(value), "confidence": float(confidence),
            "metadata": json.dumps(metadata or {}), "created_at": now_iso(),
        })
        ws.flush_durable()


def get_guesses(session_id: str, category: Optional[str] = None) -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = [r for r in ws.tables["guesses"] if r.get("session_id") == session_id and (not category or r.get("category") == category)]
        return [dict(r) for r in sorted(rows, key=lambda r: r.get("id") or 0)]


def store_answer(session_id: str, category: str, value: str, user_reply: str) -> None:
    ws = _ws()
    with ws.lock:
        ws.tables["answers"].append({
            "id": ws.next_id("answers"),
            "session_id": session_id, "category": category,
            "value": str(value), "user_reply": str(user_reply), "created_at": now_iso(),
        })
        ws.flush_durable()


def get_answers(session_id: str, category: Optional[str] = None) -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = [r for r in ws.tables["answers"] if r.get("session_id") == session_id and (not category or r.get("category") == category)]
        return [dict(r) for r in sorted(rows, key=lambda r: r.get("id") or 0)]


def get_confirmed_answer(session_id: str, category: str) -> Optional[str]:
    rows = get_answers(session_id, category)
    return str(rows[-1]["value"]) if rows else None


def is_job_saved_by_ui(job_id_or_key: str) -> bool:
    if not job_id_or_key:
        return False
    ws = _ws()
    with ws.lock:
        for r in ws.tables["jobs"]:
            if r.get("id") == job_id_or_key or r.get("url_hash") == job_id_or_key or r.get("job_key") == job_id_or_key:
                if r.get("saved_by") == "ui":
                    return True
        for r in ws.tables["applications"]:
            if r.get("id") == job_id_or_key or r.get("job_id") == job_id_or_key:
                if r.get("saved_by") == "ui":
                    return True
    return False


def mark_job_saved_by_ui(job_id_or_key: str) -> None:
    if not job_id_or_key:
        return
    ws = _ws()
    with ws.lock:
        for r in ws.tables["jobs"]:
            if r.get("id") == job_id_or_key or r.get("url_hash") == job_id_or_key or r.get("job_key") == job_id_or_key:
                r["saved_by"] = "ui"
                r["keep_flag"] = 1
        for r in ws.tables["applications"]:
            if r.get("id") == job_id_or_key or r.get("job_id") == job_id_or_key:
                r["saved_by"] = "ui"
        ws.flush_cache()
        ws.flush_durable()


def reset_stale_search_cache(session_id: str = "default") -> dict[str, int]:
    init_db()
    counts = {"jobs_cleared": 0, "signals_cleared": 0, "pending_cleared": 0}
    ws = _ws()
    with ws.lock:
        app_job_ids = {a.get("job_id") for a in ws.tables["applications"] if a.get("job_id")}
        kept_jobs = []
        for j in ws.tables["jobs"]:
            if j.get("saved_by") == "ui" or j.get("keep_flag") or j.get("id") in app_job_ids or j.get("job_key") in app_job_ids:
                kept_jobs.append(j)
        counts["jobs_cleared"] = len(ws.tables["jobs"]) - len(kept_jobs)
        ws.tables["jobs"] = kept_jobs

        kept_ids = {j.get("id") for j in kept_jobs} | {j.get("job_key") for j in kept_jobs}
        ws.tables["search_jobs"] = [s for s in ws.tables["search_jobs"] if s.get("job_key") in kept_ids]
        ws.tables["job_sources"] = [s for s in ws.tables["job_sources"] if s.get("job_id") in kept_ids]

        out_sig_ids = {o.get("signal_id") for o in ws.tables["outreach"] if o.get("signal_id")}
        kept_sigs = [s for s in ws.tables["signals"] if s.get("status") == "saved" or s.get("id") in out_sig_ids]
        counts["signals_cleared"] = len(ws.tables["signals"]) - len(kept_sigs)
        ws.tables["signals"] = kept_sigs

        counts["pending_cleared"] = len(ws.tables["pending_search_jobs"])
        ws.tables["pending_search_jobs"] = []
        ws.tables["view_filters"] = [v for v in ws.tables["view_filters"] if v.get("session_id") != session_id]
        ws.tables["settings"] = [s for s in ws.tables["settings"] if s.get("key") not in ("li_radar_last_run", "li_radar_last_query", "li_radar_last_action", "li_radar_new_last")]
        if ws.tables["radar_state"]:
            ws.tables["radar_state"][0]["last_poll_at"] = None
        ws.flush_durable()
        ws.flush_cache()
    return counts


# ------------------------------------------------------------------ Typed Store Helpers (no raw SQL in callers)

def get_job_record(job_id: str) -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        for r in ws.tables["jobs"]:
            if job_id in (r.get("id"), r.get("url_hash"), r.get("job_key")):
                return dict(r)
        for r in ws.tables["search_jobs"]:
            if r.get("job_key") == job_id:
                d = dict(r)
                try:
                    raw = json.loads(d.get("job_json") or "{}")
                    raw.update(d)
                    return raw
                except Exception:
                    return d
        for a in ws.tables["applications"]:
            if a.get("id") == job_id or a.get("job_id") == job_id:
                d = dict(a)
                try:
                    jd = json.loads(d.get("job_data_json") or "{}")
                    jd.update(d)
                    return jd
                except Exception:
                    return d
    return None


def is_job_saved_record(job_id_or_key: str) -> bool:
    if not job_id_or_key:
        return False
    ws = _ws()
    with ws.lock:
        for a in ws.tables["applications"]:
            if (a.get("id") == job_id_or_key or a.get("job_id") == job_id_or_key) and a.get("status") in ("saved", "applied", "interview", "offer", "queued"):
                return True
        for j in ws.tables["jobs"]:
            if job_id_or_key in (j.get("id"), j.get("url_hash"), j.get("job_key")) and j.get("keep_flag"):
                return True
    return False


def mark_job_saved_record(job_id_or_key: str, saved_by: str = "ui") -> None:
    ws = _ws()
    with ws.lock:
        for j in ws.tables["jobs"]:
            if job_id_or_key in (j.get("id"), j.get("url_hash"), j.get("job_key")):
                j["keep_flag"] = 1
                j["delete_at"] = None
                j["saved_by"] = saved_by
        ws.flush_cache()


def keep_jobs_by_ids(job_ids: list[str]) -> int:
    if not job_ids:
        return 0
    id_set = set(job_ids)
    changed = 0
    ws = _ws()
    with ws.lock:
        for j in ws.tables["jobs"]:
            if j.get("id") in id_set or j.get("job_key") in id_set:
                j["keep_flag"] = 1
                j["delete_at"] = None
                changed += 1
        if changed:
            ws.flush_cache()
    return changed


def job_exists(job_id: str) -> bool:
    ws = _ws()
    with ws.lock:
        return any(j.get("id") == job_id or j.get("job_key") == job_id for j in ws.tables["jobs"])


def mark_job_closed_record(job_id: str, delete_dt: str) -> None:
    iso_now = now_iso()
    ws = _ws()
    with ws.lock:
        has_app = any(a.get("job_id") == job_id for a in ws.tables["applications"])
        for j in ws.tables["jobs"]:
            if j.get("id") == job_id or j.get("job_key") == job_id:
                if j.get("keep_flag") or has_app:
                    j.update({"freshness_state": "expired", "closed_checked_at": iso_now, "keep_flag": 1, "delete_at": None})
                else:
                    j.update({"freshness_state": "expired", "closed_checked_at": iso_now, "delete_at": j.get("delete_at") or delete_dt})
        ws.flush_cache()


def cleanup_expired_records(grace_hours: int) -> int:
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    iso_now = now_dt.isoformat()
    delete_horizon = (now_dt + datetime.timedelta(hours=grace_hours)).isoformat()
    cutoff_60d = (now_dt - datetime.timedelta(days=60)).isoformat()
    deleted_count = 0

    ws = _ws()
    with ws.lock:
        app_job_ids = {a.get("job_id") for a in ws.tables["applications"] if a.get("job_id")}
        kept = []
        removed_ids = set()
        for j in ws.tables["jobs"]:
            c_at = j.get("created_at") or ""
            fs_at = j.get("first_seen_at") or ""
            if not j.get("keep_flag"):
                if j.get("freshness_state") != "expired" and ((c_at and c_at < cutoff_60d) or (fs_at and fs_at < cutoff_60d)):
                    j["freshness_state"] = "expired"
                    j["delete_at"] = delete_horizon
                if j.get("freshness_state") == "expired" and j.get("delete_at") is None:
                    j["delete_at"] = delete_horizon
            should_del = (
                j.get("freshness_state") == "expired"
                and j.get("delete_at") is not None
                and j["delete_at"] <= iso_now
                and not j.get("keep_flag")
                and j.get("id") not in app_job_ids
                and j.get("job_key") not in app_job_ids
            )
            if should_del:
                if j.get("url_hash") or j.get("fingerprint"):
                    ws.tables["tombstones"].append({
                        "id": ws.next_id("tombstones"),
                        "url_hash": j.get("url_hash") or "",
                        "fingerprint": j.get("fingerprint") or "",
                        "deleted_at": iso_now,
                    })
                removed_ids.add(j.get("id"))
                deleted_count += 1
            else:
                kept.append(j)
        ws.tables["jobs"] = kept
        if removed_ids:
            ws.tables["job_sources"] = [s for s in ws.tables["job_sources"] if s.get("job_id") not in removed_ids]
            ws.flush_durable()
        ws.flush_cache()
    return deleted_count


def mark_jobs_seen_by_user(job_ids: Optional[list[str]] = None) -> int:
    ws = _ws()
    id_set = set(job_ids) if job_ids else None
    changed = 0
    with ws.lock:
        for j in ws.tables["jobs"]:
            if id_set is not None:
                if j.get("id") in id_set or j.get("job_key") in id_set:
                    j["is_new"] = 0
                    j["seen_by_user"] = 1
                    changed += 1
            elif j.get("is_new") == 1:
                j["is_new"] = 0
                j["seen_by_user"] = 1
                changed += 1
        if changed:
            ws.flush_cache()
    return changed


def list_applications_raw() -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        return sorted([dict(r) for r in ws.tables["applications"]], key=lambda r: r.get("updated_at") or "", reverse=True)


def get_application_raw(app_id: str) -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        r = next((x for x in ws.tables["applications"] if x.get("id") == app_id), None)
        return dict(r) if r else None


def get_status_history(app_id: str) -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = [dict(h) for h in ws.tables["status_history"] if h.get("app_id") == app_id]
        rows.sort(key=lambda h: h.get("id") or 0)
        return [{"status": h["status"], "changed_at": h["changed_at"]} for h in rows]


def upsert_application_raw(record: dict[str, Any], add_history: bool = False) -> None:
    ws = _ws()
    with ws.lock:
        tbl = ws.tables["applications"]
        existing = next((r for r in tbl if r.get("id") == record["id"]), None)
        if existing:
            existing.update(record)
        else:
            tbl.append(ws._normalize_row("applications", record))
        if add_history:
            ws.tables["status_history"].append({
                "id": ws.next_id("status_history"),
                "app_id": record["id"],
                "status": record["status"],
                "changed_at": record["updated_at"],
            })
        ws.flush_durable()


def update_application_fields(app_or_job_id: str, **fields: Any) -> bool:
    ws = _ws()
    changed = False
    with ws.lock:
        for r in ws.tables["applications"]:
            if r.get("id") == app_or_job_id or r.get("job_id") == app_or_job_id:
                r.update(fields)
                r.setdefault("updated_at", now_iso())
                changed = True
        if changed:
            ws.flush_durable()
    return changed


def delete_application_raw(app_id: str) -> None:
    ws = _ws()
    with ws.lock:
        ws.tables["applications"] = [r for r in ws.tables["applications"] if r.get("id") != app_id]
        ws.tables["status_history"] = [h for h in ws.tables["status_history"] if h.get("app_id") != app_id]
        ws.flush_durable()


def list_watchlist_raw() -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        return sorted([dict(r) for r in ws.tables["watchlist"]], key=lambda r: r.get("company_name") or "")


def update_watchlist_checked(wl_id: str, checked_at: str, matches: int) -> None:
    ws = _ws()
    with ws.lock:
        for w in ws.tables["watchlist"]:
            if w.get("id") == wl_id:
                w["last_checked"] = checked_at
                w["active_matches_count"] = matches
        ws.flush_durable()


def delete_watchlist_raw(wl_id: str) -> None:
    ws = _ws()
    with ws.lock:
        ws.tables["watchlist"] = [w for w in ws.tables["watchlist"] if w.get("id") != wl_id]
        ws.flush_durable()


def add_watchlist_entry(wl_id: str, name: str, slug: str, board_type: str, target_role: str = "") -> tuple[bool, str]:
    ws = _ws()
    with ws.lock:
        for w in ws.tables["watchlist"]:
            if (w.get("board_type") or "").lower() == board_type and w.get("slug") == slug:
                return True, w["id"]
        ws.tables["watchlist"].append(ws._normalize_row("watchlist", {
            "id": wl_id, "company_name": name, "slug": slug,
            "board_type": board_type, "target_role": target_role or "", "added_at": now_iso(),
        }))
        ws.flush_durable()
    return False, wl_id


def remove_watchlist_entry(ident: str) -> bool:
    needle = (ident or "").strip().lower()
    ws = _ws()
    with ws.lock:
        before = len(ws.tables["watchlist"])
        ws.tables["watchlist"] = [
            w for w in ws.tables["watchlist"]
            if w.get("id") != ident and (w.get("slug") or "").lower() != needle and (w.get("company_name") or "").lower() != needle
        ]
        removed = len(ws.tables["watchlist"]) < before
        if removed:
            ws.flush_durable()
        return removed


def list_discovered_boards() -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        return [dict(r) for r in ws.tables["discovered_boards"]]


def upsert_discovered_board(board: str, slug: str, name: str, found_via: str, ok: Optional[bool], count: int = 0) -> bool:
    now_ts = time.time()
    ws = _ws()
    with ws.lock:
        tbl = ws.tables["discovered_boards"]
        row = next((r for r in tbl if r.get("board_type") == board and r.get("slug") == slug), None)
        is_new = row is None
        if row is None:
            row = ws._normalize_row("discovered_boards", {
                "board_type": board, "slug": slug, "company_name": name,
                "first_seen": now_iso(), "found_via": found_via,
            })
            tbl.append(row)
        if ok is True:
            row.update({"last_fetched": now_ts, "last_ok": now_ts, "job_count": count, "fail_count": 0})
        elif ok is False:
            row.update({"last_fetched": now_ts, "fail_count": int(row.get("fail_count") or 0) + 1})
        ws.flush_durable()
        return is_new


def get_source_cache(cache_key: str) -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        r = next((x for x in ws.tables["source_cache"] if x.get("cache_key") == cache_key), None)
        return dict(r) if r else None


def set_source_cache(cache_key: str, payload: str, fetched_at: float) -> None:
    ws = _ws()
    with ws.lock:
        tbl = ws.tables["source_cache"]
        row = next((x for x in tbl if x.get("cache_key") == cache_key), None)
        if row:
            row.update({"payload": payload, "fetched_at": fetched_at})
        else:
            tbl.append({"cache_key": cache_key, "payload": payload, "fetched_at": fetched_at})
        ws.flush_cache()


def query_outreach_history(contact_id: str, email: str = "", cutoff_iso: str = "") -> list[dict[str, Any]]:
    clean_email = (email or "").strip().lower()
    ws = _ws()
    with ws.lock:
        rows = []
        for r in ws.tables["outreach"]:
            if cutoff_iso and (r.get("created_at") or "") < cutoff_iso:
                continue
            if r.get("contact_id") == contact_id or (clean_email and (r.get("recipient_email") or "").lower() == clean_email):
                rows.append(dict(r))
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows


def update_outreach_record(identifier: str, updater: Any) -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        matches = [r for r in ws.tables["outreach"] if r.get("id") == identifier or r.get("contact_id") == identifier]
        if not matches:
            return None
        matches.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        row = matches[0]
        updater(row, ws)
        ws.flush_durable()
        return dict(row)


def has_outreach_for_company(company: str) -> bool:
    needle = (company or "").lower().strip()
    if not needle:
        return False
    ws = _ws()
    with ws.lock:
        return any((r.get("company") or "").lower() == needle for r in ws.tables["outreach"])


def has_outreach_for_email_since(email: str, cutoff_iso: str) -> bool:
    needle = (email or "").lower().strip()
    if not needle:
        return False
    ws = _ws()
    with ws.lock:
        return any((r.get("recipient_email") or "").lower() == needle and (r.get("sent_at") or "") >= cutoff_iso for r in ws.tables["outreach"])


def get_undigested_seen_keys(limit: int | None = None, mark_seen: bool = False) -> tuple[list[str], int]:
    ws = _ws()
    with ws.lock:
        undig = {r.get("job_key") for r in ws.tables["seen_jobs"] if not r.get("digested")}
        backlog = len(undig)
        active = [r for r in ws.tables["search_jobs"] if r.get("is_active", 1) == 1 and r.get("job_key") in undig]
        active.sort(key=lambda r: (r.get("opportunity_score") or 0, r.get("score") or 0), reverse=True)
        keys = [r["job_key"] for r in (active[:limit] if limit else active)]
        if mark_seen and keys:
            key_set = set(keys)
            for s in ws.tables["seen_jobs"]:
                if s.get("job_key") in key_set:
                    s["digested"] = 1
            ws.flush_cache()
        return keys, backlog


def mark_seen_digested(keys: list[str]) -> None:
    if not keys:
        return
    key_set = set(keys)
    ws = _ws()
    with ws.lock:
        for s in ws.tables["seen_jobs"]:
            if s.get("job_key") in key_set:
                s["digested"] = 1
        ws.flush_cache()


def get_undigested_key_set() -> set[str]:
    ws = _ws()
    with ws.lock:
        return {r["job_key"] for r in ws.tables["seen_jobs"] if not r.get("digested") and r.get("job_key")}


def upsert_mission(mission_id: str, request: str, intents: list[str], status: str, blob: str, keep: int = 200) -> None:
    now = now_iso()
    ws = _ws()
    with ws.lock:
        tbl = ws.tables["missions"]
        existing = next((r for r in tbl if r.get("id") == mission_id), None)
        created_at = existing["created_at"] if existing else now
        rec = {
            "id": mission_id, "created_at": created_at, "updated_at": now,
            "request": request[:1000], "intents": ",".join(intents), "status": status, "data_json": blob,
        }
        if existing:
            existing.update(rec)
        else:
            tbl.append(rec)
        tbl.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        del tbl[keep:]
        ws.flush_durable()


def load_mission(mission_id: str) -> Optional[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        r = next((x for x in ws.tables["missions"] if x.get("id") == mission_id), None)
        return dict(r) if r else None


def recent_missions(limit: int = 10) -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        rows = sorted([dict(r) for r in ws.tables["missions"]], key=lambda r: r.get("created_at") or "", reverse=True)
        return rows[:limit]


def all_missions() -> list[dict[str, Any]]:
    ws = _ws()
    with ws.lock:
        return [dict(r) for r in ws.tables["missions"]]


def delete_missions(mission_id: str = "all") -> int:
    ws = _ws()
    with ws.lock:
        before = len(ws.tables["missions"])
        ws.tables["missions"] = [] if mission_id == "all" else [r for r in ws.tables["missions"] if r.get("id") != mission_id]
        removed = before - len(ws.tables["missions"])
        if removed:
            ws.flush_durable()
        return removed


def find_search_jobs_by_company(needle: str, limit: int = 6) -> list[dict[str, Any]]:
    low = (needle or "").lower()
    ws = _ws()
    with ws.lock:
        rows = [r for r in ws.tables["search_jobs"] if low in (r.get("company") or "").lower()]
        rows.sort(key=lambda r: r.get("score") or 0, reverse=True)
        return [{"job_key": r["job_key"], "title": r.get("title", ""), "company": r.get("company", "")} for r in rows[:limit]]


def get_top_search_scores(limit: int = 5) -> list[float]:
    ws = _ws()
    with ws.lock:
        rows = sorted(ws.tables["search_jobs"], key=lambda r: r.get("score") or 0, reverse=True)
        return [float(r["score"]) for r in rows[:limit] if r.get("score") is not None]


def count_runtime_stats() -> dict[str, int]:
    ws = _ws()
    with ws.lock:
        jobs = ws.tables["jobs"]
        return {
            "total_jobs": len(jobs),
            "active_jobs": sum(1 for j in jobs if j.get("freshness_state") == "active"),
            "dismissals_count": len(ws.tables["dismissals"]),
            "signals_count": len(ws.tables["signals"]),
            "has_stale_jobs": int(any(j.get("saved_by") != "ui" for j in jobs)),
            "has_stale_signals": int(any(s.get("status") != "saved" for s in ws.tables["signals"])),
            "has_stale_filters": int(len(ws.tables["view_filters"]) > 0),
        }


def rescore_all_jobs_against_profile(profile: dict[str, Any]) -> None:
    from . import scoring
    ws = _ws()
    with ws.lock:
        changed = False
        for r in ws.tables["jobs"]:
            try:
                j = json.loads(r.get("job_json") or "{}")
                scored = scoring.score_job(j, profile)
                new_score = int(scored.get("score", 0))
                j.update(scored)
                r["score"] = new_score
                r["job_json"] = json.dumps(j)
                changed = True
            except Exception:
                pass
        if changed:
            ws.flush_cache()


def count_store_metrics() -> dict[str, int]:
    ws = _ws()
    with ws.lock:
        jobs = ws.tables["jobs"]
        sigs = ws.tables["signals"]
        return {
            "total_jobs": len(jobs),
            "active_jobs": sum(1 for j in jobs if j.get("freshness_state") == "active"),
            "dismissals_count": len(ws.tables["dismissals"]),
            "signals_count": len(sigs),
            "fresh_signals": sum(1 for s in sigs if s.get("status") == "fresh"),
            "contacts_count": len(ws.tables["contacts"]),
            "outreach_count": len(ws.tables["outreach"]),
        }


def get_outreach_weekly_stats() -> dict[str, Any]:
    ws = _ws()
    with ws.lock:
        out_rows = [dict(r) for r in ws.tables["outreach"]]
        sig_by_id = {s.get("id"): s.get("source") or "other" for s in ws.tables["signals"]}
    w_sent = w_rep = wo_sent = wo_rep = 0
    by_source: dict[str, dict[str, Any]] = {}
    for o in out_rows:
        st = o.get("status")
        if st == "draft":
            continue
        is_rep = 1 if st == "replied" else 0
        if o.get("attached") == 1:
            w_sent += 1
            w_rep += is_rep
        elif o.get("attached") == 0:
            wo_sent += 1
            wo_rep += is_rep
        sid = o.get("signal_id")
        if sid and sid in sig_by_id:
            sname = sig_by_id[sid]
            entry = by_source.setdefault(sname, {"sent": 0, "replies": 0, "rate": 0.0})
            entry["sent"] += 1
            entry["replies"] += is_rep
    for entry in by_source.values():
        entry["rate"] = round(entry["replies"] / entry["sent"], 2) if entry["sent"] else 0.0
    return {"w_sent": w_sent, "w_rep": w_rep, "wo_sent": wo_sent, "wo_rep": wo_rep, "by_source": by_source}


def query_jobs_by_filter(freshness_state: str = "active", limit: int = 20) -> list[str]:
    ws = _ws()
    with ws.lock:
        return [r["id"] for r in ws.tables["jobs"] if r.get("freshness_state") == freshness_state][:limit]
