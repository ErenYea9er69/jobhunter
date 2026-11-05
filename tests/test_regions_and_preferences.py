import pytest

from jh import preferences, regions, source_registry


# ------------------------------------------------------------------ regions

@pytest.mark.parametrize("text,code", [
    ("Tunis, Tunisia", "TN"), ("Sfax", "TN"), ("Paris, France", "FR"), ("Berlin", "DE"), ("Dubai, UAE", "AE"),
    ("London, UK", "GB"), ("Remote", None), ("", None), ("Casablanca", "MA"), ("San Francisco, CA", "US"),
])
def test_country_of_location(text, code):
    assert regions.country_of_location(text) == code


def test_short_words_are_not_read_as_country_codes():
    assert regions.to_code("in") is None or regions.to_code("in") == "IN"  # "IN" is valid only as an exact code
    assert regions.country_of_location("working in the it department") is None


def test_romania_is_not_oman():
    assert regions.country_of_location("Bucharest, Romania") == "RO"
    assert regions.country_of_location("Romania") == "RO"


def test_resolve_targets_order_and_fallbacks():
    assert regions.resolve_targets({"target_countries": ["Tunisia", "France"]}, {}, "") == ["TN", "FR"]
    assert regions.resolve_targets({}, {"location": "Tunis, Tunisia"}, "") == ["TN"]
    assert regions.resolve_targets({"target_countries": ["Tunisia"]}, {}, "Berlin") == ["TN", "DE"]
    assert regions.resolve_targets({}, {}, "remote") == []


def test_source_eligibility_rules():
    elig = regions.source_is_eligible
    assert elig(["*"], ["TN"], False)
    assert elig(["MENA"], ["TN"], False) and not elig(["MENA"], ["FR"], False)
    assert not elig(["IN"], ["TN"], True)            # Naukri never runs for a Tunisian searcher
    assert not elig(["FR"], ["TN"], True)            # HelloWork neither
    assert elig(["FR"], ["TN", "FR"], True)          # unless France is a target
    assert elig(["REMOTE"], ["TN"], True) and not elig(["REMOTE"], ["TN"], False)
    assert not elig(["IN"], [], True) and elig(["MENA"], [], True)   # unknown location: skip single-country sources only


def test_remote_acceptance():
    assert regions.wants_remote({"work_mode": "Any"}, {})
    assert regions.wants_remote({"work_mode": "Remote"}, {})
    assert not regions.wants_remote({"work_mode": "Onsite", "include_worldwide_remote": True}, {})
    assert regions.wants_remote({"work_mode": "Hybrid"}, {}) and not regions.wants_remote({"work_mode": "Hybrid", "include_worldwide_remote": False}, {})
    assert not regions.wants_remote({}, {"work_mode": "Onsite"})      # falls back to the resume's own preference


# ------------------------------------------------------------------ registry planning

def test_indeed_runs_once_per_target_country_with_local_domain():
    plan = source_registry.plan("Indeed", ["FR", "DE", "TN"], "", True)
    assert [p["kwargs"]["domain"] for p in plan] == ["fr.indeed.com", "de.indeed.com"]   # Tunisia has no Indeed site
    assert plan[0]["location"] == "France"


def test_indeed_with_a_city_keeps_the_city():
    plan = source_registry.plan("Indeed", ["FR"], "Lyon, France", True)
    assert plan[0]["location"] == "Lyon, France"


def test_indeed_without_any_local_site_is_skipped():
    assert source_registry.plan("Indeed", ["TN"], "", True) == []


def test_unknown_location_keeps_old_indeed_behaviour():
    plan = source_registry.plan("Indeed", [], "", True)
    assert len(plan) == 1 and plan[0]["kwargs"] == {}


def test_adzuna_countries_gate():
    assert [p["kwargs"]["country"] for p in source_registry.plan("Adzuna", ["GB", "FR", "TN"], "", True)] == ["gb", "fr"]


