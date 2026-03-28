# Core Runtime Subscription Refactor Plan

Date: 2026-03-23

## Goal

Correct the current `core_runtime` so it matches the intended architecture:

- one owner of the MT5 connector
- one live subscription registry
- one chart worker per subscribed symbol
- chart state in RAM
- no disk I/O in the hot path
- startup from `.env`
- future-ready symbol activation/deactivation from WebUI

This is a correction of the current repo, not a fresh rewrite.

## Current mismatch

The current runtime has four key deviations:

1. it discovers the full broker catalog correctly, but it also derives the live universe from `visible/selected` broker symbols;
2. it polls dynamic data for too many symbols instead of only the subscribed universe;
3. it persists too much dynamic runtime data to SQLite / live JSON;
4. it exposes a large live state file instead of treating RAM as the primary runtime state.

## Target model

### Universes must be split

The runtime must explicitly manage:

- `catalog_universe`
- `bootstrap_universe`
- `subscribed_universe`
- `active_chart_workers`

### Ownership model

- `connector_ingress` owns MT5 API access
- `subscription_manager` owns live subscriptions
- `chart_worker[symbol]` owns symbol-local RAM state
- desks consume chart state from RAM/IPC views

### Startup policy

At startup:

- load full broker catalog
- load specs as needed
- bootstrap only symbols from `.env`
- create live subscriptions only for `.env` symbols
- create one chart worker per subscribed symbol

### Future UI policy

Later, WebUI should be able to:

- list full catalog
- activate a symbol
- deactivate a symbol
- inspect worker health

That API contract must be designed now, even if the UI is not implemented yet.

## Required refactor scope

### 1. `core_runtime.service`

File:

- `src/heuristic_mt5_bridge/core/runtime/service.py`

Changes:

- stop deriving live universe from all `visible/selected` broker symbols
- introduce explicit `bootstrap_universe` from `.env`
- introduce explicit `subscribed_universe`
- introduce a symbol subscription manager
- separate catalog refresh from dynamic market refresh
- reduce `core_runtime.json` to control-plane health/status, not dynamic transport

### 2. Chart RAM manager

New module(s) recommended under:

- `src/heuristic_mt5_bridge/core/runtime/`

Examples:

- `subscriptions.py`
- `chart_registry.py`
- `chart_worker.py`
- `ingress.py`

Responsibility split:

- `ingress`: polls connector for subscribed symbols only
- `chart_worker[symbol]`: receives updates and owns RAM buffers for all configured timeframes
- `chart_registry`: exposes read-only chart access

### 3. `MarketStateService`

File:

- `src/heuristic_mt5_bridge/core/runtime/market_state.py`

Changes:

- keep it as the RAM chart backbone
- adapt it so symbol-local workers can own/write state
- preserve current deque-based rolling chart model

### 4. Persistence policy

File:

- `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`

Keep persistence for:

- symbol catalog
- symbol specs
- account state
- positions/orders
- exposure
- execution events

Reduce or remove hot-path persistence of:

- every live dynamic market refresh as transport

If `market_state_cache` remains, it must be a lightweight snapshot/checkpoint, not the live bus.

### 5. Live file policy

File:

- `storage/live/core_runtime.json`

New role:

- health/status only
- broker identity
- service status
- subscribed universe
- worker counts
- heartbeat

Do not use it as:

- chart transport
- giant feed dump
- primary market-state interface

### 6. Indicator path

File:

- `src/heuristic_mt5_bridge/infra/indicators/bridge.py`

Keep:

- optional
- non-blocking
- only for subscribed symbols/timeframes

Do not make it mandatory for the chart worker to exist.

### 7. Session path

Files:

- `src/heuristic_mt5_bridge/infra/sessions/service.py`
- `src/heuristic_mt5_bridge/infra/sessions/registry.py`

Keep:

- broker sessions as specialized service
- session registry accessible by subscribed symbol

Make sure session refresh tracks the `subscribed_universe`, not the broker-visible universe.

## Suggested runtime topology

### Process level

