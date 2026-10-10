"""Daily digest: new high-fit jobs since the last run. Writes an HTML file and emails it when SMTP is set."""
import datetime
import html
import os
import smtplib
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import config, db, pipeline
from .util import now_iso


def build_digest(profile=None, mark_sent=False, min_score=None):
    profile = profile or db.get_profile()
    min_score = int(min_score if min_score is not None else db.get_setting("digest_min_score", "75"))
    res = pipeline.search(profile=profile)
    qualifying = [j for j in res["jobs"] if j["score"] >= min_score]
    fresh = [j for j in qualifying if j.get("is_new")]
    with db.session() as c:
        undigested = {r["job_key"] for r in c.execute("SELECT job_key FROM seen_jobs WHERE digested=0")}
        picks = [j for j in qualifying if j["job_key"] in undigested]
        if mark_sent:
            for j in picks:
                c.execute("UPDATE seen_jobs SET digested=1 WHERE job_key=?", (j["job_key"],))
    return {
        "recipient_name": profile.get("name") or "there", "date": datetime.date.today().strftime("%A, %B %d, %Y"),
        "min_score": min_score, "total_matches_found": len(qualifying), "new_since_last_digest": len(picks),
        "new_today": len(fresh), "digest_jobs": picks[:10] or qualifying[:6], "showing_new_only": bool(picks),
        "sources": res["sources"],
        "summary": (f"{len(picks)} new role(s) scored {min_score}% or higher since your last digest." if picks
                    else f"No new roles at {min_score}%+ since the last digest. Showing your top current matches."),
    }


def render_html(d):
    rows = "".join(
        f"<tr><td style='padding:8px 0'><b>{html.escape(j['title'])}</b><br>{html.escape(j['company'])} | "
        f"{html.escape(j.get('location', ''))} | match {j['score']}%<br><a href='{html.escape(j['url'])}'>Open posting</a></td></tr>"
        for j in d["digest_jobs"])
    return (f"<html><body style='font-family:Arial,sans-serif;max-width:640px'><h2>Job digest for {html.escape(d['recipient_name'])}</h2>"
            f"<p>{html.escape(d['summary'])}</p><table>{rows}</table></body></html>")


def send_digest():
    profile = db.get_profile()
    d = build_digest(profile, mark_sent=True)
    page = render_html(d)
    os.makedirs(os.path.join(config.DATA_DIR, "digests"), exist_ok=True)
    path = os.path.join(config.DATA_DIR, "digests", f"digest-{datetime.date.today().isoformat()}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    to = db.get_setting("digest_email", profile.get("email", ""))
    emailed = False
    if config.SMTP_HOST and to:
        msg = MIMEMultipart("alternative")
        msg["Subject"], msg["From"], msg["To"] = f"Job digest: {len(d['digest_jobs'])} roles", config.SMTP_USER or to, to
        msg.attach(MIMEText(page, "html"))
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
            s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.send_message(msg)
        emailed = True
    return {"file": path, "emailed": emailed, "jobs": len(d["digest_jobs"])}


def start_scheduler():
    """Run send_digest once a day at JH_DIGEST_TIME (HH:MM, local time). Does nothing when unset."""
    if not config.DIGEST_TIME:
        return None
    hh, mm = (int(x) for x in config.DIGEST_TIME.split(":"))

    def loop():
        while True:
            now = datetime.datetime.now()
            nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if nxt <= now:
                nxt += datetime.timedelta(days=1)
            time.sleep(max(1, (nxt - now).total_seconds()))
            try:
                send_digest()
            except Exception as e:
                print(f"[digest] failed: {e}")
    t = threading.Thread(target=loop, daemon=True, name="jh-digest")
    t.start()
    return t
