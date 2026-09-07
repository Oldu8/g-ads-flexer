"""Shareable preview server using SDK implementation."""

from fastmcp import FastMCP

from src.services.campaign.shareable_preview_service import (
    register_shareable_preview_tools,
)

# Create the shareable preview server
shareable_preview_server = FastMCP(name="shareable-preview-service")

# Register the tools
register_shareable_preview_tools(shareable_preview_server)
