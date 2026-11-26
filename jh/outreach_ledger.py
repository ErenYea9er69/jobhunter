"""Outreach Ledger, Daily Cap Enforcement, Follow-ups, and Call Prep Pack (V8 Modern Track).

Rules:
- The MCP never sends an email: opens draft, user presses Send in mail app, clicks "I sent it".
- Gate "Already contacted?": show history; if <90d skip unless 4 days passed with no reply (allowing 1 follow-up).
- Gate "Under daily cap?": cap 20 default; if >= cap queue for tomorrow; resets daily.
- Follow-up tracker: set follow_up_due = today + 4d on send; due date triggers follow-up draft; max 1 follow-up.
- Reply tracker: status replied -> triggers call prep pack from company brief & learning pack.
- Weekly report: sent, replies, calls, reply rate by source/signal/attachment, 1 suggested change.
- First-draft legal notice: CAN-SPAM / GDPR personal outreach rules.
"""
from __future__ import annotations

import datetime
import json
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

from . import config, db, util
from .mcp_helpers import Result, ToolError, envelope

log = logging.getLogger("jobhunter.outreach_ledger")
if not log.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("[%(asctime)s] [outreach_ledger] %(levelname)s: %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

FIRST_DRAFT_LEGAL_NOTICE = (
    "You send these emails from your own email account. Follow the email rules of the "
    "recipient's country (CAN-SPAM in the US, GDPR in the EU). Modern outreach is for "
    "personal, relevant notes, not bulk email."
)


# =====================================================================
# 1. Gate: Already Contacted?
# =====================================================================

def record_contact(email: str, company: str = "") -> None:
    """Record outreach contact in ledger with 90-day cooldown."""
    db.init_db()
    clean_email = email.strip().lower()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    stable_outreach_id = util.stable_id(clean_email, "contact")
    db.log_outreach(
        contact_id=clean_email,
        company=company or "Company",
        status="sent",
        recipient_email=clean_email,
        sent_at=now,
        outreach_id=f"out_{stable_outreach_id}",
    )


def can_contact(email: str) -> bool:
    """Check if contact can be reached under 90-day ledger rules."""
    res = check_already_contacted(contact_id="", email=email)
    return bool(res.get("allowed", False))


def check_already_contacted(contact_id: str, email: str = "") -> Dict[str, Any]:
    """Check contact outreach history over past 90 days.

    Rules:
    - If never contacted in 90 days: allow.
    - If already replied: skip.
    - If follow-up already sent: skip (max 1 follow-up).
    - If contacted <4 days ago: skip (cooldown).
    - If contacted >= 4 days ago with no reply: allow ONE follow-up.
    """
    db.init_db()
    cutoff_90d = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)).isoformat()
    clean_email = email.strip().lower()
    history = db.query_outreach_history(contact_id=contact_id, email=clean_email, cutoff_iso=cutoff_90d)
    if not history:
        return {
            "allowed": True,
            "can_follow_up": False,
            "reason": "never_contacted",
            "history_count": 0,
            "history": [],
        }

    # Check statuses in history
    sent_rows = [h for h in history if h.get("status") in ("sent", "replied", "followup_sent")]
    if not sent_rows:
        return {
            "allowed": True,
            "can_follow_up": False,
            "reason": "drafted_not_sent",
            "history_count": len(history),
            "history": history,
        }

    # If any received a reply
    if any(h.get("status") == "replied" or h.get("reply_received_at") for h in history):
        return {
            "allowed": False,
            "can_follow_up": False,
            "reason": "already_replied",
            "message": "Candidate or lead already replied to previous outreach.",
            "history": history,
        }

    # If follow-up already sent (max 1 follow-up)
    if any(h.get("follow_up_sent_at") for h in history) or len(sent_rows) >= 2:
        return {
            "allowed": False,
            "can_follow_up": False,
            "reason": "follow_up_limit_reached",
            "message": "Maximum 1 follow-up already reached for this contact.",
            "history": history,
        }

    # Check timing of most recent sent outreach
    latest_sent = sent_rows[0]
    sent_at_str = latest_sent.get("sent_at") or latest_sent.get("created_at")
    try:
        sent_dt = datetime.datetime.fromisoformat(sent_at_str.replace("Z", "+00:00"))
        if sent_dt.tzinfo is None:
            sent_dt = sent_dt.replace(tzinfo=datetime.timezone.utc)
        elapsed_days = (datetime.datetime.now(datetime.timezone.utc) - sent_dt).total_seconds() / 86400.0
    except Exception:
        elapsed_days = 0.0

    follow_up_threshold = int(db.get_setting("follow_up_days", "4"))
    if elapsed_days >= follow_up_threshold:
        return {
            "allowed": True,
            "can_follow_up": True,
            "reason": "follow_up_allowed",
            "elapsed_days": round(elapsed_days, 1),
            "history": history,
        }
    else:
        return {
            "allowed": False,
            "can_follow_up": False,
            "reason": "cooldown_active",
            "elapsed_days": round(elapsed_days, 1),
            "days_remaining": round(follow_up_threshold - elapsed_days, 1),
            "message": f"Waiting for 4-day cooldown before follow-up ({round(follow_up_threshold - elapsed_days, 1)} days remaining).",
            "history": history,
        }


