import pytest

from jh import company_directory, sources
from jh.sources import ats_boards, feeds


# ------------------------------------------------------------------ ATS adapters (shapes pinned by fixtures)

def test_recruitee_adapter(net):
    net.fixture("acme-tn.recruitee.com/api/offers", "recruitee.json")
    jobs = sources.BOARDS["recruitee"].fetch_company("acme-tn", "Acme TN")
    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "Python Developer" and "Tunis" in j["location"] and j["work_mode"] == "Hybrid"
    assert j["url"].startswith("https://acme-tn.recruitee.com/o/") and j["source"] == "Recruitee"
    assert j["source_kind"] == "Direct employer ATS"


def test_personio_adapter(net):
    net.fixture("nordic.jobs.personio.de/xml", "personio.xml")
    jobs = sources.BOARDS["personio"].fetch_company("nordic", "Nordic")
    assert [j["title"] for j in jobs] == ["Data Engineer"]
    assert jobs[0]["url"] == "https://nordic.jobs.personio.de/job/9001" and "Airflow" in jobs[0]["description"]


def test_teamtailor_adapter(net):
    net.fixture("nordic.teamtailor.com/jobs.rss", "teamtailor.rss")
    jobs = sources.BOARDS["teamtailor"].fetch_company("nordic")
    assert jobs[0]["title"] == "Frontend Developer" and jobs[0]["work_mode"] == "Hybrid"


def test_bamboohr_adapter_and_enrich(net):
    net.fixture("acme.bamboohr.com/careers/list", "bamboohr.json")
    jobs = sources.BOARDS["bamboohr"].fetch_company("acme")
    assert jobs[0]["title"] == "QA Engineer" and "Lisbon" in jobs[0]["location"] and jobs[0]["needs_enrichment"]
    net.add("acme.bamboohr.com/careers/31/detail", '{"result":{"jobOpening":{"description":"<p>Test automation with Selenium and Python.</p>"}}}')
    enriched = sources.BOARDS["bamboohr"].enrich(jobs[0])
    assert "Selenium" in enriched["description"] and enriched["enriched"]


def test_breezy_adapter(net):
    net.fixture("acme.breezy.hr/json", "breezy.json")
    jobs = sources.BOARDS["breezy"].fetch_company("acme")
    assert jobs[0]["title"] == "DevOps Engineer" and "Cairo" in jobs[0]["location"]


def test_lever_eu_uses_eu_host(net):
    net.add("api.eu.lever.co/v0/postings/euco", "[]")
    assert sources.BOARDS["lever eu"].fetch_company("euco") == []
    assert any("api.eu.lever.co" in c for c in net.calls)


def test_greenhouse_unchanged_still_works(net):
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    jobs = sources.BOARDS["greenhouse"].fetch_company("adyen", "Adyen")
    assert len(jobs) == 2 and "PostgreSQL" in jobs[0]["description"]


# ------------------------------------------------------------------ URL router

@pytest.mark.parametrize("url,expected", [
    ("https://boards.greenhouse.io/adyen/jobs/101", ("greenhouse", "adyen")),
    ("https://job-boards.greenhouse.io/monzo", ("greenhouse", "monzo")),
    ("https://boards.greenhouse.io/embed/job_board?for=adyen", ("greenhouse", "adyen")),
    ("https://jobs.lever.co/spotify/abc-123", ("lever", "spotify")),
    ("https://jobs.eu.lever.co/mistral", ("lever eu", "mistral")),
    ("https://jobs.ashbyhq.com/ramp", ("ashby", "ramp")),
    ("https://apply.workable.com/instadeep/j/ABC/", ("workable", "instadeep")),
    ("https://jobs.smartrecruiters.com/Visa/123", ("smartrecruiters", "Visa")),
    ("https://acme-tn.recruitee.com/o/python-developer", ("recruitee", "acme-tn")),
    ("https://nordic.jobs.personio.de/job/9001", ("personio", "nordic")),
    ("https://nordic.teamtailor.com/jobs/1", ("teamtailor", "nordic")),
    ("https://acme.bamboohr.com/careers/31", ("bamboohr", "acme")),
    ("https://acme.breezy.hr/p/abc", ("breezy", "acme")),
])
def test_board_from_url(url, expected):
    assert ats_boards.board_from_url(url) == expected


@pytest.mark.parametrize("url", ["https://www.recruitee.com/pricing", "https://example.com/careers", "https://api.teamtailor.com/v1", ""])
def test_board_from_url_ignores_vendor_marketing_pages(url):
    assert ats_boards.board_from_url(url) is None


