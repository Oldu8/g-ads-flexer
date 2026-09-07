"""Tests for PendingChangeService (propose/apply/reject review workflow)."""

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import Context

from src.services.ad_group.ad_group_criterion_service import AdGroupCriterionService
from src.services.audiences.user_list_service import UserListService
from src.services.bidding.budget_service import BudgetService
from src.services.campaign.campaign_service import CampaignService
from src.services.review.fixes_log_service import FixesLogService
from src.services.review.pending_change_service import (
    PendingChangeService,
    create_pending_change_tools,
)
from src.services.review.pending_change_store import PendingChangeStore
from src.services.shared.shared_criterion_service import SharedCriterionService


@pytest.fixture
def mock_ad_group_criterion_service() -> AsyncMock:
    """A mocked AdGroupCriterionService - apply_pending_change should
    delegate to this, never build Google Ads protos itself."""
    return AsyncMock(spec=AdGroupCriterionService)


@pytest.fixture
def mock_budget_service() -> AsyncMock:
    """A mocked BudgetService - apply_pending_change should delegate budget
    changes to this, never build Google Ads protos itself."""
    return AsyncMock(spec=BudgetService)


@pytest.fixture
def mock_campaign_service() -> AsyncMock:
    """A mocked CampaignService - apply_pending_change should delegate
    bid-target changes to this, never build Google Ads protos itself."""
    return AsyncMock(spec=CampaignService)


@pytest.fixture
def mock_user_list_service() -> AsyncMock:
    """A mocked UserListService - apply_pending_change should delegate
    audience create/remove to this, never build Google Ads protos itself."""
    return AsyncMock(spec=UserListService)


@pytest.fixture
def mock_shared_criterion_service() -> AsyncMock:
    """A mocked SharedCriterionService - apply_pending_change should
    delegate shared-set negative-keyword add/remove to this, never build
    Google Ads protos itself."""
    return AsyncMock(spec=SharedCriterionService)


@pytest.fixture
def mock_fixes_log_service() -> AsyncMock:
    """A mocked FixesLogService - every successful apply must log to this,
    automatically, without a separate explicit call."""
    return AsyncMock(spec=FixesLogService)


@pytest.fixture
def pending_change_service(
    tmp_path: Path,
    mock_ad_group_criterion_service: AsyncMock,
    mock_budget_service: AsyncMock,
    mock_campaign_service: AsyncMock,
    mock_user_list_service: AsyncMock,
    mock_shared_criterion_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
) -> PendingChangeService:
    store = PendingChangeStore(path=tmp_path / "pending_changes.json")
    return PendingChangeService(
        store=store,
        ad_group_criterion_service=mock_ad_group_criterion_service,
        budget_service=mock_budget_service,
        campaign_service=mock_campaign_service,
        user_list_service=mock_user_list_service,
        shared_criterion_service=mock_shared_criterion_service,
        fixes_log_service=mock_fixes_log_service,
    )


# ---------------------------------------------------------------------------
# propose_add_keywords
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_add_keywords_does_not_call_api(
    pending_change_service: PendingChangeService,
    mock_ad_group_criterion_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    """Proposing a change must never touch the live account."""
    result = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[
            {"text": "buy shoes online", "match_type": "PHRASE"},
            {"text": "cheap sneakers", "match_type": "BROAD"},
        ],
    )

    assert result["status"] == "pending"
    assert result["change_id"].startswith("pc_")
    assert "buy shoes online" in result["preview"]
    assert "cheap sneakers" in result["preview"]
    mock_ad_group_criterion_service.add_keywords.assert_not_called()


@pytest.mark.asyncio
async def test_propose_add_keywords_preview_flags_negative(
    pending_change_service: PendingChangeService,
    mock_ctx: Context,
) -> None:
    result = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "competitor brand", "match_type": "EXACT"}],
        negative=True,
    )

    assert "NEGATIVE" in result["preview"]
    assert "competitor brand" in result["preview"]


