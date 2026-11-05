"""Sources that reach small and regional employers.

Generic and standards-based (these need no site-specific code):
    SiteReader        reads any site that publishes schema.org JobPosting data, which is what
                      Google for Jobs requires. Finds job pages through the sitemap and the page's
                      own links. Obeys robots.txt. Reads a handful of pages per site, politely.
    RegionalBoards    runs SiteReader over the local boards listed in ``regional_boards``.
    JobSites          runs SiteReader over sites you added with ``add_job_source(kind="site")``.
    discover_site     tells you how a site can be read: feeds, sitemap, job data, ATS links.

Vendor APIs (written from public documentation, not checked against live servers):
    Jooble            aggregator with many small local boards. Needs a free key (JOOBLE_API_KEY).
    JobTech           Sweden's public employment service. No key.
    Pinpoint          an applicant tracking system that small and mid-size employers use.

The pure parsing functions are tested offline with fixtures in ``tests/fixtures``.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import re
import threading
import time
import urllib.parse
import urllib.robotparser
from typing import Optional

from . import BOARDS, Source, _Board, make_job
from .ats_boards import board_from_url, boards_in_html
from .feeds import jobs_from_jsonld, parse_feed
from .. import config, localize, preferences, regional_boards
from ..util import clean_text, http_get, http_get_json, http_get_text, safe_parse_xml, stable_id

_PAGE_CAP = 25            # detail pages read per site per search
_SITE_WORKERS = 4
_SITE_BUDGET_SECONDS = 20
_SITES_PER_CALL = 6
_ROBOTS_TTL = 6 * 3600
_HOST_GAP_SECONDS = 0.25  # pause between requests to one host

# A path that looks like one job page: /jobs/123, /offre-emploi/ingenieur-logiciel, /careers/senior-dev
_JOB_PATH = re.compile(
    r"/(?:jobs?|job-offers?|job-details?|offres?(?:-d-?emploi|-emploi)?|offre|emploi|emplois|carrieres?|careers?|"
    r"vacanc(?:y|ies)|positions?|opportunit(?:y|ies)|recrutement|stellen(?:angebot)?|vacatures?|empleos?|"
    r"ofertas?|vagas?|annunci)(?:/|-|_)", re.I)
_LISTING_ONLY = re.compile(r"/(?:jobs?|emploi|offres?|careers?|carrieres?)/?(?:\?.*)?$", re.I)
_SITEMAP_HINT = re.compile(r"job|emploi|offre|offer|career|carriere|vacan|stellen|vagas|empleo", re.I)
_SKIP_EXT = re.compile(r"\.(?:jpe?g|png|gif|svg|webp|pdf|css|js|ico|zip|xml)(?:\?|$)", re.I)


# ------------------------------------------------------------------ robots.txt and polite fetching

_robots: dict[str, tuple[float, Optional[urllib.robotparser.RobotFileParser]]] = {}
_robots_lock = threading.Lock()
_host_last: dict[str, float] = {}
_host_lock = threading.Lock()


def _origin(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").removeprefix("www.")


def clear_state() -> None:
    """Forget cached robots.txt files and request timing. Used by tests."""
    with _robots_lock:
        _robots.clear()
    with _host_lock:
        _host_last.clear()


def robots_text(origin: str) -> str:
    try:
        return http_get_text(f"{origin}/robots.txt", retries=0, timeout=8)
    except Exception:
        return ""


def robots_allows(url: str) -> bool:
    """True when robots.txt allows reading this URL. An unreachable robots.txt means allowed."""
    origin = _origin(url)
    now = time.time()
    with _robots_lock:
        cached = _robots.get(origin)
    if cached and now - cached[0] < _ROBOTS_TTL:
        rp = cached[1]
    else:
        text = robots_text(origin)
        rp = None
        if text.strip():
            rp = urllib.robotparser.RobotFileParser()
            try:
                rp.parse(text.splitlines())
            except Exception:
                rp = None
        with _robots_lock:
            _robots[origin] = (now, rp)
    if rp is None:
        return True
    try:
        return rp.can_fetch("JobHunter", url)
    except Exception:
        return True


def _polite_get(url: str, timeout: int = 12) -> str:
    """Fetch one page after the robots check and a short gap since the last request to the same host."""
    if not robots_allows(url):
        raise PermissionError(f"robots.txt does not allow reading {urllib.parse.urlparse(url).path or '/'}")
    host = _host(url)
    with _host_lock:
        wait = _HOST_GAP_SECONDS - (time.time() - _host_last.get(host, 0))
        _host_last[host] = time.time() + max(0, wait)
    if wait > 0:
        time.sleep(wait)
    return http_get_text(url, retries=0, timeout=timeout)


# ------------------------------------------------------------------ discovery helpers (pure)

def links_in_html(html_text: str, base_url: str) -> list[tuple[str, str]]:
    """Every same-site link as ``(absolute_url, anchor_text)``, in page order, without repeats."""
    host = _host(base_url)
    out, seen = [], set()
    for m in re.finditer(r"<a\s[^>]*?href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", html_text or "", re.I | re.S):
        href = m.group(1).strip()
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        if _host(absolute) != host or _SKIP_EXT.search(absolute) or absolute in seen:
            continue
        seen.add(absolute)
        out.append((absolute, clean_text(re.sub(r"<[^>]+>", " ", m.group(2)))[:120]))
    return out


def looks_like_job_page(url: str) -> bool:
    path = urllib.parse.urlparse(url).path or ""
    if not _JOB_PATH.search(path + "/") or _LISTING_ONLY.search(path):
        return False
    return len([s for s in path.split("/") if s]) >= 2 or bool(re.search(r"\d", path))


def feed_links_in_html(html_text: str, base_url: str) -> list[str]:
    """RSS and Atom feeds a page announces in its head."""
    found = []
    for tag in re.findall(r"<link\s[^>]*>", html_text or "", re.I):
        if re.search(r"rel=[\"']alternate[\"']", tag, re.I) and re.search(r"type=[\"']application/(?:rss|atom)\+xml[\"']", tag, re.I):
            m = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.I)
            if m:
                found.append(urllib.parse.urljoin(base_url, m.group(1)))
    return list(dict.fromkeys(found))


def parse_sitemap(xml_text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Return ``(child_sitemaps, [(url, lastmod), ...])`` from a sitemap or a sitemap index."""
    try:
        root = safe_parse_xml(xml_text)
    except Exception:
        return [], []
    kids, urls = [], []
    for node in root:
        tag = node.tag.rsplit("}", 1)[-1].lower()
        loc = next((c.text.strip() for c in node if c.tag.rsplit("}", 1)[-1].lower() == "loc" and c.text), "")
        mod = next((c.text.strip() for c in node if c.tag.rsplit("}", 1)[-1].lower() == "lastmod" and c.text), "")
        if not loc:
            continue
        if tag == "sitemap":
            kids.append(loc)
        elif tag == "url":
            urls.append((loc, mod))
    return kids, urls


