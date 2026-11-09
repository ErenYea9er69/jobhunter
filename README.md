# JobHunter MCP Server

JobHunter gives an AI assistant (Claude Desktop, Cursor, Antigravity, VS Code) tools for a full job search. It searches many sources, scores each job against your real resume, writes application documents from facts in that resume, and tracks every application. All data stays on your machine.

JobHunter works like a small company. You talk to one AI, and that AI is the CEO. It briefs a team of specialists (Scout, Analyst, Writer, Coach, Chief of Staff). A Reviewer checks every job and document before you see it. See `docs/team.md`.

By default the AI sees seven CEO tools. The 39 specialist tools sit behind them. `--surface full` shows all 46. There are no MCP prompts. The old prompt contracts are the `get_playbook` tool.

## Quick start

### ⚡ 1-Command Turnkey Run (Windows, macOS, Linux)

Clone the repository and launch the entire copilot ecosystem (Web Dashboard, ATS Autofill Extension, SQLite database, and MCP bridge) with one command:

```bash
git clone https://github.com/ErenYea9er69/jobhunter.git
cd jobhunter
pip install -r requirements.txt
```

#### Run on Windows:
Double-click `run.bat` or execute in PowerShell / CMD:
```cmd
run.bat
# or
python run.py
```

#### Run on macOS & Linux:
```bash
chmod +x run.sh
./run.sh
# or
python3 run.py
```

#### Launcher CLI Options:
```bash
python run.py [OPTIONS]
  --port PORT          Port for HTTP daemon (default: 8765)
  --host HOST          Host to bind to (default: 127.0.0.1)
  --no-browser         Do not auto-launch Chromium with extension
  --setup-only         Provision directories, DB, and MCP configs, then exit
  --set-key KEY        Store API key for Standalone Direct API mode
  --provider PROVIDER  AI Provider (gemini, openai, anthropic, deepseek, groq, mistral)
  --model MODEL        Target model (e.g. gemini-3.8-flash, gpt-5-mini, claude-3-7-sonnet)
  --clear-key          Delete stored API keys and return to MCP mode
  --ai-status          Display active AI provider, mode, and masked key
  --test-ai            Test connection to the active AI endpoint and measure latency
```

#### What happens automatically:
1. **Candidate Drop Folder Provisioned**: Auto-creates `resumes/` with a `PUT_YOUR_RESUME_HERE.txt` guide. Drop your Word (**`.docx`**), PDF (**`.pdf`**), or Text (**`.txt`**, **`.md`**) resume right into this folder.
2. **SQLite Database Initialized**: Automatically creates your private local database (`engine.db`) in `~/.jobhunter/` or your workspace.
3. **AI Coding Agents Auto-Connected (MCP)**: Auto-detects and writes MCP configuration for **Cursor** (`.cursor/mcp.json`) and **Claude Desktop** so your AI assistant shares the exact same resume facts and tracking database.
4. **Web Dashboard Served**: Starts the local HTTP daemon and serves the 6-tab autonomous dashboard on `http://127.0.0.1:8765`.
5. **Browser Extension Loaded**: Detects your installed Chromium browser (Google Chrome, Microsoft Edge, Brave) and launches it with the ATS Autofill extension preloaded (`--load-extension`).
6. **First-Run Web Drop Wizard**: If no resume exists yet, the web dashboard displays a drag-and-drop wizard allowing you to upload your Word, PDF, or Text resume directly from the browser with instant skill extraction.

---

### 🖥️ Modern Web Dashboard & Visual Workspace

