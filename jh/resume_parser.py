"""Resume parsing. Reads real structure from the text. Missing fields stay empty; nothing is invented."""
import base64
import datetime
import io
import re
import shutil
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
import zlib

from . import skills as sk


class ParseError(Exception):
    pass


# ------------------------------------------------------------ file to text

def extract_text(filename, raw):
    name = (filename or "").lower()
    if name.endswith(".docx") or raw[:2] == b"PK":
        return _docx_text(raw)
    if name.endswith(".pdf") or raw[:5] == b"%PDF-":
        return _pdf_text(raw)
    if name.endswith(".doc"):
        raise ParseError("Legacy .doc files are not supported. Save the file as .docx or PDF, or paste the text.")
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ParseError("Could not decode the file as text.")


def _docx_text(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise ParseError("The .docx file is damaged or not a Word document.")
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ET.fromstring(xml)
    lines = []
    for p in root.iter(ns + "p"):
        buf = []
        for node in p.iter():
            if node.tag == ns + "t" and node.text:
                buf.append(node.text)
            elif node.tag in (ns + "tab",):
                buf.append("\t")
            elif node.tag == ns + "br":
                buf.append("\n")
        text = "".join(buf).strip()
        is_bullet = p.find(f"{ns}pPr/{ns}numPr") is not None
        if text:
            lines.append(("- " if is_bullet else "") + text)
    return "\n".join(lines)


def _pdf_text(raw):
    try:
        from pypdf import PdfReader  # optional dependency
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception:
        pass
    exe = shutil.which("pdftotext")
    if exe:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(raw)
            f.flush()
            try:
                out = subprocess.run([exe, "-layout", f.name, "-"], capture_output=True, timeout=30, check=True).stdout
                text = out.decode("utf-8", errors="replace")
                if text.strip():
                    return text
            except Exception:
                pass
    text = _pdf_text_builtin(raw)
    if len(text.strip()) < 40:
        raise ParseError("No readable text found in the PDF. It may be a scan. Paste the text instead, "
                         "or install pypdf (pip install pypdf) for better PDF support.")
    return text


def _pdf_text_builtin(raw):
    """Minimal extractor for simple text PDFs: inflate streams and read Tj/TJ operators."""
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        data = m.group(1)
        try:
            data = zlib.decompress(data)
        except Exception:
            pass
        if b"BT" not in data:
            continue
        for block in re.findall(rb"BT(.*?)ET", data, re.S):
            line = []
            for part in re.finditer(rb"\((.*?)(?<!\\)\)\s*Tj|\[(.*?)\]\s*TJ|T\*|Td|TD", block, re.S):
                tok = part.group(0)
                if tok in (b"T*", b"Td", b"TD"):
                    line.append("\n")
                elif part.group(1) is not None:
                    line.append(_pdf_unescape(part.group(1)))
                elif part.group(2) is not None:
                    line.append("".join(_pdf_unescape(s) for s in re.findall(rb"\((.*?)(?<!\\)\)", part.group(2), re.S)))
            out.append("".join(line))
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text)


def _pdf_unescape(b):
    b = re.sub(rb"\\([nrtbf()\\])", lambda m: {b"n": b"\n", b"r": b"", b"t": b" ", b"b": b"", b"f": b""}.get(m.group(1), m.group(1)), b)
    return b.decode("latin-1", errors="replace")


def decode_upload(payload):
    """Accept {text} or {filename, content_base64}. Return plain text."""
    if payload.get("content_base64"):
        try:
            raw = base64.b64decode(payload["content_base64"], validate=False)
        except Exception:
            raise ParseError("The uploaded file could not be decoded.")
        return extract_text(payload.get("filename", ""), raw)
    return payload.get("text", "") or ""


# ------------------------------------------------------------ structure

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:{_MON}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}}-\d{{2}}|\d{{4}})"
RANGE_RE = re.compile(rf"({_DATE})\s*(?:-|–|—|to)\s*({_DATE}|present|current|now|today|ongoing)", re.I)

