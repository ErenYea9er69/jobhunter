"""Big Tech Recruiter Outreach & Employee Referral Engine.

Specialized playbooks, leveling translations, and high-converting reachout templates
for top tech companies: Google, Meta, Uber, Amazon, Apple, Microsoft, Netflix, Stripe.

Produces:
1. Recruiter InMail (triage-optimized with Req ID, leveling match, and quantifiable scope)
2. Internal Employee Referral Blurb (formatted for 1-click copy-paste into internal referral portals)
3. Verified Recruiter Email pattern with Gmail compose integration
"""

from __future__ import annotations

import logging
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from . import email_finder, skills as sk
from .team import qa
from .util import clean_text

log = logging.getLogger("jobhunter.bigtech")
if not log.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [bigtech] %(levelname)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


BIGTECH_COMPANIES: Dict[str, Dict[str, Any]] = {
    "google": {
        "name": "Google",
        "domain": "google.com",
        "career_portal": "https://www.google.com/about/careers/applications/jobs/results/",
        "levels": {"junior": "L3", "mid": "L4", "senior": "L5", "staff": "L6"},
        "rubric_focus": "System Design, Algorithms, and high-concurrency distributed systems",
        "referral_portal_name": "Google Internal Referral System",
    },
    "meta": {
        "name": "Meta",
        "domain": "meta.com",
        "career_portal": "https://www.metacareers.com/jobs",
        "levels": {"junior": "E3", "mid": "E4", "senior": "E5", "staff": "E6"},
        "rubric_focus": "Rapid product execution, end-to-end architecture ownership, and scale",
        "referral_portal_name": "Meta M-Refer Portal",
    },
    "uber": {
        "name": "Uber",
        "domain": "uber.com",
        "career_portal": "https://www.uber.com/us/en/careers/list/",
        "levels": {"junior": "L3 / Software Engineer I", "mid": "L4 / Software Engineer II", "senior": "L5 / Senior Software Engineer", "staff": "L6 / Staff Engineer"},
        "rubric_focus": "Real-time dispatch pipelines, geospatial routing, and low-latency microservices",
        "referral_portal_name": "Uber Employee Referral Hub",
    },
    "amazon": {
        "name": "Amazon",
        "domain": "amazon.com",
        "career_portal": "https://www.amazon.jobs/en/",
        "levels": {"junior": "SDE I (L4)", "mid": "SDE II (L5)", "senior": "SDE III (L6)", "staff": "Principal SDE (L7)"},
        "rubric_focus": "Customer Obsession, Ownership, and distributed cloud primitives (AWS)",
        "referral_portal_name": "Amazon Global Referral Portal",
    },
    "apple": {
        "name": "Apple",
        "domain": "apple.com",
        "career_portal": "https://jobs.apple.com/en-us/search",
        "levels": {"junior": "ICT2", "mid": "ICT3", "senior": "ICT4", "staff": "ICT5"},
        "rubric_focus": "High craftsmanship, systems-level memory safety, and seamless hardware-software integration",
        "referral_portal_name": "Apple Internal Referrals",
    },
    "microsoft": {
        "name": "Microsoft",
        "domain": "microsoft.com",
        "career_portal": "https://careers.microsoft.com/v2/global/en/home.html",
        "levels": {"junior": "Level 59-60", "mid": "Level 61-62", "senior": "Level 63-64", "staff": "Principal (Level 65+)"},
        "rubric_focus": "Enterprise scalability, Azure cloud primitives, and developer tooling",
        "referral_portal_name": "Microsoft Employee Referral Network",
    },
    "netflix": {
        "name": "Netflix",
        "domain": "netflix.com",
        "career_portal": "https://jobs.netflix.com/search",
        "levels": {"junior": "L4", "mid": "Senior IC", "senior": "Senior Software Engineer", "staff": "Staff / Principal"},
        "rubric_focus": "Freedom & Responsibility, extreme autonomy, and fault-tolerant streaming infra",
        "referral_portal_name": "Netflix Referral System",
    },
    "stripe": {
        "name": "Stripe",
        "domain": "stripe.com",
        "career_portal": "https://stripe.com/jobs/search",
        "levels": {"junior": "L2", "mid": "L3", "senior": "L4", "staff": "L5"},
        "rubric_focus": "API ergonomics, 99.999% payment infrastructure reliability, and developer experience",
        "referral_portal_name": "Stripe Internal Referral Hub",
    },
}


def list_bigtech_companies() -> List[Dict[str, Any]]:
    """Return catalog of supported big tech organizations with leveling maps."""
    return [
        {
            "id": key,
            "name": val["name"],
            "domain": val["domain"],
            "career_portal": val["career_portal"],
            "levels": val["levels"],
            "rubric_focus": val["rubric_focus"],
            "referral_portal_name": val["referral_portal_name"],
        }
        for key, val in BIGTECH_COMPANIES.items()
    ]


def _extract_top_bullet(profile: Dict[str, Any], wanted_skills: List[str]) -> str:
    """Select candidate's top achievement bullet grounded in profile ledger."""
    exps = profile.get("experience", [])
    if not exps:
        return ""
    all_bullets = []
    for exp in exps:
        for b in exp.get("bullets", []):
            if b.strip():
                all_bullets.append(b.strip())
    if not all_bullets:
        return ""

    wanted_set = {w.lower() for w in wanted_skills}
    for b in all_bullets:
        if any(w in b.lower() for w in wanted_set):
            return b
    return all_bullets[0]


