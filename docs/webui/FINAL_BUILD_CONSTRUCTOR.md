# Final Build Constructor

## Purpose

This document is the construction brief for the future `Solid.js` frontend.

It is not a moodboard. It is not a free interpretation of the old WebUI proposals. It is a source-backed build document tied to the real control plane, the current architecture, and the product roadmap.

## Source precedence

The constructor must use sources in this order of authority:

1. Current backend code for what exists today:
   - [`apps/control_plane.py`](../../apps/control_plane.py)
   - [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py)
   - [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py)
2. Canonical architecture and roadmap for what the product is meant to become:
   - [`README.md`](../../README.md)
   - [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)
   - [`docs/WEBUI_ARCHITECTURE.md`](../WEBUI_ARCHITECTURE.md)
   - [`docs/plans/2026-03-24_immutable_bridge_action_plan.md`](../plans/2026-03-24_immutable_bridge_action_plan.md)
3. Operational audits and certification evidence for risk framing:
   - [`docs/audit/2026-03-24_live_bridge_audit.md`](../audit/2026-03-24_live_bridge_audit.md)
   - [`docs/audit/2026-03-24_mt5_official_surface_inventory.md`](../audit/2026-03-24_mt5_official_surface_inventory.md)
   - [`docs/plans/2026-03-24_connector_certification_plan.md`](../plans/2026-03-24_connector_certification_plan.md)
   - [`docs/audit/2026-03-24_connector_certification_execution_report.md`](../audit/2026-03-24_connector_certification_execution_report.md)
4. Final WebUI consolidation docs for editorial and UX direction:
   - [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)
   - [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
   - [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)
   - [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
5. Original proposal folders only as historical reference:
   - `docs/webui/codex/`
   - `docs/webui/copilot/`
   - `docs/webui/qwen/`

If sources conflict, apply these rules:

- current HTTP capability: [`apps/control_plane.py`](../../apps/control_plane.py) wins
- current live-state payload shape: [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py) wins
- future system shape: [`docs/plans/2026-03-24_immutable_bridge_action_plan.md`](../plans/2026-03-24_immutable_bridge_action_plan.md) wins
- operational hazard language: certification docs win
- original proposals never override code or canonical docs

## Required reading before writing code

Read these in order:

1. [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
   - defines the UX and visual posture
2. [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)
   - defines routes, navigation, and panel hierarchy
3. [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
   - defines each screen's purpose, widgets, and live versus future hooks
4. [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)
   - defines the core runtime, control plane, and data-bus boundaries
5. [`docs/WEBUI_ARCHITECTURE.md`](../WEBUI_ARCHITECTURE.md)
   - defines WebUI reading order and backend-facing operating constraints
6. [`docs/plans/2026-03-24_immutable_bridge_action_plan.md`](../plans/2026-03-24_immutable_bridge_action_plan.md)
   - defines ownership, risk, multi-terminal, live/paper, and supervisor roadmap
7. [`apps/control_plane.py`](../../apps/control_plane.py)
   - defines the actual routes the frontend can call today
8. [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py)
   - defines what `/status` and `/events` really contain
9. [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py)
   - defines connector capabilities and operational hazards hidden behind the current control plane
10. [`docs/audit/2026-03-24_connector_certification_execution_report.md`](../audit/2026-03-24_connector_certification_execution_report.md)
    - defines broker/comment/probe hazards the UI must communicate

Important interpretation note:

- the certification report is still required reading for operator risk, `comment=""` behavior, and account-probe danger
- but the current method inventory in [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py) supersedes older gap lists in that report

## Constructor summary

Build the first honest WebUI for `heuristic-metatrader5-bridge` in `Solid.js`.

The goal is not to simulate the entire future product. The goal is to ship a reliable operator console against the current control-plane surface, while leaving clean extension points for ownership, risk, paper/live, and desk-specific action APIs.

Sources:

- [`README.md`](../../README.md)
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)
- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)

## Repository placement and coexistence with backend

The WebUI may and should be built inside the same repository, as long as it does not collide with the current Python backend layout.

Recommended location:

- `apps/webui/`

Recommended repo shape:

```text
apps/
  control_plane.py
  webui/
    package.json
    vite.config.ts
    index.html
    src/
```

Rules:

- frontend code lives in the same repo for visibility, traceability, and coordinated development
- runtime communication still happens only through the HTTP/SSE control plane
- do not import Python backend modules into the frontend build
- do not read SQLite or runtime files directly from the frontend
- do not move or replace `apps/control_plane.py`

Sources:

- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)
- [`docs/WEBUI_ARCHITECTURE.md`](../WEBUI_ARCHITECTURE.md)
- [`apps/control_plane.py`](../../apps/control_plane.py)

## Joint startup model

The frontend should be designed to start alongside the backend, but not be embedded inside the backend process.

Canonical backend start command remains:

```powershell
.\.venv\Scripts\python.exe apps/control_plane.py
```

Recommended frontend dev start:

```powershell
cd apps\webui
npm install
npm run dev
```

Recommended coordinated startup approach:

- keep the backend command above as the canonical entrypoint
- allow an additional same-repo helper launcher for local development, for example:
  - `scripts/dev/start_webui_and_control_plane.ps1`
  - or `apps/start_stack.ps1`
- the helper launcher may open both processes, but it must not replace the canonical backend startup contract

The constructor may add a helper launcher, but must not rewrite backend boot semantics.

Sources:

- [`README.md`](../../README.md)
- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)

