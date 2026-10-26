"""Tests for the 6 new blueprint v2.1 modules:
- jh/models.py
- jh/schemas.py
- jh/evidence.py
- jh/source_registry.py
- jh/source_policy.py
- jh/observability.py
"""

import os
import sys
import json
import tempfile
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════
# 1. MODELS TESTS
# ═══════════════════════════════════════════════════════════════

class TestModels:

    def test_claim_type_enum_values(self):
        from jh.models import ClaimType
        assert ClaimType.SKILL.value == "skill"
        assert ClaimType.EMPLOYMENT.value == "employment"
        assert ClaimType.CERTIFICATION.value == "certification"

    def test_extraction_status_enum(self):
        from jh.models import ExtractionStatus
        assert ExtractionStatus.VERIFIED.value == "verified"
        assert ExtractionStatus.NEEDS_REVIEW.value == "needs_review"
        assert ExtractionStatus.UNPARSED.value == "unparsed"

    def test_grounding_verdict_enum(self):
        from jh.models import GroundingVerdict
        assert GroundingVerdict.SUPPORTED.value == "supported"
        assert GroundingVerdict.UNSUPPORTED.value == "unsupported"

    def test_application_stage_enum(self):
        from jh.models import ApplicationStage
        assert ApplicationStage.APPLIED.value == "applied"
        assert ApplicationStage.REJECTED.value == "rejected"
        # Verify all stages exist
        assert len(ApplicationStage) >= 10

    def test_evidence_claim_creation(self):
        from jh.models import EvidenceClaim, ClaimType, ExtractionStatus
        claim = EvidenceClaim(
            claim_type=ClaimType.SKILL,
            canonical_value="Python",
            raw_value="Python 3.11",
            source_file="resume.pdf",
        )
        assert claim.evidence_id.startswith("ev_")
        assert claim.claim_type == ClaimType.SKILL
        assert claim.canonical_value == "Python"
        assert claim.candidate_confirmed is False

    def test_evidence_claim_to_dict(self):
        from jh.models import EvidenceClaim, ClaimType
        claim = EvidenceClaim(claim_type=ClaimType.METRIC, canonical_value="95%")
        d = claim.to_dict()
        assert d["claim_type"] == "metric"
        assert d["canonical_value"] == "95%"
        assert "evidence_id" in d

    def test_tool_result_envelope(self):
        from jh.models import ToolResult, ToolOutcome, WarningCategory
        result = ToolResult(status=ToolOutcome.OK, data={"count": 5})
        assert result.status == ToolOutcome.OK
        d = result.to_dict()
        assert d["status"] == "ok"
        assert d["data"]["count"] == 5

    def test_tool_result_add_warning(self):
        from jh.models import ToolResult, ToolOutcome, WarningCategory
        result = ToolResult()
        assert result.status == ToolOutcome.OK
        result.add_warning(WarningCategory.TIMEOUT, "Source X timed out")
        assert result.status == ToolOutcome.PARTIAL
        assert len(result.warnings) == 1

    def test_normalized_job_defaults(self):
        from jh.models import NormalizedJob, WorkMode
        job = NormalizedJob(title="Engineer", company="ACME")
        assert job.work_mode == WorkMode.UNKNOWN
        d = job.to_dict()
        assert d["work_mode"] == "unknown"

    def test_score_breakdown(self):
        from jh.models import ScoreBreakdown
        score = ScoreBreakdown(
            total=78.5, skill_match=32.0, title_domain=20.0,
            seniority_experience=16.5, work_mode_compensation=10.0,
        )
        d = score.to_dict()
        assert d["total"] == 78.5
        assert d["scoring_version"] == "1.0"

    def test_unique_ids(self):
        from jh.models import _new_id
        ids = {_new_id("test_") for _ in range(100)}
        assert len(ids) == 100  # All unique


# ═══════════════════════════════════════════════════════════════
# 2. SCHEMAS TESTS
# ═══════════════════════════════════════════════════════════════

