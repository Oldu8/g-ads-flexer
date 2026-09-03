"""Campaign group server using SDK implementation."""

from fastmcp import FastMCP

from src.services.campaign.campaign_group_service import register_campaign_group_tools

# Create the campaign group server
campaign_group_server = FastMCP(name="campaign-group-service")

# Register the tools
register_campaign_group_tools(campaign_group_server)
