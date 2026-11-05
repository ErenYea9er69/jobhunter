"""Regional and national job boards, by country, for the "Regional Boards" source.

The big boards show the same famous employers. Local boards list the small and mid-size
companies that never post on LinkedIn. This catalog names well-known local boards per country.

What is verified and what is not:

* The sites exist. Nothing in this list is invented.
* Nobody has checked here whether each site publishes schema.org JobPosting data, or whether its
  robots.txt allows reading. The crawler obeys robots.txt and returns zero jobs when a site says no
  or has no readable job data. ``source_health`` then shows zero for that source.
* You can add your own sites with ``add_job_source(kind="site", value=<url>)``. Use
  ``discover_job_source`` first to see how a site can be read.
"""

from __future__ import annotations

from typing import Optional

# country code -> list of (display name, root url)
BOARDS: dict[str, tuple[tuple[str, str], ...]] = {
    "TN": (("Keejob", "https://www.keejob.com"), ("Tanitjobs", "https://www.tanitjobs.com"),
           ("Emploi Tunisie", "https://www.emploitunisie.com")),
    "MA": (("ReKrute", "https://www.rekrute.com"), ("Emploi.ma", "https://www.emploi.ma")),
    "DZ": (("Emploitic", "https://www.emploitic.com"),),
    "EG": (("Wuzzuf", "https://wuzzuf.net"),),
    "NG": (("Jobberman", "https://www.jobberman.com"),),
    "KE": (("BrighterMonday Kenya", "https://www.brightermonday.co.ke"),),
    "ZA": (("Careers24", "https://www.careers24.com"),),
}

COUNTRIES: tuple[str, ...] = tuple(BOARDS)


def sites_for(country: str) -> list[dict]:
    """Sites to read for one country code, as ``{name, url}`` dicts."""
    return [{"name": n, "url": u} for n, u in BOARDS.get((country or "").upper(), ())]


def find(url_or_name: str) -> Optional[dict]:
    """Look a catalog entry up by name or URL. Returns None when it is not in the catalog."""
    needle = (url_or_name or "").strip().lower().rstrip("/")
    for country, rows in BOARDS.items():
        for name, url in rows:
            if needle in (name.lower(), url.lower().rstrip("/")):
                return {"name": name, "url": url, "country": country}
    return None
