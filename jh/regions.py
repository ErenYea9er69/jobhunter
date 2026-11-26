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
    "BD": ("Bangladesh", ("dhaka", "chittagong"), ("bn", "en")),
    "LK": ("Sri Lanka", ("colombo", "kandy"), ("si", "ta", "en")),
    "NP": ("Nepal", ("kathmandu",), ("ne", "en")),
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
    "EUROPE": {"FR", "DE", "IE", "NL", "BE", "LU", "AT", "ES", "PT", "IT", "PL", "SE", "DK", "FI", "EE", "LT", "LV", "CZ", "RO", "GR", "GB", "CH", "NO"},
    "SOUTH ASIA": {"IN", "PK", "BD", "LK", "NP"},
    "SOUTH_ASIA": {"IN", "PK", "BD", "LK", "NP"},
    "NORTH AMERICA": {"US", "CA", "MX"},
    "NORTH_AMERICA": {"US", "CA", "MX"},
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


def resolve_targets(
    prefs: Optional[dict] = None,
    profile: Optional[dict] = None,
    location: str = "",
    allow_profile_fallback: bool = True,
) -> list[str]:
    """Ordered, de-duplicated country codes the person wants to work in.

    Order of evidence: explicit preference, the location passed to this search,
    and (only when ``allow_profile_fallback=True``) the resume location and preferred locations.
    An empty list means "worldwide / remote / unspecified".
    """
    prefs = prefs or {}
    profile = profile or {}
    out: list[str] = []

    def add(code: Optional[str]):
        if code and code not in out:
            out.append(code)

    def add_place_token(tok: str):
        clean = (tok or "").strip()
        if not clean:
            return
        up = clean.upper().replace("-", "_")
        up_sp = clean.upper().replace("_", " ")
        for grp_key in (up, up_sp):
            if grp_key in GROUPS:
                for gc in sorted(GROUPS[grp_key]):
                    add(gc)
                return
        c = country_of_location(clean) or to_code(clean)
        if c:
            add(c)

    remote_keywords = (
        "remote", "remote only", "anywhere", "worldwide", "remote worldwide",
        "worldwide remote", "international remote", "global remote", "remote worldwide (global)",
    )
    loc_clean = (location or "").strip().lower()

    for c in prefs.get("target_countries") or []:
        add_place_token(str(c))
    if loc_clean and loc_clean not in remote_keywords:
        for part in re.split(r"[;/]|\band\b|\bor\b", location, flags=re.I):
            part = part.strip()
            if not part or part.lower() in remote_keywords:
                continue
            c = country_of_location(part) or to_code(part)
            if c:
                add(c)
            else:
                add_place_token(part)
    elif loc_clean and loc_clean in remote_keywords:
        return []

    if allow_profile_fallback and not out and (loc_clean not in remote_keywords):
        add(country_of_location(profile.get("location", "")))
        for loc in profile.get("preferred_locations") or []:
            add_place_token(str(loc))
    if allow_profile_fallback and not out and (loc_clean not in remote_keywords):
        add(to_code(prefs.get("home_country", "")))
    return out


_METHOD_FILLER_RE = re.compile(
    r"\b(?:modern|modrn|classic|clasic|classik|method|outreach|boards|please|thanks|thank you|switch|change|prefer|only\s+in|jobs\s+in|look\s+in|search\s+in|city)\b",
    re.I,
)

_PLACE_TYPO_RE = (
    (re.compile(r"\b(?:remtoe|remte|rmote|remot)\b", re.I), "remote"),
    (re.compile(r"\b(?:worldwde|worlwide|worldwid|wroldwide)\b", re.I), "worldwide"),
    (re.compile(r"\b(?:internatonal|internationl|interantional)\b", re.I), "international"),
    (re.compile(r"\b(?:franec|frnace|franc)\b", re.I), "france"),
    (re.compile(r"\b(?:europ|erope|eurpoe)\b", re.I), "europe"),
    (re.compile(r"\b(?:germny|gremany|geramny)\b", re.I), "germany"),
)


