"""Extra job sources that reach beyond the big boards.

User-driven (you decide where to look):
    CustomFeeds   any RSS, Atom, JSON Feed or plain JSON job list you add
    CareerPages   any company careers page: known ATS links, or schema.org JobPosting data

Public APIs that need no key:
    WorkingNomads, TheMuse, Arbeitsagentur (Germany's public employment service)

Parsers here are pure functions, so they are tested offline with fixtures.
"""

from __future__ import annotations

import base64
import concurrent.futures as cf
import json
import re
import urllib.parse
from typing import Any

from . import BOARDS, Source, _matches, make_job
from .ats_boards import _item_fields, _local, board_from_url, boards_in_html
from .. import preferences, regions
from ..util import (clean_text, html_to_text, http_get_json, http_get_text, parse_schema_job_posting,
                    safe_parse_xml, stable_id)

_MAX_FEEDS = 20
_FEED_WORKERS = 6


# ------------------------------------------------------------------ generic feed parsing

_TITLE_SPLITS = (r"\s+at\s+", r"\s+@\s+", r"\s+\|\s+", r"\s+[-\u2013\u2014]\s+")


def split_title_company(title: str) -> tuple[str, str]:
    """Split ``"Backend Engineer at Acme"`` into ``("Backend Engineer", "Acme")``. Leaves other titles alone."""
    t = (title or "").strip()
    for pat in _TITLE_SPLITS:
        parts = re.split(pat, t)
        if len(parts) == 2 and 2 <= len(parts[1]) <= 50 and parts[0].strip():
            return parts[0].strip(), parts[1].strip()
    return t, ""


