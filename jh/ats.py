"""ATS readiness audit. Scores what can be measured from the resume text. No score floor, no cap."""
import re

from . import skills as sk

POWER_VERBS = {
    "architected", "engineered", "led", "orchestrated", "streamlined", "optimized", "scaled", "automated", "refactored",
    "designed", "deployed", "developed", "built", "mentored", "implemented", "reduced", "increased", "launched", "created",
    "improved", "migrated", "delivered", "managed", "drove", "established", "analyzed", "negotiated", "trained", "wrote",
    "owned", "shipped", "cut", "raised", "grew", "coordinated", "introduced", "set", "tuned", "added", "maintained",
}
METRIC = re.compile(r"\d+[\d,.]*\s?%|\$\s?\d|\b\d{2,}[\d,]*\b|\b\d+x\b|\b\d+\+?\s*(?:users|clients|engineers|teams|days|hours|customers|requests|people|patients|accounts)\b", re.I)


def _resume_text(r):
    parts = [r.get("summary", ""), " ".join(r.get("skills", []))]
    for e in r.get("experience", []):
        parts += [e.get("role", ""), e.get("company", ""), " ".join(e.get("bullets", []))]
    return "\n".join(parts)


def compute_ats_audit(resume, job):
    job_text = f"{job.get('title', '')}\n{job.get('description', '')}"
    weights = sk.extract_weighted(job_text)
    ranked = sorted(weights, key=lambda s: -weights[s])[:12]
    text = _resume_text(resume).lower()

    kw = []
    for s in ranked:
        n = len(re.findall(r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])", text))
        kw.append({"keyword": s, "occurrences": n, "status": "missing" if n == 0 else "stuffed" if n > 6 else "optimal",
                   "importance": "required" if weights[s] >= 0.85 else "preferred" if weights[s] <= 0.4 else "responsibility"})
    covered = sum(weights[k["keyword"]] for k in kw if k["status"] == "optimal")
    total_w = sum(weights[k["keyword"]] for k in kw)
    keyword_score = round((covered / total_w) * 40) if total_w else 20
    stuffed = [k["keyword"] for k in kw if k["status"] == "stuffed"]
    keyword_score = max(0, keyword_score - 3 * len(stuffed))

    has = {"summary": bool(resume.get("summary")), "skills": bool(resume.get("skills")),
           "experience": bool(resume.get("experience")), "education": bool(resume.get("education"))}
    contact = {"email": bool(resume.get("email")), "phone": bool(resume.get("phone")), "name": bool(resume.get("name"))}
    structure_score = sum(4 for v in has.values() if v) + 0  # up to 16
    contact_score = round(sum(contact.values()) / 3 * 4)       # up to 4

    bullets = [b for e in resume.get("experience", []) for b in e.get("bullets", [])]
    n = max(1, len(bullets))
    with_metric = [b for b in bullets if METRIC.search(b)]
    metric_ratio = len(with_metric) / n if bullets else 0
    metrics_score = round(min(1.0, metric_ratio / 0.6) * 20)
    first = [re.split(r"\W+", b.strip().lower())[0] for b in bullets if b.strip()]
    verb_ratio = sum(1 for w in first if w in POWER_VERBS) / n if bullets else 0
    verbs_score = round(min(1.0, verb_ratio / 0.7) * 10)
    length_ok = 3 <= len(bullets) <= 30
    length_score = 10 if length_ok else 4 if bullets else 0

    total = keyword_score + structure_score + contact_score + metrics_score + verbs_score + length_score
    total = int(max(0, min(100, total)))
    grade = "A" if total >= 90 else "B" if total >= 80 else "C" if total >= 70 else "D" if total >= 55 else "F"

    checklist = [
        {"id": "sections", "label": "Standard section headings present", "status": "pass" if all(has.values()) else "warning",
         "explanation": "Missing: " + ", ".join(k for k, v in has.items() if not v) if not all(has.values()) else "Summary, skills, experience and education are all present."},
        {"id": "contact", "label": "Contact details present", "status": "pass" if all(contact.values()) else "fail",
         "explanation": "Missing: " + ", ".join(k for k, v in contact.items() if not v) if not all(contact.values()) else "Name, email and phone found."},
        {"id": "metrics", "label": "Measurable results in bullets", "status": "pass" if metric_ratio >= 0.5 else "warning" if metric_ratio >= 0.25 else "fail",
         "explanation": f"{int(metric_ratio * 100)}% of bullets contain a number, percentage, or scale figure."},
        {"id": "verbs", "label": "Bullets start with action verbs", "status": "pass" if verb_ratio >= 0.7 else "warning",
         "explanation": f"{int(verb_ratio * 100)}% of bullets open with an action verb."},
        {"id": "keywords", "label": "Posting keywords covered", "status": "pass" if kw and covered / max(total_w, 1) >= 0.7 else "warning",
         "explanation": f"{sum(1 for k in kw if k['status'] == 'optimal')} of {len(kw)} top posting keywords appear in your resume." if kw else "No readable keywords in the posting."},
        {"id": "stuffing", "label": "No keyword stuffing", "status": "fail" if stuffed else "pass",
         "explanation": ("Repeated too often: " + ", ".join(stuffed)) if stuffed else "No keyword appears more than six times."},
    ]
    recs = []
    miss = [k for k in kw if k["status"] == "missing"]
    true_miss = [k["keyword"] for k in miss if k["keyword"] not in set(resume.get("skills", []))]
    if miss:
        recs.append("Keywords from the posting not in your resume: " + ", ".join(k["keyword"] for k in miss[:5])
                    + ". Add one only where it is true. Do not add skills you lack.")
    if metric_ratio < 0.5:
        recs.append("Add real numbers to more bullets: scale, percentages, time saved, money, or team size.")
    if verb_ratio < 0.7:
        recs.append("Start more bullets with an action verb such as built, led, or reduced.")
    if not all(contact.values()):
        recs.append("Add the missing contact details.")
    if not recs:
        recs.append("No blockers found. Check the posting once more for requirements the audit cannot read.")
    return {
        "ats_score": total, "grade": grade, "ats_grade": grade,
        "breakdown": {"keyword_score": keyword_score, "structure_score": structure_score + contact_score,
                      "metrics_score": metrics_score, "verbs_score": verbs_score, "length_score": length_score,
                      "quantified_bullets_pct": int(metric_ratio * 100)},
        "keyword_score": keyword_score, "sections_score": structure_score + contact_score, "metrics_score": metrics_score,
        "verbs_score": verbs_score, "top_keywords_density": [{"keyword": k["keyword"], "count": k["occurrences"], "status": k["status"]} for k in kw],
        "keyword_matches": kw, "quantified_ratio": f"{int(metric_ratio * 100)}%",
        "checklist": [{"rule": c["label"], "passed": c["status"] == "pass", "details": c["explanation"]} for c in checklist],
        "raw_checklist": checklist, "recommendations": recs,
        "note": "The audit scores text content. It cannot see the layout of an exported file.",
    }
