"""Tests for SmartCampaignSettingService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.smart_campaign_setting_service import (
    SmartCampaignSettingServiceClient,
)
from google.ads.googleads.v25.services.types.smart_campaign_setting_service import (
    GetSmartCampaignStatusResponse,
    MutateSmartCampaignSettingsResponse,
)

from src.services.campaign.smart_campaign_setting_service import (
    SmartCampaignSettingService,
    register_smart_campaign_setting_tools,
)


@pytest.fixture
def smart_campaign_setting_service(
    mock_sdk_client: Any,
) -> SmartCampaignSettingService:
    """Create a SmartCampaignSettingService instance with mocked dependencies."""
    mock_client = Mock(spec=SmartCampaignSettingServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.campaign.smart_campaign_setting_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = SmartCampaignSettingService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_get_smart_campaign_status(
    smart_campaign_setting_service: SmartCampaignSettingService,
    mock_ctx: Context,
) -> None:
    """Test getting a Smart campaign's status."""
    customer_id = "1234567890"
    mock_client = smart_campaign_setting_service.client  # type: ignore
    mock_client.get_smart_campaign_status.return_value = Mock(  # type: ignore
        spec=GetSmartCampaignStatusResponse, smart_campaign_status=5
    )

    await smart_campaign_setting_service.get_smart_campaign_status(
        ctx=mock_ctx, customer_id=customer_id, campaign_id="111"
    )

    mock_client.get_smart_campaign_status.assert_called_once()  # type: ignore
    request = mock_client.get_smart_campaign_status.call_args[1]["request"]  # type: ignore
    assert request.resource_name == (
        f"customers/{customer_id}/smartCampaignSettings/111"
    )


@pytest.mark.asyncio
async def test_update_smart_campaign_setting_final_url(
    smart_campaign_setting_service: SmartCampaignSettingService,
    mock_ctx: Context,
) -> None:
    """Test updating a Smart campaign setting's final_url and phone."""
    customer_id = "1234567890"
    mock_client = smart_campaign_setting_service.client  # type: ignore
    mock_client.mutate_smart_campaign_settings.return_value = Mock(  # type: ignore
        spec=MutateSmartCampaignSettingsResponse, results=[]
    )

    await smart_campaign_setting_service.update_smart_campaign_setting(
        ctx=mock_ctx,
        customer_id=customer_id,
        campaign_id="111",
        phone_number="5551234",
        phone_country_code="US",
        final_url="https://example.com",
    )

    request = mock_client.mutate_smart_campaign_settings.call_args[1][  # type: ignore
        "request"
    ]
    operation = request.operations[0]
    assert operation.update.resource_name == (
        f"customers/{customer_id}/smartCampaignSettings/111"
    )
    assert operation.update.phone_number.phone_number == "5551234"
    assert operation.update.phone_number.country_code == "US"
    assert operation.update.final_url == "https://example.com"
    assert set(operation.update_mask.paths) == {"phone_number", "final_url"}


@pytest.mark.asyncio
async def test_update_smart_campaign_setting_lead_form(
    smart_campaign_setting_service: SmartCampaignSettingService,
    mock_ctx: Context,
) -> None:
    """Test that include_lead_form is used when final_url is not given."""
    customer_id = "1234567890"
    mock_client = smart_campaign_setting_service.client  # type: ignore
    mock_client.mutate_smart_campaign_settings.return_value = Mock(  # type: ignore
        spec=MutateSmartCampaignSettingsResponse, results=[]
    )

    await smart_campaign_setting_service.update_smart_campaign_setting(
        ctx=mock_ctx,
        customer_id=customer_id,
        campaign_id="111",
        include_lead_form=True,
        business_profile_location="locations/123",
    )

    request = mock_client.mutate_smart_campaign_settings.call_args[1][  # type: ignore
        "request"
    ]
    operation = request.operations[0]
    assert (
        operation.update.ad_optimized_business_profile_setting.include_lead_form is True
    )
    assert operation.update.business_profile_location == "locations/123"
    assert set(operation.update_mask.paths) == {
        "ad_optimized_business_profile_setting",
        "business_profile_location",
    }


@pytest.mark.asyncio
async def test_error_handling(
    smart_campaign_setting_service: SmartCampaignSettingService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = smart_campaign_setting_service.client  # type: ignore
    mock_client.get_smart_campaign_status.side_effect = google_ads_exception  # type: ignore

    with pytest.raises(Exception) as exc_info:
        await smart_campaign_setting_service.get_smart_campaign_status(
            ctx=mock_ctx, customer_id="1234567890", campaign_id="111"
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_smart_campaign_setting_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_smart_campaign_setting_tools(mock_mcp)

    assert isinstance(service, SmartCampaignSettingService)
    assert mock_mcp.tool.call_count == 2  # type: ignore
