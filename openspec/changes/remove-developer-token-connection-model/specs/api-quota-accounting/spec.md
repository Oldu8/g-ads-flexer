## Purpose

The Google Ads API quota is now attached to the platform's Cloud project (Basic: 15,000 operations/day shared by all tenants), so a single tenant can exhaust the API for everyone. This capability counts operations per account and enforces caps before Google does.

## ADDED Requirements

### Requirement: Operations are counted per account per day
Every Google Ads API call made through the per-request client SHALL increment `api_usage(account_id, day)`. Mutate requests SHALL count each contained operation individually.

#### Scenario: Read call
- **WHEN** a tool issues one `GoogleAdsService.Search` request for an account
- **THEN** that account's counter for the current day (Google's quota day, Pacific Time) increases by 1

#### Scenario: Mutate call with several operations
- **WHEN** a tool issues one mutate request containing N operations
- **THEN** the counter increases by N

### Requirement: Per-account caps are enforced with a readable error
The system SHALL enforce a per-account daily cap and a per-minute burst cap (initial values 1,000/day and 30/min, configurable). A call over either cap SHALL return a tool-level message stating which cap was hit and when it resets, and SHALL NOT be sent to Google.

#### Scenario: Daily cap reached
- **WHEN** an account has used its daily cap
- **THEN** further tool calls for that account return "daily API quota for this account is exhausted, resets at 00:00 PT" and make no API request

### Requirement: Project-level guard
When total usage across all accounts reaches 90% of the project's daily quota, the system SHALL refuse further API-bound calls for all accounts with the same readable message and SHALL alert the operator.

#### Scenario: Project near quota
- **WHEN** the sum of today's counters reaches 13,500
- **THEN** every API-bound tool call is refused until the quota day resets
- **AND** an operator alert is emitted once

### Requirement: Usage is visible for the Standard-access decision
The system SHALL make a 7-day average of total daily operations available to the operator so the Standard access application can be started at the documented trigger (~50% of Basic sustained).

#### Scenario: Operator checks the trigger
- **WHEN** the operator runs the usage readout
- **THEN** it reports the 7-day average of total daily operations across all accounts and the current day's total
- **AND** it flags when the average is at or above 7,500
