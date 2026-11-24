"""MCP Elicitation helper with graceful chat fallback.

Supports the Model Context Protocol Elicitation specification (form/URL)
when supported by the connecting MCP client, otherwise falls back to
standard chat prompt envelopes.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("jobhunter.elicitation")


def can_elicit(mcp_context: Any = None) -> bool:
    """Check if the connecting MCP client advertises elicitation capabilities."""
    if not mcp_context:
        return False
    try:
        caps = getattr(mcp_context, "client_capabilities", None)
        if caps and getattr(caps, "elicitation", None):
            return True
    except Exception as e:
        log.debug("Error checking elicitation capabilities: %s", e)
    return False


async def request_elicitation(
    mcp_context: Any,
    prompt: str,
    schema: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Attempt an MCP elicitation request if client supports it; returns None on fallback."""
    if not can_elicit(mcp_context):
        return None
    try:
        from mcp.types import ElicitRequestFormParams
        # Request form elicitation from client
        res = await mcp_context.elicit(
            params=ElicitRequestFormParams(
                message=prompt,
                requestedSchema=schema or {},
            )
        )
        return res
    except Exception as e:
        log.info("Client does not support elicitation or request failed: %s; falling back to chat", e)
        return None
