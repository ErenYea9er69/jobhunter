"""Truthful tailoring. Every claim in an output must trace back to the master resume.

The deterministic engine only reorders and re-words using terms already true of the candidate.
An optional LLM can rewrite more freely, but each rewrite passes a grounding check first."""
import copy
import json
import re

from . import config, skills as sk
from .util import http_get, HttpError

NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
IRREGULAR = {"built", "led", "wrote", "ran", "drove", "cut", "set", "made", "grew", "won", "taught", "became", "began", "chose"}


# ------------------------------------------------------------ grounding

def resume_corpus(profile):
    parts = [profile.get("summary", ""), " ".join(profile.get("skills", [])), profile.get("target_title", "")]
    for e in profile.get("experience", []):
        parts += [e.get("role", ""), e.get("company", ""), " ".join(e.get("bullets", []))]
    for e in profile.get("education", []):
        parts += [e.get("degree", ""), e.get("institution", "")]
    return "\n".join(parts)


def _nums(text):
    return {n.replace(",", "") for n in NUM_RE.findall(text or "")}


def ungrounded(profile, new_text):
    """Return facts in new_text that the resume does not support: numbers and skills."""
    corpus = resume_corpus(profile)
    cand_skills = set(sk.extract(corpus)) | set(profile.get("skills", []))
    bad_nums = sorted(n for n in _nums(new_text) - _nums(corpus) if n not in ("0", "1"))
    # Years are computed from dates, so a years figure equal to years_of_experience is grounded.
    y = profile.get("years_of_experience")
    if y:
        bad_nums = [n for n in bad_nums if n not in {str(int(y)), str(y), str(int(y) + 1)}]
    bad_skills = sorted(s for s in sk.extract(new_text) if s not in cand_skills)
    return {"numbers": bad_nums, "skills": bad_skills}


def is_grounded(profile, new_text):
    r = ungrounded(profile, new_text)
    return not r["numbers"] and not r["skills"]


# ------------------------------------------------------------ helpers

def _aliases_for(canon):
    for cat in sk.ONTOLOGY.values():
        if canon in cat:
            return [a.lstrip("=") for a in cat[canon]] + [canon]
    return [canon]


def _relevance(bullet, wanted):
    found = set(sk.extract(bullet))
    base = sum(wanted.get(s, 0) for s in found)
    words = set(re.findall(r"[a-z]{4,}", bullet.lower()))
    bonus = 0.15 * len(words & wanted.get("__words__", set()))
    metric = 0.3 if NUM_RE.search(bullet) else 0
    return base + bonus + metric


def _align_terms(bullet, job_text, cand_skills):
    """Swap a skill's spelling for the spelling the job uses (Postgres to PostgreSQL). Same skill, no new claim."""
    changed = bullet
    for canon in sk.extract(bullet):
        if canon not in cand_skills:
            continue
        forms = _aliases_for(canon)
        job_forms = [f for f in forms if re.search(rf"(?<![A-Za-z0-9]){re.escape(f)}(?![A-Za-z0-9])", job_text, re.I)]
        if not job_forms:
            continue
        best = max(job_forms, key=lambda f: len(re.findall(re.escape(f), job_text, re.I)))
        target = re.search(rf"(?<![A-Za-z0-9]){re.escape(best)}(?![A-Za-z0-9])", job_text, re.I).group(0)  # the job's own spelling
        for f in forms:
            if f.lower() == target.lower():
                continue
            changed = re.sub(rf"(?<![A-Za-z0-9]){re.escape(f)}(?![A-Za-z0-9])", target, changed, flags=re.I) \
                if f.lower() in changed.lower() and target.lower() not in changed.lower() else changed
    return changed


def _wanted(job):
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    w = dict(sk.extract_weighted(text))
    w["__words__"] = set(re.findall(r"[a-z]{4,}", (job.get("title", "") or "").lower()))
    return w, text


def _years_phrase(profile):
    y = profile.get("years_of_experience") or 0
    if not y:
        return ""
    y = int(y) if float(y).is_integer() else y
    return f"{y} year{'s' if y != 1 else ''}"


# ------------------------------------------------------------ deterministic engine

