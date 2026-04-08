# Auditoria FAST DESK + Analista Heuristico (RR>=3.0)

Fecha: 2026-03-27
Repositorio auditado: E:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge
Autor: Codex

## 1) Alcance y metodo

- Alcance: solo codigo Python y docs internas de este repositorio.
- Restriccion respetada: no se leyo nada dentro de `E:\GITLAB\Sergio_Privado\llm-metatrader5-bridge`.
- Se revisaron capas: runtime, contexto, setup, trigger, riesgo, entry policy, ejecucion, custody, pending, scanner SMC, analista heuristico y validadores.
- Se ejecutaron tests:
  - `.venv\\Scripts\\python.exe -m pytest -q tests/fast_desk` -> 53 passed, 3 failed.
  - `.venv\\Scripts\\python.exe -m pytest -q tests/smc_desk/test_smc_desk.py` -> 30 passed.

## 2) Inventario de herramientas heuristicas

### 2.1 Analista SMC (heuristic analyst)

Herramientas de deteccion y contexto que el analista consume:

- Estructura de mercado (BOS/CHoCH/swing labels): `detect_market_structure`.
  Evidencia: `src/heuristic_mt5_bridge/smc_desk/detection/structure.py:328`
- Order Blocks: `detect_order_blocks`.
  Evidencia: `src/heuristic_mt5_bridge/smc_desk/detection/order_blocks.py:73`
- Fair Value Gaps: `detect_fair_value_gaps`.
  Evidencia: `src/heuristic_mt5_bridge/smc_desk/detection/fair_value_gaps.py:18`
- Liquidity pools + sweeps: `detect_liquidity_pools`, `detect_sweeps`.
  Evidencia: `src/heuristic_mt5_bridge/smc_desk/detection/liquidity.py:44`, `:144`
- Fibonacci levels: `fibo_levels_for_structure`.
  Evidencia: `src/heuristic_mt5_bridge/smc_desk/detection/fibonacci.py:43`
- Elliott count: `count_waves`.
  Evidencia: `src/heuristic_mt5_bridge/smc_desk/detection/elliott.py:176`
- Confluencias ponderadas: `evaluate_confluences`.
  Evidencia: `src/heuristic_mt5_bridge/smc_desk/detection/confluences.py:55`

Herramientas de decision del analista:

- Derivacion de bias multi-TF y alineacion: `_derive_bias`, `_build_multi_timeframe_alignment`.
  Evidencia: `src/heuristic_mt5_bridge/smc_desk/analyst/heuristic_analyst.py:144`, `:165`
- Scoring de zona: `_score_zone`.
  Evidencia: `.../heuristic_analyst.py:195`
- Seleccion de modelo de entrada: `_choose_entry_model`.
  Evidencia: `.../heuristic_analyst.py:243`
- Construccion de targets/SL/TP y candidato: `_build_targets`, `_build_operation_candidate`.
  Evidencia: `.../heuristic_analyst.py:301`, `:356`
- Construccion de output heuristico: `build_heuristic_output`.
  Evidencia: `.../heuristic_analyst.py:445`
- Hard validator de tesis/candidatos: `validate_heuristic_thesis`.
  Evidencia: `src/heuristic_mt5_bridge/smc_desk/validators/heuristic.py:277`

### 2.2 FAST TRADER / FAST DESK

Pipeline heuristico operativo:

- Contexto de mercado (sesion, spread %, slippage %, stale feed, fase, exhaustion): `build_context`.
  Evidencia: `src/heuristic_mt5_bridge/fast_desk/context/service.py:78`
- Deteccion de setups M5: `detect_setups`.
  Evidencia: `src/heuristic_mt5_bridge/fast_desk/setup/engine.py:41`
  - Setups core/patrones activos: `order_block_retest`, `liquidity_sweep_reclaim`, `breakout_retest`, `wedge_retest`, `flag_retest`, `triangle_retest`, `sr_polarity_retest`.
- Confirmacion de trigger M1: `confirm`.
  Evidencia: `src/heuristic_mt5_bridge/fast_desk/trigger/engine.py:30`
  - Triggers: `micro_bos`, `micro_choch`, `rejection_candle`, `reclaim`, `displacement`.
- Riesgo (lot size + safety): `calculate_lot_size`, `check_account_safe`.
  Evidencia: `src/heuristic_mt5_bridge/fast_desk/risk/engine.py:19`
