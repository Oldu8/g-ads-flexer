"""Tests for AccountRegistryService."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from fastmcp import Context

from src.services.review.account_registry_service import (
    AccountRegistryService,
    register_account_registry_tools,
)
from src.services.review.account_registry_store import AccountRegistryStore


@pytest.fixture
def account_registry_service(tmp_path: Path) -> AccountRegistryService:
    """Create an AccountRegistryService backed by a temp file (never the
    real snapshots/account_registry.json)."""
    store = AccountRegistryStore(path=tmp_path / "account_registry.json")
    return AccountRegistryService(store=store)


@pytest.mark.asyncio
async def test_list_accounts_empty(
    account_registry_service: AccountRegistryService,
    mock_ctx: Context,
) -> None:
    """Listing with nothing registered returns an empty list, not an error."""
    result = await account_registry_service.list_accounts(ctx=mock_ctx)
    assert result == []


@pytest.mark.asyncio
async def test_add_and_list_accounts(
    account_registry_service: AccountRegistryService,
    mock_ctx: Context,
) -> None:
    """Adding an account makes it show up in a subsequent list."""
    added = await account_registry_service.add_account(
        ctx=mock_ctx,
        alias="boo-ua",
        customer_id="569-031-8342",
        name="boo.ua (main)",
    )
    assert added == {
        "alias": "boo-ua",
        "customer_id": "5690318342",
        "name": "boo.ua (main)",
    }

    accounts = await account_registry_service.list_accounts(ctx=mock_ctx)
    assert accounts == [added]


@pytest.mark.asyncio
async def test_remove_account(
    account_registry_service: AccountRegistryService,
    mock_ctx: Context,
) -> None:
    """Removing a registered account reports removed=True and drops it."""
    await account_registry_service.add_account(
        ctx=mock_ctx, alias="boo-ua", customer_id="5690318342"
    )

    result = await account_registry_service.remove_account(ctx=mock_ctx, alias="boo-ua")

    assert result == {"alias": "boo-ua", "removed": True}
    assert await account_registry_service.list_accounts(ctx=mock_ctx) == []


@pytest.mark.asyncio
async def test_remove_account_not_registered(
    account_registry_service: AccountRegistryService,
    mock_ctx: Context,
) -> None:
    """Removing an alias that was never registered reports removed=False,
    not an error."""
    result = await account_registry_service.remove_account(ctx=mock_ctx, alias="nope")
    assert result == {"alias": "nope", "removed": False}


def test_register_account_registry_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_account_registry_tools(mock_mcp)

    assert isinstance(service, AccountRegistryService)
    assert mock_mcp.tool.call_count == 3  # type: ignore

    registered_tools = [call[0][0] for call in mock_mcp.tool.call_args_list]  # type: ignore
    tool_names = [tool.__name__ for tool in registered_tools]
    assert set(tool_names) == {"list_accounts", "add_account", "remove_account"}
