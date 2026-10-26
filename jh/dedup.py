"""Cross-source deduplication. Different roles at one company stay separate; true duplicates merge."""
import hashlib
import re
import urllib.parse

from .scoring import title_tokens
from .util import normalize_company, parse_date
from .sources import source_rank, source_kind, is_free_to_apply, apply_cost_note

ATS_SOURCES = ("Greenhouse", "Lever", "Ashby", "SmartRecruiters", "Workable")
TRACKING = re.compile(r"^(utm_|ref|source|gh_src|lever-source|trk|trackingid|refid)", re.I)


def canonical_url(url):
    try:
        p = urllib.parse.urlparse(url or "")
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not TRACKING.match(k)]
        return urllib.parse.urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", urllib.parse.urlencode(q), ""))
    except Exception:
        return url or ""


def _title_key(title):
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", (title or "").lower())
    t = re.split(r"\s+[-–—|@]\s+(?=[a-z]*\s*(?:remote|hybrid|onsite|us|uk|emea|eu|worldwide)\b)", t)[0]
    return " ".join(sorted(title_tokens(t)))


def _loc_class(job):
    loc = f"{job.get('location', '')} {job.get('work_mode', '')}".lower()
    if any(w in loc for w in ("remote", "anywhere", "worldwide")):
        return "remote"
    return re.sub(r"[^a-z]", "", loc.split(",")[0].split("/")[0])[:12] or "unknown"


def job_key(job):
    base = f"{normalize_company(job.get('company'))}|{_title_key(job.get('title'))}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def _jaccard(a, b):
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def _same_job(a, b):
    ka = a.get("_tk") or _title_key(a.get("title", ""))
    kb = b.get("_tk") or _title_key(b.get("title", ""))
    if not ka or not kb:
        return False
    if ka != kb and _jaccard(ka, kb) < 0.85:
        return False
    la = a.get("_lc") or _loc_class(a)
    lb = b.get("_lc") or _loc_class(b)
    return la == lb or "unknown" in (la, lb) or "remote" in (la, lb)


