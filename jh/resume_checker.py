"""Local Resume Checker & Document Classifier for JobHunter V3.

Validates resumes locally without network access.
Detects document kind (resume, cover_letter, job_description, other),
enforces hard failure gates (< 300 chars, unsupported format, non-resume),
and produces explainable soft warnings (outdated dates, name changes, garbled text).
"""
from __future__ import annotations

import datetime
import os
import re
from pathlib import Path
from typing import Any, Optional

from . import resume_parser, skills as sk

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

# Section header patterns (match headers at line start or followed by colon/newline)
SECTION_PATTERNS = {
    "experience": re.compile(r"(?:^|\n)\s*(?:work\s+experience|professional\s+experience|work\s+history|employment|experience|career|parcours|expériences?\s+professionnelles?)\s*[:\n]", re.I),
    "education": re.compile(r"(?:^|\n)\s*(?:education|formation|academic\s+background|degrees?|diplômes?|études?|qualifications?)\s*[:\n]", re.I),
    "projects": re.compile(r"(?:^|\n)\s*(?:projects?|projets?|personal\s+projects|key\s+projects|academic\s+projects)\s*[:\n]", re.I),
    "skills": re.compile(r"(?:^|\n)\s*(?:skills|compétences|technical\s+skills|technologies|expertise|stack|tools|connaissances?)\s*[:\n]", re.I),
}

# Cover letter signatures / salutations
COVER_LETTER_GREETINGS = re.compile(r"\b(dear (hiring manager|recruiter|selection committee|team|mr|mrs|ms)|to whom it may concern|madame, monsieur|messieurs)\b", re.I)
COVER_LETTER_CLOSINGS = re.compile(r"\b(sincerely|best regards|warm regards|cordially|respectfully|yours truly|cordialement|bien cordialement|je vous prie d'agréer)\b", re.I)

# Job description indicators
JOB_DESC_PHRASES = re.compile(r"\b(we are looking for|responsibilities|job responsibilities|key responsibilities|requirements|job requirements|what you'll do|who you are|about the role|apply now|submit your application|candidate profile|qualifications required)\b", re.I)


def extract_raw_text(path_or_text: str | Path) -> tuple[str, str, Optional[str]]:
    """Extract text and filename from path or direct raw text.
    
    Returns (text, filename, error_str).
    """
    if isinstance(path_or_text, Path) or (isinstance(path_or_text, str) and ("\n" not in path_or_text and (os.path.exists(path_or_text) or path_or_text.endswith(tuple(SUPPORTED_EXTENSIONS))))):
        p = Path(path_or_text)
        if not p.exists():
            return "", p.name, f"File does not exist: '{p}'"
        ext = p.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return "", p.name, f"Unsupported file type '{ext}'. Supported types: PDF, DOCX, TXT, MD."
        try:
            raw_bytes = p.read_bytes()
            if ext == ".md":
                text = raw_bytes.decode("utf-8", errors="replace")
            else:
                text = resume_parser.extract_text(p.name, raw_bytes)
            return text, p.name, None
        except Exception as e:
            return "", p.name, f"Unreadable file '{p.name}': {str(e)}"
    
    # Otherwise treat as raw text
    text = str(path_or_text or "")
    return text, "pasted_resume.txt", None


def detect_document_kind(text: str, sections_found: list[str]) -> str:
    """Classifies document as resume, cover_letter, job_description, or other."""
    t_lower = text.lower()
    
    # 1. Check Job Description
    jd_matches = len(JOB_DESC_PHRASES.findall(t_lower))
    if jd_matches >= 2 and ("experience" not in sections_found and "education" not in sections_found):
        return "job_description"
    
    # 2. Check Cover Letter
    has_greeting = bool(COVER_LETTER_GREETINGS.search(t_lower[:500]))
    has_closing = bool(COVER_LETTER_CLOSINGS.search(t_lower[-500:]))
    if (has_greeting or has_closing) and len(sections_found) <= 1:
        return "cover_letter"
    
    # 3. Check Resume
    if len(sections_found) >= 2:
        return "resume"
    
    if any(s in sections_found for s in ("experience", "education", "skills")):
        return "resume"
        
    return "other"


