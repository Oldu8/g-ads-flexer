"""Build the MCP server every entrypoint runs.

`main.py` (local stdio), `remote_main.py` (read-only HTTP) and, later,
`hosted_main.py` all call `create_server`: the same 102 mounted service
servers (the full 1:1 library, 366 tools), narrowed to one tool profile by
middleware. Mount prefixes define tool names; changing one renames tools and
breaks every client and the golden snapshots, so treat them as public API.
"""

from __future__ import annotations

from typing import Any, AsyncContextManager, Callable, List, Optional, Tuple

from fastmcp import Context, FastMCP
from fastmcp.server.auth import AuthProvider

from src.middleware.errors import ErrorMappingMiddleware
from src.middleware.tool_profile import ToolProfileMiddleware
from src.sdk_client import get_sdk_client
from src.servers.account_budget_proposal_server import (
    account_budget_proposal_server,
)
from src.servers.account_link_server import account_link_server
from src.servers.account_registry_server import account_registry_server
from src.servers.ad_group_ad_label_server import ad_group_ad_label_server
from src.servers.ad_group_ad_server import ad_group_ad_server
from src.servers.ad_group_asset_server import ad_group_asset_server
from src.servers.ad_group_asset_set_server import ad_group_asset_set_server
from src.servers.ad_group_bid_modifier_server import (
    ad_group_bid_modifier_server,
)
from src.servers.ad_group_criterion_customizer_server import (
    ad_group_criterion_customizer_server,
)
from src.servers.ad_group_criterion_label_server import (
    ad_group_criterion_label_server,
)
from src.servers.ad_group_criterion_server import ad_group_criterion_server
from src.servers.ad_group_customizer_server import (
    ad_group_customizer_server,
)
from src.servers.ad_group_label_server import ad_group_label_server
from src.servers.ad_group_server import ad_group_server
from src.servers.ad_parameter_server import (
    ad_parameter_server,
)
from src.servers.ad_resource_server import ad_resource_server
from src.servers.ad_server import ad_server
from src.servers.asset_group_asset_server import asset_group_asset_server
from src.servers.asset_group_server import asset_group_server
from src.servers.asset_group_signal_server import asset_group_signal_server
from src.servers.asset_server import asset_server
from src.servers.asset_set_asset_server import asset_set_asset_server
from src.servers.asset_set_server import asset_set_server
from src.servers.audience_insights_server import audience_insights_server
from src.servers.audience_server import audience_server
from src.servers.automatically_created_asset_removal_server import (
    automatically_created_asset_removal_server,
)
from src.servers.batch_job_server import batch_job_server
from src.servers.bidding_data_exclusion_server import (
    bidding_data_exclusion_server,
)
from src.servers.bidding_seasonality_adjustment_server import (
    bidding_seasonality_adjustment_server,
)
from src.servers.bidding_strategy_server import bidding_strategy_server
from src.servers.billing_setup_server import billing_setup_server
from src.servers.brand_suggestion_server import brand_suggestion_server
from src.servers.budget_server import budget_server
from src.servers.campaign_asset_server import campaign_asset_server
from src.servers.campaign_asset_set_server import campaign_asset_set_server
from src.servers.campaign_bid_modifier_server import (
    campaign_bid_modifier_server,
)
from src.servers.campaign_conversion_goal_server import (
    campaign_conversion_goal_server,
)
from src.servers.campaign_criterion_server import campaign_criterion_server
from src.servers.campaign_customizer_server import (
    campaign_customizer_server,
)
from src.servers.campaign_draft_server import campaign_draft_server
from src.servers.campaign_goal_config_server import (
    campaign_goal_config_server,
)
from src.servers.campaign_group_server import campaign_group_server
from src.servers.campaign_label_server import campaign_label_server
from src.servers.campaign_server import campaign_server
from src.servers.campaign_shared_set_server import (
    campaign_shared_set_server,
)
from src.servers.conversion_adjustment_upload_server import (
    conversion_adjustment_upload_server,
)
from src.servers.conversion_custom_variable_server import (
    conversion_custom_variable_server,
)
from src.servers.conversion_goal_campaign_config_server import (
    conversion_goal_campaign_config_server,
)
from src.servers.conversion_server import conversion_server
from src.servers.conversion_upload_server import conversion_upload_server
from src.servers.conversion_value_rule_server import (
    conversion_value_rule_server,
)
from src.servers.conversion_value_rule_set_server import (
    conversion_value_rule_set_server,
)
from src.servers.custom_audience_server import custom_audience_server
from src.servers.custom_conversion_goal_server import (
    custom_conversion_goal_server,
)
from src.servers.custom_interest_server import custom_interest_server
from src.servers.customer_asset_server import customer_asset_server
from src.servers.customer_asset_set_server import customer_asset_set_server
from src.servers.customer_client_link_server import (
    customer_client_link_server,
)
from src.servers.customer_conversion_goal_server import (
    customer_conversion_goal_server,
)
from src.servers.customer_customizer_server import (
    customer_customizer_server,
)
from src.servers.customer_label_server import customer_label_server
from src.servers.customer_manager_link_server import (
    customer_manager_link_server,
)
from src.servers.customer_negative_criterion_server import (
    customer_negative_criterion_server,
)
from src.servers.customer_server import customer_service_server
from src.servers.customer_user_access_invitation_server import (
    customer_user_access_invitation_server,
)
from src.servers.customer_user_access_server import (
    customer_user_access_server,
)
from src.servers.customizer_attribute_server import (
    customizer_sdk_server,
)
from src.servers.data_link_server import data_link_server
from src.servers.experiment_arm_server import experiment_arm_server
from src.servers.experiment_server import experiment_server
from src.servers.fixes_log_server import fixes_log_server
from src.servers.geo_target_constant_server import geo_target_constant_server
from src.servers.goal_server import goal_server
from src.servers.google_ads_field_server import google_ads_field_server
from src.servers.google_ads_server import google_ads_server
from src.servers.identity_verification_server import (
    identity_verification_server,
)
from src.servers.invoice_server import invoice_server
from src.servers.keyword_plan_ad_group_keyword_server import (
    keyword_plan_ad_group_keyword_server,
)
from src.servers.keyword_plan_ad_group_server import (
    keyword_plan_ad_group_server,
)
from src.servers.keyword_plan_campaign_keyword_server import (
    keyword_plan_campaign_keyword_server,
)
from src.servers.keyword_plan_campaign_server import (
    keyword_plan_campaign_server,
)
from src.servers.keyword_plan_idea_server import keyword_plan_idea_server
from src.servers.keyword_plan_server import keyword_plan_server
from src.servers.keyword_server import keyword_server
from src.servers.keyword_theme_constant_server import (
    keyword_theme_constant_server,
)
from src.servers.label_server import label_server
from src.servers.offline_user_data_job_server import (
    offline_user_data_job_server,
)
from src.servers.payments_account_server import (
    payments_account_server,
)
from src.servers.pending_change_server import pending_change_server
from src.servers.product_link_server import product_link_server
from src.servers.reach_plan_server import reach_plan_server
from src.servers.recommendation_server import recommendation_server
from src.servers.remarketing_action_server import remarketing_action_server
from src.servers.search_server import search_server
from src.servers.shareable_preview_server import shareable_preview_server
from src.servers.shared_criterion_server import shared_criterion_server
from src.servers.shared_set_server import shared_set_server
from src.servers.smart_campaign_server import smart_campaign_server
from src.servers.smart_campaign_setting_server import (
    smart_campaign_setting_server,
)
from src.servers.user_data_server import user_data_server
from src.servers.user_list_customer_type_server import (
    user_list_customer_type_server,
)
from src.servers.user_list_server import user_list_server
from src.tool_profiles import get_profile

