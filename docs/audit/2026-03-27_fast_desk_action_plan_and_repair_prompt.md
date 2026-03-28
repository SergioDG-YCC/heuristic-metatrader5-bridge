# Fast Desk — Plan de Acción Arquitectónico + Prompt de Reparación

**Fecha:** 2026-03-27  
**Basado en:** Contraste de dos auditorías independientes  
- `2026-03-27_fast_desk_analyst_heuristic_deep_audit.md` (auditor interno)  
- `codex_fast_desk_analyst_audit_2026-03-27.md` (Codex — incluye ejecución de tests)  
**Verificación de código muerto:** realizada en sesión — ver sección 1

---

## 1. Verificación del "Código Muerto" — `signals/scanner.py`

**Veredicto: NO es código muerto puro. Es código redundante activo.**

Flujo real verificado en código:

```
runtime.py:17    → from ...scanner import FastScannerConfig
runtime.py:215   → scanner_config = FastScannerConfig(min_confidence, atr_multiplier_sl, rr_ratio)
runtime.py:292   → worker.run(..., scanner_config=scanner_config, setup_config=setup_config, ...)

symbol_worker.py:74 → effective_setup_config = setup_config or FastSetupConfig(
                          rr_ratio=getattr(scanner_config, "rr_ratio", 2.0),    ← solo si setup_config es None
                          min_confidence=getattr(scanner_config, "min_confidence", 0.55),
                       )
```

**El problema real:** el runtime construye `setup_config` explícitamente y lo pasa al worker. Por lo tanto:
- El `scanner_config` se instancia y se pasa, pero **nunca se usa en la rama de ejecución normal** (el `setup_config or ...` resuelve a `setup_config`)
- El `scanner_config` solo actúa como fallback si `setup_config=None`, lo cual no ocurre en el path del runtime 
- Sus parámetros (`rr_ratio`, `min_confidence`, `atr_multiplier_sl`) son duplicados exactos de los que ya van en `FastSetupConfig`
- **`FastScannerConfig` no tiene el campo `min_rr`** — que es el más crítico — quedando invisible en el fallback

**Conclusión para el plan:** El `FastScannerConfig` debe ser eliminado como entidad de configuración. Sus campos deben vivir únicamente en `FastSetupConfig`. El archivo `signals/scanner.py` puede conservarse solo si contiene utilidades funcionales usadas (actualmente solo tiene dataclasses sin lógica real de análisis).

---

## 2. Contraste de Ambas Auditorías — Hallazgos Coincidentes y Complementarios

| ID | Hallazgo | Mi Audit | Codex | Verificado |
|----|----------|----------|-------|------------|
| A1 | `min_rr=2.0` como default viola RR3.0+ | P1 CRÍTICO | #1 CRÍTICO | ✅ Confirmado en 3 archivos |
| A2 | `FastConfigUpdateRequest` sin campo `min_rr` | — | #2 CRÍTICO | ✅ Confirmado en control_plane.py:252 |
| A3 | Señales fallidas no persisten en DB (ejecución silenciosa) | P2 CRÍTICO | DT-001/002 | ✅ Confirmado |
| A4 | Lot size irreal → broker rechaza silenciosamente | P3 CRÍTICO | DT-003 | ✅ Confirmado |
| A5 | `scanner_config` redundante vs `setup_config` | P4 ALTO | #10 MEDIO | ✅ Verificado — es fallback nunca alcanzado |
| A6 | FVG no integrado en Fast Desk | P5 ALTO | — | ✅ Sin imports en fast_desk |
| A7 | `micro_choch` trigger sin `confirmed=True` | P6 ALTO | — | ✅ Código verificado |
| A8 | Hot-reload parcial (solo context_config se propaga) | — | #4 ALTO | ✅ Confirmado en runtime.py:180-187 |
| A9 | `max_slippage_points` en API → parámetro fantasma | — | #9 MEDIO | ✅ Confirmado — no existe en FastDeskConfig |
| A10 | `FastTraderConfig` en worker con `max_slippage_points` inexistente | — | M | ✅ Confirmado en symbol_worker.py:80 |
| A11 | `max_positions_per_symbol` no enforced en EntryPolicy | — | #6 ALTO | ✅ Confirmado |
| A12 | SMC analyst: `quality="high"` desde RR=2.4 | — | #3 ALTO | ✅ Confirmado en heuristic_analyst.py:412 |
| A13 | Tests fast_desk: 3 fallos por firma antigua | — | #8 MEDIO | ✅ Codex ejecutó pytest |
| A14 | `breakout_retest` sin filtro de edad en BOS | P12 MEDIO | — | ✅ Verificado |
| A15 | `detect_market_structure` llamado 6× por ciclo | P10 MEDIO | — | ✅ Verificado |
| A16 | `hard_cut_r=1.25` > SL planificado (dilución RR) | P14 MEDIO | — | ✅ Verificado |
| A17 | Env vars FAST_DESK_* vs FAST_TRADER_* — drift config | — | #5 ALTO | ✅ Confirmado |
| A18 | `risk_pct` no clampeado al 2% documentado | — | #7 MEDIO | ✅ Confirmado |
| A19 | `min_rr` SMC Validator en 2.0 | — | #1 CRÍTICO | ✅ Confirmado en validators/heuristic.py:283 |