JobHunter includes a responsive, dark/light themed single-page web application running locally on `http://127.0.0.1:8765`. The interface uses a black, gray and white theme with small green, amber and red score colors. See `DESIGN.md` and `UI-CHANGES.md`:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          JOBHUNTER DASHBOARD                           │
├───────────────┬───────────────────────────────┬────────────────────────┤
│ TAB 1: RADAR  │ TAB 2: PIPELINE KANBAN        │ TAB 3: DOCUMENT STUDIO │
│ Opportunity   │ 5-Stage Visual Funnel         │ 100% Truthful QA       │
│ Discovery     │ Saved → Applied → Interview   │ Cover Letters & Pitch  │
├───────────────┼───────────────────────────────┼────────────────────────┤
│ TAB 4: PROFILE│ TAB 5: AI & CALIBRATION       │ TAB 6: AUTO-APPLY HUB  │
│ Resume Drop   │ Dual Engine (MCP vs API)      │ ATS Extension Dispatch │
│ & Variants    │ 2026 Frontier Models          │ 1-Click Browser Launch │
└───────────────┴───────────────────────────────┴────────────────────────┘
```

#### Tab 1: Radar & Opportunity Discovery
- **Multi-Source Aggregation**: Real-time unified search across 100+ platforms (Company Greenhouse/Ashby/Lever boards, Y Combinator, Hacker News, regional national sites, and remote boards).
- **Match Scoring Engine (0-100%)**: Every posting is ranked strictly against the candidate's verified skills, experience level, and target preferences.
- **Smart Filters**: Filter instantaneously by Work Mode (Remote, Hybrid, Onsite), Job Type (Full-time, Internship/PFE, Contract), and Score Floor.
- **1-Click Queue Auto-Apply**: Queue promising opportunities directly into the Auto-Apply batch runner.

#### Tab 2: Application Kanban Pipeline
- **Visual Funnel Tracking**: 5 automated progression lanes: `Saved` → `Queued Auto-Apply` → `Applied` → `Interviewing` → `Offers`.
- **Gmail Sync Integration**: 1-click sync scans your connected inbox for ATS confirmations, interview invitations, and status updates, automatically transitioning opportunities across lanes without manual entry.
- **Application Analytics**: Tracks submission velocity, response rates, and active interview conversions.

#### Tab 3: Truthful Document Studio & Copilot
- **Multi-Format Document Generation**:
  - **Cover Letters**: Direct-impact, metrics-driven pitches tailored to the job description.
  - **YC-Style Founder Cold Emails**: High-converting, short pitches with an automated **Founder Corporate Email Finder** that synthesizes and verifies executive email formats.
  - **Big Tech Recruiter & Internal Referrals**: Calibrated for levels and terminology at Google (L3-L6), Meta (E3-E6), Uber, Amazon, Apple, Microsoft, Netflix, and Stripe.
  - **STAR Interview Guides**: Complete preparation matrices with Situation, Task, Action, and Result outlines grounded in your actual work history.
- **Reviewer QA Badge**: Every generated paragraph is audited sentence-by-sentence against candidate resume facts before approval. Unsupported claims are rejected or flagged with zero hallucinations.
- **Direct Export**: 1-click Copy, Print to PDF, or "Open in Gmail" prefilled draft.

#### Tab 4: Candidate Profile & Resume Variants
- **Master Profile Display**: Visual hero card showing extracted coordinates, verified skills chips, and reverse-chronological professional timeline.
- **First-Run Drop Folder & Drag-and-Drop Web Wizard**: Upload Word (**`.docx`**), PDF (**`.pdf`**), or Text (**`.txt`**, **`.md`**) resumes directly in the browser or drop them into `resumes/`.
- **Variant Management**: Switch between specialized resume variants (e.g. Backend vs AI Engineer) with one click; all ranking and generation immediately recalibrate.

#### Tab 5: Search Calibration & AI Dual Engine
- **Target Filtering**: Configure target countries (e.g., Tunisia, France, Germany, Worldwide Remote), preferred cities, work mode, and search depth.
- **Dream & Excluded Companies**: Boost priority for dream employers; permanently blacklist companies and unwanted technologies.
- **AI Engine Control Deck**: Live mode badge (`Direct API Active` vs `External MCP Host Mode`), provider selector, 2026 frontier model picker, masked key display, latency test, and 1-click key wipe.

#### Tab 6: Auto-Apply & Desktop Hub
- **Queue Dispatcher**: Automatically iterates through queued applications and launches the autofill sequence.
- **Work Authorization & Visa Compliance**: Sets deterministic rules for legal authorization, sponsorship requirements, and notice period.
- **1-Click Chromium Launcher**: Detects your installed Chrome, Edge, or Brave browser and boots it with the JobHunter extension active.

---

### 🧩 Chrome ATS Autofill Extension

Located in `extension/`, the JobHunter extension turns your browser into an automated job application copilot:

- **Manifest V3 Architecture**: Fast, lightweight, and operates entirely against your local daemon (`http://127.0.0.1:8765`).
- **Supported ATS Platforms**:
  - Greenhouse (`boards.greenhouse.io`)
  - Lever (`jobs.lever.co`)
  - Ashby (`jobs.ashbyhq.com`)
  - Workday (`*.myworkdayjobs.com`)
  - SmartRecruiters, Recruitee, Workable, and custom employer career portals.
