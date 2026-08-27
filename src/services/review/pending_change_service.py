"""Propose/apply/reject review workflow for write operations.

See `pending_change_store.py` for the rationale. In short: `propose_*`
methods below validate input and persist a human-readable preview without
ever calling the Google Ads API; `apply_pending_change` is the only method
here that does, and only for a record still in "pending" status.

This wraps existing, already-tested write services (e.g.
`AdGroupCriterionService`) rather than duplicating their proto-building
logic - the safety guarantee lives entirely in the propose/apply split, not
in reimplementing the underlying mutate calls.

Currently supports one `kind`: "add_keywords" (the scenario the user asked
for first - expanding a brand campaign's keyword list without risking an
unreviewed competitor-brand term going live). Extending to budget/bid
changes (the other in-scope "flexer" operations per TRACKER.md) means
adding another `propose_*` method plus a branch in `apply_pending_change`'s
dispatch - the store and tool-registration plumbing already support it.

**Every successful apply is auto-logged to the fixes-log sheet
(2026-08-27):** unlike the propose->apply split itself, logging a change
used to depend on the calling agent remembering to call
`FixesLogService.log_fix` as a separate step afterwards - nothing enforced
it. User's explicit call: every applied change MUST be logged, so
`apply_pending_change` now calls it automatically as the last step. Logging
is best-effort *after* the real mutation - a Sheets-side failure (bad
credentials, no sheet mapped for this account, etc.) is caught, logged as a
warning, and reported back in the result (`fixes_log_error`), but never
made to look like the actual Ads mutation didn't happen - that already
succeeded and can't be undone by a logging problem downstream.
"""

from datetime import date
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Context, FastMCP

from src.services.ad_group.ad_group_criterion_service import AdGroupCriterionService
from src.services.review.fixes_log_service import FixesLogService
from src.services.review.pending_change_store import PendingChangeStore
from src.utils import get_logger

logger = get_logger(__name__)


def _format_keywords_preview(
    ad_group_id: str, keywords: List[Dict[str, Any]], negative: bool
) -> str:
    label = "NEGATIVE keywords" if negative else "keywords"
    lines = [f"Proposed {len(keywords)} {label} for ad group {ad_group_id}:"]
    for kw in keywords:
        text = kw.get("text", "?")
        match_type = kw.get("match_type", "BROAD")
        bid = kw.get("cpc_bid_micros")
        bid_note = f", cpc_bid_micros={bid}" if bid is not None else ""
        lines.append(f'  - "{text}" ({match_type}){bid_note}')
    return "\n".join(lines)


