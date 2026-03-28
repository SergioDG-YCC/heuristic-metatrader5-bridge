# Auditoría Técnica: `heuristic-metatrader5-bridge`
**Fecha:** 2026-03-23 · **Auditor:** GitHub Copilot · **Idioma:** Español

---

## 1. Hallazgos (ordenados por severidad)

---

### F-01 — CRÍTICO | Control Plane no está implementado

**Archivo:** `apps/control_plane.py`

**Comportamiento actual:**
```python
def main() -> int:
    print("control_plane bootstrap pending")
    return 0
```

**Por qué viola la arquitectura:**
El diseño exige que el Control Plane sea la pasarela entre el estado RAM del `CoreRuntimeService` y la futura WebUI. Actualmente no existe. Cualquier consumidor externo (incluyendo futura WebUI, Fast Desk, SMC Desk) no tiene acceso al estado en RAM del core_runtime por ninguna vía programática: solo pueden leer del archivo JSON en disco.

**Impacto operativo:** Sin Control Plane, la arquitectura de "RAM como fuente de verdad" es física pero inaccesible. El estado del runtime es efectivamente opaco para todos los procesos distintos al `core_runtime` mismo.

---

### F-02 — CRÍTICO | Fast Desk y SMC Desk son stubs vacíos

**Archivos:** `apps/fast_desk_runtime.py`, `apps/smc_desk_runtime.py`

**Comportamiento actual:** Ambos imprimen un mensaje y terminan.

**Por qué viola la arquitectura:**
La separación `Fast Desk / SMC Desk` es el objetivo arquitectónico central de este repo. La ruta crítica de ejecución sin LLM (Fast Desk) no existe. El estado RAM del `ChartRegistry` ni siquiera tiene una API de consumo IPC definida.

**Impacto operativo:** El sistema no puede ejecutar trades. La infraestructura de core está construida sin receptor.

---

### F-03 — CRÍTICO | `storage/live/core_runtime.json` actúa como bus de datos dinámicos, no como heartbeat

**Archivo:** `src/heuristic_mt5_bridge/core/runtime/service.py` — método `build_live_state()` (~línea 490)

**Comportamiento actual:**
El JSON live (actualizado cada **1 segundo** por defecto vía `CORE_LIVE_PUBLISH_SECONDS=1`) contiene:
- `feed_status`: array de 20 filas (5 símbolos × 4 timeframes), cada una con `bid`, `ask`, `last_price`, `tick_age_seconds`, `bar_age_seconds`, `poll_duration_ms`, `local_clock_drift_ms`
- `account_summary`: balance, equity, margin completos
- `exposure_state`: exposición por símbolo
- `broker_session_registry`: estado completo de sesiones

**Por qué viola la arquitectura:**
El plan `docs/plans/2026-03-23_core_runtime_subscription_refactor_plan.md` especifica explícitamente:
> "Do not use it as: chart transport, giant feed dump, primary market-state interface"

El archivo tiene en la práctica ~800 líneas y contiene precios en tiempo real escritos continuamente. Si algún proceso lee este archivo como fuente de mercado, el disco se convierte en bus de transporte.

**Impacto operativo:**
- Write continua cada 1s al disco sin beneficio si nadie lee el archivo
- Ningún proceso debería consumir `bid`/`ask`/`last_price` de este archivo; si lo hicieran, la latencia sería ~1s
- El archivo es un artefacto de diagnóstico tratado como API

---

### F-04 — ALTO | `symbol_spec_cache` sin partición por broker/cuenta — riesgo de corrupción cross-broker

**Archivo:** `src/heuristic_mt5_bridge/infra/storage/runtime_db.py` — tabla `symbol_spec_cache` (~línea 65)

**Comportamiento actual:**
```sql
CREATE TABLE IF NOT EXISTS symbol_spec_cache (
    symbol TEXT PRIMARY KEY,
    ...
    broker_server TEXT,
```

La `PRIMARY KEY` es solo `symbol`. No hay partición por `broker_server` ni `account_login`.