class TestSchemas:

    def test_validate_string_required(self):
        from jh.schemas import validate_string
        val, err = validate_string(None, "query", required=True)
        assert err is not None
        assert "required" in err.lower()

    def test_validate_string_truncation(self):
        from jh.schemas import validate_string
        long_str = "x" * 600
        val, err = validate_string(long_str, "query", max_length=500)
        assert len(val) == 500
        assert "truncated" in err.lower()

    def test_validate_string_success(self):
        from jh.schemas import validate_string
        val, err = validate_string("  hello  ", "field")
        assert val == "hello"
        assert err is None

    def test_validate_int_bounds(self):
        from jh.schemas import validate_int
        val, err = validate_int(-5, "limit", min_val=1, max_val=100)
        assert val == 1
        assert err is not None

        val, err = validate_int(999, "limit", min_val=1, max_val=100)
        assert val == 100

    def test_validate_int_non_numeric(self):
        from jh.schemas import validate_int
        val, err = validate_int("abc", "limit", default=50)
        assert val == 50
        assert err is not None

    def test_validate_enum_valid(self):
        from jh.schemas import validate_enum
        from jh.models import WorkMode
        val, err = validate_enum("remote", "work_mode", WorkMode)
        assert val == WorkMode.REMOTE
        assert err is None

    def test_validate_enum_invalid(self):
        from jh.schemas import validate_enum
        from jh.models import WorkMode
        val, err = validate_enum("teleport", "work_mode", WorkMode, default=None)
        assert val is None
        assert err is not None
        assert "must be one of" in err.lower()

    def test_validate_search_input_valid(self):
        from jh.schemas import validate_search_input
        result = validate_search_input({"query": "Python Engineer", "location": "NYC", "limit": 20})
        assert result.valid
        assert result.cleaned["query"] == "Python Engineer"
        assert result.cleaned["limit"] == 20

    def test_validate_search_input_missing_query(self):
        from jh.schemas import validate_search_input
        result = validate_search_input({})
        assert not result.valid
        assert "query" in result.error_dict()

    def test_validate_search_salary_swap(self):
        from jh.schemas import validate_search_input
        result = validate_search_input({"query": "Dev", "salary_min": 200000, "salary_max": 100000})
        assert result.cleaned["salary_min"] <= result.cleaned["salary_max"]

    def test_validate_date_range(self):
        from jh.schemas import validate_date_range
        s, e, err = validate_date_range("2025-01-01", "2024-01-01")
        assert err is not None  # start after end

    def test_validate_path_safe(self):
        from jh.schemas import validate_path_safe
        _, err = validate_path_safe("../../../etc/passwd", "path")
        assert err is not None

    def test_validate_export_format(self):
        from jh.schemas import validate_export_format
        fmt, err = validate_export_format("TXT")
        assert fmt == "txt"
        assert err is None
        fmt, err = validate_export_format("xlsx")
        assert fmt == "txt"
        assert err is not None

    def test_validation_result_raise(self):
        from jh.schemas import ValidationResult, ValidationError
        result = ValidationResult()
        result.add_error("field", "bad value")
        try:
            result.raise_if_invalid()
            assert False, "Should have raised"
        except ValidationError as e:
            assert e.field == "field"


# ═══════════════════════════════════════════════════════════════
# 3. EVIDENCE TESTS
# ═══════════════════════════════════════════════════════════════

