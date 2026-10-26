"""USAJOBS Federal Jobs API Adapter per Section 7.2 of newall-logic.md.

https://developer.usajobs.gov/api-reference/get-api-search
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import http_get_json, clean_text

log = logging.getLogger("jobhunter.sources.usajobs")


class USAJobsAdapter(BaseSourceAdapter):
    source_name: str = "USAJOBS"

    def search(
        self,
        query: str = "",
        filters: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> SourcePage:
        api_key = os.environ.get("USAJOBS_API_KEY")
        user_agent = os.environ.get("USAJOBS_USER_AGENT")
        if not api_key or not user_agent:
            return SourcePage(source_name=self.source_name, items=[])

        url = f"https://data.usajobs.gov/api/search?Keyword={urllib.parse.quote(query or 'technology')}"
        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": user_agent,
            "Authorization-Key": api_key,
        }
        try:
            data = http_get_json(url, headers=headers) or {}
            items = []
            results = (data.get("SearchResult") or {}).get("SearchResultItems", [])
            for r in results:
                matched_obj = r.get("MatchedObjectDescriptor", {})
                jid = f"usajobs-{matched_obj.get('PositionID')}"
                pos_uri = matched_obj.get("PositionURI", "")
                items.append({
                    "id": jid,
                    "title": clean_text(matched_obj.get("PositionTitle", "")),
                    "company": clean_text(matched_obj.get("OrganizationName", "US Federal Government")),
                    "location": clean_text((matched_obj.get("PositionLocation", [{}])[0]).get("LocationName", "")),
                    "url": pos_uri,
                    "apply_url": matched_obj.get("ApplyURI", [pos_uri])[0] if matched_obj.get("ApplyURI") else pos_uri,
                    "posted_at": matched_obj.get("PublicationStartDate", ""),
                    "source": self.source_name,
                })
            return SourcePage(source_name=self.source_name, items=items, total_count=len(items))
        except Exception as e:
            log.warning("USAJOBS search failed: %s", e)
            return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        has_keys = bool(os.environ.get("USAJOBS_API_KEY") and os.environ.get("USAJOBS_USER_AGENT"))
        return SourceHealth(source_name=self.source_name, is_available=has_keys)
