"""Local stdio entrypoint for the Google Ads MCP server.

Runs the server for one operator on this machine, with credentials from
`.env`, exposing one tool profile (`tool_profiles.yaml`; default `manager`).

    uv run main.py                       # the `manager` profile
    uv run main.py --profile read_only   # reads + fixes log only
    uv run main.py --profile all         # every tool (development only)
"""

import argparse
import asyncio
import os
import signal
import sys
import threading
from contextlib import asynccontextmanager
from types import FrameType
from typing import Any, AsyncGenerator, Optional

from fastmcp import FastMCP

from src.sdk_client import GoogleAdsSdkClient, set_sdk_client
from src.server_factory import create_server
from src.tool_profiles import DEFAULT_PROFILE, ProfileError, get_profile
from src.utils import get_logger, load_dotenv

logger = get_logger(__name__)

INSTRUCTIONS = """Google Ads MCP server for managing and analysing Google Ads accounts.

- Every tool takes `customer_id` (with or without hyphens; local account
  aliases also work).
- Use `search_execute_query` (GAQL) for reporting; check field names with the
  `google_ads_field_*` tools first. List results are capped: when a result
  says `truncated`, narrow the query instead of assuming something is missing.
- Record every change you make, with its expected outcome, in the fixes log
  (`fixes_log_*`), and review earlier fixes when asked how things went.
- Prefer the `pending_change_*` review flow for keyword, budget, bid-target,
  audience and shared-set changes so the user sees and approves them first."""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Ads MCP server (stdio)")
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"tool profile from tool_profiles.yaml (default: {DEFAULT_PROFILE})",
    )
    return parser.parse_args()


@asynccontextmanager
async def lifespan(app: Any) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """Manage Google Ads SDK client lifecycle."""
    logger.info("Starting Google Ads SDK API MCP server...")
    client = None
    try:
        client = GoogleAdsSdkClient()
        client.validate()
        set_sdk_client(client)
        logger.info("Google Ads SDK client initialized successfully")
        yield
    finally:
        logger.info("Shutting down Google Ads SDK API MCP server...")
        if client:
            client.close()


shutdown_event = asyncio.Event()


def signal_handler(signum: int, frame: Optional[FrameType]) -> None:  # noqa: ARG001
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    shutdown_event.set()

    def force_exit() -> None:
        logger.warning("Force exiting after timeout...")
        os._exit(0)

    threading.Timer(2.0, force_exit).start()


async def run_with_shutdown(mcp: FastMCP[Any], profile: str) -> None:
    """Run the MCP server with graceful shutdown support."""
    logger.info(f"Tool profile {profile!r}: {len(get_profile(profile))} tools")
    server_task = asyncio.create_task(mcp.run_async(transport="stdio"))
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    _, pending = await asyncio.wait(
        [server_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.info("Server stopped gracefully")


def main() -> None:
    args = parse_arguments()
    load_dotenv()
    try:
        mcp = create_server(
            args.profile,
            name="google-ads-mcp",
            instructions=INSTRUCTIONS,
            lifespan=lifespan,
        )
    except ProfileError as e:
        logger.error(str(e))
        sys.exit(2)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    try:
        asyncio.run(run_with_shutdown(mcp, args.profile))
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt during startup")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