def refit_deterministic(job, profile):
    wanted, job_text = _wanted(job)
    cand = set(profile.get("skills", []))
    matched = [s for s in wanted if s != "__words__" and s in cand]
    orig_skills = list(profile.get("skills", []))
    new_skills = [s for s in orig_skills if s in matched] + [s for s in orig_skills if s not in matched]

    diffs = []
    exps = copy.deepcopy(profile.get("experience", []))

    # Summary: lead with true facts (own title, years, matched skills), then keep the original text.
    role = (exps[0].get("role") if exps else "") or profile.get("target_title", "")
    lead_bits = [role] if role else []
    yp = _years_phrase(profile)
    lead = ""
    if role and yp:
        lead = f"{role} with {yp} of experience"
    elif role:
        lead = role
    if lead and matched:
        lead += f" working with {', '.join(matched[:4])}"
    orig_sum = (profile.get("summary") or "").strip()
    new_sum = (lead + ". " if lead else "") + orig_sum
    if lead and lead.lower() in orig_sum.lower():
        new_sum = orig_sum
    new_sum = new_sum.strip()
    diffs.append({"id": "diff_summary", "section": "Professional Summary", "label": "Summary Tailoring",
                  "original": orig_sum, "proposed": new_sum,
                  "status": "modified" if new_sum != orig_sum else "unchanged",
                  "rationale": "Opens with your real title, years, and the skills this posting asks for that you list. No new claims.",
                  "grounded": True})
    diffs.append({"id": "diff_skills", "section": "Core Competencies", "label": "Skill Prioritization",
                  "original": ", ".join(orig_skills[:12]), "proposed": ", ".join(new_skills[:12]),
                  "status": "reordered" if new_skills != orig_skills else "unchanged",
                  "rationale": ("Moves skills named in the posting to the front: " + ", ".join(matched[:4]) + ".") if matched
                  else "No skills from the posting matched your list, so the order is unchanged.",
                  "grounded": True})

    for xi, e in enumerate(exps):
        bullets = list(e.get("bullets", []))
        ranked = sorted(range(len(bullets)), key=lambda i: (-_relevance(bullets[i], wanted), i))
        reordered = [bullets[i] for i in ranked]
        aligned = [_align_terms(b, job_text, cand) for b in reordered]
        for bi, (before, after) in enumerate(zip(reordered, aligned)):
            if before != after:
                diffs.append({"id": f"diff_exp_{xi}_{bi}", "section": f"{e.get('role')} @ {e.get('company')}",
                              "label": f"Bullet wording #{bi + 1}", "original": before, "proposed": after, "status": "modified",
                              "rationale": "Uses the posting's spelling of a skill you already used. Same skill, same facts.", "grounded": True})
        if reordered != bullets:
            diffs.append({"id": f"diff_order_{xi}", "section": f"{e.get('role')} @ {e.get('company')}", "label": "Bullet order",
                          "original": "\n".join(bullets), "proposed": "\n".join(aligned), "status": "reordered",
                          "rationale": "Puts the bullets closest to this job's requirements first.", "grounded": True})
        e["bullets"] = aligned

    tailored = copy.deepcopy(profile)
    tailored.update(summary=new_sum, skills=new_skills, experience=exps)
    return tailored, diffs, matched, "deterministic"


# ------------------------------------------------------------ optional LLM engine

def llm_available():
    return bool(config.ANTHROPIC_API_KEY)


def _call_llm(system, user):
    body = json.dumps({"model": config.LLM_MODEL, "max_tokens": 3000, "system": system,
                       "messages": [{"role": "user", "content": user}]}).encode()
    raw = http_get("https://api.anthropic.com/v1/messages", data=body, method="POST", retries=0,
                   timeout=config.LLM_TIMEOUT_SECONDS,
                   headers={"Content-Type": "application/json", "x-api-key": config.ANTHROPIC_API_KEY,
                            "anthropic-version": "2023-06-01"})
    data = json.loads(raw)
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


LLM_SYSTEM = ("You edit resumes. Use ONLY facts present in the resume JSON. Never add a number, skill, tool, employer, title, "
              "or claim that the resume does not state. You may reword, reorder, and mirror the job posting's terminology for "
              "skills the candidate already has. Reply with JSON only: {\"summary\": str, \"bullets\": {\"<role_index>.<bullet_index>\": str}}.")


