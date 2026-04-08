# Fast Trader Gap Audit

Fecha: 2026-03-24

## Proposito

Fijar el estado real del `fast_desk` actual contra el objetivo de
`FastTraderService` definido en el plan canónico.

Este documento existe para que el constructor no trate el trabajo como
"pequeñas mejoras" sobre el scanner actual.

## Estado actual real en la repo heuristica

Hoy Fast ya tiene piezas parciales:

- scanner de señales simple en `fast_desk/signals/scanner.py`
- gate local de riesgo en `fast_desk/risk/engine.py`
- policy de entrada muy básica en `fast_desk/policies/entry.py`
- custodian simple en `fast_desk/custody/custodian.py`
- worker por símbolo en `fast_desk/workers/symbol_worker.py`
- bridge de ejecución a `MT5Connector`
- integración actual con `OwnershipRegistry` y `RiskKernel`

También ya tiene:

- conector MT5 certificado
- ownership persistente
- risk kernel global y por mesa
- runtime RAM-first operativo

## Limitaciones actuales

El Fast actual no es todavía un `FastTraderService` profesional.

### 1. Timeframes insuficientes

Hoy Fast opera con:

- `M5` como señal principal

Contexto disponible general:

- `M5`
- `H1`

Pero el nuevo Fast requerido necesita:

- `M1` para trigger microestructural
- `M5` para setup operativo
- `H1` para contexto direccional

### 2. Scanner demasiado simple

El scanner actual está basado principalmente en:

- cruce sobre EMA
- ATR mínimo
- spike de volumen

Eso no alcanza para el producto objetivo.

Faltan heurísticas explícitas para:

- order blocks
- liquidity sweep
- breakout + retest
- chart patterns
- displacement / micro BOS
- gatillos M1
- estructura M5 contextualizada por H1

### 3. Custody demasiado básica

El custodian actual:

- mueve a BE
- hace un trailing sencillo
- cierra ante sobrepaso del riesgo inicial

Pero falta custodia profesional para:

- trailing estructural
- trailing por ATR dinámico
- hard loss cut más fino
- no passive underwater
- scale-out parcial opcional
- gestión de posiciones heredadas Fast con criterio superior

### 4. No existe separación formal entre setup y trigger

Hoy el worker:

- detecta
- calcula tamaño
- abre

Todo en una sola pasada simple.

El objetivo real requiere separar:

- contexto
- setup
- trigger
- custody

### 5. No hay gates operativos completos

Siguen faltando gates explícitos por trader para:

- spread
- slippage
- sesión operativa
- régimen de mercado
- stale feed / calidad del chart

### 6. No hay soporte serio para pending orders Fast

El plan exige:

- market
- pending orders Fast
- custodia de pending orders
- cancelación defensiva
- posible modificación

Eso todavía no está cerrado como servicio trader.

## Estado objetivo

El `FastTraderService` a construir debe ser:

- heurístico puro
- sin LLM
- de baja latencia
- más agresivo que el `live_execution_trader` viejo
- no menos seguro
- apoyado en `RiskKernel`
- apoyado en `OwnershipRegistry`
- usando únicamente la superficie canónica del conector

## Decisiones de arquitectura para esta fase

### 1. No reutilizar el runtime viejo como runtime

No copiar:

- `live_execution_trader_runtime.py`
- `execution_bridge.py`
- office stack u orquestación vieja

Sólo usar la repo vieja como fuente de comportamiento.

### 2. Reutilizar heurísticas, no acoplar scanners lentos

Puede reutilizarse como fuente:

- `smc_heuristic_scanner.py`
- `chartism_patterns.md`
- `sltp_methods.md`
- `smc_entry_models.md`

Pero no enchufar el scanner SMC viejo completo en el hot path de Fast.

### 3. Fast debe ser M1 + M5 + H1

Contrato operacional:

- `M1` = trigger
- `M5` = setup
- `H1` = contexto

### 4. Order Blocks sí, pero en formato Fast

Los `order blocks` deben entrar a Fast como:

- filtro de zona
- confluencia de entrada
- soporte para retest
- subordinados a trigger rápido M1

No como tesis lenta D1/H4.

## Gaps exactos a cerrar

1. Agregar `M1` al runtime operativo de Fast.
2. Introducir `FastTraderService` separado del scanner simple actual.
3. Diseñar pipeline `context -> setup -> trigger -> custody`.
4. Integrar heurísticas de:
   - order block retest
   - liquidity sweep + reclaim
   - breakout + retest
   - chart patterns robustos
5. Implementar gates:
   - session
   - spread
   - slippage
   - stale feed
6. Implementar custody profesional:
   - BE
   - trailing ATR
   - trailing estructural
   - hard cut
   - optional scale-out
7. Integrar ownership y risk como autoridad real.
8. Persistir audit trail Fast completo.

## Primer alcance recomendado

No intentar resolver todo el universo de patrones en la primera pasada.

Primer bloque recomendado:

- `M1` habilitado
- contexto `H1`
- setup `M5`
- 3 setups iniciales:
  - order block retest
  - liquidity sweep + reclaim
  - breakout + retest
- 2 trailing policies:
  - ATR trailing
  - structural trailing
- gates:
  - session
  - spread
  - slippage

Los chart patterns pueden entrar en una segunda ola, salvo 2 o 3 de mayor robustez.

## Riesgo principal si se implementa mal

El peor error posible sería construir Fast como:

- un mega scanner mezclado
- dependiente de heurísticas SMC lentas
- sin separación setup/trigger
- sin gates reales
- sin custody profesional

Eso produciría un runtime pesado, opaco y poco confiable.

## Conclusión

`FastTraderService` no es una mejora incremental del scanner actual.

Es la siguiente gran fase del backend:

- más velocidad
- más criterio heurístico
- más control operativo
- mejor custody

Y debe construirse con un contrato explícito, no por aproximación.
