"""Tests on the MCP surface itself: what a client can list and call.

Service tests mock the Google Ads client; these go through the real MCP
protocol (in-memory client, profile middleware) so a renamed tool, a lost
docstring, a registry gap or a grown schema fails here instead of shipping.
"""

import json
from pathlib import Path
from typing import Any, Dict, FrozenSet, List
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from src.error_hints import RECONNECT_MESSAGE
from src.server_factory import create_server
from src.services.campaign.campaign_service import CampaignService
from src.services.planning.recommendation_service import RecommendationService
from src.surface import SIZE_BUDGETS, largest_tools, payload_size, render_tools_list
from src.tool_profiles import ProfileError, load_profiles
from src.tool_registry import TOOL_REGISTRY

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture(scope="module")
def profiles() -> Dict[str, FrozenSet[str]]:
    return load_profiles()


async def _list(profile: str) -> List[Dict[str, Any]]:
    return await render_tools_list(profile)


# --- registry ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_matches_registered_tools() -> None:
    registered = {t["name"] for t in await _list("all")}
    missing = sorted(registered - set(TOOL_REGISTRY))
    stale = sorted(set(TOOL_REGISTRY) - registered)
    assert not missing, f"tools without a src/tool_registry.py entry: {missing}"
    assert not stale, f"registry entries for tools that no longer exist: {stale}"


def test_registry_fixes_misleading_names() -> None:
    assert TOOL_REGISTRY["search_execute_query"].kind == "read"
    for name in (
        "user_list_create_rule_based_user_list",
        "user_list_update_user_list",
        "user_list_remove_user_list",
        "ad_create_responsive_search_ad",
    ):
        assert TOOL_REGISTRY[name].kind == "ads_write", name


@pytest.mark.asyncio
async def test_names_unique_and_described() -> None:
    tools = await _list("all")
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names))
    undescribed = [t["name"] for t in tools if not t.get("description", "").strip()]
    assert not undescribed, f"tools without a description: {undescribed}"


# --- profiles ---------------------------------------------------------------


def test_manager_profile(profiles: Dict[str, FrozenSet[str]]) -> None:
    manager = profiles["manager"]
    assert len(manager) == 77
    assert sum(1 for t in manager if TOOL_REGISTRY[t].kind == "ads_write") == 44
    assert "ad_create_expanded_text_ad" not in manager
    assert "google_ads_search_google_ads" not in manager


def test_read_only_is_derived(profiles: Dict[str, FrozenSet[str]]) -> None:
    read_only = profiles["read_only"]
    assert read_only <= profiles["manager"]
    assert "fixes_log_log_fix" in read_only
    assert "search_execute_query" in read_only
    assert not [t for t in read_only if TOOL_REGISTRY[t].kind == "ads_write"]
    assert not [t for t in read_only if t.startswith("pending_change_")]


def _write_profiles(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "tool_profiles.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_profile_typo_fails(tmp_path: Path) -> None:
    path = _write_profiles(
        tmp_path, "profiles:\n  manager:\n    - campaign_update_campaing\n"
    )
    with pytest.raises(ProfileError, match="campaign_update_campaing") as exc:
        load_profiles(path)
    assert "'manager'" in str(exc.value)


def test_empty_profile_exposes_nothing(tmp_path: Path) -> None:
    path = _write_profiles(
        tmp_path, "profiles:\n  manager:\n    - search_execute_query\n  empty:\n"
    )
    assert load_profiles(path)["empty"] == frozenset()


def test_read_only_cannot_be_listed_by_hand(tmp_path: Path) -> None:
    path = _write_profiles(
        tmp_path,
        "profiles:\n  manager:\n    - search_execute_query\n"
        "  read_only:\n    - search_execute_query\n",
    )
    with pytest.raises(ProfileError, match="computed"):
        load_profiles(path)


# --- listing and calling through MCP ------------------------------------------


@pytest.mark.asyncio
async def test_listing_matches_profile(profiles: Dict[str, FrozenSet[str]]) -> None:
    for name in ("manager", "read_only"):
        listed = {t["name"] for t in await _list(name)}
        assert listed == profiles[name], name


@pytest.mark.asyncio
async def test_hidden_tool_cannot_be_called() -> None:
    mcp = create_server("read_only", name="t", instructions="t")
    with patch.object(
        CampaignService, "update_campaign", AsyncMock()
    ) as update_campaign:
        async with Client(mcp) as client:
            with pytest.raises(ToolError, match="not available in profile 'read_only'"):
                await client.call_tool(
                    "campaign_update_campaign",
                    {"customer_id": "1234567890", "campaign_id": "1"},
                )
    update_campaign.assert_not_called()


@pytest.mark.asyncio
async def test_annotations_from_registry() -> None:
    tools = {t["name"]: t for t in await _list("manager")}
    assert tools["search_execute_query"]["annotations"] == {"readOnlyHint": True}
    assert tools["ad_group_criterion_remove_ad_group_criterion"]["annotations"] == {
        "readOnlyHint": False,
        "destructiveHint": True,
    }
    # MCP defaults destructiveHint to true for writes; non-destructive ones say so.
    assert tools["ad_group_criterion_add_keywords"]["annotations"] == {
        "readOnlyHint": False,
        "destructiveHint": False,
    }


@pytest.mark.asyncio
async def test_list_results_are_enveloped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_ADS_MCP_ROW_CAP", "2")
    rows = [{"type": "KEYWORD", "n": i} for i in range(5)]
    mcp = create_server("manager", name="t", instructions="t")
    with patch.object(
        RecommendationService, "get_recommendations", AsyncMock(return_value=rows)
    ):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recommendation_get_recommendations", {"customer_id": "1234567890"}
            )
    envelope = result.structured_content
    assert envelope is not None
    assert envelope["items"] == rows[:2]
    assert envelope["returned"] == 2
    assert envelope["truncated"] is True
    assert "NOT evidence that the item does not exist" in envelope["warning"]


@pytest.mark.asyncio
async def test_transport_error_is_translated() -> None:
    mcp = create_server("manager", name="t", instructions="t")
    failure = Exception(
        "503 Getting metadata from plugin failed with error: "
        "('invalid_grant: Bad Request', {'error': 'invalid_grant'})"
    )
    with patch.object(
        RecommendationService, "get_recommendations", AsyncMock(side_effect=failure)
    ):
        async with Client(mcp) as client:
            with pytest.raises(ToolError) as exc:
                await client.call_tool(
                    "recommendation_get_recommendations", {"customer_id": "1234567890"}
                )
    assert RECONNECT_MESSAGE in str(exc.value)


# --- snapshots and budgets ----------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["manager", "read_only"])
async def test_golden_snapshot(profile: str) -> None:
    golden = GOLDEN_DIR / f"tools_list_{profile}.json"
    current = await _list(profile)
    expected = json.loads(golden.read_text(encoding="utf-8"))
    assert current == expected, (
        f"`tools/list` for {profile!r} changed. If intended, regenerate in the "
        f"same commit: uv run scripts/dump_tools_list.py --profile {profile} "
        f"--out tests/golden/tools_list_{profile}.json"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", sorted(SIZE_BUDGETS))
async def test_size_budget(profile: str) -> None:
    payload = await _list(profile)
    size = payload_size(payload)
    budget = SIZE_BUDGETS[profile]
    assert size <= budget, (
        f"{profile!r} tools/list is {size} chars, budget {budget}; "
        f"largest: {', '.join(largest_tools(payload))}"
    )
