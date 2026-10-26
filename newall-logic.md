1. Product Overview
JobHunter is a local-first career intelligence system that helps a candidate move from a collection of resume files to a focused job search, evidence-based application materials, interview preparation, and a trackable application pipeline.

It connects to MCP hosts such as Claude Desktop, Cursor, VS Code, Antigravity, and other compatible clients. The server exposes tools for resume management, job discovery, fit analysis, resume tailoring, interview preparation, screening-question assistance, and application tracking.

JobHunter keeps candidate files and application records on the user's machine by default. It can use a local Ollama model without sending candidate data to a cloud AI provider. Cloud providers remain optional and require an explicit configuration choice. When a cloud provider is enabled, the AI layer sends only the evidence and job context needed for the requested operation.

The system separates five kinds of information:
1. Candidate evidence: Facts extracted from resumes or entered and confirmed by the candidate.
2. Job-source facts: Requirements, dates, compensation, location rules, and links returned by job sources.
3. Derived analysis: Skill alignment, fit scores, eligibility checks, and gap reports.
4. AI-generated documents: Tailored resumes, cover letters, outreach messages, and interview material.
5. Application history: User-confirmed application stages, dates, notes, and follow-up actions.
Every generated claim must remain traceable to its source. A similarity score, keyword match, or hash does not independently prove that a claim is true.
2. Target Users and Main Workflows
User type	Main need	JobHunter workflow
Senior and staff engineers	Find roles that match real technical depth	Search direct employer ATS feeds, compare architecture and responsibility requirements, and rank roles using verified experience.
Candidates with several career tracks	Manage Backend, DevOps, Data, ML, or other resume variants	Discover resume variants, compare them against one role, select the strongest source version, and preserve every generated version.
Active applicants	Keep applications and follow-ups organized	Record applications, maintain stage history, calculate due dates, and generate a current application digest.
Career pivoters	Understand which skills transfer and which skills are missing	Separate proven skills, adjacent skills, unsupported skills, and genuine requirements gaps. Build a practical learning plan.
Privacy-conscious candidates	Keep personal career data under their control	Store files and records locally, use local AI when desired, control cloud-provider use, and export or erase local data.


Main user journey
Local workspace
      |
      v
Resume discovery and incremental parsing
      |
      v
Candidate profile + evidence ledger
      |
      v
Search intent and candidate constraints
      |
      v
Parallel job-source search
      |
      v
Normalize -> validate -> deduplicate
      |
      v
Eligibility checks -> fit score -> ranked results
      |
      +-----------------------+
      |                       |
      v                       v
Job details and gap report   Save job / track application
      |                       |
      v                       v
Compare resume variants     Application timeline
      |                       |
      v                       v
Tailor resume / cover letter Follow-up digest
      |
      v
Evidence audit -> candidate review -> export
      |
      v
