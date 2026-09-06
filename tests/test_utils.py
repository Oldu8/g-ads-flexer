"""Tests for src/utils.py, focused on format_customer_id's alias support."""

from pathlib import Path

import pytest

from src.services.review import account_registry_store
from src.services.review.account_registry_store import AccountRegistryStore
from src.utils import format_customer_id


@pytest.fixture(autouse=True)
def isolated_account_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the account registry's default store path at an empty tmp
    file for every test in this module, so these tests never read or
    write the real `snapshots/account_registry.json`.
    """
    store_path = tmp_path / "account_registry.json"
    monkeypatch.setattr(account_registry_store, "DEFAULT_STORE_PATH", store_path)
    return store_path


def test_format_customer_id_strips_hyphens() -> None:
    """Raw numeric IDs are unaffected - hyphens stripped, nothing else."""
    assert format_customer_id("123-456-7890") == "1234567890"
    assert format_customer_id("1234567890") == "1234567890"


def test_format_customer_id_unregistered_alias_passes_through() -> None:
    """A string that isn't a registered alias is treated as a raw id -
    hyphens (if any) stripped the same as any other unrecognized input.
    """
    assert format_customer_id("not-a-registered-alias") == "notaregisteredalias"


def test_format_customer_id_resolves_registered_alias(
    isolated_account_registry: Path,
) -> None:
    """A registered alias resolves to its numeric customer_id."""
    AccountRegistryStore().add(alias="boo-ua", customer_id="5690318342", name="boo.ua")

    assert format_customer_id("boo-ua") == "5690318342"


def test_format_customer_id_no_registry_file_falls_back() -> None:
    """A missing registry file is not an error - falls back to treating
    the input as a raw customer_id, same as an unregistered alias.
    """
    assert format_customer_id("boo-ua") == "booua"
