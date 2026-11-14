"""Modern Signal Radar: source adapters, collection, scoring, freshness, and ledger checks."""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from . import config, db, dedup, home
from .util import now_iso, parse_date

log = logging.getLogger("jobhunter.signals")


class SignalAdapter:
    """Base source adapter for modern outreach signals."""

    def __init__(self, name: str, mode: str, kind: str, enabled: bool, terms_note: str):
        self.name = name
        self.mode = mode  # "modern" or "classic"
        self.kind = kind  # "hiring_post" or "funding"
        self.enabled = enabled
        self.terms_note = terms_note

    def fetch(self, target_role: str = "", region: str = "") -> List[Dict[str, Any]]:
        raise NotImplementedError


class HackerNewsHiringAdapter(SignalAdapter):
    """Fetches hiring posts from Hacker News 'Who is hiring' threads via Algolia API."""

    def __init__(self):
        super().__init__(
            name="HackerNews",
            mode="modern",
            kind="hiring_post",
            enabled=True,
            terms_note="Uses public Hacker News Algolia Search API. Follows rate limits."
        )

    def fetch(self, target_role: str = "", region: str = "") -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        signals = []
        try:
            # Search recent comments in whoishiring threads
            query = urllib.parse.quote(target_role or "hiring")
            url = f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=comment&hitsPerPage=25"
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            now_dt = datetime.datetime.now(datetime.timezone.utc)
            for hit in data.get("hits", []):
                comment_text = hit.get("comment_text") or ""
                if not comment_text or len(comment_text) < 40:
                    continue

                # Strip basic HTML tags
                clean_text = re.sub(r"<[^>]+>", " ", comment_text)
                clean_text = re.sub(r"\s+", " ", clean_text).strip()

                # Basic extraction of company name from first line (e.g. "Stripe | San Francisco | Remote")
                first_line = clean_text.split(".")[0]
                parts = [p.strip() for p in first_line.split("|") if p.strip()]
                company = parts[0] if parts else hit.get("author") or "Startup"
                if len(company) > 60:
                    company = company[:60]

                posted_at = hit.get("created_at") or now_dt.isoformat()
                author = hit.get("author") or ""
                object_id = str(hit.get("objectID") or "")
                post_url = f"https://news.ycombinator.com/item?id={object_id}"
                url_hash = f"hn:{object_id}"

                signals.append({
                    "id": f"sig_hn_{object_id}",
                    "type": "hiring_post",
                    "source": "HackerNews",
                    "url": post_url,
                    "url_hash": url_hash,
                    "author_name": author,
                    "author_url": f"https://news.ycombinator.com/user?id={author}" if author else "",
                    "company": company,
                    "company_domain": "",
                    "text": clean_text[:1200],
                    "posted_at": posted_at,
                    "likes": hit.get("points") or 0,
                    "comments": 0,
                    "found_at": now_dt.isoformat(),
                    "role_guess": target_role or "Software Engineer",
                    "stage": "any",
                    "region": region or "any",
                })
        except Exception as e:
            log.warning("HackerNewsHiringAdapter fetch error: %s", e)

        return signals


