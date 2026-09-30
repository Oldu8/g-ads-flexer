# platform-schema Specification

## Purpose

The single contract between `web/` and `mcp-server/`: the tables, which side reads or writes each one, how prod and dev are separated inside one Supabase project, and the exact formats both languages must agree on (encrypted refresh tokens, MCP access tokens, the fixes-log header).

## Requirements

### Requirement: Tables
Migrations in `web/` SHALL create these tables with unqualified names, resolved through the migrating role's `search_path`; generated SQL SHALL NOT name a schema (`db/unqualify-migrations.mjs` strips the `"public".` drizzle-kit adds, and a test enforces it). IDs are UUIDs (Better Auth `generateId: "uuid"`).

- `users`, `sessions`, `verifications`: Better Auth's `user`, `session`, `verification` models (snake_case columns).
- `google_connections`: Better Auth's `account` model under this name: `id`, `user_id`, `account_id` (Google `sub`), `provider_id`, `access_token`, `refresh_token_enc` (Better Auth field `refreshToken`), `id_token`, `access_token_expires_at`, `refresh_token_expires_at`, `scope`, `password`, `created_at`, `updated_at`, plus `revoked_at`; unique `(provider_id, account_id)`. `refresh_token_enc` only ever holds ciphertext; `access_token` and `id_token` SHALL always be NULL.
- `ad_accounts`: `id uuid pk`, `user_id` → `users`, `google_connection_id` → `google_connections.id`, `customer_id text` (10 digits, no dashes), `login_customer_id text null`, `display_name text`, `enabled bool default true`, `tool_profile text default 'read_only' check in ('read_only','manager')`, `context text default '' check (length ≤ 2000)`, `fixes_sheet_id text null` (created by the platform), `mcp_slug text unique not null` (12 chars of `[a-z0-9]`, random; the last path segment of the account's MCP URL, not a secret), `created_at`, `last_used_at`; unique `(google_connection_id, customer_id)`. (`bearer_token_hash` and `token_created_at` are dropped: there is no static token, D20 revised.)
- OAuth authorization-server tables of `@better-auth/oauth-provider` and `jwt()` under snake_case names: `oauth_clients`, `oauth_resources` (one row per ad account, identifier = its MCP URL), `oauth_client_resources`, `oauth_consents`, `oauth_access_tokens`, `oauth_refresh_tokens`, `jwks` (private keys encrypted by Better Auth with `BETTER_AUTH_SECRET`). Only `web/` reads or writes them.
- `pending_changes`: `id text pk` (`pc_` + 12 hex), `ad_account_id` → `ad_accounts` (on delete cascade), `tool_name text`, `arguments jsonb`, `preview jsonb`, `validation text check in ('full','partial','none')`, `status text check in ('pending','applying','applied','failed','rejected','expired')`, `created_at`, `expires_at`, `decided_at null`, `result jsonb null`, `error text null`, `fixes_log_error text null`; index `(ad_account_id, status, created_at desc)`.
- `api_usage`: `ad_account_id` → `ad_accounts`, `day date` (quota day, America/Los_Angeles), `operations int default 0`, `last_call_at`; primary key `(ad_account_id, day)`; index on `day`.
- View `api_usage_daily_totals`: `day`, `total_operations`, `active_accounts`.

#### Scenario: One grant, several accounts
- **WHEN** a user's single Google connection reaches three ad accounts and the user exposes two
- **THEN** there is one `google_connections` row and two `ad_accounts` rows referencing it, each with its own `mcp_slug` and its own `oauth_resources` row

#### Scenario: Plaintext token never stored
- **WHEN** any sign-in completes
- **THEN** `google_connections.access_token` and `id_token` are NULL and `refresh_token_enc` holds a `v1.` ciphertext

### Requirement: Access by side
Table grants to the MCP roles are applied in Phase C (`hosted-multitenant-writes`), when the Python side starts using the database; until then `mcp_dev` / `mcp_prod` exist as NOLOGIN roles with `USAGE` on their schema only. The MCP server's role SHALL then have: `SELECT` on `ad_accounts` and `UPDATE (last_used_at)` on it; `SELECT (id, user_id, refresh_token_enc, scope, revoked_at)` and `UPDATE (revoked_at)` on `google_connections`; `SELECT, INSERT, UPDATE` on `pending_changes` and `api_usage`; `SELECT` on `api_usage_daily_totals`. It SHALL have no access to `users`, `sessions`, `verifications` or any OAuth table: it verifies access tokens with the public keys from the web origin's JWKS endpoint, over HTTPS, not from the database. The web role owns the schema and runs migrations.

#### Scenario: MCP role reads a session
- **WHEN** code running as the MCP role selects from `sessions`
- **THEN** Postgres denies it

### Requirement: Prod and dev are separate schemas with separate roles
The project SHALL have schemas `app` (prod) and `app_dev` (dev). Four roles SHALL exist: `web_prod`, `mcp_prod` (search_path `app`, no privileges on `app_dev`) and `web_dev`, `mcp_dev` (search_path `app_dev`, no privileges on `app`). Migrations SHALL be applied to each schema by running them as that schema's web role. Dev and prod SHALL use different token-encryption keys.

#### Scenario: Dev code pointed at prod data
- **WHEN** a process connected as `mcp_dev` selects from `app.ad_accounts`
- **THEN** Postgres denies it

### Requirement: Refresh-token encryption format
`refresh_token_enc` SHALL be `v1.` followed by base64url (no padding) of `nonce(12 bytes) || ciphertext || tag(16 bytes)`, produced by AES-256-GCM with the 32-byte key from `TOKEN_ENCRYPTION_KEY` (base64) and associated data = the fixed UTF-8 string `adsmigo:google_connections.refresh_token_enc:v1`. (Row binding via the Google `sub` was dropped: Better Auth's account-update hook only receives the changed fields, so the row is unknown when a token is re-encrypted on a later sign-in.) A committed test vector (`web/db/test-vectors/token-encryption.json`: key, AAD, nonce, plaintext, expected output) SHALL be verified by tests on both sides.

#### Scenario: Tampered ciphertext or wrong key
- **WHEN** a `refresh_token_enc` value is altered, or decrypted with another environment's key
- **THEN** decryption fails

#### Scenario: Cross-language agreement
- **WHEN** the TypeScript and Python test suites run
- **THEN** both reproduce the test vector's output and decrypt it back to the plaintext

### Requirement: MCP access-token format
An MCP access token SHALL be a JWT issued by `web/` (Better Auth `jwt()` + `@better-auth/mcp`), signed with ES256, with public keys at the web origin's JWKS endpoint (advertised as `jwks_uri` in the authorization-server metadata). Claims the MCP server relies on: `iss` = the authorization server's issuer (an env value on both sides), `aud` containing exactly one MCP URL `<MCP_PUBLIC_URL>/<mcp_slug>` (Better Auth may add its own userinfo endpoint when identity scopes were granted; the MCP server ignores entries outside `MCP_PUBLIC_URL`), `sub` = `users.id`, `exp` ≤ 1 hour after `iat`. The MCP server SHALL accept a token only when the signature, `iss` and `exp` are valid, the one MCP URL in `aud` equals the URL the request was made to, the `ad_accounts` row with that `mcp_slug` belongs to `sub`, is enabled, and its connection is not revoked. Tokens are never stored or displayed by the cabinet.

#### Scenario: Token for one account used on another account's URL
- **WHEN** a token with `aud` = `…/mcp/aaaa` is sent to `…/mcp/bbbb`, even by the same user
- **THEN** the MCP server rejects it with 401

#### Scenario: Account removed
- **WHEN** an account is removed in the cabinet while Claude still holds an unexpired token for its URL
- **THEN** the MCP server finds no row for the slug and rejects the token

### Requirement: Fixes-log header contract
`web/db/contracts/fixes-log-header.json` SHALL hold the ordered column names of the fixes-log `Fixes` tab. `web/` writes it as the header of every sheet it creates; the MCP server SHALL load the same file (in Phase C, replacing its hardcoded `HEADER`) and a test on each side SHALL fail if its code disagrees with the file.

#### Scenario: A column is added
- **WHEN** someone adds a column to the MCP server's fixes-log code without updating the contract
- **THEN** the Python contract test fails
