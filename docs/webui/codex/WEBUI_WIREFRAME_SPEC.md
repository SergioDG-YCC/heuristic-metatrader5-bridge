# WEBUI Wireframe Specification

Date: 2026-03-24  
Frontend target: Solid.js route-based control UI  
Repository: `heuristic-metatrader5-bridge`

Capability legend used in every screen:
- `Live`
- `Partial`
- `Planned`
- `Preview`

## Screen 1: Launch / Runtime Overview

### Purpose

Provide immediate startup confidence and show execution blockers before any desk action.

### Primary operator questions answered

- Is the bridge up or degraded?
- Is MT5 connector state healthy?
- Are feeds, workers, and subscriptions alive?
- Are there unresolved warnings right now?

### Visible widgets

- Global status strip (`status`, `health`, last update time)
- Connector/runtime health board
- Broker/account identity card
- Subscribed symbols + watch timeframes panel
- Chart worker matrix (`symbol x worker freshness`)
- Feed status lane
- Pending alerts stack
- SSE event timeline

### Interactions

- Manual refresh (`GET /status`)
- Pause/resume timeline auto-scroll
- Subscribe/unsubscribe symbol quick actions
- Click symbol to open chart drilldown

### Data source

- `GET /status`
- `GET /events`
- `GET /catalog`
- `GET /specs`
- `POST /subscribe`
- `POST /unsubscribe`

### Current backend status

- `Live` for runtime visibility and subscriptions.
- `Partial` for explicit terminal trading availability because `trade_allowed` is enforced in connector but not surfaced as a dedicated control-plane field.

### Future extension hooks

- explicit terminal state endpoint with `trade_allowed`
- multi-terminal selector by `terminal_id`
- startup dependency graph panel

### Mobile degradation notes

- collapse worker matrix into symbol cards
- keep only critical alerts pinned
- move timeline to optional drawer

## Screen 2: Operations Console

### Purpose

Act as the default supervision desk for positions, pending orders, and exposure concentration.

### Primary operator questions answered

- What is open right now?
- What is pending right now?
- Where is risk concentration highest?
- What changed in recent execution activity?

### Visible widgets

- Open positions data grid
- Pending orders data grid
- Exposure heatmap by symbol
- Account snapshot card (equity, free margin, drawdown, leverage)
- Recent events stream
- Per-symbol watchlist strip

### Interactions

- sort/filter by symbol, side, PnL, age
- quick symbol drilldown to chart
- focus mode for one symbol across all panels

### Data source

- `GET /positions`
- `GET /exposure`
- `GET /account`
- `GET /events`

### Current backend status

- `Live` for positions/orders/exposure read visibility.
- Ownership column is `Preview`/`Unknown` until ownership registry exists.

### Future extension hooks

- operation assignment actions
- operation lifecycle event API
- terminal-scoped operations filters

### Mobile degradation notes

- segmented tabs: Positions / Orders / Exposure
- reduced column set
- row details via bottom sheet

## Screen 3: Fast Desk View

### Purpose

Show fast signal-to-custody flow with an aggressive but controlled visual hierarchy.

### Primary operator questions answered

- Which symbols are armed, cooling down, or under custody?
- What fast decisions happened recently?
- Is Fast execution behavior aligned with runtime reality?

### Visible widgets

- Fast signal lane (symbol, side, trigger, confidence)
- Trigger/cooldown matrix
- Custody action stream (trail/hold/close)
- Fast trade log panel
- Fast risk assumptions panel

### Interactions

- symbol focus
- time window switch (1m/5m/15m)
- split view toggle (signals first vs custody first)

### Data source

- `GET /status` (shared runtime/account context)
- `GET /events` (live state pulse)
- optional future fast-specific endpoint for signal/cooldown details

### Current backend status

- `Partial`: Fast desk runtime and connector write surface exist.
- Fine-grained Fast telemetry (confidence/trigger/cooldown/trade log) is not a first-class control-plane API yet.
- UI must mark unavailable metrics as `Preview` or `Pending API`.

### Future extension hooks

- `GET /desks/fast/status`
- `GET /desks/fast/signals`
- `GET /desks/fast/custody-log`
- ownership-aware custody eligibility

### Mobile degradation notes

- merge signal and custody lanes into one timeline
- show top-N symbols only
- hide secondary risk panels behind accordion

## Screen 4: SMC Desk View

### Purpose

Present thesis-driven structural review for slower SMC workflows.

### Primary operator questions answered

- What zones and structural context are active?
- What thesis bias and validation state exist?
- Which operation candidates need review?

### Visible widgets

- Chart-first zone map (OB/FVG/liquidity/fibo overlays)
- Thesis board (bias, scenario, invalidations)
- Validation state board (heuristic + optional LLM)
- Review schedule panel
- Candidate operations list

### Interactions

- symbol/timeframe switch
- overlay layer toggles
- candidate inspection drawer
- thesis watchlist pin

### Data source

- `GET /chart/{symbol}/{timeframe}`
- `GET /status`
- `GET /events`
- planned SMC endpoints for zones/thesis/events

### Current backend status

