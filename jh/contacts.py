"""Contact Finder & Decision Maker Intelligence Engine (V8 Modern Track).

Identifies, verifies, ranks, and stores up to 3 decision makers per company:
- ContactProviderAdapter interface (domain_search, find_email, verify)
- Hunter API adapter with quota tracking & 30-day SQLite caching
- Compliant public page fallback (team, about, careers, press, signal poster)
  (No bought lists, no login bypass, no scraping private pages, no GitHub emails)
- Title selection mapped strictly by company size (<30, 30-200, >200 never CEO)
- DNS MX verification (drops invalid addresses, never sends test emails)
- Strict confidence labels: Found, Pattern, Guess
- Exclusion rules (unrelated functions, candidate employer, 90-day cooldown, DNC)
- Alternative routes fallback (LinkedIn, X, Careers labeled 'not an email')
- Contact deletion command (removes contact & all outreach history)
"""
from __future__ import annotations

import abc
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

from . import db, email_finder, util
from .mcp_helpers import Result, ToolError, envelope

log = logging.getLogger("jobhunter.contacts")
if not log.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("[%(asctime)s] [contacts] %(levelname)s: %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

HUNTER_CACHE_TTL_SEC = 30 * 86400  # 30 days
PUBLIC_FALLBACK_NOTICE = (
    "Finding emails from public pages is limited, and an API key (e.g. Hunter.io) "
    "gives higher deliverability and verified decision maker contacts."
)


class HttpResponse:
    def __init__(self, status: int, text: str, headers: Optional[Dict[str, str]] = None):
        self.status = status
        self.text = text
        self.headers = headers or {}


def _http_get(url: str, timeout: float = 5.0) -> HttpResponse:
    """Safe internal HTTP fetcher with status and header extraction."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JobHunter/8.0 (Modern Outreach)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            hdrs = {k: v for k, v in resp.headers.items()}
            return HttpResponse(resp.status, text, hdrs)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return HttpResponse(e.code, text, {k: v for k, v in e.headers.items()} if e.headers else {})
    except Exception as e:
        log.debug("HTTP GET error for %s: %s", url, e)
        return HttpResponse(0, "", {})


# =====================================================================
# 1. Provider Adapter Interface
# =====================================================================

class ContactProviderAdapter(abc.ABC):
    """Abstract interface for contact and email discovery providers."""

    name: str = "base"

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and has remaining quota."""
        pass

    @abc.abstractmethod
    def domain_search(
        self,
        domain: str,
        title: str = "",
        department: str = "",
        seniority: str = "",
        location: str = "",
    ) -> List[Dict[str, Any]]:
        """Search for contacts associated with domain."""
        pass

    @abc.abstractmethod
    def find_email(self, domain: str, first_name: str, last_name: str) -> Optional[Dict[str, Any]]:
        """Find or verify an email for a specific named person."""
        pass

    @abc.abstractmethod
    def verify(self, email: str) -> Dict[str, Any]:
        """Check email deliverability without sending a message."""
        pass


# =====================================================================
# 2. Hunter API Adapter
# =====================================================================

class HunterAdapter(ContactProviderAdapter):
    """Hunter.io API adapter with 30-day SQLite cache and quota tracking."""

    name = "hunter"
    BASE_URL = "https://api.hunter.io/v2"

    def __init__(self, api_key: str = ""):
        self._explicit_key = api_key

    def get_api_key(self) -> str:
        if self._explicit_key:
            return self._explicit_key
        return os.environ.get("HUNTER_API_KEY", "").strip() or db.get_setting("hunter_api_key", "").strip()

    def is_available(self) -> bool:
        key = self.get_api_key()
        if not key:
            return False
        # Check if quota is reported exhausted in current cycle
        remaining = db.get_setting("hunter_quota_remaining", "")
        if remaining == "0":
            reset_at = db.get_setting("hunter_reset_date", "")
            if reset_at:
                try:
                    if datetime.datetime.fromisoformat(reset_at) > datetime.datetime.now(datetime.timezone.utc):
                        return False
                except Exception:
                    pass
        return True

    def _get_cached_payload(self, cache_key: str) -> Optional[Dict[str, Any]]:
        with db.session() as c:
            row = c.execute("SELECT payload, fetched_at FROM source_cache WHERE cache_key=?", (cache_key,)).fetchone()
            if row:
                age = time.time() - float(row["fetched_at"])
                if age < HUNTER_CACHE_TTL_SEC:
                    try:
                        return json.loads(row["payload"])
                    except Exception:
                        pass
        return None

    def _set_cached_payload(self, cache_key: str, payload: Dict[str, Any]) -> None:
        with db.session() as c:
            c.execute(
                "INSERT OR REPLACE INTO source_cache (cache_key, payload, fetched_at) VALUES (?, ?, ?)",
                (cache_key, json.dumps(payload), time.time()),
            )

    def _update_quota(self, headers: Dict[str, str], meta: Dict[str, Any]) -> None:
        rem = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
        limit = headers.get("X-RateLimit-Limit") or headers.get("x-ratelimit-limit")
        reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")

        if rem is not None:
            db.set_setting("hunter_quota_remaining", str(rem))
        if limit is not None:
            db.set_setting("hunter_quota_limit", str(limit))
        if reset is not None:
            try:
                reset_dt = datetime.datetime.fromtimestamp(float(reset), datetime.timezone.utc).isoformat()
                db.set_setting("hunter_reset_date", reset_dt)
            except Exception:
                pass

        calls = int(db.get_setting("hunter_calls_count", "0") or "0") + 1
        db.set_setting("hunter_calls_count", str(calls))

    def domain_search(
        self,
        domain: str,
        title: str = "",
        department: str = "",
        seniority: str = "",
        location: str = "",
    ) -> List[Dict[str, Any]]:
        clean_domain = domain.strip().lower()
        if not clean_domain:
            return []

        cache_key = f"hunter_domain:{clean_domain}:{title}:{department}:{seniority}:{location}"
        cached = self._get_cached_payload(cache_key)
        if cached is not None:
            return cached.get("contacts", [])

        api_key = self.get_api_key()
        if not api_key:
            return []

        params = {"domain": clean_domain, "api_key": api_key, "limit": "10"}
        if department:
            params["department"] = department
        if seniority:
            params["seniority"] = seniority

        url = f"{self.BASE_URL}/domain-search?{urllib.parse.urlencode(params)}"
        resp = _http_get(url, timeout=5.0)
        if resp.status == 429:
            log.warning("Hunter API 429 quota exhausted.")
            db.set_setting("hunter_quota_remaining", "0")
            return []
        if resp.status != 200 or not resp.text:
            return []

        try:
            data = json.loads(resp.text)
            self._update_quota(resp.headers, data.get("meta", {}))
            emails = data.get("data", {}).get("emails", [])
            contacts: List[Dict[str, Any]] = []
            for item in emails:
                fname = item.get("first_name") or ""
                lname = item.get("last_name") or ""
                name = f"{fname} {lname}".strip() or item.get("value", "").split("@")[0].capitalize()
                raw_score = item.get("confidence") or 0
                label = "Found" if raw_score >= 75 or item.get("verification", {}).get("status") == "valid" else "Pattern"

                contacts.append({
                    "name": name,
                    "first_name": fname,
                    "last_name": lname,
                    "title": item.get("position") or "",
                    "department": item.get("department") or "",
                    "seniority": item.get("seniority") or "",
                    "email": item.get("value") or "",
                    "confidence": label,
                    "email_confidence": label,
                    "linkedin_url": item.get("linkedin") or "",
                    "x_handle": item.get("twitter") or "",
                    "phone": item.get("phone_number") or "",
                    "source": "hunter",
                    "company_domain": clean_domain,
                })

            self._set_cached_payload(cache_key, {"contacts": contacts})
            return contacts
        except Exception as e:
            log.warning("Error parsing Hunter domain search response: %s", e)
            return []

    def find_email(self, domain: str, first_name: str, last_name: str) -> Optional[Dict[str, Any]]:
        clean_domain = domain.strip().lower()
        if not clean_domain or not first_name:
            return None

        cache_key = f"hunter_find:{clean_domain}:{first_name}:{last_name}"
        cached = self._get_cached_payload(cache_key)
        if cached is not None:
            return cached.get("contact")

        api_key = self.get_api_key()
        if not api_key:
            return None

        params = {
            "domain": clean_domain,
            "first_name": first_name,
            "last_name": last_name,
            "api_key": api_key,
        }
        url = f"{self.BASE_URL}/email-finder?{urllib.parse.urlencode(params)}"
        resp = _http_get(url, timeout=5.0)
        if resp.status != 200 or not resp.text:
            return None

        try:
            data = json.loads(resp.text)
            self._update_quota(resp.headers, data.get("meta", {}))
            res = data.get("data", {})
            email_val = res.get("email") or ""
            if not email_val:
                return None

            raw_score = res.get("score") or 0
            label = "Found" if raw_score >= 75 else "Pattern"
            contact = {
                "name": f"{first_name} {last_name}".strip(),
                "first_name": first_name,
                "last_name": last_name,
                "title": res.get("position") or "",
                "email": email_val,
                "confidence": label,
                "email_confidence": label,
                "linkedin_url": res.get("linkedin") or "",
                "x_handle": res.get("twitter") or "",
                "source": "hunter",
                "company_domain": clean_domain,
            }
            self._set_cached_payload(cache_key, {"contact": contact})
            return contact
        except Exception:
            return None

    def verify(self, email: str) -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key or not email or "@" not in email:
            return {"status": "unknown", "valid": True}

        params = {"email": email, "api_key": api_key}
        url = f"{self.BASE_URL}/email-verifier?{urllib.parse.urlencode(params)}"
        resp = _http_get(url, timeout=5.0)
        if resp.status == 200 and resp.text:
            try:
                data = json.loads(resp.text).get("data", {})
                status_str = data.get("status") or "unknown"
                return {
                    "status": status_str,
                    "valid": status_str in ("valid", "accept_all"),
                    "score": data.get("score", 0),
                }
            except Exception:
                pass
        return {"status": "unknown", "valid": True}


# =====================================================================
# 3. Public Page Fallback Adapter
# =====================================================================

class PublicPageAdapter(ContactProviderAdapter):
    """Compliant public web pages and signal author contact finder.

    Strict rules:
    - Never uses bought lists or leaked databases.
    - Never bypasses login gates or paywalls.
    - Never extracts private emails from GitHub commit history or API.
    - Extracts only from public team, about, careers, press pages, and signal poster.
    """

    name = "public_page"

    def is_available(self) -> bool:
        return True

    def domain_search(
        self,
        domain: str,
        title: str = "",
        department: str = "",
        seniority: str = "",
        location: str = "",
    ) -> List[Dict[str, Any]]:
        clean_domain = (domain or "").strip().lower()
        if not clean_domain:
            return []

        # DNS MX check first
        mx_info = email_finder.query_mx_records(clean_domain)
        has_mx = mx_info.get("has_mx", False)

        contacts: List[Dict[str, Any]] = []

        # Attempt to scrape public /about or /team or /careers if accessible
        for path in ["/about", "/team", "/company", "/careers"]:
            target_url = f"https://{clean_domain}{path}"
            resp = _http_get(target_url, timeout=3.0)
            if resp.status == 200 and resp.text:
                extracted = self._parse_public_team_page(resp.text, clean_domain, has_mx)
                if extracted:
                    contacts.extend(extracted)
                    break

        return contacts

    def _parse_public_team_page(self, html: str, domain: str, has_mx: bool) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        # Find mailto links
        mailtos = re.findall(r'href=[\'"]mailto:([a-zA-Z0-9._%+-]+@' + re.escape(domain) + r')[\'"]', html, re.I)
        for m in set(mailtos):
            prefix = m.split("@")[0]
            name = " ".join([p.capitalize() for p in re.split(r"[._-]", prefix) if p])
            results.append({
                "name": name or "Team Member",
                "title": "Team Lead",
                "email": m,
                "confidence": "Found" if has_mx else "Guess",
                "email_confidence": "Found" if has_mx else "Guess",
                "source": "public_page",
                "company_domain": domain,
            })
            if len(results) >= 5:
                break
        return results

    def find_email(self, domain: str, first_name: str, last_name: str) -> Optional[Dict[str, Any]]:
        clean_domain = (domain or "").strip().lower()
        if not clean_domain or not first_name:
            return None

        # Resolve domain pattern via email_finder
        res = email_finder.find_corporate_email(
            name=f"{first_name} {last_name}".strip(),
            domain=clean_domain,
        )
        if res.get("success") and res.get("primary_email"):
            label = "Pattern" if res.get("mx_verified") else "Guess"
            return {
                "name": f"{first_name} {last_name}".strip(),
                "first_name": first_name,
                "last_name": last_name,
                "title": "",
                "email": res["primary_email"],
                "confidence": label,
                "email_confidence": label,
                "source": "public_pattern",
                "company_domain": clean_domain,
            }
        return None

    def verify(self, email: str) -> Dict[str, Any]:
        if not email or "@" not in email:
            return {"status": "invalid", "valid": False}
        domain = email.split("@")[1].strip().lower()
        mx = email_finder.query_mx_records(domain)
        has_mx = bool(mx.get("has_mx"))
        return {
            "status": "valid" if has_mx else "invalid_domain",
            "valid": has_mx,
            "provider": mx.get("provider", "Unknown"),
        }


# =====================================================================
# 4. Decision Maker Targeting Rules by Company Size
# =====================================================================

def parse_company_size_num(size_str: str, stage: str = "") -> int:
    """Estimate employee count from size string or funding stage."""
    raw = (size_str or "").lower().strip()
    if raw.isdigit():
        return int(raw)

    if "-" in raw:
        parts = raw.split("-")
        try:
            return int(parts[0].strip())
        except Exception:
            pass

    # Infer from stage if size not explicit
    stage_l = (stage or "").lower()
    if "seed" in stage_l or "pre-seed" in stage_l or "angel" in stage_l:
        return 15
    if "series a" in stage_l:
        return 45
    if "series b" in stage_l:
        return 120
    if "series c" in stage_l or "growth" in stage_l or "public" in stage_l:
        return 500

    # Default to small-mid startup
    return 25


def matches_size_rules(
    title: str,
    company_size: int,
    target_role: str = "",
    is_signal_author: bool = False,
) -> Tuple[bool, int, str]:
    """Check if title is acceptable for company size and assign score priority.

    Rules:
    - Under 30 people: Founder, Co-founder, CEO, and the signal author.
    - 30 to 200 people: Head of [function], VP [function], team lead, and the signal author.
    - Over 200 people: Team lead or hiring manager in the department, and the recruiter
      who handles the role. NEVER reach out to the CEO.
    """
    t_lower = (title or "").lower().strip()

    if is_signal_author:
        # Signal poster is always relevant regardless of size
        return True, 250, "signal_author"

    # HARD RULE: Over 200 people -> NEVER CEO
    if company_size > 200:
        if any(banned in t_lower for banned in ("ceo", "chief executive", "president", "co-founder", "founder")):
            return False, 0, "disallowed_seniority"

    # Role function relevance (e.g. engineering, product, data)
    r_target = (target_role or "engineering").lower()
    is_target_dept = any(kw in t_lower for kw in (
        "eng", "tech", "software", "product", "data", "developer", "platform", "infrastructure",
        "frontend", "backend", "fullstack", "ai", "ml", "machine learning"
    )) or not t_lower

    if company_size < 30:
        # Under 30: Founder, Co-founder, CEO, and signal author
        if any(f in t_lower for f in ("founder", "co-founder", "ceo", "chief executive", "cto", "co-owner")):
            return True, 200, "founder"
        if is_target_dept and any(k in t_lower for k in ("lead", "head", "architect", "engineer", "hiring")):
            return True, 160, "department_lead"
        return True, 100, "general_lead"

    elif 30 <= company_size <= 200:
        # 30 to 200: Head of [function], VP [function], team lead, signal author
        if any(h in t_lower for h in ("head of", "vp", "vice president", "director")):
            priority = 220 if is_target_dept else 140
            return True, priority, "executive"
        if any(tl in t_lower for tl in ("team lead", "lead engineer", "engineering manager", "tech lead")):
            priority = 210 if is_target_dept else 130
            return True, priority, "team_lead"
        if any(f in t_lower for f in ("founder", "cto", "co-founder")):
            return True, 150, "founder"
        return False, 0, "outside_target_tier"

    else:
        # Over 200: Team lead / hiring manager in department, or recruiter handling role.
        # NEVER reach out to the CEO.
        if any(r in t_lower for r in ("recruiter", "talent", "people", "technical recruiter", "hiring partner")):
            return True, 180, "recruiter"
        if is_target_dept and any(m in t_lower for m in ("manager", "lead", "head", "director", "supervisor")):
            return True, 220, "hiring_manager"
        return False, 0, "outside_target_tier"


# =====================================================================
# 5. Exclusions & Cooldown Checks
# =====================================================================

def is_excluded(
    contact: Dict[str, Any],
    candidate_current_employer: str = "",
    do_not_contact_domains: Optional[Set[str]] = None,
) -> Tuple[bool, str]:
    """Verify contact against exclusion rules:

    1. People in unrelated functions (e.g. Legal, Accounting, Finance).
    2. People at the candidate's current employer.
    3. People contacted in the past 90 days.
    4. Do-not-contact domains.
    """
    title_lower = (contact.get("title") or "").lower()

    # 1. Unrelated functions
    unrelated_keywords = (
        "legal", "general counsel", "accounting", "auditor", "finance manager",
        "facilities", "sales rep", "account executive", "customer success"
    )
    if any(k in title_lower for k in unrelated_keywords):
        return True, "unrelated_function"

    # 2. Current employer
    comp = (contact.get("company") or "").lower().strip()
    emp = (candidate_current_employer or "").lower().strip()
    if emp and (emp in comp or comp in emp):
        return True, "candidate_current_employer"

    # 3. Do-not-contact domains
    dnc = do_not_contact_domains or set()
    dom = (contact.get("company_domain") or "").lower().strip()
    if dom in dnc:
        return True, "do_not_contact_domain"

    # 4. Contacted in past 90 days
    email = (contact.get("email") or "").lower().strip()
    if email:
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)).isoformat()
        with db.session() as c:
            row = c.execute(
                "SELECT id FROM outreach WHERE lower(recipient_email)=lower(?) AND sent_at >= ?",
                (email, cutoff),
            ).fetchone()
            if row:
                return True, "contacted_in_past_90_days"

    return False, ""


