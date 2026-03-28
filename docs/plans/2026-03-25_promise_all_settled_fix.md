# Bug #0: Promise.all → Promise.allSettled Fix

**Fecha**: 2026-03-25  
**Estado**: IMPLEMENTADO ✅  
**Prioridad**: 1 (CRÍTICO) — Completado

---

## Problema Original

### Código Problemático

```typescript
// Settings.tsx (ANTES)
async function loadAllConfigs() {
  try {
    const [llm, smc, fast, ownership, risk] = await Promise.all([
      api.getLlmModels(),    // ← Si esto falla con 500...
      api.getLlmStatus(),
      api.getSmcConfig(),
      api.getFastConfig(),
      api.getOwnershipConfig(),
      api.getRiskConfig(),
    ]);

    // ← NUNCA SE EJECUTA SI ALGUNA PROMESA FALLA
    if (llm.status === "success") setLlmModels(llm.models || []);
    if (smc.status === "success") setSmcConfig(smc.config);
    // ...
  } catch (e) {
    setError("Failed to load configs");  // ← ERROR GENÉRICO
    console.error(e);
  }
}
```

### Síntoma

**Si UN endpoint falla (ej: `/api/v1/llm/models` retorna 500)**:
- ❌ TODOS los configs fallan
- ❌ Paneles muestran "Loading…" permanentemente
- ❌ Usuario no puede ver/editar NADA

### Causa Raíz

`Promise.all` tiene comportamiento **"fail-fast"**:
- Si CUALQUIERA de las promesas rechaza, TODAS se rechazan
- El `catch` se ejecuta pero ningún config se setea
- Los `<Show when={config()}>` caen al fallback "Loading…"

---

## Solución Implementada

### Código Corregido

```typescript
// Settings.tsx (DESPUÉS)
async function loadAllConfigs() {
  setError(null);
  setSuccess(null);
  
  // Use Promise.allSettled to load all configs independently
  // If one endpoint fails (e.g., LLM 500), others still load
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

  // Load each config independently
  if (llmModelsRes?.status === "success" && "models" in llmModelsRes) {
    setLlmModels(llmModelsRes.models || []);
  }
  if (llmStatusRes) {
    setLlmStatus(llmStatusRes);
  }
  if (smc?.status === "success" && "config" in smc) {
    setSmcConfig((smc as any).config);
  }
  if (fast?.status === "success" && "config" in fast) {
    setFastConfig((fast as any).config);
  }
  if (ownership?.status === "success" && "config" in ownership) {
    setOwnershipConfig((ownership as any).config);
  }
  if (risk?.status === "success" && "config" in risk) {
    setRiskConfig((risk as any).config);
  }

  // Report errors for failed loads
  const failedIndexes = results
    .map((r, i) => r.status === "rejected" ? i : -1)
    .filter(i => i !== -1);
  
  if (failedIndexes.length > 0) {
    const failedNames = failedIndexes.map(i => {
      const names = ["LLM Models", "LLM Status", "SMC Config", "Fast Config", "Ownership Config", "Risk Config"];
      return names[i];
    }).join(", ");
    setError(`Failed to load ${failedIndexes.length} config(s): ${failedNames}. Retrying...`);
    console.error("Failed to load configs:", failedIndexes.map(i => results[i]));
    
    // Auto-retry after 3 seconds
    setTimeout(() => {
      console.log("Auto-retrying config load...");
      loadAllConfigs();
    }, 3000);
  }
}
```

---

## Mejoras Clave

### 1. Carga Independiente

**Antes**: Todos o ninguno  
**Ahora**: Cada config carga independientemente

| Escenario | Antes | Ahora |
|-----------|-------|-------|
| LLM falla (500) | ❌ Nada carga | ✅ SMC/Fast/Risk cargan |
| Fast falla | ❌ Nada carga | ✅ LLM/SMC/Risk cargan |
| Todos OK | ✅ Todo carga | ✅ Todo carga |

---

### 2. Error Messages Específicos

**Antes**:
```
❌ Failed to load configs
```

**Ahora**:
```
❌ Failed to load 2 config(s): LLM Models, Fast Config. Retrying...
```

**Beneficio**: Usuario sabe exactamente qué falló y que el sistema está reintentando.

---

### 3. Auto-Retry

**Antes**: Usuario tenía que recargar página manualmente  
**Ahora**: Reintento automático cada 3 segundos

