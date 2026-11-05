# JobHunter MCP Server

JobHunter gives an AI assistant (Claude Desktop, Cursor, Antigravity, VS Code) tools for a full job search. It searches many sources, scores each job against your real resume, writes application documents from facts in that resume, and tracks every application. All data stays on your machine.

JobHunter works like a small company. You talk to one AI, and that AI is the CEO. It briefs a team of specialists (Scout, Analyst, Writer, Coach, Chief of Staff). A Reviewer checks every job and document before you see it. See `docs/team.md`.

By default the AI sees seven CEO tools. The 39 specialist tools sit behind them. `--surface full` shows all 46. There are no MCP prompts. The old prompt contracts are the `get_playbook` tool.

## Quick start

```bash
pip install -r requirements.txt
python mcp_server.py --check        # starts the server, lists the tools, exits
```

Put a PDF, DOCX or TXT resume in your workspace folder (or in `resumes/`), then add the server to your client. Examples for each client are in `docs/mcp-setup/`.

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
- When a search finds nothing, the CEO widens it in steps and then says so. It does not fill the gap.
- Generated text uses only facts the resume supports. `get_evidence` lists them.
- `verify_draft` checks any text against that evidence and flags unsupported claims. `tailor_resume`, `cover_letter` and `prepare_application` run the same check and return the result.
- Tools never accept or return API keys. Optional LLM keys come from environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` and others). Without a key the deterministic engine writes the documents.

## Your data

Everything lives in `<workspace>/.jobhunter/`, which ignores itself in git.

- `engine.db` is the SQLite database: resumes, stored jobs, applications, watchlist, board health.
- `preferences.json` holds your preferences, feeds and career pages.
- `output/` holds adapted resumes, cover letters, interview prep and exports.

Applications live only in SQLite. An old `applications.json` is imported once and renamed.

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
- Only the top five jobs of a search get a live link check. Ask the CEO to recheck one before you apply.
- Several scrapers return an empty list instead of an error when blocked, so `source_health` shows them as ok with zero results.
- Reading some boards (LinkedIn, Indeed, ZipRecruiter and others) uses browser-like requests. See `docs/data-policy.md` and use `disabled_sources` if you do not want that.

## License

MIT. See `LICENSE`.
