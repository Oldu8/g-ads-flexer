"""Local, file-backed store for pending write operations.

This is not a Google Ads API concept - it is our own guardrail layer. See
the 2026-08-26 TRACKER.md entry ("End goal restated...") for the rationale:
the user was explicit that they don't want write tools to execute
immediately on a single call - they want to see exactly what would change
(e.g. the actual keyword list, so they can catch a competitor brand name
before it goes live) and approve it before anything touches the real
account.

A `propose_*` tool (see `pending_change_service.py`) validates input shape
and writes a record here with status "pending" - it never calls the Google
Ads API. `apply_pending_change` is the only path that ever does, and only
for a record that is still "pending". This is a structural guarantee (any
MCP client - Claude Code today, a future web dashboard later - gets the same
safety for free) rather than something that depends on the calling agent
choosing to ask first.

Storage is a single JSON file under `snapshots/` - that directory is already
gitignored ("Local account snapshots (real business data - keep out of git
by default)" in .gitignore) and this file is the same sensitivity class, so
it reuses that convention rather than adding a new ignore rule. It also
doubles as a human-readable audit trail of everything ever proposed, applied,
or rejected through this path - a gap flagged in the same TRACKER.md entry.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_STORE_PATH = Path("snapshots") / "pending_changes.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PendingChangeStore:
    """JSON-file-backed store of pending change records, keyed by change id.

    Not safe for concurrent writers (single local process is the expected
    use case, matching how the rest of this server runs) - writes are a
    plain read-modify-write of the whole file, not row-level locked.
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

    def create(self, kind: str, params: Dict[str, Any], preview: str) -> Dict[str, Any]:
        """Create and persist a new pending change. Returns the stored record."""
        records = self._load_all()
        change_id = f"pc_{uuid.uuid4().hex[:12]}"
        record: Dict[str, Any] = {
            "id": change_id,
            "kind": kind,
            "status": "pending",
            "params": params,
            "preview": preview,
            "created_at": _now_iso(),
            "applied_at": None,
            "rejected_at": None,
            "rejected_reason": None,
            "result": None,
        }
        records[change_id] = record
        self._save_all(records)
        return record

    def get(self, change_id: str) -> Optional[Dict[str, Any]]:
        return self._load_all().get(change_id)

    def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        records = list(self._load_all().values())
        if status is not None:
            records = [r for r in records if r.get("status") == status]
        records.sort(key=lambda r: r["created_at"])
        return records

    def mark_applied(self, change_id: str, result: Any) -> Dict[str, Any]:
        records = self._load_all()
        record = records.get(change_id)
        if record is None:
            raise KeyError(f"No pending change with id {change_id}")
        record["status"] = "applied"
        record["applied_at"] = _now_iso()
        record["result"] = result
        self._save_all(records)
        return record

    def mark_rejected(self, change_id: str, reason: Optional[str]) -> Dict[str, Any]:
        records = self._load_all()
        record = records.get(change_id)
        if record is None:
            raise KeyError(f"No pending change with id {change_id}")
        record["status"] = "rejected"
        record["rejected_at"] = _now_iso()
        record["rejected_reason"] = reason
        self._save_all(records)
        return record
