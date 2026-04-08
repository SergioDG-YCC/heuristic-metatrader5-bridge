# Plan de Acción: Corrección Arquitectónica
**Repo:** `heuristic-metatrader5-bridge`
**Fecha:** 2026-03-23
**Origen:** Auditoría `docs/audit/2026-03-23_full_audit.md`

---

## Principios no negociables (refuerzo explícito)

Antes de cada fase, el constructor debe tener estos principios grabados:

1. **El disco no es un bus de transporte.** JSON y SQLite existen solo para persistencia operativa necesaria (catálogo, specs, posiciones, órdenes, ejecución). Nunca para transportar feed de precios, charts, o indicadores entre componentes en tiempo real.
2. **Todo dato dinámico vive en RAM.** Precios, candles, indicadores, estado de sesiones — RAM exclusivamente.
3. **`core_runtime.json` no debe existir.** El runtime no escribe ningún archivo JSON al disco durante operación normal. Si necesita diagnostics externos, eso es responsabilidad del Control Plane via HTTP, no de un archivo.
4. **Tolerancia cero a precios en disco.** Cualquier campo `bid`, `ask`, `last_price`, `tick_*`, `bar_*` en SQLite o JSON es un bug arquitectónico.
5. **Un solo owner del conector MT5.** `ConnectorIngress` es el único acceso al módulo `MetaTrader5`. Ningún otro componente llama a MT5 directamente.
6. **El frontend usa HTTP/SSE sobre Python.** La WebUI puede ser Node.js, Vite, o cualquier framework web moderno. Se expone en `0.0.0.0`. Obtiene todos sus datos del Control Plane Python via REST/SSE. Nunca lee archivos del disco del servidor.
7. **UTC0 es el tiempo interno.** Toda timestamp interna se normaliza a UTC0. El offset del broker (`server_time_offset_seconds`) se aplica al normalizar, nunca se propaga a los datos almacenados.
8. **Partición broker/cuenta en toda persistencia.** Cualquier tabla SQLite con datos de símbolo o mercado incluye `broker_server` + `account_login` en su clave primaria.
9. **Multi-broker es un caso base, no una extensión.** El sistema puede tener N instancias MT5 conectadas (distintos brokers, demos y reales) sin que los datos de una contaminen a otra.

---

## Fase 0 — Corrección de documentación primaria

**Propósito:** Blindar los documentos de referencia contra los patrones incorrectos antes de lanzar cualquier constructor. Esta fase no toca código.

**Motivación:** El constructor que produjo la repo actual leyó la misma documentación de arquitectura y de todas formas introdujo `core_runtime.json`, `CORE_LIVE_PUBLISH_SECONDS`, `bid`/`ask` en specs y ausencia de partición broker. Si se lanza el siguiente constructor desde documentos que no prohíben explícitamente estos patrones, los repetirá.

### Paso 0.1 — Actualizar `README.md`

Añadir sección "Reglas de implementación" con los 9 principios de arriba en lenguaje imperativo (`MUST`, `MUST NOT`). Eliminar lenguaje ambiguo sobre "persistent storage" que no especifica qué está prohibido.

### Paso 0.2 — Actualizar `docs/ARCHITECTURE.md`

- Añadir sección "Boundary RAM/Disk" con tabla explícita de qué dominio va a donde.
- Añadir sección "Lo que no existe" listando explícitamente: `core_runtime.json`, `indicator_snapshots/` en disco local, `bid`/`ask` en `symbol_spec_cache`, live publish loop.
- Actualizar la sección "Shared Core" para incluir el Control Plane HTTP como componente real.
- Documentar el modelo multi-broker: una instancia `CoreRuntimeService` por MT5 conectado.

### Paso 0.3 — Actualizar `docs/plans/2026-03-23_mt5_data_ownership_boundary.md`

- Añadir sección "Datos prohibidos en disco" con lista exhaustiva.
- Añadir sección "Partición por broker/cuenta" como requisito de todas las tablas SQLite.