**Hallazgos exclusivos del informe Codex con evidencia sólida (tests ejecutados):**
- Los 3 tests fallidos por firma antigua de `calculate_lot_size` son evidencia directa de deuda técnica no capturada por mi audit
- La ejecución real de tests valida que el contrato del engine de riesgo cambió sin actualizar la suite

---

## 3. Plan de Acción — 4 Fases Priorizadas

### FASE 1 — CRÍTICA: RR Floor y Observabilidad de Ejecución
**Prerequisito para cualquier operación live. Plazo: antes del primer trade.**

#### 1.1 — Unificar `min_rr=3.0` en toda la cadena

**Archivos a modificar:**

| Archivo | Campo | Cambio |
|---------|-------|--------|
| `fast_desk/runtime.py` | `FastDeskConfig.min_rr` | default `2.0` → `3.0` |
| `fast_desk/runtime.py` | `from_env()` → `_getenv_float("FAST_TRADER_MIN_RR", 2.0)` | default `2.0` → `3.0` |
| `fast_desk/setup/engine.py` | `FastSetupConfig.min_rr` | default `2.0` → `3.0` |
| `smc_desk/analyst/heuristic_analyst.py` | `SmcAnalystConfig.min_rr` | default `2.0` → `3.0` |
| `smc_desk/analyst/heuristic_analyst.py` | env read `SMC_MIN_RR` | default `"2.0"` → `"3.0"` |
| `smc_desk/validators/heuristic.py` | validator `min_rr` default | `2.0` → `3.0` |
| `apps/control_plane.py` | GET `/api/v1/config/smc` response `min_rr` | default `"2.0"` → `"3.0"` |
| `smc_desk/analyst/heuristic_analyst.py:412` | `quality = "high" if rr >= 2.4` | condición → `rr >= 3.0` |

#### 1.2 — Exponer `min_rr` en Fast API

**Archivo:** `apps/control_plane.py`

Agregar a `FastConfigUpdateRequest`:
```python
min_rr: float | None = None
```

El handler `update_fast_config()` ya usa `setattr(svc.fast_desk_config, key, value)` genéricamente, por lo que el campo se propagará automáticamente al runtime en la siguiente recreación de workers.

Agregar también al bloque `_FAST_ENV_MAP` (rama desk inactivo):
```python
"min_rr": "FAST_TRADER_MIN_RR",
```

#### 1.3 — Persistir señales fallidas en base de datos

**Archivo:** `fast_desk/trader/service.py` — función `scan_and_execute()`

Antes de llamar a `self.execution.send_entry(...)`, insertar el intento con `outcome="pending"`. Envolver la ejecución en try/except. En el except, actualizar con `outcome="error"` y loguear el stack trace. **El registro del intento debe ocurrir siempre, independientemente del resultado de ejecución.**

**Archivo:** `fast_desk/workers/symbol_worker.py` — `_run_scan()`

En el except actual:
```python
except Exception as exc:
    print(f"[fast-desk] scan error ({symbol}): {exc}")
```
Agregar persistencia del error en `fast_desk_trade_log` o tabla `fast_desk_errors`.

#### 1.4 — Agregar `max_lot_size` configurable

**Archivo:** `fast_desk/risk/engine.py`

```python
@dataclass
class FastRiskConfig:
    risk_per_trade_percent: float = 1.0
    max_drawdown_percent: float = 5.0
    max_positions_per_symbol: int = 1
    max_positions_total: int = 4
    max_lot_size: float = 10.0   # ← NUEVO: cap configurable
```

Aplicar en `calculate_lot_size()`:
```python
lot_size = min(lot_size, self.config.max_lot_size, volume_max)
```

Exponer `max_lot_size` en `FastDeskConfig` → `FastConfigUpdateRequest` → API.

---

### FASE 2 — ALTA: Corrección de Triggers y Calidad de Señal
**Reduce señales falsas. Mejora RR real de los trades que sí se ejecutan.**

#### 2.1 — `micro_choch`: verificar `confirmed=True`

**Archivo:** `fast_desk/trigger/engine.py` — `_micro_choch()`

```python
choch = structure.get("last_choch")
if not choch:
    return FastTriggerDecision(False, "micro_choch", 0.0, "no_choch")
if not bool(choch.get("confirmed", False)):          # ← AGREGAR
    return FastTriggerDecision(False, "micro_choch", 0.0, "choch_unconfirmed")
```

