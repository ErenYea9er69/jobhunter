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


def _title_score(job_title, profile):
    candidates = [profile.get("target_title", "")]
    candidates += [e.get("role", "") for e in profile.get("experience", [])[:3]]
    jt = title_tokens(job_title)
    best = 0.0
    for i, c in enumerate(x for x in candidates if x):
        ct = title_tokens(c)
        if not ct or not jt:
            continue
        overlap = len(ct & jt) / len(ct | jt)
        contain = len(ct & jt) / min(len(ct), len(jt))
        s = 0.55 * overlap + 0.45 * contain
        best = max(best, s * (1.0 if i == 0 else 0.85))
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
