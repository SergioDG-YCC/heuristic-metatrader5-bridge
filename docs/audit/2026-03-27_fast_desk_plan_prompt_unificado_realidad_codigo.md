# Fast Desk - Plan de accion + prompt unificado, cotejado con codigo real

Fecha: 2026-03-27
Repositorio auditado: `E:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge`
Fuentes de ingesta tratadas en conjunto:
- `docs/audit/2026-03-27_fast_desk_analyst_heuristic_deep_audit.md`
- `docs/audit/2026-03-27_fast_desk_action_plan_and_repair_prompt.md`
- `docs/audit/codex_fast_desk_analyst_audit_2026-03-27.md`

## 1. Criterio de este documento

Este documento no elige un informe "ganador". Toma los 3 como insumo, los contrasta con el codigo real y deja un plan unificado corregido.

Verificacion adicional ejecutada en esta sesion:
- Revision directa de `fast_desk`, `smc_desk`, `apps/control_plane.py` y tests asociados.
- Ejecucion de `pytest -q tests/fast_desk`: `53 passed, 3 failed`.

## 2. Estado real cotejado con codigo

### 2.1 Hallazgos confirmados

1. El floor de RR sigue abierto en `2.0` en piezas criticas.
- `fast_desk/runtime.py`: `FastDeskConfig.min_rr = 2.0` y `FAST_TRADER_MIN_RR` default `2.0`.
- `fast_desk/setup/engine.py`: `FastSetupConfig.min_rr = 2.0`.
- `smc_desk/analyst/heuristic_analyst.py`: `SmcAnalystConfig.min_rr = 2.0` y env default `SMC_MIN_RR=2.0`.
- `smc_desk/validators/heuristic.py`: `validate_heuristic_thesis(..., min_rr: float = 2.0)`.

2. El setup engine preserva `rr_ratio=3.0`, pero admite setups con RR efectivo menor a 3.0 tras ajuste de spread.
- `fast_desk/setup/engine.py` ajusta solo `stop_loss`, deja `take_profit` fijo y filtra con `min_rr`.
- Eso permite degradacion de RR efectivo mientras `min_rr` siga en `2.0`.

3. La API Fast no gobierna bien `min_rr`.
- `FastDeskConfig.to_dict()` si expone `min_rr`.
- Pero `apps/control_plane.py` no incluye `min_rr` en `FastConfigUpdateRequest`.
- Tampoco lo incluye en el fallback inactivo de `GET /api/v1/config/fast` ni en `_FAST_ENV_MAP`.
- El problema real es parcial: lectura runtime si existe, escritura/gobernanza por API no.

4. El hot-reload real de Fast Desk es parcial.
- `FastDeskService.update_context_config()` solo propaga cambios a `FastContextConfig`.
- `risk_config`, `setup_config`, `trader_config`, `pending_config` y `custody_config` se construyen una vez en `run_forever()`.

5. Hay drift entre namespaces `FAST_TRADER_*` y `FAST_DESK_*`.
- `fast_desk/runtime.py` prioriza `FAST_TRADER_*` con alias legacy.
- `apps/control_plane.py` fallback de Fast usa solo `FAST_DESK_*`.

6. `max_positions_per_symbol` no se enforcea como limite real por simbolo.
- `fast_desk/policies/entry.py` bloquea duplicado mismo `symbol+side` y total global.
- No bloquea `buy` y `sell` simultaneos del mismo simbolo cuando el perfil exige maximo 1.

7. `scanner.py` no es el pipeline activo, pero sigue vivo como configuracion redundante.
- `fast_desk/runtime.py` sigue creando `FastScannerConfig`.
- `fast_desk/workers/symbol_worker.py` lo usa solo como fallback si `setup_config is None`.
- En el flujo normal del runtime, `setup_config` ya viene construido y `scanner_config` queda practicamente decorativo.

8. `micro_choch` confirma sin exigir `confirmed=True`.
- `fast_desk/trigger/engine.py` lee `last_choch` y solo valida direccion.
- El flag `confirmed` existe en `smc_desk/detection/structure.py`, pero aqui no se usa.

9. `breakout_retest` no filtra edad del BOS.
- `fast_desk/setup/engine.py` valida cercania al nivel y cuerpo impulsivo del BOS.
- No invalida BOS viejos.

10. `order_block_retest` usa `min_impulse_candles=2`.
- Confirmado en `fast_desk/setup/engine.py`.

11. FVG existe en SMC, pero no esta integrado en Fast Desk.
- `detect_fair_value_gaps()` existe y se usa en `smc_desk/scanner/scanner.py`.
- No hay referencias en `fast_desk`.