#### 2.2 — `breakout_retest`: filtro de edad de BOS

**Archivo:** `fast_desk/setup/engine.py` — `_breakout_retest()`

Después de obtener `bos`:
```python
bos_idx = int(bos.get("index", 0) or 0)
candle_count = len(candles_m5[-180:])
bos_age = candle_count - 1 - bos_idx   # velas desde el BOS
if bos_age > 30:                        # BOS más viejo que 30 velas M5 = 2.5h
    return []
```

#### 2.3 — Elevar `min_impulse_candles` en Order Blocks

**Archivo:** `fast_desk/setup/engine.py` — `_order_block_retest()`

```python
zones = detect_order_blocks(candles_m5[-180:], structure_m5, min_impulse_candles=3, max_zones=6)
#                                                                                  ↑ era 2
```

#### 2.4 — Enforcer `max_positions_per_symbol` en EntryPolicy

**Archivo:** `fast_desk/policies/entry.py` — `can_open()`

Agregar antes del check de `max_positions_total`:
```python
symbol_count = sum(1 for p in open_positions
                   if str(p.get("symbol", "")).upper() == symbol_norm)
if symbol_count >= config.max_positions_per_symbol:
    return False, f"max_positions_per_symbol reached for {symbol_norm}: {symbol_count}"
```

#### 2.5 — Clamp de `risk_pct` al máximo documentado

**Archivo:** `fast_desk/risk/engine.py` — `calculate_lot_size()`

```python
# === CLAMP RISK AT POLICY MAXIMUM ===
MAX_RISK_PCT = 2.0
risk_pct = min(risk_pct, MAX_RISK_PCT)
```

---

### FASE 3 — MEDIA: Hot-reload y Consistencia de Configuración
**Elimina drift entre API, .env y workers vivos.**

#### 3.1 — Hot-reload completo en `FastDeskService`

**Archivo:** `fast_desk/runtime.py`

`update_context_config()` actualmente solo propaga `FastContextConfig`. Ampliar para propagar también:
- `risk_config.risk_per_trade_percent`, `max_positions_*`
- `trader_config.signal_cooldown`, `require_h1_alignment`, `enable_pending_orders`
- `setup_config.min_rr`, `rr_ratio`, `min_confidence`
- `custody_config.enable_*`

Estrategia: en vez de mutar configs que ya se inyectaron en los traders (que son objetos independientes por worker), añadir un mecanismo de `_config_ref` mutable compartido o reiniciar workers cuando el config no-contexto cambia.

#### 3.2 — Eliminar parámetro fantasma `max_slippage_points` de la API

**Archivo:** `apps/control_plane.py`

Remover `max_slippage_points: int | None = None` de `FastConfigUpdateRequest`.  
Documentar que el slippage se controla vía `max_slippage_pct` (porcentaje) en `FastContextConfig`, no como puntos fijos.

#### 3.3 — Eliminar `max_slippage_points` del fallback en `symbol_worker.py`

**Archivo:** `fast_desk/workers/symbol_worker.py`

```python
trader_cfg = trader_config or FastTraderConfig(
    signal_cooldown=float(config.signal_cooldown),
    # max_slippage_points=30,   ← ELIMINAR: no existe en FastTraderConfig
    enable_pending_orders=True,
    require_h1_alignment=True,
)
```

#### 3.4 — Unificar namespace de env vars

**Archivo:** `apps/control_plane.py` — `update_fast_config()` rama desk-inactivo

El dict `_FAST_ENV_MAP` mapea a `FAST_DESK_*` (legacy). El runtime lee `FAST_TRADER_*` primero. Unificar: el endpoint debe escribir las vars `FAST_TRADER_*` primarias, no las legacy.

#### 3.5 — Eliminar rol de `FastScannerConfig` como contenedor de config

**Archivo:** `fast_desk/runtime.py`

El bloque que construye `scanner_config` y lo pasa al worker debe eliminarse. El `setup_config` (que ya existe y se usa) contiene exactamente los mismos campos. El worker debe recibir solo `setup_config` como fuente de verdad. El parámetro `scanner_config: Any` en `symbol_worker.run()` puede quedar como optional deprecado con warning, o eliminarse.

---

### FASE 4 — ESTRATÉGICA: Calidad de Señal Avanzada
**Mejora la tasa de conversión y el RR real promedio de los trades.**

#### 4.1 — Integrar Fair Value Gaps en Fast Desk

**Archivo:** `fast_desk/setup/engine.py`

```python
from heuristic_mt5_bridge.smc_desk.detection.fair_value_gaps import detect_fair_value_gaps
```

Agregar método `_fvg_retest()` en `FastSetupEngine`:
- Detectar FVGs en M5 últimas 60 velas
- Para cada FVG sin llenar, si `latest_close` está a ≤ ATR×0.3 del nivel, generar setup
- Confidence: 0.80 (bullish FVG en tendencia bullish H1) / 0.77 (neutral)

