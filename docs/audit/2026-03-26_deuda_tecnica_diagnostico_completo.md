# Deuda Técnica — Diagnóstico Completo Fast Desk / SMC Desk
**Fecha:** 2026-03-26  
**Proyecto:** heuristic-metatrader5-bridge  
**Estado tras restart:** `fast_desk_signals = 0 rows`, `smc_thesis_cache = 0 rows`, cero operaciones ejecutadas  
**Sesiones de diagnóstico:** 2026-03-25 + 2026-03-26

---

## Resumen Ejecutivo

Después de dos sesiones de diagnóstico profundo y tres rondas de correcciones de código, el sistema continua sin generar ninguna operación visible. La causa raíz **no es una sola línea rota** sino una cadena de al menos 10 defectos técnicos interdependientes. Los más críticos son:

1. `SymbolSpecRegistry.pip_size()` devuelve `point` (0.00001) en lugar de `pip` (0.0001) — **el fix de pip_value introducido en DT-003 queda neutralizado** porque `pip_per_point = 0.00001 / 0.00001 = 1.0` siempre.
2. El lot size calculado es ~10× demasiado grande → broker rechaza la orden → sin filas en DB.
3. Errores de ejecución se tragaban silenciosamente (corregido parcialmente, pero el defecto de pip_size invalida el fix).
4. El endpoint `/status` no expone `fast_desk_enabled` ni `smc_desk_enabled` — el stack puede estar caído sin que el operador lo vea.

---

## Inventario de Defectos

### DT-001 — `SymbolSpecRegistry.pip_size()` devuelve point, no pip ⚠️ CRÍTICO

| Atributo | Valor |
|----------|-------|
| **Archivo** | `src/heuristic_mt5_bridge/core/runtime/spec_registry.py:27` |
| **Severidad** | CRÍTICA |
| **Estado** | Abierto |

**Descripción:**  
El método `pip_size()` retorna el campo `point` (el desplazamiento mínimo del símbolo, `1e-05` para pares FX con 5 decimales). En terminología MT5/FX, un **pip** = 10 puntos = `0.0001`. Este método está nombrado incorrectamente y propaga el error silenciosamente a toda la cadena de cálculo.

**Código actual:**
```python
def pip_size(self, symbol: str) -> float | None:
    """Return the `point` value for *symbol*, or None if spec is unknown."""
    spec = self._data.get(str(symbol).upper())
    if spec is None:
        return None
    val = spec.get("point")
    return float(val) if isinstance(val, (int, float)) and float(val) > 0 else None
```

**Evidencia del diagnóstico:**
```
GET /api/v1/fast/diag/GBPUSD →
  pip_size: 1e-05       ← correcto como point, INCORRECTO como pip
  point_size: 1e-05
  pip_per_point_multiplier: 1.0   ← debería ser 10.0
  pip_value_per_lot: 1.0          ← debería ser ~10.0
```

**Impacto del error en cadena:**
```
pip_per_point = pip_size / point_size = 1e-05 / 1e-05 = 1.0  (siempre)
pip_value     = tick_value × pip_per_point = 1.0 × 1.0 = 1.0  (incorrecto)
               debería ser ≈ 10.0 para pares FX estándar
```

**Fix correcto:**
```python
def pip_size(self, symbol: str) -> float | None:
    """Return pip size (= point × 10 for standard 5-decimal FX)."""
    spec = self._data.get(str(symbol).upper())
    if spec is None:
        return None
    point = spec.get("point")
    if not isinstance(point, (int, float)) or float(point) <= 0:
        return None
    # Detectar símbolo con 3 decimales (JPY, VIX, UsDollar): pip = point
    # Símbolo con 5 decimales (EURUSD, GBPUSD, USDCHF): pip = point × 10
    digits = spec.get("digits", 5)
    multiplier = 1 if int(digits) in (2, 3) else 10
    return round(float(point) * multiplier, 10)
```

---

### DT-002 — Lot size excesivo incluso con pip_value correcto ⚠️ CRÍTICO

| Atributo | Valor |
|----------|-------|
| **Archivo** | `src/heuristic_mt5_bridge/fast_desk/risk/engine.py:35` + `.env` |
| **Severidad** | CRÍTICA |
| **Estado** | Parcialmente corregido, insuficiente |