### Paso 0.4 — Actualizar `docs/plans/2026-03-23_chart_ram_runtime_architecture.md`

- Reforzar que el checkpoint de market_state NO incluye `bid`/`ask`/`tick_age`/`bar_age`.
- Añadir sección "Sin archivo live" indicando que el runtime no produce ningún archivo JSON bajo `storage/live/`.

### Paso 0.5 — Actualizar `docs/plans/2026-03-23_core_runtime_subscription_refactor_plan.md`

- Eliminar referencias al campo `core_runtime.json` como artefacto de control-plane.
- Reemplazar con: el endpoint `/status` del Control Plane HTTP es el único punto de observabilidad externa.
- Añadir: `CORE_LIVE_PUBLISH_SECONDS` no debe existir en `.env` ni en `CoreRuntimeConfig`.

### Paso 0.6 — Reconstruir `configs/base.env.example`

Eliminar variables que no deben existir:
- `CORE_LIVE_PUBLISH_SECONDS` → eliminar
- `CORE_MARKET_STATE_CHECKPOINT_SECONDS` → eliminar (o renombrar a `CORE_RECOVERY_CHECKPOINT_SECONDS` si se mantiene, sin `bid`/`ask`)
- `STORAGE_ROOT` → mantener pero documentar que solo aplica a SQLite y archivos de ejecución

Añadir variables que faltan:
- `CONTROL_PLANE_HOST=0.0.0.0`
- `CONTROL_PLANE_PORT=8765`
- `MT5_BROKER_INSTANCE_ID=` (para multi-broker, identificador único de la instancia)

### Paso 0.7 — Actualizar `.gitignore`

La regla actual `storage/*` con `!storage/.gitkeep` es insuficiente. Corregir para:
- ignorar toda la carpeta `storage/` con sus subcarpetas
- ignorar `storage/live/` explícitamente
- ignorar `storage/indicator_snapshots/` explícitamente
- ignorar `storage/runtime.db`
- mantener `storage/.gitkeep`

---

## Fase 1 — Purga de archivos y código incorrecto

**Propósito:** Eliminar del codebase todo lo que implementa los patrones incorrectos. Esta fase solo borra, no implementa nada nuevo.

### Paso 1.1 — Purgar archivos de storage en disco

```
storage/live/core_runtime.json          → ELIMINAR
storage/indicator_snapshots/*.json      → ELIMINAR (todos los indreq_*.json)
storage/runtime.db                      → ELIMINAR (regenerable en siguiente arranque)
storage/live/                           → ELIMINAR directorio
```

Los `.gitkeep` pueden mantenerse en `storage/` si se quiere preservar la carpeta raíz en git, pero `storage/live/` y `storage/indicator_snapshots/` no deben existir en el repo.

### Paso 1.2 — Eliminar el live publish loop de `service.py`

En `src/heuristic_mt5_bridge/core/runtime/service.py`:
- Eliminar `_persist_live_state()` completo
- Eliminar la task `"live_state"` en `run_forever()`
- Eliminar `live_publish_seconds` de `CoreRuntimeConfig` y del `.env`
- Eliminar la llamada a `_persist_live_state()` en `bootstrap()`, `run_once()`, `shutdown()`
- Eliminar `build_live_state()` o convertirlo en método interno de observabilidad para el Control Plane (sin escritura a disco)

### Paso 1.3 — Eliminar `bid`/`ask` de `fetch_symbol_specification`

En `src/heuristic_mt5_bridge/infra/mt5/connector.py`:
- Eliminar `bid` y `ask` del dict retornado por `fetch_symbol_specification()`

### Paso 1.4 — Eliminar `bid`/`ask` de la tabla `symbol_spec_cache`

En `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`:
- Eliminar columnas `bid REAL` y `ask REAL` de `symbol_spec_cache`
- Actualizar `upsert_symbol_spec_cache` acorde

