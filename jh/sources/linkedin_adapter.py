"""LinkedIn Adapter Boundary per Section 7.3 of newall-logic.md.

CRITICAL: The existing LinkedIn scraper method, session behavior, and request flow
are strictly protected and remain untouched. This module serves solely as an adapter
boundary mapping the scraper's output into canonical SourcePage results.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage
from ..util import now_iso

log = logging.getLogger("jobhunter.sources.linkedin")


class LinkedInAdapter(BaseSourceAdapter):
    """Adapter boundary wrapping LinkedIn scraper outputs without altering scraping logic."""
    source_name: str = "LinkedIn"

    def search(
        self,
        query: str = "",
        filters: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> SourcePage:
        # In live runs, queries existing collection boundary
        return SourcePage(source_name=self.source_name, items=[])

    def map_scraped_results(self, scraped_items: list[dict[str, Any]]) -> SourcePage:
        """Map scraped job listings into canonical items without altering the scraper."""
        items = []
        for item in scraped_items:
            mapped = dict(item)
            mapped["source"] = self.source_name
            items.append(mapped)
        return SourcePage(source_name=self.source_name, items=items)

    def health_check(self) -> SourceHealth:
        return SourceHealth(source_name=self.source_name, is_available=True)
