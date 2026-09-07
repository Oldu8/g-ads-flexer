"""Google Sheets-backed store for the "fixes log" - a running record of live
changes made to a managed account, so results can be checked back against
expectations later. See the 2026-08-27 TRACKER.md entries for the full
rationale; this replaces the earlier `snapshots/fixes_log.json` file-based
version - the user wants the sheet itself to be the sole source of truth
(no separate local file to keep in sync).

**Auth: a Google Cloud service account, not OAuth.** The onboarding story
for a client is "share your Google Sheet with this email address, same as
sharing with a colleague" - no OAuth consent screen, no per-client refresh
token. One-time setup (done outside this codebase, in Google Cloud
Console):
  1. Enable the Google Sheets API on a GCP project (the same project used
     for Google Ads API credentials works fine).
  2. Create a service account, download its JSON key.
  3. Share the target spreadsheet with the service account's email
     (`...@<project>.iam.gserviceaccount.com`) as Editor.

Required env vars (see `.env.example`):
  - `GOOGLE_SHEETS_CREDENTIALS_FILE` (path to the service account JSON key)
    OR `GOOGLE_SHEETS_CREDENTIALS_JSON` (the key's JSON content inline -
    for deployments where a file path isn't convenient, e.g. Railway
    secrets). If both are set, the file path wins.
  - `GOOGLE_SHEETS_WORKSHEET_NAME` (optional, defaults to "Fixes" - the tab
    name within the spreadsheet)

**Account -> sheet mapping (2026-08-27 fix):** one ad account maps to
exactly one spreadsheet - never one sheet shared across accounts, per the
user's explicit rule ("1 sheet = 1 ad account, not MCC"). This matters
immediately, not just for future clients: one MCC can (and for the user,
already does) contain multiple ad accounts reachable from the same running
instance, and nothing should let a fix for account B silently land in
account A's sheet.

Resolution order, per `FixesLogSheet.for_customer(customer_id)` (used by
`FixesLogService` - see that module):
  1. Look up `customer_id` (hyphens stripped) in the account-map file -
     `snapshots/account_sheets.json` by default, overridable via
     `GOOGLE_SHEETS_ACCOUNT_MAP_FILE` - a flat JSON object,
     `{"5690318342": "<spreadsheet_id>", "3280605786": "<spreadsheet_id>"}`.
     See `account_sheets.example.json` at the repo root for the format.
  2. If not found there, fall back to the single-account
     `GOOGLE_SHEETS_SPREADSHEET_ID` env var (keeps the simplest one-account
     setup zero-config beyond `.env`).
  3. If neither resolves it, raise loudly - never guess/default to some
     other account's sheet.

**Sheet layout** - headers and the spreadsheet title are always English
(a reusable template, regardless of which language an account's fixes get
written in); the actual fix content (what/fix_text/expectation/etc.) is
whatever language the caller writes, since that depends on the account
being managed:
    What | Fix | Status | Date | Expected Outcome | 1-Week Review |
    2-Week Review | 1-Month Review | Conclusion | ID
The trailing "ID" column is machine-only (holds the fix id used to find a
row again for a later review update) - appended after "Conclusion"
specifically so it doesn't disturb the reading order a human would expect.

**First-use formatting (2026-08-27):** the first time a fresh/empty
spreadsheet is used for a given account (detected the same way as
always - the "Fixes" tab doesn't exist yet), this code also: bolds +
freezes the header row, and renames the *spreadsheet's* title (not just
the tab) to `"{account_name} - {customer_id} - Fixes Log"` (or just
`"{customer_id} - Fixes Log"` if no account name was given) via
`FixesLogSheet.for_customer(customer_id, account_name=...)`. This only
happens once, on creation - an already-initialized sheet is never
reformatted or renamed again on subsequent calls.

Deliberately no scheduling/cron here - review columns ("1-Week Review" etc.)
are only ever written when a session is explicitly asked to check on a fix,
not on a timer (user's explicit instruction, 2026-08-27).
"""

from typing import Any, Dict, List, Optional

from src.utils import get_logger

logger = get_logger(__name__)

HEADER: List[str] = [
    "What",
    "Fix",
    "Status",
    "Date",
    "Expected Outcome",
    "1-Week Review",
    "2-Week Review",
    "1-Month Review",
    "Conclusion",
    "ID",
]