- **Smart Form Autofill**: Instantly populates personal coordinates, resume attachments, LinkedIn, GitHub, portfolio URLs, and work authorization disclosures.
- **Grounded Screening Question Solver**: Intercepts custom employer questions (e.g., *"Describe a time you solved an architectural bottleneck"*, *"What is your experience with Kubernetes?"*) and formulates accurate answers drawn solely from candidate facts in SQLite.
- **Review panel**: A panel on the page lists every filled field with an Undo, lists fields that need you, and never submits unless you chose countdown mode.

---

---

### 🔀 Dual Execution Modes: External MCP Host vs. Standalone Direct API

JobHunter operates seamlessly in two distinct modes, and you can switch between them at any time:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MODE 1: EXTERNAL MCP HOST                       │
│  Zero API keys required in JobHunter!                                  │
│  Claude Desktop or Cursor runs its own frontier LLM model              │
│  and talks to JobHunter via MCP stdio tools.                           │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ (Switch dynamically anytime)
┌────────────────────────────────────▼───────────────────────────────────┐
│                    MODE 2: STANDALONE DIRECT API                       │
│  No external AI IDE needed! Clone and supply your own API key.        │
│  Powers the Web Dashboard & Chrome Extension directly via SQLite.      │
│  Supports Gemini 3.8 Flash, GPT-5 Mini, Claude 3.7 Sonnet, etc.        │
└────────────────────────────────────────────────────────────────────────┘
```

#### Mode 1: External MCP Host Mode (Zero Keys Needed)
- If you use **Claude Desktop**, **Cursor**, **Antigravity**, or **Claude Code**, you **do NOT need to supply any API keys**.
- The AI IDE hosts the conversation and passes context to JobHunter's tools over stdio.
- All documents, tailoring, and scoring run through JobHunter's strict offline Reviewer QA engine.

#### Mode 2: Standalone Direct API Mode (Web Dashboard & Chrome Extension)
- If you want to use the Web Dashboard and ATS Autofill extension independently without running Claude Desktop or Cursor, you can supply your API key directly via CLI or Web UI.
- Your key is stored securely in your private local SQLite database (`engine.db`) and is **never** sent to external telemetry or exposed in logs.

##### Configure via Command Line (Windows, macOS, Linux):
```bash
# 1. Activate Google Gemini (Default frontier: gemini-3.8-flash)
python run.py --set-key YOUR_GEMINI_API_KEY --provider gemini --model gemini-3.8-flash

# 2. Activate OpenAI (Default frontier: gpt-5-mini or o3-mini)
python run.py --set-key YOUR_OPENAI_API_KEY --provider openai --model gpt-5-mini

# 3. Activate Anthropic Claude (Default frontier: claude-3-7-sonnet)
python run.py --set-key YOUR_ANTHROPIC_API_KEY --provider anthropic --model claude-3-7-sonnet

# 4. Activate DeepSeek
python run.py --set-key YOUR_DEEPSEEK_KEY --provider deepseek --model deepseek-chat

# 5. Check active mode & masked key
python run.py --ai-status

# 6. Test connection latency and endpoint health
python run.py --test-ai
```

##### Configure via Web Dashboard:
1. Open `http://127.0.0.1:8765` in your browser.
2. Navigate to the **Calibration & Filters** tab.
3. In the **AI Engine & Dual Execution Mode** card:
   - Select your provider (**Google Gemini**, **OpenAI**, **Anthropic**, **DeepSeek**, **Groq**, **Mistral**, or local **Ollama**).
   - Pick a model or enter a custom identifier.
   - Paste your key and click **Save & Activate**.
   - Click **Test Connection** to verify round-trip ping and latency.