class RedditHiringAdapter(SignalAdapter):
    """Fetches hiring posts from Reddit tech hiring subreddits via public JSON API."""

    def __init__(self):
        super().__init__(
            name="Reddit",
            mode="modern",
            kind="hiring_post",
            enabled=True,
            terms_note="Uses public Reddit listing JSON with custom user-agent. Respects rate limits."
        )

    def fetch(self, target_role: str = "", region: str = "") -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        signals = []
        try:
            url = "https://www.reddit.com/r/forhire/new.json?limit=25"
            req = urllib.request.Request(url, headers={"User-Agent": "JobHunter-Bot/1.0 (local personal tool)"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            now_dt = datetime.datetime.now(datetime.timezone.utc)
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                title = post.get("title", "")
                # Only hiring posts
                if not (title.startswith("[Hiring]") or "[hiring]" in title.lower()):
                    continue

                selftext = post.get("selftext", "")
                author = post.get("author", "")
                post_id = post.get("id", "")
                post_url = f"https://reddit.com{post.get('permalink', '')}"
                created_utc = post.get("created_utc", 0)
                posted_dt = datetime.datetime.fromtimestamp(created_utc, tz=datetime.timezone.utc) if created_utc else now_dt

                # Extract company
                comp_match = re.search(r"at\s+([A-Za-z0-9\s.,]+)", title)
                company = comp_match.group(1).strip() if comp_match else "Hiring Team"
                if len(company) > 50:
                    company = company[:50]

                signals.append({
                    "id": f"sig_rd_{post_id}",
                    "type": "hiring_post",
                    "source": "Reddit",
                    "url": post_url,
                    "url_hash": f"rd:{post_id}",
                    "author_name": author,
                    "author_url": f"https://reddit.com/u/{author}",
                    "company": company,
                    "company_domain": "",
                    "text": f"{title}\n{selftext}"[:1200],
                    "posted_at": posted_dt.isoformat(),
                    "likes": post.get("ups") or 0,
                    "comments": post.get("num_comments") or 0,
                    "found_at": now_dt.isoformat(),
                    "role_guess": target_role or "Software Engineer",
                    "stage": "any",
                    "region": region or "any",
                })
        except Exception as e:
            log.warning("RedditHiringAdapter fetch error: %s", e)

        return signals


class TechFundingFeedAdapter(SignalAdapter):
    """Fetches funding announcements from tech press RSS feeds."""

    def __init__(self):
        super().__init__(
            name="TechFundingFeed",
            mode="modern",
            kind="funding",
            enabled=True,
            terms_note="Reads public tech funding RSS feed without scraping protected areas."
        )

    def fetch(self, target_role: str = "", region: str = "") -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        signals = []
        try:
            # Public RSS feed
            feed_url = "https://techcrunch.com/category/fundings-exits/feed/"
            req = urllib.request.Request(feed_url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                xml_data = resp.read().decode("utf-8", errors="ignore")

            # Lightweight XML extraction without heavy dependencies
            items = re.findall(r"<item>(.*?)</item>", xml_data, re.DOTALL)
            now_dt = datetime.datetime.now(datetime.timezone.utc)

            for item in items[:20]:
                title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item) or re.search(r"<title>(.*?)</title>", item)
                title = title_m.group(1).strip() if title_m else ""

                link_m = re.search(r"<link>(.*?)</link>", item)
                link = link_m.group(1).strip() if link_m else ""

                pub_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
                pub_date = pub_m.group(1).strip() if pub_m else now_dt.isoformat()

                desc_m = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", item) or re.search(r"<description>(.*?)</description>", item)
                desc = desc_m.group(1).strip() if desc_m else ""
                clean_desc = re.sub(r"<[^>]+>", " ", desc).strip()

                # Extract company and funding amount from title e.g. "Acme raises $15M Series A for AI"
                comp_match = re.search(r"^([A-Za-z0-9\s]+?)\s+(?:raises|secures|bags|closes|nabs)\s+(\$[0-9.]+[M|B|K]?)\s*(.*?)$", title, re.IGNORECASE)
                if comp_match:
                    company = comp_match.group(1).strip()
                    amount = comp_match.group(2).strip()
                    round_info = comp_match.group(3).strip()
                else:
                    first_words = title.split()[:2]
                    company = " ".join(first_words)
                    amount = ""
                    round_info = ""

                # Determine stage
                stage = "seed"
                if "series a" in title.lower():
                    stage = "series A"
                elif "series b" in title.lower():
                    stage = "series B"
                elif "pre-seed" in title.lower():
                    stage = "pre-seed"

                hash_id = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]

                signals.append({
                    "id": f"sig_fund_{hash_id}",
                    "type": "funding",
                    "source": "TechFundingFeed",
                    "url": link,
                    "url_hash": f"feed:{hash_id}",
                    "author_name": "TechCrunch",
                    "author_url": "https://techcrunch.com",
                    "company": company,
                    "company_domain": "",
                    "text": f"{title}\n{clean_desc}"[:1200],
                    "posted_at": pub_date,
                    "likes": 0,
                    "comments": 0,
                    "found_at": now_dt.isoformat(),
                    "funding_amount": amount,
                    "funding_round": round_info,
                    "role_guess": target_role or "Engineering / Product",
                    "stage": stage,
                    "region": "any",
                })
        except Exception as e:
            log.warning("TechFundingFeedAdapter fetch error: %s", e)

        return signals


class LinkedInPostsAdapter(SignalAdapter):
    """LinkedIn posts adapter - disabled by default (requires official enterprise API to prevent ToS violations)."""

    def __init__(self):
        super().__init__(
            name="LinkedInPosts",
            mode="modern",
            kind="hiring_post",
            enabled=False,
            terms_note="Automated scraping of LinkedIn personal posts is prohibited by LinkedIn User Agreement. Set enabled=True only with sanctioned Enterprise API credentials."
        )

    def fetch(self, target_role: str = "", region: str = "") -> List[Dict[str, Any]]:
        return []


class XPostsAdapter(SignalAdapter):
    """X / Twitter posts adapter - disabled by default (requires official X API v2 credentials)."""

    def __init__(self):
        super().__init__(
            name="XPosts",
            mode="modern",
            kind="hiring_post",
            enabled=False,
            terms_note="Direct scraping of X is barred by terms. Requires official X API v2 Bearer Token."
        )

    def fetch(self, target_role: str = "", region: str = "") -> List[Dict[str, Any]]:
        return []


# Adapter Registry
ACTIVE_MODERN_ADAPTERS: List[SignalAdapter] = [
    HackerNewsHiringAdapter(),
    RedditHiringAdapter(),
    TechFundingFeedAdapter(),
    LinkedInPostsAdapter(),
    XPostsAdapter(),
]


def list_signal_adapters() -> List[Dict[str, Any]]:
    return [
        {
            "name": a.name,
            "mode": a.mode,
            "kind": a.kind,
            "enabled": a.enabled,
            "terms_note": a.terms_note,
        }
        for a in ACTIVE_MODERN_ADAPTERS
    ]


def evaluate_signal_freshness(sig_type: str, posted_at: str, likes: int = 0) -> str:
    """Freshness rule:
    - hiring_post: fresh if < 24 hours old and < 100 likes. Otherwise 'late'.
    - funding: fresh if < 14 days old. Otherwise 'late'.
    """
    if not posted_at:
        return "fresh"

    try:
        p_dt = parse_date(posted_at)
        if not p_dt:
            return "fresh"

        now_dt = datetime.datetime.now(datetime.timezone.utc)
        age_hours = max(0.0, (now_dt - p_dt).total_seconds() / 3600.0)

        if sig_type == "hiring_post":
            if age_hours < 24.0 and likes < 100:
                return "fresh"
            return "late"
        elif sig_type == "funding":
            age_days = age_hours / 24.0
            if age_days < 14.0:
                return "fresh"
            return "late"
    except Exception:
        pass

    return "fresh"


def score_signal(signal: Dict[str, Any], profile: Dict[str, Any], target_role: str = "", target_stage: str = "any", target_region: str = "any") -> int:
    """Score signal from 0 to 100:
    - Freshness: 40 points
    - Fit to profile & target role: 30 points
    - Founder-led post: 10 points
    - Low reach: 10 points
    - Stage & region match: 10 points
    """
    score = 0
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    sig_type = signal.get("type", "hiring_post")
    posted_at = signal.get("posted_at")
    likes = int(signal.get("likes") or 0)
    text = (signal.get("text") or "").lower()

    # 1. Freshness (40 pts)
    age_hours = 0.0
    if posted_at:
        d = parse_date(posted_at)
        if d:
            age_hours = max(0.0, (now_dt - d).total_seconds() / 3600.0)

    status = evaluate_signal_freshness(sig_type, posted_at, likes)
    if status == "fresh":
        if sig_type == "hiring_post":
            if age_hours <= 6.0:
                score += 40
            elif age_hours <= 12.0:
                score += 35
            else:
                score += 30
        else:
            age_days = age_hours / 24.0
            if age_days <= 3.0:
                score += 40
            elif age_days <= 7.0:
                score += 35
            else:
                score += 30
    else:
        score += 10  # Late signals get minimal freshness points

    # 2. Fit to profile and target role (30 pts)
    cand_role = (target_role or profile.get("target_title") or "").lower()
    cand_skills = [s.lower() for s in (profile.get("skills") or [])]
    role_match = 0
    if cand_role and (cand_role in text or cand_role in (signal.get("role_guess") or "").lower()):
        role_match = 20
    elif any(token in text for token in cand_role.split() if len(token) > 3):
        role_match = 12

    skill_matches = sum(1 for s in cand_skills if s in text)
    skill_pts = min(10, skill_matches * 3)
    score += (role_match + skill_pts)

    # 3. Founder-led post (10 pts)
    author = (signal.get("author_name") or "").lower()
    if any(k in text or k in author for k in ["founder", "co-founder", "ceo", "cto", "founding engineer"]):
        score += 10

    # 4. Low reach (10 pts)
    if likes < 20:
        score += 10
    elif likes < 50:
        score += 7
    elif likes < 100:
        score += 4

    # 5. Stage & region match (10 pts)
    sig_stage = (signal.get("stage") or "any").lower()
    t_stage = (target_stage or "any").lower()
    if t_stage == "any" or sig_stage == "any" or t_stage in sig_stage:
        score += 5

    sig_region = (signal.get("region") or "any").lower()
    t_region = (target_region or "any").lower()
    if t_region == "any" or sig_region == "any" or t_region in sig_region or "remote" in text:
        score += 5

    return min(100, max(0, score))


def poll_modern_signals(target_role: str = "", target_stage: str = "any", target_region: str = "any") -> Dict[str, Any]:
    """Poll all active modern adapters, score signals, and ingest into database."""
    profile = db.get_profile()
    filters = db.get_view_filters()
    role = target_role or filters.get("job_style") or profile.get("target_title") or "Software Engineer"

    total_discovered = 0
    total_new = 0
    fresh_matching = []

    for adapter in ACTIVE_MODERN_ADAPTERS:
        if not adapter.enabled:
            continue
        try:
            items = adapter.fetch(target_role=role, region=target_region)
            for item in items:
                total_discovered += 1
                item["status"] = evaluate_signal_freshness(item.get("type", "hiring_post"), item.get("posted_at"), item.get("likes", 0))
                item["score"] = score_signal(item, profile, target_role=role, target_stage=target_stage, target_region=target_region)

                # Cross-check outreach ledger
                with db.session() as c:
                    contacted = c.execute("SELECT id FROM outreach WHERE lower(company)=lower(?)", (item.get("company", ""),)).fetchone()
                    if contacted:
                        item["already_contacted"] = True

                ingested = db.ingest_signal(item)
                if ingested and ingested.get("is_new") and not ingested.get("duplicate"):
                    total_new += 1
                    if item["status"] == "fresh":
                        fresh_matching.append(item)
        except Exception as e:
            log.warning("Adapter %s failed during signal polling: %s", adapter.name, e)

    return {
        "discovered": total_discovered,
        "new_ingested": total_new,
        "fresh_matching": len(fresh_matching),
        "top_signals": fresh_matching[:5],
    }
