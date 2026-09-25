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

### Requirement: Bearer token identifies exactly one enabled account
`DbTokenVerifier.verify_token` SHALL hash the presented token (sha256, hex), look up `ad_accounts` by `bearer_token_hash` joined to its connection, and return an `AccessToken` carrying the tenant fields only when the account is enabled and the connection is not revoked; otherwise it SHALL return None without calling Google. `last_used_at` SHALL be updated at most once per minute per account.

#### Scenario: Disabled account
- **WHEN** a request presents the token of an account with `enabled = false`
- **THEN** authentication fails and no Google Ads call is made

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

### Requirement: Local mode uses the same path
`main.py` (stdio) SHALL read a bearer token from `MCP_ACCOUNT_TOKEN`, resolve the tenant with the same verifier, and otherwise behave exactly like the hosted entrypoint (profile, pinning, queue, quota). `GOOGLE_ADS_REFRESH_TOKEN` and the local alias registry SHALL no longer be read. The fixes-log sheet SHALL come from `ad_accounts.fixes_sheet_id` in both modes.

#### Scenario: No token configured
- **WHEN** `main.py` starts without `MCP_ACCOUNT_TOKEN`
- **THEN** it exits with a message pointing to the cabinet to create a token
