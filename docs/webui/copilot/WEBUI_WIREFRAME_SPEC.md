# WEBUI Wireframe Specification

Date: 2026-03-24
Frontend target: Solid.js route-based operator console

## Screen 1: Launch and Runtime Overview

### Purpose

Provide immediate startup confidence and surface blockers before any execution intent.

### Primary operator questions answered

- Is the bridge alive right now?
- Is market/account ingestion stable?
- Which symbols/timeframes are actively watched?
- Are there pending incidents requiring immediate action?

### Visible widgets

- Global health strip (status, market_state, account_state, broker_sessions, indicator bridge)
- Broker and account identity block
- Subscribed universe board with quick subscribe/unsubscribe
- Chart workers matrix (symbol x timeframe freshness)
- Feed status lane (live, idle, stale, unknown)
- Pending alerts stack
- Recent state timeline from SSE

### Interactions

- Refresh now
- Pause/resume SSE stream display (not backend stream)
- Open symbol detail to chart route
- Quick add/remove subscription

### Data source

- GET /status
- GET /catalog
- GET /events
- GET /specs

### Current backend status

- Live and usable now.
- trade_allowed is operationally critical but not explicit in /status payload; show terminal availability as Unknown unless endpoint exists.

### Future extension hooks

- terminal_id switcher once BridgeSupervisor exists
- explicit terminal trade_allowed indicator when endpoint is added
- startup dependency graph health inspector

### Mobile degradation notes

- Collapse chart worker matrix into grouped symbol cards
- Keep only top 3 critical alerts pinned
- Disable dense timeline rendering

## Screen 2: Operations Console

### Purpose

Central execution supervision board for open positions, pending orders, and symbol-level risk posture.

### Primary operator questions answered

- What is currently open and pending?
- Where is exposure concentrated?
- Which symbols are at risk or in opportunity state?
- What changed in execution activity in the last minutes?

### Visible widgets

- Open positions grid
- Pending orders grid
- Exposure heatmap by symbol
- Execution activity stream (recent deals and order events)
- Quick account snapshot (equity, free margin, drawdown, leverage)
- Symbol watchlist with state chips

### Interactions

- sort/filter by symbol, side, PnL, age, desk tag
- row drilldown to symbol chart and desk view
- export visible table snapshot (UI-side CSV)

### Data source

- GET /positions
- GET /exposure
- GET /account
- GET /events

### Current backend status

- Live and usable now.
- Ownership labels in grid are inferential at best until OwnershipRegistry exists.

### Future extension hooks

- action buttons per row for ownership reassignment
- risk override and lock controls per symbol
- terminal-specific operations partitioning

### Mobile degradation notes

- replace dual grids with segmented tabs (Positions, Orders, Exposure)
- reduce columns to critical metrics only
- detail drawer replaces inline expanded rows

## Screen 3: Fast Desk View

### Purpose

Show high-speed desk signal flow and custody decision stream with stress-safe readability.

### Primary operator questions answered

- What is Fast evaluating right now?
- Which symbols are in trigger, cooldown, or custody states?
- What were the most recent fast decisions and outcomes?

### Visible widgets

- Signal tape (latest per-symbol signal snapshots)
- Trigger and cooldown matrix
- Confidence and threshold panel
- Custody action feed (trail, hold, close)
- Fast trade log panel
- Fast risk mini-panel (per-trade risk assumptions)

### Interactions

- focus symbol lane
- time-window filter (1m, 5m, 15m)
- switch between signal-centric and custody-centric layouts

### Data source

- GET /status
- GET /events
- optional delayed enrichment from account/positions

### Current backend status

- Fast desk runtime exists and execution bridge is wired.
- Show caution badge for broker-dependent comment tagging behavior.

### Future extension hooks

- explicit FastTraderService status card
- ownership-aware custody eligibility flags
- per-symbol operator intervention policy

### Mobile degradation notes

- horizontal tape becomes vertical list
- custody feed and trade log merged into one timeline
- confidence matrix reduced to top movers

## Screen 4: SMC Desk View

### Purpose

Present thesis-oriented structural context and candidate review workflow.

### Primary operator questions answered

- What structure and zone context exists now?
- What is the current thesis bias and validation confidence?
- Which candidates are under review and when next review happens?

### Visible widgets

- Zone map with OB/FVG/liquidity overlays
- Thesis board (bias, scenario, invalidation)
- Validation state panel (heuristic vs optional LLM)
- Review scheduler
- Candidate operations list

### Interactions

- inspect zone evidence layers
- review candidate rationale
- pin thesis to watchlist

### Data source

- GET /chart/{symbol}/{timeframe}
- GET /status
- GET /events
- optional account context from GET /account

### Current backend status

