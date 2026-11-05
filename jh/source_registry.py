"""One catalog of every job source: what it is, where it works, and whether to call it now.

The pipeline asks this module two questions for each source:

* ``skip_reason``  should this source be skipped for this person and place?
* ``plan``         which calls should run (for example Indeed once per target country)?

The catalog describes the real source classes in ``jh.sources``. Nothing here is a stub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import regional_boards, regions


@dataclass(frozen=True)
class SourceInfo:
    name: str
    kind: str                     # company boards | job board | aggregator | remote feed | public API | user-defined
    regions: tuple[str, ...]      # see jh.regions for the tokens
    description: str
    needs_key: tuple[str, ...] = ()
    fanout: str = ""              # "country": one call per target country
    user_configured: bool = False


_ALL_INDEED = tuple(regions.INDEED_DOMAINS)

_INFO = (
    SourceInfo("Company Boards", "company boards", ("*",),
               "Employer career boards on Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio, "
               "Teamtailor, BambooHR and Breezy. Pool = starter list + your watchlist + boards found in other results."),
    SourceInfo("Y Combinator", "company boards", ("*",), "Startups from the Y Combinator directory."),
    SourceInfo("LinkedIn", "job board", ("*",), "LinkedIn public guest search."),
    SourceInfo("Indeed", "job board", _ALL_INDEED, "Indeed, using the local site of each target country.", fanout="country"),
    SourceInfo("ZipRecruiter", "job board", ("US", "CA"), "ZipRecruiter (United States and Canada)."),
    SourceInfo("Bayt", "job board", ("MENA",), "Bayt, the main Middle East and North Africa board.", fanout="country"),
    SourceInfo("Naukri", "job board", ("IN",), "Naukri, India's largest board."),
    SourceInfo("HelloWork", "job board", ("FR",), "HelloWork, French job board."),
    SourceInfo("Arbeitsagentur", "public API", ("DE",), "Germany's public employment service. Official and free."),
    SourceInfo("Adzuna", "aggregator", tuple(regions.ADZUNA_COUNTRIES),
               "Adzuna aggregator in 19 countries. Needs a free API key.", needs_key=("ADZUNA_APP_ID", "ADZUNA_APP_KEY"), fanout="country"),
    SourceInfo("Hacker News", "remote feed", ("*",), "Hacker News 'Who is hiring' threads. Mostly small companies."),
    SourceInfo("Himalayas", "remote feed", ("REMOTE",), "Himalayas remote jobs."),
    SourceInfo("Remotive", "remote feed", ("REMOTE",), "Remotive remote jobs."),
    SourceInfo("Jobicy", "remote feed", ("REMOTE",), "Jobicy remote jobs."),
    SourceInfo("RemoteOK", "remote feed", ("REMOTE",), "Remote OK."),
    SourceInfo("We Work Remotely", "remote feed", ("REMOTE",), "We Work Remotely RSS."),
    SourceInfo("Working Nomads", "remote feed", ("REMOTE",), "Working Nomads curated remote jobs."),
    SourceInfo("Arbeitnow", "remote feed", ("EU", "REMOTE"), "Arbeitnow: Europe-focused jobs including visa-sponsored roles."),
    SourceInfo("The Muse", "aggregator", ("US", "GB", "CA", "REMOTE"), "The Muse company-curated listings."),
    SourceInfo("Regional Boards", "regional boards", regional_boards.COUNTRIES,
               "Local job boards that list small and mid-size employers (for example Keejob in Tunisia, ReKrute in Morocco). "
               "Read through schema.org job data and sitemaps, with robots.txt respected, in the local language too.", fanout="country"),
    SourceInfo("Job Sites", "user-defined", ("*",), "Sites you added with add_job_source(kind='site').", user_configured=True),
    SourceInfo("Jooble", "aggregator", ("*",), "Jooble aggregator. Collects postings from many small local boards. Needs a free key.",
               needs_key=("JOOBLE_API_KEY",), fanout="country"),
    SourceInfo("JobTech", "public API", ("SE",), "Sweden's public employment service (JobTech Dev). Open API, no key."),
    SourceInfo("Custom Feed", "user-defined", ("*",), "RSS, Atom or JSON feeds you added with add_job_source.", user_configured=True),
    SourceInfo("Career Page", "user-defined", ("*",), "Company career pages you added with add_job_source.", user_configured=True),
)
INFO: dict[str, SourceInfo] = {i.name: i for i in _INFO}


def info(name: str) -> Optional[SourceInfo]:
    return INFO.get(name)


def catalog() -> list[dict]:
    """Plain-dict description of every source, for tools and docs."""
    out = []
    for i in _INFO:
        shown = [r for r in i.regions if r not in regions.INDEED_DOMAINS] if i.name == "Indeed" else list(i.regions)
        out.append({
            "name": i.name, "kind": i.kind,
            "regions": ["worldwide"] if "*" in i.regions else (shown or ["countries with a local Indeed site"]),
            "needs_api_key": bool(i.needs_key), "description": i.description,
        })
    return out


def _is_selected(name: str, prefs: dict) -> tuple[bool, str]:
    enabled = prefs.get("enabled_sources") or []
    disabled = prefs.get("disabled_sources") or []
    if enabled and name not in enabled:
        return False, "Not in your enabled_sources list."
    if name in disabled:
        return False, "You turned this source off."
    return True, ""


def skip_reason(name: str, prefs: dict, targets: list[str], remote_ok: bool, configured: bool = True) -> Optional[tuple[str, str, bool]]:
    """Return ``(state, reason, silent)`` when the source should not run, else None.

    ``silent`` skips are left out of the status list because they are not news
    (for example, no custom feeds have been added).
    """
    i = INFO.get(name)
    ok, why = _is_selected(name, prefs)
    if not ok:
        return "disabled", why, False
    if i is None:
        return None
    if i.user_configured and not configured:
        return "skipped", "Nothing added yet.", True
    if not regions.source_is_eligible(i.regions, targets, remote_ok):
        goal = ", ".join(regions.country_name(c) for c in targets) or "your location"
        if name == "Indeed":
            return "skipped", f"Indeed has no local site for {goal}.", False
        if len(i.regions) > 8:
            return "skipped", f"Does not serve {goal}.", False
        return "skipped", f"Serves {', '.join(i.regions)}; you are targeting {goal}.", False
    return None


def _location_for(country: str, location: str) -> str:
    if location and regions.country_of_location(location) == country:
        return location
    return regions.country_name(country)


def plan(name: str, targets: list[str], location: str, remote_ok: bool) -> list[dict]:
    """The calls to make for one source: a list of ``{suffix, location, kwargs}``. Empty means skip."""
    default = [{"suffix": "", "location": location, "kwargs": {}}]
    i = INFO.get(name)
    if not i or not i.fanout:
        return default
    if name == "Indeed":
        picks = [c for c in targets if c in regions.INDEED_DOMAINS][:3]
        if not targets:
            return default
        return [{"suffix": f"@{regions.INDEED_DOMAINS[c]}", "location": _location_for(c, location),
                 "kwargs": {"domain": regions.INDEED_DOMAINS[c]}} for c in picks]
    if name == "Adzuna":
        picks = [c for c in targets if c in regions.ADZUNA_COUNTRIES][:3]
        if not targets:
            return default
        return [{"suffix": f"@{c.lower()}", "location": _location_for(c, location),
                 "kwargs": {"country": c.lower()}} for c in picks]
    if name == "Regional Boards":
        picks = [c for c in targets if c in regional_boards.COUNTRIES][:3]
        return [{"suffix": f"@{c.lower()}", "location": _location_for(c, location), "kwargs": {"country": c}} for c in picks]
    if name == "Jooble":
        picks = targets[:3]
        if not picks:
            return default
        return [{"suffix": f"@{c.lower()}", "location": _location_for(c, location), "kwargs": {"country": c}} for c in picks]
    if name == "Bayt":
        mena = regions.GROUPS["MENA"]
        picks = [c for c in targets if c in mena][:3]
        if not targets:
            return default
        return [{"suffix": f"@{c.lower()}", "location": _location_for(c, location), "kwargs": {}} for c in picks]
    return default
