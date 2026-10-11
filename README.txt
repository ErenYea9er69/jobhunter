JOBHUNTER 2.0
Resume-first job search with honest resume matching. Runs on your machine. No required dependencies.

RUN IT
  python server.py
  Open http://127.0.0.1:8080
  Python 3.8 or newer. Standard library only.

FIRST USE
  1. Open the Profile tab. Upload a PDF, DOCX, TXT or MD resume, or paste the text.
  2. Read the fields. Anything the parser did not find stays blank and is named in the toast.
  3. Save. Search uses your target title when the search box is empty.
  4. Add companies to the watchlist. The app finds each careers board for you.

WHAT YOU GET
  Search: free feeds, your watched company boards, and Adzuna when you add a key.
  Duplicates merge across sources and different roles at one company stay separate.
  Match score 0 to 100 with a written reason, a point breakdown, and a confidence level.
  Customizing: reorders and respells only. Every number and skill in the output comes from your resume.
  Gap report, cover letter, and interview prep built from your real bullets.
  ATS audit, DOCX export, text PDF export, plain text and HTML.
  Tracker with status history, follow-up dates and funnel statistics.
  Daily digest of roles first seen since the last one.

OPTIONS (environment variables)
  JH_PORT, JH_HOST              server address (default 127.0.0.1:8080)
  JH_DATA_DIR                   where the database lives
  ADZUNA_APP_ID, ADZUNA_APP_KEY free key from developer.adzuna.com for local and non-tech jobs
  ANTHROPIC_API_KEY             turns on the LLM rewrite engine (grounding check still applies)
  JH_LLM_MODEL                  default claude-sonnet-5-5
  JH_DIGEST_TIME=08:00          daily digest time
  JH_SMTP_HOST, JH_SMTP_PORT, JH_SMTP_USER, JH_SMTP_PASSWORD   email delivery
  JH_DEMO=1                     load a sample profile and labeled sample jobs
  JH_SEARCH_DEADLINE            seconds before slow sources are skipped (default 20)

OPTIONAL PACKAGES
  pip install pypdf             stronger PDF reading

TESTS
  python tests/test_jobhunter.py

PRIVACY
  Your data stays in data/jobhunter.db. The Purge button deletes every table and compacts the file.
  The only outbound calls go to the job sources you enable and, if you set a key, the Anthropic API.

LAYOUT
  server.py        entry point
  jh/              backend modules (sources, pipeline, scoring, dedup, refit, ats, parser, exporters, tracker, digest, httpd)
  static/          browser app
  tests/           unit tests
  docs/ANALYSIS.txt  the full pipeline analysis, weaknesses, and what changed
