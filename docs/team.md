# The team

JobHunter works like a small company. You talk to one AI. That AI is the CEO. The CEO briefs the employees, and a Reviewer checks every result before you see it.

```
You  ->  AI (the CEO)  ->  ceo_run
                              |
        +----------+----------+----------+----------+
      Scout     Analyst     Writer     Coach       Ops
        |          |          |          |          |
        +----------+-----+----+----------+----------+
                         |
                     Reviewer  (can block any work)
                         |
                  brief to you (report and data behind it)
```

## Why it is built this way

Language models make things up. In a job search that costs you: a dead link, a skill you do not have on a resume, a made-up employer in a letter, a scam posting, a posting that tries to give your AI orders. The design puts a checker between the work and you, and the checker does not trust the worker. `docs/evals.md` shows how well the checker does and how that was measured.

## The employees

| Employee | Owns | Job |
| --- | --- | --- |
| CEO | `ceo_*` tools | Reads the request, writes a directive for each employee, reports. The AI you chat with plays this role. |
| Head of Talent Scouting | `search_jobs`, `add_job_source`, `discover_job_source`, `get_saved_jobs` and 6 more | Finds jobs. Reaches small and regional employers. |
| Market Analyst | `score_job`, `gap_report`, `ats_audit`, `compare_resumes` | Measures fit and finds real gaps. |
| Document Writer | `tailor_resume`, `cover_letter`, `prepare_application`, `export_resume` and 3 more | Writes documents from resume facts only. |
| Interview Coach | `interview_prep`, `evaluate_mock_interview`, `skill_roadmap` | Prepares interviews and plans skills. |
| Chief of Staff | `scan_resumes`, `set_preferences`, `track_application`, `update_application` and 10 more | Keeps records and the tracker. |
| Reviewer | `verify_draft`, `get_evidence` and the checks below | Checks everything. Can block any work. |

Every tool belongs to exactly one employee. `ceo_team` shows the list. A test fails if a tool has no owner.

## What the client's AI sees

`python mcp_server.py` shows seven tools. These are the only way in.

| Tool | Use |
| --- | --- |
| `ceo_run` | Any request. Plans, delegates, reviews, reports. |
| `ceo_plan` | Preview what the CEO would do. Nothing runs. |
| `ceo_delegate` | Send one task to one employee. The result is reviewed. Scams and injected postings are removed from job lists. |
| `ceo_submit_work` | Hand in a draft the AI wrote from a work order. |
| `ceo_recheck` | Check a job (live), a draft, or a whole earlier mission again. |
| `ceo_status` | Past missions, the Reviewer's record, and `forget` to delete missions. |
| `ceo_team` | The roster and each role prompt. |

`python mcp_server.py --surface full` (or `JH_SURFACE=full`) shows all 46 tools. The hidden tools still run. The CEO calls them.

## What it can do

| Say | Intent | What happens |
| --- | --- | --- |
| "find backend engineer jobs in Tunisia" | hunt | Search, rank, review, read the top posting pages, reflect. |
| "find small companies hiring python developers in Sfax" | hunt (small) | Same, with a bias toward small and regional sources. If regional boards return nothing, the Scout finds out why. |
| "show my saved jobs", "what is new" | saved | Stored jobs, reviewed, marked as not re-read live. |
| "write a cover letter for the second one" | apply | Writer drafts, Reviewer checks every line. |
| "why is the fit low for the Adyen job" | explain | Score breakdown, audited matched skills, real gaps. |
| "interview prep for the Nova job" | interview | Coach builds questions and stories from the resume. |
| "message the recruiter at Adyen" | outreach | Writer drafts, Reviewer checks. |
| "what skills should I learn" | skills | Coach ranks gaps from stored jobs. |
| "I applied to Adyen", "Nova invited me to interview" | track | Tracker updated, then read back to confirm. |
| "not interested in banks", "never show Globex again" | feedback | Exclusions saved, then read back to confirm. |
| "export my resume as pdf" | export | Resume saved as a file. |
| "what is my status today" | status | Funnel and overdue follow-ups. |
| "is job `<id>` still open" | recheck | Live page and every job check again. |
| "I want to work in Tunisia and France" | setup | Preferences saved. |

Requests are read in English and French, with a few Arabic words.

### Two ways the AI can make this exact

- **`hints.intent`**: the AI knows what the client means better than any rule. It passes the intent (one or more of setup, hunt, saved, apply, explain, interview, outreach, skills, track, feedback, export, status, recheck, help). The rule-based router is only the fallback.
- **`hints.reference`**: when the client points ("the second one", "the Adyen job"), the CEO resolves it against the last list it showed, then the tracker, then stored jobs. If two jobs fit, it asks. It never picks one silently.

A request that matches nothing becomes `unclear`: the CEO asks which of the known actions the client wants, with an example for each.

## What happens on a request

1. The intent comes from `hints.intent` or the router. The router never guesses a job id.
2. For each step the CEO writes a directive (objective, inputs, limits, definition of done) and runs the employee's tool.
3. A failed step is retried once. An empty search is widened in steps: no score floor and any company size, then any location in your target countries, then a fresh read if no source answered at all. The report lists every attempt. If nothing comes back, the report says so and shows no jobs.
4. The shortlist is ranked before it is checked, so the live checks cover the jobs the client sees first. No single source may fill more than 40% of the list while others have jobs. Small-employer mode favours small and regional sources.
5. The Reviewer checks each result.
6. The CEO reflects on the whole result and writes findings from its numbers, each with a next move ("no job fits strongly: the best is 38 of 100. Learning Kubernetes would help most"). A weak search triggers the Coach's skill roadmap on its own.
7. The answer has two forms: a short `brief` for the client and the full `report` and data as the audit trail. Every job and document carries the call that made it (`provenance`).

