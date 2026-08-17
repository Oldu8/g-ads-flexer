# Google Ads MCP Service Implementation Tracker

## ✅ 2026-08-17 — `partial_failure_error` now decoded instead of `str()`-dumped

Prompted by comparing our approach against the OSS `promobase/ad-platform-sdks`
(Mosaic) TS SDK, which also targets Google Ads v25 — worth skimming
`packages/google-ads-sdk` there for API-shape ideas, but not a codebase to
port from (different language/stack: TS + REST-codegen vs our Python SDK
wrapper). Its `GoogleAdsError` decoding of nested failure details is the one
idea that exposed a real gap here.

**What was wrong:** when a mutate call uses `partial_failure=True`, Google
Ads doesn't raise `GoogleAdsException` — it returns per-operation errors
inline on `response.partial_failure_error`, a raw `google.rpc.Status` whose
`details` are `Any`-packed `GoogleAdsFailure` messages. 9 files were just
doing `str(response.partial_failure_error)`, which dumps an unreadable raw
protobuf blob instead of the human-readable messages `format_ads_error`
already extracts for full-request failures.

**Fix:** added `format_partial_failure_error()` to `src/utils.py` — unpacks
each `Any` detail via `GoogleAdsFailure.deserialize()` and returns a list of
`{operation_index, error_code, message}` dicts (or `None` if no failure),
mirroring `format_ads_error`'s job for the partial-failure path. Swapped the
`str(...)` call for it in all 9 files: `ad_group_customizer_service.py`,
`user_data_service.py`, `offline_user_data_job_service.py`,
`customer_asset_service.py`, `asset_group_signal_service.py`,
`campaign_asset_set_service.py`, `customer_customizer_service.py`,
`google_ads_service.py` (had its own hand-rolled `serialize_proto_message`
version), and `conversion_upload_service.py` (previously returned
`serialize_proto_message(response)` wholesale, relying on `MessageToDict`'s
undocumented/fragile ability to auto-resolve the `Any` — now explicit).
Rewrote `tests/test_user_data_service.py::test_partial_failure_error` to
build a real `Status`+`Any`-packed `GoogleAdsFailure` instead of asserting on
a stringified `Mock`; added `mock_response.partial_failure_error = None` to
5 mocks in `tests/test_conversion_upload_service.py` that didn't previously
need to touch that attribute. `ruff format`/`pyright`/`pytest` all clean
(588 passed / 4 skipped) after the change.

**Not yet done — worth a follow-up pass:** the same raw
`str(partial_failure_error)`/no-op pattern may exist in mutate-heavy files
not caught by the `partial_failure_error` string grep (e.g. any service
using a differently-named local variable). Worth a second grep pass for
`partial_failure=True` call sites generally, cross-checked against how each
one surfaces its result, rather than trusting the literal string match used
this round.

## ⚠️ 2026-08-13 — Live-verified bug in `search_service.py`, same pattern still latent elsewhere

While building a read-only remote MCP deployment (`remote_main.py`, deployed
on Railway, see the `gads-mcp-remote-readonly-deploy` memory) and running it
against the real boo.ua account, two v20→v25 gaps in
`src/services/metadata/search_service.py` surfaced — exactly the kind of
runtime-only breakage the 2026-08-11 migration note below warned was
unverified (unit tests mock the client, so pyright/pytest didn't catch
these):

