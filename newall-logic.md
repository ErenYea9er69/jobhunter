JobHunter MCP Server
Revised Architecture, Operational Flow, and Prompt Contracts
Document status: Proposed target architecture based on the supplied JobHunter description. Keep existing behavior where it already meets these contracts. Treat each item as a target only until tests confirm the code implements it.
1. Executive Summary and Core Engineering Philosophy
JobHunter is a local-first career workflow engine exposed through the Model Context Protocol (MCP). It helps a candidate discover relevant jobs, compare resume variants, assess role fit, prepare truthful application material, practice interviews, and track applications from one AI assistant.
Core operating principles
1. Candidate facts remain the source of truth. Resume files and candidate-confirmed profile data define work history, skills, qualifications, projects, dates, and measurable results. The model may reorganize and explain those facts. It must not create new ones.
2. Deterministic code owns measurable decisions. Parsers, canonicalization, deduplication, eligibility filters, score calculations, date arithmetic, persistence, and output checks run in Python. The LLM handles synthesis, writing, and coaching.
3. Every recommendation has an explanation. Job scores show component scores, matched requirements, missing requirements, data quality, and the source URL. Tailored claims link back to candidate evidence.
4. External job content remains untrusted data. Job descriptions, search results, uploaded documents, and tool responses never become instructions for the server or for other tools.
5. The user controls external actions. JobHunter prepares content and tracks user-confirmed application events. It does not silently submit applications, send recruiter messages, or bypass platform restrictions.
6. Local data stays local by default. Resume files, application history, generated drafts, and preferences live in the configured workspace. Network requests retrieve job data from approved sources. Telemetry excludes resume text, private application answers, tokens, and full prompts.
7. Failures remain visible. The server returns partial results with source-level warnings when possible. It does not quietly turn a failed source into an empty result or describe an estimate as verified fact.
Target architecture
MCP HOST
Cursor | Claude Desktop | VS Code | Antigravity | Other compatible hosts
                         |
                  MCP over stdio
                         |
                mcp_server.py
       Protocol setup, logging, dispatch, shutdown
                         |
                   jh/mcp_tools.py
        Typed tool contracts and resource registration
                         |
                 Workflow services
     Search | Fit | Resume | Interview | Application tracking
                         |
                  Domain engine
 Parsing | Evidence | Scoring | Dedup | ATS audit | Export
                         |
           Source adapters and local persistence
 Approved job feeds | JSON state | Rebuildable SQLite index
Separation of responsibilities
- MCP layer: Defines tool and resource interfaces, validates inputs, formats results, and keeps standard output reserved for protocol messages.
- Workflow layer: Coordinates steps and manages partial failure, retries, caching, and workflow status.
- Domain layer: Implements parsing, normalization, scoring, grounding, deduplication, ATS checks, and application state transitions.
- LLM prompt layer: Drafts or evaluates content using structured evidence bundles and strict output contracts.
- Storage layer: Preserves user-managed state in versioned JSON files and uses SQLite as a disposable query index.
- Source layer: Retrieves jobs through documented, public, or otherwise explicitly authorized endpoints. Each adapter declares its capabilities, data freshness, and access policy.
The architecture retains the current 100-point fit model and the eight prompt files. The main change is to make evidence, data quality, source policy, user approval, and automated validation consistent across the entire flow.
2. Target Personas and Real-World Use Cases
Persona A: Experienced engineers targeting specialist roles
Goal: Find roles where technical depth, architecture ownership, scale, and domain experience matter.

Flow:
1. The candidate selects a resume variant and provides role, location, work-mode, and compensation preferences.
2. search_jobs queries available sources and labels each result with its source and last-verified time.
3. The pipeline normalizes and deduplicates postings, then applies explicit eligibility filters.
4. score_job ranks the remaining jobs against the selected profile.
5. get_job_details, ats_audit, and gap_report explain the strongest matches and the most important missing requirements.
6. tailor_resume creates a role-specific draft using only verified evidence.
7. The candidate reviews the draft and exports an ATS-friendly version.
Persona B: Candidates with several resume variants
Goal: Choose the strongest accurate resume for each role without rewriting the same career history from scratch.

Flow:
1. JobHunter discovers supported resume files in configured folders.
2. The parser creates a separate profile for each file and records extraction confidence and source locations.
3. The candidate reviews unclear dates, skills, job titles, or broken text before the profile becomes trusted evidence.
4. compare_resumes scores every usable variant against the same job and returns a ranked comparison with reasons.
5. The candidate selects the preferred variant. JobHunter preserves the original and saves the new tailored output separately.
Persona C: Candidates managing many applications
Goal: Keep application stages, next actions, interview notes, and follow-up dates consistent.

Flow:
1. The candidate confirms that an application was submitted and selects or verifies the matching job.
2. track_application creates or updates the application record and appends a stage-history event.
3. JobHunter calculates next_action_at from configurable rules, the application stage, and the last event.
4. list_due_actions or the daily digest surfaces due follow-ups when the MCP server runs.
5. The follow-up prompt drafts a message using the actual application history. It never sends the message automatically.
Persona D: Early-career candidates changing specializations
Goal: Understand realistic fit, separate transferable experience from missing skills, and build a practical development plan.

