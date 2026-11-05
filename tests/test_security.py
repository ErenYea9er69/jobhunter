import pytest

from jh import source_policy, util


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin", "http://localhost:8080/", "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/", "http://192.168.1.10/", "http://[::1]/", "ftp://example.com/file", "file:///etc/passwd",
    "http://intranet/", "http://printer.local/", "http://service.internal/",
])
def test_static_policy_blocks_private_and_odd_urls(url):
    ok, reason = source_policy.check_url(url)
    assert not ok and reason


def test_public_url_passes_static_check():
    assert source_policy.check_url("https://boards.greenhouse.io/adyen")[0]


def test_hostname_that_resolves_to_a_private_address_is_blocked(monkeypatch):
    """The old code never resolved DNS, so a public-looking name pointing at 127.0.0.1 got through."""
    monkeypatch.setattr(source_policy.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))])
    source_policy._dns_cache.clear()
    ok, reason = source_policy.resolve_and_check("https://innocent.example.com/jobs")
    assert not ok and "blocked address" in reason


def test_http_get_refuses_private_resolution(monkeypatch):
    monkeypatch.setattr(source_policy.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 0))])
    source_policy._dns_cache.clear()
    with pytest.raises(util.HttpError, match="Security policy"):
        util.http_get("https://rebind.example.com/x")


def test_apply_url_sanitizer_strips_tracking_but_keeps_job_id():
    url, warns = source_policy.sanitize_apply_url("https://boards.greenhouse.io/x/jobs/1?gh_jid=77&utm_source=foo&ref=bar")
    assert "gh_jid=77" in url and "utm_source" not in url and "ref=" not in url and warns


def test_apply_url_to_private_address_is_dropped():
    url, warns = source_policy.sanitize_apply_url("http://127.0.0.1/evil")
    assert url == "" and warns
