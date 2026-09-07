"""Goal server using SDK implementation."""

from fastmcp import FastMCP

from src.services.conversions.goal_service import register_goal_tools

# Create the goal server
goal_server = FastMCP(name="goal-service")

# Register the tools
register_goal_tools(goal_server)
