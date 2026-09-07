"""Shareable preview service implementation using Google Ads SDK.

Generates a shareable preview URL for a Performance Max asset group or a
YouTube live-preview-eligible ad. Per the proto docstring, only Performance
Max asset groups and certain YouTube video/audio ad formats are supported -
other ad types (e.g. Responsive Search/Display Ads) return an
`UNSUPPORTED_AD_TYPE` error. Read-only in effect (generates a URL, doesn't
change any account data) but modeled as an "action" service in the API, not
a search/report.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.actions.types.generate_shareable_previews import (
    GenerateShareablePreviewsOperation,
    ShareablePreview,
)
from google.ads.googleads.v25.enums.types.preview_type import PreviewTypeEnum
from google.ads.googleads.v25.services.services.shareable_preview_service import (
    ShareablePreviewServiceClient,
)
from google.ads.googleads.v25.services.types.shareable_preview_service import (
    GenerateShareablePreviewsRequest,
    GenerateShareablePreviewsResponse,
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


class ShareablePreviewService:
    """Service for generating shareable ad/asset-group preview URLs."""

    def __init__(self) -> None:
        """Initialize the shareable preview service."""
        self._client: Optional[ShareablePreviewServiceClient] = None

    @property
    def client(self) -> ShareablePreviewServiceClient:
        """Get the shareable preview service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "ShareablePreviewService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def generate_shareable_previews(
        self,
        ctx: Context,
        customer_id: str,
        previews: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Generate shareable preview URLs.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            previews: List of dicts, each with:
                - preview_type: UI_PREVIEW (asset_group_id required) or
                  YOUTUBE_LIVE_PREVIEW (ad_group_id + ad_id required)
                - asset_group_id: required for UI_PREVIEW
                - ad_group_id / ad_id: required for YOUTUBE_LIVE_PREVIEW

        Returns:
            Generated preview URLs (each includes its expiration time)
        """
        try:
            customer_id = format_customer_id(customer_id)

            shareable_previews = []
            for preview in previews:
                sp = ShareablePreview()
                sp.preview_type = resolve_enum(
                    PreviewTypeEnum.PreviewType,
                    preview["preview_type"],
                    "preview_type",
                )
                if "asset_group_id" in preview:
                    sp.asset_group = (
                        f"customers/{customer_id}/assetGroups/"
                        f"{preview['asset_group_id']}"
                    )
                elif "ad_group_id" in preview and "ad_id" in preview:
                    sp.ad_group_ad = (
                        f"customers/{customer_id}/adGroupAds/"
                        f"{preview['ad_group_id']}~{preview['ad_id']}"
                    )
                shareable_previews.append(sp)

            operation = GenerateShareablePreviewsOperation()
            operation.shareable_previews = shareable_previews

            request = GenerateShareablePreviewsRequest()
            request.customer_id = customer_id
            request.operation = operation

            response: GenerateShareablePreviewsResponse = (
                self.client.generate_shareable_previews(request=request)
            )

            await ctx.log(
                level="info",
                message=f"Generated {len(previews)} shareable preview(s)",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to generate shareable previews: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_shareable_preview_tools(
    service: ShareablePreviewService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the shareable preview service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def generate_shareable_previews(
        ctx: Context,
        customer_id: str,
        previews: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Generate shareable preview URLs for Performance Max asset groups
        or YouTube-live-eligible ads. Other ad types (e.g. Responsive
        Search/Display Ads) are not supported and return an error.

        Args:
            customer_id: The customer ID
            previews: List of dicts, each with:
                - preview_type: UI_PREVIEW (asset_group_id required) or
                  YOUTUBE_LIVE_PREVIEW (ad_group_id + ad_id required)
                - asset_group_id: required for UI_PREVIEW
                - ad_group_id / ad_id: required for YOUTUBE_LIVE_PREVIEW

        Returns:
            Generated preview URLs (each includes its expiration time)
        """
        return await service.generate_shareable_previews(
            ctx=ctx, customer_id=customer_id, previews=previews
        )

    tools.extend(
        [
            generate_shareable_previews,
        ]
    )
    return tools


def register_shareable_preview_tools(
    mcp: FastMCP[Any],
) -> ShareablePreviewService:
    """Register shareable preview tools with the MCP server.

    Returns the ShareablePreviewService instance for testing purposes.
    """
    service = ShareablePreviewService()
    tools = create_shareable_preview_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
