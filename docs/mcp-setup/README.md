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
```
JobHunter automatically detects and parses all resume files upon startup.