# =====================================================================
# 2. Gate: Under Daily Cap?
# =====================================================================

def check_daily_cap() -> Dict[str, Any]:
    """Check sent count today against daily cap.

    Default: 20 per day. If >= cap, new drafts are queued for tomorrow.
    """
    cap = int(db.get_setting("daily_cap", "20"))
    sent_today = db.get_outreach_today()
    sent_count = len(sent_today)
    remaining = max(0, cap - sent_count)
    under_cap = sent_count < cap

    return {
        "daily_cap": cap,
        "sent_today_count": sent_count,
        "remaining_cap": remaining,
        "under_cap": under_cap,
        "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    }


def queue_or_allow_draft(outreach_id: str) -> Dict[str, Any]:
    """Inspect daily cap and set status to 'queued' if cap exceeded."""
    cap_info = check_daily_cap()
    if not cap_info["under_cap"]:
        db.update_outreach_record(
            outreach_id,
            lambda r, _ws: r.update({"status": "queued", "updated_at": db.now_iso()}),
        )
        return {
            "status": "queued",
            "queued": True,
            "message": f"Daily cap of {cap_info['daily_cap']} reached. Email queued for tomorrow.",
            "cap_info": cap_info,
        }
    return {
        "status": "ready",
        "queued": False,
        "cap_info": cap_info,
    }


# =====================================================================
# 3. Sending & Follow-up Scheduling
# =====================================================================

def mark_outreach_sent(outreach_id_or_contact_id: str, is_follow_up: bool = False) -> Dict[str, Any]:
    """Record that the user pressed send in their email app.

    Sets sent_at = now, follow_up_due = now + 4 days. Enforces daily cap for initial sends.
    """
    now = db.now_iso()
    fu_days = int(db.get_setting("follow_up_days", "4"))
    fu_due = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=fu_days)).isoformat()
    cap_info = check_daily_cap() if not is_follow_up else {"under_cap": True}

    def _apply(row: Dict[str, Any], ws: Any) -> None:
        cid = row.get("contact_id", "")
        if not is_follow_up and not cap_info.get("under_cap", True):
            row.update({"status": "queued", "updated_at": now})
            return
        if is_follow_up:
            row.update({"status": "followup_sent", "sent_at": now, "follow_up_sent_at": now, "updated_at": now})
        else:
            row.update({"status": "sent", "sent_at": now, "follow_up_due": fu_due, "updated_at": now})
        for ct in ws.tables["contacts"]:
            if ct.get("id") == cid:
                ct.update({"status": "sent", "last_contacted_at": now, "updated_at": now})

    updated = db.update_outreach_record(outreach_id_or_contact_id, _apply)
    if not updated:
        raise ToolError(f"Outreach row not found for identifier: {outreach_id_or_contact_id}")

    if not is_follow_up and not cap_info.get("under_cap", True):
        return {
            "id": updated["id"],
            "contact_id": updated["contact_id"],
            "status": "queued",
            "queued": True,
            "cap_reached": True,
            "daily_cap": cap_info.get("daily_cap", 20),
            "sent_today_count": cap_info.get("sent_today_count", 20),
            "remaining_cap": 0,
            "message": f"Daily cap of {cap_info.get('daily_cap', 20)} sends reached. Queued for tomorrow.",
        }
    return updated


# =====================================================================
# 4. Reply Tracking & Call Prep Pack
# =====================================================================

