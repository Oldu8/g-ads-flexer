"""Tests for KeywordThemeConstantService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.keyword_theme_constant_service import (
    KeywordThemeConstantServiceClient,
)
from google.ads.googleads.v25.services.types.keyword_theme_constant_service import (
    SuggestKeywordThemeConstantsResponse,
)

from src.services.audiences.keyword_theme_constant_service import (
    KeywordThemeConstantService,
    register_keyword_theme_constant_tools,
)


@pytest.fixture
def keyword_theme_constant_service(
    mock_sdk_client: Any,
) -> KeywordThemeConstantService:
    """Create a KeywordThemeConstantService instance with mocked dependencies."""
    mock_client = Mock(spec=KeywordThemeConstantServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.audiences.keyword_theme_constant_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = KeywordThemeConstantService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_suggest_keyword_theme_constants(
    keyword_theme_constant_service: KeywordThemeConstantService,
    mock_ctx: Context,
) -> None:
    """Test suggesting keyword theme constants."""
    mock_client = keyword_theme_constant_service.client  # type: ignore
    mock_constant = Mock()
    mock_constant.resource_name = "keywordThemeConstants/1~0"
    mock_constant.country_code = "US"
    mock_constant.language_code = "en"
    mock_constant.display_name = "Plumber"
    mock_client.suggest_keyword_theme_constants.return_value = Mock(  # type: ignore
        spec=SuggestKeywordThemeConstantsResponse,
        keyword_theme_constants=[mock_constant],
    )

    result = await keyword_theme_constant_service.suggest_keyword_theme_constants(
        ctx=mock_ctx, query_text="plumber"
    )

    assert result == [
        {
            "resource_name": "keywordThemeConstants/1~0",
            "country_code": "US",
            "language_code": "en",
            "display_name": "Plumber",
        }
    ]

    request = mock_client.suggest_keyword_theme_constants.call_args[1][  # type: ignore
        "request"
    ]
    assert request.query_text == "plumber"
    assert request.country_code == "US"
    assert request.language_code == "en"


@pytest.mark.asyncio
async def test_error_handling(
    keyword_theme_constant_service: KeywordThemeConstantService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = keyword_theme_constant_service.client  # type: ignore
    mock_client.suggest_keyword_theme_constants.side_effect = (  # type: ignore
        google_ads_exception
    )

    with pytest.raises(Exception) as exc_info:
        await keyword_theme_constant_service.suggest_keyword_theme_constants(
            ctx=mock_ctx, query_text="plumber"
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_keyword_theme_constant_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_keyword_theme_constant_tools(mock_mcp)

    assert isinstance(service, KeywordThemeConstantService)
    assert mock_mcp.tool.call_count == 1  # type: ignore
