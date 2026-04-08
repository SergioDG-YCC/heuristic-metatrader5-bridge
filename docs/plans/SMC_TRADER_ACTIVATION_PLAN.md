# SMC Trader — Plan de Activación

> Fecha: 2026-04-02  
> Referencia: Fast Trader como patrón de implementación  
> Objetivo: Habilitar ejecución directa desde tesis SMC (pending orders + custody)

---

## 1. Estado Actual — Inventario

### ✅ Lo que EXISTE y funciona

| Componente | Archivo | Estado |
|------------|---------|--------|
| Scanner (zonas, liquidez, estructura) | `smc_desk/scanner/scanner.py` | Completo |
| Analyst (heurístico + LLM validator) | `smc_desk/analyst/heuristic_analyst.py` + `smc_desk/llm/validator.py` | Completo |
| Thesis Store (CRUD SQLite) | `smc_desk/state/thesis_store.py` | Completo |
| Runtime (scanner → analyst dispatch) | `smc_desk/runtime.py` | Completo (solo análisis) |
| Carpeta `smc_desk/trader/` | `__init__.py` vacío | Scaffold |
| **Wiring en CoreRuntime** | `core/runtime/service.py` | **Ya pasa** `risk_gate_ref` y `ownership_register_ref` al SMC desk |
| **RiskKernel** soporta `desk="smc"` | `core/risk/kernel.py` | Budget allocation `smc_weight=0.8` ya configurado |
| **OwnershipRegistry** soporta `owner="smc"` | `core/ownership/registry.py` | `smc_owned` tag ya definido |
| **MT5Connector** execution surface | `infra/mt5/connector.py` | `send_execution_instruction`, `modify_order_levels`, `remove_order`, `close_position` |
| **FastExecutionBridge** (reutilizable) | `fast_desk/execution/bridge.py` | Wrapper genérico sobre MT5Connector |

### ❌ Lo que FALTA (componentes nuevos)

| Componente | Archivo propuesto | Complejidad | Función |
|------------|-------------------|-------------|---------|
| **SmcTraderService** | `smc_desk/trader/service.py` | Alta (~400 líneas) | Orquestador: thesis → order → custody |
| **SmcEntryPolicy** | `smc_desk/trader/entry_policy.py` | Baja (~80 líneas) | Límites por símbolo, máx. posiciones SMC |
| **SmcCustodyEngine** | `smc_desk/trader/custody.py` | Media (~200 líneas) | Monitoreo TP1/TP2/SL + modificación |
| **SmcPendingManager** | `smc_desk/trader/pending.py` | Media (~150 líneas) | Lifecycle de pending orders: place/modify/cancel |
| **SmcSymbolWorker** | `smc_desk/trader/worker.py` | Media (~150 líneas) | Async loop por símbolo: monitor + custody |
| **Runtime wiring** (extensión) | `smc_desk/runtime.py` | Baja (modificación) | Agregar trader task al TaskGroup |
| **CoreRuntime wiring** (extensión) | `core/runtime/service.py` | Baja (modificación) | Pasar `connector` + `account_payload_ref` + `mt5_call_ref` al SMC desk |
| **Config vars** | `configs/base.env.example` | Trivial | `SMC_TRADER_ENABLED`, parámetros de riesgo |

---

## 2. Diferencias Fundamentales: SMC Trader vs Fast Trader

| Aspecto | Fast Trader | SMC Trader |
|---------|-------------|------------|
| **Horizonte** | M1-M5, operación dura minutos/horas | H1-D1, operación dura horas/días/semanas |
| **Entrada** | Market order inmediata tras trigger M1 | **Pending order** en entry_zone, puede tardar días en activarse |
| **Señal** | Detectada en tiempo real (scan 5s) | **Tesis pre-calculada** con zonas + candidatos |
| **Modificación** | No se modifica (SL/TP fijos, trailing) | **Se modifica si la tesis cambia** (nuevo análisis → reprice/cancel) |
| **Custody** | Trailing ATR/structural agresivo (2s loop) | **Pasiva**: monitoreo TP1 (reduce 50%), TP2 (close), SL, invalidation |
| **Pipeline** | context→setup→trigger→risk→execute | **thesis→validate→risk→pending→monitor→custody** |
| **Loop frequency** | 5s scan + 2s custody | 30-60s monitor + event-driven desde analyst |

