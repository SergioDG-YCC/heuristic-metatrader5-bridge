# WebUI Repair — Phase 2 Execution Report

**Fecha**: 2026-03-25  
**Estado**: Phase 2 Completada ✅  
**Próximo**: Phase 3 (Consumir datos en FastDesk y SmcDesk routes)

---

## Resumen de Cambios Phase 2

### Step 2.1: ✅ Agregar endpoint `/api/v1/feed-health`

**Archivo Backend**: `apps/control_plane.py`

```python
@app.get("/api/v1/feed-health")
async def feed_health() -> dict[str, Any]:
    """Get detailed feed health for all subscribed symbols."""
    svc = _require_service()
    return {
        "status": "success",
        "feed_status": svc.feed_status_rows,
        "updated_at": utc_now_iso(),
    }
```

**Respuesta**:
```json
{
  "status": "success",
  "feed_status": [
    {
      "symbol": "BTCUSD",
      "timeframe": "M5",
      "bar_age_seconds": 45,
      "bar_count": 200,
      "state": "up"
    }
  ],
  "updated_at": "2026-03-25T14:30:00Z"
}
```

---

### Step 2.2: ✅ Agregar endpoint `/api/v1/desk-status`

**Archivo Backend**: `apps/control_plane.py`

```python
@app.get("/api/v1/desk-status")
async def desk_status() -> dict[str, Any]:
    """Get status of both Fast and SMC desks."""
    svc = _require_service()
    
    fast_desk_enabled = hasattr(svc, "_fast_desk") and svc._fast_desk is not None
    fast_config = None
    if hasattr(svc, "fast_desk_config") and svc.fast_desk_config:
        fast_config = svc.fast_desk_config.to_dict() if hasattr(svc.fast_desk_config, "to_dict") else {}
    
    smc_desk_enabled = hasattr(svc, "_smc_desk") and svc._smc_desk is not None
    smc_config = None
    if hasattr(svc, "smc_desk_config") and svc.smc_desk_config:
        smc_config = svc.smc_desk_config.to_dict() if hasattr(svc.smc_desk_config, "to_dict") else {}
    
    return {
        "status": "success",
        "fast_desk": {
            "enabled": fast_desk_enabled,
            "workers": len(svc.subscribed_universe) if fast_desk_enabled else 0,
            "config": fast_config,
        },
        "smc_desk": {
            "enabled": smc_desk_enabled,
            "scanner_active": smc_desk_enabled,
            "config": smc_config,
        },
        "updated_at": utc_now_iso(),
    }
```

**Respuesta**:
```json
{
  "status": "success",
  "fast_desk": {
    "enabled": true,
    "workers": 5,
    "config": {
      "scan_interval": 5.0,
      "risk_per_trade_percent": 1.0,
      "max_positions_total": 4
    }
  },
  "smc_desk": {
    "enabled": true,
    "scanner_active": true,
    "config": {
      "llm_model": "gemma-3-4b-it-qat",
      "llm_enabled": true,
      "max_candidates": 3
    }
  },
  "updated_at": "2026-03-25T14:30:00Z"
}
```

---

### Step 2.3: ✅ Frontend — Agregar Feed Health y Desk Status panels

**Archivos Frontend Modificados**:

1. **`apps/webui/src/types/api.ts`**
   - Agregado campo `trade_allowed?: boolean` en `LiveStateSnapshot`

2. **`apps/webui/src/api/client.ts`**
   - Agregados métodos:
     - `feedHealth()`
     - `deskStatus()`
     - `getLlmModels()`
     - `getLlmStatus()`
     - `setLlmDefaultModel()`
     - `getSmcConfig()`
     - `updateSmcConfig()`
     - `getFastConfig()`
     - `updateFastConfig()`
     - `getOwnershipConfig()`
     - `updateOwnershipConfig()`
     - `getRiskConfig()`
     - `updateRiskConfig()`

3. **`apps/webui/src/routes/RuntimeOverview.tsx`**
   - Agregadas señales: `feedHealth`, `deskStatus`
   - Agregado `onMount` para fetch inicial
   - Actualizadas `deskCards` para mostrar datos reales
   - Agregados dos nuevos paneles:
     - **Feed Health Panel**: Muestra edad de barras por símbolo/timeframe
     - **Desk Status Panel**: Muestra estado de Fast y SMC desks