def sitemap_job_urls(origin: str, robots: str = "", limit: int = 400) -> list[str]:
    """Job-looking URLs from the sitemaps a site lists, newest first."""
    starts = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots or "") or [f"{origin}/sitemap.xml"]
    queue, seen, urls = list(starts[:3]), set(), []
    reads = 0
    while queue and reads < 6:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        reads += 1
        try:
            kids, found = parse_sitemap(_polite_get(sm))
        except Exception:
            continue
        queue.extend(sorted(kids, key=lambda k: not _SITEMAP_HINT.search(k))[:4])
        urls.extend(found)
        if len(urls) >= limit * 3:
            break
    urls.sort(key=lambda t: t[1] or "", reverse=True)
    return [u for u, _ in urls if looks_like_job_page(u)][:limit]


def _rank_candidates(urls: list[tuple[str, str]], variants: list[str]) -> list[str]:
    """Order job-page candidates so pages whose link or slug fits the query come first."""
    def score(item: tuple[str, str]) -> int:
        url, text = item
        slug = urllib.parse.unquote(urllib.parse.urlparse(url).path).replace("-", " ").replace("_", " ")
        return 0 if localize.matches_any(variants, slug, text) and variants else 1
    ordered = sorted(enumerate(urls), key=lambda p: (score(p[1]), p[0]))
    return [u for _, (u, _t) in ordered]