Interview preparation and screening answers
3. Core Operating Principles
3.1 Candidate truth
- Never invent a skill, employer, role, qualification, date, project, result, or performance metric.
- Preserve exact candidate metrics unless the candidate provides corrected values.
- Mark unsupported statements as needs_review or omit them from generated material.
- Keep inferred skills separate from explicitly stated skills.
- Treat transferable skills as adjacent evidence, not as proof of direct experience.
- Keep original resume files unchanged.
- Save generated documents as new, versioned files.
3.2 Job-source truth
- Preserve the original source URL, source identifier, and source name.
- Preserve the source's application URL according to that source's rules.
- Track publication time, last-seen time, last-verified time, and expiry information separately.
- Label missing fields as unknown. Do not convert missing salary, location, or seniority data into a negative result.
- Mark a job as stale or unverified when the source cannot confirm that it remains open.
- Display source attribution wherever a source requires it.
3.3 Privacy by default
- Keep resumes, candidate profiles, generated documents, and application records in the local JobHunter workspace.
- Do not send candidate data to cloud AI unless the user enables a cloud provider.
- Redact contact details and unrelated personal information before constructing AI prompts whenever the task does not need them.
- Store API keys outside ordinary configuration files, using environment variables or the operating system's secret store.
- Do not log resume text, application notes, API keys, or raw AI prompts.
3.4 User control
- Searching, parsing, scoring, and drafting can run without changing the original resume.
- Saving a job, changing an application stage, updating preferences, and deleting records must use explicit tool calls.
- JobHunter drafts application answers. It does not submit applications or send messages without a separate user-authorized action.
- The user can inspect evidence, warnings, source links, and generated-document differences before using an output.
4. MCP Runtime and Server Lifecycle
4.1 Runtime
Use the standalone fastmcp package, pinned to a tested FastMCP 4 release. FastMCP 4 supports the MCP 2026-07-28 revision and retains compatibility with older protocol clients. Keep the server's primary local transport as STDIO.
- STDIO remains the default for local desktop and editor integrations.
- Write protocol messages only to stdout.
- Send application logs and diagnostics only to stderr.
- Keep Streamable HTTP as an optional deployment profile for remote access.
- Use OAuth-based authorization before exposing personal candidate data over a remote transport.
- Do not introduce the deprecated HTTP+SSE transport for new deployments.
- Keep tool names, schemas, and result envelopes stable across supported client versions.
Long-running bulk synchronization can use FastMCP's task extension when the runtime and host support it. Ordinary searches should return within bounded time, report partial source results, and support cancellation. Do not make background tasks a requirement for basic operation.
4.2 Startup lifecycle
On startup, the server performs these steps:
1. Load configuration and validate required values.
2. Resolve the workspace root and create .jobhunter/ if needed.
3. Add .jobhunter/ to .gitignore without deleting or rewriting existing ignore rules.
4. Open the local SQLite database and apply pending migrations.
5. Verify that database, backup, and export directories are writable.
6. Initialize a shared asynchronous HTTP client with strict timeout, TLS, redirect, and connection-pool settings.
7. Load the source registry and disable adapters with missing required credentials or invalid configuration.
8. Read the resume manifest and re-parse only files whose content hash changed.
9. Rebuild or update the candidate evidence index for changed resume files.
10. Register MCP tools, resources, and prompt templates in a deterministic order.
11. Start the STDIO transport.
Shutdown closes the HTTP client, releases database connections, completes or cancels supported tasks, and flushes local state. It does not modify original resume files.
4.3 Runtime result contract
Every tool returns one predictable result structure:
{
  "status": "ok | partial | needs_review | error",
  "success": true,
  "data": {},
  "warnings": [],
  "sources": [],
  "correlation_id": "12-character-id",
  "schema_version": "1.0"
}
- ok: The requested operation completed with no unresolved material issue.
- partial: Some sources or optional fields failed, but usable results remain.
- needs_review: The output contains unresolved evidence, eligibility, or data conflicts.
- error: The operation could not produce a usable result.
Tool errors include a stable error code, a safe user-facing explanation, and a retry hint when appropriate. They do not expose stack traces, secrets, or raw provider responses.
5. Revised Codebase Structure
jobhunter/
├── mcp_server.py                    # FastMCP 4 bootstrap, lifecycle, STDIO entry point
├── pyproject.toml                   # Package metadata, pinned runtime dependencies
├── uv.lock                          # Reproducible dependency lockfile
├── .env.example                     # Names of supported settings, no real secrets
├── prompts/                         # Versioned AI prompt contracts
│   ├── resume_tailor.md
│   ├── cover_letter.md
│   ├── interview_prep.md
│   ├── screening_question_solver.md
│   ├── recruiter_outreach.md
│   ├── mock_interview_evaluator.md
│   ├── career_skill_roadmap.md
│   └── application_follow_up.md
├── jh/
│   ├── mcp_tools.py                 # MCP tool, resource, and prompt registration
│   ├── models.py                    # Pydantic domain models and result contracts
│   ├── schemas.py                   # Input validation and output serialization
│   ├── config.py                    # Configuration and secret references
│   ├── workspace.py                 # Workspace boundary and resume discovery
│   ├── resume_parser.py             # PDF, DOCX, TXT and optional scanned-PDF parsing
│   ├── resume_registry.py           # Variant identity, file hashes and active profile
│   ├── evidence.py                  # Evidence ledger, provenance and claim verification
│   ├── skills.py                    # Versioned skill ontology, aliases and relationships
│   ├── search_planner.py            # Query expansion and filter planning
│   ├── source_registry.py           # Source capabilities, credentials, policies and TTLs
│   ├── source_policy.py             # Egress controls, URL validation and SSRF protection
│   ├── sources/
│   │   ├── base.py                  # Common adapter interface and source result contract
│   │   ├── linkedin_adapter.py      # Boundary to the existing LinkedIn scraper output
│   │   ├── greenhouse.py            # Greenhouse public Job Board API
│   │   ├── lever.py                 # Lever public Postings API
│   │   ├── ashby.py                 # Ashby public Job Postings API
│   │   ├── smartrecruiters.py       # SmartRecruiters public Posting API
│   │   ├── jobicy.py                # Jobicy remote jobs API
│   │   ├── himalayas.py             # Himalayas remote jobs API
│   │   ├── adzuna.py                # Adzuna API and market data
│   │   ├── usajobs.py               # USAJOBS federal jobs API
│   │   ├── remotive.py              # Optional attributed remote-jobs API
│   │   ├── jooble.py                # Optional credentialed adapter
│   │   └── workable_account.py      # Optional user-authorized Workable account
│   ├── pipeline.py                  # Concurrent source orchestration and aggregation
│   ├── normalization.py             # Canonical JobPosting construction
│   ├── dedup.py                     # Cross-source identity and duplicate resolution
│   ├── freshness.py                 # Job status checks and stale-result handling
│   ├── scoring.py                   # Eligibility, fit score and confidence breakdown
│   ├── ats.py                       # Resume structure and text-extraction audit
│   ├── refit.py                     # Tailoring workflow and evidence gate
│   ├── autofill.py                  # Screening-question answer generation
│   ├── interview.py                 # Interview preparation and answer evaluation
│   ├── tracker.py                   # Application state machine and event history
│   ├── digest.py                    # On-demand follow-up and search summaries
│   ├── exporters.py                 # TXT, Markdown, DOCX, HTML and PDF exports
│   ├── filestore.py                 # Import/export, backup rotation and safe deletion
│   ├── db.py                        # SQLite persistence, FTS5 and transactions
│   ├── observability.py             # Redacted logs, timings and correlation IDs
│   ├── util.py                      # URL, text, date, hashing and normalization helpers
│   └── demo.py                      # Offline demo data and deterministic demo flows
├── tests/
│   ├── unit/                        # Isolated model and algorithm tests
│   ├── integration/                 # Database, parser, AI and pipeline tests
│   ├── contracts/                   # External API fixtures and adapter contracts
│   ├── security/                    # SSRF, path, prompt-injection and secret tests
│   └── fixtures/                    # Synthetic resumes, job posts and provider samples
└── docs/
    ├── architecture.md
    ├── data-dictionary.md
    ├── source-policies.md
    ├── privacy-and-security.md
    ├── scoring-method.md
    └── mcp-host-setup.md
