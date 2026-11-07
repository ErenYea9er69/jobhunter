# House style for everything the team writes

This file is the single source for the `<voice>` block that every playbook and the Writer prompt embed.
`tests/test_prompts.py` fails if an embedded copy drifts from the block below.

## Why this exists

Hiring managers say they can tell. In surveys, the complaint is not that a letter used AI. It is that the
letter is generic and nothing in it can be checked. Readers react to a few patterns, and those patterns are
easy to avoid once you know them. A model also copies the style of its prompt, so the prompts follow these
rules too: no em dashes, no capital-letter shouting, no boasting persona, no invented statistics.

Banning words alone does not work. After "delve" became a known giveaway, its use fell and other style words
kept rising. So the block names patterns, gives the plain alternative, and asks for the positive habit: a fact
only this candidate has, in plain words. The Reviewer scans every draft for the same patterns (see
`jh/team/voice.py`) and reports them as warnings.

## The block

<!-- voice:start -->
<voice>
Write the way a capable person writes to one reader: the concrete fact first, plain words, short sentences with a longer one now and then. Use specific verbs (built, ran, cut, wrote, fixed, taught, sold). Use a number only when the candidate's data has it.
Punctuation: commas, periods, semicolons and parentheses. No em dashes or en dashes. Write ranges as "150 to 220".
Readers spot the following at once and stop trusting the text. Replace each with a fact only this candidate has, or cut it:
- openers about feeling or intent ("I am excited to", "I am writing to", "I hope this finds you well", "I came across your profile")
- stock praise ("passionate", "dynamic", "results-driven", "proven track record", "cutting-edge", "world-class", "fast-paced")
- vague power verbs ("leveraged", "spearheaded", "utilized", "orchestrated", "facilitated")
- grand framing ("in today's landscape", "testament to", "pivotal", "ever-evolving")
- the "not just X, but Y" frame, a question that the next sentence answers, three adjectives in a row, a last line that repeats the point
- exclamation marks and emoji, and bold or bullet symbols in text meant for a form or an email
If a sentence could sit in any candidate's letter, it does not belong in this one.
</voice>
<!-- voice:end -->

## Notes for editors

- Add a pattern to `jh/team/voice.py` when a new one shows up, with a genuine counterpart in `jh/team/evals.py`
  so a stricter rule cannot raise the false-alarm rate unnoticed.
- Examples inside a playbook go between `<robotic>` and `</robotic>` (what to avoid) and `<plain>` (what to write).
  The prompt linter skips `<robotic>`, `<voice>` and `<avoid>` blocks because they quote the patterns on purpose.
  Everything else in a prompt must pass the linter.
- Write facts in examples that are plainly illustrations, and tell the model not to reuse them.
- Keep examples across different fields (software, finance, teaching, operations). A prompt that only shows
  engineering examples produces engineering vocabulary for everyone.
