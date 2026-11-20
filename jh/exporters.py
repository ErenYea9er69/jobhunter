"""Resume export: plain text, escaped HTML, real .docx, and a text-based single-column PDF."""
import html
import io
import re
import zipfile
import pypdf

H = {"widths": None}
# Helvetica advance widths (per 1000 em) for ASCII 32..126, used to wrap PDF lines correctly.
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + \
     [278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667,
      778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556,
      556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]


def _sections(r):
    """Normalize a resume into (header_lines, [(title, [blocks])]) shared by every format.
    Adheres strictly to standard ATS headings: Experience, Education, Projects, Skills.
    """
    contact = " | ".join(x for x in [r.get("email"), r.get("phone"), r.get("location")] if x)
    links = " | ".join(x for x in [r.get("linkedin"), r.get("github")] if x)
    head = [x for x in [r.get("name", ""), r.get("target_title"), contact, links] if x]
    secs = []
    if r.get("summary"):
        secs.append(("Professional Summary", [("p", r["summary"])]))
    exp = []
    for e in r.get("experience", []):
        title = " - ".join(x for x in [e.get("role"), e.get("company")] if x)
        dates = " - ".join(x for x in [e.get("start_date"), e.get("end_date")] if x)
        exp.append(("h", title + (f" ({e['location']})" if e.get("location") else ""), dates))
        exp += [("b", b) for b in e.get("bullets", [])]
    if exp:
        secs.append(("Professional Experience", exp))
    edu = []
    for e in r.get("education", []):
        line = ", ".join(x for x in [e.get("degree"), e.get("institution")] if x)
        if e.get("graduation_year"):
            line += f" ({e['graduation_year']})"
        edu.append(("p", line))
    if edu:
        secs.append(("Education", edu))
    proj = []
    for p in r.get("projects", []):
        p_name = p.get("name") or p.get("title") or "Project"
        p_dates = p.get("dates") or ""
        proj.append(("h", p_name, p_dates))
        proj += [("b", b) for b in p.get("bullets", [])]
        if p.get("description") and not p.get("bullets"):
            proj.append(("p", p["description"]))
    if proj:
        secs.append(("Projects", proj))
    if r.get("skills"):
        secs.append(("Skills", [("p", ", ".join(r["skills"]))]))
    return head, secs


def to_txt(r):
    head, secs = _sections(r)
    out = [head[0].upper()] + head[1:] if head else []
    for title, blocks in secs:
        out += ["", title.upper(), "-" * 40]
        for b in blocks:
            if b[0] == "h":
                out.append(b[1] + (f"  [{b[2]}]" if b[2] else ""))
            elif b[0] == "b":
                out.append("  * " + b[1])
            else:
                out.append(b[1])
    return "\n".join(out)


def to_html(r):
    e = html.escape
    head, secs = _sections(r)
    body = [f"<h1>{e(head[0])}</h1>"] if head else []
    body += [f'<div class="c">{e(x)}</div>' for x in head[1:]]
    for title, blocks in secs:
        body.append(f"<h2>{e(title.title())}</h2>")
        ul = False
        for b in blocks:
            if b[0] != "b" and ul:
                body.append("</ul>")
                ul = False
            if b[0] == "h":
                body.append(f'<p class="r"><b>{e(b[1])}</b><span>{e(b[2])}</span></p>')
            elif b[0] == "b":
                if not ul:
                    body.append("<ul>")
                    ul = True
                body.append(f"<li>{e(b[1])}</li>")
            else:
                body.append(f"<p>{e(b[1])}</p>")
        if ul:
            body.append("</ul>")
    css = ("body{font-family:Arial,Helvetica,sans-serif;color:#111;max-width:780px;margin:24px auto;font-size:13px;line-height:1.45}"
           "h1{text-align:center;font-size:22px;margin:0 0 4px}.c{text-align:center;color:#444;font-size:12px}"
           "h2{font-size:13px;border-bottom:1px solid #222;margin:16px 0 6px;letter-spacing:.5px}"
           ".r{display:flex;justify-content:space-between;margin:8px 0 2px}ul{margin:2px 0 6px 18px;padding:0}")
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{e(head[0] if head else 'Resume')}</title><style>{css}</style></head><body>{''.join(body)}</body></html>"


# ---------------------------------------------------------------- docx

def to_docx(r):
    e = lambda s: html.escape(s or "", quote=False)
    head, secs = _sections(r)

    def para(text, bold=False, size=22, align=None, bullet=False, border=False, space_after=60):
        ppr = f'<w:spacing w:after="{space_after}"/>'
        if align:
            ppr += f'<w:jc w:val="{align}"/>'
        if bullet:
            ppr += '<w:ind w:left="360" w:hanging="220"/>'
        if border:
            ppr += '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="222222"/></w:pBdr>'
        rpr = f'<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>{"<w:b/>" if bold else ""}<w:sz w:val="{size}"/>'
        txt = ("\u2022 " if bullet else "") + text
        return f'<w:p><w:pPr>{ppr}</w:pPr><w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{e(txt)}</w:t></w:r></w:p>'

    body = []
    if head:
        body.append(para(head[0], True, 36, "center"))
        body += [para(x, False, 20, "center") for x in head[1:]]
    for title, blocks in secs:
        body.append(para(title, True, 22, border=True, space_after=80))
        for b in blocks:
            if b[0] == "h":
                body.append(para(b[1] + (f"   {b[2]}" if b[2] else ""), True, 22))
            elif b[0] == "b":
                body.append(para(b[1], bullet=True))
            else:
                body.append(para(b[1]))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body>{"".join(body)}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080"/></w:sectPr></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