Flow:
1. JobHunter compares current evidence with repeated requirements across selected jobs.
2. It separates verified skills, adjacent experience, unverified claims, and genuine learning needs.
3. career_skill_roadmap turns the most relevant gaps into staged projects and evidence-based milestones.
4. The candidate can update the profile after completing work and rerun fit analysis.
3. File and Directory Map
Keep existing modules that already satisfy the contracts below. Add a module only when it provides a clear boundary or enables independent testing.
jobhunter/
├── mcp_server.py                     # MCP process entry point and lifecycle
├── pyproject.toml                    # Package metadata and supported Python range
├── requirements-mcp.txt              # Direct MCP dependency, if retained
├── prompts/
│   ├── resume_tailor_6sec.md          # Resume tailoring contract
│   ├── cover_letter_pitch.md          # Cover letter contract
│   ├── interview_prep_copilot.md      # Interview preparation contract
│   ├── screening_question_solver.md   # Screening answer contract
│   ├── recruiter_outreach.md          # Recruiter outreach contract
│   ├── mock_interview_evaluator.md     # Practice evaluation contract
│   ├── career_skill_roadmap.md         # Career development contract
│   └── application_follow_up.md        # Follow-up draft contract
├── jh/
│   ├── __init__.py
│   ├── mcp_tools.py                   # Tool/resource registration and routing
│   ├── workspace.py                   # Workspace boundary and resume discovery
│   ├── resume_parser.py               # PDF, DOCX, TXT extraction
│   ├── models.py                      # Canonical domain records and enums [add]
│   ├── schemas.py                     # Shared input/output validation [add]
│   ├── evidence.py                    # Resume claim provenance and grounding [add]
│   ├── source_registry.py              # Supported sources and adapter capabilities [add]
│   ├── source_policy.py                # Allowed network behavior and URL checks [add]
│   ├── sources.py                      # Source adapter facade and compatibility layer
│   ├── pipeline.py                    # Concurrent search orchestration and cache
│   ├── dedup.py                       # Exact and fuzzy cross-source deduplication
│   ├── skills.py                      # Canonical skill ontology and aliases
│   ├── scoring.py                     # Explainable 100-point job fit score
│   ├── ats.py                          # Parsing-aware resume checks and match report
│   ├── refit.py                       # Prompt execution and grounded tailoring
│   ├── autofill.py                    # Copy-ready screening-answer drafts
│   ├── tracker.py                     # Application events and next-action logic
│   ├── exporters.py                   # TXT, DOCX, PDF, and HTML output
│   ├── digest.py                      # Search and application digest compiler
│   ├── filestore.py                   # Atomic JSON persistence and locking
│   ├── db.py                           # Rebuildable SQLite query index
│   ├── config.py                      # Validated configuration and defaults
│   ├── observability.py               # Sanitized structured events [add]
│   ├── demo.py                        # Clearly separated demo fixtures
│   └── util.py                        # Shared safe text, date, URL, and HTTP helpers
├── docs/
│   ├── architecture.md
│   ├── data-policy.md
│   ├── tool-contracts.md
│   └── mcp-setup/
│       ├── claude_desktop_config.json
│       ├── cursor_mcp.json
│       ├── antigravity_mcp_config.json
│       ├── vscode_mcp.json
│       └── README.md
├── tests/
│   ├── fixtures/
│   │   ├── resumes/
│   │   ├── job_posts/
│   │   └── malformed_documents/
│   ├── test_resume_parser.py
│   ├── test_evidence_grounding.py
│   ├── test_scoring.py
│   ├── test_dedup.py
│   ├── test_sources.py
│   ├── test_tracker.py
│   ├── test_storage.py
│   ├── test_mcp_contracts.py
│   └── test_prompt_injection.py
└── .gitignore
Module ownership contracts
- workspace.py may read only configured resume locations and the JobHunter data directory. It resolves paths before access and rejects paths that escape those roots.
- resume_parser.py extracts text and structure. It does not decide whether extracted claims are true.
- models.py owns shared records for profiles, evidence, jobs, scores, applications, source outcomes, and generated artifacts.
- schemas.py validates all tool arguments and returned domain objects. It rejects malformed values, unexpected sizes, invalid enumerations, and inconsistent date ranges.
- evidence.py connects each candidate claim to its source file and location, checks draft claims, and returns unsupported claims for review.
- source_registry.py declares which sources exist, their allowed retrieval method, their supported filters, their regional endpoint, and their freshness rules.
- source_policy.py blocks unsupported network behavior, unsafe URLs, disallowed destinations, and attempts to bypass access controls.
- pipeline.py coordinates independent source adapters. It does not embed source-specific parsing or scoring rules.
- scoring.py owns the score formula. Prompt text must never override the numerical result.
- filestore.py owns durable JSON writes. db.py owns rebuildable search indexes, not the only copy of application history.
- observability.py records status, duration, counts, source IDs, warning categories, and correlation IDs. It does not record private resume bodies, secrets, or full prompt/tool payloads by default.
4. End-to-End Operational Workflow
Phase 1: Startup and workspace validation
1. The host starts mcp_server.py using the configured Python environment and stdio transport.
2. The server sends protocol messages to standard output only. Logs and diagnostic messages go to standard error.
3. config.py resolves the workspace from an explicit environment variable or a documented default. It does not silently choose an unrelated working directory.
4. workspace.py verifies directory access and creates .jobhunter/, cache/, and output/ where needed.
5. The server validates configuration, storage schema versions, and the configured source registry.
6. db.py opens the SQLite index or rebuilds it from valid authoritative state when the index is missing or invalid.
7. The server registers the current tool and resource definitions in a deterministic order.
8. A health check records startup status without exposing resume content.
Phase 2: Resume ingestion and profile trust
1. workspace.discover_resumes() scans supported configured paths for PDF, DOCX, and TXT files.
2. The scanner rejects unsupported types, oversized files, symlink escapes, and duplicate paths.
3. resume_parser.py extracts text, sections, contact fields, education, experience, projects, dates, skills, and metrics where it can do so reliably.
4. The parser stores source provenance for each extracted field, such as file path, page, section, and text span when available.
5. The parser assigns a confidence state to extracted data: verified, needs_review, or unparsed. Extraction confidence does not establish factual truth by itself.
6. evidence.py normalizes claims and builds the candidate evidence ledger.
7. JobHunter detects inconsistent dates, implausible ranges, overlapping employment, conflicting skill claims, and extraction failures.
8. The server presents a concise review list for uncertain or conflicting fields. The candidate can confirm or correct these values.
9. Only trusted or candidate-confirmed evidence becomes eligible for resume generation. Unconfirmed data remains clearly marked.
Phase 3: Job search and source retrieval
1. The host calls search_jobs with role terms, seniority, locations, work mode, compensation preferences, date range, and result limits.
2. schemas.py validates and bounds all inputs.
3. pipeline.py selects adapters whose declared capabilities match the query.
4. Each adapter retrieves jobs through a documented public endpoint, an authorized API, an explicitly permitted feed, or a user-provided source that passes the source policy.
5. The adapter applies request timeouts, rate limits, retry limits, and source-specific pagination.
6. Responses are converted to the shared job schema. The adapter keeps the original job URL, source identifier, retrieval timestamp, and available publication/update timestamps.
7. A source failure produces a source_warning with a reason category. Other successful sources can still return results.
8. The pipeline marks unavailable salary, location, remote eligibility, sponsorship, and publication date as unknown, not as confirmed negatives.
9. The pipeline records cache status and source freshness with each result.
Phase 4: Normalization, eligibility, and deduplication
1. Normalize company names, job titles, locations, remote labels, currencies, salary periods, dates, skill aliases, and URLs.
2. Preserve both the raw source value and normalized value for fields that affect ranking.
3. Apply explicit hard filters only when the candidate selected them, such as excluded locations or an incompatible work mode.
4. Treat unknown facts separately from disqualifying facts. Do not reject a job solely because the source omits a field.
5. dedup.py first matches exact source job IDs and canonical URLs, then applies normalized company/title/location matching, content fingerprints, and fuzzy similarity.
6. Keep distinct locations or genuinely different requisitions separate, even when titles match.
7. When confidence is below the merge threshold, retain both listings and mark them as possible duplicates.
8. Prefer the employer's canonical application URL when a verified direct job-board URL exists. Keep source links for traceability.
9. The final result includes merged source references, duplicate confidence, and last verification time.
Phase 5: Fit scoring and job detail analysis
1. scoring.py calculates the 100-point score from the selected resume evidence and normalized job requirements.
2. The calculation returns component scores, matched evidence, missing requirements, unknown fields, and scoring-rule version.
3. The server returns a separate data-completeness indicator so missing listing details do not masquerade as poor candidate fit.
4. get_job_details retrieves or returns the freshest available description, with the source and retrieval time.
5. ats_audit reports structural readability, section consistency, requirement coverage, evidence-backed metrics, and formatting risks.
6. gap_report separates explicit job requirements from preferred skills, transferable evidence, and requirements not supported by the current resume.
7. Each report distinguishes machine-checkable facts from model-generated advice.
8. The candidate can inspect a reasoned result before requesting tailored material.
Phase 6: Truthful document generation
1. The host calls tailor_resume or cover_letter with the target job, selected resume variant, requested archetype, length/format preferences, and output type.
2. refit.py builds an evidence bundle containing candidate-confirmed claims, selected job requirements, source references, and the requested output contract.
3. The prompt treats all resume text and job-description text as data, not as instructions.
4. The model returns a structured draft with claim/evidence associations and an honest_gaps list.
5. evidence.py checks work dates, company names, titles, degree/certification claims, skills, project ownership, metrics, and other verifiable statements.
6. Deterministic checks validate section structure, length, required fields, forbidden formatting, and export compatibility.
7. Unsupported claims are removed or rewritten to match the evidence. When the system cannot safely repair them, it marks the output needs_review and shows the affected claim.
8. JobHunter saves a new version in .jobhunter/output/ without overwriting the source resume.
9. The output manifest records the source profile, job ID, prompt version, grounding result, generation time, and export format.
Phase 7: Application tracking and next actions
1. The candidate tells JobHunter that an application was submitted or asks to update an existing record.
2. tracker.py identifies the job using the canonical job ID or asks the host to resolve ambiguity before writing.
3. track_application appends an event to the application history rather than replacing past stages.
4. The record stores the applied date, current stage, source URL, resume version used, cover-letter version, notes, and optional contact details.
5. A configurable policy calculates next_action_at from stage and event date. Default intervals are suggestions and remain editable by the candidate.
6. JobHunter does not rely on an in-process timer to execute while the MCP host is closed. It computes due actions at query time and on startup.
7. digest.py summarizes new jobs, application changes, and due actions. It never sends messages or applies to jobs.
8. Duplicate updates are idempotent. Repeating the same confirmation should not create duplicate applications or duplicate stage events.
Phase 8: Maintenance, cache refresh, and recovery
1. Cached searches expire according to source-specific TTL rules. The existing 15-minute TTL can remain the default for volatile search results.
2. Job details and application state use separate refresh and retention rules.
3. Source health records latency, success rates, retry counts, rate-limit responses, and latest successful retrieval.
4. The server removes expired cache entries but never silently deletes durable application records.
5. If SQLite is corrupt, JobHunter rebuilds it from JSON state and current resumes. It records the recovery event.
6. If authoritative JSON state is corrupt, the server preserves the damaged file, restores the latest valid backup where available, and asks the candidate to review recovery rather than overwriting it silently.
7. The user can export or delete local data through an explicit command with a preview of the affected files.
8. A scheduled digest is an optional separate operating-system task. The MCP server itself does not promise background activity after the host shuts it down.
5. The Eight Prompt Blueprints with Revised Contracts
All prompts use named inputs, explicit output structures, evidence constraints, and a defined fallback. Prompt instructions support validation; they do not replace deterministic checks in Python.
5.1 resume_tailor_6sec.md
Purpose: Produce a readable, role-specific resume that preserves the candidate's actual experience.

