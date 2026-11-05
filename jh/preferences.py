"""Personal search preferences: where, what kind of work, what to avoid, which sources to use.

Preferences live in ``<data dir>/preferences.json`` and apply across every resume. They are
validated on write, so the tools return a clear error instead of storing junk.

The preferences overlay the resume profile only when a search or a tool runs
(``overlay_profile``). The stored resume is never modified, and the background LinkedIn radar
keeps reading the profile exactly as it always did.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from typing import Any

from . import config, regions
from .util import now_iso

_lock = threading.Lock()
_cache: dict[str, Any] = {"mtime": None, "path": None, "data": None}

WORK_MODES = ("Any", "Remote", "Hybrid", "Onsite")
COMPANY_FOCUS = ("any", "avoid_big_names", "only_big_names")
SEARCH_DEPTH = ("quick", "standard", "deep")
JOB_TYPES = ("Full-time", "Part-time", "Contract", "Internship")
SENIORITY = ("intern", "junior", "mid", "senior", "lead", "principal", "manager", "director")

DEFAULTS: dict[str, Any] = {
    "home_country": "",              # where you live now, e.g. "Tunisia"
    "target_countries": [],          # where you want to work, e.g. ["Tunisia", "France", "Germany"]
    "cities": [],                    # preferred cities, e.g. ["Tunis", "Paris"]
    "work_mode": "",                 # "" keeps the resume value; Any / Remote / Hybrid / Onsite
    "include_worldwide_remote": True,
    "open_to_relocation": False,
    "needs_visa_sponsorship": False,
    "languages": [],                 # languages you work in, e.g. ["English", "French", "Arabic"]
    "target_titles": [],             # roles to search for; the first one is the main target
    "min_salary": 0,                 # yearly figure in salary_currency; 0 means no floor
    "salary_currency": "",
    "job_types": [],                 # Full-time, Part-time, Contract, Internship
    "seniority": [],                 # junior, mid, senior, ...
    "excluded_keywords": [],
    "excluded_companies": [],
    "dream_companies": [],
    "company_focus": "any",          # any | avoid_big_names | only_big_names
    "max_age_days": 30,              # hide postings older than this; 0 means no limit
    "search_depth": "standard",      # quick | standard | deep
    "enabled_sources": [],           # when not empty, ONLY these sources run
    "disabled_sources": [],          # sources to skip
    "custom_feeds": [],              # [{"name": ..., "url": ...}] RSS, Atom or JSON feeds
    "career_pages": [],              # [{"name": ..., "url": ...}] company career pages
    "job_sites": [],                 # [{"name": ..., "url": ...}] small boards or company sites read through their job data
}

LIST_FIELDS = {
    "target_countries", "cities", "languages", "target_titles", "job_types", "seniority",
    "excluded_keywords", "excluded_companies", "dream_companies", "enabled_sources", "disabled_sources",
}
_MAX_ITEMS = 40
_MAX_LEN = 80


class PreferenceError(ValueError):
    """Raised when an update contains an invalid value."""


def _path() -> str:
    return os.path.join(config.DATA_DIR, "preferences.json")


def _clean_list(name: str, value: Any) -> list[str]:
    if isinstance(value, str):
        value = [v for v in value.split(",")]
    if not isinstance(value, (list, tuple)):
        raise PreferenceError(f"'{name}' must be a list of strings")
    out: list[str] = []
    for v in value:
        s = str(v).strip()[:_MAX_LEN]
        if s and s.lower() not in {x.lower() for x in out}:
            out.append(s)
    return out[:_MAX_ITEMS]


def _clean_sources(value: Any) -> list[str]:
    from . import source_registry
    known = {s["name"].lower(): s["name"] for s in source_registry.catalog()}
    out = []
    for name in _clean_list("sources", value):
        canon = known.get(name.lower())
        if not canon:
            raise PreferenceError(f"Unknown source '{name}'. Call list_job_sources to see valid names.")
        if canon not in out:
            out.append(canon)
    return out


def _clean_endpoints(name: str, value: Any) -> list[dict]:
    from . import source_policy
    if not isinstance(value, (list, tuple)):
        raise PreferenceError(f"'{name}' must be a list of {{name, url}} objects")
    out: list[dict] = []
    for item in value[:_MAX_ITEMS]:
        if isinstance(item, str):
            item = {"url": item}
        if not isinstance(item, dict) or not str(item.get("url", "")).strip():
            raise PreferenceError(f"Each entry in '{name}' needs a url")
        url = str(item["url"]).strip()
        ok, reason = source_policy.check_url(url)
        if not ok:
            raise PreferenceError(f"Rejected {url}: {reason}")
        entry = {"name": str(item.get("name") or "").strip()[:_MAX_LEN], "url": url}
        if entry["url"] not in {e["url"] for e in out}:
            out.append(entry)
    return out


def validate(updates: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Validate and normalize a partial update. Returns ``(clean_updates, warnings)``."""
    clean: dict[str, Any] = {}
    warnings: list[str] = []
    for key, value in (updates or {}).items():
        if key not in DEFAULTS:
            raise PreferenceError(f"Unknown preference '{key}'. Valid keys: {', '.join(sorted(DEFAULTS))}")
        if key in ("enabled_sources", "disabled_sources"):
            clean[key] = _clean_sources(value)
        elif key in ("custom_feeds", "career_pages", "job_sites"):
            clean[key] = _clean_endpoints(key, value)
        elif key in ("target_countries", "home_country"):
            raw = _clean_list(key, value) if key == "target_countries" else [str(value or "").strip()]
            names = []
            for item in raw:
                if not item:
                    continue
                code = regions.to_code(item) or regions.country_of_location(item)
                if code:
                    if regions.country_name(code) not in names:
                        names.append(regions.country_name(code))
                elif item.upper() in regions.GROUPS:
                    names.append(item.upper())
                else:
                    warnings.append(f"Unrecognised country '{item}'. It was kept as typed; sources may not match it.")
                    names.append(item)
            clean[key] = names if key == "target_countries" else (names[0] if names else "")
        elif key in LIST_FIELDS:
            vals = _clean_list(key, value)
            if key == "job_types":
                vals = [v for v in (_title_case_type(x) for x in vals) if v]
            if key == "seniority":
                vals = [v.lower() for v in vals if v.lower() in SENIORITY]
            clean[key] = vals
        elif key == "work_mode":
            v = str(value or "").strip().title() if value else ""
            if v and v not in WORK_MODES:
                raise PreferenceError(f"work_mode must be one of {', '.join(WORK_MODES)} (or empty)")
            clean[key] = v
        elif key == "company_focus":
            if value not in COMPANY_FOCUS:
                raise PreferenceError(f"company_focus must be one of {', '.join(COMPANY_FOCUS)}")
            clean[key] = value
        elif key == "search_depth":
            if value not in SEARCH_DEPTH:
                raise PreferenceError(f"search_depth must be one of {', '.join(SEARCH_DEPTH)}")
            clean[key] = value
        elif key in ("include_worldwide_remote", "open_to_relocation", "needs_visa_sponsorship"):
            if not isinstance(value, bool):
                raise PreferenceError(f"'{key}' must be true or false")
            clean[key] = value
        elif key in ("min_salary", "max_age_days"):
            try:
                n = int(float(value))
            except (TypeError, ValueError):
                raise PreferenceError(f"'{key}' must be a number")
            if n < 0 or n > (10_000_000 if key == "min_salary" else 3650):
                raise PreferenceError(f"'{key}' is out of range")
            clean[key] = n
        elif key == "salary_currency":
            clean[key] = str(value or "").strip().upper()[:5]
        else:
            clean[key] = str(value or "").strip()[:_MAX_LEN]
    return clean, warnings