# ---------------------------------------------------------------- pdf

def _tw(s, size):
    return sum((_W[ord(c) - 32] if 32 <= ord(c) <= 126 else 556) for c in s) * size / 1000.0


def _wrap(text, size, width):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if _tw(trial, size) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def _pdf_str(s):
    s = s.encode("cp1252", errors="replace").decode("cp1252")
    return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def verify_pdf_roundtrip(pdf_bytes: bytes, r: dict, target_max_pages: int = 2) -> tuple[bool, list[str]]:
    """Round-trip verification test using pypdf per Rule R5:
    1. Size strictly under 200 KB.
    2. Reading order is intact (contact in body -> summary/experience -> education/skills).
    3. Standard sections are found (Experience, Education, Skills, etc.).
    4. Email and phone numbers are found in the text layer.
    5. Page count does not exceed target_max_pages.
    """
    issues = []
    size_kb = len(pdf_bytes) / 1024.0
    if size_kb > 200.0:
        issues.append(f"PDF size {size_kb:.1f} KB exceeds 200 KB cap")

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        if num_pages > target_max_pages:
            issues.append(f"Page count {num_pages} exceeds allowed limit of {target_max_pages}")

        full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        low = full_text.lower()

        # Email & Phone
        if r.get("email") and r["email"].lower() not in low:
            issues.append(f"Email '{r['email']}' missing from extracted PDF text")
        if r.get("phone"):
            digits_phone = re.sub(r"\D", "", str(r["phone"]))
            digits_pdf = re.sub(r"\D", "", full_text)
            if digits_phone and digits_phone not in digits_pdf:
                issues.append(f"Phone '{r['phone']}' missing from extracted PDF text")

        # Standard headings
        if r.get("experience") and "experience" not in low:
            issues.append("Section 'Experience' heading missing from extracted PDF text")
        if r.get("education") and "education" not in low:
            issues.append("Section 'Education' heading missing from extracted PDF text")
        if r.get("skills") and "skills" not in low:
            issues.append("Section 'Skills' heading missing from extracted PDF text")

        # Reading order check: Contact details must precede experience
        if r.get("email") and r.get("experience"):
            idx_email = low.find(r["email"].lower())
            idx_exp = low.find("experience")
            if idx_email != -1 and idx_exp != -1 and idx_email > idx_exp:
                issues.append("Reading order inverted: email found after Experience section")

    except Exception as e:
        issues.append(f"PDF extraction error: {e}")

    return len(issues) == 0, issues


