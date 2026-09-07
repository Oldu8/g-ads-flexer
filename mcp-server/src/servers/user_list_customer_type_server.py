"""User list customer type server using SDK implementation."""

from fastmcp import FastMCP

from src.services.audiences.user_list_customer_type_service import (
    register_user_list_customer_type_tools,
)

# Create the user list customer type server
user_list_customer_type_server = FastMCP(name="user-list-customer-type-service")

# Register the tools
register_user_list_customer_type_tools(user_list_customer_type_server)
