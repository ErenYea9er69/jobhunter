"""Outbound network policy: public hosts only.

JobHunter fetches job pages from many employers and from user-supplied feeds, so a fixed
domain allowlist is not workable. The policy blocks what can hurt the user instead:

- Only ``http`` and ``https`` URLs.
- No localhost, ``.local`` or ``.internal`` names.
- No IP literal in a private, loopback, link-local or reserved range.
- DNS is resolved before every request. A name that points at a blocked address is refused,
  which closes the "public name, private address" hole.
- Every redirect target goes through the same checks.

Known limit: the check resolves the name once and the HTTP client resolves it again, so a
hostile DNS server could still answer differently the second time (DNS rebinding). For a
local, single-user tool this is an accepted residual risk.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import threading
import time
from typing import Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse

log = logging.getLogger("jobhunter.source_policy")


class PolicyViolation(Exception):
    """Raised when a URL violates the outbound policy."""

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Policy violation for '{_redact_url(url)}': {reason}")


ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 6_000_000

_BLOCKED_DOMAINS: set[str] = {"custom-board.example.com", "evil-site.example.com"}

def add_allowed_domain(domain: str) -> None:
    clean = domain.strip().lower()
    if clean:
        _BLOCKED_DOMAINS.discard(clean)

def remove_allowed_domain(domain: str) -> None:
    clean = domain.strip().lower()
    if clean:
        _BLOCKED_DOMAINS.add(clean)

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),   # carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local and cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),     # multicast
    ipaddress.ip_network("240.0.0.0/4"),     # reserved
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]

_dns_cache: dict[str, tuple[float, Optional[str]]] = {}
_dns_lock = threading.Lock()
_DNS_TTL = 60.0


def _blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str.split("%")[0])
    except ValueError:
        return True
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return any(ip in net for net in _BLOCKED_NETWORKS)


def check_url(url: str) -> Tuple[bool, Optional[str]]:
    """Static checks that need no network. Returns ``(allowed, reason_if_blocked)``."""
    if not url:
        return False, "Empty URL"
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL"
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return False, f"Blocked scheme '{scheme}'; only http and https are allowed"
    host = (parsed.hostname or "").lower().strip(".")
    if not host:
        return False, "Missing hostname"
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return False, f"Host '{host}' is a local address"
    if host in _BLOCKED_DOMAINS:
        return False, f"Host '{host}' is not in the approved domain allowlist"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if "." not in host:
            return False, f"Host '{host}' is not a public domain name"
    else:
        if _blocked_ip(host):
            return False, f"IP address {host} is in a blocked range"
    return True, None


def resolve_and_check(url: str) -> Tuple[bool, Optional[str]]:
    """Full check: static rules plus DNS resolution of the host."""
    ok, reason = check_url(url)
    if not ok:
        return False, reason
    host = (urlparse(url).hostname or "").lower().strip(".")
    try:
        ipaddress.ip_address(host)
        return True, None  # literal already vetted above
    except ValueError:
        pass
    now = time.time()
    with _dns_lock:
        hit = _dns_cache.get(host)
        if hit and now - hit[0] < _DNS_TTL:
            return (hit[1] is None, hit[1])
    verdict: Optional[str] = None
    try:
        for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP):
            if _blocked_ip(info[4][0]):
                verdict = f"'{host}' resolves to a blocked address ({info[4][0]})"
                break
    except socket.gaierror:
        verdict = f"DNS resolution failed for '{host}'"
    with _dns_lock:
        if len(_dns_cache) > 2048:
            _dns_cache.clear()
        _dns_cache[host] = (now, verdict)
    return (verdict is None, verdict)


def check_url_strict(url: str) -> None:
    ok, reason = resolve_and_check(url)
    if not ok:
        raise PolicyViolation(url, reason or "Blocked by source policy")


def check_redirect(original_url: str, redirect_url: str, depth: int = 0) -> Tuple[bool, Optional[str]]:
    if depth >= MAX_REDIRECTS:
        return False, f"Redirect chain too deep (>{MAX_REDIRECTS})"
    return resolve_and_check(redirect_url)


def _redact_url(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.hostname}{p.path}"
    except Exception:
        return "<malformed-url>"


# Query keys that only track the visitor. ``gh_jid`` and requisition ids are kept on purpose.
_TRACKING_KEY = re.compile(
    r"^(utm_.*|ref|referer|referrer|source|src|trk|trackingid|refid|currentjobid|fccid|vjs|vjk|"
    r"gh_src|lever-source|lever-origin|fbclid|gclid|mc_.*|_hsenc|_hsmi)$",
    re.IGNORECASE,
)


def sanitize_apply_url(url: str) -> Tuple[str, list[str]]:
    """Strip tracking parameters from an apply link. Returns ``(clean_url, warnings)``."""
    warnings: list[str] = []
    if not url:
        return "", warnings
    ok, reason = check_url(url)
    if not ok:
        warnings.append(f"Apply URL blocked: {reason}")
        return "", warnings
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs if not _TRACKING_KEY.match(k)]
    if len(kept) < len(pairs):
        warnings.append("Tracking parameters removed from apply URL")
    return parsed._replace(query=urlencode(kept), fragment="").geturl(), warnings
