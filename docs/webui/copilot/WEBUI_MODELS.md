# WEBUI Models for Solid.js

Date: 2026-03-24
Scope: heuristic-metatrader5-bridge operator WebUI direction

## Product interpretation

This UI is an execution and supervision cockpit for a live MT5 bridge.
It is not a generic admin dashboard.

Primary mission:
- keep operators aware of terminal and account reality in seconds
- expose execution-critical blockers immediately (especially MT5 trading availability)
- supervise fast and thesis desks without pretending unimplemented control layers exist
- prepare route and component boundaries for future ownership, risk kernel, and multi-terminal runtime

## Implemented backend vs Planned backend

### Available now

- Core runtime bootstraps MT5, market state, account state, symbol specs, and symbol catalog.
- HTTP control plane provides read surfaces:
  - GET /status
  - GET /chart/{symbol}/{timeframe}
  - GET /specs and /specs/{symbol}
  - GET /account
  - GET /positions
  - GET /exposure
  - GET /catalog
  - POST /subscribe and /unsubscribe
  - GET /events (SSE)
- Connector supports execution and custody primitives:
  - send_execution_instruction
  - modify_position_levels
  - modify_order_levels
  - remove_order
  - close_position
  - find_open_position_id
- Fast desk runtime and execution bridge are present and wired to connector methods.
- SMC scanning and thesis analysis pipeline exists as analysis-first flow.

### Partially available now

- Order comment tagging is broker-sensitive. Certification reports show comment="" works while tagged comment can fail on current broker.
- trade_allowed gate is enforced before write actions, but terminal trade availability is not yet a first-class control-plane field in /status payload.
- SMC execution from thesis to MT5 is not complete as a full trader service.
- Runtime DB has useful operational evidence, but WebUI should use HTTP surfaces as authority and only treat DB-backed features as secondary telemetry.

### Not available yet

- OwnershipRegistry (formal position/order ownership lifecycle).
- RiskKernel global and per-desk governance with kill switch and budget orchestration.
- BridgeSupervisor multi-terminal orchestration and routing by terminal_id.
- AccountContextManager full account-switch orchestration with frozen context lifecycle.
- SmcTraderService and FastTraderService as explicit canonical services in planned architecture.
- execution_mode split (live vs paper) as first-class runtime mode separate from account_mode.

### UI behavior policy for gaps

- Any control requiring unavailable backend must render as one of:
  - Preview
  - Planned
  - Disabled
- Disabled controls must explain why and name the missing backend component.
- No simulated success states for non-implemented actions.

## Information architecture

### Level 1 areas

1. Runtime
2. Operations
3. Fast Desk
4. SMC Desk
5. Ownership
6. Risk Center
7. Terminal and Account
8. Execution Mode

### Level 2 panels by area

- Runtime:
  - startup and health timeline
  - connector and feed integrity
  - subscribed universe and chart workers
  - account snapshot and pending alerts
- Operations:
  - open positions grid
  - pending orders grid
  - execution activity stream
  - symbol watch focus panel
- Fast Desk:
  - signal and trigger lane
  - confidence and cooldown matrix
  - custody actions lane
  - fast trade log
- SMC Desk:
  - zone and structure panel
  - thesis queue and validation state
  - review scheduler panel
  - operation candidate list (analysis-first)
- Ownership:
  - ownership map and adoption queue
  - reassignment controls (preview)
  - audit trail lane
- Risk Center:
  - global profile and desk profile cards (preview)
  - exposure and budget map
  - kill switch concept panel (preview)
- Terminal and Account:
  - terminal identity
  - broker and account context
  - AutoTrading status placeholder and warning
  - account switch safety modal hooks
- Execution Mode:
  - account_mode observed now
  - execution_mode planned controls
  - paper simulation roadmap state

## Navigation model

Use a route-based Solid.js app with two shells:

- Primary shell (desktop):
  - left rail for area switching
  - top strip for critical state badges and clock
  - center workspace with resizable panel grid
- Compact shell (mobile degradation):
  - bottom tab for area switching
  - stacked cards replacing dense grids
  - read-first behavior for high-risk controls

Proposed routes:
- /runtime
- /operations
- /desk/fast
- /desk/smc
- /ownership
- /risk
- /terminal
- /execution-mode

## Screen inventory

1. Launch and Runtime Overview
2. Operations Console
3. Fast Desk View
4. SMC Desk View
5. Ownership and Adoption View
6. Risk Center
7. Terminal and Account Context
8. Paper vs Live Execution View

## User roles

1. Operator (primary)
- supervises live runtime
- monitors exposure and execution flow
- performs safe operational actions

2. Desk Supervisor
- reviews Fast and SMC desk behavior
- approves or rejects manual interventions

3. Risk Supervisor (future phase)
- manages global and desk risk policies
- controls kill switch and overrides

4. Platform Engineer
- inspects runtime health and connector behavior
- performs terminal/account recovery procedures

## Component inventory

Cross-screen shared components:
- StatusBadge with severity scale (ok, warn, critical, planned)
- HealthTimeline
- SymbolPill and TimeframePill
- DataGrid (virtualized)
- EventStreamPanel
- AlertStack and RecoveryCallout
- PreviewBlock (planned capability wrapper)
- ActionGuardButton (requires preconditions)
- RouteSkeleton and ErrorSurface

Domain components:
- RuntimeHealthBoard
- ConnectorStatePanel
- FeedIntegrityMatrix
- AccountExposureHeatmap
- PositionGrid
- PendingOrderGrid
- FastSignalTape
- FastCustodyLog
- SmcZoneMap
- ThesisValidationBoard
- OwnershipMap (preview-enabled)
- RiskBudgetBoard (preview-enabled)
- TerminalContextCard
- ExecutionModeBoard