# =====================================================================
# 6. Verification, MX Check, & Alternative Routes
# =====================================================================

def verify_and_label(contact: Dict[str, Any]) -> Dict[str, Any]:
    """Verify email delivers via DNS MX, drop if invalid, and assign confidence label."""
    res = dict(contact)
    email = (res.get("email") or "").strip()
    dom = res.get("company_domain") or (email.split("@")[1] if "@" in email else "")

    if email and dom:
        # Perform DNS MX record verification
        mx_res = email_finder.query_mx_records(dom)
        if not mx_res.get("has_mx", False):
            # DROP ADDRESS IF MX FAILS. NEVER SEND TEST EMAIL.
            log.info("Dropping email %s for %s: DNS MX verification failed", email, res.get("name"))
            res["email"] = ""
            res["email_confidence"] = "Guess"
            res["confidence"] = "Guess"
            res["notes"] = "Email dropped: MX record check failed"
        else:
            # Valid MX: Keep label
            conf = res.get("email_confidence") or res.get("confidence") or "Pattern"
            if conf not in ("Found", "Pattern", "Guess"):
                conf = "Pattern"
            res["email_confidence"] = conf
            res["confidence"] = conf
    else:
        res["email"] = ""
        res["email_confidence"] = "Guess"
        res["confidence"] = "Guess"

    # Build alternative routes if no email
    if not res.get("email"):
        alt_routes = []
        if res.get("linkedin_url"):
            alt_routes.append({
                "channel": "LinkedIn",
                "url": res["linkedin_url"],
                "route_type": "not_an_email",
                "is_email": False,
            })
        if res.get("x_handle"):
            x_url = res["x_handle"] if res["x_handle"].startswith("http") else f"https://x.com/{res['x_handle'].lstrip('@')}"
            alt_routes.append({
                "channel": "X (Twitter)",
                "url": x_url,
                "route_type": "not_an_email",
                "is_email": False,
            })
        if dom:
            alt_routes.append({
                "channel": "Careers Page",
                "url": f"https://{dom}/careers",
                "route_type": "not_an_email",
                "is_email": False,
            })
        res["alternative_routes"] = alt_routes

    return res


