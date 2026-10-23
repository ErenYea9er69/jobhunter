"""Shared helpers: text cleanup, dates, salary parsing, and a hardened HTTP client."""
import datetime
import email.utils
import gzip
import html
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from . import config


# ---------------------------------------------------------------- text

class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK or tag == "li":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def clean_text(val):
    """Sanitize text fields: decode HTML entities (including hex &#x...; and multi-encoded),
    normalize whitespace, non-breaking spaces, and strip zero-width characters."""
    if val is None or val != val:
        return ""
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return ""
    # Decode HTML entities (run up to 3 passes for double/triple encoded entities like &amp;#xE9;)
    for _ in range(3):
        if "&" not in s:
            break
        unescaped = html.unescape(s)
        if unescaped == s:
            break
        s = unescaped
    s = s.replace("\xa0", " ").replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2022", "•").replace("\u00b7", "•")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def html_to_text(raw, limit=8000):
    """Convert HTML (possibly entity-escaped HTML) to readable plain text."""
    if not raw:
        return ""
    raw = str(raw)
    if "&lt;" in raw and "<" not in raw:
        raw = html.unescape(raw)
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    text = clean_text(text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()[:limit]


def normalize_company(name):
    s = clean_text(name).lower()
    s = re.sub(r"\b(inc|llc|corp|corporation|ltd|limited|gmbh|co|company|plc|pte|sa|ag)\b\.?", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


# ---------------------------------------------------------------- dates

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def parse_date(value):
    """Return an aware UTC datetime or None. Accepts ISO, RFC 2822, epoch seconds or millis."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)) or re.fullmatch(r"\d{9,13}", str(value)):
            n = float(value)
            if n > 1e11:
                n /= 1000.0
            return datetime.datetime.fromtimestamp(n, datetime.timezone.utc)
        s = str(value).strip()
        try:
            d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            d = email.utils.parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return d.astimezone(datetime.timezone.utc)
    except Exception:
        return None


def iso_or_empty(value):
    d = parse_date(value)
    return d.replace(microsecond=0).isoformat() if d else ""


def days_since(value):
    d = parse_date(value)
    if not d:
        return None
    return max(0.0, (datetime.datetime.now(datetime.timezone.utc) - d).total_seconds() / 86400.0)


# ---------------------------------------------------------------- salary

_CUR = [("€", "EUR"), ("eur", "EUR"), ("£", "GBP"), ("gbp", "GBP"), ("cad", "CAD"), ("aud", "AUD"),
        ("$", "USD"), ("usd", "USD")]


def parse_salary(text):
    """Parse '$150,000 - $185,000', '150k-180k USD', 'EUR 95,000 - 120,000'.
    Return dict(min, max, currency, period) or None. Placeholder words return None."""
    if not text:
        return None
    s = str(text).lower().replace(",", "")
    cur = "USD"
    for token, code in _CUR:
        if token in s:
            cur = code
            break
    nums = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(k|m)?(?![a-z0-9])", s):
        v = float(m.group(1))
        if m.group(2) == "k":
            v *= 1000
        elif m.group(2) == "m":
            v *= 1_000_000
        nums.append(v)
    nums = [n for n in nums if n >= 10]
    if not nums:
        return None
    lo, hi = min(nums[:2]), max(nums[:2])
    period = "year"
    if re.search(r"/\s*h(ou)?r|per hour|hourly", s) or hi < 400:
        period = "hour"
    elif re.search(r"/\s*mo\b|per month|monthly", s):
        period = "month"
    return {"min": lo, "max": hi, "currency": cur, "period": period}


def annualize(sal):
    if not sal:
        return None
    mult = {"year": 1, "month": 12, "hour": 2080}[sal["period"]]
    return sal["min"] * mult, sal["max"] * mult


def clean_salary_label(text):
    """Return the salary text only when it holds real figures. Placeholders become empty."""
    text = clean_text(text)
    return str(text).strip() if parse_salary(text) else ""


def clean_job_type(val):
    """Normalize employment types: Contract, Full-time, Part-time, Internship."""
    if not val:
        return ""
    if isinstance(val, (list, tuple, set)):
        items = [clean_job_type(x) for x in val if x]
        items = [x for x in items if x]
        return items[0] if items else ""
    s = clean_text(val).lower().strip().replace("-", " ").replace("_", " ")
    if re.search(r"\b(intern|internship|stage|alternance|apprentice|praktik|praktikum|werkstudent|student|co\s*op)\b", s):
        return "Internship"
    if re.search(r"\b(part\s*time|parttime|teilzeit|mi\s*temps)\b", s):
        return "Part-time"
    if re.search(r"\b(contract|contractor|c2c|w2|freelance|freelancer|consultant|subcontract|temporary|temp|cdd|fixed\s*term)\b", s):
        return "Contract"
    if re.search(r"\b(full\s*time|fulltime|permanent|cdi|regular|direct\s*hire|vollzeit|berufserfahren|experienced)\b", s):
        return "Full-time"
    return str(val).strip().title() if len(str(val).strip()) <= 20 else ""


def format_schema_salary(sal_obj):
    """Format schema.org MonetaryAmount or QuantitativeValue into readable string."""
    if not sal_obj:
        return ""
    if isinstance(sal_obj, str):
        return sal_obj.strip()
    if not isinstance(sal_obj, dict):
        return ""
    cur = sal_obj.get("currency", "USD") or "USD"
    cur_sym = "€" if cur == "EUR" else "£" if cur == "GBP" else "$"
    val = sal_obj.get("value")
    unit = str(sal_obj.get("unitText") or "").lower()
    if isinstance(val, dict):
        min_v = val.get("minValue") or val.get("min")
        max_v = val.get("maxValue") or val.get("max")
        unit = str(val.get("unitText") or unit).lower()
        if min_v and max_v:
            min_str = f"{int(min_v):,}" if float(min_v).is_integer() else f"{float(min_v):.2f}"
            max_str = f"{int(max_v):,}" if float(max_v).is_integer() else f"{float(max_v):.2f}"
            unit_str = f" / {unit.lower()}" if unit else ""
            return f"{cur_sym}{min_str} - {cur_sym}{max_str}{unit_str}"
        elif min_v:
            min_str = f"{int(min_v):,}" if float(min_v).is_integer() else f"{float(min_v):.2f}"
            unit_str = f" / {unit.lower()}" if unit else ""
            return f"{cur_sym}{min_str}{unit_str}"
    elif isinstance(val, (int, float)):
        val_str = f"{int(val):,}" if float(val).is_integer() else f"{float(val):.2f}"
        unit_str = f" / {unit.lower()}" if unit else ""
        return f"{cur_sym}{val_str}{unit_str}"
    return ""


def extract_job_sections(text):
    """Parse structured sections: responsibilities, qualifications, how to apply, contact info."""
    if not text:
        return {}
    sections = {
        "responsibilities": [],
        "qualifications": [],
        "preferred_qualifications": [],
        "how_to_apply": "",
        "contact_email": "",
        "contact_website": "",
        "salary_text": "",
        "job_type": "",
    }
    # 1. Email extraction
    email_m = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    if email_m:
        sections["contact_email"] = email_m.group(0)

    # 2. Website extraction
    site_m = re.search(r'(?:Website|Apply at|Careers):\s*(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)', text, re.I)
    if site_m:
        url = site_m.group(1).strip()
        if not url.startswith("http"):
            url = f"https://{url}"
        sections["contact_website"] = url

    # 3. Pay / Salary in text
    pay_m = re.search(r'(?:Pay|Salary|Compensation|Rate):\s*([^\n\r]+)', text, re.I)
    if pay_m:
        sections["salary_text"] = pay_m.group(1).strip()

    # 4. Job type in text
    type_m = re.search(r'(?:Job Type|Employment Type|Contract Type):\s*([^\n\r]+)', text, re.I)
    if type_m:
        sections["job_type"] = type_m.group(1).strip()

    # 5. Section headers parsing
    lines = text.split("\n")
    current_sec = None
    buffer = []

    SEC_PATTERNS = [
        ("responsibilities", re.compile(r'^(?:Key\s+)?Responsibilities(?:\s+and\s+Duties)?|^What\s+You(?:\'ll| will)\s+Do|^Missions(?:\s+du\s+poste)?', re.I)),
        ("preferred_qualifications", re.compile(r'^Preferred\s+Qualifications|^Nice\s+to\s+Have|^Bonus\s+Points', re.I)),
        ("qualifications", re.compile(r'^(?:Required\s+)?Qualifications|^Requirements|^What\s+You\s+Bring|^Profil\s+recherch[ée]|^Comp[ée]tences', re.I)),
        ("how_to_apply", re.compile(r'^How\s+to\s+Apply|^To\s+Apply|^Application\s+Process|^Comment\s+postuler', re.I)),
    ]

    def flush(sec, items):
        if not sec or not items:
            return
        cleaned = [re.sub(r'^[\s*\-•–—]+', '', it).strip() for it in items if it.strip()]
        cleaned = [c for c in cleaned if c and len(c) > 3]
        if sec in ("responsibilities", "qualifications", "preferred_qualifications"):
            sections[sec].extend(cleaned)
        elif sec == "how_to_apply":
            sections["how_to_apply"] = "\n".join(items).strip()

    for line in lines:
        sline = line.strip()
        if not sline:
            continue
        clean_header = re.sub(r'[:#*_-]+', '', sline).strip()
        matched_sec = None
        for sec_name, pat in SEC_PATTERNS:
            if pat.search(clean_header):
                matched_sec = sec_name
                break

        if matched_sec:
            flush(current_sec, buffer)
            current_sec = matched_sec
            buffer = []
        else:
            if current_sec:
                if re.match(r'^(?:Pay|Salary|Work Location|About Us|Benefits|Equal Opportunity):', sline, re.I):
                    flush(current_sec, buffer)
                    current_sec = None
                    buffer = []
                else:
                    buffer.append(sline)

    flush(current_sec, buffer)
    return sections


def parse_schema_job_posting(html_or_dict):
    """Parse schema.org JobPosting from HTML text or JSON dict."""
    if not html_or_dict:
        return {}
    if isinstance(html_or_dict, dict):
        d = html_or_dict
    else:
        matches = re.findall(r'<script[^>]*type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>', str(html_or_dict), re.S)
        d = None
        for m in matches:
            try:
                cand = json.loads(m.strip())
                if isinstance(cand, list):
                    cand = next((c for c in cand if isinstance(c, dict) and c.get("@type") == "JobPosting"), None)
                if isinstance(cand, dict) and cand.get("@type") == "JobPosting":
                    d = cand
                    break
                elif isinstance(cand, dict) and isinstance(cand.get("@graph"), list):
                    cand = next((c for c in cand["@graph"] if isinstance(c, dict) and c.get("@type") == "JobPosting"), None)
                    if cand:
                        d = cand
                        break
            except Exception:
                continue
        if not d:
            return {}

    title = d.get("title") or ""
    comp = d.get("hiringOrganization")
    company = comp.get("name") if isinstance(comp, dict) else (str(comp or "") if comp else "")
    loc = d.get("jobLocation")
    loc_str = ""
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
            loc_str = ", ".join(p for p in parts if p)
        elif isinstance(addr, str):
            loc_str = addr
    elif isinstance(loc, list) and loc:
        loc_str = str(loc[0])

    sal = format_schema_salary(d.get("baseSalary"))
    emp_type = clean_job_type(d.get("employmentType"))
    desc_raw = d.get("description") or ""
    desc_text = html_to_text(desc_raw) if desc_raw else ""
    date_posted = d.get("datePosted") or ""

    sections = extract_job_sections(desc_text)
    if not sal and sections.get("salary_text"):
        sal = sections["salary_text"]
    if not emp_type and sections.get("job_type"):
        emp_type = clean_job_type(sections["job_type"])

    return {
        "title": clean_text(title),
        "company": clean_text(company),
        "location": clean_text(loc_str),
        "salary": clean_text(sal),
        "job_type": clean_text(emp_type),
        "description": desc_text,
        "posted_at": date_posted,
        "responsibilities": sections.get("responsibilities", []),
        "qualifications": sections.get("qualifications", []),
        "preferred_qualifications": sections.get("preferred_qualifications", []),
        "how_to_apply": sections.get("how_to_apply", ""),
        "contact_email": sections.get("contact_email", ""),
        "contact_website": sections.get("contact_website", ""),
    }



# ---------------------------------------------------------------- http

class HttpError(Exception):
    pass


def http_get(url, headers=None, timeout=None, retries=1, max_bytes=6_000_000, data=None, method=None):
    """GET (or POST with data) with gzip support, size cap, and one polite retry on 429/5xx."""
    parsed = urllib.parse.urlparse(url or "")
    if parsed.scheme.lower() not in ("http", "https"):
        raise HttpError(f"Unsupported URL scheme: '{parsed.scheme}'. Only http and https are allowed.")
    timeout = timeout or config.SOURCE_TIMEOUT_SECONDS
    hdrs = {"User-Agent": config.USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.5",
            "Accept-Encoding": "gzip"}
    hdrs.update(headers or {})
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs, data=data, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    raise HttpError("response too large")
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last = HttpError(f"HTTP {e.code} from {urllib.parse.urlparse(url).netloc}")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(min(2.0, 0.6 * (attempt + 1)))
                continue
            raise last
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = HttpError(f"network error for {urllib.parse.urlparse(url).netloc}: {e}")
            if attempt < retries:
                time.sleep(0.5)
                continue
            raise last
    raise last or HttpError("request failed")


def http_get_json(url, **kw):
    return json.loads(http_get(url, **kw))