**Por qué viola la arquitectura:**
Si el operador cambia de broker (ej. de FBS-Real a ICMarkets), los valores críticos de `tick_value`, `contract_size`, `margin_initial`, `volume_min/max/step` del broker anterior permanecen en SQLite sin invalidación. Estos valores **difieren entre brokers** y son esenciales para sizing real de órdenes.

El plan `docs/plans/2026-03-23_mt5_data_ownership_boundary.md` requiere que si broker/cuenta cambia, datos stale no sobrevivan.

**Impacto operativo:** Lot sizing silenciosamente incorrecto tras cambio de broker. Error potencialmente financiero.

---

### F-05 — ALTO | `market_state_cache` en SQLite persiste `bid`/`ask`/`tick_age_seconds` como campos relacionados con dynamic feed

**Archivo:** `src/heuristic_mt5_bridge/infra/storage/runtime_db.py` — tabla `market_state_cache` (~línea 52), y `service.py` — método `_persist_market_state_checkpoint()` (~línea 215)

**Comportamiento actual:**
Cada checkpoint (defecto: 30 segundos) escribe `bid`, `ask`, `last_price`, `feed_status`, `tick_age_seconds`, `bar_age_seconds` en SQLite como columnas.

**Por qué viola la arquitectura:**
El plan establece que el checkpoint de market_state es un artefacto de recuperación, no un bus de feed. El `bid`/`ask` en un checkpoint de 30 segundos no tiene utilidad predictiva — un precio de hace 30 segundos en forex/crypto es ruido. Su presencia como columnas diferenciadas (no en el `state_summary_json`) implica que están disponibles para queries directos desde SQLite.

Adicionalmente, esta tabla tampoco tiene partición por broker/cuenta.

**Impacto operativo:** Si Control Plane o cualquier proceso lee `bid`/`ask` de `market_state_cache`, recibe precios potencialmente obsoletos de 30 segundos sin advertencia de staleness en el schema.

---

### F-06 — ALTO | Sessions service inoperativo: `running: false`, todos los símbolos en `pending`

**Archivo:** `storage/live/core_runtime.json` — campo `broker_session_registry`

**Comportamiento actual:**
```json
"service": { "running": false },
"pending_symbols": ["BTCUSD", "EURUSD", "GBPUSD", "USDCHF", "USDJPY"],
"session_groups": {}
```

El TCP server de sesiones levanta pero ningún EA MQL5 se conecta. Todos los símbolos están en pending indefinidamente.

**Por qué viola la arquitectura:**
Sin datos de sesiones, el runtime opera sin awareness de horarios de trading del broker. No puede determinar si un mercado está abierto o cerrado. El `docs/ARCHITECTURE.md` lista `broker_session_runtime` como responsabilidad clave del Shared Core.

**Impacto operativo:** No se puede determinar session-aware trading. El Fast Desk operaría ciego respecto a open/closed market status.

---

### F-07 — ALTO | `fetch_symbol_specification` mezcla specs estáticas con precios dinámicos (`bid`/`ask`)

**Archivo:** `src/heuristic_mt5_bridge/infra/mt5/connector.py` — método `fetch_symbol_specification()` (~línea 295)

**Comportamiento actual:**
```python
return {
    ...
    "tick_size": float(getattr(info, "trade_tick_size", 0.0) or 0.0),  # estático ✓
    ...
    "bid": bid,   # ← dinámico ✗
    "ask": ask,   # ← dinámico ✗
}
```

Y en la tabla `symbol_spec_cache`:
```sql
bid REAL,
ask REAL,
```

**Por qué viola la arquitectura:**
Las especificaciones de símbolo (`tick_size`, `volume_min`, `contract_size`) son prácticamente estáticas. Mezclarlas con `bid`/`ask` (que cambian múltiples veces por segundo) corrompe la semántica de la tabla: un cache de spec con `bid=70669.86` guardado hace 10 minutos es semánticamente incorrecto si se interpreta como precio actual.

**Impacto operativo:** Cualquier consumidor que lea `bid`/`ask` de `symbol_spec_cache` recibe precios stale sin advertencia.

---

### F-08 — MEDIO | `IndicatorBridge` acumula copias locales en `storage/indicator_snapshots/` sin purga

