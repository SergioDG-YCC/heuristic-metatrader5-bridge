# WebUI Architecture

Fecha: 2026-03-24

## Proposito

Este documento enumera la documentacion que un constructor de WebUI debe leer
para no perder hallazgos importantes entre auditorias, planes y prompts.

La WebUI de esta repo no es una app decorativa.

Debe ser una interfaz operativa sobre el `control plane`, con alertas reales,
restricciones reales y conocimiento explicito de los riesgos del bridge MT5.

## Regla principal

La WebUI no debe hablar directo con SQLite ni con MT5.

La unica interfaz externa autorizada es la API del `control plane`.

## Orden de lectura recomendado

### 1. Autoridad arquitectonica base

1. [ARCHITECTURE.md](./ARCHITECTURE.md)
   - arquitectura canónica
   - modelo RAM-first
   - `control plane` como unica interfaz
   - restricciones de persistencia
   - principios para WebUI

2. [2026-03-24_immutable_bridge_action_plan.md](./plans/2026-03-24_immutable_bridge_action_plan.md)
   - plan canonico del sistema objetivo
   - componentes faltantes
   - ownership, risk kernel, execution mode, multi-terminal
   - hooks futuros para UI

### 2. Estado real del sistema hoy

3. [2026-03-24_live_bridge_audit.md](./audit/2026-03-24_live_bridge_audit.md)
   - que esta realmente vivo
   - que todavia no esta cableado
   - diferencia entre repo heuristica y repo vieja

4. [2026-03-24_mt5_official_surface_inventory.md](./audit/2026-03-24_mt5_official_surface_inventory.md)
   - superficie oficial MT5
   - traduccion obligatoria a superficie de bridge
   - gaps actuales del connector heuristico
   - hallazgos empiricos del broker actual

5. [2026-03-24_connector_certification_execution_report.md](./audit/2026-03-24_connector_certification_execution_report.md)
   - evidencia real de pruebas
   - comandos ejecutados
   - que ya paso
   - que solo funciona con `comment=""`
   - riesgo operativo del cambio/probe de cuenta
   - mensaje de alerta requerido para operadores y WebUI

### 3. Documentos clave para contratos UI-backend

6. [2026-03-24_connector_certification_plan.md](./plans/2026-03-24_connector_certification_plan.md)
   - matriz de pruebas obligatoria
   - superficie minima del connector
   - reglas para cambio de cuenta y seguridad operativa

7. [2026-03-23_mt5_data_ownership_boundary.md](./plans/2026-03-23_mt5_data_ownership_boundary.md)
   - boundary de datos entre MT5, Python, MQL5 y UI
   - como debe funcionar la WebUI
   - pasos manuales que deben quedar visibles en UI

8. [2026-03-23_chart_ram_runtime_architecture.md](./plans/2026-03-23_chart_ram_runtime_architecture.md)
   - chart RAM
   - universos
   - politica de suscripcion
   - acceso live futuro para UI

### 4. Prompts y constructores relevantes

9. [CONNECTOR_CORE_RUNTIME_CONSTRUCTOR.md](./prompts/CONNECTOR_CORE_RUNTIME_CONSTRUCTOR.md)
   - contexto del backbone actual
   - contratos del runtime y `control plane`

10. [FAST_DESK_CONSTRUCTOR.md](./prompts/FAST_DESK_CONSTRUCTOR.md)
    - expectativas del Fast Desk
    - dependencia directa del connector para ejecucion y custodia

11. [SMC_DESK_MULTIMODAL_CONSTRUCTOR.md](./prompts/SMC_DESK_MULTIMODAL_CONSTRUCTOR.md)
    - contexto del desk SMC
    - thesis, validacion y dependencia futura de ownership/risk

12. [CONNECTOR_EXECUTION_SURFACE_CONSTRUCTOR.md](./prompts/CONNECTOR_EXECUTION_SURFACE_CONSTRUCTOR.md)
    - prompt originario de cierre del connector
    - la superficie ya esta implementada y certificada en `[0.2.1]`
    - referencia util para entender restricciones del broker (comment mode, probe risk)

## Lo que la WebUI debe asumir como verdadero hoy

### 1. Estado live

- el `control plane` es la fuente de verdad externa
- la UI no debe asumir que un desk esta operativo solo porque exista en docs
- la UI debe distinguir:
  - backend observado
  - backend cableado
  - backend certificado

### 2. Superficie de ejecucion MT5 (CERRADA en 0.2.1)

El connector ahora expone la superficie completa de ejecucion:

| Metodo | Accion |
|--------|--------|
| `send_execution_instruction` | abrir posicion (market/limit/stop) |
| `modify_position_levels` | modificar SL/TP de posicion abierta |
| `modify_order_levels` | modificar precio/SL/TP de orden pendiente |
| `remove_order` | cancelar orden pendiente |
| `close_position` | cerrar posicion (total o parcial) |
| `find_open_position_id` | buscar posicion por comentario exacto |

Cada metodo de escritura ejecuta primero `_ensure_trading_available()`:
- verifica `account_info()` disponible
- verifica `terminal_info()` disponible
- verifica `trade_allowed=True`
- aplica guard `ACCOUNT_MODE`

**La UI puede y debe exponer el estado de `trade_allowed` como indicador prioritario.**
Si `trade_allowed=False`, todos los botones de ejecucion deben bloquearse y mostrar
la alerta de recuperacion (re-habilitar AutoTrading en el terminal MT5).

### 3. Riesgo y ownership

- el ownership formal Fast/SMC todavia no esta terminado (`OwnershipRegistry` pendiente)
- el risk kernel global todavia no existe
- la UI no debe vender controles inexistentes como si fueran reales

### 4. Cambio de cuenta

- un `probe_account()` o cambio de cuenta fallido puede:
  - degradar la sesion MT5
  - deshabilitar `AutoTrading`
  - bajar servicios vivos
- la UI debe tratarlo como operacion peligrosa
- la UI debe exigir confirmacion fuerte
- la UI debe mostrar recuperacion operativa sugerida

### 5. Comentarios de orden

- certificacion confirmo: en este broker la ejecucion funciona con `comment=""`
- con comentario poblado el broker puede rechazar (`Invalid "comment" argument`)
- `find_open_position_id` existe y funciona cuando el broker permite comentarios
- ownership formal por comentario requiere `OwnershipRegistry` (fase siguiente)
- la UI no debe asumir ownership completo por comentario hasta que el backend lo cierre

## Pantallas o dominios de UI que dependen de esta documentacion

### Operacion live

- estado de terminal y cuenta
- estado de `trade_allowed` (CRITICO: bloquea toda escritura si es False)
- estado de `execution_mode`
- posiciones, ordenes, exposicion
- estado de Fast y SMC por runtime
- botones de cierre/modificacion de posicion (disponibles, el backend ahora los soporta)

### Riesgo y ownership

- perfil de riesgo global y por mesa
- adopcion de heredadas
- reasignacion Fast/SMC
- overrides y kill switch

### Cambio de cuenta / terminal

- selector de terminal
- broker y cuenta activa
- historial RAM de contextos congelados
- alertas de sesion degradada

### Recuperacion operativa

- alerta visible si `trade_allowed=false`
- alerta visible si falla autenticacion
- instruccion visible para re-habilitar `AutoTrading`
- instruccion visible para relanzar `apps/control_plane.py`

## Requisitos de UX no negociables

- no ocultar estados degradados
- no mezclar `account_mode` con `execution_mode`
- no permitir acciones destructivas sin confirmacion
- no mostrar botones de ownership/risk si el backend no los soporta todavia
- no asumir multi-cuenta segura hasta que backend cierre la ruta no disruptiva

## Resumen para constructores

Si un constructor de WebUI lee un solo documento, va a cometer errores.

Debe leer, como minimo:

1. `docs/ARCHITECTURE.md`
2. `docs/plans/2026-03-24_immutable_bridge_action_plan.md`
3. `docs/audit/2026-03-24_connector_certification_execution_report.md`
4. `docs/audit/2026-03-24_mt5_official_surface_inventory.md`
5. `docs/prompts/CONNECTOR_EXECUTION_SURFACE_CONSTRUCTOR.md`

**Estado de superficie backend a la fecha (2026-03-24):**

| Componente | Estado |
|---|---|
| Control Plane HTTP | ✅ operativo |
| MT5Connector — lectura | ✅ certificado |
| MT5Connector — escritura (5 metodos) | ✅ cerrado en 0.2.1 |
| Fast Desk execution (bridge canonico) | ✅ alineado en 0.2.1 |
| Fast Desk preflight (`trade_allowed`) | ✅ activo en 0.2.1 |
| OwnershipRegistry | ⏳ pendiente |
| RiskKernel (global + por desk) | ⏳ pendiente |
| FastTraderService (ejecucion real) | ⏳ pendiente |
| SmcTraderService | ⏳ pendiente |
| BridgeSupervisor (multi-terminal) | ⏳ pendiente |
| Paper mode | ⏳ pendiente |
