"""Propose/apply/reject review workflow for write operations.

See `pending_change_store.py` for the rationale. In short: `propose_*`
methods below validate input and persist a human-readable preview without
ever calling the Google Ads API; `apply_pending_change` is the only method
here that does, and only for a record still in "pending" status.

This wraps existing, already-tested write services (e.g.
`AdGroupCriterionService`) rather than duplicating their proto-building
logic - the safety guarantee lives entirely in the propose/apply split, not
in reimplementing the underlying mutate calls.

Supports seven `kind`s: "add_keywords" (the scenario the user asked for
first - expanding a brand campaign's keyword list without risking an
unreviewed competitor-brand term going live), "update_campaign_budget" and
"update_campaign_bid_target" (2026-08-27 - the other in-scope "flexer"
operations per TRACKER.md: budgets and bids),
"create_rule_based_user_list"/"remove_user_list" (2026-09-02 - audience
creation/cleanup; added specifically because a prior session did this kind
of live account change via ad-hoc scratch scripts instead of through this
review system, which the user correctly called out - every write operation
needs an explicit propose/apply step, no exceptions for "it's just an
audience"), and "add_negative_keywords_to_shared_set"/
"remove_shared_criterion" (2026-09-02 - shared negative-keyword lists are
boo.ua's actual negative-keyword architecture - see the
`gads-negative-keyword-architecture` memory - so this is the
highest-traffic write path of the four negative-keyword levels
(account/campaign/ad-group/shared-set), and was the one NOT yet gated by
this review system before now). Adding a further `kind` means one more
`propose_*` method plus one more branch in `apply_pending_change`'s
dispatch - the store and tool-registration plumbing already support it.

**Bid-target propose calls require `bidding_strategy_type`** - same reason
`campaign_service.update_campaign` itself requires it (see the 2026-08-17
TRACKER.md fix): passing only e.g. `max_conversion_value_target_roas`
without restating the campaign's *current* strategy type would silently
no-op at apply time. This module fails that at propose time instead - no
point letting a preview through that would do nothing when applied.

**Budget/bid-target previews don't fetch the "before" value themselves** -
`propose_update_campaign_budget`/`propose_update_campaign_bid_target`
accept an optional `current_*` param for a nicer before/after preview, but
never make a read call to fill it in if omitted. Consistent with this
service being a thin dispatcher, not a second place with its own Google Ads
read logic: the calling agent, which just decided *why* to propose this
change, has almost always already looked up the current value via the
existing search/GAQL tools - pass it along rather than have this service
re-fetch it.

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
from src.services.audiences.user_list_service import UserListService
from src.services.bidding.budget_service import BudgetService
from src.services.campaign.campaign_service import CampaignService
from src.services.review.fixes_log_service import FixesLogService
from src.services.review.pending_change_store import PendingChangeStore
from src.services.shared.shared_criterion_service import SharedCriterionService
from src.utils import get_logger

logger = get_logger(__name__)

# Matches campaign_service.py's _apply_bidding_strategy - kept as a plain
# set here rather than imported, since that's a private module-level
# helper, not part of campaign_service's public surface.
_KNOWN_BIDDING_STRATEGY_TYPES = {
    "MANUAL_CPC",
    "TARGET_CPA",
    "TARGET_ROAS",
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_SPEND",
    "TARGET_IMPRESSION_SHARE",
    "PORTFOLIO",
}

# bidding_strategy_type -> which target_* param is meaningful for it. Used
# only to validate that propose_update_campaign_bid_target got a target
# value that actually matches the type it's paired with.
_BID_TARGET_PARAM_BY_TYPE = {
    "TARGET_CPA": "target_cpa_micros",
    "MAXIMIZE_CONVERSIONS": "target_cpa_micros",
    "TARGET_ROAS": "target_roas",
    "MAXIMIZE_CONVERSION_VALUE": "max_conversion_value_target_roas",
}

# --- Sanity limits (2026-08-27, user's explicit choices) ---
# Deliberately advisory, not blocking: a proposal that exceeds one of these
# still gets created (status "pending") - the preview and the returned dict
# both flag it clearly, and the user's normal apply-or-reject decision is
# what "allows it anyway" if that's actually intended. No separate
# confirmation step beyond the existing propose/apply split - the user was
# explicit that adding one would be redundant friction, not extra safety.
MAX_KEYWORDS_PER_PROPOSAL = 50
MAX_BUDGET_CHANGE_PCT = 50.0


def _format_keywords_preview(
    ad_group_id: str,
    keywords: List[Dict[str, Any]],
    negative: bool,
    existing_keywords: Optional[List[str]] = None,
) -> tuple[str, bool, bool]:
    """Returns (preview_text, exceeds_count_limit, has_duplicates)."""
    label = "NEGATIVE keywords" if negative else "keywords"
    existing_lower = {t.lower() for t in (existing_keywords or [])}

    exceeds_limit = len(keywords) > MAX_KEYWORDS_PER_PROPOSAL
    lines = [f"Proposed {len(keywords)} {label} for ad group {ad_group_id}:"]
    if exceeds_limit:
        lines.insert(
            0,
            f"[!] EXCEEDS LIMIT: {len(keywords)} keywords proposed, guideline "
            f"is {MAX_KEYWORDS_PER_PROPOSAL} per proposal - consider "
            "splitting into smaller batches for easier review.",
        )

    has_duplicates = False
    for kw in keywords:
        text = kw.get("text", "?")
        match_type = kw.get("match_type", "BROAD")
        bid = kw.get("cpc_bid_micros")
        bid_note = f", cpc_bid_micros={bid}" if bid is not None else ""
        dup_note = ""
        if text.lower() in existing_lower:
            has_duplicates = True
            dup_note = "  [!] DUPLICATE - already exists in this ad group"
        lines.append(f'  - "{text}" ({match_type}){bid_note}{dup_note}')

    return "\n".join(lines), exceeds_limit, has_duplicates


def _format_budget_preview(
    budget_id: str,
    new_amount_micros: int,
    current_amount_micros: Optional[int],
) -> tuple[str, bool]:
    """Returns (preview_text, exceeds_change_limit)."""

    def _fmt(micros: int) -> str:
        return f"{micros / 1_000_000:,.2f}"

    lines = [f"Proposed budget change for campaignBudget {budget_id}:"]
    exceeds_limit = False
    if current_amount_micros is not None:
        delta = new_amount_micros - current_amount_micros
        pct = (delta / current_amount_micros * 100) if current_amount_micros else 0.0
        exceeds_limit = abs(pct) > MAX_BUDGET_CHANGE_PCT
        line = (
            f"  {_fmt(current_amount_micros)} -> {_fmt(new_amount_micros)}"
            f" ({delta:+,} micros, {pct:+.1f}%)"
        )
        if exceeds_limit:
            lines.insert(
                0,
                f"[!] EXCEEDS LIMIT: {pct:+.1f}% change requested, limit is "
                f"±{MAX_BUDGET_CHANGE_PCT:.0f}% - review carefully "
                "before approving.",
            )
        lines.append(line)
    else:
        lines.append(
            f"  New amount: {_fmt(new_amount_micros)} (current amount not "
            f"supplied - cannot verify against the ±{MAX_BUDGET_CHANGE_PCT:.0f}% limit)"
        )
    return "\n".join(lines), exceeds_limit


def _format_bid_target_preview(
    campaign_id: str,
    bidding_strategy_type: str,
    target_param_name: str,
    new_value: Any,
    current_value: Optional[Any],
) -> str:
    lines = [
        f"Proposed bid target change for campaign {campaign_id} "
        f"(strategy: {bidding_strategy_type}):"
    ]
    if current_value is not None:
        lines.append(f"  {target_param_name}: {current_value} -> {new_value}")
    else:
        lines.append(
            f"  {target_param_name}: {new_value} "
            "(current value not supplied - no before/after delta)"
        )
    return "\n".join(lines)


def _format_rule_based_user_list_preview(
    name: str, url_contains_patterns: List[str], lookback_window_days: int
) -> str:
    lines = [
        f'Proposed rule-based user list "{name}" '
        f"({lookback_window_days}-day lookback), matching ANY of:"
    ]
    for pattern in url_contains_patterns:
        lines.append(f'  - url contains "{pattern}"')
    return "\n".join(lines)


def _format_remove_user_list_preview(
    user_list_id: str, user_list_name: Optional[str]
) -> str:
    label = f'"{user_list_name}" ({user_list_id})' if user_list_name else user_list_id
    return f"Proposed removal of user list {label}."


def _format_shared_set_keywords_preview(
    shared_set_id: str,
    keywords: List[Dict[str, str]],
    existing_keywords: Optional[List[str]] = None,
) -> tuple[str, bool, bool]:
    """Returns (preview_text, exceeds_count_limit, has_duplicates). Same
    shape as _format_keywords_preview, minus cpc_bid_micros - shared-set
    (negative) criteria don't have bids."""
    existing_lower = {t.lower() for t in (existing_keywords or [])}

    exceeds_limit = len(keywords) > MAX_KEYWORDS_PER_PROPOSAL
    lines = [
        f"Proposed {len(keywords)} negative keyword(s) for shared set {shared_set_id}:"
    ]
    if exceeds_limit:
        lines.insert(
            0,
            f"[!] EXCEEDS LIMIT: {len(keywords)} keywords proposed, guideline "
            f"is {MAX_KEYWORDS_PER_PROPOSAL} per proposal - consider "
            "splitting into smaller batches for easier review.",
        )

    has_duplicates = False
    for kw in keywords:
        text = kw.get("text", "?")
        match_type = kw.get("match_type", "BROAD")
        dup_note = ""
        if text.lower() in existing_lower:
            has_duplicates = True
            dup_note = "  [!] DUPLICATE - already exists in this shared set"
        lines.append(f'  - "{text}" ({match_type}){dup_note}')

    return "\n".join(lines), exceeds_limit, has_duplicates


