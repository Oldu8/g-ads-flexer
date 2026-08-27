# Onboarding a new client

**Model: one deployment per client, each with its own Google Ads API
credentials.** Explicitly not a shared-MCC model — agencies run their own
MCCs and won't grant an external one access, and we don't want to hold
those permissions either. Each client goes through their own Google Ads API
application; the only thing that can reasonably be shared across clients is
the Google Sheets service account (see step 3), and even that can be split
per-client later if you want tighter blast-radius isolation.

This means most of the setup below repeats for every new client — there
isn't a one-time "agency setup" the way a shared-MCC model would have had.
The one thing worth doing once is deciding your Sheets service-account
strategy (step 3) so you're not re-deciding it per client.

## Per-client checklist

### 1. Client applies for their own Google Ads API access

This is the slow part — it's a Google review, not something either of you
can speed up:

- Client (or you, acting on their account) applies for a **developer
  token** on their own MCC (Google Ads UI → Tools & Settings → API Center).
  Test-account-only access is instant; **standard access** (needed to touch
  real, non-test accounts) requires Google's review — this is the wait.
- Create an **OAuth client** (Google Cloud Console → APIs & Services →
  Credentials) under a Google Cloud project — the client's own project, or
  one of yours dedicated to this client (either works; it's just where the
  OAuth client id/secret live, it does not grant you access to their Ads
  account by itself).
- Generate a **refresh token** once, authorizing whichever Google account
  will act as the API user against the client's Ads account (their own
  account, or an account they've granted Standard/Admin access to via
  Google Ads UI → Admin → Access and security → Users).
- End state: `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`,
  `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`,
  `GOOGLE_ADS_LOGIN_CUSTOMER_ID` — all specific to this one client, none of
  them reused from another client's setup.

### 2. Client's tracking spreadsheet

- Client provides (or you create from a template) their Google Sheet for
  the fixes log.
- They share it with your Sheets **service account's** email (Editor
  access) — see step 3 for where that email comes from.

### 3. Google Sheets service account — decide once, reuse the decision

Unlike step 1, this part genuinely can be a "decide once" thing, because
sharing one spreadsheet with a service account is a much narrower grant of
trust than linking a whole Ads account — it doesn't touch the client's Ads
data or MCC at all, so there's no version of the MCC objection here.
Pick one:

- **One shared service account for all clients (simpler, recommended to
  start):** create it once (Google Cloud Console → enable Sheets API →
  Service Account → download JSON key), reuse the same email for every
  client's sheet-share in step 2.
- **One service account per client (more isolation, more setup):** repeat
  the creation above per client. Only worth it if you specifically want a
  leaked key to only expose one client's sheet instead of all of them —
  can also be automated later via the Cloud IAM API if you outgrow doing it
  by hand.

Either way, fill in `GOOGLE_SHEETS_CREDENTIALS_FILE` (path to that client's
key — or the shared key, if you went with option 1) and
`GOOGLE_SHEETS_SPREADSHEET_ID` (the id segment of their sheet's URL,
between `/d/` and `/edit`) in this client's `.env`.

### 4. Stand up this client's deployment

One running instance per client — its own `.env` (all of steps 1-3), its
own process/deployment (local `main.py`, or its own hosted instance if you
go remote later). Nothing in the current codebase supports serving multiple
clients from one running process (`GOOGLE_ADS_LOGIN_CUSTOMER_ID` and
`GOOGLE_SHEETS_SPREADSHEET_ID` are both read once at startup, not passed
per call) — that's a deliberate "not yet" per the 2026-08-27 TRACKER.md
decision to validate the model with one real client before building
multi-tenant infrastructure (shared credential storage, a login/admin
panel, per-account MCP tokens, billing) around it.

### 5. First-run check

Confirm `check_sdk_client_status` reports ready, then either `log_fix` a
trivial test row or `list_fixes` against an empty sheet, before doing
anything for real against their live account.

## What's still manual / not automated

- The developer-token application and OAuth consent are Google's own flows
  — nothing here can speed up or automate them.
- Service account key files are secrets - treat them like any other
  credential in `.env` (never commit; `.gitignore` already covers `.env`).
- If a client revokes their sheet share or their Ads account access, tools
  fail loudly (`FixesLogSheetError` / a `GoogleAdsException` on auth)
  rather than silently — intentional, not a bug to route around.

## If/when this grows past one client

Revisit this doc once there's a real second paying client and the
single-tenant "one deployment per client" model is clearly the bottleneck
(not before - see the 2026-08-27 TRACKER.md entry for the reasoning). The
multi-tenant version would need: encrypted-at-rest storage for other
companies' developer tokens/OAuth secrets/refresh tokens (a real secrets
manager, not a database column), a login/admin panel for clients to submit
their own credentials, `sdk_client.py` reworked to resolve credentials
per-request instead of once at startup, and per-connected-account MCP
tokens tied to a billing/metering system. None of that is started.