def _column_letter(n: int) -> str:
    """1-indexed column number -> A1-notation letter(s), e.g. 1 -> "A",
    10 -> "J", 27 -> "AA"."""
    letters = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


DEFAULT_WORKSHEET_NAME = "Fixes"
DEFAULT_ACCOUNT_MAP_PATH = "snapshots/account_sheets.json"

_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


class FixesLogSheetError(Exception):
    """Configuration or connection problem with the fixes-log Google Sheet."""


def load_account_sheet_map(path: Optional[str] = None) -> Dict[str, str]:
    """Read the `customer_id -> spreadsheet_id` mapping file.

    A missing file is not an error - it just means nothing is mapped yet,
    so callers fall back to the single-account `GOOGLE_SHEETS_SPREADSHEET_ID`
    env var. A present-but-malformed file (not a flat JSON object of
    string -> string) *is* an error - better to fail loudly than silently
    ignore a typo'd config.
    """
    import json
    import os
    from pathlib import Path

    resolved_path = Path(
        path
        or os.environ.get("GOOGLE_SHEETS_ACCOUNT_MAP_FILE")
        or DEFAULT_ACCOUNT_MAP_PATH
    )
    if not resolved_path.exists():
        return {}

    with resolved_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise FixesLogSheetError(
            f"{resolved_path} must contain a flat JSON object mapping "
            'customer_id -> spreadsheet_id, e.g. {"5690318342": "1AbC..."}'
        )

    return {k.replace("-", ""): v for k, v in data.items()}


