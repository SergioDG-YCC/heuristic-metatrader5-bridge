# WebUI Image Generation Prompts

**Version**: 1.0.0  
**Date**: 2026-03-24  
**Repository**: `heuristic-metatrader5-bridge`  
**Purpose**: Stakeholder reference images for WebUI design direction

---

## How to Use These Prompts

These prompts are designed for AI image generation tools (Midjourney, DALL-E 3, Stable Diffusion) to create visual reference mockups for stakeholder review.

Each prompt describes:
- Screen composition
- Information density
- Mood and atmosphere
- Color palette
- Visible UI elements
- What to avoid

**Note**: These are reference images, not pixel-perfect mockups. The goal is to communicate the design direction to stakeholders before implementation.

---

## Master Moodboard Prompt

### Prompt 1: Overall Design Direction

```
Professional trading terminal dashboard UI, dark mode, heuristic-first MT5 bridge system.

COMPOSITION: Multi-panel grid layout on dark charcoal background (#0d1117). Four main KPI panels in top row: Market State status, Account Summary, Fast Desk status, SMC Desk status. Below: Feed Health table showing 5 symbols with bar age indicators. Bottom: Recent SSE event feed.

INFORMATION DENSITY: High but organized. Dense numeric data in monospace fonts (JetBrains Mono), panel titles in clean sans-serif (Inter). No empty whitespace, every pixel serves a purpose. Tables with 5-7 rows visible, each row showing symbol, timeframe, last bar time, age with colored dot.

MOOD: Serious, professional, institutional. Feels like a Bloomberg terminal met modern developer tools. No playfulness, no gamification. Calm confidence under pressure. Trading cockpit for heuristic-first trading with two desks (Fast + SMC).

COLOR PALETTE: Dark neutral base (charcoal #0d1117, gunmetal #161b22). Accent colors are functional only: green (#3fb950) for profit/healthy/live, red (#f85149) for loss/critical/blocked, yellow (#d29922) for warning, blue (#58a6ff) for info, purple (#a371f7) for SMC desk identity. No gradients, no rainbow effects.

VISIBLE ELEMENTS:
- Top bar with system status badge ("● LIVE" in green), account summary ("105845678 | $10,250"), timestamp
- KPI Card 1: "MARKET STATE — ● Up, 5 Symbols, 5 Workers"
- KPI Card 2: "ACCOUNT — Bal: $10K, Equ: $10.2K, DD: 2.1%, Positions: 5"
- KPI Card 3: "FAST DESK — ● Running, 5 Workers, Scan: 5s, Execution: ⚠️ Incomplete"
- KPI Card 4: "SMC DESK — ● Running, Scanner Active, LLM: Enabled, Trader: Pending"
- Trade Allowed banner: "● AutoTrading Enabled — All execution paths OPEN"
- Feed table: "BTCUSD | M5,H1,H4 | 14:25:00 UTC | 45s ● | Active"
- Event feed: "[14:28:00] System Account refreshed | [14:27:55] Market BTCUSD M5 updated"

WHAT TO AVOID:
- No white backgrounds
- No purple gradients
- No emoji icons
- No "Good morning, Trader!" greetings
- No confetti or celebration graphics
- No cartoon illustrations
- No generic "AI-powered" badges
- No Robinhood-style gamification
- No crypto moon/rocket imagery
- No LLM office stack elements (chairman/analyst/supervisor cards)

STYLE REFERENCES: GitHub dark mode, Bloomberg terminal, Linear app, Grafana dashboards, professional prop trading desks.

RENDER: Desktop screen, slight angle, dark room with monitor glow. Photorealistic UI on screen.
```

---

## Screen-Specific Prompts

### Prompt 2: Launch / Runtime Overview

