"""Automatically created asset removal service implementation using Google
Ads SDK.

Lets an advertiser opt a campaign out of one specific asset Google
auto-generated for it (e.g. an auto-created headline or image) without
touching any other automatically created assets. Single-purpose service:
one RPC, no create/update/list - `remove_campaign_automatically_created_asset`.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.enums.types.asset_field_type import (
    AssetFieldTypeEnum,
)
from google.ads.googleads.v25.services.services.automatically_created_asset_removal_service import (
    AutomaticallyCreatedAssetRemovalServiceClient,
)
from google.ads.googleads.v25.services.types.automatically_created_asset_removal_service import (
    RemoveCampaignAutomaticallyCreatedAssetOperation,
    RemoveCampaignAutomaticallyCreatedAssetRequest,
    RemoveCampaignAutomaticallyCreatedAssetResponse,
)

from src.sdk_client import get_sdk_client
from src.utils import (
    format_ads_error,
    format_customer_id,
    get_logger,
    resolve_enum,
    serialize_proto_message,
)

logger = get_logger(__name__)


class AutomaticallyCreatedAssetRemovalService:
    """Service for opting a campaign out of a specific auto-created asset."""

    def __init__(self) -> None:
        """Initialize the automatically created asset removal service."""
        self._client: Optional[AutomaticallyCreatedAssetRemovalServiceClient] = None

    @property
    def client(self) -> AutomaticallyCreatedAssetRemovalServiceClient:
        """Get the automatically created asset removal service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "AutomaticallyCreatedAssetRemovalService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def remove_campaign_automatically_created_asset(
        self,
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        asset_id: str,
        field_type: str,
    ) -> Dict[str, Any]:
        """Remove a specific automatically created asset from a campaign.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            campaign_id: The campaign ID
            asset_id: The asset ID to remove
            field_type: The asset's field type (e.g. HEADLINE,
                DESCRIPTION, MARKETING_IMAGE) - identifies which
                auto-created placement to opt out of

        Returns:
            Removal result
        """
        try:
            customer_id = format_customer_id(customer_id)

            operation = RemoveCampaignAutomaticallyCreatedAssetOperation()
            operation.campaign = f"customers/{customer_id}/campaigns/{campaign_id}"
            operation.asset = f"customers/{customer_id}/assets/{asset_id}"
            operation.field_type = resolve_enum(
                AssetFieldTypeEnum.AssetFieldType, field_type, "field_type"
            )

            request = RemoveCampaignAutomaticallyCreatedAssetRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: RemoveCampaignAutomaticallyCreatedAssetResponse = (
                self.client.remove_campaign_automatically_created_asset(request=request)
            )

            await ctx.log(
                level="info",
                message=(
                    f"Removed automatically created asset {asset_id} "
                    f"({field_type}) from campaign {campaign_id}"
                ),
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to remove automatically created asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_automatically_created_asset_removal_tools(
    service: AutomaticallyCreatedAssetRemovalService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the automatically created asset removal
    service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def remove_campaign_automatically_created_asset(
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        asset_id: str,
        field_type: str,
    ) -> Dict[str, Any]:
        """Opt a campaign out of one specific automatically created asset
        (e.g. an auto-generated headline or image), without affecting any
        other auto-created assets.

        Args:
            customer_id: The customer ID
            campaign_id: The campaign ID
            asset_id: The asset ID to remove
            field_type: The asset's field type (e.g. HEADLINE,
                DESCRIPTION, MARKETING_IMAGE)

        Returns:
            Removal result
        """
        return await service.remove_campaign_automatically_created_asset(
            ctx=ctx,
            customer_id=customer_id,
            campaign_id=campaign_id,
            asset_id=asset_id,
            field_type=field_type,
        )

    tools.extend(
        [
            remove_campaign_automatically_created_asset,
        ]
    )
    return tools


def register_automatically_created_asset_removal_tools(
    mcp: FastMCP[Any],
) -> AutomaticallyCreatedAssetRemovalService:
    """Register automatically created asset removal tools with the MCP
    server.

    Returns the AutomaticallyCreatedAssetRemovalService instance for
    testing purposes.
    """
    service = AutomaticallyCreatedAssetRemovalService()
    tools = create_automatically_created_asset_removal_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
