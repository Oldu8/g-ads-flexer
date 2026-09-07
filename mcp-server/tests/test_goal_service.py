"""Tests for GoalService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.goal_service import (
    GoalServiceClient,
)
from google.ads.googleads.v25.services.types.goal_service import (
    MutateGoalsResponse,
)

from src.services.conversions.goal_service import GoalService, register_goal_tools


@pytest.fixture
def goal_service(mock_sdk_client: Any) -> GoalService:
    """Create a GoalService instance with mocked dependencies."""
    mock_client = Mock(spec=GoalServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.conversions.goal_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = GoalService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_create_goal_retention(
    goal_service: GoalService,
    mock_ctx: Context,
) -> None:
    """Test creating a CUSTOMER_RETENTION goal sets the right oneof field."""
    customer_id = "1234567890"
    mock_client = goal_service.client  # type: ignore
    mock_client.mutate_goals.return_value = Mock(  # type: ignore
        spec=MutateGoalsResponse, results=[]
    )

    await goal_service.create_goal(
        ctx=mock_ctx,
        customer_id=customer_id,
        goal_type="CUSTOMER_RETENTION",
        value_multiplier=1.5,
    )

    request = mock_client.mutate_goals.call_args[1]["request"]  # type: ignore
    create = request.operations[0].create
    assert create.goal_type == 3  # CUSTOMER_RETENTION
    assert create.retention_goal_settings.value_settings.value_multiplier == 1.5


@pytest.mark.asyncio
async def test_create_goal_new_customer_acquisition(
    goal_service: GoalService,
    mock_ctx: Context,
) -> None:
    """Test creating a NEW_CUSTOMER_ACQUISITION goal with additional_value."""
    customer_id = "1234567890"
    mock_client = goal_service.client  # type: ignore
    mock_client.mutate_goals.return_value = Mock(  # type: ignore
        spec=MutateGoalsResponse, results=[]
    )

    await goal_service.create_goal(
        ctx=mock_ctx,
        customer_id=customer_id,
        goal_type="NEW_CUSTOMER_ACQUISITION",
        additional_value=10.0,
    )

    request = mock_client.mutate_goals.call_args[1]["request"]  # type: ignore
    create = request.operations[0].create
    assert create.goal_type == 4  # NEW_CUSTOMER_ACQUISITION
    assert (
        create.new_customer_acquisition_goal_settings.value_settings.additional_value
        == 10.0
    )


@pytest.mark.asyncio
async def test_update_goal(
    goal_service: GoalService,
    mock_ctx: Context,
) -> None:
    """Test updating a goal builds the right field mask."""
    customer_id = "1234567890"
    mock_client = goal_service.client  # type: ignore
    mock_client.mutate_goals.return_value = Mock(  # type: ignore
        spec=MutateGoalsResponse, results=[]
    )

    await goal_service.update_goal(
        ctx=mock_ctx,
        customer_id=customer_id,
        goal_id="5",
        goal_type="LOYALTY_RETENTION",
        value_multiplier=2.0,
    )

    request = mock_client.mutate_goals.call_args[1]["request"]  # type: ignore
    operation = request.operations[0]
    assert operation.update.resource_name == f"customers/{customer_id}/goals/5"
    assert list(operation.update_mask.paths) == ["loyalty_retention_goal_settings"]


@pytest.mark.asyncio
async def test_error_handling(
    goal_service: GoalService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = goal_service.client  # type: ignore
    mock_client.mutate_goals.side_effect = google_ads_exception  # type: ignore

    with pytest.raises(Exception) as exc_info:
        await goal_service.create_goal(
            ctx=mock_ctx, customer_id="1234567890", goal_type="CUSTOMER_RETENTION"
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_goal_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_goal_tools(mock_mcp)

    assert isinstance(service, GoalService)
    assert mock_mcp.tool.call_count == 2  # type: ignore
