"""Himalayas Remote Jobs API Adapter per Section 7.2 of newall-logic.md.

https://himalayas.app/jobs/api?limit=50
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import http_get_json, clean_text, html_to_text

log = logging.getLogger("jobhunter.sources.himalayas")


class HimalayasAdapter(BaseSourceAdapter):
    source_name: str = "Himalayas"

    def search(
        self,
        query: str = "",
        filters: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> SourcePage:
        filters = filters or {}
        params = {"limit": min(50, filters.get("limit", 20))}
        url = f"https://himalayas.app/jobs/api?{urllib.parse.urlencode(params)}"
        try:
            data = http_get_json(url) or {}
            jobs = data.get("jobs", [])
            items = []
            q_lower = query.lower() if query else ""
            for j in jobs:
                title = clean_text(j.get("title", ""))
                if q_lower and q_lower not in title.lower():
                    continue
                jid = f"himalayas-{j.get('id') or abs(hash(j.get('applicationLink', '')))}"
                items.append({
                    "id": jid,
                    "title": title,
                    "company": clean_text(j.get("companyName", "")),
                    "location": "Remote",
                    "work_mode": "Remote",
                    "url": j.get("applicationLink") or "",
                    "apply_url": j.get("applicationLink") or "",
                    "description": html_to_text(j.get("description", ""), 12000),
                    "posted_at": j.get("pubDate") or "",
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("Himalayas fetch failed: %s", e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        return SourceHealth(source_name=self.source_name, is_available=True)
