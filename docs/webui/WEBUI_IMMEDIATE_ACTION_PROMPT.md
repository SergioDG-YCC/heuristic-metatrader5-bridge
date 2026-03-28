# WebUI Immediate Action Prompt

## Proposito

Este documento existe para destrabar la correccion inmediata del frontend `apps/webui/` contra el backend real actual.

No es una nueva ronda de exploracion. No es una re-interpretacion estetica. Es una orden de correccion de contrato, representacion de capacidades y cierre tecnico.

## Contexto operativo

Estado actual:

- el frontend compila
- el frontend ya conecta con el backend
- pero la auditoria detecto desalineaciones materiales entre el shape real del backend y lo que el frontend tipa/consume/renderiza

Problema central:

- la UI no esta rota a nivel build
- la UI si esta desalineada a nivel de contrato de datos y de fidelidad de producto

## Fuente de verdad y precedencia

Usar esta jerarquia sin excepciones:

1. backend actual en codigo
   - `apps/control_plane.py`
   - `src/heuristic_mt5_bridge/core/runtime/service.py`
   - `src/heuristic_mt5_bridge/infra/mt5/connector.py`
2. frontend actual a corregir
   - `apps/webui/src/**`
3. documentacion final consolidada
   - `docs/webui/FINAL_BUILD_CONSTRUCTOR.md`
   - `docs/webui/FINAL_DIRECTION.md`
   - `docs/webui/FINAL_INFORMATION_ARCHITECTURE.md`
   - `docs/webui/FINAL_SCREEN_SET.md`
4. handoff actual
   - `docs/webui/WEBUI_BACKEND_HANDOFF.md`

Si hay conflicto:

- para capacidad actual manda el backend
- para forma de UI manda la documentacion final
- el handoff debe ser actualizado si contradice al backend real

## Hallazgos que hay que corregir ya

### 1. Contrato de exposure desalineado

El frontend espera:

- `by_symbol`
- `gross_volume`
- `net_volume`
- `floating_pnl`
- `used_margin`

El backend hoy devuelve:

- `symbols`
- `gross_exposure`
- `net_exposure`
- `floating_profit`

Impacto:

- Risk, Operations y Fast Desk pueden mostrar ceros, vacios o `No exposure data` aunque el backend si tenga datos

### 2. Contrato de positions / orders / specs / account mode desalineado

El frontend sigue esperando campos viejos como:

- `ticket`
- `type`
- `sl`
- `tp`
- `trade_contract_size`
- `trade_tick_size`
- `trade_tick_value`
- `spread`
- `account_type`

El backend hoy expone campos como:

- `position_id`
- `side`
- `stop_loss`
- `take_profit`
- `order_id`
- `order_type`
- `contract_size`
- `tick_size`
- `tick_value`
- `spread_points`
- `account_mode`

Impacto:

- tablas y tarjetas muestran datos equivocados o vacios

### 3. Ownership y Risk ya existen en backend y la UI sigue tratandolos como si no existieran

El backend actual ya expone:

- `/ownership`
- `/ownership/open`
- `/ownership/history`
- `/ownership/reassign`
- `/risk/status`
- `/risk/limits`
- `/risk/profile`
- `PUT /risk/profile`
- `/risk/kill-switch/trip`
- `/risk/kill-switch/reset`

Impacto:

- la UI y el handoff hoy venden una imagen falsa del producto actual

### 4. Warmup / boot logic no coincide con lo que la UI y el handoff prometen

Hoy el store:

- no setea `degraded_unavailable` en el arranque caido
- no implementa realmente el flujo de warmup que la documentacion describe

Impacto:

- el boot overlay cuenta una historia mas rica que la logica real

### 5. Drilldowns definidos pero no implementados

Las rutas existen:

- `/operations/symbol/:symbol`
- `/operations/symbol/:symbol/chart/:timeframe`
- `/terminal/spec/:symbol`

