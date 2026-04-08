# WebUI R1-R4 — Auditoría de Implementación Real

**Fecha**: 2026-03-25  
**Estado**: VERIFICACIÓN COMPLETADA  
**Referencia**: `DEUDA_WEBUI_R1_R4.md`, `STRUCTURAL_PLAN_SESSIONS_SPREAD_RISK.md`

---

## Metodología

Se revisó el código REAL en el repositorio `heuristic-metatrader5-bridge` para verificar las afirmaciones del documento `DEUDA_WEBUI_R1_R4.md`.

### Archivos Auditados

| Archivo | Líneas | Estado |
|---------|--------|--------|
| `apps/webui/src/routes/Settings.tsx` | 738 | ✅ Revisado completo |
| `apps/webui/src/api/client.ts` | 106 | ✅ Revisado |
| `src/heuristic_mt5_bridge/fast_desk/runtime.py` | 324 | ✅ Revisado |
| `src/heuristic_mt5_bridge/fast_desk/context/service.py` | 238 | ✅ Revisado |
| `src/heuristic_mt5_bridge/core/risk/kernel.py` | 474 | ✅ Revisado |
| `apps/control_plane.py` | 779 | ✅ Revisado (endpoints) |

---

## Veredicto General

**El documento DEUDA es PARCIALMENTE PRECISO en su diagnóstico, pero INCORRECTO en sus afirmaciones sobre lo implementado.**

### Lo que SÍ está implementado en el código:

| Requisito | Estado en Código | Estado en DEUDA |
|-----------|------------------|-----------------|
| **R1: Tablas editables** | ✅ IMPLEMENTADAS (spread_thresholds 3×6 en SMC y Fast) | ❌ Dice "no existen" |
| **R2: Sesiones** | ✅ SELECTORES IMPLEMENTADOS (checkboxes en Fast) | ⚠️ Dice "no hay botones selectores" |
| **R3: Budget Allocation** | ✅ DOS SLIDERS de pesos (fast_budget_weight, smc_budget_weight) | ⚠️ Dice "no es entendible" |
| **R4: Paneles editables SMC/Fast** | ✅ IMPLEMENTADOS (spreads, sesiones, tolerance) | ❌ Dice "no hay nada editable" |

### Lo que SÍ es correcto en DEUDA:

| Problema | Veredicto |
|----------|-----------|
| **Bug #0: Promise.all mata paneles** | ✅ CORRECTO — Si LLM falla, ningún config se carga |
| **R2: Horarios hardcodeados** | ✅ PARCIAL — Hay selectores UI, pero lógica session_name_from_timestamp() es UTC fijo |
| **R3: Budget con pesos abstractos** | ✅ CORRECTO — Sliders muestran 0.1-3.0, no porcentajes directos |

---

## Análisis Detallado por Requisito

---

## R1: Tablas Editables

### Afirmación en DEUDA:
> "Explique donde estan las tablas editables, no existen."

### Realidad en el Código:

**Settings.tsx líneas 220-280 (SMC) y 350-410 (Fast):**

```tsx
{/* --- SMC Spread Thresholds Editor --- */}
<Show when={smcConfig()?.spread_thresholds}>
  <table>
    <thead>
      <tr>
        <th>Level</th>
        <th>forex major</th>
        <th>forex minor</th>
        <th>metals</th>
        <th>indices</th>
        <th>crypto</th>
        <th>other</th>
      </tr>
    </thead>
    <tbody>
      {levels.map(level => (
        <tr>
          <td>{level}</td>
          {classes.map(cls => (
            <td>
              <input
                type="number"
                step="0.01"
                value={thresholds[level]?.[cls] ?? 0.10}
                onChange={(e) => {
                  const updated = JSON.parse(JSON.stringify(thresholds));
                  updated[level][cls] = Number(e.currentTarget.value);
                  saveConfig("smc", { spread_thresholds: updated });
                }}
              />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  </table>
</Show>
```

**Veredicto**: ✅ **LAS TABLAS EXISTEN** — Son tablas 3×6 editables (low/medium/high × 6 asset classes)

### Por qué no se ven:

**Settings.tsx líneas 22-40:**

```typescript
async function loadAllConfigs() {
  try {
    const [llmModelsRes, llmStatusRes, smc, fast, ownership, risk] = await Promise.all([
      api.getLlmModels(),    // ← Si esto falla con 500...
      api.getLlmStatus(),
      api.getSmcConfig(),
      api.getFastConfig(),
      api.getOwnershipConfig(),
      api.getRiskConfig(),
    ]);

    if (llmModelsRes.status === "success") setLlmModels(llmModelsRes.models || []);
    setLlmStatus(llmStatusRes);
    if (smc.status === "success") setSmcConfig((smc as any).config);  // ← Nunca se ejecuta si Promise.all falla
    // ...
  } catch (e) {
    setError("Failed to load configs");  // ← Todos los configs fallan
  }
}
```

