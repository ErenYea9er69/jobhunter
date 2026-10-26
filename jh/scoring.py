"""Match scoring. 0 to 100 with no artificial floor, a visible breakdown, and a confidence level."""
import re
import unicodedata

from . import skills as sk
from .util import annualize, days_since, parse_salary

LEVELS = [("intern", 0), ("junior", 1), ("jr", 1), ("entry", 1), ("associate", 1), ("mid", 2), ("senior", 3), ("sr", 3),
          ("lead", 4), ("staff", 4), ("principal", 5), ("head", 5), ("manager", 4), ("director", 5), ("vp", 6),
          ("confirme", 3), ("confirmee", 3), ("stagiaire", 0), ("alternant", 0), ("practicante", 0), ("werkstudent", 0)]
_LEVEL_RE = re.compile(r"\b(" + "|".join(k for k, _ in LEVELS) + r")\b\.?", re.I)
_LEVEL_MAP = dict(LEVELS)

TITLE_SYNONYMS = {
    "developer": "engineer", "programmer": "engineer", "swe": "engineer", "sde": "engineer", "dev": "engineer",
    "fullstack": "full stack", "full-stack": "full stack", "frontend": "front end", "front-end": "front end",
    "backend": "back end", "back-end": "back end", "devops": "platform", "sre": "platform",
    "sr": "senior", "jr": "junior", "mgr": "manager", "ux": "design", "ui": "design",
    # French
    "developpeur": "engineer", "developpeuse": "engineer", "ingenieur": "engineer", "ingenieure": "engineer",
    "confirme": "senior", "confirmee": "senior", "stage": "intern", "stagiaire": "intern", "alternance": "intern", "alternant": "intern",
    # Spanish
    "desarrollador": "engineer", "desarrolladora": "engineer", "ingeniero": "engineer", "ingeniera": "engineer",
    "practicante": "intern", "pasante": "intern",
    # German
    "entwickler": "engineer", "entwicklerin": "engineer", "softwareentwickler": "engineer",
    "praktikant": "intern", "werkstudent": "intern",
}
STOP = {
    "the", "and", "of", "for", "a", "an", "in", "at", "to", "ii", "iii", "i", "remote", "us", "uk", "emea",
    "senior", "junior", "lead", "staff", "principal", "sr", "jr", "intern", "associate", "mid",
    "fh", "hf", "f/h", "h/f", "mwd", "m/w/d", "mfd", "m/f/d", "wmd", "w/m/d", "cdi", "cdd", "irc", "ref"
}


def title_tokens(title):
    raw = unicodedata.normalize('NFKD', title or '').encode('ascii', 'ignore').decode('utf-8')
    t = raw.lower().replace("/", " ").replace(",", " ").replace("(", " ").replace(")", " ").replace("-", " ")
    for k, v in TITLE_SYNONYMS.items():
        t = re.sub(rf"(?<![a-z]){re.escape(k)}(?![a-z])", v, t)
    return {w for w in re.findall(r"[a-z+#]+", t) if w not in STOP and len(w) > 1 and not re.match(r"^irc\d+$", w)}


def level_of(title):
    raw = unicodedata.normalize('NFKD', title or '').encode('ascii', 'ignore').decode('utf-8')
    m = _LEVEL_RE.search(raw)
    return _LEVEL_MAP[m.group(1).lower()] if m else None


def years_to_level(y):
    return 0 if y < 1 else 1 if y < 3 else 2 if y < 5 else 3 if y < 8 else 4


SENIORITY_MODIFIERS = [
    ("senior", "Senior"), ("sr", "Senior"), ("lead", "Lead"), ("staff", "Staff"),
    ("principal", "Principal"), ("junior", "Junior"),
    ("jr", "Junior"), ("entry", "Entry-level"), ("associate", "Associate"),
    ("intern", "Intern")
]

DISCIPLINES = {
    "fullstack": {
        "patterns": [r"full\s*stack", r"fullstack", r"mern", r"lamp"],
        "primary": ["Full Stack Developer", "Full Stack Engineer"],
        "laterals": ["Backend Developer", "Frontend Developer", "Software Engineer", "Web Developer"],
    },
    "backend": {
        "patterns": [r"back\s*end", r"backend", r"api\s+engineer", r"server\s*side", r"microservices"],
        "primary": ["Backend Engineer", "Backend Developer"],
        "laterals": ["Software Engineer", "API Engineer", "Full Stack Developer", "Platform Engineer"],
    },
    "frontend": {
        "patterns": [r"front\s*end", r"frontend", r"ui\s+engineer", r"client\s*side"],
        "primary": ["Frontend Engineer", "Frontend Developer"],
        "laterals": ["UI Engineer", "Web Developer", "Software Engineer", "Full Stack Developer"],
    },
    "ai_ml": {
        "patterns": [r"machine\s*learning", r"\bml\b", r"\bai\b", r"deep\s*learning", r"data\s*scientist", r"\bnlp\b", r"computer\s*vision"],
        "primary": ["Machine Learning Engineer", "AI Engineer", "Data Scientist"],
        "laterals": ["Applied AI Engineer", "Deep Learning Engineer", "MLOps Engineer", "Python Engineer", "Software Engineer"],
    },
    "data_eng": {
        "patterns": [r"data\s*engineer", r"analytics\s*engineer", r"big\s*data", r"\betl\b", r"database\s*engineer"],
        "primary": ["Data Engineer", "Analytics Engineer"],
        "laterals": ["Big Data Engineer", "Database Developer", "Backend Engineer", "Python Developer"],
    },
    "devops_cloud": {
        "patterns": [r"devops", r"cloud\s*engineer", r"\bsre\b", r"site\s*reliability", r"platform\s*engineer", r"infrastructure"],
        "primary": ["DevOps Engineer", "Cloud Engineer", "Site Reliability Engineer (SRE)"],
        "laterals": ["Platform Engineer", "Infrastructure Engineer", "Systems Engineer"],
    },
    "mobile": {
        "patterns": [r"mobile", r"\bios\b", r"android", r"react\s*native", r"flutter", r"swift", r"kotlin"],
        "primary": ["Mobile Developer", "Mobile Engineer"],
        "laterals": ["iOS Developer", "Android Developer", "Frontend Developer", "Software Engineer"],
    },
    "qa": {
        "patterns": [r"\bqa\b", r"quality\s*assurance", r"\bsdet\b", r"test\s*automation", r"software\s*test"],
        "primary": ["QA Engineer", "SDET", "Test Automation Engineer"],
        "laterals": ["QA Automation Specialist", "Software Engineer in Test"],
    },
    "security": {
        "patterns": [r"security", r"cyber", r"appsec", r"infosec", r"\bsoc\b"],
        "primary": ["Security Engineer", "Cybersecurity Specialist"],
        "laterals": ["Application Security Engineer", "Information Security Analyst"],
    },
    "product": {
        "patterns": [r"product\s*manag", r"product\s*owner", r"technical\s*product", r"scrum\s*master"],
        "primary": ["Product Manager", "Technical Product Manager"],
        "laterals": ["Product Owner", "Project Manager", "Scrum Master"],
    },
    "design": {
        "patterns": [r"ui/ux", r"ux\s*design", r"product\s*design", r"user\s*experience", r"ui\s*design"],
        "primary": ["Product Designer", "UI/UX Designer"],
        "laterals": ["UX Designer", "UI Designer", "UX Researcher"],
    },
    "data_analytics": {
        "patterns": [r"data\s*analyst", r"business\s*analyst", r"bi\s*analyst", r"analytics\s*specialist"],
        "primary": ["Data Analyst", "Business Analyst"],
        "laterals": ["BI Analyst", "Analytics Specialist", "Operations Analyst"],
    },
}