**Archivo:** `src/heuristic_mt5_bridge/infra/indicators/bridge.py` — método `import_snapshots()` (~línea 75)

**Comportamiento actual:**
```python
persist_json(self.local_snapshots_dir / f"{snapshot['request_id']}.json", snapshot)
```

Cada snapshot importado se copia a `storage/indicator_snapshots/`. Los archivos no se purgan nunca.

**Por qué viola la arquitectura:**
Los archivos fuente en `MT5_COMMON_FILES_ROOT/indicator_snapshots/` sí se eliminan tras importar (`path.unlink()`). Pero las copias locales se acumulan indefinidamente. No hay beneficio documentado de estos archivos locales: el snapshot ya está aplicado a la RAM del `MarketStateService`.

**Impacto operativo:** Acumulación de disco indefinida en producción. No representa un hot-path transport violation, pero es accidental noise.

---

### F-09 — MEDIO | `pip_size_for_symbol()` en `market_state.py` usa heurística hardcodeada en vez de symbol_spec real

**Archivo:** `src/heuristic_mt5_bridge/core/runtime/market_state.py` — función `pip_size_for_symbol()` (~línea 12)

**Comportamiento actual:**
```python
def pip_size_for_symbol(symbol: str) -> float:
    if any(marker in normalized for marker in crypto_markers):
        return 1.0
    if normalized.endswith("JPY"):
        return 0.01
    return 0.0001
```

**Por qué viola la arquitectura:**
La especificación real de pip (`point`, `tick_size`) ya está disponible en `symbol_spec_cache` (SQLite) y en RAM vía `self.symbol_specifications` en `CoreRuntimeService`. Usar una estimación heurística para un valor que se carga explícitamente en startup es innecesariamente frágil.

**Impacto operativo:** Pip size incorrecto para instrumentos no convencionales (indices, algunos CFDs). Si este valor se usa para cálculo de riesgo o SL/TP en Fast Desk, introduce error en sizing.

---

### F-10 — MEDIO | Live publish cada 1 segundo escribe precios completos al disco — escritura innecesaria

**Archivo:** `src/heuristic_mt5_bridge/core/runtime/service.py` — `run_forever()` (~línea 440)

**Comportamiento actual:**
```python
tg.create_task(
    self._loop_wrapper("live_state", self.config.live_publish_seconds, self._persist_live_state)
)
```

`CORE_LIVE_PUBLISH_SECONDS=1` por defecto. Escribe ~800 líneas de JSON al disco cada segundo.

**Por qué viola la arquitectura:**
El plan define el JSON live como "health/status only". No tiene sentido escribir precios en tiempo real cada 1 segundo a un archivo que según el diseño debería ser solo heartbeat.

**Impacto operativo:** I/O de disco innecesario en producción. En sistemas con almacenamiento lento (ej. VPS con disco giratorio), puede introducir latencia en el event loop Python.

---

### F-11 — BAJO | `broker_session_registry` completo en `build_live_state()` amplifica el schema bloat

**Archivo:** `src/heuristic_mt5_bridge/core/runtime/service.py` — `build_live_state()` (~línea 478)

**Comportamiento actual:**
```python
"broker_session_registry": broker_sessions,  # ← snapshot completo de sesiones
```

Incluye `session_groups`, `symbol_to_session_group` (con todos los horarios por día), `active_symbols`, etc.

**Por qué viola la arquitectura:**
El JSON live no es el lugar para exponer el snapshot completo de sesiones. Un indicator de salud (`"broker_sessions": "up/down"`) es suficiente para un control-plane heartbeat.

---

### F-12 — BAJO | `local_clock_warning` activo en 4 de 5 símbolos en el JSON live

**Archivo:** `storage/live/core_runtime.json`

**Comportamiento actual:**
`clock_warning: true` con `local_clock_drift_ms ≈ -1500ms` a `-2500ms` en EURUSD, GBPUSD, USDCHF, USDJPY. Solo BTCUSD está dentro del threshold.

