"""Job sources. Each source returns normalized jobs or raises; the pipeline records health and falls back to cache."""
import base64
import concurrent.futures
import datetime
import functools
import html
import http.cookiejar
import json
import random
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import config
from .util import (HttpError, clean_salary_label, clean_job_type, clean_text, extract_job_sections,
                    format_schema_salary, html_to_text, http_get, http_get_json,
                    iso_or_empty, now_iso, parse_schema_job_posting)

BREAKER_FAILS = 3
BREAKER_COOLDOWN = 300

# Sources that gate applications behind paid candidate memberships, paywalls, or upsells:
PAID_OR_GATED_SOURCES = {
    "We Work Remotely": "Prompts candidates for paid WWR Pro membership ($14.95/mo) / paywalled apply links",
    "Remotive": "Prompts candidates for paid Remotive Community ($99+) membership to apply",
    "Remote OK": "Redirects candidates to remoteok.com/premium ($14.95/mo or $29.95 TopAccess paywall) to apply",
    "RemoteOK": "Redirects candidates to remoteok.com/premium ($14.95/mo or $29.95 TopAccess paywall) to apply",
}

# Ranking: 100% Free sources ALWAYS outrank paid/gated sources!
# Direct employer ATS (100) > Free Major Job Boards (88-96) > Free Feeds (70-85) > Paid/Gated Feeds (30-35)
SOURCE_RANKS = {
    "Greenhouse": 100, "Lever": 100, "Ashby": 100, "SmartRecruiters": 100, "Workable": 100,
    "Startup ATS": 100, "Y Combinator": 98,
    "LinkedIn": 96, "Indeed": 95, "ZipRecruiter": 94, "Hacker News": 92,
    "Bayt": 88, "Naukri": 88, "HelloWork": 88,
    "Himalayas": 85, "Jobicy": 82, "Arbeitnow": 80, "Adzuna": 75,
    "We Work Remotely": 35, "Remotive": 34, "Remote OK": 33, "RemoteOK": 33,
}


def is_free_to_apply(source):
    """Return True if candidate can apply 100% free without membership paywalls."""
    s = (source or "").strip()
    return s not in PAID_OR_GATED_SOURCES and s.replace(" ", "") not in PAID_OR_GATED_SOURCES


def apply_cost_note(source):
    s = (source or "").strip()
    if s in PAID_OR_GATED_SOURCES:
        return PAID_OR_GATED_SOURCES[s]
    if s.replace(" ", "") in PAID_OR_GATED_SOURCES:
        return PAID_OR_GATED_SOURCES[s.replace(" ", "")]
    if s in {"Greenhouse", "Lever", "Ashby", "SmartRecruiters", "Workable", "Startup ATS"}:
        return "100% Free Official Employer ATS"
    if s == "Y Combinator":
        return "100% Free Direct Founder Application"
    return "100% Free to apply"


def source_rank(source, tier=""):
    """Return the stable authority rank used as an explainable tie-breaker."""
    if str(tier).startswith("Direct company ATS"):
        return 100
    return SOURCE_RANKS.get(source, 50)


def source_kind(source, tier=""):
    if str(tier).startswith("Direct company ATS") or source in {"Greenhouse", "Lever", "Ashby", "SmartRecruiters", "Workable", "Startup ATS"}:
        return "Direct employer ATS"
    if source == "Y Combinator":
        return "Startup ecosystem"
    if source in {"LinkedIn", "Indeed", "ZipRecruiter", "Bayt", "Naukri", "HelloWork"}:
        return "Major job board"
    if source == "Adzuna":
        return "Job aggregator"
    s = (source or "").strip()
    if s in PAID_OR_GATED_SOURCES or s.replace(" ", "") in PAID_OR_GATED_SOURCES or "paid" in str(tier).lower() or "gated" in str(tier).lower():
        return "Paid/Gated feed"
    return "Established job feed"


def _safe_text(val):
    return clean_text(val)


def make_job(**kw):
    """Build a job dict in the shared schema. Unknown data stays empty rather than being invented."""
    desc = html_to_text(kw.get("description", ""), 12000)
    loc = _safe_text(kw.get("location"))
    title = _safe_text(kw.get("title"))
    company = _safe_text(kw.get("company"))
    mode = _safe_text(kw.get("work_mode"))
    blob = f"{title} {loc} {desc[:800]}".lower()
    if not mode:
        mode = "Remote" if re.search(r"\bremote\b|anywhere|worldwide", blob) else \
               "Hybrid" if "hybrid" in blob else "On-site" if loc else ""

    sal = clean_salary_label(kw.get("salary", ""))
    job_type = clean_job_type(kw.get("job_type", ""))

    # Auto-extract sections if description is present
    sections = extract_job_sections(desc) if desc else {}
    if not sal and sections.get("salary_text"):
        sal = clean_salary_label(sections["salary_text"]) or sections["salary_text"]
    if not job_type and sections.get("job_type"):
        job_type = clean_job_type(sections["job_type"])
    if not job_type:
        title_blob = f"{title} {desc[:400]}".lower()
        if re.search(r"\b(contract|contractor|freelance|c2c)\b", title_blob):
            job_type = "Contract"
        elif re.search(r"\b(intern|internship|stage)\b", title_blob):
            job_type = "Internship"
        elif re.search(r"\b(part[-\s]time)\b", title_blob):
            job_type = "Part-time"

    responsibilities = kw.get("responsibilities") or sections.get("responsibilities", [])
    qualifications = kw.get("qualifications") or sections.get("qualifications", [])
    pref_qualifications = kw.get("preferred_qualifications") or sections.get("preferred_qualifications", [])
    how_to_apply = kw.get("how_to_apply") or sections.get("how_to_apply", "")
    contact_email = kw.get("contact_email") or sections.get("contact_email", "")
    contact_website = kw.get("contact_website") or sections.get("contact_website", "")
    seniority = _safe_text(kw.get("seniority", ""))
    if not seniority:
        t_low = title.lower()
        if re.search(r"\b(senior|sr\.?|lead|principal|staff|architect)\b", t_low):
            seniority = "Senior"
        elif re.search(r"\b(junior|jr\.?|entry|associate|graduate)\b", t_low):
            seniority = "Junior / Entry"
        elif re.search(r"\b(intern|internship)\b", t_low):
            seniority = "Intern"

    # Check if a direct free ATS URL can be extracted from description (especially for paid/gated feeds)
    direct_apply_url = kw.get("direct_apply_url") or ""
    if not direct_apply_url and desc and not is_free_to_apply(kw.get("source")):
        ats_m = re.search(r"https?://(?:boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com|app\.join\.com|apply\.workable\.com|jobs\.smartrecruiters\.com)/[^\s\"\'<>]+", desc, re.I)
        if ats_m:
            direct_apply_url = ats_m.group(0).rstrip(".,;)")

    return {
        "id": kw["id"], "title": title, "company": company,
        "location": loc or ("Remote" if mode == "Remote" else ""), "work_mode": mode,
        "salary": sal, "job_type": job_type, "seniority": seniority,
        "url": _safe_text(kw.get("url")),
        "direct_apply_url": direct_apply_url,
        "is_free_to_apply": is_free_to_apply(kw.get("source")),
        "apply_cost_note": apply_cost_note(kw.get("source")),
        "description": desc,
        "responsibilities": responsibilities,
        "qualifications": qualifications,
        "preferred_qualifications": pref_qualifications,
        "how_to_apply": how_to_apply,
        "contact_email": contact_email,
        "contact_website": contact_website,
        "posted_at": iso_or_empty(kw.get("posted_at")),
        "source": kw.get("source", ""), "source_credit": kw.get("source_credit", kw.get("source", "")),
        "source_tier": kw.get("source_tier", ""), "source_rank": source_rank(kw.get("source", ""), kw.get("source_tier", "")),
        "source_kind": source_kind(kw.get("source", ""), kw.get("source_tier", "")), "tags": kw.get("tags", []),
        "needs_enrichment": bool(kw.get("needs_enrichment")),
        "enriched": bool(kw.get("enriched")),
    }


SYNONYM_SETS = [
    {"developer", "engineer", "dev", "swe", "sde", "programmer"},
    {"frontend", "front-end", "ui"},
    {"backend", "back-end", "api"},
    {"fullstack", "full-stack"},
]


def _expand_synonym(w):
    for group in SYNONYM_SETS:
        if w in group:
            return group
    return {w}


def _matches(query, *fields):
    """Loose client-side filter for feeds that cannot search: synonym, role-family, and token-aware."""
    if not query:
        return True
    hay = " ".join(f or "" for f in fields).lower()
    q_lower = query.lower()
    if q_lower in hay:
        return True

    # Role family expansion: Full Stack roles naturally include Backend, Frontend, and Software Engineering
    is_fullstack = "fullstack" in q_lower or "full stack" in q_lower
    if is_fullstack:
        tech_roles = {"developer", "engineer", "dev", "swe", "programmer", "software", "backend", "frontend", "fullstack", "web"}
        if any(r in hay for r in tech_roles):
            return True

    words = [w for w in re.findall(r"[a-z0-9+#.]+", q_lower) if len(w) > 1]
    if not words:
        return True
    matched_count = sum(1 for w in words if any(g in hay for g in _expand_synonym(w)))
    threshold = len(words) if len(words) <= 2 else len(words) - 1
    return matched_count >= threshold


class Source:
    name = "base"
    tier = ""
    needs_key = False

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def fetch(self, query, location):
        raise NotImplementedError

    def enrich(self, job):
        return job


# ---------------------------------------------------------------- free feeds

class Remotive(Source):
    name, tier = "Remotive", "Paid/Gated feed"

    def fetch(self, query, location):
        url = "https://remotive.com/api/remote-jobs?limit=60" + (f"&search={urllib.parse.quote(query)}" if query else "")
        data = http_get_json(url)
        return [make_job(id=f"remotive-{j['id']}", title=j.get("title"), company=j.get("company_name"),
                         location=j.get("candidate_required_location"), work_mode="Remote", salary=j.get("salary"),
                         job_type=j.get("job_type"), url=j.get("url"), description=j.get("description"),
                         posted_at=j.get("publication_date"), source=self.name,
                         source_credit="Remotive (remotive.com)", source_tier=self.tier,
                         tags=j.get("tags", [])) for j in data.get("jobs", [])]


class Jobicy(Source):
    name, tier = "Jobicy", "Free feed"

    def fetch(self, query, location):
        url = "https://jobicy.com/api/v2/remote-jobs?count=50"
        if query:
            url += f"&tag={urllib.parse.quote(query)}"
        data = http_get_json(url)
        jobs = data.get("jobs", [])
        if not jobs and query:
            data = http_get_json("https://jobicy.com/api/v2/remote-jobs?count=50&industry=engineering")
            jobs = data.get("jobs", [])
        out = []
        for j in jobs:
            if not _matches(query, j.get("jobTitle"), j.get("companyName"), j.get("jobDescription", "")[:800]):
                continue
            sal = f"{j.get('annualSalaryMin')} - {j.get('annualSalaryMax')} {j.get('salaryCurrency', '')}" if j.get("annualSalaryMin") else ""
            out.append(make_job(id=f"jobicy-{j['id']}", title=j.get("jobTitle"), company=j.get("companyName"),
                                location=j.get("jobGeo"), work_mode="Remote", salary=sal, job_type=j.get("jobType"),
                                seniority=j.get("jobLevel"), url=j.get("url"),
                                description=j.get("jobDescription"), posted_at=j.get("pubDate"), source=self.name,
                                source_credit="Jobicy Remote Jobs", source_tier=self.tier))
        return out