## Explicit note for the backend-aware constructor

If the builder adds frontend startup orchestration, it must assume:

- backend boot can take time before `/status` is available
- frontend may start before backend is ready
- frontend must tolerate connection refused, timeout, and `503 Runtime not initialized`
- frontend must not crash or render a broken error wall during backend warmup

The constructor should treat backend warmup as a first-class app state.

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py)

## Non-negotiable source-backed rules

### 1. The WebUI talks only to the control plane

The UI must not read SQLite, inspect local runtime files, or talk to MT5 directly.

Sources:

- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)
- [`docs/WEBUI_ARCHITECTURE.md`](../WEBUI_ARCHITECTURE.md)
- [`apps/control_plane.py`](../../apps/control_plane.py)

### 2. `/events` is a live-state stream, not an event ledger

`/events` streams repeated `build_live_state()` snapshots. It is useful for freshness and runtime liveness. It is not a durable or semantic event log.

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py)
- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)

### 3. Connector write methods exist, but HTTP write endpoints do not

The connector implements open/modify/remove/close helpers, but the current FastAPI control plane does not expose matching mutation routes. Therefore, the WebUI must not render live trading buttons as enabled.

Sources:

- [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py)
- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)

### 4. `trade_allowed` is operationally real but not yet a first-class HTTP field

The connector preflight enforces it. The current control plane does not expose it as a clean UI contract. The frontend must show trading permission as `Unknown` until the backend surfaces it explicitly.

Sources:

- [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py)
- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)

### 5. Comments are not ownership truth

The broker can reject populated comments. Ownership by comment remains unsafe and must not be presented as a formal operator truth.

Sources:

- [`docs/audit/2026-03-24_connector_certification_execution_report.md`](../audit/2026-03-24_connector_certification_execution_report.md)
- [`docs/plans/2026-03-24_immutable_bridge_action_plan.md`](../plans/2026-03-24_immutable_bridge_action_plan.md)
- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)

### 6. Account probe or switching is dangerous

The UI must treat account change and probe flows as dangerous future workflows, not harmless settings toggles.

Sources:

- [`docs/audit/2026-03-24_connector_certification_execution_report.md`](../audit/2026-03-24_connector_certification_execution_report.md)
- [`docs/plans/2026-03-24_connector_certification_plan.md`](../plans/2026-03-24_connector_certification_plan.md)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)

## Current control-plane contract

Build against this route surface first.

| Route | Method | Use in UI | Source |
| --- | --- | --- | --- |
| `/status` | `GET` | Runtime Overview headline state | [`apps/control_plane.py`](../../apps/control_plane.py) |
| `/chart/{symbol}/{timeframe}` | `GET` | symbol drilldown and desk charts | [`apps/control_plane.py`](../../apps/control_plane.py) |
| `/specs` | `GET` | symbol spec cache/explorer | [`apps/control_plane.py`](../../apps/control_plane.py) |
| `/specs/{symbol}` | `GET` | execution-relevant spec detail | [`apps/control_plane.py`](../../apps/control_plane.py) |
| `/account` | `GET` | account metrics, recent deals, recent orders | [`apps/control_plane.py`](../../apps/control_plane.py), [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py) |
| `/positions` | `GET` | positions and pending orders grid | [`apps/control_plane.py`](../../apps/control_plane.py) |
| `/exposure` | `GET` | exposure and risk views | [`apps/control_plane.py`](../../apps/control_plane.py) |
| `/catalog` | `GET` | universe/spec support flows | [`apps/control_plane.py`](../../apps/control_plane.py) |
| `/subscribe` | `POST` | symbol watch management | [`apps/control_plane.py`](../../apps/control_plane.py) |
| `/unsubscribe` | `POST` | symbol watch management | [`apps/control_plane.py`](../../apps/control_plane.py) |
| `/events` | `GET` SSE | freshness, runtime liveness, live-state updates | [`apps/control_plane.py`](../../apps/control_plane.py), [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py) |

