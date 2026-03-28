# Release Note 2026-03-22

## Resumen

**Scalping Desk Hardening** — endurecimiento completo de la mesa scalping-intradía en 8 fases. Restringe estrategias a scalping+intradía, eleva R:R mínimo a 1:4/1:5, implementa enforcement post-LLM (corte de pérdida al 1.5%, trailing obligatorio, prohibición de pasividad en posiciones perdedoras), reduce tolerancias SL/TP de ±10% a ±2%, y endurece risk tiers a nivel de .env y fallback defaults.

**Crypto lot-sizing fix (BTCUSD 500-lot bug)** — se detectó que el trader proponía SL de apenas $10 en un activo de $68,500 (0.015%), produciendo `suggested_lot=500` (el máximo del broker). Se agregaron 6 guardas defensivas:
1. **Notional value cap** en `compute_symbol_position_limit()`: exposición notional máxima = 20% del balance.
2. **Notional value cap (fallback)**: misma protección en la fórmula legacy cuando no hay specs disponibles.
3. **SL distance guard**: rechaza SL < 0.15% para crypto, < 0.05% para forex.
4. **Hard block**: `stop_loss_too_tight` no puede ser overrideado por el LLM.
5. **Lab override block**: `approved_limited` en lab tampoco bypasea SL flag.
6. **Execution guidance**: nota explicativa al LLM cuando SL es rechazado.

**Analyst & Supervisor Context Minimization (FASE 12-B)** — tool .md auto-append en `prompt_loader.py`, payload reducido en market_analyst y trade_supervisor, 7 archivos de tools creados/podados.

**Chairman display_text fix** — los work orders (`analyst_request`, `trader_request`, `risk_request`) ahora incluyen `display_text` para renderizar correctamente en Office Chat.

## Cambios principales

### 1. Scalping Desk Hardening (8 fases)

**FASE 1 — Estrategias restringidas**
- Nuevo `DESK_STRATEGY_TYPES = ("scalping", "intradia")` en `trader_runtime.py`
- Todas las iteraciones de generación de lanes usan `DESK_STRATEGY_TYPES` en vez de `STRATEGY_TYPES`
- `STRATEGY_TYPES` se mantiene para validación de schema (incluye imports SMC)

**FASE 2 — R:R elevado**
- `STRATEGY_RR`: scalping 1.5→4.0, intradía 2.0→5.0
- `JSON_TEMPLATE` actualizado a `scalping|intradia`

**FASE 3 — Tolerancias SL/TP**
- Sanity check: ±10% → ±2% en `_parse_llm_action()` y `execution_bridge.py`
- `build_default_protection()`: fallback distance 0.30% crypto / 0.15% forex (antes 0.35% uniforme)
- TP multiplier: 2.2x → 4.0x
- Nuevo helper `_is_crypto()` con set `_CRYPTO_SYMBOLS`

**FASES 4-6 — Enforcement post-LLM**
- `_enforce_loss_cut()`: cierre forzado cuando pérdida flotante > 1.5% equity
- `_enforce_trailing()`: trailing obligatorio en toda posición con profit
- `_enforce_no_passive_underwater()`: redirige `maintain_and_monitor` → `tighten_stop` en posiciones perdedoras
- `_apply_enforcement()`: cadena las tres reglas, se ejecuta en `build_actions()` y `build_actions_heuristic()`

**FASE 7 — Prompts alineados**
- `live_execution_trader/system.md`: 6 HARD RULES (desk scope, R:R ≥1:4, 1.5% loss cut, trailing obligatorio, no passive on losers, accept losses)
- `live_execution_trader/user.md`: reglas de loss-cut, trailing y no-passive inline
- `sltp_methods.md`: tablas ATR y porcentaje actualizadas (solo scalping+intradía), R:R 4:1/5:1
- `candidate_validation.md`: ≥1:4 Good, 1:3-1:4 Marginal, <1:3 Reject

**FASE 8 — Risk tiers**
- Fallback defaults actualizados en `risk_manager_runtime.py` y `trade_supervisor_runtime.py`
- Low: drawdown 2%, per-trade 0.30%, 1 pos/symbol, 3 total
- Medium: drawdown 3.5%, per-trade 0.50%, 2 pos/symbol, 5 total
- High: drawdown 5%, per-trade 0.75%, 3 pos/symbol, 10 total
- Chaos: drawdown 15%, per-trade 2.0%, 5 pos/symbol, 20 total

