"""Shared input/output validation for all MCP tool arguments and domain objects.

Validates and bounds every tool input before the workflow layer touches it.
Rejects malformed values, unexpected sizes, invalid enumerations, and
inconsistent date ranges.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    ApplicationStage,
    ResumeArchetype,
    ToolOutcome,
    WarningCategory,
    WorkMode,
)
from .util import parse_date


# ──────────────────────────────────────────── constants / limits

MAX_QUERY_LENGTH = 500
MAX_LOCATION_LENGTH = 200
MAX_RESULTS_LIMIT = 500
DEFAULT_RESULTS_LIMIT = 50
MAX_DESCRIPTION_LENGTH = 50_000
MAX_NOTES_LENGTH = 5_000
MAX_ANSWER_LENGTH = 10_000
MIN_SALARY = 0
MAX_SALARY = 100_000_000
MAX_DAYS_RANGE = 365
ALLOWED_EXPORT_FORMATS = {"txt", "docx", "pdf", "html", "json", "md"}
ALLOWED_SORT_FIELDS = {"score", "date", "company", "title", "salary"}
ALLOWED_OUTPUT_CATEGORIES = {"tailored", "cover-letters", "reports", "interview-prep"}
SCHEMA_VERSION = "1.0"

# Patterns
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_\-./\\: ]+$")
_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,80}$")


# ──────────────────────────────────────────── result type

class ValidationError(Exception):
    """Raised when tool input fails validation."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"Validation error on '{field}': {message}")


