import json
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)

jobs = []
specs = [
    # 1-10: Tunisia jobs (Tunis, Sfax, Sousse, Ariana)
    {'id': 'job_tn_1', 'title': 'Software Engineering Intern', 'company': 'Instadeep', 'city': 'Tunis', 'country': 'Tunisia', 'work_mode': 'on-site', 'job_type': 'internship', 'salary_min': 1000, 'salary_currency': 'TND', 'role': 'Backend Engineer', 'visa': False, 'days_old': 1},
    {'id': 'job_tn_2', 'title': 'Backend Developer PFE', 'company': 'Vermeg', 'city': 'Sfax', 'country': 'Tunisia', 'work_mode': 'on-site', 'job_type': 'internship', 'salary_min': 1200, 'salary_currency': 'TND', 'role': 'Backend Engineer', 'visa': False, 'days_old': 2},
    {'id': 'job_tn_3', 'title': 'Junior Full Stack Engineer', 'company': 'Telnet', 'city': 'Sfax', 'country': 'Tunisia', 'work_mode': 'hybrid', 'job_type': 'junior full-time', 'salary_min': 2000, 'salary_currency': 'TND', 'role': 'Full Stack Engineer', 'visa': False, 'days_old': 5},
    {'id': 'job_tn_4', 'title': 'Senior Python Backend Developer', 'company': 'Expensya', 'city': 'Tunis', 'country': 'Tunisia', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 4500, 'salary_currency': 'TND', 'role': 'Backend Engineer', 'visa': False, 'days_old': 3},
    {'id': 'job_tn_5', 'title': 'Frontend React Engineer', 'company': 'Sofrecom', 'city': 'Tunis', 'country': 'Tunisia', 'work_mode': 'hybrid', 'job_type': 'full-time', 'salary_min': 3000, 'salary_currency': 'TND', 'role': 'Frontend Engineer', 'visa': False, 'days_old': 8},
    {'id': 'job_tn_6', 'title': 'DevOps Engineer', 'company': 'CloudNets', 'city': 'Ariana', 'country': 'Tunisia', 'work_mode': 'on-site', 'job_type': 'full-time', 'salary_min': 3500, 'salary_currency': 'TND', 'role': 'DevOps Engineer', 'visa': False, 'days_old': 12},
    {'id': 'job_tn_7', 'title': 'Web Development Intern (PFE)', 'company': 'SfaxTech', 'city': 'Sfax', 'country': 'Tunisia', 'work_mode': 'on-site', 'job_type': 'internship', 'salary_min': 800, 'salary_currency': 'TND', 'role': 'Full Stack Engineer', 'visa': False, 'days_old': 0.5},
    {'id': 'job_tn_8', 'title': 'Contract Python Scraper Developer', 'company': 'DataConsult', 'city': 'Sousse', 'country': 'Tunisia', 'work_mode': 'remote', 'job_type': 'contract', 'salary_min': 2500, 'salary_currency': 'TND', 'role': 'Backend Engineer', 'visa': False, 'days_old': 15},
    {'id': 'job_tn_9', 'title': 'Frontend Vue/React Developer', 'company': 'DigitalWave', 'city': 'Sfax', 'country': 'Tunisia', 'work_mode': 'on-site', 'job_type': 'full-time', 'salary_min': 2200, 'salary_currency': 'TND', 'role': 'Frontend Engineer', 'visa': False, 'days_old': 20},
    {'id': 'job_tn_10', 'title': 'Stale Tunisia Backend Role', 'company': 'OldCorp', 'city': 'Tunis', 'country': 'Tunisia', 'work_mode': 'on-site', 'job_type': 'full-time', 'salary_min': 2000, 'salary_currency': 'TND', 'role': 'Backend Engineer', 'visa': False, 'days_old': 45},

    # 11-20: Germany / Europe (Berlin, Munich, Paris, Amsterdam)
    {'id': 'job_eu_1', 'title': 'Senior Backend Engineer (Python/FastAPI)', 'company': 'Zalando', 'city': 'Berlin', 'country': 'Germany', 'work_mode': 'hybrid', 'job_type': 'full-time', 'salary_min': 75000, 'salary_currency': 'EUR', 'role': 'Backend Engineer', 'visa': True, 'days_old': 2},
    {'id': 'job_eu_2', 'title': 'Cloud DevOps Specialist', 'company': 'Delivery Hero', 'city': 'Berlin', 'country': 'Germany', 'work_mode': 'on-site', 'job_type': 'full-time', 'salary_min': 80000, 'salary_currency': 'EUR', 'role': 'DevOps Engineer', 'visa': True, 'days_old': 4},
    {'id': 'job_eu_3', 'title': 'Frontend Engineer (React/TypeScript)', 'company': 'N26', 'city': 'Berlin', 'country': 'Germany', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 70000, 'salary_currency': 'EUR', 'role': 'Frontend Engineer', 'visa': True, 'days_old': 6},
    {'id': 'job_eu_4', 'title': 'Software Engineering Working Student', 'company': 'Siemens', 'city': 'Munich', 'country': 'Germany', 'work_mode': 'hybrid', 'job_type': 'internship', 'salary_min': 20000, 'salary_currency': 'EUR', 'role': 'Full Stack Engineer', 'visa': False, 'days_old': 7},
    {'id': 'job_eu_5', 'title': 'Backend Developer Go/Python', 'company': 'Doctolib', 'city': 'Paris', 'country': 'France', 'work_mode': 'hybrid', 'job_type': 'full-time', 'salary_min': 65000, 'salary_currency': 'EUR', 'role': 'Backend Engineer', 'visa': True, 'days_old': 10},
    {'id': 'job_eu_6', 'title': 'Site Reliability Engineer', 'company': 'Adyen', 'city': 'Amsterdam', 'country': 'Netherlands', 'work_mode': 'on-site', 'job_type': 'full-time', 'salary_min': 85000, 'salary_currency': 'EUR', 'role': 'DevOps Engineer', 'visa': True, 'days_old': 14},
    {'id': 'job_eu_7', 'title': 'Frontend Developer (Next.js)', 'company': 'Klarna', 'city': 'Berlin', 'country': 'Germany', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 72000, 'salary_currency': 'EUR', 'role': 'Frontend Engineer', 'visa': False, 'days_old': 18},
    {'id': 'job_eu_8', 'title': 'Contract Backend Architect', 'company': 'EuroConsult', 'city': 'Frankfurt', 'country': 'Germany', 'work_mode': 'remote', 'job_type': 'contract', 'salary_min': 95000, 'salary_currency': 'EUR', 'role': 'Backend Engineer', 'visa': False, 'days_old': 22},
    {'id': 'job_eu_9', 'title': 'Junior Software Developer', 'company': 'Auto1', 'city': 'Berlin', 'country': 'Germany', 'work_mode': 'on-site', 'job_type': 'junior full-time', 'salary_min': 55000, 'salary_currency': 'EUR', 'role': 'Backend Engineer', 'visa': True, 'days_old': 3},
    {'id': 'job_eu_10', 'title': 'Expired Berlin Posting', 'company': 'DeadStartup', 'city': 'Berlin', 'country': 'Germany', 'work_mode': 'on-site', 'job_type': 'full-time', 'salary_min': 60000, 'salary_currency': 'EUR', 'role': 'Full Stack Engineer', 'visa': False, 'days_old': 70},

    # 21-30: USA (Austin, San Francisco, New York)
    {'id': 'job_us_1', 'title': 'Staff Backend Engineer', 'company': 'Fintech Global', 'city': 'Austin', 'country': 'USA', 'work_mode': 'hybrid', 'job_type': 'full-time', 'salary_min': 160000, 'salary_currency': 'USD', 'role': 'Backend Engineer', 'visa': True, 'days_old': 1},
    {'id': 'job_us_2', 'title': 'Senior Frontend Developer', 'company': 'DesignCraft', 'city': 'San Francisco', 'country': 'USA', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 150000, 'salary_currency': 'USD', 'role': 'Frontend Engineer', 'visa': True, 'days_old': 3},
    {'id': 'job_us_3', 'title': 'DevOps / Infrastructure Engineer', 'company': 'CloudScale', 'city': 'Austin', 'country': 'USA', 'work_mode': 'on-site', 'job_type': 'full-time', 'salary_min': 140000, 'salary_currency': 'USD', 'role': 'DevOps Engineer', 'visa': False, 'days_old': 5},
    {'id': 'job_us_4', 'title': 'Software Engineering Intern Summer', 'company': 'BigTech Labs', 'city': 'Austin', 'country': 'USA', 'work_mode': 'on-site', 'job_type': 'internship', 'salary_min': 60000, 'salary_currency': 'USD', 'role': 'Backend Engineer', 'visa': False, 'days_old': 2},
    {'id': 'job_us_5', 'title': 'Full Stack Engineer (Node/React)', 'company': 'Stripe', 'city': 'San Francisco', 'country': 'USA', 'work_mode': 'hybrid', 'job_type': 'full-time', 'salary_min': 175000, 'salary_currency': 'USD', 'role': 'Full Stack Engineer', 'visa': True, 'days_old': 9},
    {'id': 'job_us_6', 'title': 'Junior Python Developer', 'company': 'DataStream', 'city': 'Austin', 'country': 'USA', 'work_mode': 'on-site', 'job_type': 'junior full-time', 'salary_min': 90000, 'salary_currency': 'USD', 'role': 'Backend Engineer', 'visa': False, 'days_old': 11},
    {'id': 'job_us_7', 'title': 'Frontend UI Engineer', 'company': 'Vercel', 'city': 'San Francisco', 'country': 'USA', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 145000, 'salary_currency': 'USD', 'role': 'Frontend Engineer', 'visa': False, 'days_old': 14},
    {'id': 'job_us_8', 'title': 'Contract Cloud Architect', 'company': 'Enterprise Corp', 'city': 'New York', 'country': 'USA', 'work_mode': 'remote', 'job_type': 'contract', 'salary_min': 180000, 'salary_currency': 'USD', 'role': 'DevOps Engineer', 'visa': False, 'days_old': 19},
    {'id': 'job_us_9', 'title': 'Backend Systems Engineer', 'company': 'Datadog', 'city': 'New York', 'country': 'USA', 'work_mode': 'hybrid', 'job_type': 'full-time', 'salary_min': 165000, 'salary_currency': 'USD', 'role': 'Backend Engineer', 'visa': True, 'days_old': 25},
    {'id': 'job_us_10', 'title': 'Expired Austin Listing', 'company': 'OldAustinTech', 'city': 'Austin', 'country': 'USA', 'work_mode': 'on-site', 'job_type': 'full-time', 'salary_min': 100000, 'salary_currency': 'USD', 'role': 'Backend Engineer', 'visa': False, 'days_old': 62},

    # 31-40: Global Remote / Tech Feeds
    {'id': 'job_rem_1', 'title': 'Remote Senior Backend Engineer', 'company': 'GitLab', 'city': 'Remote', 'country': 'Worldwide', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 130000, 'salary_currency': 'USD', 'role': 'Backend Engineer', 'visa': False, 'days_old': 1},
    {'id': 'job_rem_2', 'title': 'Remote Frontend React Specialist', 'company': 'Automattic', 'city': 'Remote', 'country': 'Worldwide', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 110000, 'salary_currency': 'USD', 'role': 'Frontend Engineer', 'visa': False, 'days_old': 2},
    {'id': 'job_rem_3', 'title': 'Remote Full Stack Engineer', 'company': 'Basecamp', 'city': 'Remote', 'country': 'Worldwide', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 120000, 'salary_currency': 'USD', 'role': 'Full Stack Engineer', 'visa': False, 'days_old': 4},
    {'id': 'job_rem_4', 'title': 'Remote DevOps SRE', 'company': 'Canonical', 'city': 'Remote', 'country': 'Worldwide', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 115000, 'salary_currency': 'USD', 'role': 'DevOps Engineer', 'visa': False, 'days_old': 7},
    {'id': 'job_rem_5', 'title': 'Remote Python Intern', 'company': 'OpenSourceOrg', 'city': 'Remote', 'country': 'Worldwide', 'work_mode': 'remote', 'job_type': 'internship', 'salary_min': 35000, 'salary_currency': 'USD', 'role': 'Backend Engineer', 'visa': False, 'days_old': 9},
    {'id': 'job_rem_6', 'title': 'Remote Contract Python Engineer', 'company': 'Toptal Client', 'city': 'Remote', 'country': 'Worldwide', 'work_mode': 'remote', 'job_type': 'contract', 'salary_min': 100000, 'salary_currency': 'USD', 'role': 'Backend Engineer', 'visa': False, 'days_old': 12},
    {'id': 'job_rem_7', 'title': 'Remote Junior Web Engineer', 'company': 'Zapier', 'city': 'Remote', 'country': 'Worldwide', 'work_mode': 'remote', 'job_type': 'junior full-time', 'salary_min': 85000, 'salary_currency': 'USD', 'role': 'Full Stack Engineer', 'visa': False, 'days_old': 16},
    {'id': 'job_rem_8', 'title': 'Remote Staff Infrastructure Engineer', 'company': 'HashiCorp', 'city': 'Remote', 'country': 'Worldwide', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': 155000, 'salary_currency': 'USD', 'role': 'DevOps Engineer', 'visa': False, 'days_old': 21},
    {'id': 'job_rem_9', 'title': 'Unsalaried Remote Backend Developer', 'company': 'StealthCo', 'city': 'Remote', 'country': 'Worldwide', 'work_mode': 'remote', 'job_type': 'full-time', 'salary_min': None, 'salary_currency': None, 'role': 'Backend Engineer', 'visa': False, 'days_old': 5},
    {'id': 'job_rem_10', 'title': 'Duplicate Job Tech Sample', 'company': 'Instadeep', 'city': 'Tunis', 'country': 'Tunisia', 'work_mode': 'on-site', 'job_type': 'internship', 'salary_min': 1000, 'salary_currency': 'TND', 'role': 'Backend Engineer', 'visa': False, 'days_old': 1.5}
]

for s in specs:
    post_dt = (now - timedelta(days=s['days_old'])).isoformat()
    jobs.append({
        'id': s['id'],
        'title': s['title'],
        'company': s['company'],
        'location': f"{s['city']}, {s['country']}",
        'city': s['city'],
        'country': s['country'],
        'work_mode': s['work_mode'],
        'job_type': s['job_type'],
        'salary_min': s['salary_min'],
        'salary_currency': s['salary_currency'],
        'role_focus': s['role'],
        'visa_sponsorship': s['visa'],
        'date_posted': post_dt,
        'url': f"https://example.com/jobs/{s['id']}",
        'source': 'mock_board',
        'description': f"Full job description for {s['title']} at {s['company']} in {s['city']}. Requires skills in {s['role']}."
    })

with open('tests/e2e/fixtures/jobs/jobs_40.json', 'w', encoding='utf-8') as f:
    json.dump(jobs, f, indent=2)

print(f"Generated {len(jobs)} jobs in tests/e2e/fixtures/jobs/jobs_40.json")
