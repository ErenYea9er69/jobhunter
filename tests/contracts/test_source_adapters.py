"""Contract tests for modular source adapters per Section 6.4 and 7 of newall-logic.md."""
import pytest
from jh.sources.base import BaseSourceAdapter, SourcePage, SourceHealth
from jh.sources.greenhouse import GreenhouseAdapter
from jh.sources.lever import LeverAdapter
from jh.sources.ashby import AshbyAdapter
from jh.sources.smartrecruiters import SmartRecruitersAdapter
from jh.sources.jobicy import JobicyAdapter
from jh.sources.himalayas import HimalayasAdapter
from jh.sources.adzuna import AdzunaAdapter
from jh.sources.usajobs import USAJobsAdapter
from jh.sources.remotive import RemotiveAdapter
from jh.sources.jooble import JoobleAdapter
from jh.sources.workable_account import WorkableAccountAdapter
from jh.sources.linkedin_adapter import LinkedInAdapter


def test_adapters_inherit_from_base():
    adapters = [
        GreenhouseAdapter(),
        LeverAdapter(),
        AshbyAdapter(),
        SmartRecruitersAdapter(),
        JobicyAdapter(),
        HimalayasAdapter(),
        AdzunaAdapter(),
        USAJobsAdapter(),
        RemotiveAdapter(),
        JoobleAdapter(),
        WorkableAccountAdapter(),
        LinkedInAdapter(),
    ]
    for adapter in adapters:
        assert isinstance(adapter, BaseSourceAdapter)
        health = adapter.health_check()
        assert isinstance(health, SourceHealth)
        assert hasattr(adapter, "search")
        assert hasattr(adapter, "get_details")
        assert hasattr(adapter, "check_status")


def test_greenhouse_adapter_contract():
    gh = GreenhouseAdapter()
    assert gh.source_name == "Greenhouse"
    # Greenhouse requires slug or company identifier
    page = gh.search(query="engineer", filters={"slug": "stripe"})
    assert isinstance(page, SourcePage)
    assert page.source_name == "Greenhouse"


def test_linkedin_adapter_contract_preserves_boundary():
    la = LinkedInAdapter()
    assert la.source_name == "LinkedIn"
    health = la.health_check()
    assert health.source_name == "LinkedIn"
    # Adapter maps scraped items into SourcePage
    raw_sample = [{
        "title": "Senior Python Developer",
        "company": "Anthropic",
        "location": "San Francisco, CA",
        "url": "https://www.linkedin.com/jobs/view/123456789",
        "description": "Building next-gen AI"
    }]
    page = la.map_scraped_results(raw_sample)
    assert isinstance(page, SourcePage)
    assert len(page.items) == 1
    assert page.items[0]["title"] == "Senior Python Developer"
    assert page.items[0]["source"] == "LinkedIn"
