"""Match scoring. 0 to 100 with no artificial floor, a visible breakdown, and a confidence level."""
import re

from . import skills as sk
from .util import annualize, days_since, parse_salary

LEVELS = [("intern", 0), ("junior", 1), ("jr", 1), ("entry", 1), ("associate", 1), ("mid", 2), ("senior", 3), ("sr", 3),
          ("lead", 4), ("staff", 4), ("principal", 5), ("head", 5), ("manager", 4), ("director", 5), ("vp", 6)]
_LEVEL_RE = re.compile(r"\b(" + "|".join(k for k, _ in LEVELS) + r")\b\.?", re.I)
_LEVEL_MAP = dict(LEVELS)

TITLE_SYNONYMS = {"developer": "engineer", "programmer": "engineer", "swe": "engineer", "sde": "engineer", "dev": "engineer",
                  "fullstack": "full stack", "full-stack": "full stack", "frontend": "front end", "front-end": "front end",
                  "backend": "back end", "back-end": "back end", "devops": "platform", "sre": "platform",
                  "sr": "senior", "jr": "junior", "mgr": "manager", "ux": "design", "ui": "design"}
STOP = {"the", "and", "of", "for", "a", "an", "in", "at", "to", "ii", "iii", "i", "remote", "us", "uk", "emea",
        "senior", "junior", "lead", "staff", "principal", "sr", "jr", "intern", "associate", "mid"}


def title_tokens(title):
    t = (title or "").lower().replace("/", " ").replace(",", " ").replace("(", " ").replace(")", " ")
    for k, v in TITLE_SYNONYMS.items():
        t = re.sub(rf"(?<![a-z]){re.escape(k)}(?![a-z])", v, t)
    return {w for w in re.findall(r"[a-z+#]+", t) if w not in STOP and len(w) > 1}


def level_of(title):
    m = _LEVEL_RE.search(title or "")
    return _LEVEL_MAP[m.group(1).lower()] if m else None


def years_to_level(y):
    return 0 if y < 1 else 1 if y < 3 else 2 if y < 5 else 3 if y < 8 else 4


SENIORITY_MODIFIERS = [
    ("senior", "Senior"), ("sr", "Senior"), ("lead", "Lead"), ("staff", "Staff"),
    ("principal", "Principal"), ("junior", "Junior"),
    ("jr", "Junior"), ("entry", "Entry-level"), ("associate", "Associate"),
    ("intern", "Intern")
]

