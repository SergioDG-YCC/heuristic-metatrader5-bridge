# PROMPT: FastTraderService Constructor

## Rol

Actuá como principal backend architect y senior Python engineer para construir
`FastTraderService` en `heuristic-metatrader5-bridge`.

No estás haciendo una mejora menor del `fast_desk`.

Estás cerrando la siguiente gran fase operativa del backend:

- Fast heurístico real
- sin LLM
- con `M1 + M5 + H1`
- con ownership y riesgo ya centralizados
- sobre el conector MT5 ya certificado

## Objetivo exacto

Implementar `FastTraderService` real, profesional y usable en vivo, sin tocar
todavía:

- `SmcTraderService`
- `BridgeSupervisor`
- `paper mode`
- WebUI

## Documentación obligatoria a leer primero

Tratala como fuente de verdad:

1. `docs/plans/2026-03-24_immutable_bridge_action_plan.md`
2. `docs/plans/2026-03-24_ownership_risk_operational_contract.md`
3. `docs/ARCHITECTURE.md`
4. `README.md`
5. `docs/fast_trader/README.md`
6. `docs/fast_trader/audit/2026-03-24_fast_trader_gap_audit.md`
7. `docs/fast_trader/sources/2026-03-24_fast_trader_source_inventory.md`
8. `docs/fast_trader/plans/2026-03-24_fast_trader_constructor_plan.md`
9. `docs/fast_trader/actions/2026-03-24_fast_trader_constructor_actions.md`

También inspeccioná el código real:

- `src/heuristic_mt5_bridge/core/runtime/service.py`
- `src/heuristic_mt5_bridge/core/ownership/registry.py`
- `src/heuristic_mt5_bridge/core/risk/kernel.py`
- `src/heuristic_mt5_bridge/infra/mt5/connector.py`
- `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`
- `src/heuristic_mt5_bridge/fast_desk/`
- `src/heuristic_mt5_bridge/smc_desk/detection/`

Como fuente de comportamiento de la repo vieja, sólo para extraer heurísticas:

- `../llm-metatrader5-bridge/python/live_execution_trader_runtime.py`
- `../llm-metatrader5-bridge/python/execution_bridge.py`
- `../llm-metatrader5-bridge/python/smc_heuristic_scanner.py`
- `../llm-metatrader5-bridge/python/prompts/smc_trader/tools/chartism_patterns.md`
- `../llm-metatrader5-bridge/python/prompts/smc_trader/tools/sltp_methods.md`
- `../llm-metatrader5-bridge/python/prompts/smc_trader/tools/smc_entry_models.md`

## Problema actual

Hoy Fast tiene:

- scanner simple
- policy simple
- custodian simple
- worker por símbolo
- integración con connector
- integración con `OwnershipRegistry`
- integración con `RiskKernel`

Pero no tiene todavía:

- `M1` para trigger
- contexto `H1` integrado al trader
- setups heurísticos robustos
- ordenes pending Fast realmente gestionadas
- gates explícitos de spread/slippage/session
- custody profesional
- separación clara entre contexto, setup, trigger y custody

## Resultado esperado

Fast debe terminar esta fase pudiendo:

- abrir nuevas entradas Fast
- custodiar posiciones Fast
- custodiar posiciones heredadas asignadas a Fast
- gestionar pending orders Fast
- mover SL a break-even
- trailing dinámico
- hard loss cut
- no passive underwater
- operar con criterio `M1 + M5 + H1`

## Principios innegociables

1. Fast no usa LLM.
2. El hot path Fast debe seguir siendo rápido.
3. No importar la office stack vieja.
4. No copiar el runtime viejo completo.
5. Toda entrada Fast consulta `RiskKernel`.
6. Toda operación Fast queda registrada en `OwnershipRegistry`.
7. Fast debe usar sólo la superficie canónica de `MT5Connector`.
8. `M1` confirma; `M5` arma el setup; `H1` contextualiza.

## Arquitectura obligatoria

Construí una arquitectura Fast separada en módulos, aunque reuses piezas
existentes:

```text
FastTraderService
  -> FastContextService
  -> FastSetupEngine
  -> FastTriggerEngine
  -> FastCustodyEngine
  -> FastExecutionBridge
```

### Responsabilidad de cada capa

#### FastContextService

Debe calcular:

- sesgo `H1`
- estado de sesión
- spread aceptable
- slippage permitido
- stale feed
- régimen de volatilidad
- no-trade regime

#### FastSetupEngine

Debe detectar setups en `M5`.

Setups mínimos obligatorios de primera ola:

- `order_block_retest`
- `liquidity_sweep_reclaim`
- `breakout_retest`

Chart patterns:

- agregar sólo patrones robustos y útiles para scalping/intraday
- no construir una enciclopedia enorme

Patrones candidatos:

- wedge
- flag
- triangle
- support/resistance polarity retest

#### FastTriggerEngine

Debe confirmar entradas en `M1`.

Triggers candidatos:

- micro BOS
- micro CHoCH
- rejection candle
- reclaim
- displacement candle

Regla:

- ningún setup `M5` abre solo sin trigger `M1`

#### FastCustodyEngine

Debe manejar:

- break-even
- ATR trailing
- structural trailing
- hard loss cut
- no passive underwater
- cancelación defensiva de pending
- gestión de heredadas Fast

## Timeframes obligatorios

El constructor debe dejar Fast funcionando sobre:

- `M1`
- `M5`
- `H1`

Si el runtime actual no está preparado, debés extenderlo de forma limpia para
que `M1` pueda ser observado por Fast sin degradar la arquitectura.

## Fuentes heurísticas obligatorias

### Order Blocks / structure / liquidity

Primero verificar si los detectores ya migrados en:

- `src/heuristic_mt5_bridge/smc_desk/detection/`

alcanzan para Fast.

Si sí:

- reutilizarlos o extraer wrappers livianos

Si no:

- reconstruir lo mínimo necesario desde `smc_heuristic_scanner.py`

### Chart patterns

Traducir a heurísticas deterministas desde:

- `chartism_patterns.md`

### SL/TP / trailing

Traducir a calculadores y políticas desde:

- `sltp_methods.md`

### Entry models

Usar como referencia conceptual:

- `smc_entry_models.md`

Pero simplificados a Fast:

- no D1/H4 lento
- sí M5 setup + M1 trigger + H1 context

## Integración obligatoria con backend existente

### Runtime

Integrar con:

- `CoreRuntimeService`
- `MarketStateService`
- `OwnershipRegistry`
- `RiskKernel`

### Connector

Usar solamente:

- `send_execution_instruction`
- `modify_position_levels`
- `modify_order_levels`
- `remove_order`
- `close_position`
- `find_open_position_id`

No usar llamadas MT5 raw dispersas fuera del conector.

### Ownership

Toda operación Fast nueva debe quedar como:

- `fast_owned`

Toda heredada asignada a Fast debe poder ser custodiada por Fast.

### Risk

Toda entrada Fast debe pasar por:

- evaluación central de `RiskKernel`

No dejar bypass locales ocultos.

## Gating obligatorio

El `FastTraderService` debe introducir gates explícitos de:

- sesión
- spread
- slippage
- feed freshness
- risk central

Si el gate falla:

- no abrir nueva entrada
- dejar razón legible y persistible cuando corresponda

## Pending orders Fast

Esta fase debe dejar Fast capaz de:

- emitir pending orders cuando el setup lo requiera
- cancelar pending defensivamente
- modificar niveles cuando el contexto cambie

No alcanza con market-only.

## Custodia mínima obligatoria

Fast debe poder:

- mover SL a BE
- trailing ATR
- trailing estructural
- hard cut si invalida estructura o si el deterioro excede límites
- no dejar posiciones perdedoras en pasividad

## Variables de entorno esperadas

Agregar o redefinir las necesarias en:

- `configs/base.env.example`

Como mínimo:

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
- cualquier otra estrictamente necesaria

## Archivos esperables

Es razonable que toques, entre otros:

- `src/heuristic_mt5_bridge/core/runtime/service.py`
- `src/heuristic_mt5_bridge/fast_desk/runtime.py`
- `src/heuristic_mt5_bridge/fast_desk/workers/symbol_worker.py`
- `src/heuristic_mt5_bridge/fast_desk/signals/scanner.py`
- `src/heuristic_mt5_bridge/fast_desk/custody/custodian.py`
- `src/heuristic_mt5_bridge/fast_desk/policies/entry.py`
- módulos nuevos dentro de `fast_desk/` si hacen falta
- `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`
- tests correspondientes

Podés crear nuevos módulos como:

- `fast_desk/context/`
- `fast_desk/setup/`
- `fast_desk/trigger/`

si eso mantiene el diseño claro.

## Tests obligatorios

Agregar tests unitarios e integración mínima para:

- disponibilidad `M1`
- setup detection
- trigger confirmation
- spread/slippage/session gates
- uso de `RiskKernel`
- registro ownership Fast
- custody BE / trailing / hard cut
- pending order lifecycle Fast

Y luego correr:

- `pytest -q`

Además, si no rompe el entorno vivo:

- rerun de la certificación del connector para comprobar que Fast no degradó la superficie MT5

## Documentación obligatoria a actualizar

Actualizar si hace falta:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/fast_trader/` con lo realmente construido

Si descubrís gaps o decisiones importantes:

- documentarlas en `docs/fast_trader/results/` o `docs/fast_trader/audit/`

## Fuera de alcance

No hacer todavía:

- `SmcTraderService`
- `BridgeSupervisor`
- `paper mode`
- rediseño total de ownership
- rediseño total de risk
- WebUI

## Criterios de aceptación

El trabajo se considera correcto sólo si:

1. Fast opera con `M1 + M5 + H1`.
2. Fast tiene al menos 3 setups heurísticos explícitos.
3. Fast tiene trigger `M1`.
4. Fast tiene gates de session, spread y slippage.
5. Fast usa `RiskKernel` como autoridad real.
6. Fast registra ownership en toda nueva ejecución.
7. Fast puede custodiar heredadas Fast.
8. Fast puede abrir, custodiar y cerrar.
9. Fast puede gestionar pending orders Fast.
10. La suite existente sigue verde.
11. No se rompe la certificación del connector.

## Cierre obligatorio

Al finalizar, entregá:

1. resumen técnico
2. archivos modificados
3. nuevas variables de entorno
4. nuevos tests
5. qué heurísticas se tomaron de fuentes viejas
6. qué gaps quedaron para `SmcTraderService` o fases posteriores

## Regla final

No improvises un "Fast bonito".

Construí un `FastTraderService` serio, rápido y coherente con el backend ya
existente.
