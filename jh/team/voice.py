"""The team's house style, as data and a scanner.

Readers spot machine-sounding text fast. Surveys of hiring managers say the same thing in different
words: they do not object to AI, they object to text that is generic and cannot be checked. This module
lists the patterns that make text read that way, each with a plain alternative, and finds them in a text.

Two uses:

* Drafts. ``scan(text)`` finds the patterns in a letter, message or answer. The Reviewer reports them as
  warnings (never blocks: a genuine sentence can contain a flagged word).
* Prompts. ``lint_prompt(text)`` checks the prompt files themselves. A model copies the style of its
  prompt, so a prompt that uses em dashes, shouts in capitals, or boasts about the persona invites the
  same habits in the output.

Word lists alone do not work. After "delve" became a known giveaway its use fell, while other style words
kept rising, so a ban moves the habit to a synonym. That is why the rules here are grouped by pattern, why
each carries a plain alternative, and why the prompts also ask for the positive habit: a fact only this
candidate has, in plain words.

Run on a file: ``python -m jh.team.voice prompts/cover_letter.md``
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Iterable

EM, EN = "\u2014", "\u2013"


@dataclass(frozen=True)
class Hit:
    category: str
    text: str
    start: int
    plain: str


def _rx(*alts: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])(?:" + "|".join(alts) + r")(?![\w])", re.I)


# (category, pattern, what to do instead)
RULES: list[tuple[str, re.Pattern, str]] = [
    ("opener", _rx(r"i hope this (?:message |email |note )?finds you well", r"i am writing to (?:express|apply|inquire|submit|introduce)", r"i am (?:thrilled|excited|delighted|eager|pleased|honou?red) to",
                   r"i(?:'m| am) (?:so |really |very )?(?:thrilled|excited|delighted) (?:to|about|by)", r"i came across your (?:profile|company|post|website)", r"i was (?:impressed|excited|inspired) by",
                   r"i would like to take this opportunity", r"allow me to introduce myself", r"i am reaching out (?:to|regarding|because)", r"my name is [A-Z]\w+ and i am"),
     "Open with the role and one fact only this candidate has."),
    ("hype", _rx(r"world[- ]class", r"best[- ]in[- ]class", r"cutting[- ]edge", r"state[- ]of[- ]the[- ]art", r"game[- ]chang\w+", r"high[- ]converting", r"rock ?stars?", r"ninja", r"guru",
                 r"industry[- ]leading", r"next[- ]level", r"revolutionary", r"transformative", r"10x"),
     "Name what the thing does, with a number from the candidate's data."),
    ("stock_adjective", _rx(r"passionate", r"dynamic(?! (?:programming|range|pricing|array|typing|memory|allocation|dns|content|routing|sql|analysis|systems?|rendering|loading))", r"results[- ]driven", r"detail[- ]oriented", r"self[- ]starter", r"team player", r"go[- ]getter", r"highly motivated", r"motivated professional",
                            r"innovative", r"robust(?! (?:standard errors?|regression|estimat\w+|statistic\w*|inference|optimi[sz]\w+|control|check|scaler))", r"seamless(?:ly)?", r"holistic", r"proven track record", r"track record of success", r"extensive experience", r"strong background",
                            r"highly skilled", r"think outside the box", r"hit the ground running", r"fast[- ]paced", r"entrepreneurial spirit", r"thrive in",
                            r"a wealth of (?:experience|knowledge|expertise)", r"seasoned (?:professional|engineer|leader|expert)", r"well[- ]positioned", r"add(?:ing)? (?:real |significant |immediate )?value",
                            r"track record (?:of|in)", r"committed to excellence", r"dedicated(?! (?:server|team|line|hardware|account|channel))", r"enthusiastic", r"driven professional"),
     "Show it with what the candidate did. Cut the adjective."),
    ("power_verb", _rx(r"leverag(?:e|es|ed|ing)(?! ratios?| buyout| effect| point| calculations?| cap| limit| multiple| position)", r"spearhead\w*", r"utili[sz]\w+", r"facilitat\w+", r"orchestrat\w+", r"synerg\w+", r"harness\w*", r"foster\w*",
                       r"elevat\w+", r"empower\w*", r"delv\w+", r"underscor\w+", r"showcas\w+", r"embark\w*", r"unlock\w*", r"navigat(?:e|es|ed|ing) (?:the )?(?:complex|challenges|landscape)"),
     "Use a plain verb: built, ran, cut, wrote, fixed, taught, moved, sold."),
    ("grand_framing", _rx(r"in today['’]s (?:\w+[- ]){0,3}(?:world|landscape|market|environment|era)", r"ever[- ](?:evolving|changing)", r"rapidly (?:evolving|changing)", r"testament to", r"pivotal",
                          r"tapestry", r"realm of", r"landscape of", r"in the (?:world|realm) of", r"cornerstone", r"plays? a (?:crucial|vital|key|pivotal) role", r"at the (?:forefront|heart) of",
                          r"digital age", r"in an? (?:increasingly|ever)"),
     "Say the plain point, or cut the sentence."),
    ("closer", _rx(r"i look forward to the opportunity", r"i would welcome the opportunity", r"thank you for your time and consideration", r"please (?:feel free|do not hesitate|don['’]t hesitate) to",
                   r"feel free to (?:reach out|contact)", r"i look forward to hearing from you", r"circle back", r"touch base", r"just (?:wanted|checking) (?:to|in)", r"checking in on", r"at your earliest convenience"),
     "End on one concrete next step in your own words."),
    ("frame", re.compile(r"(?:\bnot (?:just|only|merely) [^.]{3,60}?,? but (?:also )?|\bit['’]?s not (?:about )?[^.]{3,60}?,? it['’]?s |\bisn['’]t (?:just|only) [^.]{3,60}?,? it['’]?s |\bmore than just\b|"
                    r"\bwhether you['’]re\b|\bhere['’]?s the thing\b|\blet['’]?s be honest\b|\bin conclusion\b|\bto summari[sz]e\b|\bat the end of the day\b|\bin a world where\b|\blook no further\b|"
                    r"(?:^|\n\n)\s*(?:are you|do you|have you|ever wondered|what if|imagine)\b[^.?\n]{3,80}\?)", re.I),
     "State the point once, directly."),
    ("hedge_claim", _rx(r"i believe (?:i|that i) (?:would|could|can|am)", r"i feel (?:that )?i (?:would|am|could)", r"i am confident that i (?:can|would|will|am)", r"(?:great|perfect|ideal|excellent|strong) (?:fit|match|candidate)",
                        r"the (?:ideal|perfect|right) candidate", r"uniquely (?:qualified|positioned)"),
     "Show the evidence and let the reader decide the fit."),
    ("vague_quantity", _rx(r"numerous", r"countless", r"myriad", r"a (?:wide|broad|diverse) (?:range|variety|array) of", r"significant(?:ly)? (?:improv|increas|reduc|enhanc)\w*", r"substantial(?:ly)?",
                           r"various (?:stakeholders|teams|projects)", r"multiple (?:stakeholders)"),
     "Use the candidate's own number, or say what changed."),
]

# Punctuation and format are checked apart from words, because they depend on the kind of text.
_SPACED_HYPHEN = re.compile(r"(?<=\w) - (?=\w)")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2705\u274C]")
_MD_BOLD = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
_MD_HEAD = re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S")
_BULLET = re.compile(r"(?m)^\s*[•▪●]\s+")

PLAIN_KINDS = {"plain", "form", "email", "message"}      # text pasted into a form field, an email or a chat box
RESUME_KIND = "resume"

_CATEGORY_HELP = {
    "dash": "Use a comma, period, semicolon or parentheses. Write number ranges as 'to'.",
    "format": "Plain text only: no bold, headings, bullet symbols, emoji or exclamation marks.",
}


def scan(text: str, kind: str = "prose") -> list[Hit]:
    """Find machine-sounding patterns. ``kind``: prose (letters, answers), plain (form or email text), resume."""
    body = text or ""
    hits: list[Hit] = []
    for cat, rx, plain in RULES:
        for m in rx.finditer(body):
            hits.append(Hit(cat, m.group(0).strip(), m.start(), plain))
    for ch in (EM, EN):
        for m in re.finditer(ch, body):
            hits.append(Hit("dash", ch, m.start(), _CATEGORY_HELP["dash"]))
    if kind != RESUME_KIND:
        for m in _SPACED_HYPHEN.finditer(body):
            hits.append(Hit("dash", " - ", m.start(), _CATEGORY_HELP["dash"]))
    if kind in PLAIN_KINDS:
        for rx, label in ((_EMOJI, "emoji"), (_MD_BOLD, "markdown bold"), (_MD_HEAD, "markdown heading"), (_BULLET, "bullet symbol")):
            for m in rx.finditer(body):
                hits.append(Hit("format", label, m.start(), _CATEGORY_HELP["format"]))
    for m in re.finditer(r"!", body):
        hits.append(Hit("format", "!", m.start(), _CATEGORY_HELP["format"]))
    return sorted(hits, key=lambda h: h.start)


def density(hits: Iterable[Hit], text: str) -> float:
    """Hits per 100 words. Under about 1 reads as a person. Over about 3 reads as a template."""
    words = max(1, len((text or "").split()))
    return round(100 * len(list(hits)) / words, 2)


def summarize(hits: Iterable[Hit], limit: int = 5) -> str:
    """One line for a report: the first few distinct patterns and what to do instead."""
    seen: dict[str, Hit] = {}
    for h in hits:
        seen.setdefault(h.text.lower(), h)
    parts = [f"'{h.text}' ({h.category})" for h in list(seen.values())[:limit]]
    return ", ".join(parts)


# ------------------------------------------------------------------ prompt linting

_EXEMPT = re.compile(r"<(robotic|voice|avoid)>.*?</\1>", re.S | re.I)
_SHOUT = re.compile(r"\b(?:STRICTLY|MUST|NEVER|ALWAYS|CRITICAL|ABSOLUTELY|ZERO|BAN|BANNED|MANDATORY|REQUIRED|FORBIDDEN|EXACTLY|ONLY)\b")
_PERSONA = re.compile(r"\b(?:elite|world[- ]class|top tech companies|top-tier|executive (?:talent|hiring|career|resume|recruiter)|principal|staff (?:software|architect)|thousands of|hundreds of|over [\d,]+ )\b", re.I)
_HYPE_TITLE = re.compile(r"2026/2027|2026-2027|\bstandard\b\)|high-impact|high-converting|high-leverage|high-signal|engineered for maximum|maximum response", re.I)
_STAT = re.compile(r"\b\d{2,3}%\+?|\bwithin \d+ seconds|\b\d+-second\b|\b6 seconds?\b", re.I)
_SOFTWARE_LOCK = re.compile(r"\b(?:p99|latency|throughput|microservices?|distributed systems?|event-driven|kubernetes|0-to-1|SLA|uptime|architect(?:ed|ure|ural))\b", re.I)


def strip_exempt(text: str) -> str:
    """Drop the parts of a prompt that quote the patterns on purpose, for teaching what to avoid."""
    return _EXEMPT.sub(" ", text or "")


def lint_prompt(text: str) -> dict[str, list[str]]:
    """Problems in a prompt file, by kind. Content inside <robotic>, <voice> and <avoid> tags is exempt."""
    body = re.sub(r"<!--.*?-->", " ", strip_exempt(text), flags=re.S)       # HTML comments are for editors
    prose = body
    out: dict[str, list[str]] = {}
    style = scan(prose, kind="prose")
    for h in style:
        out.setdefault(h.category, []).append(h.text)
    # Caps and persona claims are checked on text outside JSON schema blocks.
    schema_free = re.sub(r"<output>.*?</output>", " ", prose, flags=re.S | re.I)
    for name, rx in (("shouting", _SHOUT), ("persona_inflation", _PERSONA), ("hype_label", _HYPE_TITLE), ("invented_stat", _STAT)):
        found = [m.group(0) for m in rx.finditer(schema_free)]
        if found:
            out[name] = found
    lock = [m.group(0) for m in _SOFTWARE_LOCK.finditer(schema_free)]
    if lock:
        out["software_lock_in"] = lock
    return out


def _main(argv: list[str]) -> int:
    code = 0
    for path in argv:
        with open(path, encoding="utf-8") as f:
            res = lint_prompt(f.read())
        total = sum(len(v) for v in res.values())
        print(f"{path}: {total} issue(s)")
        for k, v in sorted(res.items()):
            print(f"  {k}: {len(v)}  e.g. {sorted(set(map(str, v)))[:5]}")
        code = code or int(bool(total))
    return code


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
