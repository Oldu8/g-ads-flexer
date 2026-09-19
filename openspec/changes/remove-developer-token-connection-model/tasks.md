## 1. Docs (done 2026-09-14)

- [x] 1.1 Rewrite `docs/PLATFORM_ARCHITECTURE.md`: dev-token facts, `google_connections` model, discovery, quota, Phase 0, Standard-access item.
- [x] 1.2 Update `mcp-server/CLAUDE.md`, `mcp-server/TRACKER.md` (dated entry), `mcp-server/README.md`, `mcp-server/.env.example`, `mcp-server/docs/CLIENT_ONBOARDING.md`, `mcp-server/docs/ACCOUNT_SWITCHING.md`, `mcp-server/account_registry.example.json`, `web/README.md`.

## 2. Phase 0 — Google unblockers (no code; operator)

- [ ] 2.1 Publish static homepage + privacy policy + terms on the product domain.
- [ ] 2.2 Complete brand verification for Cloud project `178951272716`; set consent-screen branding (name, logo, support email, links to 2.1).
- [ ] 2.3 Submit `adwords` sensitive-scope verification; record submission date in `TRACKER.md`.

## 3. mcp-server — credentials without a developer token

- [ ] 3.1 `src/sdk_client.py`: add `build_client(refresh_token, login_customer_id)` using `GoogleAdsClient.load_from_dict` with platform `client_id`/`client_secret` from env and a module-level `_SDK_DEVELOPER_TOKEN_PLACEHOLDER` constant (comment: required by SDK 31.2.0 validation only, ignored by Google since 2026-09-09). Keep `load_from_env` path for local `main.py`. Verify with `uv run pyright` and `uv run pytest tests/test_sdk_client.py`.
- [ ] 3.2 Add a per-request client cache keyed by `(google_connection_id, login_customer_id)` with TTL; expose `get_request_client()` that reads the `AccessToken` from `fastmcp.server.dependencies.get_access_token()`. Existing services keep calling `get_sdk_client()` locally; the hosted entrypoint swaps the resolver at startup.
- [ ] 3.3 Pin the SDK version and add a `TRACKER.md` note to check each `google-ads` release for `developer_token` leaving `_REQUIRED_KEYS`; when it does, delete the placeholder and the `.env` line.

## 4. mcp-server — TokenVerifier + hosted entrypoint (read-only)

- [ ] 4.1 `src/auth/db_token_verifier.py`: `TokenVerifier.verify_token` → hash lookup in `accounts` (join `google_connections`), returns `AccessToken` with `account_id, google_connection_id, customer_id, login_customer_id, tool_profile`; disabled/revoked → None. Unit-test with a stub DB.
- [ ] 4.2 `hosted_main.py` (third entrypoint): per-account FastMCP mount at `/mcp/<slug>` with the `read_only` profile (search, field metadata, recommendations read, audience insights, invoices, fixes-log tools, Ads-Editor-table proposal tool) and `instructions` = `accounts.context`.
- [ ] 4.3 Choke point enforcing the pinned account: reject/override any tool `customer_id` that differs from the token's `customer_id`; test that a mismatched id never produces an API call.
- [ ] 4.4 Fixes log: resolve the sheet from `accounts.fixes_sheet_id` on the hosted entrypoint; local `main.py` keeps `snapshots/account_sheets.json`.

## 5. mcp-server — quota accounting

- [ ] 5.1 Count operations at the choke point into `api_usage(account_id, day)` (Pacific-Time day; N per mutate request). Unit-test the counting.
- [ ] 5.2 Per-account daily/minute caps and the 90% project guard with the readable messages from the spec; operator alert (log + one email/webhook) once per day.
- [ ] 5.3 Small operator readout (CLI or SQL view) of 7-day average total ops for the Standard-access trigger.

## 6. DB contract (web owns migrations; agree before 4.x lands)

- [ ] 6.1 Migrations: `users`, `google_connections`, `accounts` (with `login_customer_id`, `tool_profile`, `context`, `fixes_sheet_id`, `bearer_token_hash`), `api_usage`, per `docs/PLATFORM_ARCHITECTURE.md` "Data model". Decide refresh-token encryption (Supabase Vault vs. app key) and record it there.

## 7. web — one-screen cabinet (Phase 2, after 2.x and 6.1)

- [ ] 7.1 Auth.js + Google provider requesting `adwords`; persist refresh token encrypted into `google_connections`.
- [ ] 7.2 Discovery: `list_accessible_customers` + `customer_client` walk (REST from Next.js unless a blocker appears); checkbox list → `accounts` rows with the `(customer_id, login_customer_id)` pair.
- [ ] 7.3 Per-account card: MCP URL + bearer token shown once, enable/disable, `context` textarea, `fixes_sheet_id` + service-account email to share with.

## 8. Standard access (Phase 4; not before the pilot reads positive)

- [ ] 8.1 Demo Google Ads account with realistic data + demo login for Google reviewers.
- [ ] 8.2 Product write-up: guarded writes (propose → approve) and fixes log as change control; field whitelist as RMF scope; RMF gap check for exactly those areas.
- [ ] 8.3 Submit when 7-day average ≥ ~7,500 ops/day or >30 daily-active accounts; record dates in `TRACKER.md`.