DISCIPLINES = {
    "fullstack": {
        "patterns": [r"full\s*stack", r"fullstack", r"mern", r"lamp"],
        "primary": ["Full Stack Developer", "Full Stack Engineer"],
        "laterals": ["Backend Developer", "Frontend Developer", "Software Engineer", "Web Developer"],
    },
    "backend": {
        "patterns": [r"back\s*end", r"backend", r"api\s+engineer", r"server\s*side", r"microservices"],
        "primary": ["Backend Engineer", "Backend Developer"],
        "laterals": ["Software Engineer", "API Engineer", "Full Stack Developer", "Platform Engineer"],
    },
    "frontend": {
        "patterns": [r"front\s*end", r"frontend", r"ui\s+engineer", r"client\s*side"],
        "primary": ["Frontend Engineer", "Frontend Developer"],
        "laterals": ["UI Engineer", "Web Developer", "Software Engineer", "Full Stack Developer"],
    },
    "ai_ml": {
        "patterns": [r"machine\s*learning", r"\bml\b", r"\bai\b", r"deep\s*learning", r"data\s*scientist", r"\bnlp\b", r"computer\s*vision"],
        "primary": ["Machine Learning Engineer", "AI Engineer", "Data Scientist"],
        "laterals": ["Applied AI Engineer", "Deep Learning Engineer", "MLOps Engineer", "Python Engineer", "Software Engineer"],
    },
    "data_eng": {
        "patterns": [r"data\s*engineer", r"analytics\s*engineer", r"big\s*data", r"\betl\b", r"database\s*engineer"],
        "primary": ["Data Engineer", "Analytics Engineer"],
        "laterals": ["Big Data Engineer", "Database Developer", "Backend Engineer", "Python Developer"],
    },
    "devops_cloud": {
        "patterns": [r"devops", r"cloud\s*engineer", r"\bsre\b", r"site\s*reliability", r"platform\s*engineer", r"infrastructure"],
        "primary": ["DevOps Engineer", "Cloud Engineer", "Site Reliability Engineer (SRE)"],
        "laterals": ["Platform Engineer", "Infrastructure Engineer", "Systems Engineer"],
    },
    "mobile": {
        "patterns": [r"mobile", r"\bios\b", r"android", r"react\s*native", r"flutter", r"swift", r"kotlin"],
        "primary": ["Mobile Developer", "Mobile Engineer"],
        "laterals": ["iOS Developer", "Android Developer", "Frontend Developer", "Software Engineer"],
    },
    "qa": {
        "patterns": [r"\bqa\b", r"quality\s*assurance", r"\bsdet\b", r"test\s*automation", r"software\s*test"],
        "primary": ["QA Engineer", "SDET", "Test Automation Engineer"],
        "laterals": ["QA Automation Specialist", "Software Engineer in Test"],
    },
    "security": {
        "patterns": [r"security", r"cyber", r"appsec", r"infosec", r"\bsoc\b"],
        "primary": ["Security Engineer", "Cybersecurity Specialist"],
        "laterals": ["Application Security Engineer", "Information Security Analyst"],
    },
    "product": {
        "patterns": [r"product\s*manag", r"product\s*owner", r"technical\s*product", r"scrum\s*master"],
        "primary": ["Product Manager", "Technical Product Manager"],
        "laterals": ["Product Owner", "Project Manager", "Scrum Master"],
    },
    "design": {
        "patterns": [r"ui/ux", r"ux\s*design", r"product\s*design", r"user\s*experience", r"ui\s*design"],
        "primary": ["Product Designer", "UI/UX Designer"],
        "laterals": ["UX Designer", "UI Designer", "UX Researcher"],
    },
    "data_analytics": {
        "patterns": [r"data\s*analyst", r"business\s*analyst", r"bi\s*analyst", r"analytics\s*specialist"],
        "primary": ["Data Analyst", "Business Analyst"],
        "laterals": ["BI Analyst", "Analytics Specialist", "Operations Analyst"],
    },
}

TECH_SPECIALIZATIONS = [
    ("Python", ["Python Developer", "Python Engineer"]),
    ("React", ["React Developer", "React Engineer"]),
    ("Node.js", ["Node.js Developer", "Node.js Backend Engineer"]),
    ("TypeScript", ["TypeScript Developer", "TypeScript Engineer"]),
    ("JavaScript", ["JavaScript Developer", "Full Stack JavaScript Developer"]),
    ("Go", ["Go Engineer", "Golang Developer"]),
    ("Rust", ["Rust Engineer", "Systems Engineer"]),
    ("Java", ["Java Developer", "Java Backend Engineer"]),
    ("C#", ["C# Developer", ".NET Developer"]),
    ("C++", ["C++ Engineer", "Systems Software Engineer"]),
    ("Ruby", ["Ruby on Rails Developer", "Ruby Developer"]),
    ("PHP", ["PHP Developer", "Full Stack PHP Developer"]),
    ("Kotlin", ["Kotlin Developer", "Android Developer"]),
    ("Swift", ["iOS Developer", "Swift Engineer"]),
    ("SQL", ["Database Developer", "SQL Developer"]),
    ("AWS", ["AWS Cloud Engineer"]),
    ("Kubernetes", ["Kubernetes Engineer", "DevOps Engineer"]),
    ("Docker", ["DevOps Engineer"]),
    ("PyTorch", ["Machine Learning Engineer", "PyTorch Engineer"]),
    ("TensorFlow", ["Machine Learning Engineer"]),
    ("LLMs / AI", ["AI Engineer", "LLM Engineer"]),
    ("Figma", ["Product Designer", "UI/UX Designer"]),
    ("Salesforce", ["Salesforce Developer", "Salesforce Administrator"]),
]


def detect_seniority(title, years=0):
    t = (title or "").lower()
    for raw, canonical in SENIORITY_MODIFIERS:
        if re.search(rf"\b{raw}\b", t):
            return canonical
    if years >= 5:
        return "Senior"
    if 0 < years <= 1.5:
        return "Junior"
    return ""


