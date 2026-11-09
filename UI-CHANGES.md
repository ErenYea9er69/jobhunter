# What changed in the UI

Version: web app rebuilt, extension 2.5.0. See `UI-AUDIT.md` for the review of the old UI and `DESIGN.md` for the system.

## Web app (webapp/, copied to public/)
- Rebuilt with plain HTML, CSS and JavaScript. No build step needed to run it. Fonts and icons are local.
- New black, gray and white theme with a matching light theme, plus small green, amber, red, blue and orange accents.
- Jobs page is a card grid. Pressing a card opens a drawer from the right with the full detail. Previous and next buttons, and `j` and `k`, move between jobs while the drawer is open.
- Match score badge on every card: green at 80 or more, amber at 60 to 79, red below 60, gray "No score" when the app returned none.
- Applications board keeps drag and drop and adds a Move menu, Undo on every move, and a Gmail check.
- Documents page: cover letter, tailored resume, interview prep, founder email, LinkedIn note and Big Tech pitch. Every document shows the reviewer verdict and highlights resume terms.
- Resume page with a drop zone, variants and an activate button.
- Settings split into Search, AI engine, Autofill answers, Gmail and Browser.
- Honest states for loading, empty, offline and failed requests, on every page.

## Bugs and slop removed from the old UI
- The score fallback `score||85` invented a high score for jobs without one. Removed.
- Fabricated contact data in outreach views. Removed.
- A view mode mismatch that broke the tailored resume tab. Fixed.
- Invented default answers for work authorization. Removed. The extension answers legal questions only from your saved preferences.
- The chosen email subject was never sent. Now sent.
- Removed: gradient banners, hero metric cards, side-stripe borders, emoji icons, identical icon-tile grids.

## Extension (extension/)
- Version 2.5.0. No longer runs on every website. It loads only on known application sites and LinkedIn. On other pages, the toolbar popup or Alt+Shift+J adds it for that tab.
- Removed the all-sites host permission and the flyout stylesheet.
- API calls go through the background worker. Only a fixed list of local endpoints is allowed.
- New panel in a Shadow DOM. Shows connection state, the profile in use, field count, and three clear actions: fill this form, answer written questions, and LinkedIn notes.
- Fills empty fields only. Each filled field is listed with its own Undo, and there is an Undo all.
- A "Needs you" list shows each field it could not answer and why, with a Go to field button.
- Written answers are marked "Read it before you submit" with the reviewer verdict.
- Automatic submit exists only in countdown mode. It waits 10 seconds with a Cancel button, and never runs when any field needs you.
- Application tracking happens after a confirmation page is detected, or when you press "Track as Applied".
- Popup shows status, the profile in use, and two buttons.

## Verification
- Web app: interaction tests pass (0 failures). axe-core is clean in light and dark at 1440 and 390 pixels wide. No horizontal overflow. No console errors.
- Extension: loaded in Chromium and tested on a mock application form. It filled name, email, phone, LinkedIn, experience years and the work authorization radio, undid a field, answered a written question, and did not submit.
- A fresh reviewer looked at the screenshots without seeing the work. It found 12 issues. These were fixed: card header layout, company color tiles (now neutral), skill chip style, highlight padding, drawer meta separators, stage dot colors, mobile tab clipping (shorter Settings labels, fade on the stage tabs), and the extension heading count alignment.

## Known gaps
- The extension was tested on one mock form, not on live Greenhouse, Lever or Workday pages. Selectors for custom widgets (for example Workday dropdowns) may need adjustment.
- The extension fills text fields, selects and radio groups. It does not attach files.
- The Documents page keeps the generated-document layout from the first rebuild. Two reviewer notes remain: the primary button looks pale while hovered, and the extension Filled list uses two lines per row.
- The posting text in the drawer shows plain "-" bullets as the daemon sends them.

## Install
- Web app: serve `webapp/` (or copy it to the daemon's `public/`). `dev/mock_server.py` runs a fake daemon for design work: `python3 dev/mock_server.py --root webapp --port 8765`.
- Extension: open chrome://extensions, turn on Developer mode, press Load unpacked, choose `extension/`.
