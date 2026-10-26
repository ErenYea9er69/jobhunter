# JobHunter MCP Tool & Resource Contracts

## 1. Protocol Architecture & Result Envelope

JobHunter exposes **24 tools** and **6 context resources** over the Model Context Protocol (MCP) using the `stdio` transport. All tools adhere to a standardized result envelope conforming to Section 8.2 of the system architecture.

### Standard Tool Result Envelope
```json
{
  "status": "ok | partial | needs_review | error",
  "success": true,
  "data": { ... },
  "warnings": [],
  "sources": [],
  "generated_at": "2026-10-26T15:00:00Z",
  "correlation_id": "a1b2c3d4e5f6"
}
```

- **`status`**: Execution status (`ok` = complete, `partial` = some sources succeeded, `needs_review` = factual claims need candidate confirmation, `error` = failed).
- **`success`**: Backward-compatible boolean indicator (`true` if `ok` or `partial`).
- **`data`**: Payload containing tool-specific structured entities.
- **`warnings`**: Bounded list of non-fatal operational, source, or formatting warnings.
- **`sources`**: List of source adapters polled or evidence IDs cited.
- **`generated_at`**: UTC ISO-8601 timestamp.
- **`correlation_id`**: 12-character trace ID linking stderr diagnostics to this operation.

---

## 2. Capability Groups & Tool Catalog (24 Tools)

### Group 1: Profile & Resume Discovery (5 Tools)
| Tool | Description | Parameters | Side Effect |
| :--- | :--- | :--- | :--- |
| `scan_resumes` | Scans workspace root and subdirectories for PDF, DOCX, and TXT resumes, extracts profile claims, and updates the local profile registry. | `subpath: str = ""` | Mutating (profiles) |
| `get_resume` | Retrieves parsed profile data, skills, experience, and evidence counts for a specific variant or active resume. | `variant_name: str = ""` | Read-only |
| `list_resumes` | Lists all discovered resume files in the repository with parsing status and active indicator. | None | Read-only |
| `set_active_resume` | Sets the default active resume variant for searches, scoring, and tailoring. | `variant_name: str` | Mutating (config) |
| `parse_resume_file` | Parses an explicit resume file path, returning extracted sections, skills, and extraction confidence. | `file_path: str` | Read-only |

### Group 2: Job Search & Discovery (4 Tools)
| Tool | Description | Parameters | Side Effect |
| :--- | :--- | :--- | :--- |
| `search_jobs` | Concurrently searches permitted job sources (Greenhouse, Lever, RemoteOK, Jobicy, Himalayas, Indeed, Adzuna). Deduplicates listings and scores match. | `query: str`, `location: str = ""`, `work_mode: str = ""`, `sources: str = ""`, `limit: int = 15` | Read-only / Cache |
| `get_saved_jobs` | Retrieves recent search results cached in the local store. | `limit: int = 20` | Read-only |
| `get_job_details` | Retrieves full job posting details, requirements, source metadata, and verified application URL. | `job_id: str` | Read-only |
| `get_recommendations` | Recommends highest-scoring jobs based on active profile skills and preferences. | `min_score: int = 70`, `limit: int = 10` | Read-only |

### Group 3: Fit Scoring & ATS Audits (3 Tools)
| Tool | Description | Parameters | Side Effect |
| :--- | :--- | :--- | :--- |
| `score_job` | Computes explainable 100-point fit score (Skill Match 40, Title & Domain 25, Seniority 20, Work Mode & Comp 15) plus data completeness. | `job_id: str`, `variant_name: str = ""` | Read-only |
| `gap_report` | Detailed gap analysis contrasting candidate evidence against job requirements, isolating missing vs adjacent competencies. | `job_id: str`, `variant_name: str = ""` | Read-only |
| `ats_audit` | Structural parser-compatibility audit evaluating heading hierarchy, fonts, selectable text, and keyword density. | `variant_name: str = ""` | Read-only |

