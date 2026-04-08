# Fast Desk — Plan de Acción + Prompt Unificado v2 (cotejado con código real)

Fecha: 2026-03-27
Repositorio: `heuristic-metatrader5-bridge`
Fuentes:
- `docs/audit/2026-03-27_fast_desk_analyst_heuristic_deep_audit.md` (audit interna)
- `docs/audit/2026-03-27_fast_desk_action_plan_and_repair_prompt.md` (plan+prompt)
- `docs/audit/codex_fast_desk_analyst_audit_2026-03-27.md` (Codex — con tests ejecutados)
- `docs/audit/2026-03-27_fast_desk_plan_prompt_unificado_realidad_codigo.md` (primera unificación)
Método: lectura completa de los 4 documentos + revisión directa de cada archivo de código referenciado.

**ESTADO: IMPLEMENTADO** — Todas las fases 1-3 ejecutadas y validadas. 143 tests passing.

---

## 1. Criterio de este documento

Ningún informe original se elige como ganador. Los 4 se tratan como insumo y se contrastan línea a línea con el código fuente real. Donde hay discrepancia entre audit y código, el código prevalece. El resultado es un plan corregido, con hallazgos nuevos no presentes en ninguno de los 4 documentos originales.

---

## 2. Correcciones a los informes originales (errores factuales detectados)

### 2.1 Hallazgos que los informes afirmaban INCORRECTAMENTE

| # | Afirmación original | Fuente | Realidad en código | Evidencia |
|---|---------------------|--------|-------------------|-----------|
| C1 | `risk_pct` no se clampea al 2% documentado | Codex #7, Action Plan 2.5 | **SÍ se clampea**: `effective_risk_pct = min(float(risk_pct or 0.0), 2.0)` | `risk/engine.py:96` |
| C2 | `FastDeskConfig.min_rr = 2.0` | Codex #1, Audit Deep P1 | **FastDeskConfig NO tenía campo `min_rr`**. El campo vivía en `FastSetupConfig` vía `DEFAULT_EFFECTIVE_MIN_RR = 2.0` en `__post_init__` | `runtime.py:93-130` (sin min_rr), `setup/engine.py:11-31` |
| C3 | Señales fallidas desaparecen sin trazabilidad post-`send_entry()` | Audit Deep P2 | **NO desaparecen**: el try/except captura el error, marca `outcome="error"`, y SIEMPRE ejecuta `runtime_db.upsert_fast_signal()` después | `trader/service.py:318-361` |
| C4 | Hot-reload solo propaga `FastContextConfig` | Codex #4 | **`update_context_config()` actualiza 6 configs**: context, risk, setup, pending, custody, trader | `runtime.py:183-207` |
| C5 | `FAST_TRADER_MIN_RR` default 2.0 en `from_env()` | Codex #1, primera unificación | **`from_env()` NO leía `FAST_TRADER_MIN_RR`**. No existía tal variable de entorno en el método. min_rr no era campo de FastDeskConfig | `runtime.py:119-148` |
| C6 | `scanner_config` fallback usa rr default 2.0 | Action Plan sección 1 | **Fallback usa `getattr(scanner_config, "rr_ratio", 3.0)`** — default es 3.0, no 2.0 | `symbol_worker.py:73-75` |

### 2.2 Hallazgo NUEVO no presente en ningún informe original

**CRÍTICO — `update_context_config()` hardcodeaba `min_rr = min(cfg.rr_ratio, 2.0)`**

Archivo: `runtime.py:196`
```
self._setup_config.min_rr = min(cfg.rr_ratio, 2.0)
```

Esto significaba:
- Aunque se cambiase `DEFAULT_EFFECTIVE_MIN_RR` a 3.0 en `setup/engine.py`
- Aunque se agregase `min_rr` a `FastDeskConfig` y se configurase en 3.0
- Cada vez que la API invocaba `update_context_config()` (hot-reload), el `min_rr` se RESETEABA a `min(3.0, 2.0) = 2.0`

