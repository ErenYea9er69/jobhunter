"""Cross-source deduplication. Different roles at one company stay separate; true duplicates merge."""
import hashlib
import re
import urllib.parse

from .scoring import title_tokens
from .util import normalize_company, parse_date
from .sources import source_rank, source_kind

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
    return hashlib.sha1(base.encode()).hexdigest()[:16]


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
        entry = {"source": job.get("source", "Unknown"), "url": canonical_url(job.get("url")),
                 "source_credit": job.get("source_credit", job.get("source", "")),
                 "source_tier": job.get("source_tier", ""),
                 "source_rank": job.get("source_rank", source_rank(job.get("source", "Unknown"), job.get("source_tier", ""))),
                 "source_kind": job.get("source_kind", source_kind(job.get("source", "Unknown"), job.get("source_tier", "")))}

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
            g["sources"] = [entry]
            g["source_names"] = [entry["source"]]
            g.setdefault("source_rank", entry["source_rank"])
            g.setdefault("source_kind", entry["source_kind"])
            g["url"] = entry["url"]
            by_company.setdefault(norm_co, []).append(g)
            by_exact[exact_key] = g
            groups.append(g)
            continue

        if not any(s["source"] == entry["source"] and s["url"] == entry["url"] for s in target["sources"]):
            target["sources"].append(entry)
            target["source_names"].append(entry["source"])
        if entry["source_rank"] > target.get("source_rank", 0):
            target.update(url=entry["url"], source=entry["source"], source_tier=entry["source_tier"],
                          source_credit=entry["source_credit"], source_rank=entry["source_rank"],
                          source_kind=entry["source_kind"])
        if len(job.get("description", "")) > len(target.get("description", "")):
            target["description"] = job["description"]
        if job.get("salary") and not target.get("salary"):
            target["salary"] = job["salary"]
        da, db_ = parse_date(target.get("posted_at")), parse_date(job.get("posted_at"))
        if db_ and (not da or db_ > da):
            target["posted_at"] = job["posted_at"]

    for g in groups:
        g.pop("_tk", None)
        g.pop("_lc", None)
        g["job_key"] = job_key(g)
        g["sources"].sort(key=lambda s: (-s.get("source_rank", 0), s["source"]))
    return groups
