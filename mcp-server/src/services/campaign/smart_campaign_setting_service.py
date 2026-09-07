"""Smart campaign setting service implementation using Google Ads SDK.

Distinct from the already-implemented `smart_campaign_service.py`, which
wraps `SmartCampaignSuggestService` (copy/budget/keyword-theme
*suggestions* for setting up a new Smart campaign). This service wraps
`SmartCampaignSettingService`, which reads/writes the settings of a Smart
campaign that already exists (phone number, landing page, business
profile) and reports its serving status. There is no create/remove
operation - the setting is created implicitly when the Smart campaign
itself is created.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.resources.types.smart_campaign_setting import (
    SmartCampaignSetting,
)
from google.ads.googleads.v25.services.services.smart_campaign_setting_service import (
    SmartCampaignSettingServiceClient,
)
from google.ads.googleads.v25.services.types.smart_campaign_setting_service import (
    GetSmartCampaignStatusRequest,
    GetSmartCampaignStatusResponse,
    MutateSmartCampaignSettingsRequest,
    MutateSmartCampaignSettingsResponse,
    SmartCampaignSettingOperation,
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


class SmartCampaignSettingService:
    """Service for reading/writing a Smart campaign's settings and status."""

    def __init__(self) -> None:
        """Initialize the smart campaign setting service."""
        self._client: Optional[SmartCampaignSettingServiceClient] = None

    @property
    def client(self) -> SmartCampaignSettingServiceClient:
        """Get the smart campaign setting service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "SmartCampaignSettingService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def get_smart_campaign_status(
        self,
        ctx: Context,
        customer_id: str,
        campaign_id: str,
    ) -> Dict[str, Any]:
        """Get a Smart campaign's serving status and status-specific details.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            campaign_id: The Smart campaign's ID

        Returns:
            Status details (PAUSED, NOT_ELIGIBLE, PENDING, ELIGIBLE,
            REMOVED, or ENDED, plus whichever detail fields apply)
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = (
                f"customers/{customer_id}/smartCampaignSettings/{campaign_id}"
            )

            request = GetSmartCampaignStatusRequest()
            request.resource_name = resource_name

            response: GetSmartCampaignStatusResponse = (
                self.client.get_smart_campaign_status(request=request)
            )

            await ctx.log(
                level="info",
                message=f"Got status for Smart campaign {campaign_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to get Smart campaign status: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def update_smart_campaign_setting(
        self,
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        phone_number: Optional[str] = None,
        phone_country_code: Optional[str] = None,
        advertising_language_code: Optional[str] = None,
        final_url: Optional[str] = None,
        include_lead_form: Optional[bool] = None,
        business_name: Optional[str] = None,
        business_profile_location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a Smart campaign's settings.

        `final_url` and `include_lead_form` are mutually exclusive (the
        landing page is either a URL you provide or an ads-optimized
        business profile) - if both are given, `final_url` wins.
        `business_name` and `business_profile_location` are also mutually
        exclusive - if both are given, `business_name` wins.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            campaign_id: The Smart campaign's ID
            phone_number: Phone number to advertise, if changing (requires
                phone_country_code too)
            phone_country_code: Upper-case two-letter ISO-3166 country code
                for phone_number
            advertising_language_code: Language code to advertise in, if
                changing
            final_url: Landing page URL, if changing
            include_lead_form: Enable a lead form on the linked business
                profile as the landing page, if changing (mutually
                exclusive with final_url)
            business_name: Business name, if changing
            business_profile_location: Business Profile location resource
                name (``locations/{locationId}``), if changing (mutually
                exclusive with business_name)

        Returns:
            Updated Smart campaign setting details
        """
        try:
            customer_id = format_customer_id(customer_id)
            resource_name = (
                f"customers/{customer_id}/smartCampaignSettings/{campaign_id}"
            )

            setting = SmartCampaignSetting()
            setting.resource_name = resource_name

            update_fields = []
            if phone_number is not None or phone_country_code is not None:
                if phone_number is not None:
                    setting.phone_number.phone_number = phone_number
                if phone_country_code is not None:
                    setting.phone_number.country_code = phone_country_code
                update_fields.append("phone_number")
            if advertising_language_code is not None:
                setting.advertising_language_code = advertising_language_code
                update_fields.append("advertising_language_code")
            if final_url is not None:
                setting.final_url = final_url
                update_fields.append("final_url")
            elif include_lead_form is not None:
                setting.ad_optimized_business_profile_setting.include_lead_form = (
                    include_lead_form
                )
                update_fields.append("ad_optimized_business_profile_setting")
            if business_name is not None:
                setting.business_name = business_name
                update_fields.append("business_name")
            elif business_profile_location is not None:
                setting.business_profile_location = business_profile_location
                update_fields.append("business_profile_location")

            operation = SmartCampaignSettingOperation()
            operation.update = setting
            operation.update_mask = field_mask_pb2.FieldMask(paths=update_fields)

            request = MutateSmartCampaignSettingsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateSmartCampaignSettingsResponse = (
                self.client.mutate_smart_campaign_settings(request=request)
            )

            await ctx.log(
                level="info",
                message=f"Updated Smart campaign setting for campaign {campaign_id}",
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to update Smart campaign setting: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_smart_campaign_setting_tools(
    service: SmartCampaignSettingService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the smart campaign setting service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def get_smart_campaign_status(
        ctx: Context,
        customer_id: str,
        campaign_id: str,
    ) -> Dict[str, Any]:
        """Get a Smart campaign's serving status.

        Args:
            customer_id: The customer ID
            campaign_id: The Smart campaign's ID

        Returns:
            Status details (PAUSED, NOT_ELIGIBLE, PENDING, ELIGIBLE,
            REMOVED, or ENDED, plus whichever detail fields apply)
        """
        return await service.get_smart_campaign_status(
            ctx=ctx, customer_id=customer_id, campaign_id=campaign_id
        )

    async def update_smart_campaign_setting(
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        phone_number: Optional[str] = None,
        phone_country_code: Optional[str] = None,
        advertising_language_code: Optional[str] = None,
        final_url: Optional[str] = None,
        include_lead_form: Optional[bool] = None,
        business_name: Optional[str] = None,
        business_profile_location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a Smart campaign's settings (phone, language, landing
        page, business profile).

        Args:
            customer_id: The customer ID
            campaign_id: The Smart campaign's ID
            phone_number: Phone number to advertise, if changing (requires
                phone_country_code too)
            phone_country_code: Upper-case two-letter ISO-3166 country code
                for phone_number
            advertising_language_code: Language code to advertise in, if
                changing
            final_url: Landing page URL, if changing (mutually exclusive
                with include_lead_form)
            include_lead_form: Enable a lead form on the linked business
                profile as the landing page, if changing
            business_name: Business name, if changing (mutually exclusive
                with business_profile_location)
            business_profile_location: Business Profile location resource
                name (``locations/{locationId}``), if changing

        Returns:
            Updated Smart campaign setting details
        """
        return await service.update_smart_campaign_setting(
            ctx=ctx,
            customer_id=customer_id,
            campaign_id=campaign_id,
            phone_number=phone_number,
            phone_country_code=phone_country_code,
            advertising_language_code=advertising_language_code,
            final_url=final_url,
            include_lead_form=include_lead_form,
            business_name=business_name,
            business_profile_location=business_profile_location,
        )

    tools.extend(
        [
            get_smart_campaign_status,
            update_smart_campaign_setting,
        ]
    )
    return tools


def register_smart_campaign_setting_tools(
    mcp: FastMCP[Any],
) -> SmartCampaignSettingService:
    """Register smart campaign setting tools with the MCP server.

    Returns the SmartCampaignSettingService instance for testing purposes.
    """
    service = SmartCampaignSettingService()
    tools = create_smart_campaign_setting_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
