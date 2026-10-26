# JobHunter — Resume-First Multi-Board Job Engine & AI Tailor

JobHunter is a privacy-first job acquisition platform that starts with your resume. Upload your resume once: the engine parses it into a structured candidate profile, queries official employer ATS portals, major job boards (including a native, bot-immune LinkedIn search engine), and global tech feeds simultaneously, deduplicates listings across boards, scores your fit from 0 to 100, and tailors your resume for each role without ever hallucinating or inventing credentials.

---

## Data Source Strategy & Transparency

JobHunter prioritizes 100% free direct-to-employer opportunities. Sources are categorized and ranked so you never waste time behind membership paywalls:

| Tier & Category | Sources Included | Features & Behavior |
| :--- | :--- | :--- |
| **Tier 1: Direct Employer ATS** | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Startup ATS, Y Combinator | Programmatic public endpoints. 100% free direct employer applications with zero paywalls or middleman delays. |
| **Tier 1: Major Job Boards** | **LinkedIn** (Guest API Engine), **Indeed**, **ZipRecruiter**, **Bayt**, **Naukri**, **HelloWork** | Full-market coverage across tech, non-tech, hybrid, and local roles worldwide. |
| **Tier 2: Global Tech Feeds** | Himalayas, Jobicy, Arbeitnow, Adzuna, Hacker News "Who's Hiring" | Curated developer, startup, and remote feeds with transparent attribution. |
| **Paid / Gated Feeds (Demoted)** | Remote OK, Remotive, WeWorkRemotely | Gated feeds that prompt candidates for paid memberships ($15–$99/mo) are flagged with explicit paywall notes and automatically de-prioritized. |

---

## Native LinkedIn Engine & Background Radar

JobHunter features a custom LinkedIn search and radar engine built for speed, resilience, and real-time discovery without requiring login credentials or paid API subscriptions:

- **Bot-Detection Immunity**: Uses `curl_cffi` Chrome TLS fingerprint impersonation (JA3/JA4 spoofing) and asynchronous session warmup to bypass Cloudflare and LinkedIn bot filters.
- **Automated HTTP 429 Resilience**: Retains persistent TLS sessions and applies jittered backoff retries, preventing rate-limit crashes.
- **Step-25 Non-Overlapping Pagination**: Replaces naive step-10 loops with step-25 pagination to eliminate duplicate fetches and maximize scraping throughput (~10 jobs/sec).
- **Minute-Precision Post Age**: Parses relative `<time>` timestamps directly from LinkedIn cards (`"18 minutes ago"`, `"2 hours ago"`), converts them to UTC ISO datetimes, and tags postings under 2 hours old with `"just-posted"`.
- **Company Profile Links**: Extracts direct LinkedIn company URLs (`company_url`) for immediate company research.
- **Automated Background Radar**: Runs on a configurable background daemon (default: every 10 minutes) with polite jitter (`0.8–1.5s`). Uses an adaptive 3-stage loop:
  1. **Ultra-Fresh Stream**: Probes today's chronological stream (`sortBy=DD&f_TPR=r86400`).
  2. **Skill-Slice Pivoting**: When page 1 is stagnant, automatically rotates to skill-based query variants derived from your profile.
  3. **Deep Catalog Backfill**: Advances persistent database cursors to uncover unseen roles up to LinkedIn's 1000-job ceiling.
- **3-Table SQLite Deduplication**: Cross-checks `search_jobs`, `pending_search_jobs`, and `seen_jobs` with canonical `company|title` keying to guarantee zero duplicate alerts.

---

## Key Features

1. **Resume Intake & Parser**
   - Upload PDF, DOCX, TXT, or Markdown, or paste raw text.
   - Extracts candidate title, years of experience, core skill matrix, work history, and education.
   - Interactive profile editor lets you review and refine details before searching.
   - Your master resume stays 100% private in local SQLite (`data/jobhunter.db`).

2. **Unified Search & Deduplication**
   - Single query executes concurrently across direct ATS boards, major job boards, and feeds.
   - If a role appears on LinkedIn, Indeed, and Greenhouse, it collapses into a **single card** linking to all application sources, highlighting direct ATS links first.