- Entry policy: `can_open`.
  Evidencia: `src/heuristic_mt5_bridge/fast_desk/policies/entry.py:10`
- Custody: `evaluate_position`.
  Evidencia: `src/heuristic_mt5_bridge/fast_desk/custody/engine.py:39`
- Pending manager: `evaluate`.
  Evidencia: `src/heuristic_mt5_bridge/fast_desk/pending/manager.py:32`
- Orquestacion trader: `scan_and_execute` + `run_custody`.
  Evidencia: `src/heuristic_mt5_bridge/fast_desk/trader/service.py:104`, `:395`
- Runtime por simbolo: `FastDeskConfig`, `run_forever`.
  Evidencia: `src/heuristic_mt5_bridge/fast_desk/runtime.py:92`, `:189`

## 3) Hallazgos (priorizados)

## Criticos

1. RR minimo efectivo por defecto sigue en 2.0, no en 3.0.
- Fast Desk:
  - `FastDeskConfig.min_rr = 2.0` (`fast_desk/runtime.py:102`)
  - `FAST_TRADER_MIN_RR` default 2.0 (`fast_desk/runtime.py:132`)
  - `FastSetupConfig.min_rr = 2.0` (`fast_desk/setup/engine.py:15`)
- SMC Analyst:
  - `SmcAnalystConfig.min_rr = 2.0` (`smc_desk/analyst/heuristic_analyst.py:57`)
  - `SMC_MIN_RR` default 2.0 (`.../heuristic_analyst.py:82`)
  - Validator default 2.0 (`smc_desk/validators/heuristic.py:283`)
- Estado real del `.env`: no existen `FAST_TRADER_MIN_RR` ni `SMC_MIN_RR` (busqueda: `NO_MATCH`).

Impacto:
- El sistema acepta operaciones RR inaceptables para una politica estricta de scalping RR>=3.0.

2. API Fast Config no expone `min_rr`, por lo que no se puede gobernar RR minimo en runtime desde control plane.
- Request model Fast no tiene `min_rr`: `apps/control_plane.py:252-271`.
- PUT `/api/v1/config/fast` no mapea `min_rr`: `apps/control_plane.py:695-706`.

Impacto:
- Gobernanza incompleta del control de calidad mas importante (RR floor).

## Altos

3. Criterio de calidad SMC marca candidato como `high` desde RR 2.4.
- `quality = "high" if len(confluences) >= 3 and rr >= 2.4 else "medium"`.
  Evidencia: `smc_desk/analyst/heuristic_analyst.py:412`.

Impacto:
- Etiquetado de alta calidad incompatible con politica RR>=3.0.

4. Hot-reload parcial en Fast Desk: cambios runtime no-contexto no se propagan a workers vivos.
- Solo se actualiza `context_config`: `fast_desk/runtime.py:180-187`.
- `worker_config/risk_config/scanner_config/setup_config/trader_config` se construyen una vez antes del loop: `fast_desk/runtime.py:205-246`.

Impacto:
- Cambios por API en RR, riesgo, cooldown, pending/custody no necesariamente aplican al ciclo vivo sin recrear workers.

5. Inconsistencia de superficie de configuracion FAST_DESK vs FAST_TRADER.
- Runtime canonico prioriza `FAST_TRADER_*`: `fast_desk/runtime.py:70`, `:79`, `:132`, `:134-140`.
- API fallback usa solo `FAST_DESK_*`: `apps/control_plane.py:674-684`, `:695-706`.

Impacto:
- Riesgo de drift de configuracion entre lo que UI muestra y lo que runtime realmente usa al reiniciar.

6. `FastEntryPolicy` no aplica limite por simbolo de forma completa.
- Bloquea solo duplicado mismo `symbol+side` y total global, no `max_positions_per_symbol` estricto.
  Evidencia: `fast_desk/policies/entry.py:21`, `:37-42`.

Impacto:
- Puede abrirse 1 buy y 1 sell en el mismo simbolo aunque el perfil requiera max 1 posicion/simbolo.

## Medios

7. Deuda de contrato en riesgo: comentario y changelog dicen cap 2%, pero codigo no lo fuerza.
- Comentario: `risk_per_trade_percent: float = 1.0  # max allowed is 2.0` (`fast_desk/risk/engine.py:10`).
- Formula no clampa `risk_pct` a 2.0 (`fast_desk/risk/engine.py:19-110`).
- Changelog tambien afirma hard cap 2% (`CHANGELOG.md:244`).