1. `execute_query` unconditionally set `request.page_size`. v25's
   `GoogleAdsService.Search` now rejects any client-set page_size at all
   ("Setting the page size is not supported... fixed page size of 10000
   rows") — every call failed. **Fixed**: dropped the `page_size`
   param/assignment entirely.
2. `search_campaigns`'s GAQL selected `campaign.start_date`/`campaign.end_date`;
   v25 renamed these to `campaign.start_date_time`/`campaign.end_date_time`
   (the same rename `campaign_service.py` already handled during the v25
   migration, but missed here). **Fixed**.

**Not yet fixed** — same `request.page_size = ...` pattern, unverified
against the live API, next agent should check both:
- `src/services/planning/keyword_plan_idea_service.py`
- `src/services/data_import/batch_job_service.py`

Takeaway: don't trust "tests pass" as proof a service works against v25 —
these two bugs shipped through a full `pytest`/`pyright` pass. Worth a
systematic live-account smoke test per service before trusting existing
✅ marks below.

## ⚠️ 2026-08-11 — Migrated from v20 to v25 (v20 is sunset)

Google Ads API v20 was sunset on 2026-06-10 (v21 followed on 2026-08-05); live
calls against v20 now fail with `UNSUPPORTED_VERSION`. This was discovered
while validating real credentials against the boo.ua account during
environment setup, not during a planned migration.

**What was done in this pass (mechanical migration, not a full re-audit):**
- Bumped `google-ads` dependency from `29.2.0` to `31.2.0` (bundles v21-v25).
- Bulk-replaced `google.ads.googleads.v20.*` import paths and
  `get_service(..., version="v20")` calls with `v25` across `src/` and
  `tests/` (157 files, ~592 occurrences) — purely mechanical, same symbol
  names in the same modules for the overwhelming majority of cases.
- Fixed the handful of places where v25 actually changed shapes, found via
  `pyright` + `pytest`:
  - `src/services/audiences/audience_insights_service.py`: `BasicInsightsAudience`
    was removed/merged into `InsightsAudience`; `InsightsAudienceAttributeGroup`
    moved from `services.types.audience_insights_service` to
    `common.types.audience_insights_attribute`; `country_location` (singular)
    renamed to `country_locations`; there is no more standalone
    `user_interests` field — interests must be wrapped in an
    `AudienceInsightsAttribute` inside a `topic_audience_combinations` group.
  - `src/services/campaign/campaign_service.py`: `Campaign.start_date` /
    `end_date` (format `yyyyMMdd`) were replaced by `start_date_time` /
    `end_date_time` (format `"yyyy-MM-dd HH:mm:ss"`, e.g.
    `"2024-03-01 00:00:00"`). Tool-facing params are still plain `YYYY-MM-DD`;
    conversion happens inside the service.
- Re-ran `ruff format`, `pyright` (0 errors), `pytest` (588 passed / 4 skipped,
  pre-existing skips unrelated to this migration).
- Verified end-to-end against the real boo.ua account: SDK client init +
  `list_accessible_customers` succeeds on v25.

**What was NOT done (next agent's job, don't assume it's covered):**
- No re-audit of the *service list itself* against v25. Some entries below
  marked "Not available in v20 SDK" may now exist in v25 (services get added
  between majors) — every such note needs re-checking against
  `google-ads-python`'s `v25/services` directory, not assumed still true.
- No review of other behavioral/shape changes between v20 and v25 beyond the
  two fixes above — those were only the ones that happened to break tests or
  pyright. Other services may silently use stale field names that still
  happen to type-check (proto-plus messages are loosely typed) but are wrong
  at runtime. Worth a systematic diff of v20 vs v25 protos per service before
  trusting existing "✅ Implemented" marks blindly.
- `CLAUDE.md` CURRENT TASK section updated to say v25; if you're an agent
  picking up work here, that file is the source of truth going forward, not
  the "v20" mentions still scattered in code comments/docstrings (those are
  historical notes, harmless but not yet cleaned up).

---

## Overview
This document tracks the implementation progress of all Google Ads API v25 services in the MCP server.
Goal: 1:1 mapping of ALL Google Ads services with full type safety using generated protobuf types.

## Progress Summary
- Total Services: 103 (audited against google-ads-python v20; **not yet re-audited against v25's actual service list**, see migration note above)
- ✅ Implemented: 90 (87.4%)
- ❌ Not Implemented: 13 (12.6%)

**Last Audit Date:** 2026-03-22 (service *list* audit — still v20-based, needs re-verification against v25)
**Last Migration Date:** 2026-08-11 (mechanical v20→v25 type/import migration, see note above)
**Audit Method:** Complete analysis of google-ads-python v20 services directory and cross-referenced with implementations
**Latest Implementation:** Campaign service refactored for PMax/Search/Display/Shopping/Video with full bidding strategy support. Extension assets (sitelink, callout, structured snippet, call) added to asset service. MaximizeConversionValue bidding strategy added.

## Type Safety Verification
✅ **ALL implemented services use full v25 type safety:**
- Proper imports from `google.ads.googleads.v25.services.types.*`
- Enum types from `google.ads.googleads.v25.enums.types.*`
- Resource types from `google.ads.googleads.v25.resources.types.*`
- Type annotations on all methods and parameters

## Implementation Status by Service

### Account Management (11 services)
1. ✅ `account_budget_proposal` - Manage account budget proposals
2. ✅ `account_link` - Manage account links between accounts
3. ✅ `billing_setup` - Manage billing setup for accounts
4. ✅ `customer` - Customer account management
5. ✅ `customer_client_link` - Links between manager and client accounts
6. ✅ `customer_manager_link` - Manager account relationships
7. ✅ `customer_user_access` - User access management
8. ✅ `customer_user_access_invitation` - User access invitations (NEWLY IMPLEMENTED)
9. ✅ `invoice` - Access billing invoices
10. ✅ `payments_account` - Payments account management (NEWLY IMPLEMENTED)
11. ✅ `identity_verification` - Identity verification for accounts (NEWLY IMPLEMENTED)

### Ad Groups & Ads (15 services)
1. ✅ `ad` - Ad management
2. ✅ `ad_group` - Ad group management
3. ✅ `ad_group_ad` - Ads within ad groups
4. ✅ `ad_group_ad_label` - Labels for ad group ads (NEWLY IMPLEMENTED)
5. ✅ `ad_group_asset` - Assets for ad groups
6. ✅ `ad_group_asset_set` - Asset sets for ad groups (NEWLY IMPLEMENTED)
7. ✅ `ad_group_bid_modifier` - Bid modifiers for ad groups
8. ✅ `ad_group_criterion` - Ad group targeting criteria
9. ✅ `ad_group_criterion_customizer` - Criterion customizers (NEWLY IMPLEMENTED)
10. ✅ `ad_group_criterion_label` - Labels for criteria (NEWLY IMPLEMENTED)
11. ✅ `ad_group_customizer` - Ad group customizers (NEWLY IMPLEMENTED)
12. ✅ `ad_group_label` - Ad group labels
13. ✅ `ad_parameter` - Ad customizer parameters (NEWLY IMPLEMENTED)
14. ✅ `keyword` (part of ad_group_criterion) - Keyword management
15. ✅ `keyword_sdk_server` (registered separately) - Additional keyword operations

### Assets (10 services)
1. ✅ `asset` - Asset management
2. ✅ `asset_group` - Asset group management (Performance Max)
3. ✅ `asset_group_asset` - Assets within asset groups
4. ❌ `asset_group_listing_group_filter` - Not available in v20 SDK
5. ✅ `asset_group_signal` - Audience signals for asset groups (NEWLY IMPLEMENTED)
6. ✅ `asset_set` - Asset set management
7. ❌ `asset_set_asset` - Assets within asset sets
8. ✅ `customer_asset` - Customer-level assets (NEWLY IMPLEMENTED)
9. ❌ `customer_asset_set` - Customer asset sets
10. ❌ `travel_asset_suggestion` - Travel-specific asset suggestions

### Audiences & Targeting (10 services)
1. ✅ `audience` - Audience management
2. ✅ `audience_insights` - Audience insights and analysis
3. ✅ `custom_audience` - Custom audiences
4. ✅ `custom_interest` - Custom interests
5. ✅ `customer_negative_criterion` - Account-level negative criteria
6. ✅ `geo_target_constant` - Geographic targeting constants
7. ✅ `remarketing_action` - Remarketing actions/tags
8. ✅ `user_list` - User lists for remarketing
9. ❌ `user_list_customer_type` - Customer types for user lists
10. ❌ `keyword_theme_constant` - Keyword theme constants

### Bidding & Budgets (5 services)
1. ✅ `bidding_data_exclusion` - Exclude data ranges from smart bidding
2. ✅ `bidding_seasonality_adjustment` - Seasonal bid adjustments (NEWLY IMPLEMENTED)
3. ✅ `bidding_strategy` - Bidding strategies
4. ✅ `budget` (campaign_budget in our impl) - Campaign budget management
5. ❌ `campaign_budget` - Separate campaign budget service (v20 has both)

### Campaigns (17 services)
1. ✅ `campaign` - Campaign management
2. ✅ `campaign_asset` - Campaign-level assets
3. ✅ `campaign_asset_set` - Campaign asset sets (NEWLY IMPLEMENTED)
4. ✅ `campaign_bid_modifier` - Campaign bid modifiers
5. ✅ `campaign_conversion_goal` - Campaign-specific conversion goals
6. ✅ `campaign_criterion` - Campaign targeting criteria
7. ✅ `campaign_customizer` - Campaign customizers (NEWLY IMPLEMENTED)
8. ✅ `campaign_draft` - Campaign drafts for testing
9. ❌ `campaign_group` - Campaign groups (Performance Max)
10. ✅ `campaign_label` - Campaign labels
11. ❌ `campaign_lifecycle_goal` - Campaign lifecycle goals
12. ✅ `campaign_shared_set` - Shared sets for campaigns
13. ✅ `experiment` - Campaign experiments
14. ✅ `experiment_arm` - Experiment arms/variants (NEWLY IMPLEMENTED)
15. ✅ `smart_campaign_suggest` - Smart campaign suggestions
16. ❌ `smart_campaign_setting` - Smart campaign settings
17. ❌ `shareable_preview` - Shareable ad previews

### Conversions (11 services)
1. ✅ `conversion` (conversion_action in API) - Conversion actions
2. ✅ `conversion_adjustment_upload` - Upload conversion adjustments
3. ✅ `conversion_custom_variable` - Custom variables for conversions
4. ✅ `conversion_goal_campaign_config` - Campaign conversion goal configs (NEWLY IMPLEMENTED)
5. ✅ `conversion_upload` - Upload conversions
6. ✅ `conversion_value_rule` - Value rules for conversions
7. ❌ `conversion_value_rule_set` - Value rule sets
8. ✅ `custom_conversion_goal` - Custom conversion goals (NEWLY IMPLEMENTED)
9. ✅ `customer_conversion_goal` - Customer-level conversion goals (NEWLY IMPLEMENTED)
10. ❌ `customer_sk_ad_network_conversion_value_schema` - SK Ad Network schema
11. ❌ `customer_lifecycle_goal` - Customer lifecycle goals

### Data Import & Jobs (5 services)
1. ✅ `batch_job` - Batch job operations (NEWLY REGISTERED)
2. ❌ `data_link` - Data link management
3. ✅ `offline_user_data_job` - Offline user data uploads
4. ✅ `user_data` - User data operations
5. ❌ `local_services_lead` - Local services lead data

### Labels & Organization (4 services)
1. ✅ `label` - Label management
2. ✅ `campaign_label_server` - Campaign label operations
3. ✅ `customer_label` - Customer-level labels (NEWLY IMPLEMENTED)
4. ✅ `customer_customizer` - Customer-level customizers (NEWLY IMPLEMENTED)

### Metadata & Search (3 services)
1. ✅ `google_ads` - Core search/mutate service
2. ✅ `google_ads_field` - Field metadata
3. ✅ `search` (custom implementation) - Enhanced search operations

### Planning & Insights (9 services)
1. ✅ `keyword_plan` - Keyword planning
2. ✅ `keyword_plan_ad_group` - Keyword plan ad groups (NEWLY IMPLEMENTED)
3. ✅ `keyword_plan_ad_group_keyword` - Keywords in plan ad groups (NEWLY IMPLEMENTED)
4. ✅ `keyword_plan_campaign` - Keyword plan campaigns (NEWLY IMPLEMENTED)
5. ✅ `keyword_plan_campaign_keyword` - Keywords in plan campaigns (NEWLY IMPLEMENTED)
6. ✅ `keyword_plan_idea` - Keyword ideas and research
7. ✅ `reach_plan` - Reach planning
8. ✅ `recommendation` - Optimization recommendations
9. ❌ `recommendation_subscription` - Recommendation subscriptions

### Product Integration (5 services)
1. ✅ `brand_suggestion` - Brand suggestions (NEWLY IMPLEMENTED)
2. ❌ `content_creator_insights` - YouTube creator insights
3. ✅ `product_link` - Product link management (NEWLY IMPLEMENTED)
4. ❌ `product_link_invitation` - Product link invitations
5. ❌ `third_party_app_analytics_link` - Third-party analytics links

### Shared Resources (4 services)
1. ✅ `shared_criterion` - Shared criteria
2. ✅ `shared_set` - Shared sets
3. ❌ `customizer_attribute` - Customizer attributes
4. ✅ `customizer_attribute` (we have this implemented)

## API Coverage Analysis

### Fully Implemented Services (1:1 API Coverage)
Services that implement ALL operations from the Google Ads API:

1. ✅ `google_ads_service` - search, search_stream, mutate, mutate_operation
2. ✅ `customer_service` - list_accessible_customers, create_customer_client, mutate_customer  
3. ✅ `campaign_service` - create/update campaigns with full bidding & channel type support (Search, Display, Shopping, Video, PMax)
4. ✅ `ad_group_service` - mutate_ad_groups (create, update, remove)
5. ✅ `budget_service` - mutate_campaign_budgets (create, update, remove)
6. ✅ `ad_service` - mutate_ads, get_ad
7. ✅ `bidding_strategy_service` - Target CPA, Target ROAS, MaxConversions, MaxConversionValue, Target Impression Share
8. ✅ `conversion_action_service` - mutate_conversion_actions (create, update, remove)
9. ✅ `asset_service` - text, image, youtube video, sitelink, callout, structured snippet, call assets
10. ✅ `user_list_service` - mutate_user_lists (create, update, remove)

### Partially Implemented Services
Services missing some operations:

1. ⚠️ `keyword_plan_service` - Missing: generate_forecast_curve, generate_forecast_time_series, generate_forecast_metrics
2. ⚠️ `reach_plan_service` - Missing: generate_reach_forecast
3. ⚠️ `recommendation_service` - Missing: dismiss_recommendation

### Recent Enhancements (2026-03-22)

**Campaign Service (MAJOR):**
- `create_campaign` now supports ALL channel types: SEARCH, DISPLAY, SHOPPING, VIDEO, PERFORMANCE_MAX
- Supports all bidding strategies: MANUAL_CPC, TARGET_CPA, TARGET_ROAS, MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE, TARGET_SPEND, TARGET_IMPRESSION_SHARE, PORTFOLIO
- `advertising_channel_sub_type` parameter added
- Network settings are conditional (skipped for PMax)
- `update_campaign` now supports changing bidding strategies

**Asset Service (NEW extension types):**
- `create_sitelink_asset` - Sitelink extensions with link text, descriptions, and final URLs
- `create_callout_asset` - Callout extensions
- `create_structured_snippet_asset` - Structured snippet extensions with headers and values
- `create_call_asset` - Call extensions with country code and phone number

**Bidding Strategy Service (NEW):**
- `create_maximize_conversion_value_strategy` - MaximizeConversionValue with optional target ROAS

## Next Steps

### High Priority Implementations
1. ✅ `campaign_customizer` - Dynamic ad customization (COMPLETED)
2. ✅ `customer_label` - Account organization (COMPLETED)
3. ✅ `bidding_seasonality_adjustment` - Seasonal bidding (COMPLETED)
4. ✅ `customer_user_access_invitation` - User access invitations (COMPLETED)
5. ✅ `payments_account` - Payments account management (COMPLETED)
6. ✅ `batch_job` - Bulk operations (COMPLETED)
7. `product_link` - Merchant Center integration
8. `identity_verification` - Identity verification for accounts

### Medium Priority
1. Asset-related services for Performance Max
2. Remaining label services
3. Customizer services
4. Experiment arms

### Low Priority
1. Specialized services (local services, SK ad network)
2. Beta features
3. Less commonly used operations

## Implementation Guidelines

1. **Type Safety**: ALL implementations MUST use v20 protobuf types
2. **Testing**: Each service MUST have comprehensive tests
3. **Structure**: Follow pattern in `src/sdk_services/<category>/<service>_service.py`
4. **MCP Tools**: Create lightweight wrappers converting strings to enums
5. **Documentation**: Include examples and operation descriptions
6. **Error Handling**: Proper GoogleAdsException handling

## Notes for Contributors

When implementing a new service:
1. Check the v20 service types in google-ads-python
2. Implement ALL operations for 1:1 API coverage
3. Use full type annotations with v20 types
4. Write comprehensive tests
5. Update this tracker immediately
6. Run `uv run ruff format .` and `uv run pyright`