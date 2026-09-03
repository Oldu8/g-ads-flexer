"""Ad resource server using SDK implementation.

Wraps the standalone `AdService` (see `ad_resource_service.py` for why this
is a separate mount from `ad_server.py`, which wraps `AdGroupAdService`).
"""

from fastmcp import FastMCP

from src.services.ad_group.ad_resource_service import register_ad_resource_tools

# Create the ad resource server
ad_resource_server = FastMCP(name="ad-resource-service")

# Register the tools
register_ad_resource_tools(ad_resource_server)
