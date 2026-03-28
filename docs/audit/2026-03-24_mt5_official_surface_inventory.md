# MT5 Official Surface Inventory

Fecha: 2026-03-24

## Proposito

Este documento no es el manual del conector.

Su objetivo es fijar, desde documentacion oficial de MetaQuotes, la superficie
MT5 que debe considerarse obligatoria para certificar el bridge antes de seguir
con traders, ownership, risk kernel o WebUI.

## Fuentes oficiales

Python Integration - MQL5 Reference:

- `initialize`: https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py
- `login`: https://www.mql5.com/en/docs/python_metatrader5/mt5login_py
- `shutdown`: https://www.mql5.com/en/docs/python_metatrader5/mt5shutdown_py
- `symbol_info`: https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py
- `symbol_info_tick`: https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfotick_py
- `copy_rates_from_pos`: https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py
- `positions_get`: https://www.mql5.com/en/docs/python_metatrader5/mt5positionsget_py
- `orders_get`: https://www.mql5.com/en/docs/python_metatrader5/mt5ordersget_py
- `history_orders_get`: https://www.mql5.com/en/docs/python_metatrader5/mt5historyordersget_py
- `history_deals_get`: https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py
- `order_calc_margin`: https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcmargin_py
- `order_check`: https://www.mql5.com/en/docs/python_metatrader5/mt5ordercheck_py
- `order_send`: https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py

Trade request actions and order semantics:

- `TRADE_ACTION_DEAL`
- `TRADE_ACTION_PENDING`
- `TRADE_ACTION_SLTP`
- `TRADE_ACTION_MODIFY`
- `TRADE_ACTION_REMOVE`
- `TRADE_ACTION_CLOSE_BY`

Estas acciones quedan descritas en la documentacion oficial de `order_check()`
y `order_send()`.

## Superficie oficial minima

### Sesion

- `initialize`
- `login`
- `shutdown`

### Datos de mercado

- `symbol_info`
- `symbol_info_tick`
- `copy_rates_from_pos`
- `symbol_select`

### Estado operativo

- `positions_get`
- `orders_get`
- `history_orders_get`
- `history_deals_get`

### Pre-trade

- `order_calc_margin`
- `order_check`

### Ejecucion y custodia

- `order_send` con `TRADE_ACTION_DEAL`
- `order_send` con `TRADE_ACTION_PENDING`
- `order_send` con `TRADE_ACTION_SLTP`
- `order_send` con `TRADE_ACTION_MODIFY`
- `order_send` con `TRADE_ACTION_REMOVE`
- `order_send` con `TRADE_ACTION_CLOSE_BY` como capacidad oficial opcional

## Traducion obligatoria a superficie de bridge

La repo heuristica no necesita exponer los nombres raw de MT5, pero si debe
dar cobertura funcional a esta superficie:

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

### Patrones construidos encima

- trailing stop
- cierre parcial
- post-fill SL/TP
- cancelacion por vencimiento
- adopcion de posiciones y ordenes heredadas

## Estado actual en la repo heuristica

Archivo auditado:

- `src/heuristic_mt5_bridge/infra/mt5/connector.py`

### Presentes

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

### Faltantes en la clase publica

- `modify_position_levels`
- `modify_order_levels`
- `remove_order`
- `close_position`
- `find_open_position_id`

## Hallazgo empirico del broker actual

Evidencia live en cuenta demo actual:

- `storage/certification/20260324T081130Z_2587e882.json`
- `storage/certification/20260324T081538Z_e78e2b4a.json`
- `storage/certification/20260324T081633Z_571aa621.json`

Resultado observado:

- `order_check()` y `order_send()` funcionaron correctamente cuando el `comment`
  fue vacio
- `send_execution_instruction()` fallo cuando el request incluyo `comment`
  poblado, con error MT5 `Invalid "comment" argument`
- `probe_account()` sobre cuenta invalida pudo degradar la sesion viva del
  terminal hasta dejar `initialize()` en `Authorization failed`

Impacto:

- hoy la ejecucion basica del bridge esta confirmada en `market`, `limit` y
  `stop`, pero solo con `comment=""`
- el modelo de ownership basado en comentarios no puede darse por resuelto
- el cambio o probe de cuenta no puede tratarse como operacion inocua
- la futura WebUI debe alertar a operadores que una autenticacion fallida puede
  bajar la sesion MT5 o deshabilitar AutoTrading
- cualquier constructor futuro debe separar claramente:
  - capacidad de ejecutar ordenes
  - capacidad de etiquetarlas de forma confiable

## Referencia de la repo vieja

Archivo de comparacion:

- `E:\GITLAB\Sergio_Privado\llm-metatrader5-bridge\python\mt5_connector.py`

La repo vieja si expone:

- `send_execution_instruction`
- `modify_position_levels`
- `modify_order_levels`
- `remove_order`
- `close_position`
- `find_open_position_id`

## Lista de funciones a confirmar con exclusion explicita

Estas son las funciones que conviene confirmar una por una antes de fijar el
prompt constructor final.

### Seguramente obligatorias

- `initialize`
- `login`
- `shutdown`
- `symbol_info`
- `symbol_info_tick`
- `copy_rates_from_pos`
- `positions_get`
- `orders_get`
- `history_orders_get`
- `history_deals_get`
- `order_calc_margin`
- `order_check`
- `order_send` con `DEAL`
- `order_send` con `PENDING`
- `order_send` con `SLTP`
- `order_send` con `MODIFY`
- `order_send` con `REMOVE`

### A confirmar si el stack las usara de forma nativa

- `TRADE_ACTION_CLOSE_BY`
- `buy stop limit`
- `sell stop limit`
- account switch a otra cuenta durante la misma sesion de prueba
- adopcion y custodia de posiciones no propias
- adopcion y custodia de ordenes pendientes no propias

## Casos de prueba esperados

El runner de certificacion agregado en `tests/integration/mt5_connector_certification.py`
cubre cuatro capas:

- superficie publica requerida del conector
- primitivas oficiales raw MT5
- operaciones read-only del bridge
- operaciones live del bridge y su custodia

Los casos live quedan filtrables por include/exclude para que el usuario marque
que no usara el stack antes de correr la campana completa.
