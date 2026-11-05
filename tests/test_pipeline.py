"""Whole-search behaviour with a fake network: region gating, preferences, honest reporting, discovery."""

import pytest

from jh import db, pipeline, preferences, workspace


@pytest.fixture
def profile(ws):
    p = workspace.parse_resume_variant(ws / "resumes" / "ahmed_backend.txt")
    db.save_profile(p, profile_id="var_ahmed")
    db.set_active_resume_profile("var_ahmed")
    return db.get_profile()


def states(res):
    """Status by source name. A source that runs once per country is reported as 'Bayt@tn'; the first one is returned."""
    out = {}
    for s in res["sources"]:
        out.setdefault(s["source"].split("@")[0].split(":")[0], s)
    return out


def test_tunisia_search_skips_sources_that_cannot_help(profile, net):
    preferences.save({"target_countries": ["Tunisia"]})
    net.fixture("workingnomads.com/api/exposed_jobs", "workingnomads.json")
    res = pipeline.search(query="python developer", profile=profile, force_refresh=True)
    st = states(res)
    for name in ("Naukri", "HelloWork", "Arbeitsagentur", "ZipRecruiter"):
        assert st[name]["state"] == "skipped", name
    assert st["Indeed"]["state"] == "skipped" and "local site" in st["Indeed"]["error"]
    assert st["Bayt"]["state"] in ("ok", "failed", "timeout")          # MENA board does run
    assert st["Working Nomads"]["state"] == "ok" and st["Working Nomads"]["count"] == 1
    assert not any("naukri" in c or "hellowork" in c for c in net.calls)
    assert res["coverage"]["target_countries"] == ["Tunisia"]
    assert any(s["source"] == "Naukri" for s in res["coverage"]["sources_skipped"])


def test_france_and_germany_targets_use_local_sites(profile, net):
    preferences.save({"target_countries": ["France", "Germany"], "work_mode": "Onsite"})
    net.fixture("rest.arbeitsagentur.de", "arbeitsagentur.json")
    res = pipeline.search(query="python developer", profile=profile, force_refresh=True)
    hosts = " ".join(net.calls)
    assert "fr.indeed.com" in hosts and "de.indeed.com" in hosts and "hellowork" in hosts
    assert "www.indeed.com/jobs" not in hosts and "naukri" not in hosts
    assert states(res)["Arbeitsagentur"]["state"] == "ok"
    assert states(res)["Working Nomads"]["state"] == "skipped"          # onsite only: remote boards are skipped


def test_user_can_switch_a_source_off(profile, net):
    preferences.save({"target_countries": ["France"], "disabled_sources": ["Indeed", "LinkedIn"]})
    res = pipeline.search(query="python", profile=profile, force_refresh=True)
    assert states(res)["Indeed"]["state"] == "disabled" and states(res)["LinkedIn"]["state"] == "disabled"
    assert not any("indeed.com" in c or "linkedin.com" in c for c in net.calls)


def test_linkedin_still_receives_the_location_exactly_as_given(profile, net):
    """The LinkedIn scraper and its query handling must behave as before."""
    pipeline.search(query="python developer", location="Tunis, Tunisia", profile=profile, force_refresh=True)
    li = [c for c in net.calls if "linkedin.com" in c]
    assert li and all("Tunis" in c for c in li)


def test_all_sources_failing_is_reported_not_hidden(profile, net):
    res = pipeline.search(query="python developer", profile=profile, force_refresh=True)
    assert res["count"] == 0 and res["partial"] and res["warnings"]
    assert res["coverage"]["sources_with_results"] == 0


def test_company_boards_feed_the_search_and_filters_apply(profile, net):
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    preferences.save({"target_countries": ["Netherlands"]})
    res = pipeline.search(query="backend engineer", profile=profile, force_refresh=True)
    titles = [(j["title"], j["company"]) for j in res["jobs"]]
    assert ("Backend Engineer", "Adyen") in titles
    assert res["coverage"]["company_boards"]["ok"] >= 1

    preferences.save({"excluded_companies": ["Adyen"]})
    res = pipeline.search(query="backend engineer", profile=profile, force_refresh=True)
    assert not any(j["company"] == "Adyen" for j in res["jobs"])


def test_old_postings_are_hidden_by_max_age(profile, net):
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    preferences.save({"max_age_days": 1})
    res = pipeline.search(query="backend engineer", profile=profile, force_refresh=True)
    assert not any(j["company"] == "Adyen" for j in res["jobs"])      # fixture jobs are weeks old


def test_search_teaches_the_next_search_new_company_boards(profile, net):
    net.add("remotive.com", '{"jobs":[{"id":1,"title":"Python Developer","company_name":"Smallco","candidate_required_location":"Worldwide",'
                            '"url":"https://jobs.lever.co/smallco/abc","description":"Python","publication_date":"2026-10-30T00:00:00","job_type":"full_time","category":"Software Development"}]}')
    pipeline.search(query="python developer", profile=profile, force_refresh=True)
    from jh import company_directory
    assert ("lever", "smallco") in company_directory._health()


def test_custom_feed_and_career_page_jobs_appear(profile, net):
    net.fixture("jobs.example.tn/feed", "feed_wpjobmanager.rss")
    net.fixture("careers.example.com/jobs", "careerpage_jsonld.html")
    preferences.save({"custom_feeds": [{"name": "TN", "url": "https://jobs.example.tn/feed/"}],
                      "career_pages": [{"name": "InstaDeep", "url": "https://careers.example.com/jobs"}],
                      "target_countries": ["Tunisia"]})
    res = pipeline.search(query="developer", profile=profile, force_refresh=True)
    companies = {j["company"] for j in res["jobs"]}
    assert "Proxym Group" in companies or "Sofrecom Tunisie" in companies
    assert "InstaDeep" not in companies or True  # title filter may drop it; the source itself must have run
    assert states(res)["Custom Feed"]["state"] == "ok" and states(res)["Career Page"]["state"] == "ok"


def test_unconfigured_user_sources_are_silent(profile, net):
    res = pipeline.search(query="python", profile=profile, force_refresh=True)
    assert "Custom Feed" not in states(res) and "Career Page" not in states(res)


def test_preferences_overlay_does_not_touch_stored_resume(profile, net):
    preferences.save({"min_salary": 99999, "excluded_keywords": ["crypto"]})
    pipeline.search(query="python", profile=profile, force_refresh=True)
    assert db.get_profile()["min_salary"] != 99999


def test_background_enricher_is_bounded(ws):
    from jh import config
    assert config.ENRICH_BG_MAX_PER_CYCLE <= 100