Required input contract:
- Selected candidate profile and evidence IDs.
- Target job title, employer, description, requirements, source URL, and retrieval date.
- Resume archetype: startup_velocity, enterprise_scale, or technical_depth.
- Length and output format.
- Formatting constraints and any candidate-selected exclusions.
Generation rules:
- Put the target role and strongest relevant, verified evidence near the top.
- Use a simple, single-column structure with conventional section headings.
- Use accomplishment bullets that state action, scope, and verified result. Use a measured X-Y-Z structure only when the source supports all parts.
- Match the employer's terminology where it accurately describes candidate experience.
- Separate directly demonstrated skills from adjacent or learning-stage skills.
- Do not add a metric, employer, job title, date, degree, certification, project, tool, or ownership claim that lacks evidence.
- Never insert target-job keywords as claims of experience when the candidate does not have that experience.
- Avoid generic filler and repeated keyword stuffing.
- Return missing requirements in honest_gaps.
Output contract:
{
  "status": "draft | needs_review",
  "resume_sections": [],
  "honest_gaps": [],
  "claim_evidence": [],
  "format_warnings": [],
  "review_required": []
}
Every substantive claim must map to one or more evidence IDs. The exporter converts approved sections into the requested document format.
5.2 cover_letter_pitch.md
Purpose: Draft a focused application letter that connects verified evidence to the specific role.

