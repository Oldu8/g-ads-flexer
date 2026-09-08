# campaign-draft-management Specification

## Purpose
Covers how campaign drafts are validated and promoted, including surfacing async errors so a draft's readiness to promote can be trusted.

## Requirements

### Requirement: Async-error iteration failures are observable
When listing async errors for a campaign draft, the system SHALL distinguish between "the draft has zero async errors" and "the system failed to determine whether the draft has async errors." A failure while iterating the async-error response SHALL be logged and SHALL NOT be silently reported as zero errors without any trace of the failure.

#### Scenario: Async-error page iteration succeeds
- **WHEN** `list_campaign_draft_async_errors` iterates the API response without error
- **THEN** it returns the collected list of async errors
- **AND** it logs the count found

#### Scenario: Async-error page iteration fails partway through
- **WHEN** iterating the async-error response raises an exception
- **THEN** the system logs a warning describing the exception
- **AND** it still returns the async errors collected before the failure (an empty list if none were collected yet), rather than raising and aborting the whole call