```
Trading system launch dashboard, dark mode, real-time market monitoring interface for heuristic MT5 bridge.

COMPOSITION: Single screen divided into distinct panels. Top: system status bar spanning full width. Middle: 4 KPI cards in a row (Market State, Account Summary, Fast Desk Status, SMC Desk Status). Below that: Trade Allowed status banner (critical). Then: Feed Health table (5 symbols). Bottom: Recent Events feed (SSE stream).

INFORMATION DENSITY: High. Feed table shows 5 symbols (BTCUSD, EURUSD, GBPUSD, USDJPY, USDCHF) with columns: Symbol, Timeframes, Last Bar Time, Age with colored dot, Worker Status. Desk status cards show worker counts, scan intervals, execution status.

MOOD: Calm control center. Everything is monitored, everything is visible. Operator can assess system health in 3 seconds. No panic, no clutter. Professional supervision of RAM-based market state.

COLOR PALETTE:
- Background: #0d1117, #161b22 (panels)
- Borders: #30363d
- Text: #e6edf3 (primary), #8b949e (secondary)
- Status green: #3fb950 (live badge, healthy feed)
- Warning yellow: #d29922 (incomplete execution)
- Danger red: #f85149 (critical alerts)
- Info blue: #58a6ff (info badges)
- SMC purple: #a371f7 (SMC desk identity)

VISIBLE ELEMENTS:
- System status badge: "● LIVE" (green pulsing dot)
- Account: "105845678 | $10,250 | DD: 2.1%"
- KPI Card 1: "MARKET STATE — ● Up, 5 Symbols, 5 Chart Workers"
- KPI Card 2: "ACCOUNT — Bal: $10K, Equ: $10.2K, DD: 2.1%, Positions: 5"
- KPI Card 3: "FAST DESK — ● Running (FAST_DESK_ENABLED=true), 5 Workers, Scan: 5s, Custody: 2s, Execution: ⚠️ Interface Incomplete"
- KPI Card 4: "SMC DESK — ● Running (SMC_SCANNER_ENABLED=true), Scanner Active, LLM Validator: Enabled, Zones: 0, Thesis: 0, Trader: ❌ Pending"
- Trade Allowed banner: "● AutoTrading Enabled — All execution paths are OPEN. MT5 terminal is ready." (green border)
- Feed table rows: "BTCUSD | M5,H1,H4 | 14:25:00 UTC | 45s ● Green | Active", "EURUSD | M5,H1,H4 | 14:25:00 UTC | 42s ● Green | Active"
- Events: "[14:28:00] System Account state refreshed (2s interval)", "[14:27:55] Market BTCUSD M5 bar updated", "[14:27:50] Fast Symbol worker scan completed (5 symbols)"

TYPOGRAPHY: Panel titles in Inter Semi-Bold 16px. Data in JetBrains Mono 13px. Labels in Inter 12px uppercase with letter-spacing.

WHAT TO AVOID:
- No large hero images
- No empty state illustrations
- No decorative icons
- No gradient backgrounds
- No rounded corners >6px
- No shadows except on modals
- No LLM role conversation bubbles

RENDER: Full desktop screen (1920x1080), straight-on view, UI fills frame.
```

---

### Prompt 3: Operations Console

```
Professional trading operations console, position management interface, dark trading terminal for heuristic MT5 bridge.

COMPOSITION: Top section shows exposure summary bar (Gross/Net exposure, Floating P&L, Position/Order counts). Main section: Open Positions table (5 positions visible). Below: Pending Orders table (1 order). Bottom: Execution Notice banner explaining disabled buttons.

INFORMATION DENSITY: Very high in tables. Each position row shows: Symbol, Side badge (BUY/SELL), Volume, Entry Price, Current Price, P&L (color-coded), SL, TP, Comment (ownership hint), Opened timestamp, Action buttons ([Close] [Modify] disabled). Numbers aligned in monospace columns.

MOOD: Active trading desk. Positions are being monitored, decisions happening. Operator needs full visibility into every open risk. Serious, focused, no distractions. Note: Execution buttons are disabled due to incomplete MT5 surface.

COLOR PALETTE:
- Background: #0d1117, #161b22 (panels)
- Profit green: #3fb950 (positive P&L, buy side badge)
- Loss red: #f85149 (negative P&L, sell side badge)
- Warning yellow: #d29922 (execution incomplete notice)
- Border accent: Position cards have left border colored by desk (green for Fast, purple for SMC)

VISIBLE ELEMENTS:
- Exposure bar: "Gross: 0.45 lots | Net: 0.25 lots | Floating: +$250 | Positions: 5 | Orders: 1 | Margin Used: $1,500"
- Position row 1: "EURUSD | BUY ● | 0.10 | 1.0850 | 1.0862 | +$12.00 | SL: 1.0800 | TP: 1.0950 | Comment: ti:xxx | Opened: 02:29 UTC | [Close] [Modify] (disabled, gray)"
- Position row 2: "EURUSD | BUY ● | 0.10 | 1.0845 | 1.0862 | +$17.00 | SL: 1.0800 | TP: 1.0950 | Comment: ti:yyy | Opened: 02:36 UTC"
- Position row 3: "GBPUSD | SELL ● | 0.10 | 1.2640 | 1.2634 | +$6.00 | SL: 1.2680 | TP: 1.2550 | Comment: ti:zzz | Opened: 02:50 UTC"
- Position row 4: "BTCUSD | BUY ● | 0.15 | 68500 | 69200 | +$105.00 | SL: 67500 | TP: 72000 | Comment: ti:aaa | Opened: 02:40 UTC"
- Position row 5: "BTCUSD | BUY ● | 0.05 | 68800 | 69200 | +$20.00 | SL: 67800 | TP: 72000 | Comment: ti:bbb | Opened: 02:45 UTC"
- Order row: "BTCUSD | Buy Limit | 0.05 | 68000 | SL: 67000 / TP: 72000 | Comment: ti:ccc | Created: 02:48 UTC | 42m | [Cancel] (disabled)"
- Execution Notice banner: "⚠️ Execution buttons disabled: MT5 execution surface under certification. modify_position_levels, close_position, and related methods pending implementation." (yellow background)

INTERACTION CUES:
- Table rows have subtle hover state (lighter background #21262d)
- Action buttons are minimal (text only, no icons), disabled with gray color
- P&L values are bold and color-coded (green/red)
- Comment field shows ownership hints (ti: format from previous system)

TYPOGRAPHY: All prices and numbers in JetBrains Mono tabular-nums. Symbol names in Inter Medium. Side badges in Inter Bold uppercase.

WHAT TO AVOID:
- No position size visualization (pie charts, etc.)
- No P&L history charts in this view
- No emoji for buy/sell
- No large action buttons
- No confirmation modals visible
- No enabled execution buttons (must show disabled state)

RENDER: Desktop screen, focus on table area. Show 5 position rows clearly. Execution notice banner visible at bottom.
```

