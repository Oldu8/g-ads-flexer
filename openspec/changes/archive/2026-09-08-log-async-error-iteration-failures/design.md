## Context

See proposal.md - Why. The fix is confined to one method, `list_campaign_draft_async_errors`, in `mcp-server/src/services/campaign/campaign_draft_service.py`.

## Goals / Non-Goals

**Goals:**
- Make pagination failures during async-error listing observable via a log line, without changing the method's return type or success-path behavior.

**Non-Goals:**
- Reworking how async errors are parsed/serialized from the API response (the existing "simplified implementation" comment stands - out of scope here).
- Changing what happens on `GoogleAdsException` (the outer try/except already handles and re-raises that correctly).

## Decisions

### Log at `warning` level instead of raising

The pagination failure is caught and logged rather than re-raised, matching the existing convention in `search_service.py`'s per-row fallback (catch, `ctx.log(level="warning", ...)`, continue). Raising instead was considered and rejected: this inner loop is deliberately isolated from the outer `except GoogleAdsException` handler because an iteration failure isn't necessarily a Google Ads API error - it could be, e.g., a malformed page, so returning what was collected so far (rather than aborting the whole call) is closer to the existing intent than turning it into a hard failure.

## Risks / Trade-offs

- [A caller still can't tell "found 0 errors" apart from "iteration failed with 0 collected" by return value alone] → Mitigation: the log line carries that distinction; this change doesn't attempt to also change the return shape, since that would be a larger, breaking change to the tool's output contract - out of scope for this fix.
