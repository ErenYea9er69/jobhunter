"""More employer applicant-tracking systems, and a router that turns a careers URL into a board.

Small and mid-size employers, including most regional ones, rarely use Greenhouse or Lever.
They use Recruitee, Personio, Teamtailor, BambooHR, Breezy and similar tools. Each of these
publishes a public job list that needs no account. These adapters read those public lists.

Response shapes follow each vendor's public documentation. They were written without live
network access, so ``tests/fixtures`` pins the shapes and the pipeline's source health shows
any adapter that stops matching a vendor's format.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Optional

from . import BOARDS, Lever, _Board, make_job
from ..util import html_to_text, http_get_json, http_get_text, safe_parse_xml

_RESERVED_SUBDOMAINS = {"www", "api", "app", "apps", "careers", "jobs", "support", "help", "blog", "static", "cdn",
                        "assets", "status", "docs", "developers", "marketing", "login", "auth", "eu", "us"}


def _title_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _local(tag: str) -> str:
    """Drop the XML namespace from a tag name."""
    return tag.rsplit("}", 1)[-1] if tag else ""


def _item_fields(item) -> dict:
    """Flatten an RSS/Atom item into ``{local_tag: text}``. The first occurrence wins."""
    out: dict = {}
    for child in list(item):
        key = _local(child.tag).lower()
        if key not in out:
            text = (child.text or "").strip()
            if not text and child.attrib.get("href"):
                text = child.attrib["href"]
            if not text and len(child):
                text = " ".join((c.text or "").strip() for c in child.iter() if (c.text or "").strip())
            out[key] = text
    return out


class LeverEU(Lever):
    """Lever's European data centre. A company is on one instance or the other, never both."""
    name = board = "Lever EU"
    api_base = "https://api.eu.lever.co"


class Recruitee(_Board):
    name = board = "Recruitee"

    def fetch_company(self, slug, company_name=""):
        data = http_get_json(f"https://{slug}.recruitee.com/api/offers/")
        name = company_name or _title_slug(slug)
        out = []
        for j in data.get("offers", []) if isinstance(data, dict) else []:
            if j.get("status") not in (None, "published"):
                continue
            loc = j.get("location") or ", ".join(x for x in (j.get("city"), j.get("country")) if x)
            sal = j.get("salary") or {}
            salary = ""
            if isinstance(sal, dict) and sal.get("min"):
                salary = f"{sal.get('min')} - {sal.get('max') or sal.get('min')} {sal.get('currency', '')}".strip()
            mode = "Remote" if j.get("remote") else ("Hybrid" if j.get("hybrid") else "")
            out.append(make_job(
                id=f"recruitee-{slug}-{j.get('id')}", title=j.get("title"), company=name, location=loc,
                work_mode=mode, salary=salary, job_type=str(j.get("employment_type_code") or "").replace("_", " "),
                url=j.get("careers_url") or f"https://{slug}.recruitee.com/o/{j.get('slug', '')}",
                description=f"{j.get('description') or ''}\n{j.get('requirements') or ''}",
                posted_at=j.get("published_at") or j.get("created_at"), source=self.name,
                source_credit=f"{name} on Recruitee", source_tier=self.tier))
        return out


class Personio(_Board):
    name = board = "Personio"

    def fetch_company(self, slug, company_name=""):
        xml, last = None, None
        for host in ("jobs.personio.de", "jobs.personio.com"):
            try:
                xml = http_get_text(f"https://{slug}.{host}/xml", retries=0)
                if "<position" in xml:
                    base = f"https://{slug}.{host}"
                    break
            except Exception as e:  # try the other domain
                last = e
        else:
            raise last or ValueError("no Personio job feed")
        root = safe_parse_xml(xml)
        name = company_name or _title_slug(slug)
        out = []
        for pos in root.iter("position"):
            f = {_local(c.tag): (c.text or "").strip() for c in pos if len(c) == 0}
            desc = "\n".join(f"{jd.findtext('name') or ''}\n{html_to_text(jd.findtext('value') or '')}"
                             for jd in pos.iter("jobDescription"))
            pid = f.get("id")
            if not pid or not f.get("name"):
                continue
            out.append(make_job(
                id=f"personio-{slug}-{pid}", title=f["name"], company=name, location=f.get("office", ""),
                job_type=f"{f.get('schedule', '')} {f.get('employmentType', '')}".strip(),
                url=f"{base}/job/{pid}", description=desc, posted_at=f.get("createdAt"), seniority=f.get("seniority", ""),
                source=self.name, source_credit=f"{name} on Personio", source_tier=self.tier))
        return out


class Teamtailor(_Board):
    name = board = "Teamtailor"

    def fetch_company(self, slug, company_name=""):
        root = safe_parse_xml(http_get_text(f"https://{slug}.teamtailor.com/jobs.rss", retries=0))
        name = company_name or _title_slug(slug)
        out = []
        for item in root.iter("item"):
            f = _item_fields(item)
            link = f.get("link") or ""
            if not f.get("title") or not link:
                continue
            remote = (f.get("remotestatus") or "").lower()
            mode = "Remote" if remote in ("fully", "remote") else ("Hybrid" if remote == "hybrid" else "")
            uid = re.sub(r"\W+", "-", f.get("guid") or link)[-60:]
            out.append(make_job(
                id=f"teamtailor-{slug}-{uid}", title=f["title"],
                company=name, location=f.get("locations") or f.get("location", ""), work_mode=mode, url=link,
                description=f.get("description", ""), posted_at=f.get("pubdate"), source=self.name,
                source_credit=f"{name} on Teamtailor", source_tier=self.tier))
        return out


