# JobHunter MCP Server — Architecture & Implementation Plan

## 1. What This Is

Convert JobHunter from a desktop app (pywebview + local HTTP server + SQLite) into an **MCP (Model Context Protocol) server** that runs inside AI coding assistants — Antigravity, Cursor, VS Code Copilot, Claude Desktop, Windsurf, Cline, etc.

The MCP server exposes all of JobHunter's capabilities as **tools** (actions the AI can invoke) and **resources** (data the AI can read). The user interacts through the AI assistant's chat. Results come back as structured JSON that the AI interprets and presents.

**The desktop app stays untouched.** The MCP server is a new, parallel entry point — `mcp_server.py` — alongside the existing `server.py` and `desktop.py`.

---

## 2. Approaches Considered

### A — Refactor all `jh/` modules to remove SQLite, use pure filesystem
- **Cost:** Enormous. Every module imports `db`. The query engine in `db.query_stored_jobs()` does complex SQL with 30 filter dimensions. Rewriting this as filesystem operations would be 2000+ lines of new code and break every existing module.
- **Risk:** Breaks the desktop app. Loses the query performance that makes filtering fast.
- **Verdict:** Rejected. Too destructive.

### B — In-memory only, no persistence
- **Cost:** Low.
- **Risk:** Loses all state between sessions. Can't track applications. Can't cache job searches. Every conversation starts from zero.
- **Verdict:** Rejected. Unusable for real job hunting.

### C — Filesystem resumes + ephemeral SQLite engine ← CHOSEN
- **Concept:** Resumes live as actual files (PDF/DOCX/TXT) in the workspace. On MCP server startup, the server scans the workspace, parses resume files, and populates an ephemeral SQLite database (in `.jobhunter/engine.db`). The entire existing `jh/` engine runs unchanged against this SQLite. Persistent user state (applications, settings, tailored outputs) lives as JSON files in `.jobhunter/`, loaded into SQLite on startup and flushed back to JSON on writes.
- **Cost:** Moderate. New MCP layer + workspace scanner + JSON persistence adapter. Zero changes to core engine modules.
- **Risk:** Low. The engine is battle-tested. We're just changing the front door and the back store.
- **Verdict:** Best path. Full engine power, filesystem-first UX, no rewrites.

**Why C wins:** The user gets what they asked for — resumes in the repo, no opaque database. Under the hood, the engine uses an ephemeral SQLite because the 30-dimension filter query, the scoring pipeline, and the caching layer all depend on SQL. The SQLite is an implementation detail that the user never touches. If the `.jobhunter/` directory is deleted, the server rebuilds it from the resume files on next startup.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────┐
│              AI Assistant (Host)                     │
│  Antigravity / Cursor / Claude / VS Code / Cline    │
│                                                      │
│  User: "Find remote Python jobs that match my resume"│
└──────────────────────┬──────────────────────────────┘
                       │ stdio (JSON-RPC)
                       ▼
┌─────────────────────────────────────────────────────┐
│              mcp_server.py                           │
│  MCPServer("JobHunter") + stdio transport            │
│                                                      │
│  @mcp.tool()  ← 18 tools (search, score, tailor...) │
│  @mcp.resource() ← 5 resources (resumes, jobs...)   │
└──────────────────────┬──────────────────────────────┘
                       │ calls
                       ▼
┌─────────────────────────────────────────────────────┐
│              jh/ engine (UNCHANGED)                  │
│  pipeline.py │ scoring.py │ refit.py │ sources.py   │
│  tracker.py  │ ats.py     │ resume_parser.py        │
│  skills.py   │ exporters.py │ autofill.py           │
│  db.py (ephemeral SQLite, populated from files)      │
└──────────────────────┬──────────────────────────────┘
                       │ reads/writes
                       ▼
