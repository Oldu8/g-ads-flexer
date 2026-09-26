"""Read-only remote entrypoint for the Google Ads MCP server.

A separate entrypoint from ``main.py`` (local stdio) so the server can be
exposed over the network (deployed on Railway) without any tool that can
change a Google Ads account: it serves the computed ``read_only`` profile
(``src/tool_profiles.py``), i.e. the ``manager`` profile's reads plus the
fixes log, derived from ``src/tool_registry.py`` rather than from a
hand-maintained list of servers. The HTTP endpoint requires a bearer token
(``MCP_BEARER_TOKEN``); the process refuses to start without one.

Replaced by the multi-tenant ``hosted_main.py`` in Phase C
(``openspec/changes/hosted-multitenant-writes``).

Run locally:
    MCP_BEARER_TOKEN=some-secret uv run remote_main.py
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

from src.sdk_client import GoogleAdsSdkClient, set_sdk_client
from src.server_factory import create_server
from src.tool_profiles import READ_ONLY_PROFILE
from src.utils import get_logger, load_dotenv

logger = get_logger(__name__)

# Unlike main.py (always run locally, next to a real .env), this entrypoint
# runs deployed, where credentials come from real platform env vars (e.g.
# Railway service variables) and there is no .env file. src.utils.load_dotenv
# raises FileNotFoundError when the file is missing, so only call it when a
# .env is actually present (e.g. local `uv run remote_main.py` testing).
if Path(".env").exists():
    load_dotenv()


@asynccontextmanager
async def lifespan(app: Any) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """Manage Google Ads SDK client lifecycle."""
    logger.info("Starting Google Ads MCP server (remote, read-only)...")
    client = None
    try:
        client = GoogleAdsSdkClient()
        client.validate()
        set_sdk_client(client)
        logger.info("Google Ads SDK client initialized successfully")
        yield
    finally:
        logger.info("Shutting down Google Ads MCP server...")
        if client:
            client.close()


def _build_auth() -> StaticTokenVerifier:
    """Require a bearer token; refuse to start an open server otherwise."""
    token = os.environ.get("MCP_BEARER_TOKEN")
    if not token:
        logger.error(
            "MCP_BEARER_TOKEN is not set. Refusing to start an unauthenticated "
            "MCP server on a public transport."
        )
        sys.exit(1)
    return StaticTokenVerifier(tokens={token: {"client_id": "owner", "scopes": []}})


mcp = create_server(
    READ_ONLY_PROFILE,
    name="google-ads-mcp-readonly",
    instructions="""Read-only Google Ads MCP server for reporting and analysis.

    No tool exposed here can create, update, apply or delete anything in the
    Google Ads account. Use search_execute_query (GAQL) for reporting and the
    google_ads_field_* tools to check field names; the fixes log records and
    reviews changes made elsewhere.
    """,
    lifespan=lifespan,
    auth=_build_auth(),
)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"Starting HTTP transport on 0.0.0.0:{port}")
    mcp.run(transport="http", host="0.0.0.0", port=port)
