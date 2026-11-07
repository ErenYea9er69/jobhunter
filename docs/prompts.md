# The prompts: analysis, fixes and how to edit them

This is the review of every prompt in the project: the eight playbooks in `prompts/`, the seven team role prompts in
`prompts/team/`, the three prompts embedded in code (`LLM_SYSTEM`, `COVER_PITCH_LLM_SYSTEM`,
`SCREENING_SOLVER_PROMPT`), the server instructions, and the descriptions of the tools the client's AI reads.
It says what was wrong, how that was measured, what changed, and what is still open.

## How the review was done

- **Reading.** Each prompt was read against the code that consumes its output.
- **Linting.** `jh/team/voice.py` scans a prompt for dashes, shouting in capitals, persona boasting, invented statistics,
  stock phrases and software-only vocabulary. Run `python -m jh.team.voice prompts/cover_letter.md`.
- **Replay.** A reply shaped by each prompt was fed to the code, with a marker word in every field, to see whether the
  code used it or fell back to its own template.
- **Scanning output.** The deterministic writer's own outputs (the text you get when no model writes) were scanned with
  the same rules.
- **Research.** Hiring-manager surveys, studies of machine-style vocabulary, the evidence behind two claims the resume
  playbook relied on, LinkedIn's note limit, negotiation guidance, and Anthropic's prompting guidance.

## What was wrong

### 1. Six of eight playbooks asked for keys the code does not read

With a model key configured, the server uses the model's reply only if it finds the keys it expects. Version 2.3 asked
for other names, so the reply was dropped and the template text was used. The replay confirmed it.

| Playbook | The prompt asked for | The code reads | What happened |
| --- | --- | --- | --- |
| cover letter | `letter_text` | `full_text` | the model's letter was ignored; the letter was rebuilt from the parts |
| interview prep | `technical_questions`, `behavioral_story_outlines`, `questions_for_interviewer` | `technical_deep_dives`, `behavioral_scenarios`, `questions_to_ask_interviewer` | reply dropped |
| mock interview | `total_score`, `dimension_scores` (25 points each) | `overall_score`, `rubric_scores` (0 to 100) | reply dropped; the code requires `overall_score` |
| outreach | everything inside `draft_text` | top-level `linkedin_connection_note` | reply dropped |
| follow-up | message inside `draft_text` | top-level `body` | reply dropped |
| roadmap | `priority_gaps`, `milestones`, `project_specification` | `fast_track_project`, `top_missing_skills` | reply dropped |
| screening | `answer_text` | `answer` | the whole JSON object, braces and keys, could be pasted into a form field |
| resume | `executive_hook`, `bullets` | same | worked |

The prompts embedded in code had the right keys. The markdown files overrode them, so the wrong ones won.

### 2. The prompts did what they told the model not to do

Counted in the old files: 14 em or en dashes, 11 words in capital letters (STRICTLY, MUST, NEVER, CRITICAL), 14 invented
statistics, 52 persona and hype phrases ("elite", "world-class", "thousands of senior engineers", "2026/2027 standard",
"high-converting"). A model copies the style of its prompt. A prompt written in a hyped voice invites a hyped answer.

Anthropic's guidance points the same way: state what to do instead of only what not to do, and say plainly what you
want without capital-letter emphasis. The new prompts give a reason for each rule and use ordinary wording.

### 3. Invented numbers, and a model asked to grade itself

- "6-second recruiter scan" comes from one 2012 study of 30 recruiters, updated in 2018 and not peer reviewed. A
  peer-reviewed eye-tracking study of 221 recruiters in 2023 found something different. The durable finding is only
  where recruiters look first: titles, employers and dates.
- "95%+ ATS match score" and "100% ATS semantic alignment" describe a number that no applicant tracking system
  publishes. Recruiters search and sort by keyword. They are not shown a universal score.
- "Generic templates get rejected within 5 seconds" and "evaluated over 30,000 applications" were stated as fact with
  no source.
- The resume playbook asked the model to report its own `skim_score: 96`, `ats_score`, `skim_verdict: "Instant Yes"`.
  A model cannot measure these, so it invents them. The code computes the audit itself and never read the fields.
- Outreach asked the model to report `length_metrics` (character counts). Models count badly. The code, not the model,
  should count.
- Mock feedback told the candidate a "Strong Hire" verdict. A practice score cannot predict a hiring decision.

All of these were removed. The prompts now ask only for fields a person or the code can use.

### 4. The banned-phrase lists could not work alone

