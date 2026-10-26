# JobHunter MCP Server

**JobHunter** is an enterprise-grade Model Context Protocol (MCP) server that provides AI coding assistants (Claude Desktop, Cursor, Antigravity, VS Code Copilot) with native tools for **resume-first job searching, 100-point explainable fit scoring, evidence-grounded non-hallucinatory tailoring, and end-to-end application tracking**.

JobHunter operates directly inside your local repository workspace: upload your resumes once as code, and AI assistants gain direct programmatic access to official employer ATS systems, a bot-immune guest LinkedIn search engine, and global feeds without login credentials or third-party tracking.

---

## Architecture & System Overview

```
                      ┌─────────────────────────────────────────┐
                      │    MCP Clients (Claude, Cursor, etc.)   │
                      └────────────────────┬────────────────────┘
                                           │ JSON-RPC 2.0 (stdio)
                                           │ stdout reserved for frames
                                           │ stderr reserved for logs
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             JobHunter FastMCP Server                             │
│                                (mcp_server.py)                                   │
├──────────────────────────────────────────────────────────────────────────────────┤
│  27 MCP Tools         │  7 Context Resources       │  8 Prompt Contracts         │
│  - Resume Management  │  jobhunter://resumes       │  - resume_tailor            │
│  - Job Discovery      │  jobhunter://resumes/{var} │  - cover_letter             │
│  - Matching & Fit     │  jobhunter://evidence/{var}│  - interview_prep           │
│  - Document Tailoring │  jobhunter://applications  │  - screening_question_solver│
│  - Mock Interviews    │  jobhunter://jobs/latest   │  - recruiter_outreach       │
│  - Source Health      │  jobhunter://config        │  - mock_interview_evaluator │
│  - Application CRM    │  jobhunter://sources       │  - career_skill_roadmap     │
│                       │                            │  - application_follow_up    │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                 Core Engines                                     │
├───────────────────────┬──────────────────────────┬───────────────────────────────┤
│ Incremental Registry  │ Normalization & Freshness│ 5-Stage Dedup & 100-Pt Score  │
│ - SHA-256 file hashes │ - Canonical postings     │ 1. Provider ID match          │
│ - Zero-redundancy sync│ - Source vs Apply URLs   │ 2. Normalized apply URL       │
│ - Multi-variant state │ - Status: active/stale   │ 3. Employer + Role key        │
│   (.jobhunter/manifest│   expired/unreachable    │ 4. Description fingerprint    │
│    .json)             │ (jh/normalization.py)    │ 5. Merge & provenance         │
│ (jh/resume_registry.py│ (jh/freshness.py)        │ 100-point explainable fit     │
│                       │                          │ (jh/dedup.py, jh/scoring.py)  │
├───────────────────────┴──────────────────────────┴───────────────────────────────┤
│                             Multi-Source Ingestion                               │
│ - Direct ATS: Greenhouse, Lever, Ashby, SmartRecruiters, Workable                 │
│ - Major Boards: Native Bot-Immune LinkedIn Scraper (curl_cffi TLS impersonation) │
│ - Aggregators: Himalayas, Jobicy, Arbeitnow, Adzuna, Remotive, Jooble, USAJobs    │
├──────────────────────────────────────────────────────────────────────────────────┤
│                             Safety & Data Privacy                                │
│ - Evidence Ledger: Multi-stage provenance verification; zero invented facts      │
│ - SSRF Prevention: Strict block on loopback, private RFC1918, cloud metadata IPs │
│ - Path Traversal Sandbox: Workspace boundary containment                        │
│ - URL Sanitization: Automatic removal of tracking tokens (utm_*, ref, etc.)      │
└──────────────────────────────────────┬───────────────────────────────────────────┘
                                       │ Local FileStore (.jobhunter/)
                                       ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ config.json  resume_manifest.json  applications.json        │
        │ cache/ (TTL) output/tailored/      output/cover-letters/    │
        │ output/reports/ (ATS audits, gap reports, interview preps)  │
        └─────────────────────────────────────────────────────────────┘
```

---

## Key Capabilities