def find_sections(text: str) -> list[str]:
    """Identify present resume sections."""
    found = []
    for s_name, pattern in SECTION_PATTERNS.items():
        if pattern.search(text):
            found.append(s_name)
    return found


def extract_skills_local(text: str) -> list[str]:
    """Find recognizable technical skills locally."""
    return sk.extract(text)


def extract_contact_info(text: str) -> dict[str, Any]:
    """Extract email, phone, and links."""
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phones = re.findall(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}", text)
    has_contact = bool(emails or phones)
    return {
        "email": emails[0] if emails else "",
        "phone": phones[0] if phones else "",
        "has_contact": has_contact,
    }


def find_latest_date_in_history(text: str) -> Optional[datetime.date]:
    """Find the most recent year/month mentioned in the experience section."""
    current_year = datetime.date.today().year
    # Find 4-digit years between 1990 and current_year + 2
    years = [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", text)]
    valid_years = [y for y in years if 1990 <= y <= current_year + 2]
    if not valid_years:
        return None
    latest_year = max(valid_years)
    return datetime.date(latest_year, 1, 1)


def check_resume(
    path_or_text: str | Path | None = None,
    saved_profile: Optional[dict[str, Any]] = None,
    resume_text: str = "",
    filename: str = "",
    text: str = "",
) -> dict[str, Any]:
    """Run thorough local inspection on a candidate resume document.
    
    Enforces Phase B2 Hard Failures & Soft Warnings.
    """
    issues: list[str] = []
    warnings: list[str] = []

    if text and not resume_text:
        resume_text = text

    if resume_text and resume_text.strip():
        text = resume_text.strip()
        fname = filename or (Path(path_or_text).name if isinstance(path_or_text, (str, Path)) and path_or_text else "pasted_resume.txt")
        filename = fname
        err = None
    elif not path_or_text:
        return {
            "ok": False,
            "kind": "other",
            "issues": ["No resume file path or text was provided. Please provide a path to your PDF, DOCX, TXT, or MD resume, or paste the text."],
            "warnings": [],
            "text_chars": 0,
            "sections_found": [],
            "contact_found": False,
            "name": "",
            "latest_date": None,
            "skills_count": 0,
            "confidence": 0.0,
            "profile": {},
        }
    else:
        text, filename, err = extract_raw_text(path_or_text)
    if err:
        return {
            "ok": False,
            "kind": "other",
            "issues": [err],
            "warnings": [],
            "text_chars": 0,
            "sections_found": [],
            "contact_found": False,
            "name": "",
            "latest_date": None,
            "skills_count": 0,
            "confidence": 0.0,
            "profile": {},
        }

    text_chars = len(text.strip())
    
    # Try OCR fallback for scanned PDF if installed
    if text_chars < 300 and filename.lower().endswith(".pdf") and isinstance(path_or_text, (str, Path)) and os.path.isfile(str(path_or_text)):
        try:
            import pdf2image
            import pytesseract
            images = pdf2image.convert_from_path(str(path_or_text), first_page=1, last_page=3)
            ocr_text = "\n".join(pytesseract.image_to_string(img) for img in images).strip()
            if len(ocr_text) >= 300:
                text = ocr_text
                text_chars = len(text.strip())
        except Exception:
            pass

    # Hard failure 2: Extracted text holds under 300 characters
    if text_chars < 300:
        msg = f"Extracted text holds under 300 characters (found only {text_chars} characters)."
        if filename.lower().endswith(".pdf"):
            msg += " If this is a scanned PDF with no text layer, please provide a text-based PDF or paste your resume text."
        issues.append(msg)
        return {
            "ok": False,
            "kind": "other",
            "issues": issues,
            "warnings": [],
            "text_chars": text_chars,
            "sections_found": [],
            "contact_found": False,
            "name": "",
            "latest_date": None,
            "skills_count": 0,
            "confidence": 0.0,
            "profile": {},
        }

    sections_found = find_sections(text)
    kind = detect_document_kind(text, sections_found)
    
    # Hard failure 3: Document kind is not resume
    if kind == "cover_letter":
        issues.append("The provided document is a cover letter (contains greeting/closing but no structured experience or education sections). Please attach your complete resume.")
    elif kind == "job_description":
        issues.append("The provided document appears to be a job description ('we are looking for', 'requirements'), not a candidate resume.")
    elif kind == "other":
        issues.append("The document does not appear to be a resume (missing standard sections like experience, education, or skills).")

    # Extract skills and contacts
    skills_found = extract_skills_local(text)
    contact = extract_contact_info(text)
    
    # Hard failure 4: Fewer than 3 skills AND fewer than 2 resume sections
    if len(skills_found) < 3 and len(sections_found) < 2:
        issues.append(f"Insufficient resume structure: found only {len(skills_found)} skill(s) and {len(sections_found)} standard section(s). Expected at least 3 skills or 2 sections.")

    if issues:
        return {
            "ok": False,
            "kind": kind,
            "issues": issues,
            "warnings": warnings,
            "text_chars": text_chars,
            "sections_found": sections_found,
            "contact_found": contact["has_contact"],
            "name": "",
            "latest_date": None,
            "skills_count": len(skills_found),
            "confidence": 0.0,
            "profile": {},
        }

    # If hard checks passed, run full parser for profile extraction
    try:
        profile, _report = resume_parser.parse_resume(text)
    except Exception:
        profile = {"raw_text": text, "skills": skills_found}

    if not profile.get("skills"):
        profile["skills"] = skills_found

    candidate_name = profile.get("name") or ""
    if not candidate_name and text.strip():
        # Fallback: first non-empty line
        first_line = text.strip().split("\n")[0].strip()
        if len(first_line) < 50 and not any(c in first_line for c in "@:/\\"):
            candidate_name = first_line
    profile["name"] = candidate_name

    # Soft warning 5: Latest date in work history is over 18 months old
    latest_dt = find_latest_date_in_history(text)
    if latest_dt:
        days_old = (datetime.date.today() - latest_dt).days
        if days_old > 18 * 30:
            warnings.append(f"Notice: The latest date identified in your work history ({latest_dt.year}) is over 18 months old.")

    # Soft warning 6: Name differs from saved profile or < 30% skills overlap
    if saved_profile and not saved_profile.get("_is_empty"):
        saved_name = saved_profile.get("name") or ""
        if saved_name and candidate_name and saved_name.lower() != candidate_name.lower():
            warnings.append(f"Notice: Detected name '{candidate_name}' differs from saved profile '{saved_name}'. We will offer to update the active profile.")
        saved_skills = set(s.lower() for s in saved_profile.get("skills", []))
        if saved_skills:
            curr_skills = set(s.lower() for s in skills_found)
            overlap = len(saved_skills & curr_skills) / max(1, len(saved_skills))
            if overlap < 0.30:
                warnings.append(f"Notice: Skill overlap with saved profile is low ({int(overlap * 100)}%). This looks like a new profile variant.")

    # Soft warning 7: No email or phone, or garbled text
    if not contact["has_contact"]:
        warnings.append("Notice: No email address or phone number was detected in the document header.")

    non_letters = sum(1 for c in text if not c.isalnum() and not c.isspace())
    if text_chars > 0 and ((non_letters / text_chars) > 0.35 or text.count("\ufffd") >= 3):
        warnings.append("Notice: Document contains garbled text or unreadable symbols (encoding mismatch or OCR artifacts).")

    confidence = round(min(1.0, (len(sections_found) * 0.25) + (min(len(skills_found), 10) * 0.05) + (0.25 if contact["has_contact"] else 0.0)), 2)

    return {
        "ok": True,
        "kind": "resume",
        "issues": [],
        "warnings": warnings,
        "text_chars": text_chars,
        "sections_found": sections_found,
        "contact_found": contact["has_contact"],
        "name": candidate_name,
        "latest_date": str(latest_dt.year) if latest_dt else None,
        "skills_count": len(skills_found),
        "confidence": confidence,
        "profile": profile,
    }
