# MT5 Data Ownership Boundary

Date: 2026-03-23

## Objetivo

Definir con claridad qué datos deben venir del `MetaTrader5 Python connector` y cuáles deben venir de componentes MQL5 dedicados (`Service` / `EA`) en la nueva repo `heuristic-metatrader5-bridge`.

La meta es simple:

- la `WebUI` debe listar símbolos reales de la cuenta/broker conectada;
- el backend debe conocer el universo disponible, sus specs, su estado de cuenta y su `chart-ram`;
- la ruta crítica del `Fast Desk` debe quedar libre de dependencias LLM;
- los indicadores MT5 nativos deben seguir disponibles con una activación manual clara desde la UI;
- la frontera entre `connector` y `EA/Service` debe ser estable y fácil de operar.

## Principio Rector

La nueva repo debe tratar al `MT5 connector` como la fuente base del estado operativo y a los componentes MQL5 como extensiones especializadas.

Regla:

- `connector` = estado base, trading, mercado, cuenta, catálogo, chart-ram.
- `MQL5 services/EAs` = capacidades que son más directas, más fiables o más naturales dentro del terminal MT5.

## Qué Ya Entrega el MT5 Python Connector

En el repo anterior, `mt5_connector.py` ya entrega casi todo el estado base necesario:

### 1. Identidad del broker/cuenta

- `broker_server`
- `broker_company`
- `account_login`
- `terminal_name`
- `terminal_path`

Esto sale de `account_info()` y `terminal_info()`.

### 2. Universo de símbolos disponible

- catálogo completo del broker con `symbols_get()`
- `visible`, `selected`, `custom`
- `description`
- `path`, `asset_class`, `path_group`, `path_subgroup`
- `digits`, `point`, `trade_mode`, `volume_min/max/step`, etc.

Esto es exactamente lo que la futura `WebUI` necesita para que el operador seleccione símbolos reales de la cuenta conectada.

### 3. Especificación operativa de cada símbolo

- `tick_size`, `tick_value`, `contract_size`
- `spread`, `stops_level`, `freeze_level`
- monedas base/profit/margin
- modos de trade/filling/order/expiration
- márgenes y swaps

Esto alimenta:

- validación de órdenes
- sizing
- fast heuristics
- custody

### 4. Snapshot de mercado y chart base

- `bid`, `ask`, `spread`
- `ohlc`
- `tick_time`
- `last_bar_timestamp`
- `server_time_offset_seconds`

Y además ya quedó corregido en el repo anterior para que las velas internas queden canónicas en `UTC`.

Esto debe seguir siendo la base del `chart-ram`.

### 5. Estado de cuenta y exposición

- `balance`, `equity`, `margin`, `free_margin`, `margin_level`
- `profit`, `drawdown`
- posiciones abiertas
- órdenes pendientes
- exposición agregada por símbolo
- deals recientes
- orders history reciente

Esto es núcleo del `Fast Desk` y del `live custody`.

### 6. Ejecución

El `connector` también ya es el camino correcto para:

- `login()` / cambio de cuenta
- `probe_account()`
- `send_execution_instruction()`

O sea: la ejecución debe seguir anclada ahí.

## Qué Debe Seguir Viniendo Desde MQL5

Hay dos piezas donde MQL5 sigue teniendo mucho sentido.

### 1. Broker Sessions Service

Archivo actual:

- [LLMBrokerSessionsService.mq5](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/mql5/LLMBrokerSessionsService.mq5)

Responsabilidad:

- consultar `SymbolInfoSessionTrade()` y `SymbolInfoSessionQuote()`
- devolver ventanas reales de trade/quote por símbolo
- hacerlo desde el terminal, no por inferencia indirecta

Motivo:

- este dato es más natural y más confiable desde MQL5;
- además está vinculado al universo real del `Market Watch` del terminal;
- sirve para apagar o encender heurísticas, análisis y entradas por símbolo.

Protocolo actual:

- `TCP socket` local
- `Service` MQL5
- patrón `pull -> fetch_sessions -> ack`

Conclusión:

- en la nueva repo debe permanecer como `servicio especializado`;
- no debe mezclarse con chart data ni con indicadores;
- debe ser la autoridad de `session gate`.

### 2. Indicator Service EA