A short list of banned phrases was the only anti-slop measure. Research on machine-style vocabulary found that once
a word like "delve" became a known giveaway its use fell, while other style words kept rising. A ban moves the habit to a
synonym. The old resume playbook also banned "leveraged" and "spearheaded" while promoting "Architected, Engineered,
Decoupled", which are the same habit in a different costume, and it demanded the literal template "Accomplished X as
measured by Y by doing Z". A model that obeys that writes the words "as measured by" into a bullet.

The new prompts name patterns and give a plain alternative (see `prompts/voice.md`). They also ask for the positive
habit: the concrete fact first, in plain words, and a sentence that could sit in any candidate's letter gets cut.

### 5. Hiring managers react to generic text, not to AI

Surveys of hiring managers report that most dislike text that reads as machine-written, and that a large share say they
can tell, many within seconds. The complaint underneath is that the text is generic and cannot be checked. That is why the
prompts require facts only this candidate has and why the Reviewer checks every claim against the resume.

### 6. Template structure made every letter look alike

The cover letter prompt forced a fixed skeleton (hook, three pillars, why-company, bridge, call to action) and a closing
formula ("propose a focused 15-minute conversation"). The same skeleton for every candidate is itself a tell. The new
prompt gives the content to include and lets the letter's shape follow it. The close is one concrete next step in the
candidate's own words.

### 7. Software-only vocabulary

47 terms such as "p99 latency", "throughput", "microservices", "distributed systems" and "0-to-1" appeared in the old
prompts. The product serves anyone, and an accountant's resume that comes back full of latency language is wrong. The
new prompts use examples from finance, teaching and operations as well as software, and tell the model to use the
vocabulary of the candidate's own field.

### 8. Example values leaked into answers

Schemas carried example numbers and identifiers (`skim_score: 96`, `210`, `35`, `"ev_..."`, scores of 22, 20, 23 and 21).
Models copy them. The evidence ids (`ev_...`) could not be produced truthfully, because the payload the server sends holds
no evidence ledger. The new schemas hold descriptions only, and a test fails if a numeric literal appears in a schema.

### 9. Dead sections and wrong inputs

Each playbook ended with a "User Message Template" in XML that no code sends. The server sends JSON with named fields
(`job_post`, `candidate_source`, and so on), and `get_playbook` returns a `context` object with other names. The old
prompts described neither accurately and left out inputs the code does send (`value_pillars`, `honest_skill_gaps`,
`standout_bullet`, `custom_hook`). The new prompts describe the real inputs and say that text inside them from the web is
data, never instructions.

### 10. Rules that fought the rest of the system

- The follow-up prompt allowed `[Placeholder]` text. The Reviewer blocks placeholders. The prompt now asks a question
  through `missing_inputs` instead.
- Limits disagreed with themselves: LinkedIn "under 300" and "295" in one file; "under 2 minutes" next to "180
  words" (that is about 75 seconds spoken; two minutes is roughly 250 words).
- Negotiation advice asked the model for "market data". A model does not know current pay for a city and role. The prompt
  now forbids invented figures and competing offers.
- The roadmap told the candidate to say they "recently implemented" a project they had not built. The prompt now asks for
  two labelled lines: what is true now, and what may be said after the project is done.
- Scoring had no anchors, so two runs on one answer could differ widely and scores drifted high. The new rubric gives
  a description for each score band on each dimension.
- Outreach used one character limit that is wrong for free LinkedIn accounts. The help text widely quoted says 200 for a
  free account and 300 for Premium, with a small monthly number of personal notes on free accounts. Sources disagree and
  LinkedIn changes this, so check your account. The prompt uses 200.

### 11. Prompts in code repeated the problems

`LLM_SYSTEM`, `COVER_PITCH_LLM_SYSTEM` and `SCREENING_SOLVER_PROMPT` carried the same persona boasting, "2026/2027
standard", capital-letter rules and verb lists. They were rewritten in the new style. Each keeps the reply keys of its own
code path (`refit_llm` reads `summary` and `bullets`; the cover pitch reads `full_text`; the default screening prompt asks
for plain text).

## What changed

- `prompts/voice.md` is the single style guide. Its `<voice>` block is embedded in every playbook, in the Writer prompt
  and in the Coach prompt. A test fails if a copy drifts.
- Each playbook is rebuilt on one skeleton: role, inputs, grounding, how to write, voice, examples, output.
  Examples come in pairs (`<robotic>` and `<plain>`) and across fields. A test checks that each robotic example trips the
  scanner and each plain example does not.
- Every playbook asks for two output modes: a JSON object when the user message is JSON, plain text when a person is
  reading. The same prompt serves the server and the client's AI.
