"""Automatically created asset removal server using SDK implementation."""

from fastmcp import FastMCP

from src.services.assets.automatically_created_asset_removal_service import (
    register_automatically_created_asset_removal_tools,
)

# Create the automatically created asset removal server
automatically_created_asset_removal_server = FastMCP(
    name="automatically-created-asset-removal-service"
)

# Register the tools
register_automatically_created_asset_removal_tools(
    automatically_created_asset_removal_server
)
