"""Automatic Gmail job application tracker and status synchronization engine.

Parses incoming emails from ATS platforms (Greenhouse, Lever, Ashby, Workday, etc.)
and direct employer communications. Automatically extracts:
- Company name & Job title
- Application status (applied, interview, offer, rejected)
- Interview booking links & dates
- Automatically advances stages in the local SQLite Kanban tracker.
"""

from __future__ import annotations

import datetime
import email
from email.header import decode_header
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from . import config, db, tracker
from .util import clean_text, now_iso

CONFIG_FILENAME = "gmail_credentials.json"

# Common Applicant Tracking System domains
ATS_DOMAINS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkday.com",
    "myworkdayjobs.com",
    "smartrecruiters.com",
    "bamboohr.com",
    "workable.com",
    "taleo.net",
    "jobvite.com",
    "icims.com",
    "recruitee.com",
    "personio.com",
    "teamtailor.com",
    "breezy.hr",
    "pinpointhq.com",
    "rippling.com",
)

STATUS_PATTERNS = [
    # 1. Offer of Employment
    (
        "offer",
        re.compile(
            r"\b(offer of employment|pleased to offer|delighted to offer|congratulations on your offer|formal offer|offer letter|job offer)\b",
            re.IGNORECASE,
        ),
        0.95,
    ),
    # 2. Interview Invitation / Next Steps
    (
        "interview",
        re.compile(
            r"\b(invite you to (an? )?interview|invitation to interview|schedule a call|schedule an interview|schedule your (next )?round|phone screen|technical interview|coding challenge|assessment test|take-home assignment|meet with the team|calendly\.com|calendar\.google\.com|zoom\.us/j/)\b",
            re.IGNORECASE,
        ),
        0.90,
    ),
    # 3. Rejection / Not Moving Forward
    (
        "rejected",
        re.compile(
            r"\b(not (be )?moving forward|decided to pursue other|after careful (consideration|review)|unfortunately|wish you the best in your (job )?search|at this time we have decided|impressive background.*other candidates|position has been filled)\b",
            re.IGNORECASE,
        ),
        0.90,
    ),
    # 4. Acknowledgment / Application Received
    (
        "applied",
        re.compile(
            r"\b(thank you for (your )?applying|application received|received your application|we have received your|thank you for your interest in|application submitted|confirming receipt of your application)\b",
            re.IGNORECASE,
        ),
        0.85,
    ),
]


def get_config_path() -> Path:
    """Return path to .jobhunter/gmail_credentials.json."""
    base = Path(config.BASE_DIR) if hasattr(config, "BASE_DIR") else Path.cwd()
    jh_dir = base / ".jobhunter"
    jh_dir.mkdir(parents=True, exist_ok=True)
    return jh_dir / CONFIG_FILENAME


def get_gmail_config() -> Dict[str, Any]:
    """Return stored Gmail configuration (redacting secret password)."""
    cfg_path = get_config_path()
    if not cfg_path.is_file():
        return {
            "configured": False,
            "email": "",
            "imap_server": "imap.gmail.com",
            "imap_port": 993,
            "last_sync": "",
            "sync_enabled": False,
        }
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        has_pw = bool(data.get("app_password"))
        return {
            "configured": has_pw and bool(data.get("email")),
            "email": data.get("email", ""),
            "imap_server": data.get("imap_server", "imap.gmail.com"),
            "imap_port": data.get("imap_port", 993),
            "last_sync": data.get("last_sync", ""),
            "sync_enabled": data.get("sync_enabled", True),
        }
    except Exception:
        return {
            "configured": False,
            "email": "",
            "imap_server": "imap.gmail.com",
            "imap_port": 993,
            "last_sync": "",
            "sync_enabled": False,
        }


def save_gmail_config(
    email_addr: str,
    app_password: str,
    imap_server: str = "imap.gmail.com",
    imap_port: int = 993,
    sync_enabled: bool = True,
) -> bool:
    """Persist Gmail connection settings securely into .jobhunter/."""
    cfg_path = get_config_path()
    try:
        existing = {}
        if cfg_path.is_file():
            try:
                existing = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}

        payload = {
            "email": email_addr.strip(),
            "app_password": app_password.strip() if app_password else existing.get("app_password", ""),
            "imap_server": imap_server.strip() or "imap.gmail.com",
            "imap_port": int(imap_port or 993),
            "last_sync": existing.get("last_sync", ""),
            "sync_enabled": bool(sync_enabled),
            "updated_at": now_iso(),
        }
        cfg_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        return False


def _decode_mime_header(header_val: str) -> str:
    """Decode RFC 2047 MIME encoded-word strings into unicode."""
    if not header_val:
        return ""
    parts = decode_header(header_val)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(text))
    return " ".join(out).strip()


