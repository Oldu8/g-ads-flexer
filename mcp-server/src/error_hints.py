"""What the agent should do next when a call fails.

Two tables, both grown from failures this repo actually hit (each entry
names its source), not copied from another project:

- `ADS_ERROR_HINTS`: matched against a Google Ads API error's messages and
  error codes; `format_ads_error` appends the hint.
- `TRANSPORT_ERRORS`: matched against any tool failure text (auth, network,
  quota); the error middleware replaces the raw text with the message.

Order matters: the first match wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Hint:
    pattern: "re.Pattern[str]"
    text: str
    source: str


def _p(regex: str) -> "re.Pattern[str]":
    return re.compile(regex, re.IGNORECASE)


ADS_ERROR_HINTS: Tuple[Hint, ...] = (
    Hint(
        _p(r"page size is not supported"),
        "Do not set page_size: API v25 always pages at 10,000 rows. Use LIMIT "
        "in the GAQL query to bound the result.",
        "TRACKER.md 2026-08-13",
    ),
    Hint(
        _p(r"campaign\.(start|end)_date\b(?!_time)"),
        "In API v25 these fields are campaign.start_date_time and "
        "campaign.end_date_time (format 'yyyy-MM-dd HH:mm:ss').",
        "TRACKER.md 2026-08-13",
    ),
    Hint(
        _p(r"field.?mask|FIELD_MASK"),
        "The update mask must name the leaf field being changed, e.g. "
        "'maximize_conversion_value.target_roas', not the parent message.",
        "TRACKER.md 2026-09-08",
    ),
    Hint(
        _p(r"CUSTOMER_NOT_ENABLED"),
        "This ad account is cancelled or was never fully activated; it cannot "
        "be queried. Use another account.",
        "verify_google_access.py run 2026-09-25",
    ),
    Hint(
        _p(r"CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION"),
        "The Cloud project's Google Ads API access level does not allow "
        "production accounts. This is an operator issue, not a query issue.",
        "API v25.1 release notes, 2026-08-19",
    ),
    Hint(
        _p(r"USER_PERMISSION_DENIED"),
        "The signed-in identity cannot reach this account directly. If access "
        "goes through a manager (MCC), the manager's id must be sent as "
        "login-customer-id.",
        "verify_google_access.py C4 (manager path)",
    ),
    Hint(
        _p(r"UNRECOGNIZED_FIELD|Unrecognized field"),
        "Check the field name with google_ads_field_search_fields or "
        "google_ads_field_validate_query_fields before retrying.",
        "TRACKER.md 2026-08-13 (renamed v25 fields)",
    ),
)

RECONNECT_MESSAGE = (
    "The Google connection for this account is no longer valid (the refresh "
    "token expired or was revoked). Reconnect the account, then retry."
)
RETRY_MESSAGE = (
    "The Google Ads API did not respond. Retry once; if it fails again, "
    "narrow the request."
)
QUOTA_MESSAGE = (
    "The Google Ads API quota is exhausted for now. Stop calling the API and "
    "try again later."
)
STALE_PROCESS_MESSAGE = (
    "The MCP server process is running from a moved or deleted environment. "
    "Restart the MCP connection in the client."
)

TRANSPORT_ERRORS: Tuple[Hint, ...] = (
    Hint(
        _p(r"invalid_grant|unauthorized_client"),
        RECONNECT_MESSAGE,
        "Railway read-only server, 2026-09-25",
    ),
    Hint(
        _p(r"RESOURCE_EXHAUSTED|RESOURCE_TEMPORARILY_EXHAUSTED"),
        QUOTA_MESSAGE,
        "src/utils.py is_resource_exhausted",
    ),
    Hint(
        _p(r"DEADLINE_EXCEEDED|\bUNAVAILABLE\b|Deadline Exceeded"),
        RETRY_MESSAGE,
        "gRPC status codes surfaced by the SDK",
    ),
    Hint(
        _p(r"TLS CA certificate bundle"), STALE_PROCESS_MESSAGE, "TRACKER.md 2026-09-08"
    ),
)


def ads_error_hint(text: str) -> Optional[str]:
    """Hint for a Google Ads API error, or None."""
    return next((h.text for h in ADS_ERROR_HINTS if h.pattern.search(text)), None)


def transport_error_message(text: str) -> Optional[str]:
    """Readable replacement for an auth/network/quota failure, or None."""
    return next((h.text for h in TRANSPORT_ERRORS if h.pattern.search(text)), None)