Pero los componentes no leen params ni usan el flujo de chart/spec drilldown correctamente.

### 6. Quedo codigo residual muerto

Hay fragmentos sobrantes en componentes como:

- `BootOverlay.tsx`
- `GlobalStatusStrip.tsx`

Eso debe limpiarse ahora, no despues.

## Objetivo inmediato

Corregir el frontend actual para que:

- renderice correctamente los payloads reales del backend actual
- use las capacidades reales del backend actual
- deje `Preview/Planned/Disabled` solo donde realmente siga correspondiendo
- mantenga el lenguaje visual mejorado ya logrado
- actualice el handoff para que no mienta

## Plan de accion inmediato

Ejecutar en este orden:

1. releer backend actual
   - `apps/control_plane.py`
   - `src/heuristic_mt5_bridge/core/runtime/service.py`
   - `src/heuristic_mt5_bridge/infra/mt5/connector.py`
2. corregir `apps/webui/src/types/api.ts`
   - alinear todos los tipos al payload real actual
3. corregir `apps/webui/src/api/client.ts`
   - agregar clientes para ownership y risk
   - no inventar rutas
4. corregir stores
   - `runtimeStore.ts`
   - `operationsStore.ts`
   - `terminalStore.ts`
   - `chartsStore.ts`
5. corregir pantallas live
   - `RuntimeOverview.tsx`
   - `Operations.tsx`
   - `Terminal.tsx`
   - `Alerts.tsx`
   - `Risk.tsx`
   - `FastDesk.tsx`
   - `Mode.tsx`
   - `Ownership.tsx`
6. implementar correctamente warmup / degraded boot state
7. cablear los drilldowns con params reales
8. eliminar codigo residual muerto
9. actualizar `docs/webui/WEBUI_BACKEND_HANDOFF.md`
10. correr verificacion final
   - `npm run build`

## Alcance permitido

Se puede:

- modificar `apps/webui/**`
- modificar `docs/webui/WEBUI_BACKEND_HANDOFF.md`
- ajustar el helper `scripts/dev/start_webui_and_control_plane.ps1` solo si hace falta para desarrollo

No se debe:

- reestructurar el backend
- inventar endpoints
- degradar la estetica nueva a una UI generica
- volver a una interpretacion visual floja
- tocar otra repo

## Restricciones no negociables

- repo correcta: `E:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge`
- no usar `E:\GITLAB\Sergio_Privado\llm-metatrader5-bridge` como fuente de verdad
- no modificar backend salvo que encuentres un bug real imposible de resolver desde frontend; si eso pasa, documentalo explicitamente
- no tratar `/events` como event log durable
- no inferir ownership por comments
- no mostrar acciones live que el control plane actual no expone
- si una capacidad ya existe en backend y hoy esta rotulada como `Planned`, corregirla
- mantener boot overlay y warmup UX
- mantener proxy dev de Vite al backend local

## Archivos que muy probablemente deban cambiar

- `apps/webui/src/types/api.ts`
- `apps/webui/src/api/client.ts`
- `apps/webui/src/stores/runtimeStore.ts`
- `apps/webui/src/stores/operationsStore.ts`
- `apps/webui/src/stores/terminalStore.ts`
- `apps/webui/src/stores/chartsStore.ts`
- `apps/webui/src/components/BootOverlay.tsx`
- `apps/webui/src/components/GlobalStatusStrip.tsx`
- `apps/webui/src/routes/RuntimeOverview.tsx`
- `apps/webui/src/routes/Operations.tsx`
- `apps/webui/src/routes/Alerts.tsx`
- `apps/webui/src/routes/FastDesk.tsx`
- `apps/webui/src/routes/Risk.tsx`
- `apps/webui/src/routes/Terminal.tsx`
- `apps/webui/src/routes/Ownership.tsx`
- `apps/webui/src/routes/Mode.tsx`
- `docs/webui/WEBUI_BACKEND_HANDOFF.md`

