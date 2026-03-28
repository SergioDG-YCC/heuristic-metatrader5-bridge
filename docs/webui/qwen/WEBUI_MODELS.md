# WebUI Models — Heuristic MT5 Bridge

**Version**: 1.0.0  
**Date**: 2026-03-24  
**Target Framework**: Solid.js  
**Repository**: `heuristic-metatrader5-bridge`  
**Control Plane**: `http://0.0.0.0:8765`

---

## 1. Product Interpretation

This is **not** a generic admin panel. This is **not** the LLM office stack WebUI.

This WebUI is an **execution cockpit** for a heuristic-first, RAM-based MT5 bridge system with two independent desks:

| Desk | Latency | LLM | Purpose |
|------|---------|-----|---------|
| **Fast Desk** | Seconds | Never | Scalping/fast intraday, deterministic heuristics only |
| **SMC Desk** | Minutes | Optional (after heuristics) | Prepared setups, deeper thesis, LLM as final gate |

The system architecture is fundamentally different from `llm-metatrader5-bridge`:

- **No chairman → analyst → supervisor → trader → risk pipeline**
- **No disk-based runtime data bus** (RAM-first, HTTP-only external interface)
- **No LLM in Fast Desk hot path**
- **Control Plane HTTP API is the only external interface** (no direct SQLite access)
- **Multi-broker, multi-terminal from day one**

### Core Reality

The WebUI must reflect what **actually exists** in this repository:

| Component | Status |
|-----------|--------|
| **CoreRuntimeService** | ✅ Operational (market state, account, positions, orders) |
| **Control Plane HTTP** | ✅ Operational (`GET /status`, `/chart`, `/account`, `/positions`, `/exposure`, `/specs`, `/catalog`, `/subscribe`, `/events`) |
| **MT5Connector** | ✅ Certified (read + `send_execution_instruction` for market/limit/stop) |
| **Fast Desk** | ⚠️ Architecture present, execution interface incomplete (needs `modify_position_levels`, `close_position`, etc.) |
| **SMC Desk** | ⚠️ Scanner/analyst/validator present, trader not implemented |
| **OwnershipRegistry** | ❌ Not implemented (Phase 3) |
| **RiskKernel** | ❌ Not implemented (Phase 2) |
| **BridgeSupervisor** | ❌ Not implemented (Phase 1) |
| **Paper Mode** | ❌ Not implemented (Phase 4) |

---

## 2. Implemented Backend vs Planned Backend

### 2.1 Available Now (Control Plane HTTP)

| Endpoint | Method | Returns | UI Ready |
|----------|--------|---------|----------|
| `/status` | GET | Full live state: health, broker identity, universes, worker counts, account summary | ✅ |
| `/chart/{symbol}/{timeframe}` | GET | Chart context + candles from RAM | ✅ |
| `/specs` | GET | All symbol specifications | ✅ |
| `/specs/{symbol}` | GET | Single symbol spec | ✅ |
| `/account` | GET | Raw account payload (state + exposure + positions + orders) | ✅ |
| `/positions` | GET | `{ positions: [...], orders: [...] }` — individual MT5 records | ✅ |
| `/exposure` | GET | Aggregate exposure: gross/net volume + floating P&L per symbol | ✅ |
| `/catalog` | GET | Broker symbol catalog | ✅ |
| `/subscribe` | POST | Add symbol to subscribed universe | ✅ |
| `/unsubscribe` | POST | Remove symbol from subscribed universe | ✅ |
| `/events?interval=1.0` | GET | SSE stream of live state | ✅ |

### 2.2 Partially Available (Gaps Documented)

| Component | Status | Gap | UI Treatment |
|-----------|--------|-----|--------------|
| **MT5Connector Execution Surface** | ⚠️ Partial | `send_execution_instruction` works with `comment=""` only; `modify_position_levels`, `close_position`, `find_open_position_id` not exposed | Show execution buttons disabled with tooltip: "Execution surface under certification" |
| **Fast Desk** | ⚠️ Partial | Scanner/risk/policy exist; `FastExecutionBridge` calls non-existent methods (`place_order`, `modify_position`) | Show Fast Desk status panel with "Architecture present, execution interface incomplete" badge |
| **SMC Desk** | ⚠️ Partial | Scanner/analyst/validator exist; no trader implemented | Show SMC thesis panel (empty until trader implemented); mark "Trader pending" |
| **Trade Allowed Status** | ⚠️ Partial | `terminal_info.trade_allowed` observable but not exposed via API | Show warning if MT5 AutoTrading disabled (via `/status` health) |
| **Account Switch** | ⚠️ Partial | Route exists but can degrade MT5 session | Show danger alert: "Changing account may disrupt MT5 session" |

