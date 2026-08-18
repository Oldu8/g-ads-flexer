# Google Ads MCP Service Implementation Tracker

## 🚧 2026-08-17 (3) — CURRENT TASK: prepping the write ("flexer") path for boo.ua budgets/bids

**Decision (user, this session):** the write-capable service is **MCP
write-tools with an LLM in the loop** (not an autonomous scheduled process
that mutates on its own). First scope is **budgets and bids only**
(`campaign_budget`, standalone campaign bidding params) — not campaigns/ad
groups/ads. This is a scoping decision, not yet an implementation — nothing
has shipped from this section yet.

**What prep found:**

1. **Good news — the two levers this needs already exist and are tested:**
   `budget_service.update_campaign_budget` (amount_micros) and
   `campaign_service.update_campaign` (target_cpa_micros / target_roas /
   max_conversion_value_target_roas) already cover budget and bid-target
   changes. No new service needed for the core write operation.
2. **Live-verified (read-only query against boo.ua, customer_id
   `5690318342`, 2026-08-17): all 9 currently-enabled campaigns use
   *standalone* bidding (`MAXIMIZE_CONVERSION_VALUE` or
   `MAXIMIZE_CONVERSIONS`), none use a portfolio `BiddingStrategy` resource.**
   This means `bidding_strategy_service.py`'s missing `update_*` methods
   (it only has `create_*` for 5 strategy types, confirmed via grep — no
   `update_bidding_strategy` at all) **don't block the flexer** — deprioritize
   that gap, it was flagged in "Next Steps" above but isn't on this path.