def extract_company_from_email(sender: str, subject: str, body: str) -> str:
    """Extract and normalize the company name from sender header, subject, or text."""
    # 1. Check sender display name (e.g. "Stripe Recruiting <jobs@stripe.com>" -> "Stripe")
    display_match = re.match(r"^[\"']?([^<\"'@]+)[\"']?\s*<", sender)
    if display_match:
        disp = display_match.group(1).strip()
        disp_clean = re.sub(
            r"\b(recruiting|careers|talent|team|hiring|notifications?|no-reply|jobs?)\b",
            "",
            disp,
            flags=re.IGNORECASE,
        ).strip(" -:,")
        if disp_clean and len(disp_clean) > 2 and not any(ats in disp_clean.lower() for ats in ATS_DOMAINS):
            return disp_clean

    # 2. Check subject patterns (e.g. "Your application to Vermeg for Backend Engineer", "[Brex] Application received")
    sub_patterns = [
        r"(?:application to|applied to|interest in|interview with|welcome to|offer from)\s+([A-Z0-9][A-Za-z0-9_\-\.\s]{1,24})(?:\s+for|\s+as|\s+-|\s+!|\s*$)",
        r"\[([A-Z0-9][A-Za-z0-9_\-\.\s]{1,20})\]",
        r"(?:at|@)\s+([A-Z0-9][A-Za-z0-9_\-\.\s]{1,20})(?:\s+Careers|\s+Recruiting|\s+Team|\s*$)",
    ]
    for pat in sub_patterns:
        m = re.search(pat, subject, re.IGNORECASE)
        if m:
            cand = m.group(1).strip(" -:;,[]")
            if len(cand) >= 2 and cand.lower() not in ("your", "the", "job", "career", "careers"):
                return cand

    # 3. Check sender email domain
    sender_email_match = re.search(r"[\w\.-]+@([\w\.-]+)", sender)
    if sender_email_match:
        domain = sender_email_match.group(1).lower()
        if not any(ats in domain for ats in ATS_DOMAINS) and domain not in ("gmail.com", "google.com", "yahoo.com", "outlook.com"):
            comp = domain.split(".")[0].capitalize()
            if len(comp) >= 2:
                return comp

    return "Unknown Company"


def extract_job_title_from_email(subject: str, body: str) -> str:
    """Extract the specific target role title from subject or opening lines."""
    patterns = [
        r"(?:for|role of|position of|as an?)\s+([A-Za-z0-9\s\/\-\#\+]{3,40})(?:\s+at|\s+with|\s+role|\s+position|\s+-|\s*$)",
        r"(?:application:?)\s+([A-Za-z0-9\s\/\-\#\+]{3,40})(?:\s+at|\s+with|\s+-|\s*$)",
    ]
    for pat in patterns:
        m = re.search(pat, subject, re.IGNORECASE)
        if m:
            t = m.group(1).strip(" -:;,")
            if len(t) >= 4 and not t.lower().startswith("your") and not t.lower().startswith("thank"):
                return t

    # Fallback to general tech titles found in body
    common_roles = (
        "Backend Software Engineer",
        "Frontend Engineer",
        "Full Stack Engineer",
        "Software Engineer",
        "Data Engineer",
        "DevOps Engineer",
        "Machine Learning Engineer",
        "Product Manager",
    )
    lower_body = (body[:1000] if body else "").lower()
    for role in common_roles:
        if role.lower() in lower_body:
            return role

    return "Software Engineer"


def extract_meeting_links(text: str) -> List[str]:
    """Extract Calendly, Google Meet, or Zoom meeting links from text."""
    if not text:
        return []
    links = re.findall(
        r"https?://(?:calendly\.com/[^\s\"'<>)]+|meet\.google\.com/[^\s\"'<>)]+|zoom\.us/j/[^\s\"'<>)]+|app\.reclaim\.ai/[^\s\"'<>)]+)",
        text,
        re.IGNORECASE,
    )
    return list(dict.fromkeys(links))[:3]