TECH_SPECIALIZATIONS = [
    ("Python", ["Python Developer", "Python Engineer"]),
    ("React", ["React Developer", "React Engineer"]),
    ("Node.js", ["Node.js Developer", "Node.js Backend Engineer"]),
    ("TypeScript", ["TypeScript Developer", "TypeScript Engineer"]),
    ("JavaScript", ["JavaScript Developer", "Full Stack JavaScript Developer"]),
    ("Go", ["Go Engineer", "Golang Developer"]),
    ("Rust", ["Rust Engineer", "Systems Engineer"]),
    ("Java", ["Java Developer", "Java Backend Engineer"]),
    ("C#", ["C# Developer", ".NET Developer"]),
    ("C++", ["C++ Engineer", "Systems Software Engineer"]),
    ("Ruby", ["Ruby on Rails Developer", "Ruby Developer"]),
    ("PHP", ["PHP Developer", "Full Stack PHP Developer"]),
    ("Kotlin", ["Kotlin Developer", "Android Developer"]),
    ("Swift", ["iOS Developer", "Swift Engineer"]),
    ("SQL", ["Database Developer", "SQL Developer"]),
    ("AWS", ["AWS Cloud Engineer"]),
    ("Kubernetes", ["Kubernetes Engineer", "DevOps Engineer"]),
    ("Docker", ["DevOps Engineer"]),
    ("PyTorch", ["Machine Learning Engineer", "PyTorch Engineer"]),
    ("TensorFlow", ["Machine Learning Engineer"]),
    ("LLMs / AI", ["AI Engineer", "LLM Engineer"]),
    ("Figma", ["Product Designer", "UI/UX Designer"]),
    ("Salesforce", ["Salesforce Developer", "Salesforce Administrator"]),
]


def detect_seniority(title, years=0):
    t = (title or "").lower()
    for raw, canonical in SENIORITY_MODIFIERS:
        if re.search(rf"\b{raw}\b", t):
            return canonical
    if years >= 5:
        return "Senior"
    if 0 < years <= 1.5:
        return "Junior"
    return ""


def derive_target_roles(profile):
    """Return all qualified roles for candidate based on target title, experience, and tech stack."""
    profile = profile or {}
    target = (profile.get("target_title") or "").strip()
    years = float(profile.get("years_of_experience") or 0)
    skills = profile.get("skills", []) or []
    skills_lower = {s.lower() for s in skills if isinstance(s, str)}
    skills_set = set(skills)

    # Experience past roles
    exp_roles = []
    for exp in profile.get("experience", [])[:4]:
        if isinstance(exp, dict):
            r = (exp.get("role") or "").strip()
            if r and r.lower() not in [x.lower() for x in exp_roles]:
                exp_roles.append(r)

    # Detect Seniority
    seniority = detect_seniority(target, years)

    # Detect Disciplines from Title, Experience, and Skills
    detected_disciplines = []
    combined_titles = " ".join([target] + exp_roles).lower()

    for disc_key, disc_cfg in DISCIPLINES.items():
        for pat in disc_cfg["patterns"]:
            if re.search(pat, combined_titles):
                detected_disciplines.append(disc_key)
                break

    # If no discipline detected from title (or title empty/vague): infer from skill gravity!
    if not detected_disciplines and skills:
        cat_counts = {}
        for s in skills:
            if isinstance(s, str):
                cat = sk.CATEGORY_OF.get(s, "Other")
                cat_counts[cat] = cat_counts.get(cat, 0) + 1

        # Specific tool gravity overrides
        design_skills = {"figma", "ux design", "ui design", "user research", "product design"}
        analytics_skills = {"tableau", "power bi", "excel", "data analysis", "bi analyst", "google analytics"}
        mobile_skills = {"swift", "kotlin", "react native", "flutter", "ios", "android"}
        qa_skills = {"cypress", "playwright", "selenium", "unit testing", "test automation"}

        if any(s.lower() in design_skills for s in skills if isinstance(s, str)):
            detected_disciplines.append("design")
        elif any(s.lower() in analytics_skills for s in skills if isinstance(s, str)) and cat_counts.get("Backend", 0) == 0:
            detected_disciplines.append("data_analytics")
        elif any(s.lower() in mobile_skills for s in skills if isinstance(s, str)):
            detected_disciplines.append("mobile")
        elif cat_counts.get("AI & ML", 0) >= 2:
            detected_disciplines.append("ai_ml")
        elif cat_counts.get("Cloud & DevOps", 0) >= 3:
            detected_disciplines.append("devops_cloud")
        elif cat_counts.get("Frontend", 0) >= 2 and cat_counts.get("Backend", 0) >= 2:
            detected_disciplines.append("fullstack")
        elif cat_counts.get("Frontend", 0) >= 2:
            detected_disciplines.append("frontend")
        elif cat_counts.get("Backend", 0) >= 2 or cat_counts.get("Architecture", 0) >= 2:
            detected_disciplines.append("backend")
        elif cat_counts.get("Data", 0) >= 2:
            detected_disciplines.append("data_eng")
        elif cat_counts.get("Product & Design", 0) >= 2:
            detected_disciplines.append("product")
        elif cat_counts.get("Languages", 0) >= 1:
            detected_disciplines.append("backend")

    # If still none and target exists, default to backend/software engineering
    if not detected_disciplines and target:
        detected_disciplines = ["fullstack" if "full" in target.lower() else "backend"]

    # Assemble Roles with hierarchy
    roles_ordered = []
    seen = set()

    def add_role(role_name, apply_sen=False):
        clean = (role_name or "").strip()
        if not clean:
            return
        if apply_sen and seniority and not any(re.search(rf"\b{raw}\b", clean.lower()) for raw, _ in SENIORITY_MODIFIERS):
            clean = f"{seniority} {clean}"
        k = clean.lower()
        if k not in seen:
            seen.add(k)
            roles_ordered.append(clean)

    # 1. Exact user target title if present
    if target:
        add_role(target)

    # 2. Past roles from experience
    for r in exp_roles:
        add_role(r)

    # 3. Primary & lateral roles for all detected disciplines
    for d in detected_disciplines:
        cfg = DISCIPLINES.get(d)
        if not cfg:
            continue
        for p in cfg["primary"]:
            add_role(p, apply_sen=bool(seniority and seniority != "Entry-level"))
            add_role(p, apply_sen=False)
        for lat in cfg["laterals"]:
            add_role(lat, apply_sen=bool(seniority and seniority != "Entry-level"))
            add_role(lat, apply_sen=False)

    # 4. Tech stack specializations matching user's actual skills
    for tech_name, spec_roles in TECH_SPECIALIZATIONS:
        if tech_name in skills_set or tech_name.lower() in skills_lower or any(tech_name.lower() in s.lower() for s in skills if isinstance(s, str)):
            for sr in spec_roles:
                add_role(sr, apply_sen=bool(seniority == "Senior"))
                add_role(sr, apply_sen=False)

    return roles_ordered


