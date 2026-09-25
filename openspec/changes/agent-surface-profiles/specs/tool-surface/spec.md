## Purpose

Decide, per process (and later per tenant), which tools exist for the agent, and make that decision declarative, validated at startup, enforced on both listing and calling, and guarded by tests that fail when the surface drifts or grows.

## ADDED Requirements

### Requirement: Every tool has an explicit classification
Each registered tool SHALL have an entry in `src/tool_registry.py` with `kind` ∈ {`read`, `ads_write`, `internal_write`, `local_only`} and a boolean `destructive`. Classification SHALL NOT be inferred from tool names at runtime. `ads_write` means the tool can send a mutate RPC to Google Ads; `internal_write` means it writes only to our own stores (fixes-log Sheet, pending-change queue); `local_only` means it only makes sense for a local single-operator process (`account_registry_*`, `check_sdk_client_status`).

#### Scenario: A tool is added without a registry entry
- **WHEN** a new tool is registered and has no entry in the registry
- **THEN** `tests/test_tool_surface.py` fails and names the unclassified tool

#### Scenario: Names that mislead a heuristic
- **WHEN** the registry is reviewed
- **THEN** `search_execute_query` is `read`, and `user_list_create_rule_based_user_list`, `user_list_update_user_list`, `user_list_remove_user_list` and `ad_create_responsive_search_ad` are `ads_write` (a verb-based heuristic misclassified all five during analysis; the registry is the fix)

### Requirement: Annotations derive from the registry
Tool annotations SHALL be produced from the registry: `readOnlyHint = true` exactly when `kind = read`, `destructiveHint = true` exactly when `destructive = true`. No other annotation fields (`title`, `idempotentHint`, `openWorldHint`) SHALL be emitted. Annotations SHALL be attached in the profile middleware's `on_list_tools`, so no server module changes.

#### Scenario: Listing a read tool
- **WHEN** a client lists tools under any profile
- **THEN** `search_execute_query` carries `readOnlyHint: true` and `ad_group_criterion_remove_ad_group_criterion` carries `destructiveHint: true`

### Requirement: Profiles are named, explicit, validated sets
`tool_profiles.yaml` SHALL define named profiles as explicit lists of tool names. Loading SHALL fail (process does not start) if any listed name is not a registered tool. A profile key present with an empty list SHALL expose nothing. The `read_only` profile SHALL NOT be listed by hand: it SHALL be computed as the `manager` tools whose `kind` is `read` or `internal_write`, excluding the pending-change tools. The `all` profile SHALL expose every registered tool and is for local development only.

#### Scenario: Typo in a profile
- **WHEN** `tool_profiles.yaml` lists `campaign_update_campaing`
- **THEN** startup fails with an error naming `campaign_update_campaing` and the profile it appears in

#### Scenario: Deriving read_only
- **WHEN** the profiles are loaded
- **THEN** `read_only` contains `fixes_log_log_fix` (an `internal_write`) and `search_execute_query`, and contains no `ads_write` tool and no `pending_change_*` tool

### Requirement: Filtering applies to listing and calling
The active profile SHALL be enforced by middleware in both `on_list_tools` and `on_call_tool`. A tool outside the active profile SHALL NOT appear in `tools/list`, and a call to it by name SHALL return an error stating that the tool is not available in this profile, without executing the tool.

#### Scenario: Calling a hidden tool by name
- **WHEN** the active profile is `read_only` and a client calls `campaign_update_campaign`
- **THEN** the call returns "tool not available in profile read_only" and no service code runs

### Requirement: Local profile selection
`main.py` SHALL accept `--profile <name>` (default `manager`) and SHALL no longer accept `--groups`. The repository's `.mcp.json` SHALL launch `--profile manager`.

#### Scenario: Default local launch
- **WHEN** the operator starts `main.py` without flags
- **THEN** exactly the `manager` tools are listed

### Requirement: The initial manager profile
The `manager` profile SHALL contain exactly the tools below (77) until changed deliberately; each change SHALL update the golden snapshot in the same commit. Where two tools duplicate each other, the listed one wins, and the loser stays reachable only through `all`: `search_execute_query` over `google_ads_search_google_ads` / `google_ads_search_google_ads_stream`; `ad_group_criterion_*` over `keyword_add_keywords` / `keyword_update_keyword_bid` / `keyword_remove_keyword` (the pending-change apply path already calls `AdGroupCriterionService.add_keywords`); `campaign_shared_set_attach_shared_set_to_campaign` over `shared_set_attach_shared_set_to_campaigns` (8 tests vs 4). `ad_create_expanded_text_ad` is excluded because Google stopped accepting new expanded text ads in 2022.