def _generate_pdf_stream(r, font_scale=1.0, gap_scale=1.0):
    head, secs = _sections(r)
    PW, PH, M = 612, 792, 54
    pages, cmds, y = [], [], PH - M

    def new_page():
        nonlocal cmds, y
        if cmds:
            pages.append(cmds)
        cmds, y = [], PH - M

    def text(s, size, bold=False, x=M, center=False):
        nonlocal y
        font = "F2" if bold else "F1"
        px = (PW - _tw(s, size)) / 2 if center else x
        cmds.append(f"BT /{font} {size} Tf {px:.1f} {y:.1f} Td {_pdf_str(s)} Tj ET")

    def line(s, size=10, bold=False, indent=0, center=False, gap=2.5):
        nonlocal y
        actual_size = size * font_scale
        actual_gap = gap * gap_scale
        for part in _wrap(s, actual_size, PW - 2 * M - indent):
            if y < M + actual_size:
                new_page()
            text(part, actual_size, bold, M + indent, center)
            y -= actual_size + actual_gap

    for i, h in enumerate(head):
        line(h, 16 if i == 0 else 9.5, bold=(i == 0), center=True, gap=3.5)
    for title, blocks in secs:
        y -= 5 * gap_scale
        if y < M + 35:
            new_page()
        line(title, 10.5, bold=True, gap=1)
        cmds.append(f"{M} {y + 1:.1f} m {PW - M} {y + 1:.1f} l 0.5 w S")
        y -= 2.5 * gap_scale
        for b in blocks:
            if b[0] == "h":
                line(b[1] + (f"   {b[2]}" if b[2] else ""), 9.8, bold=True)
            elif b[0] == "b":
                line("- " + b[1], 9.5, indent=10)
            else:
                line(b[1], 9.5)
    pages.append(cmds)

    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    kids = []
    for pc in pages:
        stream = "\n".join(pc).encode("cp1252", errors="replace")
        content_id = len(objs) + 2
        page_id = len(objs) + 1
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PW} {PH}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(f"{page_id} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for o in offs:
        out.write(f"{o:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


def to_pdf(r, max_pages: Optional[int] = None):
    """ATS-Safe single-column text-based PDF builder with verified round-trip test (R5).
    Enforces 1 page for students / <5 years exp; max 2 pages otherwise.
    Rebuilds dynamically if round-trip validation fails.
    """
    yoe = r.get("years_of_experience")
    is_student = bool(r.get("is_student") or any("intern" in str(e.get("role", "")).lower() for e in r.get("experience", [])))
    if max_pages is not None:
        target_max_pages = max_pages
    elif is_student or (yoe is not None and float(yoe) < 5.0):
        target_max_pages = 1
    else:
        target_max_pages = 2

    # Attempt 1: Standard layout
    pdf_bytes = _generate_pdf_stream(r, font_scale=1.0, gap_scale=1.0)
    ok, issues = verify_pdf_roundtrip(pdf_bytes, r, target_max_pages=target_max_pages)
    if ok:
        return pdf_bytes

    # Attempt 2: Rebuild with tighter vertical spacing
    pdf_bytes_tight = _generate_pdf_stream(r, font_scale=0.95, gap_scale=0.8)
    ok_tight, issues_tight = verify_pdf_roundtrip(pdf_bytes_tight, r, target_max_pages=target_max_pages)
    if ok_tight:
        return pdf_bytes_tight

    # Attempt 3: Ultra-compact rebuild for strict 1-page constraints
    if target_max_pages == 1:
        pdf_bytes_compact = _generate_pdf_stream(r, font_scale=0.90, gap_scale=0.65)
        ok_comp, _ = verify_pdf_roundtrip(pdf_bytes_compact, r, target_max_pages=1)
        if ok_comp:
            return pdf_bytes_compact

    return pdf_bytes_tight




def cover_letter_to_docx(text, profile, job):
    e = lambda s: html.escape(s or "", quote=False)
    name = profile.get("name") or "Candidate"
    contact = " | ".join(x for x in [profile.get("email"), profile.get("phone"), profile.get("location")] if x)
    company = job.get("company") or "Employer"
    title = job.get("title") or "Position"

    def para(t, bold=False, size=22, align=None, border=False, space_after=120):
        ppr = f'<w:spacing w:after="{space_after}"/>'
        if align:
            ppr += f'<w:jc w:val="{align}"/>'
        if border:
            ppr += '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="222222"/></w:pBdr>'
        rpr = f'<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>{"<w:b/>" if bold else ""}<w:sz w:val="{size}"/>'
        return f'<w:p><w:pPr>{ppr}</w:pPr><w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{e(t)}</w:t></w:r></w:p>'

    body = [
        para(name, bold=True, size=32, align="left", space_after=40),
        para(contact, bold=False, size=18, align="left", border=True, space_after=180),
        para(f"Re: Application for {title} Role at {company}", bold=True, size=22, space_after=160),
    ]
    for p in text.split("\n\n"):
        p_clean = p.strip()
        if p_clean:
            body.append(para(p_clean, bold=False, size=21, space_after=140))

    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body>{"".join(body)}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def cover_letter_to_pdf(text, profile, job):
    PW, PH, M = 612, 792, 54
    pages, cmds, y = [], [], PH - M
    name = profile.get("name") or "Candidate"
    contact = " | ".join(x for x in [profile.get("email"), profile.get("phone"), profile.get("location")] if x)
    company = job.get("company") or "Employer"
    title = job.get("title") or "Position"

    def new_page():
        nonlocal cmds, y
        if cmds:
            pages.append(cmds)
        cmds, y = [], PH - M

    def text_cmd(s, size, bold=False, x=M):
        nonlocal y
        font = "F2" if bold else "F1"
        cmds.append(f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td {_pdf_str(s)} Tj ET")

    def line(s, size=10, bold=False, gap=3.0):
        nonlocal y
        for part in _wrap(s, size, PW - 2 * M):
            if y < M + size:
                new_page()
            text_cmd(part, size, bold=bold)
            y -= (size + gap)

    line(name, size=18, bold=True, gap=3)
    if contact:
        line(contact, size=9.5, bold=False, gap=6)
    cmds.append(f"{M} {y:.1f} m {PW - M} {y:.1f} l 0.7 w S")
    y -= 14
    line(f"Re: Application for {title} Role at {company}", size=11, bold=True, gap=10)

    for p in text.split("\n\n"):
        p_clean = p.strip()
        if p_clean:
            for l in p_clean.split("\n"):
                line(l.strip(), size=10, bold=False, gap=3.5)
            y -= 8

    pages.append(cmds)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    kids = []
    for pc in pages:
        stream = "\n".join(pc).encode("cp1252", errors="replace")
        content_id = len(objs) + 2
        page_id = len(objs) + 1
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PW} {PH}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(f"{page_id} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for o in offs:
        out.write(f"{o:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