---

## Nuevos Paneles en RuntimeOverview

### Feed Health Panel

```
┌─────────────────────────────────┐
│  Feed Health              [Live]│
├─────────────────────────────────┤
│  BTCUSD M5       45s  ● Green  │
│  EURUSD M5       30s  ● Green  │
│  GBPUSD M5       50s  ● Green  │
│  USDJPY M5       55s  ● Green  │
│  USDCHF M5       60s  ● Green  │
└─────────────────────────────────┘
```

### Desk Status Panel

```
┌─────────────────────────────────┐
│  Desk Status              [Live]│
├─────────────────────────────────┤
│  Fast Desk:  Active (5 workers) │
│  SMC Desk:   Active             │
└─────────────────────────────────┘
```

---

## Testing Checklist Phase 2

### ✅ Backend Tests
- [x] `GET /api/v1/feed-health` retorna feed_status
- [x] `GET /api/v1/desk-status` retorna fast_desk y smc_desk
- [x] `feed_status` incluye `bar_age_seconds` por símbolo
- [x] `desk_status` incluye `workers` count para Fast Desk
- [x] `desk_status` incluye `scanner_active` para SMC Desk

### ✅ Frontend Tests
- [x] TypeScript compila sin errores
- [x] `npm run build` exitoso
- [x] Feed Health panel se muestra cuando hay datos
- [x] Desk Status panel se muestra cuando hay datos
- [x] deskCards muestra "Active" cuando desk está habilitado
- [x] deskCards muestra "Disabled" cuando desk está deshabilitado

---

## Archivos Modificados

| Archivo | Cambios | Líneas |
|---------|---------|--------|
| `apps/control_plane.py` | 2 endpoints nuevos | ~50 |
| `apps/webui/src/types/api.ts` | `trade_allowed` field | ~1 |
| `apps/webui/src/api/client.ts` | 12 métodos nuevos | ~15 |
| `apps/webui/src/routes/RuntimeOverview.tsx` | Feed Health + Desk Status panels | ~80 |

**Total**: 4 archivos, ~146 líneas de cambio

---

## Próximos Pasos (Phase 3)

### Step 3.1: FastDesk — Mostrar datos reales

**Archivo**: `apps/webui/src/routes/FastDesk.tsx`

- Consumir `/api/v1/desk-status` para mostrar configuración
- Consumir `/api/v1/config/fast` para mostrar settings detallados
- Mostrar signals recientes (si existen en backend)

### Step 3.2: SmcDesk — Mostrar datos reales

**Archivo**: `apps/webui/src/routes/SmcDesk.tsx`

- Consumir `/api/v1/desk-status` para mostrar estado del scanner
- Consumir `/api/v1/config/smc` para mostrar configuración
- Mostrar tesis activas (cuando endpoint esté disponible)

### Step 3.3: Operations Store — Usar SSE

**Archivo**: `apps/webui/src/stores/operationsStore.ts`

- Suscribirse a SSE en lugar de polling cada 3s
- Mantener polling de fallback cada 30s

---

## Verificación de Compile

```bash
# Python
.\.venv\Scripts\python.exe -m py_compile apps/control_plane.py
# Result: ✅ Success

# TypeScript
npm run build
# Result: ✅ Success (115.77 kB bundle)
```

---

## Capturas de Pantalla Esperadas

### RuntimeOverview — Antes (Phase 1)
```
Desk Cards:
- Fast Desk: Preview — "Read context: Available"
- SMC Desk: Planned — "Thesis/zones: Planned"
- Risk Kernel: Planned — "Governance: Planned"
```

### RuntimeOverview — Después (Phase 2)
```
Desk Cards:
- Fast Desk: Live — "Status: Active (5 workers)"
- SMC Desk: Live — "Status: Active, Scanner: Running"
- Risk Kernel: Live — "All features: Available"

New Panels:
- Feed Health: 5 symbols con bar_age < 60s (verde)
- Desk Status: Fast/SMC status en tiempo real
```

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Phase 2 Complete ✅, Phase 3 Pending