The existing LinkedIn scraper file, its current path, and its scraping behavior remain unchanged. linkedin_adapter.py is only an integration boundary for the scraper's current output. It must not replace, reimplement, or modify the existing collection process.
6. Module Responsibilities
6.1 Protocol and domain layer
mcp_server.py
Creates the FastMCP server, configures the STDIO transport, loads dependencies through the server lifecycle, and guarantees that stdout contains only MCP protocol messages. It performs no job-search, resume-parsing, or scoring logic itself.
jh/mcp_tools.py
Registers the complete tool catalog, seven read-only context resources, and eight prompt contracts. Each handler validates inputs, calls one domain workflow, and returns the standard result envelope. Read-only tools remain read-only. Mutating tools identify the state they will change.
jh/models.py
Defines typed domain objects:
- CandidateProfile
- ResumeVariant
- ResumeSection
- EvidenceClaim
- GroundingResult
- JobPosting
- SourceRecord
- EligibilityResult
- FitScore
- GapReport
- GeneratedDocument
- ApplicationRecord
- ApplicationEvent
- SourceHealth
Use immutable or frozen models for evidence snapshots and normalized source records. Use explicit schema versions for persisted records.
jh/schemas.py
Validates types, enum values, string lengths, list sizes, numeric bounds, date formats, and allowed file paths. Reject unknown or unexpected fields where the operation requires a strict schema. Serialize outputs consistently.
6.2 Resume ingestion and evidence
jh/workspace.py
Resolves the approved workspace root. Rejects path escapes and symlink escapes. Limits parsing to approved folders and supported extensions. Creates the .jobhunter/ data directory and protects it from accidental Git commits.
jh/resume_parser.py
Supports PDF, DOCX, and TXT. It extracts text, headings, dates, work history, education, skills, certifications, project descriptions, and measurable outcomes. It records extraction confidence and the exact file location supporting each claim.

For scanned PDFs, an optional local OCR fallback can run only when normal text extraction returns insufficient content. The parser reports OCR-derived fields separately and never silently treats low-confidence OCR as verified evidence. Enforce file-size, page-count, archive-expansion, and processing-time limits.
jh/resume_registry.py
Discovers resume variants and assigns stable identities using normalized file paths and content hashes. It compares each file with the previous manifest and reparses only changed files. It tracks active variant, parse status, file modification time, content hash, and last successful parse time.
jh/evidence.py
Maintains a provenance-aware evidence ledger. Every claim stores:
- Claim type and normalized value.
- Original wording from the source.
- Resume variant and source file hash.
- Page, section, paragraph, or text-span location where available.
- Extraction method and confidence.
- Evidence status: explicit, candidate_confirmed, inferred, conflicting, or unverified.
- Creation time and evidence-ledger version.
SHA-256 hashes identify and compare normalized claims. They do not establish truth by themselves. Verification checks the actual supporting text, claim meaning, dates, numbers, and source relationship.
6.3 Skill intelligence
jh/skills.py
Maintains a versioned skill taxonomy for programming languages, frameworks, cloud platforms, databases, DevOps tools, security technologies, engineering practices, and role-specific concepts.

It handles aliases such as k8s and Kubernetes, but does not assume every related term means the same capability. It supports:
- Canonical names and aliases.
- Parent-child relationships.
- Related and adjacent skills.
- Skill categories and role families.
- Candidate evidence level.
- User-defined skills and corrections.
- Taxonomy version and update date.
A candidate who lists Docker is not automatically treated as having Kubernetes production experience. Relationship mapping can identify relevant adjacent knowledge, but the output must preserve that distinction.
6.4 Job-source discovery
jh/search_planner.py
Converts a search request into normalized search intent. It can expand a role into sensible title variants and skill synonyms, but it preserves the user's constraints. It separates required filters from ranking preferences.

Examples:
- Backend Engineer can expand to Backend Developer, Software Engineer, Backend, and related titles.
- Platform Engineer can include infrastructure, cloud platform, and developer-platform terms when the candidate's target role supports those terms.
- A requested country, work mode, salary floor, seniority, or employment type remains a real constraint unless the user marks it as flexible.
jh/source_registry.py
Defines each source as configuration rather than scattered conditional code. Each record stores:
- Source identifier and display name.
- Adapter module and endpoint template.
- Supported search filters.
- Authentication type and required secret names.
- Pagination mechanism.
- Request timeout and retry policy.
- Rate limit and cache TTL.
- Supported fields and known limitations.
- Attribution text and canonical source-link policy.
- Application-link policy.
- Retention and redistribution restrictions.
- Enabled/disabled state and last health result.
jh/source_policy.py
Allows requests only to registered source hosts and explicitly configured local AI endpoints. It validates DNS results, IPv4 and IPv6 addresses, redirects, ports, and destination hosts. It blocks loopback, private, link-local, multicast, reserved, and cloud-metadata destinations for external source requests.

The HTTP client pins validated destinations where practical and validates every redirect target. It rejects DNS-rebinding attempts, unsafe URL schemes, embedded credentials, unexpected ports, and unapproved redirect chains. The configured local Ollama endpoint receives a narrow exception; arbitrary user-supplied URLs do not.
jh/sources/base.py
Defines a common adapter contract:
search(query, filters, cursor) -> SourcePage
get_details(source_job_id) -> SourceJob | NotSupported
check_status(source_job_ids) -> StatusBatch | NotSupported
health_check() -> SourceHealth
Adapters return source-native data and source metadata. They do not score candidates or make deduplication decisions.
7. Job Discovery Sources and Integration Rules
JobHunter uses a layered source strategy. Company ATS feeds provide direct employer listings. Aggregator APIs add broader discovery. The source registry controls what can run and what the server may display or retain.
7.1 Direct employer ATS sources
Source	Integration	Scope and handling
Greenhouse	Public Job Board API	Read published jobs and job details using a known company board token. Preserve the Greenhouse job URL and requisition identifiers.
Lever	Public Postings API	Retrieve paginated postings for a known company site. Do not treat the endpoint as a global full-text job-search service. Preserve the original Lever posting URL.
Ashby	Public Job Postings API	Retrieve an organization's currently published jobs. Request compensation fields when available and preserve remote, workplace, location, and application fields.
SmartRecruiters	Public Posting API	Search active postings for a known company identifier. Preserve company and posting identifiers and source URL.
Workable	User-authorized account integration	Use only when the user connects an account they are authorized to access. Keep it separate from anonymous global job discovery. The current Workable MCP integration uses OAuth and account-scoped tools.


