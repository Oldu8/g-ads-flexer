"""Customer asset set server using SDK implementation."""

from fastmcp import FastMCP

from src.services.assets.customer_asset_set_service import (
    register_customer_asset_set_tools,
)

# Create the customer asset set server
customer_asset_set_server = FastMCP(name="customer-asset-set-service")

# Register the tools
register_customer_asset_set_tools(customer_asset_set_server)