### 2. Context Minimization — Analyst & Supervisor (FASE 12-B)

- `prompt_loader.py`: `load_prompt()` auto-detecta `tools/` directory y appende contenido
- `market_analyst_runtime.py`: tool .md auto-append, payload compactado
- `trade_supervisor_runtime.py`: tool .md auto-append, payload compactado
- 7 archivos de tools creados/podados en `prompts/market_analyst/tools/` y `prompts/trade_supervisor/tools/`
- `trader/user.md`: eliminada referencia duplicada a `{{strategy_tools}}`

### 3. Chairman display_text fix

- `chairman_runtime.py`: work orders (`analyst_request`, `trader_request`, `risk_request`) ahora emiten `display_text` en content dict
- Fix de renderizado en Office Chat: antes mostraba `str(dict)` crudo, ahora muestra texto legible

## Archivos tocados

| Archivo | Acción |
|---|---|
| `python/trader_runtime.py` | Modificado (FASE 1+2) |
| `python/live_execution_trader_runtime.py` | Modificado (FASES 3-6, enforcement) |
| `python/execution_bridge.py` | Modificado (FASE 3, tolerancia) |
| `python/risk_manager_runtime.py` | Modificado (FASE 8, defaults + crypto lot-sizing fix) |
| `python/trade_supervisor_runtime.py` | Modificado (FASE 8 + 12-B) |
| `python/market_analyst_runtime.py` | Modificado (FASE 12-B) |
| `python/prompt_loader.py` | Modificado (FASE 12-B) |
| `python/chairman_runtime.py` | Modificado (display_text fix) |
| `python/prompts/live_execution_trader/system.md` | Modificado (FASE 7) |
| `python/prompts/live_execution_trader/user.md` | Modificado (FASE 7) |
| `python/prompts/live_execution_trader/tools/sltp_methods.md` | Modificado (FASE 7) |
| `python/prompts/trade_supervisor/tools/candidate_validation.md` | Creado (FASE 12-B + 7) |
| `python/prompts/market_analyst/tools/` | Creados (FASE 12-B) |
| `python/prompts/trade_supervisor/tools/` | Creados (FASE 12-B) |
| `python/prompts/trader/user.md` | Modificado (limpieza) |
| `python/schemas/trader_brief.schema.json` | Modificado (minor) |
| `docs/plans/2026-03-22_scalping_desk_hardening.md` | Creado |
| `docs/audit/2026-03-21_*` | Creados (auditoría contexto) |
| `README.md` | Actualizado |
| `docs/LIVE_EXECUTION_TRADER.md` | Actualizado |
| `docs/TRADER_ROLE.md` | Actualizado |
| `docs/RISK_MANAGER_ROLE.md` | Actualizado |

## Documentación

- `docs/plans/2026-03-22_scalping_desk_hardening.md` — plan completo de 8 fases con diagnóstico y justificación
- `docs/audit/2026-03-21_*` — auditorías de contexto analyst/supervisor

---

# Release Note 2026-03-21

## Resumen

**Trader Context Minimization** — reducción del ~89% en tokens de prompt del trader (de ~31k a ~3.7k) mediante un `trader_brief` estructurado de ~2KB que reemplaza el `analysis_input` completo de ~15-30KB. Migración en 7 fases, validada en producción con stack completo.

## Cambios principales

### 1. `trader_brief` — nuevo contrato compacto

- Nuevo schema `python/schemas/trader_brief.schema.json` (19 propiedades, 11 required)
- Nueva función `build_trader_brief_from_runtime()` en `trader_runtime.py`
- El brief condensa: precio, niveles clave, estructura M5/H1, posiciones activas, snapshot de cuenta, directiva de riesgo, tesis y zonas de entrada
- Se persiste en JSON (`storage/trader_runtime/`) y SQLite (`trader_brief_cache`)

### 2. Supervisor handoff y chairman enrichment

- `trade_supervisor_runtime.py`: nueva función `_build_trader_handoff()` que estructura el paso al trader
- `chairman_runtime.py`: enriquece `trader_request` con 5 campos ejecutivos (`desk_summary_hint`, `analyst_bias`, `analyst_confidence`, `risk_decision`, `trader_status`)

### 3. Trader rewrite — consumo exclusivo de brief