### 1. Resume-as-Code & Incremental Registry
- Place resumes (`.pdf`, `.docx`, `.txt`, `.md`) directly in your workspace root or a `resumes/` folder.
- **Incremental SHA-256 Tracking**: JobHunter hashes resume files and persists hashes to `.jobhunter/resume_manifest.json`. Only modified or new files are parsed on startup, reducing startup latency to milliseconds.
- **Variant Support**: Manage distinct target profiles (e.g. *Full-Stack Engineer*, *Backend Distributed Systems*, *Engineering Manager*) and toggle active variants dynamically.

### 2. Multi-Stage Evidence Ledger & Zero Hallucination Guarantee
- Every parsed skill, experience bullet, numeric metric, and degree is extracted as an immutable, provenance-tracked claim linking to its source file and section.
- Generated application documents (resumes, cover letters, screening answers) pass through a 5-stage verification gate:
  - **Stage A**: Claim extraction from drafted text.
  - **Stage B**: Evidence matching against the active ledger.
  - **Stage C**: Verdict assignment (`supported`, `derived`, `needs_review`, `unsupported`).
  - **Stage D**: Actionable repair recommendations.
  - **Stage E**: Audit manifest generation.
- **Never fabricates credentials**: If a required skill or qualification is missing from your resume, JobHunter explicitly flags it as a candidate gap rather than inventing experience.

### 3. Canonical Job Normalization & Freshness
- Postings are normalized into structured models strictly separating:
  - `source_url`: Where the posting was discovered (e.g. feed or search catalog).
  - `apply_url`: The direct endpoint where the candidate submits their application.
- Standardized taxonomies for `work_mode` (`remote`, `hybrid`, `onsite`, `unspecified`), `employment_type` (`full_time`, `contract`, `part_time`, `internship`), and `seniority` (`entry`, `mid`, `senior`, `lead`, `executive`).
- Lifecycle state tracker: postings are automatically tagged as `active`, `stale` (>30 days), `expired`, or `unreachable`.

### 4. 5-Stage Duplicate Resolution
When a job appears on multiple platforms simultaneously (e.g. Greenhouse, LinkedIn, and Indeed), JobHunter avoids duplicate alerts using a 5-stage pipeline:
1. **Provider Identity**: Checks official ATS provider key and opening ID.
2. **Canonical Apply URL**: Strips tracking parameters while preserving distinct requisition query keys.
3. **Normalized Employer + Role Key**: Fuzzy company name matching and role title normalization.
4. **Description Text Fingerprint**: MinHash/token-set overlap of core job description text.
5. **Provenance Merge**: Merges all sources into a single card, prioritizing direct employer ATS apply links.

### 5. 100-Point Explainable Fit Scoring
Calculates a deterministic 100-point score across 6 weighted dimensions:
- **Core Skills Match (35 pts)**: Weighted overlap of primary and secondary technical skills.
- **Responsibilities & Accomplishments (25 pts)**: Experience bullet alignment with target role demands.
- **Seniority & Experience Depth (15 pts)**: Years of experience and level calibration.
- **Industry & Domain Context (10 pts)**: Relevant sector experience (e.g. Fintech, Healthcare).
- **Work Conditions (10 pts)**: Remote, hybrid, or on-site alignment.
- **Compensation Alignment (5 pts)**: Target salary range compatibility.
- **Separate Eligibility Gates**: Hard constraints (work authorization, mandatory certifications, location limits) are evaluated independently and are **never** blended into the fit score.

### 6. Mock Interview Evaluation Engine
- Grades candidate practice answers across 4 core dimensions (0–25 each, 100 points total):
  1. **Personal Ownership**: Verifies active ownership ("I built/designed") vs team deflection ("we did").
  2. **Quantified Evidence**: Detects concrete metrics, percentages, throughput numbers, and scale.
  3. **Technical Precision & Trade-offs**: Evaluates architectural terminology and rationale.
  4. **Structure & Clarity**: Assesses conciseness and STAR-L alignment.
- Returns a structured hiring committee verdict (`strong_hire`, `hire`, `lean_hire`, `needs_work`), specific critique, and a coached rewrite retaining only verified candidate facts.

---

## MCP Server Catalog

JobHunter exposes **27 tools**, **7 resources**, and **8 prompt contracts** over standard `stdio` transport.

