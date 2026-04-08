# Auditoria tecnica viva - heuristic vs llm bridge

Fecha de auditoria: 2026-03-24

## Alcance

Se audito:

- documentacion y codigo de `heuristic-metatrader5-bridge`
- proceso vivo iniciado con `.\.venv\Scripts\python.exe apps/control_plane.py`
- estado observable por HTTP en `http://127.0.0.1:8765/status`
- SQLite viva en `storage/runtime.db`
- contraste con la repo anterior `llm-metatrader5-bridge`

No se modifico codigo. Solo se inspecciono runtime, DB y fuentes.

## Resumen ejecutivo

Conclusiones principales:

1. El `core runtime` de la repo heuristica esta vivo y funcional para observacion:
   - conecta a MT5
   - refresca mercado y cuenta en tiempo real
   - expone estado por FastAPI
   - mantiene `position_cache` y `order_cache`

2. El `Fast Desk` heuristico no esta cableado de punta a punta para operar:
   - su worker y su custodia existen
   - pero `FastExecutionBridge` llama `connector.place_order()`, `connector.close_position()` y `connector.modify_position()`
   - esos metodos no existen en `MT5Connector` de esta repo
   - por lo tanto, cuando el Fast Desk necesite abrir/cerrar/modificar de verdad, va a fallar por interface incompleta

3. La `SMC Desk` heuristica tampoco esta operando en esta sesion:
   - existen scanner, analyst y validator
   - no existe un `smc trader` real en esta repo
   - no hay emision de ordenes desde tesis SMC
   - en la DB viva no aparecieron `smc_zones`, `smc_events_log` ni `smc_thesis_cache`

4. Las posiciones y la orden pendiente hoy visibles en MT5 no parecen originadas por la repo heuristica:
   - sus comentarios llevan formato `ti:<id>|ex:<id>`
   - ese formato coincide exactamente con `python/execution_bridge.py` de la repo vieja
   - la DB de `llm-metatrader5-bridge` tiene `execution_event_cache` que coincide con esos ids y timestamps

5. La repo vieja si tenia el bridge completo de ejecucion y custodia:
   - enviar orden
   - modificar SL/TP de posicion
   - modificar orden pendiente
   - remover orden pendiente
   - cerrar posicion
   - trailing/cancel/close desde `live_execution_trader`
   - aprobacion y kill-switch desde `risk_manager`

## Evidencia del runtime heuristico vivo

### Proceso y endpoint

- El proceso vivo es `apps/control_plane.py`
- El puerto `8765` esta escuchando
- `GET /status` devuelve:
  - `status=up`
  - `mt5_connector=up`
  - `market_state=up`
  - `broker_sessions=up`
  - `indicator_bridge=waiting_first_snapshot`
  - 5 simbolos suscriptos
  - 5 posiciones abiertas
  - 1 orden pendiente

### Flags activas en `.env`

En la sesion viva quedaron activados:

- `FAST_DESK_ENABLED=true`
- `SMC_SCANNER_ENABLED=true`
- `SMC_LLM_ENABLED=true`
- `BROKER_SESSIONS_ENABLED=true`
- `INDICATOR_ENRICHMENT_ENABLED=true`
- `ACCOUNT_MODE=live`

Observacion importante:

- el runtime vivo reporta cuenta `demo`
- pero `.env` dice `ACCOUNT_MODE=live`
- en ambas repos, cuando `ACCOUNT_MODE=live`, el guard rail deja de exigir que la cuenta sea demo
- eso reduce proteccion operativa contra ejecucion accidental fuera de demo

### DB viva de la repo heuristica

Conteos observados en `storage/runtime.db`:

- `position_cache`: 5
- `order_cache`: 1
- `fast_desk_signals`: 0
- `fast_desk_trade_log`: 0
- `smc_zones`: 0
- `smc_events_log`: 0
- `smc_thesis_cache`: 0

Interpretacion:

- el core observa y persiste la cuenta
- pero no hay evidencia de que Fast Desk o SMC Desk hayan producido actividad propia en esta corrida

## Repo heuristica: que si funciona

### 1. Core runtime y control plane

Implementado y operativo:

- `apps/control_plane.py`
- `src/heuristic_mt5_bridge/core/runtime/service.py`
- `src/heuristic_mt5_bridge/infra/mt5/connector.py`
- `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`

Capacidades verificadas:

- bootstrap MT5
- lectura de snapshots OHLC
- carga de specs
- refresco de cuenta, posiciones y ordenes
- `GET /status`
- `GET /chart/{symbol}/{timeframe}`
- `GET /positions`
- `GET /account`
- `GET /exposure`
- `GET /catalog`
- suscripcion de simbolos

### 2. Broker sessions

En esta sesion si estan conectadas:

- el `broker_session_registry` esta `running=true`
- no hay `pending_symbols`
- hay grupos de sesion cargados para los simbolos activos

Esto contradice la auditoria anterior del 2026-03-23, que ya quedo desactualizada.

## Repo heuristica: que no esta realmente cableado

### 1. Fast Desk: arquitectura presente, ejecucion incompleta

Archivos relevantes:

- `src/heuristic_mt5_bridge/fast_desk/runtime.py`
- `src/heuristic_mt5_bridge/fast_desk/workers/symbol_worker.py`
- `src/heuristic_mt5_bridge/fast_desk/execution/bridge.py`
- `src/heuristic_mt5_bridge/infra/mt5/connector.py`

Hallazgo central:

- `FastExecutionBridge.open_position()` llama `connector.place_order()`
- `FastExecutionBridge.apply_custody()` llama `connector.close_position()` y `connector.modify_position()`
- el `MT5Connector` de esta repo solo expone `send_execution_instruction()`
- no expone `place_order()`
- no expone `close_position()`
- no expone `modify_position()`

Implicancia:

- el Fast Desk puede escanear
- puede calcular riesgo
- puede decidir
- pero no tiene superficie MT5 compatible para materializar la decision

Corolario:

- hoy no hay evidencia en DB de `fast_desk_signals` ni `fast_desk_trade_log`
- pero aun si apareciera una señal, la ruta de ejecucion real esta rota por incompatibilidad de interface

### 2. Custodia heuristica de posiciones

El `FastSymbolWorker` recorre todas las posiciones del simbolo y el `FastCustodian` decide:

- `trail_sl`
- `close`
- `hold`

Eso significa que en teoria intentaria cuidar cualquier posicion del simbolo, incluso heredada.

Pero en la practica:

- no hay modelo de ownership
- no distingue operaciones del bridge heuristico vs operaciones heredadas
- y cuando deba actuar, hoy no tiene metodos MT5 validos para ejecutar la accion

Conclusion:

- no hay un custodio heuristico confiable y probado para la cuenta viva

### 3. Riesgo de cuenta en la repo heuristica

Existe:

- `FastRiskEngine.calculate_lot_size()`
- `FastRiskEngine.check_account_safe()`

Eso solo cubre:

- sizing por trade
- cap de 2%
- bloqueo por drawdown simple antes de abrir

No existe en esta repo un equivalente real de:

- `risk_manager_runtime.py`
- kill-switch operativo
- re-evaluacion de exposicion abierta
- cierre forzoso por postura de riesgo
- adopcion de operaciones heredadas

Conclusion:

- la repo heuristica no tiene hoy un controlador de riesgo de cuenta al nivel de la repo vieja

### 4. SMC Desk: analiza, pero no opera

Archivos relevantes:

- `src/heuristic_mt5_bridge/smc_desk/runtime.py`
- `src/heuristic_mt5_bridge/smc_desk/scanner/scanner.py`
- `src/heuristic_mt5_bridge/smc_desk/analyst/heuristic_analyst.py`
- `src/heuristic_mt5_bridge/smc_desk/llm/validator.py`
- `src/heuristic_mt5_bridge/smc_desk/trader/__init__.py`