- Prompts reescritos: `system.md` (381 words) y `user.md` (350 words) enfocados en brief
- Nuevas funciones: `build_messages_from_brief()`, `_build_strategy_lane_from_brief()`, `heuristic_trader_payload_from_brief()`, `_normalize_group_payload_from_brief()`
- `normalize_trader_intent()` ahora acepta `analysis_input: dict | None` + kwarg `trader_brief`

### 4. Legacy cleanup

6 funciones eliminadas de `trader_runtime.py`:
- `build_composite_analysis_input()`
- `build_messages()`
- `_extract_strategy_context()`
- `_build_strategy_lane()`
- `heuristic_trader_payload_from_input()`
- `_normalize_group_payload()`

### 5. Persistence y trazabilidad

- Nueva tabla `trader_brief_cache` en `runtime.db` (brief_id PK, symbol, timeframe, desk_bias, linked_thesis_id, created_at, trader_brief_payload_json)
- Nuevo campo opcional `linked_brief_id` en `trader_intent.schema.json`
- Cada `trader_intent` queda trazado a su brief de origen

### 6. Validación en producción

- 28 intents generados con stack completo, todos con `linked_brief_id`
- 7 briefs persistidos en `trader_brief_cache`
- 4 estrategias por símbolo (scalping, intradia, swing, positions) sin pérdida funcional
- Brief promedio: ~2KB vs ~15-30KB del analysis_input previo

## Archivos tocados

| Archivo | Acción |
|---|---|
| `python/schemas/trader_brief.schema.json` | Creado |
| `python/schemas/trader_intent.schema.json` | Modificado |
| `python/trader_runtime.py` | Modificado (mayor) |
| `python/trade_supervisor_runtime.py` | Modificado |
| `python/chairman_runtime.py` | Modificado |
| `python/runtime_db.py` | Modificado |
| `python/prompts/trader/system.md` | Reescrito |
| `python/prompts/trader/user.md` | Reescrito |

## Documentación

- `docs/audit/2026-03-21_trader_context_minimization_execution_report.md` — reporte completo de ejecución de las 7 fases

---

# Release Note 2026-03-18

## Resumen

Esta entrega introduce la **Mesa SMC** como un proceso paralelo e independiente que opera con Smart Money Concepts sobre timeframes D1 y H4. La mesa SMC convive con el flujo intraday sin interferir con sus límites de posición, tiene visibilidad propia en el control plane, y sus intents llegan al mismo `execution_bridge` que el resto del sistema.

Se corrigió además una limitación crítica de configuración que impedía que la mesa SMC funcionara: `MT5_WATCH_TIMEFRAMES` no incluía `H4` ni `D1`.

## Cambios principales

### 1. Mesa SMC completa

Nuevo proceso `run_smc_desk.py` que arranca dos hilos daemon:

**Scanner (`smc_heuristic_scanner.py`)**
- Lee candles D1 y H4 de `MarketStateService` re-bootstrapeando desde disco al inicio de cada ciclo (evita datos stale)
- Detecta zonas usando `smc_zone_detection/`:
  - Order Blocks (bullish/bearish con confirmación de impulso)
  - Fair Value Gaps con filtro de ruido
  - Liquidity pools y sweeps
  - Estructura de mercado: trend, swings, BOS, CHoCH, premium/discount level
  - Conteo de ondas Elliott
  - Niveles Fibonacci por swing
  - Score de confluencia 0-1 sobre 14 factores
- Persiste zonas en `smc_zone_cache` via `runtime_db`
- Ciclo configurable: `SMC_SCANNER_POLL_SECONDS` (default 300s)
- Log con recuento: `new=X approaching=Y sweeps=Z invalidated=W`; `skipped` cuando faltan barras con detalle `(D1=N H4=M)`

**Scheduler (`smc_scheduler_runtime.py`)**
- Eventos disparadores: `zone_approaching`, `sweep_detected`, `zone_invalidated`
- Revisión periódica: `SMC_PERIODIC_REVIEW_SECONDS` (default 14400s)
- `initial_analysis` para símbolos sin tesis activa al arranque
- Debounce de 300s por símbolo

**Analista (`smc_analyst_runtime.py`)**
- Prompt SMC especializado, modelo configurable `SMC_ANALYST_MODEL`
- Produce `smc_thesis` con `operation_candidates` (entry_zone_high/low, SL, TP1, TP2 con justificaciones)
- Persiste en `smc_thesis_cache`
- Publica al contexto externo via `publish_to_external_context()` para que el desk intraday lo consuma