- `Partial`: analysis-first SMC pipeline exists.
- `Planned`: full SMC trader execution from thesis to MT5.
- Zone/thesis/event details are currently DB-backed internals, not first-class HTTP resources.

### Future extension hooks

- `GET /smc/status`
- `GET /smc/zones/{symbol}`
- `GET /smc/thesis/{symbol}`
- `GET /smc/events`
- `POST /smc/trader/re-evaluate`

### Mobile degradation notes

- prioritize thesis list + next review
- render chart overlays as compact chips
- move candidates to separate tab

## Screen 5: Ownership and Adoption View

### Purpose

Define future operation ownership workflows and make current absence explicit.

### Primary operator questions answered

- Who owns each operation?
- Which operations are inherited/orphaned?
- How will reassignment and reevaluation work?

### Visible widgets

- Ownership matrix (position/order to desk owner)
- Adoption queue
- Reassignment panel (Fast/SMC/manual)
- Reevaluation toggle
- Ownership audit timeline

### Interactions

- select operation for proposed owner
- set reevaluation required
- annotate manual override reason

### Data source

- current: derived read-only placeholders from `GET /positions`
- future: ownership API

### Current backend status

- `Planned` major phase (`OwnershipRegistry` not implemented).
- Entire screen rendered as `Preview` with disabled controls and explicit missing-backend callouts.

### Future extension hooks

- `GET /operations`
- `GET /operations/{operation_uid}`
- `POST /operations/{operation_uid}/assign`
- `POST /operations/{operation_uid}/re-evaluate`

### Mobile degradation notes

- matrix becomes operation cards
- reassignment uses full-screen modal
- compress audit timeline to recent events only

## Screen 6: Risk Center

### Purpose

Define and supervise global/per-desk risk governance without faking unavailable controls.

### Primary operator questions answered

- What is global risk profile?
- How is budget split across desks?
- Which limits are close to breach?
- What is kill-switch posture?

### Visible widgets

- Global risk profile panel (`1..4`)
- Fast vs SMC budget board
- Exposure and drawdown pressure map
- Limits and overrides board
- Kill switch concept panel

### Interactions

- inspect budget/limit impact
- compare profile simulations (read-only now)
- review risk event timeline

### Data source

- current read-only: `GET /account`, `GET /exposure`
- future risk API endpoints

### Current backend status

- `Planned` major phase (`RiskKernel` not implemented).
- Only informational exposure/account views are `Live`.
- All controls are `Preview`/disabled.

### Future extension hooks

- `GET /risk/status`
- `PUT /risk/profile`
- `PUT /risk/allocations`
- `POST /risk/kill-switch/trip`
- `POST /risk/kill-switch/reset`

### Mobile degradation notes

- show one desk budget at a time
- keep breach alerts top-pinned
- collapse simulation widgets

## Screen 7: Terminal and Account Context View

### Purpose

Centralize terminal/account context and expose account-switch operational risk clearly.

### Primary operator questions answered

- Which broker/account context is active?
- Is session integrity stable?
- What are the risks before probing/switching account?

### Visible widgets

- Terminal context card (server/login/path placeholders)
- Account mode card (`demo|real|contest|unknown`)
- Session integrity panel
- Account switch danger warning panel
- Recovery checklist (AutoTrading re-enable + control-plane restart)

### Interactions

- open account-switch confirmation flow (future)
- copy recovery checklist
- acknowledge warning action

### Data source

- `GET /status`
- `GET /account`
- `GET /events`

### Current backend status

- `Partial`: context visibility is mostly live.
- `Planned`: safe account-switch orchestration API.
- UI must always show warning that failed auth/probe can disrupt MT5 session and disable AutoTrading.

### Future extension hooks

- explicit terminal diagnostics endpoint
- account switch audit trail endpoint
- account switch guarded mutation endpoint

### Mobile degradation notes

- warning panel remains always visible
- procedural recovery shown before metadata
- timeline moved to expandable section

## Screen 8: Paper vs Live Execution View

### Purpose

Separate current account mode visibility from future execution mode governance.

### Primary operator questions answered

- What account mode is connected now?
- What execution mode should be active (future)?
- What changes between live and paper operation?

### Visible widgets

- Current account mode panel
- Execution mode comparator (`live|paper|simulation`)
- Mode impact matrix
- Safety checklist before mode switch

### Interactions

- mode switch intent (disabled preview)
- what-if comparison controls

### Data source

- current: `GET /account`, `GET /status`
- future: execution mode endpoints

### Current backend status

- `Partial`: account mode is observable today.
- `Planned`: `execution_mode` control path is not implemented.
- Toggle controls remain `Preview` and disabled.

### Future extension hooks

- `GET /execution-mode`
- `PUT /execution-mode`
- paper engine event stream

### Mobile degradation notes

- comparison matrix becomes stacked cards
- checklist remains expanded by default
- hide advanced simulation options

## Cross-screen state behavior

Loading:
- route skeletons match final panel geometry
- each panel displays `last_success_at` placeholder

Error:
- global blocker banner for runtime down/degraded
- local panel fallback with retry where possible

Empty:
- no positions/orders => neutral "no active operations"
- no thesis/zones => "analysis pending" state
- unavailable backend => `Planned` badge + explicit dependency text

