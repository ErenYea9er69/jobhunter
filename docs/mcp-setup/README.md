# JobHunter MCP Server — Setup Guide

JobHunter exposes 24 tools and 6 resources over the Model Context Protocol (MCP) using `stdio` transport. It allows AI assistants like Antigravity, Cursor, Claude Desktop, and VS Code to search job boards, score resumes against postings, generate truthful tailored resumes, create targeted cover letters, and track applications directly inside your chat.

## Prerequisites

- Python 3.11+
- Install MCP dependencies:
  ```bash
  pip install -r requirements-mcp.txt
  ```

---

## 1. Antigravity Setup

Add JobHunter to your Antigravity configuration file (usually in `~/.gemini/config/mcp_config.json`):

```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["c:/Users/hp/Desktop/jobhunter/mcp_server.py"],
      "env": {
        "JH_WORKSPACE": "c:/Users/hp/Desktop/jobhunter"
      }
    }
  }
}
```

---

## 2. Cursor Setup

Add JobHunter to `.cursor/mcp.json` in your repository:

```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["c:/Users/hp/Desktop/jobhunter/mcp_server.py"],
      "env": {
        "JH_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

---

## 3. Claude Desktop Setup

Open your Claude Desktop config (`%APPDATA%/Claude/claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "jobhunter": {
      "command": "python",
      "args": ["c:/Users/hp/Desktop/jobhunter/mcp_server.py"],
      "env": {
        "JH_WORKSPACE": "c:/Users/hp/Desktop/jobhunter"
      }
    }
  }
}
```

---

## 4. VS Code Copilot Setup

Add JobHunter to `.vscode/mcp.json`:

```json
{
  "servers": {
    "jobhunter": {
      "type": "stdio",
      "command": "python",
      "args": ["c:/Users/hp/Desktop/jobhunter/mcp_server.py"],
      "env": {
        "JH_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

---

## Workspace Structure & Resumes

Place your resume files in the repository root or in a `resumes/` folder:
```
my-job-search/
  resumes/
    backend-engineer.pdf
    fullstack.docx
    cloud-architect.txt
  .jobhunter/
    config.json          (preferences & active resume)
    applications.json    (tracked applications)
    cache/jobs.json      (cached searches)
    output/              (tailored resumes & cover letters)
JobHunter automatically detects and parses all resume files upon startup.

---

## 5. Troubleshooting & Diagnostics

### Protocol Stdout Pollution
- **Issue**: Host reports `JSONRPC parse error` or connection drops immediately upon launch.
- **Cause**: An unbuffered `print()` statement or library banner emitted text to `stdout`. MCP reserves `stdout` exclusively for JSON-RPC messages.
- **Fix**: All diagnostic and informational messages in JobHunter are configured to use `logging` directed to `sys.stderr`. Never use `print()` in server code.

### Python Environment & Path Resolution
- **Issue**: `python: command not found` or module import failure (`No module named mcp`).
- **Fix**: Specify the absolute path to your Python executable (or virtual environment interpreter) in the `"command"` field instead of generic `"python"`:
  ```json
  "command": "C:/Users/hp/AppData/Local/Python/pythoncore-3.14-64/python.exe"
  ```

### Unresolved `${workspaceFolder}`
- **Issue**: Error stating `directory not found: ${workspaceFolder}`.
- **Cause**: Some hosts (e.g. Claude Desktop) do not evaluate `${workspaceFolder}`.
- **Fix**: Provide the literal absolute path in `"JH_WORKSPACE"`: `"c:/Users/hp/Desktop/jobhunter"`.

### Permission Errors on `.jobhunter/`
- **Issue**: `PermissionError: [Errno 13] Access denied` when saving configurations or applications.
- **Fix**: Ensure the running user has read/write permissions for the workspace directory and `.jobhunter/`. JobHunter uses atomic file writes (`tempfile.NamedTemporaryFile` + `replace()`) which requires directory write permission.

### Quick Verification Smoke Test
Run the automated test suite to verify full protocol and module health:
```bash
python -m pytest -q
```