def record_reply(outreach_id_or_contact_id: str, sentiment: str = "positive") -> Dict[str, Any]:
    """Record receipt of a reply from a lead and build structured Call Prep Pack."""
    now = db.now_iso()

    def _apply(row: Dict[str, Any], ws: Any) -> None:
        cid = row.get("contact_id", "")
        row.update({
            "status": "replied",
            "replied_at": now,
            "reply_received_at": now,
            "reply_sentiment": sentiment,
            "updated_at": now,
        })
        for ct in ws.tables["contacts"]:
            if ct.get("id") == cid:
                ct.update({"status": "replied", "updated_at": now})

    row_dict = db.update_outreach_record(outreach_id_or_contact_id, _apply)
    if not row_dict:
        raise ToolError(f"Outreach not found for {outreach_id_or_contact_id}")

    oid = row_dict.get("id")
    cid = row_dict.get("contact_id")
    comp = row_dict.get("company", "")
    sig_id = row_dict.get("signal_id", "")

    # Retrieve company brief & learning pack for call prep pack
    brief_data = db.get_company_brief(comp) or db.get_company_brief(sig_id) or {}
    learning_pack = brief_data.get("learning_pack", {})

    contact = db.get_contact(cid) or {}
    profile = db.get_profile() or {}

    call_prep_pack = {
        "company": comp,
        "contact_name": contact.get("name", "Contact"),
        "contact_title": contact.get("title") or contact.get("role", "Lead"),
        "sentiment": sentiment,
        "candidate_summary": f"{profile.get('name', 'Candidate')} ({profile.get('years', 4)} yrs experience)",
        "company_brief": brief_data.get("brief", {}),
        "talking_points": learning_pack.get("talking_points", [
            f"Discuss scaling engineering systems at {comp}",
            "Share learnings from high-throughput production services",
            "Understand current architecture bottlenecks and near-term roadmap",
            "Align on team culture and collaboration expectations",
            "Review candidate proof points and demonstrated impact",
        ]),
        "questions_to_ask": learning_pack.get("smart_questions", [
            "What is the most pressing technical hurdle the team is solving this quarter?",
            "How does the team prioritize feature delivery against platform reliability?",
            "What does a successful first 90 days look like in this role?",
        ]),
        "questions_to_expect": [
            "Tell me about a challenging distributed systems bug you resolved in production.",
            f"Why are you particularly interested in {comp} at this stage of growth?",
            "How do you approach testing, code reviews, and cross-functional coordination?",
        ],
    }

    return {
        "success": True,
        "outreach_id": oid,
        "contact_id": cid,
        "company": comp,
        "status": "replied",
        "call_prep_pack": call_prep_pack,
    }


# =====================================================================
# 5. Weekly Report & Performance Analytics
# =====================================================================

def generate_weekly_report() -> Dict[str, Any]:
    """Compile outreach performance analytics and suggest 1 data-driven improvement."""
    base_report = db.get_outreach_report()
    total_sent = base_report.get("total_sent", 0)
    total_replied = base_report.get("total_replied", 0)
    overall_rate = base_report.get("overall_reply_rate", 0.0)

    ws_stats = db.get_outreach_weekly_stats()
    w_sent, w_rep = ws_stats["w_sent"], ws_stats["w_rep"]
    wo_sent, wo_rep = ws_stats["wo_sent"], ws_stats["wo_rep"]
    w_rate = (w_rep / w_sent) if w_sent else 0.0
    wo_rate = (wo_rep / wo_sent) if wo_sent else 0.0
    by_source = ws_stats["by_source"]

    if w_rate > wo_rate and w_sent >= 3:
        suggested_change = (
            f"Emails with the 1-page resume attached achieved a {round(w_rate * 100)}% reply rate vs "
            f"{round(wo_rate * 100)}% without. Keep 'first_touch_attachment' enabled."
        )
    elif wo_rate > w_rate and wo_sent >= 3:
        suggested_change = (
            f"Short emails without attachments performed better ({round(wo_rate * 100)}% vs {round(w_rate * 100)}%). "
            "Consider disabling attachments for initial cold touches."
        )
    elif total_sent >= 5 and total_replied == 0:
        suggested_change = (
            "No replies received yet. Focus on hiring posts <24h old with under 50 likes "
            "to reach decision makers before the crowd."
        )
    else:
        suggested_change = (
            "Target outreach to hiring posts within 4-12 hours of publication for highest engagement."
        )

    return {
        "success": True,
        "total_sent": total_sent,
        "total_replied": total_replied,
        "calls_booked": total_replied,
        "overall_reply_rate": round(overall_rate, 2),
        "by_attachment": {
            "with_attachment": {"sent": w_sent, "replies": w_rep, "rate": round(w_rate, 2)},
            "without_attachment": {"sent": wo_sent, "replies": wo_rep, "rate": round(wo_rate, 2)},
        },
        "by_source": by_source,
        "suggested_change": suggested_change,
        "notice": FIRST_DRAFT_LEGAL_NOTICE,
    }
