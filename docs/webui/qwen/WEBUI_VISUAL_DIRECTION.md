# WebUI Visual Direction

**Version**: 1.0.0  
**Date**: 2026-03-24  
**Design System**: Trading-Native Dark  
**Repository**: `heuristic-metatrader5-bridge`  
**Framework**: Solid.js + CSS Variables

---

## 1. Design Philosophy

This UI is **not**:
- The LLM office stack UI (no chairman/supervisor/trader/risk roles)
- A generic SaaS admin panel
- A retail trading app (Robinhood, eToro)
- A crypto portfolio tracker (Zapper, DeBank)
- A disk-based runtime observer

This UI **is**:
- Professional prop desk terminal for heuristic-first trading
- RAM-based market state visualization
- Dual-desk operations board (Fast + SMC)
- Control Plane HTTP API consumer
- Multi-broker, multi-terminal ready

### Core Principles

1. **Speed Over Beauty** — Performance is a feature. Animations must be subtle and fast (<200ms).
2. **Clarity Under Stress** — When the market moves, operators need instant comprehension.
3. **Precision** — Numbers must be legible, aligned (tabular-nums), and unambiguous.
4. **Honesty** — Clearly distinguish implemented vs planned features. No fake completeness.
5. **Context** — Every number needs context (vs limit, vs previous, vs target).

---

## 2. Typography

### Font Stack

```css
:root {
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
}
```

**Rationale**:
- **Inter**: Neutral, highly legible, excellent for UI text. Not playful like Poppins, not sterile like Helvetica.
- **JetBrains Mono**: Code-grade monospace for numbers, prices, and timestamps. Ligatures optional.

### Type Scale

```css
:root {
  /* Display — Screen titles */
  --text-display-size: 24px;
  --text-display-weight: 600;
  --text-display-line-height: 1.2;

  /* Heading — Panel titles */
  --text-heading-size: 16px;
  --text-heading-weight: 600;
  --text-heading-line-height: 1.3;

  /* Body — Primary content */
  --text-body-size: 14px;
  --text-body-weight: 400;
  --text-body-line-height: 1.5;

  /* Small — Secondary info, labels */
  --text-small-size: 12px;
  --text-small-weight: 400;
  --text-small-line-height: 1.4;

  /* Mono — Numbers, prices, timestamps */
  --text-mono-size: 13px;
  --text-mono-weight: 400;
  --text-mono-line-height: 1.6;
}
```

### Usage Guidelines

| Element | Font | Size | Weight | Case |
|---------|------|------|--------|------|
| Screen Title | Inter | 24px | 600 | Sentence |
| Panel Title | Inter | 16px | 600 | Sentence |
| Body Text | Inter | 14px | 400 | Sentence |
| Labels | Inter | 12px | 500 | Uppercase (tracking: 0.05em) |
| Prices | JetBrains Mono | 13px | 400 | Tabular |
| Timestamps | JetBrains Mono | 12px | 400 | Monospace |
| P&L Values | JetBrains Mono | 14px | 500 | Tabular |
| Badges | Inter | 11px | 600 | Uppercase |
| Status Text | Inter | 11px | 600 | Uppercase |

### Number Formatting

```css
/* All numeric data uses tabular nums for alignment */
.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em; /* Tighter for numbers */
}
```

---

## 3. Color System

### Base Palette

```css
:root {
  /* Backgrounds — Dark neutral base */
  --bg-primary: #0d1117;      /* GitHub dim background */
  --bg-secondary: #161b22;    /* Card/panel background */
  --bg-tertiary: #21262d;     /* Hover/inset background */
  --bg-elevated: #30363d;     /* Modal/dropdown background */

  /* Borders */
  --border-default: #30363d;
  --border-strong: #484f58;
  --border-subtle: #21262d;

  /* Text */
  --text-primary: #e6edf3;    /* Primary text */
  --text-secondary: #8b949e;  /* Secondary text */
  --text-tertiary: #484f58;   /* Disabled/muted */
  --text-inverse: #0d1117;    /* Text on bright backgrounds */
}
```

