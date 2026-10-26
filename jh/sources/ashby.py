"""Ashby Job Postings API Adapter per Section 7.1 of newall-logic.md.

https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import http_get_json, clean_text, html_to_text

log = logging.getLogger("jobhunter.sources.ashby")


class AshbyAdapter(BaseSourceAdapter):
    source_name: str = "Ashby"

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

        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
        try:
            data = http_get_json(url) or {}
            jobs = data.get("jobs", [])
            items = []
            q_lower = query.lower() if query else ""
            for j in jobs:
                title = clean_text(j.get("title", ""))
                if q_lower and q_lower not in title.lower():
                    continue
                loc = clean_text(j.get("location", ""))
                jid = f"ashby-{slug}-{j.get('id')}"
                items.append({
                    "id": jid,
                    "title": title,
                    "company": slug.replace("-", " ").title(),
                    "location": loc,
                    "url": j.get("jobUrl") or "",
                    "apply_url": j.get("applyUrl") or j.get("jobUrl") or "",
                    "description": html_to_text(j.get("descriptionHtml", ""), 12000),
                    "posted_at": j.get("publishedAt") or "",
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("Ashby fetch failed for %s: %s", slug, e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        return SourceHealth(source_name=self.source_name, is_available=True)
