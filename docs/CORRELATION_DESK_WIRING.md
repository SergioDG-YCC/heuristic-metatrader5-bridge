# Correlation Engine — Estado de Ingesta en Fast Desk y SMC Desk

> Fecha de auditoría: 2026-04-05  
> Autor: GitHub Copilot (auditoría automática)  
> Base: `CORRELATION_ENABLED=true`, `CORRELATION_TIMEFRAMES=M5,M30,H1`

---

## 1. Resumen Ejecutivo

El motor de correlación **está en producción y calculando matrices** correctamente.
Las capas de política (`FastCorrelationPolicy`) y presentación (`SmcCorrelationFormatter`)
están **completamente implementadas, testeadas y esperando** ser conectadas.

**El único problema es el cableado en runtime**: ni `create_fast_desk_service()` ni
`create_smc_desk_service()` reciben la referencia a `CorrelationService`, por lo que
ambas mesas operan **con `correlation = None`** — el 100% de la lógica de correlación
está inerte en producción hoy.

---

## 2. Arquitectura Diseñada (flujos intencionados)

### 2.1 Fast Desk

```
CorrelationService (core/runtime)
        │  get_pair(sym_a, sym_b, "M5")
        │  get_exposure_relations(symbol, "M5")
        │  get_matrix("M5")
        ▼
FastCorrelationPolicy(correlation_service, high_threshold=0.80, timeframe="M5")
        │  .build_details(symbol)          → details["correlation"]
        │  .check_entry_conflict(symbol,   → warnings.append("correlation_conflict:…")
        │     side, open_positions)
        ▼
FastContextService(context_config, correlation_policy=<policy>)
        │  build_context(symbol, …)
        ▼
FastContext.details["correlation"]  +  FastContext.warnings[…]
        │
        ▼  (consumido por FastTriggerPolicy, FastEntryPolicy, etc.)
```

### 2.2 SMC Desk

```
CorrelationService (core/runtime)
        │  get_exposure_relations(symbol, "H1")
        │  get_matrix("H1")
        │  active_symbols()
        ▼
SmcCorrelationFormatter(correlation_service, timeframe="H1", top_n=5)
        │  .build_context_dict(symbol)     → analyst_input["correlation_context"]
        │  .build_context_snippet(symbol)  → texto para prompt LLM
        ▼
run_smc_heuristic_analyst(…, correlation_formatter=<formatter>)
        │
        ▼  analyst_input["correlation_context"] insertado en el contexto del analista
           (disponible para el validador LLM y para la lógica heurística)
```

---

## 3. Estado Actual de Cada Pieza

### 3.1 Motor central

| Componente | Archivo | Estado |
|---|---|---|
| `CorrelationService` | `core/correlation/service.py` | ✅ Implementado, testeado, corriendo |
| `CorrelationMatrixSnapshot` | `core/correlation/models.py` | ✅ Modelo completo con `compute_stale`, `all_pairs_coverage_ok` |
| `AlignmentResult` | `core/correlation/aligner.py` | ✅ Inner join por epoch, simple/log returns |
| `_pearson()` | `core/correlation/service.py` | ✅ Pure Python, clamped [-1, 1], `None` policy correcta |
| Instanciación en runtime | `core/runtime/service.py:214` | ✅ `self.correlation_service` creado si `CORRELATION_ENABLED=true` |
| Endpoint HTTP | `apps/control_plane.py` | ✅ `GET /api/v1/correlation/{tf}` y `/{tf}/{sym_a}/{sym_b}` |
| Console prints | `refresh_loop` | ✅ `[correlation] M5 pairs=45 coverage_ok=45 stale=45 elapsed=0.4s` |

### 3.2 Capa de política — Fast Desk

| Componente | Archivo | Estado |
|---|---|---|
| `FastCorrelationPolicy` | `fast_desk/correlation/policy.py` | ✅ Implementado, 17 tests |
| `.classify(coefficient)` | — | ✅ `"high"/"moderate"/"low"/"none"/"unavailable"` |
| `.check_entry_conflict(symbol, side, open_positions)` | — | ✅ Detecta *implicit hedge* y *inverse concentration* |
| `.build_details(symbol)` | — | ✅ Exporta `details["correlation"]` con todos los pares expostos |
| `FastContextService.__init__(…, correlation_policy=None)` | `fast_desk/context/service.py:94` | ✅ Acepta el parámetro |
| `FastContextService.build_context()` guarda en `details` | `fast_desk/context/service.py:336` | ✅ Invoca policy si no es `None` |
| **Instanciación de `FastCorrelationPolicy`** | `fast_desk/runtime.py` | ❌ **NUNCA se instancia** |
| **Paso a `FastContextService`** | `fast_desk/trader/service.py:83` | ❌ **`correlation_policy=None` siempre** |

