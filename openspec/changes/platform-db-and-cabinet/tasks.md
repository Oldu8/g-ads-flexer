## 1. Project and database

- [x] 1.1 Next.js (App Router, TypeScript) in `web/` (track B0); Drizzle + `drizzle-kit`; required env read through `requiredEnv` (`DATABASE_URL`, `BETTER_AUTH_URL`, `BETTER_AUTH_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`; `MCP_PUBLIC_URL` and `SHEETS_SERVICE_ACCOUNT_EMAIL` arrive with B2).
- [x] 1.2 Drizzle schema for every table in `platform-schema` (including `pending_changes`, `api_usage` and the `api_usage_daily_totals` view that only Python uses); generate SQL migrations; the migrations table lives in each schema, not in a shared one.
- [x] 1.3 `web/db/setup-roles.mjs` (`npm run db:setup-roles`): schemas `app`/`app_dev`, roles `web_prod`/`web_dev` (owners) and `mcp_prod`/`mcp_dev` (NOLOGIN until Phase C), `search_path` per role; passwords go to `.env.local` / Railway, never to the console. Migrations: `npm run db:generate` (strips `"public".`), `npm run db:migrate`.
- [x] 1.4 `web/src/lib/token-crypto.ts`: AES-256-GCM `encryptToken`/`decryptToken` in the `v1.` format; commit `web/db/test-vectors/token-encryption.json`; tests that reproduce and round-trip it.
- [ ] 1.5 Grant tests: moved to Phase C together with the MCP role grants.

## 2. Sign-in

- [x] 2.1 Better Auth with the Drizzle adapter on the custom tables; Google provider with the `adwords` scope, offline access, `prompt=select_account consent`.
- [x] 2.2 Account database hooks: encrypt the refresh token, never persist access/id tokens, clear `revoked_at` on sign-in. Unit-tested (`protectTokens`).
- [ ] 2.3 Live check on `app_dev` and prod: run `db:setup-roles` and `db:migrate`, sign in with Google, confirm the `google_connections` row (ciphertext only, `adwords` in `scope`).

## 3. Discovery and accounts

- [ ] 3.1 `web/lib/google-ads.ts`: mint an access token from the refresh token; `listAccessibleCustomers`; `customer_client` walk per manager; flatten. Unit-test the flattening with recorded responses (direct account, manager with children, nested manager, disabled child).
- [ ] 3.2 Discovery page: checkbox list of offered accounts; saving creates or updates `ad_accounts` (unique per connection + customer), never deletes on its own.
- [ ] 3.3 Account page: token generate/regenerate (`gam_` format, sha256 hex stored, shown once), MCP URL + copyable client snippet, enabled toggle, "allow changes" toggle → `tool_profile`, `context` (server-side 2,000-char check), `fixes_sheet_id` + service-account email. Every query scoped by the session user; test the "someone else's id" case.

## 4. Deploy

- [ ] 4.1 Railway service for `web/` (prod schema roles and keys; `AUTH_GOOGLE_ID` must equal the MCP server's `GOOGLE_ADS_CLIENT_ID`); the operator registers OAuth redirect URIs for localhost and the Railway domain and adds pilot emails as test users.
- [ ] 4.2 `web/README.md` rewritten: what exists, how to run locally against `app_dev`, how to migrate.
- [ ] 4.3 Verify end to end on `app_dev`: the operator signs in, discovers their accounts, exposes one, generates a token; the row matches the spec (no plaintext tokens, correct `login_customer_id`).
