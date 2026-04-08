# Fast Desk — Auditoría Profunda de Heurística del Analista y Fast Trader

**Fecha:** 2026-03-27  
**Auditor:** GitHub Copilot — perspectiva trader de alta velocidad / scalping  
**Alcance:** Análisis de arquitectura, heurística, estrategias y RR3.0+ — solo lectura, sin cambios de código  
**Archivos auditados:**  
- `src/heuristic_mt5_bridge/fast_desk/signals/scanner.py`  
- `src/heuristic_mt5_bridge/fast_desk/context/service.py`  
- `src/heuristic_mt5_bridge/fast_desk/setup/engine.py`  
- `src/heuristic_mt5_bridge/fast_desk/trigger/engine.py`  
- `src/heuristic_mt5_bridge/fast_desk/risk/engine.py`  
- `src/heuristic_mt5_bridge/fast_desk/policies/entry.py`  
- `src/heuristic_mt5_bridge/fast_desk/custody/engine.py`  
- `src/heuristic_mt5_bridge/fast_desk/pending/manager.py`  
- `src/heuristic_mt5_bridge/fast_desk/trader/service.py`  
- `src/heuristic_mt5_bridge/smc_desk/detection/structure.py`  
- `src/heuristic_mt5_bridge/smc_desk/detection/order_blocks.py`  
- `src/heuristic_mt5_bridge/smc_desk/detection/liquidity.py`  
- `docs/audit/2026-03-26_deuda_fast_desk_no_opera.md`  
- `docs/audit/2026-03-26_deuda_tecnica_fast_desk_zero_signals.md`  
- `docs/fast_trader/audit/2026-03-24_fast_trader_gap_audit.md`

---

## 1. Inventario de Herramientas Heurísticas del Analista

### 1.1 Capa de Contexto (`FastContextService`)

| Herramienta | Descripción | TF | Decisión |
|-------------|-------------|-----|----------|
| **Session gate** | Filtra sesiones prohibidas (tokyo/asia por defecto) | UTC timestamp | HARD BLOCK |
| **H1 Bias via `detect_market_structure`** | Detecta bullish/bearish/ranging en H1 mediante swing HH/HL/LH/LL | H1 | Direccional |
| **Volatility regime** | Ratio range/body en M5 → very_low/low/normal/high | M5 24 velas | HARD BLOCK si very_low |
| **Market phase** | trending/ranging/compression/breakout sobre M5 + H1 | M5+H1 | Filtro selectivo |
| **Exhaustion risk** | % candles direccionales + shrinking bodies en M5, CHoCH en H1 | M5+H1 | Eleva umbral confidence |
| **EMA20/EMA50 overextension** | Precio > 2% de EMA20 en H1 = "chasing" | H1 | HARD BLOCK |
| **Spread gate** | Spread % por asset class vs threshold configurable | tick live | HARD BLOCK |
| **Slippage gate** | Divergencia tick vs M1.close > 0.05% | tick+M1 | HARD BLOCK |
| **Stale feed** | Timestamp M1 > 180s = feed muerto | M1 | HARD BLOCK |
| **Symbol trade_mode** | Modo 0 = símbolo cerrado por broker | spec | HARD BLOCK |

### 1.2 Setup Engine (`FastSetupEngine`) — 7 Patrones

| Setup | Tipo | Side | TF base | Confidence asignado | Pending? | RR proyectado |
|-------|------|------|---------|---------------------|----------|---------------|
| **order_block_retest** | SMC zona demanda/oferta | buy/sell | M5 | 0.82 | limit | 3.0× |
| **liquidity_sweep_reclaim** | Barrida SSL/BSL + reversión | buy/sell | M5+H1 | 0.84 | market | 3.0× |
| **breakout_retest** | BOS M5 + pullback al nivel | buy/sell | M5 | 0.79 | stop | 3.0× |
| **wedge_retest** | Wedge alcista/bajista consolidación | buy/sell | M5 | 0.69 | limit | 3.0× |
| **flag_retest** | Flag después de impulso 2.2× rango | buy/sell | M5 | 0.66 | limit | 3.0× |
| **triangle_retest** | Triángulo simétrico contextuado por H1 | buy/sell | M5 | 0.64 | stop | 3.0× |
| **sr_polarity_retest** | Resistencia convertida en soporte (y vice) | buy/sell | M5 | 0.68 | limit | 3.0× |