#### Reverting to MCP Mode / Deleting Your Key:
You can wipe your stored API key at any time to return JobHunter to External MCP / Deterministic mode:
```bash
# Via CLI:
python run.py --clear-key

# Or via Web Dashboard:
Click the "Clear Key" button in Tab 5 (Calibration & Filters)
```

#### 2026 Frontier Models Supported:
- **Google Gemini**: `gemini-3.8-flash` (recommended default), `gemini-3.1-pro`, `gemini-3.5-flash`
- **OpenAI**: `gpt-5-mini` (recommended default), `o3-mini`, `gpt-5`
- **Anthropic**: `claude-3-7-sonnet` (recommended default), `claude-3-5-haiku`
- **DeepSeek**: `deepseek-chat`, `deepseek-reasoner`
- **Groq**: `llama-3.3-70b-versatile`, `qwen-2.5-coder-32b`
- **Mistral**: `mistral-large-latest`
- **Ollama**: `llama3.3`, `deepseek-r1` (local, zero cloud keys)

---

---

### Alternative: Standalone MCP Server via uvx

If you only want the stdio MCP server without the web dashboard:

```bash
uvx --from git+https://github.com/ErenYea9er69/jobhunter jobhunter-mcp
```

### Claude Code CLI

Add JobHunter directly with the Claude CLI:

```bash
claude mcp add jobhunter -- uvx --from git+https://github.com/ErenYea9er69/jobhunter jobhunter-mcp
```

### Claude Desktop Configuration

