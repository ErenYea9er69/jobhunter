---
name: jobhunter
description: Start-up workflow for JobHunter MCP server.
---

# JobHunter Start-Up Workflow

For any job request, call `jh_begin` first. If it asks for a resume or a job name, ask the user and wait. If it returns ready, tell the user in one line what you read from the resume, then launch at once: use a subagent only if your client offers one, otherwise call `jh_launch` yourself. Do not wait for the search. Keep talking with the user and ask round 2. Do not print jobs until round 2 is answered or skipped. After round 2, tell the user the UI shows the matches.

## Core Rules:
1. **Resume First**: Call `jh_begin` with the candidate's resume path or text.
2. **STOP on Missing Input**: If status is `needs_resume` or `needs_role`, ask the user and STOP. Do not call another tool.
3. **Launch in Background**: When `jh_begin` or `jh_confirm` returns `ready`, call `jh_launch` (or dispatch a subagent with `subagent_brief`). The launch completes in < 3s.
4. **Chat Stays Free**: While the search runs in the background, ask Round 2 questions. Do not print job listings in chat.
5. **Live Query-Time Filtering**: Each user answer updates filters live via `jh_answer`. The search is never restarted.
6. **Save Before Tailor**: Never offer or generate tailored resumes or cover letters until the user saves a job in the UI.
