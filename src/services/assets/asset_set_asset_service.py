"""Asset set asset service implementation using Google Ads SDK."""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.resources.types.asset_set_asset import AssetSetAsset
from google.ads.googleads.v25.services.services.asset_set_asset_service import (
    AssetSetAssetServiceClient,
)
from google.ads.googleads.v25.services.types.asset_set_asset_service import (
    AssetSetAssetOperation,
    MutateAssetSetAssetsRequest,
    MutateAssetSetAssetsResponse,
)

from src.sdk_client import get_sdk_client
from src.utils import (
    format_ads_error,
    format_customer_id,
    get_logger,
    serialize_proto_message,
)

logger = get_logger(__name__)


class AssetSetAssetService:
    """Service linking individual assets into an asset set (e.g. a location
    or business-data asset set used by Performance Max / Local campaigns).
    """

    def __init__(self) -> None:
        """Initialize the asset set asset service."""
        self._client: Optional[AssetSetAssetServiceClient] = None

    @property
    def client(self) -> AssetSetAssetServiceClient:
        """Get the asset set asset service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "AssetSetAssetService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def add_asset_to_asset_set(
        self,
        ctx: Context,
        customer_id: str,
        asset_set_id: str,
        asset_id: str,
    ) -> Dict[str, Any]:
        """Add an asset to an asset set.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            asset_set_id: The asset set ID
            asset_id: The asset ID to add

        Returns:
            Created asset set asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset_set_asset = AssetSetAsset()
            asset_set_asset.asset_set = (
                f"customers/{customer_id}/assetSets/{asset_set_id}"
            )
            asset_set_asset.asset = f"customers/{customer_id}/assets/{asset_id}"

            operation = AssetSetAssetOperation()
            operation.create = asset_set_asset

            request = MutateAssetSetAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetSetAssetsResponse = (
                self.client.mutate_asset_set_assets(request=request)
            )

            await ctx.log(
                level="info",
                message=f"Added asset {asset_id} to asset set {asset_set_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to add asset to asset set: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def remove_asset_from_asset_set(
        self,
        ctx: Context,
        customer_id: str,
        asset_set_id: str,
        asset_id: str,
    ) -> Dict[str, Any]:
        """Remove an asset from an asset set.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            asset_set_id: The asset set ID
            asset_id: The asset ID to remove

        Returns:
            Removal result
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = (
                f"customers/{customer_id}/assetSetAssets/{asset_set_id}~{asset_id}"
            )

            operation = AssetSetAssetOperation()
            operation.remove = resource_name

            request = MutateAssetSetAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_asset_set_assets(request=request)

            await ctx.log(
                level="info",
                message=f"Removed asset {asset_id} from asset set {asset_set_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to remove asset from asset set: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_asset_set_asset_tools(
    service: AssetSetAssetService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the asset set asset service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def add_asset_to_asset_set(
        ctx: Context,
        customer_id: str,
        asset_set_id: str,
        asset_id: str,
    ) -> Dict[str, Any]:
        """Add an asset to an asset set.

        Args:
            customer_id: The customer ID
            asset_set_id: The asset set ID
            asset_id: The asset ID to add

        Returns:
            Created asset set asset details
        """
        return await service.add_asset_to_asset_set(
            ctx=ctx,
            customer_id=customer_id,
            asset_set_id=asset_set_id,
            asset_id=asset_id,
        )

    async def remove_asset_from_asset_set(
        ctx: Context,
        customer_id: str,
        asset_set_id: str,
        asset_id: str,
    ) -> Dict[str, Any]:
        """Remove an asset from an asset set.

        Args:
            customer_id: The customer ID
            asset_set_id: The asset set ID
            asset_id: The asset ID to remove

        Returns:
            Removal result
        """
        return await service.remove_asset_from_asset_set(
            ctx=ctx,
            customer_id=customer_id,
            asset_set_id=asset_set_id,
            asset_id=asset_id,
        )

    tools.extend(
        [
            add_asset_to_asset_set,
            remove_asset_from_asset_set,
        ]
    )
    return tools


def register_asset_set_asset_tools(mcp: FastMCP[Any]) -> AssetSetAssetService:
    """Register asset set asset tools with the MCP server.

    Returns the AssetSetAssetService instance for testing purposes.
    """
    service = AssetSetAssetService()
    tools = create_asset_set_asset_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
