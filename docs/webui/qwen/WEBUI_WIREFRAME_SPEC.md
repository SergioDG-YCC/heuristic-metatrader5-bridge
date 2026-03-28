# WebUI Wireframe Specifications

**Version**: 1.0.0  
**Date**: 2026-03-24  
**Framework**: Solid.js  
**Repository**: `heuristic-metatrader5-bridge`  
**Control Plane**: `http://0.0.0.0:8765`

---

## Screen 1: Launch / Runtime Overview

**Route**: `/dashboard`  
**Priority**: Primary  
**Backend Status**: ✅ Fully Implemented (via `/status`)

### Purpose

Single-pane visibility into system health, market feed status, account state, and desk status. First screen operators see on startup.

### Primary Operator Questions Answered

1. Is the backend healthy and connected to MT5?
2. Is market data flowing for all subscribed symbols?
3. What is my current account state (balance, equity, positions)?
4. Are Fast Desk and SMC Desk running?
5. Is AutoTrading enabled (trade_allowed)?
6. Are there any system warnings or alerts?

### Visible Widgets

```
┌─────────────────────────────────────────────────────────────────┐
│  TOP BAR                                                         │
│  [System: ● Live]  [Account: 105845678 | $10,250]  [14:30 UTC] │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┬──────────────┬──────────────┬──────────────────┐
│  MARKET      │  ACCOUNT     │  FAST DESK   │  SMC DESK        │
│  STATE       │  SUMMARY     │  STATUS      │  STATUS          │
├──────────────┼──────────────┼──────────────┼──────────────────┤
│  ● Up        │  Bal: $10K   │  ● Running   │  ● Running       │
│  5 Symbols   │  Equ: $10.2K │  5 Workers   │  Scanner Active  │
│  5 Workers   │  DD: 2.1%    │  Scan: 5s    │  LLM: Enabled    │
└──────────────┴──────────────┴──────────────┴──────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  TRADE ALLOWED STATUS  ● AutoTrading Enabled                     │
│  All execution paths are OPEN. MT5 terminal is ready.           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  FEED HEALTH (per symbol)                                        │
├─────────────────────────────────────────────────────────────────┤
│  Symbol  │  Timeframes  │  Last Bar      │  Age    │  Worker  │
├─────────────────────────────────────────────────────────────────┤
│  BTCUSD  │  M5, H1, H4  │  14:25:00 UTC  │  45s ●   │  ● Active│
│  EURUSD  │  M5, H1, H4  │  14:25:00 UTC  │  42s ●   │  ● Active│
│  GBPUSD  │  M5, H1, H4  │  14:25:00 UTC  │  50s ●   │  ● Active│
│  USDJPY  │  M5, H1, H4  │  14:25:00 UTC  │  48s ●   │  ● Active│
│  USDCHF  │  M5, H1, H4  │  14:25:00 UTC  │  55s ●   │  ● Active│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ACCOUNT SNAPSHOT                                                │
├─────────────────────────────────────────────────────────────────┤
│  Balance: $10,000.00  │  Equity: $10,250.00  │  Floating: +$250│
│  Free Margin: $8,500  │  Margin Level: 683% │  Positions: 5    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  RECENT EVENTS (Live SSE Feed)                                   │
├─────────────────────────────────────────────────────────────────┤
│  [14:28:00]  System  Account state refreshed (2s interval)      │
│  [14:27:55]  Market  BTCUSD M5 bar updated                      │
│  [14:27:50]  Fast    Symbol worker scan completed (5 symbols)   │
│  [14:27:30]  SMC     Scanner cycle completed                    │
└─────────────────────────────────────────────────────────────────┘
```

### Interactions

- **Click symbol row** → Navigate to `/charts?symbol=BTCUSD`
- **Click event** → Expand event details inline
- **Refresh button** → Force reload `/status`
- **Auto-refresh** → Every 5 seconds (configurable)

### Data Source

- `/status` — System health, broker identity, desk status, worker counts
- `/account` — Account summary (balance, equity, positions count)
- `/events?interval=1.0` — SSE event stream

### Current Backend Status

✅ All data available via `/status` and `/account` endpoints.

### Future Extension Hooks

- Add RiskKernel status panel (Phase 2)
- Add Ownership summary (Phase 3)
- Add multi-terminal selector (Phase 1)
- Add Paper/Live mode indicator (Phase 4)

