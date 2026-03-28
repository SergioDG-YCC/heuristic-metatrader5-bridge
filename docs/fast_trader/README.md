# Fast Trader Documentation Site

Fecha base: 2026-03-24

## Proposito

Este directorio centraliza toda la documentacion canónica del nucleo
`FastTraderService`.

Debe usarse como sitio documental de referencia para:

- plan funcional
- decisiones de arquitectura
- prompts de constructor
- evidencia de pruebas
- resultados de validacion
- acciones de correccion

La idea es repetir este mismo patron luego para los otros nucleos faltantes:

- `docs/smc_trader`
- `docs/bridge_supervisor`
- `docs/paper_mode`

## Relacion con el plan global

Este sitio documental cuelga del plan canónico en:

- [`docs/plans/2026-03-24_immutable_bridge_action_plan.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/plans/2026-03-24_immutable_bridge_action_plan.md)

Fase objetivo:

- `Phase 5 - FastTraderService`

## Estructura

- [`plans/README.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/plans/README.md)
  Planes de implementacion, fases internas, checklist y criterios de aceptacion.
- [`actions/README.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/actions/README.md)
  Acciones puntuales, correcciones, follow-ups y decisiones ejecutivas.
- [`prompts/README.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/prompts/README.md)
  Prompts de constructores y subtareas de implementacion.
- [`results/README.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/results/README.md)
  Resultados, reportes de ejecucion, certificacion y validaciones.
- [`audit/README.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/audit/README.md)
  Auditorias tecnicas, hallazgos y comparativas contra la repo vieja.
- [`sources/README.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/sources/README.md)
  Referencias de origen a reutilizar o contrastar, incluyendo heuristicas viejas.

## Documentos activos

- [`FAST_TRADER_BACKEND_HANDOFF.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/FAST_TRADER_BACKEND_HANDOFF.md)
- [`FAST_TRADER_IMMEDIATE_ACTION_PROMPT.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/FAST_TRADER_IMMEDIATE_ACTION_PROMPT.md)
- [`audit/2026-03-24_fast_trader_gap_audit.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/audit/2026-03-24_fast_trader_gap_audit.md)
- [`sources/2026-03-24_fast_trader_source_inventory.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/sources/2026-03-24_fast_trader_source_inventory.md)
- [`plans/2026-03-24_fast_trader_constructor_plan.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/plans/2026-03-24_fast_trader_constructor_plan.md)
- [`actions/2026-03-24_fast_trader_constructor_actions.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/actions/2026-03-24_fast_trader_constructor_actions.md)
- [`prompts/2026-03-24_FAST_TRADER_SERVICE_CONSTRUCTOR.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/prompts/2026-03-24_FAST_TRADER_SERVICE_CONSTRUCTOR.md)

## Convencion de nombres recomendada

Usar prefijos fechados para trazabilidad:

- `YYYY-MM-DD_fast_trader_*.md`

Ejemplos:

- `2026-03-24_fast_trader_constructor_plan.md`
- `2026-03-24_fast_trader_gap_audit.md`
- `2026-03-24_fast_trader_execution_validation.md`

## Alcance esperado del nucleo

Este sitio debe cubrir, como minimo:

- contexto `M1 + M5 + H1`
- setup heuristico Fast
- trigger microestructural
- gates de sesion, spread y slippage
- custody profesional
- uso de `OwnershipRegistry`
- uso de `RiskKernel`
- audit trail operativo

## Nota operativa

La WebUI puede construirse en paralelo, pero el backend operativo final manda.
Toda decision de UI sobre Fast debe terminar referenciando este sitio documental.
