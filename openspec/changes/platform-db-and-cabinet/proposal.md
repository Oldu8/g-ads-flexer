## Why

The hosted backend (`hosted-multitenant-writes`) needs real tables and real connected accounts before it can be built or tested, and D7 forbids getting an account any other way than through a Google grant plus discovery, including for the operator's own accounts. On 2026-09-23 the user chose to build a minimal cabinet first rather than a CLI bridge, so this change comes before the hosted backend.

Decisions this implements (`docs/ROADMAP.md`): `web/` owns every migration, including the tables Python writes to; Drizzle; one database with row-level tenant isolation (every tenant-owned row carries `ad_account_id`, taken from the MCP URL the verified access token was issued for, never from tool arguments); one Supabase project with a prod schema and a dev schema behind separate roles; refresh tokens encrypted with AES-256-GCM using an application key; both apps hosted on Railway.

## What Changes

**Sides touched: web and DB. mcp-server reads the contract but does not change here.**

- `web/`: Next.js (App Router, TypeScript) skeleton, Drizzle schema and generated SQL migrations for **all** platform tables, schemas `app` and `app_dev` with least-privilege roles.
- Better Auth (decided 2026-09-27: Auth.js is in security-only maintenance and its maintainers direct new projects to Better Auth) + Google provider asking for `adwords` in the same grant (offline access, `prompt=select_account consent`). Account database hooks make sure the refresh token is only ever stored encrypted.
- Discovery over the Google Ads REST API (`listAccessibleCustomers` + `customer_client` walk), then a checkbox list that creates `ad_accounts` rows.
- **Revised 2026-09-29 (track B2, D20–D25):** Claude Desktop / claude.ai reach remote MCP servers only through OAuth (static headers are an org-level beta), so the cabinet becomes the OAuth authorization server (`@better-auth/mcp` + `jwt()`, dynamic client registration, ES256 JWTs). Every ad account gets its own MCP URL `https://ads-mcp.vtrata.com/mcp/<slug>`; OAuth proves who is connecting, the URL says which account. No static bearer token.
- One screen per account: MCP URL + Claude Desktop steps, connected clients with "Disconnect", enable/disable, "allow changes" toggle (`tool_profile`: `read_only` by default, `manager` when on), business `context` (≤ 2,000 chars), fixes log, remove.
- The platform creates the fixes-log Google Sheet per account in the user's Drive (`drive.file` in the sign-in grant); no service account.
- Railway service for `web/`.

Non-goals: landing page, pricing, blog, billing, a pending-change dashboard (approval stays in chat, D6), multiple Google connections per user in the UI, RLS policies (deferred; isolation is enforced in the MCP server's choke point), Client ID Metadata Documents (needs an SSRF-safe fetch transport; Claude falls back to dynamic registration), attaching sheets the platform did not create.

## Capabilities

### New Capabilities
- `platform-schema`: the shared tables, who may read or write which, schemas/roles, and the token-encryption format both sides depend on.
- `account-connection`: how a person turns a Google login into ad accounts exposed over MCP.

### Modified Capabilities
<!-- None. -->

## Impact

- New: everything under `web/` except `README.md` (rewritten).
- Supersedes tasks 6.1 and 7.1–7.3 of `remove-developer-token-connection-model`.
- `docs/PLATFORM_ARCHITECTURE.md` "Data model" is out of date after this change (`accounts` → `ad_accounts`, `google_connections` = Better Auth's account table, `pending_changes` added, Python writes); it is rewritten in iteration 3, and this change's spec is authoritative until then.
- Changes `hosted-multitenant-writes` (Phase C): JWT verification instead of a token-hash lookup, one MCP path per account, fixes log written with the user's grant, no local-token mode.
- Operator actions outside the code: Supabase project + both roles; OAuth client redirect URIs for `http://localhost:3000` and the Railway domain; Google Drive API and Google Sheets API enabled, `drive.file` and `adwords` declared under Data Access, consent screen published to Production without verification (done 2026-09-29: unverified-app warning, 100-user cap, no 7-day token expiry).
