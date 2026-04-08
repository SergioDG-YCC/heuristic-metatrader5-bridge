# Connector Certification Execution Report

Fecha: 2026-03-24

## Proposito

Dejar asentada la campana real ejecutada sobre la cuenta demo actual, con
comandos reproducibles, evidencia guardada y separacion explicita entre:

- primitivas oficiales MT5 que si funcionan
- superficie publica del bridge que si funciona
- superficie publica del bridge que todavia no existe
- bloqueos de terminal o broker que afectan la certificacion

## Runner usado

- `tests/integration/mt5_connector_certification.py`

## Comandos ejecutados

### Enumeracion de casos

```powershell
.\.venv\Scripts\python.exe tests\integration\mt5_connector_certification.py --list
```

### Lectura, introspeccion y pre-trade

```powershell
.\.venv\Scripts\python.exe tests\integration\mt5_connector_certification.py --include surface,official,connector.read --symbol EURUSD --timeframe M5
```

Evidencia:

- `storage/certification/20260324T081130Z_2587e882.json`

Resultado:

- lectura y pre-trade oficiales: OK
- lectura del bridge: OK
- gaps publicos del connector heuristico: detectados

### Entradas live del bridge con comentario vacio

```powershell
.\.venv\Scripts\python.exe tests\integration\mt5_connector_certification.py --include connector.write --symbol EURUSD --timeframe M5 --allow-live-writes --comment-mode empty
```

Evidencia:

- `storage/certification/20260324T081538Z_e78e2b4a.json`

Resultado:

- `market buy`: OK
- `market sell`: OK
- `buy limit`: OK
- `sell limit`: OK
- `buy stop`: OK
- `sell stop`: OK
- cleanup: OK
- posiciones residuales: 0
- ordenes residuales: 0

### Falla de comentario poblado

```powershell
.\.venv\Scripts\python.exe tests\integration\mt5_connector_certification.py --include connector.write.market_buy --symbol EURUSD --timeframe M5 --allow-live-writes --comment-mode tagged
```

Evidencia:

- `storage/certification/20260324T081633Z_571aa621.json`

Resultado:

- `send_execution_instruction()` falla con `Invalid "comment" argument`

### Campana full con live raw + bridge

```powershell
.\.venv\Scripts\python.exe tests\integration\mt5_connector_certification.py --symbol EURUSD --timeframe M5 --allow-live-writes --allow-destructive --comment-mode empty
```

Evidencia:

- `storage/certification/20260324T084053Z_1fee3aeb.json`

Resultado:

- raw official live:
  - `TRADE_ACTION_SLTP`: OK
  - `TRADE_ACTION_MODIFY`: OK
  - `TRADE_ACTION_REMOVE`: OK
  - cierre total: OK
  - cierre parcial: OK
  - trailing por `SLTP`: OK
- `probe_account()` sobre cuenta invalida: devuelve `Authorization failed`
- despues de esa secuencia, los `connector.write.*` devolvieron `10027 AutoTrading disabled by client`

### Campana full util sin probe invalido

```powershell
.\.venv\Scripts\python.exe tests\integration\mt5_connector_certification.py --symbol EURUSD --timeframe M5 --allow-live-writes --allow-destructive --comment-mode empty --exclude connector.read.probe_invalid_account
```

Evidencia:

- `storage/certification/20260324T084426Z_77626a49.json`

Resultado:

- toda la parte util del live quedo verde
- `connector.write.*` volvio a pasar en `market`, `limit` y `stop`
- los unicos no verdes fueron:
  - gaps estructurales de wrappers faltantes
  - `find_open_position_id`, que sigue bloqueado por el problema de comentarios

### Probe invalido aislado

```powershell
.\.venv\Scripts\python.exe tests\integration\mt5_connector_certification.py --include connector.read.probe_invalid_account --symbol EURUSD --timeframe M5
```

Evidencia:

- `storage/certification/20260324T084451Z_ef6318b2.json`

Observacion posterior inmediata:

- el siguiente `MT5Connector.connect()` ya cayo con `Terminal: Authorization failed`
- el control plane dejo de responder en `http://127.0.0.1:8765/status`

## Hallazgos confirmados

### 1. Superficie publica existente

Confirmado en la repo heuristica:

- `connect`
- `shutdown`
- `broker_identity`
- `ensure_symbol`
- `fetch_snapshot`
- `fetch_symbol_specification`
- `fetch_available_symbol_catalog`
- `fetch_account_runtime`
- `symbol_tick`
- `login`
- `probe_account`
- `send_execution_instruction`

### 2. Gaps publicos reales del connector heuristico