---

### Prompt 4: Fast Desk View

```
High-speed execution desk interface, heuristic-first trading terminal, PARTIAL/ROADMAP state.

COMPOSITION: Top: Fast Desk status banner with architecture/execution status. Main section: Symbol Workers table (5 workers). Below: Execution Interface Status panel (showing available vs pending methods). Then: Risk Config panel. Bottom: Roadmap panel for FastTraderService (Phase 3).

INFORMATION DENSITY: Conceptual but honest. Shows what the desk DOES display: worker status, last scan times, cooldown state, signal counts. All execution-related UI clearly marked as incomplete.

MOOD: Technical, transparent, waiting. This is a powerful architecture waiting for certified execution surface. Operator can see the machinery running but understands execution is disabled. No fake functionality.

COLOR PALETTE:
- Same dark base (#0d1117, #161b22)
- Fast desk accent: #3fb950 (green)
- Warning yellow: #d29922 (execution incomplete)
- Roadmap gray: #484f58 (disabled sections)

VISIBLE ELEMENTS:
- Status banner: "FAST DESK STATUS — ● Running (FAST_DESK_ENABLED=true) | Architecture: ✅ Complete | Execution: ⚠️ Interface Incomplete | Workers: 5 active | Scan: 5s | Custody: 2s"
- Worker table: "BTCUSD | ● Active | 14:28:00 | None | 0 (1h)", "EURUSD | ● Active | 14:28:00 | None | 0 (1h)", "GBPUSD | ● Active | 14:28:00 | None | 0 (1h)", "USDJPY | ● Active | 14:28:00 | None | 0 (1h)", "USDCHF | ● Active | 14:28:00 | None | 0 (1h)"
- Execution Interface Status panel: "AVAILABLE: ✅ send_execution_instruction (market/limit/stop, comment="") | PENDING: ❌ modify_position_levels, ❌ modify_order_levels, ❌ remove_order, ❌ close_position, ❌ find_open_position_id | Impact: Execution buttons disabled until certification complete"
- Risk Config: "Risk Per Trade: 1.0% | Max Positions/Symbol: 1 | Max Positions Total: 4 | Drawdown Guard: Active | Lot Sizing: balance × risk% / SL_pips × pip_value"
- Roadmap panel: "ROADMAP: FastTraderService (Phase 3) | Planned capabilities: Real execution via certified MT5 surface, Position custody (trail SL, lock profit, hard cut), Pending order management, Spread/slippage gates, Ownership tracking"

ROADMAP OVERLAY TEXT:
- "Architecture complete, execution interface under certification"
- "Expected capabilities after Phase 3:"
- "• Real MT5 execution (open, modify, close)"
- "• Position-level custody workers"
- "• Deterministic heuristics only (no LLM)"
- "• Max 4 positions total, R:R ≥ 1:4"

WHAT TO AVOID:
- No neon cyberpunk aesthetics
- No matrix-style falling code
- No "AI BRAIN" visualizations
- No speed lines or motion blur effects
- No "BETA" or "ALPHA" badges (use "INCOMPLETE" or "ROADMAP")
- No enabled execution buttons

RENDER: Desktop screen with execution status panel clearly visible. Show both the working architecture and the incomplete execution surface honestly.
```