---

## 3. Arquitectura Propuesta

```
┌──────────────────────────────────────────────────────┐
│                   SmcDeskService                      │
│                                                      │
│  ┌─────────┐    ┌──────────┐    ┌──────────────────┐ │
│  │ Scanner │───>│ Analyst  │───>│ Thesis Store     │ │
│  └─────────┘    └──────────┘    └────────┬─────────┘ │
│                                          │           │
│                    thesis_changed event   │           │
│                                          ▼           │
│                              ┌──────────────────┐    │
│                              │ SmcTraderService  │    │
│                              │                   │    │
│                              │ ┌───────────────┐ │   │
│                              │ │ EntryPolicy   │ │   │
│                              │ ├───────────────┤ │   │
│                              │ │ PendingMgr    │ │   │
│                              │ ├───────────────┤ │   │
│                              │ │ CustodyEngine │ │   │
│                              │ ├───────────────┤ │   │
│                              │ │ ExecBridge    │ │   │
│                              │ └───────────────┘ │   │
│                              └────────┬──────────┘   │
│                                       │              │
│  Per-symbol workers:                  │              │
│  ┌────────────┐ ┌────────────┐        │              │
│  │ EURUSD wkr │ │ GBPUSD wkr │ ...   │              │
│  └────────────┘ └────────────┘        │              │
└──────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   RiskKernel          OwnershipRegistry
   (desk="smc")        (owner="smc")
         │
         ▼
    MT5Connector
```

---

## 4. Flujo de Vida de una Operación SMC

### 4.1 Colocación de Pending Order (thesis → order)

```
1. Analyst produce thesis con operation_candidates[0]:
   - side="buy", entry_zone=[1.0780, 1.0790], SL=1.0740, TP1=1.0850, TP2=1.0920
   - quality="high", requires_confirmation=false

2. SmcTraderService.process_thesis(symbol, thesis):
   a. Verifica status != "watching" y candidates no vacíos
   b. Verifica quality >= umbral mínimo ("medium" | "high")
   c. Llama risk_gate_ref(symbol) → RiskKernel.evaluate_entry(desk="smc")
   d. Verifica SmcEntryPolicy: no hay pending/posición SMC activa en este símbolo
   e. Calcula volume vía RiskEngine (% riesgo sobre SL distance)
   f. Coloca PENDING ORDER:
      - entry_type = "buy_limit" (si price > entry_zone_high) o "buy_stop"
      - entry_price = midpoint(entry_zone_low, entry_zone_high)
      - SL = thesis.stop_loss
      - TP = thesis.take_profit_1 (primer target)
   g. Registra en OwnershipRegistry(owner="smc")
   h. Guarda mapping: thesis_id → order_id en SQLite
```

### 4.2 Modificación cuando la Tesis Cambia

```
1. Analyst re-ejecuta y produce nueva thesis (mismo thesis_id por continuidad):
   - entry_zone ajustada, o SL movido, o bias cambió

2. SmcTraderService.reconcile_thesis(symbol, new_thesis, old_thesis):
   a. Si bias cambió (bullish → bearish): CANCEL pending order
   b. Si validator_decision == "reject": CANCEL pending order
   c. Si entry_zone cambió > threshold:
      - modify_order_levels(order_id, new_price, new_sl, new_tp)
   d. Si SL/TP cambió pero entry_zone igual:
      - modify_order_levels(order_id, same_price, new_sl, new_tp)
   e. Si thesis pasó de "prepared" → "watching": CANCEL
   f. Log toda modificación al ownership event trail
```

### 4.3 Pending Order se Activa (filled)

