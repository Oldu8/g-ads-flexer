# Google Ads AI platform (name TBD)

An AI PPC assistant for Google Ads with guardrails and memory, delivered
over MCP. A monorepo with two apps that meet only in one Postgres database:

- [`mcp-server/`](./mcp-server/) — Python. The Google Ads MCP server (366
  typed tools over the Google Ads API, exposed through curated profiles).
- [`web/`](./web/) — Next.js. Sign-in with Google, account discovery,
  per-account MCP token. Not started yet.

Start with [`docs/ROADMAP.md`](./docs/ROADMAP.md) (what is being built and in
what order) and [`docs/PLATFORM_ARCHITECTURE.md`](./docs/PLATFORM_ARCHITECTURE.md)
(how it works).
