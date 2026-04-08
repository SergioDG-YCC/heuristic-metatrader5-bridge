# Plan De Accion: Fast Desk Zone Rejection + SMC Context Reuse

> Estado: propuesto para nueva ejecucion en fork limpio
> Fecha: 2026-03-31
> Alcance: `fast_desk/setup`, `fast_desk/trigger`, `fast_desk/trader`, tests y trazabilidad operativa
> Restriccion central: FAST sigue siendo heuristico y sin LLM en hot path

---

## Objetivo

Reiniciar la mejora de `FAST` para que deje de depender casi por completo de rupturas simples y pueda operar reacciones mas realistas sobre zonas locales, usando dos capas de contexto:

1. Zonas y estructuras propias de `FAST` en `M30/M5/M1`
2. Contexto `SMC` ya persistido en DB como confluencia adicional, nunca como dependencia dura de ejecucion

El objetivo no es convertir `FAST` en `SMC-lite`, sino permitir que `FAST` tome mejores decisiones cuando el mercado ya fue mapeado por `SMC` y esa informacion esta disponible en runtime.

Tampoco es hacer que `FAST` herede entradas del desk `SMC`.

Lo que `FAST` reutiliza de `SMC` es contexto analitico persistido:

- zonas
- liquidez
- rechazo
- estructura
- bias o thesis resumida

Las entradas `SMC`, si existen, quedan fuera de este alcance.

---

## Supuestos Operativos

1. `SMC` ya corre en esta repo y persiste sus artefactos en DB por broker/account/symbol.
2. El analisis `SMC` puede usar LLM solo al final de su pipeline para limpiar o validar la lectura final.
3. Por lo tanto, los datos finales que `SMC` deja en DB son aptos para lectura posterior por `FAST` como contexto frio, sin meter LLM en el path critico de `FAST`.
4. Si no hay datos `SMC` recientes, `FAST` debe seguir funcionando solo con su logica heuristica local.
5. Ningun cambio de esta fase debe romper el principio: deteccion `FAST` y confirmacion `FAST` siguen siendo deterministicas y de baja latencia.

---

## Principio Rector

`FAST` puede leer de `SMC`, pero no esperar a `SMC`.

Interpretacion practica:

- `FAST` puede consultar DB para obtener sesgo, zonas HTF, thesis o eventos `SMC` recientes.
- `FAST` no puede bloquear la apertura o el scan por una llamada LLM ni por una dependencia asincronica al scanner `SMC`.
- `SMC` es una capa de confluencia y priorizacion, no el motor de disparo de `FAST`.
- `SMC` tampoco es el proveedor de entradas para `FAST`; solo aporta contexto reutilizable.

---

## Problemas a Resolver

### 1. Detecta poco cuando el mercado esta en reaccion, no en breakout

El flujo actual de `FAST` mejora cuando encuentra `order_block`, `FVG` o `sweep`, pero todavia descarta demasiado si el rechazo no luce textbook en la ultima ventana `M1`.

### 2. Mensajeria operativa pobre

Cuando hay zona local util pero no hay trigger suficiente, el sistema historicamente cae en mensajes tipo `no_pattern` o equivalentes, que no diferencian entre:

- no hay zona
- si hay zona, pero falta confirmacion
- si hay confirmacion debil
- si hay conflicto con contexto HTF/SMC

### 3. Subutilizacion del trabajo ya hecho por SMC

La repo ya dispone de analisis `SMC` y ese analisis se limpia al final con LLM. No aprovecharlo como contexto para `FAST` desperdicia una fuente de confluencia ya computada y persistida.

---

## Resultado Esperado

Al terminar esta fase, `FAST` debe poder:

1. Detectar reacciones en zonas locales `M30` y `M5` con mas estabilidad.
2. Distinguir claramente entre `no_local_zone` y `local_zone_detected_waiting_reaction`.
3. Aplicar penalizacion o boost por confluencia `SMC` leida desde DB.
4. Mantener ejecucion sin LLM y sin dependencia dura del desk `SMC`.
5. Emitir trazas y tests que expliquen por que una oportunidad fue descartada.

---

## Fuentes SMC Permitidas Para FAST

`FAST` puede leer estas clases de datos desde DB si existen y estan frescas:

1. Zonas HTF abiertas de `SMC`
2. Thesis o bias reciente por simbolo
3. Eventos recientes de estructura o liquidez
4. Estado resumido de validez o conflicto de tesis

`FAST` no necesita leer:

1. entradas propuestas por `SMC`
2. ordenes o recomendaciones finales del desk `SMC`
3. decisiones de ejecucion propias de `SMC`

Condiciones:

- siempre por `(broker_server, account_login, symbol)`
- con chequeo de frescura
- con fallback limpio a `neutral` si no hay datos
- sin fallar el scan por ausencia de filas

---

## Diseno Funcional

### Fase A. Reforzar zonas locales FAST

Archivos objetivo:

- `src/heuristic_mt5_bridge/fast_desk/setup/engine.py`
- `tests/fast_desk/test_fast_setup_trigger.py`

Cambios:

1. Mantener deteccion dual `M5` + `M30` para `order_block_retest` y `fvg_reaction`.
2. Guardar siempre `timeframe_origin` en metadata del setup.
3. Preservar `zone_top`, `zone_bottom`, `zone_type` y `zone_reaction` como contrato estable para triggers y auditoria.
4. Evitar que el filtro de RR o penalizaciones blandas borren silenciosamente todas las reacciones sin dejar rastro logico.

Criterio de aceptacion:

- si `M5` no aporta zona pero `M30` si, el setup sigue vivo
- tests validan que el origen `M30` realmente se propaga

### Fase B. Trigger mas expresivo para rechazo real