**Descripción:**  
Incluso asumiendo que DT-001 se corrija y `pip_value = 10.0`, los parámetros de riesgo en `.env` generan lotes inmanejables para una cuenta demo de $1.18M en FBS:

```
FAST_DESK_RISK_PERCENT=4.0    → risk_amount = $1,182,668 × 4% = $47,307 por trade
SL típico GBPUSD              → 69 pips
pip_value correcto GBPUSD     → $10.0 por pip por lot

lots_raw = $47,307 / (69 × $10.0) = 68.6 lots   → capped a 50 (nuevo cap)
           50 lots × 130,000 GBP = $6,700,000 notional
```

FBS-Demo permite máximo ~100 lots pero el spread × volume eleva el margen requerido muy por encima del equity disponible en muchos escenarios.

**Adicionalmente**, el endpoint de diagnóstico retornó `risk_pct=5.0` cuando `.env` tiene `FAST_DESK_RISK_PERCENT=4.0`. Esto sugiere que `get_fast_config()` en control_plane.py puede estar leyendo el campo incorrecto del dataclass `FastRiskConfig` (que tiene `max_drawdown_percent=5.0` por defecto), o que hay un mismatch de nombres entre `FastDeskConfig` y `FastRiskConfig`.

**Simulación del impacto (datos reales del diagnóstico):**

| SL (pips) | pip_val actual (buggy) | lots calculados | lots capped | Notional |
|-----------|------------------------|-----------------|-------------|----------|
| 10 | 1.0 | 472,107 | 50.0 | ~$6.5M |
| 50 | 1.0 | 94,613 | 50.0 | ~$6.5M |
| 100 | 1.0 | 47,307 | 50.0 | ~$6.5M |

Con pip_value=1.0 siempre se toca el cap. Aunque se corrija DT-001:

| SL (pips) | pip_val correcto | lots correctos | lots capped | Notional |
|-----------|------------------|----------------|-------------|----------|
| 10 | 10.0 | 472 | 50.0 | ~$6.5M |
| 50 | 10.0 | 94.6 | 50.0 | ~$6.5M |
| 100 | 10.0 | 47.3 | 47.3 | ~$6.1M |

El parámetro `FAST_DESK_RISK_PERCENT=4.0` es **incompatible con una cuenta demo de $1.18M** para trading de FX con lots. El riesgo absoluto debe controlarse vía `max_lot_size`, no solo via `volume_max` del símbolo.

**Fix requerido:**
1. Reducir `FAST_DESK_RISK_PERCENT` a `0.5` o menos en `.env`
2. Agregar `FAST_DESK_MAX_LOT_SIZE=5.0` como techo absoluto por trade en `FastDeskConfig`
3. Investigar la discrepancia `risk_pct=5.0` vs `4.0` en el endpoint de diagnóstico

---

### DT-003 — `send_entry()` tragaba excepciones silenciosamente ⚠️ ALTO (parcialmente corregido)

| Atributo | Valor |
|----------|-------|
| **Archivo** | `src/heuristic_mt5_bridge/fast_desk/trader/service.py:209` |
| **Severidad** | ALTA |
| **Estado** | Corregido en código, pendiente verificación en runtime |

**Descripción (original):**  
La llamada `send_entry()` no estaba envuelta en `try/except`. Cualquier `MT5ConnectorError` propagaba hacia arriba, era capturado por `_run_scan()` con solo un `print()`, y **nunca se escribía ninguna fila en `fast_desk_signals`**. El fallo era totalmente invisible desde la WebUI.

**Corrección aplicada:**
```python
try:
    result = self.execution.send_entry(connector, symbol=symbol, ...)
    outcome = "accepted" if bool(result.get("ok", False)) else "rejected"
except Exception as exec_err:
    result = {"ok": False, "error": str(exec_err)}
    outcome = "error"
    print(f"[fast-desk] execution error ({symbol}/{selected_setup.setup_type}): {exec_err}")
```

**Estado pendiente:**  
Aunque la corrección fue aplicada, la combinación con DT-001 (pip_value erróneo) implica que el broker probablemente sigue rechazando órdenes de 50 lots. El `outcome="error"` al menos ahora quedará registrado en DB una vez que el pipeline llegue a ejecutar (necesita también DT-001 corregido para que produzca lotes razonables que el broker acepte).

