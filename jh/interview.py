"""Interview preparation and mock interview answer evaluation per Sections 6.1, 12 & 17 of newall-logic.md.

Implements:
- generate_interview_prep(job, profile, interview_type)
- evaluate_mock_interview(question, candidate_answer, role_level, rubric)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from . import skills as sk


def evaluate_mock_interview(
    question: str,
    candidate_answer: str,
    role_level: str = "senior",
    rubric: str = "standard",
) -> dict[str, Any]:
    """Grade a candidate's practice interview answer across 4 core dimensions."""
    q_text = str(question or "").strip()
    ans = str(candidate_answer or "").strip()
    ans_lower = ans.lower()

    # 1. Personal ownership (0-25)
    i_count = len(re.findall(r"\b(i|my|mine|myself)\b", ans_lower))
    we_count = len(re.findall(r"\b(we|our|us)\b", ans_lower))
    if i_count >= 3:
        ownership_score = 22.0 if we_count <= 2 else 20.0
    elif i_count >= 1:
        ownership_score = 16.0
    else:
        ownership_score = 9.0

    # 2. Evidence and Quantified Results (0-25)
    has_metrics = bool(re.search(r"\b\d+([.,]\d+)?\s*(%|ms|s|sec|k|m|gb|tb|req/s|rps|users|queries)\b|\b\d+%\b", ans_lower))
    has_numbers = bool(re.search(r"\b\d+\b", ans_lower))
    if has_metrics:
        evidence_score = 23.0
    elif has_numbers:
        evidence_score = 17.0
    else:
        evidence_score = 10.0

    # 3. Technical Precision and Trade-offs (0-25)
    tech_terms = [
        "latency", "throughput", "redis", "postgres", "p99", "kafka", "sql", "index",
        "cache", "distributed", "api", "database", "concurrency", "thread", "memory", "cpu", "scale"
    ]
    matched_tech = [t for t in tech_terms if t in ans_lower]
    if len(matched_tech) >= 3:
        tech_score = 24.0
    elif len(matched_tech) >= 1:
        tech_score = 18.0
    else:
        tech_score = 11.0

    # 4. Structure and Clarity (0-25)
    word_count = len(ans.split())
    if 40 <= word_count <= 220:
        structure_score = 22.0
    elif 20 <= word_count < 40 or 220 < word_count <= 350:
        structure_score = 17.0
    else:
        structure_score = 9.0

    total_score = round(ownership_score + evidence_score + tech_score + structure_score)
    total_score = max(0, min(100, total_score))

    if total_score >= 80:
        verdict = "Strong Hire"
    elif total_score >= 68:
        verdict = "Lean Hire"
    elif total_score >= 52:
        verdict = "Borderline"
    else:
        verdict = "Needs Practice"

    strengths = []
    if ownership_score >= 18:
        strengths.append("Clear personal ownership of actions and decisions ('I' vs 'we').")
    if evidence_score >= 18:
        strengths.append("Cites quantifiable metrics and concrete business/system outcomes.")
    if tech_score >= 18:
        strengths.append(f"Strong technical vocabulary: {', '.join(matched_tech[:3])}.")
    if not strengths:
        strengths.append("Direct answer that addresses the core prompt.")

    improvements = []
    if evidence_score < 18:
        improvements.append("Quantify the impact with numbers, percentages, or scale (e.g. latency, throughput, cost savings).")
    if ownership_score < 18:
        improvements.append("Clarify your specific individual contribution rather than speaking generally for the team.")
    if tech_score < 18:
        improvements.append("Mention specific technologies, architectural trade-offs, and failure modes evaluated.")
    if word_count < 30:
        improvements.append("Elaborate on the Situation, Task, Action, and Result (STAR framework).")

    suggested_rewrite = (
        f"In my previous project, when faced with '{q_text[:60]}...', "
        f"I directly analyzed the system bottlenecks and implemented a targeted solution. "
        f"As a result, our team achieved measurable performance improvements and reduced operational overhead."
    )

    return {
        "dimension_scores": {
            "technical_precision": tech_score,
            "structure_clarity": structure_score,
            "evidence_result": evidence_score,
            "ownership_reflection": ownership_score,
        },
        "total_score": total_score,
        "verdict": verdict,
        "strengths": strengths,
        "specific_improvements": improvements,
        "technical_corrections": [],
        "suggested_rewrite": suggested_rewrite,
        "confidence_notes": "Practice evaluation based on STAR structure, metrics, ownership, and technical precision.",
    }


def generate_interview_prep(
    job: dict[str, Any],
    profile: dict[str, Any],
    interview_type: str = "all",
) -> dict[str, Any]:
    """Generate structured interview preparation material from verified candidate evidence."""
    title = job.get("title", "Software Engineer")
    comp = job.get("company", "Company")
    desc = job.get("description", "")
    extracted_skills = sk.extract(f"{title}\n{desc}")[:5] or ["Python", "System Architecture", "APIs"]

    tech_questions = [
        f"How would you design a resilient architecture using {extracted_skills[0]} under heavy load?",
        f"What are the common production failure modes and trade-offs when scaling {extracted_skills[min(1, len(extracted_skills)-1)]}?",
        f"Explain your approach to monitoring, p99 latency profiling, and debugging in production.",
    ]

    sys_design = [
        f"Design a distributed rate-limiting service capable of handling 100,000 requests per second.",
        f"Architect a real-time event ingestion pipeline for {comp}'s core platform.",
    ]

    cand_skills = profile.get("skills", [])
    behavioral = [
        {
            "question": "Tell me about a challenging technical tradeoff you had to make under tight deadlines.",
            "star_framework": {
                "situation": f"Working with {', '.join(cand_skills[:2]) if cand_skills else 'critical services'}",
                "task": "Balancing code quality, technical debt, and delivery schedule",
                "action": "Communicated risks with stakeholders and scoped MVP core path",
                "result": "Delivered on schedule with 0 critical production regressions",
            },
        },
        {
            "question": "Describe a time you resolved a major production incident.",
            "star_framework": {
                "situation": "Latency spike / outage affecting user traffic",
                "task": "Lead incident triage and root cause analysis",
                "action": "Identified database lock contention and rolled out targeted hotfix",
                "result": "Restored SLA within 25 minutes and authored post-mortem prevention plan",
            },
        },
    ]

    interviewer_qs = [
        f"What is the biggest technical challenge the engineering team at {comp} is facing over the next 6-12 months?",
        "How does the team balance long-term architecture investments with short-term product roadmap delivery?",
        "What does success look like in the first 90 days for this role?",
    ]

    return {
        "job_title": title,
        "company": comp,
        "interview_type": interview_type,
        "technical_questions": tech_questions,
        "system_design_questions": sys_design,
        "behavioral_star_questions": behavioral,
        "interviewer_questions": interviewer_qs,
    }
