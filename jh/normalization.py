"""Canonical JobPosting normalization per Section 8 (Stage 3) of newall-logic.md.

Standardizes dates, currencies, employment types, seniority labels, location fields,
and work-mode values while preserving separate source URL and application URL.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .util import (
    clean_job_type,
    clean_salary_label,
    clean_text,
    extract_job_sections,
    html_to_text,
    iso_or_empty,
    parse_salary,
)


def standardize_work_mode(text: str) -> str:
    """Normalize work mode string into canonical Remote | Hybrid | On-site | empty."""
    blob = str(text or "").strip().lower()
    if not blob:
        return ""
    if re.search(r"\bremote\b|anywhere|worldwide|work from home|telecommute|wfh", blob):
        return "Remote"
    if re.search(r"\bhybrid\b|partially remote|flexible office", blob):
        return "Hybrid"
    if re.search(r"\bon-site\b|\bonsite\b|in-office|office based|in person", blob):
        return "On-site"
    return ""


def standardize_employment_type(text: str) -> str:
    """Normalize employment type string into canonical label."""
    blob = str(text or "").strip().lower()
    if not blob:
        return ""
    if re.search(r"\b(contract|contractor|freelance|c2c|temp|temporary)\b", blob):
        return "Contract"
    if re.search(r"\b(intern|internship|stage|co-op)\b", blob):
        return "Internship"
    if re.search(r"\b(part[-\s]time)\b", blob):
        return "Part-time"
    if re.search(r"\b(full[-\s]time|permanent|direct hire|regular)\b", blob):
        return "Full-time"
    cleaned = clean_job_type(blob)
    return cleaned or "Full-time"


def standardize_seniority(title: str, text: str = "") -> str:
    """Extract canonical seniority level from title and description."""
    blob = f"{title} {text[:500]}".lower()
    if re.search(r"\b(distinguished|fellow|principal)\b", blob):
        return "Principal"
    if re.search(r"\b(staff|lead|architect)\b", blob):
        return "Staff"
    if re.search(r"\b(senior|sr\.?|lead)\b", blob):
        return "Senior"
    if re.search(r"\b(entry|junior|jr\.?|associate|graduate)\b", blob):
        return "Junior"
    if re.search(r"\b(mid|intermediate)\b", blob):
        return "Mid"
    return "Mid"


def build_canonical_posting(raw_data: dict[str, Any], source_name: str = "") -> dict[str, Any]:
    """Convert raw source post into a canonical JobPosting dictionary."""
    title = clean_text(raw_data.get("title") or "")
    company = clean_text(raw_data.get("company") or raw_data.get("company_name") or "")
    loc = clean_text(raw_data.get("location") or "")
    raw_desc = raw_data.get("description") or raw_data.get("text") or ""
    desc = html_to_text(raw_desc, 15000)

    # Work mode
    mode = standardize_work_mode(raw_data.get("work_mode") or "")
    if not mode:
        combined = f"{title} {loc} {desc[:1000]}"
        mode = standardize_work_mode(combined)
        if not mode and loc:
            mode = "On-site"

    # Separate URLs
    source_url = clean_text(raw_data.get("source_url") or raw_data.get("url") or raw_data.get("link") or "")
    apply_url = clean_text(
        raw_data.get("apply_url")
        or raw_data.get("applicationLink")
        or raw_data.get("application_url")
        or source_url
    )

    # Salary parsing
    sal_raw = raw_data.get("salary") or raw_data.get("salary_text") or ""
    sal_label = clean_salary_label(sal_raw)
    parsed_sal = parse_salary(sal_label or sal_raw)

    salary_min = None
    salary_max = None
    salary_currency = ""
    if parsed_sal:
        salary_min = parsed_sal.get("min")
        salary_max = parsed_sal.get("max")
        salary_currency = parsed_sal.get("currency") or ""

    # Job type / employment type
    job_type = standardize_employment_type(raw_data.get("job_type") or raw_data.get("employment_type") or "")
    seniority = standardize_seniority(title, desc)

    posted_at = iso_or_empty(raw_data.get("posted_at") or raw_data.get("published_at") or raw_data.get("date") or "")

    canonical_id = raw_data.get("id") or f"{clean_text(source_name).lower()}-{abs(hash(source_url or title))}"

    return {
        "id": canonical_id,
        "title": title,
        "company": company,
        "location": loc,
        "work_mode": mode,
        "description": desc,
        "source": source_name or raw_data.get("source", "Unknown"),
        "source_url": source_url,
        "apply_url": apply_url,
        "salary": sal_label,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "employment_type": job_type,
        "seniority": seniority,
        "posted_at": posted_at,
        "is_closed": bool(raw_data.get("is_closed", False)),
        "source_data": raw_data,
    }