3. **0–100 Match Score & Fit Rationale**
   - Evaluates exact skill overlap, title alignment, work mode (remote/hybrid/on-site), and experience seniority.
   - Displays color-coded match badges and an explainable fit breakdown highlighting matched skills, missing requirements, and company authority.

4. **Non-Hallucinatory Resume Refiner**
   - Rephrases summary and bullet points to echo the job posting's vocabulary while preserving strict factual grounding.
   - **Zero Hallucination Guarantee**: Never invents fake companies, unearned credentials, or technologies absent from your master resume.
   - Granular controls: **Accept** or **Reject** changes individually, or edit inline.
   - Master resume remains untouched; job-specific versions are saved separately.

5. **Multi-Provider AI Tailoring**
   - Supports **Claude** (Anthropic), **GPT-4o** (OpenAI), **Gemini** (Google), **Ollama** (local offline models), or the built-in **deterministic rule engine** when no API key is provided.

6. **Honest Skill Gap Report**
   - **"Add This If True"**: Standard tools/practices (e.g. Git, Docker, REST, Agile) you might know. 1-click button to append to your profile.
   - **"Real Architectural Gaps"**: Deep technical prerequisites (e.g. Kubernetes, Go, Rust) with interview talking tracks.

7. **Cover Letter Generator & Interview Prep Studio**
   - Generates tailored, 3-paragraph cover letters in candidate voice using only verified resume facts.
   - Generates role-specific behavioral questions (STAR format), technical deep dives, and questions to ask the interviewer.

8. **Application Tracker (Kanban Pipeline)**
   - 5 Stages: *Saved*, *Applied*, *Interviewing*, *Offer Received*, *Archived*.
   - Drag-and-drop workflow, follow-up countdowns with overdue warning indicators, and interview notes.

9. **Dream Company Watchlist**
   - Track high-target companies (OpenAI, Stripe, GitLab, Figma, etc.).
   - Automatically monitors their public career endpoints and flags openings.

10. **100% Local Privacy & Data Purge**
    - Zero telemetry, tracking, or remote analytics. One-click "Permanently Wipe Data" button wipes SQLite tables and compacts the database.

---

## Model Context Protocol (MCP) Server

JobHunter runs as an **MCP Server** directly inside AI coding assistants:
- **Antigravity**
- **Cursor**
- **Claude Desktop**
- **VS Code Copilot / Windsurf / Cline**

The MCP server exposes **24 tools** and **6 resources** using the standard `stdio` transport.

### Quick Start: Running the MCP Server

```bash
# 1. Install dependencies
pip install -r requirements-mcp.txt

# 2. Run the MCP server directly
python mcp_server.py
```

### Resume-as-Code Filesystem Architecture

JobHunter reads your resumes directly from your repository workspace:
- Place resume files (`.pdf`, `.docx`, `.txt`) in your repository root or a `resumes/` folder.
- When the MCP server launches, it scans and parses each resume into a distinct variant (e.g., `backend-engineer.pdf` → "Backend Engineer").
- Persistent application records, user settings, and tailored outputs live as JSON files in `.jobhunter/`:
  - `.jobhunter/config.json` — Preferences and active resume selection
  - `.jobhunter/applications.json` — Tracked job applications and interview status
  - `.jobhunter/output/tailored/` — Generated tailored resumes
  - `.jobhunter/output/cover-letters/` — Generated cover letters
  - `.jobhunter/output/reports/` — ATS audits and skill gap analyses

### MCP Host Setup Examples

See detailed configuration examples in [`docs/mcp-setup/`](docs/mcp-setup/README.md):
- [Claude Desktop (`claude_desktop_config.json`)](docs/mcp-setup/claude_desktop_config.json)
- [Cursor (`.cursor/mcp.json`)](docs/mcp-setup/cursor_mcp.json)
- [Antigravity (`antigravity_mcp_config.json`)](docs/mcp-setup/antigravity_mcp_config.json)
- [VS Code (`.vscode/mcp.json`)](docs/mcp-setup/vscode_mcp.json)

---

## Running Tests

Run the full verification test suite:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

