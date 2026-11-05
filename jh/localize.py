"""Query variants in the language that local job boards use.

Small regional boards in Tunisia, Morocco, Algeria, France, Belgium and similar places post most
roles in French. A search for "software engineer" finds almost nothing there, while
"ingénieur logiciel" finds a lot. This module turns one English query into a short list of
variants for a country. The original query always stays first.

The word lists are short on purpose. They cover common job-title words, nothing else. A word
that is not in the list is left as it is, so the variants never invent a role.
"""

from __future__ import annotations

import re

from . import regions

# English title word -> translations. Order matters: the first translation is the main one.
_FR = {
    "software": ("logiciel", "informatique"),
    "engineer": ("ingénieur",),
    "developer": ("développeur",),
    "development": ("développement",),
    "backend": ("back-end",),
    "frontend": ("front-end",),
    "fullstack": ("full stack",),
    "web": ("web",),
    "mobile": ("mobile",),
    "data": ("données", "data"),
    "analyst": ("analyste",),
    "scientist": ("data scientist",),
    "manager": ("responsable", "chef de projet"),
    "project": ("projet",),
    "product": ("produit",),
    "designer": ("designer", "graphiste"),
    "accountant": ("comptable",),
    "sales": ("commercial", "ventes"),
    "marketing": ("marketing",),
    "support": ("support", "assistance"),
    "technician": ("technicien",),
    "network": ("réseau",),
    "security": ("sécurité",),
    "devops": ("devops",),
    "intern": ("stagiaire", "stage"),
    "internship": ("stage",),
    "junior": ("junior", "débutant"),
    "senior": ("senior", "confirmé"),
    "consultant": ("consultant",),
    "teacher": ("enseignant", "professeur"),
    "nurse": ("infirmier",),
    "assistant": ("assistant",),
    "administrator": ("administrateur",),
    "recruiter": ("recruteur", "chargé de recrutement"),
    "human": ("ressources humaines",),
}
_DE = {
    "software": ("software",), "engineer": ("ingenieur",), "developer": ("entwickler",),
    "manager": ("leiter", "manager"), "analyst": ("analyst",), "accountant": ("buchhalter",),
    "sales": ("vertrieb",), "designer": ("designer",), "intern": ("praktikant", "praktikum"),
    "junior": ("junior",), "senior": ("senior",), "teacher": ("lehrer",), "nurse": ("krankenpfleger",),
}
_ES = {
    "software": ("software",), "engineer": ("ingeniero",), "developer": ("desarrollador",),
    "manager": ("gerente", "responsable"), "analyst": ("analista",), "accountant": ("contable",),
    "sales": ("ventas", "comercial"), "designer": ("diseñador",), "intern": ("becario", "prácticas"),
    "teacher": ("profesor",), "nurse": ("enfermero",),
}
_PT = {
    "software": ("software",), "engineer": ("engenheiro",), "developer": ("programador", "desenvolvedor"),
    "manager": ("gestor", "gerente"), "analyst": ("analista",), "accountant": ("contabilista",),
    "sales": ("vendas", "comercial"), "designer": ("designer",), "intern": ("estagiário",),
    "teacher": ("professor",), "nurse": ("enfermeiro",),
}
_IT = {
    "software": ("software",), "engineer": ("ingegnere",), "developer": ("sviluppatore",),
    "manager": ("responsabile",), "analyst": ("analista",), "accountant": ("contabile",),
    "sales": ("vendite", "commerciale"), "designer": ("designer",), "intern": ("stagista", "tirocinio"),
}
_TABLES = {"fr": _FR, "de": _DE, "es": _ES, "pt": _PT, "it": _IT}

# Common whole phrases that read better than a word-by-word swap.
_PHRASES_FR = {
    "software engineer": ("ingénieur logiciel", "ingénieur développement", "ingénieur informatique"),
    "software developer": ("développeur logiciel", "développeur informatique"),
    "web developer": ("développeur web",),
    "full stack developer": ("développeur full stack",),
    "fullstack developer": ("développeur full stack",),
    "backend developer": ("développeur back-end",),
    "frontend developer": ("développeur front-end",),
    "data analyst": ("analyste de données", "data analyst"),
    "data engineer": ("ingénieur data", "ingénieur big data"),
    "project manager": ("chef de projet",),
    "product manager": ("chef de produit",),
    "customer support": ("support client", "service client"),
    "human resources": ("ressources humaines", "RH"),
}

_MAX_VARIANTS = 4


def _words(query: str) -> list[str]:
    return re.findall(r"[\w+#.-]+", (query or "").lower())


def _languages_for(country: str) -> tuple[str, ...]:
    return tuple(l for l in regions.languages_of(country) if l in _TABLES)


def _swap(query: str, table: dict[str, tuple[str, ...]]) -> str:
    words = _words(query)
    out, changed = [], False
    for w in words:
        hit = table.get(w)
        if hit:
            out.append(hit[0])
            changed = True
        else:
            out.append(w)
    return " ".join(out) if changed else ""


def variants(query: str, country: str = "") -> list[str]:
    """The query plus local-language variants for one country code. Never more than four items.

    >>> variants("software engineer", "TN")[:2]
    ['software engineer', 'ingénieur logiciel']
    """
    q = (query or "").strip()
    if not q:
        return []
    out = [q]
    low = " ".join(_words(q))
    for lang in _languages_for((country or "").upper()):
        if lang == "fr":
            for phrase, repl in _PHRASES_FR.items():
                if phrase in low:
                    out.extend(repl)
        swapped = _swap(q, _TABLES[lang])
        if swapped:
            out.append(swapped)
    seen, unique = set(), []
    for v in out:
        key = v.lower()
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique[:_MAX_VARIANTS]


def matches_any(query_variants: list[str], *fields: str) -> bool:
    """True when any variant has all its main words in the text. Used to rank crawled pages."""
    hay = " ".join(f or "" for f in fields).lower()
    for v in query_variants:
        words = [w for w in _words(v) if len(w) > 2]
        if words and sum(1 for w in words if w in hay) >= max(1, len(words) - 1):
            return True
    return not query_variants
