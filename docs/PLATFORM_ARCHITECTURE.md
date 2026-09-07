# Platform architecture — multi-tenant Google Ads AI access

Recorded 2026-09-06/07, superseding
[`mcp-server/docs/V2_COMMERCIAL_ROADMAP.md`](../mcp-server/docs/V2_COMMERCIAL_ROADMAP.md)'s
older, deliberately-deferred vision. That doc is left as historical record
(and its per-account-authorization gap analysis is still accurate) but the
concrete plan lives here now, because the user is actually starting to
build it — repo already restructured for it (see below), not just planned.

## The shape

Two people-facing needs, one architecture underneath:

1. **The user, right now**: continue running boo.ua, and start a second
   Google Ads account, switching between them from one chat interface
   (phone + computer, same synced conversation) without re-configuring
   anything per device.
2. **The bigger goal**: a hosted, multi-tenant product — anyone logs in,
   connects their own Google Ads manager account (MCC), and gets a
   personal MCP address per ad account they choose to expose, to paste
   into Claude/ChatGPT/any MCP-capable client.

Both are the same underlying mechanism at different scale (1 user vs. N),
which is why it's designed once, here.

## Two repos, two stacks, one database

- **`mcp-server/`** (Python) — the Google Ads API engine. Can't
  reasonably be anything but Python; it's built on the Google Ads Python
  SDK. Owns: the ~100 MCP tools (already built), the multi-tenant HTTP
  entrypoint, per-request credential resolution, its own `TokenVerifier`.
- **`web/`** (Next.js, not started) — the product surface: landing page,
  pricing, blog (SEO), terms/privacy, login, account dashboard. The
  user's own stack — they don't do Python web dev, and marketing/SEO
  pages are squarely Next.js's strength, not Python's. Owns: the Postgres
  schema and all migrations, the OAuth login flow, bearer-token issuance.

**They meet only at Postgres (Supabase-hosted).** Next.js writes rows
(users, cabinets, accounts, tokens); the Python side only ever reads them,
at request time, to resolve which Google Ads credentials + which
`customer_id` a given incoming MCP request is for. No API calls between
the two repos for this — the database *is* the integration contract. Keep
it that way; don't add a direct Next.js → Python (or reverse) API
dependency without a real reason, it defeats the point of the split.

## Login: one Google OAuth grant does both jobs

Rejected a separate "email magic-link login for our site" + "separate
Google OAuth consent to connect the MCC" two-step design. Every Google Ads
MCC is administered by some Google identity anyway, so: **log into the
product with the same Google account that administers your MCC**, one
OAuth screen, two things happen at once:

- **Identifies the user** — key the `users` table by the OAuth
  `sub` (stable, unlike email, which can change), not by email.
- **Authorizes Ads access** — the same grant requests the `adwords` scope
  alongside basic profile/email, so the resulting refresh token already
  covers Ads API access. No separate consent screen.

One shared Google Cloud OAuth client for the whole product (identifies
the *application*, not the caller — completely normal to reuse across all
users, same as any "Sign in with Google" button). Build this with
**Auth.js (NextAuth) + its Google provider + a Supabase DB adapter** —
mature, well-tested, in the user's own stack; don't hand-roll it.

**Explicitly not using**: JWT anywhere, and not Supabase Auth as the
identity system (Supabase is Postgres only, chosen so it can migrate to
a different Postgres host — e.g. the user's own Google Cloud project —
later without an identity-system migration bundled in). Auth.js's own
session mechanism (its DB adapter persists sessions as plain rows, not
JWTs, when configured that way) satisfies this without extra work.

### What's still a separate, unavoidable manual step