```
1. Reconciliation loop detecta: orden pending → posición abierta
   (OwnershipRegistry.reconcile_from_caches detecta fill)

2. SmcCustodyEngine toma control:
   - Modo: monitoreo pasivo cada 30-60 segundos
   - Acciones:
     a. TP1 alcanzado → close 50% volume, mover SL a breakeven
     b. TP2 alcanzado → close 100% restante
     c. SL hit → posición cerrada por broker (nada que hacer, logging)
     d. Invalidation condition de thesis → close inmediato
     e. Thesis re-analizada con quality="low" → close parcial/total
```

### 4.4 TTL y Expiración

```
- Pending orders SMC tienen TTL configurable (default: 7 días)
  - A diferencia de Fast (15min TTL), SMC opera en timeframes largos
- Si la thesis tiene review_deadline y el analyst no la renueva → cancel
- Si el analyst la renueva pero candidates vacíos → cancel
```

---

## 5. Detalle por Componente

### 5.1 SmcTraderService (`smc_desk/trader/service.py`)

```python
class SmcTraderService:
    """Orquesta thesis → pending order → custody para SMC desk."""

    def __init__(self, *, config: SmcTraderConfig):
        self.config = config
        self.entry_policy = SmcEntryPolicy(config)
        self.pending_manager = SmcPendingManager(config)
        self.custody_engine = SmcCustodyEngine(config)
        self.execution = FastExecutionBridge()  # Reutilizar

    def process_thesis(self, symbol, thesis, ...) -> dict | None:
        """Evalúa thesis y coloca/modifica/cancela pending order."""
        ...

    def run_custody_cycle(self, symbol, ...) -> dict:
        """Evalúa posiciones y pending orders SMC-owned."""
        ...
```

**Campos del thesis que se mapean a ejecución:**

| Thesis field | Uso en ejecución |
|-------------|------------------|
| `operation_candidates[0].side` | Dirección de la order |
| `operation_candidates[0].entry_zone_low/high` | Precio de la pending order |
| `operation_candidates[0].stop_loss` | SL de la order |
| `operation_candidates[0].take_profit_1` | TP inicial (primer target) |
| `operation_candidates[0].take_profit_2` | TP custody (segundo target) |
| `operation_candidates[0].volume_options` | Volumen sugerido (validado por RiskEngine) |
| `operation_candidates[0].quality` | Gate: "low" → no ejecutar |
| `operation_candidates[0].requires_confirmation` | Si true → esperar siguiente analyst run |
| `status` | "active"/"prepared" → ejecutar, "watching" → no |
| `bias` | Debe coincidir con side del candidato |
| `thesis_id` | Tracking continuidad thesis↔order |
| `invalidations[]` | Condiciones para cerrar posición |
| `watch_levels[]` | Niveles de alerta (futuro) |

### 5.2 SmcEntryPolicy (`smc_desk/trader/entry_policy.py`)

```python
class SmcEntryPolicy:
    def can_open(self, symbol, side, smc_open_operations, risk_limits) -> (bool, str):
        # max_smc_positions_per_symbol (default: 1)
        # max_smc_positions_total (default: 5)
        # no_duplicate_side: no 2 buys en el mismo símbolo
```

### 5.3 SmcPendingManager (`smc_desk/trader/pending.py`)

```python
class SmcPendingManager:
    def evaluate_pending(self, order, thesis, current_price, pip_size) -> SmcPendingDecision:
        # TTL check: order age > smc_pending_ttl_seconds (default: 604800 = 7d)
        # Thesis validity: thesis still "active"/"prepared"?
        # Reprice: if thesis entry_zone changed significantly
        # Cancel: thesis rejected/expired/bias_changed

    def thesis_changed(self, order, old_thesis, new_thesis) -> SmcPendingDecision:
        # Compare entry zones, SL, TP, bias → modify/cancel/hold
```

Diferencias clave con FastPendingManager:
- **TTL mucho mayor** (7 días vs 15 min)
- **Reprice driven by thesis** (no por distancia de precio actual)
- **Cancel driven by analyst** (bias change, reject, invalidation)

### 5.4 SmcCustodyEngine (`smc_desk/trader/custody.py`)

