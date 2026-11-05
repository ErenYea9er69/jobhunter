import pytest

from jh import skills
from jh.util import extract_job_sections, parse_salary


def test_inline_required_and_nice_to_have_are_weighted_separately():
    """A one-line posting used to weight every skill 0.4 because 'Nice to have' appeared in the line."""
    jd = "We need a Senior Backend Engineer. Required: Python, FastAPI, PostgreSQL, Kubernetes, Terraform, AWS. Nice to have: Kafka, GraphQL. 5+ years."
    w = skills.extract_weighted(jd)
    assert all(w[s] == 1.0 for s in ("Python", "FastAPI", "PostgreSQL", "Kubernetes", "Terraform", "AWS"))
    assert w["Kafka"] == 0.4 and w["GraphQL"] == 0.4


def test_multiline_sections_still_work():
    w = skills.extract_weighted("Requirements:\n- Python\n- Docker\nNice to have:\n- Kafka")
    assert w["Python"] == 1.0 and w["Kafka"] == 0.4


@pytest.mark.parametrize("text,cur,period", [
    ("$150,000 - $185,000", "USD", "year"), ("EUR 95,000 - 120,000", "EUR", "year"), ("3000-4500 TND", "TND", "month"),
    ("AED 20000 per month", "AED", "month"), ("60,000 TND per year", "TND", "year"), ("Europe remote 50k", "USD", "year"),
    ("nomad 40k", "USD", "year"),
])
def test_salary_currency_and_period(text, cur, period):
    s = parse_salary(text)
    assert s["currency"] == cur and s["period"] == period


@pytest.mark.parametrize("text,expected", [
    ("Salary 60,000-80,000 EUR", "60,000-80,000 EUR"), ("pay range of $90k to $120k per year", "$90k to $120k per year"),
    ("Rate 3000-4500 TND per month", "3000-4500 TND per month"), ("Compensation: 50k", "50k"),
    ("We pay 5-10 years of experience", ""), ("Salary is competitive", ""),
])
def test_salary_in_prose(text, expected):
    assert extract_job_sections(text)["salary_text"] == expected
