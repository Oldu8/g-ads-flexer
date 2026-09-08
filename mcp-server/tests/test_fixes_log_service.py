"""Tests for FixesLogService."""

from typing import Any, Dict
from unittest.mock import Mock

import pytest
from fastmcp import Context

from src.services.review.fixes_log_service import (
    DEFAULT_STATUS,
    FixesLogService,
    create_fixes_log_tools,
)
from src.services.review.fixes_log_sheet import FixesLogSheet


@pytest.fixture
def mock_sheet() -> Mock:
    sheet = Mock(spec=FixesLogSheet)
    # append_fix now returns the id actually stored (which only differs
    # from the requested one on a collision) - default to echoing the
    # requested id back, matching real no-collision behavior; tests that
    # care about the disambiguation path override this explicitly.
    sheet.append_fix.side_effect = lambda fix_id, **kwargs: fix_id
    return sheet


@pytest.fixture
def sheet_resolver(mock_sheet: Mock) -> Any:
    """A resolver that hands back the one mock sheet regardless of
    customer_id - fine for single-account tests."""
    calls: list[str] = []

    def _resolver(customer_id: str, account_name: Any = None) -> Mock:
        calls.append(customer_id)
        return mock_sheet

    _resolver.calls = calls  # type: ignore[attr-defined]
    return _resolver


@pytest.fixture
def service(sheet_resolver: Any) -> FixesLogService:
    return FixesLogService(sheet_resolver=sheet_resolver)


@pytest.mark.asyncio
async def test_log_fix_appends_with_default_status(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context
) -> None:
    result = await service.log_fix(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id="F-1",
        what="Added keywords",
        fix_text="details...",
        when="2026-08-27",
        expectation="IS should recover",
    )

    mock_sheet.append_fix.assert_called_once_with(
        fix_id="F-1",
        what="Added keywords",
        fix_text="details...",
        status=DEFAULT_STATUS,
        when="2026-08-27",
        expectation="IS should recover",
    )
    assert result == {"fix_id": "F-1", "status": DEFAULT_STATUS}


@pytest.mark.asyncio
async def test_log_fix_custom_status(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context
) -> None:
    result = await service.log_fix(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id="F-2",
        what="x",
        fix_text="y",
        when="2026-08-27",
        expectation="z",
        status="custom",
    )

    assert result == {"fix_id": "F-2", "status": "custom"}


@pytest.mark.asyncio
async def test_log_fix_surfaces_disambiguated_id(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context
) -> None:
    """When the sheet had to disambiguate a colliding id, the service must
    return *that* id, not the one the caller originally asked for - it's
    the one a later review update actually needs."""
    mock_sheet.append_fix.side_effect = None
    mock_sheet.append_fix.return_value = "F-1b"

    result = await service.log_fix(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id="F-1",
        what="x",
        fix_text="y",
        when="2026-08-27",
        expectation="z",
    )

    assert result == {"fix_id": "F-1b", "status": DEFAULT_STATUS}


@pytest.mark.asyncio
async def test_list_fixes_returns_sheet_rows(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context
) -> None:
    mock_sheet.list_rows.return_value = [{"What": "a"}]

    result = await service.list_fixes(ctx=mock_ctx, customer_id="1234567890")

    assert result == [{"What": "a"}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "period,column",
    [
        ("week", "1-Week Review"),
        ("2weeks", "2-Week Review"),
        ("month", "1-Month Review"),
    ],
)
async def test_update_fix_review_writes_correct_column(
    service: FixesLogService,
    mock_sheet: Mock,
    mock_ctx: Context,
    period: str,
    column: str,
) -> None:
    result = await service.update_fix_review(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id="F-1",
        period=period,
        note="IS recovered",
    )

    mock_sheet.update_cell.assert_called_once_with("F-1", column, "IS recovered")
    assert result == {"fix_id": "F-1", "column": column, "note": "IS recovered"}


@pytest.mark.asyncio
async def test_update_fix_review_invalid_period_raises(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context
) -> None:
    with pytest.raises(ValueError, match="period must be one of"):
        await service.update_fix_review(
            ctx=mock_ctx,
            customer_id="1234567890",
            fix_id="F-1",
            period="year",
            note="x",
        )
    mock_sheet.update_cell.assert_not_called()


@pytest.mark.asyncio
async def test_update_fix_conclusion_without_status(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context
) -> None:
    result = await service.update_fix_conclusion(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id="F-1",
        conclusion="Worked as expected",
    )

    mock_sheet.update_cell.assert_called_once_with(
        "F-1", "Conclusion", "Worked as expected"
    )
    assert result == {
        "fix_id": "F-1",
        "conclusion": "Worked as expected",
        "status": None,
    }


