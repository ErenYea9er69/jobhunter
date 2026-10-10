"""Demo data. Loaded only when JH_DEMO=1. Everything here carries a visible sample label."""

DEMO_PROFILE = {
    "name": "Alex Rivera (demo)", "email": "alex.rivera@example.com", "phone": "", "location": "Remote",
    "linkedin": "", "github": "", "target_title": "Senior Full-Stack Software Engineer",
    "years_of_experience": 6, "work_mode": "Remote", "preferred_locations": ["Remote"], "min_salary": 0,
    "excluded_keywords": [],
    "summary": "Full-stack engineer with six years of experience building web platforms and backend APIs in Python and TypeScript.",
    "skills": ["Python", "FastAPI", "Django", "TypeScript", "JavaScript", "React", "Node.js", "PostgreSQL",
               "Redis", "Docker", "AWS", "REST APIs", "GraphQL", "Git", "CI/CD", "Unit Testing"],
    "skills_by_category": {},
    "experience": [
        {"company": "CloudScale Systems", "role": "Senior Full-Stack Engineer", "location": "Remote",
         "start_date": "2023-01", "end_date": "Present", "current": True,
         "bullets": ["Built analytics dashboards with React, TypeScript, and FastAPI for 120,000 daily users.",
                     "Added Redis caching and tuned PostgreSQL queries, cutting peak API latency by 42%.",
                     "Set up Docker and GitHub Actions pipelines, moving releases from biweekly to daily.",
                     "Mentored 4 junior engineers on testing and API design."]},
        {"company": "Nexus Technologies", "role": "Software Engineer", "location": "San Francisco, CA",
         "start_date": "2020-03", "end_date": "2022-12", "current": False,
         "bullets": ["Developed REST microservices in Python and Node.js for financial transaction tracking.",
                     "Built React checkout components, raising conversion by 18%.",
                     "Wrote unit and integration tests reaching 88% coverage."]},
    ],
    "education": [{"institution": "University of California, Davis", "degree": "B.S. in Computer Science",
                   "graduation_year": "2018"}],
}

SAMPLE_JOBS = [
    {"id": "sample-1", "title": "Senior Backend Engineer, Billing", "company": "Sample Payments Co",
     "location": "Remote, US", "work_mode": "Remote", "salary": "$175,000 - $225,000",
     "url": "https://example.com/sample/1", "source": "Sample", "source_tier": "Sample (demo data)",
     "source_credit": "Demo data. Not a real posting.", "is_sample": True,
     "description": "Requirements: 5+ years of experience with Python, PostgreSQL, Redis, Docker and AWS. "
                    "Nice to have: Go, Kubernetes."},
]
