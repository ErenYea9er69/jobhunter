"""Application tracker, watchlist, and the prepare-application bundle."""
import datetime
import json
import time

from . import db, sources as src, refit, ats
from .util import days_since, now_iso, normalize_company

STATUSES = ["saved", "applied", "interview", "offer", "rejected"]  # "rejected" is the Archived column in the UI
FOLLOW_UP_DAYS = {"applied": 7, "interview": 3, "offer": 2}


def _row_to_app(c, r):
    hist = [dict(h) for h in c.execute("SELECT status, changed_at FROM status_history WHERE app_id=? ORDER BY id", (r["id"],))]
    since = days_since(hist[-1]["changed_at"]) if hist else None
    fu = r["follow_up_date"] or ""
    overdue = bool(fu and fu < datetime.date.today().isoformat() and r["status"] in ("applied", "interview"))
    jd = json.loads(r["job_data_json"]) if r["job_data_json"] else {}
    score = jd.get("score") or jd.get("fit_score") or (jd.get("ranking", {}) or {}).get("fit") or 0
    return {
        "id": r["id"], "job_id": r["job_id"], "company": r["company"], "title": r["title"], "location": r["location"],
        "salary": r["salary"], "status": r["status"], "notes": r["notes"], "follow_up_date": fu,
        "sources": json.loads(r["sources_json"]) if r["sources_json"] else [],
        "job_data": jd,
        "priority": jd.get("priority") or "medium",
        "tasks": jd.get("tasks") or [],
        "contacts": jd.get("contacts") or [],
        "interview_round": jd.get("interview_round") or "",
        "interview_date": jd.get("interview_date") or "",
        "url": jd.get("url") or (json.loads(r["sources_json"])[0].get("url") if r["sources_json"] and json.loads(r["sources_json"]) else ""),
        "score": int(score) if score else 0,
        "tailored_resume": json.loads(r["tailored_resume_json"]) if r["tailored_resume_json"] else None,
        "cover_letter": r["cover_letter"], "created_at": r["created_at"], "updated_at": r["updated_at"],
        "history": hist, "days_in_stage": round(since, 1) if since is not None else 0, "overdue": overdue,
    }


def list_applications():
    with db.session() as c:
        return [_row_to_app(c, r) for r in c.execute("SELECT * FROM applications ORDER BY updated_at DESC")]


