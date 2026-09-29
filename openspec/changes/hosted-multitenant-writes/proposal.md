## Why

With profiles (`agent-surface-profiles`) and real connected accounts (`platform-db-and-cabinet`) in place, the MCP server has to serve many tenants from one process, pin each request to one ad account, keep the shared 15,000-ops/day project quota alive, and, because the pilot includes writes (D4), make sure no write reaches Google without a queued, previewed and approved change.

Two facts found on 2026-09-23 change what `docs/PLATFORM_ARCHITECTURE.md` assumed:

1. **Services are not tenant-safe as they are.** 99 service classes cache their GAPIC client in `self._client` on first use, and each service is instantiated once per process. Under multi-tenancy, the first tenant's credentials would serve every later tenant. "The wrapped services don't change" is false; every one of them changes (mechanically).
2. **Per-tenant `instructions` are not possible in FastMCP 2.14.7.** `on_initialize` middleware only sees the `InitializeResult` after it has been sent. Account `context` is therefore delivered as a synthetic tool whose *description* is the context text, rewritten per tenant in `on_list_tools`.

One fact makes the write queue cheap: `GoogleAdsClient.get_service()` accepts gRPC `interceptors`, and every `Mutate*Request` has `customer_id` and `validate_only` (`ApplyRecommendationRequest` and `DismissRecommendationRequest` have no `validate_only`). One interceptor can therefore pin the account, force `validate_only` while queuing, and count quota for all 366 tools without editing any of them. None of the 44 write tools in `manager` passes `validate_only` today.

## What Changes

**Sides touched: mcp-server and DB (rows only; the schema comes from `platform-db-and-cabinet`).**

- Per-request credentials: upgrade `google-ads` to ≥ 32.0.0 (released 2026-09-09; `developer_token` is no longer a required config key and the header is only sent when set, verified 2026-09-25 by inspecting 32.0.0 and 33.0.0), a tenant contextvar, `build_client(refresh_token, login_customer_id)` with no developer token at all, a service-client cache keyed by `(google_connection_id, login_customer_id, service)`, and all services switched from `self._client` to it.
- A transport interceptor (the choke point): enforces the pinned `customer_id`, forces `validate_only` during queuing (refusing to send mutates that cannot be validated), and counts operations against caps.
- OAuth resource server (revised 2026-09-29, D22–D25): one path per account `/mcp/{mcp_slug}` with its own RFC 9728 metadata pointing at the web authorization server; ES256 JWTs verified against the web JWKS, `aud` = the request URL, owner/enabled/revoked checked in the DB per request. `hosted_main.py`, per-request profile from `ad_accounts.tool_profile`, `customer_id` removed from tool schemas and injected, the `account_context` tool.
- Unified write queue in Postgres for every `ads_write` tool; `apply`/`reject`; the seven `propose_*` tools and `snapshots/pending_changes.json` are removed.
- Quota: 1,500 ops/day and 60/min per account, stop at 90% of 15,000 for the project, one operator alert per day, 7-day readout.
- No local-token mode (D25): local development runs `hosted_main.py` on localhost against `app_dev`, with Claude Code doing OAuth against local `web/`. `main.py` (stdio), `remote_main.py`, `account_registry.json`, `account_sheets.json` and the Google refresh token in `.env` are deleted.
- Fixes log: the sheet the cabinet created (`fixes_sheet_id`), written with the connection's own grant (`drive.file`); header from `web/db/contracts/fixes-log-header.json`; the service account is removed.

Non-goals: RLS policies, a pending-change dashboard, token rotation history, Standard-access work, caching GAQL results.

## Capabilities

### New Capabilities
- `tenant-connection`: resolving credentials per request and pinning each request to one ad account (moved here from `remove-developer-token-connection-model` and updated).
- `api-quota-accounting`: counting and capping operations against the shared project quota (moved and updated: caps 1,500/60 instead of 1,000/30).
- `write-queue`: every Google Ads write is queued, validated where Google allows it, and applied only by `apply_pending_change`.

### Modified Capabilities
<!-- None in openspec/specs. `tool-surface` (from agent-surface-profiles) gains a per-request profile source; noted in its middleware task rather than as a delta, since that change is not archived yet. -->

## Impact

- New: `src/db.py`, `src/crypto.py`, `src/tenant.py`, `src/transport_guard.py`, `src/auth/account_token_verifier.py` (JWT + DB checks, per-path metadata), `src/middleware/tenant.py`, `src/middleware/write_queue.py`, `hosted_main.py`.
- Changed: `src/sdk_client.py`, the `client` property of all 99 services, `src/services/review/pending_change_service.py` (rewritten), `src/services/review/fixes_log_*` (sheet from the DB), `Dockerfile`, `.env.example`, `../.mcp.json`, `README.md`, `pyproject.toml`/`uv.lock` (SDK upgrade).
- Removed: `main.py`, `remote_main.py`, `GOOGLE_SHEETS_*` service-account settings, `src/services/review/pending_change_store.py`, `src/services/review/account_registry_*`, `account_registry.example.json`, `account_sheets.example.json`, the seven `propose_*` tools.
- Dependencies: `psycopg[binary,pool]` (sync pool: services and gRPC interceptors are synchronous already), `cryptography`.