def merge_jobs(raw_jobs):
    groups = []  # list of canonical jobs
    by_company = {}
    by_exact = {}  # (company, title_key, loc_class) -> canonical job

    for job in raw_jobs:
        if not job.get("title") or not job.get("company"):
            continue
        job["_tk"] = _title_key(job.get("title", ""))
        job["_lc"] = _loc_class(job)
        norm_co = normalize_company(job["company"])

        is_free = job.get("is_free_to_apply")
        if is_free is None:
            is_free = is_free_to_apply(job.get("source", "Unknown"))
        cost_note = job.get("apply_cost_note") or apply_cost_note(job.get("source", "Unknown"))

        entry = {
            "source": job.get("source", "Unknown"),
            "url": canonical_url(job.get("url")),
            "source_credit": job.get("source_credit", job.get("source", "")),
            "source_tier": job.get("source_tier", ""),
            "source_rank": job.get("source_rank", source_rank(job.get("source", "Unknown"), job.get("source_tier", ""))),
            "source_kind": job.get("source_kind", source_kind(job.get("source", "Unknown"), job.get("source_tier", ""))),
            "is_free_to_apply": is_free,
            "apply_cost_note": cost_note
        }

        direct_entry = None
        if job.get("direct_apply_url"):
            direct_entry = {
                "source": "Official ATS",
                "url": canonical_url(job["direct_apply_url"]),
                "source_credit": "Direct Official Application (found in posting)",
                "source_tier": "Direct company ATS",
                "source_rank": 99,
                "source_kind": "Direct employer ATS",
                "is_free_to_apply": True,
                "apply_cost_note": "100% Free Official Employer ATS (no middleman)"
            }

        # Fast path 1: exact company + title_key + loc match
        exact_key = (norm_co, job["_tk"], job["_lc"])
        target = by_exact.get(exact_key)

        # Fast path 2: exact company + title_key (one is remote or unknown)
        if target is None and (job["_lc"] in ("remote", "unknown")):
            target = by_exact.get((norm_co, job["_tk"], "remote")) or by_exact.get((norm_co, job["_tk"], "unknown"))

        # Fallback: scan fuzzy candidates within same company only
        if target is None:
            cands = by_company.setdefault(norm_co, [])
            target = next((g for g in cands if _same_job(g, job)), None)

        if target is None:
            g = dict(job)
            all_entries = [entry]
            if direct_entry:
                all_entries.insert(0, direct_entry)
            g["sources"] = all_entries
            g["source_names"] = [s["source"] for s in all_entries]
            prime = all_entries[0]
            g["url"] = prime["url"]
            g["source"] = prime["source"]
            g["source_rank"] = prime["source_rank"]
            g["source_kind"] = prime["source_kind"]
            g["is_free_to_apply"] = prime["is_free_to_apply"]
            g["apply_cost_note"] = prime["apply_cost_note"]
            by_company.setdefault(norm_co, []).append(g)
            by_exact[exact_key] = g
            groups.append(g)
            continue

        new_entries = [entry]
        if direct_entry:
            new_entries.append(direct_entry)

        for ent in new_entries:
            if not any(s["source"] == ent["source"] and s["url"] == ent["url"] for s in target["sources"]):
                target["sources"].append(ent)
                if ent["source"] not in target["source_names"]:
                    target["source_names"].append(ent["source"])

            # Rule: 100% Free application sources ALWAYS beat paid/gated sources!
            is_ent_free = ent.get("is_free_to_apply", True)
            is_target_free = target.get("is_free_to_apply", True)

            should_replace = False
            if is_ent_free and not is_target_free:
                should_replace = True
            elif is_ent_free == is_target_free and ent["source_rank"] > target.get("source_rank", 0):
                should_replace = True

            if should_replace:
                target.update(
                    url=ent["url"],
                    source=ent["source"],
                    source_tier=ent["source_tier"],
                    source_credit=ent["source_credit"],
                    source_rank=ent["source_rank"],
                    source_kind=ent["source_kind"],
                    is_free_to_apply=ent["is_free_to_apply"],
                    apply_cost_note=ent.get("apply_cost_note", "")
                )

        if len(job.get("description", "")) > len(target.get("description", "")):
            target["description"] = job["description"]
        if job.get("salary") and not target.get("salary"):
            target["salary"] = job["salary"]
        if job.get("job_type") and not target.get("job_type"):
            target["job_type"] = job["job_type"]
        if job.get("seniority") and not target.get("seniority"):
            target["seniority"] = job["seniority"]
        if job.get("contact_email") and not target.get("contact_email"):
            target["contact_email"] = job["contact_email"]
        if job.get("contact_website") and not target.get("contact_website"):
            target["contact_website"] = job["contact_website"]
        if job.get("how_to_apply") and not target.get("how_to_apply"):
            target["how_to_apply"] = job["how_to_apply"]
        if job.get("responsibilities") and not target.get("responsibilities"):
            target["responsibilities"] = job["responsibilities"]
        if job.get("qualifications") and not target.get("qualifications"):
            target["qualifications"] = job["qualifications"]
        if job.get("preferred_qualifications") and not target.get("preferred_qualifications"):
            target["preferred_qualifications"] = job["preferred_qualifications"]
        if job.get("enriched"):
            target["enriched"] = True
            target["needs_enrichment"] = False
        da, db_ = parse_date(target.get("posted_at")), parse_date(job.get("posted_at"))
        if db_ and (not da or db_ > da):
            target["posted_at"] = job["posted_at"]

    for g in groups:
        g.pop("_tk", None)
        g.pop("_lc", None)
        g["job_key"] = job_key(g)
        # Sort: 100% Free sources FIRST, then highest authority rank, then source name
        g["sources"].sort(key=lambda s: (not s.get("is_free_to_apply", True), -s.get("source_rank", 0), s["source"]))
        best_src = g["sources"][0]
        g["url"] = best_src["url"]
        g["source"] = best_src["source"]
        g["source_tier"] = best_src.get("source_tier", g.get("source_tier", ""))
        g["source_rank"] = best_src.get("source_rank", g.get("source_rank", 50))
        g["source_kind"] = best_src.get("source_kind", g.get("source_kind", "Job source"))
        g["is_free_to_apply"] = best_src.get("is_free_to_apply", True)
        g["apply_cost_note"] = best_src.get("apply_cost_note", "")

    return groups


