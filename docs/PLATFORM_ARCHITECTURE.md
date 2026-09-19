# Platform architecture — multi-tenant Google Ads AI access

Recorded 2026-09-06/07, **re-based 2026-09-14** after two things changed:

1. **Google removed the developer token from the Google Ads API
   (2026-09-09).** Access level now belongs to the Google Cloud project
   that owns the OAuth client. This collapses the hardest onboarding step
   and invalidates the "one user = one MCC + one dev token" model the
   earlier version of this doc was built on. Facts are in "Access level
   lives on the Cloud project".
2. **Launch scope was cut to a read-only MVP** ("minimum plan", decided
   2026-09-14) so the idea can be tested with real users before any of
   the write/billing/SEO surface gets built. See "Phased plan".

This supersedes [`mcp-server/docs/V2_COMMERCIAL_ROADMAP.md`](../mcp-server/docs/V2_COMMERCIAL_ROADMAP.md)
(historical) and the per-client-deployment model in
[`mcp-server/docs/CLIENT_ONBOARDING.md`](../mcp-server/docs/CLIENT_ONBOARDING.md)
(still accurate for the *local* single-operator setup, superseded for the
hosted product).

## The shape

Two people-facing needs, one architecture underneath:

1. **The user, right now**: keep running boo.ua, start a second Google
   Ads account, switch between them from one chat interface (phone +
   computer, same synced conversation) without per-device configuration.
2. **The product**: a hosted, multi-tenant service — anyone logs in with
   Google, picks which of their Google Ads accounts to expose, and gets a
   personal MCP address + bearer token per account to paste into
   Claude/ChatGPT/any MCP-capable client.

Both are the same mechanism at different scale (1 user vs. N).

**What we are actually selling** (decided 2026-09-14, after an honest look
at Composio/Pipedream/Zapier already offering hosted Google Ads MCP with
OAuth): not "an MCP endpoint to Google Ads" — that is a commodity and any
platform owner can ship it tomorrow — but an **AI PPC assistant with
guardrails and memory**: per-account business context the agent always
sees, a fixes log with expected outcomes reviewed at 1/2/4 weeks, and
(later) writes that only happen through a propose → approve step. Those
three already exist in `mcp-server/`; the product is making them
multi-tenant, not adding features.

## Two repos, two stacks, one database

- **`mcp-server/`** (Python) — the Google Ads API engine, built on the
  official Google Ads Python SDK. Owns: the ~100 typed MCP tools, the
  multi-tenant HTTP entrypoint, per-request credential resolution, its own
  `TokenVerifier`, API-usage accounting.
- **`web/`** (Next.js, not started) — the product surface: homepage,
  privacy/terms, Google login, the one-screen dashboard (connect → pick
  accounts → copy MCP URL + token). Owns the Postgres schema and all
  migrations, the OAuth flow, bearer-token issuance. Marketing (pricing
  page, blog) is **out of MVP scope**; if a blog ever exists it will be
  automated and low-effort, not a Phase.

**They meet only at Postgres (Supabase-hosted).** Next.js writes rows;
the Python side reads them at request time (plus writes usage counters,
see "Quota"). No API calls between the two repos for this — the database
*is* the integration contract. Don't add a direct Next.js → Python (or
reverse) dependency without a real reason.

## Access level lives on the Cloud project (developer token is gone)

