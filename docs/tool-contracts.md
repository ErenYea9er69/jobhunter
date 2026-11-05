# Tool contracts

## Envelope

Every tool returns this object.

```json
{
  "status": "ok | partial | error",
  "success": true,
  "data": {},
  "warnings": [],
  "sources": [],
  "error": {"code": "not_found", "message": "...", "hint": "..."},
  "correlation_id": "a1b2c3d4e5f6",
  "schema_version": "1.1",
  "generated_at": "2026-11-03T10:00:00Z"
}
```

- `status` is `partial` when some sources failed. `error` appears only when `status` is `error`.
- Error codes: `invalid_input`, `not_found`, `no_resume`, `forbidden`, `unreachable`, `empty`, `internal_error`.
- Results larger than 150 KB add a warning. Search results are compact cards, and `get_job_details` returns one full record.

## Job card

`job_id`, `title`, `company`, `location`, `work_mode`, `job_type`, `seniority`, `salary`, `fit_score`, `opportunity_score`, `posted`, `freshness`, `apply_url`, `sources`, `direct_from_employer`, `is_new`, `matched_skills`, `missing_skills`, `why`.

Pass `job_id` to `get_job_details`, `score_job`, `gap_report`, `ats_audit`, `tailor_resume`, `cover_letter`, `interview_prep`, `outreach_message`, `prepare_application`, `track_application` and `get_playbook`. Where a tool also accepts `job_title`, `company` and `description`, you paste a job found elsewhere.

## Resources

`jobhunter://resumes`, `jobhunter://resumes/{name}`, `jobhunter://applications`, `jobhunter://jobs/latest`, `jobhunter://preferences`, `jobhunter://sources`, `jobhunter://evidence/{name}`. Each has a tool with the same data, for clients without resource support. Resources never contain secrets.

## Tools

An asterisk marks a required argument.

### Resumes

- `scan_resumes`: Find resume files (PDF, DOCX, TXT) in the workspace, parse them, and make them available as resume variants.
  Arguments: subpath

- `list_resumes`: List resume variants with target role, skill count and which one is active.
  Arguments: none

- `get_resume`: Return a parsed resume (contact, skills, experience, education). Personal preferences are applied on top.
  Arguments: name

- `set_active_resume`: Choose which resume variant searches and scoring use.
  Arguments: name*

- `parse_resume_file`: Parse one resume file into a profile without saving it.
  Arguments: path*


### Preferences and sources

- `get_preferences`: Show your personal search preferences and which sources they enable.
  Arguments: none

- `set_preferences`: Change personal search preferences. Only the keys you pass change.
  Arguments: updates*, merge_lists

- `list_job_sources`: List every job source with where it works, whether it runs for you, plus your watched companies, feeds and career pages.
  Arguments: none

- `add_job_source`: Add a place to look for jobs: a company, a feed, a company career page, or a small job site. A site that forbids robots in robots.txt is refused, even with force.
  Arguments: kind*, value*, name, target_role, force

- `discover_job_source`: Find out how a website's jobs can be read: ATS board, feed, sitemap or schema.org job data. Adds nothing.
  Arguments: url*

- `remove_job_source`: Remove a watched company, custom feed, career page or site.
  Arguments: kind*, value*

- `source_health`: Show how each source did in the last search: results, errors, paused sources, and company board coverage.
  Arguments: none


### Finding jobs

- `search_jobs`: Search every enabled source for your region and return compact job cards ranked by fit.
  Arguments: query, location, work_mode, min_score, limit, company_focus, refresh

- `get_saved_jobs`: Query jobs already found by earlier searches, without any network call. Returns compact cards.
  Arguments: category, seniority, work_mode, min_score, sort, limit

- `get_job_details`: Return the full record of one job: description, requirements, salary, contacts, fit breakdown and apply link.
  Arguments: job_id, job_title, company, url, description, full_description

- `get_recommendations`: Top matches for your resume and preferences with no query needed. Uses stored jobs first.
  Arguments: limit


### Analysis

- `score_job`: Score how well your resume fits one job (0 to 100) with the full breakdown and matched or missing skills.
  Arguments: job_id, job_title, company, description, salary, location, resume_name

- `gap_report`: List which skills the job wants that your resume lacks, which are real gaps, and which you could add truthfully.
  Arguments: job_id, job_title, company, description, resume_name

- `ats_audit`: Check how an applicant tracking system would read your resume for this job: keyword coverage, format risks, fixes.
  Arguments: job_id, job_title, company, description, resume_name

- `compare_resumes`: Rank all your resume variants against one job and say which one to send.
  Arguments: job_id, job_title, company, description

