# Working with more than one Google Ads account through one MCP server

**Scope note (2026-09-07):** this is the *local, single-operator*
mechanism — one trusted person (or one Claude Code session) running
`main.py` locally, picking an account by alias per call. The hosted,
multi-tenant product (see
[`../../docs/PLATFORM_ARCHITECTURE.md`](../../docs/PLATFORM_ARCHITECTURE.md))
uses a deliberately different mechanism — one MCP address + bearer token
per account, pinned at the connection rather than passed as a parameter,
because it has to hold up between tenants who don't trust each other, not
just stay convenient for one person. Don't conflate the two or try to
unify them; they solve different problems. Everything below is about the
local case only.

Recorded 2026-09-06: the user is about to start a second project (its own
Google Ads account) while continuing to run boo.ua through the same
deployment, and wants to do it by talking to an MCP client directly
(Claude Desktop, a custom connector, etc.) rather than through the VS Code
extension - so this had to actually work, not just be a plan.

## The one decision that determines how much of this applies

**Is the new account reachable under this deployment's existing manager
account, or does it need entirely separate Google Ads API credentials?**

Check `.env`'s `GOOGLE_ADS_LOGIN_CUSTOMER_ID` - today that's `9587322149`,
boo.ua's manager account, with `5690318342` linked under it as a client
account. `sdk_client.py` authenticates as **one developer token / OAuth
client / manager account for the whole running process** - that hasn't
changed and isn't something this feature touches.

- **New account gets linked under the same manager (`9587322149`)** - this
  is the case everything below actually solves. No credential changes at
  all: every tool already takes `customer_id` per call, so a second linked
  account is reachable the moment it's linked, zero code involved. The
  alias registry below just saves you from typing/remembering a second raw
  numeric id.
- **New account needs its own developer token/OAuth client** (a
  completely separate advertiser, not something you'd link under your own
  manager) - the registry below can't help with that part. You need a
  second `.env` and a second running process, per
  [`CLIENT_ONBOARDING.md`](./CLIENT_ONBOARDING.md)'s per-client checklist.
  Nothing here changes that; it was deliberately deferred (see
  TRACKER.md's 2026-08-27 (3) entry) until there's a second real client
  validating the need for real multi-tenant credential resolution.

## What was built: an account alias registry

`format_customer_id()` (`src/utils.py`) - the one function every single
service already calls before touching `customer_id` - now resolves a
short registered alias (e.g. `"boo-ua"`) to its real numeric customer_id
first, falling back to treating the input as a raw id if it isn't a
registered alias. **This required changing exactly one function, not the
~100 service files that call it** - every existing tool's `customer_id`
parameter already accepts an alias, with no signature changes anywhere.

Deliberately **not** a stateful "current account" - no tool sets a
server-side "active account" that others default to. Two reasons:
1. This process could end up serving more than one concurrent MCP
   connection someday (this session's whole starting point was "move
   towards working via MCP, not the IDE extension") - a mutable global
   "current account" would leak across unrelated conversations.
2. It doesn't need it. The natural unit of "which account are we talking
   about" is the conversation itself - tell the agent which account (by
   alias) once, it keeps using that alias for the rest of the chat, the
   same way you'd say "let's talk about the new project" out loud. Adding
   real statefulness would mean touching every one of ~100 service files'
   `customer_id` parameter to make it optional - not worth it for what a
   conversation already does for free.

### New pieces

- `src/services/review/account_registry_store.py` - `AccountRegistryStore`,
  a JSON-file-backed `alias -> {customer_id, name}` map, same pattern as
  `pending_change_store.py`. Storage: `snapshots/account_registry.json`
  (already gitignored, same sensitivity class as `account_sheets.json` -
  which accounts you manage is business information).
- `src/services/review/account_registry_service.py` - three MCP tools:
  `list_accounts`, `add_account`, `remove_account`. All pure local config -
  none of them call the Google Ads API, so none go through propose/apply
  review (that gate is for changes to a live ad account, not local
  server config) and `add_account`/`remove_account` take effect
  immediately, same as any other local-file operation in this codebase.
- `account_registry.example.json` (repo root, template) /
  `snapshots/account_registry.json` (real file) - `boo-ua` is already
  registered (`5690318342`); add the new project's entry once its account
  is linked and you know its customer_id.

## Checklist for the new project (same-manager case)

1. In the Google Ads UI, link the new project's account under manager
   `9587322149` (Accounts → Link a new account, or accept an invite if
   the new account already exists elsewhere) - this is the one manual,
   outside-of-code step.
2. Note its customer_id (10 digits, shown in the account's UI header).
3. Call `add_account(alias="new-project", customer_id="...", name="...")`
   - or hand-edit `snapshots/account_registry.json` directly, same effect.
4. Call `list_accounts()` to confirm it's there.
5. Sanity-check reachability: run a cheap read (e.g. `search_campaigns`
   or `check_sdk_client_status`) against `customer_id="new-project"` -
   confirms the manager account can actually see it before doing anything
   that writes.
6. If you want fixes logged to a separate Sheet for the new project (the
   existing "1 sheet = 1 account" rule), add its entry to
   `snapshots/account_sheets.json` too - a separate map, not tied to this
   one.
7. From here on, every tool call for the new project just uses
   `customer_id="new-project"` instead of `customer_id="boo-ua"` - same
   running server, same MCP connection, no restart needed.

## Working through an MCP client instead of the VS Code extension

This part is unrelated to the alias registry above - it's about *how* you
connect, not which account you're talking to. `main.py` already runs as a
real MCP server over stdio; the VS Code extension is just one possible
client. To connect a different client instead:

- **Claude Desktop / another local MCP client**: point it at
  `uv run python main.py --groups <groups>` the same way `.mcp.json`
  already does for this repo - any MCP-speaking client that can launch a
  local stdio command works the same way, nothing server-side changes.
- **A remote deployment** (so you're not running a local process at all):
  there's already a read-only remote instance on Railway (see the
  `gads-mcp-remote-readonly-deploy` memory) - a write-capable remote
  deployment is a separate, not-yet-done step (needs auth on the remote
  endpoint, since unlike a local stdio process a network-reachable one
  needs to keep out strangers) - flag this explicitly if/when you want to
  test writes from a non-local client, don't assume the existing
  read-only remote already supports it.

## Explicitly not solved by this

- Per-client credential storage / a real multi-tenant admin panel - still
  the deferred V2 vision (`docs/V2_COMMERCIAL_ROADMAP.md`), untouched.
- Per-account authorization (stopping a caller from using a `customer_id`
  it isn't entitled to) - still doesn't exist in any form; irrelevant for
  a single trusted operator (you) juggling your own accounts, would matter
  the moment this server is exposed to more than one person.