Contract:
- Target 150–240 words unless the user selects another length.
- Open with a specific and accurate link between the role and the candidate's experience.
- Use two or three relevant, verified examples where available.
- Explain adjacent experience honestly. Do not claim equivalence between technologies without describing the actual transfer.
- Refer to the employer's product or engineering problem only when the job description or an approved source supports the reference.
- Avoid fabricated familiarity, praise, metrics, or company-specific claims.
- Close with a direct, professional expression of interest.
- Return a shorter version when source evidence cannot support a full letter.
Output contract: status, letter_text, claim_evidence, unsupported_company_claims, honest_gaps, and review_required.
5.3 interview_prep_copilot.md
Purpose: Help the candidate prepare for technical, system-design, and behavioral interviews.

Contract:
- Use the job description and verified candidate evidence to select likely interview areas.
- Separate likely questions from facts about the employer. Do not present a prediction as insider knowledge.
- Produce technical questions, trade-off prompts, and evaluation criteria tied to the target role.
- Build behavioral stories only from verified candidate examples.
- Use Situation, Task, Action, Result, and Learning where evidence supports each part.
- If a relevant example is missing, ask the candidate for one or provide a clearly labeled practice scenario that is not presented as personal history.
- Include three to four useful questions the candidate can ask, based on the job description and the candidate's goals.
Output contract: role_context, technical_questions, system_design_exercises, behavioral_story_outlines, evidence_needed, questions_for_interviewer, and review_notes.
5.4 screening_question_solver.md
Purpose: Draft concise, truthful responses for application screening fields.

Contract:
- Target 60–120 words unless the form gives a different limit.
- Return plain text when the destination expects plain text.
- Answer the question directly in the first sentence.
- Use first-person ownership only when the evidence identifies what the candidate personally did.
- Use the candidate's own project and work examples. Do not invent an incident, outcome, tool, team size, or metric.
- If a truthful answer needs missing information, return a brief clarification request or a partial draft with explicit placeholders. Never guess.
- Validate character and word limits when the user supplies them.
Output contract: status, answer_text, word_count, character_count, claim_evidence, missing_inputs, and review_required.
5.5 recruiter_outreach.md
Purpose: Draft professional outreach for a recruiter, hiring manager, or technical leader.

Contract:
- Generate only the format requested: connection note, direct message, or email.
- Respect user-supplied character and word limits. The default connection-note target is under 280 characters; confirm the host's current limit before relying on it for a live platform.
- Use a verified role, company, project, or shared technical interest.
- Never claim a referral, personal relationship, prior interaction, or shared connection that the candidate did not confirm.
- Do not fabricate an expected business impact or suggest that a message has been sent.
- Return the draft for user review. Sending remains outside this server.
Output contract: channel, draft_text, length_metrics, claim_evidence, personalization_sources, and review_required.
5.6 mock_interview_evaluator.md
Purpose: Score practice answers and give specific feedback the candidate can act on.

Rubric, total 100 points:
- Technical precision: 0–25.
- Structure and clarity: 0–25.
- Evidence and result: 0–25.
- Ownership and reflection: 0–25.
Contract:
- Explain the evidence for each score. Do not infer competence from accent, identity, personality, or stylistic preferences unrelated to the role.
- Distinguish missing detail from incorrect technical content.
- Identify unsupported claims in the candidate's answer.
- Provide the smallest useful rewrite while preserving the candidate's actual experience.
- Mark scores as practice feedback, not as a prediction of a real interview outcome.
Output contract: dimension_scores, total_score, evidence_for_scores, strengths, specific_improvements, technical_corrections, suggested_rewrite, and confidence_notes.
5.7 career_skill_roadmap.md
Purpose: Convert recurring role requirements into a practical learning plan.

