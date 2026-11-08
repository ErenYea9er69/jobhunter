"""AI Manager for JobHunter: MCP vs Direct API Dual-Engine Orchestrator.

Manages dynamic switching between:
1. External MCP Agent Mode (Zero API key needed; AI IDE like Claude or Cursor drives).
2. Direct Standalone API Mode (User provides their API key to run standalone in Web Dashboard & Extension).
3. Deterministic Mode (Local rules with Reviewer verification).

Supports latest 2026 frontier models: Gemini 3.8 Flash, GPT-5 Mini, Claude 3.7 Sonnet, DeepSeek Chat.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from typing import Any

from . import config, db, refit

log = logging.getLogger("jobhunter.ai_manager")

RECOMMENDED_MODELS: dict[str, list[str]] = {
    "gemini": ["gemini-3.8-flash", "gemini-3.1-pro", "gemini-3.5-flash"],
    "openai": ["gpt-5-mini", "o3-mini", "gpt-5"],
    "anthropic": ["claude-3-7-sonnet", "claude-3-5-haiku"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "groq": ["llama-3.3-70b-versatile", "qwen-2.5-coder-32b"],
    "mistral": ["mistral-large-latest", "pixtral-large-latest"],
    "ollama": ["llama3.3", "qwen2.5-coder"],
    "deterministic": [""],
    "auto": [""],
}


def mask_api_key(key: str) -> str:
    """Safely masks an API key for UI / logging display, revealing only prefix and suffix."""
    if not key:
        return ""
    clean = str(key).strip()
    if len(clean) <= 8:
        return "••••"

    if clean.startswith("sk-proj-"):
        prefix = "sk-proj-"
        tail = clean[-4:]
        return f"{prefix}••••{tail}"
    elif clean.startswith("sk-ant-"):
        prefix = "sk-ant-"
        tail = clean[-4:]
        return f"{prefix}••••{tail}"
    elif clean.startswith("AIza"):
        prefix = clean[:4]
        tail = clean[-4:]
        return f"{prefix}••••{tail}"

    prefix = clean[:4]
    tail = clean[-4:]
    return f"{prefix}••••{tail}"


def get_ai_status() -> dict[str, Any]:
    """Returns the current AI provider status, active mode, and masked key."""
    cfg = refit.get_active_ai_config()
    provider = cfg.get("provider", "deterministic")
    model = cfg.get("model", "")
    key = cfg.get("key", "")
    has_key = bool(key)

    mode = "direct_api" if (has_key or provider == "ollama") else "mcp_client"

    return {
        "status": "ok",
        "mode": mode,
        "provider": provider,
        "model": model,
        "key_configured": has_key,
        "masked_key": mask_api_key(key),
        "endpoint": cfg.get("endpoint", ""),
        "recommended_models": RECOMMENDED_MODELS,
        "available_providers": [p for p in RECOMMENDED_MODELS if p not in ("deterministic", "auto")],
    }


def set_ai_key(provider: str, api_key: str, model: str | None = None) -> dict[str, Any]:
    """Saves API key and activates Direct API mode."""
    prov = (provider or "gemini").strip().lower()
    key = api_key.strip()
    if not key:
        return {"success": False, "error": "API key cannot be empty"}

    setting_key = f"{prov}_api_key" if prov != "custom" else "custom_ai_key"
    db.set_setting(setting_key, key)
    db.set_setting("ai_provider", prov)

    selected_model = ""
    if model and model.strip():
        selected_model = model.strip()
    elif prov in RECOMMENDED_MODELS and RECOMMENDED_MODELS[prov][0]:
        selected_model = RECOMMENDED_MODELS[prov][0]

    if selected_model:
        db.set_setting("ai_model", selected_model)

    return {
        "success": True,
        "provider": prov,
        "model": db.get_setting("ai_model") or selected_model,
        "masked_key": mask_api_key(key),
        "mode": "direct_api",
    }


def clear_ai_key(provider: str | None = None) -> dict[str, Any]:
    """Clears stored API keys, seamlessly reverting to External MCP / Deterministic mode."""
    targets = []
    if provider:
        p = provider.strip().lower()
        targets.append(f"{p}_api_key" if p != "custom" else "custom_ai_key")
    else:
        for p in ["gemini", "openai", "anthropic", "deepseek", "groq", "mistral", "custom"]:
            targets.append(f"{p}_api_key" if p != "custom" else "custom_ai_key")

    with db.session() as c:
        for t in targets:
            c.execute("DELETE FROM settings WHERE key = ?", (t,))
        c.execute("DELETE FROM settings WHERE key = 'ai_model'")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai_provider', 'deterministic')")

    return {
        "success": True,
        "cleared_keys": targets,
        "mode": "mcp_client",
    }


def test_ai_connection(timeout_seconds: float = 8.0) -> dict[str, Any]:
    """Executes a lightweight health-check verification using the active configuration."""
    cfg = refit.get_active_ai_config()
    if not cfg.get("key") and cfg.get("provider") not in ("ollama",):
        return {
            "success": False,
            "error": "No API key configured. Configure an API key or run via MCP in Claude Desktop / Cursor.",
            "mode": "mcp_client",
        }

    try:
        t0 = time.time()
        res = refit._call_llm(
            system="Health check. Reply with 'PONG'.",
            user="PING",
            cfg=cfg,
        )
        latency = round((time.time() - t0) * 1000)
        return {
            "success": True,
            "latency_ms": latency,
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "response_preview": str(res).strip()[:30],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
        }