def _title_case_type(x: str) -> str:
    low = x.lower().replace("_", "-").replace(" ", "-")
    return {"full-time": "Full-time", "fulltime": "Full-time", "part-time": "Part-time", "contract": "Contract",
            "freelance": "Contract", "internship": "Internship", "intern": "Internship"}.get(low, "")


def load() -> dict[str, Any]:
    """Return the stored preferences merged over the defaults."""
    path = _path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    with _lock:
        if _cache["path"] == path and _cache["mtime"] == mtime and _cache["data"] is not None:
            return copy.deepcopy(_cache["data"])
        data = copy.deepcopy(DEFAULTS)
        if mtime is not None:
            try:
                with open(path, encoding="utf-8") as f:
                    stored = json.load(f)
                for k, v in stored.items():
                    if k in DEFAULTS:
                        data[k] = v
            except (OSError, ValueError):
                pass
        _cache.update(path=path, mtime=mtime, data=data)
        return copy.deepcopy(data)


def save(updates: dict[str, Any], merge_lists: bool = False) -> tuple[dict[str, Any], list[str]]:
    """Validate and store a partial update. With ``merge_lists`` list values are added to the stored lists."""
    clean, warnings = validate(updates)
    current = load()
    for key, value in clean.items():
        if merge_lists and key in LIST_FIELDS | {"custom_feeds", "career_pages", "job_sites"}:
            existing = current.get(key, [])
            if key in ("custom_feeds", "career_pages", "job_sites"):
                known = {e["url"] for e in existing}
                current[key] = existing + [e for e in value if e["url"] not in known]
            else:
                low = {str(x).lower() for x in existing}
                current[key] = existing + [v for v in value if str(v).lower() not in low]
        else:
            current[key] = value
    current["_updated_at"] = now_iso()
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _path())
    with _lock:
        _cache["data"] = None
    _mirror_legacy_settings(current)
    return {k: v for k, v in load().items()}, warnings


