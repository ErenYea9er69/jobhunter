"""Job sources. Each source returns normalized jobs or raises; the pipeline records health and falls back to cache."""
import base64
import datetime
import functools
import html
import http.cookiejar
import json
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import config
from .util import (HttpError, clean_salary_label, html_to_text, http_get, http_get_json, iso_or_empty, now_iso)

BREAKER_FAILS = 3
BREAKER_COOLDOWN = 300

# Ranking is deliberately transparent.  This is source authority/directness,
# not a claim that a company or a posting is objectively "famous".  Fit is
# calculated separately by scoring.py and remains the largest part of the
# final opportunity rank.
SOURCE_RANKS = {
    "Greenhouse": 100, "Lever": 100, "Ashby": 100, "SmartRecruiters": 100, "Workable": 100,
    "LinkedIn": 96, "Indeed": 95, "ZipRecruiter": 94, "Adzuna": 84, "Hacker News": 80,
    "We Work Remotely": 78, "Remotive": 76, "Himalayas": 75, "Jobicy": 72, "Arbeitnow": 70, "RemoteOK": 68,
    "Bayt": 68, "Naukri": 68, "HelloWork": 66,
}


def source_rank(source, tier=""):
    """Return the stable authority rank used as an explainable tie-breaker."""
    if str(tier).startswith("Direct company ATS"):
        return 100
    return SOURCE_RANKS.get(source, 50)


def source_kind(source, tier=""):
    if str(tier).startswith("Direct company ATS") or source in {"Greenhouse", "Lever", "Ashby", "SmartRecruiters", "Workable"}:
        return "Direct employer ATS"
    if source in {"LinkedIn", "Indeed", "ZipRecruiter", "Bayt", "Naukri", "HelloWork"}:
        return "Major job board"
    if source == "Adzuna":
        return "Job aggregator"
    return "Established job feed"


def _safe_text(val):
    if val is None or val != val:
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def make_job(**kw):
    """Build a job dict in the shared schema. Unknown data stays empty rather than being invented."""
    desc = html_to_text(kw.get("description", ""), 7000)
    loc = _safe_text(kw.get("location"))
    title = _safe_text(kw.get("title"))
    company = _safe_text(kw.get("company"))
    mode = _safe_text(kw.get("work_mode"))
    blob = f"{title} {loc} {desc[:600]}".lower()
    if not mode:
        mode = "Remote" if re.search(r"\bremote\b|anywhere|worldwide", blob) else \
               "Hybrid" if "hybrid" in blob else "On-site" if loc else ""
    return {
        "id": kw["id"], "title": title, "company": company,
        "location": loc or ("Remote" if mode == "Remote" else ""), "work_mode": mode,
        "salary": clean_salary_label(kw.get("salary", "")), "url": _safe_text(kw.get("url")),
        "description": desc, "posted_at": iso_or_empty(kw.get("posted_at")),
        "source": kw["source"], "source_credit": kw.get("source_credit", kw["source"]),
        "source_tier": kw.get("source_tier", ""), "source_rank": source_rank(kw["source"], kw.get("source_tier", "")),
        "source_kind": source_kind(kw["source"], kw.get("source_tier", "")), "tags": kw.get("tags", []),
        "needs_enrichment": bool(kw.get("needs_enrichment")),
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
    name, tier = "Remotive", "Free feed"

    def fetch(self, query, location):
        url = "https://remotive.com/api/remote-jobs?limit=60" + (f"&search={urllib.parse.quote(query)}" if query else "")
        data = http_get_json(url)
        return [make_job(id=f"remotive-{j['id']}", title=j.get("title"), company=j.get("company_name"),
                         location=j.get("candidate_required_location"), work_mode="Remote", salary=j.get("salary"),
                         url=j.get("url"), description=j.get("description"), posted_at=j.get("publication_date"),
                         source=self.name, source_credit="Remotive (remotive.com)", source_tier=self.tier,
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
                                location=j.get("jobGeo"), work_mode="Remote", salary=sal, url=j.get("url"),
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
                                url=j.get("url"), description=j.get("description"), posted_at=j.get("created_at"),
                                source=self.name, source_credit="Arbeitnow", source_tier=self.tier, tags=j.get("tags", [])))
        return out[:60]


class RemoteOK(Source):
    name, tier = "RemoteOK", "Free feed"

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
                                url=j.get("applicationLink"), description=desc, posted_at=j.get("pubDate"),
                                source=self.name, source_credit="Himalayas (himalayas.app)", source_tier=self.tier))
        return out[:60]