- `skill_roadmap`: Rank the skills worth learning next, by how many of your saved top jobs ask for them and you lack them.
  Arguments: job_id, resume_name, top_jobs


### Documents

- `tailor_resume`: Tailor your resume to a job without inventing facts. Reorders and rewords real content, then checks it against your evidence.
  Arguments: job_id, job_title, company, description, archetype, resume_name, save

- `cover_letter`: Write a short cover letter from your real experience, then check every claim against your evidence.
  Arguments: job_id, job_title, company, description, tone, angle, resume_name, format

- `solve_screening_questions`: Draft honest answers to application screening questions from your real resume facts. Unknowns are flagged, not invented.
  Arguments: questions*, job_id, job_title, company, description, resume_name

- `prepare_application`: One call that prepares an application: tailored resume, cover letter, recruiter message, interview prep, and a tracker entry.
  Arguments: job_id, job_title, company, description, archetype, resume_name, track

- `verify_draft`: Check text you or the model wrote (resume bullets, cover letter, answers) against your real resume evidence.
  Arguments: text*, resume_name, job_id

- `get_evidence`: List the facts extracted from your resume (employers, dates, skills, metrics). Generated documents may only use these.
  Arguments: resume_name, claim_type, limit

- `export_resume`: Export a resume to TXT, HTML, DOCX or PDF in .jobhunter/output/reports.
  Arguments: format, resume_name


### Interview and outreach

- `interview_prep`: Build interview prep for one job: likely questions, STAR stories from your real experience, and gaps to prepare for.
  Arguments: job_id, job_title, company, description, resume_name

- `outreach_message`: Draft a recruiter or hiring-manager message (LinkedIn note, email, follow-up) from your real experience.
  Arguments: job_id, job_title, company, description, message_type, resume_name

- `evaluate_mock_interview`: Score a practice interview answer on ownership, metrics, technical depth and clarity, with a coached rewrite.
  Arguments: question*, candidate_answer*, role_level, rubric

- `follow_up_message`: Draft a follow-up message for a tracked application.
  Arguments: app_id*, action_type, notes, resume_name


### Playbooks

- `get_playbook`: Get the writing instructions for a task plus the facts to write from, so the model can draft grounded text itself.
  Arguments: task*, job_id, job_title, company, description, resume_name, app_id


### Tracking

- `track_application`: Record an application. With a job_id the details are filled from the stored job. A repeat of the same job updates it.
  Arguments: company, title, status, url, notes, follow_up_date, job_id

- `list_applications`: List tracked applications with days in stage and overdue follow-ups.
  Arguments: status

- `update_application`: Change an application's stage, notes or follow-up date.
  Arguments: id*, status, notes, follow_up_date

- `application_stats`: Funnel numbers: how many reached each stage, conversion rates, and overdue follow-ups.
  Arguments: none

- `daily_digest`: What needs attention today: new matching jobs since the last digest, overdue follow-ups, upcoming interviews, next actions.
  Arguments: limit, mark_seen


### CEO tools

The default surface. Details in `docs/team.md`.

- `ceo_run`: Any request. Plans, delegates, reviews, reports.
  Arguments: request*, hints (intent, reference, role, location, country, job_id, work_mode, limit, min_score, company_focus, small_employers, verify_live, polish, track, archetype, text, kind, preferences, add_sources, status, title, exclude, exclude_companies, format, budget_s). hints may also be a JSON string.
  Result data: mission_id, status (done, partial, needs_input, blocked), headline, brief (relay this), insights, elapsed_s, report (the audit trail), team, jobs, removed_by_reviewer, documents, decisions_needed, not_verified, blocked, notes, work_orders, next_steps, summary (coverage, review_stats, explain, intent_menu), relay_rules

- `ceo_plan`: Preview what the CEO would do. Nothing runs.
  Arguments: request*, hints

- `ceo_delegate`: Send one task to one employee. The result is reviewed.
  Arguments: tool*, arguments, employee

- `ceo_submit_work`: Hand in a draft written from a work order. Returns approved, verdict, the final text, removed lines.
  Arguments: mission_id*, task*, text*, job_id, kind

- `ceo_recheck`: Check a job (reads the live page), a draft, or an earlier mission again.
  Arguments: job_id, text, mission_id, kind

- `ceo_status`: Recent missions, the Reviewer's record (jobs checked and removed, scams and injections blocked, links live and dead, documents approved and rejected), or one mission in full. With forget=true it deletes one mission, or all with mission_id="all".
  Arguments: mission_id, forget

- `ceo_team`: The roster, the tools each employee owns, and optionally the role prompts.
  Arguments: with_prompts

### Server

- `configure`: Show or change the few server settings that are safe to change from chat. Secrets are never accepted.
  Arguments: key, value
