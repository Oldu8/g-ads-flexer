"""Local, file-backed registry of Google Ads account aliases.

Not a Google Ads API concept - lets every tool's `customer_id` parameter
accept a short human alias (e.g. "boo-ua") instead of the raw numeric
customer ID, resolved transparently by `format_customer_id` (see
`src/utils.py`, the one choke point every service already calls before
touching `customer_id` - this is why adding alias support here required
touching that one function instead of every service file).

An alias only ever resolves to a customer_id string - it carries no
credentials and does not change which Google Ads API account this
deployment authenticates *as* (that's still `sdk_client.py`'s single,
process-wide singleton, set once at startup from `.env`). An alias only
works for an account already reachable under this deployment's configured
manager account (`GOOGLE_ADS_LOGIN_CUSTOMER_ID`) - a genuinely separate
Google Ads API credential set (its own developer token/OAuth client)
still needs its own `.env`/process; see `docs/CLIENT_ONBOARDING.md` and
`docs/ACCOUNT_SWITCHING.md`.

Storage is a single JSON file under `snapshots/` (already gitignored -
same sensitivity class as `pending_changes.json`/`account_sheets.json`:
which accounts you manage, under what names, is business information).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_STORE_PATH = Path("snapshots") / "account_registry.json"


class AccountRegistryStore:
    """JSON-file-backed `alias -> {customer_id, name}` registry.

    Not safe for concurrent writers (single local process is the expected
    use case, matching how the rest of this server runs) - writes are a
    plain read-modify-write of the whole file, not row-level locked. Same
    trade-off `PendingChangeStore` makes, for the same reason.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path: Path = path or DEFAULT_STORE_PATH

    def _load_all(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_all(self, records: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False, sort_keys=True)
        tmp_path.replace(self.path)

    def list_all(self) -> List[Dict[str, Any]]:
        """Return every registered account, sorted by alias."""
        records = self._load_all()
        return [{"alias": alias, **entry} for alias, entry in sorted(records.items())]

    def resolve(self, alias: str) -> Optional[str]:
        """Return the numeric customer_id for `alias`.

        Returns None if `alias` isn't a registered alias at all (including
        when the registry file doesn't exist yet) - the caller should then
        treat the input as a raw customer_id, never raise.
        """
        entry = self._load_all().get(alias)
        if isinstance(entry, dict) and "customer_id" in entry:
            return str(entry["customer_id"])
        return None

    def add(
        self, alias: str, customer_id: str, name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Register (or overwrite) an alias. Returns the stored entry."""
        records = self._load_all()
        entry: Dict[str, Any] = {"customer_id": customer_id.replace("-", "")}
        if name:
            entry["name"] = name
        records[alias] = entry
        self._save_all(records)
        return {"alias": alias, **entry}

    def remove(self, alias: str) -> bool:
        """Remove an alias. Returns whether it existed."""
        records = self._load_all()
        if alias not in records:
            return False
        del records[alias]
        self._save_all(records)
        return True
