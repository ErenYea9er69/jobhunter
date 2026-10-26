"""Lever Postings API Adapter per Section 7.1 of newall-logic.md.

https://api.lever.co/v0/postings/{slug}?mode=json
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import http_get_json, clean_text, html_to_text

log = logging.getLogger("jobhunter.sources.lever")


class LeverAdapter(BaseSourceAdapter):
    source_name: str = "Lever"

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

        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        try:
            postings = http_get_json(url) or []
            items = []
            q_lower = query.lower() if query else ""
            for p in postings:
                title = clean_text(p.get("text", ""))
                if q_lower and q_lower not in title.lower():
                    continue
                cats = p.get("categories") or {}
                loc = clean_text(cats.get("location", ""))
                jid = f"lever-{slug}-{p.get('id')}"
                items.append({
                    "id": jid,
                    "title": title,
                    "company": slug.replace("-", " ").title(),
                    "location": loc,
                    "url": p.get("hostedUrl") or "",
                    "apply_url": p.get("applyUrl") or p.get("hostedUrl") or "",
                    "description": html_to_text(p.get("descriptionPlain", "") or p.get("description", ""), 12000),
                    "posted_at": str(p.get("createdAt", "")),
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("Lever fetch failed for %s: %s", slug, e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        return SourceHealth(source_name=self.source_name, is_available=True)