Archivo actual:

- [LLMIndicatorServiceEA.mq5](/e:/GITLAB/Sergio_Privado/llm-metatrader5-bridge/mql5/LLMIndicatorServiceEA.mq5)

Responsabilidad:

- calcular indicadores MT5 nativos
- responder a requests puntuales de Python

Protocolo actual:

- `Common Files`
- requests en `llm_mt5_bridge\\indicator_requests\\`
- responses en `llm_mt5_bridge\\indicator_snapshots\\`

Motivo:

- muchos indicadores son más directos, más baratos y más naturales dentro de MT5;
- no vale la pena reimplementar todos en Python para la primera etapa;
- el operador ya puede activarlo manualmente desde el terminal.

Conclusión:

- sigue siendo válido para `v1`;
- más adelante puede migrarse a `TCP socket`, pero no hace falta para arrancar la nueva repo;
- la UI solo debe dejar muy claro cuándo está `active / inactive / stale`.

## Boundary Recomendada Para La Nueva Repo

### MT5 Connector debe ser owner de:

- broker/account identity
- symbol catalog
- symbol specifications
- ticks / bid / ask / spread
- OHLC bootstrap e incremental updates
- `server_time_offset_seconds`
- chart normalization a `UTC`
- chart-ram por símbolo/timeframe
- account state
- positions / orders
- exposure state
- execution

### BrokerSessionsService debe ser owner de:

- trade sessions por símbolo
- quote sessions por símbolo
- gating real `open / closed`
- refresh cuando cambia el universo activo

### IndicatorServiceEA debe ser owner de:

- indicadores MT5 nativos bajo demanda
- snapshots de indicadores listos para enrichment

### La LLM no debe ser owner de:

- datos de mercado
- estados de cuenta
- indicadores base
- sessions gating
- chart-ram
- cálculos de riesgo críticos

## Cómo Debe Funcionar La WebUI

La `WebUI` bien diseñada no debe pedirle al operador que “configure el sistema” a mano salvo donde MT5 realmente lo exige.

### Flujo deseado

1. El backend conecta a MT5.
2. El backend obtiene identidad de broker/cuenta.
3. El backend carga el `symbol catalog` completo.
4. La UI muestra los símbolos disponibles del broker/cuenta conectada.
5. El operador elige el universo activo para el desk.
6. El backend hace bootstrap de `chart-ram` para ese universo activo.
7. El backend encola refresh de sesiones para ese mismo universo.
8. Si el `Indicator EA` no está activo, la UI muestra instrucciones claras de activación manual.

### Punto importante

No conviene construir `chart-ram` para todo el broker entero por defecto si el broker expone cientos o miles de símbolos.

Modelo recomendado:

- conocer todo el `symbol catalog`;
- bootstrapping de `chart-ram` solo para el `active universe` seleccionado en la UI;
- opcionalmente, prewarm de un subconjunto `visible` o `favorites`.

Eso mantiene velocidad y evita inflar RAM sin sentido.

## Manual Steps Que Deben Quedar En UI

### Indicadores

La UI debe mostrar una tarjeta o panel de onboarding:

- nombre del EA requerido
- ruta esperada dentro de MT5
- pasos para compilarlo y adjuntarlo
- estado actual del bridge
- timestamp del último snapshot importado

Estado mínimo visible:

- `inactive`
- `waiting_first_snapshot`
- `healthy`
- `stale`

### Broker Sessions Service

Aunque sea un `Service` y no un `EA`, operativamente también necesita visibilidad en UI.

La UI debería mostrar:

- puerto configurado
- último pull exitoso
- símbolos activos en registry
- estado del session gate

## Recomendación De Arquitectura Para V1

### Mantener ahora

- `MT5 Python connector` como backbone
- `BrokerSessionsService` por `TCP`
- `IndicatorServiceEA` por `Common Files`

### Posponer para v2

- migrar indicadores a `TCP`
- exportar imágenes de chart desde MT5
- snapshot visual para `SMC multimodal`

La razón es pragmática:

- el cuello crítico actual no es el protocolo de indicadores;
- el cuello crítico era la latencia LLM y la arquitectura de desks;
- el `Fast Desk` mejora antes separando heurística y ownership de estado que reescribiendo el EA de indicadores.