# ------------------------------------------------------------------ reading one site

def read_site(site: dict, query: str, variants: Optional[list[str]] = None, max_pages: int = _PAGE_CAP,
              source: str = "Regional Boards") -> list[dict]:
    """Read jobs from one site. Raises PermissionError when robots.txt forbids it.

    Order: JobPosting data on the start page, then job pages found in the sitemap and in the
    page's links, fetched with a small thread pool and a time budget.
    """
    root, label = site["url"], site.get("name") or _host(site["url"])
    variants = variants or ([query] if query else [])
    deadline = time.time() + _SITE_BUDGET_SECONDS
    tier = "Regional job board"
    html_text = _polite_get(root)
    jobs = jobs_from_jsonld(html_text, root, label, source, tier)
    seen_urls = {j["url"] for j in jobs}

    candidates = [(u, t) for u, t in links_in_html(html_text, root) if looks_like_job_page(u)]
    known = {u for u, _ in candidates}
    for u in sitemap_job_urls(_origin(root), robots_text(_origin(root))):
        if u not in known:
            candidates.append((u, ""))
            known.add(u)
    todo = [u for u in _rank_candidates(candidates, variants) if u not in seen_urls][:max_pages]

    def one(url: str) -> list[dict]:
        if time.time() > deadline:
            return []
        page = _polite_get(url)
        return jobs_from_jsonld(page, url, label, source, tier)

    with cf.ThreadPoolExecutor(max_workers=_SITE_WORKERS) as pool:
        futs = [pool.submit(one, u) for u in todo]
        for fut in futs:
            try:
                jobs.extend(fut.result(timeout=max(1, deadline - time.time() + 5)))
            except Exception:
                continue
    for j in jobs:
        j["found_via"] = "site reader"
        j["source_credit"] = label
    unique = {}
    for j in jobs:
        unique.setdefault(j["id"], j)
    return list(unique.values())


def discover_site(url: str) -> dict:
    """Explain how a site can be read. Reads at most four pages. Never writes anything."""
    root = url.strip()
    out: dict = {"url": root, "robots_allows": True, "ats_boards": [], "feeds": [], "job_data_on_start_page": 0,
                 "job_pages_found": 0, "sitemap_job_urls": 0, "recommendation": "", "notes": []}
    if not robots_allows(root):
        out["robots_allows"] = False
        out["recommendation"] = "robots.txt asks robots not to read this site. Do not add it as a site."
        return out
    html_text = ""
    try:
        html_text = _polite_get(root)
    except Exception as e:
        out["notes"].append(f"Could not read the page: {str(e)[:100]}")
        out["recommendation"] = "The page could not be read. Check the URL."
        return out
    hit = board_from_url(root)
    out["ats_boards"] = [{"board": b, "slug": s} for b, s in ([hit] if hit else []) + boards_in_html(html_text)[:4]]
    out["job_data_on_start_page"] = len(jobs_from_jsonld(html_text, root, "", "Job Sites", "Regional job board"))
    out["job_pages_found"] = sum(1 for u, _ in links_in_html(html_text, root) if looks_like_job_page(u))
    for feed_url in feed_links_in_html(html_text, root)[:3]:
        try:
            n = len(parse_feed(http_get_text(feed_url, retries=0, timeout=10)))
        except Exception:
            n = 0
        out["feeds"].append({"url": feed_url, "jobs": n})
    try:
        out["sitemap_job_urls"] = len(sitemap_job_urls(_origin(root), robots_text(_origin(root)), limit=100))
    except Exception:
        pass

    if out["ats_boards"]:
        b = out["ats_boards"][0]
        out["recommendation"] = f"This site uses {b['board']}. Add it with add_job_source(kind='company', value='{root}')."
    elif any(f["jobs"] for f in out["feeds"]):
        best = max(out["feeds"], key=lambda f: f["jobs"])
        out["recommendation"] = f"Add the feed: add_job_source(kind='feed', value='{best['url']}')."
    elif out["job_data_on_start_page"] or out["job_pages_found"] or out["sitemap_job_urls"]:
        out["recommendation"] = "Add it as a site: add_job_source(kind='site', value='" + root + "'). Job pages were found."
    else:
        out["recommendation"] = ("No job feed, no ATS link and no job pages were found. The site may load jobs with scripts. "
                                 "Try its jobs page URL, or add the company with kind='company'.")
    return out