---

### Prompt 5: SMC Desk View

```
SMC (Smart Money Concepts) desk interface, analysis-only mode, heuristic-first trading terminal.

COMPOSITION: Top: SMC Desk status bar with scanner/analyst/LLM/trader status. Main section: Zone Detection table (5 symbols, all showing 0 zones). Below: Active Thesis panel (empty state). Then: Trader Status panel (not implemented). Bottom: SMC Detection Pipeline diagram.

INFORMATION DENSITY: Analysis-focused. Shows scanner is running but no setups detected yet. Clearly marks trader as pending. Educational pipeline diagram shows the full detection flow.

MOOD: Analytical, prepared, patient. This is slower than Fast Desk — more deliberate. Operator is monitoring for confluences, waiting for setups. No execution pressure (analysis-only mode).

COLOR PALETTE:
- Chart background: #0d1117 (darker than panels)
- SMC desk accent: #a371f7 (purple)
- Warning yellow: #d29922 (pending trader)
- Roadmap gray: #484f58 (disabled sections)

VISIBLE ELEMENTS:
- Status bar: "SMC DESK STATUS — ● Running (SMC_SCANNER_ENABLED=true) | Scanner: ✅ Active | Analyst: ✅ Heuristic | LLM Validator: ✅ Enabled | Zones Detected: 0 | Active Thesis: 0 | Trader: ❌ Not Implemented"
- Zone Detection table: "Symbol | OB Bull | OB Bear | FVG | Liquidity | Confidence" with rows: "BTCUSD | 0 | 0 | 0 | 0 | —", "EURUSD | 0 | 0 | 0 | 0 | —", "GBPUSD | 0 | 0 | 0 | 0 | —", "USDJPY | 0 | 0 | 0 | 0 | —", "USDCHF | 0 | 0 | 0 | 0 | —" and note: "No zones detected in current session"
- Active Thesis panel: "No active thesis. Scanner is running but no setups detected. Thesis will appear here when: 1. Scanner detects confluences (OB + FVG + liquidity), 2. Heuristic analyst builds bias + scenario, 3. Heuristic validator passes confidence threshold, 4. LLM validator confirms (if SMC_LLM_ENABLED=true)"
- Trader Status panel: "TRADER STATUS — ❌ Not Implemented | The SMC Trader component is planned for Phase 3. Planned capabilities: Convert thesis to execution plans, Emit market/limit/stop orders, Manage pending orders, Slow deliberate custody (vs Fast Desk), Re-evaluation on thesis invalidation"
- SMC Detection Pipeline diagram: "Candles → Structure → OB → FVG → Liquidity → Fibonacci → Elliott → Confluences → Analyst → Validator → (LLM) → Thesis" with note: "Current status: Pipeline active, no setups meeting thresholds"

WHAT TO AVOID:
- No M5/M15 candles (wrong timeframe for SMC — this is H4/D1 analysis)
- No indicator clutter (RSI, MACD, etc.)
- No volume histogram
- No drawing tools visible (this is view-only)
- No "SMC Academy" style educational labels
- No fake zones or thesis (show empty state honestly)

RENDER: Desktop screen with zone detection table and trader status panel clearly visible. Show honest empty state.
```

---

### Prompt 6: Chart Browser