### Time budget

A client usually gives up on a tool after about a minute. Each mission has a budget (`hints.budget_s`, default 50 seconds). The CEO stops widening a search, skips live checks and skips gap reports when time runs short. It says which, under `notes` and `not_verified`. `elapsed_s` is in the result.

## What the Reviewer checks

Jobs:
- A real title, an employer, and an apply link that passes the outbound network policy.
- **Scams.** An upfront fee, a deposit, a cheque-and-wire request, untraceable payment (gift cards, Western Union), or a request for passport or bank details blocks the job. Chat-app-only contact, "earn $500 a day", "no experience needed" and "start today" each warn, and two together block. "We never charge any fee" does not trigger any of this.
- **Prompt injection.** Posting text written for an AI reader ("ignore previous instructions", "note to AI assistants", "dear AI model") in a title, company or location blocks the job. In a description it warns. All web text in the report is made one line, bounded, free of hidden characters.
- **Links.** URL shorteners, unusual domain endings (`.xyz`, `.top`) and look-alike domains warn.
- A plausible date, the location against your target countries (remote is exempt), duplicates, implausible salary, ghost-job signs.
- Matched skills must be on your resume and in the posting. A high fit score with no matched skills is flagged.

Live links (the top five jobs of a search, and always the one job you apply to):
- HTTP 404 or 410, an expired `validThrough` date in the page's job data, or "no longer available" in the visible text (English, French, German, Arabic) removes the job.
- Text inside scripts is ignored. A site that blocks checks (403, 429, 999) or a page that loads with scripts is "not confirmed", never removed on that evidence.

Documents (resume, cover letter, screening answers, recruiter messages), sentence by sentence:
- **Employers.** "At Google I led ..." needs Google on the resume. Saying you worked at the employer you are applying to is blocked.
- **Titles and leadership.** "As Engineering Manager" needs those words on the resume. "I led / managed" needs leadership on the resume.
- **Degrees.** The level (bachelor, master, PhD) and the school must match the resume.
- **Skills.** A skill stated as experience must be on the resume. "I am ready to learn Terraform" is fine. In a resume every listed skill must be on the profile.
- **Numbers.** A number must be on the resume. Years of experience must be close to the resume's total. "A decade" counts as 10.
- **Credentials.** Certifications, awards, talks, publications, security clearance, founding or acquisition.
- **Personal status.** Languages, citizenship and work authorization cannot be proven, so they warn.
- **Employer facts.** "I admire Adyen's 2024 acquisition" is a warning unless the posting says so.
- Resume header lines are checked against the profile: employer, title, start year, degree. Placeholders such as `[Company Name]` block.
- Contact lines and date ranges are handled so they are not misread as claims.
- **Style.** Machine-sounding patterns (stock openers like "I am excited to", hype, vague power verbs, the "not just X, but Y" frame, dashes, emoji in a form) are reported as a `robotic_style` warning that quotes each phrase and says what to write instead. It never blocks, because a genuine sentence can contain a flagged word. The rules and their reasons are in `docs/prompts.md`.

What happens to a blocked draft: unsupported sentences are removed and the rest is checked again. If removal would delete more than a third of the draft, the draft is rejected, not patched, because what is left would no longer be what was written.

Approved text is saved to `.jobhunter/output/approved/`.

The Reviewer fails closed. If a document check crashes, the document is blocked. If a job check crashes, the job gets a warning that it was not reviewed.

Changes to your data are read back. "I applied to Adyen" and "not interested in banks" are reported as done only after the CEO reads the tracker or the preferences and finds the change.

## What the team does not check

The report lists these under `not_verified`:
- Interview stories (checked for tool errors only).
- Facts about the employer beyond the posting. A warning is raised, but the Reviewer cannot know the truth.
- Job links beyond the first five of a search.
- Anything the rules do not model. The Reviewer is rules, not a model. It catches what language models tend to invent, and `docs/evals.md` says how well. A new kind of fabrication can get through.

## Work orders

A document the deterministic engine writes is plain. When no model key is configured, `ceo_run` adds a work order for the cover letter. It holds a prompt (the Writer's role prompt, the directive, the playbook) and the candidate facts. The client's AI may write a better letter and send it with `ceo_submit_work`. The Reviewer approves it, removes unsupported sentences, or rejects it. The engine's draft stays as the fallback. Pass `hints.polish=false` to skip work orders.

## Tune the prompts

Role prompts are files in `prompts/team/`. The playbooks the Writer and Coach follow are in `prompts/`, and the shared style guide is `prompts/voice.md`. Put a file with the same name in `<workspace>/prompts/team/` to replace one. `ceo_team(with_prompts=true)` shows what is in use.

## Privacy

Missions are stored in `engine.db` on your computer, with the request and the result, including drafts. The newest 200 are kept. `ceo_status(mission_id="all", forget=true)` deletes them all.
