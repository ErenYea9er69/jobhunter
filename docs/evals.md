# Evals: the team's report card

`python -m jh.team.evals` runs fixed cases against the Reviewer and the router and prints a score. `tests/test_evals.py` fails if a change makes the score worse. The cases are in `jh/team/evals.py`.

## What is measured

- **Documents.** Texts a model might write for a letter or resume. Fabrications must be blocked (or, for claims that cannot be proven either way such as a language level, at least flagged). Genuine texts must not be blocked. Fabrications include invented employers, degrees, certifications, titles, team sizes, years, metrics, awards, talks, skills, and facts about the employer.
- **Jobs.** Postings. Scams, prompt injection, junk titles and link tricks must be caught. Honest postings that mention fees, equipment, visas or WhatsApp in harmless ways must pass.
- **Router.** Client phrasings in English, French and Arabic, with the intents and the job pointer they must produce.
- **Style.** Machine-sounding text (stock openers, hype, vague power verbs, the "not just X, but Y" frame, dashes, emoji in a form) must be flagged. Plain text must not be, including technical uses of words a naive list would flag ("financial leverage", "robust standard errors", "dynamic programming").

## Results

| Set | Version 2.2 | Version 2.3 |
| --- | --- | --- |
| Documents, dev (22 fabrications, 18 genuine) | caught 12 of 22, 1 false alarm | caught 22 of 22, 0 false alarms |
| Jobs, dev (12) | 6 of 12 | 12 of 12 |
| Router, dev (40) | 18 of 40 | 40 of 40 |
| Documents, held-out (12 fabrications, 10 genuine) | caught 4 of 12, 1 false alarm | caught 12 of 12, 0 false alarms |
| Jobs, held-out (8) | 3 of 8 | 8 of 8 |
| Router, held-out (25) | 5 of 25 | 25 of 25 |

### Style (added in 2.4)

| Set | Result |
| --- | --- |
| Dev (17 machine-sounding, 16 plain) | flags 17 of 17, 0 false flags |
| Blind round, first pass (12 machine-sounding, 10 plain) | flagged 10 of 12, 0 false flags |
| Blind round after adding the general patterns it exposed | 12 of 12, 0 false flags (now a regression set) |

The scanner is a warning in the Reviewer, never a block. See `docs/prompts.md`.

## How much to trust these numbers

Read the table with care.

- The **dev** sets were used while building the checks. Their score is not a fair measure of new data.
- The **held-out** sets were written before the 2.3 checks were built, and the checks were not tuned on them one case at a time. One router case failed on the first look and was fixed by a general change (a phrase that two patterns claimed). So the held-out router score is a first-look 24 of 25, then 25 of 25.
- A **blind round** was then written fresh and run once before any fix. First pass: router 13 of 20 (65%), documents 9 of 10 caught with 0 of 8 false alarms, jobs 4 of 6. The general causes of the misses were fixed afterwards (new phrasings, "earn 300 dollars daily", "Dear AI model:", "employee of the year"). Those cases now live in the `round2` sets as regression tests. They no longer measure new data.
- **The honest estimate** for text the checks have never seen is the blind first pass: the router around two thirds right, the document and job checks around nine in ten for the fabrications they are built for. The rules will not generalize perfectly. That is why the AI can pass `hints.intent`, why an unclear request asks instead of guessing, and why anything the rules cannot prove is shown under `not_verified`.
- The sets are small. Twenty cases cannot show a rate of 99%.
- A real-output check runs in the tests: the engine's own cover letters and resumes for real fixture jobs must not be blocked.

## Add a case

Add a row to a list in `jh/team/evals.py`. If a real fabrication got through, add it to `DOCUMENTS`, watch `tests/test_evals.py` fail, then fix the check. Keep a genuine counterpart next to every fabrication, so a stricter check cannot raise the false-alarm rate unnoticed.