There are no current HTTP routes for:

- open position
- close position
- modify SL/TP
- modify pending order
- remove pending order
- account switching
- ownership actions
- risk actions
- live/paper switching

## Dev proxy and same-origin requirement

`apps/control_plane.py` currently does not define CORS middleware. Therefore, the frontend constructor should not rely on direct browser cross-origin calls from a different port without a proxy.

Required dev approach:

- use `Vite` dev proxy so browser requests appear same-origin from the frontend app
- proxy these route families to the backend origin:
  - `/status`
  - `/chart`
  - `/specs`
  - `/account`
  - `/positions`
  - `/exposure`
  - `/catalog`
  - `/subscribe`
  - `/unsubscribe`
  - `/events`

Recommended backend origin for local development:

- `http://127.0.0.1:8765`

Recommended frontend dev origin:

- `http://127.0.0.1:5173`

Do not require backend CORS changes as a prerequisite for the first frontend build.

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)

## Build order

Build in this order. Do not start with desk-specific visuals.

1. app shell, route system, HTTP client, SSE client, capability registry
2. Runtime Overview
3. Operations Console
4. Terminal / Account Context
5. Alerts / Events
6. Risk Center with live read-only data and preview governance panels
7. Fast Desk shell with disabled or preview action zones
8. SMC Desk shell with preview thesis/zones modules
9. Ownership preview
10. Live vs Paper preview

This order keeps the frontend anchored to live data first and roadmap shells second.

Sources:

- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
- [`docs/plans/2026-03-24_immutable_bridge_action_plan.md`](../plans/2026-03-24_immutable_bridge_action_plan.md)

## Recommended Solid.js stack

- `Vite`
- `solid-js`
- `@solidjs/router`
- native `fetch` plus a thin typed API client
- native `EventSource` wrapper for SSE
- small local store layer using Solid signals/stores
- optional lightweight chart library only after route shells are stable

Do not start with SSR or SolidStart unless a later product requirement explicitly justifies it. This is an internal operator console hitting a local or controlled backend, not a content site.

Sources:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)

## Recommended app structure

```text
apps/webui/
  src/
    app/
      App.tsx
      routes.tsx
      shell/
    api/
      client.ts
      endpoints.ts
      mappers.ts
      capabilities.ts
    stores/
      runtimeStore.ts
      operationsStore.ts
      terminalStore.ts
      alertsStore.ts
      chartsStore.ts
      uiStore.ts
    routes/
      runtime/
      operations/
      fast/
      smc/
      risk/
      terminal/
      alerts/
      ownership/
      mode/
    components/
      status/
      data-grid/
      panels/
      charts/
      alerts/
      preview/
    styles/
      tokens.css
      layout.css
      components.css
```

Sources:

- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)

## Required constructor deliverables

Any implementation prompt based on this document must produce, at minimum:

1. a runnable `Solid.js` app shell under `apps/webui/`
2. route wiring for all v1 routes defined in this document
3. a typed API client for the current control-plane routes
4. one shared SSE consumer for `/events`
5. route-level stores for runtime, operations, terminal, alerts, and charts
6. reusable capability-state UI primitives
7. live implementations for:
   - Runtime Overview
   - Operations Console
   - Terminal / Account Context
   - Alerts / Events
   - Risk Center read-only shell
8. preview or disabled shells for:
   - Fast Desk action lane
   - SMC Desk thesis/action areas
   - Ownership
   - Live vs Paper
9. explicit capability labeling in every non-live module
10. operator-safe empty, loading, stale, degraded, and error states

It is not enough to produce static screens. The implementation must be wired to the current backend and must represent missing backend surfaces honestly.

Sources:

- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`apps/control_plane.py`](../../apps/control_plane.py)

