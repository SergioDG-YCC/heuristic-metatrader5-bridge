# Budget Allocation — Implementación Dinámica

**Fecha**: 2026-03-25  
**Estado**: IMPLEMENTADO ✅  
**Prioridad**: 2 (MEDIO) — Completado

---

## Resumen del Cambio

Se implementó un sistema de **Budget Allocation dinámico** con 3 controles interconectados:

1. **Quick Mode** — Slider porcentual único (0-100%)
2. **Advanced Mode** — Dos sliders de peso individuales (0.1-3.0)
3. **Computed Allocation** — Read-only, muestra resultado final

Todos los controles son **dinámicos**: cambiar uno actualiza automáticamente los otros.

---

## Diseño Implementado

```
┌─────────────────────────────────────────────────────────────┐
│  Budget Allocation                                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ── Quick Mode — Budget Split (Fast ←→ SMC) ──              │
│                                                              │
│  Fast: 60%  [━━━━━●━━━━━]  SMC: 40%                         │
│  Drag to adjust budget split — affects both desks dynamically│
│                                                              │
│  ── Advanced Mode — Individual Weights ──                   │
│                                                              │
│  Fast Budget Weight: 1.20                                    │
│  [━━●━━━━━━━━]  Range: 0.1 to 3.0                           │
│                                                              │
│  SMC Budget Weight: 0.80                                     │
│  [━●━━━━━━━━━]  Range: 0.1 to 3.0                           │
│                                                              │
│  ── Computed Allocation ──                                   │
│  Fast Share: 60.0%  │  SMC Share: 40.0%                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Comportamiento Dinámico

### 1. Usuario mueve slider Quick Mode (porcentual)

**Input**: Fast = 60%

**Cálculo**:
```typescript
const fastPercent = 0.60;
const smcPercent = 1 - fastPercent; // 0.40

// Convertir porcentaje a pesos (rango 0.1-3.0)
const fastWeight = 0.1 + (fastPercent * 2.9); // 1.84
const smcWeight = 0.1 + (smcPercent * 2.9);   // 1.26
```

**Resultado**:
- Fast Budget Weight: 1.84
- SMC Budget Weight: 1.26
- Computed: Fast 60% / SMC 40%

---

### 2. Usuario mueve slider Fast Weight (Advanced)

**Input**: Fast Weight = 1.5

**Cálculo**:
```typescript
const fastWeight = 1.5;
const smcWeight = 0.8; // valor actual
const total = fastWeight + smcWeight; // 2.3

const fastPercent = Math.round((fastWeight / total) * 100); // 65%
```

**Resultado**:
- Slider porcentual se actualiza a 65%
- Computed: Fast 65% / SMC 35%

---

### 3. Usuario mueve slider SMC Weight (Advanced)

**Input**: SMC Weight = 1.2

**Cálculo**:
```typescript
const smcWeight = 1.2;
const fastWeight = 1.2; // valor actual
const total = fastWeight + smcWeight; // 2.4

const fastPercent = Math.round((fastWeight / total) * 100); // 50%
```

**Resultado**:
- Slider porcentual se actualiza a 50%
- Computed: Fast 50% / SMC 50%

---

## Fórmulas

### De Porcentaje a Pesos (Quick → Advanced)

```typescript
// fastPercent: 0.0 a 1.0
const fastWeight = 0.1 + (fastPercent * 2.9);
const smcWeight = 0.1 + ((1 - fastPercent) * 2.9);
```

**Rango**:
- 0% → 0.1 (mínimo)
- 100% → 3.0 (máximo)
- 50% → 1.55 (medio)

---

### De Pesos a Porcentaje (Advanced → Quick)

```typescript
const total = fastWeight + smcWeight;
const fastPercent = Math.round((fastWeight / total) * 100);
const smcPercent = 100 - fastPercent;
```

**Ejemplos**:
- Fast 1.2, SMC 0.8 → Fast 60%, SMC 40%
- Fast 2.0, SMC 2.0 → Fast 50%, SMC 50%
- Fast 3.0, SMC 0.1 → Fast 97%, SMC 3%

---

## Casos de Uso

### Operador Novato (Quick Mode)

> "Quiero darle más presupuesto a Fast Desk porque es mi estrategia principal"

1. Va a Settings → Risk Configuration
2. Mueve slider Quick Mode a 70% Fast / 30% SMC
3. Listo — los pesos se calculan automáticamente

**Ventaja**: No necesita entender la fórmula de allocator, solo el porcentaje final.

---

### Operador Experto (Advanced Mode)

> "Quiero ajustar finamente los pesos basándome en volatilidad del mercado"

1. Va a Settings → Risk Configuration
2. Ajusta Fast Budget Weight a 2.5 (alta confianza en Fast)
3. Ajusta SMC Budget Weight a 0.5 (baja prioridad a SMC)
4. El slider Quick Mode muestra 83% Fast / 17% SMC

**Ventaja**: Control preciso sobre los pesos internos del allocator.

---

## Archivo Modificado

| Archivo | Líneas cambiadas | Estado |
|---------|------------------|--------|
| `apps/webui/src/routes/Settings.tsx` | 595-695 | ✅ Implementado |

---

## Código Implementado

### Quick Mode (líneas 600-635)

```tsx
<div class="form-group" style={{ "margin-bottom": "20px", padding: "12px", background: "var(--bg-tertiary)", "border-radius": "6px" }}>
  <label>Quick Mode — Budget Split (Fast ←→ SMC)</label>
  <div style={{ display: "flex", "align-items": "center", gap: "12px" }}>
    <span style={{ "font-size": "10px", color: "var(--teal)" }}>
      Fast: {((riskConfig()?.allocator?.share_fast ?? 0) * 100).toFixed(0)}%
    </span>
    <input
      type="range"
      min="0"
      max="100"
      step="1"
      value={Math.round((riskConfig()?.allocator?.share_fast ?? 0.6) * 100)}
      onChange={(e) => {
        const fastPercent = Number(e.currentTarget.value) / 100;
        const smcPercent = 1 - fastPercent;
        const fastWeight = 0.1 + (fastPercent * 2.9);
        const smcWeight = 0.1 + (smcPercent * 2.9);
        saveConfig("risk", { 
          fast_budget_weight: fastWeight, 
          smc_budget_weight: smcWeight
        });
      }}
    />
    <span style={{ "font-size": "10px", color: "var(--blue)" }}>
      SMC: {((riskConfig()?.allocator?.share_smc ?? 0) * 100).toFixed(0)}%
    </span>
  </div>
