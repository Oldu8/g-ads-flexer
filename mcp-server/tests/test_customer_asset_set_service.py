"""Tests for CustomerAssetSetService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.customer_asset_set_service import (
    CustomerAssetSetServiceClient,
)
from google.ads.googleads.v25.services.types.customer_asset_set_service import (
    MutateCustomerAssetSetsResponse,
)

from src.services.assets.customer_asset_set_service import (
    CustomerAssetSetService,
    register_customer_asset_set_tools,
)


@pytest.fixture
def customer_asset_set_service(mock_sdk_client: Any) -> CustomerAssetSetService:
    """Create a CustomerAssetSetService instance with mocked dependencies."""
    mock_client = Mock(spec=CustomerAssetSetServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.assets.customer_asset_set_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = CustomerAssetSetService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_link_asset_set_to_customer(
    customer_asset_set_service: CustomerAssetSetService,
    mock_ctx: Context,
) -> None:
    """Test linking an asset set to the customer."""
    customer_id = "1234567890"
    mock_client = customer_asset_set_service.client  # type: ignore
    mock_client.mutate_customer_asset_sets.return_value = Mock(  # type: ignore
        spec=MutateCustomerAssetSetsResponse, results=[]
    )

    await customer_asset_set_service.link_asset_set_to_customer(
        ctx=mock_ctx, customer_id=customer_id, asset_set_id="1"
    )

    request = mock_client.mutate_customer_asset_sets.call_args[1]["request"]  # type: ignore
    create = request.operations[0].create
    assert create.asset_set == f"customers/{customer_id}/assetSets/1"
    assert create.customer == f"customers/{customer_id}"


@pytest.mark.asyncio
async def test_unlink_asset_set_from_customer(
    customer_asset_set_service: CustomerAssetSetService,
    mock_ctx: Context,
) -> None:
    """Test unlinking an asset set from the customer."""
    customer_id = "1234567890"
    mock_client = customer_asset_set_service.client  # type: ignore
    mock_client.mutate_customer_asset_sets.return_value = Mock(  # type: ignore
        spec=MutateCustomerAssetSetsResponse, results=[]
    )

    await customer_asset_set_service.unlink_asset_set_from_customer(
        ctx=mock_ctx, customer_id=customer_id, asset_set_id="1"
    )

    request = mock_client.mutate_customer_asset_sets.call_args[1]["request"]  # type: ignore
    assert request.operations[0].remove == (
        f"customers/{customer_id}/customerAssetSets/1"
    )


@pytest.mark.asyncio
async def test_error_handling(
    customer_asset_set_service: CustomerAssetSetService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = customer_asset_set_service.client  # type: ignore
    mock_client.mutate_customer_asset_sets.side_effect = google_ads_exception  # type: ignore

    with pytest.raises(Exception) as exc_info:
        await customer_asset_set_service.link_asset_set_to_customer(
            ctx=mock_ctx, customer_id="1234567890", asset_set_id="1"
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_customer_asset_set_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_customer_asset_set_tools(mock_mcp)

    assert isinstance(service, CustomerAssetSetService)
    assert mock_mcp.tool.call_count == 2  # type: ignore
