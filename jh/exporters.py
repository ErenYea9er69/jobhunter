"""Resume export: plain text, escaped HTML, real .docx, and a text-based single-column PDF."""
import html
import io
import re
import zipfile

H = {"widths": None}
# Helvetica advance widths (per 1000 em) for ASCII 32..126, used to wrap PDF lines correctly.
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + \
     [278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667,
      778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556,
      556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]


def _sections(r):
    """Normalize a resume into (header_lines, [(title, [blocks])]) shared by every format."""
    contact = " | ".join(x for x in [r.get("email"), r.get("phone"), r.get("location")] if x)
    links = " | ".join(x for x in [r.get("linkedin"), r.get("github")] if x)
    head = [x for x in [r.get("name", ""), contact, links] if x]
    secs = []
    if r.get("summary"):
        secs.append(("PROFESSIONAL SUMMARY", [("p", r["summary"])]))
    if r.get("skills"):
        secs.append(("SKILLS", [("p", ", ".join(r["skills"]))]))
    exp = []
    for e in r.get("experience", []):
        title = " - ".join(x for x in [e.get("role"), e.get("company")] if x)
        dates = " - ".join(x for x in [e.get("start_date"), e.get("end_date")] if x)
        exp.append(("h", title + (f" ({e['location']})" if e.get("location") else ""), dates))
        exp += [("b", b) for b in e.get("bullets", [])]
    if exp:
        secs.append(("PROFESSIONAL EXPERIENCE", exp))
    edu = []
    for e in r.get("education", []):
        line = ", ".join(x for x in [e.get("degree"), e.get("institution")] if x)
        if e.get("graduation_year"):
            line += f" ({e['graduation_year']})"
        edu.append(("p", line))
    if edu:
        secs.append(("EDUCATION", edu))
    return head, secs


def to_txt(r):
    head, secs = _sections(r)
    out = [head[0].upper()] + head[1:] if head else []
    for title, blocks in secs:
        out += ["", title, "-" * 40]
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


def to_pdf(r):
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
        for part in _wrap(s, size, PW - 2 * M - indent):
            if y < M + size:
                new_page()
            text(part, size, bold, M + indent, center)
            y -= size + gap

    for i, h in enumerate(head):
        line(h, 17 if i == 0 else 9.5, bold=(i == 0), center=True, gap=4)
    for title, blocks in secs:
        y -= 6
        if y < M + 40:
            new_page()
        line(title, 10.5, bold=True, gap=1)
        cmds.append(f"{M} {y + 1:.1f} m {PW - M} {y + 1:.1f} l 0.5 w S")
        y -= 3
        for b in blocks:
            if b[0] == "h":
                line(b[1] + (f"   {b[2]}" if b[2] else ""), 10, bold=True)
            elif b[0] == "b":
                line("- " + b[1], 10, indent=10)
            else:
                line(b[1], 10)
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


def safe_name(r, ext):
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", (r.get("name") or "resume").strip()) or "resume"
    return f"{base}_Resume.{ext}"