## Criterio de terminado

La tarea se considera terminada solo si:

1. `npm run build` pasa limpio
2. el frontend sigue arrancando en `apps/webui/`
3. Operations / Risk / Fast Desk / Terminal muestran datos correctos del backend actual
4. Ownership y Risk reflejan la capacidad real hoy disponible
5. boot warmup y degraded state son coherentes con la logica real
6. los drilldowns por params realmente funcionan
7. no quedan fragmentos muertos evidentes
8. `WEBUI_BACKEND_HANDOFF.md` queda alineado con el backend actual

## Prompt directo para el constructor

Usa este texto como instruccion principal:

```text
Vas a corregir la WebUI ya implementada dentro de la repo `heuristic-metatrader5-bridge`.

No vas a rehacer desde cero. Vas a alinear el frontend actual con el backend real actual y con la documentacion final consolidada.

Repo correcta:
- E:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge

No uses como fuente de verdad:
- E:\GITLAB\Sergio_Privado\llm-metatrader5-bridge

Lee primero:
- docs/webui/WEBUI_IMMEDIATE_ACTION_PROMPT.md
- docs/webui/FINAL_BUILD_CONSTRUCTOR.md
- docs/webui/FINAL_DIRECTION.md
- docs/webui/FINAL_INFORMATION_ARCHITECTURE.md
- docs/webui/FINAL_SCREEN_SET.md
- docs/webui/WEBUI_BACKEND_HANDOFF.md
- apps/control_plane.py
- src/heuristic_mt5_bridge/core/runtime/service.py
- src/heuristic_mt5_bridge/infra/mt5/connector.py

Objetivo:
- corregir contratos de datos y representacion de capacidades en `apps/webui/`
- mantener la direccion visual mejorada
- no inventar rutas ni capacidades
- actualizar el handoff para que quede verdadero

Problemas que debes corregir de inmediato:
- exposure shape del frontend no coincide con el backend real
- positions / orders / specs / account mode usan nombres de campos viejos
- ownership y risk ya existen en backend y la UI/handoff siguen desactualizados
- boot warmup no implementa correctamente el degraded state
- drilldown routes existen pero no funcionan
- quedaron residuos de codigo muerto en componentes

Instrucciones de trabajo:
1. inspecciona backend actual y confirma los payloads reales
2. corrige `src/types/api.ts`
3. corrige `src/api/client.ts`
4. corrige stores y pantallas live
5. integra ownership y risk actuales donde corresponda
6. corrige boot and warmup UX para que coincida con la logica real
7. implementa params/drilldowns reales
8. limpia codigo residual
9. actualiza `docs/webui/WEBUI_BACKEND_HANDOFF.md`
10. verifica con `npm run build`

Restricciones:
- no rehagas el backend
- no inventes endpoints
- no deshabilites visualmente la direccion nueva
- no conviertas ownership/risk en preview si el backend ya los expone
- no muestres acciones de trading live si no hay endpoints HTTP para eso

Entrega esperada:
- codigo corregido
- build limpio
- handoff actualizado
- resumen corto de los cambios reales y de cualquier limite pendiente
```

## Mensaje exacto para pegar en el chat del constructor

Pega exactamente esto junto con este `.md` adjunto:

```text
Necesito que ejecutes esta correccion inmediatamente sobre la WebUI ya construida.

Adjunto `docs/webui/WEBUI_IMMEDIATE_ACTION_PROMPT.md`.

Tomalo como instruccion principal de trabajo.
No quiero una nueva propuesta ni una reescritura conceptual.
Quiero correccion real del frontend actual para alinearlo con el backend actual y con la documentacion final.

Trabaja solo en:
- `E:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge`

No uses como fuente de verdad:
- `E:\GITLAB\Sergio_Privado\llm-metatrader5-bridge`

Empeza leyendo el `.md` adjunto y despues implementa directamente.
```
