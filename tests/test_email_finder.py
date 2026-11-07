"""Tests for LinkedIn and corporate email finder engine."""

from jh import email_finder


def test_parse_linkedin_url():
    f, l = email_finder.parse_linkedin_url("https://www.linkedin.com/in/guillermo-rauch")
    assert f == "Guillermo"
    assert l == "Rauch"

    f2, l2 = email_finder.parse_linkedin_url("https://linkedin.com/in/alex-wang-88a912/")
    assert f2 == "Alex"
    assert l2 == "Wang"

    f3, l3 = email_finder.parse_linkedin_url("")
    assert f3 == ""
    assert l3 == ""


def test_resolve_company_domain():
    assert email_finder.resolve_company_domain("Stripe") == "stripe.com"
    assert email_finder.resolve_company_domain("Vercel") == "vercel.com"
    assert email_finder.resolve_company_domain("Scale AI") == "scale.com"
    assert email_finder.resolve_company_domain("Acme Technologies Inc.") == "acme.com"
    assert email_finder.resolve_company_domain("CustomCo", explicit_domain="https://custom.io/about") == "custom.io"


def test_find_corporate_email_founder():
    res = email_finder.find_corporate_email(
        name="Guillermo Rauch",
        company="Vercel",
        role="CEO & Founder",
    )
    assert res["success"] is True
    assert res["domain"] == "vercel.com"
    assert res["primary_email"] == "guillermo@vercel.com"
    assert res["confidence_pct"] >= 80
    assert len(res["candidates"]) >= 3


def test_find_corporate_email_employee():
    res = email_finder.find_corporate_email(
        name="Dara Khosrowshahi",
        company="Uber",
        role="Chief Executive Officer",
    )
    assert res["success"] is True
    assert res["domain"] == "uber.com"
    assert "@uber.com" in res["primary_email"]
    assert res["confidence_pct"] >= 75


def test_find_corporate_email_via_linkedin_url():
    res = email_finder.find_corporate_email(
        linkedin_url="https://www.linkedin.com/in/patrick-collison",
        company="Stripe",
        role="Co-Founder",
    )
    assert res["success"] is True
    assert res["domain"] == "stripe.com"
    assert res["primary_email"] == "patrick@stripe.com"
    assert res["first_name"] == "Patrick"
    assert res["last_name"] == "Collison"
