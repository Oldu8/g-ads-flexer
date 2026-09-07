"""Conversion value rule set server using SDK implementation."""

from fastmcp import FastMCP

from src.services.conversions.conversion_value_rule_set_service import (
    register_conversion_value_rule_set_tools,
)

# Create the conversion value rule set server
conversion_value_rule_set_server = FastMCP(name="conversion-value-rule-set-service")

# Register the tools
register_conversion_value_rule_set_tools(conversion_value_rule_set_server)