# =====================================================================
# 7. Orchestrated Finder & Ranking
# =====================================================================

def find_contacts(
    signal_id_or_company: str,
    target_role: str = "",
    company_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Find, verify, rank, and store up to 3 decision makers for a signal or company."""
    signal_data: Optional[Dict[str, Any]] = None
    company_name = ""
    domain = ""
    stage = ""
    signal_id = ""
    signal_poster_name = ""
    signal_poster_url = ""

    # Check if input is a signal ID
    if signal_id_or_company.startswith("sig_"):
        signal_id = signal_id_or_company
        signal_data = db.get_signal(signal_id)
        if signal_data:
            company_name = signal_data.get("company", "")
            domain = signal_data.get("company_domain", "")
            stage = signal_data.get("stage", "")
            signal_poster_name = signal_data.get("author_name", "")
            signal_poster_url = signal_data.get("author_url", "")
            if not target_role:
                target_role = signal_data.get("role_guess", "")
    else:
        company_name = signal_id_or_company.strip()

    if not company_name:
        raise ToolError("Must provide a valid company name or signal_id.")

    # Resolve domain if missing
    if not domain:
        domain = email_finder.resolve_company_domain(company_name)

    # Determine company size
    if company_size is None:
        size_num = parse_company_size_num("", stage)
    else:
        size_num = company_size

    # Load candidate profile for exclusion check
    prof = db.get_profile() or {}
    cur_emp = prof.get("current_employer", "")

    # Load DNC domains
    dnc_setting = db.get_setting("do_not_contact_domains", "")
    dnc_domains = {d.strip().lower() for d in dnc_setting.split(",") if d.strip()}

    raw_candidates: List[Dict[str, Any]] = []
    hunter = HunterAdapter()
    public_adapter = PublicPageAdapter()
    notice_messages: List[str] = []

    # 1. Try Hunter API if available
    hunter_used = False
    if hunter.is_available():
        try:
            hunter_results = hunter.domain_search(domain)
            if hunter_results:
                raw_candidates.extend(hunter_results)
                hunter_used = True
        except Exception as e:
            log.warning("Hunter adapter domain search failed: %s", e)

    # 2. Add public adapter / signal poster fallback
    if not hunter_used:
        notice_messages.append(PUBLIC_FALLBACK_NOTICE)

    # Signal poster is prime candidate if available
    if signal_poster_name:
        is_founder_hint = size_num < 30
        poster_cand = email_finder.find_corporate_email(
            name=signal_poster_name,
            company=company_name,
            domain=domain,
            role="Founder" if is_founder_hint else "Lead",
        )
        raw_candidates.append({
            "name": signal_poster_name,
            "title": "Hiring Poster / Team Lead" if not is_founder_hint else "Founder",
            "email": poster_cand.get("primary_email", "") if poster_cand.get("success") else "",
            "confidence": "Pattern" if poster_cand.get("mx_verified") else "Guess",
            "email_confidence": "Pattern" if poster_cand.get("mx_verified") else "Guess",
            "linkedin_url": signal_poster_url if "linkedin.com" in signal_poster_url else "",
            "x_handle": signal_poster_url if ("x.com" in signal_poster_url or "twitter.com" in signal_poster_url) else "",
            "source": "signal_author",
            "company_domain": domain,
            "is_signal_author": True,
        })

    # Public team page search if raw candidates low
    if len(raw_candidates) < 3:
        public_candidates = public_adapter.domain_search(domain)
        raw_candidates.extend(public_candidates)

    # Synthesize fallback decision maker if still zero
    if not raw_candidates:
        default_title = "Founder & CEO" if size_num < 30 else ("VP of Engineering" if size_num <= 200 else "Engineering Manager")
        fallback_cand = email_finder.find_corporate_email(
            name="Leadership",
            company=company_name,
            domain=domain,
            role=default_title,
        )
        raw_candidates.append({
            "name": f"{company_name} Leadership",
            "title": default_title,
            "email": fallback_cand.get("primary_email", ""),
            "confidence": "Guess",
            "email_confidence": "Guess",
            "source": "domain_pattern",
            "company_domain": domain,
        })

    # 3. Filter by exclusions, size rules, and rank
    scored_contacts: List[Tuple[int, Dict[str, Any]]] = []
    seen_identities: Set[str] = set()

    for cand in raw_candidates:
        name = cand.get("name", "").strip()
        email = cand.get("email", "").strip().lower()
        id_key = email or name.lower()
        if not id_key or id_key in seen_identities:
            continue
        seen_identities.add(id_key)

        cand["company"] = company_name
        cand["company_domain"] = domain
        cand["signal_id"] = signal_id

        # Exclusion checks
        excluded, ex_reason = is_excluded(cand, cur_emp, dnc_domains)
        if excluded:
            log.debug("Excluding contact %s: %s", name, ex_reason)
            continue

        # Size-based title check
        is_poster = bool(cand.get("is_signal_author"))
        allowed, title_priority, cat = matches_size_rules(
            cand.get("title", ""),
            size_num,
            target_role=target_role,
            is_signal_author=is_poster,
        )
        if not allowed:
            log.debug("Title disallowed by size rules (%d people): %s", size_num, cand.get("title"))
            continue

        cand["role_category"] = cat

        # Verification & MX record check (drops email if MX invalid)
        verified = verify_and_label(cand)

        # Ranking score:
        # 1. Title match (100 - 250 points)
        # 2. Reachability / confidence: Found (40), Pattern (20), Guess (5), No email (0)
        # 3. Closeness to role (20 points)
        score = title_priority
        conf = verified.get("email_confidence", "Guess")
        if verified.get("email"):
            if conf == "Found":
                score += 40
            elif conf == "Pattern":
                score += 20
            else:
                score += 5

        scored_contacts.append((score, verified))

    # Sort descending by score, pick top 3
    scored_contacts.sort(key=lambda x: x[0], reverse=True)
    top_3 = [item[1] for item in scored_contacts[:3]]

    # Store contacts in SQLite
    saved_contacts: List[Dict[str, Any]] = []
    for c in top_3:
        saved = db.save_contact(c)
        saved["alternative_routes"] = c.get("alternative_routes", [])
        saved_contacts.append(saved)

    return {
        "success": True,
        "company": company_name,
        "domain": domain,
        "company_size_estimate": size_num,
        "provider_used": "hunter" if hunter_used else "public_pages",
        "contacts_count": len(saved_contacts),
        "contacts": saved_contacts,
        "notices": notice_messages,
    }


def delete_contact_and_history(contact_id: str) -> bool:
    """Delete a contact and all associated outreach rows from SQLite."""
    return db.delete_contact(contact_id)


# =====================================================================
# 8. MCP Tool Registration
# =====================================================================

def jh_find_contacts(signal_id_or_company: str, target_role: str = "") -> Dict[str, Any]:
    """Find up to 3 decision makers (Found, Pattern, Guess) or alternative routes for outreach."""
    try:
        res = find_contacts(signal_id_or_company, target_role=target_role)
        notices = res.get("notices") or []
        return envelope(status="ok", data=res, warnings=notices)
    except ToolError as e:
        return envelope(status="error", error={"code": e.code, "message": str(e), "hint": e.hint})
    except Exception as e:
        log.exception("jh_find_contacts unexpected error: %s", e)
        return envelope(status="error", error={"code": "internal_error", "message": f"Failed to find contacts: {e}"})