def _pick(d: dict, keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return ""


def _as_text(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("name") or v.get("title") or v.get("label") or "")
    if isinstance(v, (list, tuple)):
        return ", ".join(_as_text(x) for x in v if x)
    return str(v or "")


def _parse_json_items(data: Any) -> list[dict]:
    if isinstance(data, dict):
        for key in ("items", "jobs", "results", "data", "positions", "offers", "postings", "listings", "vacancies"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = []
    out = []
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict):
            continue
        title = _as_text(_pick(d, ("title", "name", "position", "job_title", "jobTitle", "role")))
        url = _as_text(_pick(d, ("url", "link", "apply_url", "applyUrl", "absolute_url", "job_url", "external_url", "hostedUrl")))
        if not title or not url:
            continue
        out.append({
            "title": title,
            "company": _as_text(_pick(d, ("company", "company_name", "companyName", "employer", "organization", "hiringOrganization", "author", "authors"))),
            "location": _as_text(_pick(d, ("location", "candidate_required_location", "city", "locations", "place", "region"))),
            "url": url,
            "description": _as_text(_pick(d, ("description", "content_html", "content", "summary", "content_text", "body"))),
            "posted_at": _as_text(_pick(d, ("date_published", "published_at", "pubDate", "pub_date", "date_posted", "datePosted", "created_at", "date", "updated_at"))),
            "tags": [t for t in (d.get("tags") or []) if isinstance(t, str)][:8],
        })
    return out


def parse_feed(text: str) -> list[dict]:
    """Parse RSS 2.0, RSS 1.0, Atom, JSON Feed or a plain JSON job list into normalized items.

    Each item has: title, company, location, url, description, posted_at, tags.
    """
    s = (text or "").lstrip("\ufeff \t\r\n")
    if not s:
        return []
    if s[0] in "{[":
        return _parse_json_items(json.loads(s))
    root = safe_parse_xml(s)
    out = []
    for node in root.iter():
        if _local(node.tag).lower() not in ("item", "entry"):
            continue
        f = _item_fields(node)
        link = f.get("link") or ""
        title = clean_text(f.get("title", ""))
        if not title or not link:
            continue
        company = f.get("company") or f.get("employer") or f.get("hiringorganization") or f.get("creator") or f.get("author") or ""
        if not company:
            title, company = split_title_company(title)
        out.append({
            "title": title,
            "company": clean_text(company),
            "location": clean_text(f.get("location") or f.get("job_location") or f.get("region") or f.get("locations") or ""),
            "url": link,
            "description": f.get("encoded") or f.get("content") or f.get("description") or f.get("summary") or "",
            "posted_at": f.get("pubdate") or f.get("published") or f.get("updated") or f.get("date") or "",
            "tags": [t for t in (f.get("category"), f.get("job_type"), f.get("type")) if t],
        })
    return out


# ------------------------------------------------------------------ schema.org JobPosting

def extract_jobposting_jsonld(html_text: str) -> list[dict]:
    """Return every schema.org JobPosting object found in a page's JSON-LD blocks."""
    found: list[dict] = []

    def walk(node):
        if isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(isinstance(x, str) and x.rstrip("/").endswith("JobPosting") for x in types):
                found.append(node)
            for key in ("@graph", "itemListElement", "item", "mainEntity", "hasPart"):
                if key in node:
                    walk(node[key])

    for block in re.findall(r"<script[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>", html_text or "", re.S | re.I):
        try:
            walk(json.loads(block.strip()))
        except ValueError:
            continue
    return found


def jobs_from_jsonld(html_text: str, page_url: str, company_hint: str = "", source: str = "Career Page", tier: str = "Direct company ATS (career page)") -> list[dict]:
    raw_postings = extract_jobposting_jsonld(html_text)
    out = []
    for d in raw_postings:
        parsed = parse_schema_job_posting(dict(d, **{"@type": "JobPosting"}))
        if not parsed.get("title"):
            continue
        url = d.get("url") or (d.get("@id") if str(d.get("@id", "")).startswith("http") else "") or ""
        if url and not url.startswith("http"):
            url = urllib.parse.urljoin(page_url, url)
        if not url:
            url = page_url if len(raw_postings) == 1 else f"{page_url}#{stable_id(parsed['title'], d.get('identifier'))}"
        remote = str(d.get("jobLocationType", "")).upper() == "TELECOMMUTE"
        company = company_hint or parsed.get("company") or urllib.parse.urlparse(page_url).hostname or ""
        out.append(make_job(
            id=f"page-{stable_id(page_url, parsed['title'], url)}", title=parsed["title"], company=company,
            location=parsed.get("location", ""), work_mode="Remote" if remote else "", salary=parsed.get("salary", ""),
            job_type=parsed.get("job_type", ""), url=url, description=parsed.get("description", ""),
            posted_at=parsed.get("posted_at"), source=source, source_credit=f"{company} careers page", source_tier=tier,
            responsibilities=parsed.get("responsibilities"), qualifications=parsed.get("qualifications"),
            preferred_qualifications=parsed.get("preferred_qualifications"), how_to_apply=parsed.get("how_to_apply"),
            contact_email=parsed.get("contact_email")))
    return out


# ------------------------------------------------------------------ user-driven sources

def _host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").removeprefix("www.")


class CustomFeeds(Source):
    """Reads feeds the user added, such as a regional board's RSS or a niche community's job list."""
    name, tier = "Custom Feed", "Established job feed"

    def configured(self) -> bool:
        return bool(preferences.load().get("custom_feeds"))

    def _one(self, feed: dict, query: str) -> list[dict]:
        url, label = feed["url"], feed.get("name") or _host(feed["url"])
        items = parse_feed(http_get_text(url, retries=0, timeout=12))
        relevant_only = len(items) > 60  # a small niche feed is kept whole; a big general one is filtered
        out = []
        for it in items[:400]:
            if relevant_only and not _matches(query, it["title"], it["company"], it["description"][:600]):
                continue
            out.append(make_job(
                id=f"feed-{stable_id(url, it['url'])}", title=it["title"], company=it["company"] or label,
                location=it["location"], url=it["url"], description=it["description"], posted_at=it["posted_at"],
                tags=it["tags"], source=self.name, source_credit=label, source_tier=self.tier))
        return out

    def fetch(self, query, location):
        feeds = (preferences.load().get("custom_feeds") or [])[:_MAX_FEEDS]
        if not feeds:
            return []
        out, errors = [], []
        with cf.ThreadPoolExecutor(max_workers=_FEED_WORKERS) as pool:
            futs = {pool.submit(self._one, f, query): f for f in feeds}
            for fut in cf.as_completed(futs):
                try:
                    out.extend(fut.result())
                except Exception as e:
                    errors.append(f"{_host(futs[fut]['url'])}: {str(e)[:80]}")
        if errors and not out and len(errors) == len(feeds):
            raise RuntimeError("; ".join(errors[:3]))
        return out


class CareerPages(Source):
    """Reads company careers pages the user added. Works with known ATS links and schema.org JobPosting data."""
    name, tier = "Career Page", "Direct company ATS (career page)"

    def configured(self) -> bool:
        return bool(preferences.load().get("career_pages"))

    def _one(self, page: dict, query: str) -> list[dict]:
        url, label = page["url"], page.get("name") or ""
        hit = board_from_url(url)
        jobs: list[dict] = []
        if hit and hit[0] in BOARDS:
            jobs = BOARDS[hit[0]].fetch_company(hit[1], label)
        else:
            html_text = http_get_text(url, retries=0, timeout=12)
            jobs = jobs_from_jsonld(html_text, url, label, self.name, self.tier)
            if not jobs:
                for board, slug in boards_in_html(html_text)[:3]:
                    if board in BOARDS:
                        try:
                            jobs.extend(BOARDS[board].fetch_company(slug, label))
                        except Exception:
                            continue
        for j in jobs:
            j["found_via"] = "career page"
        if len(jobs) > 40:
            jobs = [j for j in jobs if _matches(query, j.get("title", ""), j.get("description", "")[:400])]
        return jobs

    def fetch(self, query, location):
        pages = (preferences.load().get("career_pages") or [])[:_MAX_FEEDS]
        if not pages:
            return []
        out, errors = [], []
        with cf.ThreadPoolExecutor(max_workers=_FEED_WORKERS) as pool:
            futs = {pool.submit(self._one, p, query): p for p in pages}
            for fut in cf.as_completed(futs):
                try:
                    out.extend(fut.result())
                except Exception as e:
                    errors.append(f"{_host(futs[fut]['url'])}: {str(e)[:80]}")
        if errors and not out and len(errors) == len(pages):
            raise RuntimeError("; ".join(errors[:3]))
        return out


# ------------------------------------------------------------------ public APIs (no key)

class WorkingNomads(Source):
    name, tier = "Working Nomads", "Established job feed"

    def fetch(self, query, location):
        data = http_get_json("https://www.workingnomads.com/api/exposed_jobs/")
        out = []
        for j in data if isinstance(data, list) else []:
            title, company = j.get("title") or "", j.get("company_name") or ""
            desc = j.get("description") or ""
            if not title or not j.get("url") or not _matches(query, title, company, j.get("tags", ""), desc[:800]):
                continue
            tags = j.get("tags")
            tags = [t.strip() for t in tags.split(",")] if isinstance(tags, str) else (tags or [])
            out.append(make_job(
                id=f"wn-{stable_id(j['url'])}", title=title, company=company, location=j.get("location") or "Remote",
                work_mode="Remote", url=j["url"], description=desc, posted_at=j.get("pub_date"), tags=tags[:8],
                source=self.name, source_credit="Working Nomads", source_tier=self.tier))
            if len(out) >= 80:
                break
        return out


class TheMuse(Source):
    name, tier = "The Muse", "Established job feed"
    _CATEGORIES = (
        (r"data|analyt|machine learning|\bml\b|\bai\b|scientist", "Data and Analytics"),
        (r"design|\bux\b|\bui\b", "Design and UX"),
        (r"product manager|product owner", "Product"),
        (r"market|seo|content|growth", "Marketing"),
        (r"sales|account exec|business develop", "Sales"),
        (r"devops|software|developer|engineer|backend|frontend|full.?stack|programmer", "Software Engineering"),
    )

    def _category(self, query: str) -> str:
        for pat, cat in self._CATEGORIES:
            if re.search(pat, (query or "").lower()):
                return cat
        return ""

    def fetch(self, query, location):
        out = []
        cat = self._category(query)
        for page in range(3):
            params = [("page", page)]
            if cat:
                params.append(("category", cat))
            data = http_get_json("https://www.themuse.com/api/public/jobs?" + urllib.parse.urlencode(params))
            for j in data.get("results", []) if isinstance(data, dict) else []:
                title = j.get("name") or ""
                company = (j.get("company") or {}).get("name") or ""
                locs = ", ".join(x.get("name", "") for x in j.get("locations", []) if isinstance(x, dict))
                url = (j.get("refs") or {}).get("landing_page") or ""
                if not title or not url or not _matches(query, title, company):
                    continue
                levels = ", ".join(x.get("short_name") or x.get("name", "") for x in j.get("levels", []) if isinstance(x, dict))
                out.append(make_job(
                    id=f"muse-{j.get('id')}", title=title, company=company, location=locs,
                    work_mode="Remote" if "flexible" in locs.lower() or "remote" in locs.lower() else "",
                    seniority=levels, url=url, description=j.get("contents"), posted_at=j.get("publication_date"),
                    source=self.name, source_credit="The Muse", source_tier=self.tier))
            if page + 1 >= int((data or {}).get("page_count") or 0):
                break
        return out


class Arbeitsagentur(Source):
    """Germany's public employment service. Official, free, and covers many small employers."""
    name, tier = "Arbeitsagentur", "Major job board"
    _API = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pi/jobs"
    _KEY = {"X-API-Key": "jobboerse-jobsuche"}

    def fetch(self, query, location):
        params = {"was": query or "", "size": 50, "page": 1, "angebotsart": 1}
        if location and regions.country_of_location(location) == "DE":
            params["wo"] = location.split(",")[0].strip()
        data = http_get_json(self._API + "?" + urllib.parse.urlencode(params), headers=self._KEY)
        out = []
        for j in data.get("stellenangebote", []) if isinstance(data, dict) else []:
            ref, title = j.get("refnr"), j.get("titel")
            if not ref or not title:
                continue
            place = j.get("arbeitsort") or {}
            loc = ", ".join(x for x in (place.get("ort"), place.get("region"), place.get("land") or "Deutschland") if x)
            out.append(make_job(
                id=f"ba-{ref}", title=title, company=j.get("arbeitgeber"), location=loc,
                url=j.get("externeUrl") or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{urllib.parse.quote(ref)}",
                description=j.get("beruf") or "", posted_at=j.get("aktuelleVeroeffentlichungsdatum") or j.get("eintrittsdatum"),
                source=self.name, source_credit="Bundesagentur fuer Arbeit", source_tier=self.tier, needs_enrichment=True))
        return out

    def enrich(self, job):
        m = re.search(r"jobdetail/([^/?#]+)", job.get("url", "") or "")
        ref = urllib.parse.unquote(m.group(1)) if m else job.get("id", "").removeprefix("ba-")
        if not ref:
            return job
        enc = base64.b64encode(ref.encode()).decode()
        d = http_get_json(f"https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pi/jobdetails/{enc}", headers=self._KEY)
        text = html_to_text(d.get("stellenbeschreibung") or "", 12000)
        if text:
            job["description"] = text
            job["enriched"] = True
            job["needs_enrichment"] = False
        return job


NEW_SOURCES = (CustomFeeds(), CareerPages(), WorkingNomads(), TheMuse(), Arbeitsagentur())
