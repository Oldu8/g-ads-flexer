## Purpose

How a hosted tenant's Google Ads access is stored, resolved per request, and pinned to exactly one ad account, now that the Google Ads API has no developer token and access level lives on the platform's Cloud project.

## ADDED Requirements

### Requirement: No per-tenant developer token
The system SHALL NOT store, request, or display a developer token for any tenant. The only developer-token value in the codebase SHALL be a single placeholder constant passed to the Google Ads SDK client builder solely to satisfy SDK config validation, and it SHALL be removed once the SDK no longer requires it.

#### Scenario: Building a client for a tenant
- **WHEN** the server builds a `GoogleAdsClient` for an incoming request
- **THEN** it uses the platform OAuth client id/secret, the tenant connection's refresh token, and the account's `login_customer_id`
- **AND** the developer-token value comes from the placeholder constant, never from the database or a per-tenant setting

#### Scenario: Onboarding a tenant
- **WHEN** a user connects Google Ads in the dashboard
- **THEN** the flow consists of one Google OAuth grant with the `adwords` scope and account selection
- **AND** no developer-token or MCC id input exists anywhere in the flow

### Requirement: One OAuth grant reaches N accounts
A `google_connections` row SHALL represent one OAuth grant from one Google identity, and SHALL be able to back any number of `accounts` rows. Each `accounts` row SHALL store the pair `(customer_id, login_customer_id)` where `login_customer_id` is the manager through which access was discovered, or NULL for direct access.

#### Scenario: Discovery through a manager
- **WHEN** `list_accessible_customers` returns a manager account for the grant
- **THEN** the system walks `customer_client` under that manager and offers its non-manager, enabled descendants
- **AND** any chosen descendant is stored with `login_customer_id` = that manager

#### Scenario: Direct access
- **WHEN** `list_accessible_customers` returns a non-manager account directly
- **THEN** a chosen row for it is stored with `login_customer_id` = NULL

### Requirement: Account pinned at the connection, not chosen by the model
On the hosted entrypoint, the bearer token SHALL identify exactly one `accounts` row, and every Google Ads API call made while serving that request SHALL target that row's `customer_id` with its stored `login_customer_id`, regardless of any `customer_id` value supplied in the tool call.

#### Scenario: Tool call names a different customer id
- **WHEN** a tool is invoked with a `customer_id` that differs from the pinned account
- **THEN** the call is rejected with a clear error (or the id is overridden to the pinned account, if the tool is read-only) and no request reaches the other account

#### Scenario: Token lookup
- **WHEN** a request arrives with a bearer token
- **THEN** the verifier looks up `accounts` by token hash and returns `account_id`, `google_connection_id`, `customer_id`, `login_customer_id`, `tool_profile`
- **AND** a missing, disabled, or revoked account yields an authentication failure without touching Google
