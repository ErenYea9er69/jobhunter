"""SmartRecruiters Public Posting API Adapter per Section 7.1 of newall-logic.md.

https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import http_get_json, clean_text

log = logging.getLogger("jobhunter.sources.smartrecruiters")


class SmartRecruitersAdapter(BaseSourceAdapter):
    source_name: str = "SmartRecruiters"

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

        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
        try:
            data = http_get_json(url) or {}
            postings = data.get("content", [])
            items = []
            q_lower = query.lower() if query else ""
            for p in postings:
                name = clean_text(p.get("name", ""))
                if q_lower and q_lower not in name.lower():
                    continue
                loc = (p.get("location") or {}).get("city", "")
                jid = f"sr-{slug}-{p.get('id')}"
                job_url = f"https://jobs.smartrecruiters.com/{slug}/{p.get('id')}"
                items.append({
                    "id": jid,
                    "title": name,
                    "company": slug.replace("-", " ").title(),
                    "location": loc,
                    "url": job_url,
                    "apply_url": job_url,
                    "posted_at": p.get("releasedDate") or "",
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("SmartRecruiters fetch failed for %s: %s", slug, e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        return SourceHealth(source_name=self.source_name, is_available=True)
