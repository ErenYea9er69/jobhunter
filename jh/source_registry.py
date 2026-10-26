"""Source registry — declares which job sources exist, their capabilities, and freshness rules.

Each registered source declares:
- Access method (public API, feed, career site, authorized API, user-provided)
- Supported query filters (location, remote, seniority, salary, etc.)
- Regional endpoint configuration
- Freshness / cache TTL rules
- Rate limiting and pagination bounds

The registry is the single source of truth for what adapters the pipeline
may invoke. Pipeline.py reads capabilities from here to decide which
adapters match a given query.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set

from .models import SourceAccessMethod, WarningCategory

log = logging.getLogger("jobhunter.source_registry")


# ──────────────────────────────────────────── source descriptor

@dataclass
class SourceCapabilities:
    """What a single source adapter can do."""
    supports_keyword: bool = True
    supports_location: bool = True
    supports_remote: bool = False
    supports_seniority: bool = False
    supports_salary_filter: bool = False
    supports_job_type: bool = False
    supports_company_filter: bool = False
    supports_pagination: bool = True
    max_pages: int = 5
    max_results_per_page: int = 25

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceDescriptor:
    """Full declaration for one job source adapter."""
    name: str = ""
    access_method: SourceAccessMethod = SourceAccessMethod.PUBLIC_FEED
    capabilities: SourceCapabilities = field(default_factory=SourceCapabilities)
    enabled: bool = True
    requires_api_key: bool = False
    api_key_env_var: str = ""
    base_url: str = ""
    regional_endpoints: dict[str, str] = field(default_factory=dict)
    # Freshness
    cache_ttl_seconds: int = 900        # 15 min default for search results
    detail_ttl_seconds: int = 3600      # 1 hour for job detail pages
    # Rate limiting
    rate_limit_rpm: int = 60            # requests per minute
    request_timeout_seconds: float = 10.0
    max_retries: int = 2
    # Circuit breaker
    circuit_breaker_threshold: int = 3
    circuit_breaker_cooldown: int = 300
    # Metadata
    documentation_url: str = ""
    terms_url: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["access_method"] = self.access_method.value
        return d


# ──────────────────────────────────────────── registry

class SourceRegistry:
    """Central registry of all known job source adapters."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceDescriptor] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the built-in source adapters."""

        # ── Direct employer ATS (public APIs)
        self.register(SourceDescriptor(
            name="Greenhouse",
            access_method=SourceAccessMethod.PUBLIC_API,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=False,
                supports_remote=False, supports_pagination=True,
                max_pages=10, max_results_per_page=100,
            ),
            base_url="https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
            documentation_url="https://developers.greenhouse.io/job-board.html",
            notes="Public Job Board API for published jobs. Board token required per company.",
        ))

        self.register(SourceDescriptor(
            name="Lever",
            access_method=SourceAccessMethod.PUBLIC_API,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_remote=False, supports_pagination=True,
                max_pages=5, max_results_per_page=50,
            ),
            base_url="https://api.lever.co/v0/postings/{company}",
            documentation_url="https://github.com/lever/postings-api",
            notes="Public postings API for job-board integrations.",
        ))

        self.register(SourceDescriptor(
            name="Ashby",
            access_method=SourceAccessMethod.PUBLIC_API,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_pagination=True,
            ),
            base_url="https://api.ashbyhq.com/posting-api/job-board/{board}",
        ))

        # ── Major job boards (native scrapers in sources.py)
        self.register(SourceDescriptor(
            name="LinkedIn",
            access_method=SourceAccessMethod.CAREER_SITE,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_remote=True, supports_seniority=True,
                supports_salary_filter=False, supports_job_type=True,
                supports_pagination=True, max_pages=5,
            ),
            rate_limit_rpm=30,
            request_timeout_seconds=12.0,
            notes="Uses public search results only. Does not scrape logged-in pages.",
        ))

        self.register(SourceDescriptor(
            name="Indeed",
            access_method=SourceAccessMethod.CAREER_SITE,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_remote=True, supports_job_type=True,
                supports_pagination=True, max_pages=5,
            ),
            rate_limit_rpm=20,
            request_timeout_seconds=12.0,
        ))

        self.register(SourceDescriptor(
            name="ZipRecruiter",
            access_method=SourceAccessMethod.CAREER_SITE,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_remote=True, supports_pagination=True,
                max_pages=3,
            ),
            rate_limit_rpm=20,
        ))

        # ── Free feeds and APIs
        self.register(SourceDescriptor(
            name="Hacker News",
            access_method=SourceAccessMethod.PUBLIC_FEED,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=False,
                supports_pagination=False, max_pages=1,
            ),
            base_url="https://hacker-news.firebaseio.com/v0/",
            cache_ttl_seconds=1800,
            notes="Monthly Who is Hiring threads. Volunteer-posted, no structured data.",
        ))

        self.register(SourceDescriptor(
            name="Y Combinator",
            access_method=SourceAccessMethod.PUBLIC_API,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_remote=True, supports_pagination=True,
            ),
            base_url="https://www.workatastartup.com/",
        ))

        self.register(SourceDescriptor(
            name="Himalayas",
            access_method=SourceAccessMethod.PUBLIC_API,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_remote=True, supports_pagination=True,
            ),
            base_url="https://himalayas.app/jobs/api",
        ))

        self.register(SourceDescriptor(
            name="Jobicy",
            access_method=SourceAccessMethod.PUBLIC_FEED,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=False,
                supports_remote=True, supports_pagination=False,
            ),
            base_url="https://jobicy.com/api/v2/remote-jobs",
        ))

        self.register(SourceDescriptor(
            name="Arbeitnow",
            access_method=SourceAccessMethod.PUBLIC_API,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_remote=True, supports_pagination=True,
            ),
            base_url="https://www.arbeitnow.com/api/job-board-api",
        ))

        self.register(SourceDescriptor(
            name="Adzuna",
            access_method=SourceAccessMethod.AUTHORIZED_API,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_salary_filter=True, supports_pagination=True,
            ),
            requires_api_key=True,
            api_key_env_var="ADZUNA_APP_KEY",
            base_url="https://api.adzuna.com/v1/api/jobs/{country}/search",
            regional_endpoints={
                "us": "https://api.adzuna.com/v1/api/jobs/us/search",
                "gb": "https://api.adzuna.com/v1/api/jobs/gb/search",
                "de": "https://api.adzuna.com/v1/api/jobs/de/search",
                "fr": "https://api.adzuna.com/v1/api/jobs/fr/search",
                "au": "https://api.adzuna.com/v1/api/jobs/au/search",
                "ca": "https://api.adzuna.com/v1/api/jobs/ca/search",
            },
        ))

        # ── Regional boards
        self.register(SourceDescriptor(
            name="Bayt",
            access_method=SourceAccessMethod.CAREER_SITE,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_pagination=True, max_pages=3,
            ),
            regional_endpoints={"mena": "https://www.bayt.com"},
            notes="Major Middle East job board.",
        ))

        self.register(SourceDescriptor(
            name="Naukri",
            access_method=SourceAccessMethod.CAREER_SITE,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_pagination=True, max_pages=3,
            ),
            regional_endpoints={"in": "https://www.naukri.com"},
            notes="Major India job board.",
        ))

        self.register(SourceDescriptor(
            name="HelloWork",
            access_method=SourceAccessMethod.CAREER_SITE,
            capabilities=SourceCapabilities(
                supports_keyword=True, supports_location=True,
                supports_pagination=True, max_pages=3,
            ),
            regional_endpoints={"fr": "https://www.hellowork.com"},
            notes="Major France job board.",
        ))

        # ── Paid/gated sources (enabled but flagged)
        for name in ("We Work Remotely", "Remotive", "Remote OK"):
            self.register(SourceDescriptor(
                name=name,
                access_method=SourceAccessMethod.PUBLIC_FEED,
                capabilities=SourceCapabilities(
                    supports_keyword=True, supports_remote=True,
                    supports_pagination=False,
                ),
                notes="Candidate may face a paywall to apply. Jobs are still discoverable.",
            ))

    def register(self, source: SourceDescriptor) -> None:
        """Register or update a source descriptor."""
        self._sources[source.name] = source
        log.debug("Registered source: %s", source.name)

    def get(self, name: str) -> Optional[SourceDescriptor]:
        return self._sources.get(name)

    def all(self) -> list[SourceDescriptor]:
        return list(self._sources.values())

    def enabled(self) -> list[SourceDescriptor]:
        return [s for s in self._sources.values() if s.enabled]

    def matching(self, **filters: Any) -> list[SourceDescriptor]:
        """Return sources whose capabilities match the given query filters.

        Example: matching(supports_remote=True) returns only sources
        that can filter by remote.
        """
        result = []
        for src in self.enabled():
            caps = src.capabilities
            match = True
            for key, val in filters.items():
                if val and hasattr(caps, key) and not getattr(caps, key):
                    match = False
                    break
            if match:
                result.append(src)
        return result

    def names(self) -> list[str]:
        return list(self._sources.keys())

    def health_summary(self) -> dict[str, Any]:
        """Return a privacy-safe summary for the MCP resource."""
        entries = []
        for src in self._sources.values():
            entries.append({
                "name": src.name,
                "enabled": src.enabled,
                "access_method": src.access_method.value,
                "requires_api_key": src.requires_api_key,
                "cache_ttl_seconds": src.cache_ttl_seconds,
                "rate_limit_rpm": src.rate_limit_rpm,
            })
        return {
            "total_sources": len(self._sources),
            "enabled_count": sum(1 for s in self._sources.values() if s.enabled),
            "sources": entries,
        }

    def to_dict(self) -> dict[str, Any]:
        return {name: src.to_dict() for name, src in self._sources.items()}


# Module-level singleton
_registry: Optional[SourceRegistry] = None


def get_registry() -> SourceRegistry:
    """Get or create the global source registry singleton."""
    global _registry
    if _registry is None:
        _registry = SourceRegistry()
    return _registry
