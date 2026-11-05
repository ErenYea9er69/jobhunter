"""Countries, cities and which job sources serve which places.

This is the single place that answers "where is this person looking?" and "which sources are
worth calling for that?". The old pipeline called India's Naukri and France's HelloWork for
every user. With this module a source declares the regions it serves and the pipeline skips
sources that cannot return anything useful.

Region tokens used by sources:
    "*"        always eligible (company career boards, global aggregators)
    "REMOTE"   remote-only boards; eligible when the person accepts remote work
    "EU", "MENA", "AFRICA", "GCC"   groups that expand to country codes
    "FR", "DE", ...   ISO 3166-1 alpha-2 country codes
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

# code -> (name, aliases/cities that identify it, languages)
_COUNTRIES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "TN": ("Tunisia", ("tunisie", "tunis", "sfax", "sousse", "ariana", "ben arous", "bizerte", "nabeul", "monastir", "la marsa", "lac 2", "gabes", "kairouan"), ("ar", "fr")),
    "MA": ("Morocco", ("maroc", "casablanca", "rabat", "marrakech", "tangier", "tanger", "fes", "agadir"), ("ar", "fr")),
    "DZ": ("Algeria", ("algerie", "algérie", "algiers", "alger", "oran", "constantine"), ("ar", "fr")),
    "EG": ("Egypt", ("cairo", "giza", "alexandria", "new cairo"), ("ar", "en")),
    "SA": ("Saudi Arabia", ("ksa", "riyadh", "jeddah", "dammam", "khobar"), ("ar", "en")),
    "AE": ("United Arab Emirates", ("uae", "dubai", "abu dhabi", "sharjah", "emirates"), ("en", "ar")),
    "QA": ("Qatar", ("doha",), ("en", "ar")),
    "KW": ("Kuwait", ("kuwait city",), ("en", "ar")),
    "BH": ("Bahrain", ("manama",), ("en", "ar")),
    "OM": ("Oman", ("muscat",), ("en", "ar")),
    "JO": ("Jordan", ("amman",), ("en", "ar")),
    "LB": ("Lebanon", ("beirut",), ("en", "ar", "fr")),
    "NG": ("Nigeria", ("lagos", "abuja"), ("en",)),
    "KE": ("Kenya", ("nairobi", "mombasa"), ("en",)),
    "GH": ("Ghana", ("accra",), ("en",)),
    "ZA": ("South Africa", ("johannesburg", "cape town", "pretoria", "durban"), ("en",)),
    "SN": ("Senegal", ("dakar",), ("fr",)),
    "CI": ("Ivory Coast", ("cote d'ivoire", "côte d'ivoire", "abidjan"), ("fr",)),
    "FR": ("France", ("paris", "lyon", "marseille", "toulouse", "lille", "bordeaux", "nantes", "nice", "strasbourg", "rennes"), ("fr",)),
    "DE": ("Germany", ("deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln", "stuttgart", "düsseldorf"), ("de",)),
    "GB": ("United Kingdom", ("uk", "england", "scotland", "wales", "great britain", "london", "manchester", "birmingham", "edinburgh", "glasgow", "bristol", "leeds"), ("en",)),
    "IE": ("Ireland", ("dublin", "cork", "galway"), ("en",)),
    "NL": ("Netherlands", ("holland", "amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague"), ("nl", "en")),
    "BE": ("Belgium", ("brussels", "bruxelles", "antwerp", "ghent"), ("nl", "fr")),
    "LU": ("Luxembourg", (), ("fr", "de")),
    "CH": ("Switzerland", ("zurich", "zürich", "geneva", "genève", "basel", "bern", "lausanne"), ("de", "fr")),
    "AT": ("Austria", ("vienna", "wien", "graz", "salzburg"), ("de",)),
    "ES": ("Spain", ("madrid", "barcelona", "valencia", "seville", "malaga"), ("es",)),
    "PT": ("Portugal", ("lisbon", "lisboa", "porto"), ("pt",)),
    "IT": ("Italy", ("rome", "roma", "milan", "milano", "turin", "torino", "bologna"), ("it",)),
    "PL": ("Poland", ("warsaw", "krakow", "kraków", "wroclaw", "gdansk", "poznan"), ("pl",)),
    "SE": ("Sweden", ("stockholm", "gothenburg", "malmö", "malmo"), ("sv", "en")),
    "NO": ("Norway", ("oslo", "bergen"), ("no", "en")),
    "DK": ("Denmark", ("copenhagen", "aarhus"), ("da", "en")),
    "FI": ("Finland", ("helsinki", "espoo", "tampere"), ("fi", "en")),
    "EE": ("Estonia", ("tallinn", "tartu"), ("en", "et")),
    "LT": ("Lithuania", ("vilnius", "kaunas"), ("en", "lt")),
    "LV": ("Latvia", ("riga",), ("en", "lv")),
    "CZ": ("Czechia", ("czech republic", "prague", "brno"), ("cs", "en")),
    "RO": ("Romania", ("bucharest", "cluj", "timisoara", "iasi"), ("ro", "en")),
    "GR": ("Greece", ("athens", "thessaloniki"), ("el", "en")),
    "TR": ("Turkey", ("türkiye", "turkiye", "istanbul", "ankara", "izmir"), ("tr", "en")),
    "US": ("United States", ("usa", "u.s.", "u.s.a.", "america", "new york", "san francisco", "seattle", "austin", "chicago", "boston", "los angeles"), ("en",)),
    "CA": ("Canada", ("toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary", "ontario", "quebec", "québec"), ("en", "fr")),
    "MX": ("Mexico", ("mexico city", "guadalajara", "monterrey"), ("es",)),
    "BR": ("Brazil", ("brasil", "sao paulo", "são paulo", "rio de janeiro"), ("pt",)),
    "AR": ("Argentina", ("buenos aires", "cordoba"), ("es",)),
    "CO": ("Colombia", ("bogota", "bogotá", "medellin"), ("es",)),
    "IN": ("India", ("bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune", "chennai", "gurgaon", "gurugram", "noida"), ("en",)),
    "PK": ("Pakistan", ("karachi", "lahore", "islamabad"), ("en",)),
    "SG": ("Singapore", (), ("en",)),
    "AU": ("Australia", ("sydney", "melbourne", "brisbane", "perth"), ("en",)),
    "NZ": ("New Zealand", ("auckland", "wellington"), ("en",)),
    "JP": ("Japan", ("tokyo", "osaka"), ("ja", "en")),
}

GROUPS: dict[str, set[str]] = {
    "MENA": {"TN", "MA", "DZ", "EG", "SA", "AE", "QA", "KW", "BH", "OM", "JO", "LB", "TR"},
    "GCC": {"SA", "AE", "QA", "KW", "BH", "OM"},
    "AFRICA": {"TN", "MA", "DZ", "EG", "NG", "KE", "GH", "ZA", "SN", "CI"},
    "EU": {"FR", "DE", "IE", "NL", "BE", "LU", "AT", "ES", "PT", "IT", "PL", "SE", "DK", "FI", "EE", "LT", "LV", "CZ", "RO", "GR"},
}

# Countries where Indeed runs a local site. Tunisia and Algeria have none, so those searches skip Indeed.
INDEED_DOMAINS: dict[str, str] = {
    "US": "www.indeed.com", "GB": "uk.indeed.com", "CA": "ca.indeed.com", "AU": "au.indeed.com",
    "DE": "de.indeed.com", "FR": "fr.indeed.com", "ES": "es.indeed.com", "IT": "it.indeed.com",
    "NL": "nl.indeed.com", "BE": "be.indeed.com", "CH": "ch.indeed.com", "AT": "at.indeed.com",
    "IE": "ie.indeed.com", "PL": "pl.indeed.com", "SE": "se.indeed.com", "NO": "no.indeed.com",
    "DK": "dk.indeed.com", "PT": "pt.indeed.com", "IN": "in.indeed.com", "SG": "sg.indeed.com",
    "AE": "ae.indeed.com", "SA": "sa.indeed.com", "EG": "eg.indeed.com", "MA": "ma.indeed.com",
    "ZA": "za.indeed.com", "NG": "ng.indeed.com", "KE": "ke.indeed.com", "MX": "mx.indeed.com",
    "BR": "br.indeed.com", "AR": "ar.indeed.com", "NZ": "nz.indeed.com", "JP": "jp.indeed.com",
    "TR": "tr.indeed.com", "QA": "qa.indeed.com", "KW": "kw.indeed.com", "BH": "bh.indeed.com",
    "OM": "om.indeed.com", "JO": "jo.indeed.com", "LB": "lb.indeed.com", "PK": "pk.indeed.com",
    "GH": "gh.indeed.com",
}

# Adzuna publishes country-specific APIs for these codes (lower-case in the URL).
ADZUNA_COUNTRIES = {"AT", "AU", "BE", "BR", "CA", "CH", "DE", "ES", "FR", "GB", "IN", "IT", "MX", "NL", "NZ", "PL", "SG", "US", "ZA"}

_NAME_TO_CODE: dict[str, str] = {}
for _code, (_name, _aliases, _langs) in _COUNTRIES.items():
    _NAME_TO_CODE[_name.lower()] = _code
    _NAME_TO_CODE[_code.lower()] = _code
    for _a in _aliases:
        _NAME_TO_CODE[_a.lower()] = _code
_NAME_TO_CODE.update({"great britain": "GB", "england": "GB", "usa": "US", "emirates": "AE", "ivory coast": "CI"})

_US_STATES = {"al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me",
              "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or",
              "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc"}


def country_name(code: str) -> str:
    return _COUNTRIES.get((code or "").upper(), ("", (), ()))[0] or code


def languages_of(code: str) -> tuple[str, ...]:
    return _COUNTRIES.get((code or "").upper(), ("", (), ()))[2]


def known_country_codes() -> list[str]:
    return sorted(_COUNTRIES)


def to_code(value: str) -> Optional[str]:
    """Turn a country name, code or city into an ISO code. Returns None when unknown.

    Two-letter strings are only read as codes when they are upper-case or an exact known code,
    so "in" and "it" inside a sentence never turn into India or Italy.
    """
    s = (value or "").strip()
    if not s:
        return None
    low = s.lower()
    if len(s) == 2 and s.isalpha():
        return s.upper() if s.upper() in _COUNTRIES else None
    if low in _NAME_TO_CODE:
        return _NAME_TO_CODE[low]
    return None


def country_of_location(text: str) -> Optional[str]:
    """Best guess of the country for a free-text location such as ``"Sfax, Tunisia"``."""
    s = (text or "").strip()
    if not s:
        return None
    low = s.lower()
    # Longest alias first so "new york" wins over "york"
    parts = [p.strip() for p in re.split(r"[,/|;]", low) if p.strip()]
    # "Austin, TX" or "San Francisco, CA": a trailing two-letter US state wins unless an earlier part names another country.
    if len(parts) >= 2 and parts[-1] in _US_STATES and len(parts[-1]) == 2:
        earlier = {_NAME_TO_CODE.get(p) for p in parts[:-1]} - {None}
        if not earlier or earlier == {"US"}:
            return "US"
    for part in reversed(parts):  # the last part is usually the country
        if part in _NAME_TO_CODE and (len(part) > 2 or part.upper() == s.strip()[-2:].upper()):
            return _NAME_TO_CODE[part]
    for alias in sorted(_NAME_TO_CODE, key=len, reverse=True):
        if len(alias) <= 3:
            continue
        if re.search(rf"(?<![a-zà-ÿ]){re.escape(alias)}(?![a-zà-ÿ])", low):
            return _NAME_TO_CODE[alias]
    return None


def expand(tokens: Iterable[str]) -> set[str]:
    """Expand group tokens such as ``MENA`` into country codes."""
    out: set[str] = set()
    for t in tokens:
        t = (t or "").strip().upper()
        if not t:
            continue
        if t in GROUPS:
            out |= GROUPS[t]
        else:
            out.add(t)
    return out


def resolve_targets(prefs: Optional[dict] = None, profile: Optional[dict] = None, location: str = "") -> list[str]:
    """Ordered, de-duplicated country codes the person wants to work in.

    Order of evidence: explicit preference, the location passed to this search, the resume
    location and preferred locations. An empty list means "unknown", and callers should then
    run every source as before.
    """
    prefs = prefs or {}
    profile = profile or {}
    out: list[str] = []

    def add(code: Optional[str]):
        if code and code not in out:
            out.append(code)

    for c in prefs.get("target_countries") or []:
        add(to_code(c) or country_of_location(c))
    if location and location.strip().lower() not in ("remote", "anywhere", "worldwide"):
        add(country_of_location(location) or to_code(location))
    if not out:
        add(country_of_location(profile.get("location", "")))
        for loc in profile.get("preferred_locations") or []:
            add(country_of_location(loc) or to_code(loc))
    if not out:
        add(to_code(prefs.get("home_country", "")))
    return out


def wants_remote(prefs: Optional[dict] = None, profile: Optional[dict] = None) -> bool:
    """Whether remote-only boards are worth calling.

    Any or Remote: yes. Onsite: no, because a remote-only board cannot return what was asked for.
    Hybrid: follows ``include_worldwide_remote`` (on by default).
    """
    prefs = prefs or {}
    profile = profile or {}
    mode = (prefs.get("work_mode") or profile.get("work_mode") or "Any").strip().lower()
    if mode in ("onsite", "on-site", "on site"):
        return False
    if mode == "hybrid":
        return bool(prefs.get("include_worldwide_remote", True))
    return True


def source_is_eligible(regions: Iterable[str], targets: list[str], remote_ok: bool) -> bool:
    """Decide whether a source with the given region tokens is worth calling."""
    toks = {str(r).upper() for r in regions or ["*"]}
    if "*" in toks:
        return True
    if "REMOTE" in toks and remote_ok:
        return True
    if not targets:
        # Location unknown: run everything except sources that only serve one named country.
        return "REMOTE" in toks or bool(toks & {"EU", "MENA", "AFRICA", "GCC"}) or len(toks) > 1
    return bool(expand(toks - {"REMOTE"}) & set(targets))
