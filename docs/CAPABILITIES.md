# What this service can actually do

A capability guide, not a service inventory - answers "can I get X done"
from a marketer's perspective when setting up or running an account. For
the exhaustive 110-service technical breakdown, see
[`TRACKER.md`](../TRACKER.md) / [`FEATURE_PARITY.md`](./FEATURE_PARITY.md)
instead - this file stays at the task level on purpose.

**Update this whenever a real capability question gets resolved by actually
reading the code** - not from memory, not from what TRACKER.md's category
table implies. E.g. the Performance Max / audience-signals entry below was
written after opening `asset_group_signal_service.py` and confirming what
it does, not by assuming from the service name. Keep it that way - a stale
"assumed" answer here is worse than no answer.

## Legend

- ✅ **Ready now** - an MCP tool does this today
- 🤖 **Needs the agent, not the API** - no Google Ads API feature does this
  at all (not a gap on our side - it plainly doesn't exist anywhere); the
  agent supplies the judgment/creativity, then executes via the ✅ tools
- 🌐 **Outside the API entirely** - has to happen on the website or
  elsewhere; no tool, ours or Google's, can do it
- ❌ **Real gap** - the Google Ads API supports this, nobody's wrapped it
  into a tool here yet

## Campaigns & structure

- ✅ Search, Display, Shopping, Video, Performance Max campaign creation,
  full bidding-strategy support, campaign budgets
- ❌ `campaign_group` (grouping campaigns for reporting/goals),
  `campaign_goal_config` (lifecycle goals), `smart_campaign_setting`,
  `shareable_preview` - real gaps, all low-priority for a standard build

## Performance Max, specifically

Verified 2026-08-27 by reading the actual service code, not the service
name/TRACKER category:

- ✅ Campaign creation, budget, asset groups, linking image/video/text/logo
  assets to a group
- ✅ **Audience signals** - `asset_group_signal_service.py` has
  `create_audience_signal` (attach any existing Audience resource: custom
  audience, user list, in-market/affinity segment) and
  `create_search_theme_signal` (text search-theme signals). Confirmed by
  reading the method bodies, not assumed.
- ❌ `asset_group_listing_group_filter` - only matters for **retail** PMax
  with a Merchant Center product feed split across multiple asset groups by
  product subset. Doesn't apply to a single-asset-group PMax or a
  non-retail (lead-gen) PMax - most builds never hit this gap.

## Conversions

- ✅ Create/update conversion actions - type, category, value settings,
  attribution model
- 🌐 Installing the Google tag / GTM configuration on the actual website -
  not an API capability at all, always manual, regardless of any tool

## Audiences, segments, interests

- ✅ Custom audiences, custom interests, user lists (including **Customer
  Match** - uploading email/phone lists), audience insights research
- 🌐 A remarketing list's *definition* is created via API, but it only
  fills with real visitors once the site's Google tag is live and actually
  firing - always manual, same as conversions above
- ❌ `user_list_customer_type`, `keyword_theme_constant` - narrow gaps

## Keyword research & grouping

- ✅ Real research data: `keyword_plan_idea` generates ideas from seed
  keywords, a URL, or a whole site - with search volume, competition, and
  suggested bids
- 🤖 **Semantic grouping into ad groups by theme/intent** - the API hands
  back a flat list of ideas with metrics; it does not cluster them into
  logical ad groups. That's the agent's job: take the raw idea list, group
  it with judgment (considering the account's actual structure/intent),
  then use the existing ad_group/keyword tools to build it out

## Ads & creative

- ✅ Creating the ad itself (responsive search ads, expanded text ads)
  once the copy exists
- 🤖 **Writing the actual headline/description text** - the Google Ads API
  has no "generate ad copy" feature anywhere, for anyone - this isn't a gap
  in our coverage, the capability simply doesn't exist as an API surface.
  This is squarely the agent's job: write copy given the business/USPs/
  brand tone, then publish it via the ✅ ad-creation tools

## Extensions (assets)

Verified 2026-09-04 by reading `asset_service.py` directly - the resource
proto has 29 asset-type variants total, most of which aren't "extensions"
in the classic Ads-UI sense at all (dynamic-remarketing feed assets, Hotel/
Demand-Gen specific formats, HTML5 upload bundles). Of the ones that are:

- ✅ Sitelinks, callouts, structured snippets, call, price, app, promotion,
  lead form, location, call-to-action, business message (WhatsApp) - 11
  types, full create support. Location assets take a Place ID directly
  (not synced from a linked Business Profile). Lead form assets support
  predefined fields only (no custom qualifying questions) and webhook
  delivery only (v25 has no email-delivery option). Promotion assets
  support percent/money discounts and code/minimum-order triggers, not
  barcode/QR triggers.
- ❌ `hotel_callout_asset`, `hotel_property_asset`, `book_on_google_asset`
  - Hotel campaigns only, real gap if ever needed
- ❌ `dynamic_*_asset` (education/real-estate/custom/hotels-and-rentals/
  flights/travel/local/jobs) - Dynamic Remarketing feed assets, a
  different feature area from extensions, not attempted
- ❌ `demand_gen_carousel_card_asset`, `youtube_video_list_asset` - Demand
  Gen ad-format assets, not extensions
- ❌ `media_bundle_asset`, `page_feed_asset`, `app_deep_link_asset` -
  HTML5 upload / DSA page-feed / deep-link sub-component, not extensions

## The pattern worth noticing

Almost everything the user was most worried about going into a
greenfield-account build - writing ads, building audiences, keyword
grouping - turns out to be 🤖 territory, not ❌ territory: not a coverage
gap to close, but the actual API having no such feature for anyone, and
the agent being the right tool for that part of the job anyway. The real
❌ gaps left (PMax listing-group filters, a handful of narrow v25
additions) are mostly edge cases a standard non-retail build won't even
touch.
