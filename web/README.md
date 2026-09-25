# web (not started)

The Next.js side of the platform. Phase B of [`../docs/ROADMAP.md`](../docs/ROADMAP.md);
full spec in [`../openspec/changes/platform-db-and-cabinet/`](../openspec/changes/platform-db-and-cabinet/).

Scope of the first version (a minimal cabinet, nothing else):

- Sign-in with Google (Auth.js v5). The same consent grants the `adwords`
  scope, offline. The refresh token is stored AES-256-GCM encrypted only.
- Account discovery over the Google Ads REST API
  (`listAccessibleCustomers` + a `customer_client` walk), a checkbox list,
  one `ad_accounts` row per exposed account.
- Per account: bearer token shown once, MCP URL, enabled, "allow changes"
  (`read_only` / `manager`), business context, fixes-log sheet id.

This app **owns the database schema and every migration** (Drizzle),
including `pending_changes` and `api_usage`, which the Python MCP server
writes to. Deployed on Railway. It must use the same Google OAuth client
as the MCP server.

Not in the first version: landing page, pricing, blog, billing, a
pending-change dashboard.
