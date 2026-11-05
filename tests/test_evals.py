"""The team's report card as a test. If a change makes the Reviewer or the router worse, this fails."""

import pytest

from jh.team import evals


@pytest.fixture(scope="module")
def res():
    return evals.run_all()


@pytest.mark.parametrize("name", ["documents", "heldout_documents", "round2_documents"])
def test_reviewer_catches_every_fabrication_and_never_blocks_genuine_text(res, name):
    r = res[name]
    assert r["catch_rate"] == 1.0, r["failures"]
    assert r["false_alarms"] == 0, r["failures"]


@pytest.mark.parametrize("name", ["jobs", "heldout_jobs", "round2_jobs"])
def test_reviewer_catches_scams_and_injection_without_flagging_honest_postings(res, name):
    assert res[name]["wrong"] == 0, res[name]["failures"]


@pytest.mark.parametrize("name", ["router", "heldout_router", "round2_router"])
def test_router_reads_the_phrasings(res, name):
    assert res[name]["accuracy"] >= 0.95, res[name]["failures"]


def test_eval_sets_are_big_enough_to_mean_something(res):
    assert res["documents"]["fabrications"] >= 20 and res["documents"]["genuine"] >= 15
    assert res["router"]["cases"] >= 40 and res["jobs"]["cases"] >= 10
    assert res["heldout_documents"]["fabrications"] >= 10 and res["round2_router"]["cases"] >= 20


def test_the_old_reviewer_would_have_failed_this_set():
    """Documents what 2.2 scored: the Reviewer of version 2.2 caught 12 of 22 fabrications and the router got 18 of 40."""
    assert evals.run_documents()["fabrications"] == 22 and evals.run_router()["cases"] == 40