class WeWorkRemotely(Source):
    name, tier = "We Work Remotely", "Free feed"

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
        if location and location.lower() not in ("remote", "worldwide"):
            q["where"] = location
        data = http_get_json(f"https://api.adzuna.com/v1/api/jobs/{config.ADZUNA_COUNTRY}/search/1?" + urllib.parse.urlencode(q))
        out = []
        for j in data.get("results", []):
            sal = f"{int(j['salary_min'])} - {int(j['salary_max'])}" if j.get("salary_min") and j.get("salary_max") and not j.get("salary_is_predicted") in ("1", 1) else ""
            out.append(make_job(id=f"adzuna-{j['id']}", title=j.get("title"), company=(j.get("company") or {}).get("display_name"),
                                location=(j.get("location") or {}).get("display_name"), salary=sal, url=j.get("redirect_url"),
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
                                url=j.get("hostedUrl"), description=desc, posted_at=j.get("createdAt"),
                                source=self.name, source_credit=f"{name} on Lever", source_tier=self.tier))
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
                                (j.get("workplaceType") or "").title(), salary=comp, url=j.get("jobUrl"),
                                description=j.get("descriptionHtml") or j.get("descriptionPlain"),
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
                                work_mode="Remote" if j.get("telecommuting") else "", url=j.get("url") or j.get("application_url"),
                                description=j.get("description"), posted_at=j.get("published_on") or j.get("created_at"),
                                source=self.name, source_credit=f"{name} on Workable", source_tier=self.tier))
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
        self._warmed = False

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

    def fetch(self, query, location):
        self._warmup()
        out = []
        seen_ids = set()
        kw = (query or "software engineer").strip()
        loc = (location or "").strip()
        is_remote = "remote" in f"{kw} {loc}".lower()
        remote_flag = "&f_WT=2" if is_remote else ""
        search_loc = loc if loc and loc.lower() not in ("remote", "anywhere") else "Worldwide"

        # Multi-query slice strategy with proper step=10 offsets, fresh filters, and role synonyms:
        queries = [
            (kw, search_loc, 0, "", False),
            (kw, search_loc, 10, "", False),
            (kw, search_loc, 20, "", False),
            (kw, search_loc, 0, "&f_TPR=r604800", False),  # Past week fresh
            (f"{kw} startup", search_loc, 0, "", True),
            (f"{kw} startup", search_loc, 10, "", True),
        ]
        q_lower = kw.lower()
        if "developer" in q_lower:
            queries.append((re.sub(r"\bdeveloper\b", "engineer", kw, flags=re.I), search_loc, 0, "", False))
        elif "engineer" in q_lower:
            queries.append((re.sub(r"\bengineer\b", "developer", kw, flags=re.I), search_loc, 0, "", False))
        else:
            queries.append((f"{kw} developer", search_loc, 0, "", False))

        if search_loc == "Worldwide":
            queries.append((f"{kw} startup", "United States", 0, "", True))

        for term, place, start_idx, extra_params, is_startup_term in queries:
            url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                   f"keywords={urllib.parse.quote(term)}&location={urllib.parse.quote(place)}"
                   f"{remote_flag}{extra_params}&start={start_idx}")
            try:
                with self._opener.open(url, timeout=5) as resp:
                    page = resp.read().decode("utf-8", errors="replace")
            except Exception:
                time.sleep(0.3)
                continue

            cards = re.findall(r"<li>(.*?)</li>", page, re.S)
            if not cards:
                continue

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
                if jid in seen_ids:
                    continue
                seen_ids.add(jid)

                title = html.unescape(t.group(1).strip())
                comp = html.unescape(c.group(1).strip())
                place_str = html.unescape(l.group(1).strip()) if l else ""
                salary = html.unescape(sal_m.group(1).strip()) if sal_m else ""

                tags = []
                if is_startup_term or "startup" in card.lower() or "early-stage" in card.lower():
                    tags.append("startup")

                out.append(make_job(
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
                ))
            time.sleep(0.15)

        return out[:100]

    def enrich(self, job):
        m = re.search(r"(\d{6,})", job.get("id", ""))
        if not m:
            return job
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            page = http_get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}", headers=headers, retries=0)
            d = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.S)
            if d:
                job["description"] = html_to_text(d.group(1))
                job["needs_enrichment"] = False
        except Exception:
            pass
        return job


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
            if not title or not company:
                continue
            jid = match.group(1)
            out.append(make_job(id=f"indeed-{jid}", title=title, company=company, location=loc,
                                work_mode="Remote" if "remote" in f"{loc} {desc}".lower() else "",
                                url=f"https://www.indeed.com/viewjob?jk={urllib.parse.quote(jid)}",
                                description=desc, source=self.name, source_credit="Indeed public results",
                                source_tier=self.tier))
        return out


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
                desc = it.get("shortDescription") or ""
                jobs.append(make_job(
                    id=f"zip-{jid}",
                    title=str(title).strip(),
                    company=str(comp or "").strip(),
                    location=str(loc_str or "").strip(),
                    salary=sal,
                    url=u,
                    description=desc,
                    source=self.name,
                    source_credit="ZipRecruiter public listing",
                    source_tier=self.tier
                ))
            return jobs
        except Exception:
            return []


