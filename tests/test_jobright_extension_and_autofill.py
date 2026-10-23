"""Tests for Jobright-style Autofill Extension Engine and Payload Enhancements."""
import pytest
from jh import autofill


def test_autofill_payload_extended_history_and_metrics():
    profile = {
        "name": "Rayen Ben Aissa",
        "email": "rayen@example.com",
        "phone": "+1-555-0199",
        "location": "San Francisco, CA, United States",
        "skills": ["Python", "React", "TypeScript", "FastAPI"],
        "experience": [
            {
                "company": "Tech Corp",
                "role": "Senior Full Stack Engineer",
                "start": "2023-01",
                "end": "Present",
                "bullets": ["Engineered core backend APIs in Python and FastAPI", "Built React UI"]
            },
            {
                "company": "Startup Studio",
                "role": "Software Engineer",
                "start": "2021-01",
                "end": "2022-12",
                "bullets": ["Developed full stack web apps using React and Python"]
            }
        ],
        "education": [
            {
                "institution": "University of Technology",
                "degree": "Bachelor of Science in Computer Science",
                "graduation_year": "2021"
            }
        ],
        "legal_and_eeo": {
            "authorized_us": "Yes",
            "require_sponsorship_now": "No",
            "require_sponsorship_future": "No",
            "gender": "Decline to self-identify",
            "veteran_status": "No"
        }
    }
    payload = autofill.get_autofill_payload(profile)

    # 1. Multi-position work history array
    assert "work_history" in payload
    assert len(payload["work_history"]) == 2
    assert payload["work_history"][0]["company"] == "Tech Corp"
    assert payload["work_history"][0]["is_current"] is True
    assert payload["work_history"][1]["company"] == "Startup Studio"
    assert payload["work_history"][1]["is_current"] is False

    # 2. Multi-education array
    assert "education_history" in payload
    assert len(payload["education_history"]) == 1
    assert payload["education_history"][0]["institution"] == "University of Technology"

    # 3. Deterministic Experience & Skill Tenure Calculation
    assert "total_years_experience" in payload
    assert payload["total_years_experience"] >= 3
    assert "skill_years" in payload
    assert payload["skill_years"]["python"] >= 3
    assert payload["skill_years"]["react"] >= 3

    # 4. Address Components
    assert "address_components" in payload
    assert payload["address_components"]["city"] == "San Francisco"
    assert payload["address_components"]["state_province"] in ["CA", "California", ""]
    assert payload["address_components"]["country"] in ["United States", "US"]

    # 5. Candidate Configurable Legal & EEO
    assert "legal_and_eeo" in payload
    assert payload["legal_and_eeo"]["authorized_us"] == "Yes"
    assert payload["legal_and_eeo"]["require_sponsorship_now"] == "No"


def test_screening_solver_question_types():
    profile = {
        "name": "Rayen Ben Aissa",
        "skills": ["Python", "React"],
        "experience": [
            {"company": "Tech Corp", "role": "Engineer", "start": "2021-01", "end": "2025-01", "bullets": ["Python development"]}
        ],
        "legal_and_eeo": {
            "authorized_us": "Yes",
            "require_sponsorship_now": "No"
        }
    }
    # 1. Boolean Yes
    res_auth = autofill.solve_screening_question("Are you legally authorized to work in the United States?", profile)
    assert res_auth["question_type"] == "boolean"
    assert "yes" in res_auth["answer"].lower()

    # 2. Boolean No
    res_spons = autofill.solve_screening_question("Will you now or in the future require visa sponsorship?", profile)
    assert res_spons["question_type"] == "boolean"
    assert "no" in res_spons["answer"].lower()

    # 3. Numeric Years
    res_num = autofill.solve_screening_question("How many years of Python experience do you have?", profile)
    assert res_num["question_type"] == "numeric"
    assert any(char.isdigit() for char in res_num["answer"])

    # 4. Behavioral STAR Narrative
    res_why = autofill.solve_screening_question("Why are you interested in joining Cohere?", profile, job={"company": "Cohere", "title": "Software Engineer"})
    assert res_why["question_type"] == "narrative"
    assert res_why["grounded"] is True


def test_extension_api_endpoints():
    from jh import httpd, db
    # 1. Extension Status
    handler_status = httpd.ROUTES.get(("GET", "/api/extension/status"))
    assert handler_status is not None, "GET /api/extension/status route not registered"
    r_status = handler_status({}, {})
    assert r_status["success"] is True
    assert "candidate_name" in r_status
    assert "extension_version" in r_status

    # 2. Extension Payload
    handler_payload = httpd.ROUTES.get(("POST", "/api/extension/payload"))
    assert handler_payload is not None, "POST /api/extension/payload route not registered"
    r_payload = handler_payload({}, {"url": "https://jobs.lever.co/cohere/software-engineer-intern"})
    assert r_payload["success"] is True
    assert "payload" in r_payload
    assert r_payload["platform"] == "lever"
    assert "work_history" in r_payload["payload"]

    # 3. Extension Solve Question
    handler_solve = httpd.ROUTES.get(("POST", "/api/extension/solve"))
    assert handler_solve is not None, "POST /api/extension/solve route not registered"
    r_solve = handler_solve({}, {
        "question": "Are you authorized to work in the United States?",
        "url": "https://jobs.lever.co/cohere/software-engineer-intern"
    })
    assert r_solve["success"] is True
    assert r_solve["question_type"] == "boolean"

    # 4. Extension Confirm Applied
    handler_confirm = httpd.ROUTES.get(("POST", "/api/extension/confirm-applied"))
    assert handler_confirm is not None, "POST /api/extension/confirm-applied route not registered"
    r_confirm = handler_confirm({}, {
        "job_url": "https://jobs.lever.co/cohere/software-engineer-intern",
        "company": "Cohere",
        "title": "Software Engineer Intern (Winter 2027)",
        "source": "chrome_extension"
    })
    assert r_confirm["success"] is True
    assert r_confirm["verified"] is True
    assert "application_id" in r_confirm


