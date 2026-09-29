## This is a monorepo

Two independent apps, different stacks, sharing one Postgres database
(Supabase) as their only integration point:

- **`mcp-server/`** — Python. The Google Ads MCP server. Has its own
  `CLAUDE.md` with rules for that side — **read it before touching
  anything under `mcp-server/`**.
- **`web/`** — Next.js. Cabinet: Google sign-in, account discovery, one
  MCP URL per ad account, and the OAuth authorization server MCP clients
  (Claude Desktop) sign in through. Owns the database schema and every
  migration, including the tables the Python side writes to.

Why two stacks: the Google Ads SDK engine has to be Python; the product
surface (cabinet now, marketing pages later) is Next.js territory and the
user's own stack. They never call each other's APIs: `web/` writes
accounts and issues OAuth tokens, `mcp-server/` verifies those tokens
against `web/`'s public JWKS, reads the accounts and writes the queue and
usage tables.

## Where things are written down

| Question | Document |
|---|---|
| What are we building, in what order, what's decided, what's open? | `docs/ROADMAP.md` |
| How does the platform work? | `docs/PLATFORM_ARCHITECTURE.md` |
| Exactly what to implement (requirements, scenarios, tasks) | `openspec/changes/<change>/` |
| What happened and why, dated | `mcp-server/TRACKER.md` |
| What the tools can do for a marketer | `mcp-server/docs/CAPABILITIES.md` |

Don't create new planning docs next to these: extend the one that owns
the question. Work on a planned phase happens by applying its OpenSpec
change (`openspec/config.yaml` has the rules); when a change is done,
archive it under `openspec/changes/archive/`.

## Root-level things

- `.mcp.json` — launches the local MCP server via
  `uv run --directory mcp-server python main.py ...`. Needs
  `mcp-server/.env` (not committed); `mcp-server/scripts/verify_google_access.py
  --write-env .env` recreates it. In Phase C the stdio entrypoint is
  removed (ROADMAP D25) and `.mcp.json` points at an `http` URL
  `/mcp/<slug>` instead.
- `openspec/` — spec-driven change workflow (lean schema: proposal,
  specs, tasks).
