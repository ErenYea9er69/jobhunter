"""Job-Name and Role Inference Engine for JobHunter V3.

Infers candidate target roles with confidence scoring (0.0 to 1.0) based on:
1. Work history titles (weighted by recency).
2. Headline / summary.
3. Skill cluster mappings (e.g. React+Node -> Full Stack, AWS+Terraform -> Cloud/DevOps).
4. Projects and graduation year.
5. Filename keywords (e.g. PFE, internship, stage, alternance).

Also produces job_type_guess and region_guess marked as `guess: True` (which NEVER filter results).
"""
from __future__ import annotations

import re
from typing import Any

# Skill clusters mapped to role families
ROLE_CLUSTERS = [
    {
        "role": "Full Stack Engineer",
        "req_any": [
            {"react", "node"}, {"react", "nodejs"}, {"vue", "node"}, {"angular", "node"},
            {"react", "django"}, {"react", "fastapi"}, {"vue", "django"}, {"typescript", "python"},
            {"next.js", "node"}, {"nextjs", "node"}, {"full stack", "fullstack"}
        ],
        "keywords": ["full stack", "fullstack", "frontend and backend"],
    },
    {
        "role": "Backend Engineer",
        "req_any": [
            {"python", "fastapi"}, {"python", "django"}, {"python", "flask"},
            {"golang", "postgres"}, {"go", "postgresql"}, {"java", "spring"},
            {"node", "express"}, {"c#", ".net"}, {"rust", "postgres"},
        ],
        "keywords": ["backend", "back-end", "api", "microservices"],
    },
    {
        "role": "Frontend Engineer",
        "req_any": [
            {"react", "css"}, {"react", "tailwind"}, {"vue", "css"}, {"angular", "typescript"},
            {"next.js", "css"}, {"html", "css", "javascript"},
        ],
        "keywords": ["frontend", "front-end", "ui", "web developer"],
    },
    {
        "role": "Cloud / DevOps Engineer",
        "req_any": [
            {"aws", "terraform"}, {"kubernetes", "docker"}, {"azure", "terraform"},
            {"gcp", "kubernetes"}, {"ci/cd", "docker"}, {"devops", "cloud"},
        ],
        "keywords": ["devops", "cloud engineer", "sre", "infrastructure"],
    },
    {
        "role": "AI / Machine Learning Engineer",
        "req_any": [
            {"python", "pytorch"}, {"python", "tensorflow"}, {"scikit-learn", "python"},
            {"llm", "python"}, {"langchain", "python"}, {"deep learning", "machine learning"},
        ],
        "keywords": ["machine learning", "ai engineer", "data scientist", "deep learning"],
    },
    {
        "role": "Data Engineer",
        "req_any": [
            {"spark", "python"}, {"airflow", "sql"}, {"kafka", "python"},
            {"snowflake", "sql"}, {"databricks", "python"}, {"etl", "sql"},
        ],
        "keywords": ["data engineer", "data pipeline", "etl developer"],
    },
    {
        "role": "Mobile Engineer",
        "req_any": [
            {"react native", "mobile"}, {"flutter", "dart"}, {"swift", "ios"}, {"kotlin", "android"},
        ],
        "keywords": ["mobile developer", "ios developer", "android developer", "flutter"],
    },
    {
        "role": "Embedded / Systems Engineer",
        "req_any": [
            {"c", "c++", "embedded"}, {"c++", "rtos"}, {"embedded", "arm"}, {"firmware", "c"},
        ],
        "keywords": ["embedded systems", "firmware engineer", "systems engineer"],
    },
]

INTERN_KEYWORDS = re.compile(r"\b(pfe|intern|internship|stage|stagiaire|alternance|co-?op|apprentice|etudiant|étudiant|student)\b", re.I)