Contract:
- Base priorities on target-job evidence, the current profile, and candidate goals.
- Separate mandatory requirements from preferred requirements and optional interests.
- Make each phase measurable through a project, artifact, test, or explanation the candidate can show.
- Preserve the existing 30/60/90-day structure when useful, but adapt it to available time and starting skill.
- Do not claim that a plan guarantees employment or mastery.
- If the plan recommends current courses, tools, certifications, or documentation, verify their status through approved sources before naming them as current.
- Prefer one coherent project that proves several related skills over a long disconnected list of tutorials.
Output contract: baseline, priority_gaps, milestones, project_specification, validation_checks, portfolio_evidence, time_assumptions, and risks.
5.8 application_follow_up.md
Purpose: Draft a polite, contextual follow-up based on a confirmed application event.

Contract:
- Target fewer than 100 words unless the candidate requests more.
- Use the actual role, stage, date, prior contact, and interview context.
- Follow configurable timing rules. Do not treat the default interval as a guarantee that the recipient expects a message.
- Avoid claiming that the candidate has another offer, deadline, or competing process unless confirmed.
- If the history is incomplete, return a draft with placeholders or ask for the missing detail.
- Never send the message automatically.
Output contract: status, draft_text, recipient_context, timing_basis, claim_evidence, and review_required.
6. Algorithms for Grounding, Scoring, Deduplication, and Parsing
6.1 Resume parsing and evidence ledger
Represent each candidate fact as a canonical claim with a stable ID and provenance.
{
  "evidence_id": "ev_...",
  "claim_type": "skill | employment | education | project | metric | certification",
  "canonical_value": "...",
  "source_file": "resumes/backend.pdf",
  "source_location": {
    "page": 2,
    "section": "Experience",
    "span": "..."
  },
  "extraction_status": "needs_review",
  "candidate_confirmed": false,
  "first_seen_at": "...",
  "last_confirmed_at": "..."
}
Parsing flow:
1. Extract native document text before considering OCR.
2. Detect empty or nearly empty extraction, corrupted files, repeated text, broken word spacing, missing sections, and suspicious date values.
3. Normalize whitespace and Unicode without destroying meaningful punctuation, version strings, URLs, or technical names.
4. Detect common sections and preserve the original text for traceability.
5. Parse employment records into employer, title, start date, end date, and source span.
6. Parse skills using canonical aliases while preserving the spelling found in the file.
7. Keep ambiguous values in needs_review. Never turn an uncertain parse into a confirmed profile claim automatically.
8. Re-parse only changed files using a file hash. Invalidate all derived profiles when a source file changes.
Resume files with images, multi-column layouts, tables, headers/footers, text boxes, or broken spacing can parse incorrectly. Run a structural readability check and ask for review when extraction looks incomplete. Do not claim that an ATS score guarantees acceptance.
6.2 Grounding and claim verification
Use a multi-stage validation pipeline instead of relying only on the presence of numbers or skill names.