### 2.3 Not Available Yet (Planned Phases)

| Component | Planned Phase | UI Treatment |
|-----------|---------------|--------------|
| **BridgeSupervisor** | Phase 1 | Show as "Roadmap — Multi-terminal support" disabled panel |
| **RiskKernel (global + per-desk)** | Phase 2 | Show as "Roadmap — Global risk management" disabled panel |
| **OwnershipRegistry** | Phase 3 | Show as "Roadmap — Position ownership tracking" disabled panel |
| **FastTraderService** | Phase 3 | Show as "Roadmap — Fast Desk execution" disabled panel |
| **SmcTraderService** | Phase 3 | Show as "Roadmap — SMC Desk execution" disabled panel |
| **ExecutionReconciler** | Phase 3 | Show as "Roadmap — MT5 reconciliation" disabled panel |
| **Paper Mode** | Phase 4 | Show as "Roadmap — Simulation mode" disabled panel |
| **Execution Mode Split (live/paper)** | Phase 4 | Show current `account_mode` only; mark "execution_mode TBD" |

---

## 3. Information Architecture

### 3.1 Primary Navigation

```
/ (redirect to /dashboard)
├── /dashboard — Launch / Runtime Overview
├── /operations — Operations Console (positions, orders, exposure)
├── /fast-desk — Fast Desk View (status + signals, execution disabled)
├── /smc — SMC Desk View (zones, thesis, analysis-only)
├── /charts — Chart Browser (multi-symbol view)
├── /terminal — Terminal / Account Context
├── /risk — Risk Center (current state + roadmap)
├── /settings — Configuration (symbols, timeframes, env vars)
```

### 3.2 Secondary Navigation (Utility)

```
├── /catalog — Symbol Catalog Browser
├── /specs — Symbol Specifications Reference
├── /events — Event Log (SSE replay)
├── /health — System Health Detail
```

### 3.3 Route Guards

- All routes consume Control Plane HTTP only (`http://127.0.0.1:8765`)
- No authentication required (local trust boundary)
- Read-only vs Write-enabled:
  - **Read-only**: `/dashboard`, `/operations`, `/fast-desk`, `/smc`, `/charts`, `/catalog`, `/specs`, `/health`
  - **Write-enabled**: `/subscribe`, `/unsubscribe`, `/settings`

---

## 4. Screen Inventory

| Screen | Route | Purpose | Backend Dependency | Status |
|--------|-------|---------|-------------------|--------|
| **Launch Overview** | `/dashboard` | System health, feed status, runtime summary | `/api/status` | Implemented |
| **Operations Console** | `/operations` | Positions, orders, exposure detail | `/api/positions`, `/api/exposure`, `/api/account` | Implemented |
| **Fast Desk View** | `/fast-desk` | Signal flow, per-symbol state, execution status | `/api/status` (Fast Desk workers) | Partial (execution disabled) |
| **SMC Desk View** | `/smc` | Zone map, thesis status, analysis | `/api/status` (SMC scanner) | Partial (analysis-only) |
| **Chart Browser** | `/charts` | Multi-symbol chart view | `/api/chart/{symbol}/{tf}` | Implemented |
| **Risk Center** | `/risk` | Current risk state + roadmap | `/api/account`, `/api/status` | Partial |
| **Terminal Context** | `/terminal` | MT5 installation, broker, account, trade_allowed | `/api/status`, `/api/account` | Implemented |
| **Symbol Catalog** | `/catalog` | Broker symbol browser | `/api/catalog` | Implemented |
| **Symbol Specs** | `/specs` | Specification reference | `/api/specs` | Implemented |
| **Settings** | `/settings` | Configuration (symbols, timeframes) | `/api/subscribe`, `/api/unsubscribe` | Implemented |
| **Event Log** | `/events` | SSE event replay | `/api/events` | Implemented |
| **Health Detail** | `/health` | System health breakdown | `/api/status` | Implemented |

---

## 5. User Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| **Operator** | Primary user — supervises desks, monitors execution | Read all, Subscribe/Unsubscribe symbols |
| **Admin** | Configures environment, manages terminals | Read all, Write settings |
| **Auditor** | Read-only historical review | Read all (no writes) |