NON_SOFTWARE_DISCIPLINES = {
    "civil", "mechanical", "electrical", "chemical", "structural", "petroleum", "biomedical",
    "aerospace", "aeronautical", "mining", "locomotive", "geotechnical", "audio", "acoustic",
    "nuclear", "marine", "hardware", "hvac", "environmental"
}

SPECIALIZED_LANGUAGES = {
    "python", "java", "typescript", "javascript", "rust", "golang", "go", "swift", "kotlin", "ruby", "php", "scala", "c++", "c#",
    "salesforce", "sap", "flutter", "react native", "solidity"
}


def _title_score(job_title, profile):
    candidates = derive_target_roles(profile)
    jt = title_tokens(job_title)
    if not jt:
        return 0.0

    cand_skills = {s.lower() for s in profile.get("skills", [])}

    # Reject non-software engineering disciplines (e.g. Civil Engineer, Petroleum Engineer)
    # when candidate is in software/tech
    if any(w in jt for w in NON_SOFTWARE_DISCIPLINES) and not any(w in cand_skills for w in NON_SOFTWARE_DISCIPLINES):
        return 0.05

    is_engineer = "engineer" in jt
    is_job_backend = "back" in jt and "end" in jt
    is_job_frontend = "front" in jt and "end" in jt
    is_job_fullstack = "full" in jt and "stack" in jt

    best = 0.0
    for i, c in enumerate(x for x in candidates if x):
        ct = title_tokens(c)
        if not ct or not jt:
            continue
        overlap = len(ct & jt) / len(ct | jt)
        contain = len(ct & jt) / min(len(ct), len(jt))
        s = 0.55 * overlap + 0.45 * contain

        is_cand_fullstack = "full" in ct and "stack" in ct
        is_cand_backend = "back" in ct and "end" in ct
        is_cand_frontend = "front" in ct and "end" in ct

        # Role family affinity:
        # Full stack candidates are fully qualified for Backend, Frontend, and Software Engineering
        if is_cand_fullstack and is_engineer:
            if is_job_backend or is_job_frontend:
                s = max(s, 0.88)
            elif is_job_fullstack:
                s = max(s, 1.0)
            elif any(w in jt for w in ("software", "web", "application", "platform", "systems", "cloud", "api", "tech", "code", "dev")):
                s = max(s, 0.90)
        elif is_cand_backend and is_engineer:
            if is_job_fullstack or ("software" in jt):
                s = max(s, 0.85)
        elif is_cand_frontend and is_engineer:
            if is_job_fullstack or ("web" in jt) or ("software" in jt):
                s = max(s, 0.85)

        # Specialized language alignment: job title specifies a distinct language
        title_langs = {w for w in jt if w in SPECIALIZED_LANGUAGES}
        if title_langs:
            if any(l in cand_skills for l in title_langs):
                s = max(s, 0.92 if is_cand_fullstack else 0.88)
            else:
                s *= 0.65

        weight = 1.0 if i < 2 else 0.90
        best = max(best, s * weight)
    return best


def _mode_of(job):
    m = (job.get("work_mode") or "").lower()
    loc = (job.get("location") or "").lower()
    if "remote" in m or "remote" in loc or "anywhere" in loc or "worldwide" in loc:
        return "remote"
    if "hybrid" in m or "hybrid" in loc:
        return "hybrid"
    if m in ("on-site", "onsite") or "on-site" in loc or "onsite" in loc:
        return "onsite"
    return "unknown"


US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia",
    "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt",
    "va", "wa", "wv", "wi", "wy", "dc"
}

US_MAJOR_CITIES = {
    "seattle", "san francisco", "new york", "nyc", "boston", "chicago", "los angeles", "austin",
    "denver", "atlanta", "miami", "silicon valley", "bay area", "dallas", "houston", "phoenix",
    "philadelphia", "san diego", "salt lake city", "portland", "washington"
}

CANADIAN_PROVINCES = {
    "on", "bc", "qc", "ab", "mb", "sk", "ns", "nb", "nl", "pe",
    "ontario", "british columbia", "quebec", "alberta"
}

