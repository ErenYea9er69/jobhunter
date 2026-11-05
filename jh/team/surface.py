"""Which tools the client's AI can see.

``team`` (the default for ``python mcp_server.py``): only the CEO tools. The specialists still run, but
only when the CEO calls them. ``full``: every tool, as in version 2.1.
Hidden tools stay callable in code. Only the list the client receives changes.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .tools import TEAM_TOOLS

SURFACES = ("team", "full")


def resolve(value: str | None) -> str:
    v = (value or os.environ.get("JH_SURFACE") or "team").strip().lower()
    return v if v in SURFACES else "team"


class TeamMCP(FastMCP):
    """FastMCP that can show the client a smaller tool list."""

    surface: str = "full"

    async def list_tools(self) -> list[Any]:
        tools = await super().list_tools()
        if self.surface == "team":
            return [t for t in tools if t.name in TEAM_TOOLS]
        return tools