### 3.3 Capa de presentación — SMC Desk

| Componente | Archivo | Estado |
|---|---|---|
| `SmcCorrelationFormatter` | `smc_desk/correlation/formatter.py` | ✅ Implementado, 17 tests |
| `.top_correlations(symbol)` | — | ✅ Top-N pares con `coverage_ok=True`, ordenados por `|r|` |
| `.build_context_snippet(symbol)` | — | ✅ Texto human-readable para prompt LLM |
| `.build_context_dict(symbol)` | — | ✅ Dict estructurado con snippet + top_pairs + metadata |
| `build_heuristic_output(…, correlation_formatter=None)` | `smc_desk/analyst/heuristic_analyst.py:466` | ✅ Acepta el parámetro |
| `run_smc_heuristic_analyst(…, correlation_formatter=None)` | `smc_desk/analyst/heuristic_analyst.py:735` | ✅ Acepta el parámetro |
| **Instanciación de `SmcCorrelationFormatter`** | `smc_desk/runtime.py` | ❌ **NUNCA se instancia** |
| **Paso a `run_smc_heuristic_analyst()`** | `smc_desk/runtime.py:177` | ❌ **`correlation_formatter` omitido en la llamada** |

---

## 4. Detalle del Gap de Cableado

### 4.1 Punto de ruptura en Fast Desk

**`fast_desk/trader/service.py` línea ~83:**
```python
# ACTUAL (roto):
self.context_service = FastContextService(context_config)
# ← correlation_policy NO se pasa → siempre None

# NECESARIO:
self.context_service = FastContextService(context_config, correlation_policy=policy)
```

**`fast_desk/runtime.py` (factory `create_fast_desk_service`):**
```python
# ACTUAL:
def create_fast_desk_service(db_path: Path) -> FastDeskService:
    config = FastDeskConfig.from_env()
    return FastDeskService(db_path=db_path, config=config)
    # ← FastDeskService no recibe correlation_service

# NECESARIO: recibir correlation_service como parámetro
def create_fast_desk_service(
    db_path: Path,
    correlation_service: CorrelationService | None = None,
) -> FastDeskService:
    ...
```

**`core/runtime/service.py` (attach de fast desk, línea ~1127):**
```python
# ACTUAL:
fast_desk = create_fast_desk_service(config.runtime_db_path)

# NECESARIO:
fast_desk = create_fast_desk_service(
    config.runtime_db_path,
    correlation_service=self.correlation_service,
)
```

### 4.2 Punto de ruptura en SMC Desk

**`smc_desk/runtime.py` `_run_analyst_safe()` línea ~167:**
```python
# ACTUAL (roto):
result = await run_smc_heuristic_analyst(
    symbol=symbol,
    …,
    config=self._analyst_config,
    # ← correlation_formatter AUSENTE
)

# NECESARIO:
result = await run_smc_heuristic_analyst(
    symbol=symbol,
    …,
    config=self._analyst_config,
    correlation_formatter=self._correlation_formatter,
)
```

**`smc_desk/runtime.py` `SmcDeskService.__init__` y factory:**
```python
# ACTUAL:
def create_smc_desk_service(db_path: Path) -> SmcDeskService:
    …
    return SmcDeskService(…)
    # ← sin correlation_service

# NECESARIO: recibir y propagar
def create_smc_desk_service(
    db_path: Path,
    correlation_service: CorrelationService | None = None,
) -> SmcDeskService:
    …
    formatter = SmcCorrelationFormatter(correlation_service, timeframe="H1") \
                if correlation_service else None
    return SmcDeskService(…, correlation_formatter=formatter)
```

---

## 5. Qué aportaría cada mesa una vez cableado

### 5.1 Fast Desk — Protección de cartera por correlación

La `FastCorrelationPolicy` actúa en **tiempo real antes de cada entrada**:

| Escenario | Detección | Acción |
|---|---|---|
| EURUSD `buy` + posición GBPUSD `sell` + r=+0.88 | **Implicit hedge** | `warnings["correlation_conflict:implicit_hedge:EURUSD-GBPUSD(r=+0.88,new=buy,open=sell)"]` |
| EURUSD `buy` + posición USDJPY `buy` + r=-0.82 | **Inverse concentration** | `warnings["correlation_conflict:inverse_concentration:EURUSD-USDJPY(r=-0.82,side=buy)"]` |
| Correlación baja (r=0.35) | No conflicto | Entrada permitida sin warning |

