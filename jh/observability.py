"""Privacy-safe structured event telemetry for JobHunter MCP server.

Records operational events (tool calls, source outcomes, errors, security events)
with sanitized payloads. By design this module NEVER logs:
- Full resume text or candidate contact details
- Complete application screening answers
- Access tokens or API keys
- Full model prompts or tool payloads

It DOES log:
- Correlation IDs and tool names
- Outcome categories and duration
- Source identifiers and result counts
- Retry counts and sanitized error categories
- Prompt versions and validator versions
- Security events (blocked URL, path escape, injection attempts)
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Generator, List, Optional

from .models import ToolOutcome, WarningCategory

log = logging.getLogger("jobhunter.observability")


# ──────────────────────────────────────────── event types

class EventType:
    """Standard event type constants."""
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SOURCE_FETCH = "source_fetch"
    SOURCE_ERROR = "source_error"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    GROUNDING_CHECK = "grounding_check"
    PARSE_RESUME = "parse_resume"
    SECURITY_BLOCKED = "security_blocked"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    RECOVERY = "recovery"
    SCHEMA_MIGRATION = "schema_migration"
    VALIDATION_ERROR = "validation_error"


# ──────────────────────────────────────────── event record

@dataclass
class ObservabilityEvent:
    """A single sanitized telemetry event."""
    event_type: str = ""
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    duration_ms: Optional[float] = None
    tool_name: Optional[str] = None
    source_name: Optional[str] = None
    outcome: Optional[str] = None
    result_count: Optional[int] = None
    retry_count: int = 0
    warning_category: Optional[str] = None
    error_category: Optional[str] = None
    prompt_version: Optional[str] = None
    validator_version: Optional[str] = None
    detail: Optional[str] = None
    # Security events
    blocked_url: Optional[str] = None
    blocked_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


# ──────────────────────────────────────────── event store

class EventStore:
    """In-memory ring buffer of recent telemetry events.

    Events are kept in memory only during the server's lifetime.
    The buffer rotates to prevent unbounded memory growth.
    """

    def __init__(self, max_events: int = 1000) -> None:
        self._events: list[ObservabilityEvent] = []
        self._max = max_events
        self._counters: dict[str, int] = {}

    def record(self, event: ObservabilityEvent) -> None:
        """Record an event and emit it to stderr logging."""
        self._events.append(event)
        if len(self._events) > self._max:
            self._events = self._events[-self._max:]

        # Update counters
        key = f"{event.event_type}:{event.outcome or 'unknown'}"
        self._counters[key] = self._counters.get(key, 0) + 1

        # Emit to stderr
        _emit_log(event)

    def recent(self, limit: int = 50, event_type: Optional[str] = None) -> list[dict[str, Any]]:
        """Return recent events, newest first."""
        filtered = self._events
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        return [e.to_dict() for e in filtered[-limit:][::-1]]

    def counters(self) -> dict[str, int]:
        """Return event type:outcome counters."""
        return dict(self._counters)

    def summary(self) -> dict[str, Any]:
        """Return a compact health summary."""
        total = len(self._events)
        errors = sum(1 for e in self._events if e.outcome == "error")
        security = sum(1 for e in self._events if e.event_type == EventType.SECURITY_BLOCKED)
        return {
            "total_events": total,
            "error_count": errors,
            "security_events": security,
            "counters": self._counters,
        }

    def clear(self) -> None:
        self._events.clear()
        self._counters.clear()


# Module-level singleton
_store: Optional[EventStore] = None


def get_store() -> EventStore:
    """Get or create the global event store."""
    global _store
    if _store is None:
        _store = EventStore()
    return _store


# ──────────────────────────────────────────── convenience recording functions

def record_tool_call(
    tool_name: str,
    correlation_id: str = "",
    outcome: str = "ok",
    duration_ms: float = 0.0,
    result_count: Optional[int] = None,
    detail: Optional[str] = None,
) -> ObservabilityEvent:
    """Record a tool invocation result."""
    event = ObservabilityEvent(
        event_type=EventType.TOOL_RESULT,
        correlation_id=correlation_id or uuid.uuid4().hex[:12],
        tool_name=tool_name,
        outcome=outcome,
        duration_ms=duration_ms,
        result_count=result_count,
        detail=detail,
    )
    get_store().record(event)
    return event


def record_source_fetch(
    source_name: str,
    correlation_id: str = "",
    success: bool = True,
    job_count: int = 0,
    duration_ms: float = 0.0,
    retry_count: int = 0,
    cached: bool = False,
    warning: Optional[str] = None,
) -> ObservabilityEvent:
    """Record a source adapter fetch outcome."""
    event = ObservabilityEvent(
        event_type=EventType.CACHE_HIT if cached else (EventType.SOURCE_FETCH if success else EventType.SOURCE_ERROR),
        correlation_id=correlation_id or uuid.uuid4().hex[:12],
        source_name=source_name,
        outcome="ok" if success else "error",
        result_count=job_count,
        duration_ms=duration_ms,
        retry_count=retry_count,
        warning_category=warning,
    )
    get_store().record(event)
    return event


def record_security_event(
    blocked_url: str = "",
    blocked_reason: str = "",
    detail: str = "",
    correlation_id: str = "",
) -> ObservabilityEvent:
    """Record a security-relevant event (blocked URL, path escape, etc.)."""
    # Redact the URL to avoid logging sensitive paths
    safe_url = _redact_for_log(blocked_url)
    event = ObservabilityEvent(
        event_type=EventType.SECURITY_BLOCKED,
        correlation_id=correlation_id or uuid.uuid4().hex[:12],
        outcome="blocked",
        blocked_url=safe_url,
        blocked_reason=blocked_reason,
        detail=detail,
    )
    get_store().record(event)
    return event


def record_parse_event(
    source_file: str,
    success: bool = True,
    duration_ms: float = 0.0,
    detail: Optional[str] = None,
    correlation_id: str = "",
) -> ObservabilityEvent:
    """Record a resume parsing event."""
    # Only log the filename, not the full path
    safe_file = source_file.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if source_file else ""
    event = ObservabilityEvent(
        event_type=EventType.PARSE_RESUME,
        correlation_id=correlation_id or uuid.uuid4().hex[:12],
        outcome="ok" if success else "error",
        duration_ms=duration_ms,
        detail=f"file={safe_file}" + (f" {detail}" if detail else ""),
    )
    get_store().record(event)
    return event


def record_grounding_check(
    supported: int = 0,
    unsupported: int = 0,
    needs_review: int = 0,
    validator_version: str = "",
    prompt_version: str = "",
    correlation_id: str = "",
) -> ObservabilityEvent:
    """Record a grounding verification result."""
    event = ObservabilityEvent(
        event_type=EventType.GROUNDING_CHECK,
        correlation_id=correlation_id or uuid.uuid4().hex[:12],
        outcome="approved" if unsupported == 0 else "needs_review",
        result_count=supported + unsupported + needs_review,
        validator_version=validator_version,
        prompt_version=prompt_version,
        detail=f"supported={supported} unsupported={unsupported} review={needs_review}",
    )
    get_store().record(event)
    return event


def record_startup(
    workspace: str = "",
    resume_count: int = 0,
    app_count: int = 0,
    source_count: int = 0,
) -> ObservabilityEvent:
    """Record server startup."""
    event = ObservabilityEvent(
        event_type=EventType.STARTUP,
        outcome="ok",
        detail=f"resumes={resume_count} apps={app_count} sources={source_count}",
    )
    get_store().record(event)
    return event


def record_recovery(detail: str, correlation_id: str = "") -> ObservabilityEvent:
    """Record a recovery event (SQLite rebuild, JSON backup restore, etc.)."""
    event = ObservabilityEvent(
        event_type=EventType.RECOVERY,
        correlation_id=correlation_id or uuid.uuid4().hex[:12],
        outcome="recovered",
        detail=detail,
    )
    get_store().record(event)
    return event


def record_validation_error(
    tool_name: str,
    field: str,
    message: str,
    correlation_id: str = "",
) -> ObservabilityEvent:
    """Record a validation error on a tool argument."""
    event = ObservabilityEvent(
        event_type=EventType.VALIDATION_ERROR,
        correlation_id=correlation_id or uuid.uuid4().hex[:12],
        tool_name=tool_name,
        outcome="rejected",
        detail=f"field={field}: {message}",
    )
    get_store().record(event)
    return event


# ──────────────────────────────────────────── timing context manager

@contextmanager
def timed_operation(
    event_type: str,
    tool_name: Optional[str] = None,
    source_name: Optional[str] = None,
    correlation_id: str = "",
) -> Generator[dict[str, Any], None, None]:
    """Context manager that records the duration of an operation.

    Usage:
        with timed_operation(EventType.TOOL_CALL, tool_name="search_jobs") as ctx:
            ... do work ...
            ctx["result_count"] = 42
    """
    ctx: dict[str, Any] = {
        "correlation_id": correlation_id or uuid.uuid4().hex[:12],
        "result_count": None,
        "outcome": "ok",
        "detail": None,
    }
    start = time.monotonic()
    try:
        yield ctx
    except Exception as exc:
        ctx["outcome"] = "error"
        ctx["detail"] = type(exc).__name__
        raise
    finally:
        elapsed = (time.monotonic() - start) * 1000
        event = ObservabilityEvent(
            event_type=event_type,
            correlation_id=ctx["correlation_id"],
            tool_name=tool_name,
            source_name=source_name,
            outcome=ctx["outcome"],
            duration_ms=round(elapsed, 2),
            result_count=ctx.get("result_count"),
            detail=ctx.get("detail"),
        )
        get_store().record(event)


# ──────────────────────────────────────────── internal helpers

def _emit_log(event: ObservabilityEvent) -> None:
    """Emit event to stderr logger at appropriate level."""
    parts = [f"[{event.event_type}]"]
    if event.tool_name:
        parts.append(f"tool={event.tool_name}")
    if event.source_name:
        parts.append(f"source={event.source_name}")
    if event.outcome:
        parts.append(f"outcome={event.outcome}")
    if event.duration_ms is not None:
        parts.append(f"duration={event.duration_ms:.0f}ms")
    if event.result_count is not None:
        parts.append(f"count={event.result_count}")
    if event.detail:
        parts.append(event.detail)

    msg = " ".join(parts)

    if event.event_type == EventType.SECURITY_BLOCKED:
        log.warning(msg)
    elif event.outcome == "error":
        log.error(msg)
    else:
        log.debug(msg)


def _redact_for_log(url: str) -> str:
    """Redact sensitive URL components for safe logging."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.hostname}{parsed.path}"
    except Exception:
        return "<redacted>"
