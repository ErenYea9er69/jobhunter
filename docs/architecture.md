# JobHunter Architecture & Engineering Specification

## 1. Executive Summary & Design Principles

JobHunter is a **local-first, career workflow engine** exposed through the Model Context Protocol (MCP) using a standard `stdio` transport. It empowers candidate agents in environments such as Antigravity, Cursor, Claude Desktop, and VS Code to discover jobs, evaluate fit, tailor application materials with zero factual hallucination, practice interviews, and manage application pipelines.

### Core Principles
1. **Candidate Truth as Ground Reality**: Candidate facts (employment history, skills, metrics, degrees) originate exclusively from verified resume documents and explicit user confirmations. JobHunter never hallucinates or fabricates career claims.
2. **Deterministic Grounding & Repair**: AI-generated drafts are subjected to a 5-stage verification ledger (Extract, Match, Check, Repair, Audit) that strips unsupported claims and flags unverified requirements in an `honest_gaps` manifest.
3. **Local-First & Privacy-By-Default**: All persistent data resides locally in `.jobhunter/`. No candidate data is sent to external cloud databases, and telemetry logs contain no PII or raw resume text.
4. **Resilient Source Federation**: Multiple job sources (Greenhouse, Lever, RemoteOK, Jobicy, Himalayas, Indeed, Adzuna, Jobindex) are polled concurrently with circuit breakers, strict SSRF defenses, and rate limiting.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 MCP Host (Antigravity / Cursor / Claude)     │
└──────────────────────────────┬──────────────────────────────┘
                               │ JSON-RPC over stdio
┌──────────────────────────────▼──────────────────────────────┐
│                    mcp_server.py / jh/mcp_tools.py          │
│  - 24 Registered MCP Tools                                  │
│  - 6 Passive Read-Only Context Resources                    │
│  - Standard Tool Envelope & Request Correlation Tracing     │
└──────┬───────────────────────┬───────────────────────┬──────┘
       │                       │                       │
┌──────▼──────┐         ┌──────▼──────┐         ┌──────▼──────┐
│  Ingestion  │         │  Discovery  │         │ Application │
│  & Evidence │         │  & Scoring  │         │  Workflow   │
├─────────────┤         ├─────────────┤         ├─────────────┤
│workspace.py │         │pipeline.py  │         │refit.py     │
│resume_parser│         │sources.py   │         │autofill.py  │
│evidence.py  │         │source_reg.py│         │ats.py       │
│models.py    │         │source_policy│         │tracker.py   │
│schemas.py   │         │dedup.py     │         │exporters.py │
│             │         │scoring.py   │         │digest.py    │
└──────┬──────┘         └──────┬──────┘         └──────┬──────┘
       │                       │                       │
┌──────▼───────────────────────▼───────────────────────▼──────┐
│                      Persistence Layer                       │
│  - filestore.py: Atomic JSON I/O (.jobhunter/ + backups/)    │
│  - db.py: SQLite Index Cache (engine.db - rebuildable)      │
│  - observability.py: Redacted structured event logger       │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Module Responsibilities

| Module | Responsibility |
| :--- | :--- |
| `jh/models.py` | Pydantic v2 domain records: `EvidenceClaim`, `JobPosting`, `FitScore`, `ApplicationRecord`, `SourceOutcome`, `GroundingResult`. |
| `jh/schemas.py` | Bounded runtime input/output validators for all MCP tool arguments, preventing path escapes and malformed requests. |
| `jh/evidence.py` | 5-stage factual grounding engine: checks candidate drafts against verified evidence claims, detects unverified metrics/dates/titles, and populates `honest_gaps`. |
| `jh/source_registry.py` | Declarative registry of permitted search adapters, endpoints, capabilities, rate limits, and freshness TTL rules. |
| `jh/source_policy.py` | Network security boundary: SSRF protection, private IPv4/IPv6 CIDR rejection, loopback blocking, domain whitelisting, and scheme validation. |
| `jh/pipeline.py` | Concurrent search orchestrator with timeouts, exponential backoff, circuit breaking, and partial-results delivery. |
| `jh/dedup.py` | 5-stage cross-source deduplication: Exact ID, Canonical URL, Strong Composite Match, Fuzzy Candidate Match, Ambiguous Matching. |
| `jh/scoring.py` | Explainable 100-point fit formula: Skill Match (40), Title & Domain (25), Seniority (20), Work Mode & Compensation (15), plus data completeness indicator. |
| `jh/resume_parser.py` | Multi-format text and structure extraction (PDF, DOCX, TXT) with provenance tracking and extraction confidence status. |
| `jh/ats.py` | Parsing-aware resume auditor reporting section structure, keyword density, contact visibility, and layout risks. |
| `jh/refit.py` | Truthful document tailoring engine binding versioned prompt templates with candidate evidence and job criteria. |
| `jh/tracker.py` | Durable application lifecycle state machine tracking status stages (`saved`, `applied`, `interview`, `offer`), interview dates, and due actions. |
| `jh/filestore.py` | Thread-safe, crash-resilient atomic file store managing `.jobhunter/` JSON files, schema versions, automated backup rotation, and watchlist management. |
| `jh/db.py` | Rebuildable SQLite cache and query accelerator (`engine.db`). Authoritative state remains in JSON files. |
| `jh/observability.py` | Privacy-safe structured telemetry: logs correlation IDs, latencies, and tool outcomes while redacting PII, tokens, and resume text. |

---

## 4. End-to-End Operational Lifecycle

1. **Startup & Recovery**:
   - Host spawns `mcp_server.py` via `stdio`.
   - `filestore.py` validates directory structure and ensures `.jobhunter/`, `cache/`, `backups/`, and `output/` exist.
   - Authoritative JSON stores (`config.json`, `applications.json`, `watchlist.json`) are verified with schema version checks.
   - SQLite cache (`engine.db`) is initialized or rebuilt from JSON if corrupt.
   - Discovered resumes are scanned and parsed; evidence claims are indexed.
2. **Job Discovery**:
   - Client calls `search_jobs`.
   - `source_policy.py` validates queries and filters.
   - `pipeline.py` fans out queries to active source adapters in parallel.
   - `dedup.py` groups duplicates and selects canonical employer job board postings.
   - Results are scored using `scoring.py` and returned within the standard envelope.
3. **Tailoring & Grounding**:
   - Client calls `tailor_resume` or `generate_cover_letter`.
   - `refit.py` constructs a prompt populated with candidate-proven claims and target requirements.
   - The model draft is inspected by `evidence.py` to ensure every skill, metric, and title matches candidate evidence.
   - Unsupported statements are repaired or placed in `honest_gaps`, returning a `needs_review` status if unresolved.
   - Output is saved as a versioned artifact in `.jobhunter/output/tailored/`.
4. **Application Tracking**:
   - Client records an application event via `track_application`.
   - `tracker.py` updates stage history, schedules next-action reminders, and writes atomically to `applications.json`.
   - Next-action reminders are surfaced on demand via `daily_digest` or `list_applications`.