class FixesLogSheet:
    """Thin wrapper around one worksheet tab used as the fixes log.

    All gspread/auth setup is lazy (only happens on first real use) and
    injectable - pass `worksheet` directly (any object exposing
    `append_row`, `get_all_records`, `col_values`, `update_cell`, matching
    gspread's `Worksheet` API) to bypass Google auth entirely, e.g. in
    tests.
    """

    def __init__(
        self,
        spreadsheet_id: Optional[str] = None,
        worksheet_name: Optional[str] = None,
        worksheet: Optional[Any] = None,
        customer_id: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> None:
        import os

        self._spreadsheet_id = spreadsheet_id or os.environ.get(
            "GOOGLE_SHEETS_SPREADSHEET_ID"
        )
        self._worksheet_name = (
            worksheet_name
            or os.environ.get("GOOGLE_SHEETS_WORKSHEET_NAME")
            or DEFAULT_WORKSHEET_NAME
        )
        self._worksheet = worksheet
        # Only used for the one-time title-rename on first init - see
        # _get_worksheet(). Not needed for any already-initialized sheet.
        self._customer_id = customer_id
        self._account_name = account_name

    @classmethod
    def for_customer(
        cls,
        customer_id: str,
        account_name: Optional[str] = None,
        worksheet_name: Optional[str] = None,
    ) -> "FixesLogSheet":
        """Resolve which spreadsheet a given ad account's fixes belong in.

        See the module docstring's "Account -> sheet mapping" section for
        the resolution order. Raises `FixesLogSheetError` rather than
        guessing if nothing is configured for this account - a fix
        silently landing in the wrong account's sheet is worse than a
        loud, immediately-fixable error.

        `account_name`, if given, is only used if this turns out to be a
        fresh/empty spreadsheet (see _get_worksheet) - to compose its
        one-time title. Harmless to omit or to pass on every call.
        """
        import os

        normalized = customer_id.replace("-", "")
        account_map = load_account_sheet_map()
        spreadsheet_id = account_map.get(normalized) or os.environ.get(
            "GOOGLE_SHEETS_SPREADSHEET_ID"
        )
        if not spreadsheet_id:
            raise FixesLogSheetError(
                f"No Google Sheet configured for ad account {customer_id}. "
                f"Add it to {DEFAULT_ACCOUNT_MAP_PATH} (customer_id -> "
                "spreadsheet_id - see account_sheets.example.json) or set "
                "GOOGLE_SHEETS_SPREADSHEET_ID if this deployment only ever "
                "handles one account."
            )
        return cls(
            spreadsheet_id=spreadsheet_id,
            worksheet_name=worksheet_name,
            customer_id=normalized,
            account_name=account_name,
        )

    def _build_credentials(self) -> Any:
        import json
        import os

        from google.oauth2.service_account import Credentials

        creds_file = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE")
        creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
        if creds_file:
            return Credentials.from_service_account_file(
                creds_file, scopes=_SHEETS_SCOPES
            )
        if creds_json:
            return Credentials.from_service_account_info(
                json.loads(creds_json), scopes=_SHEETS_SCOPES
            )
        raise FixesLogSheetError(
            "Set GOOGLE_SHEETS_CREDENTIALS_FILE (path to a service account "
            "JSON key) or GOOGLE_SHEETS_CREDENTIALS_JSON (the key's JSON "
            "content inline) to authenticate the fixes-log Google Sheet "
            "integration."
        )

    def _get_worksheet(self) -> Any:
        if self._worksheet is not None:
            return self._worksheet

        import gspread

        if not self._spreadsheet_id:
            raise FixesLogSheetError(
                "GOOGLE_SHEETS_SPREADSHEET_ID is not set - it's the id "
                "segment of the sheet's URL: "
                "https://docs.google.com/spreadsheets/d/<THIS_PART>/edit"
            )

        credentials = self._build_credentials()
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(self._spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(self._worksheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title=self._worksheet_name, rows=1000, cols=len(HEADER)
            )
            worksheet.append_row(HEADER)
            self._format_new_worksheet(worksheet)
            self._rename_spreadsheet_title(spreadsheet)

        self._worksheet = worksheet
        return worksheet

    def _format_new_worksheet(self, worksheet: Any) -> None:
        """One-time cosmetics for a freshly-created tab: bold + freeze the
        header row. Best-effort - a formatting failure shouldn't block the
        actual data write that triggered this."""
        try:
            last_col = _column_letter(len(HEADER))
            worksheet.format(f"A1:{last_col}1", {"textFormat": {"bold": True}})
            worksheet.freeze(rows=1)
        except Exception as e:
            logger.warning(f"Could not format the new fixes-log worksheet: {e}")

    def _rename_spreadsheet_title(self, spreadsheet: Any) -> None:
        """One-time rename of the whole spreadsheet (not just the tab) to
        "{account_name} - {customer_id} - Fixes Log", so an agency managing
        several client sheets can tell them apart at a glance in Drive.
        Best-effort - a rename failure shouldn't block the actual data
        write that triggered this, and requires no `account_name`/
        `customer_id` at all (falls back to whatever's available, or skips
        entirely if neither is known)."""
        parts = [p for p in (self._account_name, self._customer_id, "Fixes Log") if p]
        if len(parts) <= 1:
            return
        try:
            spreadsheet.update_title(" - ".join(parts))
        except Exception as e:
            logger.warning(f"Could not rename the fixes-log spreadsheet: {e}")

    def append_fix(
        self,
        fix_id: str,
        what: str,
        fix_text: str,
        status: str,
        when: str,
        expectation: str,
    ) -> None:
        """Append a new row. The three review columns and Conclusion start
        blank - they're only ever filled in later, on an explicit review."""
        worksheet = self._get_worksheet()
        worksheet.append_row(
            [what, fix_text, status, when, expectation, "", "", "", "", fix_id]
        )

    def find_row(self, fix_id: str) -> Optional[int]:
        """1-indexed sheet row number for a given fix id, or None."""
        worksheet = self._get_worksheet()
        id_col_index = HEADER.index("ID") + 1
        for row_number, value in enumerate(worksheet.col_values(id_col_index), start=1):
            if value == fix_id:
                return row_number
        return None

    def update_cell(self, fix_id: str, column_name: str, value: str) -> None:
        if column_name not in HEADER:
            raise FixesLogSheetError(
                f"Unknown column '{column_name}', expected one of {HEADER}"
            )
        row = self.find_row(fix_id)
        if row is None:
            raise FixesLogSheetError(f"No row found with ID {fix_id}")
        worksheet = self._get_worksheet()
        worksheet.update_cell(row, HEADER.index(column_name) + 1, value)

    def list_rows(self) -> List[Dict[str, Any]]:
        worksheet = self._get_worksheet()
        return list(worksheet.get_all_records())