COUNTRY_MAP = [
    # North Africa & MENA (including Tunisia, Morocco, Algeria, Egypt, Gulf)
    (re.compile(r"\b(tunisia|tunisie|tunis|sousse|sfax|bizerte|ariana|kairouan|monastir|gabes|nabeul|carthage|marsa|lac 1|lac 2|tn\b)\b", re.I), "Tunisia"),
    (re.compile(r"\b(morocco|maroc|casablanca|rabat|marrakech|tangier|tanger|fes|agadir|meknes|oujda|ma\b)\b", re.I), "Morocco"),
    (re.compile(r"\b(algeria|algérie|algiers|alger|oran|constantine|annaba|blida|batna|setif|dz\b)\b", re.I), "Algeria"),
    (re.compile(r"\b(egypt|égypte|cairo|alexandria|giza|sharm|mansoura|tanta|eg\b)\b", re.I), "Egypt"),
    (re.compile(r"\b(libya|tripoli|benghazi|misrata|ly\b)\b", re.I), "Libya"),
    (re.compile(r"\b(saudi arabia|saudi|ksa|riyadh|jeddah|dammam|khobar|mecca|medina|sa\b)\b", re.I), "Saudi Arabia"),
    (re.compile(r"\b(uae|united arab emirates|dubai|abu dhabi|sharjah|ajman|ras al khaimah|ae\b)\b", re.I), "UAE"),
    (re.compile(r"\b(qatar|doha|al rayyan|qa\b)\b", re.I), "Qatar"),
    (re.compile(r"\b(kuwait|kuwait city|salmiya|kw\b)\b", re.I), "Kuwait"),
    (re.compile(r"\b(bahrain|manama|muharraq|bh\b)\b", re.I), "Bahrain"),
    (re.compile(r"\b(oman|muscat|salalah|om\b)\b", re.I), "Oman"),
    (re.compile(r"\b(jordan|amman|zarqa|irbid|jo\b)\b", re.I), "Jordan"),
    (re.compile(r"\b(lebanon|beirut|tripoli|sidon|lb\b)\b", re.I), "Lebanon"),
    (re.compile(r"\b(iraq|baghdad|erbil|basra|sulaymaniyah|iq\b)\b", re.I), "Iraq"),
    (re.compile(r"\b(turkey|türkiye|istanbul|ankara|izmir|bursa|antalya|tr\b)\b", re.I), "Turkey"),

    # North America
    (re.compile(r"\b(united states|usa|u\.s\.a?|u\.s\b|us\b)\b", re.I), "United States"),
    (re.compile(r"\b(canada|can\b|toronto|vancouver|montreal|ottawa|calgary|edmonton)\b", re.I), "Canada"),
    (re.compile(r"\b(mexico|méxico|mexico city|cdmx|guadalajara|monterrey|mx\b)\b", re.I), "Mexico"),

    # Europe
    (re.compile(r"\b(united kingdom|great britain|england|scotland|wales|london|manchester|birmingham|edinburgh|glasgow|uk\b|u\.k\b|gb\b)\b", re.I), "United Kingdom"),
    (re.compile(r"\b(germany|deutschland|berlin|munich|münchen|frankfurt|hamburg|cologne|köln|stuttgart|de\b)\b", re.I), "Germany"),
    (re.compile(r"\b(france|paris|lyon|marseille|toulouse|bordeaux|nantes|lille|strasbourg|fr\b)\b", re.I), "France"),
    (re.compile(r"\b(netherlands|holland|amsterdam|rotterdam|the hague|utrecht|eindhoven|nl\b)\b", re.I), "Netherlands"),
    (re.compile(r"\b(spain|españa|madrid|barcelona|valencia|seville|malaga|bilbao|es\b)\b", re.I), "Spain"),
    (re.compile(r"\b(italy|italia|rome|roma|milan|milano|turin|naples|bologna|florence|it\b)\b", re.I), "Italy"),
    (re.compile(r"\b(switzerland|schweiz|suisse|zurich|zürich|geneva|genève|lausanne|basel|ch\b)\b", re.I), "Switzerland"),
    (re.compile(r"\b(poland|polska|warsaw|warszawa|krakow|kraków|wroclaw|gdansk|pl\b)\b", re.I), "Poland"),
    (re.compile(r"\b(sweden|sverige|stockholm|gothenburg|malmö|se\b)\b", re.I), "Sweden"),
    (re.compile(r"\b(norway|norge|oslo|bergen|trondheim|no\b)\b", re.I), "Norway"),
    (re.compile(r"\b(denmark|danmark|copenhagen|københavn|aarhus|dk\b)\b", re.I), "Denmark"),
    (re.compile(r"\b(finland|suomi|helsinki|espoo|tampere|fi\b)\b", re.I), "Finland"),
    (re.compile(r"\b(ireland|dublin|cork|galway|limerick|ie\b)\b", re.I), "Ireland"),
    (re.compile(r"\b(portugal|lisbon|lisboa|porto|braga|pt\b)\b", re.I), "Portugal"),
    (re.compile(r"\b(austria|österreich|vienna|wien|salzburg|graz|at\b)\b", re.I), "Austria"),
    (re.compile(r"\b(belgium|belgique|belgië|brussels|bruxelles|antwerp|gent|be\b)\b", re.I), "Belgium"),
    (re.compile(r"\b(czech republic|czechia|cesko|prague|praha|brno|cz\b)\b", re.I), "Czech Republic"),
    (re.compile(r"\b(romania|românia|bucharest|bucuresti|cluj|timisoara|iasi|ro\b)\b", re.I), "Romania"),
    (re.compile(r"\b(greece|hellas|athens|thessaloniki|gr\b)\b", re.I), "Greece"),
    (re.compile(r"\b(hungary|magyarország|budapest|debrecen|hu\b)\b", re.I), "Hungary"),
    (re.compile(r"\b(croatia|hrvatska|zagreb|split|hr\b)\b", re.I), "Croatia"),
    (re.compile(r"\b(bulgaria|sofia|plovdiv|varna|bg\b)\b", re.I), "Bulgaria"),
    (re.compile(r"\b(serbia|srbija|belgrade|beograd|novi sad|rs\b)\b", re.I), "Serbia"),
    (re.compile(r"\b(slovakia|slovensko|bratislava|kosice|sk\b)\b", re.I), "Slovakia"),
    (re.compile(r"\b(ukraine|kyiv|kiev|lviv|odesa|ua\b)\b", re.I), "Ukraine"),
    (re.compile(r"\b(estonia|eesti|tallinn|tartu|ee\b)\b", re.I), "Estonia"),
    (re.compile(r"\b(latvia|latvija|riga|lv\b)\b", re.I), "Latvia"),
    (re.compile(r"\b(lithuania|lietuva|vilnius|kaunas|lt\b)\b", re.I), "Lithuania"),
    (re.compile(r"\b(cyprus|nicosia|limassol|cy\b)\b", re.I), "Cyprus"),
    (re.compile(r"\b(malta|valletta|mt\b)\b", re.I), "Malta"),
    (re.compile(r"\b(luxembourg|lu\b)\b", re.I), "Luxembourg"),
    (re.compile(r"\b(iceland|reykjavik|is\b)\b", re.I), "Iceland"),

    # Asia & Oceania
    (re.compile(r"\b(india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|noida|gurugram|chennai|in\b)\b", re.I), "India"),
    (re.compile(r"\b(pakistan|karachi|lahore|islamabad|rawalpindi|pk\b)\b", re.I), "Pakistan"),
    (re.compile(r"\b(bangladesh|dhaka|chittagong|bd\b)\b", re.I), "Bangladesh"),
    (re.compile(r"\b(sri lanka|colombo|lk\b)\b", re.I), "Sri Lanka"),
    (re.compile(r"\b(singapore|sg\b)\b", re.I), "Singapore"),
    (re.compile(r"\b(japan|nippon|tokyo|osaka|kyoto|yokohama|fukuoka|jp\b)\b", re.I), "Japan"),
    (re.compile(r"\b(south korea|korea|seoul|busan|incheon|kr\b)\b", re.I), "South Korea"),
    (re.compile(r"\b(china|beijing|shanghai|shenzhen|hangzhou|guangzhou|cn\b)\b", re.I), "China"),
    (re.compile(r"\b(taiwan|taipei|tw\b)\b", re.I), "Taiwan"),
    (re.compile(r"\b(hong kong|hk\b)\b", re.I), "Hong Kong"),
    (re.compile(r"\b(malaysia|kuala lumpur|penang|my\b)\b", re.I), "Malaysia"),
    (re.compile(r"\b(indonesia|jakarta|surabaya|bandung|bali|id\b)\b", re.I), "Indonesia"),
    (re.compile(r"\b(vietnam|việt nam|hanoi|ho chi minh|saigon|da nang|vn\b)\b", re.I), "Vietnam"),
    (re.compile(r"\b(philippines|manila|cebu|davao|ph\b)\b", re.I), "Philippines"),
    (re.compile(r"\b(thailand|bangkok|chiang mai|phuket|th\b)\b", re.I), "Thailand"),
    (re.compile(r"\b(australia|sydney|melbourne|brisbane|perth|adelaide|au\b|aus\b)\b", re.I), "Australia"),
    (re.compile(r"\b(new zealand|auckland|wellington|christchurch|nz\b)\b", re.I), "New Zealand"),

    # Latin America
    (re.compile(r"\b(brazil|brasil|sao paulo|são paulo|rio de janeiro|curitiba|florianopolis|br\b)\b", re.I), "Brazil"),
    (re.compile(r"\b(argentina|buenos aires|cordoba|rosario|ar\b)\b", re.I), "Argentina"),
    (re.compile(r"\b(colombia|bogota|bogotá|medellin|medellín|cali|co\b)\b", re.I), "Colombia"),
    (re.compile(r"\b(chile|santiago|valparaiso|cl\b)\b", re.I), "Chile"),
    (re.compile(r"\b(peru|perú|lima|arequipa|pe\b)\b", re.I), "Peru"),
    (re.compile(r"\b(uruguay|montevideo|uy\b)\b", re.I), "Uruguay"),
    (re.compile(r"\b(costa rica|san jose|cr\b)\b", re.I), "Costa Rica"),
    (re.compile(r"\b(panama|panamá|panama city|pa\b)\b", re.I), "Panama"),

    # Sub-Saharan Africa
    (re.compile(r"\b(south africa|johannesburg|cape town|durban|pretoria|za\b)\b", re.I), "South Africa"),
    (re.compile(r"\b(nigeria|lagos|abuja|ibadan|ng\b)\b", re.I), "Nigeria"),
    (re.compile(r"\b(kenya|nairobi|mombasa|ke\b)\b", re.I), "Kenya"),
    (re.compile(r"\b(ghana|accra|kumasi|gh\b)\b", re.I), "Ghana"),
    (re.compile(r"\b(ethiopia|addis ababa|et\b)\b", re.I), "Ethiopia"),
    (re.compile(r"\b(rwanda|kigali|rw\b)\b", re.I), "Rwanda"),
    (re.compile(r"\b(senegal|dakar|sn\b)\b", re.I), "Senegal"),
    (re.compile(r"\b(uganda|kampala|ug\b)\b", re.I), "Uganda"),
    (re.compile(r"\b(tanzania|dar es salaam|tz\b)\b", re.I), "Tanzania"),

    # Worldwide & Global
    (re.compile(r"\b(worldwide|anywhere|global|everywhere|all countries|work from anywhere|wfa|remote - worldwide|international)\b", re.I), "Worldwide"),
]


