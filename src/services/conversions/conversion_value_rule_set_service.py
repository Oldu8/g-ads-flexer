"""Conversion value rule set service implementation using Google Ads SDK."""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.enums.types.conversion_action_category import (
    ConversionActionCategoryEnum,
)
from google.ads.googleads.v25.enums.types.conversion_value_rule_set_status import (
    ConversionValueRuleSetStatusEnum,
)
from google.ads.googleads.v25.enums.types.value_rule_set_attachment_type import (
    ValueRuleSetAttachmentTypeEnum,
)
from google.ads.googleads.v25.enums.types.value_rule_set_dimension import (
    ValueRuleSetDimensionEnum,
)
from google.ads.googleads.v25.resources.types.conversion_value_rule_set import (
    ConversionValueRuleSet,
)
from google.ads.googleads.v25.services.services.conversion_value_rule_set_service import (
    ConversionValueRuleSetServiceClient,
)
from google.ads.googleads.v25.services.types.conversion_value_rule_set_service import (
    ConversionValueRuleSetOperation,
    MutateConversionValueRuleSetsRequest,
    MutateConversionValueRuleSetsResponse,
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


class ConversionValueRuleSetService:
    """Service for conversion value rule sets - groups of value rules (see
    `conversion_value_rule_service.py`) that adjust a conversion's reported
    value by dimension (geo, device, audience) for a campaign or the whole
    account.
    """

    def __init__(self) -> None:
        """Initialize the conversion value rule set service."""
        self._client: Optional[ConversionValueRuleSetServiceClient] = None

    @property
    def client(self) -> ConversionValueRuleSetServiceClient:
        """Get the conversion value rule set service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "ConversionValueRuleSetService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def create_conversion_value_rule_set(
        self,
        ctx: Context,
        customer_id: str,
        conversion_value_rule_ids: List[str],
        dimensions: List[str],
        attachment_type: str = "CUSTOMER",
        campaign_id: Optional[str] = None,
        status: str = "ENABLED",
        conversion_action_categories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a conversion value rule set.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            conversion_value_rule_ids: IDs of existing conversion value rules
                to include in this set
            dimensions: Dimensions the rules in this set vary by, e.g.
                GEO_LOCATION, DEVICE, AUDIENCE, ITINERARY, NO_CONDITION
            attachment_type: CUSTOMER or CAMPAIGN
            campaign_id: Required when attachment_type is CAMPAIGN
            status: ENABLED or PAUSED
            conversion_action_categories: Optional list of conversion action
                categories this set applies to (applies to all if omitted)

        Returns:
            Created conversion value rule set details
        """
        try:
            customer_id = format_customer_id(customer_id)

            rule_set = ConversionValueRuleSet()
            rule_set.conversion_value_rules = [
                f"customers/{customer_id}/conversionValueRules/{rid}"
                for rid in conversion_value_rule_ids
            ]
            rule_set.dimensions = [
                resolve_enum(
                    ValueRuleSetDimensionEnum.ValueRuleSetDimension, d, "dimensions"
                )
                for d in dimensions
            ]
            rule_set.attachment_type = resolve_enum(
                ValueRuleSetAttachmentTypeEnum.ValueRuleSetAttachmentType,
                attachment_type,
                "attachment_type",
            )
            if campaign_id is not None:
                rule_set.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
            rule_set.status = resolve_enum(
                ConversionValueRuleSetStatusEnum.ConversionValueRuleSetStatus,
                status,
                "status",
            )
            if conversion_action_categories:
                rule_set.conversion_action_categories = [
                    resolve_enum(
                        ConversionActionCategoryEnum.ConversionActionCategory,
                        c,
                        "conversion_action_categories",
                    )
                    for c in conversion_action_categories
                ]

            operation = ConversionValueRuleSetOperation()
            operation.create = rule_set

            request = MutateConversionValueRuleSetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateConversionValueRuleSetsResponse = (
                self.client.mutate_conversion_value_rule_sets(request=request)
            )

            await ctx.log(
                level="info",
                message="Created conversion value rule set",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create conversion value rule set: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def update_conversion_value_rule_set_status(
        self,
        ctx: Context,
        customer_id: str,
        conversion_value_rule_set_id: str,
        status: str,
    ) -> Dict[str, Any]:
        """Update a conversion value rule set's status.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            conversion_value_rule_set_id: The conversion value rule set ID
            status: New status (ENABLED or PAUSED)

        Returns:
            Updated conversion value rule set details
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = (
                f"customers/{customer_id}/conversionValueRuleSets/"
                f"{conversion_value_rule_set_id}"
            )

            rule_set = ConversionValueRuleSet()
            rule_set.resource_name = resource_name
            rule_set.status = resolve_enum(
                ConversionValueRuleSetStatusEnum.ConversionValueRuleSetStatus,
                status,
                "status",
            )

            operation = ConversionValueRuleSetOperation()
            operation.update = rule_set
            operation.update_mask = field_mask_pb2.FieldMask(paths=["status"])

            request = MutateConversionValueRuleSetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_conversion_value_rule_sets(request=request)

            await ctx.log(
                level="info",
                message=(
                    f"Updated conversion value rule set "
                    f"{conversion_value_rule_set_id} status to {status}"
                ),
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to update conversion value rule set: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def remove_conversion_value_rule_set(
        self,
        ctx: Context,
        customer_id: str,
        conversion_value_rule_set_id: str,
    ) -> Dict[str, Any]:
        """Remove a conversion value rule set.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            conversion_value_rule_set_id: The conversion value rule set ID

        Returns:
            Removal result
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = (
                f"customers/{customer_id}/conversionValueRuleSets/"
                f"{conversion_value_rule_set_id}"
            )

            operation = ConversionValueRuleSetOperation()
            operation.remove = resource_name

            request = MutateConversionValueRuleSetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_conversion_value_rule_sets(request=request)

            await ctx.log(
                level="info",
                message=(
                    f"Removed conversion value rule set {conversion_value_rule_set_id}"
                ),
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to remove conversion value rule set: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_conversion_value_rule_set_tools(
    service: ConversionValueRuleSetService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the conversion value rule set service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def create_conversion_value_rule_set(
        ctx: Context,
        customer_id: str,
        conversion_value_rule_ids: List[str],
        dimensions: List[str],
        attachment_type: str = "CUSTOMER",
        campaign_id: Optional[str] = None,
        status: str = "ENABLED",
        conversion_action_categories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a conversion value rule set from existing value rules.

        Args:
            customer_id: The customer ID
            conversion_value_rule_ids: IDs of existing conversion value rules
                to include in this set
            dimensions: Dimensions the rules vary by, e.g. GEO_LOCATION,
                DEVICE, AUDIENCE, ITINERARY, NO_CONDITION
            attachment_type: CUSTOMER or CAMPAIGN
            campaign_id: Required when attachment_type is CAMPAIGN
            status: ENABLED or PAUSED
            conversion_action_categories: Optional list of conversion action
                categories this set applies to (applies to all if omitted)

        Returns:
            Created conversion value rule set details
        """
        return await service.create_conversion_value_rule_set(
            ctx=ctx,
            customer_id=customer_id,
            conversion_value_rule_ids=conversion_value_rule_ids,
            dimensions=dimensions,
            attachment_type=attachment_type,
            campaign_id=campaign_id,
            status=status,
            conversion_action_categories=conversion_action_categories,
        )

    async def update_conversion_value_rule_set_status(
        ctx: Context,
        customer_id: str,
        conversion_value_rule_set_id: str,
        status: str,
    ) -> Dict[str, Any]:
        """Update a conversion value rule set's status.

        Args:
            customer_id: The customer ID
            conversion_value_rule_set_id: The conversion value rule set ID
            status: New status (ENABLED or PAUSED)

        Returns:
            Updated conversion value rule set details
        """
        return await service.update_conversion_value_rule_set_status(
            ctx=ctx,
            customer_id=customer_id,
            conversion_value_rule_set_id=conversion_value_rule_set_id,
            status=status,
        )

    async def remove_conversion_value_rule_set(
        ctx: Context,
        customer_id: str,
        conversion_value_rule_set_id: str,
    ) -> Dict[str, Any]:
        """Remove a conversion value rule set.

        Args:
            customer_id: The customer ID
            conversion_value_rule_set_id: The conversion value rule set ID

        Returns:
            Removal result
        """
        return await service.remove_conversion_value_rule_set(
            ctx=ctx,
            customer_id=customer_id,
            conversion_value_rule_set_id=conversion_value_rule_set_id,
        )

    tools.extend(
        [
            create_conversion_value_rule_set,
            update_conversion_value_rule_set_status,
            remove_conversion_value_rule_set,
        ]
    )
    return tools


def register_conversion_value_rule_set_tools(
    mcp: FastMCP[Any],
) -> ConversionValueRuleSetService:
    """Register conversion value rule set tools with the MCP server.

    Returns the ConversionValueRuleSetService instance for testing purposes.
    """
    service = ConversionValueRuleSetService()
    tools = create_conversion_value_rule_set_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
