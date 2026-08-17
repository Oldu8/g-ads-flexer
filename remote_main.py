"""Read-only remote entrypoint for the Google Ads MCP server.

This is deliberately a *separate* entrypoint from ``main.py`` (which is
stdio-only, local, and mounts the full read+write tool surface). This module
exists so the server can be exposed over the network (e.g. deployed on
Railway) without any risk of a remote caller creating, updating, applying, or
deleting anything in a live Google Ads account:

- Only tool groups that are 100% query/reporting are mounted (verified by
  reading their `register_*_tools` source — no create/update/apply/mutate
  functions in any of them).
- The HTTP endpoint requires a bearer token (``MCP_BEARER_TOKEN``); the
  process refuses to start without one rather than falling back to an open
  endpoint.

Run locally:
    MCP_BEARER_TOKEN=some-secret uv run remote_main.py

On Railway, set ``MCP_BEARER_TOKEN`` and the ``GOOGLE_ADS_*`` credentials as
service variables; ``$PORT`` is provided automatically.
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastmcp import Context, FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

from src.sdk_client import GoogleAdsSdkClient, get_sdk_client, set_sdk_client
from src.servers.audience_insights_server import audience_insights_server
from src.servers.google_ads_field_server import google_ads_field_server
from src.servers.invoice_server import invoice_server
from src.servers.search_server import search_server
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


mcp = FastMCP(
    name="google-ads-mcp-readonly",
    instructions="""Read-only Google Ads MCP server for reporting/analysis.

    No tool exposed here can create, update, apply, or delete anything in the
    underlying Google Ads account — it only runs GAQL queries and reads
    metadata, so it is safe to call against a live account remotely.

    Tools:
    - search_* (search_campaigns, search_ad_groups, search_keywords,
      execute_query): run GAQL queries for cost, conversions, budgets, etc.
    - google_ads_field_*: discover and validate GAQL field names.
    - invoice_*: list billing invoices.
    - audience_insights_*: generate audience insight reports.
    - check_sdk_client_status: verify the Google Ads SDK client is ready.
    """,
    lifespan=lifespan,
    auth=_build_auth(),
)

for _prefix, _server in (
    ("search", search_server),
    ("google_ads_field", google_ads_field_server),
    ("invoice", invoice_server),
    ("audience_insights", audience_insights_server),
):
    mcp.mount(_server, prefix=_prefix)


@mcp.tool
async def check_sdk_client_status(ctx: Context) -> str:  # noqa: ARG001
    """Check if the Google Ads SDK client is initialized."""
    try:
        client = get_sdk_client()
        if client:
            return "Google Ads SDK client is initialized and ready"
    except Exception:
        pass
    return "Google Ads SDK client is not initialized"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"Starting HTTP transport on 0.0.0.0:{port}")
    mcp.run(transport="http", host="0.0.0.0", port=port)
