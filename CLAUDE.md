## This is a monorepo

Two independent projects, different stacks, sharing one Postgres database
(Supabase-hosted) as their only integration point — see
[`docs/PLATFORM_ARCHITECTURE.md`](./docs/PLATFORM_ARCHITECTURE.md) for the
full plan (multi-tenant design, DB schema, auth flow, phased rollout)
before working on either side.

- **`mcp-server/`** — Python. The Google Ads MCP server: ~100 MCP tools
  wrapping the Google Ads API 1:1 (protobuf-typed), plus (in progress) the
  multi-tenant HTTP entrypoint that resolves per-account Google Ads
  credentials from Postgres per request. Has its own `CLAUDE.md` with the
  detailed rules/current task for this side — **read that before touching
  anything under `mcp-server/`**.
- **`web/`** — Next.js (not started yet). The product surface: landing
  page, pricing, blog (SEO), terms/privacy, login (Google OAuth via
  Auth.js — same grant used for both identifying the user and getting
  Google Ads API access), account dashboard, MCP address + bearer-token
  issuance. Owns the Postgres schema/migrations.

## Why two stacks, one database

Recorded 2026-09-07: the Python side is the Google Ads SDK engine and
can't be anything but Python. The web/product side is marketing-heavy
(SEO blog, landing pages) and login/dashboard UI — squarely Next.js
territory, and the user's own stack. Rather than force one language to do
both jobs badly, each repo does its own job well and they meet only at
the database: Next.js issues bearer tokens into a Postgres table when a
user connects an account, the Python MCP server's own `TokenVerifier`
(no JWT, no Supabase Auth dependency — a plain DB lookup) checks
incoming requests against the same table. Neither side calls the other's
API directly for this.

## Root-level things

- `.mcp.json` — launches the Python MCP server via
  `uv run --directory mcp-server python main.py ...` for local Claude
  Code use. Update the `--directory` flag, not the rest, if this ever
  needs to point somewhere else.
- `docs/` (this level) — cross-cutting planning docs that describe the
  whole platform, not just one side. `mcp-server/docs/` holds the
  Python-specific ones (capabilities, client onboarding, etc.).