**Rationale**: Dark neutral base reduces eye strain during long sessions. Not pure black (too harsh). GitHub's dim palette is proven for developer tools.

### Accent Colors (Functional)

```css
:root {
  /* Status — Universal meaning */
  --status-success: #3fb950;   /* Green: profit, up, healthy */
  --status-warning: #d29922;   /* Yellow: warning, watch */
  --status-danger: #f85149;    /* Red: loss, down, critical */
  --status-info: #58a6ff;      /* Blue: info, neutral */

  /* Desk Identity */
  --desk-fast: #3fb950;        /* Green: Fast desk */
  --desk-smc: #a371f7;         /* Purple: SMC desk */

  /* Ownership (Phase 3) */
  --ownership-fast: #3fb950;   /* Green: Fast-owned */
  --ownership-smc: #a371f7;    /* Purple: SMC-owned */
  --ownership-inherited: #d29922; /* Yellow: Inherited */
  --ownership-orphaned: #f85149;  /* Red: Orphaned */
}
```

### Risk Color Semantics

```css
:root {
  /* Risk Levels — Drawdown gauge, position risk */
  --risk-low: #3fb950;         /* 0-50% of limit */
  --risk-medium: #d29922;      /* 50-80% of limit */
  --risk-high: #f85149;        /* 80-100% of limit */
  --risk-critical: #ff7b72;    /* >100% (breach) */

  /* Kill Switch (Phase 2) */
  --killswitch-armed: #3fb950;   /* Armed, not tripped */
  --killswitch-tripped: #f85149; /* Tripped, blocked */
  --killswitch-disabled: #484f58; /* Disabled */
}
```

### Feed Health Colors

```css
:root {
  /* Feed Status — Bar age */
  --feed-healthy: #3fb950;     /* < timeframe + 30s */
  --feed-warning: #d29922;     /* timeframe + 30s to + 60s */
  --feed-critical: #f85149;    /* > timeframe + 60s */
}
```

### Trade Allowed Status (CRITICAL)

```css
:root {
  /* Trade Allowed — MT5 AutoTrading */
  --trade-allowed: #3fb950;    /* trade_allowed = true */
  --trade-blocked: #f85149;    /* trade_allowed = false */
}
```

### Usage Guidelines

| Use Case | Primary Color | Secondary |
|----------|---------------|-----------|
| Profit P&L | `--status-success` | Light green bg |
| Loss P&L | `--status-danger` | Light red bg |
| Warning | `--status-warning` | Light yellow bg |
| Info | `--status-info` | Light blue bg |
| Fast Desk | `--desk-fast` | Green border |
| SMC Desk | `--desk-smc` | Purple border |
| Healthy Feed | `--feed-healthy` | Green dot |
| Warning Feed | `--feed-warning` | Yellow dot |
| Trade Allowed | `--trade-allowed` | Green badge |
| Trade Blocked | `--trade-blocked` | Red badge (CRITICAL) |

**Rule**: Never use color alone. Always pair with icon or text label (accessibility).

---

## 4. Spacing Rhythm

### Base Scale

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
}
```

**Rationale**: 4px base grid. Powers of 2 for easy mental math.

### Component Spacing

```css
/* Panel */
.panel {
  padding: var(--space-4);
  gap: var(--space-3);
}

/* Panel Header */
.panel-header {
  padding-bottom: var(--space-3);
  margin-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-default);
}

/* Grid Layout */
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
}

.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}

.grid-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}

/* Table */
.table-row {
  padding: var(--space-2) var(--space-3);
  gap: var(--space-4);
}

/* Card */
.card {
  padding: var(--space-4);
  gap: var(--space-2);
}
```

### Density Modes

```css
/* Default density */
:root {
  --density-panel-padding: var(--space-4);
  --density-row-padding: var(--space-2) var(--space-3);
  --density-gap: var(--space-3);
}