class TestEvidence:

    def _sample_profile(self):
        return {
            "skills": ["Python", "PostgreSQL", "Docker", "AWS"],
            "summary": "Senior backend engineer with 8 years of experience",
            "target_title": "Senior Python Engineer",
            "experience": [
                {
                    "role": "Senior Engineer",
                    "company": "ACME Corp",
                    "start": "2020-01",
                    "end": "2024-06",
                    "bullets": [
                        "Reduced API latency by 40% through query optimization",
                        "Led team of 5 engineers to deliver microservices platform",
                    ],
                },
                {
                    "role": "Backend Developer",
                    "company": "StartupXYZ",
                    "start": "2017-03",
                    "end": "2020-01",
                    "bullets": ["Built REST API serving 10M requests/day"],
                },
            ],
            "education": [
                {"degree": "BSc Computer Science", "institution": "MIT"},
            ],
            "certifications": ["AWS Solutions Architect"],
            "years_of_experience": 7,
        }

    def test_build_ledger_from_profile(self):
        from jh.evidence import build_ledger_from_profile
        profile = self._sample_profile()
        ledger = build_ledger_from_profile(profile, source_file="resume.pdf")
        assert len(ledger) > 0
        # Should have skill claims
        from jh.models import ClaimType
        skills = ledger.by_type(ClaimType.SKILL)
        assert len(skills) == 4  # Python, PostgreSQL, Docker, AWS

    def test_ledger_employment_claims(self):
        from jh.evidence import build_ledger_from_profile
        from jh.models import ClaimType
        profile = self._sample_profile()
        ledger = build_ledger_from_profile(profile)
        employment = ledger.by_type(ClaimType.EMPLOYMENT)
        assert len(employment) == 2

    def test_ledger_metric_extraction(self):
        from jh.evidence import build_ledger_from_profile
        from jh.models import ClaimType
        profile = self._sample_profile()
        ledger = build_ledger_from_profile(profile)
        metrics = ledger.by_type(ClaimType.METRIC)
        # Should extract "40" from "40%", "10" is structural so skipped
        # At least 1 metric claim from the bullet text
        assert len(metrics) >= 1

    def test_ledger_summary(self):
        from jh.evidence import build_ledger_from_profile
        profile = self._sample_profile()
        ledger = build_ledger_from_profile(profile)
        summary = ledger.summary()
        assert "total_claims" in summary
        assert summary["total_claims"] > 0
        assert "by_type" in summary

    def test_ledger_needs_review(self):
        from jh.evidence import build_ledger_from_profile
        profile = self._sample_profile()
        ledger = build_ledger_from_profile(profile)
        review = ledger.needs_review()
        # Certifications default to needs_review
        assert any(c.canonical_value == "AWS Solutions Architect" for c in review)

    def test_grounding_supported_text(self):
        from jh.evidence import build_ledger_from_profile, verify_grounding
        profile = self._sample_profile()
        ledger = build_ledger_from_profile(profile)
        text = "Experienced Python and PostgreSQL developer at ACME Corp."
        result = verify_grounding(text, ledger, profile)
        assert result.unsupported_count == 0

    def test_grounding_unsupported_number(self):
        from jh.evidence import build_ledger_from_profile, verify_grounding
        profile = self._sample_profile()
        ledger = build_ledger_from_profile(profile)
        text = "Achieved 99.99% uptime across 500 servers"
        result = verify_grounding(text, ledger, profile)
        # 99.99 and 500 are not in the profile
        assert result.unsupported_count > 0

    def test_grounding_honest_gaps(self):
        from jh.evidence import build_ledger_from_profile, verify_grounding
        profile = self._sample_profile()
        ledger = build_ledger_from_profile(profile)
        reqs = ["5+ years Kubernetes experience", "Expert in Rust"]
        result = verify_grounding("Python developer", ledger, profile, job_requirements=reqs)
        # "Kubernetes" and "Rust" not in profile skills
        assert len(result.honest_gaps) >= 1

    def test_audit_manifest(self):
        from jh.evidence import build_ledger_from_profile, verify_grounding, create_audit_manifest
        profile = self._sample_profile()
        ledger = build_ledger_from_profile(profile)
        result = verify_grounding("Python developer at ACME Corp", ledger, profile)
        manifest = create_audit_manifest(result, "prof_1", "job_1")
        assert manifest["manifest_id"].startswith("mfst_")
        assert manifest["validator_version"] == "1.0"

    def test_file_hash(self):
        from jh.evidence import file_hash
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            f.flush()
            path = f.name
        try:
            h = file_hash(path)
            assert len(h) == 64  # SHA-256 hex digest
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════
# 4. SOURCE REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════