**Por qué importa:**
El threshold para `clock_warning` es `abs(drift) > 1500ms` (ver `chart_worker.py`). Un drift de -2500ms en EURUSD sugiere que el reloj local del sistema está ~2.5 segundos por delante del servidor del broker (FBS-Real reporta UTC+2). Operativamente, las alertas de clock están "siempre encendidas" para estos símbolos, lo que degrada su valor de señal.

---

## 2. Veredicto Arquitectónico

### Estado general: **Parcialmente alineado**

| Componente | Estado |
|---|---|
| Separación de universos (catalog / bootstrap / subscribed) | ✅ Implementado correctamente |
| `SubscriptionManager` con lock thread-safe | ✅ Correcto |
| `ConnectorIngress` con ownership único del MT5 API | ✅ Correcto |
| `ChartWorker` por símbolo con RAM deque | ✅ Correcto |
| Polling solo para `subscribed_universe` | ✅ Correcto |
| `symbol_catalog_cache` con partición `(broker_server, account_login, symbol)` | ✅ Correcto |
| Subscribe/Unsubscribe API preparada para WebUI | ✅ Existe en `service.py` |
| `core_runtime.json` como heartbeat minimal | ❌ Actúa como dump dinámico |
| Control Plane implementado | ❌ Stub vacío |
| Fast Desk implementado | ❌ Stub vacío |
| `symbol_spec_cache` con partición por broker | ❌ Solo `symbol` como PK |
| Sessions service operativo | ❌ `running: false`, pending forever |
| Indicator bridge (transitorio aceptable) | ⚠️ Aceptable transitoriamente, pero con acumulación de archivos locales |

---

## 3. Tabla RAM/Disk Boundary

| Dominio de datos | Fuente de verdad | Dónde vive ahora | Dónde debería vivir | ¿Aceptable? |
|---|---|---|---|---|
| Chart state (OHLC deque) | MT5 connector | RAM — `MarketStateService` (deque) | RAM | ✅ Correcto |
| Feed status (`bid`, `ask`, `tick_age`) | `ChartWorker` RAM | RAM **+** JSON live (cada 1s) | Solo RAM | ❌ JSON debe eliminarse |
| Symbol specs operativos | MT5 connector | SQLite `symbol_spec_cache` (sin partición broker) | SQLite **con** partición broker | ⚠️ Fix requerido |
| Symbol catalog | MT5 connector | SQLite (con partición correcta) | SQLite | ✅ Correcto |
| Account state | MT5 connector | RAM (`account_payload`) + SQLite | RAM + SQLite | ✅ Aceptable |
| Posiciones/Órdenes | MT5 connector | SQLite | SQLite | ✅ Aceptable |
| Exposure state | MT5 connector | RAM + SQLite | RAM + SQLite | ✅ Aceptable |
| Market state checkpoint | `ChartWorker` | SQLite (cada 30s, incluye `bid`/`ask`) | SQLite (sin `bid`/`ask` como columnas top-level) | ⚠️ Transitoriamente aceptable con caveat |
| Indicator snapshots (fuente) | EA MQL5 → CommonFiles | Files (MT5 Common Files) | Files → RAM (transitorio) | ⚠️ Aceptable como transitorio |
| Indicator snapshots (copia local) | IndicatorBridge | `storage/indicator_snapshots/*.json` (acumulación) | No necesario | ❌ Acumulación no controlada |
| Session registry | MQL5 sessions service (TCP) | RAM module-level (`registry.py`) | RAM | ✅ Correcto en diseño |
| Sessions service | MQL5 EA externo | TCP server esperando conexión | TCP server (EA debe conectarse) | ⚠️ EA no conectado |
| Control plane state | `CoreRuntimeService` RAM | Inaccesible (sin API) | RAM + API REST/SSE | ❌ No implementado |
| JSON live heartbeat | `CoreRuntimeService` | JSON file ~800 líneas / 1s | JSON file minimal ~30 líneas / 5-10s | ❌ Sobredimensionado |

---

## 4. Veredicto de Startup Readiness para Trading

### ¿Puede el runtime actual calcular lot sizing real para símbolos suscritos?