class Arbeitnow(Source):
    name, tier = "Arbeitnow", "Free feed"

    def fetch(self, query, location):
        data = http_get_json("https://www.arbeitnow.com/api/job-board-api")
        out = []
        for j in data.get("data", []):
            if not _matches(query, j.get("title"), " ".join(j.get("tags", [])), j.get("description", "")[:800]):
                continue
            out.append(make_job(id=f"arbeitnow-{j.get('slug')}", title=j.get("title"), company=j.get("company_name"),
                                location=j.get("location"), work_mode="Remote" if j.get("remote") else "",
                                job_type=j.get("job_types"), url=j.get("url"), description=j.get("description"),
                                posted_at=j.get("created_at"), source=self.name, source_credit="Arbeitnow",
                                source_tier=self.tier, tags=j.get("tags", [])))
        return out[:60]


class RemoteOK(Source):
    name, tier = "RemoteOK", "Paid/Gated feed"

    def fetch(self, query, location):
        data = http_get_json("https://remoteok.com/api")
        out = []
        for j in data:
            if not isinstance(j, dict) or not j.get("id") or not j.get("position"):
                continue
            if not _matches(query, j.get("position"), " ".join(j.get("tags", [])), j.get("company"), j.get("description", "")[:500]):
                continue
            sal = ""
            if j.get("salary_min") and j.get("salary_max"):
                sal = f"${j['salary_min']} - ${j['salary_max']}"
            out.append(make_job(id=f"remoteok-{j['id']}", title=j["position"], company=j.get("company"),
                                location=j.get("location") or "Remote", work_mode="Remote", salary=sal,
                                url=j.get("url") or j.get("apply_url"), description=j.get("description"),
                                posted_at=j.get("date") or j.get("epoch"), source=self.name,
                                source_credit="Via RemoteOK (remoteok.com). Link back required.", source_tier=self.tier,
                                tags=j.get("tags", [])))
        return out[:60]


class Himalayas(Source):
    name, tier = "Himalayas", "Free feed"

    def fetch(self, query, location):
        q = urllib.parse.quote(query) if query else ""
        url = "https://himalayas.app/jobs/api?limit=50" + (f"&search={q}" if q else "")
        try:
            data = http_get_json(url)
        except Exception:
            return []
        out = []
        for j in data.get("jobs", []):
            title = j.get("title") or ""
            comp = j.get("companyName") or ""
            desc = html_to_text(j.get("description") or j.get("excerpt") or "")
            cats = " ".join(j.get("categories") or [])
            if not _matches(query, title, comp, desc[:1200], cats):
                continue
            min_s, max_s = j.get("minSalary"), j.get("maxSalary")
            currency = j.get("currency", "USD") or "USD"
            sal = f"${int(min_s):,} - ${int(max_s):,} {currency}" if min_s and max_s else ""
            loc = ", ".join(j.get("locationRestrictions") or []) or "Worldwide (Remote)"
            guid = j.get("guid") or abs(hash(j.get("applicationLink", "") or title))
            out.append(make_job(id=f"himalayas-{guid}",
                                title=title, company=comp, location=loc, work_mode="Remote", salary=sal,
                                job_type=j.get("employmentType"), url=j.get("applicationLink"),
                                description=desc, posted_at=j.get("pubDate"),
                                source=self.name, source_credit="Himalayas (himalayas.app)", source_tier=self.tier))
        return out[:60]


class WeWorkRemotely(Source):
    name, tier = "We Work Remotely", "Paid/Gated feed"

    def fetch(self, query, location):
        feeds = [
            "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
            "https://weworkremotely.com/remote-jobs.rss",
        ]
        out = []
        seen_urls = set()
        for feed_url in feeds:
            try:
                xml = http_get(feed_url, retries=0)
                root = ET.fromstring(xml)
                for item in root.iter("item"):
                    link = item.findtext("link") or ""
                    if link in seen_urls:
                        continue
                    seen_urls.add(link)
                    raw_title = (item.findtext("title") or "")
                    company, _, title = raw_title.partition(": ")
                    if not title:
                        company, title = "", raw_title
                    desc = item.findtext("description") or ""
                    if not _matches(query, title, company, desc[:1200]):
                        continue
                    out.append(make_job(id="wwr-" + re.sub(r"\W+", "-", item.findtext("guid") or title)[-60:], title=title,
                                        company=company, location=item.findtext("region") or "Remote", work_mode="Remote",
                                        url=link, description=desc, posted_at=item.findtext("pubDate"),
                                        source=self.name, source_credit="We Work Remotely", source_tier=self.tier))
            except Exception:
                continue
            if len(out) >= 60:
                break
        return out[:60]


class HackerNewsHiring(Source):
    name, tier = "Hacker News", "Free feed"

    def fetch(self, query, location):
        thread = http_get_json("https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=5")
        story = next((h for h in thread.get("hits", []) if "who is hiring" in (h.get("title") or "").lower()), None)
        if not story:
            return []
        sid = story["objectID"]
        q = f"&query={urllib.parse.quote(query)}" if query else ""
        data = http_get_json(f"https://hn.algolia.com/api/v1/search?tags=comment,story_{sid}&hitsPerPage=60{q}")
        out = []
        for h in data.get("hits", []):
            if h.get("parent_id") != int(sid) and str(h.get("parent_id")) != str(sid):
                continue  # replies to postings are not postings
            text = html_to_text(h.get("comment_text", ""), 4000)
            first = text.split("\n", 1)[0]
            parts = [p.strip() for p in first.split("|")]
            if len(parts) < 2:
                continue
            company = parts[0][:80]
            title = next((p for p in parts[1:] if re.search(r"engineer|developer|designer|manager|scientist|analyst|"
                                                            r"lead|director|sre|devops|product|data|security", p, re.I)), parts[1])
            loc = next((p for p in parts[1:] if re.search(r"remote|onsite|hybrid|[A-Z][a-z]+,", p)), "")
            out.append(make_job(id=f"hn-{h['objectID']}", title=title[:120], company=company, location=loc[:80],
                                url=f"https://news.ycombinator.com/item?id={h['objectID']}", description=text,
                                posted_at=h.get("created_at"), source=self.name,
                                source_credit="Hacker News: Who is hiring", source_tier=self.tier))
        return out


class YCombinatorStartups(Source):
    name, tier = "Y Combinator", "Startup Ecosystem"

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def fetch(self, query, location):
        q = (query or "").strip().lower()
        role_path = "software-engineer"
        if any(w in q for w in ("designer", "ui/ux", "product design", "design")):
            role_path = "designer"
        elif any(w in q for w in ("product manager", "product owner", "product lead")):
            role_path = "product-manager"
        elif any(w in q for w in ("data scientist", "data science", "machine learning", "ml engineer", "ai researcher")):
            role_path = "science"

        url = f"https://www.workatastartup.com/jobs/l/{role_path}"
        try:
            page = _fetch_html_tls(url, timeout=6)
        except Exception as e:
            raise HttpError(f"Failed to fetch YC startup page: {e}")

        m = re.search(r'data-page="([^"]+)"', page) or re.search(r"data-page='([^']+)'", page)
        if not m:
            return []

        try:
            d = json.loads(html.unescape(m.group(1)))
        except Exception:
            return []

        props = d.get("props", {})
        raw_jobs = props.get("jobs", [])
        version = d.get("version")

        # Attempt to fetch page 2 via Inertia if version is available
        if version and len(raw_jobs) >= 20:
            try:
                page2_url = f"{url}?page=2"
                headers = [
                    ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
                    ("X-Inertia", "true"),
                    ("X-Inertia-Version", str(version)),
                    ("X-Requested-With", "XMLHttpRequest"),
                    ("Accept", "text/html, application/xhtml+xml")
                ]
                page2_raw = _fetch_html_tls(page2_url, headers=headers, timeout=5)
                d2 = json.loads(page2_raw)
                p2_jobs = d2.get("props", {}).get("jobs", [])
                if p2_jobs:
                    raw_jobs.extend(p2_jobs)
            except Exception:
                pass

        out = []
        seen_ids = set()
        for j in raw_jobs:
            jid = str(j.get("id") or "")
            if not jid or jid in seen_ids:
                continue
            seen_ids.add(jid)

            title = clean_text(j.get("title") or "")
            comp = clean_text(j.get("companyName") or "")
            if not title or not comp:
                continue

            if query and not _matches(query, title, comp):
                continue

            loc = clean_text(j.get("location") or "")
            sal = clean_salary_label(j.get("salary") or "")
            jt = clean_job_type(j.get("jobType") or "")
            role_type = j.get("roleType") or ""
            batch = j.get("companyBatch") or ""
            one_liner = clean_text(j.get("companyOneLiner") or "")

            desc = f"{one_liner}\n\nRole: {title}\nRole Track: {role_type}\nYC Batch: {batch}".strip() if one_liner else f"Role: {title}\nRole Track: {role_type}\nYC Batch: {batch}".strip()
            u = f"https://www.workatastartup.com/jobs/{jid}"

            job_dict = make_job(
                id=f"yc-{jid}",
                title=title,
                company=comp,
                location=loc,
                salary=sal,
                job_type=jt,
                url=u,
                description=desc,
                source=self.name,
                source_credit="Y Combinator (workatastartup.com)",
                source_tier=self.tier,
                tags=[t for t in [role_type, batch, "Y Combinator", "Startup"] if t]
            )
            job_dict["is_startup"] = True
            out.append(job_dict)

        return out

    def enrich(self, job):
        u = job.get("url") or ""
        m = re.search(r"/jobs/(\d+)", u)
        if not m:
            return job
        jid = m.group(1)
        detail_url = f"https://www.workatastartup.com/jobs/{jid}"
        try:
            page = _fetch_html_tls(detail_url, timeout=5)
            dm = re.search(r'data-page="([^"]+)"', page) or re.search(r"data-page='([^']+)'", page)
            if dm:
                d = json.loads(html.unescape(dm.group(1)))
                j_det = d.get("props", {}).get("job", {})
                desc_html = j_det.get("descriptionHtml") or ""
                if desc_html:
                    text_desc = html_to_text(desc_html, 12000)
                    if text_desc and (len(text_desc) > len(job.get("description") or "") or "Role Track:" in str(job.get("description", ""))):
                        job["description"] = text_desc
                skills_list = j_det.get("skills") or []
                if skills_list:
                    job["skills"] = list(dict.fromkeys((job.get("skills") or []) + skills_list))
                if j_det.get("sponsorsVisa"):
                    job["h1b"] = True
                job["enriched"] = True
                job["needs_enrichment"] = False
        except Exception:
            pass
        return job


