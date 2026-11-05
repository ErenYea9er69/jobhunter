"""Small-employer reach: site reader, discovery, local-language queries, Jooble, JobTech, Pinpoint."""

import pytest

from jh import localize, regional_boards, source_registry
from jh.sources import local

SITE = "https://jobs.example.tn"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    local.clear_state()
    monkeypatch.setattr(local, "_HOST_GAP_SECONDS", 0)
    yield
    local.clear_state()


@pytest.fixture
def site(net):
    """A small Tunisian job site served from fixtures. More specific routes come first."""
    net.fixture(f"{SITE}/robots.txt", "robots_ok.txt")
    net.fixture(f"{SITE}/sitemap.xml", "sitemap.xml")
    net.fixture("ingenieur-logiciel-python-101", "site_job_1.html")
    net.fixture("comptable-senior-102", "site_job_2.html")
    net.fixture(SITE, "site_home.html")
    return net


# ------------------------------------------------------------------ local-language queries

def test_french_variants_for_tunisia():
    v = localize.variants("software engineer", "TN")
    assert v[0] == "software engineer" and "ingénieur logiciel" in v and len(v) <= 4


def test_no_variants_where_language_has_no_table():
    assert localize.variants("software engineer", "JP") == ["software engineer"]
    assert localize.variants("", "TN") == []


def test_unknown_words_are_left_alone():
    assert localize.variants("quantum whisperer", "FR") == ["quantum whisperer"]


def test_matches_any_uses_the_variants():
    v = localize.variants("software engineer", "TN")
    assert localize.matches_any(v, "Ingénieur logiciel Python")
    assert not localize.matches_any(v, "Chef cuisinier")


# ------------------------------------------------------------------ pure helpers

def test_job_page_detection():
    assert local.looks_like_job_page(f"{SITE}/offres-emploi/ingenieur-logiciel-python-101")
    assert local.looks_like_job_page("https://x.org/jobs/123")
    assert not local.looks_like_job_page("https://x.org/jobs")
    assert not local.looks_like_job_page("https://x.org/offres-emploi")
    assert not local.looks_like_job_page("https://x.org/contact")


def test_links_stay_on_site_and_skip_assets(net):
    html = (__import__("conftest").FIX / "site_home.html").read_text()
    urls = [u for u, _ in local.links_in_html(html, SITE + "/")]
    assert f"{SITE}/offres-emploi/comptable-senior-102" in urls
    assert not any("other.example.org" in u or u.endswith(".png") for u in urls)


def test_feed_links_found_in_head():
    html = (__import__("conftest").FIX / "site_home.html").read_text()
    assert local.feed_links_in_html(html, SITE + "/") == [f"{SITE}/feed/jobs.rss"]


def test_sitemap_and_index_parsing():
    fx = __import__("conftest").FIX
    kids, urls = local.parse_sitemap((fx / "sitemap_index.xml").read_text())
    assert len(kids) == 2 and urls == []
    kids, urls = local.parse_sitemap((fx / "sitemap.xml").read_text())
    assert kids == [] and urls[0][1] == "2026-10-20" and len(urls) == 3


def test_sitemap_job_urls_newest_first_and_job_pages_only(site):
    urls = local.sitemap_job_urls(SITE, "Sitemap: " + SITE + "/sitemap.xml")
    assert urls == [f"{SITE}/offres-emploi/ingenieur-logiciel-python-101", f"{SITE}/offres-emploi/comptable-senior-102"]


# ------------------------------------------------------------------ reading a site

def test_read_site_returns_jobs_from_jobposting_data(site):
    jobs = local.read_site({"name": "Jobs TN", "url": SITE + "/"}, "software engineer", localize.variants("software engineer", "TN"))
    assert {j["title"] for j in jobs} == {"Ingénieur logiciel Python", "Comptable senior"}
    j = next(x for x in jobs if "logiciel" in x["title"])
    assert j["company"] == "Jobs TN" or j["company"] == "Atelier Numérique"
    assert j["source"] == "Regional Boards" and j["url"].endswith("-101") and "Sfax" in j["location"]


def test_matching_pages_are_read_first_when_capped(site):
    jobs = local.read_site({"name": "Jobs TN", "url": SITE + "/"}, "software engineer",
                           localize.variants("software engineer", "TN"), max_pages=1)
    assert [j["title"] for j in jobs] == ["Ingénieur logiciel Python"]


def test_robots_disallow_stops_reading(net):
    net.fixture(f"{SITE}/robots.txt", "robots_block.txt")
    net.fixture(SITE, "site_home.html")
    with pytest.raises(PermissionError):
        local.read_site({"name": "x", "url": SITE + "/"}, "")
    assert not any("offres-emploi" in c for c in net.calls)


def test_unreachable_robots_file_means_allowed(net):
    net.fixture(SITE, "site_home.html")
    assert local.robots_allows(SITE + "/offres-emploi/x-1")


# ------------------------------------------------------------------ sources

def test_regional_boards_source_uses_catalog_and_local_words(site, monkeypatch):
    monkeypatch.setattr(regional_boards, "BOARDS", {"TN": (("Jobs TN", SITE),)})
    jobs = local.RegionalBoards().fetch("software engineer", "Tunisia", country="TN")
    assert any("logiciel" in j["title"].lower() for j in jobs) and all(j["source"] == "Regional Boards" for j in jobs)


def test_regional_boards_does_nothing_without_a_country(net):
    assert local.RegionalBoards().fetch("x", "") == []


def test_regional_boards_raises_when_every_site_fails(net, monkeypatch):
    monkeypatch.setattr(regional_boards, "BOARDS", {"TN": (("Dead", "https://dead.example.tn"),)})
    with pytest.raises(RuntimeError):
        local.RegionalBoards().fetch("x", "", country="TN")


