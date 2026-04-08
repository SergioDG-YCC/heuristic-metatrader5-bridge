# PROMPT: FAST Zone Rejection Constructor

> Contexto: este prompt debe leerse completo antes de escribir codigo.
> Repo objetivo: `heuristic-metatrader5-bridge`.
> Se trabaja en un fork nuevo porque un intento anterior rompio la repo.

---

## Rol

Sos un senior engineer manteniendo `FAST Desk` dentro de `heuristic-metatrader5-bridge`.

Tu tarea es mejorar la deteccion de reacciones sobre zonas locales y la trazabilidad del pipeline `FAST`, reutilizando contexto `SMC` desde DB cuando exista, sin introducir LLM en el camino critico de `FAST`.

---

## Invariantes No Negociables

1. `FAST` no usa LLM en su hot path.
2. `FAST` puede leer datos `SMC` ya persistidos en DB.
3. `SMC` puede seguir usando LLM solo al final de su analisis, fuera del path de `FAST`.
4. La ausencia de datos `SMC` no puede romper ni bloquear `FAST`.
5. Toda lectura cross-desk debe respetar particion por `broker_server` y `account_login`.
6. No hagas un refactor masivo. Toca solo superficies necesarias.

---

## Intencion Arquitectonica

`FAST` sigue siendo un desk heuristico y rapido.

`SMC` actua como una capa auxiliar de contexto persistido:

- zonas HTF
- bias reciente
- thesis o estado resumido
- eventos recientes de estructura/liquidez

`FAST` puede usar eso para boost o penalizacion de confianza, nunca como requisito duro para detectar o ejecutar.

Importante:

- `SMC` esta orientado principalmente a analisis.
- `SMC` puede o no producir entradas propias.
- esas entradas `SMC` no son necesarias para `FAST`.
- lo valioso para `FAST` son las zonas encontradas, rechazo, liquidez, estructura y contexto persistido.

---

## Problema a Resolver

Historicamente `FAST` quedo demasiado sesgado a setups de ruptura o a confirmaciones muy estrictas en `M1`.

Queremos que el desk:

1. detecte mejor reacciones a zonas locales `M30/M5`
2. confirme mejor rechazo o reclaim en `M1`
3. informe claramente cuando existe zona pero todavia falta trigger
4. use contexto `SMC` ya disponible en DB como confluencia blanda

---

## Archivos Primarios

Trabaja prioritariamente en:

- `src/heuristic_mt5_bridge/fast_desk/setup/engine.py`
- `src/heuristic_mt5_bridge/fast_desk/trigger/engine.py`
- `src/heuristic_mt5_bridge/fast_desk/trader/service.py`
- `src/heuristic_mt5_bridge/fast_desk/context/service.py`
- `tests/fast_desk/test_fast_setup_trigger.py`
- `tests/fast_desk/test_fast_trader_service_flow.py`

Si faltan helpers de lectura, podes tocar:

- `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`

---

## Cambios Esperados

### 1. Setup Engine

En `setup/engine.py`:

- reforzar familias `order_block_retest`, `fvg_reaction`, `liquidity_zone_reaction`, `liquidity_sweep_reclaim`
- mantener scan dual `M5` + `M30` cuando corresponda
- guardar siempre metadata coherente:
  - `zone_reaction`
  - `zone_top`
  - `zone_bottom`
  - `zone_type`
  - `timeframe_origin`
- permitir que `M30` sobreviva aunque `M5` no encuentre nada

### 2. Trigger Engine

En `trigger/engine.py`:

- diferenciar triggers normales de triggers de zona
- usar nombres expresivos:
  - `zone_rejection_candle`
  - `zone_reclaim`
  - `zone_sweep_reclaim`
- si el setup viene de zona, verificar que la vela `M1` realmente toque la zona antes de aceptar rechazo
- mantener stacking o trigger fuerte, pero con motivos de fallo legibles

### 3. Trader Service

En `trader/service.py`:

- si no hay setups de zona: emitir `no_local_zone`
- si hay setups de zona pero no trigger: emitir `local_zone_detected_waiting_reaction`
- incluir detalles operativos en `activity_log`
- no degradar el flujo de entrada ya existente

### 4. Context Service + DB

En `context/service.py` y donde haga falta:

- leer artefactos `SMC` desde DB solo si estan disponibles
- exponerlos como contexto opcional para `FAST`
- aplicar solo confluencia blanda
- fallback limpio a neutral si no hay datos o estan viejos
- no importar ni ejecutar entradas `SMC` dentro de `FAST`

---

## Semantica Deseada

Cuando una oportunidad no entra, el sistema debe poder distinguir:

1. no existe zona local valida
2. existe zona local valida pero falta rechazo/reclaim
3. existe trigger, pero falla por fase o contexto
4. existe setup bueno, pero hay conflicto con contexto HTF o `SMC`

Evita respuestas ambiguas del tipo `no_pattern` si el problema real es otro.

Tambien evita estas interpretaciones incorrectas:

- "si `SMC` no genero entrada, no hay contexto util"
- "si `SMC` genero entrada, `FAST` debe seguirla"

Ambas son falsas para este alcance.

---

## Contrato con SMC

Asumi explicitamente lo siguiente:

- `SMC` escribe a DB resultados ya procesados
- su LLM de confirmacion se usa solo al final del analisis `SMC`
- `FAST` nunca invoca ese LLM
- `FAST` solo consume el resultado persistido
- `FAST` no consume ni replica la logica de entradas del desk `SMC`
- la ausencia de entradas `SMC` no invalida sus zonas o eventos como contexto
- la presencia de entradas `SMC` no obliga a `FAST` a operar

Por lo tanto, es valido que `FAST` lea la salida `SMC` de DB para enriquecer contexto sin violar su principio no-LLM.

En otras palabras: el acoplamiento permitido es `contexto SMC -> FAST`, no `senial SMC -> FAST`.

---

## Restricciones de Implementacion

1. No agregues flags innecesarios si ya existe una fuente clara en `context.details` o metadata.
2. No metas dependencia circular entre desks.
3. No bloquees scans por ausencia de datos `SMC`.
4. No reemplaces la decision `FAST` por thesis `SMC`; solo influye confidence/context.
5. No cambies contratos publicos sin actualizar tests.

---

## Tests Minimos Esperados

Agrega o actualiza tests para cubrir al menos:

1. setup originado en `M30` cuando `M5` no aporta zona
2. trigger de zona rechaza velas fuera de la zona
3. `trader/service.py` reporta `local_zone_detected_waiting_reaction`
4. confluencia HTF/SMC sube o baja confianza sin matar el setup por defecto
5. ausencia de DB `SMC` no rompe `FAST`
6. presencia de artefactos `SMC` sin entradas `SMC` sigue siendo util para `FAST`

---

## Criterio de Exito

La implementacion es correcta si:

1. `FAST` detecta mas oportunidades de reaccion sin volverse indiscriminado
2. los logs explican mejor por que no ejecuto
3. los tests de `fast_desk` siguen verdes
4. `FAST` reutiliza `SMC` como contexto persistido, no como dependencia viva
5. queda explicitamente desacoplado de las entradas propias de `SMC`

---

## Entrega Esperada

Cuando termines:

1. resume los archivos tocados
2. explica como `FAST` usa `SMC` desde DB
3. lista tests ejecutados y tests pendientes si no pudiste correrlos
4. menciona cualquier supuesto tomado sobre esquemas DB `SMC`
