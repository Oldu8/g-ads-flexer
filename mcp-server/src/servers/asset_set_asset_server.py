"""Asset set asset server using SDK implementation."""

from fastmcp import FastMCP

from src.services.assets.asset_set_asset_service import register_asset_set_asset_tools

# Create the asset set asset server
asset_set_asset_server = FastMCP(name="asset-set-asset-service")

# Register the tools
register_asset_set_asset_tools(asset_set_asset_server)