```
Multi-symbol chart browser, candlestick visualization from RAM, dark trading terminal.

COMPOSITION: Top: Chart controls (symbol selector, timeframe selector, bars input, load button, last bar timestamp). Main: Large candlestick chart (TradingView Lightweight Charts). Below: Chart Context JSON panel. Optional: Multi-chart grid preview at bottom.

INFORMATION DENSITY: Chart-heavy with 200 candles visible. Clean chart with no indicator clutter. Chart context shows structure data (trend, swings, phase). Last bar timestamp with age indicator.

MOOD: Analytical, focused, data-rich. This is the primary market analysis screen. Operator can see price action clearly with structural context.

COLOR PALETTE:
- Chart background: #0d1117 (darker than panels)
- Candlestick up: #3fb950 (green)
- Candlestick down: #f85149 (red)
- Grid lines: #21262d (subtle)
- Text: #8b949e (secondary)
- Panel borders: #30363d

VISIBLE ELEMENTS:
- Chart header: "Symbol: [BTCUSD ▼] | Timeframe: [M5 ▼] | Bars: [200] | [Load Chart] | Last Bar: 14:25:00 UTC (45s ago) ● Green"
- Candlestick chart with 200 bars showing BTCUSD M5 price action, current price line at $69,200
- Chart controls: "[Zoom] [Pan] [Crosshair] | Timeframes: M1 M5 H1 H4 D1"
- Chart Context panel: "Structure: { trend: bullish, last_swing_high: 69500, last_swing_low: 68000, phase: expansion }"
- Multi-chart grid preview: Three small charts showing "BTCUSD M5 | 69,200 ● | +0.5%", "EURUSD M5 | 1.0862 ● | +0.1%", "GBPUSD M5 | 1.2634 ● | -0.05%"

CHART DETAILS:
- M5 candles visible (200 bars)
- Current price line with label
- Grid lines subtle (#21262d)
- No indicator overlays (clean price action)
- Volume histogram optional (not shown)

WHAT TO AVOID:
- No SMC zone overlays (not implemented yet)
- No indicator clutter (RSI, MACD, Bollinger Bands)
- No drawing tools visible
- No fake annotations
- No watermark or branding on chart

RENDER: Desktop screen with chart as focal point. Show chart controls, candlestick chart, and chart context panel clearly.
```

---

### Prompt 7: Risk Center

```
Risk management console, FastRiskEngine view with RiskKernel roadmap, dark trading terminal.

COMPOSITION: Top: Risk Center status banner (Partial — FastRiskEngine Only). Main sections stacked vertically: Fast Desk Risk Config panel, Account Exposure summary, Per-Symbol Exposure table, RiskKernel Roadmap panel.

INFORMATION DENSITY: High numeric density. Exposure table shows: Symbol, Net Volume, Gross Volume, Floating P&L, Risk in Flight. RiskKernel roadmap shows planned profiles (Low/Medium/High/Chaos) with concrete numbers.

MOOD: Risk-aware, controlled, protective. This is the safety layer of the trading system. Operator can see current limits and understand what's planned. Honest about what's missing (no kill switch, no budget allocator).

COLOR PALETTE:
- Risk Low (green): #3fb950
- Risk Medium (yellow): #d29922
- Risk High (red): #f85149
- Risk Critical (bright red): #ff7b72
- Roadmap gray: #484f58

VISIBLE ELEMENTS:
- Status banner: "RISK CENTER — ⚠️ Partial (FastRiskEngine Only) | Current: FastRiskEngine (per-trade sizing) | Planned: RiskKernel (global + per-desk budgets) — Phase 2"
- Fast Desk Risk Config: "Risk Per Trade: 1.0% | Max Positions/Symbol: 1 | Max Positions Total: 4 | Drawdown Guard: Active | Lot Sizing: balance × risk% / SL_pips × pip_value"
- Account Exposure: "Gross Exposure: 0.45 lots | Net Exposure: 0.25 lots | Floating P&L: +$250 | Used Margin: $1,500 | Free Margin: $8,500 | Margin Level: 683%"
- Per-Symbol Exposure table: "EURUSD | +0.20 | 0.20 | +$34.00 | $20.00", "GBPUSD | -0.10 | 0.10 | +$6.00 | $8.00", "BTCUSD | +0.15 | 0.20 | +$210.00 | $150.00"
- RiskKernel Roadmap panel: "RISKKERNEL ROADMAP (Phase 2) | Planned capabilities: Global risk profile (1-4: Low/Medium/High/Chaos), Per-desk budget allocation (Fast vs SMC weights), Kill switch (global + per-desk), Dynamic exposure limits, Circuit breakers (daily loss, consecutive losses), Real-time guard interval | Default profiles (conceptual): Low: max_drawdown=2%, per_trade=0.30%, max_positions=3 | Medium: max_drawdown=3.5%, per_trade=0.50%, max_positions=5 | High: max_drawdown=5%, per_trade=0.75%, max_positions=10 | Chaos: max_drawdown=15%, per_trade=2%, max_positions=20"

WHAT TO AVOID:
- No risk matrix (2x2 grids)
- No VaR visualizations
- No Monte Carlo simulation charts
- No "risk appetite" spider charts
- No corporate risk management aesthetics
- No enabled kill switch toggle (not implemented)

RENDER: Desktop screen with exposure table and RiskKernel roadmap clearly visible. Show honest distinction between current (FastRiskEngine) and planned (RiskKernel).
```

