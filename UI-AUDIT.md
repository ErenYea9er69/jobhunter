# JobHunter UI audit (before the redesign)

Method: single-context review. I read every line of the web app (index.html, app.js, styles.css) and the extension (manifest, background, content, popup, flyout.css). I rendered the old web app against a mock daemon at 1440 and 390 pixels wide. I read all 17 files in `uiskills/` first and judged the work against them. A separate fresh review of the rebuilt UI is listed at the end of `UI-CHANGES.md`.

Mode: Operate. The visitor came to finish a task (find a job, write a document, apply, track). Scanability, native controls and honest state outrank expression.

## Score

Nielsen heuristics, 0 to 4 each. Most real products score 20 to 32.

| # | Heuristic | Score | Main finding |
|---|-----------|-------|--------------|
| 1 | Visibility of system status | 2 | Kanban lane counts always show 0. Document generation has no loading state (the status element it writes to does not exist). "Reviewer QA: PASS" shows before anything was reviewed. |
| 2 | Match with the real world | 2 | Internal jargon in every label: Radar, Hunt Jobs, Calibration, Dispatcher, Copilot, Reviewer QA. |
| 3 | User control and freedom | 2 | No cancel for a search, no undo, no Esc on the three modals, no back-button support between views. |
| 4 | Consistency and standards | 2 | One action has three names (Track in Kanban, Saved, Bookmarked). Eight CSS classes used in JS do not exist in the stylesheet, so variants and skills render unstyled. |
| 5 | Error prevention | 1 | Four auto-apply settings (work authorization, sponsorship, notice, submission mode) are never saved or read. The extension answers "No sponsorship needed" for everyone and its main button submits the form after 5 seconds. |
| 6 | Recognition over recall | 3 | Nav items have icons plus labels. Filters are visible. |
| 7 | Flexibility and efficiency | 1 | No keyboard shortcuts, no drag and drop on a Kanban board, every filter click re-runs a full multi-source search. |
| 8 | Aesthetic and minimalist design | 2 | Every region sits in a bordered card. Five identical metric cards. Text is 11 to 13px almost everywhere. |
| 9 | Error recovery | 1 | 12 `alert()` and `confirm()` calls. Errors read "Error generating document" with no recovery step. |
| 10 | Help and documentation | 1 | No help, no shortcuts list, one overclaim ("Zero hallucinations guaranteed"). |
| | Total | 17 / 40 | Poor. Major UX overhaul needed. |

## Design specificity verdict

Interchangeable. Remove the product name and this is the default AI dashboard: dark slate ground, emerald accent, lightning-bolt logo, sidebar plus top bar, bordered cards, system font. Nothing on screen shows what is special about JobHunter: everything it writes traces back to your resume. The product makes that promise in its README and then never shows it.

## AI slop inventory

Mapped to `uiskills/craft-floor.md` ("Refuse" list) and `critique.md`.

1. Default palette: dark slate plus emerald, chosen by category, not by use scene. The code even contains `prefersDark ? "dark" : "dark"`, so the OS preference is ignored.
2. Lightning bolt as logo and as the icon on four different buttons. Unicode and emoji icons in the extension (bolt, memo, robot, key, gear).
3. Cards as the page structure. Cards inside cards (variant list, experience items, inspector). Same-size cards on every page.
4. Hero-metric template: five equal number-plus-label cards on the Kanban page.
5. Uppercase micro labels with tracking ("WHY YOU MATCH:", section captions at 11px).
6. Gradient banner for onboarding.
7. A 2px colored `border-left` on experience items.
8. `transition: all` on 8 rules. No `prefers-reduced-motion`. No authored motion moment.
9. Blurred modal backdrop as decoration. Modals used for tasks that need no interruption (add application, Gmail setup, email finder).
10. Browser surfaces left at default: no focus ring (`outline: none` on inputs, zero `:focus-visible` rules), default checkboxes and radios, default `select` arrows.
11. Product copy that sells instead of tells: "Autonomous Copilot v2.4", "Frontier Model", "Zero hallucinations guaranteed".
12. 58 inline `style=` attributes in the HTML and 75 in app.js. Styling lives in markup, so no design system survives.

## Defects that hurt real use