Agregar multiplicador de confidence para `order_block_retest` cuando coincide con un FVG sin llenar en la misma zona (+0.06, max 1.0).

#### 4.2 — Reparar tests con 3 fallos (firma antigua)

**Archivo:** `tests/fast_desk/test_fast_desk.py`

Los tests fallan al llamar `calculate_lot_size(pip_value, ...)` en lugar de `calculate_lot_size(symbol_spec_dict, account_state)`. Actualizar calls de test al contrato actual:

```python
# ANTES (falla):
engine.calculate_lot_size(balance, risk_pct, sl_pips, pip_value_float)

# DESPUÉS (correcto):
engine.calculate_lot_size(balance, risk_pct, sl_pips, 
    {"tick_value": pip_value, "point": 0.0001, "digits": 5, "contract_size": 100000},
    account_state=None)
```

#### 4.3 — Centralizar estructuras SMC en `FastContext`

**Archivo:** `fast_desk/context/service.py`

Agregar a `FastContext`:
```python
structure_h1: dict = field(default_factory=dict)
structure_m5: dict = field(default_factory=dict)
```

Calcularlas una vez en `build_context()` y almacenarlas. Modificar `FastSetupEngine.detect_setups()` y `FastTriggerEngine.confirm()` para recibir las estructuras precalculadas en lugar de recalcularlas.

Esto elimina las 6 llamadas redundantes a `detect_market_structure()` por ciclo de scan.

#### 4.4 — Agregar tests RR3.0 de extremo a extremo

Crear `tests/fast_desk/test_rr_guarantee.py`:
- Test: ningún setup generado por `FastSetupEngine` debe tener `effective_rr < 3.0`
- Test: la combinación `setup + trigger` debe producir señales con `confidence ≥ 0.70`
- Test: `FastRiskConfig.max_lot_size` limita correctamente el lote calculado

---

## 4. Prompt de Reparación para Arquitecto de Software de Trading de Alta Velocidad

