"""Skill ontology and extraction. Ambiguous words (go, next, express, ai) match only in safe forms."""
import re

# category -> canonical skill -> aliases. A leading "=" means case-sensitive exact match.
ONTOLOGY = {
    "Languages": {
        "Python": ["python3", "python"], "JavaScript": ["javascript", "ecmascript", "es6", "=JS"],
        "TypeScript": ["typescript"], "Go": ["golang", "=Go"], "Rust": ["rust lang", "=Rust"],
        "Java": ["=Java"], "C++": ["c++", "cpp"], "C#": ["c#", "csharp"], "Ruby": ["ruby"],
        "PHP": ["=PHP", "php"], "Kotlin": ["kotlin"], "Swift": ["=Swift"], "Scala": ["scala"],
        "SQL": ["sql", "t-sql", "plsql"], "R": ["r programming", "rstudio"], "Bash": ["bash scripting", "shell scripting"],
    },
    "Frontend": {
        "React": ["react.js", "reactjs", "react"], "Next.js": ["next.js", "nextjs"], "Vue.js": ["vue.js", "vuejs", "vue"],
        "Angular": ["angular"], "Svelte": ["svelte"], "Tailwind CSS": ["tailwindcss", "tailwind"],
        "HTML/CSS": ["html5", "css3", "html/css"], "Redux": ["redux"], "Webpack": ["webpack", "vite"],
    },
    "Backend": {
        "Node.js": ["node.js", "nodejs"], "Express": ["express.js", "expressjs"], "FastAPI": ["fastapi"],
        "Django": ["django"], "Flask": ["flask"], "Spring Boot": ["spring boot", "springboot", "spring framework"],
        "Ruby on Rails": ["ruby on rails", "=Rails"], ".NET": [".net", "dotnet", "asp.net"], "Laravel": ["laravel"],
    },
    "Data": {
        "PostgreSQL": ["postgresql", "postgres", "psql"], "MySQL": ["mysql", "mariadb"], "MongoDB": ["mongodb", "mongo"],
        "Redis": ["redis"], "SQLite": ["sqlite3", "sqlite"], "DynamoDB": ["dynamodb"], "Cassandra": ["cassandra"],
        "Elasticsearch": ["elasticsearch", "opensearch"], "Snowflake": ["snowflake"], "BigQuery": ["bigquery"],
        "Kafka": ["kafka"], "RabbitMQ": ["rabbitmq"], "Spark": ["apache spark", "pyspark"], "Airflow": ["airflow"],
        "dbt": ["=dbt"], "Pandas": ["pandas"], "Tableau": ["tableau"], "Power BI": ["power bi", "powerbi"],
        "Excel": ["=Excel", "microsoft excel", "spreadsheets"], "Data Analysis": ["data analysis", "data analytics"],
    },
    "Cloud & DevOps": {
        "AWS": ["amazon web services", "aws", "ec2", "aws lambda", "cloudformation"], "GCP": ["google cloud platform", "google cloud", "gcp"],
        "Azure": ["microsoft azure", "azure"], "Docker": ["docker", "containerization"], "Kubernetes": ["kubernetes", "k8s", "helm"],
        "Terraform": ["terraform", "infrastructure as code"], "CI/CD": ["ci/cd", "cicd", "continuous integration", "continuous delivery"],
        "GitHub Actions": ["github actions"], "Jenkins": ["jenkins"], "Linux": ["linux"], "Ansible": ["ansible"],
        "Prometheus": ["prometheus", "grafana"], "Datadog": ["datadog"],
    },
    "Architecture": {
        "REST APIs": ["restful", "rest apis", "rest api"], "GraphQL": ["graphql"], "gRPC": ["grpc"],
        "Microservices": ["microservices", "microservice"], "Distributed Systems": ["distributed systems"],
        "Event-Driven Architecture": ["event-driven", "event driven"], "System Design": ["system design"],
        "OAuth2": ["oauth2", "oauth"],
    },
    "Practices": {
        "Git": ["git", "github", "gitlab", "version control"], "Unit Testing": ["unit testing", "unit tests", "tdd", "test-driven"],
        "Pytest": ["pytest"], "Jest": ["jest"], "Cypress": ["cypress", "playwright", "selenium"],
        "Agile/Scrum": ["agile", "scrum", "kanban"], "Jira": ["jira"], "Code Review": ["code review", "code reviews"],
    },
    "AI & ML": {
        "Machine Learning": ["machine learning", "=ML"], "Deep Learning": ["deep learning", "neural networks"],
        "LLMs / AI": ["large language models", "llms", "llm", "prompt engineering", "generative ai", "=AI"],
        "PyTorch": ["pytorch"], "TensorFlow": ["tensorflow"], "NLP": ["natural language processing", "=NLP"],
        "scikit-learn": ["scikit-learn", "sklearn"],
    },
    "Product & Design": {
        "Product Management": ["product management", "product roadmap", "roadmapping"], "User Research": ["user research", "usability testing"],
        "Figma": ["figma"], "UX Design": ["ux design", "ui design", "interaction design"], "A/B Testing": ["a/b testing", "experimentation"],
        "Stakeholder Management": ["stakeholder management", "stakeholders"],
    },
    "Marketing & Sales": {
        "SEO": ["=SEO", "search engine optimization"], "Content Marketing": ["content marketing", "content strategy"],
        "Google Analytics": ["google analytics"], "Salesforce": ["salesforce"], "HubSpot": ["hubspot"],
        "Lead Generation": ["lead generation", "demand generation"], "CRM": ["=CRM"], "Copywriting": ["copywriting"],
        "Paid Media": ["google ads", "paid media", "ppc"],
    },
    "Finance & Ops": {
        "Financial Modeling": ["financial modeling", "financial modelling"], "Accounting": ["accounting", "bookkeeping", "gaap"],
        "QuickBooks": ["quickbooks"], "SAP": ["=SAP"], "Budgeting": ["budgeting", "forecasting"],
        "Project Management": ["project management", "=PMP"], "Supply Chain": ["supply chain", "logistics"],
        "Customer Support": ["customer support", "customer service"],
    },
    "Healthcare & Other": {
        "Patient Care": ["patient care"], "HIPAA": ["=HIPAA"], "EMR/EHR": ["=EMR", "=EHR", "epic systems"],
        "Clinical Research": ["clinical research", "clinical trials"], "Teaching": ["curriculum development", "lesson planning"],
    },
    "Security": {
        "Security Auditing": ["security audit", "penetration testing", "pentest"], "SOC 2": ["soc 2", "soc2"],
        "Application Security": ["application security", "appsec", "owasp"],
    },
}

