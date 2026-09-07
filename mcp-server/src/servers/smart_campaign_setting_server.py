"""Smart campaign setting server using SDK implementation."""

from fastmcp import FastMCP

from src.services.campaign.smart_campaign_setting_service import (
    register_smart_campaign_setting_tools,
)

# Create the smart campaign setting server
smart_campaign_setting_server = FastMCP(name="smart-campaign-setting-service")

# Register the tools
register_smart_campaign_setting_tools(smart_campaign_setting_server)
