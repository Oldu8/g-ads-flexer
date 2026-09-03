"""Tests for CampaignGoalConfigService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.campaign_goal_config_service import (
    CampaignGoalConfigServiceClient,
)
from google.ads.googleads.v25.services.types.campaign_goal_config_service import (
    MutateCampaignGoalConfigsResponse,
)

from src.services.campaign.campaign_goal_config_service import (
    CampaignGoalConfigService,
    register_campaign_goal_config_tools,
)


@pytest.fixture
def campaign_goal_config_service(
    mock_sdk_client: Any,
) -> CampaignGoalConfigService:
    """Create a CampaignGoalConfigService instance with mocked dependencies."""
    mock_client = Mock(spec=CampaignGoalConfigServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.campaign.campaign_goal_config_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = CampaignGoalConfigService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_link_campaign_to_goal_retention(
    campaign_goal_config_service: CampaignGoalConfigService,
    mock_ctx: Context,
) -> None:
    """Test linking a campaign to a CUSTOMER_RETENTION goal."""
    customer_id = "1234567890"
    mock_client = campaign_goal_config_service.client  # type: ignore
    mock_client.mutate_campaign_goal_configs.return_value = Mock(  # type: ignore
        spec=MutateCampaignGoalConfigsResponse, results=[]
    )

    await campaign_goal_config_service.link_campaign_to_goal(
        ctx=mock_ctx,
        customer_id=customer_id,
        campaign_id="111",
        goal_id="5",
        goal_type="CUSTOMER_RETENTION",
        target_option="TARGET_ALL",
        value_multiplier=1.2,
    )

    request = mock_client.mutate_campaign_goal_configs.call_args[1][  # type: ignore
        "request"
    ]
    create = request.operations[0].create
    assert create.campaign == f"customers/{customer_id}/campaigns/111"
    assert create.goal == f"customers/{customer_id}/goals/5"
    assert (
        create.campaign_retention_settings.value_settings_override.value_multiplier
        == 1.2
    )
    assert create.campaign_retention_settings.target_option == 2  # TARGET_ALL


@pytest.mark.asyncio
async def test_link_campaign_to_goal_loyalty_retention(
    campaign_goal_config_service: CampaignGoalConfigService,
    mock_ctx: Context,
) -> None:
    """Test linking a campaign to a LOYALTY_RETENTION goal sets its bools."""
    customer_id = "1234567890"
    mock_client = campaign_goal_config_service.client  # type: ignore
    mock_client.mutate_campaign_goal_configs.return_value = Mock(  # type: ignore
        spec=MutateCampaignGoalConfigsResponse, results=[]
    )

    await campaign_goal_config_service.link_campaign_to_goal(
        ctx=mock_ctx,
        customer_id=customer_id,
        campaign_id="111",
        goal_id="5",
        goal_type="LOYALTY_RETENTION",
        enable_bid_adjustments_for_loyalty_members=True,
        show_targeted_loyalty_member_benefits_in_pla=False,
    )

    request = mock_client.mutate_campaign_goal_configs.call_args[1][  # type: ignore
        "request"
    ]
    create = request.operations[0].create
    settings = create.campaign_loyalty_retention_settings
    assert settings.enable_bid_adjustments_for_loyalty_members is True
    assert settings.show_targeted_loyalty_member_benefits_in_pla is False


@pytest.mark.asyncio
async def test_update_campaign_goal_config(
    campaign_goal_config_service: CampaignGoalConfigService,
    mock_ctx: Context,
) -> None:
    """Test updating a campaign goal config builds the right field mask."""
    customer_id = "1234567890"
    mock_client = campaign_goal_config_service.client  # type: ignore
    mock_client.mutate_campaign_goal_configs.return_value = Mock(  # type: ignore
        spec=MutateCampaignGoalConfigsResponse, results=[]
    )

    await campaign_goal_config_service.update_campaign_goal_config(
        ctx=mock_ctx,
        customer_id=customer_id,
        campaign_id="111",
        goal_id="5",
        goal_type="NEW_CUSTOMER_ACQUISITION",
        value_multiplier=2.0,
    )

    request = mock_client.mutate_campaign_goal_configs.call_args[1][  # type: ignore
        "request"
    ]
    operation = request.operations[0]
    assert operation.update.resource_name == (
        f"customers/{customer_id}/campaignGoalConfigs/111~5"
    )
    assert list(operation.update_mask.paths) == [
        "campaign_new_customer_acquisition_settings"
    ]


@pytest.mark.asyncio
async def test_unlink_campaign_from_goal(
    campaign_goal_config_service: CampaignGoalConfigService,
    mock_ctx: Context,
) -> None:
    """Test unlinking a campaign from a goal."""
    customer_id = "1234567890"
    mock_client = campaign_goal_config_service.client  # type: ignore
    mock_client.mutate_campaign_goal_configs.return_value = Mock(  # type: ignore
        spec=MutateCampaignGoalConfigsResponse, results=[]
    )

    await campaign_goal_config_service.unlink_campaign_from_goal(
        ctx=mock_ctx, customer_id=customer_id, campaign_id="111", goal_id="5"
    )

    request = mock_client.mutate_campaign_goal_configs.call_args[1][  # type: ignore
        "request"
    ]
    assert request.operations[0].remove == (
        f"customers/{customer_id}/campaignGoalConfigs/111~5"
    )


@pytest.mark.asyncio
async def test_error_handling(
    campaign_goal_config_service: CampaignGoalConfigService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = campaign_goal_config_service.client  # type: ignore
    mock_client.mutate_campaign_goal_configs.side_effect = (  # type: ignore
        google_ads_exception
    )

    with pytest.raises(Exception) as exc_info:
        await campaign_goal_config_service.link_campaign_to_goal(
            ctx=mock_ctx,
            customer_id="1234567890",
            campaign_id="111",
            goal_id="5",
            goal_type="CUSTOMER_RETENTION",
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_campaign_goal_config_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_campaign_goal_config_tools(mock_mcp)

    assert isinstance(service, CampaignGoalConfigService)
    assert mock_mcp.tool.call_count == 3  # type: ignore