Current system assumes **single local operator** — no multi-user auth.

---

## 6. Component Inventory

### 6.1 Layout Components

```typescript
// src/components/layout/
- AppShell.tsx — Main layout with sidebar navigation
- TopBar.tsx — System status, account summary, trade_allowed indicator
- Sidebar.tsx — Navigation, desk status indicators
- ContentArea.tsx — Route content wrapper
- Panel.tsx — Reusable panel container
- PanelGrid.tsx — Responsive grid layout
- RoadmapPanel.tsx — "Coming Soon" placeholder for planned features
```

### 6.2 Data Display Components

```typescript
// src/components/data/
- StatusBadge.tsx — Health indicator (up/degraded/down)
- FeedHealthIndicator.tsx — Tick/bar age visualization (from chart RAM)
- PriceTicker.tsx — Live price from SSE
- KPICard.tsx — Metric display with trend
- DataTable.tsx — Sortable, filterable table
- CandlestickChart.tsx — TradingView Lightweight Charts
- PositionCard.tsx — Position summary with P&L
- OrderRow.tsx — Pending order detail
- ExposureRow.tsx — Per-symbol exposure breakdown
- DeskStatusCard.tsx — Fast/SMC Desk health summary
```

### 6.3 Control Components

```typescript
// src/components/controls/
- SymbolSelector.tsx — Symbol search + select
- TimeframeSelector.tsx — TF switcher (M1/M5/H1/H4/D1)
- SubscribeButton.tsx — Add symbol to universe
- UnsubscribeButton.tsx — Remove symbol from universe
- TradeAllowedIndicator.tsx — MT5 AutoTrading status (CRITICAL)
- AccountSwitchWarning.tsx — Danger alert for account change
```

### 6.4 Real-Time Components

```typescript
// src/components/realtime/
- SSEEventFeed.tsx — Live event stream
- PollingIndicator.tsx — Last update timestamp
- ConnectionStatus.tsx — API health monitor
```

### 6.5 Roadmap Components (Disabled/Preview)

```typescript
// src/components/roadmap/
- OwnershipPreview.tsx — Disabled ownership registry UI
- RiskKernelPreview.tsx — Disabled risk kernel UI
- FastDeskExecutionPreview.tsx — Disabled fast desk execution UI
- SmcTraderPreview.tsx — Disabled SMC trader UI
- PaperModePreview.tsx — Disabled simulation mode UI
```

---

## 7. API-to-Screen Mapping

| Screen | Primary API | Secondary APIs | SSE Streams |
|--------|-------------|----------------|-------------|
| `/dashboard` | `/status` | `/account`, `/catalog` | `/events` |
| `/operations` | `/positions` | `/account`, `/exposure` | `/events` |
| `/fast-desk` | `/status` (fast_desk_workers) | — | — |
| `/smc` | `/status` (smc_scanner) | — | — |
| `/charts` | `/chart/{symbol}/{tf}` | `/specs/{symbol}` | `/events` |
| `/risk` | `/account` | `/status` | — |
| `/terminal` | `/status` | `/account` | — |
| `/catalog` | `/catalog` | — | — |
| `/specs` | `/specs` | — | — |
| `/settings` | `/subscribe`, `/unsubscribe` | `/catalog` | — |
| `/events` | `/events` | — | N/A |
| `/health` | `/status` | — | — |

---

## 8. Startup Flow

### 8.1 Application Initialization

```typescript
// src/main.tsx
1. Render AppShell skeleton
2. Initialize API client (baseURL: http://127.0.0.1:8765)
3. Fetch `/status` (health check)
4. If healthy:
   - Initialize SSE connections
   - Load initial data for current route
   - Start polling intervals (configurable per screen)
5. If unhealthy:
   - Show connection error panel
   - Retry with exponential backoff
```

### 8.2 Route Loading Strategy

```typescript
// src/routes/Dashboard.tsx
1. On mount:
   - Fetch `/status`
   - Fetch `/account`
   - Fetch `/catalog`
2. Subscribe to `/events?interval=1.0` SSE
3. Set up polling (5s default for runtime state)
4. On unmount:
   - Close SSE connection
   - Clear polling interval
```

### 8.3 SSE Connection Management

```typescript
// src/lib/sse.ts
- Single connection per stream type
- Auto-reconnect with backoff (1s, 2s, 4s, 8s, max 30s)
- Event deduplication by event_id
- Buffer last 100 events for replay on reconnect
```