@pytest.mark.asyncio
async def test_propose_add_keywords_empty_list_raises(
    pending_change_service: PendingChangeService,
    mock_ctx: Context,
) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        await pending_change_service.propose_add_keywords(
            ctx=mock_ctx,
            customer_id="1234567890",
            ad_group_id="111222",
            keywords=[],
        )


@pytest.mark.asyncio
async def test_propose_add_keywords_missing_text_raises(
    pending_change_service: PendingChangeService,
    mock_ctx: Context,
) -> None:
    with pytest.raises(ValueError, match="text"):
        await pending_change_service.propose_add_keywords(
            ctx=mock_ctx,
            customer_id="1234567890",
            ad_group_id="111222",
            keywords=[{"match_type": "BROAD"}],
        )


# ---------------------------------------------------------------------------
# list_pending_changes / get_pending_change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pending_changes_defaults_to_pending_only(
    pending_change_service: PendingChangeService,
    mock_ad_group_criterion_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_ad_group_criterion_service.add_keywords.return_value = {"results": []}

    proposed = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "kw one"}],
    )
    applied = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "kw two"}],
    )
    await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=applied["change_id"]
    )

    pending_only = await pending_change_service.list_pending_changes(ctx=mock_ctx)

    assert [c["change_id"] for c in pending_only] == [proposed["change_id"]]


@pytest.mark.asyncio
async def test_get_pending_change_returns_full_record(
    pending_change_service: PendingChangeService,
    mock_ctx: Context,
) -> None:
    proposed = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "kw one"}],
    )

    record = await pending_change_service.get_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    assert record["params"]["ad_group_id"] == "111222"
    assert record["params"]["keywords"] == [{"text": "kw one"}]


@pytest.mark.asyncio
async def test_get_pending_change_missing_raises(
    pending_change_service: PendingChangeService,
    mock_ctx: Context,
) -> None:
    with pytest.raises(Exception, match="No pending change"):
        await pending_change_service.get_pending_change(
            ctx=mock_ctx, change_id="pc_doesnotexist"
        )


# ---------------------------------------------------------------------------
# apply_pending_change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_pending_change_calls_ad_group_criterion_service(
    pending_change_service: PendingChangeService,
    mock_ad_group_criterion_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_ad_group_criterion_service.add_keywords.return_value = {
        "results": [{"resource_name": "customers/1234567890/adGroupCriteria/111~222"}]
    }

    proposed = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "buy shoes online", "match_type": "PHRASE"}],
        negative=False,
        expectation="Impressions should rise on brand terms",
        account_name="boo.ua",
    )

    result = await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    mock_ad_group_criterion_service.add_keywords.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "buy shoes online", "match_type": "PHRASE"}],
        negative=False,
    )
    assert result["status"] == "applied"
    assert result["result"] == mock_ad_group_criterion_service.add_keywords.return_value
    assert result["fixes_log_error"] is None

    # Every successful apply must be auto-logged - no separate call needed.
    mock_fixes_log_service.log_fix.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id=proposed["change_id"],
        what="Added keywords",
        fix_text=proposed["preview"],
        when=date.today().isoformat(),
        expectation="Impressions should rise on brand terms",
        account_name="boo.ua",
    )

    # A second apply must not be allowed to re-run the mutation.
    with pytest.raises(Exception, match="already 'applied'"):
        await pending_change_service.apply_pending_change(
            ctx=mock_ctx, change_id=proposed["change_id"]
        )
    mock_ad_group_criterion_service.add_keywords.assert_called_once()
    mock_fixes_log_service.log_fix.assert_called_once()  # not called again


@pytest.mark.asyncio
async def test_apply_pending_change_negative_keywords_label(
    pending_change_service: PendingChangeService,
    mock_ad_group_criterion_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_ad_group_criterion_service.add_keywords.return_value = {"results": []}

    proposed = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "competitor brand"}],
        negative=True,
    )

    await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    assert (
        mock_fixes_log_service.log_fix.call_args.kwargs["what"]
        == "Added negative keywords"
    )
    assert (
        mock_fixes_log_service.log_fix.call_args.kwargs["expectation"]
        == "(not specified)"
    )


