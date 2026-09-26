## Objective

A Python MCP server wrapping the Google Ads API (v25) for LLMs. Two layers:

- **Coverage (the library):** `src/services/` wraps Google Ads services
  1:1, fully typed with the SDK's generated protobuf types. 366 tools
  today. Keep coverage growing where it is useful.
- **Exposure (what the agent sees):** a curated **profile**, not
  everything. See `../docs/PLATFORM_ARCHITECTURE.md` ("Tool surface")
  and `openspec/changes/agent-surface-profiles/`. Adding a tool to a
  profile is a product decision with a token cost; adding a tool to the
  library is not.

We use the Python SDK (`google-ads`), not REST: it handles retries,
pagination and typing. The one exception is
`scripts/verify_google_access.py`, which uses REST on purpose so it can
control headers exactly.

## Google access facts (2026-09-09 onwards)

- **No developer token.** The access level belongs to the Cloud project
  that owns the OAuth client (ours: `178951272716`). The header is ignored
  now and will be rejected by a future major API version.
- The repo uses `google-ads` **33.0.0** (API v25.2); 32.0.0 was the first
  release that does not require `developer_token`. Never add a developer token back anywhere: no
  env var, no config key, no schema column.
- **No MCC needed** for API access; `login-customer-id` only when access
  goes through a manager.
- Verified against the live API on 2026-09-25 (operator identity) with
  `scripts/verify_google_access.py`; re-run it after any auth change.

## Resources

1. `./refs/googleads.llms.txt` — Google Ads API docs index.
2. `./refs/fastmcp.llms.txt` — FastMCP docs index. The installed version
   is 2.14.7; check the package source in `.venv` before relying on a
   feature from newer docs.
3. The installed `google-ads` package in `.venv` — SDK source and every
   generated type.

## Rules

1. `uv` for everything; see `pyproject.toml`.
2. After changes: `uv run --extra dev ruff format .`,
   `uv run --extra dev pyright`, `uv run --extra dev pytest`. (Without
   `--extra dev` these tools are not installed.)
3. New services and tools: fully typed with v25 generated types, with
   tests. Every new tool needs an entry in `src/tool_registry.py` (its kind
   and whether it is destructive); `tests/test_tool_surface.py` fails
   otherwise. Adding it to a profile in `tool_profiles.yaml` is a separate,
   deliberate decision: regenerate the golden snapshots with
   `scripts/dump_tools_list.py` in the same commit.
4. Never change a mount prefix in `src/server_factory.py`: prefixes are
   tool names, i.e. public API.
5. Never write scratch/output files (audit dumps, keyword lists, reports,
   id lists) into the project root. Use `./tmp/` (gitignored), named
   `YYYY-MM-DD_<account-or-campaign>_<what-it-is>.<ext>`, e.g.
   `2026-09-04_boo-ua_keyword-audit-90d.txt`. Never `git add` anything
   from it.
6. Record what you did and why as a dated entry at the top of
   `TRACKER.md`, so the next agent can pick it up.

## Current task

Implement the roadmap: `../docs/ROADMAP.md` gives the order;
each phase is an OpenSpec change under `../openspec/changes/` with its own
`tasks.md`. On this side: Phase A (`agent-surface-profiles`) is done
(2026-09-26); next is Phase C (`hosted-multitenant-writes`) once the cabinet
and database exist.