Direct ATS APIs are generally company-scoped. The discovery layer must therefore maintain known employer board identifiers or obtain them from an approved company directory. It must not assume that each ATS offers one universal search endpoint for every employer.
7.2 Job aggregators and specialist feeds
Source	Integration	Operating rule
Jobicy	Public remote-jobs API	Use cursor pagination, the live location and industry taxonomies, and the batch status endpoint. The public feed covers listings from the last seven days. Keep Jobicy attribution and canonical URLs. Do not start automated synchronization passes more often than once per hour.
Himalayas	Public remote-jobs API	Use browse or filtered-search endpoints. A free API key provides higher limits and usage tracking. Display Himalayas as the source and use its supplied applicationLink unchanged for Apply actions. Do not pass its listings to third-party job boards or aggregators.
Adzuna	Credentialed REST API	Enable after the user supplies an app_id and app_key. Use its job-search endpoints and, where useful, salary, vacancy, category, and regional statistics.
USAJOBS	Credentialed REST API	Enable for United States federal roles. Store the API key securely and send the required Host, User-Agent, and Authorization-Key headers. Respect page-size and result limits.
Remotive	Optional public remote-jobs API	Use only with visible Remotive attribution and the original Remotive job link. Account for the 24-hour delay. Do not submit its listings to third-party job boards or aggregators.
Jooble	Optional credentialed API	Enable only when the user has a suitable API plan. The documented free plan has a lifetime quota of 500 requests per key, so it is not a default high-volume source.
RemoteOK, Indeed, and other existing sources	Existing approved integration only	Keep enabled only when a documented, authorized access route exists. Do not invent private endpoints or assume an unrestricted public API.


7.3 Protected LinkedIn component
The current LinkedIn scraping implementation is protected and must remain unchanged.

The following parts are outside the scope of this architecture revision:
- The existing scraping method and request flow.
- Existing authentication, session, and browser behavior.
- Existing navigation and extraction logic.
- Existing pacing, retry, and collection behavior.
- Existing file location, function names, and internal structure.
The new linkedin_adapter.py only maps the existing scraper's current output into the shared source-result structure. It must not replace or reimplement the scraper. No new LinkedIn scraping method is introduced by this blueprint.
7.4 Source selection and compliance
Before an adapter is enabled, its registry entry must contain the current endpoint, authentication requirements, usage limits, cache rules, attribution requirements, application-link behavior, and permitted display or retention rules.

The pipeline must preserve source restrictions at the individual job-record level. A source that requires its own application link keeps that link, even when another source has a direct employer ATS link. A source that prohibits redistribution must never feed a secondary board or an external publishing workflow.
8. Unified Job Search Pipeline
jh/pipeline.py coordinates the complete search. Every adapter returns data through the same contract, while the source-specific adapter handles its own authentication, pagination, and field mapping.
Stage 1: Plan
- Read the user's role, keyword, location, work mode, salary, seniority, employment type, and date constraints.
- Read the selected resume variant and candidate preferences.
- Generate a bounded set of title and skill variants.
- Decide which enabled sources support the requested filters.
- Exclude sources that lack credentials, have failed health checks, or cannot legally serve the requested use.
Stage 2: Fetch in parallel
- Query eligible sources concurrently with per-source timeouts.
- Apply a global concurrency limit and per-host limit.
- Use cursor or page pagination where supported.
- Apply bounded retries with exponential backoff and jitter for transient errors.
- Respect Retry-After, source rate limits, and source-specific sync restrictions.
- Open a circuit breaker after repeated failures.
- Return successful source results even when another source fails.
Stage 3: Normalize
Convert every posting into the canonical JobPosting model while retaining its original source data. Standardize dates, currencies, employment types, seniority labels, location fields, and work-mode values. Keep the source URL and apply URL as separate fields.
Stage 4: Validate and enrich
- Validate required fields and URL safety.
- Remove malformed or clearly incomplete records from the ranked result set while preserving an optional diagnostic record.
- Attach source attribution and source-specific display rules.
- Check publication and expiry dates.
- Use supported status endpoints or detail requests to verify saved or high-priority results.
- Mark status as open, closed, stale, or unknown.
Stage 5: Deduplicate
Run the duplicate-resolution stages described in Section 9. Keep all source records behind the canonical job record so the user can see where a listing appeared.
Stage 6: Check eligibility and calculate fit
Run hard-constraint checks separately from the weighted fit score. Calculate the score only from known and comparable fields. Return data completeness and candidate-evidence coverage alongside the score.
Stage 7: Rank and return
Rank eligible or potentially eligible roles by fit, freshness, and confidence. Show clear labels for unknown eligibility or stale listings. Return matched skills, evidence-backed strengths, meaningful gaps, source links, and warnings.
Stage 8: Cache and record
Cache according to the source TTL. Store the normalized job, source records, timestamps, score snapshot, and search metadata in SQLite. Never treat an old cache entry as proof that a job remains open.
9. Duplicate Resolution and Freshness
9.1 Five-stage duplicate resolution
1. Provider identity: Match the same provider and stable job or requisition ID.
2. Canonical source URL: Compare normalized source URLs while retaining the original URL and all application-routing parameters.
3. Employer and role key: Compare verified employer identity, normalized title, location, employment type, and requisition identifier.
4. Description fingerprint: Compare normalized job-description text and structured requirements. Use similarity only as supporting evidence.
5. Merge decision: Auto-merge only high-confidence duplicates. Group uncertain matches for review instead of collapsing distinct openings.
The canonical record stores every source occurrence, its source timestamp, its original job URL, and its application URL. A direct ATS link is preferred only when the source's rules permit it. Source-specific application links must never be overwritten.
9.2 Freshness states
- open: A source confirmed the role as active.
- closed: A source explicitly confirmed that the role closed.
- stale: The last confirmation is older than the source's configured freshness window.
- unknown: The source does not provide a reliable status check or the check failed.
A detail lookup can refresh a record. Before the user acts on an old saved job, JobHunter checks status when the source supports it. It never silently removes an application record because the original listing closed.
10. Candidate-to-Job Matching
10.1 Eligibility checks
Eligibility checks are separate from the fit score. They return met, not_met, or unknown for each requirement.