## Diseño Operativo Recomendado

### Core Runtime

Debe centralizar:

- connector lifecycle
- symbol catalog cache
- symbol spec cache
- chart-ram
- session registry import
- runtime db
- account/exposure state

### Fast Desk

Debe consumir:

- `chart-ram`
- `session gate`
- `account/exposure`
- `symbol specs`

Y no debe depender de:

- indicator EA para poder arrancar
- LLM para decidir

### SMC Desk

Puede consumir:

- `chart-ram`
- indicator enrichment
- chart snapshots / imágenes
- validación multimodal opcional

Y sí puede tolerar latencia mayor.

## Decisión

Para la nueva repo:

- `MT5 connector` será la fuente primaria del estado operativo.
- `BrokerSessionsService` será la autoridad de sesiones por símbolo.
- `IndicatorServiceEA` será opcional pero recomendado para enrichment.
- la `WebUI` será la encargada de:
  - mostrar símbolos disponibles;
  - permitir elegir el universo activo;
  - mostrar el estado del bridge de sesiones;
  - guiar la activación manual del `Indicator EA`.

## Próximo Paso Recomendado

Con esta frontera definida, el siguiente paso técnico correcto es:

1. migrar `mt5_connector.py` al `shared core` de la nueva repo;
2. crear un `core_runtime` que exponga:
   - broker identity
   - symbol catalog
   - symbol specs
   - active universe
   - chart-ram status
   - account/exposure state
   - broker session registry status
3. luego recién construir la primera `WebUI` sobre esos contratos.

## Cuándo Conviene Usar GPT-5.3-Codex

Sí conviene usar `gpt-5.3-codex` cuando pasemos a:

- migrar `mt5_connector` completo a la nueva estructura;
- dividir `core_runtime` en servicios internos limpios;
- o construir una `WebUI` especializada con contratos ya fijos.

---

## RESTRICCIONES OBLIGATORIAS — Datos prohibidos en disco

Las siguientes restricciones son inviolables. Ningún constructor puede ignorarlas:

### Archivos que NUNCA deben existir en disco durante el runtime

- `storage/live/core_runtime.json` — **prohibido**
- `storage/live/*.json` — **prohibido**
- `storage/indicator_snapshots/*.json` — **prohibido** (copias locales de snapshots de indicadores)

El `IndicatorBridge` recibe el snapshot de indicadores en memoria y lo aplica; nunca debe escribir una copia en `storage/indicator_snapshots/`.

### Columnas prohibidas en SQLite

Las siguientes columnas están **prohibidas** en cualquier tabla SQLite:

```sql
bid REAL,
ask REAL,
last_price REAL,
tick_age_seconds REAL,
bar_age_seconds REAL,
feed_status TEXT,
```

Estos valores son dinámicos. Solo existen en RAM.

### Variables de entorno prohibidas

Las siguientes variables de entorno **no deben existir** en ninguna configuración:

- `CORE_LIVE_PUBLISH_SECONDS` — activa el loop que escribe `core_runtime.json`
- `CORE_MARKET_STATE_CHECKPOINT_SECONDS` con columnas de bid/ask — activa escritura de estado live a SQLite

---

## RESTRICCIONES OBLIGATORIAS — Partición por broker

El sistema está diseñado desde el inicio para N instancias MT5 en paralelo (diferentes brokers, diferentes cuentas). Esta arquitectura es una premisa base, no una característica futura.

### PK obligatoria para toda tabla broker-dependiente

```sql
-- CORRECTO
PRIMARY KEY (broker_server, account_login, symbol)

-- PROHIBIDO
PRIMARY KEY (symbol)
```

Tablas que requieren partición por `(broker_server, account_login)`:
- `symbol_spec_cache`
- `symbol_catalog_cache`
- `market_state_cache`
- `account_state_cache`
- `position_cache`
- `order_cache`
- `exposure_cache`
- `execution_event_cache`

### Estructuras RAM

Ningún diccionario o registro en RAM debe usar `symbol` como clave sin que el contexto de broker/cuenta sea explícito e inequívoco.

Si en el futuro se opera con N `CoreRuntimeService` en paralelo, cada uno debe tener su propio scope de RAM completamente aislado.

Todavía no es necesario para este documento.
