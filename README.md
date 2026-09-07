# Google Ads AI platform (name TBD)

A monorepo with two parts:

- [`mcp-server/`](./mcp-server/) — Python. A Google Ads MCP server: ~100
  MCP tools giving an LLM full, typed access to the Google Ads API. See
  [`mcp-server/README.md`](./mcp-server/README.md) for setup and usage.
- `web/` — Next.js (not started yet). The product surface: landing page,
  login, account dashboard, per-account MCP endpoint + bearer-token
  issuance.

See [`docs/PLATFORM_ARCHITECTURE.md`](./docs/PLATFORM_ARCHITECTURE.md) for
the full multi-tenant architecture and phased build plan, and
[`CLAUDE.md`](./CLAUDE.md) for why the repo is split this way.
