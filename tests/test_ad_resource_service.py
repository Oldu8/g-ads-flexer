"""Tests for AdResourceService (standalone `AdService`, distinct from the
`AdGroupAdService`-backed `ad_service.py` in the same package)."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.ad_service import AdServiceClient
from google.ads.googleads.v25.services.services.google_ads_service import (
    GoogleAdsServiceClient,
)
from google.ads.googleads.v25.services.types.ad_service import MutateAdsResponse

from src.services.ad_group.ad_resource_service import (
    AdResourceService,
    register_ad_resource_tools,
)


@pytest.fixture
def ad_resource_service(mock_sdk_client: Any) -> AdResourceService:
    """Create an AdResourceService instance with mocked dependencies."""
    mock_client = Mock(spec=AdServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.ad_group.ad_resource_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = AdResourceService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_update_ad_urls(
    ad_resource_service: AdResourceService,
    mock_ctx: Context,
) -> None:
    """Test updating an ad's URL fields builds the right field mask."""
    customer_id = "1234567890"
    mock_client = ad_resource_service.client  # type: ignore
    mock_client.mutate_ads.return_value = Mock(  # type: ignore
        spec=MutateAdsResponse, results=[]
    )

    await ad_resource_service.update_ad_urls(
        ctx=mock_ctx,
        customer_id=customer_id,
        ad_id="111",
        final_urls=["https://example.com/new"],
        tracking_url_template="https://track.example.com",
    )

    request = mock_client.mutate_ads.call_args[1]["request"]  # type: ignore
    operation = request.operations[0]
    assert operation.update.resource_name == f"customers/{customer_id}/ads/111"
    assert list(operation.update.final_urls) == ["https://example.com/new"]
    assert operation.update.tracking_url_template == "https://track.example.com"
    assert set(operation.update_mask.paths) == {
        "final_urls",
        "tracking_url_template",
    }


@pytest.mark.asyncio
async def test_get_ad_found(
    ad_resource_service: AdResourceService,
    mock_sdk_client: Any,
    mock_ctx: Context,
) -> None:
    """Test getting an ad that exists."""
    customer_id = "1234567890"

    mock_google_ads_service = Mock(spec=GoogleAdsServiceClient)
    row = Mock()
    row.ad_group_ad.ad.resource_name = f"customers/{customer_id}/ads/111"
    row.ad_group_ad.ad.id = 111
    row.ad_group_ad.ad.name = ""
    row.ad_group_ad.ad.type_ = Mock(name="RESPONSIVE_SEARCH_AD")
    row.ad_group_ad.ad.final_urls = ["https://example.com"]
    row.ad_group_ad.ad.final_mobile_urls = []
    row.ad_group_ad.ad.tracking_url_template = ""
    row.ad_group_ad.ad.final_url_suffix = ""
    row.ad_group_ad.ad.display_url = ""
    mock_google_ads_service.search.return_value = [row]  # type: ignore

    def get_service_side_effect(service_name: str, **kwargs: Any) -> Any:
        if service_name == "GoogleAdsService":
            return mock_google_ads_service
        return ad_resource_service.client

    mock_sdk_client.client.get_service.side_effect = get_service_side_effect  # type: ignore

    with patch(
        "src.services.ad_group.ad_resource_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        result = await ad_resource_service.get_ad(
            ctx=mock_ctx, customer_id=customer_id, ad_id="111"
        )

    assert result["id"] == "111"
    assert result["final_urls"] == ["https://example.com"]

    mock_google_ads_service.search.assert_called_once()  # type: ignore
    query = mock_google_ads_service.search.call_args[1]["query"]  # type: ignore
    assert "ad_group_ad.ad.id = 111" in query


@pytest.mark.asyncio
async def test_get_ad_not_found(
    ad_resource_service: AdResourceService,
    mock_sdk_client: Any,
    mock_ctx: Context,
) -> None:
    """Test getting an ad that doesn't exist returns an empty dict."""
    customer_id = "1234567890"

    mock_google_ads_service = Mock(spec=GoogleAdsServiceClient)
    mock_google_ads_service.search.return_value = []  # type: ignore

    def get_service_side_effect(service_name: str, **kwargs: Any) -> Any:
        if service_name == "GoogleAdsService":
            return mock_google_ads_service
        return ad_resource_service.client

    mock_sdk_client.client.get_service.side_effect = get_service_side_effect  # type: ignore

    with patch(
        "src.services.ad_group.ad_resource_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        result = await ad_resource_service.get_ad(
            ctx=mock_ctx, customer_id=customer_id, ad_id="999"
        )

    assert result == {}


@pytest.mark.asyncio
async def test_error_handling(
    ad_resource_service: AdResourceService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = ad_resource_service.client  # type: ignore
    mock_client.mutate_ads.side_effect = google_ads_exception  # type: ignore

    with pytest.raises(Exception) as exc_info:
        await ad_resource_service.update_ad_urls(
            ctx=mock_ctx, customer_id="1234567890", ad_id="111", display_url="x"
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_ad_resource_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_ad_resource_tools(mock_mcp)

    assert isinstance(service, AdResourceService)
    assert mock_mcp.tool.call_count == 2  # type: ignore
