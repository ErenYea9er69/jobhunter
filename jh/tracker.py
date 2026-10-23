"""Application tracker, watchlist, and the prepare-application bundle."""
import datetime
import json
import time

from . import db, sources as src, refit, ats
from .util import days_since, now_iso, normalize_company, clean_text

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
        company = clean_text(data.get("company")) or "Unknown"
        title = clean_text(data.get("title")) or "Untitled role"
        location = clean_text(data.get("location", ""))
        salary = clean_text(data.get("salary", ""))
        c.execute("""INSERT OR REPLACE INTO applications (id,job_id,company,title,location,salary,status,notes,follow_up_date,
                     sources_json,job_data_json,tailored_resume_json,cover_letter,created_at,updated_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (app_id, data.get("job_id"), company, title,
                   location, salary, status, data.get("notes", ""), follow,
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


def generate_application_follow_up(app_id, action_type="status_check_5days", notes="", profile=None, use_llm=None, llm_caller=None):
    """Generate high-leverage follow-up communications: status ping, post-interview thank you, or offer negotiation script."""
    with db.session() as c:
        row = c.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if not row:
        raise ValueError(f"Application {app_id} not found.")

    company = row["company"] or "the company"
    title = row["title"] or "the role"
    stage = row["status"]
    applied_date = row["created_at"][:10] if row["created_at"] else ""
    salary_offered = row["salary"] or ""

    if not profile:
        profile = db.get_profile()

    cand_name = profile.get("name") or "Candidate"
    cand_role = (profile.get("experience") or [{}])[0].get("role") or profile.get("target_title") or "Software Engineer"
    skills = profile.get("skills", [])
    key_skill = skills[0] if skills else "modern architecture"

    # Normalize action_type
    at = (action_type or "").lower()
    if "interview" in at or "thank" in at:
        norm_type = "post_interview_thank_you"
    elif "offer" in at or "negotiat" in at:
        norm_type = "offer_negotiation"
    else:
        norm_type = "status_check_5days"

    # Deterministic fallback templates
    if norm_type == "post_interview_thank_you":
        subject = f"Thank you — {title} interview ({cand_name})"
        body = (
            f"Dear {company} Team,\n\n"
            f"Thank you for taking the time to speak with me today about the {title} position. "
            f"I truly enjoyed our discussion regarding the team's engineering priorities and architectural goals.\n\n"
            f"Our conversation reinforced my excitement about the opportunity. With my experience in {key_skill}, "
            f"I am confident I can contribute meaningfully from day one.\n\n"
            f"Please let me know if there are any additional details or code samples I can provide as you proceed.\n\n"
            f"Best regards,\n{cand_name}"
        )
        timing = "Within 24 hours of the interview"
        strategy = "Reinforces technical conversation and highlights immediate contribution."
    elif norm_type == "offer_negotiation":
        subject = f"{title} Offer — Discussion & Alignment ({cand_name})"
        target_sal = profile.get("target_salary") or "market rate"
        body = (
            f"Dear {company} Team,\n\n"
            f"Thank you very much for extending the offer for the {title} role. "
            f"I am genuinely thrilled about the team's mission and the impact of the work ahead.\n\n"
            f"Given my verified track record in {key_skill} and the scope of responsibilities, "
            f"I would like to discuss whether we can align closer to {target_sal} in base compensation. "
            f"I am fully committed to making this partnership a mutual success and remain flexible on structuring total compensation.\n\n"
            f"Could we schedule a brief call this week to finalize details?\n\n"
            f"Best regards,\n{cand_name}"
        )
        timing = "Within 48 hours of receiving written offer"
        strategy = "Gracious, value-anchored counter-proposal that maintains collaboration."
    else:
        subject = f"Following up on {title} application at {company} — {cand_name}"
        body = (
            f"Dear {company} Hiring Team,\n\n"
            f"I submitted my application for the {title} position last week and wanted to reiterate my strong interest in joining {company}.\n\n"
            f"Given my hands-on background in {key_skill}, I believe my skillset aligns well with the team's technical focus. "
            f"I would welcome the opportunity to connect for an introductory conversation when your schedule permits.\n\n"
            f"Thank you for your time and consideration.\n\n"
            f"Best regards,\n{cand_name}"
        )
        timing = "Tuesday or Thursday morning (9:00 AM local time)"
        strategy = "Confident 5-day touchpoint reaffirming fit without sounding demanding."

    fallback_result = {
        "ok": True,
        "application_id": app_id,
        "action_type": norm_type,
        "subject_line": subject,
        "body": body,
        "strategy_notes": strategy,
        "recommended_send_timing": timing,
        "used_llm": False,
        "provider": "deterministic"
    }

    ai_cfg = refit.get_active_ai_config()
    should_use_llm = (use_llm is True) or (use_llm is None and ai_cfg.get("provider") != "deterministic")
    caller = llm_caller or refit._call_llm

    if should_use_llm:
        import pathlib, re
        from . import config
        prompt_path = pathlib.Path(config.BASE_DIR) / "prompts" / "application_follow_up.md"
        system_prompt = (
            "You are an executive career strategist and negotiation consultant. "
            "Generate a strategic, professional follow-up communication based on the application stage. "
            "Return valid JSON only matching the schema."
        )
        try:
            if prompt_path.exists():
                text_content = prompt_path.read_text(encoding="utf-8")
                m = re.search(r"```markdown\n(.*?)\n```", text_content, re.S)
                if m:
                    system_prompt = m.group(1).strip()
        except Exception:
            pass

        try:
            prompt_payload = {
                "application": {
                    "company": company,
                    "role": title,
                    "stage": stage,
                    "applied_date": applied_date,
                    "notes": notes or row["notes"] or "",
                    "offered_salary": salary_offered
                },
                "candidate_source": {
                    "name": cand_name,
                    "target_title": cand_role,
                    "skills": skills[:15]
                },
                "follow_up_type": norm_type
            }
            raw_resp = caller(system_prompt, json.dumps(prompt_payload))
            parsed = refit._parse_json_llm_response(raw_resp)
            if parsed and isinstance(parsed, dict) and "body" in parsed:
                return {
                    "ok": True,
                    "application_id": app_id,
                    "action_type": parsed.get("action_type") or norm_type,
                    "subject_line": parsed.get("subject_line") or subject,
                    "body": parsed.get("body") or body,
                    "strategy_notes": parsed.get("strategy_notes") or strategy,
                    "recommended_send_timing": parsed.get("recommended_send_timing") or timing,
                    "used_llm": True,
                    "provider": ai_cfg.get("provider", "llm"),
                    "model": ai_cfg.get("model", "")
                }
        except Exception:
            pass

    return fallback_result


def get_stale_applications_alerts(threshold_days=5):
    """Scan all applications and return actionable alerts for follow-ups, post-interview thank-yous, and overdue items."""
    apps = list_applications()
    alerts = []
    today_iso = datetime.date.today().isoformat()

    for a in apps:
        status = a.get("status")
        days = a.get("days_in_stage", 0)
        fu = a.get("follow_up_date") or ""
        overdue = a.get("overdue", False)

        if status == "applied":
            if days >= threshold_days or overdue or (fu and fu <= today_iso):
                urgency = "high" if (days >= 10 or overdue) else "medium"
                alerts.append({
                    "id": f"alert-{a['id']}",
                    "application_id": a["id"],
                    "company": a["company"],
                    "title": a["title"],
                    "status": status,
                    "days_in_stage": days,
                    "alert_type": "status_check",
                    "action_type": "status_check_5days",
                    "urgency": urgency,
                    "headline": f"Follow-up due for {a['company']} ({int(days)}d in stage)",
                    "recommendation": f"Send a polite 5-day check-in reaffirming your fit for {a['title']}."
                })
        elif status == "interview":
            if days >= 1:
                alerts.append({
                    "id": f"alert-{a['id']}",
                    "application_id": a["id"],
                    "company": a["company"],
                    "title": a["title"],
                    "status": status,
                    "days_in_stage": days,
                    "alert_type": "interview_thank_you",
                    "action_type": "post_interview_thank_you",
                    "urgency": "high" if days <= 2 else "medium",
                    "headline": f"Send interview thank-you note to {a['company']}",
                    "recommendation": "Reinforce technical discussion points and confirm your enthusiasm."
                })
        elif status == "offer":
            alerts.append({
                "id": f"alert-{a['id']}",
                "application_id": a["id"],
                "company": a["company"],
                "title": a["title"],
                "status": status,
                "days_in_stage": days,
                "alert_type": "offer_decision",
                "action_type": "offer_negotiation",
                "urgency": "urgent",
                "headline": f"Active offer from {a['company']}",
                "recommendation": "Review compensation terms or generate a strategic negotiation counter-proposal."
            })

    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda x: priority_order.get(x["urgency"], 4))

    return {
        "ok": True,
        "alerts": alerts,
        "count": len(alerts),
        "threshold_days": threshold_days
    }


def generate_one_click_bundle(job, profile=None, use_llm=None):
    """High-velocity 1-Click Application Bundle: tailored resume, role pitch, outreach note, interview prep, and pre-filled screening answers."""
    t0 = time.time()
    from . import autofill
    if not profile:
        profile = db.get_profile()

    # 1. Tailored Resume & 6-Second Audit
    ref = refit.generate_custom_resume(job, profile, archetype="startup_velocity", use_llm=use_llm)
    tailored = ref["tailored_resume"]
    before_ats = ats.compute_ats_audit(profile, job)
    after_ats = ats.compute_ats_audit(tailored, job)

    # 2. Targeted Role Pitch
    pitch = refit.generate_cover_pitch(job, profile, angle="startup_velocity", use_llm=use_llm)

    # 3. Recruiter Outreach Package
    outreach = refit.generate_recruiter_outreach(job, profile, message_type="all", use_llm=use_llm)

    # 4. Role-Specific Interview Prep Copilot
    prep = refit.generate_interview_prep(job, profile, use_llm=use_llm)

    # 5. Top 3 Screening Questions Auto-Solved
    standard_questions = [
        "Why are you interested in this role and what makes you a strong fit?",
        "Describe your production experience with the core technical stack required for this position.",
        "Tell us about a challenging technical problem you solved and the measurable impact it had."
    ]
    screening_answers = []
    for q in standard_questions:
        ans = autofill.solve_screening_question(q, job, profile, use_llm=use_llm)
        screening_answers.append({
            "question": q,
            "answer": ans.get("answer", ""),
            "grounded": ans.get("grounded", True)
        })

    # 6. Save or stage in application tracker
    app_id = f"app-bundle-{int(time.time() * 1000)}"
    company = job.get("company") or "Unknown"
    title = job.get("title") or "Untitled role"
    boost = max(after_ats["ats_score"] - before_ats["ats_score"], 0)

    upsert_application({
        "id": app_id,
        "job_id": job.get("id"),
        "company": company,
        "title": title,
        "location": job.get("location", ""),
        "salary": job.get("salary", ""),
        "status": "saved",
        "notes": f"1-Click Bundle generated. ATS score {before_ats['ats_score']} -> {after_ats['ats_score']} (+{boost}). Outreach and screening ready.",
        "sources": job.get("sources") or [{"source": job.get("source"), "url": job.get("url")}],
        "job_data": job,
        "tailored_resume": tailored,
        "cover_letter": pitch.get("letter", "")
    })

    return {
        "ok": True,
        "success": True,
        "app_id": app_id,
        "job_id": job.get("id"),
        "company": company,
        "title": title,
        "tailored_resume": tailored,
        "refinement": ref,
        "executive_hook": ref.get("executive_hook", ""),
        "role_pitch": pitch,
        "cover_letter": pitch.get("letter", ""),
        "recruiter_outreach": outreach,
        "interview_prep": prep,
        "screening_answers": screening_answers,
        "ats_audit": after_ats,
        "before_ats": before_ats,
        "after_ats": after_ats,
        "ats_boost": boost,
        "speed_ms": int((time.time() - t0) * 1000),
        "next_step": "1-Click bundle prepared! Review tailored assets and submit directly on company site."
    }


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