MOUNTED_SERVERS: List[Tuple[str, FastMCP[Any]]] = [
    # --- core ---
    ("customer", customer_service_server),
    ("campaign", campaign_server),
    ("budget", budget_server),
    ("ad_group", ad_group_server),
    ("keyword", keyword_server),
    ("ad", ad_server),
    ("ad_resource", ad_resource_server),
    ("ad_group_ad", ad_group_ad_server),
    ("conversion", conversion_server),
    ("google_ads", google_ads_server),
    ("pending_change", pending_change_server),
    ("fixes_log", fixes_log_server),
    # --- assets ---
    ("asset", asset_server),
    ("asset_group", asset_group_server),
    ("asset_group_asset", asset_group_asset_server),
    ("asset_group_signal", asset_group_signal_server),
    ("asset_set", asset_set_server),
    ("asset_set_asset", asset_set_asset_server),
    ("ad_group_asset", ad_group_asset_server),
    ("ad_group_asset_set", ad_group_asset_set_server),
    ("campaign_asset", campaign_asset_server),
    ("campaign_asset_set", campaign_asset_set_server),
    ("customer_asset", customer_asset_server),
    ("customer_asset_set", customer_asset_set_server),
    ("automatically_created_asset_removal", automatically_created_asset_removal_server),
    # --- targeting ---
    ("campaign_criterion", campaign_criterion_server),
    ("ad_group_criterion", ad_group_criterion_server),
    ("customer_negative_criterion", customer_negative_criterion_server),
    ("geo_target", geo_target_constant_server),
    ("audience", audience_server),
    ("custom_interest", custom_interest_server),
    ("custom_audience", custom_audience_server),
    ("user_list", user_list_server),
    ("user_list_customer_type", user_list_customer_type_server),
    ("keyword_theme_constant", keyword_theme_constant_server),
    # --- bidding ---
    ("bidding_strategy", bidding_strategy_server),
    ("campaign_bid_modifier", campaign_bid_modifier_server),
    ("ag_bid_mod", ad_group_bid_modifier_server),
    ("bid_exclusion", bidding_data_exclusion_server),
    ("bid_seasonal", bidding_seasonality_adjustment_server),
    # --- planning ---
    ("keyword_plan", keyword_plan_server),
    ("keyword_plan_idea", keyword_plan_idea_server),
    ("keyword_plan_ad_group", keyword_plan_ad_group_server),
    ("keyword_plan_campaign", keyword_plan_campaign_server),
    ("kp_adgroup_kw", keyword_plan_ad_group_keyword_server),
    ("kp_campaign_kw", keyword_plan_campaign_keyword_server),
    ("reach_plan", reach_plan_server),
    ("brand_suggestion", brand_suggestion_server),
    # --- experiments ---
    ("experiment", experiment_server),
    ("experiment_arm", experiment_arm_server),
    ("campaign_draft", campaign_draft_server),
    # --- reporting ---
    ("search", search_server),
    ("google_ads_field", google_ads_field_server),
    ("recommendation", recommendation_server),
    ("invoice", invoice_server),
    ("audience_insights", audience_insights_server),
    ("shareable_preview", shareable_preview_server),
    # --- conversion ---
    ("conversion_upload", conversion_upload_server),
    ("conversion_adjustment_upload", conversion_adjustment_upload_server),
    ("conversion_value_rule", conversion_value_rule_server),
    ("conversion_value_rule_set", conversion_value_rule_set_server),
    ("conversion_custom_variable", conversion_custom_variable_server),
    ("conv_goal_config", conversion_goal_campaign_config_server),
    ("custom_conversion_goal", custom_conversion_goal_server),
    ("customer_conversion_goal", customer_conversion_goal_server),
    ("campaign_conversion_goal", campaign_conversion_goal_server),
    ("goal", goal_server),
    ("campaign_goal_config", campaign_goal_config_server),
    ("offline_user_data_job", offline_user_data_job_server),
    ("remarketing_action", remarketing_action_server),
    # --- organization ---
    ("label", label_server),
    ("campaign_label", campaign_label_server),
    ("campaign_group", campaign_group_server),
    ("ad_group_label", ad_group_label_server),
    ("ad_group_ad_label", ad_group_ad_label_server),
    ("ad_group_criterion_label", ad_group_criterion_label_server),
    ("customer_label", customer_label_server),
    ("shared_set", shared_set_server),
    ("shared_criterion", shared_criterion_server),
    ("campaign_shared_set", campaign_shared_set_server),
    # --- customizers ---
    ("customizer_attribute", customizer_sdk_server),
    ("customer_customizer", customer_customizer_server),
    ("campaign_customizer", campaign_customizer_server),
    ("ad_group_customizer", ad_group_customizer_server),
    ("ag_crit_custom", ad_group_criterion_customizer_server),
    ("ad_parameter", ad_parameter_server),
    # --- account ---
    ("account_registry", account_registry_server),
    ("customer_user_access", customer_user_access_server),
    ("access_invite", customer_user_access_invitation_server),
    ("customer_client_link", customer_client_link_server),
    ("customer_manager_link", customer_manager_link_server),
    ("account_link", account_link_server),
    ("account_budget_proposal", account_budget_proposal_server),
    ("billing_setup", billing_setup_server),
    ("payments_account", payments_account_server),
    ("identity_verification", identity_verification_server),
    ("product_link", product_link_server),
    ("data_link", data_link_server),
    # --- other ---
    ("smart_campaign", smart_campaign_server),
    ("smart_campaign_setting", smart_campaign_setting_server),
    ("batch_job", batch_job_server),
    ("user_data", user_data_server),
]


async def check_sdk_client_status(ctx: Context) -> str:  # noqa: ARG001
    """Check if the Google Ads SDK client is initialized."""
    try:
        if get_sdk_client():
            return "Google Ads SDK client is initialized and ready"
    except Exception:
        pass
    return "Google Ads SDK client is not initialized"


def create_server(
    profile: str,
    *,
    name: str,
    instructions: str,
    lifespan: Optional[Callable[[Any], AsyncContextManager[None]]] = None,
    auth: Optional[AuthProvider] = None,
) -> FastMCP[Any]:
    """A server exposing exactly the tools of `profile` (see tool_profiles.yaml)."""
    tools = get_profile(profile)
    mcp: FastMCP[Any] = FastMCP(
        name=name, instructions=instructions, lifespan=lifespan, auth=auth
    )
    for prefix, server in MOUNTED_SERVERS:
        mcp.mount(server, prefix=prefix)

    mcp.tool(check_sdk_client_status)

    mcp.add_middleware(ErrorMappingMiddleware())
    mcp.add_middleware(ToolProfileMiddleware(profile, tools))
    return mcp
