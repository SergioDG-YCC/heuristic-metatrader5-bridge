# Plan De Accion: Aislamiento Operativo FAST vs SMC por Ticket

> Estado: propuesto para implementacion controlada
> Fecha: 2026-04-07
> Alcance: `core/runtime`, `core/ownership`, `fast_desk`, `apps/control_plane`, `apps/webui`, tests y verificacion operativa
> Restriccion central: `FAST` no puede conocer tickets `SMC`; la separacion debe ser por visibilidad positiva, no por exclusiones de la mesa ajena

---

## Objetivo

Corregir la arquitectura para que `FAST` opere exclusivamente sobre:

1. tickets creados por `FAST`
2. tickets heredados externamente y clasificados como `inherited_fast`

Y para que `FAST` nunca vea, enumere, filtre, compare ni gestione tickets creados por `SMC`.

Esto incluye:

- runtime backend
- ownership reconciliation
- custody/pending de `FAST`
- control plane
- WebUI operativa

---

## Reglas No Negociables

1. `FAST` no debe construir `smc_order_ids` ni `smc_position_ids`.
2. `FAST` no debe depender de una blacklist de `SMC`.
3. `FAST` no debe ver tickets `SMC` en su `account_payload` operativo.
4. La visibilidad correcta de `FAST` es solo:
   - `fast_owned`
   - `inherited_fast`
5. `SMC` no es "externo". Nunca debe terminar adoptado o visible para `FAST`.
6. La adopcion de tickets externos debe ocurrir solo en `OwnershipRegistry`.
7. La UI `Fast Desk` no debe usar datasets globales de broker para representar operaciones de `FAST`.

---

## Diagnostico Resumido

Problema estructural actual:

1. `CoreRuntimeService` construye un snapshot global de MT5 con todas las `positions` y `orders`.
2. Ese snapshot global se inyecta a `SMC` y a `FAST`.
3. `SMC` filtra correctamente sus tickets usando ownership.
4. `FAST` consume listas globales de `positions` y `orders`.
5. `FAST` intenta "restar" tickets `SMC` armando sets de exclusion.
6. Ese diseño ya es incorrecto, porque `FAST` nunca deberia recibir tickets `SMC`.
7. Ademas, la exclusion actual falla porque runtime le pasa a `FAST` una vista de ownership ya filtrada a `fast` e `inherited_fast`.

Consecuencia:

- `FAST` ve ordenes pendientes `SMC`
- las repricia hacia mercado
- conserva `SL/TP` de `SMC`
- destruye el `RR`
- y luego su custody queda matematicamente inutil para esa posicion deformada

---

## Contrato Objetivo

### Contrato de visibilidad por desk

`FAST` debe recibir un payload operativo que solo contenga:

- `positions` con ownership `fast_owned` o `inherited_fast`
- `orders` con ownership `fast_owned` o `inherited_fast`

`SMC` debe recibir un payload operativo que solo contenga:

- `positions` con ownership `smc_owned`
- `orders` con ownership `smc_owned`

### Contrato de ownership

Estados permitidos:

- `fast_owned`
- `smc_owned`
- `inherited_fast`
- `unassigned`

Regla clave:

- `inherited_fast` significa tickets ajenos al stack antes de su adopcion
- `SMC` no entra en esa categoria

### Contrato de UI

- `/positions` puede seguir existiendo como vista global de broker
- `Fast Desk` no debe usar `/positions` como fuente operativa primaria
- `SMC Desk` tampoco debe inferir ownership desde datasets globales
- cada desk debe tener endpoints o stores desk-scoped

---

## Fase 0: Congelamiento Del Error y Preparacion

### Objetivo

Congelar el alcance y dejar trazabilidad para implementar sin volver a mezclar conceptos.

### Pasos

