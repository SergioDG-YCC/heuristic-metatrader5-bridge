# WEBUI Visual Direction

Date: 2026-03-24  
Product: `heuristic-metatrader5-bridge` operator console  
Target frontend: Solid.js

## Design intent

The UI must feel:
- fast
- disciplined
- technical
- reliable under pressure

The UI must not feel:
- playful
- retail-gamified
- generic startup dashboard

## Typography direction

Use a deliberate three-family system:

- Structural/UI headings: `Space Grotesk` (600/700)
- Dense numeric data: `IBM Plex Mono` (500/600)
- Explanatory text: `Public Sans` (400/500)

Rules:
- all prices, volumes, ids, tickets, and PnL use monospace
- compact line-height in dense grids
- avoid default browser/system font stack as final design language

## Color system

Base palette (industrial dark-neutral):

- `bg.base`: `#0B1016`
- `bg.layer`: `#121922`
- `surface.1`: `#17212C`
- `surface.2`: `#1E2A37`
- `border.base`: `#2B3A4B`
- `text.primary`: `#E6EEF8`
- `text.secondary`: `#93A6BD`

Desk identity accents:

- Fast Desk: `#00B89A`
- SMC Desk: `#2C95E8`

Operational state semantics:

- `ok`: `#2FA36A`
- `warning`: `#D49A2A`
- `danger`: `#E35A54`
- `critical`: `#FF3A33`
- `planned`: `#697E96`

## Account and risk color semantics

- account mode `demo`: neutral blue badge
- account mode `real`: amber-danger badge (high attention)
- drawdown rising: green -> amber -> red progression
- margin stress: amber pulse, then red lock
- ownership unknown: neutral gray with explicit `Unknown`
- kill switch active (future): critical red with persistent banner

## Spacing rhythm

Base unit: `4px`

Scale:
- `4, 8, 12, 16, 24, 32`

Density profiles:
- High-density table mode: row height `30-34px`
- Normal panel mode: `16px` inner padding
- Critical alert mode: `12px` compact banner with high contrast

## Surface system

Three-layer model:

1. Background atmosphere:
- subtle gradient + low-noise texture
- no flat single-color slab

2. Operational panels:
- restrained radius (`6px`)
- strong borders, low blur
- predictable panel hierarchy

3. Critical overlays:
- hard contrast borders
- minimal shadow spread
- no frosted-glass effect

## Chart and structural overlay language

Goals:
- preserve price legibility
- visually encode SMC semantics without clutter

Encoding:

- bullish order block: translucent green block + thin solid edge
- bearish order block: translucent red block + thin solid edge
- liquidity pool: blue dashed boundary + light fill
- FVG: amber translucent lane
- fibo levels: thin neutral lines with compact right labels
- invalidated zone: red hatch overlay

Do not use:
- saturated rainbow overlays
- thick opaque fills that hide candles

## Alert hierarchy

Level 1 (Critical):
- execution blockers
- auth/session disruption
- terminal trading disabled
- presentation: sticky top bar + modal on first occurrence

Level 2 (High):
- severe feed staleness on active symbols
- concentration/exposure pressure
- presentation: sticky panel warning

Level 3 (Medium):
- worker lag
- missing specs
- SSE reconnect state
- presentation: inline badges

Level 4 (Informational):
- roadmap/planned reminders
- non-blocking system notes
- presentation: muted callouts

## Motion principles

Motion must communicate data/state change, never entertainment.

- table row update flash: `120-180ms`
- panel enter settle: `140-180ms`
- alert in/out: short lateral transition `120-160ms`
- disable perpetual loops in dense screens

For critical mode:
- reduce non-essential motion
- prioritize immediate readability

## Layout principles

Desktop:
- left nav rail
- top critical strip
- central panel grid with intentional task grouping

Tablet:
- icon rail
- two-row panel composition

Mobile:
- bottom tabs
- single primary panel viewport
- secondary content in drawers/sheets

## What the UI must never look like

- purple-on-white SaaS starter layout
- giant generic KPI cards with no trading meaning
- marketing hero sections inside operator routes
- neon crypto style gradients
- playful iconography for risk operations
- fake enabled controls for planned backend features

## Component style constraints

Buttons:
- `Live` actions use solid style
- `Planned/Preview` actions use outline + disabled + capability badge

Tables:
- sticky header
- virtualized rows
- mono numeric columns

Badges:
- text + icon, never color-only encoding

Modals:
- disruptive operations require explicit warning copy and confirmation

## CSS token starter

```css
:root {
  --bg-base: #0B1016;
  --bg-layer: #121922;
  --surface-1: #17212C;
  --surface-2: #1E2A37;
  --border-base: #2B3A4B;

  --text-primary: #E6EEF8;
  --text-secondary: #93A6BD;

  --accent-fast: #00B89A;
  --accent-smc: #2C95E8;

  --state-ok: #2FA36A;
  --state-warning: #D49A2A;
  --state-danger: #E35A54;
  --state-critical: #FF3A33;
  --state-planned: #697E96;

  --radius-panel: 6px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
}
```

