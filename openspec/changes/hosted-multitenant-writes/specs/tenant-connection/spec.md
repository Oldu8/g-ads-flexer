## Purpose

How a request's Google Ads access is resolved from the database without a developer token, and how every Google Ads call made while serving it is pinned to exactly one ad account, whatever the model passes.

## ADDED Requirements

### Requirement: No per-tenant developer token
The system SHALL NOT store, request, send or display a developer token. The `google-ads` dependency SHALL be ≥ 32.0.0, the first release where `developer_token` is optional, so no placeholder exists anywhere.

#### Scenario: Building a client
- **WHEN** a client is built for a request
- **THEN** it uses the platform OAuth client id/secret from env, the connection's decrypted refresh token and the account's `login_customer_id`
- **AND** outgoing requests carry no `developer-token` header

### Requirement: Credentials are resolved per request, never cached on services
The active tenant (`ad_account_id`, `google_connection_id`, `customer_id`, `login_customer_id`, `tool_profile`) SHALL live in a contextvar set once per request. Services SHALL obtain Google Ads service clients through `get_service(name)`, which caches by `(google_connection_id, login_customer_id, name)` with a 30-minute TTL. No service SHALL keep a client on `self`.

#### Scenario: Two tenants in sequence
- **WHEN** tenant A calls a tool and then tenant B calls the same tool in the same process
- **THEN** B's request is built from B's refresh token and B's `login_customer_id` (verified in a test with a fake client factory)

#### Scenario: A service caching a client on self
- **WHEN** any module under `src/services/` assigns a Google Ads service client to an instance attribute
- **THEN** a test fails naming the module

### Requirement: One MCP URL per account, OAuth access token per request
The server SHALL serve streamable HTTP at `/mcp/{mcp_slug}`, one path per ad account (D23). For every path it SHALL publish protected-resource metadata (RFC 9728) with `resource` = that exact URL and `authorization_servers` = [the web issuer] as the only entry, and answer unauthenticated requests with 401 and `WWW-Authenticate: Bearer resource_metadata="<that path's metadata URL>"`, so that Claude Desktop discovers the web authorization server. An access token SHALL be accepted only as defined in `platform-schema` "MCP access-token format": signature (ES256, keys from the web JWKS, cached), `iss`, `exp`, the one MCP URL in `aud` equal to the request's URL (other `aud` entries, such as the web userinfo endpoint, are ignored), and an `ad_accounts` row with that slug owned by `sub`, enabled, whose connection is not revoked; otherwise 401, without calling Google. The row lookup happens on every request, so toggles in the cabinet apply immediately. `last_used_at` SHALL be updated at most once per minute per account. The per-path routing and metadata MAY require wrapping or upgrading FastMCP 2.14.7 (its auth serves one resource per app); that choice is made at the start of the phase.

#### Scenario: Disabled account
- **WHEN** a request presents a valid token for an account with `enabled = false`
- **THEN** authentication fails and no Google Ads call is made

#### Scenario: Token replayed on another account's path
- **WHEN** a token issued for `/mcp/aaaa` is presented at `/mcp/bbbb`
- **THEN** the request gets 401

#### Scenario: Unknown slug
- **WHEN** a client calls `/mcp/zzzz` for which no account exists
- **THEN** the request gets 401 (after discovery, authorization fails at the web side), never a tool list

### Requirement: The account is pinned at the transport
A gRPC client interceptor installed by `get_service` SHALL, for every RPC: allow it if the request's `customer_id` equals the pinned `customer_id`; allow it if the request has no `customer_id` field and the method is on a short allowlist of customer-independent methods (field metadata, geo-target suggestion); otherwise abort before sending.

#### Scenario: A tool computes the wrong customer id
- **WHEN** a tool builds a request for customer 9999999999 while the pinned account is 1234567890
- **THEN** the interceptor aborts, nothing is sent to Google, and the tool returns an "account mismatch" error

### Requirement: The model never chooses the account
On every profile, `customer_id` SHALL be removed from tool input schemas in `on_list_tools` and injected with the pinned value in `on_call_tool`. A call that still passes a different `customer_id` SHALL be rejected with a clear message.

#### Scenario: Listing tools
- **WHEN** a client lists tools
- **THEN** no tool schema has a `customer_id` property

### Requirement: Account context reaches the agent without a tool call
A synthetic tool `account_context` SHALL be listed for every tenant, with a description made of the account's display name, customer id and `context` text; calling it returns the same text. This replaces per-account server `instructions`, which FastMCP 2.14.7 cannot vary per tenant.

#### Scenario: Context present
- **WHEN** an account's `context` is "pawnshop marketplace, ~10% margin, ROAS ≠ profit"
- **THEN** that sentence appears in the `account_context` tool description in `tools/list`

### Requirement: Revoked grants are detected and surfaced
When token refresh fails with `invalid_grant`, the system SHALL set `google_connections.revoked_at`, drop cached clients for that connection, and return the reconnect message; the verifier then refuses the connection's tokens until the user signs in again.

#### Scenario: User revoked access in their Google account
- **WHEN** the next tool call triggers a token refresh and Google answers `invalid_grant`
- **THEN** the call returns the reconnect message and `revoked_at` is set

### Requirement: No local-token mode
There SHALL be no static token and no stdio entrypoint that reads Google credentials from `.env` (D25). Local development SHALL run the hosted entrypoint on localhost against `app_dev`, with `web/` on `http://localhost:3000` as the authorization server; MCP clients that support OAuth against a loopback resource (Claude Code) connect to `http://localhost:<port>/mcp/<slug>`. `GOOGLE_ADS_REFRESH_TOKEN`, the local alias registry and `account_sheets.json` SHALL no longer be read, and `main.py` (stdio) is removed together with `remote_main.py`. The fixes-log sheet SHALL come from `ad_accounts.fixes_sheet_id` and be written with the connection's own grant (`drive.file`); the service-account credentials (`GOOGLE_SHEETS_CREDENTIALS_*`) are removed.

#### Scenario: Developer runs the server locally
- **WHEN** a developer starts the hosted entrypoint on localhost with `app_dev` credentials and adds `http://localhost:8000/mcp/<slug>` to Claude Code
- **THEN** Claude Code completes OAuth against `http://localhost:3000` and the requests are pinned to that dev account

#### Scenario: Fixes log without Drive access
- **WHEN** the connection's `scope` lacks `drive.file` or `fixes_sheet_id` is NULL
- **THEN** fixes-log tools answer "no fixes log available; open the account in the cabinet", and applies still succeed
