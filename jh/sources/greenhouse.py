"""Greenhouse Job Board Adapter per Section 7.1 of newall-logic.md.

Integrates with Greenhouse Public Job Board API:
https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage, SourceJob
from ..util import http_get_json, clean_text, html_to_text

log = logging.getLogger("jobhunter.sources.greenhouse")


class GreenhouseAdapter(BaseSourceAdapter):
    source_name: str = "Greenhouse"

    def search(
        self,
        query: str = "",
        filters: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> SourcePage:
        filters = filters or {}
        slug = filters.get("slug") or filters.get("company_slug")
        if not slug:
            return SourcePage(source_name=self.source_name, items=[])

        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        try:
            data = http_get_json(url) or {}
            jobs = data.get("jobs", [])
            items = []
            q_lower = query.lower() if query else ""
            for j in jobs:
                title = clean_text(j.get("title", ""))
                if q_lower and q_lower not in title.lower():
                    continue
                loc = clean_text((j.get("location") or {}).get("name", ""))
                jid = f"greenhouse-{slug}-{j.get('id')}"
                items.append({
                    "id": jid,
                    "title": title,
                    "company": slug.replace("-", " ").title(),
                    "location": loc,
                    "url": j.get("absolute_url") or "",
                    "apply_url": j.get("absolute_url") or "",
                    "description": html_to_text(j.get("content", ""), 12000),
                    "posted_at": j.get("updated_at") or "",
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("Greenhouse fetch failed for %s: %s", slug, e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        return SourceHealth(source_name=self.source_name, is_available=True)