┌─────────────────────────────────────────────────────┐
│              Workspace Filesystem                    │
│                                                      │
│  resume.pdf    ← user's resume files (source of     │
│  cv.docx         truth, scanned and parsed)          │
│  resumes/                                            │
│    backend.pdf                                       │
│    fullstack.pdf                                     │
│                                                      │
│  .jobhunter/   ← managed by MCP server               │
│    config.json          (user preferences)            │
│    applications.json    (tracked applications)        │
│    cache/                                            │
│      jobs.json          (cached search results)      │
│      sources.json       (source health)              │
│    output/                                           │
│      tailored/          (generated tailored resumes) │
│      cover-letters/     (generated cover letters)    │
│      reports/           (gap reports, ATS audits)    │
│    engine.db            (ephemeral, rebuilt on start) │
└─────────────────────────────────────────────────────┘
```

---

## 4. Data Storage Design (Replacing SQLite for User)

### Source of Truth: Filesystem

| Data | Location | Format | Lifecycle |
|------|----------|--------|-----------|
| Resume profiles | `*.pdf`, `*.docx`, `*.txt` in workspace root or `resumes/` | Binary/text files | User manages directly |
| Active profile selection | `.jobhunter/config.json` → `active_resume` | JSON | Auto-updated |
| User settings | `.jobhunter/config.json` | JSON | User or MCP editable |
| Applications tracked | `.jobhunter/applications.json` | JSON array | Append-on-apply, editable |
| Watchlist | `.jobhunter/watchlist.json` | JSON array | User or MCP editable |
| Cached job search results | `.jobhunter/cache/jobs.json` | JSON | Auto-cached, TTL-based |
| Source health | `.jobhunter/cache/sources.json` | JSON | Auto-updated per search |
| Tailored resumes | `.jobhunter/output/tailored/<company>-<role>.json` | JSON (profile format) | Generated on demand |
| Cover letters | `.jobhunter/output/cover-letters/<company>-<role>.txt` | Plain text | Generated on demand |
| Gap reports | `.jobhunter/output/reports/<company>-<role>-gap.json` | JSON | Generated on demand |
| ATS audits | `.jobhunter/output/reports/<company>-<role>-ats.json` | JSON | Generated on demand |
| Interview prep | `.jobhunter/output/reports/<company>-<role>-prep.json` | JSON | Generated on demand |
| Engine database | `.jobhunter/engine.db` | SQLite | Ephemeral, rebuilt on start |

### Gitignore recommendation

The MCP server will create a `.jobhunter/.gitignore` that ignores `engine.db` and `cache/` but tracks `config.json`, `applications.json`, and `output/`. Users can override this.

### Resume Discovery Rules

The workspace scanner looks for resume files in this priority order:
1. `resumes/` or `resume/` or `cv/` directory (any depth)
2. Files matching `*resume*`, `*cv*`, `*curriculum*` in the workspace root
3. Any `.pdf`, `.docx`, `.txt` in the root (with a content heuristic to filter non-resume files)

Each discovered file becomes a **resume variant** (like the existing multi-profile system). The filename becomes the variant name (e.g., `backend-engineer.pdf` → "Backend Engineer").

---

## 5. MCP Tools Design

### 5.1 Resume Tools

| Tool | Description | Key Parameters | Returns |
|------|-------------|----------------|---------|
| `scan_resumes` | Scan workspace for resume files, parse and load them | `path?` (subdir to scan) | List of found resumes with parse status |
| `get_resume` | Get a parsed resume profile | `name?` (variant name, defaults to active) | Full profile JSON |
| `list_resumes` | List all available resume variants | — | Names, paths, skill counts, last modified |
| `set_active_resume` | Set which resume variant is active for matching | `name` | Confirmation |
| `parse_resume_file` | Parse a specific file into a profile | `path` | Parsed profile JSON |

### 5.2 Job Search Tools

| Tool | Description | Key Parameters | Returns |
|------|-------------|----------------|---------|
| `search_jobs` | Search across all job sources | `query`, `location?`, `work_mode?`, `min_score?` | Jobs list with scores |
| `get_saved_jobs` | Query previously found jobs with filters | `category?`, `seniority?`, `work_mode?`, `min_score?`, `days?`, `sort?` | Filtered jobs list |
| `get_job_details` | Enrich and score a specific job | `job_title`, `company`, `url?`, `description?` | Detailed job with full scoring breakdown |
| `get_recommendations` | Get AI-recommended jobs for the active resume | `limit?` | Ranked recommendations with insights |

### 5.3 Scoring & Analysis Tools

| Tool | Description | Key Parameters | Returns |
|------|-------------|----------------|---------|
| `score_job` | Score a job against a resume | `job` (title+description), `resume_name?` | Score breakdown (skill overlap, title alignment, seniority, etc.) |
| `gap_report` | Generate skill gap analysis | `job` (title+description), `resume_name?` | Missing skills, recommendations, upskilling plan |
| `ats_audit` | ATS readiness check for resume vs job | `job` (title+description), `resume_name?` | ATS score, checklist, keyword coverage |
| `compare_resumes` | Compare all variants against a specific job | `job` (title+description) | Ranked variants with scores |

### 5.4 Tailoring & Generation Tools

| Tool | Description | Key Parameters | Returns |
|------|-------------|----------------|---------|
| `tailor_resume` | Generate a tailored resume for a job | `job` (title+company+description), `archetype?`, `resume_name?` | Tailored resume JSON + ATS before/after |
| `cover_letter` | Generate a cover letter | `job`, `tone?`, `angle?`, `resume_name?` | Cover letter text + pitch structure |
| `interview_prep` | Generate interview questions & prep | `job`, `resume_name?` | Questions by category + suggested answers |
| `outreach_message` | Generate recruiter outreach messages | `job`, `message_type?`, `resume_name?` | LinkedIn/email messages |

### 5.5 Application Tracking Tools

| Tool | Description | Key Parameters | Returns |
|------|-------------|----------------|---------|
| `track_application` | Record a job application | `company`, `title`, `status`, `url?`, `notes?` | Application record |
| `list_applications` | List all tracked applications | `status?` | Applications with history |
| `update_application` | Update application status | `id`, `status`, `notes?` | Updated record |
| `application_stats` | Get funnel statistics | — | Applied/interview/offer/rejected counts |

### 5.6 Utility Tools

| Tool | Description | Key Parameters | Returns |
|------|-------------|----------------|---------|
| `export_resume` | Export a resume to txt/docx/pdf | `format`, `resume_name?` | File path or content |
| `source_health` | Check status of all job sources | — | Source availability report |
| `configure` | Get or set JobHunter settings | `key?`, `value?` | Current settings |

### Total: 22 tools

---

## 6. MCP Resources Design

Resources provide passive data that the AI can read as context (like GET endpoints).

| Resource URI | Description |
|-------------|-------------|
| `jobhunter://resumes` | List of all parsed resume variants |
| `jobhunter://resumes/{name}` | Full parsed profile for a variant |
| `jobhunter://applications` | All tracked applications |
| `jobhunter://jobs/latest` | Most recent search results (cached) |
| `jobhunter://config` | Current settings and AI provider status |
| `jobhunter://sources` | Source health and availability |

