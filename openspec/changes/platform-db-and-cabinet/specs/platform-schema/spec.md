## Purpose

The single contract between `web/` and `mcp-server/`: the tables, which side reads or writes each one, how prod and dev are separated inside one Supabase project, and the exact byte formats both languages must agree on (encrypted refresh tokens, bearer-token hashes).

## ADDED Requirements

### Requirement: Tables
Migrations in `web/` SHALL create these tables with unqualified names, resolved through the migrating role's `search_path`; generated SQL SHALL NOT name a schema (`db/unqualify-migrations.mjs` strips the `"public".` drizzle-kit adds, and a test enforces it). IDs are UUIDs (Better Auth `generateId: "uuid"`).

- `users`, `sessions`, `verifications`: Better Auth's `user`, `session`, `verification` models (snake_case columns).
- `google_connections`: Better Auth's `account` model under this name: `id`, `user_id`, `account_id` (Google `sub`), `provider_id`, `access_token`, `refresh_token_enc` (Better Auth field `refreshToken`), `id_token`, `access_token_expires_at`, `refresh_token_expires_at`, `scope`, `password`, `created_at`, `updated_at`, plus `revoked_at`; unique `(provider_id, account_id)`. `refresh_token_enc` only ever holds ciphertext; `access_token` and `id_token` SHALL always be NULL.
- `ad_accounts`: `id uuid pk`, `user_id` → `users`, `google_connection_id` → `google_connections.id`, `customer_id text` (10 digits, no dashes), `login_customer_id text null`, `display_name text`, `enabled bool default true`, `tool_profile text default 'read_only' check in ('read_only','manager')`, `context text default '' check (length ≤ 2000)`, `fixes_sheet_id text null`, `bearer_token_hash text unique null`, `token_created_at timestamptz null`, `created_at`, `last_used_at`; unique `(google_connection_id, customer_id)`.
- `pending_changes`: `id text pk` (`pc_` + 12 hex), `ad_account_id` → `ad_accounts` (on delete cascade), `tool_name text`, `arguments jsonb`, `preview jsonb`, `validation text check in ('full','partial','none')`, `status text check in ('pending','applying','applied','failed','rejected','expired')`, `created_at`, `expires_at`, `decided_at null`, `result jsonb null`, `error text null`, `fixes_log_error text null`; index `(ad_account_id, status, created_at desc)`.
- `api_usage`: `ad_account_id` → `ad_accounts`, `day date` (quota day, America/Los_Angeles), `operations int default 0`, `last_call_at`; primary key `(ad_account_id, day)`; index on `day`.
- View `api_usage_daily_totals`: `day`, `total_operations`, `active_accounts`.

#### Scenario: One grant, several accounts
- **WHEN** a user's single Google connection reaches three ad accounts and the user exposes two
- **THEN** there is one `google_connections` row and two `ad_accounts` rows referencing it, each with its own `bearer_token_hash`

#### Scenario: Plaintext token never stored
- **WHEN** any sign-in completes
- **THEN** `google_connections.access_token` and `id_token` are NULL and `refresh_token_enc` holds a `v1.` ciphertext

### Requirement: Access by side
Table grants to the MCP roles are applied in Phase C (`hosted-multitenant-writes`), when the Python side starts using the database; until then `mcp_dev` / `mcp_prod` exist as NOLOGIN roles with `USAGE` on their schema only. The MCP server's role SHALL then have: `SELECT` on `ad_accounts` and `UPDATE (last_used_at)` on it; `SELECT (id, "userId", refresh_token_enc, revoked_at)` and `UPDATE (revoked_at)` on `google_connections`; `SELECT, INSERT, UPDATE` on `pending_changes` and `api_usage`; `SELECT` on `api_usage_daily_totals`. It SHALL have no access to `users`, `sessions` or `verification_tokens`. The web role owns the schema and runs migrations.

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

### Requirement: Bearer-token format
A bearer token SHALL be `gam_` followed by base64url of 32 random bytes. Only `sha256(token)` as lowercase hex SHALL be stored, in `ad_accounts.bearer_token_hash`. The token SHALL be displayed once, at issue; regenerating replaces the hash and immediately invalidates the old token.

#### Scenario: Regenerate
- **WHEN** the user regenerates the token for an account
- **THEN** requests with the old token fail authentication and requests with the new one succeed
