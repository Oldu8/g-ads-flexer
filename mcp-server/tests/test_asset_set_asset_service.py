"""Tests for AssetSetAssetService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.asset_set_asset_service import (
    AssetSetAssetServiceClient,
)
from google.ads.googleads.v25.services.types.asset_set_asset_service import (
    MutateAssetSetAssetsResponse,
)

from src.services.assets.asset_set_asset_service import (
    AssetSetAssetService,
    register_asset_set_asset_tools,
)


@pytest.fixture
def asset_set_asset_service(mock_sdk_client: Any) -> AssetSetAssetService:
    """Create an AssetSetAssetService instance with mocked dependencies."""
    mock_client = Mock(spec=AssetSetAssetServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.assets.asset_set_asset_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = AssetSetAssetService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_add_asset_to_asset_set(
    asset_set_asset_service: AssetSetAssetService,
    mock_ctx: Context,
) -> None:
    """Test adding an asset to an asset set."""
    customer_id = "1234567890"
    mock_client = asset_set_asset_service.client  # type: ignore
    mock_client.mutate_asset_set_assets.return_value = Mock(  # type: ignore
        spec=MutateAssetSetAssetsResponse, results=[]
    )

    await asset_set_asset_service.add_asset_to_asset_set(
        ctx=mock_ctx, customer_id=customer_id, asset_set_id="1", asset_id="2"
    )

    request = mock_client.mutate_asset_set_assets.call_args[1]["request"]  # type: ignore
    create = request.operations[0].create
    assert create.asset_set == f"customers/{customer_id}/assetSets/1"
    assert create.asset == f"customers/{customer_id}/assets/2"


@pytest.mark.asyncio
async def test_remove_asset_from_asset_set(
    asset_set_asset_service: AssetSetAssetService,
    mock_ctx: Context,
) -> None:
    """Test removing an asset from an asset set."""
    customer_id = "1234567890"
    mock_client = asset_set_asset_service.client  # type: ignore
    mock_client.mutate_asset_set_assets.return_value = Mock(  # type: ignore
        spec=MutateAssetSetAssetsResponse, results=[]
    )

    await asset_set_asset_service.remove_asset_from_asset_set(
        ctx=mock_ctx, customer_id=customer_id, asset_set_id="1", asset_id="2"
    )

    request = mock_client.mutate_asset_set_assets.call_args[1]["request"]  # type: ignore
    assert request.operations[0].remove == (
        f"customers/{customer_id}/assetSetAssets/1~2"
    )


@pytest.mark.asyncio
async def test_error_handling(
    asset_set_asset_service: AssetSetAssetService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = asset_set_asset_service.client  # type: ignore
    mock_client.mutate_asset_set_assets.side_effect = google_ads_exception  # type: ignore

    with pytest.raises(Exception) as exc_info:
        await asset_set_asset_service.add_asset_to_asset_set(
            ctx=mock_ctx, customer_id="1234567890", asset_set_id="1", asset_id="2"
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_asset_set_asset_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_asset_set_asset_tools(mock_mcp)

    assert isinstance(service, AssetSetAssetService)
    assert mock_mcp.tool.call_count == 2  # type: ignore
