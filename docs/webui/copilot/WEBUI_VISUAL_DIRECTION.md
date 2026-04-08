# WEBUI Visual Direction

Date: 2026-03-24
Product: heuristic-metatrader5-bridge operator console

## Design intent

The interface should feel like a serious execution cockpit:
- fast
- precise
- controlled
- trustworthy under stress

It should not feel like:
- generic SaaS admin template
- retail trading toy
- AI-themed dashboard with decorative charts

## Typography direction

Primary family:
- Sora for headings and structural labels

Data family:
- IBM Plex Mono for all numeric and execution-critical values

Secondary body family:
- Source Sans 3 for explanatory text and longer descriptions

Rules:
- never use default browser/system body stack as final style
- all prices, volumes, PnL, and ticket IDs use mono family
- line-height compact in dense boards, wider in explanatory panels

## Color system

Base palette (industrial dark-neutral):
- background base: #0D1116
- background elevated: #141A22
- panel surface: #1A2330
- panel border: #2A3648
- text primary: #E7EDF6
- text secondary: #95A6BD

Desk identity accents:
- Fast Desk accent: #00C2A8 (teal-green)
- SMC Desk accent: #2A9DFF (steel-blue)

Risk and status semantics:
- normal: #2DAA5E
- caution: #D8A234
- danger: #E25555
- critical lock: #FF3B30
- planned/preview: #6A7D96

Chart and structural overlays:
- bullish order block: rgba(46, 170, 94, 0.30)
- bearish order block: rgba(226, 85, 85, 0.30)
- liquidity zones: rgba(42, 157, 255, 0.24)
- FVG zones: rgba(216, 162, 52, 0.24)
- fibo guides: rgba(149, 166, 189, 0.45)

## Spacing rhythm

Grid unit:
- 4px base unit

Scale:
- 4, 8, 12, 16, 24, 32

Panel behavior:
- min panel padding 12
- standard panel padding 16
- high-density tables use 8px row vertical rhythm

## Surface system

Layers:
1. Base atmospheric layer with low-contrast gradient and subtle grid noise
2. Operational panels with sharp edges and restrained corner radius (6px)
3. Critical overlays (alerts/modals) with stronger border contrast and shadow cutout

Panel rules:
- avoid floating card clutter
- prioritize contiguous panel groups aligned by task
- use border and contrast, not heavy blur, to separate depth

## Chart and zone visual language

Principles:
- chart-first for desk views
- overlays must be readable without obscuring price action
- each structure type has distinct fill and line style

Encoding:
- order blocks: solid translucent block with desk-colored border
- liquidity pools: dashed contour with low fill
- fibo levels: thin horizontal guides with compact labels
- invalidation zones: red diagonal hatch overlay

## Alert hierarchy

Level 1 Critical:
- execution blockers, terminal/auth disruptions, potential session break
- fixed top strip + modal for first occurrence

Level 2 High:
- data staleness in active symbols, severe exposure concentration
- sticky panel alert

Level 3 Medium:
- worker lag, missing specs, stream reconnection
- inline panel badge

Level 4 Informational:
- planned feature reminders, mode explanations
- muted note surfaces

## Account and risk color semantics

- account mode demo: blue-neutral badge
- account mode real: amber-danger neutral to avoid accidental complacency
- drawdown low: green band
- drawdown medium: amber band
- drawdown high: red band
- margin stress above threshold: pulsing amber to red
- ownership unknown: neutral gray with explicit Unknown text

## Motion principles

- motion must communicate data arrival or state transition, never entertainment
- SSE updates: quick row flash fade (120-180ms)
- panel enter animation: slight upward settle (160ms)
- alert arrival: lateral slide with opacity (140ms)
- avoid continuous animation loops in dense trading views

## Layout behavior

Desktop:
- three-zone composition:
  - left navigation rail
  - top critical strip
  - central multi-panel workspace

Tablet:
- rail collapses to icon bar
- central workspace becomes two-panel stack

Mobile:
- route tabs at bottom
- one primary panel at a time with secondary drawers
- no side-by-side dense grids

## What the UI must never look like

- purple-on-white startup template
- random KPI cards without trading meaning
- giant hero sections or marketing copy blocks
- playful gradients that hide numeric contrast
- glassmorphism-heavy layout reducing legibility
- oversaturated candles and overlays fighting each other

## Component style constraints

- Buttons:
  - primary actions reserved for live-safe operations only
  - planned actions styled as outline + Planned tag + disabled cursor

- Tables:
  - fixed header, virtualized body, sticky symbol column when needed
  - mono typography for numbers and IDs

- Badges:
  - include semantic icon and plain text state
  - no color-only communication

- Modals:
  - destructive or disruptive operations require explicit typed confirmation in future phases

## CSS token starter model

```css
:root {
  --bg-base: #0D1116;
  --bg-elev: #141A22;
  --surface: #1A2330;
  --border: #2A3648;

  --text-primary: #E7EDF6;
  --text-secondary: #95A6BD;

  --accent-fast: #00C2A8;
  --accent-smc: #2A9DFF;

  --state-ok: #2DAA5E;
  --state-warn: #D8A234;
  --state-danger: #E25555;
  --state-critical: #FF3B30;
  --state-planned: #6A7D96;

  --radius-panel: 6px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
}
```
