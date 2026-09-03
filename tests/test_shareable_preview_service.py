"""Tests for ShareablePreviewService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.shareable_preview_service import (
    ShareablePreviewServiceClient,
)
from google.ads.googleads.v25.services.types.shareable_preview_service import (
    GenerateShareablePreviewsResponse,
)

from src.services.campaign.shareable_preview_service import (
    ShareablePreviewService,
    register_shareable_preview_tools,
)


@pytest.fixture
def shareable_preview_service(mock_sdk_client: Any) -> ShareablePreviewService:
    """Create a ShareablePreviewService instance with mocked dependencies."""
    mock_client = Mock(spec=ShareablePreviewServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.campaign.shareable_preview_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = ShareablePreviewService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_generate_shareable_previews_asset_group(
    shareable_preview_service: ShareablePreviewService,
    mock_ctx: Context,
) -> None:
    """Test generating a UI_PREVIEW for a Performance Max asset group."""
    customer_id = "1234567890"
    mock_client = shareable_preview_service.client  # type: ignore
    mock_client.generate_shareable_previews.return_value = Mock(  # type: ignore
        spec=GenerateShareablePreviewsResponse
    )

    await shareable_preview_service.generate_shareable_previews(
        ctx=mock_ctx,
        customer_id=customer_id,
        previews=[{"preview_type": "UI_PREVIEW", "asset_group_id": "111"}],
    )

    request = mock_client.generate_shareable_previews.call_args[1][  # type: ignore
        "request"
    ]
    assert request.customer_id == customer_id
    sp = request.operation.shareable_previews[0]
    assert sp.preview_type == 2  # UI_PREVIEW
    assert sp.asset_group == f"customers/{customer_id}/assetGroups/111"


@pytest.mark.asyncio
async def test_generate_shareable_previews_youtube_live(
    shareable_preview_service: ShareablePreviewService,
    mock_ctx: Context,
) -> None:
    """Test generating a YOUTUBE_LIVE_PREVIEW for an ad group ad."""
    customer_id = "1234567890"
    mock_client = shareable_preview_service.client  # type: ignore
    mock_client.generate_shareable_previews.return_value = Mock(  # type: ignore
        spec=GenerateShareablePreviewsResponse
    )

    await shareable_preview_service.generate_shareable_previews(
        ctx=mock_ctx,
        customer_id=customer_id,
        previews=[
            {
                "preview_type": "YOUTUBE_LIVE_PREVIEW",
                "ad_group_id": "111",
                "ad_id": "222",
            }
        ],
    )

    request = mock_client.generate_shareable_previews.call_args[1][  # type: ignore
        "request"
    ]
    sp = request.operation.shareable_previews[0]
    assert sp.preview_type == 3  # YOUTUBE_LIVE_PREVIEW
    assert sp.ad_group_ad == f"customers/{customer_id}/adGroupAds/111~222"


@pytest.mark.asyncio
async def test_error_handling(
    shareable_preview_service: ShareablePreviewService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = shareable_preview_service.client  # type: ignore
    mock_client.generate_shareable_previews.side_effect = google_ads_exception  # type: ignore

    with pytest.raises(Exception) as exc_info:
        await shareable_preview_service.generate_shareable_previews(
            ctx=mock_ctx,
            customer_id="1234567890",
            previews=[{"preview_type": "UI_PREVIEW", "asset_group_id": "111"}],
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_shareable_preview_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_shareable_preview_tools(mock_mcp)

    assert isinstance(service, ShareablePreviewService)
    assert mock_mcp.tool.call_count == 1  # type: ignore