---

### Prompt 8: Terminal / Account Context

```
MT5 terminal information screen, broker and account details, critical AutoTrading status, dark trading terminal.

COMPOSITION: Top: Terminal Context status bar with AutoTrading warning. Main sections stacked vertically: MT5 Terminal panel, Account Details panel, Account Switch Warning panel (danger styling), Symbol Watchlist panel.

INFORMATION DENSITY: Moderate. This is reference information, not real-time data. Terminal panel shows: Terminal Name, Path, Broker Company, Broker Server, Connection status, Trade Allowed status (CRITICAL). Account panel shows: Login, Mode, Currency, Leverage, Balance, Equity, Free Margin, Margin Level.

MOOD: Informational, cautious, critical. Trade Allowed status is the most important piece of information — if false, all execution is blocked. Warning panel clearly communicates account switch risks.

COLOR PALETTE:
- Standard dark base (#0d1117, #161b22)
- Connection status: #3fb950 (green dot)
- Trade Allowed: #3fb950 (green badge when enabled)
- Trade Blocked: #f85149 (red badge when disabled — CRITICAL)
- DEMO badge: #58a6ff (blue)
- Warning panels: rgba(210, 153, 34, 0.10) background, #d29922 border
- Danger panels: rgba(248, 81, 73, 0.15) background, #f85149 border (2px)

VISIBLE ELEMENTS:
- Terminal Context note: "Note: AutoTrading status is CRITICAL. If disabled, all execution operations are blocked."
- MT5 Terminal panel: "Terminal Name: MetaTrader 5 | Terminal Path: C:\Program Files\...\terminal64.exe | Broker Company: FBS Ltd. | Broker Server: FBS-Demo | Connection: ● Connected | Trade Allowed: ● Yes (AutoTrading enabled)" (green border)
- Account Details panel: "Account Login: 105845678 | Account Mode: DEMO (● Demo | ○ Real | ○ Contest) | Currency: USD | Leverage: 1:100 | Balance: $10,000.00 | Equity: $10,250.00 | Free Margin: $8,500.00 | Margin Level: 683.3%"
- Account Switch Warning panel (danger styling): "⚠️ ACCOUNT SWITCH WARNING — Changing or probing another account can: Degrade the active MT5 terminal session, Disable AutoTrading (trade_allowed = false), Require manual recovery in MT5 | Recovery if authentication fails: 1. Re-enable AutoTrading in MT5 terminal, 2. Relaunch apps/control_plane.py if services crashed | [ I Understand ] (disabled — account switch not exposed)" (red border, 2px)
- Symbol Watchlist: "Subscribed symbols (from MT5_WATCH_SYMBOLS): BTCUSD, EURUSD, GBPUSD, USDJPY, USDCHF | [Manage Symbols] (navigates to /settings)"

CRITICAL ELEMENT:
- Trade Allowed status must be prominently visible with green badge when enabled
- If trade_allowed = false, show red badge with recovery instructions

WHAT TO AVOID:
- No MT5 terminal screenshot (this is the WebUI, not MT5)
- No chart of account balance history
- No broker comparison table
- No "recommended brokers" section
- No affiliate links or broker ads
- No enabled account switch button (must show disabled with warning)

RENDER: Desktop screen, vertical layout. Show all panels clearly with Trade Allowed status prominently visible. Account Switch Warning panel should have danger styling.
```

---

### Prompt 9: Settings