class StartupATS(Source):
    name, tier = "Startup ATS", "Direct company ATS"

    # Pre-verified high-growth startups and unicorns hosted on Ashby and Greenhouse
    STARTUP_DIRECTORY = (
        ("Ashby", "ramp", "Ramp"),
        ("Ashby", "notion", "Notion"),
        ("Ashby", "plaid", "Plaid"),
        ("Ashby", "cursor", "Cursor"),
        ("Ashby", "zapier", "Zapier"),
        ("Ashby", "perplexity", "Perplexity AI"),
        ("Ashby", "vanta", "Vanta"),
        ("Ashby", "resend", "Resend"),
        ("Ashby", "elevenlabs", "ElevenLabs"),
        ("Ashby", "cognition", "Cognition"),
        ("Ashby", "harvey", "Harvey"),
        ("Ashby", "langchain", "LangChain"),
        ("Ashby", "railway", "Railway"),
        ("Ashby", "neon", "Neon"),
        ("Ashby", "replit", "Replit"),
        ("Ashby", "linear", "Linear"),
        ("Ashby", "modal", "Modal"),
        ("Ashby", "posthog", "PostHog"),
        ("Ashby", "benchling", "Benchling"),
        ("Greenhouse", "brex", "Brex"),
        ("Greenhouse", "scaleai", "Scale AI"),
        ("Greenhouse", "fivetran", "Fivetran"),
        ("Greenhouse", "gusto", "Gusto"),
    )

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def _search_company(self, board, slug, company_name, query, location):
        try:
            jobs = board.fetch_company(slug, company_name)
            out = []
            for j in jobs:
                j["is_startup"] = True
                j["source"] = self.name
                j["source_tier"] = self.tier
                if query and not _matches(query, j.get("title", ""), j.get("company", "")):
                    continue
                out.append(j)
            return out
        except Exception:
            return []

    def fetch(self, query, location):
        out = []
        boards = {
            "Ashby": Ashby(),
            "Greenhouse": Greenhouse(),
            "Lever": Lever()
        }

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(self._search_company, boards[b_type], slug, comp_name, query, location)
                for b_type, slug, comp_name in self.STARTUP_DIRECTORY
                if b_type in boards
            ]
            for f in concurrent.futures.as_completed(futures):
                try:
                    res = f.result()
                    if res:
                        out.extend(res)
                except Exception:
                    continue

        return out


class Adzuna(Source):
    name, tier, needs_key = "Adzuna", "Aggregator API", True

    def _keys(self):
        from . import db
        return (config.ADZUNA_APP_ID or db.get_setting("adzuna_app_id"), config.ADZUNA_APP_KEY or db.get_setting("adzuna_app_key"))

    def available(self):
        i, k = self._keys()
        return bool(i and k)

    def unavailable_reason(self):
        return "Add a free Adzuna app id and key (ADZUNA_APP_ID, ADZUNA_APP_KEY) to cover local and non-tech jobs."

    def fetch(self, query, location):
        i, k = self._keys()
        q = {"app_id": i, "app_key": k, "results_per_page": 40, "content-type": "application/json"}
        if query:
            q["what"] = query
        loc_str = (location or "").strip()
        if loc_str and loc_str.lower() not in ("remote", "worldwide"):
            q["where"] = loc_str

        ADZUNA_COUNTRIES = {
            "united states": "us", "usa": "us", "us": "us",
            "united kingdom": "gb", "uk": "gb", "great britain": "gb",
            "france": "fr", "germany": "de", "deutschland": "de",
            "canada": "ca", "india": "in", "poland": "pl",
            "australia": "au", "austria": "at", "belgium": "be",
            "brazil": "br", "switzerland": "ch", "italy": "it",
            "netherlands": "nl", "new zealand": "nz", "russia": "ru",
            "singapore": "sg", "south africa": "za"
        }
        target_country = config.ADZUNA_COUNTRY or "us"
        check_loc = loc_str.lower()
        if not check_loc or check_loc in ("remote", "worldwide", "any"):
            try:
                from . import db
                check_loc = (db.get_setting("user_country") or "").lower().strip()
                if not check_loc:
                    check_loc = (db.get_profile().get("location") or "").lower().strip()
            except Exception:
                pass
        for k_name, c_code in ADZUNA_COUNTRIES.items():
            if k_name in check_loc:
                target_country = c_code
                break

        data = http_get_json(f"https://api.adzuna.com/v1/api/jobs/{target_country}/search/1?" + urllib.parse.urlencode(q))
        out = []
        for j in data.get("results", []):
            sal = f"{int(j['salary_min'])} - {int(j['salary_max'])}" if j.get("salary_min") and j.get("salary_max") and not j.get("salary_is_predicted") in ("1", 1) else ""
            c_type = f"{j.get('contract_type') or ''} {j.get('contract_time') or ''}".strip()
            out.append(make_job(id=f"adzuna-{j['id']}", title=j.get("title"), company=(j.get("company") or {}).get("display_name"),
                                location=(j.get("location") or {}).get("display_name"), salary=sal, job_type=c_type, url=j.get("redirect_url"),
                                description=j.get("description"), posted_at=j.get("created"), source=self.name,
                                source_credit="Powered by Adzuna", source_tier=self.tier))
        return out


# ---------------------------------------------------------------- company ATS boards

class _Board(Source):
    tier = "Direct company ATS"
    board = ""

    def fetch_company(self, slug, company_name=""):
        raise NotImplementedError

    def fetch(self, query, location):
        return []  # boards are queried through the watchlist


class Greenhouse(_Board):
    name = board = "Greenhouse"

    def fetch_company(self, slug, company_name=""):
        data = http_get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
        name = company_name or slug.replace("-", " ").title()
        return [make_job(id=f"greenhouse-{slug}-{j['id']}", title=j.get("title"), company=name,
                         location=(j.get("location") or {}).get("name"), url=j.get("absolute_url"),
                         description=j.get("content"), posted_at=j.get("updated_at") or j.get("first_published"),
                         source=self.name, source_credit=f"{name} on Greenhouse", source_tier=self.tier)
                for j in data.get("jobs", [])]


class Lever(_Board):
    name = board = "Lever"

    def fetch_company(self, slug, company_name=""):
        data = http_get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        name = company_name or slug.replace("-", " ").title()
        out = []
        for j in data if isinstance(data, list) else []:
            cat = j.get("categories") or {}
            desc = (j.get("descriptionPlain") or j.get("description") or "") + "\n" + \
                   "\n".join(f"{l.get('text', '')}\n{html_to_text(l.get('content', ''))}" for l in j.get("lists", []))
            sal = j.get("salaryRange") or {}
            out.append(make_job(id=f"lever-{slug}-{j['id']}", title=j.get("text"), company=name,
                                location=cat.get("location") or ", ".join(cat.get("allLocations", [])),
                                work_mode=(j.get("workplaceType") or "").title().replace("Onsite", "On-site"),
                                salary=f"{sal.get('min')} - {sal.get('max')} {sal.get('currency', '')}" if sal.get("min") else "",
                                job_type=cat.get("commitment"), url=j.get("hostedUrl"), description=desc,
                                posted_at=j.get("createdAt"), source=self.name, source_credit=f"{name} on Lever",
                                source_tier=self.tier))
        return out


class Ashby(_Board):
    name = board = "Ashby"

    def fetch_company(self, slug, company_name=""):
        data = http_get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
        name = company_name or slug.replace("-", " ").title()
        out = []
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
            out.append(make_job(id=f"ashby-{slug}-{j.get('id')}", title=j.get("title"), company=name,
                                location=j.get("location"), work_mode="Remote" if j.get("isRemote") else
                                (j.get("workplaceType") or "").title(), salary=comp, job_type=j.get("employmentType"),
                                url=j.get("jobUrl"), description=j.get("descriptionHtml") or j.get("descriptionPlain"),
                                posted_at=j.get("publishedAt"), source=self.name,
                                source_credit=f"{name} on Ashby", source_tier=self.tier))
        return out


class Workable(_Board):
    name = board = "Workable"

    def fetch_company(self, slug, company_name=""):
        data = http_get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
        name = company_name or data.get("name") or slug.replace("-", " ").title()
        out = []
        for j in data.get("jobs", []):
            loc = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
            out.append(make_job(id=f"workable-{slug}-{j.get('shortcode')}", title=j.get("title"), company=name, location=loc,
                                work_mode="Remote" if j.get("telecommuting") else "", job_type=j.get("employment_type"),
                                url=j.get("url") or j.get("application_url"), description=j.get("description"),
                                posted_at=j.get("published_on") or j.get("created_at"), source=self.name,
                                source_credit=f"{name} on Workable", source_tier=self.tier))
        return out


class SmartRecruiters(_Board):
    name = board = "SmartRecruiters"

    def fetch_company(self, slug, company_name=""):
        data = http_get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
        name = company_name or slug
        out = []
        for j in data.get("content", []):
            loc = j.get("location") or {}
            out.append(make_job(id=f"sr-{slug}-{j['id']}", title=j.get("name"), company=name,
                                location=", ".join(x for x in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if x),
                                work_mode="Remote" if loc.get("remote") else "",
                                url=f"https://jobs.smartrecruiters.com/{slug}/{j['id']}", posted_at=j.get("releasedDate"),
                                source=self.name, source_credit=f"{name} on SmartRecruiters", source_tier=self.tier,
                                needs_enrichment=True, description=""))
        return out

    def enrich(self, job):
        m = re.search(r"smartrecruiters\.com/([^/]+)/([^/?#]+)", job.get("url", ""))
        if not m:
            return job
        d = http_get_json(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}")
        sec = (d.get("jobAd") or {}).get("sections") or {}
        text = "\n".join(html_to_text(sec[k].get("text", "")) for k in ("jobDescription", "qualifications", "additionalInformation") if k in sec)
        job["description"] = text
        if d.get("typeOfEmployment"):
            job["job_type"] = clean_job_type(d.get("typeOfEmployment"))
        secs = extract_job_sections(text)
        for k in ("responsibilities", "qualifications", "preferred_qualifications", "how_to_apply", "contact_email", "contact_website"):
            if secs.get(k):
                job[k] = secs[k]
        job["enriched"] = True
        job["needs_enrichment"] = False
        return job


BOARDS = {b.board.lower(): b for b in (Greenhouse(), Lever(), Ashby(), Workable(), SmartRecruiters())}


def detect_board(company_name):
    """Probe each ATS with likely slugs and return (board_type, slug) for the first hit, or None."""
    base = re.sub(r"[^a-z0-9 -]", "", company_name.lower()).strip()
    slugs = list(dict.fromkeys([base.replace(" ", ""), base.replace(" ", "-"), base.split(" ")[0]]))
    for slug in slugs:
        if not slug:
            continue
        for board in BOARDS.values():
            try:
                jobs = board.fetch_company(slug, company_name)
                if jobs:
                    return board.board.lower(), slug
            except Exception:
                continue
    return None


# ---------------------------------------------------------------- major job boards