Facts as of 2026-09-09 (Google's change; recorded, not to be re-verified):

- **The developer token is deprecated.** The API access level now belongs
  to the **Google Cloud project that owns the OAuth client ID/secret**.
  The `developer-token` request header is optional and ignored; a future
  major API version will reject it.
- **Our Cloud project `178951272716` has Basic access: 15,000 operations
  per day for the whole project — i.e. all tenants combined.** See
  "Quota" below; this is now a first-class design constraint, not a
  Phase-3 nicety.
- **Standard access** requires a manual Google audit (~10 business days),
  demo access to the product, and compliance with Required Minimum
  Functionality (RMF) for whatever campaign-management surface we expose.
- **Brand verification of the Cloud project is mandatory** for any new
  Basic/Standard application. Re-associating an access level with a
  different Cloud project is **no longer supported** — a new project
  starts at Test. Consequence: **project `178951272716` is a
  non-replaceable asset.** Never create a second project "to clean up";
  keep the OAuth client, consent screen and brand verification all on it.
- **An MCC is no longer required for API access.** It is only needed to
  *manage* several accounts under one login. Users can therefore be any
  Google identity with access to an ad account — no MCC prerequisite in
  onboarding. API Center is obsolete.

**SDK caveat (verified locally 2026-09-14, `google-ads==31.2.0`):** the
Python SDK still lists `developer_token` in `_REQUIRED_KEYS`
(`google/ads/googleads/config.py`) and still injects the
`developer-token` header on every call (`metadata_interceptor.py`). So
"stop sending it" is gated on an SDK release that makes it optional.
Until then: build every client through one function with a fixed
placeholder value (a constant, not a secret, not per-tenant), and
track the SDK changelog so the placeholder is removed before the API
version that rejects the header ships. This is the only place the words
"developer token" should survive in code.

## Login: one Google OAuth grant does both jobs

Log into the product with a Google account that has access to the ad
accounts you want to expose. One OAuth screen, two results:

- **Identifies the user** — `users` keyed by the OAuth `sub` (stable,
  unlike email).
- **Authorizes Ads access** — the same grant requests the `adwords` scope
  alongside profile/email, so the resulting refresh token already covers
  Ads API access.

One OAuth client for the whole product, on Cloud project `178951272716`
(see above for why that project is now irreplaceable). Build with
**Auth.js (NextAuth) + Google provider + a Supabase DB adapter**; don't
hand-roll it.

**Explicitly not using**: JWT anywhere; Supabase Auth as the identity
system (Supabase is Postgres only, so the DB can move to another Postgres
host later without an identity migration). Auth.js's DB-adapter sessions
are plain rows, not JWTs.

### OAuth verification for the `adwords` scope — now Phase 0

`adwords` is a **sensitive** scope, not restricted (checked against
Google's restricted-scopes list; Ads isn't on it). So: no CASA
assessment, no annual re-certification; verification is ~3-5 business
days and reviews the consent screen, scope justification, homepage and
privacy policy — not feature completeness.

Until verified, the OAuth app is in Testing mode: max 100 manually-added
test users and **refresh tokens expire after 7 days** (already hit once,
see `mcp-server/TRACKER.md` 2026-08-27 (11)). That makes a pilot with
external users impractical, which is why homepage + privacy policy +
terms + Cloud-project brand verification are **Phase 0** — they unblock
both scope verification and any future access-level application, and
they need no product code.

## Data model

```
users               1 row per Google identity (keyed by OAuth `sub`)
  └─ 1:N ─→ google_connections   one row per OAuth grant
                                 (google_sub, email, refresh_token
                                  [encrypted at rest], scopes, granted_at,
                                  revoked_at)
                 └─ 1:N ─→ accounts   one row per ad account the user
                                      chose to expose
                                      (customer_id, login_customer_id,
                                       display_name, slug,
                                       bearer_token_hash, enabled,
                                       tool_profile, context,
                                       fixes_sheet_id, created_at,
                                       last_used_at)

api_usage           per-account daily operation counters
                    (account_id, day, operations, last_call_at)
```

Changes from the 2026-09-07 sketch, and why:

- **`mcc_connections` → `google_connections`.** A connection is an OAuth
  grant from a Google identity, not an MCC. There is no dev token to
  store. One grant can reach N ad accounts, directly or through any
  managers that identity has access to.
- **`accounts` stores the pair `(customer_id, login_customer_id)`.**
  `login_customer_id` is the manager account through which access to
  `customer_id` resolves (the `login-customer-id` header), or NULL when
  the identity has direct access. It is fixed at connect time by
  discovery (below), never chosen by the LLM.
- **`users` 1:N `google_connections`** in the schema (a freelancer may
  have two Google identities for two client groups); the MVP UI exposes
  one connection per user. Don't build the multi-connection UI until a
  pilot user asks.
- **`tool_profile`** (`read_only` | `manager`): which tool set the
  account's MCP mount exposes. MVP only ever sets `read_only`.
- **`context`** (plain text, cap ~2000 chars): per-account business
  context, e.g. "marketplace reselling pawnshop items, ~10% margin, so
  ROAS ≠ profit". Injected as the account's FastMCP mount
  `instructions`, so the agent always sees it without a tool call.
  Text only; no structure until a real need shows up.
- **`fixes_sheet_id`**: the client's own Google Sheet for that ad
  account's fixes log (one sheet per client per ad account — never per
  user or per manager). The client shares it with the platform's Sheets
  service account as Editor; the dashboard shows that email. This
  replaces `snapshots/account_sheets.json` for the hosted entrypoint
  (the local `main.py` keeps the JSON file).
- **`bearer_token_hash`**: the token is shown once in the dashboard and
  stored hashed; `TokenVerifier` compares hashes. A readable URL
  `domain/mcp/<slug>` is fine — the token is the security boundary.

### Account discovery (replaces "paste your MCC id")

At connect time, and on a "refresh" button:

1. `CustomerService.list_accessible_customers` with the grant's refresh
   token → the customer ids the identity can access directly (ad accounts
   and managers).
