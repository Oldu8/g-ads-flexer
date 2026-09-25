## Purpose

The Basic quota (15,000 operations/day) belongs to the platform's Cloud project and is shared by every tenant, so one tenant can exhaust it for all. Count per account, cap before Google does, and make the numbers visible for the Standard-access decision.

## ADDED Requirements

### Requirement: Operations are counted at the transport
The interceptor SHALL count every RPC it lets through into `api_usage(ad_account_id, day)`, where `day` is the current date in America/Los_Angeles: a non-mutate RPC counts 1; a mutate RPC counts its number of operations. `validate_only` requests SHALL count the same as real ones (conservative until measured against the Cloud console).

#### Scenario: Mutate with several operations
- **WHEN** a tool sends one mutate request with 25 operations
- **THEN** the account's counter for today increases by 25

### Requirement: Caps are checked atomically before sending
Before sending, the interceptor SHALL increment the counter only if the result stays within the per-account daily cap (default 1,500), in one statement (`UPDATE … SET operations = operations + n WHERE … AND operations + n <= cap RETURNING …`, inserting the day's row if missing). A per-account per-minute cap (default 60) SHALL be enforced in process memory. Over either cap, the RPC SHALL NOT be sent and the tool SHALL return which cap was hit and when it resets. Caps SHALL be configurable by env without code changes.

#### Scenario: Daily cap reached
- **WHEN** an account has 1,495 operations today and a tool sends a mutate with 10 operations
- **THEN** nothing is sent, the counter stays 1,495, and the tool returns "daily API quota for this account is exhausted, resets at 00:00 PT"

### Requirement: Project-level guard
When today's total across all accounts reaches 90% of 15,000 (13,500), every further API-bound RPC for every account SHALL be refused with a readable message until the quota day resets, and the operator SHALL be alerted once per day (log line at ERROR, plus a POST to `OPERATOR_ALERT_WEBHOOK_URL` when set).

#### Scenario: Project near quota
- **WHEN** today's total reaches 13,500
- **THEN** API-bound calls are refused for all accounts and exactly one alert is sent that day

### Requirement: Usage is visible for the Standard-access decision
`scripts/usage_report.py` SHALL print today's total, the 7-day average from `api_usage_daily_totals`, and a flag when the average is ≥ 7,500 (50% of Basic).

#### Scenario: Operator checks the trigger
- **WHEN** the operator runs the report
- **THEN** it shows the 7-day average and whether it has crossed 7,500
