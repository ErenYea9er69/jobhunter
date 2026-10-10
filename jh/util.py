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
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()[:limit]


def normalize_company(name):
    s = (name or "").lower().strip()
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
    return str(text).strip() if parse_salary(text) else ""


# ---------------------------------------------------------------- http

class HttpError(Exception):
    pass


def http_get(url, headers=None, timeout=None, retries=1, max_bytes=6_000_000, data=None, method=None):
    """GET (or POST with data) with gzip support, size cap, and one polite retry on 429/5xx."""
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
