"""Keyword theme constant service implementation using Google Ads SDK.

Read-only: `KeywordThemeConstantService` has a single RPC,
`SuggestKeywordThemeConstants`, which maps free-text query into Smart
Campaign keyword themes (e.g. "plumber" -> "Plumber", "Plumbing
contractor", ...). There is no mutate operation - keyword themes are a
fixed taxonomy Google maintains, not account-owned data.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.services.services.keyword_theme_constant_service import (
    KeywordThemeConstantServiceClient,
)
from google.ads.googleads.v25.services.types.keyword_theme_constant_service import (
    SuggestKeywordThemeConstantsRequest,
    SuggestKeywordThemeConstantsResponse,
)

from src.sdk_client import get_sdk_client
from src.utils import format_ads_error, get_logger

logger = get_logger(__name__)


class KeywordThemeConstantService:
    """Service for suggesting Smart Campaign keyword themes from free text."""

    def __init__(self) -> None:
        """Initialize the keyword theme constant service."""
        self._client: Optional[KeywordThemeConstantServiceClient] = None

    @property
    def client(self) -> KeywordThemeConstantServiceClient:
        """Get the keyword theme constant service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "KeywordThemeConstantService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def suggest_keyword_theme_constants(
        self,
        ctx: Context,
        query_text: str,
        country_code: str = "US",
        language_code: str = "en",
    ) -> List[Dict[str, Any]]:
        """Suggest Smart Campaign keyword themes matching free text.

        Args:
            ctx: FastMCP context
            query_text: Free text to map to keyword themes, e.g. "plumber"
                or "roofer"
            country_code: Upper-case two-letter ISO-3166 country code
            language_code: Two-letter ISO-639-1 language code

        Returns:
            List of matching keyword theme constants (resource_name,
            country_code, language_code, display_name)
        """
        try:
            request = SuggestKeywordThemeConstantsRequest()
            request.query_text = query_text
            request.country_code = country_code
            request.language_code = language_code

            response: SuggestKeywordThemeConstantsResponse = (
                self.client.suggest_keyword_theme_constants(request=request)
            )

            results = [
                {
                    "resource_name": constant.resource_name,
                    "country_code": constant.country_code,
                    "language_code": constant.language_code,
                    "display_name": constant.display_name,
                }
                for constant in response.keyword_theme_constants
            ]

            await ctx.log(
                level="info",
                message=(
                    f"Found {len(results)} keyword theme suggestions for '{query_text}'"
                ),
            )

            return results

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to suggest keyword theme constants: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_keyword_theme_constant_tools(
    service: KeywordThemeConstantService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the keyword theme constant service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def suggest_keyword_theme_constants(
        ctx: Context,
        query_text: str,
        country_code: str = "US",
        language_code: str = "en",
    ) -> List[Dict[str, Any]]:
        """Suggest Smart Campaign keyword themes matching free text.

        Args:
            query_text: Free text to map to keyword themes, e.g. "plumber"
                or "roofer"
            country_code: Upper-case two-letter ISO-3166 country code
            language_code: Two-letter ISO-639-1 language code

        Returns:
            List of matching keyword theme constants (resource_name,
            country_code, language_code, display_name)
        """
        return await service.suggest_keyword_theme_constants(
            ctx=ctx,
            query_text=query_text,
            country_code=country_code,
            language_code=language_code,
        )

    tools.extend(
        [
            suggest_keyword_theme_constants,
        ]
    )
    return tools


def register_keyword_theme_constant_tools(
    mcp: FastMCP[Any],
) -> KeywordThemeConstantService:
    """Register keyword theme constant tools with the MCP server.

    Returns the KeywordThemeConstantService instance for testing purposes.
    """
    service = KeywordThemeConstantService()
    tools = create_keyword_theme_constant_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
