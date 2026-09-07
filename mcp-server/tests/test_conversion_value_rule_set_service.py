"""Tests for ConversionValueRuleSetService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.conversion_value_rule_set_service import (
    ConversionValueRuleSetServiceClient,
)
from google.ads.googleads.v25.services.types.conversion_value_rule_set_service import (
    MutateConversionValueRuleSetsResponse,
)

from src.services.conversions.conversion_value_rule_set_service import (
    ConversionValueRuleSetService,
    register_conversion_value_rule_set_tools,
)


@pytest.fixture
def conversion_value_rule_set_service(
    mock_sdk_client: Any,
) -> ConversionValueRuleSetService:
    """Create a ConversionValueRuleSetService instance with mocked dependencies."""
    mock_client = Mock(spec=ConversionValueRuleSetServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.conversions.conversion_value_rule_set_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = ConversionValueRuleSetService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_create_conversion_value_rule_set(
    conversion_value_rule_set_service: ConversionValueRuleSetService,
    mock_ctx: Context,
) -> None:
    """Test creating a conversion value rule set."""
    customer_id = "1234567890"
    mock_client = conversion_value_rule_set_service.client  # type: ignore
    mock_client.mutate_conversion_value_rule_sets.return_value = Mock(  # type: ignore
        spec=MutateConversionValueRuleSetsResponse, results=[]
    )

    await conversion_value_rule_set_service.create_conversion_value_rule_set(
        ctx=mock_ctx,
        customer_id=customer_id,
        conversion_value_rule_ids=["10", "20"],
        dimensions=["GEO_LOCATION", "DEVICE"],
        attachment_type="CAMPAIGN",
        campaign_id="999",
        conversion_action_categories=["PURCHASE"],
    )

    request = mock_client.mutate_conversion_value_rule_sets.call_args[1][  # type: ignore
        "request"
    ]
    create = request.operations[0].create
    assert list(create.conversion_value_rules) == [
        f"customers/{customer_id}/conversionValueRules/10",
        f"customers/{customer_id}/conversionValueRules/20",
    ]
    assert create.campaign == f"customers/{customer_id}/campaigns/999"
    assert create.attachment_type == 3  # CAMPAIGN
    assert len(create.conversion_action_categories) == 1


@pytest.mark.asyncio
async def test_update_conversion_value_rule_set_status(
    conversion_value_rule_set_service: ConversionValueRuleSetService,
    mock_ctx: Context,
) -> None:
    """Test updating a conversion value rule set's status."""
    customer_id = "1234567890"
    mock_client = conversion_value_rule_set_service.client  # type: ignore
    mock_client.mutate_conversion_value_rule_sets.return_value = Mock(  # type: ignore
        spec=MutateConversionValueRuleSetsResponse, results=[]
    )

    await conversion_value_rule_set_service.update_conversion_value_rule_set_status(
        ctx=mock_ctx,
        customer_id=customer_id,
        conversion_value_rule_set_id="5",
        status="PAUSED",
    )

    request = mock_client.mutate_conversion_value_rule_sets.call_args[1][  # type: ignore
        "request"
    ]
    operation = request.operations[0]
    assert operation.update.resource_name == (
        f"customers/{customer_id}/conversionValueRuleSets/5"
    )
    assert list(operation.update_mask.paths) == ["status"]


@pytest.mark.asyncio
async def test_remove_conversion_value_rule_set(
    conversion_value_rule_set_service: ConversionValueRuleSetService,
    mock_ctx: Context,
) -> None:
    """Test removing a conversion value rule set."""
    customer_id = "1234567890"
    mock_client = conversion_value_rule_set_service.client  # type: ignore
    mock_client.mutate_conversion_value_rule_sets.return_value = Mock(  # type: ignore
        spec=MutateConversionValueRuleSetsResponse, results=[]
    )

    await conversion_value_rule_set_service.remove_conversion_value_rule_set(
        ctx=mock_ctx, customer_id=customer_id, conversion_value_rule_set_id="5"
    )

    request = mock_client.mutate_conversion_value_rule_sets.call_args[1][  # type: ignore
        "request"
    ]
    assert request.operations[0].remove == (
        f"customers/{customer_id}/conversionValueRuleSets/5"
    )


@pytest.mark.asyncio
async def test_error_handling(
    conversion_value_rule_set_service: ConversionValueRuleSetService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = conversion_value_rule_set_service.client  # type: ignore
    mock_client.mutate_conversion_value_rule_sets.side_effect = (  # type: ignore
        google_ads_exception
    )

    with pytest.raises(Exception) as exc_info:
        await conversion_value_rule_set_service.create_conversion_value_rule_set(
            ctx=mock_ctx,
            customer_id="1234567890",
            conversion_value_rule_ids=["10"],
            dimensions=["DEVICE"],
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_conversion_value_rule_set_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_conversion_value_rule_set_tools(mock_mcp)

    assert isinstance(service, ConversionValueRuleSetService)
    assert mock_mcp.tool.call_count == 3  # type: ignore
