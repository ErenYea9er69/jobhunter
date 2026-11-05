"""More things a client asks the CEO to do.

explain    why a job scored the way it did, what is missing, how the resumes compare
track      "I applied to Adyen", "Nova invited me to an interview": update the tracker
feedback   "not interested in banks", "never show Globex again": save exclusions
saved      show stored jobs, or the new ones
export     save the resume as a file
unclear    the request matched nothing: ask which of these the client wants

Every change to the client's data is read back from the store and confirmed. The CEO does not report
"saved" because a tool said so. It reports "saved" because the record is there when it looks.
"""

from __future__ import annotations

import re
from typing import Any

from .. import preferences, tracker
from . import qa, recall, safety
from .reflect import fit_label, rank

INTENT_MENU = [
    ("hunt", "Find jobs: 'find backend engineer jobs in Tunisia'"),
    ("hunt", "Find small and local employers: 'find small companies hiring python developers in Sfax'"),
    ("saved", "Show jobs I already found: 'show my saved jobs' or 'what is new'"),
    ("apply", "Prepare an application: 'write a cover letter for the second one'"),
    ("explain", "Explain a job's fit: 'why is the fit low for the Adyen job'"),
    ("interview", "Prepare for an interview: 'interview prep for the Nova job'"),
    ("outreach", "Write to a recruiter: 'message the recruiter at Adyen'"),
    ("skills", "Plan skills to learn: 'what skills should I learn'"),
    ("track", "Update my tracker: 'I applied to Adyen' or 'Nova invited me to interview'"),
    ("feedback", "Exclude things: 'not interested in banks'"),
    ("status", "See my pipeline: 'what is my status today'"),
    ("recheck", "Check a job again: 'is this job still open'"),
    ("export", "Save my resume as a file: 'export my resume as pdf'"),
    ("setup", "Set up: 'I want to work in Tunisia and France'"),
]