```
PROMPT DE REPARACIÓN ARQUITECTÓNICA
Sistema: heuristic-metatrader5-bridge (Fast Desk + SMC Analyst)
Fecha de base: 2026-03-27
Rol requerido: Arquitecto de software especializado en sistemas de trading de alta 
               velocidad / scalping heurístico. Sin LLM en el hot path. Latencia crítica.

════════════════════════════════════════════════════════════════════
CONTEXTO DEL SISTEMA
════════════════════════════════════════════════════════════════════

Stack Python + MT5 (MetaTrader 5 via conector propio).
Pipeline Fast Desk: Context → Setup → Trigger → Risk → Entry → Execution → Custody
Mandato operacional: RR ≥ 3.0 en toda señal ejecutada. Sin excepciones.
Pipeline SMC Desk: Scanner → Analyst → Validator → Thesis → Execution (separado)

Archivos clave:
- fast_desk/runtime.py               → FastDeskConfig, FastDeskService.run_forever()
- fast_desk/setup/engine.py          → FastSetupEngine, FastSetupConfig
- fast_desk/trigger/engine.py        → FastTriggerEngine
- fast_desk/risk/engine.py           → FastRiskEngine, FastRiskConfig
- fast_desk/policies/entry.py        → FastEntryPolicy
- fast_desk/custody/engine.py        → FastCustodyEngine
- fast_desk/trader/service.py        → FastTraderService.scan_and_execute()
- fast_desk/workers/symbol_worker.py → FastSymbolWorker.run()
- fast_desk/signals/scanner.py       → FastScannerConfig (redundante, ver REPARACIÓN 7)
- fast_desk/context/service.py       → FastContextService.build_context()
- apps/control_plane.py              → API REST (FastAPI) — control plane
- smc_desk/analyst/heuristic_analyst.py → SmcAnalystConfig, HeuristicAnalyst
- smc_desk/validators/heuristic.py   → validate_heuristic_thesis()
- smc_desk/detection/fair_value_gaps.py → disponible, NO integrado en Fast Desk

════════════════════════════════════════════════════════════════════
INSTRUCCIONES GENERALES
════════════════════════════════════════════════════════════════════

1. No crear nuevos archivos innecesarios.
2. No refactorizar lo que no está en el plan. Solo lo que se describe explícitamente.
3. Cada reparación es atómica: terminar y verificar antes de pasar a la siguiente.
4. Después de cada reparación que afecte un módulo con tests existentes, ejecutar:
   python -m pytest tests/fast_desk -q --tb=short
5. El orden de reparaciones importa: la Fase 1 desbloquea la operación live.
   No avanzar a Fase 2 sin haber completado y testeado la Fase 1.
6. NUNCA modificar archivos de configuración .env directamente en este prompt.
   Solo código Python y apps/.

════════════════════════════════════════════════════════════════════
REPARACIÓN 1 — RR FLOOR: Elevar min_rr a 3.0 en toda la cadena
════════════════════════════════════════════════════════════════════

OBJETIVO: Garantizar que ningún setup con RR efectivo < 3.0 sea aceptado,
          en ninguna ruta de código, en ningún escenario de configuración.

ARCHIVOS Y CAMBIOS:

fast_desk/runtime.py
  - FastDeskConfig.min_rr: float = 2.0  →  3.0
  - from_env(): _getenv_float("FAST_TRADER_MIN_RR", 2.0)  →  default 3.0

fast_desk/setup/engine.py
  - FastSetupConfig.min_rr: float = 2.0  →  3.0

smc_desk/analyst/heuristic_analyst.py
  - SmcAnalystConfig.min_rr: float = 2.0  →  3.0
  - lectura de env SMC_MIN_RR default "2.0"  →  "3.0"
  - calidad "high": condición `rr >= 2.4`  →  `rr >= 3.0`

smc_desk/validators/heuristic.py
  - cualquier default de min_rr en 2.0  →  3.0

apps/control_plane.py
  - GET /api/v1/config/smc respuesta: os.getenv("SMC_MIN_RR", "2.0")  →  "3.0"
  - GET respuesta second occurrence: same change

VALIDACIÓN:
  1. grep -r "min_rr.*2\.0" src/ apps/ → sin resultados
  2. grep -r "MIN_RR.*2\.0" src/ apps/ → sin resultados
  3. pytest tests/fast_desk -q → mismo resultado o mejor que antes
  4. pytest tests/smc_desk -q → mismo resultado o mejor

════════════════════════════════════════════════════════════════════
REPARACIÓN 2 — API: Exponer min_rr en FastConfigUpdateRequest
════════════════════════════════════════════════════════════════════

OBJETIVO: El operador debe poder gobernar el RR floor desde el control plane
          sin reiniciar el proceso.

ARCHIVO: apps/control_plane.py

CAMBIO 1: En FastConfigUpdateRequest (clase Pydantic, ~línea 252):
  Agregar campo:
    min_rr: float | None = None
  
  Constraint: validar que si se provee, sea >= 2.0 y <= 10.0.
  Agregar en el handler update_fast_config():
    if req.min_rr is not None and not (2.0 <= req.min_rr <= 10.0):
        raise HTTPException(422, "min_rr must be between 2.0 and 10.0")

CAMBIO 2: En el dict _FAST_ENV_MAP (rama desk inactivo, ~línea 698):
  Agregar:
    "min_rr": "FAST_TRADER_MIN_RR",

CAMBIO 3: En la respuesta del rama inactivo agregar:
    "min_rr": float(os.environ.get("FAST_TRADER_MIN_RR", "3.0")),

VALIDACIÓN:
  1. curl -X PUT /api/v1/config/fast -d '{"min_rr": 3.0}' → status=success
  2. curl -X PUT /api/v1/config/fast -d '{"min_rr": 1.5}' → 422 error

════════════════════════════════════════════════════════════════════
REPARACIÓN 3 — OBSERVABILIDAD: Persistir intentos de ejecución en DB
════════════════════════════════════════════════════════════════════

OBJETIVO: Toda señal que el sistema intenta ejecutar debe quedar en DB,
          independientemente del resultado de la ejecución.

ARCHIVO: fast_desk/trader/service.py → scan_and_execute()

CAMBIO: Antes del bloque try/except de send_entry():
  1. Generar signal_id y signal_payload como hoy.
  2. Insertar señal con outcome="pending" en DB ANTES de ejecutar.
  3. En el bloque try: ejecutar, obtener resultado, actualizar outcome.
  4. En el bloque except: capturar excepción, actualizar outcome="error",
     almacenar el error en evidence_json, re-raise solo si es error irrecuperable.
  5. Siempre cerrar con upsert_fast_signal() independientemente del outcome.

PSEUDO-ESTRUCTURA:
  signal_id = uuid.uuid4().hex
  signal_payload = { ..., "outcome": "pending" }
  runtime_db.upsert_fast_signal(...)   # ← PRE-EJECUCIÓN

  try:
      result = self.execution.send_entry(...)
      outcome = "accepted" if result.get("ok") else "rejected"
  except Exception as exec_err:
      result = {"ok": False, "error": str(exec_err)}
      outcome = "error"
      activity_log.emit(symbol, "execution_error", False, {"error": str(exec_err)})
  
  signal_payload["outcome"] = outcome
  signal_payload["evidence_json"]["exec_result"] = result
  runtime_db.upsert_fast_signal(...)   # ← POST-EJECUCIÓN (actualiza el pending)

ARCHIVO: fast_desk/workers/symbol_worker.py → _run_scan() except block:
  Agregar log persistente del error de scan (usar activity_log.emit() existente).

VALIDACIÓN:
  1. Simular send_entry() que lanza excepción.
  2. fast_desk_signals debe contener una fila con outcome="error".
  3. fast_desk_signals debe contener una fila con outcome="pending" que luego se actualiza.

════════════════════════════════════════════════════════════════════
REPARACIÓN 4 — RIESGO: max_lot_size configurable + clamp de risk_pct
════════════════════════════════════════════════════════════════════

OBJETIVO: Evitar órdenes rechazadas por broker due a lotes irreales o
          riesgo mayor al permitido por política.

ARCHIVO: fast_desk/risk/engine.py

CAMBIO 1: FastRiskConfig
  Agregar:
    max_lot_size: float = 10.0   # cap global, independiente del symbol spec

CAMBIO 2: calculate_lot_size()
  Después de calcular lot_size:
    lot_size = min(lot_size, self.config.max_lot_size)
  
  El cap de 50.0 en código se reemplaza por self.config.max_lot_size.
  
  Antes de calcular risk_amount:
    MAX_RISK_PCT_POLICY = 2.0
    effective_risk_pct = min(risk_pct, MAX_RISK_PCT_POLICY)

CAMBIO 3: Exponer max_lot_size en FastDeskConfig + runtime + API
  fast_desk/runtime.py → FastDeskConfig: max_lot_size: float = 10.0
  fast_desk/runtime.py → from_env(): leer FAST_TRADER_MAX_LOT_SIZE
  fast_desk/runtime.py → run_forever(): pasar max_lot_size a FastRiskConfig
  apps/control_plane.py → FastConfigUpdateRequest: max_lot_size: float | None = None
  apps/control_plane.py → _FAST_ENV_MAP: "max_lot_size": "FAST_TRADER_MAX_LOT_SIZE"

VALIDACIÓN:
  1. Con balance=$1M, risk=1%, sl_pips=50 → lot calculado debe ser ≤ 10.0 (default)
  2. Con max_lot_size=2.0: lot debe ser ≤ 2.0
  3. Con risk_pct=5.0: risk efectivo usado debe ser 2.0

════════════════════════════════════════════════════════════════════
REPARACIÓN 5 — ENTRY POLICY: Enforcer max_positions_per_symbol real
════════════════════════════════════════════════════════════════════

OBJETIVO: El límite de posiciones por símbolo debe bloquearse correctamente
          antes de abrir buy+sell en el mismo símbolo.

ARCHIVO: fast_desk/policies/entry.py → can_open()

CAMBIO: Agregar ANTES del check de max_positions_total:

  # Check max_positions_per_symbol (all sides combined)
  symbol_positions = [p for p in open_positions
                      if str(p.get("symbol", "")).upper() == symbol_norm]
  if len(symbol_positions) >= config.max_positions_per_symbol:
      return False, (
          f"max_positions_per_symbol reached for {symbol_norm}: "
          f"{len(symbol_positions)}/{config.max_positions_per_symbol}"
      )

NOTA: Este check va ANTES del check de same-symbol+same-side existente.
      El same-symbol+same-side check puede mantenerse como protección adicional
      pero ahora es redundante cuando max_positions_per_symbol=1.

VALIDACIÓN:
  1. Con 1 posición buy en EURUSD y max_positions_per_symbol=1:
     can_open("EURUSD", "sell", ...) → False, razón incluye "max_positions_per_symbol"
  2. Con 0 posiciones y max=1: can_open retorna True

════════════════════════════════════════════════════════════════════
REPARACIÓN 6 — TRIGGERS: micro_choch require confirmed=True + BOS age filter
════════════════════════════════════════════════════════════════════

OBJETIVO 6A: Eliminar confirmaciones falsas de CHoCH sin estructura posterior.
OBJETIVO 6B: Eliminar setups de breakout_retest sobre BOS viejos.

ARCHIVO A: fast_desk/trigger/engine.py → _micro_choch()

ANTES:
  choch = structure.get("last_choch") if isinstance(...) else None
  if not choch:
      return FastTriggerDecision(False, "micro_choch", 0.0, "no_choch")
  direction = str(choch.get("direction", ""))

DESPUÉS:
  choch = structure.get("last_choch") if isinstance(...) else None
  if not choch:
      return FastTriggerDecision(False, "micro_choch", 0.0, "no_choch")
  if not bool(choch.get("confirmed", False)):
      return FastTriggerDecision(False, "micro_choch", 0.0, "choch_unconfirmed")
  direction = str(choch.get("direction", ""))

ARCHIVO B: fast_desk/setup/engine.py → _breakout_retest()

Después de validar `near_retest`, agregar:
  bos_idx = int(bos.get("index", 0) or 0)
  total_bars = len(candles_m5[-180:])
  bos_age_bars = total_bars - 1 - bos_idx
  MAX_BOS_AGE_BARS = 30   # 30 × M5 = 2.5 horas
  if bos_age_bars > MAX_BOS_AGE_BARS:
      return []   # BOS demasiado viejo para ser un retest válido

VALIDACIÓN:
  1. pytest tests/fast_desk/test_fast_setup_trigger.py -v → mismo resultado o mejor
  2. Crear test: CHoCH sin confirmed=True → trigger retorna False

════════════════════════════════════════════════════════════════════
REPARACIÓN 7 — LIMPIEZA: Eliminar rol de FastScannerConfig como config container
════════════════════════════════════════════════════════════════════

OBJETIVO: Eliminar la dualidad FastScannerConfig vs FastSetupConfig como
          contenedores de configuración. Una sola fuente de verdad.

ARCHIVO: fast_desk/runtime.py → run_forever()

CAMBIO: Eliminar el bloque que construye `scanner_config`:
  # Eliminar:
  scanner_config = FastScannerConfig(
      min_confidence=cfg.min_signal_confidence,
      atr_multiplier_sl=cfg.atr_multiplier_sl,
      rr_ratio=cfg.rr_ratio,
  )
  
  # Mantener (ya existe):
  setup_config = FastSetupConfig(
      rr_ratio=cfg.rr_ratio,
      min_confidence=cfg.min_signal_confidence,
      min_rr=cfg.min_rr,
  )
  
  # En el call a worker.run(): eliminar scanner_config=scanner_config del kwargs

ARCHIVO: fast_desk/workers/symbol_worker.py → run()

CAMBIO: El parámetro `scanner_config: Any` puede quedar como deprecated con:
  import warnings
  if scanner_config is not None:
      warnings.warn("scanner_config is deprecated, use setup_config", DeprecationWarning)
  
  O eliminarlo directamente si no hay ningún caller externo.

ARCHIVO: fast_desk/signals/scanner.py

CAMBIO: El archivo retiene las funciones utilitarias `_ema()` y `_atr()` 
        si algo las importa. Si solo contiene dataclasses no usadas, agregar:
  # DEPRECATED: FastScannerConfig está reemplazado por FastSetupConfig (fast_desk/setup/engine.py)
  # Este archivo se mantiene por compatibilidad hacia atrás. No extender.

NO ELIMINAR el archivo si hay imports externos que no se hayan verificado.
VERIFICAR primero: grep -r "from.*scanner import\|import.*scanner" src/ tests/

VALIDACIÓN:
  1. python -c "from heuristic_mt5_bridge.fast_desk.runtime import FastDeskService" → sin errores
  2. pytest tests/fast_desk -q → sin regresiones

════════════════════════════════════════════════════════════════════
REPARACIÓN 8 — API: Remover max_slippage_points fantasma
════════════════════════════════════════════════════════════════════

OBJETIVO: Eliminar campo que no existe en FastDeskConfig y nunca se aplica.

ARCHIVO: apps/control_plane.py → FastConfigUpdateRequest

CAMBIO: Eliminar:
  max_slippage_points: int | None = None

ARCHIVO: fast_desk/workers/symbol_worker.py → fallback trader_config

CAMBIO: Eliminar línea:
  max_slippage_points=30,
del fallback de FastTraderConfig (ese parámetro no existe en FastTraderConfig).

VALIDACIÓN:
  1. PUT /api/v1/config/fast con {"max_slippage_points": 20} → 422 o campo ignorado (verificar comportamiento deseado con el equipo)
  2. pytest tests/ -q → sin regresiones

════════════════════════════════════════════════════════════════════
REPARACIÓN 9 — TESTS: Reparar 3 tests fallidos + agregar tests RR
════════════════════════════════════════════════════════════════════

OBJETIVO: Restaurar suite verde y agregar cobertura del contrato RR3.0.

ARCHIVO: tests/fast_desk/test_fast_desk.py

CAMBIO: Actualizar los 3 calls que pasan `pip_value: float` como 4° parámetro
        de `calculate_lot_size()` al contrato actual:
  engine.calculate_lot_size(
      balance=10000.0,
      risk_pct=1.0,
      sl_pips=20.0,
      symbol_spec={"tick_value": 10.0, "point": 0.0001, "digits": 5, "contract_size": 100000},
      account_state=None,
  )

NUEVO ARCHIVO (opcional): tests/fast_desk/test_rr_guarantee.py

Tests a incluir:
  1. test_no_setup_below_min_rr_3: ningún setup de FastSetupEngine con parámetros reales tiene eff_rr < 3.0
  2. test_max_lot_size_cap: con balance=$1M, lot calculado <= max_lot_size configurado
  3. test_min_rr_api_validation: PUT /api/v1/config/fast con min_rr=1.5 devuelve 422
  4. test_entry_policy_max_per_symbol: position abierta en símbolo bloquea nueva entrada

VALIDACIÓN FINAL:
  pytest tests/fast_desk -q → 0 failures
  pytest tests/ -q → igual o menos failures que antes

════════════════════════════════════════════════════════════════════
REPARACIÓN 10 (FASE 4 OPCIONAL) — FVG como herramienta de confluencia
════════════════════════════════════════════════════════════════════

OBJETIVO: Integrar Fair Value Gaps en Fast Desk como setup adicional
          para mejorar la tasa de conversión en scalping.

PRE-REQUISITO: Reparaciones 1-9 completas y testeadas.

ARCHIVO: fast_desk/setup/engine.py

CAMBIO 1: Import
  from heuristic_mt5_bridge.smc_desk.detection.fair_value_gaps import detect_fair_value_gaps

CAMBIO 2: En detect_setups(), agregar:
  setups.extend(
      self._fvg_retest(
          symbol=symbol,
          candles_m5=candles_m5,
          latest_close=latest_close,
          atr=atr,
          pip_size=pip_size,
          rr=cfg.rr_ratio,
          h1_bias=h1_bias,
      )
  )

CAMBIO 3: Implementar _fvg_retest():
  - Detectar FVGs en candles_m5[-60:] con detect_fair_value_gaps()
  - Filtrar solo FVGs sin llenar (mitigated=False)
  - Para cada FVG no mitigado cuyo rango contenga o esté a ≤ATR×0.3 de latest_close:
    - Bullish FVG: setup "buy" con entry=fvg_mid, sl=fvg_low-atr*0.2, confidence=0.80
    - Bearish FVG: setup "sell" con entry=fvg_mid, sl=fvg_high+atr*0.2, confidence=0.80
    - Verificar alineación con h1_bias (si h1_bias != "neutral" y no coincide: confidence=0.74)
  - setup_type = "fvg_retest"
  - requires_pending = True, pending_entry_type = "limit"

CAMBIO 4: En _order_block_retest(), si el OB coincide con un FVG sin llenar en zona:
  confidence += 0.06  # bonus de confluencia OB+FVG

VALIDACIÓN:
  1. pytest tests/fast_desk -q → sin regresiones
  2. En mercado con FVG visible en M5: pipeline detecta setup fvg_retest

════════════════════════════════════════════════════════════════════
CRITERIOS DE ACEPTACIÓN FINAL
════════════════════════════════════════════════════════════════════

El sistema está listo para operar live cuando se cumplan TODOS:

[ ] pytest tests/fast_desk -q → 0 failures
[ ] pytest tests/smc_desk -q → 0 failures  
[ ] grep -r "min_rr.*2\.0" src/ apps/ → 0 resultados
[ ] PUT /api/v1/config/fast con min_rr=3.0 → persiste en runtime
[ ] Ejecución de pipe scan_and_execute() con send_entry que falla → fila en fast_desk_signals con outcome="error"
[ ] Con balance=$1M: calculate_lot_size() retorna ≤ max_lot_size (10.0 por defecto)
[ ] WITH 1 posición en EURUSD/buy: can_open("EURUSD", "sell", ...) → False
[ ] Diagnóstico fast_desk_signals tras 10 minutos de operación → filas visibles
```

