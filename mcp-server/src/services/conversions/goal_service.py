"""Goal service implementation using Google Ads SDK.

`Goal` (v25 new) is the account-level definition of a customer-lifecycle
optimization goal (CUSTOMER_RETENTION, NEW_CUSTOMER_ACQUISITION, or
LOYALTY_RETENTION) - it replaces the old, now-removed
`customer_lifecycle_goal`. A `Goal` on its own doesn't do anything; it has
to be linked to a campaign via `CampaignGoalConfig` (see
`campaign_goal_config_service.py`) before it affects bidding.

Note the API only supports create/update for goals - there is no remove
operation (`GoalOperation` has no `remove` field).
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.common.types.goal_common import (
    CustomerLifecycleOptimizationValueSettings,
)
from google.ads.googleads.v25.enums.types.goal_type import GoalTypeEnum
from google.ads.googleads.v25.resources.types.goal import Goal
from google.ads.googleads.v25.services.services.goal_service import (
    GoalServiceClient,
)
from google.ads.googleads.v25.services.types.goal_service import (
    GoalOperation,
    MutateGoalsRequest,
    MutateGoalsResponse,
)
from google.protobuf import field_mask_pb2

from src.sdk_client import get_sdk_client
from src.utils import (
    format_ads_error,
    format_customer_id,
    get_logger,
    resolve_enum,
    serialize_proto_message,
)

logger = get_logger(__name__)

# Maps goal_type -> the Goal resource's oneof field name for its settings.
_GOAL_SETTINGS_FIELD = {
    "CUSTOMER_RETENTION": "retention_goal_settings",
    "NEW_CUSTOMER_ACQUISITION": "new_customer_acquisition_goal_settings",
    "LOYALTY_RETENTION": "loyalty_retention_goal_settings",
}


def _build_value_settings(
    additional_value: Optional[float],
    value_multiplier: Optional[float],
    additional_high_lifetime_value: Optional[float],
    high_lifetime_value_multiplier: Optional[float],
) -> CustomerLifecycleOptimizationValueSettings:
    """Build a `CustomerLifecycleOptimizationValueSettings` message.

    At most one of (additional_value, value_multiplier) and at most one of
    (additional_high_lifetime_value, high_lifetime_value_multiplier) may be
    set - each pair is a protobuf oneof.
    """
    value_settings = CustomerLifecycleOptimizationValueSettings()
    if additional_value is not None:
        value_settings.additional_value = additional_value
    elif value_multiplier is not None:
        value_settings.value_multiplier = value_multiplier
    if additional_high_lifetime_value is not None:
        value_settings.additional_high_lifetime_value = additional_high_lifetime_value
    elif high_lifetime_value_multiplier is not None:
        value_settings.high_lifetime_value_multiplier = high_lifetime_value_multiplier
    return value_settings


def _apply_goal_settings(
    goal: Goal,
    goal_type: str,
    additional_value: Optional[float],
    value_multiplier: Optional[float],
    additional_high_lifetime_value: Optional[float],
    high_lifetime_value_multiplier: Optional[float],
) -> str:
    """Set the right oneof settings field on `goal` for `goal_type`.

    Returns the settings field name that was set (for building update masks).
    """
    settings_field = _GOAL_SETTINGS_FIELD[goal_type]
    value_settings = _build_value_settings(
        additional_value,
        value_multiplier,
        additional_high_lifetime_value,
        high_lifetime_value_multiplier,
    )
    getattr(goal, settings_field).value_settings = value_settings
    return settings_field


class GoalService:
    """Service for customer lifecycle-optimization `Goal` resources."""

    def __init__(self) -> None:
        """Initialize the goal service."""
        self._client: Optional[GoalServiceClient] = None

    @property
    def client(self) -> GoalServiceClient:
        """Get the goal service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service("GoalService", version="v25")
        assert self._client is not None
        return self._client

    async def create_goal(
        self,
        ctx: Context,
        customer_id: str,
        goal_type: str,
        additional_value: Optional[float] = None,
        value_multiplier: Optional[float] = None,
        additional_high_lifetime_value: Optional[float] = None,
        high_lifetime_value_multiplier: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create a customer lifecycle-optimization goal.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            goal_type: CUSTOMER_RETENTION, NEW_CUSTOMER_ACQUISITION, or
                LOYALTY_RETENTION
            additional_value: Incremental conversion value (mutually
                exclusive with value_multiplier)
            value_multiplier: Conversion value multiplier (mutually
                exclusive with additional_value)
            additional_high_lifetime_value: Incremental high-lifetime
                conversion value (mutually exclusive with
                high_lifetime_value_multiplier)
            high_lifetime_value_multiplier: High-lifetime conversion value
                multiplier (mutually exclusive with
                additional_high_lifetime_value)

        Returns:
            Created goal details
        """
        try:
            customer_id = format_customer_id(customer_id)
            resolved_type = resolve_enum(GoalTypeEnum.GoalType, goal_type, "goal_type")

            goal = Goal()
            goal.goal_type = resolved_type
            _apply_goal_settings(
                goal,
                goal_type,
                additional_value,
                value_multiplier,
                additional_high_lifetime_value,
                high_lifetime_value_multiplier,
            )

            operation = GoalOperation()
            operation.create = goal

            request = MutateGoalsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateGoalsResponse = self.client.mutate_goals(request=request)

            await ctx.log(
                level="info",
                message=f"Created {goal_type} goal",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create goal: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def update_goal(
        self,
        ctx: Context,
        customer_id: str,
        goal_id: str,
        goal_type: str,
        additional_value: Optional[float] = None,
        value_multiplier: Optional[float] = None,
        additional_high_lifetime_value: Optional[float] = None,
        high_lifetime_value_multiplier: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update a goal's value settings.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            goal_id: The goal ID
            goal_type: The goal's type (CUSTOMER_RETENTION,
                NEW_CUSTOMER_ACQUISITION, or LOYALTY_RETENTION) - required
                to know which settings field to update, since it's a oneof
            additional_value: Incremental conversion value (mutually
                exclusive with value_multiplier)
            value_multiplier: Conversion value multiplier (mutually
                exclusive with additional_value)
            additional_high_lifetime_value: Incremental high-lifetime
                conversion value (mutually exclusive with
                high_lifetime_value_multiplier)
            high_lifetime_value_multiplier: High-lifetime conversion value
                multiplier (mutually exclusive with
                additional_high_lifetime_value)

        Returns:
            Updated goal details
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = f"customers/{customer_id}/goals/{goal_id}"

            goal = Goal()
            goal.resource_name = resource_name
            settings_field = _apply_goal_settings(
                goal,
                goal_type,
                additional_value,
                value_multiplier,
                additional_high_lifetime_value,
                high_lifetime_value_multiplier,
            )

            operation = GoalOperation()
            operation.update = goal
            operation.update_mask = field_mask_pb2.FieldMask(paths=[settings_field])

            request = MutateGoalsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_goals(request=request)

            await ctx.log(
                level="info",
                message=f"Updated goal {goal_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to update goal: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_goal_tools(
    service: GoalService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the goal service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def create_goal(
        ctx: Context,
        customer_id: str,
        goal_type: str,
        additional_value: Optional[float] = None,
        value_multiplier: Optional[float] = None,
        additional_high_lifetime_value: Optional[float] = None,
        high_lifetime_value_multiplier: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create a customer lifecycle-optimization goal (account-level -
        must be linked to a campaign via `link_campaign_to_goal` to take
        effect).

        Args:
            customer_id: The customer ID
            goal_type: CUSTOMER_RETENTION, NEW_CUSTOMER_ACQUISITION, or
                LOYALTY_RETENTION
            additional_value: Incremental conversion value (mutually
                exclusive with value_multiplier)
            value_multiplier: Conversion value multiplier (mutually
                exclusive with additional_value)
            additional_high_lifetime_value: Incremental high-lifetime
                conversion value (mutually exclusive with
                high_lifetime_value_multiplier)
            high_lifetime_value_multiplier: High-lifetime conversion value
                multiplier (mutually exclusive with
                additional_high_lifetime_value)

        Returns:
            Created goal details
        """
        return await service.create_goal(
            ctx=ctx,
            customer_id=customer_id,
            goal_type=goal_type,
            additional_value=additional_value,
            value_multiplier=value_multiplier,
            additional_high_lifetime_value=additional_high_lifetime_value,
            high_lifetime_value_multiplier=high_lifetime_value_multiplier,
        )

    async def update_goal(
        ctx: Context,
        customer_id: str,
        goal_id: str,
        goal_type: str,
        additional_value: Optional[float] = None,
        value_multiplier: Optional[float] = None,
        additional_high_lifetime_value: Optional[float] = None,
        high_lifetime_value_multiplier: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update a goal's value settings.

        Args:
            customer_id: The customer ID
            goal_id: The goal ID
            goal_type: The goal's type (CUSTOMER_RETENTION,
                NEW_CUSTOMER_ACQUISITION, or LOYALTY_RETENTION)
            additional_value: Incremental conversion value (mutually
                exclusive with value_multiplier)
            value_multiplier: Conversion value multiplier (mutually
                exclusive with additional_value)
            additional_high_lifetime_value: Incremental high-lifetime
                conversion value (mutually exclusive with
                high_lifetime_value_multiplier)
            high_lifetime_value_multiplier: High-lifetime conversion value
                multiplier (mutually exclusive with
                additional_high_lifetime_value)

        Returns:
            Updated goal details
        """
        return await service.update_goal(
            ctx=ctx,
            customer_id=customer_id,
            goal_id=goal_id,
            goal_type=goal_type,
            additional_value=additional_value,
            value_multiplier=value_multiplier,
            additional_high_lifetime_value=additional_high_lifetime_value,
            high_lifetime_value_multiplier=high_lifetime_value_multiplier,
        )

    tools.extend(
        [
            create_goal,
            update_goal,
        ]
    )
    return tools


def register_goal_tools(mcp: FastMCP[Any]) -> GoalService:
    """Register goal tools with the MCP server.

    Returns the GoalService instance for testing purposes.
    """
    service = GoalService()
    tools = create_goal_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
