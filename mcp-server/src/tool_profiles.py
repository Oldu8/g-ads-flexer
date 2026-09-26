"""Load and validate tool profiles (`tool_profiles.yaml`).

A profile is the set of tool names the agent can list and call. Profiles are
explicit lists validated against `src/tool_registry.py`; a typo stops the
process instead of silently exposing (or hiding) a tool. `read_only` is
computed from `manager` so it cannot drift: it keeps `manager`'s reads and
internal writes (fixes log), and drops the pending-change queue tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional

import yaml

from src.tool_registry import TOOL_REGISTRY, ToolMeta

PROFILES_PATH = Path(__file__).resolve().parent.parent / "tool_profiles.yaml"
DEFAULT_PROFILE = "manager"
READ_ONLY_PROFILE = "read_only"
QUEUE_TOOL_PREFIX = "pending_change_"
ALL_TOOLS = "*"


class ProfileError(ValueError):
    """A profile file or profile name is invalid."""


def _parse_profile(
    name: str, spec: Any, registry: Mapping[str, ToolMeta]
) -> FrozenSet[str]:
    if spec == ALL_TOOLS:
        return frozenset(registry)
    if spec is None:
        return frozenset()
    if not isinstance(spec, list) or not all(isinstance(t, str) for t in spec):
        raise ProfileError(
            f"profile {name!r} must be a list of tool names or {ALL_TOOLS!r}"
        )
    names: List[str] = list(spec)
    unknown = sorted({t for t in names if t not in registry})
    if unknown:
        raise ProfileError(
            f"profile {name!r} lists unknown tools: {', '.join(unknown)}"
        )
    duplicates = sorted({t for t in names if names.count(t) > 1})
    if duplicates:
        raise ProfileError(
            f"profile {name!r} lists tools more than once: {', '.join(duplicates)}"
        )
    return frozenset(names)


def compute_read_only(
    manager: FrozenSet[str], registry: Mapping[str, ToolMeta]
) -> FrozenSet[str]:
    """`manager`'s reads and internal writes, without the pending-change queue."""
    return frozenset(
        t
        for t in manager
        if registry[t].kind in ("read", "internal_write")
        and not t.startswith(QUEUE_TOOL_PREFIX)
    )


def load_profiles(
    path: Optional[Path] = None,
    registry: Mapping[str, ToolMeta] = TOOL_REGISTRY,
) -> Dict[str, FrozenSet[str]]:
    """Load, validate and complete every profile. Raises `ProfileError`."""
    source = path or PROFILES_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
        raise ProfileError(f"{source} must contain a 'profiles' mapping")
    raw: Dict[str, Any] = data["profiles"]
    if READ_ONLY_PROFILE in raw:
        raise ProfileError(
            f"{READ_ONLY_PROFILE!r} is computed from {DEFAULT_PROFILE!r}; "
            "do not list it"
        )
    profiles = {
        name: _parse_profile(name, spec, registry) for name, spec in raw.items()
    }
    if DEFAULT_PROFILE not in profiles:
        raise ProfileError(f"{source} must define the {DEFAULT_PROFILE!r} profile")
    profiles[READ_ONLY_PROFILE] = compute_read_only(profiles[DEFAULT_PROFILE], registry)
    return profiles


def get_profile(name: str, path: Optional[Path] = None) -> FrozenSet[str]:
    """Return the tool names of one profile, or raise `ProfileError`."""
    profiles = load_profiles(path)
    if name not in profiles:
        raise ProfileError(
            f"unknown profile {name!r}; available: {', '.join(sorted(profiles))}"
        )
    return profiles[name]