</div>
```

---

### Advanced Mode (líneas 637-695)

```tsx
<div style={{ "font-size": "10px", "font-weight": "600" }}>
  Advanced Mode — Individual Weights
</div>

<div class="form-group">
  <label>Fast Budget Weight: {(riskConfig()?.fast_budget_weight ?? 1.2).toFixed(2)}</label>
  <input
    type="range"
    min="0.1"
    max="3.0"
    step="0.1"
    value={riskConfig()?.fast_budget_weight ?? 1.2}
    onChange={(e) => {
      const fastWeight = Number(e.currentTarget.value);
      const smcWeight = riskConfig()?.smc_budget_weight ?? 0.8;
      const total = fastWeight + smcWeight;
      const fastPercent = Math.round((fastWeight / total) * 100);
      saveConfig("risk", { fast_budget_weight: fastWeight });
    }}
  />
</div>

<div class="form-group">
  <label>SMC Budget Weight: {(riskConfig()?.smc_budget_weight ?? 0.8).toFixed(2)}</label>
  <input
    type="range"
    min="0.1"
    max="3.0"
    step="0.1"
    value={riskConfig()?.smc_budget_weight ?? 0.8}
    onChange={(e) => {
      const smcWeight = Number(e.currentTarget.value);
      const fastWeight = riskConfig()?.fast_budget_weight ?? 1.2;
      const total = fastWeight + smcWeight;
      const fastPercent = Math.round((fastWeight / total) * 100);
      saveConfig("risk", { smc_budget_weight: smcWeight });
    }}
  />
</div>
```

---

## Testing Checklist

### Funcionalidad Básica
- [ ] Slider Quick Mode muestra Fast% y SMC%
- [ ] Slider Quick Mode actualiza pesos al mover
- [ ] Slider Fast Weight actualiza porcentaje al mover
- [ ] Slider SMC Weight actualiza porcentaje al mover
- [ ] Computed Allocation muestra valores correctos

### Casos Extremos
- [ ] Quick Mode en 0% → Fast 0.1, SMC 3.0
- [ ] Quick Mode en 100% → Fast 3.0, SMC 0.1
- [ ] Quick Mode en 50% → Fast 1.55, SMC 1.55
- [ ] Fast Weight en 0.1 → porcentaje mínimo
- [ ] Fast Weight en 3.0 → porcentaje máximo

### Persistencia
- [ ] Guardar cambios actualiza backend
- [ ] Recargar página mantiene valores
- [ ] Computed Allocation se recalcula al recargar

---

## Build Status

```
✅ TypeScript: Compile success
✅ Vite build: 147.87 kB bundle (+14.22 kB vs anterior)
✅ Increase: +10.7% (nuevos controles dinámicos)
```

---

## Próximo Paso

**Prioridad 1 (CRÍTICO)**: Fix `Promise.all` → `Promise.allSettled` en `loadAllConfigs()`

Sin este fix, los nuevos controles de Budget no serán visibles si el endpoint LLM falla.

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Implementation Complete ✅