def derive_target_roles(profile):
    """Return all qualified roles for candidate based on target title, experience, and tech stack."""
    profile = profile or {}
    target = (profile.get("target_title") or "").strip()
    years = float(profile.get("years_of_experience") or 0)
    skills = profile.get("skills", []) or []
    skills_lower = {s.lower() for s in skills if isinstance(s, str)}
    skills_set = set(skills)

    # Experience past roles
    exp_roles = []
    for exp in profile.get("experience", [])[:4]:
        if isinstance(exp, dict):
            r = (exp.get("role") or "").strip()
            if r and r.lower() not in [x.lower() for x in exp_roles]:
                exp_roles.append(r)

    # Detect Seniority
    seniority = detect_seniority(target, years)

    # Detect Disciplines from Title, Experience, and Skills
    detected_disciplines = []
    combined_titles = " ".join([target] + exp_roles).lower()

    for disc_key, disc_cfg in DISCIPLINES.items():
        for pat in disc_cfg["patterns"]:
            if re.search(pat, combined_titles):
                detected_disciplines.append(disc_key)
                break

    # If no discipline detected from title (or title empty/vague): infer from skill gravity!
    if not detected_disciplines and skills:
        cat_counts = {}
        for s in skills:
            if isinstance(s, str):
                cat = sk.CATEGORY_OF.get(s, "Other")
                cat_counts[cat] = cat_counts.get(cat, 0) + 1

        # Specific tool gravity overrides
        design_skills = {"figma", "ux design", "ui design", "user research", "product design"}
        analytics_skills = {"tableau", "power bi", "excel", "data analysis", "bi analyst", "google analytics"}
        mobile_skills = {"swift", "kotlin", "react native", "flutter", "ios", "android"}
        qa_skills = {"cypress", "playwright", "selenium", "unit testing", "test automation"}

        if any(s.lower() in design_skills for s in skills if isinstance(s, str)):
            detected_disciplines.append("design")
        elif any(s.lower() in analytics_skills for s in skills if isinstance(s, str)) and cat_counts.get("Backend", 0) == 0:
            detected_disciplines.append("data_analytics")
        elif any(s.lower() in mobile_skills for s in skills if isinstance(s, str)):
            detected_disciplines.append("mobile")
        elif cat_counts.get("AI & ML", 0) >= 2:
            detected_disciplines.append("ai_ml")
        elif cat_counts.get("Cloud & DevOps", 0) >= 3:
            detected_disciplines.append("devops_cloud")
        elif cat_counts.get("Frontend", 0) >= 2 and cat_counts.get("Backend", 0) >= 2:
            detected_disciplines.append("fullstack")
        elif cat_counts.get("Frontend", 0) >= 2:
            detected_disciplines.append("frontend")
        elif cat_counts.get("Backend", 0) >= 2 or cat_counts.get("Architecture", 0) >= 2:
            detected_disciplines.append("backend")
        elif cat_counts.get("Data", 0) >= 2:
            detected_disciplines.append("data_eng")
        elif cat_counts.get("Product & Design", 0) >= 2:
            detected_disciplines.append("product")
        elif cat_counts.get("Languages", 0) >= 1:
            detected_disciplines.append("backend")

    # If still none and target exists, default to backend/software engineering
    if not detected_disciplines and target:
        detected_disciplines = ["fullstack" if "full" in target.lower() else "backend"]

    # Assemble Roles with hierarchy
    roles_ordered = []
    seen = set()

    def add_role(role_name, apply_sen=False):
        clean = (role_name or "").strip()
        if not clean:
            return
        if apply_sen and seniority and not any(re.search(rf"\b{raw}\b", clean.lower()) for raw, _ in SENIORITY_MODIFIERS):
            clean = f"{seniority} {clean}"
        k = clean.lower()
        if k not in seen:
            seen.add(k)
            roles_ordered.append(clean)

    # 1. Exact user target title if present
    if target:
        add_role(target)

    # 2. Past roles from experience
    for r in exp_roles:
        add_role(r)

    # 3. Primary & lateral roles for all detected disciplines
    for d in detected_disciplines:
        cfg = DISCIPLINES.get(d)
        if not cfg:
            continue
        for p in cfg["primary"]:
            add_role(p, apply_sen=bool(seniority and seniority != "Entry-level"))
            add_role(p, apply_sen=False)
        for lat in cfg["laterals"]:
            add_role(lat, apply_sen=bool(seniority and seniority != "Entry-level"))
            add_role(lat, apply_sen=False)

    # 4. Tech stack specializations matching user's actual skills
    for tech_name, spec_roles in TECH_SPECIALIZATIONS:
        if tech_name in skills_set or tech_name.lower() in skills_lower or any(tech_name.lower() in s.lower() for s in skills if isinstance(s, str)):
            for sr in spec_roles:
                add_role(sr, apply_sen=bool(seniority == "Senior"))
                add_role(sr, apply_sen=False)

    return roles_ordered


