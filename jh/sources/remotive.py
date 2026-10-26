"""Remotive Remote Jobs API Adapter per Section 7.2 of newall-logic.md.

https://remotive.com/api/remote-jobs
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import http_get_json, clean_text, html_to_text

log = logging.getLogger("jobhunter.sources.remotive")


class RemotiveAdapter(BaseSourceAdapter):
    source_name: str = "Remotive"

    def search(
        self,
        query: str = "",
        filters: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> SourcePage:
        filters = filters or {}
        limit = min(50, filters.get("limit", 20))
        url = f"https://remotive.com/api/remote-jobs?limit={limit}"
        if query:
            url += f"&search={urllib.parse.quote(query)}"
        try:
            data = http_get_json(url) or {}
            jobs = data.get("jobs", [])
            items = []
            for j in jobs:
                jid = f"remotive-{j.get('id')}"
                items.append({
                    "id": jid,
                    "title": clean_text(j.get("title", "")),
                    "company": clean_text(j.get("company_name", "")),
                    "location": clean_text(j.get("candidate_required_location", "Remote")),
                    "work_mode": "Remote",
                    "url": j.get("url") or "",
                    "apply_url": j.get("url") or "",
                    "description": html_to_text(j.get("description", ""), 12000),
                    "salary": clean_text(j.get("salary", "")),
                    "posted_at": j.get("publication_date") or "",
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("Remotive search failed: %s", e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        return SourceHealth(source_name=self.source_name, is_available=True)
