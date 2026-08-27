"""Tests for FixesLogSheet."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.services.review.fixes_log_sheet import (
    HEADER,
    FixesLogSheet,
    FixesLogSheetError,
    load_account_sheet_map,
)
from src.services.review.fixes_log_sheet import (
    _column_letter,  # type: ignore[reportPrivateUsage]
)


@pytest.fixture
def mock_worksheet() -> Mock:
    return Mock()


@pytest.fixture
def sheet(mock_worksheet: Mock) -> FixesLogSheet:
    """A FixesLogSheet with the worksheet injected directly - bypasses
    Google auth entirely."""
    return FixesLogSheet(worksheet=mock_worksheet)


def test_append_fix_appends_row_in_header_order(
    sheet: FixesLogSheet, mock_worksheet: Mock
) -> None:
    sheet.append_fix(
        fix_id="F-1",
        what="Added keywords",
        fix_text="Added 9 EXACT keywords to ad group X",
        status="Collecting data",
        when="2026-08-27",
        expectation="IS should recover on brand terms",
    )

    mock_worksheet.append_row.assert_called_once_with(
        [
            "Added keywords",
            "Added 9 EXACT keywords to ad group X",
            "Collecting data",
            "2026-08-27",
            "IS should recover on brand terms",
            "",
            "",
            "",
            "",
            "F-1",
        ]
    )


def test_find_row_returns_matching_row_number(
    sheet: FixesLogSheet, mock_worksheet: Mock
) -> None:
    id_col_index = HEADER.index("ID") + 1
    mock_worksheet.col_values.return_value = ["ID", "F-1", "F-2", "F-3"]

    assert sheet.find_row("F-2") == 3
    mock_worksheet.col_values.assert_called_once_with(id_col_index)


def test_find_row_returns_none_when_missing(
    sheet: FixesLogSheet, mock_worksheet: Mock
) -> None:
    mock_worksheet.col_values.return_value = ["ID", "F-1"]

    assert sheet.find_row("F-999") is None


def test_update_cell_writes_correct_row_and_column(
    sheet: FixesLogSheet, mock_worksheet: Mock
) -> None:
    mock_worksheet.col_values.return_value = ["ID", "F-1", "F-2"]

    sheet.update_cell("F-2", "1-Week Review", "IS recovered to 90%")

    col = HEADER.index("1-Week Review") + 1
    mock_worksheet.update_cell.assert_called_once_with(3, col, "IS recovered to 90%")


def test_update_cell_unknown_column_raises(
    sheet: FixesLogSheet, mock_worksheet: Mock
) -> None:
    with pytest.raises(FixesLogSheetError, match="Unknown column"):
        sheet.update_cell("F-1", "Not A Real Column", "value")
    mock_worksheet.update_cell.assert_not_called()


def test_update_cell_missing_fix_id_raises(
    sheet: FixesLogSheet, mock_worksheet: Mock
) -> None:
    mock_worksheet.col_values.return_value = ["ID"]

    with pytest.raises(FixesLogSheetError, match="No row found"):
        sheet.update_cell("F-999", "Conclusion", "value")
    mock_worksheet.update_cell.assert_not_called()


def test_list_rows_returns_get_all_records(
    sheet: FixesLogSheet, mock_worksheet: Mock
) -> None:
    mock_worksheet.get_all_records.return_value = [{"What": "a"}, {"What": "b"}]

    assert sheet.list_rows() == [{"What": "a"}, {"What": "b"}]


def test_missing_spreadsheet_id_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)
    sheet = FixesLogSheet()  # no injected worksheet, no env var

    with pytest.raises(FixesLogSheetError, match="GOOGLE_SHEETS_SPREADSHEET_ID"):
        sheet.list_rows()


def test_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "abc123")
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_JSON", raising=False)
    sheet = FixesLogSheet()

    with pytest.raises(FixesLogSheetError, match="GOOGLE_SHEETS_CREDENTIALS"):
        sheet.list_rows()


# ---------------------------------------------------------------------------
# load_account_sheet_map
# ---------------------------------------------------------------------------


def test_load_account_sheet_map_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_account_sheet_map(str(tmp_path / "does_not_exist.json")) == {}


def test_load_account_sheet_map_strips_hyphens_from_keys(tmp_path: Path) -> None:
    path = tmp_path / "account_sheets.json"
    path.write_text(
        json.dumps({"123-456-7890": "sheet-a", "0987654321": "sheet-b"}),
        encoding="utf-8",
    )

    result = load_account_sheet_map(str(path))

    assert result == {"1234567890": "sheet-a", "0987654321": "sheet-b"}


def test_load_account_sheet_map_rejects_non_flat_object(tmp_path: Path) -> None:
    path = tmp_path / "account_sheets.json"
    path.write_text(json.dumps({"123": {"nested": "object"}}), encoding="utf-8")

    with pytest.raises(FixesLogSheetError, match="flat JSON object"):
        load_account_sheet_map(str(path))


def test_load_account_sheet_map_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "account_sheets.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(FixesLogSheetError, match="flat JSON object"):
        load_account_sheet_map(str(path))


# ---------------------------------------------------------------------------
# FixesLogSheet.for_customer
# ---------------------------------------------------------------------------


def test_for_customer_resolves_from_account_map_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "account_sheets.json"
    path.write_text(json.dumps({"1234567890": "sheet-from-map"}), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_SHEETS_ACCOUNT_MAP_FILE", str(path))
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)

    sheet = FixesLogSheet.for_customer("123-456-7890")

    assert sheet._spreadsheet_id == "sheet-from-map"  # type: ignore[attr-defined]


def test_for_customer_falls_back_to_single_account_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "GOOGLE_SHEETS_ACCOUNT_MAP_FILE", str(tmp_path / "does_not_exist.json")
    )
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "fallback-sheet")

    sheet = FixesLogSheet.for_customer("1234567890")

    assert sheet._spreadsheet_id == "fallback-sheet"  # type: ignore[attr-defined]


def test_for_customer_map_entry_wins_over_env_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "account_sheets.json"
    path.write_text(json.dumps({"1234567890": "sheet-from-map"}), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_SHEETS_ACCOUNT_MAP_FILE", str(path))
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "should-not-be-used")

    sheet = FixesLogSheet.for_customer("1234567890")

    assert sheet._spreadsheet_id == "sheet-from-map"  # type: ignore[attr-defined]


def test_for_customer_raises_when_nothing_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "GOOGLE_SHEETS_ACCOUNT_MAP_FILE", str(tmp_path / "does_not_exist.json")
    )
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)

    with pytest.raises(FixesLogSheetError, match="No Google Sheet configured"):
        FixesLogSheet.for_customer("1234567890")


def test_for_customer_different_accounts_get_different_sheets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "account_sheets.json"
    path.write_text(
        json.dumps({"1111111111": "sheet-a", "2222222222": "sheet-b"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_SHEETS_ACCOUNT_MAP_FILE", str(path))
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)

    sheet_a = FixesLogSheet.for_customer("1111111111")
    sheet_b = FixesLogSheet.for_customer("2222222222")

    assert sheet_a._spreadsheet_id == "sheet-a"  # type: ignore[attr-defined]
    assert sheet_b._spreadsheet_id == "sheet-b"  # type: ignore[attr-defined]


def test_for_customer_stores_customer_id_and_account_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "GOOGLE_SHEETS_ACCOUNT_MAP_FILE", str(tmp_path / "does_not_exist.json")
    )
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "fallback-sheet")

    sheet = FixesLogSheet.for_customer("123-456-7890", account_name="boo.ua")

    assert sheet._customer_id == "1234567890"  # type: ignore[attr-defined]
    assert sheet._account_name == "boo.ua"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _column_letter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "n,expected", [(1, "A"), (2, "B"), (10, "J"), (26, "Z"), (27, "AA"), (52, "AZ")]
)
def test_column_letter(n: int, expected: str) -> None:
    assert _column_letter(n) == expected


# ---------------------------------------------------------------------------
# First-use formatting / spreadsheet rename
# ---------------------------------------------------------------------------


def test_format_new_worksheet_bolds_and_freezes_header(mock_worksheet: Mock) -> None:
    sheet = FixesLogSheet(worksheet=mock_worksheet)

    sheet._format_new_worksheet(mock_worksheet)  # type: ignore[reportPrivateUsage]

    last_col = _column_letter(len(HEADER))
    mock_worksheet.format.assert_called_once_with(
        f"A1:{last_col}1", {"textFormat": {"bold": True}}
    )
    mock_worksheet.freeze.assert_called_once_with(rows=1)


def test_format_new_worksheet_swallows_formatting_errors(mock_worksheet: Mock) -> None:
    mock_worksheet.format.side_effect = Exception("boom")
    sheet = FixesLogSheet(worksheet=mock_worksheet)

    sheet._format_new_worksheet(mock_worksheet)  # type: ignore[reportPrivateUsage]  # must not raise


def test_rename_spreadsheet_title_with_account_name_and_customer_id() -> None:
    sheet = FixesLogSheet(
        worksheet=Mock(), customer_id="1234567890", account_name="boo.ua"
    )
    mock_spreadsheet = Mock()

    sheet._rename_spreadsheet_title(mock_spreadsheet)  # type: ignore[reportPrivateUsage]

    mock_spreadsheet.update_title.assert_called_once_with(
        "boo.ua - 1234567890 - Fixes Log"
    )


def test_rename_spreadsheet_title_without_account_name() -> None:
    sheet = FixesLogSheet(worksheet=Mock(), customer_id="1234567890")
    mock_spreadsheet = Mock()

    sheet._rename_spreadsheet_title(mock_spreadsheet)  # type: ignore[reportPrivateUsage]

    mock_spreadsheet.update_title.assert_called_once_with("1234567890 - Fixes Log")


def test_rename_spreadsheet_title_skips_when_nothing_known() -> None:
    sheet = FixesLogSheet(worksheet=Mock())  # no customer_id, no account_name

    mock_spreadsheet = Mock()
    sheet._rename_spreadsheet_title(mock_spreadsheet)  # type: ignore[reportPrivateUsage]

    mock_spreadsheet.update_title.assert_not_called()


def test_rename_spreadsheet_title_swallows_errors() -> None:
    sheet = FixesLogSheet(worksheet=Mock(), customer_id="1234567890")
    mock_spreadsheet = Mock()
    mock_spreadsheet.update_title.side_effect = Exception("boom")

    sheet._rename_spreadsheet_title(mock_spreadsheet)  # type: ignore[reportPrivateUsage]  # must not raise