**Filtros adicionales aplicados sobre los setups:**
- `Premium/Discount zone filter`: compra sólo en descuento, vende sólo en premium (basado en H1 impulse midpoint)
- `Spread buffer adjustigo a SL`: SL ajustado por spread real antes de calcular RR efectivo
- `min_rr = 2.0`: gate de RR efectivo post-spread (configurable, por defecto 2.0 — ⚠️ ver problema #4)

### 1.3 Trigger Engine (`FastTriggerEngine`) — 5 Triggers M1

| Trigger | Mecanismo | Confidence | Notas |
|---------|-----------|------------|-------|
| **micro_bos** | BOS en M1 con `detect_market_structure` (window=2) | 0.86 | Mejor calidad |
| **displacement** | Último cuerpo M1 ≥ 1.8× promedio cuerpos anteriores | 0.81 | Factor configurable |
| **micro_choch** | CHoCH en M1 (ventana 80 velas) | 0.79 | Estructural débil |
| **reclaim** | Close M1 cruza el `retest_level` del setup | 0.74 | Sensible al nivel |
| **rejection_candle** | Mecha opuesta > 1.25× cuerpo en M1 | 0.72 | Menor fiabilidad |

### 1.4 Herramientas SMC reutilizadas (del `smc_desk`)

| Función | Módulo | Uso en Fast Desk |
|---------|--------|-----------------|
| `detect_market_structure()` | `smc_desk/detection/structure.py` | Contexto H1, setup M5, trigger M1, market phase |
| `detect_order_blocks()` | `smc_desk/detection/order_blocks.py` | Setup `order_block_retest` |
| `detect_liquidity_pools()` | `smc_desk/detection/liquidity.py` | Setup `liquidity_sweep_reclaim` |
| `detect_sweeps()` | `smc_desk/detection/liquidity.py` | Setup `liquidity_sweep_reclaim` |

### 1.5 Herramientas SMC disponibles NO utilizadas por Fast Desk

| Función | Módulo | Motivo de exclusión actual |
|---------|--------|---------------------------|
| `detect_fair_value_gaps()` | `smc_desk/detection/fair_value_gaps.py` | No integrada — sin referencia en fast_desk |
| `detect_confluences()` | `smc_desk/detection/confluences.py` | No integrada |
| `fibonacci.py` | `smc_desk/detection/fibonacci.py` | No integrada |
| `elliott.py` | `smc_desk/detection/elliott.py` | No integrada (apropiada para SMC lento) |

---

## 2. Análisis del Pipeline Completo

```
[Context Gate]
   ↓ allowed=True
[Setup Engine M5+H1] → selección por confidence + P/D zone + min_rr
   ↓ setups []
[H1 Alignment Filter]
   ↓ filtered setups
[Phase/Exhaustion Filter]
   ↓ viable setups
[Signal Cooldown]
   ↓ ok
[Risk Gate (RiskKernel)] → dynamic_risk config
   ↓ allowed=True
[Account Safe (drawdown %)]
   ↓ safe=True
[Setup Selection → Trigger M1]
   ↓ confirmed=True
[Entry Policy (position limits)]
   ↓ allowed=True
[Lot Size Calculation]
   ↓ volume
[Execution]
   ↓
[DB + Activity Log]
   ↓
[Custody Loop]
```

---

## 3. Evaluación de RR — Estado vs Objetivo RR3.0+

### 3.1 RR base correcto a nivel de diseño

El `FastSetupConfig.rr_ratio = 3.0` está fijado correctamente. El método `_make_setup()` construye el TP como:

```python
tp = entry + risk * rr   # buy
tp = entry - risk * rr   # sell
```

Esto garantiza **RR=3.0 nominal** en toda señal generada.

### 3.2 PROBLEMA CRÍTICO: `min_rr = 2.0` destruye la garantía de RR3.0

**Archivo:** `setup/engine.py` — `FastSetupConfig`

```python
min_rr: float = 2.0  # hard gate: discard setups below this effective RR after spread adjustment
```

Este gate de `min_rr=2.0` se aplica DESPUÉS de ajustar el SL por spread. Significa que el sistema acepta y ejecuta setups con **RR efectivo entre 2.0 y 3.0**, violando el mandato de RR3.0+.

El SL se expande por el spread (`adj_sl = stop_loss - spread_dist`), lo que REDUCE el RR efectivo sin ajustar el TP de forma compensatoria. Un setup con RR=3.0 nominal puede pasar con RR=2.1 efectivo si el spread consume parte del riesgo.

**Severidad:** ALTA — viola mandato RR3.0+

### 3.3 PROBLEMA: TP no se ajusta por spread

Cuando el spread expande el SL efectivo, el TP permanece en el valor nominal. El riesgo real aumenta pero la recompensa nominal no escala. Para mantener RR3.0 real, el recalculo de TP debería ser:

```python
new_tp = entry ± (adj_risk * rr_ratio)   # TP recalculado desde riesgo real
```

En cambio, el código actual solo ajusta el SL y verifica `eff_rr >= min_rr`, dejando el TP fijo.

**Severidad:** MEDIA — dilución sistemática de RR en mercados con spread variable

### 3.4 PROBLEMA: `scanner.py` (legacy) tiene lógica propia con RR3.0 correcto pero NO se usa

El archivo `signals/scanner.py` tiene `FastScannerConfig.rr_ratio = 3.0` y calcula TP correctamente. Sin embargo, este scanner **no está integrado en el pipeline principal** `FastTraderService`. El pipeline usa exclusivamente `FastSetupEngine`. El scanner legacy es código muerto que confunde el inventario.

---

## 4. Problemas Arquitectónicos — Clasificados por Severidad

---

### P1 — CRÍTICO: `min_rr=2.0` viola RR3.0

**Archivo:** `fast_desk/setup/engine.py:FastSetupConfig`  
**Problema:** El gate de descarte post-spread acepta setups con RR=2.0, cuando el mandato del sistema es RR≥3.0.  
**Corrección arquitectónica:** Elevar `min_rr = 3.0` alineándolo con `rr_ratio`. Adicionalmente, cuando el spread degrada el RR por debajo de 3.0, no ajustar solo el SL — recalcular el TP desde el riesgo ajustado, o descartar directamente el setup.

---

### P2 — CRÍTICO: Señales fallidas desaparecen sin trazabilidad

**Archivos:** `fast_desk/trader/service.py`, `fast_desk/workers/symbol_worker.py`  
**Problema:** Si `send_entry()` lanza una excepción, el bloque `runtime_db.upsert_fast_signal()` nunca se ejecuta. El worker captura la excepción con un simple `print()`. No hay escritura en DB, no hay alerta, no hay visibilidad en WebUI.  
**Evidencia viva:** `fast_desk_signals = 0 rows`, `fast_desk_trade_log = 0 rows` a pesar de 5 workers activos y pipeline que valida OK offline.  
**Corrección arquitectónica:**  
1. Persistir el intento de señal con `outcome="pending"` ANTES de enviar a ejecución.
2. Actualizar el registro a `accepted|rejected|error` después.
3. Persistir excepciones en una tabla `fast_desk_errors` con stack trace.
4. Emitir `activity_log` con el error para visibilidad inmediata.

---

### P3 — CRÍTICO: Lot size irreal puede causar rechazo silencioso del broker

**Archivo:** `fast_desk/risk/engine.py`  
**Problema:** Para cuentas grandes (ej. demo $1.18M), la fórmula calcula lotes altísimos (hasta 248 lots de GBPUSD = $33M notional) que son rechazados por el broker sin error explícito visible. El cap de `50.0` lots en el engine es demasiado alto para cuentas demo típicas o para instrumentos con alto `contract_size`.  
**Problema secundario:** El `FastRiskConfig` no expone un `max_lot_size` configurable por usuario. Solo hay un hard-cap de 50.0 en código.  
**Corrección arquitectónica:**  
1. Añadir `max_lot_size: float = 10.0` a `FastRiskConfig` (configurable desde Settings).
2. Aplicar `volume = min(volume, config.max_lot_size, volume_max_from_spec)`.
3. Validar el lote resultante contra `volume_min` del spec antes de ejecutar.

---

### P4 — ALTO: `scanner.py` es código muerto que crea ambigüedad de inventario

**Archivo:** `fast_desk/signals/scanner.py`  
**Problema:** El archivo contiene un scanner completo (`FastScannerConfig`, `FastSignal`, `_ema()`, `_atr()`) que no está conectado al pipeline `FastTraderService`. El pipeline usa exclusivamente `FastSetupEngine`. El scanner legacy tiene su propia definición de `rr_ratio=3.0` y confidence que diverge del engine activo.  
**Riesgo:** Un desarrollador puede modificar el scanner creyendo que afecta al trader activo, introduciendo bugs invisibles. Confusión en auditorías futuras.  
**Corrección arquitectónica:** Marcar con `# DEPRECATED — not used in FastTraderService pipeline` o eliminar. Documentar explícitamente que el punto de entrada de setups es `FastSetupEngine`.

---

### P5 — ALTO: FVG (Fair Value Gaps) no integrado — oportunidad crítica para scalping

**Archivo:** `smc_desk/detection/fair_value_gaps.py` existe pero no se usa en Fast Desk  
**Problema:** Los FVGs son la herramienta de mayor eficiencia en scalping institucional. Son zonas de desequilibrio precio que actúan como imanes y puntos de reversión de alta probabilidad en M1/M5. El Fast Desk no los detecta ni usa como:
- zona de entrada en pullbacks
- confirmación de setup
- confluencia con order blocks
- nivel de TP intermedio (primera isla de liquidez)

Un setup `order_block_retest` + FVG sin llenar en la misma zona tiene una tasa de conversión estadísticamente superior a una OB sin FVG.  
**Corrección arquitectónica:** Integrar `detect_fair_value_gaps()` en `FastSetupEngine` como:
1. Un nuevo setup `fvg_retest` (mayor velocity que OB retest)
2. Un multiplicador de confidence para OBs que coincidan con FVGs sin llenar

---

### P6 — ALTO: `micro_choch` como trigger tiene baja fiabilidad estructural

**Archivo:** `fast_desk/trigger/engine.py`  
**Problema:** El trigger `micro_choch` usa `detect_market_structure(candles[-80:], window=2)` en M1. Pero un CHoCH en M1 es extremadamente común y frecuentemente ruidoso — representa cualquier rotura momentánea de estructura sin necesidad de momentum real. En scalping, un CHoCH en M1 NO equivale a confirmación de reversión; es simplemente noise en muchos contextos.  
**Consecuencia:** El trigger puede confirmar setups en momentos de volatilidad aleatoria, generando entradas antes de que el impulso real comience.  
**Corrección arquitectónica:**  
1. El `micro_choch` debe requerir que el CHoCH esté `confirmed=True` (BOS posterior en la misma dirección) — el campo existe en la struct pero no se verifica.
2. Opcional: desclasificar el `micro_choch` de 0.79 a 0.60 y combinarlo con un requisito de volumen o cuerpo mínimo.

---

### P7 — ALTO: `rejection_candle` trigger opera sobre ÚLTIMA vela cerrada solamente

**Archivo:** `fast_desk/trigger/engine.py`  
**Problema:** El trigger `rejection_candle` evalúa únicamente `candles[-1]` — la vela más reciente. Para un scalper, este criterio es frágil porque:
1. No verifica contexto: la mecha puede ser ruido intra-vela, no reversión.
2. No tiene filtro de tamaño mínimo de mecha en relación al ATR.
3. No verifica que la vela de rechazo esté DENTRO de la zona del setup (OB, sweep level, etc.).
4. Una vela de rechazo genérica puede ocurrir en cualquier punto del chart, no solo en zonas relevantes.  
**Corrección arquitectónica:**  
1. Añadir filtro: mecha inferior/superior ≥ 1.5× pip_size mínimo absoluto.
2. Verificar que el low/high de la mecha esté dentro del rango ATR de la zona del setup.
3. Considerar ventana de 2-3 velas para patrón de rechazo más robusto (ej. engulfing o pin bar confirmado).

---

### P8 — ALTO: `signal_cooldown=60s` es demasiado restrictivo para scalping multi-símbolo

**Archivo:** `fast_desk/trader/service.py` — `FastTraderConfig`  
**Problema:** El cooldown de 60 segundos por símbolo bloquea toda señal adicional por 1 minuto completo. Para un sistema de scalping en M1/M5:
- Una segunda oportunidad puede aparecer en la siguiente vela M1 (60s después de la primera)
- Si la señal anterior fue rechazada por el broker, el cooldown igual se activa (el cooldown solo se actualiza si `result.get("ok")`, lo cual es correcto, pero...)
- El cooldown NO distingue entre señal ejecutada exitosamente vs señal rechazada — ver el código: `state.last_signal_at = now_mono` solo se actualiza si `result.get("ok")`. Esto SÍ está correcto.

**Problema real:** El cooldown es global por símbolo y no por setup_type. Si hay 2 setups distintos en el mismo símbolo (ej. OB retest en una zona y sweep reclaim en otra), el segundo setup queda bloqueado 60s aunque no compita con el primero.  
**Corrección arquitectónica:** Considerar cooldown por `(symbol, setup_type)` en lugar de solo por `symbol`. O reducir el cooldown a 30s para setups de alta confianza (≥0.82).

---

### P9 — MEDIO: Exhaustion detection no considera volumen real

**Archivo:** `fast_desk/context/service.py`  
**Problema:** La detección de exhaustion usa:
- % candles direccionales (proxy de momentum)
- shrinking bodies (proxy de fuerza)
- CHoCH en H1 (estructural)

Pero NO usa volumen real. En scalping, el agotamiento más fiable se detecta con volumen decreciente en la dirección dominante + rango expandido = "blowoff top/bottom". Sin volumen, el sistema puede marcar exhaustion táctile por ruido estadístico de velas pequeñas.  
**Corrección arquitectónica:** Si los candles incluyen campo `tick_volume` o `volume`, agregar un check de volumen decreciente como refuerzo. Verificar si el conector MT5 incluye `tick_volume` en los candles (documentado en `infra/mt5/connector.py`).

---

### P10 — MEDIO: `detect_market_structure` se llama 4-5 veces por ciclo con los mismos candles

**Archivos:** `context/service.py`, `setup/engine.py`, `trigger/engine.py`  
**Problema:** En un ciclo de `scan_and_execute`:
1. `FastContextService.build_context()` llama `detect_market_structure(candles_h1[-160:], window=3)` → estructura H1
2. `FastContextService._detect_market_phase()` llama `detect_market_structure(candles_m5[-80:], window=2)` → estructura M5
3. `FastSetupEngine.detect_setups()` llama `detect_market_structure(candles_m5[-180:], window=3)` → estructura M5 (diferente slice)
4. `FastSetupEngine._sr_polarity_retest()` llama `detect_market_structure(candles[-180:], window=3)` → OTRA vez sobre M5
5. `FastTriggerEngine._micro_bos()` llama `detect_market_structure(candles[-80:], window=2)` → M1
6. `FastTriggerEngine._micro_choch()` llama `detect_market_structure(candles[-80:], window=2)` → M1 MISMO

La función `detect_market_structure` incluye swing detection (O(n²)) + labeling + BOS/CHoCH — no es O(1). Llamarla 6 veces por símbolo por ciclo con slices solapadas es ineficiente y puede generar resultados inconsistentes (el slice `-80` y `-180` sobre los mismos candles pueden producir estructuras contradictorias).  
**Corrección arquitectónica:** Calcular estructuras una sola vez en `build_context()` y pasarlas como parámetros / inyectarlas al `SetupEngine` y `TriggerEngine`. Centralizar en `FastContext` los campos `structure_m5`, `structure_m1`, `structure_h1`.

---

### P11 — MEDIO: `order_block_retest` — single-use filter tiene bug por slice inconsistente

**Archivo:** `fast_desk/setup/engine.py` — `_order_block_retest()`  
**Problema:** El filtro de mitigación (single-use OB) itera sobre `candle_slice[origin_idx + 2:]` donde `candle_slice = candles_m5[-180:]`. Sin embargo, `origin_idx` viene de `detect_order_blocks()` que también opera sobre `candles_m5[-180:]`. Hasta ahí correcto.

El problema es que `detect_order_blocks()` se invoca con `min_impulse_candles=2` (parámetro Fast reducido), pero internamente usa `min_impulse_candles=3` como default. Este override a `2` reduce la calidad de validación del BOS — se acepta un "impulso" de solo 2 velas consecutivas, lo cual es insuficiente para confirmar una zona real de institución. En M5, 2 velas = 10 minutos de movimiento, que puede ser puramente intrabar ruido.  
**Corrección arquitectónica:** Elevar `min_impulse_candles=3` en la llamada Fast o agregar un filtro adicional que valide el tamaño del impulso en ATR (impulso ≥ 1.5× ATR para ser considerado institucional).

---

### P12 — MEDIO: `breakout_retest` — BOS index check puede dar falsos positivos por slice offset

**Archivo:** `fast_desk/setup/engine.py` — `_breakout_retest()`  
**Problema:** El BOS viene de `structure_m5 = detect_market_structure(candles_m5[-180:], window=3)`. El `bos.index` es relativo al slice `-180`. La verificación de "BOS reciente" en `_breakout_retest` NO existe — simplemente verifica si el precio está cerca del nivel (`near_retest = abs(latest_close - level) <= atr * 0.5`). Esto significa que un BOS de hace 180 velas (15 horas de M5) puede generar un setup de "retest" si el precio regresa casualmente al nivel.  
**Corrección arquitectónica:** Agregar filtro de edad: el BOS debe haber ocurrido en las últimas N velas M5 (ej. ≤ 30 = 2.5 horas). Los setups de retest viejos son setups inválidos para scalping.

---

### P13 — MEDIO: `wedge_retest` — detección sobre sólo 18 velas es altamente ruidosa

**Archivo:** `fast_desk/setup/engine.py` — `_wedge_retest()`  
**Problema:** El wedge se detecta comparando la primera y última vela de una ventana de 18 candles M5 (= 90 minutos). Comparar solo `sample[0]` vs `sample[-1]` es extremadamente naive: ignora velas intermedias. Un canal de 18 velas donde velas 1 y 18 tienen las características de wedge, pero las velas 2-17 son caóticas, se detecta igual. La confidence de 0.69 puede ser excesiva para un detector tan rudimentario.  
**Corrección arquitectónica:**  
1. Verificar progresión suave de highs y lows (regresión lineal simple sobre highs y lows).
2. Reducir confidence a 0.60 o exigir trigger más robusto (solo `micro_bos` o `displacement` para wedge — no `rejection_candle`).

---

### P14 — MEDIO: `custody` — `hard_cut_r = 1.25` con `be_trigger_r = 1.2` es contradicción lógica

**Archivo:** `fast_desk/custody/engine.py` — `FastCustodyPolicyConfig`  
**Problema:** La custodía mueve a break-even cuando `profit_pips >= risk_pips * 1.2` (`be_trigger_r`). El hard cut cierra cuando `loss_pips >= risk_pips * 1.25` (`hard_cut_r`). La separación entre estos dos thresholds es solo 0.05× el riesgo inicial. Esto crea una zona de ambigüedad extrema:
- Si la posición llega a +1.2R y revierte, el sistema la lleva a BE.
- Si desde BE continúa retrocediendo hasta -1.25R (desde el precio de apertura), se cierra.
- Pero hay un caso: si la posición nunca llegó a +1.2R (no hubo BE activado), el hard_cut en 1.25R significa que la posición puede perderse 1.25× el riesgo planificado — un 25% extra de pérdida sobre el SL original.

**Para RR3.0, un hard_cut en 1.25R tiene consecuencias graves:** reduce el RR real efectivo significativamente si el sistema no respeta el SL de mercado y permite que la posición pierda extra.  
**Corrección arquitectónica:** El `hard_cut_r` debe ser ≤ 1.0 (en el SL diseñado) o la posición debería cerrarse por MT5 stop loss directamente. El hard_cut solo tiene sentido como protección cuando el SL no se ejecuta (ej. gap). Documentar el caso de uso explícitamente.

---

### P15 — MEDIO: Pending orders `reprice_threshold_pips = 8.0` sin calibración por asset class

**Archivo:** `fast_desk/pending/manager.py` — `FastPendingPolicyConfig`  
**Problema:** El threshold de repreciado es 8 pips para TODOS los símbolos. Para EURUSD, 8 pips es significativo (≈ 2× spread típico). Para BTCUSD, 8 pips es trivial (< 0.01% del precio). Para XAU/USD (GOLD), 8 pips puede ser $0.80 (probablemente muy estricto).  
**Corrección arquitectónica:** El `reprice_threshold_pips` debe ser relativo al ATR o al spread del símbolo. Alternativa: expresarlo como múltiplo del spread (`reprice_threshold = 4.0 * spread_pips`).

---

### P16 — BAJO: `_ema_check` en contexto calcula EMA de forma incorrecta (seed)

**Archivo:** `fast_desk/context/service.py` — `_ema_check()`  
**Problema:** La función `_ema()` local usa `ema = data[0]` como seed (primer dato) y luego itera desde `data[1:]`. Esto significa que si el primer valor de closes es un outlier (ej. gap de apertura de semana), contamina toda la serie EMA sin período de warm-up. El EMA correcto usa `seed = mean(data[:period])` para estabilizar. Ironicamente, la función `_ema()` en `scanner.py` (legacy) SÍ lo hace correctamente.  
**Corrección arquitectónica:** Unificar en una sola función `_ema()` utilitaria con warm-up correcto, usada por ambos contexts (scanner_legacy y context_service).

---

### P17 — BAJO: Directional concentration gate tiene threshold fijo 70% no calibrado

**Archivo:** `fast_desk/policies/entry.py`  
**Problema:** El gate de concentración direccional bloquea cuando ≥70% de las posiciones abiertas van en la misma dirección. Con `max_positions_total = 4`, el gate se activa con 3/4 posiciones en la misma dirección. Esto es correcto como anti-sobreexposición. Sin embargo, `max_positions_per_symbol = 1` hace que este gate sea redundante en la práctica — si cada símbolo solo puede tener 1 posición, y hay 4 símbolos, 3 posiciones buy con 1 sell nunca representan la misma exposición que 3 posiciones buy del mismo símbolo.  
**Corrección arquitectónica:** El gate de concentración tiene lógica correcta pero documentar explícitamente que es protección de desbalance de cartera, no de símbolo. No es un problema de funcionalidad sino de claridad.

---

## 5. Oportunidades de Mejora Estratégica (Recommendations for RR3.0+ scalping)

### 5.1 Integrar FVG como herramienta de confluencia y filtro de calidad

Fair Value Gaps abren oportunidades de alta precisión que el sistema actual ignora completamente:

```
Setup de máxima calidad para scalping:
OB bullish M5 + FVG sin llenar dentro del OB + micro_bos M1
→ Confidence esperado: 0.88+
→ RR realizable: 3.0-5.0 con probabilidad alta
```

La implementación requiere:
1. `detect_fair_value_gaps(candles_m5[-80:])` en el `FastSetupEngine`
2. Un nuevo setup `fvg_retest` con confidence 0.80
3. Bonus de confidence (+0.06) para OBs que coincidan con FVGs no mitigados

### 5.2 Añadir M1 Volume Filter para trigger displacement

El trigger `displacement` (0.81 confidence) es el segundo más confiable, pero opera solo sobre el tamaño del cuerpo. Añadir verificación de `tick_volume` relativo al promedio amplificaría la señal:

```python
# Pseudocódigo mejora
vol_factor = tick_vol_last / avg_tick_vol_prev
if body_factor >= 1.8 AND vol_factor >= 1.5:
    confidence = 0.88  # upgraded
elif body_factor >= 1.8:
    confidence = 0.81  # current
```

### 5.3 Session-aware RR adjustment

El RR óptimo varía por sesión:
- **London open (07:00-09:00 UTC):** Mayor momentum, RR3.0 alcanzable con setups de breakout
- **New York open (13:00-15:00 UTC):** Overlap máximo, RR3.0-4.0 en tendencia clara
- **New York tarde (18:00-20:00 UTC):** Mercado decaye, RR2.5 más realista — setups de menor calidad pero válidos

La configuración actual no distingue comportamiento por sub-sesión. Un mecanismo de `rr_ratio_override` por sesión permitiría escalar el target en high-momentum sessions.

### 5.4 Confluence scorer para ranking de setups

El `FastSetupEngine` actualmente asigna confidence fija por setup_type. Una mejora seria sería un **confluence score** que combine múltiples señales:

| Confluencia | Peso |
|-------------|------|
| OB confluye con FVG | +0.08 |
| OB en zona Premium/Discount correcta | +0.04 (ya implementado como filtro, pero debería sumar confidence) |
| H1 CHoCH reciente en dirección del setup | +0.05 |
| Volumen por encima del promedio en vela de setup | +0.03 |
| BOS M5 reciente en dirección del trade | +0.04 |
| Sesión de alta liquidez | +0.02 |

Con esto, el rango real de confidence sería 0.60-0.98, y el filtro de `min_confidence=0.55` actuaría como gate de calidad real, no solo tipo de setup.

### 5.5 Trailing stop estructural en M1 vs M5

El `FastCustodyEngine` usa M1 para el trailing estructural pero calcula el nivel estructural sobre las últimas `candles[-8:]` de M1 — solo 8 minutos de datos. Para scalping en tendencia, el trailing debería seguir la estructura del timeframe del setup (M5), no del trigger (M1). El M1 es demasiado ruidoso para trailing estructural en posiciones con objetivo de 3R.

**Corrección:** Usar `structural_level` de M5 para el trailing una vez que la posición supere 2R, y M1 solo para la gestión táctica temprana (0-1R de profit).

---

## 6. Problemas Operativos Activos (deuda heredada sin resolver)

| ID | Problema | Severidad | Estado |
|----|----------|-----------|--------|
| DT-001 | Señales fallidas no persisten en DB | CRÍTICA | ABIERTO |
| DT-002 | scan_error capturado silenciosamente | CRÍTICA | ABIERTO |
| DT-003 | Lot size irreal para cuentas grandes | ALTA | ABIERTO |
| DT-004 | Sin endpoint diagnóstico `/fast/diag/{symbol}` | ALTA | ABIERTO |
| OP-001 | Tokyo session bloqueada (default) — gaps de 6h sin operación | MEDIA | CONOCIDO |
| OP-002 | require_h1_alignment filtra setups válidos cuando H1=neutral | MEDIA | CONOCIDO |
| OP-003 | Signal cooldown 60s por símbolo bloquea segunda oportunidad mismo ciclo | MEDIA | NUEVO |

---

## 7. Tabla Resumen de Problemas

| ID | Severidad | Componente | Descripción breve | Impacto en RR |
|----|-----------|------------|-------------------|---------------|
| P1 | 🔴 CRÍTICO | setup/engine.py | `min_rr=2.0` viola mandato RR3.0+ | DIRECTO |
| P2 | 🔴 CRÍTICO | trader/service.py | Señales faltadas desaparecen sin trazabilidad | OPERATIVO |
| P3 | 🔴 CRÍTICO | risk/engine.py | Lotes irreales provocan rechazo broker | OPERATIVO |
| P4 | 🟠 ALTO | signals/scanner.py | Scanner legacy es código muerto confuso | CONFUSIÓN |
| P5 | 🟠 ALTO | fast_desk (general) | FVG no integrado — herramienta key de scalping | CALIDAD RR |
| P6 | 🟠 ALTO | trigger/engine.py | micro_choch sin validar `confirmed=True` | SEÑALES FALSAS |
| P7 | 🟠 ALTO | trigger/engine.py | rejection_candle opera sobre 1 vela sin contexto | SEÑALES FALSAS |
| P8 | 🟠 ALTO | trader/service.py | Cooldown global por símbolo pierde oportunidades | OPORTUNIDAD |
| P9 | 🟡 MEDIO | context/service.py | Exhaustion sin volumen real | CALIDAD |
| P10 | 🟡 MEDIO | múltiples | `detect_market_structure` llamado 6× mismo ciclo | PERFORMANCE |
| P11 | 🟡 MEDIO | setup/engine.py | OB con `min_impulse_candles=2` baja calidad | SEÑALES FALSAS |
| P12 | 🟡 MEDIO | setup/engine.py | BOS sin filtro de edad — setups demasiado viejos | SEÑALES FALSAS |
| P13 | 🟡 MEDIO | setup/engine.py | Wedge sobre 18 velas comparando solo primera y última | SEÑALES FALSAS |
| P14 | 🟡 MEDIO | custody/engine.py | hard_cut_r=1.25 mayor que SL planificado | DILUCIÓN RR |
| P15 | 🟡 MEDIO | pending/manager.py | reprice threshold fijo sin calibración por asset | OPERATIVO |
| P16 | 🔵 BAJO | context/service.py | EMA seed incorrecto en `_ema_check` | MENOR |
| P17 | 🔵 BAJO | policies/entry.py | Concentration gate redundante con max_positions_per_symbol=1 | MENOR |

---

## 8. Prioridades de Corrección Recomendadas

### Fase 1 — Correcciones urgentes (deben estar antes del primer trade live)

1. **P1**: Elevar `min_rr = 3.0` en `FastSetupConfig` — 5 min de cambio, impacto directo en RR
2. **P3**: Añadir `max_lot_size: float` configurable en `FastRiskConfig` con default seguro — debloquea operaciones rechazadas por broker
3. **P2**: Envolver ejecución en try/except con escritura en DB de señal fallida — 30 min de trabajo, crítico para observabilidad

### Fase 2 — Mejoras de calidad de señal

4. **P6**: Verificar `choch["confirmed"] == True` en `_micro_choch` trigger — reduce falsas confirmaciones
5. **P12**: Filtro de edad en `breakout_retest` — elimina setups obsoletos
6. **P11**: Elevar `min_impulse_candles = 3` en OB detection — mejora calidad de zonas

### Fase 3 — Mejoras arquitectónicas de performance y calidad

7. **P10**: Centralizar estructuras precalculadas en `FastContext` — reduce cálculos duplicados
8. **P5**: Integrar FVG detection como confluencia en `FastSetupEngine` — nueva herramienta de alta valor
9. **P7**: Mejorar `rejection_candle` con contexto de zona y filtro ATR

### Fase 4 — Optimización estratégica avanzada

10. Confluence scorer dinámico (sección 5.4)
11. Session-aware RR targets (sección 5.3)
12. Volume filter en displacement trigger (sección 5.2)
13. M5 structural trailing para posiciones > 2R (sección 5.5)

---

## 9. Diagrama de Estado Actual vs Estado Objetivo

### Estado Actual (2026-03-27)

```
Fast Desk Pipeline:
  Context ✅ (7 hard gates, 3 warnings)
  Setup   ⚠️ (7 patrones, min_rr=2.0, sin FVG, OB con impulso débil)
  Trigger ⚠️ (5 triggers, micro_choch sin confirmed check, rejection_candle débil)
  Risk    ⚠️ (lotes irreales en cuentas grandes)
  Entry   ✅ (max_positions_total=4, concentration gate funcional)
  Execution ❌ (señales fallidas desaparecen, 0 registros en DB)
  Custody ⚠️ (hard_cut > SL planificado, trailing M1 ruidoso)
  Pending ⚠️ (reprice threshold fijo no calibrado)

RR real del sistema: 2.0 - 3.0 (min_rr viola mandato)
Observabilidad: BAJA (errores no persistidos)
```

### Estado Objetivo (post-correcciones)

```
Fast Desk Pipeline:
  Context ✅ (idem)
  Setup   ✅ (7 patrones + FVG, min_rr=3.0, OB con min_impulse=3, BOS age filter)
  Trigger ✅ (micro_choch con confirmed=True, rejection_candle en zona, displacement+vol)
  Risk    ✅ (max_lot_size configurable, margin check pre-ejecución)
  Entry   ✅ (idem)
  Execution ✅ (señales persistidas pre y post ejecución)
  Custody ✅ (hard_cut = 1.0R, trailing M5 para posiciones maduras)
  Pending ✅ (reprice threshold relativo a ATR/spread)

RR real del sistema: 3.0+ garantizado por construcción
Observabilidad: ALTA (DB trail completo)
```

---

*Documento generado por GitHub Copilot — Auditor especializado scalping — 2026-03-27*  
*Alcance: sólo lectura, sin modificaciones de código*