def _format_remove_shared_criterion_preview(
    criterion_resource_name: str, criterion_description: Optional[str]
) -> str:
    label = (
        f'"{criterion_description}" ({criterion_resource_name})'
        if criterion_description
        else criterion_resource_name
    )
    return f"Proposed removal of shared criterion {label}."


class PendingChangeService:
    """Review workflow for write operations that must not execute on the
    first call - see module docstring."""

    def __init__(
        self,
        store: Optional[PendingChangeStore] = None,
        ad_group_criterion_service: Optional[AdGroupCriterionService] = None,
        budget_service: Optional[BudgetService] = None,
        campaign_service: Optional[CampaignService] = None,
        user_list_service: Optional[UserListService] = None,
        shared_criterion_service: Optional[SharedCriterionService] = None,
        fixes_log_service: Optional[FixesLogService] = None,
    ) -> None:
        self.store = store or PendingChangeStore()
        self._ad_group_criterion_service = (
            ad_group_criterion_service or AdGroupCriterionService()
        )
        self._budget_service = budget_service or BudgetService()
        self._campaign_service = campaign_service or CampaignService()
        self._user_list_service = user_list_service or UserListService()
        self._shared_criterion_service = (
            shared_criterion_service or SharedCriterionService()
        )
        self._fixes_log_service = fixes_log_service or FixesLogService()

    async def propose_add_keywords(
        self,
        ctx: Context,
        customer_id: str,
        ad_group_id: str,
        keywords: List[Dict[str, Any]],
        negative: bool = False,
        existing_keywords: Optional[List[str]] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage keywords to add to an ad group for review.

        Does not call the Google Ads API - only computes a preview and
        persists it. Show the preview to the user and call
        `apply_pending_change` only once they've explicitly approved it.

        Two sanity checks are advisory, not blocking (2026-08-27, user's
        explicit choice - flag clearly, let the normal apply/reject
        decision be what "allows it anyway"): proposing more than
        `MAX_KEYWORDS_PER_PROPOSAL` keywords, and any proposed keyword that
        already exists in `existing_keywords`. Both are surfaced in the
        preview text and in this method's returned dict
        (`exceeds_limit`/`has_duplicates`) - neither raises.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            ad_group_id: The ad group ID to add keywords to
            keywords: List of keyword dicts with 'text', 'match_type', and
                optional 'cpc_bid_micros'
            negative: Whether these are negative keywords
            existing_keywords: Keyword texts already present in this ad
                group (positive or negative) - look them up via the
                existing search/GAQL tools first and pass them along; used
                only to flag duplicates in the preview, this method never
                fetches them itself. Omitting it just means no duplicate
                check runs, not an error.
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
            change_id, status ("pending"), a human-readable preview, and
            exceeds_limit/has_duplicates flags
        """
        if not keywords:
            raise ValueError("keywords must be a non-empty list")
        for kw in keywords:
            if not kw.get("text"):
                raise ValueError(f"keyword entry missing 'text': {kw}")

        preview, exceeds_limit, has_duplicates = _format_keywords_preview(
            ad_group_id, keywords, negative, existing_keywords
        )
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
                + (" [EXCEEDS LIMIT]" if exceeds_limit else "")
                + (" [HAS DUPLICATES]" if has_duplicates else "")
            ),
        )
        return {
            "change_id": record["id"],
            "status": record["status"],
            "preview": preview,
            "exceeds_limit": exceeds_limit,
            "has_duplicates": has_duplicates,
        }

    async def propose_update_campaign_budget(
        self,
        ctx: Context,
        customer_id: str,
        budget_id: str,
        new_amount_micros: int,
        current_amount_micros: Optional[int] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a campaign budget amount change for review.

        Does not call the Google Ads API - only computes a preview and
        persists it. Show the preview to the user and call
        `apply_pending_change` only once they've explicitly approved it.

        The ±`MAX_BUDGET_CHANGE_PCT` sanity check is advisory, not blocking
        (2026-08-27, user's explicit choice): a change past that limit
        still gets proposed - it's flagged clearly in the preview and in
        this method's returned dict (`exceeds_limit`), and the normal
        apply/reject decision is what "allows it anyway" if that's actually
        intended. The check only runs at all if `current_amount_micros` is
        supplied - without it there's nothing to compare against, and the
        preview says so explicitly rather than silently skipping the
        caveat.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            budget_id: The campaign budget ID to update (not the full
                resource name - just the numeric id)
            new_amount_micros: The proposed new daily budget, in micros
                (1,000,000 micros = 1 unit of the account's currency)
            current_amount_micros: The budget's current amount, in micros -
                strongly recommended: without it the preview can't show a
                before/after delta *or* check the ±50% limit. This method
                never fetches it itself - look it up via the existing
                search/GAQL tools first and pass it along.
            expectation: Which metric should move, and why - carried
                through to the fixes-log sheet's "Expected Outcome" column
                when this change is later applied (every apply is
                auto-logged)
            account_name: The account's descriptive name (e.g. "boo.ua") -
                carried through to the fixes-log sheet's one-time title

        Returns:
            change_id, status ("pending"), a human-readable preview, and
            an exceeds_limit flag
        """
        if new_amount_micros <= 0:
            raise ValueError("new_amount_micros must be a positive integer")

        preview, exceeds_limit = _format_budget_preview(
            budget_id, new_amount_micros, current_amount_micros
        )
        record = self.store.create(
            kind="update_campaign_budget",
            params={
                "customer_id": customer_id,
                "budget_id": budget_id,
                "amount_micros": new_amount_micros,
                "expectation": expectation,
                "account_name": account_name,
            },
            preview=preview,
        )
        await ctx.log(
            level="info",
            message=(
                f"Proposed change {record['id']}: budget {budget_id} -> "
                f"{new_amount_micros} micros"
                + (" [EXCEEDS LIMIT]" if exceeds_limit else "")
            ),
        )
        return {
            "change_id": record["id"],
            "status": record["status"],
            "preview": preview,
            "exceeds_limit": exceeds_limit,
        }

    async def propose_update_campaign_bid_target(
        self,
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        bidding_strategy_type: str,
        target_cpa_micros: Optional[int] = None,
        target_roas: Optional[float] = None,
        max_conversion_value_target_roas: Optional[float] = None,
        current_value: Optional[Any] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a campaign bid-target change (e.g. Target ROAS, Target CPA)
        for review.

        `bidding_strategy_type` must match the campaign's *current*
        strategy - restate it even if you're only nudging its target value,
        not switching strategies (same rule `campaign_service.update_campaign`
        itself enforces, see the 2026-08-17 TRACKER.md fix). This method
        validates that up front, at propose time, rather than letting a
        preview through that would silently no-op when applied.

        Does not call the Google Ads API - only computes a preview and
        persists it. Show the preview to the user and call
        `apply_pending_change` only once they've explicitly approved it.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            campaign_id: The campaign ID to update
            bidding_strategy_type: The campaign's *current* bidding
                strategy - one of MANUAL_CPC, TARGET_CPA, TARGET_ROAS,
                MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE,
                TARGET_SPEND, TARGET_IMPRESSION_SHARE, PORTFOLIO
            target_cpa_micros: New target CPA in micros - for TARGET_CPA or
                MAXIMIZE_CONVERSIONS
            target_roas: New target ROAS - for TARGET_ROAS
            max_conversion_value_target_roas: New target ROAS - for
                MAXIMIZE_CONVERSION_VALUE
            current_value: The current target value (whichever of the
                above is relevant) - optional, but strongly recommended:
                without it the preview can't show a before/after delta.
                This method never fetches it itself - look it up via the
                existing search/GAQL tools first and pass it along.
            expectation: Which metric should move, and why - carried
                through to the fixes-log sheet's "Expected Outcome" column
                when this change is later applied (every apply is
                auto-logged)
            account_name: The account's descriptive name (e.g. "boo.ua") -
                carried through to the fixes-log sheet's one-time title

        Returns:
            change_id, status ("pending"), and a human-readable preview
        """
        bst = bidding_strategy_type.upper()
        if bst not in _KNOWN_BIDDING_STRATEGY_TYPES:
            raise ValueError(
                f"Unsupported bidding_strategy_type: {bidding_strategy_type!r}, "
                f"expected one of {sorted(_KNOWN_BIDDING_STRATEGY_TYPES)}"
            )

        provided = {
            "target_cpa_micros": target_cpa_micros,
            "target_roas": target_roas,
            "max_conversion_value_target_roas": max_conversion_value_target_roas,
        }
        set_params = [name for name, value in provided.items() if value is not None]
        if not set_params:
            raise ValueError(
                "At least one of target_cpa_micros, target_roas, or "
                "max_conversion_value_target_roas must be provided - "
                "otherwise there's nothing to change."
            )

        expected_param = _BID_TARGET_PARAM_BY_TYPE.get(bst)
        if expected_param is not None and expected_param not in set_params:
            raise ValueError(
                f"bidding_strategy_type={bst!r} expects '{expected_param}' to "
                f"be set, got {set_params} instead - these must match the "
                "campaign's actual strategy type."
            )

        target_param_name = set_params[0]
        new_value = provided[target_param_name]

        preview = _format_bid_target_preview(
            campaign_id, bst, target_param_name, new_value, current_value
        )
        record = self.store.create(
            kind="update_campaign_bid_target",
            params={
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "bidding_strategy_type": bst,
                "target_cpa_micros": target_cpa_micros,
                "target_roas": target_roas,
                "max_conversion_value_target_roas": max_conversion_value_target_roas,
                "expectation": expectation,
                "account_name": account_name,
            },
            preview=preview,
        )
        await ctx.log(
            level="info",
            message=(
                f"Proposed change {record['id']}: campaign {campaign_id} "
                f"{target_param_name} -> {new_value}"
            ),
        )
        return {
            "change_id": record["id"],
            "status": record["status"],
            "preview": preview,
        }

    async def propose_create_rule_based_user_list(
        self,
        ctx: Context,
        customer_id: str,
        name: str,
        url_contains_patterns: List[str],
        lookback_window_days: int = 30,
        description: Optional[str] = None,
        membership_status: str = "OPEN",
        prepopulate: bool = True,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a rule-based (URL-contains) remarketing user list for
        review - e.g. a "category page visitors" audience.

        Does not call the Google Ads API - only computes a preview and
        persists it. Show the preview to the user and call
        `apply_pending_change` only once they've explicitly approved it.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            name: User list name
            url_contains_patterns: Page qualifies if its URL contains ANY
                of these strings (e.g. "/zoloti-godynnyky/")
            lookback_window_days: How far back to look for a qualifying
                visit, in days - the "7/14/30/90-day" knob for this list
                type (NOT membership_life_span - see
                `UserListService.create_rule_based_user_list`'s docstring
                for why)
            description: Optional description
            membership_status: OPEN or CLOSED
            prepopulate: If True, requests backfilling from existing site
                visitors (Display Network only, last 30 days)
            expectation: Which metric should move, and why - carried
                through to the fixes-log sheet's "Expected Outcome" column
                when this change is later applied
            account_name: The account's descriptive name (e.g. "boo.ua") -
                carried through to the fixes-log sheet's one-time title

        Returns:
            change_id, status ("pending"), and a human-readable preview
        """
        if not url_contains_patterns:
            raise ValueError("url_contains_patterns must be a non-empty list")

        preview = _format_rule_based_user_list_preview(
            name, url_contains_patterns, lookback_window_days
        )
        record = self.store.create(
            kind="create_rule_based_user_list",
            params={
                "customer_id": customer_id,
                "name": name,
                "url_contains_patterns": url_contains_patterns,
                "lookback_window_days": lookback_window_days,
                "description": description,
                "membership_status": membership_status,
                "prepopulate": prepopulate,
                "expectation": expectation,
                "account_name": account_name,
            },
            preview=preview,
        )
        await ctx.log(
            level="info",
            message=(
                f"Proposed change {record['id']}: rule-based user list "
                f"'{name}' ({len(url_contains_patterns)} pattern(s))"
            ),
        )
        return {
            "change_id": record["id"],
            "status": record["status"],
            "preview": preview,
        }

    async def propose_remove_user_list(
        self,
        ctx: Context,
        customer_id: str,
        user_list_id: str,
        user_list_name: Optional[str] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a user list removal for review.

        Does not call the Google Ads API - only persists a preview. Show
        the preview to the user and call `apply_pending_change` only once
        they've explicitly approved it.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            user_list_id: The user list ID to remove
            user_list_name: The list's current name - look it up via the
                existing search/GAQL tools first and pass it along, purely
                to make the preview readable; this method never fetches it
                itself
            expectation: Why this is being removed / what should follow -
                carried through to the fixes-log sheet's "Expected
                Outcome" column when this change is later applied
            account_name: The account's descriptive name (e.g. "boo.ua") -
                carried through to the fixes-log sheet's one-time title

        Returns:
            change_id, status ("pending"), and a human-readable preview
        """
        preview = _format_remove_user_list_preview(user_list_id, user_list_name)
        record = self.store.create(
            kind="remove_user_list",
            params={
                "customer_id": customer_id,
                "user_list_id": user_list_id,
                "expectation": expectation,
                "account_name": account_name,
            },
            preview=preview,
        )
        await ctx.log(
            level="info",
            message=f"Proposed change {record['id']}: remove user list {user_list_id}",
        )
        return {
            "change_id": record["id"],
            "status": record["status"],
            "preview": preview,
        }

    async def propose_add_negative_keywords_to_shared_set(
        self,
        ctx: Context,
        customer_id: str,
        shared_set_id: str,
        keywords: List[Dict[str, str]],
        existing_keywords: Optional[List[str]] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage negative keywords to add to a shared set for review - the
        boo.ua account's actual negative-keyword architecture (20+ shared
        lists attached across many campaigns), not per-campaign/ad-group
        negatives.

        Does not call the Google Ads API - only computes a preview and
        persists it. Show the preview to the user and call
        `apply_pending_change` only once they've explicitly approved it.

        Same two advisory (non-blocking) sanity checks as
        `propose_add_keywords`: a batch over `MAX_KEYWORDS_PER_PROPOSAL`,
        and any keyword already present in `existing_keywords` - both
        flagged in the preview and the returned dict, neither one raises.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            shared_set_id: The shared set ID to add keywords to
            keywords: List of dicts with 'text' and 'match_type' - no
                cpc_bid_micros, shared-set (negative) criteria don't have
                bids
            existing_keywords: Keyword texts already present in this
                shared set - look them up via the existing search/GAQL
                tools first and pass them along; used only to flag
                duplicates in the preview, never fetched by this method
                itself
            expectation: Which metric should move, and why - carried
                through to the fixes-log sheet's "Expected Outcome" column
                when this change is later applied
            account_name: The account's descriptive name (e.g. "boo.ua") -
                carried through to the fixes-log sheet's one-time title

        Returns:
            change_id, status ("pending"), preview, exceeds_limit, and
            has_duplicates
        """
        if not keywords:
            raise ValueError("keywords must be a non-empty list")
        for kw in keywords:
            if not kw.get("text"):
                raise ValueError(f"keyword entry missing 'text': {kw}")

        preview, exceeds_limit, has_duplicates = _format_shared_set_keywords_preview(
            shared_set_id, keywords, existing_keywords
        )
        record = self.store.create(
            kind="add_negative_keywords_to_shared_set",
            params={
                "customer_id": customer_id,
                "shared_set_id": shared_set_id,
                "keywords": keywords,
                "expectation": expectation,
                "account_name": account_name,
            },
            preview=preview,
        )
        await ctx.log(
            level="info",
            message=(
                f"Proposed change {record['id']}: {len(keywords)} negative "
                f"keyword(s) for shared set {shared_set_id}"
                + (" [EXCEEDS LIMIT]" if exceeds_limit else "")
                + (" [HAS DUPLICATES]" if has_duplicates else "")
            ),
        )
        return {
            "change_id": record["id"],
            "status": record["status"],
            "preview": preview,
            "exceeds_limit": exceeds_limit,
            "has_duplicates": has_duplicates,
        }

    async def propose_remove_shared_criterion(
        self,
        ctx: Context,
        customer_id: str,
        criterion_resource_name: str,
        criterion_description: Optional[str] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a shared-set criterion removal for review.

        Does not call the Google Ads API - only persists a preview. Show
        the preview to the user and call `apply_pending_change` only once
        they've explicitly approved it.

        Args:
            ctx: FastMCP context
            customer_id: The customer ID
            criterion_resource_name: Full resource name of the shared
                criterion to remove (e.g.
                "customers/123/sharedCriteria/456~789")
            criterion_description: The keyword text (or similar) this
                criterion represents - look it up via the existing
                search/GAQL tools first and pass it along, purely to make
                the preview readable; this method never fetches it itself
            expectation: Why this is being removed / what should follow
            account_name: The account's descriptive name (e.g. "boo.ua")

        Returns:
            change_id, status ("pending"), and a human-readable preview
        """
        preview = _format_remove_shared_criterion_preview(
            criterion_resource_name, criterion_description
        )
        record = self.store.create(
            kind="remove_shared_criterion",
            params={
                "customer_id": customer_id,
                "criterion_resource_name": criterion_resource_name,
                "expectation": expectation,
                "account_name": account_name,
            },
            preview=preview,
        )
        await ctx.log(
            level="info",
            message=(
                f"Proposed change {record['id']}: remove shared criterion "
                f"{criterion_resource_name}"
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
        elif kind == "update_campaign_budget":
            result = await self._budget_service.update_campaign_budget(
                ctx=ctx,
                customer_id=params["customer_id"],
                budget_id=params["budget_id"],
                amount_micros=params["amount_micros"],
            )
            what_label = "Updated campaign budget"
        elif kind == "update_campaign_bid_target":
            result = await self._campaign_service.update_campaign(
                ctx=ctx,
                customer_id=params["customer_id"],
                campaign_id=params["campaign_id"],
                bidding_strategy_type=params["bidding_strategy_type"],
                target_cpa_micros=params.get("target_cpa_micros"),
                target_roas=params.get("target_roas"),
                max_conversion_value_target_roas=params.get(
                    "max_conversion_value_target_roas"
                ),
            )
            what_label = "Updated campaign bid target"
        elif kind == "create_rule_based_user_list":
            result = await self._user_list_service.create_rule_based_user_list(
                ctx=ctx,
                customer_id=params["customer_id"],
                name=params["name"],
                url_contains_patterns=params["url_contains_patterns"],
                lookback_window_days=params.get("lookback_window_days", 30),
                description=params.get("description"),
                membership_status=params.get("membership_status", "OPEN"),
                prepopulate=params.get("prepopulate", True),
            )
            what_label = "Created rule-based user list"
        elif kind == "remove_user_list":
            result = await self._user_list_service.remove_user_list(
                ctx=ctx,
                customer_id=params["customer_id"],
                user_list_id=params["user_list_id"],
            )
            what_label = "Removed user list"
        elif kind == "add_negative_keywords_to_shared_set":
            result = await self._shared_criterion_service.add_keywords_to_shared_set(
                ctx=ctx,
                customer_id=params["customer_id"],
                shared_set_id=params["shared_set_id"],
                keywords=params["keywords"],
            )
            what_label = "Added negative keywords to shared set"
        elif kind == "remove_shared_criterion":
            result = await self._shared_criterion_service.remove_shared_criterion(
                ctx=ctx,
                customer_id=params["customer_id"],
                criterion_resource_name=params["criterion_resource_name"],
            )
            what_label = "Removed shared criterion"
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
        existing_keywords: Optional[List[str]] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage keywords to add to an ad group for human review before
        they reach the live account. Does NOT call the Google Ads API -
        show the returned preview to the user and only call
        apply_pending_change once they've explicitly approved it.

        Two sanity checks are advisory, not blocking: proposing more than
        50 keywords at once, and any keyword already present in
        existing_keywords. Both are flagged in the preview and in this
        tool's returned exceeds_limit/has_duplicates - neither one refuses
        the proposal, the user's normal approve/reject call is what decides.

        Args:
            customer_id: The customer ID
            ad_group_id: The ad group ID to add keywords to
            keywords: List of keyword dicts, each with:
                - text: The keyword text
                - match_type: EXACT, PHRASE, or BROAD (default: BROAD)
                - cpc_bid_micros: Optional CPC bid override
            negative: Whether these are negative keywords
            existing_keywords: Keyword texts already present in this ad
                group (look them up via the existing search/GAQL tools
                first) - used only to flag duplicates in the preview,
                never fetched by this tool itself
            expectation: Which metric should move, and why - every applied
                change is auto-logged to the fixes-log sheet, and this
                becomes its "Expected Outcome" - set it, a blank hypothesis
                makes a later review meaningless
            account_name: The account's descriptive name (e.g. "boo.ua") -
                used for the fixes-log sheet's one-time title if it hasn't
                been initialized yet; harmless to omit

        Returns:
            change_id, status ("pending"), preview, exceeds_limit, and
            has_duplicates
        """
        return await service.propose_add_keywords(
            ctx=ctx,
            customer_id=customer_id,
            ad_group_id=ad_group_id,
            keywords=keywords,
            negative=negative,
            existing_keywords=existing_keywords,
            expectation=expectation,
            account_name=account_name,
        )

    async def propose_update_campaign_budget(
        ctx: Context,
        customer_id: str,
        budget_id: str,
        new_amount_micros: int,
        current_amount_micros: Optional[int] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a campaign budget amount change for human review before it
        reaches the live account. Does NOT call the Google Ads API - show
        the returned preview to the user and only call apply_pending_change
        once they've explicitly approved it.

        The ±50% change sanity check is advisory, not blocking: a bigger
        change still gets proposed, flagged in the preview and in this
        tool's returned exceeds_limit - the user's normal approve/reject
        call is what decides, not a refusal here. The check only runs if
        current_amount_micros is supplied.

        Args:
            customer_id: The customer ID
            budget_id: The campaign budget ID to update (numeric id, not
                the full resource name)
            new_amount_micros: The proposed new daily budget, in micros
            current_amount_micros: The budget's current amount, in micros -
                look it up via the existing search/GAQL tools first and
                pass it along; without it the preview has no before/after
                delta *and* the ±50% limit can't be checked
            expectation: Which metric should move, and why - every applied
                change is auto-logged to the fixes-log sheet, and this
                becomes its "Expected Outcome" - set it, a blank hypothesis
                makes a later review meaningless
            account_name: The account's descriptive name (e.g. "boo.ua") -
                used for the fixes-log sheet's one-time title if it hasn't
                been initialized yet; harmless to omit

        Returns:
            change_id, status ("pending"), preview, and an exceeds_limit flag
        """
        return await service.propose_update_campaign_budget(
            ctx=ctx,
            customer_id=customer_id,
            budget_id=budget_id,
            new_amount_micros=new_amount_micros,
            current_amount_micros=current_amount_micros,
            expectation=expectation,
            account_name=account_name,
        )

    async def propose_update_campaign_bid_target(
        ctx: Context,
        customer_id: str,
        campaign_id: str,
        bidding_strategy_type: str,
        target_cpa_micros: Optional[int] = None,
        target_roas: Optional[float] = None,
        max_conversion_value_target_roas: Optional[float] = None,
        current_value: Optional[Any] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a campaign bid-target change (Target ROAS, Target CPA,
        etc.) for human review before it reaches the live account. Does
        NOT call the Google Ads API - show the returned preview to the
        user and only call apply_pending_change once they've explicitly
        approved it.

        `bidding_strategy_type` must be the campaign's *current* strategy -
        restate it even if you're only nudging its target, not switching
        strategies. Passing a target value without it, or one that doesn't
        match the type (e.g. target_roas with MAXIMIZE_CONVERSION_VALUE
        instead of max_conversion_value_target_roas), is rejected here at
        propose time rather than silently no-op'ing at apply time.

        Args:
            customer_id: The customer ID
            campaign_id: The campaign ID to update
            bidding_strategy_type: The campaign's current bidding strategy -
                one of MANUAL_CPC, TARGET_CPA, TARGET_ROAS,
                MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE,
                TARGET_SPEND, TARGET_IMPRESSION_SHARE, PORTFOLIO
            target_cpa_micros: New target CPA in micros (for TARGET_CPA or
                MAXIMIZE_CONVERSIONS)
            target_roas: New target ROAS (for TARGET_ROAS)
            max_conversion_value_target_roas: New target ROAS (for
                MAXIMIZE_CONVERSION_VALUE)
            current_value: The current target value - look it up via the
                existing search/GAQL tools first and pass it along;
                without it the preview has no before/after delta
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
        return await service.propose_update_campaign_bid_target(
            ctx=ctx,
            customer_id=customer_id,
            campaign_id=campaign_id,
            bidding_strategy_type=bidding_strategy_type,
            target_cpa_micros=target_cpa_micros,
            target_roas=target_roas,
            max_conversion_value_target_roas=max_conversion_value_target_roas,
            current_value=current_value,
            expectation=expectation,
            account_name=account_name,
        )

    async def propose_create_rule_based_user_list(
        ctx: Context,
        customer_id: str,
        name: str,
        url_contains_patterns: List[str],
        lookback_window_days: int = 30,
        description: Optional[str] = None,
        membership_status: str = "OPEN",
        prepopulate: bool = True,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a rule-based (URL-contains) remarketing user list for
        human review before it reaches the live account - e.g. a
        "category page visitors" audience. Does NOT call the Google Ads
        API - show the returned preview to the user and only call
        apply_pending_change once they've explicitly approved it.

        Args:
            customer_id: The customer ID
            name: User list name
            url_contains_patterns: Page qualifies if its URL contains ANY
                of these strings (e.g. "/zoloti-godynnyky/")
            lookback_window_days: How far back to look for a qualifying
                visit, in days - the "7/14/30/90-day" knob for this list
                type
            description: Optional description
            membership_status: OPEN or CLOSED
            prepopulate: If True, requests backfilling from existing site
                visitors (Display Network only, last 30 days)
            expectation: Which metric should move, and why - every applied
                change is auto-logged to the fixes-log sheet, and this
                becomes its "Expected Outcome"
            account_name: The account's descriptive name (e.g. "boo.ua") -
                used for the fixes-log sheet's one-time title if it hasn't
                been initialized yet

        Returns:
            change_id, status ("pending"), and a human-readable preview
        """
        return await service.propose_create_rule_based_user_list(
            ctx=ctx,
            customer_id=customer_id,
            name=name,
            url_contains_patterns=url_contains_patterns,
            lookback_window_days=lookback_window_days,
            description=description,
            membership_status=membership_status,
            prepopulate=prepopulate,
            expectation=expectation,
            account_name=account_name,
        )

    async def propose_remove_user_list(
        ctx: Context,
        customer_id: str,
        user_list_id: str,
        user_list_name: Optional[str] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a user list removal for human review before it reaches
        the live account. Does NOT call the Google Ads API - show the
        returned preview to the user and only call apply_pending_change
        once they've explicitly approved it.

        Args:
            customer_id: The customer ID
            user_list_id: The user list ID to remove
            user_list_name: The list's current name, for a readable
                preview - look it up first, this tool doesn't fetch it
            expectation: Why this is being removed / what should follow
            account_name: The account's descriptive name (e.g. "boo.ua")

        Returns:
            change_id, status ("pending"), and a human-readable preview
        """
        return await service.propose_remove_user_list(
            ctx=ctx,
            customer_id=customer_id,
            user_list_id=user_list_id,
            user_list_name=user_list_name,
            expectation=expectation,
            account_name=account_name,
        )

    async def propose_add_negative_keywords_to_shared_set(
        ctx: Context,
        customer_id: str,
        shared_set_id: str,
        keywords: List[Dict[str, str]],
        existing_keywords: Optional[List[str]] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage negative keywords to add to a shared set for human review
        before they reach the live account - boo.ua's actual
        negative-keyword architecture (shared lists attached across many
        campaigns), not per-campaign/ad-group negatives. Does NOT call the
        Google Ads API - show the returned preview to the user and only
        call apply_pending_change once they've explicitly approved it.

        Args:
            customer_id: The customer ID
            shared_set_id: The shared set ID to add keywords to
            keywords: List of dicts with 'text' and 'match_type' (no
                cpc_bid_micros - negative criteria don't have bids)
            existing_keywords: Keyword texts already present in this
                shared set - look them up via the existing search/GAQL
                tools first; used only to flag duplicates in the preview
            expectation: Which metric should move, and why - every applied
                change is auto-logged to the fixes-log sheet, and this
                becomes its "Expected Outcome"
            account_name: The account's descriptive name (e.g. "boo.ua")

        Returns:
            change_id, status ("pending"), preview, exceeds_limit, and
            has_duplicates
        """
        return await service.propose_add_negative_keywords_to_shared_set(
            ctx=ctx,
            customer_id=customer_id,
            shared_set_id=shared_set_id,
            keywords=keywords,
            existing_keywords=existing_keywords,
            expectation=expectation,
            account_name=account_name,
        )

    async def propose_remove_shared_criterion(
        ctx: Context,
        customer_id: str,
        criterion_resource_name: str,
        criterion_description: Optional[str] = None,
        expectation: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage a shared-set criterion removal for human review before it
        reaches the live account. Does NOT call the Google Ads API - show
        the returned preview to the user and only call apply_pending_change
        once they've explicitly approved it.

        Args:
            customer_id: The customer ID
            criterion_resource_name: Full resource name of the shared
                criterion to remove
            criterion_description: The keyword text this criterion
                represents, for a readable preview - look it up first,
                this tool doesn't fetch it
            expectation: Why this is being removed / what should follow
            account_name: The account's descriptive name (e.g. "boo.ua")

        Returns:
            change_id, status ("pending"), and a human-readable preview
        """
        return await service.propose_remove_shared_criterion(
            ctx=ctx,
            customer_id=customer_id,
            criterion_resource_name=criterion_resource_name,
            criterion_description=criterion_description,
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
            propose_update_campaign_budget,
            propose_update_campaign_bid_target,
            propose_create_rule_based_user_list,
            propose_remove_user_list,
            propose_add_negative_keywords_to_shared_set,
            propose_remove_shared_criterion,
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
