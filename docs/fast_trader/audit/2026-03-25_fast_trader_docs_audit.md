# Fast Trader — Auditoría de Documentación

Fecha: 2026-03-25  
Auditor: GitHub Copilot (análisis de lectura documental, sin tocar código)  
Alcance: README.md, docs/ARCHITECTURE.md, docs/fast_trader/\*\*

---

## Resumen ejecutivo

La documentación describe un `FastTraderService` completamente diseñado y
maduro. Sin embargo, hay inconsistencias entre los distintos documentos y entre
la documentación y el estado real conocido del código. Este documento fija esas
discrepancias para contrasto posterior con el código real.

---

## Lo que la documentación dice que existe

### Marco de 3 timeframes

| TF | Rol declarado |
|----|---------------|
| H1 | Contexto direccional y gates de mercado |
| M5 | Setup heurístico |
| M1 | Trigger microestructural — sin M1 no abre |

### Pipeline declarado

```
FastContextService
  → FastSetupEngine
    → FastTriggerEngine
      → (RiskKernel gate)
        → FastExecutionBridge
          → OwnershipRegistry
            → MT5Connector
FastCustodyEngine (ciclo independiente, 2s)
FastPendingManager
```

### Setups heurísticos declarados (FastSetupEngine sobre M5)

1. `order_block_retest`
2. `liquidity_sweep_reclaim`
3. `breakout_retest`

Chart patterns declarados como opcionales:
- `wedge`, `flag`, `triangle`
- `support/resistance polarity retest`

### Triggers M1 declarados (FastTriggerEngine)

- `micro_bos`
- `micro_choch`
- `rejection_candle`
- `reclaim`
- `displacement`

### Regla cardinal declarada

> No M5 setup puede ejecutar sin un valid M1 trigger.

### Gates declarados (FastContextService)

- sesión operativa (Londres, NY, Asia)
- spread ≤ umbral
- slippage ≤ umbral
- stale feed / calidad del chart
- régimen de volatilidad
- no-trade regime

### Routing de tipo de orden declarado

| Situación | Orden |
|-----------|-------|
| Retest de zona / estructura | pending (limit) |
| Reclaim / displacement | market |

### Custody declarada (FastCustodyEngine)

1. break-even
2. ATR trailing
3. structural trailing
4. hard loss cut
5. no passive underwater
6. cancelación defensiva de pending
7. gestión de heredadas Fast (`inherited_fast`)

### Integración declarada

- `RiskKernel.evaluate_entry_for_desk()` — obligatorio antes de abrir
- `OwnershipRegistry` — toda nueva entrada como `fast_owned`
- `MT5Connector` — superficie canónica únicamente (6 métodos)
- SQLite `runtime.db` — audit trail
- Sin MT5 raw fuera del conector
- Sin LLM en ningún punto del hot path

---

## Inconsistencias detectadas entre documentos

### 1. README vs ARCHITECTURE — nombres de componentes no coinciden

**README** usa:
- `FastScannerService`
- `FastRiskEngine`
- `FastEntryPolicy`
- `FastCustodian`
- `FastSymbolWorker`

**ARCHITECTURE** usa:
- `FastContextService`
- `FastSetupEngine`
- `FastTriggerEngine`
- `FastCustodyEngine`
- `FastExecutionBridge`

Son dos nomenclaturas parcialmente distintas para describir el mismo sistema.
El README refleja el estado *antes* del rediseño; ARCHITECTURE refleja el
objetivo. **El README no fue actualizado tras definir `FastTraderService`.**

### 2. Estado de implementación declarado en ARCHITECTURE contradice el gap audit

- `ARCHITECTURE.md` declara en su cabecera:
  > `FastTraderService v1 (Immediate Phase)` — como si estuviera implementado.
  
- `2026-03-24_fast_trader_gap_audit.md` dice explícitamente:
  > M1 no está, setups heurísticos no existen como tal, custody es básica,
  > no hay separación formal contexto/setup/trigger/custody.

**Conclusión**: ARCHITECTURE.md describe el objetivo, no el estado real.
El encabezado de status es engañoso.

### 3. docs/fast_trader/README.md lista documentos que pueden no reflejar código real

Cita como "documentos activos" varios archivos de plan y prompt, pero ninguno
es evidencia de implementación. Son artefactos de diseño, no de validación.

### 4. FAST_TRADER_BACKEND_HANDOFF lista criterios de cierre de fase como meta futura

Los 10 criterios de cierre listados en
`FAST_TRADER_BACKEND_HANDOFF.md` son todos criterios *pendientes*, no
verificados. Esto es consistente con el gap audit, pero contradice el tono de
ARCHITECTURE.md que sugiere avance mayor.

### 5. El gap audit es el documento más honesto

`2026-03-24_fast_trader_gap_audit.md` es el único documento que describe el
estado real del código sin ambigüedad. Es la referencia correcta para contrastar
con el código real.

---

## Gaps documentales (independientemente del código)

1. No existe un documento de estado post-implementación de `FastTraderService`.
2. No existe un documento de validación / test coverage Fast.
3. `README.md` raíz no fue actualizado tras el rediseño de la arquitectura Fast.
4. `ARCHITECTURE.md` mezcla "objetivo" con "estado" sin distinguirlos claramente.
5. No hay un contrato operativo explícito de `FastPendingManager` (solo mencionado).
6. No hay especificación de los umbrales concretos de spread/slippage (se los
   menciona pero no se los define en ningún documento).
7. No hay documentación de los criterios exactos de detección de cada setup
   (qué condiciones numéricas definen un `order_block_retest`, etc.).

---

## Próximo paso recomendado

Leer el código real de `src/heuristic_mt5_bridge/fast_desk/` y contrastar
cada componente declarado en la documentación contra lo que está realmente
implementado.

Directorios a inspeccionar:
- `fast_desk/context/`
- `fast_desk/setup/`
- `fast_desk/trigger/`
- `fast_desk/custody/`
- `fast_desk/execution/`
- `fast_desk/pending/`
- `fast_desk/trader/`
- `fast_desk/workers/`
- `fast_desk/risk/`
- `fast_desk/policies/`
- `fast_desk/signals/`
- `fast_desk/runtime.py`