def classify_job_country(location, title="", description=""):
    loc = (location or "").strip()
    if not loc or loc.lower() in ("remote", "unknown", "work from home", "remote - anywhere"):
        return "Worldwide"

    parts = [p.strip() for p in loc.split(",") if p.strip()]
    if parts:
        last = parts[-1].strip().lower()
        if last in US_STATES:
            return "United States"
        if last in CANADIAN_PROVINCES:
            return "Canada"
        if len(parts) >= 2 and parts[-2].strip().lower() in US_STATES:
            return "United States"
        if len(parts) >= 2 and parts[-2].strip().lower() in CANADIAN_PROVINCES:
            return "Canada"

    loc_lower = loc.lower()
    if any(city in loc_lower for city in US_MAJOR_CITIES):
        return "United States"

    for pat, country in COUNTRY_MAP:
        if pat.search(loc):
            return country

    if "worldwide" in loc_lower or "anywhere" in loc_lower or "global" in loc_lower:
        return "Worldwide"

    if parts:
        cleaned_last = re.sub(r"[^A-Za-z\s-]", "", parts[-1]).strip().title()
        if len(cleaned_last) >= 3 and cleaned_last.lower() not in ("remote", "hybrid", "onsite", "area", "region", "city"):
            return cleaned_last

    return "Worldwide"


def classify_company_stage(job):
    from .pipeline import is_famous_company
    comp = job.get("company", "")
    if is_famous_company(comp):
        return "big_tech"
    tags = [t.lower() for t in (job.get("tags") or [])]
    text = f"{job.get('title', '')} {comp} {(job.get('description', '') or '')[:500]}".lower()
    if "startup" in tags or "(yc" in comp.lower() or re.search(r"\b(startup|early-stage|early stage|founding engineer|founding developer|stealth|seed stage|series a|series b)\b", text):
        return "startup"
    src_name = job.get("source", "")
    if src_name in ("Hacker News", "RemoteOK", "Himalayas"):
        return "startup"
    return "mid_tech"


def classify_job_seniority(title, text=""):
    t = f"{title or ''} {(text or '')[:350]}".lower()
    if re.search(r"\b(intern|internship|co-op|apprentice)\b", t):
        return "intern"
    if re.search(r"\b(lead|staff|principal|director|head of|vp|architect|founding)\b", t):
        return "lead_staff"
    if re.search(r"\b(senior|sr\.?|sr\b)\b", t):
        return "senior"
    if re.search(r"\b(junior|jr\.?|jr\b|entry|associate|graduate|new grad)\b", t):
        return "junior"
    return "mid"