---

## 7. File Structure

### New Files

```
mcp_server.py                    # MCP entry point (stdio transport)
jh/mcp_tools.py                  # All @mcp.tool() and @mcp.resource() definitions
jh/workspace.py                  # Workspace scanner: find resumes, manage .jobhunter/
jh/filestore.py                  # JSON file persistence adapter
tests/test_mcp_server.py         # MCP tool unit tests
tests/test_workspace.py          # Workspace scanner tests
tests/test_filestore.py          # Filestore adapter tests
```

### Modified Files

```
jh/config.py                     # Add MCP-mode config: workspace path, .jobhunter/ paths
requirements-mcp.txt             # New: mcp[cli] dependency (separate from zero-dep core)
pyproject.toml                   # New: proper Python packaging with [mcp] optional extra
.gitignore                       # Add .jobhunter/engine.db, .jobhunter/cache/
```

### Untouched (Existing Engine)

```
jh/pipeline.py                   # Search orchestration — works as-is
jh/scoring.py                    # Match scoring — works as-is
jh/refit.py                      # Resume tailoring — works as-is
jh/sources.py                    # Job sources — works as-is
jh/db.py                         # SQLite layer — works as-is (fed from filesystem)
jh/tracker.py                    # Application tracking — works as-is
jh/ats.py                        # ATS audit — works as-is
jh/resume_parser.py              # Resume parsing — works as-is
jh/skills.py                     # Skill ontology — works as-is
jh/exporters.py                  # Resume export — works as-is
jh/autofill.py                   # Autofill engine — works as-is
jh/digest.py                     # Digest — works as-is
jh/util.py                       # Utilities — works as-is
desktop.py                       # Desktop app — untouched
server.py                        # HTTP server entry — untouched
jh/httpd.py                      # HTTP routes — untouched
```

---

## 8. Implementation Tasks

### Phase 1: Foundation (workspace scanner + filestore)

**Task 1.1: Create `jh/workspace.py` — Workspace Scanner**