Ningún audit detectó este bug. Era una segunda fuente de verdad contradictoria que invalidaba cualquier corrección parcial al RR floor.

**Además**: `run_forever()` creaba `FastSetupConfig` SIN pasar `min_rr`:
```
setup_config = FastSetupConfig(rr_ratio=cfg.rr_ratio, min_confidence=cfg.min_signal_confidence)
```
Esto disparaba `__post_init__` que calculaba `min_rr = min(3.0, DEFAULT_EFFECTIVE_MIN_RR=2.0) = 2.0`.

**Conclusión: había 3 puntos donde min_rr se fijaba en 2.0:**
1. `DEFAULT_EFFECTIVE_MIN_RR = 2.0` (constante en setup/engine.py:11)
2. `FastSetupConfig.__post_init__()` cuando min_rr no se pasaba (setup/engine.py:24)
3. `update_context_config()` línea 196 hardcodeaba `min(cfg.rr_ratio, 2.0)`

Los 3 fueron corregidos.

---

## 3. Estado real verificado contra código (hallazgos CONFIRMADOS)

### Críticos

| ID | Hallazgo | Archivo | Estado |
|----|----------|---------|--------|
| V1 | RR floor efectivo en 2.0 vía 3 rutas | `setup/engine.py:11,24`, `runtime.py:196` | ✅ CORREGIDO |
| V2 | API Fast no exponía `min_rr` para escritura | `apps/control_plane.py:254-270` | ✅ CORREGIDO |
| V3 | `FastDeskConfig` no tenía campo `min_rr` | `runtime.py:93-130` | ✅ CORREGIDO |
| V4 | SMC analyst `quality="high"` desde RR 2.4 | `heuristic_analyst.py:412` | ✅ CORREGIDO → `rr >= 3.0` |
| V5 | SMC validator `min_rr` default 2.0 | `validators/heuristic.py:283` | ✅ CORREGIDO → `3.0` |
| V6 | SMC analyst `SmcAnalystConfig.min_rr = 2.0` | `heuristic_analyst.py:59` | ✅ CORREGIDO → `3.0` |

### Altos

| ID | Hallazgo | Archivo | Estado |
|----|----------|---------|--------|
| V7 | `max_slippage_points=30` en fallback worker — TypeError latente | `symbol_worker.py:79` | ✅ CORREGIDO |
| V8 | `micro_choch` no verificaba `confirmed=True` | `trigger/engine.py:72-81` | ✅ CORREGIDO |
| V9 | `breakout_retest` sin filtro de edad de BOS | `setup/engine.py:320+` | ✅ CORREGIDO — filtro >20 candles |
| V10 | `order_block_retest` usa `min_impulse_candles=2` | `setup/engine.py:196` | ✅ CORREGIDO → `3` |
| V11 | `max_positions_per_symbol` no enforced como límite real | `policies/entry.py` | ✅ CORREGIDO |
| V12 | FVG disponible en SMC, no integrado en Fast Desk | `smc_desk/detection/fair_value_gaps.py` | ⬜ FASE 5 (opcional) |
| V13 | Lot size cap hardcoded en 50.0, sin config | `risk/engine.py:127` | ✅ CORREGIDO → `max_lot_size=10.0` configurable |
| V14 | `max_slippage_points` en API → parámetro fantasma | `control_plane.py:265` | ✅ CORREGIDO — eliminado |
| V15 | scanner_config redundante | `runtime.py`, `symbol_worker.py` | ⬜ FASE 4 (baja prioridad) |
| V16 | Drift env vars | `runtime.py`, `control_plane.py` | ⬜ FASE 4 (sin drift crítico actual) |

### Medios

