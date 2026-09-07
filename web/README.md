# web (not started)

Next.js app — the product surface for the platform described in
[`../docs/PLATFORM_ARCHITECTURE.md`](../docs/PLATFORM_ARCHITECTURE.md).

Planned scope (see that doc for the full picture):

- Landing page, pricing, blog (SEO), terms of use, privacy policy
- Login via Google OAuth (Auth.js + Google provider), requesting the
  `adwords` scope in the same consent grant used to identify the user
- Dashboard: shows the accounts under the user's linked MCC, lets them
  pick which ones to expose, issues a bearer token + MCP URL per account
- Owns the Postgres (Supabase) schema — the Python MCP server
  (`../mcp-server/`) only reads from it, never writes

Nothing here yet — set up the Next.js project in this directory when
starting Phase 2.