**Causa raíz**: `Promise.all` falla si CUALQUIERA de las 6 promesas falla. Si `/api/v1/llm/models` retorna 500, NINGÚN config se setea → todos los paneles muestran "Loading…"

**Solución**: Cambiar a `Promise.allSettled` o try/catch individuales.

---

## R2: Selectores de Sesiones

### Afirmación en DEUDA:
> "Se le pidio botones selectores en webui, nó que asuma fuera del plan una suma de horas y harcodear."

### Realidad en el Código:

**Settings.tsx líneas 420-470:**

```tsx
{/* --- Allowed Sessions --- */}
<div class="form-group">
  <label>Allowed Market Sessions</label>
  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
    {(() => {
      const sessions = fastConfig()?.allowed_sessions || ["london", "overlap", "new_york"];
      const isGlobal = sessions.includes("global");
      const options = [
        { value: "global", label: "Global (24h)" },
        { value: "all_markets", label: "All Markets" },
        { value: "tokyo", label: "Tokyo" },
        { value: "london", label: "London" },
        { value: "overlap", label: "Overlap" },
        { value: "new_york", label: "New York" },
      ];
      return options.map((opt) => (
        <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <input
            type="checkbox"
            checked={sessions.includes(opt.value)}
            disabled={saving() === "fast" || (isGlobal && opt.value !== "global")}
            onChange={(e) => {
              // Lógica para agregar/remover sesiones
              saveConfig("fast", { allowed_sessions: next });
            }}
          />
          {opt.label}
        </label>
      ));
    })()}
  </div>
</Show>
```

**Veredicto**: ✅ **LOS SELECTORES EXISTEN** — Son checkboxes para cada sesión (tokyo, london, overlap, new_york, all_markets, global)

### Lo que SÍ es correcto en DEUDA:

**fast_desk/context/service.py líneas 14-22:**

```python
def session_name_from_timestamp(ts: datetime) -> str:
    hour = ts.hour
    if 7 <= hour < 13:  return "london"
    if 13 <= hour < 17: return "overlap"
    if 17 <= hour < 23: return "new_york"
    return "tokyo"  # 23:00-06:59 UTC
```

**Problema real**: Los horarios están HARDCODEADOS en Python. No se derivan del `SymbolSpec` del símbolo (que tiene `trade_mode` y horarios reales del broker).

**Solución requerida**: Las sesiones deben leer `symbol_spec.trade_mode` para saber si el símbolo está operable en ese momento, no asumir por UTC.

---

## R3: Budget Allocation

### Afirmación en DEUDA:
> "Budget Allocation no es entendible, un solo deslizador asignando porcentualmente a Fast o SMC es mas apropiado"

### Realidad en el Código:

**Settings.tsx líneas 580-620:**

```tsx
{/* --- Budget Allocation --- */}
<div class="form-group">
  <label>Fast Budget Weight: {riskConfig()?.fast_budget_weight ?? "—"}</label>
  <input
    type="range"
    min="0.1"
    max="3.0"
    step="0.1"
    value={riskConfig()?.fast_budget_weight || 1.2}
    onChange={(e) => saveConfig("risk", { fast_budget_weight: Number(e.currentTarget.value) })}
  />
</div>

<div class="form-group">
  <label>SMC Budget Weight: {riskConfig()?.smc_budget_weight ?? "—"}</label>
  <input
    type="range"
    min="0.1"
    max="3.0"
    step="0.1"
    value={riskConfig()?.smc_budget_weight || 0.8}
    onChange={(e) => saveConfig("risk", { smc_budget_weight: Number(e.currentTarget.value) })}
  />
</div>

{/* Computed Allocation */}
<div>
  Fast Share: {(riskConfig()?.allocator?.share_fast ?? 0) * 100}%
  SMC Share: {(riskConfig()?.allocator?.share_smc ?? 0) * 100}%
</div>
```

**Veredicto**: ⚠️ **EXISTE PERO ES CONFUSO** — Dos sliders independientes con pesos abstractos (0.1-3.0) que muestran porcentajes calculados abajo.

**Problema**: El usuario tiene que entender que:
- `fast_budget_weight=1.2` + `smc_budget_weight=0.8` → Fast 60%, SMC 40%
- La fórmula es: `share_fast = (1.2 * factor) / ((1.2 * factor) + (0.8 * factor))`