| ID | Hallazgo | Estado |
|----|----------|--------|
| V17 | `hard_cut_r=1.25` > SL planificado | ⬜ FASE 5 — requiere decisión de producto |
| V18 | `detect_market_structure` llamado múltiples veces | ⬜ FASE 5 — optimización |
| V19 | 3 tests fallaban por firma antigua | ✅ Ya no fallan (61/61 pass) |
| V20 | Worker error handling usa `print()` | ⬜ FASE 4 — cosmético |
| V21 | `reprice_threshold_pips=8.0` fijo | ⬜ FASE 5 |
| V22 | EMA seed usa `data[0]` | ⬜ Discutible — EMA estándar |
| V23 | Legacy bridge tipos no definidos | ⬜ Bridge deprecado |

---

## 4. Tests — evidencia post-implementación

```
ANTES:
  pytest tests/fast_desk     → 53 passed, 3 failed
  pytest tests/smc_desk      → 30 passed

DESPUÉS:
  pytest tests/fast_desk     → 61 passed, 0 failed
  pytest tests/smc_desk      → 30 passed
  pytest tests/               → 143 passed, 0 failed
```

Validaciones grep:
```
grep -rn "min_rr.*2\.0|DEFAULT_EFFECTIVE_MIN_RR.*2" src/ apps/ → 0 resultados
```

---

## 5. Cambios implementados — resumen por archivo

### FASE 1 — CRÍTICA: Cerrar brecha RR >= 3.0 ✅

| Archivo | Cambios |
|---------|---------|
| `src/heuristic_mt5_bridge/fast_desk/setup/engine.py` | `DEFAULT_EFFECTIVE_MIN_RR = 2.0` → `3.0` |
| `src/heuristic_mt5_bridge/fast_desk/runtime.py` | 5 cambios: campo `min_rr: float = 3.0` en FastDeskConfig, `from_env()`, `to_dict()`, `run_forever()` pasa min_rr a FastSetupConfig, `update_context_config()` usa `cfg.min_rr` en vez de hardcode |
| `src/heuristic_mt5_bridge/smc_desk/analyst/heuristic_analyst.py` | `min_rr: float = 2.0` → `3.0`, `SMC_MIN_RR` default → `"3.0"`, `rr >= 2.4` → `rr >= 3.0` |
| `src/heuristic_mt5_bridge/smc_desk/validators/heuristic.py` | `min_rr: float = 2.0` → `3.0` |
| `apps/control_plane.py` | `min_rr` agregado a FastConfigUpdateRequest, `_FAST_ENV_MAP`, GET/PUT fallbacks; SMC GET/PUT defaults → `"3.0"` |
| `tests/fast_desk/test_fast_runtime_dynamic_workers.py` | Assertion `min_rr == 2.0` → `3.0` |
| `tests/fast_desk/test_fast_setup_trigger.py` | Mock rr `3.0` → `3.5` (para pasar spread filter), assertion `> 2.0` → `> 3.0` |

### FASE 2 — ALTA: Riesgo, contratos y observabilidad ✅

| Archivo | Cambios |
|---------|---------|
| `src/heuristic_mt5_bridge/fast_desk/risk/engine.py` | `max_lot_size: float = 10.0` en FastRiskConfig; `min(50.0, ...)` → `min(self.config.max_lot_size, ...)` |
| `src/heuristic_mt5_bridge/fast_desk/runtime.py` | `max_lot_size` en FastDeskConfig, from_env, to_dict, run_forever, update_context_config |
| `src/heuristic_mt5_bridge/fast_desk/workers/symbol_worker.py` | Eliminado `max_slippage_points=30` del fallback FastTraderConfig |
| `src/heuristic_mt5_bridge/fast_desk/policies/entry.py` | Agregado per-symbol position count antes de max_positions_total check |
| `apps/control_plane.py` | `max_lot_size` en FastConfigUpdateRequest, _FAST_ENV_MAP, GET/PUT fallbacks |

### FASE 3 — MEDIA: Calidad de señal ✅

