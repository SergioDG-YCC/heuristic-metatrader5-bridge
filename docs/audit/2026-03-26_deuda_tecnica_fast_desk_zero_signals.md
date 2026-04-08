# Deuda Técnica — Fast Desk: 0 señales ejecutadas (0 rows en fast_desk_signals)

**Fecha:** 2026-03-26  
**Estado:** ABIERTO — causa raíz parcialmente identificada  
**Prioridad:** ALTA — el Fast Desk está activo (5 workers) pero nunca ejecuta ni registra nada

---

## 1. Síntoma

```
fast_desk_signals:   0 rows
fast_desk_trade_log: 0 rows
```

Ambos desks figuran como `enabled: true` y con workers activos en `/api/v1/desk-status`. El SMC Desk sí genera `smc_events_log` (>6000 filas) y `smc_thesis_cache` (4 tesis). El Fast Desk no escribe nada en ninguna tabla.

---

## 2. Diagnóstico realizado

### 2.1 Pipeline check con script `scripts/fast_desk_diag.py`

Se ejecutó un diagnóstico offline simulando todos los pasos del pipeline `scan_and_execute` con datos en vivo del endpoint `/chart/{symbol}/{tf}`.

**Resultado GBPUSD (el caso más claro):**

```
Context: allowed=True  h1_bias=neutral  session=tokyo
Setups found: 2
  liquidity_sweep_reclaim buy  risk_pips=69.0  trigger=micro_choch/True  entry_policy=True
  *** WOULD EXECUTE: lot=100.0 MARKET ***
```

Todos los filtros del pipeline pasan:
- ✅ `context.allowed = True` (no stale, no spread, sesión = global)
- ✅ Setups detectados (liquidity_sweep_reclaim + micro_choch)
- ✅ `h1_bias = neutral` → h1_alignment no filtra
- ✅ `risk_gate_ref` → `allowed = True`, `risk_per_trade_pct = 1.449`
- ✅ `check_account_safe` → pass (balance=$1.18M, equity=$1.18M, drawdown=0%)
- ✅ `entry_policy.can_open` → True (0 posiciones abiertas)
- ✅ Lot size = 100 lots (capped desde 248 por FastRiskEngine hardcap)

### 2.2 Por qué no hay escritura en DB

El flujo de `scan_and_execute` (en `fast_desk/trader/service.py`) escribe en `fast_desk_signals` **solo después** de llamar a `self.execution.send_entry(connector, ...)`. Si `send_entry` lanza excepción, el worker la captura en silencio:

```python
# symbol_worker.py → _run_scan()
except Exception as exc:
    print(f"[fast-desk] scan error ({symbol}): {exc}")
```

No hay escritura en DB si hay excepción. Esto explica `0 rows`.

### 2.3 Causa raíz probable (no confirmada — sin acceso a logs del backend)

La causa más probable es una excepción en `send_execution_instruction` en `infra/mt5/connector.py`:

```python
result = mt5.order_send(request)
if result is None:
    raise MT5ConnectorError(f"order_send returned None: {mt5.last_error()}")
```

Candidatos de excepción (en orden de probabilidad):

| Ranking | Causa | Evidencia |
|---------|-------|-----------|
| 1 | `order_send → None` por alguna restricción del broker FBS-Demo | No hay acceso a logs del proceso |
| 2 | Lot size de 100 lots rechazado por regla de negocio (margin/volume check interno) | Volume_max=500 pero lot=100 * contract=100000 = $13M notional |  
| 3 | Llenado de orden (`filling_mode`) incompatible para LIMIT orders | GBPUSD `filling_mode=3` (FOK+IOC) |
| 4 | `account_info()` devuelve `None` antes de ejecutar | MT5 thread contention |
| 5 | Race condition con `_mt5_lock` en el path `_make_mt5_execute_sync` | Threadpool nested call |

---

## 3. Bloqueo actual

**No se puede confirmar la causa raíz** sin leer los logs del proceso de backend en tiempo real. El terminal donde corre `core_runtime.py` (`apps/core_runtime.py`) debería mostrar líneas como:

```
[fast-desk] scan error (GBPUSD): order_send returned None: (10004, ...)
```

Los terminales que ejecutan el backend no están accesibles en la sesión actual de Copilot Chat. El proceso está corriendo en background.

---

## 4. Deuda técnica identificada

### DT-001: Señales fallidas no se persisten

**Ubicación:** `fast_desk/trader/service.py` → `scan_and_execute()`