def parse_confirmed_places(reply: str, answers: Optional[dict] = None) -> dict[str, object]:
    """Parse user-confirmed target places from Step 3/5 reply or answers. Never falls back to resume."""
    answers = answers or {}
    raw_items: list[str] = []
    for k in ("locations", "target_place", "location", "place"):
        val = answers.get(k)
        if isinstance(val, list):
            raw_items.extend(str(x).strip() for x in val if str(x).strip())
        elif isinstance(val, str) and val.strip():
            raw_items.append(val.strip())

    src_text = ", ".join(raw_items) if raw_items else (reply or "").strip()
    for rx, canonical in _PLACE_TYPO_RE:
        src_text = rx.sub(canonical, src_text)
    low = src_text.lower()

    places: list[str] = []
    remote_only = False
    worldwide_remote = False
    worldwide = False

    def add_place(p: str):
        if p and p not in places:
            places.append(p)

    # Explicit remote / worldwide variants first
    if re.search(r"\b(?:international|worldwide|global)\s+remote\b|\bremote\s+(?:worldwide|international|global|anywhere)\b", low):
        add_place("Worldwide Remote")
        worldwide_remote = True
    elif re.search(r"\bremote\s+only\b|\bonly\s+remote\b", low):
        add_place("Remote")
        remote_only = True
    elif re.search(r"\b(?:worldwide|anywhere|international|abroad)\b", low) and "remote" not in low:
        add_place("Worldwide")
        worldwide = True

    # Split text cleanly into place segments while keeping "City, Country" or "Country, city X" intact
    cleaned = _METHOD_FILLER_RE.sub(" ", src_text)
    segments = [s.strip(" .!?:;") for s in re.split(r"[\n;/]|\band\b|\bor\b|\+", cleaned, flags=re.I) if s.strip(" .!?:;")]
    expanded_segs: list[str] = []
    for seg in segments:
        comma_parts = [p.strip() for p in seg.split(",") if p.strip()]
        i = 0
        while i < len(comma_parts):
            cur = comma_parts[i]
            nxt = comma_parts[i + 1] if i + 1 < len(comma_parts) else ""
            c_cur = to_code(cur) or country_of_location(cur)
            c_nxt = to_code(nxt) or country_of_location(nxt)
            # Combine "City, Country" OR "Country, City" cleanly without dropping the city
            _country_word_set = {n[0].lower() for n in _COUNTRIES.values()} | {"usa", "us", "uk", "united states", "united kingdom"}
            if nxt and c_nxt and cur.lower() not in _country_word_set and (not c_cur or c_cur == c_nxt):
                expanded_segs.append(f"{cur}, {country_name(c_nxt)}")
                i += 2
            elif nxt and c_cur and cur.lower() in _country_word_set and nxt.lower() not in _country_word_set and (not c_nxt or c_nxt == c_cur) and len(nxt.split()) <= 3:
                expanded_segs.append(f"{nxt}, {country_name(c_cur)}")
                i += 2
            else:
                expanded_segs.append(cur)
                i += 1

    # Check regional group names and country/city phrases in each segment
    known_group_labels = {
        "europe": "Europe",
        "eu": "EU",
        "south asia": "South Asia",
        "north america": "North America",
        "mena": "MENA",
        "gcc": "GCC",
        "africa": "Africa",
    }

    for seg in expanded_segs:
        s_low = seg.lower().strip()
        if not s_low or s_low in ("any", "skip", "none"):
            continue
        if re.search(r"\b(?:international|worldwide|global)\s+remote\b|\bremote\s+(?:worldwide|international|global)\b", s_low):
            add_place("Worldwide Remote")
            worldwide_remote = True
            continue
        if re.fullmatch(r"remote(?:\s+only)?|only\s+remote", s_low):
            add_place("Remote")
            remote_only = True
            continue
        if re.fullmatch(r"worldwide|anywhere|international|global|abroad", s_low):
            add_place("Worldwide")
            worldwide = True
            continue

        # Strip optional leading "remote in " inside segment like "remote in europe"
        if s_low.startswith("remote "):
            rem_rest = re.sub(r"^remote(?:\s+in|\s+within)?\s+", "", s_low).strip()
            if rem_rest:
                add_place("Remote")
                s_low = rem_rest
                seg = re.sub(r"^remote(?:\s+in|\s+within)?\s+", "", seg, flags=re.I).strip()

        matched_group = False
        for g_low, g_label in known_group_labels.items():
            if re.search(rf"\b{re.escape(g_low)}\b", s_low):
                add_place(g_label)
                matched_group = True
        if matched_group:
            continue

        # Guard against "us" pronoun unless uppercase US or explicit USA/United States
        has_explicit_usa = bool(re.search(r"\b(?:usa|u\.s\.a\.?|united states(?:\s+of\s+america)?)\b", s_low)) or bool(re.search(r"\bUS\b", seg))
        if has_explicit_usa:
            # Check if city prefix like "Austin, USA"
            city_m = re.match(r"^([A-Za-z\s.-]+?)[,\s]+(?:usa|u\.s\.a?\.|united states|US)\b", seg, flags=re.I)
            if city_m and city_m.group(1).strip() and city_m.group(1).strip().lower() not in ("in", "the", "from", "and"):
                add_place(f"{city_m.group(1).strip().title()}, United States")
            else:
                add_place("United States")
            continue

        # Ignore standalone two-letter lowercase "us", "in", "it", "is", "no", "or" as English words
        if s_low in ("us", "in", "it", "no", "or", "at", "be", "to", "my", "me", "hi", "ok", "yes"):
            continue

        code = country_of_location(seg) or to_code(seg)
        if code:
            c_name = country_name(code)
            # Preserve explicit city when user wrote e.g. "Paris, France" or "Sfax"
            if "," in seg:
                city_part = seg.split(",")[0].strip()
                if city_part and city_part.lower() != c_name.lower():
                    add_place(f"{city_part.title()}, {c_name}")
                else:
                    add_place(c_name)
            else:
                # Preserve country aliases as country names rather than treating synonyms like "Holland" as cities
                _country_synonyms = {
                    "uk", "usa", "us", "u.s.", "u.s.a.", "united states", "united kingdom",
                    "great britain", "england", "holland", "america", "czech republic",
                    "uae", "ksa", "tunisie", "deutschland", "maroc", "algerie", "brasil",
                }
                if s_low != c_name.lower() and s_low not in _country_synonyms:
                    add_place(f"{seg.strip().title()}, {c_name}")
                else:
                    add_place(c_name)

    return {
        "places": places,
        "remote_only": remote_only,
        "worldwide_remote": worldwide_remote,
        "worldwide": worldwide,
    }