CLUSTERS = {
    "relational_db": {"PostgreSQL", "MySQL", "SQLite", "SQL"},
    "nosql_db": {"MongoDB", "DynamoDB", "Cassandra", "Redis", "Elasticsearch"},
    "frontend_fw": {"React", "Next.js", "Vue.js", "Angular", "Svelte"},
    "backend_py": {"FastAPI", "Django", "Flask"},
    "backend_js": {"Node.js", "Express"},
    "cloud": {"AWS", "GCP", "Azure"},
    "containers": {"Docker", "Kubernetes"},
    "testing": {"Pytest", "Jest", "Cypress", "Unit Testing"},
    "messaging": {"Kafka", "RabbitMQ"},
    "dl": {"PyTorch", "TensorFlow", "Deep Learning"},
    "bi": {"Tableau", "Power BI", "Excel", "Data Analysis"},
    "crm": {"Salesforce", "HubSpot", "CRM"},
}

# Skills a person plausibly has but forgot to list, versus skills that need real ramp-up time.
ADJACENT = {"Git", "REST APIs", "Docker", "Unit Testing", "CI/CD", "Agile/Scrum", "Code Review", "Linux", "SQL",
            "JSON", "Jira", "GitHub Actions", "OAuth2", "Pytest", "Jest", "HTML/CSS", "Excel", "Google Analytics",
            "Stakeholder Management", "Bash"}
DEEP = {"Kubernetes", "Rust", "Go", "C++", "Terraform", "Kafka", "Cassandra", "Elasticsearch", "Deep Learning",
        "Distributed Systems", "gRPC", "Security Auditing", "Snowflake", "Machine Learning", "System Design",
        "Spark", "PyTorch", "TensorFlow", "Application Security", "Financial Modeling", "Product Management"}

