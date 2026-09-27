## Purpose

Turn "sign in with Google" into ad accounts that an MCP client can use, with the same path for the operator and for any new user (D7): no hardcoded accounts, no pasted ids.

## ADDED Requirements

### Requirement: One Google grant signs in and grants Ads access
Sign-in SHALL use Better Auth with the Google provider, requesting scopes `openid email profile https://www.googleapis.com/auth/adwords`, `access_type=offline` and `prompt=select_account consent`. Better Auth's account database hooks SHALL encrypt the refresh token into `refresh_token_enc` and null the access and id tokens before any write, so that a later sign-in which returns a new refresh token overwrites `refresh_token_enc`; a successful sign-in SHALL clear `revoked_at`.

#### Scenario: First sign-in
- **WHEN** a new person signs in and consents
- **THEN** one `users` row and one `google_connections` row exist, the refresh token is stored encrypted only, and the person lands on discovery

#### Scenario: Reconnect after revocation
- **WHEN** a connection has `revoked_at` set and the user signs in again
- **THEN** `refresh_token_enc` is replaced and `revoked_at` is cleared

### Requirement: One OAuth client for both sides
`AUTH_GOOGLE_ID`/`AUTH_GOOGLE_SECRET` in `web/` and `GOOGLE_ADS_CLIENT_ID`/`GOOGLE_ADS_CLIENT_SECRET` in `mcp-server/` SHALL be the same OAuth client of Cloud project `178951272716`, because a refresh token only works with the client it was issued to, and the Ads API access level belongs to that project.

#### Scenario: Misconfigured deploy
- **WHEN** the two sides are deployed with different client ids
- **THEN** the MCP server's first token refresh fails with `unauthorized_client`, and the deploy checklist (task 4.1) catches this by comparing the two values

### Requirement: Discovery lists every reachable ad account
Discovery SHALL run server-side in Next.js against the Google Ads REST API, using an access token minted from the stored refresh token: `customers:listAccessibleCustomers`, then for each manager returned, a GAQL search over `customer_client` with `login-customer-id` set to that manager (fields `customer_client.id`, `.descriptive_name`, `.manager`, `.status`, `.level`). The result SHALL be flattened to `(customer_id, login_customer_id, display_name, is_manager, status)`, and only non-manager, `ENABLED` accounts SHALL be offered. No developer-token header SHALL be sent. The API version SHALL be one constant matching the Python SDK's (v25).

#### Scenario: Account reached through a manager
- **WHEN** the grant reaches manager 111 and 111 has child 222
- **THEN** 222 is offered, and choosing it stores `customer_id` = 222 and `login_customer_id` = 111

#### Scenario: Direct access
- **WHEN** `listAccessibleCustomers` returns non-manager account 333 directly
- **THEN** choosing it stores `login_customer_id = NULL`

### Requirement: Per-account controls
For each `ad_accounts` row the cabinet SHALL show: display name and customer id; the MCP URL (one URL for all accounts, `https://<mcp-host>/mcp`); a "generate token" / "regenerate token" action that displays the token once, with a copy button and an example `.mcp.json`/Claude Code snippet; an enabled toggle; an "allow changes" toggle mapping to `tool_profile` (`read_only` off, `manager` on) with a line explaining that every change still waits for approval in chat; a `context` textarea (≤ 2,000 chars); a `fixes_sheet_id` field with the platform service-account email to share the sheet with as Editor.

#### Scenario: Token shown once
- **WHEN** the user generates a token and reloads the page
- **THEN** the token is no longer visible; only "regenerate" is offered

#### Scenario: Disabling an account
- **WHEN** the user switches an account off
- **THEN** its token stops authenticating on the MCP server (the verifier checks `enabled`), without deleting the row

### Requirement: Users only see their own rows
Every cabinet query and mutation SHALL be scoped by the signed-in user's id; ids in URLs or forms SHALL be checked against that user's rows.

#### Scenario: Guessing another user's account id
- **WHEN** a signed-in user submits a form for an `ad_accounts.id` belonging to someone else
- **THEN** the request is rejected and nothing changes
