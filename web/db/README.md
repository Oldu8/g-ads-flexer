# Database

One Supabase project, two schemas (ROADMAP D11): `app_dev` (local
development) and `app` (production), each owned by its own role. Tables
are unqualified; the role's `search_path` picks the schema, so one set of
migrations serves both.

| Environment | Schema | Owner (web) | MCP role | Where the credentials live |
|---|---|---|---|---|
| dev | `app_dev` | `web_dev` | `mcp_dev` | `web/.env.local` |
| prod | `app` | `web_prod` | `mcp_prod` | Railway service `web` variables |

## One-time setup

1. Put the Supabase **Session pooler** connection string of the `postgres`
   user into `ADMIN_DATABASE_URL` in `.env.local` (Supabase → Connect →
   Session pooler; replace `[YOUR-PASSWORD]`).
2. `npm run db:setup-roles` — creates schemas and roles, writes the dev
   `DATABASE_URL` to `.env.local` and sets the prod one on Railway. Passwords
   are never printed. Re-running is safe; `-- --rotate` issues new passwords.

## Migrations

- Change `src/db/schema.ts`, then `npm run db:generate` (drizzle-kit +
  `unqualify-migrations.mjs`, which strips the `"public".` drizzle-kit adds).
  Commit the SQL and `migrations/meta`.
- Apply: `npm run db:migrate` (dev) and `npm run db:migrate:prod` (prod,
  credentials injected by `railway run`).

## Token encryption

`test-vectors/token-encryption.json` pins the refresh-token format; the
Python MCP server must pass the same vector (Phase C).