SECTION_ALIASES = {
    "summary": ["summary", "professional summary", "profile", "about", "about me", "objective", "career summary"],
    "experience": ["experience", "work experience", "professional experience", "employment", "employment history",
                   "work history", "career history", "relevant experience"],
    "education": ["education", "academic background", "education and training", "academics"],
    "skills": ["skills", "technical skills", "core competencies", "competencies", "technologies", "tech stack",
               "key skills", "skills and tools", "core skills"],
    "projects": ["projects", "selected projects", "personal projects"],
    "certifications": ["certifications", "certificates", "licenses", "licenses and certifications"],
    "other": ["languages", "awards", "publications", "interests", "volunteering", "references", "activities"],
}
_HEAD = {a: k for k, v in SECTION_ALIASES.items() for a in v}
BULLET_RE = re.compile(r"^\s*(?:[-•*▪●◦‣·]|\d+[.)])\s+")
DEGREE_RE = re.compile(r"\b(b\.?\s?tech|m\.?\s?tech|b\.?\s?s\.?c?\.?|b\.?a\.?|m\.?s\.?c?\.?|m\.?a\.?|mba|ph\.?d\.?|bachelor[^,\n]*|master[^,\n]*|doctorate|associate[^,\n]*|diploma)\b", re.I)
INSTITUTION_RE = re.compile(r"\b(university|college|institute|school|academy|polytechnic|universit[éey]|hochschule)\b", re.I)


def _to_ym(token):
    t = token.strip().lower().rstrip(".")
    if t in ("present", "current", "now", "today", "ongoing"):
        return None
    m = re.match(rf"({_MON})\s+(\d{{4}})", t, re.I)
    if m:
        return int(m.group(2)), MONTHS.get(m.group(1)[:3].lower(), 1)
    m = re.match(r"(\d{1,2})/(\d{4})", t)
    if m:
        return int(m.group(2)), min(12, max(1, int(m.group(1))))
    m = re.match(r"(\d{4})-(\d{2})", t)
    if m:
        return int(m.group(1)), min(12, max(1, int(m.group(2))))
    m = re.match(r"(\d{4})", t)
    return (int(m.group(1)), 1) if m else None


def _fmt(ym):
    return f"{ym[0]:04d}-{ym[1]:02d}" if ym else "Present"


def years_from_ranges(ranges):
    """Merge overlapping (start, end) month ranges and return total years, rounded to 0.5."""
    today = datetime.date.today()
    spans = []
    for s, e in ranges:
        if not s:
            continue
        e = e or (today.year, today.month)
        a, b = s[0] * 12 + s[1], e[0] * 12 + e[1]
        if b >= a:
            spans.append((a, b))
    spans.sort()
    total, cur = 0, None
    for a, b in spans:
        if cur is None:
            cur = [a, b]
        elif a <= cur[1]:
            cur[1] = max(cur[1], b)
        else:
            total += cur[1] - cur[0]
            cur = [a, b]
    if cur:
        total += cur[1] - cur[0]
    return round(total / 12 * 2) / 2


def _split_sections(lines):
    sections, current, buf = {"header": []}, "header", []
    for ln in lines:
        key = re.sub(r"[^a-z& ]", "", ln.strip().lower()).replace("&", "and").strip()
        is_head = key in _HEAD and len(ln.strip()) < 40 and not BULLET_RE.match(ln)
        if is_head:
            sections.setdefault(current, []).extend(buf)
            buf, current = [], _HEAD[key]
            sections.setdefault(current, [])
        else:
            buf.append(ln)
    sections.setdefault(current, []).extend(buf)
    return sections


def _role_company(text, prev_line):
    """Split a header line (date range removed) into (role, company, location)."""
    t = RANGE_RE.sub("", text).strip(" |,-–—·()")
    parts = [p.strip() for p in re.split(r"\s+[|•·–—-]\s+|\s{3,}|\t", t) if p.strip()]
    role = company = location = ""
    m = re.match(r"(.+?)\s+(?:at|@)\s+(.+)", t, re.I)
    if m and len(parts) < 2:
        role, company = m.group(1).strip(), m.group(2).strip()
    elif len(parts) >= 2:
        role, company = parts[0], parts[1]
        if len(parts) >= 3:
            location = parts[2]
    elif parts:
        role = parts[0]
    if not company and prev_line and not BULLET_RE.match(prev_line) and len(prev_line) < 80 and not RANGE_RE.search(prev_line):
        company = prev_line.strip(" |,-–—")
    if "," in company and not location:
        company, _, tail = company.partition(",")
        location = tail.strip()
    return role, company.strip(), location


_ROLE_WORDS = re.compile(r"engineer|developer|manager|analyst|designer|director|lead|architect|consultant|specialist|"
                         r"nurse|teacher|scientist|administrator|coordinator|intern|officer|associate|accountant|"
                         r"technician|marketer|writer|editor|representative|assistant|head|vp|president|founder", re.I)