Impacto:
- Riesgo de operar con porcentaje mayor al especificado si falla o se omite `RiskKernel`.

8. Tests fast con deuda tecnica real (3 fallos) por firma antigua de `calculate_lot_size`.
- Falla al pasar `pip_value` float en lugar de `symbol_spec dict`.
  Evidencia de test: `tests/fast_desk/test_fast_desk.py:100`, `:115`, `:120`.
- Resultado observado: `3 failed, 53 passed` en `tests/fast_desk`.

Impacto:
- La suite no protege correctamente el contrato actual de riesgo.

9. `FastConfigUpdateRequest` incluye `max_slippage_points`, pero runtime usa `max_slippage_pct`.
- API field: `apps/control_plane.py:263`.
- Runtime config: `fast_desk/runtime.py:105`.
- El `setattr` silencioso puede dejar este campo sin efecto: `apps/control_plane.py:760-764`.

Impacto:
- Parametro fantasma en API, potencial confusion operativa.

10. Modulo `fast_desk/signals/scanner.py` quedo incompleto/dead para la arquitectura actual.
- Solo contiene dataclasses/utiles, sin servicio operativo (`65` lineas).
  Evidencia: `fast_desk/signals/scanner.py` (line count 65).

Impacto:
- Superficie de codigo ambigua y deuda de mantenimiento.

11. Metodos legacy en execution bridge referencian tipos no definidos en el modulo.
- `FastSignal`, `CustodyDecision`, `CustodyAction` usados en metodos legacy.
  Evidencia: `fast_desk/execution/bridge.py:218`, `:234`, `:240`, `:252`.

Impacto:
- Riesgo de error runtime si se invocan rutas legacy.

## 4) Evaluacion de estrategia (RR>=3.0)

Situacion actual:
- Fast Desk construye TP con `rr_ratio` default 3.0, pero filtra por `min_rr` default 2.0.
  Evidencia: `fast_desk/runtime.py:101-102`, `fast_desk/setup/engine.py:13-15`.
- SMC valida con `min_rr` default 2.0 y clasifica `high` desde 2.4.
  Evidencia: `smc_desk/validators/heuristic.py:283`, `smc_desk/analyst/heuristic_analyst.py:412`.

Conclusion:
- El stack no esta bloqueado de extremo a extremo en RR>=3.0.
- Hay piezas RR3-ready, pero la puerta de calidad final sigue en 2.0.

## 5) Plan de correccion arquitectonica (sin tocar codigo en esta auditoria)

Fase A (obligatoria, inmediata)
1. Subir floors:
- Fast: `FAST_TRADER_MIN_RR` default y runtime -> `3.0`.
- SMC: `SMC_MIN_RR` default y validator -> `3.0`.
2. Exponer `min_rr` en `/api/v1/config/fast` (GET/PUT + modelo).
3. Cambiar etiqueta de calidad SMC `high` a `rr >= 3.0`.

Fase B (consistencia runtime)
1. Hot-reload completo en Fast Desk:
- O recrear workers al cambiar config no-contexto,
- o inyectar referencias mutables para `risk/setup/trader/pending/custody`.
2. Eliminar parametro fantasma `max_slippage_points` o mapearlo a `%` claramente.
3. Unificar superficie de config canonica en API: priorizar `FAST_TRADER_*` y usar alias legacy solo para compatibilidad.

Fase C (hardening de riesgo)
1. En `FastRiskEngine`, si se define politica local, clamp explicito de `risk_pct` a max permitido.
2. Aplicar `volume_min` + `volume_step` ademas de `volume_max` para evitar rechazos por granularidad.
3. En `FastEntryPolicy`, aplicar `max_positions_per_symbol` real (no solo duplicado por lado).

Fase D (calidad de pruebas)
1. Reparar `tests/fast_desk/test_fast_desk.py` al contrato actual de `calculate_lot_size(symbol_spec, account_state)`.
2. Agregar tests de aceptacion RR>=3.0 en Fast y SMC.
3. Agregar test de config API para `min_rr` en Fast.

## 6) Resumen ejecutivo

- El motor heuristico es solido y bien modularizado, pero hoy no garantiza RR>=3.0 de punta a punta.
- El mayor gap es de politica/configuracion (floors 2.0 + API Fast sin `min_rr`) mas que de deteccion tecnica.
- Prioridad inmediata: cerrar la brecha de RR y la gobernanza de config en runtime.
