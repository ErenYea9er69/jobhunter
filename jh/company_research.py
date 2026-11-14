"""Company Research and Learning Pack Engine for Modern Track (Phase B11).

Builds factual company briefs with source URLs on every claim and learning packs (3 questions,
skill gaps with study list, 5 interview talking points, 5-line product summary).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from . import db, lifecycle, skills as sk
from .util import clean_text, now_iso

log = logging.getLogger("jobhunter.company_research")


def verify_signal_liveness(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Verify if a hiring post signal is still live before conducting research."""
    url = signal.get("url") or ""
    if not url:
        return {"is_live": True, "reason": "No URL provided"}

    # Use lifecycle liveness check
    res = lifecycle.liveness_check(url, job_id=signal.get("id"))
    return res


def build_company_brief(signal: Dict[str, Any], profile: Dict[str, Any], source_text: str = "") -> Dict[str, Any]:
    """Build a factual company brief where every claim cites a source URL or is marked 'unknown'."""
    company = signal.get("company") or "Unknown Company"
    source_url = signal.get("url") or "unknown"
    sig_text = source_text or signal.get("text") or ""
    sig_type = signal.get("type", "hiring_post")

    # 1. Product / What company does
    # Extract description from signal text
    summary = "unknown"
    if sig_text:
        first_few = ". ".join(sig_text.split(".")[:2]).strip()
        if len(first_few) > 20:
            summary = first_few

    # 2. Stage
    stage = signal.get("stage") or "unknown"
    if stage == "any":
        stage = "unknown"

    # 3. Funding
    funding_amt = signal.get("funding_amount") or "unknown"
    funding_round = signal.get("funding_round") or "unknown"
    funding_investors = "unknown"

    # Match investors e.g. "led by Sequoia" or "backed by Founders Fund"
    inv_match = re.search(r"(?:led by|backed by|from)\s+([A-Za-z0-9\s,&]+?)(?:\.|\n|$)", sig_text, re.IGNORECASE)
    if inv_match:
        funding_investors = inv_match.group(1).strip()

    # 4. Team
    team_size = "unknown"
    team_match = re.search(r"\b([0-9]{1,4})\s*(?:people|employees|team members|engineers)\b", sig_text, re.IGNORECASE)
    if team_match:
        team_size = team_match.group(1)

    # 5. Recent News
    recent_news = "unknown"
    if sig_type == "funding" and funding_amt != "unknown":
        recent_news = f"Announced {funding_round} funding of {funding_amt}"
    elif "launch" in sig_text.lower():
        recent_news = "Recent product launch announced in hiring update"

    # 6. Where candidate helps
    cand_skills = profile.get("skills") or []
    wanted_skills = sk.extract(sig_text) if sig_text else []
    overlap = [s for s in wanted_skills if any(s.lower() == cs.lower() for cs in cand_skills)]

    if overlap:
        candidate_value = f"Strong alignment in {', '.join(overlap[:3])} to accelerate core technical roadmap."
    elif cand_skills:
        candidate_value = f"Core expertise in {', '.join(cand_skills[:3])} matching target role requirements."
    else:
        candidate_value = "Technical leadership and engineering execution."

    brief = {
        "company": company,
        "product_summary": {"claim": summary, "source_url": source_url if summary != "unknown" else "unknown"},
        "stage": {"claim": stage, "source_url": source_url if stage != "unknown" else "unknown"},
        "funding": {
            "amount": funding_amt,
            "round": funding_round,
            "investors": funding_investors,
            "source_url": source_url if funding_amt != "unknown" or funding_investors != "unknown" else "unknown",
        },
        "team": {
            "size": team_size,
            "key_person": signal.get("author_name") or "unknown",
            "source_url": source_url if team_size != "unknown" or signal.get("author_name") else "unknown",
        },
        "recent_news": {"claim": recent_news, "source_url": source_url if recent_news != "unknown" else "unknown"},
        "candidate_impact": candidate_value,
        "researched_at": now_iso(),
    }
    return brief


