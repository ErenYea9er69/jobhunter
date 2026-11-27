# JobHunter MCP Server
<!-- mcp-name: io.github.ErenYea9er69/jobhunter -->

[![PyPI version](https://img.shields.io/pypi/v/jobhunter-mcp.svg)](https://pypi.org/project/jobhunter-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/jobhunter-mcp.svg)](https://pypi.org/project/jobhunter-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Smithery](https://smithery.ai/badge/@ErenYea9er69/jobhunter)](https://smithery.ai/server/@ErenYea9er69/jobhunter)

JobHunter gives an AI assistant (Claude Desktop, Cursor, Antigravity, VS Code) tools for a full job search. It searches many sources, scores each job against your real resume, writes application documents from facts in that resume, and tracks every application. All data stays on your machine.

JobHunter works like a small company. You talk to one AI, and that AI is the CEO. It briefs a team of specialists (Scout, Analyst, Writer, Coach, Chief of Staff). A Reviewer checks every job and document before you see it. See `docs/team.md`.

By default the AI sees seven CEO tools. The 39 specialist tools sit behind them. `--surface full` shows all 46. There are no MCP prompts. The prompt playbooks are served through `get_playbook` and loaded directly by the drafting tools (`prompts/*.md`).

## Quick start

### 🚀 1-Command Run (Published on PyPI — Zero Clone, Zero Setup)

You **do not need to clone this repository** to run JobHunter with your AI assistant. Run it instantly with a single command via `uvx` (the fast, isolated package runner from Astral) or Smithery:

#### 1. Instant Verification / Terminal Run
```bash
uvx jobhunter-mcp --check
```

#### 2. Claude Desktop Integration
Add JobHunter to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "uvx",
      "args": ["jobhunter-mcp"]
    }
  }
}
```

#### 3. Cursor Integration (`.cursor/mcp.json` or Settings > MCP)
```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "uvx",
      "args": ["jobhunter-mcp"]
    }
  }
}
```

#### 4. Smithery Integration (1-Click)
```bash
npx -y @smithery/cli run @ErenYea9er69/jobhunter
```
Or 1-click install directly into Claude Desktop:
```bash
npx -y @smithery/cli install @ErenYea9er69/jobhunter --client claude
```

#### 5. Optional Arguments
You can pass any arguments directly to `uvx jobhunter-mcp`:
```bash
# Run with all specialist tools exposed
uvx jobhunter-mcp --surface full

# Run with custom resume workspace directory
uvx jobhunter-mcp --workspace /path/to/my-resumes
```

---

### 🛠️ Local Developer Setup (Optional)

Clone only if you are developing JobHunter or customizing adapters and prompts:

```bash
git clone https://github.com/ErenYea9er69/jobhunter.git
cd jobhunter
pip install -r requirements.txt
```

Verify the MCP server and register it into Claude Desktop in one command:
```bash
python mcp_server.py --check
python mcp_server.py --install-claude --workspace /path/to/resumes
```

#### Hybrid Claude Desktop Workflow:
1. **Load & Validate Resumes (`jh_begin`)**: Reads `.pdf`, `.docx`, or `.txt` resumes without guessing unconfirmed locations or roles.
2. **Confirm Target Place & Filters (`jh_confirm` -> `jh_launch` -> `jh_answer`)**: Runs headless Hybrid discovery combining multi-board job search, fresh Signal Radar posts (<24h / recent funding), and LinkedIn radar.
3. **Fit + Recency Ranked Matches in Chat (`jh_query`)**: Presents Reviewer-verified compact cards filtered by live criteria (`work_mode`, `job_type`, `min_salary`, `industries`, company exclusions).
4. **Tailor & Prepare Per User Selection**: For chosen roles, generates grounded tailored resumes (`tailor_resume`, `jh_build_resume` 1-page PDF), `cover_letter`, `interview_prep`, MX-verified hiring contacts (`jh_find_contacts`), and anti-slop cold outreach drafts (`jh_draft_email`).
5. **100% Human Control**: Never auto-submits applications or sends emails automatically. Every output is checked by `jh.team.qa` against master resume facts.

---

### 🔐 Optional LLM Provider Keys (Zero Key Required by Default)

By default, **Claude Desktop** uses your connected Claude model to orchestrate JobHunter's deterministic scoring, ATS checks, PDF exporter, and evidence grounding with **zero external API keys**. If you optionally configure a provider key in your MCP client `env` block (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, or local `OLLAMA_ENDPOINT`), wording helpers automatically use it while Reviewer grounding blocks any unsupported claim.

---

### Alternative: Standalone MCP Server via uvx

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
      "args": ["jobhunter-mcp"],
      "env": {
        "JH_WORKSPACE": "/path/to/resumes-workspace"
      }
    }
  }
}
```