### Mobile Degradation

- Stack all panels vertically
- Hide feed detail table (show summary only)
- Collapse desk status to badges
- Show last 5 events only

---

## Screen 2: Operations Console

**Route**: `/operations`  
**Priority**: Primary  
**Backend Status**: ✅ Fully Implemented

### Purpose

Real-time visibility into open positions, pending orders, and account exposure. Operator's main trading supervision screen.

### Primary Operator Questions Answered

1. What positions are open right now?
2. What is my total P&L (floating)?
3. What orders are pending?
4. What is my exposure per symbol?
5. What are the position comments (ownership hints)?

### Visible Widgets

```
┌─────────────────────────────────────────────────────────────────┐
│  EXPOSURE SUMMARY                                                │
├─────────────────────────────────────────────────────────────────┤
│  Gross: 0.45 lots  │  Net: 0.25 lots  │  Floating: +$250      │
│  Positions: 5  │  Orders: 1  │  Margin Used: $1,500           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  OPEN POSITIONS                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Symbol  │  Side  │  Vol  │  Entry   │  Current  │  P&L      │
├─────────────────────────────────────────────────────────────────┤
│  EURUSD  │  BUY ● │  0.10  │  1.0850  │  1.0862   │  +$12.00 │
│    SL: 1.0800  TP: 1.0950  │  Swap: -$0.30  │  Comment: ti:xxx│
│    Opened: 02:29 UTC  │  [Close] [Modify] (disabled)           │
├─────────────────────────────────────────────────────────────────┤
│  EURUSD  │  BUY ● │  0.10  │  1.0845  │  1.0862   │  +$17.00 │
│    SL: 1.0800  TP: 1.0950  │  Swap: -$0.30  │  Comment: ti:yyy│
│    Opened: 02:36 UTC  │  [Close] [Modify] (disabled)           │
├─────────────────────────────────────────────────────────────────┤
│  GBPUSD  │  SELL ●│  0.10  │  1.2640  │  1.2634   │  +$6.00  │
│    SL: 1.2680  TP: 1.2550  │  Swap: -$0.10  │  Comment: ti:zzz│
│    Opened: 02:50 UTC  │  [Close] [Modify] (disabled)           │
├─────────────────────────────────────────────────────────────────┤
│  BTCUSD  │  BUY ● │  0.15  │  68500   │  69200    │  +$105.00│
│    SL: 67500  TP: 72000  │  Swap: -$0.50  │  Comment: ti:aaa │
│    Opened: 02:40 UTC  │  [Close] [Modify] (disabled)           │
├─────────────────────────────────────────────────────────────────┤
│  BTCUSD  │  BUY ● │  0.05  │  68800   │  69200    │  +$20.00 │
│    SL: 67800  TP: 72000  │  Swap: -$0.20  │  Comment: ti:bbb │
│    Opened: 02:45 UTC  │  [Close] [Modify] (disabled)           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  PENDING ORDERS                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Symbol  │  Type       │  Vol  │  Price   │  SL/TP    │  Age  │
├─────────────────────────────────────────────────────────────────┤
│  BTCUSD  │  Buy Limit  │  0.05  │  68000   │  67000/   │  42m  │
│                                    │  72000    │  [Cancel]    │
│    Comment: ti:ccc  │  Created: 02:48 UTC                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  EXECUTION NOTICE                                              │
├─────────────────────────────────────────────────────────────────┤
│  ⚠️ Execution buttons disabled: MT5 execution surface under    │
│  certification. modify_position_levels, close_position, and    │
│  related methods pending implementation.                       │
└─────────────────────────────────────────────────────────────────┘
```

### Interactions

- **Click [Close]** → Disabled with tooltip (execution surface incomplete)
- **Click [Modify]** → Disabled with tooltip
- **Click [Cancel]** → Disabled with tooltip
- **Click position row** → Expand position details
- **Sort columns** → Click column header
- **Filter by symbol** → Dropdown filter
- **Auto-refresh** → Every 3 seconds for positions, 10s for account

### Data Source

- `/positions` — Positions and orders list
- `/account` — Account summary
- `/exposure` — Exposure breakdown

### Current Backend Status

✅ All endpoints implemented. Execution buttons disabled due to incomplete execution surface in Fast Desk bridge.

### Future Extension Hooks

