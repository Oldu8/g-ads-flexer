"""Fixes-log service: append a change record to the user's Google Sheet
when a live change is made to a managed account, then update it later with
observed results when explicitly asked to check ("проверь фиксы"). See
`fixes_log_sheet.py` and the 2026-08-27 TRACKER.md entries for the
rationale and setup.

Deliberately no scheduling here - "review" columns are only ever written by
an explicit tool call, never on a timer. This service doesn't compute the
observed-results text itself either: pulling and interpreting metrics is a
job for the calling agent (via the existing search/GAQL tools), which then
writes its conclusion here - keeps this service a thin, dumb sheet-writer
rather than a second place with business logic about what "good" looks
like.

**Every method takes `customer_id` (2026-08-27 fix):** one ad account maps
to exactly one sheet - see `fixes_log_sheet.py`'s account-mapping doc. This
service resolves the right `FixesLogSheet` per call via
`FixesLogSheet.for_customer` (injectable as `sheet_resolver` for tests),
caching one resolved sheet per customer_id per service instance so repeat
calls for the same account don't re-resolve/re-auth every time.
"""

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP

from src.services.review.fixes_log_sheet import FixesLogSheet
from src.utils import format_customer_id, get_logger

logger = get_logger(__name__)

DEFAULT_STATUS = "Collecting data"

# Enforced, not just documented (2026-08-27): a later review computes
# elapsed days by parsing the "Date" column, so an ambiguous or
# inconsistent format there would silently break that judgment. ISO 8601
# date-only, no time component.
DATE_FORMAT = "%Y-%m-%d"


def _validate_date(when: str) -> None:
    try:
        datetime.strptime(when, DATE_FORMAT)
    except ValueError as e:
        raise ValueError(
            f"'when' must be in YYYY-MM-DD format (ISO 8601, date-only), "
            f"got {when!r} - a later review computes elapsed days by "
            f"parsing this column, so the format must be exact."
        ) from e


_REVIEW_PERIOD_COLUMNS: Dict[str, str] = {
    "week": "1-Week Review",
    "2weeks": "2-Week Review",
    "month": "1-Month Review",
}