---

### DT-004 — `scan_error` en `symbol_worker.py` no persiste en DB ⚠️ ALTO

| Atributo | Valor |
|----------|-------|
| **Archivo** | `src/heuristic_mt5_bridge/fast_desk/workers/symbol_worker.py` |
| **Severidad** | ALTA |
| **Estado** | Abierto |

**Descripción:**  
En `_run_scan()`, cualquier excepción que no sea `MT5ConnectorError` especifica solo un `print()`:

```python
except Exception as exc:
    print(f"[fast-desk] scan error ({symbol}): {exc}")
    # No DB write, no counter, no alert
```

Esto significa que si el scanner, el context checker, o el setup engine fallan en mitad del ciclo, el error desaparece en stdout sin dejar rastro en la DB ni en la WebUI. En producción con logs rotados, esto hace el debugging retroactivo imposible.

**Fix requerido:**
- Escribir a una tabla `fast_desk_errors` (nueva) o al menos a `fast_desk_trade_log` con `action="scan_error"` y `details_json={"error": str(exc), "traceback": ...}`

---

### DT-005 — `/status` no expone estado de desks ⚠️ ALTO

| Atributo | Valor |
|----------|-------|
| **Archivo** | `apps/control_plane.py` + `src/.../core/runtime/service.py` |
| **Severidad** | ALTA |
| **Estado** | Abierto |

**Descripción:**  
Después del restart, `GET /status` devuelve:
```json
{
  "status": "up",
  "health": { "status": "up", ... }
}
```

Las keys `fast_desk_enabled` y `smc_desk_enabled` **no existen en la respuesta**. Cuando se llaman desde la WebUI con `st.get('fast_desk_enabled')` el resultado es `None`. No hay ninguna señal observable de si los workers del Fast Desk y el scanner SMC están corriendo o no.

**`build_live_state()`** en `CoreRuntimeService` no incluye el estado de `self._fast_desk` ni de `self._smc_desk`. El operador no puede saber si los desks están activos sin leer los logs de consola.

**Fix requerido:**
```python
# En build_live_state() o en /status endpoint:
"desks": {
    "fast_desk": {
        "enabled": self._fast_desk is not None,
        "worker_count": len(getattr(self._fast_desk, '_workers', {})),
        "config": {...},
    },
    "smc_desk": {
        "enabled": self._smc_desk is not None,
        ...
    }
}
```

---

### DT-006 — `purge_runtime_db.py` sin confirmación ni autorización ⚠️ ALTO

| Atributo | Valor |
|----------|-------|
| **Archivo** | `scripts/purge_runtime_db.py` |
| **Severidad** | ALTA |
| **Estado** | Abierto |

**Descripción:**  
El script borra las 18 tablas del runtime (incluyendo `fast_desk_signals`, `smc_thesis_cache`, `risk_events_log`, `operation_ownership`) **sin ningún prompt de confirmación y sin flag `--dry-run` por defecto**. Fue ejecutado (probablemente por error) durante esta sesión de diagnóstico, borrando toda la evidencia acumulada.

```
Purging database: storage\runtime.db
Found 18 tables
  ✓ Purged: fast_desk_signals        ←  DATOS PERDIDOS
  ✓ Purged: operation_ownership      ←  POSICIONES HUERFANAS POSIBLES
  ✓ Purged: risk_events_log          ←  AUDIT TRAIL PERDIDO
Database purged successfully!
```

**Riesgo de producción:** Si hay posiciones abiertas en MT5 y se purga `operation_ownership`, el sistema pierde el registro de qué posiciones son suyas, impidiendo el custody y el stop-loss management automático.

**Fix requerido:**
1. Agregar `--confirm` flag obligatorio (no solo `--dry-run` como opcional)
2. Verificar que no haya posiciones abiertas en MT5 antes de borrar `operation_ownership`
3. Mostrar resumen de lo que se va a borrar y pedir confirmación interactiva

---

### DT-007 — SMC `rr_ok=false` para candidatos con RR > 5 ⚠️ MEDIO

| Atributo | Valor |
|----------|-------|
| **Archivo** | `src/.../smc_desk/validators/heuristic.py` (presumible) |
| **Severidad** | MEDIA |
| **Estado** | Abierto |

