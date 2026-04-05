# heuristic-metatrader5-bridge

Resumen breve en español del estado actual del proyecto.

Este repositorio es un laboratorio de trading asistido sobre MetaTrader 5. La idea central no es delegar todo a IA: el nucleo operativo es heuristico, con control de riesgo centralizado, ownership de operaciones y una WebUI de observabilidad. Hoy conviven dos mesas independientes:

- `Fast Desk`: ejecucion rapida, heuristica-first, sin LLM en el camino critico.
- `SMC Desk`: tesis preparadas de mayor estructura, con validacion heuristica y una validacion final por IA opcional.

## Repaso rapido doc vs codigo

El `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md` y la WebUI en `apps/webui/src` estan bastante alineados con el codigo actual.

Lo mas importante que efectivamente existe hoy:

- runtime core unificado;
- conexion MT5 centralizada;
- `OwnershipRegistry` para saber de quien es cada operacion;
- `RiskKernel` como autoridad de riesgo;
- `Fast Desk` separado del `SMC Desk`;
- control plane HTTP;
- WebUI Solid.js real en `apps/webui/src`.

## Como funciona el motor back

El sistema corre como un runtime central que conecta MT5, mantiene estado en RAM y deja que cada mesa opere sobre ese estado.

Flujo general:

```text
MetaTrader 5
-> MT5Connector
-> SubscriptionManager
-> ChartRegistry / ChartWorker por simbolo
-> MarketStateService
-> SymbolSpecRegistry
-> AccountState
-> Control Plane HTTP
-> Fast Desk y SMC Desk
```

El runtime central:

- trae ticks, barras y specs del broker;
- mantiene charts en RAM por simbolo y timeframe;
- refresca cuenta, posiciones, ordenes y exposicion;
- publica todo por API y SSE;
- guarda persistencia operativa en SQLite.

## Conexion con MT5

La conexion a MetaTrader 5 esta centralizada en `MT5Connector`.

Eso significa que:

- el acceso al API MT5 tiene un unico dueño;
- las llamadas de escritura estan serializadas;
- los desks no hablan directamente con MT5 de cualquier manera;
- la ejecucion, cierre y modificacion de niveles pasan por una superficie canonica.

Superficie operativa principal:

- `send_execution_instruction`
- `modify_position_levels`
- `modify_order_levels`
- `remove_order`
- `close_position`
- `find_open_position_id`

Tambien hay chequeos previos para evitar escribir cuando el terminal o la cuenta no estan en condicion de trading.

## Mesa Fast

La `Fast Desk` es la mesa de decisiones rapidas. Su principio es claro: nada de LLM en el camino critico.

Pipeline logico:

```text
contexto
-> setup
-> cooldown
-> risk gate
-> account safe
-> trigger
-> entry policy
-> execution
```

Eso se ve incluso en la WebUI `FastPipeline.tsx`, donde el pipeline tiene 8 etapas canonicas.

Componentes principales:

- `context/service.py`: bias M30, sesion, spread, slippage, stale/regime gates. Hard gates (`stale_feed`, `symbol_closed`, `session_blocked`, `spread_too_wide`, `slippage`, `no_trade_regime`) bloquean inmediatamente; soft gates aplican penalizacion de confianza.
- `setup/engine.py`: setups M5.
- `trigger/engine.py`: trigger en M1, obligatorio antes de ejecutar.
- `pending/manager.py`: vida de pendientes.
- `custody/engine.py`: break-even, trailing, hard cut, no passive underwater.
- `trader/service.py`: orquestador de la mesa fast.
- `workers/symbol_worker.py`: un worker por simbolo.
- `runtime.py`: orquestador de ciclo de vida de workers con market-gate (solo crea workers para mercados abiertos segun horarios del EA + reloj de sistema).

Idea operativa:

- la mesa fast no dispara por intuicion libre;
- primero filtra contexto;
- despues busca setup;
- luego exige trigger fino;
- pasa por risk y politica de entrada;
- y recien al final ejecuta o administra la posicion.

Es una mesa mas cercana a una maquina de decisiones tacticas que a un chat trader.

## Mesa SMC

La `SMC Desk` es la mesa de tesis preparadas. Trabaja mas lento y con mas estructura.

Su pipeline real es:

```text
scanner heuristico
-> analista heuristico
-> validador heuristico
-> validador LLM opcional (secuencial, una consulta a la vez)
-> thesis store
```

El dispatch procesa un simbolo completo antes de pasar al siguiente. La bandeja de salida hacia LocalAI siempre tiene como maximo una consulta. Esto evita saturar la GPU cuando hay multiples simbolos activos.

En esta mesa se buscan zonas y contextos donde valga la pena preparar una operacion, no entrar por impulso.

Analisis heuristico SMC:

- estructura de mercado;
- order blocks;
- fair value gaps;
- liquidez;
- fibonacci;
- elliott;
- confluencias.