@pytest.mark.asyncio
async def test_apply_pending_change_survives_fixes_log_failure(
    pending_change_service: PendingChangeService,
    mock_ad_group_criterion_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    """A Sheets-side failure must not make it look like the Ads mutation
    didn't happen - it already did, and can't be undone by a logging
    problem downstream."""
    mock_ad_group_criterion_service.add_keywords.return_value = {"results": []}
    mock_fixes_log_service.log_fix.side_effect = Exception("no sheet configured")

    proposed = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "buy shoes online"}],
    )

    result = await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    assert result["status"] == "applied"
    assert result["fixes_log_error"] == "no sheet configured"


@pytest.mark.asyncio
async def test_apply_pending_change_missing_id_raises(
    pending_change_service: PendingChangeService,
    mock_ad_group_criterion_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    with pytest.raises(Exception, match="No pending change"):
        await pending_change_service.apply_pending_change(
            ctx=mock_ctx, change_id="pc_doesnotexist"
        )
    mock_ad_group_criterion_service.add_keywords.assert_not_called()


# ---------------------------------------------------------------------------
# reject_pending_change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_pending_change_never_calls_api(
    pending_change_service: PendingChangeService,
    mock_ad_group_criterion_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    proposed = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "competitor brand name"}],
    )

    result = await pending_change_service.reject_pending_change(
        ctx=mock_ctx,
        change_id=proposed["change_id"],
        reason="matches a competitor brand",
    )

    assert result["status"] == "rejected"
    assert result["rejected_reason"] == "matches a competitor brand"
    mock_ad_group_criterion_service.add_keywords.assert_not_called()

    # A rejected change must not be applicable afterwards.
    with pytest.raises(Exception, match="already 'rejected'"):
        await pending_change_service.apply_pending_change(
            ctx=mock_ctx, change_id=proposed["change_id"]
        )


@pytest.mark.asyncio
async def test_reject_pending_change_missing_id_raises(
    pending_change_service: PendingChangeService,
    mock_ctx: Context,
) -> None:
    with pytest.raises(Exception, match="No pending change"):
        await pending_change_service.reject_pending_change(
            ctx=mock_ctx, change_id="pc_doesnotexist"
        )


