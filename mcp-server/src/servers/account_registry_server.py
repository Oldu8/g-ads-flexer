"""Account registry server using SDK implementation.

Local config only - see `account_registry_service.py`. Not a Google Ads
API wrapper like every other server in this package.
"""

from fastmcp import FastMCP

from src.services.review.account_registry_service import (
    register_account_registry_tools,
)

# Create the account registry server
account_registry_server = FastMCP(name="account-registry-service")

# Register the tools
register_account_registry_tools(account_registry_server)