Archivos objetivo:

- `src/heuristic_mt5_bridge/fast_desk/trigger/engine.py`
- `tests/fast_desk/test_fast_setup_trigger.py`

Cambios:

1. Diferenciar triggers genericos de triggers de zona:
   - `zone_rejection_candle`
   - `zone_reclaim`
   - `zone_sweep_reclaim`
2. Si el setup es de familia `zone_reaction`, exigir que la vela `M1` toque la zona antes de marcar rechazo.
3. Mantener confirmacion por stacking o trigger fuerte, pero con semantica mas clara.
4. Evitar que una reaccion valida sea catalogada como breakout comun.

Criterio de aceptacion:

- tests cubren rechazo dentro de zona, reclaim y displacement sobre setup de zona
- el motivo de fallo distingue `trigger_outside_zone`, `no_rejection`, `weak_trigger_only`

### Fase C. Contexto SMC leido desde DB

Archivos objetivo:

- `src/heuristic_mt5_bridge/fast_desk/context/service.py`
- `src/heuristic_mt5_bridge/fast_desk/trader/service.py`
- `src/heuristic_mt5_bridge/infra/storage/runtime_db.py` si faltan helpers
- `tests/fast_desk/test_fast_trader_service_flow.py`

Cambios:

1. Leer zonas HTF `SMC` desde DB como contexto opcional.
2. Exponer en `FastContext.details` estructuras como:
   - `smc_htf_zones`
   - `smc_bias`
   - `smc_thesis_state`
   - `smc_data_freshness_seconds`
3. Aplicar confluencia blanda, nunca bloqueo duro, salvo que el equipo decida una excepcion explicita despues.
4. La ausencia de DB o filas debe devolver contexto neutral.
5. No incorporar conceptos de "entrada SMC confirmada" como input de `FAST`.

Criterio de aceptacion:

- `FAST` puede escanear con DB vacia
- si hay zona `SMC` alineada, el setup gana algo de confianza
- si hay conflicto, pierde confianza pero no desaparece sin explicacion
- si `SMC` no emitio ninguna entrada pero si dejo zonas/eventos utiles, `FAST` los puede reutilizar igual

### Fase D. Trazabilidad operativa util

Archivos objetivo:

- `src/heuristic_mt5_bridge/fast_desk/trader/service.py`
- `src/heuristic_mt5_bridge/fast_desk/activity_log.py`
- tests relacionados

Cambios:

1. Emitir `no_local_zone` cuando no se detecta ninguna familia de reaccion.
2. Emitir `local_zone_detected_waiting_reaction` cuando si hay setup de zona pero el trigger no confirma.
3. Adjuntar en detalles:
   - `zone_setup_count`
   - `zone_setup_types`
   - `h1_bias`
   - `market_phase`
   - `htf_zone_state`
   - posible contexto `SMC` resumido
4. Evitar mensajes ambiguos tipo `no_pattern` para esta parte del flujo.

Criterio de aceptacion:

- el operador puede distinguir ausencia real de setup vs espera de confirmacion
- test unitario captura el motivo nuevo en el stage `trigger`

---

## Reglas de Integracion con SMC

1. `FAST` no invoca al validador LLM de `SMC`.
2. `FAST` solo consume el resultado ya materializado en DB.
3. `SMC` sigue siendo el duenio semantico de sus tablas y modelos.
4. `FAST` solo mapea esos artefactos a estados simples de confluencia:
   - `confluence`
   - `conflict`
   - `neutral`
5. Si una fila `SMC` esta vieja, corrupta o incompleta, `FAST` la ignora y continua.
6. `FAST` no replica ni importa el sistema de entradas de `SMC`.
7. La utilidad esperada de `SMC` para `FAST` es analitica, no ejecutora.

---

## Riesgos a Evitar

1. Convertir confluencia `SMC` en dependencia dura de trading.
2. Duplicar logica profunda `SMC` dentro de `FAST`.
3. Introducir lecturas DB fragiles sin particion broker/account.
4. Usar nombres de campos que cambien entre writer y reader sin tests.
5. Repetir el error anterior de tocar demasiadas superficies a la vez.
6. Confundir contexto `SMC` con entradas `SMC`.

---

## Orden Recomendado de Ejecucion

1. Reforzar tests de `setup/trigger` en aislamiento.
2. Mejorar mensajes de descarte en `trader/service.py`.
3. Incorporar lectura `SMC` desde DB con fallback neutral.
4. Aplicar boost/penalty de confluencia despues de tener tests base.
5. Ejecutar `pytest tests/fast_desk -q` y luego smoke manual de runtime.

---

## Criterios de Done

Se considera completado cuando:

1. `FAST` mantiene principio no-LLM en hot path.
2. `FAST` puede leer contexto `SMC` desde DB sin romperse si no existe.
3. Hay tests para origen `M30`, espera de reaccion y confluencia HTF/SMC.
4. Los logs diferencian zona inexistente vs zona detectada sin confirmacion.
5. El cambio queda acotado a `fast_desk` mas helpers minimos de DB, sin refactor masivo de la repo.
6. La documentacion deja claro que `FAST` aprovecha contexto `SMC`, no entradas `SMC`.

---

## Nota Final

Esta fase asume explicitamente que `SMC` usa su LLM solo al final de su analisis para depurar la lectura. Eso habilita a `FAST` a reutilizar la salida ya persistida de `SMC` como contexto de calidad, sin contaminar la naturaleza rapida, heuristica y deterministica de `FAST`.

La clave de esta fase no es sincronizar dos traders, sino reutilizar una capa analitica ya computada por `SMC` para mejorar la lectura de zonas y rechazo en `FAST`.
