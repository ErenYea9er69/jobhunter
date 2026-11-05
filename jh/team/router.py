"""Turn a request into intents and entities. Rules, so it needs no model key.

The AI that talks to the client is the CEO. It can pass ``hints`` (role, location, job_id, ...) so this
router rarely has to guess. When the hints are missing, patterns in English and French, and a few Arabic
words, cover the usual requests. An unclear request becomes the ``help`` intent.

Intents: setup, hunt, saved, apply, explain, interview, outreach, skills, track, feedback, export, status,
recheck, help.

References. A request often points at a job without an id: "the second one", "number 3", "the Adyen job".
The router extracts that pointer as ``reference`` (an ordinal like "2", or a lowercase company name). The CEO
resolves it against the last search. The router never guesses a job id: an id comes from the hints or the
text, or it stays empty.

``jh/team/evals.py`` measures this router on fixed phrasings, plus a held-out set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ORDER = ("setup", "hunt", "saved", "apply", "explain", "interview", "outreach", "skills", "track", "feedback", "export", "status", "recheck", "help", "unclear")

_ORD_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
              "premier": 1, "première": 1, "deuxième": 2, "troisième": 3, "quatrième": 4, "cinquième": 5, "last": -1,
              "الأول": 1, "الأولى": 1, "الثاني": 2, "الثانية": 2, "الثالث": 3, "الثالثة": 3}
_ORD_RX = re.compile(
    r"\b(?:the\s+|la\s+|le\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last|premier|première|deuxième|troisième|quatrième|cinquième)"
    r"\s+(?:one|job|listing|result|offer|posting|role|position|offre|poste|annonce)\b"
    r"|\b(?:number|no\.?|n°|result|listing|job|option)\s*#?(\d{1,2})\b|(?<![\w/])#(\d{1,2})\b|\b(\d{1,2})(?:st|nd|rd|th)\s+(?:one|job|listing|result)\b"
    r"|(الأول|الأولى|الثاني|الثانية|الثالث|الثالثة)", re.I)
_JOB_ID = re.compile(r"\b[0-9a-f]{16}\b")

_HUNT_VERB = (r"(?:(?<!job )\bsearch(?:\s+for)?\b|\bfind\b|\blook(?:ing)?\s+for\b|\bhunt\w*|\bshow\s+me\b|\bget\s+me\b|\bcherche\w*|\btrouve\w*|\brecherche\w*"
              r"|\bany\s+(?:\w+\s+){0,3}(?:jobs?|roles?|positions?|openings?)\b|\bstartups?\s+hiring\b|\bcompanies\s+hiring\b|\bwho(?:'s|\s+is)\s+hiring\b"
              r"|\bi\s+(?:need|want|am\s+looking\s+for|['’]m\s+looking\s+for)\s+(?:an?\s+)?(?:\w+\s+){0,4}?(?:jobs?|positions?|roles?|openings?|postes?)\b)"
              r"|ابحث|أبحث|جد لي|بحث عن")
_P: dict[str, str] = {
    "setup": r"\b(?:set ?up|set me up|get started|onboard\w*|configure|scan\b.{0,20}\bresumes?|parse\b.{0,20}\bresume|my preferences|preferences|settings|configurer|préférences?)\b"
             r"|\b(?:i|we)\s+(?:want|would like|wish|prefer)\s+to\s+(?:work|live|relocate|move)\b|\bi['’]d\s+like\s+to\s+(?:work|live|relocate)\b|\b(?:je\s+veux|je\s+voudrais)\s+travailler\b|\bopen to relocat\w+"
             r"|\badd\s+(?:a\s+|the\s+)?(?:job\s+)?(?:source|site|feed|company|career page)\b|\b(?:update|change|set|switch)\s+my\s+(?:target\s+)?(?:countries|country|preferences|location|work mode|salary|titles?)\b|\bstart\s+over\b|أريد أن أعمل|إعدادات|اعدادات",
    "saved": r"\b(?:saved|stored|earlier|previous(?:ly)?|already found)\s+(?:jobs?|results?|listings?|matches)\b|\blist\s+(?:the\s+)?jobs\s+(?:you\s+)?(?:found|saved)\b|\bwhat['’]?s\s+new\b|\banything\s+new\b"
             r"|\bany\s+new\s+(?:jobs?|matches|results)\b|\bnew\s+since\b|\bnew\s+matches\b|\bwhat\s+you\s+found\b|\blast\s+time\b|\bshow\s+(?:me\s+)?(?:my\s+)?(?:saved|stored)\b|\bmy\s+saved\b|الوظائف المحفوظة|offres\s+(?:sauvegardées|enregistrées)",
    "apply": r"\b(?:apply|application|prepare|tailor\w*|cover letter|resume|cv|postuler|candidature|lettre|screening|ready my)\b|رسالة تقديم|تقديم|جهز|جهّز",
    "explain": r"\b(?:explain|why\b.{0,30}\b(?:score|fit|rank|match|low|high)|tell me (?:more )?about(?! yourself)|more (?:info|details?) (?:on|about)|details? (?:of|on|about)|what['’]?s missing|missing from|how (?:well|good)|am i a (?:good )?fit|fit score|breakdown|compare|what(?:['’]s| is) wrong with|\bmy fit\b)\b|اشرح|لماذا",
    "interview": r"\b(?:interview\w*|entretien\w*|mock\b|practice (?:questions|answers)|(?:check|evaluate|score|review|rate|grade)\s+my\s+answers?|tell me about yourself)\b|مقابلة",
    "outreach": r"\b(?:outreach|recruiter|hiring manager|linkedin (?:note|message)|follow[- ]?up (?:email|message|note)|relance|thank[- ]you note|message the)\b|\bsend .{0,30}\ba note\b",
    "skills": r"\b(?:skills? gap|gap report|roadmap|what (?:should|do) i (?:learn|study)|skills? (?:should|to) (?:i )?learn|skills? am i missing|which skills|learning plan|upskill\w*)\b",
    "track": r"\b(?:i|we)\s+(?:just\s+|already\s+|have\s+)?(?:applied|sent|submitted)\b|\bj['’]ai\s+postul|\b(?:i\s+got|i\s+have|i\s+received|got)\s+(?:an?\s+|the\s+)?(?:interview|offer|rejection|callback)\b"
             r"|\b(?:invited|called|emailed|contacted|offered)\s+me\b|\b(?:turned|let)\s+me\s+down\b|\bi\s+(?:was|got)\s+(?:rejected|declined|ghosted)\b|\brejected\s+(?:by|me)\b|\bi\s+(?:was|am)\s+rejected\b|\boffer\s+from\b"
             r"|\binterview\s+(?:is\s+)?scheduled\b|\bghosted\b|\bi\s+(?:just\s+)?(?:interviewed|had\s+an\s+interview|did\s+an\s+interview)\b|تقدمت|تم رفضي|رفضوني|قبلوني",
    "feedback": r"\b(?:not interested in|no interest in|(?:don['’]t|do not|never)\s+(?:show|want|like)|stop\s+showing|exclude|avoid|hide|no more|skip|filter\s+out|leave\s+out)\b|\bremove\b.{0,30}\bfrom\s+(?:my\s+)?(?:results|search|list|feed)\b|لا أريد|لا اريد",
    "recheck": r"\b(?:re-?check|double[- ]check|verify|fact[- ]?check|hallucinat\w*|vérifie\w*|scam|fake|legit(?:imate)?|still\s+(?:open|available|there|active))\b|\bis (?:this|it|that|job)\b.{0,30}\b(?:real|still)\b|تحقق",
    "export": r"\b(?:export|download|save|convert)\b.{0,30}\b(?:resume|cv)\b|\b(?:resume|cv)\b.{0,30}\bas\s+(?:a\s+)?(?:pdf|docx|word|txt|html)\b",
    "status": r"\b(?:status|digest|pipeline|my applications|tracker|where do i stand|funnel|suivi|mes\s+candidatures|candidatures\s+en\s+cours|overdue|follow[- ]?ups?|any\s+updates?|how (?:is|am)\b.{0,25}(?:search|going|doing)|how(?:'s| is) my (?:job )?search)\b|حالة طلباتي|حالة الطلبات|وضع طلباتي",
    "help": r"^\s*(?:hello|hi|hey|salut|bonjour|bonsoir|marhaba|help|aide)\b|\bwhat can you do\b|\bhow does this work\b|\bwhat do you do\b|^\s*(?:مرحبا|اهلا|أهلا)",
    "full": r"\bfind\b.*\band\b.*\bapply\b|\bend[- ]to[- ]end\b|\bdo everything\b|\bapply for me\b|\bfull (?:search|hunt)\b",
}
_SMALL = r"\b(?:small(?:er)?|startups?|smes?|local|regional|lesser[- ]known|hidden|not (?:only )?(?:the )?(?:big|famous)|pme|petites? (?:entreprises?|sociétés?))\b|الشركات الصغيرة|شركات صغيرة"
_WORK_MODE = {"Remote": r"\bremote(?:ly)?\b|\bà distance\b|عن بعد", "Hybrid": r"\bhybrid\w*\b", "Onsite": r"\bon[- ]?site\b|\bsur place\b|\bin[- ]office\b"}

_ROLE = re.compile(
    r"(?:find|search(?: for)?|look(?:ing)? for|hunt(?: for)?|show me|get me|cherche|trouve|recherche)\s+(?:me\s+)?(?:some\s+|any\s+|new\s+|a\s+|an\s+)?"
    r"(?:small |smaller |local |regional |remote |junior |senior )*(.+?)\s+(?:jobs?|roles?|positions?|openings?|vacancies|offres?|postes?)\b", re.I)
_ROLE_FR = re.compile(r"\b(?:offres?|postes?|emplois?)\s+(?:de|d['’]|en)\s*(.+?)(?:\s+(?:à|a|au|en|in)\s+[A-ZÀ-Ý]|[.!?]?$)", re.I)
_ROLE_HIRING = re.compile(r"\bhiring\s+(.+?)(?:\s+(?:in|near|around)\s+[A-Z]|[.!?]?$)", re.I)
_ROLE_ANY = re.compile(r"\b(?:any|some)\s+(?:remote\s+|new\s+|hybrid\s+|local\s+)?(.+?)\s+(?:jobs?|roles?|positions?|openings?)\b", re.I)
_ROLE_LOOK = re.compile(r"\blook\s+for\s+(.+?)\s+(?:openings?|vacancies|positions?)\b", re.I)
_STOP_ROLE = {"me", "a", "an", "some", "any", "new", "the", "my", "des", "de", "les", "du", "la", "le", "un", "une", "d", "startups", "companies"}
_PLACE = re.compile(r"\b(?:in|near|around|à|a|au|en)\s+([A-ZÀ-Ý][\w'’-]+(?:[ ,]+[A-ZÀ-Ý][\w'’-]+){0,2})\s*[.!?]?\s*$")
_PLACES_LIST = re.compile(r"\b(?:(?:work|live|relocate|move|working|travailler|settle)\s+(?:in|to|en|à|au)|(?:target\s+)?countr(?:y|ies)\s+to)\s+(.+?)[.!?]?$", re.I)
_CAP = re.compile(r"\b([A-ZÀ-Ý][\w&'’-]{1,}(?:\s+[A-ZÀ-Ý][\w&'’-]+){0,2})\b")
_NOT_COMPANY = {"i", "i'm", "i've", "i'd", "find", "show", "write", "draft", "prepare", "apply", "tell", "explain", "what", "what's", "why", "how", "is", "are", "can",
                "could", "would", "please", "my", "the", "stop", "exclude", "list", "send", "practice", "download", "export", "ready", "hello", "hi", "hey",
                "salut", "bonjour", "any", "anything", "which", "message", "check", "compare", "cover", "set", "get", "save", "never", "not", "no", "don't",
                "do", "make", "give", "help", "recheck", "verify", "double", "also", "and", "or", "monday", "tuesday", "wednesday", "thursday", "friday",
                "saturday", "sunday", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
                "pdf", "docx", "cv", "linkedin", "python", "java", "javascript", "react", "node", "sql", "aws", "docker", "english", "french", "arabic",
                "je", "j'ai", "mon", "ma", "mes", "un", "une", "des", "trouve", "cherche", "prépare", "can", "tell", "is"}
_CONTEXT_BEFORE = re.compile(r"\b(?:at|for|with|from|to|by|chez|of|about|de)\s+$", re.I)
_CONTEXT_AFTER = re.compile(r"^\s*(?:['’]s\s+)?(?:job|role|position|listing|offer|opening|interview|application|recruiter|one|posting|invited|turned|rejected|offered|called|emailed|contacted|declined|ghosted|got|sent|accepted)\b", re.I)
_LOCATION_BEFORE = re.compile(r"\b(?:in|near|around|à|en|au|aux)\s+$", re.I)
_PLACE_WORDS = {"tunisia", "tunis", "sfax", "sousse", "france", "paris", "morocco", "algeria", "egypt", "germany", "netherlands", "spain", "italy", "canada", "usa", "uk",
                "europe", "africa", "remote", "berlin", "amsterdam", "london", "casablanca", "cairo", "algiers", "tunisie", "maroc", "algérie", "allemagne"}

_STATUS_WORDS = [
    ("rejected", r"\b(?:rejected|rejection|turned me down|declined|ghosted|let me down)\b|تم رفضي|رفضوني"),
    ("offer", r"\b(?:got an? offer|offered me|offer from|received an? offer)\b|قبلوني"),
    ("interview", r"\b(?:interview|invited me|called me|scheduled)\b"),
    ("applied", r"\b(?:applied|sent|submitted|postul\w+)\b|تقدمت"),
]
_EXPORT_FMT = re.compile(r"\b(pdf|docx|word|txt|text|html)\b", re.I)


def _singular(role: str) -> str:
    """"backend engineers" -> "backend engineer". Titles on postings are singular, so plural queries miss them.

    Only common title endings change (engineers, developers, analysts, consultants). "sales" and "devops" stay as they are.
    """
    return " ".join(w[:-1] if re.search(r"(?:er|or|st|nt)s$", w, re.I) and len(w) > 4 else w for w in role.split())


@dataclass
class Parsed:
    intents: list[str]
    role: str = ""
    location: str = ""
    job_id: str = ""
    small: bool = False
    docs: set[str] = field(default_factory=set)      # resume, letter, interview, outreach
    reference: str = ""                              # "2" or a lowercase company name
    status: str = ""                                 # for track: applied, interview, offer, rejected
    exclude: list[str] = field(default_factory=list)  # for feedback: keywords
    exclude_companies: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    work_mode: str = ""
    export_format: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"intents": self.intents, "role": self.role, "location": self.location, "job_id": self.job_id,
                             "small_employers": self.small, "documents": sorted(self.docs), "notes": self.notes}
        for k in ("reference", "status", "work_mode", "export_format", "exclude", "exclude_companies", "countries"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        return d


def _has(name: str, text: str) -> bool:
    return bool(re.search(_P[name], text, re.I))


def _reference(text: str) -> str:
    m = _ORD_RX.search(text)
    if m:
        word = (m.group(1) or "").lower()
        if word:
            return str(_ORD_WORDS.get(word, ""))
        for g in (m.group(2), m.group(3), m.group(4)):
            if g:
                return str(int(g))
        if m.group(5):
            return str(_ORD_WORDS.get(m.group(5), ""))
    for m in _CAP.finditer(text):
        name = m.group(1).strip()
        first = name.split()[0].lower()
        if first in _NOT_COMPANY or name.lower() in _PLACE_WORDS:
            continue
        before, after = text[:m.start()], text[m.end():]
        if _LOCATION_BEFORE.search(before):
            continue
        if _CONTEXT_BEFORE.search(before) or _CONTEXT_AFTER.search(after):
            return re.sub(r"['’]s$", "", name).lower()
    return ""


def _split_items(chunk: str) -> list[str]:
    parts = re.split(r",|\band\b|\bet\b|\bou\b|\bor\b|&|\bو\b", chunk, flags=re.I)
    out = []
    for p in parts:
        p = re.sub(r"^(?:the|la|le|les|l['’])\s*", "", p.strip(" .'’"), flags=re.I).strip()
        if p and len(p) < 40 and p.lower() not in ("remote", "home"):
            out.append(p.title() if p.islower() else p)
    return out


def parse(request: str, hints: dict[str, Any] | None = None) -> Parsed:
    hints = hints or {}
    text = (request or "").strip()
    low = text.lower()
    job_id = str(hints.get("job_id") or "").strip()
    if not job_id:
        m = _JOB_ID.search(low)
        job_id = m.group(0) if m else ""
    reference = "" if job_id else (str(hints.get("reference") or "") or _reference(text))

    wanted: set[str] = set()
    for name in ("setup", "saved", "apply", "explain", "interview", "outreach", "skills", "track", "feedback", "recheck", "export", "status", "help"):
        if _has(name, low):
            wanted.add(name)
    if re.search(_HUNT_VERB, low, re.I):
        wanted.add("hunt")
    if hints.get("preferences") or hints.get("add_sources"):
        wanted.add("setup")
    if _has("full", low):
        wanted |= {"hunt", "apply"}
    small = bool(re.search(_SMALL, low, re.I)) or bool(hints.get("small_employers"))
    if small and not (wanted - {"hunt"}):
        wanted.add("hunt")

    pointed = bool(job_id or reference or "this job" in low or "that job" in low)
    request_verb = bool(re.search(r"\b(?:write|draft|prepare|tailor|make|create|ready|generate|prépare\w*|rédige\w*)\b|جهز|جهّز", low))

    if "track" in wanted:                  # a statement of fact about an application is tracking, not prep
        keep_interview = bool(re.search(r"\b(?:prepare|prep|practice|questions|mock)\b", low))
        wanted -= {"hunt", "apply", "explain", "saved", "status", "help", "outreach"}
        if not keep_interview:
            wanted.discard("interview")
    if "feedback" in wanted:
        wanted -= {"hunt", "apply", "explain", "saved", "status", "interview", "help", "setup", "skills", "export"}
    if "export" in wanted:
        wanted -= {"apply", "hunt", "help", "explain", "status", "saved"}
    if "saved" in wanted and not re.search(r"\b(?:find|search|look|hunt)\b", low):
        wanted -= {"hunt", "status"}
    if "recheck" in wanted and (pointed or not (wanted & {"hunt", "apply"})):
        wanted -= {"apply", "hunt", "explain", "help"}
    if "explain" in wanted:
        if "skills" in wanted and not pointed:
            wanted.discard("explain")
        elif re.search(r"\b(?:missing|compare|explain|why|tell me|more (?:info|details?)|details?|breakdown|how (?:well|good))\b", low) or not request_verb:
            wanted -= {"apply", "help"}
    if "interview" in wanted and "apply" in wanted and not re.search(r"\b(?:cover letter|resume|cv|lettre|application|candidature|tailor\w*)\b", low):
        wanted.discard("apply")
    if "skills" in wanted:
        wanted -= ({"help"} if re.search(r"\b(?:find|search|look)\b", low) else {"hunt", "help"})
    if "setup" in wanted and "hunt" in wanted and not re.search(r"\b(?:find|search|look|hunt|cherche|trouve)\b", low):
        wanted.discard("hunt")
    if "outreach" in wanted:
        wanted -= {"status", "help"}
    if "status" in wanted:
        wanted.discard("help")
        if not request_verb:
            wanted.discard("apply")
    if "hunt" in wanted and (job_id or reference) and not _has("full", low):
        wanted.discard("hunt")             # a pointed-at job means "work on it", not "search again"
    if wanted - {"help"}:
        wanted.discard("help")
    ordered = [i for i in ORDER if i in wanted] or ["unclear"]

    docs: set[str] = set()
    if re.search(r"\b(?:cover letter|lettre)\b|رسالة تقديم", low):
        docs.add("letter")
    if re.search(r"\b(?:resume|cv|tailor\w*)\b", low) and "export" not in ordered:
        docs.add("resume")
    if "interview" in ordered:
        docs.add("interview")
    if "outreach" in ordered:
        docs.add("outreach")
    if "apply" in ordered and not docs & {"letter", "resume"}:
        docs |= {"letter", "resume"}

    role = str(hints.get("role") or "").strip()
    if not role and "hunt" in ordered:
        for rx in (_ROLE, _ROLE_FR, _ROLE_HIRING, _ROLE_ANY, _ROLE_LOOK):
            m = rx.search(text)
            cand = m.group(1).strip(" ,.") if m else ""
            if cand and cand.lower() not in _STOP_ROLE and not re.fullmatch(r"(?:small|local|remote|new)", cand, re.I):
                role = cand
                break
    role = _singular(re.sub(r"\b(?:remote|hybrid|small|local)\b", "", role, flags=re.I).strip())
    location = str(hints.get("location") or hints.get("country") or "").strip()
    if not location and "hunt" in ordered:
        m = _PLACE.search(text)
        location = m.group(1).strip(" ,.") if m else ""

    p = Parsed(ordered, role=role, location=location, job_id=job_id, small=small, docs=docs, reference=reference)
    for mode, rx in _WORK_MODE.items():
        if re.search(rx, low, re.I):
            p.work_mode = mode
            break
    if hints.get("work_mode"):
        p.work_mode = str(hints["work_mode"])
    if "track" in ordered:
        for st, rx in _STATUS_WORDS:
            if re.search(rx, low, re.I):
                p.status = st
                break
    if "feedback" in ordered:
        m = re.search(r"(?:not interested in|no interest in|(?:don['’]t|do not)\s+(?:show me|want|like)|never show me(?: jobs?)?(?: (?:from|at))?|stop showing me(?: jobs?)?(?: (?:from|at))?|exclude|avoid|hide|no more|skip)\s+(.+?)(?:\s+(?:again|from now on|anymore|please)\b)?[.!?]?$", text, re.I)
        what = m.group(1).strip() if m else ""
        what = re.sub(r"^(?:jobs?\s+(?:from|at)\s+|jobs?\s+|companies\s+(?:like\s+)?)", "", what, flags=re.I).strip()
        what = re.sub(r"\s+(?:companies|jobs?|roles?|positions?)$", "", what, flags=re.I).strip(" ,.")
        for item in _split_items(what):
            if item[0].isupper() and item.lower() not in ("banks", "consulting"):
                p.exclude_companies.append(item)
            else:
                p.exclude.append(item.lower()[:-1] if item.lower().endswith("s") and len(item) > 4 else item.lower())
    if "setup" in ordered:
        m = _PLACES_LIST.search(text)
        if m:
            p.countries = _split_items(m.group(1))
    if "export" in ordered:
        m = _EXPORT_FMT.search(low)
        fmt = m.group(1).lower() if m else "pdf"
        p.export_format = {"word": "docx", "text": "txt"}.get(fmt, fmt)
    return p