**Trader (`smc_trader_runtime.py`)**
- Trabaja sobre `smc_thesis` activa y zonas activas del símbolo
- Emite `trader_intent` con `strategy_type=smc_prepared`
- `trader_intent_id` con prefijo `smc_` → `execution_bridge` construye comment MT5 como `ti:smc_...|ex:...`

**Thesis builder (`smc_thesis_runtime.py`)**
- Normaliza y persiste tesis SMC
- Preserva todos los campos de precio en `operation_candidates`
- Maneja `review_strategy` nested, `bias_confidence`, `analyst_notes`, `watch_levels`

### 2. Pool de posiciones independiente para SMC

`risk_manager_runtime` detecta `strategy_type == "smc_prepared"` y usa un pool de conteo separado.

- `open_position_counts_smc()`: filtra `position_cache WHERE comment LIKE 'ti:smc_%'`
- Límites propios: `SMC_MAX_POSITIONS_PER_SYMBOL` y `SMC_MAX_POSITIONS_TOTAL`
- Las posiciones intraday/scalping no consumen ni son afectadas por este pool
- Los limits de postura (`RISK_{POSTURE}_MAX_POSITIONS_*`) aplican solo al desk intraday

### 3. Nuevas tablas en `runtime.db`

- `smc_zone_cache`: zonas activas con `zone_id`, `symbol`, `timeframe`, `zone_type`, `price_high/low`, `quality_score`, `status`
- `smc_thesis_cache`: tesis SMC con operation candidates completos
- `smc_event_log`: registro de eventos de zona con timestamp, tipo y payload

### 4. Visibilidad en Control Plane

Nueva página `/smc` con:
- Tabla de tesis activas por símbolo
- Tabla de zonas activas con quality score y status
- Panel de última tesis con operation candidates
- **Chart interactivo** con TradingView Lightweight Charts v4.1.3:
  - Click en cualquier tesis → carga candles H4 o D1 desde MT5 en tiempo real
  - Selector de timeframe H4 / D1
  - Líneas de precio para: Entry Zone (azul), SL (rojo), TP (verde), Watch levels (amarillo), Fibonacci (violeta)
  - **Línea de precio vivo (bid)** actualizada cada 3s via polling
  - **Precisión decimal dinámica** según `digits` del símbolo MT5 (ej: 5 para forex, 2/3 para índices)
  - Corrección de server time offset para timestamps UTC correctos
  - Panel de strategy cards debajo del chart con resumen numérico de todos los niveles
  - Right offset de 12 barras para visualizar la última vela sin pegarse al borde

Nuevos endpoints:
- `GET /api/v1/smc/thesis?symbol=&limit=`
- `GET /api/v1/smc/zones?symbol=&timeframe=&status=&limit=`
- `GET /api/v1/smc/events?symbol=&limit=`
- `GET /api/v1/smc/candles?symbol=&timeframe=&bars=` — candles OHLC desde MT5 con corrección de offset
- `GET /api/v1/smc/tick?symbol=` — bid/ask/digits en vivo desde MT5

### 5. Integración en el stack

`run_market_state_stack.py` lanza `run_smc_desk.py` automáticamente al final de la secuencia de arranque.

### 6. Corrección crítica de configuración

`MT5_WATCH_TIMEFRAMES` debe incluir `H4` y `D1`.
Sin ellos `market_state_runtime` nunca descargaba esos timeframes y el scanner retornaba `skipped` permanentemente.
Valor corregido: `MT5_WATCH_TIMEFRAMES=M5,H1,H4,D1`

### 7. Resolución de modelos SMC

`agent_models.py` incluye `smc_analyst` y `smc_trader` en `resolve_agent_models()`.

### 8. Variables de entorno nuevas

```dotenv
# SMC Scanner
SMC_SCANNER_ENABLED=true
SMC_SCANNER_POLL_SECONDS=300
SMC_SCANNER_SYMBOLS=EURUSD,GBPUSD,USDJPY,USDCHF
SMC_ZONE_APPROACH_PCT=1.5
SMC_MIN_IMPULSE_CANDLES=3
SMC_MAX_ACTIVE_ZONES_PER_SYMBOL=10

# SMC Scheduler
SMC_PERIODIC_REVIEW_SECONDS=14400
SMC_URGENT_ON_SWEEP=true

# SMC Analyst
SMC_ANALYST_MODEL=gemma-3-4b-it-qat
SMC_ANALYST_MAX_TOKENS=4000

# SMC Trader
SMC_TRADER_MODEL=gemma-3-4b-it-qat
SMC_TRADER_MAX_TOKENS=3000

# SMC Position Limits
SMC_MAX_POSITIONS_PER_SYMBOL=3
SMC_MAX_POSITIONS_TOTAL=10
```

