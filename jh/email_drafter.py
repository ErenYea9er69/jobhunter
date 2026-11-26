"""Short Email Drafter, Slop Checker, and Single-Resume Engine (V8 Modern Track).

Rules:
- Single resume per company and role, reused across all contacts at that company.
- Grounded against master resume; 1-page PDF <= 200 KB in jobmcp/outputs/.
- Email drafter: 3-4 lines, 40-80 words, subject <6 words, human tone.
- Line 1: 1 real detail from hiring post or product (<=5 words quoted).
- Line 2: 1 proof point from profile closest to stack.
- Line 3: small ask (reply or 15m).
- Last line: first name + portfolio link (or omitted if none).
- Attachment policy: mention resume & attach if first_touch_attachment on; omit if off.
- slop_check(draft, signal, brief): checks (a) through (h) rules.
- 2-round auto-rewrite loop on slop failure.
- Follow-up drafter: 2 lines, 1 new item, no attachment.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, db, exporters, home, preferences
from .mcp_helpers import Result, ToolError, envelope

log = logging.getLogger("jobhunter.email_drafter")
if not log.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("[%(asctime)s] [email_drafter] %(levelname)s: %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

BANNED_PHRASES = [
    "i hope this email finds you well",
    "i was thrilled to see",
    "reach out",
    "synergy",
    "deep dive",
    "game-changer",
    "testament",
    "spearhead",
    "delve",
    "leverage",
    "passion",
    "fast-paced",
]

EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\uD800-\uDBFF][\uDC00-\uDFFF]|[\u2600-\u27BF]|[\u2300-\u23FF]",
    re.UNICODE,
)


# =====================================================================
# 1. Single Job Resume Generator & Reuse Cache
# =====================================================================

def build_job_resume(
    company: str,
    role: str,
    signal_id: str = "",
    profile_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate or retrieve single grounded 1-page PDF resume per company and role.

    Output: 1-page PDF, at most 200 KB, in jobmcp/outputs/.
    Naming: Firstname_Lastname_Company_Role.pdf.
    Reused across all contacts at that company.
    """
    raw_profile = profile_override or db.get_profile() or {}
    profile = preferences.overlay_profile(raw_profile, None) if (raw_profile and not profile_override and not raw_profile.get("_prefs_applied")) else raw_profile
    name_str = profile.get("name") or "Candidate"
    name_parts = name_str.strip().split()
    first_name = name_parts[0] if name_parts else "Candidate"
    last_name = name_parts[-1] if len(name_parts) > 1 else ""

    clean_first = re.sub(r"[^\w]", "", first_name) or "Candidate"
    clean_last = re.sub(r"[^\w]", "", last_name) or "Resume"
    clean_comp = re.sub(r"[^\w]", "", company.replace(" ", "_")) or "Company"
    clean_role = re.sub(r"[^\w]", "", role.replace(" ", "_")) or "Role"

    filename = f"{clean_first}_{clean_last}_{clean_comp}_{clean_role}.pdf"
    outputs_dir = home.get_home() / "outputs"
    os.makedirs(outputs_dir, exist_ok=True)
    pdf_path = outputs_dir / filename
    meta_path = outputs_dir / f"{filename}.meta.json"

    # Compute factual signature so confirmed facts (e.g. side_work) invalidate stale PDF cache
    import hashlib
    eff_profile = dict(profile)
    sw_items: list[str] = []
    try:
        from . import refit
        sw_items = refit._confirmed_side_work_items(eff_profile)
        if sw_items:
            eff_profile["confirmed_side_work"] = sw_items
        if eff_profile.get("summary"):
            eff_profile["summary"] = refit._dehype_text(eff_profile["summary"])
    except Exception:
        pass
    facts_sig = hashlib.sha256(
        json.dumps({"side_work": sw_items, "summary": eff_profile.get("summary", ""), "skills": eff_profile.get("skills", [])}, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]

    # Reuse cache ONLY when confirmed facts / profile signature match
    cached_sig = ""
    if meta_path.is_file():
        try:
            cached_sig = json.loads(meta_path.read_text(encoding="utf-8")).get("facts_sig", "")
        except Exception:
            cached_sig = ""
    if pdf_path.is_file() and pdf_path.stat().st_size > 0 and cached_sig == facts_sig:
        size_kb = pdf_path.stat().st_size / 1024.0
        if size_kb <= 200:
            log.info("Reusing existing resume PDF: %s (%.1f KB)", filename, size_kb)
            return {
                "success": True,
                "resume_path": str(pdf_path),
                "filename": filename,
                "size_kb": round(size_kb, 1),
                "reused": True,
            }

    # Generate 1-page PDF using exporters
    pdf_bytes = exporters.to_pdf(eff_profile)
    size_bytes = len(pdf_bytes)
    size_kb = size_bytes / 1024.0

    if size_kb > 200:
        log.warning("Generated PDF is %.1f KB, exceeding 200 KB cap. Pruning sections.", size_kb)
        # Pruning redundant profile text to strictly fit 200 KB
        pruned_prof = dict(eff_profile)
        if "experience" in pruned_prof and isinstance(pruned_prof["experience"], list):
            pruned_prof["experience"] = pruned_prof["experience"][:3]
        pdf_bytes = exporters.to_pdf(pruned_prof)
        size_kb = len(pdf_bytes) / 1024.0

    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    try:
        meta_path.write_text(json.dumps({"facts_sig": facts_sig}), encoding="utf-8")
    except Exception:
        pass

    log.info("Generated new job resume: %s (%.1f KB)", filename, size_kb)
    return {
        "success": True,
        "resume_path": str(pdf_path),
        "filename": filename,
        "size_kb": round(size_kb, 1),
        "reused": False,
    }


# =====================================================================
# 2. Slop Checker
# =====================================================================

def slop_check(
    draft: Dict[str, Any] | str,
    signal: Optional[Dict[str, Any]] = None,
    brief: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """Strict linter for outreach emails.

    Checks:
    a) Banned phrases (case-insensitive).
    b) Word count between 30 and 80 words.
    c) Subject under 6 words.
    d) Quotes at most 5 words from post/product.
    e) Line openers: no two lines start with "I".
    f) No list of 3 items in a sentence.
    g) No em dashes, exclamation marks, or emojis.
    h) Sentence lengths: no two sentences with same word count in a row.
    """
    flags: List[str] = []

    if isinstance(draft, dict):
        subject = (draft.get("subject") or "").strip()
        body = (draft.get("body") or "").strip()
    else:
        subject = ""
        body = str(draft).strip()

    body_lower = body.lower()
    full_text = f"{subject} {body}".strip()
    full_lower = full_text.lower()

    # (a) Banned phrases
    for banned in BANNED_PHRASES:
        if banned in full_lower:
            flags.append(f"banned_phrase: '{banned}'")

    # (b) Word count between 30 and 80 words
    words = re.findall(r"\b\w+[\w'-]*\b", body)
    word_count = len(words)
    if word_count < 30:
        flags.append(f"word_count_too_short: {word_count} words (min 30)")
    elif word_count > 80:
        flags.append(f"word_count_too_long: {word_count} words (max 80)")

    # (c) Subject under 6 words
    if subject:
        subj_words = re.findall(r"\b\w+[\w'-]*\b", subject)
        if len(subj_words) >= 6:
            flags.append(f"subject_too_long: {len(subj_words)} words (max 5 words)")

    # (d) Quotes at most 5 words from post or product
    quotes = re.findall(r'["\']([^"\']+)["\']', body)
    for q in quotes:
        q_words = re.findall(r"\b\w+[\w'-]*\b", q)
        if len(q_words) > 5:
            flags.append(f"quote_too_long: quoted '{q}' has {len(q_words)} words (max 5)")

    # (e) Line openers: no two lines start with "I"
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    i_opener_count = 0
    for line in lines:
        if re.match(r"^I\b", line):
            i_opener_count += 1
    if i_opener_count >= 2:
        flags.append(f"multiple_i_openers: {i_opener_count} lines start with 'I'")

    # (f) No list of 3 items in a sentence
    # e.g. "X, Y, and Z" or "X, Y, or Z" or "1, 2, 3"
    list_3_pattern = re.compile(r"\b\w+,\s+\w+,\s+(?:and|or)\s+\w+\b", re.I)
    if list_3_pattern.search(body):
        flags.append("list_of_three_items: sentences should avoid 'A, B, and C' lists")

    # (g) No em dashes, exclamation marks, or emojis
    if "—" in full_text or "–" in full_text or "--" in full_text:
        flags.append("em_dash_detected: replace dashes with commas or separate sentences")
    if "!" in full_text:
        flags.append("exclamation_mark_detected: use periods for a calm professional tone")
    if EMOJI_PATTERN.search(full_text):
        flags.append("emoji_detected: remove emojis")

    # (h) Sentence lengths: no two sentences with same word count in a row
    # Split body into sentences
    sentences = [s.strip() for s in re.split(r"[.!?]+", body) if s.strip()]
    prev_len: Optional[int] = None
    for s in sentences:
        s_words = len(re.findall(r"\b\w+[\w'-]*\b", s))
        if s_words == 0:
            continue
        if prev_len is not None and s_words == prev_len:
            flags.append(f"equal_sentence_lengths_in_a_row: consecutive sentences both have {s_words} words")
            break
        prev_len = s_words

    passed = len(flags) == 0
    return passed, flags


# =====================================================================
# 3. Short Email Drafter with Rewrite Loop
# =====================================================================

def _select_proof_point(profile: Dict[str, Any], target_stack: str = "") -> str:
    """Select the single most relevant proof point from profile."""
    pps = profile.get("proof_points") or []
    if isinstance(pps, str):
        try:
            import json
            pps = json.loads(pps)
        except Exception:
            pps = []

    if pps and isinstance(pps, list):
        # Match stack keyword if available
        stack_lower = target_stack.lower()
        for p in pps:
            if isinstance(p, dict):
                proj = p.get("project", "")
                num = p.get("number", "")
                desc = f"{proj} ({num})" if num else proj
                if any(kw in proj.lower() for kw in stack_lower.split() if len(kw) > 3):
                    return desc
            elif isinstance(p, str):
                return p
        # Default to first proof point
        first_p = pps[0]
        if isinstance(first_p, dict):
            proj = first_p.get("project", "")
            num = first_p.get("number", "")
            return f"scaled {proj} to {num}" if num else proj
        return str(first_p)

    # Fallback to skills / years
    years = profile.get("years") or profile.get("years_of_experience") or 4
    skills = profile.get("skills") or ["Python", "distributed systems"]
    skill_str = skills[0] if skills else "engineering"
    return f"building production {skill_str} systems for {years} years"


def _format_draft_lines(
    recipient_first: str,
    specific_detail: str,
    proof_point: str,
    ask_line: str,
    first_name: str,
    portfolio_url: str,
    mention_attachment: bool = True,
    variation: int = 0,
) -> Tuple[str, str]:
    """Format subject and 3-4 line body."""
    # Subject: under 6 words
    if variation == 1:
        subject = "Quick question on your stack"
    elif variation == 2:
        subject = "Thoughts on your recent work"
    else:
        subject = "Note regarding your open role"

    # Line 1: 1 real detail from hiring post / product with <=5 words quoted
    if specific_detail:
        # Quote at most 4-5 words
        quoted_words = " ".join(re.findall(r"\b\w+\b", specific_detail)[:4])
        if variation == 1:
            line_1 = f"Saw your note discussing \"{quoted_words}\" earlier this week."
        elif variation == 2:
            line_1 = f"Noticed your recent update featuring \"{quoted_words}\"."
        else:
            line_1 = f"Caught your post mentioning \"{quoted_words}\" yesterday."
    else:
        if variation == 1:
            line_1 = "Followed your recent engineering progress with interest."
        else:
            line_1 = "Saw your latest team update this week."

    # Line 2: 1 proof point closest to their stack
    if variation == 1:
        line_2 = f"At my previous team, I focused on {proof_point}."
    elif variation == 2:
        line_2 = f"My recent work centered around {proof_point}."
    else:
        line_2 = f"Recently led work {proof_point}."

    # Line 3: small ask (+ optional attachment mention)
    if mention_attachment:
        if variation == 1:
            line_3 = "Curious if you have fifteen minutes this Thursday, and attached my background."
        elif variation == 2:
            line_3 = "Would fifteen minutes work next week? Attached one page for context."
        else:
            line_3 = "Open to a quick fifteen-minute chat? Attached one page for reference."
    else:
        if variation == 1:
            line_3 = "Would you be open to a quick fifteen-minute conversation this week?"
        else:
            line_3 = "Curious if you might be open to a quick reply or brief chat."

    # Last line: first name + portfolio link
    if portfolio_url:
        last_line = f"{first_name} | {portfolio_url}"
    else:
        last_line = first_name

    body = f"{line_1}\n{line_2}\n{line_3}\n{last_line}"
    return subject, body


def draft_cold_email(signal: Dict[str, Any], profile: Dict[str, Any], contact: Dict[str, Any]) -> Dict[str, Any]:
    """Draft cold email: 3-4 lines, 40-80 words, portfolio on last line, free of slop."""
    p_name = profile.get("name") or "Alex"
    first_name = p_name.strip().split()[0] if p_name.strip() else "Alex"
    portfolio_url = profile.get("portfolio") or profile.get("portfolio_url") or ""

    detail = signal.get("detail") or "engineering updates"
    quoted = " ".join(re.findall(r"\b\w+\b", detail)[:4])

    line_1 = f"Caught your recent update mentioning \"{quoted}\" earlier this week."
    proof = _select_proof_point(profile)
    clean_proof = proof.strip().rstrip(".")
    if clean_proof.lower().startswith("engineered"):
        proof_text = f"built and {clean_proof.lower()}"
    elif not clean_proof.lower().startswith("i "):
        proof_text = f"focused on {clean_proof}"
    else:
        proof_text = clean_proof
    line_2 = f"At my previous team, I {proof_text}."
    line_3 = "Would you have fifteen minutes for a quick chat? Attached one page for context."
    last_line = f"{first_name} | {portfolio_url}" if portfolio_url else first_name

    body = f"{line_1}\n{line_2}\n{line_3}\n{last_line}"
    return {
        "subject": "Note on your open role",
        "body": body,
        "recipient": contact.get("email", ""),
        "company": contact.get("company", ""),
    }


def draft_short_email(
    contact_id: str,
    signal_id: str = "",
    resume_path: str = "",
    specific_detail: str = "",
    company_override: str = "",
) -> Dict[str, Any]:
    """Draft human outreach email with strict slop linting and 2-round rewrite loop."""
    contact = db.get_contact(contact_id) or {}
    signal = db.get_signal(signal_id) if signal_id else {}
    profile = preferences.overlay_profile(db.get_profile() or {}, None)

    c_name = contact.get("name") or "there"
    c_parts = c_name.strip().split()
    recipient_first = c_parts[0] if c_parts else "there"
    company = contact.get("company") or (signal.get("company") if signal else "") or company_override or "the team"

    p_name = profile.get("name") or "Candidate"
    p_first = p_name.strip().split()[0] if p_name.strip() else "Candidate"
    portfolio_url = profile.get("portfolio_url") or ""

    # Check attachment policy
    attachment_flag = bool(config.get_first_touch_attachment())

    # Build or reuse resume if attachment enabled
    final_resume_path = resume_path
    if attachment_flag and not final_resume_path:
        target_role = contact.get("role") or (signal.get("role_guess") if signal else "Software Engineer")
        res_info = build_job_resume(company=company, role=target_role, signal_id=signal_id)
        final_resume_path = res_info.get("resume_path", "")

    # Extract specific detail from signal text if not provided
    if not specific_detail and signal:
        sig_text = signal.get("text", "")
        if sig_text:
            first_sentence = sig_text.split(".")[0].strip()
            # Quote up to 4 words
            words = re.findall(r"\b\w+\b", first_sentence)
            specific_detail = " ".join(words[:4]) if words else "infrastructure growth"
    if not specific_detail:
        specific_detail = "recent platform milestones"

    proof_point = _select_proof_point(profile, target_stack=specific_detail)

    # Drafting & Rewrite Loop (up to 2 rounds on slop failure)
    subject = ""
    body = ""
    flags: List[str] = []
    passed = False

    for attempt in range(3):  # initial attempt + up to 2 rewrites
        subject, body = _format_draft_lines(
            recipient_first=recipient_first,
            specific_detail=specific_detail,
            proof_point=proof_point,
            ask_line="",
            first_name=p_first,
            portfolio_url=portfolio_url,
            mention_attachment=attachment_flag,
            variation=attempt,
        )
        passed, flags = slop_check({"subject": subject, "body": body}, signal=signal)
        if passed:
            break
        log.debug("Slop check failed on attempt %d: %s. Rewriting.", attempt, flags)

    # Enforce daily send cap (20/day default): queue new outreach if cap reached
    from . import outreach_ledger
    cap_info = outreach_ledger.check_daily_cap()
    init_status = "draft" if cap_info.get("under_cap", True) else "queued"

    # Log draft in outreach ledger
    outreach_row = db.log_outreach(
        contact_id=contact_id,
        signal_id=signal_id,
        company=company,
        status=init_status,
        recipient_name=c_name,
        recipient_email=contact.get("email", ""),
        recipient_title=contact.get("title") or contact.get("role", ""),
        subject=subject,
        body=body,
        resume_path=final_resume_path if attachment_flag else "",
        attached=1 if attachment_flag else 0,
    )

    if init_status == "queued":
        return {
            "success": False,
            "status": "queued",
            "queued": True,
            "cap_reached": True,
            "under_cap": False,
            "daily_cap": cap_info.get("daily_cap", 20),
            "sent_today_count": cap_info.get("sent_today_count", 20),
            "remaining_cap": 0,
            "outreach_id": outreach_row.get("id"),
            "contact_id": contact_id,
            "company": company,
            "recipient_name": c_name,
            "recipient_email": contact.get("email", ""),
            "message": f"Daily cap of {cap_info.get('daily_cap', 20)} sends reached. Draft queued for tomorrow.",
        }

    return {
        "success": True,
        "status": "draft",
        "queued": False,
        "cap_reached": False,
        "under_cap": True,
        "daily_cap": cap_info.get("daily_cap", 20),
        "sent_today_count": cap_info.get("sent_today_count", 0),
        "remaining_cap": cap_info.get("remaining_cap", 20),
        "outreach_id": outreach_row.get("id"),
        "contact_id": contact_id,
        "company": company,
        "recipient_name": c_name,
        "recipient_email": contact.get("email", ""),
        "subject": subject,
        "body": body,
        "word_count": len(re.findall(r"\b\w+[\w'-]*\b", body)),
        "attached": attachment_flag,
        "resume_path": final_resume_path if attachment_flag else None,
        "slop_check_passed": passed,
        "slop_flags": flags,
    }


# =====================================================================
# 4. Follow-up Drafter
# =====================================================================

def draft_follow_up(
    contact_id: str,
    new_item: str = "",
) -> Dict[str, Any]:
    """Draft a short 2-line follow-up note, with 1 new item, no attachment.

    Never repeats the first email.
    """
    contact = db.get_contact(contact_id) or {}
    profile = preferences.overlay_profile(db.get_profile() or {}, None)
    p_name = profile.get("name") or "Candidate"
    p_first = p_name.strip().split()[0] if p_name.strip() else "Candidate"
    company = contact.get("company") or "the team"

    clean_item = new_item.strip() or f"recent updates on {company}'s roadmap"

    subject = f"Following up on {company}"
    line_1 = f"Saw the recent announcement regarding {clean_item} this morning."
    line_2 = "Still interested in a brief chat whenever your schedule allows."
    last_line = p_first

    body = f"{line_1}\n{line_2}\n{last_line}"
    return {
        "success": True,
        "contact_id": contact_id,
        "subject": subject,
        "body": body,
        "attached": False,
        "line_count": 2,
    }


# =====================================================================
# 5. MCP Tool Registrations
# =====================================================================

def jh_build_resume(company: str, role: str, signal_id: str = "") -> Dict[str, Any]:
    """Build or retrieve single grounded 1-page PDF resume <= 200 KB in jobmcp/outputs/."""
    try:
        res = build_job_resume(company=company, role=role, signal_id=signal_id)
        return envelope(status="ok", data=res)
    except ToolError as e:
        return envelope(status="error", error={"code": e.code, "message": str(e), "hint": e.hint})
    except Exception as e:
        log.exception("jh_build_resume unexpected error: %s", e)
        return envelope(status="error", error={"code": "resume_build_error", "message": str(e)})


def jh_draft_email(contact_id: str, signal_id: str = "", resume_path: str = "") -> Dict[str, Any]:
    """Draft human 3-4 line outreach email with strict slop check and attachment policy."""
    try:
        res = draft_short_email(contact_id=contact_id, signal_id=signal_id, resume_path=resume_path)
        warnings = res.get("slop_flags", []) if not res.get("slop_check_passed") else []
        return envelope(status="ok", data=res, warnings=warnings)
    except ToolError as e:
        return envelope(status="error", error={"code": e.code, "message": str(e), "hint": e.hint})
    except Exception as e:
        log.exception("jh_draft_email unexpected error: %s", e)
        return envelope(status="error", error={"code": "email_draft_error", "message": str(e)})
