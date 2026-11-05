"""Safety checks on posting text and links. Pure functions, no network.

Three risks, all of which grow when the search reaches small and regional boards:

* scams       fake jobs that ask for money or personal documents. Strong signals block a job. Weak
              signals only warn, and two weak signals together block.
* injection   posting text written for an AI reader ("ignore previous instructions"). The text that the
              client's AI reads is data, never instructions. A title, company or location that carries
              such text blocks the job. A description that carries it is flagged.
* links       URL shorteners and unusual top-level domains hide where an apply link really goes.

Every pattern here has a guard against honest postings. "We never charge any fee" must not trigger the
fee rule, and "equipment provided by us" must not trigger the equipment rule.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Iterable

_NEGATION = re.compile(r"(?:\bno\b|\bnot\b|\bnever\b|\bwithout\b|free of|\bzero\b|n['’]t\b|\bnon[- ]?refundable fee is not\b)[^.\n]{0,50}$", re.I)

_FEE_WORD = r"(?:registration|application|training|processing|admin(?:istration)?|starter[- ]kit|onboarding|security|equipment|background[- ]check|visa|document|verification|activation|membership)"
_STRONG = [
    ("upfront_fee", re.compile(rf"\b{_FEE_WORD}\s+(?:fee|deposit|charge|payment|cost)s?\b", re.I),
     "The posting asks for an upfront fee. Real employers do not charge to hire."),
    ("deposit", re.compile(r"\bdeposit\b[^.\n]{0,40}(?:\d|euro|dollar|usd|eur|\$|€|£)|\b(?:refundable\s+)?deposit\b[^.\n]{0,30}\b(?:required|needed|must|before)\b", re.I),
     "The posting asks for a deposit before you start."),
    ("pay_to_start", re.compile(r"\bpay\b[^.\n]{0,30}\bto\s+(?:apply|start|begin|secure|get the job|receive)\b", re.I),
     "The posting asks you to pay to apply or start."),
    ("cheque", re.compile(r"\b(?:cheque|check)\b[^.\n]{0,60}\b(?:deposit|cash|buy|equipment|wire)\b|\bwire\b[^.\n]{0,40}\b(?:balance|funds|money|remaining)\b", re.I),
     "The posting describes the classic cheque overpayment scam."),
    ("untraceable_payment", re.compile(r"\b(?:western union|moneygram|gift cards?|bitcoin|crypto(?:currency)? (?:payment|transfer)|zelle)\b", re.I),
     "The posting mentions an untraceable payment method."),
    ("data_harvest", re.compile(r"\b(?:send|email|submit|provide|share|upload)\b[^.\n]{0,40}\b(?:passport|id card|national id|ssn|social security|bank (?:details|account)|credit card|card number|iban|selfie)\b", re.I),
     "The posting asks you to send ID or bank details."),
]
_WEAK = [
    ("chat_only", re.compile(r"\b(?:whatsapp|telegram|signal|wechat)\b", re.I), "The posting pushes you to a chat app."),
    ("easy_money", re.compile(r"\bearn\s+(?:up to\s+)?[$€£]?\s?\d[\d,]*\s*(?:usd|eur|dollars?|euros?|\$|€)?\s*(?:per|a|/|every)?\s*(?:day|daily|hour|hourly|hr|week|weekly)\b", re.I),
     "The posting promises high pay per day or hour."),
    ("no_experience", re.compile(r"\bno\s+experience\s+(?:needed|required|necessary)\b", re.I), "The posting needs no experience."),
    ("urgent", re.compile(r"\b(?:hiring\s+immediately|urgent(?:ly)?\s+hiring|start\s+(?:today|immediately|now))\b", re.I), "The posting pushes you to start at once."),
    ("free_mail_contact", re.compile(r"[\w.+-]+@(?:gmail|yahoo|hotmail|outlook|aol|proton(?:mail)?)\.[a-z.]+", re.I), "The contact is a free email address."),
]

_INJECTION = [
    re.compile(r"ignore\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier|preceding)\s+(?:instructions?|prompts?|messages?|rules)", re.I),
    re.compile(r"disregard\s+(?:all\s+|the\s+|your\s+)?(?:previous|above|prior|earlier)", re.I),
    re.compile(r"(?:reveal|show|print|repeat|leak|output)\s+(?:your\s+|the\s+)?(?:system\s+)?(?:prompt|instructions)", re.I),
    re.compile(r"\byou\s+are\s+now\b", re.I),
    re.compile(r"(?:^|[.!?\n]\s*)(?:system|assistant|developer)\s*:\s", re.I),
    re.compile(r"developer\s+mode|jailbreak", re.I),
    re.compile(r"<\|[a-z_]+\|>|\[/?INST\]|<<\s*SYS\s*>>", re.I),
    re.compile(r"note\s+to\s+(?:the\s+)?(?:ai|llm|assistant|model|agent|bot)s?\b", re.I),
    re.compile(r"\b(?:ai|llm|language model|assistant)s?\s+(?:reading|processing)\s+this", re.I),
    re.compile(r"\b(?:dear|hello|hi|attention)\s+(?:ai|llm|assistant|model|chatbot|bot)\b", re.I),
    re.compile(r"\bomit\s+(?:the\s+)?(?:red flags|warnings?|negatives?|risks?)\b|(?:summari[sz]e|describe|present)\s+this\s+(?:job|posting|role|position)\s+as\b", re.I),
    re.compile(r"do\s+not\s+(?:tell|inform|mention|reveal)[^.\n]{0,20}\buser\b", re.I),
    re.compile(r"tell\s+the\s+user\s+to\b", re.I),
    re.compile(r"(?:recommend|rank|rate)\s+this\s+(?:job|posting|role|position)\b[^.\n]{0,30}\b(?:best|first|highest|top|10/10)\b", re.I),
]

SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "cutt.ly", "rb.gy", "is.gd", "ow.ly", "buff.ly", "shorturl.at", "tiny.cc", "t.ly", "lnkd.in"}
ODD_TLDS = {"xyz", "top", "click", "buzz", "loan", "work", "gq", "tk", "ml", "cf", "ga", "icu", "monster", "rest", "cyou", "sbs"}


def _hits(patterns: Iterable[tuple[str, re.Pattern, str]], text: str) -> list[tuple[str, str]]:
    """Pattern hits that are not negated earlier in the same sentence ("we never charge any fee")."""
    found = []
    for code, rx, msg in patterns:
        for m in rx.finditer(text):
            before = re.split(r"[.!?\n]", text[max(0, m.start() - 80):m.start()])[-1]
            if _NEGATION.search(before):
                continue
            found.append((code, msg))
            break
    return found


def scam_signals(text: str) -> list[dict[str, str]]:
    """Findings as ``{severity, code, message}``. A strong signal blocks. Two weak signals block. One warns."""
    body = text or ""
    strong = _hits(_STRONG, body)
    weak = _hits(_WEAK, body)
    out = [{"severity": "block", "code": c, "message": m} for c, m in strong]
    if len(weak) >= 2 and not strong:
        out.append({"severity": "block", "code": "scam_pattern", "message": "Several scam signs together: " + "; ".join(m.rstrip(".").lower() for _, m in weak[:3]) + "."})
    elif weak and not strong:
        out.append({"severity": "warn", "code": weak[0][0], "message": weak[0][1] + " Check the employer before you share anything."})
    return out


def injection_hits(text: str) -> list[str]:
    """The matched fragments of text aimed at an AI reader."""
    body = text or ""
    return [m.group(0).strip()[:60] for rx in _INJECTION for m in [rx.search(body)] if m]


def link_signals(url: str) -> list[dict[str, str]]:
    host = (urllib.parse.urlparse(url or "").hostname or "").lower()
    if not host:
        return []
    out = []
    if host.removeprefix("www.") in SHORTENERS:
        out.append({"severity": "warn", "code": "link_shortener",
                    "message": "The apply link is a URL shortener, so you cannot see where it goes. Open the employer's own site instead."})
    tld = host.rsplit(".", 1)[-1]
    if tld in ODD_TLDS:
        out.append({"severity": "warn", "code": "odd_domain", "message": f"The apply link uses an unusual domain ending (.{tld}). Check that it is the employer's real site."})
    if "xn--" in host:
        out.append({"severity": "warn", "code": "lookalike_domain", "message": "The apply link uses a look-alike (punycode) domain."})
    return out


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def inline(text: object, limit: int = 120) -> str:
    """Make posting text safe to place in a report: one line, no control or hidden characters, bounded length."""
    s = _CONTROL.sub("", str(text or "")).replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "…"