def score_job(job, profile):
    # Structured qualifications & preferred qualifications extraction
    req_quals = job.get("qualifications") or []
    pref_quals = job.get("preferred_qualifications") or []
    resps = job.get("responsibilities") or []
    req_text = "\n".join(req_quals) if isinstance(req_quals, list) else str(req_quals)
    pref_text = "\n".join(pref_quals) if isinstance(pref_quals, list) else str(pref_quals)
    resp_text = "\n".join(resps) if isinstance(resps, list) else str(resps)

    all_texts = [
        job.get("title", ""),
        job.get("description", ""),
        req_text,
        pref_text,
        resp_text,
        " ".join(job.get("tags", []) or [])
    ]
    text = "\n".join(t for t in all_texts if t)
    weights = sk.extract_weighted(text)
    cand = set(profile.get("skills", []))
    cand_l = {c.lower() for c in cand}

    req_skills = set(sk.extract(req_text)) if req_text else set()
    pref_skills = set(sk.extract(pref_text)) if pref_text else set()

    # Boost weights for explicit must-have requirements
    for s in req_skills:
        weights[s] = max(weights.get(s, 0.0), 1.0)

    # Add or calibrate weights for skills that appear in preferred qualifications
    for s in pref_skills:
        if s not in req_skills:
            if s in weights:
                weights[s] = min(weights[s], 0.65)
            else:
                weights[s] = 0.65

    matched = sorted(s for s in weights if s in cand or s.lower() in cand_l)
    missing = sorted(s for s in weights if s not in matched)

    # Specific subsets for deep matching
    matched_required = sorted(s for s in matched if s in req_skills)
    missing_required = sorted(s for s in missing if s in req_skills)
    bonus_matches = sorted(s for s in matched if s in pref_skills and s not in req_skills)

    # Affinity: a sister technology in the same cluster earns partial credit (Postgres for MySQL).
    affinity, credit = [], {}
    for m in missing:
        for cname, members in sk.CLUSTERS.items():
            if m in members and members & cand:
                have = sorted(members & cand)[:2]
                affinity.append(f"{m} ~ {', '.join(have)}")
                credit[m] = 0.45
                break

    # If candidate matches primary core domain tech, grant adjacent tooling credit for universal dev tools/practices
    if matched or (title_ratio := _title_score(job.get("title", ""), profile)) >= 0.7:
        for m in missing:
            if m not in credit and m in sk.ADJACENT:
                credit[m] = 0.45

    title_ratio = _title_score(job.get("title", ""), profile)
    title_pts = title_ratio * 20

    total_w = sum(weights.values())
    desc_len = len(job.get("description", "") or "")
    is_enriched = bool(job.get("enriched"))
    raw_match_w = sum(weights[s] for s in matched) + sum(weights[s] * credit.get(s, 0.0) for s in credit)

    if desc_len < 400 and not is_enriched:
        # Sparse/unenriched posting: requirements are incomplete.
        # 1 observed title skill is NOT 100% of an employer's requirements.
        # Smooth against an expected requirement baseline horizon.
        expected_w = max(total_w, 4.5)
        unobserved_w = expected_w - total_w
        if matched and title_ratio >= 0.6:
            unobserved_credit = unobserved_w * (0.35 + 0.22 * title_ratio)
        elif matched:
            unobserved_credit = unobserved_w * 0.25
        elif total_w == 0:
            unobserved_credit = unobserved_w * (0.36 + 0.20 * title_ratio)
        else:
            unobserved_credit = unobserved_w * (0.12 * title_ratio)
        cov = (raw_match_w + unobserved_credit) / expected_w
        skill_pts = cov * 50
    elif total_w > 0:
        cov = raw_match_w / total_w
        skill_pts = min(50.0, cov * 50)
    else:
        skill_pts = 18 + (title_ratio * 10)  # unknown requirements: neutral baseline + title alignment boost

    # Bonus points for preferred qualifications
    bonus_pts = min(4.0, len(bonus_matches) * 1.5)

    notes = []

    # Highlight structured requirements in notes
    if matched_required:
        notes.append(f"Matches {len(matched_required)} core requirement{'s' if len(matched_required) > 1 else ''} ({', '.join(matched_required[:3])})")
    if missing_required:
        notes.append(f"Core requirement gap: {', '.join(missing_required[:3])}")
    if bonus_matches:
        notes.append(f"Bonus qualification match: {', '.join(bonus_matches[:3])}")

    # Core required skill verification (must-have requirements - excluding universal adjacent tools)
    core_penalty = 0
    core_required = [s for s, w in weights.items() if w >= 0.95 and s not in sk.ADJACENT]
    if len(core_required) >= 2:
        matched_core = [s for s in core_required if s in matched or s in credit]
        if not matched_core:
            core_penalty = 22
            missing_core = [s for s in core_required if s in missing and s not in credit]
            notes.append("Missing core required technologies: " + ", ".join(missing_core[:3]))

    # Seniority and leveling alignment
    sen_pts = 7.0
    sen_penalty = 0
    jl, y = level_of(job.get("title", "")), float(profile.get("years_of_experience") or 0)
    job_sen_class = classify_job_seniority(job.get("title", ""), text)
    if jl is None:
        jl = 0 if job_sen_class == "intern" else 1 if job_sen_class == "junior" else 3 if job_sen_class == "senior" else 4 if job_sen_class == "lead_staff" else 2

    cl = years_to_level(y) if y else (level_of(profile.get("target_title", "")) or 2)
    need_yrs = sk.years_required(job.get("description", ""))

    level_diff = jl - cl
    if level_diff >= 3 or (need_yrs and y and y <= need_yrs - 4):
        sen_pts = 0
        sen_penalty = 25
        notes.append(f"Seniority level ({job_sen_class.replace('_', ' ').title()}{f' / {need_yrs}+ yrs' if need_yrs else ''}) is significantly above your experience level ({int(y)} yrs).")
    elif level_diff == 2 or (need_yrs and y and y <= need_yrs - 2):
        sen_pts = 2
        sen_penalty = 12
        notes.append(f"Requires higher seniority level ({f'{need_yrs}+ yrs required vs your {int(y)} yrs' if need_yrs else 'senior level'}).")
    elif level_diff <= -3:
        sen_pts = 1
        sen_penalty = 20
        notes.append("Entry/internship role intended for students or new graduates.")
    elif level_diff in (0, 1, -1):
        sen_pts = 10 if level_diff == 0 else 8
        sen_penalty = 0
    else:
        sen_pts = 5
        sen_penalty = 0

    # Work mode, geographic and location compatibility
    jm, cm = _mode_of(job), (profile.get("work_mode") or "Any").lower()
    prefs = [p.lower() for p in profile.get("preferred_locations", []) if p and p.lower() not in ("remote", "worldwide")]
    loc = (job.get("location") or "").lower()

    # Detect candidate country from preferred_locations and home location
    cand_loc_str = " ".join(profile.get("preferred_locations", []) + [profile.get("location", "")])
    cand_countries = set()
    for pat, cname in COUNTRY_MAP:
        if pat.search(cand_loc_str):
            cand_countries.add(cname)
    cand_has_specific_country = bool(cand_countries - {"Worldwide"})

    job_country = classify_job_country(job.get("location"), job.get("title"), text)

    # Detect candidate remote status
    cand_is_remote = (
        (profile.get("work_mode") or "").lower() == "remote" or
        (profile.get("location") or "").lower() in ("remote", "worldwide")
    ) and not profile.get("preferred_locations")

    # Detect strict country requirements in job description/location
    us_restricted = bool(re.search(r"\b(us only|u\.s\. only|must reside in (the )?us|must be located in (the )?united states|us citizen|green card|security clearance|authorized to work in the (us|united states))\b", text, re.I))
    uk_restricted = bool(re.search(r"\b(uk only|must be located in (the )?united kingdom|right to work in the uk|must reside in the uk)\b", text, re.I))
    canada_restricted = bool(re.search(r"\b(canada only|must reside in canada|authorized to work in canada)\b", text, re.I))
    eu_restricted = bool(re.search(r"\b(eu only|must be based in europe|emea only|schengen)\b", text, re.I))

    geo_blocked = False
    if cand_has_specific_country:
        if us_restricted and "United States" not in cand_countries:
            geo_blocked = True
            notes.append("Geographic restriction: Posting requires US residency or citizenship.")
        elif uk_restricted and "United Kingdom" not in cand_countries:
            geo_blocked = True
            notes.append("Geographic restriction: Posting requires UK residency / work authorization.")
        elif canada_restricted and "Canada" not in cand_countries:
            geo_blocked = True
            notes.append("Geographic restriction: Posting requires Canada residency.")
        elif eu_restricted and not (cand_countries & {"Germany", "France", "Netherlands", "Ireland", "Spain", "Poland", "Sweden", "Italy", "Portugal", "Austria", "Belgium", "Denmark", "Finland"}):
            geo_blocked = True
            notes.append("Geographic restriction: Posting requires European/EU residency.")
        elif jm in ("hybrid", "onsite") and job_country not in ("Worldwide", "") and job_country not in cand_countries:
            geo_blocked = True
            notes.append(f"Location mismatch: Role is {jm} in {job_country}, outside your preferred location.")

    if geo_blocked:
        mode_pts = 0
    elif cand_is_remote and jm in ("onsite", "hybrid") and job_country not in ("Worldwide", ""):
        # Candidate is remote without foreign country preference, but job requires physical on-site presence
        mode_pts = 2 if jm == "onsite" else 3
        notes.append(f"Location barrier: Role requires {jm} presence in {job.get('location') or job_country}.")
    elif cm in ("any", ""):
        mode_pts = 8 if jm != "unknown" else 6
    elif cm in jm or (cm == "remote" and jm == "remote"):
        mode_pts = 10
    elif jm == "unknown":
        mode_pts = 5
    else:
        mode_pts = 2
    if not geo_blocked and jm in ("hybrid", "onsite") and prefs:
        mode_pts = max(mode_pts, 9 if any(p.split(",")[0] in loc for p in prefs) else mode_pts - 2)
    mode_pts = max(0, min(10, mode_pts))

    # Freshness and salary alignment
    age = days_since(job.get("posted_at"))
    fresh_pts = 3 if age is None else 5 if age <= 7 else 4 if age <= 21 else 2 if age <= 45 else 0
    if age is not None and age > 60:
        notes.append(f"Posted {age} days ago (may be filled).")

    sal_pts = 3
    want = float(profile.get("min_salary") or 0)
    ann = annualize(parse_salary(job.get("salary", "")))
    if want and ann:
        want_annual = want * 2000 if want < 500 else want
        if ann[1] >= want_annual:
            sal_pts = 5
            notes.append(f"Salary ({job.get('salary')}) meets your minimum target.")
        elif ann[1] < want_annual * 0.80:
            sal_pts = 0
            notes.append(f"Salary ({job.get('salary')}) is below your minimum target.")
        else:
            sal_pts = 2
    elif ann:
        sal_pts = 4

    # Job type / Contract preference matching
    jt = (job.get("job_type") or "").lower()
    raw_pref_types = profile.get("preferred_job_types") or []
    if isinstance(raw_pref_types, str):
        pref_types = [t.lower().strip() for t in raw_pref_types.split(",") if t.strip()]
    else:
        pref_types = [t.lower().strip() for t in raw_pref_types if isinstance(t, str) and t.strip()]
    pref_types = [t for t in pref_types if t != "any"]
    job_type_pts = 3
    if jt and pref_types:
        if any(p in jt for p in pref_types):
            job_type_pts = 5
            notes.append(f"Job type ({job.get('job_type')}) matches your preference.")
        elif "full-time" in pref_types and "intern" in jt:
            job_type_pts = 0
            notes.append(f"Job type ({job.get('job_type')}) is an internship, but you prefer Full-time.")
        elif "full-time" in pref_types and "contract" in jt:
            job_type_pts = 2
        elif "contract" in pref_types and "full-time" in jt:
            job_type_pts = 2
    elif jt:
        job_type_pts = 4

    # Dream companies alignment
    comp_name = (job.get("company") or "").lower().strip()
    raw_dream_comps = profile.get("dream_companies") or []
    if isinstance(raw_dream_comps, str):
        dream_comps = [c.lower().strip() for c in raw_dream_comps.split(",") if c.strip()]
    else:
        dream_comps = [c.lower().strip() for c in raw_dream_comps if isinstance(c, str) and c.strip()]
    is_dream_company = False
    if comp_name and dream_comps:
        if any(dc in comp_name or comp_name in dc for dc in dream_comps):
            is_dream_company = True
            notes.append(f"Wishlist Company: {job.get('company')} is in your dream companies!")

    # Dream role focus alignment
    dream_role_text = (profile.get("dream_role") or "").strip().lower()
    dream_role_bonus = 0
    if dream_role_text and len(dream_role_text) > 10:
        dream_tokens = set(re.findall(r"[a-z0-9+#]+", dream_role_text)) - STOP
        job_tokens = set(re.findall(r"[a-z0-9+#]+", f"{job.get('title', '')} {job.get('description', '')[:1000]}".lower()))
        overlap_count = len(dream_tokens & job_tokens)
        if overlap_count >= 3:
            dream_role_bonus = min(3, overlap_count // 2)
            notes.append("Aligns with your dream role technical focus.")

    dream_bonus = (3 if is_dream_company else 0) + dream_role_bonus + bonus_pts
    score = (skill_pts + title_pts + sen_pts + mode_pts + fresh_pts + sal_pts + dream_bonus) - sen_penalty - core_penalty
    if geo_blocked:
        score = min(score, 38)

    # Domain gate: a different profession with almost no skill overlap must not look like a fit.
    if title_ratio < 0.12 and len(matched) <= 1:
        score = min(score, 32)
        notes.append("Job title is in a different field from your target roles.")
    bad = [k for k in profile.get("excluded_keywords", []) if k and k.lower() in text.lower()]
    if bad:
        score = min(score, 25)
        notes.append("Contains excluded keyword: " + ", ".join(bad[:3]))
    score = int(round(max(0, min(100, score))))

    confidence = "high" if total_w >= 3 and desc_len > 400 else "medium" if (total_w >= 2 and desc_len >= 250) or is_enriched else "low"
    if confidence == "low":
        notes.append("Few requirements were readable from this posting, so the score leans on title and role alignment.")

    if score >= 85:
        label = "Excellent fit"
    elif score >= 70:
        label = "Strong fit"
    elif score >= 50:
        label = "Moderate fit"
    else:
        label = "Weak fit"
    parts = []
    if weights:
        parts.append(f"Matches {len(matched)} of {len(weights)} skills named in the posting"
                     + (f" ({', '.join(matched[:4])})" if matched else ""))
    if missing:
        parts.append("Missing: " + ", ".join(missing[:4]))
    if affinity:
        parts.append("Related experience: " + "; ".join(affinity[:2]))
    parts += notes
    parts = [x.rstrip(".") for x in parts]
    rationale = f"{label} ({score}%). " + ". ".join(parts) + "." if parts else f"{label} ({score}%)."
    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "matched_required_skills": matched_required,
        "missing_required_skills": missing_required,
        "bonus_matches": bonus_matches,
        "affinity_matches": affinity,
        "rationale": rationale,
        "confidence": confidence,
        "is_dream_company": is_dream_company,
        "score_breakdown": {
            "skills": round(min(50, skill_pts + bonus_pts), 1),
            "title": round(title_pts, 1),
            "seniority": round(sen_pts, 1),
            "work_mode": round(mode_pts, 1),
            "salary": sal_pts,
            "preferences": round(job_type_pts + dream_role_bonus + (3 if is_dream_company else 0), 1),
            "freshness": fresh_pts
        },
        "required_skills": {k: v for k, v in weights.items()},
        "salary_annual_min": int(ann[0]) if ann else 0,
        "salary_annual_max": int(ann[1]) if ann else 0,
        "has_salary": bool(ann),
        "seniority": classify_job_seniority(job.get("title"), text),
        "country": job_country,
        "company_stage": classify_company_stage(job),
    }