Add the server to your `claude_desktop_config.json`:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/ErenYea9er69/jobhunter",
        "jobhunter-mcp"
      ],
      "env": {
        "JH_DATA_DIR": ""
      }
    }
  }
}
```

*(Leave `JH_DATA_DIR` empty to default to `~/.jobhunter`, or provide a custom directory path).*

### Local Development

```bash
pip install -r requirements.txt
python mcp_server.py --check        # starts the server, lists the tools, exits
```

Put a PDF, DOCX or TXT resume in your workspace folder (or in `resumes/`), or use `scan_resumes` / `parse_resume_file`. Local configuration can also be pointed at a workspace:

```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["/absolute/path/to/jobhunter/mcp_server.py"],
      "env": { "JH_WORKSPACE": "/absolute/path/to/your/workspace" }
    }
  }
}
```

First conversation. Just talk to the AI:

1. "Set me up. I want to work in Tunisia and France." The CEO reads your resumes and saves your preferences.
2. "Find backend engineer jobs." The Scout searches, the Reviewer checks each job and reads the top posting pages.
3. "Find small companies hiring python developers in Sfax." Same, with a bias toward small and local employers.
4. "Write a cover letter for the second one." or "...for the Adyen job." The CEO resolves the pointer against the last list. The Writer drafts. The Reviewer checks every sentence against your resume.
5. "I applied to Adyen." "Not interested in banks." "Why is the fit low for the first one?" The CEO updates your tracker or your exclusions, then reads the change back to confirm it. Or it explains the score.

The answer is a short brief. The full report and data are behind it. Every answer says what was not verified. Nothing is submitted for you.

## Make it yours

`set_preferences` stores your choices in `.jobhunter/preferences.json`. They apply to every resume and every search.

| Key | Meaning |
| --- | --- |
| `target_countries` | Where you want to work, for example `["Tunisia", "France", "Germany"]`. Picks the local sources. |
| `home_country`, `cities` | Where you live and the cities you prefer. |
| `work_mode` | `Any`, `Remote`, `Hybrid` or `Onsite`. Onsite skips remote-only boards. |
| `target_titles` | Roles to search. The first is the main one. |
| `min_salary`, `salary_currency` | A yearly floor. Salaries in TND, MAD, EGP, AED and SAR are read as monthly figures. |
| `job_types`, `seniority` | Full-time, Contract, Internship. Junior to director. |
| `excluded_keywords`, `excluded_companies`, `dream_companies` | Hide or boost. |
| `company_focus` | `any`, `avoid_big_names` or `only_big_names`. |
| `max_age_days` | Hide postings older than this. Default 30. |
| `search_depth` | `quick`, `standard` or `deep` (more query variants). |
| `enabled_sources`, `disabled_sources` | Choose exactly which sources run. |
| `needs_visa_sponsorship`, `open_to_relocation`, `languages` | Stored and applied to the resume profile. |

Example: `set_preferences({"target_countries": ["Tunisia", "France"], "company_focus": "avoid_big_names", "excluded_keywords": ["php"]})`.

## Where the jobs come from

Which sources run depends on your target countries. A search from Tunisia no longer calls India's Naukri or France's HelloWork. A search that targets France calls HelloWork and `fr.indeed.com`.

| Source | Serves | Notes |
| --- | --- | --- |
| Company Boards | Worldwide | Greenhouse, Lever (US and EU), Ashby, Workable, SmartRecruiters, Recruitee, Personio, Teamtailor, BambooHR, Breezy |
| Y Combinator, Hacker News | Worldwide | Hacker News now reads three pages of the monthly thread |
| LinkedIn | Worldwide | Unchanged. See "Protected code" below |
| Indeed | 41 countries | One call per target country, on the local site |
| Bayt | Middle East and North Africa | One call per target country |
| Arbeitsagentur | Germany | Public employment service, no key |
| HelloWork, Naukri, ZipRecruiter | France, India, US and Canada | |
| Adzuna | 19 countries | Needs a free key (`ADZUNA_APP_ID`, `ADZUNA_APP_KEY`) |
| Regional Boards | Tunisia, Morocco, Algeria, Egypt, Nigeria, Kenya, South Africa | Local boards (Keejob, ReKrute, Wuzzuf and others) read through their job data and sitemaps. Tries local-language queries too |
| Jooble | Many countries | Aggregator that collects small local boards. Needs a free key (`JOOBLE_API_KEY`) |
| JobTech | Sweden | Public employment service, no key |
| Himalayas, Remotive, Jobicy, RemoteOK, We Work Remotely, Working Nomads | Remote | Skipped when you want onsite work |
| Arbeitnow, The Muse | Europe, US and UK | |
| Custom Feed, Career Page, Job Sites | Anywhere you point them | Added with `add_job_source` |

### Reaching small and regional employers

The big boards show the same famous names. These features reach the rest:

- `add_job_source(kind="company", value="Acme")` finds the company's public board by name, or reads a careers URL directly. Every open role is searched.
- `add_job_source(kind="feed", value=<rss url>)` adds any RSS, Atom or JSON feed, such as a national job board. The feed is test-read before it is saved.
- `add_job_source(kind="career_page", value=<url>)` reads schema.org job data on a careers page, or follows an embedded ATS link.
- `add_job_source(kind="site", value=<url>)` adds a small job board or any site that publishes schema.org job data (what Google for Jobs reads). The reader finds job pages through the sitemap and the page's links. It obeys `robots.txt` and refuses a site that forbids reading, even with `force`. Not sure which kind to use? `discover_job_source(url)` explains how a site can be read and adds nothing.
- Regional Boards runs the catalog in `jh/regional_boards.py` for your target countries. Queries are also sent in French for countries where local boards post in French ("software engineer" also searches "ingénieur logiciel").
- Pinpoint is a new company board type, so small employers on that system are found by name.
- Boards discovered along the way: every job link that points at a known ATS adds that company's board to later searches. Each search teaches the next one. Boards that fail three times rest for 24 hours.

The built-in starter list of company boards is short and its slugs are unverified. Dead ones prune themselves.

Honest limits of this reach: the catalog names real local boards, but nobody has checked here which of them publish readable job data or allow reading. A board that does not shows zero in `source_health`. Add your own with `kind="site"`. A site that builds its job list with scripts cannot be read this way. Use `kind="company"` if the employer uses a known ATS.

## Tools

The full list with arguments is in `docs/tool-contracts.md`. The CEO tools (`ceo_run` and six more) are described in `docs/team.md`. Specialist groups: resumes (5), preferences and sources (7), finding jobs (4), analysis (5), documents (7), interview and outreach (4), playbooks (1), tracking (5), server (1).

Every tool returns one envelope: `status` (`ok`, `partial`, `error`), `success`, `data`, `warnings`, `sources`, `correlation_id`. Errors carry a `code` and a `hint`. Search results are compact cards, so a search never floods the model's context. Use the `job_id` from a card with any tool.

## Truthful by design

- The Reviewer does not trust the employee who made the work. It checks every job (fields, link, date, country, duplicates, matched skills, scams, text aimed at your AI), reads live posting pages, and checks every document sentence against your resume. Invented employers, titles, degrees, certifications, skills, numbers and awards are removed or rejected. Details in `docs/team.md`.
- The Reviewer is measured. `python -m jh.team.evals` scores it on fixed cases, and `docs/evals.md` reports the numbers and how far to trust them. The honest estimate on text it has never seen is lower than the scores on the cases it was built with.
- The CEO's report comes from tool results only, and every job and document names the call that produced it.
- The prompts follow their own rules. A linter checks every prompt for dashes, capital-letter shouting, persona boasting and invented statistics, and a test checks that each playbook asks the model for the keys the code reads. Drafts are scanned for machine-sounding phrases, and the Reviewer warns about them. See `docs/prompts.md`.
- When a search finds nothing, the CEO widens it in steps and then says so. It does not fill the gap.
- Generated text uses only facts the resume supports. `get_evidence` lists them.
- `verify_draft` checks any text against that evidence and flags unsupported claims. `tailor_resume`, `cover_letter` and `prepare_application` run the same check and return the result.
- Tools never accept or return API keys. Optional LLM keys come from environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` and others). Without a key the deterministic engine writes the documents.

