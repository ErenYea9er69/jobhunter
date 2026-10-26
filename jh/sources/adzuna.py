"""Adzuna API Adapter per Section 7.2 of newall-logic.md.

Requires app_id and app_key.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import http_get_json, clean_text

log = logging.getLogger("jobhunter.sources.adzuna")


class AdzunaAdapter(BaseSourceAdapter):
    source_name: str = "Adzuna"

    def search(
        self,
        query: str = "",
        filters: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> SourcePage:
        app_id = os.environ.get("ADZUNA_APP_ID")
        app_key = os.environ.get("ADZUNA_APP_KEY")
        if not app_id or not app_key:
            return SourcePage(source_name=self.source_name, items=[])

        country = (filters or {}).get("country", "us").lower()
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?app_id={app_id}&app_key={app_key}&what={urllib.parse.quote(query or 'developer')}"
        try:
            data = http_get_json(url) or {}
            results = data.get("results", [])
            items = []
            for r in results:
                items.append({
                    "id": f"adzuna-{r.get('id')}",
                    "title": clean_text(r.get("title", "")),
                    "company": clean_text((r.get("company") or {}).get("display_name", "")),
                    "location": clean_text((r.get("location") or {}).get("display_name", "")),
                    "url": r.get("redirect_url") or "",
                    "apply_url": r.get("redirect_url") or "",
                    "description": clean_text(r.get("description", "")),
                    "posted_at": r.get("created") or "",
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("Adzuna search failed: %s", e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        has_keys = bool(os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY"))
        return SourceHealth(source_name=self.source_name, is_available=has_keys)