def expand_place_targets(places: Iterable[str]) -> dict[str, object]:
    """Expand confirmed place list into codes, cities, and remote flags for SQL filtering."""
    codes: set[str] = set()
    cities: set[str] = set()
    raw: list[str] = []
    remote_only = False
    worldwide_remote = False
    worldwide = False

    for p in places or []:
        s = str(p or "").strip()
        if not s:
            continue
        raw.append(s)
        low = s.lower()
        if low in ("worldwide remote", "international remote", "global remote", "remote worldwide"):
            worldwide_remote = True
            continue
        if low in ("worldwide", "anywhere", "international", "global"):
            worldwide = True
            continue
        if low in ("remote", "remote only"):
            remote_only = True
            continue
        up = s.upper().replace("-", "_")
        up_sp = s.upper().replace("_", " ")
        if up in GROUPS:
            codes |= GROUPS[up]
            continue
        if up_sp in GROUPS:
            codes |= GROUPS[up_sp]
            continue
        if "," in s:
            city_part, rest = s.split(",", 1)
            if city_part.strip():
                cities.add(city_part.strip().lower())
            code = country_of_location(rest) or to_code(rest) or country_of_location(s)
            if code:
                codes.add(code)
            continue
        code = to_code(s) or country_of_location(s)
        if code:
            codes.add(code)
            c_name = country_name(code).lower()
            _country_synonyms = {
                "uk", "usa", "us", "u.s.", "u.s.a.", "united states", "united kingdom",
                "great britain", "england", "holland", "america", "czech republic",
                "uae", "ksa", "tunisie", "deutschland", "maroc", "algerie", "brasil",
            }
            if low != c_name and low not in _country_synonyms:
                cities.add(low)

    return {
        "country_codes": codes,
        "cities": cities,
        "remote_only": remote_only,
        "worldwide_remote": worldwide_remote,
        "worldwide": worldwide,
        "raw": raw,
    }


def job_matches_confirmed_places(job: dict, places: Iterable[str], work_mode_filter: str = "") -> bool:
    """Return True iff job matches at least one user-confirmed place or compatible remote mode."""
    exp = expand_place_targets(places)
    raw = exp["raw"]
    if not raw or exp["worldwide"]:
        return True

    j_loc_text = f"{job.get('location', '')} {job.get('city', '')} {job.get('country', '')}".strip()
    j_loc_low = j_loc_text.lower()
    j_wm = (job.get("work_mode") or "").lower()
    j_country = country_of_location(j_loc_text) or to_code(str(job.get("country") or ""))
    is_remote_job = ("remote" in j_wm) or ("remote" in j_loc_low) or (str(job.get("country") or "").lower() == "worldwide")

    if exp["worldwide_remote"]:
        if is_remote_job:
            return True

    codes: set[str] = exp["country_codes"]  # type: ignore[assignment]
    cities: set[str] = exp["cities"]  # type: ignore[assignment]

    if exp["remote_only"]:
        if not codes and not cities:
            return is_remote_job
        if not is_remote_job:
            return False

    if codes or cities:
        city_hit = any(c in j_loc_low for c in cities) if cities else True
        code_hit = bool(j_country and j_country in codes)
        raw_hit = any(r.lower() in j_loc_low for r in raw if r.lower() not in ("remote", "remote only", "worldwide remote"))
        if cities:
            if city_hit and (not codes or code_hit or j_country is None):
                return True
        elif code_hit or raw_hit:
            return True

        # Remote jobs remain eligible unless user requested onsite-only or the job restricts to another region ("US only")
        if is_remote_job and "onsite" not in (work_mode_filter or "").lower():
            restricted = bool(re.search(r"\b(?:us|u\.s\.|usa|uk|eu|europe|canada|india|germany|france)\s+only\b", j_loc_low))
            if not restricted or not codes or (j_country and j_country in codes):
                return True

    return False


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