Typical checks include:
- Country and location eligibility.
- Remote, hybrid, or on-site requirements.
- Work authorization or visa restrictions, only when the candidate supplied the relevant information.
- Required license, certification, or legally necessary qualification.
- Employment type and availability constraints.
- Explicit mandatory experience or language requirements.
An unknown value remains unknown. The engine must not infer citizenship, visa status, or legal work authorization from a resume.
10.2 Explainable 100-point fit score
Each dimension is scored from 0 to 100, then combined using these weights:
Dimension	Weight	What it measures
Skills	35	Required and preferred skills, with direct and adjacent evidence separated.
Responsibilities and scope	25	Similarity between actual role responsibilities and proven candidate work.
Seniority and ownership	15	Role level, technical scope, decision ownership, and verified experience.
Domain and environment	10	Industry, architecture, scale, product type, and operating environment.
Work conditions	10	Location, work mode, employment type, and user preferences.
Compensation	5	Compatibility with the user's stated compensation requirements when both sides provide usable data.


Only dimensions with enough comparable information contribute to the displayed fit score. The score is normalized across the available weights. The response separately reports:
- fit_score: 0-100, based on comparable dimensions.
- job_data_completeness: how much relevant job information the source provided.
- candidate_evidence_coverage: how much of the candidate profile has supporting evidence for this comparison.
- score_confidence: high, medium, or low, based on evidence and input completeness.
- eligibility: the separate hard-constraint result.
A missing salary or unspecified seniority does not become a zero score. A candidate's inferred skill does not receive the same evidence weight as a skill demonstrated in a project or work-history claim. The score is a ranking aid, not a probability of receiving an interview.
10.3 Skill classifications
For each job requirement, return one of:
- proven: Directly supported by candidate evidence.
- candidate_confirmed: Confirmed by the candidate but not present in the current resume.
- adjacent: Related experience that may transfer but does not prove the exact skill.
- missing: The candidate has no supporting evidence for the requirement.
- unknown: The job or candidate data does not support a reliable conclusion.
11. Gap Analysis and Career Roadmaps
jh/scoring.py and the career-roadmap prompt produce a structured gap report.

Every report separates:
1. Mandatory role requirements without direct evidence.
2. Preferred requirements without direct evidence.
3. Adjacent skills that may transfer.
4. Skills that appear in the resume but lack enough context or proof.
5. Requirements that cannot be evaluated because the posting is incomplete.
Each gap includes its importance, the job-posting evidence that created it, and the candidate evidence that was checked. The system then suggests a practical 30/60/90-day or custom-duration roadmap.

A roadmap describes what the candidate should learn or build. It must not write planned work into the resume as completed experience. A project can enter the resume only after the candidate confirms that they completed it and provides accurate details.
12. Resume Quality, Tailoring and Export
12.1 ATS structure audit
jh/ats.py evaluates document structure rather than claiming to predict an employer's proprietary ATS decision.

It checks:
- Whether extracted text preserves the intended reading order.
- Whether headings and section labels are recognizable.
- Whether contact information is extractable.
- Whether dates, employers, titles, and education remain associated.
- Whether tables, columns, text boxes, icons, headers, footers, or graphics cause extraction problems.
- Whether the resume includes relevant job language supported by evidence.
- Whether fonts, spacing, page breaks, and file format create readability risks.
The audit reports specific issues and suggested corrections. It does not promise an ATS pass rate or an interview outcome.
12.2 Resume variant comparison
compare_resumes scores all discovered variants against one job using the same matching model. It identifies the best base resume and explains why. It can recommend combining verified evidence from more than one variant, but it never changes the original files.
12.3 Tailoring workflow
jh/refit.py follows this sequence:
1. Load the selected resume variant and its evidence ledger.
2. Load the normalized job posting and source restrictions.
3. Select a prompt archetype: technical depth, product impact, startup execution, enterprise scale, or another configured role profile.
4. Build a minimized evidence packet containing only relevant verified claims and their source references.
5. Generate a structured draft.
6. Extract every factual claim from the draft.
7. Match claims to the evidence ledger and check dates, metrics, job titles, tools, and responsibilities.
8. Remove unsupported statements or move them into honest_gaps and needs_review.
9. Compare the draft with the source resume and produce a change report.
10. Save the new version only after validation. Never overwrite the source resume.
Each generated document stores the source resume version, job ID, prompt version, AI provider and model ID, generation time, validation result, and document hash.
12.4 Cover letters and outreach
Cover letters use evidence-backed examples and a role-specific reason for interest. Recruiter messages follow the selected channel's current length and content limits. The system does not claim personal contact, shared history, or knowledge of a company that the candidate has not supplied or that the source does not support.
12.5 Screening-question assistance
jh/autofill.py generates concise answers from candidate evidence and explicit preferences. It distinguishes:
- Answer supported by the profile.
- Answer requires candidate confirmation.
- Answer cannot be determined.
Salary expectations use the candidate's configured range. Work authorization, sponsorship, notice period, relocation, and similar personal details must come from explicit user data. The engine does not guess them.
12.6 Export
jh/exporters.py exports TXT, Markdown, DOCX, HTML, and PDF. It preserves a clean single-column ATS-friendly template by default and offers more visual layouts only as an explicit choice.

Every export runs a text-extraction check. It compares the exported text with the approved document content and reports lost sections, reordered content, broken links, or missing characters. Generated files go into a controlled output folder and receive unique names or version identifiers.
13. AI Provider Layer
13.1 Provider options
The provider interface supports:
- Ollama for local generation.
- Anthropic.
- OpenAI.
- Google Gemini.
- DeepSeek.
- Groq.
- Mistral.
Provider model IDs are configuration values, not assumptions embedded throughout the code. The provider adapter checks model availability and supported features before starting a generation request.
13.2 Privacy modes
Local mode
- Uses the configured local Ollama endpoint.
- Keeps candidate evidence and prompts on the machine.
- Works without cloud AI credentials.
- Reports the configured local model and its availability.
Cloud mode
- Requires the user to enable a cloud provider.
- Sends only the minimum candidate evidence and job context required for the operation.
- Removes contact details and unrelated personal information unless the task needs them.
- Never sends the entire candidate workspace by default.
- Reports which provider and model handled the request.
13.3 Fallback behavior
If no AI provider is configured, JobHunter can still parse resumes, search jobs, calculate deterministic scores, manage applications, and export source content.