/* Compact density (for data-heavy screens) */
.compact {
  --density-panel-padding: var(--space-3);
  --density-row-padding: var(--space-1) var(--space-2);
  --density-gap: var(--space-2);
}
```

---

## 5. Surface System

### Panel Variants

```css
/* Base Panel */
.panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: var(--space-4);
}

/* Elevated Panel (modal, dropdown) */
.panel-elevated {
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

/* Active Panel (selected tab, focused) */
.panel-active {
  border-color: var(--desk-fast);
  box-shadow: 0 0 0 1px var(--desk-fast);
}

/* Warning Panel */
.panel-warning {
  border-color: var(--status-warning);
  background: rgba(210, 153, 34, 0.05);
}

/* Danger Panel */
.panel-danger {
  border-color: var(--status-danger);
  background: rgba(248, 81, 73, 0.05);
}

/* Critical Panel (Trade Blocked) */
.panel-critical {
  border-color: var(--status-danger);
  background: rgba(248, 81, 73, 0.10);
  border-width: 2px;
}
```

### Card Variants

```css
/* KPI Card */
.kpi-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: var(--space-3);
  min-width: 160px;
}

/* Position Card */
.position-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--desk-fast); /* Desk identity */
  border-radius: 6px;
  padding: var(--space-3);
}

/* Position Card — Profit */
.position-card.profit {
  border-left-color: var(--status-success);
}

/* Position Card — Loss */
.position-card.loss {
  border-left-color: var(--status-danger);
}

/* Desk Status Card */
.desk-status-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-top: 3px solid;
  border-radius: 6px;
  padding: var(--space-3);
}

.desk-status-card.fast {
  border-top-color: var(--desk-fast);
}

.desk-status-card.smc {
  border-top-color: var(--desk-smc);
}
```

### Table Styles

```css
.table {
  width: 100%;
  border-collapse: collapse;
}

.table-header {
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-strong);
}

.table-header-cell {
  padding: var(--space-2) var(--space-3);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  text-align: left;
}

.table-row {
  border-bottom: 1px solid var(--border-subtle);
}

.table-row:hover {
  background: var(--bg-tertiary);
}

.table-cell {
  padding: var(--space-2) var(--space-3);
  font-size: 13px;
}

.table-cell-mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

/* Critical row (e.g., trade blocked) */
.table-row.critical {
  background: rgba(248, 81, 73, 0.05);
  border-bottom-color: var(--status-danger);
}
```

---

## 6. Chart & Zone Visual Language

### Chart Container

```css
.chart-container {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  height: 400px;
  position: relative;
}

.chart-header {
  position: absolute;
  top: var(--space-3);
  left: var(--space-3);
  z-index: 10;
  display: flex;
  gap: var(--space-2);
}
```

### Candle Colors (TradingView Lightweight Charts)

```javascript
const chartOptions = {
  layout: {
    background: { color: '#0d1117' },  // --bg-primary
    textColor: '#8b949e',               // --text-secondary
  },
  grid: {
    vertLines: { color: '#21262d' },   // --border-subtle
    horzLines: { color: '#21262d' },
  },
};

const candlestickSeries = {
  upColor: '#3fb950',                   // --status-success
  downColor: '#f85149',                 // --status-danger
  borderUpColor: '#3fb950',
  borderDownColor: '#f85149',
  wickUpColor: '#3fb950',
  wickDownColor: '#f85149',
};
```

### SMC Zone Overlays (Phase 3)

```css
/* Order Block — Bullish */
.zone-ob-bullish {
  fill: rgba(63, 185, 80, 0.15);       /* Green with opacity */
  stroke: var(--status-success);
  stroke-width: 1;
  stroke-dasharray: 4 2;
}

/* Order Block — Bearish */
.zone-ob-bearish {
  fill: rgba(248, 81, 73, 0.15);       /* Red with opacity */
  stroke: var(--status-danger);
  stroke-width: 1;
  stroke-dasharray: 4 2;
}

/* Fair Value Gap */
.zone-fvg {
  fill: rgba(210, 153, 34, 0.10);      /* Yellow with opacity */
  stroke: var(--status-warning);
  stroke-width: 1;
  stroke-dasharray: 2 2;
}

