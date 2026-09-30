# account-connection Specification

## Purpose

Turn "sign in with Google" into ad accounts that an MCP client can use, with the same path for the operator and for any new user (D7): no hardcoded accounts, no pasted ids. The target client is Claude Desktop / claude.ai (D22), which connects to a remote MCP server only through OAuth, so the cabinet is also the OAuth authorization server for the MCP server.

## Requirements

### Requirement: One Google grant signs in, grants Ads access and lets the platform keep a sheet
Sign-in SHALL use Better Auth with the Google provider, requesting scopes `openid email profile https://www.googleapis.com/auth/adwords https://www.googleapis.com/auth/drive.file`, `access_type=offline` and `prompt=select_account consent`. `drive.file` is non-sensitive and only reaches files the app created; it is how the platform creates and writes the fixes-log sheet (D21). Better Auth's account database hooks SHALL encrypt the refresh token into `refresh_token_enc` and null the access and id tokens before any write, so that a later sign-in which returns a new refresh token overwrites `refresh_token_enc`; a successful sign-in SHALL clear `revoked_at`. Better Auth does not update `scope` on a repeat sign-in, so whenever `web/` mints a Google access token it SHALL write the scopes Google reports as granted back to `google_connections.scope` (comma-joined, sorted); the MCP server may do the same.

#### Scenario: First sign-in
- **WHEN** a new person signs in and consents
- **THEN** one `users` row and one `google_connections` row exist, the refresh token is stored encrypted only, `scope` lists `adwords` and `drive.file`, and the person lands on discovery