## Output contract for the implementation prompt

The constructor prompt should be treated as successful only if it produces:

- real code, not only mockups
- route components, stores, and API plumbing
- capability badges and preview/disabled states
- documented assumptions where the backend is still future-state
- no fabricated HTTP routes or action handlers

The constructor prompt should not stop at:

- a wireframe-only output
- a visual-only prototype
- invented APIs
- enabling controls that the current backend cannot honor

Sources:

- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)
- [`FINAL_BUILD_CONSTRUCTOR.md`](./FINAL_BUILD_CONSTRUCTOR.md)

## Layout rules

Use a three-band mental model:

- top strip: global health, connection, freshness, account headline
- main workspace: route-specific panels and grids
- right rail or lower rail: alerts, preview modules, and secondary context

General layout requirements:

- desktop-first density with strong tablet fallback
- no oversized header chrome
- persistent global status strip
- fast route switching between Runtime, Operations, Fast, and SMC

Sources:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)

## Route contract

Create these routes first:

- `/`
- `/operations`
- `/fast`
- `/smc`
- `/risk`
- `/terminal`
- `/alerts`
- `/ownership`
- `/mode`
- `/operations/symbol/:symbol`
- `/operations/symbol/:symbol/chart/:timeframe`
- `/terminal/spec/:symbol`

Sources:

- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)

## Data contract notes for the builder

The constructor must normalize payloads around these facts:

- `/status` returns the `build_live_state()` payload from `CoreRuntimeService`
- `/positions` returns `{ positions, orders }`
- `/account` returns `account_state`, `positions`, `orders`, `exposure_state`, `recent_deals`, `recent_orders`
- `/events` repeats the live-state snapshot and is suitable for freshness, not history
- `/chart/{symbol}/{timeframe}` returns `chart_context` and `candles`

The builder should create stable frontend types for:

- `RuntimeHealth`
- `LiveStateSnapshot`
- `AccountState`
- `ExposureState`
- `PositionRow`
- `OrderRow`
- `RecentDeal`
- `RecentOrder`
- `ChartContext`
- `CapabilityState`
- `AlertItem`

These types should be derived from the current Python payloads, not from proposal prose.

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py)
- [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py)

## Stores and state responsibilities

### `runtimeStore`

Responsibilities:

- load `/status`
- consume `/events` as live-state snapshots, not as semantic events
- compute freshness, stale flags, and connectivity indicators
- expose capability-state flags for runtime panels

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)

### `operationsStore`

Responsibilities:

- poll `/positions`
- poll `/exposure`
- poll `/account`
- normalize positions, exposure, recent orders, and recent deals
- derive operational summaries used by Operations Console and Alerts

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py)
- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)

### `terminalStore`

Responsibilities:

- load `/catalog`
- load `/specs`
- load `/specs/{symbol}`
- provide account/spec context to Terminal and drilldown routes

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)

### `chartsStore`

Responsibilities:

- fetch `/chart/{symbol}/{timeframe}`
- manage symbol/timeframe cache
- track chart freshness and request state

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)

### `alertsStore`

Responsibilities:

- derive alert objects from runtime, account, exposure, and recent broker activity
- maintain a severity-sorted queue
- distinguish `live`, `derived`, `preview`, and `unknown`

Sources:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
- [`docs/audit/2026-03-24_connector_certification_execution_report.md`](../audit/2026-03-24_connector_certification_execution_report.md)

### `uiStore`

Responsibilities:

- route-local layout state
- selected symbol/timeframe
- panel expansion, density, and drawer state

Sources:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)

## Polling and SSE strategy

Use one shared SSE connection to `/events`.

Important rule:

- treat `/events` as a repeating live-state stream
- do not model it as an append-only event log

Recommended cadence:

- `/status`: poll every `5s`
- `/positions`: poll every `2s` to `5s`, depending on route
- `/exposure`: poll every `3s` to `5s`
- `/account`: poll every `5s` to `10s`
- `/chart/{symbol}/{timeframe}`: on demand plus route-level refresh
- `/specs` and `/catalog`: load once, then refresh manually or infrequently

The SSE stream should update freshness immediately, but polling should remain authoritative for route-specific data until the backend exposes richer streams.

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py)
- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)

## Boot and warmup UX

The app must define a global boot state before any route becomes operational.

Required warmup states:

- `launching_ui`
- `waiting_for_control_plane`
- `control_plane_detected_syncing`
- `ready`
- `reconnecting`
- `degraded_unavailable`