Stage A: Claim extraction
- Split the generated draft into factual claims.
- Classify each claim as employment, education, skill, project, ownership, metric, date, certification, or general phrasing.
- Ignore purely stylistic text that makes no factual claim.
Stage B: Evidence matching
- Match each claim to candidate-confirmed evidence using canonical entities, dates, skill aliases, and meaning-preserving text comparison.
- Metrics must match source values and units, or use a clearly derivable calculation with the derivation recorded.
- Do not infer a percentage, scale, team size, performance improvement, or ownership responsibility.
- Do not infer skill proficiency from a keyword appearing in a job description.
- Calculate total experience from merged employment intervals and do not double-count overlapping jobs.
- Never treat a date or number in the target job description as evidence about the candidate.
Stage C: Decision
- supported: the source evidence supports the claim.
- derived: the claim follows from a deterministic, recorded calculation.
- needs_review: the match is uncertain or depends on candidate interpretation.
- unsupported: no acceptable evidence supports the claim.
Stage D: Repair
- Remove or rewrite unsupported claims.
- Preserve adjacent experience only when phrased accurately.
- Place unresolved requirements in honest_gaps.
- Return the source and claim side by side for any remaining review.
- Block export as approved when critical factual claims remain unsupported.
Stage E: Audit
- Store claim IDs, evidence IDs, validator version, and outcome in the artifact manifest.
- Test the validator against examples where source and output use different number formats, dates, aliases, punctuation, and units.
The validator should minimize false negatives without treating every new number as a hallucination. For example, a word-count limit, current year, or section number is not a candidate achievement. Equally, a plausible-looking metric remains unsupported if no candidate evidence justifies it.
6.3 100-point job-fit score
Keep the current formula:
\[
\text{Fit Score} =
\text{Skill Match}_{40} +
\text{Title and Domain}_{25} +
\text{Seniority}_{20} +
\text{Work Mode and Compensation}_{15}
\]
Skill match, 0–40
- Extract required and preferred skills separately.
- Required skills carry weight 1.0; preferred skills carry weight 0.4 unless a versioned scoring profile specifies otherwise.
- Normalize aliases such as Postgres and PostgreSQL.
- Count only candidate-supported skills. Distinguish direct evidence from adjacent experience.
- Avoid double-counting synonyms for the same underlying skill.
- Return matched and missing requirement lists with evidence IDs.
Title and domain, 0–25
- Compare normalized titles, role families, functional domains, and key responsibilities.
- Weight core role alignment more than superficial token overlap.
- Penalize a material discipline mismatch, such as mobile development for a backend-only target, only when the job and candidate preferences support that distinction.
- Return the matching terms and the reason for any penalty.
Seniority and experience, 0–20
- Normalize seniority labels and required years.
- Merge overlapping employment intervals before calculating total experience.
- Do not interpret an unstated minimum as zero years required.
- Keep seniority title evidence separate from calculated years of experience.
- Flag missing or unclear employment dates instead of inventing a precise total.
Work mode and compensation, 0–15
- Preserve the 10-point work-mode and 5-point compensation allocation.
- Score the candidate's actual preference against verified job details.
- Convert salaries only when currency, pay period, and conversion assumptions are known. Record those assumptions and the timestamp for any exchange rate used.
- Treat undisclosed salary as unknown, not automatically below the candidate's target.
- Treat remote eligibility by country or region where the source specifies it. A generic remote label does not always mean worldwide remote.
Output requirements
- Return each component score, the total, rule version, matching evidence, missing requirements, unknown fields, and an explanation.
- Return a separate data_completeness value.
- Label the result as a heuristic ranking, never a hiring probability or guarantee.
- Keep any user-selected hard filters separate from the soft score.
6.4 Cross-source job deduplication
Use ordered matching stages:
1. Exact identity: Same source plus job ID, or same canonical application URL.
2. Canonical URL: Remove tracking parameters and normalize host/path only when doing so does not change job identity.
3. Strong composite match: Same employer, normalized title, location/remote region, and materially similar description.
4. Fuzzy candidate match: Compare title, employer, location, description fingerprint, and date. Merge only above a calibrated confidence threshold.
5. Ambiguous case: Keep both results and annotate possible_duplicate_of.
Rules:
- Do not merge different locations, requisition IDs, job levels, or language versions when those differences matter.
- Do not let a stale aggregator listing overwrite fresher official job details.
- Prefer a verified employer application URL as canonical while retaining every source reference.
- Keep first_seen_at, last_seen_at, last_verified_at, and source_published_at separate.
- Test duplicates with punctuation differences, tracking URLs, title abbreviations, remote tags, stale posts, and near-identical roles.
6.5 Source reliability and search orchestration
For each adapter:
- Use a bounded timeout, concurrency limit, page limit, and retry policy.
- Retry transient failures with exponential backoff and jitter. Do not retry permanent 4xx failures blindly.
- Honor documented rate limits and stop after access-denied, anti-bot, or CAPTCHA responses. Do not rotate fingerprints or identities to bypass a block.
- Use a circuit breaker to pause repeatedly failing sources.
- Return partial results from healthy sources and disclose failed sources.
- Cache according to source volatility and freshness. A 15-minute cache may suit active searches, but longer-lived job details need their own policy.
- Keep source adapters independently testable with saved fixtures.
6.6 ATS and export validation
The ATS audit reports measurable risks, not an unverifiable universal ATS score. Validate:
- Clear section headings and consistent chronology.
- Selectable text in PDF output.
- Standard fonts and readable text order.
- No critical contact information hidden in headers, footers, shapes, or images.
- Simple single-column output by default.
- Correct dates, links, bullet structure, and section order.
- Supported file type and generated file integrity.
- Target-job keywords only where they accurately describe the candidate.
- No duplicate bullets, empty headings, broken glyphs, or leftover placeholders.
Run an extract-after-export check. Reopen the exported file with the parser and compare its text and section order with the intended content.
7. Storage Architecture and Lifecycle
7.1 Source of truth
.jobhunter/
├── config.json
├── applications.json
├── watchlist.json
├── profiles/
│   ├── index.json
│   └── <profile-id>.json
├── cache/
│   ├── jobs.json
│   └── sources.json
├── engine.db
├── backups/
└── output/
    ├── tailored/
    ├── cover-letters/
    ├── interview-prep/
    └── reports/
- config.json stores validated preferences, active resume variant, scoring profile, source choices, and reminder intervals. It contains no API secrets.
- applications.json is the durable application ledger with stable IDs and stage-history events.
- watchlist.json stores candidate-selected target companies and supported public endpoints. It does not imply that JobHunter can monitor a source indefinitely or bypass its access controls.
- profiles/ stores normalized profile claims and references to their source files. The original resume remains the primary evidence source.
- cache/ contains disposable search and source-health data with timestamps and schema versions.
- engine.db accelerates indexed queries. It can be rebuilt and is not the sole copy of durable records.
- backups/ keeps a small, bounded rotation of valid prior state files.
- output/ stores generated artifacts and manifests. Source resumes remain unmodified.
7.2 Safe writes and consistency
- Write JSON to a temporary file in the same directory, flush it, then atomically replace the previous file.
- Serialize writes with a process/thread lock where the server may handle concurrent requests.
- Use SQLite transactions for index updates. Rebuild the index from authoritative files after an invalid schema or integrity failure.
- Add a schema_version to every durable record. Migrations must preserve a backup and either complete fully or leave the prior version intact.
- Use stable IDs and idempotency keys for job and application mutations.
- Validate each write before persistence. Do not accept arbitrary file paths from model-generated arguments.
- Keep generated files versioned. A new tailored resume creates a new artifact rather than overwriting the source or previous approved version.
7.3 Retention and privacy
- Keep job-search caches only as long as their configured TTL requires.
- Keep application history until the candidate deletes or exports it.
- Allow the candidate to delete a profile or generated artifact while preserving only the minimal record needed to maintain referential integrity, unless the candidate requests deletion of that record too.
- Do not upload candidate files to external services unless the selected workflow clearly requires it and the user has approved that service.
- Do not log resume text, complete screening answers, personal contact details, access tokens, or complete model prompts by default.
- Provide a data export and a clear local-data deletion path.
7.4 Startup recovery lifecycle
1. Load and validate config.json.
2. Validate durable JSON files and create recoverable backups where appropriate.
3. Discover source resume files and compare their hashes with cached parse records.
4. Reparse changed files only, then rebuild affected evidence records.
5. Open or rebuild engine.db.
6. Restore application and watchlist indexes from the authoritative JSON files.
7. Expire cache entries and mark stale job records.
8. Expose a health summary and proceed even if one optional source is unavailable.
9. Stop and request user action only when a required configuration or durable record cannot be recovered safely.
8. MCP Tool Surface and Host Integration
8.1 Tool capability groups
Keep existing public tool names stable unless a planned major version explicitly changes them. Organize their contracts into these groups:

