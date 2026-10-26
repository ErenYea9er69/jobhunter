"""Resume claim provenance and grounding verification.

Connects each candidate claim to its source file and location, builds the
evidence ledger from parsed profiles, checks generated draft claims against
the ledger, and returns unsupported claims for review.

Implements the multi-stage grounding pipeline from the blueprint:
  Stage A: Claim extraction from generated text
  Stage B: Evidence matching against the ledger
  Stage C: Verdict assignment (supported / derived / needs_review / unsupported)
  Stage D: Repair recommendations
  Stage E: Audit manifest
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from . import skills as sk
from .models import (
    ClaimType,
    EvidenceClaim,
    ExtractionStatus,
    GroundingVerdict,
    SourceLocation,
    _new_id,
)
from .util import now_iso


# ──────────────────────────────────────────── constants

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_DATE_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b"
    r"|\b\d{4}\s*[-–]\s*(?:\d{4}|[Pp]resent|[Cc]urrent)\b"
    r"|\b\d{1,2}/\d{4}\b",
    re.IGNORECASE,
)

VALIDATOR_VERSION = "1.0"

# Numbers that are structural, not candidate achievements
_STRUCTURAL_NUMBERS = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}


# ──────────────────────────────────────────── evidence ledger

class EvidenceLedger:
    """Stores and queries all evidence claims for a candidate profile."""

    def __init__(self) -> None:
        self._claims: dict[str, EvidenceClaim] = {}
        self._by_type: dict[ClaimType, list[str]] = {}
        self._by_file: dict[str, list[str]] = {}

    @property
    def claims(self) -> dict[str, EvidenceClaim]:
        return dict(self._claims)

    def __len__(self) -> int:
        return len(self._claims)

    def add(self, claim: EvidenceClaim) -> str:
        """Add a claim and return its evidence_id."""
        self._claims[claim.evidence_id] = claim
        self._by_type.setdefault(claim.claim_type, []).append(claim.evidence_id)
        if claim.source_file:
            self._by_file.setdefault(claim.source_file, []).append(claim.evidence_id)
        return claim.evidence_id

    def get(self, evidence_id: str) -> Optional[EvidenceClaim]:
        return self._claims.get(evidence_id)

    def by_type(self, claim_type: ClaimType) -> list[EvidenceClaim]:
        ids = self._by_type.get(claim_type, [])
        return [self._claims[i] for i in ids if i in self._claims]

    def by_file(self, source_file: str) -> list[EvidenceClaim]:
        ids = self._by_file.get(source_file, [])
        return [self._claims[i] for i in ids if i in self._claims]

    def confirmed_only(self) -> list[EvidenceClaim]:
        return [c for c in self._claims.values() if c.candidate_confirmed]

    def needs_review(self) -> list[EvidenceClaim]:
        return [c for c in self._claims.values()
                if c.extraction_status == ExtractionStatus.NEEDS_REVIEW]

    def all_canonical_values(self) -> set[str]:
        return {c.canonical_value.lower() for c in self._claims.values() if c.canonical_value}

    def skill_values(self) -> set[str]:
        return {c.canonical_value for c in self.by_type(ClaimType.SKILL)}

    def to_list(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._claims.values()]

    def summary(self) -> dict[str, Any]:
        """Return a privacy-safe summary of the ledger."""
        by_type = {}
        for ct in ClaimType:
            items = self.by_type(ct)
            by_type[ct.value] = {
                "count": len(items),
                "confirmed": sum(1 for c in items if c.candidate_confirmed),
                "needs_review": sum(1 for c in items if c.extraction_status == ExtractionStatus.NEEDS_REVIEW),
            }
        return {
            "total_claims": len(self._claims),
            "by_type": by_type,
            "source_files": list(self._by_file.keys()),
        }


# ──────────────────────────────────────────── building the ledger from parsed profiles

def build_ledger_from_profile(profile: dict[str, Any], source_file: str = "") -> EvidenceLedger:
    """Create an EvidenceLedger from a parsed resume profile dict.

    Extracts skills, employment, education, projects, and certifications as
    individual provenance-tracked claims.
    """
    ledger = EvidenceLedger()
    src = source_file or profile.get("_source_file", "")

    # ── skills
    for skill_name in profile.get("skills", []):
        canon = sk.canonicalize(skill_name) if hasattr(sk, "canonicalize") else skill_name
        claim = EvidenceClaim(
            claim_type=ClaimType.SKILL,
            canonical_value=canon,
            raw_value=skill_name,
            source_file=src,
            source_location=SourceLocation(section="Skills"),
            extraction_status=ExtractionStatus.VERIFIED,
            candidate_confirmed=False,
        )
        ledger.add(claim)

    # ── employment
    for exp in profile.get("experience", []):
        claim = EvidenceClaim(
            claim_type=ClaimType.EMPLOYMENT,
            canonical_value=f"{exp.get('role', '')} @ {exp.get('company', '')}",
            raw_value=str(exp),
            source_file=src,
            source_location=SourceLocation(section="Experience"),
            extraction_status=_assess_employment_status(exp),
            candidate_confirmed=False,
        )
        ledger.add(claim)

        # Extract metrics from bullets
        for bullet in exp.get("bullets", []):
            nums = _extract_numbers(bullet)
            for num in nums:
                metric_claim = EvidenceClaim(
                    claim_type=ClaimType.METRIC,
                    canonical_value=num,
                    raw_value=bullet,
                    source_file=src,
                    source_location=SourceLocation(section="Experience", span=bullet[:80]),
                    extraction_status=ExtractionStatus.VERIFIED,
                    candidate_confirmed=False,
                )
                ledger.add(metric_claim)

    # ── education
    for edu in profile.get("education", []):
        claim = EvidenceClaim(
            claim_type=ClaimType.EDUCATION,
            canonical_value=f"{edu.get('degree', '')} — {edu.get('institution', '')}",
            raw_value=str(edu),
            source_file=src,
            source_location=SourceLocation(section="Education"),
            extraction_status=ExtractionStatus.VERIFIED if edu.get("degree") else ExtractionStatus.NEEDS_REVIEW,
            candidate_confirmed=False,
        )
        ledger.add(claim)

    # ── projects
    for proj in profile.get("projects", []):
        name = proj if isinstance(proj, str) else proj.get("name", str(proj))
        claim = EvidenceClaim(
            claim_type=ClaimType.PROJECT,
            canonical_value=name,
            raw_value=str(proj),
            source_file=src,
            source_location=SourceLocation(section="Projects"),
            extraction_status=ExtractionStatus.VERIFIED,
            candidate_confirmed=False,
        )
        ledger.add(claim)

    # ── certifications
    for cert in profile.get("certifications", []):
        name = cert if isinstance(cert, str) else cert.get("name", str(cert))
        claim = EvidenceClaim(
            claim_type=ClaimType.CERTIFICATION,
            canonical_value=name,
            raw_value=str(cert),
            source_file=src,
            source_location=SourceLocation(section="Certifications"),
            extraction_status=ExtractionStatus.NEEDS_REVIEW,
            candidate_confirmed=False,
        )
        ledger.add(claim)

    return ledger


def _assess_employment_status(exp: dict[str, Any]) -> ExtractionStatus:
    """Determine extraction confidence for an employment record."""
    has_role = bool(exp.get("role"))
    has_company = bool(exp.get("company"))
    has_dates = bool(exp.get("start"))
    if has_role and has_company and has_dates:
        return ExtractionStatus.VERIFIED
    if has_role or has_company:
        return ExtractionStatus.NEEDS_REVIEW
    return ExtractionStatus.UNPARSED


def _extract_numbers(text: str) -> list[str]:
    """Extract meaningful numbers from a text (not structural ones)."""
    raw = _NUM_RE.findall(text or "")
    return [n.replace(",", "") for n in raw if n.replace(",", "") not in _STRUCTURAL_NUMBERS]


# ──────────────────────────────────────────── grounding pipeline

class GroundingResult:
    """Container for claim verification results."""

    def __init__(self) -> None:
        self.verdicts: list[dict[str, Any]] = []
        self.supported_count: int = 0
        self.unsupported_count: int = 0
        self.needs_review_count: int = 0
        self.honest_gaps: list[str] = []

    @property
    def is_approved(self) -> bool:
        """True if no critical unsupported claims remain."""
        return self.unsupported_count == 0

    @property
    def status(self) -> str:
        if self.is_approved and self.needs_review_count == 0:
            return "approved"
        if self.is_approved:
            return "needs_review"
        return "needs_review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_claims": len(self.verdicts),
            "supported": self.supported_count,
            "unsupported": self.unsupported_count,
            "needs_review": self.needs_review_count,
            "honest_gaps": self.honest_gaps,
            "validator_version": VALIDATOR_VERSION,
            "verdicts": self.verdicts,
        }


def verify_grounding(
    generated_text: str,
    ledger: EvidenceLedger,
    profile: dict[str, Any],
    job_requirements: Optional[list[str]] = None,
) -> GroundingResult:
    """Run the full multi-stage grounding pipeline on generated text.

    Stage A: Extract factual claims from the generated draft
    Stage B: Match each claim against the evidence ledger
    Stage C: Assign verdict
    Stage D: Collect repair recommendations
    Stage E: Build audit manifest
    """
    result = GroundingResult()
    job_requirements = job_requirements or []

    # ── Stage A: extract claims from generated text
    claims = _extract_claims(generated_text)

    # Build lookup sets from the ledger
    ledger_skills = ledger.skill_values()
    ledger_skills_lower = {s.lower() for s in ledger_skills}
    ledger_values = ledger.all_canonical_values()

    # Build corpus for number matching
    corpus_text = _build_corpus_text(profile)
    corpus_numbers = {n.replace(",", "") for n in _NUM_RE.findall(corpus_text)} - _STRUCTURAL_NUMBERS

    # Years of experience is derivable
    yoe = profile.get("years_of_experience")
    derived_numbers = set()
    if yoe:
        derived_numbers.add(str(int(yoe)))
        derived_numbers.add(str(yoe))
        derived_numbers.add(str(int(yoe) + 1))

    for claim in claims:
        verdict = _match_claim(
            claim, ledger, ledger_skills_lower, ledger_values,
            corpus_numbers, derived_numbers, job_requirements,
        )
        result.verdicts.append(verdict)
        v = verdict["verdict"]
        if v == GroundingVerdict.SUPPORTED.value:
            result.supported_count += 1
        elif v == GroundingVerdict.DERIVED.value:
            result.supported_count += 1
        elif v == GroundingVerdict.NEEDS_REVIEW.value:
            result.needs_review_count += 1
        elif v == GroundingVerdict.UNSUPPORTED.value:
            result.unsupported_count += 1

    # ── Stage D: identify honest gaps
    if job_requirements:
        candidate_skills = {s.lower() for s in profile.get("skills", [])}
        for req in job_requirements:
            req_skills = {s.lower() for s in sk.extract(req)}
            if req_skills and not req_skills.intersection(candidate_skills):
                result.honest_gaps.append(req)

    return result


def _extract_claims(text: str) -> list[dict[str, str]]:
    """Stage A: Split generated text into factual claim fragments."""
    claims = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue
        # Skip purely structural text
        if line.startswith("#") or line.startswith("---"):
            continue

        claim_type = _classify_claim(line)
        if claim_type == "stylistic":
            continue

        claims.append({
            "text": line,
            "claim_type": claim_type,
            "numbers": _extract_numbers(line),
            "skills": list(sk.extract(line)),
        })
    return claims


def _classify_claim(text: str) -> str:
    """Classify a line into a claim category."""
    lower = text.lower()
    if any(kw in lower for kw in ("years", "experience", "worked at", "employed")):
        return "employment"
    if any(kw in lower for kw in ("degree", "bachelor", "master", "phd", "university", "college")):
        return "education"
    if any(kw in lower for kw in ("certified", "certification", "certificate")):
        return "certification"
    if any(kw in lower for kw in ("built", "developed", "designed", "created", "implemented", "led", "managed")):
        return "project"
    if _NUM_RE.search(text):
        return "metric"
    if sk.extract(text):
        return "skill"
    return "stylistic"


def _match_claim(
    claim: dict[str, Any],
    ledger: EvidenceLedger,
    ledger_skills_lower: set[str],
    ledger_values: set[str],
    corpus_numbers: set[str],
    derived_numbers: set[str],
    job_requirements: list[str],
) -> dict[str, Any]:
    """Stage B+C: Match a claim against the ledger and assign a verdict."""
    verdict_info: dict[str, Any] = {
        "claim_text": claim["text"][:200],
        "claim_type": claim["claim_type"],
        "verdict": GroundingVerdict.SUPPORTED.value,
        "evidence_ids": [],
        "issues": [],
    }

    issues = []

    # Check numbers
    for num in claim.get("numbers", []):
        if num in corpus_numbers:
            continue  # supported
        if num in derived_numbers:
            verdict_info["verdict"] = GroundingVerdict.DERIVED.value
            continue
        # Check if it's a job requirement number (not a candidate claim)
        req_text = " ".join(job_requirements)
        if num in {n.replace(",", "") for n in _NUM_RE.findall(req_text)}:
            continue  # this is a job requirement, not candidate claim
        issues.append(f"Unsupported number: {num}")

    # Check skills
    for skill in claim.get("skills", []):
        if skill.lower() in ledger_skills_lower:
            # Find matching evidence
            for ev in ledger.by_type(ClaimType.SKILL):
                if ev.canonical_value.lower() == skill.lower():
                    verdict_info["evidence_ids"].append(ev.evidence_id)
                    break
        elif skill.lower() in {v.lower() for v in ledger_values}:
            pass  # found in broader ledger
        else:
            issues.append(f"Unsupported skill: {skill}")

    # Assign final verdict
    if issues:
        has_number_issue = any("number" in i.lower() for i in issues)
        has_skill_issue = any("skill" in i.lower() for i in issues)
        if has_number_issue:
            verdict_info["verdict"] = GroundingVerdict.UNSUPPORTED.value
        elif has_skill_issue:
            verdict_info["verdict"] = GroundingVerdict.NEEDS_REVIEW.value
        verdict_info["issues"] = issues

    return verdict_info


def _build_corpus_text(profile: dict[str, Any]) -> str:
    """Build a text corpus from the profile for number matching."""
    parts = [
        profile.get("summary", ""),
        " ".join(profile.get("skills", [])),
        profile.get("target_title", ""),
    ]
    for e in profile.get("experience", []):
        parts.extend([e.get("role", ""), e.get("company", ""), " ".join(e.get("bullets", []))])
    for e in profile.get("education", []):
        parts.extend([e.get("degree", ""), e.get("institution", "")])
    return "\n".join(parts)


# ──────────────────────────────────────────── audit manifest

def create_audit_manifest(
    grounding_result: GroundingResult,
    profile_id: str,
    job_id: str,
    prompt_version: str = "",
    artifact_type: str = "tailored_resume",
) -> dict[str, Any]:
    """Stage E: Create an audit manifest recording grounding results."""
    return {
        "manifest_id": _new_id("mfst_"),
        "artifact_type": artifact_type,
        "profile_id": profile_id,
        "job_id": job_id,
        "prompt_version": prompt_version,
        "validator_version": VALIDATOR_VERSION,
        "grounding_status": grounding_result.status,
        "total_claims": len(grounding_result.verdicts),
        "supported": grounding_result.supported_count,
        "unsupported": grounding_result.unsupported_count,
        "needs_review": grounding_result.needs_review_count,
        "honest_gaps": grounding_result.honest_gaps,
        "generated_at": now_iso(),
    }


# ──────────────────────────────────────────── file hashing

def file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file for change detection."""
    try:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""
