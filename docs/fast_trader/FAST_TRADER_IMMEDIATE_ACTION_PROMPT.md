# FastTrader Immediate Action Prompt

Usa este texto para arrancar un constructor nuevo sin contexto adicional:

```md
Quiero que ejecutes la siguiente fase canonica del backend de
`heuristic-metatrader5-bridge`: `FastTraderService`.

Antes de escribir codigo, lee en este orden:

1. `docs/fast_trader/FAST_TRADER_BACKEND_HANDOFF.md`
2. `docs/fast_trader/audit/2026-03-24_fast_trader_gap_audit.md`
3. `docs/fast_trader/sources/2026-03-24_fast_trader_source_inventory.md`
4. `docs/fast_trader/plans/2026-03-24_fast_trader_constructor_plan.md`
5. `docs/fast_trader/actions/2026-03-24_fast_trader_constructor_actions.md`
6. `docs/fast_trader/prompts/2026-03-24_FAST_TRADER_SERVICE_CONSTRUCTOR.md`

Luego implementa exactamente ese bloque.

No avances a:

- `SmcTraderService`
- `BridgeSupervisor`
- `paper mode`
- WebUI

No quiero brainstorming ni propuesta general.
Quiero implementacion real, tests, y cierre tecnico de la fase Fast.
```

## Uso esperado

Este archivo no reemplaza el prompt canonico.

Sirve para:

- arrancar rapido un constructor
- evitar que lea el orden equivocado
- mantener la secuencia canonica del backend

El prompt que manda sigue siendo:

- [`prompts/2026-03-24_FAST_TRADER_SERVICE_CONSTRUCTOR.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/fast_trader/prompts/2026-03-24_FAST_TRADER_SERVICE_CONSTRUCTOR.md)
