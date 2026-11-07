"""Hermetic test setup: no real network, no DNS, a fresh workspace and database for every test."""

import pathlib
import sys
import urllib.request

import pytest

# Hard guarantee that no test reaches the internet, including LinkedIn's warm-up thread that starts
# when the sources package is imported. Real network access fails loudly instead of leaking.
def _blocked(*args, **kwargs):
    raise OSError("network access is disabled in tests")


urllib.request.OpenerDirector.open = _blocked
try:
    from curl_cffi import requests as _curl

    _curl.Session.get = _blocked
    _curl.Session.request = _blocked
except Exception:  # curl_cffi missing is fine
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

SAMPLE_RESUME = """Ahmed Ben Salah
ahmed@example.com | +216 20 000 000 | Tunis, Tunisia
linkedin.com/in/ahmed-bensalah | github.com/ahmedbs

Backend Engineer

SUMMARY
Backend engineer with 4 years of experience building REST APIs and data pipelines in Python and Node.js.

SKILLS
Python, FastAPI, Django, PostgreSQL, Redis, Docker, AWS, Git, REST APIs, Node.js, TypeScript, CI/CD

EXPERIENCE
Software Engineer, Vermeg, Tunis, Tunisia
Jan 2022 - Present
- Built a payments reconciliation service in Python and FastAPI processing 2 million transactions per day.
- Reduced PostgreSQL query latency by 45% by redesigning indexes and caching hot paths in Redis.
- Containerized 6 services with Docker and automated deployment with GitHub Actions.

Junior Developer, Sofrecom, Tunis, Tunisia
Jun 2020 - Dec 2021
- Developed Django REST endpoints used by 3 internal teams.
- Wrote unit tests that raised coverage from 40% to 82%.

EDUCATION
Bachelor of Engineering in Computer Science, ENIT, 2020
"""


class FakeNet:
    """Serves fixture bodies for URLs that contain a route string. Every other URL fails like an offline host."""

    def __init__(self):
        self.routes: list[tuple[str, bytes, str | None]] = []
        self.calls: list[str] = []

    def add(self, fragment: str, body, charset=None):
        if isinstance(body, pathlib.Path):
            body = body.read_bytes()
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.routes.append((fragment, body, charset))
        return self

    def fixture(self, fragment: str, name: str, charset=None):
        return self.add(fragment, FIX / name, charset)

    def fetch(self, url, headers=None, timeout=None, retries=1, max_bytes=6_000_000, data=None, method=None, allow_private=False):
        from jh.util import HttpError
        self.calls.append(url)
        for fragment, body, charset in self.routes:
            if fragment in url:
                return body, charset
        raise HttpError(f"offline in tests: {url}")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A workspace with one resume and a fresh engine database."""
    from jh import company_directory, config, db, preferences, sources
    (tmp_path / "resumes").mkdir()
    (tmp_path / "resumes" / "ahmed_backend.txt").write_text(SAMPLE_RESUME, encoding="utf-8")
    test_jh_dir = tmp_path / ".jobhunter"
    test_jh_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("JH_DATA_DIR", str(test_jh_dir))
    config.configure_mcp_environment(str(tmp_path))
    db.init_db()
    preferences._cache.update(mtime=None, path=None, data=None)
    company_directory._cache.clear()
    sources.reset_breakers()
    return tmp_path


@pytest.fixture
def net(monkeypatch):
    """Replace the HTTP layer and the TLS fetcher so nothing leaves the machine."""
    from jh import source_policy, sources, util
    fake = FakeNet()
    monkeypatch.setattr(util, "_http_fetch", fake.fetch)

    def no_tls(url, *a, **k):
        fake.calls.append(url)
        raise util.HttpError(f"offline in tests: {url}")

    monkeypatch.setattr(sources, "_fetch_html_tls", no_tls)

    def no_dns(*a, **k):
        raise OSError("DNS disabled in tests")

    monkeypatch.setattr(source_policy.socket, "getaddrinfo", no_dns)
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)   # retry back-offs would only slow the tests

    def linkedin_page(self, url, timeout=6):        # LinkedIn fetches pages through its own method
        fake.calls.append(url)
        return ""

    monkeypatch.setattr(sources.LinkedInGuest, "_get_page", linkedin_page)
    return fake


@pytest.fixture
def server(ws, net):
    """An in-process MCP server on the test workspace."""
    import mcp_server
    return mcp_server.create_server(str(ws))


class ToolClient:
    def __init__(self, server):
        self.server = server

    def call(self, _tool, **args):
        import asyncio
        import json
        out = asyncio.run(self.server.call_tool(_tool, args))
        blocks = out[0] if isinstance(out, tuple) else out
        return json.loads(blocks[0].text)


@pytest.fixture
def tools(server):
    return ToolClient(server)