```python
class SmcCustodyEngine:
    def evaluate_position(self, position, thesis, current_price, pip_size) -> SmcCustodyDecision:
        # TP1 hit → scale_out (close 50%, move SL to breakeven)
        # TP2 hit → close_all
        # thesis invalidated → close_all
        # thesis quality downgraded to "low" → close_all
        # loss > 1.5x risk → hard_cut (protective, shouldn't happen with SL)
```

Diferencias clave con FastCustodyEngine:
- **Sin trailing ATR/structural** (SMC confía en niveles definidos por tesis)
- **Scale-out en TP1** en vez de trailing
- **Cierre por invalidación de tesis** (concepto que no existe en Fast)
- **Loop más lento** (30-60s vs 2s)

### 5.5 SmcSymbolWorker (`smc_desk/trader/worker.py`)

```python
class SmcSymbolWorker:
    async def run(self, symbol, ...):
        while True:
            # 1. Load latest thesis for symbol
            # 2. Load SMC-owned pending orders + positions
            # 3. If thesis has candidates and no active order → process_thesis
            # 4. If active pending → pending_manager.evaluate
            # 5. If active position → custody_engine.evaluate
            # 6. Execute decisions via execution bridge
            await asyncio.sleep(30)  # 30s cycle (configurable)
```

---

## 6. Wiring Changes (Modificaciones a código existente)

### 6.1 `smc_desk/runtime.py` — Agregar trader al TaskGroup

```python
# En SmcDeskService.__init__:
self._trader: SmcTraderService | None = None  # None si SMC_TRADER_ENABLED=false

# En run_forever():
async with asyncio.TaskGroup() as tg:
    tg.create_task(self._scanner.run_forever(...), name="smc_scanner")
    tg.create_task(self._dispatch_loop(), name="smc_analyst_dispatch")
    if self._trader is not None:
        tg.create_task(
            self._trader.run_forever(
                service=self._service,
                spec_registry=self._spec_registry,
                connector=self._connector,            # NUEVO parámetro
                account_payload_ref=self._account_ref, # NUEVO parámetro
                db_path=self._db_path,
                broker_server=self._broker_server,
                account_login=self._account_login,
                risk_gate_ref=self._risk_gate_ref,
                ownership_register_ref=self._ownership_register_ref,
                ownership_open_ref=self._ownership_open_ref,
                mt5_call_ref=self._mt5_call_ref,
            ),
            name="smc_trader",
        )
```

### 6.2 `core/runtime/service.py` — Pasar refs adicionales

El wiring ya pasa `risk_gate_ref` y `ownership_register_ref`. Se necesita agregar:

```python
# En la sección de SMC desk de run_forever():
self._smc_desk.run_forever(
    service=self.market_state,
    broker_server=...,
    account_login=...,
    spec_registry=self.spec_registry,
    symbols_ref=...,
    risk_gate_ref=...,
    ownership_register_ref=...,
    # NUEVOS parámetros para trader:
    connector=self.connector,                          # MT5Connector
    account_payload_ref=lambda: self.account_payload,  # Posiciones/cuenta
    ownership_open_ref=lambda: self.ownership_open_for_desk(desk="smc"),
    mt5_call_ref=self._mt5_call,                       # Thread-safe wrapper
)
```

### 6.3 `configs/base.env.example` — Nuevas variables

```env
# ── SMC Trader (Step 4) ──────────────────────────
SMC_TRADER_ENABLED=false
SMC_TRADER_MIN_QUALITY=medium          # "low"|"medium"|"high"
SMC_TRADER_PENDING_TTL_SECONDS=604800  # 7 días
SMC_TRADER_CUSTODY_INTERVAL_SECONDS=30
SMC_TRADER_MAX_POSITIONS_PER_SYMBOL=1
SMC_TRADER_MAX_POSITIONS_TOTAL=5
SMC_TRADER_RISK_PER_TRADE_PCT=0.5      # Conservador: 0.5% por operación SMC
SMC_TRADER_SCALE_OUT_PCT=50            # % de volumen a cerrar en TP1
```

---

## 7. Tabla de Mapping: thesis.operation_candidates → MT5 Instruction