def refit_llm(job, profile, llm=None):
    """Return (tailored, diffs, matched, engine). Rewrites that fail the grounding check fall back to the original."""
    base, diffs, matched, _ = refit_deterministic(job, profile)
    llm = llm or _call_llm
    payload = {"job": {"title": job.get("title"), "company": job.get("company"), "description": (job.get("description") or "")[:3500]},
               "resume": {"summary": profile.get("summary"), "skills": profile.get("skills"),
                          "experience": [{"role": e.get("role"), "company": e.get("company"), "bullets": e.get("bullets")}
                                         for e in profile.get("experience", [])]}}
    try:
        out = llm(LLM_SYSTEM, json.dumps(payload))
        out = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
    except Exception:
        return base, diffs, matched, "deterministic (LLM unavailable)"

    rejected = 0
    tailored = copy.deepcopy(base)
    new_sum = (out.get("summary") or "").strip()
    if new_sum and is_grounded(profile, new_sum):
        tailored["summary"] = new_sum
        for d in diffs:
            if d["id"] == "diff_summary":
                d.update(proposed=new_sum, status="modified", rationale="Rewritten by the LLM. Checked: no new numbers or skills.")
    elif new_sum:
        rejected += 1
    for key, text in (out.get("bullets") or {}).items():
        try:
            xi, bi = (int(p) for p in key.split("."))
            orig = profile["experience"][xi]["bullets"][bi]
        except Exception:
            continue
        if text and text != orig and is_grounded(profile, text):
            diffs.append({"id": f"diff_llm_{xi}_{bi}", "section": f"{profile['experience'][xi].get('role')} @ {profile['experience'][xi].get('company')}",
                          "label": f"LLM rewrite #{bi + 1}", "original": orig, "proposed": text, "status": "modified",
                          "rationale": "Rewritten by the LLM. Checked: no new numbers or skills.", "grounded": True})
            tailored["experience"][xi]["bullets"][bi] = text
        elif text and text != orig:
            rejected += 1
    return tailored, diffs, matched, f"llm ({rejected} rewrite(s) rejected for unsupported claims)"


def refine_resume_for_job(job, profile, use_llm=None):
    use_llm = llm_available() if use_llm is None else use_llm
    tailored, diffs, matched, engine = (refit_llm if use_llm else refit_deterministic)(job, profile)
    return {"job_id": job.get("id"), "job_title": job.get("title"), "company": job.get("company"),
            "tailored_summary": tailored["summary"], "tailored_skills": tailored["skills"],
            "tailored_experience": tailored["experience"], "diff_items": diffs, "engine": engine,
            "tailored_resume": tailored, "guarantee": "Every number and skill in the tailored resume appears in your master resume."}


# ------------------------------------------------------------ gap report

TOOLISH = {"Jira", "Figma", "Excel", "Tableau", "Power BI", "HubSpot", "Salesforce", "QuickBooks", "Google Analytics", "Webpack", "Redux", "Postman"}


def generate_gap_report(job, profile):
    wanted, _ = _wanted(job)
    wanted.pop("__words__", None)
    cand = set(profile.get("skills", []))
    add_if_true, real_gaps = [], []
    for s in sorted(wanted):
        if s in cand:
            continue
        priority = "required" if wanted[s] >= 0.85 else "preferred" if wanted[s] <= 0.4 else "responsibility"
        cluster_mates = next((sorted(m & cand) for m in sk.CLUSTERS.values() if s in m and m & cand), [])
        if s in sk.ADJACENT or s in TOOLISH:
            add_if_true.append({"skill": s, "type": "Adjacent tool or practice", "priority": priority,
                                "advice": "Add this only if you have used it, even in side projects or coursework."})
        else:
            tip = (f"You list {', '.join(cluster_mates[:2])}, which is related. Say so, and be clear you have not used {s} directly."
                   if cluster_mates else f"Do not claim {s}. Prepare an honest answer about how you would learn it.")
            real_gaps.append({"skill": s, "type": "Core prerequisite" if s in sk.DEEP else "Specialized skill",
                              "priority": priority, "advice": tip})
    order = {"required": 0, "responsibility": 1, "preferred": 2}
    add_if_true.sort(key=lambda x: order[x["priority"]])
    real_gaps.sort(key=lambda x: order[x["priority"]])
    return {"job_title": job.get("title"), "company": job.get("company"),
            "matched_skills": sorted(s for s in wanted if s in cand), "add_if_true": add_if_true, "real_gaps": real_gaps,
            "readable_requirements": len(wanted)}


# ------------------------------------------------------------ cover letter

def _first_person(bullet):
    b = bullet.strip().rstrip(".")
    first = b.split(" ", 1)[0].lower()
    if first.endswith("ed") or first in IRREGULAR:
        return b[0].lower() + b[1:]
    return "my work included: " + b[0].lower() + b[1:]


def _best_bullet(job, profile):
    wanted, _ = _wanted(job)
    best, where = None, None
    for e in profile.get("experience", []):
        for b in e.get("bullets", []):
            r = _relevance(b, wanted)
            if best is None or r > best[0]:
                best, where = (r, b), e
    return (best[1], where) if best else (None, None)


TONES = {"direct": ("I am applying for the {title} role at {company}.", "Thank you for your time. I am glad to talk through any of this."),
         "conversational": ("I came across the {title} opening at {company} and wanted to put my name forward.", "Thanks for reading. I would enjoy hearing more about the team."),
         "systems": ("I am writing about the {title} position at {company}.", "I would welcome a technical conversation about the role.")}