def test_boards_in_html_finds_embedded_boards():
    html = (feeds.FIX if hasattr(feeds, "FIX") else None)
    from pathlib import Path
    text = (Path(__file__).parent / "fixtures" / "careerpage_embeds_ats.html").read_text()
    assert ats_boards.boards_in_html(text) == [("greenhouse", "adyen")]


# ------------------------------------------------------------------ generic feeds

def read(name):
    from pathlib import Path
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def test_parse_wp_job_manager_rss():
    items = feeds.parse_feed(read("feed_wpjobmanager.rss"))
    assert len(items) == 2
    assert items[0]["company"] == "Sofrecom Tunisie" and items[0]["location"] == "Sfax, Tunisie"
    assert (items[1]["title"], items[1]["company"]) == ("Backend Developer", "Proxym Group")


def test_parse_atom_and_json_feed():
    atom = feeds.parse_feed(read("feed_atom.xml"))
    assert atom[0]["title"] == "Site Reliability Engineer" and atom[0]["company"] == "Orange"
    assert atom[0]["url"] == "https://careers.example.com/sre-1"
    js = feeds.parse_feed(read("feed.json"))
    assert js[0]["title"] == "Data Analyst" and js[0]["company"] == "Open Data Org"


def test_parse_feed_rejects_xml_with_dtd():
    evil = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "boom">]><rss><channel><item><title>&a;</title><link>http://x.com</link></item></channel></rss>'
    with pytest.raises(Exception):
        feeds.parse_feed(evil)


def test_custom_feed_source_reads_user_feeds(ws, net):
    from jh import preferences
    net.fixture("jobs.example.tn/feed", "feed_wpjobmanager.rss")
    preferences.save({"custom_feeds": [{"name": "Tunisia Jobs", "url": "https://jobs.example.tn/feed/"}]})
    jobs = feeds.CustomFeeds().fetch("backend developer", "")
    assert {j["company"] for j in jobs} == {"Sofrecom Tunisie", "Proxym Group"}
    assert all(j["id"].startswith("feed-") and j["source"] == "Custom Feed" for j in jobs)


def test_custom_feed_all_failing_raises(ws, net):
    from jh import preferences
    preferences.save({"custom_feeds": [{"url": "https://dead.example.org/feed"}]})
    with pytest.raises(RuntimeError):
        feeds.CustomFeeds().fetch("x", "")


# ------------------------------------------------------------------ career pages

def test_jsonld_career_page(ws, net):
    net.fixture("careers.example.com/jobs", "careerpage_jsonld.html")
    from jh import preferences
    preferences.save({"career_pages": [{"name": "InstaDeep", "url": "https://careers.example.com/jobs"}]})
    jobs = feeds.CareerPages().fetch("machine learning", "")
    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "Machine Learning Engineer" and j["company"] == "InstaDeep" and "Tunis" in j["location"]
    assert j["source"] == "Career Page" and j["source_kind"] == "Direct employer ATS" and j["url"] == "https://careers.example.com/ml-engineer"
    assert j["salary"]  # read from the description text


def test_career_page_that_embeds_an_ats_uses_its_api(ws, net):
    net.fixture("careers.example.com/work", "careerpage_embeds_ats.html")
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    from jh import preferences
    preferences.save({"career_pages": [{"url": "https://careers.example.com/work"}]})
    jobs = feeds.CareerPages().fetch("backend", "")
    assert {j["title"] for j in jobs} >= {"Backend Engineer"}
    assert all(j["found_via"] == "career page" for j in jobs)


def test_career_page_given_an_ats_url_skips_html(ws, net):
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    from jh import preferences
    preferences.save({"career_pages": [{"url": "https://boards.greenhouse.io/adyen"}]})
    assert len(feeds.CareerPages().fetch("", "")) == 2


# ------------------------------------------------------------------ public APIs

def test_working_nomads_filters_by_query(net):
    net.fixture("workingnomads.com/api/exposed_jobs", "workingnomads.json")
    jobs = feeds.WorkingNomads().fetch("python developer", "")
    assert [j["title"] for j in jobs] == ["Python Developer"] and jobs[0]["work_mode"] == "Remote"
    assert jobs[0]["id"] == feeds.WorkingNomads().fetch("python developer", "")[0]["id"]  # stable across calls


def test_the_muse(net):
    net.fixture("themuse.com/api/public/jobs", "themuse.json")
    jobs = feeds.TheMuse().fetch("software engineer", "")
    assert jobs[0]["id"] == "muse-4242" and jobs[0]["work_mode"] == "Remote"
    assert "category=Software+Engineering" in net.calls[0]