/* Entry Zone */
.zone-entry {
  stroke: var(--desk-smc);
  stroke-width: 2;
  stroke-dasharray: 6 3;
}

/* Stop Loss */
.line-sl {
  stroke: var(--status-danger);
  stroke-width: 1;
  stroke-dasharray: 4 2;
}

/* Take Profit */
.line-tp {
  stroke: var(--status-success);
  stroke-width: 1;
  stroke-dasharray: 4 2;
}
```

### Zone Labels

```css
.zone-label {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 500;
  background: var(--bg-elevated);
  color: var(--text-primary);
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid var(--border-strong);
}
```

---

## 7. Alert Hierarchy

### Toast Notifications

```css
/* Info Toast */
.toast-info {
  background: var(--bg-elevated);
  border-left: 3px solid var(--status-info);
  color: var(--text-primary);
}

/* Success Toast */
.toast-success {
  background: var(--bg-elevated);
  border-left: 3px solid var(--status-success);
  color: var(--text-primary);
}

/* Warning Toast */
.toast-warning {
  background: var(--bg-elevated);
  border-left: 3px solid var(--status-warning);
  color: var(--text-primary);
}

/* Error Toast */
.toast-error {
  background: var(--bg-elevated);
  border-left: 3px solid var(--status-danger);
  color: var(--text-primary);
}

