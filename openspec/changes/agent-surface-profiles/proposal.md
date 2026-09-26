## Why

The server exposes 366 tools and the agent sees far too many of them. Real
`tools/list` sizes, measured 2026-09-23 by rendering the MCP schemas of the
registered tools (`--groups all`, no lifespan): **all = 366 tools / 345,074
chars (~86k tokens)**; the `.mcp.json` default (`core,reporting,targeting,
assets`) = **153 tools / ~39k tokens**; `core` alone = 41 tools / ~13k.
There are no tool annotations, list responses have no size limit, nothing
tests the MCP surface itself, and exposure is fixed by a CLI flag at
process start. `remote_main.py`'s read-only guarantee rests on a comment
saying someone read every tool body.

Decisions this implements (`docs/ROADMAP.md`, 2026-09-21/23): D1 (surface
before backend), D2 (default profile of 60–80 tools; `read_only` derived),
D3 (profiles are named YAML sets; tenants get a profile *name* later), plus
the numeric ceilings accepted 2026-09-23 (500 rows per response;
`tools/list` ≤ 25k tokens for `manager`, ≤ 10k for `read_only`).

## What Changes

**Sides touched: mcp-server only.** No DB, no tenants, no change to how
writes execute (the write queue arrives in `hosted-multitenant-writes`).

- **Tool registry**: explicit per-tool classification (`read` /
  `ads_write` / `internal_write` / `local_only`, plus `destructive`).
  Annotations (`readOnlyHint`, `destructiveHint`) derive from it.
- **Profiles**: `tool_profiles.yaml` with `manager` (77 tools, ~20k tokens
  with annotations), `read_only` (computed from `manager`: 29 tools, ~8k;
  the earlier "33" came from a name heuristic the registry corrected) and
  `all`. Middleware filters both `tools/list` and `tools/call`.
  `main.py --profile` replaces `--groups`; `remote_main.py` switches to
  the `read_only` profile.
- **Response envelope**: list-returning reads return `{items, returned,
  truncated, warning}` with a 500-row cap; GAQL without `LIMIT` gets one.
- **Actionable errors**: hint table and transport-error mapping.
- **Surface tests**: golden `tools/list` per profile and size budgets.
- **Fixes found during analysis**: `page_size` accepted but never sent
  (v25 rejects it anyway); `README.md` says MIT, `LICENSE` is AGPL-3.0.

Non-goals: deleting any service code (coverage stays and is reachable via
`all`); renaming tools; the write queue; anything tenant-aware.

## Capabilities

### New Capabilities
- `tool-surface`: what the agent can see and call, how that is chosen, and how it is kept honest by tests.
- `tool-responses`: bounded response shapes and error messages that tell the agent what to do next.

### Modified Capabilities
<!-- None. -->

## Impact

- New: `src/tool_registry.py`, `src/tool_profiles.py`, `tool_profiles.yaml`, `src/middleware/tool_profile.py`, `scripts/dump_tools_list.py`, `tests/test_tool_surface.py`, `tests/golden/`.
- Changed: `main.py` (flag), `remote_main.py` (profile instead of hand-picked servers), `src/utils.py` (envelope, error hints), `src/services/metadata/search_service.py`, `src/services/metadata/google_ads_service.py`, `../.mcp.json`, `README.md`, `CLAUDE.md` ("CURRENT TASK" still says the goal is 1:1 exposure).
- Behaviour for the local operator: the default surface shrinks from 153 tools to 77. Writes still execute on call locally, exactly as they do today, until the queue lands.