def test_arbeitsagentur_sends_public_key_and_maps_fields(net):
    net.fixture("rest.arbeitsagentur.de/jobboerse/jobsuche-service/pi/jobs", "arbeitsagentur.json")
    jobs = feeds.Arbeitsagentur().fetch("python", "Leipzig, Germany")
    assert jobs[0]["company"] == "Mittelstand GmbH" and "Leipzig" in jobs[0]["location"]
    assert "wo=Leipzig" in net.calls[0]


# ------------------------------------------------------------------ stable ids

def test_ids_do_not_depend_on_pythons_per_process_hash():
    """Bayt, Himalayas and Naukri used abs(hash(...)), which changes on every start and duplicated saved jobs."""
    import pathlib, subprocess, sys
    root = str(pathlib.Path(__file__).parent.parent)
    code = "from jh.util import stable_id; print(stable_id('https://x.com/a'))"
    outs = []
    for seed in (1, 2, 3):
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root, env={"PYTHONHASHSEED": str(seed), "PATH": ""})
        assert r.returncode == 0, r.stderr
        outs.append(r.stdout.strip())
    assert outs[0] and len(set(outs)) == 1
    # and the builtin really does differ between seeds, so the test can fail
    builtin = {subprocess.run([sys.executable, "-c", "print(hash('https://x.com/a'))"], capture_output=True, text=True, env={"PYTHONHASHSEED": str(s), "PATH": ""}).stdout for s in (1, 2)}
    assert len(builtin) == 2


# ------------------------------------------------------------------ company directory

def test_harvest_learns_boards_from_job_links(ws):
    jobs = [{"company": "Small Co", "source": "Remotive", "url": "https://jobs.lever.co/smallco/123", "description": ""},
            {"company": "Tiny GmbH", "source": "Arbeitnow", "url": "https://example.com/x", "description": "Apply: https://tiny.jobs.personio.de/job/5"},
            {"company": "No ATS", "source": "X", "url": "https://example.com/y", "description": ""}]
    assert company_directory.harvest(jobs) == 2
    assert company_directory.harvest(jobs) == 0  # nothing new the second time
    health = company_directory._health()
    assert ("lever", "smallco") in health and ("personio", "tiny") in health


def test_boards_that_keep_failing_rest_for_a_day(ws):
    for _ in range(company_directory.FAIL_LIMIT):
        company_directory._upsert_health("greenhouse", "adyen", "Adyen", "starter", False)
    chosen = {(e["board"], e["slug"]) for e in company_directory.select_boards(500)}
    assert ("greenhouse", "adyen") not in chosen and ("ashby", "ramp") in chosen


def test_watchlist_always_selected_first(ws, net):
    net.fixture("boards-api.greenhouse.io/v1/boards/tinyco/jobs", "greenhouse_adyen.json")
    res = company_directory.add_company(name="TinyCo", board_type="greenhouse", slug="tinyco")
    assert not res["already_watched"]
    assert company_directory.add_company(name="TinyCo", board_type="greenhouse", slug="tinyco")["already_watched"]
    first = company_directory.select_boards(3)[0]
    assert first["via"] == "watchlist" and first["slug"] == "tinyco"


def test_add_company_by_careers_url(ws):
    res = company_directory.add_company(url="https://acme-tn.recruitee.com/o/python-developer")
    assert (res["board_type"], res["slug"]) == ("recruitee", "acme-tn")


def test_add_company_by_name_detects_board_and_lists_alternatives(ws, net):
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    net.fixture("adyen.recruitee.com/api/offers", "recruitee.json")
    res = company_directory.add_company(name="Adyen")
    assert res["board_type"] == "greenhouse" and res["auto_detected"] and res["alternatives"][0]["board_type"] == "recruitee"


def test_company_boards_source_filters_by_query_but_shows_full_watchlist(ws, net):
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    src = company_directory.make_company_boards_source()
    jobs = src.fetch("backend engineer", "")
    assert [j["title"] for j in jobs if j["company"] == "Adyen"] == ["Backend Engineer"]  # starter list is query-filtered
    company_directory.add_company(name="Adyen", board_type="greenhouse", slug="adyen")
    company_directory._cache.clear()
    jobs = src.fetch("backend engineer", "")
    assert {j["title"] for j in jobs if j["company"] == "Adyen"} == {"Backend Engineer", "Office Manager"}  # watched: everything
    assert company_directory.last_run()["ok"] >= 1