def _title_score(job_title, profile):
    candidates = derive_target_roles(profile)
    jt = title_tokens(job_title)
    if not jt:
        return 0.0

    cand_skills = {s.lower() for s in profile.get("skills", [])}
    is_engineer = "engineer" in jt
    is_job_backend = "back" in jt and "end" in jt
    is_job_frontend = "front" in jt and "end" in jt
    is_job_fullstack = "full" in jt and "stack" in jt

    best = 0.0
    for i, c in enumerate(x for x in candidates if x):
        ct = title_tokens(c)
        if not ct or not jt:
            continue
        overlap = len(ct & jt) / len(ct | jt)
        contain = len(ct & jt) / min(len(ct), len(jt))
        s = 0.55 * overlap + 0.45 * contain

        is_cand_fullstack = "full" in ct and "stack" in ct
        is_cand_backend = "back" in ct and "end" in ct
        is_cand_frontend = "front" in ct and "end" in ct

        # Role family affinity:
        # Full stack candidates are fully qualified for Backend, Frontend, and Software Engineering
        if is_cand_fullstack and is_engineer:
            if is_job_backend or is_job_frontend:
                s = max(s, 0.88)
            elif is_job_fullstack:
                s = max(s, 1.0)
            elif not (is_job_backend or is_job_frontend or is_job_fullstack):
                s = max(s, 0.90)
        elif is_cand_backend and is_engineer:
            if is_job_fullstack or ("software" in jt):
                s = max(s, 0.85)
        elif is_cand_frontend and is_engineer:
            if is_job_fullstack or ("web" in jt) or ("software" in jt):
                s = max(s, 0.85)

        # Tech stack alignment: job title specifies a core language/framework in candidate's skills
        # e.g., 'Python Developer', 'React Engineer', 'Node.js Developer'
        if is_engineer:
            for w in jt:
                if w in cand_skills:
                    s = max(s, 0.92 if is_cand_fullstack else 0.88)
                    break

        weight = 1.0 if i < 2 else 0.90
        best = max(best, s * weight)
    return best


def _mode_of(job):
    m = (job.get("work_mode") or "").lower()
    loc = (job.get("location") or "").lower()
    if "remote" in m or "remote" in loc or "anywhere" in loc or "worldwide" in loc:
        return "remote"
    if "hybrid" in m or "hybrid" in loc:
        return "hybrid"
    if m in ("on-site", "onsite") or "on-site" in loc or "onsite" in loc:
        return "onsite"
    return "unknown"