def score_job_best(job, profiles=None):
    """Evaluate a job against multiple candidate resume profiles and select the best match.

    Returns a unified match dictionary containing:
    - The winning profile's score and match details (matched_skills, missing_skills, rationale, etc.)
    - best_profile_id: ID of the winning resume variant
    - best_profile_name: Display name of the winning resume variant
    - best_profile_target: Target title of the winning resume variant
    - live_matches: Ranked breakdown list of all evaluated profiles
    - total_live_profiles: Number of active resumes evaluated
    """
    if profiles is None:
        from . import db
        profiles = db.get_live_profiles()

    if isinstance(profiles, dict):
        profiles = [profiles]
    elif not profiles:
        from . import db
        profiles = [db.get_profile()]

    evaluations = []
    for idx, p in enumerate(profiles, start=1):
        pid = p.get("_profile_id") or p.get("id") or f"profile_{idx}"
        pname = p.get("_profile_name") or p.get("name") or f"Resume #{idx}"
        target = p.get("target_title") or "General Candidate"
        is_master = bool(p.get("_is_master") or p.get("is_master"))
        is_active = bool(p.get("_is_active") or p.get("is_active"))

        res = score_job(job, p)
        evaluations.append({
            "id": pid,
            "name": pname,
            "target_title": target,
            "score": res.get("score", 0),
            "matched_count": len(res.get("matched_skills", [])),
            "missing_count": len(res.get("missing_skills", [])),
            "matched_skills": res.get("matched_skills", []),
            "missing_skills": res.get("missing_skills", []),
            "is_master": is_master,
            "is_active": is_active,
            "scored_result": res
        })

    # Rank profiles:
    # 1. Highest score
    # 2. Most matched skills
    # 3. Master profile tie-breaker
    evaluations.sort(key=lambda e: (e["score"], e["matched_count"], 1 if e["is_master"] else 0), reverse=True)

    winner = evaluations[0]
    winning_result = dict(winner["scored_result"])

    live_matches = []
    for idx, e in enumerate(evaluations, start=1):
        is_best = (idx == 1)
        live_matches.append({
            "id": e["id"],
            "name": e["name"],
            "target_title": e["target_title"],
            "score": e["score"],
            "matched_count": e["matched_count"],
            "missing_count": e["missing_count"],
            "is_master": e["is_master"],
            "is_active": e["is_active"],
            "is_best": is_best
        })

    winning_result["best_profile_id"] = winner["id"]
    winning_result["best_profile_name"] = winner["name"]
    winning_result["best_profile_target"] = winner["target_title"]
    winning_result["live_matches"] = live_matches
    winning_result["total_live_profiles"] = len(evaluations)

    if len(evaluations) > 1:
        prefix = f"[Best match with {winner['name']}] "
        orig_rat = winning_result.get("rationale", "")
        if prefix not in orig_rat:
            winning_result["rationale"] = f"{prefix}{orig_rat}"

    return winning_result