class TestSourceRegistry:

    def test_registry_has_defaults(self):
        from jh.source_registry import SourceRegistry
        registry = SourceRegistry()
        assert len(registry.all()) > 10
        assert registry.get("Greenhouse") is not None
        assert registry.get("LinkedIn") is not None

    def test_registry_greenhouse_is_public_api(self):
        from jh.source_registry import SourceRegistry
        from jh.models import SourceAccessMethod
        registry = SourceRegistry()
        gh = registry.get("Greenhouse")
        assert gh.access_method == SourceAccessMethod.PUBLIC_API

    def test_registry_matching_capabilities(self):
        from jh.source_registry import SourceRegistry
        registry = SourceRegistry()
        remote_sources = registry.matching(supports_remote=True)
        assert len(remote_sources) > 0
        for src in remote_sources:
            assert src.capabilities.supports_remote

    def test_registry_health_summary(self):
        from jh.source_registry import SourceRegistry
        registry = SourceRegistry()
        summary = registry.health_summary()
        assert "total_sources" in summary
        assert "enabled_count" in summary
        assert summary["total_sources"] > 0

    def test_registry_names(self):
        from jh.source_registry import SourceRegistry
        registry = SourceRegistry()
        names = registry.names()
        assert "Greenhouse" in names
        assert "Lever" in names
        assert "LinkedIn" in names

    def test_registry_singleton(self):
        from jh.source_registry import get_registry
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_source_descriptor_to_dict(self):
        from jh.source_registry import SourceRegistry
        registry = SourceRegistry()
        gh = registry.get("Greenhouse")
        d = gh.to_dict()
        assert d["name"] == "Greenhouse"
        assert d["access_method"] == "public_api"

    def test_adzuna_requires_api_key(self):
        from jh.source_registry import SourceRegistry
        registry = SourceRegistry()
        adzuna = registry.get("Adzuna")
        assert adzuna.requires_api_key is True
        assert adzuna.api_key_env_var == "ADZUNA_APP_KEY"


# ═══════════════════════════════════════════════════════════════
# 5. SOURCE POLICY TESTS
# ═══════════════════════════════════════════════════════════════

class TestSourcePolicy:

    def test_allowed_greenhouse_url(self):
        from jh.source_policy import check_url
        allowed, reason = check_url("https://boards-api.greenhouse.io/v1/boards/test/jobs")
        assert allowed is True

    def test_blocked_private_ip(self):
        from jh.source_policy import check_url
        allowed, reason = check_url("http://192.168.1.1/admin")
        assert allowed is False
        assert "blocked" in reason.lower()

    def test_blocked_loopback(self):
        from jh.source_policy import check_url
        allowed, reason = check_url("http://127.0.0.1:8080/api")
        assert allowed is False

    def test_blocked_unknown_domain(self):
        from jh.source_policy import check_url
        allowed, reason = check_url("https://evil-site.example.com/jobs")
        assert allowed is False
        assert "not in the approved" in reason.lower()

    def test_blocked_ftp_scheme(self):
        from jh.source_policy import check_url
        allowed, reason = check_url("ftp://files.example.com/resume.pdf")
        assert allowed is False
        assert "scheme" in reason.lower()

    def test_empty_url(self):
        from jh.source_policy import check_url
        allowed, reason = check_url("")
        assert allowed is False

    def test_allowed_subdomain(self):
        from jh.source_policy import check_url
        # Subdomains of allowed domains should pass
        allowed, _ = check_url("https://api.greenhouse.io/test")
        assert allowed is True

    def test_employer_career_pattern(self):
        from jh.source_policy import check_url
        allowed, _ = check_url("https://careers.google.com/jobs/123")
        assert allowed is True
        allowed, _ = check_url("https://jobs.microsoft.com/en-us")
        assert allowed is True

    def test_sanitize_apply_url(self):
        from jh.source_policy import sanitize_apply_url
        cleaned, warnings = sanitize_apply_url(
            "https://www.linkedin.com/jobs/view/123?utm_source=google&trk=abc&refId=xyz"
        )
        assert "utm_source" not in cleaned
        assert "trk" not in cleaned
        assert len(warnings) > 0

    def test_add_and_remove_domain(self):
        from jh.source_policy import add_allowed_domain, remove_allowed_domain, check_url
        add_allowed_domain("custom-board.example.com")
        allowed, _ = check_url("https://custom-board.example.com/jobs")
        assert allowed is True
        remove_allowed_domain("custom-board.example.com")
        allowed, _ = check_url("https://custom-board.example.com/jobs")
        assert allowed is False

    def test_redirect_depth_limit(self):
        from jh.source_policy import check_redirect
        allowed, reason = check_redirect(
            "https://www.linkedin.com/jobs",
            "https://www.linkedin.com/login",
            depth=10,
        )
        assert allowed is False
        assert "deep" in reason.lower()

    def test_policy_violation_exception(self):
        from jh.source_policy import PolicyViolation
        try:
            raise PolicyViolation("http://evil.com", "blocked domain")
        except PolicyViolation as e:
            assert "blocked domain" in str(e)