@pytest.mark.asyncio
async def test_update_fix_conclusion_with_status(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context
) -> None:
    await service.update_fix_conclusion(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id="F-1",
        conclusion="Worked",
        status="confirmed_positive",
    )

    assert mock_sheet.update_cell.call_count == 2
    mock_sheet.update_cell.assert_any_call("F-1", "Conclusion", "Worked")
    mock_sheet.update_cell.assert_any_call("F-1", "Status", "confirmed_positive")


@pytest.mark.asyncio
async def test_tool_wrapper_log_fix_round_trip(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context
) -> None:
    tools: list[Any] = create_fixes_log_tools(service)
    by_name = {tool.__name__: tool for tool in tools}

    result = await by_name["log_fix"](
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id="F-1",
        what="x",
        fix_text="y",
        when="2026-08-27",
        expectation="z",
    )

    assert result["fix_id"] == "F-1"
    mock_sheet.append_fix.assert_called_once()


# ---------------------------------------------------------------------------
# Per-account routing / caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolver_called_once_per_account_then_cached(
    mock_ctx: Context,
) -> None:
    """Repeat calls for the same account reuse the resolved sheet instead
    of re-resolving/re-authenticating every time."""
    mock_sheet = Mock(spec=FixesLogSheet)
    call_count = 0

    def resolver(customer_id: str, account_name: Any = None) -> Mock:
        nonlocal call_count
        call_count += 1
        return mock_sheet

    service = FixesLogService(sheet_resolver=resolver)

    await service.list_fixes(ctx=mock_ctx, customer_id="1234567890")
    await service.list_fixes(
        ctx=mock_ctx, customer_id="123-456-7890"
    )  # same, hyphenated

    assert call_count == 1


@pytest.mark.asyncio
async def test_different_accounts_route_to_different_sheets(
    mock_ctx: Context,
) -> None:
    """The core guarantee this fix is for: one account's fix never lands in
    another account's sheet."""
    sheets: Dict[str, Mock] = {
        "1111111111": Mock(spec=FixesLogSheet),
        "2222222222": Mock(spec=FixesLogSheet),
    }

    def resolver(customer_id: str, account_name: Any = None) -> Mock:
        return sheets[customer_id]

    service = FixesLogService(sheet_resolver=resolver)

    await service.log_fix(
        ctx=mock_ctx,
        customer_id="1111111111",
        fix_id="F-1",
        what="x",
        fix_text="y",
        when="2026-08-27",
        expectation="z",
    )
    await service.log_fix(
        ctx=mock_ctx,
        customer_id="2222222222",
        fix_id="F-2",
        what="x",
        fix_text="y",
        when="2026-08-27",
        expectation="z",
    )

    sheets["1111111111"].append_fix.assert_called_once()
    sheets["2222222222"].append_fix.assert_called_once()
    assert sheets["1111111111"].append_fix.call_args.kwargs["fix_id"] == "F-1"
    assert sheets["2222222222"].append_fix.call_args.kwargs["fix_id"] == "F-2"


@pytest.mark.asyncio
async def test_log_fix_forwards_account_name_to_resolver(
    mock_ctx: Context,
) -> None:
    """account_name is only meaningful on first resolution (for the
    one-time sheet title) - confirm it actually reaches the resolver."""
    mock_sheet = Mock(spec=FixesLogSheet)
    seen_account_names: list[Any] = []

    def resolver(customer_id: str, account_name: Any = None) -> Mock:
        seen_account_names.append(account_name)
        return mock_sheet

    service = FixesLogService(sheet_resolver=resolver)

    await service.log_fix(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id="F-1",
        what="x",
        fix_text="y",
        when="2026-08-27",
        expectation="z",
        account_name="boo.ua",
    )

    assert seen_account_names == ["boo.ua"]


# ---------------------------------------------------------------------------
# Date format validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_fix_accepts_iso_date(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context
) -> None:
    await service.log_fix(
        ctx=mock_ctx,
        customer_id="1234567890",
        fix_id="F-1",
        what="x",
        fix_text="y",
        when="2026-08-27",
        expectation="z",
    )

    mock_sheet.append_fix.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_date",
    [
        "27.08.2026",
        "08/27/2026",
        "2026-08-27T00:00:00",
        "Aug 27, 2026",
        "2026/08/27",
        "not a date",
    ],
)
async def test_log_fix_rejects_non_iso_date(
    service: FixesLogService, mock_sheet: Mock, mock_ctx: Context, bad_date: str
) -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        await service.log_fix(
            ctx=mock_ctx,
            customer_id="1234567890",
            fix_id="F-1",
            what="x",
            fix_text="y",
            when=bad_date,
            expectation="z",
        )
    mock_sheet.append_fix.assert_not_called()