12. El engine de riesgo no fuerza el cap documentado del 2%.
- `fast_desk/risk/engine.py` comenta "max allowed is 2.0", pero no clampa `risk_pct`.

13. El engine de riesgo no ofrece `max_lot_size` configurable.
- Solo aplica un cap hardcoded de `50.0`.
- En el servicio ademas se hace `min(volume, volume_max)` por spec, pero no existe cap operativo configurable.

14. La deuda de tests es real y reproducible.
- `tests/fast_desk/test_fast_desk.py` sigue llamando `calculate_lot_size(..., pip_value_float)`.
- La firma real hoy espera `symbol_spec: dict`.
- Resultado reproducido: `3 failed, 53 passed`.

15. `hard_cut_r=1.25` sigue por encima del riesgo base.
- Confirmado en `fast_desk/custody/engine.py`.

16. Hay llamadas repetidas a `detect_market_structure()` en un mismo ciclo.
- `context/service.py`, `setup/engine.py`, `trigger/engine.py` recalculan estructura por separado.
- Ademas `trigger/engine.py` recalcula M1 una vez para BOS y otra para CHoCH sobre el mismo slice.

### 2.2 Hallazgos que hubo que corregir o matizar

1. "Si `send_entry()` falla, la senal desaparece sin persistencia" no es exacto en el codigo actual.
- `fast_desk/trader/service.py` envuelve `send_entry()` en `try/except`.
- Si falla, genera `result={"ok": False, "error": ...}`, marca `outcome="error"` y luego hace `runtime_db.upsert_fast_signal(...)`.
- El hueco real de observabilidad esta en `fast_desk/workers/symbol_worker.py`: errores de scan o custody fuera de `scan_and_execute()` se quedan en `print(...)`.

2. `scanner.py` no es "codigo muerto puro".
- No aporta scanning activo, pero todavia participa como fallback de configuracion.
- Debe simplificarse o retirarse, pero el diagnostico correcto es "config redundante y ambigua", no "muerto puro".

3. `max_slippage_points` no es totalmente fantasma.
- Es inconsistente en Fast API y en `FastTraderConfig`, porque ese dataclass no lo define.
- Pero si existe y se usa en `fast_desk/execution/bridge.py` para la orden MT5.
- El problema real es desalineacion entre slippage de contexto (`max_slippage_pct`) y slippage de ejecucion (`max_slippage_points`), mas una llamada invalida en `symbol_worker.py`.

4. La persistencia previa a ejecucion es una mejora valida, pero no corrige un bug literal de desaparicion post-excepcion en `send_entry()`.
- Esa mejora sirve para auditoria operativa fina y trazabilidad temporal.
- No debe justificarse con una premisa falsa sobre el estado actual.

## 3. Tests y evidencia operativa de esta revision

Comando ejecutado:

```bash
pytest -q tests/fast_desk
```

Resultado:
- `53 passed`
- `3 failed`

Fallos:
- `tests/fast_desk/test_fast_desk.py::TestFastRiskEngine::test_calculate_lot_size_known_inputs`
- `tests/fast_desk/test_fast_desk.py::TestFastRiskEngine::test_lot_size_clamped_to_minimum`
- `tests/fast_desk/test_fast_desk.py::TestFastRiskEngine::test_lot_size_risk_capped_at_2pct`

Causa comun:
- Los tests usan la firma vieja de `calculate_lot_size(...)`.
- Uno de ellos ademas espera un cap al 2% que el engine hoy no implementa.

## 4. Plan de accion unificado y corregido

### Fase 1 - Obligatoria antes de operar live

Objetivo: cerrar la brecha RR>=3.0 y gobernarla de punta a punta.

1. Unificar `min_rr=3.0` en Fast + SMC.
- Archivos:
  - `src/heuristic_mt5_bridge/fast_desk/runtime.py`
  - `src/heuristic_mt5_bridge/fast_desk/setup/engine.py`
  - `src/heuristic_mt5_bridge/smc_desk/analyst/heuristic_analyst.py`
  - `src/heuristic_mt5_bridge/smc_desk/validators/heuristic.py`
  - `apps/control_plane.py`
- Criterio:
  - ningun default nuevo en `2.0`
  - `quality="high"` en SMC solo cuando `rr >= 3.0`

2. Exponer `min_rr` correctamente en Fast API.
- Agregar `min_rr: float | None = None` a `FastConfigUpdateRequest`.
- Incluirlo en:
  - fallback de `GET /api/v1/config/fast`
  - `_FAST_ENV_MAP`
  - respuesta de desk inactivo
- Validar rango razonable en API.

