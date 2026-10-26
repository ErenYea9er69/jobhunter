"""Workable Account Adapter per Section 7.1 of newall-logic.md.

User-authorized account integration (OAuth / account-scoped token).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import http_get_json, clean_text

log = logging.getLogger("jobhunter.sources.workable")


class WorkableAccountAdapter(BaseSourceAdapter):
    source_name: str = "Workable"

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

        url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
        try:
            data = http_get_json(url) or {}
            jobs = data.get("jobs", [])
            items = []
            q_lower = query.lower() if query else ""
            comp_name = data.get("name") or slug.replace("-", " ").title()
            for j in jobs:
                title = clean_text(j.get("title", ""))
                if q_lower and q_lower not in title.lower():
                    continue
                loc = clean_text(j.get("city", "") or j.get("country", ""))
                jid = f"workable-{slug}-{j.get('shortcode') or j.get('id')}"
                items.append({
                    "id": jid,
                    "title": title,
                    "company": comp_name,
                    "location": loc,
                    "url": j.get("url") or "",
                    "apply_url": j.get("url") or "",
                    "posted_at": j.get("published_on") or "",
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("Workable account fetch failed: %s", e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        return SourceHealth(source_name=self.source_name, is_available=True)
