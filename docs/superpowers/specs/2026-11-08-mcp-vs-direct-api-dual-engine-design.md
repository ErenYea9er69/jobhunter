# Design Document: MCP vs Direct API Dual-Engine, Dynamic Switching & Latest Models

**Date:** 2026-11-08  
**Status:** Approved  
**Target Architecture:** Multi-Tier AI Driver (External MCP Host vs Direct Standalone API vs Deterministic) + Dynamic Key Management (Add, Delete, Mask, Test) + Latest Frontier Models (Gemini 3.8 Flash, GPT-5 Mini, Claude 3.7 Sonnet) + Turnkey CLI Commands & Web Dashboard UI.

---

## 1. Intent and Why

JobHunter was originally built as an MCP server for AI coding assistants (Claude Desktop, Cursor, Antigravity). However, users cloning the project from GitHub have distinct workflows:
1. **MCP Users**: Want Claude Desktop, Cursor, or Antigravity to act as the AI brain via MCP tools over stdio. They do NOT need or want to enter an API key into JobHunter.
2. **Direct API Users**: Want a standalone Web Dashboard and ATS browser extension without needing Claude Desktop or Cursor open. They supply their own API key (Gemini, OpenAI, Anthropic, DeepSeek, Groq) to power document tailoring and screening directly.
3. **Hybrid & Switching Users**: Want the flexibility to add an API key for standalone use, and later delete/disconnect it to revert cleanly to MCP / deterministic mode without corrupting settings.

Furthermore, default model definitions must use the latest 2026 generation: **`gemini-3.8-flash`** (not 2.5), **`gpt-5-mini`** (not 4o), and **`claude-3-7-sonnet`**.

---

## 2. Core Separation of Modes

| Dimension | MCP Mode | Direct API Mode | Deterministic Mode |
| :--- | :--- | :--- | :--- |
| **Driver / Agent** | Claude Desktop / Cursor / Antigravity | Local JobHunter HTTP Engine (`jh/refit.py`) | Local Rule Engine (`jh/refit.py`) |
| **Protocol** | Standard MCP JSON-RPC over `stdio` | REST API over `http://127.0.0.1:8765` | In-memory Python formatting |
| **API Key Needed?** | **No** (the MCP client provides the LLM) | **Yes** (Gemini, OpenAI, Anthropic, DeepSeek, Groq) | **No** |
| **Document Drafting**| Written by MCP Client or Low-Level Generator | Written by Direct LLM API call | Written by deterministic structured templates |
| **Reviewer QA** | Always enforced via `jh/team/qa.py` | Always enforced via `jh/team/qa.py` | Always enforced via `jh/team/qa.py` |

### Dynamic Switching Lifecycle:
1. **Zero-Key State**: Default is pure MCP / Deterministic mode.
2. **Add API Key**: User runs `python run.py --set-key <KEY> --provider <PROV>` or pastes their key into the Web Dashboard settings. Stored securely in SQLite `settings` table (`<prov>_api_key`). Direct API mode is immediately activated.
3. **Delete / Disconnect API Key**: User runs `python run.py --clear-key` or clicks "Disconnect API Key" in the Web Dashboard. The key is completely purged from SQLite (`DELETE FROM settings WHERE key LIKE '%api_key%'`), immediately reverting to MCP / Deterministic mode.

---

## 3. Latest Frontier Models (2026)

Default models configured across `jh/refit.py` and `jh/config.py`:
- **Google Gemini**: Default to **`gemini-3.8-flash`** (Pro alternative: `gemini-3.1-pro`).
- **OpenAI**: Default to **`gpt-5-mini`** (Reasoning alternative: `o3-mini`, Flagship: `gpt-5`).
- **Anthropic**: Default to **`claude-3-7-sonnet`**.
- **DeepSeek**: Default to **`deepseek-chat`** (Reasoning: `deepseek-reasoner`).
- **Groq**: Default to **`llama-3.3-70b-versatile`**.

---

## 4. Components & Interfaces

### 4.1 AI Settings & Manager (`jh/ai_manager.py`)
- `get_ai_status() -> dict`:
  - Returns current provider, model, whether a key is configured (`key_configured: bool`), masked key string (e.g. `AIzaSy...4xQ`), active mode (`"direct_api"`, `"mcp_client"`, `"deterministic"`), and available providers with recommended models.
- `set_ai_key(provider: str, api_key: str, model: str | None = None) -> dict`:
  - Saves key and provider into SQLite `settings` table.
- `clear_ai_key(provider: str | None = None) -> dict`:
  - Deletes key from SQLite and resets provider to `auto` or `deterministic`.
- `test_ai_connection(timeout_seconds: float = 10.0) -> dict`:
  - Sends a minimal test ping to verify credentials without heavy token usage.

### 4.2 Backend REST Endpoints (`jh/httpd.py`)
- `GET /api/ai/status`: Returns `get_ai_status()` with masked keys.
- `POST /api/ai/config`: Updates provider, model, and/or API key.
- `POST /api/ai/clear-key`: Deletes stored API keys and switches back to MCP mode.
- `POST /api/ai/test`: Tests the connection with the active provider/key.

### 4.3 CLI Commands in `run.py` (Windows, macOS, Linux)
- `python run.py --set-key <KEY> --provider <PROV> [--model <MODEL>]`
- `python run.py --clear-key`
- `python run.py --ai-status`
- `python run.py --test-ai`
- All supported through `run.bat` and `./run.sh` seamlessly.

### 4.4 Dashboard UI Deck (`public/index.html`, `public/app.js`)
- Dedicated **AI Engine & Mode Control Deck** under Tab 5 (Calibration & Filters):
  - Shows active mode badge ("Direct API Active" vs "MCP Host Mode").
  - Provider dropdown with auto-populated recommended latest models.
  - Masked API key input with toggle visibility.
  - "Save & Activate Key", "Test Connection", and "Disconnect / Delete Key" buttons.
  - Real-time feedback alert banners.