LINKEDIN_GEO_MAP = {
    "united states": "103644278",
    "usa": "103644278",
    "us": "103644278",
    "united kingdom": "102257491",
    "uk": "102257491",
    "canada": "101174742",
    "germany": "101282230",
    "france": "105015875",
    "india": "102713980",
    "australia": "101452733",
    "netherlands": "102890719",
    "ireland": "104738515",
    "spain": "105646813",
    "italy": "103350119",
    "brazil": "106057199",
    "singapore": "102454443",
    "switzerland": "106693272",
    "sweden": "105117694",
    "poland": "105072130",
}


class LinkedInGuest(Source):
    name, tier = "LinkedIn", "Major job board"

    def __init__(self):
        super().__init__()
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cj))
        self._opener.addheaders = [
            ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
            ("Accept-Language", "en-US,en;q=0.9"),
            ("Sec-Ch-Ua", '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"'),
            ("Sec-Ch-Ua-Mobile", "?0"),
            ("Sec-Ch-Ua-Platform", '"Windows"'),
        ]
        self._tls_session = None
        self._session_lock = threading.Lock()
        self._warmed = False
        # Fire warmup asynchronously so it doesn't block the fetch budget
        self._warmup_thread = threading.Thread(target=self._warmup, daemon=True)
        self._warmup_thread.start()

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def _warmup(self):
        if not self._warmed:
            try:
                with self._opener.open("https://www.linkedin.com/jobs", timeout=4) as _:
                    pass
                self._warmed = True
            except Exception:
                pass

    def _build_query_slices(self, kw):
        """Generate narrower query variants from profile skills to multiply LinkedIn's result window.

        Instead of scraping 15 pages of one query, we scrape 2-3 pages each of many queries.
        Each query gets its own 1000-result cap from LinkedIn's API.
        """
        variants = []
        q_lower = kw.lower().strip()

        # Get profile skills for skill-based slicing
        profile_skills = []
        try:
            from . import db
            profile = db.get_profile()
            if not profile.get("_is_empty"):
                profile_skills = [s for s in (profile.get("skills") or []) if s and len(s) > 1][:8]
        except Exception:
            pass

        # Strip seniority prefixes to get the role base
        role_base = re.sub(r'\b(senior|junior|lead|staff|principal|sr\.?|jr\.?|head\s+of|chief)\b\s*',
                           '', q_lower, flags=re.I).strip()
        if not role_base:
            role_base = q_lower

        # 1. Skill + role variants (e.g. "Python developer", "React engineer")
        for skill in profile_skills[:4]:
            variant = f"{skill} {role_base}"
            if variant.lower() not in (q_lower, kw.lower()):
                variants.append(variant)

        # 2. Role family expansion
        if "full stack" in q_lower or "fullstack" in q_lower:
            suffix = re.sub(r'full[-\s]?stack\s*', '', role_base, flags=re.I).strip() or "developer"
            variants.extend([f"backend {suffix}", f"frontend {suffix}", f"software {suffix}"])
        elif "backend" in q_lower or "back-end" in q_lower:
            suffix = re.sub(r'back[-\s]?end\s*', '', role_base, flags=re.I).strip() or "developer"
            variants.extend([f"software {suffix}", f"API {suffix}"])
        elif "frontend" in q_lower or "front-end" in q_lower:
            suffix = re.sub(r'front[-\s]?end\s*', '', role_base, flags=re.I).strip() or "developer"
            variants.extend([f"web {suffix}", f"UI {suffix}"])

        # Deduplicate while preserving order
        seen = {q_lower}
        result = []
        for v in variants:
            v_clean = v.strip()
            if v_clean.lower() not in seen and len(v_clean) >= 3:
                seen.add(v_clean.lower())
                result.append(v_clean)

        return result[:6]

    def _get_page(self, url, timeout=6):
        """Fetch URL using persistent curl_cffi Chrome TLS session with automatic fallback to urllib."""
        try:
            from curl_cffi import requests as curl_requests
            with self._session_lock:
                if self._tls_session is None:
                    self._tls_session = curl_requests.Session(impersonate="chrome")
                    try:
                        self._tls_session.get("https://www.linkedin.com/jobs", timeout=4)
                    except Exception:
                        pass
                session = self._tls_session

            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            r = session.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r.text
            elif r.status_code == 429:
                # Keep the TLS session alive — 429 is a rate-limit signal, not session corruption.
                # Destroying and recreating costs a cold TLS handshake + warmup page on every retry.
                return "429"
        except Exception:
            pass

        try:
            with self._opener.open(url, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if "429" in str(e):
                return "429"
            return ""

    def fetch(self, query, location, _deadline_at=None, depth=None):
        # Warmup is now async from __init__; if it hasn't finished yet, wait briefly
        if hasattr(self, '_warmup_thread') and self._warmup_thread.is_alive():
            self._warmup_thread.join(timeout=1.0)
        out = []
        seen_ids = set()
        kw = (query or "software engineer").strip()
        loc = (location or "").strip()

        user_c = ""
        try:
            from . import db
            user_c = (db.get_setting("user_country") or "").strip()
            if not user_c:
                user_c = (db.get_profile().get("location") or "").strip()
        except Exception:
            pass

        if not loc and user_c and user_c.lower() not in ("remote", "anywhere", "worldwide"):
            loc = user_c

        is_remote = "remote" in f"{kw} {loc}".lower()
        remote_flag = "&f_WT=2" if is_remote else ""
        search_loc = loc if loc and loc.lower() not in ("remote", "anywhere") else "Worldwide"

        # Load known IDs from all 3 tables for promoted-safe early stopping and avoiding re-downloads
        known_db_ids = set()
        try:
            from . import db
            with db.session() as c:
                try:
                    for r in c.execute("SELECT job_key FROM seen_jobs WHERE job_key LIKE 'linkedin-%' LIMIT 5000").fetchall():
                        known_db_ids.add(r["job_key"].replace("linkedin-", ""))
                except Exception:
                    pass
                for tbl in ("search_jobs", "pending_search_jobs"):
                    try:
                        for r in c.execute(f"SELECT job_key, job_json FROM {tbl} WHERE job_key LIKE 'linkedin-%' OR source_names LIKE '%LinkedIn%' OR job_json LIKE '%linkedin-%' LIMIT 5000").fetchall():
                            jk = r["job_key"] or ""
                            if jk.startswith("linkedin-"):
                                known_db_ids.add(jk.replace("linkedin-", ""))
                            jj = r["job_json"] or ""
                            m = re.search(r'linkedin-(\d{6,})', jj)
                            if m:
                                known_db_ids.add(m.group(1))
                    except Exception:
                        pass
        except Exception:
            pass

        # Persistent offset cursor for deep continuation
        clean_kw_key = re.sub(r"[^a-z0-9]", "", kw.lower())
        clean_loc_key = re.sub(r"[^a-z0-9]", "", search_loc.lower())
        cursor_key = f"li_cursor_{clean_kw_key}_{clean_loc_key}"[:60]
        base_cursor = 0
        try:
            from . import db
            c_val = db.get_setting(cursor_key)
            if c_val and c_val.isdigit():
                base_cursor = int(c_val)
                if base_cursor >= 900:
                    base_cursor = 0
        except Exception:
            pass

        depth = depth or config.get_linkedin_scrape_depth()
        # Step-25 pagination: LinkedIn returns up to 25 cards per page, so step-25
        # gives zero overlap. Step-10 wasted ~60% of fetches on duplicate cards.
        if depth == "max":
            primary_offsets = [base_cursor + (i * 25) for i in range(8)]
            fresh_offsets = [0, 25, 50, 75, 100, 125]
            startup_offsets = [0, 25, 50]
            slice_offsets = [0, 25, 50]
            filter_offsets = [0, 25]
            max_out = 1500
        elif depth == "deep":
            primary_offsets = [base_cursor + (i * 25) for i in range(5)]
            fresh_offsets = [0, 25, 50, 75, 100]
            startup_offsets = [0, 25, 50]
            slice_offsets = [0, 25]
            filter_offsets = [0, 25]
            max_out = 800
        elif depth == "fast":
            primary_offsets = [0, 25]
            fresh_offsets = [0, 25]
            startup_offsets = [0]
            slice_offsets = [0]
            filter_offsets = []
            max_out = 150
        else:
            primary_offsets = [0, 25, 50, 75]
            fresh_offsets = [0, 25, 50, 75]
            startup_offsets = [0, 25]
            slice_offsets = [0, 25]
            filter_offsets = [0]
            max_out = 400

        target_places = [search_loc]
        if user_c and user_c.lower() not in ("remote", "anywhere", "worldwide") and user_c.lower() != search_loc.lower():
            target_places.append(user_c)

        # Query matrix reordered by marginal value: if the budget cuts execution
        # short, the highest-unique-yield queries will have already run.
        queries = []

        # Build synonym and slices upfront so we can weave them in priority order
        q_lower = kw.lower()
        syn = ""
        if "developer" in q_lower:
            syn = re.sub(r"\bdeveloper\b", "engineer", kw, flags=re.I)
        elif "engineer" in q_lower:
            syn = re.sub(r"\bengineer\b", "developer", kw, flags=re.I)
        elif "programmer" in q_lower:
            syn = re.sub(r"\bprogrammer\b", "engineer", kw, flags=re.I)
        else:
            syn = f"{kw} developer"
        query_slices = self._build_query_slices(kw)

        # Priority 1: Ultra-fresh 24h stream (today's postings — highest value, least overlap with DB)
        if depth != "fast":
            for off in [0, 25]:
                queries.append((kw, search_loc, off, "&sortBy=DD&f_TPR=r86400", False, True))

        # Priority 2: Fresh 7-day chronological (page 0 only — most new content per fetch)
        for pl in target_places:
            queries.append((kw, pl, 0, "&sortBy=DD&f_TPR=r604800", False, True))

        # Priority 3: Primary relevance page 0 (LinkedIn's best-match ranking)
        for pl in target_places:
            queries.append((kw, pl, 0, "", False, False))

        # Priority 4: Skill-slice variants (unique queries = unique result windows)
        for sl in query_slices:
            for pl in target_places[:1]:
                queries.append((sl, pl, 0, "", False, False))

        # Priority 5: Synonym variant page 0
        if syn and syn != kw:
            queries.append((syn, search_loc, 0, "", False, False))

        # Priority 6: Remote worldwide variant
        if search_loc == "Worldwide" and not remote_flag:
            queries.append((kw, "Worldwide", 0, "&f_WT=2", False, False))

        # Priority 7: Startup roles page 0
        for pl in target_places:
            queries.append((f"{kw} startup", pl, 0, "", True, False))

        # Priority 8: Deeper pagination (pages 1+ of the highest-value streams)
        for pl in target_places:
            for off in primary_offsets[1:]:
                queries.append((kw, pl, off, "", False, False))
            for off in fresh_offsets[1:]:
                queries.append((kw, pl, off, "&sortBy=DD&f_TPR=r604800", False, True))
            for off in startup_offsets[1:]:
                queries.append((f"{kw} startup", pl, off, "", True, False))

        # Priority 9: Deeper pages for slices and synonyms
        for sl in query_slices:
            for pl in target_places[:1]:
                for off in slice_offsets[1:]:
                    queries.append((sl, pl, off, "", False, False))
        if syn and syn != kw:
            if depth in ("deep", "max"):
                queries.append((syn, search_loc, 25, "", False, False))
        if search_loc == "Worldwide" and not remote_flag:
            if depth in ("deep", "max"):
                queries.append((kw, "Worldwide", 25, "&f_WT=2", False, False))

        # Priority 10: Experience level filter variants (lowest marginal value)
        if filter_offsets:
            for ef in ("&f_E=4", "&f_E=3"):
                for off in filter_offsets:
                    queries.append((kw, search_loc, off, ef, False, False))

        # Parallel page fetching with rate limiting and 429 retry
        _last_req = [0.0]
        _rlock = threading.Lock()

        def _throttled_fetch(query_tuple):
            """Fetch one LinkedIn page with rate limiting and 429 retry."""
            term, place, start_idx, extra_params, is_startup_term, is_fresh_stream = query_tuple

            geo_id = LINKEDIN_GEO_MAP.get(str(place).lower().strip(), "")
            geo_param = f"&geoId={geo_id}" if geo_id else ""
            url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                   f"keywords={urllib.parse.quote(term)}&location={urllib.parse.quote(place)}"
                   f"{geo_param}{remote_flag}{extra_params}&start={start_idx}")

            # Rate limiting: minimum gap between request starts across all workers
            with _rlock:
                gap = random.uniform(0.14, 0.30)
                wait = max(0, _last_req[0] + gap - time.time())
                if wait > 0:
                    time.sleep(wait)
                _last_req[0] = time.time()

            page = self._get_page(url, timeout=5)

            # 429 retry: recover the page instead of discarding it
            if page == "429":
                time.sleep(random.uniform(1.5, 3.0))
                page = self._get_page(url, timeout=5)
                if page == "429":
                    time.sleep(random.uniform(2.0, 5.0))
                    page = self._get_page(url, timeout=5)
                    if page == "429" or not page:
                        return []

            if not page:
                return []

            cards = re.findall(r"<li>(.*?)</li>", page, re.S)
            if not cards:
                return []

            # Promoted-safe early stopping on chronological fresh stream:
            # If deeper than start=0 and >= 80% of cards are already known, skip older pages
            if is_fresh_stream and start_idx > 0 and known_db_ids and len(cards) >= 5:
                card_jids = [m.group(1) for m in re.finditer(r'base-card__full-link[^>]*href="[^"]*?(\d{6,})', page)]
                if card_jids:
                    known_hits = sum(1 for cid in card_jids if cid in known_db_ids)
                    if known_hits / len(card_jids) >= 0.8:
                        return []

            results = []
            for card in cards:
                t = re.search(r'base-search-card__title[^>]*>\s*([^<]+)', card)
                c = re.search(r'base-search-card__subtitle[^>]*>\s*(?:<a[^>]*>\s*)?([^<]+)', card)
                l = re.search(r'job-search-card__location[^>]*>\s*([^<]+)', card)
                u = re.search(r'base-card__full-link[^>]*href="([^"?]+)', card)
                d = re.search(r'datetime="([^"]+)"', card)
                sal_m = re.search(r'job-search-card__salary-info[^>]*>\s*([^<]+)', card)

                if not (t and c and u):
                    continue

                jid_match = re.search(r"(\d{6,})", u.group(1))
                jid = jid_match.group(1) if jid_match else str(abs(hash(u.group(1))))

                title = html.unescape(t.group(1).strip())
                comp = html.unescape(c.group(1).strip())
                place_str = html.unescape(l.group(1).strip()) if l else ""
                salary = html.unescape(sal_m.group(1).strip()) if sal_m else ""

                tags = []
                if is_startup_term or "startup" in card.lower() or "early-stage" in card.lower():
                    tags.append("startup")

                results.append((jid, make_job(
                    id=f"linkedin-{jid}",
                    title=title,
                    company=comp,
                    location=place_str,
                    salary=salary,
                    url=u.group(1),
                    posted_at=d.group(1) if d else "",
                    description="",
                    tags=tags,
                    needs_enrichment=True,
                    source=self.name,
                    source_credit="LinkedIn public listing",
                    source_tier=self.tier
                )))
            return results

        n_workers = 3 if depth in ("deep", "max") else 2
        batch_size = n_workers * 3
        # Use the pipeline-provided deadline if available, otherwise no inner wall.
        # The pipeline's SEARCH_DEADLINE_SECONDS is the single timeout gate.
        fetch_deadline = _deadline_at or (time.time() + 120.0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
            qi = 0
            while qi < len(queries) and len(out) < max_out:
                if time.time() > fetch_deadline:
                    break

                batch = queries[qi:qi + batch_size]
                qi += batch_size

                futs = [pool.submit(_throttled_fetch, q) for q in batch]
                try:
                    for f in concurrent.futures.as_completed(futs, timeout=8.0):
                        try:
                            for jid, job in f.result():
                                if jid not in seen_ids and jid not in known_db_ids and len(out) < max_out:
                                    seen_ids.add(jid)
                                    out.append(job)
                        except Exception:
                            continue
                except concurrent.futures.TimeoutError:
                    pass

        # Advance cursor for deep searches
        if depth in ("deep", "max") and primary_offsets:
            try:
                from . import db
                next_cur = primary_offsets[-1] + 25
                if next_cur >= 900:
                    next_cur = 0
                db.set_setting(cursor_key, str(next_cur))
            except Exception:
                pass

        return out[:max_out]

    def enrich(self, job):
        m = re.search(r"(\d{6,})", job.get("id", ""))
        if not m:
            return job
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}"
        try:
            page = self._get_page(detail_url, timeout=6)
            if not page or page == "429":
                page = http_get(detail_url, headers=headers, retries=0)
            d = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.S)
            if d:
                full_desc = html_to_text(d.group(1))
                job["description"] = full_desc
                secs = extract_job_sections(full_desc)
                for k, v in secs.items():
                    if v and not job.get(k):
                        job[k] = v

            # Extract criteria items (Employment type, Seniority level, Industries)
            criteria = re.findall(r'<li[^>]*class="description__job-criteria-item"[^>]*>(.*?)</li>', page, re.S)
            for c in criteria:
                hdr = re.search(r'<h3[^>]*>(.*?)</h3>', c, re.S)
                val = re.search(r'<span[^>]*class="description__job-criteria-text[^"]*"[^>]*>(.*?)</span>', c, re.S)
                if hdr and val:
                    h_text = html_to_text(hdr.group(1)).lower()
                    v_text = html_to_text(val.group(1)).strip()
                    if "employment type" in h_text:
                        job["job_type"] = clean_job_type(v_text)
                    elif "seniority" in h_text:
                        job["seniority"] = v_text
                    elif "industries" in h_text and v_text:
                        job.setdefault("tags", []).append(v_text)

            # Check for ld+json if salary missing
            if not job.get("salary"):
                parsed = parse_schema_job_posting(page)
                if parsed.get("salary"):
                    job["salary"] = parsed["salary"]
                if parsed.get("job_type") and not job.get("job_type"):
                    job["job_type"] = parsed["job_type"]

            job["enriched"] = True
            job["needs_enrichment"] = False
        except Exception:
            pass
        return job

    def fetch_incremental(self, query, location):
        """Lightweight adaptive scrape for periodic background updates.

        1. Checks Page 1 of the real-time fresh stream (sortBy=DD&f_TPR=r86400).
        2. Detects if Page 1 is identical to last time (all cards known / top ID unchanged).
        3. If NEW jobs exist: collects them, advances to page 2 if heavily populated.
        4. If Page 1 is UNCHANGED (stagnant): avoids redundant calls on the same query
           and pivots to rotated profile skill slices or an advancing backfill cursor
           so every run discovers new unseen opportunities for the user.
        """
        # Warmup is async from __init__; wait briefly if still running
        if hasattr(self, '_warmup_thread') and self._warmup_thread.is_alive():
            self._warmup_thread.join(timeout=1.0)
        kw = (query or "software engineer").strip()
        loc = (location or "").strip()

        user_c = ""
        try:
            from . import db
            user_c = (db.get_setting("user_country") or "").strip()
            if not user_c:
                user_c = (db.get_profile().get("location") or "").strip()
        except Exception:
            pass

        if not loc and user_c and user_c.lower() not in ("remote", "anywhere", "worldwide"):
            loc = user_c

        is_remote = "remote" in f"{kw} {loc}".lower()
        remote_flag = "&f_WT=2" if is_remote else ""
        search_loc = loc if loc and loc.lower() not in ("remote", "anywhere") else "Worldwide"

        # Load known IDs and canonical keys to skip already-seen/stored jobs from ANY source
        known_ids = set()
        known_canonical_keys = set()
        try:
            from . import db, dedup
            with db.session() as c:
                # Direct LinkedIn IDs
                for tbl in ("search_jobs", "seen_jobs", "pending_search_jobs"):
                    try:
                        rows = c.execute(f"SELECT job_key FROM {tbl} WHERE job_key LIKE 'linkedin-%' LIMIT 5000").fetchall()
                        known_ids.update(r["job_key"].replace("linkedin-", "") for r in rows)
                    except Exception:
                        pass
                
                # Canonical company|title deduplication keys across ALL existing jobs
                for tbl in ("search_jobs", "pending_search_jobs", "seen_jobs"):
                    try:
                        rows = c.execute(f"SELECT job_key, title, company FROM {tbl} LIMIT 10000").fetchall()
                        for r in rows:
                            if r["job_key"]:
                                known_canonical_keys.add(r["job_key"])
                            if r["company"] and r["title"]:
                                ck = dedup.job_key({"company": r["company"], "title": r["title"]})
                                known_canonical_keys.add(ck)
                    except Exception:
                        pass
        except Exception:
            pass

        out = []
        seen_ids = set()

        def _parse_cards(page_text):
            parsed = []
            if not page_text or page_text == "429":
                return parsed
            try:
                from . import dedup
            except Exception:
                dedup = None

            cards = re.findall(r"<li>(.*?)</li>", page_text, re.S)
            for card in cards:
                t = re.search(r'base-search-card__title[^>]*>\s*([^<]+)', card)
                c = re.search(r'base-search-card__subtitle[^>]*>\s*(?:<a[^>]*>\s*)?([^<]+)', card)
                u = re.search(r'base-card__full-link[^>]*href="([^"?]+)', card)
                d = re.search(r'datetime="([^"]+)"', card)
                l = re.search(r'job-search-card__location[^>]*>\s*([^<]+)', card)
                sal_m = re.search(r'job-search-card__salary-info[^>]*>\s*([^<]+)', card)

                if not (t and c and u):
                    continue

                jid_match = re.search(r"(\d{6,})", u.group(1))
                jid = jid_match.group(1) if jid_match else str(abs(hash(u.group(1))))
                raw_title = html.unescape(t.group(1).strip())
                raw_company = html.unescape(c.group(1).strip())
                canon_k = dedup.job_key({"company": raw_company, "title": raw_title}) if dedup else f"li-{jid}"

                parsed.append({
                    "jid": jid,
                    "canon_key": canon_k,
                    "title": raw_title,
                    "company": raw_company,
                    "location": html.unescape(l.group(1).strip()) if l else "",
                    "salary": html.unescape(sal_m.group(1).strip()) if sal_m else "",
                    "url": u.group(1),
                    "posted_at": d.group(1) if d else "",
                })
            return parsed

        def _fetch_url(term, place, start_idx, extra):
            geo_id = LINKEDIN_GEO_MAP.get(str(place).lower().strip(), "")
            geo_param = f"&geoId={geo_id}" if geo_id else ""
            url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                   f"keywords={urllib.parse.quote(term)}&location={urllib.parse.quote(place)}"
                   f"{geo_param}{remote_flag}{extra}&start={start_idx}")
            page = self._get_page(url, timeout=5)
            if page == "429":
                time.sleep(random.uniform(1.5, 3.0))
                page = self._get_page(url, timeout=5)
                if page == "429" or not page:
                    return ""
            return page or ""

        # Step 1: Probe Page 1 of 24h ultra-fresh stream
        p1_page = _fetch_url(kw, search_loc, 0, "&sortBy=DD&f_TPR=r86400")
        p1_items = _parse_cards(p1_page)

        # Check fingerprint against stored top job ID
        last_top_id = ""
        try:
            from . import db
            last_top_id = db.get_setting("li_radar_last_top_id") or ""
        except Exception:
            pass

        top_id = p1_items[0]["jid"] if p1_items else ""
        new_in_p1 = [it for it in p1_items if it["jid"] not in known_ids and it["jid"] not in seen_ids and it.get("canon_key") not in known_canonical_keys]
        is_stagnant = len(p1_items) > 0 and (top_id == last_top_id or len(new_in_p1) == 0)

        activity_msg = ""
        if not is_stagnant and new_in_p1:
            # Page 1 has genuine new postings! Collect them immediately
            if top_id:
                try:
                    from . import db
                    db.set_setting("li_radar_last_top_id", top_id)
                except Exception:
                    pass

            for it in new_in_p1:
                seen_ids.add(it["jid"])
                if it.get("canon_key"):
                    known_canonical_keys.add(it["canon_key"])
                out.append(make_job(
                    id=f"linkedin-{it['jid']}",
                    job_key=it.get("canon_key"),
                    title=it["title"],
                    company=it["company"],
                    location=it["location"],
                    salary=it["salary"],
                    url=it["url"],
                    posted_at=it["posted_at"],
                    description="",
                    needs_enrichment=True,
                    source=self.name,
                    source_credit="LinkedIn public listing",
                    source_tier=self.tier
                ))

            activity_msg = f"Found {len(new_in_p1)} fresh 24h posting{'s' if len(new_in_p1) != 1 else ''} for '{kw}'"

            # If page 1 was full of new jobs, check page 2 for overflow
            if len(new_in_p1) >= 8 and len(out) < 60:
                time.sleep(random.uniform(0.3, 0.6))
                p2_page = _fetch_url(kw, search_loc, 25, "&sortBy=DD&f_TPR=r86400")
                for it in _parse_cards(p2_page):
                    if it["jid"] not in known_ids and it["jid"] not in seen_ids and it.get("canon_key") not in known_canonical_keys and len(out) < 80:
                        seen_ids.add(it["jid"])
                        if it.get("canon_key"):
                            known_canonical_keys.add(it["canon_key"])
                        out.append(make_job(
                            id=f"linkedin-{it['jid']}",
                            job_key=it.get("canon_key"),
                            title=it["title"],
                            company=it["company"],
                            location=it["location"],
                            salary=it["salary"],
                            url=it["url"],
                            posted_at=it["posted_at"],
                            description="",
                            needs_enrichment=True,
                            source=self.name,
                            source_credit="LinkedIn public listing",
                            source_tier=self.tier
                        ))
        else:
            # Page 1 is UNCHANGED or empty: Avoid redundant calls on this query!
            # Adaptive Pivot 1: Check rotated skill slice
            slices = self._build_query_slices(kw)
            if slices:
                slice_idx = 0
                try:
                    from . import db
                    slice_idx = int(db.get_setting("li_radar_slice_idx") or 0)
                except Exception:
                    pass

                rot_kw = slices[slice_idx % len(slices)]
                try:
                    from . import db
                    db.set_setting("li_radar_slice_idx", str((slice_idx + 1) % len(slices)))
                except Exception:
                    pass

                time.sleep(random.uniform(0.3, 0.6))
                rot_page = _fetch_url(rot_kw, search_loc, 0, "&sortBy=DD&f_TPR=r86400")
                for it in _parse_cards(rot_page):
                    if it["jid"] not in known_ids and it["jid"] not in seen_ids and it.get("canon_key") not in known_canonical_keys and len(out) < 50:
                        seen_ids.add(it["jid"])
                        if it.get("canon_key"):
                            known_canonical_keys.add(it["canon_key"])
                        out.append(make_job(
                            id=f"linkedin-{it['jid']}",
                            job_key=it.get("canon_key"),
                            title=it["title"],
                            company=it["company"],
                            location=it["location"],
                            salary=it["salary"],
                            url=it["url"],
                            posted_at=it["posted_at"],
                            description="",
                            needs_enrichment=True,
                            source=self.name,
                            source_credit="LinkedIn public listing",
                            source_tier=self.tier
                        ))
                if out:
                    activity_msg = f"Page 1 unchanged for '{kw}' · Rotated to '{rot_kw}' ({len(out)} new)"

            # Adaptive Pivot 2: If rotated slice had 0 new jobs, run deep catalog backfill
            if not out:
                backfill_offset = 25
                try:
                    from . import db
                    backfill_offset = int(db.get_setting("li_radar_backfill_offset") or 25)
                except Exception:
                    pass

                time.sleep(random.uniform(0.3, 0.6))
                bf_page = _fetch_url(kw, search_loc, backfill_offset, "&sortBy=DD&f_TPR=r604800")
                bf_items = _parse_cards(bf_page)
                for it in bf_items:
                    if it["jid"] not in known_ids and it["jid"] not in seen_ids and it.get("canon_key") not in known_canonical_keys and len(out) < 50:
                        seen_ids.add(it["jid"])
                        if it.get("canon_key"):
                            known_canonical_keys.add(it["canon_key"])
                        out.append(make_job(
                            id=f"linkedin-{it['jid']}",
                            job_key=it.get("canon_key"),
                            title=it["title"],
                            company=it["company"],
                            location=it["location"],
                            salary=it["salary"],
                            url=it["url"],
                            posted_at=it["posted_at"],
                            description="",
                            needs_enrichment=True,
                            source=self.name,
                            source_credit="LinkedIn public listing",
                            source_tier=self.tier
                        ))

                next_offset = backfill_offset + 25
                # Extend backfill to LinkedIn's ~1000 result cap (offset 900 at step-25)
                if next_offset > 900 or len(bf_items) == 0:
                    next_offset = 25
                try:
                    from . import db
                    db.set_setting("li_radar_backfill_offset", str(next_offset))
                except Exception:
                    pass

                if out:
                    activity_msg = f"Page 1 unchanged · Unseen catalog page {backfill_offset // 25 + 1} ({len(out)} new)"
                else:
                    activity_msg = f"Checked 24h & catalog · No new postings at this moment"

        self._last_incremental_activity = activity_msg
        return out


