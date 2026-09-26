"""Replace raw auth/network/quota failures with a message the agent can act on.

Google Ads API errors already carry a hint (`format_ads_error`); this layer
handles failures that happen before or around the API call (expired refresh
token, dead channel, quota), which otherwise reach the agent as stack-trace
text such as "503 Getting metadata from plugin failed ... invalid_grant".
"""

from __future__ import annotations

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from typing_extensions import override

from src.error_hints import transport_error_message


class ErrorMappingMiddleware(Middleware):
    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        except ToolError as e:
            message = transport_error_message(str(e))
            if message is None:
                raise
            raise ToolError(f"{message} (Detail: {str(e)[:300]})") from e
