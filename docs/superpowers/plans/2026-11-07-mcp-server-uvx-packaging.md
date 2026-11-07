# MCP Server and UVX Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn JobHunter into a fully-functional MCP server package installable with a single command (`uvx --from git+https://github.com/ErenYea9er69/jobhunter jobhunter-mcp`), exposing core tools over stdio without stdout pollution, storing data in `~/.jobhunter` (configurable via `JH_DATA_DIR`), keeping the web app working, and adding Claude Desktop configuration instructions.

**Architecture:** Use the official Python `mcp` SDK (`FastMCP`) over stdio transport. Expose core job hunting tools (`search_jobs`, `score_fit`/`score_job`, `rewrite_resume`/`tailor_resume`, `add_to_tracker`/`track_application`) along with full team specialist tools. Configure `jh/config.py` to route data to `~/.jobhunter` by default or `JH_DATA_DIR` when specified, ensuring tests stay hermetic using `JH_DATA_DIR` temp dirs.

**Tech Stack:** Python 3.11+, `mcp[cli]>=1.9,<2`, `FastMCP`, `curl_cffi`, `pypdf`, `setuptools`, `uv`/`uvx`.

**Spec:** User prompt instructions.

## Global Constraints

- Never write to `sys.stdout` except for JSON-RPC transport frames handled by FastMCP stdio. All logging and diagnostics must go to `sys.stderr`.
- Do not edit protected LinkedIn code or modify signatures forbidden by `AGENTS.md`.
- Keep the current web app (`desktop.py`, `jh/httpd.py`) fully functional.
- Maintain test suite integrity: all offline tests in `tests/` must pass.
- Default data directory must be `~/.jobhunter` in the user's home directory, overridable by `JH_DATA_DIR`.

## Review Focus

1. **Stdout Pollution:** Any rogue `print()` to stdout corrupts JSON-RPC messages and breaks MCP clients (e.g. Claude Desktop, MCP Inspector).
2. **Fresh Directory Execution:** Running `jobhunter-mcp` from a clean folder with no git repo or local `./data` must successfully initialize without crashing.
3. **Tool Discoverability in Inspector:** Core tools (`search_jobs`, `score_fit`, `rewrite_resume`, `add_to_tracker`, and their counterparts) must be listed and functional in MCP Inspector.
4. **Hermetic Test Isolation:** pytest must not pollute or read the user's real `~/.jobhunter` database.
5. **Web App Compatibility:** `desktop.py` and `jh/httpd.py` must correctly read/write to the user data directory and launch without errors.

---

### Task 1: Dependencies and Package Configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`

- [ ] Check dependencies in `requirements.txt` and ensure `mcp[cli]>=1.9,<2` is declared.
- [ ] Update `pyproject.toml` with:
  - Package name `jobhunter-mcp`
  - Dependencies matching `requirements.txt`
  - Script entry point: `jobhunter-mcp = "mcp_server:main"`
  - Package data for `prompts/**` so prompts are included in built distributions.
- [ ] Build test wheel with `python -m pip wheel --no-deps -w scratch .` and verify `mcp_server.py`, `jh/`, and `prompts/` are included.

### Task 2: Home Data Directory and Configuration (`JH_DATA_DIR`)

**Files:**
- Modify: `jh/config.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_mcp_server.py`

- [ ] Update `jh/config.py`:
  - Define `DEFAULT_DATA_DIR = os.environ.get("JH_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".jobhunter")`
  - Set `DATA_DIR = os.environ.get("JH_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".jobhunter")`
  - In `configure_mcp_environment`: respect `JH_DATA_DIR` if set, else fallback to home `.jobhunter` (or workspace `.jobhunter` if explicitly running in a workspace with one).
  - Automatically create data directory and migrate existing `data/engine.db` if `~/.jobhunter/engine.db` doesn't exist yet.
- [ ] Update `tests/conftest.py`:
  - Set `monkeypatch.setenv("JH_DATA_DIR", str(tmp_path / ".jobhunter"))` so tests always run isolated.
- [ ] Update `tests/test_mcp_server.py`:
  - Ensure `setUp` sets `os.environ["JH_DATA_DIR"] = str(self.ws_path / ".jobhunter")` for isolated test runs.
- [ ] Run test suite `python -m pytest tests -q` to verify hermetic test execution.

### Task 3: Wrap Core Tools and Default Surface in `mcp_server.py`

**Files:**
- Modify: `mcp_server.py`
- Modify: `jh/team/roles.py`
- Modify: `jh/mcp_tools.py`

- [ ] Ensure `mcp_server.py` uses FastMCP with stdio transport, sends all logs to `sys.stderr`, and never writes to `sys.stdout`.
- [ ] In `jh/mcp_tools.py` and `jh/team/roles.py`:
  - Add explicit tools/aliases with concise descriptions:
    - `search_jobs`: "Search jobs across multiple sources with filters, ranked by fit against your resume."
    - `score_fit`: "Score fit between your resume and a job description. Returns match score, breakdown, and missing skills." (wraps `score_job`)
    - `rewrite_resume`: "Rewrite resume bullets tailored to a target job while strictly preserving factual accuracy." (wraps `tailor_resume`)
    - `add_to_tracker`: "Add a job application to your local application tracking pipeline." (wraps `track_application`)
  - Update `jh/team/roles.py` so `analyst` owns `score_fit`, `writer` owns `rewrite_resume`, and `ops` owns `add_to_tracker`, keeping `ROSTER` and `_OWNER` strictly consistent.
- [ ] Ensure default surface in `mcp_server.py:main()` provides full tool availability (including the 4 core tools and all specialist tools) while supporting `--surface team` if desired.
- [ ] Verify with `python mcp_server.py --check` that tools list properly to stderr.

### Task 4: Web App Compatibility Verification

**Files:**
- Check: `desktop.py`
- Check: `jh/httpd.py`

- [ ] Verify `desktop.py` runs and correctly uses `config.DATA_DIR`.
- [ ] Test starting `desktop.py --no-browser --port 8769` and verify endpoints respond properly using stderr logging.
- [ ] Run desktop tests: `python -m pytest tests/test_desktop_launcher.py`.

### Task 5: Documentation (README.md) Updates

**Files:**
- Modify: `README.md`

- [ ] Add the single-command install instructions:
  ```bash
  uvx --from git+https://github.com/ErenYea9er69/jobhunter jobhunter-mcp
  ```
- [ ] Add the `claude mcp add` command:
  ```bash
  claude mcp add jobhunter -- uvx --from git+https://github.com/ErenYea9er69/jobhunter jobhunter-mcp
  ```
- [ ] Add the Claude Desktop configuration JSON block (`claude_desktop_config.json` format).
- [ ] Document `JH_DATA_DIR` and `JH_WORKSPACE` configuration options.

### Task 6: Local MCP Testing & Clean Folder Verification

**Files:**
- Scratch testing directory

- [ ] Run full test suite: `python -m pytest tests -q`.
- [ ] Test the MCP server locally with standard stdio handshake (JSON-RPC `initialize`, `tools/list`).
- [ ] Test running `uvx --from . jobhunter-mcp --check` from a clean temporary directory outside the repo.
- [ ] Verify `~/.jobhunter` directory creation and that no errors occur.