```
Settings screen, symbol subscription management, environment variable viewer, dark trading terminal.

COMPOSITION: Top: Settings header with restart notice. Main sections stacked vertically: Subscribed Symbols table (with subscribe/unsubscribe controls), Timeframes section, Environment Variables panel (read-only).

INFORMATION DENSITY: Moderate. Symbol table shows currently subscribed symbols with active status and unsubscribe buttons. Add symbol input with autocomplete. Timeframes shown as checkboxes. Env vars listed as read-only key-value pairs.

MOOD: Administrative, configuration-focused, clear about what requires restart. Operator can manage symbol universe easily but understands env var changes need file edit + restart.

COLOR PALETTE:
- Standard dark base (#0d1117, #161b22)
- Active symbol badge: #3fb950 (green)
- Button primary: #58a6ff (blue)
- Button danger: #f85149 (red for unsubscribe)
- Read-only text: #8b949e (secondary)

VISIBLE ELEMENTS:
- Settings header: "SETTINGS — Note: Changes require restart for some settings."
- Subscribed Symbols table:
  - "BTCUSD | ● Active | [Unsubscribe]" (red button)
  - "EURUSD | ● Active | [Unsubscribe]"
  - "GBPUSD | ● Active | [Unsubscribe]"
  - "USDJPY | ● Active | [Unsubscribe]"
  - "USDCHF | ● Active | [Unsubscribe]"
  - "Add symbol: [─────────── ▼] [Subscribe] (Symbol must exist in broker catalog)"
- Timeframes section: "Tracked timeframes (from MT5_WATCH_TIMEFRAMES): ● M1 ● M5 ● H1 ● H4 ● D1 | Note: Changing timeframes requires restart."
- Environment Variables panel: "FAST_DESK_ENABLED=true | SMC_SCANNER_ENABLED=true | SMC_LLM_ENABLED=true | FAST_DESK_RISK_PERCENT=1.0 | FAST_DESK_MAX_POSITIONS_PER_SYMBOL=1 | FAST_DESK_MAX_POSITIONS_TOTAL=4 | MT5_POLL_SECONDS=5 | CORE_ACCOUNT_REFRESH_SECONDS=2 | ACCOUNT_MODE=demo | Note: Changing env vars requires editing .env file and restarting control plane."

INTERACTION CUES:
- Unsubscribe buttons are red (danger action)
- Subscribe button is blue (primary action)
- Symbol input has autocomplete dropdown
- Env vars are read-only (no edit controls)

WHAT TO AVOID:
- No enabled env var edit controls
- No "Save Settings" button (changes are immediate for subscribe/unsubscribe)
- No complex configuration forms
- No advanced settings sections

RENDER: Desktop screen, vertical layout. Show subscribed symbols table with unsubscribe buttons, add symbol input, and env vars panel clearly.
```

---

## Technical Notes for Image Generation

### Aspect Ratios

- Desktop screens: 16:9 (1920x1080)
- Detail shots: 4:3 (for specific panels)
- Mobile mockups: 9:16 (if needed later)

### Style Keywords

Use these in prompts:
- "dark mode trading terminal"
- "professional prop desk"
- "GitHub dark theme aesthetic"
- "data-dense but organized"
- "monospace numbers"
- "functional color coding"
- "no gradients"
- "minimal shadows"
- "heuristic-first trading"
- "RAM-based market state"
- "dual-desk operations (Fast + SMC)"

### Negative Prompts

Always include:
- "no white backgrounds"
- "no purple gradients"
- "no emoji"
- "no gamification"
- "no retail trading app aesthetics"
- "no crypto moon imagery"
- "no AI brain visualizations"
- "no LLM office stack elements"
- "no chairman/analyst/supervisor/trader/risk cards"
- "no conversation flow bubbles"

---

## Usage Workflow

1. **Generate Master Moodboard first** — Use this to align stakeholders on overall direction
2. **Generate individual screens** — One at a time, review each
3. **Compile into presentation** — Combine into slide deck for stakeholder review
4. **Annotate with notes** — Add callouts for specific features (execution incomplete, trader pending, etc.)
5. **Use as implementation reference** — Keep visible during Solid.js development

---

## Repository-Specific Notes

These prompts are specific to `heuristic-metatrader5-bridge`:

- **NOT** the LLM office stack (no chairman/analyst/supervisor/trader/risk roles)
- **NOT** disk-based runtime (RAM-first, HTTP-only)
- **Two desks**: Fast Desk (heuristic, no LLM) + SMC Desk (heuristic + optional LLM)
- **Control Plane HTTP API** is the only external interface
- **Honest about implementation status**: Execution incomplete, Trader pending, RiskKernel roadmap
- **Critical Trade Allowed status**: Must be prominently displayed
- **Account switch warning**: Danger styling for disruptive operation

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-24  
**Author**: Senior Frontend Architect (AI-Assisted)  
**Reviewers**: Pending
