# FastTrader Backend Handoff

Fecha: 2026-03-24

## Estado previo obligatorio

Estas fases ya quedaron resueltas y no deben reabrirse dentro del constructor
de Fast:

- connector MT5 cerrado y certificado
- `OwnershipRegistry` implementado
- `RiskKernel` implementado

Fuente canonica:

- [`docs/plans/2026-03-24_immutable_bridge_action_plan.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/plans/2026-03-24_immutable_bridge_action_plan.md)

## Que sigue ahora

La siguiente fase operativa del backend es:

- `FastTraderService`

Todavia no corresponde construir:

- `SmcTraderService`
- `BridgeSupervisor`
- `paper mode`
- WebUI

## Objetivo resumido

Convertir `fast_desk` en una mesa Fast realmente operativa, heuristica y de
alta velocidad, con:

- `M1` para trigger
- `M5` para setup
- `H1` para contexto
- gates de session, spread y slippage
- custody profesional
- integracion total con `OwnershipRegistry`
- integracion total con `RiskKernel`

## Orden de lectura obligatorio

1. [`audit/2026-03-24_fast_trader_gap_audit.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/audit/2026-03-24_fast_trader_gap_audit.md)
2. [`sources/2026-03-24_fast_trader_source_inventory.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/sources/2026-03-24_fast_trader_source_inventory.md)
3. [`plans/2026-03-24_fast_trader_constructor_plan.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/plans/2026-03-24_fast_trader_constructor_plan.md)
4. [`actions/2026-03-24_fast_trader_constructor_actions.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/actions/2026-03-24_fast_trader_constructor_actions.md)
5. [`prompts/2026-03-24_FAST_TRADER_SERVICE_CONSTRUCTOR.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/prompts/2026-03-24_FAST_TRADER_SERVICE_CONSTRUCTOR.md)

## Reglas que no se discuten

- Fast no usa LLM
- no copiar el runtime viejo completo
- no meter heuristicas SMC lentas en el hot path Fast
- no abrir por `M5` sin confirmacion `M1`
- no bypassear `RiskKernel`
- no dejar ejecuciones Fast sin ownership
- no usar MT5 raw fuera del conector canonico

## Fuente vieja autorizada

La repo vieja se usa solo como fuente de comportamiento:

- [CHANGELOG.md](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/CHANGELOG.md)
- [live_execution_trader_runtime.py](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/live_execution_trader_runtime.py)
- [smc_heuristic_scanner.py](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/smc_heuristic_scanner.py)
- [chartism_patterns.md](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/prompts/smc_trader/tools/chartism_patterns.md)
- [sltp_methods.md](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/prompts/smc_trader/tools/sltp_methods.md)
- [smc_entry_models.md](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/prompts/smc_trader/tools/smc_entry_models.md)

No es runtime importable.

## Criterio de cierre

La fase se considera bien cerrada si Fast:

1. usa `M1 + M5 + H1`
2. tiene al menos 3 setups heuristicos explicitos
3. tiene trigger `M1`
4. tiene gates de session, spread y slippage
5. usa `RiskKernel` como autoridad real
6. registra ownership en toda nueva ejecucion
7. puede custodiar heredadas Fast
8. puede abrir, custodiar y cerrar
9. puede gestionar pending orders Fast
10. no rompe la suite ni la certificacion del conector