def build_learning_pack(brief: Dict[str, Any], signal: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Build the learning pack:
    - 3 smart questions to ask the company
    - Skill gaps with a short study list
    - 5 interview talking points
    - 5-line product summary to read before calls
    """
    company = brief.get("company", "the team")
    sig_text = signal.get("text") or ""
    cand_skills = {s.lower() for s in (profile.get("skills") or [])}
    wanted = sk.extract(sig_text) if sig_text else []
    missing_skills = [w for w in wanted if w.lower() not in cand_skills]

    # 1. 3 Smart Questions
    questions = [
        f"What is the single biggest engineering bottleneck currently slowing down {company}'s roadmap?",
        f"How does the engineering team balance rapid product iteration with infrastructure reliability at this stage?",
        f"What would success look like for this role in the first 90 days of joining?",
    ]

    # 2. Skill Gaps & Study List
    study_list = []
    for m in missing_skills[:4]:
        study_list.append({
            "skill": m,
            "resource": f"Official documentation and production architecture guides for {m}",
            "talking_angle": f"Demonstrate deep fundamentals and rapid transferability from known stack to {m}.",
        })

    # 3. 5 Interview Talking Points
    exps = profile.get("experience") or []
    talking_points = []
    for exp in exps:
        for b in exp.get("bullets", []):
            if b.strip() and len(talking_points) < 5:
                talking_points.append(b.strip())

    # Fallback talking points if experience bullets are few
    if len(talking_points) < 5:
        proof_points = profile.get("proof_points") or []
        for pp in proof_points:
            if isinstance(pp, dict) and pp.get("metric"):
                talking_points.append(f"{pp.get('project')}: {pp.get('metric')}")
            elif isinstance(pp, str):
                talking_points.append(pp)

    while len(talking_points) < 5:
        talking_points.append(f"Hands-on execution with {', '.join(profile.get('skills', ['modern engineering'])[:3])}.")

    # 4. 5-line Product Summary
    prod_claim = brief.get("product_summary", {}).get("claim", f"{company} technology platform")
    product_summary = [
        f"1. Company: {company} ({brief.get('stage', {}).get('claim', 'Early stage')})",
        f"2. Core offering: {prod_claim[:100]}",
        f"3. Target audience: Developers, businesses, and technical operators",
        f"4. Competitive edge: High performance, seamless developer ergonomics, and rapid deployment",
        f"5. Key talking hook: Direct alignment with our core engineering execution standards",
    ]

    return {
        "questions": questions[:3],
        "skill_gaps": missing_skills[:4],
        "study_list": study_list,
        "talking_points": talking_points[:5],
        "product_summary": product_summary,
        "built_at": now_iso(),
    }


def research_saved_signal(signal_or_id: str | Dict[str, Any]) -> Dict[str, Any]:
    """Execute background research and learning pack generation on a saved signal."""
    if isinstance(signal_or_id, dict):
        signal = signal_or_id
    else:
        signal = db.get_signal(str(signal_or_id))
        if not signal:
            return {"status": "error", "message": f"Signal '{signal_or_id}' not found."}

    # Verify post liveness for hiring posts
    if signal.get("type") == "hiring_post" and signal.get("url"):
        liveness = verify_signal_liveness(signal)
        if not liveness.get("is_live"):
            return {
                "status": "closed",
                "message": f"Posting closed ({liveness.get('reason')}). Research skipped.",
                "signal_id": signal.get("id"),
            }

    profile = db.get_profile()
    brief = build_company_brief(signal, profile)
    learning_pack = build_learning_pack(brief, signal, profile)

    company = signal.get("company") or "Unknown Company"
    saved = db.save_company_brief(
        company=company,
        brief_data=brief,
        learning_pack_data=learning_pack,
        signal_id=signal.get("id", ""),
        domain=signal.get("company_domain", ""),
        stage=brief.get("stage", {}).get("claim", ""),
        funding_summary=brief.get("funding", {}).get("amount", ""),
    )

    # Mark signal as saved in DB
    db.update_signal_status(signal.get("id", ""), "saved")

    return {
        "status": "ok",
        "brief_id": saved.get("id"),
        "company": company,
        "brief": brief,
        "learning_pack": learning_pack,
    }
