# WEBUI Models for Solid.js

Date: 2026-03-24  
Repository: `heuristic-metatrader5-bridge`  
Scope: implementation-facing UI models for `docs/webui/codex`

## Product interpretation

This frontend is an operator control surface for a live MT5 bridge.

It must behave like:
- an execution cockpit
- a market and account supervision console
- a desk operations board for Fast and SMC workflows

It must not behave like:
- a generic SaaS admin panel
- a broker marketing page
- an AI-themed dashboard with fake controls

## Implemented backend vs Planned backend

### Available now (Live)

- Control plane API is the only authorized external interface.
- Core runtime is live with MT5 connectivity, market state, account state, symbol specs, and subscriptions.
- `GET /status` exposes health, broker identity, universes, chart workers, feed status, account summary, open positions/orders, exposure state, and runtime metrics.
- `GET /events` provides SSE snapshots for real-time UI updates.
- Operational endpoints exist and are usable now:
  - `GET /chart/{symbol}/{timeframe}`
  - `GET /specs`, `GET /specs/{symbol}`
  - `GET /account`
  - `GET /positions`
  - `GET /exposure`
  - `GET /catalog`
  - `POST /subscribe`, `POST /unsubscribe`
- Connector execution surface is closed in code (`0.2.1`):
  - `send_execution_instruction`
  - `modify_position_levels`
  - `modify_order_levels`
  - `remove_order`
  - `close_position`
  - `find_open_position_id`
- Fast desk runtime exists and is wired to connector execution/custody methods.
- SMC scanner + analyst + heuristic validator + optional LLM validator exist.

### Partially available now (Partial)

- Broker comment behavior is constrained: live certification confirms reliable execution with `comment=""`, while populated comments can fail on current broker.
- `trade_allowed` is enforced in connector preflight, but no dedicated control-plane field currently exposes terminal trading availability as a first-class UI status.
- SMC currently provides analysis/thesis generation, not full thesis-to-order trading service.
- Fast/SMC detailed internal telemetry exists in runtime DB tables, but not as first-class HTTP endpoints yet.

### Not available yet (Planned)

- `OwnershipRegistry` and operation assignment lifecycle.
- `RiskKernel` (global + per desk), budget allocator, kill switch APIs.
- `FastTraderService` and `SmcTraderService` as canonical planned services.
- `BridgeSupervisor` and multi-terminal routing by `terminal_id`.
- Formal `execution_mode = live | paper` API split (separate from `account_mode`).
- Account switch orchestration with non-disruptive safeguards and explicit control-plane support.

### UI capability labels (mandatory)

Every interactive panel must carry one capability badge:

- `Live`: backed by API/action path today.
- `Partial`: available with known constraints.
- `Planned`: backend component not implemented.
- `Preview`: design/interaction shown, write controls disabled.

No panel may imply `Live` if the backend path is still planned.

## Information architecture

Top-level domains:

1. Runtime
2. Operations
3. Fast Desk
4. SMC Desk
5. Ownership and Adoption
6. Risk Center
7. Terminal and Account Context
8. Paper vs Live Execution

## Navigation model

Primary layout (desktop):
- left rail: route navigation and desk identity
- top strip: global status, last update, critical incident markers
- central workspace: resizable panel grid

Compact layout (mobile):
- bottom tab bar for domain switching
- single-column panel stack
- read-first behavior for high-risk actions

Route map (Solid.js):
- `/runtime`
- `/operations`
- `/desk/fast`
- `/desk/smc`
- `/ownership`
- `/risk`
- `/terminal`
- `/execution-mode`

Future-ready route convention:
- `/:terminalId/runtime` etc. once `BridgeSupervisor` exists

## Screen inventory

1. Launch / Runtime Overview
2. Operations Console
3. Fast Desk View
4. SMC Desk View
5. Ownership and Adoption View
6. Risk Center
7. Terminal and Account Context View
8. Paper vs Live Execution View

## User roles

1. Operator (primary)
- monitors runtime and execution safety
- supervises positions/orders/exposure

2. Desk Supervisor
- supervises Fast and SMC desk behavior
- reviews thesis and custody decisions

3. Risk Supervisor (planned phase)
- manages risk profiles, budgets, kill switches

4. Platform Engineer
- handles terminal/account disruptions and runtime recovery

## Component inventory

Shared core components:
- `CapabilityBadge`
- `StatusStrip`
- `AlertStack`
- `DataGridVirtual`
- `EventStreamPanel`
- `PanelShell` (header, status, actions, body)
- `RouteSkeleton`, `PanelErrorState`, `PanelEmptyState`
- `PreviewGuard` (locks planned controls)

Domain components:
- `RuntimeHealthBoard`
- `ChartWorkerMatrix`
- `AccountSnapshot`
- `ExposureHeatmap`
- `PositionGrid`
- `PendingOrderGrid`
- `FastSignalLane` (initially partial/preview)
- `FastCustodyTimeline` (initially partial/preview)
- `SmcZoneMap` (initially preview unless API added)
- `ThesisBoard` (initially preview unless API added)
- `OwnershipMatrix` (preview)
- `RiskBudgetBoard` (preview)
- `TerminalContextCard`
- `ExecutionModeComparator`

## API to screen mapping (current control-plane reality)

