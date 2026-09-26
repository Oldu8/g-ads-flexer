<div align="center">

<a href="https://openpromo.app">
  <img src="https://openpromo.app/logo.svg" width="80" alt="OpenPromo" />
</a>

# google-ads-mcp

**A typed MCP server for letting AI agents operate Google Ads.**

Built by [**Promobase**](https://openpromo.app) for [**OpenPromo**](https://openpromo.app), the AI-native workspace for creating, publishing, and managing ads.

[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)](https://www.python.org/)
[![Google Ads API](https://img.shields.io/badge/Google%20Ads%20API-v25-4285F4.svg)](https://developers.google.com/google-ads/api/docs/start)
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP-111827.svg)](https://github.com/jlowin/fastmcp)
[![CI](https://github.com/promobase/google-ads-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/promobase/google-ads-mcp/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](./LICENSE)

</div>

---

## What

`google-ads-mcp` wraps the official Google Ads Python SDK in a Model Context Protocol server. It exposes Google Ads API v25 services as typed MCP tools, so LLMs and agent runtimes can safely inspect accounts, create campaigns, manage budgets, upload conversions, work with assets, and run GAQL search.

This repo is the Google Ads execution layer behind OpenPromo's agent workflows. For application-facing, multi-platform ad publishing and inbox automation, use the companion SDK:

**[`@promobase/ad-platforms`](https://www.npmjs.com/package/@promobase/ad-platforms)** - one TypeScript SDK for Meta, TikTok, and soon Google Ads, with AI SDK tools and production clients for ad platform automation.

## Why

Google Ads has a large, typed API surface, but it is hard for agents to use directly. This server keeps the reliability of the official Python SDK while giving agents a structured tool interface:

- **Official SDK foundation** - built on `google-ads`, including its auth, retries, paging, and protobuf types.
- **Typed service wrappers** - implementations use Google Ads API v25 generated service, resource, enum, and operation types.
- **Agent-ready MCP tools** - FastMCP servers grouped by workflow: core, assets, targeting, bidding, planning, reporting, conversions, account management, and more.
- **GAQL access** - search and metadata tools for reporting, discovery, and account inspection.
- **Production-oriented scope** - designed for OpenPromo's ads loop: generate creative, build campaigns, publish, measure, and iterate.

## Coverage

| Area | Status |
|------|--------|
| Google Ads API version | `v25` |
| Wrapped services | 97, 366 tools (gaps listed at the end of [`TRACKER.md`](./TRACKER.md)) |
| Coverage model | 1:1 service mapping where implemented |
| Type policy | Generated Google Ads protobuf types |
| What this service can do (task-level) | [`docs/CAPABILITIES.md`](./docs/CAPABILITIES.md) |
| Platform plan and architecture | [`../docs/ROADMAP.md`](../docs/ROADMAP.md), [`../docs/PLATFORM_ARCHITECTURE.md`](../docs/PLATFORM_ARCHITECTURE.md) |

Core campaign, ad group, ad, budget, keyword, conversion, asset, audience, recommendation, account, billing, and reporting workflows are implemented; implementation history lives in [`TRACKER.md`](./TRACKER.md).

## Install

```bash
git clone https://github.com/promobase/google-ads-mcp.git
cd google-ads-mcp
uv sync
```

Create a `.env` file or export the required Google Ads credentials:

```bash
GOOGLE_ADS_CLIENT_ID="your_client_id"
GOOGLE_ADS_CLIENT_SECRET="your_client_secret"
GOOGLE_ADS_REFRESH_TOKEN="your_refresh_token"
GOOGLE_ADS_LOGIN_CUSTOMER_ID="optional_manager_customer_id"
```

See [`.env.example`](./.env.example) for the full credential template. The quickest way to get the three OAuth values is to download the OAuth client JSON from Google Cloud Console and run `uv run scripts/verify_google_access.py --client-secrets <json> --label me --write-env .env`: it signs you in, writes `.env`, and checks that API access works.

Google removed the developer token on 2026-09-09: API access level now
belongs to the Google Cloud project that owns your OAuth client, and the
header is ignored, so there is nothing to configure for it
(`google-ads` 32.0.0+ does not require one). A manager account is optional:
set `GOOGLE_ADS_LOGIN_CUSTOMER_ID` only when you reach the account through
one.

## Run

The server always mounts every service (366 tools) and exposes one **tool
profile** from [`tool_profiles.yaml`](./tool_profiles.yaml):

```bash
uv run main.py                       # `manager`: 77 tools, ~20k tokens (default)
uv run main.py --profile read_only   # 29 tools, ~8k tokens: reads + fixes log
uv run main.py --profile all         # all 366 tools, ~93k tokens (development)
```

| Profile | What the agent gets |
|---------|---------------------|
| `manager` | GAQL reporting and field metadata, campaigns, budgets, ad groups, keywords and negatives (shared sets included), responsive search ads, recommendations, asset extensions (sitelink, callout, snippet, call), location/language/device targeting and bid modifiers, audiences and remarketing lists, the pending-change review flow and the fixes log |
| `read_only` | `manager`'s reads plus the fixes log, computed from the tool registry; nothing that can change an account |
| `all` | every tool the library wraps |

Hidden tools cannot be called by name either. List results are capped at
500 items (`GOOGLE_ADS_MCP_ROW_CAP`) and come back as
`{items, returned, truncated, warning}`; GAQL queries without `LIMIT` get
one. Every tool is classified in [`src/tool_registry.py`](./src/tool_registry.py),
which also drives the MCP `readOnlyHint` / `destructiveHint` annotations.
`scripts/dump_tools_list.py --profile <name>` prints what a client sees.

## MCP Client

Example stdio configuration:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "uv",
      "args": ["run", "main.py", "--profile", "manager"],
      "cwd": "/path/to/google-ads-mcp",
      "env": {
        "GOOGLE_ADS_CLIENT_ID": "...",
        "GOOGLE_ADS_CLIENT_SECRET": "...",
        "GOOGLE_ADS_REFRESH_TOKEN": "...",
        "GOOGLE_ADS_USE_PROTO_PLUS": "true"
      }
    }
  }
}
```

## Development

```bash
# Format
uv run ruff format .

# Type check
uv run pyright

# Test
uv run pytest
```

When adding a service:

1. Check the Google Ads API v25 generated service types.
2. Implement the service wrapper with generated protobuf request, operation, resource, and enum types.
3. Register lightweight MCP tools for the service.
4. Add focused tests.
5. Update [`TRACKER.md`](./TRACKER.md).
6. Run `uv run ruff format .` and `uv run pyright`.

## Related

| Project | Description |
|---------|-------------|
| [OpenPromo](https://openpromo.app) | AI-native workspace for creating, publishing, and managing ads |
| [`@promobase/ad-platforms`](https://www.npmjs.com/package/@promobase/ad-platforms) | TypeScript ad platform SDK with AI SDK tools for Meta, TikTok, and Google Ads work |
| [`promobase/ad-platform-sdks`](https://github.com/promobase/ad-platform-sdks) | Source repo for Promobase's multi-platform ad SDKs |

## License

AGPL-3.0 — see [`LICENSE`](./LICENSE) and [`NOTICE.md`](./NOTICE.md).

## Disclaimer

This is an unofficial Google Ads API integration. It is not affiliated with, endorsed by, or supported by Google.