def parse_experience(lines):
    entries, cur, prev = [], None, ""
    ranges = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        m = RANGE_RE.search(s)
        present_m = (not m and re.search(r"\b(present|current|ongoing)\b", s, re.I) and not BULLET_RE.match(s) and len(s) < 140)
        if (m or present_m) and not BULLET_RE.match(s) and len(s) < 140:
            if cur:
                entries.append(cur)
            if m:
                start, end = _to_ym(m.group(1)), _to_ym(m.group(2))
                role, company, loc = _role_company(s, prev)
                ranges.append((start, end))
            else:
                start, end = None, None
                clean_s = re.sub(r"\b(present|current|now|today|ongoing)\b", "", s, flags=re.I).strip(" |,-–—")
                role, company, loc = _role_company(clean_s, prev)
            if not role and prev and not BULLET_RE.match(prev) and not RANGE_RE.search(prev) and len(prev) < 100:
                role, company, loc = _role_company(prev, "")
                if "," in role and not company:
                    role, _, company = role.partition(",")
                    role, company = role.strip(), company.strip()
            # If the "role" looks like a company and the previous line looks like a role, swap.
            if prev and _ROLE_WORDS.search(prev) and not _ROLE_WORDS.search(role) and not RANGE_RE.search(prev):
                role, company = prev.strip(" |,-–—"), role or company
            cur = {"company": company, "role": role, "location": loc, "start_date": _fmt(start),
                   "end_date": _fmt(end), "current": end is None, "bullets": []}
        elif cur is not None:
            if BULLET_RE.match(s):
                cur["bullets"].append(BULLET_RE.sub("", s).strip())
            elif cur["bullets"] and not _looks_like_header(s):
                cur["bullets"][-1] += " " + s
            elif not _looks_like_header(s):
                cur["bullets"].append(s)
        prev = s
    if cur:
        entries.append(cur)
    for e in entries:  # a header line followed by a title-like line means the pair was mis-split
        e["bullets"] = [b for b in e["bullets"] if len(b) > 8]
    return entries, ranges


def _looks_like_header(s):
    return len(s) < 60 and bool(_ROLE_WORDS.search(s)) and not s.endswith(".")


def parse_education(lines):
    out, buf = [], []
    for ln in lines:
        s = ln.strip()
        if s:
            buf.append(s)
    i = 0
    while i < len(buf):
        block = buf[i]
        look = " ".join(buf[i:i + 2])
        if DEGREE_RE.search(block) or INSTITUTION_RE.search(block):
            seg = look if not (DEGREE_RE.search(block) and INSTITUTION_RE.search(block)) else block
            year = re.findall(r"(?:19|20)\d{2}", seg)
            deg = DEGREE_RE.search(seg)
            inst = ""
            for piece in re.split(r"\s+[|•·–—-]\s+|,\s+(?=[A-Z])", seg):
                if INSTITUTION_RE.search(piece):
                    inst = re.sub(r"\s*,?\s*(?:19|20)\d{2}\s*$", "", RANGE_RE.sub("", piece)).strip(" ,-")
                    break
            degree = ""
            if deg:
                degree = next((p.strip() for p in re.split(r"\s+[|•·–—-]\s+|,\s+(?=[A-Z])", seg)
                               if DEGREE_RE.search(p)), deg.group(0)).strip()
            gpa = re.search(r"GPA[:\s]*([0-9.]+(?:\s*/\s*[0-9.]+)?)", seg, re.I)
            out.append({"institution": inst, "degree": degree, "graduation_year": year[-1] if year else "",
                        "gpa": gpa.group(1) if gpa else ""})
            i += 2 if look is seg else 1
        else:
            i += 1
    return out