### Result Envelope Standard (`schema_version: "1.0"`)
Every tool response follows this standardized schema:
```json
{
  "status": "ok | partial | needs_review | error",
  "success": true,
  "data": { ... },
  "warnings": [],
  "sources": [],
  "correlation_id": "a1b2c3d4e5f6",
  "schema_version": "1.0",
  "generated_at": "2026-10-26T17:40:00Z"
}
```

### Registered Tools (27 Total)

| Group | Tool Name | Description |
| :--- | :--- | :--- |
| **Resume Management** | `scan_resumes` | Discovers and incrementally parses all resume files in workspace. |
| | `get_resume` | Retrieves the full parsed profile JSON and skill matrix for a variant. |
| | `list_resumes` | Lists all discovered variants, skill counts, and active status. |
| | `set_active_resume` | Switches the active variant used for matching and tailoring. |
| | `parse_resume_file` | Parses an arbitrary resume file with workspace boundary validation. |
| **Job Discovery** | `search_jobs` | Unified multi-source search across direct ATS, LinkedIn, and feeds. |
| | `get_saved_jobs` | Retrieves saved jobs with pagination and status filtering. |
| | `get_job_details` | Retrieves full job description, apply URL, and metadata for a job ID. |
| | `get_recommendations`| Returns top matching jobs scored against the active resume variant. |
| **Matching & Fit** | `score_job` | Computes 100-point explainable fit score with 6-dimension breakdown. |
| | `gap_report` | Reports honest skill gaps ("Add This If True" vs "Real Gaps"). |
| | `ats_audit` | Evaluates ATS parseability, typography, layout, and keyword density. |
| **Document Tailoring** | `compare_resumes` | Compares two resume variants side-by-side against a job specification. |
| | `tailor_resume` | Generates targeted resume bullets grounded in verified evidence. |
| | `cover_letter` | Generates a 3-paragraph personalized cover letter using verified facts. |
| | `export_resume` | Exports a resume profile to TXT, DOCX, PDF, or HTML format. |
| | `solve_screening_questions` | Drafts evidence-grounded answers for ATS application screening questions. |
| **Interview & Outreach** | `interview_prep` | Generates role-specific STAR stories, technical questions, and situational prompts. |
| | `outreach_message` | Drafts high-conversion recruiter outreach messages (LinkedIn, InMail, Email). |
| | `evaluate_mock_interview` | Evaluates practice interview answers on a 100-point rubric with coaching rewrite. |
| **Sources & Operations** | `source_health` | Reports status, latency, error rates, and capabilities across all 18 sources. |
| **CRM & Settings** | `track_application` | Records a new application in the tracker pipeline with follow-up date. |
| | `list_applications` | Lists tracked applications filtered by stage (`applied`, `interview`, etc.). |
| | `update_application`| Updates application stage, notes, or next follow-up reminder. |
| | `application_stats` | Returns funnel metrics, active count, and overdue follow-up alerts. |
| | `daily_digest` | Daily summary of new jobs, overdue follow-ups, and high-leverage actions. |
| | `configure` | Reads or updates preferences and active AI provider configurations. |

### Context Resources (7 Total)

| URI | Description |
| :--- | :--- |
| `jobhunter://resumes` | Summary list of all parsed resume variants in the workspace. |
| `jobhunter://resumes/{name}` | Complete parsed JSON profile for a specific resume variant. |
| `jobhunter://evidence/{name}` | Provenance evidence ledger and verified claims for a variant. |
| `jobhunter://applications` | Full application tracking pipeline records and stage history. |
| `jobhunter://jobs/latest` | Most recent cached multi-source job search results. |
| `jobhunter://config` | Current configuration, preferences, and AI provider settings. |
| `jobhunter://sources` | Source registry health summary, access tiers, and capabilities. |

### FastMCP Prompt Contracts (8 Total)

Registered via `@mcp.prompt()` with standardized markdown templates in `prompts/`:

| Prompt Contract | Parameters | Purpose |
| :--- | :--- | :--- |
| `resume_tailor` | `job_id`, `variant_name`, `archetype` | Guides AI in tailoring a resume without hallucinating facts. |
| `cover_letter` | `job_id`, `variant_name`, `pitch_angle` | Generates personalized 3-paragraph narrative cover letter. |
| `interview_prep` | `job_id`, `variant_name`, `interview_type` | Structures technical and behavioral interview preparation. |
| `screening_question_solver` | `job_id`, `questions`, `variant_name` | Solves ATS application screening questions grounded in profile. |
| `recruiter_outreach` | `company`, `role`, `channel`, `variant_name`| Formats high-conversion recruiter outreach messages. |
| `mock_interview_evaluator` | `question`, `candidate_answer`, `role_level`, `rubric` | Grades practice interview answers across 4 core dimensions. |
| `career_skill_roadmap` | `job_id`, `variant_name` | Creates prioritized 30-60-90 day skill acquisition roadmaps. |
| `application_follow_up` | `app_id`, `channel` | Generates polite, professional post-application follow-up notes. |

---

## Data Sources & Ingestion

JobHunter categorizes and ranks sources to prioritize direct employer opportunities:

| Tier | Category | Sources | Characteristics |
| :--- | :--- | :--- | :--- |
| **Tier 1** | **Direct Employer ATS** | **Greenhouse**, **Lever**, **Ashby**, **SmartRecruiters**, **Workable** | Direct employer APIs. 100% free direct-to-company applications with zero middleman delays or candidate paywalls. |
| **Tier 1** | **Major Job Boards** | **LinkedIn** (Bot-Immune Guest Engine), **Indeed**, **ZipRecruiter**, **Bayt**, **Naukri**, **HelloWork** | Full-market coverage worldwide across tech, hybrid, remote, and onsite roles. |
| **Tier 2** | **Public Feeds & APIs** | **Himalayas**, **Jobicy**, **Arbeitnow**, **Adzuna**, **Hacker News "Who's Hiring"** | Curated developer and remote startup feeds with direct apply links. |
| **Tier 3** | **Aggregators** | **Remotive**, **Jooble**, **USAJobs** | Broad discovery feeds; validated through strict duplicate resolution. |

### Bot-Immune LinkedIn Engine
- **TLS Fingerprint Impersonation**: Uses `curl_cffi` Chrome TLS impersonation (JA3/JA4 spoofing) and asynchronous session warmup to bypass Cloudflare and LinkedIn guest bot blocks.
- **HTTP 429 Resilience**: Retains persistent TLS sessions with jittered backoff retries.
- **Step-25 Pagination**: Step-25 pagination eliminates duplicate card fetches and maximizes throughput (~10 jobs/sec).
- **Minute-Precision Timestamping**: Converts relative post times (`"18 minutes ago"`, `"2 hours ago"`) to UTC datetimes and tags roles under 2 hours old with `"just-posted"`.

---

## Security & Privacy Controls

1. **Local-Only Workspace Execution**:
   - Resumes, applications, and logs are stored exclusively on your local machine in `.jobhunter/`.
   - Zero telemetry, tracking pixels, or remote database synchronization.
2. **SSRF Protection**:
   - Outbound requests pass through strict IP validation (`jh/source_policy.py`).
   - Automatically blocks loopback (`127.0.0.1`, `::1`), private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and cloud instance metadata IP (`169.254.169.254`).
3. **Path Traversal Sandboxing**:
   - All file-access tools enforce path containment within the workspace directory using `relative_to(workspace_root)`. Any attempt to traverse (`../../etc/passwd`) is denied immediately.
4. **Tracking Parameter Sanitization**:
   - External job URLs are sanitized to strip ad-network tracking (`utm_source`, `utm_medium`, `utm_campaign`, `ref`, `trackingId`, `refId`).
5. **Secret Redaction**:
   - API keys and tokens in URLs and error messages are automatically masked before logging to `sys.stderr`.

---

## Installation & MCP Client Setup

### Prerequisites
- **Python 3.11+**
- Git

### Installation
```bash
# Clone the repository
git clone https://github.com/ErenYea9er69/jobhunter.git
cd jobhunter

# Install dependencies
pip install -r requirements.txt
```

### Running Directly
```bash
python mcp_server.py
```
*(Protocol messages stream across `stdout`; logs stream across `stderr`.)*

### Connecting to AI Assistants