def score_job(job, profile):
    text = f"{job.get('title', '')}\n{job.get('description', '')}\n{' '.join(job.get('tags', []) or [])}"
    weights = sk.extract_weighted(text)
    cand = set(profile.get("skills", []))
    cand_l = {c.lower() for c in cand}
    matched = sorted(s for s in weights if s in cand or s.lower() in cand_l)
    missing = sorted(s for s in weights if s not in matched)

    # Affinity: a sister technology in the same cluster earns partial credit (Postgres for MySQL).
    affinity, credit = [], {}
    for m in missing:
        for cname, members in sk.CLUSTERS.items():
            if m in members and members & cand:
                have = sorted(members & cand)[:2]
                affinity.append(f"{m} ~ {', '.join(have)}")
                credit[m] = 0.45
                break

    title_ratio = _title_score(job.get("title", ""), profile)
    title_pts = title_ratio * 20

    total_w = sum(weights.values())
    desc_len = len(job.get("description", "") or "")
    if total_w > 0:
        cov = (sum(weights[s] for s in matched) + sum(weights[s] * credit[s] for s in credit)) / total_w
        skill_pts = cov * 50
    else:
        skill_pts = 18 + (title_ratio * 10)  # unknown requirements: neutral baseline + title alignment boost

    # Seniority and years
    sen_pts = 7.0
    jl, y = level_of(job.get("title", "")), float(profile.get("years_of_experience") or 0)
    if y:
        cl = years_to_level(y)
        if jl is not None:
            sen_pts = {0: 10, 1: 6, 2: 2}.get(abs(jl - cl), 0) if jl >= cl else {0: 10, 1: 7, 2: 4}.get(abs(jl - cl), 1)
        need = sk.years_required(job.get("description", ""))
        if need:
            sen_pts = min(sen_pts, 10 if y >= need else 7 if y >= need - 1 else 3 if y >= need - 2 else 0)

    # Work mode and location
    jm, cm = _mode_of(job), (profile.get("work_mode") or "Any").lower()
    prefs = [p.lower() for p in profile.get("preferred_locations", []) if p and p.lower() not in ("remote", "worldwide")]
    loc = (job.get("location") or "").lower()
    if cm in ("any", ""):
        mode_pts = 8 if jm != "unknown" else 6
    elif cm in jm or (cm == "remote" and jm == "remote"):
        mode_pts = 10
    elif jm == "unknown":
        mode_pts = 5
    else:
        mode_pts = 2
    if jm in ("hybrid", "onsite") and prefs:
        mode_pts = max(mode_pts, 9 if any(p.split(",")[0] in loc for p in prefs) else mode_pts - 2)
    mode_pts = max(0, min(10, mode_pts))

    # Freshness and salary
    age = days_since(job.get("posted_at"))
    fresh_pts = 3 if age is None else 5 if age <= 7 else 4 if age <= 21 else 2 if age <= 45 else 0
    sal_pts = 3
    want = float(profile.get("min_salary") or 0)
    ann = annualize(parse_salary(job.get("salary", "")))
    if want and ann:
        sal_pts = 5 if ann[1] >= want else 0
    elif ann:
        sal_pts = 4

    score = skill_pts + title_pts + sen_pts + mode_pts + fresh_pts + sal_pts
    notes = []
    # Domain gate: a different profession with almost no skill overlap must not look like a fit.
    if title_ratio < 0.12 and len(matched) <= 1:
        score = min(score, 32)
        notes.append("Job title is in a different field from your target roles.")
    bad = [k for k in profile.get("excluded_keywords", []) if k and k.lower() in text.lower()]
    if bad:
        score = min(score, 25)
        notes.append("Contains excluded keyword: " + ", ".join(bad[:3]))
    score = int(round(max(0, min(100, score))))

    confidence = "high" if total_w >= 3 and desc_len > 400 else "medium" if total_w >= 1 else "low"
    if confidence == "low":
        notes.append("Few requirements were readable from this posting, so the score leans on the title.")

    if score >= 85:
        label = "Excellent fit"
    elif score >= 70:
        label = "Strong fit"
    elif score >= 50:
        label = "Moderate fit"
    else:
        label = "Weak fit"
    parts = []
    if weights:
        parts.append(f"Matches {len(matched)} of {len(weights)} skills named in the posting"
                     + (f" ({', '.join(matched[:4])})" if matched else ""))
    if missing:
        parts.append("Missing: " + ", ".join(missing[:4]))
    if affinity:
        parts.append("Related experience: " + "; ".join(affinity[:2]))
    parts += notes
    parts = [x.rstrip(".") for x in parts]
    rationale = f"{label} ({score}%). " + ". ".join(parts) + "." if parts else f"{label} ({score}%)."
    return {
        "score": score, "matched_skills": matched, "missing_skills": missing, "affinity_matches": affinity,
        "rationale": rationale, "confidence": confidence,
        "score_breakdown": {"skills": round(skill_pts, 1), "title": round(title_pts, 1), "seniority": round(sen_pts, 1),
                            "work_mode": round(mode_pts, 1), "freshness": fresh_pts, "salary": sal_pts},
        "required_skills": {k: v for k, v in weights.items()},
    }
