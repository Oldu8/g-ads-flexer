"""Render what an MCP client sees in `tools/list` for a profile.

Used by `scripts/dump_tools_list.py` (golden snapshots) and
`tests/test_tool_surface.py` (snapshot and size-budget checks), so both
measure exactly the same payload: the real MCP listing, through the
profile middleware, without the lifespan (no credentials needed).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from fastmcp import Client

from src.server_factory import create_server

# Serialized `tools/list` size ceilings, in characters (~4 chars per token).
SIZE_BUDGETS: Dict[str, int] = {
    "manager": 100_000,  # ~25k tokens
    "read_only": 40_000,  # ~10k tokens
}


async def render_tools_list(profile: str) -> List[Dict[str, Any]]:
    """The profile's `tools/list` payload, sorted by tool name."""
    mcp = create_server(profile, name="surface", instructions="surface")
    async with Client(mcp) as client:
        tools = await client.list_tools()
    payload = [
        t.model_dump(mode="json", exclude_none=True, by_alias=True) for t in tools
    ]
    return sorted(payload, key=lambda t: t["name"])


def payload_size(payload: List[Dict[str, Any]]) -> int:
    """Characters of the compact JSON a client receives."""
    return len(json.dumps(payload, ensure_ascii=False))


def largest_tools(payload: List[Dict[str, Any]], n: int = 3) -> List[str]:
    sized = sorted(
        ((len(json.dumps(t, ensure_ascii=False)), t["name"]) for t in payload),
        reverse=True,
    )
    return [f"{name} ({size} chars)" for size, name in sized[:n]]
