## Why

`list_campaign_draft_async_errors` silently swallows any exception raised while paginating the API response and returns an empty list instead. This makes a genuine failure (network blip, malformed page, transient API error) indistinguishable from a campaign draft that legitimately has zero async errors — the tool reports "Found 0 async errors" either way, which can mislead whoever (human or LLM) is deciding whether a draft is safe to promote.

## What Changes

- Replace the silent `except Exception: pass` around the pagination loop with a `ctx.log(level="warning", ...)` call that reports the exception, matching the existing pattern already used elsewhere in this codebase (e.g. `search_service.py`'s per-row fallback logging).
- No behavior change to the return value on success; only the failure path becomes observable.

## Capabilities

### New Capabilities
- `campaign-draft-management`: no spec exists yet for this area, so this change introduces the first requirement for it — async-error iteration failures must be observable (logged), never silently discarded.

### Modified Capabilities
<!-- None: openspec/specs/ has no existing capability spec to modify yet. -->

## Impact

- `mcp-server/src/services/campaign/campaign_draft_service.py`: `list_campaign_draft_async_errors` — log-and-continue instead of silent `pass` on pagination failure.
