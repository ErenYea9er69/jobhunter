"""Source access policy — blocks unsafe network behavior and validates URLs.

Implements SSRF prevention, domain allowlisting, and access-method enforcement
before any HTTP request leaves the server. Every outbound fetch must pass
through ``check_url`` before the request is made.

Security controls:
- Scheme validation (https/http only)
- Private-network / loopback / link-local blocking
- Domain allowlist enforcement
- Redirect chain depth limit
- Response size cap reference
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import Any, Optional, Set, Tuple
from urllib.parse import urlparse

log = logging.getLogger("jobhunter.source_policy")


# ──────────────────────────────────────────── policy configuration

class PolicyViolation(Exception):
    """Raised when a URL or network request violates the source policy."""

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Policy violation for '{_redact_url(url)}': {reason}")


# Schemes that are always allowed
ALLOWED_SCHEMES = {"http", "https"}

# Maximum redirect chain depth
MAX_REDIRECTS = 5

# Maximum response size (6 MB, matching util.http_get default)
MAX_RESPONSE_BYTES = 6_000_000

# Known safe domains for job sources
# This is the allowlist of hostnames whose outbound requests are permitted.
# Model-generated URLs that resolve outside this list are blocked.
ALLOWED_DOMAINS: set[str] = {
    # Direct employer ATS
    "boards-api.greenhouse.io",
    "boards.greenhouse.io",
    "api.lever.co",
    "jobs.lever.co",
    "api.ashbyhq.com",
    "jobs.ashbyhq.com",
    "api.smartrecruiters.com",
    "jobs.smartrecruiters.com",
    "apply.workable.com",

    # Major job boards
    "www.linkedin.com",
    "linkedin.com",
    "www.indeed.com",
    "indeed.com",
    "api.indeed.com",
    "www.ziprecruiter.com",
    "api.ziprecruiter.com",

    # Free feeds / APIs
    "hacker-news.firebaseio.com",
    "www.workatastartup.com",
    "himalayas.app",
    "jobicy.com",
    "www.arbeitnow.com",
    "api.adzuna.com",

    # Regional boards
    "www.bayt.com",
    "www.naukri.com",
    "www.hellowork.com",

    # Remote boards (may have paywalls for apply, but listing is public)
    "weworkremotely.com",
    "www.weworkremotely.com",
    "remotive.com",
    "remotive.io",
    "remoteok.com",
    "remoteok.io",

    # Y Combinator
    "www.ycombinator.com",
    "news.ycombinator.com",
}

# Patterns for auto-approved employer career subdomains
_EMPLOYER_CAREER_PATTERNS = [
    re.compile(r"^careers?\.", re.IGNORECASE),
    re.compile(r"^jobs?\.", re.IGNORECASE),
    re.compile(r"\.greenhouse\.io$", re.IGNORECASE),
    re.compile(r"\.lever\.co$", re.IGNORECASE),
    re.compile(r"\.ashbyhq\.com$", re.IGNORECASE),
    re.compile(r"\.smartrecruiters\.com$", re.IGNORECASE),
    re.compile(r"\.workable\.com$", re.IGNORECASE),
]

# Private / reserved IP ranges that must be blocked (SSRF prevention)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("10.0.0.0/8"),         # private
    ipaddress.ip_network("172.16.0.0/12"),      # private
    ipaddress.ip_network("192.168.0.0/16"),     # private
    ipaddress.ip_network("169.254.0.0/16"),     # link-local
    ipaddress.ip_network("0.0.0.0/8"),          # "this network"
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


# ──────────────────────────────────────────── URL checking

def check_url(url: str, *, allow_user_provided: bool = False) -> Tuple[bool, Optional[str]]:
    """Validate a URL against the source policy.

    Returns:
        (is_allowed, reason_if_blocked)
    """
    if not url:
        return False, "Empty URL"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL"

    # 1. Scheme check
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return False, f"Blocked scheme '{scheme}'; only http/https allowed"

    # 2. Hostname extraction
    hostname = (parsed.hostname or "").lower().strip(".")
    if not hostname:
        return False, "Missing hostname"

    # 3. Block IP-literal URLs that resolve to private ranges
    blocked_reason = _check_ip_literal(hostname)
    if blocked_reason:
        return False, blocked_reason

    # 4. Domain allowlist check
    if _is_domain_allowed(hostname, allow_user_provided=allow_user_provided):
        return True, None

    return False, f"Domain '{hostname}' is not in the approved source list"


def check_url_strict(url: str) -> None:
    """Like check_url but raises PolicyViolation on failure."""
    allowed, reason = check_url(url)
    if not allowed:
        raise PolicyViolation(url, reason or "Blocked by source policy")


def resolve_and_check(url: str) -> Tuple[bool, Optional[str]]:
    """Resolve hostname to IP and verify it doesn't target private networks.

    This is the full SSRF check — call it before making the actual HTTP request
    when DNS resolution is needed.
    """
    allowed, reason = check_url(url)
    if not allowed:
        return False, reason

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    try:
        addrs = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, f"DNS resolution failed for '{hostname}'"

    for family, _, _, _, sockaddr in addrs:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                return False, f"Resolved IP {ip_str} is in a blocked network range"

    return True, None


# ──────────────────────────────────────────── redirect policy

def check_redirect(original_url: str, redirect_url: str, depth: int = 0) -> Tuple[bool, Optional[str]]:
    """Check whether a redirect target is acceptable.

    Args:
        original_url: The URL that initiated the redirect chain
        redirect_url: The target of this redirect
        depth: Current redirect chain depth

    Returns:
        (is_allowed, reason_if_blocked)
    """
    if depth >= MAX_REDIRECTS:
        return False, f"Redirect chain too deep (>{MAX_REDIRECTS})"

    return check_url(redirect_url, allow_user_provided=True)


# ──────────────────────────────────────────── domain management

def add_allowed_domain(domain: str) -> None:
    """Add a domain to the runtime allowlist (e.g. for user-configured company boards)."""
    clean = domain.lower().strip().strip(".")
    if clean:
        ALLOWED_DOMAINS.add(clean)
        log.info("Added allowed domain: %s", clean)


def remove_allowed_domain(domain: str) -> None:
    """Remove a domain from the runtime allowlist."""
    clean = domain.lower().strip().strip(".")
    ALLOWED_DOMAINS.discard(clean)


def list_allowed_domains() -> list[str]:
    """Return sorted list of currently allowed domains."""
    return sorted(ALLOWED_DOMAINS)


# ──────────────────────────────────────────── internal helpers

def _is_domain_allowed(hostname: str, *, allow_user_provided: bool = False) -> bool:
    """Check if hostname or its parent domain is in the allowlist."""
    # Direct match
    if hostname in ALLOWED_DOMAINS:
        return True

    # Subdomain match: e.g. 'boards.greenhouse.io' matches '*.greenhouse.io'
    parts = hostname.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in ALLOWED_DOMAINS:
            return True

    # Employer career site pattern match
    for pattern in _EMPLOYER_CAREER_PATTERNS:
        if pattern.search(hostname):
            return True

    return False


def _check_ip_literal(hostname: str) -> Optional[str]:
    """If hostname is an IP literal, check it against blocked ranges."""
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return None  # not an IP literal, DNS resolution happens later

    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return f"IP address {hostname} is in a blocked network range (SSRF prevention)"

    return None


def _redact_url(url: str) -> str:
    """Redact sensitive parts of a URL for logging."""
    try:
        parsed = urlparse(url)
        # Redact query params that might contain tokens
        return f"{parsed.scheme}://{parsed.hostname}{parsed.path}"
    except Exception:
        return "<malformed-url>"


# ──────────────────────────────────────────── sanitize job URLs

def sanitize_apply_url(url: str) -> Tuple[str, list[str]]:
    """Strip tracking parameters and validate a job application URL.

    Returns:
        (cleaned_url, warnings)
    """
    warnings = []
    if not url:
        return "", warnings

    allowed, reason = check_url(url, allow_user_provided=True)
    if not allowed:
        warnings.append(f"Apply URL blocked: {reason}")
        return "", warnings

    try:
        parsed = urlparse(url)
    except Exception:
        return url, warnings

    # Strip common tracking parameters
    tracking_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "ref", "referer", "source", "trk", "trackingId", "currentJobId",
        "refId", "fccid", "vjs", "vjk",
    }

    from urllib.parse import parse_qs, urlencode
    params = parse_qs(parsed.query, keep_blank_values=False)
    clean_params = {k: v for k, v in params.items() if k.lower() not in tracking_params}

    if len(clean_params) < len(params):
        warnings.append("Tracking parameters removed from apply URL")

    clean_query = urlencode(clean_params, doseq=True) if clean_params else ""
    cleaned = parsed._replace(query=clean_query, fragment="").geturl()

    return cleaned, warnings
