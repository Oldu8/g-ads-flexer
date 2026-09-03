"""Campaign goal config server using SDK implementation."""

from fastmcp import FastMCP

from src.services.campaign.campaign_goal_config_service import (
    register_campaign_goal_config_tools,
)

# Create the campaign goal config server
campaign_goal_config_server = FastMCP(name="campaign-goal-config-service")

# Register the tools
register_campaign_goal_config_tools(campaign_goal_config_server)
