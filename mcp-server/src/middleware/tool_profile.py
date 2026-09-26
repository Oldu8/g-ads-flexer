"""Expose exactly one tool profile, annotated and with bounded list results.

Applies to both `tools/list` and `tools/call`: filtering only the listing
would leave every hidden tool callable by name, which is an authorization
hole on a hosted endpoint. Annotations and the list envelope are attached
here, from `src/tool_registry.py`, so no server module changes.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Mapping, Optional, Sequence

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import Tool, ToolResult
from typing_extensions import override

from src.tool_registry import TOOL_REGISTRY, ToolMeta
from src.utils import list_envelope, row_cap


def annotations_for(meta: ToolMeta) -> mt.ToolAnnotations:
    """`readOnlyHint` for reads; an explicit `destructiveHint` for writes.

    MCP defaults `destructiveHint` to true for non-read-only tools, so
    non-destructive writes must say false explicitly.
    """
    if meta.kind == "read":
        return mt.ToolAnnotations(readOnlyHint=True)
    return mt.ToolAnnotations(readOnlyHint=False, destructiveHint=meta.destructive)


def is_wrapped_list_schema(schema: Optional[Dict[str, Any]]) -> bool:
    """FastMCP's output schema for a tool returning a list: `{result: [...]}`."""
    if not schema or not schema.get("x-fastmcp-wrap-result"):
        return False
    result = schema.get("properties", {}).get("result", {})
    return result.get("type") == "array"


def envelope_schema(list_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Output schema for `src.utils.list_envelope` results."""
    return {
        "type": "object",
        "properties": {
            "items": list_schema["properties"]["result"],
            "returned": {"type": "integer"},
            "truncated": {"type": "boolean"},
            "warning": {"type": "string"},
        },
        "required": ["items", "returned", "truncated"],
    }


class ToolProfileMiddleware(Middleware):
    def __init__(
        self,
        profile_name: str,
        tools: FrozenSet[str],
        registry: Mapping[str, ToolMeta] = TOOL_REGISTRY,
    ) -> None:
        self.profile_name = profile_name
        self.tools = tools
        self.registry = registry

    @override
    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        listed: list[Tool] = []
        for tool in await call_next(context):
            if tool.key not in self.tools:
                continue
            meta = self.registry[tool.key]
            update: Dict[str, Any] = {"annotations": annotations_for(meta)}
            if meta.kind == "read" and is_wrapped_list_schema(tool.output_schema):
                update["output_schema"] = envelope_schema(tool.output_schema or {})
            listed.append(tool.model_copy(update=update))
        return listed

    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        name = context.message.name
        if name not in self.tools:
            raise ToolError(
                f"Tool {name!r} is not available in profile {self.profile_name!r}."
            )
        result = await call_next(context)
        if self.registry[name].kind != "read":
            return result
        structured = result.structured_content
        if (
            isinstance(structured, dict)
            and set(structured) == {"result"}
            and isinstance(structured["result"], list)
        ):
            return ToolResult(
                structured_content=list_envelope(structured["result"], row_cap()),
                meta=result.meta,
            )
        return result
