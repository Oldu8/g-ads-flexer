## 1. Project and database

- [x] 1.1 Next.js (App Router, TypeScript) in `web/` (track B0); Drizzle + `drizzle-kit`; required env read through `requiredEnv` (`DATABASE_URL`, `BETTER_AUTH_URL`, `BETTER_AUTH_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`; `MCP_PUBLIC_URL` arrives with B2).
- [x] 1.2 Drizzle schema for every table in `platform-schema` (including `pending_changes`, `api_usage` and the `api_usage_daily_totals` view that only Python uses); generate SQL migrations; the migrations table lives in each schema, not in a shared one.
- [x] 1.3 `web/db/setup-roles.mjs` (`npm run db:setup-roles`): schemas `app`/`app_dev`, roles `web_prod`/`web_dev` (owners) and `mcp_prod`/`mcp_dev` (NOLOGIN until Phase C), `search_path` per role; passwords go to `.env.local` / Railway, never to the console. Migrations: `npm run db:generate` (strips `"public".`), `npm run db:migrate`.
- [x] 1.4 `web/src/lib/token-crypto.ts`: AES-256-GCM `encryptToken`/`decryptToken` in the `v1.` format; commit `web/db/test-vectors/token-encryption.json`; tests that reproduce and round-trip it.
- [ ] 1.5 Grant tests: moved to Phase C together with the MCP role grants.

## 2. Sign-in

- [x] 2.1 Better Auth with the Drizzle adapter on the custom tables; Google provider with the `adwords` scope, offline access, `prompt=select_account consent`.
- [x] 2.2 Account database hooks: encrypt the refresh token, never persist access/id tokens, clear `revoked_at` on sign-in. Unit-tested (`protectTokens`).
- [x] 2.3 Live check on `app_dev` and prod (done 2026-09-28: operator signed in on ads.vtrata.com; row has `v1.` ciphertext, null access/id tokens, `adwords` scope): run `db:setup-roles` and `db:migrate`, sign in with Google, confirm the `google_connections` row (ciphertext only, `adwords` in `scope`).

## 3. Discovery, accounts, fixes log

- [x] 3.1 Schema: `ad_accounts.mcp_slug` (unique, not null), drop `bearer_token_hash`/`token_created_at`; the OAuth tables of `@better-auth/oauth-provider` + `jwt()` in `src/db/schema.ts` (snake_case, generated with the Better Auth CLI as a reference); migration.
- [x] 3.2 `web/src/lib/google-ads.ts`: mint an access token from the refresh token; `listAccessibleCustomers`; `customer_client` walk per manager; flatten and dedupe (direct wins, then lowest level). Unit-test with recorded responses (direct account, manager with children, nested manager, disabled child, account reached twice).
- [x] 3.3 `web/src/lib/fixes-sheet.ts` + `web/db/contracts/fixes-log-header.json`: create the spreadsheet (title, `Fixes` tab, frozen bold header) and probe an existing one (ok / missing / no scope). Tests with a fake fetch; a test that the contract equals the MCP server's current `HEADER`.
- [x] 3.4 `/app/discover`: live discovery grouped by manager; saving creates `ad_accounts` rows with `mcp_slug`, their `oauth_resources` rows and sheets; never deletes. `/app`: account list.
- [x] 3.5 `/app/accounts/[id]`: MCP URL + Claude Desktop steps, connected clients + Disconnect, enabled, allow changes, `context` (server-side 2,000-char check), fixes log (link / grant access / create new), Remove account. Every query scoped by the session user; test the "someone else's id" case.

## 4. OAuth for MCP clients

- [x] 4.1 Better Auth: `jwt()` with ES256, `@better-auth/mcp` (`resource` = `MCP_PUBLIC_URL`, per-account resources from the DB with `enforcePerClientResources: false`, open DCR for public clients, access tokens 1 h, rotating refresh tokens, `loginPage: /login`, `consentPage: /oauth/consent`); root `/.well-known/oauth-authorization-server` (+ path-suffixed and `openid-configuration`) routes; `drive.file` added to the Google scopes. New env: `MCP_PUBLIC_URL`.
- [x] 4.2 Resource check: disabled resources refused at authorize, foreign ones on the consent page and by a `/oauth2/consent` hook (403), and in `customAccessTokenClaims` at every issuance. `/login` resumes a pending authorization after Google sign-in (client plugin forwards the signed query). Loopback-only registrations become `native`; the canonical resource row is inserted in `instrumentation.ts` (cold-start seeding race).
- [x] 4.3 `/oauth/consent`: client name, account, what it allows; Allow / Deny.
- [x] 4.4 Tests: metadata advertises S256, `none` auth, registration and JWKS endpoints; foreign and disabled resources are refused; issued token claims (`aud`, `sub`, `iss`, ES256 header). Done as `npm run check:oauth` (`scripts/oauth-dev-check.mjs`, 14 checks against a local server and `app_dev`), plus unit tests for discovery, MCP URLs and the sheet.

## 5. Deploy and verify

- [x] 5.1 Railway service for `web/` (B0/B1). Operator console work done 2026-09-29: Drive and Sheets APIs enabled, `drive.file`/`adwords` declared, consent screen in Production.
- [x] 5.2 `MCP_PUBLIC_URL=https://ads-mcp.vtrata.com/mcp` on Railway, `db:migrate:prod` (0002, 0003), deployed 2026-09-29/30.
- [x] 5.3 `web/README.md` rewritten: what exists, how to run locally against `app_dev`, how to migrate.
- [x] 5.4 Live check on prod with the operator's account (2026-09-30): re-sign-in; discovery; account boo.ua (569-031-8342) added with `mcp_slug`, `login_customer_id = NULL` (direct access), OAuth resource row; fixes-log sheet created in the operator's Drive (after fixing stale `scope`: Better Auth does not update it on a repeat sign-in, now synced from Google's token response); `web/scripts/oauth-smoke.mjs`: DCR → consent in the browser → PKCE exchange → ES256 JWT verified against the JWKS, `aud` = the account URL (+ userinfo), `sub` = the operator, 3600 s, refresh token issued; "Disconnect" deleted the consent and revoked the refresh token. End-to-end with Claude Desktop is the first live step of Phase C (it needs the MCP server).
