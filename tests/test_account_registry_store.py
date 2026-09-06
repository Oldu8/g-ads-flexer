"""Tests for AccountRegistryStore."""

from pathlib import Path

from src.services.review.account_registry_store import AccountRegistryStore


def test_list_all_empty_when_no_file(tmp_path: Path) -> None:
    """A missing registry file behaves like an empty registry."""
    store = AccountRegistryStore(path=tmp_path / "account_registry.json")
    assert store.list_all() == []


def test_add_and_list(tmp_path: Path) -> None:
    """Adding an account makes it show up in list_all, sorted by alias."""
    store = AccountRegistryStore(path=tmp_path / "account_registry.json")

    store.add(alias="new-project", customer_id="0987654321", name="New Project")
    store.add(alias="boo-ua", customer_id="5690318342", name="boo.ua")

    accounts = store.list_all()
    assert accounts == [
        {"alias": "boo-ua", "customer_id": "5690318342", "name": "boo.ua"},
        {
            "alias": "new-project",
            "customer_id": "0987654321",
            "name": "New Project",
        },
    ]


def test_add_strips_hyphens_from_customer_id(tmp_path: Path) -> None:
    """A customer_id with hyphens is normalized before storing."""
    store = AccountRegistryStore(path=tmp_path / "account_registry.json")
    entry = store.add(alias="boo-ua", customer_id="569-031-8342")
    assert entry["customer_id"] == "5690318342"


def test_add_without_name(tmp_path: Path) -> None:
    """name is optional - omitted from the stored entry when not given."""
    store = AccountRegistryStore(path=tmp_path / "account_registry.json")
    entry = store.add(alias="boo-ua", customer_id="5690318342")
    assert entry == {"alias": "boo-ua", "customer_id": "5690318342"}


def test_resolve_registered_alias(tmp_path: Path) -> None:
    """resolve() returns the customer_id for a registered alias."""
    store = AccountRegistryStore(path=tmp_path / "account_registry.json")
    store.add(alias="boo-ua", customer_id="5690318342")
    assert store.resolve("boo-ua") == "5690318342"


def test_resolve_unregistered_alias_returns_none(tmp_path: Path) -> None:
    """resolve() returns None (not an error) for an unregistered alias."""
    store = AccountRegistryStore(path=tmp_path / "account_registry.json")
    assert store.resolve("nope") is None


def test_remove_existing(tmp_path: Path) -> None:
    """remove() deletes the alias and reports it existed."""
    store = AccountRegistryStore(path=tmp_path / "account_registry.json")
    store.add(alias="boo-ua", customer_id="5690318342")

    assert store.remove("boo-ua") is True
    assert store.list_all() == []


def test_remove_nonexistent(tmp_path: Path) -> None:
    """remove() reports False rather than raising for an unknown alias."""
    store = AccountRegistryStore(path=tmp_path / "account_registry.json")
    assert store.remove("nope") is False


def test_persists_across_instances(tmp_path: Path) -> None:
    """Data written by one store instance is visible to a fresh instance
    pointed at the same file (real file-backed persistence, not just an
    in-memory cache)."""
    path = tmp_path / "account_registry.json"
    AccountRegistryStore(path=path).add(alias="boo-ua", customer_id="5690318342")

    fresh = AccountRegistryStore(path=path)
    assert fresh.resolve("boo-ua") == "5690318342"