def resolve_duplicates_5stage(postings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Execute the 5-stage duplicate resolution from Section 9.1 of newall-logic.md.

    Stages:
    1. Provider identity (same source + provider job id)
    2. Canonical source URL (same stripped url)
    3. Employer and role key (normalized company + title key + location)
    4. Description fingerprint (Jaccard similarity >= 0.85 on description)
    5. Merge decision (auto-merge high-confidence, keep source links and separate apply_urls)
    """
    if not postings:
        return [], []

    merged: list[dict] = []
    uncertain: list[dict] = []

    for post in postings:
        job = dict(post)
        if not job.get("title") or not job.get("company"):
            continue

        c_url = canonical_url(job.get("url") or job.get("source_url") or "")
        apply_url = job.get("apply_url") or job.get("applicationLink") or c_url
        src_name = job.get("source", "Unknown")
        jid = str(job.get("id") or "")
        co = normalize_company(job.get("company", ""))
        tk = _title_key(job.get("title", ""))
        lc = _loc_class(job)
        desc = (job.get("description") or "").lower()

        src_record = {
            "source": src_name,
            "id": jid,
            "url": c_url,
            "apply_url": apply_url,
            "posted_at": job.get("posted_at", ""),
            "source_tier": job.get("source_tier", ""),
            "source_rank": source_rank(src_name, job.get("source_tier", "")),
            "is_free_to_apply": is_free_to_apply(src_name),
        }

        matched_target = None
        for cand in merged:
            # Stage 1: Provider identity
            cand_sources = cand.get("sources", [])
            stage1_match = False
            for s in cand_sources:
                if s.get("source") == src_name and jid and s.get("id") == jid:
                    stage1_match = True
                    break
            if stage1_match:
                matched_target = cand
                break

            # Stage 2: Canonical source URL
            cand_url = canonical_url(cand.get("source_url") or cand.get("url") or "")
            if c_url and cand_url and c_url == cand_url:
                matched_target = cand
                break

            # Stage 3: Employer and role key
            cand_co = normalize_company(cand.get("company", ""))
            cand_tk = _title_key(cand.get("title", ""))
            cand_lc = _loc_class(cand)

            if co and cand_co and co == cand_co:
                if tk and cand_tk and (tk == cand_tk or _jaccard(tk, cand_tk) >= 0.85):
                    if lc == cand_lc or "remote" in (lc, cand_lc) or "unknown" in (lc, cand_lc):
                        matched_target = cand
                        break

            # Stage 4: Description fingerprint
            if co and cand_co and co == cand_co and desc and cand.get("description"):
                cand_desc = cand["description"].lower()
                if len(desc) > 100 and len(cand_desc) > 100:
                    sim = _jaccard(desc[:1000], cand_desc[:1000])
                    if sim >= 0.85:
                        matched_target = cand
                        break

        if matched_target is not None:
            # Stage 5: Merge decision
            matched_target["sources"].append(src_record)
            if len(desc) > len(matched_target.get("description", "")):
                matched_target["description"] = job.get("description", "")
            if not matched_target.get("salary") and job.get("salary"):
                matched_target["salary"] = job["salary"]
            if not matched_target.get("work_mode") and job.get("work_mode"):
                matched_target["work_mode"] = job["work_mode"]
        else:
            new_canonical = dict(job)
            new_canonical["source_url"] = c_url
            new_canonical["apply_url"] = apply_url
            new_canonical["sources"] = [src_record]
            merged.append(new_canonical)

    return merged, uncertain