def generate_cover_letter(job, profile, tone="direct"):
    tone = tone if tone in TONES else "direct"
    opener, closer = TONES[tone]
    company, title = job.get("company") or "your company", job.get("title") or "open"
    wanted, _ = _wanted(job)
    matched = [s for s in wanted if s != "__words__" and s in set(profile.get("skills", []))]
    yp = _years_phrase(profile)
    role = (profile.get("experience") or [{}])[0].get("role") or profile.get("target_title") or ""
    p1 = opener.format(title=title, company=company)
    if role and yp:
        p1 += f" I am a {role} with {yp} of experience"
        p1 += f" in {', '.join(matched[:3])}." if matched else "."
    bullet, where = _best_bullet(job, profile)
    p2 = ""
    if bullet:
        p2 = f"One example from my work: at {where.get('company')}, {_first_person(bullet)}."
    gaps = [s for s in wanted if s != "__words__" and s not in set(profile.get("skills", [])) and wanted[s] >= 0.85]
    p3 = (f"The posting also names {', '.join(gaps[:2])}. I have not used {'it' if len(gaps[:2]) == 1 else 'them'} professionally, "
          "and I learn new tools quickly.") if gaps else ""
    sign = "\n".join(x for x in [profile.get("name", ""), " | ".join(x for x in [profile.get("email", ""), profile.get("phone", "")] if x)] if x)
    # Self-check the facts from the resume. The gap paragraph names job skills on purpose, so it is exempt.
    core = "\n\n".join(x for x in [p1, p2] if x)
    check = ungrounded(profile, core.replace(title, "").replace(company, ""))
    if check["numbers"] or check["skills"]:
        p1 = re.sub(r"\s*I am a .*", "", p1) if check["skills"] else p1
        p2 = ""
    body = "\n\n".join(x for x in [f"Dear {company} hiring team,", p1, p2, p3, closer,
                                    ("Best regards,\n" + sign) if sign else "Best regards"] if x)
    return body


# ------------------------------------------------------------ interview prep

BEHAVIORAL = [
    (r"lead|mentor|manage|team", "Tell me about a time you helped a teammate improve.", "Pick a mentoring or review example from your resume. State the situation, your action, and the result."),
    (r"deadline|fast|ship|deliver|release", "Describe a time you had to ship under a tight deadline.", "Name what you cut, what you protected, and the outcome."),
    (r"stakeholder|cross|collaborat|product", "Tell me about a disagreement with a colleague and how it ended.", "Lead with facts and data, then the decision."),
    (r"customer|user|client", "Describe a time customer feedback changed your plan.", "Show how you gathered the feedback and what you changed."),
]


def generate_interview_prep(job, profile):
    wanted, text = _wanted(job)
    wanted.pop("__words__", None)
    cand = set(profile.get("skills", []))
    matched = [s for s in wanted if s in cand]
    missing = [s for s in wanted if s not in cand]
    company, title = job.get("company") or "the company", job.get("title") or "this role"
    beh = []
    for pat, q, tip in BEHAVIORAL:
        if re.search(pat, text, re.I) or len(beh) < 2:
            beh.append({"question": q, "tip": tip})
    beh.append({"question": f"Why do you want to work at {company}?", "tip": f"Use something specific from the posting or {company}'s public material. Do not guess."})
    tech = []
    for s in sorted(matched, key=lambda x: -wanted[x])[:4]:
        ev = next((b for e in profile.get("experience", []) for b in e.get("bullets", []) if s in sk.extract(b)), "")
        tech.append({"topic": s, "question": f"Walk me through a problem you solved with {s}.",
                     "talking_point": ("Your resume evidence: " + ev) if ev else f"You list {s}. Prepare one concrete project."})
    gaps = [{"skill": s, "recommended_response": f"I have not used {s} in production. My closest experience is "
             f"{', '.join(sorted(next((m & cand for m in sk.CLUSTERS.values() if s in m and m & cand), set()))[:2]) or 'in nearby tools'}, "
             f"and here is how I would ramp up on {s}."} for s in missing[:3]]
    asks = [f"What does success look like in the first 90 days for a {title}?"]
    if re.search(r"on[\s-]?call|incident|oncall", text, re.I):
        asks.append("How does the on-call rotation work, and how often do incidents page the team?")
    if re.search(r"remote|distributed|async", text, re.I):
        asks.append("How does the team handle time zones and handoffs?")
    asks.append("What is the hardest problem the team is working on right now?")
    return {"role": title, "company": company, "behavioral_questions": beh, "technical_deep_dives": tech,
            "gap_talking_points": gaps, "questions_to_ask_interviewer": asks}
