## Why

Google removed the developer token from the Google Ads API on 2026-09-09. Access level now belongs to the Cloud project that owns the OAuth client (ours, `178951272716`, has Basic: 15,000 ops/day shared by every tenant), the header is ignored, and an MCC is no longer needed for API access. The multi-tenant plan was built on "one user = one MCC + one dev token" and on a per-tenant quota assumption; both are now wrong, and the code still carries the token through config, docs and every request.

## What Changes

**Sides touched: mcp-server, web (schema contract), DB.** No cross-side API — they meet only at Postgres.

- **mcp-server**: one client-builder function that takes `(refresh_token, login_customer_id)` and injects a placeholder `developer_token` only because `google-ads==31.2.0` still validates the key and sends the header (verified in `config.py` / `metadata_interceptor.py`); drop the token from `.env`-driven config once the SDK makes it optional. `sdk_client.py` singleton → per-request resolution keyed by `google_connection_id`. `TokenVerifier` returns `account_id, google_connection_id, customer_id, login_customer_id, tool_profile`. API-usage accounting + per-account/per-project caps at the same choke point.
- **DB (owned by web, read by mcp-server)**: `mcc_connections` → `google_connections` (no `dev_token` column); `accounts` gains `login_customer_id`, `tool_profile`, `context`, `fixes_sheet_id`, `bearer_token_hash`; new `api_usage`.
- **web**: onboarding is OAuth-only; account discovery = `list_accessible_customers` + `customer_client` walk, storing the `(customer_id, login_customer_id)` pair per exposed account. Phase 0 (homepage, privacy, terms, brand verification) precedes any dashboard code.
- **Docs**: `docs/PLATFORM_ARCHITECTURE.md` rewritten (done in this change); `mcp-server/CLAUDE.md`, `TRACKER.md`, `README.md`, `.env.example`, `docs/CLIENT_ONBOARDING.md`, `docs/ACCOUNT_SWITCHING.md`, `web/README.md` updated (done).

## Capabilities

### New Capabilities
- `tenant-connection`: how a tenant's Google Ads credentials are stored, resolved per request, and pinned to one ad account — without a developer token.
- `api-quota-accounting`: per-account operation counting and caps against the shared project-level Basic quota.

### Modified Capabilities
<!-- None: no existing spec covers these areas. -->

## Impact

- `mcp-server/src/sdk_client.py` — per-request builder + cache; placeholder constant is the only place the token survives.
- `mcp-server/remote_main.py` — unchanged; a new third entrypoint mounts the `read_only` profile per account.
- `mcp-server/tests/test_sdk_client.py` — fixture YAML keeps `developer_token` only while the SDK requires it.
- `web/` (not started) — schema/migrations per `docs/PLATFORM_ARCHITECTURE.md` "Data model".