---

## 5. Resumen Ejecutivo del Contraste

**El informe Codex aporta evidencia que mi audit no tenía:**
1. Tests ejecutados: 3 fallos reales con nombres de archivo y líneas específicas
2. Identificó el hot-reload parcial con evidencia de líneas exactas
3. Cuantificó la SMC quality label en `rr >= 2.4` con referencia de línea
4. Detectó el drift de env vars (`FAST_DESK_*` vs `FAST_TRADER_*`) en la API

**Mi audit aportó hallazgos que el informe Codex no tuvo:**
1. `micro_choch` trigger sin `confirmed=True` — riesgo de señales falsas estructurales
2. `breakout_retest` sin filtro de edad en BOS — setups de 15h generando entradas
3. FVG como herramienta estratégica ausente — oportunidad de confluencia crítica para scalping
4. `hard_cut_r=1.25 > 1.0` — dilución de RR en custody
5. 6× llamadas duplicadas a `detect_market_structure()` por ciclo — performance
6. `rejection_candle` operable sobre 1 vela sin contexto de zona

**El hallazgo de "código muerto" fue incorrecto en ambos informes:**
`FastScannerConfig` NO es puro código muerto — se instancia y pasa al worker. Es **código redundante**: sus valores son duplicados exactos de `FastSetupConfig`, y el path de fallback en el worker nunca se ejecuta en operación normal. La acción correcta es eliminarlo como fuente de configuración y dejar solo `FastSetupConfig`.

---

*Documento generado por GitHub Copilot — 2026-03-27*