class BambooHR(_Board):
    name = board = "BambooHR"

    def fetch_company(self, slug, company_name=""):
        data = http_get_json(f"https://{slug}.bamboohr.com/careers/list", headers={"Accept": "application/json"})
        name = company_name or _title_slug(slug)
        out = []
        for j in data.get("result", []) if isinstance(data, dict) else []:
            loc = j.get("location") or {}
            ats = j.get("atsLocation") or {}
            place = ", ".join(x for x in (loc.get("city") or ats.get("city"), loc.get("state") or ats.get("state"),
                                          ats.get("country")) if x)
            remote = j.get("isRemote") or str(j.get("locationType")) == "1"
            out.append(make_job(
                id=f"bamboohr-{slug}-{j.get('id')}", title=j.get("jobOpeningName"), company=name, location=place,
                work_mode="Remote" if remote else "", job_type=j.get("employmentStatusLabel"),
                url=f"https://{slug}.bamboohr.com/careers/{j.get('id')}", description="", source=self.name,
                source_credit=f"{name} on BambooHR", source_tier=self.tier, needs_enrichment=True))
        return out

    def enrich(self, job):
        m = re.search(r"https://([a-z0-9-]+)\.bamboohr\.com/careers/(\d+)", job.get("url", ""))
        if not m:
            return job
        d = http_get_json(f"https://{m.group(1)}.bamboohr.com/careers/{m.group(2)}/detail",
                          headers={"Accept": "application/json"})
        opening = ((d or {}).get("result") or {}).get("jobOpening") or {}
        if opening.get("description"):
            job["description"] = html_to_text(opening["description"], 12000)
            job["enriched"] = True
            job["needs_enrichment"] = False
        return job


class Breezy(_Board):
    name = board = "Breezy"

    def fetch_company(self, slug, company_name=""):
        data = http_get_json(f"https://{slug}.breezy.hr/json")
        name = company_name or _title_slug(slug)
        out = []
        for j in data if isinstance(data, list) else []:
            loc = j.get("location") or {}
            country = loc.get("country") or {}
            place = loc.get("name") or ", ".join(x for x in (loc.get("city"), country.get("name") if isinstance(country, dict) else country) if x)
            jtype = j.get("type") or {}
            out.append(make_job(
                id=f"breezy-{slug}-{j.get('friendly_id') or j.get('id')}", title=j.get("name"), company=name,
                location=place, work_mode="Remote" if loc.get("is_remote") else "",
                job_type=jtype.get("name") if isinstance(jtype, dict) else jtype, url=j.get("url"),
                description="", posted_at=j.get("published_date"), source=self.name,
                source_credit=f"{name} on Breezy", source_tier=self.tier, needs_enrichment=True))
        return out


NEW_BOARDS = (LeverEU(), Recruitee(), Personio(), Teamtailor(), BambooHR(), Breezy())
BOARDS.update({b.board.lower(): b for b in NEW_BOARDS})


# ------------------------------------------------------------------ URL router

_ROUTES = [
    (re.compile(r"job-boards(?:\.eu)?\.greenhouse\.io/([a-z0-9_-]+)", re.I), "greenhouse"),
    (re.compile(r"boards\.(?:eu\.)?greenhouse\.io/([a-z0-9_-]+)", re.I), "greenhouse"),
    (re.compile(r"boards-api\.greenhouse\.io/v1/boards/([a-z0-9_-]+)", re.I), "greenhouse"),
    (re.compile(r"greenhouse\.io/embed/job_board\?(?:[^#\s\"']*&)?for=([a-z0-9_-]+)", re.I), "greenhouse"),
    (re.compile(r"jobs\.eu\.lever\.co/([a-z0-9_-]+)", re.I), "lever eu"),
    (re.compile(r"jobs\.lever\.co/([a-z0-9_-]+)", re.I), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com/([a-z0-9._%-]+)", re.I), "ashby"),
    (re.compile(r"apply\.workable\.com/([a-z0-9_-]+)", re.I), "workable"),
    (re.compile(r"jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I), "smartrecruiters"),
    (re.compile(r"([a-z0-9-]+)\.recruitee\.com", re.I), "recruitee"),
    (re.compile(r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)", re.I), "personio"),
    (re.compile(r"([a-z0-9-]+)\.teamtailor\.com", re.I), "teamtailor"),
    (re.compile(r"([a-z0-9-]+)\.bamboohr\.com", re.I), "bamboohr"),
    (re.compile(r"([a-z0-9-]+)\.breezy\.hr", re.I), "breezy"),
    (re.compile(r"([a-z0-9-]+)\.pinpointhq\.com", re.I), "pinpoint"),
]
_BAD_SLUGS = _RESERVED_SUBDOMAINS | {"embed", "v1", "boards", "job_board"}


def board_from_url(url: str) -> Optional[tuple[str, str]]:
    """Return ``(board_type, slug)`` when the URL points at a known ATS, else None."""
    if not url:
        return None
    text = urllib.parse.unquote(url) if "%" in url and "ashbyhq" not in url else url
    for pattern, board in _ROUTES:
        m = pattern.search(text)
        if m:
            slug = m.group(1).strip("/").lower() if board != "smartrecruiters" else m.group(1).strip("/")
            if slug and slug not in _BAD_SLUGS:
                return board, slug
    return None


def boards_in_html(html_text: str) -> list[tuple[str, str]]:
    """Find ATS boards that a careers page links to or embeds. Order of first appearance, no repeats."""
    found: list[tuple[str, str]] = []
    for m in re.finditer(r"https?://[^\s\"'<>)\\]+", html_text or ""):
        hit = board_from_url(m.group(0))
        if hit and hit not in found:
            found.append(hit)
    return found
