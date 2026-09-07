"""Tests for AutomaticallyCreatedAssetRemovalService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.automatically_created_asset_removal_service import (
    AutomaticallyCreatedAssetRemovalServiceClient,
)
from google.ads.googleads.v25.services.types.automatically_created_asset_removal_service import (
    RemoveCampaignAutomaticallyCreatedAssetResponse,
)

from src.services.assets.automatically_created_asset_removal_service import (
    AutomaticallyCreatedAssetRemovalService,
    register_automatically_created_asset_removal_tools,
)


@pytest.fixture
def automatically_created_asset_removal_service(
    mock_sdk_client: Any,
) -> AutomaticallyCreatedAssetRemovalService:
    """Create an AutomaticallyCreatedAssetRemovalService with mocked deps."""
    mock_client = Mock(spec=AutomaticallyCreatedAssetRemovalServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.assets.automatically_created_asset_removal_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = AutomaticallyCreatedAssetRemovalService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_remove_campaign_automatically_created_asset(
    automatically_created_asset_removal_service: AutomaticallyCreatedAssetRemovalService,
    mock_ctx: Context,
) -> None:
    """Test removing an automatically created asset from a campaign."""
    customer_id = "1234567890"
    mock_client = automatically_created_asset_removal_service.client  # type: ignore
    mock_client.remove_campaign_automatically_created_asset.return_value = (  # type: ignore
        Mock(spec=RemoveCampaignAutomaticallyCreatedAssetResponse)
    )

    await automatically_created_asset_removal_service.remove_campaign_automatically_created_asset(
        ctx=mock_ctx,
        customer_id=customer_id,
        campaign_id="111",
        asset_id="222",
        field_type="HEADLINE",
    )

    mock_client.remove_campaign_automatically_created_asset.assert_called_once()  # type: ignore
    call_args = mock_client.remove_campaign_automatically_created_asset.call_args  # type: ignore
    request = call_args[1]["request"]
    assert request.customer_id == customer_id
    operation = request.operations[0]
    assert operation.campaign == f"customers/{customer_id}/campaigns/111"
    assert operation.asset == f"customers/{customer_id}/assets/222"


@pytest.mark.asyncio
async def test_error_handling(
    automatically_created_asset_removal_service: AutomaticallyCreatedAssetRemovalService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = automatically_created_asset_removal_service.client  # type: ignore
    mock_client.remove_campaign_automatically_created_asset.side_effect = (  # type: ignore
        google_ads_exception
    )

    with pytest.raises(Exception) as exc_info:
        await automatically_created_asset_removal_service.remove_campaign_automatically_created_asset(
            ctx=mock_ctx,
            customer_id="1234567890",
            campaign_id="111",
            asset_id="222",
            field_type="HEADLINE",
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_automatically_created_asset_removal_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_automatically_created_asset_removal_tools(mock_mcp)

    assert isinstance(service, AutomaticallyCreatedAssetRemovalService)
    assert mock_mcp.tool.call_count == 1  # type: ignore
