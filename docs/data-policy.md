# Data, privacy and network policy

## Local first

- Resumes, jobs, applications, preferences and generated documents stay in `<workspace>/.jobhunter/`. The folder ignores itself in git.
- JobHunter sends no resume text to any server. Two exceptions exist, both optional: an LLM provider you configure through an environment variable receives the text it is asked to rewrite, and each job site receives the search terms and location you search for.
- Deleting `engine.db` removes resumes' parsed copies, stored jobs, applications, the watchlist and board health. Keep a copy if you track applications.

## Secrets

- API keys come from environment variables only.
- No tool accepts a key and no tool or resource returns one. `configure` and `source_health` report only whether a key is present.

## Outbound requests

`jh/source_policy.py` applies to every request made through the shared HTTP client, to page enrichment, and to every redirect.

- Only `http` and `https`.
- No `localhost`, `.local`, `.internal` or single-label host names.
- No private, loopback, link-local, carrier-grade NAT, multicast or reserved address.
- DNS is resolved before the request. A public name that points at a blocked address is refused.
- User-supplied feed and career-page URLs pass the same check when you add them and when they are fetched.

Residual risk: the check resolves a name once and the client resolves it again, so a hostile DNS server might answer differently the second time (DNS rebinding). For a single-user local tool this is accepted.

There is no domain allowlist. Job postings link to thousands of employer sites, so an allowlist would break enrichment. Earlier documentation described an allowlist that the code never enforced.

## How sites are read

- Public APIs and feeds: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio, Teamtailor, BambooHR, Breezy, Remotive, Jobicy, Himalayas, Working Nomads, The Muse, Arbeitnow, Arbeitsagentur, Hacker News, Pinpoint, Jooble (key), JobTech (Sweden), RSS and JSON feeds you add.
- Missions: each request and its result, including drafts, are stored in `engine.db` on your computer. The newest 200 are kept. `ceo_status(mission_id="all", forget=true)` deletes them. Nothing is sent anywhere.
- Site reader (Regional Boards, Job Sites, `discover_job_source`): reads a site's own job pages. It fetches `robots.txt` first and does not read a page that file forbids. It reads at most 25 job pages per site per search, with a quarter-second pause between requests to one host, and sends no cookies or login. The Reviewer's link check reads one posting page per job, for the top five jobs of a search.
- Public web pages: LinkedIn guest search, Indeed, ZipRecruiter, Bayt, Naukri, HelloWork. These are read with browser-like requests, and Indeed and ZipRecruiter use TLS impersonation to pass bot checks. Their terms of use might forbid automated reading. You are responsible for that choice. Turn any of them off with `set_preferences({"disabled_sources": ["LinkedIn", "Indeed"]})`.
- Failing sources are paused by a circuit breaker after repeated errors. HTTP 429 and 5xx responses are retried at most once.
- JobHunter does not log in anywhere, does not apply to jobs for you, and does not send messages.

## Retention

- Stored jobs: replaced by each search. Search cache: 15 minutes. Stale results are used for up to 24 hours when a source is down, and are marked stale.
- Applications, preferences, the watchlist and board health stay until you remove them.