**Sí, pero solo marginalmente.** El startup llama a `_refresh_symbol_specs()` para cada símbolo suscrito, que captura `tick_size`, `tick_value`, `contract_size`, `volume_min/max/step`, `stops_level_points`, `freeze_level_points`. Todo lo necesario está disponible en `self.symbol_specifications` (RAM) y en SQLite.

**Excepción:** `pip_size_for_symbol()` en `market_state.py` (F-09) usa una función heurística hardcodeada que no consulta el spec real. Si este valor fluye al Fast Desk para cálculos de riesgo, los resultados serán incorrectos para instrumentos fuera de los casos hardcodeados.

### ¿Puede soportar validación real de órdenes?

**Parcialmente.** Los campos de spec están disponibles. Sin embargo:
1. El Fast Desk no existe — no hay consumer de estos specs.
2. No hay API de acceso en RAM para que un proceso externo consulte specs sin leer SQLite o JSON.
3. Sessions service está inoperativo — no se puede validar si el mercado está abierto.

### ¿Es el estado broker/cuenta suficientemente cargado?

**Sí para la sesión actual.** Balance, equity, leverage, margin se cargan en startup. El `account_mode_guard` previene uso accidental en live con config de demo.

**Sin embargo**, si el broker o cuenta cambia mientras el runtime está corriendo:
- `symbol_spec_cache` contiene specs del broker anterior sin invalidación (F-04).
- El `server_time_offset_seconds` no se resetea automáticamente — solo se recalcula en `connect()`.
- No hay mecanismo de detección de cambio de broker/cuenta que dispare una purga de caches.

---

## 5. Plan de Corrección Mínima

### Prioridad A — Correcciones críticas de integridad de datos

**A1. Añadir partición por broker/cuenta a `symbol_spec_cache`**

Archivo: `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`

Cambiar la PK de `symbol` a `(broker_server, account_login, symbol)`. Añadir las columnas `broker_server TEXT NOT NULL` y `account_login INTEGER NOT NULL`. Actualizar `upsert_symbol_spec_cache` para incluir estas columnas. Cambiar `upsert_market_state_cache` para incluir también `broker_server` + `account_login`, o añadir un step de purga al detectar cambio de broker.

**A2. Eliminar `bid`/`ask` de `fetch_symbol_specification`**

Archivo: `src/heuristic_mt5_bridge/infra/mt5/connector.py`

Eliminar los campos `bid` y `ask` del dict retornado por `fetch_symbol_specification()`. Eliminar las columnas `bid REAL` y `ask REAL` de la tabla `symbol_spec_cache` (o moverlas a un campo JSON separado si son necesarias para tracking).

---

### Prioridad B — Correcciones del schema live JSON

**B1. Reducir `build_live_state()` al schema mínimo de control-plane**

Archivo: `src/heuristic_mt5_bridge/core/runtime/service.py` — método `build_live_state()`

El JSON live resultante debe contener **solo**:
```
status, health, broker_identity, server_time_offset_seconds,
universes { catalog_count, bootstrap, subscribed, rejected },
watched_timeframes, chart_workers { count, symbols, workers { symbol, ready_timeframes, last_updated_at } },
sessions_health, indicator_health, runtime_metrics { poll_ms_avg, poll_ms_max },
symbol_catalog { status, count, updated_at },
symbol_specifications_count, updated_at
```

Eliminar: `feed_status` (array con precios), `account_summary` completo, `exposure_state`, `broker_session_registry` completo.

**B2. Aumentar `CORE_LIVE_PUBLISH_SECONDS` por defecto a 5–10 segundos**

El heartbeat de estado de salud no necesita resolución de 1 segundo.

---

### Prioridad C — Correcciones de acumulación y staleness

**C1. Eliminar la copia local en `IndicatorBridge.import_snapshots()`**

Archivo: `src/heuristic_mt5_bridge/infra/indicators/bridge.py`

Eliminar la línea:
```python
persist_json(self.local_snapshots_dir / f"{snapshot['request_id']}.json", snapshot)
```
El snapshot ya está aplicado al `MarketStateService` en RAM. La copia local no tiene ningún consumidor documentado.