Responsibilities:
- `discover_resumes(workspace_path) → list[dict]` — find resume files using discovery rules from §4
- `ensure_jobhunter_dir(workspace_path) → Path` — create `.jobhunter/` structure
- `detect_workspace() → Path` — determine workspace root (from env var, cwd, or MCP init)
- `parse_resume_variant(file_path) → dict` — call `resume_parser.extract_text()` + `resume_parser.parse_resume()`, return profile dict with `_source_file` and `_variant_name` metadata

Test: `test_workspace.py`
- Given a temp dir with `resume.pdf` and `resumes/backend.docx`, `discover_resumes()` returns both
- Given a temp dir with no resume files, returns empty list
- `ensure_jobhunter_dir()` creates the full directory tree

**Task 1.2: Create `jh/filestore.py` — JSON File Persistence**

Responsibilities:
- `FileStore(jobhunter_dir)` — manages all JSON files in `.jobhunter/`
- `load_applications() → list[dict]` / `save_application(app)` — read/write `applications.json`
- `load_watchlist() → list[dict]` / `save_watch(item)` — read/write `watchlist.json`
- `load_config() → dict` / `save_config(key, value)` — read/write `config.json`
- `cache_jobs(jobs, query_key)` / `get_cached_jobs(query_key, max_age)` — TTL-based job cache
- `save_output(category, filename, data)` — write to `output/tailored/`, `output/cover-letters/`, etc.
- Atomic writes (write to `.tmp` then rename) to prevent corruption
- Thread-safe via `threading.Lock`

Test: `test_filestore.py`
- Round-trip: save application → load → matches
- Cache TTL: expired cache returns None
- Atomic write: concurrent writes don't corrupt

**Task 1.3: Update `jh/config.py` — MCP mode configuration**

Add:
- `MCP_MODE = os.environ.get("JH_MCP_MODE", "0") == "1"` — flag to indicate MCP mode
- `WORKSPACE_DIR = os.environ.get("JH_WORKSPACE", "")` — workspace root
- `JOBHUNTER_DIR` — computed as `WORKSPACE_DIR/.jobhunter/`

### Phase 2: MCP Server Core

**Task 2.1: Create `mcp_server.py` — Entry Point**

Startup sequence:
1. Detect workspace directory (from env or cwd)
2. Initialize `.jobhunter/` directory structure
3. Scan workspace for resume files
4. Parse all found resumes
5. Initialize ephemeral SQLite (`engine.db`) via `db.init_db()`
6. Populate SQLite with parsed profiles via `db.save_profile()`
7. Load cached jobs from `.jobhunter/cache/jobs.json` into SQLite
8. Load applications from `.jobhunter/applications.json` into SQLite
9. Start MCP server on stdio transport

Test: `test_mcp_server.py`
- Server starts without error in a temp workspace with one resume file
- Startup populates the engine database with parsed profiles

**Task 2.2: Create `jh/mcp_tools.py` — Tool & Resource Definitions**

All 22 tools + 6 resources from §5 and §6. Each tool is a thin wrapper:
1. Resolve the active resume (from `filestore.config` or parameter)
2. Call the existing `jh/` engine function
3. If the tool produces persistent output (tailored resume, cover letter), save to `.jobhunter/output/` via filestore
4. If the tool modifies state (track application, update settings), flush to JSON via filestore
5. Return structured JSON result

Split into logical sections within the file:
- Resume tools (~80 lines)
- Search tools (~100 lines)
- Scoring tools (~80 lines)
- Tailoring tools (~120 lines)
- Application tracking tools (~80 lines)
- Utility tools (~60 lines)
- Resources (~60 lines)

### Phase 3: Packaging & Configuration

**Task 3.1: Create `pyproject.toml`**

Proper Python packaging so the MCP server can be installed and discovered.

**Task 3.2: Create `requirements-mcp.txt`**

Separate from the zero-dep core. The desktop app still has no dependencies.

**Task 3.3: Create MCP host configuration examples**

