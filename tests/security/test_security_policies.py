"""Security tests verifying SSRF prevention, path traversal rejection, and URL sanitization.

Validates Section 13 & 14 security controls.
"""
import pytest
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from jh.filestore import FileStore
from jh.mcp_tools import register_tools_and_resources
from jh.source_policy import (
    check_url,
    check_url_strict,
    PolicyViolation,
    sanitize_apply_url,
    _redact_url,
)


def test_ssrf_prevention_private_and_loopback_ips():
    """Verify loopback, private ranges, and cloud metadata IPs are blocked."""
    forbidden_urls = [
        "http://127.0.0.1/metrics",
        "http://127.0.0.1:8000/api",
        "http://10.0.0.1/internal",
        "http://172.16.0.1/admin",
        "http://192.168.1.1/setup",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0:5000/",
    ]

    for url in forbidden_urls:
        allowed, reason = check_url(url)
        assert not allowed, f"Expected {url} to be blocked by SSRF policy, but was allowed"
        assert reason is not None

        with pytest.raises(PolicyViolation):
            check_url_strict(url)


def test_ssrf_scheme_validation():
    """Verify non-HTTP(S) schemes are blocked."""
    non_http_urls = [
        "file:///etc/passwd",
        "file:///C:/Windows/win.ini",
        "ftp://example.com/resumes",
        "gopher://evil.com/",
        "javascript:alert(1)",
    ]

    for url in non_http_urls:
        allowed, reason = check_url(url)
        assert not allowed, f"Scheme in {url} must not be allowed"
        assert "scheme" in reason.lower() or "blocked" in reason.lower()


def test_path_traversal_protection(tmp_path):
    """Verify parse_resume_file rejects paths escaping the workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    jh_dir = ws / ".jobhunter"
    jh_dir.mkdir()
    fs = FileStore(jh_dir)

    server = FastMCP(name="JobHunterSecurityTest")
    register_tools_and_resources(server, fs, ws)

    parse_fn = server._tool_manager._tools["parse_resume_file"].fn

    # Create a secret file completely outside the workspace
    outside_dir = tmp_path / "secret_system"
    outside_dir.mkdir()
    secret_file = outside_dir / "passwords.txt"
    secret_file.write_text("root:secret", encoding="utf-8")

    # Attempt path traversal via relative escape
    res_rel = parse_fn(path="../../secret_system/passwords.txt")
    assert not res_rel.get("success"), "Relative traversal outside workspace must fail"
    assert "escapes workspace" in res_rel.get("error", "").lower() or "access denied" in res_rel.get("error", "").lower()

    # Attempt path traversal via absolute path outside workspace
    res_abs = parse_fn(path=str(secret_file.resolve()))
    assert not res_abs.get("success"), "Absolute path outside workspace must fail"
    assert "escapes workspace" in res_abs.get("error", "").lower() or "access denied" in res_abs.get("error", "").lower()


def test_sanitize_apply_url_removes_trackers():
    """Verify tracking parameters are scrubbed while preserving valid destination."""
    dirty_url = "https://boards.greenhouse.io/company/jobs/12345?utm_source=linkedin&utm_medium=cpc&utm_campaign=hiring&ref=tracker123&keep_this=true"
    clean_url, warnings = sanitize_apply_url(dirty_url)

    assert "utm_source" not in clean_url
    assert "utm_medium" not in clean_url
    assert "utm_campaign" not in clean_url
    assert "ref" not in clean_url
    assert "keep_this=true" in clean_url
    assert len(warnings) > 0


def test_redact_url_protects_query_secrets():
    """Verify query strings with tokens or secrets are redacted for safe logging."""
    sensitive_url = "https://api.adzuna.com/v1/api/jobs/gb/search/1?app_id=myid&app_key=supersecret123"
    redacted = _redact_url(sensitive_url)

    assert "supersecret123" not in redacted
    assert "api.adzuna.com" in redacted