Confirmed in code and in the old renders.

Honesty (highest priority for a product that sells "truthful"):

- `score || 85`: a job with no score shows "85% FIT". The fit rationale falls back to a stock sentence about "years of experience".
- Static HTML shows "Reviewer QA: PASS" and "92% ATS Match" before anything is generated. `verdict || "PASS"` turns a missing review into a pass.
- Profile fallbacks invent contact data ("email@example.com", "+1 234 567 890"). Big Tech view invents "recruiter@bigtech.com".
- The extension fills "3" years of experience when the resume has none.
- Another person's defaults ship in the form: company "Vermeg", role "Software Engineer", location "Tunisia".

Broken behavior:

- Kanban lane counts never update (`count-*` ids are never written). "Rejected" applications land in the Saved lane.
- Sort "Most Recent" does nothing (the option value is `date`, the code checks `freshness`, and the comparison is reversed).
- Printing a tailored resume prints the cover letter (`"resume"` vs `"tailored-resume"` mismatch).
- Variant list, skill chips and experience cards use class names the stylesheet does not define.
- Work authorization card clips its own fields. The browser list clips.
- All filter chips trigger a full network search. The page also runs a search on load with a hard-coded query.
- No responsive CSS at all (0 media queries). At 390px the sidebar takes 250px and the content is cut off.

Accessibility:

- 37 of 40 labels are not tied to their inputs. Zero ARIA attributes. Job cards are `div` click targets with no keyboard access. Modals have no focus trap and no Esc. Body text is 13.5px, and 41 of 73 font sizes are 12.5px or smaller.

## Extension findings

- The panel is injected into every page on the web (`<all_urls>`), including search engines and banks, and watches every DOM change by reading the full page text. It marks "applied" on any form submit anywhere.
- `all: initial` on one container is not isolation. Page CSS leaks in and out. Shadow DOM fixes this.
- Primary button: "Auto-Pilot (Fill & Submit)". Auto-submit is on by default and ignores the dashboard setting. Sponsorship and authorization answers are hard-coded.
- No list of what was filled, no undo, no marker for fields it could not answer.
- The popup only shows status and a link. It cannot act on the page you are viewing.
- Manifest has no icons. Versions disagree (manifest 2.3.0, panel 2.4.0, dashboard v2.4).

## What works and stays

- The six jobs the product does: search with fit scores, pipeline, documents, resume variants, preferences with AI engine, auto-apply. All features stay.
- Two-pane list plus inspector on the jobs page. It matches how people scan jobs.
- Theme toggle, themed scrollbars and selection, HTML escaping, drag-and-drop resume upload, local-first privacy.

## Persona red flags

- Alex (power user): no shortcuts, no bulk move, no drag on the board, every filter re-searches.
- Jordan (first timer): nothing says which tab to open first. Terms like "Dispatcher" and "Calibration" need explaining. A resume wizard stays on the page forever after upload.
- Sam (screen reader and keyboard): cannot open a job without a mouse. Focus is invisible. Labels are not announced.
- Casey (phone): the layout breaks. Nothing is kept after a reload.
- Riley (stress tester): Arabic and long titles overflow. Failed requests end in `alert()`. A missing score looks like 85%.

## Direction contract for the redesign

THESIS: A job search is paperwork under doubt. JobHunter's promise is that nothing on the page is invented. The surface shows that promise: your resume facts are marked in highlighter wherever they appear, the Reviewer speaks in plain verdicts, and a missing fact reads as missing. It refuses the dark slate and emerald dashboard of identical cards.

OWN WORLD: the marked-up page. Paper ground, ink-blue shell, highlighter yellow for "from your resume", red pen for "flagged". Standard controls and navigation. The world supplies type, palette, density and one signature move.

STORY: Find roles that fit and see why. Write documents you trust. Apply with fewer clicks and no surprises. See where every application stands.

FIRST VIEWPORT (Jobs): ink rail with five destinations, one search line, a row list of roles, and a detail pane with the posting text where matching skills carry the highlighter.

SIGNATURE MOMENT: the highlighter sweep. When you open a job, the terms from your resume sweep into the description once. The same marks appear in generated documents behind a "Show resume matches" switch. Reduced motion shows them static.
