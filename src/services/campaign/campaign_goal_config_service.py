"""Campaign goal config service implementation using Google Ads SDK.

`CampaignGoalConfig` (v25 new) links a campaign to a customer
lifecycle-optimization `Goal` (see `../conversions/goal_service.py`),
enabling campaign-specific optimization for that goal. Replaces the old,
now-removed `campaign_lifecycle_goal`.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.common.types.goal_common import (
    CustomerLifecycleOptimizationValueSettings,
)
from google.ads.googleads.v25.enums.types.customer_lifecycle_optimization_mode import (
    CustomerLifecycleOptimizationModeEnum,
)
from google.ads.googleads.v25.resources.types.campaign_goal_config import (
    CampaignGoalConfig,
)
from google.ads.googleads.v25.services.services.campaign_goal_config_service import (
    CampaignGoalConfigServiceClient,
)
from google.ads.googleads.v25.services.types.campaign_goal_config_service import (
    CampaignGoalConfigOperation,
    MutateCampaignGoalConfigsRequest,
    MutateCampaignGoalConfigsResponse,
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

# Maps goal_type -> the CampaignGoalConfig resource's oneof settings field.
_CAMPAIGN_GOAL_SETTINGS_FIELD = {
    "CUSTOMER_RETENTION": "campaign_retention_settings",
    "NEW_CUSTOMER_ACQUISITION": "campaign_new_customer_acquisition_settings",
    "LOYALTY_RETENTION": "campaign_loyalty_retention_settings",
}


def _apply_campaign_goal_settings(
    config: CampaignGoalConfig,
    goal_type: str,
    target_option: Optional[str],
    value_multiplier: Optional[float],
    enable_bid_adjustments_for_loyalty_members: Optional[bool],
    show_targeted_loyalty_member_benefits_in_pla: Optional[bool],
) -> str:
    """Set the right oneof settings field on `config` for `goal_type`.

    Returns the settings field name that was set (for building update masks).
    """
    settings_field = _CAMPAIGN_GOAL_SETTINGS_FIELD[goal_type]
    settings = getattr(config, settings_field)

    if value_multiplier is not None:
        value_settings = CustomerLifecycleOptimizationValueSettings()
        value_settings.value_multiplier = value_multiplier
        settings.value_settings_override = value_settings

    if goal_type == "LOYALTY_RETENTION":
        if enable_bid_adjustments_for_loyalty_members is not None:
            settings.enable_bid_adjustments_for_loyalty_members = (
                enable_bid_adjustments_for_loyalty_members
            )
        if show_targeted_loyalty_member_benefits_in_pla is not None:
            settings.show_targeted_loyalty_member_benefits_in_pla = (
                show_targeted_loyalty_member_benefits_in_pla
            )
    elif target_option is not None:
        settings.target_option = resolve_enum(
            CustomerLifecycleOptimizationModeEnum.CustomerLifecycleOptimizationMode,
            target_option,
            "target_option",
        )

    setattr(config, settings_field, settings)
    return settings_field


class CampaignGoalConfigService:
    """Service linking campaigns to customer lifecycle-optimization goals."""

    def __init__(self) -> None:
        """Initialize the campaign goal config service."""
        self._client: Optional[CampaignGoalConfigServiceClient] = None

    @property
    def client(self) -> CampaignGoalConfigServiceClient:
        """Get the campaign goal config service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "CampaignGoalConfigService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def link_campaign_to_goal(
        self,
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        goal_id: str,
        goal_type: str,
        target_option: Optional[str] = None,
        value_multiplier: Optional[float] = None,
        enable_bid_adjustments_for_loyalty_members: Optional[bool] = None,
        show_targeted_loyalty_member_benefits_in_pla: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Link a campaign to a goal, enabling campaign-specific
        optimization for it.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            campaign_id: The campaign ID
            goal_id: The goal ID (see `goal_service.py`'s `create_goal`)
            goal_type: The goal's type - CUSTOMER_RETENTION,
                NEW_CUSTOMER_ACQUISITION, or LOYALTY_RETENTION (must match
                the goal's actual type)
            target_option: TARGET_ALL or TARGET_SPECIFIC - ignored for
                LOYALTY_RETENTION goals (allowlist-gated feature)
            value_multiplier: Campaign-specific conversion value multiplier
                override
            enable_bid_adjustments_for_loyalty_members: LOYALTY_RETENTION
                goals only
            show_targeted_loyalty_member_benefits_in_pla: LOYALTY_RETENTION
                goals only

        Returns:
            Created campaign goal config details
        """
        try:
            customer_id = format_customer_id(customer_id)

            config = CampaignGoalConfig()
            config.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
            config.goal = f"customers/{customer_id}/goals/{goal_id}"
            _apply_campaign_goal_settings(
                config,
                goal_type,
                target_option,
                value_multiplier,
                enable_bid_adjustments_for_loyalty_members,
                show_targeted_loyalty_member_benefits_in_pla,
            )

            operation = CampaignGoalConfigOperation()
            operation.create = config

            request = MutateCampaignGoalConfigsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateCampaignGoalConfigsResponse = (
                self.client.mutate_campaign_goal_configs(request=request)
            )

            await ctx.log(
                level="info",
                message=f"Linked campaign {campaign_id} to goal {goal_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to link campaign to goal: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def update_campaign_goal_config(
        self,
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        goal_id: str,
        goal_type: str,
        target_option: Optional[str] = None,
        value_multiplier: Optional[float] = None,
        enable_bid_adjustments_for_loyalty_members: Optional[bool] = None,
        show_targeted_loyalty_member_benefits_in_pla: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update a campaign goal config's settings.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            campaign_id: The campaign ID
            goal_id: The goal ID
            goal_type: The goal's type - CUSTOMER_RETENTION,
                NEW_CUSTOMER_ACQUISITION, or LOYALTY_RETENTION (must match
                the goal's actual type, since it's a oneof)
            target_option: TARGET_ALL or TARGET_SPECIFIC - ignored for
                LOYALTY_RETENTION goals
            value_multiplier: Campaign-specific conversion value multiplier
                override
            enable_bid_adjustments_for_loyalty_members: LOYALTY_RETENTION
                goals only
            show_targeted_loyalty_member_benefits_in_pla: LOYALTY_RETENTION
                goals only

        Returns:
            Updated campaign goal config details
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = (
                f"customers/{customer_id}/campaignGoalConfigs/{campaign_id}~{goal_id}"
            )

            config = CampaignGoalConfig()
            config.resource_name = resource_name
            settings_field = _apply_campaign_goal_settings(
                config,
                goal_type,
                target_option,
                value_multiplier,
                enable_bid_adjustments_for_loyalty_members,
                show_targeted_loyalty_member_benefits_in_pla,
            )

            operation = CampaignGoalConfigOperation()
            operation.update = config
            operation.update_mask = field_mask_pb2.FieldMask(paths=[settings_field])

            request = MutateCampaignGoalConfigsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_campaign_goal_configs(request=request)

            await ctx.log(
                level="info",
                message=(
                    f"Updated campaign goal config for campaign {campaign_id} "
                    f"/ goal {goal_id}"
                ),
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to update campaign goal config: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def unlink_campaign_from_goal(
        self,
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        goal_id: str,
    ) -> Dict[str, Any]:
        """Unlink a campaign from a goal.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            campaign_id: The campaign ID
            goal_id: The goal ID

        Returns:
            Removal result
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = (
                f"customers/{customer_id}/campaignGoalConfigs/{campaign_id}~{goal_id}"
            )

            operation = CampaignGoalConfigOperation()
            operation.remove = resource_name

            request = MutateCampaignGoalConfigsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_campaign_goal_configs(request=request)

            await ctx.log(
                level="info",
                message=f"Unlinked campaign {campaign_id} from goal {goal_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to unlink campaign from goal: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_campaign_goal_config_tools(
    service: CampaignGoalConfigService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the campaign goal config service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def link_campaign_to_goal(
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        goal_id: str,
        goal_type: str,
        target_option: Optional[str] = None,
        value_multiplier: Optional[float] = None,
        enable_bid_adjustments_for_loyalty_members: Optional[bool] = None,
        show_targeted_loyalty_member_benefits_in_pla: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Link a campaign to a customer lifecycle-optimization goal.

        Args:
            customer_id: The customer ID
            campaign_id: The campaign ID
            goal_id: The goal ID (create one first with `create_goal`)
            goal_type: The goal's type - CUSTOMER_RETENTION,
                NEW_CUSTOMER_ACQUISITION, or LOYALTY_RETENTION (must match
                the goal's actual type)
            target_option: TARGET_ALL or TARGET_SPECIFIC - ignored for
                LOYALTY_RETENTION goals (allowlist-gated feature)
            value_multiplier: Campaign-specific conversion value multiplier
                override
            enable_bid_adjustments_for_loyalty_members: LOYALTY_RETENTION
                goals only
            show_targeted_loyalty_member_benefits_in_pla: LOYALTY_RETENTION
                goals only

        Returns:
            Created campaign goal config details
        """
        return await service.link_campaign_to_goal(
            ctx=ctx,
            customer_id=customer_id,
            campaign_id=campaign_id,
            goal_id=goal_id,
            goal_type=goal_type,
            target_option=target_option,
            value_multiplier=value_multiplier,
            enable_bid_adjustments_for_loyalty_members=(
                enable_bid_adjustments_for_loyalty_members
            ),
            show_targeted_loyalty_member_benefits_in_pla=(
                show_targeted_loyalty_member_benefits_in_pla
            ),
        )

    async def update_campaign_goal_config(
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        goal_id: str,
        goal_type: str,
        target_option: Optional[str] = None,
        value_multiplier: Optional[float] = None,
        enable_bid_adjustments_for_loyalty_members: Optional[bool] = None,
        show_targeted_loyalty_member_benefits_in_pla: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update a campaign goal config's settings.

        Args:
            customer_id: The customer ID
            campaign_id: The campaign ID
            goal_id: The goal ID
            goal_type: The goal's type - CUSTOMER_RETENTION,
                NEW_CUSTOMER_ACQUISITION, or LOYALTY_RETENTION (must match
                the goal's actual type)
            target_option: TARGET_ALL or TARGET_SPECIFIC - ignored for
                LOYALTY_RETENTION goals
            value_multiplier: Campaign-specific conversion value multiplier
                override
            enable_bid_adjustments_for_loyalty_members: LOYALTY_RETENTION
                goals only
            show_targeted_loyalty_member_benefits_in_pla: LOYALTY_RETENTION
                goals only

        Returns:
            Updated campaign goal config details
        """
        return await service.update_campaign_goal_config(
            ctx=ctx,
            customer_id=customer_id,
            campaign_id=campaign_id,
            goal_id=goal_id,
            goal_type=goal_type,
            target_option=target_option,
            value_multiplier=value_multiplier,
            enable_bid_adjustments_for_loyalty_members=(
                enable_bid_adjustments_for_loyalty_members
            ),
            show_targeted_loyalty_member_benefits_in_pla=(
                show_targeted_loyalty_member_benefits_in_pla
            ),
        )

    async def unlink_campaign_from_goal(
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        goal_id: str,
    ) -> Dict[str, Any]:
        """Unlink a campaign from a goal.

        Args:
            customer_id: The customer ID
            campaign_id: The campaign ID
            goal_id: The goal ID

        Returns:
            Removal result
        """
        return await service.unlink_campaign_from_goal(
            ctx=ctx,
            customer_id=customer_id,
            campaign_id=campaign_id,
            goal_id=goal_id,
        )

    tools.extend(
        [
            link_campaign_to_goal,
            update_campaign_goal_config,
            unlink_campaign_from_goal,
        ]
    )
    return tools


def register_campaign_goal_config_tools(
    mcp: FastMCP[Any],
) -> CampaignGoalConfigService:
    """Register campaign goal config tools with the MCP server.

    Returns the CampaignGoalConfigService instance for testing purposes.
    """
    service = CampaignGoalConfigService()
    tools = create_campaign_goal_config_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