```
thesis.operation_candidates[0]          MT5Connector.send_execution_instruction()
─────────────────────────────────────   ──────────────────────────────────────────
side = "buy"                         →  side = "buy"
entry_zone midpoint                  →  entry_price = avg(entry_zone_low, entry_zone_high)
(precio actual vs entry_price)       →  entry_type = "buy_limit" | "buy_stop"
stop_loss                            →  stop_loss
take_profit_1                        →  take_profit  (primer target)
volume_options[0] (validado)         →  volume
"smc_thesis_{id}"                    →  comment (truncado a 160 chars)
```

**Regla entry_type:**
- `side="buy"` y `entry_price < precio_actual` → `"buy_limit"` (esperar retroceso)
- `side="buy"` y `entry_price > precio_actual` → `"buy_stop"` (breakout)
- `side="sell"` y `entry_price > precio_actual` → `"sell_limit"`
- `side="sell"` y `entry_price < precio_actual` → `"sell_stop"`

---

## 8. Fases de Implementación

### Fase A — Fundación (~1 sesión)
1. `SmcTraderConfig` dataclass con `from_env()`
2. `SmcEntryPolicy` con can_open()
3. `SmcPendingManager` con evaluate_pending() + thesis_changed()
4. `SmcCustodyEngine` con evaluate_position()
5. `SmcTraderService` con process_thesis() + run_custody_cycle()
6. Tests unitarios básicos para cada componente

### Fase B — Worker + Runtime Wiring (~1 sesión)
1. `SmcSymbolWorker` async loop
2. Extender `SmcDeskService.run_forever()` para aceptar trader
3. Extender `SmcDeskService.__init__` + `create_smc_desk_service()` con `SMC_TRADER_ENABLED`
4. Extender `CoreRuntimeService` para pasar connector/account/mt5_call al SMC desk
5. Agregar variables a `base.env.example`

### Fase C — Reconciliación + Testing (~1 sesión)
1. thesis→order mapping table en SQLite (smc_thesis_orders)
2. Reconciliation: detectar fills, cancelaciones externas
3. Integration test con MT5 demo: colocar pending, modificar, cancelar
4. End-to-end: analyst produce thesis → trader coloca order → modify on re-analysis

### Fase D — Observabilidad + Hardening
1. Activity log (como fast_desk activity_log)
2. WebUI panel para SMC operations
3. Kill-switch: `SMC_TRADER_ENABLED=false` cancela todos los pending orders SMC
4. Rate limiting: máx. 1 modificación por order por ciclo de analyst

---

## 9. Riesgos y Mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Pending order se activa durante re-análisis | Posición con tesis obsoleta | Custody lee siempre la tesis más reciente |
| Analyst produce tesis contradictoria (buy→sell en 5min) | Whipsaw de orders | Mínimo 1h entre cambios de bias por símbolo |
| Volume calculation incorrecto | Pérdida excesiva | RiskKernel budget + max 0.5% por trade + margin cap |
| MT5 rechaza pending order (spread, min distance) | Order no colocada | Retry con buffer en entry_price, log y skip |
| Thesis con entry_zone ya superada por precio | Pending order nunca se activa | Detectar y usar market order si precio ya en zona |
| Dos desks operan el mismo símbolo | Conflicto de ownership | OwnershipRegistry ya implementa desk isolation |
| Kill-switch no cancela pending orders | Operaciones huérfanas | `on_disable()` → cancel all SMC pending via OwnershipRegistry query |

---

## 10. Conclusión

**El SMC Trader está en ~60% de preparación conceptual** — la infraestructura compartida (RiskKernel, OwnershipRegistry, MT5Connector, CoreRuntime wiring) ya existe y funciona probada por el Fast Trader. Los refs ya se pasan al SMC desk pero no se consumen.

**Componentes nuevos necesarios: 5 módulos** (~980 líneas estimadas), todos siguiendo patrones ya establecidos por Fast Trader pero adaptados al horizonte temporal largo de SMC.

**Decisión clave antes de implementar:** ¿Se reutiliza `FastExecutionBridge` directamente (recomendado, es genérico) o se crea un `SmcExecutionBridge` separado? Recomendación: reutilizar, es un wrapper stateless sobre MT5Connector.
