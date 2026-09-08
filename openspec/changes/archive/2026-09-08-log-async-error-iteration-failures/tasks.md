## 1. Fix

- [x] 1.1 In `mcp-server/src/services/campaign/campaign_draft_service.py`, replace the `except Exception: pass` around the async-error pagination loop with `await ctx.log(level="warning", message=...)` reporting the exception, then continue returning the errors collected so far — verify by reading the diff against `search_service.py`'s equivalent pattern.

## 2. Tests

- [x] 2.1 Add a test in `mcp-server/tests/test_campaign_draft_service.py` covering pagination failure: mock the response iterator to raise partway through, assert a warning is logged and the partial/empty list is still returned (not an exception) — verify with `pytest mcp-server/tests/test_campaign_draft_service.py`. (An existing test, `test_list_campaign_draft_async_errors_empty`, already covered this exact scenario; its assertions were updated in place rather than adding a duplicate.)
- [x] 2.2 Run the full `campaign_draft_service` test file and confirm no regressions — verify with `pytest mcp-server/tests/test_campaign_draft_service.py -v`. All 10 tests pass.