**Flujo**:
1. Config falla → Error message muestra cuál
2. Espera 3 segundos
3. Reintenta cargar TODOS los configs
4. Si falla de nuevo → repite

---

### 4. Type Guards

**Antes**:
```typescript
if (llmModelsRes.status === "success") {
  setLlmModels(llmModelsRes.models || []);  // ← TS error: 'models' may not exist
}
```

**Ahora**:
```typescript
if (llmModelsRes?.status === "success" && "models" in llmModelsRes) {
  setLlmModels(llmModelsRes.models || []);  // ✅ Type-safe
}
```

**Beneficio**: TypeScript verifica que el campo existe antes de acceder.

---

## Comparación Promise.all vs Promise.allSettled

### Promise.all (Fail-Fast)

```typescript
const results = await Promise.all([p1, p2, p3]);
// Si p2 falla → results nunca se resuelve, catch se ejecuta
```

**Estado de las promesas**:
- p1: ✅ fulfilled (pero resultado se pierde)
- p2: ❌ rejected (causa el fallo)
- p3: ⏳ pending (nunca se resuelve)

---

### Promise.allSettled (Todos Resuelven)

```typescript
const results = await Promise.allSettled([p1, p2, p3]);
// Todos resuelven, cada resultado tiene {status, value/reason}
```

**Estado de las promesas**:
- p1: ✅ `{status: "fulfilled", value: ...}`
- p2: ❌ `{status: "rejected", reason: ...}`
- p3: ✅ `{status: "fulfilled", value: ...}`

---

## Testing Checklist

### Escenario 1: Todos los endpoints OK
- [ ] Los 6 configs cargan
- [ ] No hay error messages
- [ ] Todos los paneles muestran datos

### Escenario 2: LLM falla (500)
- [ ] Error message: "Failed to load 1 config(s): LLM Models. Retrying..."
- [ ] SMC/Fast/Ownership/Risk configs cargan
- [ ] Paneles de SMC/Fast/Ownership/Risk son visibles
- [ ] Panel LLM muestra fallback o está oculto
- [ ] Después de 3s, reintenta automáticamente

### Escenario 3: Múltiples endpoints fallan
- [ ] Error message lista todos los fallidos
- [ ]Configs exitosos cargan igual
- [ ] Auto-retry funciona

### Escenario 4: Recuperación después de fallo
- [ ] Endpoint que fallaba ahora funciona
- [ ] Auto-retry carga exitosamente
- [ ] Error message desaparece
- [ ] Success message opcionalmente aparece

---

## Impacto en UX

### Antes del Fix

```
Usuario entra a Settings
  → LLM endpoint falla (500)
  → Promise.all rechaza
  → catch se ejecuta
  → setError("Failed to load configs")
  → NINGÚN config se setea
  → Todos los paneles muestran "Loading…"
  → Usuario no puede hacer NADA
  → Tiene que recargar página manualmente
```

---

### Después del Fix

```
Usuario entra a Settings
  → LLM endpoint falla (500)
  → Promise.allSettled resuelve todos
  → LLM: {status: "rejected", reason: "500"}
  → SMC: {status: "fulfilled", value: {...}}
  → Fast: {status: "fulfilled", value: {...}}
  → ...
  → setError("Failed to load 1 config(s): LLM Models. Retrying...")
  → SMC/Fast/Ownership/Risk configs se setean
  → Paneles de SMC/Fast/Ownership/Risk se renderizan
  → Panel LLM muestra fallback
  → Usuario puede editar 5 de 6 configs
  → Auto-retry en 3s...
  → LLM ahora funciona
  → Config carga exitosamente
  → Error desaparece
```

---

## Archivo Modificado

| Archivo | Líneas cambiadas | Estado |
|---------|------------------|--------|
| `apps/webui/src/routes/Settings.tsx` | 17-77 | ✅ Implementado |

---

## Build Status

```
✅ TypeScript: Compile success
✅ Vite build: 148.37 kB bundle (+0.50 kB vs anterior)
✅ Increase: +0.34% (lógica de auto-retry + type guards)
```

---

## Próximos Pasos

**Prioridad 3 (ALTO)**: Session Hours from Symbol Spec

Actualmente `session_name_from_timestamp()` usa UTC fijo. Debe leer `symbol_spec.trade_mode` para saber si el símbolo está operable.

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Implementation Complete ✅