def _fetch_html_tls(url, headers=None, impersonate="chrome", timeout=8):
    """Fetch using curl_cffi for browser TLS impersonation (bypasses Cloudflare/Akamai bot walls), with fallback to http_get."""
    try:
        from curl_cffi import requests as curl_requests
        r = curl_requests.get(url, impersonate=impersonate, headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return http_get(url, headers=headers, timeout=timeout)


NK_KEY = "MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBALrlQ+djR0RjJwBF1xuisHmdFv334MImK6LgzJhmLhN7B5yuEyaKoasgXQk3+OQglsOaBxEJ0j5PcTL3nbOvt80CAwEAAQ=="


def _read_der(data: bytes, i: int):
    length = data[i + 1]
    i += 2
    if length & 0x80:
        size = length & 0x7F
        length = int.from_bytes(data[i : i + size], "big")
        i += size
    return data[i : i + length], i + length


@functools.cache
def _naukri_pubkey():
    key, _ = _read_der(base64.b64decode(NK_KEY), 0)
    _, i = _read_der(key, 0)
    bit_string, _ = _read_der(key, i)
    rsa_key, _ = _read_der(bit_string[1:], 0)
    modulus, i = _read_der(rsa_key, 0)
    exponent, _ = _read_der(rsa_key, i)
    return int.from_bytes(modulus, "big"), int.from_bytes(exponent, "big")


def _generate_nkparam(page="srp"):
    modulus, exponent = _naukri_pubkey()
    size = (modulus.bit_length() + 7) // 8
    message = f"v0|{int(time.time() * 1000)}|121_{page}".encode()
    padding = bytes(secrets.randbelow(255) + 1 for _ in range(size - 3 - len(message)))
    block = b"\x00\x02" + padding + b"\x00" + message
    cipher = pow(int.from_bytes(block, "big"), exponent, modulus)
    return base64.b64encode(cipher.to_bytes(size, "big")).decode()


class Indeed(Source):
    name, tier = "Indeed", "Major job board"

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    @staticmethod
    def _field(fragment, patterns, limit=500):
        for pattern in patterns:
            m = re.search(pattern, fragment, re.I | re.S)
            if m:
                value = html_to_text(html.unescape(m.group(1)), limit)
                if value:
                    return value
        return ""

    def fetch(self, query, location):
        """Native Indeed public scraper using TLS impersonation to bypass Cloudflare."""
        params = {"q": query or "software engineer", "l": location or "", "fromage": "14"}
        url = "https://www.indeed.com/jobs?" + urllib.parse.urlencode(params)
        try:
            page = _fetch_html_tls(url, impersonate="chrome")
        except Exception:
            return []
        out = []
        for match in re.finditer(r'data-jk=["\']([^"\']+)["\']', page, re.I):
            start, end = max(0, match.start() - 1500), min(len(page), match.end() + 6500)
            card = page[start:end]
            title = self._field(card, [r'class=["\'][^"\']*jobTitle[^"\']*["\'][^>]*>.*?<span[^>]*>(.*?)</span>',
                                       r'class=["\'][^"\']*jobTitle[^"\']*["\'][^>]*>.*?>(.*?)</a>'], 180)
            company = self._field(card, [r'data-testid=["\']company-name["\'][^>]*>(.*?)</',
                                         r'class=["\'][^"\']*companyName[^"\']*["\'][^>]*>(.*?)</'], 180)
            loc = self._field(card, [r'data-testid=["\']text-location["\'][^>]*>(.*?)</',
                                    r'class=["\'][^"\']*companyLocation[^"\']*["\'][^>]*>(.*?)</'], 180)
            desc = self._field(card, [r'class=["\'][^"\']*job-snippet[^"\']*["\'][^>]*>(.*?)</'], 3000)
            sal = self._field(card, [r'class=["\'][^"\']*(?:salary-snippet-container|metadata\s+salary-snippet|css-55yg5b)[^"\']*["\'][^>]*>(.*?)</',
                                     r'data-testid=["\']attribute_snippet_testid["\'][^>]*>(\$[^<]+)</',
                                     r'class=["\'][^"\']*jobMetaDataGroup[^"\']*["\'][^>]*>.*?(\$[\d,\.]+[^\n<]+)'], 100)
            job_type = self._field(card, [r'data-testid=["\']attribute_snippet_testid["\'][^>]*>(Full-time|Part-time|Contract|Internship|Temporary)</'], 50)
            if not title or not company:
                continue
            jid = match.group(1)
            out.append(make_job(id=f"indeed-{jid}", title=title, company=company, location=loc,
                                salary=sal, job_type=job_type,
                                work_mode="Remote" if "remote" in f"{loc} {desc}".lower() else "",
                                url=f"https://www.indeed.com/viewjob?jk={urllib.parse.quote(jid)}",
                                description=desc, source=self.name, source_credit="Indeed public results",
                                source_tier=self.tier, needs_enrichment=True))
        return out

    def enrich(self, job):
        jid = ""
        m = re.search(r"jk=([a-zA-Z0-9_-]+)", job.get("url", ""))
        if m:
            jid = m.group(1)
        elif job.get("id", "").startswith("indeed-"):
            jid = job["id"].replace("indeed-", "")
        if not jid:
            return job

        detail_url = f"https://www.indeed.com/m/viewjob?jk={urllib.parse.quote(jid)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            page = _fetch_html_tls(detail_url, impersonate="chrome", headers=headers)
            parsed = parse_schema_job_posting(page)
            if parsed and parsed.get("description"):
                if parsed.get("salary"):
                    job["salary"] = parsed["salary"]
                if parsed.get("job_type"):
                    job["job_type"] = parsed["job_type"]
                job["description"] = parsed["description"]
                for sec_key in ("responsibilities", "qualifications", "preferred_qualifications", "how_to_apply", "contact_email", "contact_website"):
                    if parsed.get(sec_key):
                        job[sec_key] = parsed[sec_key]
                job["enriched"] = True
                job["needs_enrichment"] = False
            else:
                idx = page.find('id="jobDescriptionText"')
                if idx != -1:
                    m_desc = re.search(r'id=[\'"]jobDescriptionText[\'"][^>]*>(.*?)</div>\s*<(?:div|footer)', page, re.S)
                    if m_desc:
                        full_desc = html_to_text(m_desc.group(1))
                        if len(full_desc) > len(job.get("description", "")):
                            job["description"] = full_desc
                            secs = extract_job_sections(full_desc)
                            for k, v in secs.items():
                                if v and not job.get(k):
                                    job[k] = v
                            job["enriched"] = True
                            job["needs_enrichment"] = False
        except Exception:
            pass
        return job


class ZipRecruiter(Source):
    name, tier = "ZipRecruiter", "Major job board"
    default_location = "US"

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def fetch(self, query, location):
        q = urllib.parse.quote(query or "software engineer")
        loc = urllib.parse.quote(location or self.default_location)
        url = f"https://www.ziprecruiter.com/jobs-search?search={q}&location={loc}"
        try:
            page = _fetch_html_tls(url, impersonate="safari")
            chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', page)
            full = "".join(json.loads(c) for c in chunks)
            idx = full.find('"jobKeysMap":')
            if idx == -1:
                return []
            sub = full[idx + len('"jobKeysMap":'):]
            data = json.JSONDecoder().raw_decode(sub)[0]
            jobs = []
            for jid, it in data.items():
                title = it.get("title") or ""
                comp = it.get("company")
                if isinstance(comp, dict):
                    comp = comp.get("name")
                loc_obj = it.get("location")
                loc_str = loc_obj.get("displayName") if isinstance(loc_obj, dict) else str(loc_obj or "")
                u = it.get("rawCanonicalZipJobPageUrl") or it.get("jobRedirectPageUrl") or f"/jobs/{jid}"
                if not u.startswith("http"):
                    u = f"https://www.ziprecruiter.com{u}"
                pay = it.get("pay")
                sal = ""
                if isinstance(pay, dict):
                    if pay.get("minAnnual") and pay.get("maxAnnual"):
                        sal = f"${int(pay['minAnnual']):,} - ${int(pay['maxAnnual']):,}"
                    elif pay.get("min") and pay.get("max"):
                        sal = f"${int(pay['min']):,} - ${int(pay['max']):,}"
                emp_type = clean_job_type(it.get("employmentType") or (pay.get("employmentType") if isinstance(pay, dict) else ""))
                desc = it.get("shortDescription") or ""
                jobs.append(make_job(
                    id=f"zip-{jid}",
                    title=str(title).strip(),
                    company=str(comp or "").strip(),
                    location=str(loc_str or "").strip(),
                    salary=sal,
                    job_type=emp_type,
                    url=u,
                    description=desc,
                    source=self.name,
                    source_credit="ZipRecruiter public listing",
                    source_tier=self.tier,
                    needs_enrichment=True
                ))
            return jobs
        except Exception:
            return []

    def enrich(self, job):
        url = job.get("url")
        if not url or not url.startswith("http"):
            return job
        try:
            page = _fetch_html_tls(url, impersonate="safari")
            parsed = parse_schema_job_posting(page)
            if parsed and parsed.get("description"):
                if parsed.get("salary") and not job.get("salary"):
                    job["salary"] = parsed["salary"]
                if parsed.get("job_type"):
                    job["job_type"] = parsed["job_type"]
                if len(parsed["description"]) > len(job.get("description", "")):
                    job["description"] = parsed["description"]
                for sec_key in ("responsibilities", "qualifications", "preferred_qualifications", "how_to_apply", "contact_email", "contact_website"):
                    if parsed.get(sec_key):
                        job[sec_key] = parsed[sec_key]
                job["enriched"] = True
                job["needs_enrichment"] = False
            else:
                m = re.search(r'class=[\'"][^\'"]*job_description[^\'"]*[\'"][^>]*>(.*?)</div>', page, re.S)
                if m:
                    full_desc = html_to_text(m.group(1))
                    if len(full_desc) > len(job.get("description", "")):
                        job["description"] = full_desc
                        secs = extract_job_sections(full_desc)
                        for k, v in secs.items():
                            if v and not job.get(k):
                                job[k] = v
                        job["enriched"] = True
                        job["needs_enrichment"] = False
        except Exception:
            pass
        return job


class Bayt(Source):
    name, tier = "Bayt", "Major job board"

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def fetch(self, query, location):
        slug = urllib.parse.quote("-".join((query or "software engineer").lower().split()))
        loc_lower = (location or "").lower().strip()

        if not loc_lower or loc_lower in ("remote", "anywhere", "worldwide"):
            try:
                from . import db
                uc = (db.get_setting("user_country") or "").lower().strip()
                if not uc:
                    uc = (db.get_profile().get("location") or "").lower().strip()
                if uc:
                    loc_lower = uc
            except Exception:
                pass

        BAYT_COUNTRIES = {
            "tunisia": "tunisia", "tunis": "tunisia", "tunisie": "tunisia",
            "morocco": "morocco", "maroc": "morocco", "casablanca": "morocco",
            "algeria": "algeria", "algérie": "algeria", "alger": "algeria",
            "egypt": "egypt", "cairo": "egypt",
            "saudi": "saudi-arabia", "saudi arabia": "saudi-arabia", "ksa": "saudi-arabia", "riyadh": "saudi-arabia",
            "uae": "uae", "dubai": "uae", "abu dhabi": "uae",
            "qatar": "qatar", "doha": "qatar",
            "kuwait": "kuwait",
            "bahrain": "bahrain",
            "oman": "oman", "muscat": "oman",
            "jordan": "jordan", "amman": "jordan",
            "lebanon": "lebanon", "beirut": "lebanon",
            "iraq": "iraq",
        }
        country_slug = "international"
        for k, v in BAYT_COUNTRIES.items():
            if k in loc_lower:
                country_slug = v
                break

        urls = [
            f"https://www.bayt.com/en/{country_slug}/jobs/{slug}-jobs/",
            f"https://www.bayt.com/en/{country_slug}/jobs/{slug}-jobs/?page=2",
        ]
        if country_slug != "international":
            urls.extend([
                f"https://www.bayt.com/en/international/jobs/{slug}-jobs/",
                f"https://www.bayt.com/en/international/jobs/{slug}-jobs/?page=2",
            ])

        jobs = []
        seen = set()
        for url in urls:
            try:
                page = _fetch_html_tls(url, impersonate="chrome")
                cards = re.findall(r'<li[^>]*data-js-job[^>]*>(.*?)</li>', page, re.S)
                for card in cards:
                    t = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', card)
                    c = re.search(r'job-company-location-wrapper.*?<a[^>]*>([^<]+)</a>', card, re.S)
                    l = re.search(r'jb-label-location.*?<span>([^<]+)</span>', card, re.S)
                    d = re.search(r'data-automation-jobactivedate="([^"]*)"', card)
                    desc = re.search(r'class="jb-descr[^"]*"[^>]*>(.*?)</div>', card, re.S)
                    sal = re.search(r'data-automation-jobsalary="([^"]*)"', card)
                    if not t:
                        continue
                    link = "https://www.bayt.com" + t.group(1).split("?")[0]
                    title = html.unescape(t.group(2).strip())
                    comp = html.unescape((c.group(1) if c else "").strip())
                    loc = html.unescape((l.group(1) if l else "").strip())
                    jid = str(abs(hash(link)))
                    if jid in seen:
                        continue
                    seen.add(jid)
                    jobs.append(make_job(
                        id=f"bayt-{jid}",
                        title=title,
                        company=comp,
                        location=loc or (country_slug.replace("-", " ").title() if country_slug != "international" else ""),
                        url=link,
                        posted_at=d.group(1) if d else "",
                        salary=sal.group(1) if sal else "",
                        description=html.unescape(re.sub(r'<[^>]+>', '', desc.group(1)).strip()) if desc else "",
                        source=self.name,
                        source_credit="Bayt.com public listing",
                        source_tier=self.tier,
                        needs_enrichment=True
                    ))
            except Exception:
                continue
        return jobs

    def enrich(self, job):
        url = job.get("url")
        if not url or not url.startswith("http"):
            return job
        try:
            page = _fetch_html_tls(url, impersonate="chrome")
            parsed = parse_schema_job_posting(page)
            if parsed and parsed.get("description"):
                if parsed.get("salary") and not job.get("salary"):
                    job["salary"] = parsed["salary"]
                if parsed.get("job_type"):
                    job["job_type"] = parsed["job_type"]
                if len(parsed["description"]) > len(job.get("description", "")):
                    job["description"] = parsed["description"]
                for sec_key in ("responsibilities", "qualifications", "preferred_qualifications", "how_to_apply", "contact_email", "contact_website"):
                    if parsed.get(sec_key):
                        job[sec_key] = parsed[sec_key]
                job["enriched"] = True
                job["needs_enrichment"] = False
            else:
                m = re.search(r'data-js-view="job-description"[^>]*>(.*?)</section>', page, re.S) or \
                    re.search(r'class="jb-descr[^"]*"[^>]*>(.*?)</div>', page, re.S)
                if m:
                    full_desc = html_to_text(m.group(1))
                    if len(full_desc) > len(job.get("description", "")):
                        job["description"] = full_desc
                        secs = extract_job_sections(full_desc)
                        for k, v in secs.items():
                            if v and not job.get(k):
                                job[k] = v
                        job["enriched"] = True
                        job["needs_enrichment"] = False
        except Exception:
            pass
        return job


class Naukri(Source):
    name, tier = "Naukri", "Major job board"

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def fetch(self, query, location):
        url = f"https://www.naukri.com/jobapi/v3/search?noOfResults=20&urlType=search_by_keyword&searchType=adv&k={urllib.parse.quote(query or 'software engineer')}"
        hdrs = {
            "appid": "109",
            "systemid": "Naukri",
            "nkparam": _generate_nkparam("srp"),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }
        try:
            raw = _fetch_html_tls(url, impersonate="chrome", headers=hdrs)
            data = json.loads(raw)
            items = data.get("jobDetails") or []
            jobs = []
            for it in items:
                jid = str(it.get("jobId") or abs(hash(it.get("title", ""))))
                title = it.get("title") or ""
                comp = it.get("companyName") or ""
                placeholders = it.get("placeholders") or []
                loc = placeholders[2].get("label", "") if len(placeholders) > 2 else (placeholders[0].get("label", "") if placeholders else "")
                sal = placeholders[1].get("label", "") if len(placeholders) > 1 else ""
                desc = it.get("jobDescription") or ""
                u = it.get("staticUrl") or f"https://www.naukri.com/job-listings-{jid}"
                if not u.startswith("http"):
                    u = f"https://www.naukri.com/{u.lstrip('/')}"
                jobs.append(make_job(
                    id=f"naukri-{jid}",
                    title=title,
                    company=comp,
                    location=loc,
                    salary=sal,
                    url=u,
                    description=desc,
                    source=self.name,
                    source_credit="Naukri.com public listing",
                    source_tier=self.tier,
                    needs_enrichment=True
                ))
            return jobs
        except Exception:
            return []

    def enrich(self, job):
        url = job.get("url")
        if not url:
            return job
        try:
            page = _fetch_html_tls(url, impersonate="chrome")
            parsed = parse_schema_job_posting(page)
            if parsed and parsed.get("description"):
                if parsed.get("salary") and not job.get("salary"):
                    job["salary"] = parsed["salary"]
                if parsed.get("job_type"):
                    job["job_type"] = parsed["job_type"]
                if len(parsed["description"]) > len(job.get("description", "")):
                    job["description"] = parsed["description"]
                for sec_key in ("responsibilities", "qualifications", "preferred_qualifications", "how_to_apply", "contact_email", "contact_website"):
                    if parsed.get(sec_key):
                        job[sec_key] = parsed[sec_key]
                job["enriched"] = True
                job["needs_enrichment"] = False
            else:
                m = re.search(r'class="[^"]*styles_job-desc-container[^"]*"[^>]*>(.*?)</div>', page, re.S) or \
                    re.search(r'class="[^"]*job-desc[^"]*"[^>]*>(.*?)</div>', page, re.S)
                if m:
                    full_desc = html_to_text(m.group(1))
                    if len(full_desc) > len(job.get("description", "")):
                        job["description"] = full_desc
                        secs = extract_job_sections(full_desc)
                        for k, v in secs.items():
                            if v and not job.get(k):
                                job[k] = v
                        job["enriched"] = True
                        job["needs_enrichment"] = False
        except Exception:
            pass
        return job


class HelloWork(Source):
    name, tier = "HelloWork", "Major job board"

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def fetch(self, query, location):
        url = f"https://www.hellowork.com/fr-fr/emploi/recherche.html?k={urllib.parse.quote(query or 'software engineer')}"
        try:
            page = _fetch_html_tls(url, impersonate="chrome")
            jobs = []
            seen = set()
            for m in re.finditer(r'href="(/fr-fr/emplois/(\d+)\.html)"[^>]*title="([^"]+)"', page):
                href, jid, raw_title = m.group(1), m.group(2), clean_text(m.group(3))
                if jid in seen:
                    continue
                seen.add(jid)
                title, sep, comp = raw_title.partition(" - ")
                if not comp:
                    title, comp = raw_title, ""

                start, end = max(0, m.start() - 200), min(len(page), m.end() + 1000)
                sub = page[start:end]
                loc_m = re.search(r'data-cy="localisationCard"[^>]*>\s*([^<]+)', sub)
                contract_m = re.search(r'data-cy="contractCard"[^>]*>\s*([^<]+)', sub)

                loc = clean_text(loc_m.group(1)) if loc_m else ""
                contract = clean_job_type(clean_text(contract_m.group(1))) if contract_m else ""

                url_full = f"https://www.hellowork.com{href}"
                jobs.append(make_job(
                    id=f"hellowork-{jid}",
                    title=clean_text(title),
                    company=clean_text(comp),
                    location=loc,
                    job_type=contract,
                    url=url_full,
                    source=self.name,
                    source_credit="HelloWork.com public listing",
                    source_tier=self.tier,
                    needs_enrichment=True
                ))
            return jobs
        except Exception:
            return []

    def enrich(self, job):
        url = job.get("url")
        if not url or not url.startswith("http"):
            return job
        try:
            page = _fetch_html_tls(url, impersonate="chrome")
            parsed = parse_schema_job_posting(page)
            if parsed and parsed.get("description"):
                if parsed.get("salary") and not job.get("salary"):
                    job["salary"] = parsed["salary"]
                if parsed.get("job_type"):
                    job["job_type"] = parsed["job_type"]
                if len(parsed["description"]) > len(job.get("description", "")):
                    job["description"] = parsed["description"]
                for sec_key in ("responsibilities", "qualifications", "preferred_qualifications", "how_to_apply", "contact_email", "contact_website"):
                    if parsed.get(sec_key):
                        job[sec_key] = parsed[sec_key]
                job["enriched"] = True
                job["needs_enrichment"] = False
            else:
                secs = []
                for pat in (r'<section[^>]*data-cy="job-description"[^>]*>(.*?)</section>',
                            r'<div[^>]*class="[^"]*content-job-description[^"]*"[^>]*>(.*?)</div>',
                            r'<section[^>]*class="[^"]*job-description[^"]*"[^>]*>(.*?)</section>'):
                    m = re.search(pat, page, re.S)
                    if m:
                        secs.append(html_to_text(m.group(1)))
                if secs:
                    full_desc = "\n\n".join(secs)
                    if len(full_desc) > len(job.get("description", "")):
                        job["description"] = full_desc
                        jsecs = extract_job_sections(full_desc)
                        for k, v in jsecs.items():
                            if v and not job.get(k):
                                job[k] = v
                        job["enriched"] = True
                        job["needs_enrichment"] = False
        except Exception:
            pass
        return job


def enrich_job(job):
    """Universal enricher: fetch complete details, salary, job type, and sections for any job."""
    if not job or not isinstance(job, dict):
        return job
    desc = job.get("description", "") or ""
    # If already fully enriched with sections, no need to refetch
    if job.get("enriched") and len(desc) > 800 and job.get("responsibilities"):
        return job

    src_name = job.get("source", "")
    url = job.get("url", "")

    # 1. Match by source class if available
    by_name = {s.name: s for s in list(BOARDS.values()) + SEARCH_SOURCES if hasattr(s, "enrich")}
    if src_name in by_name:
        try:
            job = by_name[src_name].enrich(job)
            if job.get("enriched") or len(job.get("description", "") or "") > 500:
                return job
        except Exception:
            pass

    # 2. Match by URL domain
    if "indeed.com" in url:
        job = Indeed().enrich(job)
    elif "linkedin.com" in url:
        job = LinkedInGuest().enrich(job)
    elif "ziprecruiter.com" in url:
        job = ZipRecruiter().enrich(job)
    elif "bayt.com" in url:
        job = Bayt().enrich(job)
    elif "hellowork.com" in url:
        job = HelloWork().enrich(job)
    elif url and url.startswith("http") and (not job.get("enriched") or len(job.get("description", "")) < 500):
        # 3. Universal fallback: fetch target URL and parse schema.org JobPosting or HTML
        try:
            page = _fetch_html_tls(url)
            parsed = parse_schema_job_posting(page)
            if parsed and parsed.get("description"):
                if parsed.get("salary") and not job.get("salary"):
                    job["salary"] = parsed["salary"]
                if parsed.get("job_type"):
                    job["job_type"] = parsed["job_type"]
                if len(parsed["description"]) > len(job.get("description", "")):
                    job["description"] = parsed["description"]
                for sec_key in ("responsibilities", "qualifications", "preferred_qualifications", "how_to_apply", "contact_email", "contact_website"):
                    if parsed.get(sec_key):
                        job[sec_key] = parsed[sec_key]
                job["enriched"] = True
                job["needs_enrichment"] = False
            elif page:
                m = re.search(r'<(?:article|main|div)[^>]*(?:id|class)=[\'"][^\'"]*(?:job[-_]?description|job[-_]?detail|posting[-_]?content|description)[^\'"]*[\'"][^>]*>(.*?)</(?:article|main|div)>', page, re.S | re.I)
                if m:
                    text = html_to_text(m.group(1))
                    if len(text) > len(job.get("description", "")):
                        job["description"] = text
                        secs = extract_job_sections(text)
                        for k, v in secs.items():
                            if v and not job.get(k):
                                job[k] = v
                        job["enriched"] = True
                        job["needs_enrichment"] = False
        except Exception:
            pass

    # Make sure sections are populated if description is present
    if job.get("raw_description") and len(job.get("raw_description", "")) > len(job.get("description", "")):
        job["description"] = job["raw_description"]
    desc_to_check = job.get("description") or ""
    if desc_to_check:
        secs = extract_job_sections(desc_to_check)
        for k in ("responsibilities", "qualifications", "preferred_qualifications", "how_to_apply", "contact_email", "contact_website", "salary_text", "job_type"):
            if secs.get(k):
                if k == "salary_text" and not job.get("salary"):
                    job["salary"] = secs[k]
                elif k == "job_type" and not job.get("job_type"):
                    job["job_type"] = clean_job_type(secs[k])
                elif not job.get(k):
                    job[k] = secs[k]

    return job


SEARCH_SOURCES = [
    StartupATS(), YCombinatorStartups(),
    Himalayas(), Remotive(), Jobicy(), Arbeitnow(), RemoteOK(), WeWorkRemotely(),
    HackerNewsHiring(), Adzuna(), LinkedInGuest(), Indeed(),
    ZipRecruiter(), Bayt(), Naukri(), HelloWork()
]


# ---------------------------------------------------------------- circuit breaker

_breaker = {}
_blk = threading.Lock()


def breaker_open(name):
    with _blk:
        st = _breaker.get(name)
        return bool(st and st["fails"] >= BREAKER_FAILS and time.time() - st["last"] < BREAKER_COOLDOWN)


def breaker_record(name, ok):
    with _blk:
        st = _breaker.setdefault(name, {"fails": 0, "last": 0})
        st["fails"] = 0 if ok else st["fails"] + 1
        st["last"] = time.time()


def reset_breakers():
    with _blk:
        _breaker.clear()