The deterministic fallback can perform safe formatting, section ordering, known alias normalization, and template filling. It must not pretend to perform high-quality semantic rewriting or generate unsupported claims. When an AI-dependent operation cannot be completed properly, return a clear limitation and the available non-AI alternative.
13.4 Prompt execution boundary
All job descriptions, source API responses, resume text, and user-supplied documents are untrusted data. Prompts label them as data, but XML tags alone are not treated as a security boundary.

The model receives no unnecessary tool permissions during document generation. It cannot execute instructions embedded in a job description, change source configuration, access arbitrary files, or submit applications. Output must pass typed-schema validation and the evidence audit before it becomes a saved document.
14. Application CRM and Follow-Up Flow
14.1 Application state machine
Supported stages:
saved -> preparing -> applied -> screening -> interview
      -> assessment -> offer -> accepted
      -> rejected / withdrawn / archived
The user can move a record between valid stages. Every change creates an ApplicationEvent with the previous stage, new stage, timestamp, notes, and source of the change.
14.2 Application record
Each record stores:
- Company and role.
- Canonical job ID and source references.
- Original job URL and permitted application URL.
- Resume version and cover-letter version used.
- Application date and current stage.
- Salary information, when provided.
- Interview dates, notes, and preparation links.
- Next action and due date.
- Full stage-change history.
Duplicate tracking checks use company, role, requisition ID, and canonical URL. A closed job does not delete the application record.
14.3 Follow-up reminders and daily digest
jh/digest.py generates an on-demand summary of:
- Follow-ups that are due or overdue.
- Upcoming interviews and assessments.
- Applications with no recent activity.
- Recent stage changes.
- New saved jobs and recent search results.
The MCP server runs as a local subprocess. It cannot send a reliable daily notification while its host is closed. Daily automation therefore uses an optional operating-system scheduler, such as Windows Task Scheduler or cron, to launch the digest command at a configured time. Without that scheduler, the user requests the digest through the daily_digest MCP tool.
15. Storage and Data Lifecycle
15.1 Storage model
Use SQLite as the durable local source of truth for normalized application state, candidate profile metadata, search history, saved jobs, source records, and generated-document metadata.
- Enable SQLite WAL mode for concurrent reads and reliable local writes.
- Use transactions for multi-record updates.
- Add schema migrations and a database schema version.
- Use FTS5 for local full-text search where available.
- Store original resume files outside the database and never modify them.
- Store generated documents as files and reference them from the database.
- Treat caches as disposable derived data, not authoritative records.
15.2 Backups and export
jh/filestore.py handles consistent database backups, portable JSON export, document export, and data erasure. Keep a rolling set of five verified backups by default. Verify a backup before rotating out an older one. The export contains a schema version and includes the user's candidate records, saved jobs, application history, and preferences.
15.3 Data deletion
A full deletion operation must cover:
- Database records.
- Resume-derived evidence and profile indexes.
- Search and job caches.
- Generated documents, temporary files, and exports selected for deletion.
- Backup snapshots when the user requests full erasure.
The tool first shows the scope of the deletion and requires an explicit confirmation. Do not claim legal compliance solely because export and deletion functions exist. Legal compliance depends on the complete product, its data practices, and the applicable jurisdiction.
16. Configuration
Configuration uses validated environment variables plus a local non-secret preferences record. Secrets are read from environment variables or the operating system's secret store.

Example setting names:
JH_TRANSPORT=stdio
JH_WORKSPACE_ROOT=.
JH_DATA_DIR=.jobhunter
JH_DATABASE_PATH=.jobhunter/jobhunter.sqlite3
JH_AI_PROVIDER=ollama
JH_OLLAMA_BASE_URL=http://127.0.0.1:11434
JH_OLLAMA_MODEL=<configured-local-model>
JH_ALLOW_CLOUD_AI=false
JH_SOURCE_GREENHOUSE=true
JH_SOURCE_LEVER=true
JH_SOURCE_ASHBY=true
JH_SOURCE_SMARTRECRUITERS=true
JH_SOURCE_JOBICY=true
JH_SOURCE_HIMALAYAS=true
JH_SOURCE_ADZUNA=false
JH_SOURCE_USAJOBS=false
JH_SOURCE_REMOTIVE=false
JH_SOURCE_JOOBLE=false
The example file contains variable names and safe defaults only. It must never contain real API keys, OAuth tokens, or personal data.
17. MCP Tool Catalog
The revised catalog exposes 27 tools. Tool inputs use typed schemas, bounded parameters, defaults, and clear read/write behavior.
Group 1: Resume management
Tool	Main inputs	State change	Purpose
scan_resumes	subpath, force_reparse	Yes	Discovers variants and incrementally parses changed resume files.
get_resume	variant_name	No	Returns a normalized profile, skills, work history, evidence coverage, and parse warnings.
list_resumes	None	No	Lists discovered variants, file hashes, parse state, confidence, and active variant.
set_active_resume	variant_name	Yes	Sets the default resume variant for subsequent searches and drafting.
parse_resume_file	file_path	Registry update	Parses one approved file inside the workspace boundary.


Group 2: Job discovery
Tool	Main inputs	State change	Purpose
search_jobs	query, location, country, work_mode, seniority, salary_min, currency, employment_type, sources, date_posted, variant_name, limit, cursor	Cache only	Runs the full federated search, normalization, freshness checks, deduplication, eligibility, and scoring flow.
get_saved_jobs	limit, status, sort	No	Retrieves saved and recently discovered jobs from local storage.
get_job_details	job_id, refresh	Cache refresh only	Returns normalized details, original source records, source links, and current status.
get_recommendations	min_score, eligibility, limit, variant_name	No	Returns the strongest current matches for a candidate variant.