def test_job_sites_source_reads_user_sites(ws, site):
    from jh import preferences
    preferences.save({"job_sites": [{"name": "Mine", "url": SITE + "/"}]})
    src = local.JobSites()
    assert src.configured()
    jobs = src.fetch("comptable", "Tunis")
    assert jobs and all(j["source"] == "Job Sites" for j in jobs)


def test_catalog_boards_are_plain_https_urls():
    for country, rows in regional_boards.BOARDS.items():
        assert len(country) == 2
        assert all(u.startswith("https://") and n for n, u in rows)


def test_plan_runs_regional_boards_for_tunisia_only():
    plan = source_registry.plan("Regional Boards", ["TN", "FR", "MA"], "", True)
    assert [p["kwargs"]["country"] for p in plan] == ["TN", "MA"]
    assert source_registry.plan("Regional Boards", ["FR"], "", True) == []


def test_regional_boards_skipped_for_countries_without_boards():
    state, why, silent = source_registry.skip_reason("Regional Boards", {}, ["JP"], True)
    assert state == "skipped"


def test_jooble_needs_a_key_and_parses(monkeypatch, ws):
    from jh import config
    monkeypatch.setattr(config, "JOOBLE_API_KEY", "")
    assert not local.Jooble().available()
    monkeypatch.setattr(config, "JOOBLE_API_KEY", "k")
    assert local.Jooble().available()
    rows = local.Jooble.parse(__import__("json").loads((__import__("conftest").FIX / "jooble.json").read_text()))
    assert len(rows) == 1 and rows[0]["company"] == "Digital Souk" and rows[0]["url"].startswith("https://")


def test_jooble_fetch_posts_and_builds_jobs(ws, net, monkeypatch):
    from jh import config
    monkeypatch.setattr(config, "JOOBLE_API_KEY", "secret")
    net.fixture("jooble.org/api/secret", "jooble.json")
    jobs = local.Jooble().fetch("python", "Tunis", country="TN")
    assert [j["title"] for j in jobs] == ["Développeur Python"] and jobs[0]["source"] == "Jooble"


def test_jobtech_parse_and_fetch(net):
    net.fixture("jobsearch.api.jobtechdev.se/search", "jobtech.json")
    jobs = local.JobTech().fetch("python", "Stockholm")
    assert len(jobs) == 1 and jobs[0]["company"] == "Nordic Pay AB" and "Stockholm" in jobs[0]["location"]


def test_pinpoint_board_parses_and_routes(net):
    from jh.sources import BOARDS
    from jh.sources.ats_boards import board_from_url
    assert board_from_url("https://acme.pinpointhq.com/postings/77") == ("pinpoint", "acme")
    net.fixture("acme.pinpointhq.com/postings.json", "pinpoint.json")
    jobs = BOARDS["pinpoint"].fetch_company("acme", "Acme")
    assert len(jobs) == 1 and jobs[0]["work_mode"] == "Hybrid" and "EUR" in jobs[0]["salary"] and "Lisbon" in jobs[0]["location"]


# ------------------------------------------------------------------ discovery and the tools

def test_discover_site_recommends_adding_as_site(site):
    net_feed_missing = local.discover_site(SITE + "/")
    assert net_feed_missing["job_pages_found"] == 2 and net_feed_missing["sitemap_job_urls"] == 2
    assert "kind='site'" in net_feed_missing["recommendation"]
    assert net_feed_missing["feeds"] == [{"url": f"{SITE}/feed/jobs.rss", "jobs": 0}]


def test_discover_site_respects_robots(net):
    net.fixture(f"{SITE}/robots.txt", "robots_block.txt")
    res = local.discover_site(SITE + "/")
    assert res["robots_allows"] is False and "Do not add" in res["recommendation"]


def test_add_site_tool_tests_before_saving(tools, site):
    res = tools.call("add_job_source", kind="site", value=SITE + "/", name="Jobs TN")
    assert res["success"] and res["data"]["jobs_found_in_test"] == 2
    listing = tools.call("list_job_sources")
    assert listing["data"]["job_sites"][0]["url"] == SITE + "/"
    assert tools.call("remove_job_source", kind="site", value="Jobs TN")["data"]["removed"] is True


def test_add_site_refuses_when_robots_say_no_even_with_force(tools, net):
    net.fixture(f"{SITE}/robots.txt", "robots_block.txt")
    net.fixture(SITE, "site_home.html")
    res = tools.call("add_job_source", kind="site", value=SITE + "/", force=True)
    assert res["status"] == "error" and res["error"]["code"] == "forbidden"


def test_discover_job_source_tool(tools, site):
    res = tools.call("discover_job_source", url=SITE + "/")
    assert res["success"] and res["data"]["job_pages_found"] == 2
    assert tools.call("discover_job_source", url="ftp://x")["error"]["code"] == "invalid_input"


def test_search_from_tunisia_reaches_the_regional_board(tools, site, monkeypatch):
    monkeypatch.setattr(regional_boards, "BOARDS", {"TN": (("Jobs TN", SITE),)})
    tools.call("set_preferences", updates={"target_countries": ["Tunisia"], "work_mode": "Onsite", "max_age_days": 0})
    res = tools.call("search_jobs", query="software engineer", limit=20, refresh=True)
    assert res["success"], res
    states = {s["source"].split("@")[0]: s for s in res["data"]["sources"]}
    assert states["Regional Boards"]["state"] == "ok" and states["Regional Boards"]["count"] >= 1
    titles = [j["title"] for j in res["data"]["jobs"]]
    assert "Ingénieur logiciel Python" in titles
