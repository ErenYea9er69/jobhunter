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

ROLE_TITLE_FAMILIES: dict[str, list[str]] = {
    "Cloud / DevOps Engineer": ["Cloud Engineer", "DevOps Engineer", "Site Reliability Engineer", "Platform Engineer", "Infrastructure Engineer"],
    "Full Stack Software Engineer": ["Full Stack Software Engineer", "Full Stack Developer", "Software Engineer", "Product Engineer", "Web Application Engineer"],
    "Backend Software Engineer": ["Backend Software Engineer", "Backend Engineer", "API Engineer", "Distributed Systems Engineer", "Platform Backend Engineer"],
    "Frontend Engineer": ["Frontend Engineer", "Frontend Developer", "UI Software Engineer", "React Engineer", "Web UI Developer"],
    "AI / ML Engineer": ["AI / ML Engineer", "Machine Learning Engineer", "Applied AI Engineer", "LLM Engineer", "MLOps Engineer"],
    "Data Engineer": ["Data Engineer", "Analytics Engineer", "ETL Developer", "Data Platform Engineer", "Big Data Engineer"],
    "Mobile Developer": ["Mobile Developer", "Mobile Software Engineer", "iOS Developer", "Android Developer", "React Native Engineer"],
    "QA / Test Automation Engineer": ["QA Automation Engineer", "Software Development Engineer in Test", "QA Engineer", "Test Automation Engineer", "Quality Engineer"],
    "Cybersecurity Analyst / Engineer": ["Cybersecurity Engineer", "Security Analyst", "Application Security Engineer", "Information Security Analyst", "SOC Engineer"],
    "Embedded / Systems Engineer": ["Embedded Systems Engineer", "Firmware Engineer", "Systems Engineer", "Embedded Software Developer", "RTOS Engineer"],
    "Software Engineer": ["Software Engineer", "Software Developer", "Application Developer", "Systems Developer", "Associate Software Engineer"],
    "Product Manager": ["Product Manager", "Technical Product Manager", "Product Owner", "Associate Product Manager", "Platform Product Manager"],
    "Data Analyst": ["Data Analyst", "Business Intelligence Analyst", "Product Analyst", "Operations Analyst", "Quantitative Analyst"],
}


def expand_title_family(role_name: str) -> list[str]:
    """Return ~5 closely related standard titles for search query expansion only (never a filter)."""
    clean = (role_name or "").strip()
    if not clean:
        return ["Software Engineer", "Software Developer", "Application Engineer", "Backend Engineer", "Full Stack Developer"]
    if clean in ROLE_TITLE_FAMILIES:
        return list(ROLE_TITLE_FAMILIES[clean])
    low = clean.lower()
    for canon, fam in ROLE_TITLE_FAMILIES.items():
        if canon.lower() == low or any(low == f.lower() for f in fam):
            out = [clean] + [f for f in fam if f.lower() != low]
            return out[:5]
    # Generic deterministic expansion preserving role noun + core synonyms
    variants = [clean]
    if "engineer" in low:
        variants.extend([
            re.sub(r"\bengineer\b", "Developer", clean, flags=re.I),
            f"{clean} Specialist",
            f"Associate {clean}",
            f"Platform {clean}",
        ])
    elif "developer" in low:
        variants.extend([
            re.sub(r"\bdeveloper\b", "Engineer", clean, flags=re.I),
            f"Application {clean}",
            f"Associate {clean}",
            f"Software {clean}",
        ])
    elif "manager" in low:
        variants.extend([
            f"Senior {clean}",
            f"Lead {clean}",
            f"{clean} Specialist",
            f"Program {clean}",
        ])
    else:
        variants.extend([
            f"{clean} Specialist",
            f"{clean} Lead",
            f"{clean} Associate",
            f"{clean} Analyst",
        ])
    deduped = []
    for v in variants:
        vs = " ".join(v.split())
        if vs and vs not in deduped:
            deduped.append(vs)
    return deduped[:5]


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

    # 2. Work history job titles (weighted by recency; accept both 'role' and 'title')
    for idx, job in enumerate(work_history):
        raw_title = (job.get("role") or job.get("title") or "").strip()
        title = raw_title.lower()
        if not title:
            continue
        weight = 0.50 if idx == 0 else (0.35 if idx == 1 else 0.20)
        for c in ROLE_CLUSTERS:
            if any(k in title for k in c["keywords"]):
                add_score(c["role"], weight, f"Previous role as {raw_title}")

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

    # Normalize confidences to [0.0, 1.0] and expand each inferred role into ~5 search-query-only title variants
    ranked_roles = []
    all_title_families: list[str] = []
    for role, raw_score in sorted(role_scores.items(), key=lambda x: x[1], reverse=True)[:3]:
        conf = round(min(1.0, raw_score), 2)
        family = expand_title_family(role)
        for t in family:
            if t not in all_title_families:
                all_title_families.append(t)
        ranked_roles.append({
            "role": role,
            "confidence": conf,
            "reason": "; ".join(role_reasons.get(role, [])),
            "title_family": family,
            "is_guess": True,
            "usage": "search_query_only",
        })

    # Confidence >= 0.5 becomes role_focus
    role_focus = [r["role"] for r in ranked_roles if r["confidence"] >= 0.5]
    status = "ready" if len(role_focus) > 0 else "needs_role"

    # Job type guess (suggestion for round 2 only - NEVER filters results)
    is_intern_filename = bool(INTERN_KEYWORDS.search(filename))
    is_intern_summary = bool(INTERN_KEYWORDS.search(summary))
    years_exp = float(profile.get("years_of_experience") if profile.get("years_of_experience") is not None else (profile.get("years_experience") or 0.0))
    
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

    # Contract Step 2/3 Place Rule: resume NEVER supplies place, remote choice, or filter.
    region_guess = {
        "value": "",
        "guess": True,
        "source": "never_from_resume",
        "note": "Place is never guessed from resume, address, phone, IP, or language. Confirm explicitly with user.",
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
        "title_families": all_title_families,
        "status": status,
        "level": inferred_level,
        "inferred_level": inferred_level,
        "job_type_guess": job_type_guess,
        "region_guess": region_guess,
        "one_line_summary": one_line_summary,
        "profile_summary": profile_summary,
    }
