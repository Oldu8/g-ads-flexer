## 1. Project and database

- [ ] 1.1 Next.js (App Router, TypeScript) in `web/`; Drizzle + `drizzle-kit`; env schema validated at startup (`DATABASE_URL`, `AUTH_SECRET`, `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, `TOKEN_ENCRYPTION_KEY`, `MCP_PUBLIC_URL`, `SHEETS_SERVICE_ACCOUNT_EMAIL`).
- [ ] 1.2 Drizzle schema for every table in `platform-schema` (including `pending_changes`, `api_usage` and the `api_usage_daily_totals` view that only Python uses); generate SQL migrations; the migrations table lives in each schema, not in a shared one.
- [ ] 1.3 `web/db/roles.sql` (run once by the operator): schemas `app`/`app_dev`, roles `web_prod`/`mcp_prod`/`web_dev`/`mcp_dev`, `search_path` per role, grants exactly as in the spec. `web/db/README.md`: how to apply migrations to each schema.
- [ ] 1.4 `web/lib/crypto.ts`: AES-256-GCM `encryptToken`/`decryptToken` in the `v1.` format; commit `web/db/test-vectors/token-encryption.json`; tests that reproduce and round-trip it.
- [ ] 1.5 Grant tests (run against `app_dev` when `DATABASE_URL` is set, skipped otherwise): `mcp_dev` cannot read `sessions` or anything in `app`.

## 2. Sign-in

- [ ] 2.1 Auth.js v5 with the Drizzle adapter on the custom tables; Google provider with the `adwords` scope, offline access, `prompt=consent`.
- [ ] 2.2 Adapter wrapper: encrypt on `linkAccount`, overwrite `refresh_token_enc` and clear `revoked_at` on a sign-in that returns a new refresh token, never persist plaintext tokens. Test with a fake adapter.

## 3. Discovery and accounts

- [ ] 3.1 `web/lib/google-ads.ts`: mint an access token from the refresh token; `listAccessibleCustomers`; `customer_client` walk per manager; flatten. Unit-test the flattening with recorded responses (direct account, manager with children, nested manager, disabled child).
- [ ] 3.2 Discovery page: checkbox list of offered accounts; saving creates or updates `ad_accounts` (unique per connection + customer), never deletes on its own.
- [ ] 3.3 Account page: token generate/regenerate (`gam_` format, sha256 hex stored, shown once), MCP URL + copyable client snippet, enabled toggle, "allow changes" toggle → `tool_profile`, `context` (server-side 2,000-char check), `fixes_sheet_id` + service-account email. Every query scoped by the session user; test the "someone else's id" case.

## 4. Deploy

- [ ] 4.1 Railway service for `web/` (prod schema roles and keys; `AUTH_GOOGLE_ID` must equal the MCP server's `GOOGLE_ADS_CLIENT_ID`); the operator registers OAuth redirect URIs for localhost and the Railway domain and adds pilot emails as test users.
- [ ] 4.2 `web/README.md` rewritten: what exists, how to run locally against `app_dev`, how to migrate.
- [ ] 4.3 Verify end to end on `app_dev`: the operator signs in, discovers their accounts, exposes one, generates a token; the row matches the spec (no plaintext tokens, correct `login_customer_id`).