class Bayt(Source):
    name, tier = "Bayt", "Major job board"

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def fetch(self, query, location):
        slug = urllib.parse.quote("-".join((query or "software engineer").lower().split()))
        url = f"https://www.bayt.com/en/international/jobs/{slug}-jobs/"
        try:
            page = _fetch_html_tls(url, impersonate="chrome")
            cards = re.findall(r'<li[^>]*data-js-job[^>]*>(.*?)</li>', page, re.S)
            jobs = []
            seen = set()
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
                    location=loc,
                    url=link,
                    posted_at=d.group(1) if d else "",
                    salary=sal.group(1) if sal else "",
                    description=html.unescape(re.sub(r'<[^>]+>', '', desc.group(1)).strip()) if desc else "",
                    source=self.name,
                    source_credit="Bayt.com public listing",
                    source_tier=self.tier
                ))
            return jobs
        except Exception:
            return []


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
                    source_tier=self.tier
                ))
            return jobs
        except Exception:
            return []


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
            cards = re.findall(r'<li[^>]*data-id-storage-target=item[^>]*>(.*?)</li>', page, re.S)
            jobs = []
            seen = set()
            for card in cards:
                t = re.search(r'<h3[^>]*>(.*?)</h3>', card, re.S)
                comp = re.search(r'data-cy="company-name"[^>]*>([^<]+)<', card)
                loc = re.search(r'data-cy="location"[^>]*>([^<]+)<', card)
                link = re.search(r'<a[^>]*href="(/fr-fr/emplois/[^"]+)"', card)
                jid_m = re.search(r'data-id-storage-item-id="([^"]+)"', card)
                if not (t and link):
                    continue
                title = html.unescape(re.sub(r'<[^>]+>', '', t.group(1)).strip())
                cname = html.unescape(comp.group(1).strip()) if comp else ""
                lname = html.unescape(loc.group(1).strip()) if loc else ""
                url_full = f"https://www.hellowork.com{link.group(1)}"
                jid = jid_m.group(1) if jid_m else str(abs(hash(url_full)))
                if jid in seen:
                    continue
                seen.add(jid)
                jobs.append(make_job(
                    id=f"hellowork-{jid}",
                    title=title,
                    company=cname,
                    location=lname,
                    url=url_full,
                    source=self.name,
                    source_credit="HelloWork.com public listing",
                    source_tier=self.tier
                ))
            return jobs
        except Exception:
            return []


SEARCH_SOURCES = [
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
