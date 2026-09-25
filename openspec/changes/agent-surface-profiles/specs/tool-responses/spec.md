## Purpose

Keep every tool result small enough to leave room for reasoning, make truncation impossible to mistake for absence, and turn errors into instructions the agent can act on instead of retry loops.

## ADDED Requirements

### Requirement: List results use a bounded envelope
Every `read` tool in the `manager` profile that returns a list SHALL return `{"items": [...], "returned": N, "truncated": bool}` and, when truncated, a `"warning"` string. The cap SHALL default to 500 rows and SHALL be configurable with `GOOGLE_ADS_MCP_ROW_CAP`. Truncation SHALL be detected by fetching `cap + 1` rows. The warning SHALL say that the list is incomplete, that an item missing from it is not evidence that the item does not exist, and how to narrow the query (`WHERE`, `ORDER BY ... LIMIT`).

#### Scenario: Result under the cap
- **WHEN** a query yields 120 rows
- **THEN** the tool returns 120 items, `returned: 120`, `truncated: false` and no warning

#### Scenario: Result over the cap
- **WHEN** a query yields 3,000 rows
- **THEN** the tool returns 500 items, `returned: 500`, `truncated: true` and the warning
- **AND** iteration stops after row 501, so the remaining pages are not fetched

### Requirement: GAQL gets a LIMIT
`search_execute_query` SHALL append `LIMIT <cap + 1>` to a query that has no `LIMIT` clause, and SHALL leave an existing `LIMIT` unchanged (the envelope still truncates at the cap).

#### Scenario: Query without LIMIT
- **WHEN** the agent sends `SELECT campaign.id FROM campaign`
- **THEN** the request sent to Google ends with `LIMIT 501`

#### Scenario: Query with its own LIMIT
- **WHEN** the agent sends a query ending in `LIMIT 50`
- **THEN** the query is sent unchanged

### Requirement: Tools do not advertise parameters that do nothing
A tool SHALL NOT expose a parameter that is not applied to the request. `google_ads_search_google_ads` SHALL drop `page_size`: it is currently accepted, documented as "max 10000" and never assigned, and v25 rejects requests that set it.

#### Scenario: Schema after the fix
- **WHEN** the tool schema of `google_ads_search_google_ads` is listed
- **THEN** it has no `page_size` property

### Requirement: Errors carry a next step
`format_ads_error` SHALL append a `hint` when the Google Ads error matches an entry in a hint table kept in one module. The table SHALL be seeded from failures recorded in `TRACKER.md` and grown from real logs, not copied from another project. Transport-level failures SHALL map to fixed, readable messages: an expired or revoked refresh token (`invalid_grant`) → "the Google connection for this account is no longer valid; reconnect it"; `DEADLINE_EXCEEDED` / `UNAVAILABLE` → "Google Ads API did not respond; retry once, then narrow the request"; `RESOURCE_EXHAUSTED` → the quota message used by quota accounting.

#### Scenario: Known GAQL mistake
- **WHEN** a query fails with an error whose text matches a hint-table entry
- **THEN** the returned error contains the original message, the `request_id` and the hint

#### Scenario: Revoked grant
- **WHEN** the SDK raises a refresh error with `invalid_grant`
- **THEN** the tool returns the reconnect message instead of a stack trace
