"""Asset service implementation using Google Ads SDK."""

import base64
import mimetypes
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.common.types.asset_types import (
    BusinessMessageAsset,
    BusinessMessageCallToActionInfo,
    CallAsset,
    CalloutAsset,
    CallToActionAsset,
    ImageAsset,
    LeadFormAsset,
    LeadFormDeliveryMethod,
    LeadFormField,
    LocationAsset,
    MobileAppAsset,
    PriceAsset,
    PriceOffering,
    PromotionAsset,
    SitelinkAsset,
    StructuredSnippetAsset,
    TextAsset,
    WebhookDelivery,
    WhatsappBusinessMessageInfo,
    YoutubeVideoAsset,
)
from google.ads.googleads.v25.common.types.feed_common import Money
from google.ads.googleads.v25.enums.types.asset_type import AssetTypeEnum
from google.ads.googleads.v25.enums.types.business_message_call_to_action_type import (
    BusinessMessageCallToActionTypeEnum,
)
from google.ads.googleads.v25.enums.types.business_message_provider import (
    BusinessMessageProviderEnum,
)
from google.ads.googleads.v25.enums.types.call_to_action_type import (
    CallToActionTypeEnum,
)
from google.ads.googleads.v25.enums.types.lead_form_call_to_action_type import (
    LeadFormCallToActionTypeEnum,
)
from google.ads.googleads.v25.enums.types.lead_form_field_user_input_type import (
    LeadFormFieldUserInputTypeEnum,
)
from google.ads.googleads.v25.enums.types.location_ownership_type import (
    LocationOwnershipTypeEnum,
)
from google.ads.googleads.v25.enums.types.mobile_app_vendor import (
    MobileAppVendorEnum,
)
from google.ads.googleads.v25.enums.types.price_extension_price_qualifier import (
    PriceExtensionPriceQualifierEnum,
)
from google.ads.googleads.v25.enums.types.price_extension_price_unit import (
    PriceExtensionPriceUnitEnum,
)
from google.ads.googleads.v25.enums.types.price_extension_type import (
    PriceExtensionTypeEnum,
)
from google.ads.googleads.v25.enums.types.promotion_extension_discount_modifier import (
    PromotionExtensionDiscountModifierEnum,
)
from google.ads.googleads.v25.enums.types.promotion_extension_occasion import (
    PromotionExtensionOccasionEnum,
)
from google.ads.googleads.v25.resources.types.asset import Asset
from google.ads.googleads.v25.services.services.asset_service import (
    AssetServiceClient,
)
from google.ads.googleads.v25.services.services.google_ads_service import (
    GoogleAdsServiceClient,
)
from google.ads.googleads.v25.services.types.asset_service import (
    AssetOperation,
    MutateAssetsRequest,
    MutateAssetsResponse,
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


class AssetService:
    """Asset service for managing Google Ads assets (images, videos, text)."""

    def __init__(self) -> None:
        """Initialize the asset service."""
        self._client: Optional[AssetServiceClient] = None

    @property
    def client(self) -> AssetServiceClient:
        """Get the asset service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service("AssetService", version="v25")
        assert self._client is not None
        return self._client

    async def create_text_asset(
        self,
        ctx: Context,
        customer_id: str,
        text: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a text asset.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            text: The text content
            name: Optional name for the asset

        Returns:
            Created asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            # Create asset
            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.TEXT

            # Set name if provided
            if name:
                asset.name = name
            else:
                asset.name = f"Text: {text[:50]}"  # Use first 50 chars as name

            # Create text asset
            text_asset = TextAsset()
            text_asset.text = text
            asset.text_asset = text_asset

            # Create operation
            operation = AssetOperation()
            operation.create = asset

            # Create request
            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            # Make the API call
            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create text asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_image_asset(
        self,
        ctx: Context,
        customer_id: str,
        name: str,
        image_data_base64: Optional[str] = None,
        image_url: Optional[str] = None,
        image_file_path: Optional[str] = None,
        mime_type: str = "image/jpeg",
    ) -> Dict[str, Any]:
        """Create an image asset from base64, a URL, or a local file.

        Provide exactly one of the three source parameters.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            name: Name for the asset
            image_data_base64: Base64-encoded image bytes
            image_url: Public URL to download the image from
            image_file_path: Absolute path to a local image file
            mime_type: MIME type (auto-detected from URL or file extension)

        Returns:
            Created asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            if image_file_path:
                p = Path(image_file_path)
                raw_bytes = p.read_bytes()
                guessed = mimetypes.guess_type(str(p))[0]
                if guessed:
                    mime_type = guessed
            elif image_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        resp.raise_for_status()
                        raw_bytes = await resp.read()
                        content_type = resp.content_type or mime_type
                        if "png" in content_type:
                            mime_type = "image/png"
                        elif "gif" in content_type:
                            mime_type = "image/gif"
            elif image_data_base64:
                raw_bytes = base64.b64decode(image_data_base64)
            else:
                raise ValueError(
                    "Provide one of: image_file_path, image_url, or image_data_base64"
                )

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.IMAGE
            asset.name = name

            image_asset = ImageAsset()
            image_asset.data = raw_bytes
            image_asset.mime_type = self.get_mime_type_enum(mime_type)
            asset.image_asset = image_asset

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create image asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_youtube_video_asset(
        self,
        ctx: Context,
        customer_id: str,
        youtube_video_id: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a YouTube video asset.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            youtube_video_id: The YouTube video ID
            name: Optional name for the asset

        Returns:
            Created asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            # Create asset
            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.YOUTUBE_VIDEO

            # Set name
            if name:
                asset.name = name
            else:
                asset.name = f"YouTube: {youtube_video_id}"

            # Create YouTube video asset
            youtube_video = YoutubeVideoAsset()
            youtube_video.youtube_video_id = youtube_video_id
            asset.youtube_video_asset = youtube_video

            # Create operation
            operation = AssetOperation()
            operation.create = asset

            # Create request
            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            # Make the API call
            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create YouTube video asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_sitelink_asset(
        self,
        ctx: Context,
        customer_id: str,
        link_text: str,
        final_urls: List[str],
        description1: Optional[str] = None,
        description2: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a sitelink asset.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            link_text: Display text for the sitelink (1-25 chars)
            final_urls: Landing page URLs
            description1: First description line (1-35 chars)
            description2: Second description line (1-35 chars)
            name: Optional asset name

        Returns:
            Created asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.SITELINK
            asset.name = name or f"Sitelink: {link_text}"
            asset.final_urls.extend(final_urls)

            sitelink = SitelinkAsset()
            sitelink.link_text = link_text
            if description1:
                sitelink.description1 = description1
            if description2:
                sitelink.description2 = description2
            asset.sitelink_asset = sitelink

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create sitelink asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_callout_asset(
        self,
        ctx: Context,
        customer_id: str,
        callout_text: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a callout asset.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            callout_text: Callout text (1-25 chars)
            name: Optional asset name

        Returns:
            Created asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.CALLOUT
            asset.name = name or f"Callout: {callout_text}"

            callout = CalloutAsset()
            callout.callout_text = callout_text
            asset.callout_asset = callout

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create callout asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_structured_snippet_asset(
        self,
        ctx: Context,
        customer_id: str,
        header: str,
        values: List[str],
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a structured snippet asset.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            header: Snippet header (predefined, e.g. "Brands", "Types")
            values: Snippet values (3-10 items, each 1-25 chars)
            name: Optional asset name

        Returns:
            Created asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.STRUCTURED_SNIPPET
            asset.name = name or f"Snippet: {header}"

            snippet = StructuredSnippetAsset()
            snippet.header = header
            snippet.values.extend(values)
            asset.structured_snippet_asset = snippet

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create structured snippet asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_call_asset(
        self,
        ctx: Context,
        customer_id: str,
        country_code: str,
        phone_number: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a call asset.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            country_code: Two-letter country code (e.g. "US")
            phone_number: Phone number (e.g. "1234567890")
            name: Optional asset name

        Returns:
            Created asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.CALL
            asset.name = name or f"Call: {country_code} {phone_number}"

            call = CallAsset()
            call.country_code = country_code
            call.phone_number = phone_number
            asset.call_asset = call

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create call asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_price_asset(
        self,
        ctx: Context,
        customer_id: str,
        price_type: str,
        language_code: str,
        price_offerings: List[Dict[str, Any]],
        price_qualifier: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a price extension asset.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            price_type: BRANDS, EVENTS, LOCATIONS, NEIGHBORHOODS,
                PRODUCT_CATEGORIES, PRODUCT_TIERS, SERVICES,
                SERVICE_CATEGORIES, or SERVICE_TIERS
            language_code: BCP 47 language tag, e.g. "en"
            price_offerings: 3-8 dicts, each with:
                - header: 1-25 chars
                - description: 1-25 chars
                - price: numeric amount (e.g. 19.99)
                - currency_code: 3-letter ISO 4217 code, e.g. "USD"
                - final_url: landing page URL
                - unit: optional, e.g. PER_HOUR, PER_DAY, PER_MONTH
            price_qualifier: Optional FROM, UP_TO, or AVERAGE
            name: Optional asset name

        Returns:
            Created price asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.PRICE
            asset.name = name or f"Price: {price_type}"

            price_asset = PriceAsset()
            price_asset.type_ = resolve_enum(
                PriceExtensionTypeEnum.PriceExtensionType, price_type, "price_type"
            )
            price_asset.language_code = language_code
            if price_qualifier:
                price_asset.price_qualifier = resolve_enum(
                    PriceExtensionPriceQualifierEnum.PriceExtensionPriceQualifier,
                    price_qualifier,
                    "price_qualifier",
                )

            for offering in price_offerings:
                po = PriceOffering()
                po.header = offering["header"]
                po.description = offering["description"]
                po.final_url = offering["final_url"]
                money = Money()
                money.currency_code = offering["currency_code"]
                money.amount_micros = int(float(offering["price"]) * 1_000_000)
                po.price = money
                if offering.get("unit"):
                    po.unit = resolve_enum(
                        PriceExtensionPriceUnitEnum.PriceExtensionPriceUnit,
                        offering["unit"],
                        "unit",
                    )
                price_asset.price_offerings.append(po)

            asset.price_asset = price_asset

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create price asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_app_asset(
        self,
        ctx: Context,
        customer_id: str,
        app_id: str,
        app_store: str,
        link_text: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an app extension asset.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            app_id: Platform-native app ID, e.g. "com.android.ebay" or an
                iOS numeric ID
            app_store: APPLE_APP_STORE or GOOGLE_APP_STORE
            link_text: Visible link text (1-25 chars)
            start_date: Optional start date, yyyy-MM-dd
            end_date: Optional end date, yyyy-MM-dd
            name: Optional asset name

        Returns:
            Created app asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.MOBILE_APP
            asset.name = name or f"App: {app_id}"

            app_asset = MobileAppAsset()
            app_asset.app_id = app_id
            app_asset.app_store = resolve_enum(
                MobileAppVendorEnum.MobileAppVendor, app_store, "app_store"
            )
            app_asset.link_text = link_text
            if start_date:
                app_asset.start_date = start_date
            if end_date:
                app_asset.end_date = end_date
            asset.mobile_app_asset = app_asset

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create app asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_promotion_asset(
        self,
        ctx: Context,
        customer_id: str,
        promotion_target: str,
        language_code: Optional[str] = None,
        percent_off: Optional[int] = None,
        money_amount_off: Optional[float] = None,
        money_currency_code: Optional[str] = None,
        promotion_code: Optional[str] = None,
        orders_over_amount: Optional[float] = None,
        orders_over_amount_currency_code: Optional[str] = None,
        discount_modifier: Optional[str] = None,
        occasion: Optional[str] = None,
        redemption_start_date: Optional[str] = None,
        redemption_end_date: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a promotion extension asset.

        Exactly one of `percent_off` / `money_amount_off` is required
        (mutually exclusive discount types). `promotion_code` and
        `orders_over_amount` are also mutually exclusive if both given,
        `promotion_code` wins - barcode/QR-code triggers aren't wrapped.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            promotion_target: Freeform description of what's being
                promoted, e.g. "Site-wide sale"
            language_code: BCP 47 language tag
            percent_off: Percent discount, e.g. 20 for 20% (mutually
                exclusive with money_amount_off)
            money_amount_off: Fixed discount amount (mutually exclusive
                with percent_off, requires money_currency_code)
            money_currency_code: 3-letter ISO 4217 code for
                money_amount_off
            promotion_code: Code the user enters to redeem
            orders_over_amount: Minimum order amount to qualify (requires
                orders_over_amount_currency_code)
            orders_over_amount_currency_code: 3-letter ISO 4217 code for
                orders_over_amount
            discount_modifier: Optional UP_TO
            occasion: Optional occasion, e.g. BLACK_FRIDAY, NEW_YEARS
            redemption_start_date: Optional yyyy-MM-dd
            redemption_end_date: Optional yyyy-MM-dd
            name: Optional asset name

        Returns:
            Created promotion asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            if percent_off is None and money_amount_off is None:
                raise ValueError(
                    "Provide exactly one of: percent_off, money_amount_off"
                )

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.PROMOTION
            asset.name = name or f"Promotion: {promotion_target}"

            promo = PromotionAsset()
            promo.promotion_target = promotion_target
            if language_code:
                promo.language_code = language_code
            if discount_modifier:
                promo.discount_modifier = resolve_enum(
                    PromotionExtensionDiscountModifierEnum.PromotionExtensionDiscountModifier,
                    discount_modifier,
                    "discount_modifier",
                )
            if occasion:
                promo.occasion = resolve_enum(
                    PromotionExtensionOccasionEnum.PromotionExtensionOccasion,
                    occasion,
                    "occasion",
                )
            if redemption_start_date:
                promo.redemption_start_date = redemption_start_date
            if redemption_end_date:
                promo.redemption_end_date = redemption_end_date

            if percent_off is not None:
                promo.percent_off = percent_off
            else:
                assert money_amount_off is not None
                money = Money()
                money.currency_code = money_currency_code or ""
                money.amount_micros = int(money_amount_off * 1_000_000)
                promo.money_amount_off = money

            if promotion_code:
                promo.promotion_code = promotion_code
            elif orders_over_amount is not None:
                money = Money()
                money.currency_code = orders_over_amount_currency_code or ""
                money.amount_micros = int(orders_over_amount * 1_000_000)
                promo.orders_over_amount = money

            asset.promotion_asset = promo

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create promotion asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_lead_form_asset(
        self,
        ctx: Context,
        customer_id: str,
        business_name: str,
        call_to_action_type: str,
        call_to_action_description: str,
        headline: str,
        description: str,
        privacy_policy_url: str,
        field_input_types: List[str],
        webhook_url: str,
        webhook_secret: Optional[str] = None,
        webhook_payload_schema_version: Optional[int] = None,
        post_submit_headline: Optional[str] = None,
        post_submit_description: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a lead form extension asset.

        Only predefined input fields are supported (no custom qualifying
        questions, no single-choice answers) and delivery is always via
        webhook - the API has no email-delivery option in v25.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            business_name: The advertised business's name
            call_to_action_type: e.g. LEARN_MORE, GET_QUOTE, SIGN_UP,
                SUBSCRIBE, BOOK_NOW, GET_OFFER, REGISTER
            call_to_action_description: Value proposition shown on the
                expand button
            headline: Headline of the expanded form
            description: Detailed description of what the form asks for
            privacy_policy_url: Link to the data-handling policy page
            field_input_types: Ordered predefined fields to collect, e.g.
                ["FULL_NAME", "EMAIL", "PHONE_NUMBER"]
            webhook_url: Advertiser endpoint leads are POSTed to
            webhook_secret: Optional anti-spoofing secret in the payload
            webhook_payload_schema_version: Optional payload schema version
            post_submit_headline: Optional headline shown after submission
            post_submit_description: Optional description shown after
                submission
            name: Optional asset name

        Returns:
            Created lead form asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.LEAD_FORM
            asset.name = name or f"Lead form: {business_name}"

            lead_form = LeadFormAsset()
            lead_form.business_name = business_name
            lead_form.call_to_action_type = resolve_enum(
                LeadFormCallToActionTypeEnum.LeadFormCallToActionType,
                call_to_action_type,
                "call_to_action_type",
            )
            lead_form.call_to_action_description = call_to_action_description
            lead_form.headline = headline
            lead_form.description = description
            lead_form.privacy_policy_url = privacy_policy_url
            if post_submit_headline:
                lead_form.post_submit_headline = post_submit_headline
            if post_submit_description:
                lead_form.post_submit_description = post_submit_description

            for input_type in field_input_types:
                field = LeadFormField()
                field.input_type = resolve_enum(
                    LeadFormFieldUserInputTypeEnum.LeadFormFieldUserInputType,
                    input_type,
                    "field_input_types",
                )
                lead_form.fields.append(field)

            webhook = WebhookDelivery()
            webhook.advertiser_webhook_url = webhook_url
            if webhook_secret:
                webhook.google_secret = webhook_secret
            if webhook_payload_schema_version is not None:
                webhook.payload_schema_version = webhook_payload_schema_version
            delivery = LeadFormDeliveryMethod()
            delivery.webhook = webhook
            lead_form.delivery_methods.append(delivery)

            asset.lead_form_asset = lead_form

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create lead form asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_location_asset(
        self,
        ctx: Context,
        customer_id: str,
        place_id: str,
        location_ownership_type: str = "BUSINESS_OWNER",
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a location extension asset.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            place_id: Google Places place ID for the location
            location_ownership_type: BUSINESS_OWNER (served as a location
                extension) or AFFILIATE (served as an affiliate location)
            name: Optional asset name

        Returns:
            Created location asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.LOCATION
            asset.name = name or f"Location: {place_id}"

            location = LocationAsset()
            location.place_id = place_id
            location.location_ownership_type = resolve_enum(
                LocationOwnershipTypeEnum.LocationOwnershipType,
                location_ownership_type,
                "location_ownership_type",
            )
            asset.location_asset = location

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create location asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_call_to_action_asset(
        self,
        ctx: Context,
        customer_id: str,
        call_to_action: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a call-to-action asset (used as a button overlay on
        image/video assets in some ad formats).

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            call_to_action: e.g. LEARN_MORE, SHOP_NOW, BUY_NOW, SIGN_UP,
                BOOK_NOW, DOWNLOAD, SUBSCRIBE, CONTACT_US
            name: Optional asset name

        Returns:
            Created call-to-action asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.CALL_TO_ACTION
            asset.name = name or f"CTA: {call_to_action}"

            cta = CallToActionAsset()
            cta.call_to_action = resolve_enum(
                CallToActionTypeEnum.CallToActionType,
                call_to_action,
                "call_to_action",
            )
            asset.call_to_action_asset = cta

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create call-to-action asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def create_business_message_asset(
        self,
        ctx: Context,
        customer_id: str,
        starter_message: str,
        whatsapp_country_code: str,
        whatsapp_phone_number: str,
        call_to_action_type: Optional[str] = None,
        call_to_action_description: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a business message extension asset.

        Only the WhatsApp provider is wrapped (Facebook Messenger and Zalo
        share the same shape and can be added the same way if needed).

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            starter_message: Welcome message prompting the user to start
                a conversation
            whatsapp_country_code: Two-letter country code for the
                WhatsApp phone number
            whatsapp_phone_number: WhatsApp business phone number
            call_to_action_type: Optional, e.g. CONTACT_US, GET_QUOTE,
                GET_INFO, GET_OFFER, APPLY_NOW, BOOK_NOW (requires
                call_to_action_description too)
            call_to_action_description: Optional value proposition text
            name: Optional asset name

        Returns:
            Created business message asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            asset = Asset()
            asset.type_ = AssetTypeEnum.AssetType.BUSINESS_MESSAGE
            asset.name = name or f"Business message: {whatsapp_phone_number}"

            message_asset = BusinessMessageAsset()
            message_asset.message_provider = (
                BusinessMessageProviderEnum.BusinessMessageProvider.WHATSAPP
            )
            message_asset.starter_message = starter_message

            whatsapp_info = WhatsappBusinessMessageInfo()
            whatsapp_info.country_code = whatsapp_country_code
            whatsapp_info.phone_number = whatsapp_phone_number
            message_asset.whatsapp_info = whatsapp_info

            if call_to_action_type and call_to_action_description:
                cta = BusinessMessageCallToActionInfo()
                cta.call_to_action_selection = resolve_enum(
                    BusinessMessageCallToActionTypeEnum.BusinessMessageCallToActionType,
                    call_to_action_type,
                    "call_to_action_type",
                )
                cta.call_to_action_description = call_to_action_description
                message_asset.call_to_action = cta

            asset.business_message_asset = message_asset

            operation = AssetOperation()
            operation.create = asset

            request = MutateAssetsRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateAssetsResponse = self.client.mutate_assets(request=request)
            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to create business message asset: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def search_assets(
        self,
        ctx: Context,
        customer_id: str,
        asset_types: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search for assets in the account.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            asset_types: Optional list of asset types to filter by
            limit: Maximum number of results

        Returns:
            List of asset details
        """
        try:
            customer_id = format_customer_id(customer_id)

            # Use GoogleAdsService for search
            sdk_client = get_sdk_client()
            google_ads_service: GoogleAdsServiceClient = sdk_client.client.get_service(
                "GoogleAdsService"
            )

            # Build query
            query = """
                SELECT
                    asset.id,
                    asset.name,
                    asset.type,
                    asset.resource_name,
                    asset.text_asset.text,
                    asset.image_asset.file_size,
                    asset.youtube_video_asset.youtube_video_id
                FROM asset
            """

            if asset_types:
                type_conditions = [f"asset.type = '{t}'" for t in asset_types]
                query += " WHERE " + " OR ".join(type_conditions)

            query += f" ORDER BY asset.id DESC LIMIT {limit}"

            # Execute search
            response = google_ads_service.search(customer_id=customer_id, query=query)

            # Process results
            assets = []
            for row in response:
                asset = row.asset
                asset_dict = {
                    "asset_id": str(asset.id),
                    "name": asset.name,
                    "type": asset.type_.name,
                    "resource_name": asset.resource_name,
                }

                # Add type-specific fields
                if asset.type_ == AssetTypeEnum.AssetType.TEXT:
                    asset_dict["text"] = asset.text_asset.text
                elif asset.type_ == AssetTypeEnum.AssetType.IMAGE:
                    asset_dict["file_size"] = str(asset.image_asset.file_size)
                elif asset.type_ == AssetTypeEnum.AssetType.YOUTUBE_VIDEO:
                    asset_dict["youtube_video_id"] = (
                        asset.youtube_video_asset.youtube_video_id
                    )

                assets.append(asset_dict)

            await ctx.log(
                level="info",
                message=f"Found {len(assets)} assets",
            )

            return assets

        except Exception as e:
            error_msg = f"Failed to search assets: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    def get_mime_type_enum(self, mime_type: str):
        """Convert MIME type string to enum value."""
        from google.ads.googleads.v25.enums.types.mime_type import MimeTypeEnum

        mime_type_map = {
            "image/jpeg": MimeTypeEnum.MimeType.IMAGE_JPEG,
            "image/png": MimeTypeEnum.MimeType.IMAGE_PNG,
            "image/gif": MimeTypeEnum.MimeType.IMAGE_GIF,
        }

        return mime_type_map.get(
            mime_type.lower(),
            MimeTypeEnum.MimeType.IMAGE_JPEG,  # Default
        )


def create_asset_tools(service: AssetService) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the asset service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def create_text_asset(
        ctx: Context,
        customer_id: str,
        text: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a text asset.

        Args:
            customer_id: The customer ID
            text: The text content
            name: Optional name for the asset

        Returns:
            Created asset details including resource_name and asset_id
        """
        return await service.create_text_asset(
            ctx=ctx,
            customer_id=customer_id,
            text=text,
            name=name,
        )

    async def create_image_asset(
        ctx: Context,
        customer_id: str,
        name: str,
        image_data_base64: Optional[str] = None,
        image_url: Optional[str] = None,
        image_file_path: Optional[str] = None,
        mime_type: str = "image/jpeg",
    ) -> Dict[str, Any]:
        """Create an image asset from a local file, URL, or base64 string.

        Provide exactly one of the three source parameters.

        Args:
            customer_id: The customer ID
            name: Name for the asset (e.g. "Hero Banner 1200x628")
            image_data_base64: Base64-encoded image data
            image_url: Public URL to download the image from
            image_file_path: Absolute local file path (e.g. "C:/images/logo.png")
            mime_type: MIME type - auto-detected from file extension or URL

        Returns:
            Created asset details including resource_name and asset_id
        """
        return await service.create_image_asset(
            ctx=ctx,
            customer_id=customer_id,
            name=name,
            image_data_base64=image_data_base64,
            image_url=image_url,
            image_file_path=image_file_path,
            mime_type=mime_type,
        )

    async def create_youtube_video_asset(
        ctx: Context,
        customer_id: str,
        youtube_video_id: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a YouTube video asset.

        Args:
            customer_id: The customer ID
            youtube_video_id: The YouTube video ID (e.g., "dQw4w9WgXcQ")
            name: Optional name for the asset

        Returns:
            Created asset details including resource_name and asset_id
        """
        return await service.create_youtube_video_asset(
            ctx=ctx,
            customer_id=customer_id,
            youtube_video_id=youtube_video_id,
            name=name,
        )

    async def search_assets(
        ctx: Context,
        customer_id: str,
        asset_types: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search for assets in the account.

        Args:
            customer_id: The customer ID
            asset_types: Optional list of asset types to filter by (TEXT, IMAGE, YOUTUBE_VIDEO)
            limit: Maximum number of results

        Returns:
            List of asset details
        """
        return await service.search_assets(
            ctx=ctx,
            customer_id=customer_id,
            asset_types=asset_types,
            limit=limit,
        )

    async def create_sitelink_asset(
        ctx: Context,
        customer_id: str,
        link_text: str,
        final_urls: List[str],
        description1: Optional[str] = None,
        description2: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a sitelink extension asset.

        Args:
            customer_id: The customer ID
            link_text: Display text for the sitelink (1-25 chars)
            final_urls: Landing page URLs for the sitelink
            description1: Optional first description line (1-35 chars)
            description2: Optional second description line (1-35 chars)
            name: Optional asset name

        Returns:
            Created sitelink asset details including resource_name
        """
        return await service.create_sitelink_asset(
            ctx=ctx,
            customer_id=customer_id,
            link_text=link_text,
            final_urls=final_urls,
            description1=description1,
            description2=description2,
            name=name,
        )

    async def create_callout_asset(
        ctx: Context,
        customer_id: str,
        callout_text: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a callout extension asset.

        Args:
            customer_id: The customer ID
            callout_text: The callout text (1-25 chars)
            name: Optional asset name

        Returns:
            Created callout asset details including resource_name
        """
        return await service.create_callout_asset(
            ctx=ctx,
            customer_id=customer_id,
            callout_text=callout_text,
            name=name,
        )

    async def create_structured_snippet_asset(
        ctx: Context,
        customer_id: str,
        header: str,
        values: List[str],
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a structured snippet extension asset.

        Args:
            customer_id: The customer ID
            header: Snippet header (e.g. "Brands", "Types", "Destinations", "Styles")
            values: List of snippet values (3-10 items, each 1-25 chars)
            name: Optional asset name

        Returns:
            Created structured snippet asset details including resource_name
        """
        return await service.create_structured_snippet_asset(
            ctx=ctx,
            customer_id=customer_id,
            header=header,
            values=values,
            name=name,
        )

    async def create_call_asset(
        ctx: Context,
        customer_id: str,
        country_code: str,
        phone_number: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a call extension asset.

        Args:
            customer_id: The customer ID
            country_code: Two-letter country code (e.g. "US", "GB")
            phone_number: Phone number (e.g. "1234567890", "(123)456-7890")
            name: Optional asset name

        Returns:
            Created call asset details including resource_name
        """
        return await service.create_call_asset(
            ctx=ctx,
            customer_id=customer_id,
            country_code=country_code,
            phone_number=phone_number,
            name=name,
        )

    async def create_price_asset(
        ctx: Context,
        customer_id: str,
        price_type: str,
        language_code: str,
        price_offerings: List[Dict[str, Any]],
        price_qualifier: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a price extension asset.

        Args:
            customer_id: The customer ID
            price_type: BRANDS, EVENTS, LOCATIONS, NEIGHBORHOODS,
                PRODUCT_CATEGORIES, PRODUCT_TIERS, SERVICES,
                SERVICE_CATEGORIES, or SERVICE_TIERS
            language_code: BCP 47 language tag, e.g. "en"
            price_offerings: 3-8 dicts, each with header, description,
                price (numeric), currency_code, final_url, and optional
                unit (e.g. PER_HOUR, PER_MONTH)
            price_qualifier: Optional FROM, UP_TO, or AVERAGE
            name: Optional asset name

        Returns:
            Created price asset details including resource_name
        """
        return await service.create_price_asset(
            ctx=ctx,
            customer_id=customer_id,
            price_type=price_type,
            language_code=language_code,
            price_offerings=price_offerings,
            price_qualifier=price_qualifier,
            name=name,
        )

    async def create_app_asset(
        ctx: Context,
        customer_id: str,
        app_id: str,
        app_store: str,
        link_text: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an app extension asset.

        Args:
            customer_id: The customer ID
            app_id: Platform-native app ID, e.g. "com.android.ebay"
            app_store: APPLE_APP_STORE or GOOGLE_APP_STORE
            link_text: Visible link text (1-25 chars)
            start_date: Optional start date, yyyy-MM-dd
            end_date: Optional end date, yyyy-MM-dd
            name: Optional asset name

        Returns:
            Created app asset details including resource_name
        """
        return await service.create_app_asset(
            ctx=ctx,
            customer_id=customer_id,
            app_id=app_id,
            app_store=app_store,
            link_text=link_text,
            start_date=start_date,
            end_date=end_date,
            name=name,
        )

    async def create_promotion_asset(
        ctx: Context,
        customer_id: str,
        promotion_target: str,
        language_code: Optional[str] = None,
        percent_off: Optional[int] = None,
        money_amount_off: Optional[float] = None,
        money_currency_code: Optional[str] = None,
        promotion_code: Optional[str] = None,
        orders_over_amount: Optional[float] = None,
        orders_over_amount_currency_code: Optional[str] = None,
        discount_modifier: Optional[str] = None,
        occasion: Optional[str] = None,
        redemption_start_date: Optional[str] = None,
        redemption_end_date: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a promotion extension asset. Exactly one of percent_off
        / money_amount_off is required.

        Args:
            customer_id: The customer ID
            promotion_target: Freeform description, e.g. "Site-wide sale"
            language_code: BCP 47 language tag
            percent_off: Percent discount, e.g. 20 for 20%
            money_amount_off: Fixed discount amount (requires
                money_currency_code)
            money_currency_code: 3-letter ISO 4217 code for
                money_amount_off
            promotion_code: Code the user enters to redeem
            orders_over_amount: Minimum order amount to qualify (requires
                orders_over_amount_currency_code)
            orders_over_amount_currency_code: 3-letter ISO 4217 code for
                orders_over_amount
            discount_modifier: Optional UP_TO
            occasion: Optional occasion, e.g. BLACK_FRIDAY, NEW_YEARS
            redemption_start_date: Optional yyyy-MM-dd
            redemption_end_date: Optional yyyy-MM-dd
            name: Optional asset name

        Returns:
            Created promotion asset details including resource_name
        """
        return await service.create_promotion_asset(
            ctx=ctx,
            customer_id=customer_id,
            promotion_target=promotion_target,
            language_code=language_code,
            percent_off=percent_off,
            money_amount_off=money_amount_off,
            money_currency_code=money_currency_code,
            promotion_code=promotion_code,
            orders_over_amount=orders_over_amount,
            orders_over_amount_currency_code=orders_over_amount_currency_code,
            discount_modifier=discount_modifier,
            occasion=occasion,
            redemption_start_date=redemption_start_date,
            redemption_end_date=redemption_end_date,
            name=name,
        )

    async def create_lead_form_asset(
        ctx: Context,
        customer_id: str,
        business_name: str,
        call_to_action_type: str,
        call_to_action_description: str,
        headline: str,
        description: str,
        privacy_policy_url: str,
        field_input_types: List[str],
        webhook_url: str,
        webhook_secret: Optional[str] = None,
        webhook_payload_schema_version: Optional[int] = None,
        post_submit_headline: Optional[str] = None,
        post_submit_description: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a lead form extension asset. Only predefined input
        fields are supported and delivery is always via webhook.

        Args:
            customer_id: The customer ID
            business_name: The advertised business's name
            call_to_action_type: e.g. LEARN_MORE, GET_QUOTE, SIGN_UP,
                SUBSCRIBE, BOOK_NOW, GET_OFFER, REGISTER
            call_to_action_description: Value proposition shown on the
                expand button
            headline: Headline of the expanded form
            description: Detailed description of what the form asks for
            privacy_policy_url: Link to the data-handling policy page
            field_input_types: Ordered predefined fields to collect, e.g.
                ["FULL_NAME", "EMAIL", "PHONE_NUMBER"]
            webhook_url: Advertiser endpoint leads are POSTed to
            webhook_secret: Optional anti-spoofing secret in the payload
            webhook_payload_schema_version: Optional payload schema version
            post_submit_headline: Optional headline shown after submission
            post_submit_description: Optional description shown after
                submission
            name: Optional asset name

        Returns:
            Created lead form asset details including resource_name
        """
        return await service.create_lead_form_asset(
            ctx=ctx,
            customer_id=customer_id,
            business_name=business_name,
            call_to_action_type=call_to_action_type,
            call_to_action_description=call_to_action_description,
            headline=headline,
            description=description,
            privacy_policy_url=privacy_policy_url,
            field_input_types=field_input_types,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            webhook_payload_schema_version=webhook_payload_schema_version,
            post_submit_headline=post_submit_headline,
            post_submit_description=post_submit_description,
            name=name,
        )

    async def create_location_asset(
        ctx: Context,
        customer_id: str,
        place_id: str,
        location_ownership_type: str = "BUSINESS_OWNER",
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a location extension asset.

        Args:
            customer_id: The customer ID
            place_id: Google Places place ID for the location
            location_ownership_type: BUSINESS_OWNER (served as a location
                extension) or AFFILIATE (served as an affiliate location)
            name: Optional asset name

        Returns:
            Created location asset details including resource_name
        """
        return await service.create_location_asset(
            ctx=ctx,
            customer_id=customer_id,
            place_id=place_id,
            location_ownership_type=location_ownership_type,
            name=name,
        )

    async def create_call_to_action_asset(
        ctx: Context,
        customer_id: str,
        call_to_action: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a call-to-action asset (button overlay used on
        image/video assets in some ad formats).

        Args:
            customer_id: The customer ID
            call_to_action: e.g. LEARN_MORE, SHOP_NOW, BUY_NOW, SIGN_UP,
                BOOK_NOW, DOWNLOAD, SUBSCRIBE, CONTACT_US
            name: Optional asset name

        Returns:
            Created call-to-action asset details including resource_name
        """
        return await service.create_call_to_action_asset(
            ctx=ctx,
            customer_id=customer_id,
            call_to_action=call_to_action,
            name=name,
        )

    async def create_business_message_asset(
        ctx: Context,
        customer_id: str,
        starter_message: str,
        whatsapp_country_code: str,
        whatsapp_phone_number: str,
        call_to_action_type: Optional[str] = None,
        call_to_action_description: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a business message extension asset (WhatsApp provider
        only - Facebook Messenger and Zalo share the same shape).

        Args:
            customer_id: The customer ID
            starter_message: Welcome message prompting the user to start
                a conversation
            whatsapp_country_code: Two-letter country code for the
                WhatsApp phone number
            whatsapp_phone_number: WhatsApp business phone number
            call_to_action_type: Optional, e.g. CONTACT_US, GET_QUOTE,
                GET_INFO, GET_OFFER, APPLY_NOW, BOOK_NOW (requires
                call_to_action_description too)
            call_to_action_description: Optional value proposition text
            name: Optional asset name

        Returns:
            Created business message asset details including resource_name
        """
        return await service.create_business_message_asset(
            ctx=ctx,
            customer_id=customer_id,
            starter_message=starter_message,
            whatsapp_country_code=whatsapp_country_code,
            whatsapp_phone_number=whatsapp_phone_number,
            call_to_action_type=call_to_action_type,
            call_to_action_description=call_to_action_description,
            name=name,
        )

    tools.extend(
        [
            create_text_asset,
            create_image_asset,
            create_youtube_video_asset,
            create_sitelink_asset,
            create_callout_asset,
            create_structured_snippet_asset,
            create_call_asset,
            create_price_asset,
            create_app_asset,
            create_promotion_asset,
            create_lead_form_asset,
            create_location_asset,
            create_call_to_action_asset,
            create_business_message_asset,
            search_assets,
        ]
    )
    return tools


def register_asset_tools(mcp: FastMCP[Any]) -> AssetService:
    """Register asset tools with the MCP server.

    Returns the AssetService instance for testing purposes.
    """
    service = AssetService()
    tools = create_asset_tools(service)

    # Register each tool
    for tool in tools:
        mcp.tool(tool)

    return service