1. Documentar este contrato como fuente de verdad para la implementacion.
2. Marcar como invalida cualquier logica `FAST` que dependa de conocer tickets `SMC`.
3. Identificar en tests y codigo toda referencia a:
   - `smc_order_ids`
   - `smc_pos_ids`
   - exclusion de `SMC` dentro de `fast_desk`
4. Confirmar el nombre definitivo del env para auto-adopcion externa.

### Criterio de aceptacion

- Existe una definicion clara y escrita del modelo correcto: `allowlist FAST`, no `blacklist SMC`.

---

## Fase 1: Formalizar Payload Operativo Por Desk En Runtime

### Objetivo

Mover la separacion real al `runtime`, antes de que cualquier desk vea operaciones.

### Archivos objetivo

- `src/heuristic_mt5_bridge/core/runtime/service.py`

### Cambios requeridos

1. Mantener un snapshot global interno de MT5 para reconciliacion y vistas globales.
2. Crear un builder de payload desk-scoped, por ejemplo:
   - `account_payload_for_desk("fast")`
   - `account_payload_for_desk("smc")`
3. Filtrar `positions` y `orders` usando ownership positivo.
4. No filtrar por comentario MT5 como fuente principal.
5. Permitir que `account_state` y `exposure_state` sigan globales si hace falta, pero que las listas operables sean desk-scoped.

### Pasos intermedios

1. Extraer helpers para obtener sets visibles por desk desde ownership.
2. Resolver comportamiento cuando ownership aun no tiene fila:
   - `FAST`: solo ve esas filas si ownership ya las adopto como `inherited_fast`
   - `SMC`: no ve nada sin ownership `smc_owned`
3. Reemplazar la inyeccion actual de `lambda: self.account_payload` por lambdas desk-scoped.
4. Conservar el snapshot global solo para:
   - reconciliacion
   - `/positions`
   - `/account`
   - `/ownership`

### Criterio de aceptacion

- `FAST` deja de recibir listas globales de broker.
- Si un ticket es `smc_owned`, no aparece en el payload operativo de `FAST`.

---

## Fase 2: Simplificar FAST a Visibilidad Positiva

### Objetivo

Eliminar del trader `FAST` toda nocion de tickets `SMC`.

### Archivos objetivo

- `src/heuristic_mt5_bridge/fast_desk/trader/service.py`
- `src/heuristic_mt5_bridge/fast_desk/workers/symbol_worker.py`
- `src/heuristic_mt5_bridge/fast_desk/runtime.py`

### Cambios requeridos

1. Borrar la construccion de `smc_order_ids` y `smc_pos_ids`.
2. Borrar comentarios y ramas del estilo:
   - "belongs to SMC desk — do not touch"
3. Hacer que `FAST` opere suponiendo que el payload ya viene limpio.
4. Mantener solo la logica propia de:
   - `fast_owned`
   - `inherited_fast`
   - grace windows de adopcion
5. Agregar una defensa de contrato:
   - si aparece un ticket fuera del set visible FAST, ignorarlo y loguear violacion de contrato
   - sin nombrar `SMC`

### Pasos intermedios

1. Reusar `_fast_owned_sets()` donde sirva.
2. En `custody`, iterar solo tickets ya visibles a `FAST`.
3. En `pending`, iterar solo ordenes ya visibles a `FAST`.
4. Verificar que `forced_custody_symbols()` siga funcionando solo con owner/status FAST.

### Criterio de aceptacion

- El trader `FAST` ya no contiene logica de exclusion de la mesa `SMC`.
- El hot path queda modelado con allowlist positiva.

---

## Fase 3: Blindar La Adopcion Externa En Ownership

### Objetivo

Concentrar toda adopcion de tickets externos en un unico lugar: `OwnershipRegistry`.

### Archivos objetivo

- `src/heuristic_mt5_bridge/core/ownership/registry.py`
- `src/heuristic_mt5_bridge/core/runtime/service.py`

### Cambios requeridos

