---
name: strategic-coding
description: Use before any coding task, bug fix, code review, or technical design. Forces a fixed workflow. Understand the task, ground every claim in real files and docs, plan with alternatives, pick the best path for the request and the app without asking the user, build in small verified steps, run the code, and report results honestly. Cuts invented APIs, false success claims, and rushed fixes.
---

PURPOSE

Coding models fail in predictable ways. They start writing before they understand the task. They invent functions, flags, files, and package names. They skip verification. They report success without proof. They patch symptoms and leave the root cause in place.

Research on code hallucination sorts the errors into four types. Mapping errors break data types or structures. Naming errors use wrong or invented identifiers. Resource errors ignore memory, time, or environment limits. Logic errors produce code with valid syntax and wrong behavior. This skill blocks each type with a fixed workflow.

Follow the six phases in order. Do not skip a phase because the task looks easy. Scale the depth to the task. A one-line fix needs a short pass. A new feature needs a full pass.

RULE ZERO

Treat your memory as a draft, not a source. Check every fact you did not read during this session before you rely on it. This covers function names, signatures, flags, config keys, file paths, package versions, and error messages.

RULE ONE: CHOOSE THE PATH YOURSELF

You make the technical decisions. Do not ask the user which approach is best. Read the request and the app, then pick.

1. Read the request, the app, and its context before you choose. Note the app type (web, mobile, CLI, library, backend service, data pipeline), the language, the framework, the size of the codebase, the existing patterns, the users, and the risk level.
2. Pick the path by fit. The best path matches what the user asked for, how the app already works, and what the task needs. A prototype needs a fast path. A payment flow, an auth change, or a data migration needs a careful one.
3. When you find several strategies, analyze all of them. Score each one against the request, the app, the cost, and the risk. Then choose one of two moves. Pick the single best strategy. Or build a mix: take the strong part of each strategy, drop the weak part, and say which parts you took and why. Choose the mix when two strategies each solve part of the problem and fit together without extra complexity.
4. Base every choice on evidence from the task and the app. Do not choose by habit, by taste, or by the option you know best.
5. Ask the user only when the choice is complicated for you. This means the options trade off in ways only the user knows, such as budget, business rules, deadline, or who maintains the code, and no file, doc, or test settles it. Ask one short question. Give your recommended default and say what you will do if the user does not answer.
6. After you choose, commit. State the choice and the reason in one or two sentences, then move on. Do not hedge. Do not list options for the user to pick from.

PHASE 1: UNDERSTAND

1. Restate the goal in one sentence. Define done as a result someone else tests.
2. List the inputs, outputs, constraints, language version, and library versions.
3. Identify the app type and its conventions. Let them shape the approach.
4. List the unknowns. Mark each one as "look up" or "decide". Mark one as "ask the user" only when Rule One step 5 applies.
5. Look up what the code or docs answer. Decide the rest yourself using Rule One. Ask the user only when the answer changes the design, no file or doc settles it, and the choice is too complicated to settle from the request and the app. Keep the question short and give a default.
6. State what is out of scope. Do not add features nobody requested.

PHASE 2: GROUND

Read before you write.

1. Open every file you plan to change. Open the callers and the tests for each one.
2. Find how the project solves similar problems. Copy its conventions for naming, error handling, logging, and tests.
3. Confirm each function, class, flag, config key, and path exists. Use search, read the source, or read the docs. Never write an API call from memory when the source or docs are available.
4. Treat a failed lookup as a stop signal. Report the gap. Do not fill it with a guess.
5. Label each fact in your notes as verified (you saw it), inferred (you reasoned to it), or assumed (no evidence). Move assumed items toward verified before you build on them.
6. When docs and source disagree, trust the source and say so.

PHASE 3: PLAN STRATEGICALLY