### Paso 1.5 — Eliminar copia local de indicadores en `IndicatorBridge`

En `src/heuristic_mt5_bridge/infra/indicators/bridge.py`:
- Eliminar la línea `persist_json(self.local_snapshots_dir / ...)` en `import_snapshots()`
- Eliminar `self.local_snapshots_dir` del `__init__`
- Eliminar referencias a `storage/indicator_snapshots/` en toda la clase

### Paso 1.6 — Eliminar `CORE_LIVE_PUBLISH_SECONDS` y `CORE_MARKET_STATE_CHECKPOINT_SECONDS` del `.env`

Estos parámetros deben desaparecer del `CoreRuntimeConfig` y de `configs/base.env.example`.

### Paso 1.7 — Eliminar `pip_size_for_symbol()` hardcodeada de `market_state.py`

En `src/heuristic_mt5_bridge/core/runtime/market_state.py`:
- Eliminar `pip_size_for_symbol()` y `instrument_scale_for_symbol()`
- Eliminar su uso en `build_chart_context()`
- El valor correcto llegará desde symbol_spec vía el registry de specs (Fase 3)

---

## Fase 2 — Corrección de integridad de datos en SQLite

**Propósito:** Corregir el schema SQLite para que sea seguro en contexto multi-broker y no contenga datos dinámicos.

### Paso 2.1 — Repartir `symbol_spec_cache` por broker/cuenta

Cambiar PRIMARY KEY de `symbol` a `(broker_server, account_login, symbol)`.

Añadir columnas al inicio:
```sql
broker_server TEXT NOT NULL,
account_login INTEGER NOT NULL,
```

Actualizar `upsert_symbol_spec_cache` para recibir y persistir estos campos.
Actualizar `_refresh_symbol_specs()` en `service.py` para pasar broker_identity.

### Paso 2.2 — Corregir `market_state_cache` — eliminar columnas de feed dinámico

Eliminar de la tabla:
- `last_price REAL`
- `bid REAL`
- `ask REAL`
- `feed_status TEXT`
- `tick_age_seconds REAL`
- `bar_age_seconds REAL`

Estas columnas no tienen valor en un checkpoint de recuperación. El único dato útil es `state_summary_json` (estructura de velas) y `chart_context_json`.

Añadir `broker_server TEXT NOT NULL` y `account_login INTEGER NOT NULL` a la PK: `(broker_server, account_login, symbol, timeframe)`.

Actualizar `upsert_market_state_cache` y `_persist_market_state_checkpoint()` acorde.

### Paso 2.3 — Añadir detección de cambio de broker/cuenta

En `CoreRuntimeService.bootstrap()`:
- Al obtener `broker_identity`, comparar con la última identity persistida para este `runtime_db_path`.
- Si difiere (broker_server o account_login cambiaron), ejecutar purga de `symbol_spec_cache` y `market_state_cache` para el broker anterior antes de cargar datos nuevos.
- Persistir la identity actual en una tabla simple `runtime_identity_cache`.

---

## Fase 3 — Symbol Spec Registry en RAM

**Propósito:** Exponer las especificaciones de símbolo desde RAM para que cualquier componente (Fast Desk, chart_context, risk engine) las consuma sin tocar SQLite en el hot path.

### Paso 3.1 — Crear `SymbolSpecRegistry`

Nuevo módulo: `src/heuristic_mt5_bridge/core/runtime/spec_registry.py`

Responsabilidad:
- Almacena `dict[str, SymbolSpec]` indexado por símbolo
- Thread-safe (Lock)
- `get(symbol)` → `SymbolSpec | None`
- `update(specs)` → reemplaza specs para broker/cuenta actuales
- `pip_size(symbol)` → lee `point` del spec real, no una heurística

Tipos:
```python
@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level_points: int
    freeze_level_points: int
    trade_mode: int
    filling_mode: int
    order_mode: int
    currency_base: str
    currency_profit: str
    currency_margin: str
    broker_server: str
    account_login: int
```

