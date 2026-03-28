# Fast Trader Constructor Plan

Fecha: 2026-03-24

## Proposito

Definir el alcance exacto de la construcción de `FastTraderService`.

Este documento debe leerse antes del prompt constructor y funciona como mapa de
implementación y aceptación.

## Objetivo

Convertir la mesa Fast en una mesa realmente operativa, heurística, de baja
latencia y profesional, usando:

- `M1` para trigger
- `M5` para setup
- `H1` para contexto

Sin LLM y sin reintroducir runtimes lentos de la repo vieja.

## Resultado esperado

Al final de esta fase, Fast debe poder:

- detectar setups heurísticos de alta calidad
- abrir entradas rápidas
- custodiar posiciones propias y heredadas Fast
- trabajar con pending orders Fast
- usar `OwnershipRegistry`
- usar `RiskKernel`
- dejar audit trail en DB

## Arquitectura objetivo del servicio

```text
FastTraderService
  -> FastContextService
  -> FastSetupEngine
  -> FastTriggerEngine
  -> FastCustodyEngine
  -> FastExecutionBridge
  -> OwnershipRegistry
  -> RiskKernel
```

## Fases internas recomendadas

### Fase A - Habilitación de datos y timeframes

Objetivo:

- incorporar `M1` al runtime operativo Fast

Entregables:

- watch timeframes compatibles con `M1,M5,H1`
- lectura RAM estable de `M1`
- tests de disponibilidad de candles

Aceptación:

- Fast puede leer `M1`, `M5` y `H1` sin hacks locales

### Fase B - Context service

Objetivo:

- separar el contexto de mercado del setup de entrada

Debe resolver:

- sesgo `H1`
- régimen de volatilidad
- estado de sesión
- spread aceptable
- slippage permitido
- stale feed
- zonas rápidas relevantes para Fast

Aceptación:

- el contexto se calcula una vez por ciclo y se reusa

### Fase C - Setup engine

Objetivo:

- detectar setups rápidos sobre `M5`

Setups obligatorios de primera ola:

- order block retest
- liquidity sweep + reclaim
- breakout + retest

Setups opcionales de primera ola si ya encajan bien:

- wedge / flag / triangle
- support/resistance polarity retest

Aceptación:

- cada setup devuelve estructura tipada
- no hay señales ambiguas no explicadas

### Fase D - Trigger engine

Objetivo:

- confirmar entradas en `M1`

Triggers candidatos:

- micro BOS
- micro CHoCH
- rejection candle
- reclaim
- displacement candle

Aceptación:

- un setup `M5` no dispara por sí solo sin trigger `M1`

### Fase E - Entry and execution

Objetivo:

- traducir setup + trigger + contexto a una acción real

Debe resolver:

- market / pending order selection
- cálculo de volumen
- SL por estructura
- TP por estructura y R:R
- spread gate
- slippage gate
- session gate
- consulta previa al `RiskKernel`
- registro en `OwnershipRegistry`

Aceptación:

- toda entrada Fast queda auditada
- toda entrada pasa por risk central

### Fase F - Custody profesional

Objetivo:

- custodiar posiciones Fast y heredadas Fast

Capacidades mínimas:

- move to BE
- trailing ATR
- trailing estructural
- hard loss cut
- no passive underwater
- cancelación defensiva de pending
- gestión sobre heredadas Fast

Aceptación:

- la custodia no depende de decisiones LLM
- usa solo reglas explícitas y repetibles

### Fase G - Reconciliación y validación

Objetivo:

- cerrar el servicio con evidencia verificable

Debe cubrir:

- coherencia con ownership
- coherencia con risk
- compatibilidad con el connector certificado
- pruebas unitarias
- pruebas de integración

Aceptación:

- suite verde
- no rompe el conector live
- no degrada runtime actual

## Reglas de diseño

1. Fast no usa LLM.
2. El hot path Fast no puede depender del scanner SMC completo.
3. Toda entrada Fast debe pasar por `RiskKernel`.
4. Toda operación Fast debe quedar con owner.
5. `M1` no reemplaza `M5`; lo confirma.
6. `H1` no dispara; contextualiza.
7. La custodia Fast debe ser más seria que el `live_execution_trader` viejo.

## Contratos operativos mínimos

### Datos requeridos por Fast

- candles `M1`
- candles `M5`
- candles `H1`
- spec por símbolo
- account payload
- ownership open set
- risk status

### Persistencia requerida

Como mínimo:

- `fast_desk_signals`
- `fast_desk_trade_log`
- ownership ya existente
- risk events ya existentes

Si hace falta agregar tablas nuevas Fast:

- deben ser broker/account partitioned
- sólo si resuelven un contrato real

## Variables de entorno esperables

Además de las ya existentes, esta fase debería introducir o redefinir:

- `MT5_WATCH_TIMEFRAMES=M1,M5,H1`
- `FAST_TRADER_ENABLED`
- `FAST_TRADER_SCAN_INTERVAL`
- `FAST_TRADER_GUARD_INTERVAL`
- `FAST_TRADER_SIGNAL_COOLDOWN`
- `FAST_TRADER_SPREAD_MAX_PIPS`
- `FAST_TRADER_MAX_SLIPPAGE_POINTS`
- `FAST_TRADER_REQUIRE_H1_ALIGNMENT`
- `FAST_TRADER_ENABLE_PENDING_ORDERS`
- `FAST_TRADER_ENABLE_STRUCTURAL_TRAILING`
- `FAST_TRADER_ENABLE_ATR_TRAILING`

## Fuera de alcance

No hacer en esta fase:

- `SmcTraderService`
- `BridgeSupervisor`
- `paper mode`
- rediseño del `RiskKernel`
- rediseño total del `OwnershipRegistry`

## Criterios de aceptación finales

1. Fast usa `M1 + M5 + H1`.
2. Fast tiene al menos 3 setups heurísticos reales.
3. Fast tiene gates explícitos de spread, slippage y sesión.
4. Fast puede abrir, custodiar y cerrar.
5. Fast puede custodiar heredadas asignadas a Fast.
6. Toda entrada usa `RiskKernel`.
7. Toda ejecución queda registrada con ownership.
8. El servicio no depende de LLM.
9. La suite nueva y la suite existente pasan.
10. La certificación del conector no se rompe.