Situacion real:

- hay scanner heuristico
- hay analyst heuristico
- hay validator heuristico
- hay validator LLM opcional
- no hay trader SMC implementado
- el paquete `smc_desk/trader/` esta vacio a efectos practicos

Ademas, en la corrida viva:

- `smc_zones = 0`
- `smc_events_log = 0`
- `smc_thesis_cache = 0`

Conclusion:

- la SMC Desk no esta produciendo tesis ni emitiendo ordenes en esta sesion
- y aunque produjera tesis, no existe el tramo final para mandar orden a MT5

## Repo vieja: el bridge MT5 si estaba completo

### Superficie MT5 disponible

En `llm-metatrader5-bridge/python/mt5_connector.py` existen estos metodos:

- `send_execution_instruction()`
- `modify_position_levels()`
- `modify_order_levels()`
- `remove_order()`
- `close_position()`

Eso cubre:

- abrir market y pending orders
- ajustar SL/TP post-fill
- modificar pendientes
- cancelar pendientes
- cerrar posiciones

### Bridge de ejecucion real

En `llm-metatrader5-bridge/python/execution_bridge.py`:

- `build_execution_instruction()` construye la instruccion
- usa comentario `ti:<trader_ref>|ex:<execution_ref>`
- `submit_new_executions()` manda la orden a MT5
- `apply_post_fill_levels()` fija SL/TP post-fill
- `maintain_trailing_stops()` recalcula trailing
- `cancel_expired_orders()` remueve pendientes vencidas

Esa cadena si esta cableada de punta a punta.

### Trader y riesgo en la repo vieja

Cadena funcional:

- trader o smc trader genera `trader_intent`
- `risk_manager_runtime.py` aprueba / limita / rechaza
- `execution_bridge.py` ejecuta en MT5
- `live_execution_trader_runtime.py` vigila y ajusta operaciones vivas

Roles claros:

- `risk_manager` controla aprobacion, sizing y `kill_switch_state`
- `live_execution_trader` controla proteccion, trailing, cancelacion y cierre

### Operaciones heredadas / abiertas previamente

La repo vieja si tenia logica explicita para esto:

- `analysis_input_builder.py` reconstruye `operation_origin`
- clasifica `ownership_status` como `linked`, `reconstructed` u `orphaned`
- computa `inherited_position_count` e `inherited_order_count`
- `live_execution_trader_runtime.py` revisa exposicion heredada y puede:
  - `add_protection`
  - `tighten_stop`
  - `enable_trailing_stop`
  - `cancel_order`
  - `close_position`
  - `reduce_position`

Entonces la respuesta para la repo vieja es:

- si, habia alguien cuidando operaciones abiertas previamente
- incluso cuando no estuvieran perfectamente ligadas al chat original

## Correlacion de las operaciones vivas actuales con la repo vieja

Hallazgo fuerte:

- las posiciones abiertas hoy en MT5 tienen comentarios como `ti:f8b0ea45|ex:f`
- ese formato coincide exactamente con `execution_bridge.py` de la repo vieja
- la DB vieja contiene `execution_event_cache` consistentes con esos ids

Ejemplos observados en la DB vieja:

- `EURUSD` filled en `2026-03-24T02:29:55Z`
- `EURUSD` filled en `2026-03-24T02:36:44Z`
- `EURUSD` filled en `2026-03-24T02:46:51Z`
- `GBPUSD` filled en `2026-03-24T02:50:38Z`
- `BTCUSD` pending `placed` en `2026-03-24T02:48:39Z`

Tambien aparecen acciones de custodia en la repo vieja:

- `add_protection`
- `tighten_stop`
- `enable_trailing_stop`
- `close_position`

Por lo tanto:

- las operaciones visibles hoy fueron abiertas por la stack vieja o por componentes que reutilizan su protocolo
- no hay evidencia de que hayan sido emitidas por el Fast Desk heuristico actual

## Respuestas directas a las preguntas operativas

### Estan funcionales los operadores en la repo heuristica?

Parcialmente:

- funcional el operador de observacion del core
- no funcional de punta a punta el operador Fast para ejecucion
- no funcional de punta a punta el operador SMC para trading

### Pueden operar directo?

Hoy no de forma confiable.

El Fast Desk tiene decision y riesgo, pero no tiene interfaz MT5 completa compatible. La SMC Desk no tiene trader/execution final.

### Pueden emitir ordenes?

La repo heuristica tiene `send_execution_instruction()` en el conector, pero sus operadores actuales no usan correctamente esa superficie.

La repo vieja si emitia ordenes reales.

### Existe un trader heuristico que cuide real-time las posiciones emitidas?

No al nivel robusto de la repo vieja.

Existe un `FastCustodian`, pero:

- no tiene ownership model
- no tiene kill switch
- no tiene capa de review operativa
- depende de metodos MT5 ausentes en el conector actual

### Quien controla el riesgo de la cuenta?

En la repo heuristica:

- solo un gate simple previo a entrada dentro de `FastRiskEngine`

En la repo vieja:

- `risk_manager_runtime.py`
- `kill_switch_state`
- aprobacion operativa
- guidance de ejecucion
- y `live_execution_trader_runtime.py` para enforcement sobre exposicion viva

### Si hay operaciones abiertas previamente en MT5, alguien las cuida?

En la repo heuristica actual:

- no encontre una capa equivalente a la de la repo vieja
- el Fast Desk podria llegar a verlas por simbolo
- pero no hay ownership ni bridge de custodia confiable

En la repo vieja:

- si, explicitamente

## Diferencia gruesa entre ambas repos

### Repo vieja `llm-metatrader5-bridge`

Modelo completo de oficina:

- chairman / trader / supervisor / risk
- execution bridge real
- live execution trader para custodiar exposicion viva
- reconstruccion de ownership y gestion de operaciones heredadas

### Repo nueva `heuristic-metatrader5-bridge`

Modelo corregido hacia:

- core RAM-first correcto
- control plane HTTP funcional
- Fast Desk heuristico de baja latencia
- SMC scanner/analyst heuristico con LLM opcional

Pero el recorte dejo incompleto:

- el bridge de ejecucion del Fast Desk
- la custodia real MT5
- la capa de riesgo operativa de cuenta
- el trader SMC final

## Veredicto actual

Como bridge operativo en vivo:

- `heuristic-metatrader5-bridge` hoy sirve como core observador y base arquitectonica
- no lo considero todavia un reemplazo funcional completo de la ruta de trading de la repo vieja

Para decir que la repo heuristica ya reemplaza a la vieja, faltaria como minimo:

1. cerrar la interfaz de ejecucion MT5 del Fast Desk
2. agregar custodia real compatible con MT5
3. decidir si la cuenta tendra risk manager separado o un equivalente heuristico serio
4. definir quien adopta y cuida exposicion heredada
5. implementar el tramo `SMC thesis -> trader intent -> execution` o declararlo fuera de alcance

## Preguntas abiertas necesarias

1. Hubo otra automatizacion o intervencion manual en MT5 despues de `2026-03-24T02:50:40Z`?
   - La foto actual de MT5 no coincide exactamente con la ultima `position_cache` de la repo vieja para al menos una operacion.

2. Queres que inspeccione tambien los logs/journals del terminal MT5 para atribuir quien modifico las posiciones despues de que la repo vieja dejo de escribir en su DB?

3. Queres que en la siguiente pasada baje al detalle por mesa:
   - `Fast Desk`: señales, sizing, thresholds, fail modes
   - `SMC Desk`: por que hoy no genero ni zonas ni tesis en esta sesion viva
