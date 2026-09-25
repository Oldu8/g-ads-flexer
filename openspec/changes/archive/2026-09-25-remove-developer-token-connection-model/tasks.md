## 1. Docs (done 2026-09-14)

- [x] 1.1 Rewrite `docs/PLATFORM_ARCHITECTURE.md`: dev-token facts, `google_connections` model, discovery, quota, Phase 0, Standard-access item.
- [x] 1.2 Update `mcp-server/CLAUDE.md`, `mcp-server/TRACKER.md` (dated entry), `mcp-server/README.md`, `mcp-server/.env.example`, `mcp-server/docs/CLIENT_ONBOARDING.md`, `mcp-server/docs/ACCOUNT_SWITCHING.md`, `mcp-server/account_registry.example.json`, `web/README.md`.

## Moved 2026-09-23

Sections 2–8 of the original checklist were re-planned in iteration 2 of
`docs/ROADMAP.md` and now live in dedicated changes; the `tenant-connection`
and `api-quota-accounting` specs moved with them (updated: `ad_accounts`,
caps 1,500/day and 60/min, transport-level pinning).

- 2.x Phase 0 (operator, no code) → `docs/ROADMAP.md`, Phase 0.
- 3.x, 4.x, 5.x (credentials, verifier, hosted entrypoint, quota) → `hosted-multitenant-writes`.
- 6.1, 7.x (DB contract, cabinet) → `platform-db-and-cabinet`.
- 8.x (Standard access) → Phase E; not specced yet.

Docs-only and complete; archived 2026-09-25.