def classify_job_email(
    subject: str,
    sender: str,
    body: str,
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """Classify a single email into an actionable job application event."""
    sub_decoded = _decode_mime_header(subject)
    sender_decoded = _decode_mime_header(sender)
    combined_text = f"{sub_decoded} \n {body}"

    matched_status = None
    confidence = 0.0

    for status_name, pattern, score in STATUS_PATTERNS:
        if pattern.search(combined_text):
            matched_status = status_name
            confidence = score
            break

    # If no explicit status matched, check if sender is a recognized ATS
    is_ats = any(ats in sender_decoded.lower() for ats in ATS_DOMAINS)
    if not matched_status and is_ats:
        matched_status = "applied"
        confidence = 0.65

    company = extract_company_from_email(sender_decoded, sub_decoded, body)
    title = extract_job_title_from_email(sub_decoded, body)
    meeting_links = extract_meeting_links(body)

    # Clean concise snippet
    clean_snippet = re.sub(r"\s+", " ", body[:280]).strip() if body else ""

    return {
        "is_job_email": matched_status is not None,
        "company": company,
        "job_title": title,
        "status": matched_status or "saved",
        "confidence": confidence,
        "subject": sub_decoded,
        "sender": sender_decoded,
        "snippet": clean_snippet,
        "meeting_links": meeting_links,
        "date": date_str or now_iso(),
    }


def sync_gmail_with_tracker(classified_emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Synchronize classified job emails into SQLite applications table.

    Advances existing application statuses or creates new applications.
    """
    existing_apps = tracker.list_applications()
    comp_map = {}
    for app in existing_apps:
        norm = (app.get("company") or "").lower().strip()
        if norm and norm not in comp_map:
            comp_map[norm] = app

    updated_count = 0
    created_count = 0
    matches = []

    stage_order = {"saved": 1, "queued": 2, "applied": 3, "interview": 4, "offer": 5, "rejected": 6}

    for item in classified_emails:
        if not item.get("is_job_email"):
            continue

        comp = (item.get("company") or "").strip()
        comp_lower = comp.lower()
        status = item.get("status")
        snippet = item.get("snippet") or item.get("subject") or ""

        # Match existing application
        matched_app = comp_map.get(comp_lower)
        if not matched_app:
            # Substring matching (e.g. "Stripe" in "Stripe Payments")
            for k, app in comp_map.items():
                if (len(k) >= 4 and k in comp_lower) or (len(comp_lower) >= 4 and comp_lower in k):
                    matched_app = app
                    break

        if matched_app:
            current_status = matched_app.get("status")
            curr_rank = stage_order.get(current_status, 0)
            new_rank = stage_order.get(status, 0)

            # Advance stage if new status is higher rank or rejection
            should_advance = (status == "rejected") or (new_rank > curr_rank)
            note_entry = f"[Gmail Sync {item.get('date', '')[:10]}] {item.get('subject')}"

            if should_advance:
                tracker.upsert_application(
                    {
                        "id": matched_app["id"],
                        "company": matched_app["company"],
                        "title": matched_app["title"],
                        "status": status,
                        "notes": f"{matched_app.get('notes', '')}\n{note_entry}".strip(),
                    }
                )
                updated_count += 1
                matches.append(
                    {
                        "action": "updated",
                        "company": matched_app["company"],
                        "previous_status": current_status,
                        "new_status": status,
                        "subject": item.get("subject"),
                    }
                )
        else:
            # Auto-create newly discovered application if confirmed applied, interview, or offer
            if status in ("applied", "interview", "offer"):
                new_app_id = tracker.upsert_application(
                    {
                        "company": comp,
                        "title": item.get("job_title") or "Software Engineer",
                        "status": status,
                        "notes": f"Discovered via Gmail: {item.get('subject')}\n{snippet}",
                    }
                )
                created_count += 1
                comp_map[comp_lower] = {"id": new_app_id, "company": comp, "status": status}
                matches.append(
                    {
                        "action": "created",
                        "company": comp,
                        "status": status,
                        "subject": item.get("subject"),
                    }
                )

    # Record last sync time
    cfg_path = get_config_path()
    if cfg_path.is_file():
        try:
            curr_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            curr_cfg["last_sync"] = now_iso()
            cfg_path.write_text(json.dumps(curr_cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    return {
        "success": True,
        "emails_processed": len(classified_emails),
        "applications_updated": updated_count,
        "applications_created": created_count,
        "matches": matches,
    }


def fetch_gmail_and_sync(limit: int = 40, mock_messages: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Fetch recent messages from Gmail IMAP or mock messages, classify them, and sync with tracker."""
    if mock_messages is not None:
        classified = [
            classify_job_email(m.get("subject", ""), m.get("sender", ""), m.get("body", ""), m.get("date"))
            for m in mock_messages
        ]
        return sync_gmail_with_tracker(classified)

    cfg_path = get_config_path()
    if not cfg_path.is_file():
        return {"success": False, "error": "Gmail is not configured. Please add your email and app password in settings."}

    try:
        raw_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        email_addr = raw_cfg.get("email")
        app_password = raw_cfg.get("app_password")
        imap_server = raw_cfg.get("imap_server", "imap.gmail.com")
        imap_port = int(raw_cfg.get("imap_port", 993))
        if not email_addr or not app_password:
            return {"success": False, "error": "Incomplete Gmail credentials."}

        import imaplib

        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(email_addr, app_password)
        mail.select("INBOX", readonly=True)

        # Search query for recent job communications
        search_terms = '(OR FROM "greenhouse" (OR FROM "lever" (OR FROM "ashby" (OR FROM "workday" (OR SUBJECT "application" (OR SUBJECT "interview" SUBJECT "offer"))))))'
        typ, data = mail.search(None, search_terms)
        msg_ids = data[0].split() if data and data[0] else []

        classified = []
        # Process the most recent messages up to limit
        for mid in reversed(msg_ids[-limit:]):
            try:
                res, msg_data = mail.fetch(mid, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = _decode_mime_header(msg.get("Subject", ""))
                        sender = _decode_mime_header(msg.get("From", ""))
                        date_str = msg.get("Date", "")

                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                ctype = part.get_content_type()
                                if ctype == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body += payload.decode("utf-8", errors="replace") + "\n"
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")

                        item = classify_job_email(subject, sender, body, date_str)
                        if item["is_job_email"]:
                            classified.append(item)
            except Exception:
                continue

        mail.logout()
        return sync_gmail_with_tracker(classified)

    except Exception as e:
        return {"success": False, "error": f"Gmail IMAP connection failed: {str(e)}"}