3. Corregir la inconsistencia de RR efectivo bajo spread.
- Opcion preferida: si el spread degrada el RR efectivo por debajo del floor, descartar el setup.
- Opcion mas estricta: recalcular `take_profit` desde riesgo ajustado para preservar RR real.
- Elegir una sola politica y documentarla.

### Fase 2 - Riesgo y contratos basicos

Objetivo: evitar rechazos silenciosos y volver confiable la superficie de riesgo.

1. Agregar `max_lot_size` configurable.
- Archivos:
  - `fast_desk/risk/engine.py`
  - `fast_desk/runtime.py`
  - `apps/control_plane.py`
- Aplicar cap junto con `volume_max` del spec.

2. Clampear `risk_pct` al maximo de politica o mover esa responsabilidad a un solo punto de verdad.
- Si se decide que el engine haga enforcement local, agregar clamp explicito.
- Si se decide que solo el `RiskKernel` gobierna, alinear comentarios, tests y docs para no prometer un cap que el engine no hace.

3. Reparar tests del contrato actual.
- Actualizar `tests/fast_desk/test_fast_desk.py` al uso de `symbol_spec`.
- Separar el test del 2% en:
  - test de clamp real, si se implementa
  - o eliminacion/reescritura si la politica queda en otro componente

### Fase 3 - Observabilidad y coherencia runtime

Objetivo: saber que falla y que config esta realmente viva.

1. Persistir mejor los errores de scan/custody del worker.
- `fast_desk/workers/symbol_worker.py` hoy solo imprime.
- Emitir `activity_log` y/o `fast_desk_trade_log` con contexto de simbolo y excepcion.

2. Evaluar persistencia pre-ejecucion de senales como mejora de trazabilidad.
- Implementar `pending -> accepted/rejected/error` solo si se quiere auditoria temporal mas fina.
- No presentarlo como arreglo de una perdida actual post-`send_entry()` porque esa perdida no es literal hoy.

3. Resolver hot-reload parcial.
- O recrear workers cuando cambie config no-contexto.
- O pasar referencias mutables compartidas a setup/risk/trader/pending/custody.
- No mezclar ambos enfoques en la misma iteracion.

4. Unificar namespace canonico de env vars.
- Canonico recomendado: `FAST_TRADER_*`.
- Mantener `FAST_DESK_*` solo como alias legacy de lectura.

5. Corregir `symbol_worker.py` para no construir `FastTraderConfig(max_slippage_points=30)`.
- `FastTraderConfig` no acepta ese campo.
- Ese fallback debe eliminarse o alinearse al dataclass real.

### Fase 4 - Calidad de senal

Objetivo: mejorar precision antes de agregar complejidad nueva.

1. Endurecer `micro_choch`.
- Requerir `choch.get("confirmed") is True`.

2. Agregar filtro de edad al `breakout_retest`.
- BOS dentro de una ventana reciente explicita.

3. Subir `min_impulse_candles` de Order Blocks a `3`.

4. Reforzar `rejection_candle`.
- Solo despues de resolver los puntos 1-3.
- Agregar contexto de zona o filtro ATR/pip minimo.

### Fase 5 - Mejoras estrategicas, no bloqueantes

Objetivo: subir calidad estructural una vez estabilizado el core.

1. Integrar FVG en Fast Desk.
- Como confluencia primero.
- Como setup nuevo solo en una segunda iteracion.

2. Centralizar estructuras precalculadas.
- `FastContext` puede transportar estructuras M1/M5/H1 para evitar recalculos.

3. Revisar custody.
- Reevaluar `hard_cut_r=1.25`.
- Confirmar si es proteccion de emergencia o si esta sustituyendo un SL que deberia cerrar antes.

## 5. Orden recomendado de implementacion

1. RR floor y API de `min_rr`
2. Riesgo (`max_lot_size`, criterio del 2%)
3. Tests rotos del contrato actual
4. Observabilidad del worker
5. Hot-reload y namespace de env vars
6. Filtros de calidad (`micro_choch`, BOS age, OB impulse)
7. FVG y performance

## 6. Prompt unificado de reparacion