## Your data

Everything lives in your user home directory at `~/.jobhunter/` by default, or the folder configured via the `JH_DATA_DIR` environment variable.

- `engine.db` is the SQLite database: resumes, stored jobs, applications, watchlist, board health.
- `preferences.json` holds your preferences, feeds and career pages.
- `output/` holds adapted resumes, cover letters, interview prep and exports.

Applications live in SQLite. Any old `applications.json` is imported once and renamed.

## Protected code

The LinkedIn scraper (`LinkedInGuest`), the LinkedIn radar in `jh/pipeline.py`, and its two config getters are not to be edited. `tests/test_protected_linkedin.py` checks them byte for byte. The radar's background workers are not started by the MCP server. See `AGENTS.md`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

The suite runs offline. A fake network serves fixtures that pin each vendor's response format. Live behaviour of the newer adapters (Recruitee, Personio, Teamtailor, BambooHR, Breezy, Working Nomads, The Muse, Arbeitsagentur, Jooble, JobTech, Pinpoint) and of the regional boards was not checked against real servers. The site reader and the Reviewer's link check follow public standards (schema.org JobPosting, sitemaps, robots.txt) and are tested against fixtures. `source_health` shows any adapter whose format has drifted.

## Known limits

- Job IDs ignore location, so one title at one company in two cities shares an ID. The LinkedIn radar uses the same key, so it was left alone.
- Salary comparison does not convert currencies.
- The CEO's request router is rule-based. It reads English and French, and a few Arabic words. On phrasings it had never seen, it was right about two times in three. An unclear request makes the CEO ask. The AI should pass `hints.intent` and `hints.reference` so nothing is guessed.
- The Reviewer is also rules, not a model. It was built to catch what language models tend to invent. A new kind of fabrication can get through. Facts about the employer beyond the posting cannot be checked at all, so they are flagged.
- When no model writes the text, the code's own templates do, and some still contain stock phrases (the outreach, follow-up and screening templates). The Reviewer flags them. They are listed in `docs/prompts.md`.
- Only the top five jobs of a search get a live link check. Ask the CEO to recheck one before you apply.
- Several scrapers return an empty list instead of an error when blocked, so `source_health` shows them as ok with zero results.
- Reading some boards (LinkedIn, Indeed, ZipRecruiter and others) uses browser-like requests. See `docs/data-policy.md` and use `disabled_sources` if you do not want that.

## License

MIT. See `LICENSE`.
