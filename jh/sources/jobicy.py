"""Jobicy Remote Jobs API Adapter per Section 7.2 of newall-logic.md.

https://jobicy.com/api/v2/remote-jobs
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import http_get_json, clean_text, html_to_text

log = logging.getLogger("jobhunter.sources.jobicy")


class JobicyAdapter(BaseSourceAdapter):
    source_name: str = "Jobicy"

    def search(
        self,
        query: str = "",
        filters: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> SourcePage:
        filters = filters or {}
        params = {"count": min(50, filters.get("limit", 20))}
        if query:
            params["tag"] = query
        url = f"https://jobicy.com/api/v2/remote-jobs?{urllib.parse.urlencode(params)}"
        try:
            data = http_get_json(url) or {}
            jobs = data.get("jobs", [])
            items = []
            for j in jobs:
                jid = f"jobicy-{j.get('id')}"
                items.append({
                    "id": jid,
                    "title": clean_text(j.get("jobTitle", "")),
                    "company": clean_text(j.get("companyName", "")),
                    "location": clean_text(j.get("jobGeo", "Remote")),
                    "work_mode": "Remote",
                    "url": j.get("url") or "",
                    "apply_url": j.get("url") or "",
                    "salary": clean_text(j.get("annualSalaryMin", "")),
                    "description": html_to_text(j.get("jobDescription", ""), 12000),
                    "posted_at": j.get("pubDate") or "",
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("Jobicy fetch failed: %s", e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        return SourceHealth(source_name=self.source_name, is_available=True)