```text
PROMPT DE REPARACION

Repositorio: heuristic-metatrader5-bridge
Fecha base: 2026-03-27
Objetivo: reparar Fast Desk y su integracion con SMC para que el stack quede coherente con una politica RR >= 3.0, con configuracion gobernable por API y sin deuda operativa obvia en riesgo/tests/runtime.

REGLAS
1. Trabajar solo sobre el repositorio actual.
2. No tocar .env manualmente.
3. Hacer cambios pequenos y verificables.
4. Despues de cada bloque relevante, ejecutar tests del area afectada.
5. No introducir refactors grandes fuera del alcance explicitado.

FASE 1 - RR Y GOBERNANZA
1. Subir todos los defaults de `min_rr` de 2.0 a 3.0 en:
   - fast_desk/runtime.py
   - fast_desk/setup/engine.py
   - smc_desk/analyst/heuristic_analyst.py
   - smc_desk/validators/heuristic.py
   - apps/control_plane.py donde aplique fallback/env
2. Cambiar en SMC la etiqueta `quality="high"` para que requiera `rr >= 3.0`.
3. Exponer `min_rr` en Fast API:
   - agregarlo a `FastConfigUpdateRequest`
   - incluirlo en fallback GET de Fast
   - incluirlo en `_FAST_ENV_MAP`
   - validar rango
4. Revisar la politica de spread-adjusted RR en `fast_desk/setup/engine.py` y elegir una:
   - descartar setups si el RR efectivo cae bajo floor, o
   - recalcular TP para preservar RR real
   Documentar la eleccion en comentario corto o test.

VALIDACION FASE 1
- pytest -q tests/fast_desk
- pytest -q tests/smc_desk/test_smc_desk.py
- buscar defaults residuales `min_rr=2.0`

FASE 2 - RIESGO Y CONTRATOS
1. Agregar `max_lot_size` configurable en:
   - fast_desk/risk/engine.py
   - fast_desk/runtime.py
   - apps/control_plane.py
2. Decidir y alinear la politica del cap 2%:
   - si el engine debe aplicarlo, implementar clamp explicito
   - si no, corregir comentario/tests para no afirmar algo falso
3. Reparar `tests/fast_desk/test_fast_desk.py` al contrato real de `calculate_lot_size(symbol_spec, account_state)`.

VALIDACION FASE 2
- pytest -q tests/fast_desk/test_fast_desk.py
- pytest -q tests/fast_desk

FASE 3 - RUNTIME Y OBSERVABILIDAD
1. En `fast_desk/workers/symbol_worker.py`, reemplazar `print(...)` de errores de scan/custody por persistencia/log estructurado usando herramientas ya existentes.
2. Corregir el fallback que intenta construir `FastTraderConfig(max_slippage_points=30)`.
3. Resolver el hot-reload parcial:
   - o reiniciar workers al cambiar config no-contexto
   - o compartir referencias mutables reales
4. Unificar namespace de configuracion canonico en `FAST_TRADER_*` y dejar `FAST_DESK_*` como compat legacy.
5. Evaluar si se desea persistencia pre-ejecucion de senales como `pending`; si se implementa, hacerlo como mejora de trazabilidad, no como supuesto arreglo de perdida actual post-excepcion.

VALIDACION FASE 3
- tests de runtime/env aliases
- pruebas manuales de PUT /api/v1/config/fast

FASE 4 - CALIDAD DE SENAL
1. En `fast_desk/trigger/engine.py`, exigir `confirmed=True` para `micro_choch`.
2. En `fast_desk/setup/engine.py`, agregar filtro de edad al `breakout_retest`.
3. Subir `min_impulse_candles` de Order Blocks a 3.
4. Solo despues, evaluar mejoras a `rejection_candle`.

VALIDACION FASE 4
- pytest -q tests/fast_desk/test_fast_setup_trigger.py
- pytest -q tests/fast_desk

FASE 5 - MEJORAS NO BLOQUEANTES
1. Integrar FVG primero como confluencia en Fast Desk.
2. Reducir recalculo de estructuras compartiendo M1/M5/H1 precalculadas.
3. Revisar `hard_cut_r=1.25` y documentar si es emergency stop o politica regular.

ENTREGABLE FINAL
- codigo actualizado
- tests ejecutados con resultado reportado
- resumen corto de:
  - hallazgos corregidos
  - decisiones tomadas donde habia ambiguedad
  - riesgos que quedan abiertos
```

## 7. Cierre ejecutivo

Los 3 documentos originales apuntaban correctamente al nucleo del problema: el stack todavia no queda bloqueado de extremo a extremo en RR>=3.0. Pero al cotejarlos con el codigo real hubo que corregir dos afirmaciones importantes: la API Fast si conoce `min_rr` a nivel de config runtime aunque no lo gobierna bien, y las excepciones de `send_entry()` no desaparecen silenciosamente porque hoy si terminan en `upsert_fast_signal()` con `outcome="error"`.

La prioridad correcta queda asi: primero RR floor y gobernanza por API, despues riesgo/tests, luego observabilidad y coherencia runtime, y solo entonces mejoras de calidad como FVG o optimizacion de estructuras.