Create `docs/mcp-setup/` with configuration snippets for each host:

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["/path/to/jobhunter/mcp_server.py"],
      "env": {
        "JH_WORKSPACE": "/path/to/my-job-search-repo"
      }
    }
  }
}
```

**Cursor** (`.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["/path/to/jobhunter/mcp_server.py"]
    }
  }
}
```

**Antigravity** (`.gemini/config/mcp_config.json`):
```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["/path/to/jobhunter/mcp_server.py"]
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`):
```json
{
  "servers": {
    "jobhunter": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/jobhunter/mcp_server.py"]
    }
  }
}
```

### Phase 4: Testing & Verification

**Task 4.1:** Unit tests for workspace scanner
**Task 4.2:** Unit tests for filestore
**Task 4.3:** Integration tests for MCP tools
**Task 4.4:** MCP Inspector validation (`mcp dev mcp_server.py`)
**Task 4.5:** Host integration smoke test

---

## 9. User Experience Flow

### First-time setup

```
User: "I just added JobHunter as an MCP server. Here's my repo with resumes."
AI:   → calls scan_resumes()
AI:   "Found 3 resumes: backend-engineer.pdf (12 skills),
       fullstack.pdf (15 skills), data-engineer.docx (9 skills).
       Set 'fullstack.pdf' as active since it has the broadest skill coverage."
```

### Daily job search

```
User: "Find remote senior Python jobs posted this week"
AI:   → calls search_jobs(query="senior python engineer",
                          location="Remote", work_mode="Remote")
AI:   "Found 47 jobs. Top 5 matches:
       1. Senior Python Engineer at Stripe — 89% match
       2. Backend Engineer (Python) at Vercel — 84% match
       ..."
```

### Deep analysis

```
User: "Tell me more about the Stripe role. Is my resume good enough?"
AI:   → calls get_job_details(...)
      → calls ats_audit(...)
      → calls gap_report(...)
AI:   "Match score: 89%. ATS score: 72/100 — missing 'distributed systems'
       and 'payments' keywords. You have 10/12 required skills."
```

### Tailoring

```
User: "Tailor my resume for this job and write a cover letter"
AI:   → calls tailor_resume(...)
      → calls cover_letter(...)
AI:   "Done. Tailored resume saved to .jobhunter/output/tailored/stripe-senior-python.json
       ATS score improved 72 → 91. Cover letter saved too."
```

### Application tracking

```
User: "I applied. Track it."
AI:   → calls track_application(company="Stripe", title="Senior Python Engineer",
                                status="applied", url="...")
AI:   "Tracked. Follow-up reminder set for Nov 2."
```

---

## 10. Edge Cases & Design Decisions

1. **No resume files found:** `scan_resumes` returns empty list with a message suggesting where to put resume files.

2. **Multiple resumes:** All loaded as variants. First-discovered or user-configured one is "active." Switch with `set_active_resume`.

3. **Large workspaces:** Scanner only checks root, `resumes/`, `resume/`, `cv/` — not recursive through `node_modules/` or `.git/`.

4. **Stale engine.db:** Rebuilt on every server startup. Source of truth is always the filesystem.

5. **LLM configuration:** AI provider keys from environment variables (same as current config.py).

6. **Concurrent access:** Single process per host session. Filestore uses `threading.Lock`.

7. **Existing desktop app:** Completely unaffected. Independent data paths.

---

## 11. Dependencies

| Dependency | Purpose | Required? |
|-----------|---------|-----------|
| `mcp[cli]` | MCP protocol SDK + dev tools | Yes (new) |
| Python 3.11+ | MCP SDK requirement | Yes (upgrade from 3.10+) |
| Everything else in `jh/` | Existing engine | Already present, zero-dep |

**Total new dependencies: 1** (`mcp` package).

---

## 12. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| MCP SDK API changes | Low (v1.0 stable) | Pin version in requirements |
| Resume parser fails on some PDFs | Medium | Graceful error per file, suggest alternatives |
| Job sources rate-limit/block | Medium | Circuit breakers already in sources.py |
| Large JSON files slow down | Low | Cache TTL limits growth; purge old data |

---

## 13. Implementation Order

```
Phase 1 (Foundation):     Task 1.1 → 1.2 → 1.3     ~3 files, ~500 lines
Phase 2 (MCP Core):       Task 2.1 → 2.2            ~2 files, ~700 lines
Phase 3 (Packaging):      Task 3.1 → 3.2 → 3.3     ~5 files, ~100 lines
Phase 4 (Testing):        Task 4.1 → 4.2 → 4.3     ~3 files, ~400 lines
                          Task 4.4 → 4.5             Manual verification
```

Total estimated: **~1700 lines of new code across ~13 files**, zero lines changed in existing engine.
