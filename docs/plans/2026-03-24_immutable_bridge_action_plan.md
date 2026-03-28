# Immutable Action Plan - Heuristic MT5 Bridge

Fecha: 2026-03-24

## Proposito

Este documento fija el plan de accion detallado para completar
`heuristic-metatrader5-bridge` sin degradar su objetivo principal:

- Fast Desk mucho mas agil que la repo anterior
- heuristica fuerte en la ruta critica
- cero LLM en Fast
- SMC lenta, preparada, con tiempo suficiente para tesis, estrategia y entradas
- LLM robusto solo al final de validacion SMC
- soporte real para varias cuentas, brokers e instalaciones MT5
- separacion estricta entre observacion, riesgo, ownership y ejecucion

Este plan debe leerse junto a:

- `docs/ARCHITECTURE.md`
- `docs/audit/2026-03-24_live_bridge_audit.md`
- `docs/prompts/CONNECTOR_CORE_RUNTIME_CONSTRUCTOR.md`
- `docs/prompts/FAST_DESK_CONSTRUCTOR.md`

## Decisiones inalterables

1. Fast Desk no usa LLM.
2. SMC puede usar LLM solo despues de pasar filtros heuristicos.
3. El core sigue siendo RAM-first.
4. No se reintroduce la office stack lenta de la repo vieja en la ruta Fast.
5. La multi-cuenta, multi-broker y multi-instalacion MT5 se mantiene como caso base.
6. `live` significa modo operativo de trading, no tipo de cuenta del broker.
7. El sistema debe poder operar en `paper` sobre charts vivos sin escribir a MT5.
8. La pertenencia de posiciones y ordenes a Fast o SMC es obligatoria y persistente.
9. Las operaciones heredadas o huerfanas deben adoptarse automaticamente.
10. La API del control plane es la unica interfaz externa autorizada.
11. El conector MT5 debe tener una superficie unica y coherente para abrir, modificar, cancelar y cerrar.
12. El control de riesgo de cuenta no puede quedar adentro de un trader de mesa. Debe existir un nucleo global.

## Diagnostico sintetico

Estado actual:

- el core runtime observa MT5 y expone estado correctamente
- la sesion viva muestra mercado, cuenta, posiciones y ordenes
- el bridge heuristico no tiene hoy una interfaz MT5 completa compatible con sus operadores
- Fast Desk existe en arquitectura, pero no esta cerrado de punta a punta
- SMC scanner y analyst existen, pero falta trader real y tramo final a ejecucion
- no existe hoy un Risk Kernel global equivalente al de la repo vieja
- no existe ownership model serio de operaciones
- no existe modo `paper` separado del tipo real/demo de cuenta

## Prioridad inmediata absoluta

Antes de avanzar con traders, ownership o RiskKernel, se debe completar una
etapa formal de:

- cierre de la superficie del conector MT5
- certificacion funcional del conector
- documentacion completa de todas sus capacidades operativas

Sin esa etapa, cualquier trader nuevo o capa de riesgo quedaria montado sobre un
bridge no certificado.

Regla:

- primero se documenta el manual del conector
- luego se ejecuta la matriz completa de pruebas
- recien despues se autoriza construir traders y custody avanzada

## Objetivo operacional final

El sistema terminado debe verse asi:

```text
BridgeSupervisor
  -> TerminalRuntime[terminal_id] x N
      -> MT5ConnectorAdapter
      -> AccountContextManager
      -> MarketStateService
      -> SymbolSpecRegistry
      -> BrokerSessionsService
      -> ExecutionBridge
      -> ExecutionReconciler
      -> OwnershipRegistry
      -> RiskKernel
      -> FastTraderService
      -> SmcScannerService
      -> SmcAnalystService
      -> SmcTraderService
      -> ControlPlane API
```

## Componentes faltantes o incompletos

### 1. MT5 execution surface unificada

Problema actual:

- el Fast Desk espera metodos `place_order`, `close_position`, `modify_position`
- el conector actual expone solo `send_execution_instruction`

Decision:

- crear una superficie unificada de ejecucion dentro de `MT5Connector`
- todos los operadores usan esa superficie
- no se permiten adapters distintos por mesa

Metodos requeridos:

- `send_execution_instruction(instruction)`
- `modify_position_levels(symbol, position_id, stop_loss, take_profit)`
- `modify_order_levels(symbol, order_id, price_open, stop_loss, take_profit)`
- `remove_order(order_id)`
- `close_position(symbol, position_id, side, volume, max_slippage_points=...)`
- `find_open_position_id(symbol, comment)`

Contrato:

- un solo serializer MT5
- request/response tipados
- ids y comentarios consistentes
- mismos retcodes y misma semantica para Fast y SMC

Adicional obligatorio:

- documentar todas las operaciones del conector y sus variantes
- ejecutar una matriz de pruebas para cada operacion soportada

Manual minimo del conector:

- conexion y shutdown
- broker identity
- symbol resolution
- snapshot y tick
- specs y account runtime
- login y probe account
- market order buy/sell
- pending limit buy/sell
- pending stop buy/sell
- modificacion de SL/TP de posicion
- modificacion de orden pendiente
- cancelacion de orden pendiente
- cierre total y parcial de posicion
- localizacion de posicion abierta por comentario
- retcodes esperados y fallos comunes

Nota sobre trailing stop:

- trailing stop no es un metodo nativo separado del conector
- debe documentarse como patron operacional construido sobre llamadas repetidas
  a `modify_position_levels()`

### 2. BridgeSupervisor multi-terminal

Problema actual:

- la arquitectura documenta multi-broker
- pero el runtime real sigue siendo una sola instancia operativa por proceso

Decision:

- introducir `BridgeSupervisor`
- administrar N `TerminalRuntime`
- cada `TerminalRuntime` queda asociado a:
  - `terminal_id`
  - `mt5_installation_id`
  - `broker_server`
  - `account_login`
  - `execution_mode`

Responsabilidades:

- levantar y apagar runtimes por terminal
- detectar cambio de broker/cuenta
- conservar snapshots RAM viejos por TTL
- enrutar API por `terminal_id`

### 3. AccountContextManager con cambio automatico de cuenta

Requisito del producto:

- si el operador cambia de cuenta en un MT5, el motor se adapta automaticamente
- el estado de la cuenta anterior puede quedar en RAM
- no se persiste en DB por ahora como estado vivo
- al reiniciar, solo se reconstruyen cuentas vivas actuales

Decision:

- agregar `AccountContextManager`

Comportamiento:

1. detecta cambio de `broker_server/account_login`
2. congela el contexto anterior en RAM con `ttl`
3. crea un nuevo contexto activo para la nueva cuenta
4. recarga simbolos, specs, posiciones, ordenes y riesgo
5. reatacha traders y registries
6. deja de escribir estado vivo del contexto anterior en DB

Guardas obligatorias:

- un intento de cambio o probe de cuenta con credenciales erradas no puede
  tratarse como operacion inocua
- si la autenticacion falla, el sistema debe asumir riesgo de degradacion de la
  sesion MT5 y de los servicios vivos
- la API debe emitir estado explicito de `terminal_trade_allowed`
- la API debe emitir alerta explicita de `account_switch_disrupted_session`
- la WebUI futura debe exigir confirmacion fuerte antes de probar otra cuenta
- la WebUI futura debe mostrar alerta visible a operadores:
  - "Si la autenticacion falla, MT5 puede perder la sesion o deshabilitar AutoTrading"
- la WebUI futura debe mostrar recuperacion sugerida:
  - "Rehabilitar AutoTrading en MT5 y relanzar servicios si quedaron caidos"

Persistencia:

- DB solo para cuenta activa por runtime
- RAM para snapshots previos mientras dure el proceso

### 4. OwnershipRegistry de operaciones

Problema actual:

- no se sabe formalmente a quien pertenece cada posicion u orden
- no hay separacion robusta Fast vs SMC
- no existe adopcion formal de huerfanas

Decision:

- crear `OwnershipRegistry`
- toda operacion MT5 viva o historica debe tener ownership persistido

Estados minimos:

- `fast_owned`
- `smc_owned`
- `shared_managed`
- `inherited_fast`
- `manual_override`
- `unknown`

Campos minimos:

- `operation_uid`
- `terminal_id`
- `broker_server`
- `account_login`
- `mt5_position_id`
- `mt5_order_id`
- `desk_owner`
- `ownership_status`
- `origin_type`
- `source_signal_id`
- `source_thesis_id`
- `source_trader_intent_id`
- `execution_mode`
- `lifecycle_status`
- `opened_at`
- `closed_at`
- `cancelled_at`
- `retention_until`
- `metadata_json`

Reglas:

- si el sistema arranca y encuentra operaciones no propias, pasan a `inherited_fast`
- la API debe permitir reasignarlas a `smc_owned`
- la API debe permitir marcar si requieren o no reevaluacion al reasignarse
- esa decision debe quedar persistida

### 5. Retencion historica de ownership y lifecycle

No alcanza con `position_cache` y `order_cache`.

Deben persistirse:

- aperturas
- modificaciones
- trailing
- cierres
- cancelaciones
- reasignaciones de mesa
- adopciones de huerfanas

Debe poder configurarse:

- retencion de abiertas
- retencion de cerradas
- retencion de canceladas
- purga por dias

### 6. RiskKernel global y por mesa

Problema actual:

- solo existe un risk gate basico dentro de Fast
- no existe coherencia entre riesgo global y riesgo por mesa

Decision:

- crear `RiskKernel`
- independiente de traders
- expuesto por API
- configurable por env y por API

Debe manejar:

- perfil global `1..4`
- perfil por mesa `fast` y `smc`
- presupuesto dinamico entre mesas
- kill switch global
- kill switch por mesa
- exposure caps
- drawdown caps
- max positions
- max active risk
- adaptacion por modo `live` o `paper`

Perfiles base:

- `1 = low`
- `2 = medium`
- `3 = high`
- `4 = chaos`

Defaults iniciales heredados conceptualmente de la repo vieja:

- low: `max_drawdown=2.0%`, `per_trade=0.30%`, `max_positions=3`
- medium: `max_drawdown=3.5%`, `per_trade=0.50%`, `max_positions=5`
- high: `max_drawdown=5.0%`, `per_trade=0.75%`, `max_positions=10`
- chaos: `max_drawdown=15.0%`, `per_trade=2.0%`, `max_positions=20`

Pero en esta repo no deben aplicarse como reparto 50-50.

Regla de asignacion:

- el perfil global define el maximo absoluto de cuenta
- cada mesa consume presupuesto desde ese total
- aumentar riesgo en una mesa reduce el libre de la otra
- el riesgo global puede forzar recorte simultaneo en ambas
- Fast y SMC tienen pesos distintos, no simetricos

Modelo recomendado:

- `global_budget`
- `fast_budget_weight`
- `smc_budget_weight`
- `fast_max_active_risk`
- `smc_max_active_risk`

### 7. FastTraderService real

Problema actual:

- hay scanner, policy, risk y custodian parciales
- falta un trader fast profesional equivalente funcional a un `live_execution_trader`

Decision:

- introducir `FastTraderService`
- separarlo de `FastScannerService`

Capacidades requeridas:

- abrir nuevas entradas fast
- custodiar posiciones fast
- custodiar posiciones heredadas asignadas a Fast
- gestionar pending orders fast
- mover SL a BE
- trailing dinamico
- scale-out parcial opcional
- hard loss cut
- spread gate
- slippage gate
- session gate
- no passive underwater
- reconciliacion con MT5

