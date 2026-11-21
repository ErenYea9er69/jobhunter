"""Scripted MCP Client & Test Agents for JobHunter E2E verification.

Simulates:
1. Lazy Agent (takes shortest path, attempts early search without answers).
2. Diligent Agent (inspects next_tool, answers interview questions with verbatim words).
3. Direct Client (Mode A: no subagent tool available).
4. Subagent Client (Mode B: has subagent capability).
"""
from __future__ import annotations

import os
from typing import Any, Optional
from jh import v5_tools, mcp_tools


class ScriptedMCPClient:
    """In-memory FastMCP / Python tool caller wrapping JobHunter MCP tools."""
    def __init__(self, mode: str = "direct", client_type: str = "diligent"):
        self.mode = mode  # "direct" or "subagent"
        self.client_type = client_type  # "diligent" or "lazy"
        self.session_id: Optional[str] = None
        self.ticket: Optional[str] = None
        self.last_reply: dict[str, Any] = {}
        self.history: list[dict[str, Any]] = []

    def call_tool(self, tool_name: str, **kwargs) -> dict[str, Any]:
        """Invoke JobHunter tool function directly, unpacking Result envelope."""
        fn = getattr(v5_tools, tool_name, None)
        if fn is None:
            fn = getattr(mcp_tools, tool_name, None)
        if fn is None:
            raise AttributeError(f"JobHunter tool '{tool_name}' not found.")

        try:
            res = fn(**kwargs)
        except Exception as exc:
            res = {"status": "error", "error": str(exc), "message_for_user": str(exc)}

        self.last_reply = res
        self.history.append({"tool": tool_name, "args": kwargs, "reply": res})

        if isinstance(res, dict):
            if "session_id" in res:
                self.session_id = res["session_id"]
            if "ticket" in res and res["ticket"]:
                self.ticket = res["ticket"]

        return res

    def jh_begin(self, resume_path: str = "", resume_text: str = "") -> dict[str, Any]:
        return self.call_tool("jh_begin", resume_path=resume_path, resume_text=resume_text)

    def jh_confirm(self, session_id: str = "", answers: dict | None = None, user_reply: str = "") -> dict[str, Any]:
        sid = session_id or self.session_id or ""
        return self.call_tool("jh_confirm", session_id=sid, answers=answers or {}, user_reply=user_reply)

    def jh_answer(self, session_id: str = "", answers: dict | None = None, user_reply: str = "") -> dict[str, Any]:
        sid = session_id or self.session_id or ""
        return self.call_tool("jh_answer", session_id=sid, answers=answers or {}, user_reply=user_reply)

    def jh_launch(self, session_id: str = "", ticket: str = "") -> dict[str, Any]:
        sid = session_id or self.session_id or ""
        t = ticket or self.ticket or ""
        return self.call_tool("jh_launch", session_id=sid, ticket=t)

    def jh_status(self, session_id: str = "", include_matches: bool = False) -> dict[str, Any]:
        sid = session_id or self.session_id or ""
        return self.call_tool("jh_status", session_id=sid, include_matches=include_matches)

    def jh_replace_resume(self, session_id: str = "", resume_path: str = "", resume_text: str = "") -> dict[str, Any]:
        sid = session_id or self.session_id or ""
        return self.call_tool("jh_replace_resume", session_id=sid, resume_path=resume_path, resume_text=resume_text)

    def jh_stop(self, session_id: str = "") -> dict[str, Any]:
        sid = session_id or self.session_id or ""
        return self.call_tool("jh_stop", session_id=sid)

    def search_jobs(self, **kwargs) -> dict[str, Any]:
        # Alias or direct search tool
        fn = getattr(v5_tools, "search_jobs", None) or getattr(mcp_tools, "search_jobs", None) or getattr(v5_tools, "jh_search", None)
        return fn(**kwargs) if fn else {"status": "needs_input", "error": "Search gated"}
