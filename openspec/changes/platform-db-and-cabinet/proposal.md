## Why

The hosted backend (`hosted-multitenant-writes`) needs real tables and real connected accounts before it can be built or tested, and D7 forbids getting an account any other way than through a Google grant plus discovery, including for the operator's own accounts. On 2026-09-23 the user chose to build a minimal cabinet first rather than a CLI bridge, so this change comes before the hosted backend.

Decisions this implements (`docs/ROADMAP.md`): `web/` owns every migration, including the tables Python writes to; Drizzle; one database with row-level tenant isolation (every tenant-owned row carries `ad_account_id`, taken from the bearer token and never from tool arguments); one Supabase project with a prod schema and a dev schema behind separate roles; refresh tokens encrypted with AES-256-GCM using an application key; both apps hosted on Railway.

## What Changes

**Sides touched: web and DB. mcp-server reads the contract but does not change here.**

- `web/`: Next.js (App Router, TypeScript) skeleton, Drizzle schema and generated SQL migrations for **all** platform tables, schemas `app` and `app_dev` with least-privilege roles.
- Auth.js v5 + Google provider asking for `adwords` in the same grant (offline access, `prompt=consent`). The adapter is wrapped so the refresh token is only ever stored encrypted.
- Discovery over the Google Ads REST API (`listAccessibleCustomers` + `customer_client` walk), then a checkbox list that creates `ad_accounts` rows.
- One screen per account: issue or regenerate the bearer token (shown once), MCP URL, enable/disable, "allow changes" toggle (`tool_profile`: `read_only` by default, `manager` when on), business `context` (≤ 2,000 chars), `fixes_sheet_id` next to the service-account email to share the sheet with.
- Railway service for `web/`.

Non-goals: landing page, pricing, blog, billing, a pending-change dashboard (approval stays in chat, D6), multiple Google connections per user in the UI, token history, RLS policies (deferred; isolation is enforced in the MCP server's choke point).

## Capabilities

### New Capabilities
- `platform-schema`: the shared tables, who may read or write which, schemas/roles, and the token-encryption format both sides depend on.
- `account-connection`: how a person turns a Google login into ad accounts exposed over MCP.

### Modified Capabilities
<!-- None. -->

## Impact

- New: everything under `web/` except `README.md` (rewritten).
- Supersedes tasks 6.1 and 7.1–7.3 of `remove-developer-token-connection-model`.
- `docs/PLATFORM_ARCHITECTURE.md` "Data model" is out of date after this change (`accounts` → `ad_accounts`, `google_connections` = the Auth.js account table, `pending_changes` added, Python writes); it is rewritten in iteration 3, and this change's spec is authoritative until then.
- Operator actions outside the code: Supabase project + both roles; OAuth client redirect URIs for `http://localhost:3000` and the Railway domain; pilot users added as test users on the consent screen until `adwords` verification clears (refresh tokens of test users expire after 7 days).