class PendingChangeService:
    """Review workflow for write operations that must not execute on the
    first call - see module docstring."""

    def __init__(
        self,
        store: Optional[PendingChangeStore] = None,
        ad_group_criterion_service: Optional[AdGroupCriterionService] = None,
        fixes_log_service: Optional[FixesLogService] = None,
    ) -> None:
        self.store = store or PendingChangeStore()
        self._ad_group_criterion_service = (
            ad_group_criterion_service or AdGroupCriterionService()
        )
        self._fixes_log_service = fixes_log_service or FixesLogService()

    async def propose_add_keywords(
        self,
        ctx: Context,
        customer_id: str,
        ad_group_id: str,
        keywords: List[Dict[str, Any]],
        negative: bool = False,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage keywords to add to an ad group for review.

        Does not call the Google Ads API - only computes a preview and
        persists it. Show the preview to the user and call
        `apply_pending_change` only once they've explicitly approved it.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            ad_group_id: The ad group ID to add keywords to
            keywords: List of keyword dicts with 'text', 'match_type', and
                optional 'cpc_bid_micros'
            negative: Whether these are negative keywords
            expectation: Which metric should move, and why - carried
                through to the fixes-log sheet's "Expected Outcome" column
                when this change is later applied (every apply is
                auto-logged - see module docstring). Optional, but worth
                setting since a blank hypothesis makes a later review
                meaningless.
            account_name: The account's descriptive name (e.g. "boo.ua") -
                carried through to the fixes-log sheet's one-time title if
                this account's sheet hasn't been initialized yet. Harmless
                to omit.

        Returns:
            change_id, status ("pending"), and a human-readable preview
        """
        if not keywords:
            raise ValueError("keywords must be a non-empty list")
        for kw in keywords:
            if not kw.get("text"):
                raise ValueError(f"keyword entry missing 'text': {kw}")

        preview = _format_keywords_preview(ad_group_id, keywords, negative)
        record = self.store.create(
            kind="add_keywords",
            params={
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "keywords": keywords,
                "negative": negative,
                "expectation": expectation,
                "account_name": account_name,
            },
            preview=preview,
        )
        await ctx.log(
            level="info",
            message=(
                f"Proposed change {record['id']}: {len(keywords)} keyword(s) "
                f"for ad group {ad_group_id}"
            ),
        )
        return {
            "change_id": record["id"],
            "status": record["status"],
            "preview": preview,
        }

    async def list_pending_changes(
        self, ctx: Context, status: Optional[str] = "pending"
    ) -> List[Dict[str, Any]]:
        """List proposed changes, defaulting to only those awaiting review.

        Args:
            ctx: FastMCP context
            status: Filter by "pending", "applied", or "rejected". Pass
                None for all statuses.
        """
        records = self.store.list(status=status)
        return [
            {
                "change_id": r["id"],
                "kind": r["kind"],
                "status": r["status"],
                "preview": r["preview"],
                "created_at": r["created_at"],
            }
            for r in records
        ]

    async def get_pending_change(self, ctx: Context, change_id: str) -> Dict[str, Any]:
        """Get full detail (including raw params) for one pending change."""
        record = self.store.get(change_id)
        if record is None:
            raise Exception(f"No pending change found with id {change_id}")
        return record

    async def apply_pending_change(
        self, ctx: Context, change_id: str
    ) -> Dict[str, Any]:
        """Execute a previously-proposed change against the live account.

        This is the only method in this service that calls the Google Ads
        API. Refuses to run if the change isn't in "pending" status (e.g.
        already applied or rejected) rather than silently re-running it.

        Every successful apply is automatically logged to the fixes-log
        sheet as its last step (see module docstring) - this is not
        optional/best-effort on the Ads-mutation side, but the *logging*
        step itself is best-effort: a Sheets-side failure is caught and
        reported in the result (`fixes_log_error`) rather than raised,
        since the real change already happened and can't be undone by a
        downstream logging problem.
        """
        record = self.store.get(change_id)
        if record is None:
            raise Exception(f"No pending change found with id {change_id}")
        if record["status"] != "pending":
            raise Exception(
                f"Change {change_id} is already '{record['status']}', not "
                "pending - refusing to apply it again."
            )

        kind = record["kind"]
        params = record["params"]

        if kind == "add_keywords":
            result = await self._ad_group_criterion_service.add_keywords(
                ctx=ctx,
                customer_id=params["customer_id"],
                ad_group_id=params["ad_group_id"],
                keywords=params["keywords"],
                negative=params.get("negative", False),
            )
            what_label = (
                "Added negative keywords"
                if params.get("negative")
                else "Added keywords"
            )
        else:
            raise Exception(f"Unknown pending-change kind: {kind}")

        updated = self.store.mark_applied(change_id, result)
        await ctx.log(
            level="info",
            message=f"Applied pending change {change_id} ({kind})",
        )

        fixes_log_error: Optional[str] = None
        try:
            await self._fixes_log_service.log_fix(
                ctx=ctx,
                customer_id=params["customer_id"],
                fix_id=change_id,
                what=what_label,
                fix_text=record["preview"],
                when=date.today().isoformat(),
                expectation=params.get("expectation") or "(not specified)",
                account_name=params.get("account_name"),
            )
        except Exception as e:
            fixes_log_error = str(e)
            await ctx.log(
                level="warning",
                message=(
                    f"Applied change {change_id} successfully, but failed to "
                    f"log it to the fixes-log sheet: {e}"
                ),
            )

        return {
            "change_id": change_id,
            "status": updated["status"],
            "applied_at": updated["applied_at"],
            "result": result,
            "fixes_log_error": fixes_log_error,
        }

    async def reject_pending_change(
        self, ctx: Context, change_id: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Discard a proposed change without ever calling the API."""
        record = self.store.get(change_id)
        if record is None:
            raise Exception(f"No pending change found with id {change_id}")
        if record["status"] != "pending":
            raise Exception(
                f"Change {change_id} is already '{record['status']}', "
                "nothing to reject."
            )
        updated = self.store.mark_rejected(change_id, reason)
        await ctx.log(level="info", message=f"Rejected pending change {change_id}")
        return {
            "change_id": change_id,
            "status": updated["status"],
            "rejected_reason": updated["rejected_reason"],
        }


