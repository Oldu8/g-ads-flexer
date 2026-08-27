"""Pending-change review server using SDK implementation."""

from fastmcp import FastMCP

from src.services.review.pending_change_service import register_pending_change_tools

# Create the pending-change server
pending_change_server = FastMCP(name="pending-change-service")

# Register the tools
register_pending_change_tools(pending_change_server)