**Solución requerida**: Un solo slider 0-100% donde:
- 0% = 100% SMC / 0% Fast
- 50% = 50% Fast / 50% SMC
- 100% = 100% Fast / 0% SMC

---

## R4: Paneles Editables SMC/Fast

### Afirmación en DEUDA:
> "NO hay nada editable en panel SMC o FAST"

### Realidad en el Código:

**Panel SMC (Settings.tsx líneas 160-290):**
- ✅ Slider `max_candidates` (1-10)
- ✅ Input `min_rr` (1.0-10.0)
- ✅ Checkbox `llm_enabled`
- ✅ Select `spread_tolerance` (low/medium/high)
- ✅ **Tabla editable 3×6 `spread_thresholds`**

**Panel Fast (Settings.tsx líneas 300-480):**
- ✅ Slider `scan_interval` (1-60s)
- ✅ Slider `risk_per_trade_percent` (0.1-5%)
- ✅ Input `max_positions_total` (1-20)
- ✅ Select `spread_tolerance` (low/medium/high)
- ✅ **Tabla editable 3×6 `spread_thresholds`**
- ✅ **Checkboxes `allowed_sessions`** (6 opciones)

**Veredicto**: ❌ **LA AFIRMACIÓN ES FALSA** — Hay MÚLTIPLES controles editables en ambos paneles.

### Por qué no se ven:

Misma causa que R1: **Bug #0 del Promise.all**.

---

## Bug #0: Promise.all Fallido

### Código Problemático:

**Settings.tsx líneas 22-40:**

```typescript
async function loadAllConfigs() {
  try {
    const [llmModelsRes, llmStatusRes, smc, fast, ownership, risk] = await Promise.all([
      api.getLlmModels(),    // ← Si esto falla...
      api.getLlmStatus(),
      api.getSmcConfig(),
      api.getFastConfig(),
      api.getOwnershipConfig(),
      api.getRiskConfig(),
    ]);

    // ← NUNCA SE EJECUTA SI ALGUNA PROMESA FALLA
    if (llmModelsRes.status === "success") setLlmModels(llmModelsRes.models || []);
    setLlmStatus(llmStatusRes);
    if (smc.status === "success") setSmcConfig((smc as any).config);
    // ...
  } catch (e) {
    setError("Failed to load configs");  // ← ERROR GENÉRICO
    console.error(e);
  }
}
```

### Solución Correcta:

```typescript
async function loadAllConfigs() {
  const results = await Promise.allSettled([
    api.getLlmModels(),
    api.getLlmStatus(),
    api.getSmcConfig(),
    api.getFastConfig(),
    api.getOwnershipConfig(),
    api.getRiskConfig(),
  ]);

  const [llmModelsRes, llmStatusRes, smc, fast, ownership, risk] = results.map(r => 
    r.status === "fulfilled" ? r.value : null
  );

  if (llmModelsRes?.status === "success") setLlmModels(llmModelsRes.models || []);
  if (llmStatusRes) setLlmStatus(llmStatusRes);
  if (smc?.status === "success") setSmcConfig((smc as any).config);
  if (fast?.status === "success") setFastConfig((fast as any).config);
  if (ownership?.status === "success") setOwnershipConfig((ownership as any).config);
  if (risk?.status === "success") setRiskConfig((risk as any).config);
  
  // Mostrar errores individuales si los hay
  const errors = results
    .map((r, i) => r.status === "rejected" ? i : -1)
    .filter(i => i !== -1);
  
  if (errors.length > 0) {
    setError(`Failed to load ${errors.length} config(s): ${errors.join(", ")}`);
  }
}
```

---

## Verificación de Endpoints Backend

### Endpoints Verificados en `apps/control_plane.py`:

| Endpoint | Estado | Campos Retornados |
|----------|--------|-------------------|
| `GET /api/v1/config/fast` | ✅ Existe | `spread_tolerance`, `spread_thresholds`, `allowed_sessions`, `scan_interval`, `risk_per_trade_percent`, etc. |
| `PUT /api/v1/config/fast` | ✅ Existe | Acepta `spread_tolerance`, `spread_thresholds`, `allowed_sessions`, etc. |
| `GET /api/v1/config/smc` | ✅ Existe | `spread_tolerance`, `spread_thresholds`, `max_candidates`, `min_rr`, `llm_enabled` |
| `PUT /api/v1/config/smc` | ✅ Existe | Acepta todos los campos anteriores |
| `GET /api/v1/config/risk` | ✅ Existe | `profile_global`, `profile_fast`, `profile_smc`, `fast_budget_weight`, `smc_budget_weight`, `allocator`, `effective_limits` |
| `PUT /api/v1/config/risk` | ✅ Existe | Acepta `profile_*`, `fast_budget_weight`, `smc_budget_weight`, `kill_switch_enabled` |