*(Data is stored cleanly in JSON under `~/Desktop/jobmcp` or `JOBMCP_HOME`, with zero `.db` database files).*


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
| `confirmed_industries`, `company_stages`, `markets_served` | Optional Step 5 live SQL filters (`startup`/`scale-up`/`public`, industry, market) applied only when confirmed. |
| `side_work` | Optional confirmed current freelance or contract work; rendered on tailored resumes only when confirmed by you. |

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

The full list with arguments is in `docs/tool-contracts.md`. The CEO tools (`ceo_run` and six more) are described in `docs/team.md`. Specialist groups: resumes (5), preferences and sources (7), finding jobs (4), analysis (5), documents (7), interview and outreach (5, including `practice_interview`), playbooks (1), tracking (5), coaching (4), server (1).

Key `2.0.1` flow guarantees:
- **Explicit target place**: Resumes never supply location, remote mode, or filters. `jh_confirm` always asks you to confirm `remote only`, `worldwide remote`, or specific countries/regions (plus optional city) before issuing a session ticket.
- **Title families & live filtering**: Inferred role title families widen search queries only (never filters). Preferences confirmed during the live search filter the SQL view immediately without restarting the background worker.
- **Honest match check on Save**: Saving shows strengths alongside `soft_gaps` (e.g., 3 vs 4 years requested — marked apply anyway) and `hard_gaps` (work authorization, clearance, required license) without hiding postings.
- **Structured prep & `practice_interview`**: Interview prep includes "Tell me about yourself", Recruiter Screen, Hiring Manager, Peer Round, and unscraped Glassdoor search links. Run `practice_interview` (under `coach`) after prep exists to rehearse answers and get graded feedback.

Every tool returns one envelope: `status` (`ok`, `partial`, `error`), `success`, `data`, `warnings`, `sources`, `correlation_id`, and `coaching` (`null` by default). Errors carry a `code` and a `hint`. Search results are compact cards, so a search never floods the model's context. Use the `job_id` from a card with any tool.

## Career Coaching Layer

JobHunter includes an optional, non-intrusive career coaching layer.

### Prime Directive: Pure Execution by Default
- The default behavior is **pure, silent execution**. The app searches, scores, tailors, and tracks with zero unsolicited life or career advice.
- Factual notes (paywall flags, match scores, matched/missing skills, skill gaps, duplicate counts) appear normally in data fields and are **not** coaching.
- Coaching text appears **only** inside the top-level `coaching` envelope field (`coaching: null` when inactive). It is never mixed into data fields.
- Coaching triggers appear **at most once per session** (`coach_events`), remain under 120 words, and can be dismissed in a single click or message.

### Triggers & Priority
Triggers evaluate in strict priority order (`S > D > A > B > C > E`):

| ID | Name | Fires When | Must NOT Fire When | Priority | Frequency |
|---|---|---|---|---|---|
| **S** | Safety | Signs of crisis, despair, or self-harm. Always on, ignores opt-out. Provides locale-keyed emergency contacts. | Metaphorical speech ("kill -9", "dead end job", "dying for coffee"). | 1 (Highest) | Every occurrence |
| **D** | Distress / AI Anxiety | Overwhelming frustration (hundreds of apps with no reply) or panic about AI replacing developer jobs. | Neutral questions about AI jobs, skills, or tooling ("search AI engineer jobs"). | 2 | Once per session |
| **A** | Explicit Advice | User explicitly asks for advice, opinion, or help deciding ("what would you advise?"). Overrides session opt-out for that request. | Normal job search queries or formatting commands. | 3 | Once per request |
| **B** | Early Career / Reach | Entry-level candidate (confidence >= medium) + aspirational reach target ("dream/ideal job", FAANG) + objective mismatch (seniority gap >= 2 or top scores < threshold). Offers Dual Track A/B. | Mid/Senior candidates, low-confidence profiles, queries with "best" ("best Python jobs"), or after track accepted. | 4 | Once per session |
| **C** | Business / Startup | Asks what business to start or how to make money with a company. Validates existing skills and customer demand; warns against scheme red flags. | Ordinary business analyst or business operations job searches. | 5 | Once per session |
| **E** | Career Direction | Asks about career direction, choosing a path, or "what am I good at". Focuses on demonstrated competencies. | Idiomatic praise ("good job!", "great job finding those listings"). | 6 | Once per session |

### Opt-Out & Controls
- **Chat Opt-Out:** Speaking phrases like *"just search"*, *"no advice"*, *"skip the coaching"*, or *"stop coaching"* turns coaching off for the session. *"No advice on this one"* suppresses coaching for that single query. Or configure `set_coaching_preference` via MCP tools.
- **Dual Track Selection:** When Trigger B fires, users can choose *Target Track Only*, *Bridge Track*, or *Both (Dual Track)*. The optional `track` parameter (`"bridge" | "target" | "both"`) is passed to searches.