def calculate_explainable_fit(profile: dict, job: dict) -> dict:
    """Calculate the explainable 100-point fit score and separate eligibility checks per Section 10.

    Weights:
    - Skills: 35
    - Responsibilities & Scope: 25
    - Seniority & Ownership: 15
    - Domain & Environment: 10
    - Work Conditions: 10
    - Compensation: 5
    """
    cand_skills = set(profile.get("skills") or [])
    cand_skills_l = {s.lower() for s in cand_skills}

    title = job.get("title") or ""
    desc = job.get("description") or ""
    all_text = f"{title}\n{desc}"

    # 1. Skills (Weight: 35)
    extracted_weights = sk.extract_weighted(all_text)
    matched = [s for s in extracted_weights if s in cand_skills or s.lower() in cand_skills_l]
    missing = [s for s in extracted_weights if s not in matched]

    adjacent = []
    adj_credit = 0.0
    for m in missing:
        if m in sk.ADJACENT or any(m in members for members in sk.CLUSTERS.values()):
            adjacent.append(m)
            adj_credit += 0.45 * extracted_weights.get(m, 1.0)

    total_w = sum(extracted_weights.values()) or 1.0
    matched_w = sum(extracted_weights[s] for s in matched) + adj_credit
    skills_score = min(100.0, (matched_w / total_w) * 100.0)

    # 2. Responsibilities and Scope (Weight: 25)
    title_ratio = _title_score(title, profile)
    resp_score = min(100.0, title_ratio * 100.0)

    # 3. Seniority and Ownership (Weight: 15)
    job_level = level_of(title)
    if job_level is None:
        sen_class = classify_job_seniority(title, desc)
        job_level = 3 if "senior" in sen_class else 4 if "lead" in sen_class or "staff" in sen_class else 2
    cand_years = float(profile.get("years_of_experience") or 0.0)
    cand_level = years_to_level(cand_years) if cand_years else 2
    diff = abs(job_level - cand_level)
    sen_score = max(0.0, 100.0 - (diff * 25.0))

    # 4. Domain and Environment (Weight: 10)
    domain_score = 75.0 if matched else 50.0

    # 5. Work conditions (Weight: 10)
    job_mode = (job.get("work_mode") or "").strip().lower()
    cand_mode = (profile.get("work_mode_preference") or "").strip().lower()
    work_conditions_score = 100.0
    if cand_mode and job_mode:
        if cand_mode in job_mode or job_mode in cand_mode or "remote" in (cand_mode, job_mode):
            work_conditions_score = 100.0
        else:
            work_conditions_score = 30.0

    # 6. Compensation (Weight: 5)
    cand_min_sal = float(profile.get("target_salary_min") or profile.get("salary_min") or 0.0)
    job_sal = job.get("salary_min") or job.get("salary")
    comp_applicable = False
    comp_score = None
    if cand_min_sal and job_sal:
        comp_applicable = True
        comp_score = 100.0

    # Separate Eligibility Checks (met, not_met, unknown)
    eligibility_details: dict[str, str] = {}
    if cand_mode and job_mode:
        if cand_mode == "remote" and job_mode in ("on-site", "onsite"):
            eligibility_details["work_mode"] = "not_met"
        elif cand_mode in ("on-site", "onsite") and job_mode == "remote":
            eligibility_details["work_mode"] = "met"
        else:
            eligibility_details["work_mode"] = "met"
    else:
        eligibility_details["work_mode"] = "unknown"

    overall_eligibility = "not_met" if "not_met" in eligibility_details.values() else "met"

    # Weighted combination normalized across applicable dimensions
    active_weights = {"skills": 35.0, "responsibilities": 25.0, "seniority": 15.0, "domain": 10.0, "work_conditions": 10.0}
    scores = {
        "skills": skills_score,
        "responsibilities": resp_score,
        "seniority": sen_score,
        "domain": domain_score,
        "work_conditions": work_conditions_score,
    }
    if comp_applicable and comp_score is not None:
        active_weights["compensation"] = 5.0
        scores["compensation"] = comp_score

    weight_sum = sum(active_weights.values())
    weighted_total = sum(scores[dim] * active_weights[dim] for dim in active_weights)
    final_score = weighted_total / weight_sum

    # Completeness and Coverage
    filled_fields = sum(1 for f in (title, desc, job.get("location"), job.get("work_mode"), job.get("company"), job.get("salary")) if f)
    completeness = round(filled_fields / 6.0, 2)
    coverage = round(len(matched) / max(1, len(cand_skills)), 2)

    confidence = "high" if completeness >= 0.7 and coverage >= 0.3 else "medium" if completeness >= 0.5 else "low"

    return {
        "fit_score": round(final_score),
        "breakdown": {
            "skills": round(skills_score, 1),
            "responsibilities": round(resp_score, 1),
            "seniority": round(sen_score, 1),
            "domain": round(domain_score, 1),
            "work_conditions": round(work_conditions_score, 1),
            "compensation": round(comp_score, 1) if comp_score is not None else None,
        },
        "dimension_weights": {
            "skills": 35,
            "responsibilities": 25,
            "seniority": 15,
            "domain": 10,
            "work_conditions": 10,
            "compensation": 5,
        },
        "score_confidence": confidence,
        "job_data_completeness": completeness,
        "candidate_evidence_coverage": coverage,
        "eligibility": overall_eligibility,
        "eligibility_details": eligibility_details,
        "matched_skills": sorted(matched),
        "missing_skills": sorted(missing),
        "adjacent_skills": sorted(adjacent),
    }

