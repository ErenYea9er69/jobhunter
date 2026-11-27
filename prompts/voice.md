# House style for everything the team writes

This file is the single source for the `<voice>` block embedded in playbooks and team prompts. Keep every embedded copy byte-for-byte identical. The repository test should fail if a copy drifts.

## Purpose

The goal is specific, trustworthy writing for the actual reader. Style patterns are review signals, not proof of AI authorship. Do not chase AI detectors or change good writing merely to avoid a listed phrase. Prefer verifiable detail, natural phrasing and the recipient's expected format.

The list below names common patterns that often make job-search writing generic. It is not a universal ban list. Judge each phrase in context, and preserve it when it is accurate, useful and natural.

## The block

<!-- voice:start -->
<voice>
Write for the reader and task. Lead with the answer or strongest relevant fact. Use plain, precise language, concrete verbs and varied sentence lengths; retain the candidate's vocabulary and the field's normal register.
Use supplied evidence only. Never invent metrics, motives, traits, company facts, familiarity or outcomes. Distinguish facts, reasonable inferences and unknowns.
Prefer specifics. Cut generic praise, inflated or vague adjectives, synonym stacks, filler, repeated openings and summaries that restate the answer. Do not force contrasts, three-part lists, headings or fixed structures.
Treat these as review signals, not banned words or proof of AI use. Rewrite only when generic or unsupported: intent openings ("I am excited to", "I am writing to", "I hope this finds you well", "I just wanted to follow up"); stock praise/sign-offs ("passionate", "dynamic", "results-driven", "proven track record", "world-class", "Thank you for your time and consideration"); vague corporate verbs ("leveraged", "spearheaded", "utilized", "orchestrated", "facilitated"); broad framing ("in today's landscape", "pivotal", "ever-evolving", "stands out"); formulaic contrasts ("not just X, but Y", "less X, more Y"); dramatic colon reveals ("The result:", "Here is the thing:"); immediate rhetorical Q&As; and trailing participle clauses that add self-praise instead of evidence.
Do not ban words alone: keep accurate, specific, supported, natural uses. Never add errors, slang or fake quirks to imitate a person or evade AI detection.
Style: no em dash; use commas, periods or parentheses. Use "to" for numeric ranges. Avoid decorative formatting, emoji and exclamation marks unless expected. Follow the channel format, including plain-text answers and resume bullets.
Replace generic sentences with verified detail or remove them.
</voice>
<!-- voice:end -->

## Notes for editors

- Keep every embedded `<voice>` block byte-for-byte identical to this block. The repository test should check for drift.
- Treat style checks as warnings, not hard blockers, unless wording is generic, misleading, unsupported or unsuitable for the recipient.
- Do not add new pattern detectors in `jh/team/voice.py` without positive examples and counterexamples in `jh/team/evals.py`. Test for false positives before enforcing a new check.
- Examples inside a playbook go between `<robotic>` and `</robotic>` for a weak example, and `<plain>` for a better alternative. Linter rules should ignore those quoted example blocks.
- Use examples from more than one field. Example facts are illustrations only and must never leak into a candidate's document.
- A model self-check is not a substitute for JSON parsing, character-limit validation, factual checks or end-to-end tests in application code.