La IA aca no deberia inventar el setup desde cero. Su rol actual es mas fino:

- la heuristica arma la tesis;
- los validadores duros la filtran;
- y la IA, si esta habilitada, hace una validacion final opcional.

Ese enfoque es bueno para laboratorio porque deja la tesis apoyada en estructura real antes de agregar una capa semantica.

## Enfasis en SMC

La parte mas prometedora del proyecto hoy es SMC.

La direccion del repo sugiere una meta bastante clara:

- construir una zona de ejecucion de tesis listas y aprobadas;
- trabajar como una especie de estacion de preparacion y disparo;
- algo conceptualmente cercano a una consola estilo NinjaTrader, pero dentro de Solid.js y del control plane;
- siempre con guardas de riesgo de cuenta.

Los traders autonomos siguen en desarrollo. En especial SMC parece apuntar menos a "tradear por impulso" y mas a:

- detectar una zona valida;
- preparar una tesis con invalidaciones;
- esperar confirmacion;
- y habilitar una ejecucion cuidada cuando el contexto cierre.

## Manejo de Risk

El riesgo no queda repartido de forma difusa. En este repo la autoridad es `RiskKernel`.

Responsabilidades:

- perfiles de riesgo;
- limites efectivos;
- asignacion de presupuesto por desk;
- control de uso;
- kill switch;
- bloqueo de nuevas entradas cuando corresponde.

Ademas `OwnershipRegistry` ayuda a que cada operacion tenga dueño claro:

- `fast_owned`
- `smc_owned`
- `inherited_fast`

Eso importa mucho porque evita que dos mesas administren mal la misma posicion.

En terminos simples:

- `Fast` decide rapido, pero no manda sola;
- `SMC` prepara tesis, pero tampoco ejecuta sin marco;
- `RiskKernel` pone los limites;
- `OwnershipRegistry` ordena la custodia;
- `MT5Connector` es la unica puerta de salida real hacia el broker.

## Paneles front

La WebUI actual esta en `apps/webui/src` y usa `Solid.js`.

Rutas reales detectadas en `apps/webui/src/App.tsx`:

- `/` `RuntimeOverview`
- `/operations`
- `/terminal`
- `/alerts`
- `/risk`
- `/fast`
- `/fast/pipeline`
- `/smc`
- `/ownership`
- `/mode`
- `/symbols`
- `/settings`

Descripcion rapida de cada panel:

- `Runtime Overview`: tablero principal del runtime. Muestra salud del bridge, conexion MT5, feed, SSE, broker sessions y estado general del desk.
- `Operations`: posiciones, ordenes, actividad broker y exposicion por simbolo.
- `Terminal`: identidad de cuenta, metricas de cuenta y specs del broker por simbolo.
- `Alerts`: alertas criticas, warnings, actividad broker y cambios de estado.
- `Risk`: vista de salud, limites y estado de riesgo de la cuenta.
- `Fast Desk`: panel operativo de la mesa fast con status, actividad, señales y trade log.
- `Fast Pipeline`: visualizacion didactica del pipeline fast etapa por etapa, incluyendo accepted/rejected/pending.
- `SMC Desk`: vista de tesis SMC, zonas, candles y niveles, con chart interactivo.
- `Ownership`: quien controla cada operacion y su historial.
- `Mode`: intenta separar modo de cuenta MT5 y modo de producto, aunque todavia marca varias partes como parciales o planned.
- `Symbols`: catalogo, desks asignados y specs por simbolo.
- `Settings`: configuracion viva de modelos, SMC, Fast, Ownership y Risk, con parte aun en evolucion.

## Modulos principales para leer primero

- `apps/control_plane.py`
- `src/heuristic_mt5_bridge/infra/mt5/connector.py`
- `src/heuristic_mt5_bridge/core/`
- `src/heuristic_mt5_bridge/fast_desk/`
- `src/heuristic_mt5_bridge/smc_desk/`
- `apps/webui/src/App.tsx`
- `apps/webui/src/routes/FastDesk.tsx`
- `apps/webui/src/routes/FastPipeline.tsx`
- `apps/webui/src/routes/SmcDesk.tsx`
- `apps/webui/src/routes/Risk.tsx`
- `apps/webui/src/routes/Ownership.tsx`

## Idea final

Este proyecto no se presenta hoy como "un bot LLM". Se parece mas a una mesa experimental seria con cuatro pilares:

- heuristica de mercado;
- estado vivo y conexion fuerte con MT5;
- risk y ownership centralizados;
- UI de control para observar y operar con criterio.

La mesa Fast busca decision tactica rapida sin depender de IA. La mesa SMC busca tesis mas maduras, con estructura, confluencia y una validacion final opcional por IA. Todo sigue en desarrollo, pero la base ya muestra una arquitectura bastante concreta y didactica.
