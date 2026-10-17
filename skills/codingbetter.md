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