Group 3: Matching and analysis
Tool	Main inputs	State change	Purpose
score_job	job_id, variant_name	No	Returns the weighted score, eligibility checks, data completeness, and evidence breakdown.
gap_report	job_id, variant_name	No	Separates proven, adjacent, missing, and unknown requirements.
ats_audit	variant_name, format	No	Checks document structure, parsing order, layout, and keyword evidence.


Group 4: Application documents
Tool	Main inputs	State change	Purpose
compare_resumes	job_id, variant_names	No	Compares candidate variants against a role and selects the strongest base version.
tailor_resume	job_id, variant_name, archetype, provider	New document	Creates a role-specific resume and validates every factual claim.
cover_letter	job_id, variant_name, pitch_angle, provider	New document	Writes an evidence-backed cover letter.
export_resume	document_id or variant_name, format, filename	New file	Exports an approved document and checks text extraction.
solve_screening_questions	job_id, questions, variant_name	No	Drafts honest answers and flags fields that require candidate input.


Group 5: Interview and outreach
Tool	Main inputs	State change	Purpose
interview_prep	job_id, variant_name, interview_type	No	Builds technical, system-design, and behavioral preparation from verified experience.
outreach_message	company, role, channel, variant_name	No	Drafts a channel-specific recruiter or networking message.
evaluate_mock_interview	question, candidate_answer, role_level, rubric	No	Grades practice answers and identifies missing evidence, unclear structure, and technical gaps.


Group 6: Sources and operations
Tool	Main inputs	State change	Purpose
source_health	source_names, include_history	Health cache only	Reports source availability, latency, recent failures, rate limits, and last successful fetch.


Group 7: Application CRM and settings
Tool	Main inputs	State change	Purpose
track_application	job_id or company/role/URL, status, applied_at, salary, notes	Yes	Creates a durable application record and its first timeline event.
list_applications	status_filter, due_before, company, limit	No	Lists applications and follow-up actions.
update_application	app_id, status, notes, next_action_date	Yes	Updates a record and appends a timeline event.
application_stats	date_from, date_to	No	Calculates stage counts, conversion rates, response rates, and overdue actions.
daily_digest	date, include_jobs, include_interviews	No	Produces the current follow-up and search summary on demand.
configure	key, value, action	Config only	Reads or updates validated preferences and source settings. Secrets are stored outside ordinary config.


Mutating tools return the affected record ID and a concise description of the change. Destructive operations require a separate confirmation path. No tool submits job applications or sends messages automatically.
18. MCP Context Resources
Expose these read-only resources for clients that need persistent context without invoking a tool:
Resource URI	Content
jobhunter://resumes	Inventory of resume variants, parse states, active variant, and last scan.
jobhunter://resumes/{name}	Normalized profile and verified experience for a selected variant.
jobhunter://evidence/{name}	Candidate evidence ledger with source references and confidence states.
jobhunter://applications	Current application pipeline, interview dates, and due follow-ups.
jobhunter://jobs/latest	Latest cached search results with source and freshness metadata.
jobhunter://config	Non-secret preferences, active variant, search constraints, and provider mode.
jobhunter://sources	Source registry, enabled capabilities, health state, and rate-limit status.


Resources must return only the data requested by their URI. Do not expose API keys, full raw resumes, or unrelated application notes through broad summary resources.
19. Prompt Contracts
All eight prompts are versioned and share the same evidence and privacy contract. External job postings and candidate documents are untrusted data, not instructions.
Prompt	Purpose	Required output rules
resume_tailor.md	Recruiter-ready resume tailored to one role	Produce a concise opening profile, relevant skills, and evidence-backed experience bullets. Preserve candidate metrics and titles. Put unsupported requirements into honest_gaps.
cover_letter.md	Role-specific cover letter	Use a clear opening, two evidence-based reasons for fit, and a direct close. Avoid generic claims and unsupported company details.
interview_prep.md	Role-specific interview plan	Generate technical topics, system-design questions, behavioral questions, STAR examples, and questions for the interviewer. Link examples to verified candidate projects.
screening_question_solver.md	Application form answers	Give concise, copy-ready answers. Return needs_user_input for unknown personal, legal, salary, or availability details.
recruiter_outreach.md	LinkedIn and email outreach drafts	Respect the selected channel's current length limits. Use verified role fit and avoid invented relationships or prior contact.
mock_interview_evaluator.md	Practice-answer evaluation	Grade technical correctness, depth, structure, relevance, and communication. Distinguish a weak explanation from missing experience.
career_skill_roadmap.md	Skill development roadmap	Turn verified gaps into practical milestones and projects. Do not represent planned projects as completed work.
application_follow_up.md	Follow-up message	Use the actual stage history and elapsed time. Avoid fabricated recruiter conversations or assumed commitments.