1. Confirmar que toda operacion desconocida del snapshot global se adopte solo en `reconcile_from_caches()`.
2. Documentar que `inherited_fast` representa tickets externos a ambos desks del stack.
3. Impedir semanticamente que una operacion `smc_owned` pueda degradarse o reinterpretarse como `inherited_fast`.
4. Alinear el env de auto-adopcion:
   - un solo nombre canonico
   - lectura consistente en runtime
   - exposicion consistente en control plane/UI

### Pasos intermedios

1. Resolver la discrepancia entre:
   - `OWNERSHIP_AUTO_ADOPT_FOREIGN`
   - `RISK_ADOPT_FOREIGN_POSITIONS`
2. Elegir uno como canonico y mantener el otro, si se quiere, solo como alias legacy.
3. Asegurar que la docs, UI de settings y runtime reflejen la misma variable efectiva.

### Criterio de aceptacion

- La adopcion externa queda unificada.
- No hay ambiguedad operativa sobre cuando un ticket manual/humano entra a `FAST`.

---

## Fase 4: Separar Endpoints Y Stores Operativos De La WebUI

### Objetivo

Evitar que las pantallas de desk usen datasets globales de broker como si fueran datasets del desk.

### Archivos objetivo

- `apps/control_plane.py`
- `apps/webui/src/stores/operationsStore.ts`
- `apps/webui/src/routes/FastDesk.tsx`
- `apps/webui/src/routes/SmcDesk.tsx`
- `apps/webui/src/api/client.ts`

### Cambios requeridos

1. Mantener `/positions` como consola global de broker.
2. Crear endpoints desk-scoped, por ejemplo:
   - `/api/v1/fast/operations`
   - `/api/v1/smc/operations`
3. Hacer que `FastDesk.tsx` consuma solo operaciones `FAST`.
4. Hacer que `SmcDesk.tsx` consuma solo operaciones `SMC`.
5. Dejar `Operations` y `Ownership` como vistas globales de auditoria.

### Pasos intermedios

1. Reusar el builder desk-scoped del runtime en el control plane.
2. Crear stores o polling separados por desk.
3. Revisar cards y railes de `FastDesk` que hoy leen `operationsStore.positions`.
4. Revisar metrics de `SmcDesk` que hoy cuentan posiciones desde el store global.

### Criterio de aceptacion

- La pantalla `Fast Desk` deja de mostrar posiciones SMC.
- La pantalla `SMC Desk` deja de mezclar posiciones globales no SMC.

---

## Fase 5: Endurecer Verificaciones y Tests

### Objetivo

Convertir este bug en una regresion imposible de reintroducir sin romper tests.

### Tests requeridos

1. Runtime desk payload
   - un ticket `smc_owned` existe en snapshot global
   - aparece en payload `smc`
   - no aparece en payload `fast`

2. FAST pending custody
   - `FAST` no intenta modificar una orden `smc_owned`
   - `FAST` si puede modificar una orden `inherited_fast`

3. Ownership adoption
   - ticket manual sin fila previa se adopta como `inherited_fast`
   - ticket `smc_owned` no puede ser re-clasificado como heredado

4. WebUI/API
   - endpoint `fast/operations` devuelve solo tickets FAST
   - endpoint `smc/operations` devuelve solo tickets SMC

5. Regression log
   - con tickets `smc_owned` abiertos, `fast_desk_trade_log` no registra eventos sobre esos `order_id/position_id`

### Archivos probables

- `tests/core/test_runtime_service.py`
- `tests/core/test_ownership_registry.py`
- `tests/fast_desk/test_fast_trader_context_pending.py`
- tests nuevos para control plane o webui stores si el repo ya tiene la base

### Criterio de aceptacion

- La separacion queda cubierta en backend, ownership y UI.

---

## Fase 6: Verificacion Operativa En Runtime Real

### Objetivo

Validar en la cuenta real que el aislamiento se cumple con operaciones vivas.