El `FastContext.details["correlation"]` también expone los primeros N pares para que el
`FastTriggerPolicy` pueda ajustar umbrales de confianza basados en exposición cruzada.

### 5.2 SMC Desk — Contexto de correlación para el analista LLM

El `SmcCorrelationFormatter` genera para cada análisis heurístico:

```
CORRELATION (H1, window=50 bars):
  GBPUSD: r=+0.91 [high]   coverage=48 bars
  USDJPY: r=-0.84 [high]   coverage=47 bars
  AUDUSD: r=+0.71 [moderate]  coverage=43 bars
[matrix computed 2026-04-05T10:30:00Z]
```

Este bloque entra en `analyst_input["correlation_context"]` y es parte del contexto
enviado al validador LLM. El LLM puede razonar sobre si una tesis en EURUSD tiene
coherencia de contexto con los instrumentos altamente correlacionados.

---

## 6. Plan de Implementación (3 cambios en 2 archivos + 1 archivo)

### Paso 1 — Propagar `correlation_service` desde core runtime a las factories

**`core/runtime/service.py`** (único punto, al crear los desks):
```python
fast_desk = create_fast_desk_service(
    config.runtime_db_path,
    correlation_service=self.correlation_service,
)
smc_desk = create_smc_desk_service(
    config.runtime_db_path,
    correlation_service=self.correlation_service,
)
```

### Paso 2 — Fast Desk: factory + `FastTraderService`

**`fast_desk/runtime.py`** `create_fast_desk_service`:
- Aceptar `correlation_service: CorrelationService | None = None`
- Instanciar `FastCorrelationPolicy(correlation_service, timeframe="M5")` si no es `None`
- Pasarla a `FastDeskService`

**`fast_desk/trader/service.py`** `FastTraderService.__init__`:
- Aceptar `correlation_policy: FastCorrelationPolicy | None = None`
- Pasar a `FastContextService(context_config, correlation_policy=correlation_policy)`

### Paso 3 — SMC Desk: factory + `SmcDeskService._run_analyst_safe`

**`smc_desk/runtime.py`** `create_smc_desk_service`:
- Aceptar `correlation_service: CorrelationService | None = None`
- Instanciar `SmcCorrelationFormatter(correlation_service, timeframe="H1", top_n=5)` si no es `None`
- Guardar en `SmcDeskService._correlation_formatter`

**`smc_desk/runtime.py`** `_run_analyst_safe`:
- Añadir `correlation_formatter=self._correlation_formatter` a la llamada de `run_smc_heuristic_analyst`

---

## 7. Archivos a modificar (inventario completo)

| Archivo | Cambio necesario | Línea aprox |
|---|---|---|
| `core/runtime/service.py` | Pasar `correlation_service=` a las dos factories | ~1127, ~1123 |
| `fast_desk/runtime.py` | `create_fast_desk_service` acepta + instancia `FastCorrelationPolicy` | ~540 |
| `fast_desk/trader/service.py` | `FastTraderService.__init__` acepta + propaga `correlation_policy` | ~83 |
| `smc_desk/runtime.py` | `create_smc_desk_service` acepta + instancia `SmcCorrelationFormatter` | ~350 |
| `smc_desk/runtime.py` | `_run_analyst_safe` pasa `correlation_formatter=` | ~177 |

**Archivos que NO necesitan cambios** (ya están listos):
- `fast_desk/correlation/policy.py`
- `fast_desk/context/service.py`
- `smc_desk/correlation/formatter.py`
- `smc_desk/analyst/heuristic_analyst.py`
- `core/correlation/service.py`
- `core/runtime/market_state.py`

---

## 8. Tests existentes (cobertura actual)

| Suite | Tests | Cubre |
|---|---|---|
| `tests/core/test_correlation_numerical.py` | 14 | `_pearson`, edge cases, clamp |
| `tests/core/test_correlation_aligner.py` | 19 | `align_and_returns`, epoch join, returns |
| `tests/core/test_correlation_service.py` | 17 | `CorrelationService`, `get_pair`, `get_matrix`, snapshot atomicity |

No existen tests de integración que verifiquen el cableado runtime:
`FastCorrelationPolicy` → `FastContextService` → `FastTraderService` (gap a cubrir si se implementa).

---

*Fin del informe.*