Debe ser mas agresivo y profesional que el `live_execution_trader` viejo, pero no menos seguro.

### 8. SmcTraderService real

Problema actual:

- existe scanner/analyst/validator
- no existe trader SMC real en esta repo

Decision:

- agregar `SmcTraderService`

Capacidades requeridas:

- leer tesis SMC validadas
- convertir candidatos en planes de ejecucion
- emitir market, limit o stop segun tesis
- gestionar pending orders SMC
- reevaluar segun invalidez de tesis
- custodiar posiciones SMC de forma mas lenta y deliberada
- permitir reevaluacion manual o por API

### 9. ExecutionReconciler

Componente nuevo obligatorio.

Responsabilidades:

- reconciliar intenciones locales con estado real MT5
- detectar fills parciales
- detectar cierres manuales
- detectar SL/TP modificados fuera del sistema
- detectar ordenes pendientes desaparecidas
- actualizar ownership y lifecycle
- disparar reevaluacion de trader o riesgo

Sin esto no hay coherencia entre runtime y broker.

### 10. ExecutionMode split: live vs paper

Decision de producto:

- `live` significa operar
- no significa cuenta real

Decision tecnica:

- separar `execution_mode` de `account_mode`

Campos:

- `execution_mode = live | paper`
- `account_mode = demo | real | contest | unknown`

Comportamiento:

- `paper`: traders y riesgo corren igual, pero las ordenes van a `PaperExecutionEngine`
- `live`: las ordenes van a `MT5Connector`
- la UI futura puede mostrar simulacion sobre charts vivos

### 11. API para riesgo, ownership y modo operativo

Faltan endpoints explicitamente operativos.

Endpoints minimos:

- `GET /terminals`
- `GET /terminals/{terminal_id}/status`
- `GET /terminals/{terminal_id}/risk/status`
- `PUT /terminals/{terminal_id}/risk/profile`
- `PUT /terminals/{terminal_id}/risk/allocations`
- `POST /terminals/{terminal_id}/risk/kill-switch/trip`
- `POST /terminals/{terminal_id}/risk/kill-switch/reset`
- `GET /terminals/{terminal_id}/operations`
- `GET /terminals/{terminal_id}/operations/{operation_uid}`
- `POST /terminals/{terminal_id}/operations/{operation_uid}/assign`
- `POST /terminals/{terminal_id}/operations/{operation_uid}/re-evaluate`
- `PUT /terminals/{terminal_id}/execution/mode`
- `GET /terminals/{terminal_id}/desks/fast/status`
- `GET /terminals/{terminal_id}/desks/smc/status`

### 12. Operability and observability

Faltan estados visibles y alarmas.

Deben exponerse:

- salud del connector
- health por terminal
- health por trader
- ultimo evento de reconciliacion
- ultimo fallo de orden
- ultimo kill switch
- presupuesto de riesgo actual
- cantidad de huerfanas adoptadas
- cantidad de overrides manuales

### 13. Test harness serio

Faltan pruebas de:

- apertura real abstracta
- modificacion de posicion
- modificacion de orden
- cierre
- cancelacion
- adopcion de huerfanas
- reasignacion Fast -> SMC
- cambio automatico de cuenta
- paper mode
- budget allocator de riesgo
- reconciliacion ante cierres manuales

## Variables de entorno a introducir o redefinir

### Runtime global

- `BRIDGE_SUPERVISOR_ENABLED`
- `BRIDGE_TERMINALS_CONFIG`
- `TERMINAL_CONTEXT_RAM_TTL_SECONDS`
- `EXECUTION_MODE_DEFAULT=live|paper`

### RiskKernel