### Checklist de verificacion

1. Abrir o detectar una orden `SMC` pendiente.
2. Confirmar en DB:
   - `operation_ownership.desk_owner = smc`
   - `ownership_status = smc_owned`
3. Confirmar que:
   - no aparece en `fast/operations`
   - no aparece en `Fast Desk` UI
   - no recibe `pending_modify` desde `FAST`
4. Abrir o detectar una operacion externa/manual.
5. Confirmar adopcion como `inherited_fast`.
6. Confirmar que:
   - aparece en `fast/operations`
   - puede recibir custody/pending de `FAST`

### Criterio de aceptacion

- `FAST` solo toca tickets `fast_owned` o `inherited_fast`.
- `SMC` queda completamente fuera de su visibilidad operativa.

---

## Orden Recomendado De Implementacion

1. `core/runtime/service.py`
2. `fast_desk/trader/service.py`
3. `core/ownership/registry.py`
4. `apps/control_plane.py`
5. `apps/webui`
6. tests
7. validacion en runtime real

---

## Riesgos A Vigilar

1. Romper la adopcion legitima de tickets manuales/humanos.
2. Dejar `FAST` sin visibilidad de `inherited_fast` por filtrar demasiado pronto.
3. Mantener endpoints UI globales y desk-scoped con semanticas mezcladas.
4. Reintroducir la logica incorrecta mediante un fallback futuro a `account_payload` global.
5. No alinear el env de auto-adopcion y dejar la operacion real en estado ambiguo.

---

## Deliverables Esperados

1. Runtime con payload desk-scoped.
2. `FAST` sin referencias operativas a tickets `SMC`.
3. Ownership con adopcion externa unificada.
4. Control plane con endpoints por desk.
5. WebUI de cada desk consumiendo solo su universo visible.
6. Tests de regresion que bloqueen futuras contaminaciones.

---

## Prompt De Ejecucion Propuesto

```text
Implementar aislamiento total por ticket entre FAST y SMC en esta repo.

Reglas obligatorias:
- FAST nunca debe conocer, listar, filtrar ni comparar tickets SMC.
- FAST solo puede operar tickets fast_owned e inherited_fast.
- inherited_fast significa tickets externos al stack, nunca creados por SMC.
- La separacion correcta es por allowlist positiva, no por blacklist de SMC.
- /positions puede seguir siendo global, pero Fast Desk y Smc Desk deben consumir endpoints desk-scoped.

Objetivo tecnico:
- mover la separacion de tickets al runtime
- generar account_payload_for_desk("fast") y account_payload_for_desk("smc")
- inyectar esos payloads desk-scoped a cada desk
- eliminar de fast_desk toda logica que construya smc_order_ids o smc_pos_ids
- mantener la adopcion externa solo en OwnershipRegistry
- unificar la configuracion de auto-adopcion externa
- agregar tests backend y control-plane para garantizar que FAST nunca toque tickets smc_owned

Archivos foco:
- src/heuristic_mt5_bridge/core/runtime/service.py
- src/heuristic_mt5_bridge/core/ownership/registry.py
- src/heuristic_mt5_bridge/fast_desk/trader/service.py
- src/heuristic_mt5_bridge/fast_desk/workers/symbol_worker.py
- apps/control_plane.py
- apps/webui/src/routes/FastDesk.tsx
- apps/webui/src/routes/SmcDesk.tsx
- apps/webui/src/stores/operationsStore.ts

Criterios de aceptacion:
- tickets smc_owned no aparecen en fast payload
- fast_desk_trade_log no registra acciones sobre tickets smc_owned
- tickets externos/manuales pueden adoptarse como inherited_fast
- Fast Desk UI no muestra tickets SMC
- Smc Desk UI no mezcla posiciones globales ajenas

No usar una blacklist de SMC. Si FAST ve un ticket SMC, el bug sigue vivo.
```