def generate_bigtech_outreach(
    company_key: str,
    job: Dict[str, Any],
    profile: Dict[str, Any],
    recruiter_name: str = "",
    req_id: str = "",
    leveling_tier: str = "mid",
) -> Dict[str, Any]:
    """Generate high-converting recruiter InMail and internal referral blurb for big tech."""
    comp_info = BIGTECH_COMPANIES.get(company_key.lower()) or {
        "name": company_key.capitalize(),
        "domain": f"{company_key.lower()}.com",
        "career_portal": f"https://{company_key.lower()}.com/careers",
        "levels": {"mid": "Software Engineer II"},
        "rubric_focus": "Scalable systems and engineering excellence",
        "referral_portal_name": "Internal Referral Portal",
    }

    comp_name = comp_info["name"]
    comp_domain = comp_info["domain"]
    level_label = comp_info["levels"].get(leveling_tier.lower(), comp_info["levels"].get("mid", "Software Engineer"))
    req_display = f" [Req: {req_id.strip()}]" if req_id.strip() else ""

    cand_name = profile.get("name") or "Candidate"
    first_name_cand = cand_name.split()[0] if cand_name else "Candidate"
    cand_title = profile.get("target_title") or "Software Engineer"
    cand_skills = profile.get("skills", [])

    desc = job.get("description", "")
    wanted = sk.extract(desc) if desc else []
    matched = [s for s in wanted if s in cand_skills]
    key_skill = matched[0] if matched else (cand_skills[0] if cand_skills else "distributed systems")
    second_skill = matched[1] if len(matched) > 1 else (cand_skills[1] if len(cand_skills) > 1 else "Python")

    top_bullet = _extract_top_bullet(profile, matched or cand_skills[:3])
    if len(top_bullet) > 110:
        top_bullet = top_bullet[:105].rsplit(" ", 1)[0] + "..."

    recruiter_fname = recruiter_name.strip().split()[0] if recruiter_name.strip() else ""
    recruiter_greeting = f"Hi {recruiter_fname}," if recruiter_fname else "Hi,"

    # 1. Recruiter InMail (Triage & Screening Optimized)
    inmail_subject = f"{cand_title} ({level_label}) - {cand_name}{req_display}"
    inmail_lines = [
        recruiter_greeting,
        f"Reaching out regarding the {cand_title} opening at {comp_name}{req_display}. I wanted to share my background directly as you review candidate profiles for the team.",
        "Key qualifications from my work:",
        f"- Core stack: {key_skill}, {second_skill}, and REST APIs.",
        f"- Proven ownership: {top_bullet}",
        "- Track record delivering full-stack features autonomously end-to-end.",
        "I have reviewed the role requirements and would love to schedule a brief call next week to discuss team alignment.",
        f"Best,\n{cand_name}\n{profile.get('email', '')} | {profile.get('github', '')}",
    ]
    inmail_body = "\n\n".join([inmail_lines[0], inmail_lines[1], "\n".join(inmail_lines[2:6]), inmail_lines[6], inmail_lines[7]])

    # 2. Internal Employee Referral Blurb (Formatted for 1-Click Submission)
    referral_blurb_lines = [
        f"Candidate: {cand_name}",
        f"Target Role: {cand_title} ({level_label}){req_display}",
        f"Portfolio / GitHub: {profile.get('github') or profile.get('linkedin') or 'Available on resume'}",
        f"Email: {profile.get('email', '')}",
        "",
        "Why this candidate is a strong hire:",
        f"- Strong technical foundation in {key_skill} and {second_skill}.",
        f"- Proven impact: {top_bullet}",
        "- High autonomy: builds and deploys end-to-end systems without management friction.",
    ]
    referral_blurb = "\n".join(referral_blurb_lines)

    # 3. Recruiter Email Prediction
    email_data = {}
    if recruiter_name:
        email_data = email_finder.find_corporate_email(
            name=recruiter_name,
            company=comp_name,
            domain=comp_domain,
            role="Technical Recruiter",
        )
    else:
        email_data = email_finder.find_corporate_email(
            name="University Talent",
            company=comp_name,
            domain=comp_domain,
            role="Technical Recruiter",
        )

    # 4. Reviewer QA Checks
    rev_inmail = qa.review_document(inmail_body, kind="outreach", profile=profile, job=job)
    rev_referral = qa.review_document(referral_blurb, kind="outreach", profile=profile, job=job)

    # Gmail compose link
    quoted_sub = urllib.parse.quote(inmail_subject)
    quoted_body = urllib.parse.quote(inmail_body)
    to_email = email_data.get("primary_email", "")
    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_email}&su={quoted_sub}&body={quoted_body}"

    return {
        "company": comp_name,
        "company_domain": comp_domain,
        "level_label": level_label,
        "req_id": req_id,
        "rubric_focus": comp_info["rubric_focus"],
        "referral_portal_name": comp_info["referral_portal_name"],
        "inmail_subject": inmail_subject,
        "inmail_body": inmail_body,
        "inmail_word_count": len(inmail_body.split()),
        "referral_blurb": referral_blurb,
        "recruiter_email": email_data.get("primary_email", ""),
        "recruiter_email_confidence": email_data.get("confidence_pct", 85),
        "mail_provider": email_data.get("mail_provider", "Corporate Mail"),
        "gmail_compose_url": gmail_url,
        "review_inmail": {
            "verdict": rev_inmail.verdict,
            "findings": rev_inmail.findings,
        },
        "review_referral": {
            "verdict": rev_referral.verdict,
            "findings": rev_referral.findings,
        },
    }