NO_AUTO = {"Express", "Spark", "Excel", "Ruby on Rails", "Teaching", "Budgeting"}
CATEGORY_OF = {}
_patterns = []  # (canonical, compiled regex)

_PRE = r"(?<![A-Za-z0-9_+#.])"
_POST = r"(?![A-Za-z0-9_+#])(?!\.[A-Za-z0-9])"


def _build():
    for cat, skills in ONTOLOGY.items():
        for canon, aliases in skills.items():
            CATEGORY_OF[canon] = cat
            ci, cs = [], []
            for a in aliases + [canon]:
                if a == canon and canon in NO_AUTO:
                    continue
                if a.startswith("="):
                    cs.append(re.escape(a[1:]))
                elif a == canon and canon in ("Go", "Rust", "Java", "Swift", "R", "AI", "ML"):
                    cs.append(re.escape(a))
                else:
                    ci.append(re.escape(a))
            parts = []
            if ci:
                parts.append(re.compile(_PRE + "(?:" + "|".join(sorted(set(ci), key=len, reverse=True)) + ")" + _POST, re.I))
            if cs:
                parts.append(re.compile(_PRE + "(?:" + "|".join(sorted(set(cs), key=len, reverse=True)) + ")" + _POST))
            _patterns.append((canon, parts))


_build()
KNOWN = sorted(CATEGORY_OF)

# "Go" only counts in programming context so "go-to-market" and "go to" never match.
_GO_FALSE = re.compile(r"\bGo(?:-to|\s+(?:to|for|with|through|ahead|live|above|beyond|back|on)\b)")


def extract(text):
    """Return the sorted canonical skills found in text."""
    if not text:
        return []
    found = set()
    for canon, parts in _patterns:
        for p in parts:
            if p.search(text):
                found.add(canon)
                break
    if "Go" in found and "golang" not in text.lower():
        stripped = _GO_FALSE.sub(" ", text)
        if not re.search(r"(?<![A-Za-z0-9_])Go(?=\s*[,/)\]]|\s+(?:developer|engineer|programming|services|backend|microservices|and\b|or\b))"
                         r"|\b(?:in|with|using|and|or|experience in|proficiency in)\s+Go\b"
                         r"|[,/(:]\s*Go\s*(?:$|\n)", stripped, re.M):
            found.discard("Go")
    if "Excel" in found and not re.search(r"\bExcel\b(?!\s+(?:at|in|on|as|under|during|with\s+the)\b)", text) \
            and not re.search(r"microsoft excel|spreadsheets", text, re.I):
        found.discard("Excel")
    return sorted(found)


_PREFERRED = re.compile(r"nice[\s-]to[\s-]have|bonus|preferred|a plus|is a plus|are a plus|good to have|desirable|ideally", re.I)
_REQUIRED = re.compile(r"requirements?|qualifications?|you have|you bring|must[\s-]have|what you.?ll need|required|minimum|about you|who you are", re.I)
_RESP = re.compile(r"responsibilities|what you.?ll do|the role|your role|in this role|day[\s-]to[\s-]day", re.I)


def extract_weighted(text):
    """Return {skill: weight}. Required skills weigh 1.0, responsibilities 0.7, preferred 0.4."""
    weights = {}
    mode, mode_w = "neutral", 0.85
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        short = len(s) < 70
        if _PREFERRED.search(s) and (short or ":" in s[:60]):
            mode, mode_w = "preferred", 0.4
        elif _REQUIRED.search(s) and short:
            mode, mode_w = "required", 1.0
        elif _RESP.search(s) and short:
            mode, mode_w = "resp", 0.7
        line_w = 0.4 if _PREFERRED.search(s) and not short else mode_w
        for sk in extract(s):
            weights[sk] = max(weights.get(sk, 0), line_w)
    return weights


def years_required(text):
    """Largest explicit 'N+ years' requirement found, or None."""
    best = None
    for m in re.finditer(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)\b", text or "", re.I):
        ctx = (text or "")[max(0, m.start() - 40): m.end() + 60].lower()
        if "experience" in ctx or "exp" in ctx:
            n = int(m.group(1))
            if 0 < n <= 25:
                best = n if best is None else max(best, n)
    return best