- `core_runtime`
- `fast_desk_runtime`
- `smc_desk_runtime`
- `control_plane`

### Inside `core_runtime`

- `connector_ingress_task`
- `subscription_manager`
- `chart_worker[symbol]`
- `account_state_task`
- `catalog_specs_task`
- `indicator_import_task`
- `sessions_service`
- `control_plane_snapshot_task`

## Important design rule

Do not let every chart worker call MT5 directly.

Correct approach:

- one connector owner
- many symbol-local workers consuming updates from ingress

This keeps MT5 access serialized and the architecture predictable.

## Minimal implementation strategy

### Phase 1

- split universes
- restrict polling to `.env` subscribed symbols
- reduce live JSON
- keep one process

### Phase 2

- add explicit symbol chart workers
- add subscription manager API
- expose read-only chart registry

### Phase 3

- wire desks to consume chart registry / IPC
- add control-plane symbol activation/deactivation

## Acceptance criteria

The correction is successful if:

1. broker catalog still loads fully from MT5
2. initial live subscriptions come only from `.env`
3. only subscribed symbols get live OHLC/tick refreshes
4. one chart worker exists per subscribed symbol
5. chart state lives in RAM, not in JSON
6. `core_runtime.json` becomes a health/control artifact only
7. the runtime remains ready for future WebUI-driven symbol activation

## Tests to add

- bootstrap uses `.env` symbols as the initial subscribed universe
- broker-visible but unsubscribed symbols do not get live polling
- adding a symbol creates a worker
- removing a symbol stops its worker
- chart buffers remain in RAM and do not require disk reads
- live JSON stays small and does not contain feed dumps

## Non-goals for this refactor

- full WebUI implementation
- full fast desk implementation
- full SMC runtime implementation
- replacing the indicator EA protocol

This refactor is only to make the core runtime correct and future-safe.

---

## RESTRICCIONES OBLIGATORIAS — Correcciones del audit 2026-03-23

Las siguientes reglas anulan cualquier implementación anterior que las contradiga.

### core_runtime.json no debe existir

El test `live JSON stays small and does not contain feed dumps` fue insuficiente como criterio de aceptación. La corrección definitiva es:

- `storage/live/core_runtime.json` **no debe existir en absoluto**
- el loop de publicación a disco (`_publish_live_state`, `build_live_state`) **no debe existir**
- la variable de entorno `CORE_LIVE_PUBLISH_SECONDS` **no debe existir**
- cualquier llamada a `persist_json()` dentro de un loop de runtime **no debe existir**

El estado del runtime se expone únicamente a través del Control Plane HTTP.

### Columnas prohibidas en SQLite

El refactor no debe introducir ni conservar las siguientes columnas en ninguna tabla:

```sql
bid REAL,
ask REAL,
last_price REAL,
tick_age_seconds REAL,
bar_age_seconds REAL,
feed_status TEXT,
```

Estas columnas solo pueden existir en RAM (estructuras Python en proceso).

### Partición por broker en todas las tablas

El test de aceptación `bootstrap uses .env symbols as the initial subscribed universe` es correcto. Se añade:

- toda tabla SQLite con datos broker-dependientes **debe** incluir `(broker_server, account_login)` en la PK
- en particular, `symbol_spec_cache` y `market_state_cache` deben usar PK compuesta `(broker_server, account_login, symbol)`
- ninguna tabla usa `symbol` como PK única si el dato es broker-dependiente

### indicator_snapshots en disco: prohibido

El `IndicatorBridge` aplica los snapshots al estado en RAM. No debe copiar archivos a `storage/indicator_snapshots/`. Esa carpeta no debe tener archivos creados por el runtime.

### pip_size_for_symbol: prohibido

No debe existir ninguna función `pip_size_for_symbol()` con valores hardcoded para activos concretos (BTC, JPY, etc.). El único origen de `tick_size`, `point`, `digits` y `pip_value` debe ser `SymbolSpecRegistry`, que a su vez lee desde el connector MT5 o la caché SQLite de specs correctamente particionada.