| Endpoint | Current fields used | Screens |
|---|---|---|
| `GET /status` | `health`, `broker_identity`, `universes`, `chart_workers`, `feed_status`, `account_summary`, `exposure_state`, `open_positions`, `open_orders`, `runtime_metrics`, `indicator_enrichment` | Runtime, Operations, Fast, SMC, Terminal |
| `GET /events` | SSE snapshots of live state | Runtime, Operations, Fast, Terminal |
| `GET /positions` | `positions`, `orders` | Operations, Fast (custody context) |
| `GET /exposure` | aggregate exposure state | Operations, Risk (read-only preview) |
| `GET /account` | account payload summary and lists | Operations, Terminal, Execution Mode |
| `GET /chart/{symbol}/{tf}` | chart context + candles | SMC, Operations drilldown |
| `GET /specs`, `GET /specs/{symbol}` | symbol execution specs | Runtime, Operations, Terminal |
| `GET /catalog` | symbol catalog/status | Runtime, Terminal |
| `POST /subscribe`, `POST /unsubscribe` | subscription mutations | Runtime |

## Data coupling matrix

### Readable now from API

- Runtime and connector health status
- Broker/account identity
- Subscribed symbols and chart worker status
- Feed freshness summaries
- Open positions and pending orders
- Exposure aggregates
- Symbol catalog/specs

### Visible today only in runtime DB (not first-class API yet)

- `fast_desk_signals`
- `fast_desk_trade_log`
- `smc_zones`
- `smc_thesis_cache`
- `smc_events_log`

UI policy: do not read SQLite directly from frontend. Treat these as backend telemetry waiting for API exposure.

### Should become API next

- Fast desk state endpoint (signal, trigger, cooldown, custody)
- SMC state endpoints (`thesis`, `zones`, `events`, `status`)
- Terminal safety endpoint with explicit `trade_allowed` and auth disruption flags
- Ownership endpoints (adopt, assign, audit)
- Risk endpoints (profile, budget, limits, kill switch)
- Execution mode endpoints (`live | paper`)

### UI sections that need mock/preview state now

- Ownership and Adoption view (full preview)
- Risk Center controls (full preview)
- Execution mode toggles (preview)
- SMC order execution controls (preview)
- Fast per-symbol trigger/confidence matrix (partial/preview until API)

## Startup flow

1. Boot on `/runtime`.
2. In parallel: fetch `GET /status`, `GET /catalog`, `GET /specs`.
3. Start SSE (`GET /events`).
4. If SSE fails, degrade to polling `GET /status` every 1-2 seconds.
5. Gate all write-intent controls until first healthy status snapshot.
6. Hydrate route stores from shared runtime store and mark capability badges per panel.

## Loading, error, empty states

Loading:
- deterministic skeletons matching final layout
- display `last_success_at` placeholder and stream state

Error:
- global critical error banner for runtime down/degraded
- panel-level failure isolation (one failing panel does not blank route)
- connector/blocker errors show concrete recovery message

Empty:
- positions/orders empty => neutral "no live operations" state
- no subscribed symbols => guided subscribe workflow
- no SMC thesis/zones => analysis pending state with `Preview` badge if API missing

## Representation rules for live vs planned capabilities

- `Live` controls: enabled only with supporting API/action path.
- `Partial` controls: enabled only for read paths; actions guarded with caveat labels.
- `Planned` controls: disabled by default, with explicit missing component note.
- `Preview` controls: visible to show roadmap interaction model, never fake success.

Critical warning policy:
- Account probe/account switch must always show danger copy about possible MT5 session disruption and AutoTrading disablement.

## Visualization model for trading entities

Terminals:
- show runtime instance identity today via `broker_identity`
- reserve `terminal_id` slot as planned field

Brokers and accounts:
- top-context strip with broker server, account login, account mode, margin/equity

Desks:
- Fast and SMC visual identities separated by accent and panel labeling

Positions and orders:
- grids with side, symbol, volume, open/current, SL/TP, PnL, age, comment
- ownership column shown as `Unknown/Planned` until `OwnershipRegistry`

Exposure:
- per-symbol gross/net exposure bars and concentration highlights

Feed health:
- worker freshness matrix by symbol/timeframe
- stale/degraded states prioritized over decorative metrics

Future ownership/risk:
- explicit preview panels with disabled controls and required backend component callouts

## Solid.js implementation direction

App structure:
- route-first SolidStart app
- one state module per domain
- shared runtime connection module for SSE + fallback polling

Recommended store boundaries:
- `runtimeStore`: health, identity, universes, stream state
- `operationsStore`: positions/orders/exposure filters and grid state
- `fastDeskStore`: fast desk view model (initially partial)
- `smcDeskStore`: thesis/zone view model (initially preview-heavy)
- `terminalStore`: account/terminal context and disruption warnings
- `capabilityStore`: static/dynamic feature flags (`Live`, `Partial`, `Planned`, `Preview`)

Rendering strategy:
- reusable panel system, no monolithic single page
- virtualized tables for dense operation lists
- composable chart overlays for SMC structure layers

Realtime strategy:
- SSE primary
- polling fallback
- stale event rejection by timestamp

## Initial frontend implementation slices

1. Deliver live Runtime and Operations routes against current control plane API.
2. Deliver Fast and SMC routes with honest `Partial`/`Preview` labeling for missing endpoints.
3. Deliver Terminal context route with explicit account-switch risk warnings.
4. Deliver Ownership, Risk, and Execution Mode routes as roadmap-ready preview shells.

