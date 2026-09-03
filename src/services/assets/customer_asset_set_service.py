"""Customer asset set service implementation using Google Ads SDK."""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.resources.types.customer_asset_set import (
    CustomerAssetSet,
)
from google.ads.googleads.v25.services.services.customer_asset_set_service import (
    CustomerAssetSetServiceClient,
)
from google.ads.googleads.v25.services.types.customer_asset_set_service import (
    CustomerAssetSetOperation,
    MutateCustomerAssetSetsRequest,
    MutateCustomerAssetSetsResponse,
)

from src.sdk_client import get_sdk_client
from src.utils import (
    format_ads_error,
    format_customer_id,
    get_logger,
    serialize_proto_message,
)

logger = get_logger(__name__)


class CustomerAssetSetService:
    """Service linking an asset set directly to the customer (account-wide),
    as opposed to a specific campaign - used for account-level location/
    business-data asset sets.
    """

    def __init__(self) -> None:
        """Initialize the customer asset set service."""
        self._client: Optional[CustomerAssetSetServiceClient] = None

    @property
    def client(self) -> CustomerAssetSetServiceClient:
        """Get the customer asset set service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "CustomerAssetSetService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def link_asset_set_to_customer(
        self,
        ctx: Context,
        customer_id: str,
        asset_set_id: str,
    ) -> Dict[str, Any]:
        """Link an asset set to the customer account.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            asset_set_id: The asset set ID to link

        Returns:
            Created customer asset set details
        """
        try:
            customer_id = format_customer_id(customer_id)

            customer_asset_set = CustomerAssetSet()
            customer_asset_set.asset_set = (
                f"customers/{customer_id}/assetSets/{asset_set_id}"
            )
            customer_asset_set.customer = f"customers/{customer_id}"

            operation = CustomerAssetSetOperation()
            operation.create = customer_asset_set

            request = MutateCustomerAssetSetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateCustomerAssetSetsResponse = (
                self.client.mutate_customer_asset_sets(request=request)
            )

            await ctx.log(
                level="info",
                message=f"Linked asset set {asset_set_id} to customer {customer_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to link asset set to customer: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def unlink_asset_set_from_customer(
        self,
        ctx: Context,
        customer_id: str,
        asset_set_id: str,
    ) -> Dict[str, Any]:
        """Unlink an asset set from the customer account.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            asset_set_id: The asset set ID to unlink

        Returns:
            Removal result
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = f"customers/{customer_id}/customerAssetSets/{asset_set_id}"

            operation = CustomerAssetSetOperation()
            operation.remove = resource_name

            request = MutateCustomerAssetSetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_customer_asset_sets(request=request)

            await ctx.log(
                level="info",
                message=(
                    f"Unlinked asset set {asset_set_id} from customer {customer_id}"
                ),
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to unlink asset set from customer: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_customer_asset_set_tools(
    service: CustomerAssetSetService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the customer asset set service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def link_asset_set_to_customer(
        ctx: Context,
        customer_id: str,
        asset_set_id: str,
    ) -> Dict[str, Any]:
        """Link an asset set to the customer account (account-wide, not a
        specific campaign).

        Args:
            customer_id: The customer ID
            asset_set_id: The asset set ID to link

        Returns:
            Created customer asset set details
        """
        return await service.link_asset_set_to_customer(
            ctx=ctx, customer_id=customer_id, asset_set_id=asset_set_id
        )

    async def unlink_asset_set_from_customer(
        ctx: Context,
        customer_id: str,
        asset_set_id: str,
    ) -> Dict[str, Any]:
        """Unlink an asset set from the customer account.

        Args:
            customer_id: The customer ID
            asset_set_id: The asset set ID to unlink

        Returns:
            Removal result
        """
        return await service.unlink_asset_set_from_customer(
            ctx=ctx, customer_id=customer_id, asset_set_id=asset_set_id
        )

    tools.extend(
        [
            link_asset_set_to_customer,
            unlink_asset_set_from_customer,
        ]
    )
    return tools


def register_customer_asset_set_tools(mcp: FastMCP[Any]) -> CustomerAssetSetService:
    """Register customer asset set tools with the MCP server.

    Returns the CustomerAssetSetService instance for testing purposes.
    """
    service = CustomerAssetSetService()
    tools = create_customer_asset_set_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
