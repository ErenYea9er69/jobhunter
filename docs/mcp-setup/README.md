# Connecting JobHunter to your client

JobHunter speaks MCP over stdio. Every client needs the same three things: the Python command, the path to `mcp_server.py`, and the workspace folder that holds your resumes.

Replace the paths below with your own. Use forward slashes on Windows.

## Check it first

```bash
pip install -r requirements.txt
JH_WORKSPACE=/path/to/workspace python mcp_server.py --check
```

You should see `7 tools OK`. These are the CEO tools. Add `--surface full` to see all 46.

## Claude Desktop

File: `claude_desktop_config.json` (Settings, Developer, Edit Config).

```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["/path/to/jobhunter/mcp_server.py"],
      "env": { "JH_WORKSPACE": "/path/to/workspace" }
    }
  }
}
```

## Cursor

File: `.cursor/mcp.json` in your project, or the global `~/.cursor/mcp.json`. Same JSON as above.

## VS Code

File: `.vscode/mcp.json`.

```json
{
  "servers": {
    "jobhunter": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/jobhunter/mcp_server.py"],
      "env": { "JH_WORKSPACE": "/path/to/workspace" }
    }
  }
}
```

## Antigravity

File: `~/.gemini/config/mcp_config.json`. Same JSON as Claude Desktop.

## Optional keys

Add keys to the `env` block, never to a chat message.

| Variable | Purpose |
| --- | --- |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Turns on the Adzuna source |
| `JOOBLE_API_KEY` | Turns on Jooble, which collects small local boards in many countries |
| `JH_SURFACE` | `team` (default): the AI sees only the CEO tools. `full`: it sees every tool |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY` | LLM wording for documents. Without one, the built-in engine writes them |
| `JH_AI_PROVIDER` | `auto`, `deterministic`, `gemini`, `openai`, `anthropic`, `ollama`, `custom` |

## Troubleshooting

- `ModuleNotFoundError: mcp.server.fastmcp`: you installed mcp 2.x. Run `pip install "mcp[cli]>=1.9,<2"`.
- No resume found: put a `.pdf`, `.docx` or `.txt` file in the workspace or `workspace/resumes/`, then call `scan_resumes`.
- Searches return nothing: call `source_health`. The `coverage` block in a search result lists skipped sources and why.
- Logs go to stderr. Your client shows them in its MCP log view.