Profile and resume
- Discover and list supported resume variants.
- Read the active profile summary and preferences.
- Compare resume variants against a selected job.
- Report parse confidence and fields needing review.
Job discovery
- search_jobs: search supported sources with validated filters and bounded results.
- get_job_details: return current normalized details plus source and freshness metadata.
- Search results return direct links, source identity, fit breakdown, duplicate references, and data-quality warnings.
Fit and resume quality
- ats_audit: return structural checks and role-keyword coverage.
- gap_report: separate required skills, preferred skills, transferable evidence, and unsupported claims.
- tailor_resume: create a grounded draft and review report.
- compare_resumes: compare variants using the same job snapshot and scoring version.
Application materials and preparation
- cover_letter: generate a grounded draft.
- autofill / screening-answer capability: generate copy-ready text; do not control a browser or submit a form.
- Interview preparation, mock evaluation, outreach, skill-roadmap, and follow-up tools each follow the matching prompt contract in Section 5.
Application lifecycle
- track_application: create or update a user-confirmed application event.
- List applications, stage history, and due actions through the existing tracking capabilities.
- Generate a digest on demand.
- Mutating operations return the record ID and the event created.
The current project description states that the server exposes 24 tools. Keep that public surface compatible, but ensure every registered tool belongs to a documented capability and has its own schema, side-effect level, tests, and error contract. Do not add tools merely to reach a target count.
8.2 Standard tool contract
Every tool defines:
- A short description stating exactly what it does and what it does not do.
- A typed input schema with required fields, allowed values, size limits, and defaults.
- A validated structured result, plus a readable text summary for compatible hosts.
- Clear error categories: invalid input, unavailable source, no result, parse warning, stale data, storage failure, and internal error.
- Timeout, pagination, concurrency, and result limits where applicable.
- Side-effect metadata that truthfully describes read-only or mutating behavior.
- A correlation ID for logs and follow-up diagnosis.
- An explicit versioned contract test.
Example result envelope:
{
  "status": "ok | partial | needs_review | error",
  "data": {},
  "warnings": [],
  "sources": [],
  "generated_at": "...",
  "correlation_id": "..."
}
Tool annotations help clients understand behavior but do not replace server-side authorization and validation. The server must enforce restrictions even when a model supplies malformed, hostile, or over-broad arguments.
8.3 Six passive context resources
Keep resources read-only and small enough to include safely in a host context. Use the current resource names where clients already depend on them. The resource roles should cover:
1. Candidate profile summary with evidence status, not the full contents of every resume.
2. Resume variant inventory and parse status.
3. Candidate search, location, salary, and work-mode preferences.
4. Skill ontology and alias version.
5. Application pipeline summary and next-action counts.
6. Source registry health, supported capabilities, and last-refresh metadata.
Resources never submit applications, send messages, alter settings, or expose secrets. The host should be able to request detailed resume evidence through an explicit tool call when it is needed.
8.4 STDIO and host compatibility
- Reserve stdout for MCP protocol messages. Send diagnostics through the logging system configured for stderr.
- Use a stable, tested Python environment and lock the MCP SDK to a version that passes the project's compatibility suite. Upgrade deliberately rather than depending on an unrestricted version range.
- Resolve the Python executable and project path in each host configuration. Prefer the project's virtual environment or a documented runner.
- Use ${workspaceFolder} only in hosts that support that variable. Use an explicit absolute path where the host does not resolve it.
- Pass non-secret configuration through environment variables. Keep credentials out of example JSON, repository files, logs, and error messages.
- Test each supported host configuration from a clean installation.
- Include setup troubleshooting for missing Python, invalid paths, import failures, permission errors, and protocol output polluted by stdout logging.
- Keep a compatibility smoke test for tools/list, resources/list, representative read-only calls, a mutating call, and clean shutdown.
- Use current MCP Inspector or an equivalent protocol test client when validating registration and tool schemas.
9. Security, Privacy, Compliance, and Quality Gates
9.1 Job-source access policy
- Prefer documented public career-site APIs, official ATS feeds, authorized partner APIs, or feeds whose terms permit the intended access.
- Greenhouse provides a public Job Board API for published jobs, and Lever provides a public postings API for job-board integrations. Implement these through dedicated adapters and retain the canonical posting links.
- Do not scrape logged-in pages, defeat CAPTCHAs, rotate fingerprints to evade detection, bypass paywalls, or circumvent source access limits.
- Do not use LinkedIn scraping or activity automation as a fallback. LinkedIn states that it prohibits third-party software that scrapes or automates activity on its website. If a permitted integration becomes available, implement it only within the applicable authorization and terms.
- Honor robots and rate-limit signals where relevant. Stop and surface the restriction rather than repeatedly retrying.
- Store the source URL, access method, retrieval time, and any known limitations with the result.
- Use a source adapter's allowlist and documented endpoints rather than fetching arbitrary URLs supplied by model output.
9.2 MCP and prompt-injection defenses
- Treat tool arguments, job descriptions, resume files, URLs, API responses, and generated text as untrusted input.
- Never interpret instructions found in external job listings or documents as authority to read files, call a different tool, or disclose data.
- Validate all tool inputs at runtime. Limit path access to configured roots and network access to approved destinations.
- Prevent SSRF by validating scheme, hostname, resolved destination, redirects, and private-network targets before a fetch.
- Parse required fields from job pages instead of feeding entire raw HTML pages into the model.
- Enforce access policy in Python. Do not rely on a prompt instruction to prevent unauthorized tool behavior.
- Separate reading candidate evidence from operations that write state or disclose data externally.
- Require explicit user confirmation for destructive deletion, application submission, outgoing messages, or other external side effects. This server's default workflow prepares drafts and records user-confirmed actions only.
- Review changes to tool names, descriptions, schemas, annotations, and dependencies before release.
- Do not expose a remote transport by default. Any future remote deployment needs its own authentication, authorization, transport security, and deployment review.
9.3 File-system and secret protection
- Scope reads and writes to the configured workspace. Resolve paths and symlinks before access to prevent path traversal.
- Reject unexpected document types and enforce size limits before parsing.
- Keep credentials out of config files that enter version control. Load secrets through environment variables or an appropriate secret store when an integration requires them.
- Redact tokens and personal data from exceptions.
- Use restrictive file permissions where the platform supports them.
- Keep generated documents out of public repository paths by default, and add .jobhunter/ to .gitignore.
- Never execute code embedded in a resume, job description, prompt file, or scraped content.
9.4 Privacy-by-default telemetry
Log:
- Correlation ID, tool name, outcome category, duration, source identifier, result count, retry count, and sanitized error category.
- Prompt version and validator version, without logging the entire prompt or candidate output.
- Security events such as blocked URL, path escape attempt, unsupported source access, or suspected prompt injection.
Do not log:
- Full resumes, contact details, complete application answers, access tokens, full private prompts, or full raw tool input/output by default.
9.5 Automated quality gates
Unit tests
- Resume parsing and section extraction.
- Skill aliases and skill evidence.
- Employment date merging and salary-period conversion.
- Score component boundaries and total score.
- Exact, canonical, and fuzzy deduplication.
- Atomic writes, migrations, backups, and SQLite rebuild.
- Application stage transitions, idempotency, and next-action dates.
Contract tests
- Validate every tool's input and output schema.
- Verify read-only operations do not write data.
- Verify mutating operations create the expected durable event.
- Check structured errors and partial results.
- Check deterministic tool registration order and clean stdio output.
Adversarial tests
- Job descriptions containing instructions to reveal private resume data.
- Malicious filenames and path traversal.
- Unsafe URLs, redirect chains, and private-network addresses.
- Malformed, oversized, or deeply nested responses.
- Invented metrics, unsupported credentials, contradictory dates, and false ownership claims.
- Tool requests that exceed configured page, timeout, or output limits.
End-to-end tests
- Ingest several resume formats.
- Search fixture sources and live permitted test endpoints.
- Deduplicate identical and similar job listings.
- Score the same job against several resume variants.
- Generate, ground-check, export, and re-parse a tailored resume.
- Track an application, restart the server, rebuild SQLite, and confirm the history survives.
- Run the setup instructions in each declared host configuration.
Release gates
- No unsupported resume claim can be marked approved.
- No source adapter bypasses its documented access policy.
- No private data or secret appears in standard output or default telemetry.
- No durable application record disappears during cache expiry or index rebuild.
- Every tool has a documented contract and test.
- Exported documents pass extraction and formatting checks.
- Dependency and MCP SDK upgrades pass the full protocol compatibility suite.
10. Delivery and Acceptance Criteria
Consider a workflow complete when the following end-to-end checks pass:
1. A clean install starts the server with one documented host configuration and keeps stdout protocol-safe.
2. Resume ingestion identifies supported files, reports parsing uncertainty, and builds traceable evidence.
3. A job search returns source-labeled results or explicit source warnings. It never silently reports a failed source as having no jobs.
4. Duplicate handling preserves distinct requisitions and exposes uncertain matches.
5. Every score includes its component breakdown, scoring version, evidence matches, and data-completeness information.
6. Tailored documents contain no unsupported factual claims. Any claim that needs candidate confirmation blocks approval or appears in a review list.
7. Generated output is saved as a new version and can be extracted again without losing critical content.
8. Application updates survive process restart and SQLite reconstruction without duplicate events.
9. Due actions appear when queried, without claiming that a stopped MCP process runs background timers.
10. Network access follows the source registry and policy, and security tests block unsafe paths and URLs.
11. Tool/resource contracts pass the declared host compatibility suite.
12. Documentation describes the behavior that tests verify, not behavior that the code merely intends to provide.
External implementation references
- OWASP MCP Security Cheat Sheet: input/output validation, least privilege, prompt injection, SSRF, and human approval.
- Greenhouse Job Board API: published job-board data and public job-post endpoints.
- Lever Postings API: public postings API documentation for job-board integrations.
- LinkedIn automated activity policy: restrictions on third-party scraping and automation.
- Greenhouse resume parsing guidance: formatting patterns that can interfere with resume parsing.