**Developer token.** Confirmed (not assumed) via Google's own docs: the
developer token is issued to a **manager (MCC) account** via API Center,
never to an individual ad account, and a non-manager account can't
generate one at all
([onboarding guide](https://developers.google.com/google-ads/api/docs/get-started/onboarding),
[developer token docs](https://developers.google.com/google-ads/api/docs/api-policy/developer-token)).
This is good news for the data model: **exactly one dev token per user**
(since one user = one MCC, see below), not one per ad account. It's also
unavoidably manual — Google's own review process, no OAuth substitute —
so the dashboard just shows instructions and a paste-it-in field.

## Data model

Deliberately simple, not the fully general multi-MCC-per-user shape
floated earlier and then cut:

```
users            1 row per Google identity (keyed by OAuth `sub`)
  └─ 1:1 ─→ mcc_connection   exactly one MCC per user, no more
                              (dev_token, oauth_refresh_token — both
                               encrypted at rest)
                   └─ 1:N ─→ accounts      one row per ad account under
                                            that MCC the user has chosen
                                            to expose
                                            (customer_id, display_name,
                                             slug, bearer_token, enabled)
```

**One user = one MCC, not "N cabinets per user."** An earlier version of
this plan had users connecting multiple MCCs ("cabinets"); cut for now to
keep the onboarding flow and the data model simple. Revisit only if a
real user actually needs to manage two unrelated MCCs through one login —
don't build for it speculatively.

**Per-account MCP address + bearer token**, not a shared endpoint with a
`customer_id` parameter the LLM picks per call. Rejected the
alias-parameter design (see "What already exists" below) specifically
because pinning the account at the connection level, not inside a
parameter the LLM chooses, structurally prevents one chat from touching
the wrong account — no way to mistype/hallucinate an id into the wrong
Ads account when the account isn't a parameter at all.

**URL shape doesn't need to be secret.** The bearer token (randomly
generated, shown once in the dashboard, checked via a plain DB lookup) is
the actual security boundary. A readable path
(`domain/mcp/<account-slug>`) is fine and better for debugging/support
than an obscured random path — don't bother making the URL itself
unguessable, that effort buys nothing once the bearer token is enforced.

## Auth on the MCP server itself: no JWT here either

FastMCP's `TokenVerifier` base class is not JWT-specific — confirmed by
reading the installed package (`fastmcp.server.auth.auth.TokenVerifier`,
and `providers/debug.py`'s `DebugTokenVerifier` which takes an arbitrary
`validate(token) -> bool` callable). Write a small custom `TokenVerifier`
whose `verify_token()` does a plain `SELECT` against the `accounts` table
by bearer token — no JWKS, no signature verification, no algorithm
choice, nothing to migrate later.

Inside any tool, `fastmcp.server.dependencies.get_access_token()` returns
whatever the verifier's `AccessToken` carried for this request (account
id, mcc connection id, whatever fields we attach) — **without changing
any of the ~100 existing tool signatures**, same pattern already used for
account aliasing (see below): one choke point, not a hundred files.

`sdk_client.py`'s current process-wide singleton (`get_sdk_client()`/
`set_sdk_client()`, resolved once at startup from `.env`) becomes
per-request resolution instead: look up the account → its MCC's
encrypted credentials → build (or pull from an in-memory cache keyed by
`mcc_connection_id`) a `GoogleAdsClient` for that specific request. This
is the one piece of `mcp-server/` that structurally has to change for
multi-tenancy; nothing else about the ~100 wrapped services changes.

## What already exists in `mcp-server/` and how it relates

- **`AccountRegistryStore`/`format_customer_id` alias resolution**
  (`src/services/review/account_registry_store.py`, 2026-09-06) — this is
  the **local, single-operator** mechanism: a JSON file, an alias passed
  as a parameter, resolved by the one human (or one Claude Code session)
  running the process locally. Still useful for exactly that — the user's
  own boo.ua + next-project juggling via Claude Code — but it is **not**
  the mechanism the hosted multi-tenant platform will use (that's the
  per-account bearer-token + DB-backed `TokenVerifier` design above,
  where the account is pinned at the connection, not passed as a
  parameter — see `mcp-server/docs/ACCOUNT_SWITCHING.md` for why that
  distinction matters). Both can coexist: alias registry for local/dev
  use of `main.py`, the new mechanism for the deployed multi-tenant HTTP
  entrypoint. Don't conflate them or try to unify them - they solve
  different problems (convenience for one trusted local operator vs.
  hard isolation between untrusted-of-each-other tenants).
- **`remote_main.py`** — today's read-only, single-tenant, static-bearer-
  token remote deployment. The multi-tenant HTTP entrypoint described
  here is a new, third entrypoint (alongside `main.py` and
  `remote_main.py`), not a modification of either — it needs write
  access (unlike `remote_main.py`) and per-request credential resolution
  (unlike both).

## OAuth verification for the `adwords` scope

