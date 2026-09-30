# web

The Next.js side of the platform (working name **adsmigo**): public pages,
Google sign-in, the user's cabinet, the OAuth authorization server MCP
clients (Claude Desktop) sign in through, and later an operator-only admin.
It shares one Postgres database with `../mcp-server/` and owns its schema.

Plan and status: [`../docs/ROADMAP.md`](../docs/ROADMAP.md), web tracks B0–B6.
Contracts: [`../openspec/specs/platform-schema/`](../openspec/specs/platform-schema/spec.md) and
[`../openspec/specs/account-connection/`](../openspec/specs/account-connection/spec.md).

| Track | Status |
|---|---|
| B0 skeleton: Next.js + Tailwind, routes, Railway, domain | done |
| B1 database and Google sign-in | done |
| B2 cabinet: discovery, one MCP URL per account, OAuth for Claude, fixes-log sheets | done |
| B3 landing · B4 legal pages · B5 admin · B6 blog | planned |

## What exists

- `/login` — Google sign-in (Better Auth) asking for `adwords` and
  `drive.file` offline; the refresh token is stored AES-256-GCM encrypted.
- `/app` — the user's ad accounts. `/app/discover` — live discovery over the
  Google Ads REST API (accessible customers + `customer_client` walk); adding
  an account gives it an MCP URL `<MCP_PUBLIC_URL>/<slug>`, an OAuth resource
  row for that URL and a fixes-log Google Sheet in the user's Drive.
- `/app/accounts/[id]` — MCP URL and Claude Desktop steps, connected
  assistants (disconnect), on/off, allow changes (`tool_profile`), business
  context, fixes log, remove.
- OAuth for MCP clients (`@better-auth/mcp` + `jwt()`): metadata at
  `/.well-known/oauth-authorization-server`, open dynamic client
  registration, `/oauth/consent`, ES256 JWTs (1 h) whose `aud` is one
  account's MCP URL, JWKS at `/api/auth/jwks`. Only the user's own enabled
  accounts can be authorized (checked at consent and at every token issuance).

## Run locally

```bash
cp .env.example .env.local   # fill in; see db/README.md for the database
npm install
npm run db:migrate           # app_dev
npm run dev                  # http://localhost:3000
```

Checks: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.

`npm run check:oauth` (with `npm run dev` running) walks the whole MCP OAuth
flow against `app_dev` without a browser: it seeds two throwaway users,
registers a client, consents, exchanges and verifies the token, checks the
refusals and deletes what it created. It refuses to run against anything but
localhost and `app_dev`, and never prints tokens.

## Database

Schema, roles and migrations: [`db/README.md`](./db/README.md).

## Deploy

Railway project `adsmigo`, service `web`, region EU West (Amsterdam),
configured by `railway.json` (Railpack, `npm start`, health check
`/api/health`). Served at `https://ads.vtrata.com` (Cloudflare: CNAME +
`_railway-verify` TXT, DNS only) and `https://web-production-0e5a7.up.railway.app`.
Variables: see `.env.example` (`MCP_PUBLIC_URL=https://ads-mcp.vtrata.com/mcp`
in prod).

Deploys are manual for now, from this directory: migrate first with
`npm run db:migrate:prod`, then `railway up --service web --ci`.
Once GitHub is connected in the Railway UI (source `Oldu8/g-ads-flexer`,
branch `main`, root directory `/web`), pushes to `main` deploy automatically.