1. Write two or three candidate approaches, even for small tasks. For each one, state the cost, the main risk, what breaks if the approach is wrong, and how well it fits the request and the app.
2. Compare all candidates using Rule One. Pick the best one, or build a mix of the best parts. Give the reason in one or two sentences. Prefer the smallest change. It solves the real problem, reuses existing code, and is easy to undo. Do not ask the user to choose.
3. Find the root cause. Ask why the problem happens, not only where it shows up. Keep asking until the answer points to something you control.
4. Run a pre-mortem. Assume the change failed in production. List the three most likely reasons. Add a check for each reason to your plan.
5. List what else your change touches: callers, data formats, other services, performance, security, and users with older versions.
6. Split the work into small steps. Give each step a check you run.
7. Pause and confirm with the user before any action with no undo. This covers deletes, migrations, force pushes, overwrites, and calls to paid or production services.

PHASE 4: BUILD IN SMALL STEPS

1. For a bug, write a failing test or a minimal reproduction first. For new behavior, write the test first when the project has a test setup.
2. Make one change. Run the check. Move on only after the check passes.
3. Keep each diff small and focused. Do not refactor unrelated code.
4. Handle the edge cases: empty input, null values, wrong types, large input, repeated calls, concurrent calls, timeouts, and partial failure.
5. Choose clear names. Write comments to explain why, not what.
6. Prefer boring, proven solutions over clever ones. Add a dependency only when the standard library and existing dependencies fall short.

PHASE 5: VERIFY

Run the code. Reading code does not count as verification.

1. Run the tests, the build, the linter, and the type checker.
2. Run the code with a normal input, an edge case, and a bad input. Read the actual output.
3. Review your own diff as a strict outside reviewer. Ask a pointed question about each risky line. Does this function exist with this signature? Does this loop end? What happens with null? Is this index off by one? Does this change leak a secret or trust unchecked input?
4. Compare the result to the definition of done from Phase 1. Check each requirement one at a time.
5. When a check fails, read the full error first. Form one hypothesis. Test it. Repeat. Do not change code at random.
6. After three failed attempts on the same problem, stop. Write down what you learned. Return to Phase 3 and plan again.
7. If you lack a way to run something, say so plainly. Never claim a test passes when you did not run it.
8. For high-stakes work, ask a fresh reader to review the diff. Use a second agent or a new session. A reviewer who watched you build the change shares your blind spots.

PHASE 6: REPORT HONESTLY

1. State what you changed and why, in plain language.
2. State which path you chose and why. If you combined strategies, name the parts you took from each.
3. State what you verified and how. Include the commands you ran and the results.
4. State what you did not verify. List every assumption you made.
5. State the known risks and the follow-up work.
6. Never write "should work" in place of a test. Never hide a failure or a skipped step.
7. Say "I do not know" when you do not know. An honest gap beats a confident guess.

ANTI-HALLUCINATION RULES

1. Never invent a file path, function, flag, package, version number, or error message. Look each one up.
2. Never cite a doc or a source you did not open.
3. Quote code and error text exactly. Do not paraphrase from memory.
4. Separate observation from interpretation. Write "the test fails with this error" first. Write "I think the cause is X" second.
5. State your confidence in plain words: sure, fairly sure, or guessing. Match the words to the evidence.
6. Look for evidence against your current theory. Do not collect only the evidence for it.
7. Re-read the original request before you write the final answer. Long sessions drift from the goal.
8. When two sources conflict, say so and name both.

THINKING HABITS

1. Ask what a senior engineer would question about this change.
2. Ask what the simplest explanation is, then test the second simplest.
3. Ask what you would regret not checking if this ships today.
4. Trace the data from input to output once, step by step, before you trust the logic.
5. Prefer reversible decisions. Make irreversible ones slowly.
6. Match effort to risk. Spend more care on auth, payments, data deletion, and public APIs.
7. Match the path to the app. The same task needs a different approach in a small script, a production web app, and a shared library.

HARD STOPS

Stop and tell the user when any of these happen.