Every prompt has a version, expected input schema, output schema, prohibited claim list, and test fixtures. Prompt changes run through regression tests before release.
20. Security, Privacy and Data Protection
20.1 Network security
- Allow outbound requests only to registered provider hosts.
- Validate DNS answers and each redirect destination.
- Block private, loopback, link-local, multicast, reserved, and metadata-service addresses for external sources.
- Pin validated destination addresses where practical to reduce DNS-rebinding risk.
- Require HTTPS and normal certificate verification for internet sources.
- Apply per-source timeouts, response-size limits, redirect limits, and connection limits.
- Treat job descriptions and API fields as untrusted content.
20.2 File security
- Resolve every path against the workspace root.
- Reject traversal and symlink escapes.
- Limit file sizes, page counts, decompressed archive size, and parser execution time.
- Never execute macros, scripts, embedded links, or content from uploaded resumes.
- Store temporary extraction files in a restricted temporary directory and clean them after parsing.
20.3 AI and prompt-injection security
- Keep untrusted source content separate from system instructions.
- Do not let document-generation models invoke filesystem, network, configuration, or application-submission tools.
- Validate all AI output against typed schemas.
- Run evidence verification after generation.
- Treat XML delimiters as formatting aids, not as the sole defense against prompt injection.
20.4 Secrets and logging
- Keep API keys and OAuth tokens in environment variables or a secure local secret store.
- Redact secrets before exception reporting.
- Log tool name, duration, status, source identifiers, and correlation ID.
- Do not log candidate text, raw prompts, email addresses, phone numbers, access tokens, or private notes.
- Use stderr for local structured logs. Keep stdout reserved for the MCP transport.
20.5 Export, backup and erasure
- Provide a user-readable export of all locally stored candidate and application data.
- Provide clear deletion scopes and explicit confirmation.
- Include caches, generated files, temporary files, and backup snapshots in full-erasure logic.
- Explain that deleting local records cannot recall information already sent to an external AI provider or job source.
21. Automation and Execution Policy
Workflow	Default automation	User control
Resume discovery	Incremental scan at startup and on scan_resumes	User can force a full rescan.
Resume parsing	Automatic for changed files	User can parse a specific approved file.
Search planning	Automatic for every search_jobs call	User can override query and filters.
Multi-source fetching	Concurrent within configured limits	User can select or disable sources.
Normalization and deduplication	Automatic after fetch	Uncertain duplicate groups remain separate or are flagged.
Job freshness	Automatic on detail refresh and configured checks	User can request a fresh check.
Fit scoring and eligibility	Automatic for each search result	User can inspect each dimension and constraint.
Resume comparison	Automatic when compare_resumes is called	User selects the final base version.
Evidence audit	Automatic after AI drafting	User reviews unresolved claims.
Export verification	Automatic after export	User chooses the final format and layout.
Application-stage history	Automatic after a user-confirmed update	User controls every stage change.
Daily digest	On demand by default	Optional OS scheduler can launch it daily.
Source health	On demand and during source use	User can disable unreliable sources.


The local STDIO server does not stay alive after the MCP host exits. It must not promise scheduled notifications or continuous background synchronization unless an independent scheduler or service is installed and configured.
22. Reliability, Observability and Performance
jh/observability.py records:
- Correlation ID.
- Tool name and operation category.
- Start time, duration, and completion status.
- Source identifier and safe error code.
- Cache hit or miss.
- Number of records fetched, normalized, merged, and returned.
It does not record candidate text or raw AI prompts.

The source pipeline uses bounded concurrency, separate connection pools or host limits where needed, per-source circuit breakers, and partial-result responses. One unavailable provider must not cancel successful results from other providers.

SQLite uses indexed lookups and FTS5 for local search. Large job descriptions are stored once and referenced by job ID. Repeated searches reuse valid cache entries. A source's TTL and terms determine the cache period.
23. Test and Release Strategy
23.1 Unit tests
- Evidence extraction and claim comparison.
- Skill normalization and related-skill handling.
- Scoring with missing values and zero required skills.
- Eligibility states: met, not met, unknown.
- URL canonicalization without changing application URLs.
- Duplicate resolution with multiple locations and requisition IDs.
- Application state transitions and follow-up calculations.
- Export naming and output-schema validation.
23.2 Integration tests
- Resume parsing for PDF, DOCX, TXT, and scanned-PDF fallback.
- Incremental parsing when a resume changes or disappears.
- SQLite migrations, WAL transactions, backup restoration, and export/import.
- AI provider timeouts, invalid output, and local-only mode.
- Search pipeline behavior when a source times out or returns malformed data.
- Job freshness checks and closed-posting handling.
- MCP tool and resource registration under STDIO.
23.3 Source contract tests
Use captured, synthetic, or explicitly permitted fixtures. Verify adapter schemas, pagination, status checks, attribution, rate limits, and missing-field behavior. Keep external API contract tests separate from deterministic unit tests so provider outages do not make every local test fail.
23.4 Security tests
- IPv4 and IPv6 SSRF attempts.
- DNS rebinding and redirects to blocked networks.
- Symlink and path traversal attempts.
- Oversized and malformed PDF/DOCX inputs.
- Prompt-injection strings embedded in job descriptions.
- Secret leakage in exception paths and logs.
- Deletion coverage across database, cache, backups, and temporary files.
23.5 Release checks
A release is ready when:
- All registered tools have valid input and output schemas.
- Every advertised tool is reachable through MCP.
- Source adapters pass contract tests.
- The LinkedIn scraper's current behavior remains unchanged.
- Generated resumes pass the evidence audit.
- Exports preserve text and reading order.
- Database backup and restore tests pass.
- Logs contain no candidate PII or secrets.
- The STDIO transport keeps stdout free of non-protocol output.
24. Source Documentation
The source registry should use the providers' current official documentation as its integration contract. Re-check endpoint versions, terms, attribution, limits, and authentication before enabling or updating an adapter.
- MCP specification, 2026-07-28: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- FastMCP 4 release and compatibility notes: https://blog.gofastmcp.com/3mufbh2vcv22o
- Greenhouse Job Board API: https://docs.greenhouse.io/job-board.html
- Lever Postings API: https://github.com/lever/postings-api
- Ashby Job Postings API: https://developers.ashbyhq.com/docs/public-job-posting-api
- SmartRecruiters Posting API: https://developers.smartrecruiters.com/docs/posting-api
- Jobicy API and fair-use rules: https://github.com/Jobicy/remote-jobs-api
- Himalayas Remote Jobs API: https://himalayas.app/docs/remote-jobs-api
- Himalayas API terms: https://himalayas.app/terms
- Adzuna API overview: https://developer.adzuna.com/overview
- USAJOBS Search API: https://developer.usajobs.gov/api-reference/get-api-search
- Remotive API terms: https://remotive.com/remote-jobs/api
- Jooble REST API documentation: https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation
- Workable MCP Server: https://workable.readme.io/reference/workable-mcp-server
t.