**C2. Detectar cambio de broker/cuenta y purgar caches stale**

Archivo: `src/heuristic_mt5_bridge/core/runtime/service.py`

Persistir `broker_identity` en startup. En cada `_refresh_symbol_catalog()`, comparar broker_identity activa con la guardada. Si difiere, purgar `symbol_spec_cache` y `market_state_cache` de SQLite antes de recargar.

---

### Prioridad D — Arquitectura de consumo (sin estos no hay trading real)

**D1. Diseñar e implementar Control Plane básico**

Archivo: `apps/control_plane.py`

Implementar un FastAPI/aiohttp server que exponga como mínimo:
- `GET /status` → health snapshot desde RAM
- `GET /chart/{symbol}/{timeframe}` → chart context desde `MarketStateService`
- `POST /subscribe/{symbol}` → llama a `runtime.subscribe_symbol()`
- `POST /unsubscribe/{symbol}` → llama a `runtime.unsubscribe_symbol()`

El Control Plane debe compartir instancia de `CoreRuntimeService` o conectarse via IPC — no leer del JSON en disco.

**D2. Definir IPC boundary entre `core_runtime` y `fast_desk_runtime`**

Antes de implementar Fast Desk, definir cómo recibe actualizaciones de chart sin leer JSON ni SQLite en el hot path. Opciones válidas: in-process si corren en el mismo proceso, asyncio Queue, o ZeroMQ PUB/SUB si corren en procesos separados.

---

## 6. Criterios de Aceptación (pass/fail)

| Criterio | Condición de PASS | Estado actual |
|---|---|---|
| **Chart RAM ownership** | `MarketStateService` es la única fuente de OHLC; ningún archivo JSON contiene candles o precios por timeframe | ❌ FAIL — `feed_status` en JSON live |
| **Polling solo subscribed** | Solo los símbolos en `SubscriptionManager.subscribed_universe()` reciben llamadas MT5 dinámicas | ✅ PASS |
| **Schema control-plane minimal** | `core_runtime.json` no contiene `bid`, `ask`, `last_price`, `tick_age_seconds`, `bar_age_seconds` ni `account_summary` con balance | ❌ FAIL |
| **Symbol spec completo en startup** | `tick_size`, `tick_value`, `contract_size`, `volume_min/max/step`, `stops_level`, `filling_mode`, `order_mode` cargados para todos los símbolos suscritos | ✅ PASS |
| **Partición broker en specs** | `symbol_spec_cache.PRIMARY KEY` incluye `broker_server` + `account_login` | ❌ FAIL |
| **Invalidación en cambio de broker** | Al detectar cambio de `broker_identity`, se purgan `symbol_spec_cache` y `market_state_cache` | ❌ FAIL — no existe mecanismo |
| **Sessions service operativo** | `broker_session_registry.service.running = true`, `session_groups` no vacío para símbolos suscritos | ❌ FAIL — EA no conectado |
| **Control Plane funcional** | `GET /status` devuelve estado RAM sin leer JSON de disco | ❌ FAIL — no implementado |
| **Sin acumulación de archivos indicadores** | `storage/indicator_snapshots/` se mantiene vacío o con purga automática | ❌ FAIL — acumulación sin control |
| **Fast Desk consume RAM, no disco** | Fast Desk accede a chart state via API RAM/IPC, no lee `core_runtime.json` ni SQLite en hot path | ❌ FAIL — no implementado |

---

## Resumen ejecutivo

El núcleo de infraestructura (`SubscriptionManager`, `ConnectorIngress`, `ChartRegistry`, `ChartWorker`, `MarketStateService`) está correctamente diseñado e implementado conforme a la arquitectura pretendida. La corrección de subscription-driven polling es real. El problema es que las capas externas (Control Plane, Fast Desk, SMC Desk) son inexistentes, el JSON live sigue siendo un dump dinámico que viola el boundary RAM/disk, y la seguridad cross-broker de los specs en SQLite tiene una falla de diseño en el schema. El sistema puede hacer chart-in-RAM correctamente; no puede hacer trading todavía.
