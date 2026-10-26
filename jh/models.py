"""Canonical domain records and enums.

Owns shared data structures for profiles, evidence, jobs, scores,
applications, source outcomes, and generated artifacts.  Every module
that needs a domain type imports from here.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

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


class ApplicationStage(str, enum.Enum):
    """Lifecycle stage of a tracked application."""
    SAVED = "saved"
    APPLIED = "applied"
    SCREENING = "screening"
    PHONE_SCREEN = "phone_screen"
    TECHNICAL = "technical"
    ONSITE = "onsite"
    OFFER = "offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    ARCHIVED = "archived"


class ResumeArchetype(str, enum.Enum):
    """Tailoring style for resume generation."""
    STARTUP_VELOCITY = "startup_velocity"
    ENTERPRISE_SCALE = "enterprise_scale"
    TECHNICAL_DEPTH = "technical_depth"


class WorkMode(str, enum.Enum):
    """Candidate or job work-mode preference."""
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class SourceAccessMethod(str, enum.Enum):
    """How a source adapter retrieves job data."""
    PUBLIC_API = "public_api"
    PUBLIC_FEED = "public_feed"
    CAREER_SITE = "career_site"
    AUTHORIZED_API = "authorized_api"
    USER_PROVIDED = "user_provided"


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


@dataclass
class CandidateProfile:
    """Normalized candidate profile built from one resume variant."""
    profile_id: str = field(default_factory=lambda: _new_id("prof_"))
    variant_name: str = ""
    source_file: str = ""
    source_hash: str = ""
    parsed_at: str = field(default_factory=now_iso)
    target_title: str = ""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    experience: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    contact: dict[str, str] = field(default_factory=dict)
    years_of_experience: Optional[float] = None
    evidence_ids: list[str] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedJob:
    """A job posting after normalization and source metadata attachment."""
    job_id: str = field(default_factory=lambda: _new_id("job_"))
    title: str = ""
    company: str = ""
    location: str = ""
    work_mode: WorkMode = WorkMode.UNKNOWN
    salary_raw: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "USD"
    salary_period: str = "year"
    job_type: str = ""
    description: str = ""
    requirements: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)
    apply_url: str = ""
    source_name: str = ""
    source_url: str = ""
    source_job_id: str = ""
    retrieved_at: str = field(default_factory=now_iso)
    published_at: str = ""
    first_seen_at: str = field(default_factory=now_iso)
    last_seen_at: str = field(default_factory=now_iso)
    last_verified_at: str = field(default_factory=now_iso)
    cache_status: str = "fresh"
    duplicate_of: Optional[str] = None
    duplicate_confidence: Optional[float] = None
    source_refs: list[dict[str, str]] = field(default_factory=list)
    data_completeness: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["work_mode"] = self.work_mode.value
        return d


@dataclass
class ScoreBreakdown:
    """Explainable 100-point fit score with component detail."""
    total: float = 0.0
    skill_match: float = 0.0
    title_domain: float = 0.0
    seniority_experience: float = 0.0
    work_mode_compensation: float = 0.0
    matched_skills: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_preferred: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    data_completeness: float = 1.0
    scoring_version: str = "1.0"
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageEvent:
    """A single timestamped event in application history."""
    stage: ApplicationStage = ApplicationStage.SAVED
    timestamp: str = field(default_factory=now_iso)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stage"] = self.stage.value
        return d


@dataclass
class ApplicationRecord:
    """A tracked job application with stage history."""
    app_id: str = field(default_factory=lambda: _new_id("app_"))
    job_id: str = ""
    job_title: str = ""
    company: str = ""
    source_url: str = ""
    resume_variant: str = ""
    cover_letter_version: str = ""
    current_stage: ApplicationStage = ApplicationStage.SAVED
    applied_at: Optional[str] = None
    next_action_at: Optional[str] = None
    history: list[StageEvent] = field(default_factory=list)
    contact: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["current_stage"] = self.current_stage.value
        d["history"] = [e if isinstance(e, dict) else e.to_dict()
                        for e in (self.history or [])]
        return d


@dataclass
class ArtifactManifest:
    """Metadata for a generated output (tailored resume, cover letter, etc.)."""
    artifact_id: str = field(default_factory=lambda: _new_id("art_"))
    artifact_type: str = ""           # "tailored_resume", "cover_letter", etc.
    source_profile_id: str = ""
    job_id: str = ""
    prompt_version: str = ""
    grounding_status: str = ""        # "approved", "needs_review"
    claim_evidence: list[dict[str, str]] = field(default_factory=list)
    honest_gaps: list[str] = field(default_factory=list)
    output_path: str = ""
    export_format: str = ""
    generated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolResult:
    """Standard result envelope for every MCP tool response."""
    status: ToolOutcome = ToolOutcome.OK
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, str]] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)
    generated_at: str = field(default_factory=now_iso)
    correlation_id: str = field(default_factory=lambda: _new_id("cor_"))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def add_warning(self, category: WarningCategory, message: str) -> None:
        self.warnings.append({"category": category.value, "message": message})
        if self.status == ToolOutcome.OK:
            self.status = ToolOutcome.PARTIAL


@dataclass
class SourceOutcome:
    """Result metadata from a single source adapter call."""
    source_name: str = ""
    success: bool = True
    job_count: int = 0
    duration_ms: float = 0.0
    warning: Optional[str] = None
    warning_category: Optional[WarningCategory] = None
    cached: bool = False
    retrieved_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.warning_category:
            d["warning_category"] = self.warning_category.value
        return d