# ------------------------------------------------------------------ site-based sources

class _SiteSource(Source):
    tier = "Regional job board"

    def _read_all(self, sites: list[dict], query: str, variants: list[str]) -> list[dict]:
        sites = sites[:_SITES_PER_CALL]
        if not sites:
            return []
        out, errors = [], []
        with cf.ThreadPoolExecutor(max_workers=3) as pool:
            futs = {pool.submit(read_site, s, query, variants, _PAGE_CAP, self.name): s for s in sites}
            for fut in cf.as_completed(futs):
                try:
                    out.extend(fut.result())
                except Exception as e:
                    errors.append(f"{_host(futs[fut]['url'])}: {str(e)[:80]}")
        if errors and not out and len(errors) == len(sites):
            raise RuntimeError("; ".join(errors[:3]))
        return out


class RegionalBoards(_SiteSource):
    """Local boards from ``regional_boards``, one call per target country, in the local language too."""
    name = "Regional Boards"

    def fetch(self, query, location, country=None):
        if not country:
            return []
        variants = localize.variants(query, country)
        return self._read_all(regional_boards.sites_for(country), query, variants)


class JobSites(_SiteSource):
    """Sites you added with add_job_source(kind='site')."""
    name = "Job Sites"

    def configured(self) -> bool:
        return bool(preferences.load().get("job_sites"))

    def fetch(self, query, location):
        sites = preferences.load().get("job_sites") or []
        return self._read_all(sites, query, localize.variants(query, "") or [query])


# ------------------------------------------------------------------ aggregators and public APIs

class Jooble(Source):
    """Jooble collects postings from many small local boards. Free key from jooble.org/api/about."""
    name, tier, needs_key = "Jooble", "Aggregator API", True

    def _key(self) -> str:
        from .. import db
        return config.JOOBLE_API_KEY or db.get_setting("jooble_api_key") or ""

    def available(self):
        return bool(self._key())

    def unavailable_reason(self):
        return "Add a free Jooble key (JOOBLE_API_KEY) to reach small local boards in many countries."

    @staticmethod
    def parse(data: dict) -> list[dict]:
        out = []
        for j in (data or {}).get("jobs", []) if isinstance(data, dict) else []:
            title, link = clean_text(j.get("title")), j.get("link") or ""
            if not title or not link:
                continue
            out.append({"id": f"jooble-{j.get('id') or stable_id(link)}", "title": title, "company": clean_text(j.get("company")),
                        "location": clean_text(j.get("location")), "url": link, "description": j.get("snippet") or "",
                        "salary": clean_text(j.get("salary")), "job_type": clean_text(j.get("type")),
                        "posted_at": j.get("updated") or "", "origin": clean_text(j.get("source"))})
        return out

    def fetch(self, query, location, country=None):
        body = json.dumps({"keywords": query or "", "location": location or "", "page": "1"}).encode()
        raw = http_get(f"https://jooble.org/api/{urllib.parse.quote(self._key())}", data=body, method="POST",
                       headers={"Content-Type": "application/json"}, retries=0, timeout=15)
        jobs = []
        for it in self.parse(json.loads(raw)):
            jobs.append(make_job(
                id=it["id"], title=it["title"], company=it["company"] or it["origin"], location=it["location"], url=it["url"],
                description=it["description"], salary=it["salary"], job_type=it["job_type"], posted_at=it["posted_at"],
                source=self.name, source_credit=it["origin"] or "Jooble", source_tier=self.tier, needs_enrichment=True))
        return jobs


