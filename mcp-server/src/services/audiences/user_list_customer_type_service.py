"""User list customer type service implementation using Google Ads SDK."""

from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.enums.types.user_list_customer_type_category import (
    UserListCustomerTypeCategoryEnum,
)
from google.ads.googleads.v25.resources.types.user_list_customer_type import (
    UserListCustomerType,
)
from google.ads.googleads.v25.services.services.user_list_customer_type_service import (
    UserListCustomerTypeServiceClient,
)
from google.ads.googleads.v25.services.types.user_list_customer_type_service import (
    MutateUserListCustomerTypesRequest,
    MutateUserListCustomerTypesResponse,
    UserListCustomerTypeOperation,
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


class UserListCustomerTypeService:
    """Service for tagging a Customer Match user list with a customer-type
    category (e.g. PURCHASERS, CART_ABANDONERS), used by Customer Match /
    combined audiences that segment by customer lifecycle stage.
    """

    def __init__(self) -> None:
        """Initialize the user list customer type service."""
        self._client: Optional[UserListCustomerTypeServiceClient] = None

    @property
    def client(self) -> UserListCustomerTypeServiceClient:
        """Get the user list customer type service client."""
        if self._client is None:
            sdk_client = get_sdk_client()
            self._client = sdk_client.client.get_service(
                "UserListCustomerTypeService", version="v25"
            )
        assert self._client is not None
        return self._client

    async def add_customer_type_to_user_list(
        self,
        ctx: Context,
        customer_id: str,
        user_list_id: str,
        customer_type_category: str,
    ) -> Dict[str, Any]:
        """Tag a user list with a customer-type category.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            user_list_id: The user list ID
            customer_type_category: e.g. ALL_CUSTOMERS, PURCHASERS,
                HIGH_VALUE_CUSTOMERS, DISENGAGED_CUSTOMERS, QUALIFIED_LEADS,
                CONVERTED_LEADS, PAID_SUBSCRIBERS, CART_ABANDONERS

        Returns:
            Created user list customer type details
        """
        try:
            customer_id = format_customer_id(customer_id)
            user_list_resource = f"customers/{customer_id}/userLists/{user_list_id}"

            entry = UserListCustomerType()
            entry.user_list = user_list_resource
            entry.customer_type_category = resolve_enum(
                UserListCustomerTypeCategoryEnum.UserListCustomerTypeCategory,
                customer_type_category,
                "customer_type_category",
            )

            operation = UserListCustomerTypeOperation()
            operation.create = entry

            request = MutateUserListCustomerTypesRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response: MutateUserListCustomerTypesResponse = (
                self.client.mutate_user_list_customer_types(request=request)
            )

            await ctx.log(
                level="info",
                message=(
                    f"Tagged user list {user_list_id} with customer type "
                    f"{customer_type_category}"
                ),
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to add customer type to user list: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e

    async def remove_customer_type_from_user_list(
        self,
        ctx: Context,
        customer_id: str,
        user_list_id: str,
        customer_type_category: str,
    ) -> Dict[str, Any]:
        """Remove a customer-type tag from a user list.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            user_list_id: The user list ID
            customer_type_category: The customer-type category to remove

        Returns:
            Removal result
        """
        try:
            customer_id = format_customer_id(customer_id)
            category_enum = resolve_enum(
                UserListCustomerTypeCategoryEnum.UserListCustomerTypeCategory,
                customer_type_category,
                "customer_type_category",
            )
            resource_name = (
                f"customers/{customer_id}/userListCustomerTypes/"
                f"{user_list_id}~{category_enum.name}"
            )

            operation = UserListCustomerTypeOperation()
            operation.remove = resource_name

            request = MutateUserListCustomerTypesRequest()
            request.customer_id = customer_id
            request.operations = [operation]

            response = self.client.mutate_user_list_customer_types(request=request)

            await ctx.log(
                level="info",
                message=(
                    f"Removed customer type {customer_type_category} from "
                    f"user list {user_list_id}"
                ),
            )

            return serialize_proto_message(response)

        except GoogleAdsException as e:
            error_msg = format_ads_error(e)
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to remove customer type from user list: {str(e)}"
            await ctx.log(level="error", message=error_msg)
            raise Exception(error_msg) from e


def create_user_list_customer_type_tools(
    service: UserListCustomerTypeService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the user list customer type service.

    This returns a list of tool functions that can be registered with FastMCP.
    This approach makes the tools testable by allowing service injection.
    """
    tools = []

    async def add_customer_type_to_user_list(
        ctx: Context,
        customer_id: str,
        user_list_id: str,
        customer_type_category: str,
    ) -> Dict[str, Any]:
        """Tag a Customer Match user list with a customer-type category.

        Args:
            customer_id: The customer ID
            user_list_id: The user list ID
            customer_type_category: e.g. ALL_CUSTOMERS, PURCHASERS,
                HIGH_VALUE_CUSTOMERS, DISENGAGED_CUSTOMERS, QUALIFIED_LEADS,
                CONVERTED_LEADS, PAID_SUBSCRIBERS, CART_ABANDONERS

        Returns:
            Created user list customer type details
        """
        return await service.add_customer_type_to_user_list(
            ctx=ctx,
            customer_id=customer_id,
            user_list_id=user_list_id,
            customer_type_category=customer_type_category,
        )

    async def remove_customer_type_from_user_list(
        ctx: Context,
        customer_id: str,
        user_list_id: str,
        customer_type_category: str,
    ) -> Dict[str, Any]:
        """Remove a customer-type tag from a user list.

        Args:
            customer_id: The customer ID
            user_list_id: The user list ID
            customer_type_category: The customer-type category to remove

        Returns:
            Removal result
        """
        return await service.remove_customer_type_from_user_list(
            ctx=ctx,
            customer_id=customer_id,
            user_list_id=user_list_id,
            customer_type_category=customer_type_category,
        )

    tools.extend(
        [
            add_customer_type_to_user_list,
            remove_customer_type_from_user_list,
        ]
    )
    return tools


def register_user_list_customer_type_tools(
    mcp: FastMCP[Any],
) -> UserListCustomerTypeService:
    """Register user list customer type tools with the MCP server.

    Returns the UserListCustomerTypeService instance for testing purposes.
    """
    service = UserListCustomerTypeService()
    tools = create_user_list_customer_type_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
