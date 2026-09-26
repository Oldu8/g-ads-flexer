## 1. Fixes found during analysis

- [x] 1.1 `src/services/metadata/google_ads_service.py`: remove `page_size` from `search` (signature, docstring, tool schema). Add a unit test with a fake multi-page pager proving what `search` returns today (the pager probably exposes page one only through `response.results`), then make it iterate through the envelope from 3.2.
- [x] 1.2 `README.md`: the closing "MIT © Promobase" line → AGPL-3.0, matching the badge, `LICENSE` and `NOTICE.md` (done 2026-09-25 in the docs consolidation).

## 2. Measure first

- [x] 2.1 `scripts/dump_tools_list.py --profile <name> --out <file>`: renders the real `tools/list` without running the lifespan (no credentials needed). Starting point: `mcp-server/tmp/dump_tools.py` from 2026-09-23 (patches `load_dotenv`, imports `main`, calls `get_tools()` then `to_mcp_tool()`).
- [x] 2.2 `tests/test_tool_surface.py`: unique names, non-empty descriptions, golden snapshot per profile under `tests/golden/`, size budgets (`manager` ≤ 100,000 chars, `read_only` ≤ 40,000) in one constant; on failure, print the size and the three largest tools.

## 3. Registry, envelope, errors

- [x] 3.1 `src/tool_registry.py`: one entry per registered tool (366 today). Generate the first draft from `tmp/2026-09-23_tool-inventory.json`, then review by hand; the five known heuristic misses are listed in the spec. Test: every registered tool has an entry and every entry is a registered tool.
- [x] 3.2 `src/utils.py`: `list_envelope(rows_iter, cap)` with the `cap + 1` probe and the warning text; `GOOGLE_ADS_MCP_ROW_CAP` (default 500). Apply it to every list-returning `read` tool in `manager` (18 reads + the list tools in assets/targeting/audiences). `search_execute_query`: append `LIMIT cap+1` when the query has no `LIMIT`. Tests for both scenarios.
- [x] 3.3 Error hints: hint table module, `format_ads_error` appends `hint`, transport mapping (`invalid_grant`, `DEADLINE_EXCEEDED`/`UNAVAILABLE`, `RESOURCE_EXHAUSTED`). Seed from `TRACKER.md` incidents. Tests per mapping.

## 4. Profiles

- [x] 4.1 `tool_profiles.yaml` (`manager` = the 77 tools in the spec, `all`), `src/tool_profiles.py` (load, validate names against the registry and fail on unknown, compute `read_only`).
- [x] 4.2 `src/middleware/tool_profile.py`: filter `on_list_tools` and `on_call_tool`; attach annotations from the registry in `on_list_tools`. The profile is a constructor argument now; `hosted-multitenant-writes` will make it per-request.
- [x] 4.3 `main.py`: `--profile` (default `manager`) replaces `--groups`; mount every server, filter via middleware. `../.mcp.json` → `--profile manager`.
- [x] 4.4 `remote_main.py`: mount everything and apply the `read_only` profile via the middleware; delete the hand-picked server list and the comment that carried the guarantee.
- [x] 4.5 Regenerate the golden snapshots; confirm `manager` = 77 tools (~20k tokens measured) and `read_only` = 29 (~8k); record the three duplicate winners and the ETA exclusion in `TRACKER.md`.

## 5. Docs and verification

- [x] 5.1 `CLAUDE.md` "CURRENT TASK": coverage keeps growing as a library, exposure is chosen by profiles. `docs/CAPABILITIES.md`: add the profile concept. Dated `TRACKER.md` entry with the before/after numbers.
- [x] 5.2 `uv run ruff format .`, `uv run pyright`, `uv run pytest` are all green.

## Notes from implementation (2026-09-26)

- The list envelope (3.2) is applied once, in `ToolProfileMiddleware`, to
  every `read` tool whose output schema is a wrapped list (it also rewrites
  that tool's advertised output schema), instead of editing ~20 tool
  functions. `search_execute_query` additionally gets `LIMIT cap+1`.
- Server construction moved from `main.py` into `src/server_factory.py`
  (`create_server(profile, ...)`), shared by `main.py`, `remote_main.py`,
  the tests and `scripts/dump_tools_list.py`; Phase C's `hosted_main.py`
  reuses it.
- `google_ads_search_google_ads` (not in `manager`) returns the first
  10,000-row page capped at the row cap; when that page is truncated its
  `next_page_token` is withheld, because continuing from it would skip the
  rest of the page.
- Live-checked on boo.ua over stdio: 77 tools listed, a 310-row GAQL result
  enveloped, and Google's real "Unrecognized field 'campaign.start_date'"
  error returned with the v25 hint.
