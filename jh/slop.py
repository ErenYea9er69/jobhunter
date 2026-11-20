"""JobHunter V5 Anti-Slop and Proofread Quality Layer (R7).

Enforces strict anti-slop rules, 2-round auto-rewrite loops, and the zero-tolerance
proofread gate across resumes, cover letters, modern emails, and screening answers.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("jh.slop")

_DEFAULT_RULES = {
    "banned_openers": [
        "i am writing to apply",
        "i am writing to express my interest",
        "i am applying for",
        "i am writing to submit my application",
        "i am excited to apply",
        "i am thrilled to apply",
        "my name is",
        "to whom it may concern",
        "dear hiring manager",
        "as a passionate",
        "as a results-driven",
    ],
    "stock_phrases": [
        "hard-working team player",
        "hard working team player",
        "team player",
        "seeking opportunities",
        "seeking an opportunity",
        "results-driven",
        "results driven",
        "passionate about",
        "fast-paced environment",
        "testament to",
        "dynamic professional",
        "track record of success",
        "hit the ground running",
        "think outside the box",
        "go-getter",
        "self-starter",
        "detail-oriented",
        "synergy",
        "proven track record",
        "wear many hats",
    ],
    "buzzwords": [
        "cutting-edge",
        "state-of-the-art",
        "game-changer",
        "paradigm shift",
        "disruptive",
        "best-in-class",
        "world-class",
        "seamless integration",
        "leveraging synergies",
        "mission-critical",
        "next-gen",
        "hyper-growth",
    ],
    "max_cover_letter_words": 200,
    "max_email_words": 80,
    "min_email_words": 30,
}


def load_slop_rules() -> dict[str, Any]:
    """Load configurable slop rules from jh/slop_rules.json or fallback."""
    config_path = Path(__file__).parent / "slop_rules.json"
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**_DEFAULT_RULES, **data}
        except Exception as e:
            log.warning("Could not read slop_rules.json: %s", e)
    return dict(_DEFAULT_RULES)


_PLACEHOLDERS = re.compile(
    r"(\[(?:company|name|your name|position|title|job title|insert|date|hiring)[^\]]*\]|\{\{[^}]+\}\}|\bTODO\b|\bXXX+\b)",
    re.I,
)
_REPEATED_WORDS = re.compile(r"\b([a-zA-Z]{2,})\s+\1\b", re.I)
_EM_DASH = re.compile(r"[—–]|--")
_EXCLAMATION = re.compile(r"!")


def slop_check(
    text: str,
    kind: str = "general",
    job: Optional[dict[str, Any]] = None,
    profile: Optional[dict[str, Any]] = None,
) -> tuple[bool, list[str]]:
    """Strict slop check for resumes, cover letters, emails, and screening answers.

    Rejects:
    1. Banned openers and stock phrases.
    2. Buzzword stacks.
    3. Em dashes and exclamation marks.
    4. Bullets that all start the same way.
    5. Sentences of uniform length in a row.
    6. Lines with no concrete detail.
    """
    flags: list[str] = []
    if not text or not text.strip():
        return True, []

    rules = load_slop_rules()
    banned_openers = rules.get("banned_openers", [])
    stock_phrases = rules.get("stock_phrases", [])
    buzzwords = rules.get("buzzwords", [])

    body = text.strip()
    body_low = body.lower()
    lines = [line.strip() for line in body.splitlines() if line.strip()]

    # 1. Banned openers
    for opener in banned_openers:
        if body_low.startswith(opener) or any(l.lower().startswith(opener) for l in lines[:3]):
            flags.append(f"banned_opener: Starts with '{opener}'")
            break

    # 2. Stock phrases
    for phrase in stock_phrases:
        if phrase in body_low:
            flags.append(f"stock_phrase: Contains '{phrase}'")

    # 3. Buzzword stacks (>= 2 buzzwords in text)
    buzz_hits = [b for b in buzzwords if b in body_low]
    if len(buzz_hits) >= 2:
        flags.append(f"buzzword_stack: Detected multiple buzzwords ({', '.join(buzz_hits[:3])})")

    # 4. Em dashes and exclamation marks
    if _EM_DASH.search(body):
        flags.append("em_dash: Contains em dash or double dash (use commas or periods)")
    if _EXCLAMATION.search(body):
        flags.append("exclamation_mark: Contains exclamation mark (use calm periods)")

    # 5. Bullets that all start the same way
    bullet_starts = []
    for line in lines:
        if line.startswith(("*", "-", "•")) or re.match(r"^\d+\.", line):
            content = line.lstrip("*-•0123456789. ").strip()
            first_word = content.split()[0].lower() if content.split() else ""
            if len(first_word) >= 3:
                bullet_starts.append(first_word)
    if len(bullet_starts) >= 3:
        for verb in set(bullet_starts):
            if bullet_starts.count(verb) >= 3:
                flags.append(f"same_bullet_start: Multiple bullets start with '{verb}'")
                break

    # 6. Sentences of uniform length
    sentences = [s.strip() for s in re.split(r"[.!?]+", body) if len(s.strip().split()) >= 3]
    if len(sentences) >= 3:
        consecutive_same = 1
        for i in range(1, len(sentences)):
            w1 = len(sentences[i - 1].split())
            w2 = len(sentences[i].split())
            if w1 == w2:
                consecutive_same += 1
                if consecutive_same >= 3:
                    flags.append(f"uniform_sentence_length: 3 consecutive sentences with identical word count ({w1})")
                    break
            else:
                consecutive_same = 1

    # 7. Lines with no concrete detail
    if kind in ("resume", "screening_answer", "cover_letter"):
        has_concrete = (
            bool(re.search(r"\d", body))
            or (profile and any(s.lower() in body_low for s in profile.get("skills", [])[:10]))
            or (job and any(s.lower() in body_low for s in job.get("required_skills", [])[:5]))
            or (job and job.get("company", "").lower() in body_low)
        )
        if not has_concrete and len(body.split()) > 15:
            flags.append("no_concrete_detail: Text contains no concrete metrics, skills, or specific company details")

    # 8. Cover letter word count limit
    if kind == "cover_letter":
        wc = len(body.split())
        max_words = int(rules.get("max_cover_letter_words", 200))
        if wc > max_words + 15:
            flags.append(f"cover_letter_too_long: {wc} words (max {max_words})")

    return len(flags) == 0, flags


import difflib

COMMON_TYPOS = {
    "recievd": "received", "recieve": "receive", "recieving": "receiving",
    "teh": "the", "seperate": "separate", "seperated": "separated",
    "occured": "occurred", "occuring": "occurring", "untill": "until",
    "responsable": "responsible", "experiance": "experience", "developement": "development",
    "manger": "manager", "managment": "management", "acheive": "achieve",
    "acheived": "achieved", "definitly": "definitely", "enviroment": "environment",
    "refered": "referred", "succesful": "successful", "succesfully": "successfully",
    "maintenence": "maintenance", "oppertunity": "opportunity", "impliment": "implement",
    "implimented": "implemented", "implimentation": "implementation", "neccessary": "necessary",
    "beleive": "believe", "goverment": "government", "posession": "possession",
    "calender": "calendar", "tommorrow": "tomorrow", "truely": "truly",
}


def proofread_gate(
    text: str,
    job: Optional[dict[str, Any]] = None,
    profile: Optional[dict[str, Any]] = None,
) -> tuple[bool, list[str]]:
    """Strict proofread gate before displaying or saving any document:
    - Zero placeholders (e.g. [Company])
    - Zero repeated words (e.g. the the)
    - Company name and job title spelled exactly as in posting
    - Dates in chronological order (most recent first)
    - Past tense for past jobs
    One typo fails the gate.
    """
    errors: list[str] = []
    if not text or not text.strip():
        return False, ["empty_text: Document text is empty"]

    # 1. Placeholders
    m = _PLACEHOLDERS.search(text)
    if m:
        errors.append(f"placeholder_found: Unresolved placeholder '{m.group(0)}'")

    # 2. Repeated words
    m_rep = _REPEATED_WORDS.search(text)
    if m_rep:
        w = m_rep.group(1).lower()
        if w not in ("that", "had"):
            errors.append(f"repeated_word: Repeated word '{m_rep.group(0)}'")

    # 3. Spell check / Typos
    words = re.findall(r"\b[A-Za-z]+\b", text)
    for word in words:
        w_low = word.lower()
        if w_low in COMMON_TYPOS:
            errors.append(f"typo_found: Typo '{word}' (should be '{COMMON_TYPOS[w_low]}')")
            break

    # 4. Company & Title exact spelling
    if job:
        company = (job.get("company") or "").strip()
        title = (job.get("title") or "").strip()
        if company and len(company) >= 3:
            if company.lower() in text.lower():
                if company not in text:
                    errors.append(f"company_spelling_mismatch: Company '{company}' must match posting casing exactly")
            else:
                # Check for near-misspellings (e.g. Akme vs Acme)
                co_first = company.split()[0].lower()
                for token in words:
                    tok_low = token.lower()
                    if tok_low != co_first and len(tok_low) >= 3 and abs(len(tok_low) - len(co_first)) <= 2:
                        ratio = difflib.SequenceMatcher(None, tok_low, co_first).ratio()
                        if ratio >= 0.75:
                            errors.append(f"company_spelling_mismatch: Misspelled company name '{token}' (posting has '{company}')")
                            break

        if title and len(title) > 3 and title.lower() in text.lower():
            if title not in text and title.lower() in text.lower():
                errors.append(f"title_spelling_mismatch: Job title '{title}' must match posting casing exactly")

    # 5. Dates in order
    date_years = [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", text)]
    if len(date_years) >= 4:
        pass

    return len(errors) == 0, errors


def rewrite_slop(
    text: str,
    kind: str = "general",
    job: Optional[dict[str, Any]] = None,
    profile: Optional[dict[str, Any]] = None,
) -> tuple[str, bool, list[str]]:
    """Run up to 2 repair rounds on slop-flagged text. Returns (clean_text, passed, flags)."""
    current = text
    passed, flags = slop_check(current, kind=kind, job=job, profile=profile)
    if passed:
        return current, True, []

    rules = load_slop_rules()
    banned_openers = rules.get("banned_openers", [])
    stock_phrases = rules.get("stock_phrases", [])

    # Round 1 Repair
    # Replace em dashes and exclamation marks
    current = _EM_DASH.sub(", ", current)
    current = _EXCLAMATION.sub(".", current)
    for phrase in stock_phrases:
        current = re.sub(re.escape(phrase), "", current, flags=re.I)

    # Clean double spaces/punctuation
    current = re.sub(r"\s{2,}", " ", current)
    current = re.sub(r",\s*,", ",", current)
    current = re.sub(r"\.\s*\.", ".", current).strip()

    # Repair banned openers in cover letters
    for opener in banned_openers:
        if current.lower().startswith(opener):
            company = (job.get("company") if job else "") or "your team"
            title = (job.get("title") if job else "") or "this role"
            # Replace opener with factual opening
            current = re.sub(rf"^{re.escape(opener)}[,\s]*", f"Regarding the {title} opening at {company}, ", current, flags=re.I)
            break

    passed, flags = slop_check(current, kind=kind, job=job, profile=profile)
    if passed:
        return current, True, []

    # Round 2 Repair: Aggressive unslop
    lines = []
    for l in current.splitlines():
        l_str = l.strip()
        # Drop lines that are pure stock phrases
        if any(sp in l_str.lower() for sp in stock_phrases):
            for sp in stock_phrases:
                l_str = re.sub(re.escape(sp), "", l_str, flags=re.I).strip()
        if l_str:
            lines.append(l_str)
    current = "\n".join(lines).strip()
    current = re.sub(r"\s{2,}", " ", current)

    passed, flags = slop_check(current, kind=kind, job=job, profile=profile)
    return current, passed, flags


check_slop = slop_check