## API to screen mapping

### Current control-plane APIs usable now

| Screen | Endpoint | Data usage |
|---|---|---|
| Runtime | GET /status | overall health, universes, workers, account summary, exposure, open positions and orders |
| Runtime | GET /events | near-real-time state stream for top strip and incident feed |
| Runtime | GET /catalog | broker symbols and catalog status |
| Runtime | GET /specs | symbol specification completeness checks |
| Operations | GET /positions | open positions and pending orders grids |
| Operations | GET /exposure | exposure map and per-symbol concentration |
| Operations | GET /account | account summary and recent history blocks |
| Fast Desk | GET /events + GET /status | worker and runtime-derived fast signals summary where available |
| SMC Desk | GET /status + GET /chart/{symbol}/{tf} | thesis context inputs and zone-friendly chart context |
| Terminal | GET /status + GET /account | broker identity, account mode, terminal-linked runtime context |
| All screens | POST /subscribe and /unsubscribe | symbol universe management |

### Runtime DB facts visible today but not primary UI contract

- fast_desk_signals and fast_desk_trade_log can enrich audit/history widgets.
- smc_zones and smc_thesis_cache may back delayed analytics views.
- Do not make UI correctness depend on direct SQLite reads.

### API surfaces recommended next

- GET /terminal_state -> include terminal trade_allowed and auth degradation flags.
- GET /desks/fast/state -> explicit fast signal and custody status shape.
- GET /desks/smc/state -> explicit thesis and candidate state shape.
- GET /ownership/state and POST /ownership/reassign.
- GET /risk/state and POST /risk/override and POST /risk/kill-switch.
- GET /execution-mode and POST /execution-mode.

### Mock state needed until backend phases exist

- ownership matrices and reassignment actions
- risk budgets and kill-switch controls
- execution_mode toggle and paper simulation state
- account switch disruption history panel

## Startup flow

1. App boot
- route to /runtime
- fetch GET /status and GET /catalog in parallel
- start SSE subscription GET /events

2. Runtime validation gate
- if status is not up, lock action controls and show recovery panel
- if account summary missing, keep read-only skeleton with retry

3. Symbol context bootstrap
- load /specs and first chart context for default symbols/timeframes
- show stale markers until all required symbol specs arrive

4. Desk hydration
- render Fast and SMC routes with state gate badges:
  - Live
  - Partial
  - Preview

5. Session continuity
- keep last successful state cache in-memory only
- when SSE drops, degrade to polling on /status until stream restores

## Loading, error, and empty states

Loading:
- skeleton rows for grids
- shimmer only on first load; use subtle pulse for refresh
- explicit timestamp of last successful update

Error:
- sticky top incident banner for critical runtime failures
- local panel errors do not blank entire page
- connector write precondition failures open recovery callout

Empty:
- positions/orders empty state with explanation and current exposure 0
- no subscribed symbols state with immediate subscribe action
- SMC/Ownership/Risk empty states explicitly marked Planned when backend missing

## Representation of live vs planned capabilities

Use a strict capability badge model on every actionable panel:

- Live: backend exists and endpoint/action path is available now.
- Partial: backend exists with operational caveats.
- Planned: backend phase defined but unavailable.

Mandatory examples:
- Fast desk open/close/modify controls: Live, but guarded by runtime health and terminal trading availability.
- SMC order placement: Planned until SmcTraderService is implemented.
- Ownership reassignment controls: Planned until OwnershipRegistry exists.
- Risk kill switch controls: Planned until RiskKernel exists.
- execution_mode switch: Planned until live/paper split is first-class.

## Data visualization model for operations

- Terminals and brokers:
  - terminal context card with installation and broker server identity
  - session risk warning block for account probing and auth failures
- Accounts:
  - account summary strip with drawdown, margin level, free margin, leverage
- Desks:
  - split color identity (Fast vs SMC) across tabs and rows
- Positions and orders:
  - ownership column reserved now, marked unknown/inferred until registry exists
  - side, volume, open price, current price, SL/TP, floating PnL, age, source comments
- Exposure:
  - per-symbol net/gross bars and margin share heat scale
- Feed health:
  - worker-level freshness matrix by symbol and timeframe

## Solid.js implementation direction

Architecture:
- SolidStart route app
- data layer with resource + store per route domain
- central connection service for SSE and fallback polling
- domain stores:
  - runtimeStore
  - operationsStore
  - fastDeskStore
  - smcDeskStore
  - terminalStore
  - plannedStore (ownership/risk/execution mode placeholders)

State boundaries:
- global: runtime health, connector status, selected account context
- route-local: dense grid filters, selected symbol/timeframe, panel layout state
- ephemeral: modal state, hover inspection state

Real-time strategy:
- SSE as primary for /status stream
- polling fallback at 1-2s when SSE disconnected
- drop stale events based on event timestamp and sequence guard

## Future architecture readiness hooks

- terminal_id-aware route params prepared now: /runtime/:terminalId
- account context switch event bus in UI store
- ownership/risk feature flags in config-driven capability registry
- control action wrappers that can switch from disabled preview to live endpoint without redesign

## First implementation backlog (frontend)

1. Build Runtime and Operations routes with current control-plane data only.
2. Build Fast and SMC views as hybrid: live observability plus planned-action placeholders.
3. Add terminal and account warning surfaces for account probe disruption and trade availability uncertainty.
4. Add capability registry and badge system to enforce honest live vs planned rendering.
5. Add feature-flag scaffolding for Ownership, Risk, and execution_mode routes.