#### 1. Claude Desktop
Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["C:/Users/hp/Desktop/jobhunter/mcp_server.py"],
      "env": {
        "JH_WORKSPACE": "C:/Users/hp/Desktop/jobhunter"
      }
    }
  }
}
```

#### 2. Cursor
Add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["C:/Users/hp/Desktop/jobhunter/mcp_server.py"]
    }
  }
}
```

#### 3. Antigravity IDE
Add to your workspace `mcp_config.json`:
```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["C:/Users/hp/Desktop/jobhunter/mcp_server.py"]
    }
  }
}
```

#### 4. VS Code Copilot / Windsurf / Cline
Add to `.vscode/mcp.json`:
```json
{
  "servers": {
    "jobhunter": {
      "command": "python",
      "args": ["${workspaceFolder}/mcp_server.py"]
    }
  }
}
```

---

## Workspace Layout

```text
jobhunter/
├── mcp_server.py                 # FastMCP server entry point (stdio transport)
├── pyproject.toml                # Build configuration and dependencies
├── requirements.txt              # Production dependencies (mcp[cli]>=1.0.0)
├── jh/                           # Core JobHunter package
│   ├── mcp_tools.py              # 27 tools, 7 resources, 8 prompts registration
│   ├── resume_registry.py        # Incremental SHA-256 hash manifest manager
│   ├── evidence.py               # Evidence ledger & grounding verification pipeline
│   ├── normalization.py          # Canonical job schema & WorkMode/Seniority enums
│   ├── freshness.py              # Active/stale/expired posting lifecycle
│   ├── dedup.py                  # 5-stage duplicate resolution
│   ├── scoring.py                # 100-point explainable fit scoring engine
│   ├── interview.py              # 4-dimension mock interview grading engine
│   ├── autofill.py               # ATS screening question solving engine
│   ├── filestore.py              # Local JSON document store (.jobhunter/)
│   ├── tracker.py                # Kanban application pipeline & reminders
│   ├── source_policy.py          # SSRF prevention & URL sanitizer
│   ├── source_registry.py        # 18-source capabilities and health registry
│   ├── sources/                  # Modular source adapters
│   │   ├── base.py               # BaseSourceAdapter contract
│   │   ├── linkedin_adapter.py   # Bot-immune guest scraper adapter
│   │   ├── greenhouse.py         # Direct Greenhouse ATS adapter
│   │   ├── lever.py              # Direct Lever ATS adapter
│   │   ├── ashby.py              # Direct Ashby ATS adapter
│   │   └── ...                   # Aggregators & public feeds
│   └── util.py                   # HTTP utilities, hashing, clean text helpers
├── prompts/                      # Production prompt contracts for FastMCP
│   ├── resume_tailor.md
│   ├── cover_letter.md
│   ├── interview_prep.md
│   ├── screening_question_solver.md
│   ├── recruiter_outreach.md
│   ├── mock_interview_evaluator.md
│   ├── career_skill_roadmap.md
│   └── application_follow_up.md
├── docs/                         # Technical documentation
│   ├── architecture.md           # Architectural blueprints
│   ├── data-policy.md            # Privacy and data retention policies
│   ├── tool-contracts.md         # MCP tool input/output specifications
│   └── mcp-setup/                # Client-specific configuration templates
├── tests/                        # Comprehensive test suite (115 tests)
│   ├── unit/                     # Schemas, registry, dedup, scoring, interview tests
│   ├── contracts/                # Source adapter contract inheritance tests
│   ├── integration/              # FastMCP 27 tools, 7 resources, 8 prompts tests
│   └── security/                 # SSRF prevention and path traversal tests
└── .jobhunter/                   # Local workspace runtime directory (gitignored)
    ├── resume_manifest.json      # SHA-256 variant cache
    ├── config.json               # Local user preferences
    ├── applications.json         # Active application tracker
    └── output/                   # Exported tailored resumes, cover letters, reports
```

---

## Verification & Testing

JobHunter maintains a 100% verified test suite:

```bash
# Run all 115 tests
python -m pytest tests/ -v

# Run specific test suites
python -m pytest tests/unit/ -v          # Schemas, registry, dedup, fit score
python -m pytest tests/contracts/ -v     # Source adapter contracts
python -m pytest tests/integration/ -v   # 27 tools, 7 resources, 8 prompts
python -m pytest tests/security/ -v      # SSRF prevention & path traversal
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