class JobTech(Source):
    """Sweden's public employment service (JobTech Dev). Open API, no key."""
    name, tier = "JobTech", "Public API"

    @staticmethod
    def parse(data: dict) -> list[dict]:
        out = []
        for h in (data or {}).get("hits", []) if isinstance(data, dict) else []:
            title = clean_text(h.get("headline"))
            url = h.get("webpage_url") or (h.get("application_details") or {}).get("url") or ""
            if not title or not url:
                continue
            addr = h.get("workplace_address") or {}
            place = ", ".join(x for x in (addr.get("municipality"), addr.get("region"), addr.get("country")) if x)
            out.append({"id": f"jobtech-{h.get('id')}", "title": title, "company": clean_text((h.get("employer") or {}).get("name")),
                        "location": place, "url": url, "description": (h.get("description") or {}).get("text") or "",
                        "posted_at": h.get("publication_date") or "",
                        "job_type": clean_text((h.get("employment_type") or {}).get("label"))})
        return out

    def fetch(self, query, location):
        params = {"q": query or "", "limit": 50}
        data = http_get_json("https://jobsearch.api.jobtechdev.se/search?" + urllib.parse.urlencode(params), retries=0, timeout=15)
        return [make_job(id=it["id"], title=it["title"], company=it["company"], location=it["location"], url=it["url"],
                         description=it["description"], job_type=it["job_type"], posted_at=it["posted_at"], source=self.name,
                         source_credit="Arbetsformedlingen", source_tier=self.tier) for it in self.parse(data)]


class Pinpoint(_Board):
    """Pinpoint applicant tracking: https://{slug}.pinpointhq.com/postings.json"""
    name = board = "Pinpoint"

    @staticmethod
    def parse(data: dict, slug: str, name: str) -> list[dict]:
        out = []
        for j in (data or {}).get("data", []) if isinstance(data, dict) else []:
            title, url = clean_text(j.get("title")), j.get("url") or j.get("path") or ""
            if not title or not url:
                continue
            if url.startswith("/"):
                url = f"https://{slug}.pinpointhq.com{url}"
            loc = j.get("location") or {}
            place = loc.get("name") or ", ".join(x for x in (loc.get("city"), loc.get("province")) if x)
            wt = str(j.get("workplace_type") or "").lower()
            lo, hi, cur = j.get("compensation_minimum"), j.get("compensation_maximum"), j.get("compensation_currency") or ""
            salary = f"{lo} - {hi or lo} {cur}".strip() if lo else ""
            desc = "\n".join(str(j.get(k) or "") for k in ("description", "key_responsibilities", "skills_knowledge_expertise", "benefits"))
            out.append(make_job(
                id=f"pinpoint-{slug}-{j.get('id')}", title=title, company=name, location=place,
                work_mode="Remote" if wt == "remote" else ("Hybrid" if wt == "hybrid" else ""), salary=salary,
                job_type=str(j.get("employment_type_text") or ""), url=url, description=desc,
                posted_at=j.get("created_at") or j.get("published_at") or "", source="Pinpoint",
                source_credit=f"{name} on Pinpoint", source_tier="Direct company ATS"))
        return out

    def fetch_company(self, slug, company_name=""):
        data = http_get_json(f"https://{slug}.pinpointhq.com/postings.json", retries=0)
        return self.parse(data, slug, company_name or slug.replace("-", " ").title())


BOARDS["pinpoint"] = Pinpoint()

NEW_SOURCES = (RegionalBoards(), JobSites(), Jooble(), JobTech())
