# Platform architecture

How the platform works once the specced changes are built. **Order of
work, decisions and open items** live in [`ROADMAP.md`](./ROADMAP.md).
**Exact contracts** (columns, formats, behaviours, test scenarios) live in
the OpenSpec changes under [`../openspec/changes/`](../openspec/changes/);
where this document and a spec disagree, the spec wins.

Rewritten 2026-09-25. Earlier versions (the "one user = one MCC + one
developer token" model, the read-only MVP, per-client deployments) are in
git history.

## What we are selling

Not "an MCP endpoint to Google Ads": that is a commodity (Composio,
Pipedream and Zapier already host one with OAuth). The product is an
**AI PPC assistant with guardrails and memory**:

- per-account business context the agent always sees;
- a fixes log (one Google Sheet per ad account) with expected outcomes,
  reviewed at 1, 2 and 4 weeks;
- writes that only happen through a queued, previewed, approved change.

All three exist in `mcp-server/` today for one local operator. The
platform makes them multi-tenant.

## The shape

```
 person ──Google sign-in──► web/ (Next.js cabinet) ──writes──► Postgres (Supabase)
                                                                   ▲
 MCP client (Claude, ChatGPT, …) ──bearer token──► mcp-server/ ────┘ reads accounts,
                                                       │            writes queue + usage
                                                       ▼
                                                Google Ads API
```

- **`web/`** (Next.js, Drizzle, Auth.js) owns the database schema and all
  migrations, signs people in, discovers their ad accounts, issues one
  bearer token per exposed account.
- **`mcp-server/`** (Python, FastMCP, `google-ads` SDK) serves MCP over
  streamable HTTP at one URL, `/mcp`. The bearer token decides which ad
  account a request is pinned to.
- They never call each other; **Postgres is the only integration point**.
  Both are deployed on Railway.

## Google access without a developer token

On 2026-09-09 Google retired developer tokens
([developer token](https://developers.google.com/google-ads/api/docs/api-policy/developer-token),
[access levels](https://developers.google.com/google-ads/api/docs/api-policy/access-levels)):

- The API access level belongs to the **Google Cloud project that owns
  the OAuth client** used to get the user's token. Ours is
  `178951272716`. Access levels were migrated from developer tokens to the
  projects that used them in the preceding 90 days; they cannot be moved
  to another project, and a new project starts at Test. **This project is
  a non-replaceable asset.**
- The `developer-token` header is optional and ignored; a future major API
  version will reject it. `google-ads` **32.0.0** (released 2026-09-09) no
  longer requires `developer_token` in its config and only sends the
  header when one is set. The repo uses 33.0.0 (API v25.2) and has no
  developer token anywhere.
- **No manager account is needed.** An identity that has access to an ad
  account can call the API for it directly; `login-customer-id` is only
  needed when access goes through a manager.
- Levels: Test (test accounts only), Explorer (2,880 ops/day on
  production accounts), Basic (15,000 ops/day), Standard (unlimited).
  Basic and Standard require brand verification of the Cloud project.
  **Our project is Basic** (confirmed in the console by the operator,
  2026-09-25).

**Premise status: verified for the operator's identity on 2026-09-25**
with `mcp-server/scripts/verify_google_access.py`: no developer-token
header, a garbage header ignored, direct and MCC (`login-customer-id`)
access, a `validate_only` write, and the SDK path all pass (request ids in
`mcp-server/TRACKER.md`). Still to run: a second Google identity reaching
accounts through an MCC it was invited to, i.e. the agency scenario
(`ROADMAP.md`, Phase 0.1, step 3).

Consequences for the design:

- `web/` and `mcp-server/` **must use the same OAuth client**: a refresh
  token only works with the client it was issued to, and that client's
  project sets the access level.
- The quota is **one budget shared by every tenant**, so it is counted
  and capped per account (below).
- Until the `adwords` sensitive scope is verified, the consent screen
  stays in Testing: only listed test users can sign in, and their refresh
  tokens expire after 7 days.

## Data

One database, **tenants separated by rows**: every tenant-owned row
carries `ad_account_id`, and the MCP server takes it from the bearer
token, never from tool arguments. Prod and dev are two schemas (`app`,
`app_dev`) in one Supabase project, each with its own `web_*` and `mcp_*`
roles and its own token-encryption key; the dev roles cannot read prod.

| Table | Written by | Purpose |
|---|---|---|
| `users`, `sessions`, `verification_tokens` | web (Auth.js) | identities and sessions |
| `google_connections` | web | one Google grant; the Auth.js account table plus `refresh_token_enc` (AES-256-GCM, never plaintext) and `revoked_at` |
| `ad_accounts` | web | one exposed ad account: `(customer_id, login_customer_id)` from discovery, `bearer_token_hash`, `enabled`, `tool_profile`, `context`, `fixes_sheet_id` |
| `pending_changes` | mcp-server | the write queue |
| `api_usage` | mcp-server | operations per account per quota day |

The MCP role cannot read `users` or `sessions`. Columns, grants and byte
formats: `openspec/changes/platform-db-and-cabinet/specs/platform-schema/`.

## Connecting an account

1. Sign in with Google (Auth.js). The same consent grants `adwords`,
   offline. The refresh token is stored encrypted only.
2. Discovery, from Next.js over REST: `listAccessibleCustomers`, then a
   `customer_client` walk under every manager. Enabled non-manager
   accounts are offered as checkboxes; each chosen one becomes an
   `ad_accounts` row with the `login_customer_id` that reached it.
3. Per account: generate a token (shown once, stored as sha256), copy the
   MCP URL, toggle enabled, toggle "allow changes" (`read_only` →
   `manager`), write the business context, set the fixes-log sheet.

This is the only way an account appears, for the operator and for
customers alike: no hardcoded ids, no pasted ids.

## Serving a request

```
bearer token → DbTokenVerifier (hash lookup; enabled; connection not revoked)
  → tenant contextvar (ad_account, connection, customer_id, login_customer_id, profile)
  → profile middleware (filter list + call; annotations; customer_id hidden and injected;
                        account_context tool)
  → write-queue middleware (ads_write tools are queued, not executed)
  → service code (unchanged logic; gets clients via get_service())
  → transport interceptor ── pins customer_id ── forces validate_only while queuing
                         ── counts quota and enforces caps
  → Google Ads API
```

- **Credentials per request.** Service clients are cached per
  `(connection, login_customer_id, service)`, never on the service
  object. Today all 99 services cache a client on `self`; in a
  multi-tenant process that would hand one tenant's credentials to the
  next, so the change is mandatory.
- **The transport interceptor is the choke point.** One gRPC interceptor
  on every client enforces the pinned account, dry-run and quota for all
  366 tools without touching them.
- **Account context** is carried in the description of a synthetic
  `account_context` tool. FastMCP 2.14.7 sends `InitializeResult` before
  middleware can change it, so per-tenant `instructions` are impossible.
- **Local mode** (`main.py`, stdio) takes a cabinet-issued token from
  `MCP_ACCOUNT_TOKEN` and runs the same stack.

Spec: `openspec/changes/hosted-multitenant-writes/`.

## Tool surface

366 tools exist (about 86k tokens if all are listed). The agent sees a
**profile**:

- `manager`: 77 tools (~18k tokens): reporting and GAQL, campaigns,
  budgets, ad groups, keywords and negatives, RSAs, recommendations,
  asset extensions, targeting and bid modifiers, audiences, the queue and
  the fixes log.
- `read_only`: computed from `manager`: its reads plus the fixes log
  (33 tools, ~8k tokens).
- `all`: everything, for local development.

Profiles are YAML validated against a tool registry that classifies
every tool explicitly (`read` / `ads_write` / `internal_write` /
`local_only`). Filtering applies to both listing and calling. A golden
snapshot and a size budget per profile fail CI on drift. List responses
are capped at 500 rows, with an explicit "truncated, absence is not proof"
warning. Spec: `openspec/changes/agent-surface-profiles/`.

## Writes

Every `ads_write` call is **queued, not applied**. The tool runs with
`validate_only` forced on by the interceptor, the change is stored in
`pending_changes` with a readable preview and a validation outcome
(`full` / `partial` / `none`), and the agent gets a `change_id`. Only
`apply_pending_change` executes it: atomic claim, scoped to the pinned
account, expires after 24 h, fixes-log entry written best-effort after
success. Approval happens in the chat; the tool description requires it,
but it is guidance, not enforcement. Spec: `…/specs/write-queue/`.

## Quota

The interceptor counts every call into `api_usage` (a mutate counts its
operations; `validate_only` counts too). Defaults: 1,500 ops/day and
60/min per account; at 90% of 15,000 for the whole project every account
is stopped until the quota day resets (00:00 Pacific), and the operator
is alerted once. `scripts/usage_report.py` shows the 7-day average
against the Standard-access trigger (7,500/day).

## Known constraints and risks

- **MCP clients and static bearer tokens.** Claude Code sends custom
  headers. Whether the clients pilot users actually use (Claude Desktop /
  claude.ai connectors, ChatGPT) accept a static bearer token or require
  OAuth has not been checked. If they require OAuth, token issuance in
  the cabinet changes. To be checked before the pilot.
- **Approval is conversational.** A model that ignores the instruction
  can call `apply_pending_change` without asking. The queue guarantees a
  stored preview and an audit trail, not a human in the loop.
- **Tenant isolation is enforced in the MCP server**, not by Postgres RLS
  (deferred).

## Naming

The product has no name yet. "g-ads-flexer" is the repo, not the product.
Unchecked candidates: AdWire, AdsDock, Adnex, PlugAds, AdSwitchboard.
