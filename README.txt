JOBHUNTER 2.0
Resume-first multi-board job acquisition engine with non-hallucinatory AI tailoring.
Runs 100% on your local machine with local SQLite. Zero required dependencies.

RUN IT
  python server.py
  Open http://127.0.0.1:8080
  Python 3.8 or newer. Standard library only (curl_cffi optional for enhanced bot-bypass).

FIRST USE
  1. Open the Profile tab. Upload a PDF, DOCX, TXT, or MD resume, or paste raw text.
  2. Review extracted fields. Anything the parser did not find stays blank for you to edit.
  3. Save. Search uses your target title and skills automatically.
  4. Track dream companies on the Watchlist; JobHunter monitors their career boards directly.

WHAT YOU GET
  - Multi-Board Search: Direct ATS (Greenhouse, Lever, Ashby, SmartRecruiters, Workable),
    Y Combinator, LinkedIn Guest API, Indeed, ZipRecruiter, Bayt, Naukri, HelloWork,
    Himalayas, Adzuna, and HN Hiring.
  - Cost Transparency: 100% Free sources always outrank paid/gated feeds with explicit paywall notes.
  - Native LinkedIn Engine: Chrome TLS fingerprint impersonation, step-25 pagination,
    minute-precision post age ("18m ago"), direct company URLs, and Easy Apply support.
  - Automated LinkedIn Radar: Background daemon checks fresh streams, rotates skill slices,
    and backfills catalogs on an adaptive schedule.
  - Deduplication: Merges identical postings across sources; direct ATS links prioritized.
  - 0-100 Match Score: Clear fit breakdown, matched skills, missing requirements, and opportunity rank.
  - Non-Hallucinatory Tailoring: Side-by-side diff reorders and rephrases using only verified facts.
  - Multi-Provider AI: Works with Claude, GPT-4o, Gemini, local Ollama, or deterministic rule engine.
  - Skill Gap Report: "Add This If True" quick-adds vs "Real Architectural Gaps" with talking tracks.
  - Interview Prep Studio: Role-specific STAR behavioral questions and technical deep dives.
  - Kanban Tracker: 5 pipeline stages with follow-up date countdowns and interview notes.
  - Privacy Guarantee: Zero telemetry. Local SQLite database. One-click "Permanently Wipe Data".

CONFIGURATION (Environment Variables)
  JH_PORT, JH_HOST              Server address (default 127.0.0.1:8080)
  JH_DATA_DIR                   Database directory (default ./data)
  JH_LINKEDIN_INCREMENTAL_MIN   Background LinkedIn Radar scan interval (default 10 min, 0=off)
  JH_LINKEDIN_DEPTH             LinkedIn search depth: fast, standard, deep, max
  JH_SEARCH_DEADLINE            Search timeout in seconds (default 35)
  AI_PROVIDER                   auto, gemini, openai, anthropic, ollama, deterministic
  GEMINI_API_KEY                Google Gemini API key
  ANTHROPIC_API_KEY             Anthropic Claude API key
  OPENAI_API_KEY                OpenAI API key
  JH_OLLAMA_ENDPOINT            Local Ollama URL (default http://127.0.0.1:11434)
  ADZUNA_APP_ID, ADZUNA_APP_KEY Free key from developer.adzuna.com for local aggregation
  JH_DIGEST_TIME                Morning digest briefing time (e.g. 08:00)

TESTS
  python -m unittest discover -s tests

LAYOUT
  server.py        Web server entry point
  desktop.py       Desktop window launcher
  jh/              Core backend engine:
                   sources.py  - Direct ATS, LinkedIn, Indeed, and feed scrapers
                   pipeline.py - Search coordination, LinkedIn Radar daemon, scoring
                   scoring.py  - Fit scoring, opportunity ranking, title derivation
                   dedup.py    - Cross-source job merging and canonical keying
                   refit.py    - Non-hallucinatory resume refiner and AI adapters
                   parser.py   - Multi-format resume parser
                   db.py       - SQLite WAL persistence and schema migrations
                   httpd.py    - REST API and static asset router
  public/          Single-page web application (Vanilla HTML, CSS, JS)
  tests/           Automated unit and regression test suite