| Archivo | Cambios |
|---------|---------|
| `src/heuristic_mt5_bridge/fast_desk/trigger/engine.py` | `micro_choch`: check `confirmed=True` antes de aceptar señal |
| `src/heuristic_mt5_bridge/fast_desk/setup/engine.py` | BOS age filter (>20 candles → reject); `min_impulse_candles=2` → `3` |
| `apps/control_plane.py` | Eliminado `max_slippage_points` de FastConfigUpdateRequest |

---

## 6. Fases pendientes (baja prioridad)

### FASE 4 — Limpieza y consistencia runtime

- Eliminar `scanner_config` redundante de `runtime.py:239-242`
- Unificar namespace env vars en API fallback
- Reemplazar `print()` por logging estructurado en symbol_worker.py

### FASE 5 — Estratégica (no bloqueante)

- Integrar FVG como confluencia en Fast Desk setup engine
- Centralizar estructuras SMC precalculadas en FastContext
- Revisar `custody hard_cut_r=1.25` (decisión de producto)
- Calibrar `reprice_threshold_pips` por asset class

---

## 7. Prompt de reparación (para referencia futura)

```
PROMPT DE REPARACIÓN ARQUITECTÓNICA — v2 (cotejado con código)
Sistema: heuristic-metatrader5-bridge (Fast Desk + SMC Analyst)
Fecha de base: 2026-03-27
Rol: Arquitecto de software de trading de alta velocidad / scalping heurístico.

================================================================
CONTEXTO VERIFICADO DEL SISTEMA
================================================================

Stack Python + MetaTrader 5 (conector propio).
Pipeline Fast Desk: Context → Setup → Trigger → Risk → Entry → Execution → Custody
Mandato: RR >= 3.0 en toda señal ejecutada. Sin excepciones.
Pipeline SMC Desk: Scanner → Analyst → Validator → Thesis → Execution (separado)

ESTADO DE TESTS POST-IMPLEMENTACIÓN:
  pytest tests/fast_desk → 61 passed
  pytest tests/smc_desk  → 30 passed
  pytest tests/           → 143 passed

HALLAZGO CRÍTICO DESCUBIERTO Y CORREGIDO:
  update_context_config() en runtime.py hardcodeaba min_rr = min(cfg.rr_ratio, 2.0)
  Ahora usa cfg.min_rr directamente.

HALLAZGOS QUE LAS AUDITS AFIRMARON MAL (verificados):
  - risk_pct SÍ está clampeado a 2.0 (risk/engine.py:96)
  - Señales SÍ se persisten después de error en send_entry() (trader/service.py:340-361)
  - update_context_config SÍ actualiza 6 configs, no solo context
```

---

## 8. Resumen ejecutivo

Los 4 documentos de auditoría apuntaban correctamente al núcleo del problema: el stack no garantizaba RR >= 3.0 de extremo a extremo. Sin embargo, al cotejar con el código real se encontraron:

**3 errores factuales relevantes en las auditorías:**
1. `risk_pct` SÍ está clampeado a 2.0 (el Codex audit y el action plan afirmaron lo contrario)
2. Las señales SÍ se persisten después de errores de ejecución (la audit profunda afirmó lo contrario)
3. `update_context_config()` SÍ actualiza 6 configs, no solo context (el Codex audit afirmó lo contrario)

**1 hallazgo crítico nuevo no detectado por ningún informe:**
`update_context_config()` hardcodeaba `min_rr = min(cfg.rr_ratio, 2.0)`, lo que invalidaba cualquier corrección parcial al RR floor. Además, `FastDeskConfig` no tenía campo `min_rr`, así que no había pathway de configuración. Estos eran los puntos ciegos reales del sistema.

**Implementación completada:**
- FASE 1 (CRÍTICA): RR floor 3.0 cerrado en todas las rutas — Fast Desk, SMC Desk, API ✅
- FASE 2 (ALTA): max_lot_size configurable, per-symbol position limit, phantom params eliminados ✅
- FASE 3 (MEDIA): micro_choch confirmed check, BOS age filter, OB impulse candles ✅
- 143/143 tests passing, 0 grep hits para min_rr=2.0
