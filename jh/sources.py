"""Job sources. Each source returns normalized jobs or raises; the pipeline records health and falls back to cache."""
import datetime
import html
import importlib
import json
import re
import threading
import time
import urllib.parse
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
    "LinkedIn": 96, "Indeed": 95, "Adzuna": 84, "Hacker News": 80,
    "We Work Remotely": 78, "Remotive": 76, "Jobicy": 72, "Arbeitnow": 70, "RemoteOK": 68,
}


def source_rank(source, tier=""):
    """Return the stable authority rank used as an explainable tie-breaker."""
    if str(tier).startswith("Direct company ATS"):
        return 100
    return SOURCE_RANKS.get(source, 50)


def source_kind(source, tier=""):
    if str(tier).startswith("Direct company ATS") or source in {"Greenhouse", "Lever", "Ashby", "SmartRecruiters", "Workable"}:
        return "Direct employer ATS"
    if source in {"LinkedIn", "Indeed"}:
        return "Major job board"
    if source == "Adzuna":
        return "Job aggregator"
    return "Established job feed"


def make_job(**kw):
    """Build a job dict in the shared schema. Unknown data stays empty rather than being invented."""
    desc = html_to_text(kw.get("description", ""), 7000)
    loc = (kw.get("location") or "").strip()
    mode = kw.get("work_mode") or ""
    blob = f"{kw.get('title', '')} {loc} {desc[:600]}".lower()
    if not mode:
        mode = "Remote" if re.search(r"\bremote\b|anywhere|worldwide", blob) else \
               "Hybrid" if "hybrid" in blob else "On-site" if loc else ""
    return {
        "id": kw["id"], "title": (kw.get("title") or "").strip(), "company": (kw.get("company") or "").strip(),
        "location": loc or ("Remote" if mode == "Remote" else ""), "work_mode": mode,
        "salary": clean_salary_label(kw.get("salary", "")), "url": kw.get("url") or "",
        "description": desc, "posted_at": iso_or_empty(kw.get("posted_at")),
        "source": kw["source"], "source_credit": kw.get("source_credit", kw["source"]),
        "source_tier": kw.get("source_tier", ""), "source_rank": source_rank(kw["source"], kw.get("source_tier", "")),
        "source_kind": source_kind(kw["source"], kw.get("source_tier", "")), "tags": kw.get("tags", []),
        "needs_enrichment": bool(kw.get("needs_enrichment")),
    }


def _matches(query, *fields):
    """Loose client-side filter for feeds that cannot search: every query word must appear somewhere."""
    if not query:
        return True
    hay = " ".join(f or "" for f in fields).lower()
    return all(w in hay for w in re.findall(r"[a-z0-9+#.]+", query.lower()) if len(w) > 1)


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
        url = "https://jobicy.com/api/v2/remote-jobs?count=50" + (f"&tag={urllib.parse.quote(query)}" if query else "")
        data = http_get_json(url)
        out = []
        for j in data.get("jobs", []):
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
            if not _matches(query, j.get("position"), " ".join(j.get("tags", [])), j.get("company")):
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


class WeWorkRemotely(Source):
    name, tier = "We Work Remotely", "Free feed"

    def fetch(self, query, location):
        xml = http_get("https://weworkremotely.com/remote-jobs.rss")
        root = ET.fromstring(xml)
        out = []
        for item in root.iter("item"):
            raw_title = (item.findtext("title") or "")
            company, _, title = raw_title.partition(": ")
            if not title:
                company, title = "", raw_title
            desc = item.findtext("description") or ""
            if not _matches(query, title, company, desc[:800]):
                continue
            out.append(make_job(id="wwr-" + re.sub(r"\W+", "-", item.findtext("guid") or title)[-60:], title=title,
                                company=company, location=item.findtext("region") or "Remote", work_mode="Remote",
                                url=item.findtext("link"), description=desc, posted_at=item.findtext("pubDate"),
                                source=self.name, source_credit="We Work Remotely", source_tier=self.tier))
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

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def fetch(self, query, location):
        url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords="
               f"{urllib.parse.quote(query or 'software engineer')}&location={urllib.parse.quote(location or 'Remote')}&start=0")
        html = http_get(url, headers={"Accept": "text/html"}, retries=0)
        out = []
        for card in re.findall(r"<li>(.*?)</li>", html, re.S):
            t = re.search(r'base-search-card__title[^>]*>\s*([^<]+)', card)
            c = re.search(r'base-search-card__subtitle[^>]*>\s*(?:<a[^>]*>\s*)?([^<]+)', card)
            l = re.search(r'job-search-card__location[^>]*>\s*([^<]+)', card)
            u = re.search(r'base-card__full-link[^>]*href="([^"?]+)', card)
            d = re.search(r'datetime="([^"]+)"', card)
            if not (t and c and u):
                continue
            jid = re.search(r"(\d{6,})", u.group(1))
            out.append(make_job(id=f"linkedin-{jid.group(1) if jid else abs(hash(u.group(1)))}", title=t.group(1).strip(),
                                company=c.group(1).strip(), location=l.group(1).strip() if l else "", url=u.group(1),
                                posted_at=d.group(1) if d else "", description="", needs_enrichment=True,
                                source=self.name, source_credit="LinkedIn public listing", source_tier=self.tier))
        return out

    def enrich(self, job):
        m = re.search(r"(\d{6,})", job.get("id", ""))
        if not m:
            return job
        html = http_get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}", headers={"Accept": "text/html"}, retries=0)
        d = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', html, re.S)
        if d:
            job["description"] = html_to_text(d.group(1))
            job["needs_enrichment"] = False
        return job


class IndeedJobSpy(Source):
    name, tier = "Indeed", "Major job board"

    def available(self):
        # JobSpy is an acceleration/coverage enhancement, not a requirement.
        # The built-in parser below keeps Indeed in every search on a stdlib-only install.
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

    def _fetch_builtin(self, query, location):
        """Small public-results fallback when python-jobspy is not installed."""
        params = {"q": query or "software engineer", "l": location or "", "fromage": "14"}
        url = "https://www.indeed.com/jobs?" + urllib.parse.urlencode(params)
        try:
            page = http_get(url, headers={"Accept": "text/html",
                                          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"}, retries=0)
        except HttpError:
            raise HttpError("Indeed requires python-jobspy for Cloudflare bypass. Other feeds active.")
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

    def fetch(self, query, location):
        try:
            jobspy = importlib.import_module("jobspy")
            scrape_jobs = jobspy.scrape_jobs
        except (ImportError, AttributeError):
            return self._fetch_builtin(query, location)
        df = scrape_jobs(site_name=["indeed"], search_term=query or "software engineer", location=location or "",
                         results_wanted=40, hours_old=24 * 14)
        out = []
        for r in df.to_dict("records"):
            sal = f"{int(r['min_amount'])} - {int(r['max_amount'])}" if r.get("min_amount") == r.get("min_amount") and r.get("min_amount") else ""
            out.append(make_job(id=f"indeed-{r.get('id')}", title=r.get("title"), company=r.get("company"),
                                location=r.get("location"), work_mode="Remote" if r.get("is_remote") else "", salary=sal,
                                url=r.get("job_url"), description=r.get("description") or "", posted_at=str(r.get("date_posted") or ""),
                                source=self.name, source_credit="Indeed (via JobSpy)", source_tier=self.tier))
        return out


SEARCH_SOURCES = [Remotive(), Jobicy(), Arbeitnow(), RemoteOK(), WeWorkRemotely(), HackerNewsHiring(), Adzuna(),
                  LinkedInGuest(), IndeedJobSpy()]


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
