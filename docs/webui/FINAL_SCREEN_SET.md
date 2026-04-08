# Final Screen Set

## Runtime Overview

- Purpose: establish whether the bridge is alive, fresh, connected, and safe enough to trust before any desk work starts.
- Questions answered:
  - Is the bridge healthy right now?
  - Is MT5 connected?
  - Is market data flowing?
  - Is the subscribed runtime stable?
- Widgets:
  - global status strip
  - freshness and heartbeat card
  - feed/subscription summary
  - account headline strip
  - top alerts rail
- Required data:
  - `/status`
  - `/events`
  - `/account`
  - `/exposure`
  - `/catalog`
- Backend status:
  - mostly live
  - alerts are partly derived
- Future hooks:
  - supervisor diagnostics
  - terminal-scoped runtime health
  - desk service status

## Operations Console

- Purpose: provide the main live supervision surface for positions, exposure, recent broker activity, and symbol inspection.
- Questions answered:
  - What is currently open?
  - Where is exposure concentrated?
  - What changed recently at the broker level?
  - Which symbol needs inspection now?
- Widgets:
  - positions grid
  - exposure matrix
  - recent deals panel
  - recent orders panel
  - symbol watchlist
  - quick chart launch
- Required data:
  - `/positions`
  - `/exposure`
  - `/account`
  - `/events`
  - `/chart/{symbol}/{timeframe}`
- Backend status:
  - live for core supervision
  - watchlist quality partly derived
- Future hooks:
  - richer watch telemetry
  - terminal-scoped operations resources
  - action handoff to desk modules

## Fast Desk

- Purpose: focus on execution-centric symbol context and position awareness for fast trading workflows.
- Questions answered:
  - Is this symbol operationally ready?
  - What open position or order context already exists?
  - What would the future action path look like?
- Widgets:
  - instrument focus header
  - position/order context panels
  - spec summary
  - linked chart panel
  - disabled or preview action lane
- Required data:
  - `/positions`
  - `/account`
  - `/exposure`
  - `/chart/{symbol}/{timeframe}`
  - `/specs/{symbol}`
- Backend status:
  - live for read context
  - not live for HTTP execution actions
- Future hooks:
  - FastTraderService state
  - open/close/modify/remove endpoints
  - explicit trading permission and execution readiness

## SMC Desk

- Purpose: present structure/thesis-oriented decision support without pretending SMC backend semantics already exist in the control plane.
- Questions answered:
  - What live market context exists for this symbol?
  - Where would thesis, zones, and candidates appear once exposed?
  - What should the operator inspect before future SMC actions?
- Widgets:
  - thesis summary rail
  - zone/state board
  - candidate stack
  - chart context panel
  - preview execution/handoff area
- Required data:
  - `/chart/{symbol}/{timeframe}`
  - `/positions`
  - `/account`
- Backend status:
  - mostly preview with selective live context
- Future hooks:
  - thesis state
  - zone inventory
  - candidate lists
  - execution handoff endpoints

## Ownership

- Purpose: reserve the governance surface for account, terminal, and strategy ownership without inventing current authority models.
- Questions answered:
  - Which future ownership entities will matter?
  - Where would conflicts and adoption state be surfaced?
  - What is not yet enforceable from current backend?
- Widgets:
  - ownership explainer
  - preview ownership table
  - preview conflict queue
  - capability-state badges
- Required data:
  - none as first-class live ownership resources today
  - optional contextual account metadata from `/account`
- Backend status:
  - planned or preview only
- Future hooks:
  - OwnershipRegistry
  - adoption/conflict actions
  - terminal/account ownership state

## Risk Center

- Purpose: centralize exposure, margin, drawdown, and derived risk warnings, while reserving space for future risk governance controls.
- Questions answered:
  - Is the account approaching unsafe conditions?
  - Which symbols consume margin and concentration?
  - Which risk capabilities are still future-state?
- Widgets:
  - margin and drawdown board
  - exposure concentration table
  - used-margin-share view
  - derived warning queue
  - preview risk governance panel
- Required data:
  - `/account`
  - `/exposure`
  - `/positions`
- Backend status:
  - live for state inspection
  - preview for governance/actions
- Future hooks:
  - RiskKernel
  - limits and killswitches
  - terminal-scoped risk policy APIs

## Terminal / Account Context

- Purpose: expose broker/account facts and instrument specs cleanly, without mixing them with governance abstractions.
- Questions answered:
  - Which account am I connected to?
  - What is the current leverage, margin, and drawdown context?
  - What recent broker-side actions happened?
  - What are the execution-relevant specs for a symbol?
- Widgets:
  - account identity card
  - account metrics board
  - recent broker activity panels
  - symbol spec explorer
  - caution notes
- Required data:
  - `/account`
  - `/specs`
  - `/specs/{symbol}`
  - `/catalog`
- Backend status:
  - live
  - trading permission remains unknown via current API
- Future hooks:
  - terminal identity registry
  - explicit trade permission
  - multi-terminal metadata

## Live vs Paper

- Purpose: define where environment or execution mode control will live, while being explicit that current API does not expose that control.
- Questions answered:
  - What does the product mean by Live versus Paper?
  - Is the current backend exposing that mode explicitly?
  - What future switching workflow should the UI reserve?
- Widgets:
  - mode model explainer
  - current state badge as `Unknown` or `Preview`
  - preview switch workflow
  - operator warnings
- Required data:
  - none reliable today beyond contextual account facts
- Backend status:
  - planned
- Future hooks:
  - explicit execution-mode API
  - safe switching and certification flow

## Alerts / Events

- Purpose: collect actionable alerts, derived state changes, and broker activity without pretending the backend already exposes a durable event ledger.
- Questions answered:
  - What needs attention now?
  - What changed recently in runtime or account state?
  - Which changes are live facts versus UI-derived interpretations?
- Widgets:
  - critical alerts queue
  - warnings queue
  - broker activity timeline
  - derived state-change list
  - preview audit-history panel
- Required data:
  - `/events`
  - `/account`
  - derived signals from `/status`, `/positions`, and `/exposure`
- Backend status:
  - partial
  - current `/events` is a live-state stream, not a durable event log
- Future hooks:
  - certified event history
  - alert acknowledgements
  - audit exports