def _mirror_legacy_settings(prefs: dict[str, Any]) -> None:
    """Older code reads ``user_country`` and ``include_worldwide_remote`` from the settings table."""
    try:
        from . import db
        home = prefs.get("home_country") or (prefs.get("target_countries") or [""])[0]
        if home:
            db.set_setting("user_country", home)
        db.set_setting("include_worldwide_remote", "1" if prefs.get("include_worldwide_remote", True) else "0")
    except Exception:
        pass


def is_default(prefs: dict[str, Any]) -> bool:
    return all(prefs.get(k) == v for k, v in DEFAULTS.items())


def overlay_profile(profile: dict[str, Any], prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a copy of ``profile`` with the person's preferences applied on top."""
    prefs = prefs if prefs is not None else load()
    p = copy.deepcopy(profile or {})
    if prefs.get("work_mode"):
        p["work_mode"] = prefs["work_mode"]
    places = list(prefs.get("cities") or []) + [c for c in prefs.get("target_countries") or [] if c not in regions.GROUPS]
    if places:
        p["preferred_locations"] = places
    if prefs.get("min_salary"):
        p["min_salary"] = prefs["min_salary"]
    if prefs.get("excluded_keywords"):
        p["excluded_keywords"] = sorted({*(p.get("excluded_keywords") or []), *prefs["excluded_keywords"]})
    if prefs.get("dream_companies"):
        p["dream_companies"] = sorted({*(p.get("dream_companies") or []), *prefs["dream_companies"]})
    if prefs.get("job_types"):
        p["preferred_job_types"] = prefs["job_types"]
    titles = prefs.get("target_titles") or []
    if titles:
        p["target_title"] = titles[0]
        p["target_roles"] = titles + [r for r in (p.get("target_roles") or []) if r not in titles]
    if prefs.get("languages"):
        p["languages"] = prefs["languages"]
    p["_prefs_applied"] = True
    return p


def famous_mode(prefs: dict[str, Any] | None = None) -> str:
    """Map company_focus to the ``famous_mode`` the pipeline understands."""
    focus = (prefs or load()).get("company_focus", "any")
    return {"avoid_big_names": "hide", "only_big_names": "only"}.get(focus, "all")
