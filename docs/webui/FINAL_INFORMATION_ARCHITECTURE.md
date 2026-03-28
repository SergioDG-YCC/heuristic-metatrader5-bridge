# Final Information Architecture

## IA intent

The final IA must optimize for operational supervision first, desk work second, and roadmap visibility third.

The user should not have to think in backend module names. The user should move through the product in the same order they validate a live trading environment:

1. bridge health
2. account and exposure context
3. symbol and chart inspection
4. desk-specific reasoning
5. governance and future controls

## Final navigation map

### Primary routes

- `/`
  - Runtime Overview
- `/operations`
  - Operations Console
- `/fast`
  - Fast Desk
- `/smc`
  - SMC Desk
- `/risk`
  - Risk Center
- `/terminal`
  - Terminal / Account Context
- `/alerts`
  - Alerts / Events

### Secondary routes or tabs

- `/ownership`
  - Ownership
- `/mode`
  - Live vs Paper

### Contextual drilldowns

- `/operations/symbol/:symbol`
  - symbol detail shell
- `/operations/symbol/:symbol/chart/:timeframe`
  - chart drilldown
- `/terminal/spec/:symbol`
  - symbol spec detail

These drilldowns should be entered from primary screens. They should not be promoted as separate top-level navigation destinations.

## Screen-level information priorities

### Runtime Overview

Priority order:

1. bridge health and freshness
2. MT5 connectivity and feed state
3. subscription footprint
4. current account/exposure headline
5. active alerts

### Operations Console

Priority order:

1. positions and exposure
2. broker activity and recent account changes
3. subscribed symbol watch state
4. chart access and symbol drilldown
5. operator follow-up actions

### Fast Desk

Priority order:

1. execution context and symbol focus
2. current positions/orders visibility
3. disabled or preview action lane
4. chart and tape-like state panels

### SMC Desk

Priority order:

1. thesis and zone context
2. market structure watch panels
3. candidate review
4. preview governance and execution handoff

### Risk Center

Priority order:

1. exposure concentration
2. margin and drawdown context
3. derived risk warnings
4. preview kernel controls and future governance hooks

### Terminal / Account Context

Priority order:

1. account identity and broker context
2. leverage, margin, drawdown, account mode
3. recent orders and deals
4. symbol specs and instrument metadata

### Alerts / Events

Priority order:

1. current critical alerts
2. recently derived state changes
3. broker activity timeline
4. preview event-history placeholders

## Main screen set and substructure

### Runtime Overview

Panels:

- bridge status strip
- connectivity and freshness card
- feed and subscription summary
- account headline strip
- top alerts rail

### Operations Console

Panels:

- positions grid
- exposure matrix
- recent deals and recent orders
- symbol watchlist with freshness status
- quick chart launch panel

### Fast Desk

Panels:

- instrument focus header
- position/order context
- preview execution rail
- fast metrics strip
- linked chart area

### SMC Desk

Panels:

- thesis summary rail
- zones/state board
- candidate review stack
- linked chart area
- preview handoff panel

### Risk Center

Panels:

- margin and drawdown board
- exposure concentration table
- symbol-level used-margin-share view
- derived warnings list
- preview governance panel

### Terminal / Account Context

Panels:

- account identity card
- account state metrics
- recent broker activity
- symbol spec explorer
- terminal caution notes

### Alerts / Events

Panels:

- critical alerts queue
- warnings queue
- derived state changes
- broker activity timeline
- preview audit/event history area

### Ownership

Panels:

- ownership model explainer
- preview terminal/account ownership table
- preview adoption/conflict queue

### Live vs Paper

Panels:

- mode model explainer
- current mode status as `Unknown` or `Preview`
- preview environment switching workflow

## Primary operator flows

### Flow 1: Runtime anomaly triage

1. land on Runtime Overview
2. confirm bridge freshness and feed state
3. jump to Alerts / Events if critical
4. inspect Operations Console for account impact

### Flow 2: Position and exposure supervision

1. open Operations Console
2. inspect positions and exposure concentration
3. jump to Terminal / Account Context for margin or broker detail
4. open Risk Center if thresholds look unsafe

### Flow 3: Symbol inspection

1. select symbol from watchlist, position, or alert
2. open symbol detail
3. open chart drilldown by timeframe
4. review spec detail if execution context requires it

### Flow 4: Fast desk preparation

1. confirm Runtime Overview is healthy
2. validate account context and current exposure
3. open Fast Desk
4. use preview action lane only as a future-oriented control map until write APIs exist

### Flow 5: SMC desk review

1. inspect Runtime Overview and Operations Console first
2. open SMC Desk
3. review thesis/zones/candidates in preview form combined with live chart context

## Widget hierarchy rules

- Status strips belong at the top.
- Grids and dense tables belong in the middle working area.
- Preview or roadmap panels belong in side rails or lower sections.
- Critical alerts should never be below the fold when present.
- Chart panels should support the current question; they should not dominate every route by default.

## Relationship to current and future endpoints

| Route | Current backend inputs | Future backend hooks |
| --- | --- | --- |
| Runtime Overview | `/status`, `/events`, `/account`, `/exposure`, `/catalog` | explicit supervisor/terminal health, desk status |
| Operations Console | `/positions`, `/exposure`, `/account`, `/events`, `/chart/{symbol}/{timeframe}` | terminal-scoped operations API, richer watch telemetry |
| Fast Desk | `/positions`, `/account`, `/exposure`, `/chart/...`, `/specs/{symbol}` | FastTraderService state, order and position mutations |
| SMC Desk | `/chart/...`, `/positions`, `/account` | thesis, zones, candidates, structure state, execution handoff |
| Risk Center | `/account`, `/exposure`, `/positions` | RiskKernel state, killswitch, account limits |
| Terminal / Account Context | `/account`, `/specs`, `/specs/{symbol}`, `/catalog` | terminal identity, terminal registry, trade permission |
| Alerts / Events | `/events`, `/account` | durable event feed, audit log, alert acknowledgements |
| Ownership | none live beyond indirect hints | OwnershipRegistry APIs and conflict actions |
| Live vs Paper | none reliable today | execution-mode APIs and environment governance |

## Explicit exclusions

These should not become primary IA elements in v1:

- settings editor
- environment-variable admin
- raw catalog page
- raw specs page
- raw health/debug page

They can exist as support surfaces only if they serve a concrete operator workflow.