class ValidationResult:
    """Accumulates validation errors and cleaned values."""

    def __init__(self) -> None:
        self.errors: list[ValidationError] = []
        self.cleaned: dict[str, Any] = {}
        self.warnings: list[str] = []

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, field: str, message: str) -> None:
        self.errors.append(ValidationError(field, message))

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def error_dict(self) -> dict[str, str]:
        return {e.field: e.message for e in self.errors}

    def raise_if_invalid(self) -> None:
        if not self.valid:
            raise self.errors[0]

    def __getitem__(self, key: str) -> Any:
        return self.cleaned[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.cleaned[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self.cleaned

    def get(self, key: str, default: Any = None) -> Any:
        return self.cleaned.get(key, default)


# ──────────────────────────────────────────── primitive validators

def validate_string(
    value: Any,
    field: str,
    *,
    max_length: int = 1000,
    required: bool = False,
    strip: bool = True,
    allow_empty: bool = True,
) -> Tuple[str, Optional[str]]:
    """Validate and clean a string field. Returns (cleaned, error_or_None)."""
    if value is None:
        if required:
            return "", f"'{field}' is required"
        return "", None
    s = str(value)
    if strip:
        s = s.strip()
    if not s and required:
        return "", f"'{field}' is required and cannot be empty"
    if not allow_empty and not s:
        return "", f"'{field}' cannot be empty"
    if len(s) > max_length:
        return s[:max_length], f"'{field}' exceeds {max_length} characters, truncated"
    return s, None


def validate_int(
    value: Any,
    field: str,
    *,
    min_val: int = 0,
    max_val: int = 100_000,
    default: int = 0,
    required: bool = False,
) -> Tuple[int, Optional[str]]:
    """Validate an integer field. Returns (cleaned, error_or_None)."""
    if value is None:
        if required:
            return default, f"'{field}' is required"
        return default, None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default, f"'{field}' must be an integer"
    if n < min_val:
        return min_val, f"'{field}' must be at least {min_val}"
    if n > max_val:
        return max_val, f"'{field}' must be at most {max_val}"
    return n, None


def validate_float(
    value: Any,
    field: str,
    *,
    min_val: float = 0.0,
    max_val: float = 1e9,
    default: float = 0.0,
    required: bool = False,
) -> Tuple[float, Optional[str]]:
    """Validate a float field. Returns (cleaned, error_or_None)."""
    if value is None:
        if required:
            return default, f"'{field}' is required"
        return default, None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default, f"'{field}' must be a number"
    if n < min_val:
        return min_val, f"'{field}' must be at least {min_val}"
    if n > max_val:
        return max_val, f"'{field}' must be at most {max_val}"
    return n, None


def validate_enum(
    value: Any,
    field: str,
    enum_class: type,
    *,
    default: Any = None,
    required: bool = False,
) -> Tuple[Any, Optional[str]]:
    """Validate an enum field by value string. Returns (enum_member, error_or_None)."""
    if value is None:
        if required:
            return default, f"'{field}' is required"
        return default, None
    s = str(value).strip().lower()
    for member in enum_class:
        if member.value == s:
            return member, None
    allowed = ", ".join(m.value for m in enum_class)
    return default, f"'{field}' must be one of: {allowed}"


def validate_id(value: Any, field: str, *, required: bool = False) -> Tuple[str, Optional[str]]:
    """Validate an identifier string. Returns (cleaned, error_or_None)."""
    if value is None:
        if required:
            return "", f"'{field}' is required"
        return "", None
    s = str(value).strip()
    if not s and required:
        return "", f"'{field}' is required"
    if s and not _ID_RE.match(s):
        return "", f"'{field}' contains invalid characters"
    return s, None


def validate_date_range(
    start: Any, end: Any, field_prefix: str = "date"
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Validate a date range. Returns (start_iso, end_iso, error_or_None)."""
    s = parse_date(start) if start else None
    e = parse_date(end) if end else None
    if s and e and s > e:
        return None, None, f"'{field_prefix}_start' must be before '{field_prefix}_end'"
    s_str = s.isoformat() if s else None
    e_str = e.isoformat() if e else None
    return s_str, e_str, None


def validate_path_safe(value: Any, field: str) -> Tuple[str, Optional[str]]:
    """Validate a path component is safe (no traversal). Returns (cleaned, error)."""
    if value is None:
        return "", None
    s = str(value).strip()
    if not s:
        return "", None
    if ".." in s or s.startswith("/") or s.startswith("\\"):
        return "", f"'{field}' contains unsafe path characters"
    if not _SAFE_PATH_RE.match(s):
        return "", f"'{field}' contains disallowed characters"
    return s, None


# ──────────────────────────────────────────── compound validators

def validate_search_input(args: dict[str, Any]) -> ValidationResult:
    """Validate search_jobs tool arguments."""
    result = ValidationResult()

    query, err = validate_string(args.get("query"), "query", max_length=MAX_QUERY_LENGTH, required=True)
    if err:
        result.add_error("query", err)
    result.cleaned["query"] = query

    location, err = validate_string(args.get("location"), "location", max_length=MAX_LOCATION_LENGTH)
    if err:
        result.add_warning(err)
    result.cleaned["location"] = location

    limit, err = validate_int(
        args.get("limit"), "limit",
        min_val=1, max_val=MAX_RESULTS_LIMIT, default=DEFAULT_RESULTS_LIMIT,
    )
    if err:
        result.add_warning(err)
    result.cleaned["limit"] = limit

    work_mode, err = validate_enum(args.get("work_mode"), "work_mode", WorkMode, default=None)
    if err:
        result.add_warning(err)
    result.cleaned["work_mode"] = work_mode

    salary_min, err = validate_float(
        args.get("salary_min"), "salary_min", min_val=MIN_SALARY, max_val=MAX_SALARY,
    )
    if err:
        result.add_warning(err)
    result.cleaned["salary_min"] = salary_min

    salary_max, err = validate_float(
        args.get("salary_max"), "salary_max", min_val=MIN_SALARY, max_val=MAX_SALARY,
    )
    if err:
        result.add_warning(err)
    result.cleaned["salary_max"] = salary_max

    if salary_min and salary_max and salary_min > salary_max:
        result.add_warning("salary_min exceeds salary_max; swapping values")
        result.cleaned["salary_min"], result.cleaned["salary_max"] = salary_max, salary_min

    days, err = validate_int(
        args.get("days"), "days", min_val=1, max_val=MAX_DAYS_RANGE, default=30,
    )
    if err:
        result.add_warning(err)
    result.cleaned["days"] = days

    # Pass-through safe fields
    for key in ("seniority", "job_type", "sources", "excluded_companies"):
        val = args.get(key)
        if val is not None:
            result.cleaned[key] = val

    return result


def validate_score_input(args: dict[str, Any]) -> ValidationResult:
    """Validate score_job tool arguments."""
    result = ValidationResult()

    job_id, err = validate_string(args.get("job_id"), "job_id", required=True, max_length=200)
    if err:
        result.add_error("job_id", err)
    result.cleaned["job_id"] = job_id

    profile_id, err = validate_string(args.get("profile_id"), "profile_id", max_length=200)
    if err:
        result.add_warning(err)
    result.cleaned["profile_id"] = profile_id

    return result


def validate_tailor_input(args: dict[str, Any]) -> ValidationResult:
    """Validate tailor_resume tool arguments."""
    result = ValidationResult()

    job_id, err = validate_string(args.get("job_id"), "job_id", required=True, max_length=200)
    if err:
        result.add_error("job_id", err)
    result.cleaned["job_id"] = job_id

    profile_id, err = validate_string(args.get("profile_id"), "profile_id", max_length=200)
    if err:
        result.add_warning(err)
    result.cleaned["profile_id"] = profile_id

    archetype, err = validate_enum(
        args.get("archetype"), "archetype", ResumeArchetype,
        default=ResumeArchetype.TECHNICAL_DEPTH,
    )
    if err:
        result.add_warning(err)
    result.cleaned["archetype"] = archetype

    fmt, err = validate_string(args.get("format"), "format", max_length=20)
    if err:
        result.add_warning(err)
    if fmt and fmt.lower() not in ALLOWED_EXPORT_FORMATS:
        result.add_warning(f"Unsupported format '{fmt}'; defaulting to 'txt'")
        fmt = "txt"
    result.cleaned["format"] = fmt or "txt"

    return result


def validate_track_input(args: dict[str, Any]) -> ValidationResult:
    """Validate track_application tool arguments."""
    result = ValidationResult()

    job_id, err = validate_string(args.get("job_id"), "job_id", max_length=200)
    if err:
        result.add_warning(err)
    result.cleaned["job_id"] = job_id

    company, err = validate_string(args.get("company"), "company", max_length=200)
    if err:
        result.add_warning(err)
    result.cleaned["company"] = company

    title, err = validate_string(args.get("title"), "title", max_length=300)
    if err:
        result.add_warning(err)
    result.cleaned["title"] = title

    stage, err = validate_enum(
        args.get("stage"), "stage", ApplicationStage,
        default=ApplicationStage.APPLIED,
    )
    if err:
        result.add_warning(err)
    result.cleaned["stage"] = stage

    notes, err = validate_string(args.get("notes"), "notes", max_length=MAX_NOTES_LENGTH)
    if err:
        result.add_warning(err)
    result.cleaned["notes"] = notes

    url, err = validate_string(args.get("url"), "url", max_length=2000)
    if err:
        result.add_warning(err)
    result.cleaned["url"] = url

    return result


def validate_screening_input(args: dict[str, Any], raise_on_error: bool = True) -> ValidationResult:
    """Validate screening question solver input."""
    result = ValidationResult()

    job_id = args.get("job_id", "")
    if job_id:
        jid, err = validate_string(job_id, "job_id", max_length=200)
        if err:
            result.add_warning(err)
        result.cleaned["job_id"] = jid
    else:
        result.cleaned["job_id"] = ""

    variant_name, _ = validate_string(args.get("variant_name", ""), "variant_name", max_length=200)
    result.cleaned["variant_name"] = variant_name

    questions = args.get("questions")
    if questions is not None:
        if not isinstance(questions, list) or len(questions) == 0:
            result.add_error("questions", "Must provide at least one screening question")
            result.cleaned["questions"] = []
        else:
            cleaned_q = [str(q).strip() for q in questions if str(q).strip()]
            if not cleaned_q:
                result.add_error("questions", "Questions list contains no valid text")
            result.cleaned["questions"] = cleaned_q
    else:
        question, err = validate_string(
            args.get("question"), "question",
            max_length=MAX_DESCRIPTION_LENGTH, required=True,
        )
        if err:
            result.add_error("question", err)
        result.cleaned["question"] = question
        result.cleaned["questions"] = [question] if question else []

    char_limit, err = validate_int(
        args.get("char_limit"), "char_limit",
        min_val=10, max_val=MAX_ANSWER_LENGTH, default=0,
    )
    if err:
        result.add_warning(err)
    result.cleaned["char_limit"] = char_limit

    word_limit, err = validate_int(
        args.get("word_limit"), "word_limit",
        min_val=5, max_val=2000, default=0,
    )
    if err:
        result.add_warning(err)
    result.cleaned["word_limit"] = word_limit

    if raise_on_error:
        result.raise_if_invalid()
    return result


def validate_mock_interview_input(args: dict[str, Any], raise_on_error: bool = True) -> ValidationResult:
    """Validate practice mock interview question and answer evaluation input."""
    result = ValidationResult()

    question, err = validate_string(args.get("question"), "question", required=True, max_length=10_000)
    if err:
        result.add_error("question", err)
    result.cleaned["question"] = question

    ans, err = validate_string(args.get("candidate_answer"), "candidate_answer", required=True, max_length=50_000)
    if err:
        result.add_error("candidate_answer", err)
    result.cleaned["candidate_answer"] = ans

    role_level, _ = validate_string(args.get("role_level", "senior"), "role_level", max_length=50)
    result.cleaned["role_level"] = role_level or "senior"

    rubric, _ = validate_string(args.get("rubric", "standard"), "rubric", max_length=100)
    result.cleaned["rubric"] = rubric or "standard"

    if raise_on_error:
        result.raise_if_invalid()
    return result


def validate_daily_digest_input(args: dict[str, Any], raise_on_error: bool = True) -> ValidationResult:
    """Validate daily digest parameters."""
    result = ValidationResult()

    date_str, err = validate_string(args.get("date"), "date", max_length=30)
    if err:
        result.add_warning(err)
    result.cleaned["date"] = date_str

    result.cleaned["include_jobs"] = bool(args.get("include_jobs", True))
    result.cleaned["include_interviews"] = bool(args.get("include_interviews", True))

    if raise_on_error:
        result.raise_if_invalid()
    return result


def validate_export_format(fmt: Any) -> Tuple[str, Optional[str]]:
    """Validate and normalize an export format string."""
    if fmt is None:
        return "txt", None
    s = str(fmt).strip().lower().lstrip(".")
    if s not in ALLOWED_EXPORT_FORMATS:
        return "txt", f"Unsupported export format '{s}'; defaulting to 'txt'"
    return s, None


# ──────────────────────────────────────────── output validators

def validate_tool_result(data: dict[str, Any]) -> bool:
    """Check that a tool result dict has the required envelope fields."""
    required = {"status", "data"}
    return required.issubset(data.keys())


def validate_evidence_list(claims: list[dict[str, Any]]) -> list[str]:
    """Check a list of claim-evidence associations for completeness. Returns warning list."""
    warnings = []
    for i, c in enumerate(claims):
        if not c.get("evidence_id"):
            warnings.append(f"Claim at index {i} is missing evidence_id")
        if not c.get("claim_type"):
            warnings.append(f"Claim at index {i} is missing claim_type")
    return warnings
