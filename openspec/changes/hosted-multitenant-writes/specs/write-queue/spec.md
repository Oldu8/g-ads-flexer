## Purpose

No Google Ads write happens on the first call. Every `ads_write` tool call becomes a stored, previewed and, where Google allows it, validated change; only `apply_pending_change` executes it. One mechanism for all writes (decided 2026-09-23), replacing both the seven `propose_*` tools and the idea of a model-controlled `confirm` flag.

## ADDED Requirements

### Requirement: Writes are queued, not applied
When a tool whose registry `kind` is `ads_write` is called, the write-queue middleware SHALL run the tool with the queuing flag set in a contextvar; the interceptor SHALL set `validate_only = true` on every mutate request sent during that run. The middleware SHALL then store a `pending_changes` row (tool name, arguments, preview, validation outcome, `expires_at` = now + 24 h) for the pinned account and return `{queued: true, change_id, validation, preview, next}`, where `next` tells the agent to show the preview and call `apply_pending_change` only after the user approves.

#### Scenario: Budget change
- **WHEN** the agent calls `budget_update_campaign_budget` for a campaign
- **THEN** Google receives only a `validate_only` request, the budget is unchanged, a `pending` row exists, and the result carries its `change_id`

### Requirement: Nothing is sent that cannot be validated
While the queuing flag is set, the interceptor SHALL abort, without sending, any mutate RPC whose request has no `validate_only` field (e.g. `ApplyRecommendation`, `DismissRecommendation`). Non-mutate RPCs (reads a tool makes before writing) SHALL pass. The stored `validation` SHALL be `full` when every mutate was validated, `partial` when the tool stopped after at least one validated mutate (typically because a later step needed the real result of an earlier one), and `none` when no mutate could be validated. The preview returned to the agent SHALL state the outcome in words.

#### Scenario: Recommendation apply
- **WHEN** the agent calls `recommendation_apply_recommendation`
- **THEN** nothing is sent to Google, the change is queued with `validation: none`, and the preview says Google could not check it in advance

### Requirement: Invalid changes are not queued
If Google rejects a `validate_only` request, the middleware SHALL NOT create a row and SHALL return the error with any hint from the hint table.

#### Scenario: Budget below minimum
- **WHEN** validation fails because the amount is invalid
- **THEN** no row exists and the agent receives Google's error plus the hint

### Requirement: Applying is explicit, atomic and scoped
`apply_pending_change(change_id)` SHALL claim the row with a single `UPDATE … SET status = 'applying' WHERE id = … AND ad_account_id = <pinned> AND status = 'pending' AND expires_at > now()`; if nothing is claimed, it returns why (unknown, another account's, already decided, expired). It SHALL then call the stored tool with the stored arguments and the queuing flag off, store `result` or `error`, and set `applied` or `failed`. After a successful apply it SHALL write the fixes-log entry best-effort, recording a failure in `fixes_log_error` without turning a successful mutation into a failure (current behaviour, kept). `reject_pending_change` SHALL set `rejected`. Its description SHALL tell the agent to apply only after the user's explicit approval in the current conversation; this is guidance, not enforcement, as accepted in D6.

#### Scenario: Double apply
- **WHEN** two `apply_pending_change` calls for the same id arrive together
- **THEN** exactly one executes the write; the other returns "already decided"

#### Scenario: Another account's change
- **WHEN** tenant B calls `apply_pending_change` with an id created by tenant A
- **THEN** it returns "not found" and nothing executes

### Requirement: Previews are readable
The preview SHALL include the tool name and arguments. For the seven kinds the current `pending_change_service.py` formats (keyword lists, budget before/after, bid target, rule-based user list, user list removal, shared-set negatives, shared-criterion removal), the existing formatters SHALL be reused for the equivalent tools (`ad_group_criterion_add_keywords`, `budget_update_campaign_budget`, `campaign_update_campaign`, `user_list_create_rule_based_user_list`, `user_list_remove_user_list`, `shared_criterion_add_keywords_to_shared_set`, `shared_criterion_remove_shared_criterion`).

#### Scenario: Adding keywords
- **WHEN** `ad_group_criterion_add_keywords` is queued with 40 keywords
- **THEN** the preview lists the 40 keywords with match types, as `propose_add_keywords` does today

### Requirement: The queue lives only in Postgres
`snapshots/pending_changes.json`, `PendingChangeStore` and the seven `propose_*` tools SHALL be removed. `list_pending_changes` and `get_pending_change` SHALL read only the pinned account's rows. Rows past `expires_at` SHALL read as `expired`.

#### Scenario: Listing
- **WHEN** tenant A lists pending changes
- **THEN** only A's rows are returned, newest first, within the response envelope
