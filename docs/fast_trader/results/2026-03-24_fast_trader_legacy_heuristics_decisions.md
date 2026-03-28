# FastTrader Legacy Heuristics Decisions (2026-03-24)

## Objetivo

Documentar que partes del legado se importaron al `FastTraderService` y como se tradujeron a contratos deterministas en `src/heuristic_mt5_bridge/fast_desk/`.

## Fuentes legacy usadas

- `llm-metatrader5-bridge/python/prompts/smc_trader/tools/smc_entry_models.md`
- `llm-metatrader5-bridge/python/prompts/smc_trader/tools/chartism_patterns.md`
- `llm-metatrader5-bridge/python/prompts/smc_trader/tools/sltp_methods.md`
- `llm-metatrader5-bridge/python/live_execution_trader_runtime.py`
- `llm-metatrader5-bridge/python/execution_bridge.py`
- `llm-metatrader5-bridge/python/smc_heuristic_scanner.py`

## Traducciones aplicadas

1. Setup library M5:
- `order_block_retest`, `liquidity_sweep_reclaim`, `breakout_retest`.
- `wedge_retest`, `flag_retest`, `triangle_retest`, `sr_polarity_retest`.
- Implementado en `fast_desk/setup/engine.py` con `risk_pips`, `confidence`, `pending intent` y niveles SL/TP derivados.

2. Trigger library M1:
- `micro_bos`, `micro_choch`, `rejection_candle`, `reclaim`, `displacement`.
- Implementado en `fast_desk/trigger/engine.py`.
- Regla dura aplicada: sin trigger M1 valido no hay ejecucion.

3. Context and gates:
- Sesion, spread, slippage esperada, stale feed y sesgo H1.
- Implementado en `fast_desk/context/service.py`.

4. Pending lifecycle:
- Repricing por distancia y cancel defensivo por invalidez/timeout/gates.
- Implementado en `fast_desk/pending/manager.py`.

5. Professional custody:
- Break-even, ATR trailing, structural trailing, hard cut, no passive underwater, scale-out opcional.
- Implementado en `fast_desk/custody/engine.py`.

6. Conector canonico unificado:
- Solo `send_execution_instruction`, `modify_position_levels`, `modify_order_levels`, `remove_order`, `close_position`, `find_open_position_id`.
- Implementado via `fast_desk/execution/bridge.py`.

## Decisiones de alcance

- No se importaron roles LLM ni memoria de oficina al camino fast.
- No se modifico `SmcTraderService`, `BridgeSupervisor`, `paper mode` ni WebUI.
- Custodia limitada a ownership `fast_owned` e `inherited_fast` para no interferir con SMC.
- Config canonica `FAST_TRADER_*` con compatibilidad backward `FAST_DESK_*` (prioridad a canonica).
