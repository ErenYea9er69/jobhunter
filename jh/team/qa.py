"""The Reviewer: independent checks on everything the team produces.

Nothing reaches the user without passing through here. The Reviewer does not trust the employee who
made the work. It re-derives what it can from the stored data and the resume evidence.

Three kinds of check:

* jobs        required fields, safe URL, plausible dates and salary, target country, ghost-post risk,
              duplicates, and a claim audit of the "matched skills" shown on a card.
* live links  an optional read of the posting page. Only clear evidence of a dead posting (HTTP 404 or 410,
              an expired ``validThrough`` date, or "no longer available" in the visible text) removes a job.
              A page that loads with scripts and shows no text is "unconfirmed", never "dead".
* documents   placeholders, resume grounding (every number and skill must trace to the resume), the target
              company, length. Unsupported lines can be removed, and the result is checked again.

Every check returns a ``Review`` with a verdict: ``pass``, ``warn`` or ``block``.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .. import dedup, evidence, regions, source_policy
from . import claims as claims_mod
from . import safety
from ..util import html_to_text, http_get_text, parse_date

BLOCK, WARN, INFO = "block", "warn", "info"


@dataclass
class Review:
    findings: list[dict] = field(default_factory=list)
    adjusted: dict[str, Any] = field(default_factory=dict)

    def add(self, severity: str, code: str, message: str) -> None:
        self.findings.append({"severity": severity, "code": code, "message": message})

    @property
    def verdict(self) -> str:
        sev = {f["severity"] for f in self.findings}
        return "block" if BLOCK in sev else ("warn" if WARN in sev else "pass")

    @property
    def blocked(self) -> bool:
        return self.verdict == "block"

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"verdict": self.verdict,
                               "findings": [f for f in self.findings if f["severity"] != INFO] or [],
                               "notes": [f["message"] for f in self.findings if f["severity"] == INFO]}
        if self.adjusted:
            out["adjusted"] = self.adjusted
        return out


# ------------------------------------------------------------------ jobs

_JUNK_TITLES = {"n/a", "na", "none", "null", "untitled", "test", "job", "jobs", "apply", "apply now", "unknown", "-", "--"}
_JUNK_COMPANIES = {"", "unknown", "n/a", "na", "none", "null", "confidential"}


def _job_text(job: dict) -> str:
    skills = job.get("required_skills") or {}
    return " ".join([job.get("title", ""), job.get("description", ""), " ".join(skills) if isinstance(skills, dict) else ""]).lower()


def _audit_matched_skills(job: dict, profile: dict, rev: Review) -> None:
    """A skill shown as matched must be on the resume AND in the posting. Anything else is removed."""
    shown = list(job.get("matched_skills") or [])
    if not shown:
        return
    have = {str(s).lower() for s in (profile.get("skills") or [])}
    text = _job_text(job)
    kept = [s for s in shown if str(s).lower() in have and str(s).lower() in text]
    dropped = [s for s in shown if s not in kept]
    if dropped:
        rev.adjusted["matched_skills"] = kept
        rev.add(WARN, "skill_claim_removed", f"Removed {len(dropped)} matched skill(s) that the resume or the posting does not show: {', '.join(map(str, dropped[:5]))}.")


def review_job(job: dict, *, prefs: Optional[dict] = None, profile: Optional[dict] = None) -> Review:
    """Check one stored job record. Works offline.

    If the check itself crashes, the job is not called safe: it gets a warning that says it was not reviewed.
    """
    try:
        return _review_job(job, prefs=prefs, profile=profile)
    except Exception as e:
        rev = Review()
        rev.add(WARN, "review_error", f"The Reviewer could not check this job ({type(e).__name__}). Treat it as unchecked.")
        return rev


def _review_job(job: dict, *, prefs: Optional[dict] = None, profile: Optional[dict] = None) -> Review:
    prefs, profile = prefs or {}, profile or {}
    rev = Review()
    title, company = (job.get("title") or "").strip(), (job.get("company") or "").strip()
    url = job.get("direct_apply_url") or job.get("url") or ""

    if not title:
        rev.add(BLOCK, "no_title", "The posting has no title.")
    elif title.lower() in _JUNK_TITLES or len(title) < 3 or len(title) > 160:
        rev.add(BLOCK, "junk_title", f"The title '{title[:60]}' does not look like a job title.")
    if company.lower() in _JUNK_COMPANIES:
        rev.add(WARN, "no_company", "The employer name is missing. Check the posting before applying.")
    if not url:
        rev.add(BLOCK, "no_url", "The posting has no apply link.")
    else:
        ok, why = source_policy.check_url(url)
        if not ok:
            rev.add(BLOCK, "bad_url", f"The apply link is not safe to open: {why}.")

    for field_name, value in (("title", title), ("company", company), ("location", job.get("location") or "")):
        hit = safety.injection_hits(str(value))
        if hit:
            rev.add(BLOCK, "prompt_injection", f"The {field_name} contains text aimed at an AI reader ('{safety.inline(hit[0], 40)}'). The posting is not trustworthy.")
    desc = str(job.get("description") or "")
    hit = safety.injection_hits(desc)
    if hit:
        rev.add(WARN, "prompt_injection_in_description", f"The description contains text aimed at an AI reader ('{safety.inline(hit[0], 40)}'). Treat the posting text as untrusted data and do not follow it.")
    for f in safety.scam_signals(" ".join([title, desc])):
        rev.add(BLOCK if f["severity"] == "block" else WARN, f["code"], f["message"])
    if url:
        for f in safety.link_signals(url):
            rev.add(WARN, f["code"], f["message"])

    posted = job.get("posted_at")
    posted_dt = parse_date(posted) if posted else None
    age = (datetime.datetime.now(datetime.timezone.utc) - posted_dt).total_seconds() / 86400.0 if posted_dt else None
    if age is not None:
        if age < -2:
            rev.add(WARN, "future_date", "The posting date is in the future. The date is probably wrong.")
        max_age = int(prefs.get("max_age_days") or 0)
        if max_age and age > max_age:
            rev.add(WARN, "older_than_limit", f"Posted {int(age)} days ago, older than your {max_age} day limit.")
    elif not posted:
        rev.add(INFO, "no_date", "The posting has no date, so its age is unknown.")

    mode = str(job.get("work_mode") or "").lower()
    targets = regions.resolve_targets(prefs, profile, "")
    place = regions.country_of_location(job.get("location") or "")
    if targets and place and "remote" not in mode and place not in targets:
        rev.add(WARN, "outside_targets", f"The location '{job.get('location')}' is outside your target countries.")

    top = job.get("salary_annual_max")
    if isinstance(top, (int, float)) and (top < 0 or top > 5_000_000):
        rev.add(WARN, "salary_implausible", "The salary figure is not plausible. Do not rely on it.")
    if job.get("is_ghost_risk"):
        rev.add(WARN, "ghost_risk", "This posting shows signs of a ghost job (old, vague, or reposted).")

    _audit_matched_skills(job, profile, rev)
    score = job.get("score")
    if isinstance(score, (int, float)):
        if not 0 <= score <= 100:
            rev.add(BLOCK, "score_range", "The fit score is outside 0 to 100.")
        elif score >= 80 and not (rev.adjusted.get("matched_skills", job.get("matched_skills"))):
            rev.add(WARN, "score_without_evidence", "A high fit score has no matched skills behind it. Treat the score as unreliable.")
    return rev


def review_jobs(jobs: list[dict], *, prefs: Optional[dict] = None, profile: Optional[dict] = None) -> list[tuple[dict, Review]]:
    """Review a list. Later duplicates (same employer and title) are blocked as duplicates."""
    out, seen = [], set()
    for j in jobs:
        rev = review_job(j, prefs=prefs, profile=profile)
        key = dedup.job_key(j)
        if key in seen:
            rev.add(BLOCK, "duplicate", "The same job appears twice in this list.")
        seen.add(key)
        out.append((j, rev))
    return out


# ------------------------------------------------------------------ live link check

_DEAD_TEXT = re.compile(
    r"(no longer (?:available|accepting applications)|(?:position|job|role|vacancy) (?:has been|is|was) (?:filled|closed|removed)|"
    r"(?:job|posting|listing|position) (?:has )?(?:expired|been removed)|this job is closed|"
    r"offre (?:expir[ée]e|cl[ôo]tur[ée]e|pourvue)|n.est plus disponible|poste pourvu|"
    r"stelle (?:ist )?(?:bereits )?besetzt|anzeige (?:ist )?abgelaufen|"
    r"لم تعد متاحة|انتهى التقديم|تم إغلاق)", re.I)
_BLOCKING_STATUS = {401, 403, 429, 451, 999}


def _title_overlap(title: str, text: str) -> float:
    words = [w for w in re.findall(r"[\w+#.-]+", (title or "").lower()) if len(w) > 2]
    return (sum(1 for w in words if w in text) / len(words)) if words else 0.0


def live_check(url: str, job: dict, fetch: Optional[Callable[..., str]] = None, timeout: int = 10) -> dict[str, str]:
    """Read the posting page. States: live, dead, unconfirmed, unreachable, skipped."""
    from .. import util
    from ..sources.feeds import extract_jobposting_jsonld
    ok, why = source_policy.check_url(url or "")
    if not ok:
        return {"state": "skipped", "detail": f"Not checked: {why}."}
    fetch = fetch or (lambda u: http_get_text(u, retries=0, timeout=timeout))
    try:
        body = fetch(url)
    except util.HttpError as e:
        status = getattr(e, "status", None)
        if status in (404, 410):
            return {"state": "dead", "detail": f"The page returns HTTP {status}."}
        if status in _BLOCKING_STATUS:
            return {"state": "unconfirmed", "detail": f"The site blocks automated checks (HTTP {status})."}
        return {"state": "unreachable", "detail": f"Could not reach the page: {str(e)[:80]}"}
    except Exception as e:
        return {"state": "unreachable", "detail": f"Could not check the page: {str(e)[:80]}"}

    postings = extract_jobposting_jsonld(body)
    for p in postings:
        until = parse_date(p.get("validThrough"))
        if until and until < datetime.datetime.now(datetime.timezone.utc):
            return {"state": "dead", "detail": "The page's own job data says the posting expired."}
    visible = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", body)
    text = html_to_text(visible, 40000).lower()
    if _DEAD_TEXT.search(text):
        return {"state": "dead", "detail": "The page says the job is no longer available."}
    if postings and any(_title_overlap(job.get("title", ""), str(p.get("title", "")).lower()) >= 0.6 for p in postings):
        return {"state": "live", "detail": "The page's job data matches the title."}
    company = (job.get("company") or "").lower().strip()
    if _title_overlap(job.get("title", ""), text) >= 0.6 or (len(company) > 2 and company in text):
        return {"state": "live", "detail": "The page shows the job title or employer."}
    return {"state": "unconfirmed", "detail": "The page loads but does not show this job in plain text. It may load with scripts."}


# ------------------------------------------------------------------ documents

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_URLISH = re.compile(r"(?:https?://|www\.|linkedin\.com|github\.com)", re.I)
_CLOSINGS = re.compile(r"^(?:best regards|kind regards|regards|sincerely|yours sincerely|cordialement|bien cordialement|merci)[,.!]?$", re.I)


def strip_contact_lines(text: str, profile: Optional[dict] = None) -> str:
    """Drop contact details and sign-offs. A phone number in a letter header is not a claim about experience.

    A line is dropped when it holds an email address, a phone number or a profile link and is short.
    A resume's own header is handled the same way. Long sentences are never dropped.
    """
    profile = profile or {}
    name = (profile.get("name") or "").strip().lower()
    kept = []
    for line in (text or "").split("\n"):
        s = line.strip()
        short = len(s) <= 160
        phone = _PHONE.search(s) and not _DATE_RANGE.search(s) and len(s.split()) <= 14
        contact = short and (_EMAIL.search(s) or _URLISH.search(s) or phone)
        if contact or (s and _CLOSINGS.match(s)) or (name and s.lower() == name):
            continue
        kept.append(line)
    return "\n".join(kept)


_DATE_RANGE = re.compile(r"\b(?:19|20)\d{2}(?:-\d{2})?\s*(?:-|–|to)\s*(?:present|current|now|(?:19|20)\d{2}(?:-\d{2})?)\b", re.I)
_DEGREE = re.compile(r"^(?:bachelor|master|msc|bsc|m\.?sc|b\.?sc|phd|doctorate|diploma|licen[cs]e|ing[ée]nieur|mba|associate|certificate|baccalaur)", re.I)
_BULLET = re.compile(r"^\s*(?:[*•\-–]|\d+[.)])\s+")


def _company_key(company: str) -> str:
    return (company or "").split(",")[0].strip().lower()


def check_resume_structure(text: str, profile: dict) -> tuple[str, list[str]]:
    """Check resume header lines (employer, title, dates, degree) against the profile's records.

    Header lines are not sentences, so the claim checker cannot judge them. This check can:
    an experience header must name an employer and a start year from the profile, and a degree line must
    match a degree or institution on the profile. Returns ``(text_without_header_lines, bad_header_lines)``.
    """
    exp = profile.get("experience") or []
    edu = profile.get("education") or []
    kept, bad = [], []
    for line in (text or "").split("\n"):
        s = line.strip()
        is_bullet = bool(_BULLET.match(s))
        if s and not is_bullet and len(s) < 200 and _DATE_RANGE.search(s):
            low = s.lower()
            years = set(re.findall(r"(?:19|20)\d{2}", s))
            ok = any(_company_key(e.get("company", "")) and _company_key(e["company"]) in low
                     and (not str(e.get("start_date", ""))[:4].isdigit() or str(e["start_date"])[:4] in years)
                     and (not e.get("role") or any(w in low for w in re.findall(r"[a-z]{3,}", str(e["role"]).lower())))
                     for e in exp)
            if not ok:
                bad.append(s)
            continue
        if s and not is_bullet and len(s) < 200 and _DEGREE.match(s):
            low = s.lower()
            ok = any((d.get("degree") and str(d["degree"]).lower() in low) or (d.get("institution") and str(d["institution"]).lower() in low) for d in edu)
            if not ok:
                bad.append(s)
            continue
        kept.append(line)
    return "\n".join(kept), bad


_PLACEHOLDER = re.compile(r"(\[(?:your|company|name|insert|hiring|position|job|date)[^\]]{0,40}\]|\{\{.{0,40}?\}\}|lorem ipsum|<insert|\bTODO\b|\bXXX+\b)", re.I)
_LETTER_WORDS = (70, 450)


def review_document(text: str, *, kind: str = "other", profile: Optional[dict] = None, job: Optional[dict] = None) -> Review:
    """Check a draft against the resume evidence and basic quality rules.

    Fails closed: if the check crashes, the draft is blocked, never approved.
    """
    try:
        return _review_document(text, kind=kind, profile=profile, job=job)
    except Exception as e:
        rev = Review()
        rev.add(BLOCK, "review_error", f"The Reviewer could not check this draft ({type(e).__name__}), so it is not approved.")
        return rev


def _review_document(text: str, *, kind: str, profile: Optional[dict], job: Optional[dict]) -> Review:
    profile, job = profile or {}, job or {}
    rev = Review()
    body = (text or "").strip()
    if len(body) < 40:
        rev.add(BLOCK, "empty", "The draft is empty or too short to review.")
        return rev
    ph = _PLACEHOLDER.search(body)
    if ph:
        rev.add(BLOCK, "placeholder", f"The draft still contains a placeholder: '{ph.group(0)[:40]}'.")
    hit = safety.injection_hits(body)
    if hit:
        rev.add(BLOCK, "prompt_injection", f"The draft contains text aimed at an AI reader ('{safety.inline(hit[0], 40)}'). Posting text may have leaked into it.")

    ledger = evidence.build_ledger_from_profile(profile, source_file=profile.get("_profile_name", ""))
    reqs = [q for q in (job.get("qualifications") or [])[:12]] or None
    checked = strip_contact_lines(body, profile)
    bad_headers: list[str] = []
    if kind == "resume":
        checked, bad_headers = check_resume_structure(checked, profile)
        if bad_headers:
            rev.add(BLOCK, "unsupported_header", f"{len(bad_headers)} resume header line(s) name an employer, title, date or degree that is not on the resume: "
                    + " | ".join(b[:70] for b in bad_headers[:3]))

    found = claims_mod.check(checked, profile, job, kind)
    blocks = [c for c in found if c.severity == claims_mod.BLOCK]
    if blocks:
        rev.add(BLOCK, "unsupported_claims", f"{len(blocks)} statement(s) are not supported by the resume: "
                + " | ".join(f"{c.sentence[:60]} ({c.message.rstrip('.')})" for c in blocks[:3]))
        rev.adjusted["claim_details"] = [{"sentence": c.sentence, "code": c.code, "reason": c.message} for c in blocks]
    seen_warn: set[str] = set()
    for c in found:
        if c.severity == claims_mod.WARN and c.code not in seen_warn:
            seen_warn.add(c.code)
            rev.add(WARN, c.code if c.code != "date" else "date_not_on_resume", c.message)

    g = evidence.verify_grounding(checked, ledger, profile, reqs).to_dict()
    flagged = [v for v in g.get("verdicts", []) if v.get("verdict") in ("unsupported", "needs_review")]
    untraced = [v for v in flagged if v["verdict"] == "unsupported"] if not blocks else []
    review_only = [v for v in flagged if v["verdict"] == "needs_review"]
    if untraced:
        rev.add(WARN, "untraced_lines", f"{len(untraced)} line(s) could not be traced to the resume: " + " | ".join(v["claim_text"][:60] for v in untraced[:3]))
    if review_only and not blocks:
        rev.add(WARN, "claims_need_review", f"{len(review_only)} line(s) mention skills that are not on the resume. Check them.")
    if g.get("honest_gaps"):
        rev.add(INFO, "honest_gaps", "The job asks for things the resume does not show: " + "; ".join(g["honest_gaps"][:4]))
    if blocks or bad_headers:
        rev.adjusted["unsupported_lines"] = bad_headers + [c.sentence for c in blocks]
    rev.adjusted["grounding"] = {"supported": g.get("supported"), "unsupported": g.get("unsupported"), "needs_review": g.get("needs_review")}

    if kind == "cover_letter":
        words = len(body.split())
        if not _LETTER_WORDS[0] <= words <= _LETTER_WORDS[1]:
            rev.add(WARN, "letter_length", f"The letter has {words} words. A good range is {_LETTER_WORDS[0]} to {_LETTER_WORDS[1]}.")
        company = (job.get("company") or "").strip()
        if company and company.lower() not in body.lower():
            rev.add(WARN, "company_not_named", f"The letter never names {company}. It may be a template or about the wrong employer.")
        name = (profile.get("name") or "").strip()
        if name and name.split()[0].lower() not in body.lower():
            rev.add(INFO, "no_signature", "The candidate's name does not appear in the letter.")
    return rev


_END = r"[\s.,;:]*"


def remove_unsupported(text: str, review: Review) -> tuple[str, list[str]]:
    """Delete the unsupported statements. Whole lines when the line is the statement, otherwise just the sentence.

    Returns ``(new_text, removed_statements)``.
    """
    bad = [b.strip() for b in review.adjusted.get("unsupported_lines", []) if b.strip()]
    if not bad:
        return text, []
    out_lines, removed = [], []
    for line in text.split("\n"):
        cur, s = line, line.strip()
        for b in bad:
            if not s:
                break
            if s == b or (len(b) >= 20 and s.startswith(b[:200])):
                removed.append(b)
                cur = ""
                s = ""
            elif b in cur:
                cur = re.sub(r"\s{2,}", " ", cur.replace(b, " ")).rstrip()
                removed.append(b)
        out_lines.append(cur)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()
    return cleaned, list(dict.fromkeys(removed))


MAX_REMOVED_SHARE = 0.35


def salvage(text: str, review: Review, *, kind: str, profile: dict, job: Optional[dict] = None) -> tuple[str, Review, list[str]]:
    """Try to repair a blocked draft by removing its unsupported statements, then check it again.

    A draft that loses more than a third of its statements, or most of its words, is not repaired: it is
    rejected, because what is left would no longer be the letter or resume that was written.
    Returns ``(final_text, final_review, removed)``. The final review is blocked when the repair failed.
    """
    if not review.blocked or not review.adjusted.get("unsupported_lines"):
        return text, review, []
    cleaned, removed = remove_unsupported(text, review)
    if not removed:
        return text, review, []
    before, after = len(claims_mod.sentences(text)) or 1, len(claims_mod.sentences(cleaned))
    if (before - after) / before > MAX_REMOVED_SHARE or len(cleaned.split()) < 0.5 * len(text.split()):
        rev = Review(findings=list(review.findings), adjusted=dict(review.adjusted))
        rev.add(BLOCK, "too_much_removed", f"Removing the unsupported statements would delete {before - after} of {before}. The draft should be rewritten, not patched.")
        return text, rev, []
    second = review_document(cleaned, kind=kind, profile=profile, job=job)
    if second.blocked:
        return text, second, []
    second.add(WARN, "lines_removed", f"The Reviewer removed {len(removed)} unsupported statement(s).")
    return cleaned, second, removed


# ------------------------------------------------------------------ tool output

def review_envelope(env: dict) -> Review:
    """A generic check on any tool result. Errors block, partial results warn."""
    rev = Review()
    status = env.get("status")
    if status == "error":
        err = env.get("error") or {}
        rev.add(BLOCK, f"tool_{err.get('code', 'error')}", err.get("message") or "The tool failed.")
    elif status == "partial":
        rev.add(WARN, "partial", "; ".join(env.get("warnings") or []) or "Some sources did not answer.")
    return rev