Confirmed (not assumed) via Google's own scope lists: `adwords` is a
**sensitive** scope, not a **restricted** one — checked the actual
restricted-scopes list
([support.google.com/cloud/answer/13464325](https://support.google.com/cloud/answer/13464325)),
which only covers Gmail/Drive/Fit/Chat/Data Portability/Photos
Ambient/Health; Google Ads isn't on it. This matters a lot for how much
process weight to expect:

- **No CASA security assessment, no annual re-certification** — that's
  only for restricted scopes.
- **Sensitive-scope verification**: Google's own guidance puts it at
  ~3-5 business days. Requirements: a privacy policy hosted on a verified
  domain, a homepage, accurate branding (app name, logo, support email)
  on the consent screen.
- **Can (and should) submit early, in parallel with building** —
  verification reviews the consent screen/scope justification/privacy
  policy, not feature completeness. Don't block it on the rest of the
  build; the reverse is true — build the privacy policy + homepage pages
  first specifically so this can be in Google's queue while everything
  else gets built.
- **Until verified**: OAuth app in Testing mode caps at 100 manually-
  added test users and — already hit once in this project, see
  `mcp-server/TRACKER.md`'s 2026-08-27 (11) entry — refresh tokens expire
  after 7 days. Fine for building/testing with a handful of whitelisted
  testers; not fine for real onboarding.

## Naming

"g-ads-flexer" / "ads-flexer" was never meant to be the product name.
Candidates floated, not decided — none checked against a live registrar
(no tool access to real WHOIS/pricing; treat these as starting points to
verify on an actual registrar, not confirmed availability):

- **AdWire** — "wire your Ads account into your AI assistant." Short,
  literal.
- **AdsDock** — accounts "dock" into the platform.
- **Adnex** — ads + nexus/connection point. Short, brandable.
- **PlugAds** — literal "plug your account in," leans technical/direct.
- **AdSwitchboard** — evokes the multi-account-switching angle
  specifically; plain "Switchboard" has some existing dev-tool overlap,
  the "Ad" prefix avoids that.

Pick later, doesn't block any of the phases below — folder names
(`mcp-server/`, `web/`) were deliberately kept generic/stack-descriptive
rather than named after any candidate, specifically so naming can
resolve independently without another repo reshuffle.

## Phased plan

**Phase 1 — `mcp-server/` backend foundations (Python, this repo):**
- Postgres schema (`users`, `mcc_connections`, `accounts`) — agreed
  jointly with the `web/` side once that starts, since Next.js/Auth.js
  owns migrations; Python just needs read access to the agreed shape
- Custom `TokenVerifier` (DB lookup, no JWT)
- `sdk_client.py`: singleton → per-request resolution + cache
- New multi-tenant HTTP entrypoint (full read+write tool surface, unlike
  `remote_main.py`)
- Migrate `pending_changes.json`/`account_sheets.json` off local JSON
  files onto Postgres tables — required before this can run on Railway
  (ephemeral filesystem, and no longer a single trusted local operator)

**Phase 2 — `web/` minimal cabinet (Next.js, new repo/folder):**
- Auth.js + Google provider (login + `adwords` consent, one grant)
- Privacy policy + homepage pages — ship these **first**, specifically to
  unblock submitting for OAuth verification in parallel with the rest
- Dashboard: MCC info, account list (live via `list_accessible_customers`
  through the Python side, or directly), enable/disable per account,
  bearer-token generation + MCP address display
- Dev-token paste-in field + instructions

**Phase 3 — productionize:**
- Submit + track Google's sensitive-scope verification (starts as soon
  as Phase 2's privacy policy page is live, doesn't wait for the rest of
  Phase 3)
- Change-history view in the dashboard
- Token rotation/revocation UX
- Rate limiting / abuse protection now that this is internet-facing and
  multi-tenant, not one trusted local operator

## Open / not decided yet

- Exact Postgres column list and types — sketched above, not finalized;
  finalize together once `web/` (Auth.js + its DB adapter) actually
  starts, since its schema conventions constrain this too.
- Whether `list_accessible_customers` (showing the account picker) gets
  called from Next.js directly against Google's API, or proxied through
  the Python side — leaning direct-from-Next.js (it's a read-only Google
  API call, doesn't need the Python SDK), not decided.
- Product name (see above).