/* Critical Toast (Trade Blocked) */
.toast-critical {
  background: var(--bg-elevated);
  border-left: 4px solid var(--status-danger);
  color: var(--text-primary);
  box-shadow: 0 4px 12px rgba(248, 81, 73, 0.3);
}
```

### Inline Alerts

```css
/* Panel Alert */
.alert {
  padding: var(--space-3);
  border-radius: 4px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.alert-info {
  background: rgba(88, 166, 255, 0.10);
  border: 1px solid var(--status-info);
  color: var(--text-primary);
}

.alert-warning {
  background: rgba(210, 153, 34, 0.10);
  border: 1px solid var(--status-warning);
  color: var(--text-primary);
}

.alert-error {
  background: rgba(248, 81, 73, 0.10);
  border: 1px solid var(--status-danger);
  color: var(--text-primary);
}

.alert-critical {
  background: rgba(248, 81, 73, 0.15);
  border: 2px solid var(--status-danger);
  color: var(--text-primary);
  font-weight: 600;
}
```

### Status Badges

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-live {
  background: rgba(63, 185, 80, 0.15);
  color: var(--status-success);
}

.badge-partial {
  background: rgba(210, 153, 34, 0.15);
  color: var(--status-warning);
}

.badge-analysis {
  background: rgba(88, 166, 255, 0.15);
  color: var(--status-info);
}

.badge-roadmap {
  background: rgba(72, 79, 88, 0.5);
  color: var(--text-secondary);
}

.badge-danger {
  background: rgba(248, 81, 73, 0.15);
  color: var(--status-danger);
}

.badge-critical {
  background: rgba(248, 81, 73, 0.20);
  color: var(--status-danger);
  font-weight: 700;
  border: 1px solid var(--status-danger);
}
```

### Pulsing Live Indicator

```css
.live-dot {
  width: 8px;
  height: 8px;
  background: var(--status-success);
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.2); }
}
```

---

## 8. Motion Principles

### Animation Tokens

```css
:root {
  /* Duration */
  --duration-instant: 0ms;
  --duration-fast: 100ms;
  --duration-normal: 200ms;
  --duration-slow: 300ms;

  /* Easing */
  --ease-linear: linear;
  --ease-in: cubic-bezier(0.4, 0, 1, 1);
  --ease-out: cubic-bezier(0, 0, 0.2, 1);
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);

  /* Transitions */
  --transition-colors: color var(--duration-fast) var(--ease-in-out),
                       background-color var(--duration-fast) var(--ease-in-out),
                       border-color var(--duration-fast) var(--ease-in-out);
  --transition-transform: transform var(--duration-fast) var(--ease-out);
  --transition-opacity: opacity var(--duration-normal) var(--ease-in-out);
}
```

### Motion Guidelines

| Animation | Duration | Easing | Use Case |
|-----------|----------|--------|----------|
| Hover | 100ms | ease-out | Buttons, rows, cards |
| Focus | 100ms | ease-out | Input focus, tab switch |
| Fade In | 200ms | ease-in | Panel load, modal open |
| Fade Out | 200ms | ease-in | Panel unload, modal close |
| Slide In | 300ms | ease-out | Toast, drawer |
| Pulse | 2s infinite | ease-in-out | Live indicator, loading |

### Loading States

```css
/* Skeleton Loader */
.skeleton {
  background: linear-gradient(
    90deg,
    var(--bg-tertiary) 0%,
    var(--bg-elevated) 50%,
    var(--bg-tertiary) 100%
  );
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s infinite;
  border-radius: 4px;
}

@keyframes skeleton-pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Spinner */
.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-default);
  border-top-color: var(--desk-fast);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
```

**Rule**: Never animate more than 2 properties simultaneously. Keep animations under 300ms for UI interactions.

---

## 9. What This UI Must Never Look Like

### Avoid These Anti-Patterns

1. **LLM Office Stack UI**
   - No chairman/analyst/supervisor/trader/risk role cards
   - No conversation flow visualization
   - No "AI thinking" animations

2. **Purple-on-White SaaS Default**
   - No gradient purple buttons
   - No white background with purple accents
   - No generic "modern startup" aesthetic

3. **Gamified Retail Trading**
   - No confetti animations on profit
   - No emoji-heavy UI
   - No "You're on a 5-day winning streak!" badges

4. **Empty AI Dashboard Clichés**
   - No "AI-Powered" badges everywhere
   - No neural network visualizations
   - No fake "machine learning" graphics

5. **Crypto Portfolio Tracker**
   - No rainbow color explosions
   - No moon/rocket imagery
   - No "To the moon!" messaging

6. **Generic Admin Panel**
   - No boilerplate "4 cards per row" without purpose
   - No empty state illustrations of people working
   - No generic "Welcome back, User!" headers

### Visual Comparison

| ❌ Avoid | ✅ Embrace |
|----------|------------|
| White background, purple gradient | Dark neutral (#0d1117), functional accents |
| Rounded buttons (border-radius: 99px) | Subtle rounding (border-radius: 6px) |
| Playful illustrations | Data-first, minimal decoration |
| Emoji icons | SVG icons (lucide, heroicons) |
| "Good morning, Trader!" | "System Status: Live" |
| Confetti on profit | Green P&L number, no animation |
| Neural network graphics | Clean zone overlays on chart |
| LLM role cards | Desk status badges (Fast/SMC) |

---

## 10. Component Examples

### KPI Card

```tsx
// src/components/data/KPICard.tsx
<div class="kpi-card">
  <div class="kpi-label">Gross Exposure</div>
  <div class="kpi-value mono">0.45 lots</div>
  <div class="kpi-trend status-success">+0.10 vs avg</div>
</div>
```

### Status Badge

```tsx
// src/components/data/StatusBadge.tsx
<span class={`badge badge-${status}`}>
  {status === 'live' && <span class="live-dot" />}
  {label}
</span>
```

### Trade Allowed Indicator (CRITICAL)

```tsx
// src/components/controls/TradeAllowedIndicator.tsx
<div class={`trade-allowed ${tradeAllowed ? 'allowed' : 'blocked'}`}>
  <span class={`status-dot ${tradeAllowed ? 'success' : 'danger'}`} />
  <span class="status-text">
    {tradeAllowed ? 'AutoTrading Enabled' : 'AutoTrading Disabled'}
  </span>
  {!tradeAllowed && (
    <span class="recovery-hint">
      Enable AutoTrading in MT5 terminal
    </span>
  )}
</div>
```

### Position Card

```tsx
// src/components/data/PositionCard.tsx
<div class={`position-card ${pnl >= 0 ? 'profit' : 'loss'}`}>
  <div class="position-header">
    <span class="position-symbol">{symbol}</span>
    <span class={`badge badge-${side.toLowerCase()}`}>{side}</span>
  </div>
  <div class="position-details">
    <div class="position-row">
      <span class="label">Volume</span>
      <span class="mono">{volume} lots</span>
    </div>
    <div class="position-row">
      <span class="label">Entry</span>
      <span class="mono">{entry}</span>
    </div>
    <div class="position-row">
      <span class="label">P&L</span>
      <span class={`mono ${pnl >= 0 ? 'text-success' : 'text-danger'}`}>
        {pnl >= 0 ? '+' : ''}{pnl}
      </span>
    </div>
    <div class="position-row">
      <span class="label">Comment</span>
      <span class="mono text-secondary">{comment}</span>
    </div>
  </div>
  <div class="position-actions">
    <button class="btn btn-sm" disabled>Close</button>
    <button class="btn btn-sm" disabled>Modify</button>
  </div>
</div>
```

### Roadmap Panel

```tsx
// src/components/roadmap/RoadmapPanel.tsx
<div class="panel panel-roadmap">
  <div class="panel-header">
    <h3 class="panel-title">{title}</h3>
    <span class="badge badge-roadmap">COMING SOON</span>
  </div>
  <div class="roadmap-content">
    <p class="roadmap-description">{description}</p>
    <p class="roadmap-phase">Planned: {plannedPhase}</p>
    <ul class="roadmap-details">
      {details.map((detail) => (
        <li>{detail}</li>
      ))}
    </ul>
  </div>
</div>
```

---

## 11. Responsive Breakpoints

```css
:root {
  --breakpoint-sm: 640px;   /* Mobile landscape */
  --breakpoint-md: 768px;   /* Tablet */
  --breakpoint-lg: 1024px;  /* Desktop */
  --breakpoint-xl: 1280px;  /* Large desktop */
}

/* Mobile-first approach */
@media (max-width: 639px) {
  /* Mobile overrides */
  .grid-4 { grid-template-columns: 1fr; }
  .panel { padding: var(--space-3); }
  .table { font-size: 12px; }
}

@media (min-width: 640px) and (max-width: 767px) {
  /* Mobile landscape */
  .grid-4 { grid-template-columns: repeat(2, 1fr); }
}

@media (min-width: 768px) and (max-width: 1023px) {
  /* Tablet */
  .grid-4 { grid-template-columns: repeat(2, 1fr); }
}

@media (min-width: 1024px) {
  /* Desktop — Default */
}
```

---

## 12. Accessibility

### Color Contrast

All text must meet WCAG AA contrast ratio (4.5:1 for normal text, 3:1 for large text).

```css
/* Good contrast on dark background */
.text-primary { color: #e6edf3; }   /* 12.6:1 on #0d1117 */
.text-secondary { color: #8b949e; } /* 5.7:1 on #0d1117 */
```

### Focus States

```css
/* Visible focus ring */
:focus-visible {
  outline: 2px solid var(--desk-fast);
  outline-offset: 2px;
}

/* Remove default focus outline */
:focus:not(:focus-visible) {
  outline: none;
}
```

### Screen Reader Support

```css
/* Visually hidden but accessible */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

---

## 13. Summary: Visual Identity

This UI looks like:
- **Professional prop desk terminal** (Bloomberg, Reuters Eikon)
- **Developer tools** (GitHub, Vercel, Linear)
- **Data-first dashboards** (Grafana, Kibana)
- **RAM-based market state viewer**

This UI does NOT look like:
- **LLM office stack** (chairman/analyst/supervisor/trader/risk)
- **Retail trading apps** (Robinhood, eToro)
- **Crypto portfolios** (Zapper, DeBank)
- **SaaS admin panels** (Generic Bootstrap/Tailwind templates)

**Mood**: Serious, fast, deliberate, market-native, honest about implementation status.

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-24  
**Author**: Senior Frontend Architect (AI-Assisted)  
**Reviewers**: Pending