3. **Real bug found in `campaign_service.py::update_campaign`, blocks the
   flexer as-is:** `target_cpa_micros` / `target_roas` /
   `max_conversion_value_target_roas` are only applied when the caller
   *also* passes `bidding_strategy_type` — they're read and forwarded to
   `_apply_bidding_strategy` only inside the `if bidding_strategy_type is
   not None:` branch (`src/services/campaign/campaign_service.py:293-316`).
   Call `update_campaign(customer_id, campaign_id,
   max_conversion_value_target_roas=8.5)` alone (the exact shape a "just
   nudge the ROAS target" flexer call would take) and it **silently no-ops**
   — no error, the field never enters `update_mask_fields`, nothing changes
   on the server, but the call returns normally. This is a correctness trap
   specifically for the automation use case, not just a style nit.

**Fixed (2026-08-17):** `update_campaign` now raises a clear `ValueError`
(wrapped into the usual `Exception("Failed to update campaign: ...")`) when
`target_cpa_micros`/`target_roas`/`max_conversion_value_target_roas`/
`target_spend_cpc_bid_ceiling_micros` are passed without
`bidding_strategy_type` — converting the silent no-op into a loud, actionable
error instead. Deliberately **not** auto-detecting the campaign's current
strategy type via an extra live read (would add a second API round-trip, a
read/write race window, and still can't disambiguate `target_cpa_micros`
between `TARGET_CPA` and `MAXIMIZE_CONVERSIONS` — both use that same field
name in different oneof branches). The caller (LLM agent) must pass the
campaign's current `bidding_strategy_type` explicitly even when only nudging
a target value, not switching strategy — docstrings on both the service
method and the MCP tool wrapper now say so. Added
`test_update_campaign_nudge_max_conversion_value_roas` (the actual boo.ua
shape: restate `MAXIMIZE_CONVERSION_VALUE` + new `max_conversion_value_target_roas`
→ applies) and `test_update_campaign_bid_value_without_strategy_type_raises`
(regression test for the original bug) to
`tests/test_campaign_service.py`. `ruff format`/`pyright`/`pytest` all clean
(590 passed / 4 skipped, up from 588).

**Next step (not started):** decide whether a write-capable deployment
happens at all (vs. using the existing local stdio `main.py`, which already
mounts full read+write — see `gads-mcp-remote-readonly-deploy` memory for
why the *remote* deploy was deliberately kept read-only) — not yet decided.

## ✅ 2026-08-17 (2) — Full service-list re-audit against actual v25 (the gap flagged in the 2026-08-11 note below is now closed)

The 2026-08-11 migration note said the service *list* itself was never
re-checked against v25 — every ✅/❌ below was still from a v20 audit dated
2026-03-22. Did that re-check now, and **not** by comparing filenames (too
easy to get false matches/misses — e.g. `budget_service.py` vs
`campaign_budget`, `ad_service.py` vs `ad`) but by grepping every one of our
87 `src/services/**/*_service.py` files for the literal
`get_service("XxxService", ...)` string they call, and diffing that set
against the real service list in the installed `google-ads==31.2.0` package
(`.venv/Lib/site-packages/google/ads/googleads/v25/services/services/`,
which is the authoritative v25 surface — 110 real services, not 103).

**Result: 84/110 (76%) actually implemented**, not the stale 90/103 (87%)
this file previously claimed. Full corrected breakdown is in the
"Implementation Status by Service" section below. Highlights:

- **Real bug found, not just a stale count**: `src/services/ad_group/ad_service.py`
  is named/tracked as if it wraps `AdService`, but its `get_service(...)` call
  is actually `"AdGroupAdService"` — same service `ad_group_ad_service.py`
  already wraps. The real `AdService` (v25's standalone `mutate_ads` on Ad
  resources — no create/remove, update-only by design) has **no wrapper at
  all**. The old tracker's "Fully Implemented Services" list even asserted
  "✅ `ad_service` - mutate_ads, get_ad" — that claim was checked against
  nothing and is false; `ad_service.py` has no `mutate_ads`/`get_ad` methods.
- Confirmed **not** gaps (old tracker had these wrong/duplicated):
  - `budget` vs `campaign_budget` — old tracker listed these as two separate
    services ("v20 has both"). There is only one: `CampaignBudgetService`,
    wrapped by `budget_service.py`. Not a gap.
  - `customizer_attribute` was listed both ✅ and ❌ in the old category
    table (copy-paste error) — it's ✅, one file, confirmed via `get_service`.
  - `smart_campaign` — old tracker's ✅ entry correctly maps to
    `SmartCampaignSuggestService`; `smart_campaign_setting` is a genuinely
    different, separate, still-unimplemented service.
- **Old tracker ❌ entries that no longer exist in v25 at all** (not
  "not implemented" — just gone, don't carry these forward):
  `campaign_lifecycle_goal`, `customer_lifecycle_goal`. v25 replaced them
  with `campaign_goal_config_service` and `goal_service` (both still ❌, see
  below — different service, not the same gap).
- **New in v25, not on the old v20-era list at all** (so nobody ever
  evaluated them): `asset_generation`, `automatically_created_asset_removal`,
  `benchmarks`, `campaign_goal_config`, `goal`, `incentive`,
  `multi_party_auth_review`, `reservation`, `you_tube_video_upload`. All ❌
  (unevaluated — not yet looked at for whether/how they map to an MCP tool).

**Not done in this pass** (re-audit was scope-limited to "does a wrapper
file exist and call the right API service" — not "is the wrapper's coverage
of that service's fields/operations complete", and not a live-account check):
- No re-verification of whether each ✅ service covers **all** operations
  the real service exposes (e.g. `keyword_plan_service`, `reach_plan_service`,
  `recommendation_service` were already flagged as partial in "API Coverage
  Analysis" below — that section wasn't re-audited this pass, may have more
  gaps of this kind).
- No live-account smoke test of the 26 newly/previously-flagged ❌ services
  (they're unimplemented, so nothing to smoke-test yet) or of the ✅ ones
  beyond what 2026-08-13's spot-check already covered.

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
- Total Services: 110 (audited against the real `google-ads==31.2.0` v25 service list, `.venv/Lib/site-packages/google/ads/googleads/v25/services/services/` — see 2026-08-17 re-audit note above)
- ✅ Implemented: 84 (76.4%)
- ❌ Not Implemented: 26 (23.6%)

**Last Audit Date:** 2026-08-17 (service *list* re-audited by grepping each wrapper's actual `get_service("XxxService")` call, not by filename)
**Last Migration Date:** 2026-08-11 (mechanical v20→v25 type/import migration, see note above)
**Audit Method:** Diffed the set of `XxxService` names our 87 `src/services/**/*_service.py` files actually call against the installed v25 package's real service directory.
**Latest Implementation:** Campaign service refactored for PMax/Search/Display/Shopping/Video with full bidding strategy support. Extension assets (sitelink, callout, structured snippet, call) added to asset service. MaximizeConversionValue bidding strategy added.

## Type Safety Verification
✅ **ALL implemented services use full v25 type safety:**
- Proper imports from `google.ads.googleads.v25.services.types.*`
- Enum types from `google.ads.googleads.v25.enums.types.*`
- Resource types from `google.ads.googleads.v25.resources.types.*`
- Type annotations on all methods and parameters

## Implementation Status by Service

Status below reflects the actual `get_service("XxxService")` call each
`src/services/**/*_service.py` file makes, diffed against the real v25
service list (110 services) — not filenames, not the old v20 list. See the
2026-08-17 re-audit note at the top of this file for method.

### Account Management (11 services) — 11 ✅ / 0 ❌
1. ✅ `account_budget_proposal` - Manage account budget proposals
2. ✅ `account_link` - Manage account links between accounts
3. ✅ `billing_setup` - Manage billing setup for accounts
4. ✅ `customer` - Customer account management
5. ✅ `customer_client_link` - Links between manager and client accounts
6. ✅ `customer_manager_link` - Manager account relationships
7. ✅ `customer_user_access` - User access management
8. ✅ `customer_user_access_invitation` - User access invitations
9. ✅ `invoice` - Access billing invoices
10. ✅ `payments_account` - Payments account management
11. ✅ `identity_verification` - Identity verification for accounts

### Ad Groups & Ads (13 services) — 12 ✅ / 1 ❌
1. ❌ `ad` - Standalone Ad resource `mutate_ads`/get. **`src/services/ad_group/ad_service.py`
   exists but is mislabeled** — it actually calls `AdGroupAdService` (same
   service `ad_group_ad_service.py` wraps), not `AdService`. Real gap.
2. ✅ `ad_group` - Ad group management
3. ✅ `ad_group_ad` - Ads within ad groups (this is what `ad_service.py` also
   happens to wrap — duplicate coverage of `ad_group_ad`, not of `ad`)
4. ✅ `ad_group_ad_label` - Labels for ad group ads
5. ✅ `ad_group_asset` - Assets for ad groups
6. ✅ `ad_group_asset_set` - Asset sets for ad groups
7. ✅ `ad_group_bid_modifier` - Bid modifiers for ad groups
8. ✅ `ad_group_criterion` - Ad group targeting criteria (also has a
   `keyword_service.py` convenience wrapper over the same API service —
   fine, not a second gap)
9. ✅ `ad_group_criterion_customizer` - Criterion customizers
10. ✅ `ad_group_criterion_label` - Labels for criteria
11. ✅ `ad_group_customizer` - Ad group customizers
12. ✅ `ad_group_label` - Ad group labels
13. ✅ `ad_parameter` - Ad customizer parameters

### Assets (13 services) — 6 ✅ / 7 ❌
1. ✅ `asset` - Asset management
2. ❌ `asset_generation` - AI asset generation (new in v25, unevaluated)
3. ✅ `asset_group` - Asset group management (Performance Max)
4. ✅ `asset_group_asset` - Assets within asset groups
5. ❌ `asset_group_listing_group_filter` - PMax listing group filters
6. ✅ `asset_group_signal` - Audience signals for asset groups
7. ✅ `asset_set` - Asset set management
8. ❌ `asset_set_asset` - Assets within asset sets
9. ❌ `automatically_created_asset_removal` - Opt out of auto-created assets (new in v25, unevaluated)
10. ✅ `customer_asset` - Customer-level assets
11. ❌ `customer_asset_set` - Customer asset sets
12. ❌ `travel_asset_suggestion` - Travel-specific asset suggestions
13. ❌ `you_tube_video_upload` - YouTube video upload for assets (new in v25, unevaluated)

### Audiences & Targeting (10 services) — 8 ✅ / 2 ❌
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

### Bidding & Budgets (4 services) — 4 ✅ / 0 ❌
There is only **one** budget service in v25 (`CampaignBudgetService`); the
old tracker's "separate `budget` vs `campaign_budget`, v20 has both" entry
was wrong — confirmed via `get_service` call in `budget_service.py`.
1. ✅ `bidding_data_exclusion` - Exclude data ranges from smart bidding
2. ✅ `bidding_seasonality_adjustment` - Seasonal bid adjustments
3. ✅ `bidding_strategy` - Bidding strategies
4. ✅ `campaign_budget` (our `budget_service.py`) - Campaign budget management

### Campaigns (17 services) — 13 ✅ / 4 ❌
1. ✅ `campaign` - Campaign management
2. ✅ `campaign_asset` - Campaign-level assets
3. ✅ `campaign_asset_set` - Campaign asset sets
4. ✅ `campaign_bid_modifier` - Campaign bid modifiers
5. ✅ `campaign_conversion_goal` - Campaign-specific conversion goals
6. ✅ `campaign_criterion` - Campaign targeting criteria
7. ✅ `campaign_customizer` - Campaign customizers
8. ✅ `campaign_draft` - Campaign drafts for testing
9. ❌ `campaign_goal_config` - Campaign lifecycle-goal config (new in v25;
   replaces the old, now-removed `campaign_lifecycle_goal` — don't confuse
   with the two below)
10. ❌ `campaign_group` - Campaign groups (Performance Max)
11. ✅ `campaign_label` - Campaign labels
12. ✅ `campaign_shared_set` - Shared sets for campaigns
13. ✅ `experiment` - Campaign experiments
14. ✅ `experiment_arm` - Experiment arms/variants
15. ✅ `smart_campaign_suggest` - Smart campaign suggestions
16. ❌ `smart_campaign_setting` - Smart campaign settings (distinct from
    `smart_campaign_suggest`, which IS implemented)
17. ❌ `shareable_preview` - Shareable ad previews

### Conversions (11 services) — 8 ✅ / 3 ❌
1. ✅ `conversion_action` (our `conversion_service.py`) - Conversion actions
2. ✅ `conversion_adjustment_upload` - Upload conversion adjustments
3. ✅ `conversion_custom_variable` - Custom variables for conversions
4. ✅ `conversion_goal_campaign_config` - Campaign conversion goal configs
5. ✅ `conversion_upload` - Upload conversions
6. ✅ `conversion_value_rule` - Value rules for conversions
7. ❌ `conversion_value_rule_set` - Value rule sets
8. ✅ `custom_conversion_goal` - Custom conversion goals
9. ✅ `customer_conversion_goal` - Customer-level conversion goals
10. ❌ `customer_sk_ad_network_conversion_value_schema` - SK Ad Network schema
11. ❌ `goal` - Customer lifecycle-goal (new in v25; replaces the old,
    now-removed `customer_lifecycle_goal`)

### Data Import & Jobs (5 services) — 4 ✅ / 1 ❌
1. ✅ `batch_job` - Batch job operations
2. ❌ `data_link` - Data link management
3. ✅ `offline_user_data_job` - Offline user data uploads
4. ✅ `user_data` - User data operations
5. ❌ `local_services_lead` - Local services lead data

### Labels & Organization (3 services) — 3 ✅ / 0 ❌
(`ad_group_label` and `campaign_label` live under their own categories
above — they're separate services, not counted twice here.)
1. ✅ `label` - Generic label management
2. ✅ `customer_label` - Customer-level labels
3. ✅ `customer_customizer` - Customer-level customizers

### Metadata & Search (2 services) — 2 ✅ / 0 ❌
`search_service.py` is a convenience wrapper over `GoogleAdsService`, not a
separate v25 API service — not counted as a distinct entry.
1. ✅ `google_ads` - Core search/mutate service
2. ✅ `google_ads_field` - Field metadata

### Planning & Insights (9 services) — 8 ✅ / 1 ❌
1. ✅ `keyword_plan` - Keyword planning
2. ✅ `keyword_plan_ad_group` - Keyword plan ad groups
3. ✅ `keyword_plan_ad_group_keyword` - Keywords in plan ad groups
4. ✅ `keyword_plan_campaign` - Keyword plan campaigns
5. ✅ `keyword_plan_campaign_keyword` - Keywords in plan campaigns
6. ✅ `keyword_plan_idea` - Keyword ideas and research
7. ✅ `reach_plan` - Reach planning
8. ✅ `recommendation` - Optimization recommendations
9. ❌ `recommendation_subscription` - Recommendation subscriptions

### Product Integration & Business Data (9 services) — 2 ✅ / 7 ❌
v25 added several business-data services (`benchmarks`, `incentive`,
`multi_party_auth_review`, `reservation`) that didn't exist under the old
v20-era list at all — nobody has evaluated these yet.
1. ✅ `brand_suggestion` - Brand suggestions
2. ❌ `benchmarks` - Industry benchmark data (new in v25, unevaluated)
3. ❌ `content_creator_insights` - YouTube creator insights
4. ❌ `incentive` - Account incentives/promotions (new in v25, unevaluated)
5. ❌ `multi_party_auth_review` - Multi-party authorization review (new in v25, unevaluated)
6. ✅ `product_link` - Product link management
7. ❌ `product_link_invitation` - Product link invitations
8. ❌ `reservation` - Ad reservations (new in v25, unevaluated)
9. ❌ `third_party_app_analytics_link` - Third-party analytics links

### Shared Resources (3 services) — 3 ✅ / 0 ❌
1. ✅ `shared_criterion` - Shared criteria
2. ✅ `shared_set` - Shared sets
3. ✅ `customizer_attribute` - Customizer attributes (old tracker listed
   this both ✅ and ❌ due to a copy-paste error — it's ✅, one file)

## API Coverage Analysis

### Fully Implemented Services (1:1 API Coverage)
Services that implement ALL operations from the Google Ads API:

1. ✅ `google_ads_service` - search, search_stream, mutate, mutate_operation
2. ✅ `customer_service` - list_accessible_customers, create_customer_client, mutate_customer  
3. ✅ `campaign_service` - create/update campaigns with full bidding & channel type support (Search, Display, Shopping, Video, PMax)
4. ✅ `ad_group_service` - mutate_ad_groups (create, update, remove)
5. ✅ `budget_service` - mutate_campaign_budgets (create, update, remove)
6. ❌ ~~`ad_service` - mutate_ads, get_ad~~ **WRONG, see 2026-08-17 re-audit note
   at top.** `src/services/ad_group/ad_service.py` exists but calls
   `AdGroupAdService`, not `AdService` — it has no `mutate_ads`/`get_ad`
   methods. Real `AdService` is unimplemented.
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

(Superseded by the 2026-08-17 re-audit — the list below is current as of
that pass. 26 real gaps remain; grouped by how likely they matter for a
write/automation use case, not by API category.)

### High Priority
1. `ad` (`AdService`) - the mislabeled gap found this pass. Real service is
   update-only (`mutate_ads`, no create/remove) but it's the only way to
   touch ad-level fields (e.g. `final_urls`) without going through
   `AdGroupAdService`'s combined ad+ad_group_ad object — worth its own
   correctly-named wrapper.
2. `campaign_group`, `campaign_goal_config`, `goal` - if the eventual
   write/automation service (see CLAUDE.md CURRENT TASK) needs to set
   target ROAS/CPA at a cross-campaign or account level, these are likely
   load-bearing; check before assuming `campaign`/`bidding_strategy` cover it.
3. `asset_set_asset`, `customer_asset_set`, `asset_group_listing_group_filter` -
   PMax asset-group plumbing; PMax campaigns already have partial coverage
   (`asset_group`, `asset_group_asset`, `asset_group_signal`) but these
   linking services are what actually attach assets/listing filters to a
   PMax asset group.

### Medium Priority
1. `conversion_value_rule_set`, `data_link`, `recommendation_subscription`,
   `user_list_customer_type`, `keyword_theme_constant`
2. Newly-added-in-v25, unevaluated (`asset_generation`,
   `automatically_created_asset_removal`, `you_tube_video_upload`) - check
   whether these are read-only reporting or actually mutate-capable before
   prioritizing.

### Low Priority
1. `smart_campaign_setting`, `shareable_preview` - Smart Campaigns / ad
   previews, unlikely to matter for boo.ua's account.
2. `content_creator_insights`, `third_party_app_analytics_link`,
   `product_link_invitation`, `local_services_lead`,
   `customer_sk_ad_network_conversion_value_schema` - specialized/vertical
   features (YouTube creators, app analytics, Local Services Ads, iOS SKAN)
   not relevant to a standard Search/PMax/Shopping account.
3. `benchmarks`, `incentive`, `multi_party_auth_review`, `reservation` -
   new in v25, unevaluated; likely low-value for automation (benchmarks/
   incentive read informational data, reservation/multi_party_auth_review
   sound account-admin-flow-specific rather than campaign-management).

Also still open, pre-existing and unrelated to this pass: the 3 partial
services under "Partially Implemented Services" above (`keyword_plan`,
`reach_plan`, `recommendation` — each missing specific operations, not
whole services) weren't re-verified this round either.

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