# V2 commercial roadmap (superseded — kept as historical record)

**Superseded 2026-09-07 by
[`../../docs/PLATFORM_ARCHITECTURE.md`](../../docs/PLATFORM_ARCHITECTURE.md)**
— the vision below (each client brings full separate Ads API credentials)
turned out not to be what got built; the actual plan is one MCC per user,
Google OAuth login doing double duty as identity + Ads-access grant, and a
two-repo (`mcp-server/` + `web/`) split with Postgres as the only
integration point. Read that doc instead for anything current. This file
stays only so the "shared-MCC rejected" reasoning below isn't lost - it's
still correct context for why the platform doc's data model looks the way
it does (one MCC per user, not a shared platform-owned MCC).

---

This records the v2 product vision as scoped 2026-08-27, so it isn't lost
and so near-term decisions can be made with it in mind — **without**
building any of it now. Per-client (v1) is still the active model; see
[`CLIENT_ONBOARDING.md`](./CLIENT_ONBOARDING.md) and the 2026-08-27 (3)
TRACKER.md entry for why v2 is deliberately deferred until there's a real
paying client validating demand on v1.

## The v2 vision (user's words, organized)

1. **Admin panel + authentication.** A real web app clients log into.
2. **Encrypted credential storage.** Client-submitted Google Ads API
   credentials (developer token, OAuth client id/secret, refresh token)
   stored server-side, encrypted at rest — not a plain DB column (these are
   other companies' API secrets).
3. **No billing yet.** Testing informally through personal contacts first;
   billing gets built later if that validates. Design should not preclude
   adding it, but nothing billing-shaped needs building now.
4. **Per-account entitlement, not per-MCC.** A client's MCC can contain
   multiple ad accounts (the user's own MCC currently has 2). Buying
   "access to the service" should be scoped to specific accounts within
   that MCC, chosen by the client (e.g. account A enabled, account B not)
   — this is the basis for future per-account billing. Enforcing this
   needs a real authorization check in the admin panel / API layer, not
   just a UI toggle. Also stated as a hard rule: **one Google Sheet maps to
   exactly one ad account, never one MCC** — multiple accounts sharing a
   sheet was explicitly called out as something that "will be a mess."

## Design-with-this-in-mind principle

Nothing below should be built now. The point of writing it down is so that
if a near-term decision has an easy option that keeps this path open and a
slightly-easier option that closes it off, the easy-but-open option wins
when the cost is comparable. It's not a license to add speculative
abstraction to code that doesn't need it yet.

## Where today's code already conflicts with this vision (the gap analysis)

None of these are bugs to fix right now — they're the concrete list of
"this will need rework, not just extension" when v2 actually starts.

1. **No account-level authorization anywhere.** Every tool that takes
   `customer_id` executes against whatever `customer_id` it's given, as
   long as the process's Google Ads credentials can reach it. There's no
   allow-list, no concept of "this caller may touch account A but not
   account B." The v2 "client picks which accounts are enabled" feature
   needs an authorization check inserted before every tool's Google Ads
   call, keyed off caller identity — that check doesn't exist in any form
   today (not even a stub).

2. ~~The fixes-log Sheet is one-per-process, not one-per-account.~~
   **Fixed 2026-08-27.** `FixesLogSheet.for_customer(customer_id)` now
   resolves the right spreadsheet per account via
   `snapshots/account_sheets.json` (a `customer_id -> spreadsheet_id` map,
   template at `account_sheets.example.json`), falling back to the
   single-account `GOOGLE_SHEETS_SPREADSHEET_ID` env var, and raising
   loudly if neither resolves - never guessing/mixing accounts.
   `FixesLogService` now takes `customer_id` on every method and
   routes/caches per account. This closes the entitlement-*data-shape* gap
   (a fix for account B can no longer physically land in account A's
   sheet) - it does **not** add authorization (#1 below still applies:
   nothing stops a caller from passing whichever `customer_id` it wants,
   it just now always lands in *that* account's own sheet, correctly).

3. **The pending-change store is similarly one-per-process.**
   `snapshots/pending_changes.json` (`src/services/review/pending_change_store.py`)
   is one shared file for the whole running instance. Each record does
   store its own `customer_id` inside `params`, so the *data* to filter by
   account exists - but there's no enforcement that a given caller may only
   propose/apply changes for their entitled account(s). Same class of gap
   as #1/#2, not yet a problem because there's exactly one trusted operator
   (the user) using it today.

4. **No tenant/client identity concept in the code at all.** Every service
   assumes a single global identity, resolved once at process startup from
   `.env` (`src/sdk_client.py`'s `get_sdk_client()`/`set_sdk_client()`
   singleton). Introducing multi-client support means this becomes
   per-request credential + entitlement resolution keyed off whatever
   identifies the caller (an MCP bearer token, most likely) - a rework of
   the client-acquisition path, not an additive change. This was already
   flagged in the 2026-08-27 (3) TRACKER.md entry re: the admin-panel/
   billing pivot; repeated here because it's the same underlying gap that
   also blocks per-account entitlement specifically (#1).

## Not decided yet (deliberately - revisit only when v2 actually starts)

- Where the per-account entitlement check should live (a decorator/middleware
  around every tool call? a wrapper service like `pending_change`'s? part of
  the future admin-panel API layer?).
- Whether "one sheet per account" should be enforced by the code (reject a
  `log_fix` call if its account isn't the sheet's assigned account) or left
  as an onboarding-time convention.
- What identifies a caller once there are multiple clients - an MCP bearer
  token minted per client, most likely, but the mapping from that token to
  {credentials, entitled accounts, sheet(s)} isn't designed.