- Reads (18): `search_execute_query`, `search_search_campaigns`, `search_search_ad_groups`, `search_search_keywords`, `google_ads_field_search_fields`, `google_ads_field_get_resource_fields`, `google_ads_field_get_field_metadata`, `google_ads_field_validate_query_fields`, `recommendation_get_recommendations`, `ad_group_ad_list_ad_group_ads`, `ad_resource_get_ad`, `shared_set_list_shared_sets`, `shared_criterion_list_shared_criteria`, `campaign_shared_set_list_campaign_shared_sets`, `customer_negative_criterion_list_negative_criteria`, `fixes_log_list_fixes`, `pending_change_list_pending_changes`, `pending_change_get_pending_change`
- Core writes (24): `campaign_create_campaign`, `campaign_update_campaign`, `budget_create_campaign_budget`, `budget_update_campaign_budget`, `ad_group_create_ad_group`, `ad_group_update_ad_group`, `ad_group_criterion_add_keywords`, `ad_group_criterion_update_criterion_bid`, `ad_group_criterion_remove_ad_group_criterion`, `campaign_criterion_add_negative_keyword_criteria`, `campaign_criterion_remove_campaign_criterion`, `customer_negative_criterion_add_negative_keywords`, `customer_negative_criterion_remove_negative_criterion`, `shared_set_create_shared_set`, `shared_criterion_add_keywords_to_shared_set`, `shared_criterion_remove_shared_criterion`, `campaign_shared_set_attach_shared_set_to_campaign`, `campaign_shared_set_detach_shared_set_from_campaign`, `ad_create_responsive_search_ad`, `ad_group_ad_update_ad_group_ad_status`, `ad_group_ad_remove_ad_group_ad`, `ad_resource_update_ad_urls`, `recommendation_apply_recommendation`, `recommendation_dismiss_recommendation`
- Queue and memory (5): `pending_change_apply_pending_change`, `pending_change_reject_pending_change`, `fixes_log_log_fix`, `fixes_log_update_fix_review`, `fixes_log_update_fix_conclusion`
- Asset extensions (11): `asset_search_assets`, `asset_create_sitelink_asset`, `asset_create_callout_asset`, `asset_create_structured_snippet_asset`, `asset_create_call_asset`, `campaign_asset_list_campaign_assets`, `campaign_asset_link_asset_to_campaign`, `campaign_asset_remove_asset_from_campaign`, `ad_group_asset_list_ad_group_assets`, `ad_group_asset_link_asset_to_ad_group`, `ad_group_asset_remove_asset_from_ad_group`
- Targeting and bid modifiers (10): `geo_target_search_geo_targets`, `campaign_criterion_add_location_criteria`, `campaign_criterion_add_language_criteria`, `campaign_criterion_add_device_criteria`, `campaign_bid_modifier_list_campaign_bid_modifiers`, `campaign_bid_modifier_update_bid_modifier`, `campaign_bid_modifier_remove_bid_modifier`, `ag_bid_mod_list_ad_group_bid_modifiers`, `ag_bid_mod_create_ad_group_device_bid_modifier`, `ag_bid_mod_update_ad_group_bid_modifier`
- Audiences (9): `audience_list_audiences`, `custom_audience_list_custom_audiences`, `custom_audience_create_custom_audience`, `user_list_create_rule_based_user_list`, `user_list_update_user_list`, `user_list_remove_user_list`, `ad_group_criterion_add_audience_criteria`, `audience_insights_generate_audience_composition_insights`, `audience_insights_generate_suggested_targeting_insights`

#### Scenario: Profile contents match the list
- **WHEN** the `manager` profile is loaded
- **THEN** it has 77 tools, 44 of them `ads_write`

### Requirement: The surface is snapshot-tested and budgeted
The repository SHALL contain a golden `tools/list` snapshot per profile (`manager`, `read_only`) produced by `scripts/dump_tools_list.py`, and a test that fails on any diff. A second test SHALL fail when a profile's serialized `tools/list` exceeds its budget: `manager` ≤ 100,000 chars (≈25k tokens), `read_only` ≤ 40,000 chars (≈10k tokens). Both budgets SHALL live in one constant. The same test module SHALL assert tool names are unique and every tool has a non-empty description.

#### Scenario: A docstring change grows a schema
- **WHEN** a change makes the `manager` snapshot differ
- **THEN** the snapshot test fails until the snapshot is regenerated in the same commit, so the diff is reviewed

#### Scenario: Budget exceeded
- **WHEN** the `manager` payload reaches 100,001 chars
- **THEN** the budget test fails and prints the current size and the three largest tools

### Requirement: The read-only remote entrypoint uses the derived profile
`remote_main.py` SHALL expose the `read_only` profile through the same registry and middleware instead of a hand-picked list of servers, until the hosted entrypoint replaces it.

#### Scenario: A write tool is added to a server remote_main used to mount
- **WHEN** someone adds an `ads_write` tool to `search_server`
- **THEN** `remote_main.py` still does not expose it, because `read_only` is computed from the registry