---

## 9. Loading / Error / Empty States

### 9.1 Loading States

| Component | Loading UI |
|-----------|------------|
| DataTable | Skeleton rows (3-5 rows) |
| KPICard | Pulsing placeholder |
| Chart | Spinner + "Loading chart..." |
| Panel | Skeleton header + content lines |

**Rule**: Never show blank screen. Always show skeleton or spinner.

### 9.2 Error States

| Error Type | UI Treatment |
|------------|--------------|
| API Unavailable | Full-screen "Backend Offline" panel with retry |
| Single Endpoint Failure | Panel-level error with "Retry" button |
| SSE Disconnect | Toast notification + auto-reconnect indicator |
| Invalid Data | Show partial data, highlight invalid fields |

### 9.3 Empty States

| Scenario | Empty State UI |
|----------|----------------|
| No positions | "No open positions" + illustration |
| No SMC zones | "No SMC zones detected" + scanner status |
| No Fast signals | "No signals in cooldown" + scan interval |
| No catalog | "Symbol catalog not loaded" + refresh button |

---

## 10. Representing Live vs Planned Capabilities

### 10.1 Visual Indicators

| Status | Badge | Treatment |
|--------|-------|-----------|
| **Live** | Green "OPERATIONAL" | Full functionality |
| **Partial** | Yellow "PARTIAL" | Enabled with tooltip explaining gaps |
| **Analysis-Only** | Blue "ANALYSIS" | View-only, execution disabled |
| **Roadmap** | Gray "COMING SOON" | Disabled panel with description |

### 10.2 Feature Flags

```typescript
// src/config/features.ts
export const FEATURES = {
  FAST_DESK_EXECUTION: false,    // Execution interface incomplete
  SMC_TRADER: false,             // Not implemented
  OWNERSHIP_REGISTRY: false,     // Phase 3
  RISK_KERNEL: false,            // Phase 2
  PAPER_MODE: false,             // Phase 4
  MULTI_TERMINAL: false,         // Phase 1
};
```

### 10.3 Roadmap Panel Pattern

```tsx
// src/components/roadmap/RoadmapPanel.tsx
<RoadmapPanel
  title="RiskKernel"
  description="Global and per-desk risk management"
  plannedPhase="Phase 2"
  details={[
    "Global risk profile (1-4)",
    "Per-desk budget allocation",
    "Kill switch (global + per-desk)",
    "Dynamic exposure limits"
  ]}
/>
```

---

## 11. Visualizing Key Concepts

### 11.1 Terminals

**Current**: Single terminal (one CoreRuntimeService instance)

```
Terminal Panel:
├── Terminal ID: default
├── Broker Company: "FBS Ltd."
├── Broker Server: "FBS-Demo"
├── Account Login: 105845678
├── Terminal Path: C:\Program Files\...
├── Trade Allowed: ● Yes (AutoTrading enabled)
└── Connection: ● Connected
```

**Future (Phase 1)**: Multi-terminal via BridgeSupervisor

```
Terminal Selector:
├── Terminal 1: FBS-Demo :105845678 (Active)
├── Terminal 2: ICMarkets :987654 (Inactive)
└── + Add Terminal (Roadmap)
```

### 11.2 Brokers

```
Broker Card:
├── Broker Name: FBS Ltd.
├── Server: "FBS-Demo"
├── Account Login: 105845678
├── Account Mode: DEMO | REAL | CONTEST
├── Currency: USD
├── Leverage: 1:100
├── Balance: $10,000
├── Equity: $10,250
└── Drawdown: 2.5%
```

### 11.3 Accounts

```
Account Summary:
├── Login: 105845678
├── Mode: DEMO
├── Currency: USD
├── Balance: $10,000
├── Equity: $10,250
├── Free Margin: $8,500
├── Open Positions: 5
├── Pending Orders: 1
└── Floating P&L: +$250
```

### 11.4 Desks

```
Desk Status:
├── Fast Desk
│   ├── Status: ● Running (FAST_DESK_ENABLED=true)
│   ├── Workers: 5 (one per symbol)
│   ├── Scan Interval: 5s
│   ├── Custody Interval: 2s
│   ├── Signals (last hour): 0
│   └── Execution: ⚠️ Interface incomplete
├── SMC Desk
│   ├── Status: ● Running (SMC_SCANNER_ENABLED=true)
│   ├── LLM Validator: ● Enabled
│   ├── Zones Detected: 0
│   ├── Active Thesis: 0
│   └── Trader: ❌ Not implemented
```

