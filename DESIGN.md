# JobHunter design system

## Idea
The marked-up page. The product reads your resume and marks the words in a posting that match it. The interface stays quiet so the marks and the scores carry the meaning.

## Color
Dark theme: about 70% black surfaces, 20% gray (panels, lines, secondary text), 10% white (text, primary actions). The light theme mirrors it: about 70% white, 20% light gray, 10% black.

Small semantic colors, used only where they carry meaning:
- Green: match score 80 or more, success, connected.
- Amber: match score 60 to 79, warnings.
- Red: match score under 60, errors, fields that need you.
- Blue: info, the "New" badge.
- Orange: the "Top fit" badge (score 90 or more).
- No score: gray, with the words "No score".

Company initials sit in neutral gray tiles. Application stages use neutral gray marks. Green, amber and red mean score or state only.

Tokens live at the top of `webapp/styles.css` (light, dark, and dark by system setting). Extension tokens live in `panel.css` inside the extension build and are embedded in `panel-styles.js`.

## Type
JH Sans (Instrument Sans) for the interface, JH Serif (Newsreader) for page titles and documents, JH Mono (JetBrains Mono) for code. All three are self-hosted. No network font requests.

## Layout
- Mobile first. A bottom tab bar on phones, a left rail from 900px up.
- Jobs: a card grid. Each card shows company, title, score, one meta line, a two-line summary, matched skills as outline chips, and the main actions.
- Pressing a card opens a drawer from the right (a native dialog). It holds the fit reasons, the full posting with resume terms highlighted, and shortcuts to write documents. On phones it fills the screen.
- Applications: a Kanban board on wide screens, one stage at a time on phones. Drag and drop, plus a Move menu for keyboard and touch.

## Signature: the highlight
`.mk` marks a term that comes from your resume: a gray fill with a rule underneath. It sweeps in once when a posting opens. The sweep stops under reduced motion.

## Accessibility
- Every interactive element is a real button, link or input with a visible focus ring.
- Touch targets are at least 44px on coarse pointers.
- axe-core reports no violations in light and dark at 1440 and 390 pixels wide.
- Text direction follows the content (`dir="auto"`), so Arabic postings read correctly.
- Toasts use aria-live. Reduced motion is respected. Forced colors mode keeps the highlight visible.

## Keyboard
`/` search, `j` and `k` move between jobs, `Enter` or click opens the drawer, `s` save, `a` apply, `?` list shortcuts, `g` then `j`, `a`, `d`, `r` or `s` to go to a page. In the browser, Alt+Shift+J opens the extension panel.

## Extension panel
A Shadow DOM panel in the bottom right. Page styles cannot change it and it cannot change the page. It appears only on pages with a form (three or more fillable fields) or on a LinkedIn profile, and on any page when you press Alt+Shift+J or use the toolbar popup.
