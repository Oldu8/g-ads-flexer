"""Standalone Ad resource service implementation using Google Ads SDK.

This wraps `AdService` (`mutate_ads`/`get_ad`), which operates on the `Ad`
resource directly - distinct from `ad_service.py` in this same package,
which (despite its filename) actually wraps `AdGroupAdService` for creating
ads within an ad group. Ads can only be *created* via `AdGroupAdService`;
`AdService.MutateAds` only supports *updating* ad-level fields (final URLs,
tracking template, display URL, etc.) on an ad that already exists,
regardless of which ad group it lives in.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.resources.types.ad import Ad
from google.ads.googleads.v25.services.services.ad_service import AdServiceClient
from google.ads.googleads.v25.services.services.google_ads_service import (
    GoogleAdsServiceClient,
)
from google.ads.googleads.v25.services.types.ad_service import (
    AdOperation,
    MutateAdsRequest,
    MutateAdsResponse,
)
from google.protobuf import field_mask_pb2

from src.sdk_client import get_sdk_client
from src.utils import (
    format_ads_error,
    format_customer_id,
    get_logger,
    serialize_proto_message,
)

logger = get_logger(__name__)


class AdResourceService:
    """Service for updating ad-level fields on an existing `Ad` resource."""

    def __init__(self) -> None:
        """Initialize the ad resource service."""
        self._client: Optional[AdServiceClient] = None

    @property
    def client(self) -> AdServiceClient:
        """Get the ad service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service("AdService", version="v25")
        assert self._client is not None
        return self._client

    async def update_ad_urls(
        self,
        ctx: Context,
        customer_id: str,
        ad_id: str,
        final_urls: Optional[List[str]] = None,
        tracking_url_template: Optional[str] = None,
        final_url_suffix: Optional[str] = None,
        display_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an ad's URL-related fields.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            ad_id: The ad ID
            final_urls: New list of final URLs, if changing
            tracking_url_template: New tracking URL template, if changing
            final_url_suffix: New final URL suffix, if changing
            display_url: New display URL (image/display ads only), if changing

        Returns:
            Updated ad details
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = f"customers/{customer_id}/ads/{ad_id}"

            ad = Ad()
            ad.resource_name = resource_name

            update_fields = []
            if final_urls is not None:
                ad.final_urls = final_urls
                update_fields.append("final_urls")
            if tracking_url_template is not None:
                ad.tracking_url_template = tracking_url_template
                update_fields.append("tracking_url_template")
            if final_url_suffix is not None:
                ad.final_url_suffix = final_url_suffix
                update_fields.append("final_url_suffix")
            if display_url is not None:
                ad.display_url = display_url
                update_fields.append("display_url")

            operation = AdOperation()
            operation.update = ad
            operation.update_mask = field_mask_pb2.FieldMask(paths=update_fields)

            request = MutateAdsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAdsResponse = self.client.mutate_ads(request=request)

            await ctx.log(
                level="info",
                message=f"Updated ad {ad_id} fields: {', '.join(update_fields)}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to update ad: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def get_ad(
        self,
        ctx: Context,
        customer_id: str,
        ad_id: str,
    ) -> Dict[str, Any]:
        """Get an ad by ID (ad-level fields only, via `GoogleAdsService`).

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            ad_id: The ad ID

        Returns:
            Ad details, or an empty dict if not found
        """
        try:
            customer_id = format_customer_id(customer_id)

            sdk_client = get_sdk_client()
            google_ads_service: GoogleAdsServiceClient = sdk_client.client.get_service(
                "GoogleAdsService"
            )

            query = f"""
                SELECT
                    ad_group_ad.ad.id,
                    ad_group_ad.ad.resource_name,
                    ad_group_ad.ad.name,
                    ad_group_ad.ad.type,
                    ad_group_ad.ad.final_urls,
                    ad_group_ad.ad.final_mobile_urls,
                    ad_group_ad.ad.tracking_url_template,
                    ad_group_ad.ad.final_url_suffix,
                    ad_group_ad.ad.display_url
                FROM ad_group_ad
                WHERE ad_group_ad.ad.id = {ad_id}
                LIMIT 1
            """

            response = google_ads_service.search(customer_id=customer_id, query=query)

            for row in response:
                ad = row.ad_group_ad.ad
                await ctx.log(level="info", message=f"Found ad {ad_id}")
                return {
                    "resource_name": ad.resource_name,
                    "id": str(ad.id),
                    "name": ad.name,
                    "type": ad.type_.name if ad.type_ else "UNKNOWN",
                    "final_urls": list(ad.final_urls),
                    "final_mobile_urls": list(ad.final_mobile_urls),
                    "tracking_url_template": ad.tracking_url_template,
                    "final_url_suffix": ad.final_url_suffix,
                    "display_url": ad.display_url,
                }

            await ctx.log(level="info", message=f"Ad {ad_id} not found")
            return {}

        except Exception as e:
            error_msg = f"Failed to get ad: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_ad_resource_tools(
    service: AdResourceService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the ad resource service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def update_ad_urls(
        ctx: Context,
        customer_id: str,
        ad_id: str,
        final_urls: Optional[List[str]] = None,
        tracking_url_template: Optional[str] = None,
        final_url_suffix: Optional[str] = None,
        display_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an ad's URL-related fields (final URLs, tracking template,
        final URL suffix, display URL) directly on the `Ad` resource,
        independent of which ad group it lives in.

        Args:
            customer_id: The customer ID
            ad_id: The ad ID
            final_urls: New list of final URLs, if changing
            tracking_url_template: New tracking URL template, if changing
            final_url_suffix: New final URL suffix, if changing
            display_url: New display URL (image/display ads only), if changing

        Returns:
            Updated ad details
        """
        return await service.update_ad_urls(
            ctx=ctx,
            customer_id=customer_id,
            ad_id=ad_id,
            final_urls=final_urls,
            tracking_url_template=tracking_url_template,
            final_url_suffix=final_url_suffix,
            display_url=display_url,
        )

    async def get_ad(
        ctx: Context,
        customer_id: str,
        ad_id: str,
    ) -> Dict[str, Any]:
        """Get an ad's ad-level fields by ID.

        Args:
            customer_id: The customer ID
            ad_id: The ad ID

        Returns:
            Ad details, or an empty dict if not found
        """
        return await service.get_ad(ctx=ctx, customer_id=customer_id, ad_id=ad_id)

    tools.extend(
        [
            update_ad_urls,
            get_ad,
        ]
    )
    return tools


def register_ad_resource_tools(mcp: FastMCP[Any]) -> AdResourceService:
    """Register ad resource tools with the MCP server.

    Returns the AdResourceService instance for testing purposes.
    """
    service = AdResourceService()
    tools = create_ad_resource_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