**Descripción:**  
Del snapshot anterior (antes del purge), el `smc_thesis_cache` mostraba:

| Símbolo | Candidatos | `rr_ok` | RR individual | min_rr config |
|---------|-----------|---------|--------------|--------------|
| GBPUSD | `candidate_count_out=0` | false | 7.2 – 15.4 | 5.0 |
| EURUSD | `candidate_count_out=0` | false | 8.1 – 12.3 | 5.0 |
| USDCHF | 6 candidatos | watching | — | 5.0 |
| USDJPY | `validator_decision=reject` | — | — | — |

Los candidatos tienen RR individual mayor que `min_rr=5.0` pero el campo agregado `rr_ok=false`. El validador heurístico probablemente está evaluando una condición diferente al RR del candidato (e.g., comparando contra el spread actual, calculando RR neto de slippage, o usando la tesis global en vez del candidato individual).

**Impact:** El SMC desk genera cero trades para 2 de 4 símbolos activos por este bug de validación.

---

### DT-008 — `FAST_DESK_RR_RATIO=5.0` bloquea mayoría de setups ⚠️ MEDIO

| Atributo | Valor |
|----------|-------|
| **Archivo** | `.env` |
| **Severidad** | MEDIA |
| **Estado** | Abierto (configuración) |

**Descripción:**  
El parámetro `FAST_DESK_RR_RATIO=5.0` exige que el TP esté a 5× la distancia del SL. Para scalping M1/M5 esto es extremadamente restrictivo. En el mercado actual (sesión Asian/Early London), encontrar setups con 5:1 RR en ese timeframe es muy raro. La combinación con `FAST_DESK_REQUIRE_H1_ALIGNMENT=true` añade otra barrera estructural.

**Evidencia:** En el script de diagnóstico `fast_desk_diag.py`, de 5 símbolos solo GBPUSD llegaba a `*** WOULD EXECUTE ***` con `micro_choch trigger`. El alto RR requerido filtra los setups que sí existen.

**Recomendación:**
- Bajar a `FAST_DESK_RR_RATIO=2.0` o `2.5` para M1/M5 scalping
- O separar la configuración por timeframe

---

### DT-009 — `FAST_DESK_MAX_POSITIONS_PER_SYMBOL=5` y `TOTAL=30` son valores extremos ⚠️ MEDIO

| Atributo | Valor |
|----------|-------|
| **Archivo** | `.env` |
| **Severidad** | MEDIA |
| **Estado** | Abierto (configuración) |

**Descripción:**  
Los límites de posiciones en `.env` son:
```
FAST_DESK_MAX_POSITIONS_PER_SYMBOL=5
FAST_DESK_MAX_POSITIONS_TOTAL=30
```

30 posiciones simultáneas × 50 lots cada una (cap actual) = exposición potencial de $195M notional. Aunque en la práctica el margen disponible lo limitaría antes, esta configuración no tiene ninguna barrera defensiva secundaria. El `FastRiskConfig` en código tiene defaults de 1 y 4, muy distintos a los valores del `.env` en producción.

---

### DT-010 — `VIX` y `UsDollar` en `MT5_WATCH_SYMBOLS` sin manejo especial de pip ⚠️ BAJO

| Atributo | Valor |
|----------|-------|
| **Archivo** | `.env` + `spec_registry.py` |
| **Severidad** | BAJA |
| **Estado** | Abierto |

**Descripción:**  
```
MT5_WATCH_SYMBOLS=BTCUSD,EURUSD,GBPUSD,USDJPY,USDCHF,VIX,UsDollar
```

`VIX` y `UsDollar` (índices) tienen convenciones de pip completamente distintas a los pares FX. El fix de DT-001 (multiplicador ×10 para `digits=5`) puede calcular incorrectamente para estos instrumentos dependiendo de sus `digits`. Además, `tick_value` para índices no es $1.0 por lot. Si el Fast Desk intenta tradear estos símbolos, los lotes calculados serán incorrectos.

---

## Matriz de Prioridad