- Enable Close/Modify buttons when `modify_position_levels`, `close_position` implemented
- Ownership badge per position (Phase 3)
- Position-level P&L chart (Phase 2)

### Mobile Degradation

- Show positions as cards (not table)
- Hide order details (show count only)
- Collapse position details (expand on tap)

---

## Screen 3: Fast Desk View

**Route**: `/fast-desk`  
**Priority**: Secondary  
**Backend Status**: ⚠️ Partial (Architecture present, execution incomplete)

### Purpose

Monitor Fast Desk heuristic signal flow, per-symbol worker status, and custody state. Execution controls disabled until MT5 surface certified.

### Primary Operator Questions Answered

1. Is Fast Desk running?
2. How many symbol workers are active?
3. What is the scan/custody interval?
4. Are there any signals in cooldown?
5. What is the execution interface status?

### Visible Widgets

```
┌─────────────────────────────────────────────────────────────────┐
│  FAST DESK STATUS  ● Running (FAST_DESK_ENABLED=true)            │
├─────────────────────────────────────────────────────────────────┤
│  Architecture: ✅ Complete  │  Execution: ⚠️ Interface Incomplete│
│  Workers: 5 active  │  Scan: 5s  │  Custody: 2s                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SYMBOL WORKERS                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Symbol  │  Status    │  Last Scan   │  Cooldown  │  Signals  │
├─────────────────────────────────────────────────────────────────┤
│  BTCUSD  │  ● Active  │  14:28:00    │  None      │  0 (1h)   │
│  EURUSD  │  ● Active  │  14:28:00    │  None      │  0 (1h)   │
│  GBPUSD  │  ● Active  │  14:28:00    │  None      │  0 (1h)   │
│  USDJPY  │  ● Active  │  14:28:00    │  None      │  0 (1h)   │
│  USDCHF  │  ● Active  │  14:28:00    │  None      │  0 (1h)   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  EXECUTION INTERFACE STATUS  ⚠️ Under Certification              │
├─────────────────────────────────────────────────────────────────┤
│  Available:                                                      │
│  ✅ send_execution_instruction (market/limit/stop, comment="") │
│                                                                  │
│  Pending:                                                        │
│  ❌ modify_position_levels                                      │
│  ❌ modify_order_levels                                         │
│  ❌ remove_order                                                 │
│  ❌ close_position                                               │
│  ❌ find_open_position_id                                        │
│                                                                  │
│  Impact: Execution buttons disabled until certification complete│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  RISK CONFIG (from env)                                          │
├─────────────────────────────────────────────────────────────────┤
│  Risk Per Trade: 1.0%  │  Max Positions/Symbol: 1             │
│  Max Positions Total: 4  │  Drawdown Guard: Active            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ROADMAP: FastTraderService (Phase 3)                            │
├─────────────────────────────────────────────────────────────────┤
│  Planned capabilities:                                           │
│  • Real execution via certified MT5 surface                     │
│  • Position custody (trail SL, lock profit, hard cut)          │
│  • Pending order management                                     │
│  • Spread/slippage gates                                        │
│  • Ownership tracking                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Interactions

- **Click worker row** → Navigate to `/charts?symbol=`
- **Click execution status** → Expand certification details
- **Auto-refresh** → Every 5 seconds

### Data Source

- `/status` — Fast Desk worker counts, health
- `/account` — Risk parameters (indirectly via env)

### Current Backend Status

⚠️ Fast Desk architecture complete (scanner, risk, policy, custody logic), but `FastExecutionBridge` calls non-existent connector methods (`place_order`, `modify_position`, `close_position`). Execution disabled.

### Future Extension Hooks

- Enable execution when MT5 surface certified
- Add signal detail panel
- Add custody action log

### Mobile Degradation

- Stack workers vertically
- Hide execution status detail
- Collapse roadmap panel

---

## Screen 4: SMC Desk View

**Route**: `/smc`  
**Priority**: Secondary  
**Backend Status**: ⚠️ Partial (Scanner/analyst present, trader not implemented)

### Purpose

Monitor SMC scanner activity, view detected zones and thesis. Analysis-only mode (no trader execution until Phase 3).

### Primary Operator Questions Answered

1. Is SMC scanner running?
2. How many zones detected?
3. What thesis are active?
4. Is LLM validator enabled?
5. When will trader be implemented?

### Visible Widgets

```
┌─────────────────────────────────────────────────────────────────┐
│  SMC DESK STATUS  ● Running (SMC_SCANNER_ENABLED=true)           │
├─────────────────────────────────────────────────────────────────┤
│  Scanner: ✅ Active  │  Analyst: ✅ Heuristic  │  LLM: ✅ Enabled│
│  Zones Detected: 0  │  Active Thesis: 0  │  Trader: ❌ Pending │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ZONE DETECTION (per symbol)                                     │
├─────────────────────────────────────────────────────────────────┤
│  Symbol  │  OB Bull  │  OB Bear  │  FVG  │  Liquidity  │  Conf │
├─────────────────────────────────────────────────────────────────┤
│  BTCUSD  │  0        │  0        │  0     │  0          │  —    │
│  EURUSD  │  0        │  0        │  0     │  0          │  —    │
│  GBPUSD  │  0        │  0        │  0     │  0          │  —    │
│  USDJPY  │  0        │  0        │  0     │  0          │  —    │
│  USDCHF  │  0        │  0        │  0     │  0          │  —    │
└─────────────────────────────────────────────────────────────────┘
│  Note: No zones detected in current session                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ACTIVE THESIS                                                   │
├─────────────────────────────────────────────────────────────────┤
│  No active thesis. Scanner is running but no setups detected.  │
│                                                                  │
│  Thesis will appear here when:                                  │
│  1. Scanner detects confluences (OB + FVG + liquidity)         │
│  2. Heuristic analyst builds bias + scenario                   │
│  3. Heuristic validator passes confidence threshold            │
│  4. LLM validator confirms (if SMC_LLM_ENABLED=true)           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  TRADER STATUS  ❌ Not Implemented                               │
├─────────────────────────────────────────────────────────────────┤
│  The SMC Trader component is planned for Phase 3.              │
│                                                                  │
│  Planned capabilities:                                           │
│  • Convert thesis to execution plans                            │
│  • Emit market/limit/stop orders                                │
│  • Manage pending orders                                        │
│  • Slow, deliberate custody (vs Fast Desk)                      │
│  • Re-evaluation on thesis invalidation                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SMC DETECTION PIPELINE                                          │
├─────────────────────────────────────────────────────────────────┤
│  Candles → Structure → OB → FVG → Liquidity → Fibonacci →       │
│  Elliott → Confluences → Analyst → Validator → (LLM) → Thesis  │
│                                                                  │
│  Current status: Pipeline active, no setups meeting thresholds │
└─────────────────────────────────────────────────────────────────┘
```

### Interactions

- **Click symbol row** → Navigate to `/charts?symbol=`
- **Click thesis (when present)** → Expand thesis details
- **Auto-refresh** → Every 10 seconds

### Data Source

- `/status` — SMC scanner status, zone counts
- (Future) `/smc/zones` — Zone details
- (Future) `/smc/thesis` — Active thesis

### Current Backend Status

⚠️ SMC scanner, analyst, and validator implemented. No trader service. No zones/thesis endpoints exposed via Control Plane yet.

### Future Extension Hooks

- Add `/smc/zones` endpoint
- Add `/smc/thesis` endpoint
- Implement SmcTraderService (Phase 3)
- Add chart zone overlays

### Mobile Degradation

- Stack zones vertically
- Hide detection pipeline diagram
- Collapse thesis details

---

## Screen 5: Chart Browser

**Route**: `/charts`  
**Priority**: Primary  
**Backend Status**: ✅ Fully Implemented

### Purpose

Multi-symbol chart viewing with candlestick data from RAM. Primary market analysis screen.

### Primary Operator Questions Answered

1. What is the current price action per symbol?
2. What timeframes are available?
3. What is the chart context (structure, swings)?
4. Is data fresh (bar age)?

### Visible Widgets

```
┌─────────────────────────────────────────────────────────────────┐
│  CHART BROWSER                                                   │
├─────────────────────────────────────────────────────────────────┤
│  Symbol: [BTCUSD ▼]  │  Timeframe: [M5 ▼]  │  Bars: [200]     │
│  [Load Chart]  │  Last Bar: 14:25:00 UTC (45s ago) ●           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  CANDLESTICK CHART (TradingView Lightweight)                     │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                                                          │  │
│  │  [Candlestick chart with 200 bars]                       │  │
│  │                                                          │  │
│  │  Current Price: $69,200 ●                                 │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│  [Zoom] [Pan] [Crosshair]  │  Timeframes: M1 M5 H1 H4 D1      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  CHART CONTEXT                                                   │
├─────────────────────────────────────────────────────────────────┤
│  Structure: {                                                    │
│    "trend": "bullish",                                          │
│    "last_swing_high": 69500,                                    │
│    "last_swing_low": 68000,                                     │
│    "phase": "expansion"                                         │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  MULTI-CHART GRID (optional view)                                │
├─────────────────────────────────────────────────────────────────┤
│  [BTCUSD M5]  [EURUSD M5]  [GBPUSD M5]                         │
│  [69,200 ●]   [1.0862 ●]   [1.2634 ●]                          │
│  [+0.5%]      [+0.1%]      [-0.05%]                            │
└─────────────────────────────────────────────────────────────────┘
```

### Interactions

- **Change symbol** → Reload chart
- **Change timeframe** → Reload chart
- **Change bars** → Reload with different count
- **Click chart** → Show crosshair + price
- **Auto-refresh** → Every 5 seconds (via SSE)

### Data Source

- `/chart/{symbol}/{timeframe}?bars=200` — Chart context + candles
- `/events?interval=1.0` — SSE for live updates

### Current Backend Status

✅ Fully implemented. Chart data served from RAM via CoreRuntimeService.

### Future Extension Hooks

- Add SMC zone overlays
- Add indicator overlays (from IndicatorBridge)
- Add drawing tools
- Add multi-chart sync

### Mobile Degradation

- Single chart view only
- Hide chart context JSON
- Simplify toolbar

---

## Screen 6: Risk Center

**Route**: `/risk`  
**Priority**: Secondary  
**Backend Status**: ⚠️ Partial (FastRiskEngine only, no RiskKernel)

### Purpose

View current risk configuration and account exposure. Roadmap for RiskKernel (Phase 2).

### Primary Operator Questions Answered

1. What is the current risk per trade?
2. What are the position limits?
3. What is my current exposure?
4. What risk features are planned?

### Visible Widgets

```
┌─────────────────────────────────────────────────────────────────┐
│  RISK CENTER  ⚠️ Partial (FastRiskEngine Only)                   │
├─────────────────────────────────────────────────────────────────┤
│  Current: FastRiskEngine (per-trade sizing)                    │
│  Planned: RiskKernel (global + per-desk budgets) — Phase 2     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  FAST DESK RISK CONFIG (from env)                                │
├─────────────────────────────────────────────────────────────────┤
│  Risk Per Trade: 1.0%  │  Max Positions/Symbol: 1             │
│  Max Positions Total: 4  │  Drawdown Guard: Active            │
│  Lot Sizing: balance × risk% / SL_pips × pip_value             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ACCOUNT EXPOSURE                                                │
├─────────────────────────────────────────────────────────────────┤
│  Gross Exposure: 0.45 lots  │  Net Exposure: 0.25 lots         │
│  Floating P&L: +$250  │  Used Margin: $1,500                   │
│  Free Margin: $8,500  │  Margin Level: 683%                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  PER-SYMBOL EXPOSURE                                             │
├─────────────────────────────────────────────────────────────────┤
│  Symbol  │  Net Vol  │  Gross Vol  │  Floating P&L  │  Risk   │
├─────────────────────────────────────────────────────────────────┤
│  EURUSD  │  +0.20    │  0.20       │  +$34.00       │  $20.00 │
│  GBPUSD  │  -0.10    │  0.10       │  +$6.00        │  $8.00  │
│  BTCUSD  │  +0.15    │  0.20       │  +$210.00      │  $150.00│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  RISKKERNEL ROADMAP (Phase 2)                                    │
├─────────────────────────────────────────────────────────────────┤
│  Planned capabilities:                                           │
│  • Global risk profile (1-4: Low/Medium/High/Chaos)            │
│  • Per-desk budget allocation (Fast vs SMC weights)            │
│  • Kill switch (global + per-desk)                             │
│  • Dynamic exposure limits                                      │
│  • Circuit breakers (daily loss, consecutive losses)           │
│  • Real-time guard interval                                     │
│                                                                  │
│  Default profiles (conceptual):                                 │
│  • Low: max_drawdown=2%, per_trade=0.30%, max_positions=3      │
│  • Medium: max_drawdown=3.5%, per_trade=0.50%, max_positions=5 │
│  • High: max_drawdown=5%, per_trade=0.75%, max_positions=10    │
│  • Chaos: max_drawdown=15%, per_trade=2%, max_positions=20     │
└─────────────────────────────────────────────────────────────────┘
```

### Interactions

- **Click roadmap section** → Expand RiskKernel details
- **Auto-refresh** → Every 10 seconds for exposure

### Data Source

- `/account` — Account state, exposure
- `/exposure` — Per-symbol breakdown
- `/status` — Risk config (from env)

### Current Backend Status

⚠️ FastRiskEngine provides per-trade sizing and drawdown guard. No RiskKernel, no kill switch, no budget allocator.

### Future Extension Hooks

- RiskKernel implementation (Phase 2)
- Kill switch toggle
- Budget configuration UI
- Per-desk risk allocation

### Mobile Degradation

- Stack exposure panels
- Hide per-symbol table (show summary)
- Collapse roadmap

---

## Screen 7: Terminal / Account Context

**Route**: `/terminal`  
**Priority**: Secondary  
**Backend Status**: ✅ Implemented (via `/status`)

### Purpose

View MT5 terminal state, broker details, account configuration, and critical AutoTrading status.

### Primary Operator Questions Answered

1. Which MT5 terminal is connected?
2. Which broker and server am I using?
3. Is the account DEMO, REAL, or CONTEST?
4. Is AutoTrading enabled (trade_allowed)?
5. Are there any authentication risks?

### Visible Widgets

```
┌─────────────────────────────────────────────────────────────────┐
│  TERMINAL CONTEXT                                                │
├─────────────────────────────────────────────────────────────────┤
│  Note: AutoTrading status is CRITICAL. If disabled, all        │
│  execution operations are blocked.                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  MT5 TERMINAL                                                    │
├─────────────────────────────────────────────────────────────────┤
│  Terminal Name: MetaTrader 5                                    │
│  Terminal Path: C:\Program Files\...\terminal64.exe            │
│  Broker Company: FBS Ltd.                                       │
│  Broker Server: FBS-Demo                                        │
│  Connection: ● Connected                                        │
│  Trade Allowed: ● Yes (AutoTrading enabled)                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ACCOUNT DETAILS                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Account Login: 105845678                                       │
│  Account Mode: DEMO  (● Demo | ○ Real | ○ Contest)             │
│  Currency: USD                                                  │
│  Leverage: 1:100                                                │
│  Balance: $10,000.00                                            │
│  Equity: $10,250.00                                             │
│  Free Margin: $8,500.00                                         │
│  Margin Level: 683.3%                                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ⚠️ ACCOUNT SWITCH WARNING                                       │
├─────────────────────────────────────────────────────────────────┤
│  Changing or probing another account can:                       │
│  • Degrade the active MT5 terminal session                      │
│  • Disable AutoTrading (trade_allowed = false)                  │
│  • Require manual recovery in MT5                               │
│                                                                  │
│  Recovery if authentication fails:                              │
│  1. Re-enable AutoTrading in MT5 terminal                       │
│  2. Relaunch apps/control_plane.py if services crashed          │
│                                                                  │
│  [ I Understand ] (disabled — account switch not exposed)       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SYMBOL WATCHLIST                                                │
├─────────────────────────────────────────────────────────────────┤
│  Subscribed symbols (from MT5_WATCH_SYMBOLS):                   │
│  BTCUSD, EURUSD, GBPUSD, USDJPY, USDCHF                         │
│                                                                  │
│  [Manage Symbols] (navigates to /settings)                      │
└─────────────────────────────────────────────────────────────────┘
```

### Interactions

- **Click [Manage Symbols]** → Navigate to `/settings`
- **Auto-refresh** → Every 30 seconds for account state

### Data Source

- `/status` — Broker identity, terminal health, trade_allowed
- `/account` — Account details

### Current Backend Status

✅ Implemented via `/status`. Trade allowed status observable but may need explicit exposure in health response.

### Future Extension Hooks

- Explicit `trade_allowed` field in `/status` health
- Account switch API (with danger warnings)
- Multi-terminal selector (Phase 1)

### Mobile Degradation

- Stack all panels vertically
- Hide terminal path (show name only)
- Collapse account details

---

## Screen 8: Settings

**Route**: `/settings`  
**Priority**: Tertiary  
**Backend Status**: ✅ Implemented (subscribe/unsubscribe)

### Purpose

Configure subscribed symbol universe and view environment variables.

### Primary Operator Questions Answered

1. What symbols are currently subscribed?
2. What timeframes are being tracked?
3. How do I add/remove symbols?
4. What are the current env var settings?

### Visible Widgets

```
┌─────────────────────────────────────────────────────────────────┐
│  SETTINGS                                                        │
├─────────────────────────────────────────────────────────────────┤
│  Note: Changes require restart for some settings.              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SUBSCRIBED SYMBOLS                                              │
├─────────────────────────────────────────────────────────────────┤
│  Currently subscribed:                                           │
│  ┌──────────┬─────────────┬─────────────────────────────────┐  │
│  │  BTCUSD  │  ● Active   │  [Unsubscribe]                  │  │
│  │  EURUSD  │  ● Active   │  [Unsubscribe]                  │  │
│  │  GBPUSD  │  ● Active   │  [Unsubscribe]                  │  │
│  │  USDJPY  │  ● Active   │  [Unsubscribe]                  │  │
│  │  USDCHF  │  ● Active   │  [Unsubscribe]                  │  │
│  └──────────┴─────────────┴─────────────────────────────────┘  │
│                                                                  │
│  Add symbol: [───────────] [Subscribe]                          │
│  (Symbol must exist in broker catalog)                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  TIMEFRAMES                                                      │
├─────────────────────────────────────────────────────────────────┤
│  Tracked timeframes (from MT5_WATCH_TIMEFRAMES):                │
│  ● M1  ● M5  ● H1  ● H4  ● D1                                  │
│                                                                  │
│  Note: Changing timeframes requires restart.                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ENVIRONMENT VARIABLES (read-only)                               │
├─────────────────────────────────────────────────────────────────┤
│  FAST_DESK_ENABLED=true                                         │
│  SMC_SCANNER_ENABLED=true                                       │
│  SMC_LLM_ENABLED=true                                           │
│  FAST_DESK_RISK_PERCENT=1.0                                     │
│  FAST_DESK_MAX_POSITIONS_PER_SYMBOL=1                           │
│  FAST_DESK_MAX_POSITIONS_TOTAL=4                                │
│  MT5_POLL_SECONDS=5                                             │
│  CORE_ACCOUNT_REFRESH_SECONDS=2                                 │
│  ACCOUNT_MODE=demo                                              │
│                                                                  │
│  Note: Changing env vars requires editing .env file and        │
│  restarting control plane.                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Interactions

- **Click [Subscribe]** → POST `/subscribe`, add symbol
- **Click [Unsubscribe]** → POST `/unsubscribe`, remove symbol
- **Symbol input** → Autocomplete from catalog

### Data Source

- `/status` — Current subscribed universe
- `/catalog` — Available symbols for autocomplete
- `/account` — Timeframes (indirectly)

### Current Backend Status

✅ Subscribe/unsubscribe endpoints implemented.

### Future Extension Hooks

- Env var editor (with restart warning)
- Timeframe configuration
- Risk parameter configuration (when RiskKernel implemented)

### Mobile Degradation

- Stack symbol list
- Hide env var details (show count only)

---

## Summary: Implementation Priority

| Priority | Screen | Route | Status | Notes |
|----------|--------|-------|--------|-------|
| P0 | Launch Overview | `/dashboard` | ✅ Full | Core health monitoring |
| P0 | Operations Console | `/operations` | ✅ Full | Position/order supervision |
| P0 | Chart Browser | `/charts` | ✅ Full | Market analysis |
| P1 | Terminal Context | `/terminal` | ✅ Full | Critical trade_allowed status |
| P1 | Fast Desk View | `/fast-desk` | ⚠️ Partial | Execution disabled |
| P1 | SMC Desk View | `/smc` | ⚠️ Partial | Analysis-only |
| P2 | Risk Center | `/risk` | ⚠️ Partial | Roadmap for RiskKernel |
| P2 | Settings | `/settings` | ✅ Full | Symbol management |
| P3 | Symbol Catalog | `/catalog` | ✅ Full | Reference only |
| P3 | Event Log | `/events` | ✅ Full | SSE replay |

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-24  
**Author**: Senior Frontend Architect (AI-Assisted)  
**Reviewers**: Pending
