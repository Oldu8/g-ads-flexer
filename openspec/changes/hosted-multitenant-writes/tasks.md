## 1. Foundations

- [ ] 1.1 Dependencies `psycopg[binary,pool]`, `cryptography`. `src/db.py`: sync `ConnectionPool` from `DATABASE_URL` (role `mcp_dev` locally, `mcp_prod` deployed), small repositories for `ad_accounts`, `google_connections`, `pending_changes`, `api_usage`. Unit tests use in-memory fakes; tests marked `db` run against `app_dev` only when `DATABASE_URL` is set.
- [ ] 1.2 `src/crypto.py`: AES-256-GCM `v1.` decrypt/encrypt; test against `../web/db/test-vectors/token-encryption.json`.
- [ ] 1.3 ~~Upgrade `google-ads` (now 33.0.0) and remove `GOOGLE_ADS_DEVELOPER_TOKEN` everywhere~~ (done 2026-09-25). `src/tenant.py`: `Tenant` dataclass and contextvar. `src/sdk_client.py`: `build_client(refresh_token, login_customer_id)` via `GoogleAdsClient.load_from_dict` with the existing `GOOGLE_ADS_CLIENT_ID`/`GOOGLE_ADS_CLIENT_SECRET` (the platform OAuth client) and no developer token; `get_service(name)` with the `(connection, login_customer_id, name)` TTL cache and the interceptor installed. Test: no outgoing request carries a `developer-token` header.

## 2. Make services tenant-safe

- [ ] 2.1 Replace the `client` property body in all 99 services with `return get_service("<Name>Service")` (script-assisted, reviewed by diff). Remove `self._client`.
- [ ] 2.2 Tests: the two-tenants-in-sequence scenario, and an AST test that fails if any `src/services/` module assigns a service client to `self`.

## 3. Transport interceptor (`src/transport_guard.py`)

- [ ] 3.1 Pinning: compare `request.customer_id` with the tenant's; allowlist of customer-independent methods; abort with "account mismatch". Test with a fake channel.
- [ ] 3.2 Queuing flag: set `validate_only = True` on mutate requests; abort mutates without the field; record per-call validation outcome for the middleware. Test that no mutate goes out without `validate_only` while queuing.
- [ ] 3.3 Quota: operations per RPC, atomic daily increment with cap, in-memory per-minute window, project guard at 13,500 with one alert per day (`OPERATOR_ALERT_WEBHOOK_URL`). Readable errors. Tests for each scenario in `api-quota-accounting`.

## 4. Auth, tenancy, entrypoints

- [ ] 4.1 `src/auth/db_token_verifier.py` (hash lookup, enabled, not revoked, throttled `last_used_at`). Tests with a fake repository.
- [ ] 4.2 `src/middleware/tenant.py`: set the tenant contextvar from `get_access_token()` (hosted) or from the process-level tenant (stdio); pick the profile from `tool_profile` for the `agent-surface-profiles` middleware; strip `customer_id` from schemas and inject it on calls; synthetic `account_context` tool.
- [ ] 4.3 `hosted_main.py`: streamable HTTP at `/mcp`, `DbTokenVerifier`, middleware order: tenant → profile → write queue → error mapping. `main.py`: `MCP_ACCOUNT_TOKEN`, same stack over stdio, exits with a pointer to the cabinet when missing.
- [ ] 4.4 `invalid_grant` handling: set `revoked_at`, evict cached clients, reconnect message.

## 5. Write queue

- [ ] 5.1 `src/middleware/write_queue.py`: intercept `ads_write` calls, run with the queuing flag, store the row, return `{queued, change_id, validation, preview, next}`; no row when validation fails.
- [ ] 5.2 Rewrite `pending_change_service.py`: `list`, `get`, `apply` (atomic claim, tenant scope, expiry, run with the flag off, fixes-log best-effort), `reject`. Port the seven preview formatters to their tools. Delete `pending_change_store.py` and the `propose_*` tools; update the registry and golden snapshots.
- [ ] 5.3 End-to-end test with a fake transport: queue → nothing mutated → apply → exactly one real mutate; double apply; foreign `change_id`; expired row.

## 6. Fixes log, cleanup, deploy

- [ ] 6.1 Fixes log: sheet from `ad_accounts.fixes_sheet_id`; when missing, fixes-log tools say "no sheet configured; set it in the cabinet" and applies still succeed. Remove `account_sheets` resolution.
- [ ] 6.2 Remove `remote_main.py`, `account_registry_*` (service, store, server, example JSON), `account_sheets.example.json`, `GOOGLE_ADS_REFRESH_TOKEN` from `.env.example`. Update `../.mcp.json` (`MCP_ACCOUNT_TOKEN` in `env`), `README.md` (local setup = token from the cabinet), `../docs/PLATFORM_ARCHITECTURE.md` if anything built differs from it.
- [ ] 6.3 `Dockerfile` → `hosted_main.py`; Railway service with `mcp_prod` credentials, `TOKEN_ENCRYPTION_KEY` (prod), OAuth client id/secret, cap env vars.
- [ ] 6.4 `scripts/usage_report.py`.
- [ ] 6.5 Verify on `app_dev` with the operator's real account from the cabinet: read query; queued budget change with `validation: full`; apply; fixes-log row; a second tenant token cannot see or apply the first one's change. `uv run ruff format .`, `uv run pyright`, `uv run pytest` green. Dated `TRACKER.md` entry.