Required behavior:

- on first load, show a startup animation or boot overlay instead of a blank page
- keep the overlay visible until the first successful `/status` response
- if `/status` is unreachable, show a controlled waiting state, not a fatal crash
- if SSE is not yet available but `/status` succeeds, the app may continue with a degraded live-state badge
- if the backend later disappears, switch to reconnecting or degraded state while preserving the last good snapshot where safe

Recommended boot copy:

- `Starting WebUI`
- `Waiting for control plane`
- `Synchronizing runtime state`
- `Control plane unavailable`

This warmup layer is global application behavior, not a route-specific widget.

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)

## Milestone definition of done

### Milestone 1: shell and data layer

Done when:

- app boots locally
- route shell exists for all primary routes
- HTTP client reaches current control-plane routes
- SSE connection works and exposes freshness state
- no mocked data is required to render the shell

### Milestone 2: supervision core

Done when:

- Runtime Overview is live against `/status`, `/events`, `/account`, `/exposure`
- Operations Console is live against `/positions`, `/exposure`, `/account`
- Terminal / Account Context shows account metrics, recent deals/orders, and specs
- Alerts / Events renders derived alerts and broker activity without pretending to be an audit log

### Milestone 3: risk and drilldown

Done when:

- Risk Center renders live derived risk signals
- symbol drilldown and chart routes are wired and navigable
- catalog/spec drilldowns support operator inspection flows

### Milestone 4: roadmap shells

Done when:

- Fast Desk shows live read context and disabled or preview action lane
- SMC Desk shows live context and preview thesis/zones modules
- Ownership and Live vs Paper routes exist as honest preview surfaces

### Milestone 5: implementation polish

Done when:

- all unknown states are explicit
- stale and degraded states are visually distinct
- preview/planned/disabled semantics are consistent across screens
- no route suggests a live mutation that the backend does not expose

Sources:

- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)
- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)

## Capability-state contract

Use these labels consistently across the app:

- `Live`
- `Derived`
- `Partial`
- `Preview`
- `Planned`
- `Unknown`
- `Disabled`

Interpretation:

- `Live`: directly backed by current control-plane endpoints
- `Derived`: computed from live payloads
- `Partial`: live data exists but the contract is incomplete
- `Preview`: intentional UI shell for a near-future backend surface
- `Planned`: reserved future area only
- `Unknown`: state exists conceptually but current API does not expose it cleanly
- `Disabled`: control is intentionally not available in the current environment

Sources:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)

## Component system

Build these base components before route polish:

- `GlobalStatusStrip`
- `CapabilityBadge`
- `FreshnessBadge`
- `SeverityBadge`
- `MetricCard`
- `DensePanel`
- `DataGrid`
- `AlertList`
- `PreviewPanel`
- `UnknownStateNotice`
- `DisabledActionLane`
- `SymbolHeader`
- `ChartPanel`

These components should be visually consistent across all routes.

Sources:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)

## Prompt execution constraints

Any implementation prompt built from this document must include these constraints verbatim in substance:

- do not modify backend Python code
- do not invent API endpoints
- do not use mock-only placeholders in place of current live routes
- do not enable trade actions in the UI
- do not represent `trade_allowed` as a live known field
- do not infer ownership from comments
- do not collapse roadmap modules into live modules
- do not require backend boot to complete before rendering the frontend shell
- do not fail hard when the backend is still warming up
- do not require backend CORS changes for the first delivery

If the constructor needs a feature that the backend does not expose, it must render a preview shell instead of inventing a contract.

Sources:

- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)
- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`apps/control_plane.py`](../../apps/control_plane.py)

## Screen implementation rules

### Runtime Overview

Build this as the trust screen.

- runtime health is the first payload shown
- alerts must surface above fold
- account and exposure headline can appear, but only after health

Sources:

- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)

### Operations Console

This is the primary working screen in v1.

- positions and exposure are central
- recent orders and recent deals must be shown
- symbol drilldown must be reachable in one click

Sources:

- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
- [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py)

### Terminal / Account Context

- show real broker/account state
- include leverage, margin level, drawdown, and account mode
- treat trading permission as `Unknown` unless future API exposes it

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)

### Alerts / Events

- build from derived alerts plus broker activity
- if needed, split tabs into `Critical`, `Warnings`, `Broker Activity`, `Preview History`
- never imply this is a certified audit log