### Paso 3.2 — Integrar `SymbolSpecRegistry` en `CoreRuntimeService`

- `self.spec_registry = SymbolSpecRegistry()`
- Tras `_refresh_symbol_specs()`, llamar a `spec_registry.update(specs)`
- Eliminar `self.symbol_specifications` (lista raw de dicts) reemplazándolo por el registry tipado
- Pasar `spec_registry` al Control Plane para exposición via API

### Paso 3.3 — Conectar `build_chart_context()` al `spec_registry`

En `market_state.py`:
- Recibir `spec_registry` como parámetro opcional en `build_chart_context(symbol, timeframe, spec_registry=None)`
- Obtener `point` real del registry en lugar de `pip_size_for_symbol()`

---

## Fase 4 — Control Plane HTTP

**Propósito:** Implementar el Control Plane como servidor HTTP real que expone el estado RAM del `CoreRuntimeService`. Esta es la única fuente de datos para la WebUI y para procesos externos.

### Paso 4.1 — Diseño de contrato de API

Endpoints mínimos (FastAPI sobre `uvicorn`):

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/status` | Health + broker identity + universos + worker counts |
| `GET` | `/chart/{symbol}/{timeframe}` | Chart context + últimas N velas desde RAM |
| `GET` | `/specs/{symbol}` | Symbol spec desde `SpecRegistry` |
| `GET` | `/account` | Estado de cuenta desde RAM |
| `GET` | `/positions` | Posiciones abiertas desde RAM |
| `GET` | `/catalog` | Listado del catálogo de símbolos |
| `POST` | `/subscribe` | `{"symbol": "EURUSD"}` → `runtime.subscribe_symbol()` |
| `POST` | `/unsubscribe` | `{"symbol": "EURUSD"}` → `runtime.unsubscribe_symbol()` |
| `GET` | `/events` | SSE stream de actualizaciones de chart (para WebUI live) |

Configuración:
- `host = CONTROL_PLANE_HOST` (defecto `0.0.0.0`)
- `port = CONTROL_PLANE_PORT` (defecto `8765`)
- Sin autenticación en V1 (red local/VPN únicamente)

### Paso 4.2 — Implementar `apps/control_plane.py`

El proceso `control_plane` debe:
1. Importar y arrancar `CoreRuntimeService`
2. O conectarse a una instancia existente via referencia compartida (in-process)
3. Exponer la API FastAPI en `0.0.0.0:CONTROL_PLANE_PORT`
4. Nunca leer `core_runtime.json` (que ya no existirá)

### Paso 4.3 — SSE para actualizaciones de chart

Implementar endpoint `/events` (Server-Sent Events):
- El `ChartRegistry` notifica via `asyncio.Queue` a subscribers activos
- El endpoint SSE drena la queue y hace stream al cliente
- La WebUI puede suscribirse a eventos de símbolo específico

---

## Fase 5 — Frontend WebUI

**Propósito:** UI de control ligera para observabilidad y gestión del universo suscrito. Consumo exclusivo via Control Plane HTTP.

### Paso 5.1 — Decisión de framework

Opciones válidas:
- **Vite + React/Vue** (recomendado para SSE y estado reactivo)
- **Node.js + htmx** (más simple si la UI es principalmente dashboards)
- **Svelte** (mínimo overhead, excelente para streams)

Restricciones:
- Se expone en `0.0.0.0:WEBUI_PORT` (defecto `3000` o `5173`)
- Conecta SOLO al Control Plane Python via HTTP/SSE
- No accede a disco del servidor
- No tiene lógica de trading

Estructura recomendada:
```
webui/
  package.json
  vite.config.ts
  src/
    App.tsx
    components/
      StatusPanel.tsx
      ChartViewer.tsx
      SymbolManager.tsx
      AccountPanel.tsx