# ---------------------------------------------------------------------------
# Tool wrappers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_wrapper_propose_then_apply_round_trip(
    pending_change_service: PendingChangeService,
    mock_ad_group_criterion_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_ad_group_criterion_service.add_keywords.return_value = {"results": []}
    tools: list[Any] = create_pending_change_tools(pending_change_service)
    by_name = {tool.__name__: tool for tool in tools}

    proposed = await by_name["propose_add_keywords"](
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "brand keyword"}],
    )
    applied = await by_name["apply_pending_change"](
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    assert applied["status"] == "applied"
    mock_ad_group_criterion_service.add_keywords.assert_called_once()


# ---------------------------------------------------------------------------
# propose_update_campaign_budget / apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_update_campaign_budget_does_not_call_api(
    pending_change_service: PendingChangeService,
    mock_budget_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    result = await pending_change_service.propose_update_campaign_budget(
        ctx=mock_ctx,
        customer_id="1234567890",
        budget_id="555",
        new_amount_micros=20_000_000,
        current_amount_micros=15_000_000,
    )

    assert result["status"] == "pending"
    assert "15.00" in result["preview"]
    assert "20.00" in result["preview"]
    mock_budget_service.update_campaign_budget.assert_not_called()


@pytest.mark.asyncio
async def test_propose_update_campaign_budget_rejects_non_positive_amount(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    with pytest.raises(ValueError, match="positive"):
        await pending_change_service.propose_update_campaign_budget(
            ctx=mock_ctx,
            customer_id="1234567890",
            budget_id="555",
            new_amount_micros=0,
        )


@pytest.mark.asyncio
async def test_apply_update_campaign_budget_calls_budget_service(
    pending_change_service: PendingChangeService,
    mock_budget_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_budget_service.update_campaign_budget.return_value = {"results": []}

    proposed = await pending_change_service.propose_update_campaign_budget(
        ctx=mock_ctx,
        customer_id="1234567890",
        budget_id="555",
        new_amount_micros=20_000_000,
        current_amount_micros=15_000_000,
        expectation="Volume should rise",
        account_name="boo.ua",
    )

    result = await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    mock_budget_service.update_campaign_budget.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        budget_id="555",
        amount_micros=20_000_000,
    )
    assert result["status"] == "applied"
    mock_fixes_log_service.log_fix.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id=proposed["change_id"],
        what="Updated campaign budget",
        fix_text=proposed["preview"],
        when=date.today().isoformat(),
        expectation="Volume should rise",
        account_name="boo.ua",
    )


# ---------------------------------------------------------------------------
# propose_update_campaign_bid_target / apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_update_campaign_bid_target_does_not_call_api(
    pending_change_service: PendingChangeService,
    mock_campaign_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    result = await pending_change_service.propose_update_campaign_bid_target(
        ctx=mock_ctx,
        customer_id="1234567890",
        campaign_id="999",
        bidding_strategy_type="maximize_conversion_value",
        max_conversion_value_target_roas=8.5,
        current_value=7.0,
    )

    assert result["status"] == "pending"
    assert "7.0" in result["preview"]
    assert "8.5" in result["preview"]
    mock_campaign_service.update_campaign.assert_not_called()


@pytest.mark.asyncio
async def test_propose_update_campaign_bid_target_unknown_strategy_raises(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    with pytest.raises(ValueError, match="Unsupported bidding_strategy_type"):
        await pending_change_service.propose_update_campaign_bid_target(
            ctx=mock_ctx,
            customer_id="1234567890",
            campaign_id="999",
            bidding_strategy_type="NOT_A_REAL_STRATEGY",
            target_roas=5.0,
        )


@pytest.mark.asyncio
async def test_propose_update_campaign_bid_target_no_target_value_raises(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    with pytest.raises(ValueError, match="At least one of"):
        await pending_change_service.propose_update_campaign_bid_target(
            ctx=mock_ctx,
            customer_id="1234567890",
            campaign_id="999",
            bidding_strategy_type="TARGET_ROAS",
        )


@pytest.mark.asyncio
async def test_propose_update_campaign_bid_target_mismatched_param_raises(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    """MAXIMIZE_CONVERSION_VALUE needs max_conversion_value_target_roas,
    not target_roas - the exact silent-no-op trap the 2026-08-17 fix in
    campaign_service.py closed; this must reject it up front instead."""
    with pytest.raises(ValueError, match="expects 'max_conversion_value_target_roas'"):
        await pending_change_service.propose_update_campaign_bid_target(
            ctx=mock_ctx,
            customer_id="1234567890",
            campaign_id="999",
            bidding_strategy_type="MAXIMIZE_CONVERSION_VALUE",
            target_roas=5.0,
        )


@pytest.mark.asyncio
async def test_apply_update_campaign_bid_target_calls_campaign_service(
    pending_change_service: PendingChangeService,
    mock_campaign_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_campaign_service.update_campaign.return_value = {"results": []}

    proposed = await pending_change_service.propose_update_campaign_bid_target(
        ctx=mock_ctx,
        customer_id="1234567890",
        campaign_id="999",
        bidding_strategy_type="MAXIMIZE_CONVERSION_VALUE",
        max_conversion_value_target_roas=8.5,
        current_value=7.0,
        expectation="ROAS should hold, volume may drop slightly",
        account_name="boo.ua",
    )

    result = await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    mock_campaign_service.update_campaign.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        campaign_id="999",
        bidding_strategy_type="MAXIMIZE_CONVERSION_VALUE",
        target_cpa_micros=None,
        target_roas=None,
        max_conversion_value_target_roas=8.5,
    )
    assert result["status"] == "applied"
    mock_fixes_log_service.log_fix.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id=proposed["change_id"],
        what="Updated campaign bid target",
        fix_text=proposed["preview"],
        when=date.today().isoformat(),
        expectation="ROAS should hold, volume may drop slightly",
        account_name="boo.ua",
    )


# ---------------------------------------------------------------------------
# Sanity limits (advisory, not blocking - 2026-08-27)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_update_campaign_budget_flags_over_50_pct_change(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    """A >50% change is still proposed (not rejected) - just flagged."""
    result = await pending_change_service.propose_update_campaign_budget(
        ctx=mock_ctx,
        customer_id="1234567890",
        budget_id="555",
        new_amount_micros=30_000_000,
        current_amount_micros=15_000_000,  # +100%
    )

    assert result["status"] == "pending"
    assert result["exceeds_limit"] is True
    assert "EXCEEDS LIMIT" in result["preview"]


@pytest.mark.asyncio
async def test_propose_update_campaign_budget_under_50_pct_not_flagged(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    result = await pending_change_service.propose_update_campaign_budget(
        ctx=mock_ctx,
        customer_id="1234567890",
        budget_id="555",
        new_amount_micros=18_000_000,
        current_amount_micros=15_000_000,  # +20%
    )

    assert result["exceeds_limit"] is False
    assert "EXCEEDS LIMIT" not in result["preview"]


@pytest.mark.asyncio
async def test_propose_update_campaign_budget_no_current_value_not_flagged(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    """Without current_amount_micros there's nothing to compare against -
    the check silently doesn't run (the preview says why, but it's not an
    error)."""
    result = await pending_change_service.propose_update_campaign_budget(
        ctx=mock_ctx,
        customer_id="1234567890",
        budget_id="555",
        new_amount_micros=30_000_000,
    )

    assert result["exceeds_limit"] is False
    assert "cannot verify" in result["preview"]


@pytest.mark.asyncio
async def test_propose_add_keywords_flags_over_50_count(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    keywords = [{"text": f"keyword {i}"} for i in range(51)]

    result = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=keywords,
    )

    assert result["status"] == "pending"
    assert result["exceeds_limit"] is True
    assert "EXCEEDS LIMIT" in result["preview"]


@pytest.mark.asyncio
async def test_propose_add_keywords_50_count_not_flagged(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    """Exactly at the limit (50) should not trip it - only strictly over."""
    keywords = [{"text": f"keyword {i}"} for i in range(50)]

    result = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=keywords,
    )

    assert result["exceeds_limit"] is False


@pytest.mark.asyncio
async def test_propose_add_keywords_flags_duplicates(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    result = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "Buy Shoes"}, {"text": "cheap sneakers"}],
        existing_keywords=["buy shoes", "boots"],
    )

    assert result["has_duplicates"] is True
    assert "DUPLICATE" in result["preview"]
    # only the actual duplicate is flagged, not the non-duplicate one
    assert result["preview"].count("DUPLICATE") == 1


@pytest.mark.asyncio
async def test_propose_add_keywords_no_existing_keywords_not_flagged(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    result = await pending_change_service.propose_add_keywords(
        ctx=mock_ctx,
        customer_id="1234567890",
        ad_group_id="111222",
        keywords=[{"text": "buy shoes"}],
    )

    assert result["has_duplicates"] is False
    assert "DUPLICATE" not in result["preview"]


# ---------------------------------------------------------------------------
# propose_create_rule_based_user_list / apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_create_rule_based_user_list_does_not_call_api(
    pending_change_service: PendingChangeService,
    mock_user_list_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    result = await pending_change_service.propose_create_rule_based_user_list(
        ctx=mock_ctx,
        customer_id="1234567890",
        name="Gold users / 30 / 2026",
        url_contains_patterns=["/zoloti-godynnyky/", "/zoloti-serezhky/"],
        lookback_window_days=30,
    )

    assert result["status"] == "pending"
    assert "/zoloti-godynnyky/" in result["preview"]
    assert "/zoloti-serezhky/" in result["preview"]
    assert "30-day" in result["preview"]
    mock_user_list_service.create_rule_based_user_list.assert_not_called()


@pytest.mark.asyncio
async def test_propose_create_rule_based_user_list_empty_patterns_raises(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        await pending_change_service.propose_create_rule_based_user_list(
            ctx=mock_ctx,
            customer_id="1234567890",
            name="Empty",
            url_contains_patterns=[],
        )


@pytest.mark.asyncio
async def test_apply_create_rule_based_user_list_calls_user_list_service(
    pending_change_service: PendingChangeService,
    mock_user_list_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_user_list_service.create_rule_based_user_list.return_value = {
        "results": [{"resource_name": "customers/1234567890/userLists/999"}]
    }

    proposed = await pending_change_service.propose_create_rule_based_user_list(
        ctx=mock_ctx,
        customer_id="1234567890",
        name="Gold users / 30 / 2026",
        url_contains_patterns=["/zoloti-godynnyky/"],
        lookback_window_days=30,
        expectation="Audience should grow within 1-2 weeks",
        account_name="boo.ua",
    )

    result = await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    mock_user_list_service.create_rule_based_user_list.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        name="Gold users / 30 / 2026",
        url_contains_patterns=["/zoloti-godynnyky/"],
        lookback_window_days=30,
        description=None,
        membership_status="OPEN",
        prepopulate=True,
    )
    assert result["status"] == "applied"
    mock_fixes_log_service.log_fix.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id=proposed["change_id"],
        what="Created rule-based user list",
        fix_text=proposed["preview"],
        when=date.today().isoformat(),
        expectation="Audience should grow within 1-2 weeks",
        account_name="boo.ua",
    )


# ---------------------------------------------------------------------------
# propose_remove_user_list / apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_remove_user_list_does_not_call_api(
    pending_change_service: PendingChangeService,
    mock_user_list_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    result = await pending_change_service.propose_remove_user_list(
        ctx=mock_ctx,
        customer_id="1234567890",
        user_list_id="746722256",
        user_list_name="Розница: пользователи, не завершившие покупку (AdWords)",
    )

    assert result["status"] == "pending"
    assert "746722256" in result["preview"]
    assert "Розница" in result["preview"]
    mock_user_list_service.remove_user_list.assert_not_called()


@pytest.mark.asyncio
async def test_apply_remove_user_list_calls_user_list_service(
    pending_change_service: PendingChangeService,
    mock_user_list_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_user_list_service.remove_user_list.return_value = {
        "results": [{"resource_name": "customers/1234567890/userLists/746722256"}]
    }

    proposed = await pending_change_service.propose_remove_user_list(
        ctx=mock_ctx,
        customer_id="1234567890",
        user_list_id="746722256",
        expectation="Cleanup - list is empty and stale",
        account_name="boo.ua",
    )

    result = await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    mock_user_list_service.remove_user_list.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        user_list_id="746722256",
    )
    assert result["status"] == "applied"
    mock_fixes_log_service.log_fix.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id=proposed["change_id"],
        what="Removed user list",
        fix_text=proposed["preview"],
        when=date.today().isoformat(),
        expectation="Cleanup - list is empty and stale",
        account_name="boo.ua",
    )


# ---------------------------------------------------------------------------
# propose_add_negative_keywords_to_shared_set / apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_add_negative_keywords_to_shared_set_does_not_call_api(
    pending_change_service: PendingChangeService,
    mock_shared_criterion_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    result = await pending_change_service.propose_add_negative_keywords_to_shared_set(
        ctx=mock_ctx,
        customer_id="1234567890",
        shared_set_id="2079557334",
        keywords=[{"text": "техносток", "match_type": "BROAD"}],
    )

    assert result["status"] == "pending"
    assert "техносток" in result["preview"]
    mock_shared_criterion_service.add_keywords_to_shared_set.assert_not_called()


@pytest.mark.asyncio
async def test_propose_add_negative_keywords_to_shared_set_empty_list_raises(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        await pending_change_service.propose_add_negative_keywords_to_shared_set(
            ctx=mock_ctx,
            customer_id="1234567890",
            shared_set_id="2079557334",
            keywords=[],
        )


@pytest.mark.asyncio
async def test_propose_add_negative_keywords_to_shared_set_flags_duplicates(
    pending_change_service: PendingChangeService, mock_ctx: Context
) -> None:
    result = await pending_change_service.propose_add_negative_keywords_to_shared_set(
        ctx=mock_ctx,
        customer_id="1234567890",
        shared_set_id="2079557334",
        keywords=[{"text": "Техносток", "match_type": "BROAD"}],
        existing_keywords=["техносток"],
    )

    assert result["has_duplicates"] is True
    assert "DUPLICATE" in result["preview"]


@pytest.mark.asyncio
async def test_apply_add_negative_keywords_to_shared_set_calls_shared_criterion_service(
    pending_change_service: PendingChangeService,
    mock_shared_criterion_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_shared_criterion_service.add_keywords_to_shared_set.return_value = [
        {"resource_name": "customers/1234567890/sharedCriteria/2079557334~1"}
    ]

    proposed = await pending_change_service.propose_add_negative_keywords_to_shared_set(
        ctx=mock_ctx,
        customer_id="1234567890",
        shared_set_id="2079557334",
        keywords=[{"text": "техносток", "match_type": "BROAD"}],
        expectation="Reduce wasted spend from competitor-brand searches",
        account_name="boo.ua",
    )

    result = await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    mock_shared_criterion_service.add_keywords_to_shared_set.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        shared_set_id="2079557334",
        keywords=[{"text": "техносток", "match_type": "BROAD"}],
    )
    assert result["status"] == "applied"
    mock_fixes_log_service.log_fix.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id=proposed["change_id"],
        what="Added negative keywords to shared set",
        fix_text=proposed["preview"],
        when=date.today().isoformat(),
        expectation="Reduce wasted spend from competitor-brand searches",
        account_name="boo.ua",
    )


# ---------------------------------------------------------------------------
# propose_remove_shared_criterion / apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_remove_shared_criterion_does_not_call_api(
    pending_change_service: PendingChangeService,
    mock_shared_criterion_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    result = await pending_change_service.propose_remove_shared_criterion(
        ctx=mock_ctx,
        customer_id="1234567890",
        criterion_resource_name="customers/1234567890/sharedCriteria/2079557334~1",
        criterion_description="техносток",
    )

    assert result["status"] == "pending"
    assert "техносток" in result["preview"]
    mock_shared_criterion_service.remove_shared_criterion.assert_not_called()


@pytest.mark.asyncio
async def test_apply_remove_shared_criterion_calls_shared_criterion_service(
    pending_change_service: PendingChangeService,
    mock_shared_criterion_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
    mock_ctx: Context,
) -> None:
    mock_shared_criterion_service.remove_shared_criterion.return_value = {
        "results": [
            {"resource_name": "customers/1234567890/sharedCriteria/2079557334~1"}
        ]
    }

    proposed = await pending_change_service.propose_remove_shared_criterion(
        ctx=mock_ctx,
        customer_id="1234567890",
        criterion_resource_name="customers/1234567890/sharedCriteria/2079557334~1",
        expectation="No longer relevant",
        account_name="boo.ua",
    )

    result = await pending_change_service.apply_pending_change(
        ctx=mock_ctx, change_id=proposed["change_id"]
    )

    mock_shared_criterion_service.remove_shared_criterion.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        criterion_resource_name="customers/1234567890/sharedCriteria/2079557334~1",
    )
    assert result["status"] == "applied"
    mock_fixes_log_service.log_fix.assert_called_once_with(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id=proposed["change_id"],
        what="Removed shared criterion",
        fix_text=proposed["preview"],
        when=date.today().isoformat(),
        expectation="No longer relevant",
        account_name="boo.ua",
    )
