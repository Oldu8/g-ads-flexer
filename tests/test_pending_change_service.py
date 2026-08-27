"""Tests for PendingChangeService (propose/apply/reject review workflow)."""

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import Context

from src.services.ad_group.ad_group_criterion_service import AdGroupCriterionService
from src.services.review.fixes_log_service import FixesLogService
from src.services.review.pending_change_service import (
    PendingChangeService,
    create_pending_change_tools,
)
from src.services.review.pending_change_store import PendingChangeStore


@pytest.fixture
def mock_ad_group_criterion_service() -> AsyncMock:
    """A mocked AdGroupCriterionService - apply_pending_change should
    delegate to this, never build Google Ads protos itself."""
    return AsyncMock(spec=AdGroupCriterionService)


@pytest.fixture
def mock_fixes_log_service() -> AsyncMock:
    """A mocked FixesLogService - every successful apply must log to this,
    automatically, without a separate explicit call."""
    return AsyncMock(spec=FixesLogService)


@pytest.fixture
def pending_change_service(
    tmp_path: Path,
    mock_ad_group_criterion_service: AsyncMock,
    mock_fixes_log_service: AsyncMock,
) -> PendingChangeService:
    store = PendingChangeStore(path=tmp_path / "pending_changes.json")
    return PendingChangeService(
        store=store,
        ad_group_criterion_service=mock_ad_group_criterion_service,
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