def infer_roles(profile: dict[str, Any], filename: str = "") -> dict[str, Any]:
    """Infers top candidate roles and confidence based on profile data and filename."""
    skills = set(s.lower().strip() for s in profile.get("skills", []))
    target_title = (profile.get("target_title") or "").strip()
    summary = (profile.get("summary") or "").lower()
    work_history = profile.get("work_experience") or profile.get("experience") or []
    
    role_scores: dict[str, float] = {}
    role_reasons: dict[str, list[str]] = {}

    def add_score(role: str, score: float, reason: str):
        role_scores[role] = role_scores.get(role, 0.0) + score
        if role not in role_reasons:
            role_reasons[role] = []
        role_reasons[role].append(reason)

    # 1. Direct target_title from resume header
    if target_title:
        title_lower = target_title.lower()
        matched_cluster = False
        for c in ROLE_CLUSTERS:
            if any(k in title_lower for k in c["keywords"]):
                add_score(c["role"], 0.70, f"Explicit target title '{target_title}'")
                matched_cluster = True
                break
        if not matched_cluster:
            # Non-cluster / non-standard title gets moderate confidence (below 0.50 threshold)
            add_score(target_title, 0.40, f"Title declared in resume: '{target_title}'")

    # 2. Work history job titles (weighted by recency)
    for idx, job in enumerate(work_history):
        title = (job.get("title") or "").strip().lower()
        if not title:
            continue
        weight = 0.50 if idx == 0 else (0.35 if idx == 1 else 0.20)
        for c in ROLE_CLUSTERS:
            if any(k in title for k in c["keywords"]):
                add_score(c["role"], weight, f"Previous role as {job.get('title')}")

    # 3. Skill clusters
    for c in ROLE_CLUSTERS:
        for pair in c["req_any"]:
            if pair.issubset(skills):
                add_score(c["role"], 0.35, f"Core stack match ({', '.join(pair)})")
                break

    # 4. Summary & Headline keywords
    for c in ROLE_CLUSTERS:
        if any(k in summary for k in c["keywords"]):
            add_score(c["role"], 0.20, f"Mentioned in summary")

    # 5. Fallback if empty: software engineer generic
    if not role_scores:
        if skills:
            role_scores["Software Engineer"] = 0.45
            role_reasons["Software Engineer"] = ["Technical skills present without clear specialization"]
        else:
            role_scores["Software Engineer"] = 0.20
            role_reasons["Software Engineer"] = ["Unspecified profile"]

    # Normalize confidences to [0.0, 1.0]
    ranked_roles = []
    for role, raw_score in sorted(role_scores.items(), key=lambda x: x[1], reverse=True)[:3]:
        conf = round(min(1.0, raw_score), 2)
        ranked_roles.append({
            "role": role,
            "confidence": conf,
            "reason": "; ".join(role_reasons.get(role, []))
        })

    # Confidence >= 0.5 becomes role_focus
    role_focus = [r["role"] for r in ranked_roles if r["confidence"] >= 0.5]
    status = "ready" if len(role_focus) > 0 else "needs_role"

    # Job type guess (suggestion for round 2 only - NEVER filters results)
    is_intern_filename = bool(INTERN_KEYWORDS.search(filename))
    is_intern_summary = bool(INTERN_KEYWORDS.search(summary))
    years_exp = float(profile.get("years_of_experience") or 0.0)
    
    if is_intern_filename or is_intern_summary or (years_exp <= 1.0 and "pfe" in filename.lower()):
        job_type_guess_val = "internship (PFE)"
    elif years_exp <= 2.0:
        job_type_guess_val = "junior full-time"
    else:
        job_type_guess_val = "full-time"

    job_type_guess = {
        "value": job_type_guess_val,
        "guess": True,
        "note": "Suggested default based on experience and file cues. Does not filter until confirmed.",
    }

    # Default region to Worldwide / anywhere for all candidates
    region_val = "Worldwide"

    region_guess = {
        "value": region_val,
        "guess": True,
        "note": "Default for anywhere in the world. Does not filter until confirmed.",
    }

    # Build concise profile summaries
    name_display = profile.get("name") or "Candidate"
    roles_display = ", ".join(f"{r['role']} ({int(r['confidence']*100)}%)" for r in ranked_roles)
    top_skills_display = ", ".join(list(profile.get("skills", []))[:6]) or "None listed"
    years_display = f"{years_exp:.1f} years" if years_exp else "Entry level / Student"

    one_line_summary = f"Name: {name_display} | Roles: {roles_display} | Exp: {years_display} | Top Skills: {top_skills_display}. Say if this is wrong."

    profile_summary = (
        f"Profile Summary:\n"
        f"- Name: {name_display}\n"
        f"- Inferred Roles: {roles_display}\n"
        f"- Experience: {years_display}\n"
        f"- Top Skills: {top_skills_display}"
    )

    # Candidate level inference: junior, mid, senior, lead
    exp_summary_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+of\s+experience", summary)
    if exp_summary_match:
        years_exp = float(exp_summary_match.group(1))
    elif "3y" in filename.lower() or "mid" in filename.lower():
        years_exp = 3.0

    if is_intern_filename or (years_exp < 1.0 and "pfe" in filename.lower()):
        inferred_level = "junior"
    elif years_exp <= 1.5:
        inferred_level = "junior"
    elif years_exp <= 4.0 or "mid" in filename.lower():
        inferred_level = "mid"
    elif years_exp <= 8.0:
        inferred_level = "senior"
    else:
        inferred_level = "lead"

    return {
        "roles": ranked_roles,
        "role_focus": role_focus,
        "status": status,
        "level": inferred_level,
        "inferred_level": inferred_level,
        "job_type_guess": job_type_guess,
        "region_guess": region_guess,
        "one_line_summary": one_line_summary,
        "profile_summary": profile_summary,
    }