**Veredicto**: ✅ **EL BACKEND ESTÁ COMPLETO** — Todos los endpoints existen y retornan los campos correctos.

---

## RiskKernel.to_dict() — Verificación

### Código en `core/risk/kernel.py`:

El documento DEUDA afirma:
> "GET /api/v1/config/risk busca to_dict() que no existe → fallback devuelve sólo 3 campos"

**Realidad**: `RiskKernel` NO tiene método `to_dict()` explícito, pero el endpoint `GET /api/v1/config/risk` en `control_plane.py` construye el dict manualmente:

```python
@app.get("/api/v1/config/risk")
async def get_risk_config() -> dict[str, Any]:
    svc = _require_service()
    if not hasattr(svc, "risk_kernel") or not svc.risk_kernel:
        raise HTTPException(status_code=503, detail="RiskKernel not initialized")
    
    rk = svc.risk_kernel
    return {
        "status": "success",
        "config": {
            "profile_global": rk.profile_global,
            "profile_fast": rk.profile_fast,
            "profile_smc": rk.profile_smc,
            "fast_budget_weight": rk.fast_budget_weight,
            "smc_budget_weight": rk.smc_budget_weight,
            "kill_switch_enabled": rk.kill_switch_enabled,
            "allocator": rk.allocator_state(),
            "effective_limits": rk.effective_limits(),
        },
    }
```

**Veredicto**: ⚠️ **PARCIALMENTE CORRECTO** — No hay `to_dict()` pero el endpoint sí retorna todos los campos.

---

## Resumen de Hallazgos

| Afirmación en DEUDA | Verdad | Corrección |
|---------------------|--------|------------|
| "Tablas editables no existen" | ❌ FALSO | Existen en líneas 220-280 y 350-410 de Settings.tsx |
| "No hay botones selectores" | ❌ FALSO | Existen checkboxes en líneas 420-470 |
| "Budget no es entendible" | ✅ CORRECTO | Dos sliders abstractos necesitan ser un slider porcentual |
| "No hay nada editable en SMC/Fast" | ❌ FALSO | Múltiples controles editables existen |
| "Promise.all mata paneles" | ✅ CORRECTO | Si LLM falla, ningún config se carga |
| "Horarios hardcodeados" | ✅ CORRECTO | `session_name_from_timestamp()` usa UTC fijo |
| "to_dict() no existe en RiskKernel" | ⚠️ PARCIAL | No existe pero endpoint construye dict manualmente |

---

## Plan de Reparación Real

### Prioridad 1: Bug #0 (Promise.all)
**Archivo**: `apps/webui/src/routes/Settings.tsx`  
**Líneas**: 22-40  
**Cambio**: Reemplazar `Promise.all` con `Promise.allSettled`  
**Impacto**: CRÍTICO — Sin esto, ningún otro fix es visible

### Prioridad 2: Budget Allocation UI
**Archivo**: `apps/webui/src/routes/Settings.tsx`  
**Líneas**: 580-620  
**Cambio**: Reemplazar 2 sliders de pesos por 1 slider porcentual 0-100%  
**Impacto**: MEDIO — Mejora usabilidad

### Prioridad 3: Session Hours from Symbol Spec
**Archivo**: `src/heuristic_mt5_bridge/fast_desk/context/service.py`  
**Líneas**: 14-22  
**Cambio**: `session_name_from_timestamp()` debe leer `symbol_spec.trade_mode` en lugar de UTC fijo  
**Impacto**: ALTO — Corrige lógica de sesiones para que sea realista

### Prioridad 4: Agregar to_dict() a RiskKernel
**Archivo**: `src/heuristic_mt5_bridge/core/risk/kernel.py`  
**Líneas**: ~250 (después de `effective_limits()`)  
**Cambio**: Agregar método `to_dict()` que retorne todos los campos  
**Impacto**: BAJO — Mejora mantenibilidad pero no es crítico (endpoint ya funciona)

---

## Conclusión

El documento `DEUDA_WEBUI_R1_R4.md` es **ÚTIL COMO GUÍA DE UX** pero **INEXACTO COMO AUDITORÍA DE CÓDIGO**.

- ✅ Identifica correctamente problemas de UX (Budget confuso, Promise.all bug)
- ❌ Afirma incorrectamente que características no existen (cuando SÍ existen en el código)
- ⚠️ No distingue entre "no implementado" vs "no visible por bug"

**Recomendación**: Usar este documento de auditoría como fuente de verdad para el plan de reparación.

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Audit Complete ✅