def upsert_application(data):
    app_id = data.get("id") or f"app-{int(time.time() * 1000)}"
    status = data.get("status", "saved")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    now = now_iso()
    job_d = data.get("job_data") or {}
    if not isinstance(job_d, dict):
        job_d = {}
    for k in ("priority", "tasks", "contacts", "interview_round", "interview_date", "url", "score"):
        if k in data and data[k] is not None:
            job_d[k] = data[k]

    with db.session() as c:
        old = c.execute("SELECT status, follow_up_date, created_at FROM applications WHERE id=?", (app_id,)).fetchone()
        follow = data.get("follow_up_date") or ""
        if not follow and status in FOLLOW_UP_DAYS and (old is None or old["status"] != status):
            follow = (datetime.date.today() + datetime.timedelta(days=FOLLOW_UP_DAYS[status])).isoformat()
        c.execute("""INSERT OR REPLACE INTO applications (id,job_id,company,title,location,salary,status,notes,follow_up_date,
                     sources_json,job_data_json,tailored_resume_json,cover_letter,created_at,updated_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (app_id, data.get("job_id"), data.get("company") or "Unknown", data.get("title") or "Untitled role",
                   data.get("location", ""), data.get("salary", ""), status, data.get("notes", ""), follow,
                   json.dumps(data.get("sources", [])), json.dumps(job_d),
                   json.dumps(data.get("tailored_resume")), data.get("cover_letter", ""),
                   old["created_at"] if old else now, now))
        if old is None or old["status"] != status:
            c.execute("INSERT INTO status_history (app_id,status,changed_at) VALUES (?,?,?)", (app_id, status, now))
    return app_id


def delete_application(app_id):
    with db.session() as c:
        c.execute("DELETE FROM applications WHERE id=?", (app_id,))
        c.execute("DELETE FROM status_history WHERE app_id=?", (app_id,))


def funnel_stats():
    apps = list_applications()
    reached = {s: 0 for s in STATUSES}
    today_iso = datetime.date.today().isoformat()
    for a in apps:
        seen = {h["status"] for h in a["history"]} | {a["status"]}
        for s in seen:
            if s in reached:
                reached[s] += 1
    applied = reached["applied"] + 0
    def rate(n, d):
        return round(100 * n / d, 1) if d else None
    waits = []
    for a in apps:
        h = {x["status"]: x["changed_at"] for x in a["history"]}
        if "applied" in h and "interview" in h:
            d1, d2 = days_since(h["applied"]), days_since(h["interview"])
            if d1 is not None and d2 is not None:
                waits.append(d1 - d2)
    return {
        "total": len(apps),
        "live": sum(1 for a in apps if a["status"] not in ("rejected", "archived")),
        "reached": reached,
        "applied_to_interview_pct": rate(reached["interview"], applied),
        "interview_to_offer_pct": rate(reached["offer"], reached["interview"]),
        "avg_days_to_interview": round(sum(waits) / len(waits), 1) if waits else None,
        "overdue_follow_ups": sum(1 for a in apps if a["overdue"]),
        "today_follow_ups": sum(1 for a in apps if a.get("follow_up_date") == today_iso and a["status"] in ("applied", "interview")),
    }


def prepare_application(job, profile):
    """Build the full package for one job and save it as 'saved'. The user marks it 'applied' after submitting."""
    ref = refit.refine_resume_for_job(job, profile)
    tailored = ref["tailored_resume"]
    before, after = ats.compute_ats_audit(profile, job), ats.compute_ats_audit(tailored, job)
    letter = refit.generate_cover_letter(job, profile)
    prep = refit.generate_interview_prep(job, profile)
    app_id = f"app-prep-{int(time.time() * 1000)}"
    upsert_application({
        "id": app_id, "job_id": job.get("id"), "company": job.get("company"), "title": job.get("title"),
        "location": job.get("location", ""), "salary": job.get("salary", ""), "status": "saved",
        "notes": f"Package prepared. ATS score {before['ats_score']} to {after['ats_score']}. Mark as Applied after you submit.",
        "sources": job.get("sources") or [{"source": job.get("source"), "url": job.get("url")}],
        "job_data": job, "tailored_resume": tailored, "cover_letter": letter})
    return {"success": True, "status": "success", "app_id": app_id, "application_id": app_id, "job": job,
            "ats_audit": after, "before_ats": before, "after_ats": after, "tailor_result": ref, "refinement": ref,
            "cover_letter": letter, "prep_dossier": prep, "interview_prep": prep,
            "next_step": "Review the package, submit on the employer's page, then move the card to Applied."}


# ---------------------------------------------------------------- watchlist

def list_watchlist():
    with db.session() as c:
        return [dict(r) for r in c.execute("SELECT * FROM watchlist ORDER BY company_name")]


def add_watch(company_name, slug="", board_type="", target_role=""):
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("company_name is required")
    detected = None
    if not slug or not board_type:
        detected = src.detect_board(company_name)
        if detected:
            board_type, slug = detected
        elif not slug:
            raise ValueError(f"Could not find a public careers board for {company_name}. Enter the board type and slug by hand.")
    board_type = (board_type or "greenhouse").lower()
    if board_type not in src.BOARDS:
        raise ValueError(f"board_type must be one of {', '.join(src.BOARDS)}")
    wl_id = f"wl-{int(time.time() * 1000)}"
    with db.session() as c:
        c.execute("INSERT INTO watchlist (id,company_name,slug,board_type,target_role,added_at) VALUES (?,?,?,?,?,?)",
                  (wl_id, company_name, slug, board_type, target_role or "", now_iso()))
    return {"id": wl_id, "board_type": board_type, "slug": slug, "auto_detected": bool(detected)}


def check_watchlist(profile, force=True):
    """Fetch each watched board, count openings that match the target role, and record when it was checked."""
    from .scoring import score_job
    results = []
    for w in list_watchlist():
        board = src.BOARDS.get(w["board_type"])
        entry = {"id": w["id"], "company": w["company_name"], "matches": 0, "total": 0, "error": ""}
        try:
            jobs = board.fetch_company(w["slug"], w["company_name"])
            entry["total"] = len(jobs)
            role_words = [x for x in (w["target_role"] or profile.get("target_title", "")).lower().split() if len(x) > 2]
            hits = [j for j in jobs if not role_words or any(x in j["title"].lower() for x in role_words)]
            for j in hits:
                j.update(score_job(j, profile))
            hits.sort(key=lambda j: -j["score"])
            entry["matches"] = len(hits)
            entry["top"] = [{"title": j["title"], "url": j["url"], "score": j["score"], "location": j["location"]} for j in hits[:5]]
        except Exception as e:
            entry["error"] = str(e)[:160]
        with db.session() as c:
            if not entry["error"]:
                c.execute("UPDATE watchlist SET last_checked=?, active_matches_count=? WHERE id=?", (now_iso(), entry["matches"], w["id"]))
        results.append(entry)
    return results


def delete_watch(wl_id):
    with db.session() as c:
        c.execute("DELETE FROM watchlist WHERE id=?", (wl_id,))
