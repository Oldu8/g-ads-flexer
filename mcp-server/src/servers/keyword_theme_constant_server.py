"""Keyword theme constant server using SDK implementation."""

from fastmcp import FastMCP

from src.services.audiences.keyword_theme_constant_service import (
    register_keyword_theme_constant_tools,
)

# Create the keyword theme constant server
keyword_theme_constant_server = FastMCP(name="keyword-theme-constant-service")

# Register the tools
register_keyword_theme_constant_tools(keyword_theme_constant_server)
