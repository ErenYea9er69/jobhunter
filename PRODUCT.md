# JobHunter product notes for the UI

JobHunter is a local-first job search tool. A web app and a Chrome extension talk to a daemon on this computer (http://127.0.0.1:8765). No data leaves the machine except the calls you set up yourself (AI provider, Gmail).

Who uses it: one person, searching for work, often on a laptop and sometimes on a phone browser on the same network. They apply to many roles and need to know three things quickly: which jobs fit, what they already did, and what each form still needs from them.

What the UI promises:
- Every score, answer and document comes from the resume. Nothing is invented. When data is missing, the screen says so ("No score", "Not found in your resume").
- Nothing is submitted for the person unless they chose the countdown mode and every answer was found.
- Every change the extension makes to a page can be undone.
- Offline, empty and error states say what happened and what to do next.

Voice: short, plain sentences. No exclamation marks. No dashes used as punctuation.
