# web (not started)

Next.js app — the product surface for the platform described in
[`../docs/PLATFORM_ARCHITECTURE.md`](../docs/PLATFORM_ARCHITECTURE.md).

Planned scope (see that doc for the full picture):

- Landing page, pricing, blog (SEO), terms of use, privacy policy
- Login via Google OAuth (Auth.js + Google provider), requesting the
  `adwords` scope in the same consent grant used to identify the user.
  No developer token, no MCC prerequisite (Google removed the developer
  token on 2026-09-09; access level lives on our Cloud project)
- Dashboard (one screen for the MVP): account discovery via
  `list_accessible_customers` + a `customer_client` walk, checkboxes for
  which accounts to expose, bearer token + MCP URL per account, a
  per-account business-context textarea, and the fixes-log Google Sheet
  id per account (one sheet per client per ad account)
- Phase 0, before any of the above: static homepage + privacy policy +
  terms, needed for Cloud-project brand verification and `adwords`
  scope verification
- Not in the MVP: pricing page, billing, blog
- Owns the Postgres (Supabase) schema — the Python MCP server
  (`../mcp-server/`) only reads from it, never writes

Nothing here yet — set up the Next.js project in this directory when
starting Phase 2.
