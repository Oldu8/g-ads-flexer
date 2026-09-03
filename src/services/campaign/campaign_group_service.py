"""Campaign group service implementation using Google Ads SDK."""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.enums.types.campaign_group_status import (
    CampaignGroupStatusEnum,
)
from google.ads.googleads.v25.resources.types.campaign_group import CampaignGroup
from google.ads.googleads.v25.services.services.campaign_group_service import (
    CampaignGroupServiceClient,
)
from google.ads.googleads.v25.services.types.campaign_group_service import (
    CampaignGroupOperation,
    MutateCampaignGroupsRequest,
    MutateCampaignGroupsResponse,
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


class CampaignGroupService:
    """Campaign group service for organizing campaigns for reporting/goals."""

    def __init__(self) -> None:
        """Initialize the campaign group service."""
        self._client: Optional[CampaignGroupServiceClient] = None

    @property
    def client(self) -> CampaignGroupServiceClient:
        """Get the campaign group service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "CampaignGroupService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def create_campaign_group(
        self,
        ctx: Context,
        customer_id: str,
        name: str,
        status: str = "ENABLED",
    ) -> Dict[str, Any]:
        """Create a campaign group.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            name: The campaign group name
            status: Status (ENABLED or REMOVED)

        Returns:
            Created campaign group details
        """
        try:
            customer_id = format_customer_id(customer_id)

            campaign_group = CampaignGroup()
            campaign_group.name = name
            campaign_group.status = resolve_enum(
                CampaignGroupStatusEnum.CampaignGroupStatus, status, "status"
            )

            operation = CampaignGroupOperation()
            operation.create = campaign_group

            request = MutateCampaignGroupsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateCampaignGroupsResponse = self.client.mutate_campaign_groups(
                request=request
            )

            await ctx.log(
                level="info",
                message=f"Created campaign group '{name}'",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create campaign group: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def update_campaign_group(
        self,
        ctx: Context,
        customer_id: str,
        campaign_group_id: str,
        name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a campaign group's name and/or status.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            campaign_group_id: The campaign group ID
            name: New name, if changing
            status: New status (ENABLED or REMOVED), if changing

        Returns:
            Updated campaign group details
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = (
                f"customers/{customer_id}/campaignGroups/{campaign_group_id}"
            )

            campaign_group = CampaignGroup()
            campaign_group.resource_name = resource_name

            update_fields = []
            if name is not None:
                campaign_group.name = name
                update_fields.append("name")
            if status is not None:
                campaign_group.status = resolve_enum(
                    CampaignGroupStatusEnum.CampaignGroupStatus, status, "status"
                )
                update_fields.append("status")

            operation = CampaignGroupOperation()
            operation.update = campaign_group
            operation.update_mask = field_mask_pb2.FieldMask(paths=update_fields)

            request = MutateCampaignGroupsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_campaign_groups(request=request)

            await ctx.log(
                level="info",
                message=f"Updated campaign group {campaign_group_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to update campaign group: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def remove_campaign_group(
        self,
        ctx: Context,
        customer_id: str,
        campaign_group_id: str,
    ) -> Dict[str, Any]:
        """Remove a campaign group.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            campaign_group_id: The campaign group ID

        Returns:
            Removal result
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = (
                f"customers/{customer_id}/campaignGroups/{campaign_group_id}"
            )

            operation = CampaignGroupOperation()
            operation.remove = resource_name

            request = MutateCampaignGroupsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_campaign_groups(request=request)

            await ctx.log(
                level="info",
                message=f"Removed campaign group {campaign_group_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to remove campaign group: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_campaign_group_tools(
    service: CampaignGroupService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the campaign group service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def create_campaign_group(
        ctx: Context,
        customer_id: str,
        name: str,
        status: str = "ENABLED",
    ) -> Dict[str, Any]:
        """Create a campaign group for grouping campaigns by reporting/goal.

        Args:
            customer_id: The customer ID
            name: The campaign group name
            status: Status (ENABLED or REMOVED)

        Returns:
            Created campaign group details
        """
        return await service.create_campaign_group(
            ctx=ctx, customer_id=customer_id, name=name, status=status
        )

    async def update_campaign_group(
        ctx: Context,
        customer_id: str,
        campaign_group_id: str,
        name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a campaign group's name and/or status.

        Args:
            customer_id: The customer ID
            campaign_group_id: The campaign group ID
            name: New name, if changing
            status: New status (ENABLED or REMOVED), if changing

        Returns:
            Updated campaign group details
        """
        return await service.update_campaign_group(
            ctx=ctx,
            customer_id=customer_id,
            campaign_group_id=campaign_group_id,
            name=name,
            status=status,
        )

    async def remove_campaign_group(
        ctx: Context,
        customer_id: str,
        campaign_group_id: str,
    ) -> Dict[str, Any]:
        """Remove a campaign group.

        Args:
            customer_id: The customer ID
            campaign_group_id: The campaign group ID

        Returns:
            Removal result
        """
        return await service.remove_campaign_group(
            ctx=ctx, customer_id=customer_id, campaign_group_id=campaign_group_id
        )

    tools.extend(
        [
            create_campaign_group,
            update_campaign_group,
            remove_campaign_group,
        ]
    )
    return tools


def register_campaign_group_tools(mcp: FastMCP[Any]) -> CampaignGroupService:
    """Register campaign group tools with the MCP server.

    Returns the CampaignGroupService instance for testing purposes.
    """
    service = CampaignGroupService()
    tools = create_campaign_group_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
