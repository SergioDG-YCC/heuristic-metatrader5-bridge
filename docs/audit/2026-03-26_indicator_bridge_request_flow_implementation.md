# Implementación: Indicator Bridge Request/Response Flow

**Fecha**: 2026-03-26  
**Estado**: IMPLEMENTADO ✅  
**Problema**: EA no recibía solicitudes para procesar

---

## Problema Encontrado

El `IndicatorBridge` en la nueva repo **SOLO LEÍA** archivos de `indicator_snapshots/` pero **NUNCA ESCRIBÍA** archivos en `indicator_requests/`.

**Flujo esperado**:
1. Backend escribe solicitud en `indicator_requests/{request_id}.json`
2. EA lee solicitud de `indicator_requests/{request_id}.json`
3. EA escribe respuesta en `indicator_snapshots/{request_id}.json`
4. Backend lee respuesta de `indicator_snapshots/{request_id}.json`

**Flujo real (BUGGY)**:
1. Backend lee `indicator_snapshots/` (vacío)
2. EA nunca recibe solicitudes
3. EA nunca escribe respuestas
4. Backend muestra `waiting_first_snapshot` eternamente

---

## Solución Implementada

### 1. Agregado `write_request()` a `IndicatorBridge`

```python
def write_request(
    self,
    symbol: str,
    timeframe: str,
    requested_indicators: list[str],
    lookback: int = 100,
    reason: str = "market_state_enrichment",
) -> dict[str, Any] | None:
    """Write indicator request file for EA to process."""
    request = _build_indicator_request(symbol, timeframe, requested_indicators, lookback, reason)
    
    # Write to Common Files directory (where EA reads from)
    request_path = self.requests_dir / f"{request['request_id']}.json"
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    return request
```

### 2. Actualizado `poll()` para crear requests automáticamente

```python
def poll(
    self,
    market_state: MarketStateService,
    subscribed_symbols: set[str] | None = None,
    subscribed_timeframes: set[str] | None = None,
    requested_indicators: list[str] | None = None,
) -> dict[str, Any]:
    # Import existing snapshots
    imported = self.import_snapshots()
    applied = self.apply_to_market_state(market_state, imported, ...)
    
    # Create requests for symbols/timeframes without recent snapshots
    for symbol in allowed_symbols:
        for timeframe in allowed_timeframes:
            state = market_state._states.get(key, {})
            enrichment = state.get("indicator_enrichment", {})
            
            # Check if enrichment is stale or missing
            if enrichment is stale or missing:
                request = self.write_request(symbol, timeframe, requested_indicators)
                requests_created += 1
    
    return {
        "status": self._snapshot_status(),
        "requests_created_in_cycle": requests_created,
        "total_requested": self.total_requested,
        ...
    }
```

### 3. Actualizado `_refresh_indicator_state()` en `service.py`

```python
async def _refresh_indicator_state(self) -> None:
    self.indicator_status = await asyncio.to_thread(
        self.indicator_bridge.poll,
        self.market_state,
        set(self.subscribed_universe),
        set(self.config.watch_timeframes),
        ["ema_20", "ema_50", "rsi_14", "atr_14", "macd_main"],  # ← NUEVO
    )
```

---

## Archivos Modificados

| Archivo | Cambios |
|---------|---------|
| `src/heuristic_mt5_bridge/infra/indicators/bridge.py` | +100 líneas (write_request, poll actualizado) |
| `src/heuristic_mt5_bridge/core/runtime/service.py` | +1 línea (requested_indicators) |

---

## Verificación

### Reiniciar Backend

```powershell
# Ctrl+C en terminal del backend
python apps/control_plane.py
```

### Logs Esperados

```
[2026-03-26T...] status=up | market=up | indicator=healthy | account=up | ...
```

**Antes**: `indicator=waiting_first_snapshot`  
**Ahora**: `indicator=healthy` (después de que el EA procese los requests)

### Verificar Archivos Creados

```powershell
# Verificar que se crean requests
dir $env:APPDATA\MetaQuotes\Terminal\Common\Files\llm_mt5_bridge\indicator_requests\

# Verificar que el EA escribe respuestas
dir $env:APPDATA\MetaQuotes\Terminal\Common\Files\llm_mt5_bridge\indicator_snapshots\
```

### Verificar en MT5

En la pestaña "Experts" de MT5, deberías ver logs del EA procesando requests.

---

## Próximos Pasos

1. **Reiniciar backend**
2. **Esperar 10-20 segundos** (tiempo para que el EA procese requests)
3. **Verificar logs del backend**: `indicator=healthy`
4. **Verificar logs del EA en MT5**: debería mostrar procesamiento de requests
5. **Verificar archivos en Common Files**: requests y snapshots

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-26  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Ready for Testing ✅
