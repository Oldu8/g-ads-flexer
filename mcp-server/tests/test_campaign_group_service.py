"""Tests for CampaignGroupService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.campaign_group_service import (
    CampaignGroupServiceClient,
)
from google.ads.googleads.v25.services.types.campaign_group_service import (
    MutateCampaignGroupsResponse,
)

from src.services.campaign.campaign_group_service import (
    CampaignGroupService,
    register_campaign_group_tools,
)


@pytest.fixture
def campaign_group_service(mock_sdk_client: Any) -> CampaignGroupService:
    """Create a CampaignGroupService instance with mocked dependencies."""
    mock_client = Mock(spec=CampaignGroupServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.campaign.campaign_group_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = CampaignGroupService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_create_campaign_group(
    campaign_group_service: CampaignGroupService,
    mock_ctx: Context,
) -> None:
    """Test creating a campaign group."""
    customer_id = "1234567890"
    mock_response = Mock(spec=MutateCampaignGroupsResponse)
    mock_response.results = [
        Mock(resource_name=f"customers/{customer_id}/campaignGroups/1")
    ]
    mock_client = campaign_group_service.client  # type: ignore
    mock_client.mutate_campaign_groups.return_value = mock_response  # type: ignore

    await campaign_group_service.create_campaign_group(
        ctx=mock_ctx, customer_id=customer_id, name="Brand campaigns"
    )

    mock_client.mutate_campaign_groups.assert_called_once()  # type: ignore
    request = mock_client.mutate_campaign_groups.call_args[1]["request"]  # type: ignore
    assert request.customer_id == customer_id
    assert request.operations[0].create.name == "Brand campaigns"
    assert request.operations[0].create.status == 2  # ENABLED


@pytest.mark.asyncio
async def test_update_campaign_group(
    campaign_group_service: CampaignGroupService,
    mock_ctx: Context,
) -> None:
    """Test updating a campaign group builds the right field mask."""
    customer_id = "1234567890"
    mock_client = campaign_group_service.client  # type: ignore
    mock_client.mutate_campaign_groups.return_value = Mock(  # type: ignore
        spec=MutateCampaignGroupsResponse, results=[]
    )

    await campaign_group_service.update_campaign_group(
        ctx=mock_ctx,
        customer_id=customer_id,
        campaign_group_id="1",
        status="REMOVED",
    )

    request = mock_client.mutate_campaign_groups.call_args[1]["request"]  # type: ignore
    operation = request.operations[0]
    assert operation.update.resource_name == (
        f"customers/{customer_id}/campaignGroups/1"
    )
    assert list(operation.update_mask.paths) == ["status"]


@pytest.mark.asyncio
async def test_remove_campaign_group(
    campaign_group_service: CampaignGroupService,
    mock_ctx: Context,
) -> None:
    """Test removing a campaign group."""
    customer_id = "1234567890"
    mock_client = campaign_group_service.client  # type: ignore
    mock_client.mutate_campaign_groups.return_value = Mock(  # type: ignore
        spec=MutateCampaignGroupsResponse, results=[]
    )

    await campaign_group_service.remove_campaign_group(
        ctx=mock_ctx, customer_id=customer_id, campaign_group_id="1"
    )

    request = mock_client.mutate_campaign_groups.call_args[1]["request"]  # type: ignore
    assert request.operations[0].remove == (f"customers/{customer_id}/campaignGroups/1")


@pytest.mark.asyncio
async def test_error_handling(
    campaign_group_service: CampaignGroupService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = campaign_group_service.client  # type: ignore
    mock_client.mutate_campaign_groups.side_effect = google_ads_exception  # type: ignore

    with pytest.raises(Exception) as exc_info:
        await campaign_group_service.create_campaign_group(
            ctx=mock_ctx, customer_id="1234567890", name="X"
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_campaign_group_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_campaign_group_tools(mock_mcp)

    assert isinstance(service, CampaignGroupService)
    assert mock_mcp.tool.call_count == 3  # type: ignore