```python
result = self.execution.send_entry(connector, ...)
# Si send_entry() lanza → sin escritura en DB
outcome = "accepted" if bool(result.get("ok", False)) else "rejected"
runtime_db.upsert_fast_signal(db_path, ...)  ← nunca llega si hay excepción
```

**Fix:** Persistir el intento de señal ANTES de la ejecución, con `outcome = "pending"`, y actualizarla a `accepted` / `rejected` / `error` después. O envolver en try/except con escritura en caso de error.

### DT-002: scan_error no persiste en DB

**Ubicación:** `fast_desk/workers/symbol_worker.py` → `_run_scan()`

```python
except Exception as exc:
    print(f"[fast-desk] scan error ({symbol}): {exc}")
    # → sin persistencia, sin alerta, invisible en WebUI
```

**Fix:** Persistir errores de ejecución en `fast_desk_trade_log` o tabla nueva `fast_desk_errors` para visibilidad en WebUI.

### DT-003: Lot size irreal para cuenta grande en demo

**Ubicación:** `fast_desk/risk/engine.py` → `calculate_lot_size()`

Con balance=$1.18M y `risk_per_trade_percent=1.449%`, para SL=69 pips:
```
lot = 1182668 * 0.01449 / (69 * 1.0) = 248 lots → capped to 100
```

100 lots de GBPUSD = $13.3M notional en cuenta demo de $1.18M. Probablemente rechazado por FBS-Demo.

**Fix:** Añadir `volume_max` del spec del símbolo como techo adicional. Añadir cap configurable en `FastRiskConfig` (`max_lot_size: float = 10.0`).

### DT-004: No existe endpoint de diagnóstico para Fast Desk

No hay endpoint que exponga el resultado del último scan por símbolo (contexto, setups, triggers, razón de bloqueo). Solo se puede ver si el worker está "activo" con N workers.

**Fix:** Crear `GET /api/v1/fast/diag/{symbol}` que ejecute el pipeline en dry-run y devuelva cada etapa.

### DT-005: SMC candidates=0 por min_rr=5.0 muy estricto

De los 4 tesis en `smc_thesis_cache`:
- USDJPY: `candidate_count_out=0` → validator_decision=`reject` (D1/H4 conflict)
- GBPUSD: `candidate_count_out=0` → `rr_ok=false`
- EURUSD: `candidate_count_out=0` → `rr_ok=false`
- USDCHF: `candidate_count_out=6` pero `status=watching` (necesita H1 confirmation)

`validation_summary.rr_ok=false` para 3 de 4 tesis. El min_rr configurado es 5.0 pero muchos candidatos tienen RR entre 7 y 15 (deberían pasar). La causa es que el validador heurístico rechaza candidatos ANTES de llegar al LLM validator.

**Fix:** Revisar `validators/heuristic.py` → función `validate_candidates_batch` para entender por qué `rr_ok=false` cuando los candidatos individuales sí tienen RR > 5.

---

## 5. Acciones inmediatas recomendadas

### Prioridad 1: Ver logs del backend
1. Abrir una terminal y ejecutar `Get-Content -Wait <log_file>` o reiniciar el backend con captura de stdout/stderr para un archivo
2. Buscar líneas `[fast-desk] scan error`

### Prioridad 2: Fix DT-003 (lot size)
Reducir el lot size para demo. Añadir `max_lot_size = 10.0` como cap en `FastRiskConfig` y verificar con:
```python
volume = min(calculated_volume, spec.get("volume_max", 500.0), self.config.max_lot_size or 500.0)
```

### Prioridad 3: Fix DT-001 (señales fallidas)
Persistir intentos de señal en DB para que sean visibles en WebUI sin importar si la ejecución falla.

### Prioridad 4: Endpoint de diagnóstico (DT-004)
Añadir `GET /api/v1/fast/diag/{symbol}` para visibilidad desde WebUI.

---

## 6. Evidencia del sistema en vivo

```
# 2026-03-26T03:25 UTC
Desk status:  Fast ACTIVE 5 workers, SMC ACTIVE scanner active
Kill switch:  armed (not tripped)
Risk profile: global=4, fast=4, smc=4
Open positions: 0
Pending orders: 0

GBPUSD en el momento del diagnóstico:
  h1_bias=neutral  volatility=low(ratio=2.04)  stale=False
  Setups: [liquidity_sweep_reclaim buy (+micro_choch), order_block_retest buy (+micro_choch)]
  *** Pipeline dice: WOULD EXECUTE — sin señal en DB ***
```

---

*Generado por GitHub Copilot — sesión 2026-03-26*
