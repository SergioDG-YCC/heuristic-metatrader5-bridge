# Deuda técnica — WebUI R1-R4

**Fecha**: 2026-03-25  
**Estado**: PENDIENTE  
**Referencia**: `STRUCTURAL_PLAN_SESSIONS_SPREAD_RISK.md`

---

## Contexto

Se reclamó que las correcciones R1-R4 estaban implementadas. La auditoría revela que el código backend y el código TSX existen, pero **los paneles no se renderizan** en producción y hay decisiones de diseño incorrectas.

---

## Lo que SÍ está en el código de Settings.tsx

El archivo fuente (755 líneas) **sí contiene**:

- **SMC panel**: Select de `spread_tolerance` + tabla editable 3×6 de `spread_thresholds`
- **Fast panel**: Select de `spread_tolerance` + tabla editable 3×6 de `spread_thresholds` + checkboxes de `allowed_sessions`
- **Risk panel**: Global Overrides con 6 inputs editables + desk limits computados (read-only)
- **Budget Allocation**: Dos sliders independientes (`fast_budget_weight` y `smc_budget_weight`)

Los endpoints del backend también devuelven correctamente los campos `spread_thresholds`, `spread_tolerance`, `overrides`, `effective_limits`, y `allocator`.

---

## Capturas vs. código

| Captura | Lo que muestra | Diagnóstico |
|---|---|---|
| **Settings (SMC/Fast)** | SMC: "Loading SMC config…" / Fast: "Loading Fast config…" | **La API falla o no devuelve data** → los `<Show when={smcConfig()}>` y `<Show when={fastConfig()}>` caen al fallback. Los paneles no cargan, por eso no se ven los controles editables. |
| **Settings (Risk)** | Se ve Profiles, Budget y Overrides editables correctamente | El panel Risk **sí cargó** — esto confirma que la API risk funciona. Los campos editables existen. |
| **Settings (error)** | Error rojo: "Failed to save llm config: HTTP 500 — /api/v1/llm/models/default" | El control_plane tiene un error 500 en el endpoint LLM, lo cual puede estar afectando el `Promise.all` que carga todos los configs juntos. |

---

## Problema #0 — Bug crítico: `Promise.all` mata todos los paneles

**Archivo**: `apps/webui/src/routes/Settings.tsx` (líneas 22-40)

En `loadAllConfigs()` hay un `Promise.all(...)` que carga los 6 configs simultáneamente. **Si cualquiera** de las 6 promesas falla (ej: el endpoint LLM que muestra error 500), el bloque `catch` se ejecuta y **ningún config se setea**.

```typescript
const [llmModelsRes, llmStatusRes, smc, fast, ownership, risk] = await Promise.all([
  api.getLlmModels(),    // ← si esto falla con 500...
  api.getLlmStatus(),
  api.getSmcConfig(),
  api.getFastConfig(),
  api.getOwnershipConfig(),
  api.getRiskConfig(),
]);
```

**Resultado**: Los paneles SMC y Fast quedan permanentemente en "Loading…" aunque el backend tenga la data lista.

**Solución requerida**: Cambiar a `Promise.allSettled` o envolver cada llamada en try/catch individual.

---

## Problema R2 — Sesiones: cambio no solicitado y hardcodeado

**Archivo**: `src/heuristic_mt5_bridge/core/runtime/market_state.py` (líneas 14-22)

Se hardcodearon las horas UTC en `session_name_from_timestamp()`:

```python
def session_name_from_timestamp(ts: datetime) -> str:
    hour = ts.hour
    if 7 <= hour < 13:  return "london"
    if 13 <= hour < 17: return "overlap"
    if 17 <= hour < 23: return "new_york"
    return "tokyo"  # 23:00-06:59 UTC
```

### Lo que se pidió vs. lo que se hizo

| Se pidió | Se hizo |
|---|---|
| Botones selectores en WebUI para gestionar sesiones | Se adivinaron horas y se hardcodearon en Python |
| Los horarios operables los fija la especificación de cada símbolo | Se asumió un mapa UTC fijo ignorando el spec del símbolo |
| No hay un tramo "unknown" — no se asume que a cierta hora no se puede | Se eliminó "unknown" pero se reemplazó con otra asunción (tokyo cubre todo lo que sobra) |