### 11.5 Positions

```
Position Card:
├── Symbol: EURUSD
├── Side: BUY ●
├── Volume: 0.10
├── Entry: 1.0850
├── Current: 1.0862
├── SL: 1.0800
├── TP: 1.0950
├── P&L: +$12.00
├── Swap: -$0.30
├── Commission: -$1.00
├── Comment: ti:f8b0ea45|ex:f
├── Opened: 2026-03-24 02:29
└── [Close] [Modify] (disabled until execution surface complete)
```

**Note**: Comment format `ti:<id>|ex:<id>` indicates positions originated from `llm-metatrader5-bridge` execution bridge, not current heuristic bridge.

### 11.6 Orders

```
Order Row:
├── Symbol: BTCUSD
├── Type: Buy Limit
├── Volume: 0.05
├── Price: 68000
├── SL: 67000
├── TP: 72000
├── Status: Working
├── Created: 2026-03-24 02:48
└── [Cancel] [Modify] (disabled until execution surface complete)
```

### 11.7 Exposure

```
Exposure Summary:
├── Gross Exposure: 0.45 lots
├── Net Exposure: 0.25 lots
├── Floating P&L: +$250.00
├── Used Margin: $1,500
├── Free Margin: $8,500
└── Per Symbol:
    ├── EURUSD: +0.20 (Long) | +$24.00
    ├── GBPUSD: -0.10 (Short) | +$6.00
    └── BTCUSD: +0.15 (Long) | +$220.00
```

### 11.8 Feed Health

**Note**: Current architecture stores candles in RAM only. Feed health is inferred from chart update timestamps, not persisted metrics.

```
Feed Status Panel:
├── Symbol: EURUSD
├── Timeframe: M5
├── Last Bar: 2026-03-24 14:25:00 UTC
├── Bar Age: 45s ● Green
├── Poll Interval: 5s
└── Worker: ● Active
```

**Alert Thresholds**:
- Bar Age > timeframe + 30s: Warning
- Chart worker not updating: Error

### 11.9 Trade Allowed Status (CRITICAL)

```
Trade Allowed Indicator:
├── Status: ● AutoTrading Enabled
├── Terminal: trade_allowed = true
└── All execution paths: OPEN

OR

├── Status: ⚠️ AutoTrading Disabled
├── Terminal: trade_allowed = false
├── Warning: "All MT5 write operations blocked"
└── Recovery: "Enable AutoTrading in MT5 terminal"
```

**Rule**: If `trade_allowed = false`, ALL execution buttons must be disabled with tooltip explaining recovery steps.

### 11.10 Risk (Current vs Planned)

**Current** (from FastRiskEngine):
```
Risk Panel:
├── Per-Trade Risk: 1.0% (FAST_DESK_RISK_PERCENT)
├── Max Positions/Symbol: 1
├── Max Positions Total: 4
├── Drawdown Guard: Active
└── Lot Sizing: Automatic (balance × risk% / SL_pips × pip_value)
```

**Planned (RiskKernel — Phase 2)**:
```
Risk Kernel Panel (Roadmap):
├── Global Profile: [2 - Medium ▼]
├── Global Max Drawdown: 3.5%
├── Fast Desk Budget: 50% ($175/day)
├── SMC Desk Budget: 50% ($175/day)
├── Kill Switch: ● Armed (not tripped)
├── Circuit Breakers:
│   ├── Daily Loss: Active
│   ├── Consecutive Losses: Active
│   └── Volatility Spike: Active
└── [Configure] [Override]
```

### 11.11 Account Switch Warning

```
⚠️ DANGER: Account Switch May Disrupt MT5 Session

Changing or probing another account can:
• Degrade the active MT5 terminal session
• Disable AutoTrading (trade_allowed = false)
• Require manual recovery in MT5

Recovery steps if authentication fails:
1. Re-enable AutoTrading in MT5 terminal
2. Relaunch apps/control_plane.py if services crashed

[ I Understand — Proceed Anyway ]  [ Cancel ]
```

---

## 12. Solid.js Implementation Notes

### 12.1 State Management

```typescript
// src/stores/
- runtimeState.ts — Core runtime health (from /status)
- accountState.ts — Account + exposure + positions + orders
- chartState.ts — Chart data per symbol/timeframe
- catalogState.ts — Symbol catalog
- uiState.ts — UI preferences
```

