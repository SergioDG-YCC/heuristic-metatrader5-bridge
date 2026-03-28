# PROMPT: Connector + Core Runtime Constructor

## Recommended model

**Primary for implementation**: `gpt-5.3-codex`  
**Primary for architecture review**: `gpt-5.4`

## Role

You are implementing the first real executable backbone of `heuristic-metatrader5-bridge`.

Your task is to migrate the `MetaTrader5 connector` and build the new `core_runtime` around it without importing the old monolithic office architecture.

This repository is heuristic-first.

The `core_runtime` is not a role office.

It is the operational backbone that must provide:

- broker/account identity
- symbol catalog
- symbol specifications
- active universe market snapshots
- chart-ram
- account and exposure state
- broker sessions registry status
- persistence to runtime db and live files

## Canonical documents

Use these as the only architecture authorities:

1. `README.md`
2. `docs/ARCHITECTURE.md`
3. `docs/plans/2026-03-23_extraction_plan.md`
4. `docs/plans/2026-03-23_repo_structure_async_foundation.md`
5. `docs/plans/2026-03-23_mt5_data_ownership_boundary.md`

## Old repo source of truth for migration

Use these files only as source references, not as target architecture:

1. `../llm-metatrader5-bridge/python/mt5_connector.py`
2. `../llm-metatrader5-bridge/python/market_state_runtime.py`
3. `../llm-metatrader5-bridge/python/account_runtime.py`
4. `../llm-metatrader5-bridge/python/broker_session_runtime.py`
5. `../llm-metatrader5-bridge/python/indicator_enrichment.py`

Do not port the old office stack or old role runtime patterns.

## Objective

Implement the first usable `core_runtime` for the new repo with this shape:

```text
MT5 connector
  -> broker identity
  -> symbol catalog/specs
  -> market snapshots
  -> account/exposure
  -> chart-ram
  -> runtime db
  -> live json state
  -> broker session service integration
```

## Non-negotiable rules

### 1. Keep the new architecture clean

Do not recreate:

- chairman
- analyst runtimes
- trader office queues
- memory systems
- message buses for slow deliberation

### 2. Preserve the important data fixes

The migrated connector must preserve:

- canonical internal `UTC` timestamps for `ohlc.timestamp`
- `server_time_offset_seconds`
- raw broker timestamps as metadata only when useful
- symbol normalization and context symbol handling

### 3. Keep sessions separate

`BrokerSessionsService` stays a specialized service.

The new `core_runtime` must integrate with it, but not merge it into the connector.

### 4. Indicators are optional enrichment

The new `core_runtime` must not require the indicator EA in order to start.

It may import indicator snapshots if available, but the system must remain operational without them.

## Existing new-repo modules you must reuse

These already exist and should be reused instead of rewritten:

- `src/heuristic_mt5_bridge/core/config/env.py`
- `src/heuristic_mt5_bridge/core/config/paths.py`
- `src/heuristic_mt5_bridge/core/runtime/market_state.py`
- `src/heuristic_mt5_bridge/infra/storage/json_files.py`
- `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`
- `src/heuristic_mt5_bridge/infra/sessions/registry.py`
- `src/heuristic_mt5_bridge/infra/sessions/gate.py`
- `src/heuristic_mt5_bridge/shared/symbols/universe.py`
- `src/heuristic_mt5_bridge/shared/time/utc.py`

## Required implementation scope

### A. MT5 connector migration

Create a new connector module under:

- `src/heuristic_mt5_bridge/infra/mt5/connector.py`

It must provide, at minimum:

- connection lifecycle
- broker identity
- symbol resolution
- server time offset estimation
- snapshot fetch
- symbol specification fetch
- available symbol catalog fetch
- account runtime fetch
- symbol tick
- account login / probe
- execution instruction sending

Do not blindly copy the old file.

Refactor only enough to fit the new repo structure.

### B. Core runtime service

Implement a new runtime service layer under:

- `src/heuristic_mt5_bridge/core/runtime/`

Expected outcome:

- a clean service that owns connector lifecycle
- active universe bootstrap
- chart-ram population
- runtime db persistence
- live json publication
- session service startup/integration
- account/exposure refresh

### C. App entrypoint

Turn this into a real runnable process:

- `apps/core_runtime.py`

It must no longer be a stub.

### D. Live state contract

Publish a single live runtime payload, for example:

- `storage/live/core_runtime.json`

It should contain enough data for later UI and downstream desks:

- broker identity
- active universe
- feed status rows
- broker session registry snapshot
- account summary
- chart bootstrap status
- indicator enrichment availability summary
- timestamps and health fields

### E. Runtime DB persistence

Use the existing new-repo `runtime_db.py` to persist:

- market state cache
- symbol spec cache
- symbol catalog cache
- account state cache
- positions
- orders
- exposure state
- execution events

### F. Indicator enrichment hook

Do not build the full indicator subsystem yet.

But leave a clean hook in `core_runtime` for:

- importing indicator snapshots if present
- enriching `MarketStateService`
- reporting indicator health to the live state

This hook must be optional and non-blocking.

## Architectural target

The intended direction is:

```text
apps/core_runtime.py
  -> infra.mt5.connector
  -> core.runtime.market_state
  -> infra.storage.runtime_db
  -> infra.sessions.registry
  -> infra.sessions.gate
  -> optional indicator snapshot importer
```

No LLM.
No office roles.
No prompt loading.

## What to avoid

- do not port `market_state_runtime.py` as a giant single-file clone
- do not hardcode old repo paths
- do not reintroduce old message-cache concepts
- do not make indicators mandatory
- do not make session gating depend on the old JSON file layout
- do not mix SMC-specific logic into the core runtime

## First milestone acceptance criteria

Deliver a state where:

1. `apps/core_runtime.py` runs.
2. MT5 connection initializes cleanly.
3. symbol catalog can be fetched and persisted.
4. symbol specifications can be fetched and persisted.
5. active-universe snapshots populate `MarketStateService`.
6. `chart-ram` is alive for the active universe.
7. account/exposure state is fetched and persisted.
8. broker session registry can be integrated.
9. a live runtime json file is produced.
10. the runtime starts even if the indicator EA is not active.

## Testing expectations

Add or update tests where practical.

At minimum:

- connector-independent tests for runtime helpers
- smoke validation for `core_runtime` imports
- no syntax regressions

If live MT5 cannot be exercised automatically, say so clearly and still validate everything else that can be validated locally.

## Final output requirements

At the end:

- summarize files created
- summarize files migrated
- summarize what came from the old repo and what was redesigned
- state what is runnable now
- state what still remains before building the WebUI

## Implementation style

- favor small cohesive modules over giant monolithic files
- keep data contracts explicit
- keep the hot path operational and deterministic
- build the minimum stable backbone, not abstractions for their own sake