#### Scenario: Drive unticked on Google's consent screen
- **WHEN** the person unticks the Drive permission (Google's granular consent) and the stored `scope` lacks `drive.file`
- **THEN** sign-in and discovery still work, and every account page shows "Allow the fixes log in Google Drive", which re-runs the Google grant

#### Scenario: Drive granted on a later sign-in
- **WHEN** a user who first signed in without `drive.file` signs in again and grants it
- **THEN** the next page that talks to Google stores the new `scope`, and the account page offers the sheet instead of "Grant access"

#### Scenario: Reconnect after revocation
- **WHEN** a connection has `revoked_at` set and the user signs in again
- **THEN** `refresh_token_enc` is replaced and `revoked_at` is cleared

### Requirement: One OAuth client for both sides
`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` in `web/` and `GOOGLE_ADS_CLIENT_ID`/`GOOGLE_ADS_CLIENT_SECRET` in `mcp-server/` SHALL be the same OAuth client of Cloud project `178951272716`, because a refresh token only works with the client it was issued to, and the Ads API access level belongs to that project.

#### Scenario: Misconfigured deploy
- **WHEN** the two sides are deployed with different client ids
- **THEN** the MCP server's first token refresh fails with `unauthorized_client`, and the Phase C deploy checklist catches this by comparing the two values

### Requirement: Discovery lists every reachable ad account
Discovery SHALL run server-side in Next.js against the Google Ads REST API, using an access token minted from the stored refresh token: `customers:listAccessibleCustomers`, then for each manager returned, a GAQL search over `customer_client` with `login-customer-id` set to that manager (fields `customer_client.id`, `.descriptive_name`, `.manager`, `.status`, `.level`). The result SHALL be flattened to `(customer_id, login_customer_id, display_name, is_manager, status)`, and only non-manager, `ENABLED` accounts SHALL be offered, grouped by the manager that reaches them. An account reached several ways SHALL be offered once: direct access (`login_customer_id = NULL`) wins, otherwise the path with the lowest `level`. No developer-token header SHALL be sent. The API version SHALL be one constant matching the Python SDK's (v25).

#### Scenario: Account reached through a manager
- **WHEN** the grant reaches manager 111 and 111 has child 222
- **THEN** 222 is offered, and choosing it stores `customer_id` = 222 and `login_customer_id` = 111

#### Scenario: Direct access
- **WHEN** `listAccessibleCustomers` returns non-manager account 333 directly
- **THEN** choosing it stores `login_customer_id = NULL`

#### Scenario: Reached twice
- **WHEN** account 444 is directly accessible and also a child of manager 111
- **THEN** it is offered once, with `login_customer_id = NULL`

### Requirement: Adding an account gives it its own MCP address and fixes log
Saving the discovery checkboxes SHALL create an `ad_accounts` row per newly chosen account (unique per connection + customer; existing rows are kept, and discovery never deletes on its own). Each new row SHALL get a random `mcp_slug`, and an `oauth_resource` row whose identifier is the account's MCP URL `<MCP_PUBLIC_URL>/<mcp_slug>` (e.g. `https://ads-mcp.vtrata.com/mcp/k7d2m9x4q1ta`), so that access tokens can be issued for exactly that account (D23). The platform SHALL then create the account's fixes-log sheet (below); a sheet failure SHALL NOT undo the account.

#### Scenario: Two accounts, two addresses
- **WHEN** a user adds accounts 222 and 333
- **THEN** there are two `ad_accounts` rows with different `mcp_slug` values and two enabled `oauth_resource` rows, one per MCP URL

### Requirement: The platform creates one fixes-log sheet per account
The sheet SHALL be created with the Sheets API (`spreadsheets.create`) using an access token minted from the connection's refresh token (scope `drive.file`), in the user's own Drive, titled `Adsmigo fixes log — <display_name> (<customer id as 123-456-7890>)`, with one tab named `Fixes` whose first row is the header from `web/db/contracts/fixes-log-header.json` (frozen, bold). The contract file is the single list both sides use; the MCP server appends rows in that column order. The spreadsheet id SHALL be stored in `ad_accounts.fixes_sheet_id`. If the connection lacks `drive.file`, or the stored sheet is gone (the Drive API `files.get` answers 404 or 403, or reports it trashed; other failures are shown as "Drive did not answer", not as missing), the account page SHALL offer "Grant access" or "Create a new sheet" respectively, and creating replaces `fixes_sheet_id`. The platform SHALL NOT attach sheets it did not create.

#### Scenario: Account added with Drive granted
- **WHEN** a user with `drive.file` adds account 222
- **THEN** a spreadsheet titled "Adsmigo fixes log — Shop (222-…)" exists in their Drive with the `Fixes` header, and its id is in `fixes_sheet_id`

#### Scenario: Sheet deleted by the user
- **WHEN** the user deletes the sheet in Drive and opens the account page
- **THEN** the page says the sheet is missing and "Create a new sheet" stores a new id

### Requirement: MCP clients get access through OAuth
`web/` SHALL be the OAuth 2.1 authorization server for the MCP server, using Better Auth's `@better-auth/mcp` plugin (built on `@better-auth/oauth-provider`) and the `jwt()` plugin: authorization code with PKCE `S256` only; open dynamic client registration (RFC 7591) for public clients (`token_endpoint_auth_method: none`), because Claude registers itself that way when Client ID Metadata Documents are not advertised; a registration without `application_type` whose redirect URIs are all `http` loopback (Claude Code) is registered as `native`, since Better Auth refuses loopback redirects for the default `web` type; registered clients get `offline_access` by default (so Claude receives a refresh token) and may ask for `openid profile email`; authorization-server metadata (RFC 8414) served at the root `/.well-known/oauth-authorization-server` (and path-suffixed form) of the web origin; access tokens are JWTs signed with **ES256** (FastMCP's `JWTVerifier` has no EdDSA), valid 1 hour, `aud` = the requested resource (the account's MCP URL), `sub` = the user id; refresh tokens rotate. A `resource` that is not an MCP URL of one of the signed-in user's enabled accounts SHALL be refused before any code is issued: a disabled account's resource is refused at `/oauth2/authorize`, another user's at the consent page (no Allow) and at `/oauth2/consent` (403), and every token issuance, refreshes included, checks again. The canonical resource row (`MCP_PUBLIC_URL`) SHALL exist before the first request (inserted at server start), because Better Auth's own seeding fails permanently for the process when two cold-start requests race. The consent page SHALL name the client (from its registration), the ad account (name and customer id) and what it allows ("read reports; propose changes that you approve in the chat" when changes are allowed), with Allow and Deny. Revoking in the cabinet SHALL delete that client's consent and refresh tokens for the account; the current access token lapses within the hour, and disabling the account stops it immediately (the MCP server checks `enabled` on every request).

#### Scenario: Claude Desktop connects an account
- **WHEN** the user adds the account's MCP URL as a custom connector in Claude Desktop and clicks Connect
- **THEN** Claude registers itself, the browser opens the web origin (Google sign-in if there is no session), the consent page names Claude and the account, and after Allow Claude holds a token whose `aud` is that URL and whose `sub` is the user

#### Scenario: Someone else's account address
- **WHEN** a signed-in user starts authorization with `resource` = the MCP URL of an account owned by another user
- **THEN** the consent page offers no Allow, a direct consent request gets 403, and no code or token is issued

#### Scenario: Disconnecting a client
- **WHEN** the user clicks "Disconnect" next to Claude on the account page
- **THEN** Claude's refresh token for that account no longer works, and Claude must go through consent again after its access token expires

### Requirement: Per-account controls
The cabinet SHALL have: `/app` listing the user's accounts (name, customer id, enabled, changes allowed, last used) with "Add accounts"; `/app/discover` (above); `/app/accounts/[id]` with:
- the MCP URL with a copy button and the steps to add it in Claude Desktop (Settings → Connectors → Add custom connector; suggested name `Ads · <display_name>`), noting that each account is a separate connector;
- connected clients (name, connected at, last refreshed) with "Disconnect";
- an enabled toggle;
- an "allow changes" toggle mapping to `tool_profile` (`read_only` off, `manager` on) with a line explaining that every change still waits for approval in chat;
- a `context` textarea (≤ 2,000 chars, checked server-side);
- the fixes-log link, or the actions from the sheet requirement;
- "Remove account": deletes the row (cascading its queue and usage), its `oauth_resource` row and every consent and token for it; the sheet stays in the user's Drive.

There is no static bearer token (D20 revised 2026-09-29).

#### Scenario: Disabling an account
- **WHEN** the user switches an account off
- **THEN** every token for its URL stops working on the MCP server on the next request, without deleting the row, and new authorizations for it are refused

### Requirement: Users only see their own rows
Every cabinet query and mutation SHALL be scoped by the signed-in user's id; ids in URLs or forms SHALL be checked against that user's rows. The same holds for the OAuth resource check above.

#### Scenario: Guessing another user's account id
- **WHEN** a signed-in user submits a form for an `ad_accounts.id` belonging to someone else
- **THEN** the request is rejected and nothing changes