**Pattern**: Use `createStore` for nested state, `createSignal` for primitives.

### 12.2 Real-Time Updates

```typescript
// src/hooks/useSSE.ts
export function useSSE<T>(
  endpoint: string,
  onEvent: (data: T) => void
) {
  // Manage EventSource lifecycle
  // Auto-reconnect with backoff
  // Event deduplication
}
```

### 12.3 Polling Pattern

```typescript
// src/hooks/usePolling.ts
export function usePolling(
  queryFn: () => Promise<void>,
  intervalMs: number,
  enabled: boolean
) {
  // Poll with visibility API awareness
  // Pause when tab is hidden
  // Resume on visibility change
}
```

### 12.4 Component Composition

```tsx
// Example: Dashboard Screen
<Dashboard>
  <PanelGrid>
    <Panel title="System Health">
      <StatusBadge status={health.status} />
    </Panel>
    <Panel title="Account Summary">
      <AccountSummary data={accountState} />
    </Panel>
    <Panel title="Desk Status">
      <DeskStatusCard fast={fastStatus} smc={smcStatus} />
    </Panel>
  </PanelGrid>
  <Panel title="Feed Health">
    <FeedHealthTable data={feedStatus} />
  </Panel>
</Dashboard>
```

---

## 13. Mobile Degradation

This is a **desktop-first** trading cockpit. Mobile is secondary.

| Screen | Desktop | Tablet | Mobile |
|--------|---------|--------|--------|
| Dashboard | Full grid | 2-column | Stacked cards |
| Operations | Full table | Scrollable table | List view |
| Charts | Multi-chart grid | Single chart | Chart only (no sidebar) |
| Risk | Full gauges | Simplified | Summary only |
| Terminal | Full detail | Condensed | Key info only |

**Rule**: Never hide critical data on mobile — reflow only.

---

## 14. Critical Operator Alerts

The WebUI must prominently display these alerts based on backend state:

### 14.1 Trade Allowed Disabled

```
🔴 CRITICAL: AutoTrading Disabled

MT5 terminal has trade_allowed = false.

All execution operations are blocked:
• Opening positions
• Modifying SL/TP
• Closing positions
• Canceling orders

Recovery:
1. Open MT5 terminal
2. Enable AutoTrading button
3. Verify trade_allowed = true
4. Relaunch control plane if needed

[Dismiss]
```

### 14.2 Account Switch Disrupted Session

```
⚠️ WARNING: Account Switch May Have Failed

Authentication to the new account failed.
This may have degraded your MT5 session.

Symptoms:
• AutoTrading disabled
• Terminal authorization failed
• Services unresponsive

Recovery:
1. Re-enable AutoTrading in MT5
2. Relaunch apps/control_plane.py
3. Verify /status endpoint responds

[Dismiss]
```

### 14.3 Execution Interface Incomplete

```
⚠️ NOTICE: Execution Interface Under Certification

The Fast Desk architecture is complete, but the MT5 execution
surface is still being certified.

Currently available:
• send_execution_instruction (market/limit/stop) with comment=""

Pending certification:
• modify_position_levels
• modify_order_levels
• remove_order
• close_position
• find_open_position_id

Execution buttons are disabled until certification completes.
```

---

## 15. Summary: What This UI Is and Is Not

### This UI IS:
- An execution cockpit for heuristic-first trading
- A real-time supervision console for RAM-based market state
- A desk operations board for Fast + SMC strategies
- A control surface for account/exposure monitoring
- Tightly coupled to Control Plane HTTP API only
- Honest about what's implemented vs planned

### This UI IS NOT:
- The LLM office stack UI (chairman/supervisor/trader/risk)
- A generic SaaS admin panel
- A retail trading app
- A crypto portfolio tracker
- A disk-based runtime observer
- A direct SQLite reader

---

## 16. Next Steps

1. Review this document with backend team
2. Validate API contracts for each screen
3. Create wireframe specifications (WEBUI_WIREFRAME_SPEC.md)
4. Define visual direction (WEBUI_VISUAL_DIRECTION.md)
5. Generate image prompts for stakeholder review (WEBUI_IMAGE_PROMPTS.md)
6. Begin Solid.js scaffolding

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-24  
**Author**: Senior Frontend Architect (AI-Assisted)  
**Reviewers**: Pending