class FixesLogService:
    """Append/list/update rows in the fixes-log Google Sheet.

    One ad account maps to exactly one sheet - every method takes
    `customer_id` and resolves (then caches) the right `FixesLogSheet` for
    it via `sheet_resolver`, rather than the service holding one fixed
    sheet for its whole lifetime.
    """

    def __init__(
        self,
        sheet_resolver: Optional[Callable[[str, Optional[str]], FixesLogSheet]] = None,
    ) -> None:
        self._sheet_resolver = sheet_resolver or FixesLogSheet.for_customer
        self._sheets_by_customer: Dict[str, FixesLogSheet] = {}

    def _get_sheet(
        self, customer_id: str, account_name: Optional[str] = None
    ) -> FixesLogSheet:
        normalized = format_customer_id(customer_id)
        if normalized not in self._sheets_by_customer:
            self._sheets_by_customer[normalized] = self._sheet_resolver(
                normalized, account_name
            )
        return self._sheets_by_customer[normalized]

    async def log_fix(
        self,
        ctx: Context,
        customer_id: str,
        fix_id: str,
        what: str,
        fix_text: str,
        when: str,
        expectation: str,
        status: str = DEFAULT_STATUS,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append a new fix record to the fixes-log sheet for one account.

        Args:
            ctx: FastMCP context
            customer_id: The ad account this fix belongs to - determines
                which sheet the row is written to (one account, one sheet)
            fix_id: A proposed id for this fix (e.g. "F-20260827-01") -
                needed later to update this same row's review columns. If
                another row already uses it (e.g. a concurrent session on
                the same account picked the same "F-<today>-01"
                independently - there's no shared counter, so don't assume
                you're the only writer today), a letter suffix is added
                automatically (-> "F-20260827-01b") and a fresh row is
                appended under that id instead; this never fails and never
                touches the other row. **Check the returned `fix_id` in the
                response** - it may differ from what you passed in, and
                that's the one to use for any later review update
            what: Short label for what changed (the "What" column)
            fix_text: What was actually done (the "Fix" column). **Keep it
                to 1-2 sentences** - what changed, a count, and the scope
                (campaign/ad group/list name). No backstory/rationale for
                why it's notable, no enumerating the individual keywords/
                negative-words (the live account already has that list -
                duplicating it here is dead weight; name a specific term
                only if something was done *to it specifically*, e.g. a bid
                raised on it), no describing the propose/apply/confirmation
                process. End with a bare id line and nothing else around it
                - `change_ids: pc_x, pc_y` for anything made via the
                pending-change flow (full detail stays recoverable from
                `snapshots/pending_changes.json`, permanently), or
                `ids: <shared_set_id>, ...` for direct mutations. Full
                before/after detail is also recoverable from the Google Ads
                `change_event` GAQL resource, but only for the last 30 days
                - so the id line is the durable pointer, not the sheet text
                itself.
            when: Date the change was made, **format YYYY-MM-DD, e.g.
                "2026-08-27" - no other format accepted**. Enforced, not
                just a convention: a later review computes elapsed days by
                parsing this column, so an ambiguous format would silently
                break that judgment.
            expectation: Which metric should move and in which direction
                (the "Expected Outcome" column) - this is the hypothesis a
                later review checks. Same brevity as fix_text: one sentence,
                metric + direction + a rough check-back window (e.g. "1-2
                недели"). No restated stats (impressions/clicks/cost/etc.) -
                those are always re-derivable live via GAQL.
            status: Initial status text (the "Status" column) - matches
                whatever dropdown values the sheet's Status column already
                uses; defaults to `DEFAULT_STATUS`
            account_name: The account's descriptive name (e.g. "boo.ua") -
                only used if this is a brand new spreadsheet, to compose
                its one-time title ("{account_name} - {customer_id} - Fixes
                Log"); harmless to omit or to pass on every call, it's
                ignored once the sheet's already initialized

        Returns:
            Confirmation with the fix_id actually written (may differ from
            the one passed in - see the `fix_id` arg doc) and status
        """
        _validate_date(when)
        sheet = self._get_sheet(customer_id, account_name)
        actual_id = sheet.append_fix(
            fix_id=fix_id,
            what=what,
            fix_text=fix_text,
            status=status,
            when=when,
            expectation=expectation,
        )
        await ctx.log(
            level="info",
            message=f"Logged fix {actual_id} for account {customer_id} to its fixes-log sheet",
        )
        return {"fix_id": actual_id, "status": status}

    async def list_fixes(self, ctx: Context, customer_id: str) -> List[Dict[str, Any]]:
        """Read back every row currently in one account's fixes-log sheet."""
        sheet = self._get_sheet(customer_id)
        return sheet.list_rows()

    async def update_fix_review(
        self, ctx: Context, customer_id: str, fix_id: str, period: str, note: str
    ) -> Dict[str, Any]:
        """Write an observed-results note into one of the time-boxed review
        columns for a fix.

        Args:
            ctx: FastMCP context
            customer_id: The ad account this fix belongs to
            fix_id: The fix id this note is for (as passed to log_fix)
            period: Which column to write - "week", "2weeks", or "month"
            note: The observed-results text to write into that column

        Returns:
            Confirmation with the fix_id, the column written, and the note
        """
        column = _REVIEW_PERIOD_COLUMNS.get(period)
        if column is None:
            raise ValueError(
                f"period must be one of {list(_REVIEW_PERIOD_COLUMNS)}, got {period!r}"
            )
        sheet = self._get_sheet(customer_id)
        sheet.update_cell(fix_id, column, note)
        await ctx.log(level="info", message=f"Updated '{column}' for fix {fix_id}")
        return {"fix_id": fix_id, "column": column, "note": note}

    async def update_fix_conclusion(
        self,
        ctx: Context,
        customer_id: str,
        fix_id: str,
        conclusion: str,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Write the final "Conclusion" for a fix, optionally also updating Status.

        Args:
            ctx: FastMCP context
            customer_id: The ad account this fix belongs to
            fix_id: The fix id this conclusion is for
            conclusion: The conclusion text (the "Conclusion" column)
            status: Optional new status (e.g. "confirmed_positive",
                "confirmed_negative", "inconclusive", "reverted") - matches
                whatever the sheet's Status dropdown already uses

        Returns:
            Confirmation with the fix_id, conclusion, and status written
        """
        sheet = self._get_sheet(customer_id)
        sheet.update_cell(fix_id, "Conclusion", conclusion)
        if status is not None:
            sheet.update_cell(fix_id, "Status", status)
        await ctx.log(level="info", message=f"Updated conclusion for fix {fix_id}")
        return {"fix_id": fix_id, "conclusion": conclusion, "status": status}


def create_fixes_log_tools(
    service: FixesLogService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the fixes-log service.

    This returns a list of tool functions that can be registered with
    FastMCP. This approach makes the tools testable by allowing service
    injection.
    """
    tools: List[Callable[..., Awaitable[Any]]] = []

    async def log_fix(
        ctx: Context,
        customer_id: str,
        fix_id: str,
        what: str,
        fix_text: str,
        when: str,
        expectation: str,
        status: str = DEFAULT_STATUS,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append a new fix record to the fixes-log Google Sheet. Call this
        right after applying a live change to a managed account.

        Args:
            customer_id: The ad account this fix belongs to - one account
                always maps to exactly one sheet, never shared across
                accounts
            fix_id: A proposed id for this fix (e.g. "F-20260827-01") - if
                another row already uses it (a concurrent session on the
                same account may have picked the same "F-<today>-NN"
                independently), a letter suffix is added automatically and
                a new row is appended under that id instead. Check the
                returned `fix_id` - use it, not what you passed in, for any
                later review update
            what: Short label for what changed
            fix_text: What was actually done - **1-2 sentences only**: what
                changed, a count, the scope (campaign/ad group/list). No
                backstory/rationale, no enumerating individual keywords (name
                one only if something was done specifically to it, e.g. a
                bid raise), no describing the propose/apply process. End
                with a bare `change_ids: ...` or `ids: ...` line pointing at
                the durable detail (pending_changes.json, or the live
                list/campaign) - that pointer is what makes the brevity safe.
            when: Date the change was made - **must be YYYY-MM-DD**, e.g.
                "2026-08-27", no other format accepted (a later review
                parses this to compute elapsed days)
            expectation: Which metric should move and in which direction -
                one sentence, no restated stats (those are re-derivable live)
            status: Initial status text (defaults to "Collecting data")
            account_name: The account's descriptive name (e.g. "boo.ua") -
                only used the very first time this account's sheet is
                touched, to title it "{account_name} - {customer_id} -
                Fixes Log"; harmless to pass every time, ignored once
                already initialized
        """
        return await service.log_fix(
            ctx=ctx,
            customer_id=customer_id,
            fix_id=fix_id,
            what=what,
            fix_text=fix_text,
            when=when,
            expectation=expectation,
            status=status,
            account_name=account_name,
        )

    async def list_fixes(ctx: Context, customer_id: str) -> List[Dict[str, Any]]:
        """Read back every row currently in one account's fixes-log sheet.

        Args:
            customer_id: The ad account whose sheet to read
        """
        return await service.list_fixes(ctx=ctx, customer_id=customer_id)

    async def update_fix_review(
        ctx: Context, customer_id: str, fix_id: str, period: str, note: str
    ) -> Dict[str, Any]:
        """Write an observed-results note into a fix's time-boxed review
        column. Pull the relevant metrics yourself first (via the existing
        search/GAQL tools) and compose the note - this tool only writes it.

        Args:
            customer_id: The ad account this fix belongs to
            fix_id: The fix id this note is for
            period: Which column to write - "week", "2weeks", or "month"
            note: The observed-results text to write
        """
        return await service.update_fix_review(
            ctx=ctx, customer_id=customer_id, fix_id=fix_id, period=period, note=note
        )

    async def update_fix_conclusion(
        ctx: Context,
        customer_id: str,
        fix_id: str,
        conclusion: str,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Write the final "Conclusion" (and optionally a new Status) for a fix.

        Args:
            customer_id: The ad account this fix belongs to
            fix_id: The fix id this conclusion is for
            conclusion: The conclusion text
            status: Optional new status value
        """
        return await service.update_fix_conclusion(
            ctx=ctx,
            customer_id=customer_id,
            fix_id=fix_id,
            conclusion=conclusion,
            status=status,
        )

    tools.extend([log_fix, list_fixes, update_fix_review, update_fix_conclusion])
    return tools


def register_fixes_log_tools(mcp: FastMCP[Any]) -> FixesLogService:
    """Register fixes-log tools with the MCP server.

    Returns the FixesLogService instance for testing purposes.
    """
    service = FixesLogService()
    tools = create_fixes_log_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
