# Fast Trader Source Inventory

Fecha: 2026-03-24

## Proposito

Listar qué fuentes deben leerse para construir `FastTraderService`, qué puede
reutilizarse y qué no debe importarse como runtime.

## Fuentes canónicas de esta repo

Leer primero:

- [`docs/plans/2026-03-24_immutable_bridge_action_plan.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/plans/2026-03-24_immutable_bridge_action_plan.md)
- [`docs/plans/2026-03-24_ownership_risk_operational_contract.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/plans/2026-03-24_ownership_risk_operational_contract.md)
- [`docs/ARCHITECTURE.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/docs/ARCHITECTURE.md)
- [`README.md`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/README.md)

Código actual a usar como base real:

- [`core/runtime/service.py`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/src/heuristic_mt5_bridge/core/runtime/service.py)
- [`infra/mt5/connector.py`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/src/heuristic_mt5_bridge/infra/mt5/connector.py)
- [`core/ownership/registry.py`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/src/heuristic_mt5_bridge/core/ownership/registry.py)
- [`core/risk/kernel.py`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/src/heuristic_mt5_bridge/core/risk/kernel.py)
- [`fast_desk/`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/src/heuristic_mt5_bridge/fast_desk)

SMC detectors ya portados que pueden ser extraíbles:

- [`smc_desk/scanner/scanner.py`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/src/heuristic_mt5_bridge/smc_desk/scanner/scanner.py)
- [`smc_desk/detection/`](/e:/GITLAB/Sergio_Privado/heuristic-metatrader5-bridge/src/heuristic_mt5_bridge/smc_desk/detection)

## Fuentes de la repo vieja

Usar sólo como fuente de comportamiento:

- [CHANGELOG.md](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/CHANGELOG.md)
- [live_execution_trader_runtime.py](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/live_execution_trader_runtime.py)
- [execution_bridge.py](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/execution_bridge.py)
- [smc_heuristic_scanner.py](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/smc_heuristic_scanner.py)

Tools docs importantes:

- [chartism_patterns.md](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/prompts/smc_trader/tools/chartism_patterns.md)
- [sltp_methods.md](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/prompts/smc_trader/tools/sltp_methods.md)
- [smc_entry_models.md](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/python/prompts/smc_trader/tools/smc_entry_models.md)

## Qué reutilizar

### De la repo heurística actual

Reutilizar directamente:

- `CoreRuntimeService`
- `MarketStateService`
- `MT5Connector`
- `OwnershipRegistry`
- `RiskKernel`
- `FastExecutionBridge` como base mínima
- estructura de `fast_desk` por módulos

Reutilizar parcialmente:

- `fast_desk/signals/scanner.py`
- `fast_desk/custody/custodian.py`
- `fast_desk/policies/entry.py`
- `fast_desk/workers/symbol_worker.py`

### De la repo vieja

Reutilizar como lógica o referencia:

- trailing y enforcement del `live_execution_trader`
- reglas de no passive underwater
- protección de profit
- algunos patrones chartistas
- ideas de `sltp_methods`
- modelos de entrada basados en order block / sweep / BOS / retest

### De `smc_heuristic_scanner.py`

Reutilizar sólo si hace falta, en formato extraído o adaptado:

- detección de `order blocks`
- `market structure`
- `liquidity`
- `fair value gaps`
- confluencias
- fibo ligado a estructura

## Qué NO reutilizar como runtime

No importar entero ni copiar ciegamente:

- `live_execution_trader_runtime.py`
- `execution_bridge.py`
- orquestación vieja LLM
- office stack vieja
- decisiones atadas a runtimes lentos

## Traducción de fuentes a responsabilidades Fast

### `chartism_patterns.md`

Sirve para:

- definir librería inicial de patrones chartistas Fast
- reglas de breakout válidos
- invalidación estructural
- objetivos por patrón

No debe usarse como texto suelto.
Debe traducirse a heurísticas deterministas.

### `sltp_methods.md`

Sirve para:

- reglas de SL por estructura
- fallback por ATR
- TP por R:R y estructura
- pending order reconsideration

Debe traducirse a:

- calculadores Python
- trailing policy
- update policy

### `smc_entry_models.md`

Sirve para:

- modelar setups `sweep + OB`
- `FVG + OB`
- `BOS + OB`

Para Fast se deben simplificar a:

- ordenes y setup rápidos en `M5`
- confirmación `M1`
- contexto `H1`

## Decisión sobre `smc_heuristic_scanner.py`

No usarlo como dependencia runtime del Fast.

Sí usarlo para:

- verificar si la detección de `order blocks` ya migrada en `smc_desk/detection`
  es suficiente
- comparar cobertura heurística
- extraer reglas faltantes

Si los detectores portados ya alcanzan el nivel requerido:

- reutilizar detectores actuales

Si no alcanzan:

- reconstruir sólo las piezas necesarias desde las fuentes viejas
- mantenerlas dentro del dominio `fast_desk`

## Prioridad de extracción heurística

Orden recomendado:

1. `order block retest`
2. `liquidity sweep + reclaim`
3. `breakout + retest`
4. `structural SL/TP`
5. `ATR trailing`
6. `chart patterns` robustos para scalping/intraday

## Regla editorial para el constructor

Toda heurística importada de la repo vieja debe entrar documentada como:

- fuente
- decisión de reutilización
- adaptación hecha
- por qué aplica a Fast y no sólo a SMC

Eso evita copiar lógica vieja sin justificación.
