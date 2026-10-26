"""Jooble API Adapter per Section 7.2 of newall-logic.md.

Credentialed REST API with quota limits.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from .base import BaseSourceAdapter, SourceHealth, SourcePage

log = logging.getLogger("jobhunter.sources.jooble")


class JoobleAdapter(BaseSourceAdapter):
    source_name: str = "Jooble"

    def search(
        self,
        query: str = "",
        filters: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> SourcePage:
        key = os.environ.get("JOOBLE_API_KEY")
        if not key:
            return SourcePage(source_name=self.source_name, items=[])
        # Stub for optional credentialed access
        return SourcePage(source_name=self.source_name, items=[])

    def health_check(self) -> SourceHealth:
        has_key = bool(os.environ.get("JOOBLE_API_KEY"))
        return SourceHealth(source_name=self.source_name, is_available=has_key)