### Group 4: Truthful Document Tailoring (4 Tools)
| Tool | Description | Parameters | Side Effect |
| :--- | :--- | :--- | :--- |
| `compare_resumes` | Compares all resume variants against a target job to recommend the highest-scoring base variant. | `job_id: str` | Read-only |
| `tailor_resume` | Generates a 6-second recruiter hook, highlights matching evidence, and isolates unverified requirements in `honest_gaps`. | `job_id: str`, `variant_name: str = ""`, `archetype: str = "startup_velocity"` | Mutating (output) |
| `cover_letter` | Generates an evidence-grounded, punchy 3-paragraph cover letter adhering to the candidate's verified background. | `job_id: str`, `variant_name: str = ""`, `pitch_angle: str = "direct_impact"` | Mutating (output) |
| `export_resume` | Exports a resume profile or tailored draft to TXT, DOCX, PDF, or HTML format. | `variant_name: str = ""`, `format: str = "txt"`, `filename: str = ""` | Mutating (output) |

### Group 5: Interview & Preparation Copilots (3 Tools)
| Tool | Description | Parameters | Side Effect |
| :--- | :--- | :--- | :--- |
| `interview_prep` | Produces role-specific technical deep-dives, system architecture exercises, and STAR behavioral story frameworks. | `job_id: str`, `variant_name: str = ""` | Read-only |
| `outreach_message` | Drafts concise, professional networking and recruiter outreach messages tailored to target company and tech stack. | `company: str`, `role: str`, `channel: str = "linkedin_connect"` | Read-only |
| `source_health` | Reports operational health, latency, failure counts, and registry capabilities for all configured job sources. | None | Read-only |

### Group 6: Application Tracking & Administration (5 Tools)
| Tool | Description | Parameters | Side Effect |
| :--- | :--- | :--- | :--- |
| `track_application` | Records a candidate-confirmed job application event in `applications.json` with stage history and next action date. | `company: str`, `role: str`, `url: str = ""`, `status: str = "applied"`, `salary: str = ""` | Mutating (durable) |
| `list_applications` | Lists all tracked applications with stage, notes, and filter by status. | `status_filter: str = ""` | Read-only |
| `update_application` | Updates application stage (`applied`, `screen`, `interview`, `offer`, `rejected`), notes, or follow-up date. | `app_id: str`, `status: str = ""`, `notes: str = ""`, `next_action_days: int = 5` | Mutating (durable) |
| `application_stats` | Aggregates application funnel metrics, response rate, active interviews, and upcoming due follow-ups. | None | Read-only |
| `configure` | Reads or updates user preferences (salary floor, remote preference, location, target title, AI models). | `key: str = ""`, `value: str = ""` | Read-only / Mutating |

---

## 3. Passive Context Resources (6 Resources)

Passive resources provide read-only context to the host LLM without triggering side effects or external network requests.

| URI | Role & Description |
| :--- | :--- |
| `jobhunter://resumes` | JSON inventory of all discovered resume files in the workspace with parse status and active variant indicator. |
| `jobhunter://resumes/{name}` | Normalized profile claims, skills, experience, and contact metadata for a specific named variant. |
| `jobhunter://applications` | Active application pipeline summary with stage breakdown and due follow-up tasks. |
| `jobhunter://jobs/latest` | Most recent search results cached in local storage. |
| `jobhunter://config` | Candidate search preferences, work-mode constraints, and active resume selection. |
| `jobhunter://sources` | Source registry operational status, supported filters, and rate-limit capabilities. |

---

## 4. Error Codes & Recovery Semantics

When a tool operation cannot complete successfully, the envelope returns `status: "error"` with an explanation in `warnings` or `data.error`:

- **`invalid_input`**: Argument schema validation failure (e.g., negative limits, disallowed formats, missing required IDs).
- **`source_unavailable`**: Network failure or rate limit exceeded on an external job board. Other sources continue.
- **`no_results`**: Valid query returned zero matches across all consulted sources.
- **`needs_review`**: Tailoring or grounding detected unverified claims; requires candidate confirmation before approval.
- **`storage_failure`**: File system read/write error; handled with atomic rollback to prior backup.
