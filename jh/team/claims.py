"""Sentence-level fact checking against the resume.

The older grounding check judges whole lines and missed many invented facts: an employer, a degree, a
certification, a job title, a skill stated as experience. This module reads each sentence the candidate
would sign, pulls out the checkable facts, and compares each with a fact base built from the resume.

What is checked, per sentence the candidate states about themselves:

    employer        "At Google I led ..."            the employer must be on the resume
    title           "As Engineering Manager ..."      every word of the title must be on the resume
    leadership      "I led / managed / mentored"     the resume must show leading or managing
    degree          "PhD ... from Stanford"           the degree level and the school must be on the resume
    skill           "I have expertise in Kubernetes" the skill must be on the resume, unless the sentence
                                                      says the candidate lacks it or wants to learn it
    quantity        "40 engineers", "a decade"        the number must be on the resume. Total years of
                                                      experience must be close to the resume's years.
    credential      certifications, awards, talks, publications, clearance, exits (acquired by ...)
    status          languages, citizenship, work authorization (cannot be proven; flagged for the client)
    employer fact   "I admire Adyen's 2024 acquisition"  facts about the employer must appear in the posting

Anything the check cannot prove is reported as a warning. Only a claim the resume contradicts or does not
contain at all is a block. A resume is held to a stricter rule: every skill it lists must be on the profile.

The checks are rules, not a model. They are written to catch what a language model tends to invent, and
``jh/team/evals.py`` measures how well they do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .. import skills as sk

BLOCK, WARN = "block", "warn"


@dataclass
class Claim:
    sentence: str
    severity: str
    code: str
    message: str


# ------------------------------------------------------------------ the fact base

_SKIP_KEYS = {"email", "phone", "linkedin", "github", "min_salary", "work_mode", "preferred_locations", "excluded_keywords",
              "preferred_job_types", "dream_companies", "dream_role", "target_roles", "skills_by_category", "_profile_name"}


def _strings(obj: Any, key: str = "") -> list[str]:
    if key in _SKIP_KEYS:
        return []
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return [str(obj)]
    if isinstance(obj, dict):
        return [s for k, v in obj.items() for s in _strings(v, k)]
    if isinstance(obj, (list, tuple, set)):
        return [s for v in obj for s in _strings(v, key)]
    return []


_MAG = {"k": 1e3, "m": 1e6, "b": 1e9}
_WORDS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
          "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
          "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
          "dozen": 12, "decade": 10, "thousand": 1000}
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(%|k\b|m\b|b\b|million|billion|thousand)?", re.I)
_WORD_NUM = re.compile(r"\b(" + "|".join(_WORDS) + r")\b", re.I)
_YEAR = re.compile(r"^(?:19[89]\d|20[0-3]\d)$")


def quantities(text: str) -> list[tuple[float, str]]:
    """Numbers in a text as ``(value, surface)``. "2 million" and "2M" are both 2000000. Words count from three up."""
    out: list[tuple[float, str]] = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(1).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        if unit in ("million",):
            v *= 1e6
        elif unit == "billion":
            v *= 1e9
        elif unit == "thousand":
            v *= 1e3
        elif unit in _MAG:
            v *= _MAG[unit]
        out.append((v, m.group(0).strip()))
    for m in _WORD_NUM.finditer(text or ""):
        out.append((float(_WORDS[m.group(1).lower()]), m.group(0)))
    return out


class FactBase:
    """What the resume says, in forms that are quick to compare."""

    def __init__(self, profile: dict, job: Optional[dict] = None):
        profile, job = profile or {}, job or {}
        self.profile = profile
        parts = _strings({k: v for k, v in profile.items()})
        self.corpus = " \n ".join(parts).lower()
        self.employers = {(e.get("company") or "").split(",")[0].strip().lower() for e in profile.get("experience") or [] if e.get("company")}
        self.roles = " ".join(str(e.get("role", "")) for e in profile.get("experience") or []).lower() + " " + str(profile.get("target_title", "")).lower()
        self.institutions = {str(d.get("institution", "")).strip().lower() for d in profile.get("education") or [] if d.get("institution")}
        degree_text = " ".join(str(d.get("degree", "")) for d in profile.get("education") or []).lower()
        self.levels = _levels(degree_text)
        self.skills = {str(s).lower() for s in profile.get("skills") or []} | {s.lower() for s in sk.extract(self.corpus)}
        no_months = re.sub(r"\b((?:19|20)\d{2})-\d{1,2}\b", r"\1", self.corpus)      # "2021-12" is the year 2021, not the number 12
        self.numbers = [v for v, _ in quantities(no_months)]
        for e in profile.get("experience") or []:       # dates are numbers too: "2022-01" holds 2022 and 1
            for key in ("start_date", "end_date"):
                self.numbers += [float(x) for x in re.findall(r"(?:19|20)\d{2}", str(e.get(key, "")))]   # years only, not months
        self.years = float(profile.get("years_of_experience") or 0)
        self.company = (job.get("company") or "").strip()
        self.job_text = " ".join(str(job.get(k, "")) for k in ("title", "company", "description", "location")).lower()
        self.job_company_low = self.company.lower()

    def has_number(self, v: float) -> bool:
        return any(abs(v - n) < 1e-6 or (n and abs(v - n) / n < 0.005) for n in self.numbers)

    def knows_entity(self, name: str) -> bool:
        low = name.lower().strip()
        if not low:
            return True
        if any(low == e or low in e or e in low for e in self.employers | self.institutions if e):
            return True
        return low in self.corpus


def _levels(text: str) -> set[str]:
    out = set()
    t = text.lower()
    if re.search(r"bachelor|b\.?sc|licen[cs]e|baccalaur|undergraduate|engineer(?:ing)? degree|diplôme d'ingénieur|ingénieur", t):
        out.add("bachelor")
    if re.search(r"master|m\.?sc|\bmba\b|\bmsc\b", t):
        out.add("master")
    if re.search(r"ph\.?d|doctor", t):
        out.add("phd")
    return out


# ------------------------------------------------------------------ sentence helpers

_FIRST = re.compile(r"\b(?:i|i'm|i've|i'd|i’m|i’ve|my|me|myself|mine)\b", re.I)
_BULLET = re.compile(r"^\s*(?:[*•\-–]|\d+[.)])\s+")
_APPLYING = re.compile(r"\b(?:appl(?:y|ying|ication)|interested in|writing to|position of|the .{0,40} role|opening|vacancy|opportunity|your posting|you ask|job description)\b", re.I)
_LEARNING = re.compile(r"\b(?:learn\w*|pick(?:ing)? up|eager|keen|ready to|interested in|excited (?:to|by|about)|looking forward|haven['’]t|have not|has not|do not have|don['’]t have|did not|never (?:used|worked|had)|no experience|not yet|without|lack|new to|curious|grow\w*|would like to|hope to|want to)\b", re.I)
_ASSERT = re.compile(r"\b(?:use|used|using|know|knew|have|has|had|built|build|building|run|ran|running|manage|managed|administer\w*|deploy\w*|design\w*|develop\w*|implement\w*|wrote|write|writing|work|worked|working|lead|led|leading|own|owned|maintain\w*|architect\w*|optimi[sz]\w*|migrat\w*|automat\w*|experience\w*|expertise|proficien\w+|skilled|expert|fluent|certified|hold|master\w*|specializ\w*|ship\w*|shipped|created?|launched|scal\w+|operate\w*|handle[sd]?|am an?|is an?)\b", re.I)
_PAST_CLAIM = re.compile(r"\b(?:i|we)\s+(?:\w+\s+){0,2}?(?:\w+ed|led|built|ran|wrote|made|cut|grew|managed|drove|won|took|got|owned)\b", re.I)
_ENTITY = re.compile(r"\b(?i:at|with|for|joined|left|from|by)\s+((?:[A-Z][\w&.'’-]+)(?:\s+(?:[A-Z][\w&.'’-]+|of|and|&)){0,3})")
_NOT_ENTITY = {"the", "my", "our", "your", "this", "that", "these", "those", "a", "an", "one", "each", "every", "all", "home", "work", "scale",
               "night", "least", "first", "last", "present", "times", "once", "most", "some", "any", "no", "i", "we", "it", "its", "their",
               "his", "her", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march",
               "april", "may", "june", "july", "august", "september", "october", "november", "december", "english", "french", "arabic"}


def sentences(text: str) -> list[str]:
    """Split into sentences. Bullets and lines are kept apart."""
    out = []
    for line in (text or "").split("\n"):
        s = line.strip()
        if not s:
            continue
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", s):
            if part.strip():
                out.append(part.strip())
    return out


def _clauses(sentence: str) -> list[str]:
    return [c for c in re.split(r",|;|\bbut\b|\bhowever\b|\bthough\b|\bwhile\b|\balthough\b| - | — ", sentence) if c.strip()]


def _clean_entity(raw: str) -> str:
    toks = raw.split()
    while toks and toks[-1].lower() in ("of", "and", "&"):
        toks.pop()
    cut = []
    for t in toks:
        if t == "I" or t.lower() in ("i'm", "i've"):
            break
        cut.append(t)
    return " ".join(cut).strip(" .,'’")


# ------------------------------------------------------------------ credentials

_CREDENTIALS = [
    ("certification", re.compile(r"\b(?:certified|certification|certificate|pmp|cissp|ccna|ccnp|cka|ckad|scrum master|\bcsm\b|itil|six sigma)\b", re.I),
     "A certification is claimed that is not on the resume.", BLOCK),
    ("award", re.compile(r"\b(?:award(?:ed)?|prize|\bwon\b|winner|hackathon|scholarship|finalist|ranked (?:top|#?\d)|employee of the (?:year|month|quarter)|best employee|top performer|recogni[sz]ed as|honou?red as|named .{0,25}(?:best|top))\b", re.I),
     "An award or prize is claimed that is not on the resume.", BLOCK),
    ("publication", re.compile(r"\b(?:published|publication|papers?|patents?|spoke at|speaker|keynote|talk at|presented at|conference|pycon|jsconf|meetup talk|ted talk)\b", re.I),
     "A publication or talk is claimed that is not on the resume.", BLOCK),
    ("clearance", re.compile(r"\b(?:security clearance|top secret|secret clearance|clearance)\b", re.I),
     "A security clearance is claimed that is not on the resume.", BLOCK),
    ("exit", re.compile(r"\b(?:acquired|acquisition|ipo|founded|co-?founded|founder|raised \$|series [a-e]\b)", re.I),
     "A founding, funding or acquisition is claimed that is not on the resume.", BLOCK),
    ("status", re.compile(r"\b(?:citizen|citizenship|work authori[sz]ation|work permit|visa|passport|right to work|green card|residen(?:t|cy))\b", re.I),
     "A personal status is claimed that is not on the resume. Confirm it is true before sending.", WARN),
    ("language", re.compile(r"\b(?:fluent|native speaker|bilingual|mother tongue)\b", re.I),
     "A language level is claimed that is not on the resume. Confirm it is true before sending.", WARN),
]
_LANGS = ("german", "japanese", "chinese", "spanish", "italian", "portuguese", "russian", "turkish", "dutch", "korean", "hindi", "english", "french", "arabic")
_LEADERSHIP = re.compile(r"\b(?:led|lead|leading|manage[sd]?|managing|supervis\w+|directed|headed|oversaw|mentored|coached|squad|team of|in charge)\b", re.I)
_LEADER_STEM = re.compile(r"\b(?:led|lead\w*|manag\w+|supervis\w+|direct(?:ed|or)|head\w*|oversaw|mentor\w*|coach\w*|in charge)\b", re.I)
_SENIORITY = ("senior", "staff", "principal", "lead", "head of", "director", "vp", "vice president", "chief", "cto", "architect", "manager", "founder", "owner")
_LEADER_TITLES = {"manager", "director", "head", "chief", "lead", "principal", "architect", "vp", "founder", "cto", "ceo"}
_DEGREE_WORD = re.compile(r"\b(?:bachelor|b\.?sc|licen[cs]e|master|m\.?sc|mba|ph\.?d|doctorate|doctoral|diploma)\b", re.I)
_EMPLOYER_FACT = re.compile(r"\b(?:acquisition|acquired|merger|ipo|funding|raised|series [a-e]|valuation|revenue|profit|launched|opened|offices?|headquarters|expansion|expanded|award|awarded|ranked|record|customers|founded|partnership|announced|recent|recently|latest)\b", re.I)
_STOP = {"the", "and", "for", "with", "that", "this", "your", "you", "our", "its", "into", "from", "have", "has", "was", "are", "will", "would", "about",
         "role", "team", "work", "join", "love", "like", "much", "very", "also", "more", "than", "what", "when", "where", "which", "their", "them"}


# ------------------------------------------------------------------ the checks

def _claim_sentence(s: str, resume_like: bool) -> bool:
    if resume_like and _BULLET.match(s):
        return True
    return bool(_FIRST.search(s))


def _check_employer(s: str, fb: FactBase, out: list[Claim]) -> None:
    for m in _ENTITY.finditer(s):
        ent = _clean_entity(m.group(1))
        if not ent or ent.lower() in _NOT_ENTITY or sk.extract(ent):
            continue
        first = ent.split()[0].lower()
        if first in _NOT_ENTITY:
            continue
        if fb.company and fb.job_company_low and ent.lower().startswith(fb.job_company_low.split()[0]):
            if re.search(rf"\b(?:at|with|for)\s+{re.escape(ent)}\s*,?\s+(?:i|we)\s+(?:\w+\s+){{0,2}}?(?:\w+ed|led|built|ran|wrote|made|cut|grew)\b", s, re.I) or \
               re.search(rf"\b(?:previously|formerly|used to|once)\s+(?:worked|work)\s+(?:at|for|with)\s+{re.escape(ent)}", s, re.I):
                out.append(Claim(s, BLOCK, "employer", f"The sentence says the candidate worked at {ent}, the employer being applied to. The resume does not show that."))
            continue
        if not fb.knows_entity(ent):
            out.append(Claim(s, BLOCK, "employer", f"'{ent}' is not an employer or school on the resume."))


def _check_degree(s: str, fb: FactBase, out: list[Claim]) -> None:
    claimed = _levels(" ".join(m.group(0) for m in _DEGREE_WORD.finditer(s)))
    if not claimed:
        return
    missing = claimed - fb.levels
    if missing and not _LEARNING.search(s):
        out.append(Claim(s, BLOCK, "degree", f"A {', '.join(sorted(missing))} degree is claimed. The resume shows: {', '.join(sorted(fb.levels)) or 'no degree'}."))


def _check_title_and_leadership(s: str, fb: FactBase, out: list[Claim]) -> None:
    if _APPLYING.search(s):
        return
    for m in re.finditer(r"\b(?i:as|was|became|promoted to|serving as|served as|role as)\s+(?:(?i:an?|the)\s+)?([A-Z][\w-]*(?:\s+[A-Z][\w-]*){0,3})", s):
        title = m.group(1)
        toks = [t.lower() for t in title.split() if t.lower() not in ("at", "of", "the", "i")]
        unknown = [t for t in toks if t not in fb.roles and t not in fb.corpus]
        senior_unknown = [t for t in toks if t in _LEADER_TITLES and t not in fb.roles]
        if unknown or senior_unknown:
            out.append(Claim(s, BLOCK, "title", f"The title '{title}' is not on the resume."))
            return
    if _LEADERSHIP.search(s) and not _LEARNING.search(s) and _FIRST.search(s) and not _LEADER_STEM.search(fb.corpus):
        out.append(Claim(s, BLOCK, "leadership", "The sentence claims leading or managing people. The resume shows no leadership."))
        return
    low = s.lower()
    for w in _SENIORITY:
        if re.search(rf"\b(?:i am|i'm|i was|as)\s+(?:an?\s+)?{re.escape(w)}\b", low) and w not in fb.roles and w not in fb.corpus:
            out.append(Claim(s, BLOCK, "title", f"The sentence claims seniority ('{w}') that the resume does not show."))
            return


def _check_skills(s: str, fb: FactBase, out: list[Claim], resume_like: bool) -> None:
    if not resume_like:
        if not (_FIRST.search(s) and _ASSERT.search(s)):
            return
        if _APPLYING.search(s) and not re.search(r"\b(?:which|that)\s+i\s+(?:use|know|have|run|work)", s, re.I):
            return
    missing = []
    for clause in _clauses(s):
        if not resume_like and _LEARNING.search(clause):
            continue
        for skill in sk.extract(clause):
            if skill.lower() not in fb.skills and skill not in missing:
                missing.append(skill)
    if missing:
        out.append(Claim(s, BLOCK, "skill", "Skill(s) stated as experience that are not on the resume: " + ", ".join(missing[:5]) + "."))


def _check_quantities(s: str, fb: FactBase, out: list[Claim]) -> None:
    if _LEARNING.search(s) and not re.search(r"\d", s):
        return
    bad = []
    for v, surface in quantities(s):
        if v <= 2 or _YEAR.match(str(int(v))) and v == int(v):
            continue
        is_years = re.search(re.escape(surface) + r"\+?\s*(?:years?|yrs?)\b", s, re.I) or surface.lower() == "decade" or re.search(r"\b(?:a|one)\s+decade\b", s, re.I) and v == 10
        if is_years:
            if fb.years and not (fb.years - 1.5 <= v <= fb.years + 0.5) and not fb.has_number(v):
                bad.append(f"{surface} years (the resume shows about {fb.years:g})")
            continue
        if not fb.has_number(v):
            bad.append(surface)
    if bad:
        out.append(Claim(s, BLOCK, "number", "Number(s) not on the resume: " + ", ".join(bad[:4]) + "."))


def _check_years_as_dates(s: str, fb: FactBase, out: list[Claim]) -> None:
    unknown = [m for m in re.findall(r"\b(?:19[89]\d|20[0-3]\d)\b", s) if not fb.has_number(float(m))]
    if unknown:
        out.append(Claim(s, WARN, "date", "Date(s) not on the resume: " + ", ".join(sorted(set(unknown))) + "."))


def _check_credentials(s: str, fb: FactBase, out: list[Claim]) -> None:
    if _LEARNING.search(s) or (_APPLYING.search(s) and not _PAST_CLAIM.search(s)):
        return
    for code, rx, msg, sev in _CREDENTIALS:
        m = rx.search(s)
        if not m:
            continue
        if code == "language":
            named = [l for l in _LANGS if l in s.lower() and l not in fb.corpus]
            if named:
                out.append(Claim(s, sev, code, f"{msg} ({', '.join(named)})"))
            continue
        if code in ("exit",) and re.search(rf"\b{re.escape(fb.company.lower())}\b", s.lower()) and fb.company:
            continue                       # about the target employer: handled by the employer-fact check
        if not rx.search(fb.corpus):
            out.append(Claim(s, sev, code, msg))


def _check_employer_fact(s: str, fb: FactBase, out: list[Claim]) -> None:
    """Facts about the employer must come from the posting. The resume cannot support them."""
    if not fb.job_text.strip():
        return                            # no posting to check the employer's facts against
    low = s.lower()
    mentions = (fb.job_company_low and re.search(rf"\b{re.escape(fb.job_company_low)}\b", low)) or re.search(r"\byour (?:company|team|platform|products?|mission|culture|growth|clients|customers)\b", low)
    if not mentions:
        return
    specifics: list[str] = []
    for m in _EMPLOYER_FACT.finditer(s):
        specifics.append(m.group(0))
    for v, surface in quantities(s):
        if v > 2 or _YEAR.match(str(int(v))):
            specifics.append(surface)
    for m in re.finditer(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b", s):
        ent = m.group(1)
        if m.start() == 0:
            continue                      # the first word of a sentence is capitalized anyway
        if ent.lower() in _NOT_ENTITY or ent.lower() == fb.job_company_low or ent.lower() in fb.corpus or sk.extract(ent):
            continue
        if ent.lower() in fb.job_text or any(w.lower() in fb.job_text for w in ent.split()):
            continue
        if re.match(r"(?:I|Dear|Thank|Best|Kind|Sincerely|Regards)\b", ent):
            continue
        specifics.append(ent)
    unsupported = []
    for sp in dict.fromkeys(specifics):
        key = sp.lower()
        if key in fb.job_text or (len(key) > 5 and key[:5] in fb.job_text):
            continue
        unsupported.append(sp)
    if unsupported:
        out.append(Claim(s, WARN, "employer_fact", "The sentence states facts about the employer that the posting does not contain: "
                         + ", ".join(unsupported[:5]) + ". Remove them or check them yourself."))


def check(text: str, profile: dict, job: Optional[dict] = None, kind: str = "other") -> list[Claim]:
    """All claim findings for a text. The caller decides what to do with blocks and warnings."""
    fb = FactBase(profile, job)
    resume_like = kind == "resume"
    out: list[Claim] = []
    for s in sentences(text):
        if len(s) < 8:
            continue
        found: list[Claim] = []
        if resume_like or _claim_sentence(s, resume_like):
            _check_employer(s, fb, found)
            _check_degree(s, fb, found)
            _check_title_and_leadership(s, fb, found)
            _check_skills(s, fb, found, resume_like)
            _check_quantities(s, fb, found)
            _check_credentials(s, fb, found)
            if not any(c.code == "number" for c in found):
                _check_years_as_dates(s, fb, found)
        if kind in ("cover_letter", "outreach", "other"):
            _check_employer_fact(s, fb, found)
        seen = set()
        for c in found:
            if c.code not in seen:
                seen.add(c.code)
                out.append(c)
    return out