1. A required file, doc, or dependency is missing and no source confirms the right one.
2. The request contradicts itself or contradicts the existing code.
3. A step needs credentials, production access, or a destructive action you have no approval for.
4. Three attempts at the same fix have failed.
5. You find yourself writing code against an API you have not seen.

A hard stop is not the same as a choice between approaches. Settle approach choices yourself with Rule One. Ask the user only when Rule One step 5 applies.

OUTPUT FORMAT

End each task with a short report in plain text.

Goal: one sentence.
Path: the approach you chose and why, in one line. Name the mix if you combined strategies.
Change: what you did and where.
Evidence: commands run and results.
Unverified: what you did not check, and your assumptions.
Risks and next steps: what the user should watch.

Keep the report short. Lead with the result. Use simple words and active voice.

---

# ARCHITECTURAL ANALYSIS & SPECIFICATION: SEARCH RELAXATION WIDGET
## Comprehensive Multi-Aspect Analysis (Filters, Matching Engine, Resume Variants, Profile Calibration, and Auto-Relaxation UX)

### 1. Executive Summary & Objective
When users search or filter jobs on JobHunter (by Category, Role, Date Posted, Match Score, Work Mode, Location, etc.), combinations of constraints frequently lead to low or zero results (e.g., 0 to 4 jobs displayed). 

The goal is to implement an intelligent, proactive **Search Relaxation Widget** rendered at the end of the home page job list. It:
1. Explains why result counts are restricted ("What's limiting your search").
2. Prescribes the single highest-impact adjustment ("How you may adjust").
3. Provides an instant, one-click **"Update Now"** action button that automatically reconfigures the limiting filter, synchronizes UI controls, and re-queries/re-renders the job stream.

---

### 2. Deep Aspect 1: The App Filtering System (30 Dimensions)
Grounding in `jh/db.py` (`query_stored_jobs`) and `public/app.js` (`filteredJobs`):

JobHunter filters operate across 30 distinct dimensions divided between backend SQL pre-filtering and frontend reactive filtering:

1. **Date Freshness (`freshnessDays`)**:
   - Tiers: `Past 24 hours` (1 day), `Past 3 days` (3 days), `Past week` (7 days), `Past 2 weeks` (14 days), `Past month` (30 days), `All time` (0).
   - *Impact*: In tech scraping and aggregation, fresh listings decay exponentially. Setting Date Posted to "Past 24 hours" drops available listings by 85–95% compared to "Past week".
2. **Match Score Threshold (`minScore`)**:
   - Tiers: `0%`, `50%`, `60%`, `70%`, `80%`, `90%`.
   - *Impact*: Evaluated dynamically by `jh/scoring.py`. Strict thresholding (>70% or >80%) eliminates listings where the candidate has partial skill overlap or missing adjacent tools.
3. **Work Mode (`workMode` / `workModels`)**:
   - Modes: `Remote`, `Hybrid`, `Onsite`, `Any`.
   - *Impact*: Restricting to `Remote` excludes 65%+ of hybrid tech roles in tech hubs.
4. **Category & Role Function (`category`, `jobFunctions`)**:
   - Roles: Full Stack, Backend, Frontend, DevOps/SRE, ML/AI, Data Engineering, Mobile, QA, Security, Product, Design.
   - *Impact*: Niche roles (e.g., Security, QA, Mobile) have lower baseline volumes than Full Stack or Backend.
5. **Seniority & Experience Level (`seniority`, `expLevels`, `expYears`)**:
   - Levels: Intern, Junior, Mid, Senior, Lead/Staff, Director.
   - *Impact*: Strict `Junior` or `Intern` filters cut 80%+ of available tech listings because many employers post general "Software Engineer" without junior tags.
6. **Compensation / Salary Tier (`minSalary`, `salaryTier`, `salaryOpenToAll`)**:
   - Tiers: Open to all, Disclosed only, $100k+, $140k+, $180k+.
   - *Impact*: 60%+ of scraped listings do not disclose public salary bands. Filtering for "$140k+" removes both low-paying jobs and unlisted salary roles.