- `RISK_PROFILE_GLOBAL=1|2|3|4`
- `RISK_PROFILE_FAST=1|2|3|4`
- `RISK_PROFILE_SMC=1|2|3|4`
- `RISK_GLOBAL_MAX_DRAWDOWN_PCT`
- `RISK_FAST_MAX_ACTIVE_RISK_PCT`
- `RISK_SMC_MAX_ACTIVE_RISK_PCT`
- `RISK_FAST_BUDGET_WEIGHT`
- `RISK_SMC_BUDGET_WEIGHT`
- `RISK_KILL_SWITCH_ENABLED`
- `RISK_REALTIME_GUARD_INTERVAL`

### Ownership

- `OWNERSHIP_AUTO_ADOPT_ORPHANS=true`
- `OWNERSHIP_DEFAULT_ORPHAN_DESK=fast`
- `OWNERSHIP_HISTORY_RETENTION_DAYS_OPEN`
- `OWNERSHIP_HISTORY_RETENTION_DAYS_CLOSED`
- `OWNERSHIP_HISTORY_RETENTION_DAYS_CANCELLED`

### Traders

- `FAST_TRADER_ENABLED`
- `FAST_TRADER_GUARD_INTERVAL`
- `FAST_TRADER_SPREAD_MAX_PIPS`
- `FAST_TRADER_MAX_SLIPPAGE_POINTS`
- `SMC_TRADER_ENABLED`
- `SMC_TRADER_GUARD_INTERVAL`
- `SMC_TRADER_REEVALUATION_DEFAULT=true`

## Nuevas tablas o familias de tablas

### Operational ownership

- `operation_registry`
- `operation_assignment_log`
- `operation_lifecycle_log`

### Risk

- `risk_profile_state`
- `risk_budget_state`
- `risk_events_log`
- `kill_switch_log`

### Execution

- `execution_intent_log`
- `execution_reconcile_log`

### Future paper mode

- `paper_position_registry`
- `paper_order_registry`
- `paper_trade_log`

## Fases de implementacion

### Phase 0 - Connector manual and certification

Objetivo:

- convertir el conector en un componente certificado y documentado

Tareas:

- cerrar metodos faltantes
- escribir el manual del conector
- definir la matriz de pruebas
- probar todas las operaciones soportadas en `paper` y en `live` controlado
- documentar retcodes, restricciones y precondiciones

Cobertura minima:

- open market buy/sell
- open pending limit buy/sell
- open pending stop buy/sell
- close full
- close partial
- modify position SL only
- modify position TP only
- modify position SL+TP
- modify order price only
- modify order SL only
- modify order TP only
- modify order full
- remove pending order
- trailing stop as repeated modify
- login/probe account
- symbol resolution broker-aware

Aceptacion:

- todo metodo soportado tiene prueba y documentacion
- no queda ninguna capacidad del conector sin manual
- Fast y SMC ya pueden depender del bridge sin ambiguedad

### Phase 1 - Canonical contracts

Objetivo:

- cerrar contratos antes de tocar runtime

Entregables:

- spec de `MT5Connector` unificado
- spec de `execution_mode`
- spec de `ownership_status`
- spec de `risk profile`
- spec de `terminal_id`

### Phase 2 - MT5 bridge closure

Objetivo:

- cerrar la superficie MT5 faltante

Tareas:

- agregar modify/cancel/close/find
- normalizar respuestas
- reemplazar llamadas incompatibles del Fast Desk
- agregar tests de bridge

Aceptacion:

- Fast y SMC llaman la misma API de conector
- no quedan metodos fantasma

### Phase 3 - OwnershipRegistry + adoption

Objetivo:

- saber de quien es cada operacion

Tareas:

- crear tablas y CRUD
- adopcion automatica de huerfanas a Fast
- API de reasignacion
- retention policy

Aceptacion:

- toda posicion u orden visible tiene owner
- una huerfana nunca queda en `unknown` mas de un ciclo

### Phase 4 - RiskKernel

Objetivo:

- centralizar riesgo global y por mesa

Tareas:

- perfiles `1..4`
- allocator dinamico
- kill switch
- API de lectura y escritura
- exposure limits

Aceptacion:

- cambiar riesgo Fast reduce presupuesto libre SMC
- kill switch global frena entradas y puede forzar reducciones

### Phase 5 - FastTraderService

Objetivo:

- hacer realmente operativa la mesa Fast

Tareas:

- separar scanner y trader
- custodia real
- pending orders fast
- guardas de spread/slippage/session
- reconciliacion con ownership y risk

Aceptacion:

- puede abrir
- puede custodiar
- puede cerrar
- puede adoptar
- queda audit trail en DB

### Phase 6 - SmcTraderService

Objetivo:

- completar la cadena thesis -> order

Tareas:

- trader SMC
- pending logic
- reevaluacion lenta
- API manual para recheck y reasignacion

Aceptacion:

- una tesis SMC valida puede convertirse en operacion real o paper

### Phase 7 - BridgeSupervisor multi-terminal

Objetivo:

- soportar varias instalaciones y cuentas sin degradar arquitectura

Tareas:

- supervisor de runtimes
- account switch RAM retention
- API por `terminal_id`

Aceptacion:

- dos terminales paralelos sin contaminacion
- cambio de cuenta sin reinicio manual

### Phase 8 - Paper mode and future UI hooks

Objetivo:

- permitir simulacion operativa sobre charts vivos

Tareas:

- `PaperExecutionEngine`
- mismas decisiones, distinta salida
- endpoints preparados para sliders y reasignacion

Aceptacion:

- una orden puede ejecutarse en live o paper sin cambiar traders

## Criterios de aceptacion globales

1. Ninguna mesa llama metodos MT5 inexistentes.
2. Toda orden y posicion tiene owner persistido.
3. Toda huerfana se adopta automaticamente a Fast al arrancar.
4. La API permite reasignar ownership a SMC.
5. El riesgo global y por mesa es visible y modificable por API.
6. `live` y `paper` ya no significan demo vs real.
7. La cuenta anterior puede quedarse en RAM luego de un switch de cuenta.
8. El reinicio reconstruye solo cuentas vivas actuales.
9. Fast puede abrir, custodiar y cerrar de forma real.
10. SMC puede emitir ordenes desde tesis confirmadas.
11. Multi-terminal funciona sin contaminacion entre brokers/cuentas.
12. Todo queda auditado en SQLite con retencion configurable.

## Cosas que faltaban recordar

Ademas de lo ya mencionado por producto, todavia faltan estas piezas:

- reconciliacion activa contra MT5
- idempotencia de ejecucion para evitar doble envio
- tratamiento de fills parciales
- tratamiento de cierres o modificaciones manuales fuera del sistema
- session/spread/slippage gates explicitos por trader
- `paper mode` desacoplado del tipo de cuenta
- `BridgeSupervisor` multi-terminal real
- API de ownership y overrides manuales
- retention policy completa para lifecycle de operaciones
- tests de account switch y de huerfanas
- eventos de riesgo y kill switch visibles
- criterio profesional de custody para Fast superior al `live_execution_trader` viejo

## Lo que no debe importarse de la repo vieja

- chairman
- supervisor conversacional en la ruta Fast
- memory curator como dependencia operativa
- cola lenta de mensajes como bus de ejecucion
- decisiones LLM en la ruta critica de scalping

## Nota final

La repo vieja sirve como banco de herramientas MT5 y como referencia de:

- risk profiles
- ownership/orphan adoption
- execution bridge
- live custody

Pero esta repo nueva no debe copiar su arquitectura social.

Debe absorber solo:

- el bridge real de MT5
- la disciplina de ownership
- la disciplina de riesgo
- la disciplina de custodia

Y reconstruir todo lo demas como sistema heuristico rapido, RAM-first y multi-terminal.