- Analysis-first is available.
- Full SMC trader execution remains planned.

### Future extension hooks

- SmcTraderService action controls
- thesis-to-order linkage and audit trace
- ownership handoff controls

### Mobile degradation notes

- prioritize thesis list and next review times
- chart overlay layers become selectable chips
- hide low-priority evidence blocks

## Screen 5: Ownership and Adoption View

### Purpose

Provide ownership mapping for positions/orders and planned adoption/reassignment workflow.

### Primary operator questions answered

- Who owns each live operation?
- Which operations are inherited or unknown?
- What reassignment actions are pending?

### Visible widgets

- Ownership matrix table (position/order x owner/state)
- Adoption queue panel
- Reassignment form (Fast, SMC, Manual)
- Reevaluation toggle control
- Ownership audit timeline

### Interactions

- select operation and propose owner
- set reevaluation required flag
- annotate manual override reason

### Data source

- Current phase: derived placeholder state from GET /positions and comments where available
- Future phase: dedicated ownership endpoints

### Current backend status

- Planned major phase.
- Entire screen is preview with disabled action buttons and explanation callouts.

### Future extension hooks

- GET /ownership/state
- POST /ownership/reassign
- POST /ownership/adopt

### Mobile degradation notes

- matrix converts to operation cards
- reassignment opens full-screen modal
- audit timeline condensed to last 20 entries

## Screen 6: Risk Center

### Purpose

Expose account and desk risk posture, budgets, and emergency control concepts.

### Primary operator questions answered

- What is current global risk posture?
- How is risk split by desk?
- Are limits near breach?
- Is kill switch available and what is its state?

### Visible widgets

- Global risk profile card (1..4 profile model)
- Desk budget bars (Fast vs SMC)
- Exposure and drawdown risk map
- Limit and override board
- Kill switch panel

### Interactions

- inspect breach conditions
- simulate profile switch impact (no write)
- review override history

### Data source

- Current phase: GET /account + GET /exposure for informational risk only
- Future phase: risk endpoints

### Current backend status

- Planned major phase.
- Risk kernel controls and kill switch are preview only.

### Future extension hooks

- GET /risk/state
- POST /risk/profile
- POST /risk/override
- POST /risk/kill-switch

### Mobile degradation notes

- show one desk at a time
- move simulations to secondary sheet
- keep breach alerts top-pinned

## Screen 7: Terminal and Account Context View

### Purpose

Expose terminal, broker, account context and account-switch safety risks.

### Primary operator questions answered

- Which MT5 installation and account context is active?
- Is session health stable?
- What warnings apply before any account probe/switch?

### Visible widgets

- Terminal context card (installation path placeholder, broker server, account login)
- Account mode card (demo/real/contest)
- Session integrity panel
- Account-switch danger warning banner
- Recovery checklist block for auth disruptions

### Interactions

- open account-switch confirmation modal (future write flow)
- acknowledge warning and log operator acknowledgement

### Data source

- GET /status
- GET /account
- GET /events

### Current backend status

- Read visibility is mostly available.
- Safe switch orchestration is planned and should remain disabled.

### Future extension hooks

- account probe and switch workflows with explicit disruption handling
- terminal health endpoint including trade_allowed and auth diagnostics

### Mobile degradation notes

- keep warning and recovery checklist permanently visible at top
- collapse low-priority metadata into accordion sections

## Screen 8: Paper vs Live Execution View

### Purpose

Separate broker account mode from bridge execution mode and prepare controlled paper workflow.

### Primary operator questions answered

- Is this account demo or real today?
- Is bridge execution currently live or paper?
- What would change if execution mode flips?

### Visible widgets

- Account mode observed panel (from account state)
- Execution mode planned panel (Live, Paper, Simulation)
- Mode impact comparison table
- Compliance checklist before mode switch

### Interactions

- mode switch intent (disabled preview)
- what-if simulation selector

### Data source

- Current phase: GET /account and GET /status
- Future phase: execution mode endpoints

### Current backend status

- account_mode is available now.
- execution_mode as runtime control is planned.

### Future extension hooks

- GET /execution-mode
- POST /execution-mode
- simulation stream endpoint for paper fills

### Mobile degradation notes

- show comparison table as stacked cards
- keep mode warning text always expanded
- hide advanced simulation settings

## Cross-screen loading/error/empty specification

Loading contract:
- show deterministic skeleton layouts matching final component structure
- include last update timestamp placeholder

Error contract:
- fatal runtime error: lock write-intent controls globally
- panel error: keep route alive and render panel fallback with retry

Empty contract:
- no positions/orders: show neutral operational state, not success celebration
- no SMC thesis: show analysis waiting state
- planned backend missing: show Planned badge and missing component reference