def create_pending_change_tools(
    service: PendingChangeService,
) -> List[Callable[..., Awaitable[Any]]]:
    """Create tool functions for the pending-change review service.

    This returns a list of tool functions that can be registered with
    FastMCP. This approach makes the tools testable by allowing service
    injection.
    """
    tools: List[Callable[..., Awaitable[Any]]] = []

    async def propose_add_keywords(
        ctx: Context,
        customer_id: str,
        ad_group_id: str,
        keywords: List[Dict[str, Any]],
        negative: bool = False,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage keywords to add to an ad group for human review before
        they reach the live account. Does NOT call the Google Ads API -
        show the returned preview to the user and only call
        apply_pending_change once they've explicitly approved it.

        Args:
            customer_id: The customer ID
            ad_group_id: The ad group ID to add keywords to
            keywords: List of keyword dicts, each with:
                - text: The keyword text
                - match_type: EXACT, PHRASE, or BROAD (default: BROAD)
                - cpc_bid_micros: Optional CPC bid override
            negative: Whether these are negative keywords
            expectation: Which metric should move, and why - every applied
                change is auto-logged to the fixes-log sheet, and this
                becomes its "Expected Outcome" - set it, a blank hypothesis
                makes a later review meaningless
            account_name: The account's descriptive name (e.g. "boo.ua") -
                used for the fixes-log sheet's one-time title if it hasn't
                been initialized yet; harmless to omit

        Returns:
            change_id, status ("pending"), and a human-readable preview
        """
        return await service.propose_add_keywords(
            ctx=ctx,
            customer_id=customer_id,
            ad_group_id=ad_group_id,
            keywords=keywords,
            negative=negative,
            expectation=expectation,
            account_name=account_name,
        )

    async def list_pending_changes(
        ctx: Context, status: Optional[str] = "pending"
    ) -> List[Dict[str, Any]]:
        """List proposed changes awaiting review (or by another status).

        Args:
            status: Filter by "pending", "applied", or "rejected". Pass
                None for all statuses.
        """
        return await service.list_pending_changes(ctx=ctx, status=status)

    async def get_pending_change(ctx: Context, change_id: str) -> Dict[str, Any]:
        """Get full detail for one proposed change, including raw parameters.

        Args:
            change_id: The change ID returned by a propose_* tool
        """
        return await service.get_pending_change(ctx=ctx, change_id=change_id)

    async def apply_pending_change(ctx: Context, change_id: str) -> Dict[str, Any]:
        """Execute a previously-proposed change against the live Google Ads
        account. Only call this after the user has explicitly reviewed and
        approved the change's preview - never call it in the same turn as
        propose_* without the user confirming in between.

        Automatically logs the change to the fixes-log Google Sheet as its
        last step - no separate log_fix call needed. If that logging step
        fails, the result's `fixes_log_error` says why, but the Ads change
        itself already succeeded regardless.

        Args:
            change_id: The change ID returned by a propose_* tool
        """
        return await service.apply_pending_change(ctx=ctx, change_id=change_id)

    async def reject_pending_change(
        ctx: Context, change_id: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Discard a proposed change without ever touching the live account.

        Args:
            change_id: The change ID returned by a propose_* tool
            reason: Optional note on why it was rejected
        """
        return await service.reject_pending_change(
            ctx=ctx, change_id=change_id, reason=reason
        )

    tools.extend(
        [
            propose_add_keywords,
            list_pending_changes,
            get_pending_change,
            apply_pending_change,
            reject_pending_change,
        ]
    )
    return tools


def register_pending_change_tools(mcp: FastMCP[Any]) -> PendingChangeService:
    """Register pending-change tools with the MCP server.

    Returns the PendingChangeService instance for testing purposes.
    """
    service = PendingChangeService()
    tools = create_pending_change_tools(service)

    for tool in tools:
        mcp.tool(tool)

    return service
