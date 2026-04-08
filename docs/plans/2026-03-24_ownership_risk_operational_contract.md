# Ownership + Risk Operational Contract

Date: 2026-03-24

## Scope closed in this phase

This document captures the backend contract delivered for:

1. `OwnershipRegistry` and inherited operation adoption
2. `RiskKernel` global + desk (fast/smc)
3. Minimal control-plane API for ownership/risk
4. Runtime integration hooks so current runtime actively uses both

Out of scope (intentionally unchanged):

- `FastTraderService` full rewrite
- `SmcTraderService`
- `BridgeSupervisor`
- `paper mode`
- WebUI workflows

## Ownership contract

Partition key for all ownership rows:

- `broker_server`
- `account_login`

Main ownership state:

- `desk_owner`: `fast | smc | unassigned`
- `ownership_status`: `fast_owned | smc_owned | inherited_fast | unassigned`
- `lifecycle_status`: `active | closed | cancelled | filled`
- `reevaluation_required`: persisted bool

Persistence tables:

- `operation_ownership`
- `operation_ownership_events`

Runtime reconciliation policy:

1. On each account refresh, current MT5 `positions` and `orders` are reconciled.
2. Missing ownership rows for live cache operations are auto-adopted as `inherited_fast` (if `RISK_ADOPT_FOREIGN_POSITIONS=true`).
3. Live rows that disappear from cache are transitioned:
   - position -> `closed`
   - order -> `cancelled` or `filled` (when runtime evidence indicates execution)
4. Rows are not deleted immediately; retention purge uses `OWNERSHIP_HISTORY_RETENTION_DAYS`.

Manual reassignment:

- API supports reassignment to `fast` or `smc`
- supports `reevaluation_required=true|false`
- persists event with reason and timestamp

## Risk contract

Persistence tables:

- `risk_profile_state`
- `risk_budget_state`
- `risk_events_log`

Profiles:

- `1=low`, `2=medium`, `3=high`, `4=extreme`
- active profiles: `global`, `fast`, `smc`

Allocator policy:

- `score_fast = weight_fast * profile_factor(profile_fast)`
- `score_smc = weight_smc * profile_factor(profile_smc)`
- `share = score / (score_fast + score_smc)`
- factors: `{1:0.6, 2:1.0, 3:1.5, 4:2.0}`

This guarantees that increasing one desk profile/weight reduces available budget for the other desk.

Risk gates evaluate new entries against:

- drawdown
- max open positions (global and desk budget)
- max positions per symbol
- max pending orders (global and desk budget)
- max gross exposure
- kill switch

Kill switch state:

- `state`: `armed | tripped`
- `reason`
- `tripped_at`
- `manual_override`

Kill switch behavior:

- blocks new entries
- does not block defensive actions (`close_position`, `reduce_position`, `remove_order`, level modifications, trailing)

## Control-plane API contract

Ownership:

- `GET /ownership`
- `GET /ownership/open`
- `GET /ownership/history`
- `POST /ownership/reassign`

Risk:

- `GET /risk/status`
- `GET /risk/limits`
- `GET /risk/profile`
- `PUT /risk/profile`
- `POST /risk/kill-switch/trip`
- `POST /risk/kill-switch/reset`

No direct DB contract is exposed externally.

## Runtime integration points

- `CoreRuntimeService.bootstrap()` initializes `OwnershipRegistry` and `RiskKernel`.
- `CoreRuntimeService._refresh_account_state()` triggers ownership reconcile + risk usage refresh.
- `build_live_state()` now includes ownership/risk state.
- Fast desk worker consults `RiskKernel` before opening entries.
- Successful fast openings are registered as `fast_owned` ownership rows.

## Environment surface

Minimum env variables used by this phase:

- `RISK_PROFILE_GLOBAL`
- `RISK_PROFILE_FAST`
- `RISK_PROFILE_SMC`
- `RISK_MAX_DRAWDOWN_PCT`
- `RISK_MAX_RISK_PER_TRADE_PCT`
- `RISK_MAX_POSITIONS_TOTAL`
- `RISK_MAX_POSITIONS_PER_SYMBOL`
- `RISK_MAX_PENDING_ORDERS_TOTAL`
- `RISK_MAX_GROSS_EXPOSURE`
- `RISK_KILL_SWITCH_ENABLED`
- `RISK_ADOPT_FOREIGN_POSITIONS`
- `OWNERSHIP_HISTORY_RETENTION_DAYS`
- `RISK_FAST_BUDGET_WEIGHT`
- `RISK_SMC_BUDGET_WEIGHT`
