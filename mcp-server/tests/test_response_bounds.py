"""Bounded list results, GAQL LIMIT injection and error hints."""

from types import SimpleNamespace
from typing import Any, Iterator, cast

import pytest
from google.ads.googleads.v25.errors.types.authorization_error import (
    AuthorizationErrorEnum,
)
from google.ads.googleads.v25.errors.types.errors import ErrorCode, GoogleAdsError

from src.error_hints import (
    QUOTA_MESSAGE,
    RECONNECT_MESSAGE,
    RETRY_MESSAGE,
    ads_error_hint,
    transport_error_message,
)
from src.utils import (
    DEFAULT_ROW_CAP,
    ensure_gaql_limit,
    format_ads_error,
    list_envelope,
    row_cap,
)

# --- list_envelope -----------------------------------------------------------


def test_envelope_under_cap() -> None:
    env = list_envelope(range(120), 500)
    assert env == {"items": list(range(120)), "returned": 120, "truncated": False}


def test_envelope_over_cap_warns() -> None:
    env = list_envelope(range(3000), 500)
    assert env["returned"] == 500
    assert env["truncated"] is True
    assert "not evidence" in env["warning"].lower()


def test_envelope_reads_only_cap_plus_one() -> None:
    consumed = []

    def rows() -> Iterator[int]:
        for i in range(10_000):
            consumed.append(i)
            yield i

    list_envelope(rows(), 500)
    assert len(consumed) == 501


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", DEFAULT_ROW_CAP), ("50", 50), ("0", DEFAULT_ROW_CAP), ("x", DEFAULT_ROW_CAP)],
)
def test_row_cap_env(monkeypatch: pytest.MonkeyPatch, raw: str, expected: int) -> None:
    monkeypatch.setenv("GOOGLE_ADS_MCP_ROW_CAP", raw)
    assert row_cap() == expected


# --- ensure_gaql_limit --------------------------------------------------------


def test_limit_added_when_missing() -> None:
    assert (
        ensure_gaql_limit("SELECT campaign.id FROM campaign", 501)
        == "SELECT campaign.id FROM campaign LIMIT 501"
    )


def test_existing_limit_kept() -> None:
    query = "SELECT campaign.id FROM campaign ORDER BY campaign.id LIMIT 50"
    assert ensure_gaql_limit(query, 501) == query


def test_limit_goes_before_parameters() -> None:
    assert (
        ensure_gaql_limit("SELECT a FROM b PARAMETERS include_drafts=true", 501)
        == "SELECT a FROM b LIMIT 501 PARAMETERS include_drafts=true"
    )


# --- hints ------------------------------------------------------------------


def test_ads_hint_from_error_code() -> None:
    error = GoogleAdsError(
        message="The customer account can't be accessed because it is not yet enabled.",
        error_code=ErrorCode(
            authorization_error=AuthorizationErrorEnum.AuthorizationError.CUSTOMER_NOT_ENABLED
        ),
    )
    ex = SimpleNamespace(failure=SimpleNamespace(errors=[error]), request_id="rid-1")
    text = format_ads_error(cast(Any, ex))
    assert "not yet enabled" in text
    assert "request_id=rid-1" in text
    assert "Hint: This ad account is cancelled" in text


def test_ads_hint_for_renamed_v25_field() -> None:
    hint = ads_error_hint("Unrecognized field in the query: 'campaign.start_date'.")
    assert hint is not None and "start_date_time" in hint


def test_no_hint_for_unknown_error() -> None:
    assert ads_error_hint("Something entirely new went wrong") is None


@pytest.mark.parametrize(
    ("text", "message"),
    [
        # invalid_grant wins over the 503 in the same text (Railway, 2026-09-25).
        ("503 Getting metadata from plugin failed: invalid_grant", RECONNECT_MESSAGE),
        ("StatusCode.RESOURCE_EXHAUSTED quota", QUOTA_MESSAGE),
        ("StatusCode.DEADLINE_EXCEEDED", RETRY_MESSAGE),
        ("StatusCode.UNAVAILABLE failed to connect", RETRY_MESSAGE),
    ],
)
def test_transport_messages(text: str, message: str) -> None:
    assert transport_error_message(text) == message


def test_ordinary_error_not_translated() -> None:
    assert transport_error_message("Google Ads API error: Invalid budget") is None
