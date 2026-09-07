"""Tests for PendingChangeStore."""

from pathlib import Path

import pytest

from src.services.review.pending_change_store import PendingChangeStore


@pytest.fixture
def store(tmp_path: Path) -> PendingChangeStore:
    """A store backed by a fresh file under pytest's tmp_path."""
    return PendingChangeStore(path=tmp_path / "pending_changes.json")


def test_create_returns_pending_record(store: PendingChangeStore) -> None:
    record = store.create(
        kind="add_keywords", params={"ad_group_id": "111"}, preview="preview text"
    )

    assert record["id"].startswith("pc_")
    assert record["kind"] == "add_keywords"
    assert record["status"] == "pending"
    assert record["preview"] == "preview text"
    assert record["params"] == {"ad_group_id": "111"}
    assert record["applied_at"] is None
    assert record["rejected_at"] is None


def test_create_persists_to_disk(store: PendingChangeStore) -> None:
    record = store.create(kind="add_keywords", params={}, preview="p")

    assert store.path.exists()
    reloaded = PendingChangeStore(path=store.path)
    assert reloaded.get(record["id"]) == record


def test_get_missing_returns_none(store: PendingChangeStore) -> None:
    assert store.get("pc_doesnotexist") is None


def test_list_filters_by_status(store: PendingChangeStore) -> None:
    pending = store.create(kind="add_keywords", params={}, preview="p1")
    to_apply = store.create(kind="add_keywords", params={}, preview="p2")
    store.mark_applied(to_apply["id"], result={"ok": True})

    all_records = store.list(status=None)
    pending_only = store.list(status="pending")
    applied_only = store.list(status="applied")

    assert {r["id"] for r in all_records} == {pending["id"], to_apply["id"]}
    assert [r["id"] for r in pending_only] == [pending["id"]]
    assert [r["id"] for r in applied_only] == [to_apply["id"]]


def test_mark_applied_updates_status_and_result(store: PendingChangeStore) -> None:
    record = store.create(kind="add_keywords", params={}, preview="p")

    updated = store.mark_applied(record["id"], result={"results": [1, 2]})

    assert updated["status"] == "applied"
    assert updated["applied_at"] is not None
    assert updated["result"] == {"results": [1, 2]}


def test_mark_rejected_updates_status_and_reason(store: PendingChangeStore) -> None:
    record = store.create(kind="add_keywords", params={}, preview="p")

    updated = store.mark_rejected(record["id"], reason="looked like a competitor term")

    assert updated["status"] == "rejected"
    assert updated["rejected_at"] is not None
    assert updated["rejected_reason"] == "looked like a competitor term"


def test_mark_applied_missing_id_raises(store: PendingChangeStore) -> None:
    with pytest.raises(KeyError):
        store.mark_applied("pc_doesnotexist", result={})


def test_mark_rejected_missing_id_raises(store: PendingChangeStore) -> None:
    with pytest.raises(KeyError):
        store.mark_rejected("pc_doesnotexist", reason=None)


def test_corrupt_store_file_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.json"
    path.write_text("not valid json {{{", encoding="utf-8")
    store = PendingChangeStore(path=path)

    assert store.list(status=None) == []