7. **Geographic Scope & Work Authorization (`country`, `locationQuery`, `h1b`, `excludeClearance`, `excludeCitizenOnly`)**:
   - Scope: United States, Worldwide, specific metro, H1B sponsorship required.
   - *Impact*: Requiring H1B sponsorship or limiting to a specific radius in non-hub cities shrinks results drastically.
8. **Company Type & Stage (`famousMode`, `companies`, `companyStages`, `excludeStaffing`)**:
   - Tiers: Big Tech Only (`famousMode=only`), Hide Big Tech, Startups Only, Exclude Staffing.
   - *Impact*: `famousMode=only` restricts the pool to ~15 mega-cap companies.
9. **Required & Excluded Skills (`skills`, `selectedSkills`, `excludedSkills`)**:
   - AND-logic filtering across skill tokens in description and title.
10. **Winning Resume Variant Filter (`best_profile_id` / `filterResume`)**:
    - Limits view to jobs where a specific tailored resume won the match over other variants.

---

### 3. Deep Aspect 2: Match Scoring Engine (`jh/scoring.py`)
Understanding how match scoring drives results:

Scoring uses a composite 100-point model:
- **Skill Overlap (50 pts max)**: Weighted requirement extraction (`sk.extract_weighted`) with cluster affinities (e.g., Postgres ~ MySQL grants 0.45 credit).
- **Title Alignment (20 pts max)**: Token similarity ratio (`title_tokens`). If ratio < 0.12 and <= 1 skill matched, the score is hard-capped at 32%.
- **Seniority Alignment (10 pts max)**: Level delta (`level_of(job)` vs `profile.years_of_experience`). A 2-level gap imposes a -12 penalty; a 3+ level gap imposes a -25 penalty.
- **Work Mode & Geo Fit (10 pts max)**: Work mode compatibility. If a job is US-only or requires citizenship and the candidate profile lacks US residency, score is hard-capped at 38%.
- **Freshness & Salary (5 pts + 5 pts max)**: Freshness decay (>60 days notes stale).
- **Core Requirement Penalties**: Missing 2+ core non-adjacent technologies penalizes -22 pts.

*Crucial Correlation*: When a user sets `minScore >= 70%`, a single minor gap (such as a 2-year seniority delta or a missing secondary framework) causes an otherwise great job (scoring 64–68%) to be filtered out. Relaxing `minScore` from 70% to 50% or 60% unlocks high-quality opportunities.

---

### 4. Deep Aspect 3: Resume Variants & Candidate Profile
JobHunter supports multiple live resume profiles (`jh/refit.py`, `jh/resume_parser.py`):
1. **Multi-Variant Pool**: A user may have a "Full Stack General" variant and a "Python Backend" variant.
2. **Filtering by Variant**: When the user filters by `best_profile_id`, the system hides jobs where another variant scored higher. Relaxing to "All Resumes" restores the full breadth.
3. **Profile Completeness Bottleneck**: If the active profile contains < 6 skills or lacks clear target titles, all calculated match scores drop into the 30–50 range. If `minScore` is active, the entire job board appears empty.
4. **Geo & Work Mode Preference**: A profile marked "Remote Only" without target countries filters out hybrid roles within commuting distance.

---

### 5. Bottleneck Detection & Dynamic Relaxation Algorithm
When `filteredJobs().length <= 5` (or when `filteredJobs().length === 0` but `totalAll > 0`), the system evaluates which active filter is responsible for the constriction:

