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

from . import config, db
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

def check_already_contacted(contact_id: str, email: str = "") -> Dict[str, Any]:
    """Check contact outreach history over past 90 days.

    Rules:
    - If never contacted in 90 days: allow.
    - If already replied: skip.
    - If follow-up already sent: skip (max 1 follow-up).
    - If contacted <4 days ago: skip (cooldown).
    - If contacted >= 4 days ago with no reply: allow ONE follow-up.
    """
    cutoff_90d = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)).isoformat()
    clean_email = email.strip().lower()

    with db.session() as c:
        if clean_email:
            rows = c.execute(
                """SELECT * FROM outreach
                   WHERE (contact_id=? OR lower(recipient_email)=lower(?))
                     AND created_at >= ?
                   ORDER BY created_at DESC""",
                (contact_id, clean_email, cutoff_90d),
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT * FROM outreach
                   WHERE contact_id=? AND created_at >= ?
                   ORDER BY created_at DESC""",
                (contact_id, cutoff_90d),
            ).fetchall()

    history = [dict(r) for r in rows]
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
        with db.session() as c:
            c.execute("UPDATE outreach SET status='queued', updated_at=? WHERE id=?", (db.now_iso(), outreach_id))
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

    Sets sent_at = now, follow_up_due = now + 4 days.
    """
    now = db.now_iso()
    fu_days = int(db.get_setting("follow_up_days", "4"))
    fu_due = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=fu_days)).isoformat()

    with db.session() as c:
        row = c.execute(
            """SELECT * FROM outreach
               WHERE id=? OR contact_id=?
               ORDER BY created_at DESC LIMIT 1""",
            (outreach_id_or_contact_id, outreach_id_or_contact_id),
        ).fetchone()
        if not row:
            raise ToolError(f"Outreach row not found for identifier: {outreach_id_or_contact_id}")

        oid = row["id"]
        cid = row["contact_id"]

        if is_follow_up:
            c.execute("""
                UPDATE outreach
                SET status='followup_sent', sent_at=?, follow_up_sent_at=?, updated_at=?
                WHERE id=?
            """, (now, now, now, oid))
        else:
            c.execute("""
                UPDATE outreach
                SET status='sent', sent_at=?, follow_up_due=?, updated_at=?
                WHERE id=?
            """, (now, fu_due, now, oid))

        c.execute("UPDATE contacts SET status='sent', last_contacted_at=?, updated_at=? WHERE id=?", (now, now, cid))

        updated = c.execute("SELECT * FROM outreach WHERE id=?", (oid,)).fetchone()
        return dict(updated) if updated else {}


# =====================================================================
# 4. Reply Tracking & Call Prep Pack
# =====================================================================

def record_reply(outreach_id_or_contact_id: str, sentiment: str = "positive") -> Dict[str, Any]:
    """Record receipt of a reply from a lead and build structured Call Prep Pack."""
    now = db.now_iso()
    with db.session() as c:
        row = c.execute(
            """SELECT * FROM outreach
               WHERE id=? OR contact_id=?
               ORDER BY created_at DESC LIMIT 1""",
            (outreach_id_or_contact_id, outreach_id_or_contact_id),
        ).fetchone()
        if not row:
            raise ToolError(f"Outreach not found for {outreach_id_or_contact_id}")

        row_dict = dict(row)
        oid = row_dict.get("id")
        cid = row_dict.get("contact_id")
        comp = row_dict.get("company", "")
        sig_id = row_dict.get("signal_id", "")

        c.execute("""
            UPDATE outreach
            SET status='replied', replied_at=?, reply_received_at=?, reply_sentiment=?, updated_at=?
            WHERE id=?
        """, (now, now, sentiment, now, oid))
        c.execute("UPDATE contacts SET status='replied', updated_at=? WHERE id=?", (now, cid))

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

    # Breakdowns
    with db.session() as c:
        # 1. By attachment policy
        w_att = c.execute(
            "SELECT count(*) as s, sum(CASE WHEN status='replied' THEN 1 ELSE 0 END) as r FROM outreach WHERE attached=1 AND status != 'draft'"
        ).fetchone()
        wo_att = c.execute(
            "SELECT count(*) as s, sum(CASE WHEN status='replied' THEN 1 ELSE 0 END) as r FROM outreach WHERE attached=0 AND status != 'draft'"
        ).fetchone()

        w_rate = (w_att["r"] / w_att["s"]) if (w_att and w_att["s"]) else 0.0
        wo_rate = (wo_att["r"] / wo_att["s"]) if (wo_att and wo_att["s"]) else 0.0

        # 2. By source type
        source_rows = c.execute("""
            SELECT s.source, count(o.id) as sent, sum(CASE WHEN o.status='replied' THEN 1 ELSE 0 END) as replies
            FROM outreach o
            JOIN signals s ON o.signal_id = s.id
            WHERE o.status != 'draft'
            GROUP BY s.source
        """).fetchall()

        by_source = {}
        for r in source_rows:
            s_name = r["source"] or "other"
            s_sent = r["sent"] or 0
            s_rep = r["replies"] or 0
            by_source[s_name] = {
                "sent": s_sent,
                "replies": s_rep,
                "rate": round(s_rep / s_sent, 2) if s_sent else 0.0,
            }

    # Data-driven suggested change
    if w_rate > wo_rate and w_att["s"] >= 3:
        suggested_change = (
            f"Emails with the 1-page resume attached achieved a {round(w_rate * 100)}% reply rate vs "
            f"{round(wo_rate * 100)}% without. Keep 'first_touch_attachment' enabled."
        )
    elif wo_rate > w_rate and wo_att["s"] >= 3:
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
            "with_attachment": {"sent": w_att["s"] if w_att else 0, "replies": w_att["r"] if w_att else 0, "rate": round(w_rate, 2)},
            "without_attachment": {"sent": wo_att["s"] if wo_att else 0, "replies": wo_att["r"] if wo_att else 0, "rate": round(wo_rate, 2)},
        },
        "by_source": by_source,
        "suggested_change": suggested_change,
        "notice": FIRST_DRAFT_LEGAL_NOTICE,
    }