No existen hoy en `src/heuristic_mt5_bridge/infra/mt5/connector.py`:

- `modify_position_levels`
- `modify_order_levels`
- `remove_order`
- `close_position`
- `find_open_position_id`

Esto hace que fallen o queden en gap:

- custodia de posiciones del bridge
- trailing del bridge
- cierres del bridge
- adopcion por comentario

### 3. MT5 oficial si soporta la custodia faltante

En esta misma terminal y cuenta demo se pudo ejercer correctamente, por raw MT5:

- `TRADE_ACTION_SLTP`
- `TRADE_ACTION_MODIFY`
- `TRADE_ACTION_REMOVE`
- cierre total por deal opuesto
- cierre parcial por deal opuesto
- trailing construido con multiples `SLTP`

Conclusion:

- el bloqueo no es del broker ni de MT5 para esas operaciones
- el bloqueo esta en la superficie publica faltante del bridge

### 4. El comentario de orden no esta resuelto

Hecho observado:

- con `comment=""`, la apertura live del bridge quedo probada
- con `comment` poblado, `send_execution_instruction()` fallo

Impacto:

- ownership por comentario no esta certificado
- `find_open_position_id()` no puede darse por operativo aunque existiera
- la futura WebUI no debe asumir tagging confiable hasta resolver esta capa

### 5. Cambio de cuenta: la ruta existe, pero tiene riesgo operativo lateral severo

Prueba negativa ejecutada:

- `probe_account()` sobre login invalido devolvio:
  - `error_code = -6`
  - `error_message = "Terminal: Authorization failed"`

Primera observacion correlativa:

- en la corrida full posterior, la terminal quedo con:
  - `TerminalInfo.trade_allowed = False`

Segunda observacion, ya aislada:

- al ejecutar solo `probe_invalid_account`, el siguiente `initialize()` ya fallo
  con `Authorization failed`
- el control plane quedo caido y sin proceso Python vivo

Esto ya no es solo una sospecha difusa. Queda confirmado que la ruta de probe o
cambio de cuenta puede degradar la sesion viva del terminal.

- la ruta de cambio/probe de cuenta puede requerir re-habilitacion manual de
  AutoTrading en la terminal
- la ruta de cambio/probe de cuenta puede dejar el terminal sin sesion valida
- la futura WebUI no debe exponer esto como accion inocua

## Mensaje de alerta requerido para operadores y WebUI

Texto minimo sugerido:

- `Cambiar o probar otra cuenta puede interrumpir la sesion MT5 activa.`
- `Si la autenticacion falla, AutoTrading puede quedar deshabilitado y los servicios pueden caer.`
- `Recuperacion: rehabilitar AutoTrading en MT5 y relanzar el control plane si fuera necesario.`

Nivel sugerido:

- alerta visible tipo `danger`
- confirmacion explicita antes de ejecutar
- registrar auditoria del intento

## Recuperacion operativa observada

En esta instalacion actual, el operador pudo recuperar la terminal volviendo a
habilitar AutoTrading manualmente.

Procedimiento minimo a documentar:

1. verificar que MT5 quede conectado a la cuenta esperada
2. volver a habilitar el boton `AutoTrading`
3. verificar `trade_allowed = true`
4. relanzar `apps/control_plane.py` si el servicio quedo caido

## Estado final observado

Verificacion posterior:

- `TerminalInfo.trade_allowed = False`
- `positions_get(EURUSD) = ()`
- `orders_get(EURUSD) = ()`

Es decir:

- la terminal quedo bloqueando nuevas escrituras
- no quedaron posiciones ni ordenes residuales del harness en `EURUSD`

## Conclusiones de construccion

Hoy queda probado:

- el bridge heuristico lee correctamente MT5
- el bridge heuristico puede abrir entradas `market/limit/stop` cuando:
  - la terminal tiene `trade_allowed = True`
  - el request usa `comment=""`
- las primitivas oficiales necesarias para custodia existen y funcionan

Hoy queda no probado o negativamente probado:

- tagging/ownership por comentario
- wrappers publicos de custodia del bridge
- estabilidad del flujo `probe_account()` respecto al estado de AutoTrading
- estabilidad del flujo `probe_account()` respecto a la sesion viva del terminal

## Proximo paso tecnico

Antes de seguir con traders o WebUI:

1. restaurar `trade_allowed = True` en la terminal
2. cerrar la superficie publica faltante del connector heuristico
3. definir la politica oficial de `comment`
4. encapsular `probe_account()` y cambio de cuenta en un flujo no disruptivo
5. agregar deteccion explicita de `terminal.trade_allowed`
6. re-correr la campana full
7. recien entonces escribir el manual final del conector