### Configuration
Configure coaching behavior via environment variables:
- `JH_COACHING`: `on` or `off` (default: `on`).
- `JH_COACH_CLASSIFIER`: `local` (deterministic regex/rules), `provider` (LLM-assisted classification), or `off` (default: `local`).
- `JH_COACH_THRESHOLD`: Seniority score mismatch cutoff (default: `60`).
- `JH_COACH_LANG`: Preferred coaching language code (e.g. `en`, `es`, `fr`; default: `en`).

### Editing Templates & Guidelines
- **Prompt Guidelines:** `prompts/coach/coach_guidelines.md` contains persona rules and style anchors (linted via `python -m jh.team.voice prompts/coach/coach_guidelines.md`).
- **Templates:** Vetted deterministic fallback templates live in `jh/coach/templates/<lang>.json`.
- **Lexicons:** Classification regex patterns live in `jh/coach/lexicons/<lang>.json`.
- **Emergency Directory:** Locale emergency hotlines live in `jh/coach/emergency.json`.

### MCP Server Integration
JobHunter runs as an official stdio MCP server via `mcp_server.py`:
```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "env": {
        "JH_COACHING": "on",
        "JH_COACH_CLASSIFIER": "local"
      }
    }
  }
}
```

## Truthful by design

- The Reviewer does not trust the employee who made the work. It checks every job (fields, link, date, country, duplicates, matched skills, scams, text aimed at your AI), reads live posting pages, and checks every document sentence against your resume. Invented employers, titles, degrees, certifications, skills, numbers and awards are removed or rejected, returning structured `status` (`approved`, `blocked_fixable`, `blocked_missing_data`), `blockers`, `warnings`, and `unchecked` fields, with a 2-pass internal rewrite cap in `ceo_submit_work`. Details in `docs/team.md`.
- The Reviewer is measured. `python -m jh.team.evals` scores it on fixed cases, and `docs/evals.md` reports the numbers and how far to trust them. The honest estimate on text it has never seen is lower than the scores on the cases it was built with.
- The CEO's report comes from tool results only, and every job and document names the call that produced it.
- The prompts follow their own rules. A linter (`python -m jh.team.voice`) checks all 17 prompt files (`prompts/*.md`, `prompts/team/*.md`, `prompts/coach/coach_guidelines.md`) for dashes, capital-letter shouting, persona boasting and invented statistics, and `tests/test_prompt_contract.py` / `tests/test_prompts.py` verify that each playbook's schema keys (`missing_inputs`, `honest_gaps`, `pitch_hook`, `linkedin_connection_validated`, etc.) match the code. Drafts are scanned for machine-sounding phrases, and the Reviewer warns about them. See `docs/prompts.md`.
- When a search finds nothing, the CEO widens it in steps and then says so. It does not fill the gap.
- Playbooks and deterministic fallbacks never invent missing candidate facts (such as salary targets, notice periods, work authorization, visa sponsorship, relocation, or interview discussion topics); instead, they return `missing_inputs` questions for the user. LinkedIn connection notes are validated to stay within 200 characters without mid-word truncation.
- Generated text uses only facts the resume supports. `get_evidence` lists them.
- `verify_draft` checks any text against that evidence and flags unsupported claims. `tailor_resume`, `cover_letter` and `prepare_application` run the same check and return the result.
- Tools never accept or return API keys. Optional LLM keys come from environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` and others). Without a key the deterministic engine writes the documents.

## Your data

Everything lives locally under `~/Desktop/jobmcp/` (override via `JOBMCP_HOME`), or `JH_DATA_DIR` when explicitly set. Zero `.db` / SQLite files are created.

- `data/` holds atomic JSON workspace persistence (`durable.json` for resumes, view filters, applications, watchlist, settings; `cache.json` for search cache and signals).
- `preferences.json` holds your preferences, feeds and career pages.
- `outputs/` holds adapted resumes, 1-page PDFs, cover letters, interview prep and reports.

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
- When no model writes the text, the code's deterministic fallback templates do; they follow the updated prompt rules and emit `missing_inputs` when key facts are absent. (Legacy `jh/interview.py` scoring and localized `jh/coach/templates/es.json` / `fr.json` templates retain older formatting.)
- Only the top five jobs of a search get a live link check. Ask the CEO to recheck one before you apply.
- Several scrapers return an empty list instead of an error when blocked, so `source_health` shows them as ok with zero results.
- Reading some boards (LinkedIn, Indeed, ZipRecruiter and others) uses browser-like requests. See `docs/data-policy.md` and use `disabled_sources` if you do not want that.

## License

MIT. See `LICENSE`.