class ExtraIntents:
    # ---- unclear ------------------------------------------------------------------------

    def _unclear(self, m) -> None:
        m.decisions.append(f"I could not tell what you want from \"{safety.inline(m.request, 100)}\". Tell me which one, or say it another way.")
        m.summary["intent_menu"] = [{"intent": i, "example": ex} for i, ex in INTENT_MENU]
        m.next_steps.append("The AI can also pass hints.intent (one of: " + ", ".join(sorted({i for i, _ in INTENT_MENU})) + ") so nothing is guessed.")

    # ---- explain ------------------------------------------------------------------------

    def _explain(self, m) -> None:
        job_id = self._resolve_job(m)
        if not job_id:
            return
        job = self._gate_job(m, job_id)
        if job is None:
            return
        env = self.delegate(m, "analyst", "score_job", {"job_id": job_id}, f"Score the fit for job {job_id} and show how the score was built.")
        d = self._data(env)
        rev = qa.review_job(job, prefs=preferences.load(), profile=self._profile())
        matched = rev.adjusted.get("matched_skills", d.get("matched_skills") or job.get("matched_skills") or [])
        explain: dict[str, Any] = {"job_id": job_id, "title": safety.inline(job.get("title"), 80), "company": safety.inline(job.get("company"), 60)}
        if env["success"]:
            score = d.get("fit_score", d.get("score"))
            explain.update({"fit_score": score, "fit_label": fit_label(score), "matched_skills": matched,
                            "missing_skills": d.get("missing_skills") or job.get("missing_skills") or [],
                            "score_breakdown": d.get("score_breakdown") or {}})
            m.say(f"Analyst: fit score {score} ({fit_label(score)}) for {explain['title']} at {explain['company']}. "
                  f"Matched skills checked against your resume and the posting: {', '.join(map(str, matched[:6])) or 'none'}.")
        g = self.delegate(m, "analyst", "gap_report", {"job_id": job_id}, f"List the real gaps and the skills you could truthfully add for job {job_id}.")
        if g["success"]:
            gd = self._data(g)
            explain["real_gaps"] = (gd.get("real_gaps") or [])[:8]
            explain["could_add_if_true"] = (gd.get("add_if_true") or [])[:8]
            m.say("Analyst: real gaps: " + (", ".join(map(str, explain["real_gaps"])) or "none found") + ".")
        if re.search(r"\bcompare\b", m.request, re.I):
            c = self.delegate(m, "analyst", "compare_resumes", {"job_id": job_id}, f"Compare your resume versions for job {job_id}.")
            if c["success"]:
                explain["resume_comparison"] = {k: v for k, v in self._data(c).items() if k in ("best_resume", "ranking", "resumes", "recommendation")} or self._data(c)
                m.say("Analyst: resume versions compared.")
        m.summary["explain"] = explain
        m.next_steps.append("Ask me to prepare the application if the fit is worth it.")

    # ---- track --------------------------------------------------------------------------

    def _confirm(self, m, what: str, ok: bool, detail: str) -> None:
        from .ceo import Step  # local import: ceo.py imports this module
        m.steps.append(Step(id=f"s{len(m.steps) + 1}", employee="reviewer", tool="readback", objective=f"Read {what} back from the store to confirm it.",
                            status="done" if ok else "failed", attempts=1, review={"verdict": "pass" if ok else "block"}, note=detail))

    def _track(self, m) -> None:
        p, hints = m.parsed, m.hints
        status = str(hints.get("status") or p.status or "applied").lower()
        if status not in tracker.STATUSES:
            m.decisions.append(f"Which stage is it? One of: {', '.join(tracker.STATUSES)}.")
            return
        note = f"Recorded from the client's message: {safety.inline(m.request, 120)}"
        ref = p.reference
        company_ref = ref if ref and not re.fullmatch(r"-?\d{1,2}", ref) else ""
        apps = tracker.list_applications()
        matches = [a for a in apps if company_ref and company_ref in (a.get("company") or "").lower()] if not p.job_id else []
        if len(matches) > 1:
            m.decisions.append("More than one tracked application matches '" + company_ref + "': " + "; ".join(f"{a['title']} (id {a['id']})" for a in matches[:5]) + ". Which one?")
            return
        app_id = ""
        if len(matches) == 1:
            a = matches[0]
            env = self.delegate(m, "ops", "update_application", {"id": a["id"], "status": status, "notes": note}, f"Move {a['company']} to '{status}'.")
            app_id = a["id"] if env["success"] else ""
            if not env["success"]:
                m.blocked.append("The tracker update failed: " + (env.get("error") or {}).get("message", ""))
        else:
            job_id = p.job_id
            not_found = ""
            if not job_id and ref:
                rec = recall.resolve(ref)
                job_id = rec.job_id
                if rec.options:
                    m.decisions.append(rec.note + " " + "; ".join(f"{o.get('title')} at {o.get('company')} (job id {o['job_id']})" for o in rec.options) + ". Which one?")
                    return
                if not job_id and not (company_ref and hints.get("title")):
                    m.decisions.append((f"Which role at {company_ref.title()}? " if company_ref else "") + (rec.note or "Give the job title or a job_id, and I will record it."))
                    return
            if job_id:
                env = self.delegate(m, "ops", "track_application", {"job_id": job_id, "status": status, "notes": note}, f"Record job {job_id} as '{status}'.")
                app_id = (self._data(env).get("application") or {}).get("id", "") if env["success"] else ""
                if not env["success"]:
                    m.blocked.append("The tracker update failed: " + (env.get("error") or {}).get("message", ""))
            elif company_ref and hints.get("title"):
                env = self.delegate(m, "ops", "track_application", {"company": company_ref.title(), "title": hints["title"], "status": status, "notes": note},
                                    f"Record {company_ref.title()} as '{status}'.")
                app_id = (self._data(env).get("application") or {}).get("id", "") if env["success"] else ""
            else:
                m.decisions.append((f"Which role at {company_ref.title()}?" if company_ref else "Which job?") + " Give the job title or a job_id, and I will record it.")
                return
        if not app_id:
            return
        stored = next((a for a in tracker.list_applications() if str(a["id"]) == str(app_id)), None)
        ok = bool(stored and stored["status"] == status)
        self._confirm(m, "the tracker entry", ok, f"{stored['company']} / {stored['title']} is '{stored['status']}'." if stored else "The entry was not found.")
        if ok:
            m.say(f"Tracked: {stored['company']}, {stored['title']} is now '{status}' (read back from the tracker). Follow-up date: {stored.get('follow_up_date') or 'none'}.")
            if status == "interview":
                m.next_steps.append("Ask me for interview prep for this job.")
            if status == "rejected":
                m.next_steps.append("Ask me for a skill roadmap or to find similar jobs.")
        else:
            m.blocked.append("The tracker entry could not be confirmed after the update. Check your tracker.")

    # ---- feedback -----------------------------------------------------------------------

    def _feedback(self, m) -> None:
        p, hints = m.parsed, m.hints
        kws = list(dict.fromkeys([*(p.exclude or []), *[str(x).lower() for x in hints.get("exclude", []) or []]]))
        cos = list(dict.fromkeys([*(p.exclude_companies or []), *[str(x) for x in hints.get("exclude_companies", []) or []]]))
        if not kws and not cos:
            m.decisions.append("What should I leave out? Give company names or words, for example: 'never show Globex again' or 'not interested in banks'.")
            return
        updates: dict[str, list[str]] = {}
        if kws:
            updates["excluded_keywords"] = kws
        if cos:
            updates["excluded_companies"] = cos
        env = self.delegate(m, "ops", "set_preferences", {"updates": updates, "merge_lists": True}, "Save what the client does not want to see.")
        if not env["success"]:
            m.blocked.append("The exclusions were not saved: " + (env.get("error") or {}).get("message", ""))
            return
        prefs = preferences.load()
        have_k = {str(x).lower() for x in prefs.get("excluded_keywords", [])}
        have_c = {str(x).lower() for x in prefs.get("excluded_companies", [])}
        ok = all(k in have_k for k in kws) and all(c.lower() in have_c for c in cos)
        self._confirm(m, "your saved preferences", ok, f"keywords {sorted(have_k)[:6]}, companies {sorted(have_c)[:6]}")
        if ok:
            m.say("Excluded: " + ", ".join([*kws, *cos]) + " (read back from your saved preferences).")
            m.next_steps.append("This applies from your next search. Ask me to find jobs again.")
        else:
            m.blocked.append("The exclusions could not be confirmed in your preferences.")

    # ---- saved --------------------------------------------------------------------------

    def _saved(self, m) -> None:
        limit = max(1, min(25, int(m.hints.get("limit") or 10)))
        env = self.delegate(m, "scout", "get_saved_jobs", {"sort": "score", "limit": 50, "min_score": int(m.hints.get("min_score") or 0)}, "List the jobs already stored.")
        cards = self._data(env).get("jobs") or []
        if not cards:
            m.say("No jobs are stored yet.")
            m.next_steps.append("Ask me to find jobs.")
            return
        if re.search(r"\bnew\b|what['’]?s new|since", m.request, re.I):
            fresh = [c for c in cards if c.get("is_new")]
            if fresh:
                cards = fresh
            else:
                m.notes.append("None of the stored jobs is marked new, so this is the full list.")
        m.say(f"{len(cards)} stored job(s). They come from earlier searches and were not read live today.")
        self._review_cards(m, rank(cards, small=False, limit=limit), env.get("correlation_id", ""), limit, live=False, tool="get_saved_jobs")
        m.next_steps.append("Ask me to recheck one before you apply.")

    # ---- export -------------------------------------------------------------------------

    def _export(self, m) -> None:
        fmt = (m.hints.get("format") or m.parsed.export_format or "pdf").lower()
        env = self.delegate(m, "writer", "export_resume", {"format": fmt, "resume_name": m.hints.get("resume_name", "")}, f"Save the resume as {fmt}.")
        if not env["success"]:
            m.blocked.append("The export failed: " + (env.get("error") or {}).get("message", ""))
            return
        d = self._data(env)
        path = next((str(v) for v in d.values() if isinstance(v, str) and v.lower().endswith(("." + fmt, ".txt", ".html", ".docx", ".pdf"))), "")
        m.docs.append({"kind": f"resume export ({fmt})", "job_id": "", "review": {"verdict": "pass", "notes": ["Your own resume data. Nothing was written for you."]},
                       "approved_file": path, "provenance": {"correlation_id": env.get("correlation_id", "")}})
        m.say(f"Exported: {path or 'the file was created'}.")
