"""Shared enums and the evidence record.

Evidence claims and tool outcomes are the only types shared across modules.
Jobs, profiles and applications are plain dicts (see ``jh.db`` and ``jh.tracker``).
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .util import now_iso


# ──────────────────────────────────────────── enums

class ClaimType(str, enum.Enum):
    """Category of a candidate evidence claim."""
    SKILL = "skill"
    EMPLOYMENT = "employment"
    EDUCATION = "education"
    PROJECT = "project"
    METRIC = "metric"
    CERTIFICATION = "certification"


class ExtractionStatus(str, enum.Enum):
    """Parser confidence in a single extracted datum."""
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    UNPARSED = "unparsed"


class GroundingVerdict(str, enum.Enum):
    """Result of matching a generated claim against candidate evidence."""
    SUPPORTED = "supported"
    DERIVED = "derived"
    NEEDS_REVIEW = "needs_review"
    UNSUPPORTED = "unsupported"


class ToolOutcome(str, enum.Enum):
    """Standard result status for every MCP tool response."""
    OK = "ok"
    PARTIAL = "partial"
    NEEDS_REVIEW = "needs_review"
    ERROR = "error"


class WarningCategory(str, enum.Enum):
    """Categories for source and tool warnings."""
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    ACCESS_DENIED = "access_denied"
    PARSE_ERROR = "parse_error"
    STALE_DATA = "stale_data"
    NETWORK_ERROR = "network_error"
    CAPTCHA = "captcha"
    EMPTY_RESULT = "empty_result"
    INVALID_INPUT = "invalid_input"
    STORAGE_ERROR = "storage_error"
    INTERNAL_ERROR = "internal_error"


# ──────────────────────────────────────────── data records

def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


@dataclass
class SourceLocation:
    """Where inside a document a piece of evidence was found."""
    page: Optional[int] = None
    section: Optional[str] = None
    span: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class EvidenceClaim:
    """A single provenance-tracked candidate fact."""
    evidence_id: str = field(default_factory=lambda: _new_id("ev_"))
    claim_type: ClaimType = ClaimType.SKILL
    canonical_value: str = ""
    raw_value: str = ""
    source_file: str = ""
    source_location: SourceLocation = field(default_factory=SourceLocation)
    extraction_status: ExtractionStatus = ExtractionStatus.NEEDS_REVIEW
    candidate_confirmed: bool = False
    first_seen_at: str = field(default_factory=now_iso)
    last_confirmed_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["claim_type"] = self.claim_type.value
        d["extraction_status"] = self.extraction_status.value
        d["source_location"] = self.source_location.to_dict()
        return d


