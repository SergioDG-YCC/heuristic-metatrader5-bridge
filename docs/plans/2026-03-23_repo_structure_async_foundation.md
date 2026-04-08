# Plan: Repo Structure and Async Foundation

**Date**: 2026-03-23  
**Goal**: define the repository and application structure before migrating code, so the new repo does not become another accumulation of monolithic runtimes.

---

## 1. Core decision

The new repo should **not** be:

- a giant collection of `*_runtime.py` files at the root
- a single monolithic process with too many responsibilities
- a fully distributed microservices platform

The right target is:

**modular monolith + async runtimes + process separation only where it matters**

That means:

- one repository
- one codebase
- strong package boundaries
- a few explicit apps/runtimes
- shared contracts
- in-process async eventing where possible
- separate processes only for clearly isolated operational concerns

---

## 2. Architectural style

## Recommended style

### Modular monolith

Use one repo with bounded modules:

- `shared core`
- `fast desk`
- `smc desk`
- `control plane`

Each module should be importable and testable independently.

### Async runtime model

Use `asyncio` as the default orchestration model.

Reason:

- built into Python
- enough for event-driven loops, queues and coordination
- avoids heavy framework overhead
- easy to mix with thread pools for CPU-bound heuristics

### Process model

Use a **small number of explicit apps**, not dozens of small daemons.

Recommended app split:

- `core_runtime`
- `fast_desk_runtime`
- `smc_desk_runtime`
- `control_plane`

Optional later:

- `backtester`
- `research_worker`

---

## 3. Repo structure

## Recommended top-level layout

```text
heuristic-metatrader5-bridge/
  docs/
  apps/
  src/
  tests/
  scripts/
  configs/
  storage/
```

### Why this layout

- `apps/`: process entrypoints only
- `src/`: actual business code
- `tests/`: isolated testing per domain
- `scripts/`: maintenance and migration tools
- `configs/`: environment and runtime profiles
- `storage/`: local runtime state for dev/live runs

This avoids mixing:

- business logic
- runtime launchers
- docs
- ops scripts
- storage

in the same root.

---

## 4. Python package structure

## Recommended `src/` layout

```text
src/heuristic_mt5_bridge/
  core/
  infra/
  shared/
  fast_desk/
  smc_desk/
  control_plane/
```

### 4.1 `core/`

Purpose:

- system-wide contracts
- config
- event model
- runtime primitives
- common typing and schemas

Suggested contents:

```text
core/
  config/
  events/
  models/
  runtime/
  clock/
  ids/
```

### 4.2 `infra/`

Purpose:

- concrete adapters to external systems

Suggested contents:

```text
infra/
  mt5/
  storage/
  indicators/
  sessions/
  logging/
  telemetry/
```

### 4.3 `shared/`

Purpose:

- reusable helpers that are domain-neutral

Suggested contents:

```text
shared/
  math/
  prices/
  symbols/
  time/
  serialization/
```

### 4.4 `fast_desk/`

Purpose:

- low-latency signal, risk and custody

Suggested contents:

```text
fast_desk/
  signals/
  risk/
  custody/
  execution/
  workers/
  policies/
  state/
```

### 4.5 `smc_desk/`

Purpose:

- slower heuristic-first prepared setups

Suggested contents:

```text
smc_desk/
  scanner/
  analyst/
  validators/
  trader/
  chart_rendering/
  llm/
  state/
```

### 4.6 `control_plane/`

Purpose:

- API
- observability
- local UI

Suggested contents:

```text
control_plane/
  api/
  views/
  sse/
  dto/
```

---

## 5. App entrypoints

Keep runtime entrypoints thin.

## Recommended `apps/` layout

```text
apps/
  core_runtime.py
  fast_desk_runtime.py
  smc_desk_runtime.py
  control_plane.py
  dev_stack.py
```

Rule:

Each app should do only:

1. load config
2. build container/wiring
3. start tasks
4. own lifecycle and shutdown

No business logic should live in `apps/`.

---

## 6. Async design rules

## 6.1 Default primitive

Use:

- `asyncio.TaskGroup`
- `asyncio.Queue`
- `asyncio.Event`
- `asyncio.Lock`

Prefer built-ins first.

## 6.2 CPU-bound heuristics

For CPU-heavy heuristics:

- use `asyncio.to_thread()`
- or explicit thread pools

Do not fake CPU work as async if it blocks the loop.

## 6.3 Blocking IO

For blocking adapters:

- isolate behind adapter classes
- wrap carefully if the external library is synchronous

This matters especially for MT5 and some file/SQLite operations.

## 6.4 Event-driven over poll-heavy

Prefer:

- symbol wakeups
- position wakeups
- material-change wakeups

over:

- global loops that scan everything every few seconds

Some polling is unavoidable, but it should be local and intentional.

---

## 7. Recommended micro-framework stack

Use a small async-friendly stack.

## Must-have

- `asyncio`
- `pydantic`
- `pydantic-settings`
- `fastapi` for control plane
- `uvicorn` for local serving
- `httpx` for async HTTP

## Likely useful

- `aiosqlite` if SQLite is kept in async loops
- `orjson` for fast serialization
- `structlog` or standard structured logging
- `tenacity` for retry wrappers

## Optional later

- `msgspec` if serialization becomes a bottleneck
- `polars` or `pandas` for research and slower analytics

## Not recommended at bootstrap

- Celery
- Kafka
- Redis dependency for core orchestration
- heavy service mesh logic

The new repo should stay local-first and operationally simple.

---

## 8. Data and state boundaries

## Shared Core state

Shared Core owns:

- market state
- account state
- positions
- orders
- symbol specs
- broker session registry
- indicator snapshots

## Fast Desk state

Fast Desk owns:

- signal state
- open setup state
- custody decisions
- per-position guardian state

## SMC Desk state

SMC Desk owns:

- zone cache
- event log
- heuristic thesis state
- validation state
- optional llm review artifacts

Rule:

Each desk owns its own domain state.  
Shared Core only owns neutral operational state.

---

## 9. Contract design

Do not rely on ad-hoc dicts everywhere like the old repo ended up doing.

Use explicit models for:

- `MarketSnapshot`
- `AccountSnapshot`
- `PositionSnapshot`
- `OrderSnapshot`
- `FastSignal`
- `FastRiskDecision`
- `CustodyAction`
- `SmcZone`
- `SmcHeuristicThesis`
- `SmcValidationResult`

These can be `pydantic` models or typed dataclasses, but they must be explicit.

---

## 10. Fast Desk structural rules

Fast Desk should be decomposed by responsibility, not by giant runtime file.

## Recommended split

### `signals/`

- setup detection
- microstructure logic
- reversal logic
- entry conditions

### `risk/`

- position sizing
- max exposure
- cross-position limits
- session and volatility guards

### `custody/`

- break-even
- trailing
- fast take-profit
- loss cut
- invalidation exit

### `workers/`

- symbol worker
- position worker
- account guard worker

---

## 11. SMC Desk structural rules

SMC should also avoid monoliths.

## Recommended split

### `scanner/`

- zone detection orchestration
- event emission

### `analyst/`

- heuristic thesis construction

### `validators/`

- regime checks
- side compatibility
- SL/TP geometry
- R:R checks
- consistency checks

### `llm/`

- minimal validator runtime
- multimodal chart review
- prompt builders

### `chart_rendering/`

- chart snapshots for the multimodal validator

This is important because image-based SMC validation is now a first-class option.

---

## 12. Configuration strategy

Do not keep one giant `.env` with every concern mixed together from day one.

Recommended:

```text
configs/
  base.env
  core.env
  fast_desk.env
  smc_desk.env
  local.dev.env
```

Load order:

- base
- app-specific
- environment override

This keeps desks from inheriting each other's irrelevant settings.

---

## 13. Testing layout

Use domain-level tests from the start.

```text
tests/
  core/
  infra/
  fast_desk/
  smc_desk/
  integration/
```

Priority:

1. unit tests for heuristics
2. contract tests for models
3. integration tests for runtime wiring

Fast Desk especially should have deterministic tests around:

- trailing
- loss cut
- reversal take-profit
- session gating
- sizing

---

## 14. Migration policy

When code starts moving, use this rule:

- move infra and core first
- rebuild fast desk intentionally
- migrate SMC only after its new heuristic-first design is clear

Do not copy old root-level runtime files into `src/` and call it architecture.

---

## 15. Recommended next step

Before any major code migration, create the physical skeleton:

```text
apps/
src/heuristic_mt5_bridge/
  core/
  infra/
  shared/
  fast_desk/
  smc_desk/
  control_plane/
tests/
scripts/
configs/
```

Then implement only the first migration target:

**Shared Core**

Specifically:

- MT5 connector
- market state
- account state
- broker sessions
- indicator enrichment
- execution bridge

Only after that should `fast_desk/` begin.

