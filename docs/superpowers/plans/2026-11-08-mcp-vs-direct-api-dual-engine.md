# MCP vs Direct API Dual-Engine, Key Management & Latest Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide seamless dual-mode execution (External MCP Agent Mode vs Direct Standalone API Mode with dynamic key add/delete/test), update all default models to the latest frontier generation (`gemini-3.8-flash`, `gpt-5-mini`, `claude-3-7-sonnet`), and expose turnkey CLI commands and web dashboard controls.

**Architecture:** A centralized `jh/ai_manager.py` manages model mappings, masked key representation, secure SQLite storage, and testing. `jh/refit.py` uses the latest models. `jh/httpd.py` exposes REST endpoints for web dashboard switching, while `run.py` provides cross-platform CLI management.

**Tech Stack:** Python 3.11+, SQLite, standard library HTTP and JSON, Vanilla JS / HTML / CSS.

**Spec:** `docs/superpowers/specs/2026-11-08-mcp-vs-direct-api-dual-engine-design.md`

## Global Constraints

- Protected regions in `jh/sources/__init__.py`, `jh/pipeline.py`, and `jh/config.py` MUST NOT be modified (`tests/test_protected_linkedin.py` hash gate).
- Stdout must stay 100% clean for MCP stdio compatibility; all logs go to stderr.
- API keys must never be logged or returned in plaintext over API / tool calls (use masked representation).
- Offline test suite `python -m pytest tests -q` must remain 100% passing.

## Review Focus

- Safe deletion of API keys from SQLite without residual traces.
- Accurate masking of diverse key formats (`AIza...`, `sk-proj-...`, `sk-ant-...`).
- Clean fallback to deterministic engine when keys are deleted.
- Offline mocking in tests for AI ping requests.

---

### Task 1: Update Default LLM Models to Latest Frontier Generation

**Files:**
- Modify: `jh/refit.py`
- Modify: `jh/config.py`
- Create: `tests/test_latest_models.py`

- [ ] **Step 1: Write test for latest model defaults**
  Create `tests/test_latest_models.py` verifying that default models are `gemini-3.8-flash` for Gemini, `gpt-5-mini` for OpenAI, and `claude-3-7-sonnet` for Anthropic, and that no `gpt-4o` or `gemini-2.5` appears as defaults.
- [ ] **Step 2: Run test to watch it fail**
  Run `python -m pytest tests/test_latest_models.py -q`.
- [ ] **Step 3: Update model defaults in `jh/refit.py`**
  Update default model strings in `get_active_ai_config` and `_call_llm`.
- [ ] **Step 4: Re-run test to verify it passes**
  Run `python -m pytest tests/test_latest_models.py -q`.

---

### Task 2: Build `jh/ai_manager.py` for Key Lifecycle & Masking

**Files:**
- Create: `jh/ai_manager.py`
- Create: `tests/test_ai_manager.py`

- [ ] **Step 1: Write test for AI Manager (status, set key, mask key, clear key)**
  In `tests/test_ai_manager.py`, test:
  - `get_ai_status()` reports active mode (`mcp_client` when no key vs `direct_api` when key exists).
  - Masking keys properly (e.g. `sk-proj-1234567890abcdef` -> `sk-proj-...cdef`).
  - `set_ai_key()` stores in SQLite and activates provider.
  - `clear_ai_key()` purges the key and reverts mode to MCP/deterministic.
- [ ] **Step 2: Run test to watch it fail**
  Run `python -m pytest tests/test_ai_manager.py -q`.
- [ ] **Step 3: Implement `jh/ai_manager.py`**
  Provide `mask_api_key()`, `get_ai_status()`, `set_ai_key()`, `clear_ai_key()`, and `test_ai_connection()`.
- [ ] **Step 4: Re-run test to verify it passes**
  Run `python -m pytest tests/test_ai_manager.py -q`.

---

### Task 3: Backend REST Endpoints in `jh/httpd.py`

**Files:**
- Modify: `jh/httpd.py`
- Create: `tests/test_httpd_ai_routes.py`

- [ ] **Step 1: Write tests for `/api/ai/*` routes**
  In `tests/test_httpd_ai_routes.py`, test:
  - `GET /api/ai/status` returns status, active mode, and masked key.
  - `POST /api/ai/config` saves provider and key.
  - `POST /api/ai/clear-key` deletes key and switches mode.
- [ ] **Step 2: Run test to watch it fail**
  Run `python -m pytest tests/test_httpd_ai_routes.py -q`.
- [ ] **Step 3: Implement routes in `jh/httpd.py`**
  Add handlers in `do_GET` and `do_POST`.
- [ ] **Step 4: Re-run test to verify it passes**
  Run `python -m pytest tests/test_httpd_ai_routes.py -q`.

---

### Task 4: CLI Commands in `run.py` (Windows, macOS, Linux)

**Files:**
- Modify: `run.py`
- Modify: `tests/test_run_and_mcp_config.py`

- [ ] **Step 1: Write tests for `run.py` CLI arguments**
  Add tests for `--set-key`, `--clear-key`, and `--ai-status`.
- [ ] **Step 2: Implement CLI flags in `run.py`**
  Support `--set-key`, `--provider`, `--model`, `--clear-key`, `--ai-status`, `--test-ai`.
- [ ] **Step 3: Run tests to verify they pass**
  Run `python -m pytest tests/test_run_and_mcp_config.py -q`.

---

### Task 5: Web Dashboard UI Deck for AI Provider & Key Management

**Files:**
- Modify: `public/index.html`
- Modify: `public/styles.css`
- Modify: `public/app.js`

- [ ] **Step 1: Add HTML markup in `public/index.html`**
  Add the AI Engine & Mode Control Deck under Tab 5 (`#tab-preferences`).
- [ ] **Step 2: Add styles in `public/styles.css`**
  Add styling for mode badges, provider dropdown, masked key input, and action buttons.
- [ ] **Step 3: Implement client logic in `public/app.js`**
  Add `loadAIStatus()`, `saveAIConfig()`, `clearAIKey()`, and `testAIConnection()`.

---

### Task 6: Documentation and Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update `README.md` with MCP vs Direct API mode documentation**
  Clearly document how to run with MCP, how to clone and use direct API keys, and how to switch or delete keys.
- [ ] **Step 2: Run full test suite**
  Execute `python -m pytest tests -q` to guarantee 100% green pass.