## Bugs corregidos

| Bug | Fix |
|---|---|
| `max_tokens` no se enviaba al payload LocalAI en SMC analyst/trader | Agregado `"max_tokens": CFG["max_tokens"]` en ambos `call_localai()` |
| `MarketStateService` stale (bootstrapeado solo al arranque) | `run_scanner_loop()` re-bootstrapea desde disco al inicio de cada ciclo |
| SMC desk no arrancaba con el stack | Agregado `launch_process("smc-desk", ...)` en `run_market_state_stack.py` |
| H4 y D1 nunca descargados de MT5 | `MT5_WATCH_TIMEFRAMES` corregido a `M5,H1,H4,D1` |

---

# Release Note 2026-03-17

## Resumen

Esta entrega consolidó el paso de un `trader` mono-idea a un flujo multi-estrategia por símbolo, endureció el corte entre símbolos operables y contexto-only, y corrigió dos bloqueos operativos reales del pipeline vivo:
- rechazo MT5 por `comment` inválido
- sizing absurdo en Forex por no usar especificaciones reales del broker

## Cambios principales

### 1. Trader multi-estrategia `M5 + H1`

- `trader_runtime` ahora combina `M5 + H1` en una sola lectura operativa
- emite estrategias independientes por símbolo:
  - `scalping`
  - `intradia`
  - `swing`
  - `positions`
- cada estrategia se persiste como un `trader_intent` separado
- nuevos campos de contrato:
  - `strategy_type`
  - `strategy_group_id`
  - `source_timeframes`

### 2. Símbolos contexto-only

Se formalizó la separación entre universo operable y símbolos de contexto.

Context-only actuales:
- `VIX`
- `UsDollar`

Estos símbolos pueden informar régimen, volatilidad y sesgo, pero no deben generar:
- `operation_candidates`
- `trader_intents`
- `risk_reviews`
- `execution_instructions`

### 3. Trader con tools tácticas compartidas

`trader` ahora recibe las mismas herramientas tácticas que `live_execution_trader`:
- `python/prompts/live_execution_trader/tools/sltp_methods.md`
- `python/prompts/live_execution_trader/tools/chartism_patterns.md`

Objetivo:
- mejorar diseño de entrada
- mejorar SL/TP
- evitar ignorancia operativa del prompt del trader

### 4. Risk broker-aware

Se agregó captura de especificaciones reales del broker por símbolo desde MT5 y persistencia en `symbol_spec_cache`.

`risk_manager` ahora puede usar:
- `tick_size`
- `tick_value`
- `contract_size`
- `volume_min`
- `volume_max`
- `volume_step`
- `margin_initial`
- ejemplos de margen por lote

Resultado:
- se corrigió el problema de lotajes absurdos y rechazos `No money` en Forex

### 5. Bridge y ejecución

- `execution_bridge` preserva metadata multi-estrategia en el payload
- el `comment` hacia MT5 volvió a formato corto para evitar `Invalid "comment" argument`
- se mantiene soporte para múltiples intents activos del mismo símbolo

### 6. API, UI y monitoreo

Nuevo endpoint:
- `/api/v1/symbol-specs`

Cambios visibles:
- `/trader` ahora muestra `Group`, `Strategy` y `Sources`
- `/api/v1/trader-intents` expone los campos multi-estrategia
- `monitor_trader_degradation_live.py` ahora separa por estrategia y distingue contexto-only

## Impacto operativo observado

- `BTCUSD`, `GBPUSD`, `USDCHF` y `USDJPY` volvieron a entrar al flujo ejecutable
- `risk` dejó de ser el cuello principal una vez aprobado el intent
- la ejecución volvió a abrir operaciones después de corregir `comment` y sizing

## Notas abiertas

- queda un caso legacy sobredimensionado de `USDJPY` útil como referencia negativa para reparar `live_execution_trader`
- sigue pendiente revisar el crecimiento excesivo de logs diarios del EA
