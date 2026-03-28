# Connector Certification Plan

Fecha: 2026-03-24

## Proposito

Definir la campana obligatoria de cierre, prueba y documentacion del conector
MT5 antes de continuar con traders, ownership o gestion de riesgo avanzada.

Antes de redactar el manual propio del conector hay que:

- fijar la superficie oficial MT5 desde documentacion primaria
- enumerar las funciones realmente necesarias para este stack
- correr la campana live sobre cuenta demo
- guardar evidencia suficiente por caso

Este documento es previo a la implementacion de:

- `FastTraderService`
- `SmcTraderService`
- `RiskKernel`
- `ExecutionReconciler`

## Principio rector

Ningun trader nuevo debe operar sobre un conector cuya superficie no este:

- completa
- probada
- documentada
- observada en runtime real

## Superficie minima a certificar

### Observacion

- `connect()`
- `shutdown()`
- `broker_identity()`
- `ensure_symbol()`
- `fetch_snapshot()`
- `fetch_symbol_specification()`
- `fetch_available_symbol_catalog()`
- `fetch_account_runtime()`
- `symbol_tick()`
- `login()`
- `probe_account()`

### Ejecucion

- `send_execution_instruction()` para:
  - `market buy`
  - `market sell`
  - `limit buy`
  - `limit sell`
  - `stop buy`
  - `stop sell`
- `modify_position_levels()`
- `modify_order_levels()`
- `remove_order()`
- `close_position()`
- `find_open_position_id()`

### Patrones operativos construidos sobre el conector

- trailing stop por secuencia de `modify_position_levels()`
- post-fill SL/TP
- cancelacion por vencimiento
- cierre parcial
- adopcion de posicion heredada y primer ajuste de proteccion

## Manual del conector a producir

Se redacta despues de la campana live, no antes.

Debe existir un documento de referencia del conector en esta repo, no solo en la vieja.

Secciones minimas:

1. objetivo del conector
2. superficie publica completa
3. contratos de entrada por metodo
4. contratos de salida por metodo
5. precondiciones
6. restricciones por tipo de orden
7. retcodes esperados
8. errores frecuentes y tratamiento
9. `execution_mode = live | paper`
10. separacion respecto de `account_mode`
11. ejemplos operativos completos
12. limitaciones conocidas por broker/simbolo

## Matriz de pruebas obligatoria

### Grupo A - Conectividad y estado

- inicializacion con terminal valido
- fallo controlado con terminal invalido
- lectura de broker identity
- lectura de catalogo
- lectura de specs
- lectura de cuenta
- lectura de tick
- login a otra cuenta y restore
- probe account sin degradar sesion activa

### Grupo B - Resolucion de simbolo

- simbolo exacto del broker
- matching case-insensitive
- simbolo no operable
- simbolos broker-aware como `UsDollar`

### Grupo C - Market execution

- buy market con SL/TP validos
- sell market con SL/TP validos
- buy market sin SL/TP y post-fill posterior
- sell market sin SL/TP y post-fill posterior
- validacion de comment y magic number

### Grupo D - Pending execution

- buy limit valido
- sell limit valido
- buy stop valido
- sell stop valido
- limit invalido que deba ser rechazado
- stop invalido que deba ser rechazado

### Grupo E - Position modification

- modificar solo SL
- modificar solo TP
- modificar SL y TP
- modificar posicion recien abierta por busqueda via `find_open_position_id()`
- modificar posicion heredada ya presente al inicio

### Grupo F - Order modification

- modificar solo precio
- modificar precio + SL
- modificar precio + TP
- modificar precio + SL + TP
- modificar pendiente heredida/asignada

### Grupo G - Remove / cancel

- cancelar orden pendiente propia
- cancelar orden pendiente heredada asignada
- cancelar orden ya no existente y verificar error manejado

### Grupo H - Close

- cierre total de buy
- cierre total de sell
- cierre parcial de buy
- cierre parcial de sell
- cierre de posicion heredada

### Grupo I - Trailing stop

- activar trailing por ganancias
- multiples updates de trailing
- no retroceder SL
- trailing sobre posicion fast
- trailing sobre posicion heredada fast

### Grupo J - Runtime consistency

- reconciliacion de posicion abierta luego de `send_execution_instruction()`
- reconciliacion de orden pendiente luego de `send_execution_instruction()`
- deteccion de fill posterior
- deteccion de cierre manual fuera del bridge
- deteccion de SL/TP cambiados fuera del bridge

### Grupo K - Modo operativo

- `execution_mode=paper`: no escribir en MT5
- `execution_mode=live`: escribir en MT5
- `account_mode` demo/real no cambia el significado de `live`

### Grupo L - Cambio de cuenta y seguridad operativa

- `probe_account()` con credenciales validas no debe degradar la sesion activa
- `probe_account()` con credenciales invalidas debe quedar registrado como caso de
  riesgo operativo
- la prueba debe verificar si la terminal queda con `trade_allowed=false`
- la prueba debe verificar si un `initialize()` posterior cae en `Authorization failed`
- debe quedar documentado el procedimiento de recuperacion operativo
- debe quedar definido el mensaje de alerta para operadores y WebUI futura

## Entornos de prueba

Deben existir como minimo dos niveles:

### Nivel 1 - Pruebas controladas

- cuenta de prueba aislada
- bajo volumen
- pocos simbolos
- spread razonable

Objetivo:

- validar superficie funcional

### Nivel 2 - Pruebas operativas

- posiciones reales del bridge
- modificaciones sucesivas
- adopcion de heredadas
- trailing y cierres

Objetivo:

- validar consistencia operativa en sesion viva

## Evidencia que debe guardarse

Por cada caso de prueba:

- `test_case_id`
- metodo ejercitado
- simbolo
- tipo de orden o accion
- request enviada
- respuesta recibida
- retcode
- timestamps
- confirmacion posterior desde MT5
- estado resultante en DB
- observaciones

Esto debe quedar:

- en SQLite
- y en un reporte Markdown o CSV de campana

## Criterios de aceptacion

1. Toda operacion publica del conector tiene documentacion.
2. Toda operacion publica del conector tiene al menos una prueba exitosa.
3. Toda operacion critica de escritura tiene al menos una prueba negativa.
4. El trailing stop queda documentado como patron, no como magia implicita.
5. `live` y `paper` quedan separados del modo de cuenta broker.
6. La campana produce evidencia suficiente para que Fast y SMC dependan del bridge.
7. El cambio de cuenta queda clasificado como operacion sensible y disruptiva si
   las credenciales fallan.
8. El procedimiento de recuperacion queda documentado para operadores.

## Orden recomendado

1. fijar la superficie oficial MT5 desde documentacion primaria
2. enumerar funciones obligatorias y funciones opcionales/no usadas
3. cerrar metodos faltantes del conector
4. montar el runner de certificacion con evidencia persistente
5. ejecutar pruebas de conectividad y lectura
6. ejecutar pruebas de pre-trade sin escritura
7. ejecutar pruebas live de apertura
8. ejecutar pruebas live de modificacion, cancelacion y cierre
9. ejecutar trailing y pruebas sobre operaciones heredadas
10. ejecutar y clasificar pruebas de cambio de cuenta
11. recien entonces redactar el manual del conector
12. emitir informe final de certificacion

## Relacion con el plan canonico

Este documento implementa la `Phase 0 - Connector manual and certification`
definida en:

- `docs/plans/2026-03-24_immutable_bridge_action_plan.md`