### Lo que debería hacerse

Las sesiones deben derivarse de `trade_mode` y los horarios del spec del símbolo (que ya llegan del connector MT5), no de un mapa UTC fijo inventado. Los selectores en WebUI deben controlar la **preferencia de operación** del usuario, no redefinir la realidad del mercado.

Los checkboxes de "Allowed Market Sessions" que existen en el TSX (solo en Fast Desk) son un filtro de qué sesiones son elegibles — pero las definiciones de horarios siguen siendo la asunción hardcodeada.

---

## Problema R3 — Budget Allocation no es entendible

**Archivo**: `apps/webui/src/routes/Settings.tsx` (sección Risk → Budget Allocation)

### Estado actual

Dos sliders independientes con pesos abstractos:
- `fast_budget_weight`: rango 0.1 → 3.0 (default 1.2)
- `smc_budget_weight`: rango 0.1 → 3.0 (default 0.8)

Debajo muestra "Computed Allocation" con porcentajes derivados (ej: Fast 60%, SMC 40%).

### Lo que se pidió

> "Un solo deslizador asignando porcentualmente a Fast o SMC es mas apropiado, o agregar un deslizador general de % a FAST ó SMC"

### Solución requerida

Reemplazar los dos sliders abstractos por **un solo slider porcentual** (0-100%):
- Extremo izquierdo: 100% Fast / 0% SMC
- Extremo derecho: 0% Fast / 100% SMC
- Default: 60% Fast / 40% SMC

El backend puede seguir usando pesos internamente, pero el WebUI debe presentar porcentaje directo.

---

## Problema R1/R4 — Los controles editables existen pero no se ven

### Panel SMC — Controles que existen en TSX pero no renderizan:
- Select `spread_tolerance` (Low/Medium/High)
- Tabla 3×6 editable de `spread_thresholds`
- Slider `max_candidates`
- Input `min_rr`
- Checkbox `llm_enabled`

### Panel Fast — Controles que existen en TSX pero no renderizan:
- Slider `scan_interval`
- Slider `risk_per_trade_percent`
- Input `max_positions_total`
- Select `spread_tolerance`
- Tabla 3×6 editable de `spread_thresholds`
- Checkboxes `allowed_sessions`

### Causa raíz

Todo se reduce al Bug #0 (`Promise.all`). Si la carga de LLM falla con 500, ninguno de los 6 configs se asigna → los `<Show when={...}>` caen al fallback → "Loading config…" permanente.

**Una vez resuelto el Bug #0**, los controles deberían aparecer — pero necesitan verificación visual real.

---

## Resumen de acciones

| # | Problema | Prioridad | Acción |
|---|---|---|---|
| **Bug #0** | `Promise.all` mata todos los paneles si un endpoint falla | **CRÍTICO** | Cambiar a `Promise.allSettled` o try/catch individuales |
| **R2** | Horarios hardcodeados en Python, no vienen del símbolo | **ALTA** | Replantear: sesiones deben derivarse del spec del símbolo, no de mapa UTC fijo |
| **R3** | Budget con 2 sliders abstractos (pesos) | **MEDIA** | Reemplazar por 1 slider porcentual 0-100% (Fast ↔ SMC) |
| **R1/R4** | Controles editables no se renderizan | **Derivado de Bug #0** | Se resuelve al arreglar Bug #0 + verificación visual |

---

## Verificación del backend (sin problemas)

Los endpoints del control_plane están correctos:

| Endpoint | Campos clave | Estado |
|---|---|---|
| `GET /api/v1/config/fast` | Incluye `spread_thresholds`, `spread_tolerance`, `allowed_sessions` | ✅ OK |
| `GET /api/v1/config/smc` | Incluye `spread_tolerance`, `spread_thresholds` | ✅ OK |
| `GET /api/v1/config/risk` | Incluye `effective_limits`, `overrides`, `allocator` | ✅ OK |
| `PUT` para cada uno | Validación de estructura correcta | ✅ OK |

El `api/client.ts` tiene los métodos correspondientes (`getFastConfig`, `getSmcConfig`, `getRiskConfig` + updates). No hay desconexión de contrato entre frontend y backend — el problema es puramente de rendering por la falla en cascada del `Promise.all`.