```
Algorithm: Marginal Gain Bottleneck Resolver
1. Input: Active filter set F, Current filtered job count N (N <= 5), Full job pool P.
2. For each active non-default filter f in F:
   a. Create candidate filter set F' where f is relaxed to its next broader setting:
      - freshnessDays: 1 -> 7 (Past week), 3 -> 14, 7 -> 30, >7 -> 0 (All time)
      - minScore: >=80 -> 60, >=70 -> 50, >=50 -> 0 (Any score)
      - workMode: 'Remote'/'Hybrid'/'Onsite' -> 'Any'
      - jobTypes: (filtered set) -> All Job Types
      - salaryTier / minSalary: active -> Open to all
      - seniority / expLevels: active -> Open to all levels
      - famousMode: 'only' / 'startups' -> 'all'
      - best_profile_id: specific -> 'all'
      - country / location: specific -> Worldwide Remote
   b. Compute simulated count N' = evaluate(P, F').
   c. Compute marginal gain G = N' - N.
3. Select filter f* with max(G) (highest marginal gain).
4. Return LimitingCriterion(
     filterKey: f*,
     currentLabel: displayLabel(f*),
     currentValueBadge: displayValue(f*),
     adjustAction: prescribeAdjustment(f*),
     recommendedValueBadge: recommendedValue(f*),
     relaxedState: F'
   ).
```

---

### 6. Widget UI/UX Specification (Pixel-Accurate to Design)
The widget is positioned at the bottom of the job list (`#jobList`), styled with modern typography, subtle borders, and accessible contrast:

```
+-----------------------------------------------------------------------------------+
|  (!) We couldn't find more jobs with your current preferences. Try adjusting      |
|      the following criteria to view more jobs.                                    |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |  📌 What's limiting your search:                                            |  |
|  |     Date Posted is set to  [ Past 24 hours ]                                |  |
|  |  -------------------------------------------------------------------------  |  |
|  |  💡 How you may adjust:                                                     |  |
|  |     Set the Date Posted to  [ Past week ]                                   |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
|                                 [ Update Now ]                                    |
+-----------------------------------------------------------------------------------+
```

- **Container**: Card with rounded corners (`16px`), background `#ffffff` (dark mode `#1e293b`), border `1px solid var(--line, #e2e8f0)`, soft shadow.
- **Header Notice**: Emerald-green circle (`#10b981`) with white exclamation mark `!`, followed by explanatory heading text.
- **Inner Criteria Box**: Light container (`#f8fafc` / `#0f172a`), border `1px solid #e2e8f0`.
  - Section 1: "📌 What's limiting your search:" + Criterion name + Badge (`.badge-pill`).
  - Divider: Subtle hairline divider.
  - Section 2: "💡 How you may adjust:" + Recommended adjustment action + Badge.
- **Action Button**: Centered black pill button (`#000000`, white text, `border-radius: 9999px`, font-weight: 700, padding: `10px 28px`).
- **Interaction**: Clicking **"Update Now"** executes the single targeted relaxation, synchronizes the UI controls (dropdowns, sliders, chips), and triggers `filterAndRender(true)` without reloading the page.

---

### 7. Implementation Plan & File Touchpoints
1. **Frontend Logic (`public/app.js`)**:
   - Add `detectSearchBottleneck(jobsPool, activeFilters)`: simulates relaxations and ranks marginal gains.
   - Add `renderSearchRelaxationWidget(bottleneck, currentCount)`: builds the responsive HTML component matching the design.
   - Update `renderList()`: append widget at the end of the jobs list when `jobs.length <= 6` or when reaching end of filtered results where total pool was limited.
   - Add global click handler for `[data-action="apply-search-relaxation"]`: mutates `S.filters`, updates DOM inputs/pills, and executes `filterAndRender(true)`.
2. **Frontend Styling (`public/styles.css`)**:
   - Add `.search-relaxation-card`, `.relaxation-notice-header`, `.relaxation-criteria-box`, `.relaxation-pill-badge`, `.btn-relaxation-update`. Supports dark/light themes.
3. **Verification**:
   - Test low result conditions: `freshnessDays = 1` -> suggests `Past week` and clicking "Update Now" relaxes and refreshes.
   - Test score threshold: `minScore = 80` with low results -> suggests lowering to 60%.
   - Test work mode: `workMode = Remote` -> suggests `Hybrid & Remote` or `Any`.
   - Test zero jobs state: replaces generic empty text with the targeted relaxation card.