Sources:

- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`src/heuristic_mt5_bridge/infra/mt5/connector.py`](../../src/heuristic_mt5_bridge/infra/mt5/connector.py)
- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)

### Fast Desk and SMC Desk

- build shells now
- show live context panels where current data supports them
- show action lanes as `Disabled`, `Preview`, or `Planned`
- never render enabled trade buttons until real action endpoints exist

Sources:

- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
- [`docs/plans/2026-03-24_immutable_bridge_action_plan.md`](../plans/2026-03-24_immutable_bridge_action_plan.md)
- [`apps/control_plane.py`](../../apps/control_plane.py)

## Placeholders for non-implemented features

Use exactly three placeholder states for future modules:

- `Preview`: UX shape is intentional; backend surface expected soon
- `Planned`: reserved space only; no implied readiness
- `Disabled`: control exists conceptually but is intentionally not available in the current environment

Examples:

- Fast execution buttons today: `Disabled` or `Preview`, not `Live`
- Ownership board today: `Planned` or `Preview`
- Live vs Paper mode switch today: `Planned`

Sources:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)

## Mandatory restrictions

- Do not infer `trade_allowed` as truth from indirect signals.
- Do not infer ownership from comment fields.
- Do not equate `account_mode` with product `Live/Paper`.
- Do not represent `/events` as a durable event log.
- Do not build top-level settings or env-management routes in v1.
- Do not create generic admin screens just because data exists.
- Do not hide preview status; label it explicitly.
- Do not expose account-switch flows as harmless controls.

Sources:

- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)
- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`docs/audit/2026-03-24_connector_certification_execution_report.md`](../audit/2026-03-24_connector_certification_execution_report.md)

## Anti-patterns to avoid

- generic dashboard SaaS layout
- giant hero cards and low-information whitespace
- too many primary routes
- fake green states for unknown capability
- mixing roadmap panels with live control panels without labels
- enabling action controls behind optimistic assumptions
- exposing raw JSON mental models directly to operators

Sources:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md)

## Minimum acceptance bar

The first shippable frontend is acceptable only if all of the following are true:

- an operator can tell whether the bridge is healthy in under five seconds
- an operator can inspect positions, exposure, and recent broker activity without leaving the main supervision flow
- every future-only feature is visibly marked as non-live
- no screen suggests a control-plane mutation that the backend does not actually expose
- route and component structure are clean enough to absorb future terminal-scoped APIs without redesigning the whole app

Sources:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)
- [`apps/control_plane.py`](../../apps/control_plane.py)

## Prompt-ready handoff

This document is prompt-ready when used together with:

- [`FINAL_DIRECTION.md`](./FINAL_DIRECTION.md)
- [`FINAL_INFORMATION_ARCHITECTURE.md`](./FINAL_INFORMATION_ARCHITECTURE.md)
- [`FINAL_SCREEN_SET.md`](./FINAL_SCREEN_SET.md)
- [`apps/control_plane.py`](../../apps/control_plane.py)
- [`src/heuristic_mt5_bridge/core/runtime/service.py`](../../src/heuristic_mt5_bridge/core/runtime/service.py)

A future implementation prompt should instruct the builder to:

1. read the source precedence section first
2. build only against current HTTP routes
3. implement live supervision surfaces before roadmap shells
4. label every non-live capability explicitly
5. make frontend boot tolerant of backend startup latency
6. use a dev proxy instead of assuming CORS support
7. finish with a self-check against the minimum acceptance bar

## Decision for construction

- Winning base: use the consolidated direction, not any raw proposal. In practice: `codex` backbone, `copilot` operational refinements, limited `qwen` salvage, as defined in [`FINAL_EVALUATION.md`](./FINAL_EVALUATION.md).
- Recommended build sequence: shell and API layer first, then Runtime Overview, then Operations Console, then terminal/account supervision, then alerts, then preview governance modules.
- Pending risks: no HTTP write endpoints, no explicit `trade_allowed` field, no formal ownership API, no true event ledger, no live/paper control contract, and no terminal-scoped multi-instance router yet.
- Depends on future backend: ownership registry, risk kernel, supervisor APIs, live/paper execution mode, desk-specific telemetry, and mutation endpoints.
- Can be built now: supervision, account/exposure/positions UI, chart drilldown, broker activity view, alert derivation, and honest preview shells for future capabilities.