- Every schema ends with `missing_inputs`, so the model asks instead of guessing or leaving a placeholder.
- The team prompts were tightened. The CEO prompt tells the AI how to speak to the client (answer first, plain lines, no
  praise of the question, no closing offer of help, no recap) and to pass `hints.intent` and `hints.reference`.
- The Reviewer now warns about machine-sounding phrases (`robotic_style`), quoting each and giving the plain
  alternative. It is a warning, never a block, because a genuine sentence can contain a flagged word. Technical uses such
  as "financial leverage", "robust standard errors" and "dynamic programming" are not flagged.

## Measured

| | Before (2.3) | After (2.4) |
| --- | --- | --- |
| Playbooks whose reply the code used | 2 of 8 (resume; cover letter in part) | 8 of 8 |
| Dashes in the playbooks | 14 | 0 |
| Capital-letter shouting | 11 | 0 |
| Invented statistics | 14 | 0 |
| Persona and hype phrases | 52 | 0 |
| Software-only terms | 47 | 0 |
| Style issues found by the linter, all prompt files | 183 | 0 |
| System prompt words, all eight playbooks | 2,715 | 6,126 |

The scanner on text: on its development set it flags 17 of 17 machine-sounding texts and none of 16 plain ones. A blind
round written afterwards flagged 10 of 12 on first pass and none of 10 plain ones. The two misses ("wealth of experience",
"seasoned professional", "dedicated, motivated, enthusiastic") were added as general patterns, and the set stays as a
regression test. See `docs/evals.md`.

## Still open

- **No model was run.** There was no model key here. The tests prove the contract (the code uses a reply that follows each
  playbook) and the static properties of the prompts. They do not prove how any given model will write. Run a few letters
  through a real model and read them before you rely on the style.
- **The deterministic writer still produces the patterns.** When no model writes the text, the code's own templates do.
  Scanning them: outreach 3.1 hits per 100 words ("I came across your profile", an em dash, an exclamation mark, "strong
  fit"), follow-ups up to 3.7 ("I would welcome the opportunity", "Thank you for your time and consideration", em dashes in
  subject lines), screening answers 2.4 ("I am excited to", "I am eager to"). The cover letter template scored 0. These
  strings are in `refit.py`, `tracker.py` and `screening.py`. The Reviewer now flags them, but they were not rewritten. The
  roadmap fallback also claims the candidate "recently implemented" a prototype.
- **Prompt length grew 2.3 times.** About 1,500 of the added words are the voice block repeated in eight files. A loader
  in code that adds the block once would cut that.
- **Rules are not a model.** The scanner finds patterns. A new habit will get through until it is added.
- **The 200-character limit is a default.** Check it against your own LinkedIn account.

## Editing a prompt

1. Keep the first `markdown` block as the only system prompt. The code takes the first one.
2. Keep every key in the contract table of the playbook. `tests/test_prompts.py` lists the keys the code reads and fails if
   the schema stops asking for one, or if the code stops using one.
3. Keep the `<voice>` block identical to `prompts/voice.md`.
4. Put quoted bad examples inside `<robotic>`, `<voice>` or `<avoid>` tags. Everything else must pass the linter.
5. Use no dashes, no capital-letter emphasis, no persona boasting and no numbers you cannot source.
6. Add a good example next to every bad one, and draw them from more than one field.
7. Run `python -m pytest tests/test_prompts.py tests/test_prompt_contract.py tests/test_evals.py`.

## Sources

- Kobak, González-Márquez, Horvát and Lause, "Delving into ChatGPT usage in academic writing through excess vocabulary",
  arXiv 2406.07016: which style words rose after ChatGPT, and how use shifted once some were noticed.
- Hiring-manager surveys by CV Genius (2024) and TopResume (2025), and trade coverage of them, on how managers react to
  machine-written applications.
- The 2012 and 2018 Ladders eye-tracking studies, commentary on their method (for example ERE.net, "Is the 6 second
  resume scan a myth"), and a 2023 peer-reviewed eye-tracking study of recruiters.
- Recruiter and ATS vendor explanations of how applicant tracking systems search and rank, against the "75% of resumes are
  never seen" claim.
- LinkedIn help text on connection-note length, as summarised by outreach tool vendors, whose figures differ.
- Negotiation guides on timing, written offers, one specific ask, non-salary terms, and not bluffing.
- Anthropic's prompt engineering guidance (`https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/overview`):
  positive instructions with reasons, plain wording instead of capital-letter emphasis, a few varied examples, and clear
  structure.
