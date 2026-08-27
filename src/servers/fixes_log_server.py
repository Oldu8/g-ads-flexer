"""Fixes-log server using SDK implementation."""

from fastmcp import FastMCP

from src.services.review.fixes_log_service import register_fixes_log_tools

# Create the fixes-log server
fixes_log_server = FastMCP(name="fixes-log-service")

# Register the tools
register_fixes_log_tools(fixes_log_server)