def test_user_disabled_and_enabled_lists():
    assert source_registry.skip_reason("Indeed", {"disabled_sources": ["Indeed"]}, ["FR"], True)[0] == "disabled"
    assert source_registry.skip_reason("Indeed", {"enabled_sources": ["Bayt"]}, ["FR"], True)[0] == "disabled"
    assert source_registry.skip_reason("Bayt", {"enabled_sources": ["Bayt"]}, ["TN"], True) is None
    state, why, silent = source_registry.skip_reason("Custom Feed", {}, ["TN"], True, configured=False)
    assert state == "skipped" and silent


def test_every_real_source_has_a_catalog_entry():
    from jh import sources
    assert {s.name for s in sources.SEARCH_SOURCES} <= set(source_registry.INFO)


# ------------------------------------------------------------------ preferences

def test_defaults_when_no_file(ws):
    assert preferences.is_default(preferences.load())


def test_save_validates_and_normalises(ws):
    saved, warns = preferences.save({"target_countries": ["tunisie", "FR", "Narnia"], "work_mode": "remote", "min_salary": "45000",
                                     "job_types": ["fulltime", "freelance"], "seniority": ["Senior", "wizard"]})
    assert saved["target_countries"] == ["Tunisia", "France", "Narnia"]
    assert any("Narnia" in w for w in warns)
    assert saved["work_mode"] == "Remote" and saved["min_salary"] == 45000
    assert saved["job_types"] == ["Full-time", "Contract"] and saved["seniority"] == ["senior"]


@pytest.mark.parametrize("bad", [{"nonsense": 1}, {"work_mode": "teleport"}, {"min_salary": -5}, {"company_focus": "x"},
                                 {"include_worldwide_remote": "yes"}, {"disabled_sources": ["NoSuchBoard"]},
                                 {"custom_feeds": [{"url": "http://127.0.0.1/feed"}]}, {"search_depth": "insane"}])
def test_invalid_updates_are_rejected(ws, bad):
    with pytest.raises(preferences.PreferenceError):
        preferences.save(bad)


def test_merge_lists(ws):
    preferences.save({"excluded_keywords": ["php"]})
    saved, _ = preferences.save({"excluded_keywords": ["PHP", "cobol"]}, merge_lists=True)
    assert saved["excluded_keywords"] == ["php", "cobol"]


def test_preferences_persist_and_mirror_legacy_settings(ws):
    from jh import db
    preferences.save({"home_country": "Tunisia", "include_worldwide_remote": False})
    preferences._cache.update(mtime=None, path=None, data=None)
    assert preferences.load()["home_country"] == "Tunisia"
    assert db.get_setting("user_country") == "Tunisia" and db.get_setting("include_worldwide_remote") == "0"


def test_overlay_changes_a_copy_not_the_stored_profile(ws):
    profile = {"work_mode": "Any", "target_title": "Backend Engineer", "target_roles": ["Python Developer"], "excluded_keywords": ["php"], "min_salary": 0}
    prefs = dict(preferences.DEFAULTS, work_mode="Remote", min_salary=50000, target_titles=["Platform Engineer"],
                 excluded_keywords=["crypto"], cities=["Tunis"], target_countries=["Tunisia"])
    out = preferences.overlay_profile(profile, prefs)
    assert out["work_mode"] == "Remote" and out["min_salary"] == 50000 and out["target_title"] == "Platform Engineer"
    assert out["target_roles"] == ["Platform Engineer", "Python Developer"]
    assert out["excluded_keywords"] == ["crypto", "php"] and out["preferred_locations"] == ["Tunis", "Tunisia"]
    assert profile["work_mode"] == "Any" and profile["min_salary"] == 0   # input untouched


def test_company_focus_maps_to_famous_mode():
    assert preferences.famous_mode({"company_focus": "avoid_big_names"}) == "hide"
    assert preferences.famous_mode({"company_focus": "only_big_names"}) == "only"
    assert preferences.famous_mode({"company_focus": "any"}) == "all"