# ═══════════════════════════════════════════════════════════════
# 6. OBSERVABILITY TESTS
# ═══════════════════════════════════════════════════════════════

class TestObservability:

    def test_record_tool_call(self):
        from jh.observability import record_tool_call, get_store
        store = get_store()
        store.clear()
        event = record_tool_call("search_jobs", outcome="ok", duration_ms=120.5, result_count=42)
        assert event.tool_name == "search_jobs"
        assert event.outcome == "ok"
        assert event.duration_ms == 120.5

    def test_event_store_ring_buffer(self):
        from jh.observability import EventStore, ObservabilityEvent
        store = EventStore(max_events=5)
        for i in range(10):
            store.record(ObservabilityEvent(event_type="test", detail=str(i)))
        assert len(store.recent(limit=100)) == 5

    def test_record_source_fetch(self):
        from jh.observability import record_source_fetch, get_store
        store = get_store()
        store.clear()
        event = record_source_fetch("LinkedIn", success=True, job_count=25, duration_ms=800.0)
        assert event.source_name == "LinkedIn"
        assert event.result_count == 25

    def test_record_security_event(self):
        from jh.observability import record_security_event, get_store, EventType
        store = get_store()
        store.clear()
        event = record_security_event(
            blocked_url="http://127.0.0.1/admin",
            blocked_reason="Loopback address blocked",
        )
        assert event.event_type == EventType.SECURITY_BLOCKED
        assert event.outcome == "blocked"

    def test_record_grounding_check(self):
        from jh.observability import record_grounding_check, get_store
        store = get_store()
        store.clear()
        event = record_grounding_check(supported=10, unsupported=2, needs_review=1)
        assert event.outcome == "needs_review"

    def test_timed_operation(self):
        from jh.observability import timed_operation, get_store, EventType
        store = get_store()
        store.clear()
        with timed_operation(EventType.TOOL_CALL, tool_name="test_tool") as ctx:
            time.sleep(0.01)
            ctx["result_count"] = 5
        events = store.recent(limit=1)
        assert len(events) == 1
        assert events[0]["tool_name"] == "test_tool"
        assert events[0]["duration_ms"] > 0

    def test_store_summary(self):
        from jh.observability import get_store, record_tool_call
        store = get_store()
        store.clear()
        record_tool_call("tool_a", outcome="ok")
        record_tool_call("tool_b", outcome="error")
        summary = store.summary()
        assert summary["total_events"] == 2
        assert summary["error_count"] == 1

    def test_record_startup(self):
        from jh.observability import record_startup, get_store
        store = get_store()
        store.clear()
        event = record_startup(resume_count=3, app_count=5, source_count=15)
        assert event.event_type == "startup"
        assert "resumes=3" in event.detail

    def test_record_parse_event(self):
        from jh.observability import record_parse_event
        event = record_parse_event("resume.pdf", success=True, duration_ms=50.0)
        assert "resume.pdf" in (event.detail or "")

    def test_event_counters(self):
        from jh.observability import EventStore, ObservabilityEvent
        store = EventStore()
        store.record(ObservabilityEvent(event_type="tool_call", outcome="ok"))
        store.record(ObservabilityEvent(event_type="tool_call", outcome="ok"))
        store.record(ObservabilityEvent(event_type="tool_call", outcome="error"))
        counters = store.counters()
        assert counters["tool_call:ok"] == 2
        assert counters["tool_call:error"] == 1


# ═══════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════

def run_tests():
    """Run all test classes and report results."""
    test_classes = [
        TestModels,
        TestSchemas,
        TestEvidence,
        TestSourceRegistry,
        TestSourcePolicy,
        TestObservability,
    ]

    total = 0
    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        print(f"\n{'-' * 60}")
        print(f"  {cls.__name__} ({len(methods)} tests)")
        print(f"{'-' * 60}")

        for method_name in sorted(methods):
            total += 1
            try:
                getattr(instance, method_name)()
                passed += 1
                print(f"  OK {method_name}")
            except Exception as e:
                failed += 1
                errors.append((cls.__name__, method_name, str(e)))
                print(f"  FAIL {method_name}: {e}")

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 60}")

    if errors:
        print("\nFailed tests:")
        for cls_name, method, err in errors:
            print(f"  {cls_name}.{method}: {err}")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
