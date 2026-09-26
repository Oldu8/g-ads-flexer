# web

The Next.js side of the platform (working name **adsmigo**): public pages,
sign-in, the user's cabinet and an operator-only admin. It shares one
Postgres database with `../mcp-server/` and owns its schema.

Plan and status: [`../docs/ROADMAP.md`](../docs/ROADMAP.md), web tracks B0–B6.

| Track | Status |
|---|---|
| B0 skeleton: Next.js + Tailwind, routes, Railway, domain | done |
| B1 database and Google sign-in | next |
| B2 cabinet · B3 landing · B4 legal pages · B5 admin · B6 blog | planned |

## Run locally

```bash
cp .env.example .env.local
npm install
npm run dev          # http://localhost:3000
```

Checks: `npm run lint`, `npm run typecheck`, `npm run build`.

## Deploy

Railway project with a `web` service built from this directory
(`npm run build`, `npm start`, health check `/api/health`), served at
`https://ads.vtrata.com`. Variables: see `.env.example`.
