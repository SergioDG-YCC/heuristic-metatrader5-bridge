# PROMPT: Core Runtime Subscription Refactor Constructor

## Recommended model

**Primary for implementation**: `gpt-5.3-codex`  
**Primary for architecture review**: `gpt-5.4`

## Role

You are correcting the existing `core_runtime` implementation in `heuristic-metatrader5-bridge`.

This is not a greenfield build.

The repo already has:

- MT5 connector
- core runtime
- sessions service
- indicator bridge
- runtime DB
- RAM chart service

Your task is to refactor the current runtime so it matches the intended subscription-driven architecture.

## Canonical documents

Use these as authoritative:

1. `README.md`
2. `docs/ARCHITECTURE.md`
3. `docs/plans/2026-03-23_mt5_data_ownership_boundary.md`
4. `docs/plans/2026-03-23_chart_ram_runtime_architecture.md`
5. `docs/plans/2026-03-23_core_runtime_subscription_refactor_plan.md`

## Current problem to correct

The current implementation wrongly treats too many broker symbols as live-active.

It currently:

- discovers the full broker catalog correctly
- but derives `active_universe` from broker `visible/selected` symbols
- polls dynamic OHLC/feed state for too many symbols
- writes too much dynamic state to live JSON / SQLite

This must be corrected.

## Architectural target

The corrected runtime must follow this model:

- one connector owner
- one subscription registry
- one chart worker per subscribed symbol
- chart state lives in RAM
- only subscribed symbols receive dynamic live updates
- startup subscription comes from `.env`
- future front-driven subscribe/unsubscribe must already be supported by the internal design

## Non-negotiable rules

### 1. Full broker catalog stays available

The runtime must still fetch the full operable broker catalog from MT5.

That is required for future WebUI symbol selection.

### 2. Dynamic polling must be limited

Only the `subscribed_universe` may receive:

- live OHLC refresh
- live tick/feed updates
- indicator refresh
- session-driven dynamic handling

### 3. `.env` is the initial live subscription source

Until the WebUI exists, `.env` defines the initial subscribed symbols.

Do not replace `.env` with broker-visible symbols.

### 4. RAM is the hot-path source of truth

The chart virtual state must live in RAM.

Disk is not the runtime bus.

### 5. Connector access must have a single owner

Do not create per-symbol workers that call MT5 directly.

Correct pattern:

- one connector ingress owner
- per-symbol workers receiving updates from ingress

## Existing files to refactor

Primary files:

- `src/heuristic_mt5_bridge/core/runtime/service.py`
- `src/heuristic_mt5_bridge/core/runtime/market_state.py`
- `src/heuristic_mt5_bridge/infra/sessions/service.py`
- `src/heuristic_mt5_bridge/infra/indicators/bridge.py`

You may add new modules under:

- `src/heuristic_mt5_bridge/core/runtime/`

Suggested additions:

- `subscriptions.py`
- `chart_registry.py`
- `chart_worker.py`
- `ingress.py`

## Required implementation scope

### A. Split universe concepts

Introduce explicit runtime objects for:

- `catalog_universe`
- `bootstrap_universe`
- `subscribed_universe`
- `active_chart_workers`

These must not be collapsed into one overloaded `active_universe`.

### B. Subscription manager

Implement a subscription manager that:

- starts from `.env`
- can add symbols
- can remove symbols
- can report the current subscribed universe

Even if the WebUI is not implemented yet, this API must exist now.

### C. Symbol chart workers

Implement one worker per subscribed symbol.

Each symbol worker must own RAM state for all configured timeframes from `.env`.

Each symbol worker must receive updates from a connector ingress owner, not call MT5 directly.

### D. Connector ingress owner

Implement or refactor an ingress layer that:

- serializes MT5 API access
- fetches dynamic updates only for subscribed symbols
- fans out updates to symbol workers

### E. Chart RAM

Keep the current rolling candle logic, but make the runtime explicitly chart-worker-driven.

Required behavior:

- each subscribed symbol has RAM charts
- each timeframe keeps the configured number of bars
- market_state stays in RAM

### F. Persistence policy correction

Keep persistence for:

- broker catalog
- symbol specs
- account state
- positions/orders
- exposure
- execution events

Reduce disk usage for:

- dynamic chart transport
- giant live feed dumps

If `market_state_cache` remains, use it only as lightweight operational checkpoint, not as the live runtime bus.

### G. Live JSON correction

`storage/live/core_runtime.json` must become a control-plane artifact only.

It may include:

- status
- broker identity
- subscribed universe
- worker counts
- health
- last heartbeat
- indicator/session service health

It must not include:

- full dynamic feed dumps
- large per-symbol chart contexts for all symbols
- chart transport payloads

### H. Session integration

Broker sessions must track the subscribed universe, not the broker-visible universe.

### I. Indicator integration

Indicator enrichment must remain optional and non-blocking.

It should only matter for subscribed symbols/timeframes.

## Constraints

- do not rewrite the whole repo from scratch
- do not break the connector data fixes
- do not move chart transport to disk
- do not let symbol workers each own an MT5 client
- do not add LLM or prompt logic
- do not build the WebUI now, only the internal hooks for it

## Acceptance criteria

Deliver a state where:

1. full broker catalog still loads
2. initial subscribed universe comes only from `.env`
3. only subscribed symbols get live dynamic polling
4. one chart worker exists per subscribed symbol
5. each chart worker owns all configured timeframes
6. chart state remains in RAM
7. `core_runtime.json` is reduced to control-plane status
8. subscription add/remove hooks exist for future WebUI integration

## Testing expectations

Add/update tests for:

- `.env` bootstraps the subscribed universe
- broker-visible extra symbols do not get dynamic polling
- chart workers are created per subscribed symbol
- chart workers stop when unsubscribed
- RAM chart state is accessible without disk reads
- live JSON remains small and status-oriented

If live MT5 cannot be fully exercised automatically, validate everything possible with tests and explain the remaining live-only checks.

## Final output requirements

At the end:

- summarize files changed
- summarize what behavior was corrected
- explain the new runtime topology
- explain what remains before adding WebUI symbol activation