def parse_resume(text):
    """Return (profile, report). report lists which fields were found and which need the user's review."""
    text = (text or "").replace("\r", "")
    lines = [l.rstrip() for l in text.split("\n")]
    nonblank = [l.strip() for l in lines if l.strip()]
    sections = _split_sections(lines)
    header = [l.strip() for l in sections.get("header", []) if l.strip()][:8]

    email = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    phone = re.search(r"(?<!\d)(\+?\(?\d[\d\s().-]{8,16}\d)(?!\d)", "\n".join(header) or text)
    if phone and len(re.sub(r"\D", "", phone.group(1))) not in range(9, 16):
        phone = None
    linkedin = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w%-]+/?", text, re.I)
    github = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+", text, re.I)
    portfolio = re.search(r"(?:https?://)?(?:www\.)?[\w-]+\.(?:vercel\.app|netlify\.app|github\.io|me|dev)(?:/[\w-]*)?", text, re.I)
    if not github and portfolio:
        github = portfolio

    name = ""
    for l in header:
        if "@" in l or re.search(r"\d{3}", l) or "http" in l.lower() or len(l) > 50:
            continue
        words = l.replace(",", " ").split()
        if 2 <= len(words) <= 4 and all(re.match(r"^[A-Za-zÀ-ÿ.'’-]+$", w) for w in words) and not _ROLE_WORDS.search(l):
            name = l.title() if l.isupper() else l
            break

    location = ""
    for l in header:
        m = re.search(r"([A-Z][A-Za-z.\s]+,\s*(?:[A-Z]{2}|[A-Z][a-z]+(?:\s[A-Z][a-z]+)?))\b", re.sub(r"[|•]", " ", l))
        if m and "@" not in m.group(1):
            location = m.group(1).strip()
            break
    if not location:
        for l in header:
            parts = [p.strip() for p in re.split(r"[|•·–—-]", l) if p.strip()]
            for p in parts:
                if "@" not in p and not re.search(r"\d", p) and "http" not in p.lower() and len(p) < 30:
                    if re.match(r"^[A-Z][a-z]+(?:\s[A-Z][a-z]+)?$", p) and not _ROLE_WORDS.search(p):
                        location = p
                        break
            if location:
                break
    if not location and re.search(r"\bremote\b", "\n".join(header), re.I):
        location = "Remote"

    exp, ranges = parse_experience(sections.get("experience", []))
    edu = parse_education(sections.get("education", []))
    years = years_from_ranges(ranges)

    summary = " ".join(l.strip() for l in sections.get("summary", []) if l.strip())[:900]
    if not years and summary:
        ym = re.search(r"(\d+)\+?\s*years?\b.*?\bexperience", summary, re.I)
        if ym:
            years = float(ym.group(1))

    skills_text = "\n".join(sections.get("skills", []))
    explicit = sk.extract(skills_text)
    listed = [s.strip() for s in re.split(r"[,;•|\n]", skills_text) if 2 < len(s.strip()) < 30]
    rest = sk.extract(text)
    skill_list = list(dict.fromkeys(explicit + [s for s in rest if s not in explicit]))
    extras = [s for s in listed if s.lower() not in {x.lower() for x in skill_list} and not sk.extract(s)
              and not re.search(r"\b(languages?|frameworks?|tools|databases)\b\s*:", s, re.I)]
    # Keep unrecognized but explicitly listed skills so non-tech resumes still carry their skills.
    skill_list += [re.sub(r"^[A-Za-z &/]+:\s*", "", s) for s in extras[:25]]
    skill_list = [s for s in dict.fromkeys(skill_list) if s]

    by_cat = {}
    for s in skill_list:
        by_cat.setdefault(sk.CATEGORY_OF.get(s, "Other"), []).append(s)

    target = exp[0]["role"] if exp and exp[0]["role"] else ""
    if (not target or target.lower() == "freelance developer") and summary:
        tm = re.search(r"^([A-Z][A-Za-z\s/-]+?)\s+with\s+\d+", summary, re.I)
        if tm:
            target = tm.group(1).strip()
    from .scoring import derive_target_roles
    tmp_prof = {"target_title": target, "skills": skill_list, "experience": exp}
    target_roles = derive_target_roles(tmp_prof)

    profile = {
        "name": name, "email": email.group(0) if email else "", "phone": phone.group(1).strip() if phone else "",
        "location": location, "linkedin": linkedin.group(0) if linkedin else "", "github": github.group(0) if github else "",
        "target_title": target, "target_roles": target_roles, "years_of_experience": years, "work_mode": "Any",
        "preferred_locations": [location] if location else [], "min_salary": 0, "excluded_keywords": [],
        "preferred_job_types": [], "dream_companies": [], "dream_role": "",
        "summary": summary, "skills": skill_list, "skills_by_category": by_cat,
        "experience": exp, "education": edu,
    }
    checks = {
        "name": bool(name), "email": bool(email), "phone": bool(phone), "location": bool(location),
        "summary": bool(summary), "skills": len(skill_list) >= 3, "experience": bool(exp),
        "experience_bullets": bool(exp) and all(e["bullets"] for e in exp), "education": bool(edu),
    }
    report = {
        "found": [k for k, v in checks.items() if v],
        "needs_review": [k for k, v in checks.items() if not v],
        "years_method": "Merged employment date ranges (overlaps counted once)" if ranges else "No dates found",
        "message": ("Review every field before saving. Fields listed under needs_review were not found in the resume "
                    "and are left blank." if not all(checks.values()) else "All main sections were found."),
        "text_length": len(text),
    }
    if len(nonblank) < 5:
        report["message"] = "Very little text found. Paste the full resume text for a better result."
    return profile, report