| ID | Defecto | Severidad | Bloquea trades | Esfuerzo fix |
|----|---------|-----------|----------------|--------------|
| DT-001 | `pip_size()` devuelve point ≠ pip | CRÍTICA | ✅ SÍ | 15 min |
| DT-002 | risk_pct=4% + no max_lot_size absoluto | CRÍTICA | ✅ SÍ | 10 min (.env) |
| DT-003 | send_entry sin try/except | ALTA | ✅ SÍ (aplicado) | ✅ Aplicado |
| DT-004 | scan_error no persiste | ALTA | ⚠️ Parcial | 30 min |
| DT-005 | /status sin estado de desks | ALTA | ❌ NO (observabilidad) | 45 min |
| DT-006 | purge_db sin confirmación | ALTA | ❌ NO (seguridad) | 20 min |
| DT-007 | SMC rr_ok=false con RR>5 | MEDIA | ✅ SÍ (SMC) | Investigar |
| DT-008 | RR_RATIO=5.0 muy restrictivo | MEDIA | ✅ SÍ | 2 min (.env) |
| DT-009 | MAX_POSITIONS=30 extremo | MEDIA | ❌ NO (riesgo) | 2 min (.env) |
| DT-010 | VIX/UsDollar pip handling | BAJA | ⚠️ Parcial | 30 min |

---

## Plan de Acción Inmediata (Orden de Aplicación)

### Paso 1 — `.env` (2 minutos, sin código)
```bash
FAST_DESK_RISK_PERCENT=0.5       # era 4.0
FAST_DESK_RR_RATIO=2.0           # era 5.0
FAST_DESK_MAX_POSITIONS_PER_SYMBOL=1   # era 5
FAST_DESK_MAX_POSITIONS_TOTAL=4        # era 30
```

### Paso 2 — `spec_registry.py` (15 minutos)
```python
def pip_size(self, symbol: str) -> float | None:
    spec = self._data.get(str(symbol).upper())
    if spec is None:
        return None
    point = spec.get("point")
    if not isinstance(point, (int, float)) or float(point) <= 0:
        return None
    digits = int(spec.get("digits", 5) or 5)
    multiplier = 1 if digits in (2, 3) else 10
    return round(float(point) * multiplier, 10)
```

### Paso 3 — Reiniciar backend y verificar con `/api/v1/fast/diag/GBPUSD`
```
Esperado tras fix:
  pip_per_point_multiplier: 10.0     ← fue 1.0
  pip_value_per_lot: 10.0            ← fue 1.0
  lots@50pip after_volume_max_cap: ≈ 2.4   ← fue 50.0
```

### Paso 4 — Monitorear `fast_desk_signals` table
Si `outcome` aparece como `"error"` → revisar `exec_result.error` en el JSON de evidencia.  
Si `outcome = "rejected"` → el broker rechaza aun así → investigar margen/spread.  
Si `outcome = "accepted"` → el sistema funciona.

---

## Archivos Modificados en Esta Sesión (para referencia)

| Archivo | Cambio |
|---------|--------|
| `src/.../fast_desk/trader/service.py` | DT-003: try/except en send_entry; DT-002: pip_value scaling; cap volume_max |
| `src/.../fast_desk/risk/engine.py` | DT-002: cap reducido de 100 a 50 lots |
| `apps/control_plane.py` | DT-005: endpoint `GET /api/v1/fast/diag/{symbol}` agregado |
| `scripts/db_diag.py` | Nuevo script de diagnóstico de DB |
| `scripts/fast_desk_diag.py` | Nuevo script de simulación offline del pipeline |

---

## Notas Adicionales

- `indicator_enrichment: waiting_first_snapshot` — Los indicadores técnicos aún no han llegado al primer snapshot. Si el Fast Desk depende de ATR para calcular el SL, este estado puede bloquear setups en la primera ventana post-restart.
- `clock_warning: True` para GBPUSD/USDCHF/USDJPY — Deriva del reloj local vs servidor MT5 de 4–8 segundos. Puede afectar `stale_feed_seconds` checks si el umbral es ajustado.
- La sesión actual del mercado es `03:19 UTC` = Tokyo/Asian. `FAST_DESK_ALLOWED_SESSIONS` por defecto incluye solo `london,overlap,new_york` — puede que Tokyo no esté permitida y todos los ciclos de scan estén siendo bloqueados por el context checker. Verificar `context.allowed` en los logs.