```

### Paso 5.2 — Vistas mínimas V1

1. **Status panel**: health, broker identity, universo suscrito, worker counts
2. **Symbol manager**: catálogo completo, subscribe/unsubscribe
3. **Chart viewer**: últimas velas + indicadores para símbolo/timeframe
4. **Account panel**: balance, equity, margin, posiciones abiertas

---

## Fase 6 — Migración desde `llm-metatrader5-bridge`

**Propósito:** Extraer e integrar el código de Fast Desk y SMC Desk desde la repo anterior, adaptado a la arquitectura corregida.

### Paso 6.1 — Auditoría del código a migrar

Antes de migrar, auditar en `llm-metatrader5-bridge`:
- Qué módulos de Fast Desk son algoritmos puros (sin dependencia LLM, sin disco)
- Qué módulos tienen dependencias de LLM que deben ser eliminadas o reemplazadas
- Qué módulos leen `market_state` desde archivo (deben adaptarse a RAM)

### Paso 6.2 — Migrar Fast Desk

Adaptar los workers de Fast Desk para consumir chart state desde `ChartRegistry` via RAM/IPC, no desde SQLite ni JSON.

Implementar `apps/fast_desk_runtime.py` real.

### Paso 6.3 — Migrar SMC Desk

Adaptar SMC Desk con las mismas restricciones de acceso a datos. El LLM es opcional y posterior a los filtros heurísticos.

Implementar `apps/smc_desk_runtime.py` real.

---

## Fase 7 — Multi-broker y escalabilidad a ticks

**Propósito:** Verificar y completar el soporte para N instancias MT5 en paralelo y frecuencia de polling hasta nivel tick.

### Paso 7.1 — Modelo multi-instancia

Cada `CoreRuntimeService` debe ser instanciable con un `instance_id` único:
- Propios workers de chart
- Propia conexión al conector MT5
- Propia tabla SQLite (o partición explícita por `broker_server` + `account_login`)
- Propio endpoint en Control Plane (o instancia propia de Control Plane)

### Paso 7.2 — Polling a escala tick

Reemplazar el polling por intervalo (`poll_seconds`) por suscripción a ticks de MT5:
- `mt5.symbol_info_tick()` en loop vs `copy_rates_from_pos`
- Implementar `tick_ingress` como alternativa a `ingress.py`
- El `ChartWorker` debe aceptar actualizaciones de tick y reconstruir la vela activa en RAM

---

## Orden de ejecución recomendado

```
Fase 0 → Fase 1 → Fase 2 → Fase 3 → Fase 4 → Fase 5 → Fase 6 → Fase 7
  docs      purga   schema   specs    http     webui   migra   ticks
```

Las fases 0, 1, 2 son **prerrequisito** para cualquier trabajo de constructor.
Las fases 3, 4 son el núcleo funcional.
Las fases 5, 6, 7 son expansión.

Cada fase debe tener tests verificables antes de avanzar a la siguiente.

---

## Criterios de aceptación por fase

| Fase | Criterio de PASS |
|---|---|
| 0 | Documentos actualizados, `.env.example` sin variables prohibidas, `.gitignore` correcto |
| 1 | `storage/live/` no existe, `persist_json` no llamado desde `service.py`, no hay `bid`/`ask` en specs |
| 2 | PK de `symbol_spec_cache` incluye `broker_server` + `account_login`, `market_state_cache` sin columnas de feed dinámico |
| 3 | `SymbolSpecRegistry.pip_size("EURUSD")` retorna `0.00001` desde spec real, no desde heurística |
| 4 | `GET /status` responde con datos RAM, `POST /subscribe` reactiva worker, sin lectura de disco |
| 5 | WebUI muestra chart live vía SSE, no realiza requests a disco, funciona en `0.0.0.0` |
| 6 | Fast Desk ejecuta signal cycle sin leer JSON ni SQLite en el hot path |
| 7 | Sistema corre con 2 brokers en paralelo sin cruce de datos entre instancias |