2. For each result that is a manager: GAQL over `customer_client`
   (`login-customer-id` = that manager) reading `customer_client.level`,
   `.manager`, `.status`, `.descriptive_name`, `.id` → the tree beneath it.
3. Flatten to `(customer_id, login_customer_id, display_name, is_manager,
   status)`; show non-manager, enabled accounts as checkboxes; store the
   chosen rows in `accounts` with the `login_customer_id` that reached
   them (NULL for direct hits from step 1).

Where this runs is still open (see "Open"): leaning **directly from
Next.js via the REST endpoint** — it is now just an OAuth bearer + REST
call with no dev-token header, so there is no reason to route it through
Python.

## Auth on the MCP server itself: no JWT here either

FastMCP's `TokenVerifier` base class is not JWT-specific (confirmed by
reading the installed package). A small custom `TokenVerifier` does a
`SELECT` on `accounts` by token hash and returns an `AccessToken` carrying
`account_id`, `google_connection_id`, `customer_id`, `login_customer_id`,
`tool_profile`. Inside any tool `get_access_token()` yields those fields
**without changing any of the ~100 tool signatures** — one choke point.

`sdk_client.py`'s process-wide singleton becomes per-request resolution:
account → its connection's decrypted refresh token → a `GoogleAdsClient`
built from the platform OAuth client id/secret + that refresh token +
`login_customer_id` (+ the SDK placeholder, see caveat above), cached in
memory keyed by `(google_connection_id, login_customer_id)`. This is the
one structural change to `mcp-server/`; the wrapped services don't change.

`customer_id` per tool call is **not** chosen by the LLM on the hosted
entrypoint: the choke point overrides/validates it against the pinned
account. That is what makes "one chat can't touch the wrong account" a
structural guarantee rather than a prompt-level hope.

## Quota: 15,000 operations/day is shared by every tenant

Basic access is a project-wide budget, so one noisy tenant can exhaust
the API for everyone. This moves accounting and limiting from Phase 3
into Phase 1:

- **Count at the choke point.** Every Google Ads API call made through
  the per-request client increments `api_usage(account_id, day)`.
  Count requests, and mutate operations individually inside a mutate
  request, to stay conservative relative to how Google counts.
- **Per-account daily cap** (start at 1,000 ops/day ≈ 7% of the project;
  tune from pilot data) and a **per-minute burst cap** (e.g. 30/min). Over
  cap → the tool returns a clear "daily API quota for this account is
  exhausted, resets at 00:00 PT" instead of a raw quota error.
- **Project-level guard**: at 90% of 15,000 the entrypoint refuses
  non-cached calls for everyone with the same message and alerts the
  operator; better a clean stop for all than Google throttling the
  project unpredictably.
- **Cheap wins that reduce ops**: GAQL results cached per account for a
  few minutes; `list_accessible_customers`/discovery cached for a day.
- **Threshold for applying for Standard**: rough sizing — an active chat
  session is ~50-150 ops; an account used daily ~300-500 ops/day; so
  Basic supports roughly 30-40 daily-active accounts. Start the Standard
  application when 7-day average usage passes **~50% (7,500/day)**,
  because the audit is ~10 business days plus preparation, and the
  per-account cap keeps Basic survivable meanwhile.

## What already exists in `mcp-server/` and how it relates

- **`AccountRegistryStore`/`format_customer_id` alias resolution**
  (`src/services/review/account_registry_store.py`) — the **local,
  single-operator** mechanism: JSON aliases resolved by the one human
  running `main.py`. Not the hosted mechanism (where the account is
  pinned at the connection). Both coexist; don't unify them.
- **`remote_main.py`** — today's read-only, single-tenant, static-bearer
  deployment. The multi-tenant HTTP entrypoint is a **third** entrypoint,
  not a modification of either; it starts from the same read-only tool
  set `remote_main.py` already mounts (verified free of mutate calls).
- **Guarded writes** (`propose_* → apply_pending_change`), **fixes log**
  (`FixesLogService`, Google Sheet per ad account), **Ads Editor paste
  tables** (the pattern used for bulk keyword/ad changes) — the
  differentiators. MVP ships the fixes log and the Editor tables; guarded
  writes come in Phase 4 once `pending_changes.json` moves to Postgres.

## Tool surface: curated, not 1:1

Mounting ~100 tools into Claude Desktop/ChatGPT is a product problem:
descriptions eat context, near-duplicate services confuse the model, and
a marketer doesn't know what a `campaign_criterion` is. The 1:1 API
mapping stays as the engine; the hosted entrypoint mounts **profiles**:

- **`read_only` (MVP):** GAQL (`execute_query`, `search_*`), field
  metadata, recommendations (read), audience insights, invoices; plus
  task-level tools: account overview, keyword/search-term audit, "propose
  changes as an Ads Editor table" (the agent proposes, the user pastes
  into Google Ads Editor and applies — no API write, liability stays with
  the marketer, value is already visible), fixes-log tools (`log_fix`,
  `list_fixes`, `update_fix_review`, `update_fix_conclusion`).
- **`manager` (Phase 4):** `read_only` + guarded writes restricted to a
  **whitelist of fields**, not the whole mutable surface: keyword
  add/pause/negative, campaign status/budget/target (ROAS/CPA), ad
  pause/enable. Narrow on purpose — it limits blast radius, keeps the
  approval diff readable, and keeps the RMF exposure for the Standard
  audit to a small, defensible set.

## Naming

"g-ads-flexer" was never the product name. Candidates (unchecked against
a registrar): AdWire, AdsDock, Adnex, PlugAds, AdSwitchboard. Doesn't
block any phase; folder names are stack-descriptive on purpose.

## Phased plan (re-based 2026-09-14)

**Phase 0 — unblock Google (no product code; start now, runs in parallel
with everything else):**
- Static homepage (what the product is, support email) + privacy policy
  + terms on the product domain.
- Brand verification of Cloud project `178951272716`; consent-screen
  branding (name, logo, support email, the two pages above).
- Submit sensitive-scope verification for `adwords`. Until it clears,
  pilots run as manually-added test users with 7-day refresh tokens.

**Phase 1 — `mcp-server/` multi-tenant backend (read-only):**
- Postgres schema above, agreed with the `web/` side (Auth.js adapter
  conventions constrain `users`); Python reads `accounts`/
  `google_connections`, writes `api_usage`.
- Remove the developer token: placeholder constant in one client-builder
  function (SDK caveat), no env var, no DB column, no doc mention outside
  that caveat.
- Custom `TokenVerifier` (DB lookup by token hash).
- `sdk_client.py`: singleton → per-request resolution + cache keyed by
  connection.
- New HTTP entrypoint mounting the `read_only` profile per account, with
  `context` injected as mount `instructions`.
- Fixes log resolved from `accounts.fixes_sheet_id` (not
  `account_sheets.json`) on the hosted entrypoint.
- API-usage accounting + per-account/per-project limits (see "Quota").
- **Not in MVP:** `pending_changes.json` → Postgres migration (no writes
  yet), token rotation UI, change history.

**Phase 2 — `web/` one-screen cabinet:**
- Auth.js + Google provider requesting `adwords` in the same grant;
  refresh token encrypted into `google_connections`.
- Discovery (accessible customers + `customer_client` walk) → checkbox
  list → `accounts` rows.
- Per account: MCP URL + bearer token (shown once), enable/disable,
  `context` textarea, `fixes_sheet_id` field with the service-account
  email to share with.
- No pricing page, no billing, no blog. Payments are handled manually
  by the operator during the pilot.

**Phase 3 — pilot:**
- 5-10 users from the operator's own network, free, read-only.
- Success metric: weekly active use after 3 weeks and a stated
  willingness to pay per account. Nothing in Phase 4 starts before this
  reads positive.

**Phase 4 — writes, productionize, Standard access:**
- Guarded writes on the hosted entrypoint: `pending_changes` → Postgres,
  approve via chat or a dashboard diff; `manager` profile with the field
  whitelist above.
- **Standard access application** — explicit item with dependencies:
  1. brand verification done (Phase 0);
  2. a demo Google Ads account with realistic data + a demo login for
     Google's reviewers;
  3. written product description presenting guarded writes (propose →
     approve) and the fixes log as the change-control mechanism, and the
     field whitelist as the RMF scope;
  4. RMF gap check for exactly the whitelisted write areas;
  5. trigger: 7-day average usage ≥ ~50% of Basic, or the pilot needs
     more than ~30 daily-active accounts — whichever first.
- Token rotation/revocation, change-history view, abuse protection
  beyond the quota caps (IP rate limits, token misuse detection).
- Billing (Paddle/Lemon Squeezy or similar merchant-of-record, per
  account), only after Phase 3 says yes.

## Open / not decided yet

- Exact Postgres column types; finalize when `web/` (Auth.js adapter)
  starts.
- Discovery from Next.js directly (REST, leaning yes) vs. proxied through
  Python.
- Refresh-token encryption: Supabase Vault vs. app-level key in env.
  Either is fine for the pilot; decide before external users.
- How Google counts "operations" for Basic exactly (per request vs. per
  mutate operation) — accounting is conservative until measured against
  the Cloud console's quota page.
- Product name.
