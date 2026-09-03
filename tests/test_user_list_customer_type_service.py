"""Tests for UserListCustomerTypeService."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastmcp import Context
from google.ads.googleads.v25.services.services.user_list_customer_type_service import (
    UserListCustomerTypeServiceClient,
)
from google.ads.googleads.v25.services.types.user_list_customer_type_service import (
    MutateUserListCustomerTypesResponse,
)

from src.services.audiences.user_list_customer_type_service import (
    UserListCustomerTypeService,
    register_user_list_customer_type_tools,
)


@pytest.fixture
def user_list_customer_type_service(
    mock_sdk_client: Any,
) -> UserListCustomerTypeService:
    """Create a UserListCustomerTypeService instance with mocked dependencies."""
    mock_client = Mock(spec=UserListCustomerTypeServiceClient)
    mock_sdk_client.client.get_service.return_value = mock_client  # type: ignore

    with patch(
        "src.services.audiences.user_list_customer_type_service.get_sdk_client",
        return_value=mock_sdk_client,
    ):
        service = UserListCustomerTypeService()
        _ = service.client
        return service


@pytest.mark.asyncio
async def test_add_customer_type_to_user_list(
    user_list_customer_type_service: UserListCustomerTypeService,
    mock_ctx: Context,
) -> None:
    """Test tagging a user list with a customer type."""
    customer_id = "1234567890"
    mock_client = user_list_customer_type_service.client  # type: ignore
    mock_client.mutate_user_list_customer_types.return_value = Mock(  # type: ignore
        spec=MutateUserListCustomerTypesResponse, results=[]
    )

    await user_list_customer_type_service.add_customer_type_to_user_list(
        ctx=mock_ctx,
        customer_id=customer_id,
        user_list_id="111",
        customer_type_category="PURCHASERS",
    )

    request = mock_client.mutate_user_list_customer_types.call_args[1][  # type: ignore
        "request"
    ]
    assert request.customer_id == customer_id
    create = request.operations[0].create
    assert create.user_list == f"customers/{customer_id}/userLists/111"
    assert create.customer_type_category == 3  # PURCHASERS


@pytest.mark.asyncio
async def test_remove_customer_type_from_user_list(
    user_list_customer_type_service: UserListCustomerTypeService,
    mock_ctx: Context,
) -> None:
    """Test removing a customer-type tag from a user list."""
    customer_id = "1234567890"
    mock_client = user_list_customer_type_service.client  # type: ignore
    mock_client.mutate_user_list_customer_types.return_value = Mock(  # type: ignore
        spec=MutateUserListCustomerTypesResponse, results=[]
    )

    await user_list_customer_type_service.remove_customer_type_from_user_list(
        ctx=mock_ctx,
        customer_id=customer_id,
        user_list_id="111",
        customer_type_category="PURCHASERS",
    )

    request = mock_client.mutate_user_list_customer_types.call_args[1][  # type: ignore
        "request"
    ]
    assert request.operations[0].remove == (
        f"customers/{customer_id}/userListCustomerTypes/111~PURCHASERS"
    )


@pytest.mark.asyncio
async def test_error_handling(
    user_list_customer_type_service: UserListCustomerTypeService,
    mock_ctx: Context,
    google_ads_exception: Any,
) -> None:
    """Test error handling when API call fails."""
    mock_client = user_list_customer_type_service.client  # type: ignore
    mock_client.mutate_user_list_customer_types.side_effect = (  # type: ignore
        google_ads_exception
    )

    with pytest.raises(Exception) as exc_info:
        await user_list_customer_type_service.add_customer_type_to_user_list(
            ctx=mock_ctx,
            customer_id="1234567890",
            user_list_id="111",
            customer_type_category="PURCHASERS",
        )

    assert "Test Google Ads Exception" in str(exc_info.value)


def test_register_user_list_customer_type_tools() -> None:
    """Test tool registration."""
    mock_mcp = Mock()
    service = register_user_list_customer_type_tools(mock_mcp)

    assert isinstance(service, UserListCustomerTypeService)
    assert mock_mcp.tool.call_count == 2  # type: ignore
