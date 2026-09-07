"""Account registry service - MCP tools for managing account aliases.

Pure local config management: these tools only ever read/write
`snapshots/account_registry.json` (see `account_registry_store.py`) - none
of them call the Google Ads API, so none of them go through the
propose/apply review gate (`pending_change_service.py`) - that gate exists
for changes to a live ad account, not for this server's own local config.
`add_account`/`remove_account` take effect immediately, same as any other
local-file operation in this codebase (`fixes_log`'s account-sheet map,
`pending_change`'s store).
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP

from src.services.review.account_registry_store import AccountRegistryStore
from src.utils import get_logger

logger = get_logger(__name__)


class AccountRegistryService:
    """Service for listing/registering/removing Google Ads account aliases."""

    def __init__(self, store: Optional[AccountRegistryStore] = None) -> None:
        """Initialize the account registry service."""
        self._store = store or AccountRegistryStore()

    async def list_accounts(self, ctx: Context) -> List[Dict[str, Any]]:
        """List every registered account alias.

        Args:
            ctx: FastMCP context

        Returns:
            List of {alias, customer_id, name} - empty if none registered
            yet (this deployment still works fine with raw customer_ids)
        """
        accounts = self._store.list_all()
        await ctx.log(
            level="info",
            message=f"{len(accounts)} account(s) registered",
        )
        return accounts

    async def add_account(
        self,
        ctx: Context,
        alias: str,
        customer_id: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register (or update) an account alias.

        This only edits local config - it does not touch the Google Ads
        account itself and does not verify the account is actually
        reachable with this deployment's credentials. Run a cheap read
        tool (e.g. `check_sdk_client_status`, or search campaigns) against
        the resolved customer_id afterward to confirm that separately.

        Args:
            ctx: FastMCP context
            alias: Short human name to register, e.g. "boo-ua" - every
                other tool's `customer_id` parameter will accept this
                afterward
            customer_id: The real numeric Google Ads customer ID (with or
                without hyphens)
            name: Optional display name, e.g. "boo.ua (main account)"

        Returns:
            The stored entry: {alias, customer_id, name}
        """
        entry = self._store.add(
            alias=alias, customer_id=customer_id.replace("-", ""), name=name
        )
        await ctx.log(
            level="info",
            message=f"Registered account alias '{alias}' -> {entry['customer_id']}",
        )
        return entry

    async def remove_account(self, ctx: Context, alias: str) -> Dict[str, Any]:
        """Remove a registered account alias.

        Only edits local config - does not touch the Google Ads account.

        Args:
            ctx: FastMCP context
            alias: The alias to remove

        Returns:
            {alias, removed} - removed is False if it wasn't registered
        """
        removed = self._store.remove(alias)
        await ctx.log(
            level="info",
            message=(
                f"Removed account alias '{alias}'"
                if removed
                else f"No account alias '{alias}' was registered"
            ),
        )
        return {"alias": alias, "removed": removed}


def create_account_registry_tools(
    service: AccountRegistryService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the account registry service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def list_accounts(ctx: Context) -> List[Dict[str, Any]]:
        """List every registered account alias, so an agent (or you) can
        see what short names are available instead of raw customer_ids.

        Returns:
            List of {alias, customer_id, name} - empty if none registered
            yet (raw customer_ids still work everywhere regardless)
        """
        return await service.list_accounts(ctx=ctx)

    async def add_account(
        ctx: Context,
        alias: str,
        customer_id: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register (or update) a short alias for a Google Ads account, so
        every other tool's `customer_id` parameter can use that alias
        instead of the raw numeric id from now on. Only edits local
        config - does not touch the Google Ads account, and does not
        verify this deployment's credentials can actually reach it (the
        account must be linked under this deployment's configured
        manager account - GOOGLE_ADS_LOGIN_CUSTOMER_ID - or a separate
        credential set is needed instead, see docs/ACCOUNT_SWITCHING.md).

        Args:
            alias: Short human name, e.g. "boo-ua"
            customer_id: The real numeric Google Ads customer ID (with or
                without hyphens)
            name: Optional display name, e.g. "boo.ua (main account)"

        Returns:
            The stored entry: {alias, customer_id, name}
        """
        return await service.add_account(
            ctx=ctx, alias=alias, customer_id=customer_id, name=name
        )

    async def remove_account(ctx: Context, alias: str) -> Dict[str, Any]:
        """Remove a registered account alias. Only edits local config -
        does not touch the Google Ads account.

        Args:
            alias: The alias to remove

        Returns:
            {alias, removed} - removed is False if it wasn't registered
        """
        return await service.remove_account(ctx=ctx, alias=alias)

    tools.extend(
        [
            list_accounts,
            add_account,
            remove_account,
        ]
    )
    return tools


def register_account_registry_tools(mcp: FastMCP[Any]) -> AccountRegistryService:
    """Register account registry tools with the MCP server.

    Returns the AccountRegistryService instance for testing purposes.
    """
    service = AccountRegistryService()
    tools = create_account_registry_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
